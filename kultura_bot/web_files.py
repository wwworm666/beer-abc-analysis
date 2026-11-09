"""Файлы к вопросам со страницы kultura.research (решение владельца 2026-11-09: «кнопка добавить
картинку, PDF и т. д.»).

## Что это

Человек прикладывает к вопросу файлы — сайт проверяет их, хранит у себя и отдаёт серверу бота в
Амстердаме, а тот — модели, как фото и PDF из Telegram (kultura_bot/engine/service.py). Сайт к Claude
не обращается: он только готовит копию для бота (уменьшенная картинка, текст таблицы).

## Что принимается — по содержимому, а не по имени файла и не по слову браузера

| Вид | Файлы | Боту уходит |
|---|---|---|
| image | JPEG, PNG, WebP, GIF | картинкой (блок image Claude API). Больше WEB_IMAGE_BOT_MAX_BYTES или стороной больше WEB_IMAGE_MAX_SIDE — уменьшенной копией JPEG |
| pdf | PDF | документом (блок document) |
| table | Excel .xlsx, CSV, TSV | текстом: каждый лист — строки через «;», до TABLE_ROWS_MAX строк и TABLE_COLS_MAX колонок на лист |
| text | .txt, .md, .json | текстом |

Текст боту — не длиннее WEB_TEXT_MAX_CHARS знаков (дальше обрезается с пометкой). HEIC, старый .xls,
Word и остальное — отказ с текстом, что принимается. Пределы — kultura_bot/settings.py (WEB_FILES_*):
файлов в вопросе, размер файла и всех файлов вопроса (запрос к Claude API — до 32 МБ, base64 + 33 %).

## Где лежит — у нас и у того, кто спросил

<данные сайта>/research_files/<id вопроса>/<n>.<ext> — файл, как его прислал человек (страница отдаёт
его только ему); <n>.bot.<ext> — копия для бота, если она другая. Список файлов вопроса — колонка files
таблицы bot_web_questions (kultura_bot/web.py). Удаляются вместе с беседой; другим людям не видны.
"""
import base64
import binascii
import csv
import io
import os
import re
import shutil
import zipfile
from datetime import date, datetime, time as dtime
from typing import Any, Dict, List, Optional

from kultura_bot import settings

DIR_NAME = 'research_files'
TABLE_ROWS_MAX = 2000          # строк листа Excel или CSV боту
TABLE_COLS_MAX = 60            # колонок
XLSX_UNPACKED_MAX = 200 * 1024 * 1024   # распакованный .xlsx — защита от «zip-бомбы»
IMAGE_PIXELS_MAX = 60_000_000           # картинка больше — отказ (защита от «бомбы» распаковки)
NAME_MAX = 120

