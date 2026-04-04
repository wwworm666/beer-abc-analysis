"""
Модуль расчёта KPI-бонусов сотрудников.

Формула (двухэтапная):
  1. Промежуточная премия за KPI = capped_ratio × base_premium
     где capped_ratio = max(0, min((Факт - Мин) / (Цель - Мин), max_ratio))
  2. Итого KPI = Σ промежуточных премий × Коэффициент
     где Коэффициент = смены / norm_shifts (по умолчанию 15)

Цели и минимумы — взвешенные по сменам на точках.
Конфигурация KPI (какие метрики используются) привязана к месяцу.
"""
import json
import os
from typing import Dict, List, Optional, Tuple

from core.employee_plans import BAR_NAME_MAPPING, normalize_bar_name

# Обратный маппинг: английские ключи → русские названия (для kpi_targets.json)
REVERSE_BAR_NAME_MAPPING = {v: k for k, v in BAR_NAME_MAPPING.items()}

# Маппинг популярных русских названий для поиска в kpi_targets.json
RUSSIAN_BAR_NAMES = {
    'kremenchugskaya': 'Кременчугская',
    'varshavskaya': 'Варшавская',
    'bolshoy': 'Большой пр В.О.',
    'ligovskiy': 'Лиговский',
}

KPI_KEYS = ['kpi1', 'kpi2', 'kpi3']

# Каталог доступных метрик из EmployeeMetricsCalculator.calculate()
AVAILABLE_METRICS = {
    'kitchen_share':    {'name': 'Доля кухни',        'unit': '%',  'decimals': 1},
    'draft_share':      {'name': 'Доля розлива',      'unit': '%',  'decimals': 1},
    'bottles_share':    {'name': 'Доля фасовки',      'unit': '%',  'decimals': 1},
    'avg_check':        {'name': 'Средний чек',       'unit': '₽',  'decimals': 0},
    'total_revenue':    {'name': 'Общая выручка',     'unit': '₽',  'decimals': 0},
    'revenue_per_shift':{'name': 'Выручка/смена',     'unit': '₽',  'decimals': 0},
    'revenue_per_hour': {'name': 'Выручка/час',       'unit': '₽',  'decimals': 0},
    'total_checks':     {'name': 'Кол-во чеков',      'unit': 'шт', 'decimals': 0},
    'avg_markup':       {'name': 'Средняя наценка',   'unit': '%',  'decimals': 1},
    'discount_percent': {'name': '% скидок',          'unit': '%',  'decimals': 1},
    'cancelled_count':  {'name': 'Отмены/возвраты',   'unit': 'шт', 'decimals': 0},
}

# Дефолтный конфиг KPI (если в месяце не указан kpi_config)
DEFAULT_KPI_CONFIG = {
    'kpi1': {'metric': 'kitchen_share', 'name': 'Доля кухни (%)'},
    'kpi2': {'metric': 'draft_share',   'name': 'Доля розлива (%)'},
    'kpi3': {'metric': 'avg_check',     'name': 'Средний чек (₽)'},
}


