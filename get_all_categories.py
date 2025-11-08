"""
Получить список всех категорий (поставщиков) из номенклатуры
"""
from core.olap_reports import OlapReports
import xml.etree.ElementTree as ET

print("Получаю список всех поставщиков из номенклатуры\n")

# Подключаемся к API
olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

# Получаем номенклатуру
import requests
url = f"{olap.api.base_url}/products"
params = {"key": olap.token}

response = requests.get(url, params=params, timeout=30)

if response.status_code == 200:
    # Парсим XML
    root = ET.fromstring(response.text)

    # Собираем уникальные категории
    categories = {}

    for product_el in root.findall('productDto'):
        product_category = product_el.find('productCategory')
        product_type = product_el.find('productType')

        if product_category is not None and product_category.text:
            cat = product_category.text
            ptype = product_type.text if product_type is not None else 'Unknown'

            if cat not in categories:
                categories[cat] = {'GOODS': 0, 'DISH': 0, 'OTHER': 0}

            if ptype == 'GOODS':
                categories[cat]['GOODS'] += 1
            elif ptype == 'DISH':
                categories[cat]['DISH'] += 1
            else:
                categories[cat]['OTHER'] += 1

    print(f"Всего категорий (поставщиков): {len(categories)}\n")
    print("=" * 80)
    print(f"{'Категория (поставщик)':<50} {'ТОВАРЫ':<10} {'БЛЮДА':<10} {'ПРОЧЕЕ':<10}")
    print("=" * 80)

    for cat in sorted(categories.keys()):
        goods = categories[cat]['GOODS']
        dishes = categories[cat]['DISH']
        other = categories[cat]['OTHER']
        print(f"{cat:<50} {goods:<10} {dishes:<10} {other:<10}")

    print("=" * 80)
    print("\nЛегенда:")
    print("ТОВАРЫ (GOODS) - сырьё, ингредиенты, продукты")
    print("БЛЮДА (DISH) - готовые блюда (обычно разливное пиво)")
    print("ПРОЧЕЕ (OTHER) - модификаторы, услуги и т.д.")

else:
    print(f"Ошибка получения номенклатуры: {response.status_code}")

olap.disconnect()
