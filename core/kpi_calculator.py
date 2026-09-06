"""
Модуль расчёта KPI-бонусов сотрудников.

Формула (двухэтапная):
  1. Промежуточная премия за KPI = capped_ratio × base_premium
     где capped_ratio = max(0, min((Факт - Мин) / (Цель - Мин), max_ratio))
  2. Итого KPI = Σ промежуточных премий × Коэффициент
     где Коэффициент = смены / norm_shifts (по умолчанию 15)

Цели и минимумы — взвешенные по сменам на точках.
Конфигурация KPI (какие метрики используются) привязана к месяцу.

Штучные и суммовые показатели считаются НА КАССОВУЮ СМЕНУ (с августа 2026,
решение владельца 2026-09-06): одно абсолютное число «30 карт за месяц» нельзя
ставить и человеку с 5 сменами, и человеку с 25 — факт таких метрик растёт со
сменами, а коэффициент смен потом множит премию ещё раз. Поэтому у KPI на
«экстенсивной» метрике (см. `extensive` в AVAILABLE_METRICS) факт делится на
число кассовых смен за период, а цель и минимум задаются за одну смену.
Долевые и удельные метрики (доли, средний чек, наценка, выручка/смена) уже
«на единицу» и не меняются.

Направление метрики выводится из целей: цель выше минимума — «больше лучше»,
минимум выше цели — «меньше лучше» (опоздания, отмены). Пара «цель 0 / мин 0»
считается НЕ заданной: такая точка не участвует ни во взвешивании, ни в
коэффициенте (редактор сохраняет пустые поля нулями).
"""
import copy
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

# Первый месяц расчёта, с которого штучные метрики без явного флага `per_shift`
# в конфиге считаются «на смену» (владелец: «делаем начиная с 31 июля, для
# августа пересчитать по новым правилам»). Расчёт помесячный, поэтому граница —
# месяц: июль и раньше считаются как прежде, август и позже — на смену.
# Явный флаг в конфиге месяца всегда сильнее этой даты.
PER_SHIFT_FROM_MONTH = '2026-08'

# Единица «на смену» в подписях (страница ЗП, /me, /goals)
PER_SHIFT_UNIT_SUFFIX = '/смену'

# Знаков после запятой у значения «на смену»: штуки и часы за смену — дробные
# (1,6 карты за смену), рубли за смену остаются целыми
PER_SHIFT_DECIMALS = 2

# Каталог доступных метрик из EmployeeMetricsCalculator.calculate().
# Полный набор соответствует карточкам на странице /employee (дашборд сотрудника).
# extensive: факт растёт с числом смен (штуки, суммы, часы) — такие KPI считаются
#   на кассовую смену (см. докстринг модуля). Долевые и удельные метрики — нет.
# lower_is_better: подсказка редактору («меньше — лучше»: минимум ставят выше
#   цели). На формулу не влияет — направление выводится из цели и минимума.
AVAILABLE_METRICS = {
    'kitchen_share':       {'name': 'Доля кухни',              'unit': '%',  'decimals': 1},
    'draft_share':         {'name': 'Доля розлива',            'unit': '%',  'decimals': 1},
    'bottles_share':       {'name': 'Доля фасовки',            'unit': '%',  'decimals': 1},
    'avg_check':           {'name': 'Средний чек',             'unit': '₽',  'decimals': 0},
    'total_revenue':       {'name': 'Общая выручка',           'unit': '₽',  'decimals': 0, 'extensive': True},
    'revenue_per_shift':   {'name': 'Выручка/смена',           'unit': '₽',  'decimals': 0},
    'revenue_per_hour':    {'name': 'Выручка/час',             'unit': '₽',  'decimals': 0},
    'total_checks':        {'name': 'Кол-во чеков',            'unit': 'шт', 'decimals': 0, 'extensive': True},
    'avg_markup':          {'name': 'Средняя наценка',         'unit': '%',  'decimals': 1},
    'discount_percent':    {'name': '% скидок',                'unit': '%',  'decimals': 1},
    'cancelled_count':     {'name': 'Отмены/возвраты',         'unit': 'шт', 'decimals': 0, 'extensive': True, 'lower_is_better': True},
    'draft_revenue':       {'name': 'Выручка розлива',         'unit': '₽',  'decimals': 0, 'extensive': True},
    'bottles_revenue':     {'name': 'Выручка фасовки',         'unit': '₽',  'decimals': 0, 'extensive': True},
    'kitchen_revenue':     {'name': 'Выручка кухни',           'unit': '₽',  'decimals': 0, 'extensive': True},
    'shifts_count':        {'name': 'Количество смен',         'unit': 'шт', 'decimals': 0},
    'work_hours':          {'name': 'Часы работы',             'unit': 'ч',  'decimals': 1, 'extensive': True},
    'late_count':          {'name': 'Опоздания',               'unit': 'шт', 'decimals': 0, 'extensive': True, 'lower_is_better': True},
    'loyalty_cards_count': {'name': 'Новые карты лояльности',  'unit': 'шт', 'decimals': 0, 'extensive': True},
    'plan_fact_percent':   {'name': 'План/Факт',               'unit': '%',  'decimals': 1},
}

