"""Один YML на бар: кухня и пиво 0,5 л.

В карточке Яндекс Карт можно указать только одну ссылку.
"""
from core.taplist import BAR_NAMES

FEED_ORDER = ('bar1', 'bar2', 'bar3', 'bar4')
DRINKS_CATEGORY_ID = '100'
DRINKS_CATEGORY_NAME = 'Пиво'

# Порядок на Картах: пиво, горячие закуски, пицца, горячее мясо, закуски, десерты.
# (ранг, id раздела в файле, заголовок)
_SECTIONS = {
    '100': (0, '100', 'Пиво'),
    '2': (1, '2', 'Горячие закуски'),
    '1': (2, '1', 'Пицца'),
    '3': (3, '3', 'Горячее мясо'),
    '4': (3, '3', 'Горячее мясо'),
    '5': (4, '5', 'Закуски'),
    '6': (4, '5', 'Закуски'),
    '7': (5, '7', 'Десерты'),
}


def feed_catalog():
    return [{
        'id': bar_id,
        'kind': 'bar',
        'group': 'Бары',
        'bar_id': bar_id,
        'title': BAR_NAMES[bar_id],
        'public_path': f'/feeds/kitchen/{bar_id}',
        'ready': True,
    } for bar_id in FEED_ORDER]


def combine_offers(kitchen, drinks):
    """Пиво первым, затем кухня по заданным разделам. Внутри раздела порядок меню сохраняется."""
    rows = []
    for item in kitchen or []:
        row = dict(item)
        row['category_id'] = str(row.get('category_id') or '7')
        rows.append(row)
    for item in drinks or []:
        row = dict(item)
        row['category_id'] = DRINKS_CATEGORY_ID
        rows.append(row)
    rows.sort(key=lambda item: _SECTIONS.get(str(item.get('category_id')), (9, '9', 'Меню'))[0])
    for item in rows:
        rank = _SECTIONS.get(str(item.get('category_id')))
        if rank:
            item['category_id'] = rank[1]
            item['category_name'] = rank[2]
        else:
            item['category_name'] = item.get('category_name') or 'Меню'
    return rows


def overrides_for_bar(stored, bar_id):
    """Старые правки кухни и таплиста остаются в силе. Новые важнее."""
    bucket = {}
    stored = stored or {}
    for key in (f'kitchen-{bar_id}', f'taplist-{bar_id}', bar_id):
        bucket.update(stored.get(key) or {})
    return bucket


def feed_by_id(feed_id):
    for feed in feed_catalog():
        if feed['id'] == feed_id:
            return feed
    return None
