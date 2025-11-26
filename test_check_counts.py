"""Тест нового способа подсчёта чеков"""
from core.olap_reports import OlapReports

olap = OlapReports()

if olap.connect():
    # Тест нового метода
    result = olap.get_orders_count_report('2025-11-17', '2025-11-24', 'Кременчугская')
    
    if result and 'data' in result:
        total = 0
        print("Количество заказов по дням:")
        for record in result['data']:
            date = record.get('OpenDate.Typed')
            count = record.get('UniqOrderId.OrdersCount', 0)
            print(f"  {date}: {count} заказов")
            total += count
        
        print(f"\nВсего заказов: {total}")
    
    olap.disconnect()
