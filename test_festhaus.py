"""
Анализ остатков ФестХаус Хеллес по складам
"""
import sys
sys.path.insert(0, 'c:\\KULT\\beer-abc-analysis')

from core.olap_reports import OlapReports
import re

olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

balances = olap.get_store_balances()
nomenclature = olap.get_nomenclature()
olap.disconnect()

print("=" * 80)
print("АНАЛИЗ: ФестХаус Хеллес")
print("=" * 80)

# Ищем все записи с "ФестХаус" или "Festhaus"
festhaus_by_store = {}

for balance in balances:
    product_id = balance.get('product')
    store_id = balance.get('store')
    amount = balance.get('amount', 0)

    product_info = nomenclature.get(product_id)
    if not product_info:
        continue

    product_name = product_info.get('name', '')

    if 'фестхаус' in product_name.lower() or 'festhaus' in product_name.lower():
        if 'хеллес' in product_name.lower() or 'helles' in product_name.lower():
            # Обработка названия
            base_name = product_name
            base_name = re.sub(r'^Кег\s+', '', base_name, flags=re.IGNORECASE)
            base_name = re.sub(r',?\s*\d+\s*л.*', '', base_name)
            base_name = re.sub(r'\s+л\s*$', '', base_name)
            base_name = re.sub(r',?\s*кег.*', '', base_name, flags=re.IGNORECASE)
            base_name = re.sub(r',\s*$', '', base_name)
            base_name = base_name.strip()

            if store_id not in festhaus_by_store:
                festhaus_by_store[store_id] = []

            festhaus_by_store[store_id].append({
                'original': product_name,
                'processed': base_name,
                'amount': amount
            })

# Маппинг складов
store_names = {
    'a4c88d1c-be9a-4366-9aca-68ddaf8be40d': 'Большой пр. В.О (bar1)',
    '1239d270-1bbe-f64f-b7ea-5f00518ef508': 'Лиговский (bar2)',
    '91d7d070-875b-4d98-a81c-ae628eca45fd': 'Кременчугская (bar3)',
    '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d': 'Варшавская (bar4)',
}

print("\nОстатки по складам:\n")

total_all_stores = 0

for store_id, items in sorted(festhaus_by_store.items()):
    store_name = store_names.get(store_id, f'Неизвестный склад ({store_id[:8]}...)')
    print(f"Склад: {store_name}")
    print(f"Store ID: {store_id}\n")

    for item in items:
        print(f"  Оригинал: {item['original']}")
        print(f"  Обработано: {item['processed']}")
        print(f"  Остаток: {item['amount']} л\n")

    total = sum(i['amount'] for i in items)
    print(f"  ИТОГО на складе: {total} л\n")
    print("-" * 80 + "\n")
    total_all_stores += total

print(f"{'=' * 80}")
print(f"ИТОГО по всем складам: {total_all_stores} л")
print("=" * 80)

print("\n\nТекущий маппинг bar3 (Кременчугская):")
print(f"  store_id: 91d7d070-875b-4d98-a81c-ae628eca45fd")
if '91d7d070-875b-4d98-a81c-ae628eca45fd' in festhaus_by_store:
    total_bar3 = sum(i['amount'] for i in festhaus_by_store['91d7d070-875b-4d98-a81c-ae628eca45fd'])
    print(f"  ФестХаус Хеллес на этом складе: {total_bar3} л")
else:
    print("  [!] На этом складе НЕТ ФестХаус Хеллес!")

print(f"\nЕсли в iiko показывает 109.25 л, проверяем соответствие:")
for store_id, items in festhaus_by_store.items():
    total = sum(i['amount'] for i in items)
    if abs(total - 109.25) < 0.5:
        print(f"  [OK] НАЙДЕНО СОВПАДЕНИЕ!")
        print(f"       Склад: {store_names.get(store_id, store_id)}")
        print(f"       Остаток: {total} л")
        print(f"  Возможно нужно переназначить bar3 на этот склад!")
