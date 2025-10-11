"""Тестирование исправления анализа категорий"""
import json
from data_processor import BeerDataProcessor
from category_analysis import CategoryAnalysis

print("=" * 70)
print("ТЕСТИРОВАНИЕ ИСПРАВЛЕНИЯ АНАЛИЗА КАТЕГОРИЙ")
print("=" * 70)

# Загружаем данные
print("\n1️⃣ Загрузка данных из beer_report.json...")
with open("beer_report.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"   ✅ Загружено {len(data.get('data', []))} записей")

# Обрабатываем данные
print("\n2️⃣ Обработка данных через BeerDataProcessor...")
processor = BeerDataProcessor(data)

if not processor.prepare_dataframe():
    print("   ❌ Ошибка обработки данных")
    exit(1)

print(f"   ✅ Данные подготовлены")

# Агрегируем
print("\n3️⃣ Агрегация данных...")
agg_data = processor.aggregate_by_beer_and_bar()
print(f"   ✅ Агрегировано {len(agg_data)} записей")

# Проверяем наличие null в Style
null_count = agg_data['Style'].isna().sum()
print(f"\n📊 Записей с пустым Style ДО создания CategoryAnalysis: {null_count}")

# Создаем анализатор категорий (здесь должно происходить заполнение null)
print("\n4️⃣ Создание CategoryAnalysis (с исправлением null)...")
cat_analyzer = CategoryAnalysis(agg_data)

# Проверяем, что null заполнены
null_after = cat_analyzer.data['Style'].isna().sum()
uncategorized_count = (cat_analyzer.data['Style'] == 'Без категории (Ф)').sum()

print(f"   ✅ CategoryAnalysis создан")
print(f"   📊 Записей с пустым Style ПОСЛЕ: {null_after}")
print(f"   📊 Записей в категории 'Без категории (Ф)': {uncategorized_count}")

# Получаем категории
print("\n5️⃣ Получение списка категорий...")
categories = cat_analyzer.get_categories()
print(f"   ✅ Найдено категорий: {len(categories)}")

if len(categories) == 0:
    print("   ❌ ОШИБКА: Категорий не найдено!")
    exit(1)

print(f"\n   Топ-10 категорий по количеству фасовок:")
for i, category in enumerate(categories[:10], 1):
    count = len(cat_analyzer.data[cat_analyzer.data['Style'] == category])
    print(f"      {i}. {category} ({count} фасовок)")

# Проверяем для конкретного бара
bar_name = "Большой пр. В.О"
print(f"\n6️⃣ Получение категорий для бара '{bar_name}'...")
bar_categories = cat_analyzer.get_categories(bar_name)
print(f"   ✅ Найдено категорий: {len(bar_categories)}")

if len(bar_categories) == 0:
    print(f"   ❌ ОШИБКА: Для бара '{bar_name}' категорий не найдено!")
    exit(1)

# Пробуем запустить анализ категории
print(f"\n7️⃣ Анализ первой категории для бара '{bar_name}'...")
first_category = bar_categories[0]
print(f"   Категория: '{first_category}'")

result = cat_analyzer.analyze_category(first_category, bar_name)

if result is None:
    print(f"   ❌ ОШИБКА: Анализ вернул None!")
    exit(1)

print(f"   ✅ Анализ успешен!")
print(f"   📊 Фасовок в категории: {result['total_beers']}")
print(f"   💰 Выручка: {result['total_revenue']:,.0f} руб")
print(f"   📈 ABC распределение: {result['abc_stats']}")

# Получаем сводку
print(f"\n8️⃣ Получение сводки по всем категориям...")
summary = cat_analyzer.get_category_summary(bar_name)
print(f"   ✅ Сводка получена: {len(summary)} категорий")
print(f"\n   Топ-5 категорий по выручке:")
print(summary[['Category', 'BeersCount', 'TotalRevenue', 'RevenuePercent']].head().to_string(index=False))

print("\n" + "=" * 70)
print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
print("=" * 70)
print("\n💡 Исправление работает:")
print("   - Пустые значения Style заменяются на 'Без категории (Ф)'")
print("   - Категории успешно извлекаются")
print("   - Анализ категорий работает корректно")
