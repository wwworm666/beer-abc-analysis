"""Фоновый пересчёт витрины «Месячный отчёт».

Раз в сутки досчитывает завершённые месяцы по всем заведениям и годам глубины
(текущий неполный месяц не нужен и не считается); закрытый месяц считается один раз
и замораживается, только что закрывшийся подхватывается ближайшим прогоном.
При старте приложения делает разовый бэкфилл (на свежем деплое — за N лет назад),
чтобы вкладка открывалась мгновенно с диска, не дёргая iiko на просмотре.

Время берётся из env MONTHLY_REPORT_HOUR/MINUTE (default 04:30 локального времени).

ЗАЩИТА ОТ ДВОЙНОГО ЗАПУСКА (gunicorn --workers 2):
каждый воркер стартует свой scheduler-поток; в момент прогона первый берёт atomic
lock-file (O_CREAT|O_EXCL) на дату, второй ловит FileExistsError и пропускает.
Тот же паттерн, что в chz_scheduler / open_check_scheduler.
"""
import os
import threading
import time
from datetime import datetime, timedelta

from core import monthly_report

REFRESH_HOUR = int(os.environ.get("MONTHLY_REPORT_HOUR", "4"))
REFRESH_MINUTE = int(os.environ.get("MONTHLY_REPORT_MINUTE", "30"))

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_DIR = os.path.join(_BASE_DIR, 'data')
LOCK_PREFIX = '.monthly_report_lock_'
STARTUP_LOCK_PREFIX = '.monthly_report_startup_'

_started = False
_lock = threading.Lock()


def _iiko_configured():
    try:
        from config import IIKO_LOGIN, IIKO_PASSWORD
        return bool(IIKO_LOGIN and IIKO_PASSWORD)
    except Exception:
        return False


def _seconds_until_next_run(hour, minute):
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


def _try_acquire_lock(prefix: str, date_str: str) -> bool:
    """Atomic test-and-set на день. True если этот воркер первый."""
    os.makedirs(LOCK_DIR, exist_ok=True)
    lock_path = os.path.join(LOCK_DIR, f'{prefix}{date_str}')
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
    """Удалить lock-файлы старше 2 дней."""
    if not os.path.isdir(LOCK_DIR):
        return
    today = datetime.now().strftime('%Y-%m-%d')
    cutoff = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    for fname in os.listdir(LOCK_DIR):
        if not (fname.startswith(LOCK_PREFIX) or fname.startswith(STARTUP_LOCK_PREFIX)):
            continue
        date_part = fname.split('_')[-1]
        if len(date_part) == 10 and date_part < cutoff and date_part != today:
            try:
                os.remove(os.path.join(LOCK_DIR, fname))
            except OSError:
                pass


def _run_refresh(tag: str):
    started = time.time()
    try:
        changed = monthly_report.refresh_all()
        print(f"[MONTHLY-SCHED] {datetime.now().isoformat()} {tag}: "
              f"izmeneno {changed} (venue,year) za {time.time()-started:.0f}s")
    except Exception as e:
        print(f"[MONTHLY-SCHED] {datetime.now().isoformat()} {tag} oshibka: {e}")


def _nightly_loop():
    while True:
        try:
            wait = _seconds_until_next_run(REFRESH_HOUR, REFRESH_MINUTE)
            next_at = datetime.now() + timedelta(seconds=wait)
            print(f"[MONTHLY-SCHED] sleduyushchiy pereraschet: {next_at.isoformat()} "
                  f"(cherez {wait/3600:.1f}ch)")
            time.sleep(wait)
            date_str = datetime.now().strftime('%Y-%m-%d')
            if _try_acquire_lock(LOCK_PREFIX, date_str):
                _run_refresh("nightly")
            else:
                print(f"[MONTHLY-SCHED] lock uzhe vzyat drugim vorkerom — propusk")
            time.sleep(60)  # не дать циклу прокрутиться слишком быстро
        except Exception as e:
            print(f"[MONTHLY-SCHED] isklyuchenie v cikle: {e}")
            time.sleep(60)


def _startup_backfill():
    """Разовый прогон при старте: на свежем деплое наполняет витрину за N лет.
    На тёплом кэше дёшев (только текущий месяц). Один раз в день на воркеров."""
    time.sleep(10)  # дать приложению подняться
    date_str = datetime.now().strftime('%Y-%m-%d')
    if not _try_acquire_lock(STARTUP_LOCK_PREFIX, date_str):
        print("[MONTHLY-SCHED] startup-backfill uzhe vzyat drugim vorkerom — propusk")
        return
    _run_refresh("startup-backfill")


def start_scheduler():
    """Запустить daemon-потоки (ночной пересчёт + стартовый бэкфилл). Идемпотентно."""
    global _started
    with _lock:
        if _started:
            return
        if not _iiko_configured():
            print("[MONTHLY-SCHED] IIKO_LOGIN/PASSWORD ne zadany — pereraschet otklyuchen")
            return
        _cleanup_old_locks()
        threading.Thread(target=_nightly_loop, name="monthly-report-scheduler", daemon=True).start()
        threading.Thread(target=_startup_backfill, name="monthly-report-backfill", daemon=True).start()
        _started = True
        print(f"[MONTHLY-SCHED] startoval, pereraschet ezhednevno v "
              f"{REFRESH_HOUR:02d}:{REFRESH_MINUTE:02d} + startovy bekfill")
