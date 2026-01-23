"""
Модуль для расчёта планов сотрудников на основе явок.

План сотрудника = сумма планов ТТ за те дни, когда он работал.
Данные берутся из data/bar_plans.json
"""
import json
from datetime import datetime
from typing import Optional, Dict, List
import os


# Маппинг названий баров из iiko API на названия в планах
# Используем нормализованные ключи (lower, strip)
# ВАЖНО: Данные о реальной точке работы берутся из кассовых смен (/v2/cashshifts),
# а не из attendance API (который возвращает только "Пивная культура").
BAR_NAME_MAPPING = {
    # === ИЗ КАССОВЫХ СМЕН (группы iiko) ===
    # "Пивная культура" - это Кременчугская (основная точка, она же доставка)
    'пивная культура': 'Кременчугская',
    # Большой пр. В.О (в iiko с точкой после В.О)
    'большой пр. в.о': 'Большой пр В.О.',
    # Варшавская
    'варшавская': 'Варшавская',
    # Лиговский
    'лиговский': 'Лиговский',
    # Планерная (новая точка - пока без плана)
    'планерная': 'Планерная',

    # === LEGACY (из attendance API и других источников) ===
    # Кременчугская варианты
    'пивной бутик': 'Кременчугская',
    'пивной бутик кременчугская': 'Кременчугская',
    'кременчугская': 'Кременчугская',
    'кременчуг': 'Кременчугская',
    # Варшавская варианты
    'варшавка': 'Варшавская',
    'пивной бутик варшавская': 'Варшавская',
    # Большой пр В.О. варианты
    'большой пр в.о.': 'Большой пр В.О.',
    'большой': 'Большой пр В.О.',
    'большой пр': 'Большой пр В.О.',
    'большой проспект': 'Большой пр В.О.',
    'пивной бутик большой': 'Большой пр В.О.',
    'в.о.': 'Большой пр В.О.',
    'во': 'Большой пр В.О.',
    # Лиговский варианты
    'лиговка': 'Лиговский',
    'пивной бутик лиговский': 'Лиговский',
}


def normalize_bar_name(name: str) -> str:
    """Нормализует название бара для поиска в маппинге."""
    if not name:
        return ''
    return name.lower().strip()


