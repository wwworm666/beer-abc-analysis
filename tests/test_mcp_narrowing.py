"""
Сужение больших ответов для ИИ-агентов (2026-09-28): compact, фильтры, q и limit.

Self-runnable: `py -3 tests/test_mcp_narrowing.py` (совместимо с pytest).

Зачем: мост MCP режет ответ на 60 000 символов, а агент контента упирался в таплист
бара (58–85 тыс.), кэш ЧЗ (~0,5 млн), справочник кег (~50 тыс.) и карточки меню
(~60 тыс.). Маршруты получили необязательные параметры; страницы их не передают,
поэтому без параметров ответ обязан остаться прежним байт в байт.

Что проверяется (голый Flask с нужными blueprint'ами, данные подменены, iiko нет):
- /api/stocks/order-board: supplier (имя или написание category), only_to_order=1,
  limit меняют только состав items/suppliers — числа позиций и счётчики те же, что
  без фильтра; неизвестный поставщик — пусто и known_suppliers; кривой фильтр — 400
  ДО похода в iiko;
- /api/chz/stock, /api/beers/draft, /menu/api/items: q (регистр, «ё», GTIN и штрихкод),
  limit, total и matched; кривой limit — 400; без параметров — прежняя форма ответа;
- /api/taps/taplist-full: compact=1 — краткая запись крана, compact=0 и без него —
  полный ответ, другое значение — 400;
- через мост MCP: аргументы инструментов доходят до маршрутов (схема -> строка запроса).
Снимок сети и справочник поставщиков берутся из tests/test_stocks_routes.py (только чтение).
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from flask import Flask  # noqa: E402

import routes.menu_editor as rme  # noqa: E402
import routes.stocks as rs  # noqa: E402
import routes.taps as rtaps  # noqa: E402
import test_stocks_routes as tsr  # noqa: E402  (синтетический снимок сети и _patched)

BAR = tsr.BAR_LIG


# --------------------------------------------------------------------------- доска «К заказу»

def _board(client, **params):
    response = client.get('/api/stocks/order-board', query_string=dict({'bar': BAR}, **params))
    return response.status_code, response.get_json()


def test_order_board_without_filters_unchanged():
    with tsr._patched() as client:
        code, board = _board(client)
        assert code == 200 and 'filter' not in board, 'страница фильтров не передаёт: ответ прежний'
        assert board['items'] and board['suppliers']


def test_order_board_supplier_filter_keeps_numbers():
    with tsr._patched() as client:
        _, full = _board(client)
        by_id = {it['product_id']: it for it in full['items']}
        for supplier in sorted({it['supplier'] for it in full['items']}):
            code, part = _board(client, supplier=supplier.upper())      # регистр не важен
            assert code == 200, part
            assert part['items'] and all(it['supplier'] == supplier for it in part['items']), supplier
            for it in part['items']:
                assert it == by_id[it['product_id']], 'расчёт позиции тот же, что без фильтра'
            assert list(part['suppliers']) == [supplier]
            assert part['suppliers'][supplier] == full['suppliers'][supplier], 'минимальный заказ группы тот же'
            for key in ('total_items', 'critical_count', 'decide_count', 'recommended_total'):
                assert part[key] == full[key], key + ': счётчики — по всей доске'
            expected = [it['product_id'] for it in full['items'] if it['supplier'] == supplier]
            assert [it['product_id'] for it in part['items']] == expected, 'порядок срочности сохранён'
            assert part['filter'] == {'supplier': supplier, 'only_to_order': False, 'limit': None,
                                      'matched': len(expected), 'returned': len(expected),
                                      'total_items': len(full['items'])}
        # Написание category из iiko сводится справочником к имени поставщика.
        for item in full['items']:
            _, part = _board(client, supplier=item['supplier_raw'])
            assert item['product_id'] in {it['product_id'] for it in part['items']}, item['supplier_raw']


def test_order_board_only_to_order_limit_and_unknown_supplier():
    with tsr._patched() as client:
        _, full = _board(client)
        _, to_order = _board(client, only_to_order='1')
        expected = [it['product_id'] for it in full['items'] if it['recommended'] > 0]
        assert expected, 'в синтетическом снимке есть что заказать'
        assert [it['product_id'] for it in to_order['items']] == expected
        _, limited = _board(client, limit=2)
        assert [it['product_id'] for it in limited['items']] == [it['product_id'] for it in full['items'][:2]]
        assert limited['filter']['matched'] == len(full['items']) and limited['filter']['returned'] == 2
        assert limited['suppliers'] == full['suppliers'], 'limit не трогает группы поставщиков'
        _, nobody = _board(client, supplier='Поставщик, которого нет')
        assert nobody['items'] == [] and nobody['suppliers'] == {}
        assert nobody['filter']['known_suppliers'] == sorted(full['suppliers'])
        _, off = _board(client, only_to_order='0')
        assert off['items'] == full['items'] and 'filter' not in off


def test_order_board_bad_filter_is_400_before_iiko():
    calls = []
    with tsr._patched() as client:
        original = rs.get_stock_snapshot
        rs.get_stock_snapshot = lambda *a, **k: calls.append(1) or original()
        for params in ({'only_to_order': 'yes'}, {'only_to_order': 'true'}, {'limit': '0'},
                       {'limit': 'abc'}, {'limit': str(rs.LIST_LIMIT_MAX + 1)}):
            code, data = _board(client, **params)
            assert code == 400 and data.get('error'), params
        assert calls == [], 'кривой фильтр отвечает 400, не трогая iiko'
        code, _ = _board(client, limit=str(rs.LIST_LIMIT_MAX))
        assert code == 200 and calls == [1]


# --------------------------------------------------------------------------- кэш ЧЗ

CHZ_ITEMS = [
    {'gtin': '04610093628430', 'name': 'Пиво FH Helles светлое 4,5%', 'brand': 'Фестхаус', 'count': 134},
    {'gtin': '04601234567890', 'name': 'Пиво Тёмное Портер', 'brand': 'Бакунин', 'count': 12},
    {'gtin': '04600000000017', 'name': 'Сидр яблочный', 'brand': 'Кидерс', 'count': 3},
]


def _chz_client(tmp):
    path = Path(tmp) / 'chz_stock.json'
    path.write_text(json.dumps(CHZ_ITEMS, ensure_ascii=False), encoding='utf-8')
    rs._CHZ_CACHE_FILE = path
    app = Flask('narrow_chz')
    app.register_blueprint(rs.stocks_bp)
    return app.test_client()


def test_chz_cache_search_and_limit():
    saved = rs._CHZ_CACHE_FILE
    with tempfile.TemporaryDirectory() as tmp:
        try:
            client = _chz_client(tmp)
            plain = client.get('/api/chz/stock').get_json()
            assert set(plain) == {'items', 'updated_at'} and plain['items'] == CHZ_ITEMS, 'без q и limit — прежний ответ'

            def names(**params):
                data = client.get('/api/chz/stock', query_string=params).get_json()
                return [it['gtin'] for it in data['items']], data
            gtins, data = names(q='HELLES')
            assert gtins == ['04610093628430'] and data['total'] == 3 and data['matched'] == 1
            assert names(q='4610093628430')[0] == ['04610093628430'], 'штрихкод EAN-13 без ведущего нуля'
            assert names(q='темное')[0] == ['04601234567890'], '«ё» = «е»'
            assert names(q='бакунин')[0] == ['04601234567890'], 'поиск и по бренду'
            gtins, data = names(limit=2)
            assert gtins == [it['gtin'] for it in CHZ_ITEMS[:2]] and data['matched'] == 3
            gtins, data = names(q='пиво', limit=1)
            assert len(gtins) == 1 and data['matched'] == 2
            for bad in ('0', 'x', '1001'):
                assert client.get('/api/chz/stock', query_string={'limit': bad}).status_code == 400, bad
        finally:
            rs._CHZ_CACHE_FILE = saved


# --------------------------------------------------------------------------- кеги и таплист

CATALOG = {
    'g1': {'id': 'g1', 'name': 'КЕГ Фуллерс ИПА 30 л', 'num': '101'},
    'g2': {'id': 'g2', 'name': 'КЕГ Жигули Тёмное 30 л', 'num': '102'},
    'g3': {'id': 'g3', 'name': 'КЕГ Сидр Грушевый 20 л', 'num': '103'},
}
DETAILS = {'g1': ('Fuller\'s IPA', 'Fuller\'s', 'IPA - English'), 'g2': None, 'g3': ('Pear Cider', 'Кидерс', 'Cider')}


def _fake_tap_details(tap, registry):
    card = DETAILS.get(tap['iiko_product_id'])
    if card is None:
        return {'mapping_status': 'unverified', 'beer_name': tap['current_beer'], 'brewery': None, 'style': None}
    return {'mapping_status': 'verified', 'beer_name': card[0], 'brewery': card[1], 'style': card[2]}


class _TapsPatch:
    def __enter__(self):
        self.saved = {name: getattr(rtaps, name) for name in
                      ('load_registry', 'product_catalog', 'tap_details', 'reviewed_taplist')}
        rtaps.load_registry = lambda: {'products': {}}
        rtaps.product_catalog = lambda registry: {k: dict(v) for k, v in CATALOG.items()}
        rtaps.tap_details = _fake_tap_details
        rtaps.reviewed_taplist = lambda: [dict(row) for row in TAPLIST_ROWS]
        app = Flask('narrow_taps')
        app.register_blueprint(rtaps.taps_bp)
        self.client = app.test_client()
        return self

    def __exit__(self, *exc):
        for name, value in self.saved.items():
            setattr(rtaps, name, value)
        return False


def test_beers_draft_search_and_limit():
    with _TapsPatch() as rig:
        plain = rig.client.get('/api/beers/draft').get_json()
        assert set(plain) == {'beers'} and [b['id'] for b in plain['beers']] == ['g2', 'g3', 'g1'], \
            'без параметров — прежний список по алфавиту'

        def ids(**params):
            data = rig.client.get('/api/beers/draft', query_string=params).get_json()
            return [b['id'] for b in data['beers']], data
        assert ids(q='ипа')[0] == ['g1']
        assert ids(q='english')[0] == ['g1'], 'по стилю из карточки Untappd'
        assert ids(q='темное')[0] == ['g2'], '«ё» = «е»'
        assert ids(q='103')[0] == ['g3'], 'по артикулу'
        found, data = ids(q='кег', limit=2)
        assert found == ['g2', 'g3'] and data['total'] == 3 and data['matched'] == 3 and data['limit'] == 2
        assert rig.client.get('/api/beers/draft?limit=0').status_code == 400


TAPLIST_ROWS = [
    {'bar': 'Лиговский', 'bar_id': 'bar2', 'tap_number': 1, 'beer_name': 'Пилс', 'brewery': 'Б', 'style': 'Pilsner',
     'abv': 4.8, 'ibu': 30, 'mapped': True, 'mapping_status': 'verified', 'price_status': 'verified',
     'description': 'Очень длинное описание ' * 40, 'photo_url': 'https://img.example/1.jpg',
     'untappd_url': 'https://untappd.com/b/1', 'started_at': '2026-09-20T15:00:00',
     'servings': [{'portion_liters': '0.5', 'price_rub': '330.00', 'dish_name': 'Пилс 0,5', 'dish_id': 'd1',
                   'recipe_id': 'r1', 'price_source': {'kind': 'iiko_price_order'}}]},
    {'bar': 'Лиговский', 'bar_id': 'bar2', 'tap_number': 2, 'beer_name': 'Сорт без цены', 'brewery': None,
     'style': None, 'abv': None, 'ibu': None, 'mapped': False, 'mapping_status': 'missing_product',
     'price_status': 'unavailable', 'description': None, 'photo_url': None, 'servings': []},
]


def test_taplist_full_compact():
    with _TapsPatch() as rig:
        full = rig.client.get('/api/taps/taplist-full').get_json()
        assert full['taplist'] == TAPLIST_ROWS and 'compact' not in full, 'без compact — полный ответ'
        assert rig.client.get('/api/taps/taplist-full?compact=0').get_json() == full
        short = rig.client.get('/api/taps/taplist-full?compact=1').get_json()
        assert short['compact'] is True and short['count'] == 2 and short['mapped_count'] == 1
        first, second = short['taplist']
        assert first['price_0_5'] == '330.00' and first['prices'] == [{'l': '0.5', 'rub': '330.00'}]
        assert 'description' not in first and 'photo_url' not in first and 'servings' not in first
        assert second['price_0_5'] is None and second['mapping_status'] == 'missing_product'
        assert len(json.dumps(short, ensure_ascii=False)) < len(json.dumps(full, ensure_ascii=False)) / 2
        for bad in ('true', 'yes', '2'):
            response = rig.client.get('/api/taps/taplist-full', query_string={'compact': bad})
            assert response.status_code == 400, bad


# --------------------------------------------------------------------------- карточки меню

MENU_ITEMS = [
    {'id': 1, 'n': 1, 'name': 'Фуллерс ИПА', 'latin': "Fuller's IPA", 'brewery': "Fuller's", 'country': 'Англия',
     'style': 'English IPA', 'tags': ['Хмель', 'Цитрус', 'Горечь'], 'tap': 3},
    {'id': 2, 'n': 2, 'name': 'Тёмный лагер', 'latin': 'Dark Lager', 'brewery': 'Бакунин', 'country': 'Россия',
     'style': 'Munich Dunkel', 'tags': ['Карамель'], 'tap': None},
    {'id': 3, 'n': 3, 'name': 'Грушевый сидр', 'latin': 'Pear Cider', 'brewery': 'Кидерс', 'country': 'Россия',
     'style': 'Cider', 'tags': [], 'tap': None},
]


def test_menu_items_search_and_limit():
    saved = rme._load_items
    rme._load_items = lambda: [dict(item) for item in MENU_ITEMS]
    try:
        app = Flask('narrow_menu')
        app.register_blueprint(rme.menu_editor_bp)
        client = app.test_client()
        assert client.get('/menu/api/items').get_json() == MENU_ITEMS, 'без параметров — прежний список'

        def ids(**params):
            data = client.get('/menu/api/items', query_string=params).get_json()
            return [item['id'] for item in data['items']], data
        assert ids(q='ipa')[0] == [1]
        assert ids(q='цитрус')[0] == [1], 'по дескрипторам'
        assert ids(q='темный')[0] == [2], '«ё» = «е»'
        found, data = ids(q='россия', limit=1)
        assert found == [2] and data['matched'] == 2 and data['total'] == 3
        assert client.get('/menu/api/items?limit=abc').status_code == 400
    finally:
        rme._load_items = saved


# --------------------------------------------------------------------------- через мост MCP

def test_tool_arguments_reach_routes_through_bridge():
    """Схемы инструментов и строка запроса совпадают: compact, q и limit доходят до маршрутов."""
    from core.mcp import bridge
    from core.mcp.principal import Principal
    from core.mcp.tools import stocks
    tools = {spec.name: spec for spec in stocks.TOOLS}
    owner = {'id': 1, 'login': 'owner', 'display_name': 'Владелец', 'is_admin': True, 'active': True}
    saved_owner = bridge.owner_record
    saved_items = rme._load_items
    bridge.owner_record = lambda principal: dict(owner)
    rme._load_items = lambda: [dict(item) for item in MENU_ITEMS]
    bridge.response_cache.clear()
    principal = Principal(user_id=1, login='owner', display_name='Владелец', token_id='st_t', token_kind='static',
                          client_name='pytest')
    try:
        with _TapsPatch():
            app = Flask('narrow_bridge')
            app.register_blueprint(rtaps.taps_bp)
            app.register_blueprint(rme.menu_editor_bp)
            with app.app_context():
                result = bridge.execute(tools['stocks_taplist_full'], {'bar_id': 'bar2', 'compact': '1'}, principal)
                assert not result.is_error, result.text_value
                assert result.content[0]['text'].startswith('Данные на '), 'тяжёлое чтение — со строкой свежести'
                assert json.loads(result.content[1]['text'])['compact'] is True
                beers = bridge.execute(tools['stocks_beers_draft'], {'q': 'сидр', 'limit': 5}, principal)
                assert [b['id'] for b in json.loads(beers.text_value)['beers']] == ['g3']
                menu = bridge.execute(tools['stocks_menu_items'], {'q': 'lager', 'limit': 1}, principal)
                assert [i['id'] for i in json.loads(menu.text_value)['items']] == [2]
                bad = bridge.execute(tools['stocks_menu_items'], {'limit': 0}, principal)
                assert bad.is_error and 'limit' in bad.text_value, 'схема ловит до маршрута'
    finally:
        bridge.owner_record = saved_owner
        rme._load_items = saved_items
        bridge.response_cache.clear()


if __name__ == '__main__':
    import inspect
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and inspect.isfunction(fn):
            try:
                fn()
                print('ok   ' + name)
            except Exception as error:  # noqa: BLE001 — самозапуск печатает все падения
                failed += 1
                import traceback
                traceback.print_exc()
                print('FAIL ' + name + ': ' + repr(error))
    sys.exit(1 if failed else 0)
