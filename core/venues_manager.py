"""
Менеджер заведений - управление данными по барам
"""
from typing import Dict, List, Optional
from .venues_config import (
    VENUES,
    VENUE_KEYS_ORDERED,
    PHYSICAL_VENUES,
    KEY_TO_IIKO_NAME,
    IIKO_NAME_TO_KEY
)


class VenuesManager:
    """Класс для работы с заведениями"""

    def __init__(self):
        """Инициализация менеджера заведений"""
        self.venues = VENUES

    def get_all_venues(self) -> List[Dict]:
        """
        Получить список всех заведений в порядке отображения

        Returns:
            List[Dict] - список заведений с полной информацией
        """
        return [self.venues[key] for key in VENUE_KEYS_ORDERED]

    def get_venue(self, venue_key: str) -> Optional[Dict]:
        """
        Получить информацию о конкретном заведении

        Args:
            venue_key: str - ключ заведения ('bolshoy', 'ligovskiy', и т.д.)

        Returns:
            Dict - информация о заведении или None если не найдено
        """
        return self.venues.get(venue_key)

    def get_physical_venues(self) -> List[Dict]:
        """
        Получить список физических баров (без "all")

        Returns:
            List[Dict] - список физических заведений
        """
        return [self.venues[key] for key in PHYSICAL_VENUES]

    def validate_venue_key(self, venue_key: str) -> bool:
        """
        Проверить валидность ключа заведения

        Args:
            venue_key: str - ключ заведения

        Returns:
            bool - True если ключ валиден
        """
        return venue_key in self.venues

    def get_iiko_name(self, venue_key: str) -> Optional[str]:
        """
        Получить название заведения для API iiko

        Args:
            venue_key: str - ключ заведения

        Returns:
            str - название для iiko API или None для 'all'
        """
        return KEY_TO_IIKO_NAME.get(venue_key)

    def get_iiko_names_for_all(self) -> List[str]:
        """
        Получить список всех названий для запроса к iiko
        Используется для venue_key='all'

        Returns:
            List[str] - список названий всех физических баров
        """
        return [KEY_TO_IIKO_NAME[key] for key in PHYSICAL_VENUES]

    def get_key_by_iiko_name(self, iiko_name: str) -> Optional[str]:
        """
        Получить ключ заведения по названию в iiko

        Args:
            iiko_name: str - название в iiko API

        Returns:
            str - ключ заведения или None
        """
        return IIKO_NAME_TO_KEY.get(iiko_name)

    def get_venue_for_dropdown(self, venue_key: str) -> Dict:
        """
        Получить данные заведения для dropdown селектора

        Args:
            venue_key: str - ключ заведения

        Returns:
            Dict - данные для отображения в селекторе
        """
        venue = self.get_venue(venue_key)
        if not venue:
            return None

        return {
            'key': venue['key'],
            'label': f"{venue['icon']} {venue['full_name']}",
            'name': venue['name'],
            'icon': venue['icon']
        }

    def get_all_for_dropdown(self) -> List[Dict]:
        """
        Получить все заведения для dropdown селектора

        Returns:
            List[Dict] - список заведений для селектора
        """
        return [
            self.get_venue_for_dropdown(key)
            for key in VENUE_KEYS_ORDERED
        ]

    def aggregate_metrics(self, metrics_by_venue: Dict[str, Dict]) -> Dict:
        """
        Агрегировать метрики по всем заведениям (для venue_key='all')

        Args:
            metrics_by_venue: Dict[str, Dict] - метрики для каждого бара
                {
                    'bolshoy': {'total_revenue': 100000, 'total_checks': 500, ...},
                    'ligovskiy': {...},
                    ...
                }

        Returns:
            Dict - суммарные метрики по всем барам
        """
        aggregated = {
            'total_revenue': 0,
            'total_checks': 0,
            'draft_revenue': 0,
            'bottles_revenue': 0,
            'kitchen_revenue': 0,
            'total_margin': 0,
            'loyalty_points_written_off': 0
        }

        # Для взвешенной наценки нужны отдельные суммы
        weighted_markup_data = {
            'draft': {'total_cost': 0, 'total_weighted_markup': 0},
            'bottles': {'total_cost': 0, 'total_weighted_markup': 0},
            'kitchen': {'total_cost': 0, 'total_weighted_markup': 0},
            'all': {'total_cost': 0, 'total_weighted_markup': 0}
        }

        # Суммируем метрики
        for venue_key in PHYSICAL_VENUES:
            metrics = metrics_by_venue.get(venue_key)
            if not metrics:
                continue

            aggregated['total_revenue'] += metrics.get('total_revenue', 0)
            aggregated['total_checks'] += metrics.get('total_checks', 0)
            aggregated['draft_revenue'] += metrics.get('draft_revenue', 0)
            aggregated['bottles_revenue'] += metrics.get('bottles_revenue', 0)
            aggregated['kitchen_revenue'] += metrics.get('kitchen_revenue', 0)
            aggregated['total_margin'] += metrics.get('total_margin', 0)
            aggregated['loyalty_points_written_off'] += metrics.get('loyalty_points_written_off', 0)

        # Рассчитываем производные метрики
        if aggregated['total_revenue'] > 0:
            aggregated['draft_share'] = round(aggregated['draft_revenue'] / aggregated['total_revenue'] * 100, 2)
            aggregated['bottles_share'] = round(aggregated['bottles_revenue'] / aggregated['total_revenue'] * 100, 2)
            aggregated['kitchen_share'] = round(aggregated['kitchen_revenue'] / aggregated['total_revenue'] * 100, 2)
        else:
            aggregated['draft_share'] = 0
            aggregated['bottles_share'] = 0
            aggregated['kitchen_share'] = 0

        # Средний чек
        if aggregated['total_checks'] > 0:
            aggregated['avg_check'] = round(aggregated['total_revenue'] / aggregated['total_checks'], 2)
        else:
            aggregated['avg_check'] = 0

        # Средняя наценка (упрощенно - через маржу)
        if aggregated['total_revenue'] > 0:
            cost = aggregated['total_revenue'] - aggregated['total_margin']
            if cost > 0:
                aggregated['avg_markup'] = round(aggregated['total_margin'] / cost * 100, 2)
            else:
                aggregated['avg_markup'] = 0
        else:
            aggregated['avg_markup'] = 0

        # Наценки по категориям (упрощенно)
        # TODO: Для точного расчета нужны данные о себестоимости по категориям
        aggregated['draft_markup'] = aggregated['avg_markup']
        aggregated['bottles_markup'] = aggregated['avg_markup']
        aggregated['kitchen_markup'] = aggregated['avg_markup']

        return aggregated
