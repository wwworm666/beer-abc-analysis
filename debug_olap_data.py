"""Проверка структуры OLAP данных"""
from core.olap_reports import OlapReports
from datetime import datetime

olap = OlapReports()

if olap.connect():
    print("Получение данных Кременчугская 17.11-23.11...\n")
    
    # Разливное
    draft_data = olap.get_draft_sales_report('2025-11-17', '2025-11-24', 'Кременчугская')
    if draft_data and 'data' in draft_data:
        records = draft_data['data']
        print(f"Разливное: {len(records)} записей")
        if records:
            print("Первая запись:")
            first = records[0]
            print(f"  Название: {first.get('DishName')}")
            print(f"  UniqOrderId: {first.get('UniqOrderId')}")
            print(f"  UniqOrderId.OrdersCount: {first.get('UniqOrderId.OrdersCount')}")
            print(f"  Поля: {list(first.keys())}")
    
    print()
    
    # Фасовка
    bottles_data = olap.get_beer_sales_report('2025-11-17', '2025-11-24', 'Кременчугская')
    if bottles_data and 'data' in bottles_data:
        records = bottles_data['data']
        print(f"Фасовка: {len(records)} записей")
        if records:
            print("Первая запись:")
            first = records[0]
            print(f"  Название: {first.get('DishName')}")
            print(f"  UniqOrderId: {first.get('UniqOrderId')}")
            print(f"  UniqOrderId.OrdersCount: {first.get('UniqOrderId.OrdersCount')}")
    
    print()
    
    # Кухня
    kitchen_data = olap.get_kitchen_sales_report('2025-11-17', '2025-11-24', 'Кременчугская')
    if kitchen_data and 'data' in kitchen_data:
        records = kitchen_data['data']
        print(f"Кухня: {len(records)} записей")
        if records:
            print("Первая запись:")
            first = records[0]
            print(f"  Название: {first.get('DishName')}")
            print(f"  UniqOrderId: {first.get('UniqOrderId')}")
            print(f"  UniqOrderId.OrdersCount: {first.get('UniqOrderId.OrdersCount')}")
    
    olap.disconnect()
else:
    print("Не удалось подключиться к API")
