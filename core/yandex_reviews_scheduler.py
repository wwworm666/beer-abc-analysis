"""Планировщик сверки отзывов Яндекс Бизнеса: раз в сутки (решение владельца 2026-09-28).

Время — по МОСКВЕ, явно через core/msk_time (в прод-образе нет tzdata, и
наивное время там UTC — у других шедулеров проекта 05:40 значит 08:40 МСК;
здесь так не делаем, чтобы час в .env читался как есть). По умолчанию 08:30:
утром, до начала смен — ночные отзывы уже в списке.
    YANDEX_REVIEWS_SYNC_HOUR / _MINUTE   время ежедневной сверки, МСК (8 / 30)
    YANDEX_REVIEWS_SYNC_ENABLED          0 — не запускать (по умолчанию 1)
    YANDEX_REVIEWS_NOTIFY                0 — не слать новые отзывы в бот
                                         kulturaopenclosed (по умолчанию 1,
                                         core/review_notify.py)

При старте приложения — разовая сверка, если успешной не было больше
STARTUP_STALE_HOURS: так первая загрузка истории происходит сразу после
деплоя, а новые cookies (после «сессия не принята») подхватываются
перезапуском, без ожидания утра. Частые деплои не множат обращения к
Яндексу: успешная сверка моложе этого срока — стартовой нет.

Защита от двойного запуска (gunicorn --workers 2): lock-файл на дату
(O_CREAT|O_EXCL, как core/guest_sync_scheduler.py) + межпроцессный замок
внутри core/yandex_reviews_sync.sync_all.

Сверка только читает Яндекс (core/yandex_business.py — только GET).
Документация: docs/yandex-reviews.md.
"""
import os
import threading
import time
from datetime import datetime, timedelta

from core import msk_time

SYNC_HOUR = int(os.environ.get('YANDEX_REVIEWS_SYNC_HOUR', '8'))
SYNC_MINUTE = int(os.environ.get('YANDEX_REVIEWS_SYNC_MINUTE', '30'))
# Стартовая сверка — только если успешной не было дольше этого: сутки минус
# запас, чтобы утренняя сверка и перезапуск днём не ходили в Яндекс дважды.
STARTUP_STALE_HOURS = 20

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_DIR = os.path.join(_BASE_DIR, 'data')
LOCK_PREFIX = '.yandex_reviews_lock_'
STARTUP_LOCK_PREFIX = '.yandex_reviews_startup_'

_started = False
_lock = threading.Lock()


def _now() -> datetime:
    return msk_time.now().replace(tzinfo=None)


def seconds_until(hour: int, minute: int, now: datetime) -> float:
    """Секунды до ближайшего hour:minute (МСК) после now."""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _try_acquire_lock(prefix: str, date_str: str) -> bool:
    """Atomic test-and-set на день. True — этот воркер первый."""
    os.makedirs(LOCK_DIR, exist_ok=True)
    try:
        fd = os.open(os.path.join(LOCK_DIR, f'{prefix}{date_str}'), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    try:
        os.write(fd, f'{os.getpid()}\n'.encode())
    finally:
        os.close(fd)
    return True


def _cleanup_old_locks() -> None:
    if not os.path.isdir(LOCK_DIR):
        return
    cutoff = (_now() - timedelta(days=2)).strftime('%Y-%m-%d')
    for fname in os.listdir(LOCK_DIR):
        if fname.startswith(LOCK_PREFIX) or fname.startswith(STARTUP_LOCK_PREFIX):
            date_part = fname.rsplit('_', 1)[-1]
            if len(date_part) == 10 and date_part < cutoff:
                try:
                    os.remove(os.path.join(LOCK_DIR, fname))
                except OSError:
                    pass


def needs_startup_sync(state: dict, now: datetime) -> bool:
    """Успешной сверки нет или она старше STARTUP_STALE_HOURS."""
    last = state.get('last_success_at')
    if not last:
        return True
    try:
        return now - datetime.strptime(last, '%Y-%m-%dT%H:%M') > timedelta(hours=STARTUP_STALE_HOURS)
    except ValueError:
        return True


def _run(tag: str) -> None:
    from core.yandex_reviews_sync import sync_all
    notifier = None
    if os.environ.get('YANDEX_REVIEWS_NOTIFY', '1').strip() != '0':
        from core.review_notify import notify_new_reviews
        notifier = notify_new_reviews
    print(f'[YANDEX-REVIEWS-SCHED] сверка ({tag}), рассылка новых отзывов: '
          f'{"да" if notifier else "нет"}')
    sync_all(notifier=notifier)


def _daily_loop():
    while True:
        try:
            wait = seconds_until(SYNC_HOUR, SYNC_MINUTE, _now())
            print(f'[YANDEX-REVIEWS-SCHED] следующая сверка через {wait / 3600:.1f} ч '
                  f'({SYNC_HOUR:02d}:{SYNC_MINUTE:02d} МСК)')
            time.sleep(wait)
            if _try_acquire_lock(LOCK_PREFIX, _now().strftime('%Y-%m-%d')):
                _run('daily')
            time.sleep(60)
        except Exception as e:  # noqa: BLE001 — цикл не должен умирать
            print(f'[YANDEX-REVIEWS-SCHED] исключение в цикле: {e!r}')
            time.sleep(60)


def _startup_sync():
    time.sleep(20)   # дать приложению подняться
    try:
        from core.yandex_reviews_sync import load_state
        if not needs_startup_sync(load_state(), _now()):
            print('[YANDEX-REVIEWS-SCHED] свежая сверка есть — стартовой не будет')
            return
        if _try_acquire_lock(STARTUP_LOCK_PREFIX, _now().strftime('%Y-%m-%d')):
            _run('startup')
    except Exception as e:  # noqa: BLE001
        print(f'[YANDEX-REVIEWS-SCHED] стартовая сверка: {e!r}')


def start_scheduler():
    """Запустить daemon-потоки (ежедневная + стартовая сверка). Идемпотентно."""
    global _started
    with _lock:
        if _started:
            return
        if os.environ.get('YANDEX_REVIEWS_SYNC_ENABLED', '1').strip() == '0':
            print('[YANDEX-REVIEWS-SCHED] выключен (YANDEX_REVIEWS_SYNC_ENABLED=0)')
            return
        if not (os.environ.get('YANDEX_BUSINESS_SESSION_ID', '').strip()
                and os.environ.get('YANDEX_BUSINESS_SESSION_ID2', '').strip()):
            print('[YANDEX-REVIEWS-SCHED] cookies Яндекса не заданы — сверка не запускается')
            return
        _cleanup_old_locks()
        threading.Thread(target=_daily_loop, name='yandex-reviews-daily', daemon=True).start()
        threading.Thread(target=_startup_sync, name='yandex-reviews-startup', daemon=True).start()
        _started = True
        print(f'[YANDEX-REVIEWS-SCHED] запущен: ежедневно в {SYNC_HOUR:02d}:{SYNC_MINUTE:02d} МСК')
