"""
Модуль расчёта 4 ключевых метрик выручки для главной страницы

Метрики:
1. Текущая выручка — факт по данным OLAP за выбранный период
2. План — плановая выручка из daily_plans.json на период (рассчитывается автоматически: пт/сб = 2x)
3. Ожидаемая — прогноз на основе текущей динамики (тренд)
4. Средняя — среднедневная выручка за период
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from core.olap_reports import OlapReports
from core.daily_plans_generator import get_daily_plan_for_date


class RevenueMetricsCalculator:
    """Калькулятор метрик выручки"""

    def __init__(self):
        self._plans_file = 'data/daily_plans.json'

    def _read_plans_file(self) -> Dict:
        """Прочитать файл планов daily_plans.json"""
        try:
            with open(self._plans_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[REVENUE] Ошибка чтения планов: {e}")
            return {'plans': {}}

    def _get_daily_plan(self, date_str: str, bar_name: str) -> Optional[float]:
        """
        Получить плановую выручку на конкретный день для бара
        Использует daily_plans.json (автоматический расчёт пт/сб = 2x)

        Args:
            date_str: Дата в формате 'YYYY-MM-DD'
            bar_name: Название бара (например, 'bolshoy', 'kremenchugskaya')

        Returns:
            Плановая выручка или None
        """
        # Используем готовую функцию из daily_plans_generator
        return get_daily_plan_for_date(date_str, bar_name)

    def _calculate_period_plan(self, bar_name: str, date_from: str, date_to: str) -> Optional[float]:
        """
        Рассчитать плановую выручку за период из daily_plans.json

        Args:
            bar_name: Ключ заведения ('bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya') или '' для общей
            date_from: Начало периода 'YYYY-MM-DD'
            date_to: Конец периода 'YYYY-MM-DD'

        Returns:
            Плановая выручка за период или None
        """
        # Маппинг старых названий на новые ключи
        venue_key_map = {
            'Кременчугская': 'kremenchugskaya',
            'Варшавская': 'varshavskaya',
            'Большой пр В.О.': 'bolshoy',
            'Большой пр В.О': 'bolshoy',
            'Большой пр': 'bolshoy',
            'Лиговский': 'ligovskiy',
            'bolshoy': 'bolshoy',
            'ligovskiy': 'ligovskiy',
            'kremenchugskaya': 'kremenchugskaya',
            'varshavskaya': 'varshavskaya',
        }

        # Определяем ключ заведения
        venue_key = venue_key_map.get(bar_name, bar_name) if bar_name else None

        # Для "общей" используем 'all'
        if not venue_key:
            venue_key = 'all'

        total_plan = 0.0
        days_found = 0

        # Генерируем даты в периоде
        current_date = datetime.strptime(date_from, '%Y-%m-%d')
        end_date = datetime.strptime(date_to, '%Y-%m-%d')

        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')

            # Получаем план на день из daily_plans.json
            day_plan = get_daily_plan_for_date(date_str, venue_key)

            if day_plan and day_plan > 0:
                total_plan += day_plan
                days_found += 1

            current_date += timedelta(days=1)

        if days_found == 0:
            return None

        return round(total_plan, 2)

    def _calculate_actual_revenue(self, date_from: str, date_to: str, bar_name: str) -> Optional[float]:
        """
        Рассчитать фактическую выручку из OLAP за период

        Args:
            date_from: Начало периода 'YYYY-MM-DD'
            date_to: Конец периода 'YYYY-MM-DD'
            bar_name: Название бара или '' для общей

        Returns:
            Фактическая выручка или None
        """
        try:
            olap = OlapReports()
            if not olap.connect():
                print("[REVENUE] Не удалось подключиться к iiko API")
                return None

            # OLAP использует exclusive to-дату
            olap_date_to = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

            # Получаем данные о продажах пива (подойдёт для общей выручки)
            report_data = olap.get_beer_sales_report(date_from, olap_date_to, bar_name if bar_name else None)

            olap.disconnect()

            if not report_data or not report_data.get('data'):
                return None

            # Суммируем выручку
            total_revenue = 0.0
            for row in report_data['data']:
                dish_sum = float(row.get('DishDiscountSumInt', 0) or 0)
                total_revenue += dish_sum

            return round(total_revenue, 2)

        except Exception as e:
            print(f"[REVENUE] Ошибка расчёта факта: {e}")
            return None

    def _calculate_expected_revenue(
        self,
        actual: float,
        plan: float,
        date_from: str,
        date_to: str
    ) -> float:
        """
        Рассчитать ожидаемую выручку на основе тренда

        Логика:
        - Считаем сколько дней прошло в периоде
        - Считаем общий план на период
        - Экстраполируем факт на оставшиеся дни

        Args:
            actual: Фактическая выручка
            plan: Плановая выручка
            date_from: Начало периода
            date_to: Конец периода

        Returns:
            Ожидаемая выручка
        """
        try:
            start = datetime.strptime(date_from, '%Y-%m-%d')
            end = datetime.strptime(date_to, '%Y-%m-%d')
            total_days = (end - start).days + 1

            # Считаем сколько дней уже прошло (включая сегодня)
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            days_elapsed = min((today - start).days + 1, total_days)

            if days_elapsed <= 0:
                return plan

            # Средняя выручка в день по факту
            daily_actual = actual / days_elapsed

            # Если период ещё не закончился — экстраполируем
            if days_elapsed < total_days:
                days_remaining = total_days - days_elapsed
                expected = actual + (daily_actual * days_remaining)
            else:
                # Период закончился — ожидаемая = факт
                expected = actual

            return round(expected, 2)

        except Exception as e:
            print(f"[REVENUE] Ошибка расчёта ожидаемой: {e}")
            return plan

    def _calculate_average_daily(self, actual: float, date_from: str, date_to: str) -> float:
        """
        Рассчитать среднюю дневную выручку

        Args:
            actual: Фактическая выручка
            date_from: Начало периода
            date_to: Конец периода

        Returns:
            Средняя дневная выручка
        """
        try:
            start = datetime.strptime(date_from, '%Y-%m-%d')
            end = datetime.strptime(date_to, '%Y-%m-%d')
            total_days = (end - start).days + 1

            if total_days <= 0:
                return 0.0

            return round(actual / total_days, 2)

        except Exception as e:
            print(f"[REVENUE] Ошибка расчёта средней: {e}")
            return 0.0

    def get_metrics(
        self,
        date_from: str,
        date_to: str,
        bar_name: str = ''
    ) -> Optional[Dict]:
        """
        Получить все 4 метрики выручки

        Args:
            date_from: Начало периода 'YYYY-MM-DD'
            date_to: Конец периода 'YYYY-MM-DD'
            bar_name: Название бара или '' для общей

        Returns:
            Dict с метриками:
            - current: текущая выручка (факт)
            - plan: плановая выручка
            - expected: ожидаемая выручка (прогноз)
            - average: средняя дневная выручка
            - period_days: количество дней в периоде
            - completion_percent: % выполнения плана
        """
        try:
            # 1. План
            plan = self._calculate_period_plan(bar_name, date_from, date_to)
            if plan is None:
                plan = 0.0

            # 2. Факт (текущая)
            current = self._calculate_actual_revenue(date_from, date_to, bar_name)
            if current is None:
                current = 0.0

            # 3. Ожидаемая (прогноз)
            expected = self._calculate_expected_revenue(current, plan, date_from, date_to)

            # 4. Средняя дневная
            average = self._calculate_average_daily(current, date_from, date_to)

            # % выполнения плана
            completion_percent = round((current / plan * 100), 1) if plan > 0 else 0.0

            # Дней в периоде
            start = datetime.strptime(date_from, '%Y-%m-%d')
            end = datetime.strptime(date_to, '%Y-%m-%d')
            period_days = (end - start).days + 1

            return {
                'current': current,
                'plan': plan,
                'expected': expected,
                'average': average,
                'period_days': period_days,
                'completion_percent': completion_percent,
                'bar_name': bar_name if bar_name else 'Общая',
                'period': f"{date_from} — {date_to}"
            }

        except Exception as e:
            print(f"[REVENUE] Ошибка расчёта метрик: {e}")
            import traceback
            traceback.print_exc()
            return None


# Тестирование
if __name__ == "__main__":
    print("=" * 60)
    print("RevenueMetricsCalculator Test")
    print("=" * 60)

    calculator = RevenueMetricsCalculator()

    # Тест на прошлой неделе
    today = datetime.now()
    date_to = today - timedelta(days=today.weekday() + 1)  # Прошлое воскресенье
    date_from = date_to - timedelta(days=6)  # Прошлый понедельник

    date_from_str = date_from.strftime('%Y-%m-%d')
    date_to_str = date_to.strftime('%Y-%m-%d')

    print(f"\nPeriod: {date_from_str} - {date_to_str}")
    print("-" * 40)

    # Тест для одного бара
    print("\nKremenchugskaya:")
    metrics = calculator.get_metrics(date_from_str, date_to_str, "Кременчугская")
    if metrics:
        print(f"  Plan: {metrics['plan']:,.0f}")
        print(f"  Actual: {metrics['current']:,.0f}")
        print(f"  Expected: {metrics['expected']:,.0f}")
        print(f"  Average: {metrics['average']:,.0f}/day")
        print(f"  Completion: {metrics['completion_percent']}%")
    else:
        print("  No data")

    # Тест для всех баров
    print("\nTotal (all bars):")
    metrics = calculator.get_metrics(date_from_str, date_to_str, "")
    if metrics:
        print(f"  Plan: {metrics['plan']:,.0f}")
        print(f"  Actual: {metrics['current']:,.0f}")
        print(f"  Expected: {metrics['expected']:,.0f}")
        print(f"  Average: {metrics['average']:,.0f}/day")
        print(f"  Completion: {metrics['completion_percent']}%")
    else:
        print("  No data")

    print("\n" + "=" * 60)
