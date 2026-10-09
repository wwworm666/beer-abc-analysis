"""Планировщик отзывов с Яндекс Карт: проверка раз в 3 часа, полный проход раз в сутки, сторож.

Решение владельца 2026-10-09 (docs/yandex-reviews.md):
    - раз в CHECK_EVERY_HOURS (3 ч) — быстрая проверка: первая страница каждого
      бара (4 запроса), остальные страницы — только если на Картах отзывов больше,
      чем у нас (core/yandex_reviews_sync.sync_all('quick'));
    - раз в сутки в FULL_HOUR:FULL_MINUTE по Москве (08:30) — полный проход всех
      страниц: ответы на старые отзывы, правки, пропавшие (sync_all('full'));
    - после каждого такта — сторож (core/yandex_reviews_watchdog.check): сообщение
      в Telegram, если отзывы не обновлялись больше суток или на Картах больше
      отзывов, чем у нас, дольше 6 часов.
Новые отзывы уходят в бот после каждой проверки — в течение трёх часов, а не раз
в сутки.

Что делать на такте (due_kind), по состоянию загрузки:
    1. полного прохода не было с последнего «08:30» (сегодня, если уже прошло,
       иначе вчера) -> full;
    2. с начала последней проверки прошло меньше 3 ч -> ничего;
    3. удачного полного прохода с последнего «08:30» нет (он не удался) -> full
       (повтор не чаще раза в 3 ч), иначе -> quick.
Первый запуск после перехода с кабинета — сразу full: в состоянии ещё нет полного
прохода с Карт.

Такт — раз в TICK_SEC (15 минут), первый — через STARTUP_DELAY_SEC после старта.
Время — по МОСКВЕ через core/msk_time (в прод-образе наивное время — UTC).
Один поток на все воркеры gunicorn: поток держит файловый замок
THREAD_LOCK_PATH, второй воркер его не получает и поток не заводит (как сверка
прайсов core/yandex_maps_status.start_watcher). Перезапущенный воркер берёт
освободившийся замок. Сама проверка ещё и под замком состояния (sync_all).

Переменные окружения:
    YANDEX_REVIEWS_SYNC_HOUR / _MINUTE   время полного прохода, МСК (8 / 30)
    YANDEX_REVIEWS_SYNC_ENABLED          0 — не запускать (по умолчанию 1)
    YANDEX_REVIEWS_NOTIFY                0 — не слать новые отзывы в бот
                                         kulturaopenclosed (core/review_notify.py)
    YANDEX_REVIEWS_WATCHDOG              0 — сторож не пишет в Telegram
Cookies Яндекса для загрузки больше не нужны.
"""
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import portalocker

from core import msk_time

CHECK_EVERY_HOURS = 3
CHECK_EVERY = timedelta(hours=CHECK_EVERY_HOURS)
FULL_HOUR = int(os.environ.get('YANDEX_REVIEWS_SYNC_HOUR', '8'))
FULL_MINUTE = int(os.environ.get('YANDEX_REVIEWS_SYNC_MINUTE', '30'))
# Такт: 15 минут — полный проход начинается не позже 08:45, а проверка «пора ли»
# только читает файл состояния.
TICK_SEC = 15 * 60
STARTUP_DELAY_SEC = 20    # дать приложению подняться

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THREAD_LOCK_PATH = os.path.join(_BASE_DIR, 'data', '.yandex_reviews_thread.lock')
STAMP = '%Y-%m-%dT%H:%M'

_started = False
_lock = threading.Lock()
_lock_handle = None


def _now() -> datetime:
    return msk_time.now().replace(tzinfo=None)


def _parse(stamp) -> Optional[datetime]:
    try:
        return datetime.strptime(str(stamp)[:16], STAMP) if stamp else None
    except ValueError:
        return None


def last_full_slot(now: datetime) -> datetime:
    """Последнее наступившее «FULL_HOUR:FULL_MINUTE» по Москве: сегодня или вчера."""
    slot = now.replace(hour=FULL_HOUR, minute=FULL_MINUTE, second=0, microsecond=0)
    return slot if slot <= now else slot - timedelta(days=1)


def due_kind(state: dict, now: datetime) -> Optional[str]:
    """'full' | 'quick' | None — что делать на этом такте (правила — докстринг модуля)."""
    from core.yandex_reviews_sync import FULL, QUICK, STATE_SOURCE
    maps = state.get('source') == STATE_SOURCE
    slot = last_full_slot(now)
    full_attempt = _parse(state.get('last_full_attempt_at')) if maps else None
    if full_attempt is None or full_attempt < slot:
        return FULL
    last = _parse(state.get('last_attempt_at'))
    if last is not None and now - last < CHECK_EVERY:
        return None
    full_ok = _parse(state.get('last_full_at'))
    return FULL if full_ok is None or full_ok < slot else QUICK


def tick(now: Optional[datetime] = None) -> dict:
    """Один такт: проверка, если пора, затем сторож. -> {kind, status, watchdog}."""
    from core import yandex_reviews_sync as sync
    from core import yandex_reviews_watchdog as watchdog
    now = now or _now()
    kind = due_kind(sync.load_state(), now)
    result = {'kind': kind, 'status': None}
    if kind:
        notifier = None
        if os.environ.get('YANDEX_REVIEWS_NOTIFY', '1').strip() != '0':
            from core.review_notify import notify_new_reviews
            notifier = notify_new_reviews
        print(f'[YANDEX-REVIEWS-SCHED] проверка Карт ({kind}), рассылка новых отзывов: '
              f'{"да" if notifier else "нет"}')
        result['status'] = sync.sync_all(kind, notifier=notifier).get('status')
    result['watchdog'] = watchdog.check()
    return result


def _loop():
    time.sleep(STARTUP_DELAY_SEC)
    while True:
        try:
            tick()
        except Exception as e:  # noqa: BLE001 — цикл не должен умирать
            print(f'[YANDEX-REVIEWS-SCHED] исключение в такте: {e!r}')
        time.sleep(TICK_SEC)


def start_scheduler():
    """Запустить поток проверок (один на все воркеры). Идемпотентно."""
    global _started, _lock_handle
    with _lock:
        if _started:
            return
        from core.yandex_reviews_sync import enabled
        if not enabled():
            print('[YANDEX-REVIEWS-SCHED] выключен (YANDEX_REVIEWS_SYNC_ENABLED=0)')
            return
        os.makedirs(os.path.dirname(THREAD_LOCK_PATH), exist_ok=True)
        handle = open(THREAD_LOCK_PATH, 'a')
        try:
            portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.exceptions.BaseLockException:
            handle.close()
            return
        _lock_handle = handle
        threading.Thread(target=_loop, name='yandex-reviews', daemon=True).start()
        _started = True
        print(f'[YANDEX-REVIEWS-SCHED] запущен: Яндекс Карты раз в {CHECK_EVERY_HOURS} ч, '
              f'полный проход в {FULL_HOUR:02d}:{FULL_MINUTE:02d} МСК')
