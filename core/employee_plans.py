"""
Модуль для чтения планов сотрудников из Excel файла.
"""
import pandas as pd
from datetime import datetime, date
from typing import Optional, Dict, List
import os


# Маппинг инициалов на полные имена сотрудников
INITIALS_TO_NAME = {
    'АН': 'Артемий Новаев',
    'НВ': 'Васильев Никита',
    'ДК': 'Кизатов Дамир',
    'ДКС': 'Дарья Коновцова',
    'ЕБ': 'Егор Бобриков',
    'ЕВ': 'Егор Верещагин',
    'ТМ': 'Макарова Татьяна',
    'тм': 'Макарова Татьяна',  # lowercase вариант
    'МП': 'Максим Поляков',
    'КД': 'Кизатов Дамир',
    # Старые сотрудники (для истории)
    'АЛЯ': None,
    'Аля': None,
    'ВМ': None,
    'вм': None,
    'ВН': None,
    'СС': None,
}

# Маппинг месяцев
MONTH_NAMES = {
    'октябрь': 10,
    'ноябрь': 11,
    'декабрь': 12,
    'январь': 1,
    'февраль': 2,
    'март': 3,
    'апрель': 4,
    'май': 5,
    'июнь': 6,
    'июль': 7,
    'август': 8,
    'сентябрь': 9,
}

# Бары и их индексы колонок в Excel
BARS = {
    'Кременчугская': (1, 2),      # бармен col 1, план col 2
    'Варшавская': (3, 4),         # бармен col 3, план col 4
    'Большой пр В.О.': (5, 6),    # бармен col 5, план col 6
    'Лиговский': (7, 8),          # бармен col 7, план col 8
}


class EmployeePlansReader:
    """Класс для чтения планов из Excel файла."""

    def __init__(self, filepath: str = None):
        if filepath is None:
            # Путь по умолчанию
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            filepath = os.path.join(base_dir, 'план для сайта.xlsx')

        self.filepath = filepath
        self._plans_cache = None

    def _parse_month_year(self, month_str: str) -> tuple:
        """Парсит строку месяца типа 'Октябрь 2025' -> (10, 2025)."""
        if not isinstance(month_str, str):
            return None, None

        parts = month_str.lower().strip().split()
        if len(parts) != 2:
            return None, None

        month_name, year_str = parts
        month = MONTH_NAMES.get(month_name)
        try:
            year = int(year_str)
        except ValueError:
            return None, None

        return month, year

    def _load_plans(self) -> Dict:
        """
        Загружает и парсит Excel файл.
        Возвращает структуру: {(year, month, day, bar): {initials: plan_value}}
        """
        if self._plans_cache is not None:
            return self._plans_cache

        if not os.path.exists(self.filepath):
            print(f"[PLANS] Fayl ne nayden: {self.filepath}")
            return {}

        df = pd.read_excel(self.filepath, header=None)
        plans = {}

        current_month = None
        current_year = None

        for idx, row in df.iterrows():
            # Проверяем, является ли строка заголовком месяца
            cell = row[1]
            if isinstance(cell, str):
                month, year = self._parse_month_year(cell)
                if month and year:
                    current_month = month
                    current_year = year
                    continue

            # Пропускаем строки без номера дня
            day = row[0]
            if pd.isna(day) or not isinstance(day, (int, float)):
                continue

            day = int(day)

            # Если нет текущего месяца, пропускаем
            if current_month is None or current_year is None:
                continue

            # Читаем данные по каждому бару
            for bar_name, (bartender_col, plan_col) in BARS.items():
                bartender = row[bartender_col]
                plan_value = row[plan_col]

                if pd.isna(bartender) or pd.isna(plan_value):
                    continue

                bartender = str(bartender).strip().upper()

                try:
                    plan_value = float(plan_value)
                except (ValueError, TypeError):
                    continue

                key = (current_year, current_month, day, bar_name)
                if key not in plans:
                    plans[key] = {}
                plans[key][bartender] = plan_value

        self._plans_cache = plans
        print(f"[PLANS] Zagruzheno {len(plans)} zapisey planov")
        return plans

    def get_employee_plan(
        self,
        employee_name: str,
        date_from: str,
        date_to: str,
        bar_name: Optional[str] = None
    ) -> float:
        """
        Получает план сотрудника за период.

        Args:
            employee_name: Полное имя сотрудника
            date_from: Дата начала (YYYY-MM-DD)
            date_to: Дата окончания (YYYY-MM-DD)
            bar_name: Название бара (опционально)

        Returns:
            Сумма плана за период
        """
        plans = self._load_plans()

        if not plans:
            return 0.0

        # Находим инициалы для сотрудника
        employee_initials = []
        for initials, name in INITIALS_TO_NAME.items():
            if name == employee_name:
                employee_initials.append(initials.upper())

        if not employee_initials:
            print(f"[PLANS] Ne naydeny inicialy dlya: {employee_name}")
            return 0.0

        # Парсим даты
        try:
            start = datetime.strptime(date_from, '%Y-%m-%d').date()
            end = datetime.strptime(date_to, '%Y-%m-%d').date()
        except ValueError:
            print(f"[PLANS] Neverny format dat: {date_from}, {date_to}")
            return 0.0

        total_plan = 0.0

        # Перебираем все дни в диапазоне
        current = start
        while current <= end:
            year = current.year
            month = current.month
            day = current.day

            # Собираем план по барам
            bars_to_check = [bar_name] if bar_name else list(BARS.keys())

            for bar in bars_to_check:
                key = (year, month, day, bar)
                day_plans = plans.get(key, {})

                for initials in employee_initials:
                    if initials in day_plans:
                        total_plan += day_plans[initials]

            # Следующий день
            current = date(year, month, day)
            current = date.fromordinal(current.toordinal() + 1)

        print(f"[PLANS] Plan dlya {employee_name}: {total_plan:.0f} rub ({date_from} - {date_to})")
        return total_plan

    def clear_cache(self):
        """Очищает кэш планов."""
        self._plans_cache = None


# Глобальный экземпляр для переиспользования
_reader = None

def get_employee_plan(employee_name: str, date_from: str, date_to: str, bar_name: str = None) -> float:
    """
    Удобная функция для получения плана сотрудника.
    """
    global _reader
    if _reader is None:
        _reader = EmployeePlansReader()
    return _reader.get_employee_plan(employee_name, date_from, date_to, bar_name)
