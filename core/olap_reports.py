import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from core.iiko_api import IikoAPI

class OlapReports:
    """Класс для работы с OLAP отчетами iiko"""
    
    def __init__(self):
        self.api = IikoAPI()
        self.token = None
    
    def connect(self):
        """Подключиться к API и получить токен"""
        if self.api.authenticate():
            self.token = self.api.token
            return True
        return False
    
    def disconnect(self):
        """Отключиться и освободить токен"""
        self.api.logout()

    def get_store_balances(self, timestamp=None):
        """
        Получить остатки товаров на складах (iiko API v2)

        timestamp: дата-время в формате 'YYYY-MM-DDTHH:MM:SS' (если None, то текущее время)

        Возвращает список остатков: [{store, product, amount, sum}, ...]
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        # Если timestamp не указан, используем текущее время в timezone Europe/Moscow
        if not timestamp:
            # Используем московское время (UTC+3)
            moscow_tz = ZoneInfo("Europe/Moscow")
            timestamp = datetime.now(moscow_tz).strftime("%Y-%m-%dT%H:%M:%S")

        print(f"\n[BALANCE] Zaprashivayu ostatki na skladakh...")
        print(f"   Timestamp: {timestamp}")

        url = f"{self.api.base_url}/v2/reports/balance/stores"
        params = {
            "key": self.token,
            "timestamp": timestamp
        }

        try:
            response = requests.get(url, params=params, timeout=60)

            if response.status_code == 200:
                print("[OK] Ostatki uspeshno polucheny!")
                balances = response.json()
                print(f"[OK] Polucheno zapisey: {len(balances)}")
                return balances
            else:
                print(f"[ERROR] Oshibka polucheniya ostatkov: {response.status_code}")
                print(f"   Otvet servera: {response.text[:200]}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def get_nomenclature(self):
        """
        Получить номенклатуру товаров с полной информацией

        Возвращает словарь: {product_guid: {name, type, category, ...}}
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[NOMENCLATURE] Zaprashivayu nomenklaturu tovarov...")

        url = f"{self.api.base_url}/products"
        params = {"key": self.token}

        try:
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 200:
                print("[OK] Nomenklatura uspeshno poluchena!")

                # API возвращает XML, парсим его
                root = ET.fromstring(response.text)

                # Создаем mapping GUID -> полная информация о товаре
                nomenclature = {}
                for product_el in root.findall('productDto'):
                    product_id = product_el.find('id')

                    if product_id is not None:
                        product_info = {
                            'name': product_el.find('name').text if product_el.find('name') is not None else None,
                            'type': product_el.find('productType').text if product_el.find('productType') is not None else None,
                            'category': product_el.find('productCategory').text if product_el.find('productCategory') is not None else None,
                            'mainUnit': product_el.find('mainUnit').text if product_el.find('mainUnit') is not None else None,
                            'parentId': product_el.find('parentId').text if product_el.find('parentId') is not None else None,
                        }
                        nomenclature[product_id.text] = product_info

                print(f"[OK] Rasparsen XML: {len(nomenclature)} tovarov")
                return nomenclature
            else:
                print(f"[ERROR] Oshibka polucheniya nomenklatury: {response.status_code}")
                print(f"   Otvet servera: {response.text[:200]}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def get_products_in_group(self, parent_group_id, nomenclature=None):
        """
        Рекурсивно получить все товары, входящие в указанную группу

        Args:
            parent_group_id: ID родительской группы
            nomenclature: словарь с номенклатурой (если None, получит автоматически)

        Returns:
            set с ID всех товаров в этой группе и подгруппах
        """
        if nomenclature is None:
            nomenclature = self.get_nomenclature()
            if not nomenclature:
                return set()

        result_ids = set()

        # Проходим по всем товарам и ищем те, у которых parentId = parent_group_id
        for product_id, product_info in nomenclature.items():
            if product_info.get('parentId') == parent_group_id:
                # Если у этого товара есть тип (это реальный товар, а не группа)
                if product_info.get('type'):
                    result_ids.add(product_id)
                else:
                    # Это подгруппа, рекурсивно получаем товары из нее
                    child_ids = self.get_products_in_group(product_id, nomenclature)
                    result_ids.update(child_ids)

        return result_ids

    def get_beer_sales_report(self, date_from, date_to, bar_name=None):
        """
        Получить OLAP отчет по продажам пива

        date_from: дата начала (строка 'YYYY-MM-DD')
        date_to: дата окончания (строка 'YYYY-MM-DD')
        bar_name: название бара (если None, то все бары)
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[OLAP] Zaprashivayu OLAP otchet po prodazham piva...")
        print(f"   Period: {date_from} - {date_to}")
        if bar_name:
            print(f"   Bar: {bar_name}")
        else:
            print(f"   Bar: VSE")

        # Формируем JSON запрос для OLAP v2
        request_body = self._build_olap_request(date_from, date_to, bar_name)

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url,
                params=params,
                json=request_body,
                headers=headers
            )

            if response.status_code == 200:
                print("[OK] Otchet uspeshno poluchen!")
                return response.json()
            else:
                print(f"[ERROR] Oshibka polucheniya otcheta: {response.status_code}")
                print(f"   Otvet servera: {response.text}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def get_draft_sales_report(self, date_from, date_to, bar_name=None):
        """
        Получить OLAP отчет по продажам разливного пива

        date_from: дата начала (строка 'YYYY-MM-DD')
        date_to: дата окончания (строка 'YYYY-MM-DD')
        bar_name: название бара (если None, то все бары)
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[OLAP] Zaprashivayu OLAP otchet po razlivnomu pivu...")
        print(f"   Period: {date_from} - {date_to}")
        if bar_name:
            print(f"   Bar: {bar_name}")
        else:
            print(f"   Bar: VSE")

        # Формируем JSON запрос для OLAP v2 (разливное)
        request_body = self._build_olap_request(date_from, date_to, bar_name, draft=True)

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url,
                params=params,
                json=request_body,
                headers=headers
            )

            if response.status_code == 200:
                print("[OK] Otchet po razlivnomu uspeshno poluchen!")
                return response.json()
            else:
                print(f"[ERROR] Oshibka polucheniya otcheta: {response.status_code}")
                print(f"   Otvet servera: {response.text}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def get_draft_sales_by_waiter_report(self, date_from, date_to, bar_name=None):
        """
        Получить OLAP отчет по продажам разливного пива с информацией об официантах

        date_from: дата начала (строка 'YYYY-MM-DD')
        date_to: дата окончания (строка 'YYYY-MM-DD')
        bar_name: название бара (если None, то все бары)
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[OLAP] Zaprashivayu OLAP otchet po razlivnomu pivu s oficiantami...")
        print(f"   Period: {date_from} - {date_to}")
        if bar_name:
            print(f"   Bar: {bar_name}")
        else:
            print(f"   Bar: VSE")

        # Формируем JSON запрос для OLAP v2 (разливное + официанты)
        request_body = self._build_olap_request(date_from, date_to, bar_name, draft=True, include_waiter=True)

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url,
                params=params,
                json=request_body,
                headers=headers
            )

            if response.status_code == 200:
                print("[OK] Otchet po razlivnomu s oficiiantami uspeshno poluchen!")
                return response.json()
            else:
                print(f"[ERROR] Oshibka polucheniya otcheta: {response.status_code}")
                print(f"   Otvet servera: {response.text}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def get_kitchen_sales_report(self, date_from, date_to, bar_name=None):
        """
        Получить OLAP отчет по продажам блюд кухни (исключая напитки)

        date_from: дата начала (строка 'YYYY-MM-DD')
        date_to: дата окончания (строка 'YYYY-MM-DD')
        bar_name: название бара (если None, то все бары)
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[OLAP] Zaprashivayu OLAP otchet po kukhne...")
        print(f"   Period: {date_from} - {date_to}")
        if bar_name:
            print(f"   Bar: {bar_name}")
        else:
            print(f"   Bar: VSE")

        # Формируем JSON запрос для OLAP v2 (кухня, без напитков)
        request_body = self._build_kitchen_olap_request(date_from, date_to, bar_name)

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url,
                params=params,
                json=request_body,
                headers=headers
            )

            if response.status_code == 200:
                print("[OK] Otchet po kukhne uspeshno poluchen!")
                return response.json()
            else:
                print(f"[ERROR] Oshibka polucheniya otcheta: {response.status_code}")
                print(f"   Otvet servera: {response.text}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None
    
    def get_store_operations_report(self, date_from, date_to, bar_name=None):
        """
        Получить отчет по складским операциям с детализацией по товарам

        date_from: дата начала (строка 'DD.MM.YYYY')
        date_to: дата окончания (строка 'DD.MM.YYYY')
        bar_name: название бара (если None, то все бары)

        Возвращает детализированный отчет по всем складским операциям с товарами
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[STORE] Zaprashivayu otchet po skladskim operaciyam...")
        print(f"   Period: {date_from} - {date_to}")
        # Пропускаем вывод bar_name чтобы избежать проблем с кодировкой

        url = f"{self.api.base_url}/reports/storeOperations"
        params = {
            "key": self.token,
            "dateFrom": date_from,
            "dateTo": date_to,
            "productDetalization": "true"
        }

        # Если указан конкретный бар, добавляем его ID
        # TODO: Нужно будет сделать mapping имени бара в его ID
        # if bar_name:
        #     params["stores"] = bar_id

        try:
            response = requests.get(url, params=params)

            if response.status_code == 200:
                print("[OK] Otchet po skladskim operaciyam uspeshno poluchen!")
                # API возвращает XML, парсим его

                # Парсим XML
                root = ET.fromstring(response.text)

                # Извлекаем данные из XML
                items = []
                for item_el in root.findall('storeReportItemDto'):
                    item = {}
                    # Извлекаем все нужные поля
                    for child in item_el:
                        item[child.tag] = child.text

                    items.append(item)

                print(f"[OK] Rasparsen XML: {len(items)} zapisey")
                return items
            else:
                print(f"[ERROR] Oshibka polucheniya otcheta: {response.status_code}")
                print(f"   Otvet servera: {response.text}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def get_product_expense_report(self, date_from, date_to, department_id=None):
        """
        Получить отчет по расходу продуктов (товаров) по продажам

        date_from: дата начала (строка 'DD.MM.YYYY')
        date_to: дата окончания (строка 'DD.MM.YYYY')
        department_id: GUID подразделения (если None, нужен ID)
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[PRODUCTS] Zaprashivayu otchet po raskhodu produktov...")
        print(f"   Period: {date_from} - {date_to}")

        # TODO: Нужно получить department_id для каждого бара
        # Пока используем заглушку - этот метод требует GUID подразделения
        if not department_id:
            print("[WARNING] Dlya productExpense nuzhen department GUID")
            return None

        url = f"{self.api.base_url}/reports/productExpense"
        params = {
            "key": self.token,
            "department": department_id,
            "dateFrom": date_from,
            "dateTo": date_to
        }

        try:
            response = requests.get(url, params=params)

            if response.status_code == 200:
                print("[OK] Otchet po raskhodu produktov uspeshno poluchen!")
                return response.json()
            else:
                print(f"[ERROR] Oshibka polucheniya otcheta: {response.status_code}")
                print(f"   Otvet servera: {response.text}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def _build_kitchen_olap_request(self, date_from, date_to, bar_name=None):
        """Построить JSON запрос для OLAP отчета по блюдам кухни"""

        request = {
            "reportType": "SALES",
            "groupByRowFields": [
                "Store.Name",
                "DishName",
                "DishGroup.TopParent",
                "DishForeignName",
                "OpenDate.Typed"
            ],
            "groupByColFields": [],
            "aggregateFields": [
                "UniqOrderId",
                "UniqOrderId.OrdersCount",  # Количество уникальных заказов (чеков)
                "DishAmountInt",
                "DishDiscountSumInt",
                "DiscountSum",  # Сумма скидки (для списаний баллов)
                "ProductCostBase.ProductCost",
                "ProductCostBase.MarkUp"
            ],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": f"{date_from}",
                    "to": f"{date_to}"
                },
                "DishGroup.TopParent": {
                    "filterType": "ExcludeValues",
                    "values": ["Напитки Фасовка", "Напитки Розлив"]
                },
                "DeletedWithWriteoff": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"]
                },
                "OrderDeleted": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"]
                }
            }
        }

        # Если указан конкретный бар, добавляем фильтр
        if bar_name:
            request["filters"]["Store.Name"] = {
                "filterType": "IncludeValues",
                "values": [bar_name]
            }

        return request

    def _build_olap_request(self, date_from, date_to, bar_name=None, draft=False, include_waiter=False):
        """Построить JSON запрос для OLAP отчета v2

        draft: True - разливное пиво, False - фасованное пиво
        include_waiter: True - добавить поля с информацией об официантах
        """

        # Определяем группу напитков
        drink_group = "Напитки Розлив" if draft else "Напитки Фасовка"

        # Базовая структура запроса согласно документации
        groupByRowFields = [
            "Store.Name",
            "DishName",
            "DishGroup.ThirdParent",
            "DishForeignName",
            "OpenDate.Typed"
        ]

        # Добавляем поля официантов если требуется
        if include_waiter:
            # ВАЖНО: Используем ТОЛЬКО WaiterName (официант блюда)
            # Добавление OrderWaiter.Name в groupByRowFields создаёт дублирование строк!
            # Если WaiterName и OrderWaiter.Name различаются, OLAP создаст отдельные строки,
            # что приведёт к двойному учёту одних и тех же продаж.
            groupByRowFields.append("WaiterName")

        request = {
            "reportType": "SALES",
            "groupByRowFields": groupByRowFields,
            "groupByColFields": [],
            "aggregateFields": [
                "UniqOrderId",
                "UniqOrderId.OrdersCount",  # Количество уникальных заказов (чеков)
                "DishAmountInt",
                "DishDiscountSumInt",
                "DiscountSum",  # Сумма скидки (для списаний баллов)
                "ProductCostBase.ProductCost",
                "ProductCostBase.MarkUp"
            ],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": f"{date_from}",
                    "to": f"{date_to}"
                },
                "DishGroup.TopParent": {
                    "filterType": "IncludeValues",
                    "values": [drink_group]
                },
                "DeletedWithWriteoff": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"]
                },
                "OrderDeleted": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"]
                }
            }
        }

        # Если указан конкретный бар, добавляем фильтр
        if bar_name:
            request["filters"]["Store.Name"] = {
                "filterType": "IncludeValues",
                "values": [bar_name]
            }

        return request

    def _build_orders_count_request(self, bar_name, date_from, date_to):
        """
        Создать OLAP запрос для подсчета КОЛИЧЕСТВА ЧЕКОВ (заказов)

        ВАЖНО: Этот запрос НЕ группирует по DishName, только по Store.Name и дате.
        Это даёт правильное количество уникальных заказов без дублирования.

        Args:
            bar_name: str - название бара или None для всех баров
            date_from: str - начальная дата в формате YYYY-MM-DD
            date_to: str - конечная дата в формате YYYY-MM-DD

        Returns:
            dict - OLAP запрос для подсчета заказов
        """
        # Группируем ТОЛЬКО по бару и дате, БЕЗ DishName!
        groupByRowFields = [
            "Store.Name",
            "OpenDate.Typed"
        ]

        request = {
            "reportType": "SALES",
            "groupByRowFields": groupByRowFields,
            "groupByColFields": [],
            "aggregateFields": [
                "UniqOrderId.OrdersCount"  # Количество уникальных заказов
            ],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": f"{date_from}",
                    "to": f"{date_to}"
                },
                "DeletedWithWriteoff": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"]
                },
                "OrderDeleted": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"]
                }
            }
        }

        # Если указан конкретный бар, добавляем фильтр
        if bar_name:
            request["filters"]["Store.Name"] = {
                "filterType": "IncludeValues",
                "values": [bar_name]
            }

        return request

    def get_orders_count(self, bar_name, date_from, date_to):
        """
        Получить количество заказов (чеков) за период

        Args:
            bar_name: str - название бара или None для всех баров
            date_from: str - начальная дата в формате YYYY-MM-DD
            date_to: str - конечная дата в формате YYYY-MM-DD

        Returns:
            int - количество уникальных заказов
        """
        request = self._build_orders_count_request(bar_name, date_from, date_to)

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, params=params, json=request, headers=headers, timeout=60)

            if response.status_code == 200:
                result = response.json()
                # Суммируем количество заказов из всех записей
                total_orders = 0
                for record in result.get('data', []):
                    orders = record.get('UniqOrderId.OrdersCount', 0)
                    total_orders += int(orders) if orders else 0

                return total_orders
            else:
                print(f"[ERROR] OLAP orders count request failed: {response.status_code}")
                print(f"[ERROR] Response: {response.text}")
                return 0

        except Exception as e:
            print(f"[ERROR] Failed to get orders count: {e}")
            return 0


