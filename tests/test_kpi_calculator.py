"""Тесты калькулятора KPI (core/kpi_calculator.py).

Закрывают решение владельца от 2026-09-06 «штучные KPI считаются от количества
смен» и две ошибки формулы, найденные при разборе страницы ЗП:
инверсные метрики никогда не платили (защита «факт ниже минимума» срабатывала
на любом хорошем факте), а пустые цели 0/0 давали максимальный множитель.

Запуск: python -m pytest tests/test_kpi_calculator.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.kpi_calculator import (  # noqa: E402
    NON_PERSISTENT_KEYS, PER_SHIFT_FROM_MONTH, KpiCalculator, KpiTargetsReader,
    is_extensive, metric_decimals, metric_unit, normalize_month_data,
    targets_are_set,
)

LOCS = ['Кременчугская', 'Варшавская', 'Лиговский', 'Большой пр В.О.']
DEFAULTS = {'norm_shifts': 15, 'kpi_pool': 15000, 'base_premium': 5000, 'max_ratio': 2}
KITCHEN = {'metric': 'kitchen_share', 'name': 'Доля кухни (%)'}
CARDS = {'metric': 'loyalty_cards_count', 'name': 'Новые карты лояльности (шт)'}


def month_data(config, targets):
    """config: {kpi_key: conf}; targets: {kpi_key: (target, min)} для всех точек
    или {loc: {kpi_key: (target, min)}} для отдельных точек."""
    data = {'kpi_config': json.loads(json.dumps(config))}
    for loc in LOCS:
        per_loc = targets.get(loc) if loc in targets else targets
        data[loc] = {k: {'target': t, 'min': m} for k, (t, m) in per_loc.items()}
    return data


def make_reader(tmp_path, months, defaults=DEFAULTS):
    path = tmp_path / 'kpi_targets.json'
    path.write_text(json.dumps({'defaults': defaults, 'months': months}, ensure_ascii=False),
                    encoding='utf-8')
    return KpiTargetsReader(str(path))


def shifts(n, loc='Пивная культура', month='2026-08'):
    """{дата: точка} — n дней смен на точке (как shift_locations из iiko)."""
    return {f'{month}-{i + 1:02d}': loc for i in range(n)}


AUG = {'2026-08': month_data({'kpi1': KITCHEN, 'kpi2': CARDS},
                             {'kpi1': (18, 13), 'kpi2': (30, 10)})}
JUL = {'2026-07': month_data({'kpi1': KITCHEN, 'kpi2': CARDS},
                             {'kpi1': (18, 13), 'kpi2': (30, 10)})}


# ==================== «на смену» ====================

def test_owner_example_same_rate_gives_same_ratio(tmp_path):
    """5 смен и 8 карт против 25 смен и 40 карт — одинаковая отдача 1,6 карты
    за смену, одинаковый множитель; разница в деньгах только через коэффициент."""
    calc = KpiCalculator(make_reader(tmp_path, AUG))
    a = calc.calculate_employee('A', {'kitchen_share': 15.5, 'loyalty_cards_count': 8,
                                      'shifts_count': 5}, shifts(5), '2026-08')
    b = calc.calculate_employee('B', {'kitchen_share': 15.5, 'loyalty_cards_count': 40,
                                      'shifts_count': 25}, shifts(25), '2026-08')
    ka, kb = a['kpis']['kpi2'], b['kpis']['kpi2']
    assert ka['per_shift'] and kb['per_shift']
    assert ka['fact'] == kb['fact'] == 1.6
    assert (ka['fact_raw'], ka['shifts_divisor']) == (8, 5)
    assert (kb['fact_raw'], kb['shifts_divisor']) == (40, 25)
    assert ka['target'] == kb['target'] == 2.0 and ka['min'] == kb['min'] == 0.67
    assert ka['capped_ratio'] == kb['capped_ratio'] == pytest.approx(0.6992, abs=1e-4)
    assert ka['unit'] == 'шт/смену' and ka['decimals'] == 2
    assert a['koef'] == 0.33 and b['koef'] == 1.67
    assert a['cash_shifts'] == 5 and b['cash_shifts'] == 25


def test_per_shift_divides_by_cash_shifts_not_days(tmp_path):
    """Делитель — кассовые смены периода (мы считаем смены по кассам), а не дни:
    22 кассы за 20 дней делят факт на 22. Коэффициент по-прежнему по дням на точках с целями."""
    calc = KpiCalculator(make_reader(tmp_path, AUG))
    res = calc.calculate_employee('A', {'loyalty_cards_count': 44, 'shifts_count': 22},
                                  shifts(20), '2026-08')
    k = res['kpis']['kpi2']
    assert k['shifts_divisor'] == 22 and k['fact'] == 2.0
    assert res['total_shifts'] == 20 and res['koef'] == 1.33


def test_divisor_falls_back_to_shift_days_without_cash_shifts(tmp_path):
    calc = KpiCalculator(make_reader(tmp_path, AUG))
    res = calc.calculate_employee('A', {'loyalty_cards_count': 10}, shifts(5), '2026-08')
    assert res['kpis']['kpi2']['shifts_divisor'] == 5
    assert res['kpis']['kpi2']['fact'] == 2.0


def test_explicit_divisor_argument(tmp_path):
    calc = KpiCalculator(make_reader(tmp_path, AUG))
    res = calc.calculate_employee('A', {'loyalty_cards_count': 10, 'shifts_count': 5},
                                  shifts(5), '2026-08', shifts_divisor=4)
    assert res['kpis']['kpi2']['shifts_divisor'] == 4
    assert res['kpis']['kpi2']['fact'] == 2.5


def test_share_metric_never_per_shift(tmp_path):
    """Долевая метрика с флагом per_shift в конфиге: флаг игнорируется."""
    cfg = {'kpi1': dict(KITCHEN, per_shift=True)}
    reader = make_reader(tmp_path, {'2026-08': month_data(cfg, {'kpi1': (18, 13)})})
    res = KpiCalculator(reader).calculate_employee(
        'A', {'kitchen_share': 15.5, 'shifts_count': 10}, shifts(10), '2026-08')
    k = res['kpis']['kpi1']
    assert k['per_shift'] is False and k['fact'] == 15.5 and k['unit'] == '%'
    assert 'fact_raw' not in k


# ==================== граница месяца и нормализация ====================

def test_legacy_monthly_targets_normalized_from_august():
    """Старый конфиг августа без флага: штучный KPI становится «на смену»,
    месячные цели делятся на норму — 30 карт за месяц при норме 15 = 2 за смену."""
    assert PER_SHIFT_FROM_MONTH == '2026-08'
    data, converted = normalize_month_data('2026-08', AUG['2026-08'], DEFAULTS)
    assert data['kpi_config']['kpi2']['per_shift'] is True
    assert 'per_shift' not in data['kpi_config']['kpi1']
    assert data['Кременчугская']['kpi2'] == {'target': 2.0, 'min': 0.67}
    assert data['Кременчугская']['kpi1'] == {'target': 18, 'min': 13}
    assert converted == {'kpi2': {'norm_shifts': 15.0}}
    # исходник не тронут
    assert AUG['2026-08']['Кременчугская']['kpi2'] == {'target': 30, 'min': 10}


def test_july_keeps_absolute_targets(tmp_path):
    """Июль и раньше считаются как прежде: одно месячное число, без деления."""
    data, converted = normalize_month_data('2026-07', JUL['2026-07'], DEFAULTS)
    assert converted == {} and 'per_shift' not in data['kpi_config']['kpi2']
    calc = KpiCalculator(make_reader(tmp_path, JUL))
    res = calc.calculate_employee('A', {'loyalty_cards_count': 8, 'shifts_count': 5},
                                  shifts(5, month='2026-07'), '2026-07')
    k = res['kpis']['kpi2']
    assert k['per_shift'] is False and k['fact'] == 8 and k['target'] == 30.0
    assert k['capped_ratio'] == 0.0


def test_explicit_flag_wins_over_month_border(tmp_path):
    """Явный флаг в конфиге сильнее границы: false в августе — месячное число,
    true в июле — на смену. Явные цели не конвертируются."""
    aug_off = month_data({'kpi1': KITCHEN, 'kpi2': dict(CARDS, per_shift=False)},
                         {'kpi1': (18, 13), 'kpi2': (30, 10)})
    jul_on = month_data({'kpi1': KITCHEN, 'kpi2': dict(CARDS, per_shift=True)},
                        {'kpi1': (18, 13), 'kpi2': (2, 0.67)})
    reader = make_reader(tmp_path, {'2026-08': aug_off, '2026-07': jul_on})
    assert reader.get_targets_for_month('2026-08')['Кременчугская']['kpi2'] == {'target': 30, 'min': 10}
    assert reader.get_editor_data()['converted_from_monthly'] == {}
    calc = KpiCalculator(reader)
    aug = calc.calculate_employee('A', {'loyalty_cards_count': 40, 'shifts_count': 25},
                                  shifts(25), '2026-08')['kpis']['kpi2']
    assert aug['per_shift'] is False and aug['fact'] == 40 and aug['capped_ratio'] == 1.5
    jul = calc.calculate_employee('A', {'loyalty_cards_count': 8, 'shifts_count': 5},
                                  shifts(5, month='2026-07'), '2026-07')['kpis']['kpi2']
    assert jul['per_shift'] is True and jul['fact'] == 1.6 and jul['target'] == 2.0


def test_editor_data_and_calculator_see_same_numbers(tmp_path):
    reader = make_reader(tmp_path, AUG)
    editor = reader.get_editor_data()
    assert editor['per_shift_from_month'] == '2026-08'
    assert editor['months']['2026-08']['Лиговский']['kpi2'] == {'target': 2.0, 'min': 0.67}
    assert editor['converted_from_monthly'] == {'2026-08': {'kpi2': {'norm_shifts': 15.0}}}
    assert reader.get_targets_for_month('2026-08')['Лиговский']['kpi2'] == {'target': 2.0, 'min': 0.67}


# ==================== формула множителя ====================

def _premium(fact, target, min_val):
    calc = KpiCalculator(KpiTargetsReader('/nonexistent/kpi_targets.json'))
    return calc.calculate_premium(fact, target, min_val, DEFAULTS, base_premium=5000)


def test_direct_metric_ratio_unchanged():
    assert _premium(12, 18, 13)['capped_ratio'] == 0.0
    assert _premium(15.5, 18, 13)['capped_ratio'] == 0.5
    assert _premium(18, 18, 13)['capped_ratio'] == 1.0
    assert _premium(30, 18, 13) == {'ratio': 3.4, 'capped_ratio': 2.0, 'intermediate_premium': 10000.0}


def test_inverse_metric_pays_when_fact_is_low():
    """Опоздания: цель 0, минимум 3 (меньше — лучше). Раньше любой факт ниже
    минимума давал 0 из-за защиты «факт < минимум», и такой KPI не платил никогда."""
    assert _premium(0, 0, 3)['capped_ratio'] == 1.0
    assert _premium(1, 0, 3)['capped_ratio'] == pytest.approx(0.6667, abs=1e-4)
    assert _premium(3, 0, 3)['capped_ratio'] == 0.0
    assert _premium(5, 0, 3) == {'ratio': 0.0, 'capped_ratio': 0.0, 'intermediate_premium': 0.0}
    # перевыполнение инверсной цели — множитель выше 1, потолок max_ratio
    assert _premium(0, 1, 3)['capped_ratio'] == 1.5
    assert _premium(0, 0.5, 3)['capped_ratio'] == 1.2
    assert _premium(0, 2, 3) == {'ratio': 3.0, 'capped_ratio': 2.0, 'intermediate_premium': 10000.0}


def test_inverse_metric_per_shift_end_to_end(tmp_path):
    """Опоздания на смену: цель 0, минимум 0,2 за смену. 1 опоздание на 10 смен = 0,1."""
    cfg = {'kpi1': {'metric': 'late_count', 'name': 'Опоздания (шт)'}}
    reader = make_reader(tmp_path, {'2026-08': month_data(cfg, {'kpi1': (0, 3)})})
    res = KpiCalculator(reader).calculate_employee(
        'A', {'late_count': 1, 'shifts_count': 10}, shifts(10), '2026-08')
    k = res['kpis']['kpi1']
    assert k['per_shift'] and k['target'] == 0.0 and k['min'] == 0.2
    assert k['fact'] == 0.1 and k['capped_ratio'] == 0.5


# ==================== пустые цели 0/0 ====================

def test_zero_pair_is_not_a_target():
    assert targets_are_set({'target': 18, 'min': 13})
    assert targets_are_set({'target': 0, 'min': 3})      # инверсная: цель 0 — задана
    assert not targets_are_set({'target': 0, 'min': 0})
    assert not targets_are_set(None)
    assert not targets_are_set({})


def test_zero_targets_location_excluded_from_weighting_and_koef(tmp_path):
    """Точка с 0/0 не размывает цель и не входит в коэффициент. Раньше 0/0
    считалось целью: цель 18 падала до 12, а на «пустой» точке множитель был x2."""
    targets = {loc: {'kpi1': (18, 13)} for loc in LOCS}
    targets['Большой пр В.О.'] = {'kpi1': (0, 0)}
    reader = make_reader(tmp_path, {'2026-08': month_data({'kpi1': KITCHEN}, targets)})
    locs = dict(shifts(10), **shifts(5, loc='Большой пр. В.О', month='2026-09'))
    res = KpiCalculator(reader).calculate_employee(
        'A', {'kitchen_share': 18.0, 'shifts_count': 15}, locs, '2026-08')
    k = res['kpis']['kpi1']
    assert (k['target'], k['min']) == (18.0, 13.0)
    assert k['capped_ratio'] == 1.0
    assert k['target_shifts'] == 10 and res['total_shifts'] == 10 and res['koef'] == 0.67
    assert set(k['location_targets']) == {'Кременчугская'}


def test_employee_only_on_unset_location_has_no_kpi(tmp_path):
    targets = {loc: {'kpi1': (18, 13)} for loc in LOCS}
    targets['Варшавская'] = {'kpi1': (0, 0)}
    reader = make_reader(tmp_path, {'2026-08': month_data({'kpi1': KITCHEN}, targets)})
    res = KpiCalculator(reader).calculate_employee(
        'A', {'kitchen_share': 40.0, 'shifts_count': 8}, shifts(8, loc='Варшавская'), '2026-08')
    assert res is None


def test_kpi_without_targets_on_employee_points_pays_zero(tmp_path):
    """kpi2 задан только на Варшавской, сотрудник работал на Кременчугской:
    по kpi2 премии нет (раньше цель 0 давала x2), kpi1 и коэффициент как обычно."""
    targets = {loc: {'kpi1': (18, 13), 'kpi2': (0, 0)} for loc in LOCS}
    targets['Варшавская'] = {'kpi1': (18, 13), 'kpi2': (2, 0.67)}
    cfg = {'kpi1': KITCHEN, 'kpi2': dict(CARDS, per_shift=True)}
    reader = make_reader(tmp_path, {'2026-08': month_data(cfg, targets)})
    res = KpiCalculator(reader).calculate_employee(
        'A', {'kitchen_share': 18.0, 'loyalty_cards_count': 50, 'shifts_count': 15},
        shifts(15), '2026-08')
    k1, k2 = res['kpis']['kpi1'], res['kpis']['kpi2']
    assert k2['no_targets'] is True and k2['capped_ratio'] == 0.0 and k2['intermediate_premium'] == 0.0
    assert k1['no_targets'] is False and k1['capped_ratio'] == 1.0
    assert res['koef'] == 1.0 and res['total_premium'] == 7500.0


# ==================== сохранение ====================

def test_save_strips_meta_keys_and_persists_explicit_flags(tmp_path):
    reader = make_reader(tmp_path, AUG)
    editor = reader.get_editor_data()
    editor['available_metrics'] = {'x': 1}
    reader.save_targets(editor)
    saved = json.loads((tmp_path / 'kpi_targets.json').read_text(encoding='utf-8'))
    assert set(saved) == {'defaults', 'months'}
    assert not any(k in saved for k in NON_PERSISTENT_KEYS)
    assert saved['months']['2026-08']['kpi_config']['kpi2']['per_shift'] is True
    assert saved['months']['2026-08']['Варшавская']['kpi2'] == {'target': 2.0, 'min': 0.67}
    assert not (tmp_path / 'kpi_targets.json.tmp').exists()
    # после сохранения месяц уже явный — конвертировать нечего
    reader.clear_cache()
    assert reader.get_editor_data()['converted_from_monthly'] == {}
    assert reader.get_targets_for_month('2026-08')['Варшавская']['kpi2'] == {'target': 2.0, 'min': 0.67}


def test_save_rejects_bad_payload(tmp_path):
    reader = make_reader(tmp_path, AUG)
    with pytest.raises(ValueError):
        reader.save_targets({'defaults': DEFAULTS})
    with pytest.raises(ValueError):
        reader.save_targets({'months': []})


# ==================== каталог и подписи ====================

def test_catalog_marks_extensive_metrics():
    assert all(is_extensive(m) for m in ('loyalty_cards_count', 'total_checks', 'total_revenue',
                                          'draft_revenue', 'bottles_revenue', 'kitchen_revenue',
                                          'work_hours', 'late_count', 'cancelled_count'))
    assert not any(is_extensive(m) for m in ('kitchen_share', 'draft_share', 'avg_check',
                                              'revenue_per_shift', 'revenue_per_hour',
                                              'plan_fact_percent', 'shifts_count'))


def test_units_and_decimals():
    assert metric_unit('loyalty_cards_count') == 'шт'
    assert metric_unit('loyalty_cards_count', per_shift=True) == 'шт/смену'
    assert metric_decimals('loyalty_cards_count') == 0
    assert metric_decimals('loyalty_cards_count', per_shift=True) == 2
    assert metric_decimals('total_revenue', per_shift=True) == 0
    assert metric_decimals('kitchen_share') == 1
