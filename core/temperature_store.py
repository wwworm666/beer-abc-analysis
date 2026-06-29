"""Хранилище истории показаний температуры (SQLite).

Зачем БД, а не «живой» опрос: чтобы видеть динамику (спарклайн за сутки) и иметь
последнее известное значение, когда Tuya недоступна.

Дедуп под gunicorn --workers 2 БЕЗ lock-файлов: первичный ключ (bar_key, bucket_ts),
где bucket_ts — время, округлённое вниз до интервала опроса. Оба воркера опрашивают
независимо, но INSERT OR IGNORE на один и тот же бакет оставит ровно одну строку.
Это проще и надёжнее, чем atomic-lock-файлы (см. core/open_check_scheduler.py): даже
если у одного воркера запрос к Tuya упал, значение запишет другой.

Путь к БД: /kultura/temperature.db на проде (persistent volume), data/temperature.db
локально. Зеркалит логику core/shifts_manager.py. Файл в .gitignore (data/*.db).

Документация: docs/temperature.md
"""

import os
import time
import sqlite3
import threading
from contextlib import contextmanager


def _default_db_path():
    """Путь к БД: persistent volume на проде, иначе локальная папка data/."""
    if os.path.exists("/kultura"):
        return "/kultura/temperature.db"
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "temperature.db")


class TemperatureStore:
    """Потокобезопасный доступ к истории показаний."""

    def __init__(self, db_path=None):
        self.db_path = db_path or _default_db_path()
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            # WAL + busy_timeout: два воркера пишут одновременно (см. shifts_manager).
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    bar_key     TEXT    NOT NULL,
                    bucket_ts   INTEGER NOT NULL,   -- unix-сек, округлённый вниз до интервала
                    ts          INTEGER NOT NULL,   -- время сэмпла (опроса), unix-сек
                    device_id   TEXT,
                    temperature REAL,               -- C
                    humidity    REAL,               -- %
                    battery     INTEGER,            -- %
                    online      INTEGER,            -- 1/0/NULL
                    PRIMARY KEY (bar_key, bucket_ts)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_readings_bar_ts ON readings (bar_key, ts)"
            )
            # Состояние тревоги по высокой температуре (антиспам + дедуп под 2 воркера).
            # alarming: 1 — бар сейчас «в тревоге» (выше порога), 0 — норма.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alarm_state (
                    bar_key    TEXT PRIMARY KEY,
                    alarming   INTEGER NOT NULL DEFAULT 0,
                    changed_ts INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def save_readings(self, readings, interval_s, sample_ts=None):
        """Сохранить пачку показаний (out из tuya_temperature.read_all()) как сэмпл истории.

        Бакетируем по ВРЕМЕНИ ОПРОСА (wall-clock), а НЕ по update_time устройства:
        датчики Tuya шлют данные по изменению, и при стабильной температуре их update_time
        стоит часами — бакетирование по нему оставляло бы историю почти пустой (1-2 точки
        за неделю). Сэмпл на каждый опрос (раз в interval_s) даёт ровный лог последнего
        известного значения — то, что нужно для графика истории.

        bucket_ts = floor(sample_ts / interval_s) * interval_s; PRIMARY KEY
        (bar_key, bucket_ts) + INSERT OR IGNORE дедупит два воркера в одном окне.
        Пишем только показания с числовой температурой (ошибочные/пустые — пропускаем).
        """
        interval_s = max(1, int(interval_s))
        now = int(sample_ts if sample_ts is not None else time.time())
        bucket_ts = (now // interval_s) * interval_s
        rows = []
        for bar_key, r in (readings or {}).items():
            if r.get("temperature") is None:
                continue
            online = r.get("online")
            rows.append((
                bar_key,
                bucket_ts,
                now,
                r.get("device_id"),
                r.get("temperature"),
                r.get("humidity"),
                r.get("battery"),
                (1 if online else 0) if online is not None else None,
            ))
        if not rows:
            return 0
        with self._lock, self._conn() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO readings
                    (bar_key, bucket_ts, ts, device_id, temperature, humidity, battery, online)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            return conn.total_changes

    def set_alarm_state(self, bar_key, alarming) -> bool:
        """Атомарно выставить состояние тревоги по бару.

        Возвращает True, ТОЛЬКО если этот вызов реально изменил состояние (переход
        0->1 или 1->0). Под gunicorn --workers 2 оба воркера зовут этот метод, но
        SQLite сериализует запись: `UPDATE ... WHERE alarming != target` поменяет
        строку лишь у одного (rowcount==1), второй увидит уже выставленное (rowcount==0).
        Так тревогу/возврат шлёт ровно один воркер — без lock-файлов.
        """
        target = 1 if alarming else 0
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO alarm_state (bar_key, alarming, changed_ts) VALUES (?, 0, 0)",
                (bar_key,),
            )
            cur = conn.execute(
                "UPDATE alarm_state SET alarming=?, changed_ts=? WHERE bar_key=? AND alarming!=?",
                (target, int(time.time()), bar_key, target),
            )
            conn.commit()
            return cur.rowcount == 1

    def latest(self):
        """Последнее показание по каждому бару: {bar_key: {ts, temperature, humidity, battery, online}}."""
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT r.bar_key, r.ts, r.temperature, r.humidity, r.battery, r.online
                FROM readings r
                JOIN (
                    SELECT bar_key, MAX(ts) AS mx FROM readings GROUP BY bar_key
                ) m ON m.bar_key = r.bar_key AND m.mx = r.ts
                """
            )
            out = {}
            for row in cur.fetchall():
                out[row["bar_key"]] = {
                    "ts": row["ts"],
                    "temperature": row["temperature"],
                    "humidity": row["humidity"],
                    "battery": row["battery"],
                    "online": row["online"],
                }
            return out

    def history(self, hours=24, since_ts=None):
        """Точки за период для спарклайна: {bar_key: [{ts, temperature, humidity}, ...]} по возрастанию ts.

        hours используется, если since_ts не задан. since_ts — unix-сек нижней границы.
        """
        import time as _time
        if since_ts is None:
            since_ts = int(_time.time()) - int(hours) * 3600
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT bar_key, ts, temperature, humidity
                FROM readings
                WHERE ts >= ?
                ORDER BY bar_key, ts
                """,
                (int(since_ts),),
            )
            out = {}
            for row in cur.fetchall():
                out.setdefault(row["bar_key"], []).append({
                    "ts": row["ts"],
                    "temperature": row["temperature"],
                    "humidity": row["humidity"],
                })
            return out

    def prune(self, keep_days=90):
        """Удалить показания старше keep_days (защита от безграничного роста БД)."""
        import time as _time
        cutoff = int(_time.time()) - int(keep_days) * 86400
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM readings WHERE ts < ?", (cutoff,))
            conn.commit()


# Синглтон процесса (как shifts_mgr в extensions.py).
_STORE = None
_STORE_LOCK = threading.Lock()


def get_store():
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = TemperatureStore()
    return _STORE
