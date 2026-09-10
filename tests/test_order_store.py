"""
Тесты хранилища заказов поставщикам (core/order_store.py) и календаря поставок
(core/supplier_calendar.py) — этап 1 редизайна «Заказы и остатки» (2026-09-10).

Self-runnable: `py -3 tests/test_order_store.py` (совместимо с pytest).

Файл заказов — временный (tempfile), диск /kultura и data/ не трогаются.

Что проверяется:
- черновик: добавление/обновление/удаление позиций (qty <= 0 удаляет), автор,
  пустой черновик исчезает, количества по бару и по сети, очистка;
- отправка: черновик становится заказом (id, статус sent, позиции по бару и
  названию), пустой черновик и мусорная дата — ValueError;
- список: открытые заказы всегда, закрытые только за N дней, новые первыми;
- «приехало» с корректировкой факта, отмена, запреты по статусам;
- «в пути»: суммы по открытым заказам по бару/сети, факт вместо плана,
  оприходованные позиции и отменённые заказы не считаются;
- сверка с приходами iiko: накладная по товару и складу бара не раньше дня
  отправки → позиция posted, заказ posted когда все позиции; без изменений
  файл не переписывается;
- текст для чата: порядок баров как в сети, позиции по названию, целые без
  «.0», строка ожидаемой поставки с днём недели;
- календарь: пропуск выходных, lead_time в днях доставки, горизонт, задержка.
"""

import os
import sys
import json
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import order_store as osm  # noqa: E402
from core.order_store import OrderStore, order_text, draft_key  # noqa: E402
from core.supplier_calendar import (next_delivery_date, delivery_after, horizon_days,  # noqa: E402
                                    is_overdue, ORDER_OVERDUE_GRACE_DAYS)

USER_A = {'login': 'anna', 'display_name': 'Анна'}
USER_B = {'login': 'boris', 'display_name': 'Борис'}
BAR_LIG = 'Лиговский'
BAR_BOL = 'Большой пр. В.О'
STORE_LIG = 'store-lig'
STORE_BOL = 'store-bol'
BAR_STORES = {BAR_LIG: STORE_LIG, BAR_BOL: STORE_BOL}


def _store():
    tmp = tempfile.mkdtemp(prefix='orders_test_')
    return OrderStore(os.path.join(tmp, 'orders.json'))


def _item(pid, bar, qty, name=None, unit='шт', kind='bottle', recommended=None):
    return {'product_id': pid, 'bar': bar, 'qty': qty, 'name': name or pid,
            'unit': unit, 'kind': kind, 'recommended': recommended}


def _raw(store):
    with open(store.data_file, encoding='utf-8') as f:
        return json.load(f)


# --- черновик --------------------------------------------------------------

def test_draft_add_update_remove():
    s = _store()
    d = s.set_draft_items('Метро', [_item('p1', BAR_LIG, 3, 'Кола'), _item('p2', BAR_BOL, 1.5, 'Масло', 'л', 'kitchen', 2)], USER_A)
    assert d['supplier'] == 'Метро'
    assert set(d['items']) == {draft_key('p1', BAR_LIG), draft_key('p2', BAR_BOL)}
    it = d['items'][draft_key('p1', BAR_LIG)]
    assert it['qty'] == 3.0 and it['updated_by'] == 'anna' and it['unit'] == 'шт'
    assert d['items'][draft_key('p2', BAR_BOL)]['recommended'] == 2
    assert d['updated_by'] == 'anna'

    d = s.set_draft_item('Метро', _item('p1', BAR_LIG, 5), USER_B)
    assert d['items'][draft_key('p1', BAR_LIG)]['qty'] == 5.0
    assert d['items'][draft_key('p1', BAR_LIG)]['updated_by'] == 'boris'
    assert d['updated_by'] == 'boris'

    # qty 0 удаляет позицию; последняя удалённая позиция убирает черновик целиком
    d = s.set_draft_item('Метро', _item('p1', BAR_LIG, 0), USER_A)
    assert draft_key('p1', BAR_LIG) not in d['items']
    assert s.set_draft_item('Метро', _item('p2', BAR_BOL, -1), USER_A) is None
    assert s.get_drafts() == {}


