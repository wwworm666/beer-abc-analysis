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
    is_dish_based, is_extensive, metric_decimals, metric_unit,
    normalize_dish_name, normalize_month_data, resolve_fact, targets_are_set,
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
    assert ka['target'] == kb['target'] == 2.0
    assert ka['min'] == kb['min'] == pytest.approx(0.6667, abs=1e-4)
    # 0,70 ровно: точность хранения 4 знака даёт минимум 10x5/15 = 3,33, а не 3,35
    assert ka['capped_ratio'] == kb['capped_ratio'] == pytest.approx(0.7, abs=1e-4)
    assert ka['unit'] == 'шт/смену' and ka['decimals'] == 2
    # Человеку показывают цель за ЕГО смены, в штуках: «8 из 10» и «40 из 50»
    assert (ka['target_period'], ka['min_period']) == (10.0, 3.33)
    assert (kb['target_period'], kb['min_period']) == (50.0, 16.67)
    assert ka['period_decimals'] == 0
    assert ka['location_targets']['Кременчугская']['target_period'] == 10.0
    assert kb['location_targets']['Кременчугская']['target_period'] == 50.0
    assert a['koef'] == 0.33 and b['koef'] == 1.67
    assert a['cash_shifts'] == 5 and b['cash_shifts'] == 25


def test_period_targets_scale_with_shifts(tmp_path):
    """Цель за период = цель за смену x кассовые смены сотрудника. Это то,
    что видит человек: «сделал 8 из 10», дробные «за смену» на экран не идут."""
    calc = KpiCalculator(make_reader(tmp_path, AUG))
    for cash, want_target, want_min in ((15, 30.0, 10.0), (10, 20.0, 6.67), (30, 60.0, 20.0)):
        res = calc.calculate_employee('A', {'loyalty_cards_count': 1, 'shifts_count': cash},
                                      shifts(15), '2026-08')
        k = res['kpis']['kpi2']
        assert (k['target_period'], k['min_period']) == (want_target, want_min), cash


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
    assert data['Кременчугская']['kpi2']['target'] == 2.0
    assert data['Кременчугская']['kpi2']['min'] == pytest.approx(0.6667, abs=1e-4)
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
    assert editor['months']['2026-08']['Лиговский']['kpi2']['target'] == 2.0
    assert editor['converted_from_monthly'] == {'2026-08': {'kpi2': {'norm_shifts': 15.0}}}
    assert reader.get_targets_for_month('2026-08')['Лиговский']['kpi2']['target'] == 2.0
    # Обратный пересчёт в редакторе (значение x норма) возвращает введённые 30 / 10,
    # а не 30,0 / 10,05 — ради этого хранение «за смену» держит 4 знака
    per = editor['months']['2026-08']['Лиговский']['kpi2']
    assert round(per['target'] * 15, 2) == 30 and round(per['min'] * 15, 2) == 10


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
    # На экране: «1 опоздание при пороге 2 за 10 смен», а не «0,1 против 0,2»
    assert (k['fact_raw'], k['target_period'], k['min_period']) == (1, 0.0, 2.0)


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
    assert saved['months']['2026-08']['Варшавская']['kpi2']['target'] == 2.0
    assert not (tmp_path / 'kpi_targets.json.tmp').exists()
    # после сохранения месяц уже явный — конвертировать нечего
    reader.clear_cache()
    assert reader.get_editor_data()['converted_from_monthly'] == {}
    assert reader.get_targets_for_month('2026-08')['Варшавская']['kpi2']['target'] == 2.0


def test_save_rejects_bad_payload(tmp_path):
    reader = make_reader(tmp_path, AUG)
    with pytest.raises(ValueError):
        reader.save_targets({'defaults': DEFAULTS})
    with pytest.raises(ValueError):
        reader.save_targets({'months': []})


# ==================== KPI на выбранные блюда ====================

DISHES = {'metric': 'dish_count', 'name': 'Брискет + Щёчки (шт)',
          'per_shift': True, 'dishes': ['Брискет', 'Щёчки говяжьи']}


def dish_month(config=None, targets=(2, 0.6667)):
    return month_data(config or {'kpi1': DISHES}, {'kpi1': targets})


def test_dish_kpi_sums_selected_dishes(tmp_path):
    """Факт KPI на блюда — сумма продаж выбранных позиций; в ответе разбивка."""
    reader = make_reader(tmp_path, {'2026-09': dish_month()})
    metrics = {'shifts_count': 10,
               'dishes': {'count': {'брискет': 7, 'щёчки говяжьи': 5, 'борщ': 40}}}
    res = KpiCalculator(reader).calculate_employee('A', metrics, shifts(10, month='2026-09'), '2026-09')
    k = res['kpis']['kpi1']
    assert k['fact_raw'] == 12 and k['dish_facts'] == {'Брискет': 7, 'Щёчки говяжьи': 5}
    assert k['dishes'] == ['Брискет', 'Щёчки говяжьи'] and k['no_dishes'] is False
    # блюда штучные -> KPI зависит от смен: цель 2/смену x 10 смен = 20
    assert k['per_shift'] and (k['target_period'], k['fact']) == (20.0, 1.2)
    assert k['capped_ratio'] == pytest.approx(0.4, abs=1e-4)


