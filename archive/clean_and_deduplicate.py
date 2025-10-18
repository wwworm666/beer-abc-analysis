"""
Убираем дубликаты блюд (с порциями и префиксами НЗ)
Оставляем только основные названия
"""

import pandas as pd
import re

print("="*80)
print("OCHISTKA I DEDUPLIKATSIYA BLYUD")
print("="*80)

# Загружаем текущий маппинг
df = pd.read_csv('active_dishes_to_kegs_2025.csv', encoding='utf-8-sig')

print(f"\nIshodnyh zapisey: {len(df)}")

# Функция для определения базового названия
def get_base_dish_name(dish_name):
    """Получаем базовое название блюда без порций и префиксов"""
    name = dish_name

    # Убираем префикс "НЗ " (Невский завод?)
    name = re.sub(r'^НЗ\s+', '', name, flags=re.IGNORECASE)

    # Убираем порции и маркировки в конце
    # (0,5), (0,5)(П), (1,0) (П), (0,5) - В ЗАЛАХ, etc
    name = re.sub(r'\s*\([0-9,\.]+\).*$', '', name)

    # Убираем лишние пробелы
    name = ' '.join(name.split())

    return name.strip()

# Добавляем колонку с базовым названием
df['BASE_NAME'] = df['DISH_NAME'].apply(get_base_dish_name)

# Группируем по базовому названию
# Оставляем запись где уже есть маппинг, или первую если маппинга нет
def select_best_row(group):
    """Выбираем лучшую запись из группы дубликатов"""
    # Если есть запись с маппингом - берём её
    with_mapping = group[group['KEG_NAME'].notna() & (group['KEG_NAME'] != '')]
    if len(with_mapping) > 0:
        return with_mapping.iloc[0]
    # Иначе берём первую
    return group.iloc[0]

# Группируем и выбираем
df_clean = df.groupby('BASE_NAME', as_index=False).apply(select_best_row)
df_clean = df_clean.reset_index(drop=True)

# Используем BASE_NAME как DISH_NAME
df_final = df_clean[['BASE_NAME', 'KEG_NAME', 'NOTES', 'STATUS']].copy()
df_final.columns = ['DISH_NAME', 'KEG_NAME', 'NOTES', 'STATUS']

print(f"Posle ochistki: {len(df_final)}")
print(f"Udaleno duplikatov: {len(df) - len(df_final)}")

# Статистика
filled = len(df_final[df_final['STATUS'] == 'OK'])
unfilled = len(df_final[df_final['STATUS'] == 'ZAPOLNIT'])

print(f"\nZamapleno: {filled} ({filled/len(df_final)*100:.1f}%)")
print(f"Pustыh: {unfilled} ({unfilled/len(df_final)*100:.1f}%)")

# Сохраняем
output_file = 'active_dishes_to_kegs_CLEAN.csv'
df_final.to_csv(output_file, index=False, encoding='utf-8-sig')

print(f"\n[SAVED] {output_file}")

# Показываем незаполненные
if unfilled > 0:
    print("\n" + "="*80)
    print(f"BLYUDA BEZ MAPPINGA ({unfilled} sht):")
    print("="*80)

    empty_dishes = df_final[df_final['STATUS'] == 'ZAPOLNIT']['DISH_NAME'].tolist()
    for i, dish in enumerate(empty_dishes, 1):
        print(f"{i:3}. {dish}")

print("\n" + "="*80)
print("Otkroyte: " + output_file)
print("Zapolnite pustye v stolbce KEG_NAME")
print("Zapustite: python import_active_kegs_mapping.py")
print("="*80)
