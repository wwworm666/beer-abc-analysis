"""
Проверка разливного пива в номенклатуре
"""
from core.olap_reports import OlapReports
import xml.etree.ElementTree as ET

print("Анализируем разливное пиво в номенклатуре\n")

olap = OlapReports()
if not olap.connect():
    print("Не удалось подключиться к API")
    exit()

import requests
url = f"{olap.api.base_url}/products"
params = {"key": olap.token}

response = requests.get(url, params=params, timeout=30)

if response.status_code == 200:
    root = ET.fromstring(response.text)

    # Ищем DISH с единицей измерения "л"
    draft_beers = []

    for product_el in root.findall('productDto'):
        product_type = product_el.find('productType')
        main_unit = product_el.find('mainUnit')
        name = product_el.find('name')
        category = product_el.find('productCategory')

        if (product_type is not None and product_type.text == 'DISH' and
            main_unit is not None and main_unit.text == 'л'):

            beer_name = name.text if name is not None else 'Unknown'
            beer_category = category.text if category is not None else 'Unknown'

            # Пропускаем ВО
            if 'ВО' not in beer_name:
                draft_beers.append({
                    'name': beer_name,
                    'category': beer_category
                })

    print(f"Найдено разливного пива (DISH + литры, без ВО): {len(draft_beers)}\n")

    if draft_beers:
        print("Первые 30 позиций:")
        for i, beer in enumerate(draft_beers[:30], 1):
            print(f"{i}. {beer['name']}")
            print(f"   Категория: {beer['category']}")
    else:
        print("Разливное пиво не найдено!")
        print("\nПроверяем что есть с типом DISH:")

        dish_count = 0
        for product_el in root.findall('productDto'):
            product_type = product_el.find('productType')
            if product_type is not None and product_type.text == 'DISH':
                dish_count += 1
                if dish_count <= 10:
                    name = product_el.find('name')
                    unit = product_el.find('mainUnit')
                    print(f"  {name.text if name is not None else 'N/A'} ({unit.text if unit is not None else 'N/A'})")

        print(f"\nВсего DISH: {dish_count}")

else:
    print(f"Ошибка получения номенклатуры: {response.status_code}")

olap.disconnect()
