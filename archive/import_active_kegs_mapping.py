"""
Импорт маппинга активных блюд к кегам из CSV
"""

import pandas as pd
import json

print("="*80)
print("IMPORT MAPPINGA IZ CSV")
print("="*80)

# Читаем CSV
csv_file = 'active_dishes_to_kegs_CLEAN.csv'
df = pd.read_csv(csv_file, encoding='utf-8-sig')

print(f"\n[LOADED] {csv_file}")
print(f"Vsego zapisey: {len(df)}")

# Подсчитываем статистику
filled = len(df[(df['KEG_NAME'].notna()) & (df['KEG_NAME'] != '')])
empty = len(df[(df['KEG_NAME'].isna()) | (df['KEG_NAME'] == '')])

print(f"Zapolneno: {filled}")
print(f"Pustыh: {empty}")

if empty > 0:
    print(f"\n[WARNING] Eshche {empty} blyud bez mappinga!")
    response = input("Prodolzhit i sozdat mapping dlya zapolnennyh? (y/n): ")
    if response.lower() != 'y':
        print("Otmeneno.")
        exit()

# Создаём маппинг KEG_NAME -> [DISH_NAME]
# Т.к. несколько блюд могут ссылаться на один кег
keg_to_dishes = {}

for idx, row in df.iterrows():
    dish_name = row['DISH_NAME']
    keg_name = row['KEG_NAME']

    # Пропускаем пустые
    if pd.isna(keg_name) or keg_name == '':
        continue

    keg_name = keg_name.strip()

    # Обрабатываем несколько кегов через ";"
    kegs = [k.strip() for k in keg_name.split(';')]

    for keg in kegs:
        if keg not in keg_to_dishes:
            keg_to_dishes[keg] = []
        keg_to_dishes[keg].append(dish_name)

print(f"\nUnikalnyh kegov v mappinge: {len(keg_to_dishes)}")

# Сохраняем в keg_mapping.py
py_content = f'''"""
МАППИНГ КЕГОВ К БЛЮДАМ
Импортировано из {csv_file}
Дата: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
Только активные кеги продававшиеся в 2025 году
"""

KEG_TO_DISH_MAPPING = {{
'''

for keg_name, dish_list in sorted(keg_to_dishes.items()):
    # Убираем дубликаты
    dish_list = list(set(dish_list))
    dishes_str = ', '.join([f"'{d}'" for d in sorted(dish_list)])
    py_content += f'    "{keg_name}": [{dishes_str}],\n'

py_content += '}\n'

with open('keg_mapping.py', 'w', encoding='utf-8') as f:
    f.write(py_content)

print(f"[SAVED] keg_mapping.py")

# Сохраняем в JSON
with open('keg_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(keg_to_dishes, f, indent=2, ensure_ascii=False)

print(f"[SAVED] keg_mapping.json")

# Создаём обратный маппинг (блюдо -> кег)
dish_to_keg = {}
for keg, dishes in keg_to_dishes.items():
    for dish in dishes:
        dish_to_keg[dish] = keg

with open('dish_to_keg_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(dish_to_keg, f, indent=2, ensure_ascii=False)

print(f"[SAVED] dish_to_keg_mapping.json")

# Статистика
print("\n" + "="*80)
print("STATISTIKA:")
print("="*80)

print(f"\nVsego blyud v mappinge: {len(dish_to_keg)}")
print(f"Vsego kegov: {len(keg_to_dishes)}")

# Кеги с несколькими блюдами
multi_dish_kegs = {k: v for k, v in keg_to_dishes.items() if len(v) > 1}
if multi_dish_kegs:
    print(f"\nKegi s neskolkimi blyudami: {len(multi_dish_kegs)}")
    for keg, dishes in list(multi_dish_kegs.items())[:5]:
        print(f"\n{keg}:")
        for dish in dishes:
            print(f"  - {dish}")

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
print("\nMapping uspeshno importirovan!")
print("Teper mozhno zapustit server: python app.py")
print("I proverit v brauzere: http://localhost:5000/draft")
