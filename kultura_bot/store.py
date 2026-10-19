"""Память бота в mcp.db: привязки Telegram, диалоги, задания, расход, состояние.

Почему mcp.db: это база ИИ-агентов сайта (core/mcp/db.py — WAL, атомарные записи из
обоих gunicorn-воркеров), в ней же настройки и журнал вызовов инструментов.

Таблицы:

    bot_links       кто может говорить с ботом: tg_user_id (PK) -> администратор сайта
                    (user_id, login), tg_name — имя в Telegram, linked_at, linked_by
    bot_link_codes  одноразовые коды привязки (/start <код>): code (PK), user_id, login,
                    created_ts, expires_ts; срок — LINK_CODE_TTL_S, использованный удаляется
    bot_dialogs     текущий диалог чата: chat_id (PK), fingerprint (инструкции и инструменты,
                    с которыми он начат), started_at, last_ts, turns, messages — история
                    Messages API как есть (JSON): Claude принимает её назад только без правок
    bot_jobs        вопросы: id, chat_id, tg_user_id, started_ts (когда пришёл), finished_ts,
                    status (queued — ждёт очереди чата | running | done | error | interrupted),
                    error
    bot_usage       расход по дням и моделям: day + model (PK), requests, input_tokens,
                    output_tokens, cache_read, cache_write, cost_usd

Состояние бота для страницы «Доступ агентов» — ключ kultura_bot_status в settings
(JSON): опрос Telegram идёт в одном воркере, а страницу может открыть другой.
"""
import json
import time
from typing import Any, Dict, List, Optional

from core import msk_time
from core.mcp import db

