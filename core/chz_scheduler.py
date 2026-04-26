"""Ежедневный авторефреш ЧЗ-данных.

Запускает фоновый поток, который раз в сутки в заданное время дёргает
`POST /api/chz/refresh` (тот же эндпоинт что и кнопка в UI). Результат —
свежий `chz_stock.json` без ручного вмешательства.

Время refresh берётся из env CHZ_REFRESH_HOUR (default 3, т.е. 03:00 по
локальному времени бара-сервера).
"""
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta

REFRESH_HOUR = int(os.environ.get("CHZ_REFRESH_HOUR", "3"))
REFRESH_MINUTE = int(os.environ.get("CHZ_REFRESH_MINUTE", "0"))
LOCAL_REFRESH_URL = os.environ.get("CHZ_REFRESH_URL", "http://127.0.0.1:5000/api/chz/refresh")

_started = False
_lock = threading.Lock()


def _seconds_until_next_run(hour, minute):
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


def _trigger_refresh():
    try:
        req = urllib.request.Request(LOCAL_REFRESH_URL, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", errors="replace")
        print(f"[CHZ-SCHED] {datetime.now().isoformat()} POST refresh → {r.status}: {body[:200]}")
    except Exception as e:
        print(f"[CHZ-SCHED] {datetime.now().isoformat()} refresh failed: {e}")


def _loop():
    while True:
        wait = _seconds_until_next_run(REFRESH_HOUR, REFRESH_MINUTE)
        next_at = datetime.now() + timedelta(seconds=wait)
        print(f"[CHZ-SCHED] следующий авторефреш: {next_at.isoformat()} (через {wait/3600:.1f}ч)")
        time.sleep(wait)
        _trigger_refresh()
        # На всякий случай не дать циклу прокрутиться слишком быстро если
        # _trigger_refresh падает мгновенно
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
        t = threading.Thread(target=_loop, name="chz-scheduler", daemon=True)
        t.start()
        _started = True
        print(f"[CHZ-SCHED] стартовал, refresh ежедневно в {REFRESH_HOUR:02d}:{REFRESH_MINUTE:02d}")
