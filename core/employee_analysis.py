"""
Модуль для детального анализа эффективности сотрудника
"""

from typing import Dict, List, Optional


class EmployeeMetricsCalculator:
    """Класс для расчета метрик эффективности одного сотрудника"""

    # Системные пользователи для фильтрации
    SYSTEM_USERS = [
        'Пользователь для централизованной доставки',
        'Системный пользователь',
        'Неизвестно'
    ]

    def calculate(
        self,
        employee_name: str,
        aggregated_data: Optional[dict],
        draft_data: Optional[dict],
        bottles_data: Optional[dict],
        kitchen_data: Optional[dict],
        cancelled_data: Optional[dict],
        attendances: Optional[List[dict]] = None,
        plan_revenue: float = 0.0,
        date_from: str = None,
        date_to: str = None,
        shifts_count_override: int = None,
        total_hours_override: float = None,
        late_count_override: int = 0,
        loyalty_cards_count: int = 0,
        total_revenue_override: float = None
    ) -> dict:
        """
        Рассчитать все метрики для сотрудника

        Args:
            employee_name: Имя сотрудника
            aggregated_data: Агрегированные данные по сотрудникам (OrderNum, DishDiscountSumInt)
            draft_data: Данные разливного пива (OLAP)
            bottles_data: Данные фасовки (OLAP)
            kitchen_data: Данные кухни (OLAP)
            cancelled_data: Данные отмен/возвратов (OLAP)
            attendances: Данные о сменах (iiko attendance API) - deprecated
            plan_revenue: План выручки
            date_from: Дата начала периода (YYYY-MM-DD)
            date_to: Дата окончания периода (YYYY-MM-DD)
            shifts_count_override: Количество смен из кассовых смен
            total_hours_override: Часы работы из кассовых смен

        Returns:
            dict с метриками
        """
        # Получаем агрегированные данные для сотрудника
        # aggregated_data теперь keyed по AuthUser ("Авторизовал") — формат может отличаться от employee_name
        emp_aggregated = {}
        if aggregated_data:
            # 1. Точное совпадение
            if employee_name in aggregated_data:
                emp_aggregated = aggregated_data[employee_name]
            else:
                # 2. Поиск по словам (Артемий Новаев ↔ Новаев Артемий)
                emp_words = set(employee_name.lower().split())
                for auth_name, data in aggregated_data.items():
                    auth_words = set(auth_name.lower().split())
                    if emp_words == auth_words or (len(emp_words) >= 2 and emp_words.issubset(auth_words)):
                        emp_aggregated = data
                        break

        # Количество чеков — уникальные заказы из OLAP
        total_checks = int(emp_aggregated.get('UniqOrderId.OrdersCount', 0) or 0)
        discount_sum = float(emp_aggregated.get('DiscountSum', 0) or 0)

        # Выручка: приоритет — кассовые смены (override), fallback — OLAP
        if total_revenue_override is not None:
            total_revenue = total_revenue_override
        else:
            total_revenue = float(emp_aggregated.get('DishDiscountSumInt', 0) or 0)

        # Средний чек — считаем из OLAP (выручка OLAP / чеки OLAP), не мешая с кассовыми сменами
        olap_revenue = float(emp_aggregated.get('DishDiscountSumInt', 0) or 0)

        # Фильтруем записи по сотруднику для расчёта по категориям
        draft_records = self._filter_by_employee(draft_data, employee_name)
        bottles_records = self._filter_by_employee(bottles_data, employee_name)
        kitchen_records = self._filter_by_employee(kitchen_data, employee_name)

        # 1. Выручка по категориям
        draft_revenue = self._sum_revenue(draft_records)
        bottles_revenue = self._sum_revenue(bottles_records)
        kitchen_revenue = self._sum_revenue(kitchen_records)

        # 2. Доли категорий
        draft_share = (draft_revenue / total_revenue * 100) if total_revenue > 0 else 0
        bottles_share = (bottles_revenue / total_revenue * 100) if total_revenue > 0 else 0
        kitchen_share = (kitchen_revenue / total_revenue * 100) if total_revenue > 0 else 0

        # 3. Данные о сменах
        shifts_count = 0
        total_hours = 0.0

        # Приоритет: override параметры (из кассовых смен) > attendances (deprecated)
        if shifts_count_override is not None:
            shifts_count = shifts_count_override
        if total_hours_override is not None:
            total_hours = total_hours_override

        if shifts_count_override is None and total_hours_override is None and attendances:
            # DEPRECATED: fallback на attendance API
            filtered_attendances = []
            for a in attendances:
                shift_date = a.get('date')
                if shift_date and date_from and date_to:
                    if date_from <= shift_date <= date_to:
                        filtered_attendances.append(a)
                else:
                    filtered_attendances.append(a)

            shifts_count = len([a for a in filtered_attendances if a.get('duration_minutes')])
            total_hours = sum((a.get('duration_minutes') or 0) for a in filtered_attendances) / 60

        # 4. Выручка/смена и выручка/час
        revenue_per_shift = (total_revenue / shifts_count) if shifts_count > 0 else 0
        revenue_per_hour = (total_revenue / total_hours) if total_hours > 0 else 0

        # 5. Средний чек — из OLAP (оба значения из одного источника)
        avg_check = (olap_revenue / total_checks) if total_checks > 0 else 0

        # 6. Топ сортов пива (только напитки)
        drink_records = draft_records + bottles_records
        top_beers = self._get_top_beers(drink_records)

        # 7. Наценка (взвешенная средняя)
        all_records = draft_records + bottles_records + kitchen_records
        avg_markup = self._calculate_weighted_markup(all_records) * 100

        # 8. % скидок от выручки
        gross_revenue = total_revenue + discount_sum
        discount_percent = (discount_sum / gross_revenue * 100) if gross_revenue > 0 else 0

        # 9. Отмены/возвраты - количество удалённых чеков (напрямую из cancelled_data)
        cancelled_count = 0
        if cancelled_data and cancelled_data.get('data'):
            for record in cancelled_data['data']:
                if record.get('WaiterName') == employee_name:
                    cancelled_count = int(record.get('OrderNum', 0) or 0)
                    break

        # 10. План/факт выручки в процентах
        plan_fact_percent = (total_revenue / plan_revenue * 100) if plan_revenue > 0 else 0

        return {
            'employee_name': employee_name,
            'total_revenue': round(total_revenue, 2),

            # Доли по категориям
            'draft_share': round(draft_share, 2),
            'bottles_share': round(bottles_share, 2),
            'kitchen_share': round(kitchen_share, 2),

            # Выручка по категориям
            'draft_revenue': round(draft_revenue, 2),
            'bottles_revenue': round(bottles_revenue, 2),
            'kitchen_revenue': round(kitchen_revenue, 2),

            # Эффективность
            'shifts_count': shifts_count,
            'work_hours': round(total_hours, 1),
            'revenue_per_shift': round(revenue_per_shift, 2),
            'revenue_per_hour': round(revenue_per_hour, 2),

            # Продажи
            'top_beers': top_beers,

            # Чеки
            'total_checks': total_checks,
            'avg_check': round(avg_check, 2),

            # Наценка и скидки
            'avg_markup': round(avg_markup, 2),
            'discount_sum': round(discount_sum, 2),
            'discount_percent': round(discount_percent, 2),

            # Отмены - количество удалённых чеков
            'cancelled_count': cancelled_count,

            # План/факт
            'plan_revenue': round(plan_revenue, 2),
            'plan_fact_percent': round(plan_fact_percent, 1),

            # Опоздания (смены открытые позже 14:35)
            'late_count': late_count_override,

            # Новые карты лояльности
            'loyalty_cards_count': loyalty_cards_count
        }

    def _filter_by_employee(self, data: Optional[dict], employee_name: str) -> List[dict]:
        """Фильтрация записей по имени сотрудника"""
        if not data or not data.get('data'):
            return []
        return [r for r in data['data'] if r.get('WaiterName') == employee_name]

    def _sum_revenue(self, records: List[dict]) -> float:
        """Суммирование выручки (DishDiscountSumInt)"""
        total = 0.0
        for r in records:
            try:
                val = r.get('DishDiscountSumInt', 0)
                if val:
                    total += float(val)
            except (ValueError, TypeError):
                continue
        return total

    def _sum_field(self, records: List[dict], field: str) -> float:
        """Суммирование произвольного поля"""
        total = 0.0
        for r in records:
            try:
                val = r.get(field, 0)
                if val:
                    total += float(val)
            except (ValueError, TypeError):
                continue
        return total

    def _calculate_weighted_markup(self, records: List[dict]) -> float:
        """Расчет взвешенной наценки по себестоимости"""
        total_weighted = 0.0
        total_cost = 0.0

        for r in records:
            try:
                markup = r.get('ProductCostBase.MarkUp', 0)
                cost = r.get('ProductCostBase.ProductCost', 0)
                if markup and cost:
                    markup = float(markup)
                    cost = float(cost)
                    if cost > 0:
                        total_weighted += markup * cost
                        total_cost += cost
            except (ValueError, TypeError):
                continue

        return (total_weighted / total_cost) if total_cost > 0 else 0

    def _get_top_beers(self, records: List[dict], top_n: int = 10) -> List[dict]:
        """Получить топ продаваемых сортов пива"""
        if not records:
            return []

        # Группируем по названию блюда
        beer_sales = {}
        for r in records:
            dish_name = r.get('DishName', '')
            if dish_name:
                if dish_name not in beer_sales:
                    beer_sales[dish_name] = {'quantity': 0, 'revenue': 0.0}
                try:
                    qty = r.get('DishAmountInt', 0)
                    rev = r.get('DishDiscountSumInt', 0)
                    if qty:
                        beer_sales[dish_name]['quantity'] += int(qty)
                    if rev:
                        beer_sales[dish_name]['revenue'] += float(rev)
                except (ValueError, TypeError):
                    continue

        # Сортируем по выручке
        sorted_beers = sorted(
            beer_sales.items(),
            key=lambda x: x[1]['revenue'],
            reverse=True
        )

        return [
            {
                'name': name,
                'quantity': data['quantity'],
                'revenue': round(data['revenue'], 2)
            }
            for name, data in sorted_beers[:top_n]
        ]


def get_employees_from_waiter_data(data: dict) -> List[str]:
    """
    Извлечь уникальные имена сотрудников из OLAP данных

    Args:
        data: Результат OLAP запроса с WaiterName

    Returns:
        Отсортированный список уникальных имен сотрудников
    """
    if not data or not data.get('data'):
        return []

    system_users = [
        'Пользователь для централизованной доставки',
        'Системный пользователь',
        'Неизвестно',
        ''
    ]

    employees = set()
    for record in data['data']:
        name = record.get('WaiterName', '')
        if name and name not in system_users:
            employees.add(name)

    return sorted(list(employees))
