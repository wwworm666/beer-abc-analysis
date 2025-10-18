"""
Автоматически добавляет новые блюда в маппинг с умным подбором названия кега
"""

import pandas as pd
import re
from datetime import datetime, timedelta
from olap_reports import OlapReports
from keg_mapping import KEG_TO_DISH_MAPPING

def normalize_text(text):
    """Нормализация для сравнения"""
    text = text.lower()
    text = ' '.join(text.split())
    text = text.replace('"', '').replace("'", '').replace('`', '')
    return text

def clean_dish_name(dish_name):
    """Убираем порции и префиксы"""
    # Убираем префикс "НЗ ", "ВО " и т.д.
    name = re.sub(r'^(НЗ|ВО|ТЦ)\s+', '', dish_name, flags=re.IGNORECASE)
    # Убираем порции
    name = re.sub(r'\s*\([0-9,\.]+\)\s*.*$', '', name)
    return name.strip()

def find_best_keg_match(dish_name, all_kegs):
    """Умное сопоставление блюда с кегом"""
    dish_norm = normalize_text(dish_name)

    best_match = None
    best_score = 0

    for keg in all_kegs:
        # Убираем "КЕГ" и объём
        keg_clean = re.sub(r'^кег\s+', '', keg, flags=re.IGNORECASE).strip()
        keg_clean = re.sub(r'\s*\d+\s*л\s*$', '', keg_clean, flags=re.IGNORECASE).strip()
        keg_norm = normalize_text(keg_clean)

        # Точное совпадение
        if dish_norm == keg_norm:
            return keg

        # Блюдо содержится в кеге (и достаточно длинное)
        if dish_norm in keg_norm and len(dish_norm) > 5:
            score = len(dish_norm) / len(keg_norm) * 100
            if score > best_score and score > 70:  # Минимум 70% совпадение
                best_score = score
                best_match = keg

        # Кег содержится в блюде
        elif keg_norm in dish_norm and len(keg_norm) > 5:
            score = len(keg_norm) / len(dish_norm) * 90
            if score > best_score and score > 70:
                best_score = score
                best_match = keg

    return best_match

print("="*80)
print("AVTOMATICHESKOE DOBAVLENIE NOVYH BLYUD")
print("="*80)

# 1. Загружаем существующий маппинг
mapped_dishes = set()
for keg, dishes in KEG_TO_DISH_MAPPING.items():
    mapped_dishes.update(dishes)

print(f"\nV mappinge uzhe est: {len(mapped_dishes)} blyud")

# 2. Получаем реальные продажи
olap = OlapReports()
if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

date_to = datetime.now().strftime('%Y-%m-%d')
date_from = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

print(f"Period proverki: {date_from} - {date_to}")

report_data = olap.get_draft_sales_report(date_from, date_to)
olap.disconnect()

if not report_data:
    print("[ERROR] Net dannyh")
    exit()

# 3. Находим незамапленные блюда
df = pd.DataFrame(report_data['data'])
df['DishClean'] = df['DishName'].apply(clean_dish_name)
unique_dishes_sold = set(df['DishClean'].unique())

unmapped = unique_dishes_sold - mapped_dishes

print(f"Prodayotsya blyud: {len(unique_dishes_sold)}")
print(f"Novyh blyud: {len(unmapped)}")

if len(unmapped) == 0:
    print("\n[OK] Vse blyuda uzhe zamapleny!")
    exit()

# 4. Загружаем список всех кегов
import json
with open('kegs_products.json', 'r', encoding='utf-8') as f:
    all_kegs_data = json.load(f)

all_kegs = [keg['name'] for keg in all_kegs_data]
print(f"Vsego kegov v baze: {len(all_kegs)}")

# 5. Автоматически подбираем кеги для новых блюд
new_mappings = []

print("\n" + "="*80)
print("AVTOMATICHESKIY PODBOR KEGOV:")
print("="*80)

for dish in sorted(unmapped):
    # Подбираем кег
    matched_keg = find_best_keg_match(dish, all_kegs)

    # Считаем продажи
    dish_sales = df[df['DishClean'] == dish]
    total_portions = int(dish_sales['DishAmountInt'].sum())
    bars = dish_sales['departmentName'].unique()

    if matched_keg:
        new_mappings.append({
            'DISH_NAME': dish,
            'KEG_NAME': matched_keg,
            'PORTIONS_30D': total_portions,
            'BARS': ', '.join(bars[:2]) if len(bars) <= 2 else f"{bars[0]} +{len(bars)-1}",
            'STATUS': 'AUTO'
        })
        print(f"[OK] {dish} -> {matched_keg} ({total_portions} porciy)")
    else:
        new_mappings.append({
            'DISH_NAME': dish,
            'KEG_NAME': '',  # Не нашли - нужно заполнить вручную
            'PORTIONS_30D': total_portions,
            'BARS': ', '.join(bars[:2]) if len(bars) <= 2 else f"{bars[0]} +{len(bars)-1}",
            'STATUS': 'MANUAL_REQUIRED'
        })
        print(f"[??] {dish} -> [NE NAYDENO] ({total_portions} porciy)")

