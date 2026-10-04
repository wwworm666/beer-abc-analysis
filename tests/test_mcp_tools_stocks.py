"""
Тесты описаний MCP-инструментов домена stocks (core/mcp/tools/stocks.py).

Self-runnable: `py -3 tests/test_mcp_tools_stocks.py` (совместимо с pytest).

Приложение — голый Flask со ВСЕМИ blueprint'ами сервиса (routes.register_blueprints),
как видит прод; app.py не импортируется (он запускает шедулеры и Telegram с боевыми
токенами). Маршруты не вызываются: нужны только url_map и исходники view-функций,
поэтому ни iiko, ни ЧЗ, ни файлы данных тест не трогает.

Что проверяется (контракт MCP, раздел 5):
- validate_tool_spec пуст; имена уникальны, с префиксом stocks_, домен stocks;
- каждый (метод, путь) есть в url_map, метод разрешён, view — из файлов домена
  (routes/stocks.py, orders.py, suppliers.py, receiving.py, expiration.py, taps.py,
  yml_feeds.py, menu_editor.py); path_params совпадают с аргументами правила Flask;
- все API- и data-маршруты этих файлов (/api/*, /feeds/*, /menu/api/*) покрыты ровно
  одним инструментом или стоят в EXCLUDED; HTML-страницы в охват не входят;
- query- и body-аргументы действительно читаются модулем маршрута (имя поля в
  исходнике: request.args.get('...') или строка '...'), чтобы опечатка в схеме не
  превращалась в молча игнорируемый аргумент;
- heavy совпадает с тем, ходит ли view в iiko / ЧЗ / Chromium (маркеры в исходнике);
- examples проходят проверку схемы: core/mcp/schema_check.py, если он есть, плюс
  своя минимальная проверка; типичные ошибки агента схема отбивает;
- идентификаторы баров и константы схем совпадают с кодом (extensions.BARS,
  core.taplist.BAR_NAMES, routes/stocks и routes/expiration, TapsManager, order_store,
  supplier_directory, menu_editor, yml_overrides; пределы и перечни приёмки на РЦ —
  routes/receiving, receiving_store, receiving_codes, receiving_photo_store);
- пометки: GET — только чтение; зафиксированные наборы destructive, open_world,
  heavy и also_in=('content',); примеры есть у всех лёгких чтений и нет у записи;
- тексты: без эмодзи, упомянутые stocks_* и документы docs/*.md существуют;
  INSTRUCTIONS 40..90 строк и содержит правила безопасности;
- сценарии: имена, аргументы, render на пустых, верных и кривых аргументах;
- модуль совместим с Python 3.10: f-строк в нём нет вовсе.
"""

import inspect
import io
import os
import re
import sys
import tokenize

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from core.mcp import spec as mcp_spec  # noqa: E402
from core.mcp.tools import stocks  # noqa: E402

OWN_MODULES = ('routes.stocks', 'routes.orders', 'routes.suppliers', 'routes.receiving',
               'routes.expiration', 'routes.taps', 'routes.yml_feeds', 'routes.menu_editor')
ROUTE_METHODS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')
DATA_ROUTES = ('/feeds/taplist.yml', '/feeds/kitchen.yml', '/feeds/kitchen/<bar_id>')

# Зафиксированные пометки (решение по коду маршрутов, см. докстринг core/mcp/tools/stocks.py).
EXPECTED_DESTRUCTIVE = {
    'stocks_order_draft_clear', 'stocks_order_send', 'stocks_order_close', 'stocks_order_cancel',
    'stocks_supplier_delete', 'stocks_tap_start', 'stocks_tap_stop', 'stocks_tap_replace',
    'stocks_menu_item_delete',
    # фид Яндекса публичен: сохранение необратимо уходит наружу (проверка безопасности 2026-09-28)
    'stocks_yml_feed_save',
    # приёмка на РЦ: закрытие не отменить (и уходит сообщение бухгалтерии), скан и фото — удаление
    'stocks_receiving_close', 'stocks_receiving_scan_delete', 'stocks_receiving_invoice_delete',
}
EXPECTED_OPEN_WORLD = {
    'stocks_chz_live', 'stocks_chz_refresh', 'stocks_nomenclature_update', 'stocks_yml_feed_save',
    'stocks_yml_refresh', 'stocks_menu_refresh_prices',
    # кег и сорт на кране меняют публичный таплист и фид Яндекса
    'stocks_tap_start', 'stocks_tap_stop', 'stocks_tap_replace', 'stocks_tap_identify',
    # приёмка на РЦ: сверка с iiko, ЧЗ через бар-ПК, Telegram бухгалтерии; индекс из iiko
    'stocks_receiving_close', 'stocks_receiving_index_refresh',
}
EXPECTED_HEAVY = {
    'stocks_order_board', 'stocks_taplist_stock', 'stocks_bottles_stock', 'stocks_kitchen_stock',
    'stocks_expiry_stock', 'stocks_chz_live', 'stocks_chz_refresh', 'stocks_suppliers_list',
    'stocks_supplier_upsert', 'stocks_supplier_delete', 'stocks_supplier_alias_add',
    'stocks_expiration_board', 'stocks_taplist_full', 'stocks_taplist_full_csv',
    'stocks_nomenclature_update', 'stocks_feed_taplist_yml', 'stocks_feed_bar_yml',
    'stocks_yml_feed', 'stocks_yml_feed_save', 'stocks_yml_feed_ack', 'stocks_yml_refresh',
    'stocks_menu_refresh_prices', 'stocks_menu_render_pdf', 'stocks_menu_export_pdf',
    'stocks_receiving_close', 'stocks_receiving_index_refresh',
}
EXPECTED_ALSO_CONTENT = {
    'stocks_taps_bars', 'stocks_taps_bar', 'stocks_taplist_full', 'stocks_feed_taplist_yml',
    'stocks_feed_kitchen_yml', 'stocks_yml_feeds', 'stocks_yml_feed', 'stocks_feed_bar_yml',
}
# Признаки того, что view в момент вызова ходит в iiko, ЧЗ или Chromium (прямо или через
# помощника маршрута): снимок сети, прайс, номенклатура, OLAP, бар-ПК, рендер PDF.
IIKO_MARKERS = (
    'get_stock_snapshot', '_load_stock_data', 'fetch_price_sources', 'reviewed_taplist',
    'IikoAPI', 'OlapReports', 'get_stocks_nomenclature', '_payload(', 'refresh_prices',
    'render_bar_feed', 'bar_state', 'feed_detail_data', 'refresh_snapshot', '_render_pdf_html',
    'get_chz_stock', 'start_chz_refresh',
    # приёмка на РЦ: фоновая сверка закрытой приёмки (iiko, ЧЗ на бар-ПК) и пересборка индекса
    'start_receiving_index_refresh', 'start_receipt_processing',
)

