"""
Тесты эндпоинтов остатков /api/stocks/* (routes/stocks.py) после этапа 0
редизайна страницы «Заказы и остатки» (2026-09-10).

Self-runnable: `py -3 tests/test_stocks_routes.py` (совместимо с pytest).

Моков iiko нет: снимок сети и номенклатура подменяются атрибутами модуля
routes.stocks (get_stock_snapshot / get_stocks_nomenclature) на маленькие
синтетические данные — тот же приём, что в tests/test_me_routes.py. Краны
(taps_manager.get_bar_taps), карта штрихкодов и путь к кэшу ЧЗ тоже
подменяются, чтобы ответ не зависел от файлов на диске.

Что проверяется (нумерация — docs/technical/audits/STOCKS_AUDIT_2026-09-10.md):
- валидация ?bar=: нет параметра / неизвестный бар → 400 с known_bars;
- сбой iiko → явный 503 с кодом, а не пустой список (S-08);
- расход считается по складу выбранного бара через primaryStore записи
  (S-01), для «Общая» — по всей сети; перемещения из бара входят в расход;
- кухня = верхняя группа «ЕДА», а не белый список поставщиков и не единица
  измерения (S-18, S-28); единица — из mainUnit;
- позиция с остатком без операций в окне остаётся в списке (avg 0, «Высокий»);
- новинка: знаменатель периода = дни с первого прихода;
- фасовка по имени верхней группы (стиль XML) и по GUID группы;
- форма ответа order-board (прежние ключи + days_in_period/is_new/
  consumption_by_type) и таплиста.
"""

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
import routes.stocks as rs  # noqa: E402
from core.order_store import OrderStore  # noqa: E402
from extensions import BARS  # noqa: E402
from routes.stocks import stocks_bp  # noqa: E402

ENDPOINTS = ('order-board', 'kitchen', 'bottles', 'expiry', 'taplist')

# Склады — из карты модуля, чтобы тест не расходился с реализацией.
STORE_BOL = rs._STORE_ID_MAP['bar1']   # Большой пр. В.О
STORE_LIG = rs._STORE_ID_MAP['bar2']   # Лиговский
STORE_KRE = rs._STORE_ID_MAP['bar3']   # Кременчугская

BAR_BOL = 'Большой пр. В.О'
BAR_LIG = 'Лиговский'
BAR_KRE = 'Кременчугская'
BAR_ALL = 'Общая'

# Окно снимка: 06.10.2025 .. 05.11.2025, делитель 30 дней.
TODAY = '2025-11-05'
FETCHED_AT = '2025-11-05T10:00:00'
WINDOW = 30

# Заведомо несуществующий путь: кэша ЧЗ нет — сроки годности пустые, без ошибки.
NO_CHZ_FILE = Path(os.path.dirname(os.path.abspath(__file__))) / 'no_such_dir' / 'chz_stock.json'

P_BOTTLE = 'p-bottle'          # фасовка на двух складах, расход на обоих (S-01)
P_METRO = 'p-metro-bottle'     # поставщик «Метро», группа «Напитки Фасовка» — НЕ кухня
P_SAUCE = 'p-sauce'            # группа «ЕДА», поставщик не из старого белого списка, кг
P_OIL = 'p-oil'                # масло в литрах, группа «ЕДА» — кухня, не кега
P_KEG_LAGER = 'p-keg-lager'    # кега на кране Лиговского
P_KEG_STOUT = 'p-keg-stout'    # кега на Кременчугской, кранов у бара нет
P_IDLE = 'p-idle-bottle'       # остаток есть, операций в окне нет
P_NEW = 'p-new-bottle'         # новинка: первый приход 26.10, расход после
P_GUID = 'p-guid-bottle'       # фасовка с parentId = GUID группы (старая номенклатура)
P_DISH = 'p-dish'              # блюдо — остатков не имеет, пропускается
P_UNKNOWN = 'p-unknown'        # остаток есть, товара нет в номенклатуре — пропускается
P_NEG = 'p-neg-bottle'         # отрицательный остаток фасовки на Лиговском — critical
P_KEG_NEG = 'p-keg-neg'        # кега с отрицательным остатком на Кременчугской, не на кране
P_MOD = 'p-modifier'           # модификатор «порц» под «ЕДА» — остатков не имеет, пропускается
P_CAN = 'p-can-draft'          # банка в штуках под «Напитки Розлив» — не кега, пропускается

_DEFAULT = object()


