"""Exact regular menu prices by department, dish GUID and current recipe.

No sales averages or name matching. See docs/taplist-v2.md for the contract.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import re
import xml.etree.ElementTree as ET

GROUP_NAMES = {'bar1': 'Большой пр. В.О', 'bar2': 'Лиговский',
               'bar3': 'Пивная культура', 'bar4': 'Варшавская'}
# Live iiko nomenclature group "Напитки Розлив", verified 2026-09-20.
DRAFT_GROUP_ID = '12369d54-4fac-41cf-904a-707fe09a8105'


def decimal(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (ValueError, InvalidOperation):
        return None


def number(value):
    return format(value.normalize(), 'f')


def current(row, day):
    return bool(row.get('dateFrom') and row['dateFrom'] <= day
                and (not row.get('dateTo') or day < row['dateTo']))


def applies(specification, department):
    if specification is None:
        return True
    included = department in specification.get('departments', [])
    return not included if specification.get('inverse') else included


def bar_contexts(groups_xml):
    groups = ET.fromstring(groups_xml)
    contexts = {}
    for bar, name in GROUP_NAMES.items():
        matches = [g for g in groups.findall('.//groupDto') if g.findtext('name') == name]
        if len(matches) == 1 and matches[0].findtext('departmentId'):
            g = matches[0]
            contexts[bar] = {'department': g.findtext('departmentId'),
                             'sections': {s.findtext('id') for s in g.findall('.//restaurantSectionInfo')}}
    return contexts


def portion(product, size=None):
    """Use the explicit sale label, then configured unit capacity. Never keg volume."""
    name = (size or {}).get('name', '') if size else product.get('name', '')
    if size:
        match = re.fullmatch(r'\s*(\d+(?:[.,]\d+)?)\s*(л|l|мл|ml)?\s*(?:\(б\))?\s*', name, re.I)
    else:
        match = re.search(r'\((\d+(?:[.,]\d+)?)\s*(л|l|мл|ml)?\)', name, re.I)
    if match:
        value = decimal(match[1].replace(',', '.'))
        if (match[2] or '').lower() in ('мл', 'ml'):
            value /= 1000
        return (value, 'iiko_size_name' if size else 'iiko_dish_name') if value > 0 else (None, None)
    capacity = decimal(product.get('unitCapacity'))
    if capacity is None or capacity <= 0:
        return None, None
    if size:
        factors = [f for f in size.get('factors', []) if f.get('startNumber', 0) <= 1]
        if not factors:
            return None, None
        factor = decimal(max(factors, key=lambda f: f.get('startNumber', 0)).get('factor'))
        if factor is None or factor <= 0:
            return None, None
        capacity *= factor
    return capacity, 'iiko_unit_capacity'


def regular_price(records, product, day):
    active = [p for p in records if current(p, day)]
    if any(p.get('schedule') is not None for p in active):
        return None, 'Есть цена по расписанию: нужна проверка', None
    if len(active) > 1:
        return None, 'Несколько действующих цен: нужна проверка', None
    if active:
        item = active[0]
        if item.get('included') is not True:
            return None, 'Порция снята с продажи', None
        price = decimal(item.get('price'))
        if price is None or price < 0:
            return None, 'Некорректная цена iiko', None
        # Owner confirmed the regular price for every bar; categories never override it.
        if price != price.quantize(Decimal('0.01')):
            return None, 'Цена точнее копейки: нужна проверка', None
        return price, None, {'kind': 'iiko_price_order', 'document_id': item.get('documentId')}
    if product.get('defaultIncludedInMenu') is not True:
        return None, 'Порция не включена в меню', None
    price = decimal(product.get('defaultSalePrice'))
    if price is None or price <= 0:
        return None, 'Цена в iiko не задана', None
    if price != price.quantize(Decimal('0.01')):
        return None, 'Цена точнее копейки: нужна проверка', None
    return price, None, {'kind': 'iiko_default_sale_price', 'document_id': None}


def enrich_prices(rows, registry, sources):
    """Attach every independently priced sale portion to its exact keg and bar."""
    day = sources['date']
    contexts = bar_contexts(sources['groups'])
    products = {p['id']: p for p in sources['products']}
    groups = {g['id']: g for g in sources['product_groups']}

    def draft_product(product):
        parent = product.get('parent')
        seen = set()
        while parent and parent not in seen:
            if parent == DRAFT_GROUP_ID:
                return True
            seen.add(parent)
            parent = groups.get(parent, {}).get('parent')
        return False
    prices = defaultdict(list)
    for entry in sources['prices']:
        prices[(entry['departmentId'], entry['productId'], entry.get('productSizeId'))].extend(entry['prices'])
    charts = defaultdict(list)
    for chart in sources['charts']:
        if current(chart, day):
            charts[chart['assembledProductId']].append(chart)
    latest = {}
    for dish, values in charts.items():
        start = max(v['dateFrom'] for v in values)
        candidates = {v['id']: v for v in values if v['dateFrom'] == start}
        if len(candidates) == 1:
            latest[dish] = next(iter(candidates.values()))
    offers = defaultdict(list)
    issues = defaultdict(set)
    keg_ids = set(registry['products'])
    wanted = {row['iiko_product_id'] for row in rows if row.get('iiko_product_id')}
    for bar in {row['bar_id'] for row in rows}:
        context = contexts.get(bar)
        if not context:
            continue
        dep = context['department']
        for dish, chart in latest.items():
            product = products.get(dish)
            if not product or product.get('deleted') or product.get('type') != 'DISH' or not draft_product(product):
                continue
            if applies(chart.get('effectiveDirectWriteoffStoreSpecification'), dep):
                continue
            if context['sections'] and context['sections'] <= set(product.get('excludedSections') or []):
                continue
            scale = sources.get('scales', {}).get(dish)
            if product.get('productScaleId'):
                if not scale or scale.get('deleted'):
                    continue
                sizes = [s for s in scale.get('productSizes', []) if not s.get('disabled') and not s.get('deleted')]
            else:
                sizes = [None]
            for size in sizes:
                size_id = size['id'] if size else None
                ingredients = {item['productId'] for item in chart.get('items', [])
                    if applies(item.get('storeSpecification'), dep)
                    and (item.get('productSizeSpecification') == size_id if chart.get('productSizeAssemblyStrategy') == 'SPECIFIC'
                         else item.get('productSizeSpecification') is None)
                    and decimal(item.get('amount')) is not None and decimal(item.get('amount')) > 0}
                kegs = ingredients & keg_ids
                if len(kegs) != 1:
                    continue
                keg = next(iter(kegs))
                if keg not in wanted:
                    continue
                key = bar, keg
                if product.get('canSetOpenPrice'):
                    issues[key].add('Свободная цена: нужна проверка')
                    continue
                records = prices.get((dep, dish, size_id), [])
                price, error, provenance = regular_price(records, product, day)
                if error:
                    if error not in ('Порция снята с продажи', 'Порция не включена в меню'):
                        issues[key].add(error)
                    continue
                volume, volume_source = portion(product, size)
                if volume is None:
                    issues[key].add('Размер порции не указан в iiko')
                    continue
                offers[key].append({'dish_id': dish, 'dish_name': product['name'],
                    'product_size_id': size_id, 'size_name': size.get('name') if size else None,
                    'portion_liters': number(volume), 'price_rub': format(price, '.2f'),
                    'currency': 'RUB', 'price_source': provenance,
                    'portion_source': volume_source, 'recipe_id': chart['id']})
    for row in rows:
        key = row['bar_id'], row.get('iiko_product_id')
        row['servings'] = sorted(offers[key], key=lambda s: (Decimal(s['portion_liters']), s['dish_name'], s['dish_id'], s['product_size_id'] or ''))
        row['prices_checked_at'] = sources['checked_at']
        warnings = sorted(issues[key])
        if row['bar_id'] not in contexts:
            warnings.append('Не найдено подразделение бара в iiko')
        if not row['servings']:
            warnings.append('Нет подтверждённой цены и порции')
        row['price_status'] = 'partial' if warnings and row['servings'] else ('unavailable' if warnings else 'verified')
        row['price_message'] = '; '.join(warnings) if warnings else 'Обычный прайс iiko'
    return rows
