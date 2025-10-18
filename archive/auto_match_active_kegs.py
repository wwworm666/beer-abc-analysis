"""
Автоматический маппинг активных блюд к кегам с точным совпадением
"""

import pandas as pd
import re

print("="*80)
print("AVTOMATICHESKIY MAPPING AKTIVNYH BLYUD K KEGAM")
print("="*80)

# Загружаем блюда и кеги
df_dishes = pd.read_csv('active_dishes_to_kegs_2025.csv', encoding='utf-8-sig')
df_kegs = pd.read_csv('all_kegs_reference.csv', encoding='utf-8-sig')

dishes = df_dishes['DISH_NAME'].tolist()
kegs = df_kegs['KEG_NAME'].tolist()

print(f"\nBlyud: {len(dishes)}")
print(f"Kegov: {len(kegs)}")

def normalize_text(text):
    """Нормализация текста для сравнения"""
    # Нижний регистр
    text = text.lower()
    # Убираем лишние пробелы
    text = ' '.join(text.split())
    # Убираем кавычки
    text = text.replace('"', '').replace("'", '').replace('`', '')
    return text

def find_exact_keg(dish_name, keg_list):
    """Находим точное совпадение кега для блюда"""
    dish_norm = normalize_text(dish_name)

    for keg in keg_list:
        # Убираем "КЕГ" из начала
        keg_without_prefix = re.sub(r'^кег\s+', '', keg, flags=re.IGNORECASE).strip()
        # Убираем объём в конце (20 л, 30л, etc)
        keg_without_volume = re.sub(r'\s*\d+\s*л\s*$', '', keg_without_prefix, flags=re.IGNORECASE).strip()

        keg_norm = normalize_text(keg_without_volume)

        # Точное совпадение
        if dish_norm == keg_norm:
            return keg

        # Блюдо содержится в кеге (например "Brewlok IPA" в "КЕГ Brewlok IPA 20 л")
        if dish_norm in keg_norm and len(dish_norm) > 5:
            # Проверяем что это не случайное вхождение
            # Разница не должна быть больше 10 символов
            if len(keg_norm) - len(dish_norm) < 10:
                return keg

    return None

# Автоматический маппинг
matched = 0
unmatched = 0

mapping = []

for dish in dishes:
    keg = find_exact_keg(dish, kegs)

    if keg:
        matched += 1
        mapping.append({
            'DISH_NAME': dish,
            'KEG_NAME': keg,
            'NOTES': 'AUTO',
            'STATUS': 'OK'
        })
        print(f"[OK] {dish} -> {keg}")
    else:
        unmatched += 1
        mapping.append({
            'DISH_NAME': dish,
            'KEG_NAME': '',
            'NOTES': '',
            'STATUS': 'ZAPOLNIT'
        })
        print(f"[--] {dish} -> [NE NAYDENO]")

# Сохраняем результат
df_result = pd.DataFrame(mapping)
df_result.to_csv('active_dishes_to_kegs_2025.csv', index=False, encoding='utf-8-sig')

print("\n" + "="*80)
print("STATISTIKA:")
print("="*80)

print(f"\nAvtomaticheski: {matched} ({matched/len(dishes)*100:.1f}%)")
print(f"Nuzhno zapolnit: {unmatched} ({unmatched/len(dishes)*100:.1f}%)")

print(f"\n[SAVED] active_dishes_to_kegs_2025.csv")

# Показываем незаполненные
if unmatched > 0:
    print("\n" + "="*80)
    print("BLYUDA BEZ MAPPINGA (nuzhno zapolnit vruchnuyu):")
    print("="*80)

    unmatched_dishes = df_result[df_result['STATUS'] == 'ZAPOLNIT']['DISH_NAME'].tolist()
    for dish in unmatched_dishes[:30]:
        print(f"  {dish}")

    if len(unmatched_dishes) > 30:
        print(f"  ... i eshche {len(unmatched_dishes) - 30}")

print("\n" + "="*80)
print("Otkroyte active_dishes_to_kegs_2025.csv")
print("Prover'te avtomaticheskiy mapping i zapolnite pustye")
print("Potom zapustite: python import_active_kegs_mapping.py")
print("="*80)