def _nomenclature():
    return {
        P_BOTTLE: {'name': 'Пиво Светлое 0.5', 'category': 'ООО "Май"',
                   'parentId': 'Напитки Фасовка', 'type': 'GOODS', 'mainUnit': 'шт'},
        P_METRO: {'name': 'Кола 0.5', 'category': 'Метро',
                  'parentId': 'Напитки Фасовка', 'type': 'GOODS', 'mainUnit': 'шт'},
        P_SAUCE: {'name': 'Соус Барбекю', 'category': 'ИП Ромашка',
                  'parentId': 'ЕДА', 'type': 'GOODS', 'mainUnit': 'кг'},
        P_OIL: {'name': 'Масло подсолнечное', 'category': 'Метро',
                'parentId': 'ЕДА', 'type': 'GOODS', 'mainUnit': 'л'},
        P_KEG_LAGER: {'name': 'Кег Лагер Домашний, 30 л', 'category': 'ООО "Арбореал"',
                      'parentId': 'Напитки Розлив', 'type': 'GOODS', 'mainUnit': 'л'},
        P_KEG_STOUT: {'name': 'Кег Стаут Тёмный, 30 л', 'category': 'ООО "Арбореал"',
                      'parentId': 'Напитки Розлив', 'type': 'GOODS', 'mainUnit': 'л'},
        P_IDLE: {'name': 'Сидр Яблочный 0.33', 'category': 'Лента',
                 'parentId': 'Напитки Фасовка', 'type': 'GOODS', 'mainUnit': 'шт'},
        P_NEW: {'name': 'Лимонад Новый 0.5', 'category': 'Лента',
                'parentId': 'Напитки Фасовка', 'type': 'GOODS', 'mainUnit': 'шт'},
        P_GUID: {'name': 'Квас 1.0', 'category': 'Лента',
                 'parentId': rs.FASOVKA_GROUP_ID, 'type': 'GOODS', 'mainUnit': 'шт'},
        P_DISH: {'name': 'Бургер', 'category': 'Кухня',
                 'parentId': 'ЕДА', 'type': 'DISH', 'mainUnit': 'порц'},
        P_NEG: {'name': 'Тоник 0.2', 'category': 'Лента',
                'parentId': 'Напитки Фасовка', 'type': 'GOODS', 'mainUnit': 'шт'},
        P_KEG_NEG: {'name': 'Кег Портер Ночной, 30 л', 'category': 'ООО "Арбореал"',
                    'parentId': 'Напитки Розлив', 'type': 'GOODS', 'mainUnit': 'л'},
        P_MOD: {'name': 'Соус чесночный', 'category': None,
                'parentId': 'ЕДА', 'type': 'MODIFIER', 'mainUnit': 'порц'},
        P_CAN: {'name': 'Радлер б/а 0.45 ж/б', 'category': 'ООО "Арбореал"',
                'parentId': 'Напитки Розлив', 'type': 'GOODS', 'mainUnit': 'шт'},
    }


def _bal(store, product, amount, cost=0.0):
    """Запись balance/stores: остаток и его стоимость по складу."""
    return {'store': store, 'product': product, 'amount': amount, 'sum': cost}


def _balances():
    return [
        _bal(STORE_LIG, P_BOTTLE, 4.0, 400.0),
        _bal(STORE_BOL, P_BOTTLE, 9.0, 900.0),
        _bal(STORE_LIG, P_METRO, 30.0, 1500.0),
        _bal(STORE_LIG, P_SAUCE, 2.5, 250.0),
        _bal(STORE_LIG, P_OIL, 3.0, 300.0),
        _bal(STORE_KRE, P_OIL, 5.0, 500.0),
        _bal(STORE_LIG, P_KEG_LAGER, 18.0, 3600.0),
        _bal(STORE_KRE, P_KEG_STOUT, 30.0, 6000.0),
        _bal(STORE_LIG, P_IDLE, 6.0, 300.0),
        _bal(STORE_LIG, P_NEW, 13.0, 650.0),
        _bal(STORE_LIG, P_GUID, 7.0, 350.0),
        _bal(STORE_LIG, P_DISH, 1.0, 0.0),
        _bal(STORE_LIG, P_UNKNOWN, 5.0, 0.0),
        _bal(STORE_LIG, P_NEG, -1.0, 0.0),
        _bal(STORE_KRE, P_KEG_NEG, -3.0, 0.0),
        _bal(STORE_LIG, P_MOD, 2.0, 0.0),
        _bal(STORE_LIG, P_CAN, 12.0, 0.0),
    ]


def _op(product, store, amount, op_date, doc_type='SALES_DOCUMENT', incoming='false'):
    """Запись storeOperations в виде iiko: amount строкой со знаком, incoming строкой."""
    return {'product': product, 'primaryStore': store, 'amount': amount,
            'incoming': incoming, 'documentType': doc_type, 'date': op_date}


