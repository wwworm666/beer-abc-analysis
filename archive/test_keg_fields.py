"""
Тестовый скрипт для проверки доступных полей в OLAP отчёте
Цель: найти поля для работы с ингредиентами (кегами)
"""

from datetime import datetime, timedelta
from olap_reports import OlapReports
import json

print("="*60)
print("TEST: Poisk poley dlya raboty s kegami")
print("="*60)

# Подключаемся
olap = OlapReports()
if not olap.connect():
    print("[ERROR] Ne udalos podklyuchitsya k API")
    exit()

# Запрашиваем данные за последние 7 дней (небольшой период)
date_to = datetime.now().strftime("%Y-%m-%d")
date_from = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

print(f"\nPeriod: {date_from} - {date_to}")
print("Zaprashivaem dannye po razlivnomu pivu s oficiantami...\n")

# Получаем данные
report_data = olap.get_draft_sales_by_waiter_report(date_from, date_to, "Большой пр. В.О")
olap.disconnect()

if not report_data or not report_data.get('data'):
    print("[ERROR] Net dannykh")
    exit()

print(f"[OK] Polucheno {len(report_data['data'])} zapisey\n")

# Показываем первую запись и все её поля
if report_data['data']:
    first_record = report_data['data'][0]

    print("DOSTUPNYE POLYA V PERVOY ZAPISI:")
    print("-" * 60)
    for key, value in sorted(first_record.items()):
        print(f"  {key:40s} = {value}")

    print("\n" + "="*60)
    print("ANALIZ:")
    print("="*60)

    # Сохраняем полный пример в JSON
    with open("test_keg_sample.json", "w", encoding="utf-8") as f:
        json.dump(report_data['data'][:5], f, indent=2, ensure_ascii=False)

    print("[OK] Pervye 5 zapisey sokhraneny v: test_keg_sample.json")
    print("\nIschem polya svyazannye s:")
    print("   - Ingredientami (Ingredient, Product)")
    print("   - Kegami (KEG, Bochka)")
    print("   - Spisaniem (Writeoff, Consumption)")

    # Проверяем наличие полезных полей
    interesting_fields = []
    for key in first_record.keys():
        lower_key = key.lower()
        if any(word in lower_key for word in ['ingredient', 'product', 'keg', 'consumption', 'writeoff']):
            interesting_fields.append(key)

    if interesting_fields:
        print(f"\n[FOUND] Interesnye polya: {interesting_fields}")
    else:
        print("\n[WARNING] Polya dlya ingredientov ne naydeny v tekuschem zaprose")
        print("          Vozmozhno, nuzhno dobavit ikh v groupByRowFields")

print("\n" + "="*60)
print("GOTOVO!")
print("="*60)
