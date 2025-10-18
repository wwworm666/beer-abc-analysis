"""
Анализ метода расчёта через ProductCostBase
Проверяем можно ли использовать себестоимость для расчёта реального расхода
"""

from datetime import datetime, timedelta
from olap_reports import OlapReports
import pandas as pd
import re

print("="*80)
print("ANALIZ METODA RASHODA CHEREZ PRODUCTCOSTBASE")
print("="*80)

# Подключаемся
olap = OlapReports()
if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

date_to = datetime.now().strftime("%Y-%m-%d")
date_from = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

print(f"\nPeriod: {date_from} - {date_to}")
print("Bar: Bolshoy pr. V.O\n")

# Получаем данные
report_data = olap.get_draft_sales_by_waiter_report(date_from, date_to, "Большой пр. В.О")
olap.disconnect()

if not report_data or not report_data.get('data'):
    print("[ERROR] Net dannykh")
    exit()

# Преобразуем в DataFrame
df = pd.DataFrame(report_data['data'])
df['DishAmountInt'] = pd.to_numeric(df['DishAmountInt'], errors='coerce')
df['ProductCostBase.ProductCost'] = pd.to_numeric(df['ProductCostBase.ProductCost'], errors='coerce')
df['DishDiscountSumInt'] = pd.to_numeric(df['DishDiscountSumInt'], errors='coerce')

print(f"[OK] Polucheno {len(df)} zapisey\n")

# Извлекаем объём
def extract_volume(dish_name):
    pattern = r'\((\d+[,\.]\d+)\)'
    match = re.search(pattern, dish_name)
    if match:
        return float(match.group(1).replace(',', '.'))
    return 0.0

df['PortionVolume'] = df['DishName'].apply(extract_volume)
df['VolumeByPortions'] = df['DishAmountInt'] * df['PortionVolume']

# Группируем по пиву (убираем объём из названия)
df['BeerName'] = df['DishName'].str.replace(r'\s*\(.*\)', '', regex=True)

print("="*80)
print("VSE VARIANTY PODSCHETA:")
print("="*80)

print("\n1. TEKUSCHIY VARIANT (po porciyam):")
print("-" * 80)

# Группируем по пиву
summary1 = df.groupby('BeerName').agg({
    'VolumeByPortions': 'sum',
    'DishAmountInt': 'sum',
    'ProductCostBase.ProductCost': 'sum',
    'DishDiscountSumInt': 'sum'
}).round(2)

summary1.columns = ['TotalLiters_Method1', 'TotalPortions', 'TotalCost', 'TotalRevenue']

print(f"\n{'Pivo':<40s} {'Litry':<12s} {'Porcii':<10s}")
print("-" * 80)
for beer, row in summary1.head(10).iterrows():
    print(f"{beer:<40s} {row['TotalLiters_Method1']:<12.2f} {int(row['TotalPortions']):<10d}")

print("\n\n2. VARIANT CHEREZ SEBESTOIMOST (esli izvestna cena za litr):")
print("-" * 80)
print("\nPREDPOLOZHIM chto sebestoimost kegi 30L = 5000 rub")
print("Togda cena za litr = 5000 / 30 = 166.67 rub/L\n")

COST_PER_LITER = 166.67  # Примерная себестоимость за литр

summary1['TotalLiters_Method2'] = (summary1['TotalCost'] / COST_PER_LITER).round(2)
summary1['Difference'] = (summary1['TotalLiters_Method2'] - summary1['TotalLiters_Method1']).round(2)
summary1['DifferencePercent'] = ((summary1['Difference'] / summary1['TotalLiters_Method1']) * 100).round(1)

print(f"{'Pivo':<40s} {'Method1':<12s} {'Method2':<12s} {'Raznica':<12s} {'%':<8s}")
print("-" * 80)
for beer, row in summary1.head(10).iterrows():
    print(f"{beer:<40s} {row['TotalLiters_Method1']:<12.2f} {row['TotalLiters_Method2']:<12.2f} {row['Difference']:<12.2f} {row['DifferencePercent']:<8.1f}%")

print("\n" + "="*80)
print("VYVOD:")
print("="*80)
print("""
1. METOD PO PORCIYAM (tekuschiy):
   - Schitaem: porci × obem
   - Prostoy i ponyatny
   - NE UCHTVAET: poteri, penu, degustacii

2. METOD PO SEBESTOIMOSTI:
   - Schitaem: sebestoimost / cena_za_litr
   - Mozhet uchest fakticheskiy raskhod PO TEKHKARTE
   - NO: nuzhno znat sebestoimost kegi

3. PROBLEMA:
   - Razniza mezhdu metodami pokazyvaet POTERI
   - Chtoby uznat tochnuyu cifru, nado:
     a) Znat tochnuyu sebestoimost kazhdoy kegi
     b) Ili ispolzovat otchet iz iiko Office
     c) Ili nastroit STOCK uchet

4. REKOMENDACIYA:
   - Ispolzovat tekuschiy metod (po porciyam)
   - On pokazyvaet PRODANNYY obyom
   - Dlya analiza raboty oficiantov eto PRAVILEN
   - Poteri - eto otdelnaya tema (kontrolya kachestva)
""")

# Сохраняем сравнение
summary1.to_csv('comparison_methods.csv', encoding='utf-8-sig')
print("\n[SAVED] comparison_methods.csv")
print("\n" + "="*80)
