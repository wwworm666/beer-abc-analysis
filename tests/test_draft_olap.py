"""
Проверка OLAP отчета по разливному пиву
"""
from core.olap_reports import OlapReports
from datetime import datetime, timedelta

olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

date_to = datetime.now().strftime("%Y-%m-%d")
date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

print(f"Запрашиваю OLAP отчет по разливному пиву: {date_from} - {date_to}\n")

sales_data = olap.get_draft_sales_report(date_from, date_to, None)

if sales_data:
    print(f"Получен ответ!")
    print(f"Ключи: {sales_data.keys()}")

    data = sales_data.get('data', [])
    print(f"\nКоличество записей: {len(data)}")

    if data:
        print("\nПервые 10 записей:")
        for i, row in enumerate(data[:10], 1):
            print(f"\n{i}. {row.get('Dish.Name', 'N/A')}")
            print(f"   Объем: {row.get('DishAmountInt', 0)} л")
            print(f"   Группа: {row.get('DishGroup.TopParent', 'N/A')}")
            print(f"   Все поля: {list(row.keys())}")
    else:
        print("\nНет данных в ответе!")
        print(f"Структура ответа: {sales_data}")
else:
    print("Ошибка получения данных!")

olap.disconnect()
