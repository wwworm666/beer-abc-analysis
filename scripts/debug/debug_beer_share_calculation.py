#!/usr/bin/env python3
"""
Скрипт диагностики: Почему BeerSharePercent не совпадает с фактическими процентами?

Проверяет:
1. Как рассчитывается BeerSharePercent
2. Какие данные используются для расчёта
3. Где может быть ошибка в логике
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

print("=" * 80)
print("ДИАГНОСТИКА: Расчёт BeerSharePercent")
print("=" * 80)

# Создаём тестовые данные, похожие на реальные
test_data = {
    'BeerName': ['Brewlok IPA', 'ФестХаус Хеллес', 'Блек Шип', 'Коникс Черри', 'Нектар Лагер'],
    'TotalLiters': [75.0, 120.0, 45.0, 30.0, 25.0],
    'TotalPortions': [150, 240, 90, 60, 50],
    'Bar': ['Большой пр. В.О', 'Большой пр. В.О', 'Большой пр. В.О', 'Лиговский', 'Лиговский'],
    'WeeksActive': [4, 4, 4, 3, 3],
}

df = pd.DataFrame(test_data)

print("\n" + "=" * 80)
print("1. ТЕСТОВЫЕ ДАННЫЕ")
print("=" * 80)
print(df.to_string())

print("\n" + "=" * 80)
print("2. БАЗОВЫЙ РАСЧЁТ (текущая логика)")
print("=" * 80)

# Текущая логика из draft_analysis.py (get_beer_summary)
total_liters = df['TotalLiters'].sum()
df['BeerSharePercent_V1'] = (df['TotalLiters'] / total_liters * 100)

print(f"\nОбщий объём всех пив: {total_liters} L")
print(f"\nРасчёт: BeerSharePercent = (TotalLiters / {total_liters}) * 100")
print(f"\n{df[['BeerName', 'TotalLiters', 'BeerSharePercent_V1']].to_string()}")

print(f"\nСумма BeerSharePercent: {df['BeerSharePercent_V1'].sum():.2f}%")

print("\n" + "=" * 80)
print("3. ПОТЕНЦИАЛЬНЫЕ ПРОБЛЕМЫ")
print("=" * 80)

print("\n❓ ПРОБЛЕМА 1: Рассчитывается ли для каждого бара отдельно?")
print("-" * 80)

# Вариант 2: Для каждого бара отдельно
df['BeerSharePercent_V2_ByBar'] = 0.0

for bar in df['Bar'].unique():
    bar_data = df[df['Bar'] == bar]
    bar_total = bar_data['TotalLiters'].sum()
    df.loc[df['Bar'] == bar, 'BeerSharePercent_V2_ByBar'] = \
        (df.loc[df['Bar'] == bar, 'TotalLiters'] / bar_total * 100)

print(f"Если рассчитывать для каждого бара отдельно:")
print(df[['BeerName', 'Bar', 'TotalLiters', 'BeerSharePercent_V2_ByBar']].to_string())
print(f"Сумма процентов: {df.groupby('Bar')['BeerSharePercent_V2_ByBar'].sum().to_dict()}")

print("\n❓ ПРОБЛЕМА 2: Учитываются ли фильтры при расчёте?")
print("-" * 80)

# Может быть, в логике есть фильтр на определённый период или бар
print("Возможные фильтры:")
print("  • Выбранный период (дата от/до)")
print("  • Выбранный бар (или все бары)")
print("  • Минимальный объём пива")
print("  • Исключённые категории пива")

print("\n❓ ПРОБЛЕМА 3: Может ли быть ошибка в source data из OLAP?")
print("-" * 80)

# Пример: может быть, OLAP возвращает дублирующиеся записи
test_duplicates = {
    'BeerName': ['Brewlok IPA', 'Brewlok IPA', 'ФестХаус Хеллес'],
    'TotalLiters': [50.0, 25.0, 100.0],  # Один пиво два раза!
}

df_dupes = pd.DataFrame(test_duplicates)
print("\nПример с дубликатами в source data:")
print(df_dupes.to_string())

# Если просто сгруппировать
df_grouped = df_dupes.groupby('BeerName').agg({'TotalLiters': 'sum'}).reset_index()
print("\nПосле группировки (правильно):")
print(df_grouped.to_string())

total = df_grouped['TotalLiters'].sum()
df_grouped['Share'] = (df_grouped['TotalLiters'] / total * 100)
print(f"\nОбщий объём: {total} L")
print(df_grouped[['BeerName', 'TotalLiters', 'Share']].to_string())

print("\n❓ ПРОБЛЕМА 4: Разница на 30% — что это может быть?")
print("-" * 80)

print("""
Если разница ровно на 30%, это может быть:

