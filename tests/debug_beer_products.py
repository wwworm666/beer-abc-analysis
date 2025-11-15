"""
Скрипт для отладки - выводит информацию о пивных товарах
"""
from core.olap_reports import OlapReports

def main():
    # Подключаемся к iiko
    olap = OlapReports()
    if not olap.connect():
        print("[ERROR] Не удалось подключиться к iiko API")
        return

    print("\n" + "="*60)
    print("АНАЛИЗ ПИВНЫХ ТОВАРОВ")
    print("="*60)

    # Получаем номенклатуру
    nomenclature = olap.get_nomenclature()
    if not nomenclature:
        print("[ERROR] Не удалось получить номенклатуру")
        olap.disconnect()
        return

    # Ищем товары с "пив" в названии
    beer_products = []
    for product_id, product_info in nomenclature.items():
        name = (product_info.get('name') or '').lower()
        if 'пив' in name or 'beer' in name or 'ipa' in name:
            beer_products.append({
                'id': product_id,
                'name': product_info.get('name'),
                'type': product_info.get('type'),
                'category': product_info.get('category'),
                'unit': product_info.get('mainUnit')
            })

    print(f"\n[OK] Найдено пивных товаров: {len(beer_products)}\n")

    # Группируем по типам
    types_stats = {}
    units_stats = {}

    for product in beer_products:
        ptype = product['type'] or 'NO_TYPE'
        unit = product['unit'] or 'NO_UNIT'

        if ptype not in types_stats:
            types_stats[ptype] = []
        types_stats[ptype].append(product)

        if unit not in units_stats:
            units_stats[unit] = []
        units_stats[unit].append(product)

    # Выводим статистику по типам
    print("СТАТИСТИКА ПО ТИПАМ:")
    print("-" * 60)
    for ptype, products in sorted(types_stats.items()):
        print(f"\n{ptype}: {len(products)} товаров")
        # Показываем первые 5 примеров
        for i, p in enumerate(products[:5], 1):
            print(f"  {i}. {p['name']} (единица: {p['unit']}, категория: {p['category']})")

    # Выводим статистику по единицам
    print("\n" + "="*60)
    print("СТАТИСТИКА ПО ЕДИНИЦАМ ИЗМЕРЕНИЯ:")
    print("-" * 60)
    for unit, products in sorted(units_stats.items()):
        print(f"\n{unit}: {len(products)} товаров")
        # Показываем первые 5 примеров
        for i, p in enumerate(products[:5], 1):
            print(f"  {i}. {p['name']} (тип: {p['type']}, категория: {p['category']})")

    # Ищем фасованное пиво (GOODS + шт)
    print("\n" + "="*60)
    print("ВОЗМОЖНОЕ ФАСОВАННОЕ ПИВО (GOODS + шт):")
    print("-" * 60)

    bottled_beer = [p for p in beer_products if p['type'] == 'GOODS' and p['unit'] == 'шт']
    print(f"\nНайдено: {len(bottled_beer)} товаров\n")

    for i, p in enumerate(bottled_beer[:20], 1):
        print(f"{i:2}. {p['name']}")
        print(f"    Категория: {p['category']}")
        print()

    olap.disconnect()

if __name__ == '__main__':
    main()
