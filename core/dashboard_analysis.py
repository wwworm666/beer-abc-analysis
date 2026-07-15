"""
Модуль расчета метрик дашборда Новаева
Работает ТОЛЬКО с сырыми данными из iiko OLAP API
"""


class DashboardMetrics:
    """Класс для расчета всех метрик дашборда из сырых OLAP данных"""

    # Значения DishGroup.TopParent («Группа блюда 1-го уровня» в iiko).
    # Кухня = строго группа «ЕДА»; всё, что не попало в три именованные
    # категории (НАБОРЫ, Чай/Кофе, Газ и Пэт, ...), уходит в «Прочее».
    TOP_PARENT_DRAFT = 'Напитки Розлив'
    TOP_PARENT_BOTTLES = 'Напитки Фасовка'
    TOP_PARENT_KITCHEN = 'ЕДА'

    def __init__(self):
        """Инициализация калькулятора метрик"""
        pass

    def calculate_metrics(self, all_sales_data):
        """
        Рассчитать все метрики из комплексных OLAP данных.
        Один запрос содержит все категории (розлив + фасовка + кухня + прочее).

        Args:
            all_sales_data: dict - сырой ответ от get_all_sales_report()
                Содержит поле 'data' со всеми записями.
                Каждая запись имеет поле 'DishGroup.TopParent':
                - "Напитки Розлив" - разливное
                - "Напитки Фасовка" - фасовка
                - "ЕДА" - кухня
                - прочие (НАБОРЫ, Чай/Кофе, Газ и Пэт, ...) - «Прочее»

        Returns:
            dict с метриками. Категория «Прочее» (other_*) считается,
            но на дашборде пока не отображается (нет в get_table_data).
        """

        # Извлекаем все записи
        all_records = all_sales_data.get('data', []) if all_sales_data else []

        # Разделяем по категориям на основе DishGroup.TopParent
        draft_records = []
        bottles_records = []
        kitchen_records = []
        other_records = []

        for record in all_records:
            category = record.get('DishGroup.TopParent', '')
            if category == self.TOP_PARENT_DRAFT:
                draft_records.append(record)
            elif category == self.TOP_PARENT_BOTTLES:
                bottles_records.append(record)
            elif category == self.TOP_PARENT_KITCHEN:
                kitchen_records.append(record)
            else:
                other_records.append(record)

        # 1-4. Выручка по категориям
        draft_revenue = self._sum_revenue(draft_records)
        bottles_revenue = self._sum_revenue(bottles_records)
        kitchen_revenue = self._sum_revenue(kitchen_records)
        other_revenue = self._sum_revenue(other_records)

        total_revenue = draft_revenue + bottles_revenue + kitchen_revenue + other_revenue

        # 5-8. Доли категорий (%). Сумма четырёх долей = 100%,
        # но на экране показываются только розлив/фасовка/кухня.
        draft_share = (draft_revenue / total_revenue * 100) if total_revenue > 0 else 0
        bottles_share = (bottles_revenue / total_revenue * 100) if total_revenue > 0 else 0
        kitchen_share = (kitchen_revenue / total_revenue * 100) if total_revenue > 0 else 0
        other_share = (other_revenue / total_revenue * 100) if total_revenue > 0 else 0

        # Количество чеков - считаем из уже полученных данных (без дополнительного OLAP запроса)
        total_checks = self._count_unique_orders(all_records)

        # Средний чек
        avg_check = (total_revenue / total_checks) if total_checks > 0 else 0

        # Наценка по категориям (дробь: 2.84 = 284%)
        draft_markup = self._calculate_markup(draft_records)
        bottles_markup = self._calculate_markup(bottles_records)
        kitchen_markup = self._calculate_markup(kitchen_records)
        other_markup = self._calculate_markup(other_records)

        # Средняя наценка по всем записям (включая «Прочее») —
        # совпадает со строкой «Итого» OLAP-отчёта iiko
        avg_markup = self._calculate_markup(all_records)

        # Прибыль (маржа)
        draft_margin = self._sum_margin(draft_records)
        bottles_margin = self._sum_margin(bottles_records)
        kitchen_margin = self._sum_margin(kitchen_records)
        other_margin = self._sum_margin(other_records)
        total_margin = draft_margin + bottles_margin + kitchen_margin + other_margin

        # Списания баллов (сумма скидок из DiscountSum)
        loyalty_points = self._sum_discounts(all_records)

        # Формируем результат.
        # Наценки округляются до 4 знаков: это дробь (2.2448),
        # после ×100 на фронте получается 224.48% — как в iiko.
        metrics = {
            'total_revenue': round(total_revenue, 2),
            'total_checks': total_checks,
            'avg_check': round(avg_check, 2),

            'draft_share': round(draft_share, 2),
            'bottles_share': round(bottles_share, 2),
            'kitchen_share': round(kitchen_share, 2),
            'other_share': round(other_share, 2),

            'draft_revenue': round(draft_revenue, 2),
            'bottles_revenue': round(bottles_revenue, 2),
            'kitchen_revenue': round(kitchen_revenue, 2),
            'other_revenue': round(other_revenue, 2),

            'avg_markup': round(avg_markup, 4),
            'total_margin': round(total_margin, 2),

            'draft_markup': round(draft_markup, 4),
            'bottles_markup': round(bottles_markup, 4),
            'kitchen_markup': round(kitchen_markup, 4),
            'other_markup': round(other_markup, 4),

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

    def _calculate_markup(self, records):
        """
        Рассчитать наценку агрегатом, как строка «Итого» OLAP-отчёта iiko:

            наценка = (Σ выручка - Σ себестоимость) / Σ себестоимость

        Строки с нулевой себестоимостью (позиции без техкарты/оприходования)
        участвуют выручкой в числителе — ровно как в iiko. Раньше здесь было
        средневзвешенное построчного поля MarkUp с выбросом таких строк,
        из-за чего наценка расходилась с iiko (фасовка: 134% против 139%).

        Args:
            records: list - массив записей с полями:
                - 'DishDiscountSumInt' (выручка со скидкой)
                - 'ProductCostBase.ProductCost' (себестоимость)

        Returns:
            float - наценка как дробь (2.84 = 284%); 0.0 если себестоимость <= 0
        """
        total_revenue = 0.0
        total_cost = 0.0

        for record in records:
            revenue = record.get('DishDiscountSumInt', 0)
            cost = record.get('ProductCostBase.ProductCost', 0)

            try:
                total_revenue += float(revenue) if revenue else 0.0
                total_cost += float(cost) if cost else 0.0
            except (ValueError, TypeError):
                continue

        if total_cost > 0:
            return (total_revenue - total_cost) / total_cost
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

    def _count_unique_orders(self, all_records):
        """
        Посчитать количество уникальных заказов (чеков) из уже полученных OLAP данных.
        Избегает дополнительного OLAP запроса get_orders_count().

        Args:
            all_records: list - все записи OLAP (без разбивки по категориям)

        Returns:
            int - количество уникальных заказов
        """
        unique_order_ids = set()

        # Собираем уникальные ID заказов из OLAP данных
        for record in all_records:
            # КЛЮЧЕВОЕ: используем UniqOrderId.Id (уникальный UUID заказа из iiko)
            # Это поле добавлено в groupByRowFields OLAP запроса
            order_id = record.get('UniqOrderId.Id')

            if order_id:
                unique_order_ids.add(str(order_id))
        return len(unique_order_ids)

    # ========== ДОПОЛНИТЕЛЬНЫЕ РАЗРЕЗЫ (для месячного отчёта) ==========

    # Россия = локальное производство; любая другая страна (или пусто) = импорт.
    # Решение бизнеса: классификация по полю DishForeignName (страна).
    LOCAL_COUNTRY = 'Россия'

    def local_import_revenue(self, records, top_parent):
        """
        Разбить выручку категории на локальную и импортную по стране (DishForeignName).

        Локал = страна 'Россия'. Импорт = все остальные страны (и пустое значение).

        Args:
            records: list - сырые OLAP записи (get_all_sales_report -> data)
            top_parent: str - 'Напитки Фасовка' или 'Напитки Розлив'

        Returns:
            dict - {'local': ₽, 'import': ₽}
        """
        local_sum = 0.0
        import_sum = 0.0
        for record in records:
            if record.get('DishGroup.TopParent', '') != top_parent:
                continue
            revenue = record.get('DishDiscountSumInt', 0)
            try:
                revenue = float(revenue) if revenue else 0.0
            except (ValueError, TypeError):
                continue
            country = (record.get('DishForeignName') or '').strip()
            if country == self.LOCAL_COUNTRY:
                local_sum += revenue
            else:
                import_sum += revenue
        return {'local': round(local_sum, 2), 'import': round(import_sum, 2)}

    def category_units(self, records, top_parent):
        """
        Сумма проданных единиц (DishAmountInt) по категории.

        Для фасовки единица = бутылка/банка, для розлива = порция (0.3/0.5 л).

        Args:
            records: list - сырые OLAP записи
            top_parent: str - 'Напитки Фасовка' или 'Напитки Розлив'

        Returns:
            float - суммарное количество единиц
        """
        total = 0.0
        for record in records:
            if record.get('DishGroup.TopParent', '') != top_parent:
                continue
            amount = record.get('DishAmountInt', 0)
            try:
                total += float(amount) if amount else 0.0
            except (ValueError, TypeError):
                continue
        return round(total, 2)

    def revenue_card_split(self, rfm_rows):
        """
        Разбить выручку на «по картам лояльности» и «без карты».

        Признак карты — непустое поле Delivery.CustomerCardNumber в строках
        RFM-отчёта (get_rfm_report).

        Args:
            rfm_rows: list - строки get_rfm_report -> data

        Returns:
            dict - {'card': ₽, 'nocard': ₽}
        """
        card_sum = 0.0
        nocard_sum = 0.0
        for row in rfm_rows:
            card = (row.get('Delivery.CustomerCardNumber') or '').strip()
            revenue = row.get('DishDiscountSumInt', 0)
            try:
                revenue = float(revenue) if revenue else 0.0
            except (ValueError, TypeError):
                continue
            if card:
                card_sum += revenue
            else:
                nocard_sum += revenue
        return {'card': round(card_sum, 2), 'nocard': round(nocard_sum, 2)}
