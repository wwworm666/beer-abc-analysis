"""
Тесты API заказов поставщикам /api/orders/* (routes/orders.py) — этап 1
редизайна «Заказы и остатки» (2026-09-10).

Self-runnable: `py -3 tests/test_orders_routes.py` (совместимо с pytest).

Хранилище подменяется временным OrderStore (routes.orders.get_order_store),
пользователь — атрибутом routes.orders.current_user; iiko не нужен.

Что проверяется:
- валидация позиции черновика: поставщик, конкретный бар из сети (не «Общая»),
  qty >= 0, kind из допустимых; ошибки батча указывают номер позиции;
- черновик: добавление/удаление, ответ с текстом для чата и total_qty, очистка
  по поставщику и целиком (removed);
- отправка: ожидаемая дата по календарю поставок и lead_time поставщика,
  переопределение датой, мусорная дата → 400, пустой черновик → 409;
- список: окно дней (клампится), фильтр статусов, overdue_grace_days;
- один заказ (404), «приехало» с фактом, отмена, запреты по статусам (409).
"""

import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
import routes.orders as ro  # noqa: E402
from routes.orders import orders_bp  # noqa: E402
from routes.stocks import _supplier_params  # noqa: E402
from core.order_store import OrderStore  # noqa: E402
from core.supplier_calendar import next_delivery_date, ORDER_OVERDUE_GRACE_DAYS  # noqa: E402
from extensions import BARS  # noqa: E402

USER = {'login': 'anna', 'display_name': 'Анна'}
BAR_LIG = 'Лиговский'
BAR_BOL = 'Большой пр. В.О'


@contextmanager
def _client():
    store = OrderStore(os.path.join(tempfile.mkdtemp(prefix='orders_api_'), 'orders.json'))
    saved = (ro.get_order_store, ro.current_user)
    ro.get_order_store = lambda: store
    ro.current_user = lambda: USER
    app = Flask('test_orders')
    app.register_blueprint(orders_bp)
    try:
        yield app.test_client(), store
    finally:
        ro.get_order_store, ro.current_user = saved


def _post(c, url, body=None):
    r = c.post(url, json=body if body is not None else {})
    return r.status_code, r.get_json()


def _item(pid='p1', bar=BAR_LIG, qty=3, supplier='Метро', **extra):
    d = {'supplier': supplier, 'product_id': pid, 'bar': bar, 'qty': qty,
         'name': 'Кола 0.5', 'unit': 'шт', 'kind': 'bottle', 'recommended': 4}
    d.update(extra)
    return d


# --- черновик: валидация --------------------------------------------------------

def test_draft_validation():
    with _client() as (c, _):
        cases = [
            ({'product_id': 'p1', 'bar': BAR_LIG, 'qty': 1}, 'supplier'),
            (_item(pid=''), 'product_id'),
            (_item(bar='Общая'), 'бар'),
            (_item(bar='Ливонский'), 'бар'),
            (_item(qty=-1), 'qty'),
            (_item(qty='много'), 'qty'),
            (_item(kind='snack'), 'kind'),
        ]
        for body, word in cases:
            code, d = _post(c, '/api/orders/draft', body)
            assert code == 400, (body, code, d)
            assert word in d['error'], (body, d['error'])
        # не JSON-объект → 400, а не 500
        r = c.post('/api/orders/draft', data='[]', content_type='application/json')
        assert r.status_code == 400
        code, d = _post(c, '/api/orders/draft/batch', {'items': []})
        assert code == 400
        code, d = _post(c, '/api/orders/draft/batch', {'items': [_item(), _item(bar='Общая')]})
        assert code == 400 and d['error'].startswith('позиция 1')


# --- черновик: жизненный цикл ---------------------------------------------------

def test_draft_lifecycle_and_text():
    with _client() as (c, store):
        code, d = c.get('/api/orders/draft').status_code, c.get('/api/orders/draft').get_json()
        assert code == 200 and d == {'drafts': [], 'bars': list(BARS)}

        code, d = _post(c, '/api/orders/draft', _item())
        assert code == 200, d
        assert [x['supplier'] for x in d['drafts']] == ['Метро']
        draft = d['drafts'][0]
        assert draft['total_qty'] == 3.0 and draft['updated_by'] == 'anna'
        assert draft['items'][0]['product_id'] == 'p1' and draft['items'][0]['qty'] == 3.0
        assert 'Поставщик: Метро' in draft['text'] and '- Кола 0.5 — 3 шт' in draft['text']
        assert f'{BAR_LIG}:' in draft['text']

        # батч: два поставщика, тот же товар в другой бар
        code, d = _post(c, '/api/orders/draft/batch', {'items': [
            _item(bar=BAR_BOL, qty=2), _item(pid='p2', supplier='Лента', qty=1.5, name='Сидр', unit='шт')]})
        assert code == 200, d
        assert [x['supplier'] for x in d['drafts']] == ['Лента', 'Метро']
        metro = [x for x in d['drafts'] if x['supplier'] == 'Метро'][0]
        assert [(i['bar'], i['qty']) for i in metro['items']] == [(BAR_BOL, 2.0), (BAR_LIG, 3.0)]
        assert store.draft_quantities(BAR_LIG) == {'p1': 3.0, 'p2': 1.5}

        # qty 0 удаляет позицию
        code, d = _post(c, '/api/orders/draft', _item(qty=0))
        assert code == 200
        metro = [x for x in d['drafts'] if x['supplier'] == 'Метро'][0]
        assert [i['bar'] for i in metro['items']] == [BAR_BOL]

        # очистка по поставщику и целиком
        code, d = _post(c, '/api/orders/draft/clear', {'supplier': 'Лента'})
        assert code == 200 and d['removed'] == 1 and [x['supplier'] for x in d['drafts']] == ['Метро']
        code, d = _post(c, '/api/orders/draft/clear', {})
        assert code == 200 and d['removed'] == 1 and d['drafts'] == []


