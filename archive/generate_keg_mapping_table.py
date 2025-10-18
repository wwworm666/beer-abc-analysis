"""
Генерируем таблицу со всеми кегами и их привязками к блюдам для ручной проверки
"""

import json
import pandas as pd
from datetime import datetime, timedelta
from olap_reports import OlapReports

print("="*80)
print("GENERACIYA TABLICY KEGOV I IH PRIVYAZOK K BLYUDAM")
print("="*80)

# 1. Загружаем список всех кегов из API
with open('kegs_products.json', 'r', encoding='utf-8') as f:
    all_kegs = json.load(f)

print(f"\nVsego kegov v sisteme: {len(all_kegs)}")

# 2. Получаем данные о продажах разливного пива за последние 90 дней
# чтобы понять какие блюда реально продаются
olap = OlapReports()

if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya k API")
    exit()

date_to = datetime.now().strftime('%Y-%m-%d')
date_from = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

print(f"\nPoluchaem dannye o prodazhah razlivnogo za period: {date_from} - {date_to}")

report_data = olap.get_draft_sales_report(date_from, date_to)
olap.disconnect()

if not report_data:
    print("[ERROR] Ne udalos poluchit dannye")
    exit()

# 3. Парсим данные о блюдах
df = pd.DataFrame(report_data['data'])

# Получаем уникальные названия блюд разливного пива
unique_dishes = df['DishName'].unique()
print(f"\nUnikalnыh poziciy razlivnogo piva: {len(unique_dishes)}")

# 4. Создаем таблицу для маппинга
mapping_table = []

for keg in all_kegs:
    keg_name = keg['name']
    keg_id = keg['id']

    # Убираем "КЕГ " из начала для поиска
    search_name = keg_name.replace('КЕГ ', '').replace('кег ', '').strip()

    # Ищем подходящие блюда
    matched_dishes = []

    for dish in unique_dishes:
        dish_clean = dish.split('(')[0].strip()  # Убираем порцию "(0.5)" и т.д.

        # Простой поиск по вхождению подстроки
        if search_name.lower() in dish_clean.lower() or dish_clean.lower() in search_name.lower():
            matched_dishes.append(dish_clean)

    # Удаляем дубликаты
    matched_dishes = list(set(matched_dishes))

    mapping_table.append({
        'KEG_ID': keg_id,
        'KEG_NAME': keg_name,
        'MATCHED_DISHES': ', '.join(matched_dishes) if matched_dishes else '[НЕТ СОВПАДЕНИЙ]',
        'DISHES_COUNT': len(matched_dishes),
        'STATUS': 'OK' if len(matched_dishes) > 0 else 'НЕТ ПРИВЯЗКИ'
    })

# 5. Создаем DataFrame и сортируем
df_mapping = pd.DataFrame(mapping_table)

# Сортируем: сначала кеги без привязки, потом с привязкой по алфавиту
df_mapping = df_mapping.sort_values(['STATUS', 'KEG_NAME'])

# 6. Сохраняем в CSV (Excel можно открыть позже)
csv_file = 'keg_to_dish_mapping_CHECK.csv'
df_mapping.to_csv(csv_file, index=False, encoding='utf-8-sig')
print(f"\n[SAVED] {csv_file}")

# 8. Статистика
print("\n" + "="*80)
print("STATISTIKA:")
print("="*80)

total_kegs = len(df_mapping)
kegs_with_match = len(df_mapping[df_mapping['STATUS'] == 'OK'])
kegs_without_match = len(df_mapping[df_mapping['STATUS'] == 'НЕТ ПРИВЯЗКИ'])

print(f"\nVsego kegov: {total_kegs}")
print(f"S privyazkami: {kegs_with_match} ({kegs_with_match/total_kegs*100:.1f}%)")
print(f"Bez privyazok: {kegs_without_match} ({kegs_without_match/total_kegs*100:.1f}%)")

# 9. Показываем примеры кегов БЕЗ привязки
print("\n" + "="*80)
print("PRIMERY KEGOV BEZ PRIVYAZKI (nuzhno dobavit vruchnuyu):")
print("="*80)

no_match = df_mapping[df_mapping['STATUS'] == 'НЕТ ПРИВЯЗКИ'].head(20)
for idx, row in no_match.iterrows():
    print(f"\n{row['KEG_NAME']}")
    print(f"  ID: {row['KEG_ID']}")

# 10. Показываем примеры кегов С НЕСКОЛЬКИМИ привязками (могут быть ошибки)
print("\n" + "="*80)
print("KEGI S NESKOLKIMI PRIVYAZKAMI (proverit na oshibki):")
print("="*80)

multiple_matches = df_mapping[df_mapping['DISHES_COUNT'] > 1].head(15)
for idx, row in multiple_matches.iterrows():
    print(f"\n{row['KEG_NAME']}")
    print(f"  Privyazannye blyuda: {row['MATCHED_DISHES']}")

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
print(f"\nOtkroyte fayl {csv_file} v Excel ili tekstovom redaktore")
print("Prover'te i ispravte oshibki v stolbce MATCHED_DISHES")
print("Posle proverki my mozhem sozdat obnovlennyy mapping file")
