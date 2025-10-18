"""
Детальная проверка расчёта для Блек Шип
Ищем где теряется 5.75L
"""

from datetime import datetime
from olap_reports import OlapReports
import pandas as pd
import re

print("="*80)
print("DETALNAYA PROVERKA BLEK SHIP")
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

# Получаем RAW данные без фильтра по официантам
report_data = olap.get_draft_sales_report(date_from, date_to, bar_name)
olap.disconnect()

if not report_data or not report_data.get('data'):
    print("[ERROR] Net dannykh")
    exit()

df = pd.DataFrame(report_data['data'])
print(f"[OK] Polucheno VSEGO zapisey: {len(df)}\n")

# Показываем все поля первой записи
print("="*80)
print("POLYA V DANNYKH (pervaya zapis):")
print("="*80)
if len(df) > 0:
    first = df.iloc[0]
    for col in sorted(df.columns):
        print(f"  {col:40s} = {first[col]}")

# Ищем ВСЕ упоминания Блек Шип
print("\n" + "="*80)
print("POISK VSEKH VARIANTOV 'BLEK SHIP':")
print("="*80)

# Разные варианты поиска
search_variants = [
    ("Точное совпадение 'Блек Шип'", df['DishName'].str.contains('Блек Шип', case=False, na=False)),
    ("Вариант 'Блэк Шип'", df['DishName'].str.contains('Блэк Шип', case=False, na=False)),
    ("English 'Black Sheep'", df['DishName'].str.contains('Black Sheep', case=False, na=False)),
    ("Только 'Sheep'", df['DishName'].str.contains('Sheep', case=False, na=False, regex=False)),
    ("Только 'Шип'", df['DishName'].str.contains('Шип', case=False, na=False, regex=False)),
]

for variant_name, mask in search_variants:
    found = df[mask]
    if not found.empty:
        print(f"\n{variant_name}: {len(found)} zapisey")
        unique_names = found['DishName'].unique()
        for name in unique_names:
            print(f"  - {name}")

# Основной поиск
df_bs = df[df['DishName'].str.contains('Блек Шип|Блэк Шип|Black Sheep', case=False, na=False, regex=True)]

print(f"\n" + "="*80)
print(f"NAYDEN VSEGO: {len(df_bs)} zapisey")
print("="*80)

# Преобразуем числа
df_bs['DishAmountInt'] = pd.to_numeric(df_bs['DishAmountInt'], errors='coerce')

# Извлекаем объём из названия разными способами
def extract_volume_v1(dish_name):
    """Вариант 1: (0,5) или (0.5)"""
    pattern = r'\((\d+[,\.]\d+)\)'
    match = re.search(pattern, dish_name)
    if match:
        return float(match.group(1).replace(',', '.'))
    return None

def extract_volume_v2(dish_name):
    """Вариант 2: 0,5л или 0.5l"""
    pattern = r'(\d+[,\.]\d+)\s*[лlL]'
    match = re.search(pattern, dish_name.lower())
    if match:
        return float(match.group(1).replace(',', '.'))
    return None

df_bs['Volume_V1'] = df_bs['DishName'].apply(extract_volume_v1)
df_bs['Volume_V2'] = df_bs['DishName'].apply(extract_volume_v2)

# Используем первый успешный вариант
df_bs['PortionVolume'] = df_bs['Volume_V1'].fillna(df_bs['Volume_V2']).fillna(0)

# Рассчитываем литры
df_bs['TotalLiters'] = df_bs['DishAmountInt'] * df_bs['PortionVolume']

# Показываем детали
print(f"\n{'DishName':<60s} {'Porcii':<8s} {'Obem':<8s} {'Litry':<10s}")
print("-" * 100)

for _, row in df_bs.iterrows():
    print(f"{row['DishName']:<60s} {int(row['DishAmountInt']):<8d} {row['PortionVolume']:<8.2f} {row['TotalLiters']:<10.2f}")

# Итого
total_portions = df_bs['DishAmountInt'].sum()
total_liters = df_bs['TotalLiters'].sum()

print("-" * 100)
print(f"{'ITOGO':<60s} {int(total_portions):<8d} {'':<8s} {total_liters:<10.2f}")

# Проверка на пропущенные объёмы
missing_volumes = df_bs[df_bs['PortionVolume'] == 0]
if not missing_volumes.empty:
    print(f"\n[WARNING] Propuschen obyom v {len(missing_volumes)} zapisyakh:")
    for name in missing_volumes['DishName'].unique():
        print(f"  - {name}")

# Группировка по размеру порции
print("\n" + "="*80)
print("GRUPPIROVKA PO RAZMERU PORCII:")
print("="*80)

by_size = df_bs.groupby('PortionVolume').agg({
    'DishAmountInt': 'sum',
    'TotalLiters': 'sum'
}).reset_index()

print(f"\n{'Obem porcii':<15s} {'Kolichestvo':<15s} {'Litry':<15s}")
print("-" * 50)
for _, row in by_size.iterrows():
    print(f"{row['PortionVolume']:<15.2f} {int(row['DishAmountInt']):<15d} {row['TotalLiters']:<15.2f}")

print("\n" + "="*80)
print("SRAVNENIE:")
print("="*80)
print(f"Nash raschet:     {total_liters:.2f} L")
print(f"Office otchet:    75.00 L")
print(f"Razniza:          {75 - total_liters:.2f} L")
print(f"Procent:          {((75 - total_liters) / 75 * 100):.1f}%")

if abs(75 - total_liters) > 1:
    print("\n[PROBLEM] Razniza bolshe 1L!")
    print("\nVOZMOZHNYE PRICHINY:")
    print("1. V Office ispolzuetsya drugoy filtr (mozhet ne po baru?)")
    print("2. V Office drugoy period (prover tochnye daty)")
    print("3. Est eshche varianty nazvaniya kotorye my ne nashli")
    print("4. V Office schitaetsya po-drugomu (napr, po ingredientam)")
    print("\nREKOMENDACIYa: Proverit v Office:")
    print("  - Tochnyy period: 01.09.2025 - 30.09.2025")
    print("  - Tochnyy bar: Ligovskiy")
    print("  - Tochnyy produkt: KAK IMENNO nazyvaetsya v otchete?")
else:
    print("\n[OK] Razniza menee 1L - eto normalno!")

# Сохраняем
df_bs.to_csv('blacksheep_detailed.csv', index=False, encoding='utf-8-sig')
print("\n[SAVED] blacksheep_detailed.csv")
print("="*80)
