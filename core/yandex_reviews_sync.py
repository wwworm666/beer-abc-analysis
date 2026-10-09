"""Загрузка отзывов с Яндекс Карт в раздел «Отзывы» — с публичной страницы бара, без входа.

С 2026-10-09 (решение владельца) отзывы читаются с публичной страницы
организации на Картах (core/yandex_maps_reviews.py), а не из кабинета Яндекс
Бизнеса (core/yandex_business.py): кабинету нужна сессия аккаунта Яндекса, она
протухла 28.09, и отзывы 11 дней не обновлялись, а заметили это не сразу.
Публичную страницу видит любой гость: cookies не нужны, протухать нечему.
Кабинет остаётся только на будущее — для ответа на отзыв прямо из сервиса.

Что делает sync_all(kind) для каждого из четырёх баров:
    quick  (раз в 3 часа) — первая страница отзывов (50 новых по порядку Карт).
           Если на Картах отзывов больше, чем будет у нас вместе с этой страницей
           (count > |наши живые id ∪ id страницы|), догружаются остальные страницы.
    full   (раз в сутки)  — все страницы: ловит ответы на старые отзывы, правки и
           пропавшие отзывы.
Загрузка — ReviewStore.upsert_imported (core/guest_reviews.py), правила статусов
там же. Проход считается полным, только если получено ровно count отзывов и
листание не сломалось: тогда отзывы, которых на Картах больше нет, получают
отметку gone_at (из хранилища ничего не удаляется).

Защита от дублей при смене источника: если на первой странице меньше половины
id совпадает с уже сохранёнными (ID_MATCH_MIN_SHARE; проверяется, когда и там,
и там от ID_MATCH_MIN_REVIEWS отзывов), бар не загружается, а получает ошибку:
иначе разные id задвоили бы все отзывы и разослали их в бот как новые.
Новых отзывов за 3 часа единицы, поэтому при правильных id совпадает почти всё.

Бары — по id организации на Картах (тот же permanent_id, что в кабинете;
подтверждено владельцем 2026-09-28), не по названию.

Состояние — yandex_reviews_sync.json рядом с отзывами (постоянный том):
    source          'maps' — файл пишет загрузка с Карт. Файл без него остался от
                    кабинета: при первом запуске из него переносятся только
                    history_cutoff, notify_since, last_success_at и synced_at баров
    source_since    'YYYY-MM-DDTHH:MM' — первая проверка Карт
    status          'ok' | 'partial' (часть баров с ошибкой) | 'captcha' |
                    'error' (ни один бар не прочитан) | 'running'
    kind            'quick' | 'full' — какой была последняя проверка
    started_at, finished_at
    last_attempt_at       начало последней проверки
    last_success_at       конец последней проверки, где прочитаны все бары
    last_full_attempt_at  начало последнего полного прохода
    last_full_at          конец последнего полного прохода со статусом ok
    history_cutoff  'YYYY-MM-DD' — граница истории (ставится один раз, см. ниже)
    notify_since    с какого момента новые отзывы шлются в бот (core/review_notify.py)
    error           текст для экрана или null
    bars            {bar: {org_id, count (сколько отзывов на Картах), count_source,
                     received (сколько получено), ours (живых отзывов бара у нас
                     после загрузки), pages, stats, error, synced_at (последнее
                     удачное чтение), full_at (последний полный проход бара),
                     behind_since (с какого момента на Картах больше, чем у нас)}}
    watchdog        что уже сообщено в Telegram (core/yandex_reviews_watchdog.py)
    notify          сводка последней рассылки новых отзывов
Экран получает сводку public_state в yandex_sync ответа GET /api/reviews.

Граница истории: отзывы без ответа старше «первая загрузка − 30 дней» ложатся в
«Без ответа по решению» с причиной «до подключения сервиса» (решение владельца
2026-09-28). Ставится один раз (у нас — 2026-08-29) и дальше не меняется.

Одна проверка за раз на все процессы: межпроцессный замок без ожидания
(второй вызов получает {'skipped': 'already_running'}). Документация:
docs/yandex-reviews.md.
"""
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Callable, Optional

import portalocker

from core import msk_time
from core import yandex_maps_reviews as maps_reviews
from core.guest_reviews import BAR_KEYS, BARS, get_review_store
from core.json_store import atomic_write_json
from core.storage_paths import get_data_path