_APP = None


def _app():
    """Голый Flask со всеми blueprint'ами сервиса (один раз на процесс)."""
    global _APP
    if _APP is None:
        from flask import Flask
        from routes import register_blueprints
        app = Flask(__name__)
        register_blueprints(app)
        _APP = app
    return _APP


def _routes():
    """{(метод, правило): [Rule]} без HEAD/OPTIONS."""
    out = {}
    for rule in _app().url_map.iter_rules():
        for method in rule.methods or ():
            if method in ROUTE_METHODS:
                out.setdefault((method, rule.rule), []).append(rule)
    return out


def _view(rule):
    return _app().view_functions.get(rule.endpoint)


def _view_module(rule):
    view = _view(rule)
    return getattr(inspect.unwrap(view), '__module__', '') if view is not None else ''


def _in_scope(path):
    """API и data-маршруты (охват MCP); страницы HTML — нет."""
    return path.startswith('/api/') or path.startswith('/menu/api/') or path in DATA_ROUTES


def _own_routes():
    pairs = set()
    for (method, path), rules in _routes().items():
        if _in_scope(path) and any(_view_module(rule) in OWN_MODULES for rule in rules):
            pairs.add((method, path))
    return pairs


def _tools():
    return {spec.name: spec for spec in stocks.TOOLS}


def _module_source(rule):
    view = _view(rule)
    return inspect.getsource(sys.modules[inspect.unwrap(view).__module__])


def _view_body(rule):
    """Тело view без декораторов и строки def: имя функции маркером не считается."""
    lines = inspect.getsource(inspect.unwrap(_view(rule))).splitlines()
    for index, line in enumerate(lines):
        if line.lstrip().startswith('def '):
            return '\n'.join(lines[index + 1:])
    return '\n'.join(lines)


# --------------------------------------------------------------------------- проверка схемы

_JSON_TYPES = {
    'string': lambda v: isinstance(v, str),
    'integer': lambda v: isinstance(v, int) and not isinstance(v, bool),
    'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    'boolean': lambda v: isinstance(v, bool),
    'array': lambda v: isinstance(v, list),
    'object': lambda v: isinstance(v, dict),
    'null': lambda v: v is None,
}


def _fallback_check(schema, value, where='args'):
    """Минимальная проверка значения по JSON Schema (подмножество, которым пользуются описания)."""
    errors = []
    types = schema.get('type')
    if types is not None:
        types = types if isinstance(types, list) else [types]
        if not any(_JSON_TYPES[t](value) for t in types):
            return [where + ': тип не ' + '/'.join(types)]
    if 'enum' in schema and value not in schema['enum']:
        errors.append(where + ': значение не из enum')
    if isinstance(value, str):
        if 'minLength' in schema and len(value) < schema['minLength']:
            errors.append(where + ': короче minLength')
        if 'maxLength' in schema and len(value) > schema['maxLength']:
            errors.append(where + ': длиннее maxLength')
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            errors.append(where + ': не подходит под pattern')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 'minimum' in schema and value < schema['minimum']:
            errors.append(where + ': меньше minimum')
        if 'maximum' in schema and value > schema['maximum']:
            errors.append(where + ': больше maximum')
    if isinstance(value, list):
        if 'minItems' in schema and len(value) < schema['minItems']:
            errors.append(where + ': меньше minItems')
        if 'maxItems' in schema and len(value) > schema['maxItems']:
            errors.append(where + ': больше maxItems')
        if 'items' in schema:
            for i, item in enumerate(value):
                errors += _fallback_check(schema['items'], item, where + '[' + str(i) + ']')
    if isinstance(value, dict):
        props = schema.get('properties') or {}
        extra = schema.get('additionalProperties')
        if 'minProperties' in schema and len(value) < schema['minProperties']:
            errors.append(where + ': меньше minProperties')
        for key in schema.get('required') or []:
            if key not in value:
                errors.append(where + ': нет обязательного ' + key)
        for key, item in value.items():
            if key in props:
                errors += _fallback_check(props[key], item, where + '.' + key)
            elif extra is False:
                errors.append(where + ': лишнее поле ' + key)
            elif isinstance(extra, dict):
                errors += _fallback_check(extra, item, where + '.' + key)
    return errors


def _schema_errors(schema, args):
    """Ошибки аргументов: своя проверка плюс core/mcp/schema_check.py, если он уже есть."""
    errors = _fallback_check(schema, args)
    try:
        from core.mcp import schema_check
    except ImportError:
        return errors
    for name in ('check_args', 'validate_args', 'check', 'validate', 'errors'):
        fn = getattr(schema_check, name, None)
        if callable(fn):
            result = fn(schema, args)
            if isinstance(result, (list, tuple)):
                errors += [str(e) for e in result]
            elif isinstance(result, str) and result:
                errors.append(result)
            break
    return errors


# --------------------------------------------------------------------------- тексты

_EMOJI_RE = re.compile('[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]')


