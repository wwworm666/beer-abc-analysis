"""Ежедневный запуск проверки открытых смен в 14:59 МСК.

Паттерн скопирован с core/chz_scheduler.py с тремя отличиями:

1. Явный МСК: на Render контейнер UTC, поэтому datetime.now(MOSCOW_TZ) вместо
   локального datetime.now().
2. Защита от двойного срабатывания под gunicorn --workers 2: первый воркер,
   проснувшийся в 14:59, создаёт atomic lock-файл через
   os.open(O_CREAT | O_EXCL); второй ловит FileExistsError и тихо выходит.
3. Гейт по env: если TELEGRAM_OPEN_CHECK_BOT_TOKEN не задан — шедулер не
   стартует (аналог REMOTE_PASS в chz_scheduler).

Lock-файлы кладутся в data/ — ephemeral, но shared между воркерами одного
контейнера (это всё, что нужно). На следующий день день в имени файла другой,
старые удаляются при старте.
"""
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from core.open_check_bot import MOSCOW_TZ, now_msk, run_check

CHECK_HOUR = int(os.environ.get("OPEN_CHECK_HOUR", "14"))
CHECK_MINUTE = int(os.environ.get("OPEN_CHECK_MINUTE", "59"))

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_DIR = os.path.join(_BASE_DIR, 'data')
LOCK_PREFIX = '.open_check_lock_'

_started = False
_lock = threading.Lock()


def _seconds_until_next_run(hour: int, minute: int) -> float:
    """Сколько секунд до следующего срабатывания в указанное МСК-время."""
    now = datetime.now(MOSCOW_TZ)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


def _try_acquire_daily_lock(date_str: str) -> bool:
    """Atomic test-and-set на день. True если этот воркер первый."""
    os.makedirs(LOCK_DIR, exist_ok=True)
    lock_path = os.path.join(LOCK_DIR, f'{LOCK_PREFIX}{date_str}')
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, f'{os.getpid()}\n'.encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False


def _cleanup_old_locks() -> None:
    """Удалить lock-файлы старше 2 дней. Защита от мусора."""
    if not os.path.isdir(LOCK_DIR):
        return
    today = datetime.now(MOSCOW_TZ).strftime('%Y-%m-%d')
    cutoff = (datetime.now(MOSCOW_TZ) - timedelta(days=2)).strftime('%Y-%m-%d')
    for fname in os.listdir(LOCK_DIR):
        if not fname.startswith(LOCK_PREFIX):
            continue
        date_part = fname[len(LOCK_PREFIX):]
        if len(date_part) == 10 and date_part < cutoff and date_part != today:
            try:
                os.remove(os.path.join(LOCK_DIR, fname))
            except OSError:
                pass


def _run_once() -> None:
    """Одно срабатывание: lock + run_check."""
    check_dt = now_msk()
    date_str = check_dt.strftime('%Y-%m-%d')
    if not _try_acquire_daily_lock(date_str):
        print(f"[OPEN-CHECK] {check_dt.isoformat()} lock уже взят другим воркером — пропуск")
        return
    print(f"[OPEN-CHECK] {check_dt.isoformat()} trigger")
    try:
        result = run_check(check_dt=check_dt)
        print(f"[OPEN-CHECK] результат: {result}")
    except Exception as e:
        print(f"[OPEN-CHECK] {check_dt.isoformat()} run_check failed: {e}")


def _loop() -> None:
    while True:
        try:
            wait = _seconds_until_next_run(CHECK_HOUR, CHECK_MINUTE)
            next_at = datetime.now(MOSCOW_TZ) + timedelta(seconds=wait)
            print(f"[OPEN-CHECK] следующая проверка: {next_at.isoformat()} (через {wait/3600:.1f}ч)")
            time.sleep(wait)
            _run_once()
            # Не дать циклу прокрутиться слишком быстро, если _run_once упал мгновенно.
            time.sleep(60)
        except Exception as e:
            # Не даём исключению (например OSError из lock-файла) молча убить
            # daemon-поток — иначе проверка открытых смен перестанет срабатывать
            # до рестарта. Логируем и продолжаем после паузы.
            print(f"[OPEN-CHECK] исключение в цикле планировщика: {e}")
            time.sleep(60)


def start_scheduler() -> None:
    """Запустить daemon-поток. Идемпотентно (один поток на процесс)."""
    global _started
    with _lock:
        if _started:
            return
        if not os.environ.get("TELEGRAM_OPEN_CHECK_BOT_TOKEN"):
            print("[OPEN-CHECK] TELEGRAM_OPEN_CHECK_BOT_TOKEN не задан — шедулер отключён")
            return
        _cleanup_old_locks()
        t = threading.Thread(target=_loop, name="open-check-scheduler", daemon=True)
        t.start()
        _started = True
        print(f"[OPEN-CHECK] стартовал, проверка ежедневно в {CHECK_HOUR:02d}:{CHECK_MINUTE:02d} МСК")
