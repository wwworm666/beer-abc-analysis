"""Кухня для страницы фидов Яндекса.

Меню одно на все точки: в Яндекс Облаке лежал общий каталог, не четыре разных.
offers_for_bar возвращает те же блюда для каждого бара, чтобы карточка точки
могла взять свою ссылку.
"""
from core.kitchen_menu import catalog_offers
from core.taplist import BAR_NAMES


def offers_for_bar(bar_id):
    if bar_id not in BAR_NAMES:
        return []
    items = []
    for item in catalog_offers():
        row = dict(item)
        row['bar_id'] = bar_id
        items.append(row)
    return items
