"""Проверки баланса и потерь фасовки (core/packaging_losses.py).

    python tests/test_packaging_losses.py
    python -m pytest -q tests/test_packaging_losses.py

Формулы — зеркало баланса кегов (core/draft_kegs.py, tests/test_draft_kegs.py
TestLosses), единица — штуки. Отдельно проверяется то, чего у розлива нет:
связка товара склада с позицией продаж по DishId (и запасной вариант по
имени), диагностика отброшенных единиц и чужих типов проводок, сверка
«касса против склада».
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.packaging_analysis import PackagingAnalysis  # noqa: E402
from core.packaging_losses import PIECE_UNIT, build_losses_block, collect_stock  # noqa: E402

passed = 0
failed = 0


def _run(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f'  ok  {name}')
    except Exception as exc:  # noqa: BLE001 — тестовый раннер печатает любую причину
        failed += 1
        print(f'FAIL  {name}')
        print(f'      {type(exc).__name__}: {exc}')


P1, P2, P3 = 'prod-1', 'prod-2', 'prod-3'
FROM, TO = '2026-08-04', '2026-08-31'


def trans(bar, product_id, day, kind, out=0.0, inc=0.0, cost=0.0, name=None, unit=PIECE_UNIT):
    """Строка ответа get_packaging_writeoff_report() — та же форма, что у кегов."""
    return {
        'Account.Name': bar,
        'Product.Id': product_id,
        'Product.Name': name or f'{product_id} 0,500 бут.',
        'Product.MeasureUnit': unit,
        'DateTime.DateTyped': day,
        'TransactionType': kind,
        'Amount.Out': out,
        'Amount.In': inc,
        'Sum.Outgoing': cost,
    }


def sale(bar, dish_id, day, qty, revenue, cost, name=None):
    """Строка продаж фасовки с DishId (get_packaging_sales_report)."""
    return {
        'Store.Name': bar,
        'DishName': name or f'{dish_id} 0,500 бут.',
        'DishGroup.ThirdParent': 'Лагер (Ф)',
        'DishForeignName': 'Россия',
        'OpenDate.Typed': day,
        'DishAmountInt': qty,
        'DishDiscountSumInt': revenue,
        'ProductCostBase.ProductCost': cost,
        'DishId': dish_id,
    }


def build(rows, transactions, bar=None):
    return PackagingAnalysis(rows, FROM, TO, transactions=transactions).build(bar)


REFERENCE = [
    trans('Лиговский', P1, '2026-08-04', 'INVOICE', inc=48.0),
    trans('Лиговский', P1, '2026-08-05', 'SESSION_WRITEOFF', out=30.0, cost=9000.0),
    trans('Лиговский', P1, '2026-08-05', 'WRITEOFF', out=2.0),
    trans('Лиговский', P1, '2026-08-06', 'INVENTORY_CORRECTION', out=5.0, inc=1.0),
    trans('Лиговский', P1, '2026-08-07', 'TRANSFER', out=4.0, inc=1.0),
]
REFERENCE_SALES = [sale('Лиговский', P1, '2026-08-05', 30, 15000, 9000)]


# ==================== формулы баланса ====================

def test_balance_formula_mirrors_draft():
    """Изменение остатка = приход + перемещения в − продано − акты − недостача − перемещения из."""
    losses = build(REFERENCE_SALES, REFERENCE)['losses']
    assert losses['unit'] == 'шт'
    assert losses['inventory_net'] == 4.0
    # 48 + 1 − 30 − 2 − 4 − 4 = 9
    assert abs(losses['balance'] - 9.0) < 1e-9, losses['balance']
    assert abs(losses['spent'] - 40.0) < 1e-9, losses['spent']


def test_loss_shares_of_sold():
    losses = build(REFERENCE_SALES, REFERENCE)['losses']
    assert abs(losses['writeoff_percent_of_sold'] - 2 / 30 * 100) < 1e-9
    assert abs(losses['inventory_percent_of_sold'] - 4 / 30 * 100) < 1e-9


def test_by_item_row_and_percent_computed_on_server():
    """Строка расхождений считается на сервере, включая процент к проданному."""
    losses = build(REFERENCE_SALES, REFERENCE)['losses']
    assert len(losses['by_item']) == 1
    item = losses['by_item'][0]
    assert item['SoldQty'] == 30.0 and item['WriteoffQty'] == 2.0
    assert item['InventoryNetQty'] == 4.0 and item['LossQty'] == 6.0
    assert abs(item['LossPercentOfSold'] - 20.0) < 1e-9


def test_by_item_lists_only_items_with_losses():
    rows = [
        trans('Лиговский', P1, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
        trans('Лиговский', P2, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
        trans('Лиговский', P2, '2026-08-04', 'WRITEOFF', out=1.0),
    ]
    losses = build([], rows)['losses']
    assert [k['ProductId'] for k in losses['by_item']] == [P2]


def test_surplus_is_negative_net_and_not_a_loss():
    """Излишек инвентаризации — отрицательная недостача, в потери не входит."""
    rows = [
        trans('Лиговский', P1, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
        trans('Лиговский', P1, '2026-08-05', 'INVENTORY_CORRECTION', out=0.0, inc=3.0),
    ]
    losses = build([], rows)['losses']
    assert losses['inventory_net'] == -3.0
    assert abs(losses['balance'] - (-10.0 + 3.0)) < 1e-9
    item = losses['by_item'][0]
    assert item['InventoryNetQty'] == -3.0 and item['LossQty'] == 0.0
    assert item['LossPercentOfSold'] == 0.0


def test_percent_undefined_without_sales():
    rows = [trans('Лиговский', P1, '2026-08-04', 'WRITEOFF', out=2.0)]
    losses = build([], rows)['losses']
    assert losses['writeoff_percent_of_sold'] == 0.0
    assert losses['by_item'][0]['LossPercentOfSold'] is None


def test_sort_by_discrepancy_then_name():
    rows = [
        trans('Лиговский', 'b', '2026-08-04', 'WRITEOFF', out=1.0, name='Б'),
        trans('Лиговский', 'a', '2026-08-04', 'WRITEOFF', out=1.0, name='А'),
        trans('Лиговский', 'c', '2026-08-04', 'INVENTORY_CORRECTION', out=5.0, name='В'),
    ]
    losses = build([], rows)['losses']
    assert [k['ProductName'] for k in losses['by_item']] == ['В', 'А', 'Б']
    other = build([], list(reversed(rows)))['losses']
    assert [k['ProductName'] for k in other['by_item']] == ['В', 'А', 'Б']


# ==================== что отбрасывается и как об этом сказано ====================

def test_non_piece_units_excluded_but_reported():
    rows = [
        trans('Лиговский', P1, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
        trans('Лиговский', P2, '2026-08-04', 'SESSION_WRITEOFF', out=1.5, unit='кг', name='Орехи'),
    ]
    losses = build([], rows)['losses']
    assert losses['sold'] == 10.0, 'килограммы сложились со штуками'
    assert losses['diagnostics']['non_piece_products'] == [
        {'ProductId': P2, 'ProductName': 'Орехи', 'Unit': 'кг'}]


def test_corresponding_account_rows_add_nothing():
    """Служебный счёт даёт строки с нулями — они ничего не приносят в баланс."""
    rows = [
        trans('Лиговский', P1, '2026-08-04', 'SESSION_WRITEOFF', out=10.0),
        trans('Расход продуктов', P1, '2026-08-04', 'SESSION_WRITEOFF', out=0.0),
    ]
    losses = build([], rows)['losses']
    assert losses['sold'] == 10.0
    assert len(losses['by_item']) == 0


def test_unknown_types_counted_not_summed():
    """Возврат поставщику в баланс не входит (формула та же, что у кегов), но виден."""
    rows = [
        trans('Лиговский', P1, '2026-08-04', 'INVOICE', inc=10.0),
        trans('Лиговский', P1, '2026-08-05', 'OUTGOING_INVOICE', out=4.0),
        trans('Лиговский', P1, '2026-08-05', 'RETURNED_INVOICE', out=0.0),   # нулевая — не считаем
    ]
    losses = build([], rows)['losses']
    assert losses['balance'] == 10.0
    assert losses['diagnostics']['ignored_types'] == {'OUTGOING_INVOICE': 1}


def test_bar_scope_filters_and_total_merges():
    rows = [
        trans('Лиговский', P1, '2026-08-04', 'INVOICE', inc=10.0),
        trans('Варшавская', P1, '2026-08-04', 'INVOICE', inc=5.0),
        trans('Варшавская', P1, '2026-08-05', 'WRITEOFF', out=1.0),
    ]
    assert build([], rows, 'Лиговский')['losses']['invoice_in'] == 10.0
    assert build([], rows, 'Лиговский')['losses']['by_item'] == []
    total = build([], rows)['losses']
    assert total['invoice_in'] == 15.0
    assert len(total['by_item']) == 1 and total['by_item'][0]['WriteoffQty'] == 1.0


# ==================== связка со списком позиций ====================

def test_match_by_dish_id_and_fields_on_position():
    block = build(REFERENCE_SALES, REFERENCE)
    position = block['positions'][0]
    assert position['DishId'] == P1 and position['DishIds'] == [P1]
    assert block['losses']['by_item'][0]['PositionId'] == position['Id']
    assert block['losses']['by_item'][0]['MatchedBy'] == 'guid'
    assert position['SoldQtyStock'] == 30.0
    assert position['WriteoffQty'] == 2.0 and position['InventoryNetQty'] == 4.0
    assert position['LossQty'] == 6.0 and abs(position['LossPercentOfSold'] - 20.0) < 1e-9
    assert block['losses']['diagnostics']['match_mode'] == 'guid'


def test_match_by_guid_survives_rename():
    """Товар переименован в номенклатуре: имена разные, GUID один — связка держится."""
    sales = [sale('Лиговский', P1, '2026-08-05', 3, 1500, 900, name='Polnochnyj Progect IPA')]
    rows = [trans('Лиговский', P1, '2026-08-05', 'WRITEOFF', out=1.0, name='Polnochnyj Project IPA')]
    block = build(sales, rows)
    assert block['losses']['by_item'][0]['PositionId'] == block['positions'][0]['Id']


def test_fallback_by_name_when_sales_have_no_dish_id():
    """Старый кэш или фикстура без DishId: сопоставление по имени, режим виден."""
    sales = [sale('Лиговский', None, '2026-08-05', 3, 1500, 900, name='  Пиво А  ')]
    del sales[0]['DishId']
    rows = [trans('Лиговский', P1, '2026-08-05', 'WRITEOFF', out=1.0, name='Пиво А')]
    block = build(sales, rows)
    assert block['positions'][0]['DishId'] is None
    assert block['losses']['by_item'][0]['PositionId'] == block['positions'][0]['Id']
    assert block['losses']['by_item'][0]['MatchedBy'] == 'name'
    assert block['losses']['diagnostics']['match_mode'] == 'name'


def test_unmatched_product_is_reported_not_dropped():
    rows = [trans('Лиговский', P3, '2026-08-05', 'WRITEOFF', out=2.0, name='Со склада')]
    block = build(REFERENCE_SALES, rows)
    item = next(k for k in block['losses']['by_item'] if k['ProductId'] == P3)
    assert item['PositionId'] is None and item['MatchedBy'] is None
    assert block['losses']['diagnostics']['unmatched_products'] == 1


def test_register_vs_stock_delta():
    """Касса и склад считаются независимо; разница отдаётся, а не прячется."""
    sales = [sale('Лиговский', P1, '2026-08-05', 30, 15000, 9000)]
    rows = [trans('Лиговский', P1, '2026-08-05', 'SESSION_WRITEOFF', out=28.0)]
    diag = build(sales, rows)['losses']['diagnostics']
    assert diag['sold_by_register'] == 30.0 and diag['sold_by_stock'] == 28.0
    assert diag['sold_delta'] == -2.0


# ==================== край ====================

def test_no_transactions_gives_zeros_not_crash():
    for transactions in (None, []):
        block = PackagingAnalysis(REFERENCE_SALES, FROM, TO, transactions=transactions).build(None)
        losses = block['losses']
        assert losses['balance'] == 0.0 and losses['by_item'] == []
        assert losses['diagnostics']['has_transactions'] is False
        assert block['positions'][0]['LossQty'] == 0.0
        assert block['positions'][0]['LossPercentOfSold'] is None


def test_collect_stock_ignores_rows_without_product():
    stock, _ = collect_stock([{'Account.Name': 'Лиговский', 'Product.Id': '',
                               'Product.MeasureUnit': 'шт', 'TransactionType': 'INVOICE',
                               'Amount.In': 5}])
    assert stock == {}


def test_deterministic_and_serialisable():
    first = build(REFERENCE_SALES, REFERENCE)
    second = build(REFERENCE_SALES, REFERENCE)
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == \
        json.dumps(second, sort_keys=True, ensure_ascii=False)
    json.dumps(build([], REFERENCE), ensure_ascii=False)


if __name__ == '__main__':
    print('Баланс и потери фасовки\n')
    _run('формула баланса как у кегов', test_balance_formula_mirrors_draft)
    _run('доли потерь от проданного', test_loss_shares_of_sold)
    _run('строка расхождений и процент считаются на сервере',
         test_by_item_row_and_percent_computed_on_server)
    _run('в расхождениях только товары с потерями', test_by_item_lists_only_items_with_losses)
    _run('излишек — отрицательная недостача, не потеря', test_surplus_is_negative_net_and_not_a_loss)
    _run('процент не определён без продаж', test_percent_undefined_without_sales)
    _run('сортировка по расхождению, тай-брейк по имени', test_sort_by_discrepancy_then_name)
    _run('не в штуках — отброшено и показано', test_non_piece_units_excluded_but_reported)
    _run('служебный счёт ничего не приносит', test_corresponding_account_rows_add_nothing)
    _run('чужие типы проводок считаются, не суммируются', test_unknown_types_counted_not_summed)
    _run('разрез бара фильтрует, «Общая» схлопывает', test_bar_scope_filters_and_total_merges)
    _run('связка по DishId и поля на позиции', test_match_by_dish_id_and_fields_on_position)
    _run('связка по GUID переживает переименование', test_match_by_guid_survives_rename)
    _run('запасная связка по имени без DishId', test_fallback_by_name_when_sales_have_no_dish_id)
    _run('несопоставленный товар показан, а не потерян', test_unmatched_product_is_reported_not_dropped)
    _run('касса против склада', test_register_vs_stock_delta)
    _run('без проводок — нули, не падение', test_no_transactions_gives_zeros_not_crash)
    _run('строки без товара пропускаются', test_collect_stock_ignores_rows_without_product)
    _run('детерминизм и JSON', test_deterministic_and_serialisable)
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
