"""
Проверяем какие поля доступны для товаров в iiko API
Включая штрихкоды, если они есть
"""

import sys
sys.path.insert(0, 'core')

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
print("PROVERYAEM STRUKTURU DANNYKH PRODUKTOV")
print("="*80)

try:
    response = requests.get(url, params=params)

    if response.status_code == 200:
        print(f"[OK] Polucheny dannye!")

        # Парсим XML
        root = ET.fromstring(response.content)

        # Берём первый товар для примера
        first_product = root.find('.//productDto')

        if first_product is not None:
            print("\n" + "="*80)
            print("VSE DOSTUPNYE POLYA DLYA PERVOGO TOVARA:")
            print("="*80)

            fields = {}
            for child in first_product:
                tag = child.tag
                text = child.text if child.text else '(empty)'
                fields[tag] = text
                print(f"{tag}: {text[:100]}")

            # Сохраняем структуру
            with open('data/product_structure.json', 'w', encoding='utf-8') as f:
                json.dump(fields, f, indent=2, ensure_ascii=False)
            print("\n[SAVED] data/product_structure.json")

        # Ищем товар с кегой для примера
        print("\n" + "="*80)
        print("PRIMER KEGI:")
        print("="*80)

        for product in root.findall('.//productDto'):
            name_elem = product.find('name')
            if name_elem is not None and name_elem.text:
                name = name_elem.text
                if 'КЕГ' in name.upper() or 'KEG' in name.upper():
                    print(f"\nNazvaniye: {name}")
                    keg_fields = {}
                    for child in product:
                        tag = child.tag
                        text = child.text if child.text else '(empty)'
                        keg_fields[tag] = text
                        if tag.lower() in ['barcode', 'code', 'num', 'id']:
                            print(f"  {tag}: {text}")

                    # Сохраняем
                    with open('data/keg_example.json', 'w', encoding='utf-8') as f:
                        json.dump(keg_fields, f, indent=2, ensure_ascii=False)
                    print("\n[SAVED] data/keg_example.json")
                    break

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
print("\nESLI UVIDIT E 'barcode' ILI 'code' - ETO I EST SHTRIKHKOD")
