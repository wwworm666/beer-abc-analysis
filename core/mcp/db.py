"""SQLite-хранилище MCP-платформы: mcp.db на постоянном диске.

Что лежит: статические токены, OAuth-клиенты, коды и токены, журнал вызовов,
настройки. Каждый модуль сам создаёт свои таблицы через ensure_schema() —
так модули токенов, OAuth и журнала пишутся независимо и не спорят за один DDL.

Почему SQLite, а не JSON: журнал растёт на каждый вызов агента и пишется из двух
gunicorn-воркеров одновременно; SQLite с WAL и busy_timeout даёт атомарные записи
между процессами (тот же приём, что core/auth_manager.py).

Путь: core.storage_paths.get_data_path('mcp.db') — /kultura/mcp.db в проде,
data/mcp.db локально. Тесты подменяют путь через set_db_path().

Транзакции:
- read()  — обычное соединение для чтения;
- write() — BEGIN IMMEDIATE на весь блок: проверка и запись атомарны между
  воркерами (например «код авторизации использован один раз»).
"""
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterable, Optional

from core.storage_paths import get_data_path

DB_FILE = 'mcp.db'
BUSY_TIMEOUT_MS = 5000   # сколько ждать чужой write-лок, прежде чем упасть

_path_override: Optional[str] = None
_schema_done = set()     # {(путь БД, имя схемы)} — DDL выполняется один раз на процесс
_schema_lock = threading.Lock()


def db_path() -> str:
    """Путь к mcp.db (подмена для тестов — set_db_path)."""
    return _path_override or get_data_path(DB_FILE)


def set_db_path(path: Optional[str]) -> None:
    """Тесты: работать с временным файлом. None — вернуть боевой путь."""
    global _path_override
    _path_override = path
    with _schema_lock:
        _schema_done.clear()


def _connect(autocommit: bool) -> sqlite3.Connection:
    path = db_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10,
                           isolation_level=None if autocommit else '')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute(f'PRAGMA busy_timeout={BUSY_TIMEOUT_MS}')
    conn.execute('PRAGMA synchronous=NORMAL')
    return conn


@contextmanager
def read():
    """Соединение для чтения."""
    conn = _connect(autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def write():
    """Соединение с немедленным write-локом на весь блок (BEGIN IMMEDIATE)."""
    conn = _connect(autocommit=True)
    try:
        conn.execute('BEGIN IMMEDIATE')
        try:
            yield conn
            conn.execute('COMMIT')
        except BaseException:
            conn.execute('ROLLBACK')
            raise
    finally:
        conn.close()


def ensure_schema(name: str, statements: Iterable[str]) -> None:
    """Выполнить DDL схемы `name` один раз на процесс и путь БД.

    statements — CREATE TABLE/INDEX IF NOT EXISTS; повторный вызов безопасен.
    """
    key = (db_path(), name)
    if key in _schema_done:
        return
    with _schema_lock:
        if key in _schema_done:
            return
        with write() as conn:
            for sql in statements:
                conn.execute(sql)
        _schema_done.add(key)
