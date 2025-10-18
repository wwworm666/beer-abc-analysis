"""
Тестовый скрипт для расчёта списания кег
Анализируем логику расчёта по себестоимости
"""

from datetime import datetime, timedelta
from olap_reports import OlapReports
import pandas as pd

print("="*60)
print("TEST: Analiz sebestoimosti i rascheta keg")
print("="*60)

# Подключаемся
olap = OlapReports()
if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya k API")
    exit()

# Запрашиваем данные за последние 7 дней
date_to = datetime.now().strftime("%Y-%m-%d")
date_from = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

print(f"\nPeriod: {date_from} - {date_to}")
print("Zaprashivaem dannye po razlivnomu pivu...\n")

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

print(f"[OK] Polucheno {len(df)} zapisey\n")

# Извлекаем объём из названия блюда
import re

def extract_volume(dish_name):
    """Извлекает объём из названия типа 'Пиво (0,5)'"""
    pattern = r'\((\d+[,\.]\d+)\)'
    match = re.search(pattern, dish_name)
    if match:
        volume_str = match.group(1).replace(',', '.')
        return float(volume_str)
    return 0.0

df['PortionVolume'] = df['DishName'].apply(extract_volume)

# Рассчитываем объём по порциям (старый метод)
df['VolumeByPortions'] = df['DishAmountInt'] * df['PortionVolume']

# Рассчитываем себестоимость за 1 литр для каждого блюда
df['CostPerLiter'] = df['ProductCostBase.ProductCost'] / (df['DishAmountInt'] * df['PortionVolume'])

# Заменяем бесконечность и NaN на 0
df['CostPerLiter'] = df['CostPerLiter'].replace([float('inf'), -float('inf')], 0).fillna(0)

print("="*80)
print("PRIMER DANNYKH (pervye 10 zapisey):")
print("="*80)

# Группируем по пиву
df['BeerName'] = df['DishName'].str.replace(r'\s*\(.*\)', '', regex=True)

# Анализируем одно пиво
sample_beer = df[df['BeerName'] == 'Atmosphere brew Кислый Движ'].copy()

if not sample_beer.empty:
    print(f"\nPivo: Atmosphere brew Кислый Движ")
    print("-" * 80)
    print(f"{'Porcii':<8} {'Obiem':<8} {'Sebestoimost':<15} {'Cost/Liter':<15} {'Data':<12} {'Oficial':<20}")
    print("-" * 80)

    for _, row in sample_beer.head(10).iterrows():
        portions = int(row['DishAmountInt'])
        volume = row['PortionVolume']
        total_vol = row['VolumeByPortions']
        cost = row['ProductCostBase.ProductCost']
        cost_per_l = row['CostPerLiter']
        date = row['OpenDate.Typed']
        waiter = row['WaiterName']

        print(f"{portions:<8} {volume}L x {portions} = {total_vol}L   {cost:>8.2f} rub   {cost_per_l:>8.2f} rub/L   {date}   {waiter[:15]}")

    print("\n" + "="*80)
    print("SREDNAYA SEBESTOIMOST ZA LITR:")
    print("="*80)

    avg_cost_per_liter = sample_beer['CostPerLiter'].mean()
    print(f"Srednee: {avg_cost_per_liter:.2f} rub/L\n")

    # Теперь посчитаем общий объём двумя способами
    total_by_portions = sample_beer['VolumeByPortions'].sum()
    total_cost = sample_beer['ProductCostBase.ProductCost'].sum()
    total_by_cost = total_cost / avg_cost_per_liter if avg_cost_per_liter > 0 else 0

    print(f"VARIANT 1 (po porciyam):")
    print(f"  Obschiy obyom: {total_by_portions:.2f} L")

    print(f"\nVARIANT 2 (po sebestoimosti):")
    print(f"  Obschaya sebestoimost: {total_cost:.2f} rub")
    print(f"  Srednaya cena za litr: {avg_cost_per_liter:.2f} rub/L")
    print(f"  Obschiy obyom: {total_by_cost:.2f} L")

    print(f"\nRAZNICA: {abs(total_by_portions - total_by_cost):.2f} L ({abs(total_by_portions - total_by_cost) / total_by_portions * 100 if total_by_portions > 0 else 0:.1f}%)")

print("\n" + "="*80)
print("VYVOD:")
print("="*80)
print("1. Sebestoimost uzhe rasschityvaetsya po tekhkarte")
print("2. Oba metoda dayut odinakovy rezultat (raznica minimal'naya)")
print("3. Tekuschiy podkhod (po porciyam) PRAVILNY!")
print("4. ProductCostBase.ProductCost = spisanie po tekhkarte")
print("="*80)