# Дефолтный конфиг KPI (если в месяце не указан kpi_config)
DEFAULT_KPI_CONFIG = {
    'kpi1': {'metric': 'kitchen_share', 'name': 'Доля кухни (%)'},
    'kpi2': {'metric': 'draft_share',   'name': 'Доля розлива (%)'},
    'kpi3': {'metric': 'avg_check',     'name': 'Средний чек (₽)'},
}

# Ключи ответа GET /api/kpi-targets, которые редактор шлёт обратно, но в файл
# они не пишутся (справочник метрик, граница «на смену», журнал конвертации)
NON_PERSISTENT_KEYS = ('available_metrics', 'per_shift_from_month',
                       'converted_from_monthly')


def is_extensive(metric: str) -> bool:
    """Метрика «растёт со сменами» — штуки, суммы, часы (см. AVAILABLE_METRICS)."""
    return bool((AVAILABLE_METRICS.get(metric) or {}).get('extensive'))


def metric_unit(metric: str, per_shift: bool = False) -> str:
    """Единица показателя для подписей: «шт», а на смену — «шт/смену»."""
    unit = (AVAILABLE_METRICS.get(metric) or {}).get('unit', '')
    return f"{unit}{PER_SHIFT_UNIT_SUFFIX}" if per_shift else unit


def metric_decimals(metric: str, per_shift: bool = False) -> int:
    """Знаки после запятой: у значения «на смену» штуки и часы дробные."""
    info = AVAILABLE_METRICS.get(metric) or {}
    decimals = int(info.get('decimals', 1))
    if per_shift and info.get('unit') != '₽':
        return max(decimals, PER_SHIFT_DECIMALS)
    return decimals


def targets_are_set(loc_targets) -> bool:
    """Заданы ли цели точки по KPI. Пара 0/0 — «не задано» (пустые поля
    редактора сохраняются нулями); отсутствие ключа — тоже не задано."""
    if not isinstance(loc_targets, dict):
        return False
    try:
        target = float(loc_targets.get('target') or 0)
        min_val = float(loc_targets.get('min') or 0)
    except (TypeError, ValueError):
        return False
    return not (target == 0 and min_val == 0)


def per_shift_effective(kpi_conf: dict) -> bool:
    """Считается ли KPI на смену: явный флаг конфига И экстенсивная метрика.
    Флаг на долевой метрике игнорируется — делить процент на смены бессмысленно."""
    if not isinstance(kpi_conf, dict):
        return False
    return bool(kpi_conf.get('per_shift')) and is_extensive(kpi_conf.get('metric', ''))


