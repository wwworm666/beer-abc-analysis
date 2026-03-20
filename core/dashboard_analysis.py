"""
Модуль расчета метрик дашборда Новаева
Работает ТОЛЬКО с сырыми данными из iiko OLAP API
"""


class DashboardMetrics:
    """Класс для расчета всех метрик дашборда из сырых OLAP данных"""

    def __init__(self):
        """Инициализация калькулятора метрик"""
        pass

    def calculate_metrics(self, all_sales_data):
        """
        Рассчитать все 15 метрик из комплексных OLAP данных.
        Один запрос содержит все категории (розлив + фасовка + кухня).

        Args:
            all_sales_data: dict - сырой ответ от get_all_sales_report()
                Содержит поле 'data' со всеми записями.
                Каждая запись имеет поле 'DishGroup.TopParent':
                - "Напитки Розлив" - разливное
                - "Напитки Фасовка" - фасовка
                - прочие - кухня

        Returns:
            dict с 15 метриками
        """

        # Извлекаем все записи
        all_records = all_sales_data.get('data', []) if all_sales_data else []

        # Разделяем по категориям на основе DishGroup.TopParent
        draft_records = []
        bottles_records = []
        kitchen_records = []

        for record in all_records:
            category = record.get('DishGroup.TopParent', '')
            if category == 'Напитки Розлив':
                draft_records.append(record)
            elif category == 'Напитки Фасовка':
                bottles_records.append(record)
            else:
                # Всё остальное - кухня
                kitchen_records.append(record)

        # 1-3. Выручка по категориям
        draft_revenue = self._sum_revenue(draft_records)
        bottles_revenue = self._sum_revenue(bottles_records)
        kitchen_revenue = self._sum_revenue(kitchen_records)

        total_revenue = draft_revenue + bottles_revenue + kitchen_revenue

        # 4-6. Доли категорий (%)
        draft_share = (draft_revenue / total_revenue * 100) if total_revenue > 0 else 0
        bottles_share = (bottles_revenue / total_revenue * 100) if total_revenue > 0 else 0
        kitchen_share = (kitchen_revenue / total_revenue * 100) if total_revenue > 0 else 0

        # 7. Количество чеков - считаем из уже полученных данных (без дополнительного OLAP запроса)
        total_checks = self._count_unique_orders(draft_records, bottles_records, kitchen_records)

        # 8. Средний чек
        avg_check = (total_revenue / total_checks) if total_checks > 0 else 0

        # 9-11. Наценка по категориям (%)
        draft_markup = self._calculate_weighted_markup(draft_records)
        bottles_markup = self._calculate_weighted_markup(bottles_records)
        kitchen_markup = self._calculate_weighted_markup(kitchen_records)

        # 12. Средняя наценка (взвешенная по себестоимости)
        avg_markup = self._calculate_weighted_markup(draft_records + bottles_records + kitchen_records)

        # 13. Прибыль (маржа)
        draft_margin = self._sum_margin(draft_records)
        bottles_margin = self._sum_margin(bottles_records)
        kitchen_margin = self._sum_margin(kitchen_records)
        total_margin = draft_margin + bottles_margin + kitchen_margin

        # 14. Списания баллов (сумма скидок из DiscountSum)
        loyalty_points = self._sum_discounts(draft_records + bottles_records + kitchen_records)

        # Формируем результат
        metrics = {
            'total_revenue': round(total_revenue, 2),
            'total_checks': total_checks,
            'avg_check': round(avg_check, 2),

            'draft_share': round(draft_share, 2),
            'bottles_share': round(bottles_share, 2),
            'kitchen_share': round(kitchen_share, 2),

            'draft_revenue': round(draft_revenue, 2),
            'bottles_revenue': round(bottles_revenue, 2),
            'kitchen_revenue': round(kitchen_revenue, 2),

            'avg_markup': round(avg_markup, 2),
            'total_margin': round(total_margin, 2),

            'draft_markup': round(draft_markup, 2),
            'bottles_markup': round(bottles_markup, 2),
            'kitchen_markup': round(kitchen_markup, 2),

            'loyalty_points_written_off': loyalty_points
        }

        return metrics

    def get_table_data(self, metrics):
        """
        Преобразовать метрики в формат таблицы для фронтенда

        Args:
            metrics: dict - результат calculate_metrics()

        Returns:
            list of dict - данные для таблицы
        """
        table = [
            {'metric': 'Выручка', 'value': metrics['total_revenue'], 'unit': '₽', 'format': 'money'},
            {'metric': 'Чеки', 'value': metrics['total_checks'], 'unit': 'шт', 'format': 'number'},
            {'metric': 'Средний чек', 'value': metrics['avg_check'], 'unit': '₽', 'format': 'money'},

            {'metric': 'Доля розлива', 'value': metrics['draft_share'], 'unit': '%', 'format': 'percent'},
            {'metric': 'Доля фасовки', 'value': metrics['bottles_share'], 'unit': '%', 'format': 'percent'},
            {'metric': 'Доля кухни', 'value': metrics['kitchen_share'], 'unit': '%', 'format': 'percent'},

            {'metric': 'Выручка розлив', 'value': metrics['draft_revenue'], 'unit': '₽', 'format': 'money'},
            {'metric': 'Выручка фасовка', 'value': metrics['bottles_revenue'], 'unit': '₽', 'format': 'money'},
            {'metric': 'Выручка кухня', 'value': metrics['kitchen_revenue'], 'unit': '₽', 'format': 'money'},

            {'metric': '% наценки', 'value': metrics['avg_markup'], 'unit': '%', 'format': 'percent'},
            {'metric': 'Прибыль', 'value': metrics['total_margin'], 'unit': '₽', 'format': 'money'},

            {'metric': 'Наценка розлив', 'value': metrics['draft_markup'], 'unit': '%', 'format': 'percent'},
            {'metric': 'Наценка фасовка', 'value': metrics['bottles_markup'], 'unit': '%', 'format': 'percent'},
            {'metric': 'Наценка кухня', 'value': metrics['kitchen_markup'], 'unit': '%', 'format': 'percent'},

            {'metric': 'Списания баллов', 'value': metrics['loyalty_points_written_off'], 'unit': 'баллов', 'format': 'number'}
        ]

        return table

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    def _sum_revenue(self, records):
        """
        Суммировать выручку из массива записей OLAP

        Args:
            records: list - массив записей с полем 'DishDiscountSumInt'

        Returns:
            float - общая выручка
        """
        total = 0.0
        for record in records:
            revenue = record.get('DishDiscountSumInt', 0)
            if revenue:
                try:
                    total += float(revenue)
                except (ValueError, TypeError):
                    continue
        return total

    def _sum_margin(self, records):
        """
        Суммировать маржу (прибыль) из массива записей OLAP
        Маржа = Выручка - Себестоимость

        Args:
            records: list - массив записей

        Returns:
            float - общая маржа
        """
        total = 0.0
        for record in records:
            revenue = record.get('DishDiscountSumInt', 0)
            cost = record.get('ProductCostBase.ProductCost', 0)

            try:
                revenue_float = float(revenue) if revenue else 0.0
                cost_float = float(cost) if cost else 0.0
                total += (revenue_float - cost_float)
            except (ValueError, TypeError):
                continue

        return total

    def _calculate_weighted_markup(self, records):
        """
        Рассчитать среднюю наценку, взвешенную по себестоимости

        Args:
            records: list - массив записей с полями:
                - 'ProductCostBase.MarkUp' (наценка в %)
                - 'ProductCostBase.ProductCost' (себестоимость)

        Returns:
            float - средняя наценка в %
        """
        total_weighted_markup = 0.0
        total_cost = 0.0

        for record in records:
            markup = record.get('ProductCostBase.MarkUp', 0)
            cost = record.get('ProductCostBase.ProductCost', 0)

            try:
                markup_float = float(markup) if markup else 0.0
                cost_float = float(cost) if cost else 0.0

                if cost_float > 0:
                    total_weighted_markup += markup_float * cost_float
                    total_cost += cost_float
            except (ValueError, TypeError):
                continue

        if total_cost > 0:
            return total_weighted_markup / total_cost
        return 0.0

    def _sum_discounts(self, records):
        """
        Суммировать скидки из массива записей OLAP

        Args:
            records: list - массив записей с полем 'DiscountSum'

        Returns:
            float - общая сумма скидок
        """
        total = 0.0
        for record in records:
            discount = record.get('DiscountSum', 0)
            if discount:
                try:
                    total += float(discount)
                except (ValueError, TypeError):
                    continue
        return total

    def _count_unique_orders(self, draft_records, bottles_records, kitchen_records):
        """
        Посчитать количество уникальных заказов (чеков) из уже полученных OLAP данных.
        Избегает дополнительного OLAP запроса get_orders_count().

        Args:
            draft_records: list - записи разливного пива
            bottles_records: list - записи фасованного пива
            kitchen_records: list - записи кухни

        Returns:
            int - количество уникальных заказов
        """
        unique_order_ids = set()

        # Объединяем все записи
        all_records = draft_records + bottles_records + kitchen_records

        # Собираем уникальные ID заказов из OLAP данных
        for record in all_records:
            # КЛЮЧЕВОЕ: используем UniqOrderId.Id (уникальный UUID заказа из iiko)
            # Это поле добавлено в groupByRowFields OLAP запроса
            order_id = record.get('UniqOrderId.Id')

            if order_id:
                unique_order_ids.add(str(order_id))
        return len(unique_order_ids)
