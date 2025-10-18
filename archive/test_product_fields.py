"""
Тестовый скрипт для поиска полей товаров/продуктов
Цель: получить данные по кегам как по товарам, а не по блюдам
"""

from datetime import datetime, timedelta
from iiko_api import IikoAPI
import requests
import json

print("="*80)
print("TEST: Zapros dannykh po TOVARAM (produktam) vmesto blyud")
print("="*80)

# Подключаемся
api = IikoAPI()
if not api.authenticate():
    print("[ERROR] Ne udalos podklyuchitsya k API")
    exit()

date_to = datetime.now().strftime("%Y-%m-%d")
date_from = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

print(f"\nPeriod: {date_from} - {date_to}")

# Попробуем запрос с полями для ПРОДУКТОВ вместо блюд
# Согласно документации iiko, есть поля связанные с ингредиентами

test_requests = []

# ВАРИАНТ 1: Запрос по ингредиентам блюд
variant1 = {
    "reportType": "SALES",
    "groupByRowFields": [
        "Store.Name",
        "OpenDate.Typed",
        "WaiterName",
        "DishIngredient.Name",  # Название ингредиента
        "DishName"
    ],
    "groupByColFields": [],
    "aggregateFields": [
        "DishIngredient.Amount",  # Количество ингредиента
        "DishAmountInt"
    ],
    "filters": {
        "OpenDate.Typed": {
            "filterType": "DateRange",
            "periodType": "CUSTOM",
            "from": date_from,
            "to": date_to
        },
        "DishGroup.TopParent": {
            "filterType": "IncludeValues",
            "values": ["Напитки Розлив"]
        },
        "Store.Name": {
            "filterType": "IncludeValues",
            "values": ["Большой пр. В.О"]
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

# ВАРИАНТ 2: Продукты из себестоимости
variant2 = {
    "reportType": "SALES",
    "groupByRowFields": [
        "Store.Name",
        "OpenDate.Typed",
        "WaiterName",
        "ProductCostBase.ProductName",  # Название продукта из себестоимости
        "DishName"
    ],
    "groupByColFields": [],
    "aggregateFields": [
        "ProductCostBase.ProductAmount",  # Количество продукта
        "DishAmountInt"
    ],
    "filters": {
        "OpenDate.Typed": {
            "filterType": "DateRange",
            "periodType": "CUSTOM",
            "from": date_from,
            "to": date_to
        },
        "DishGroup.TopParent": {
            "filterType": "IncludeValues",
            "values": ["Напитки Розлив"]
        },
        "Store.Name": {
            "filterType": "IncludeValues",
            "values": ["Большой пр. В.О"]
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

test_requests = [
    ("Variant 1: DishIngredient", variant1),
    ("Variant 2: ProductCostBase.ProductName", variant2)
]

url = f"{api.base_url}/v2/reports/olap"
params = {"key": api.token}
headers = {"Content-Type": "application/json"}

for variant_name, request_body in test_requests:
    print("\n" + "="*80)
    print(f"TESTIRUEM: {variant_name}")
    print("="*80)

    try:
        response = requests.post(
            url,
            params=params,
            json=request_body,
            headers=headers
        )

        if response.status_code == 200:
            data = response.json()
            if data and data.get('data'):
                print(f"[OK] Polucheno zapisey: {len(data['data'])}")

                # Показываем первую запись
                first = data['data'][0]
                print("\nPERVAYA ZAPIS:")
                print("-" * 80)
                for key, value in sorted(first.items()):
                    print(f"  {key:40s} = {value}")

                # Сохраняем в файл
                filename = f"test_{variant_name.replace(' ', '_').replace(':', '')}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data['data'][:5], f, indent=2, ensure_ascii=False)
                print(f"\n[SAVED] {filename}")

            else:
                print("[WARNING] Net dannykh v otvete")
        else:
            print(f"[ERROR] Status: {response.status_code}")
            print(f"Response: {response.text[:500]}")

    except Exception as e:
        print(f"[ERROR] {e}")

api.logout()

print("\n" + "="*80)
print("ZAVERSHENO! Prover'te sozdannye JSON faily")
print("="*80)
