"""
Тесты расчёта расхода по складу (core/stock_consumption.py).

Self-runnable: `py -3 tests/test_stock_consumption.py` (совместимо с pytest).

Модуль чистый: сеть не нужна, iiko не дёргается. Проверяется то, что раньше
ломалось молча (S-01 в docs/technical/audits/STOCKS_AUDIT_2026-09-10.md):
фильтр по складу записи, знак и формат amount из iiko, знаменатель периода для
новинок, устойчивость к битым полям. Плюс один прогон на реальном кэше
storeOperations: расход одного склада не может превышать сетевой.
"""

import json
import os
import unittest
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.stock_consumption import (WINDOW_DAYS, aggregate_consumption, format_period,  # noqa: E402
                                    is_outgoing, new_stats, parse_ops_date, period_bounds)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS_CACHE = os.path.join(ROOT, 'data', 'cache', 'store_operations_report.json')

# Дата расчёта во всех синтетических тестах: окно 06.10.2025 .. 05.11.2025.
TODAY = date(2025, 11, 5)
DATE_FROM = date(2025, 10, 6)

STORE_A = 'store-a'
STORE_B = 'store-b'
PID = 'product-1'

EPS = 1e-9


def _op(product=PID, store=STORE_A, amount='-1.000000000', incoming='false',
        doc_type='SALES_DOCUMENT', op_date='20.10.2025'):
    """Запись storeOperations в том виде, как отдаёт iiko (все значения — строки)."""
    return {
        'product': product,
        'primaryStore': store,
        'amount': amount,
        'incoming': incoming,
        'documentType': doc_type,
        'date': op_date,
    }


# --- parse_ops_date / period_bounds / format_period ---------------------------

def test_parse_ops_date_normal():
    assert parse_ops_date('18.10.2025') == date(2025, 10, 18)
    assert parse_ops_date(' 18.10.2025 ') == date(2025, 10, 18)     # пробелы обрезаются


def test_parse_ops_date_empty():
    assert parse_ops_date('') is None
    assert parse_ops_date(None) is None


def test_parse_ops_date_garbage():
    assert parse_ops_date('мусор') is None
    assert parse_ops_date('2025-10-18') is None      # ISO-формат — не формат iiko v1
    assert parse_ops_date('32.13.2025') is None
    assert parse_ops_date(12345) is None


def test_period_bounds_default_window():
    assert WINDOW_DAYS == 30
    assert period_bounds(TODAY) == (DATE_FROM, TODAY)


def test_period_bounds_custom_window():
    assert period_bounds(TODAY, 7) == (date(2025, 10, 29), TODAY)
    assert period_bounds(date(2026, 1, 3), 5) == (date(2025, 12, 29), date(2026, 1, 3))


def test_format_period_iiko_v1():
    assert format_period(DATE_FROM, TODAY) == ('06.10.2025', '05.11.2025')
    assert format_period(date(2026, 1, 3), date(2026, 1, 3)) == ('03.01.2026', '03.01.2026')


# --- is_outgoing ------------------------------------------------------------

def test_is_outgoing_string_flags():
    assert is_outgoing({'incoming': 'false'}) is True
    assert is_outgoing({'incoming': 'true'}) is False
    assert is_outgoing({'incoming': 'True'}) is False
    assert is_outgoing({'incoming': 'FALSE'}) is True


def test_is_outgoing_missing_field_is_unknown():
    """Нет поля incoming — направление неизвестно: None, запись пропускается."""
    assert is_outgoing({}) is None
    assert is_outgoing({'incoming': None}) is None
    assert is_outgoing({'incoming': ''}) is None
    ops = [_op(amount='-5.000000000'), {'product': PID, 'primaryStore': STORE_A,
                                        'amount': '-7.000000000', 'date': '20.10.2025'}]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert abs(stats['outgoing'] - 5.0) < EPS
    assert stats['skipped'] == 1


def test_is_outgoing_boolean_values():
    """Если когда-нибудь придёт bool, а не строка — трактовка та же."""
    assert is_outgoing({'incoming': True}) is False
    assert is_outgoing({'incoming': False}) is True


