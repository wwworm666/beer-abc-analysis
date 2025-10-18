"""
ФИНАЛЬНАЯ проверка с правильным маппингом
Сравниваем с ТОЧНЫМИ данными Office
"""

from datetime import datetime
from olap_reports import OlapReports
import pandas as pd
import re
from final_perfect_mapping import OFFICE_EXACT, CORRECT_KEG_MAPPING

print("="*90)
print("FINALNOE SRAVNENIE S OFFICE (TOCHNYE DANNYE)")
print("="*90)

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

# Создаём обратный маппинг для поиска
DISH_TO_KEG = {v.lower().strip(): k for k, v in CORRECT_KEG_MAPPING.items()}

# Также добавляем варианты с разным регистром
extra_mappings = {
    "карлова корчма": "КЕГ Карлова Корчма Премиум 30 л",
    "ребел эппл дикий крест": "КЕГ Rebel Apple Дикий Крест",
}
DISH_TO_KEG.update(extra_mappings)

def map_dish_to_keg(beer_name):
    key = beer_name.lower().strip()
    return DISH_TO_KEG.get(key, f"[НЕ НАЙДЕНО] {beer_name}")

df['KegName'] = df['BeerName'].apply(map_dish_to_keg)

# Группируем по кегам
kegs_result = df.groupby('KegName').agg({
    'TotalLiters': 'sum',
    'DishAmountInt': 'sum'
}).reset_index()

kegs_result = kegs_result.sort_values('TotalLiters', ascending=False)

# Создаём таблицу сравнения
print("="*100)
print(f"{'KEGA (TOVAR)':<55s} {'Office':<12s} {'Nash':<12s} {'Razniza':<12s} {'%':<8s}")
print("="*100)

total_office = 0
total_our = 0
perfect_matches = 0
close_matches = 0
big_differences = 0

for keg_name, office_liters in sorted(OFFICE_EXACT.items()):
    # Ищем в наших данных
    our_data = kegs_result[kegs_result['KegName'] == keg_name]

    if not our_data.empty:
        our_liters = our_data.iloc[0]['TotalLiters']
    else:
        our_liters = 0.0

    diff = our_liters - office_liters
    diff_pct = (diff / office_liters * 100) if office_liters > 0 else 0

    total_office += office_liters
    total_our += our_liters

    # Категоризация
    marker = ""
    if abs(diff) < 0.5:
        marker = " OTLICHNO!"
        perfect_matches += 1
    elif abs(diff) < 2:
        marker = " OK"
        close_matches += 1
    else:
        marker = " <-- PROBLEMA"
        big_differences += 1

    print(f"{keg_name:<55s} {office_liters:<12.3f} {our_liters:<12.3f} {diff:<12.3f} {diff_pct:<8.1f}%{marker}")

print("="*100)
print(f"{'ITOGO':<55s} {total_office:<12.3f} {total_our:<12.3f} {total_our - total_office:<12.3f} {((total_our - total_office) / total_office * 100 if total_office > 0 else 0):<8.1f}%")

# Проверяем не найденные блюда
not_found = kegs_result[kegs_result['KegName'].str.contains('[НЕ НАЙДЕНО]', regex=False)]

if not not_found.empty:
    print("\n" + "="*100)
    print("BLYUDA BEZ KEGI:")
    print("="*100)
    for _, row in not_found.iterrows():
        print(f"  {row['KegName']:<60s} {row['TotalLiters']:.2f}L")

print("\n" + "="*100)
print("STATISTIKA:")
print("="*100)
print(f"Vsego keg v Office: {len(OFFICE_EXACT)}")
print(f"Tochnoe sovpadenie (< 0.5L): {perfect_matches}")
print(f"Blizkoe sovpadenie (< 2L): {close_matches}")
print(f"Bolshaya razniza (> 2L): {big_differences}")
print(f"\nObschaya razniza: {total_our - total_office:.2f}L ({((total_our - total_office) / total_office * 100 if total_office > 0 else 0):.1f}%)")

# Детализация по проблемным кегам
if big_differences > 0:
    print("\n" + "="*100)
    print("DETALIZACIYA PO PROBLEMNYM KEGAM:")
    print("="*100)

    for keg_name, office_liters in sorted(OFFICE_EXACT.items()):
        our_data = kegs_result[kegs_result['KegName'] == keg_name]
        if not our_data.empty:
            our_liters = our_data.iloc[0]['TotalLiters']
            diff = our_liters - office_liters

            if abs(diff) >= 2:
                print(f"\n{keg_name}: Office={office_liters:.2f}L, Nash={our_liters:.2f}L, Diff={diff:.2f}L")

                # Ищем все блюда для этой кеги
                dish_name = CORRECT_KEG_MAPPING.get(keg_name, "")
                if dish_name:
                    dishes = df[df['BeerName'].str.lower() == dish_name.lower()]
                    if not dishes.empty:
                        print(f"  Vsego prodazh: {len(dishes)} zapisey")
                        by_size = dishes.groupby('PortionVolume').agg({
                            'DishAmountInt': 'sum',
                            'TotalLiters': 'sum'
                        }).reset_index()

                        for _, row in by_size.iterrows():
                            print(f"    Porciya {row['PortionVolume']}L: {int(row['DishAmountInt'])} sht = {row['TotalLiters']:.2f}L")

# Сохраняем
comparison = []
for keg_name, office_liters in OFFICE_EXACT.items():
    our_data = kegs_result[kegs_result['KegName'] == keg_name]
    our_liters = our_data.iloc[0]['TotalLiters'] if not our_data.empty else 0.0

    comparison.append({
        'KegName': keg_name,
        'Office_Liters': office_liters,
        'Our_Liters': our_liters,
        'Difference': our_liters - office_liters,
        'Difference_Pct': ((our_liters - office_liters) / office_liters * 100) if office_liters > 0 else 0
    })

pd.DataFrame(comparison).to_csv('final_comparison_exact.csv', index=False, encoding='utf-8-sig')
print("\n[SAVED] final_comparison_exact.csv")
print("="*100)
