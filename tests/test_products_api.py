"""
Тестовый скрипт для проверки получения данных о товарах через API
"""
from datetime import datetime, timedelta
from core.olap_reports import OlapReports
import json
import sys
import io

# Фикс кодировки для Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("Testiruem poluchenie dannykh o tovarakh\n")

# Создаем объект для работы с отчетами
olap = OlapReports()

# Подключаемся
if not olap.connect():
    print("Ne udalos podklyuchitsya k API")
    exit()

# Запрашиваем отчет за последние 30 дней
date_to_obj = datetime.now()
date_from_obj = datetime.now() - timedelta(days=30)

# Формат DD.MM.YYYY для API
date_to = date_to_obj.strftime("%d.%m.%Y")
date_from = date_from_obj.strftime("%d.%m.%Y")

print(f"Period: {date_from} - {date_to}\n")

# Получаем отчет по складским операциям с товарами
print("=== 1. Otchet po skladskim operaciyam ===")
store_data = olap.get_store_operations_report(date_from, date_to)

if store_data:
    # Сохраняем в файл для просмотра
    with open("store_operations_report.json", "w", encoding="utf-8") as f:
        json.dump(store_data, f, indent=2, ensure_ascii=False)

    print("\nOtchet sokhranyen v file: store_operations_report.json")

    # Покажем статистику
    if isinstance(store_data, list) and len(store_data) > 0:
        print(f"\nPolucheno zapisey: {len(store_data)}")

        # Подсчитаем уникальные товары
        products = {}
        for record in store_data:
            product_name = record.get("product", "Unknown")
            if product_name and product_name != "Unknown":
                if product_name not in products:
                    products[product_name] = {
                        'incoming': 0,
                        'outgoing': 0,
                        'count': 0
                    }
                products[product_name]['count'] += 1

                # Проверяем направление (incoming/outgoing)
                amount = float(record.get('amount', 0) or 0)
                is_incoming = record.get('incoming', 'false') == 'true'

                if is_incoming:
                    products[product_name]['incoming'] += amount
                else:
                    products[product_name]['outgoing'] += abs(amount)  # Расход обычно отрицательный

        print(f"\nUnikalnykh tovarov: {len(products)}")
        print("\nPervye 10 tovarov:")
        for i, (name, data) in enumerate(list(products.items())[:10], 1):
            print(f"{i}. {name}")
            print(f"   Prikhod: {data['incoming']}, Raskhod: {data['outgoing']}")
            print(f"   Operaciy: {data['count']}")
    else:
        print("\nDannye ne naydeny ili neverniy format")
else:
    print("\nNe udalos poluchit otchet po skladskim operaciyam")

# Отключаемся
olap.disconnect()
print("\nGotovo!")