def _prompt_renders():
    samples = ({}, {'bar': 'bar1'}, {'bar': 'Лиговский', 'supplier': 'ООО "Май"'},
               {'bar': 'nevsky'}, {'bar': None, 'supplier': 17}, {'bar': '  BAR4  '})
    for prompt in stocks.PROMPTS:
        for args in samples:
            yield prompt, args, prompt.render(args)


def _texts():
    """Всё, что видит агент: (где, текст)."""
    out = [('INSTRUCTIONS', stocks.INSTRUCTIONS)]
    for spec in stocks.TOOLS:
        out.append((spec.name + '.title', spec.title))
        out.append((spec.name + '.description', spec.description))
        out.append((spec.name + '.schema', repr(spec.input_schema)))
    for prompt in stocks.PROMPTS:
        out.append((prompt.name + '.title', prompt.title))
        out.append((prompt.name + '.description', prompt.description))
        for arg in prompt.arguments:
            out.append((prompt.name + '.' + arg.name, arg.description))
    for prompt, args, text in _prompt_renders():
        out.append((prompt.name + '.render' + repr(args), text))
    return out


# --------------------------------------------------------------------------- тесты: описания

def test_specs_valid():
    errors = [e for spec in stocks.TOOLS for e in mcp_spec.validate_tool_spec(spec)]
    assert errors == [], errors


def test_names_unique_prefixed():
    names = [spec.name for spec in stocks.TOOLS]
    assert len(names) == len(set(names)), 'повтор имени инструмента'
    for spec in stocks.TOOLS:
        assert spec.domain == 'stocks', spec.name
        assert spec.name.startswith('stocks_'), spec.name
        assert mcp_spec.TOOL_NAME_RE.match(spec.name), spec.name
        assert spec.route_backed, spec.name + ': у домена stocks только инструменты-маршруты'
        for other in spec.also_in:
            assert other in mcp_spec.DOMAINS and other != 'stocks', spec.name


def test_exports():
    assert isinstance(stocks.TOOLS, list) and stocks.TOOLS
    assert isinstance(stocks.PROMPTS, list) and stocks.PROMPTS
    assert isinstance(stocks.INSTRUCTIONS, str) and stocks.INSTRUCTIONS.strip()
    assert isinstance(stocks.EXCLUDED, dict)
    for key, reason in stocks.EXCLUDED.items():
        assert isinstance(key, tuple) and len(key) == 2, key
        assert isinstance(reason, str) and reason.strip(), key


# --------------------------------------------------------------------------- тесты: маршруты

def test_routes_exist_and_params_match():
    routes = _routes()
    for spec in stocks.TOOLS:
        key = (spec.method, spec.path)
        assert key in routes, spec.name + ': нет маршрута ' + spec.method + ' ' + spec.path
        rules = routes[key]
        assert all(_view_module(rule) in OWN_MODULES for rule in rules), \
            spec.name + ': маршрут не из файлов домена stocks'
        for rule in rules:
            assert spec.method in rule.methods, spec.name
            assert set(rule.arguments) == set(spec.path_params), \
                spec.name + ': path_params ' + repr(spec.path_params) + ' != ' + repr(sorted(rule.arguments))


def test_all_own_routes_covered_once():
    covered = {}
    for spec in stocks.TOOLS:
        covered.setdefault((spec.method, spec.path), []).append(spec.name)
    doubles = {key: names for key, names in covered.items() if len(names) > 1}
    assert not doubles, 'маршрут описан дважды: ' + repr(doubles)
    own = _own_routes()
    missing = sorted(key for key in own if key not in covered and key not in stocks.EXCLUDED)
    assert not missing, 'маршруты без инструмента и без EXCLUDED: ' + repr(missing)
    both = sorted(key for key in covered if key in stocks.EXCLUDED)
    assert not both, 'маршрут и описан, и исключён: ' + repr(both)
    foreign = sorted(key for key in stocks.EXCLUDED if key not in own)
    assert not foreign, 'EXCLUDED содержит чужие или несуществующие маршруты: ' + repr(foreign)
    outside = sorted(key for key in covered if key not in own)
    assert not outside, 'инструменты вне охвата (страницы или чужие файлы): ' + repr(outside)


def _field_read(source, field):
    return re.search('[\'"]' + re.escape(field) + '[\'"]', source) is not None


def test_arguments_are_read_by_route():
    """Каждый query- и body-аргумент схемы упомянут в модуле маршрута (или в модуле-хранилище)."""
    routes = _routes()
    # Вложенные поля правок фидов и хранилища читаются не в routes/, а в core/.
    extra_sources = {
        'routes.yml_feeds': ('core.yml_overrides',),
        'routes.suppliers': ('core.supplier_directory',),
        'routes.orders': ('core.order_store',),
    }
    for spec in stocks.TOOLS:
        rule = routes[(spec.method, spec.path)][0]
        module_name = inspect.unwrap(_view(rule)).__module__
        source = _module_source(rule)
        for extra in extra_sources.get(module_name, ()):
            __import__(extra)
            source += inspect.getsource(sys.modules[extra])
        props = spec.input_schema.get('properties') or {}
        for name in spec.query_params:
            pattern = r'request\.args\.get\(\s*[\'"]' + re.escape(name) + '[\'"]'
            assert re.search(pattern, source), spec.name + ': маршрут не читает ?' + name
        routed = set(spec.path_params) | set(spec.query_params) | set(spec.file_params)
        for name in props:
            if name in routed:
                continue
            assert spec.body in ('json', 'form', 'multipart'), spec.name
            assert _field_read(source, name), spec.name + ': маршрут не читает поле ' + name


_ARG_READ_RE = re.compile(r'request\.args\.get\(\s*[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]')
# Переменная, в которую view кладёт тело запроса: data = request.get_json(...) or {},
# data = request.json, body = _json_body().
_BODY_ASSIGN_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:request\.get_json\([^)]*\)'
                             r'(?:\s*or\s*\{\})?|request\.json\b|_json_body\(\))')
_HELPER_CALL_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\(([^()]*)\)')