class KpiTargetsReader:
    """Загрузка и сохранение KPI-целей из JSON."""

    def __init__(self, filepath: str = None):
        if filepath is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            local_path = os.path.join(base_dir, 'data', 'kpi_targets.json')

            # Render Disk: /kultura — постоянное хранение (как taps_data.json)
            if os.path.exists('/kultura'):
                filepath = '/kultura/kpi_targets.json'
                # При первом деплое копируем данные из репо
                if not os.path.exists(filepath) and os.path.exists(local_path):
                    import shutil
                    shutil.copy2(local_path, filepath)
                    print(f"[KPI] Skopirovany tseli iz {local_path} -> {filepath}")
                print(f"[KPI] Render Disk: {filepath}")
            else:
                filepath = local_path
                print(f"[KPI] Lokalnyy put: {filepath}")

        self.filepath = filepath
        self._cache = None

    def _load(self) -> dict:
        if self._cache is not None:
            return self._cache

        if not os.path.exists(self.filepath):
            print(f"[KPI] Fayl ne nayden: {self.filepath}")
            return {}

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self._cache = json.load(f)
            return self._cache
        except Exception as e:
            print(f"[KPI] Oshibka chteniya JSON: {e}")
            return {}

    def get_all_data(self) -> dict:
        """Полные данные для UI-редактора."""
        return self._load()

    def get_defaults(self) -> dict:
        data = self._load()
        return data.get('defaults', {
            'norm_shifts': 15,
            'base_premium': 5000,
            'max_ratio': 2,
        })

    def get_month_data(self, month_str: str) -> dict:
        """Все данные месяца (kpi_config + targets по точкам)."""
        data = self._load()
        return data.get('months', {}).get(month_str, {})

    def get_kpi_config_for_month(self, month_str: str) -> dict:
        """
        Конфигурация KPI для месяца.

        Returns:
            {kpi1: {metric, name}, kpi2: ..., kpi3: ...}
        """
        month_data = self.get_month_data(month_str)
        return month_data.get('kpi_config', DEFAULT_KPI_CONFIG)

    def get_targets_for_month(self, month_str: str) -> dict:
        """
        Цели за месяц (только точки, без kpi_config).

        Returns:
            {location_name: {kpi1: {target, min}, kpi2: ..., kpi3: ...}}
        """
        month_data = self.get_month_data(month_str)
        # Фильтруем — всё кроме kpi_config
        return {k: v for k, v in month_data.items() if k != 'kpi_config'}

    def get_available_months(self) -> list:
        """Список доступных месяцев."""
        data = self._load()
        return sorted(data.get('months', {}).keys())

    def save_targets(self, new_data: dict):
        """Сохраняет полные данные в JSON."""
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
            self._cache = new_data
            print(f"[KPI] Tseli sohraneny v {self.filepath}")
        except Exception as e:
            print(f"[KPI] Oshibka zapisi JSON: {e}")
            raise

    def clear_cache(self):
        self._cache = None


