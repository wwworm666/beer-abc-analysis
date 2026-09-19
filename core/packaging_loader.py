# -*- coding: utf-8 -*-
"""Загрузчик сырых данных страницы /packaging (фасовка): продажи + проводки.

Устроен как core/draft_loader.py и по той же причине: два запроса к iiko
должны жить под ОДНИМ ключом кэша, иначе продажи и склад за один и тот же
период могут приехать из разных моментов времени, и «продано по кассе» будет
расходиться с «продано по складу» просто из-за возраста данных.

Что возвращается: {'sales': [...], 'transactions': [...], 'fetched_at': 'ЧЧ:ММ'}
— сырьё для core/packaging_analysis.py::PackagingAnalysis, либо None при сбое
iiko (не кэшируется). Продажи приходят с DishId — по нему проводки склада
связываются с позициями таблицы (core/packaging_losses.py).

Ключ кэша НОВЫЙ (не «packaging:{bar}:{from}:{to}», под которым до 2026-09-19
лежал голый ответ по продажам): старая запись хранит другую форму, и десять
минут после выкатки отдала бы данные без проводок.

Границы периода: date_from/date_to ВКЛЮЧИТЕЛЬНО, как на экране; +1 день к
date_to для iiko (правая граница DateRange эксклюзивная) делается здесь, один
раз для обоих отчётов.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.olap_reports import OlapReports
from extensions import cached_olap


def packaging_cache_key(bar_name, date_from, olap_date_to):
    """Ключ кэша /packaging: bar_name — iiko-имя бара или None (все бары)."""
    return f"packaging_{bar_name or 'ALL'}_{date_from}_{olap_date_to}"


def load_packaging(bar_name, date_from, date_to):
    """
    Сырые данные фасовки из общего кэша (TTL 10 мин, single-flight).

    Args:
        bar_name: iiko-имя бара ('Лиговский', ...) или None для всех баров
        date_from, date_to: 'YYYY-MM-DD', обе даты включительно

    Returns:
        dict {'sales', 'transactions', 'fetched_at'} или None при сбое iiko
    """
    olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d')
                    + timedelta(days=1)).strftime('%Y-%m-%d')
    cache_key = packaging_cache_key(bar_name, date_from, olap_date_to)

    def fetch():
        olap = OlapReports()
        if not olap.connect():
            return None
        try:
            # Порядок важен: связь с iiko рвётся, и если упал первый запрос,
            # второй только жжёт бюджет gunicorn --timeout впустую. Частичный
            # ответ не кэшируется: страница либо целая, либо «ошибка iiko».
            transactions = olap.get_packaging_writeoff_report(date_from, olap_date_to, bar_name)
            if transactions is None:
                return None
            sales = olap.get_packaging_sales_report(date_from, olap_date_to, bar_name)
            if sales is None:
                return None
        finally:
            olap.disconnect()

        return {
            'sales': sales.get('data') or [],
            'transactions': transactions.get('data') or [],
            # Когда данные реально забраны из iiko. Лежит внутри кэша, поэтому
            # «обновлено» на странице показывает возраст цифр, а не момент клика.
            'fetched_at': datetime.now(ZoneInfo('Europe/Moscow')).strftime('%H:%M'),
        }

    return cached_olap(cache_key, fetch)
