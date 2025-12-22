#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тест для запроса ВСЕХ возможных данных из iiko API
Пробуем все доступные endpoint'ы
"""

import json
import requests
from core.olap_reports import OlapReports

def test_all_apis():
    """Попробовать все API для получения данных о продукте"""

    print("="*80)
    print("ТЕСТ: Запрос ВСЕХ доступных API iiko")
    print("="*80)

    olap = OlapReports()
    if not olap.connect():
        print("[ERROR] Не удалось подключиться к iiko API")
        return

    base_url = olap.api.base_url
    token = olap.token

    try:
        # ID нашего продукта
        dish_id = "6bc2ca6e-4b30-4fa5-8d04-70fa4b9eccdc"

        print(f"\n{'='*80}")
        print("1. API НОМЕНКЛАТУРЫ (/products)")
        print(f"{'='*80}")

        # Получаем номенклатуру
        nomenclature = olap.get_nomenclature()

        if nomenclature and dish_id in nomenclature:
            product_info = nomenclature[dish_id]
            print(f"\n[OK] Найден продукт в номенклатуре!")
            print(json.dumps(product_info, ensure_ascii=False, indent=2))
        else:
            print(f"[WARN] Продукт {dish_id} не найден в номенклатуре")
            print(f"Всего товаров в номенклатуре: {len(nomenclature) if nomenclature else 0}")

            # Попробуем найти по имени
            if nomenclature:
                for pid, pinfo in nomenclature.items():
                    if pinfo.get('name') and 'Вайнштефан Хефе' in pinfo['name']:
                        print(f"\n[FOUND] Похожий товар: {pid}")
                        print(json.dumps(pinfo, ensure_ascii=False, indent=2))

        # Сохраняем полную номенклатуру
        if nomenclature:
            with open('nomenclature_full.json', 'w', encoding='utf-8') as f:
                json.dump(nomenclature, f, ensure_ascii=False, indent=2)
            print(f"\n[SAVE] Номенклатура сохранена в: nomenclature_full.json")

        print(f"\n{'='*80}")
        print("2. API ПРАЙС-ЛИСТОВ (/priceLists)")
        print(f"{'='*80}")

        # Пробуем получить прайс-листы
        url = f"{base_url}/priceLists"
        params = {"key": token}

        try:
            response = requests.get(url, params=params, timeout=30)
            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                print("[OK] Получены прайс-листы!")

                # Парсим XML
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)

                pricelists = []
                for pl in root.findall('.//priceListDto'):
                    pl_info = {}
                    for child in pl:
                        pl_info[child.tag] = child.text
                    pricelists.append(pl_info)

                print(f"Найдено прайс-листов: {len(pricelists)}")

                # Сохраняем
                with open('pricelists.json', 'w', encoding='utf-8') as f:
                    json.dump(pricelists, f, ensure_ascii=False, indent=2)

                print("Первый прайс-лист:")
                if pricelists:
                    print(json.dumps(pricelists[0], ensure_ascii=False, indent=2))

            else:
                print(f"[ERROR] Ошибка: {response.status_code}")
                print(f"Response: {response.text[:500]}")
        except Exception as e:
            print(f"[ERROR] {e}")

        print(f"\n{'='*80}")
        print("3. API ОСТАТКОВ НА СКЛАДАХ (/v2/reports/balance/stores)")
        print(f"{'='*80}")

        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            moscow_tz = ZoneInfo("Europe/Moscow")
            timestamp = datetime.now(moscow_tz).strftime("%Y-%m-%dT%H:%M:%S")

            url = f"{base_url}/v2/reports/balance/stores"
            params = {
                "key": token,
                "timestamp": timestamp
            }

            response = requests.get(url, params=params, timeout=60)
            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                balance_data = response.json()
                print(f"[OK] Получены остатки!")
                print(f"Всего записей: {len(balance_data.get('balance', []))}")

                # Ищем наш продукт
                found_balances = []
                for item in balance_data.get('balance', []):
                    if dish_id in str(item.get('productId', '')):
                        found_balances.append(item)

                if found_balances:
                    print(f"\n[FOUND] Найдены остатки для продукта:")
                    print(json.dumps(found_balances, ensure_ascii=False, indent=2))
                else:
                    print(f"[WARN] Остатки для продукта {dish_id} не найдены")

                # Сохраняем все остатки
                with open('balance_stores.json', 'w', encoding='utf-8') as f:
                    json.dump(balance_data, f, ensure_ascii=False, indent=2)

            else:
                print(f"[ERROR] Ошибка: {response.status_code}")
                print(f"Response: {response.text[:500]}")
        except Exception as e:
            print(f"[ERROR] {e}")

        print(f"\n{'='*80}")
        print("4. API МЕНЮ (/menu)")
        print(f"{'='*80}")

        try:
            url = f"{base_url}/menu"
            params = {"key": token}

            response = requests.get(url, params=params, timeout=30)
            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                print("[OK] Получено меню!")

                # Парсим XML
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)

                # Ищем наш продукт в меню
                found_items = []
                for item in root.findall('.//productDto'):
                    item_id = item.find('id')
                    if item_id is not None and dish_id in item_id.text:
                        item_info = {}
                        for child in item:
                            item_info[child.tag] = child.text
                        found_items.append(item_info)

                if found_items:
                    print(f"\n[FOUND] Найдено в меню:")
                    print(json.dumps(found_items, ensure_ascii=False, indent=2))
                else:
                    print(f"[WARN] Продукт не найден в меню")

                # Сохраняем полное меню
                with open('menu_full.xml', 'w', encoding='utf-8') as f:
                    f.write(response.text)

            else:
                print(f"[ERROR] Ошибка: {response.status_code}")
                print(f"Response: {response.text[:500]}")
        except Exception as e:
            print(f"[ERROR] {e}")

        print(f"\n{'='*80}")
        print("5. СПИСОК ВСЕХ ДОСТУПНЫХ ENDPOINT'ОВ")
        print(f"{'='*80}")

        endpoints = [
            "/products",
            "/priceLists",
            "/menu",
            "/v2/reports/balance/stores",
            "/priceCategories",
            "/productGroups",
            "/measures",
            "/suppliers",
        ]

        results = {}
        for endpoint in endpoints:
            try:
                url = f"{base_url}{endpoint}"
                params = {"key": token}
                response = requests.get(url, params=params, timeout=10)
                results[endpoint] = {
                    "status": response.status_code,
                    "available": response.status_code == 200
                }
                print(f"{endpoint}: {response.status_code} {'✓' if response.status_code == 200 else '✗'}")
            except Exception as e:
                results[endpoint] = {
                    "status": "error",
                    "error": str(e),
                    "available": False
                }
                print(f"{endpoint}: ERROR - {e}")

        # Сохраняем результаты
        with open('api_endpoints_test.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n{'='*80}")
        print("ИТОГ")
        print(f"{'='*80}")
        print("Все доступные данные сохранены в файлы:")
        print("  - weihenstephan_full_data.json (OLAP продажи)")
        print("  - nomenclature_full.json (Номенклатура)")
        print("  - pricelists.json (Прайс-листы, если доступно)")
        print("  - balance_stores.json (Остатки)")
        print("  - menu_full.xml (Меню)")
        print("  - api_endpoints_test.json (Результаты тестов)")

    finally:
        olap.disconnect()

if __name__ == "__main__":
    test_all_apis()
