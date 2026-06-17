"""Хранилище чатов, подписанных на уведомления open-check бота.

Подписка — одна кнопка в самом боте (см. core/open_check_telegram.py): человек
открывает бота, жмёт «Подписаться» и его чат начинает получать ВСЕ уведомления
(и «все открыты», и тревоги, и ошибки iiko). Раньше был раздельный выбор
positive/alarm пятью кнопками — убрано как лишняя сложность по запросу владельца.

Список персистентный — JSON на постоянном диске (storage_paths.get_data_path).
Запись под portalocker + atomic_write_json (как в plans_manager): polling/webhook
могут прийти в любой из gunicorn-воркеров, плюс шедулер читает список параллельно.

Структура файла: {"chats": ["670033096", "-1001234567890"]}

chat_id всегда строки (у групп они отрицательные).
"""
import json
import logging
import os
import re
import shutil
import threading
from contextlib import contextmanager

import portalocker

from core.storage_paths import get_data_path
from core.json_store import atomic_write_json

log = logging.getLogger("open-check")

# Валидный Telegram chat_id — целое (личка) или отрицательное целое (группа).
_CHAT_ID_RE = re.compile(r'^-?\d+$')

_PATH = None
_thread_lock = threading.Lock()


def _path() -> str:
    global _PATH
    if _PATH is None:
        _PATH = get_data_path('open_check_subscribers.json')
    return _PATH


def _clean(chats) -> list:
    """str + trim + дедуп с сохранением порядка + отбрасывание невалидных
    chat_id (None, дробные, мусор из битого legacy-файла). Отброшенное логируем,
    чтобы порча была видна, а не утекала молча в send_message."""
    out, seen, dropped = [], set(), []
    for x in chats:
        s = str(x).strip()
        if not _CHAT_ID_RE.match(s):
            dropped.append(s)
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    if dropped:
        log.warning("open_check_subscribers: отброшены невалидные chat_id: %s", dropped)
    return out


def _read() -> list:
    """Список подписанных chat_id. Читает и старый формат {positive,alarm}
    (миграция на лету: подписчик любого типа становится подписчиком на всё).

    Без портлока — безопасно: запись атомарна (atomic_write_json: tmp+fsync+
    os.replace), читатель никогда не видит полу-файл, в худшем случае — снимок
    на миллисекунды раньше записи (для рассылки несущественно). Поэтому read-путь
    не зависит от захвата лока (важно для критичного send_report в шедулере)."""
    p = _path()
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
    except Exception as e:
        # Файл ЕСТЬ, но не парсится — это порча, а не «нет подписчиков». Молча
        # вернуть [] нельзя: следующая запись затрёт всех. Логируем громко и
        # сохраняем копию, чтобы данные можно было восстановить.
        log.error("open_check_subscribers.json не читается (%s) — сохраняю копию .corrupt", e)
        try:
            shutil.copy2(p, p + '.corrupt')
        except Exception:
            pass
        return []
    if isinstance(d, list):
        chats = d
    elif isinstance(d, dict):
        chats = list(d.get('chats') or [])
        for legacy_kind in ('positive', 'alarm'):
            chats += d.get(legacy_kind) or []
    else:
        log.error("open_check_subscribers.json: неожиданный тип %s — игнорирую",
                  type(d).__name__)
        return []
    return _clean(chats)


def _write(chats: list) -> None:
    atomic_write_json(_path(), {'chats': chats})


@contextmanager
def _locked():
    p = _path()
    directory = os.path.dirname(p)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    with _thread_lock:
        with portalocker.Lock(p + '.lock', mode='a', timeout=10):
            yield


def get_recipients() -> list:
    """Все подписанные чаты (для send_report). Read-путь намеренно без лока —
    см. _read (атомарная запись делает чтение безопасным)."""
    return _read()


def is_subscribed(chat_id) -> bool:
    return str(chat_id) in _read()


def subscribe(chat_id) -> bool:
    """Подписать чат на все уведомления. True если добавили (False если уже был)."""
    chat_id = str(chat_id)
    with _locked():
        chats = _read()
        if chat_id in chats:
            return False
        chats.append(chat_id)
        _write(chats)
        return True


def unsubscribe(chat_id) -> bool:
    """Отписать чат. True если удалили (False если не был подписан)."""
    chat_id = str(chat_id)
    with _locked():
        chats = _read()
        if chat_id not in chats:
            return False
        chats.remove(chat_id)
        _write(chats)
        return True