def _field_reads(source, names):
    """Поля, прочитанные из переменных names: x.get('поле') и x['поле']."""
    found = set()
    for name in names:
        found |= set(re.findall(r'\b' + re.escape(name) + r'\.get\(\s*[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]',
                                source))
        found |= set(re.findall(r'\b' + re.escape(name) + r'\[\s*[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]\s*\]',
                                source))
    return found


def _request_reads(rule):
    """(query-параметры, поля тела), которые читают view и его помощники из того же модуля.

    Помощник смотрится на один уровень: если view передаёт ему переменную с телом запроса,
    читается соответствующий параметр помощника (selected_product(data), _validate_item(body)).
    """
    view = inspect.unwrap(_view(rule))
    module = sys.modules[view.__module__]
    body = _view_body(rule)
    body_vars = set(_BODY_ASSIGN_RE.findall(body))
    arg_reads = set(_ARG_READ_RE.findall(body))
    fields = _field_reads(body, body_vars)
    for match in _HELPER_CALL_RE.finditer(body):
        fn = getattr(module, match.group(1), None)
        if not (inspect.isfunction(fn) and fn.__module__ == module.__name__ and fn is not view):
            continue
        source = inspect.getsource(fn)
        arg_reads |= set(_ARG_READ_RE.findall(source))
        params = list(inspect.signature(fn).parameters)
        passed = [a.strip() for a in match.group(2).split(',')] if match.group(2).strip() else []
        helper_vars = {params[i] for i, a in enumerate(passed) if a in body_vars and i < len(params)}
        fields |= _field_reads(source, helper_vars)
    return arg_reads, fields


def test_route_reads_are_described():
    """Обратная сверка: всё, что view (или его помощник в том же модуле) читает из запроса —
    request.args.get('x'), тело.get('x'), тело['x'] — есть в схеме инструмента. Так новое
    поле в маршруте (правки владельца идут параллельно) не проходит мимо описания."""
    routes = _routes()
    for spec in stocks.TOOLS:
        arg_reads, fields = _request_reads(routes[(spec.method, spec.path)][0])
        props = set((spec.input_schema.get('properties') or {}))
        for name in sorted(arg_reads):
            assert name in spec.query_params, spec.name + ': маршрут читает ?' + name + ', в схеме нет'
        if spec.body == 'none':
            assert not fields, spec.name + ': маршрут читает тело ' + repr(sorted(fields)) + ', а body=none'
        for name in sorted(fields):
            assert name in props, spec.name + ': маршрут читает поле ' + name + ', в схеме нет'


def test_reverse_check_sees_known_reads():
    """Сама обратная сверка не пустая: на известных маршрутах она находит чтения."""
    routes = _routes()
    _args, fields = _request_reads(routes[('POST', '/api/taps/<bar_id>/identify')][0])
    assert {'expected', 'tap_number', 'iiko_product_id'} <= fields, fields
    _args, fields = _request_reads(routes[('POST', '/api/orders/draft')][0])
    assert {'supplier', 'product_id', 'bar', 'qty', 'price'} <= fields, fields
    args, _fields = _request_reads(routes[('GET', '/api/stocks/order-board')][0])
    assert args == {'bar', 'supplier', 'only_to_order', 'limit'}, args
    args, _fields = _request_reads(routes[('GET', '/api/taps/taplist-full')][0])
    assert args == {'bar_id', 'active_only', 'compact'}, args
    for path in ('/api/chz/stock', '/api/beers/draft', '/menu/api/items'):
        args, _fields = _request_reads(routes[('GET', path)][0])
        assert args == {'q', 'limit'}, (path, args)


def test_heavy_matches_route_code():
    """heavy = view (сам или через помощника) ходит в iiko, ЧЗ или рендерит PDF."""
    routes = _routes()
    for spec in stocks.TOOLS:
        source = _view_body(routes[(spec.method, spec.path)][0])
        calls_out = any(marker in source for marker in IIKO_MARKERS)
        assert calls_out == spec.heavy, spec.name + ': heavy=' + repr(spec.heavy) + \
            ', а маркеры внешних вызовов в view: ' + repr(calls_out)


# --------------------------------------------------------------------------- тесты: схемы и примеры

def test_examples_pass_schema():
    for spec in stocks.TOOLS:
        for example in spec.examples:
            errors = _schema_errors(spec.input_schema, example)
            assert errors == [], spec.name + ': ' + repr(errors)


def test_examples_policy():
    for spec in stocks.TOOLS:
        if spec.read_only and not spec.heavy:
            assert spec.examples, spec.name + ': у лёгкого чтения нужен пример для дымового теста'
        if not spec.read_only:
            assert not spec.examples, spec.name + ': у записи примеров быть не должно (дымовой прогон)'


