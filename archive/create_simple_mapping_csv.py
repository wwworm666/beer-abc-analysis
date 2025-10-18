"""
Создаём простой CSV для ручного маппинга
Формат: KEG_NAME | DISH_NAME | STATUS
"""

import json
import pandas as pd

# Загружаем кеги
with open('kegs_products.json', 'r', encoding='utf-8') as f:
    all_kegs = json.load(f)

# Загружаем текущий маппинг
with open('smart_keg_mapping.json', 'r', encoding='utf-8') as f:
    smart_mapping = json.load(f)

# Создаём таблицу для ручного заполнения
rows = []

for keg in all_kegs:
    keg_name = keg['name']
    current_mapping = smart_mapping['mapping'].get(keg_name, [])

    if current_mapping:
        dish_name = current_mapping[0]
        status = 'ПРОВЕРИТЬ'  # Нужно проверить автоматический маппинг
    else:
        dish_name = ''
        status = 'ЗАПОЛНИТЬ'  # Нужно заполнить вручную

    rows.append({
        'KEG_NAME': keg_name,
        'DISH_NAME': dish_name,
        'STATUS': status
    })

df = pd.DataFrame(rows)

# Сортируем: сначала незаполненные, потом на проверку
df = df.sort_values(['STATUS', 'KEG_NAME'], ascending=[False, True])

# Сохраняем в CSV
csv_file = 'keg_dish_mapping_EDIT.csv'
df.to_csv(csv_file, index=False, encoding='utf-8-sig')

print("="*80)
print("SOZDANIE CSV DLya RUCHNOGO MAPPINGA")
print("="*80)

print(f"\n[SAVED] {csv_file}")
print(f"\nVsego kegov: {len(df)}")
print(f"Nuzhno zapolnit: {len(df[df['STATUS'] == 'ЗАПОЛНИТЬ'])}")
print(f"Nuzhno proverit: {len(df[df['STATUS'] == 'ПРОВЕРИТЬ'])}")

print("\n" + "="*80)
print("INSTRUKTSIYA:")
print("="*80)

print(f"""
1. Otkroyte fayl: {csv_file}
2. V stolbce DISH_NAME ukazhite pravilnoe nazvanie blyuda (BEZ porcii!)
3. Primery pravilnyh nazvaniy:
   - "Brewlok IPA" (ne "Brewlok IPA (0.5)")
   - "���� ���" (ne "���� ��� (1.0)")
4. Dlya kegov kotorye NE prodayutsya - postavte "НЕ ПРОДАЕТСЯ"
5. Sohranite CSV
6. Zapustite: python import_csv_mapping.py
""")
