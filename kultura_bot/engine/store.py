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
             output_tokens, cache_read, cache_write, cost_usd — для общего дневного предела
    meta     служебные пары ключ — значение (2026-11-06): хеш аватарки, которую сервер бота уже
             поставил в Telegram (avatar_sha256:<id бота>) — второй раз тот же файл не грузится
    user_usage расход по дням (МСК) и людям (2026-11-06, предел на человека): day + tg_user_id
             (PK), requests, cost_usd — вопросы человека, бот и агенты вместе; STATS_KEEP_DAYS дней.
             Сброс предела (settings.USER_BUDGET_RESET_AT, 2026-11-09) удаляет строки своих суток;
             что сброс уже сделан, помнит meta (user_budget_reset)
    job_stats  удачные работы для оценки «сколько осталось» (engine/progress.py, 2026-10-29):
             вид (answer | report), сколько шла работа, шагов модели, вызовов инструментов,
             расход; что обещал прогресс при первом показе (shown_eta, shown_at) — для точности;
             хранятся STATS_KEEP_DAYS дней
    tool_stats длительность каждого вызова инструмента — «обычно до N с» в прогрессе;
             STATS_KEEP_DAYS дней
    journal_outbox записи журнала вопросов и ответов, ещё не принятые сайтом (2026-11-06,
             engine/journal.py): uid (PK), payload (JSON записи), ts; не больше OUTBOX_MAX —
             сайт молчит дольше, старые уходят (в журнал сервера — предупреждение)
    sent     текст ответов, ушедших богатым сообщением (2026-11-06): chat_id + message_id (PK),
             text (Markdown ответа), ts — у богатого сообщения в Telegram нет поля text, а ответ
             на него (Reply или кнопка следующего шага) — продолжение той работы; SENT_KEEP_DAYS дней

