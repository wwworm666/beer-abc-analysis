# -*- coding: utf-8 -*-
"""Загрузчик сырых данных страницы /kitchen (кухня): продажи + проводки.

Копия core/packaging_loader.py по устройству и по причине: два запроса к iiko
живут под ОДНИМ ключом кэша, иначе продажи и склад за один период приехали бы
из разных моментов времени, и сверка «касса против склада» расходилась бы из-за
возраста данных.

Что возвращается: {'sales': [...], 'transactions': [...], 'fetched_at': 'ЧЧ:ММ'}
— сырьё для core/kitchen_analysis.py::KitchenAnalysis, либо None при сбое iiko
(не кэшируется).

Границы периода: date_from/date_to ВКЛЮЧИТЕЛЬНО, как на экране; +1 день к
date_to для iiko (правая граница DateRange эксклюзивная) делается здесь.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.olap_reports import OlapReports
from extensions import cached_olap


def kitchen_cache_key(bar_name, date_from, olap_date_to):
    """Ключ кэша /kitchen: bar_name — iiko-имя бара или None (все бары)."""
    return f"kitchen_{bar_name or 'ALL'}_{date_from}_{olap_date_to}"


def load_kitchen(bar_name, date_from, date_to):
    """
    Сырые данные кухни из общего кэша (TTL 10 мин, single-flight).

    Args:
        bar_name: iiko-имя бара ('Лиговский', ...) или None для всех баров
        date_from, date_to: 'YYYY-MM-DD', обе даты включительно

    Returns:
        dict {'sales', 'transactions', 'fetched_at'} или None при сбое iiko
    """
    olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d')
                    + timedelta(days=1)).strftime('%Y-%m-%d')
    cache_key = kitchen_cache_key(bar_name, date_from, olap_date_to)

    def fetch():
        olap = OlapReports()
        if not olap.connect():
            return None
        try:
            # Порядок и правила те же, что у фасовки: упал первый запрос —
            # второй не делаем; ответ без ключа data — сбой, а не «пусто».
            transactions = olap.get_kitchen_writeoff_report(date_from, olap_date_to, bar_name)
            if not isinstance(transactions, dict) or 'data' not in transactions:
                return None
            sales = olap.get_kitchen_page_sales_report(date_from, olap_date_to, bar_name)
            if not isinstance(sales, dict) or 'data' not in sales:
                return None
        finally:
            olap.disconnect()

        return {
            'sales': sales.get('data') or [],
            'transactions': transactions.get('data') or [],
            'fetched_at': datetime.now(ZoneInfo('Europe/Moscow')).strftime('%H:%M'),
        }

    return cached_olap(cache_key, fetch)
