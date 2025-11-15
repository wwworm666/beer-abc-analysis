"""
Тест фильтрации активных кранов для остатков кег
"""
import sys
sys.path.insert(0, 'c:\\KULT\\beer-abc-analysis')

from core.olap_reports import OlapReports
from core.taps_manager import TapsManager
import re

print("=" * 60)
print("ТЕСТ ФИЛЬТРАЦИИ ПО АКТИВНЫМ КРАНАМ")
print("=" * 60)

# Инициализируем taps_manager
taps_manager = TapsManager()

# Собираем список активных кег со всех баров
active_beers = set()

for bar_id in ['bar1', 'bar2', 'bar3', 'bar4']:
    result = taps_manager.get_bar_taps(bar_id)
    print(f"\n{bar_id}: {result.get('name', 'Unknown')}")

    if 'taps' in result:
        for tap in result['taps']:
            if tap.get('status') == 'active' and tap.get('current_beer'):
                beer_name = tap['current_beer']
                tap_number = tap.get('tap_number', '?')

                # Убираем "КЕГ" из названия если есть
                beer_name_clean = re.sub(r'^КЕГ\s+', '', beer_name, flags=re.IGNORECASE)

                print(f"  Кран {tap_number}: '{beer_name}' -> '{beer_name_clean.strip()}'")
                active_beers.add(beer_name_clean.strip())

print(f"\n{'=' * 60}")
print(f"Итого активных кранов: {len(active_beers)}")
print(f"{'=' * 60}\n")

if active_beers:
    print("Список активных кег (для фильтрации):")
    for i, beer in enumerate(sorted(active_beers), 1):
        print(f"  {i}. '{beer}'")
else:
    print("[!] НЕТ АКТИВНЫХ КРАНОВ!")

print(f"\n{'=' * 60}")
print("Теперь проверяем соответствие с остатками...")
print(f"{'=' * 60}\n")

# Получаем остатки из iiko
olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

nomenclature = olap.get_nomenclature()
balances = olap.get_store_balances()
olap.disconnect()

if not balances or not nomenclature:
    print("Ошибка получения данных")
    exit()

# Обрабатываем остатки кег
print("Обработка остатков кег (первые 20):\n")

kegs_processed = 0
kegs_matched = 0
kegs_not_matched = []

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

    # Убираем "Кег" и объёмы из названия для агрегации
    base_name = product_name
    base_name = re.sub(r'^Кег\s+', '', base_name, flags=re.IGNORECASE)
    base_name = re.sub(r'\s+\d+\s*л.*', '', base_name)  # Убираем "20 л", "30 л" и т.д.
    base_name = re.sub(r',?\s*кег.*', '', base_name, flags=re.IGNORECASE)
    base_name = base_name.strip()

    kegs_processed += 1

    if kegs_processed <= 20:
        is_active = base_name in active_beers
        status = "[+] ACTIVE" if is_active else "[-] not active"

        print(f"{kegs_processed}. {status}")
        print(f"   Original: '{product_name}'")
        print(f"   Processed: '{base_name}'")
        print(f"   Amount: {amount} л\n")

        if is_active:
            kegs_matched += 1
        else:
            kegs_not_matched.append(base_name)

print(f"\n{'=' * 60}")
print(f"Обработано кег: {kegs_processed}")
print(f"Совпадений с активными: {kegs_matched}")
print(f"{'=' * 60}\n")

if kegs_matched == 0 and active_beers:
    print("[!] ПРОБЛЕМА: Нет совпадений между названиями кег и активными кранами!")
    print("\nВозможные причины:")
    print("1. Разные форматы названий")
    print("2. Разные регистры букв")
    print("3. Дополнительные пробелы или символы")

    print("\nПопробуем найти похожие названия:")
    for beer in list(active_beers)[:5]:
        print(f"\n  Ищем похожее на: '{beer}'")
        for not_matched in kegs_not_matched[:30]:
            if beer.lower() in not_matched.lower() or not_matched.lower() in beer.lower():
                print(f"    Возможно: '{not_matched}'")
