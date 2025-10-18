"""
Создаем шаблон для ручного заполнения маппинга кегов к блюдам
"""

import pandas as pd

# Читаем CSV
df = pd.read_csv('keg_to_dish_mapping_CHECK.csv')

# Получаем список всех уникальных блюд
with open('keg_to_dish_mapping_CHECK.csv', 'r', encoding='utf-8-sig') as f:
    content = f.read()

# Собираем все блюда из MATCHED_DISHES
all_dishes = set()
for idx, row in df.iterrows():
    dishes_str = row['MATCHED_DISHES']
    if dishes_str != '[НЕТ СОВПАДЕНИЙ]':
        dishes = [d.strip() for d in dishes_str.split(',')]
        all_dishes.update(dishes)

print("="*80)
print("SOZDAEM SHABLON DLya RUCHNOGO ZAPOLNENIYA MAPPINGA")
print("="*80)

print(f"\nVsego kegov: {len(df)}")
print(f"Vsego unikalnyh blyud: {len(all_dishes)}")

# Создаем Python файл с шаблоном для заполнения
template_content = '''"""
РУЧНОЙ МАППИНГ КЕГОВ К БЛЮДАМ
Заполните этот файл правильными привязками

ИНСТРУКЦИЯ:
1. Для каждого кега укажите список названий блюд (без порций!)
2. Названия блюд должны совпадать с тем, как они называются в меню
3. Если кег не продается - оставьте пустой список []
4. После заполнения запустите скрипт apply_manual_mapping.py
"""

# Список всех доступных блюд для справки:
AVAILABLE_DISHES = [
'''

for dish in sorted(all_dishes):
    template_content += f'    "{dish}",\n'

template_content += ''']\n\n# МАППИНГ КЕГОВ К БЛЮДАМ\n# Формат: "Название кега": ["Блюдо 1", "Блюдо 2", ...]\n\nKEG_TO_DISH_MANUAL_MAPPING = {\n'''

# Добавляем кеги с автоматическим маппингом (для проверки)
print("\n[1] Dobavlyaem kegi s avtomaticheskim mappingom (dlya proverki)...")

df_with_match = df[df['STATUS'] == 'OK'].sort_values('KEG_NAME')
for idx, row in df_with_match.iterrows():
    keg_name = row['KEG_NAME']
    dishes = row['MATCHED_DISHES']

    if ',' in dishes:
        # Несколько блюд
        dishes_list = [f'"{d.strip()}"' for d in dishes.split(',')]
        template_content += f'    "{keg_name}": [{", ".join(dishes_list)}],  # ПРОВЕРИТЬ: несколько привязок\n'
    else:
        template_content += f'    "{keg_name}": ["{dishes}"],\n'

# Добавляем кеги БЕЗ маппинга (нужно заполнить вручную)
print("[2] Dobavlyaem kegi BEZ mappinga (nuzhno zapolnit vruchnuyu)...")

template_content += '\n    # ======================================================================\n'
template_content += '    # КЕГИ БЕЗ АВТОМАТИЧЕСКОЙ ПРИВЯЗКИ - ЗАПОЛНИТЕ ВРУЧНУЮ!\n'
template_content += '    # ======================================================================\n\n'

df_no_match = df[df['STATUS'] == 'НЕТ ПРИВЯЗКИ'].sort_values('KEG_NAME')
for idx, row in df_no_match.iterrows():
    keg_name = row['KEG_NAME']
    template_content += f'    "{keg_name}": [],  # TODO: указать название блюда\n'

template_content += '}\n'

# Сохраняем
filename = 'keg_mapping_MANUAL.py'
with open(filename, 'w', encoding='utf-8') as f:
    f.write(template_content)

print(f"\n[SAVED] {filename}")

print("\n" + "="*80)
print("STATISTIKA:")
print("="*80)

print(f"\nKegov s avtomappingom: {len(df_with_match)}")
print(f"Kegov bez mappinga (zapolnit): {len(df_no_match)}")

print("\n" + "="*80)
print("CHTO DELAT DALSHE:")
print("="*80)

print(f"""
1. Otkroyte fayl: {filename}
2. Nayдите sekciyu s komentariem "TODO: ukazat nazvanie blyuda"
3. Dlya kazhdogo kega ukazhite pravilnoe nazvanie blyuda iz spiska AVAILABLE_DISHES
4. Prover'te kegi s komentariem "PROVERIT: neskolko privyazok"
5. Sohranite fayl
6. Zapustite: python apply_manual_mapping.py
""")
