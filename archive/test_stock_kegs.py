"""
Тестовый запрос STOCK отчёта для получения данных по кегам
"""

from iiko_api import IikoAPI
from datetime import datetime, timedelta
import requests
import json

print("="*80)
print("TEST: STOCK OTCHET - SPISANIE KEG PO OFICIIANTAM")
print("="*80)

api = IikoAPI()
if not api.authenticate():
    print("[ERROR] Ne udalos podklyuchitsya k API")
    exit()

date_to = datetime.now().strftime("%Y-%m-%d")
date_from = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

print(f"\nPeriod: {date_from} - {date_to}")
print("Bar: Bolshoy pr. V.O")

# Формируем STOCK запрос
request_body = {
    "reportType": "STOCK",  # Складской отчёт
    "groupByRowFields": [
        "ProductName",      # Название товара (кега)
        "User",             # Сотрудник (официант)
        "EventDate",        # Дата
        "Department"        # Бар
    ],
    "groupByColFields": [],
    "aggregateFields": [
        "Amount",                        # Количество списанного
        "ProductCostBase.ProductCost"    # Себестоимость
    ],
    "filters": {
        "EventDate": {
            "filterType": "DateRange",
            "periodType": "CUSTOM",
            "from": date_from,
            "to": date_to
        }
        # Убираем фильтр по бару чтобы посмотреть есть ли данные вообще
    }
}

url = f"{api.base_url}/v2/reports/olap"
params = {"key": api.token}
headers = {"Content-Type": "application/json"}

print("\nZaprashivaem STOCK otchet...\n")

try:
    response = requests.post(
        url,
        params=params,
        json=request_body,
        headers=headers
    )

    if response.status_code == 200:
        data = response.json()

        # Сохраняем
        with open("test_stock_kegs.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[OK] Polucheno zapisey: {len(data.get('data', []))}")
        print("[SAVED] test_stock_kegs.json\n")

        if data.get('data'):
            print("="*80)
            print("PERVYE 10 ZAPISEY:")
            print("="*80)

            for i, record in enumerate(data['data'][:10], 1):
                print(f"\n{i}.")
                for key, value in sorted(record.items()):
                    print(f"  {key:40s} = {value}")

            # Анализируем какие товары есть
            products = set()
            for record in data['data']:
                product_name = record.get('ProductName', '')
                if product_name and 'кег' in product_name.lower():
                    products.add(product_name)

            print("\n" + "="*80)
            print(f"NAYDEN KEG ({len(products)}):")
            print("="*80)
            for product in sorted(products)[:20]:
                print(f"  - {product}")

        else:
            print("[WARNING] Net dannykh v otvete")

    else:
        print(f"[ERROR] Status: {response.status_code}")
        print(f"Response: {response.text}")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()

api.logout()

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
