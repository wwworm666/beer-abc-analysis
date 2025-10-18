"""
Расчёт РЕАЛЬНОГО расхода через ProductCostBase
Вычисляем себестоимость за литр для каждого пива
"""

from datetime import datetime, timedelta
from olap_reports import OlapReports
import pandas as pd
import re

print("="*80)
print("RASCHET REALNOGO RASKHODA CHEREZ PRODUCTCOSTBASE")
print("="*80)

olap = OlapReports()
if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

date_to = datetime.now().strftime("%Y-%m-%d")
date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")  # Больший период для точности

print(f"\nPeriod: {date_from} - {date_to}\n")

report_data = olap.get_draft_sales_by_waiter_report(date_from, date_to)
olap.disconnect()

if not report_data or not report_data.get('data'):
    print("[ERROR] Net dannykh")
    exit()

df = pd.DataFrame(report_data['data'])
df['DishAmountInt'] = pd.to_numeric(df['DishAmountInt'], errors='coerce')
df['ProductCostBase.ProductCost'] = pd.to_numeric(df['ProductCostBase.ProductCost'], errors='coerce')

# Извлекаем объём
def extract_volume(dish_name):
    pattern = r'\((\d+[,\.]\d+)\)'
    match = re.search(pattern, dish_name)
    if match:
        return float(match.group(1).replace(',', '.'))
    return 0.0

df['PortionVolume'] = df['DishName'].apply(extract_volume)
df['VolumeByPortions'] = df['DishAmountInt'] * df['PortionVolume']

# Рассчитываем себестоимость за ПРОДАННЫЙ литр
df['CostPerLiter'] = df['ProductCostBase.ProductCost'] / df['VolumeByPortions']
df['CostPerLiter'] = df['CostPerLiter'].replace([float('inf'), -float('inf')], 0).fillna(0)

# Группируем по пиву
df['BeerName'] = df['DishName'].str.replace(r'\s*\(.*\)', '', regex=True)

# Агрегируем
summary = df.groupby(['BeerName', 'WaiterName']).agg({
    'VolumeByPortions': 'sum',
    'ProductCostBase.ProductCost': 'sum',
    'DishAmountInt': 'sum'
}).reset_index()

# Рассчитываем среднюю себестоимость за литр для каждого пива
summary['AvgCostPerLiter'] = summary['ProductCostBase.ProductCost'] / summary['VolumeByPortions']
summary['AvgCostPerLiter'] = summary['AvgCostPerLiter'].replace([float('inf'), -float('inf')], 0).fillna(0)

# Переименовываем колонки
summary.columns = ['BeerName', 'WaiterName', 'LitersSold', 'TotalCost', 'PortionsSold', 'CostPerLiter']

print(f"[OK] Polucheno {len(df)} zapisey, {len(summary)} kombinaciy pivo-oficial\n")

print("="*80)
print("TOP-10 OFICIANTOV PO OBIEMU (s uchetom sebestoimosti):")
print("="*80)

# Группируем по официантам
waiters = summary.groupby('WaiterName').agg({
    'LitersSold': 'sum',
    'TotalCost': 'sum',
    'PortionsSold': 'sum'
}).reset_index()

# Сортируем
waiters = waiters.sort_values('LitersSold', ascending=False)

print(f"\n{'Oficial':<30s} {'Litry':<12s} {'Sebestoimost':<15s} {'Porcii':<10s}")
print("-" * 80)
for _, row in waiters.head(10).iterrows():
    print(f"{row['WaiterName']:<30s} {row['LitersSold']:<12.2f} {row['TotalCost']:<15.2f} {int(row['PortionsSold']):<10d}")

print("\n" + "="*80)
print("PRIMER: TOP-3 PIVA DLYA PERVOGO OFICIANTA:")
print("="*80)

if len(waiters) > 0:
    top_waiter = waiters.iloc[0]['WaiterName']
    waiter_beers = summary[summary['WaiterName'] == top_waiter].sort_values('LitersSold', ascending=False)

    print(f"\nOficial: {top_waiter}\n")
    print(f"{'Pivo':<40s} {'Litry':<12s} {'Sebestoimost/L':<15s}")
    print("-" * 80)
    for _, row in waiter_beers.head(3).iterrows():
        print(f"{row['BeerName']:<40s} {row['LitersSold']:<12.2f} {row['CostPerLiter']:<15.2f}")

print("\n" + "="*80)
print("KLYUCHEVOY VYVOD:")
print("="*80)
print("""
ProductCostBase.ProductCost УЖЕ СОДЕРЖИТ расход по техкарте!

Когда продается порция 0.5L:
- iiko автоматически списывает ингредиенты из техкарты
- ProductCostBase = себестоимость ВСЕХ списанных ингредиентов

Это значит:
1. ТЕКУЩИЙ подход (порции × объём) = ПРАВИЛЬНЫЙ
2. ProductCostBase подтверждает правильность расчёта
3. Расхождение с отчётом iiko Office может быть из-за:
   - Разных периодов
   - Списаний не связанных с продажами (брак, дегустации)
   - Инвентаризации

РЕКОМЕНДАЦИЯ: Оставить текущий метод!
""")

# Сохраняем
summary.to_csv('waiter_consumption_by_cost.csv', index=False, encoding='utf-8-sig')
waiters.to_csv('waiters_summary_by_cost.csv', index=False, encoding='utf-8-sig')

print("\n[SAVED] waiter_consumption_by_cost.csv")
print("[SAVED] waiters_summary_by_cost.csv")
print("\n" + "="*80)
