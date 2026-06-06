"""
Генератор ежедневных планов (производный кэш data/daily_plans.json).

Вся математика веса дня вынесена в core/day_weights.py — здесь она НЕ дублируется.
Этот модуль лишь материализует подневной план из месячных планов
(plansdashboard.json) + override весов (day_weight_overrides.json) и сохраняет в
data/daily_plans.json, откуда читают бонусы сотрудников и метрики выручки.

Формула (см. core/day_weights):
    план_на_день = (месячный_план / сумма_весов_месяца) × вес_дня

Агрегат 'all' за день = сумма дневных планов реальных точек (не выводится из
отдельного месячного плана all_*), чтобы override точек автоматически в него попадали.
"""

import json
import os
from datetime import datetime
from calendar import monthrange
from typing import Dict, List, Optional

from core.storage_paths import get_data_path
from core.day_weights import (
    daily_plan as compute_daily_plan,
    month_weight,
    WEEKDAY_WEIGHT,
    WEEKEND_WEIGHT,
)


# Реальные заведения для агрегата 'all'
REAL_VENUES = ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']


class DailyPlansGenerator:
    """Генератор ежедневных планов из месячных + override весов."""

    def __init__(self, monthly_plans_file: str = None, daily_plans_file: str = None):
        if monthly_plans_file is None:
            monthly_plans_file = get_data_path('plansdashboard.json', seed_from_local=True)

        if daily_plans_file is None:
            daily_plans_file = get_data_path('daily_plans.json', seed_from_local=True)

        self.monthly_plans_file = monthly_plans_file
        self.daily_plans_file = daily_plans_file
        self._overrides_mgr = None  # ленивый DayWeightOverridesManager

    # ------------------------------------------------------------------ overrides

    def _overrides_for(self, venue_key: str, year: int, month: int) -> Dict[str, float]:
        """Override весов дней для заведения+месяца: {"YYYY-MM-DD": weight}."""
        try:
            from core.day_weight_overrides import DayWeightOverridesManager
            if self._overrides_mgr is None:
                self._overrides_mgr = DayWeightOverridesManager()
            return self._overrides_mgr.get_for_venue_month(venue_key, year, month)
        except Exception as e:
            print(f"[DAILY_PLANS WARN] overrides не загружены ({venue_key} {year}-{month:02d}): {e}")
            return {}

    # ------------------------------------------------------------------ I/O

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
        """Атомарно сохранить ежедневные планы и сбросить кэш потребителей."""
        data = {
            'plans': daily_plans,
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'source': self.monthly_plans_file,
                'formula': 'daily_plan = (monthly_revenue / month_weight) × day_weight',
                'weights': {
                    'weekday': WEEKDAY_WEIGHT,
                    'weekend': WEEKEND_WEIGHT,
                    'weekend_days': 'Friday (4), Saturday (5)',
                    'overrides': 'core/day_weight_overrides.py (per venue+date absolute weight)',
                },
                'aggregate_all': 'sum of real venues per day',
            }
        }

        directory = os.path.dirname(self.daily_plans_file)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        # Backup перед записью
        if os.path.exists(self.daily_plans_file):
            try:
                import shutil
                shutil.copy2(self.daily_plans_file, self.daily_plans_file + '.backup')
            except Exception as e:
                print(f"[DAILY_PLANS WARNING] backup не создан: {e}")

        # Атомарная запись: tmp -> fsync -> os.replace
        temp_file = self.daily_plans_file + '.tmp'
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(temp_file, self.daily_plans_file)
        except Exception:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise

        print(f"[DAILY_PLANS] Сохранено ежедневных планов: {len(daily_plans)} дней")

        # Сбросить кэш DailyPlansReader в core/employee_plans.py — иначе бонусы
        # сотрудников будут считаться по устаревшему daily_plans.json до рестарта.
        try:
            from core.employee_plans import clear_plans_cache
            clear_plans_cache()
        except Exception as e:
            print(f"[DAILY_PLANS WARN] не удалось сбросить кэш employee_plans: {e}")

    # ------------------------------------------------------------------ helpers

    def parse_month_key(self, month_key: str) -> tuple:
        """Разобрать ключ месяца 'venue_YYYY-MM' или 'YYYY-MM'.

        Returns:
            (venue_key, year, month); venue_key=None если без заведения.
        """
        parts = month_key.split('_')

        if len(parts) == 2 and len(parts[1]) == 7:
            venue_key = parts[0]
            year = int(parts[1][:4])
            month = int(parts[1][5:7])
            return venue_key, year, month
        elif len(parts) == 1 and len(parts[0]) == 7:
            year = int(parts[0][:4])
            month = int(parts[0][5:7])
            return None, year, month
        else:
            return None, None, None

    def _recompute_aggregate(self, daily_plans: Dict, year: int, month: int):
        """Пересчитать агрегат 'all' = сумма дневных планов реальных точек за месяц.

        Мутирует daily_plans на месте. Дни, которых нет в daily_plans, пропускаются.
        """
        days_in_month = monthrange(year, month)[1]
        for day in range(1, days_in_month + 1):
            date_str = f"{year}-{month:02d}-{day:02d}"
            day_plans = daily_plans.get(date_str)
            if day_plans is None:
                continue
            day_plans['all'] = round(sum(day_plans.get(v, 0.0) for v in REAL_VENUES), 2)

    # ------------------------------------------------------------------ генерация

    def generate_for_month(self, venue_key: str, year: int, month: int,
                           monthly_revenue: float) -> Dict[str, float]:
        """Сгенерировать ежедневные планы одного заведения за месяц."""
        ov = self._overrides_for(venue_key, year, month)
        daily_plans = {}
        days_in_month = monthrange(year, month)[1]
        for day in range(1, days_in_month + 1):
            date_str = f"{year}-{month:02d}-{day:02d}"
            daily_plans[date_str] = compute_daily_plan(monthly_revenue, year, month, day, ov)
        return daily_plans

    def generate_all(self, venues: List[str] = None) -> Dict[str, Dict[str, float]]:
        """Сгенерировать ежедневные планы для всех заведений из месячных планов.

        Агрегат 'all' считается как сумма реальных точек (месячный план all_* для
        подневной разбивки не используется).
        """
        monthly_plans = self.load_monthly_plans()

        if not monthly_plans:
            print("[DAILY_PLANS] Нет месячных планов для генерации")
            return {}

        daily_plans = {}

        # Собираем {(year, month): {venue_key: revenue}}
        months_data = {}
        for month_key, plan_data in monthly_plans.items():
            venue_key, year, month = self.parse_month_key(month_key)
            if year is None or month is None:
                continue
            if venue_key is None:
                venue_key = 'all'
            revenue = plan_data.get('revenue', 0) if isinstance(plan_data, dict) else 0
            months_data.setdefault((year, month), {})[venue_key] = revenue

        for (year, month), venues_revenue in months_data.items():
            print(f"[DAILY_PLANS] Генерация планов на {year}-{month:02d}...")

            days_in_month = monthrange(year, month)[1]
            for day in range(1, days_in_month + 1):
                date_str = f"{year}-{month:02d}-{day:02d}"
                daily_plans.setdefault(date_str, {})

            for venue_key, monthly_revenue in venues_revenue.items():
                if venue_key == 'all':
                    continue  # 'all' считаем как сумму точек ниже
                if not monthly_revenue or monthly_revenue <= 0:
                    continue
                ov = self._overrides_for(venue_key, year, month)
                for day in range(1, days_in_month + 1):
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    daily_plans[date_str][venue_key] = compute_daily_plan(
                        monthly_revenue, year, month, day, ov)

            # Агрегат 'all' = сумма реальных точек
            self._recompute_aggregate(daily_plans, year, month)

        return daily_plans

    def regenerate(self, venues: List[str] = None):
        """Полностью пересобрать все ежедневные планы."""
        print("[DAILY_PLANS] Начало генерации ежедневных планов...")
        daily_plans = self.generate_all(venues)
        if daily_plans:
            self.save_daily_plans(daily_plans)
            print(f"[DAILY_PLANS] Готово! Сгенерировано {len(daily_plans)} дней")
        else:
            print("[DAILY_PLANS] Нет данных для генерации")

    def regenerate_for_period(self, year: int, month: int, venues: List[str] = None):
        """Пересобрать планы за конкретный месяц (мерджит в существующий файл)."""
        print(f"[DAILY_PLANS] Генерация планов на {year}-{month:02d}...")

        monthly_plans = self.load_monthly_plans()
        daily_plans = self.load_daily_plans()

        for month_key, plan_data in monthly_plans.items():
            venue_key, y, m = self.parse_month_key(month_key)
            if y != year or m != month:
                continue
            if venue_key is None:
                venue_key = 'all'
            if venue_key == 'all':
                continue  # пересчитаем как сумму точек
            if venues and venue_key not in venues:
                continue

            revenue = plan_data.get('revenue', 0) if isinstance(plan_data, dict) else 0
            ov = self._overrides_for(venue_key, year, month)
            days_in_month = monthrange(year, month)[1]
            for day in range(1, days_in_month + 1):
                date_str = f"{year}-{month:02d}-{day:02d}"
                daily_plans.setdefault(date_str, {})
                daily_plans[date_str][venue_key] = compute_daily_plan(revenue, year, month, day, ov)

        self._recompute_aggregate(daily_plans, year, month)
        self.save_daily_plans(daily_plans)
        print("[DAILY_PLANS] Готово!")

    def regenerate_for_venue_month(self, venue_key: str, year: int, month: int):
        """Точечно пересобрать ежедневные планы одного заведения+месяца.

        Вызывается после сохранения месячного плана или изменения override.
        Заодно пересчитывает агрегат 'all' за этот месяц. Для venue_key='all'
        пересчитывает только агрегат.
        """
        daily_plans = self.load_daily_plans()

        if venue_key == 'all':
            self._recompute_aggregate(daily_plans, year, month)
            self.save_daily_plans(daily_plans)
            print(f"[DAILY_PLANS] Пересчитан агрегат all для {year}-{month:02d}")
            return

        monthly_plans = self.load_monthly_plans()
        month_key = f"{venue_key}_{year}-{month:02d}"
        plan_data = monthly_plans.get(month_key, {})
        revenue = plan_data.get('revenue', 0) if isinstance(plan_data, dict) else 0

        ov = self._overrides_for(venue_key, year, month)
        days_in_month = monthrange(year, month)[1]
        for day in range(1, days_in_month + 1):
            date_str = f"{year}-{month:02d}-{day:02d}"
            daily_plans.setdefault(date_str, {})
            # revenue<=0 -> 0.0 (compute_daily_plan), что заодно чистит «призрачные» значения
            daily_plans[date_str][venue_key] = compute_daily_plan(revenue, year, month, day, ov)

        self._recompute_aggregate(daily_plans, year, month)
        self.save_daily_plans(daily_plans)
        print(f"[DAILY_PLANS] Пересчитан {month_key}")

    def regenerate_for_aggregate_month(self, year: int, month: int):
        """Пересчитать только агрегат 'all' за месяц (сумма точек)."""
        daily_plans = self.load_daily_plans()
        self._recompute_aggregate(daily_plans, year, month)
        self.save_daily_plans(daily_plans)

    def needs_regeneration(self) -> bool:
        """Проверить, покрывает ли daily_plans.json все месячные планы.

        Проверяем первый и последний день каждого месяца для каждой точки.
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


# ------------------------------------------------------------------ модульный API

def regenerate_daily_plans(venues: List[str] = None):
    """Пересобрать ежедневные планы из месячных."""
    generator = DailyPlansGenerator()
    generator.regenerate(venues)


def ensure_daily_plans_current(force: bool = False, venues: List[str] = None) -> bool:
    """Убедиться, что daily_plans.json покрывает все месячные планы.

    Returns:
        True если файл был пересобран.
    """
    generator = DailyPlansGenerator()
    if force or generator.needs_regeneration():
        generator.regenerate(venues)
        return True
    return False


def regenerate_daily_plan_for_venue_month(venue_key: str, year: int, month: int):
    """Точечно пересобрать ежедневные планы одного заведения+месяца."""
    generator = DailyPlansGenerator()
    generator.regenerate_for_venue_month(venue_key, year, month)


def regenerate_all_aggregate_for_month(year: int, month: int):
    """Пересчитать агрегат 'all' (сумма точек) за месяц."""
    generator = DailyPlansGenerator()
    generator.regenerate_for_aggregate_month(year, month)


def get_daily_plan_for_date(date_str: str, venue_key: str = None):
    """Получить план на конкретную дату.

    Args:
        date_str: Дата 'YYYY-MM-DD'.
        venue_key: Ключ заведения (None = все заведения этого дня).

    Returns:
        float (если venue_key задан) или dict {venue_key: plan}.
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
    print("ТЕСТ DailyPlansGenerator")
    print("=" * 60)

    os.makedirs('data', exist_ok=True)
    test_monthly = 'data/test_plansdashboard.json'
    test_daily = 'data/test_daily_plans.json'
    test_overrides = 'data/test_day_weight_overrides.json'

    with open(test_monthly, 'w', encoding='utf-8') as f:
        json.dump({'plans': {
            'bolshoy_2025-11': {'revenue': 1201750.0},
            'ligovskiy_2025-11': {'revenue': 655500.0},
            'all_2025-11': {'revenue': 9999999.0},  # должен игнорироваться для подневной разбивки
        }}, f, ensure_ascii=False)

    # override: пусть менеджер пишет в тестовый файл
    from core.day_weight_overrides import DayWeightOverridesManager
    for p in (test_overrides, test_overrides + '.backup', test_overrides + '.lock'):
        if os.path.exists(p):
            os.remove(p)
    ov_mgr = DayWeightOverridesManager(data_file=test_overrides)

    gen = DailyPlansGenerator(monthly_plans_file=test_monthly, daily_plans_file=test_daily)
    gen._overrides_mgr = ov_mgr  # подменяем на тестовый менеджер
    gen.regenerate()

    daily = gen.load_daily_plans()
    nov = [d for d in daily if d.startswith('2025-11-')]
    sum_bolshoy = round(sum(daily[d].get('bolshoy', 0) for d in nov), 2)
    print(f"\nСумма bolshoy за ноябрь = {sum_bolshoy:,.2f} (план 1 201 750)")
    assert abs(sum_bolshoy - 1201750.0) <= 1.0

    # 'all' = сумма точек
    sample = '2025-11-07'  # пятница
    all_val = daily[sample].get('all', 0)
    venues_sum = round(sum(daily[sample].get(v, 0) for v in REAL_VENUES), 2)
    print(f"all[{sample}] = {all_val} ; сумма точек = {venues_sum}")
    assert abs(all_val - venues_sum) <= 0.01

    print("\nOK")

    for p in (test_monthly, test_daily, test_daily + '.backup', test_daily + '.tmp',
              test_overrides, test_overrides + '.backup', test_overrides + '.lock'):
        if os.path.exists(p):
            os.remove(p)
