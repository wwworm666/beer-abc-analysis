"""
Хранение фотографий накладных приёмки на РЦ.

## Что это

Приёмщик снимает бумажную накладную (УПД) кнопкой «Накладная» на экране
`/receiving`; бухгалтерия открывает фото на `/receiving/review`. Модуль —
копия `core/bar_photo_store.py` (фото приёмки бара) со своим каталогом, своим
потолком размера и своей формой имени: он решает три задачи — куда положить,
под каким именем и что вообще принимать.

## Где лежат файлы

Каталог `receiving_photos/` на постоянном диске (`/kultura` в проде, `data/`
локально — общее правило `core/storage_paths.get_data_path`). В БД
(`receipt_invoices` в `receiving.db`) хранится ТОЛЬКО имя файла, не путь: путь
зависит от окружения, имя переносимо. Тесты подменяют каталог через `set_dir()`.

## Имя файла

`r<номер приёмки>_<ГГГГММДДTЧЧММСС по МСК>_<8 hex>.jpg`, например
`r12_20261003T140500_3fa2b9c1.jpg`.

Номер приёмки и время — чтобы каталог читался глазами («чьё это фото»).
Случайные 8 hex — чтобы имя нельзя было угадать по номеру приёмки: раздача и
так закрыта общим гейтом авторизации (`core/auth_guard.py`), но утёкшая ссылка
не открывает соседние накладные.

`is_valid_name()` — единственный допуск к файловой системе: только имена этого
вида (`\\Z`, а не `$`: `$` пропустил бы имя с переводом строки в конце).
Никакой конкатенации пользовательской строки с путём, поэтому `../` и
абсолютные пути отсекаются формой имени, а не поиском подстрок.

## Что принимаем

Только JPEG и только до `MAX_PHOTO_BYTES`. Формат проверяется по СИГНАТУРЕ
(`FF D8 FF`), а не по расширению и не по `Content-Type`: их пишет клиент.
Перекодировки на сервере нет: браузер уменьшает снимок до ~2400 px по длинной
стороне и JPEG 0.85 (`static/js/receiving/scan.js`, по образцу
`static/js/me/acceptance.js`) — при таком размере текст накладной читается.

## Файлы

- `core/receiving_photo_store.py` — этот модуль.
- `core/receiving_store.py` — запись о фото (`add_invoice` / `list_invoices`).
- `routes/receiving.py` — загрузка `POST /api/receiving/<id>/invoice` и раздача
  `GET /api/receiving/invoice/<имя>`.

## Changelog

- 2026-10-03 — модуль создан (приёмка на РЦ, первый этап).
"""

import os
import re
import secrets
from datetime import datetime
from typing import Optional, Tuple

from core import msk_time
from core.storage_paths import get_data_path

# Каталог с фотографиями на постоянном диске.
PHOTO_DIR_NAME = 'receiving_photos'

# Потолок размера. Снимок накладной после уменьшения в браузере (2400 px, JPEG
# 0.85) — ~0.5-1.5 МБ; 8 МБ — запас на клиента, который уменьшить не смог
# (старый браузер), чтобы мелкий текст УПД всё равно дошёл читаемым.
MAX_PHOTO_BYTES = 8 * 1024 * 1024

# Сигнатура JPEG. Проверяем её, а не расширение и не Content-Type: их пишет
# клиент. SOI-маркер FF D8 + начало первого сегмента FF.
JPEG_MAGIC = b'\xff\xd8\xff'

# Номер приёмки в имени — до 9 цифр (AUTOINCREMENT столько не наберёт за всю жизнь
# сервиса; предел нужен, чтобы форма имени была конечной и проверяемой).
MAX_RECEIPT_ID = 10 ** 9 - 1

# Единственная допустимая форма имени файла (см. докстроку модуля).
NAME_RE = re.compile(r'^r\d{1,9}_\d{8}T\d{6}_[0-9a-f]{8}\.jpg\Z')

_dir_override: Optional[str] = None


def set_dir(path: Optional[str]) -> None:
    """Тесты: хранить фото во временном каталоге. None — вернуть боевой путь."""
    global _dir_override
    _dir_override = path


def photo_dir() -> str:
    """Каталог с фотографиями; создаётся при первом обращении."""
    path = _dir_override or get_data_path(PHOTO_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def is_valid_name(name) -> bool:
    """Проверить имя файла ПЕРЕД любым обращением к диску."""
    return isinstance(name, str) and bool(NAME_RE.match(name))


def photo_path(name) -> Optional[str]:
    """Абсолютный путь к фото по имени; None, если имя не нашей формы."""
    if not is_valid_name(name):
        return None
    return os.path.join(photo_dir(), name)


def exists(name) -> bool:
    """Есть ли файл на диске (имя невалидной формы -> False)."""
    path = photo_path(name)
    return bool(path) and os.path.isfile(path)


def make_name(receipt_id: int, now: Optional[datetime] = None) -> str:
    """Сгенерировать имя файла для приёмки. now — момент по МСК (по умолчанию сейчас)."""
    rid = int(receipt_id)
    if rid < 1 or rid > MAX_RECEIPT_ID:
        raise ValueError('Номер приёмки вне диапазона')
    moment = now or msk_time.now()
    return f'r{rid}_{moment:%Y%m%dT%H%M%S}_{secrets.token_hex(4)}.jpg'


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


def save(data: bytes, receipt_id: int) -> Tuple[bool, str]:
    """Проверить и сохранить фото. -> (ok, имя_файла | текст_ошибки).

    Запись через временный файл + fsync + os.replace: параллельный читатель
    никогда не получает полу-записанную картинку (тот же приём, что в
    `atomic_write_json`). Временное имя `<имя>.tmp` не проходит is_valid_name,
    поэтому недописанный файл никогда не раздаётся. Текст ошибки — без пути.
    """
    ok, err = check(data)
    if not ok:
        return False, err

    name = make_name(receipt_id)
    tmp_path = None
    try:
        path = os.path.join(photo_dir(), name)
        tmp_path = f'{path}.tmp'
        with open(tmp_path, 'wb') as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # некоторые ФС (сетевые маунты) не поддерживают fsync
        os.replace(tmp_path, path)
    except OSError as e:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False, 'Фото не сохранилось: ' + (e.strerror or type(e).__name__)
    return True, name


def delete(name) -> bool:
    """Удалить фото (best-effort): запись о накладной удалили — файл осиротел."""
    path = photo_path(name)
    if not path:
        return False
    try:
        os.unlink(path)
        return True
    except OSError:
        return False
