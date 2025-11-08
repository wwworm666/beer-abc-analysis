"""
Анализ обработки названия "Гулден Драк 708"
"""
import sys
sys.path.insert(0, 'c:\\KULT\\beer-abc-analysis')

from core.olap_reports import OlapReports
from core.taps_manager import TapsManager
import re

print("=" * 80)
print("АНАЛИЗ: Гулден Драк 708")
print("=" * 80)

# 1. Проверяем что в кранах
taps_manager = TapsManager(data_file='data/taps_data.json')
result = taps_manager.get_bar_taps('bar1')

print("\n1. ЧТО НА КРАНАХ (bar1):")
print("-" * 80)

active_beers_from_taps = []
if 'taps' in result:
    for tap in result['taps']:
        if tap.get('status') == 'active' and tap.get('current_beer'):
            beer_name = tap['current_beer']
            # Обработка как в app.py
            beer_name_clean = re.sub(r'^КЕГ\s+', '', beer_name, flags=re.IGNORECASE).strip()

            if 'гулден' in beer_name.lower() or 'gulden' in beer_name.lower():
                print(f"\nКран {tap.get('tap_number')}:")
                print(f"  Оригинал: '{beer_name}'")
                print(f"  После обработки: '{beer_name_clean}'")
                active_beers_from_taps.append(beer_name_clean)

if not active_beers_from_taps:
    print("\n[!] НЕТ Гулден Драк на кранах bar1")

# 2. Проверяем что в остатках iiko
print("\n\n2. ЧТО В ОСТАТКАХ IIKO:")
print("-" * 80)

olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

nomenclature = olap.get_nomenclature()
balances = olap.get_store_balances()
olap.disconnect()

gulden_kegs = []

for balance in balances:
    product_id = balance.get('product')
    amount = balance.get('amount', 0)

    product_info = nomenclature.get(product_id)
    if not product_info:
        continue

    if product_info.get('type') != 'GOODS':
        continue

    if product_info.get('mainUnit') != 'л':
        continue

    product_name = product_info.get('name', product_id)

    if 'гулден' in product_name.lower() or 'gulden' in product_name.lower():
        # Обработка как в app.py
        base_name = product_name
        base_name = re.sub(r'^Кег\s+', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'\s+\d+\s*л.*', '', base_name)
        base_name = re.sub(r'\s+л\s*$', '', base_name)
        base_name = re.sub(r',?\s*кег.*', '', base_name, flags=re.IGNORECASE)
        base_name = base_name.strip()

        gulden_kegs.append({
            'original': product_name,
            'processed': base_name,
            'amount': amount
        })

if gulden_kegs:
    print(f"\nНайдено кег: {len(gulden_kegs)}")
    for i, keg in enumerate(gulden_kegs, 1):
        print(f"\n{i}. Оригинал: '{keg['original']}'")
        print(f"   Обработано: '{keg['processed']}'")
        print(f"   Остаток: {keg['amount']} л")
else:
    print("\n[!] НЕТ Гулден Драк в остатках!")

# 3. Сопоставление
print(f"\n\n{'=' * 80}")
print("3. СОПОСТАВЛЕНИЕ:")
print("=" * 80)

if active_beers_from_taps and gulden_kegs:
    for tap_beer in active_beers_from_taps:
        print(f"\nИщем совпадение для: '{tap_beer}'")

        found = False
        for keg in gulden_kegs:
            if tap_beer == keg['processed']:
                print(f"  [OK] НАЙДЕНО точное совпадение!")
                print(f"       '{keg['original']}' -> {keg['amount']} л")
                found = True
            elif tap_beer.lower() == keg['processed'].lower():
                print(f"  [~] Совпадение без учета регистра")
                print(f"       tap: '{tap_beer}'")
                print(f"       keg: '{keg['processed']}'")
                found = True

        if not found:
            print(f"  [X] НЕТ совпадения!")
            print(f"\n  Доступные варианты из остатков:")
            for keg in gulden_kegs:
                print(f"    - '{keg['processed']}'")

elif not active_beers_from_taps:
    print("\n[!] Гулден Драк не стоит на активных кранах bar1")
elif not gulden_kegs:
    print("\n[!] Гулден Драк не найден в остатках iiko")

print(f"\n{'=' * 80}")
