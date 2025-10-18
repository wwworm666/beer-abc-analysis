"""
Создаём маппинг только для АКТИВНЫХ кегов (которые продавались в 2025 году)
"""

import json
import pandas as pd
from datetime import datetime
from olap_reports import OlapReports

print("="*80)
print("SOZDANIE MAPPINGA TOLKO DLya AKTIVNYH KEGOV (2025)")
print("="*80)

# 1. Получаем продажи за 2025 год
olap = OlapReports()
if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

date_from = "2025-01-01"
date_to = datetime.now().strftime('%Y-%m-%d')

print(f"\nPoluchaem dannye za period: {date_from} - {date_to}")

report_data = olap.get_draft_sales_report(date_from, date_to)
olap.disconnect()

if not report_data:
    print("[ERROR] Net dannyh")
    exit()

# 2. Получаем список уникальных блюд которые реально продавались
df = pd.DataFrame(report_data['data'])

# Убираем порции из названий блюд
def clean_dish_name(dish_name):
    import re
    name = re.sub(r'\s*\([0-9,\.]+\)\s*$', '', dish_name)
    return name.strip()

df['DishNameClean'] = df['DishName'].apply(clean_dish_name)
unique_dishes = sorted(df['DishNameClean'].unique())

print(f"\nUnikalnyh blyud v 2025: {len(unique_dishes)}")

# 3. Загружаем все кеги
with open('kegs_products.json', 'r', encoding='utf-8') as f:
    all_kegs = json.load(f)

print(f"Vsego kegov v baze: {len(all_kegs)}")

# 4. Создаём простую таблицу для заполнения
rows = []

for dish in unique_dishes:
    rows.append({
        'DISH_NAME': dish,
        'KEG_NAME': '',  # Заполнить вручную
        'NOTES': ''
    })

# Сохраняем в CSV
csv_file = 'active_dishes_to_kegs_2025.csv'
df_out = pd.DataFrame(rows)
df_out.to_csv(csv_file, index=False, encoding='utf-8-sig')

print(f"\n[SAVED] {csv_file}")

# 5. Также сохраняем список всех кегов для справки
kegs_list = [keg['name'] for keg in all_kegs]
kegs_df = pd.DataFrame({'KEG_NAME': sorted(kegs_list)})
kegs_df.to_csv('all_kegs_reference.csv', index=False, encoding='utf-8-sig')

print(f"[SAVED] all_kegs_reference.csv (dlya spravki)")

print("\n" + "="*80)
print("STATISTIKA:")
print("="*80)

print(f"\nBlyud kotorye nuzhno zapolnit: {len(unique_dishes)}")
print(f"Vsego kegov v spravochnike: {len(all_kegs)}")

# Показываем примеры блюд
print("\n" + "="*80)
print("PRIMERY BLYUD (nuzhno ukazat kegi):")
print("="*80)

for dish in unique_dishes[:20]:
    print(f"  {dish}")

if len(unique_dishes) > 20:
    print(f"  ... i eshche {len(unique_dishes) - 20}")

print("\n" + "="*80)
print("INSTRUKTSIYA:")
print("="*80)

print(f"""
1. Otkroyte: {csv_file}
2. V stolbce KEG_NAME ukazhite TOCHNOE nazvanie kega iz all_kegs_reference.csv
3. Mozhno ukazat neskolko kegov cherez ";" esli odno blyudo delaetsya iz raznyh kegov
4. Primer:
   DISH_NAME          | KEG_NAME                        | NOTES
   Brewlok IPA        | КЕГ Brewlok IPA 20 л            |
   Блек Шип           | КЕГ Блек Шип                    |
   ФестХаус Хеллес    | КЕГ ФестХаус Хеллес             |

5. Posle zapolneniya zapustite: python import_active_kegs_mapping.py
""")