class KpiCalculator:
    """Расчёт KPI-бонусов."""

    def __init__(self, targets_reader: KpiTargetsReader = None):
        self.reader = targets_reader or _get_reader()

    def count_shifts_per_location(self, shift_locations: dict) -> Dict[str, int]:
        """
        Считает смены по точкам.
        Возвращает русские названия для совместимости с kpi_targets.json

        Args:
            shift_locations: {date_str: location_name} из iiko cashshifts

        Returns:
            {russian_location_name: shift_count}
        """
        counts = {}
        for date_str, location in shift_locations.items():
            normalized = normalize_bar_name(location)
            # Сначала маппим на английский ключ
            english_key = BAR_NAME_MAPPING.get(normalized, normalized)
            # Затем конвертируем в русское название для kpi_targets.json
            russian_name = RUSSIAN_BAR_NAMES.get(english_key, english_key)
            counts[russian_name] = counts.get(russian_name, 0) + 1
        return counts

    def calculate_weighted_targets(
        self,
        shifts_per_location: Dict[str, int],
        month_targets: dict,
        kpi_keys: List[str] = None,
    ) -> Tuple[dict, int]:
        """
        Взвешенные цели по сменам на точках.

        Returns:
            ({kpi_key: {target: float, min: float}}, total_shifts)
        """
        if kpi_keys is None:
            kpi_keys = KPI_KEYS

        result = {}
        total_shifts = 0

        for kpi_key in kpi_keys:
            weighted_target = 0.0
            weighted_min = 0.0
            shifts_with_targets = 0

            for location, shift_count in shifts_per_location.items():
                loc_targets = month_targets.get(location, {})
                kpi_targets = loc_targets.get(kpi_key)
                if kpi_targets is None:
                    continue

                weighted_target += shift_count * kpi_targets['target']
                weighted_min += shift_count * kpi_targets['min']
                shifts_with_targets += shift_count

            if shifts_with_targets > 0:
                result[kpi_key] = {
                    'target': round(weighted_target / shifts_with_targets, 2),
                    'min': round(weighted_min / shifts_with_targets, 2),
                }
            else:
                result[kpi_key] = {'target': 0, 'min': 0}

            # Запомним total_shifts при первом KPI
            if kpi_key == kpi_keys[0]:
                total_shifts = shifts_with_targets

        return result, total_shifts

    def calculate_premium(
        self,
        fact: float,
        target: float,
        min_val: float,
        defaults: dict,
    ) -> dict:
        """
        Расчёт промежуточной премии по одному KPI (без учёта смен).

        Формула:
            ratio = (факт - мин) / (цель - мин)
            capped_ratio = max(0, min(ratio, max_ratio))
            intermediate_premium = capped_ratio × base_premium

        Коэффициент (смены / норма) применяется позже к общей сумме.

        Returns:
            {ratio, capped_ratio, intermediate_premium}
        """
        base_premium = defaults.get('base_premium', 5000)
        max_ratio = defaults.get('max_ratio', 2)

        if target == min_val:
            ratio = float(max_ratio) if fact >= target else 0.0
        elif fact < min_val:
            ratio = 0.0
        else:
            ratio = (fact - min_val) / (target - min_val)

        capped_ratio = max(0.0, min(ratio, float(max_ratio)))
        intermediate_premium = capped_ratio * base_premium

        return {
            'ratio': round(ratio, 4),
            'capped_ratio': round(capped_ratio, 4),
            'intermediate_premium': round(intermediate_premium, 2),
        }

    def calculate_employee(
        self,
        employee_name: str,
        metrics: dict,
        shift_locations: dict,
        month: str,
    ) -> Optional[dict]:
        """
        Полный расчёт KPI-бонуса для сотрудника.

        Args:
            employee_name: имя сотрудника
            metrics: результат EmployeeMetricsCalculator.calculate()
            shift_locations: {date: location} из cashshifts
            month: "YYYY-MM"

        Returns:
            Полный результат расчёта или None если нет целей/смен
        """
        month_targets = self.reader.get_targets_for_month(month)
        if not month_targets:
            return None

        defaults = self.reader.get_defaults()
        norm_shifts = defaults.get('norm_shifts', 15)

        # Конфиг KPI из месяца (какие метрики используются)
        kpi_config = self.reader.get_kpi_config_for_month(month)

        # Считаем смены по точкам
        shifts_per_location = self.count_shifts_per_location(shift_locations)
        total_shifts_all = sum(shifts_per_location.values())

        if total_shifts_all == 0:
            return None

        # Взвешенные цели (только по точкам с целями)
        weighted_targets, total_shifts = self.calculate_weighted_targets(
            shifts_per_location, month_targets, KPI_KEYS
        )

        if total_shifts == 0:
            return None

        # Расчёт по каждому KPI
        kpis = {}
        total_intermediate = 0.0

        for kpi_key in KPI_KEYS:
            # Берём metric field из конфига месяца
            kpi_conf = kpi_config.get(kpi_key, DEFAULT_KPI_CONFIG.get(kpi_key, {}))
            metric_field = kpi_conf.get('metric', DEFAULT_KPI_CONFIG[kpi_key]['metric'])
            kpi_name = kpi_conf.get('name', kpi_key)

            fact = metrics.get(metric_field, 0)
            targets = weighted_targets.get(kpi_key, {'target': 0, 'min': 0})

            premium_result = self.calculate_premium(
                fact=fact,
                target=targets['target'],
                min_val=targets['min'],
                defaults=defaults,
            )

            kpis[kpi_key] = {
                'name': kpi_name,
                'metric': metric_field,
                'fact': round(fact, 2),
                'target': targets['target'],
                'min': targets['min'],
                **premium_result,
            }
            total_intermediate += premium_result['intermediate_premium']

        # Коэффициент применяется к итогу всех KPI
        koef = round(total_shifts / norm_shifts, 2)
        total_premium = round(total_intermediate * koef, 2)

        return {
            'employee_name': employee_name,
            'total_shifts': total_shifts,
            'koef': koef,
            'shifts_per_location': shifts_per_location,
            'kpis': kpis,
            'total_premium': total_premium,
        }


# --- Глобальный экземпляр ---

_reader = None


def _get_reader() -> KpiTargetsReader:
    global _reader
    if _reader is None:
        _reader = KpiTargetsReader()
    return _reader


def clear_kpi_cache():
    global _reader
    if _reader is not None:
        _reader.clear_cache()
