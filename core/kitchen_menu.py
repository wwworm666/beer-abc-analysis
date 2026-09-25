"""Кухонное меню для Яндекс Карт.

Каталог хранится в репозитории. В исходном файле фото ещё ссылаются на
Яндекс Облако; при отдаче фида адрес заменяется на файл с нашего сайта.
Позиция без локального фото остаётся в меню, но без картинки.
"""
import re
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'resources' / 'kitchen_menu.yml'
PHOTO_DIR = ROOT / 'static' / 'kitchen-menu'
_PHOTO_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.jpe?g$')


def picture_filename(url):
    """Имя файла из ссылки. Чужой путь и не-JPEG отбрасываются."""
    name = str(url or '').strip().split('?', 1)[0].rstrip('/').rsplit('/', 1)[-1]
    return name if _PHOTO_NAME.fullmatch(name) else ''


def render_kitchen_menu(public_base, source=None, photo_dir=None):
    """XML-фид. public_base — корень сайта, например https://beerkultura.ru/."""
    source = Path(source or SOURCE)
    photo_dir = Path(photo_dir or PHOTO_DIR)
    base = str(public_base or '').rstrip('/') + '/'
    root = ET.parse(source).getroot()
    for offer in root.findall('./shop/offers/offer'):
        picture = offer.find('picture')
        if picture is None:
            continue
        name = picture_filename(picture.text)
        if not name or not (photo_dir / name).is_file():
            offer.remove(picture)
            continue
        picture.text = f'{base}static/kitchen-menu/{name}'
    body = ET.tostring(root, encoding='unicode')
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body
