"""
Скрипт для отладки - выводит все уникальные категории товаров из iiko
"""
from core.olap_reports import OlapReports
from datetime import datetime, timedelta

def main():
    # Подключаемся к iiko
    olap = OlapReports()
    if not olap.connect():
        print("[ERROR] Не удалось подключиться к iiko API")
        return

    print("\n" + "="*60)
    print("ПОЛУЧЕНИЕ УНИКАЛЬНЫХ КАТЕГОРИЙ ТОВАРОВ")
    print("="*60)

    # Получаем номенклатуру
    nomenclature = olap.get_nomenclature()
    if not nomenclature:
        print("[ERROR] Не удалось получить номенклатуру")
        olap.disconnect()
        return

    print(f"\n[OK] Получено товаров: {len(nomenclature)}")

    # Собираем все уникальные категории
    categories = set()
    for product_id, product_info in nomenclature.items():
        category = product_info.get('category')
        if category:
            categories.add(category)

    # Сортируем и выводим
    print(f"\n[OK] Найдено уникальных категорий: {len(categories)}\n")
    print("Список всех категорий:")
    print("-" * 60)

    for i, category in enumerate(sorted(categories), 1):
        print(f"{i:3}. {category}")

    # Ищем категории со словом "пиво" или похожие
    print("\n" + "="*60)
    print("КАТЕГОРИИ СОДЕРЖАЩИЕ 'ПИВ' ИЛИ 'BEER':")
    print("="*60)

    beer_categories = [cat for cat in categories if 'пив' in cat.lower() or 'beer' in cat.lower()]
    for cat in sorted(beer_categories):
        print(f"  - {cat}")

    # Ищем категории со словом "фасов"
    print("\n" + "="*60)
    print("КАТЕГОРИИ СОДЕРЖАЩИЕ 'ФАСОВ' ИЛИ 'BOTTLE':")
    print("="*60)

    bottle_categories = [cat for cat in categories if 'фасов' in cat.lower() or 'bottle' in cat.lower()]
    if bottle_categories:
        for cat in sorted(bottle_categories):
            print(f"  - {cat}")
    else:
        print("  [НЕ НАЙДЕНО]")

    olap.disconnect()
    print("\n" + "="*60)

if __name__ == '__main__':
    main()
