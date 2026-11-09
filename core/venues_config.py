"""
Конфигурация заведений для системы мультизаведений
Все 4 бара в Санкт-Петербурге
"""

# Маппинг: ключ -> полное название заведения (как в iiko API)
VENUES = {
    'bolshoy': {
        'key': 'bolshoy',
        'name': 'Большой пр. В.О',
        'full_name': 'Культура - Большой пр. В.О',
        'icon': '',  # Эмодзи удалены для совместимости с Windows
        'address': 'Большой пр. В.О',
        'taps': 24,
        'order': 1
    },
    'ligovskiy': {
        'key': 'ligovskiy',
        'name': 'Лиговский',
        'full_name': 'Культура - Лиговский',
        'icon': '',
        'address': 'Лиговский пр.',
        'taps': 24,  # с 2026-11-09; было 12
        'order': 2
    },
    'kremenchugskaya': {
        'key': 'kremenchugskaya',
        'name': 'Кременчугская',
        'full_name': 'Культура - Кременчугская',
        'icon': '',
        'address': 'ул. Кременчугская',
        'taps': 12,
        'order': 3
    },
    'varshavskaya': {
        'key': 'varshavskaya',
        'name': 'Варшавская',
        'full_name': 'Культура - Варшавская',
        'icon': '',
        'address': 'ул. Варшавская',
        'taps': 24,  # с 2026-11-09; было 12
        'order': 4
    },
    'all': {
        'key': 'all',
        'name': 'Все заведения',
        'full_name': 'Все заведения (сводно)',
        'icon': '',
        'address': 'Все бары',
        'taps': 0,  # сумма кранов баров, считается ниже (24 + 24 + 12 + 24 = 84)
        'order': 0
    }
}

# Список ключей в порядке отображения
VENUE_KEYS_ORDERED = ['all', 'bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']

# Список физических баров (без "all")
PHYSICAL_VENUES = ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']

# Краны всей сети — сумма по барам, а не число руками: поменяли краны бара — итог следует.
VENUES['all']['taps'] = sum(VENUES[key]['taps'] for key in PHYSICAL_VENUES)

# Маппинг: название в iiko -> ключ в системе
IIKO_NAME_TO_KEY = {
    'Большой пр. В.О': 'bolshoy',
    'Лиговский': 'ligovskiy',
    'Кременчугская': 'kremenchugskaya',
    'Варшавская': 'varshavskaya'
}

# Маппинг: ключ -> название в iiko API
KEY_TO_IIKO_NAME = {
    'bolshoy': 'Большой пр. В.О',
    'ligovskiy': 'Лиговский',
    'kremenchugskaya': 'Кременчугская',
    'varshavskaya': 'Варшавская',
    'all': None  # Для "all" запрашиваем все бары
}


# ---------------------------------------------------------------- таблица баров сайта
#
# Одна таблица для общего выбора бара (план единого виджета, раздел 4.2): ключ, имя, короткое
# имя, имя iiko и его варианты написания, номер bar1…bar4 (краны, фиды, сроки). Страница
# получает её в настройках полосы и передаёт ключ; старые значения сводятся к ключу через
# bar_key(). Номер точки графика берётся из базы смен по locations.venue_key, поэтому здесь
# его нет.

# Подпись всей сети — одна на сайт (ответ владельца Р6, 2026-11-01).
ALL_BARS_LABEL = 'Все бары'
ALL_BARS_HINT = 'вся сеть'

SITE_BARS = [
    {'key': 'bolshoy', 'name': 'Большой пр. В.О', 'short': 'ВО', 'bar_id': 'bar1',
     # «Большой пр В.О.» — цели KPI, «Большой пр. В.О.» — примеры бота.
     'iiko_name': 'Большой пр. В.О', 'aliases': ['Большой пр В.О.', 'Большой пр. В.О.']},
    {'key': 'ligovskiy', 'name': 'Лиговский', 'short': 'Лиг', 'bar_id': 'bar2',
     'iiko_name': 'Лиговский', 'aliases': []},
    {'key': 'kremenchugskaya', 'name': 'Кременчугская', 'short': 'Крем', 'bar_id': 'bar3',
     'iiko_name': 'Кременчугская', 'aliases': []},
    {'key': 'varshavskaya', 'name': 'Варшавская', 'short': 'Вар', 'bar_id': 'bar4',
     'iiko_name': 'Варшавская', 'aliases': []},
]

# Все написания «всей сети» на сайте (опись 2026-11-01): ключ дашборда, «Общая» склада и
# розлива, пустое значение раздела «Гости».
_ALL_SPELLINGS = {'', 'all', 'total', 'общая', 'все бары', 'вся сеть', 'все заведения', 'все точки'}


def _norm(text):
    return ' '.join(str(text).strip().lower().replace('ё', 'е').split())


_BAR_BY_SPELLING = {}
for _bar in SITE_BARS:
    for _spelling in [_bar['key'], _bar['name'], _bar['iiko_name'], _bar['bar_id']] + _bar['aliases']:
        _BAR_BY_SPELLING[_norm(_spelling)] = _bar['key']


def bar_key(raw):
    """Любое написание бара -> ключ ('bolshoy'…); вся сеть -> ''; неизвестное -> None.

    Понимает ключи, имена iiko и их варианты («Большой пр В.О.»), bar1…bar4 и все подписи
    всей сети («all», «Общая», «Все бары»…). Регистр и лишние пробелы не важны.
    """
    if raw is None:
        return ''
    text = _norm(raw)
    if text in _ALL_SPELLINGS:
        return ''
    return _BAR_BY_SPELLING.get(text)


def site_bar(key):
    """Строка таблицы баров по ключу или None."""
    for bar in SITE_BARS:
        if bar['key'] == key:
            return bar
    return None
