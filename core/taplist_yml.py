"""YML-фид разливного пива для Яндекс Бизнеса / Карт и сборка XML.

Формат — Yandex Market Language: yml_catalog, shop, categories, offers.
В фид попадает одна порция 0,5 л на сорт в баре. Правила выбора цены, id
позиции и текста описаны в docs/yandex-feeds.md.
"""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from core.taplist import BAR_NAMES

SHOP_COMPANY = 'Пивная культура'
SHOP_URL = 'https://beerkultura.ru'
# Справка Яндекс Бизнеса: currencyId — одно из RUB, KZT, BYN.
CURRENCY = 'RUB'
CATEGORY_IDS = {'bar1': '1', 'bar2': '2', 'bar3': '3', 'bar4': '4'}
HALF_LITER = Decimal('0.5')
_CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]')
# Порция навынос: размер «0,5 (б)» или блюдо «... (0,5) (б)» / «с собой».
# В карточке заведения показываем цену в зале, навынос в фид не идёт.
_TAKEAWAY = re.compile(r'\(\s*б\s*\)|с\s+собой|навынос', re.IGNORECASE)
# Служебные слова пивоварни. «Brouwerij Palm» + «Palm Spéciale»: пивоварня уже
# есть в начале названия сорта, второй раз её не добавляем.
_BREWERY_WORDS = {
    'brouwerij', 'brasserie', 'pivovar', 'pivovarna', 'brewery', 'brewing', 'brewers',
    'brewhouse', 'company', 'bryggeri', 'birrificio', 'brauerei', 'the', 'and',
    'пивоварня', 'пивоваренный', 'пивоваренная', 'завод', 'компания',
}
_SAFE_ID = re.compile(r'^[A-Za-z0-9]{1,40}$')


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


def money(price) -> str:
    """'1580.00' -> '1580', '490.50' -> '490,50'. Для подписей, не для XML."""
    text = str(price or '')
    if text.endswith('.00'):
        text = text[:-3]
    return text.replace('.', ',')


def _date(value) -> str:
    """'2026-03-01' или '2026-03-01T00:00:00' -> '01.03.2026'."""
    match = re.match(r'(\d{4})-(\d{2})-(\d{2})', str(value or ''))
    return f'{match[3]}.{match[2]}.{match[1]}' if match else ''


def offer_id(bar_id, untappd_id) -> str:
    """Позиция пива привязана к сорту (карточка Untappd), а не к крану:
    смена кеги не переносит правки на другой сорт, переезд на другой кран
    их не теряет."""
    return f'{bar_id}-u{untappd_id}-p05'


def is_takeaway(serving) -> bool:
    text = f"{serving.get('dish_name') or ''} {serving.get('size_name') or ''}"
    return bool(_TAKEAWAY.search(text))


def price_source_label(serving) -> str:
    source = serving.get('price_source') or {}
    if source.get('kind') == 'iiko_price_order':
        day = _date(source.get('date_from'))
        return f'приказ iiko от {day}' if day else 'приказ iiko'
    return 'цена по умолчанию в iiko'


def _dish_label(serving) -> str:
    name = serving.get('dish_name') or 'блюдо без названия'
    if serving.get('size_name'):
        name += ' / ' + serving['size_name']
    return name


def choose_serving(servings):
    """Какая порция 0,5 л даёт цену. -> (порция | None, предупреждение, причина отказа).

    1. Берутся порции ровно 0,5 л с ценой > 0.
    2. Навынос («(б)», «с собой») отбрасывается.
    3. Одна цена у всех оставшихся блюд — она и идёт в фид.
    4. Цены разные — берётся цена из самого свежего приказа (dateFrom),
       с предупреждением. Если у самых свежих приказов цены всё равно разные
       или дат нет, сорт в фид не идёт: угадывать цену нельзя.
    """
    servings = list(servings or [])
    half = [s for s in servings
            if _portion(s.get('portion_liters')) is not None
            and Decimal(_portion(s.get('portion_liters'))) == HALF_LITER
            and _price(s.get('price_rub'))]
    if not half:
        portions = sorted({_portion(s.get('portion_liters')) for s in servings
                           if _portion(s.get('portion_liters'))}, key=Decimal)
        if portions:
            listed = ', '.join(p.replace('.', ',') + ' л' for p in portions)
            return None, None, f'В iiko нет порции 0,5 л (есть: {listed})'
        return None, None, None
    in_house = [s for s in half if not is_takeaway(s)]
    if not in_house:
        return None, None, 'Порция 0,5 л есть только навынос'
    if len({_price(s['price_rub']) for s in in_house}) == 1:
        return in_house[0], None, None
    listing = '; '.join(
        f'«{_dish_label(s)}» {money(_price(s["price_rub"]))} ₽ ({price_source_label(s)})'
        for s in in_house)
    dated = [s for s in in_house if (s.get('price_source') or {}).get('date_from')]
    if dated:
        newest = max(s['price_source']['date_from'] for s in dated)
        top = [s for s in dated if s['price_source']['date_from'] == newest]
        if len({_price(s['price_rub']) for s in top}) == 1:
            note = (f'Несколько блюд 0,5 л с разной ценой: {listing}. Взята цена из самого '
                    f'свежего приказа. Лишние блюда уберите из техкарт этой кеги в iiko.')
            return top[0], note, None
    return None, None, (f'Разные цены 0,5 л, самый свежий приказ не определить: {listing}. '
                        f'Оставьте в iiko одно блюдо 0,5 л на эту кегу.')


def _words(text):
    return re.findall(r'\w+', text.casefold())