def test_bad_args_rejected_by_schema():
    """Схема ловит типичные ошибки агента до вызова маршрута."""
    tools = _tools()
    cases = [
        ('stocks_order_board', {}),
        ('stocks_order_board', {'bar': 'bar2'}),                     # не та система id
        ('stocks_order_board', {'bar': 'Лиговский', 'status': 'critical'}),     # лишнее поле
        ('stocks_order_board', {'bar': 'Лиговский', 'only_to_order': True}),    # флаг — строка '1'
        ('stocks_order_board', {'bar': 'Лиговский', 'limit': 0}),
        ('stocks_order_board', {'bar': 'Лиговский', 'limit': 5000}),
        ('stocks_order_board', {'bar': 'Лиговский', 'supplier': ''}),
        ('stocks_taplist_full', {'compact': True}),
        ('stocks_taplist_full', {'compact': 'yes'}),
        ('stocks_chz_cache', {'limit': 0}),
        ('stocks_chz_cache', {'gtin': '4610093628430'}),
        ('stocks_beers_draft', {'q': ''}),
        ('stocks_menu_items', {'limit': 1001}),
        ('stocks_order_draft_set', {'supplier': 'Май', 'product_id': 'p', 'bar': 'Общая', 'qty': 1}),
        ('stocks_order_draft_set', {'supplier': 'Май', 'product_id': 'p', 'bar': 'Лиговский', 'qty': -1}),
        ('stocks_order_draft_set', {'supplier': 'Май', 'product_id': 'p', 'bar': 'Лиговский', 'qty': 1,
                                    'kind': 'beer'}),
        ('stocks_order_draft_batch', {'items': []}),
        ('stocks_order_send', {'expected_at': '2026-10-01'}),
        ('stocks_orders_list', {'status': 'open'}),
        ('stocks_orders_list', {'days': 400}),
        ('stocks_supplier_upsert', {'name': 'Май', 'lead_time_days': 0}),
        ('stocks_supplier_upsert', {'name': 'Май', 'delivery_weekdays': [7]}),
        ('stocks_supplier_upsert', {'name': 'Май', 'min_order_scope': 'network'}),
        ('stocks_expiration_board', {'bars': 'Лиговский'}),
        ('stocks_expiration_board', {'force': True}),
        ('stocks_taps_bar', {'bar_id': 'Лиговский'}),
        ('stocks_tap_start', {'bar_id': 'bar1', 'tap_number': 3}),
        ('stocks_tap_identify', {'bar_id': 'bar1', 'tap_number': 3, 'iiko_product_id': 'g',
                                 'expected': {'current_beer': 'x'}}),
        ('stocks_taplist_full', {'active_only': True}),
        ('stocks_yml_feed_save', {'feed_id': 'bar1', 'changes': {'x': {'hidden': 'yes'}}}),
        ('stocks_yml_feed_save', {'feed_id': 'bar1', 'changes': {'x': {'colour': 'red'}}}),
        ('stocks_yml_feed_ack', {'feed_id': 'bar1', 'keys': ['nothex']}),
        ('stocks_menu_item_create', {'vols': ['05', '10', '04', '025']}),
        ('stocks_menu_item_create', {'ratings': {'gor': 6}}),
        ('stocks_menu_export_pdf', {'filter': 'taps'}),
        ('stocks_receiving_list', {'status': 'done'}),
        ('stocks_receiving_list', {'limit': 500}),
        ('stocks_receiving_get', {'receipt_id': '12'}),                  # номер — число
        ('stocks_receiving_get', {'receipt_id': 0}),
        ('stocks_receiving_scan', {'receipt_id': 1, 'code': '4610093628430'}),     # нет client_id
        ('stocks_receiving_scan', {'receipt_id': 1, 'code': '4610093628430', 'client_id': 'short'}),
        ('stocks_receiving_scan', {'receipt_id': 1, 'code': '4610093628430',
                                   'client_id': 'abcd-1234-efgh', 'source': 'phone'}),
        ('stocks_receiving_scan', {'receipt_id': 1, 'code': '', 'client_id': 'abcd-1234-efgh'}),
        ('stocks_receiving_scan', {'receipt_id': 1, 'code': 'x' * 513, 'client_id': 'abcd-1234-efgh'}),
        ('stocks_receiving_review', {'status': 'open'}),                 # open — это state
        ('stocks_receiving_review', {'status': 'new,'}),
        ('stocks_receiving_review', {'state': 'done'}),
        ('stocks_receiving_review', {'limit': 1001}),
        ('stocks_receiving_review_update', {'gtin': '4610093628430', 'state': 'done'}),   # 13 цифр
        ('stocks_receiving_review_update', {'gtin': '04610093628430', 'state': 'closed'}),
        ('stocks_receiving_review_update', {'gtin': '04610093628430', 'note': 'x' * 501}),
        ('stocks_receiving_products', {}),
        ('stocks_receiving_products', {'q': 'I'}),
        ('stocks_receiving_products', {'q': 'IPA', 'limit': 101}),
        ('stocks_receiving_invoice_get', {'name': '../receiving.db'}),
        ('stocks_receiving_invoice_upload', {'receipt_id': 1, 'photo': {'content_base64': 'AA=='}}),
    ]
    for name, args in cases:
        assert _fallback_check(tools[name].input_schema, args), name + ': схема пропустила ' + repr(args)


def test_bar_ids_match_code():
    import extensions
    import routes.expiration as rexp
    import routes.stocks as rst
    from core.taplist import BAR_NAMES
    from core.taps_manager import TapsManager
    from core.yml_feeds import FEED_ORDER

    assert tuple(extensions.BARS) == stocks.IIKO_BAR_NAMES
    assert BAR_NAMES == stocks.BAR_ID_TO_NAME
    assert FEED_ORDER == stocks.BAR_IDS
    assert {name: bid for name, bid in rst._BAR_ID_MAP.items() if bid} == stocks.BAR_NAME_TO_ID
    assert rst._BAR_ID_MAP.get(stocks.NETWORK_BAR, 'нет') is None
    assert rexp._BAR_ID_MAP == stocks.BAR_NAME_TO_ID
    assert tuple(rexp._STORE_ID_MAP) == stocks.BAR_IDS
    assert {bid: cfg['taps'] for bid, cfg in TapsManager.BARS_CONFIG.items()} == stocks.TAP_COUNTS

    tools = _tools()
    ru = list(stocks.IIKO_BAR_NAMES) + [stocks.NETWORK_BAR]
    for name in ('stocks_order_board', 'stocks_taplist_stock', 'stocks_bottles_stock',
                 'stocks_kitchen_stock', 'stocks_expiry_stock'):
        assert tools[name].input_schema['properties']['bar']['enum'] == ru, name
    item = tools['stocks_order_draft_set'].input_schema['properties']['bar']
    assert item['enum'] == list(stocks.IIKO_BAR_NAMES)
    for spec in stocks.TOOLS:
        for key in ('bar_id', 'feed_id'):
            node = (spec.input_schema.get('properties') or {}).get(key)
            if node is not None:
                assert node['enum'] == list(stocks.BAR_IDS), spec.name + '.' + key


