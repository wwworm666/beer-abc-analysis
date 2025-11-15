"""
Тестовый скрипт для проверки endpoint /api/stocks/taplist с реальными данными из iiko
"""
import requests
import json

print("Testiruem endpoint /api/stocks/taplist s dannymi iz iiko API\n")

try:
    # Пробуем подключиться к серверу
    response = requests.get("http://localhost:5000/api/stocks/taplist?bar=Общая", timeout=120)

    print(f"Status code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"\nTotal items: {data.get('total_items', 0)}")
        print(f"Total liters: {data.get('total_liters', 0)}")
        print(f"Low stock count: {data.get('low_stock_count', 0)}")

        taps = data.get('taps', [])
        if taps:
            print(f"\nPervye 20 poziciy razlivnogo piva (sortirovka po ostatkam):")
            for i, tap in enumerate(taps[:20], 1):
                name = tap.get('beer_name', 'N/A')
                liters = tap.get('remaining_liters', 0)
                level = tap.get('stock_level', 'unknown')
                category = tap.get('category', 'N/A')

                print(f"\n{i}. {name}")
                print(f"   Kategoriya: {category}")
                print(f"   Ostatok: {liters} litrov")
                print(f"   Uroven: {level}")
        else:
            print("\nNet dannykh")
    else:
        print(f"Error: {response.text}")

except requests.exceptions.ConnectionError:
    print("ERROR: Ne mogu podklyuchitsya k serveru.")
    print("Zapustite server: python app.py")
except Exception as e:
    print(f"ERROR: {e}")
