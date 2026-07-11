"""Ежедневный авторефреш ЧЗ-данных.

Запускает фоновый поток, который раз в сутки в заданное время дёргает
`POST /api/chz/refresh` (тот же эндпоинт что и кнопка в UI). Результат —
свежий `chz_stock.json` без ручного вмешательства.

Время refresh берётся из env CHZ_REFRESH_HOUR (default 3, т.е. 03:00 по
локальному времени бара-сервера).

ЗАЩИТА ОТ ДВОЙНОГО ЗАПУСКА (gunicorn --workers 2):
Каждый воркер стартует свой scheduler-поток. В момент срабатывания первый
воркер берёт atomic lock-file (O_CREAT|O_EXCL) на текущую дату, второй —
ловит FileExistsError и пропускает. Тот же паттерн что и в open_check_scheduler.
"""
import os
import threading
import time
from datetime import datetime, timedelta

REFRESH_HOUR = int(os.environ.get("CHZ_REFRESH_HOUR", "3"))
REFRESH_MINUTE = int(os.environ.get("CHZ_REFRESH_MINUTE", "0"))

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_DIR = os.path.join(_BASE_DIR, 'data')
LOCK_PREFIX = '.chz_refresh_lock_'

_started = False
_lock = threading.Lock()


def _seconds_until_next_run(hour, minute):
    now = datetime.now()
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
    today = datetime.now().strftime('%Y-%m-%d')
    cutoff = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    for fname in os.listdir(LOCK_DIR):
        if not fname.startswith(LOCK_PREFIX):
            continue
        date_part = fname[len(LOCK_PREFIX):]
        if len(date_part) == 10 and date_part < cutoff and date_part != today:
            try:
                os.remove(os.path.join(LOCK_DIR, fname))
            except OSError:
                pass


def _trigger_refresh():
    date_str = datetime.now().strftime('%Y-%m-%d')
    if not _try_acquire_daily_lock(date_str):
        print(f"[CHZ-SCHED] {datetime.now().isoformat()} lock уже взят другим воркером — пропуск")
        return
    # Зовём refresh НАПРЯМУЮ, а не POST'ом на /api/chz/refresh: у планировщика нет
    # сессии, и auth-гейт отбивает внутренний запрос 401 (из-за этого авторефреш
    # молча стоял с 26.06.2026, см. docs/lessons.md). Прямой вызов разделяет ту же
    # cross-worker блокировку, что и кнопка в UI. Импорт ленивый — routes.stocks
    # тянет Flask-контекст, грузим только в момент срабатывания.
    try:
        from routes.stocks import start_chz_refresh
        result, code = start_chz_refresh()
        print(f"[CHZ-SCHED] {datetime.now().isoformat()} refresh → {code}: {result}")
    except Exception as e:
        print(f"[CHZ-SCHED] {datetime.now().isoformat()} refresh failed: {e}")


def _loop():
    while True:
        try:
            wait = _seconds_until_next_run(REFRESH_HOUR, REFRESH_MINUTE)
            next_at = datetime.now() + timedelta(seconds=wait)
            print(f"[CHZ-SCHED] следующий авторефреш: {next_at.isoformat()} (через {wait/3600:.1f}ч)")
            time.sleep(wait)
            _trigger_refresh()
            # На всякий случай не дать циклу прокрутиться слишком быстро если
            # _trigger_refresh падает мгновенно
            time.sleep(60)
        except Exception as e:
            # Не даём исключению (например OSError из lock-файла на full/RO диске)
            # молча убить daemon-поток — иначе авторефреш перестанет работать до
            # рестарта. Логируем и продолжаем после паузы.
            print(f"[CHZ-SCHED] исключение в цикле планировщика: {e}")
            time.sleep(60)


def start_scheduler():
    """Запустить daemon-поток с ежедневным refresh. Идемпотентно."""
    global _started
    with _lock:
        if _started:
            return
        if not os.environ.get("REMOTE_PASS"):
            print("[CHZ-SCHED] REMOTE_PASS не установлен — авторефреш отключён")
            return
        _cleanup_old_locks()
        t = threading.Thread(target=_loop, name="chz-scheduler", daemon=True)
        t.start()
        _started = True
        print(f"[CHZ-SCHED] стартовал, refresh ежедневно в {REFRESH_HOUR:02d}:{REFRESH_MINUTE:02d}")