def test_dish_kpi_without_dishes_pays_zero(tmp_path):
    """Метрика выбрана, блюда — нет: настройка не закончена, премии нет."""
    reader = make_reader(tmp_path, {'2026-09': dish_month({'kpi1': dict(DISHES, dishes=[])})})
    metrics = {'shifts_count': 10, 'dishes': {'count': {'брискет': 7}}}
    res = KpiCalculator(reader).calculate_employee('A', metrics, shifts(10, month='2026-09'), '2026-09')
    k = res['kpis']['kpi1']
    assert k['no_dishes'] is True and k['dishes'] == []
    assert k['capped_ratio'] == 0.0 and k['intermediate_premium'] == 0.0
    assert res['total_premium'] == 0.0


def test_dish_name_matching_ignores_case_and_spaces():
    assert normalize_dish_name('  Щёчки   ГОВЯЖЬИ ') == 'щёчки говяжьи'
    assert normalize_dish_name(None) == ''
    metrics = {'dishes': {'count': {'брискет': 7}, 'revenue': {'брискет': 4900}}}
    assert resolve_fact(metrics, 'dish_count', {'dishes': ['  БРИСКЕТ  ']}) == (7, {'  БРИСКЕТ  ': 7})
    assert resolve_fact(metrics, 'dish_revenue', {'dishes': ['Брискет']})[0] == 4900


def test_dish_revenue_metric_uses_money(tmp_path):
    conf = {'kpi1': {'metric': 'dish_revenue', 'name': 'Выручка по брискету (₽)',
                     'per_shift': False, 'dishes': ['Брискет']}}
    reader = make_reader(tmp_path, {'2026-09': dish_month(conf, targets=(10000, 4000))})
    metrics = {'shifts_count': 10, 'dishes': {'count': {'брискет': 7}, 'revenue': {'брискет': 7000}}}
    res = KpiCalculator(reader).calculate_employee('A', metrics, shifts(10, month='2026-09'), '2026-09')
    k = res['kpis']['kpi1']
    assert k['fact'] == 7000 and k['per_shift'] is False
    assert k['capped_ratio'] == 0.5 and 'target_period' not in k


def test_two_dish_kpis_have_independent_dish_sets(tmp_path):
    """Одна метрика на два показателя с разными блюдами — факты не смешиваются."""
    conf = {'kpi1': dict(DISHES, dishes=['Брискет']),
            'kpi2': dict(DISHES, name='Щёчки (шт)', dishes=['Щёчки говяжьи'])}
    m = month_data(conf, {'kpi1': (2, 0.6667), 'kpi2': (1, 0.3333)})
    reader = make_reader(tmp_path, {'2026-09': m})
    metrics = {'shifts_count': 15, 'dishes': {'count': {'брискет': 30, 'щёчки говяжьи': 9}}}
    res = KpiCalculator(reader).calculate_employee('A', metrics, shifts(15, month='2026-09'), '2026-09')
    assert res['kpis']['kpi1']['fact_raw'] == 30 and res['kpis']['kpi2']['fact_raw'] == 9
    # 30 брискетов за 15 смен = ровно цель (2/смену); щёчек 9 из 15 -> 0,6 при цели 1
    assert res['kpis']['kpi1']['capped_ratio'] == 1.0
    assert res['kpis']['kpi2']['capped_ratio'] == pytest.approx(0.4, abs=1e-4)


def test_non_dish_metric_ignores_dishes_key(tmp_path):
    """Список блюд у обычной метрики ничего не меняет (и не попадает в ответ)."""
    conf = {'kpi1': {'metric': 'kitchen_share', 'name': 'Доля кухни (%)', 'dishes': ['Брискет']}}
    reader = make_reader(tmp_path, {'2026-09': month_data(conf, {'kpi1': (18, 13)})})
    metrics = {'kitchen_share': 18.0, 'shifts_count': 10, 'dishes': {'count': {'брискет': 7}}}
    res = KpiCalculator(reader).calculate_employee('A', metrics, shifts(10, month='2026-09'), '2026-09')
    k = res['kpis']['kpi1']
    assert k['fact'] == 18.0 and k['capped_ratio'] == 1.0
    assert 'dishes' not in k and 'dish_facts' not in k