def test_draft_validation_and_qty_coercion():
    s = _store()
    for bad in ({'product_id': '', 'bar': BAR_LIG, 'qty': 1}, {'product_id': 'p', 'bar': '', 'qty': 1}):
        try:
            s.set_draft_item('Метро', bad, USER_A)
            assert False, bad
        except ValueError:
            pass
    try:
        s.set_draft_item('', [_item('p', BAR_LIG, 1)], USER_A)
        assert False
    except ValueError:
        pass
    # мусор в qty → 0 → позиция не создаётся; NaN тоже 0
    assert s.set_draft_item('Метро', {'product_id': 'p', 'bar': BAR_LIG, 'qty': 'abc'}, USER_A) is None
    assert s.set_draft_item('Метро', {'product_id': 'p', 'bar': BAR_LIG, 'qty': float('nan')}, USER_A) is None
    # без пользователя автор 'unknown', имя по умолчанию = product_id
    d = s.set_draft_item('Метро', {'product_id': 'p', 'bar': BAR_LIG, 'qty': '2'}, None)
    it = d['items'][draft_key('p', BAR_LIG)]
    assert it['qty'] == 2.0 and it['updated_by'] == 'unknown' and it['name'] == 'p'


def test_draft_quantities_and_clear():
    s = _store()
    s.set_draft_items('Метро', [_item('p1', BAR_LIG, 3), _item('p1', BAR_BOL, 2)], USER_A)
    s.set_draft_items('Лента', [_item('p1', BAR_LIG, 1), _item('p2', BAR_LIG, 4)], USER_A)
    assert s.draft_quantities(BAR_LIG) == {'p1': 4.0, 'p2': 4.0}
    assert s.draft_quantities(BAR_BOL) == {'p1': 2.0}
    assert s.draft_quantities() == {'p1': 6.0, 'p2': 4.0}
    assert s.clear_drafts('Нет такого') == 0
    assert s.clear_drafts('Лента') == 1
    assert set(s.get_drafts()) == {'Метро'}
    assert s.clear_drafts() == 1
    assert s.get_drafts() == {}
    assert s.clear_drafts() == 0


# --- отправка и список -----------------------------------------------------

def test_send_makes_order_and_empties_draft():
    s = _store()
    s.set_draft_items('Метро', [_item('p2', BAR_LIG, 2, 'Яблоко'), _item('p1', BAR_LIG, 3, 'Кола'),
                                _item('p1', BAR_BOL, 1, 'Кола')], USER_A)
    o = s.send('Метро', USER_A, expected_at='2026-09-14', note='до 12:00')
    assert o['id'].startswith('ord-') and o['status'] == 'sent'
    assert o['sent_by'] == 'anna' and o['sent_by_name'] == 'Анна'
    assert o['expected_at'] == '2026-09-14' and o['note'] == 'до 12:00'
    assert [(i['bar'], i['name'], i['qty']) for i in o['items']] == [
        (BAR_BOL, 'Кола', 1.0), (BAR_LIG, 'Кола', 3.0), (BAR_LIG, 'Яблоко', 2.0)]
    assert s.get_drafts() == {}
    assert s.get_order(o['id'])['id'] == o['id']
    assert s.get_order('nope') is None
    # повторная отправка пустого черновика и мусорная дата
    for kwargs in ({}, {'expected_at': 'вчера'}):
        try:
            s.send('Метро', USER_A, **kwargs)
            assert False, kwargs
        except ValueError:
            pass


def _seed_orders(s):
    """Три заказа с разными датами/статусами прямо в файле (sent_at в прошлом)."""
    data = s._load()
    data['orders'] = [
        {'id': 'old-posted', 'supplier': 'Метро', 'status': 'posted', 'sent_at': '2026-07-01T10:00:00',
         'items': [{'product_id': 'p1', 'bar': BAR_LIG, 'name': 'Кола', 'unit': 'шт', 'qty': 5, 'posted_at': '2026-07-02'}]},
        {'id': 'old-sent', 'supplier': 'Лента', 'status': 'sent', 'sent_at': '2026-07-05T10:00:00',
         'expected_at': '2026-07-07',
         'items': [{'product_id': 'p1', 'bar': BAR_LIG, 'name': 'Кола', 'unit': 'шт', 'qty': 7}]},
        {'id': 'recent-cancelled', 'supplier': 'Метро', 'status': 'cancelled', 'sent_at': '2026-09-09T10:00:00',
         'items': [{'product_id': 'p2', 'bar': BAR_BOL, 'name': 'Масло', 'unit': 'л', 'qty': 2}]},
    ]
    s._save(data)


