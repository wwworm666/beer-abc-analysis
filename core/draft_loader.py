# -*- coding: utf-8 -*-
"""Общий загрузчик сырых данных страницы /draft (проливы по кегам).

До 2026-09-04 три запроса к iiko (проводки кегов, продажи розлива с DishId,
техкарты) жили вложенной функцией fetch() внутри вьюхи /api/draft-kegs
(routes/analysis.py) и переиспользовать их было нельзя. Теперь тот же набор
данных нужен карточкам розлива на дашборде (вкладка «Литры»), поэтому загрузчик
вынесен сюда. Ключ кэша НЕ изменился: при совпадении бара и периода страница
/draft и карточка дашборда читают одну запись кэша, и цифры у них равны по
построению.

Что возвращается: {'transactions': [...], 'sales': [...], 'dish_map': {...},
'fetched_at': 'ЧЧ:ММ'} - сырьё для core/draft_kegs.py::DraftKegAnalysis, либо
None при сбое iiko (не кэшируется).

Границы периода: date_from/date_to ВКЛЮЧИТЕЛЬНО, как на экране; +1 день к
date_to для iiko (правая граница DateRange эксклюзивная) делается здесь.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.olap_reports import OlapReports
from extensions import cached_olap


def draft_kegs_cache_key(bar_name, date_from, olap_date_to):
    """Ключ кэша /draft: bar_name - iiko-имя бара или None (все бары)."""
    return f"draft_kegs_{bar_name or 'ALL'}_{date_from}_{olap_date_to}"


def load_draft_kegs(bar_name, date_from, date_to):
    """
    Сырые данные проливов из общего кэша (TTL 10 мин, single-flight).

    Args:
        bar_name: iiko-имя бара ('Лиговский', ...) или None для всех баров
        date_from, date_to: 'YYYY-MM-DD', обе даты включительно

    Returns:
        dict {'transactions', 'sales', 'dish_map', 'fetched_at'} или None при сбое iiko
    """
    olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d')
                    + timedelta(days=1)).strftime('%Y-%m-%d')
    cache_key = draft_kegs_cache_key(bar_name, date_from, olap_date_to)

    def fetch():
        olap = OlapReports()
        if not olap.connect():
            return None
        try:
            # Порядок важен: связь с iiko рвётся, и если упал первый запрос,
            # остальные только жгут бюджет gunicorn --timeout впустую.
            transactions = olap.get_draft_writeoff_report(date_from, olap_date_to, bar_name)
            if transactions is None:
                return None
            sales = olap.get_draft_sales_by_dish(date_from, olap_date_to, bar_name)
            if sales is None:
                return None
            dish_map = olap.get_dish_ingredient_map(date_from, olap_date_to)
        finally:
            olap.disconnect()

        if dish_map is None:
            return None
        return {
            'transactions': transactions.get('data') or [],
            'sales': sales.get('data') or [],
            'dish_map': dish_map,
            # Когда данные реально забраны из iiko. Лежит внутри кэша, поэтому
            # «обновлено» на странице показывает возраст цифр, а не момент клика.
            'fetched_at': datetime.now(ZoneInfo('Europe/Moscow')).strftime('%H:%M'),
        }

    return cached_olap(cache_key, fetch)
