"""
Тестовый скрипт для получения номенклатуры товаров из iiko
"""
from core.iiko_api import IikoAPI
import json
import sys
import io

# Фикс кодировки для Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("Testiruem poluchenie nomenklatury iz iiko\n")

# Создаем API клиент
api = IikoAPI()

# Подключаемся
if not api.authenticate():
    print("Ne udalos podklyuchitsya k API")
    exit()

print(f"Token: {api.token[:20]}...\n")

# Пробуем разные эндпоинты для номенклатуры
import requests

endpoints = [
    "/products",
    "/nomenclature",
    "/corporation/products",
    "/v2/entities/products/list"
]

for endpoint in endpoints:
    print(f"Probuyem endpoint: {endpoint}")
    url = f"{api.base_url}{endpoint}"

    try:
        response = requests.get(url, params={"key": api.token}, timeout=10)
        print(f"  Status: {response.status_code}")

        if response.status_code == 200:
            print(f"  SUCCESS! Content-Type: {response.headers.get('Content-Type')}")
            print(f"  Response length: {len(response.text)} bytes")

            # Попробуем сохранить результат
            filename = f"nomenclature_{endpoint.replace('/', '_')}.json"

            # Попробуем распарсить как JSON
            try:
                data = response.json()
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  Saved to: {filename}")
                print(f"  Data type: {type(data)}")
                if isinstance(data, list):
                    print(f"  Items count: {len(data)}")
                    if len(data) > 0:
                        print(f"  First item keys: {list(data[0].keys())}")
                elif isinstance(data, dict):
                    print(f"  Dict keys: {list(data.keys())}")
            except:
                # Может быть XML
                with open(filename.replace('.json', '.xml'), 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"  Saved as XML")

            break
        else:
            print(f"  Error: {response.text[:200]}")
    except Exception as e:
        print(f"  Exception: {e}")

    print()

# Отключаемся
api.logout()
print("Gotovo!")
