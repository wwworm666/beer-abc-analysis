"""
Файлы материалов контент-плана (фото и видео) — хранение на диске.

## Что это

Второе место в приложении (после `core/bar_photo_store.py`), куда пользователь
загружает файл. Модуль повторяет ту же паранойю: он решает только три задачи —
куда положить, под каким именем и что вообще принимать. Какие файлы у какого
материала и когда файл можно удалить, решает `core/content_plan.py`.

## Где лежат файлы

Каталог `content_media/` на постоянном диске (`/kultura` в проде, `data/`
локально — общее правило `core/storage_paths.get_data_path`). В JSON контент-плана
хранится ТОЛЬКО имя файла, не путь: путь зависит от окружения, имя переносимо.

## Имя файла

`cp_<YYYYMMDD>_<12 hex>.<ext>`, ext из `jpg | png | webp | mp4`.

- `cp_` — префикс раздела (content plan), чтобы файл читался глазами в каталоге.
- `YYYYMMDD` — московская дата загрузки: удобно разбирать каталог по времени.
- 12 hex (48 бит случайности, `secrets.token_hex(6)`) — имя нельзя угадать:
  утёкшая ссылка не открывает соседние файлы. Раздача и так закрыта общим
  гейтом авторизации, это защита в глубину.

`MediaStore.path()` — единственный допуск к файловой системе: имя проверяется
регулярным выражением `NAME_RE` ДО любого обращения к диску. Никакой
конкатенации пользовательской строки с путём, поэтому `../`, абсолютные пути и
обратные слэши отсекаются формой имени, а не поиском подстрок.

## Что принимаем

Тип определяется по СИГНАТУРЕ (первым байтам файла), а не по расширению и не по
`Content-Type`: и то и другое пишет клиент.

| Тип  | Сигнатура                                  | Вид   |
|------|--------------------------------------------|-------|
| JPEG | `FF D8 FF`                                 | image |
| PNG  | `89 50 4E 47 0D 0A 1A 0A`                  | image |
| WEBP | `RIFF` (байты 0..3) + `WEBP` (байты 8..11) | image |
| MP4  | `ftyp` в байтах 4..7                       | video |

Край: `ftyp` — общий заголовок контейнера ISO-BMFF. Им же начинаются фото
HEIC/AVIF с iPhone. Такие файлы мы НЕ принимаем как видео: бренд в байтах 8..11
из `IMAGE_FTYP_BRANDS` даёт понятную ошибку «сохраните как JPEG». MOV (бренд
`qt  `) проходит как видео — браузеры и Telegram его играют.

Лимиты размера (факты площадок, куда файл потом уйдёт):
- фото `MAX_IMAGE_BYTES` = 10 МБ — предел Telegram Bot API для sendPhoto
  («The photo must be at most 10 MB»). У Instagram для фото предел строже
  (8 МБ, только JPEG) — это проверит отправка, когда её подключат.
- видео `MAX_VIDEO_BYTES` = 50 МБ — предел Telegram Bot API на загрузку файла
  ботом (multipart upload до 50 МБ).

Перекодировки нет (в образе нет Pillow); файл сохраняется как есть.

## Changelog

- 2026-09-26 — модуль создан (раздел «Гости», контент-план, этап «только интерфейс»).
"""

import os
import re
import secrets
from datetime import date
from typing import Optional, Tuple

from core.storage_paths import get_data_path

MEDIA_DIR_NAME = 'content_media'

# Предел Telegram Bot API для фото (sendPhoto): 10 МБ. См. докстроку модуля.
MAX_IMAGE_BYTES = 10 * 1024 * 1024
# Предел Telegram Bot API на загрузку файла ботом: 50 МБ. См. докстроку модуля.
MAX_VIDEO_BYTES = 50 * 1024 * 1024
# Запас на заголовки multipart поверх самого файла при проверке Content-Length
# (имя поля, имя файла, границы) — тот же приём, что в routes/cleanliness.py.
UPLOAD_OVERHEAD_BYTES = 64 * 1024

# Единственная допустимая форма имени файла (см. докстроку модуля).
# Конец строки — \Z, а не $: в Python `$` пропускает завершающий перевод строки,
# и имя с переводом строки в конце прошло бы проверку.
NAME_RE = re.compile(r'^cp_\d{8}_[0-9a-f]{12}\.(jpg|png|webp|mp4)\Z')

EXT_KIND = {'jpg': 'image', 'png': 'image', 'webp': 'image', 'mp4': 'video'}
MIMETYPES = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp', 'mp4': 'video/mp4'}

