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


def _base(public_base):
    return str(public_base or '').rstrip('/') + '/'


def _local_picture(url, public_base, photo_dir):
    name = picture_filename(url)
    if not name or not (photo_dir / name).is_file():
        return ''
    return f'{_base(public_base)}static/kitchen-menu/{name}'


def catalog_offers(public_base='https://beerkultura.ru/', source=None, photo_dir=None):
    """Позиции меню: id, цена, категория, фото с нашего сайта."""
    source = Path(source or SOURCE)
    photo_dir = Path(photo_dir or PHOTO_DIR)
    root = ET.parse(source).getroot()
    categories = {
        node.get('id'): (node.text or '').strip()
        for node in root.findall('./shop/categories/category')
    }
    items = []
    for offer in root.findall('./shop/offers/offer'):
        category_id = (offer.findtext('categoryId') or '').strip()
        items.append({
            'id': offer.get('id') or '',
            'name': (offer.findtext('name') or '').strip(),
            'price': (offer.findtext('price') or '').strip(),
            'category_id': category_id,
            'category_name': categories.get(category_id) or 'Меню',
            'picture': _local_picture(offer.findtext('picture'), public_base, photo_dir),
            'vendor': (offer.findtext('vendor') or '').strip(),
            'description': (offer.findtext('description') or '').strip(),
        })
    return items


def render_kitchen_menu(public_base, source=None, photo_dir=None):
    """XML-фид. public_base — корень сайта, например https://beerkultura.ru/."""
    source = Path(source or SOURCE)
    photo_dir = Path(photo_dir or PHOTO_DIR)
    root = ET.parse(source).getroot()
    for offer in root.findall('./shop/offers/offer'):
        picture = offer.find('picture')
        if picture is None:
            continue
        local = _local_picture(picture.text, public_base, photo_dir)
        if not local:
            offer.remove(picture)
            continue
        picture.text = local
    body = ET.tostring(root, encoding='unicode')
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body


def render_for_bar(public_base, bar_id, overrides=None, source=None, photo_dir=None):
    """Тот же каталог, в названии магазина — конкретная точка, плюс её правки."""
    from core.taplist import BAR_NAMES
    xml = render_kitchen_menu(public_base, source=source, photo_dir=photo_dir)
    root = ET.fromstring(xml)
    name = root.find('./shop/name')
    if name is not None and bar_id in BAR_NAMES:
        name.text = f'Культура, {BAR_NAMES[bar_id]}'
    body = ET.tostring(root, encoding='unicode')
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + body
    return apply_overrides(xml, overrides or {})


def apply_overrides(xml, overrides):
    """Скрыть позицию или подменить имя, цену и описание. Остальной файл не трогаем."""
    overrides = overrides or {}
    root = ET.fromstring(xml)
    box = root.find('./shop/offers')
    if box is None:
        return xml
    for offer in list(box.findall('offer')):
        change = overrides.get(offer.get('id')) or {}
        if change.get('hidden'):
            box.remove(offer)
            continue
        if change.get('name') and offer.find('name') is not None:
            offer.find('name').text = change['name']
        if change.get('price') and offer.find('price') is not None:
            offer.find('price').text = change['price']
        if change.get('description'):
            node = offer.find('description')
            if node is None:
                node = ET.SubElement(offer, 'description')
            node.text = change['description']
    body = ET.tostring(root, encoding='unicode')
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body