def _operations():
    return [
        # P_BOTTLE: приход в первый день окна (не новинка), продажи на Лиговском 45,
        # на Большом 60 + перемещение с Большого 30 (входит в расход Большого),
        # приход перемещения на Кременчугскую — не расход.
        _op(P_BOTTLE, STORE_LIG, '20.000000000', '06.10.2025', 'INCOMING_INVOICE', 'true'),
        _op(P_BOTTLE, STORE_LIG, '-30.000000000', '10.10.2025'),
        _op(P_BOTTLE, STORE_LIG, '-15.000000000', '20.10.2025'),
        _op(P_BOTTLE, STORE_BOL, '-60.000000000', '15.10.2025'),
        _op(P_BOTTLE, STORE_BOL, '-30.000000000', '18.10.2025', 'INTERNAL_TRANSFER'),
        _op(P_BOTTLE, STORE_KRE, '30.000000000', '18.10.2025', 'INTERNAL_TRANSFER', 'true'),
        _op(P_METRO, STORE_LIG, '-10.000000000', '12.10.2025'),
        _op(P_SAUCE, STORE_LIG, '-1.500000000', '15.10.2025', 'WRITEOFF_DOCUMENT'),
        _op(P_OIL, STORE_LIG, '-1.000000000', '15.10.2025', 'WRITEOFF_DOCUMENT'),
        _op(P_KEG_LAGER, STORE_LIG, '-12.000000000', '20.10.2025'),
        # P_NEW: первый приход 26.10 внутри окна, расход только после него →
        # новинка, делитель = (05.11 − 26.10) + 1 = 11 дней.
        _op(P_NEW, STORE_LIG, '24.000000000', '26.10.2025', 'INCOMING_INVOICE', 'true'),
        _op(P_NEW, STORE_LIG, '-5.000000000', '28.10.2025'),
        _op(P_NEW, STORE_LIG, '-6.000000000', '02.11.2025'),
        _op(P_GUID, STORE_LIG, '-3.000000000', '01.11.2025'),
    ]


def _snapshot(balances=None, operations=None):
    return {
        'balances': _balances() if balances is None else balances,
        'operations': _operations() if operations is None else operations,
        'today': TODAY,
        'date_from': '06.10.2025',
        'date_to': '05.11.2025',
        'window_days': WINDOW,
        'fetched_at': FETCHED_AT,
    }


# Краны: только у Лиговского (bar2). Кран 2 активен, но остатка по кеге нет.
_TAPS = {
    'bar2': [
        {'tap_number': 1, 'status': 'active', 'current_beer': 'Лагер Домашний'},
        {'tap_number': 2, 'status': 'active', 'current_beer': 'ИПА Хмельной'},
        {'tap_number': 3, 'status': 'empty', 'current_beer': None},
    ],
}


def _fake_bar_taps(bar_id):
    return {'bar_id': bar_id, 'taps': [dict(t) for t in _TAPS.get(bar_id, [])]}


def _make_app():
    app = Flask('test_stocks')
    app.register_blueprint(stocks_bp)
    return app


def _temp_order_store():
    return OrderStore(os.path.join(tempfile.mkdtemp(prefix='stocks_orders_'), 'orders.json'))


@contextmanager
def _patched(snapshot=_DEFAULT, nomenclature=_DEFAULT, order_store=_DEFAULT):
    """Подменить источники данных routes.stocks; отдаёт тестовый клиент.

    Хранилище заказов — временное (пустое), чтобы доска не зависела от
    data/orders.json; order_store=callable подменяет фабрику целиком.
    """
    saved = {name: getattr(rs, name) for name in
             ('get_stock_snapshot', 'get_stocks_nomenclature', 'get_barcode_map', '_CHZ_CACHE_FILE',
              'get_order_store')}
    snap = _snapshot() if snapshot is _DEFAULT else snapshot
    nom = _nomenclature() if nomenclature is _DEFAULT else nomenclature
    store = _temp_order_store() if order_store is _DEFAULT else order_store
    rs.get_stock_snapshot = lambda *a, **k: snap
    rs.get_stocks_nomenclature = lambda *a, **k: nom
    rs.get_barcode_map = lambda *a, **k: {}
    rs._CHZ_CACHE_FILE = NO_CHZ_FILE
    rs.get_order_store = store if callable(store) else (lambda: store)
    # Атрибут экземпляра перекрывает метод класса; снимается в finally.
    rs.taps_manager.get_bar_taps = _fake_bar_taps
    try:
        yield _make_app().test_client()
    finally:
        for name, value in saved.items():
            setattr(rs, name, value)
        rs.taps_manager.__dict__.pop('get_bar_taps', None)


def _get(client, endpoint, bar=None):
    url = f'/api/stocks/{endpoint}'
    if bar is not None:
        url += f'?bar={bar}'
    r = client.get(url)
    return r.status_code, r.get_json()


def _by_id(payload):
    return {it['product_id']: it for it in payload['items']}


# --- валидация ?bar= -----------------------------------------------------------