# --- отправка ---------------------------------------------------------------------

def test_send_expected_date_and_errors():
    with _client() as (c, store):
        code, d = _post(c, '/api/orders/send', {})
        assert code == 400
        code, d = _post(c, '/api/orders/send', {'supplier': 'Метро'})
        assert code == 409, d                                         # черновик пуст

        _post(c, '/api/orders/draft', _item())
        code, d = _post(c, '/api/orders/send', {'supplier': 'Метро', 'expected_at': 'скоро'})
        assert code == 400 and 'expected_at' in d['error']

        code, d = _post(c, '/api/orders/send', {'supplier': 'Метро', 'note': 'к открытию'})
        assert code == 200, d
        o = d['order']
        lead = _supplier_params('Метро')['lead_time_days']
        assert o['expected_at'] == next_delivery_date(date.today(), lead).isoformat()
        assert o['status'] == 'sent' and o['sent_by'] == 'anna' and o['note'] == 'к открытию'
        assert 'Ожидаемая поставка' in o['text'] and 'Поставщик: Метро' in o['text']
        assert c.get('/api/orders/draft').get_json()['drafts'] == []

        # явная дата
        _post(c, '/api/orders/draft', _item(supplier='Лента'))
        code, d = _post(c, '/api/orders/send', {'supplier': 'Лента', 'expected_at': '2026-09-21'})
        assert code == 200 and d['order']['expected_at'] == '2026-09-21'


# --- список и один заказ ----------------------------------------------------------

def test_list_and_get():
    with _client() as (c, store):
        _post(c, '/api/orders/draft', _item())
        _, sent = _post(c, '/api/orders/send', {'supplier': 'Метро'})
        oid = sent['order']['id']

        r = c.get('/api/orders')
        d = r.get_json()
        assert r.status_code == 200
        assert d['days'] == 30 and d['overdue_grace_days'] == ORDER_OVERDUE_GRACE_DAYS
        assert [o['id'] for o in d['orders']] == [oid] and d['orders'][0]['text']

        assert c.get('/api/orders?days=9999').get_json()['days'] == ro.MAX_HISTORY_DAYS
        assert c.get('/api/orders?days=0').get_json()['days'] == 1
        assert c.get('/api/orders?days=abc').status_code == 400
        r = c.get('/api/orders?status=cancelled')
        assert r.status_code == 200 and r.get_json()['orders'] == []
        r = c.get('/api/orders?status=lost')
        assert r.status_code == 400 and 'known_statuses' in r.get_json()

        assert c.get('/api/orders/nope').status_code == 404
        r = c.get(f'/api/orders/{oid}')
        assert r.status_code == 200 and r.get_json()['order']['id'] == oid


# --- приёмка и отмена ---------------------------------------------------------------

def test_received_and_cancel():
    with _client() as (c, store):
        _post(c, '/api/orders/draft/batch', {'items': [_item(), _item(pid='p2', name='Сидр')]})
        _, sent = _post(c, '/api/orders/send', {'supplier': 'Метро'})
        oid = sent['order']['id']

        assert _post(c, '/api/orders/nope/received')[0] == 404
        assert _post(c, '/api/orders/nope/cancel')[0] == 404
        code, d = _post(c, f'/api/orders/{oid}/received', {'items': 'p1'})
        assert code == 400
        code, d = _post(c, f'/api/orders/{oid}/received', {'items': [{'product_id': 'p1', 'bar': BAR_LIG, 'qty': 'x'}]})
        assert code == 400

        code, d = _post(c, f'/api/orders/{oid}/received',
                        {'items': [{'product_id': 'p1', 'bar': BAR_LIG, 'qty': 2}], 'note': 'одной нет'})
        assert code == 200, d
        o = d['order']
        assert o['status'] == 'received' and o['received_by'] == 'anna' and o['note'] == 'одной нет'
        by_pid = {i['product_id']: i for i in o['items']}
        assert by_pid['p1']['received_qty'] == 2.0 and 'received_qty' not in by_pid['p2']
        assert store.open_quantities(BAR_LIG) == {'p1': 2.0, 'p2': 3.0}

        code, d = _post(c, f'/api/orders/{oid}/cancel', {'note': 'отменили'})
        assert code == 200 and d['order']['status'] == 'cancelled'
        assert store.open_quantities(BAR_LIG) == {}
        code, d = _post(c, f'/api/orders/{oid}/received')
        assert code == 409, d


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
