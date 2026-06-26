"""Список GTIN, которые бар реально держит на остатке (фасовка in-stock) —
для ТОЧЕЧНОЙ выгрузки ЧЗ через /cises/search (фильтр `gtins`).

Зачем: с 2026-06 коды выводятся из оборота при приёмке, и /cises/search «по
ownerInn без gtins» отдаёт лишь ~20 высокообъёмных GTIN (newest-first, длинный
хвост каталога недостижим). Поэтому спрашиваем ЧЗ ровно про те GTIN, что есть на
остатке в iiko. Источник GTIN — iiko balances + nomenclature (группа «Напитки
Фасовка») + баркоды из nomenclature__products.xml.

Модуль без Flask-зависимостей — его импортит и веб-приложение, и remote_exec.
"""
from core.olap_reports import OlapReports
from core.iiko_barcodes import get_barcode_map, invert_to_product_gtins

# Группа «Напитки Фасовка» (та же, что в routes/expiration.py).
FASOVKA_GROUP_ID = "6103ecbf-e6f8-49fe-8cd2-6102d49e14a6"
FASOVKA_GROUP_NAME = "Напитки Фасовка"


def compute_needed_gtins(olap=None):
    """Вернуть отсортированный список GTIN-14 фасовки, что сейчас на остатке.

    olap: переиспользовать готовое подключение OlapReports (иначе создаст своё).
    Пустой список — если iiko недоступен (вызывающий код решает, что делать).
    """
    own = olap is None
    if own:
        olap = OlapReports()
        if not olap.connect():
            return []
    try:
        from extensions import get_cached_nomenclature
        nom = get_cached_nomenclature(olap) or {}
        fasovka = {
            pid for pid, info in nom.items()
            if info.get("parentId") in (FASOVKA_GROUP_ID, FASOVKA_GROUP_NAME)
        }
        if not fasovka:
            fasovka = olap.get_products_in_group(FASOVKA_GROUP_ID, nom)

        balances = olap.get_store_balances() or []
        instock = {
            b.get("product") for b in balances
            if b.get("product") in fasovka and float(b.get("amount", 0) or 0) > 0
        }

        barcode_map = get_barcode_map()
        product_to_gtins = invert_to_product_gtins(barcode_map)
        gtins = set()
        for pid in instock:
            for g in product_to_gtins.get(pid, []):
                gtins.add(g)
        return sorted(gtins)
    finally:
        if own:
            olap.disconnect()
