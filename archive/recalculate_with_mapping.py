"""
Пересчёт с использованием маппинга кег -> блюда
Теперь группируем по КЕГАМ, а не по блюдам
"""

from datetime import datetime
from olap_reports import OlapReports
import pandas as pd
import re
from keg_mapping import KEG_TO_DISH_MAPPING

print("="*80)
print("PERASCHET S ISPOLZOVANIEM MAPPINGA KEG -> BLYUDA")
print("="*80)

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

# Создаём обратный маппинг: блюдо -> кега
DISH_TO_KEG = {}
for keg, dishes in KEG_TO_DISH_MAPPING.items():
    for dish in dishes:
        # Нормализуем для сравнения
        dish_normalized = dish.strip().lower()
        DISH_TO_KEG[dish_normalized] = keg

# Добавляем колонку с названием кеги
def map_to_keg(beer_name):
    beer_normalized = beer_name.strip().lower()
    return DISH_TO_KEG.get(beer_normalized, f"[НЕ НАЙДЕНА КЕГА] {beer_name}")

df['KegName'] = df['BeerName'].apply(map_to_keg)

# Группируем по КЕГАМ
kegs_summary = df.groupby('KegName').agg({
    'TotalLiters': 'sum',
    'DishAmountInt': 'sum'
}).reset_index()

kegs_summary = kegs_summary.sort_values('TotalLiters', ascending=False)

print("="*80)
print("REZULTAT GRUPPIROVKI PO KEGAM:")
print("="*80)

print(f"\n{'KEGA (TOVAR)':<60s} {'Litry':<15s} {'Porcii':<10s}")
print("="*100)

for _, row in kegs_summary.iterrows():
    keg = row['KegName']
    liters = row['TotalLiters']
    portions = int(row['DishAmountInt'])

    # Выделяем нужные кеги
    if keg == "КЕГ Блек Шип":
        marker = " <--- BLEK SHIP"
    elif keg == "КЕГ ФестХаус Хеллес":
        marker = " <--- FESTHAUS"
    else:
        marker = ""

    print(f"{keg:<60s} {liters:<15.2f} {portions:<10d}{marker}")

# Проверяем Блек Шип отдельно
print("\n" + "="*80)
print("DETALNAYA PROVERKA BLEK SHIP:")
print("="*80)

black_sheep_data = df[df['KegName'] == 'КЕГ Блек Шип']

if not black_sheep_data.empty:
    print(f"\nVsego zapisey: {len(black_sheep_data)}")

    # Группируем по размеру порции
    by_portion = black_sheep_data.groupby(['BeerName', 'PortionVolume']).agg({
        'DishAmountInt': 'sum',
        'TotalLiters': 'sum'
    }).reset_index()

    print(f"\n{'Nazvanie blyuda':<40s} {'Obem':<10s} {'Porcii':<10s} {'Litry':<10s}")
    print("-" * 80)
    for _, row in by_portion.iterrows():
        print(f"{row['BeerName']:<40s} {row['PortionVolume']:<10.2f} {int(row['DishAmountInt']):<10d} {row['TotalLiters']:<10.2f}")

    total_bs = black_sheep_data['TotalLiters'].sum()
    total_portions_bs = black_sheep_data['DishAmountInt'].sum()

    print("-" * 80)
    print(f"{'ITOGO':<40s} {'':<10s} {int(total_portions_bs):<10d} {total_bs:<10.2f}")

    print(f"\n[NASH REZULTAT] {total_bs:.2f} L")
    print(f"[OFFICE]        75.00 L")
    print(f"[RAZNIZA]       {abs(75 - total_bs):.2f} L ({abs(75 - total_bs) / 75 * 100:.1f}%)")

# Проверяем ФестХаус
print("\n" + "="*80)
print("DETALNAYA PROVERKA FESTHAUS HELLES:")
print("="*80)

festhaus_data = df[df['KegName'] == 'КЕГ ФестХаус Хеллес']

if not festhaus_data.empty:
    total_fh = festhaus_data['TotalLiters'].sum()
    total_portions_fh = festhaus_data['DishAmountInt'].sum()

    print(f"\n[NASH REZULTAT] {total_fh:.2f} L ({int(total_portions_fh)} porciy)")
    print(f"[OFFICE]        141.00 L")
    print(f"[RAZNIZA]       {abs(141 - total_fh):.2f} L ({abs(141 - total_fh) / 141 * 100:.1f}%)")

# Сохраняем
kegs_summary.to_csv('kegs_summary_with_mapping.csv', index=False, encoding='utf-8-sig')
print("\n[SAVED] kegs_summary_with_mapping.csv")

print("\n" + "="*80)
print("VYVOD:")
print("="*80)
print("""
Esli razniza vse eshche est, vozmozhny prichiny:

1. V Office schitaetsya RASKHOD kegi (vklyuchaya poteri)
2. V Office drugiye daty/filtry
3. Nekotorye blyuda ne svyazany s kegoy v tekhkarte
4. Est drugie varianty napisaniya kotorye my propustili

Chtoby tochno ponyat - nado posmotr v Office:
- Kakoy TOCHNO otchet ispolzuetsya?
- Kakie TOCHNO filtry primenyayutsya?
- Mozhet byt v Office agregaciya po-drugomu?
""")

print("="*80)
