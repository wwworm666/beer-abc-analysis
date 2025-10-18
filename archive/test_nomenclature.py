"""
Проверяем есть ли endpoint для получения номенклатуры/рецептов
Попробуем разные варианты:
- /nomenclature
- /products
- /recipes
- /dishes
"""

from iiko_api import IikoAPI
import requests
import json

api = IikoAPI()
if not api.authenticate():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

# Пробуем разные эндпоинты
endpoints = [
    "/nomenclature",
    "/products",
    "/recipes",
    "/dishes",
    "/assortment",
    "/menu"
]

print("="*80)
print("TESTIRUEM RAZNYE ENDPOINTY DLya POLUCHENIYA RECEPTUR/NOMENKLATURY")
print("="*80)

for endpoint in endpoints:
    url = f"{api.base_url}{endpoint}"
    params = {"key": api.token}

    print(f"\n[TEST] {endpoint}")
    print(f"  URL: {url}")

    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"  Status: {response.status_code}")

        if response.status_code == 200:
            print(f"  [OK] Endpoint rabotaet!")
            # Сохраняем результат
            filename = f"response_{endpoint.replace('/', '')}.json"
            try:
                data = response.json()
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"  [SAVED] {filename}")

                # Показываем структуру
                if isinstance(data, dict):
                    print(f"  Keys: {list(data.keys())[:5]}")
                elif isinstance(data, list):
                    print(f"  Items count: {len(data)}")
                    if len(data) > 0:
                        print(f"  First item keys: {list(data[0].keys())[:5] if isinstance(data[0], dict) else 'N/A'}")
            except:
                print(f"  Response (text): {response.text[:200]}")
        else:
            print(f"  Error: {response.text[:200]}")

    except Exception as e:
        print(f"  Exception: {e}")

api.logout()

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