1. ❌ ФИЛЬТРАЦИЯ ПО ДАТЕ
   └─ Выбран период: 01.09.2025 — 30.09.2025 (только сентябрь)
   └─ Но фактические данные включают и август (или октябрь)
   └─ Разница: разный период = разные пиво = разные проценты

2. ❌ ФИЛЬТРАЦИЯ ПО БАРУ
   └─ Выбран 1 бар для отчёта
   └─ Но мэппинг или данные включают все бары
   └─ Разница: агрегация по разным наборам баров

3. ❌ ДУБЛИРУЮЩИЕСЯ ЗАПИСИ В OLAP
   └─ Одна продажа записана дважды в базе
   └─ При расчёте объём удваивается
   └─ Проценты смещаются на ~50% (или другой множитель)

4. ❌ НЕПРАВИЛЬНАЯ ГРУППИРОВКА
   └─ Группировка не по BeerName
   └─ Или включены вспомогательные пива (напр., с префиксом)
   └─ Пиво считается несколько раз

5. ❌ ФИЛЬТР НА МИНИМАЛЬНЫЙ ОБЪЁМ
   └─ Исключены пива с объёмом < X литров
   └─ Это меняет denominator (сумму)
   └─ Все проценты становятся больше

6. ❌ НЕПРАВИЛЬНЫЙ РАСЧЁТ ПЕРИОДА
   └─ Дата от/до интерпретируется неправильно
   └─ Включаются/исключаются неправильные дни
   └─ Разный набор данных = разные проценты
""")

print("\n" + "=" * 80)
print("4. ЧТО ПРОВЕРИТЬ В КОДЕ")
print("=" * 80)

checks = """
1. В функции get_beer_summary():
   □ Линия, где рассчитывается BeerSharePercent
   □ Какие данные используются для total_liters?
   □ Применяется ли фильтр по бару или дате?

2. В функции /api/draft-analyze:
   □ Какой период используется (date_from, date_to)?
   □ Какой бар выбран (bar_name)?
   □ Есть ли дополнительные фильтры на данные?

3. В OLAP запросе:
   □ Какие колонки возвращаются?
   □ Есть ли дубликаты в результатах?
   □ Фильтруются ли данные по категориям?

4. В frontend коде (JavaScript):
   □ Какой период отправляется на backend?
   □ Какой бар отправляется на backend?
   □ Совпадают ли отправленные параметры с фактическим расчётом?
"""

print(checks)

print("\n" + "=" * 80)
print("5. КОМАНДЫ ДЛЯ ПРОВЕРКИ")
print("=" * 80)

print("""
# 1. Проверить, что возвращает OLAP за конкретный период
python3 -c "
from core.olap_reports import OlapReports
olap = OlapReports()
olap.connect()
data = olap.get_draft_sales_report('2025-09-01', '2025-09-30', None)
print(f'Количество записей: {len(data[\"data\"])}')
print(f'Уникальные блюда: {len(set([d[\"DishName\"] for d in data[\"data\"]]))}')
print(f'Сумма всех объёмов: {sum([float(d[\"DishAmountInt\"])*0.5 for d in data[\"data\"]])}L')
olap.disconnect()
"

# 2. Запустить анализ вручную и сравнить
python3 -c "
import pandas as pd
from core.draft_analysis import DraftAnalysis
from core.olap_reports import OlapReports

olap = OlapReports()
olap.connect()
data = olap.get_draft_sales_report('2025-09-01', '2025-09-30', None)
olap.disconnect()

df = pd.DataFrame(data['data'])
analyzer = DraftAnalysis(df)
summary = analyzer.get_beer_summary()

print('\\nТоп 10 пив:')
print(summary[['BeerName', 'TotalLiters', 'BeerSharePercent']].head(10).to_string())
print(f'\\nОбщий объём: {summary[\"TotalLiters\"].sum()} L')
print(f'Сумма процентов: {summary[\"BeerSharePercent\"].sum():.2f}%')
"

# 3. Проверить логику фильтрации в frontend
# Открыть Developer Tools (F12) в браузере
// Выполнить в Console:
fetch('/api/draft-analyze', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({bar: null, days: 30, date_from: '2025-09-01', date_to: '2025-09-30'})
})
.then(r => r.json())
.then(data => {
  let total = 0;
  for (let beer of data[Object.keys(data)[0]].beers) {
    console.log(`${beer.BeerName}: ${beer.TotalLiters}L = ${beer.BeerSharePercent.toFixed(2)}%`);
    total += beer.BeerSharePercent;
  }
  console.log(`Сумма процентов: ${total.toFixed(2)}%`);
});
""")

print("\n" + "=" * 80)
print("ДИАГНОСТИКА ЗАВЕРШЕНА")
print("=" * 80)
print("\nПроверьте каждый пункт выше и найдите, где происходит фильтрация!")
