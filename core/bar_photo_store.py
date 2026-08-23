"""
Хранение фотографий приёмки бара («Плохо» — строка + фото).

## Что это

Единственное место в приложении, куда пользователь загружает файл. Поэтому
модуль маленький и параноидальный: он решает три задачи — куда положить, под
каким именем и что вообще принимать.

## Где лежат файлы

Каталог `bar_photos/` на постоянном диске (`/kultura` в проде, `data/` локально
— общее правило `core/storage_paths.get_data_path`). В БД хранится ТОЛЬКО имя
файла, не путь: путь зависит от окружения, имя переносимо, и перенос диска не
делает записи битыми.

## Имя файла

`YYYY-MM-DD_<shift_id>_<8 hex>.jpg`

Дата и смена — чтобы каталог читался глазами при разборе «что это за файл».
Случайные 8 hex — чтобы имя нельзя было угадать по номеру смены. Это защита в
глубину, а не основная: раздача фото и так закрыта общим гейтом авторизации
(`core/auth_guard.py`), но неугадываемое имя означает, что утёкшая ссылка не
открывает соседние фотографии.

`is_valid_name()` — единственный допуск к файловой системе: только имена этого
вида. Никакой конкатенации пользовательской строки с путём, поэтому `../` и
абсолютные пути отсекаются формой имени, а не поиском подстрок.

## Что принимаем

Только JPEG и только до `MAX_PHOTO_BYTES`. Формат проверяется по СИГНАТУРЕ
файла (`FF D8 FF`), а не по расширению и не по заголовку `Content-Type`: и то и
другое пишет клиент, и им нельзя верить. Никакой перекодировки на сервере не
делается — в образе нет Pillow, и добавлять его ради одного ресайза дорого;
уменьшает картинку браузер перед отправкой (`static/js/me/acceptance.js`,
canvas -> JPEG). Потолок здесь — страховка на случай клиента, который этого не
сделал.

## Файлы

- `core/bar_photo_store.py` — этот модуль.
- `core/bar_acceptance.py` — правила приёмки (когда фото обязательно).
- `routes/cleanliness.py` — приём загрузки и раздача `/api/cleanliness/photo/<имя>`.

## Changelog

- 2026-08-23 — модуль создан.
"""

import os
import re
import secrets
from typing import Optional, Tuple

from core.storage_paths import get_data_path

# Каталог с фотографиями на постоянном диске.
PHOTO_DIR_NAME = 'bar_photos'

# Потолок размера. Браузер шлёт ~200-400 КБ после уменьшения; 4 МБ — запас на
# клиента, который уменьшить не смог (старый браузер, отключённый JS-путь).
MAX_PHOTO_BYTES = 4 * 1024 * 1024

# Сигнатура JPEG. Проверяем её, а не расширение и не Content-Type: их пишет
# клиент. SOI-маркер FF D8 + начало первого сегмента FF.
JPEG_MAGIC = b'\xff\xd8\xff'

# Единственная допустимая форма имени файла (см. докстроку модуля).
NAME_RE = re.compile(r'^\d{4}-\d{2}-\d{2}_\d+_[0-9a-f]{8}\.jpg$')


def photo_dir() -> str:
    """Каталог с фотографиями; создаётся при первом обращении."""
    path = get_data_path(PHOTO_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def is_valid_name(name) -> bool:
    """Проверить имя файла ПЕРЕД любым обращением к диску."""
    return bool(name) and bool(NAME_RE.match(str(name)))


def photo_path(name) -> Optional[str]:
    """Абсолютный путь к фото по имени; None, если имя не нашей формы."""
    if not is_valid_name(name):
        return None
    return os.path.join(photo_dir(), str(name))


def exists(name) -> bool:
    """Есть ли файл на диске (имя невалидной формы -> False)."""
    path = photo_path(name)
    return bool(path) and os.path.isfile(path)


def make_name(date_str: str, shift_id: int) -> str:
    """Сгенерировать имя файла для смены."""
    return f"{str(date_str)[:10]}_{int(shift_id)}_{secrets.token_hex(4)}.jpg"


def check(data: bytes) -> Tuple[bool, Optional[str]]:
    """Проверить содержимое загруженного файла. -> (ok, текст_ошибки)."""
    if not data:
        return False, 'Файл пустой'
    if len(data) > MAX_PHOTO_BYTES:
        mb = MAX_PHOTO_BYTES // (1024 * 1024)
        return False, f'Фото больше {mb} МБ — сделайте снимок меньшего размера'
    if not data.startswith(JPEG_MAGIC):
        return False, 'Нужна фотография в формате JPEG'
    return True, None


def save(data: bytes, date_str: str, shift_id: int) -> Tuple[bool, str]:
    """Проверить и сохранить фото. -> (ok, имя_файла | текст_ошибки).

    Запись через временный файл + os.replace: параллельный читатель никогда не
    получает полу-записанную картинку (тот же приём, что в `atomic_write_json`).
    """
    ok, err = check(data)
    if not ok:
        return False, err

    name = make_name(date_str, shift_id)
    path = os.path.join(photo_dir(), name)
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, 'wb') as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # некоторые ФС (сетевые маунты) не поддерживают fsync
        os.replace(tmp_path, path)
    except OSError as e:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return False, f'Фото не сохранилось: {e}'
    return True, name


def delete(name) -> bool:
    """Удалить фото (best-effort). Используется, когда ответ переписали и
    прежний файл осиротел: он уже ни на что не ссылается, а место занимает."""
    path = photo_path(name)
    if not path:
        return False
    try:
        os.unlink(path)
        return True
    except OSError:
        return False
