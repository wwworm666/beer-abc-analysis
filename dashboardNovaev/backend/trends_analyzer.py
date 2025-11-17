"""
Анализатор трендов
Анализ исторических данных, расчёт трендов и прогнозов
"""
from typing import Dict, List, Optional
import statistics


class TrendsAnalyzer:
    """Класс для анализа трендов метрик"""

    def __init__(self):
        """Инициализация анализатора"""
        pass

    def analyze_trend(
        self,
        historical_data: List[Dict],
        metric: str
    ) -> Dict:
        """
        Анализировать тренд для метрики

        Args:
            historical_data: List[Dict] - исторические данные
                [
                    {'period': '2024-11-01_2024-11-07', 'metrics': {...}},
                    ...
                ]
            metric: str - название метрики

        Returns:
            Dict - результаты анализа тренда
        """
        if not historical_data:
            return self._empty_trend_result()

        # Извлекаем значения метрики
        values = []
        periods = []

        for entry in historical_data:
            metrics = entry.get('metrics', {})
            value = metrics.get(metric, 0)

            if value is not None:
                values.append(float(value))
                periods.append(entry.get('period', ''))

        if not values:
            return self._empty_trend_result()

        # Рассчитываем статистики
        mean = statistics.mean(values)
        median = statistics.median(values)
        std_dev = statistics.stdev(values) if len(values) > 1 else 0

        # Находим макс и мин
        max_value = max(values)
        min_value = min(values)
        max_period = periods[values.index(max_value)]
        min_period = periods[values.index(min_value)]

        # Определяем тренд (линейная регрессия упрощенно)
        trend_direction, trend_percent = self._calculate_trend(values)

        # Прогноз на следующий период
        forecast = self._forecast_next(values)

        return {
            'metric': metric,
            'data_points': len(values),
            'values': values,
            'periods': periods,
            'statistics': {
                'mean': round(mean, 2),
                'median': round(median, 2),
                'std_dev': round(std_dev, 2),
                'max': max_value,
                'min': min_value,
                'max_period': max_period,
                'min_period': min_period
            },
            'trend': {
                'direction': trend_direction,  # 'up', 'down', 'stable'
                'percent_change': round(trend_percent, 2)
            },
            'forecast': {
                'next_period': round(forecast, 2),
                'confidence': self._calculate_confidence(std_dev, mean)
            }
        }

    def compare_to_average(
        self,
        current_value: float,
        historical_data: List[Dict],
        metric: str
    ) -> Dict:
        """
        Сравнить текущее значение со средним историческим

        Args:
            current_value: float - текущее значение метрики
            historical_data: List[Dict] - исторические данные
            metric: str - название метрики

        Returns:
            Dict - результаты сравнения
        """
        values = [
            float(entry['metrics'].get(metric, 0))
            for entry in historical_data
            if entry.get('metrics', {}).get(metric) is not None
        ]

        if not values:
            return {'comparison': 'no_data'}

        mean = statistics.mean(values)
        diff_abs = current_value - mean
        diff_percent = ((current_value - mean) / mean * 100) if mean != 0 else 0

        status = 'above' if diff_abs > 0 else ('below' if diff_abs < 0 else 'equal')

        return {
            'current': current_value,
            'historical_mean': round(mean, 2),
            'diff_abs': round(diff_abs, 2),
            'diff_percent': round(diff_percent, 2),
            'status': status
        }

    def detect_seasonality(
        self,
        historical_data: List[Dict],
        metric: str
    ) -> Dict:
        """
        Определить сезонность (если данных достаточно)

        Args:
            historical_data: List[Dict] - исторические данные (минимум год)
            metric: str - название метрики

        Returns:
            Dict - результаты анализа сезонности
        """
        if len(historical_data) < 12:
            return {'seasonality': 'insufficient_data'}

        values = [
            float(entry['metrics'].get(metric, 0))
            for entry in historical_data
            if entry.get('metrics', {}).get(metric) is not None
        ]

        if not values:
            return {'seasonality': 'no_data'}

        # Упрощенный анализ: разбиваем на квартили
        mean = statistics.mean(values)

        strong_weeks = [i for i, v in enumerate(values) if v > mean * 1.15]
        weak_weeks = [i for i, v in enumerate(values) if v < mean * 0.85]

        return {
            'seasonality': 'detected' if (strong_weeks or weak_weeks) else 'not_detected',
            'mean': round(mean, 2),
            'strong_periods': len(strong_weeks),
            'weak_periods': len(weak_weeks)
        }

    def _calculate_trend(self, values: List[float]) -> tuple:
        """
        Рассчитать направление тренда (упрощенный метод)

        Args:
            values: List[float] - значения метрики по периодам

        Returns:
            tuple - (direction, percent_change)
        """
        if len(values) < 2:
            return ('stable', 0)

        # Сравниваем первую и последнюю треть периода
        third = len(values) // 3
        if third == 0:
            third = 1

        first_third_avg = statistics.mean(values[:third])
        last_third_avg = statistics.mean(values[-third:])

        diff_percent = ((last_third_avg - first_third_avg) / first_third_avg * 100) if first_third_avg != 0 else 0

        # Определяем направление
        if abs(diff_percent) < 5:
            direction = 'stable'
        elif diff_percent > 0:
            direction = 'up'
        else:
            direction = 'down'

        return (direction, diff_percent)

    def _forecast_next(self, values: List[float]) -> float:
        """
        Прогноз следующего значения (простое скользящее среднее)

        Args:
            values: List[float] - значения метрики

        Returns:
            float - прогнозируемое значение
        """
        if not values:
            return 0

        # Используем последние 3 значения для прогноза
        window = min(3, len(values))
        recent_values = values[-window:]

        return statistics.mean(recent_values)

    def _calculate_confidence(self, std_dev: float, mean: float) -> str:
        """
        Рассчитать уровень доверия к прогнозу

        Args:
            std_dev: float - стандартное отклонение
            mean: float - среднее значение

        Returns:
            str - 'high', 'medium', 'low'
        """
        if mean == 0:
            return 'low'

        cv = (std_dev / mean) * 100  # Коэффициент вариации

        if cv < 10:
            return 'high'
        elif cv < 25:
            return 'medium'
        else:
            return 'low'

    def _empty_trend_result(self) -> Dict:
        """Пустой результат для случая когда нет данных"""
        return {
            'metric': '',
            'data_points': 0,
            'values': [],
            'periods': [],
            'statistics': {
                'mean': 0,
                'median': 0,
                'std_dev': 0,
                'max': 0,
                'min': 0
            },
            'trend': {
                'direction': 'stable',
                'percent_change': 0
            },
            'forecast': {
                'next_period': 0,
                'confidence': 'low'
            }
        }
