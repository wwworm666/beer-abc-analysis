"""Приёмка на РЦ: обработка закрытых приёмок и обновление индекса iiko.

Что это. Связка модулей приёмки, которую зовут маршруты (routes/receiving.py),
MCP и шедулер (core/receiving_scheduler.py):
- обработка закрытой приёмки (process_receipt): GTIN приёмки сверяются с индексом
  «GTIN -> карточки iiko» (core/receiving_index), для ненайденных берутся названия из
  Честного знака (core/receiving_chz), заводятся строки разбора бухгалтерии
  (core/receiving_store.upsert_review), бухгалтерии уходит сообщение
  (core/receiving_notify);
- обновление индекса из iiko (кнопка — start_receiving_index_refresh, синхронно —
  run_index_refresh) и пересверка открытых строк разбора по новому индексу
  (reconcile_open_rows): карточку завели — строка закрывается сама (resolution auto).

Почему в фоне. Закрытие приёмки — запрос с телефона приёмщика, а обработка может
ждать iiko (пересборка индекса — минуты), бар-ПК (product/info по SSH — до
REMOTE_TIMEOUT на пакет) и Telegram. gunicorn убивает запрос дольше 180 с (урок 21),
поэтому маршрут только закрывает приёмку и зовёт start_receipt_processing: он
атомарно «берёт» обработку (receiving_store.claim_processing — из двух воркеров её
получит один) и запускает поток-демон. Обработка, прерванная перезапуском или
упавшая, не теряется: шедулер раз в 10 минут зовёт retry_stuck_processing
(running дольше PROCESS_STALE_SEC, error старше PROCESS_RETRY_SEC, pending).

Как обрабатывается приёмка (process_receipt; docs/receiving.md, «Как работает»):
1. Позиции = принятые неудалённые сканы по GTIN (receipt_lines). Пусто — done,
   заметка «Пустая приёмка».
2. Индекса нет — пересобрать (ждать чужую пересборку до INDEX_WAIT_SEC); не вышло —
   error «Нет индекса iiko: ...» (шедулер повторит через PROCESS_RETRY_SEC).
3. Статус по индексу (раздел 1): одна актуальная карточка — found, две и больше —
   duplicate, только удалённые/архивные — restore, нет карточек — missing. Есть
   не-found, а индекс старше INDEX_RECHECK_MIN минут — пересобрать и сверить заново:
   бухгалтер мог завести карточку утром, а индекс собран в 07:30. Сбой пересборки —
   предупреждение в заметке, сверка по старому индексу.
4. Для всех не-found — названия ЧЗ (кэш -> chz_stock.json -> product/info на бар-ПК);
   сбой — в заметку, позиции без названия остаются «новыми».
5. missing + название ЧЗ + похожие карточки (similar_cards, счёт совпавших слов >= 2)
   -> similar, иначе new.
6. Строка разбора каждому GTIN (правила открытия/автозакрытия — в upsert_review).
7. Среди строк, открытых этой приёмкой, есть new/similar/restore — сообщение
   бухгалтерии (в фоне).
8. Итог — finish_processing('done', заметка с предупреждениями) или ('error', текст).

Тексты ошибок в process_note и в ответах уходят на страницу, в MCP и Telegram:
только тексты исключений, которые по контракту без секретов (IndexSourceError,
RefreshBusy, ChzError, ReceivingUnavailable), иначе — имя типа исключения
(в тексте исключения requests — URL с токеном iiko).

Модули приёмки вызываются через атрибуты модулей (receiving_index.load_index(),
receiving_chz.lookup(...), receiving_store.xxx, receiving_notify.xxx) — тесты
подменяют их фейками.
"""
import threading
import traceback
from typing import Optional

from core import receiving_chz
from core import receiving_index
from core import receiving_notify
from core import receiving_store
from core.receiving_notify import NOTIFY_STATUSES