def test_bar_required_400():
    with _patched() as c:
        for ep in ENDPOINTS:
            code, d = _get(c, ep)
            assert code == 400, (ep, code, d)
            assert d and 'error' in d, (ep, d)


def test_unknown_bar_400_with_known_bars():
    with _patched() as c:
        for ep in ENDPOINTS:
            code, d = _get(c, ep, 'Ливонский')
            assert code == 400, (ep, code, d)
            assert d['known_bars'] == list(BARS) + [BAR_ALL], (ep, d)
            assert 'Ливонский' in d['error']


# --- сбой iiko: явный 503, а не пустой список (S-08) ---------------------------

def test_snapshot_none_503():
    with _patched(snapshot=None) as c:
        for ep in ENDPOINTS:
            for bar in (BAR_LIG, BAR_ALL):
                code, d = _get(c, ep, bar)
                assert code == 503, (ep, bar, code, d)
                assert d['code'] == 'iiko_unavailable', (ep, bar, d)
                assert d['error']


def test_empty_balances_503():
    with _patched(snapshot=_snapshot(balances=[])) as c:
        for ep in ENDPOINTS:
            code, d = _get(c, ep, BAR_LIG)
            assert code == 503, (ep, code, d)
            assert d['code'] == 'empty_balances', (ep, d)


def test_nomenclature_none_503():
    with _patched(nomenclature=None) as c:
        for ep in ENDPOINTS:
            code, d = _get(c, ep, BAR_LIG)
            assert code == 503, (ep, code, d)
            assert d['code'] == 'nomenclature_unavailable', (ep, d)


# --- S-01: расход по складу выбранного бара, «Общая» — сеть -------------------

def test_consumption_scope_store_vs_network():
    """Один товар на двух складах: Лиговский видит только свой primaryStore.

    Лиговский: 30 + 15 = 45 / 30 дн = 1.5;  Большой: 60 + 30 (перемещение) = 90 / 30 = 3.0;
    Общая: перемещения внутри сети не считаются вовсе → 105 / 30 = 3.5.
    Приход перемещения на Кременчугскую расходом не считается.
    """
    with _patched() as c:
        code, lig = _get(c, 'order-board', BAR_LIG)
        assert code == 200, lig
        assert lig['consumption_scope'] == 'store'
        it = _by_id(lig)[P_BOTTLE]
        assert it['stock'] == 4.0
        assert it['avg_sales'] == 1.5
        assert it['consumption_by_type'] == {'SALES_DOCUMENT': 45.0}

        code, bol = _get(c, 'order-board', BAR_BOL)
        assert code == 200, bol
        it = _by_id(bol)[P_BOTTLE]
        assert it['stock'] == 9.0
        assert it['avg_sales'] == 3.0
        assert it['consumption_by_type'] == {'SALES_DOCUMENT': 60.0, 'INTERNAL_TRANSFER': 30.0}

        code, net = _get(c, 'order-board', BAR_ALL)
        assert code == 200, net
        assert net['consumption_scope'] == 'network'
        it = _by_id(net)[P_BOTTLE]
        assert it['stock'] == 13.0
        assert it['avg_sales'] == 3.5
        assert it['consumption_by_type'] == {'SALES_DOCUMENT': 105.0}

        # Тот же скоуп во вкладках: бутылки и сроки годности.
        for ep in ('bottles', 'expiry'):
            _, d_lig = _get(c, ep, BAR_LIG)
            _, d_net = _get(c, ep, BAR_ALL)
            assert d_lig['consumption_scope'] == 'store'
            assert d_net['consumption_scope'] == 'network'
            assert _by_id(d_lig)[P_BOTTLE]['avg_sales'] == 1.5, ep
            assert _by_id(d_net)[P_BOTTLE]['avg_sales'] == 3.5, ep

        # На Кременчугской остатка нет — позиции нет, хотя операция по складу была.
        _, kre = _get(c, 'bottles', BAR_KRE)
        assert P_BOTTLE not in _by_id(kre)


# --- кухня = верхняя группа «ЕДА» (S-18, S-28) ----------------------------------

def test_kitchen_by_top_group_not_supplier():
    with _patched() as c:
        code, kitchen = _get(c, 'kitchen', BAR_LIG)
        assert code == 200, kitchen
        by = _by_id(kitchen)
        assert set(by) == {P_SAUCE, P_OIL}, sorted(by)
        assert by[P_SAUCE]['unit'] == 'кг'          # из mainUnit
        assert by[P_SAUCE]['category'] == 'ИП Ромашка'
        assert by[P_SAUCE]['avg_sales'] == 0.05      # 1.5 / 30
        assert by[P_OIL]['unit'] == 'л'
        assert P_METRO not in by                     # «Метро» + «Напитки Фасовка» — не кухня

        _, board = _get(c, 'order-board', BAR_LIG)
        types = {pid: it['type'] for pid, it in _by_id(board).items()}
        assert types[P_SAUCE] == 'kitchen'
        assert types[P_OIL] == 'kitchen'             # литры не делают масло кегой
        assert types[P_METRO] == 'bottle'
        assert types[P_KEG_LAGER] == 'draft'
        assert P_DISH not in types
        assert P_UNKNOWN not in types
        assert P_MOD not in types                    # модификатор под «ЕДА» — не кухня
        assert P_CAN not in types                    # банка в штуках под «Розлив» — не кега
        assert P_MOD not in by
        assert _by_id(board)[P_SAUCE]['unit'] == 'кг'


