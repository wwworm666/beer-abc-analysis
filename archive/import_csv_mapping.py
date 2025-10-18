"""
Импортируем маппинг из CSV файла после ручной проверки
"""

import pandas as pd
import json

print("="*80)
print("IMPORT MAPPINGA IZ CSV")
print("="*80)

# Читаем CSV
csv_file = 'keg_dish_mapping_EDIT.csv'
df = pd.read_csv(csv_file, encoding='utf-8-sig')

print(f"\n[LOADED] {csv_file}")
print(f"Vsego zapisey: {len(df)}")

# Подсчитываем статистику
filled = len(df[(df['DISH_NAME'].notna()) & (df['DISH_NAME'] != '')])
empty = len(df[(df['DISH_NAME'].isna()) | (df['DISH_NAME'] == '')])
not_sold = len(df[df['DISH_NAME'] == 'НЕ ПРОДАЕТСЯ'])

print(f"\nZapolneno: {filled}")
print(f"Pustыh: {empty}")
print(f"Ne prodaetsya: {not_sold}")

# Создаём маппинг
mapping = {}

for idx, row in df.iterrows():
    keg_name = row['KEG_NAME']
    dish_name = row['DISH_NAME']

    # Пропускаем пустые и "НЕ ПРОДАЕТСЯ"
    if pd.isna(dish_name) or dish_name == '' or dish_name == 'НЕ ПРОДАЕТСЯ':
        continue

    # Добавляем в маппинг
    mapping[keg_name] = [dish_name.strip()]

print(f"\nV mappinge: {len(mapping)} kegov")

# Сохраняем в Python файл
py_content = '''"""
МАППИНГ КЕГОВ К БЛЮДАМ
Импортировано из keg_dish_mapping_EDIT.csv
Дата: {}
"""

KEG_TO_DISH_MAPPING = {{
'''.format(pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'))

for keg_name, dish_list in sorted(mapping.items()):
    dishes_str = ', '.join([f"'{d}'" for d in dish_list])
    py_content += f'    "{keg_name}": [{dishes_str}],\n'

py_content += '}\n'

with open('keg_mapping.py', 'w', encoding='utf-8') as f:
    f.write(py_content)

print(f"[SAVED] keg_mapping.py")

# Сохраняем в JSON
with open('keg_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(mapping, f, indent=2, ensure_ascii=False)

print(f"[SAVED] keg_mapping.json")

# Создаём обратный маппинг (блюдо -> кеги)
dish_to_kegs = {}
for keg, dishes in mapping.items():
    for dish in dishes:
        if dish not in dish_to_kegs:
            dish_to_kegs[dish] = []
        dish_to_kegs[dish].append(keg)

with open('dish_to_keg_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(dish_to_kegs, f, indent=2, ensure_ascii=False)

print(f"[SAVED] dish_to_keg_mapping.json")

# Статистика по блюдам
print("\n" + "="*80)
print("STATISTIKA PO BLYUDAM:")
print("="*80)

unique_dishes = set()
for dish_list in mapping.values():
    unique_dishes.update(dish_list)

print(f"\nUnikalnyh blyud: {len(unique_dishes)}")

# Блюда с несколькими кегами
multi_keg = {d: kegs for d, kegs in dish_to_kegs.items() if len(kegs) > 1}
if multi_keg:
    print(f"\nBlyuda s neskolkimi kegami: {len(multi_keg)}")
    for dish, kegs in sorted(multi_keg.items())[:10]:
        print(f"\n{dish}:")
        for keg in kegs[:3]:  # Показываем первые 3
            print(f"  - {keg}")
        if len(kegs) > 3:
            print(f"  ... i eshche {len(kegs)-3}")

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
print("\nMapping uspeshno importirovan!")
print("Teper mozhno ispolzovat v draft_analysis.py i waiter_analysis.py")
