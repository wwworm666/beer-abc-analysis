"""Журнал вызовов MCP-инструментов: кто, чем, с какими аргументами и что получилось.

Зачем: агент работает от имени владельца и может менять данные. Журнал отвечает
на вопросы «что агент сделал ночью», «почему в плане появился материал», «какой
инструмент падает». Смотрится на странице «Доступ агентов» и инструментом
common_audit_recent.

Таблица audit (mcp.db):
    id            автонумер
    at            момент вызова, МСК ISO ('2026-09-27T16:40:00+03:00')
    user_login    владелец токена (логин аккаунта сайта)
    token_id      'st_…' статический токен или 'oa_…' OAuth
    client_name   имя токена или OAuth-клиента («Claude», «ноутбук»)
    connector     домен коннектора ('content', 'stocks', …) или 'all' для /mcp; не полный
                  режим — через «/»: 'content/read', 'all/draft'
    tool          имя инструмента (кривое имя — обрезанным до TOOL_CHARS)
    args_preview  JSON аргументов, не длиннее ARGS_PREVIEW_CHARS символов; строки
                  длиннее LONG_STRING_CHARS заменены на «<строка N симв.>» — так в
                  журнал не попадают base64 файлов и длинные тексты
    status        'ok' | 'error' | 'denied' (отказ до исполнения: чужой коннектор,
                  неизвестный инструмент, запрет режима, лимиты частоты и занятости)
    http_status   код ответа маршрута (для инструментов-обработчиков — пусто)
    duration_ms   длительность исполнения
    result_chars  длина текста результата
    error_preview начало текста ошибки (не длиннее ERROR_PREVIEW_CHARS)

Хранение (проверка безопасности 2026-09-28): отказы ('denied') и настоящие вызовы
хранятся раздельно, чтобы поток отказов не вытеснил историю действий агента:
- 'denied' — последние KEEP_DENIED_ROWS записей;
- 'ok' и 'error' — последние KEEP_ROWS записей, но записи моложе KEEP_MIN_DAYS дней
  чистка по количеству не удаляет никогда (история за полгода цела при любом потоке).
Чистка — при каждой CLEANUP_EVERY-й вставке (по номеру записи, а не по счётчику
процесса: так правило одно на оба gunicorn-воркера и не зависит от перезапусков).
Длины полей ограничены (FIELD_LIMITS, ARGS_PREVIEW_CHARS, ERROR_PREVIEW_CHARS): в
журнал попадает пользовательский ввод, и одна запись не должна весить мегабайты.
"""
import json
from datetime import timedelta
from typing import Any, Dict, List, Optional

from core import msk_time
from core.mcp import db

