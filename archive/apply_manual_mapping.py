"""
Применяем ручной маппинг кегов к блюдам
После того как пользователь заполнил keg_mapping_MANUAL.py
"""

import json
from keg_mapping_MANUAL import KEG_TO_DISH_MANUAL_MAPPING

print("="*80)
print("PRIMENENIE RUCHNOGO MAPPINGA KEGOV K BLYUDAM")
print("="*80)

# Подсчитываем статистику
total_kegs = len(KEG_TO_DISH_MANUAL_MAPPING)
filled_kegs = sum(1 for dishes in KEG_TO_DISH_MANUAL_MAPPING.values() if len(dishes) > 0)
empty_kegs = total_kegs - filled_kegs

print(f"\nVsego kegov v mappinge: {total_kegs}")
print(f"Zapolneno: {filled_kegs} ({filled_kegs/total_kegs*100:.1f}%)")
print(f"Pustыh (ne zapolneno): {empty_kegs} ({empty_kegs/total_kegs*100:.1f}%)")

if empty_kegs > 0:
    print(f"\n[WARNING] Eshche est {empty_kegs} kegov bez privyazki!")
    print("Rekomenduyetsya zapolnit vse kegi pered primeneniem mappinga")

    # Показываем первые 10 незаполненных
    empty_list = [keg for keg, dishes in KEG_TO_DISH_MANUAL_MAPPING.items() if len(dishes) == 0]
    print("\nPrimery nezapolnennyh kegov:")
    for keg in empty_list[:10]:
        print(f"  - {keg}")

    response = input("\nProdolzhit v lyubom sluchae? (y/n): ")
    if response.lower() != 'y':
        print("Otmeneno. Zapolnite mapping i zapustite snova.")
        exit()

# Преобразуем в формат для использования в коде
# Формат: "Название кега": ['Блюдо 1', 'Блюдо 2']

print("\n" + "="*80)
print("SOHRANYAEM MAPPING V FAYLY")
print("="*80)

# 1. Сохраняем в keg_mapping.py (основной рабочий файл)
mapping_code = '''"""
МАППИНГ КЕГОВ К БЛЮДАМ
Автоматически сгенерировано из keg_mapping_MANUAL.py
НЕ РЕДАКТИРУЙТЕ ВРУЧНУЮ! Используйте keg_mapping_MANUAL.py
"""

KEG_TO_DISH_MAPPING = {
'''

for keg_name, dish_list in KEG_TO_DISH_MANUAL_MAPPING.items():
    if len(dish_list) > 0:
        dishes_str = ', '.join([f"'{d}'" for d in dish_list])
        mapping_code += f'    "{keg_name}": [{dishes_str}],\n'

mapping_code += '}\n'

with open('keg_mapping.py', 'w', encoding='utf-8') as f:
    f.write(mapping_code)

print("[SAVED] keg_mapping.py")

# 2. Также сохраняем в JSON для других целей
mapping_json = {}
for keg_name, dish_list in KEG_TO_DISH_MANUAL_MAPPING.items():
    if len(dish_list) > 0:
        mapping_json[keg_name] = dish_list

with open('keg_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(mapping_json, f, indent=2, ensure_ascii=False)

print("[SAVED] keg_mapping.json")

# 3. Создаем обратный маппинг (Блюдо -> Список кегов)
dish_to_kegs = {}
for keg_name, dish_list in KEG_TO_DISH_MANUAL_MAPPING.items():
    for dish in dish_list:
        if dish not in dish_to_kegs:
            dish_to_kegs[dish] = []
        dish_to_kegs[dish].append(keg_name)

with open('dish_to_keg_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(dish_to_kegs, f, indent=2, ensure_ascii=False)

print("[SAVED] dish_to_keg_mapping.json (obratnyy mapping)")

# 4. Статистика по блюдам
print("\n" + "="*80)
print("STATISTIKA PO BLYUDAM:")
print("="*80)

unique_dishes = set()
for dish_list in KEG_TO_DISH_MANUAL_MAPPING.values():
    unique_dishes.update(dish_list)

print(f"\nVsego unikalnyh blyud v mappinge: {len(unique_dishes)}")

# Показываем блюда с несколькими кегами
multi_keg_dishes = {dish: kegs for dish, kegs in dish_to_kegs.items() if len(kegs) > 1}
if multi_keg_dishes:
    print(f"\nBlyuda s neskolkimi kegami: {len(multi_keg_dishes)}")
    for dish, kegs in sorted(multi_keg_dishes.items())[:10]:
        print(f"\n{dish}:")
        for keg in kegs:
            print(f"  - {keg}")

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
print("\nMapping uspeshno primenyon!")
print("Teper mozhno ispolzovat keg_mapping.py v draft_analysis.py i waiter_analysis.py")
