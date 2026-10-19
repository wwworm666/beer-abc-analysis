"""Своя база сервера бота (SQLite): диалоги, вопросы, расход.

Файл — $KULTURA_BOT_DATA/bot.db (на сервере /var/lib/kultura-bot/bot.db). Сайт её не
видит: история разговоров остаётся на сервере бота; на страницу «Доступ агентов» уходят
только состояние и расход (отчёт /api/bot/report).

Таблицы:

    dialogs  текущий диалог чата: chat_id (PK), fingerprint (инструкции и инструменты, с
             которыми он начат), started_at, last_ts, turns, messages — история Messages
             API как есть (JSON): Claude принимает её назад только без правок
    jobs     вопросы: id, chat_id, tg_user_id, started_ts (когда пришёл), finished_ts,
             status (queued — ждёт очереди чата | running | done | error | interrupted),
             error; хранятся JOBS_KEEP_DAYS дней
    usage    расход по дням (МСК) и моделям: day + model (PK), requests, input_tokens,
             output_tokens, cache_read, cache_write, cost_usd — для дневного предела

Потоки: опрос Telegram и ответы в чатах пишут из разных потоков — одно соединение под
замком (WAL, автокоммит).
"""
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

MSK = timezone(timedelta(hours=3), 'МСК')     # в Москве нет перехода на летнее время с 2014 года
JOBS_KEEP_DAYS = 30

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS dialogs (
        chat_id     TEXT PRIMARY KEY,
        fingerprint TEXT NOT NULL,
        started_at  TEXT NOT NULL,
        last_ts     REAL NOT NULL,
        turns       INTEGER NOT NULL DEFAULT 0,
        messages    TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS jobs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id     TEXT NOT NULL,
        tg_user_id  TEXT NOT NULL DEFAULT '',
        started_ts  REAL NOT NULL,
        finished_ts REAL,
        status      TEXT NOT NULL,
        error       TEXT NOT NULL DEFAULT ''
    )''',
    'CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, started_ts)',
    '''CREATE TABLE IF NOT EXISTS usage (
        day           TEXT NOT NULL,
        model         TEXT NOT NULL,
        requests      INTEGER NOT NULL DEFAULT 0,
        input_tokens  INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        cache_read    INTEGER NOT NULL DEFAULT 0,
        cache_write   INTEGER NOT NULL DEFAULT 0,
        cost_usd      REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (day, model)
    )''',
)


def msk_now() -> datetime:
    return datetime.now(MSK)


def msk_day(now: Optional[datetime] = None) -> str:
    return (now or msk_now()).date().isoformat()


class Store:
    def __init__(self, path: str):
        self.path = path
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute('PRAGMA journal_mode=WAL')
            for statement in SCHEMA:
                self._conn.execute(statement)

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _rows(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------------------------------------------------------- диалоги

    def get_dialog(self, chat_id: str) -> Optional[Dict[str, Any]]:
        rows = self._rows('SELECT * FROM dialogs WHERE chat_id = ?', (str(chat_id),))
        if not rows:
            return None
        dialog = rows[0]
        dialog['messages'] = json.loads(dialog['messages'])
        return dialog

    def save_dialog(self, chat_id: str, fingerprint: str, started_at: str, messages: List[Dict[str, Any]],
                    turns: int, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        self._exec('INSERT INTO dialogs (chat_id, fingerprint, started_at, last_ts, turns, messages) '
                   'VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(chat_id) DO UPDATE SET fingerprint=excluded.fingerprint, '
                   'started_at=excluded.started_at, last_ts=excluded.last_ts, turns=excluded.turns, '
                   'messages=excluded.messages',
                   (str(chat_id), fingerprint, started_at, now, turns, json.dumps(messages, ensure_ascii=False)))

    def delete_dialog(self, chat_id: str) -> bool:
        return self._exec('DELETE FROM dialogs WHERE chat_id = ?', (str(chat_id),)).rowcount > 0

    # ---------------------------------------------------------------- вопросы

    def start_job(self, chat_id: str, tg_user_id: str = '', now: Optional[float] = None,
                  status: str = 'running') -> int:
        """Записать вопрос: 'queued' — пришёл и ждёт очереди чата, 'running' — ответ начат."""
        now = time.time() if now is None else now
        with self._lock:
            self._conn.execute('DELETE FROM jobs WHERE started_ts < ?', (now - JOBS_KEEP_DAYS * 86400,))
            return self._conn.execute('INSERT INTO jobs (chat_id, tg_user_id, started_ts, status) VALUES (?, ?, ?, ?)',
                                      (str(chat_id), str(tg_user_id), now, status)).lastrowid

    def run_job(self, job_id: int) -> None:
        """Вопрос из очереди взят в работу: 'queued' -> 'running'."""
        self._exec("UPDATE jobs SET status = 'running' WHERE id = ? AND status = 'queued'", (job_id,))

    def finish_job(self, job_id: int, status: str, error: str = '', now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        self._exec('UPDATE jobs SET status = ?, error = ?, finished_ts = ? WHERE id = ?',
                   (status, (error or '')[:500], now, job_id))

    def take_interrupted_jobs(self, max_age_s: float, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Вопросы, оборванные остановкой сервера, — в работе и ждавшие очереди: 'running' и
        'queued' -> 'interrupted'. Вернуть свежие (моложе max_age_s): их чатам бот скажет,
        что ответ прервался."""
        now = time.time() if now is None else now
        with self._lock:
            rows = [dict(r) for r in self._conn.execute(
                "SELECT * FROM jobs WHERE status IN ('running', 'queued')").fetchall()]
            self._conn.execute("UPDATE jobs SET status = 'interrupted', finished_ts = ? "
                               "WHERE status IN ('running', 'queued')", (now,))
        return [r for r in rows if now - r['started_ts'] <= max_age_s]

    def recent_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._rows('SELECT * FROM jobs ORDER BY id DESC LIMIT ?', (limit,))

    # ---------------------------------------------------------------- расход

    def add_usage(self, model: str, usage: Dict[str, int], cost_usd: float, day: Optional[str] = None) -> None:
        self._exec('INSERT INTO usage (day, model, requests, input_tokens, output_tokens, cache_read, cache_write, '
                   'cost_usd) VALUES (?, ?, 1, ?, ?, ?, ?, ?) ON CONFLICT(day, model) DO UPDATE SET '
                   'requests = requests + 1, input_tokens = input_tokens + excluded.input_tokens, '
                   'output_tokens = output_tokens + excluded.output_tokens, '
                   'cache_read = cache_read + excluded.cache_read, cache_write = cache_write + excluded.cache_write, '
                   'cost_usd = cost_usd + excluded.cost_usd',
                   (day or msk_day(), model or '', int(usage.get('input_tokens', 0)), int(usage.get('output_tokens', 0)),
                    int(usage.get('cache_read_input_tokens', 0)), int(usage.get('cache_creation_input_tokens', 0)),
                    float(cost_usd)))

    def spent_on(self, day: Optional[str] = None) -> float:
        rows = self._rows('SELECT COALESCE(SUM(cost_usd), 0) AS total FROM usage WHERE day = ?', (day or msk_day(),))
        return float(rows[0]['total'] or 0)
