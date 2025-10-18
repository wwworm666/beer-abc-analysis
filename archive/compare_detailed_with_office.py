"""
Детальное сравнение с данными из Office
Лиговский, 01.09.2025 - 30.09.2025
"""

from datetime import datetime
from olap_reports import OlapReports
import pandas as pd
import re

print("="*80)
print("DETALNOE SRAVNENIE S OFFICE")
print("="*80)

# Данные из Office (ТОЧНЫЕ!)
OFFICE_DATA = {
    "КЕГ Brewlok IPA 20 л": 20.950,
    "КЕГ Brewlok Stout": 8.700,
    "КЕГ Brewlok Пилс 20 л": 8.250,
    "КЕГ Rebel Apple Дикий Крест": 18.000,
    "КЕГ Барбе Руби 30 л": 17.050,
    "КЕГ Бланш де Намур, светлое": 22.500,
    "КЕГ Блек Шип": 75.000,
    "КЕГ Гулден Драк 708, 20 л": 6.000,
    "КЕГ Карлова Корчма Премиум 30 л": 27.000,
    "КЕГ Леруа Капиттель Блонд 30 л": 16.250,
    "КЕГ Монкс Кафе 20 л": 15.050,
    "КЕГ Нишко 30 л": 20.100,
    "КЕГ ФестХаус Вайцен": 61.350,
    "КЕГ ФестХаус Октобер": 14.500,
    "КЕГ ФестХаус Хеллес": 141.850,
}

# Получаем наши данные
olap = OlapReports()
if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

date_from = "2025-09-01"
date_to = "2025-09-30"
bar_name = "Лиговский"

print(f"\nPeriod: {date_from} - {date_to}")
print(f"Bar: {bar_name}\n")

report_data = olap.get_draft_sales_report(date_from, date_to, bar_name)
olap.disconnect()

if not report_data or not report_data.get('data'):
    print("[ERROR] Net dannykh")
    exit()

df = pd.DataFrame(report_data['data'])
df['DishAmountInt'] = pd.to_numeric(df['DishAmountInt'], errors='coerce')

# Извлекаем объём и название
def extract_volume(dish_name):
    pattern = r'\((\d+[,\.]\d+)\)'
    match = re.search(pattern, dish_name)
    if match:
        return float(match.group(1).replace(',', '.'))
    return 0.0

def extract_beer_name(dish_name):
    return re.sub(r'\s*\(.*\)', '', dish_name).strip()

df['PortionVolume'] = df['DishName'].apply(extract_volume)
df['BeerName'] = df['DishName'].apply(extract_beer_name)
df['TotalLiters'] = df['DishAmountInt'] * df['PortionVolume']

# Показываем ВСЕ уникальные названия блюд
print("="*80)
print("VSE UNIKALNYE NAZVANIYA BLYUD V NASHIKH DANNYKH:")
print("="*80)

unique_beers = df.groupby('BeerName').agg({
    'TotalLiters': 'sum',
    'DishAmountInt': 'sum'
}).reset_index().sort_values('TotalLiters', ascending=False)

print(f"\n{'#':<4} {'Nazvanie blyuda':<50s} {'Litry':<12s} {'Porcii':<10s}")
print("-" * 90)

for i, row in unique_beers.iterrows():
    print(f"{i+1:<4} {row['BeerName']:<50s} {row['TotalLiters']:<12.2f} {int(row['DishAmountInt']):<10d}")

print(f"\nVSEGO: {len(unique_beers)} poziciy")

# Пытаемся сопоставить с кегами из Office
print("\n" + "="*80)
print("POISK SOOTVETSTVIY:")
print("="*80)

