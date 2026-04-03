"""
Генератор ежедневных планов на основе месячных планов с weekend weighting.

Логика:
- Пт/Сб имеют вес 2.0 (приносят ~2x выручки)
- Остальные дни (пн-чт, вс) имеют вес 1.0
- План на день = (месячный план / сумму весов в месяце) × вес дня

Файл ежедневных планов: data/daily_plans.json
"""

import json
import os
from datetime import datetime, timedelta
from calendar import monthrange
from typing import Dict, List, Optional
from core.storage_paths import get_data_path


# Веса дней недели
WEEKEND_WEIGHT = 2.0  # Пятница (4) и Суббота (5)
WEEKDAY_WEIGHT = 1.0  # Остальные дни


def get_day_weight(date: datetime) -> float:
    """Получить вес дня недели."""
    weekday = date.weekday()  # 0=пн, 4=пт, 5=сб, 6=вс
    if weekday in (4, 5):  # Пт, Сб
        return WEEKEND_WEIGHT
    return WEEKDAY_WEIGHT


def get_days_in_month(year: int, month: int) -> List[datetime]:
    """Получить список всех дней месяца."""
    days_in_month = monthrange(year, month)[1]
    return [
        datetime(year, month, day)
        for day in range(1, days_in_month + 1)
    ]


def calculate_month_weight(year: int, month: int) -> float:
    """Рассчитать суммарный вес месяца."""
    days = get_days_in_month(year, month)
    return sum(get_day_weight(d) for d in days)


def get_daily_plan(monthly_revenue: float, year: int, month: int, day: int) -> float:
    """
    Рассчитать план на конкретный день.

    Args:
        monthly_revenue: План выручки на месяц
        year: Год
        month: Месяц (1-12)
        day: День месяца

    Returns:
        План на день
    """
    # Суммарный вес месяца
    month_weight = calculate_month_weight(year, month)

    if month_weight == 0 or monthly_revenue == 0:
        return 0.0

    # План на одну "весовую единицу"
    plan_per_weight = monthly_revenue / month_weight

    # Вес конкретного дня
    date = datetime(year, month, day)
    day_weight = get_day_weight(date)

    # План на день
    return round(plan_per_weight * day_weight, 2)


