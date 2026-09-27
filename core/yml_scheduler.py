"""Снимок пива для фидов Яндекса: каждый день в 05:00 МСК и по кнопке.

В снимке только разливное пиво 0,5 л по барам (цены iiko и сорта на кранах на
утро). Кухня в снимок не входит: она из файла в репозитории и собирается при
каждом запросе, поэтому деплой обновляет её сразу. Ручные правки накладываются
при чтении. Правила — docs/yandex-feeds.md, раздел «Снимок».
"""
import html
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
SNAPSHOT_SCHEMA = 2
# Бар не обновился: прошлый список пива держим не дольше двух суток, дальше
# в файле его лучше не показывать, чем показать давно выпитые сорта.
KEEP_OLD_BEER = timedelta(hours=48)
# Страница помечает снимок устаревшим, если он старше суток с запасом.
STALE_AFTER = timedelta(hours=26)
RETRY_SECONDS = 600
MAX_ATTEMPTS_PER_DAY = 6

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_PATH = os.path.join(_BASE_DIR, 'data', '.yml_refresh.lock')
# Сам прогон снимка: и планировщик, и кнопка «Переснять» берут этот лок.
RUN_LOCK_PATH = os.path.join(_BASE_DIR, 'data', '.yml_refresh_run.lock')
_started = False
_thread_lock = threading.Lock()
_lock_handle = None
_alerted_day = None


class RefreshBusy(Exception):
    """Снимок уже снимается (другой воркер или вторая кнопка)."""


def snapshot_path() -> str:
    return get_data_path('yml_bar_snapshot.json')


