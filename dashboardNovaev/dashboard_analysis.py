"""
Модуль аналитики для дашборда Новаева
Расчет ключевых метрик бизнеса: выручка, чеки, доли категорий, наценки и т.д.
"""

import pandas as pd
from datetime import datetime


class DashboardAnalytics:
    """Класс для расчета всех метрик дашборда"""

    def __init__(self, draft_data=None, bottles_data=None, kitchen_data=None):
        """
        Инициализация с данными из разных источников

        Args:
            draft_data: DataFrame с данными по разливному пиву
            bottles_data: DataFrame с данными по фасовке
            kitchen_data: DataFrame с данными по кухне
        """
        self.draft_df = draft_data if draft_data is not None else pd.DataFrame()
        self.bottles_df = bottles_data if bottles_data is not None else pd.DataFrame()
        self.kitchen_df = kitchen_data if kitchen_data is not None else pd.DataFrame()

    def calculate_all_metrics(self, bar_name=None):
        """
        Рассчитать все метрики для дашборда

        Args:
            bar_name: Название бара (если None, то общая по всем барам)

        Returns:
            dict с всеми метриками
        """
        # Фильтруем данные по бару если нужно
        draft_df = self._filter_by_bar(self.draft_df, bar_name)
        bottles_df = self._filter_by_bar(self.bottles_df, bar_name)
        kitchen_df = self._filter_by_bar(self.kitchen_df, bar_name)

        # Расчет метрик
        metrics = {}

        # 1. Выручка (общая)
        draft_revenue = self._calculate_revenue(draft_df)
        bottles_revenue = self._calculate_revenue(bottles_df)
        kitchen_revenue = self._calculate_revenue(kitchen_df)
        total_revenue = draft_revenue + bottles_revenue + kitchen_revenue

        metrics['total_revenue'] = round(total_revenue, 2)
        metrics['draft_revenue'] = round(draft_revenue, 2)
        metrics['bottles_revenue'] = round(bottles_revenue, 2)
        metrics['kitchen_revenue'] = round(kitchen_revenue, 2)

        # 2. Количество чеков
        total_checks = self._count_checks(draft_df, bottles_df, kitchen_df)
        metrics['total_checks'] = total_checks

        # 3. Средний чек
        metrics['avg_check'] = round(total_revenue / total_checks, 2) if total_checks > 0 else 0

        # 4-6. Доли категорий (%)
        if total_revenue > 0:
            metrics['draft_share'] = round((draft_revenue / total_revenue) * 100, 2)
            metrics['bottles_share'] = round((bottles_revenue / total_revenue) * 100, 2)
            metrics['kitchen_share'] = round((kitchen_revenue / total_revenue) * 100, 2)
        else:
            metrics['draft_share'] = 0
            metrics['bottles_share'] = 0
            metrics['kitchen_share'] = 0

        # 7-9. Выручка по категориям (уже посчитали выше)
        # Дублируем для удобства

        # 10. Средняя наценка (%)
        draft_markup = self._calculate_avg_markup(draft_df)
        bottles_markup = self._calculate_avg_markup(bottles_df)
        kitchen_markup = self._calculate_avg_markup(kitchen_df)

        # Взвешенная средняя наценка
        total_cost = self._calculate_total_cost(draft_df) + self._calculate_total_cost(bottles_df) + self._calculate_total_cost(kitchen_df)
        if total_cost > 0:
            weighted_markup = ((total_revenue - total_cost) / total_cost) * 100
            metrics['avg_markup'] = round(weighted_markup, 2)
        else:
            metrics['avg_markup'] = 0

        # 11. Прибыль (маржа)
        draft_margin = self._calculate_margin(draft_df)
        bottles_margin = self._calculate_margin(bottles_df)
        kitchen_margin = self._calculate_margin(kitchen_df)
        total_margin = draft_margin + bottles_margin + kitchen_margin

        metrics['total_margin'] = round(total_margin, 2)

        # 12-14. Наценка по категориям
        metrics['draft_markup'] = round(draft_markup, 2)
        metrics['bottles_markup'] = round(bottles_markup, 2)
        metrics['kitchen_markup'] = round(kitchen_markup, 2)

        # 15. Списания баллов (заглушка - нужно уточнить источник данных)
        metrics['loyalty_points_written_off'] = 0

        return metrics

    def _filter_by_bar(self, df, bar_name):
        """Фильтрация DataFrame по названию бара"""
        if df.empty or bar_name is None:
            return df

        # Проверяем наличие колонки с баром
        if 'DepartmentName' in df.columns:
            return df[df['DepartmentName'] == bar_name].copy()
        elif 'Department' in df.columns:
            return df[df['Department'] == bar_name].copy()

        return df

    def _calculate_revenue(self, df):
        """Расчет выручки из DataFrame"""
        if df.empty:
            return 0.0

        # Разные названия колонок в разных отчетах
        if 'DishDiscountSumInt' in df.columns:
            return float(df['DishDiscountSumInt'].sum())
        elif 'TotalRevenue' in df.columns:
            return float(df['TotalRevenue'].sum())
        elif 'DishAmountInt' in df.columns:
            return float(df['DishAmountInt'].sum())

        return 0.0

    def _count_checks(self, *dfs):
        """Подсчет уникальных чеков из нескольких DataFrame"""
        all_orders = set()

        for df in dfs:
            if df.empty:
                continue

            # Ищем колонку с ID заказа
            if 'OrderId' in df.columns:
                all_orders.update(df['OrderId'].dropna().unique())
            elif 'OrderNum' in df.columns:
                all_orders.update(df['OrderNum'].dropna().unique())

        return len(all_orders) if all_orders else 0

    def _calculate_avg_markup(self, df):
        """Расчет средней наценки в процентах"""
        if df.empty:
            return 0.0

        # Метод 1: если есть готовая колонка с наценкой
        if 'ProductCostBase.MarkUp' in df.columns:
            markup_values = pd.to_numeric(df['ProductCostBase.MarkUp'], errors='coerce')
            return float(markup_values.mean()) if not markup_values.isna().all() else 0.0

        # Метод 2: если есть AvgMarkupPercent
        if 'AvgMarkupPercent' in df.columns:
            return float(df['AvgMarkupPercent'].mean())

        # Метод 3: рассчитываем из выручки и себестоимости
        revenue = self._calculate_revenue(df)
        cost = self._calculate_total_cost(df)

        if cost > 0:
            return ((revenue - cost) / cost) * 100

        return 0.0

    def _calculate_total_cost(self, df):
        """Расчет общей себестоимости"""
        if df.empty:
            return 0.0

        if 'ProductCostBase.ProductCost' in df.columns:
            return float(pd.to_numeric(df['ProductCostBase.ProductCost'], errors='coerce').sum())
        elif 'TotalCost' in df.columns:
            return float(df['TotalCost'].sum())

        return 0.0

    def _calculate_margin(self, df):
        """Расчет маржи (прибыли)"""
        if df.empty:
            return 0.0

        # Если есть готовая колонка Margin
        if 'Margin' in df.columns:
            return float(df['Margin'].sum())

        # Если есть TotalMargin
        if 'TotalMargin' in df.columns:
            return float(df['TotalMargin'].sum())

        # Рассчитываем: Выручка - Себестоимость
        revenue = self._calculate_revenue(df)
        cost = self._calculate_total_cost(df)

        return revenue - cost

    def get_metrics_table_data(self, bar_name=None):
        """
        Получить данные в формате таблицы для отображения

        Returns:
            list of dict - каждая строка таблицы
        """
        metrics = self.calculate_all_metrics(bar_name)

        # Формируем таблицу
        table_data = [
            {
                'metric': 'Выручка',
                'value': metrics['total_revenue'],
                'unit': '₽',
                'format': 'money'
            },
            {
                'metric': 'Чеки',
                'value': metrics['total_checks'],
                'unit': 'шт',
                'format': 'number'
            },
            {
                'metric': 'Средний чек',
                'value': metrics['avg_check'],
                'unit': '₽',
                'format': 'money'
            },
            {
                'metric': 'Доля розлива',
                'value': metrics['draft_share'],
                'unit': '%',
                'format': 'percent'
            },
            {
                'metric': 'Доля фасовки',
                'value': metrics['bottles_share'],
                'unit': '%',
                'format': 'percent'
            },
            {
                'metric': 'Доля кухни',
                'value': metrics['kitchen_share'],
                'unit': '%',
                'format': 'percent'
            },
            {
                'metric': 'Выручка розлив',
                'value': metrics['draft_revenue'],
                'unit': '₽',
                'format': 'money'
            },
            {
                'metric': 'Выручка фасовка',
                'value': metrics['bottles_revenue'],
                'unit': '₽',
                'format': 'money'
            },
            {
                'metric': 'Выручка кухня',
                'value': metrics['kitchen_revenue'],
                'unit': '₽',
                'format': 'money'
            },
            {
                'metric': '% наценки',
                'value': metrics['avg_markup'],
                'unit': '%',
                'format': 'percent'
            },
            {
                'metric': 'Прибыль',
                'value': metrics['total_margin'],
                'unit': '₽',
                'format': 'money'
            },
            {
                'metric': 'Наценка розлив',
                'value': metrics['draft_markup'],
                'unit': '%',
                'format': 'percent'
            },
            {
                'metric': 'Наценка фасовка',
                'value': metrics['bottles_markup'],
                'unit': '%',
                'format': 'percent'
            },
            {
                'metric': 'Наценка кухня',
                'value': metrics['kitchen_markup'],
                'unit': '%',
                'format': 'percent'
            },
            {
                'metric': 'Списания баллов',
                'value': metrics['loyalty_points_written_off'],
                'unit': 'баллов',
                'format': 'number'
            }
        ]

        return table_data