# 6. Добавляем в основной CSV файл
csv_file = 'tochno prav spisok - active_dishes_to_kegs_CLEAN.csv.csv'

try:
    # Читаем существующий файл
    df_existing = pd.read_csv(csv_file, encoding='utf-8-sig')
    print(f"\n[LOADED] {csv_file}")
    print(f"Bylo zapisey: {len(df_existing)}")

    # Добавляем новые
    df_new = pd.DataFrame(new_mappings)

    # Объединяем (только DISH_NAME и KEG_NAME)
    df_to_add = df_new[['DISH_NAME', 'KEG_NAME']].copy()
    df_updated = pd.concat([df_existing, df_to_add], ignore_index=True)

    # Убираем дубликаты по DISH_NAME
    df_updated = df_updated.drop_duplicates(subset=['DISH_NAME'], keep='first')
    df_updated = df_updated.sort_values('DISH_NAME')

    # Сохраняем
    df_updated.to_csv(csv_file, index=False, encoding='utf-8-sig')

    print(f"Stalo zapisey: {len(df_updated)}")
    print(f"Dobavleno novyh: {len(new_mappings)}")
    print(f"[SAVED] {csv_file}")

    # Также сохраняем детали новых блюд для проверки
    review_file = 'NEW_DISHES_FOR_REVIEW.csv'
    df_new.to_csv(review_file, index=False, encoding='utf-8-sig')
    print(f"[SAVED] {review_file} (dlya proverki)")

except Exception as e:
    print(f"[ERROR] Ne udalos obnovit CSV: {e}")
    exit()

# 7. Автоматически импортируем обновлённый маппинг
print("\n" + "="*80)
print("AVTOMATICHESKIY IMPORT OBNOVLENNOGO MAPPINGA:")
print("="*80)

import subprocess
result = subprocess.run(['python', 'import_final_mapping.py'],
                       capture_output=True, text=True, encoding='utf-8', errors='ignore')

if result.returncode == 0:
    print("[OK] Mapping uspeshno obnovlen!")
else:
    print("[ERROR] Oshibka importa mappinga")
    print(result.stderr)

# 8. Статистика
print("\n" + "="*80)
print("STATISTIKA:")
print("="*80)

auto_matched = len([m for m in new_mappings if m['STATUS'] == 'AUTO'])
manual_required = len([m for m in new_mappings if m['STATUS'] == 'MANUAL_REQUIRED'])

print(f"\nNovyh blyud dobavleno: {len(new_mappings)}")
print(f"  Avtomaticheski zamapleno: {auto_matched}")
print(f"  Trebuyet ruchnoy proverki: {manual_required}")

if manual_required > 0:
    print("\n" + "="*80)
    print("VNIMANIE! TREBUETSYA RUCHNAYA PROVERKA:")
    print("="*80)

    manual_dishes = [m for m in new_mappings if m['STATUS'] == 'MANUAL_REQUIRED']
    for dish_info in manual_dishes:
        print(f"\n{dish_info['DISH_NAME']}")
        print(f"  Prodano: {dish_info['PORTIONS_30D']} porciy")
        print(f"  Bary: {dish_info['BARS']}")
        print(f"  KEG_NAME: [PUSTOE - zapolnite v CSV]")

print("\n" + "="*80)
print("CHTO DELAT DALSHE:")
print("="*80)

if manual_required > 0:
    print(f"""
1. Otkroyte: {review_file}
2. Prover'te avtomaticheskiy mapping (STATUS=AUTO)
3. Zapolnite pustye KEG_NAME (STATUS=MANUAL_REQUIRED)
4. Otkroyte: {csv_file}
5. Ispravte oshibki esli est
6. Zapustite: python import_final_mapping.py
7. Perezapustite server
""")
else:
    print(f"""
1. Prover'te: {review_file}
2. Esli vse pravilno - gotovo!
3. Perezapustite server dlya primeneniya:
   Ctrl+C
   python app.py
""")
