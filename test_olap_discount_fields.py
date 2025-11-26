"""Тест OLAP запроса с расширенным списком полей для поиска скидок"""
from core.olap_reports import OlapReports
import requests
import json

olap = OlapReports()

if olap.connect():
    # Запрос с дополнительными полями скидок
    request = {
        "reportType": "SALES",
        "groupByRowFields": [
            "Store.Name",
            "OpenDate.Typed",
            "DishName"
        ],
        "groupByColFields": [],
        "aggregateFields": [
            "DishAmountInt",
            "DishDiscountSumInt",
            "DiscountSum"  # Попробуем сумму скидки
        ],
        "filters": {
            "OpenDate.Typed": {
                "filterType": "DateRange",
                "periodType": "CUSTOM",
                "from": "2025-11-17",
                "to": "2025-11-24"
            },
            "Store.Name": {
                "filterType": "IncludeValues",
                "values": ["Кременчугская"]
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

    url = f"{olap.api.base_url}/v2/reports/olap"
    params = {"key": olap.token}
    headers = {"Content-Type": "application/json"}

    response = requests.post(url, params=params, json=request, headers=headers, timeout=60)

    if response.status_code == 200:
        result = response.json()
        print("Первая запись с расширенными полями:")
        if result.get('data') and len(result['data']) > 0:
            print(json.dumps(result['data'][0], indent=2, ensure_ascii=False))

            # Посчитаем общую сумму DiscountSum
            total_discount = sum(float(r.get('DiscountSum', 0) or 0) for r in result['data'])
            print(f"\nОбщая сумма DiscountSum: {total_discount:.2f} руб")
            print(f"Ожидаемое значение: 10657.00 руб")
        else:
            print("Нет данных в ответе")
    else:
        print(f"Ошибка: {response.status_code}")
        print(response.text)

    olap.disconnect()