def test_route_collects_and_normalizes_dishes():
    """routes/employee.py: что запросить у OLAP и как разложить ответ."""
    from routes.employee import _configured_dishes, _dish_metric_map
    config = {'kpi1': {'metric': 'dish_count', 'dishes': ['Брискет', 'Щёчки говяжьи']},
              'kpi2': {'metric': 'kitchen_share'},
              'kpi3': {'metric': 'dish_revenue', 'dishes': [' брискет ', 'Стейк']}}
    # дубль между показателями схлопнут, порядок первого появления сохранён
    assert _configured_dishes(config) == ['Брискет', 'Щёчки говяжьи', 'Стейк']
    assert _configured_dishes({}) == []
    sales = {'Брискет': {'count': 7, 'revenue': 4900},
             'Щёчки  ГОВЯЖЬИ': {'count': 5, 'revenue': 2500}}
    assert _dish_metric_map(sales) == {
        'count': {'брискет': 7.0, 'щёчки говяжьи': 5.0},
        'revenue': {'брискет': 4900.0, 'щёчки говяжьи': 2500.0},
    }
    assert _dish_metric_map(None) == {'count': {}, 'revenue': {}}


# ==================== каталог и подписи ====================

def test_dish_metrics_are_in_catalog():
    assert is_dish_based('dish_count') and is_dish_based('dish_revenue')
    assert not is_dish_based('kitchen_share')
    # штучные -> зависят от смен, как карты и чеки
    assert is_extensive('dish_count') and is_extensive('dish_revenue')
    assert metric_unit('dish_count') == 'шт' and metric_unit('dish_revenue') == '₽'


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


# ==================== доля чеков с едой (2026-10-06) ====================
# Владелец: «доля кухни — плохой KPI, лучше доля чеков с едой». Факт = чеки
# сотрудника, где есть хотя бы одна позиция группы «ЕДА», / все его чеки × 100.
# Числа примеров — настоящие за сентябрь 2026 (Дамир Кизатов: 139 из 375).

FOOD = {'metric': 'food_checks_share', 'name': 'Доля чеков с едой (%)'}


def kpi_olap_for(name, total_checks, categories):
    """kpi_olap как его отдаёт OlapReports.get_kpi_olap_data: categories —
    [(группа, выручка, чеки)]."""
    return {
        'summary': {name: {'total_checks': total_checks, 'total_revenue': 100000.0,
                           'discount_sum': 0.0}},
        'categories': {name: [{'category': cat, 'revenue': rev, 'cost': 0.0,
                               'markup': 0.0, 'checks': checks}
                              for cat, rev, checks in categories]},
    }


def test_food_checks_share_in_catalog():
    from core.kpi_calculator import AVAILABLE_METRICS
    info = AVAILABLE_METRICS['food_checks_share']
    assert info['name'] == 'Доля чеков с едой' and info['unit'] == '%' and info['decimals'] == 1
    # долевая метрика: не на смену и не по блюдам
    assert not is_extensive('food_checks_share') and not is_dish_based('food_checks_share')
    assert metric_unit('food_checks_share') == '%' and metric_decimals('food_checks_share') == 1


def test_build_kpi_metrics_food_checks_share_takes_only_food_row():
    """Чеки строки «ЕДА» / чеки сотрудника. Чеки других групп не складываются:
    чек с пивом и едой есть и в строке розлива, и в строке еды."""
    from routes.employee import _build_kpi_metrics
    olap = kpi_olap_for('Дамир Кизатов', 375, [
        ('ЕДА', 30000.0, 139), ('Напитки Розлив', 50000.0, 281),
        ('Напитки Фасовка', 15000.0, 124), ('Газ и Пэт', 3000.0, 63), ('', 100.0, 1),
    ])
    m = _build_kpi_metrics('Дамир Кизатов', olap, shifts_count=12, total_hours=120)
    assert m['food_checks'] == 139 and m['total_checks'] == 375
    assert m['food_checks_share'] == 37.07  # 139 / 375 × 100, округление до сотых


def test_build_kpi_metrics_food_checks_share_edge_cases():
    from routes.employee import _build_kpi_metrics
    # без чеков — 0, а не деление на ноль
    m = _build_kpi_metrics('А Б', kpi_olap_for('А Б', 0, [('ЕДА', 0.0, 0)]), 1, 1)
    assert m['food_checks_share'] == 0
    # ни одной позиции «ЕДА» — 0
    m = _build_kpi_metrics('А Б', kpi_olap_for('А Б', 50, [('Напитки Розлив', 1000.0, 50)]), 1, 1)
    assert m['food_checks'] == 0 and m['food_checks_share'] == 0
    # имя в другом порядке слов находится так же, как для остальных метрик
    m = _build_kpi_metrics('Кизатов Дамир', kpi_olap_for('Дамир Кизатов', 100, [('ЕДА', 1.0, 40)]), 1, 1)
    assert m['food_checks_share'] == 40.0
    # строка categories без поля checks (старая форма ответа) — 0, без исключения
    olap = kpi_olap_for('А Б', 10, [('ЕДА', 1.0, 3)])
    del olap['categories']['А Б'][0]['checks']
    assert _build_kpi_metrics('А Б', olap, 1, 1)['food_checks_share'] == 0
    # сотрудника нет в OLAP — 0
    assert _build_kpi_metrics('Нет Такого', olap, 1, 1)['food_checks_share'] == 0


