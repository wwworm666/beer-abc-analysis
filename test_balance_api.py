"""
Тестовый скрипт для проверки API остатков на складах
"""
from core.olap_reports import OlapReports

print("Testiruem API ostatkov na skladakh\n")

olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

# Получаем остатки на текущий момент
balances = olap.get_store_balances()

if balances:
    print(f"\nПолучено {len(balances)} записей об остатках")

    # Группируем по типу товара
    products_count = {}
    total_records = 0

    for balance in balances[:20]:  # Показываем первые 20
        product_id = balance.get('product')
        amount = balance.get('amount', 0)
        store_id = balance.get('store')

        print(f"\nProduct ID: {product_id}")
        print(f"  Store ID: {store_id}")
        print(f"  Amount: {amount}")
        print(f"  Sum: {balance.get('sum', 0)}")

        total_records += 1

    print(f"\n\nВсего записей: {len(balances)}")
    print(f"Показано первых: {total_records}")
else:
    print("Ошибка получения остатков!")

olap.disconnect()
