import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config import IIKO_BASE_URL, IIKO_LOGIN, IIKO_PASSWORD

class IikoAPI:
    """Класс для работы с iiko API"""
    
    def __init__(self):
        self.base_url = IIKO_BASE_URL
        self.login = IIKO_LOGIN
        self.password = IIKO_PASSWORD
        self.token = None
    
    def get_sha1_hash(self, text):
        """Получить SHA-1 хэш от текста"""
        return hashlib.sha1(text.encode()).hexdigest()
    
    def authenticate(self):
        """Получить токен авторизации"""
        password_hash = self.get_sha1_hash(self.password)
        
        url = f"{self.base_url}/auth"
        params = {
            "login": self.login,
            "pass": password_hash
        }
        
        print(f"[AUTH] Podklyuchaus k {self.base_url}...")

        try:
            response = requests.get(url, params=params)

            if response.status_code == 200:
                # Токен приходит в формате <string>токен</string>
                self.token = response.text.strip().replace("<string>", "").replace("</string>", "")
                print(f"[OK] Uspeshno poluchen token: {self.token[:20]}...")
                return True
            else:
                print(f"[ERROR] Oshibka avtorizacii: {response.status_code}")
                print(f"   Otvet servera: {response.text}")
                return False

        except Exception as e:
            print(f"[ERROR] Oshibka podklyucheniya: {e}")
            return False
    
    def logout(self):
        """Освободить токен (освободить слот лицензии)"""
        if not self.token:
            return

        url = f"{self.base_url}/logout"
        params = {"key": self.token}

        try:
            requests.get(url, params=params)
            print("[OK] Token osvobozhden")
        except:
            pass

    # =====================================================
    # ATTENDANCE API (Явки сотрудников) - DEPRECATED
    # Используйте get_employee_metrics_from_shifts() вместо этого
    # =====================================================

    def get_attendance(
        self,
        date_from: str,
        date_to: str,
        department_id: Optional[str] = None,
        employee_id: Optional[str] = None
    ) -> List[Dict]:
        """
        DEPRECATED: Используйте get_employee_metrics_from_shifts() для получения данных о сменах.

        Attendance API возвращает только "Пивная культура" для всех сотрудников,
        что не позволяет корректно определить место работы.
        Cash Shifts API (/v2/cashshifts) содержит точные данные о локации.

        Получить явки сотрудников за период.

        Args:
            date_from: Дата начала (YYYY-MM-DD)
            date_to: Дата окончания (YYYY-MM-DD)
            department_id: UUID подразделения (опционально)
            employee_id: UUID сотрудника (опционально)

        Returns:
            Список явок с полями: id, employee_id, date, start_time, end_time, duration_minutes
        """
        if not self.token:
            print("[ERROR] Нужна авторизация")
            return []

        # Формируем URL в зависимости от параметров
        if department_id and employee_id:
            url = f"{self.base_url}/employees/attendance/department/{department_id}/byEmployee/{employee_id}/"
        elif department_id:
            url = f"{self.base_url}/employees/attendance/department/{department_id}/"
        elif employee_id:
            url = f"{self.base_url}/employees/attendance/byEmployee/{employee_id}/"
        else:
            url = f"{self.base_url}/employees/attendance"

        params = {
            "key": self.token,
            "from": date_from,
            "to": date_to,
            "withPaymentDetails": "false"
        }

        print(f"[ATTENDANCE] Загружаю явки с {date_from} по {date_to}...")

        try:
            response = requests.get(url, params=params)

            if response.status_code == 200:
                return self._parse_attendance_xml(response.text)
            else:
                print(f"[ERROR] Ошибка получения явок: {response.status_code}")
                print(f"   Ответ: {response.text[:200]}")
                return []

        except Exception as e:
            print(f"[ERROR] Ошибка запроса: {e}")
            return []

    def _parse_attendance_xml(self, xml_text: str) -> List[Dict]:
        """Парсинг XML ответа с явками."""
        attendances = []

        try:
            root = ET.fromstring(xml_text)

            for att in root.findall('.//attendance'):
                attendance = {}

                # ID явки
                id_elem = att.find('id')
                attendance['id'] = id_elem.text if id_elem is not None else None

                # ID сотрудника
                emp_id = att.find('employeeId')
                attendance['employee_id'] = emp_id.text if emp_id is not None else None

                # ID подразделения
                dept_id = att.find('departmentId')
                attendance['department_id'] = dept_id.text if dept_id is not None else None

                # Название подразделения
                dept_name = att.find('departmentName')
                attendance['department_name'] = dept_name.text if dept_name is not None else None

                # Время начала
                date_from = att.find('dateFrom')
                if date_from is not None and date_from.text:
                    dt = self._parse_iso_datetime(date_from.text)
                    if dt:
                        attendance['date'] = dt.strftime('%Y-%m-%d')
                        attendance['start_time'] = dt.strftime('%H:%M')
                        attendance['start_datetime'] = dt

                # Время окончания
                date_to = att.find('dateTo')
                if date_to is not None and date_to.text:
                    dt = self._parse_iso_datetime(date_to.text)
                    if dt:
                        attendance['end_time'] = dt.strftime('%H:%M')
                        attendance['end_datetime'] = dt
                else:
                    # Смена ещё открыта
                    attendance['end_time'] = None
                    attendance['end_datetime'] = None

                # Рассчитываем продолжительность
                if attendance.get('start_datetime') and attendance.get('end_datetime'):
                    delta = attendance['end_datetime'] - attendance['start_datetime']
                    attendance['duration_minutes'] = int(delta.total_seconds() / 60)
                else:
                    attendance['duration_minutes'] = None

                # Убираем datetime объекты (не нужны для графа)
                attendance.pop('start_datetime', None)
                attendance.pop('end_datetime', None)

                attendances.append(attendance)

            print(f"[OK] Загружено {len(attendances)} явок")
            return attendances

        except ET.ParseError as e:
            print(f"[ERROR] Ошибка парсинга XML: {e}")
            return []

    def _parse_iso_datetime(self, iso_str: str) -> Optional[datetime]:
        """Парсинг ISO datetime строки."""
        try:
            # Убираем timezone часть для простоты
            if '+' in iso_str:
                iso_str = iso_str.split('+')[0]
            return datetime.fromisoformat(iso_str)
        except:
            return None

    # =====================================================
    # CASH SHIFTS API (Кассовые смены v2)
    # =====================================================

    def get_cash_shifts(
        self,
        date_from: str,
        date_to: str,
        department_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict]:
        """
        Получить кассовые смены за период.

        Args:
            date_from: Дата начала (YYYY-MM-DD)
            date_to: Дата окончания (YYYY-MM-DD)
            department_id: UUID подразделения (опционально)
            status: Статус смены: OPEN, CLOSED (опционально)

        Returns:
            Список кассовых смен с полями: id, departmentId, pointOfSale, etc.
        """
        if not self.token:
            print("[ERROR] Нужна авторизация")
            return []

        # V2 API для кассовых смен (возвращает JSON)
        url = f"{self.base_url}/v2/cashshifts/list"

        params = {
            "key": self.token,
            "openDateFrom": date_from,
            "openDateTo": date_to
        }

        if department_id:
            params["departmentId"] = department_id
        if status:
            params["status"] = status

        print(f"[CASHSHIFTS] Загружаю кассовые смены с {date_from} по {date_to}...")

        try:
            response = requests.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                shifts = data if isinstance(data, list) else data.get('response', [])
                print(f"[OK] Загружено {len(shifts)} кассовых смен")
                return shifts
            else:
                print(f"[ERROR] Ошибка получения кассовых смен: {response.status_code}")
                print(f"   Ответ: {response.text[:500]}")
                return []

        except Exception as e:
            print(f"[ERROR] Ошибка запроса: {e}")
            return []

    def get_groups_with_pos(self) -> Dict[str, str]:
        """
        Получить маппинг pointOfSaleId -> название группы (торговой точки).

        Returns:
            Dict {point_of_sale_id: group_name}
        """
        if not self.token:
            print("[ERROR] Нужна авторизация")
            return {}

        url = f"{self.base_url}/corporation/groups"
        params = {"key": self.token}

        print("[GROUPS] Загружаю группы (торговые точки)...")

        try:
            response = requests.get(url, params=params)

            if response.status_code == 200:
                pos_mapping = {}
                root = ET.fromstring(response.text)

                for group in root.findall('.//groupDto'):
                    name = group.find('name').text if group.find('name') is not None else 'Unknown'

                    for pos in group.findall('.//pointOfSaleDto'):
                        pos_id = pos.find('id').text if pos.find('id') is not None else None
                        if pos_id:
                            pos_mapping[pos_id] = name

                print(f"[OK] Загружено {len(pos_mapping)} точек продаж")
                return pos_mapping
            else:
                print(f"[ERROR] Ошибка: {response.status_code}")
                return {}

        except Exception as e:
            print(f"[ERROR] {e}")
            return {}

    def get_employee_locations_from_shifts(
        self,
        date_from: str,
        date_to: str
    ) -> Dict[str, Dict[str, str]]:
        """
        Получить места работы сотрудников по кассовым сменам.

        Returns:
            Dict {employee_id: {date: location_name}}
        """
        pos_mapping = self.get_groups_with_pos()
        shifts = self.get_cash_shifts(date_from, date_to, status='CLOSED')

        employee_locations = {}

        for shift in shifts:
            emp_id = shift.get('responsibleUserId')
            pos_id = shift.get('pointOfSaleId')
            open_date = shift.get('openDate', '')[:10]  # YYYY-MM-DD

            if not emp_id or not open_date:
                continue

            location = pos_mapping.get(pos_id, 'Неизвестная точка')

            if emp_id not in employee_locations:
                employee_locations[emp_id] = {}

            employee_locations[emp_id][open_date] = location

        print(f"[OK] Определены точки для {len(employee_locations)} сотрудников")
        return employee_locations

    def get_employee_metrics_from_shifts(
        self,
        date_from: str,
        date_to: str
    ) -> Dict[str, Dict]:
        """
        Получить агрегированные данные по сотрудникам из кассовых смен.

        Unified метод: сотрудник, локация, дата, выручка, часы - всё из одного API.

        Args:
            date_from: Дата начала (YYYY-MM-DD)
            date_to: Дата окончания (YYYY-MM-DD)

        Returns:
            Dict {employee_id: {
                'shifts_count': int,           # Количество смен
                'dates': [str],                # Даты смен
                'locations': {str: int},       # Локация -> кол-во смен
                'shift_locations': {str: str}, # Дата -> локация (для расчёта плана)
                'total_revenue': float,        # Выручка (salesCard + salesCash)
                'revenue_card': float,         # Выручка картой
                'revenue_cash': float,         # Выручка наличными
                'total_hours': float           # Часы работы (из openDate/closeDate)
            }}
        """
        if not self.token:
            print("[ERROR] Нужна авторизация")
            return {}

        # Получаем маппинг точек продаж
        pos_mapping = self.get_groups_with_pos()

        # Получаем закрытые кассовые смены
        shifts = self.get_cash_shifts(date_from, date_to, status='CLOSED')

        if not shifts:
            return {}

        employee_data = {}

        for shift in shifts:
            emp_id = shift.get('responsibleUserId')
            if not emp_id:
                continue

            pos_id = shift.get('pointOfSaleId')
            open_date_str = shift.get('openDate', '')
            close_date_str = shift.get('closeDate', '')
            open_date = open_date_str[:10] if open_date_str else ''  # YYYY-MM-DD

            # Рассчитываем длительность смены в часах
            shift_hours = 0.0
            if open_date_str and close_date_str:
                try:
                    open_dt = self._parse_iso_datetime(open_date_str)
                    close_dt = self._parse_iso_datetime(close_date_str)
                    if open_dt and close_dt:
                        delta = close_dt - open_dt
                        shift_hours = delta.total_seconds() / 3600
                        # Защита от отрицательных или слишком больших значений
                        if shift_hours < 0 or shift_hours > 24:
                            shift_hours = 0.0
                except:
                    pass

            # Выручка
            sales_card = float(shift.get('payOrders', 0) or 0)
            sales_cash = float(shift.get('payOrdersCash', 0) or 0)

            location = pos_mapping.get(pos_id, 'Неизвестная точка')

            # Инициализируем данные сотрудника
            if emp_id not in employee_data:
                employee_data[emp_id] = {
                    'shifts_count': 0,
                    'dates': [],
                    'locations': {},
                    'shift_locations': {},
                    'total_revenue': 0.0,
                    'revenue_card': 0.0,
                    'revenue_cash': 0.0,
                    'total_hours': 0.0
                }

            emp = employee_data[emp_id]

            # Агрегируем данные
            emp['shifts_count'] += 1
            emp['total_hours'] += shift_hours

            if open_date and open_date not in emp['dates']:
                emp['dates'].append(open_date)

            if location:
                emp['locations'][location] = emp['locations'].get(location, 0) + 1
                if open_date:
                    emp['shift_locations'][open_date] = location

            emp['total_revenue'] += sales_card + sales_cash
            emp['revenue_card'] += sales_card
            emp['revenue_cash'] += sales_cash

        # Сортируем даты
        for emp_id in employee_data:
            employee_data[emp_id]['dates'].sort()

        print(f"[OK] Получены метрики из смен для {len(employee_data)} сотрудников")
        return employee_data

    def get_employees(self) -> List[Dict]:
        """Получить список сотрудников."""
        if not self.token:
            print("[ERROR] Нужна авторизация")
            return []

        url = f"{self.base_url}/employees"
        params = {"key": self.token}

        print("[EMPLOYEES] Загружаю список сотрудников...")

        try:
            response = requests.get(url, params=params)

            if response.status_code == 200:
                return self._parse_employees_xml(response.text)
            else:
                print(f"[ERROR] Ошибка: {response.status_code}")
                return []

        except Exception as e:
            print(f"[ERROR] {e}")
            return []

    def _parse_employees_xml(self, xml_text: str) -> List[Dict]:
        """Парсинг XML со списком сотрудников."""
        employees = []

        try:
            root = ET.fromstring(xml_text)

            for emp in root.findall('.//employee'):
                employee = {}

                id_elem = emp.find('id')
                employee['id'] = id_elem.text if id_elem is not None else None

                name_elem = emp.find('name')
                employee['name'] = name_elem.text if name_elem is not None else None

                code_elem = emp.find('code')
                employee['code'] = code_elem.text if code_elem is not None else None

                employees.append(employee)

            print(f"[OK] Загружено {len(employees)} сотрудников")
            return employees

        except ET.ParseError as e:
            print(f"[ERROR] Ошибка парсинга: {e}")
            return []

# Тестовый запуск
if __name__ == "__main__":
    print("🍺 Тестируем подключение к iiko API\n")
    
    api = IikoAPI()
    
    if api.authenticate():
        print("\n🎉 Все работает! Можем переходить к получению данных.")
        api.logout()
    else:
        print("\n❌ Не удалось подключиться. Проверьте настройки в config.py")