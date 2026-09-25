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
            })
    return result


def build_yml(rows, when=None, shop_url=SHOP_URL):
    """Собрать XML. Пустой список порций даёт валидный фид без товаров."""
    when = when or generated_at()
    bars = []
    for row in rows:
        bar_id = row.get('bar_id')
        if bar_id in BAR_NAMES and bar_id not in bars:
            bars.append(bar_id)
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
    categories = ET.SubElement(shop, 'categories')
    for bar_id in bars:
        ET.SubElement(categories, 'category', id=CATEGORY_IDS[bar_id]).text = BAR_NAMES[bar_id]
    ET.SubElement(shop, 'delivery').text = 'false'
    ET.SubElement(shop, 'pickup').text = 'true'
    offers = ET.SubElement(shop, 'offers')
    for item in offers_for(rows):
        offer = ET.SubElement(offers, 'offer', id=item['id'], available='true')
        ET.SubElement(offer, 'url').text = shop_url
        ET.SubElement(offer, 'price').text = item['price']
        ET.SubElement(offer, 'currencyId').text = 'RUR'
        ET.SubElement(offer, 'categoryId').text = CATEGORY_IDS[item['bar_id']]
        if item['picture']:
            ET.SubElement(offer, 'picture').text = item['picture']
        ET.SubElement(offer, 'name').text = item['name']
        if item['vendor']:
            ET.SubElement(offer, 'vendor').text = item['vendor']
        ET.SubElement(offer, 'description').text = item['description']
        ET.SubElement(offer, 'param', name='Объём', unit='л').text = item['portion']
    body = ET.tostring(catalog, encoding='unicode')
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body
