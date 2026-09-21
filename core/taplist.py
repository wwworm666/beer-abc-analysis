"""Taplist V2: explicit product identity and reviewed characteristics.

Legacy identity migration uses literal iiko names, optionally constrained by the
stored article. It never compares a name to an Untappd name. See docs/taplist-v2.md.
"""
import json
from pathlib import Path
from uuid import UUID

from core.untappd_registry import resolve_beer

PRODUCTS_PATH = Path(__file__).resolve().parents[1] / 'data/all_products.json'
BAR_NAMES = {'bar1': 'Большой пр. В.О', 'bar2': 'Лиговский',
             'bar3': 'Кременчугская', 'bar4': 'Варшавская'}


def product_catalog(registry, products_path=PRODUCTS_PATH):
    """Keep separate GUIDs even when names or articles coincide."""
    catalog = {}
    for guid, row in registry['products'].items():
        if row['status'] == 'excluded':
            continue
        catalog[guid] = {'id': guid, 'name': row['iiko_name'].strip(),
                         'num': row['iiko_article'], 'names': {row['iiko_name'].strip()},
                         'articles': {str(row['iiko_article'] or '')}}
    path = Path(products_path)
    products = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else []
    for product in products:
        try:
            guid = str(UUID(str(product.get('id'))))
        except (ValueError, TypeError, AttributeError):
            continue
        name = (product.get('name') or '').strip()
        if not name or registry['products'].get(guid, {}).get('status') == 'excluded':
            continue
        if guid not in catalog:
            if product.get('deleted') in (True, 'true') or not name.upper().startswith(('КЕГ ', 'KEG ')):
                continue
            catalog[guid] = {'id': guid, 'name': name, 'num': product.get('num'),
                             'names': set(), 'articles': set()}
        catalog[guid]['names'].add(name)
        catalog[guid]['articles'].add(str(product.get('num') or ''))
    return catalog


def legacy_product_id(tap, catalog):
    """One exact local identity or none; never use an article on its own."""
    name = (tap.get('current_beer') or '').strip()
    article = str(tap.get('current_keg_id') or '').strip()
    matches = [guid for guid, item in catalog.items() if name in item['names']
               and (not article or article.startswith('AUTO-') or article in item['articles'])]
    return matches[0] if len(matches) == 1 else None


def tap_details(tap, registry):
    guid = tap.get('iiko_product_id')
    card = resolve_beer(registry, guid)
    status = 'verified' if card else ('missing_product' if not guid else 'unverified')
    description = card.get('description') if card else None
    description_source = 'untappd' if description else None
    if card and not description:
        facts = []
        if card.get('style'):
            facts.append('Стиль: ' + card['style'])
        if card.get('abv_percent') is not None:
            facts.append('Крепость: ' + str(card['abv_percent']).replace('.', ',') + '%')
        if card.get('ibu') is not None:
            facts.append('Горечь: ' + str(card['ibu']) + ' IBU')
        description = '. '.join(facts) + '.' if facts else None
        description_source = 'verified_characteristics' if facts else None
    return {'iiko_product_id': guid, 'iiko_name': tap.get('current_beer'),
            'beer_name': card['beer_name'] if card else tap.get('current_beer'),
            'brewery': card.get('brewery') if card else None,
            'untappd_beer_id': card['id'] if card else None,
            'untappd_url': card['url'] if card else None,
            'style': card.get('style') if card else None,
            'abv': card.get('abv_percent') if card else None,
            'ibu': card.get('ibu') if card else None,
            'description': description, 'description_source': description_source,
            'photo_url': card.get('photo_url') if card else None,
            'photo_kind': card.get('photo_kind') if card else None,
            'description_is_excerpt': card.get('description_is_excerpt', False) if card else False,
            'media_source_url': card.get('media_source_url') if card else None,
            'observed_at': card.get('observed_at') if card else None,
            'mapped': card is not None, 'mapping_status': status,
            'mapping_message': {'verified': 'Связь проверена',
                                'missing_product': 'Уточните сорт на кране',
                                'unverified': 'Нет проверенной связи с Untappd'}[status]}


class UnknownBar(KeyError):
    """Запрошен бар, которого нет в снимке кранов.

    Отдельный тип, потому что маршрут отвечает на него 404. Обычный KeyError
    прилетает и из разбора ответа iiko, и выдавать его за неизвестный бар —
    значит показывать владельцу «Бар не найден» вместо настоящей причины.
    Наследуется от KeyError: прежние обработчики продолжают работать.
    """


def full_taplist(snapshot, registry, bar_id=None, active_only=True):
    if bar_id is not None and bar_id not in snapshot:
        raise UnknownBar('Бар не найден')
    result = []
    for bid, bar in snapshot.items():
        if bar_id is not None and bar_id != bid:
            continue
        for tap in bar['taps']:
            if not tap.get('current_beer') or (active_only and tap['status'] != 'active'):
                continue
            result.append({'bar': BAR_NAMES.get(bid, bar['name']), 'bar_id': bid,
                           'tap_number': tap['tap_number'], 'started_at': tap.get('started_at'),
                           **tap_details(tap, registry)})
    return result