JPEG_MAGIC = b'\xff\xd8\xff'
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
# Бренды ISO-BMFF, которыми помечены КАРТИНКИ (HEIF/HEIC/AVIF), а не видео.
IMAGE_FTYP_BRANDS = {b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis',
                     b'mif1', b'msf1', b'avif', b'avis'}

UNSUPPORTED_TEXT = 'Поддерживаются фото JPEG, PNG, WEBP и видео MP4'


def is_valid_name(name) -> bool:
    """Проверить имя файла ПЕРЕД любым обращением к диску."""
    return isinstance(name, str) and bool(NAME_RE.match(name))


def ext_of(name) -> Optional[str]:
    """Расширение валидного имени (jpg/png/webp/mp4) или None."""
    if not is_valid_name(name):
        return None
    return name.rsplit('.', 1)[1]


def kind_of(name) -> Optional[str]:
    """'image' / 'video' по расширению валидного имени."""
    ext = ext_of(name)
    return EXT_KIND.get(ext) if ext else None


def mimetype_of(name) -> Optional[str]:
    ext = ext_of(name)
    return MIMETYPES.get(ext) if ext else None


def detect(data: bytes) -> Optional[str]:
    """Расширение по сигнатуре файла или None, если формат не наш."""
    if not data:
        return None
    if data[:3] == JPEG_MAGIC:
        return 'jpg'
    if data[:8] == PNG_MAGIC:
        return 'png'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    if len(data) >= 12 and data[4:8] == b'ftyp' and data[8:12] not in IMAGE_FTYP_BRANDS:
        return 'mp4'
    return None


def check(data: bytes) -> Tuple[bool, str]:
    """Проверить содержимое загрузки. -> (True, ext) или (False, текст ошибки)."""
    if not data:
        return False, 'Файл пустой'
    if len(data) >= 12 and data[4:8] == b'ftyp' and data[8:12] in IMAGE_FTYP_BRANDS:
        return False, 'Фото HEIC/AVIF не поддерживается — сохраните его как JPEG'
    ext = detect(data)
    if ext is None:
        return False, UNSUPPORTED_TEXT
    limit = MAX_VIDEO_BYTES if EXT_KIND[ext] == 'video' else MAX_IMAGE_BYTES
    if len(data) > limit:
        what = 'Видео' if EXT_KIND[ext] == 'video' else 'Фото'
        return False, f'{what} больше {limit // (1024 * 1024)} МБ'
    return True, ext


def make_name(day, ext: str) -> str:
    """Имя нового файла: cp_<YYYYMMDD>_<12 hex>.<ext>."""
    if isinstance(day, date):
        stamp = day.strftime('%Y%m%d')
    else:
        stamp = str(day)[:10].replace('-', '')
    if not re.fullmatch(r'\d{8}', stamp):
        raise ValueError('Дата для имени файла: YYYY-MM-DD')
    if ext not in EXT_KIND:
        raise ValueError('Неизвестное расширение файла')
    return f'cp_{stamp}_{secrets.token_hex(6)}.{ext}'


class MediaStore:
    """Каталог файлов контент-плана. directory — для тестов (временный каталог)."""

    def __init__(self, directory: Optional[str] = None):
        # Абсолютный путь: Flask send_from_directory считает относительный путь
        # от корня приложения, а не от текущего каталога.
        self.directory = os.path.abspath(directory or get_data_path(MEDIA_DIR_NAME))

    def ensure_dir(self) -> str:
        os.makedirs(self.directory, exist_ok=True)
        return self.directory

    def path(self, name) -> Optional[str]:
        """Абсолютный путь по имени; None, если имя не нашей формы."""
        if not is_valid_name(name):
            return None
        return os.path.join(self.directory, name)

    def exists(self, name) -> bool:
        path = self.path(name)
        return bool(path) and os.path.isfile(path)

    def save(self, data: bytes, day) -> Tuple[bool, str]:
        """Проверить и сохранить файл. -> (True, имя) или (False, текст ошибки).

        Запись через временный файл + os.replace: параллельный читатель никогда
        не получает полузаписанный файл (приём `atomic_write_json`).
        """
        ok, ext_or_err = check(data)
        if not ok:
            return False, ext_or_err
        name = make_name(day, ext_or_err)
        path = os.path.join(self.ensure_dir(), name)
        tmp_path = f'{path}.tmp'
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
            return False, f'Файл не сохранился: {e}'
        return True, name

    def delete(self, name) -> bool:
        """Удалить файл (best-effort). Невалидное имя — False без обращения к диску."""
        path = self.path(name)
        if not path:
            return False
        try:
            os.unlink(path)
            return True
        except OSError:
            return False
