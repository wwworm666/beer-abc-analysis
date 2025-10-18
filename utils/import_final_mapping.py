"""
Импорт финального маппинга из CSV с правильными данными
"""

import pandas as pd
import json

print("="*80)
print("IMPORT FINALNOGO MAPPINGA")
print("="*80)

# Читаем правильный CSV
csv_file = 'tochno prav spisok - active_dishes_to_kegs_CLEAN.csv.csv'
df = pd.read_csv(csv_file, encoding='utf-8-sig')

print(f"\n[LOADED] {csv_file}")
print(f"Vsego zapisey: {len(df)}")

# Создаём маппинг KEG_NAME -> [DISH_NAME]
keg_to_dishes = {}

for idx, row in df.iterrows():
    dish_name = row['DISH_NAME']
    keg_name = row['KEG_NAME']

    # Пропускаем пустые
    if pd.isna(keg_name) or keg_name == '':
        print(f"[WARNING] Pustoy keg dlya: {dish_name}")
        continue

    keg_name = keg_name.strip()
    dish_name = dish_name.strip()

    # Добавляем в маппинг
    if keg_name not in keg_to_dishes:
        keg_to_dishes[keg_name] = []
    keg_to_dishes[keg_name].append(dish_name)

print(f"\nUnikalnyh kegov: {len(keg_to_dishes)}")
print(f"Unikalnyh blyud: {len(df)}")

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
    # Используем repr() для правильного экранирования кавычек
    keg_repr = repr(keg_name)
    dishes_repr = ', '.join([repr(d) for d in sorted(dish_list)])
    py_content += f'    {keg_repr}: [{dishes_repr}],\n'

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

print(f"\nVsego blyud: {len(dish_to_keg)}")
print(f"Vsego kegov: {len(keg_to_dishes)}")

# Кеги с несколькими блюдами
multi_dish_kegs = {k: v for k, v in keg_to_dishes.items() if len(v) > 1}
if multi_dish_kegs:
    print(f"\nKegi s neskolkimi blyudami: {len(multi_dish_kegs)}")
    for keg, dishes in sorted(multi_dish_kegs.items())[:10]:
        print(f"\n{keg}:")
        for dish in sorted(dishes):
            print(f"  - {dish}")
        if len(multi_dish_kegs) > 10:
            break

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
print("\nMapping uspeshno importirovan!")
print("Zapustite server: python app.py")
print("Otkroyte: http://localhost:5000/draft")
