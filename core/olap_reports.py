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
                headers=headers,
                timeout=30
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
                headers=headers,
                timeout=30
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
                headers=headers,
                timeout=30
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
                headers=headers,
                timeout=30
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

    def get_all_sales_report(self, date_from, date_to, bar_name=None):
        """
        Получить КОМПЛЕКСНЫЙ OLAP отчет по всем продажам (розлив + фасовка + кухня) за ОДИН запрос.
        Оптимизация: 1 HTTP запрос вместо 3 параллельных.

        Args:
            date_from: дата начала (строка 'YYYY-MM-DD')
            date_to: дата окончания (строка 'YYYY-MM-DD')
            bar_name: название бара (если None, то все бары)

        Returns:
            dict с полем 'data' содержащим все записи.
            Каждая запись содержит поле 'DishGroup.TopParent' для разделения категорий:
            - "Напитки Розлив" - разливное пиво
            - "Напитки Фасовка" - фасованное пиво
            - прочие - кухня
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[OLAP] Zaprashivayu kompleksny OLAP otchet (razliv + fasovka + kukhnya)...")
        print(f"   Period: {date_from} - {date_to}")
        if bar_name:
            print(f"   Bar: {bar_name}")
        else:
            print(f"   Bar: VSE")

        # Формируем JSON запрос БЕЗ фильтрации по категориям (получим всё сразу)
        request_body = self._build_all_sales_olap_request(date_from, date_to, bar_name)

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url,
                params=params,
                json=request_body,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                total_records = len(data.get('data', []))
                print(f"[OK] Kompleksny otchet uspeshno poluchen! ({total_records} zapisey)")
                return data
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
                "ProductCostBase.OneItem",  # Себестоимость единицы товара
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

    def _build_all_sales_olap_request(self, date_from, date_to, bar_name=None):
        """
        Построить JSON запрос для комплексного OLAP отчета (все категории за один запрос).
        НЕ фильтрует по DishGroup.TopParent - получаем всё: розлив + фасовку + кухню.
        """

        request = {
            "reportType": "SALES",
            "groupByRowFields": [
                "Store.Name",
                "DishName",
                "DishGroup.TopParent",  # ВАЖНО: нужно для разделения категорий
                "DishForeignName",
                "OpenDate.Typed",
                "UniqOrderId.Id"  # КЛЮЧЕВОЕ: уникальный ID заказа для подсчета чеков
            ],
            "groupByColFields": [],
            "aggregateFields": [
                "UniqOrderId.OrdersCount",  # Количество уникальных заказов (чеков)
                "DishAmountInt",
                "DishDiscountSumInt",
                "DiscountSum",  # Сумма скидки (для списаний баллов)
                "ProductCostBase.ProductCost",
                "ProductCostBase.OneItem",  # Себестоимость единицы товара
                "ProductCostBase.MarkUp"
            ],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": f"{date_from}",
                    "to": f"{date_to}"
                },
                # НЕ фильтруем по DishGroup.TopParent - получаем ВСЁ
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
                "ProductCostBase.OneItem",  # Себестоимость единицы товара
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

    # ============ Методы для дашборда сотрудника ============

    def get_bottles_sales_by_waiter_report(self, date_from, date_to, bar_name=None):
        """
        Получить OLAP отчет по продажам фасованного пива с информацией об официантах

        date_from: дата начала (строка 'YYYY-MM-DD')
        date_to: дата окончания (строка 'YYYY-MM-DD')
        bar_name: название бара (если None, то все бары)
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[OLAP] Zaprashivayu OLAP otchet po fasovke s oficiantami...")
        print(f"   Period: {date_from} - {date_to}")
        if bar_name:
            print(f"   Bar: {bar_name}")
        else:
            print(f"   Bar: VSE")

        # Формируем JSON запрос для OLAP v2 (фасовка + официанты)
        request_body = self._build_olap_request(date_from, date_to, bar_name, draft=False, include_waiter=True)

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url,
                params=params,
                json=request_body,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                print("[OK] Otchet po fasovke s oficiantami uspeshno poluchen!")
                return response.json()
            else:
                print(f"[ERROR] Oshibka polucheniya otcheta: {response.status_code}")
                print(f"   Otvet servera: {response.text}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def get_kitchen_sales_by_waiter_report(self, date_from, date_to, bar_name=None):
        """
        Получить OLAP отчет по продажам кухни с информацией об официантах

        date_from: дата начала (строка 'YYYY-MM-DD')
        date_to: дата окончания (строка 'YYYY-MM-DD')
        bar_name: название бара (если None, то все бары)
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[OLAP] Zaprashivayu OLAP otchet po kukhne s oficiantami...")
        print(f"   Period: {date_from} - {date_to}")
        if bar_name:
            print(f"   Bar: {bar_name}")
        else:
            print(f"   Bar: VSE")

        # Формируем JSON запрос для OLAP v2 (кухня + официанты)
        request_body = self._build_kitchen_olap_request_with_waiter(date_from, date_to, bar_name)

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url,
                params=params,
                json=request_body,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                print("[OK] Otchet po kukhne s oficiantami uspeshno poluchen!")
                return response.json()
            else:
                print(f"[ERROR] Oshibka polucheniya otcheta: {response.status_code}")
                print(f"   Otvet servera: {response.text}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def get_cancelled_orders_by_waiter(self, date_from, date_to, bar_name=None):
        """
        Получить OLAP отчет по отмененным/возвращенным позициям с информацией об официантах

        date_from: дата начала (строка 'YYYY-MM-DD')
        date_to: дата окончания (строка 'YYYY-MM-DD')
        bar_name: название бара (если None, то все бары)
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[OLAP] Zaprashivayu OLAP otchet po otmenam/vozvratam...")
        print(f"   Period: {date_from} - {date_to}")
        if bar_name:
            print(f"   Bar: {bar_name}")
        else:
            print(f"   Bar: VSE")

        # Формируем JSON запрос для OLAP v2 (отмены + официанты)
        request_body = self._build_cancelled_orders_request(date_from, date_to, bar_name)

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url,
                params=params,
                json=request_body,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                print("[OK] Otchet po otmenam/vozvratam uspeshno poluchen!")
                return response.json()
            else:
                print(f"[ERROR] Oshibka polucheniya otcheta: {response.status_code}")
                print(f"   Otvet servera: {response.text}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def _build_kitchen_olap_request_with_waiter(self, date_from, date_to, bar_name=None):
        """Построить JSON запрос для OLAP отчета по блюдам кухни с информацией об официантах"""

        request = {
            "reportType": "SALES",
            "groupByRowFields": [
                "Store.Name",
                "DishName",
                "DishGroup.TopParent",
                "DishForeignName",
                "OpenDate.Typed",
                "WaiterName"  # Добавляем официанта
            ],
            "groupByColFields": [],
            "aggregateFields": [
                "UniqOrderId",
                "UniqOrderId.OrdersCount",
                "DishAmountInt",
                "DishDiscountSumInt",
                "DiscountSum",
                "ProductCostBase.ProductCost",
                "ProductCostBase.OneItem",
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

        if bar_name:
            request["filters"]["Store.Name"] = {
                "filterType": "IncludeValues",
                "values": [bar_name]
            }

        return request

    def _build_cancelled_orders_request(self, date_from, date_to, bar_name=None):
        """Построить JSON запрос для OLAP отчета по отмененным/возвращенным позициям"""

        request = {
            "reportType": "SALES",
            "groupByRowFields": [
                "WaiterName"
            ],
            "groupByColFields": [],
            "aggregateFields": [
                "OrderNum"  # Количество удалённых чеков
            ],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": f"{date_from}",
                    "to": f"{date_to}"
                },
                # Только удаленные/возвращенные позиции (исключаем NOT_DELETED)
                "DeletedWithWriteoff": {
                    "filterType": "ExcludeValues",
                    "values": ["NOT_DELETED"]
                }
            }
        }

        if bar_name:
            request["filters"]["Store.Name"] = {
                "filterType": "IncludeValues",
                "values": [bar_name]
            }

        return request

    def get_employee_aggregated_metrics(self, date_from, date_to, bar_name=None):
        """
        Получить агрегированные метрики по каждому сотруднику.
        Группировка только по WaiterName - API сам агрегирует данные.

        Возвращает dict с ключами по именам сотрудников:
        {
            "Иван Петров": {
                "UniqOrderId": 435,  # количество уникальных чеков
                "DishDiscountSumInt": 752912.00,  # выручка
                "DiscountSum": 23622.00,  # сумма скидок
                ...
            }
        }
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[OLAP] Zaprashivayu agregirovannye metriki po sotrudnikam...")
        print(f"   Period: {date_from} - {date_to}")
        if bar_name:
            print(f"   Bar: {bar_name}")
        else:
            print(f"   Bar: VSE")

        request = {
            "reportType": "SALES",
            "groupByRowFields": [
                "AuthUser"  # "Авторизовал" — кто пробил чек
            ],
            "groupByColFields": [],
            "aggregateFields": [
                "UniqOrderId",              # ID заказа (нужен для OrdersCount)
                "UniqOrderId.OrdersCount",  # Количество уникальных чеков
                "DishDiscountSumInt",        # Выручка
                "DiscountSum",              # Сумма скидок
                "DishAmountInt"             # Количество блюд
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

        if bar_name:
            request["filters"]["Store.Name"] = {
                "filterType": "IncludeValues",
                "values": [bar_name]
            }

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url,
                params=params,
                json=request,
                headers=headers
            )

            if response.status_code == 200:
                result = response.json()
                print("[OK] Agregirovannye metriki polucheny!")

                # Преобразуем в dict по именам сотрудников (AuthUser = "Авторизовал")
                employees_data = {}
                for record in result.get('data', []):
                    auth_user = record.get('AuthUser', '')
                    if auth_user:
                        employees_data[auth_user] = record

                return employees_data
            else:
                print(f"[ERROR] Oshibka: {response.status_code}")
                print(f"   Otvet: {response.text}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def debug_employee_field_names(self, date_from, date_to, employee_name):
        """
        Диагностика: пробует разные поля для группировки по сотруднику,
        чтобы найти правильное название поля для 'Авторизовал'.
        """
        if not self.token:
            return {}

        candidates = [
            "WaiterName",
            "OpenUser", "OpenUser.Name",
            "CloseUser", "CloseUser.Name",
            "Waiter", "Waiter.Name",
            "Employee", "Employee.Name",
            "AuthUser", "OrderCloseUser",
            "User", "User.Name",
        ]
        results = {}

        for field in candidates:
            request = {
                "reportType": "SALES",
                "groupByRowFields": [field],
                "groupByColFields": [],
                "aggregateFields": [
                    "UniqOrderId",
                    "UniqOrderId.OrdersCount",
                    "DishDiscountSumInt",
                ],
                "filters": {
                    "OpenDate.Typed": {
                        "filterType": "DateRange",
                        "periodType": "CUSTOM",
                        "from": date_from,
                        "to": date_to
                    },
                    "DeletedWithWriteoff": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]},
                    "OrderDeleted": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]}
                }
            }

            try:
                import requests as req
                response = req.post(
                    f"{self.api.base_url}/v2/reports/olap",
                    params={"key": self.token},
                    json=request,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    data = response.json().get('data', [])
                    # Ищем запись для нашего сотрудника
                    found = False
                    for record in data:
                        name = record.get(field, '')
                        if employee_name.lower() in (str(name) or '').lower():
                            results[field] = {
                                'found': True,
                                'name_value': name,
                                'UniqOrderId.OrdersCount': record.get('UniqOrderId.OrdersCount'),
                                'DishDiscountSumInt': record.get('DishDiscountSumInt'),
                            }
                            found = True
                            break
                    if not found:
                        # Показываем все значения поля чтобы понять формат
                        results[field] = {
                            'found': False,
                            'total_records': len(data),
                            'all_values': [r.get(field) for r in data]
                        }
                else:
                    results[field] = {'error': f'HTTP {response.status_code}', 'detail': response.text[:200]}
            except Exception as e:
                results[field] = {'error': str(e)}

        return results

    def get_employee_daily_revenue(self, date_from, date_to):
        """
        Получить дневную выручку по каждому сотруднику.
        Группировка по WaiterName + OpenDate.Typed.

        Возвращает dict:
        {
            "Иван Петров": {
                "2026-01-05": 85000.0,
                "2026-01-06": 72000.0,
                ...
            }
        }
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return None

        print(f"\n[OLAP] Zaprashivayu dnevnuyu vyruchku po sotrudnikam...")
        print(f"   Period: {date_from} - {date_to}")

        request = {
            "reportType": "SALES",
            "groupByRowFields": [
                "WaiterName",
                "OpenDate.Typed"
            ],
            "groupByColFields": [],
            "aggregateFields": [
                "DishDiscountSumInt"
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

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url,
                params=params,
                json=request,
                headers=headers
            )

            if response.status_code == 200:
                result = response.json()
                print(f"[OK] Dnevnaya vyruchka poluchena: {len(result.get('data', []))} zapisey")

                # Преобразуем в dict {name: {date: revenue}}
                employees_daily = {}
                for record in result.get('data', []):
                    waiter_name = record.get('WaiterName', '')
                    date_str = record.get('OpenDate.Typed', '')
                    revenue = float(record.get('DishDiscountSumInt', 0) or 0)

                    if waiter_name and date_str:
                        # Нормализуем дату (может прийти как "01.01.2026" или "2026-01-01")
                        if '.' in date_str:
                            parts = date_str.split('.')
                            if len(parts) == 3:
                                date_str = f"{parts[2]}-{parts[1]}-{parts[0]}"

                        if waiter_name not in employees_daily:
                            employees_daily[waiter_name] = {}
                        employees_daily[waiter_name][date_str] = revenue

                return employees_daily
            else:
                print(f"[ERROR] Oshibka: {response.status_code}")
                print(f"   Otvet: {response.text}")
                return None

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return None

    def get_new_loyalty_cards_by_waiter(self, date_from, date_to, bar_name=None):
        """
        Получить количество новых зарегистрированных карт лояльности по сотрудникам.

        Логика: если дата создания клиента попадает в выбранный период,
        значит клиент был зарегистрирован в этот период (по телефону).

        Args:
            date_from: str - начальная дата в формате YYYY-MM-DD
            date_to: str - конечная дата в формате YYYY-MM-DD
            bar_name: str - название бара или None для всех баров

        Returns:
            dict - {waiter_name: count_of_new_cards}
        """
        if not self.token:
            print("[ERROR] Snachala nuzhno podklyuchitsya (vizovite connect())")
            return {}

        print(f"\n[OLAP] Zaprashivayu novye karty loyalnosti (po telefonu)...")
        print(f"   Period: {date_from} - {date_to}")

        # Запрос: группируем по официанту и телефону клиента,
        # фильтруем по дате создания клиента
        request = {
            "reportType": "SALES",
            "groupByRowFields": [
                "WaiterName",
                "Delivery.CustomerPhone"  # Телефон клиента (идентификатор карты лояльности)
            ],
            "groupByColFields": [],
            "aggregateFields": [
                "UniqOrderId.OrdersCount"
            ],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": f"{date_from}",
                    "to": f"{date_to}"
                },
                # Фильтр: дата создания клиента в пределах периода
                "Delivery.CustomerCreatedDateTyped": {
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

        if bar_name:
            request["filters"]["Store.Name"] = {
                "filterType": "IncludeValues",
                "values": [bar_name]
            }

        url = f"{self.api.base_url}/v2/reports/olap"
        params = {"key": self.token}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url,
                params=params,
                json=request,
                headers=headers,
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                print("[OK] Danye po kartam loyalnosti polucheny!")

                # Считаем уникальные телефоны по сотрудникам
                waiter_cards = {}
                for record in result.get('data', []):
                    waiter_name = record.get('WaiterName', '')
                    phone = record.get('Delivery.CustomerPhone', '')

                    if waiter_name and phone:
                        if waiter_name not in waiter_cards:
                            waiter_cards[waiter_name] = set()
                        waiter_cards[waiter_name].add(phone)

                # Преобразуем set в count
                return {name: len(cards) for name, cards in waiter_cards.items()}
            else:
                print(f"[ERROR] Oshibka: {response.status_code}")
                print(f"   Otvet: {response.text}")
                return {}

        except Exception as e:
            print(f"[ERROR] Oshibka: {e}")
            return {}


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