SOURCE = 'yandex'                  # source отзыва в хранилище
STATE_SOURCE = 'maps'              # source файла состояния: загрузка с Карт
SYNC_BY = 'Яндекс Карты'           # подпись загрузки в отзывах (added_by, reply.by)
QUICK, FULL = 'quick', 'full'
KINDS = (QUICK, FULL)

# Организация на Картах -> наш бар. Подтверждено владельцем 2026-09-28.
BAR_BY_PERMANENT_ID = {
    31434555884: 'kremenchugskaya',    # «Культура», Кременчугская ул., 11 к1
    48832698165: 'bolshoy',            # «Культура», Большой пр. В.О., 18
    149836365055: 'varshavskaya',      # «Культура», Варшавская ул., 6 к1
    161689116864: 'ligovskiy',         # «Каск», Лиговский пр., 271
}
BAR_NAMES = {b['key']: b['name'] for b in BARS}

# Граница истории: «первая загрузка − 30 дней» (решение владельца 2026-09-28).
HISTORY_WINDOW_DAYS = 30
# Защита от дублей (см. докстринг): проверка совпадения id включается, когда и
# на странице, и у нас от 10 отзывов; бар не загружается, если совпало меньше половины.
ID_MATCH_MIN_REVIEWS = 10
ID_MATCH_MIN_SHARE = 0.5

STATE_FILE_NAME = 'yandex_reviews_sync.json'
STAMP = '%Y-%m-%dT%H:%M'
# Что переносится из файла, оставшегося от кабинета (см. докстринг, source).
_CARRY_FROM_CABINET = ('history_cutoff', 'notify_since', 'last_success_at')

assert set(BAR_BY_PERMANENT_ID.values()) <= set(BAR_KEYS), 'бар вне venues_config'


def state_path() -> str:
    return get_data_path(STATE_FILE_NAME)