OCT_FOOD_TARGETS = {  # предложение на октябрь 2026: (цель, минимум) по точкам
    'Большой пр В.О.': {'kpi1': (28, 21)}, 'Варшавская': {'kpi1': (36, 29)},
    'Кременчугская': {'kpi1': (36, 29)}, 'Лиговский': {'kpi1': (38, 31)},
}


def test_food_checks_share_kpi_weighted_by_shifts(tmp_path):
    """Цели взвешены по сменам, факт — доля как есть (не на смену)."""
    reader = make_reader(tmp_path, {'2026-10': month_data({'kpi1': FOOD}, OCT_FOOD_TARGETS)})
    shift_locs = dict(shifts(15, 'Варшавская', '2026-10'))
    shift_locs.update({'2026-10-20': 'Лиговский', '2026-10-21': 'Лиговский'})
    res = KpiCalculator(reader).calculate_employee(
        'Дарья Коновцова', {'food_checks_share': 34.9, 'shifts_count': 17}, shift_locs, '2026-10')
    k = res['kpis']['kpi1']
    assert k['metric'] == 'food_checks_share' and k['unit'] == '%' and k['per_shift'] is False
    assert k['target'] == pytest.approx((36 * 15 + 38 * 2) / 17, abs=1e-4)
    assert k['min'] == pytest.approx((29 * 15 + 31 * 2) / 17, abs=1e-4)
    assert k['fact'] == 34.9
    assert k['capped_ratio'] == pytest.approx((34.9 - k['min']) / (k['target'] - k['min']), abs=1e-3)
    # единственный KPI месяца получает весь фонд
    assert res['base_per_kpi'] == 15000 and res['koef'] == round(17 / 15, 2)


def test_food_checks_share_kpi_floor_and_cap(tmp_path):
    reader = make_reader(tmp_path, {'2026-10': month_data({'kpi1': FOOD}, OCT_FOOD_TARGETS)})
    calc = KpiCalculator(reader)
    big = shifts(15, 'Большой пр. В.О', '2026-10')
    below = calc.calculate_employee('A', {'food_checks_share': 20.5}, big, '2026-10')
    assert below['kpis']['kpi1']['capped_ratio'] == 0  # ниже минимума 21 — ×0
    on_target = calc.calculate_employee('A', {'food_checks_share': 28.0}, big, '2026-10')
    assert on_target['kpis']['kpi1']['capped_ratio'] == 1.0
    above = calc.calculate_employee('A', {'food_checks_share': 40.0}, big, '2026-10')
    assert above['kpis']['kpi1']['capped_ratio'] == 2.0  # потолок max_ratio


def test_kpi_olap_categories_request_counts_checks_per_group():
    """Запрос categories несёт чеки группы (UniqOrderId.OrdersCount), ответ их разбирает."""
    from unittest.mock import patch
    from core.olap_reports import OlapReports
    olap = OlapReports()
    olap.token = 't'
    bodies = []

    class Resp:
        status_code = 200

        def __init__(self, body):
            self.body = body

        def json(self):
            if 'DishGroup.TopParent' in self.body['groupByRowFields']:
                return {'data': [{'AuthUser': 'Дамир Кизатов', 'DishGroup.TopParent': 'ЕДА',
                                  'DishDiscountSumInt': 30000, 'ProductCostBase.ProductCost': 9000,
                                  'ProductCostBase.MarkUp': 2.3, 'UniqOrderId.OrdersCount': 139}]}
            return {'data': [{'AuthUser': 'Дамир Кизатов', 'UniqOrderId.OrdersCount': 375,
                              'DishDiscountSumInt': 100000, 'DiscountSum': 0}]}

    def fake_post(url, params=None, json=None, headers=None, timeout=None):
        bodies.append(json)
        return Resp(json)

    with patch('core.olap_reports.requests.post', fake_post):
        data = olap.get_kpi_olap_data('2026-09-01', '2026-10-01')

    cat_body = next(b for b in bodies if 'DishGroup.TopParent' in b['groupByRowFields'])
    assert 'UniqOrderId.OrdersCount' in cat_body['aggregateFields']
    assert cat_body['filters']['DeletedWithWriteoff']['values'] == ['NOT_DELETED']
    assert data['categories']['Дамир Кизатов'][0]['checks'] == 139
    assert data['summary']['Дамир Кизатов']['total_checks'] == 375
