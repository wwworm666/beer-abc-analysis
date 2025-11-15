"""
Ищем конкретно КЕГ Brewlok IPA и проверяем есть ли штрихкод
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
print("ISHEM KEG BREWLOK IPA")
print("="*80)

try:
    response = requests.get(url, params=params)

    if response.status_code == 200:
        print(f"[OK] Polucheny dannye!")

        # Парсим XML
        root = ET.fromstring(response.content)

        found = False
        for product in root.findall('.//productDto'):
            name_elem = product.find('name')
            if name_elem is not None and name_elem.text:
                name = name_elem.text

                # Ищем Brewlok IPA
                if 'brewlok' in name.lower() and 'ipa' in name.lower():
                    print(f"\n{'='*80}")
                    print(f"NAYDENO: {name}")
                    print("="*80)

                    product_info = {}

                    # Смотрим все поля
                    for child in product:
                        tag = child.tag
                        text = child.text if child.text else None
                        product_info[tag] = text
                        print(f"{tag}: {text}")

                        # Отдельно смотрим barcodes
                        if tag == 'barcodes':
                            print(f"\n  >>> SHTRIKHKODY:")
                            if text:
                                print(f"      {text}")
                            else:
                                # Может быть вложенная структура
                                barcodes_list = []
                                for barcode in child:
                                    barcode_value = barcode.text if barcode.text else barcode.get('value', '')
                                    if barcode_value:
                                        barcodes_list.append(barcode_value)
                                        print(f"      - {barcode_value}")

                                if barcodes_list:
                                    product_info['barcodes_list'] = barcodes_list
                                else:
                                    print(f"      (net shtrikhkodov)")

                    # Сохраняем
                    with open('data/brewlok_ipa.json', 'w', encoding='utf-8') as f:
                        json.dump(product_info, f, indent=2, ensure_ascii=False)
                    print(f"\n[SAVED] data/brewlok_ipa.json")

                    found = True
                    print("\n")

        if not found:
            print("\n[!] Ne nashli KEG Brewlok IPA")
            print("Vozmozhno nazvanie drugoe. Pokazyvayu vse Brewlok:\n")

            for product in root.findall('.//productDto'):
                name_elem = product.find('name')
                if name_elem is not None and name_elem.text:
                    name = name_elem.text
                    if 'brewlok' in name.lower():
                        print(f"  - {name}")

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
