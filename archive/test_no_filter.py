from datetime import datetime, timedelta
from olap_reports import OlapReports
import json

print("🔍 Запрашиваем данные БЕЗ фильтра по группе\n")

olap = OlapReports()

if not olap.connect():
    print("❌ Не удалось подключиться")
    exit()

# Запрашиваем за последние 7 дней (меньше период)
date_to = datetime.now().strftime("%Y-%m-%d")
date_from = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

# Формируем запрос БЕЗ фильтра по Фасовка
request = {
    "reportType": "SALES",
    "groupByRowFields": [
        "DishGroup.TopParent",  # Группа 1-го уровня - ГЛАВНОЕ!
        "DishName"              # Название блюда
    ],
    "groupByColFields": [],
    "aggregateFields": [
        "DishAmountInt"  # Количество
    ],
    "filters": {
        "OpenDate.Typed": {
            "filterType": "DateRange",
            "periodType": "CUSTOM",
            "from": date_from,
            "to": date_to
        },
        "DeletedWithWriteoff": {
            "filterType": "IncludeValues",
            "values": ["NOT_DELETED"]
        },
        "OrderDeleted": {
            "filterType": "IncludeValues",
            "values": ["NOT_DELETED"]
        }
    }
}

print(f"Период: {date_from} - {date_to}\n")

import requests

url = f"{olap.api.base_url}/v2/reports/olap"
params = {"key": olap.token}
headers = {"Content-Type": "application/json"}

response = requests.post(url, params=params, json=request, headers=headers)

if response.status_code == 200:
    data = response.json()
    
    # Сохраним полный отчет
    with open("all_groups.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("✅ Отчет получен!")
    print(f"📊 Всего записей: {len(data.get('data', []))}\n")
    
    # Соберем уникальные группы 1-го уровня
    groups = set()
    for record in data.get('data', []):
        group = record.get('DishGroup.TopParent')
        if group:
            groups.add(group)
    
    print("📋 Найденные ГРУППЫ 1-го УРОВНЯ:")
    print("=" * 50)
    for group in sorted(groups):
        print(f"  - {group}")
    print("=" * 50)
    
    # Покажем несколько примеров записей
    print("\n📝 Примеры записей (первые 5):")
    for i, record in enumerate(data.get('data', [])[:5], 1):
        group = record.get('DishGroup.TopParent', 'N/A')
        dish = record.get('DishName', 'N/A')
        qty = record.get('DishAmountInt', 0)
        print(f"\n{i}. Группа: {group}")
        print(f"   Блюдо: {dish}")
        print(f"   Кол-во: {qty}")
    
    print(f"\n💾 Полный отчет сохранен в: all_groups.json")
    
else:
    print(f"❌ Ошибка: {response.status_code}")
    print(response.text)

olap.disconnect()