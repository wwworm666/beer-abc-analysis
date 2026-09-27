"""Сверка отзывов Яндекс Бизнеса с разделом «Отзывы» (этап 1, раз в сутки).

Что делает sync_all: читает кабинет (core/yandex_business.py — только GET,
отвечать на отзывы и удалять что-либо клиент не умеет), для каждого из
четырёх баров проходит ВСЕ страницы отзывов и загружает их в хранилище
отзывов (core/guest_reviews.ReviewStore.upsert_imported). Правила статусов —
там. Решения владельца 2026-09-28 (docs/yandex-reviews.md):
    - загрузка раз в сутки (планировщик core/yandex_reviews_scheduler.py),
      каждый раз полный проход: он же ловит ответы на старые отзывы;
    - отзывы без ответа старше «дата первой сверки − 30 дней» ложатся в
      «Без ответа по решению» с причиной «до подключения сервиса»;
    - ответ, данный в Яндексе, делает отзыв «Отвеченным» с временем из Яндекса;
    - ручного ввода отзывов нет; аккаунт — владельца.

Бары — по permanent_id организации в Яндексе, не по названию (подтверждено
владельцем 2026-09-28 по выводу scripts/yandex_reviews_probe.py). Организации
аккаунта, которых нет в BAR_BY_PERMANENT_ID (Draftmasters, First), не читаются.

Состояние — yandex_reviews_sync.json рядом с отзывами (постоянный том):
    status        'ok' | 'partial' (часть баров с ошибкой) | 'expired' (сессия
                  не принята — нужны новые cookies) | 'captcha' | 'error' |
                  'not_configured' (cookies не заданы) | 'running'
    started_at, finished_at, last_success_at   'YYYY-MM-DDTHH:MM' по Москве
    history_cutoff  'YYYY-MM-DD' — граница истории, ставится при первой сверке
                    и дальше не меняется
    error         текст ошибки для экрана (без cookies) или null
    bars          {bar: {permanent_id, name, total, received, stats, error, synced_at}}
Экран показывает его сводкой (public_state); cookies в состояние не попадают.

Одна сверка за раз на все процессы: межпроцессный замок без ожидания
(второй вызов получает {'skipped': 'already_running'}).
"""
import json
import os
from datetime import datetime, timedelta
from typing import Callable, Optional

import portalocker

from core import msk_time
from core.guest_reviews import BAR_KEYS, get_review_store
from core.json_store import atomic_write_json
from core.storage_paths import get_data_path
from core.yandex_business import (MAX_REVIEW_PAGES, YandexAuthError, YandexBusinessClient,
                                  YandexBusinessError, YandexCaptchaError, parse_review)

ENV_SESSION_ID = 'YANDEX_BUSINESS_SESSION_ID'
ENV_SESSION_ID2 = 'YANDEX_BUSINESS_SESSION_ID2'

SOURCE = 'yandex'
SYNC_BY = 'Яндекс Бизнес'          # подпись загрузки в отзывах (added_by, reply.by)

# Организация в Яндексе -> наш бар. Подтверждено владельцем 2026-09-28.
BAR_BY_PERMANENT_ID = {
    31434555884: 'kremenchugskaya',    # «Культура», Кременчугская ул., 11 к1
    48832698165: 'bolshoy',            # «Культура», Большой пр. В.О., 18
    149836365055: 'varshavskaya',      # «Культура», Варшавская ул., 6 к1
    161689116864: 'ligovskiy',         # «Каск», Лиговский пр., 271
}
# Организации аккаунта, которые не бары: не читаются (владелец 2026-09-28).
NOT_BARS = {145889739395: 'Draftmasters', 244677756127: 'First'}

# Граница истории: отзывы без ответа старше «первая сверка − 30 дней» — в
# «Без ответа по решению». 30 дней: свежие отзывы, на которые ещё уместно
# ответить, остаются в работе (решение владельца 2026-09-28).
HISTORY_WINDOW_DAYS = 30

STATE_FILE_NAME = 'yandex_reviews_sync.json'

assert set(BAR_BY_PERMANENT_ID.values()) <= set(BAR_KEYS), 'бар вне venues_config'


def state_path() -> str:
    return get_data_path(STATE_FILE_NAME)