# Тестовый запуск
if __name__ == "__main__":
    print("🍺 Тестируем получение OLAP отчета по пиву\n")
    
    # Создаем объект для работы с отчетами
    olap = OlapReports()
    
    # Подключаемся
    if not olap.connect():
        print("❌ Не удалось подключиться к API")
        exit()
    
    # Запрашиваем отчет за последние 30 дней (московское время)
    moscow_tz = ZoneInfo("Europe/Moscow")
    now_moscow = datetime.now(moscow_tz)
    date_to = now_moscow.strftime("%Y-%m-%d")
    date_from = (now_moscow - timedelta(days=30)).strftime("%Y-%m-%d")
    
    # Получаем отчет
    report_data = olap.get_beer_sales_report(date_from, date_to)
    
    if report_data:
        # Сохраняем в файл для просмотра
        with open("beer_report.json", "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        print("\n📄 Отчет сохранен в файл: beer_report.json")
        print("   Откройте его чтобы посмотреть структуру данных")
        
        # Покажем первые несколько записей
        if "data" in report_data and len(report_data["data"]) > 0:
            print(f"\n📊 Получено записей: {len(report_data['data'])}")
            print("\nПервые 3 записи:")
            for i, record in enumerate(report_data["data"][:3], 1):
                print(f"\n{i}. {record}")
    
    # Отключаемся
    olap.disconnect()
    print("\n✅ Готово!")
    def get_orders_count_report(self, date_from, date_to, bar_name=None):
        """
        Получить OLAP отчет с подсчётом уникальных заказов (чеков)
        Без группировки по товарам - только общее количество заказов

        date_from: дата начала (строка 'YYYY-MM-DD')
        date_to: дата окончания (строка 'YYYY-MM-DD')
        bar_name: название бара (если None, то все бары)
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[OLAP] Zaprashivayu OLAP otchet po kolichestvu chekov...")
        print(f"   Period: {date_from} - {date_to}")
        if bar_name:
            print(f"   Bar: {bar_name}")

        # Запрос без группировки по DishName - только Store.Name и OpenDate.Typed
        # Это даст общее количество уникальных заказов за каждый день
        request = {
            "reportType": "SALES",
            "groupByRowFields": [
                "Store.Name",
                "OpenDate.Typed"
            ],
            "groupByColFields": [],
            "aggregateFields": [
                "UniqOrderId.OrdersCount"  # Количество уникальных заказов
            ],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": f"{date_from}",
                    "to": f"{date_to}"
                },
                "DeletedWithWriteoff": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"]
                },
                "OrderDeleted": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"]
                }
            }
        }

        # Если указан конкретный бар, добавляем фильтр
        if bar_name:
            request["filters"]["Store.Name"] = {
                "filterType": "IncludeValues",
                "values": [bar_name]
            }

        # Выполняем запрос к OLAP v2
        return self._execute_olap_request(request)
