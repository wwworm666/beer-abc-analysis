"""Снимок фидов Яндекса каждый день в 05:00 МСК.

До первого снимка страница и ссылка собирают краны сразу. После пяти утра
Яндекс и страница читают этот снимок до следующего утра. Ручные правки
накладываются уже при чтении, их ждать до пяти не нужно.
"""
import json
import os
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import portalocker

from core.storage_paths import get_data_path
from core.yml_feeds import FEED_ORDER

MOSCOW = ZoneInfo('Europe/Moscow')
REFRESH_HOUR = 5
REFRESH_MINUTE = 0

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_PATH = os.path.join(_BASE_DIR, 'data', '.yml_refresh.lock')
_started = False
_thread_lock = threading.Lock()
_lock_handle = None


def snapshot_path() -> str:
    return get_data_path('yml_bar_snapshot.json')


def next_refresh_at(now: datetime) -> datetime:
    """Ближайшие 05:00 МСК строго после now."""
    target = now.replace(hour=REFRESH_HOUR, minute=REFRESH_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def needs_refresh(now: datetime, updated_at: datetime = None) -> bool:
    """После сегодняшних 05:00 снимок нужен, если его ещё нет или он снят раньше."""
    today = now.replace(hour=REFRESH_HOUR, minute=REFRESH_MINUTE, second=0, microsecond=0)
    if now < today:
        return False
    return updated_at is None or updated_at < today


def load_snapshot(path=None):
    path = str(path or snapshot_path())
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def parse_updated_at(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MOSCOW)
    return parsed.astimezone(MOSCOW)


def save_snapshot(data, path=None) -> None:
    path = str(path or snapshot_path())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False)
    os.replace(temporary, path)


def refresh_snapshot(path=None) -> dict:
    """Снять кухню и пиво 0,5 л по всем барам. Прайс iiko запрашивается один раз."""
    from core.kitchen_yml import offers_for_bar
    from core.yml_feeds import combine_offers
    from routes.taps import fetch_price_sources
    from routes.yml_feeds import bar_items

    path = path or snapshot_path()
    previous = load_snapshot(path) or {}
    old_bars = previous.get('bars') if isinstance(previous.get('bars'), dict) else {}
    sources = fetch_price_sources()
    bars = {}
    for bar_id in FEED_ORDER:
        try:
            bars[bar_id] = {'items': bar_items(bar_id, sources=sources), 'error': None}
            print(f'[YML] снимок {bar_id}: {len(bars[bar_id]["items"])} позиций')
        except Exception as error:
            old = old_bars.get(bar_id) if isinstance(old_bars.get(bar_id), dict) else None
            if old and isinstance(old.get('items'), list):
                bars[bar_id] = {'items': old['items'], 'error': 'не обновилось, оставлен прошлый список'}
            else:
                bars[bar_id] = {'items': combine_offers(offers_for_bar(bar_id), []), 'error': 'пиво не обновилось'}
            print(f'[YML] снимок {bar_id} не удался: {type(error).__name__}')
    data = {
        'updated_at': datetime.now(MOSCOW).replace(microsecond=0).isoformat(),
        'bars': bars,
    }
    save_snapshot(data, path)
    return data


def _loop() -> None:
    while True:
        now = datetime.now(MOSCOW)
        updated = parse_updated_at((load_snapshot() or {}).get('updated_at'))
        if needs_refresh(now, updated):
            try:
                refresh_snapshot()
            except Exception as error:
                print(f'[YML] автообновление не удалось: {type(error).__name__}: {error}')
                time.sleep(600)
                continue
        wait = (next_refresh_at(datetime.now(MOSCOW)) - datetime.now(MOSCOW)).total_seconds()
        time.sleep(max(1.0, wait))


def start_scheduler() -> None:
    """Один поток на все воркеры gunicorn. В 05:00 МСК снимает фиды."""
    global _started, _lock_handle
    with _thread_lock:
        if _started:
            return
        os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
        handle = open(LOCK_PATH, 'a')
        try:
            portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.exceptions.BaseLockException:
            handle.close()
            print('[YML] лок обновления занят другим воркером')
            return
        _lock_handle = handle
        threading.Thread(target=_loop, name='yml-refresh', daemon=True).start()
        _started = True
        print('[YML] автообновление фидов в 05:00 МСК')
