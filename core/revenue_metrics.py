"""
Модуль расчёта 4 ключевых метрик выручки для главной страницы

Метрики:
1. Текущая выручка — факт по данным OLAP за выбранный период
2. План — плановая выручка из bar_plans.json на период
3. Ожидаемая — прогноз на основе текущей динамики (тренд)
4. Средняя — среднедневная выручка за период
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from core.olap_reports import OlapReports
from core.plans_manager import PlansManager


class RevenueMetricsCalculator:
    """Калькулятор метрик выручки"""

    def __init__(self):
        self.plans_manager = PlansManager(data_file='data/bar_plans.json')
        self._plans_file = 'data/bar_plans.json'

    def _read_plans_file(self) -> Dict:
        """Прочитать файл планов bar_plans.json"""
        try:
            with open(self._plans_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[REVENUE] Ошибка чтения планов: {e}")
            return {'plans': {}}

    def _get_daily_plan(self, date_str: str, bar_name: str) -> Optional[float]:
        """
        Получить плановую выручку на конкретный день для бара

        Args:
            date_str: Дата в формате 'YYYY-MM-DD'
            bar_name: Название бара (как в bar_plans.json)

        Returns:
            Плановая выручка или None
        """
        plans_data = self._read_plans_file()
        plans = plans_data.get('plans', {})

        if date_str in plans:
            day_plan = plans[date_str]
            if bar_name in day_plan:
                return float(day_plan[bar_name])

        return None

    def _calculate_period_plan(self, bar_name: str, date_from: str, date_to: str) -> Optional[float]:
        """
        Рассчитать плановую выручку за период

        Args:
            bar_name: Название бара или '' для общей
            date_from: Начало периода 'YYYY-MM-DD'
            date_to: Конец периода 'YYYY-MM-DD'

        Returns:
            Плановая выручка за период или None
        """
        plans_data = self._read_plans_file()
        plans = plans_data.get('plans', {})

        # Определяем бары для расчёта
        if bar_name:
            bars_to_check = [bar_name]
        else:
            # Для "общей" суммируем все бары
            bars_to_check = ["Кременчугская", "Варшавская", "Большой пр В.О.", "Лиговский"]

        total_plan = 0.0
        days_found = 0

        # Генерируем даты в периоде
        current_date = datetime.strptime(date_from, '%Y-%m-%d')
        end_date = datetime.strptime(date_to, '%Y-%m-%d')

        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')

            if date_str in plans:
                day_plan = plans[date_str]

                for bar in bars_to_check:
                    # Пробуем разные варианты написания названия бара
                    bar_variants = [
                        bar,
                        bar.replace('.', ''),  # "Большой пр В.О" -> "Большой пр В.О"
                        bar.strip(),
                    ]

                    for variant in bar_variants:
                        if variant in day_plan:
                            total_plan += float(day_plan[variant])
                            break

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
