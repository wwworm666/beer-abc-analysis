"""
Проверяет какие блюда продаются, но не имеют маппинга к кегам
"""

import pandas as pd
from datetime import datetime, timedelta
from olap_reports import OlapReports
from keg_mapping import KEG_TO_DISH_MAPPING

print("="*80)
print("PROVERKA NEZAMAPLENNYH BLYUD")
print("="*80)

# Получаем список всех замапленных блюд
mapped_dishes = set()
for keg, dishes in KEG_TO_DISH_MAPPING.items():
    mapped_dishes.update(dishes)

print(f"\nVsego v mappinge blyud: {len(mapped_dishes)}")

# Получаем реальные продажи за последние 30 дней
olap = OlapReports()
if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

date_to = datetime.now().strftime('%Y-%m-%d')
date_from = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

print(f"Period: {date_from} - {date_to}")

report_data = olap.get_draft_sales_report(date_from, date_to)
olap.disconnect()

if not report_data:
    print("[ERROR] Net dannyh")
    exit()

# Анализируем продажи
df = pd.DataFrame(report_data['data'])

# Убираем порции
import re
def clean_dish_name(dish_name):
    name = re.sub(r'\s*\([0-9,\.]+\)\s*.*$', '', dish_name)
    return name.strip()

df['DishClean'] = df['DishName'].apply(clean_dish_name)
unique_dishes_sold = set(df['DishClean'].unique())

print(f"Prodayotsya blyud (za 30 dney): {len(unique_dishes_sold)}")

# Находим незамапленные
unmapped = unique_dishes_sold - mapped_dishes

print("\n" + "="*80)
print(f"NOVYE BLYUDA BEZ MAPPINGA: {len(unmapped)}")
print("="*80)

if unmapped:
    # Группируем по барам и считаем объёмы продаж
    unmapped_details = []

    for dish in sorted(unmapped):
        dish_sales = df[df['DishClean'] == dish]
        total_amount = dish_sales['DishAmountInt'].sum()
        bars = dish_sales['departmentName'].unique()

        unmapped_details.append({
            'DISH_NAME': dish,
            'TOTAL_PORTIONS': int(total_amount),
            'BARS': ', '.join(bars[:3]) if len(bars) <= 3 else f"{bars[0]} +{len(bars)-1}",
            'KEG_NAME': '',  # Заполнить вручную
        })

    # Сохраняем в CSV
    df_unmapped = pd.DataFrame(unmapped_details)
    df_unmapped = df_unmapped.sort_values('TOTAL_PORTIONS', ascending=False)

    output_file = 'NEW_DISHES_TO_ADD.csv'
    df_unmapped.to_csv(output_file, index=False, encoding='utf-8-sig')

    print(f"\n[SAVED] {output_file}")
    print("\nSamye populyarnye novye blyuda:")

    for idx, row in df_unmapped.head(20).iterrows():
        print(f"\n{row['DISH_NAME']}")
        print(f"  Prodano porciy: {row['TOTAL_PORTIONS']}")
        print(f"  Bary: {row['BARS']}")

    if len(unmapped) > 20:
        print(f"\n... i eshche {len(unmapped) - 20} blyud")

    print("\n" + "="*80)
    print("CHTO DELAT:")
    print("="*80)
    print(f"""
1. Otkroyte: {output_file}
2. Zapolnite stolbec KEG_NAME dlya novyh blyud
3. Zapustite: python add_new_dishes_to_mapping.py
""")

else:
    print("\nVse blyuda zamapleny! Novyh blyud net.")

print("\n" + "="*80)
print("STATISTIKA POKRYTIYA:")
print("="*80)

coverage = (len(unique_dishes_sold - unmapped) / len(unique_dishes_sold) * 100) if unique_dishes_sold else 0
print(f"\nPokrytie mappingom: {coverage:.1f}%")
print(f"Zamapleno: {len(unique_dishes_sold - unmapped)}")
print(f"Ne zamapleno: {len(unmapped)}")