def _prop(tool, *path):
    node = _tools()[tool].input_schema
    for key in path:
        node = node['items'] if key == '[]' else node['properties'][key]
    return node


def test_constants_match_code():
    import core.order_store as cos
    import core.supplier_directory as csd
    import core.yml_overrides as cyo
    import routes.menu_editor as rme
    import routes.orders as rord
    from core.taps_manager import TapsManager

    assert stocks.ORDER_STATUSES == cos.ALL_STATUSES
    assert stocks.ORDER_ITEM_KINDS == rord.ALLOWED_KINDS
    assert stocks.MAX_ORDER_QTY == cos.MAX_QTY
    assert stocks.MAX_HISTORY_DAYS == rord.MAX_HISTORY_DAYS
    assert (stocks.MIN_LEAD_TIME_DAYS, stocks.MAX_LEAD_TIME_DAYS) == (csd.MIN_LEAD_TIME_DAYS, csd.MAX_LEAD_TIME_DAYS)
    assert stocks.MAX_PACK_SIZE == csd.MAX_PACK_SIZE
    assert stocks.MAX_MIN_ORDER_SUM == csd.MAX_MIN_ORDER_SUM
    assert stocks.MIN_ORDER_SCOPES == csd.MIN_ORDER_SCOPES
    assert stocks.MENU_VOLUMES == tuple(key for key, _label, _field in rme.VOLUMES)
    assert stocks.MENU_MAX_VOLS == rme.MAX_VOLS
    assert (stocks.YML_NAME_LIMIT, stocks.YML_DESCRIPTION_LIMIT) == (cyo.NAME_LIMIT, cyo.DESCRIPTION_LIMIT)
    assert stocks.TAP_HISTORY_MAX == TapsManager.MAX_TAP_HISTORY

    # схемы действительно используют эти значения
    assert _prop('stocks_orders_list', 'days')['maximum'] == rord.MAX_HISTORY_DAYS
    assert _prop('stocks_order_draft_set', 'kind')['enum'] == list(rord.ALLOWED_KINDS)
    assert _prop('stocks_order_draft_set', 'qty')['maximum'] == cos.MAX_QTY
    for status in cos.ALL_STATUSES:
        assert re.fullmatch(_prop('stocks_orders_list', 'status')['pattern'], status), status
    assert _prop('stocks_supplier_upsert', 'min_order_scope')['enum'] == list(csd.MIN_ORDER_SCOPES)
    assert _prop('stocks_supplier_upsert', 'lead_time_days')['maximum'] == csd.MAX_LEAD_TIME_DAYS
    assert _prop('stocks_supplier_upsert', 'note')['maxLength'] == 500
    assert _prop('stocks_menu_item_create', 'vols', '[]')['enum'] == list(stocks.MENU_VOLUMES)
    menu_fields = set(_tools()['stocks_menu_item_create'].input_schema['properties'])
    assert menu_fields == set(rme.ITEM_FIELDS), sorted(menu_fields ^ set(rme.ITEM_FIELDS))
    update_fields = set(_tools()['stocks_menu_item_update'].input_schema['properties']) - {'item_id'}
    assert update_fields == set(rme.ITEM_FIELDS)
    render_fields = set(_tools()['stocks_menu_render_pdf'].input_schema['properties'])
    assert render_fields == set(rme.ITEM_FIELDS)
    override = _prop('stocks_yml_feed_save', 'changes')['additionalProperties']['properties']
    assert set(cyo.FIELDS) <= set(override), sorted(set(cyo.FIELDS) - set(override))
    supplier_fields = set(_tools()['stocks_supplier_upsert'].input_schema['properties']) - {'name', 'rename_to'}
    import routes.suppliers as rsup
    assert supplier_fields == set(rsup.EDITABLE_FIELDS), sorted(supplier_fields ^ set(rsup.EDITABLE_FIELDS))


def test_narrowing_params_match_routes():
    """Сужение больших ответов для агентов (2026-09-28): предел limit и флаги — те же, что в
    маршрутах; флаги строкой '1'/'0' (маршруты сравнивают строго с '1')."""
    import routes.menu_editor as rme
    import routes.stocks as rst
    import routes.taps as rtaps
    assert stocks.LIST_LIMIT_MAX == rst.LIST_LIMIT_MAX == rtaps.LIST_LIMIT_MAX == rme.LIST_LIMIT_MAX
    for name in ('stocks_order_board', 'stocks_chz_cache', 'stocks_beers_draft', 'stocks_menu_items'):
        node = _prop(name, 'limit')
        assert (node['minimum'], node['maximum']) == (1, stocks.LIST_LIMIT_MAX), name
        assert 'limit' in _tools()[name].query_params, name
    for name in ('stocks_chz_cache', 'stocks_beers_draft', 'stocks_menu_items'):
        assert _prop(name, 'q')['minLength'] == 1 and 'q' in _tools()[name].query_params, name
    assert _prop('stocks_taplist_full', 'compact')['enum'] == ['1', '0']
    assert _prop('stocks_order_board', 'only_to_order')['enum'] == ['1', '0']
    assert _tools()['stocks_order_board'].query_params == ('bar', 'supplier', 'only_to_order', 'limit')
    assert rtaps.COMPACT_MAIN_PORTION == '0.5'
    row = {'bar': 'Лиговский', 'bar_id': 'bar2', 'tap_number': 3, 'beer_name': 'Пилс', 'brewery': 'Б',
           'style': 'Pilsner', 'abv': 4.8, 'ibu': 30, 'mapped': True, 'mapping_status': 'verified',
           'price_status': 'verified', 'description': 'x' * 500, 'photo_url': 'https://img',
           'servings': [{'portion_liters': '0.3', 'price_rub': '220.00', 'dish_name': 'Пилс 0,3'},
                        {'portion_liters': '0.5', 'price_rub': '330.00', 'dish_name': 'Пилс 0,5'}]}
    compact = rtaps.compact_tap_row(row)
    assert set(compact) == {'bar', 'bar_id', 'tap_number', 'beer_name', 'brewery', 'style', 'abv', 'ibu',
                            'mapped', 'mapping_status', 'price_status', 'price_0_5', 'prices'}
    assert compact['price_0_5'] == '330.00'
    assert compact['prices'] == [{'l': '0.3', 'rub': '220.00'}, {'l': '0.5', 'rub': '330.00'}]
    two_prices = dict(row, servings=row['servings'] + [{'portion_liters': '0.5', 'price_rub': '390.00'}])
    assert rtaps.compact_tap_row(two_prices)['price_0_5'] is None, 'две цены 0,5 л — не выбираем за владельца'
    assert rtaps.compact_tap_row(dict(row, servings=[]))['price_0_5'] is None


