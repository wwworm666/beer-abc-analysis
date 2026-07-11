"""
Премия «передача смены» платится только за дни со сданной кассовой дисциплиной.

Логика в routes/employee.py: за день (начиная с HANDOVER_CASH_RULE_FROM = 11.07.2026)
без заполненной кассы (наличные в сейфе) премия 500 ₽ не начисляется; дни ДО этой
даты оплачиваются всегда (исторические месяцы без кассы не режем). Сопоставление
точки iiko (кассовые смены) и точки графика — через venue_key (BAR_NAME_MAPPING),
т.к. имена различаются («Пивная культура» == «Кременчугская»).
"""

from routes.employee import (
    _paid_handover_shifts, _canon_venue, HANDOVER_CASH_RULE_FROM,
)


def test_canon_venue_matches_iiko_and_graph():
    # график «Кременчугская» и кассовая группа iiko «Пивная культура» -> один venue_key
    assert _canon_venue('Кременчугская') == _canon_venue('Пивная культура') == 'kremenchugskaya'
    assert _canon_venue('Варшавская') == 'varshavskaya'
    assert _canon_venue('Большой пр. В.О') == 'bolshoy'


def test_all_days_with_cash_paid_fully():
    locs = {'2026-07-11': 'Варшавская', '2026-07-12': 'Варшавская'}
    keys = {('varshavskaya', '2026-07-11'), ('varshavskaya', '2026-07-12')}
    assert _paid_handover_shifts(2, locs, keys) == (2, 0)


def test_day_without_cash_not_paid():
    locs = {'2026-07-11': 'Варшавская', '2026-07-12': 'Лиговский'}
    keys = {('varshavskaya', '2026-07-11')}          # Лиговский 12.07 кассу не сдал
    assert _paid_handover_shifts(2, locs, keys) == (1, 1)


def test_iiko_name_matches_graph_venue():
    # день на кассовой группе «Пивная культура» = точка графика «Кременчугская»
    locs = {'2026-07-13': 'Пивная культура'}
    keys = {('kremenchugskaya', '2026-07-13')}
    assert _paid_handover_shifts(1, locs, keys) == (1, 0)


def test_days_before_rule_date_always_paid():
    # 05.07 (до отсечки) без кассы — всё равно платим; 11.07 без кассы — не платим
    assert HANDOVER_CASH_RULE_FROM == '2026-07-11'
    locs = {'2026-07-05': 'Варшавская', '2026-07-11': 'Лиговский'}
    assert _paid_handover_shifts(2, locs, set()) == (1, 1)


def test_all_before_rule_date_full_pay():
    # весь период до отсечки (старый месяц) — премия не режется, даже без кассы
    locs = {'2026-06-20': 'Варшавская', '2026-06-21': 'Лиговский'}
    assert _paid_handover_shifts(2, locs, set()) == (2, 0)


def test_none_keys_fail_open():
    # данные графика недоступны -> премию не режем, платим все смены
    locs = {'2026-07-20': 'Варшавская'}
    assert _paid_handover_shifts(3, locs, None) == (3, 0)


def test_never_negative_on_count_mismatch():
    # смен по метрике меньше, чем дней без кассы — не уходим ниже нуля
    locs = {'2026-07-11': 'Варшавская', '2026-07-12': 'Лиговский'}
    assert _paid_handover_shifts(1, locs, set())[0] == 0
