"""
Поиск конкретных кег которые должны быть в остатках
"""
import sys
sys.path.insert(0, 'c:\\KULT\\beer-abc-analysis')

from core.olap_reports import OlapReports
import re

olap = OlapReports()
olap.connect()
nomenclature = olap.get_nomenclature()
balances = olap.get_store_balances()
olap.disconnect()

search_terms = [
    ('Клинское', 'klinskoe'),
    ('Вайсбург', 'weisburg'),
    ('Brewlok', 'brewlok'),
    ('ФестХаус', 'festhaus'),
]

print("=" * 80)
print("ПОИСК КОНКРЕТНЫХ КЕГ В ОСТАТКАХ")
print("=" * 80)

for rus, eng in search_terms:
    print(f"\n\nПоиск: '{rus}' / '{eng}'")
    print("-" * 80)

    found = []

    for balance in balances:
        product_info = nomenclature.get(balance.get('product'))
        if not product_info:
            continue

        if product_info.get('type') != 'GOODS' or product_info.get('mainUnit') != 'л':
            continue

        name = product_info.get('name', '')
        name_lower = name.lower()

        if rus.lower() in name_lower or eng.lower() in name_lower:
            amount = balance.get('amount', 0)

            # Обработка
            processed = name
            processed = re.sub(r'^Кег\s+', '', processed, flags=re.IGNORECASE)
            processed = re.sub(r',?\s*\d+\s*л.*', '', processed)
            processed = re.sub(r'\s+л\s*$', '', processed)
            processed = re.sub(r',?\s*кег.*', '', processed, flags=re.IGNORECASE)
            processed = re.sub(r',\s*$', '', processed)
            processed = processed.strip()

            found.append({
                'original': name,
                'processed': processed,
                'amount': amount
            })

    if found:
        # Группируем по обработанному названию
        grouped = {}
        for item in found:
            proc = item['processed']
            if proc not in grouped:
                grouped[proc] = {'items': [], 'total': 0}
            grouped[proc]['items'].append(item)
            grouped[proc]['total'] += item['amount']

        print(f"Найдено уникальных наименований: {len(grouped)}")
        print()

        for proc_name in sorted(grouped.keys()):
            data = grouped[proc_name]
            print(f"  '{proc_name}' -> ИТОГО: {data['total']:.1f} л")

            if len(data['items']) > 1:
                print(f"    Из {len(data['items'])} записей:")
                for item in data['items']:
                    if item['amount'] > 0:
                        print(f"      - {item['original']}: {item['amount']:.1f} л")
    else:
        print("  [!] НЕ НАЙДЕНО")

print(f"\n{'=' * 80}")
