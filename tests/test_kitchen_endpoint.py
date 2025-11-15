"""
Тестовый скрипт для проверки endpoint /api/stocks/kitchen
"""
import requests
import json

print("Testiruem endpoint /api/stocks/kitchen\n")

# Запускаем запрос к локальному серверу
# ВАЖНО: Сервер должен быть запущен (python app.py)

try:
    # Пробуем подключиться к серверу
    response = requests.get("http://localhost:5000/api/stocks/kitchen?bar=Общая", timeout=30)

    print(f"Status code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"\nTotal items: {data.get('total_items', 0)}")
        print(f"Low stock count: {data.get('low_stock_count', 0)}")

        items = data.get('items', [])
        if items:
            print(f"\nPervye 10 blyud:")
            for i, item in enumerate(items[:10], 1):
                print(f"\n{i}. {item.get('name', 'N/A')}")
                print(f"   Kategoriya: {item.get('category', 'N/A')}")
                print(f"   Ostatok: {item.get('stock', 0)}")
                print(f"   Srednie prodazhi: {item.get('avg_sales', 0)} v den")
                print(f"   Uroven: {item.get('stock_level', 'unknown')}")
        else:
            print("\nNet dannykh")
    else:
        print(f"Error: {response.text}")

except requests.exceptions.ConnectionError:
    print("ERROR: Ne mogu podklyuchitsya k serveru.")
    print("Zapustite server: python app.py")
except Exception as e:
    print(f"ERROR: {e}")
