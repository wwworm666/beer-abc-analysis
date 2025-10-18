"""
Создание маппинга между названиями кег и блюд
Анализируем какие блюда соответствуют каким кегам
"""

from datetime import datetime
from olap_reports import OlapReports
import pandas as pd
import re

print("="*80)
print("SOZDANIE MAPPINGA KEG -> BLYUDA")
print("="*80)

# Список кег из Office (Лиговский, сентябрь 2025)
KEGS_FROM_OFFICE = [
    "КЕГ Brewlok IPA 20 л",
    "КЕГ Brewlok Stout",
    "КЕГ Brewlok Пилс 20 л",
    "КЕГ Rebel Apple Дикий Крест",
    "КЕГ Барбе Руби 30 л",
    "КЕГ Бланш де Намур, светлое",
    "КЕГ Блек Шип",
    "КЕГ Гулден Драк 708, 20 л",
    "КЕГ Карлова Корчма Премиум 30 л",
    "КЕГ Леруа Капиттель Блонд 30 л",
    "КЕГ Монкс Кафе 20 л",
    "КЕГ Нишко 30 л",
    "КЕГ ФестХаус Вайцен",
    "КЕГ ФестХаус Октобер",
    "КЕГ ФестХаус Хеллес",
]

# Получаем данные
olap = OlapReports()
if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

date_from = "2025-09-01"
date_to = "2025-09-30"
bar_name = "Лиговский"

report_data = olap.get_draft_sales_report(date_from, date_to, bar_name)
olap.disconnect()

if not report_data or not report_data.get('data'):
    print("[ERROR] Net dannykh")
    exit()

df = pd.DataFrame(report_data['data'])

# Извлекаем название пива без объёма
def extract_beer_name(dish_name):
    """Убираем объём из названия"""
    return re.sub(r'\s*\(.*\)', '', dish_name).strip()

df['BeerName'] = df['DishName'].apply(extract_beer_name)

# Получаем уникальные названия блюд
unique_beers = sorted(df['BeerName'].unique())

print(f"\n[INFO] Nayden {len(unique_beers)} unikalnykh piv v prodazhakh")
print(f"[INFO] V Office {len(KEGS_FROM_OFFICE)} keg\n")

# Создаём маппинг автоматически
def normalize_name(name):
    """Нормализуем название для сравнения"""
    # Убираем "КЕГ", объёмы, лишние пробелы
    normalized = name.upper()
    normalized = re.sub(r'КЕГ\s*', '', normalized)
    normalized = re.sub(r'\d+\s*[ЛL]', '', normalized)
    normalized = re.sub(r'[,\.]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

print("="*80)
print("AVTOMATICHESKIY MAPPING:")
print("="*80)

mapping = {}
unmatched_kegs = []
unmatched_beers = []

for keg in KEGS_FROM_OFFICE:
    keg_norm = normalize_name(keg)
    matched = False

    for beer in unique_beers:
        beer_norm = normalize_name(beer)

        # Проверяем совпадение
        if keg_norm == beer_norm or beer_norm in keg_norm or keg_norm in beer_norm:
            if keg not in mapping:
                mapping[keg] = []
            mapping[keg].append(beer)
            matched = True

    if not matched:
        unmatched_kegs.append(keg)

# Проверяем какие блюда не нашли соответствие
for beer in unique_beers:
    found = False
    for keg, beers in mapping.items():
        if beer in beers:
            found = True
            break
    if not found:
        unmatched_beers.append(beer)

# Показываем результат
print(f"\n{'TOVAR (KEGA)':<50s} {'BLYUDO (PRODAZHA)':<50s}")
print("="*100)

for keg, beers in sorted(mapping.items()):
    if beers:
        print(f"{keg:<50s} {beers[0]:<50s}")
        for beer in beers[1:]:
            print(f"{'':<50s} {beer:<50s}")
    else:
        print(f"{keg:<50s} {'[NE NAYDEN]':<50s}")

if unmatched_kegs:
    print("\n" + "="*80)
    print("KEGI BEZ SOOTVETSTVIYA:")
    print("="*80)
    for keg in unmatched_kegs:
        print(f"  - {keg}")
        # Пробуем найти похожие
        keg_norm = normalize_name(keg)
        similar = []
        for beer in unique_beers:
            beer_norm = normalize_name(beer)
            # Проверяем есть ли общие слова
            keg_words = set(keg_norm.split())
            beer_words = set(beer_norm.split())
            common = keg_words & beer_words
            if common and len(common) >= 1:
                similar.append(beer)

        if similar:
            print(f"    Vozmozhnye varianty:")
            for s in similar[:3]:
                print(f"      * {s}")

if unmatched_beers:
    print("\n" + "="*80)
    print("BLYUDA BEZ SOOTVETSTVIYA:")
    print("="*80)
    for beer in unmatched_beers:
        print(f"  - {beer}")

# Сохраняем маппинг в файл
print("\n" + "="*80)
print("SOKHRANENIE MAPPINGA:")
print("="*80)

# Создаём Python словарь для использования в коде
mapping_code = "KEG_TO_DISH_MAPPING = {\n"
for keg, beers in sorted(mapping.items()):
    if beers:
        mapping_code += f'    "{keg}": {beers},\n'

# Добавляем ручные маппинги для не найденных
mapping_code += "\n    # Ruchnye mappingi (proverit!):\n"
for keg in unmatched_kegs:
    mapping_code += f'    "{keg}": [],  # TODO: dobavit sootvetstvuyuschie blyuda\n'

mapping_code += "}\n"

with open("keg_mapping.py", "w", encoding="utf-8") as f:
    f.write(mapping_code)

print("[SAVED] keg_mapping.py")

print("\n" + "="*80)
print("PRIMER ISPOLZOVANIYA:")
print("="*80)
print("""
# Importirovat:
from keg_mapping import KEG_TO_DISH_MAPPING

# Najti blyuda dlya kegi:
keg_name = "KEG Blek Ship"
dishes = KEG_TO_DISH_MAPPING.get(keg_name, [])

# Filtrovaт dannye:
df_keg = df[df['BeerName'].isin(dishes)]
total = df_keg['VolumeByPortions'].sum()
""")

print("="*80)
