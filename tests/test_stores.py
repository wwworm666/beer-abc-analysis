"""
Проверка складов в балансах
"""
import sys
sys.path.insert(0, 'c:\\KULT\\beer-abc-analysis')

from core.olap_reports import OlapReports

olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

balances = olap.get_store_balances()
nomenclature = olap.get_nomenclature()
olap.disconnect()

print("=" * 80)
print("АНАЛИЗ СКЛАДОВ")
print("=" * 80)

# Собираем уникальные store_id
stores = {}

for balance in balances:
    store_id = balance.get('store')
    amount = balance.get('amount', 0)

    if store_id not in stores:
        stores[store_id] = {'count': 0, 'total_items': 0}

    stores[store_id]['count'] += 1
    if amount > 0:
        stores[store_id]['total_items'] += 1

print(f"\nНайдено складов: {len(stores)}\n")

for store_id, data in sorted(stores.items()):
    print(f"Store ID: {store_id}")
    print(f"  Всего записей: {data['count']}")
    print(f"  С остатком > 0: {data['total_items']}\n")

# Смотрим Гулден Драк по складам
print("=" * 80)
print("ГУЛДЕН ДРАК 708 ПО СКЛАДАМ:")
print("=" * 80)

gulden_by_store = {}

for balance in balances:
    product_id = balance.get('product')
    store_id = balance.get('store')
    amount = balance.get('amount', 0)

    if amount <= 0:
        continue

    product_info = nomenclature.get(product_id)
    if not product_info:
        continue

    product_name = product_info.get('name', '')

    if 'гулден' in product_name.lower() or 'gulden' in product_name.lower():
        if '708' in product_name:
            if store_id not in gulden_by_store:
                gulden_by_store[store_id] = []

            gulden_by_store[store_id].append({
                'name': product_name,
                'amount': amount
            })

if gulden_by_store:
    for store_id, items in sorted(gulden_by_store.items()):
        print(f"\nСклад: {store_id}")
        for item in items:
            print(f"  {item['name']}: {item['amount']} л")

        total = sum(i['amount'] for i in items)
        print(f"  ИТОГО на складе: {total} л")
else:
    print("\nГулден Драк 708 не найден в остатках")

print(f"\n{'=' * 80}")
print(f"ИТОГО по всем складам: {sum(sum(i['amount'] for i in items) for items in gulden_by_store.values())} л")
print("=" * 80)
