"""
Умный автоматический маппинг кегов к блюдам
Учитывает латиницу, кириллицу, синонимы, объёмы
"""

import json
import pandas as pd
from datetime import datetime, timedelta
from olap_reports import OlapReports
import re

def clean_keg_name(keg_name):
    """Очищаем название кега для поиска"""
    # Убираем "КЕГ" в начале
    name = re.sub(r'^кег\s+', '', keg_name, flags=re.IGNORECASE)
    # Убираем объёмы (20 л, 30л, 30 л, etc)
    name = re.sub(r'\s*\d+\s*л\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\d+\s*l\s*$', '', name, flags=re.IGNORECASE)
    # Убираем лишние пробелы
    name = name.strip()
    return name

def clean_dish_name(dish_name):
    """Очищаем название блюда для поиска"""
    # Убираем порции (0.5), (0,5), etc
    name = re.sub(r'\s*\([0-9,\.]+\)\s*$', '', dish_name)
    name = name.strip()
    return name

def normalize_for_comparison(text):
    """Нормализуем текст для сравнения"""
    # Приводим к нижнему регистру
    text = text.lower()
    # Убираем все пробелы
    text = re.sub(r'\s+', '', text)
    # Убираем кавычки и спец символы
    text = re.sub(r'["\'\`\-]', '', text)
    return text

def find_best_match(keg_name, dish_list):
    """Находим лучшее совпадение блюда для кега"""
    keg_clean = clean_keg_name(keg_name)
    keg_normalized = normalize_for_comparison(keg_clean)

    matches = []

    for dish in dish_list:
        dish_clean = clean_dish_name(dish)
        dish_normalized = normalize_for_comparison(dish_clean)

        # Точное совпадение после нормализации
        if keg_normalized == dish_normalized:
            matches.append((dish_clean, 100))
            continue

        # Кег содержит блюдо
        if dish_normalized in keg_normalized:
            score = len(dish_normalized) / len(keg_normalized) * 90
            matches.append((dish_clean, score))
            continue

        # Блюдо содержит кег
        if keg_normalized in dish_normalized:
            score = len(keg_normalized) / len(dish_normalized) * 85
            matches.append((dish_clean, score))
            continue

        # Проверяем похожие слова (>50% общих символов)
        common = sum(1 for c in keg_normalized if c in dish_normalized)
        if common > 0:
            score = (common / max(len(keg_normalized), len(dish_normalized))) * 100
            if score > 50:
                matches.append((dish_clean, score))

    # Возвращаем лучшее совпадение
    if matches:
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0] if matches[0][1] > 60 else None

    return None

print("="*80)
print("UMNYY AVTOMATICHESKIY MAPPING KEGOV K BLYUDAM")
print("="*80)

# 1. Загружаем кеги
with open('kegs_products.json', 'r', encoding='utf-8') as f:
    all_kegs = json.load(f)

print(f"\nVsego kegov: {len(all_kegs)}")

# 2. Получаем список блюд
olap = OlapReports()
if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

date_to = datetime.now().strftime('%Y-%m-%d')
date_from = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

print(f"Poluchaem dannye za period: {date_from} - {date_to}")

report_data = olap.get_draft_sales_report(date_from, date_to)
olap.disconnect()

if not report_data:
    print("[ERROR] Net dannyh")
    exit()

df = pd.DataFrame(report_data['data'])
unique_dishes = df['DishName'].unique()
unique_dishes_clean = list(set([clean_dish_name(d) for d in unique_dishes]))

print(f"Unikalnyh blyud: {len(unique_dishes_clean)}")

# 3. Умный маппинг
mapping = {}
success_count = 0
fail_count = 0

print("\n" + "="*80)
print("AVTOMATICHESKIY MAPPING:")
print("="*80)

for keg in all_kegs:
    keg_name = keg['name']
    best_match = find_best_match(keg_name, unique_dishes_clean)

    if best_match:
        mapping[keg_name] = [best_match]
        success_count += 1
        print(f"[OK] {keg_name} -> {best_match}")
    else:
        mapping[keg_name] = []
        fail_count += 1
        print(f"[--] {keg_name} -> [NET SOVPADENIYA]")

# 4. Статистика
print("\n" + "="*80)
print("STATISTIKA:")
print("="*80)

print(f"\nUspeshno: {success_count} ({success_count/len(all_kegs)*100:.1f}%)")
print(f"Bez sovpadeniy: {fail_count} ({fail_count/len(all_kegs)*100:.1f}%)")

# 5. Сохраняем результат
output = {
    'mapping': mapping,
    'stats': {
        'total_kegs': len(all_kegs),
        'matched': success_count,
        'unmatched': fail_count,
        'match_rate': f"{success_count/len(all_kegs)*100:.1f}%"
    }
}

with open('smart_keg_mapping.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n[SAVED] smart_keg_mapping.json")

# 6. Создаём Python файл
py_content = '''"""
АВТОМАТИЧЕСКИЙ МАППИНГ КЕГОВ К БЛЮДАМ
Сгенерировано smart_keg_mapping.py
"""

KEG_TO_DISH_MAPPING = {
'''

for keg_name, dishes in mapping.items():
    if dishes:
        dishes_str = ', '.join([f"'{d}'" for d in dishes])
        py_content += f'    "{keg_name}": [{dishes_str}],\n'

py_content += '}\n'

with open('keg_mapping.py', 'w', encoding='utf-8') as f:
    f.write(py_content)

print(f"[SAVED] keg_mapping.py")

# 7. Показываем примеры неудач для ручной проверки
print("\n" + "="*80)
print("KEGI BEZ SOVPADENIY (nuzhna ruchnaya proverka):")
print("="*80)

failed_kegs = [k for k, v in mapping.items() if not v]
for keg in failed_kegs[:20]:
    print(f"  {keg}")
    # Пробуем показать похожие блюда
    keg_norm = normalize_for_comparison(clean_keg_name(keg))
    similar = []
    for dish in unique_dishes_clean:
        dish_norm = normalize_for_comparison(dish)
        common = sum(1 for c in keg_norm if c in dish_norm)
        if common > 3:
            score = common / max(len(keg_norm), len(dish_norm)) * 100
            if score > 30:
                similar.append((dish, score))

    if similar:
        similar.sort(key=lambda x: x[1], reverse=True)
        print(f"    Pohozhie: {similar[0][0]} ({similar[0][1]:.0f}%)")

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
