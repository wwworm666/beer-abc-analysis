"""
Тесты описаний MCP-инструментов домена analytics (core/mcp/tools/analytics.py).

Самозапуск: `py -3 tests/test_mcp_tools_analytics.py`; pytest:
`py -3 -m pytest -q tests/test_mcp_tools_analytics.py`.

Приложение — голый Flask со ВСЕМИ blueprint'ами сервиса (routes.register_blueprints),
как видит прод; app.py не импортируется (он запускает шедулеры и Telegram с боевыми
токенами). Маршруты НЕ вызываются: нужны только url_map и исходники view-функций,
поэтому ни iiko, ни файлы данных тест не трогает.

Что проверяется (контракт сборки MCP, раздел 5, и решения core/mcp/tools/analytics.py):
- validate_tool_spec пуст; имена уникальны, с префиксом analytics_, домен analytics;
- каждый (метод, путь) есть в url_map, метод разрешён, view — из routes/dashboard.py,
  routes/analysis.py, routes/explorer.py или routes/guests.py; path_params совпадают
  с аргументами правила Flask;
- все API-маршруты этих файлов покрыты ровно одним инструментом (или стоят в EXCLUDED);
  HTML-страницы (/explorer, /guests) в охват не входят;
- query- и body-аргументы действительно читает модуль маршрута (опечатка в схеме
  иначе стала бы молча игнорируемым аргументом); поля плана = PlansManager.PLAN_SCHEMA;
- heavy совпадает с тем, ходит ли view в iiko (маркеры в исходнике view);
- examples проходят проверку схемы (core/mcp/schema_check.py плюс своя минимальная);
  типичные ошибки агента схема отбивает (чужая система идентификаторов бара, запись
  в «все заведения», месячный ключ плана вместо ключа комментария);
- константы описаний совпадают с кодом: ключи и имена баров, id карточек дашборда,
  ленивые секции, конструктор отчётов, поля плана, типы периода «Маркетинга», пороги
  ABC/XYZ и RFM, упомянутые в текстах;
- пометки: зафиксированные наборы записи, destructive, open_world, heavy, also_in;
  примеры есть у всех лёгких чтений и нет у записи;
- тексты: без эмодзи; упомянутые analytics_* / common_* и документы docs/*.md
  существуют; INSTRUCTIONS 40..90 строк с правилами безопасности;
- сценарии: имена, аргументы, render на пустых, верных и кривых аргументах;
- модуль и этот тест совместимы с Python 3.10: f-строк в модуле описаний нет.
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
from core.mcp.tools import analytics  # noqa: E402

OWN_MODULES = ('routes.dashboard', 'routes.analysis', 'routes.explorer', 'routes.guests')
ROUTE_METHODS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')

# Зафиксированные пометки (решение по коду маршрутов, см. докстринг analytics.py).
EXPECTED_HEAVY = {
    'analytics_dashboard', 'analytics_dashboard_card_details', 'analytics_revenue_metrics',
    'analytics_widget_revenue', 'analytics_monthly_report', 'analytics_monthly_loyalty',
    'analytics_monthly_draft_liters', 'analytics_monthly_top_guests', 'analytics_export_excel',
    'analytics_export_pdf', 'analytics_packaging', 'analytics_kitchen', 'analytics_draft_kegs',
    'analytics_draft_analyze', 'analytics_discounts', 'analytics_explorer_pivot',
    'analytics_guests_sync',
}
# Запись: имя -> (destructive, idempotent, open_world).
EXPECTED_WRITES = {
    'analytics_plan_save': (False, True, False),
    'analytics_plan_delete': (True, True, False),
    'analytics_daily_plan_set_weight': (False, True, False),
    'analytics_daily_plan_reset_weight': (True, True, False),
    'analytics_comment_save': (False, True, False),
    'analytics_guests_sync': (False, False, True),
}
# RFM (каждый гость с телефоном) контент-агенту не открыт — проверка безопасности 2026-09-28.
EXPECTED_ALSO_CONTENT = {'analytics_guests_summary'}
# Контракт: staff видит дневные планы (от них считаются премии) и чтение планов для KPI;
# правка и удаление месячного плана остаются только в analytics.
EXPECTED_ALSO_STAFF = {
    'analytics_plan_get', 'analytics_plan_calculate', 'analytics_daily_plan_get',
    'analytics_daily_plan_set_weight', 'analytics_daily_plan_reset_weight',
}
# Признаки того, что view в момент вызова может пойти в iiko (прямо или через загрузчик).
IIKO_MARKERS = (
    'OlapReports(', 'load_dashboard_sales(', 'load_draft_kegs(', 'load_packaging(',
    'load_kitchen(', 'build_pivot(', 'get_dashboard_analytics_data(', '_maybe_refresh(',
    'start_background_sync(',
)
# Разумные аргументы тяжёлых и пишущих инструментов: в examples их нет (дымовой прогон
# не должен ходить в iiko и менять данные), но схема обязана их принимать.
SAMPLE_ARGS = {
    'analytics_dashboard': {'bar': 'ligovskiy', 'date_from': '2026-09-01', 'date_to': '2026-09-07'},
    'analytics_dashboard_card_details': {'venue_key': 'all', 'date_from': '2026-09-01',
                                         'date_to': '2026-09-07', 'metric': 'revenueDraft',
                                         'section': 'draft_liters'},
    'analytics_revenue_metrics': {'bar': '', 'date_from': '2026-09-01', 'date_to': '2026-09-26',
                                  'period_from': '2026-09-01', 'period_to': '2026-09-30'},
    'analytics_widget_revenue': {},
    'analytics_monthly_report': {'venue': 'bolshoy', 'years': '2026', 'force': '1'},
    'analytics_export_excel': {'bar': 'all', 'date_from': '2026-09-01', 'date_to': '2026-09-07'},
    'analytics_export_pdf': {'bar': 'varshavskaya', 'date_from': '2026-09-01',
                             'date_to': '2026-09-07'},
    'analytics_packaging': {'bar': 'Лиговский', 'date_from': '2026-08-21', 'date_to': '2026-09-19'},
    'analytics_kitchen': {'bar': '', 'days': 30},
    'analytics_draft_kegs': {'bar': 'Большой пр. В.О', 'date_from': '2026-09-01',
                             'date_to': '2026-09-26'},
    'analytics_draft_analyze': {'bar': 'Кременчугская', 'days': 14},
    'analytics_discounts': {'bar': '', 'date_from': '2026-09-01', 'date_to': '2026-09-26'},
    'analytics_explorer_pivot': {'date_from': '2026-09-01', 'date_to': '2026-09-26',
                                 'venue': 'all', 'granularity': 'week', 'group_by': 'dish_name',
                                 'top_category': 'kitchen', 'metric': 'revenue'},
    'analytics_plan_save': {
        'venue_key': 'bolshoy', 'period_key': '2026-10', 'revenue': 1600000, 'checks': 1000,
        'averageCheck': 1600, 'draftShare': 62, 'packagedShare': 20, 'kitchenShare': 18,
        'revenueDraft': 992000, 'revenuePackaged': 320000, 'revenueKitchen': 288000,
        'markupPercent': 200, 'profit': 1066666.67, 'markupDraft': 250, 'markupPackaged': 120,
        'markupKitchen': 180, 'loyaltyWriteoffs': 80000, 'tapActivity': 100,
        'cardChecksShare': 70,
    },
    'analytics_plan_delete': {'venue_key': 'ligovskiy', 'period_key': '2026-10'},
    'analytics_daily_plan_set_weight': {'venue_key': 'kremenchugskaya', 'year': 2026,
                                        'month': 12, 'date': '2026-12-31', 'weight': 0},
    'analytics_daily_plan_reset_weight': {'venue_key': 'kremenchugskaya', 'year': 2026,
                                          'month': 12, 'date_str': '2026-12-31'},
    'analytics_comment_save': {'venue_key': 'all', 'period_key': '2026-09-14_2026-09-20',
                               'comment': 'Выручка выше плана за счёт пятницы.'},
    'analytics_guests_sync': {'force': '1'},
}
# Типичные ошибки агента, которые схема обязана отбить: (инструмент, аргументы, почему).
BAD_ARGS = [
    ('analytics_dashboard', {'bar': 'Лиговский', 'date_from': '2026-09-01',
                             'date_to': '2026-09-07'},
     'русское имя вместо ключа: маршрут молча посчитал бы всю сеть'),
    ('analytics_dashboard', {'venue_key': 'all', 'date_from': '2026-09-01',
                             'date_to': '2026-09-07'},
     'поле venue_key у дашборда не читается — бар передаётся полем bar'),
    ('analytics_dashboard', {'bar': 'all', 'date_from': '01.09.2026', 'date_to': '2026-09-07'},
     'дата не в формате YYYY-MM-DD'),
    ('analytics_dashboard', {'bar': 'all', 'date_from': '2026-09-01'}, 'нет date_to'),
    ('analytics_dashboard_card_details', {'date_from': '2026-09-01', 'date_to': '2026-09-07',
                                          'metric': 'cardChecks'},
     'cardChecks — вкладка карточки cardChecksShare, а не карточка'),
    ('analytics_packaging', {'bar': 'ligovskiy', 'days': 30},
     'ключ заведения вместо русского имени iiko: ответ «Нет данных»'),
    ('analytics_discounts', {'bar': 'Лиговский'}, 'даты обязательны'),
    ('analytics_plan_save', dict(SAMPLE_ARGS['analytics_plan_save'], venue_key='all'),
     '«все заведения» — сумма баров, отдельно не планируется'),
    ('analytics_plan_save', dict(SAMPLE_ARGS['analytics_plan_save'], period_key='2026-9'),
     'ключ плана только YYYY-MM'),
    ('analytics_plan_save', dict(SAMPLE_ARGS['analytics_plan_save'], checks=1000.5),
     'checks — целое: иначе 400 от сервиса'),
    ('analytics_plan_save', {k: v for k, v in SAMPLE_ARGS['analytics_plan_save'].items()
                             if k != 'revenue'},
     'план заменяется целиком — без revenue сервис отвечает 400'),
    ('analytics_plan_save', dict(SAMPLE_ARGS['analytics_plan_save'], cardChecksShare=120),
     'доля чеков с картой — процент 0..100'),
    ('analytics_plan_delete', {'venue_key': 'all', 'period_key': '2026-10'},
     'агрегат не удаляется'),
    ('analytics_daily_plan_set_weight', dict(SAMPLE_ARGS['analytics_daily_plan_set_weight'],
                                             weight=-1),
     'вес дня не бывает отрицательным'),
    ('analytics_daily_plan_set_weight', dict(SAMPLE_ARGS['analytics_daily_plan_set_weight'],
                                             venue_key='all'),
     'агрегат all не редактируется'),
    ('analytics_comment_save', dict(SAMPLE_ARGS['analytics_comment_save'],
                                    period_key='bolshoy_2026-09'),
     'месячный ключ плана вписал бы комментарий внутрь боевого плана'),
    ('analytics_comment_save', dict(SAMPLE_ARGS['analytics_comment_save'], period_key='2026-09'),
     'ключ комментария — только период YYYY-MM-DD_YYYY-MM-DD'),
    ('analytics_guests_rfm', {'store': 'all'}, 'точка RFM — физический бар, сеть = без store'),
    ('analytics_guests_rfm', {'period_type': 'day'}, 'такого типа периода нет (молча был бы месяц)'),
    ('analytics_explorer_pivot', {'date_from': '2026-09-01', 'date_to': '2026-09-07'},
     'venue обязателен'),
    ('analytics_explorer_pivot', {'date_from': '2026-09-01', 'date_to': '2026-09-07',
                                  'venue': 'all', 'metric': 'checks'},
     'в MVP только revenue'),
    ('analytics_monthly_report', {'years': '2026;2025'}, 'годы — через запятую'),
    ('analytics_guests_search', {'q': '7'}, 'меньше 2 символов маршрут не ищет'),
    ('analytics_plan_get', {'venue_key': 'bolshoy'}, 'параметр пути обязателен'),
]

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


def _own_routes():
    """API-маршруты своих файлов: {(метод, правило)}. Страницы HTML в охват не входят."""
    pairs = set()
    for (method, path), rules in _routes().items():
        if path.startswith('/api/') and any(_view_module(rule) in OWN_MODULES for rule in rules):
            pairs.add((method, path))
    return pairs


def _tools():
    return {spec.name: spec for spec in analytics.TOOLS}


def _rule_of(spec):
    rules = _routes().get((spec.method, spec.path)) or []
    assert rules, spec.name + ': нет маршрута ' + spec.method + ' ' + spec.path
    return rules[0]


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
    """Минимальная проверка по JSON Schema (подмножество, которым пользуется модуль)."""
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
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            errors.append(where + ': не подходит под pattern')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 'minimum' in schema and value < schema['minimum']:
            errors.append(where + ': меньше minimum')
        if 'maximum' in schema and value > schema['maximum']:
            errors.append(where + ': больше maximum')
    if isinstance(value, list) and 'items' in schema:
        for index, item in enumerate(value):
            errors += _fallback_check(schema['items'], item, where + '[' + str(index) + ']')
    if isinstance(value, dict):
        props = schema.get('properties') or {}
        for key in schema.get('required') or []:
            if key not in value:
                errors.append(where + ': нет обязательного ' + key)
        for key, item in value.items():
            if key in props:
                errors += _fallback_check(props[key], item, where + '.' + key)
            elif schema.get('additionalProperties') is False:
                errors.append(where + ': лишнее поле ' + key)
    return errors


def _schema_errors(schema, args):
    """Ошибки аргументов: своя проверка плюс core/mcp/schema_check.py, если он уже есть."""
    errors = _fallback_check(schema, args)
    try:
        from core.mcp import schema_check
    except ImportError:
        return errors
    fn = getattr(schema_check, 'check', None)
    if callable(fn):
        errors += [str(e) for e in fn(schema, args)]
    return errors


def _has_schema_check():
    try:
        from core.mcp import schema_check  # noqa: F401
    except ImportError:
        return False
    return True


# --------------------------------------------------------------------------- тексты

_EMOJI_RE = re.compile('[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]')

_PROMPT_SAMPLES = (
    {}, {'month': '2026-08', 'bar': 'ligovskiy'}, {'month': '2026-8', 'bar': 'Лиговский'},
    {'month': 'август', 'bar': 'nevsky'}, {'month': '2099-01'}, {'bar': None, 'month': 17},
    {'week_start': '2026-09-16', 'bar': ' ВО '}, {'week_start': 'вчера'},
    {'period': '2026-08'}, {'period': '2026-09-01..2026-09-26'}, {'period': 'неделя'},
    {'period': '2026-09-26 — 2026-09-01'},
)


def _prompt_renders():
    for prompt in analytics.PROMPTS:
        for args in _PROMPT_SAMPLES:
            yield prompt, args, prompt.render(args)


def _schema_descriptions(node, where):
    """Все description внутри схемы: (где, текст)."""
    out = []
    if isinstance(node, dict):
        if isinstance(node.get('description'), str):
            out.append((where, node['description']))
        for key, sub in (node.get('properties') or {}).items():
            out += _schema_descriptions(sub, where + '.' + key)
        if isinstance(node.get('items'), dict):
            out += _schema_descriptions(node['items'], where + '[]')
    return out


def _texts():
    """Всё, что видит агент: (где, текст)."""
    out = [('INSTRUCTIONS', analytics.INSTRUCTIONS)]
    for spec in analytics.TOOLS:
        out.append((spec.name + '.title', spec.title))
        out.append((spec.name + '.description', spec.description))
        out += _schema_descriptions(spec.input_schema, spec.name + '.schema')
    for prompt in analytics.PROMPTS:
        out.append((prompt.name + '.title', prompt.title))
        out.append((prompt.name + '.description', prompt.description))
        for arg in prompt.arguments:
            out.append((prompt.name + '.' + arg.name, arg.description))
    for prompt, args, text in _prompt_renders():
        out.append((prompt.name + '.render' + repr(args), text))
    return out


# --------------------------------------------------------------------------- тесты: описания

def test_specs_valid():
    problems = [error for spec in analytics.TOOLS for error in mcp_spec.validate_tool_spec(spec)]
    assert not problems, problems


def test_names_unique_prefixed():
    names = [spec.name for spec in analytics.TOOLS]
    assert len(names) == len(set(names)), 'повтор имени'
    for spec in analytics.TOOLS:
        assert spec.domain == 'analytics', spec.name
        assert spec.name.startswith('analytics_'), spec.name
        assert spec.route_backed, spec.name + ': у домена нет инструментов без маршрута'
    prompt_names = [prompt.name for prompt in analytics.PROMPTS]
    assert len(prompt_names) == len(set(prompt_names))
    assert not set(prompt_names) & set(names), 'имя сценария совпадает с инструментом'


def test_exports():
    assert isinstance(analytics.TOOLS, list) and analytics.TOOLS
    assert isinstance(analytics.PROMPTS, list) and analytics.PROMPTS
    assert isinstance(analytics.INSTRUCTIONS, str) and analytics.INSTRUCTIONS.strip()
    assert isinstance(analytics.EXCLUDED, dict)
    for (method, path), reason in analytics.EXCLUDED.items():
        assert method in ROUTE_METHODS and path.startswith('/'), (method, path)
        assert isinstance(reason, str) and len(reason) > 10, (method, path)
    for spec in analytics.TOOLS:
        assert isinstance(spec, mcp_spec.ToolSpec)
    for prompt in analytics.PROMPTS:
        assert isinstance(prompt, mcp_spec.PromptSpec) and prompt.domain == 'analytics'


def test_routes_exist_and_params_match():
    for spec in analytics.TOOLS:
        rule = _rule_of(spec)
        assert spec.method in rule.methods, spec.name
        assert _view_module(rule) in OWN_MODULES, spec.name + ': маршрут чужого файла ' + \
            _view_module(rule)
        assert set(spec.path_params) == set(rule.arguments), spec.name
        assert spec.path.startswith('/api/'), spec.name


def test_all_own_routes_covered_once():
    covered = {}
    for spec in analytics.TOOLS:
        key = (spec.method, spec.path)
        assert key not in covered, 'маршрут описан дважды: ' + repr(key)
        covered[key] = spec.name
    own = _own_routes()
    missing = sorted(key for key in own if key not in covered and key not in analytics.EXCLUDED)
    assert not missing, 'не покрыты: ' + repr(missing)
    stale = sorted(key for key in analytics.EXCLUDED if key not in own)
    assert not stale, 'EXCLUDED ссылается на несуществующее: ' + repr(stale)
    both = sorted(key for key in analytics.EXCLUDED if key in covered)
    assert not both, 'и описан, и исключён: ' + repr(both)
    assert len(analytics.TOOLS) == len(own) - len(analytics.EXCLUDED)


def _field_read(source, field):
    return ("'" + field + "'") in source or ('"' + field + '"') in source


def test_arguments_are_read_by_route():
    """Каждый аргумент вне пути читается модулем маршрута (или helper'ом: _ctx, _maybe_refresh)."""
    from core.plans_manager import PlansManager
    for spec in analytics.TOOLS:
        rule = _rule_of(spec)
        source = _module_source(rule)
        props = set(spec.input_schema.get('properties', {}))
        for field in sorted(props - set(spec.path_params)):
            if spec.name == 'analytics_plan_save':
                # Тело целиком уходит в plans_manager.save_plan: схема = PLAN_SCHEMA.
                assert field in PlansManager.PLAN_SCHEMA, field
                continue
            assert _field_read(source, field), spec.name + ': маршрут не читает поле ' + field
        for field in spec.query_params:
            assert ('args.get(' in source), spec.name
            assert _field_read(source, field), spec.name + ': нет request.args ' + field


def test_plan_save_schema_matches_plans_manager():
    from core.plans_manager import PlansManager
    spec = _tools()['analytics_plan_save']
    props = spec.input_schema['properties']
    body = set(props) - set(spec.path_params)
    assert body == set(PlansManager.PLAN_SCHEMA), sorted(body ^ set(PlansManager.PLAN_SCHEMA))
    required = set(spec.input_schema['required']) - set(spec.path_params)
    assert required == set(PlansManager.PLAN_SCHEMA) - set(PlansManager.PLAN_DEFAULTS)
    assert props['checks']['type'] == 'integer'      # PLAN_SCHEMA: checks — только int
    assert props['cardChecksShare']['maximum'] == 100
    assert set(analytics.PLAN_OPTIONAL_FIELDS) == set(PlansManager.PLAN_DEFAULTS)


def test_heavy_matches_route_code():
    for spec in analytics.TOOLS:
        body = _view_body(_rule_of(spec))
        touches_iiko = any(marker in body for marker in IIKO_MARKERS)
        assert touches_iiko == spec.heavy, spec.name + ': heavy=' + str(spec.heavy) + \
            ', а маркеры iiko в коде: ' + str(touches_iiko)


def test_examples_pass_schema():
    for spec in analytics.TOOLS:
        for example in spec.examples:
            errors = _schema_errors(spec.input_schema, example)
            assert not errors, spec.name + ': ' + repr(errors)
    for name, args in SAMPLE_ARGS.items():
        errors = _schema_errors(_tools()[name].input_schema, args)
        assert not errors, name + ': ' + repr(errors)


def test_examples_policy():
    for spec in analytics.TOOLS:
        if spec.read_only and not spec.heavy:
            assert spec.examples, spec.name + ': лёгкому чтению нужен пример для дымового прогона'
        if not spec.read_only:
            assert not spec.examples, spec.name + ': у записи примеров быть не должно'
        for example in spec.examples:
            # Примеры тяжёлых инструментов (месячный отчёт) не должны включать пересчёт в iiko.
            assert 'force' not in example and 'full' not in example, spec.name


def test_bad_args_rejected_by_schema():
    tools = _tools()
    for name, args, why in BAD_ARGS:
        errors = _schema_errors(tools[name].input_schema, args)
        assert errors, name + ' принял ' + repr(args) + ' (' + why + ')'
    if _has_schema_check():
        # format=date: несуществующая дата отбивается, а не уходит в strptime маршрута.
        errors = _schema_errors(tools['analytics_dashboard'].input_schema,
                                {'date_from': '2026-02-30', 'date_to': '2026-03-01'})
        assert errors


# --------------------------------------------------------------------------- тесты: константы

def _prop(tool, *path):
    node = _tools()[tool].input_schema
    for key in path:
        node = node['properties'][key]
    return node


def test_bar_ids_match_code():
    import extensions
    from core import venues_config
    assert analytics.VENUE_KEYS == tuple(venues_config.PHYSICAL_VENUES)
    assert set(analytics.VENUE_KEYS_ALL) == set(venues_config.VENUES)
    assert analytics.IIKO_BAR_NAMES == tuple(extensions.BARS)
    expected_pairs = {k: v for k, v in venues_config.KEY_TO_IIKO_NAME.items() if k != 'all'}
    assert dict(zip(analytics.VENUE_KEYS, analytics.IIKO_BAR_NAMES)) == expected_pairs
    # Где ждут ключ заведения, а где русское имя iiko.
    for tool, field in (('analytics_dashboard', 'bar'), ('analytics_revenue_metrics', 'bar'),
                        ('analytics_dashboard_card_details', 'venue_key'),
                        ('analytics_explorer_pivot', 'venue'), ('analytics_monthly_report', 'venue'),
                        ('analytics_plan_get', 'venue_key'), ('analytics_export_excel', 'bar')):
        values = set(_prop(tool, field)['enum']) - {''}
        assert values == set(venues_config.VENUES), tool
    for tool in ('analytics_packaging', 'analytics_kitchen', 'analytics_draft_kegs',
                 'analytics_draft_analyze', 'analytics_discounts'):
        assert set(_prop(tool, 'bar')['enum']) == set(extensions.BARS) | {''}, tool
    for tool in ('analytics_plan_save', 'analytics_plan_delete', 'analytics_daily_plan_set_weight',
                 'analytics_daily_plan_reset_weight'):
        assert set(_prop(tool, 'venue_key')['enum']) == set(venues_config.PHYSICAL_VENUES), tool
    assert set(_prop('analytics_guests_rfm', 'store')['enum']) == set(venues_config.PHYSICAL_VENUES)


def test_constants_match_code():
    from core import abc_thresholds, day_weights, dashboard_details, explorer, guest_analytics
    from core import monthly_report
    assert analytics.DASHBOARD_METRIC_IDS == tuple(dashboard_details.METRIC_IDS)
    assert analytics.CARD_LAZY_SECTIONS == tuple(dashboard_details.LAZY_SECTIONS)
    assert set(analytics.EXPLORER_GRANULARITIES) == set(explorer.GRANULARITIES)
    assert set(analytics.EXPLORER_GROUP_BY) == set(explorer.GROUP_BY_FIELD)
    assert set(analytics.EXPLORER_TOP_CATEGORIES) == set(explorer.TOP_CATEGORY_FILTERS)
    for period_type in analytics.GUEST_PERIOD_TYPES:
        assert guest_analytics.resolve_period(period_type, '2026-08-15')['type'] == period_type
    # Неизвестный тип молча становится месяцем — поэтому в схеме enum.
    assert guest_analytics.resolve_period('day', '2026-08-15')['type'] == 'month'
    # Числа, которые тексты называют агенту, совпадают с константами кода.
    texts = {spec.name: spec.description for spec in analytics.TOOLS}
    text_all = analytics.INSTRUCTIONS + '\n'.join(texts.values())
    pairs = ((abc_thresholds.MARKUP_A_MIN, abc_thresholds.MARKUP_B_MIN, 'analytics_packaging'),
             (abc_thresholds.KITCHEN_MARKUP_A_MIN, abc_thresholds.KITCHEN_MARKUP_B_MIN,
              'analytics_kitchen'),
             (abc_thresholds.KEG_MARKUP_A_MIN, abc_thresholds.KEG_MARKUP_B_MIN,
              'analytics_draft_kegs'))
    for a_min, b_min, tool in pairs:
        a_pct, b_pct = str(int(round(a_min * 100))), str(int(round(b_min * 100)))
        assert 'A ≥ ' + a_pct + '%' in texts[tool] and 'B ≥ ' + b_pct + '%' in texts[tool], tool
        assert a_pct + '/' + b_pct + '%' in analytics.INSTRUCTIONS, tool
    assert (abc_thresholds.PARETO_A_MAX_CUM_PERCENT, abc_thresholds.PARETO_B_MAX_CUM_PERCENT) == \
        (80.0, 95.0) and 'Парето 80/95' in text_all
    assert (abc_thresholds.XYZ_X_MAX_CV, abc_thresholds.XYZ_Y_MAX_CV) == (30.0, 60.0)
    assert 'X ≤ 30%' in analytics.INSTRUCTIONS and 'Y ≤ 60%' in analytics.INSTRUCTIONS
    assert abc_thresholds.MIN_XYZ_WEEKS == 3 and 'меньше 3 недель' in analytics.INSTRUCTIONS
    rfm = texts['analytics_guests_rfm']
    assert '/'.join(str(x) for x in guest_analytics.RFM_R_THRESHOLDS) in rfm
    assert '/'.join(str(x) for x in guest_analytics.RFM_F_THRESHOLDS) in rfm
    assert str(guest_analytics.RFM_WINDOW_DAYS) + ' дней' in rfm
    activity = [(lo, hi) for _name, lo, hi in guest_analytics.ACTIVITY_SEGMENTS]
    assert activity == [(0, 30), (31, 90), (91, 180), (181, None)]
    assert 'active ≤ 30' in texts['analytics_guests_activity']
    windows = '/'.join(str(x) for x in guest_analytics.RETENTION_WINDOWS)
    assert windows in texts['analytics_guests_retention']
    assert monthly_report.TOP_STYLES == 8 and 'топ-8' in texts['analytics_monthly_draft_liters']
    assert (day_weights.WEEKDAY_WEIGHT, day_weights.WEEKEND_WEIGHT) == (1.0, 2.0)
    assert 'пт/сб = 2' in analytics.INSTRUCTIONS


# --------------------------------------------------------------------------- тесты: пометки

def test_annotations():
    tools = _tools()
    writes = {name for name, spec in tools.items() if not spec.read_only}
    assert writes == set(EXPECTED_WRITES), sorted(writes ^ set(EXPECTED_WRITES))
    for name, (destructive, idempotent, open_world) in EXPECTED_WRITES.items():
        spec = tools[name]
        assert (spec.destructive, spec.idempotent, spec.open_world) == \
            (destructive, idempotent, open_world), name
    for name, spec in tools.items():
        if spec.method == 'GET':
            assert spec.read_only, name
        if spec.read_only:
            assert not spec.destructive and not spec.open_world, name
    heavy = {name for name, spec in tools.items() if spec.heavy}
    assert heavy == EXPECTED_HEAVY, sorted(heavy ^ EXPECTED_HEAVY)
    content = {name for name, spec in tools.items() if 'content' in spec.also_in}
    assert content == EXPECTED_ALSO_CONTENT, sorted(content ^ EXPECTED_ALSO_CONTENT)
    staff = {name for name, spec in tools.items() if 'staff' in spec.also_in}
    assert staff == EXPECTED_ALSO_STAFF, sorted(staff ^ EXPECTED_ALSO_STAFF)
    for spec in analytics.TOOLS:
        assert spec.annotations()['readOnlyHint'] is spec.read_only


def test_write_descriptions_warn():
    """Запись говорит, что меняет, и что только по прямой просьбе владельца."""
    for name in EXPECTED_WRITES:
        text = _tools()[name].description
        assert 'по прямой просьбе владельца' in text, name
        assert re.match(r'^(ЗАПИСЬ|УДАЛЕНИЕ|ЗАПУСК)', text), name


def test_query_flags_are_strings():
    """force/full и export — строки: маршрут сравнивает с '1'/'csv', булево дало бы 'True'."""
    for spec in analytics.TOOLS:
        for field in ('force', 'full', 'export'):
            node = spec.input_schema.get('properties', {}).get(field)
            if node is not None:
                assert node.get('type') == 'string' and node.get('enum'), spec.name + '.' + field


# --------------------------------------------------------------------------- тесты: тексты

def test_texts_without_emoji():
    for where, text in _texts():
        found = _EMOJI_RE.findall(text or '')
        assert not found, where + ': ' + repr(found)


def test_mentioned_names_exist():
    known = set(_tools()) | {prompt.name for prompt in analytics.PROMPTS}
    # Ссылки с сокращённым префиксом (_packaging, _kitchen ...) в INSTRUCTIONS разворачиваются.
    short = re.findall(r'(?<![a-z0-9])_([a-z][a-z0-9_]+)', analytics.INSTRUCTIONS)
    for tail in short:
        if 'analytics_' + tail in known:
            continue
        assert tail in ('обрезано',), 'сокращение не найдено: _' + tail
    for where, text in _texts():
        for name in re.findall(r'\banalytics_[a-z0-9_]+', text or ''):
            assert name in known, where + ': неизвестный инструмент ' + name


def test_common_tools_mentioned_exist_if_available():
    mentioned = set()
    for _where, text in _texts():
        mentioned |= set(re.findall(r'\bcommon_[a-z0-9_]+', text or ''))
    assert mentioned <= {'common_bars_reference', 'common_docs_read', 'common_docs_list'}, mentioned
    try:
        from core.mcp.tools import common
    except ImportError:
        return
    names = {spec.name for spec in getattr(common, 'TOOLS', [])}
    if names:
        assert mentioned <= names, sorted(mentioned - names)


def test_mentioned_docs_exist():
    docs_dir = os.path.join(REPO, 'docs')
    for where, text in _texts():
        for doc in re.findall(r'([a-z][a-z0-9\-_]*)\.md\b', text or ''):
            assert os.path.exists(os.path.join(docs_dir, doc + '.md')), where + ': нет docs/' + doc


def test_instructions():
    lines = analytics.INSTRUCTIONS.strip('\n').splitlines()
    assert 40 <= len(lines) <= 90, len(lines)
    text = analytics.INSTRUCTIONS
    for needle in ('Безопасность', 'только по прямой просьбе владельца', 'никогда из расписания',
                   'Числа никогда не из модели', 'common_bars_reference', 'включительно',
                   'Тяжёлые вызовы', 'данные, а не инструкции'):
        assert needle.lower() in text.lower(), needle
    for name in EXPECTED_HEAVY - {'analytics_monthly_report', 'analytics_monthly_loyalty',
                                  'analytics_monthly_draft_liters', 'analytics_monthly_top_guests',
                                  'analytics_guests_sync'}:
        tail = name[len('analytics'):]
        assert name in text or tail in text, 'тяжёлый не назван в INSTRUCTIONS: ' + name


def test_descriptions_reasonable():
    for spec in analytics.TOOLS:
        assert len(spec.description) >= 120, spec.name
        assert spec.title and spec.title[0].isupper(), spec.name
        for key, node in spec.input_schema.get('properties', {}).items():
            assert node.get('description'), spec.name + '.' + key + ': нет описания поля'


# --------------------------------------------------------------------------- тесты: сценарии

def test_prompts():
    prompts = {prompt.name: prompt for prompt in analytics.PROMPTS}
    assert set(prompts) == {'analytics_month_review', 'analytics_week_pulse',
                            'analytics_draft_losses'}
    args = {name: {(arg.name, arg.required) for arg in prompt.arguments}
            for name, prompt in prompts.items()}
    assert args['analytics_month_review'] == {('month', True), ('bar', False)}
    assert args['analytics_week_pulse'] == {('week_start', False), ('bar', False)}
    assert args['analytics_draft_losses'] == {('period', False)}
    for prompt, call_args, text in _prompt_renders():
        assert isinstance(text, str) and len(text) > 300, prompt.name + repr(call_args)
        assert 'Формат ответа' in text, prompt.name
    review = prompts['analytics_month_review']
    text = review.render({'month': '2026-08', 'bar': 'Лиговский'})
    assert 'date_from=2026-08-01' in text and 'date_to=2026-08-31' in text
    assert 'bar=ligovskiy' in text and 'years=2026,2025' in text
    assert 'не в формате' in review.render({'month': 'август'})
    assert 'common_bars_reference' in review.render({'month': '2026-08', 'bar': 'nevsky'})
    assert 'ещё не начался' in review.render({'month': '2099-01'})
    pulse = prompts['analytics_week_pulse'].render({'week_start': '2026-09-16', 'bar': 'во'})
    assert 'date_from=2026-09-14' in pulse and 'date_to=2026-09-20' in pulse
    assert 'bar=bolshoy' in pulse and 'date_from=2026-09-07' in pulse
    losses = prompts['analytics_draft_losses']
    text = losses.render({'period': '2026-09-01..2026-09-26'})
    assert 'date_from=2026-09-01' in text and 'date_to=2026-09-26' in text
    assert 'не распознан' in losses.render({'period': 'неделя'})
    assert 'date_to=2026-08-31' in losses.render({'period': '2026-08'})


# --------------------------------------------------------------------------- тесты: Python 3.10

def test_module_has_no_fstrings():
    """CI гоняет Python 3.10: f-строк (и PEP 701) в модуле описаний нет вовсе."""
    path = os.path.join(REPO, 'core', 'mcp', 'tools', 'analytics.py')
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
            print('FAIL ' + name + ': ' + type(error).__name__ + ': ' + str(error)[:600])
        else:
            print('ok   ' + name)
    print(str(len(tests) - failed) + '/' + str(len(tests)) + ' passed')
    sys.exit(1 if failed else 0)