def test_receiving_constants_match_code():
    """Приёмка на РЦ: перечни и пределы схем — те же, что в маршрутах и хранилище."""
    import core.receiving_codes as rcodes
    import core.receiving_photo_store as rphotos
    import core.receiving_store as rstore
    import routes.receiving as rr

    assert stocks.RECEIPT_FILTERS == rr.RECEIPT_FILTERS
    assert stocks.RECEIPTS_LIMIT_MAX == rr.RECEIPTS_LIMIT_MAX
    assert stocks.RECEIVING_NOTE_LIMIT == rr.NOTE_LIMIT == rstore.NOTE_LIMIT
    assert stocks.RECEIVING_CODE_MAX == rcodes.MAX_CODE_LEN
    assert stocks.SCAN_SOURCES == rr.SCAN_SOURCES == rstore.SOURCES
    assert stocks.SCAN_CLIENT_TIME_LIMIT == rr.CLIENT_TIME_LIMIT == rstore.CLIENT_TIME_LIMIT
    assert stocks.REVIEW_STATES == rr.REVIEW_STATES == rstore.LIST_STATES
    assert stocks.REVIEW_STATUSES == rr.REVIEW_STATUSES == rstore.STATUSES
    assert stocks.REVIEW_USER_STATES == rr.REVIEW_USER_STATES == rstore.USER_STATES
    assert stocks.REVIEW_LIMIT_MAX == rr.REVIEW_LIMIT_MAX == rstore.LIST_LIMIT_MAX
    assert (stocks.PRODUCTS_MIN_Q, stocks.PRODUCTS_LIMIT_MAX) == (rr.PRODUCTS_MIN_Q, rr.PRODUCTS_LIMIT_MAX)
    assert stocks.SEARCH_Q_MAX == rr.SEARCH_Q_MAX
    assert stocks.INVOICE_MAX_MB * 1024 * 1024 == rphotos.MAX_PHOTO_BYTES
    assert int('9' * 9) == stocks.RECEIPT_ID_MAX

    # схемы действительно используют эти значения
    assert _prop('stocks_receiving_list', 'status')['enum'] == list(rr.RECEIPT_FILTERS)
    assert _prop('stocks_receiving_list', 'limit')['maximum'] == rr.RECEIPTS_LIMIT_MAX
    assert _prop('stocks_receiving_scan', 'source')['enum'] == list(rstore.SOURCES)
    assert _prop('stocks_receiving_scan', 'code')['maxLength'] == rcodes.MAX_CODE_LEN
    assert _prop('stocks_receiving_review', 'state')['enum'] == list(rstore.LIST_STATES)
    assert _prop('stocks_receiving_review', 'limit')['maximum'] == rstore.LIST_LIMIT_MAX
    assert _prop('stocks_receiving_review_update', 'state')['enum'] == list(rstore.USER_STATES)
    assert _prop('stocks_receiving_review_update', 'note')['maxLength'] == rstore.NOTE_LIMIT
    assert _prop('stocks_receiving_create', 'note')['maxLength'] == rstore.NOTE_LIMIT
    assert _prop('stocks_receiving_products', 'q')['minLength'] == rr.PRODUCTS_MIN_Q
    assert _prop('stocks_receiving_products', 'limit')['maximum'] == rr.PRODUCTS_LIMIT_MAX
    for status in rstore.STATUSES:
        assert re.fullmatch(_prop('stocks_receiving_review', 'status')['pattern'], status), status
    assert re.fullmatch(_prop('stocks_receiving_review', 'status')['pattern'], 'new,similar,restore')
    # client_id: схема и маршрут пускают одно и то же
    pattern = _prop('stocks_receiving_scan', 'client_id')['pattern']
    for value in ('0f8e7d6c-1a2b-4c3d-9e8f-0123456789ab', 'abcd1234', 'a' * 64):
        assert re.search(pattern, value) and rr.CLIENT_ID_RE.match(value), value
    for value in ('abc', 'a' * 65, 'abc_1234', 'абвгдежз'):
        assert not re.search(pattern, value) and not rr.CLIENT_ID_RE.match(value), value
    # имя фото накладной: схема и хранилище фото согласны
    name_pattern = _prop('stocks_receiving_invoice_get', 'name')['pattern']
    assert _prop('stocks_receiving_invoice_delete', 'name')['pattern'] == name_pattern
    good = rphotos.make_name(12)
    assert re.search(name_pattern, good) and rphotos.is_valid_name(good)
    for bad in ('../r1.jpg', 'r1_20261003T140500_0123abcd.png', 'r1_20261003T140500_0123ABCD.jpg'):
        assert not re.search(name_pattern, bad) and not rphotos.is_valid_name(bad), bad
    upload = _tools()['stocks_receiving_invoice_upload']
    assert upload.file_params == ('photo',) and upload.body == 'multipart'


# --------------------------------------------------------------------------- тесты: пометки