# --- aggregate_consumption: скоуп по складу ---------------------------------

def test_store_filter_excludes_other_store():
    ops = [
        _op(store=STORE_A, amount='-2.000000000'),
        _op(store=STORE_B, amount='-5.000000000'),
        _op(store=STORE_B, amount='-1.000000000'),
    ]
    stats = aggregate_consumption(ops, None, STORE_A, TODAY)
    assert abs(stats[PID]['outgoing'] - 2.0) < EPS
    assert stats[PID]['scope'] == 'store'


def test_network_scope_counts_all_stores():
    ops = [
        _op(store=STORE_A, amount='-2.000000000'),
        _op(store=STORE_B, amount='-5.000000000'),
        _op(store=STORE_B, amount='-1.000000000'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)
    assert abs(stats[PID]['outgoing'] - 8.0) < EPS
    assert stats[PID]['scope'] == 'network'


def test_store_filter_product_only_on_other_store_gives_empty_stats():
    """Товар есть в product_ids, но движение только на чужом складе — нули, не KeyError."""
    ops = [_op(store=STORE_B, amount='-5.000000000')]
    stats = aggregate_consumption(ops, [PID], STORE_A, TODAY)
    assert stats[PID]['outgoing'] == 0.0
    assert stats[PID]['avg_per_day'] == 0.0
    assert stats[PID]['by_document_type'] == {}


# --- aggregate_consumption: product_ids -------------------------------------

def test_product_ids_none_collects_all_seen_products():
    ops = [_op(product='p1'), _op(product='p2'), _op(product='p2')]
    stats = aggregate_consumption(ops, None, None, TODAY)
    assert set(stats) == {'p1', 'p2'}
    assert abs(stats['p2']['outgoing'] - 2.0) < EPS


def test_product_ids_given_restricts_and_pads():
    ops = [_op(product='p1'), _op(product='p3')]
    stats = aggregate_consumption(ops, ['p1', 'p2'], None, TODAY)
    assert set(stats) == {'p1', 'p2'}          # p3 не запрашивали — его нет
    assert abs(stats['p1']['outgoing'] - 1.0) < EPS
    assert stats['p2'] == new_stats('network')  # пустая статистика без операций


def test_product_ids_empty_set_gives_empty_result():
    ops = [_op(product='p1')]
    assert aggregate_consumption(ops, [], None, TODAY) == {}


def test_record_without_product_is_skipped():
    ops = [_op(product=None), _op(product=''), _op(product='p1')]
    stats = aggregate_consumption(ops, None, None, TODAY)
    assert set(stats) == {'p1'}


# --- aggregate_consumption: outgoing / incoming -----------------------------

def test_outgoing_is_abs_sum_of_outgoing_records_only():
    ops = [
        _op(amount='-1.500000000', incoming='false'),
        _op(amount='-0.500000000', incoming='false'),
        _op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert abs(stats['outgoing'] - 2.0) < EPS
    assert abs(stats['incoming'] - 10.0) < EPS


def test_outgoing_uses_absolute_value_regardless_of_sign():
    """Списание с положительным amount (бывает у WRITEOFF) тоже идёт в расход по модулю."""
    ops = [
        _op(amount='-1.000000000', doc_type='SALES_DOCUMENT'),
        _op(amount='2.000000000', doc_type='WRITEOFF_DOCUMENT'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert abs(stats['outgoing'] - 3.0) < EPS


def test_transfers_and_writeoffs_count_as_outgoing_for_store():
    """Решение владельца 2026-09-10: перемещения ИЗ бара и списания входят в расход склада."""
    ops = [
        _op(amount='-1.000000000', doc_type='SALES_DOCUMENT'),
        _op(amount='-2.000000000', doc_type='INTERNAL_TRANSFER'),
        _op(amount='-3.000000000', doc_type='WRITEOFF_DOCUMENT'),
        _op(amount='4.000000000', incoming='true', doc_type='INTERNAL_TRANSFER'),
    ]
    stats = aggregate_consumption(ops, None, STORE_A, TODAY)[PID]
    assert abs(stats['outgoing'] - 6.0) < EPS
    assert abs(stats['incoming'] - 4.0) < EPS


def test_network_scope_excludes_internal_transfers():
    """Для «Общая» перемещение между своими складами — не расход и не приход:
    товар сеть не покинул, его продажа в баре-получателе посчитается сама."""
    ops = [
        _op(store=STORE_A, amount='-2.000000000', doc_type='INTERNAL_TRANSFER'),
        _op(store=STORE_B, amount='2.000000000', incoming='true', doc_type='INTERNAL_TRANSFER'),
        _op(store=STORE_B, amount='-1.000000000', doc_type='SALES_DOCUMENT'),
    ]
    net = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert abs(net['outgoing'] - 1.0) < EPS
    assert abs(net['incoming'] - 0.0) < EPS
    assert net['by_document_type'] == {'SALES_DOCUMENT': 1.0}
    store_a = aggregate_consumption(ops, None, STORE_A, TODAY)[PID]
    assert abs(store_a['outgoing'] - 2.0) < EPS


# --- aggregate_consumption: by_document_type --------------------------------

def test_by_document_type_breakdown():
    ops = [
        _op(amount='-1.000000000', doc_type='SALES_DOCUMENT'),
        _op(amount='-0.500000000', doc_type='SALES_DOCUMENT'),
        _op(amount='-2.000000000', doc_type='INTERNAL_TRANSFER'),
        _op(amount='-3.000000000', doc_type='WRITEOFF_DOCUMENT'),
        _op(amount='9.000000000', incoming='true', doc_type='INCOMING_INVOICE'),
    ]
    by_type = aggregate_consumption(ops, None, STORE_A, TODAY)[PID]['by_document_type']
    assert set(by_type) == {'SALES_DOCUMENT', 'INTERNAL_TRANSFER', 'WRITEOFF_DOCUMENT'}
    assert abs(by_type['SALES_DOCUMENT'] - 1.5) < EPS
    assert abs(by_type['INTERNAL_TRANSFER'] - 2.0) < EPS
    assert abs(by_type['WRITEOFF_DOCUMENT'] - 3.0) < EPS
    # приход в разбивку расхода не попадает
    assert 'INCOMING_INVOICE' not in by_type


def test_by_document_type_missing_type_goes_to_unknown():
    ops = [_op(amount='-1.000000000', doc_type=None), _op(amount='-1.000000000', doc_type='')]
    by_type = aggregate_consumption(ops, None, None, TODAY)[PID]['by_document_type']
    assert by_type == {'UNKNOWN': 2.0}


def test_by_document_type_sum_equals_outgoing():
    ops = [
        _op(amount='-1.250000000', doc_type='SALES_DOCUMENT'),
        _op(amount='-2.750000000', doc_type='INTERNAL_TRANSFER'),
        _op(amount='-0.250000000', doc_type=None),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert abs(sum(stats['by_document_type'].values()) - stats['outgoing']) < EPS


# --- aggregate_consumption: знаменатель периода для новинки ----------------

def test_new_product_denominator_is_days_since_first_incoming():
    """Первый приход 20.10 (позже начала окна), первый расход 22.10 → делитель 17 дней (20.10..05.11)."""
    ops = [
        _op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='20.10.2025'),
        _op(amount='-3.400000000', op_date='22.10.2025'),
        _op(amount='-3.400000000', op_date='30.10.2025'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert stats['is_new'] is True
    assert stats['first_in'] == date(2025, 10, 20)
    assert stats['first_out'] == date(2025, 10, 22)
    assert stats['days_in_period'] == 17
    assert abs(stats['avg_per_day'] - 6.8 / 17) < EPS


def test_incoming_on_window_start_is_not_new():
    """Приход в первый день окна (date_from) — обычный товар: делитель 30."""
    ops = [
        _op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='06.10.2025'),
        _op(amount='-3.000000000', op_date='10.10.2025'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert stats['is_new'] is False
    assert stats['days_in_period'] == WINDOW_DAYS
    assert abs(stats['avg_per_day'] - 3.0 / 30) < EPS


def test_outgoing_before_incoming_is_not_new():
    """Расход был до прихода — товар уже стоял на остатке, это не новинка."""
    ops = [
        _op(amount='-1.000000000', op_date='15.10.2025'),
        _op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='20.10.2025'),
        _op(amount='-1.000000000', op_date='25.10.2025'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert stats['is_new'] is False
    assert stats['days_in_period'] == WINDOW_DAYS
    assert abs(stats['avg_per_day'] - 2.0 / 30) < EPS


def test_incoming_without_outgoing_is_new_with_zero_avg():
    ops = [_op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='25.10.2025')]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert stats['is_new'] is True
    assert stats['first_out'] is None
    assert stats['days_in_period'] == 12          # 25.10..05.11 включительно
    assert stats['outgoing'] == 0.0
    assert stats['avg_per_day'] == 0.0


def test_incoming_and_outgoing_same_day_is_new():
    ops = [
        _op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='01.11.2025'),
        _op(amount='-2.000000000', op_date='01.11.2025'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert stats['is_new'] is True
    assert stats['days_in_period'] == 5           # 01.11..05.11


def test_new_product_denominator_lower_clamp():
    """Приход сегодня → 1 день; приход «из будущего» (кривые данные) → тоже 1, не 0 и не минус."""
    today_ops = [_op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='05.11.2025'),
                 _op(amount='-2.000000000', op_date='05.11.2025')]
    stats = aggregate_consumption(today_ops, None, None, TODAY)[PID]
    assert stats['is_new'] is True
    assert stats['days_in_period'] == 1
    assert abs(stats['avg_per_day'] - 2.0) < EPS

    # Приход с датой позже today (кривые данные) новинкой не считается.
    future_ops = [_op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='07.11.2025')]
    stats = aggregate_consumption(future_ops, None, None, TODAY)[PID]
    assert stats['is_new'] is False
    assert stats['days_in_period'] == WINDOW_DAYS


def test_opening_stock_blocks_novelty_for_restocked_item():
    """Товар с остатком на начало окна, которому просто привезли ещё, — не новинка.

    stock_now 10, приход 6, расход 2 → остаток на начало окна 10 − 6 + 2 = 6 > 0.
    """
    ops = [_op(amount='6.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='28.10.2025'),
           _op(amount='-2.000000000', op_date='04.11.2025')]
    stats = aggregate_consumption(ops, None, None, TODAY, stock_now={PID: 10.0})[PID]
    assert stats['is_new'] is False
    assert stats['days_in_period'] == WINDOW_DAYS
    assert abs(stats['opening_stock'] - 6.0) < EPS


def test_opening_stock_zero_keeps_novelty():
    """Распроданный (или новый) товар: остаток на начало окна 4 − 6 + 2 = 0 → новинка."""
    ops = [_op(amount='6.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='28.10.2025'),
           _op(amount='-2.000000000', op_date='04.11.2025')]
    stats = aggregate_consumption(ops, None, None, TODAY, stock_now={PID: 4.0})[PID]
    assert stats['is_new'] is True
    assert stats['days_in_period'] == 9            # 28.10 .. 05.11 включительно
    assert abs(stats['opening_stock'] - 0.0) < EPS
    # Без stock_now проверка остатка не выполняется — новинка по датам.
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert stats['is_new'] is True
    assert stats['opening_stock'] is None


def test_zero_amount_records_do_not_set_first_dates():
    """Нулевой приход (сторно) не делает товар новинкой."""
    ops = [_op(amount='0.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='28.10.2025'),
           _op(amount='-2.000000000', op_date='04.11.2025')]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert stats['first_in'] is None
    assert stats['is_new'] is False


def test_new_product_denominator_upper_clamp_is_window():
    """Приход на второй день окна → 30 дней ровно, не больше окна."""
    ops = [
        _op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='07.10.2025'),
        _op(amount='-3.000000000', op_date='08.10.2025'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert stats['is_new'] is True
    assert stats['days_in_period'] == WINDOW_DAYS


def test_new_product_denominator_respects_custom_window():
    """Окно 7 дней (30.10..05.11): приход 31.10 → новинка, делитель 6; приход 30.10 — не новинка."""
    ops = [
        _op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='31.10.2025'),
        _op(amount='-3.000000000', op_date='01.11.2025'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY, window_days=7)[PID]
    assert stats['is_new'] is True
    assert stats['days_in_period'] == 6

    ops = [
        _op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='29.10.2025'),
        _op(amount='-3.000000000', op_date='01.11.2025'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY, window_days=7)[PID]
    assert stats['is_new'] is False
    assert stats['days_in_period'] == 7


def test_novelty_is_decided_per_store_scope():
    """На складе A первый приход 20.10 и расход после — новинка; по сети расход был 10.10 на B — нет."""
    ops = [
        _op(store=STORE_B, amount='-1.000000000', op_date='10.10.2025'),
        _op(store=STORE_A, amount='5.000000000', incoming='true', doc_type='INTERNAL_TRANSFER', op_date='20.10.2025'),
        _op(store=STORE_A, amount='-1.000000000', op_date='21.10.2025'),
    ]
    store_stats = aggregate_consumption(ops, None, STORE_A, TODAY)[PID]
    network_stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert store_stats['is_new'] is True and store_stats['days_in_period'] == 17
    assert network_stats['is_new'] is False and network_stats['days_in_period'] == WINDOW_DAYS


# --- aggregate_consumption: формат amount из iiko ---------------------------

def test_amount_as_iiko_string_with_nine_decimals():
    ops = [
        _op(amount='-0.500000000'),
        _op(amount='-0.250000000'),
        _op(amount='1.000000000', incoming='true', doc_type='INCOMING_INVOICE'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert abs(stats['outgoing'] - 0.75) < EPS
    assert abs(stats['incoming'] - 1.0) < EPS


def test_amount_numeric_types_also_accepted():
    ops = [_op(amount=-1.5), _op(amount=2), _op(amount='-1')]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert abs(stats['outgoing'] - 4.5) < EPS


# --- aggregate_consumption: битые данные ------------------------------------

def test_broken_amount_does_not_break_aggregation():
    ops = [
        _op(amount='abc'),
        _op(amount=None),
        _op(amount=''),
        {'product': PID, 'primaryStore': STORE_A, 'incoming': 'false', 'date': '20.10.2025'},  # нет amount
        _op(amount='-1.000000000'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert abs(stats['outgoing'] - 1.0) < EPS
    assert abs(stats['by_document_type'].get('SALES_DOCUMENT', 0.0) - 1.0) < EPS


def test_broken_date_counts_amount_but_not_first_dates():
    ops = [
        _op(amount='10.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='мусор'),
        _op(amount='-2.000000000', op_date=None),
        _op(amount='-1.000000000', op_date=''),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert abs(stats['outgoing'] - 3.0) < EPS
    assert abs(stats['incoming'] - 10.0) < EPS
    assert stats['first_in'] is None
    assert stats['first_out'] is None
    assert stats['is_new'] is False
    assert stats['days_in_period'] == WINDOW_DAYS
    assert abs(stats['avg_per_day'] - 3.0 / 30) < EPS


def test_broken_date_on_incoming_does_not_hide_novelty_from_later_valid_incoming():
    """Битая дата у одного прихода игнорируется; новизна по первому приходу с датой."""
    ops = [
        _op(amount='5.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='xx.yy.zzzz'),
        _op(amount='5.000000000', incoming='true', doc_type='INCOMING_INVOICE', op_date='25.10.2025'),
        _op(amount='-1.000000000', op_date='26.10.2025'),
    ]
    stats = aggregate_consumption(ops, None, None, TODAY)[PID]
    assert stats['first_in'] == date(2025, 10, 25)
    assert stats['is_new'] is True
    assert stats['days_in_period'] == 12


def test_empty_operations_and_new_stats_shape():
    stats = aggregate_consumption([], ['p1'], STORE_A, TODAY)
    assert stats == {'p1': new_stats('store')}
    assert new_stats('store', 7)['days_in_period'] == 7
    assert set(new_stats('network')) == {'outgoing', 'incoming', 'by_document_type', 'first_in',
                                         'first_out', 'last_in', 'last_in_amount', 'days_in_period',
                                         'avg_per_day', 'is_new', 'opening_stock', 'skipped', 'scope'}


def test_last_incoming_date_and_amount():
    """last_in — дата последнего прихода в окне, last_in_amount — сумма приходов в этот день."""
    inv = dict(product='p1', store=STORE_A, incoming='true', doc_type='INCOMING_INVOICE')
    ops = [
        _op(amount='10.000000000', op_date='02.11.2025', **inv),
        _op(amount='4.000000000', op_date='04.11.2025', **inv),
        _op(amount='6.000000000', op_date='04.11.2025', **inv),
        _op(product='p1', store=STORE_A, amount='-3.000000000', op_date='05.11.2025'),
        _op(product='p1', store=STORE_B, amount='50.000000000', op_date='05.11.2025',
            incoming='true', doc_type='INCOMING_INVOICE'),   # другой склад
    ]
    st = aggregate_consumption(ops, ['p1'], STORE_A, TODAY)['p1']
    assert st['last_in'] == date(2025, 11, 4) and st['last_in_amount'] == 10.0
    assert aggregate_consumption([], ['p1'], STORE_A, TODAY)['p1']['last_in'] is None


# --- интеграция на реальном кэше storeOperations ---------------------------

def test_real_cache_store_consumption_never_exceeds_network():
    """На реальной выгрузке (окт–ноя 2025): расход одного склада без перемещений <= сетевого по
    каждому товару, хотя бы у одного товара строго меньше, а сумма по складам без перемещений
    равна сетевому (в сети перемещения между своими складами не считаются)."""
    if not os.path.exists(OPS_CACHE):
        raise unittest.SkipTest(f'нет {OPS_CACHE}')
    with open(OPS_CACHE, encoding='utf-8') as f:
        ops = json.load(f)
    assert len(ops) > 1000

    today = date(2025, 11, 5)
    network = aggregate_consumption(ops, None, None, today)
    stores = sorted({r.get('primaryStore') for r in ops if r.get('primaryStore')})
    assert len(stores) >= 2

    # В реальной выгрузке нет расходных записей с положительным amount и приходных с
    # отрицательным: abs() в _amount опирается на это; при смене формата iiko тест
    # сработает первым.
    for r in ops:
        amt = float(r.get('amount') or 0)
        if r.get('incoming') == 'false':
            assert amt <= 0, r
        else:
            assert amt >= 0, r

    def without_transfers(st):
        return st['outgoing'] - st['by_document_type'].get('INTERNAL_TRANSFER', 0.0)

    per_store = {s: aggregate_consumption(ops, None, s, today) for s in stores}
    strictly_less_seen = False
    for store, stats in per_store.items():
        for pid, st in stats.items():
            # Товар, у которого в сети только перемещения, в сетевой статистике отсутствует.
            net_st = network.get(pid) or new_stats('network')
            net = net_st['outgoing']
            assert 'INTERNAL_TRANSFER' not in net_st['by_document_type']
            own = without_transfers(st)
            assert own <= net + EPS, (store, pid, own, net)
            if own < net - EPS:
                strictly_less_seen = True
    assert strictly_less_seen

    # Записи без склада отсутствуют, значит сумма по складам без перемещений сходится с сетью.
    for pid, net_st in network.items():
        total = sum(without_transfers(per_store[s][pid]) for s in stores if pid in per_store[s])
        assert abs(total - net_st['outgoing']) < 1e-6, (pid, total, net_st['outgoing'])


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except unittest.SkipTest as e:
            print(f'SKIP {t.__name__}: {e}')
        except Exception as e:
            failed += 1
            import traceback
            print(f'FAIL {t.__name__}: {e}')
            traceback.print_exc()
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(_run())