# При закрытии с ненайденными GTIN индекс старше 10 минут перечитать из iiko:
# карточку заводят руками в iikoOffice, и «новая» позиция из-за утреннего индекса
# бухгалтеру не нужна. 10 минут — чтобы серия закрытий подряд не пересобирала индекс
# на каждой приёмке (пересборка ~1-2 минуты и слот лицензии iikoAPI).
INDEX_RECHECK_MIN = 10
# Сколько фоновой обработке ждать чужое обновление индекса (кнопка, шедулер, другая
# приёмка). Обычная пересборка — 1-2 минуты; 5 минут с запасом, и это меньше
# PROCESS_STALE_SEC (15 мин), после которого обработку может перехватить другой воркер.
INDEX_WAIT_SEC = 300

# Текст для кнопки «Обновить из iiko» без кредов (тот же, что IndexSourceError индекса).
NO_IIKO_TEXT = 'Не настроено подключение к iiko'
EMPTY_RECEIPT_NOTE = 'Пустая приёмка'
# Разделитель предупреждений в process_note (одна строка на странице и в MCP).
NOTE_SEP = '; '

_LOG = '[RECEIVING]'


# ----------------------------------------------------------------- помощники

def iiko_configured() -> bool:
    """Заданы ли IIKO_LOGIN и IIKO_PASSWORD (config читает .env при импорте)."""
    try:
        import config
    except Exception:  # noqa: BLE001 — без config нет и iiko
        return False
    return bool(getattr(config, 'IIKO_LOGIN', None) and getattr(config, 'IIKO_PASSWORD', None))


def _safe_types() -> tuple:
    """Исключения, чей текст по контракту без токена, хоста и пароля.

    Берутся из атрибутов модулей в момент вызова: тесты подменяют модули фейками.
    """
    found = []
    for module, name in ((receiving_index, 'IndexSourceError'), (receiving_index, 'RefreshBusy'),
                         (receiving_chz, 'ChzError'), (receiving_store, 'ReceivingUnavailable')):
        cls = getattr(module, name, None)
        if isinstance(cls, type) and issubclass(cls, BaseException):
            found.append(cls)
    return tuple(found)


def _error_text(error: BaseException) -> str:
    """Текст сбоя для заметки, страницы и MCP — без секретов (см. докстринг модуля)."""
    safe = _safe_types()
    if safe and isinstance(error, safe):
        text = ' '.join(str(error).split())
        if text:
            return text
    not_found = getattr(receiving_store, 'ReceiptNotFound', None)
    if isinstance(not_found, type) and isinstance(error, not_found):
        return 'Приёмка не найдена'
    return 'Сбой: ' + type(error).__name__


def _log_error(context: str, error: BaseException) -> None:
    """В лог — тип и текст; трассировку — только не для requests (в ней URL с токеном)."""
    print(f'{_LOG} {context}: {_error_text(error)}')
    try:
        import requests
        is_http = isinstance(error, requests.RequestException)
    except Exception:  # noqa: BLE001
        is_http = False
    if not is_http and not isinstance(error, _safe_types()):
        traceback.print_exception(type(error), error, error.__traceback__)


def _spawn(target, name: str, *args) -> threading.Thread:
    """Запустить поток-демон (одно место — тесты подменяют или ждут его)."""
    thread = threading.Thread(target=target, args=args, name=name, daemon=True)
    thread.start()
    return thread


def _age_minutes(index) -> Optional[int]:
    """Возраст индекса в минутах по index_info; нет индекса или даты — None."""
    info = receiving_index.index_info(index) if index else None
    if not info:
        return None
    age = info.get('age_minutes')
    return age if isinstance(age, int) else None


def _is_fresh(index) -> bool:
    """Индекс есть и собран не раньше INDEX_RECHECK_MIN минут назад."""
    age = _age_minutes(index)
    return age is not None and age <= INDEX_RECHECK_MIN


def _chz_name(info) -> tuple:
    """(название, бренд) из данных ЧЗ; название — name, иначе full_name."""
    if not isinstance(info, dict):
        return '', ''
    name = str(info.get('name') or info.get('full_name') or '').strip()
    return name, str(info.get('brand') or '').strip()


