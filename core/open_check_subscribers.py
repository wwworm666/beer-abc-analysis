"""Хранилище чатов, подписанных на уведомления open-check бота.

Подписка управляется кнопками в самом боте (см. core/open_check_telegram.py),
поэтому список нужно хранить персистентно — JSON на Render Disk через
storage_paths.get_data_path. Запись защищена portalocker (как в plans_manager),
т.к. webhook может прийти в любой из gunicorn-воркеров.

Структура файла:
    {
        "positive": ["670033096", "-1001234567890"],  # кому слать "всё открыто"
        "alarm":    ["670033096"]                       # кому слать тревоги
    }

chat_id всегда строки (у групп они отрицательные).
"""
import json
import os
import threading
from contextlib import contextmanager

import portalocker

from core.storage_paths import get_data_path
from core.json_store import atomic_write_json

KINDS = ('positive', 'alarm')

_PATH = None
_thread_lock = threading.Lock()


def _path() -> str:
    global _PATH
    if _PATH is None:
        _PATH = get_data_path('open_check_subscribers.json')
    return _PATH


def _read() -> dict:
    p = _path()
    if not os.path.exists(p):
        return {'positive': [], 'alarm': []}
    try:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        for k in KINDS:
            d.setdefault(k, [])
            d[k] = [str(x) for x in d[k]]
        return d
    except Exception:
        return {'positive': [], 'alarm': []}


def _write(d: dict) -> None:
    # Атомарная запись (tmp+fsync+replace): при гонке чтение/запись или падении
    # читатель не увидит усечённый файл (раньше был open(..., 'w') — усекающий).
    atomic_write_json(_path(), d)


@contextmanager
def _locked():
    p = _path()
    directory = os.path.dirname(p)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    with _thread_lock:
        with portalocker.Lock(p + '.lock', mode='a', timeout=10):
            yield


def get_recipients(kind: str) -> list:
    """Список chat_id, подписанных на данный тип ('positive' | 'alarm')."""
    return list(_read().get(kind, []))


def subscribe(chat_id, kinds) -> dict:
    """Подписать чат на один или несколько типов уведомлений."""
    chat_id = str(chat_id)
    with _locked():
        d = _read()
        for k in kinds:
            if k in KINDS and chat_id not in d[k]:
                d[k].append(chat_id)
        _write(d)
        return d


def unsubscribe(chat_id) -> dict:
    """Отключить чат от всех уведомлений."""
    chat_id = str(chat_id)
    with _locked():
        d = _read()
        for k in KINDS:
            if chat_id in d[k]:
                d[k].remove(chat_id)
        _write(d)
        return d


def status(chat_id) -> dict:
    """Что сейчас получает данный чат: {'positive': bool, 'alarm': bool}."""
    chat_id = str(chat_id)
    d = _read()
    return {k: chat_id in d[k] for k in KINDS}
