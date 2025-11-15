"""
Проверка остатков кег (GOODS в литрах) в balance/stores
"""
from core.olap_reports import OlapReports

olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

# Получаем номенклатуру
nomenclature = olap.get_nomenclature()

# Получаем остатки
balances = olap.get_store_balances()

if balances and nomenclature:
    print(f"Всего остатков: {len(balances)}")
    print(f"Всего товаров в номенклатуре: {len(nomenclature)}\n")

    # Ищем GOODS в литрах (это кеги)
    kegs_count = 0
    total_liters = 0

    print("Кеги пива (GOODS в литрах) с остатками:\n")

    for balance in balances:
        product_id = balance.get('product')
        amount = balance.get('amount', 0)

        if amount <= 0:
            continue

        product_info = nomenclature.get(product_id)
        if not product_info:
            continue

        product_type = product_info.get('type')
        main_unit = product_info.get('mainUnit')
        category = product_info.get('category', 'N/A')

        # Ищем GOODS в литрах
        if product_type == 'GOODS' and main_unit == 'л':
            kegs_count += 1
            total_liters += amount

            if kegs_count <= 30:  # Показываем первые 30
                name = product_info.get('name', 'N/A')
                print(f"{kegs_count}. {name}")
                print(f"   Остаток: {amount} л")
                print(f"   Категория: {category}")
                print(f"   Store: {balance.get('store', 'N/A')}\n")

    print(f"\n{'='*60}")
    print(f"Итого кег (GOODS в литрах): {kegs_count}")
    print(f"Общий объем: {round(total_liters, 1)} литров")
    print(f"{'='*60}")
else:
    print("Ошибка получения данных!")

olap.disconnect()