def normalize_month_data(month: str, month_data: dict, defaults: dict) -> Tuple[dict, dict]:
    """Привести конфиг месяца к явной форме «на смену».

    Для каждого KPI на экстенсивной метрике БЕЗ флага `per_shift` в месяце
    начиная с PER_SHIFT_FROM_MONTH: флаг ставится, а месячные цель/минимум по
    точкам делятся на норму смен — «30 карт за месяц при норме 15» = «2 за
    смену» (округление до сотых). Так расчёт августа по старому конфигу и
    редактор видят одни и те же числа; после первого сохранения месяц хранится
    уже в явном виде. Явный флаг (true/false) и месяцы до границы не трогаются.

    Returns:
        (копия данных месяца, {kpi_key: {'norm_shifts': N}} — что было сконвертировано)
    """
    data = copy.deepcopy(month_data or {})
    converted = {}
    kpi_config = data.get('kpi_config')
    if not isinstance(kpi_config, dict) or month < PER_SHIFT_FROM_MONTH:
        return data, converted

    norm = float((defaults or {}).get('norm_shifts') or 15)
    if norm <= 0:
        norm = 15.0

    for kpi_key, conf in kpi_config.items():
        if not isinstance(conf, dict) or 'per_shift' in conf:
            continue
        if not is_extensive(conf.get('metric', '')):
            continue
        conf['per_shift'] = True
        converted[kpi_key] = {'norm_shifts': norm}
        for loc, loc_targets in data.items():
            if loc == 'kpi_config' or not isinstance(loc_targets, dict):
                continue
            t = loc_targets.get(kpi_key)
            if not isinstance(t, dict):
                continue
            try:
                t['target'] = round(float(t.get('target') or 0) / norm, PER_SHIFT_DECIMALS)
                t['min'] = round(float(t.get('min') or 0) / norm, PER_SHIFT_DECIMALS)
            except (TypeError, ValueError):
                t['target'], t['min'] = 0, 0
    return data, converted


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
        """Полные данные как в файле (без нормализации «на смену»)."""
        return self._load()

    def get_editor_data(self) -> dict:
        """Данные для редактора целей и памятки /goals: месяцы в явной форме
        «на смену» (см. normalize_month_data) плюс граница и журнал конвертации.
        Ключи из NON_PERSISTENT_KEYS при сохранении отбрасываются."""
        raw = self._load()
        defaults = self.get_defaults()
        months, converted_all = {}, {}
        for month, month_data in (raw.get('months') or {}).items():
            months[month], converted = normalize_month_data(month, month_data, defaults)
            if converted:
                converted_all[month] = converted
        return {
            'defaults': copy.deepcopy(raw.get('defaults', defaults)),
            'months': months,
            'per_shift_from_month': PER_SHIFT_FROM_MONTH,
            'converted_from_monthly': converted_all,
        }

    def get_defaults(self) -> dict:
        data = self._load()
        return data.get('defaults', {
            'norm_shifts': 15,
            'kpi_pool': 15000,
            'base_premium': 5000,
            'max_ratio': 2,
        })

    def get_kpi_keys_for_month(self, month_str: str) -> List[str]:
        """
        Ключи KPI для месяца (динамическое количество).

        Берёт ключи из kpi_config месяца, отсортированные по номеру (kpi1, kpi2, ...).
        Если конфига нет — дефолтные 3 ключа.
        """
        kpi_config = self.get_kpi_config_for_month(month_str)
        keys = [k for k in kpi_config.keys() if k.startswith('kpi')]
        if not keys:
            return list(KPI_KEYS)
        # Сортируем по числовому суффиксу: kpi1, kpi2, kpi10
        return sorted(keys, key=lambda k: int(k[3:]) if k[3:].isdigit() else 0)

    def get_month_data(self, month_str: str) -> dict:
        """Все данные месяца (kpi_config + targets по точкам) в явной форме
        «на смену» — копия, кэш файла не меняется."""
        data = self._load()
        month_data = data.get('months', {}).get(month_str, {})
        normalized, _ = normalize_month_data(month_str, month_data, self.get_defaults())
        return normalized

    def get_kpi_config_for_month(self, month_str: str) -> dict:
        """
        Конфигурация KPI для месяца.

        Returns:
            {kpi1: {metric, name, per_shift?}, kpi2: ..., kpi3: ...}
        """
        month_data = self.get_month_data(month_str)
        return month_data.get('kpi_config', copy.deepcopy(DEFAULT_KPI_CONFIG))

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
        """Сохраняет полные данные в JSON.

        Служебные ключи ответа редактора (справочник метрик, граница «на
        смену», журнал конвертации) отбрасываются. Запись атомарная: во
        временный файл рядом и os.replace — оборванная запись не оставит
        полфайла (цели читает каждый расчёт ЗП).
        """
        if not isinstance(new_data, dict) or not isinstance(new_data.get('months'), dict):
            raise ValueError('Неверный формат данных: ожидается объект с "months"')
        to_save = {k: v for k, v in new_data.items() if k not in NON_PERSISTENT_KEYS}
        tmp_path = f"{self.filepath}.tmp"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(to_save, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.filepath)
            self._cache = to_save
            print(f"[KPI] Tseli sohraneny v {self.filepath}")
        except Exception as e:
            print(f"[KPI] Oshibka zapisi JSON: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
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

        Точка участвует в KPI, если её цели по этому KPI заданы
        (targets_are_set: есть ключ и пара не 0/0). KPI без единой заданной
        точки у сотрудника помечается no_targets — премия по нему 0, а не
        «максимум за цель 0».

        Returns:
            ({kpi_key: {target, min, shifts, no_targets, locations: {loc: {target, min, shifts}}}},
             total_shifts — смены сотрудника на точках, где задан ХОТЯ БЫ ОДИН KPI месяца)
        """
        if kpi_keys is None:
            kpi_keys = KPI_KEYS

        result = {}
        locations_with_any = set()

        for kpi_key in kpi_keys:
            weighted_target = 0.0
            weighted_min = 0.0
            shifts_with_targets = 0
            locations = {}

            for location, shift_count in shifts_per_location.items():
                loc_targets = month_targets.get(location, {})
                kpi_targets = loc_targets.get(kpi_key) if isinstance(loc_targets, dict) else None
                if not targets_are_set(kpi_targets):
                    continue

                target = float(kpi_targets['target'] or 0)
                min_val = float(kpi_targets['min'] or 0)
                weighted_target += shift_count * target
                weighted_min += shift_count * min_val
                shifts_with_targets += shift_count
                locations[location] = {'target': target, 'min': min_val, 'shifts': shift_count}
                locations_with_any.add(location)

            if shifts_with_targets > 0:
                result[kpi_key] = {
                    'target': round(weighted_target / shifts_with_targets, 2),
                    'min': round(weighted_min / shifts_with_targets, 2),
                    'shifts': shifts_with_targets,
                    'no_targets': False,
                    'locations': locations,
                }
            else:
                result[kpi_key] = {'target': 0, 'min': 0, 'shifts': 0,
                                   'no_targets': True, 'locations': {}}

        total_shifts = sum(count for loc, count in shifts_per_location.items()
                           if loc in locations_with_any)
        return result, total_shifts

    def calculate_premium(
        self,
        fact: float,
        target: float,
        min_val: float,
        defaults: dict,
        base_premium: float = None,
    ) -> dict:
        """
        Расчёт промежуточной премии по одному KPI (без учёта смен).

        Формула:
            ratio = (факт - мин) / (цель - мин)
            capped_ratio = max(0, min(ratio, max_ratio))
            intermediate_premium = capped_ratio × base_premium

        Направление — из целей. Цель выше минимума: «больше лучше», факт ниже
        минимума даёт 0. Минимум выше цели («меньше лучше»: опоздания, отмены):
        та же формула, факт выше минимума даёт 0, факт ниже цели — выше 1.
        Цель равна минимуму: ступенька — max_ratio при факте не ниже цели.

        Коэффициент (смены / норма) применяется позже к общей сумме.

        Args:
            base_premium: база за ОДИН KPI (фонд / количество KPI). Если None —
                          легаси-режим: берётся defaults['base_premium'].

        Returns:
            {ratio, capped_ratio, intermediate_premium}
        """
        if base_premium is None:
            base_premium = defaults.get('base_premium', 5000)
        max_ratio = defaults.get('max_ratio', 2)

        span = target - min_val
        if span == 0:
            ratio = float(max_ratio) if fact >= target else 0.0
        elif span > 0:
            # обычная метрика: больше — лучше
            ratio = 0.0 if fact < min_val else (fact - min_val) / span
        else:
            # инверсная метрика: меньше — лучше (минимум выше цели)
            ratio = 0.0 if fact > min_val else (fact - min_val) / span

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
        shifts_divisor: int = None,
    ) -> Optional[dict]:
        """
        Полный расчёт KPI-бонуса для сотрудника.

        Args:
            employee_name: имя сотрудника
            metrics: результат EmployeeMetricsCalculator.calculate() /
                     _build_kpi_metrics(); metrics['shifts_count'] — кассовые
                     смены за период, делитель показателей «на смену»
            shift_locations: {date: location} из cashshifts
            month: "YYYY-MM"
            shifts_divisor: явный делитель «на смену» (кассовые смены); если
                     None — metrics['shifts_count'], а без него — дни смен

        Returns:
            Полный результат расчёта или None если нет целей/смен
        """
        month_data = self.reader.get_month_data(month)
        month_targets = {k: v for k, v in month_data.items() if k != 'kpi_config'}
        if not month_targets:
            return None

        defaults = self.reader.get_defaults()
        norm_shifts = defaults.get('norm_shifts', 15)

        # Конфиг KPI из месяца (какие метрики используются, флаг «на смену»)
        kpi_config = month_data.get('kpi_config', copy.deepcopy(DEFAULT_KPI_CONFIG))

        # Динамическое количество KPI: ключи берём из конфига месяца
        kpi_keys = self.reader.get_kpi_keys_for_month(month)
        kpi_count = len(kpi_keys)

        # База за ОДИН KPI: фонд делится поровну на количество KPI.
        # Легаси (нет kpi_pool): фиксированная база за каждый KPI (сумма растёт с количеством).
        kpi_pool = defaults.get('kpi_pool')
        if kpi_pool is not None and kpi_count > 0:
            base_per_kpi = round(kpi_pool / kpi_count, 2)
        else:
            base_per_kpi = defaults.get('base_premium', 5000)
            kpi_pool = round(base_per_kpi * kpi_count, 2)

        # Считаем смены по точкам
        shifts_per_location = self.count_shifts_per_location(shift_locations)
        total_shifts_all = sum(shifts_per_location.values())

        if total_shifts_all == 0:
            return None

        # Взвешенные цели (только по точкам с целями)
        weighted_targets, total_shifts = self.calculate_weighted_targets(
            shifts_per_location, month_targets, kpi_keys
        )

        if total_shifts == 0:
            return None

        # Делитель показателей «на смену» — кассовые смены периода (мы считаем
        # смены по кассам). Без них в метриках — дни смен, чтобы не делить на 0.
        if shifts_divisor is None:
            shifts_divisor = metrics.get('shifts_count') or 0
        try:
            shifts_divisor = int(shifts_divisor or 0)
        except (TypeError, ValueError):
            shifts_divisor = 0
        if shifts_divisor <= 0:
            shifts_divisor = total_shifts_all

        # Расчёт по каждому KPI
        kpis = {}
        total_intermediate = 0.0

        for kpi_key in kpi_keys:
            # Берём metric field из конфига месяца
            kpi_conf = kpi_config.get(kpi_key, DEFAULT_KPI_CONFIG.get(kpi_key, {}))
            default_conf = DEFAULT_KPI_CONFIG.get(kpi_key, {})
            metric_field = kpi_conf.get('metric', default_conf.get('metric', ''))
            kpi_name = kpi_conf.get('name', kpi_key)
            per_shift = per_shift_effective({'metric': metric_field,
                                             'per_shift': kpi_conf.get('per_shift')})

            fact_raw = metrics.get(metric_field, 0) or 0
            fact = fact_raw / shifts_divisor if per_shift else fact_raw
            targets = weighted_targets.get(kpi_key) or {
                'target': 0, 'min': 0, 'shifts': 0, 'no_targets': True, 'locations': {}}

            if targets['no_targets']:
                # Ни на одной точке сотрудника этот KPI не задан — премии нет
                premium_result = {'ratio': 0.0, 'capped_ratio': 0.0,
                                  'intermediate_premium': 0.0}
            else:
                premium_result = self.calculate_premium(
                    fact=fact,
                    target=targets['target'],
                    min_val=targets['min'],
                    defaults=defaults,
                    base_premium=base_per_kpi,
                )

            kpi_row = {
                'name': kpi_name,
                'metric': metric_field,
                'fact': round(fact, 4 if per_shift else 2),
                'target': targets['target'],
                'min': targets['min'],
                'per_shift': per_shift,
                'unit': metric_unit(metric_field, per_shift),
                'decimals': metric_decimals(metric_field, per_shift),
                'no_targets': targets['no_targets'],
                'target_shifts': targets['shifts'],
                'location_targets': targets['locations'],
                **premium_result,
            }
            if per_shift:
                kpi_row['fact_raw'] = round(fact_raw, 2)
                kpi_row['shifts_divisor'] = shifts_divisor
            kpis[kpi_key] = kpi_row
            total_intermediate += premium_result['intermediate_premium']

        # Коэффициент применяется к итогу всех KPI
        koef = round(total_shifts / norm_shifts, 2)
        total_premium = round(total_intermediate * koef, 2)

        return {
            'employee_name': employee_name,
            'total_shifts': total_shifts,
            'koef': koef,
            'shifts_per_location': shifts_per_location,
            'cash_shifts': shifts_divisor,
            'kpis': kpis,
            'kpi_count': kpi_count,
            'kpi_pool': kpi_pool,
            'base_per_kpi': base_per_kpi,
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