def test_list_orders_window_and_filters():
    s = _store()
    _seed_orders(s)
    fixed_today = date(2026, 9, 10)

    class _FakeDT(osm.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(fixed_today.year, fixed_today.month, fixed_today.day, 12, 0, 0)

    saved = osm.datetime
    osm.datetime = _FakeDT
    try:
        ids = [o['id'] for o in s.list_orders(days=30)]
        # открытый старый заказ виден всегда; старый posted отрезан окном; новые первыми
        assert ids == ['recent-cancelled', 'old-sent']
        assert [o['id'] for o in s.list_orders(days=365)] == ['recent-cancelled', 'old-sent', 'old-posted']
        assert [o['id'] for o in s.list_orders(days=30, statuses=['cancelled'])] == ['recent-cancelled']
        assert [o['id'] for o in s.list_orders(days=0)] == ['recent-cancelled', 'old-sent', 'old-posted']
    finally:
        osm.datetime = saved


# --- приёмка, отмена, статусы ---------------------------------------------

def test_received_cancel_and_status_guards():
    s = _store()
    s.set_draft_items('Метро', [_item('p1', BAR_LIG, 3), _item('p2', BAR_LIG, 2)], USER_A)
    o = s.send('Метро', USER_A)
    r = s.mark_received(o['id'], USER_B, received_items=[{'product_id': 'p1', 'bar': BAR_LIG, 'qty': 2}], note='одной не хватило')
    assert r['status'] == 'received' and r['received_by'] == 'boris' and r['note'] == 'одной не хватило'
    by_pid = {i['product_id']: i for i in r['items']}
    assert by_pid['p1']['received_qty'] == 2.0 and 'received_qty' not in by_pid['p2']
    # «приехало» повторно допустимо (статус остаётся received), после отмены — нет
    assert s.mark_received(o['id'], USER_A)['status'] == 'received'
    c = s.cancel(o['id'], USER_A, note='поставщик не смог')
    assert c['status'] == 'cancelled' and c['cancelled_by'] == 'anna'
    try:
        s.mark_received(o['id'], USER_A)
        assert False
    except ValueError:
        pass
    for fn in (s.mark_received, s.cancel):
        try:
            fn('nope', USER_A)
            assert False
        except KeyError:
            pass
    # оприходованный заказ отменить нельзя
    data = s._load()
    data['orders'][0]['status'] = 'posted'
    s._save(data)
    try:
        s.cancel(o['id'], USER_A)
        assert False
    except ValueError:
        pass


# --- «в пути» ----------------------------------------------------------------

def test_open_quantities_by_bar_and_network():
    s = _store()
    s.set_draft_items('Метро', [_item('p1', BAR_LIG, 3), _item('p1', BAR_BOL, 2), _item('p2', BAR_LIG, 1)], USER_A)
    o1 = s.send('Метро', USER_A)
    s.set_draft_items('Лента', [_item('p1', BAR_LIG, 10)], USER_A)
    o2 = s.send('Лента', USER_A)
    s.set_draft_items('Лента', [_item('p1', BAR_LIG, 100)], USER_A)
    o3 = s.send('Лента', USER_A)
    s.cancel(o3['id'], USER_A)                                     # отменённый не считается
    s.mark_received(o2['id'], USER_A, [{'product_id': 'p1', 'bar': BAR_LIG, 'qty': 8}])  # факт вместо плана

    assert s.open_quantities(BAR_LIG) == {'p1': 11.0, 'p2': 1.0}
    assert s.open_quantities(BAR_BOL) == {'p1': 2.0}
    assert s.open_quantities() == {'p1': 13.0, 'p2': 1.0}
    open_lig = s.open_orders_for(BAR_LIG)
    assert sorted(x['order_id'] for x in open_lig['p1']) == sorted([o1['id'], o2['id']])
    assert {x['status'] for x in open_lig['p1']} == {'sent', 'received'}
    assert [x['qty'] for x in open_lig['p1'] if x['order_id'] == o2['id']] == [8.0]

    # оприходованная позиция выпадает из «в пути», даже если заказ ещё открыт
    data = s._load()
    for it in data['orders'][0]['items']:
        if it['product_id'] == 'p2':
            it['posted_at'] = '2026-09-11'
    s._save(data)
    assert s.open_quantities(BAR_LIG) == {'p1': 11.0}


def _inv(pid, store, day, doc='INCOMING_INVOICE', incoming='true'):
    return {'product': pid, 'primaryStore': store, 'amount': '10.0', 'incoming': incoming,
            'documentType': doc, 'date': day}


def test_reconcile_with_incoming_invoices():
    s = _store()
    data = s._load()
    data['orders'] = [
        {'id': 'o1', 'supplier': 'Метро', 'status': 'sent', 'sent_at': '2026-09-08T10:00:00',
         'items': [{'product_id': 'p1', 'bar': BAR_LIG, 'name': 'Кола', 'unit': 'шт', 'qty': 5},
                   {'product_id': 'p2', 'bar': BAR_BOL, 'name': 'Масло', 'unit': 'л', 'qty': 2}]},
        {'id': 'o2', 'supplier': 'Лента', 'status': 'received', 'sent_at': '2026-09-09T10:00:00',
         'items': [{'product_id': 'p1', 'bar': BAR_LIG, 'name': 'Кола', 'unit': 'шт', 'qty': 7}]},
        {'id': 'o3', 'supplier': 'Лента', 'status': 'cancelled', 'sent_at': '2026-09-01T10:00:00',
         'items': [{'product_id': 'p1', 'bar': BAR_LIG, 'name': 'Кола', 'unit': 'шт', 'qty': 7}]},
    ]
    s._save(data)
    ops = [
        _inv('p1', STORE_LIG, '07.09.2026'),                      # раньше отправки — не считается
        _inv('p1', STORE_BOL, '09.09.2026'),                      # другой склад — не считается
        _inv('p1', STORE_LIG, '09.09.2026', doc='INTERNAL_TRANSFER'),  # не накладная
        _inv('p1', STORE_LIG, '09.09.2026', incoming='false'),    # не приход
        _inv('p1', STORE_LIG, '10.09.2026'),                      # подходит o1 и o2
        _inv('p1', STORE_LIG, '11.09.2026'),
        _inv('p2', STORE_LIG, 'мусор'),                           # битая дата пропускается
    ]
    assert s.reconcile_with_operations(ops, BAR_STORES) == 2
    o1, o2, o3 = (s.get_order(i) for i in ('o1', 'o2', 'o3'))
    assert o1['status'] == 'sent'                                  # p2 ещё не оприходован
    assert o1['items'][0]['posted_at'] == '2026-09-10'             # ближайшая подходящая накладная
    assert 'posted_at' not in o1['items'][1]
    assert o2['status'] == 'posted' and o2['posted_at'] and o2['items'][0]['posted_at'] == '2026-09-10'
    assert o3['status'] == 'cancelled' and 'posted_at' not in o3['items'][0]
    assert s.open_quantities(BAR_LIG) == {}
    assert s.open_quantities(BAR_BOL) == {'p2': 2.0}

    # повторная сверка ничего не меняет и файл не переписывает
    mtime = os.path.getmtime(s.data_file)
    assert s.reconcile_with_operations(ops, BAR_STORES) == 0
    assert os.path.getmtime(s.data_file) == mtime
    assert s.reconcile_with_operations([], BAR_STORES) == 0

    # приход масла на Большой закрывает o1
    assert s.reconcile_with_operations([_inv('p2', STORE_BOL, '12.09.2026')], BAR_STORES) == 1
    assert s.get_order('o1')['status'] == 'posted'


# --- файл --------------------------------------------------------------------

def test_persistence_and_corrupted_file():
    s = _store()
    s.set_draft_item('Метро', _item('p1', BAR_LIG, 3), USER_A)
    again = OrderStore(s.data_file)
    assert again.draft_quantities(BAR_LIG) == {'p1': 3.0}
    raw = _raw(s)
    assert raw['version'] == osm.SCHEMA_VERSION and 'drafts' in raw and 'orders' in raw
    with open(s.data_file, 'w', encoding='utf-8') as f:
        f.write('{not json')
    assert OrderStore(s.data_file).get_drafts() == {}
    with open(s.data_file, 'w', encoding='utf-8') as f:
        f.write('[]')
    assert OrderStore(s.data_file).list_orders() == []
    missing = OrderStore(os.path.join(tempfile.mkdtemp(), 'none.json'))
    assert missing.get_drafts() == {} and missing.open_quantities() == {}


# --- текст для чата ----------------------------------------------------------

def test_order_text_format():
    order = {
        'supplier': 'Метро', 'sent_at': '2026-09-10T14:02:00', 'expected_at': '2026-09-14',
        'items': [
            {'product_id': 'p2', 'bar': BAR_LIG, 'name': 'Яблоко', 'unit': 'кг', 'qty': 1.5},
            {'product_id': 'p1', 'bar': BAR_LIG, 'name': 'Кола', 'unit': 'шт', 'qty': 3.0},
            {'product_id': 'p1', 'bar': BAR_BOL, 'name': 'Кола', 'unit': 'шт', 'qty': 12},
        ],
    }
    text = order_text(order, [BAR_BOL, BAR_LIG])
    assert text.split('\n') == [
        'Заказ, чт 10.09',
        'Поставщик: Метро',
        f'{BAR_BOL}:',
        '- Кола — 12 шт',
        f'{BAR_LIG}:',
        '- Кола — 3 шт',
        '- Яблоко — 1.5 кг',
        'Ожидаемая поставка: пн 14.09 (ориентировочно)',
    ]
    # без порядка баров — по алфавиту; без даты поставки — без последней строки
    order['expected_at'] = None
    lines = order_text(order).split('\n')
    assert lines[2] == f'{BAR_BOL}:' and 'Ожидаемая' not in lines[-1]


# --- календарь поставок -------------------------------------------------------

def test_next_delivery_date_skips_weekends():
    fri, sat, sun, wed, thu = (date(2026, 9, 11), date(2026, 9, 12), date(2026, 9, 13),
                               date(2026, 9, 9), date(2026, 9, 10))
    mon = date(2026, 9, 14)
    assert next_delivery_date(fri, 1) == mon
    assert next_delivery_date(sat, 1) == mon
    assert next_delivery_date(sun, 1) == mon
    assert next_delivery_date(wed, 3) == mon
    assert next_delivery_date(thu, 1) == fri
    assert next_delivery_date(thu, 0) == fri            # lead < 1 считается как 1
    assert next_delivery_date(thu, 2) == mon
    # поставщик возит только по вторникам и четвергам
    assert next_delivery_date(thu, 1, (1, 3)) == date(2026, 9, 15)
    assert next_delivery_date(thu, 2, (1, 3)) == date(2026, 9, 17)
    # пустой набор дней → по умолчанию пн–пт
    assert next_delivery_date(fri, 1, ()) == mon
    assert delivery_after(mon) == date(2026, 9, 15)


def test_horizon_and_overdue():
    thu, mon = date(2026, 9, 10), date(2026, 9, 14)
    assert horizon_days(thu, 1) == 4       # пт → следующая пн: пт, сб, вс, пн
    assert horizon_days(mon, 1) == 2       # вт → ср
    expected = date(2026, 9, 14)
    assert ORDER_OVERDUE_GRACE_DAYS == 2
    assert not is_overdue(expected, date(2026, 9, 16))
    assert is_overdue(expected, date(2026, 9, 17))
    assert not is_overdue(expected, date(2026, 9, 13))


if __name__ == '__main__':
    import inspect
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and inspect.isfunction(fn):
            try:
                fn()
                print(f'ok   {name}')
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f'FAIL {name}: {e!r}')
    sys.exit(1 if failed else 0)
