"""
ABC action buckets: группировка 27 комбинаций ABC×Markup×XYZ в 6 корзин действий.

Корзина определяется первыми двумя буквами (выручка + наценка). Третья буква (XYZ /
стабильность спроса) — операционный модификатор (как планировать запас), а не
стратегическое решение.

6 корзин:
  stars        — AA*: топ во всём, держать всегда
  workhorses   — AB*, BA*: хорошая пара выручка/наценка, оставить
  price_up     — AC*, BC*: есть спрос, но низкая наценка — поднять цену
  premium      — CA*: низкий спрос при высокой наценке, продвигать
  background   — BB*, CB*: середняки, не трогать
  remove       — CC*: плохо во всём, кандидат на удаление
"""

BUCKETS = {
    'stars':      {'name': 'Звёзды',          'action': 'Держать всегда',                  'order': 1},
    'workhorses': {'name': 'Рабочие лошадки', 'action': 'Оставить',                        'order': 2},
    'price_up':   {'name': 'Недооценённые',   'action': 'Поднять наценку',                 'order': 3},
    'premium':    {'name': 'Премиум-ниша',    'action': 'Продвигать',                      'order': 4},
    'background': {'name': 'Фон',             'action': 'Не трогать',                      'order': 5},
    'remove':     {'name': 'Удалить',         'action': 'Рассмотреть удаление',            'order': 6},
}

# Выручка + наценка -> ключ корзины
_REVENUE_MARKUP_TO_BUCKET = {
    'AA': 'stars',
    'AB': 'workhorses',
    'AC': 'price_up',
    'BA': 'workhorses',
    'BB': 'background',
    'BC': 'price_up',
    'CA': 'premium',
    'CB': 'background',
    'CC': 'remove',
}


def get_bucket_key(abc_revenue, abc_markup):
    """Вернуть ключ корзины по первым двум буквам ABC."""
    return _REVENUE_MARKUP_TO_BUCKET.get(f'{abc_revenue}{abc_markup}', 'background')


def get_bucket_info(abc_revenue, abc_markup):
    """Вернуть словарь {key, name, action, order} для пары (выручка, наценка)."""
    key = get_bucket_key(abc_revenue, abc_markup)
    info = BUCKETS[key].copy()
    info['key'] = key
    return info
