"""
Диагностический скрипт для отладки расхождения по ФестХаус Хеллес
"""

from datetime import datetime, timedelta
from core.olap_reports import OlapReports
from core.draft_analysis import DraftAnalysis
import pandas as pd

# Параметры
BAR = "Кременчугская"
DATE_FROM = "2024-09-01"
DATE_TO = "2024-09-30"
BEER_TO_CHECK = "фестхаус хеллес"

print(f"\n{'='*80}")
print(f"ДИАГНОСТИКА: {BEER_TO_CHECK.upper()} в баре {BAR}")
print(f"Период: {DATE_FROM} - {DATE_TO}")
print(f"{'='*80}\n")

# 1. Получаем данные из OLAP
print("[1] Подключаемся к iiko API...")
olap = OlapReports()
if not olap.connect():
    print("[ERROR] Не удалось подключиться к API")
    exit()

print(f"[2] Запрашиваем OLAP отчёт...")
report_data = olap.get_draft_sales_report(DATE_FROM, DATE_TO, BAR)
olap.disconnect()

if not report_data or not report_data.get('data'):
    print("[ERROR] Нет данных")
    exit()

# 2. Создаём DataFrame
df = pd.DataFrame(report_data['data'])
print(f"[3] Получено записей из OLAP: {len(df)}")

# Преобразуем типы
df['DishAmountInt'] = pd.to_numeric(df['DishAmountInt'], errors='coerce')
df['DishDiscountSumInt'] = pd.to_numeric(df['DishDiscountSumInt'], errors='coerce')
df['ProductCostBase.ProductCost'] = pd.to_numeric(df['ProductCostBase.ProductCost'], errors='coerce')
df['ProductCostBase.MarkUp'] = pd.to_numeric(df['ProductCostBase.MarkUp'], errors='coerce')

# 3. Применяем DraftAnalysis
print(f"\n[4] Применяем DraftAnalysis...")
analyzer = DraftAnalysis(df)
prepared_df = analyzer.prepare_draft_data()

print(f"    После prepare_draft_data: {len(prepared_df)} записей")
print(f"    Исключено записей с нулевым объёмом: {len(df) - len(prepared_df)}")

# 4. Фильтруем только "ФестХаус Хеллес"
festhaus_df = prepared_df[prepared_df['BeerName'].str.contains(BEER_TO_CHECK, case=False, na=False)].copy()

print(f"\n[5] Записей с '{BEER_TO_CHECK}': {len(festhaus_df)}")

if festhaus_df.empty:
    print(f"[ERROR] Не найдено записей с '{BEER_TO_CHECK}'")
    print("\nДоступные названия пива:")
    print(prepared_df['BeerName'].unique()[:20])
    exit()

# 5. Показываем детали
print(f"\n{'='*80}")
print("ДЕТАЛИ ПО ПОРЦИЯМ:")
print(f"{'='*80}")

portion_summary = festhaus_df.groupby('PortionVolume').agg({
    'DishAmountInt': 'sum',
    'VolumeInLiters': 'sum'
}).reset_index()

portion_summary = portion_summary.sort_values('PortionVolume')

print(f"\n{'Порция (л)':<12} {'Кол-во порций':<15} {'Объём (л)':<12}")
print(f"{'-'*40}")
for _, row in portion_summary.iterrows():
    print(f"{row['PortionVolume']:<12.1f} {int(row['DishAmountInt']):<15} {row['VolumeInLiters']:<12.1f}")

total_portions = portion_summary['DishAmountInt'].sum()
total_liters = portion_summary['VolumeInLiters'].sum()

print(f"{'-'*40}")
print(f"{'ИТОГО:':<12} {int(total_portions):<15} {total_liters:<12.1f}")

# 6. Показываем по дням (первые 10 дней)
print(f"\n{'='*80}")
print("ПРОДАЖИ ПО ДНЯМ (первые 10 дней):")
print(f"{'='*80}\n")

daily_df = festhaus_df.copy()
daily_df['Date'] = pd.to_datetime(daily_df['OpenDate.Typed']).dt.date

daily_summary = daily_df.groupby('Date').agg({
    'DishAmountInt': 'sum',
    'VolumeInLiters': 'sum'
}).reset_index()

daily_summary = daily_summary.sort_values('Date').head(10)

print(f"{'Дата':<12} {'Порций':<10} {'Литров':<10}")
print(f"{'-'*35}")
for _, row in daily_summary.iterrows():
    print(f"{row['Date']} {int(row['DishAmountInt']):<10} {row['VolumeInLiters']:<10.1f}")

# 7. Проверяем исходные DishName
print(f"\n{'='*80}")
print("УНИКАЛЬНЫЕ ВАРИАНТЫ DishName:")
print(f"{'='*80}\n")

dish_variants = festhaus_df['DishName'].unique()
for i, dish in enumerate(dish_variants, 1):
    count = len(festhaus_df[festhaus_df['DishName'] == dish])
    total_vol = festhaus_df[festhaus_df['DishName'] == dish]['VolumeInLiters'].sum()
    print(f"{i}. {dish:<50} ({count} записей, {total_vol:.1f}л)")

# 8. Итоговый результат через get_beer_summary
print(f"\n{'='*80}")
print("РЕЗУЛЬТАТ ЧЕРЕЗ get_beer_summary:")
print(f"{'='*80}\n")

summary = analyzer.get_beer_summary(BAR, include_financials=True)
festhaus_summary = summary[summary['BeerName'].str.contains(BEER_TO_CHECK, case=False, na=False)]

if not festhaus_summary.empty:
    row = festhaus_summary.iloc[0]
    print(f"BeerName:      {row['BeerName']}")
    print(f"TotalLiters:   {row['TotalLiters']:.2f} л")
    print(f"TotalPortions: {int(row['TotalPortions'])} шт")
    print(f"TotalRevenue:  {row['TotalRevenue']:.2f} руб")
    print(f"Kegs30L:       {row['Kegs30L']:.2f}")
else:
    print(f"[ERROR] '{BEER_TO_CHECK}' не найден в summary")

print(f"\n{'='*80}")
print("ГОТОВО!")
print(f"{'='*80}\n")
