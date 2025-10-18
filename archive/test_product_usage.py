"""
Проверяем endpoint для получения информации о вхождении товара в блюда
Попробуем разные варианты
"""

from iiko_api import IikoAPI
import requests
import json

api = IikoAPI()
if not api.authenticate():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

# Берем ID одного из известных кегов
keg_id = "9963ae82-d3b3-438e-aa1c-48e75935ef16"  # КЕГ Brewlok IPA 20 л
keg_name = "КЕГ Brewlok IPA 20 л"

print("="*80)
print(f"ISHCHEM ENDPOINT DLya POLUCHENIYA SOSTAVA/RECEPTURY")
print(f"Test KEG: {keg_name}")
print(f"Test KEG ID: {keg_id}")
print("="*80)

# Пробуем разные эндпоинты
test_endpoints = [
    f"/products/{keg_id}/usage",
    f"/products/{keg_id}/dishes",
    f"/products/{keg_id}/recipes",
    f"/products/{keg_id}",
    "/dishes",
    "/assortment/items",
    "/corporation/products",
]

for endpoint in test_endpoints:
    url = f"{api.base_url}{endpoint}"
    params = {"key": api.token}

    print(f"\n[TEST] {endpoint}")

    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"  Status: {response.status_code}")

        if response.status_code == 200:
            print(f"  [OK] Endpoint rabotaet!")

            # Пытаемся сохранить ответ
            content_type = response.headers.get('Content-Type', '')

            if 'json' in content_type:
                data = response.json()
                filename = f"test_{endpoint.replace('/', '_')}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  [SAVED JSON] {filename}")
            elif 'xml' in content_type:
                filename = f"test_{endpoint.replace('/', '_')}.xml"
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"  [SAVED XML] {filename}")
                print(f"  Content preview: {response.text[:200]}")
            else:
                print(f"  Response: {response.text[:300]}")

        elif response.status_code == 404:
            print(f"  [NOT FOUND] Endpoint ne sushchestvuet")
        else:
            print(f"  Error: {response.text[:200]}")

    except Exception as e:
        print(f"  Exception: {e}")

api.logout()

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