# --- позиция без операций в окне не исчезает ----------------------------------

def test_idle_item_stays_with_zero_consumption():
    with _patched() as c:
        for ep in ('bottles', 'expiry', 'order-board'):
            _, d = _get(c, ep, BAR_LIG)
            it = _by_id(d).get(P_IDLE)
            assert it is not None, (ep, sorted(_by_id(d)))
            assert it['stock'] == 6.0
            assert it['avg_sales'] == 0
            assert it['days_in_period'] == WINDOW
            assert it['is_new'] is False
            if ep == 'order-board':
                assert it['velocity'] == 'dead'
                assert it['urgency'] == 'low'
                assert it['recommended'] == 0
                assert it['days_left'] is None
            else:
                assert it['stock_level'] == 'high'


# --- новинка: делитель — дни с первого прихода -------------------------------

def test_new_item_days_in_period():
    with _patched() as c:
        for ep in ('bottles', 'expiry', 'order-board'):
            _, d = _get(c, ep, BAR_LIG)
            by = _by_id(d)
            new = by[P_NEW]
            assert new['is_new'] is True, ep
            assert new['days_in_period'] == 11, ep
            assert new['days_in_period'] < WINDOW
            assert new['avg_sales'] == 1.0, ep       # (5 + 6) / 11
            old = by[P_BOTTLE]                       # приход в первый день окна — не новинка
            assert old['is_new'] is False
            assert old['days_in_period'] == WINDOW


# --- фасовка по имени группы (XML) и по GUID -----------------------------------

def test_fasovka_by_parent_name_and_guid():
    with _patched() as c:
        for ep in ('bottles', 'expiry'):
            code, d = _get(c, ep, BAR_LIG)
            assert code == 200, d
            by = _by_id(d)
            assert set(by) == {P_BOTTLE, P_METRO, P_IDLE, P_NEW, P_GUID, P_NEG}, (ep, sorted(by))
            assert by[P_METRO]['category'] == 'Метро'
        _, kitchen = _get(c, 'kitchen', BAR_LIG)
        assert not ({P_METRO, P_GUID} & set(_by_id(kitchen)))

        _, expiry = _get(c, 'expiry', BAR_LIG)
        it = _by_id(expiry)[P_METRO]
        assert it['has_chz_data'] is False
        assert it['gtins'] == [] and it['expiration_dates'] == []
        assert it['nearest_expiry'] is None and it['days_to_expiry'] is None
        assert expiry['chz_updated_at'] is None
        assert expiry['matched_items'] == 0
        assert expiry['near_expiry_count'] == 0


# --- форма ответов ---------------------------------------------------------------

ORDER_BOARD_KEYS = {
    'bar', 'updated_at', 'chz_updated_at', 'consumption_scope', 'window_days',
    'safety_days', 'near_expiry_block_days', 'slow_mover_weekly_sales',
    'fast_mover_weekly_sales', 'total_items', 'critical_count', 'high_count',
    'medium_count', 'active_count', 'slow_count', 'dead_count',
    'recommended_total', 'on_order_count', 'draft_count', 'items',
}
ORDER_ITEM_KEYS = {
    'product_id', 'type', 'name', 'supplier', 'unit', 'stock', 'avg_sales',
    'weekly_sales', 'days_in_period', 'is_new', 'consumption_by_type', 'velocity',
    'days_left', 'lead_time_days', 'pack_size', 'recommended', 'urgency',
    'nearest_expiry', 'days_to_expiry',
    'on_order', 'effective_stock', 'open_orders', 'draft_qty',   # этап 1: заказы поставщикам
}