def _ids(cards) -> list:
    return [str(c.get('id') or '') for c in (cards or ()) if isinstance(c, dict)]


# ----------------------------------------------------------------- статусы

def _status_for(index: dict, base: dict, chz_info) -> dict:
    """Итоговый статус GTIN по результату classify и данным ЧЗ.

    found/duplicate/restore — как в индексе, candidates пусто. missing: есть
    название ЧЗ и similar_cards нашёл кандидатов (порог счёта — в индексе) ->
    similar с кандидатами, иначе new.
    """
    base_status = base.get('status')
    cards = list(base.get('cards') or [])
    if base_status != 'missing':
        return {'status': base_status, 'cards': cards, 'candidates': []}
    name, brand = _chz_name(chz_info)
    candidates = receiving_index.similar_cards(name, index, brand) if name else []
    if candidates:
        return {'status': 'similar', 'cards': cards, 'candidates': list(candidates)}
    return {'status': 'new', 'cards': cards, 'candidates': []}


def classify_gtins(gtins, index, chz_items) -> dict:
    """{gtin: {'status', 'cards', 'candidates'}} — статусы позиций (раздел 1).

    status: found | duplicate | restore | similar | new. chz_items — {gtin: данные ЧЗ}
    (name/full_name, brand); без названия missing всегда new.
    """
    chz_items = chz_items or {}
    out = {}
    for gtin in gtins:
        base = receiving_index.classify(gtin, index)
        out[gtin] = _status_for(index, base, chz_items.get(gtin))
    return out


# ----------------------------------------------------------------- индекс

def status() -> dict:
    """Состояние для страницы и агента: {'index': index_info|None, 'job': read_state()}."""
    return {'index': receiving_index.index_info(receiving_index.load_index()),
            'job': receiving_index.read_state()}


def reconcile_open_rows(index=None) -> dict:
    """Пересверить открытые строки разбора с индексом. -> {'checked','auto_closed','changed','chz_errors'}.

    Каждой открытой строке — classify; карточка нашлась (found) — строка закрывается
    сама (resolution auto, receiving_store.reclassify_open). missing — статус
    similar/new по названию ЧЗ: у строки без названия оно запрашивается
    (receiving_chz.lookup — кэш, chz_stock.json, product/info), так «новая» позиция
    становится «похожей», когда ЧЗ ответил или в iiko завели похожую карточку.
    checked — сколько строк пересверено; auto_closed — закрыто автоматически;
    changed — у скольких сменились статус, карточки или кандидаты; chz_errors —
    тексты сбоев ЧЗ (без секретов). Индекса нет — ничего не делает (нули).
    """
    summary = {'checked': 0, 'auto_closed': 0, 'changed': 0, 'chz_errors': []}
    if index is None:
        index = receiving_index.load_index()
    if not index:
        print(f'{_LOG} пересверка открытых строк: индекса iiko нет — пропуск')
        return summary
    built_at = str(index.get('built_at') or '')

    rows = []
    for gtin in receiving_store.open_review_gtins():
        try:
            rows.append(receiving_store.get_review_item(gtin))
        except receiving_store.ReviewItemNotFound:
            continue   # строку закрыли или удалили между запросами
    if not rows:
        return summary

    bases = {row['gtin']: receiving_index.classify(row['gtin'], index) for row in rows}
    need_chz = [row['gtin'] for row in rows
                if bases[row['gtin']].get('status') == 'missing' and not _chz_name(row.get('chz'))[0]]
    fetched = {}
    if need_chz:
        try:
            found = receiving_chz.lookup(need_chz) or {}
            fetched = dict(found.get('items') or {})
            summary['chz_errors'] = [str(e) for e in (found.get('errors') or [])]
        except Exception as error:  # noqa: BLE001 — без названий пересверка всё равно полезна
            _log_error('пересверка: названия ЧЗ', error)
            summary['chz_errors'] = ['Названия ЧЗ не получены: ' + _error_text(error)]

    for row in rows:
        gtin = row['gtin']
        chz_info = fetched.get(gtin) or row.get('chz') or {}
        result = _status_for(index, bases[gtin], chz_info)
        try:
            done = receiving_store.reclassify_open(gtin, result['status'], result['cards'],
                                                   result['candidates'], chz=fetched.get(gtin),
                                                   index_built_at=built_at)
        except receiving_store.ReviewItemNotFound:
            continue
        summary['checked'] += 1
        if done.get('auto_closed'):
            summary['auto_closed'] += 1
        if (result['status'] != row.get('status') or _ids(result['cards']) != _ids(row.get('cards'))
                or _ids(result['candidates']) != _ids(row.get('candidates'))):
            summary['changed'] += 1
    print(f'{_LOG} пересверка открытых строк: {summary["checked"]} проверено, '
          f'{summary["auto_closed"]} закрыто автоматически, {summary["changed"]} изменилось')
    return summary


