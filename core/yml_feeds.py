"""Список YML-фидов для страницы управления.

Розлив — по одному файлу на бар, из текущих кранов.
Кухня — один общий файл меню, его собирает core.kitchen_menu.
"""
from core.taplist import BAR_NAMES

FEED_ORDER = ('bar1', 'bar2', 'bar3', 'bar4')


def feed_catalog():
    feeds = []
    for bar_id in FEED_ORDER:
        feeds.append({
            'id': f'taplist-{bar_id}',
            'kind': 'taplist',
            'group': 'Розлив',
            'bar_id': bar_id,
            'title': BAR_NAMES[bar_id],
            'public_path': f'/feeds/taplist.yml?bar={bar_id}',
            'ready': True,
        })
    for bar_id in FEED_ORDER:
        feeds.append({
            'id': f'kitchen-{bar_id}',
            'kind': 'kitchen',
            'group': 'Кухня',
            'bar_id': bar_id,
            'title': BAR_NAMES[bar_id],
            'public_path': f'/feeds/kitchen/{bar_id}',
            'ready': True,
        })
    return feeds


def feed_by_id(feed_id):
    for feed in feed_catalog():
        if feed['id'] == feed_id:
            return feed
    return None