def test_order_board_shape_and_totals():
    with _patched() as c:
        code, d = _get(c, 'order-board', BAR_LIG)
        assert code == 200, d
        assert ORDER_BOARD_KEYS <= set(d), ORDER_BOARD_KEYS - set(d)
        assert d['bar'] == BAR_LIG
        assert d['updated_at'] == FETCHED_AT
        assert d['chz_updated_at'] is None
        assert d['window_days'] == WINDOW
        assert d['safety_days'] == rs.SAFETY_DAYS
        assert d['near_expiry_block_days'] == rs.NEAR_EXPIRY_BLOCK_DAYS
        assert d['slow_mover_weekly_sales'] == rs.SLOW_MOVER_WEEKLY_SALES
        assert d['fast_mover_weekly_sales'] == rs.FAST_MOVER_WEEKLY_SALES

        items = d['items']
        assert d['total_items'] == len(items) == 9
        for it in items:
            assert ORDER_ITEM_KEYS <= set(it), ORDER_ITEM_KEYS - set(it)
            assert isinstance(it['consumption_by_type'], dict)
        assert d['recommended_total'] == sum(it['recommended'] for it in items)
        assert d['critical_count'] == sum(1 for it in items if it['urgency'] == 'critical') == 1
        assert d['high_count'] == 0
        assert d['medium_count'] == 1
        assert d['active_count'] == 4     # fast: P_BOTTLE, P_NEW; regular: P_METRO, P_KEG_LAGER
        assert d['slow_count'] == 3       # P_SAUCE, P_OIL, P_GUID
        assert d['dead_count'] == 2       # P_IDLE, P_NEG

        # Отрицательный остаток — critical раньше любой скорости, рекомендация 0, первая строка.
        neg = _by_id(d)[P_NEG]
        assert neg['stock'] == -1.0 and neg['urgency'] == 'critical'
        assert neg['velocity'] == 'dead' and neg['recommended'] == 0
        assert items[0]['product_id'] == P_NEG

        # Расчёт для P_BOTTLE (ООО "Май": lead 2, pack 1):
        # target = 1.5 × (2 + 3) = 7.5; deficit = 7.5 − 4 = 3.5 → ceil → 4;
        # days_left = 4 / 1.5 = 2.67 — меньше lead + safety → medium.
        it = _by_id(d)[P_BOTTLE]
        assert it['velocity'] == 'fast'
        assert it['weekly_sales'] == 10.5
        assert it['lead_time_days'] == 2 and it['pack_size'] == 1
        assert it['recommended'] == 4
        assert it['urgency'] == 'medium'
        assert it['days_left'] == 2.7
        assert items[1]['product_id'] == P_BOTTLE     # сортировка: срочность, потом days_left
        assert d['recommended_total'] == 4


def test_negative_stock_in_tabs():
    """Отрицательный остаток без расхода: уровень 'high' — известный пробел S-19."""
    with _patched() as c:
        _, d = _get(c, 'bottles', BAR_LIG)
        it = _by_id(d)[P_NEG]
        assert it['stock'] == -1.0 and it['avg_sales'] == 0
        assert it['stock_level'] == 'high'


def test_stock_tabs_shape():
    with _patched() as c:
        for ep in ('kitchen', 'bottles', 'expiry'):
            code, d = _get(c, ep, BAR_LIG)
            assert code == 200, (ep, d)
            assert d['bar'] == BAR_LIG
            assert d['updated_at'] == FETCHED_AT, ep
            assert d['consumption_scope'] == 'store'
            assert d['window_days'] == WINDOW
            assert d['total_items'] == len(d['items'])
            assert d['low_stock_count'] == sum(1 for it in d['items'] if it['stock_level'] == 'low')
            for it in d['items']:
                for key in ('product_id', 'name', 'category', 'unit', 'stock',
                            'avg_sales', 'days_in_period', 'is_new', 'stock_level'):
                    assert key in it, (ep, key)


# --- таплист ---------------------------------------------------------------------

def test_taplist_bar_with_active_taps():
    with _patched() as c:
        code, d = _get(c, 'taplist', BAR_LIG)
        assert code == 200, d
        assert d['updated_at'] == FETCHED_AT
        assert d['active_taps_count'] == 2
        by = {t['beer_name']: t for t in d['taps']}
        assert set(by) == {'Лагер Домашний', 'ИПА Хмельной'}, sorted(by)

        lager = by['Лагер Домашний']
        assert lager['remaining_liters'] == 18.0
        assert lager['on_tap'] is True
        assert lager['stock_level'] == 'medium'      # 10 <= 18 < 25
        assert lager['tap_numbers'] == '1' and lager['taps_count'] == 1

        # Активный кран без остатка в iiko: ноль литров, но на кране.
        ipa = by['ИПА Хмельной']
        assert ipa['remaining_liters'] == 0
        assert ipa['on_tap'] is True
        assert ipa['stock_level'] == 'low'
        assert ipa['tap_numbers'] == '2'

        assert d['taps'][0]['beer_name'] == 'ИПА Хмельной'   # сортировка по остатку
        assert d['total_items'] == 2
        assert d['total_liters'] == 18.0
        assert d['low_stock_count'] == 1
        assert d['negative_stock_count'] == 0