IMAGE_MIMES = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp', 'gif': 'image/gif'}
TEXT_EXTS = {'csv': 'table', 'tsv': 'table', 'txt': 'text', 'md': 'text', 'json': 'text'}
MIMES = dict(IMAGE_MIMES, pdf='application/pdf', csv='text/csv', tsv='text/tab-separated-values',
             txt='text/plain', md='text/markdown', json='application/json',
             xlsx='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
KIND_TITLES = {'image': 'картинка', 'pdf': 'PDF', 'table': 'таблица', 'text': 'текст'}
HEIC_BRANDS = {b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis', b'mif1', b'msf1', b'avif', b'avis'}

ACCEPTED_TEXT = 'Понимаю картинки (JPEG, PNG, WebP, GIF), PDF, Excel (.xlsx), CSV и текст (.txt, .md, .json).'
_DIR_OVERRIDE: Optional[str] = None     # тесты — временный каталог


class FileError(ValueError):
    """Файл не принят: текст — человеку на странице."""


def files_dir() -> str:
    if _DIR_OVERRIDE:
        return _DIR_OVERRIDE
    from core.storage_paths import get_data_path
    return os.path.abspath(get_data_path(DIR_NAME))


def _mb(n: int) -> str:
    return f'{n / (1024 * 1024):.0f} МБ' if n >= 1024 * 1024 else f'{n / 1e6:.1f} МБ'


def clean_name(value: Any) -> str:
    """Имя файла для показа: без пути и управляющих знаков, до NAME_MAX."""
    name = str(value or '').replace('\\', '/').rsplit('/', 1)[-1]
    name = re.sub(r'[\x00-\x1f\x7f]', '', name).strip()
    return name[:NAME_MAX] or 'файл'


def _extension(name: str) -> str:
    return name.rsplit('.', 1)[-1].lower() if '.' in name else ''


def _decode_text(data: bytes) -> str:
    if b'\x00' in data[:65536]:
        raise FileError('Это не текстовый файл. ' + ACCEPTED_TEXT)
    for encoding in ('utf-8-sig', 'cp1251'):        # выгрузки Excel и iiko бывают в cp1251
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise FileError('Текст файла не прочитался (кодировка) — сохраните его в UTF-8.')


def detect(data: bytes, name: str) -> str:
    """Расширение по содержимому: jpg, png, webp, gif, pdf, xlsx, csv, tsv, txt, md, json. Иначе — FileError."""
    if not data:
        raise FileError(f'Файл «{name}» пустой.')
    if data[:3] == b'\xff\xd8\xff':
        return 'jpg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if data[:5] == b'%PDF-':
        return 'pdf'
    if len(data) >= 12 and data[4:8] == b'ftyp' and data[8:12] in HEIC_BRANDS:
        raise FileError(f'Фото «{name}» в HEIC/AVIF — сохраните его как JPEG (на iPhone: «Настройки → Камера → '
                        'Форматы → Наиболее совместимые»).')
    if data[:4] == b'PK\x03\x04':
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            raise FileError(f'Файл «{name}» повреждён.') from None
        if 'xl/workbook.xml' in names:
            return 'xlsx'
        if 'word/document.xml' in names:
            raise FileError(f'Word («{name}») пока не читаю — сохраните его как PDF. ' + ACCEPTED_TEXT)
        raise FileError(f'Файл «{name}» я не читаю. ' + ACCEPTED_TEXT)
    ext = _extension(name)
    if ext in TEXT_EXTS:
        _decode_text(data)
        return ext
    if data[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        raise FileError(f'Старый Excel или Word («{name}») не читаю — сохраните как .xlsx или PDF.')
    raise FileError(f'Файл «{name}» я не читаю. ' + ACCEPTED_TEXT)


def _cell(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M') if (value.hour or value.minute) else value.strftime('%Y-%m-%d')
    if isinstance(value, (date, dtime)):
        return value.isoformat()
    if isinstance(value, float):
        return ('%.6f' % value).rstrip('0').rstrip('.') if value != int(value) else str(int(value))
    return ' '.join(str(value).split()).replace(';', ',')


def _cut(text: str, title: str) -> str:
    limit = int(settings.WEB_TEXT_MAX_CHARS)
    if len(text) <= limit:
        return text
    return text[:limit] + f'\n… (дальше обрезано: файл «{title}» длиннее {limit} знаков)'


def xlsx_text(data: bytes, name: str) -> str:
    """Excel -> текст боту: лист за листом, строки через «;»."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(info.file_size for info in archive.infolist()) > XLSX_UNPACKED_MAX:
            raise FileError(f'Таблица «{name}» слишком большая — сохраните нужный лист в CSV.')
    from openpyxl import load_workbook
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 — любой сбой разбора: файл не таблица или повреждён
        raise FileError(f'Таблица «{name}» не открылась — пересохраните её в Excel.') from None
    parts = []
    try:
        for sheet in book.worksheets:
            rows = []
            for row in sheet.iter_rows(max_row=TABLE_ROWS_MAX, max_col=TABLE_COLS_MAX, values_only=True):
                cells = [_cell(v) for v in row]
                while cells and cells[-1] == '':
                    cells.pop()
                if cells:
                    rows.append(';'.join(cells))
            total = sheet.max_row or len(rows)
            more = f', показаны первые {TABLE_ROWS_MAX}' if total > TABLE_ROWS_MAX else ''
            parts.append(f'Лист «{sheet.title}» (строк: {total}{more}):\n' + '\n'.join(rows))
    finally:
        book.close()
    return '\n\n'.join(parts) or '(таблица пустая)'


def delimited_text(data: bytes, ext: str) -> str:
    """CSV или TSV -> те же строки через «;», не больше TABLE_ROWS_MAX и TABLE_COLS_MAX."""
    text = _decode_text(data)
    sample = text[:20000]
    delimiter = '\t' if ext == 'tsv' else (';' if sample.count(';') > sample.count(',') else ',')
    rows, total = [], 0
    for row in csv.reader(io.StringIO(text), delimiter=delimiter):
        total += 1
        if len(rows) < TABLE_ROWS_MAX:
            rows.append(';'.join(_cell(c) for c in row[:TABLE_COLS_MAX]))
    more = f', показаны первые {TABLE_ROWS_MAX}' if total > TABLE_ROWS_MAX else ''
    return f'(строк: {total}{more})\n' + '\n'.join(rows)


def _shrink_image(data: bytes, ext: str, name: str) -> Optional[bytes]:
    """Картинка боту: проверить, что открывается; большую — уменьшить до JPEG. None — подходит как есть."""
    from PIL import Image, ImageOps
    try:
        image = Image.open(io.BytesIO(data))
        width, height = image.size
        if width * height > IMAGE_PIXELS_MAX:
            raise FileError(f'Картинка «{name}» слишком большая ({width}×{height}).')
        image.load()
    except FileError:
        raise
    except Exception:  # noqa: BLE001 — Pillow: повреждённый файл, «бомба» распаковки
        raise FileError(f'Картинка «{name}» не открылась — она повреждена или в другом формате.') from None
    side = int(settings.WEB_IMAGE_MAX_SIDE)
    if len(data) <= int(settings.WEB_IMAGE_BOT_MAX_BYTES) and max(width, height) <= side:
        return None
    image = ImageOps.exif_transpose(image)
    image.thumbnail((side, side))
    if image.mode in ('RGBA', 'LA', 'P'):
        image = image.convert('RGBA')
        canvas = Image.new('RGB', image.size, (255, 255, 255))     # прозрачное — на белом, как на экране
        canvas.paste(image, mask=image.split()[-1])
        image = canvas
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    for quality in (85, 70, 55):
        out = io.BytesIO()
        image.save(out, 'JPEG', quality=quality, optimize=True)
        if out.tell() <= int(settings.WEB_IMAGE_BOT_MAX_BYTES):
            return out.getvalue()
    raise FileError(f'Картинку «{name}» не удалось ужать — пришлите её поменьше.')


def prepare(raw: Any) -> List[Dict[str, Any]]:
    """Файлы со страницы [{name, data: base64}] -> проверенные и готовые к записи. Ошибка — FileError."""
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise FileError('files — список файлов')
    if len(raw) > int(settings.WEB_FILES_MAX):
        raise FileError(f'Не больше {settings.WEB_FILES_MAX} файлов к вопросу.')
    out, total = [], 0
    for item in raw:
        if not isinstance(item, dict):
            raise FileError('Файл — объект {name, data}')
        name = clean_name(item.get('name'))
        try:
            data = base64.b64decode(str(item.get('data') or ''), validate=True)
        except (binascii.Error, ValueError):
            raise FileError(f'Файл «{name}» пришёл повреждённым — приложите его ещё раз.') from None
        if len(data) > int(settings.WEB_FILE_MAX_BYTES):
            raise FileError(f'Файл «{name}» больше {_mb(int(settings.WEB_FILE_MAX_BYTES))}.')
        total += len(data)
        if total > int(settings.WEB_FILES_TOTAL_MAX_BYTES):
            raise FileError(f'Все файлы вопроса вместе — не больше {_mb(int(settings.WEB_FILES_TOTAL_MAX_BYTES))}.')
        ext = detect(data, name)
        bot_data, bot_ext = None, None
        if ext in IMAGE_MIMES:
            kind = 'image'
            bot_data = _shrink_image(data, ext, name)
            bot_ext = 'jpg' if bot_data is not None else None
        elif ext == 'pdf':
            kind = 'pdf'
        else:
            kind = 'table' if ext == 'xlsx' else TEXT_EXTS[ext]
            body = xlsx_text(data, name) if ext == 'xlsx' else (
                delimited_text(data, ext) if ext in ('csv', 'tsv') else _decode_text(data))
            what = 'Excel' if ext == 'xlsx' else ext.upper()
            bot_data = _cut(f'Файл «{name}» ({what}):\n{body}', name).encode('utf-8')
            bot_ext = 'txt'
        out.append({'name': name, 'kind': kind, 'ext': ext, 'mime': MIMES[ext], 'data': data,
                    'bot_ext': bot_ext, 'bot_data': bot_data})
    return out


def _question_dir(qid: str) -> str:
    if not re.fullmatch(r'q[A-Za-z0-9_-]{16}', str(qid or '')):
        raise FileError('id вопроса — q и 16 знаков')
    return os.path.join(files_dir(), qid)


def _write(path: str, data: bytes) -> None:
    tmp = f'{path}.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)                     # параллельный читатель не увидит полуфайл


def store(qid: str, prepared: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Записать файлы вопроса на диск -> описания для колонки files (без самих данных)."""
    if not prepared:
        return []
    folder = _question_dir(qid)
    os.makedirs(folder, exist_ok=True)
    meta = []
    try:
        for n, item in enumerate(prepared):
            _write(os.path.join(folder, f'{n}.{item["ext"]}'), item['data'])
            entry = {'n': n, 'name': item['name'], 'kind': item['kind'], 'ext': item['ext'], 'mime': item['mime'],
                     'size': len(item['data'])}
            if item.get('bot_data') is not None:
                _write(os.path.join(folder, f'{n}.bot.{item["bot_ext"]}'), item['bot_data'])
                entry.update(bot_ext=item['bot_ext'],
                             bot_mime='text/plain; charset=utf-8' if item['bot_ext'] == 'txt' else 'image/jpeg',
                             bot_size=len(item['bot_data']))
            meta.append(entry)
    except OSError as exc:
        delete(qid)
        raise FileError(f'Файлы не сохранились: {exc}') from None
    return meta


def read(qid: str, entry: Dict[str, Any], for_bot: bool = False) -> bytes:
    """Файл вопроса: как прислал человек или копия для бота (если есть)."""
    folder = _question_dir(qid)
    n = int(entry['n'])
    if for_bot and entry.get('bot_ext'):
        name = f'{n}.bot.{entry["bot_ext"]}'
    else:
        name = f'{n}.{entry["ext"]}'
    if not re.fullmatch(r'\d{1,2}(\.bot)?\.[a-z]{2,4}', name):
        raise FileError('Файла нет')
    with open(os.path.join(folder, name), 'rb') as f:
        return f.read()


def bot_mime(entry: Dict[str, Any]) -> str:
    return str(entry.get('bot_mime') or entry.get('mime') or 'application/octet-stream')


def delete(qid: str) -> None:
    """Файлы вопроса — вместе с вопросом (удаление беседы)."""
    try:
        folder = _question_dir(qid)
    except FileError:
        return
    shutil.rmtree(folder, ignore_errors=True)


def describe(entries: List[Dict[str, Any]]) -> str:
    """«Накладная.pdf (PDF), фото.jpg (картинка)» — для текста вопроса боту и истории беседы."""
    return ', '.join(f'{e.get("name")} ({KIND_TITLES.get(e.get("kind"), "файл")})' for e in entries or [])
