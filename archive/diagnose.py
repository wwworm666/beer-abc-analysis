"""Диагностика проблемы с категориями пива"""
import json
import pandas as pd

print("=" * 60)
print("ДИАГНОСТИКА ДАННЫХ ДЛЯ АНАЛИЗА КАТЕГОРИЙ")
print("=" * 60)

# Загружаем данные
with open("beer_report.json", "r", encoding="utf-8") as f:
    data = json.load(f)

raw_data = data.get('data', [])
print(f"\n✅ Загружено {len(raw_data)} записей из beer_report.json")

# Подсчитываем записи с null/пустым DishGroup.ThirdParent
nulls = sum(1 for item in raw_data if item.get('DishGroup.ThirdParent') is None)
with_style = len(raw_data) - nulls

print(f"\n📊 Статистика по полю 'DishGroup.ThirdParent' (Style):")
print(f"   С заполненным Style: {with_style} ({with_style/len(raw_data)*100:.1f}%)")
print(f"   С пустым Style:      {nulls} ({nulls/len(raw_data)*100:.1f}%)")

# Создаем DataFrame
df = pd.DataFrame(raw_data)

# Смотрим уникальные стили (не пустые)
styles = df['DishGroup.ThirdParent'].dropna().unique()
print(f"\n🍺 Найдено уникальных стилей: {len(styles)}")
print("\nПервые 10 стилей:")
for i, style in enumerate(styles[:10], 1):
    count = len(df[df['DishGroup.ThirdParent'] == style])
    print(f"   {i}. {style} ({count} записей)")

# Проверяем, что произойдет при фильтрации по бару
bar_name = "Большой пр. В.О"
bar_data = df[df['Store.Name'] == bar_name]
print(f"\n🏪 Данные для бара '{bar_name}':")
print(f"   Всего записей: {len(bar_data)}")

bar_styles = bar_data['DishGroup.ThirdParent'].dropna().unique()
print(f"   Уникальных стилей: {len(bar_styles)}")

bar_nulls = len(bar_data[bar_data['DishGroup.ThirdParent'].isna()])
print(f"   С пустым Style: {bar_nulls} ({bar_nulls/len(bar_data)*100:.1f}%)")

# Пробуем агрегировать как в data_processor.py
print(f"\n🔄 Тест агрегации данных...")
agg_data = df.groupby(['Store.Name', 'DishName', 'DishGroup.ThirdParent', 'DishForeignName']).agg({
    'DishAmountInt': 'sum',
    'DishDiscountSumInt': 'sum',
    'ProductCostBase.ProductCost': 'sum',
    'ProductCostBase.MarkUp': 'mean',
}).reset_index()

agg_data.columns = ['Bar', 'Beer', 'Style', 'Country', 'TotalQty', 'TotalRevenue', 'TotalCost', 'AvgMarkupPercent']

print(f"   Агрегировано записей: {len(agg_data)}")
print(f"   Записей с пустым Style: {len(agg_data[agg_data['Style'].isna()])}")

# Теперь проверяем что происходит в CategoryAnalysis
print(f"\n🧪 Тест CategoryAnalysis.get_categories()...")
categories = agg_data['Style'].dropna().unique().tolist()
print(f"   Категорий найдено: {len(categories)}")

if len(categories) > 0:
    print(f"\n✅ ДАННЫЕ ЕСТЬ! Категории успешно извлекаются.")
    print(f"\nПервые 5 категорий:")
    for i, cat in enumerate(categories[:5], 1):
        cat_data = agg_data[agg_data['Style'] == cat]
        print(f"   {i}. {cat} ({len(cat_data)} фасовок)")
else:
    print(f"\n❌ ПРОБЛЕМА! Категорий не найдено после dropna()")

# Проверяем для конкретного бара
bar_agg = agg_data[agg_data['Bar'] == bar_name]
bar_categories = bar_agg['Style'].dropna().unique().tolist()
print(f"\n🏪 Категории для бара '{bar_name}': {len(bar_categories)}")

if len(bar_categories) == 0:
    print(f"   ❌ ПРОБЛЕМА! Для бара '{bar_name}' категорий не найдено!")
    print(f"   Всего фасовок в баре: {len(bar_agg)}")
    print(f"   С пустым Style: {len(bar_agg[bar_agg['Style'].isna()])}")
else:
    print(f"   ✅ Найдено категорий: {len(bar_categories)}")

print("\n" + "=" * 60)
print("ДИАГНОСТИКА ЗАВЕРШЕНА")
print("=" * 60)