def test_taplist_without_taps_only_goods_liters_excluding_kitchen():
    """Кранов нет — показываем все кеги склада, но не кухонное масло в литрах."""
    with _patched() as c:
        code, d = _get(c, 'taplist', BAR_KRE)
        assert code == 200, d
        assert d['active_taps_count'] == 0
        by = {t['beer_name']: t for t in d['taps']}
        assert set(by) == {'Стаут Тёмный', 'Портер Ночной'}, sorted(by)
        assert 'Масло подсолнечное' not in by
        assert 'Радлер б/а 0.45 ж/б' not in by         # штуки под «Розлив» — не кега
        stout = by['Стаут Тёмный']
        assert stout['remaining_liters'] == 30.0
        assert stout['on_tap'] is False
        assert stout['stock_level'] == 'high'
        assert stout['tap_numbers'] == '—' and stout['taps_count'] == 0
        porter = by['Портер Ночной']
        assert porter['remaining_liters'] == -3.0
        assert porter['stock_level'] == 'negative'
        assert d['taps'][0]['beer_name'] == 'Портер Ночной'   # отрицательный — первым
        assert d['negative_stock_count'] == 1
        assert d['low_stock_count'] == 1                       # negative входит в low
        assert d['total_liters'] == 30.0                       # минус не вычитается


def test_taplist_network():
    with _patched() as c:
        code, d = _get(c, 'taplist', BAR_ALL)
        assert code == 200, d
        assert d['bar'] == BAR_ALL
        assert d['updated_at'] == FETCHED_AT
        names = {t['beer_name'] for t in d['taps']}
        # Фильтр по кранам действует посклада: кеги бара без кранов видны и в сети.
        assert names == {'Лагер Домашний', 'ИПА Хмельной', 'Стаут Тёмный', 'Портер Ночной'}, sorted(names)
        assert 'Масло подсолнечное' not in names
        by = {t['beer_name']: t for t in d['taps']}
        assert by['Стаут Тёмный']['on_tap'] is False
        assert by['Лагер Домашний']['on_tap'] is True
        assert d['active_taps_count'] == 2
        assert d['total_items'] == 4
        assert d['total_liters'] == 48.0                       # 18 + 30, минус не вычитается
        assert d['negative_stock_count'] == 1


# --- этап 1: заказы поставщикам на доске (S-10..S-13) ---------------------------

USER = {'login': 'anna', 'display_name': 'Анна'}


def _order_item(pid, bar, qty, name='x', unit='шт', kind='bottle'):
    return {'product_id': pid, 'bar': bar, 'qty': qty, 'name': name, 'unit': unit, 'kind': kind}


def test_order_board_on_order_reduces_recommendation():
    """Открытый заказ вычитается из рекомендации, но не из «хватит дн.».

    P_BOTTLE на Лиговском: остаток 4, расход 1.5/день, ООО "Май" lead 2:
    без заказа → рекомендация 4, срочность medium (см. test_order_board_shape_and_totals);
    с заказом 10 в пути → effective 14 ≥ target 7.5 → рекомендация 0, срочность low,
    days_left по-прежнему 4 / 1.5 = 2.7. Заказ на Большой — только в «Общая» (сумма).
    """
    store = _temp_order_store()
    store.set_draft_items('ООО "Май"', [_order_item(P_BOTTLE, BAR_LIG, 10), _order_item(P_BOTTLE, BAR_BOL, 6)], USER)
    order = store.send('ООО "Май"', USER, expected_at='2025-11-07')
    with _patched(order_store=store) as c:
        code, d = _get(c, 'order-board', BAR_LIG)
        assert code == 200, d
        it = _by_id(d)[P_BOTTLE]
        assert it['stock'] == 4.0 and it['on_order'] == 10.0 and it['effective_stock'] == 14.0
        assert it['recommended'] == 0 and it['urgency'] == 'low'
        assert it['days_left'] == 2.7
        assert it['open_orders'] == [{'order_id': order['id'], 'supplier': 'ООО "Май"', 'qty': 10.0,
                                      'expected_at': '2025-11-07', 'status': 'sent'}]
        assert d['on_order_count'] == 1 and d['recommended_total'] == 0
        # у остальных позиций «в пути» нет
        assert all(x['on_order'] == 0 for x in d['items'] if x['product_id'] != P_BOTTLE)

        code, d = _get(c, 'order-board', BAR_BOL)
        assert _by_id(d)[P_BOTTLE]['on_order'] == 6.0
        code, d = _get(c, 'order-board', BAR_ALL)
        it = _by_id(d)[P_BOTTLE]
        assert it['on_order'] == 16.0 and it['effective_stock'] == 29.0
        assert len(it['open_orders']) == 2

        # «приехало» не закрывает «в пути»; отмена — закрывает
        store.mark_received(order['id'], USER)
        code, d = _get(c, 'order-board', BAR_LIG)
        assert _by_id(d)[P_BOTTLE]['on_order'] == 10.0
        assert _by_id(d)[P_BOTTLE]['open_orders'][0]['status'] == 'received'
        store.cancel(order['id'], USER)
        code, d = _get(c, 'order-board', BAR_LIG)
        it = _by_id(d)[P_BOTTLE]
        assert it['on_order'] == 0 and it['recommended'] == 4 and it['urgency'] == 'medium'
        assert d['on_order_count'] == 0


