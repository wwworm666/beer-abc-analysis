"""Один YML на бар: кухня и пиво 0,5 л.

В карточке Яндекс Карт можно указать только одну ссылку.
"""
from core.taplist import BAR_NAMES

FEED_ORDER = ('bar1', 'bar2', 'bar3', 'bar4')
DRINKS_CATEGORY_ID = '100'
DRINKS_CATEGORY_NAME = 'Напитки'


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
    """Кухня сохраняет свои разделы. Пиво садится в отдельный раздел «Напитки»."""
    rows = []
    for item in kitchen or []:
        row = dict(item)
        row['category_id'] = str(row.get('category_id') or '1')
        row['category_name'] = row.get('category_name') or 'Кухня'
        rows.append(row)
    for item in drinks or []:
        row = dict(item)
        row['category_id'] = DRINKS_CATEGORY_ID
        row['category_name'] = DRINKS_CATEGORY_NAME
        rows.append(row)
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
