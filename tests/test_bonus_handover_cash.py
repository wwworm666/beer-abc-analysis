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


# ==================== _handover_premium: правило целиком ====================
# «Премия за передачу смены не выплачивается либо если не заполнена касса,
# либо если проставлен штраф вручную» (формулировка владельца 2026-08-06).

def _d(date, manual=False, cash=True, rule=True):
    return {'date': date, 'manual_cash_penalty': manual,
            'cash_filled': cash, 'cash_rule_applies': rule}


def test_premium_pays_every_day_with_cash():
    from routes.employee import _handover_premium
    days = [_d('2026-07-11'), _d('2026-07-12')]
    locs = {'2026-07-11': 'Варшавская', '2026-07-12': 'Варшавская'}
    keys = {('varshavskaya', '2026-07-11'), ('varshavskaya', '2026-07-12')}
    bonus, paid, without, manual = _handover_premium(days, locs, keys)
    assert (bonus, paid, without, manual) == (1000, 2, 0, 0)


def test_premium_skips_day_without_cash_and_day_with_penalty():
    """Две причины не платить, и они не задваиваются."""
    from routes.employee import _handover_premium
    days = [_d('2026-07-11'),                                  # оплачен
            _d('2026-07-12', cash=False),                      # нет кассы
            _d('2026-07-13', manual=True)]                     # ручной штраф
    locs = {'2026-07-11': 'Варшавская', '2026-07-12': 'Варшавская',
            '2026-07-13': 'Варшавская'}
    keys = {('varshavskaya', '2026-07-11'), ('varshavskaya', '2026-07-13')}
    bonus, paid, without, manual = _handover_premium(days, locs, keys)
    assert (bonus, paid, without, manual) == (500, 1, 1, 1)

    # день без кассы И со штрафом вычитается ОДИН раз
    days2 = [_d('2026-07-11'), _d('2026-07-12', manual=True, cash=False)]
    locs2 = {'2026-07-11': 'Варшавская', '2026-07-12': 'Варшавская'}
    keys2 = {('varshavskaya', '2026-07-11')}
    assert _handover_premium(days2, locs2, keys2)[:2] == (500, 1)


def test_two_cash_shifts_in_one_day_paid_once():
    """Две кассовые смены в одном дне -> премия одна, за первую открытую.

    Так быть не должно, но в июне 2026 у Верещагина было 10 кассовых смен на 9
    дней. Раньше база премии была «кассовые смены», такой день давал 1000 ₽, а
    ручной штраф снимал с него только 500. Решение владельца 2026-08-06 —
    платить один раз за день, поэтому база = ДНИ (len(days_detail)).
    """
    from routes.employee import _handover_premium
    # два кассовых чека 12.07 -> в days_detail всё равно ОДИН день
    days = [_d('2026-07-11'), _d('2026-07-12')]
    locs = {'2026-07-11': 'Варшавская', '2026-07-12': 'Варшавская'}
    keys = {('varshavskaya', '2026-07-11'), ('varshavskaya', '2026-07-12')}
    bonus, paid, _, _ = _handover_premium(days, locs, keys)
    assert (bonus, paid) == (1000, 2), 'платим за дни, а не за кассовые смены'
    # и штраф на такой день снимает премию этого дня целиком
    days[1]['manual_cash_penalty'] = True
    assert _handover_premium(days, locs, keys)[:2] == (500, 1)