def load_state(path: Optional[str] = None) -> dict:
    """Состояние загрузки; файла нет или он битый -> {} (его пишет сама загрузка)."""
    try:
        with open(path or state_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def enabled() -> bool:
    """YANDEX_REVIEWS_SYNC_ENABLED=0 выключает загрузку (и сторож молчит)."""
    return os.environ.get('YANDEX_REVIEWS_SYNC_ENABLED', '1').strip() != '0'


def _naive(dt: datetime) -> datetime:
    return dt.astimezone(msk_time.MOSCOW_TZ).replace(tzinfo=None) if dt.tzinfo else dt


def public_state(path: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """Сводка для экрана: статус, время, по барам — сколько на Картах и у нас, тревоги сторожа."""
    from core import yandex_reviews_watchdog as watchdog
    from core.yandex_reviews_scheduler import CHECK_EVERY_HOURS, FULL_HOUR, FULL_MINUTE
    s = load_state(path)
    now = _naive(now or msk_time.now())
    schedule = {'quick_every_hours': CHECK_EVERY_HOURS, 'full_at': f'{FULL_HOUR:02d}:{FULL_MINUTE:02d}'}
    maps = s.get('source') == STATE_SOURCE
    bars = {}
    for bar, b in ((s.get('bars') or {}).items() if maps else ()):
        if isinstance(b, dict):
            bars[bar] = {k: b.get(k) for k in ('count', 'received', 'ours', 'error', 'synced_at',
                                               'full_at', 'behind_since')}
    status = (s.get('status') or 'never') if maps else 'never'
    if not enabled():
        status = 'disabled'
    return {'status': status, 'kind': s.get('kind') if maps else None,
            'started_at': s.get('started_at') if maps else None,
            'finished_at': s.get('finished_at') if maps else None,
            'last_success_at': s.get('last_success_at'), 'last_full_at': s.get('last_full_at'),
            'error': s.get('error') if maps else None, 'history_cutoff': s.get('history_cutoff'),
            'bars': bars, 'schedule': schedule,
            'alerts': watchdog.evaluate(s, now) if maps and enabled() else {'stale': [], 'behind': []}}


def _now_str(now: datetime) -> str:
    return now.strftime(STAMP)


@contextmanager
def state_lock(path: Optional[str] = None):
    """Замок файла состояния без ожидания: True — взят, False — проверка уже идёт.

    Держат его загрузка (sync_all) и сторож (core/yandex_reviews_watchdog.check),
    чтобы их записи состояния не затирали друг друга.
    """
    lock_path = (path or state_path()) + '.lock'
    os.makedirs(os.path.dirname(lock_path) or '.', exist_ok=True)
    lock = portalocker.Lock(lock_path, mode='a', timeout=0, fail_when_locked=True)
    try:
        lock.acquire()
    except portalocker.exceptions.LockException:
        yield False
        return
    try:
        yield True
    finally:
        lock.release()


def _bar_ids(store, bar):
    """(все id отзывов бара с Карт у нас, id без отметки «нет в Яндексе»)."""
    every, live = set(), set()
    for r in store.all():
        if r.get('source') == SOURCE and r.get('origin') == 'import' and r.get('bar') == bar \
                and r.get('external_id'):
            every.add(r['external_id'])
            if not r.get('gone_at'):
                live.add(r['external_id'])
    return every, live


def id_mismatch(page_ids: set, stored_ids: set) -> Optional[str]:
    """Текст ошибки, если id со страницы почти не совпадают с сохранёнными (см. докстринг), иначе None."""
    if len(page_ids) < ID_MATCH_MIN_REVIEWS or len(stored_ids) < ID_MATCH_MIN_REVIEWS:
        return None
    known = len(page_ids & stored_ids)
    if known >= len(page_ids) * ID_MATCH_MIN_SHARE:
        return None
    return (f'На Картах из {len(page_ids)} отзывов первой страницы у нас известны только {known}: '
            f'id не совпадают с сохранёнными. Загрузка остановлена, чтобы не задвоить отзывы')


def sync_all(kind: str = FULL, *, store=None, fetch: Optional[Callable] = None,
             sleep: Callable[[float], None] = time.sleep,
             clock: Callable[[], datetime] = msk_time.now, path: Optional[str] = None,
             notifier: Optional[Callable] = None) -> dict:
    """Одна проверка всех баров (kind 'quick' или 'full'). Возвращает записанное состояние.

    fetch(org_id, page) -> разобранная страница (по умолчанию
    core.yandex_maps_reviews.fetch_page); store — хранилище отзывов (по умолчанию
    общий ReviewStore); sleep — паузы между запросами. Не бросает исключений:
    всё уходит в state.status / state.error и в ошибки баров.

    notifier(store, state, now_str) -> сводка — рассылка новых отзывов после
    загрузки (core/review_notify.notify_new_reviews). По умолчанию None — НЕ шлётся
    ничего: настоящий отправитель передаёт только планировщик, чтобы тесты и
    ручной вызов не писали в Telegram. Вызывается, если загружен хоть один бар;
    его сбой статус не меняет, а пишется в state.notify.error.
    """
    if kind not in KINDS:
        raise ValueError(f'kind: {kind!r}')
    path = path or state_path()
    with state_lock(path) as locked:
        if not locked:
            print('[YANDEX-REVIEWS] проверка уже идёт в другом процессе — пропуск')
            return {'skipped': 'already_running'}
        return _sync_locked(kind, store, fetch, sleep, clock, path, notifier)


def _sync_locked(kind, store, fetch, sleep, clock, path, notifier) -> dict:
    def clock_now():
        return _naive(clock())

    now = clock_now()
    now_s = _now_str(now)
    state = load_state(path)
    if state.get('source') != STATE_SOURCE:
        old_bars = state.get('bars') if isinstance(state.get('bars'), dict) else {}
        state = {k: state[k] for k in _CARRY_FROM_CABINET if state.get(k)}
        state.update(source=STATE_SOURCE, source_since=now_s,
                     bars={bar: {'synced_at': b.get('synced_at')} for bar, b in old_bars.items()
                           if bar in BAR_KEYS and isinstance(b, dict) and b.get('synced_at')})
    state.update(status='running', kind=kind, started_at=now_s, finished_at=None, error=None,
                 last_attempt_at=now_s)
    if kind == FULL:
        state['last_full_attempt_at'] = now_s
    if not state.get('history_cutoff'):
        state['history_cutoff'] = (now.date() - timedelta(days=HISTORY_WINDOW_DAYS)).isoformat()
    atomic_write_json(path, state)

    store = store or get_review_store()
    fetch = fetch or maps_reviews.fetch_page
    bars_state = state.setdefault('bars', {})
    failed, loaded, captcha = [], 0, None
    for index, (org_id, bar) in enumerate(BAR_BY_PERMANENT_ID.items()):
        if index:
            sleep(maps_reviews.PAUSE_SEC)
        prev = bars_state.get(bar) if isinstance(bars_state.get(bar), dict) else {}
        b = {'org_id': org_id, 'count': prev.get('count'), 'count_source': prev.get('count_source'),
             'received': None, 'ours': prev.get('ours'), 'pages': 0, 'stats': None, 'error': None,
             'synced_at': prev.get('synced_at'), 'full_at': prev.get('full_at'),
             'behind_since': prev.get('behind_since')}
        bars_state[bar] = b
        try:
            b['error'] = _sync_bar(kind, org_id, bar, b, store, fetch, sleep, state['history_cutoff'],
                                   lambda: _now_str(clock_now()))
            loaded += 1
        except maps_reviews.MapsCaptchaError as e:
            b['error'] = str(e)
            captcha = str(e)
            if b['received'] is not None:
                loaded += 1
            failed.append(bar)
            break     # капча — на все запросы с этого адреса: остальные бары не дёргаем
        except Exception as e:  # noqa: BLE001 — сбой одного бара не оставляет проверку «идущей»
            b['error'] = str(e) or type(e).__name__
        if b['error']:
            failed.append(bar)

    if notifier is not None and loaded:
        try:
            state['notify'] = notifier(store, state, _now_str(clock_now()))
        except Exception as e:  # noqa: BLE001 — рассылка не должна ломать итог проверки
            state['notify'] = {'error': repr(e)}
            print(f'[YANDEX-REVIEWS] рассылка новых отзывов: {state["notify"]["error"]}')

    if captcha:
        status, error = 'captcha', captcha
    elif failed and len(failed) == len(BAR_BY_PERMANENT_ID):
        status, error = 'error', _failed_text(failed, bars_state)
    elif failed:
        status, error = 'partial', _failed_text(failed, bars_state)
    else:
        status, error = 'ok', None
    state['status'] = status
    state['error'] = error
    state['finished_at'] = _now_str(clock_now())
    if status == 'ok':
        state['last_success_at'] = state['finished_at']
        if kind == FULL:
            state['last_full_at'] = state['finished_at']
    atomic_write_json(path, state)
    print(f'[YANDEX-REVIEWS] проверка Карт ({kind}): {status}' + (f' — {error}' if error else ''))
    return state


def _failed_text(failed, bars_state) -> str:
    return 'Не прочитаны: ' + '; '.join(
        f'{BAR_NAMES.get(bar, bar)} — {(bars_state.get(bar) or {}).get("error") or "ошибка"}' for bar in failed)


def _sync_bar(kind, org_id, bar, b, store, fetch, sleep, history_cutoff, now_str) -> Optional[str]:
    """Прочитать и загрузить один бар; b — его состояние (меняется на месте).

    -> текст ошибки бара (листание не дошло до конца) или None. Капча после
    загрузки полученного — MapsCaptchaError; иные сбои — исключения
    (MapsReviewsError, ReviewStoreUnavailable, ...): бар не загружен.
    """
    first = fetch(org_id, 1)
    every, live = _bar_ids(store, bar)
    page_ids = {str(r.get('reviewId')).strip() for r in first['reviews']}
    problem = id_mismatch(page_ids, every)
    if problem:
        raise maps_reviews.MapsReviewsError(problem)
    count = first.get('count')
    walk = {'reviews': first['reviews'], 'pages': 1, 'error': None, 'captcha': False}
    if kind == FULL or (count is not None and count > len(live | page_ids)):
        walk = maps_reviews.collect_pages(org_id, first, fetch=fetch, sleep=sleep)
    items = [maps_reviews.parse_review(raw) for raw in walk['reviews']]
    received = len({i['external_id'] for i in items if i['external_id']})
    complete = walk['error'] is None and count is not None and received == count
    b['stats'] = store.upsert_imported(SOURCE, bar, items, history_cutoff=history_cutoff,
                                       complete=complete, by=SYNC_BY)
    stamp = now_str()
    b.update(count=count, count_source=first.get('count_source'), received=received,
             pages=walk['pages'], synced_at=stamp)
    if complete:
        b['full_at'] = stamp
    b['ours'] = len(_bar_ids(store, bar)[1])
    behind = count is not None and count > b['ours']
    b['behind_since'] = (b.get('behind_since') or stamp) if behind else None
    if walk['captcha']:
        raise maps_reviews.MapsCaptchaError(walk['error'])
    return walk['error']
