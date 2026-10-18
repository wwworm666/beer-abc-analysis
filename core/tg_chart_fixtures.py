"""Фикстуры мини-приложения графиков: пять графиков из прототипа и ряд по дням.

Зачем: dev-страница /tg/chart/dev (только при FLASK_DEBUG) показывает их в обеих
темах, тесты проверяют на них формат описания (core/tg_charts.normalize) и
отрисовку. Описания записаны в формате агента — так, как их прислал бы
инструмент common_chart_send.

Откуда цифры: пять графиков сняты с PNG-карточек бота (прототип мини-приложения,
октябрь 2026). Суммы в рублях — тысячи с карточки × 1000; база выручки по барам
пересчитана из подписанного процента (база = ивент / (1 + % / 100), до рубля).
Это демонстрационные данные для сверки вида, а не отчёт: в боевых графиках
агент передаёт точные значения из инструментов. Ряд по дням — выдуманный
(подписан «тестовые данные»), он нужен, чтобы проверить зум по периоду.
"""
from datetime import date, timedelta
from typing import Any, Dict, List

LITERS = {
    'kind': 'rating',
    'title': 'Литры Gravity Project',
    'subtitle': '12 окт 2025 – 11 окт 2026 · Все',
    'note': 'Кран (все объёмы вместе) и бутылки; л = порции или шт × объём из названия',
    'unit': 'л',
    'categories': [
        {'label': 'Heartless Bitch 2.0', 'tag': 'кран'},
        {'label': "It's Mango", 'tag': 'кран'},
        {'label': 'Bananed', 'tag': 'кран'},
        {'label': 'Blueberry Jam', 'tag': 'кран'},
        {'label': 'Blueberry Jam голуб.', 'tag': 'бут'},
        {'label': 'Забананен', 'tag': 'бут'},
        {'label': 'Bananed Banana', 'tag': 'бут'},
        {'label': 'Санрайз', 'tag': 'бут'},
        {'label': "It's a Mango", 'tag': 'бут'},
        {'label': 'Rexberry', 'tag': 'бут'},
        {'label': 'Blueberry Jam 0,5', 'tag': 'бут'},
        {'label': 'Молодой', 'tag': 'бут'},
        {'label': 'Russkiy Pierog', 'tag': 'ж/б'},
        {'label': 'Лет ми спик', 'tag': 'бут'},
        {'label': 'Прочие (8)', 'note': '8 позиций не разделены на кран и фасовку'},
    ],
    'series': [{'name': 'Литры', 'role': 'value',
                'data': [252.9, 28.7, 26.2, 22.0, 10.0, 9.4, 8.5, 8.5, 8.0, 6.5, 4.0, 3.1, 3.0, 2.6, 13.3]}],
    'groups': [{'label': 'Кран', 'tags': ['кран']}, {'label': 'Фасовка', 'tags': ['бут', 'ж/б']}],
    'source': 'iiko',
    'data_at': '2026-10-12T09:15:00+03:00',
}

BELGIUM = {
    'kind': 'periods',
    'title': 'Бельгия на розливе',
    'subtitle': '2–13 сен к 19–30 авг 2026 · Все',
    'note': 'Выручка сорта за 12 дней ср–вс, ₽; Гулден Драк в ивент не продавался',
    'unit': '₽',
    'categories': [
        {'label': 'Квак'},
        {'label': 'Стинбрюгге Бланш', 'short': 'Стинб.\nБланш'},
        {'label': 'Палм'},
        {'label': 'Барбе Руби', 'short': 'Барбе\nРуби'},
        {'label': 'Роденбах', 'short': 'Роден-\nбах'},
        {'label': 'Гулден Драк', 'short': 'Гулден\nДрак', 'note': 'В ивент не продавался'},
        {'label': 'Стинбрюгге Блонд', 'short': 'Стинб.\nБлонд'},
    ],
    'series': [
        {'name': '2–13 сен (ивент)', 'role': 'current',
         'data': [136000, 69000, 55000, 47000, 16000, 0, 4000]},
        {'name': '19–30 авг', 'role': 'base',
         'data': [0, 69000, 68000, 24000, 18000, 17000, 11000]},
    ],
    'source': 'iiko',
    'data_at': '2026-09-14T00:58:00+03:00',
}