KEEP_ROWS = 50000           # ok/error: ~ полгода активной работы нескольких агентов; строка ~0,5 КБ -> ~25 МБ
KEEP_DENIED_ROWS = 5000     # denied: отказам хватит недели разбора, остальное — шум
KEEP_MIN_DAYS = 180         # ok/error моложе полугода чистка по количеству не трогает
CLEANUP_EVERY = 1000        # раз во сколько вставок чистить хвосты
TOOL_CHARS = 64             # как spec.TOOL_NAME_RE: длиннее имя инструмента не бывает
FIELD_LIMITS = {'user_login': 64, 'token_id': 64, 'client_name': 100, 'connector': 32, 'tool': TOOL_CHARS}
ARGS_PREVIEW_CHARS = 2000   # предел превью аргументов (контракт 4.5)
LONG_STRING_CHARS = 300     # строки длиннее — заменяются описанием длины
ERROR_PREVIEW_CHARS = 500   # сколько текста ошибки хранить
MAX_RECENT = 1000           # больше за один запрос страница и агент не просят
STATUSES = ('ok', 'error', 'denied')

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS audit (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        at            TEXT NOT NULL,
        user_login    TEXT NOT NULL DEFAULT '',
        token_id      TEXT NOT NULL DEFAULT '',
        client_name   TEXT NOT NULL DEFAULT '',
        connector     TEXT NOT NULL DEFAULT '',
        tool          TEXT NOT NULL DEFAULT '',
        args_preview  TEXT NOT NULL DEFAULT '',
        status        TEXT NOT NULL,
        http_status   INTEGER,
        duration_ms   INTEGER,
        result_chars  INTEGER,
        error_preview TEXT NOT NULL DEFAULT ''
    )''',
    'CREATE INDEX IF NOT EXISTS idx_audit_tool ON audit(tool)',
    'CREATE INDEX IF NOT EXISTS idx_audit_status ON audit(status)',
    'CREATE INDEX IF NOT EXISTS idx_audit_token ON audit(token_id)',
)


def _ensure() -> None:
    db.ensure_schema('audit', SCHEMA)


def _shrink(value: Any) -> Any:
    """Длинные строки -> «<строка N симв.>» (рекурсивно по спискам и объектам)."""
    if isinstance(value, str):
        return value if len(value) <= LONG_STRING_CHARS else f'<строка {len(value)} симв.>'
    if isinstance(value, dict):
        return {str(k): _shrink(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_shrink(v) for v in value]
    return value


def args_preview(args: Any) -> str:
    """Превью аргументов для журнала (правила — в докстринге модуля)."""
    try:
        text = json.dumps(_shrink(args if args is not None else {}), ensure_ascii=False,
                          separators=(',', ':'), default=str)
    except (TypeError, ValueError):
        text = str(args)
    if len(text) > ARGS_PREVIEW_CHARS:
        text = text[:ARGS_PREVIEW_CHARS - 1] + '…'
    return text


def record(*, user_login: str = '', token_id: str = '', client_name: str = '', connector: str = '',
           tool: str = '', args: Any = None, status: str = 'ok', http_status: Optional[int] = None,
           duration_ms: Optional[int] = None, result_chars: Optional[int] = None,
           error: str = '') -> int:
    """Записать вызов. Возвращает id записи.

    Ошибка записи журнала не должна ронять ответ агенту — вызывающий код
    (protocol.py) оборачивает вызов и пишет сбой в лог.
    """
    if status not in STATUSES:
        raise ValueError(f'Неизвестный статус журнала: {status}')
    _ensure()
    fields = {'user_login': user_login, 'token_id': token_id, 'client_name': client_name,
              'connector': connector, 'tool': tool}
    clipped = {k: str(v or '')[:FIELD_LIMITS[k]] for k, v in fields.items()}
    now = msk_time.now()
    row = (now.isoformat(timespec='seconds'), clipped['user_login'], clipped['token_id'],
           clipped['client_name'], clipped['connector'], clipped['tool'], args_preview(args), status,
           http_status, duration_ms, result_chars, str(error or '')[:ERROR_PREVIEW_CHARS])
    with db.write() as conn:
        cur = conn.execute(
            'INSERT INTO audit (at, user_login, token_id, client_name, connector, tool, args_preview, '
            'status, http_status, duration_ms, result_chars, error_preview) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', row)
        new_id = cur.lastrowid
        if new_id % CLEANUP_EVERY == 0:
            _cleanup(conn, now)
    return new_id


def _cleanup(conn, now) -> None:
    """Чистка хвостов (правила — в докстринге модуля). Вызывается внутри транзакции записи."""
    row = conn.execute("SELECT id FROM audit WHERE status='denied' ORDER BY id DESC LIMIT 1 OFFSET ?",
                       (KEEP_DENIED_ROWS - 1,)).fetchone()
    if row is not None:
        conn.execute("DELETE FROM audit WHERE status='denied' AND id < ?", (row['id'],))
    row = conn.execute("SELECT id FROM audit WHERE status IN ('ok', 'error') ORDER BY id DESC LIMIT 1 OFFSET ?",
                       (KEEP_ROWS - 1,)).fetchone()
    if row is not None:
        cutoff = (now - timedelta(days=KEEP_MIN_DAYS)).isoformat(timespec='seconds')
        conn.execute("DELETE FROM audit WHERE status IN ('ok', 'error') AND id < ? AND at < ?",
                     (row['id'], cutoff))


def recent(limit: int = 100, tool: Optional[str] = None, status: Optional[str] = None,
           token_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Последние записи, новые сверху. tool — точное имя инструмента; status — из STATUSES;
    token_id — только вызовы этого токена (агенту по умолчанию видны лишь свои вызовы)."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 100
    limit = max(1, min(limit, MAX_RECENT))
    where, params = [], []
    if tool:
        where.append('tool = ?')
        params.append(tool)
    if status:
        if status not in STATUSES:
            raise ValueError(f'Статус — один из: {", ".join(STATUSES)}')
        where.append('status = ?')
        params.append(status)
    if token_id:
        where.append('token_id = ?')
        params.append(token_id)
    sql = 'SELECT * FROM audit'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY id DESC LIMIT ?'
    params.append(limit)
    _ensure()
    with db.read() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

