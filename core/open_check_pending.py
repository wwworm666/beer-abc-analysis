"""Очередь недоставленных отчётов open-check бота.

Зачем: 2026-08-16 в 14:59 тревога «ЗАКРЫТ — ВО» дошла только до 2 из 4
получателей — блокировка ТСПУ «мигала»: тот же запасной IP, что дважды дал
таймаут, через несколько секунд заработал. Отправка была «одна попытка на
чат» — недоставленное терялось молча (см. docs/lessons.md).

Механика:
- send_report (core/open_check_bot.py) складывает сюда чаты, до которых
  сообщение не дошло даже после повторных проходов;
- resend-поток планировщика (core/open_check_scheduler.py) каждые
  RESEND_INTERVAL_SEC зовёт resend_due(): досылает остаток с честной пометкой
  о задержке, пока не доставит всем или не кончится день;
- очередь живёт ТОЛЬКО день отправки: пометка «Проверка 14:59 МСК» в тексте
  завтра станет враньём, поэтому в новый день остаток удаляется с ERROR-логом
  (не молча).

Файл: data/open_check_pending.json (get_data_path — на проде /kultura,
переживает рестарт контейнера). Структура:

    {"date": "2026-08-16",
     "items": [{"text": "<исходный текст отчёта>",
                "chats": ["670033096", ...],   # кому ещё НЕ доставлено
                "target": "alarm",             # positive | alarm (для логов)
                "first_try": "14:59"}]}        # МСК-время исходной отправки

Все отчёты шлются с html=True (как в send_report), поэтому флаг не храним.

Конкуренция: gunicorn --workers 2 → оба воркера крутят resend-поток. Лок НЕ
держится на время сетевых отправок (при лежащем Telegram один провальный
send_message стоит 15-60с таймаутов — лок висел бы минутами, и add() со свежей
тревогой 14:59 не дождался бы его; это нашло адверсариальное ревью 2026-08-16).
Вместо этого клейм: под коротким локом в файл пишется claimed_at, лок
отпускается, отправка идёт без лока, результат сливается обратно под локом.
Чужой свежий клейм (моложе _CLAIM_TTL_SEC) → busy, тик пропускается. Устаревший
клейм (процесс умер во время отправки) переигрывается — возможен дубль
доставленного перед смертью, это принято: дубль тревоги лучше потери.
"""
import hashlib
import json
import logging
import os
import time

import portalocker

from core.json_store import atomic_write_json
from core.storage_paths import get_data_path

log = logging.getLogger("open-check")

_FILE = 'open_check_pending.json'

# Все локи теперь держатся миллисекунды (чтение/запись маленького JSON), но
# семантика таймаутов разная:
# add() обязан дождаться лока: если бросить — недоставленная тревога потеряется.
_LOCK_TIMEOUT_ADD = 10
# resend_due(): лок занят дольше секунды = что-то не так, пропускаем тик —
# следующая попытка через RESEND_INTERVAL_SEC.
_LOCK_TIMEOUT_RESEND = 1
# Слияние результата отправки обратно в файл: остатки терять нельзя — ждём.
_LOCK_TIMEOUT_MERGE = 10

# Клейм моложе этого — «кто-то сейчас досылает», тик пропускается. Старше —
# считаем, что клеймивший процесс умер, и переигрываем. Значение больше
# худшего цикла отправки: ~4-6 чатов x ~45с таймаутов (primary + 2 запасных IP
# + DoH при лежащем Telegram) ~= 5 минут.
_CLAIM_TTL_SEC = 600

# Процессная память успешных досылок: {(date, sha1(text), chat_id)}. Страхует
# от дублей, когда файл очереди не удалось переписать после отправки (диск
# полон): следующий тик этого же процесса не пошлёт чату то же сообщение
# повторно. Второй воркер этой памяти не видит — от него возможен один дубль,
# принято (дубль лучше потери).
_delivered_cache = set()


def _cache_key(date_str: str, text: str, chat_id) -> tuple:
    return (date_str, hashlib.sha1(text.encode('utf-8')).hexdigest(), str(chat_id))


def _path() -> str:
    # Не кэшируем: get_data_path зависит от окружения (тесты подменяют).
    return get_data_path(_FILE)