def load_state(path: Optional[str] = None) -> dict:
    """Состояние сверки; файла нет или он битый -> {} (состояние не критично: его пишет сверка)."""
    try:
        with open(path or state_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def public_state(path: Optional[str] = None) -> dict:
    """Сводка для экрана: статус, время, ошибка, по барам — сколько получено и счётчик Яндекса."""
    s = load_state(path)
    configured = bool(os.environ.get(ENV_SESSION_ID, '').strip() and os.environ.get(ENV_SESSION_ID2, '').strip())
    bars = {}
    for bar, b in (s.get('bars') or {}).items():
        if isinstance(b, dict):
            bars[bar] = {'total': b.get('total'), 'received': b.get('received'),
                         'error': b.get('error'), 'synced_at': b.get('synced_at')}
    status = s.get('status') or ('never' if configured else 'not_configured')
    if not configured:
        status = 'not_configured'
    return {'status': status, 'started_at': s.get('started_at'), 'finished_at': s.get('finished_at'),
            'last_success_at': s.get('last_success_at'), 'error': s.get('error'),
            'history_cutoff': s.get('history_cutoff'), 'bars': bars, 'schedule': 'daily'}


def _now_str(now: datetime) -> str:
    return now.strftime('%Y-%m-%dT%H:%M')


def _scrub(text, secrets) -> str:
    s = str(text)
    for v in secrets:
        if v:
            s = s.replace(v, '***')
    return s


def sync_all(*, store=None, client_factory: Optional[Callable] = None,
             clock: Callable[[], datetime] = msk_time.now, path: Optional[str] = None) -> dict:
    """Одна полная сверка всех баров. Возвращает записанное состояние.

    client_factory(session_id, session_id2) -> клиент с branches() и
    iter_review_pages() (по умолчанию YandexBusinessClient); store — хранилище
    отзывов (по умолчанию общий ReviewStore). Не бросает исключений: всё
    уходит в state.status / state.error.
    """
    path = path or state_path()
    lock_path = path + '.lock'
    os.makedirs(os.path.dirname(lock_path) or '.', exist_ok=True)
    try:
        lock = portalocker.Lock(lock_path, mode='a', timeout=0, fail_when_locked=True)
        lock.acquire()
    except portalocker.exceptions.LockException:
        print('[YANDEX-REVIEWS] сверка уже идёт в другом процессе — пропуск')
        return {'skipped': 'already_running'}
    try:
        return _sync_locked(store, client_factory, clock, path)
    finally:
        lock.release()


def _sync_locked(store, client_factory, clock, path) -> dict:
    def clock_now():
        n = clock()
        return n.astimezone(msk_time.MOSCOW_TZ).replace(tzinfo=None) if n.tzinfo else n

    now = clock_now()
    state = load_state(path)
    state.update({'status': 'running', 'started_at': _now_str(now), 'finished_at': None, 'error': None})
    sid = os.environ.get(ENV_SESSION_ID, '').strip()
    sid2 = os.environ.get(ENV_SESSION_ID2, '').strip()
    secrets = (sid, sid2)

    def finish(status, error=None):
        state['status'] = status
        state['error'] = _scrub(error, secrets) if error else None
        state['finished_at'] = _now_str(clock_now())
        if status == 'ok':
            state['last_success_at'] = state['finished_at']
        atomic_write_json(path, state)
        print(f'[YANDEX-REVIEWS] сверка: {status}' + (f' — {state["error"]}' if state['error'] else ''))
        return state

    if not sid or not sid2:
        return finish('not_configured', 'Не заданы cookies Яндекса (YANDEX_BUSINESS_SESSION_ID и _ID2)')
    if not state.get('history_cutoff'):
        state['history_cutoff'] = (now.date() - timedelta(days=HISTORY_WINDOW_DAYS)).isoformat()
    atomic_write_json(path, state)

    store = store or get_review_store()
    factory = client_factory or YandexBusinessClient
    bars_state = state.setdefault('bars', {})
    failed = []
    try:
        client = factory(sid, sid2)
    except YandexAuthError as e:
        return finish('expired', str(e))
    try:
        try:
            found = {b['permanent_id']: b for b in client.branches()}
        except YandexAuthError as e:
            return finish('expired', str(e))
        except YandexCaptchaError as e:
            return finish('captcha', str(e))
        except Exception as e:  # noqa: BLE001 — любой сбой: без списка организаций сверки нет
            return finish('error', f'Список организаций не получен: {e}')

        for pid, bar in BAR_BY_PERMANENT_ID.items():
            b_state = {'permanent_id': pid, 'name': (found.get(pid) or {}).get('name'),
                       'total': None, 'received': 0, 'stats': None, 'error': None,
                       'synced_at': bars_state.get(bar, {}).get('synced_at')}
            bars_state[bar] = b_state
            if pid not in found:
                b_state['error'] = 'Организации нет в аккаунте Яндекс Бизнеса'
                failed.append(bar)
                continue
            try:
                items, total = [], None
                for page in client.iter_review_pages(pid, max_pages=MAX_REVIEW_PAGES):
                    total = page['total'] if page['total'] is not None else total
                    items.extend(parse_review(raw) for raw in page['items'])
                b_state['total'] = total
                b_state['received'] = len(items)
                # Полный проход — только когда получено ровно по счётчику
                # Яндекса: иначе «пропавшими» стали бы недополученные отзывы.
                complete = total is not None and len(items) == total
                b_state['stats'] = store.upsert_imported(SOURCE, bar, items,
                                                         history_cutoff=state['history_cutoff'],
                                                         complete=complete, by=SYNC_BY)
                b_state['synced_at'] = _now_str(clock_now())
                if not complete:
                    b_state['error'] = (f'Получено {len(items)} отзывов при счётчике Яндекса {total}: '
                                        f'пропавшие не отмечались')
            except YandexAuthError as e:
                b_state['error'] = str(e)
                return finish('expired', str(e))
            except YandexCaptchaError as e:
                b_state['error'] = str(e)
                return finish('captcha', str(e))
            except (YandexBusinessError, ValueError, OSError, RuntimeError) as e:
                b_state['error'] = _scrub(e, secrets)
                failed.append(bar)
        if failed:
            return finish('partial', 'Не сверены: ' + ', '.join(failed))
        return finish('ok')
    finally:
        close = getattr(client, 'close', None)
        if callable(close):
            close()
