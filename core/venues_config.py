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
        'taps': 12,
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
        'taps': 12,
        'order': 4
    },
    'all': {
        'key': 'all',
        'name': 'Все заведения',
        'full_name': 'Все заведения (сводно)',
        'icon': '',
        'address': 'Все бары',
        'taps': 60,  # Сумма всех кранов
        'order': 0
    }
}

# Список ключей в порядке отображения
VENUE_KEYS_ORDERED = ['all', 'bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']

# Список физических баров (без "all")
PHYSICAL_VENUES = ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']

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
