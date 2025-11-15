"""
Проверка есть ли DISH в остатках на складах
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

    # Ищем DISH в остатках
    dish_count = 0
    dish_liters = 0
    goods_count = 0

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

        if product_type == 'DISH':
            dish_count += 1
            if main_unit == 'л' and dish_count <= 10:
                name = product_info.get('name', 'N/A')
                print(f"{dish_count}. {name}")
                print(f"   Остаток: {amount} л")
                print(f"   Категория: {product_info.get('category', 'N/A')}")
                dish_liters += amount
        elif product_type == 'GOODS':
            goods_count += 1

    print(f"\n\nИтого:")
    print(f"DISH (блюда) в остатках: {dish_count}")
    print(f"Из них в литрах: {dish_liters}")
    print(f"GOODS (товары) в остатках: {goods_count}")
else:
    print("Ошибка получения данных!")

olap.disconnect()
