"""Фоновый опрос термометров и запись истории.

Daemon-поток будит каждые TUYA_POLL_MINUTES минут, опрашивает Tuya и складывает
показания в temperature_store. Дедуп между воркерами — на уровне БД (PRIMARY KEY
по бакету, INSERT OR IGNORE), поэтому здесь, в отличие от open_check_scheduler,
lock-файлы не нужны: оба воркера могут опрашивать, в истории останется одна строка
на бакет (и если у одного воркера запрос упал — запишет другой).

Гейт: поток стартует только если заданы TUYA_ACCESS_ID/SECRET и TUYA_POLL_MINUTES > 0
(аналог гейта по REMOTE_PASS в chz_scheduler / по токену в open_check_scheduler).

Документация: docs/temperature.md
"""

import os
import time
import threading

from core.tuya_temperature import read_all, is_configured
from core.temperature_store import get_store


def _poll_minutes():
    """Интервал опроса в минутах из env (по умолчанию 15). 0/некорректное => 0 (выкл)."""
    try:
        return max(0, int(os.getenv("TUYA_POLL_MINUTES", "15")))
    except (ValueError, TypeError):
        return 15


# Раз в сутки подчищаем историю старше N дней (защита от роста БД).
_PRUNE_KEEP_DAYS = 90
_PRUNE_EVERY_S = 86400

_started = False
_lock = threading.Lock()


def _poll_once(interval_s):
    """Один опрос: read_all -> save_readings. Исключения наружу не пускаем."""
    try:
        readings = read_all()
        saved = get_store().save_readings(readings, interval_s)
        ok = sum(1 for r in readings.values() if r.get("temperature") is not None)
        print(f"[TUYA] опрос: {ok}/{len(readings)} датчиков, записано строк: {saved}")
    except Exception as e:
        print(f"[TUYA] опрос не удался: {e}")


def _loop():
    interval_s = _poll_minutes() * 60
    last_prune = 0.0
    # Стартовый опрос — чтобы страница сразу показала данные, не дожидаясь интервала.
    _poll_once(interval_s)
    while True:
        try:
            time.sleep(interval_s)
            _poll_once(interval_s)
            now = time.time()
            if now - last_prune > _PRUNE_EVERY_S:
                try:
                    get_store().prune(keep_days=_PRUNE_KEEP_DAYS)
                except Exception as e:
                    print(f"[TUYA] prune не удался: {e}")
                last_prune = now
        except Exception as e:
            # Не даём исключению молча убить daemon-поток (иначе опрос встанет до рестарта).
            print(f"[TUYA] исключение в цикле опроса: {e}")
            time.sleep(60)


def start_scheduler():
    """Запустить daemon-поток опроса. Идемпотентно (один поток на процесс)."""
    global _started
    with _lock:
        if _started:
            return
        if not is_configured():
            print("[TUYA] TUYA_ACCESS_ID/SECRET не заданы — опрос температуры отключён")
            return
        minutes = _poll_minutes()
        if minutes <= 0:
            print("[TUYA] TUYA_POLL_MINUTES=0 — фоновый опрос температуры отключён")
            return
        t = threading.Thread(target=_loop, name="tuya-temperature-poller", daemon=True)
        t.start()
        _started = True
        print(f"[TUYA] опрос температуры стартовал, интервал {minutes} мин")