class DailyPlansGenerator:
    """Генератор ежедневных планов из месячных."""

    def __init__(self, monthly_plans_file: str = None, daily_plans_file: str = None):
        """
        Инициализация генератора.

        Args:
            monthly_plans_file: Путь к файлу месячных планов (plansdashboard.json)
            daily_plans_file: Путь к файлу ежедневных планов (daily_plans.json)
        """
        if monthly_plans_file is None:
            monthly_plans_file = get_data_path('plansdashboard.json', seed_from_local=True)

        if daily_plans_file is None:
            daily_plans_file = get_data_path('daily_plans.json', seed_from_local=True)

        self.monthly_plans_file = monthly_plans_file
        self.daily_plans_file = daily_plans_file

    def load_monthly_plans(self) -> Dict:
        """Загрузить месячные планы."""
        if not os.path.exists(self.monthly_plans_file):
            print(f"[DAILY_PLANS] Файл месячных планов не найден: {self.monthly_plans_file}")
            return {}

        try:
            with open(self.monthly_plans_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('plans', {})
        except Exception as e:
            print(f"[DAILY_PLANS] Ошибка чтения месячных планов: {e}")
            return {}

    def load_daily_plans(self) -> Dict:
        """Загрузить ежедневные планы."""
        if not os.path.exists(self.daily_plans_file):
            return {}

        try:
            with open(self.daily_plans_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('plans', {})
        except Exception as e:
            print(f"[DAILY_PLANS] Ошибка чтения ежедневных планов: {e}")
            return {}

    def save_daily_plans(self, daily_plans: Dict):
        """Сохранить ежедневные планы."""
        data = {
            'plans': daily_plans,
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'source': self.monthly_plans_file,
                'formula': 'daily_plan = (monthly_revenue / month_weight) × day_weight',
                'weights': {
                    'weekday': WEEKDAY_WEIGHT,
                    'weekend': WEEKEND_WEIGHT,
                    'weekend_days': 'Friday (4), Saturday (5)'
                }
            }
        }

        # Создаем директорию если нужно
        directory = os.path.dirname(self.daily_plans_file)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        with open(self.daily_plans_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[DAILY_PLANS] Сохранено ежедневных планов: {len(daily_plans)} дней")

    def parse_month_key(self, month_key: str) -> tuple:
        """
        Разобрать ключ месяца.

        Args:
            month_key: Ключ в формате 'venue_YYYY-MM' или 'YYYY-MM'

        Returns:
            (venue_key, year, month) или (None, year, month) если venue не указан
        """
        parts = month_key.split('_')

        if len(parts) == 2 and len(parts[1]) == 7:
            # Формат: venue_YYYY-MM
            venue_key = parts[0]
            year = int(parts[1][:4])
            month = int(parts[1][5:7])
            return venue_key, year, month
        elif len(parts) == 1 and len(parts[0]) == 7:
            # Формат: YYYY-MM (без venue)
            year = int(parts[0][:4])
            month = int(parts[0][5:7])
            return None, year, month
        else:
            return None, None, None

    def generate_for_month(self, venue_key: str, year: int, month: int, monthly_revenue: float) -> Dict[str, float]:
        """
        Сгенерировать ежедневные планы для одного месяца.

        Args:
            venue_key: Ключ заведения
            year: Год
            month: Месяц
            monthly_revenue: План выручки на месяц

        Returns:
            Dict {date_str: daily_plan}
        """
        daily_plans = {}
        days_in_month = monthrange(year, month)[1]

        for day in range(1, days_in_month + 1):
            date_str = f"{year}-{month:02d}-{day:02d}"
            daily_plan = get_daily_plan(monthly_revenue, year, month, day)
            daily_plans[date_str] = daily_plan

        return daily_plans

    def generate_all(self, venues: List[str] = None) -> Dict[str, Dict[str, float]]:
        """
        Сгенерировать ежедневные планы для всех заведений.

        Args:
            venues: Список заведений для генерации (None = все из monthly plans)

        Returns:
            Dict {date_str: {venue_key: daily_plan}}
        """
        monthly_plans = self.load_monthly_plans()

        if not monthly_plans:
            print("[DAILY_PLANS] Нет месячных планов для генерации")
            return {}

        # Структура: {date_str: {venue_key: daily_plan}}
        daily_plans = {}

        # Собираем все месяцы и заведения
        months_data = {}  # {(year, month): {venue_key: revenue}}

        for month_key, plan_data in monthly_plans.items():
            venue_key, year, month = self.parse_month_key(month_key)

            if year is None or month is None:
                continue

            # Если venue не указан в ключе, используем 'all'
            if venue_key is None:
                venue_key = 'all'

            revenue = plan_data.get('revenue', 0)

            if (year, month) not in months_data:
                months_data[(year, month)] = {}

            months_data[(year, month)][venue_key] = revenue

        # Генерируем ежедневные планы для каждого месяца
        for (year, month), venues_revenue in months_data.items():
            print(f"[DAILY_PLANS] Генерация планов на {year}-{month:02d}...")

            days_in_month = monthrange(year, month)[1]

            for day in range(1, days_in_month + 1):
                date_str = f"{year}-{month:02d}-{day:02d}"

                if date_str not in daily_plans:
                    daily_plans[date_str] = {}

                for venue_key, monthly_revenue in venues_revenue.items():
                    if monthly_revenue > 0:
                        daily_plan = get_daily_plan(monthly_revenue, year, month, day)
                        daily_plans[date_str][venue_key] = daily_plan

        return daily_plans

    def regenerate(self, venues: List[str] = None):
        """
        Пересгенерировать все ежедневные планы.

        Args:
            venues: Список заведений (None = все)
        """
        print("[DAILY_PLANS] Начало генерации ежедневных планов...")

        daily_plans = self.generate_all(venues)

        if daily_plans:
            self.save_daily_plans(daily_plans)
            print(f"[DAILY_PLANS] Готово! Сгенерировано {len(daily_plans)} дней")
        else:
            print("[DAILY_PLANS] Нет данных для генерации")

    def regenerate_for_period(self, year: int, month: int, venues: List[str] = None):
        """
        Пересгенерировать планы за конкретный месяц.

        Args:
            year: Год
            month: Месяц
            venues: Список заведений
        """
        print(f"[DAILY_PLANS] Генерация планов на {year}-{month:02d}...")

        monthly_plans = self.load_monthly_plans()
        daily_plans = self.load_daily_plans()

        for month_key, plan_data in monthly_plans.items():
            venue_key, y, m = self.parse_month_key(month_key)

            if y != year or m != month:
                continue

            if venue_key is None:
                venue_key = 'all'

            if venues and venue_key not in venues:
                continue

            revenue = plan_data.get('revenue', 0)
            if revenue <= 0:
                continue

            # Генерируем планы для этого месяца
            days_in_month = monthrange(year, month)[1]

            for day in range(1, days_in_month + 1):
                date_str = f"{year}-{month:02d}-{day:02d}"

                if date_str not in daily_plans:
                    daily_plans[date_str] = {}

                daily_plan = get_daily_plan(revenue, year, month, day)
                daily_plans[date_str][venue_key] = daily_plan

        self.save_daily_plans(daily_plans)
        print(f"[DAILY_PLANS] Готово!")
    def needs_regeneration(self) -> bool:
        """
        Проверить, покрывает ли daily_plans.json все месячные планы.

        Проверяем первый и последний день каждого месяца для каждой точки.
        Этого достаточно, чтобы быстро обнаружить пропавшие месяцы на Render Disk.
        """
        monthly_plans = self.load_monthly_plans()
        if not monthly_plans:
            return False

        daily_plans = self.load_daily_plans()
        if not daily_plans:
            print("[DAILY_PLANS] daily_plans.json отсутствует или пуст")
            return True

        for month_key, plan_data in monthly_plans.items():
            venue_key, year, month = self.parse_month_key(month_key)

            if year is None or month is None:
                continue

            if venue_key is None:
                venue_key = 'all'

            revenue = plan_data.get('revenue', 0) if isinstance(plan_data, dict) else 0
            if revenue <= 0:
                continue

            days_in_month = monthrange(year, month)[1]
            first_day = f"{year}-{month:02d}-01"
            last_day = f"{year}-{month:02d}-{days_in_month:02d}"

            first_day_plans = daily_plans.get(first_day, {})
            last_day_plans = daily_plans.get(last_day, {})

            if venue_key not in first_day_plans or venue_key not in last_day_plans:
                print(
                    f"[DAILY_PLANS] Требуется пересчет: нет покрытия "
                    f"для {venue_key} {year}-{month:02d}"
                )
                return True

        return False


# Глобальная функция для использования в других модулях
def regenerate_daily_plans(venues: List[str] = None):
    """
    Пересгенерировать ежедневные планы из месячных.

    Args:
        venues: Список заведений (None = все)
    """
    generator = DailyPlansGenerator()
    generator.regenerate(venues)


def ensure_daily_plans_current(force: bool = False, venues: List[str] = None) -> bool:
    """
    Убедиться, что daily_plans.json существует и покрывает все месячные планы.

    Returns:
        bool: True если файл был пересобран
    """
    generator = DailyPlansGenerator()

    if force or generator.needs_regeneration():
        generator.regenerate(venues)
        return True

    return False


def get_daily_plan_for_date(date_str: str, venue_key: str = None) -> Dict[str, float]:
    """
    Получить план на конкретную дату.

    Args:
        date_str: Дата в формате YYYY-MM-DD
        venue_key: Ключ заведения (None = все)

    Returns:
        Dict {venue_key: daily_plan} или float если venue_key указан
    """
    generator = DailyPlansGenerator()
    daily_plans = generator.load_daily_plans()

    day_plans = daily_plans.get(date_str, {})

    if venue_key:
        return day_plans.get(venue_key, 0.0)

    return day_plans


# Тестирование
if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ DailyPlansGenerator")
    print("=" * 60)

    # Создаём тестовые месячные планы
    test_monthly_plans = {
        "bolshoy_2025-10": {"revenue": 1201750.0},
        "ligovskiy_2025-10": {"revenue": 655500.0},
        "kremenchugskaya_2025-10": {"revenue": 1500000.0},
        "varshavskaya_2025-10": {"revenue": 1000000.0},
    }

    # Сохраняем тестовые планы
    os.makedirs('data', exist_ok=True)
    with open('data/test_plansdashboard.json', 'w', encoding='utf-8') as f:
        json.dump({'plans': test_monthly_plans}, f, indent=2, ensure_ascii=False)

    # Генерируем ежедневные планы
    generator = DailyPlansGenerator(
        monthly_plans_file='data/test_plansdashboard.json',
        daily_plans_file='data/test_daily_plans.json'
    )

    generator.regenerate()

    # Проверяем результат
    daily_plans = generator.load_daily_plans()

    print("\nПример планов на разные дни октября 2025:")
    print("-" * 60)

    test_dates = ['2025-10-01', '2025-10-03', '2025-10-04', '2025-10-05']

    for date_str in test_dates:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        weekday_name = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'][date.weekday()]
        weight = get_day_weight(date)

        day_plans = daily_plans.get(date_str, {})

        print(f"\n{date_str} ({weekday_name}, вес={weight}):")
        for venue, plan in day_plans.items():
            print(f"   {venue}: {plan:,.0f}")

    # Проверяем расчёт для одного дня
    print("\n" + "=" * 60)
    print("ПРОВЕРКА ФОРМУЛЫ для bolshoy_2025-10:")
    print("=" * 60)

    monthly_revenue = 1201750.0
    year, month = 2025, 10

    month_weight = calculate_month_weight(year, month)
    plan_per_weight = monthly_revenue / month_weight

    print(f"Месячный план: {monthly_revenue:,.0f}")
    print(f"Вес месяца: {month_weight:.1f} единиц")
    print(f"План на 1 вес: {plan_per_weight:,.2f}")

    days_in_month = monthrange(year, month)[1]
    weekday_count = sum(1 for d in get_days_in_month(year, month) if d.weekday() not in (4, 5))
    weekend_count = sum(1 for d in get_days_in_month(year, month) if d.weekday() in (4, 5))

    print(f"\nДней в месяце: {days_in_month}")
    print(f"Будних дней (вес=1): {weekday_count}")
    print(f"Выходных дней (вес=2): {weekend_count}")
    print(f"Проверка: {weekday_count}*1 + {weekend_count}*2 = {weekday_count + weekend_count * 2:.1f}")

    # Очистка
    print("\n" + "=" * 60)
    print("Очистка тестовых файлов...")

    if os.path.exists('data/test_plansdashboard.json'):
        os.remove('data/test_plansdashboard.json')
    if os.path.exists('data/test_daily_plans.json'):
        os.remove('data/test_daily_plans.json')

    print("Готово!")
