"""
Проверка маппинга складов на популярных кегах
Берем топ-10 кег по остаткам и смотрим их распределение
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

# Текущий маппинг
store_id_map = {
    'a4c88d1c-be9a-4366-9aca-68ddaf8be40d': 'Большой пр. В.О (bar1)',
    '91d7d070-875b-4d98-a81c-ae628eca45fd': 'Лиговский (bar2)',
    '1239d270-1bbe-f64f-b7ea-5f00518ef508': 'Кременчугская (bar3)',
    '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d': 'Варшавская (bar4)',
}

print("=" * 80)
print("ПРОВЕРКА МАППИНГА СКЛАДОВ")
print("=" * 80)

# Собираем все кеги по барам
beers_by_store = {}

for balance in balances:
    store_id = balance.get('store')
    amount = balance.get('amount', 0)

    if amount <= 0:
        continue

    product_info = nomenclature.get(balance.get('product'))
    if not product_info:
        continue

    if product_info.get('type') != 'GOODS' or product_info.get('mainUnit') != 'л':
        continue

    product_name = product_info.get('name', '')

    # Обработка
    base_name = product_name
    base_name = re.sub(r'^Кег\s+', '', base_name, flags=re.IGNORECASE)
    base_name = re.sub(r',?\s*\d+\s*л.*', '', base_name)
    base_name = re.sub(r'\s+л\s*$', '', base_name)
    base_name = re.sub(r',?\s*кег.*', '', base_name, flags=re.IGNORECASE)
    base_name = re.sub(r',\s*$', '', base_name)
    base_name = base_name.strip()

    if store_id not in beers_by_store:
        beers_by_store[store_id] = {}

    if base_name not in beers_by_store[store_id]:
        beers_by_store[store_id][base_name] = 0
    beers_by_store[store_id][base_name] += amount

# Для каждого склада показываем топ-10 кег
for store_id in sorted(beers_by_store.keys()):
    store_name = store_id_map.get(store_id, f'Неизвестный ({store_id[:8]}...)')

    print(f"\n{store_name}")
    print(f"Store ID: {store_id}")
    print("-" * 80)

    beers = beers_by_store[store_id]
    top_beers = sorted(beers.items(), key=lambda x: x[1], reverse=True)[:10]

    print(f"Топ-10 кег по остаткам:\n")
    for i, (beer, amount) in enumerate(top_beers, 1):
        print(f"  {i:2}. {beer:50} {amount:6.1f} л")

    total = sum(beers.values())
    print(f"\nВсего кег: {len(beers)}, объем: {total:.1f} л")

print(f"\n{'=' * 80}")
print("ПЕРЕКРЕСТНАЯ ПРОВЕРКА:")
print("=" * 80)

# Берем несколько популярных кег и смотрим на каких складах они есть
test_beers = [
    'ФестХаус Хеллес',
    'Гулден Драк 708',
    'Клинское Светлое',
    'Вайсбург',
]

for test_beer in test_beers:
    print(f"\n'{test_beer}':")

    found_stores = []
    for store_id, beers in beers_by_store.items():
        for beer_name, amount in beers.items():
            if test_beer.lower() in beer_name.lower():
                store_name = store_id_map.get(store_id, store_id[:8])
                found_stores.append((store_name, amount))

    if found_stores:
        for store_name, amount in sorted(found_stores, key=lambda x: x[1], reverse=True):
            print(f"  {store_name:30} {amount:6.1f} л")
        total = sum(x[1] for x in found_stores)
        print(f"  {'ИТОГО:':30} {total:6.1f} л")
    else:
        print("  [!] Не найдено")

print(f"\n{'=' * 80}")
print("ИТОГОВАЯ СТАТИСТИКА:")
print("=" * 80)

for store_id in sorted(beers_by_store.keys()):
    store_name = store_id_map.get(store_id, store_id[:8])
    beers = beers_by_store[store_id]
    total = sum(beers.values())

    print(f"{store_name:30} | Кег: {len(beers):3} шт | Объем: {total:7.1f} л")

print("=" * 80)