def run_index_refresh(trigger, *, lock=None, wait=0) -> dict:
    """Синхронно: пересобрать индекс из iiko и пересверить открытые строки разбора.

    trigger — кто запустил ('schedule' | 'startup' | 'button' | 'close'); lock — уже
    взятый receiving_index.acquire_run_lock (кнопка) или None (взять здесь, ждать
    wait секунд). Ошибки пересборки (RefreshBusy, IndexSourceError, прочие) —
    пробрасываются, состояние ошибки уже записано индексом. Сбой пересверки индекс
    не отменяет: он — в reconcile_error.
    -> {'index': index_info, 'reconcile': {...} | None, 'reconcile_error': str}.
    """
    info = receiving_index.refresh_index(trigger, lock=lock, wait=wait)
    summary = {'index': info, 'reconcile': None, 'reconcile_error': ''}
    try:
        summary['reconcile'] = reconcile_open_rows(receiving_index.load_index())
    except Exception as error:  # noqa: BLE001 — индекс уже обновлён
        _log_error(f'пересверка после обновления индекса ({trigger})', error)
        summary['reconcile_error'] = _error_text(error)
    return summary


def _refresh_in_background(trigger: str, lock) -> None:
    try:
        run_index_refresh(trigger, lock=lock)
    except Exception as error:  # noqa: BLE001 — ошибка уже в состоянии обновления
        print(f'{_LOG} обновление индекса ({trigger}) не удалось: {_error_text(error)}')


def start_receiving_index_refresh(trigger='button') -> tuple:
    """Кнопка «Обновить из iiko»: запустить пересборку в фоне. -> (dict, http_code).

    202 {'status': 'started'} — лок взят здесь же (второй запрос сразу получит 409),
    пересборка и пересверка идут в потоке-демоне; ход — read_state() / status().
    409 {'status': 'already_running'} — обновляет другой воркер, шедулер или приёмка.
    503 {'status': 'error', 'error': текст} — нет кредов iiko или поток не стартовал.
    """
    if not iiko_configured():
        return {'status': 'error', 'error': NO_IIKO_TEXT}, 503
    try:
        lock = receiving_index.acquire_run_lock(0)
    except receiving_index.RefreshBusy:
        return {'status': 'already_running'}, 409
    except Exception as error:  # noqa: BLE001 — лок-файл недоступен (права, диск)
        _log_error('лок обновления индекса', error)
        return {'status': 'error', 'error': 'Не удалось запустить обновление: ' + _error_text(error)}, 503
    try:
        _spawn(_refresh_in_background, 'receiving-index-' + str(trigger), trigger, lock)
    except Exception as error:  # noqa: BLE001 — поток не стартовал: лок отдать сразу
        lock.release()
        _log_error('поток обновления индекса', error)
        return {'status': 'error', 'error': 'Не удалось запустить обновление: ' + _error_text(error)}, 503
    return {'status': 'started'}, 202


