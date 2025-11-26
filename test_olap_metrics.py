"""Тест различных метрик OLAP для поиска количества чеков"""
from core.olap_reports import OlapReports
import json

olap = OlapReports()

if olap.connect():
    # Запрос с большим количеством метрик чтобы найти правильную
    request = {
        "reportType": "SALES",
        "groupByRowFields": [
            "Store.Name",
            "OpenDate.Typed"
        ],
        "groupByColFields": [],
        "aggregateFields": [
            "UniqOrderId",
            "UniqOrderId.OrdersCount",
            "OrdersCount",  # Попробуем это
            "DishAmountInt",
            "DishDiscountSumInt"
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
    
    result = olap._execute_olap_request(request)
    
    if result and 'data' in result:
        print("Результат OLAP без группировки по товарам:")
        print(f"Количество записей: {len(result['data'])}")
        print("\nПервая запись:")
        if result['data']:
            first = result['data'][0]
            print(json.dumps(first, indent=2, ensure_ascii=False))
            
        print("\nВсе записи:")
        total_orders = 0
        for record in result['data']:
            date = record.get('OpenDate.Typed')
            orders = record.get('UniqOrderId.OrdersCount', 0) or record.get('OrdersCount', 0)
            print(f"  {date}: {orders} заказов")
            total_orders += orders
        
        print(f"\nВсего заказов за период: {total_orders}")
    
    olap.disconnect()
