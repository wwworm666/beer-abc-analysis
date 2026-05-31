"""
core/json_store.py — общие хелперы безопасной работы с JSON-файлами.

Единый источник паттерна, который раньше был размазан по коду: эталон жил в
plans_manager, но taps_manager / meeting_notes / open_check_subscribers его не
соблюдали (усекающая запись open(..., 'w') и/или отсутствие cross-worker лока).
Под gunicorn 2 workers это давало потерю данных (last-writer-wins) и усечённые
файлы при гонке чтение/запись.

Хелперы:
- atomic_write_json: tmp + flush + fsync + os.replace — параллельный читатель
  никогда не видит полу-записанный файл, запись durable на потере питания.
- file_lock: cross-worker advisory-lock (portalocker) для защиты
  read-modify-write между параллельными воркерами.
"""
import os
import json
from contextlib import contextmanager

import portalocker


def atomic_write_json(path, data, *, indent=2, ensure_ascii=False):
    """
    Атомарно записать data в path как JSON.

    Пишем во временный файл, сбрасываем буфер (flush) и на диск (fsync), затем
    os.replace на финальный путь — атомарная замена на уровне ФС.
    """
    directory = os.path.dirname(path) or '.'
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass  # некоторые ФС (сетевые маунты) не поддерживают fsync
    os.replace(tmp_path, path)


@contextmanager
def file_lock(lock_path, timeout=10):
    """
    Cross-worker advisory-lock на отдельном lock-файле (portalocker).

    Используется в дополнение к in-process threading.Lock, чтобы защитить
    read-modify-write цикл между параллельными gunicorn-воркерами.
    """
    directory = os.path.dirname(lock_path) or '.'
    os.makedirs(directory, exist_ok=True)
    with portalocker.Lock(lock_path, mode='a', timeout=timeout):
        yield