def test_annotations():
    tools = _tools()
    for spec in stocks.TOOLS:
        if spec.method == 'GET':
            assert spec.read_only and not spec.destructive, spec.name
        if spec.method in ('PUT', 'PATCH', 'DELETE'):
            assert not spec.read_only, spec.name
        if spec.method == 'DELETE':
            assert spec.destructive, spec.name
        if spec.read_only:
            assert spec.idempotent, spec.name + ': чтение идемпотентно'
    # единственный POST без изменений данных — рендер PDF из переданных полей
    post_read = {spec.name for spec in stocks.TOOLS if spec.method == 'POST' and spec.read_only}
    assert post_read == {'stocks_menu_render_pdf'}, post_read
    assert {n for n, s in tools.items() if s.destructive} == EXPECTED_DESTRUCTIVE
    assert {n for n, s in tools.items() if s.open_world} == EXPECTED_OPEN_WORLD
    assert {n for n, s in tools.items() if s.heavy} == EXPECTED_HEAVY
    assert {n for n, s in tools.items() if 'content' in s.also_in} == EXPECTED_ALSO_CONTENT
    for name in EXPECTED_ALSO_CONTENT:
        assert tools[name].read_only, name + ': контент-агенту — только чтение'


# --------------------------------------------------------------------------- тесты: тексты

def test_texts_without_emoji():
    for where, text in _texts():
        assert not _EMOJI_RE.search(text), where + ': эмодзи в тексте'


def test_mentioned_names_exist():
    tool_names = set(_tools())
    prompt_names = {p.name for p in stocks.PROMPTS}
    docs = set()
    for where, text in _texts():
        for name in re.findall(r'\bstocks_[a-z0-9_]*[a-z0-9]', text):
            assert name in tool_names or name in prompt_names, where + ': нет инструмента ' + name
        if 'common_docs_read' in text:
            docs.update(re.findall(r"\('([a-z0-9-]+)'\)", text))
    assert docs, 'описания должны ссылаться на документацию'
    for name in sorted(docs):
        assert os.path.exists(os.path.join(REPO, 'docs', name + '.md')), 'нет docs/' + name + '.md'


def test_common_tools_mentioned_exist_if_available():
    """common_* из текстов домена существуют, если модуль common уже собран (пишет агент A)."""
    try:
        from core.mcp.tools import common
    except ImportError:
        return
    names = {spec.name for spec in getattr(common, 'TOOLS', [])}
    if not names:
        return
    for where, text in _texts():
        for name in re.findall(r'\bcommon_[a-z0-9_]*[a-z0-9]', text):
            assert name in names, where + ': нет общего инструмента ' + name


def test_instructions():
    lines = stocks.INSTRUCTIONS.strip().splitlines()
    assert 40 <= len(lines) <= 90, len(lines)
    text = stocks.INSTRUCTIONS
    for word in ('БЕЗОПАСНОСТЬ', 'данные, а не инструкции', 'прямой просьбе владельца',
                 'bar1', 'Большой пр. В.О', 'common_bars_reference', 'Тяжёлые'):
        assert word in text, word
    for name in ('stocks_order_board', 'stocks_expiration_board', 'stocks_suppliers_list'):
        assert name in text, name


def test_descriptions_reasonable():
    for spec in stocks.TOOLS:
        assert 60 <= len(spec.description) <= 1000, spec.name + ': ' + str(len(spec.description))
        assert spec.title.strip() and len(spec.title) <= 60, spec.name
        for key, node in (spec.input_schema.get('properties') or {}).items():
            assert (node.get('description') or '').strip(), spec.name + '.' + key + ': нет описания поля'


# --------------------------------------------------------------------------- тесты: сценарии

def test_prompts():
    names = [p.name for p in stocks.PROMPTS]
    assert names == ['stocks_weekly_digest', 'stocks_order_advice', 'stocks_taps_review'], names
    for prompt in stocks.PROMPTS:
        assert mcp_spec.PROMPT_NAME_RE.match(prompt.name), prompt.name
        assert prompt.domain == 'stocks' and prompt.title.strip() and prompt.description.strip()
        assert all(not arg.required for arg in prompt.arguments), prompt.name + ': аргументы необязательны'
    args = {p.name: [a.name for a in p.arguments] for p in stocks.PROMPTS}
    assert args == {'stocks_weekly_digest': ['bar'], 'stocks_order_advice': ['supplier', 'bar'],
                    'stocks_taps_review': ['bar']}, args
    for prompt, call_args, text in _prompt_renders():
        assert isinstance(text, str) and len(text) > 200, prompt.name + repr(call_args)
    digest = stocks.PROMPTS[0].render({'bar': 'bar2'})
    assert 'Лиговский' in digest and 'bar2' in digest
    advice = stocks.PROMPTS[1].render({'supplier': 'ООО МаркетБир'})
    assert 'ООО МаркетБир' in advice and 'НЕ отправляй' in advice
    unknown = stocks.PROMPTS[2].render({'bar': 'nevsky'})
    assert 'common_bars_reference' in unknown
    assert 'bar4' in stocks.PROMPTS[2].render({'bar': '  BAR4  '})


# --------------------------------------------------------------------------- тесты: Python 3.10

def test_module_has_no_fstrings():
    """CI гоняет Python 3.10: f-строк (и PEP 701) в модуле описаний нет вовсе."""
    path = os.path.join(REPO, 'core', 'mcp', 'tools', 'stocks.py')
    with open(path, encoding='utf-8') as handle:
        source = handle.read()
    fstring_start = getattr(tokenize, 'FSTRING_START', None)
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if fstring_start is not None and tok.type == fstring_start:
            raise AssertionError('f-строка в строке ' + str(tok.start[0]))
        if tok.type == tokenize.STRING:
            prefix = re.match(r'^[A-Za-z]*', tok.string).group(0).lower()
            assert 'f' not in prefix, 'f-строка в строке ' + str(tok.start[0])


if __name__ == '__main__':
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith('test_') and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as error:  # noqa: BLE001 — самозапуск печатает все падения
            failed += 1
            print('FAIL ' + name + ': ' + type(error).__name__ + ': ' + str(error)[:500])
        else:
            print('ok   ' + name)
    print(str(len(tests) - failed) + '/' + str(len(tests)) + ' passed')
    sys.exit(1 if failed else 0)
