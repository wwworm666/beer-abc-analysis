"""Тест OLAP запроса БЕЗ группировки по товарам - только по дате"""
from core.olap_reports import OlapReports
import requests

olap = OlapReports()

if olap.connect():
    # Запрос БЕЗ группировки по DishName - только Store и Date
    request = {
        "reportType": "SALES",
        "groupByRowFields": [
            "Store.Name",
            "OpenDate.Typed"
        ],
        "groupByColFields": [],
        "aggregateFields": [
            "UniqOrderId.OrdersCount"
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
    
    response = requests.post(url, params=params, json=request, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        print("OLAP без группировки по товарам:")
        print(f"Записей: {len(result.get('data', []))}")
        
        total = 0
        for record in result.get('data', []):
            date = record.get('OpenDate.Typed')
            count = record.get('UniqOrderId.OrdersCount', 0)
            print(f"  {date}: {count} заказов")
            total += count
        
        print(f"\nВСЕГО ЗАКАЗОВ: {total}")
    else:
        print(f"Ошибка: {response.status_code}")
        print(response.text)
    
    olap.disconnect()