LINK_CODE_TTL_S = 15 * 60          # ссылка «Подключить Telegram» живёт 15 минут
JOBS_KEEP_DAYS = 30                # история заданий для разбора сбоев
STATUS_KEY = 'kultura_bot_status'

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS bot_links (
        tg_user_id TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL,
        login      TEXT NOT NULL,
        tg_name    TEXT NOT NULL DEFAULT '',
        linked_at  TEXT NOT NULL,
        linked_by  TEXT NOT NULL DEFAULT ''
    )''',
    '''CREATE TABLE IF NOT EXISTS bot_link_codes (
        code       TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL,
        login      TEXT NOT NULL,
        created_ts REAL NOT NULL,
        expires_ts REAL NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS bot_dialogs (
        chat_id     TEXT PRIMARY KEY,
        fingerprint TEXT NOT NULL,
        started_at  TEXT NOT NULL,
        last_ts     REAL NOT NULL,
        turns       INTEGER NOT NULL DEFAULT 0,
        messages    TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS bot_jobs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id     TEXT NOT NULL,
        tg_user_id  TEXT NOT NULL DEFAULT '',
        started_ts  REAL NOT NULL,
        finished_ts REAL,
        status      TEXT NOT NULL,
        error       TEXT NOT NULL DEFAULT ''
    )''',
    'CREATE INDEX IF NOT EXISTS idx_bot_jobs_status ON bot_jobs(status, started_ts)',
    '''CREATE TABLE IF NOT EXISTS bot_usage (
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


def _ensure() -> None:
    db.ensure_schema('kultura_bot', SCHEMA)


def _now_iso() -> str:
    return msk_time.now().isoformat(timespec='seconds')


# ------------------------------------------------------------------ привязки

def add_link_code(code: str, user_id: int, login: str, now: Optional[float] = None) -> float:
    """Записать код привязки; вернуть срок (ts). Просроченные коды вычищаются."""
    _ensure()
    now = time.time() if now is None else now
    expires = now + LINK_CODE_TTL_S
    with db.write() as conn:
        conn.execute('DELETE FROM bot_link_codes WHERE expires_ts <= ?', (now,))
        conn.execute('INSERT INTO bot_link_codes (code, user_id, login, created_ts, expires_ts) VALUES (?, ?, ?, ?, ?)',
                     (code, user_id, login, now, expires))
    return expires


def take_link_code(code: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Забрать код (одноразово): запись или None — нет такого или истёк."""
    _ensure()
    now = time.time() if now is None else now
    with db.write() as conn:
        row = conn.execute('SELECT * FROM bot_link_codes WHERE code = ?', (code,)).fetchone()
        conn.execute('DELETE FROM bot_link_codes WHERE code = ? OR expires_ts <= ?', (code, now))
    if row is None or row['expires_ts'] <= now:
        return None
    return dict(row)


def save_link(tg_user_id: str, user_id: int, login: str, tg_name: str = '', by: str = '') -> None:
    _ensure()
    with db.write() as conn:
        conn.execute('INSERT INTO bot_links (tg_user_id, user_id, login, tg_name, linked_at, linked_by) '
                     'VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(tg_user_id) DO UPDATE SET user_id=excluded.user_id, '
                     'login=excluded.login, tg_name=excluded.tg_name, linked_at=excluded.linked_at, '
                     'linked_by=excluded.linked_by',
                     (str(tg_user_id), int(user_id), login, tg_name[:100], _now_iso(), by))


def get_link(tg_user_id: str) -> Optional[Dict[str, Any]]:
    _ensure()
    with db.read() as conn:
        row = conn.execute('SELECT * FROM bot_links WHERE tg_user_id = ?', (str(tg_user_id),)).fetchone()
    return dict(row) if row else None


def list_links() -> List[Dict[str, Any]]:
    _ensure()
    with db.read() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM bot_links ORDER BY linked_at')]


def delete_link(tg_user_id: str) -> bool:
    _ensure()
    with db.write() as conn:
        return conn.execute('DELETE FROM bot_links WHERE tg_user_id = ?', (str(tg_user_id),)).rowcount > 0


def delete_links_for_user(user_id: int) -> int:
    """Снять все привязки Telegram администратора (отключение, снятие админства, удаление)."""
    _ensure()
    with db.write() as conn:
        conn.execute('DELETE FROM bot_link_codes WHERE user_id = ?', (int(user_id),))
        return conn.execute('DELETE FROM bot_links WHERE user_id = ?', (int(user_id),)).rowcount


# ------------------------------------------------------------------ диалоги

def get_dialog(chat_id: str) -> Optional[Dict[str, Any]]:
    _ensure()
    with db.read() as conn:
        row = conn.execute('SELECT * FROM bot_dialogs WHERE chat_id = ?', (str(chat_id),)).fetchone()
    if row is None:
        return None
    dialog = dict(row)
    dialog['messages'] = json.loads(dialog['messages'])
    return dialog


def save_dialog(chat_id: str, fingerprint: str, started_at: str, messages: List[Dict[str, Any]],
                turns: int, now: Optional[float] = None) -> None:
    _ensure()
    now = time.time() if now is None else now
    payload = json.dumps(messages, ensure_ascii=False)
    with db.write() as conn:
        conn.execute('INSERT INTO bot_dialogs (chat_id, fingerprint, started_at, last_ts, turns, messages) '
                     'VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(chat_id) DO UPDATE SET fingerprint=excluded.fingerprint, '
                     'started_at=excluded.started_at, last_ts=excluded.last_ts, turns=excluded.turns, '
                     'messages=excluded.messages',
                     (str(chat_id), fingerprint, started_at, now, turns, payload))


def delete_dialog(chat_id: str) -> bool:
    _ensure()
    with db.write() as conn:
        return conn.execute('DELETE FROM bot_dialogs WHERE chat_id = ?', (str(chat_id),)).rowcount > 0


# ------------------------------------------------------------------ задания

def start_job(chat_id: str, tg_user_id: str = '', now: Optional[float] = None, status: str = 'running') -> int:
    """Записать вопрос: 'queued' — пришёл и ждёт очереди чата, 'running' — ответ начат."""
    _ensure()
    now = time.time() if now is None else now
    with db.write() as conn:
        conn.execute('DELETE FROM bot_jobs WHERE started_ts < ?', (now - JOBS_KEEP_DAYS * 86400,))
        return conn.execute('INSERT INTO bot_jobs (chat_id, tg_user_id, started_ts, status) VALUES (?, ?, ?, ?)',
                            (str(chat_id), str(tg_user_id), now, status)).lastrowid


def run_job(job_id: int) -> None:
    """Вопрос из очереди взят в работу: 'queued' -> 'running'."""
    _ensure()
    with db.write() as conn:
        conn.execute("UPDATE bot_jobs SET status = 'running' WHERE id = ? AND status = 'queued'", (job_id,))


def finish_job(job_id: int, status: str, error: str = '', now: Optional[float] = None) -> None:
    _ensure()
    now = time.time() if now is None else now
    with db.write() as conn:
        conn.execute('UPDATE bot_jobs SET status = ?, error = ?, finished_ts = ? WHERE id = ?',
                     (status, (error or '')[:500], now, job_id))


def take_interrupted_jobs(max_age_s: float, now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Вопросы, оборванные перезапуском процесса — в работе и ждавшие очереди:
    'running' и 'queued' -> 'interrupted'. Вернуть свежие (моложе max_age_s) — их чатам бот
    скажет, что ответ прервался."""
    _ensure()
    now = time.time() if now is None else now
    with db.write() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM bot_jobs WHERE status IN ('running', 'queued')")]
        conn.execute("UPDATE bot_jobs SET status = 'interrupted', finished_ts = ? "
                     "WHERE status IN ('running', 'queued')", (now,))
    return [r for r in rows if now - r['started_ts'] <= max_age_s]


def recent_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    _ensure()
    with db.read() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM bot_jobs ORDER BY id DESC LIMIT ?', (limit,))]


# ------------------------------------------------------------------ расход

def add_usage(model: str, usage: Dict[str, int], cost_usd: float, day: Optional[str] = None) -> None:
    _ensure()
    day = day or msk_time.now().date().isoformat()
    with db.write() as conn:
        conn.execute('INSERT INTO bot_usage (day, model, requests, input_tokens, output_tokens, cache_read, '
                     'cache_write, cost_usd) VALUES (?, ?, 1, ?, ?, ?, ?, ?) ON CONFLICT(day, model) DO UPDATE SET '
                     'requests = requests + 1, input_tokens = input_tokens + excluded.input_tokens, '
                     'output_tokens = output_tokens + excluded.output_tokens, '
                     'cache_read = cache_read + excluded.cache_read, cache_write = cache_write + excluded.cache_write, '
                     'cost_usd = cost_usd + excluded.cost_usd',
                     (day, model or '', int(usage.get('input_tokens', 0)), int(usage.get('output_tokens', 0)),
                      int(usage.get('cache_read_input_tokens', 0)), int(usage.get('cache_creation_input_tokens', 0)),
                      float(cost_usd)))


def spent_on(day: Optional[str] = None) -> float:
    _ensure()
    day = day or msk_time.now().date().isoformat()
    with db.read() as conn:
        row = conn.execute('SELECT COALESCE(SUM(cost_usd), 0) AS s FROM bot_usage WHERE day = ?', (day,)).fetchone()
    return float(row['s'])


def usage_summary(days: int = 30) -> Dict[str, Any]:
    """Расход за сегодня и за days дней: запросы, токены, доллары (для страницы)."""
    _ensure()
    today = msk_time.now().date()
    since = (today.toordinal() - days + 1)
    from datetime import date
    since_day = date.fromordinal(since).isoformat()
    with db.read() as conn:
        rows = [dict(r) for r in conn.execute('SELECT * FROM bot_usage WHERE day >= ? ORDER BY day', (since_day,))]

    def total(items):
        keys = ('requests', 'input_tokens', 'output_tokens', 'cache_read', 'cache_write')
        out = {k: sum(int(r[k]) for r in items) for k in keys}
        out['cost_usd'] = round(sum(float(r['cost_usd']) for r in items), 2)
        return out

    return {'today': total([r for r in rows if r['day'] == today.isoformat()]),
            'period': total(rows), 'days': days}


# ------------------------------------------------------------------ состояние для страницы

def set_status(state: str, detail: str = '', **extra: Any) -> None:
    """Состояние бота (running, waiting, conflict, error, stopped) — пишет поток опроса."""
    from core.mcp import settings
    value = dict({'state': state, 'detail': detail[:500], 'at': _now_iso(), 'at_ts': time.time()}, **extra)
    try:
        settings.set(STATUS_KEY, value, by='kultura_bot')
    except Exception:  # noqa: BLE001 — состояние не должно ронять бота
        pass


def get_status() -> Dict[str, Any]:
    from core.mcp import settings
    value = settings.get(STATUS_KEY)
    return value if isinstance(value, dict) else {'state': 'stopped', 'detail': '', 'at': '', 'at_ts': 0}
