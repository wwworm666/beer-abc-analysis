"""
Тест для проверки получения товаров из группы "Напитки Фасовка"
"""
from core.olap_reports import OlapReports

def main():
    # Подключаемся к iiko
    olap = OlapReports()
    if not olap.connect():
        print("[ERROR] Не удалось подключиться к iiko API")
        return

    print("\n" + "="*80)
    print("ТЕСТ ПОЛУЧЕНИЯ ТОВАРОВ ИЗ ГРУППЫ 'НАПИТКИ ФАСОВКА'")
    print("="*80)

    # ID группы "Напитки Фасовка"
    FASOVKA_GROUP_ID = '6103ecbf-e6f8-49fe-8cd2-6102d49e14a6'

    # Получаем номенклатуру
    nomenclature = olap.get_nomenclature()
    if not nomenclature:
        print("[ERROR] Не удалось получить номенклатуру")
        olap.disconnect()
        return

    print(f"\n[OK] Получено товаров всего: {len(nomenclature)}")

    # Получаем товары из группы "Напитки Фасовка"
    fasovka_ids = olap.get_products_in_group(FASOVKA_GROUP_ID, nomenclature)

    print(f"[OK] Товаров в группе 'Напитки Фасовка': {len(fasovka_ids)}\n")

    # Показываем статистику по типам и единицам
    types_stats = {}
    units_stats = {}

    for product_id in fasovka_ids:
        product_info = nomenclature.get(product_id)
        if not product_info:
            continue

        ptype = product_info.get('type', 'NO_TYPE')
        unit = product_info.get('mainUnit', 'NO_UNIT')

        if ptype not in types_stats:
            types_stats[ptype] = 0
        types_stats[ptype] += 1

        if unit not in units_stats:
            units_stats[unit] = 0
        units_stats[unit] += 1

    print("СТАТИСТИКА ПО ТИПАМ:")
    print("-" * 80)
    for ptype, count in sorted(types_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"{ptype:20} - {count} товаров")

    print("\nСТАТИСТИКА ПО ЕДИНИЦАМ ИЗМЕРЕНИЯ:")
    print("-" * 80)
    for unit, count in sorted(units_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"{unit:20} - {count} товаров")

    # Показываем первые 30 товаров
    print("\n" + "="*80)
    print("ПЕРВЫЕ 30 ТОВАРОВ ИЗ ГРУППЫ 'НАПИТКИ ФАСОВКА'")
    print("="*80 + "\n")

    fasovka_list = []
    for product_id in fasovka_ids:
        product_info = nomenclature.get(product_id)
        if product_info:
            fasovka_list.append({
                'id': product_id,
                'name': product_info.get('name', ''),
                'type': product_info.get('type', ''),
                'unit': product_info.get('mainUnit', ''),
                'category': product_info.get('category', '')
            })

    # Сортируем по названию
    fasovka_list.sort(key=lambda x: x['name'])

    for i, item in enumerate(fasovka_list[:30], 1):
        print(f"{i:2}. {item['name']}")
        print(f"    Тип: {item['type']:10} | Единица: {item['unit']:5} | Поставщик: {item['category']}")
        print()

    # Проверяем, есть ли товары GOODS + шт
    goods_sht = [item for item in fasovka_list if item['type'] == 'GOODS' and item['unit'] == 'шт']
    print(f"\n[INFO] Товаров типа GOODS + шт: {len(goods_sht)} из {len(fasovka_list)}")

    olap.disconnect()
    print("\n" + "="*80)

if __name__ == '__main__':
    main()
