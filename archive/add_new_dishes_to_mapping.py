"""
Добавляет новые блюда к существующему маппингу
"""

import pandas as pd
import json
from keg_mapping import KEG_TO_DISH_MAPPING

print("="*80)
print("DOBAVLENIE NOVYH BLYUD K MAPPINGU")
print("="*80)

# Читаем файл с новыми блюдами
csv_file = 'NEW_DISHES_TO_ADD.csv'

try:
    df_new = pd.read_csv(csv_file, encoding='utf-8-sig')
except FileNotFoundError:
    print(f"[ERROR] Fayl {csv_file} ne nayden!")
    print("Snachala zapustite: python check_unmapped_dishes.py")
    exit()

print(f"\n[LOADED] {csv_file}")
print(f"Vsego novyh blyud: {len(df_new)}")

# Фильтруем только заполненные
df_filled = df_new[(df_new['KEG_NAME'].notna()) & (df_new['KEG_NAME'] != '')]
filled_count = len(df_filled)

print(f"Zapolneno: {filled_count}")

if filled_count == 0:
    print("\n[WARNING] Net zapolnennyh blyud!")
    print("Zapolnite KEG_NAME v faylе i zapustite snova")
    exit()

# Создаём обновлённый маппинг
updated_mapping = dict(KEG_TO_DISH_MAPPING)  # Копируем старый

for idx, row in df_filled.iterrows():
    dish_name = row['DISH_NAME'].strip()
    keg_name = row['KEG_NAME'].strip()

    if keg_name not in updated_mapping:
        updated_mapping[keg_name] = []

    # Добавляем блюдо если его ещё нет
    if dish_name not in updated_mapping[keg_name]:
        updated_mapping[keg_name].append(dish_name)
        print(f"[+] {keg_name} -> {dish_name}")

# Сохраняем обновлённый маппинг
py_content = f'''"""
МАППИНГ КЕГОВ К БЛЮДАМ
Обновлено: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
Добавлено новых блюд: {filled_count}
"""

KEG_TO_DISH_MAPPING = {{
'''

for keg_name, dish_list in sorted(updated_mapping.items()):
    dishes_str = ', '.join([f"'{d}'" for d in sorted(dish_list)])
    py_content += f'    "{keg_name}": [{dishes_str}],\n'

py_content += '}\n'

with open('keg_mapping.py', 'w', encoding='utf-8') as f:
    f.write(py_content)

print(f"\n[SAVED] keg_mapping.py")

# Сохраняем в JSON
with open('keg_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(updated_mapping, f, indent=2, ensure_ascii=False)

print(f"[SAVED] keg_mapping.json")

# Создаём обратный маппинг
dish_to_keg = {}
for keg, dishes in updated_mapping.items():
    for dish in dishes:
        dish_to_keg[dish] = keg

with open('dish_to_keg_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(dish_to_keg, f, indent=2, ensure_ascii=False)

print(f"[SAVED] dish_to_keg_mapping.json")

# Также обновляем основной CSV файл
try:
    df_main = pd.read_csv('tochno prav spisok - active_dishes_to_kegs_CLEAN.csv.csv', encoding='utf-8-sig')

    # Добавляем новые строки
    new_rows = []
    for idx, row in df_filled.iterrows():
        new_rows.append({
            'DISH_NAME': row['DISH_NAME'],
            'KEG_NAME': row['KEG_NAME']
        })

    df_updated = pd.concat([df_main, pd.DataFrame(new_rows)], ignore_index=True)
    df_updated = df_updated.drop_duplicates(subset=['DISH_NAME'])
    df_updated = df_updated.sort_values('DISH_NAME')

    df_updated.to_csv('tochno prav spisok - active_dishes_to_kegs_CLEAN.csv.csv', index=False, encoding='utf-8-sig')
    print(f"[SAVED] tochno prav spisok - active_dishes_to_kegs_CLEAN.csv.csv (obnovlen)")

except Exception as e:
    print(f"[WARNING] Ne udalos obnovit osnovnoy CSV: {e}")

print("\n" + "="*80)
print("STATISTIKA:")
print("="*80)

total_dishes = sum(len(dishes) for dishes in updated_mapping.values())
print(f"\nVsego blyud v mappinge: {total_dishes}")
print(f"Vsego kegov: {len(updated_mapping)}")
print(f"Dobavleno novyh: {filled_count}")

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
print("\nMapping uspeshno obnovlen!")
print("Perezapustite server dlya primeneniya izmeneniy:")
print("  Ctrl+C (ostanovit)")
print("  python app.py (zapustit)")