def _brewery_in_name(brewery, beer) -> bool:
    if brewery.casefold() in beer.casefold():
        return True
    own = [w for w in _words(brewery) if w not in _BREWERY_WORDS and len(w) >= 3]
    first = _words(beer)[:1]
    return bool(own and first and first[0] in own)


def _offer_name(row, portion):
    beer = _text(row.get('beer_name') or row.get('iiko_name'), 120)
    brewery = _text(row.get('brewery'), 80)
    if brewery and not _brewery_in_name(brewery, beer):
        beer = f'{brewery} {beer}'.strip()
    volume = portion.replace('.', ',')
    return _text(f'{beer}, {volume} л', 200)


def _sentence(text):
    text = text.strip()
    if not text:
        return ''
    return text if text[-1] in '.!?…' else text + '.'


def _description(row, portion):
    """Текст Untappd, затем стиль, крепость и горечь, затем объём порции.

    Если описания в Untappd нет, text уже собран из стиля/крепости/горечи
    (description_source='verified_characteristics') — второй раз не добавляем.
    Служебные пометки Untappd после «NB:» (про бутылки, партии) отрезаются.
    Выдержка Untappd обрезана с «...», часто после точки («bread....»):
    любая серия из двух и больше точек становится одним «…».
    """
    parts = []
    text = _text(row.get('description'), 1500)
    text = text.split('NB:', 1)[0].strip()
    text = re.sub(r'\.{2,}', '…', text)
    if text:
        parts.append(_sentence(text))
    if row.get('description_source') != 'verified_characteristics':
        if row.get('style'):
            parts.append(_sentence('Стиль: ' + _text(row['style'], 120)))
        if row.get('abv') not in (None, ''):
            parts.append('Крепость: ' + str(row['abv']).replace('.', ',') + '%.')
        if row.get('ibu') not in (None, ''):
            parts.append('Горечь: ' + str(row['ibu']) + ' IBU.')
    parts.append('Порция: ' + portion.replace('.', ',') + ' л.')
    return _text(' '.join(parts), 3000)


def beer_offers(rows):
    """Пиво 0,5 л для фида. -> (позиции, не попавшие в фид с причиной).

    Один сорт в баре — одна позиция, даже если он стоит на двух кранах
    (номера кранов собираются в taps). В фид идут только сорта с проверенной
    карточкой Untappd: без неё нет ни стабильного id, ни пивоварни, ни названия
    кроме «КЕГ …» из iiko.
    """
    items, excluded, seen = [], [], {}
    for row in rows or []:
        bar_id = row.get('bar_id')
        if bar_id not in BAR_NAMES:
            continue
        tap = row.get('tap_number')
        untappd = str(row.get('untappd_beer_id') or '')
        label = _text(row.get('beer_name') or row.get('iiko_name'), 120) or 'Без названия'
        verified = row.get('mapping_status') == 'verified' and _SAFE_ID.match(untappd)
        key = (bar_id, untappd if verified else f"tap{tap}")
        if key in seen:
            seen[key]['taps'].append(tap)
            continue
        entry = {'bar_id': bar_id, 'taps': [tap], 'name': label}
        seen[key] = entry
        if not verified:
            entry['reason'] = 'Нет проверенной карточки сорта: уточните сорт на странице кранов'
            excluded.append(entry)
            continue
        serving, note, reason = choose_serving(row.get('servings'))
        if serving is None:
            entry['reason'] = reason or row.get('price_message') or 'Нет цены в iiko'
            excluded.append(entry)
            continue
        portion = _portion(serving['portion_liters'])
        warnings = [note] if note else []
        if row.get('price_status') == 'partial' and row.get('price_message'):
            warnings.append('Часть порций этой кеги в iiko не проверена: ' + row['price_message'])
        brewery = _text(row.get('brewery'), 80)
        if not brewery:
            warnings.append('Нет пивоварни: Яндекс может не принять позицию без vendor')
        item = {
            'id': offer_id(bar_id, untappd),
            'kind': 'beer',
            'bar_id': bar_id,
            'taps': entry['taps'],
            'keg_id': row.get('iiko_product_id'),
            'name': _offer_name(row, portion),
            'price': _price(serving['price_rub']),
            'price_source': price_source_label(serving),
            'price_dish': _dish_label(serving),
            'portion': portion,
            'vendor': brewery,
            'picture': _picture(row.get('photo_url')),
            'description': _description(row, portion),
            'category_id': CATEGORY_IDS[bar_id],
            'category_name': BAR_NAMES[bar_id],
            'warnings': warnings,
        }
        entry['id'] = item['id']
        items.append(item)
    return items, excluded


def offers_for(rows):
    """Только позиции (без списка исключённых) — для общего фида всех баров."""
    return beer_offers(rows)[0]


def build_yml(rows=None, when=None, shop_url=SHOP_URL, items=None, shop_name=None):
    """Собрать XML. Скрытые позиции (hidden) в файл не попадают.

    <url> у позиций не пишется: поле необязательное, а корень сайта — это
    дашборд за логином, гостю туда незачем.
    """
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
    ET.SubElement(currencies, 'currency', id=CURRENCY, rate='1')
    category_box = ET.SubElement(shop, 'categories')
    for category_id, category_name in categories:
        ET.SubElement(category_box, 'category', id=category_id).text = category_name
    ET.SubElement(shop, 'delivery').text = 'false'
    ET.SubElement(shop, 'pickup').text = 'true'
    offers = ET.SubElement(shop, 'offers')
    for item in visible:
        offer = ET.SubElement(offers, 'offer', id=str(item['id']), available='true')
        ET.SubElement(offer, 'price').text = str(item['price'])
        ET.SubElement(offer, 'currencyId').text = CURRENCY
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
