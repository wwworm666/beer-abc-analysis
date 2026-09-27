"""Настройки MCP-платформы: таблица settings в mcp.db, значения — JSON.

Правит их владелец на странице «Доступ агентов» (/admin/mcp, раздел «Настройки»).
Хранить в mcp.db, а не в .env: настройки меняются без передеплоя, и их видят оба
gunicorn-воркера сразу (SQLite общий, кэша в памяти нет — чтение дешёвое).

Известные ключи (проверяются при записи, см. KNOWN):
    notify_chat_id        str        чат Telegram для отчётов агентов (инструмент
                                     common_notify_owner). '' — не настроено.
                                     Формат chat_id Telegram: целое, у групп
                                     отрицательное ('670033096', '-1001234567890').
    oauth_redirect_hosts  list[str]  хосты, на которые OAuth может вернуть код
                                     авторизации (core/mcp/oauth.py). По умолчанию
                                     приложения Claude и локальные адреса для Claude Code.
Неизвестные ключи сохраняются как есть (любой JSON) — задел для новых модулей.

get(key, default): сохранённое значение; если его нет — default, а если и он не
задан — умолчание из DEFAULTS (для неизвестного ключа — None).
"""
import json
import re
from typing import Any, Dict, Optional

from core import msk_time
from core.mcp import db

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS settings (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,          -- JSON
        updated_at TEXT NOT NULL,          -- МСК, ISO
        updated_by TEXT NOT NULL DEFAULT ''
    )''',
)

# Умолчания. Хосты OAuth: claude.ai и claude.com — приложение Claude и расписания,
# localhost/127.0.0.1 — Claude Code принимает код на локальный порт (loopback).
DEFAULTS: Dict[str, Any] = {
    'notify_chat_id': '',
    'oauth_redirect_hosts': ['claude.ai', 'claude.com', 'localhost', '127.0.0.1'],
}

# Предел списка хостов: владельцу нужны единицы; сотни — это ошибка ввода.
MAX_REDIRECT_HOSTS = 20
HOST_RE = re.compile(r'^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$')
CHAT_ID_RE = re.compile(r'^-?\d{1,20}$')


def _ensure() -> None:
    db.ensure_schema('settings', SCHEMA)


def _clean_chat_id(value: Any) -> str:
    text = '' if value is None else str(value).strip()
    if text and not CHAT_ID_RE.match(text):
        raise ValueError('Чат Telegram — это число (у групп со знаком минус), например 670033096')
    return text


def _clean_hosts(value: Any) -> list:
    if isinstance(value, str):
        value = [part for part in re.split(r'[\s,;]+', value) if part]
    if not isinstance(value, list):
        raise ValueError('Разрешённые хосты — список имён, например claude.ai')
    out = []
    for raw in value:
        host = str(raw or '').strip().lower().rstrip('.')
        if not host:
            continue
        if '://' in host or '/' in host or ':' in host:
            raise ValueError(f'Хост «{host}» указан с адресом или портом — нужно только имя, например claude.ai')
        if not HOST_RE.match(host):
            raise ValueError(f'«{host}» — не имя хоста')
        if host not in out:
            out.append(host)
    if len(out) > MAX_REDIRECT_HOSTS:
        raise ValueError(f'Не больше {MAX_REDIRECT_HOSTS} хостов')
    return out


KNOWN = {
    'notify_chat_id': _clean_chat_id,
    'oauth_redirect_hosts': _clean_hosts,
}


def get(key: str, default: Any = None) -> Any:
    """Значение настройки (см. докстринг модуля про умолчания)."""
    _ensure()
    with db.read() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    if row is not None:
        try:
            return json.loads(row['value'])
        except ValueError:
            pass   # битое значение (ручная правка БД) — ведём себя как «не задано»
    if default is not None:
        return default
    value = DEFAULTS.get(key)
    return list(value) if isinstance(value, list) else value


def set(key: str, value: Any, by: str = '') -> Any:  # noqa: A001 — имя из контракта (settings.set)
    """Сохранить значение. Для известных ключей — проверка и нормализация; вернёт то, что записано.

    Ошибка ввода -> ValueError с русским текстом (админ-API отдаёт его как 400).
    """
    if not isinstance(key, str) or not key.strip():
        raise ValueError('Пустой ключ настройки')
    cleaner = KNOWN.get(key)
    clean = cleaner(value) if cleaner else value
    payload = json.dumps(clean, ensure_ascii=False)
    _ensure()
    with db.write() as conn:
        conn.execute(
            'INSERT INTO settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?) '
            'ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, '
            'updated_by=excluded.updated_by',
            (key, payload, msk_time.now().isoformat(timespec='seconds'), by or ''))
    return clean


def all_settings() -> Dict[str, Any]:
    """Все известные настройки с учётом умолчаний (для страницы доступа)."""
    return {key: get(key) for key in DEFAULTS}


def updated_info(key: str) -> Optional[Dict[str, str]]:
    """Когда и кем настройка менялась в последний раз (None — ни разу)."""
    _ensure()
    with db.read() as conn:
        row = conn.execute('SELECT updated_at, updated_by FROM settings WHERE key=?', (key,)).fetchone()
    return dict(row) if row else None
