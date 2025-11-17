"""
Скрипт для анализа групп товаров через поле parentId
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
    print("АНАЛИЗ ГРУПП ТОВАРОВ (parentId)")
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

        # Собираем все товары и группы
        products_by_parent = {}
        all_parent_ids = set()
        product_details = {}

        for product_el in root.findall('productDto'):
            product_id_el = product_el.find('id')
            parent_id_el = product_el.find('parentId')
            name_el = product_el.find('name')
            product_type_el = product_el.find('productType')
            main_unit_el = product_el.find('mainUnit')
            product_group_type_el = product_el.find('productGroupType')

            if product_id_el is not None:
                product_id = product_id_el.text
                parent_id = parent_id_el.text if parent_id_el is not None else None
                name = name_el.text if name_el is not None else ''
                product_type = product_type_el.text if product_type_el is not None else ''
                main_unit = main_unit_el.text if main_unit_el is not None else ''
                group_type = product_group_type_el.text if product_group_type_el is not None else ''

                product_details[product_id] = {
                    'name': name,
                    'parent_id': parent_id,
                    'type': product_type,
                    'unit': main_unit,
                    'group_type': group_type
                }

                if parent_id:
                    all_parent_ids.add(parent_id)
                    if parent_id not in products_by_parent:
                        products_by_parent[parent_id] = []
                    products_by_parent[parent_id].append(product_id)

        print(f"\n[OK] Всего товаров: {len(product_details)}")
        print(f"[OK] Уникальных родительских групп: {len(all_parent_ids)}")

        # Находим товары, которые являются группами (у них есть дети)
        group_products = {}
        for parent_id, children in products_by_parent.items():
            if parent_id in product_details:
                group_products[parent_id] = {
                    'name': product_details[parent_id]['name'],
                    'children_count': len(children),
                    'group_type': product_details[parent_id]['group_type']
                }

        print(f"[OK] Групп (товаров с детьми): {len(group_products)}\n")

        # Показываем группы
        print("ТОП-20 ГРУПП ПО КОЛИЧЕСТВУ ТОВАРОВ:")
        print("-" * 80)

        sorted_groups = sorted(group_products.items(), key=lambda x: x[1]['children_count'], reverse=True)

        for i, (group_id, group_info) in enumerate(sorted_groups[:20], 1):
            print(f"\n{i}. {group_info['name']}")
            print(f"   ID: {group_id}")
            print(f"   Тип группы: {group_info['group_type']}")
            print(f"   Товаров в группе: {group_info['children_count']}")

            # Показываем несколько примеров из этой группы
            children = products_by_parent[group_id][:3]
            for child_id in children:
                child = product_details[child_id]
                print(f"     - {child['name']} (тип: {child['type']}, ед: {child['unit']})")

        # Ищем группу "фасовка" или похожие
        print("\n" + "="*80)
        print("ПОИСК ГРУППЫ 'ФАСОВКА' ИЛИ ПОХОЖИХ")
        print("="*80)

        fasovka_groups = []
        for group_id, group_info in group_products.items():
            name_lower = group_info['name'].lower()
            if any(keyword in name_lower for keyword in ['фасов', 'бутыл', 'bottle', 'pack']):
                fasovka_groups.append({
                    'id': group_id,
                    'name': group_info['name'],
                    'count': group_info['children_count'],
                    'group_type': group_info['group_type']
                })

        if fasovka_groups:
            print(f"\nНайдено групп: {len(fasovka_groups)}\n")
            for group in fasovka_groups:
                print(f"- {group['name']}")
                print(f"  ID: {group['id']}")
                print(f"  Тип группы: {group['group_type']}")
                print(f"  Товаров: {group['count']}\n")

                # Показываем все товары из этой группы
                children = products_by_parent[group['id']]
                print(f"  Товары в группе:")
                for child_id in children[:10]:
                    child = product_details[child_id]
                    print(f"    - {child['name']} (тип: {child['type']}, ед: {child['unit']})")
        else:
            print("\n[НЕ НАЙДЕНО] Группы со словом 'фасовка' не найдены")

        # Ищем группу "пиво" или похожие
        print("\n" + "="*80)
        print("ПОИСК ГРУПП СО СЛОВОМ 'ПИВО'")
        print("="*80)

        beer_groups = []
        for group_id, group_info in group_products.items():
            name_lower = group_info['name'].lower()
            if any(keyword in name_lower for keyword in ['пив', 'beer']):
                beer_groups.append({
                    'id': group_id,
                    'name': group_info['name'],
                    'count': group_info['children_count'],
                    'group_type': group_info['group_type']
                })

        if beer_groups:
            print(f"\nНайдено групп: {len(beer_groups)}\n")
            for group in beer_groups:
                print(f"- {group['name']}")
                print(f"  ID: {group['id']}")
                print(f"  Тип группы: {group['group_type']}")
                print(f"  Товаров: {group['count']}\n")

                # Показываем все товары из этой группы
                children = products_by_parent[group['id']]
                print(f"  Первые 15 товаров:")
                for child_id in children[:15]:
                    child = product_details[child_id]
                    print(f"    - {child['name']} (тип: {child['type']}, ед: {child['unit']})")
                print()

        # Анализ товаров GOODS + шт без группы
        print("\n" + "="*80)
        print("ТОВАРЫ GOODS + ШТ БЕЗ ГРУППЫ")
        print("="*80)

        no_parent_goods = []
        for product_id, details in product_details.items():
            if (details['type'] == 'GOODS' and
                details['unit'] == 'шт' and
                not details['parent_id']):
                no_parent_goods.append(details['name'])

        print(f"\nТоваров без родительской группы: {len(no_parent_goods)}")
        if no_parent_goods:
            print("\nПримеры (первые 20):")
            for i, name in enumerate(no_parent_goods[:20], 1):
                print(f"{i}. {name}")

    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

    olap.disconnect()
    print("\n" + "="*80)

if __name__ == '__main__':
    main()
