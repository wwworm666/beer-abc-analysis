"""
Комплексный анализ маппинга складов для всех баров
Проверяет соответствие store_id каждому бару
"""
import sys
sys.path.insert(0, 'c:\\KULT\\beer-abc-analysis')

from core.olap_reports import OlapReports
from core.taps_manager import TapsManager
import re

print("=" * 80)
print("КОМПЛЕКСНЫЙ АНАЛИЗ МАППИНГА СКЛАДОВ")
print("=" * 80)

# Текущий маппинг из app.py
store_id_map = {
    'bar1': 'a4c88d1c-be9a-4366-9aca-68ddaf8be40d',  # Большой пр. В.О
    'bar2': '91d7d070-875b-4d98-a81c-ae628eca45fd',  # Лиговский
    'bar3': '1239d270-1bbe-f64f-b7ea-5f00518ef508',  # Кременчугская
    'bar4': '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d',  # Варшавская
}

bar_names = {
    'bar1': 'Большой пр. В.О',
    'bar2': 'Лиговский',
    'bar3': 'Кременчугская',
    'bar4': 'Варшавская',
}

# Получаем данные
olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

balances = olap.get_store_balances()
nomenclature = olap.get_nomenclature()
olap.disconnect()

taps_manager = TapsManager(data_file='data/taps_data.json')

print("\n1. СТАТИСТИКА ПО СКЛАДАМ:")
print("-" * 80)

# Собираем статистику по каждому складу
store_stats = {}

for balance in balances:
    store_id = balance.get('store')
    amount = balance.get('amount', 0)

    if store_id not in store_stats:
        store_stats[store_id] = {
            'total_items': 0,
            'total_volume': 0,
            'kegs_count': 0,
            'kegs_volume': 0
        }

    if amount > 0:
        store_stats[store_id]['total_items'] += 1

        product_info = nomenclature.get(balance.get('product'))
        if product_info:
            if product_info.get('type') == 'GOODS' and product_info.get('mainUnit') == 'л':
                store_stats[store_id]['kegs_count'] += 1
                store_stats[store_id]['kegs_volume'] += amount
            store_stats[store_id]['total_volume'] += amount

for bar_id, store_id in store_id_map.items():
    bar_name = bar_names[bar_id]
    stats = store_stats.get(store_id, {})

    print(f"\n{bar_name} ({bar_id}):")
    print(f"  Store ID: {store_id}")
    print(f"  Всего позиций с остатком > 0: {stats.get('total_items', 0)}")
    print(f"  Кег (GOODS в литрах): {stats.get('kegs_count', 0)} шт")
    print(f"  Объем кег: {stats.get('kegs_volume', 0):.1f} л")

print(f"\n{'=' * 80}")
print("2. ПРОВЕРКА АКТИВНЫХ КРАНОВ VS ОСТАТКИ:")
print("=" * 80)

# Для каждого бара проверяем соответствие
errors_found = []

for bar_id, bar_name in bar_names.items():
    print(f"\n{bar_name} ({bar_id}):")
    print("-" * 80)

    store_id = store_id_map[bar_id]

    # Получаем активные краны
    result = taps_manager.get_bar_taps(bar_id)
    active_taps = []

    if 'taps' in result:
        for tap in result['taps']:
            if tap.get('status') == 'active' and tap.get('current_beer'):
                beer_name = tap['current_beer']
                # Обработка как в app.py
                beer_name = re.sub(r'^КЕГ\s+', '', beer_name, flags=re.IGNORECASE)
                beer_name = re.sub(r'^Кег\s+', '', beer_name, flags=re.IGNORECASE)
                beer_name = re.sub(r',?\s*\d+\s*л.*', '', beer_name)
                beer_name = re.sub(r'\s+л\s*$', '', beer_name)
                beer_name = re.sub(r',?\s*кег.*', '', beer_name, flags=re.IGNORECASE)
                beer_name = re.sub(r',\s*$', '', beer_name)
                beer_name = beer_name.strip()

                active_taps.append({
                    'tap_number': tap.get('tap_number'),
                    'name': beer_name,
                    'original': tap['current_beer']
                })

    print(f"Активных кранов: {len(active_taps)}")

    if not active_taps:
        print("  [!] Нет активных кранов")
        continue

    # Получаем остатки этого склада
    store_kegs = {}

    for balance in balances:
        if balance.get('store') != store_id:
            continue

        amount = balance.get('amount', 0)
        if amount <= 0:
            continue

        product_info = nomenclature.get(balance.get('product'))
        if not product_info:
            continue

        if product_info.get('type') != 'GOODS' or product_info.get('mainUnit') != 'л':
            continue

        product_name = product_info.get('name', '')

        # Обработка как в app.py
        base_name = product_name
        base_name = re.sub(r'^Кег\s+', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r',?\s*\d+\s*л.*', '', base_name)
        base_name = re.sub(r'\s+л\s*$', '', base_name)
        base_name = re.sub(r',?\s*кег.*', '', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r',\s*$', '', base_name)
        base_name = base_name.strip()

        if base_name not in store_kegs:
            store_kegs[base_name] = 0
        store_kegs[base_name] += amount

    # Проверяем каждый активный кран
    matched = 0
    not_matched = []

    for tap in active_taps:
        tap_name = tap['name']

        if tap_name in store_kegs:
            print(f"  [OK] Кран {tap['tap_number']}: '{tap_name}' -> {store_kegs[tap_name]:.1f} л")
            matched += 1
        else:
            print(f"  [X] Кран {tap['tap_number']}: '{tap_name}' -> НЕ НАЙДЕНО в остатках!")
            not_matched.append(tap_name)
            errors_found.append({
                'bar': bar_name,
                'tap': tap['tap_number'],
                'beer': tap_name,
                'store_id': store_id
            })

    print(f"\nИтого: {matched}/{len(active_taps)} найдено")

    if not_matched:
        print(f"\nНе найдены на складе:")
        for beer in not_matched:
            print(f"  - '{beer}'")
            # Ищем похожие
            similar = [k for k in store_kegs.keys() if beer.lower() in k.lower() or k.lower() in beer.lower()]
            if similar:
                print(f"    Похожие на складе:")
                for s in similar[:3]:
                    print(f"      '{s}' -> {store_kegs[s]:.1f} л")

print(f"\n{'=' * 80}")
print("3. ИТОГОВЫЙ АНАЛИЗ:")
print("=" * 80)

if errors_found:
    print(f"\n[!] НАЙДЕНЫ ОШИБКИ: {len(errors_found)}")
    print("\nПроблемные позиции:")
    for error in errors_found:
        print(f"  - {error['bar']}, кран {error['tap']}: '{error['beer']}'")

    print("\nВОЗМОЖНЫЕ ПРИЧИНЫ:")
    print("  1. Неправильный маппинг store_id")
    print("  2. Кега закончилась (amount = 0)")
    print("  3. Различия в названиях между кранами и iiko")
    print("  4. Устаревшие данные в taps_data.json")
else:
    print("\n[OK] ВСЕ АКТИВНЫЕ КРАНЫ НАЙДЕНЫ В ОСТАТКАХ!")
    print("Маппинг складов корректный.")

print(f"\n{'=' * 80}")
