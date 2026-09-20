# -*- coding: utf-8 -*-
"""Решения по ассортименту (core/abc_buckets.py): правила, их порядок и защита от
малых выборок. Одни и те же правила для фасовки (штуки) и кегов (порции).

    python3 tests/test_abc_buckets.py
    python3 -m pytest -q tests/test_abc_buckets.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.abc_buckets import BUCKETS, bucket_cards, bucket_rule_text, decide_bucket  # noqa: E402
from core.abc_thresholds import (  # noqa: E402
    KEG_MARKUP_A_MIN,
    KEG_MARKUP_B_MIN,
    MARKUP_A_MIN,
    MARKUP_AUDIT_FLOOR_FACTOR,
    MARKUP_B_MIN,
    MIN_DAYS_FOR_NEGATIVE_VERDICT,
    MIN_SALES_FOR_VERDICT,
)

passed = 0
failed = 0


def _run(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f'  ok  {name}')
    except Exception as exc:  # noqa: BLE001
        failed += 1
        print(f'FAIL  {name}')
        print(f'      {type(exc).__name__}: {exc}')


def d(abc='A', markup=1.2, sales=10, weeks=4, weekly=None, outside=0.0,
      a_min=MARKUP_A_MIN, b_min=MARKUP_B_MIN):
    if weekly is None:
        weekly = [sales / weeks] * weeks if weeks else []
    return decide_bucket(abc, markup, sales, weeks, weekly, outside, a_min, b_min)


def test_six_buckets_with_unique_order():
    assert len(BUCKETS) == 6
    assert sorted(b['order'] for b in BUCKETS.values()) == [1, 2, 3, 4, 5, 6]
    for info in BUCKETS.values():
        assert info['name'] and info['action'] and info['hint']


def test_names_are_plain_business_russian():
    text = ' '.join(b['name'] + ' ' + b['action'] for b in BUCKETS.values())
    for metaphor in ('Звёзд', 'лошадк', 'Фон', 'Премиум', 'Удалить'):
        assert metaphor not in text, metaphor


def test_no_cost_or_below_floor_goes_to_check():
    assert d(markup=None) == 'check'
    assert d(markup=-1.0) == 'check'                        # продано в ноль
    floor = MARKUP_B_MIN * MARKUP_AUDIT_FLOOR_FACTOR          # 0.5 у фасовки
    assert d(markup=floor - 0.01) == 'check'
    assert d(markup=floor) == 'low_markup'
    # У кегов пол вдвое выше: 100%.
    assert d(markup=0.99, a_min=KEG_MARKUP_A_MIN, b_min=KEG_MARKUP_B_MIN) == 'check'
    assert d(markup=1.0, a_min=KEG_MARKUP_A_MIN, b_min=KEG_MARKUP_B_MIN) == 'low_markup'


def test_check_wins_over_every_other_rule():
    assert d(abc='C', markup=None, sales=1, weekly=[0, 0, 0, 1]) == 'check'
    assert d(abc='A', markup=-0.5, sales=100) == 'check'


def test_newcomer_is_all_sales_in_last_week():
    assert d(abc='C', markup=1.5, sales=3, weekly=[0, 0, 0, 3]) == 'new'
    assert d(abc='A', markup=1.5, sales=40, weekly=[0, 0, 0, 40]) == 'new'
    # Продажи были и раньше (в неделе или вне окна) — не новинка.
    assert d(abc='C', markup=1.5, sales=3, weekly=[0, 0, 3, 0]) == 'few'
    assert d(abc='C', markup=1.5, sales=3, weekly=[0, 0, 0, 3], outside=1.0) == 'few'
    # На одной неделе последняя корзина — весь период: признака нет.
    assert d(abc='C', markup=1.5, sales=3, weeks=1, weekly=[3]) == 'few'


def test_sales_without_any_weekly_movement_is_newcomer():
    """Кег открыт в последний день: порции есть, списание легло за границу
    периода — по неделям нули. Истории нет, это новинка, а не «слабые продажи»."""
    assert d(abc='C', markup=2.5, sales=12, weeks=4, weekly=[0, 0, 0, 0], a_min=2.5, b_min=2.0) == 'new'
    # А без продаж вовсе такой строки не бывает; на одной неделе — «мало данных» нет,
    # решение по правилам ниже.
    assert d(abc='C', markup=2.5, sales=12, weeks=1, weekly=[0], a_min=2.5, b_min=2.0) == 'weak'


def test_few_sales_below_minimum():
    n = MIN_SALES_FOR_VERDICT
    assert d(abc='A', sales=n - 1) == 'few'
    assert d(abc='C', markup=0.6, sales=n - 1) == 'few'
    assert d(abc='A', sales=n) == 'core'


def test_weak_is_revenue_c_with_enough_sales_whatever_the_markup():
    assert d(abc='C', markup=1.5, sales=5) == 'weak'
    assert d(abc='C', markup=0.7, sales=5) == 'weak'


def test_low_markup_is_below_owner_minimum_not_below_b():
    """«120 и 250 это минималка»: граница «поднять цену» — порог A, буква B лишь
    говорит, что позиция ниже минимума ненамного."""
    assert d(abc='A', markup=MARKUP_A_MIN - 0.01) == 'low_markup'      # 119% — B, но низкая
    assert d(abc='B', markup=MARKUP_A_MIN) == 'core'                    # 120% — минимум
    assert d(abc='B', markup=MARKUP_B_MIN) == 'low_markup'              # 100%
    assert d(abc='B', markup=0.99) == 'low_markup'
    kegs = dict(a_min=KEG_MARKUP_A_MIN, b_min=KEG_MARKUP_B_MIN)
    assert d(abc='A', markup=2.49, **kegs) == 'low_markup'
    assert d(abc='A', markup=2.5, **kegs) == 'core'
    assert d(abc='A', markup=2.0, **kegs) == 'low_markup'


def _rows():
    rows = []
    for index, (key, revenue) in enumerate([('core', 500.0), ('core', 300.0), ('weak', 50.0),
                                            ('few', 100.0), ('check', 0.0), ('new', 50.0)]):
        rows.append({'Id': index, 'ABC_Bucket': key, 'TotalRevenue': revenue})
    return rows


def test_cards_cover_all_rows_in_order_with_shares():
    cards = bucket_cards(_rows(), 30, 'pieces')
    assert [c['key'] for c in cards] == ['core', 'low_markup', 'weak', 'few', 'new', 'check']
    assert sum(c['count'] for c in cards) == 6
    assert abs(sum(c['revenue_share_percent'] for c in cards) - 100.0) < 1e-9
    core = cards[0]
    assert core['count'] == 2 and core['revenue'] == 800.0 and abs(core['revenue_share_percent'] - 80.0) < 1e-9
    assert cards[1]['count'] == 0 and cards[1]['revenue_share_percent'] == 0.0


def test_weak_verdict_only_from_four_weeks():
    short = next(c for c in bucket_cards(_rows(), MIN_DAYS_FOR_NEGATIVE_VERDICT - 1, 'pieces') if c['key'] == 'weak')
    full = next(c for c in bucket_cards(_rows(), MIN_DAYS_FOR_NEGATIVE_VERDICT, 'pieces') if c['key'] == 'weak')
    assert short['action'] == 'Смотреть за 4 недели' and short['tone'] == 'calm' and short['verdict_ready'] is False
    assert full['action'] == 'Вывести из ассортимента' and full['tone'] == 'bad' and full['verdict_ready'] is True
    assert 'не выносится' in short['rule'] and 'не выносится' not in full['rule']


def test_rule_texts_carry_the_thresholds():
    n = str(MIN_SALES_FOR_VERDICT)
    core = bucket_rule_text('core', MARKUP_A_MIN, MARKUP_B_MIN, 'pieces', 30)
    assert n in core and '120%' in core and 'минимум' in core
    assert '50%' in bucket_rule_text('check', MARKUP_A_MIN, MARKUP_B_MIN, 'pieces', 30)
    kegs = bucket_rule_text('low_markup', KEG_MARKUP_A_MIN, KEG_MARKUP_B_MIN, 'portions', 7)
    assert '250%' in kegs and 'порций' in kegs and n in kegs
    assert '100%' in bucket_rule_text('check', KEG_MARKUP_A_MIN, KEG_MARKUP_B_MIN, 'portions', 7)
    assert str(MIN_DAYS_FOR_NEGATIVE_VERDICT) in bucket_rule_text('weak', MARKUP_A_MIN, MARKUP_B_MIN, 'pieces', 30)


def test_deterministic():
    a = bucket_cards(_rows(), 30, 'pieces')
    b = bucket_cards(list(reversed(_rows())), 30, 'pieces')
    assert a == b


if __name__ == '__main__':
    print('Решения по ассортименту\n')
    _run('шесть групп с уникальным порядком', test_six_buckets_with_unique_order)
    _run('имена без метафор', test_names_are_plain_business_russian)
    _run('без себестоимости и ниже пола — сверить учёт', test_no_cost_or_below_floor_goes_to_check)
    _run('учёт побеждает остальные правила', test_check_wins_over_every_other_rule)
    _run('новинка — все продажи в последней неделе', test_newcomer_is_all_sales_in_last_week)
    _run('продажи без движений по неделям — новинка', test_sales_without_any_weekly_movement_is_newcomer)
    _run('мало продаж — ниже минимума', test_few_sales_below_minimum)
    _run('слабые продажи — выручка C при достатке продаж', test_weak_is_revenue_c_with_enough_sales_whatever_the_markup)
    _run('«поднять цену» ниже минимума владельца', test_low_markup_is_below_owner_minimum_not_below_b)
    _run('карточки покрывают все строки', test_cards_cover_all_rows_in_order_with_shares)
    _run('«вывести» только от четырёх недель', test_weak_verdict_only_from_four_weeks)
    _run('в правилах напечатаны пороги', test_rule_texts_carry_the_thresholds)
    _run('детерминизм', test_deterministic)
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
