"""
Проверка реального сопоставления названий кег
"""
import sys
sys.path.insert(0, 'c:\\KULT\\beer-abc-analysis')

from core.olap_reports import OlapReports
from core.taps_manager import TapsManager
import re

print("=" * 80)
print("ПРОВЕРКА СОПОСТАВЛЕНИЯ НАЗВАНИЙ КЕГ")
print("=" * 80)

# 1. Получаем активные краны
taps_manager = TapsManager(data_file='data/taps_data.json')
active_beers = set()

print("\n1. АКТИВНЫЕ КРАНЫ:")
print("-" * 80)

for bar_id in ['bar1', 'bar2', 'bar3', 'bar4']:
    result = taps_manager.get_bar_taps(bar_id)
    if 'taps' in result:
        for tap in result['taps']:
            if tap.get('status') == 'active' and tap.get('current_beer'):
                beer_name = tap['current_beer']
                # Убираем "КЕГ" из названия
                beer_name_clean = re.sub(r'^КЕГ\s+', '', beer_name, flags=re.IGNORECASE).strip()

                print(f"\n{bar_id} Кран {tap.get('tap_number')}:")
                print(f"  Оригинал: '{beer_name}'")
                print(f"  Обработка: '{beer_name_clean}'")

                active_beers.add(beer_name_clean)

print(f"\n{'=' * 80}")
print(f"ИТОГО активных: {len(active_beers)}")
print(f"{'=' * 80}")

# 2. Получаем остатки кег из iiko
print("\n2. ОСТАТКИ КЕГ ИЗ IIKO:")
print("-" * 80)

olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

nomenclature = olap.get_nomenclature()
balances = olap.get_store_balances()
olap.disconnect()

# Собираем все кеги из остатков
kegs_in_stock = []

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

    # Обрабатываем название так же, как в app.py
    base_name = product_name
    base_name = re.sub(r'^Кег\s+', '', base_name, flags=re.IGNORECASE)
    base_name = re.sub(r'\s+\d+\s*л.*', '', base_name)
    base_name = re.sub(r',?\s*кег.*', '', base_name, flags=re.IGNORECASE)
    base_name = base_name.strip()

    kegs_in_stock.append({
        'original': product_name,
        'processed': base_name,
        'amount': amount
    })

print(f"\nНайдено кег в остатках: {len(kegs_in_stock)}")

# 3. Пытаемся сопоставить каждый активный кран с остатками
print(f"\n{'=' * 80}")
print("3. СОПОСТАВЛЕНИЕ:")
print("=" * 80)

for active_beer in sorted(active_beers):
    print(f"\n[ПОИСК] Ищем: '{active_beer}'")

    # Точное совпадение
    exact_matches = [k for k in kegs_in_stock if k['processed'] == active_beer]

    if exact_matches:
        print(f"  [OK] НАЙДЕНО (точное совпадение): {len(exact_matches)} шт")
        for match in exact_matches[:3]:
            print(f"     - '{match['original']}' -> {match['amount']} л")
    else:
        print(f"  [X] НЕТ точного совпадения")

        # Пробуем нечеткое сравнение
        active_norm = active_beer.lower().strip()
        active_words = active_norm.split()

        fuzzy_matches = []

        for keg in kegs_in_stock:
            keg_norm = keg['processed'].lower().strip()
            keg_words = keg_norm.split()

            # Проверка 1: вхождение
            if active_norm in keg_norm or keg_norm in active_norm:
                fuzzy_matches.append(('вхождение', keg))
                continue

            # Проверка 2: первые 2 слова
            if len(active_words) >= 2 and len(keg_words) >= 2:
                if active_words[0] == keg_words[0] and active_words[1] == keg_words[1]:
                    fuzzy_matches.append(('2 слова', keg))
                    continue

            # Проверка 3: похожие слова
            if len(active_words) >= 2 and len(keg_words) >= 2:
                if active_words[0] == keg_words[0]:
                    word2_active = active_words[1]
                    word2_keg = keg_words[1]

                    if (word2_active.startswith(word2_keg) or
                        word2_keg.startswith(word2_active) or
                        (len(word2_active) >= 4 and len(word2_keg) >= 4 and
                         word2_active[:4] == word2_keg[:4])):
                        fuzzy_matches.append(('похожие', keg))

        if fuzzy_matches:
            print(f"  [~] Нечеткие совпадения: {len(fuzzy_matches)} шт")
            for match_type, match in fuzzy_matches[:3]:
                print(f"     [{match_type}] '{match['original']}' -> {match['amount']} л")
                print(f"                  обработано: '{match['processed']}'")
        else:
            print(f"  [!] СОВСЕМ НЕ НАШЛИ!")
            print(f"\n  Показываем первые 10 кег для сравнения:")
            for keg in kegs_in_stock[:10]:
                print(f"     '{keg['processed']}'")

print(f"\n{'=' * 80}")
print("ИТОГ:")
print("=" * 80)

matched = 0
not_matched = 0

for active_beer in active_beers:
    active_norm = active_beer.lower().strip()
    found = False

    for keg in kegs_in_stock:
        keg_norm = keg['processed'].lower().strip()
        if active_norm == keg_norm:
            found = True
            break

    if found:
        matched += 1
    else:
        not_matched += 1

print(f"Активных кранов: {len(active_beers)}")
print(f"Найдено в остатках (точно): {matched}")
print(f"НЕ найдено: {not_matched}")
