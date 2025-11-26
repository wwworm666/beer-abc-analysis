"""Тест суммы скидок из OLAP данных для Кременчугская 17.11-23.11"""
from core.olap_reports import OlapReports

olap = OlapReports()

if olap.connect():
    # Получаем данные по всем категориям
    draft_data = olap.get_draft_sales_report('2025-11-17', '2025-11-24', 'Кременчугская')
    bottles_data = olap.get_beer_sales_report('2025-11-17', '2025-11-24', 'Кременчугская')
    kitchen_data = olap.get_kitchen_sales_report('2025-11-17', '2025-11-24', 'Кременчугская')

    total_discount = 0

    # Суммируем DishDiscountSumInt из всех категорий
    for data in [draft_data, bottles_data, kitchen_data]:
        if data and 'data' in data:
            for record in data['data']:
                discount = record.get('DishDiscountSumInt', 0)
                if discount:
                    total_discount += float(discount)

    print(f"Сумма скидок (DishDiscountSumInt) для Кременчугская 17.11-23.11:")
    print(f"  {total_discount:.2f} руб")
    print()
    print(f"Ожидаемое значение: 10657.00 руб")
    print(f"Разница: {abs(total_discount - 10657):.2f} руб")

    olap.disconnect()