def _refresh_for_close() -> Optional[str]:
    """Пересобрать индекс для обработки приёмки. -> текст сбоя или None.

    Ждёт чужую пересборку до INDEX_WAIT_SEC и, взяв лок, сперва смотрит, не свежий
    ли индекс уже (его только что собрал другой воркер, кнопка или соседняя
    приёмка): тогда пересборки нет. Иначе run_index_refresh('close') с этим локом —
    несколько зависших приёмок, подобранных разом, не пересобирают индекс подряд.
    Без кредов iiko — сразу NO_IIKO_TEXT (лок и состояние обновления не трогаются).
    """
    if not iiko_configured():
        return NO_IIKO_TEXT
    try:
        lock = receiving_index.acquire_run_lock(INDEX_WAIT_SEC)
    except Exception as error:  # noqa: BLE001 — RefreshBusy после ожидания и прочее
        return _error_text(error)
    try:
        fresh = _is_fresh(receiving_index.load_index())
    except Exception:
        lock.release()
        raise
    if fresh:
        lock.release()
        return None
    try:
        run_index_refresh('close', lock=lock)
    except Exception as error:  # noqa: BLE001 — refresh_index отдаёт лок сам
        return _error_text(error)
    return None


# ----------------------------------------------------------------- обработка приёмки

def _lookup_chz(gtins: list, notes: list) -> dict:
    """Названия ЧЗ для GTIN: {gtin: info}; сбои — в notes (без секретов)."""
    if not gtins:
        return {}
    try:
        found = receiving_chz.lookup(gtins) or {}
    except Exception as error:  # noqa: BLE001 — без названий строки всё равно заводятся
        _log_error('названия ЧЗ', error)
        notes.append('Названия ЧЗ не получены: ' + _error_text(error))
        return {}
    for text in found.get('errors') or ():
        notes.append('Честный знак: ' + ' '.join(str(text).split()))
    return dict(found.get('items') or {})


def _finish(rid: int, state: str, notes: list, summary: dict) -> dict:
    note = NOTE_SEP.join(n for n in notes if n)
    summary['state'] = state
    summary['note'] = note
    receiving_store.finish_processing(rid, state, note)
    return summary


