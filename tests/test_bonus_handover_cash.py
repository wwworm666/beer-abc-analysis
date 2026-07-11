"""
Премия «передача смены» платится только за дни со сданной кассовой дисциплиной.

Логика в routes/employee.py: за день без заполненной кассы (наличные в сейфе)
премия 500 ₽ не начисляется. Сопоставление точки iiko (кассовые смены) и точки
графика — через venue_key (BAR_NAME_MAPPING), т.к. имена различаются
(«Пивная культура» == «Кременчугская»).
"""

from routes.employee import _paid_handover_shifts, _canon_venue


def test_canon_venue_matches_iiko_and_graph():
    # график «Кременчугская» и кассовая группа iiko «Пивная культура» -> один venue_key
    assert _canon_venue('Кременчугская') == _canon_venue('Пивная культура') == 'kremenchugskaya'
    assert _canon_venue('Варшавская') == 'varshavskaya'
    assert _canon_venue('Большой пр. В.О') == 'bolshoy'


def test_all_days_with_cash_paid_fully():
    locs = {'2026-07-01': 'Варшавская', '2026-07-02': 'Варшавская'}
    keys = {('varshavskaya', '2026-07-01'), ('varshavskaya', '2026-07-02')}
    assert _paid_handover_shifts(2, locs, keys) == (2, 0)


def test_day_without_cash_not_paid():
    locs = {'2026-07-01': 'Варшавская', '2026-07-02': 'Лиговский'}
    keys = {('varshavskaya', '2026-07-01')}          # Лиговский 02.07 кассу не сдал
    assert _paid_handover_shifts(2, locs, keys) == (1, 1)


def test_iiko_name_matches_graph_venue():
    # день на кассовой группе «Пивная культура» = точка графика «Кременчугская»
    locs = {'2026-07-03': 'Пивная культура'}
    keys = {('kremenchugskaya', '2026-07-03')}
    assert _paid_handover_shifts(1, locs, keys) == (1, 0)


def test_none_keys_fail_open():
    # данные графика недоступны -> премию не режем, платим все смены
    locs = {'2026-07-01': 'Варшавская'}
    assert _paid_handover_shifts(3, locs, None) == (3, 0)


def test_never_negative_on_count_mismatch():
    # смен по метрике меньше, чем дней без кассы — не уходим ниже нуля
    locs = {'2026-07-01': 'Варшавская', '2026-07-02': 'Лиговский'}
    assert _paid_handover_shifts(1, locs, set())[0] == 0
