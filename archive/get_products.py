"""
Получаем список всех продуктов/товаров из iiko API
Endpoint: /products возвращает список всех товаров включая кеги
"""

from iiko_api import IikoAPI
import requests
import xml.etree.ElementTree as ET
import json

api = IikoAPI()
if not api.authenticate():
    print("[ERROR] Ne udalos podklyuchitsya")
    exit()

url = f"{api.base_url}/products"
params = {"key": api.token}

print("="*80)
print("POLUCHAEM SPISOK VSEH PRODUKTOV/TOVAROV")
print("="*80)

try:
    response = requests.get(url, params=params)

    if response.status_code == 200:
        print(f"[OK] Polucheny dannye!")

        # Парсим XML
        root = ET.fromstring(response.content)

        products = []
        kegs = []

        for product in root.findall('.//productDto'):
            product_id = product.find('id').text if product.find('id') is not None else None
            name = product.find('name').text if product.find('name') is not None else None
            parent_id = product.find('parentId').text if product.find('parentId') is not None else None
            num = product.find('num').text if product.find('num') is not None else None

            product_data = {
                'id': product_id,
                'name': name,
                'parent_id': parent_id,
                'num': num
            }

            products.append(product_data)

            # Ищем кеги
            if name and 'КЕГ' in name.upper():
                kegs.append(product_data)

        print(f"\nVsego produktov: {len(products)}")
        print(f"Iz nih kegov: {len(kegs)}")

        # Сохраняем все продукты
        with open('all_products.json', 'w', encoding='utf-8') as f:
            json.dump(products, f, indent=2, ensure_ascii=False)
        print("[SAVED] all_products.json")

        # Сохраняем только кеги
        with open('kegs_products.json', 'w', encoding='utf-8') as f:
            json.dump(kegs, f, indent=2, ensure_ascii=False)
        print("[SAVED] kegs_products.json")

        # Показываем примеры кегов
        print("\n" + "="*80)
        print("PRIMERY KEGOV:")
        print("="*80)

        for keg in kegs[:15]:
            print(f"\nID: {keg['id']}")
            print(f"Name: {keg['name']}")
            print(f"Num: {keg['num']}")

    else:
        print(f"[ERROR] Status: {response.status_code}")
        print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()

api.logout()

print("\n" + "="*80)
print("GOTOVO!")
print("="*80)