CHECK = {
    'kind': 'stack',
    'title': 'Средний чек',
    'subtitle': 'до, во время и после ивента · Все',
    'note': 'Окна по 12 дней ср–вс, ₽ на чек: позиции ивента и всё остальное',
    'unit': '₽',
    'additive': False,
    'categories': ['19–30 авг', '2–13 сен', '16–27 сен'],
    'series': [
        {'name': 'Позиции ивента', 'role': 'part', 'color': 'part_light', 'data': [0, 152, 56]},
        {'name': 'Остальное', 'role': 'part', 'color': 'part_dark', 'data': [1426, 1357, 1347]},
    ],
    'base_category': '19–30 авг',
    'source': 'iiko',
    'data_at': '2026-09-28T00:58:00+03:00',
}

REVENUE = {
    'kind': 'periods',
    'title': 'Выручка · 2–13 сен к 19–30 авг 2026',
    'subtitle': 'по барам',
    'note': 'Окна по 12 дней ср–вс, ₽ со скидкой',
    'unit': '₽',
    'categories': [
        {'label': 'Большой пр. В.О.', 'short': 'ВО', 'color': 'bolshoy'},
        {'label': 'Лиговский', 'short': 'Лиг', 'color': 'ligovskiy'},
        {'label': 'Кременчугская', 'short': 'Крем', 'color': 'kremenchugskaya'},
        {'label': 'Варшавская', 'short': 'Варш', 'color': 'varshavskaya'},
    ],
    'series': [
        {'name': '2–13 сен (ивент)', 'role': 'current', 'data': [534000, 514000, 503000, 380000]},
        {'name': '19–30 авг', 'role': 'base', 'data': [506161, 491396, 601675, 355805]},
    ],
    'source': 'iiko',
    'data_at': '2026-09-14T00:58:00+03:00',
}

DESSERTS = {
    'kind': 'stack',
    'title': 'Десерты, порции',
    'subtitle': 'июн – 8 окт 2026 · по барам',
    'note': 'Порции по учётным месяцам; в июне 11 порций — один чек на Варшавской 6 июн',
    'unit': 'порций',
    'unit_forms': ['порция', 'порции', 'порций'],
    'categories': [
        {'label': 'Июнь', 'note': '11 из 13 порций — один чек на Варшавской 6 июня'},
        'Июль', 'Август', 'Сентябрь', '1–8 октября',
    ],
    'series': [
        {'name': 'Лиговский', 'role': 'part', 'color': 'ligovskiy', 'data': [0, 0, 0, 2, 3]},
        {'name': 'Кременчугская', 'role': 'part', 'color': 'kremenchugskaya', 'data': [0, 0, 4, 8, 2]},
        {'name': 'Варшавская', 'role': 'part', 'color': 'varshavskaya', 'data': [13, 8, 23, 6, 4]},
    ],
    'source': 'iiko',
    'data_at': '2026-10-08T15:24:00+03:00',
}

# Литры по дням недели (пн..вс) и множитель месяца — чтобы ряд был похож на бар:
# пятница и суббота выше, август — пик сезона. 2026 год = 2025 × 1,08 (до литра).
_WEEKDAY_LITERS = (58, 54, 61, 72, 118, 146, 97)
_MONTH_FACTOR = {7: 1.0, 8: 1.12, 9: 0.94}


def _days_fixture() -> Dict[str, Any]:
    start = date(2026, 7, 1)
    labels: List[str] = []
    base: List[int] = []
    current: List[int] = []
    day = start
    while day <= date(2026, 9, 30):
        litres = _WEEKDAY_LITERS[day.weekday()] * _MONTH_FACTOR[day.month]
        labels.append(day.isoformat())
        base.append(round(litres))
        current.append(round(litres * 1.08))
        day += timedelta(days=1)
    return {
        'kind': 'days',
        'title': 'Пример: литры розлива по дням',
        'subtitle': '1 июл – 30 сен 2026 · Все',
        'note': 'Тестовые данные для проверки зума по периоду, не из iiko',
        'unit': 'л',
        'categories': labels,
        'series': [
            {'name': '2026', 'role': 'current', 'data': current},
            {'name': '2025', 'role': 'base', 'data': base},
        ],
        'source': 'тестовые данные',
        'data_at': '2026-10-01T06:00:00+03:00',
    }


DAYS = _days_fixture()

# Порядок — как на dev-странице: пять графиков прототипа, затем ряд по дням.
FIXTURES = (
    ('liters', LITERS),
    ('belgium', BELGIUM),
    ('check', CHECK),
    ('revenue', REVENUE),
    ('desserts', DESSERTS),
    ('days', DAYS),
)
