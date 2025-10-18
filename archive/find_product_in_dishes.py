"""
Ищем API метод аналогичный "отчету о вхождении в блюдо" из iiko Office
В Office: правый клик на товаре -> "отчет о вхождении в блюдо"

Попробуем:
1. POST /products с параметрами
2. GET /products с фильтрами
3. Специальные endpoints для tech-cards
"""

from iiko_api import IikoAPI
import requests
import json
import xml.etree.ElementTree as ET

api = IikoAPI()
if not api.authenticate():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

# Тестовый кег
keg_id = "9963ae82-d3b3-438e-aa1c-48e75935ef16"  # КЕГ Brewlok IPA 20 л

print("="*80)
print("ISHCHEM METOD 'OTCHET O VHOZHDENII V BLYUDO'")
print("="*80)

# Вариант 1: Попробуем получить все блюда и их составы через /products
print("\n[VARIANT 1] Probуem /products s includeDeleted i druge parametry...")

test_params = [
    {"key": api.token, "includeDeleted": "false"},
    {"key": api.token, "type": "DISH"},
    {"key": api.token, "withModifiers": "true"},
]

for params in test_params:
    try:
        response = requests.get(f"{api.base_url}/products", params=params, timeout=10)
        print(f"\n  Params: {params}")
        print(f"  Status: {response.status_code}")

        if response.status_code == 200:
            # Парсим XML чтобы посмотреть структуру
            root = ET.fromstring(response.content)

            # Ищем есть ли информация о составе (items, ingredients, components)
            sample = root.find('.//productDto')
            if sample is not None:
                print(f"  Sample product fields:")
                for child in list(sample)[:10]:  # Первые 10 полей
                    print(f"    - {child.tag}: {child.text[:50] if child.text else 'None'}")

                # Ищем поля связанные с составом
                composition_fields = [child.tag for child in sample if any(x in child.tag.lower() for x in ['item', 'ingredient', 'component', 'child', 'composition'])]
                if composition_fields:
                    print(f"  [!] Found composition fields: {composition_fields}")

    except Exception as e:
        print(f"  Error: {e}")

# Вариант 2: POST запрос
print("\n\n[VARIANT 2] Probуem POST /products...")

try:
    response = requests.post(
        f"{api.base_url}/products",
        params={"key": api.token},
        json={"productId": keg_id},
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    print(f"  Status: {response.status_code}")
    if response.status_code == 200:
        print(f"  Response: {response.text[:500]}")
    else:
        print(f"  Error: {response.text[:200]}")
except Exception as e:
    print(f"  Error: {e}")

# Вариант 3: Пробуем endpoint /corporation/products или другие
print("\n\n[VARIANT 3] Probуem drugiye endpointy...")

other_endpoints = [
    f"/corporation/products?productId={keg_id}",
    f"/productUsage?productId={keg_id}",
    "/product/usage",
    "/corporation/dishes",
]

for endpoint in other_endpoints:
    url = f"{api.base_url}{endpoint}"
    params = {"key": api.token}

    print(f"\n  Endpoint: {endpoint}")
    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            print(f"  [OK] Rabotaet!")
            print(f"  Response: {response.text[:300]}")
    except Exception as e:
        print(f"  Error: {e}")

api.logout()

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
print("\nEsli nichego ne nashlos, mozhet byt nado ispolzovat drugoy API (ne resto/api)?")
print("Ili ispolzovat ruchnoy mapping na osnove nazvaniy?")
