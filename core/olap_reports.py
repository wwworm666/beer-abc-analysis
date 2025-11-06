import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
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
        if bar_name:
            print(f"   Bar: {bar_name}")
        else:
            print(f"   Bar: VSE")

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
                print(f"[DEBUG] Response length: {len(response.text)} bytes")

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
                "DishAmountInt",
                "DishDiscountSumInt",
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
                "DishAmountInt",
                "DishDiscountSumInt",
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


# Тестовый запуск
if __name__ == "__main__":
    print("🍺 Тестируем получение OLAP отчета по пиву\n")
    
    # Создаем объект для работы с отчетами
    olap = OlapReports()
    
    # Подключаемся
    if not olap.connect():
        print("❌ Не удалось подключиться к API")
        exit()
    
    # Запрашиваем отчет за последние 30 дней
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
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