class BarPlansReader:
    """Класс для чтения планов ТТ из JSON файла."""

    def __init__(self, filepath: str = None):
        if filepath is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            filepath = os.path.join(base_dir, 'data', 'bar_plans.json')

        self.filepath = filepath
        self._plans_cache = None
        self._metadata = None

    def _load_plans(self) -> Dict:
        """Загружает JSON файл с планами."""
        if self._plans_cache is not None:
            return self._plans_cache

        if not os.path.exists(self.filepath):
            print(f"[PLANS] Fayl ne nayden: {self.filepath}")
            return {}

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._metadata = data.get('metadata', {})
            self._plans_cache = data.get('plans', {})

            print(f"[PLANS] Zagruzheno {len(self._plans_cache)} dney planov TT")
            return self._plans_cache

        except Exception as e:
            print(f"[PLANS] Oshibka chteniya JSON: {e}")
            return {}

    def get_bar_plan(self, date_str: str, bar_name: str) -> float:
        """
        Получает план для конкретного бара на дату.

        Args:
            date_str: Дата в формате YYYY-MM-DD
            bar_name: Название бара

        Returns:
            План на день (или 0 если не найден)
        """
        plans = self._load_plans()
        day_plans = plans.get(date_str, {})

        # Пробуем найти бар напрямую или через маппинг
        if bar_name in day_plans:
            return day_plans[bar_name]

        mapped_name = BAR_NAME_MAPPING.get(bar_name)
        if mapped_name and mapped_name in day_plans:
            return day_plans[mapped_name]

        return 0.0

    def calculate_employee_plan(self, attendances: List[Dict]) -> float:
        """
        Рассчитывает план сотрудника на основе его явок.

        Args:
            attendances: Список явок [{date, department_name, ...}]

        Returns:
            Суммарный план за все смены
        """
        if not attendances:
            return 0.0

        total_plan = 0.0
        plans = self._load_plans()

        details = []
        unmatched = []

        for att in attendances:
            date_str = att.get('date')
            bar_name = att.get('department_name', '')

            if not date_str or not bar_name:
                unmatched.append(f"Missing: date={date_str}, bar={bar_name}")
                continue

            # Получаем план для этого бара на эту дату
            day_plans = plans.get(date_str, {})

            if not day_plans:
                unmatched.append(f"No plans for date {date_str}")
                continue

            # Пробуем найти бар
            plan = 0.0
            mapped_name = None
            normalized = normalize_bar_name(bar_name)

            # 1. Точное совпадение
            if bar_name in day_plans:
                plan = day_plans[bar_name]
                mapped_name = bar_name
            # 2. Через нормализованный маппинг
            elif normalized in BAR_NAME_MAPPING:
                mapped_name = BAR_NAME_MAPPING[normalized]
                if mapped_name in day_plans:
                    plan = day_plans[mapped_name]
            # 3. Поиск по подстроке (если ничего не нашли)
            else:
                for key, val in BAR_NAME_MAPPING.items():
                    if key in normalized or normalized in key:
                        mapped_name = val
                        if mapped_name in day_plans:
                            plan = day_plans[mapped_name]
                            break

            if plan == 0.0 and bar_name:
                unmatched.append(f"{date_str}: '{bar_name}'")

            if plan > 0:
                details.append(f"{date_str}: {mapped_name} = {plan:.0f}")
            total_plan += plan

        # Логируем только если есть проблемы
        if unmatched and not details:
            print(f"[PLANS] WARNING: No plan matched for {len(unmatched)} attendances")
            for u in unmatched[:3]:
                print(f"   {u}")

        return total_plan

    def get_bars(self) -> list:
        """Возвращает список баров."""
        self._load_plans()
        return self._metadata.get('bars', [])

    def clear_cache(self):
        """Очищает кэш планов."""
        self._plans_cache = None
        self._metadata = None

    def calculate_plan_from_shifts(self, shift_locations: Dict[str, str]) -> float:
        """
        Рассчитывает план сотрудника на основе кассовых смен.

        Args:
            shift_locations: Dict {date: location_name} из кассовых смен

        Returns:
            Суммарный план за все смены
        """
        if not shift_locations:
            return 0.0

        total_plan = 0.0
        plans = self._load_plans()

        for date_str, location in shift_locations.items():
            day_plans = plans.get(date_str, {})

            if not day_plans:
                continue

            # Нормализуем название и ищем через маппинг
            normalized = normalize_bar_name(location)
            mapped_name = BAR_NAME_MAPPING.get(normalized, location)

            # Ищем план
            plan = day_plans.get(mapped_name, 0.0)

            # Если не нашли, пробуем точное совпадение
            if plan == 0.0 and location in day_plans:
                plan = day_plans[location]

            total_plan += plan

        return total_plan


# Глобальный экземпляр
_reader = None


def get_employee_plan_by_attendance(attendances: List[Dict]) -> float:
    """
    DEPRECATED: Используйте get_employee_plan_by_shifts() вместо этого.

    Attendance API возвращает только "Пивная культура" для всех сотрудников,
    что не позволяет корректно определить место работы для расчёта плана.

    Args:
        attendances: Список явок сотрудника

    Returns:
        Суммарный план
    """
    global _reader
    if _reader is None:
        _reader = BarPlansReader()
    return _reader.calculate_employee_plan(attendances)


def get_bar_plan(date_str: str, bar_name: str) -> float:
    """
    Получает план бара на дату.
    """
    global _reader
    if _reader is None:
        _reader = BarPlansReader()
    return _reader.get_bar_plan(date_str, bar_name)


# Для обратной совместимости (старая функция)
def get_employee_plan(employee_name: str, date_from: str, date_to: str, bar_name: str = None) -> float:
    """
    DEPRECATED: Используйте get_employee_plan_by_attendance()

    Эта функция оставлена для обратной совместимости.
    Возвращает 0, т.к. без явок не можем рассчитать план.
    """
    print(f"[PLANS] WARNING: get_employee_plan() deprecated, use get_employee_plan_by_attendance()")
    return 0.0


def clear_plans_cache():
    """Очищает кэш планов."""
    global _reader
    if _reader is not None:
        _reader.clear_cache()


def get_employee_plan_by_shifts(shift_locations: Dict[str, str]) -> float:
    """
    Рассчитывает план сотрудника на основе кассовых смен.

    Args:
        shift_locations: Dict {date: location_name} из iiko cashshifts API

    Returns:
        Суммарный план
    """
    global _reader
    if _reader is None:
        _reader = BarPlansReader()
    return _reader.calculate_plan_from_shifts(shift_locations)
