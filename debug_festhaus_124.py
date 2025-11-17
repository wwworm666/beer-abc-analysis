"""
Отладка: откуда берется 124.5 л для ФестХаус Хеллес
"""
import sys
sys.path.insert(0, 'c:\\KULT\\beer-abc-analysis')

from core.olap_reports import OlapReports
import re

# Какой бар проверяем?
BAR = 'Кременчугская'  # Измени если нужен другой

bar_to_store = {
    'Большой пр. В.О': 'a4c88d1c-be9a-4366-9aca-68ddaf8be40d',
    'Лиговский': '91d7d070-875b-4d98-a81c-ae628eca45fd',
    'Кременчугская': '1239d270-1bbe-f64f-b7ea-5f00518ef508',
    'Варшавская': '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d',
}

target_store_id = bar_to_store[BAR]

print("=" * 80)
print(f"ОТЛАДКА: ФестХаус Хеллес на баре '{BAR}'")
print(f"Store ID: {target_store_id}")
print("=" * 80)

olap = OlapReports()
olap.connect()
nomenclature = olap.get_nomenclature()
balances = olap.get_store_balances()
olap.disconnect()

print("\n1. ВСЕ ЗАПИСИ С 'ФЕСТХАУС ХЕЛЛЕС' НА ЭТОМ СКЛАДЕ:")
print("-" * 80)

festhaus_records = []
total = 0

for balance in balances:
    store_id = balance.get('store')

    # Фильтруем по нужному складу
    if store_id != target_store_id:
        continue

    product_id = balance.get('product')
    amount = balance.get('amount', 0)

    product_info = nomenclature.get(product_id)
    if not product_info:
        continue

    product_name = product_info.get('name', '')

    if 'фестхаус' in product_name.lower() and 'хеллес' in product_name.lower():
        product_type = product_info.get('type')
        unit = product_info.get('mainUnit')

        print(f"\nProduct ID: {product_id}")
        print(f"  Название: {product_name}")
        print(f"  Тип: {product_type}")
        print(f"  Ед.изм: {unit}")
        print(f"  Остаток: {amount}")

        festhaus_records.append({
            'name': product_name,
            'type': product_type,
            'unit': unit,
            'amount': amount,
            'id': product_id
        })

        if product_type == 'GOODS' and unit == 'л':
            total += amount

print(f"\n{'=' * 80}")
print(f"ИТОГО записей: {len(festhaus_records)}")
print(f"Сумма GOODS в литрах: {total} л")
print("=" * 80)

print("\n2. ОБРАБОТКА НАЗВАНИЙ (КАК В APP.PY):")
print("-" * 80)

beer_stocks = {}

for record in festhaus_records:
    # Пропускаем не-кеги
    if record['type'] != 'GOODS' or record['unit'] != 'л':
        print(f"\n[SKIP] Не кега: {record['name']}")
        continue

    if record['amount'] <= 0:
        print(f"\n[SKIP] Нулевой остаток: {record['name']}")
        continue

    product_name = record['name']

    # Обработка как в app.py
    base_name = product_name
    base_name = re.sub(r'^Кег\s+', '', base_name, flags=re.IGNORECASE)
    base_name = re.sub(r',?\s*\d+\s*л.*', '', base_name)
    base_name = re.sub(r'\s+л\s*$', '', base_name)
    base_name = re.sub(r',?\s*кег.*', '', base_name, flags=re.IGNORECASE)
    base_name = re.sub(r',\s*$', '', base_name)
    base_name = base_name.strip()

    print(f"\n[PROCESS]")
    print(f"  Оригинал: '{product_name}'")
    print(f"  Обработано: '{base_name}'")
    print(f"  Остаток: {record['amount']} л")

    if base_name not in beer_stocks:
        beer_stocks[base_name] = 0
    beer_stocks[base_name] += record['amount']

print(f"\n{'=' * 80}")
print("3. ИТОГОВАЯ АГРЕГАЦИЯ:")
print("=" * 80)

for beer_name, amount in beer_stocks.items():
    print(f"\n'{beer_name}' -> {amount} л")

print(f"\n{'=' * 80}")
print("ИТОГ:")
print(f"На складе '{BAR}' ФестХаус Хеллес: {beer_stocks.get('ФестХаус Хеллес', 0)} л")
print("=" * 80)

# Проверяем все склады для сравнения
print(f"\n\n{'=' * 80}")
print("4. ПРОВЕРКА ВСЕХ СКЛАДОВ (ДЛЯ СРАВНЕНИЯ):")
print("=" * 80)

all_stores = {}

for balance in balances:
    store_id = balance.get('store')
    product_id = balance.get('product')
    amount = balance.get('amount', 0)

    if amount <= 0:
        continue

    product_info = nomenclature.get(product_id)
    if not product_info:
        continue

    if product_info.get('type') != 'GOODS' or product_info.get('mainUnit') != 'л':
        continue

    product_name = product_info.get('name', '')

    if 'фестхаус' in product_name.lower() and 'хеллес' in product_name.lower():
        # Обработка
        base_name = product_name
        base_name = re.sub(r'^Кег\s+', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r',?\s*\d+\s*л.*', '', base_name)
        base_name = re.sub(r'\s+л\s*$', '', base_name)
        base_name = re.sub(r',?\s*кег.*', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r',\s*$', '', base_name)
        base_name = base_name.strip()

        if store_id not in all_stores:
            all_stores[store_id] = 0
        all_stores[store_id] += amount

store_names = {
    'a4c88d1c-be9a-4366-9aca-68ddaf8be40d': 'Большой пр. В.О (bar1)',
    '91d7d070-875b-4d98-a81c-ae628eca45fd': 'Лиговский (bar2)',
    '1239d270-1bbe-f64f-b7ea-5f00518ef508': 'Кременчугская (bar3)',
    '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d': 'Варшавская (bar4)',
}

for store_id, amount in sorted(all_stores.items(), key=lambda x: x[1], reverse=True):
    store_name = store_names.get(store_id, store_id[:8])
    print(f"{store_name:30} {amount:7.1f} л")

print(f"\n{'ИТОГО:':30} {sum(all_stores.values()):7.1f} л")
print("=" * 80)
