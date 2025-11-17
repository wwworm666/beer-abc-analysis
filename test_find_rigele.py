"""
Поиск кег со словом Ригеле/Rigele
"""
import sys
sys.path.insert(0, 'c:\\KULT\\beer-abc-analysis')

from core.olap_reports import OlapReports
import re

olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

nomenclature = olap.get_nomenclature()
balances = olap.get_store_balances()
olap.disconnect()

print("=" * 80)
print("ПОИСК КЕГА 'РИГЕЛЕ'")
print("=" * 80)

found_kegs = []

for balance in balances:
    product_id = balance.get('product')
    amount = balance.get('amount', 0)

    if amount <= 0:
        continue

    product_info = nomenclature.get(product_id)
    if not product_info:
        continue

    if product_info.get('type') != 'GOODS':
        continue

    if product_info.get('mainUnit') != 'л':
        continue

    product_name = product_info.get('name', product_id)

    # Ищем "ригеле" в названии
    if 'ригеле' in product_name.lower() or 'rigele' in product_name.lower():
        # Обрабатываем название
        base_name = product_name
        base_name = re.sub(r'^Кег\s+', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'\s+\d+\s*л.*', '', base_name)
        base_name = re.sub(r',?\s*кег.*', '', base_name, flags=re.IGNORECASE)
        base_name = base_name.strip()

        found_kegs.append({
            'original': product_name,
            'processed': base_name,
            'amount': amount
        })

if found_kegs:
    print(f"\nНайдено кег с 'Ригеле': {len(found_kegs)}")
    print("-" * 80)

    for i, keg in enumerate(found_kegs, 1):
        print(f"\n{i}. Оригинал: '{keg['original']}'")
        print(f"   Обработано: '{keg['processed']}'")
        print(f"   Остаток: {keg['amount']} л")
else:
    print("\n[!] КЕГА 'РИГЕЛЕ' НЕ НАЙДЕНА В ОСТАТКАХ!")
    print("\nВозможно она закончилась или имеет другое название.")
    print("\nПоказываем ВСЕ кеги (первые 30):")
    print("-" * 80)

    count = 0
    for balance in balances:
        if count >= 30:
            break

        product_id = balance.get('product')
        amount = balance.get('amount', 0)

        if amount <= 0:
            continue

        product_info = nomenclature.get(product_id)
        if not product_info:
            continue

        if product_info.get('type') != 'GOODS':
            continue

        if product_info.get('mainUnit') != 'л':
            continue

        product_name = product_info.get('name', product_id)
        count += 1

        print(f"{count}. {product_name} ({amount} л)")

print(f"\n{'=' * 80}")
