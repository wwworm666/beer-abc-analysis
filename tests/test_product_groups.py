"""
Скрипт для анализа групп товаров в номенклатуре
"""
from core.olap_reports import OlapReports
import xml.etree.ElementTree as ET

print("Анализируем группы товаров в номенклатуре\n")

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

    # Собираем статистику по группам
    groups = {}
    product_types = {}
    categories = {}

    for product_el in root.findall('productDto'):
        # Извлекаем поля
        product_type = product_el.find('productType')
        product_category = product_el.find('productCategory')
        parent_id = product_el.find('parentId')
        name = product_el.find('name')

        # Статистика по типам
        if product_type is not None:
            type_val = product_type.text or 'None'
            product_types[type_val] = product_types.get(type_val, 0) + 1

        # Статистика по категориям
        if product_category is not None:
            cat_val = product_category.text or 'None'
            categories[cat_val] = categories.get(cat_val, 0) + 1

    print(f"Всего товаров: {len(root.findall('productDto'))}\n")

    print("=== ТИПЫ ТОВАРОВ (productType) ===")
    for ptype, count in sorted(product_types.items(), key=lambda x: -x[1]):
        print(f"{ptype}: {count}")

    print("\n=== КАТЕГОРИИ ТОВАРОВ (productCategory) ===")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"{cat}: {count}")

    # Ищем товары с группой "Еда" или похожей
    print("\n=== ПОИСК ГРУППЫ 'ЕДА' ===")
    food_keywords = ['еда', 'food', 'продукт', 'ingredient']

    food_found = False
    for cat in categories.keys():
        if any(keyword in cat.lower() for keyword in food_keywords):
            print(f"Найдена категория: {cat} ({categories[cat]} товаров)")
            food_found = True

    if not food_found:
        print("Категория 'Еда' не найдена напрямую")
        print("\nВозможно, нужно исключать категории с напитками/пивом:")
        beer_keywords = ['пиво', 'beer', 'напит', 'drink', 'спб', 'невский', 'фёст']
        print("\nКатегории БЕЗ пива/напитков:")
        for cat in sorted(categories.keys()):
            if not any(keyword in cat.lower() for keyword in beer_keywords):
                print(f"  - {cat}: {categories[cat]} товаров")

else:
    print(f"Ошибка получения номенклатуры: {response.status_code}")

olap.disconnect()
