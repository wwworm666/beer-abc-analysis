"""
Калькулятор сравнения периодов
Сравнение двух периодов между собой, расчёт динамики
"""
from typing import Dict, List, Optional
from dashboardNovaev.dashboard_analysis import DashboardMetrics


class ComparisonCalculator:
    """Класс для сравнения метрик между двумя периодами"""

    def __init__(self):
        """Инициализация калькулятора"""
        self.calculator = DashboardMetrics()

    def compare_periods(
        self,
        period1_data: Dict,
        period2_data: Dict,
        metrics_list: List[str] = None
    ) -> Dict:
        """
        Сравнить два периода

        Args:
            period1_data: Dict - метрики первого периода
            period2_data: Dict - метрики второго периода
            metrics_list: List[str] - список метрик для сравнения (опционально)

        Returns:
            Dict - результаты сравнения с динамикой
        """
        # Если список метрик не указан, берём все
        if not metrics_list:
            metrics_list = [
                'total_revenue', 'total_checks', 'avg_check',
                'draft_share', 'bottles_share', 'kitchen_share',
                'draft_revenue', 'bottles_revenue', 'kitchen_revenue',
                'avg_markup', 'total_margin',
                'draft_markup', 'bottles_markup', 'kitchen_markup',
                'loyalty_points_written_off'
            ]

        comparison = {}

        for metric in metrics_list:
            value1 = period1_data.get(metric, 0)
            value2 = period2_data.get(metric, 0)

            # Рассчитываем абсолютную и относительную разницу
            diff_abs = value2 - value1
            diff_percent = self._calculate_percent_change(value1, value2)

            comparison[metric] = {
                'period1': value1,
                'period2': value2,
                'diff_abs': diff_abs,
                'diff_percent': diff_percent,
                'trend': 'up' if diff_abs > 0 else ('down' if diff_abs < 0 else 'stable')
            }

        return comparison

    def compare_venues(
        self,
        venues_data: Dict[str, Dict],
        metric: str
    ) -> List[Dict]:
        """
        Сравнить заведения по конкретной метрике

        Args:
            venues_data: Dict[str, Dict] - данные по заведениям
                {
                    'bolshoy': {метрики},
                    'ligovskiy': {метрики},
                    ...
                }
            metric: str - название метрики для сравнения

        Returns:
            List[Dict] - список заведений с сортировкой по метрике
        """
        comparison = []

        for venue_key, metrics in venues_data.items():
            if venue_key == 'all':  # Пропускаем сводные данные
                continue

            value = metrics.get(metric, 0)

            comparison.append({
                'venue_key': venue_key,
                'value': value,
                'metric': metric
            })

        # Сортируем по значению метрики (от большего к меньшему)
        comparison.sort(key=lambda x: x['value'], reverse=True)

        return comparison

    def get_top_changes(
        self,
        comparison: Dict,
        top_n: int = 5,
        by: str = 'abs'
    ) -> List[Dict]:
        """
        Получить топ изменений между периодами

        Args:
            comparison: Dict - результат compare_periods()
            top_n: int - количество топовых изменений
            by: str - по какому параметру сортировать ('abs' или 'percent')

        Returns:
            List[Dict] - топ изменений
        """
        changes = []

        for metric, data in comparison.items():
            changes.append({
                'metric': metric,
                'diff_abs': data['diff_abs'],
                'diff_percent': data['diff_percent'],
                'trend': data['trend'],
                'period1': data['period1'],
                'period2': data['period2']
            })

        # Сортируем по абсолютному значению изменения
        sort_key = 'diff_abs' if by == 'abs' else 'diff_percent'
        changes.sort(key=lambda x: abs(x[sort_key]), reverse=True)

        return changes[:top_n]

    def get_summary_insights(self, comparison: Dict) -> List[str]:
        """
        Получить текстовые выводы по сравнению

        Args:
            comparison: Dict - результат compare_periods()

        Returns:
            List[str] - список выводов
        """
        insights = []

        # Анализируем выручку
        revenue = comparison.get('total_revenue', {})
        if revenue.get('diff_percent', 0) > 0:
            insights.append(
                f"✅ Выручка выросла на {revenue['diff_percent']:.1f}% "
                f"(+{revenue['diff_abs']:,.0f} ₽)"
            )
        elif revenue.get('diff_percent', 0) < 0:
            insights.append(
                f"❌ Выручка снизилась на {abs(revenue['diff_percent']):.1f}% "
                f"({revenue['diff_abs']:,.0f} ₽)"
            )

        # Анализируем чеки
        checks = comparison.get('total_checks', {})
        if checks.get('diff_percent', 0) > 0:
            insights.append(
                f"✅ Количество чеков увеличилось на {checks['diff_percent']:.1f}%"
            )
        elif checks.get('diff_percent', 0) < 0:
            insights.append(
                f"⚠️ Количество чеков снизилось на {abs(checks['diff_percent']):.1f}%"
            )

        # Анализируем средний чек
        avg_check = comparison.get('avg_check', {})
        if avg_check.get('diff_percent', 0) > 0:
            insights.append(
                f"✅ Средний чек вырос на {avg_check['diff_percent']:.1f}%"
            )

        # Анализируем прибыль
        margin = comparison.get('total_margin', {})
        if margin.get('diff_percent', 0) > 0:
            insights.append(
                f"✅ Прибыль выросла на {margin['diff_percent']:.1f}%"
            )
        elif margin.get('diff_percent', 0) < 0:
            insights.append(
                f"❌ Прибыль снизилась на {abs(margin['diff_percent']):.1f}%"
            )

        # Анализируем доли категорий
        draft_share = comparison.get('draft_share', {})
        if abs(draft_share.get('diff_abs', 0)) > 2:
            trend = "выросла" if draft_share['diff_abs'] > 0 else "снизилась"
            insights.append(
                f"ℹ️ Доля розлива {trend} на {abs(draft_share['diff_abs']):.1f}%"
            )

        return insights

    def _calculate_percent_change(self, value1: float, value2: float) -> float:
        """
        Рассчитать процентное изменение

        Args:
            value1: float - значение периода 1
            value2: float - значение периода 2

        Returns:
            float - процентное изменение
        """
        if value1 == 0:
            return 0 if value2 == 0 else 100

        return ((value2 - value1) / value1) * 100