def _load() -> dict:
    """Содержимое очереди или {} (нет файла / бит). Битый файл — ERROR-лог,
    но не исключение: очередь вспомогательная, ронять resend-поток нельзя."""
    try:
        with open(_path(), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        log.error("open_check_pending.json не читается (%s) — очередь считаю пустой", e)
        return {}


def _remove() -> None:
    try:
        os.remove(_path())
    except FileNotFoundError:
        pass
    except OSError:
        log.exception("не удалось удалить open_check_pending.json")


def _delayed_text(item: dict) -> str:
    """Исходный отчёт + честная пометка, почему он пришёл не в 14:59.
    Пометка без HTML-спецсимволов — безопасна при parse_mode=HTML."""
    first_try = item.get('first_try') or '?'
    return (item.get('text', '') +
            f"\n\nДоставлено с задержкой: отправка в {first_try} МСК не прошла "
            f"(Telegram был недоступен)")


def add(date_str: str, text: str, chats: list, target: str, first_try: str) -> None:
    """Поставить недоставленное сообщение в очередь досылки.

    date_str: день отправки МСК ('YYYY-MM-DD') — очередь живёт только этот день.
    chats: chat_id, до которых НЕ дошло. Пустой список — no-op.
    """
    chats = [str(c) for c in chats if str(c).strip()]
    if not chats:
        return
    p = _path()
    try:
        with portalocker.Lock(p + '.lock', mode='a', timeout=_LOCK_TIMEOUT_ADD):
            d = _load()
            if d.get('date') != date_str:
                # Остаток другого дня (если был) устарел — дропаем с логом.
                if d.get('items'):
                    log.error("open_check_pending: остаток за %s вытеснен новым днём %s "
                              "(%d сообщений так и не доставлено)",
                              d.get('date'), date_str, len(d['items']))
                d = {'date': date_str, 'items': []}
            d.setdefault('items', []).append({
                'text': text,
                'chats': chats,
                'target': target,
                'first_try': first_try,
            })
            atomic_write_json(p, d)
        log.warning("open_check_pending: в очередь досылки добавлено %d чатов (%s): %s",
                    len(chats), target, chats)
    except portalocker.exceptions.BaseLockException:
        # Лок не отпустили за 10с — ненормально (все держатели лока укладываются
        # в миллисекунды). Логируем текст целиком, чтобы тревогу можно было
        # восстановить руками из логов.
        log.error("open_check_pending: не взял лок за %ds — НЕ сохранено: chats=%s text=%r",
                  _LOCK_TIMEOUT_ADD, chats, text)
    except Exception:
        # add() — best-effort по контракту: ошибка записи (диск полон, ФС
        # read-only) не должна вылетать в send_report и превращать частично
        # доставленный отчёт в ложную тревогу «проверка упала». Текст в лог —
        # для ручного восстановления.
        log.exception("open_check_pending: очередь не записана (ошибка диска?) — "
                      "НЕ сохранено: chats=%s text=%r", chats, text)


def resend_due(today_str: str, send_fn=None) -> dict:
    """Дослать всё из очереди. Зовётся resend-потоком планировщика.

    Три фазы, лок НЕ держится на время сетевых вызовов (см. докстринг модуля):
    1. клейм: под коротким локом прочитать items и записать claimed_at
       (чужой свежий клейм → busy);
    2. отправка без лока (может занять минуты при лежащем Telegram —
       add() со свежим отчётом в это время свободно пишет в файл);
    3. слияние: под локом убрать доставленное, оставить остаток + всё,
       что add() дописал за время отправки, снять клейм.

    today_str: сегодняшняя дата МСК ('YYYY-MM-DD'). Очередь другого дня
    удаляется с ERROR-логом (сообщение с «Проверка 14:59 МСК» на следующий
    день только запутает).
    send_fn: DI для тестов; сигнатура send_message(chat_id, text, html=...).

    Возвращает сводку {'status': ...} для логов и тестов:
    empty | stale | busy | ok (+delivered, +remaining).
    """
    global _delivered_cache
    p = _path()
    if not os.path.exists(p):
        return {'status': 'empty'}
    if send_fn is None:
        from core.open_check_telegram import send_message as send_fn

    # Память доставок хранит только сегодняшний день.
    _delivered_cache = {k for k in _delivered_cache if k[0] == today_str}

    # --- Фаза 1: клейм под коротким локом -----------------------------------
    try:
        with portalocker.Lock(p + '.lock', mode='a', timeout=_LOCK_TIMEOUT_RESEND):
            d = _load()
            items = d.get('items') or []
            if not items:
                _remove()
                return {'status': 'empty'}
            if d.get('date') != today_str:
                log.error("open_check_pending: очередь за %s устарела (сегодня %s) — "
                          "удаляю %d недоставленных сообщений: %s",
                          d.get('date'), today_str, len(items),
                          [(i.get('target'), i.get('chats')) for i in items])
                _remove()
                return {'status': 'stale', 'dropped': len(items)}
            claimed_at = d.get('claimed_at')
            now_ts = time.time()
            if claimed_at and (now_ts - float(claimed_at)) < _CLAIM_TTL_SEC:
                return {'status': 'busy'}  # другой воркер досылает прямо сейчас
            if claimed_at:
                log.warning("open_check_pending: клейм устарел (%.0fs назад; процесс "
                            "умер во время досылки?) — переигрываю, возможен дубль",
                            now_ts - float(claimed_at))
            atomic_write_json(p, {**d, 'claimed_at': now_ts})
    except portalocker.exceptions.BaseLockException:
        return {'status': 'busy'}

    # --- Фаза 2: отправка без лока -------------------------------------------
    delivered = 0
    still = []
    for item in items:
        text = _delayed_text(item)
        remaining = []
        for chat_id in item.get('chats', []):
            key = _cache_key(today_str, item.get('text', ''), chat_id)
            if key in _delivered_cache:
                # Уже доставляли, но файл тогда не переписался (ошибка диска) —
                # не дублируем.
                log.warning("open_check_pending: chat_id=%s уже получал это сообщение "
                            "(память процесса) — пропуск", chat_id)
                continue
            if send_fn(chat_id, text, html=True):
                delivered += 1
                _delivered_cache.add(key)
                log.info("open_check_pending: доставлено с задержкой chat_id=%s (%s)",
                         chat_id, item.get('target'))
            else:
                remaining.append(chat_id)
        if remaining:
            still.append({**item, 'chats': remaining})

    # --- Фаза 3: слияние под локом --------------------------------------------
    remaining_total = sum(len(i['chats']) for i in still)
    try:
        with portalocker.Lock(p + '.lock', mode='a', timeout=_LOCK_TIMEOUT_MERGE):
            d2 = _load()
            if d2.get('date') == today_str:
                # add() мог дописать новые items за время отправки — они в хвосте
                # (add только аппендит, другие resend отсечены нашим клеймом).
                tail = (d2.get('items') or [])[len(items):]
            elif not d2.get('items'):
                # Файл исчез или бит — восстанавливаем свой остаток.
                tail = []
            else:
                # Файл занят другим (новым) днём: наши остатки устарели, чужие
                # items трогать нельзя.
                if still:
                    log.error("open_check_pending: за время досылки наступил новый день "
                              "(%s) — %d недоставленных за %s удалены: %s",
                              d2.get('date'), remaining_total, today_str,
                              [(i.get('target'), i.get('chats')) for i in still])
                return {'status': 'ok', 'delivered': delivered, 'remaining': 0}
            merged = still + tail
            if merged:
                atomic_write_json(p, {'date': today_str, 'items': merged})
            else:
                _remove()
    except portalocker.exceptions.BaseLockException:
        log.error("open_check_pending: слияние после досылки не взяло лок — файл не "
                  "обновлён, возможен дубль на следующем тике (память процесса защитит)")
    except Exception:
        # Диск полон и т.п.: доставленное уже в _delivered_cache — этот процесс
        # дубль не пошлёт; клейм в файле устареет через _CLAIM_TTL_SEC.
        log.exception("open_check_pending: файл очереди не переписан после досылки "
                      "(доставлено %d: см. лог выше)", delivered)

    if remaining_total:
        log.warning("open_check_pending: досылка — доставлено %d, ещё в очереди %d",
                    delivered, remaining_total)
    return {'status': 'ok', 'delivered': delivered, 'remaining': remaining_total}
