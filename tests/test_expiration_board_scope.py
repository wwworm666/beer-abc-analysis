"""
Тесты скоупа расхода в борде сроков годности /api/expiration/board
(routes/expiration.py) после перевода на общий снимок сети (2026-09-10).

Self-runnable: `py -3 tests/test_expiration_board_scope.py` (совместимо с pytest).

Моков iiko нет: снимок и номенклатура подменяются атрибутами модуля
routes.expiration (get_stock_snapshot / get_stocks_nomenclature), как в
tests/test_me_routes.py; карта штрихкодов пустая, кэш ЧЗ указывает на
несуществующий файл — сроки годности не участвуют, проверяется только расход.

Что проверяется:
- снимок None → 503 с кодом iiko_unavailable (S-08), а не борд из нулей; ошибка не кэшируется;
- S-01: avg_sales одного товара различается по барам согласно primaryStore
  записей, «чужой» расход бару не приписывается;
- updated_at равен fetched_at снимка; force=1 обходит кэш борда и сбрасывает снимок;
- окно расхода берётся из снимка (window_days), а не из константы.
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
import routes.expiration as re_  # noqa: E402
from routes.expiration import expiration_bp  # noqa: E402

STORE_BOL = re_._STORE_ID_MAP['bar1']   # Большой пр. В.О
STORE_LIG = re_._STORE_ID_MAP['bar2']   # Лиговский
STORE_KRE = re_._STORE_ID_MAP['bar3']   # Кременчугская

BAR_BOL = 'Большой пр. В.О'
BAR_LIG = 'Лиговский'

# Окно снимка: 06.10.2025 .. 05.11.2025, делитель 30 дней.
TODAY = '2025-11-05'
FETCHED_AT = '2025-11-05T10:00:00'
WINDOW = 30

NO_CHZ_FILE = Path(os.path.dirname(os.path.abspath(__file__))) / 'no_such_dir' / 'chz_stock.json'

P_BOTTLE = 'p-bottle'      # фасовка на двух складах, расход на обоих (S-01)
P_NEW = 'p-new-bottle'     # новинка: первый приход 26.10, расход после
P_SAUCE = 'p-sauce'        # кухня — в борд сроков не входит

_DEFAULT = object()


def _nomenclature():
    return {
        P_BOTTLE: {'name': 'Пиво Светлое 0.5', 'category': 'ООО "Май"',
                   'parentId': 'Напитки Фасовка', 'type': 'GOODS', 'mainUnit': 'шт'},
        P_NEW: {'name': 'Лимонад Новый 0.5', 'category': 'Лента',
                'parentId': 'Напитки Фасовка', 'type': 'GOODS', 'mainUnit': 'шт'},
        P_SAUCE: {'name': 'Соус Барбекю', 'category': 'ИП Ромашка',
                  'parentId': 'ЕДА', 'type': 'GOODS', 'mainUnit': 'кг'},
    }


def _bal(store, product, amount, cost):
    return {'store': store, 'product': product, 'amount': amount, 'sum': cost}


def _op(product, store, amount, op_date, doc_type='SALES_DOCUMENT', incoming='false'):
    return {'product': product, 'primaryStore': store, 'amount': amount,
            'incoming': incoming, 'documentType': doc_type, 'date': op_date}


def _snapshot():
    return {
        'balances': [
            _bal(STORE_LIG, P_BOTTLE, 4.0, 400.0),
            _bal(STORE_BOL, P_BOTTLE, 9.0, 900.0),
            _bal(STORE_LIG, P_NEW, 13.0, 650.0),
            _bal(STORE_LIG, P_SAUCE, 2.5, 250.0),
        ],
        'operations': [
            # Лиговский: 45; Большой: 60 + перемещение 30 = 90; приход на
            # Кременчугскую расходом не является и остатка там нет.
            _op(P_BOTTLE, STORE_LIG, '20.000000000', '06.10.2025', 'INCOMING_INVOICE', 'true'),
            _op(P_BOTTLE, STORE_LIG, '-30.000000000', '10.10.2025'),
            _op(P_BOTTLE, STORE_LIG, '-15.000000000', '20.10.2025'),
            _op(P_BOTTLE, STORE_BOL, '-60.000000000', '15.10.2025'),
            _op(P_BOTTLE, STORE_BOL, '-30.000000000', '18.10.2025', 'INTERNAL_TRANSFER'),
            _op(P_BOTTLE, STORE_KRE, '30.000000000', '18.10.2025', 'INTERNAL_TRANSFER', 'true'),
            _op(P_NEW, STORE_LIG, '24.000000000', '26.10.2025', 'INCOMING_INVOICE', 'true'),
            _op(P_NEW, STORE_LIG, '-5.000000000', '28.10.2025'),
            _op(P_NEW, STORE_LIG, '-6.000000000', '02.11.2025'),
            _op(P_SAUCE, STORE_LIG, '-1.500000000', '15.10.2025', 'WRITEOFF_DOCUMENT'),
        ],
        'today': TODAY,
        'date_from': '06.10.2025',
        'date_to': '05.11.2025',
        'window_days': WINDOW,
        'fetched_at': FETCHED_AT,
    }


def _make_app():
    app = Flask('test_expiration')
    app.register_blueprint(expiration_bp)
    return app


@contextmanager
def _patched(snapshot=_DEFAULT, nomenclature=_DEFAULT):
    saved = {name: getattr(re_, name) for name in
             ('get_stock_snapshot', 'get_stocks_nomenclature', 'get_barcode_map', '_CHZ_CACHE_FILE')}
    saved_cache = dict(re_._BOARD_CACHE)
    snap = _snapshot() if snapshot is _DEFAULT else snapshot
    nom = _nomenclature() if nomenclature is _DEFAULT else nomenclature
    re_.get_stock_snapshot = lambda *a, **k: snap
    re_.get_stocks_nomenclature = lambda *a, **k: nom
    re_.get_barcode_map = lambda *a, **k: {}
    re_._CHZ_CACHE_FILE = NO_CHZ_FILE
    re_._BOARD_CACHE.clear()
    try:
        yield _make_app().test_client()
    finally:
        for name, value in saved.items():
            setattr(re_, name, value)
        re_._BOARD_CACHE.clear()
        re_._BOARD_CACHE.update(saved_cache)


def _board(client, bars='all', force=1):
    r = client.get(f'/api/expiration/board?bars={bars}&force={force}')
    return r.status_code, r.get_json()


def _index(payload):
    return {(it['bar'], it['product_id']): it for it in payload['items']}


def test_snapshot_none_503():
    with _patched(snapshot=None) as c:
        code, d = _board(c)
        assert code == 503, (code, d)
        assert d['code'] == 'iiko_unavailable'
        assert d['error']


def test_nomenclature_none_503():
    with _patched(nomenclature=None) as c:
        code, d = _board(c)
        assert code == 503, (code, d)
        assert d['code'] == 'nomenclature_unavailable'


def test_error_is_not_cached_and_force_reaches_snapshot():
    """503 не попадает в кэш борда; без force второй ответ идёт из кэша с тем же updated_at;
    force=1 передаётся в get_stock_snapshot."""
    with _patched(snapshot=None) as c:
        code, _ = _board(c, force=0)
        assert code == 503
        assert re_._BOARD_CACHE == {}
    calls = []
    snap = _snapshot()

    def fake_snapshot(*a, **k):
        calls.append(k.get('force'))
        return snap

    with _patched() as c:
        re_.get_stock_snapshot = fake_snapshot
        code, d1 = _board(c, force=0)
        assert code == 200 and d1['cache']['hit'] is False
        assert calls == [False]
        code, d2 = _board(c, force=0)
        assert code == 200 and d2['cache']['hit'] is True
        assert d2['updated_at'] == FETCHED_AT and len(d2['items']) == len(d1['items'])
        assert calls == [False]                      # кэш борда — снимок не запрашивался
        code, d3 = _board(c, force=1)
        assert code == 200 and d3['cache']['hit'] is False
        assert calls == [False, True]                # force дошёл до снимка


def test_window_days_from_snapshot():
    """Знаменатель расхода — окно снимка, а не константа модуля."""
    snap = _snapshot()
    snap['window_days'] = 10
    with _patched(snapshot=snap) as c:
        code, d = _board(c)
        assert code == 200, d
        idx = _index(d)
        assert idx[(BAR_LIG, P_BOTTLE)]['avg_sales'] == 4.5      # 45 / 10
        # Первый приход 26.10 = today − 10 → граница окна, не новинка: 11 / 10.
        assert idx[(BAR_LIG, P_NEW)]['avg_sales'] == 1.1


def test_invalid_bars_400():
    with _patched() as c:
        code, d = _board(c, 'nope')
        assert code == 400, (code, d)
        assert 'error' in d


def test_avg_sales_per_bar_by_primary_store():
    """S-01: расход одного товара по барам разный, «чужой» склад не подмешивается."""
    with _patched() as c:
        code, d = _board(c)
        assert code == 200, d
        idx = _index(d)
        lig = idx[(BAR_LIG, P_BOTTLE)]
        bol = idx[(BAR_BOL, P_BOTTLE)]
        assert lig['stock'] == 4.0 and lig['avg_sales'] == 1.5     # 45 / 30
        assert bol['stock'] == 9.0 and bol['avg_sales'] == 3.0     # 90 / 30
        assert lig['avg_sales'] != bol['avg_sales']
        # Себестоимость единицы = sum / stock.
        assert lig['price'] == 100.0 and bol['price'] == 100.0
        # Без остатка на складе позиции нет, хотя операция по складу была.
        assert ('Кременчугская', P_BOTTLE) not in idx
        assert ('Варшавская', P_BOTTLE) not in idx
        # Кухня в борд сроков не входит.
        assert not any(pid == P_SAUCE for _, pid in idx)
        # Новинка: делитель — 11 дней с первого прихода, (5 + 6) / 11.
        assert idx[(BAR_LIG, P_NEW)]['avg_sales'] == 1.0
        # Без ЧЗ — tier unknown, но позиция на месте.
        assert lig['has_chz_data'] is False and lig['tier'] == 'unknown'


def test_bars_filter_limits_scope():
    with _patched() as c:
        code, d = _board(c, 'bar2')
        assert code == 200, d
        assert d['bars'] == [BAR_LIG]
        assert {it['bar'] for it in d['items']} == {BAR_LIG}
        assert _index(d)[(BAR_LIG, P_BOTTLE)]['avg_sales'] == 1.5


def test_updated_at_is_snapshot_fetched_at():
    with _patched() as c:
        code, d = _board(c)
        assert code == 200, d
        assert d['updated_at'] == FETCHED_AT
        assert d['chz_updated_at'] is None
        assert d['cache'] == {'hit': False, 'age_sec': 0}
        assert d['bars'] == [BAR_BOL, BAR_LIG, 'Кременчугская', 'Варшавская']
        assert set(d['kpi']) == {'risk_rub', 'critical_count', 'surplus_units'}
        assert d['tier_counts']['unknown'] == len(d['items']) == 3


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:
            failed += 1
            import traceback
            print(f'FAIL {t.__name__}: {e}')
            traceback.print_exc()
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(_run())
