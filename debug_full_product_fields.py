"""
Скрипт для отладки - показывает ВСЕ доступные поля для товаров из iiko API
"""
from core.olap_reports import OlapReports
import xml.etree.ElementTree as ET

def main():
    # Подключаемся к iiko
    olap = OlapReports()
    if not olap.connect():
        print("[ERROR] Не удалось подключиться к iiko API")
        return

    print("\n" + "="*80)
    print("АНАЛИЗ ВСЕХ ПОЛЕЙ ТОВАРОВ ИЗ iiko API")
    print("="*80)

    # Получаем RAW XML ответ
    import requests
    url = f"{olap.api.base_url}/products"
    params = {"key": olap.token}

    try:
        response = requests.get(url, params=params, timeout=30)

        if response.status_code != 200:
            print(f"[ERROR] Ошибка получения данных: {response.status_code}")
            olap.disconnect()
            return

        # Парсим XML
        root = ET.fromstring(response.text)

        # Собираем ВСЕ уникальные теги из всех товаров
        all_tags = set()
        product_count = 0

        for product_el in root.findall('productDto'):
            product_count += 1
            for child in product_el:
                all_tags.add(child.tag)

        print(f"\n[OK] Всего товаров в системе: {product_count}")
        print(f"[OK] Найдено уникальных полей: {len(all_tags)}\n")

        print("СПИСОК ВСЕХ ДОСТУПНЫХ ПОЛЕЙ:")
        print("-" * 80)
        for i, tag in enumerate(sorted(all_tags), 1):
            print(f"{i:2}. {tag}")

        # Теперь показываем примеры значений для каждого поля
        print("\n" + "="*80)
        print("ПРИМЕРЫ ЗНАЧЕНИЙ ДЛЯ КАЖДОГО ПОЛЯ")
        print("="*80)

        # Берем первые 5 товаров и показываем все их поля
        print("\nПРИМЕР 1: Первый товар в списке")
        print("-" * 80)

        first_product = root.find('productDto')
        if first_product:
            for child in first_product:
                value = child.text or "(пусто)"
                # Ограничиваем длину значения для читаемости
                if len(value) > 100:
                    value = value[:100] + "..."
                print(f"{child.tag:30} = {value}")

        # Ищем пример товара типа GOODS с единицей измерения "шт"
        print("\n" + "="*80)
        print("ПРИМЕР 2: Товар типа GOODS с единицей 'шт' (потенциальная фасовка)")
        print("-" * 80)

        for product_el in root.findall('productDto'):
            product_type_el = product_el.find('productType')
            main_unit_el = product_el.find('mainUnit')

            if (product_type_el is not None and product_type_el.text == 'GOODS' and
                main_unit_el is not None and main_unit_el.text == 'шт'):

                for child in product_el:
                    value = child.text or "(пусто)"
                    if len(value) > 100:
                        value = value[:100] + "..."
                    print(f"{child.tag:30} = {value}")
                break

        # Ищем пример DRAFT BEER (разливное)
        print("\n" + "="*80)
        print("ПРИМЕР 3: Разливное пиво (тип DISH)")
        print("-" * 80)

        for product_el in root.findall('productDto'):
            product_type_el = product_el.find('productType')
            main_unit_el = product_el.find('mainUnit')
            name_el = product_el.find('name')

            if (product_type_el is not None and product_type_el.text == 'DISH' and
                main_unit_el is not None and main_unit_el.text == 'л' and
                name_el is not None and 'кег' in name_el.text.lower()):

                for child in product_el:
                    value = child.text or "(пусто)"
                    if len(value) > 100:
                        value = value[:100] + "..."
                    print(f"{child.tag:30} = {value}")
                break

        # Анализ поля "num" или других потенциальных классификаторов
        print("\n" + "="*80)
        print("АНАЛИЗ ПОТЕНЦИАЛЬНЫХ КЛАССИФИКАТОРОВ")
        print("="*80)

        # Проверяем, есть ли поля, которые могут указывать на группу/категорию
        interesting_fields = ['num', 'code', 'cookingPlaceType', 'group', 'parentGroup',
                             'productCategory', 'category', 'groupId', 'groupName']

        for field in interesting_fields:
            unique_values = set()
            count = 0

            for product_el in root.findall('productDto'):
                field_el = product_el.find(field)
                if field_el is not None and field_el.text:
                    unique_values.add(field_el.text)
                    count += 1

            if count > 0:
                print(f"\n{field}:")
                print(f"  - Товаров с этим полем: {count}")
                print(f"  - Уникальных значений: {len(unique_values)}")

                if len(unique_values) <= 20:
                    print(f"  - Значения: {sorted(unique_values)}")
                else:
                    sample = list(sorted(unique_values))[:10]
                    print(f"  - Примеры (первые 10): {sample}")

        # Ищем товары с кодом или номером, который может указывать на фасовку
        print("\n" + "="*80)
        print("ПОИСК ТОВАРОВ ТИПА GOODS + ШТ С РАЗЛИЧНЫМИ ПОЛЯМИ")
        print("="*80)

        goods_sht = []
        for product_el in root.findall('productDto'):
            product_type_el = product_el.find('productType')
            main_unit_el = product_el.find('mainUnit')

            if (product_type_el is not None and product_type_el.text == 'GOODS' and
                main_unit_el is not None and main_unit_el.text == 'шт'):

                name = product_el.find('name').text if product_el.find('name') is not None else ''
                category = product_el.find('productCategory').text if product_el.find('productCategory') is not None else ''
                num = product_el.find('num').text if product_el.find('num') is not None else ''
                code = product_el.find('code').text if product_el.find('code') is not None else ''

                goods_sht.append({
                    'name': name,
                    'category': category,
                    'num': num,
                    'code': code
                })

        print(f"\nВсего товаров GOODS + шт: {len(goods_sht)}\n")
        print("Первые 20 примеров:")
        print("-" * 80)

        for i, item in enumerate(goods_sht[:20], 1):
            print(f"\n{i}. {item['name']}")
            print(f"   Категория (поставщик): {item['category']}")
            print(f"   Номер: {item['num']}")
            print(f"   Код: {item['code']}")

    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

    olap.disconnect()
    print("\n" + "="*80)

if __name__ == '__main__':
    main()
