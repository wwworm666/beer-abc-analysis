"""
Тестовый скрипт для проверки получения данных меню кухни через API
"""
from datetime import datetime, timedelta
from core.olap_reports import OlapReports
import json
import sys
import io

# Фикс кодировки для Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("Testiruem poluchenie dannykh menyu kukhni\n")

# Создаем объект для работы с отчетами
olap = OlapReports()

# Подключаемся
if not olap.connect():
    print("Ne udalos podklyuchitsya k API")
    exit()

# Запрашиваем отчет за последние 30 дней
date_to = datetime.now().strftime("%Y-%m-%d")
date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

print(f"Период: {date_from} - {date_to}\n")

# Получаем отчет по кухне (все блюда кроме напитков)
report_data = olap.get_kitchen_sales_report(date_from, date_to)

if report_data:
    # Сохраняем в файл для просмотра
    with open("kitchen_report.json", "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print("\nOtchet sokhranyen v file: kitchen_report.json")

    # Покажем статистику
    if "data" in report_data and len(report_data["data"]) > 0:
        print(f"\nPolucheno zapisey: {len(report_data['data'])}")

        # Группируем по категориям
        categories = {}
        for record in report_data["data"]:
            cat = record.get("DishGroup.TopParent", "Прочее")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(record)

        print(f"\nKategoriy naydeno: {len(categories)}")
        for cat, items in categories.items():
            print(f"   - {cat}: {len(items)} pozitsiy")

        # Покажем первые 5 записей
        print("\nPervye 5 zapisey:")
        for i, record in enumerate(report_data["data"][:5], 1):
            print(f"\n{i}. Blyudo: {record.get('DishName', 'N/A')}")
            print(f"   Kategoriya: {record.get('DishGroup.TopParent', 'N/A')}")
            print(f"   Kolichestvo: {record.get('DishAmountInt', 0)}")
    else:
        print("\nDannye ne naydeny")
else:
    print("\nNe udalos poluchit otchet")

# Отключаемся
olap.disconnect()
print("\nGotovo!")