def normalize_for_comparison(name):
    """Нормализация для сравнения"""
    normalized = name.upper()
    normalized = re.sub(r'КЕГ\s*', '', normalized)
    normalized = re.sub(r'\d+\s*[ЛL]', '', normalized)
    normalized = re.sub(r'[,\.\-]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

# Создаём маппинг
matches = {}
unmatched_kegs = []
unmatched_dishes = []

for keg_name, office_liters in OFFICE_DATA.items():
    keg_norm = normalize_for_comparison(keg_name)
    found = False

    for _, beer_row in unique_beers.iterrows():
        beer_name = beer_row['BeerName']
        beer_norm = normalize_for_comparison(beer_name)

        # Более мягкое сравнение
        keg_words = set(keg_norm.split())
        beer_words = set(beer_norm.split())

        # Проверяем совпадение основных слов
        common_words = keg_words & beer_words

        # Если есть хотя бы 50% общих слов
        if common_words and len(common_words) >= max(1, min(len(keg_words), len(beer_words)) * 0.5):
            matches[keg_name] = {
                'dish_name': beer_name,
                'office_liters': office_liters,
                'our_liters': beer_row['TotalLiters'],
                'difference': beer_row['TotalLiters'] - office_liters,
                'difference_pct': ((beer_row['TotalLiters'] - office_liters) / office_liters * 100) if office_liters > 0 else 0
            }
            found = True
            break

    if not found:
        unmatched_kegs.append((keg_name, office_liters))

# Находим блюда без кеги
matched_dishes = set([m['dish_name'] for m in matches.values()])
for _, beer_row in unique_beers.iterrows():
    if beer_row['BeerName'] not in matched_dishes:
        unmatched_dishes.append((beer_row['BeerName'], beer_row['TotalLiters']))

# Показываем результат
print(f"\n{'KEGA (OFFICE)':<50s} {'BLYUDO (NASH)':<40s} {'Office':<12s} {'Nash':<12s} {'Razniza':<12s}")
print("="*130)

total_office = 0
total_ours = 0

for keg_name in sorted(OFFICE_DATA.keys()):
    if keg_name in matches:
        m = matches[keg_name]
        total_office += m['office_liters']
        total_ours += m['our_liters']

        # Выделяем большие расхождения
        marker = ""
        if abs(m['difference']) > 2:
            marker = " <-- BOLSHAYA RAZNIZA!"
        elif abs(m['difference']) > 0.5:
            marker = " <-- RAZNIZA"

        print(f"{keg_name:<50s} {m['dish_name']:<40s} {m['office_liters']:<12.2f} {m['our_liters']:<12.2f} {m['difference']:<12.2f}{marker}")
    else:
        total_office += OFFICE_DATA[keg_name]
        print(f"{keg_name:<50s} {'[NE NAYDEN]':<40s} {OFFICE_DATA[keg_name]:<12.2f} {'0.00':<12s} {-OFFICE_DATA[keg_name]:<12.2f} <-- NE NAYDEN!")

print("="*130)
print(f"{'ITOGO':<50s} {'':<40s} {total_office:<12.2f} {total_ours:<12.2f} {total_ours - total_office:<12.2f}")

if unmatched_dishes:
    print("\n" + "="*80)
    print("BLYUDA BEZ SOOTVETSTVIYA S KEGAMI:")
    print("="*80)
    for dish, liters in unmatched_dishes:
        print(f"  {dish:<50s} {liters:.2f}L")

print("\n" + "="*80)
print("ANALIZ:")
print("="*80)

print(f"\nV Office: {len(OFFICE_DATA)} keg")
print(f"V nashikh dannykh: {len(unique_beers)} blyud")
print(f"Sovpadayut: {len(matches)}")
print(f"Ne naydeno keg: {len(unmatched_kegs)}")
print(f"Ne naydeno blyud: {len(unmatched_dishes)}")

# Сохраняем детальное сравнение
comparison_data = []
for keg_name, m in matches.items():
    comparison_data.append({
        'KegName': keg_name,
        'DishName': m['dish_name'],
        'Office_Liters': m['office_liters'],
        'Our_Liters': m['our_liters'],
        'Difference': m['difference'],
        'Difference_Pct': m['difference_pct']
    })

comparison_df = pd.DataFrame(comparison_data)
comparison_df.to_csv('detailed_comparison_with_office.csv', index=False, encoding='utf-8-sig')

print("\n[SAVED] detailed_comparison_with_office.csv")
print("="*80)
