"""YML-фид текущего таплиста для Яндекс Бизнеса / Карт.

Формат — Yandex Market Language: yml_catalog, shop, categories, offers.
В фид попадают только порции с подтверждённой ценой. Один и тот же сорт
в одном баре и одном объёме не повторяется, даже если стоит на двух кранах.
"""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from core.taplist import BAR_NAMES

SHOP_COMPANY = 'Пивная культура'
SHOP_URL = 'https://beerkultura.ru'
CATEGORY_IDS = {'bar1': '1', 'bar2': '2', 'bar3': '3', 'bar4': '4'}
_CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def generated_at(moment=None) -> str:
    moment = moment or datetime.now(ZoneInfo('Europe/Moscow'))
    return moment.replace(microsecond=0).isoformat()


def _text(value, limit):
    cleaned = _CONTROL.sub('', str(value or '')).strip()
    return cleaned[:limit]


def _portion(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    return format(number.normalize(), 'f')


def _price(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    return format(number.quantize(Decimal('0.01')), 'f')


def _picture(url):
    url = _text(url, 512)
    return url if url.startswith('https://') else ''


def _offer_name(row, portion):
    beer = _text(row.get('beer_name') or row.get('iiko_name'), 120)
    brewery = _text(row.get('brewery'), 80)
    if brewery and brewery.casefold() not in beer.casefold():
        beer = f'{brewery} {beer}'.strip()
    volume = portion.replace('.', ',')
    return _text(f'{beer}, {volume} л', 200)


def _description(row, portion):
    parts = []
    if row.get('description'):
        parts.append(_text(row['description'], 1500))
    if row.get('style'):
        parts.append('Стиль: ' + _text(row['style'], 120))
    if row.get('abv') not in (None, ''):
        parts.append('Крепость: ' + str(row['abv']).replace('.', ',') + '%')
    if row.get('ibu') not in (None, ''):
        parts.append('Горечь: ' + str(row['ibu']) + ' IBU')
    parts.append('Порция: ' + portion.replace('.', ',') + ' л')
    if row.get('tap_number'):
        parts.append('Кран ' + str(row['tap_number']))
    return _text('. '.join(parts), 3000)


def offers_for(rows):
    """Порции с ценой. Ключ дедупликации — бар, название и объём."""
    seen = set()
    result = []
    for row in rows:
        bar_id = row.get('bar_id')
        if bar_id not in BAR_NAMES:
            continue
        beer = _text(row.get('beer_name') or row.get('iiko_name'), 120).casefold()
        for serving in row.get('servings') or []:
            portion = _portion(serving.get('portion_liters'))
            price = _price(serving.get('price_rub'))
            if not beer or portion is None or price is None:
                continue
            key = (bar_id, beer, portion)
            if key in seen:
                continue
            seen.add(key)
            result.append({
                'id': f"{bar_id}-tap{row.get('tap_number')}-p{portion.replace('.', '')}",
                'bar_id': bar_id,
                'name': _offer_name(row, portion),
                'price': price,
                'portion': portion,
                'vendor': _text(row.get('brewery'), 80),
                'picture': _picture(row.get('photo_url')),
                'description': _description(row, portion),
                'category_id': CATEGORY_IDS[bar_id],
                'category_name': BAR_NAMES[bar_id],
            })
    return result


def build_yml(rows=None, when=None, shop_url=SHOP_URL, items=None, shop_name=None):
    """Собрать XML. Скрытые позиции (hidden) в файл не попадают."""
    when = when or generated_at()
    source = list(items if items is not None else offers_for(rows or []))
    visible = [item for item in source if not item.get('hidden')]
    bars = []
    categories = []
    for item in visible:
        bar_id = item.get('bar_id')
        if bar_id in BAR_NAMES and bar_id not in bars:
            bars.append(bar_id)
        category_id = str(item.get('category_id') or CATEGORY_IDS.get(bar_id) or '')
        category_name = item.get('category_name') or BAR_NAMES.get(bar_id) or 'Меню'
        if category_id and (category_id, category_name) not in categories:
            categories.append((category_id, category_name))
    if shop_name is None:
        shop_name = SHOP_COMPANY
        if len(bars) == 1:
            shop_name = f'{SHOP_COMPANY}, {BAR_NAMES[bars[0]]}'

    catalog = ET.Element('yml_catalog', date=when)
    shop = ET.SubElement(catalog, 'shop')
    ET.SubElement(shop, 'name').text = shop_name
    ET.SubElement(shop, 'company').text = SHOP_COMPANY
    ET.SubElement(shop, 'url').text = shop_url
    currencies = ET.SubElement(shop, 'currencies')
    ET.SubElement(currencies, 'currency', id='RUR', rate='1')
    category_box = ET.SubElement(shop, 'categories')
    for category_id, category_name in categories:
        ET.SubElement(category_box, 'category', id=category_id).text = category_name
    ET.SubElement(shop, 'delivery').text = 'false'
    ET.SubElement(shop, 'pickup').text = 'true'
    offers = ET.SubElement(shop, 'offers')
    for item in visible:
        offer = ET.SubElement(offers, 'offer', id=str(item['id']), available='true')
        ET.SubElement(offer, 'url').text = shop_url
        ET.SubElement(offer, 'price').text = str(item['price'])
        ET.SubElement(offer, 'currencyId').text = 'RUR'
        ET.SubElement(offer, 'categoryId').text = str(
            item.get('category_id') or CATEGORY_IDS.get(item.get('bar_id')))
        if item.get('picture'):
            ET.SubElement(offer, 'picture').text = item['picture']
        ET.SubElement(offer, 'name').text = item['name']
        if item.get('vendor'):
            ET.SubElement(offer, 'vendor').text = item['vendor']
        ET.SubElement(offer, 'description').text = item.get('description') or ''
        if item.get('portion'):
            ET.SubElement(offer, 'param', name='Объём', unit='л').text = str(item['portion'])
    body = ET.tostring(catalog, encoding='unicode')
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body
