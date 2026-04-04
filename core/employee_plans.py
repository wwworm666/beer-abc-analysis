"""
Модуль для расчёта планов сотрудников на основе кассовых смен.

План сотрудника = сумма ежедневных планов ТТ за те дни, когда он работал.
Данные берутся из data/daily_plans.json (автоматически генерируется из monthly plans).
"""
import json
from datetime import datetime
from typing import Dict, List, Optional
import os

from core.storage_paths import get_data_path


# Маппинг названий баров из iiko API на ключи в daily_plans.json
# ВАЖНО: daily_plans.json использует английские ключи: kremenchugskaya, bolshoy, varshavskaya, ligovskiy
# Данные о реальной точке работы берутся из кассовых смен (/v2/cashshifts),
# а не из attendance API (который возвращает только "Пивная культура").
BAR_NAME_MAPPING = {
    # === ИЗ КАССОВЫХ СМЕН (группы iiko) ===
    # "Пивная культура" - это Кременчугская (основная точка, она же доставка)
    'пивная культура': 'kremenchugskaya',
    # Большой пр. В.О (в iiko с точкой после В.О)
    'большой пр. в.о': 'bolshoy',
    # Варшавская
    'варшавская': 'varshavskaya',
    # Лиговский
    'лиговский': 'ligovskiy',
    # Планерная (новая точка - пока без плана)
    'планерная': 'planernaya',

    # === LEGACY (из attendance API и других источников) ===
    'пивной бутик': 'kremenchugskaya',
    'пивной бутик кременчугская': 'kremenchugskaya',
    'кременчугская': 'kremenchugskaya',
    'кременчуг': 'kremenchugskaya',
    'варшавка': 'varshavskaya',
    'пивной бутик варшавская': 'varshavskaya',
    'большой пр в.о.': 'bolshoy',
    'большой': 'bolshoy',
    'большой пр': 'bolshoy',
    'большой проспект': 'bolshoy',
    'пивной бутик большой': 'bolshoy',
    'в.о.': 'bolshoy',
    'во': 'bolshoy',
    'лиговка': 'ligovskiy',
    'пивной бутик лиговский': 'ligovskiy',
}


def normalize_bar_name(name: str) -> str:
    """Нормализует название бара для поиска в маппинге."""
    if not name:
        return ''
    return name.lower().strip()


class DailyPlansReader:
    """Чтение ежедневных планов из data/daily_plans.json."""

    def __init__(self, filepath: str = None):
        if filepath is None:
            filepath = get_data_path('daily_plans.json', seed_from_local=True)

        self.filepath = filepath
        self._plans_cache = None

    def _load_plans(self) -> Dict:
        """Загружает daily_plans.json."""
        if self._plans_cache is not None:
            return self._plans_cache

        if not os.path.exists(self.filepath):
            print(f"[EMPLOYEE_PLANS] daily_plans.json не найден: {self.filepath}")
            return {}

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._plans_cache = data.get('plans', {})
            print(f"[EMPLOYEE_PLANS] Загружено {len(self._plans_cache)} дней")
            return self._plans_cache
        except Exception as e:
            print(f"[EMPLOYEE_PLANS] Ошибка чтения daily_plans.json: {e}")
            return {}

    def get_plan_for_shift(self, date_str: str, venue_key: str) -> float:
        """
        Получает план для конкретного заведения на дату.

        Args:
            date_str: Дата в формате YYYY-MM-DD
            venue_key: Английский ключ заведения (kremenchugskaya, bolshoy, ...)

        Returns:
            План на день (или 0 если не найден)
        """
        plans = self._load_plans()
        day_plans = plans.get(date_str, {})
        return day_plans.get(venue_key, 0.0)

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
        unmatched = []

        for date_str, location in shift_locations.items():
            normalized = normalize_bar_name(location)
            venue_key = BAR_NAME_MAPPING.get(normalized, normalized)

            day_plans = plans.get(date_str, {})
            plan = day_plans.get(venue_key, 0.0)

            if plan == 0.0:
                unmatched.append(f"{date_str}: '{location}' -> '{venue_key}'")
            else:
                total_plan += plan

        if unmatched:
            print(f"[EMPLOYEE_PLANS] {len(unmatched)} смены без плана:")
            for u in unmatched[:5]:
                print(f"   {u}")

        return total_plan

    def clear_cache(self):
        """Очищает кэш."""
        self._plans_cache = None


# Глобальный экземпляр
_reader = None


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
        _reader = DailyPlansReader()
    return _reader.calculate_plan_from_shifts(shift_locations)


def clear_plans_cache():
    """Очищает кэш ежедневных планов."""
    global _reader
    if _reader is not None:
        _reader.clear_cache()
