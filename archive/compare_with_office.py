"""
Сравнение данных с отчётом iiko Office
Период: 01.09.2025 - 30.09.2025
Бар: Лиговский
"""

from datetime import datetime
from olap_reports import OlapReports
import pandas as pd
import re

print("="*80)
print("SRAVNENIE S OTCHETOM IIKO OFFICE")
print("="*80)

olap = OlapReports()
if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

# Точный период из запроса
date_from = "2025-09-01"
date_to = "2025-09-30"
bar_name = "Лиговский"

print(f"\nPeriod: {date_from} - {date_to}")
print(f"Bar: {bar_name}\n")

# Получаем данные
report_data = olap.get_draft_sales_by_waiter_report(date_from, date_to, bar_name)
olap.disconnect()

if not report_data or not report_data.get('data'):
    print("[ERROR] Net dannykh")
    exit()

df = pd.DataFrame(report_data['data'])
df['DishAmountInt'] = pd.to_numeric(df['DishAmountInt'], errors='coerce')
df['ProductCostBase.ProductCost'] = pd.to_numeric(df['ProductCostBase.ProductCost'], errors='coerce')

print(f"[OK] Polucheno {len(df)} zapisey\n")

# Извлекаем объём
def extract_volume(dish_name):
    pattern = r'\((\d+[,\.]\d+)\)'
    match = re.search(pattern, dish_name)
    if match:
        return float(match.group(1).replace(',', '.'))
    return 0.0

df['PortionVolume'] = df['DishName'].apply(extract_volume)
df['VolumeByPortions'] = df['DishAmountInt'] * df['PortionVolume']

# Извлекаем название пива (убираем объём)
df['BeerName'] = df['DishName'].str.replace(r'\s*\(.*\)', '', regex=True).str.strip()

# Показываем ВСЕ записи для интересующих позиций
print("="*80)
print("DETALI PO BLEK SHIP:")
print("="*80)

black_sheep = df[df['BeerName'].str.contains('Блек Шип', case=False, na=False)]

if not black_sheep.empty:
    print(f"\nVsego zapisey: {len(black_sheep)}")
    print(f"\n{'Data':<12} {'Porcii':<8} {'Obem':<8} {'Litry':<10} {'Oficial':<25} {'Blyudo'}")
    print("-" * 100)

    for _, row in black_sheep.iterrows():
        print(f"{row['OpenDate.Typed']:<12} {int(row['DishAmountInt']):<8} {row['PortionVolume']:<8.2f} {row['VolumeByPortions']:<10.2f} {row['WaiterName']:<25} {row['DishName']}")

    total_bs = black_sheep['VolumeByPortions'].sum()
    total_portions_bs = black_sheep['DishAmountInt'].sum()

    print("\n" + "-" * 100)
    print(f"ITOGO BLEK SHIP: {total_bs:.2f} L (porcii: {int(total_portions_bs)})")
    print(f"V OFFICE: 75 L")
    print(f"RAZNIZA: {75 - total_bs:.2f} L ({((75 - total_bs) / 75 * 100):.1f}%)")
else:
    print("[NOT FOUND] Net dannykh po Blek Ship")

print("\n" + "="*80)
print("DETALI PO FESTHAUS HELLES:")
print("="*80)

festhaus = df[df['BeerName'].str.contains('ФестХаус Хеллес', case=False, na=False)]

if not festhaus.empty:
    print(f"\nVsego zapisey: {len(festhaus)}")

    # Группируем по размеру порции
    festhaus_summary = festhaus.groupby('PortionVolume').agg({
        'DishAmountInt': 'sum',
        'VolumeByPortions': 'sum'
    }).reset_index()

    print(f"\n{'Obem porcii':<15} {'Porcii':<10} {'Litry':<10}")
    print("-" * 40)
    for _, row in festhaus_summary.iterrows():
        print(f"{row['PortionVolume']:<15.2f} {int(row['DishAmountInt']):<10} {row['VolumeByPortions']:<10.2f}")

    total_fh = festhaus['VolumeByPortions'].sum()
    total_portions_fh = festhaus['DishAmountInt'].sum()

    print("-" * 40)
    print(f"ITOGO FESTHAUS: {total_fh:.2f} L (porcii: {int(total_portions_fh)})")
    print(f"V OFFICE: 141 L")
    print(f"RAZNIZA: {141 - total_fh:.2f} L ({((141 - total_fh) / 141 * 100 if total_fh > 0 else 0):.1f}%)")
else:
    print("[NOT FOUND] Net dannykh po FestHaus")

# Показываем ВСЕ пиво для проверки
print("\n" + "="*80)
print("VSE PIVO ZA PERIOD (s sortirovkoy po obiemu):")
print("="*80)

all_beers = df.groupby('BeerName').agg({
    'VolumeByPortions': 'sum',
    'DishAmountInt': 'sum',
    'ProductCostBase.ProductCost': 'sum'
}).reset_index()

all_beers = all_beers.sort_values('VolumeByPortions', ascending=False)

print(f"\n{'Pivo':<50s} {'Litry':<12} {'Porcii':<10} {'Sebestoimost':<15}")
print("-" * 100)

for _, row in all_beers.iterrows():
    print(f"{row['BeerName']:<50s} {row['VolumeByPortions']:<12.2f} {int(row['DishAmountInt']):<10} {row['ProductCostBase.ProductCost']:<15.2f}")

# Проверяем варианты названий Блек Шип
print("\n" + "="*80)
print("PROVERKA VARIANTOV NAZVANIY:")
print("="*80)

print("\nIschem 'Blek', 'Black', 'Ship', 'Sheep' v nazvaniyakh:")
variants = df[df['DishName'].str.contains('Блек|Блэк|Black|Ship|Sheep', case=False, na=False, regex=True)]

if not variants.empty:
    unique_names = variants['DishName'].unique()
    print(f"\nNayden {len(unique_names)} variantov:")
    for name in sorted(unique_names):
        count = len(variants[variants['DishName'] == name])
        total = variants[variants['DishName'] == name]['VolumeByPortions'].sum()
        print(f"  {name:<60s} ({count} zapisey, {total:.2f}L)")

print("\n" + "="*80)
print("VOZMOZHNYEPRICHINY RAZNICY:")
print("="*80)
print("""
1. Raznoe napisanie nazvaniya (registr, probely, dopolnitelnye symboly)
2. Spisaniya ne svyazannye s prodazhami:
   - Degustacii
   - Brak (isporchennoe pivo)
   - Poteri pri zamene kegi
   - Inventarizaciya
3. Raznye filtry v Office (mozhet vklyucheny vse bary?)
4. Raznye periody (prover tochnye daty v Office)
""")

# Сохраняем детальные данные
black_sheep.to_csv('black_sheep_details.csv', index=False, encoding='utf-8-sig')
festhaus.to_csv('festhaus_details.csv', index=False, encoding='utf-8-sig')
all_beers.to_csv('all_beers_ligovskiy_sept.csv', index=False, encoding='utf-8-sig')

print("\n[SAVED] black_sheep_details.csv")
print("[SAVED] festhaus_details.csv")
print("[SAVED] all_beers_ligovskiy_sept.csv")
print("\n" + "="*80)