Потоки: опрос Telegram и ответы в чатах пишут из разных потоков — одно соединение под
замком (WAL, автокоммит).
"""
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

MSK = timezone(timedelta(hours=3), 'МСК')     # в Москве нет перехода на летнее время с 2014 года
JOBS_KEEP_DAYS = 30
STATS_KEEP_DAYS = 90                # история для оценки времени: старая — уже не про нынешнюю скорость
STATS_RECENT = 50                   # столько последних работ вида берёт оценка
SENT_KEEP_DAYS = 30                 # текст ответов богатыми сообщениями — для ответа на них
OUTBOX_MAX = 2000                   # записей журнала ждут сайт — при ~50 вопросах в день это больше месяца
SENT_TEXT_MAX = 20000

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
    '''CREATE TABLE IF NOT EXISTS job_stats (
        job_id      INTEGER PRIMARY KEY,
        mode        TEXT NOT NULL,
        finished_ts REAL NOT NULL,
        seconds     REAL NOT NULL,
        steps       INTEGER NOT NULL DEFAULT 0,
        tool_calls  INTEGER NOT NULL DEFAULT 0,
        cost_usd    REAL NOT NULL DEFAULT 0,
        shown_eta   REAL,
        shown_at    REAL
    )''',
    'CREATE INDEX IF NOT EXISTS idx_job_stats_mode ON job_stats(mode, finished_ts)',
    '''CREATE TABLE IF NOT EXISTS tool_stats (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        name    TEXT NOT NULL,
        seconds REAL NOT NULL,
        ts      REAL NOT NULL
    )''',
    'CREATE INDEX IF NOT EXISTS idx_tool_stats_name ON tool_stats(name, ts)',
    '''CREATE TABLE IF NOT EXISTS user_usage (
        day        TEXT NOT NULL,
        tg_user_id TEXT NOT NULL,
        requests   INTEGER NOT NULL DEFAULT 0,
        cost_usd   REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (day, tg_user_id)
    )''',
    '''CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS journal_outbox (
        uid     TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        ts      REAL NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS sent (
        chat_id    TEXT NOT NULL,
        message_id INTEGER NOT NULL,
        text       TEXT NOT NULL,
        ts         REAL NOT NULL,
        PRIMARY KEY (chat_id, message_id)
    )''',
)


_TELEGRAM_CHAT_RE = re.compile(r'-?\d{1,21}')


def is_telegram_chat(chat_id: Any) -> bool:
    """Чат Telegram (число) — а не беседа страницы сайта web:<id> (2026-11-09)."""
    return bool(_TELEGRAM_CHAT_RE.fullmatch(str(chat_id or '')))


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

    # ---------------------------------------------------------------- журнал: ждут отправки на сайт

    def outbox_add(self, record: Dict[str, Any], now: Optional[float] = None) -> int:
        """Положить запись журнала; вернуть, сколько старых выброшено сверх OUTBOX_MAX."""
        now = time.time() if now is None else now
        with self._lock:
            self._conn.execute('INSERT OR REPLACE INTO journal_outbox (uid, payload, ts) VALUES (?, ?, ?)',
                               (record['uid'], json.dumps(record, ensure_ascii=False), now))
            extra = self._conn.execute('SELECT COUNT(*) FROM journal_outbox').fetchone()[0] - OUTBOX_MAX
            if extra > 0:
                self._conn.execute('DELETE FROM journal_outbox WHERE uid IN (SELECT uid FROM journal_outbox '
                                   'ORDER BY ts LIMIT ?)', (extra,))
            return max(extra, 0)

    def outbox_batch(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self._rows('SELECT payload FROM journal_outbox ORDER BY ts LIMIT ?', (int(limit),))
        out = []
        for row in rows:
            try:
                out.append(json.loads(row['payload']))
            except ValueError:
                continue
        return out

    def outbox_drop(self, uids) -> None:
        for uid in uids or []:
            self._exec('DELETE FROM journal_outbox WHERE uid = ?', (str(uid),))

    def outbox_count(self) -> int:
        return int(self._rows('SELECT COUNT(*) AS n FROM journal_outbox')[0]['n'])

    # ---------------------------------------------------------------- ответы богатыми сообщениями

    def save_sent(self, chat_id: str, message_id: int, text: str, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        self._exec('INSERT OR REPLACE INTO sent (chat_id, message_id, text, ts) VALUES (?, ?, ?, ?)',
                   (str(chat_id), int(message_id), (text or '')[:SENT_TEXT_MAX], now))
        self._exec('DELETE FROM sent WHERE ts < ?', (now - SENT_KEEP_DAYS * 86400,))

    def get_sent(self, chat_id: str, message_id: int) -> str:
        rows = self._rows('SELECT text FROM sent WHERE chat_id = ? AND message_id = ?', (str(chat_id), int(message_id)))
        return rows[0]['text'] if rows else ''

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

    def prune_dialogs(self, prefix: str, max_idle_s: float, now: Optional[float] = None) -> int:
        """Диалоги бесед сайта (web:…, 2026-11-09), простоявшие дольше max_idle_s: бот их уже не продолжит
        (после простоя диалог начинается заново, прошлые ответы беседы присылает сайт), а копились бы без конца."""
        now = time.time() if now is None else now
        return self._exec('DELETE FROM dialogs WHERE chat_id LIKE ? AND last_ts < ?',
                          (prefix + '%', now - max_idle_s)).rowcount

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

    # ---------------------------------------------------------------- время работ (прогресс)

    def add_job_stats(self, job_id: int, mode: str, seconds: float, *, steps: int, tool_calls: int,
                      cost_usd: float, shown_eta: Optional[float] = None, shown_at: Optional[float] = None,
                      tools: Optional[List[Any]] = None, now: Optional[float] = None) -> None:
        """Удачная работа (и длительности её вызовов инструментов) — в историю для оценки времени."""
        now = time.time() if now is None else now
        with self._lock:
            old = now - STATS_KEEP_DAYS * 86400
            self._conn.execute('DELETE FROM job_stats WHERE finished_ts < ?', (old,))
            self._conn.execute('DELETE FROM tool_stats WHERE ts < ?', (old,))
            self._conn.execute('INSERT OR REPLACE INTO job_stats (job_id, mode, finished_ts, seconds, steps, tool_calls, '
                               'cost_usd, shown_eta, shown_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                               (job_id, mode, now, float(seconds), int(steps), int(tool_calls), float(cost_usd),
                                shown_eta, shown_at))
            for name, secs in tools or []:
                self._conn.execute('INSERT INTO tool_stats (name, seconds, ts) VALUES (?, ?, ?)',
                                   (str(name), float(secs), now))

    def recent_durations(self, mode: str, limit: int = STATS_RECENT) -> List[float]:
        """Сколько шли последние удачные работы этого вида (секунды)."""
        return [r['seconds'] for r in self._rows('SELECT seconds FROM job_stats WHERE mode = ? '
                                                 'ORDER BY finished_ts DESC LIMIT ?', (mode, limit))]

    def tool_durations(self, per_tool: int = 200) -> Dict[str, List[float]]:
        """Длительности последних вызовов каждого инструмента (не больше per_tool на инструмент)."""
        out: Dict[str, List[float]] = {}
        for r in self._rows('SELECT name, seconds FROM tool_stats ORDER BY ts DESC'):
            bucket = out.setdefault(r['name'], [])
            if len(bucket) < per_tool:
                bucket.append(r['seconds'])
        return out

    def eta_accuracy(self, mode: str = 'report', last: int = 20, within_s: float = 60) -> Dict[str, int]:
        """У скольких из последних работ (где прогресс показывал «осталось») оценка ошиблась не больше
        чем на within_s секунд: {'n': всего, 'ok': точных}."""
        rows = self._rows('SELECT seconds, shown_eta, shown_at FROM job_stats WHERE mode = ? AND shown_eta IS NOT '
                          'NULL AND shown_at IS NOT NULL ORDER BY finished_ts DESC LIMIT ?', (mode, last))
        ok = sum(1 for r in rows if abs((r['seconds'] - r['shown_at']) - r['shown_eta']) <= within_s)
        return {'n': len(rows), 'ok': ok}

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

    def add_user_usage(self, tg_user_id: str, cost_usd: float, day: Optional[str] = None) -> None:
        """Шаг модели по вопросу этого человека (бот или его агент) — в расход человека за сутки."""
        day = day or msk_day()
        with self._lock:
            self._conn.execute('INSERT INTO user_usage (day, tg_user_id, requests, cost_usd) VALUES (?, ?, 1, ?) '
                               'ON CONFLICT(day, tg_user_id) DO UPDATE SET requests = requests + 1, '
                               'cost_usd = cost_usd + excluded.cost_usd', (day, str(tg_user_id), float(cost_usd)))
            old = (datetime.fromisoformat(day) - timedelta(days=STATS_KEEP_DAYS)).date().isoformat()
            self._conn.execute('DELETE FROM user_usage WHERE day < ?', (old,))

    def reset_user_usage(self, day: str) -> int:
        """Обнулить расход людей за сутки day (сброс предела, settings.USER_BUDGET_RESET_AT): сколько строк убрано.
        Общий расход (usage) не трогает — он идёт в отчёт сайту."""
        with self._lock:
            return self._conn.execute('DELETE FROM user_usage WHERE day = ?', (str(day),)).rowcount

    def spent_by(self, tg_user_id: str, day: Optional[str] = None) -> float:
        """Расход человека за сутки МСК (бот и агенты по его вопросам)."""
        rows = self._rows('SELECT cost_usd FROM user_usage WHERE day = ? AND tg_user_id = ?',
                          (day or msk_day(), str(tg_user_id)))
        return float(rows[0]['cost_usd']) if rows else 0.0

    def get_meta(self, key: str) -> Optional[str]:
        rows = self._rows('SELECT value FROM meta WHERE key = ?', (key,))
        return str(rows[0]['value']) if rows else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute('INSERT INTO meta (key, value) VALUES (?, ?) '
                               'ON CONFLICT(key) DO UPDATE SET value = excluded.value', (key, str(value)))

    def known_chats(self, limit: int = 500) -> List[str]:
        """Чаты, где бот уже работал (вопросы и диалоги): в них могут остаться старые меню."""
        rows = self._rows('SELECT chat_id FROM jobs UNION SELECT chat_id FROM dialogs LIMIT ?', (int(limit),))
        # Беседы страницы сайта (web:<id>, 2026-11-09) — не чаты Telegram: у них меню нет.
        return sorted({str(row['chat_id']) for row in rows if row['chat_id'] and is_telegram_chat(row['chat_id'])})
