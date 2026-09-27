"""Один YML на бар: кухня и пиво 0,5 л.

В карточке Яндекс Карт можно указать только одну ссылку на прайс-лист.
"""
from core.taplist import BAR_NAMES

FEED_ORDER = ('bar1', 'bar2', 'bar3', 'bar4')
DRINKS_CATEGORY_ID = '100'
# Меню кухни одно на все бары, поэтому и правки кухни общие: ключ 'kitchen'.
# Правки пива — по бару: ключ 'bar1'…'bar4'.
KITCHEN_SCOPE = 'kitchen'

# Порядок разделов в файле и в кабинете: розлив, горячие закуски, пицца,
# горячее мясо, закуски, десерты. На самих Картах Яндекс упорядочивает
# разделы сам (справка «Прайс-лист компании»), файл на это не влияет.
# (ранг, id раздела в файле, заголовок)
_SECTIONS = {
    '100': (0, '100', 'Разливное'),
    '2': (1, '2', 'Горячие закуски'),
    '1': (2, '1', 'Пицца'),
    '3': (3, '3', 'Горячее мясо'),
    '4': (3, '3', 'Горячее мясо'),
    '5': (4, '5', 'Закуски'),
    '6': (4, '5', 'Закуски'),
    '7': (5, '7', 'Десерты'),
}
# Блюдо без раздела в исходном меню: отдельный раздел в конце, а не «Десерты».
_NO_SECTION = (9, '99', 'Меню')


def feed_catalog():
    return [{
        'id': bar_id,
        'kind': 'bar',
        'bar_id': bar_id,
        'title': BAR_NAMES[bar_id],
        'public_path': f'/feeds/kitchen/{bar_id}',
    } for bar_id in FEED_ORDER]


def _section(category_id):
    if not category_id:
        return _NO_SECTION
    return _SECTIONS.get(category_id)


def combine_offers(kitchen, drinks):
    """Пиво первым, затем кухня по разделам. Внутри раздела порядок меню сохраняется."""
    rows = []
    for item in kitchen or []:
        row = dict(item)
        row['kind'] = 'kitchen'
        row['category_id'] = str(row.get('category_id') or '')
        rows.append(row)
    for item in drinks or []:
        row = dict(item)
        row['kind'] = 'beer'
        row['category_id'] = DRINKS_CATEGORY_ID
        rows.append(row)
    rows.sort(key=lambda item: (_section(item['category_id']) or (8, '', ''))[0])
    for item in rows:
        section = _section(item['category_id'])
        if section:
            item['category_id'] = section[1]
            item['category_name'] = section[2]
        else:
            item['category_name'] = item.get('category_name') or 'Меню'
    return rows


def legacy_scopes(bar_id):
    """Ключи правок до 2026-09-27: кухня и таплист хранились по бару отдельно."""
    return (f'kitchen-{bar_id}', f'taplist-{bar_id}')


def overrides_for_bar(stored, bar_id):
    """Правки, которые действуют в фиде бара. Позже в списке — важнее.

    Общая правка кухни < старые ключи бара < правка бара.
    """
    bucket = {}
    stored = stored or {}
    for key in (KITCHEN_SCOPE, *legacy_scopes(bar_id), bar_id):
        bucket.update(stored.get(key) or {})
    return bucket


def bar_scoped(stored, bar_id, offer_id):
    """Правка задана именно для этого бара (а не общая правка кухни)."""
    stored = stored or {}
    return any(offer_id in (stored.get(key) or {}) for key in (*legacy_scopes(bar_id), bar_id))


def feed_by_id(feed_id):
    for feed in feed_catalog():
        if feed['id'] == feed_id:
            return feed
    return None