def test_order_board_negative_stock_stays_critical_with_on_order():
    store = _temp_order_store()
    store.set_draft_items('Лента', [_order_item(P_NEG, BAR_LIG, 5)], USER)
    store.send('Лента', USER)
    with _patched(order_store=store) as c:
        code, d = _get(c, 'order-board', BAR_LIG)
        it = _by_id(d)[P_NEG]
        assert it['stock'] == -1.0 and it['on_order'] == 5.0 and it['effective_stock'] == 4.0
        assert it['urgency'] == 'critical'                 # учётная ошибка не лечится заказом
        assert d['items'][0]['product_id'] == P_NEG


def test_order_board_draft_qty_per_bar():
    store = _temp_order_store()
    store.set_draft_items('ООО "Май"', [_order_item(P_BOTTLE, BAR_LIG, 3), _order_item(P_BOTTLE, BAR_BOL, 2)], USER)
    store.set_draft_items('Лента', [_order_item(P_IDLE, BAR_LIG, 1)], USER)
    with _patched(order_store=store) as c:
        _, lig = _get(c, 'order-board', BAR_LIG)
        assert _by_id(lig)[P_BOTTLE]['draft_qty'] == 3.0
        assert _by_id(lig)[P_IDLE]['draft_qty'] == 1.0
        assert lig['draft_count'] == 2
        _, bol = _get(c, 'order-board', BAR_BOL)
        assert _by_id(bol)[P_BOTTLE]['draft_qty'] == 2.0 and bol['draft_count'] == 1
        _, net = _get(c, 'order-board', BAR_ALL)
        assert _by_id(net)[P_BOTTLE]['draft_qty'] == 5.0      # для «Общая» — сумма, только показ
        # черновик не влияет на рекомендацию (в пути — только отправленное)
        assert _by_id(lig)[P_BOTTLE]['recommended'] == 4 and _by_id(lig)[P_BOTTLE]['on_order'] == 0


def test_order_board_reconciles_with_incoming_invoice():
    """Приход P_NEW на Лиговский 26.10.2025 закрывает заказ, отправленный до него.

    Заказ от 25.10 → позиция оприходована 26.10, заказ posted, «в пути» 0.
    Заказ от 27.10 (после накладной) остаётся открытым.
    """
    store = _temp_order_store()
    data = store._load()
    data['orders'] = [
        {'id': 'before', 'supplier': 'Лента', 'status': 'sent', 'sent_at': '2025-10-25T10:00:00',
         'expected_at': '2025-10-27',
         'items': [{'product_id': P_NEW, 'bar': BAR_LIG, 'name': 'Лимонад', 'unit': 'шт', 'qty': 24}]},
        {'id': 'after', 'supplier': 'Лента', 'status': 'sent', 'sent_at': '2025-10-27T10:00:00',
         'expected_at': '2025-10-29',
         'items': [{'product_id': P_NEW, 'bar': BAR_LIG, 'name': 'Лимонад', 'unit': 'шт', 'qty': 12}]},
        {'id': 'other-bar', 'supplier': 'Лента', 'status': 'sent', 'sent_at': '2025-10-25T10:00:00',
         'items': [{'product_id': P_NEW, 'bar': BAR_KRE, 'name': 'Лимонад', 'unit': 'шт', 'qty': 6}]},
    ]
    store._save(data)
    with _patched(order_store=store) as c:
        code, d = _get(c, 'order-board', BAR_LIG)
        assert code == 200, d
        it = _by_id(d)[P_NEW]
        assert it['on_order'] == 12.0
        assert [o['order_id'] for o in it['open_orders']] == ['after']
    before = store.get_order('before')
    assert before['status'] == 'posted' and before['items'][0]['posted_at'] == '2025-10-26'
    assert store.get_order('after')['status'] == 'sent'
    assert store.get_order('other-bar')['status'] == 'sent'   # склад Кременчугской: прихода не было


def test_order_board_survives_order_store_failure():
    def broken():
        raise OSError('disk gone')
    with _patched(order_store=broken) as c:
        code, d = _get(c, 'order-board', BAR_LIG)
        assert code == 200, d
        it = _by_id(d)[P_BOTTLE]
        assert it['on_order'] == 0 and it['draft_qty'] == 0 and it['open_orders'] == []
        assert it['recommended'] == 4


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