def next_refresh_at(now: datetime) -> datetime:
    """Ближайшие 05:00 МСК строго после now."""
    target = now.replace(hour=REFRESH_HOUR, minute=REFRESH_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def needs_refresh(now: datetime, updated_at: datetime = None, schema_ok: bool = True) -> bool:
    """Снимок старой схемы — снять сразу. Иначе после сегодняшних 05:00 снимок
    нужен, если его ещё нет или он снят раньше."""
    if not schema_ok:
        return True
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


def snapshot_ok(data) -> bool:
    """Снимок текущей схемы. Схема 1 (кухня+пиво с id по крану) не годится."""
    return (isinstance(data, dict) and data.get('schema') == SNAPSHOT_SCHEMA
            and isinstance(data.get('bars'), dict))


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
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def snapshot_status(data, now=None) -> dict:
    """Для страницы: когда снят снимок, устарел ли, когда следующий."""
    now = now or datetime.now(MOSCOW)
    updated = parse_updated_at(data.get('updated_at')) if snapshot_ok(data) else None
    return {
        'updated_at': updated.isoformat() if updated else None,
        'stale': bool(updated and now - updated > STALE_AFTER),
        'next_refresh': next_refresh_at(now).isoformat(),
    }


def _bar_snapshot(bar_id, sources, old, now):
    """Пиво одного бара. Не собралось или пусто при активных кранах — прошлый
    список (не старше KEEP_OLD_BEER) с текстом ошибки."""
    from core.taplist_yml import beer_offers
    from routes.taps import load_reviewed_taplist

    excluded, active, problem = [], 0, None
    try:
        rows = load_reviewed_taplist(bar_id, True, sources=sources)
        active = len(rows)
        beer, excluded = beer_offers(rows)
        if active and not beer:
            problem = f'0 позиций пива при {active} активных кранах'
    except Exception as error:
        beer, problem = [], f'{type(error).__name__}: {str(error)[:200]}'
    if problem is None:
        return {'beer': beer, 'excluded': excluded, 'error': None,
                'beer_updated_at': now.isoformat(), 'active_taps': active}
    old_at = parse_updated_at(old.get('beer_updated_at'))
    if old.get('beer') and old_at and now - old_at <= KEEP_OLD_BEER:
        return {'beer': old['beer'], 'excluded': excluded,
                'error': f'Пиво не обновилось ({problem}). В файле список от {old_at:%d.%m %H:%M}.',
                'beer_updated_at': old['beer_updated_at'], 'active_taps': active}
    return {'beer': [], 'excluded': excluded,
            'error': f'Пиво не обновилось ({problem}). Пиво в файле не показывается.',
            'beer_updated_at': None, 'active_taps': active}


def refresh_snapshot(path=None, wait=300.0) -> dict:
    """Снять пиво 0,5 л по всем барам. Прайс iiko запрашивается один раз.

    wait — сколько секунд ждать, если снимок уже снимается. 0 — не ждать:
    RefreshBusy. Сбой прайса iiko пробрасывается, файл снимка не трогается.
    """
    from routes.taps import fetch_price_sources

    path = str(path or snapshot_path())
    os.makedirs(os.path.dirname(RUN_LOCK_PATH), exist_ok=True)
    lock = portalocker.Lock(RUN_LOCK_PATH, timeout=wait, fail_when_locked=not wait)
    try:
        lock.acquire()
    except portalocker.exceptions.LockException:
        raise RefreshBusy('Снимок уже снимается') from None
    try:
        previous = load_snapshot(path)
        old_bars = previous['bars'] if snapshot_ok(previous) else {}
        sources = fetch_price_sources()
        now = datetime.now(MOSCOW).replace(microsecond=0)
        bars = {}
        for bar_id in FEED_ORDER:
            old = old_bars.get(bar_id) if isinstance(old_bars.get(bar_id), dict) else {}
            bars[bar_id] = _bar_snapshot(bar_id, sources, old, now)
            state = bars[bar_id]
            print(f'[YML] снимок {bar_id}: {len(state["beer"])} сортов, '
                  f'{len(state["excluded"])} не в фиде' + (f'; {state["error"]}' if state['error'] else ''))
        data = {'schema': SNAPSHOT_SCHEMA, 'updated_at': now.isoformat(), 'bars': bars}
        save_snapshot(data, path)
        return data
    finally:
        lock.release()


def _send_alarm(text) -> bool:
    """В чаты тревог open-check (TELEGRAM_ALARM_CHAT_IDS + подписчики)."""
    try:
        from core.open_check_bot import _alarm_recipients, _is_dry_run
        from core.open_check_telegram import send_message
        recipients = _alarm_recipients()
        if not recipients:
            print('[YML] тревога: нет получателей')
            return False
        if _is_dry_run():
            text = '[DRY-RUN] ' + text
            recipients = recipients[:1]
        return sum(bool(send_message(chat, text, html=True)) for chat in recipients) > 0
    except Exception as error:
        print(f'[YML] тревога не отправлена: {type(error).__name__}: {error}')
        return False


def alarm_text(problems) -> str:
    from core.taplist import BAR_NAMES
    lines = ['<b>Фиды Яндекса: снимок пива с ошибкой</b>']
    for bar_id, text in problems.items():
        title = BAR_NAMES.get(bar_id, 'Все бары')
        lines.append(f'{html.escape(title)}: {html.escape(str(text))}')
    lines.append('Страница /yandex, кнопка «Переснять».')
    return '\n'.join(lines)


def _alarm_once(day, problems):
    """Одна тревога в день: повторы каждые 10 минут чат не засыпают."""
    global _alerted_day
    if _alerted_day == day:
        return
    if _send_alarm(alarm_text(problems)):
        _alerted_day = day


def _loop() -> None:
    attempts = {}
    while True:
        now = datetime.now(MOSCOW)
        day = now.date().isoformat()
        data = load_snapshot()
        ok = snapshot_ok(data)
        updated = parse_updated_at(data.get('updated_at')) if ok else None
        after_five = now >= now.replace(hour=REFRESH_HOUR, minute=REFRESH_MINUTE, second=0, microsecond=0)
        failed = ok and any(isinstance(bar, dict) and bar.get('error') for bar in data['bars'].values())
        retry = failed and after_five and 0 < attempts.get(day, 0) < MAX_ATTEMPTS_PER_DAY
        if needs_refresh(now, updated, ok) or retry:
            attempts[day] = attempts.get(day, 0) + 1
            try:
                fresh = refresh_snapshot()
            except Exception as error:
                # Прайс iiko недоступен: повторять каждые 10 минут, пока не снимется.
                print(f'[YML] автообновление не удалось: {type(error).__name__}: {error}')
                _alarm_once(day, {'all': f'снимок не снят ({type(error).__name__}: {str(error)[:200]}); '
                                         f'в файлах остаётся прошлый снимок'})
                time.sleep(RETRY_SECONDS)
                continue
            problems = {bar: state['error'] for bar, state in fresh['bars'].items() if state.get('error')}
            if problems:
                _alarm_once(day, problems)
                if attempts[day] < MAX_ATTEMPTS_PER_DAY:
                    time.sleep(RETRY_SECONDS)
                    continue
        wait = (next_refresh_at(datetime.now(MOSCOW)) - datetime.now(MOSCOW)).total_seconds()
        time.sleep(max(1.0, wait))


def start_scheduler() -> None:
    """Один поток на все воркеры gunicorn. В 05:00 МСК снимает пиво."""
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
        print('[YML] автообновление снимка пива в 05:00 МСК')