def process_receipt(receipt_id) -> dict:
    """Обработать закрытую приёмку синхронно (алгоритм — докстринг модуля).

    Зовётся из потока start_receipt_processing (и тестами напрямую) после
    claim_processing. -> {'receipt_id', 'state': 'done'|'error', 'note', 'gtins',
    'statuses': {status: n}, 'opened': n, 'notified': bool}. Любое исключение ->
    finish_processing('error', текст без секретов); не удалось и это — только лог
    (обработка останется running, шедулер перехватит её через PROCESS_STALE_SEC).
    """
    rid = int(receipt_id)
    notes = []
    summary = {'receipt_id': rid, 'state': '', 'note': '', 'gtins': 0, 'statuses': {},
               'opened': 0, 'notified': False}
    try:
        lines = receiving_store.receipt_lines(rid)
        gtins = []
        for line in lines:
            gtin = str(line.get('gtin') or '')
            if gtin and gtin not in gtins:
                gtins.append(gtin)
        summary['gtins'] = len(gtins)
        if not gtins:
            notes.append(EMPTY_RECEIPT_NOTE)
            return _finish(rid, 'done', notes, summary)

        index = receiving_index.load_index()
        if not index:
            problem = _refresh_for_close()
            index = receiving_index.load_index()
            if not index:
                notes.append('Нет индекса iiko: ' + (problem or 'обновите его кнопкой на странице разбора'))
                return _finish(rid, 'error', notes, summary)

        result = classify_gtins(gtins, index, {})
        if any(r['status'] != 'found' for r in result.values()) and not _is_fresh(index):
            problem = _refresh_for_close()
            if problem:
                notes.append('Индекс iiko не обновлён, сверено по прежнему: ' + problem)
            index = receiving_index.load_index() or index
            result = classify_gtins(gtins, index, {})

        not_found = [g for g in gtins if result[g]['status'] != 'found']
        chz_items = _lookup_chz(not_found, notes)
        if chz_items:
            result.update(classify_gtins(not_found, index, chz_items))

        built_at = str(index.get('built_at') or '')
        opened_rows = []
        for gtin in gtins:
            item = result[gtin]
            summary['statuses'][item['status']] = summary['statuses'].get(item['status'], 0) + 1
            done = receiving_store.upsert_review(gtin, rid, item['status'], item['cards'],
                                                 item['candidates'], chz_items.get(gtin) or {},
                                                 built_at)
            if done.get('opened'):
                opened_rows.append(done['row'])
        summary['opened'] = len(opened_rows)

        if any(row.get('status') in NOTIFY_STATUSES for row in opened_rows):
            try:
                receipt = receiving_store.get_receipt(rid)
                receiving_notify.notify_receipt_in_background(receipt, opened_rows)
                summary['notified'] = True
            except Exception as error:  # noqa: BLE001 — строки уже заведены, сообщение вторично
                _log_error(f'приёмка №{rid}: сообщение бухгалтерии', error)
                notes.append('Сообщение бухгалтерии не отправлено: ' + _error_text(error))

        _finish(rid, 'done', notes, summary)
        print(f'{_LOG} приёмка №{rid} обработана: позиций {summary["gtins"]}, '
              f'статусы {summary["statuses"]}, открыто строк {summary["opened"]}'
              + (f'; {summary["note"]}' if summary['note'] else ''))
        return summary
    except Exception as error:  # noqa: BLE001 — итог обработки обязан записаться
        _log_error(f'приёмка №{rid}: обработка упала', error)
        notes.append(_error_text(error))
        try:
            return _finish(rid, 'error', notes, summary)
        except Exception as finish_error:  # noqa: BLE001
            _log_error(f'приёмка №{rid}: итог обработки не записан', finish_error)
            summary['state'] = 'error'
            summary['note'] = NOTE_SEP.join(notes)
            return summary


def _process_safely(receipt_id: int) -> None:
    try:
        process_receipt(receipt_id)
    except Exception as error:  # noqa: BLE001 — process_receipt ловит сам; страховка потока
        _log_error(f'приёмка №{receipt_id}: поток обработки', error)


def start_receipt_processing(receipt_id, retry_error_now: bool = False) -> bool:
    """Взять обработку приёмки и запустить её в потоке-демоне. -> взяли ли.

    False — обработку уже ведёт другой поток/воркер, она сделана или ошибка свежее
    PROCESS_RETRY_SEC (receiving_store.claim_processing; retry_error_now=True —
    повторное «Завершить» человеком: ошибку перезапустить сразу). ReceivingUnavailable из
    claim — пробрасывается (маршрут: 503). Поток не стартовал — обработка помечается
    error (повтор шедулером) и ответ False.
    """
    rid = int(receipt_id)
    if not receiving_store.claim_processing(rid, retry_error_now=retry_error_now):
        return False
    try:
        _spawn(_process_safely, f'receiving-process-{rid}', rid)
    except Exception as error:  # noqa: BLE001
        _log_error(f'приёмка №{rid}: поток обработки не стартовал', error)
        try:
            receiving_store.finish_processing(rid, 'error', 'Обработка не запустилась: ' + _error_text(error))
        except Exception as finish_error:  # noqa: BLE001
            _log_error(f'приёмка №{rid}: итог не записан', finish_error)
        return False
    return True


def retry_stuck_processing() -> list:
    """Для шедулера: запустить обработку приёмок, которые claim_processing взял бы сейчас.

    -> номера приёмок, обработка которых запущена этим вызовом. Второй воркер,
    пришедший с тем же списком, получит False от claim и ничего не запустит.
    """
    started = []
    for rid in receiving_store.receipts_needing_processing():
        try:
            if start_receipt_processing(rid):
                started.append(rid)
        except Exception as error:  # noqa: BLE001 — одна приёмка не мешает остальным
            _log_error(f'приёмка №{rid}: повтор обработки', error)
    return started
