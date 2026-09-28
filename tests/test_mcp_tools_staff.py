# -*- coding: utf-8 -*-
"""
Тесты описаний MCP-инструментов домена staff (core/mcp/tools/staff.py).

Запуск:
    py -3 -m pytest tests/test_mcp_tools_staff.py -q
    py -3 tests/test_mcp_tools_staff.py              # без pytest

Что защищают (контракт MCP-платформы, раздел 5):

1. validate_tool_spec пуст у каждого описания; имена уникальны и начинаются с «staff_».
2. Каждый (method, path) есть в url_map голого Flask со ВСЕМИ blueprint'ами сервиса
   (routes.register_blueprints — то же видит прод), метод разрешён, маршрут принадлежит
   файлам домена; path_params равны аргументам правила, а тип схемы совпадает с
   конвертером (<int:...> -> integer, остальное -> string).
3. Покрытие: каждый API-маршрут файлов домена (/api/* и /schedule/cal.ics) описан ровно
   одним инструментом или стоит в EXCLUDED с причиной; исключения указывают на
   существующие маршруты этих файлов и не пересекаются с инструментами.
4. examples проходят проверку схемы (core/mcp/schema_check.py, когда он есть, плюс своя
   минимальная проверка), у каждого read_only и не heavy инструмента пример есть.
5. Пометка heavy совпадает с тем, ходит ли view-функция в iiko (по её исходнику).
6. Имена аргументов действительно читает маршрут: литерал в исходнике view-функции или в
   явно названном модуле, который разбирает payload дальше.
7. Сознательные решения по пометкам (read_only у POST-расчётов, destructive, open_world)
   зафиксированы списками — их изменение должно быть осознанным.
8. Сценарии рендерятся, инструкции 40..90 строк, эмодзи нет нигде.

Сеть и iiko не трогаются: проверяются описания и карта маршрутов, запросов нет.
"""

import inspect
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Импорт routes поднимает менеджеры данных (extensions). Направляем постоянное
# хранилище во временный каталог, чтобы тест не трогал data/ репозитория.
os.environ.setdefault('PERSISTENT_DATA_DIR', tempfile.mkdtemp(prefix='mcp_staff_test_'))
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from core.mcp.spec import (HTTP_METHODS, TOOL_NAME_RE, PromptSpec, ToolSpec,  # noqa: E402
                           validate_tool_spec)
from core.mcp.tools import staff  # noqa: E402

# Blueprint'ы файлов домена (routes/<файл>.py -> имя blueprint'а).
OWN_BLUEPRINTS = {'employee', 'salary', 'schedule', 'me', 'cleanliness', 'temperature',
                  'open_check', 'auth'}
# Маршруты данных вне /api/, которые тоже входят в охват MCP (контракт, раздел 4.9).
NON_API_DATA_ROUTES = {'/feeds/taplist.yml', '/feeds/kitchen.yml', '/feeds/kitchen/<bar_id>',
                       '/schedule/cal.ics'}

ACCESS_REASON = 'управление доступом остаётся только в интерфейсе'
BOT_REASON = 'инфраструктура бота'

# Признаки похода в iiko в исходнике view-функции (прямо или через общий загрузчик).
HEAVY_MARKERS = ('IikoAPI(', 'OlapReports(', 'load_dashboard_sales(', '_month_inputs(',
                 'sync_once(', 'run_check(', 'start_background_refresh(')

# POST-маршруты, которые только считают и ничего не пишут.
READ_ONLY_POST = {
    'staff_employee_analytics', 'staff_employee_compare', 'staff_employee_discount_checks',
    'staff_employee_metrics_breakdown', 'staff_bonus_calculate', 'staff_kpi_calculate',
    'staff_salary_export_xlsx',
}
DESTRUCTIVE = {
    'staff_kpi_targets_save', 'staff_salary_handover_penalty', 'staff_salary_export_gsheet',
    'staff_salary_sync_gsheet', 'staff_schedule_employees_sync',
    'staff_schedule_cash_register_set', 'staff_schedule_shift_delete',
    'staff_schedule_dayoff_delete', 'staff_schedule_wish_save', 'staff_meeting_note_save',
    'staff_open_check_run_now',
}
OPEN_WORLD = {
    'staff_salary_export_gsheet', 'staff_salary_sync_gsheet', 'staff_schedule_employees_sync',
    'staff_schedule_revenue_sync_day', 'staff_schedule_revenue_sync_month', 'staff_me_refresh',
    'staff_open_check_run_now',
}

# Аргументы, которые маршрут передаёт дальше целиком: их имена читает указанный модуль.
DOWNSTREAM = {
    'staff_kpi_targets_save': ('core/kpi_calculator.py',),
    'staff_salary_export_xlsx': ('core/salary_layout.py', 'core/salary_export.py'),
    'staff_salary_export_gsheet': ('core/salary_layout.py', 'core/salary_export.py'),
    'staff_schedule_shift_update': ('core/shifts_manager.py',),
}

EMOJI_RE = re.compile('[\U0001F000-\U0001FFFF☀-➿⬀-⯿️]')

_APP = None


def _app():
    """Голый Flask со всеми blueprint'ами сервиса (без app.py и его шедулеров)."""
    global _APP
    if _APP is None:
        from flask import Flask
        import routes
        app = Flask('mcp_staff_tools_test')
        routes.register_blueprints(app)
        _APP = app
    return _APP


def _rules_by_path():
    out = {}
    for rule in _app().url_map.iter_rules():
        out.setdefault(rule.rule, []).append(rule)
    return out


def _rule_for(spec):
    """Правило Flask с тем же путём, у которого разрешён метод инструмента."""
    for rule in _rules_by_path().get(spec.path, []):
        if spec.method in rule.methods:
            return rule
    return None


def _source(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as f:
        return f.read()


def _view_source(rule):
    return inspect.getsource(_app().view_functions[rule.endpoint])


def _tools():
    return list(staff.TOOLS)


# ---------------------------------------------------------------- минимальная проверка схемы

def _type_ok(value, type_name):
    if type_name == 'object':
        return isinstance(value, dict)
    if type_name == 'array':
        return isinstance(value, list)
    if type_name == 'string':
        return isinstance(value, str)
    if type_name == 'integer':
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == 'number':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == 'boolean':
        return isinstance(value, bool)
    if type_name == 'null':
        return value is None
    return False


def _check_value(schema, value, where):
    """Подмножество JSON Schema, которое используют описания домена."""
    errors = []
    types = schema.get('type')
    if types is not None:
        type_list = types if isinstance(types, list) else [types]
        if not any(_type_ok(value, t) for t in type_list):
            return ['%s: тип %s не из %s' % (where, type(value).__name__, type_list)]
    if 'enum' in schema and value not in schema['enum']:
        errors.append('%s: %r не из %r' % (where, value, schema['enum']))
    if isinstance(value, str):
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            errors.append('%s: %r не подходит под %s' % (where, value, schema['pattern']))
        if 'minLength' in schema and len(value) < schema['minLength']:
            errors.append('%s: короче %s' % (where, schema['minLength']))
        if 'maxLength' in schema and len(value) > schema['maxLength']:
            errors.append('%s: длиннее %s' % (where, schema['maxLength']))
    if _type_ok(value, 'number'):
        if 'minimum' in schema and value < schema['minimum']:
            errors.append('%s: меньше %s' % (where, schema['minimum']))
        if 'maximum' in schema and value > schema['maximum']:
            errors.append('%s: больше %s' % (where, schema['maximum']))
    if isinstance(value, dict):
        props = schema.get('properties') or {}
        for key in schema.get('required') or []:
            if key not in value:
                errors.append('%s: нет обязательного %s' % (where, key))
        extra = schema.get('additionalProperties', True)
        for key, sub in value.items():
            if key in props:
                errors.extend(_check_value(props[key], sub, where + '.' + key))
            elif extra is False:
                errors.append('%s: лишнее поле %s' % (where, key))
            elif isinstance(extra, dict):
                errors.extend(_check_value(extra, sub, where + '.' + key))
    if isinstance(value, list):
        if 'minItems' in schema and len(value) < schema['minItems']:
            errors.append('%s: меньше %s элементов' % (where, schema['minItems']))
        if isinstance(schema.get('items'), dict):
            for i, item in enumerate(value):
                errors.extend(_check_value(schema['items'], item, '%s[%d]' % (where, i)))
    return errors


def _external_errors(spec, args):
    """Проверка тем же валидатором, что протокол применяет к tools/call.

    core/mcp/schema_check.py: validate_arguments(schema, args, tool_name) -> None | текст
    ошибки для агента. None от этой функции-обёртки — модуля ещё нет (сборка шла
    параллельно); тогда работает только своя проверка _check_value.
    """
    try:
        from core.mcp import schema_check
    except ImportError:
        return None
    message = schema_check.validate_arguments(spec.input_schema, args, spec.name)
    return [message] if message else []


# ================================================================ тесты

def test_specs_are_valid():
    errors = [e for spec in _tools() for e in validate_tool_spec(spec)]
    assert errors == [], errors


def test_exports_have_expected_types():
    assert isinstance(staff.TOOLS, list) and all(isinstance(t, ToolSpec) for t in staff.TOOLS)
    assert isinstance(staff.PROMPTS, list) and all(isinstance(p, PromptSpec)
                                                   for p in staff.PROMPTS)
    assert isinstance(staff.INSTRUCTIONS, str)
    assert isinstance(staff.EXCLUDED, dict)


def test_names_unique_and_prefixed():
    names = [t.name for t in _tools()]
    dups = sorted({n for n in names if names.count(n) > 1})
    assert dups == [], dups
    for spec in _tools():
        assert spec.domain == 'staff', spec.name
        assert spec.name.startswith('staff_'), spec.name
        assert TOOL_NAME_RE.match(spec.name), spec.name
        assert spec.route_backed, spec.name + ': инструменты домена — только маршруты'


def test_one_tool_per_route_and_method():
    keys = [(t.method, t.path) for t in _tools()]
    dups = sorted({k for k in keys if keys.count(k) > 1})
    assert dups == [], dups


def test_routes_exist_methods_allowed_and_own():
    for spec in _tools():
        rule = _rule_for(spec)
        assert rule is not None, '%s: нет маршрута %s %s' % (spec.name, spec.method, spec.path)
        blueprint = rule.endpoint.split('.', 1)[0]
        assert blueprint in OWN_BLUEPRINTS, '%s: маршрут чужого файла (%s)' % (spec.name,
                                                                             rule.endpoint)


def test_path_params_match_rule_arguments_and_types():
    for spec in _tools():
        rule = _rule_for(spec)
        assert set(spec.path_params) == set(rule.arguments), spec.name
        converters = dict(rule._converters)
        props = spec.input_schema['properties']
        for param in spec.path_params:
            conv = type(converters[param]).__name__
            want = 'integer' if conv == 'IntegerConverter' else 'string'
            assert props[param].get('type') == want, '%s.%s: %s' % (spec.name, param, conv)
            assert param in spec.input_schema.get('required', []), spec.name


def test_all_own_routes_covered_or_excluded():
    covered = {(t.method, t.path) for t in _tools()}
    excluded = set(staff.EXCLUDED)
    assert not (covered & excluded), sorted(covered & excluded)
    missing = []
    for rule in _app().url_map.iter_rules():
        blueprint = rule.endpoint.split('.', 1)[0]
        if blueprint not in OWN_BLUEPRINTS:
            continue
        if not (rule.rule.startswith('/api/') or rule.rule in NON_API_DATA_ROUTES):
            continue
        for method in sorted(set(rule.methods) & set(HTTP_METHODS)):
            if (method, rule.rule) not in covered and (method, rule.rule) not in excluded:
                missing.append((method, rule.rule))
    assert missing == [], missing


def test_excluded_point_to_own_routes_with_reasons():
    by_path = _rules_by_path()
    for (method, path), reason in staff.EXCLUDED.items():
        assert method in HTTP_METHODS, (method, path)
        rules = [r for r in by_path.get(path, []) if method in r.methods]
        assert rules, 'исключение без маршрута: %s %s' % (method, path)
        assert rules[0].endpoint.split('.', 1)[0] in OWN_BLUEPRINTS, (method, path)
        assert isinstance(reason, str) and len(reason.strip()) >= 10, (method, path)
        if path.startswith('/api/auth/'):
            assert reason.startswith(ACCESS_REASON), (method, path)
        if path.startswith('/telegram/'):
            assert reason.startswith(BOT_REASON), (method, path)


def test_access_management_is_excluded_not_exposed():
    """Создание/удаление аккаунтов, пароли, флаги админа и активности — не для агента."""
    exposed = {(t.method, t.path) for t in _tools()}
    for key in (('POST', '/api/auth/users'),
                ('POST', '/api/auth/users/<int:user_id>/password'),
                ('POST', '/api/auth/users/<int:user_id>/active'),
                ('POST', '/api/auth/users/<int:user_id>/admin'),
                ('DELETE', '/api/auth/users/<int:user_id>')):
        assert key in staff.EXCLUDED and key not in exposed, key


def test_examples_pass_schema():
    for spec in _tools():
        for args in spec.examples:
            errors = _check_value(spec.input_schema, args, spec.name)
            assert errors == [], errors
            external = _external_errors(spec, args)
            assert not external, '%s: %s' % (spec.name, external)


def test_schemas_reject_dangerous_or_wrong_arguments():
    """Ужесточения схем против маршрута (см. докстроку staff.py) действительно работают."""
    by_name = {t.name: t for t in _tools()}
    bad = [
        # касса без трат/инкассации стёрла бы прежние значения — поля обязательны
        ('staff_schedule_shift_cash', {'shift_id': 1, 'cash_end': 1000}),
        ('staff_schedule_cash_register_set', {'shift_id': 1, 'cash_end': 1000,
                                              'penalize': True}),
        # пустое тело маршрут понял бы как «очистить факт»
        ('staff_schedule_shift_fact', {'shift_id': 1}),
        ('staff_schedule_shift_fact', {'shift_id': 1, 'fact_minutes': 1441}),
        # без penalized маршрут снял бы штраф
        ('staff_salary_handover_penalty', {'date': '2026-09-01', 'employee_name': 'А Б'}),
        ('staff_employee_analytics', {'employee_name': 'А Б', 'date_from': '2026-09-01',
                                      'date_to': '2026-09-30', 'bar': 'bolshoy'}),
        ('staff_employee_compare', {'employee_names': ['А Б'], 'date_from': '2026-09-01',
                                    'date_to': '2026-09-30'}),
        ('staff_schedule_shift_create', {'date': '2026-09-01', 'employee_name': 'А Б',
                                         'location_id': 1, 'role_id': 1,
                                         'start_time': '25:00'}),
        ('staff_kpi_dishes', {'refresh': True}),
        ('staff_schedule_month', {'year': 2026, 'month': 13}),
        ('staff_salary_export_gsheet', {'month': '2026-09', 'employees': [{'name': 'А'}]}),
        ('staff_schedule_roles', {'unexpected': 1}),
    ]
    for name, args in bad:
        spec = by_name[name]
        assert _check_value(spec.input_schema, args, name), (name, args)
        external = _external_errors(spec, args)
        if external is not None:
            assert external, ('schema_check пропустил', name, args)
    good = ('staff_schedule_shift_cash', {'shift_id': 1, 'cash_expense': 0,
                                          'cash_expense_note': None, 'cash_collection': None,
                                          'cash_end': '15 340,25'})
    assert _check_value(by_name[good[0]].input_schema, good[1], good[0]) == []
    assert not _external_errors(by_name[good[0]], good[1])


def test_read_only_light_tools_have_examples():
    for spec in _tools():
        if spec.read_only and not spec.heavy:
            assert spec.examples, spec.name + ': нужен пример для дымового прогона'
        if spec.heavy or spec.open_world or not spec.read_only:
            # Примеры для тяжёлых и пишущих не заводим: их не должен запускать ни один
            # дымовой прогон, даже чужой.
            assert not spec.examples, spec.name


def test_heavy_matches_iiko_usage():
    for spec in _tools():
        src = _view_source(_rule_for(spec))
        hits = [m for m in HEAVY_MARKERS if m in src]
        if hits:
            assert spec.heavy, '%s ходит в iiko (%s), а heavy=False' % (spec.name, hits)
        else:
            assert not spec.heavy, '%s: heavy=True, но view в iiko не ходит' % spec.name


def test_argument_names_are_read_by_route():
    for spec in _tools():
        src = _view_source(_rule_for(spec))
        downstream = ''.join(_source(p) for p in DOWNSTREAM.get(spec.name, ()))
        names = [k for k in spec.input_schema['properties'] if k not in spec.path_params]
        for name in names:
            literal = ("'%s'" % name, '"%s"' % name)
            found = any(x in src for x in literal) or any(x in downstream for x in literal)
            assert found, '%s: маршрут не читает поле %s' % (spec.name, name)


def test_salary_payload_fields_match_export_contract():
    """Поля сотрудника в payload экспорта — из контракта core/salary_export.py."""
    contract = _source('core/salary_export.py') + _source('core/salary_layout.py')
    spec = next(t for t in _tools() if t.name == 'staff_salary_export_xlsx')
    item = spec.input_schema['properties']['employees']['items']
    for name in item['properties']:
        assert '"%s"' % name in contract or "'%s'" % name in contract, name


def test_query_and_body_routing():
    for spec in _tools():
        if spec.method == 'GET':
            assert spec.body == 'none', spec.name
        if spec.body == 'json':
            assert not spec.query_params, spec.name + ': тело JSON, строка запроса не читается'
        if spec.file_params:
            assert spec.body == 'multipart', spec.name
            for param in spec.file_params:
                node = spec.input_schema['properties'][param]
                assert node['type'] == 'object'
                assert 'content_base64' in node['properties'], spec.name


def test_annotation_decisions():
    by_name = {t.name: t for t in _tools()}
    read_only_post = {t.name for t in _tools() if t.method != 'GET' and t.read_only}
    assert read_only_post == READ_ONLY_POST, sorted(read_only_post ^ READ_ONLY_POST)
    destructive = {t.name for t in _tools() if t.destructive}
    assert destructive == DESTRUCTIVE, sorted(destructive ^ DESTRUCTIVE)
    open_world = {t.name for t in _tools() if t.open_world}
    assert open_world == OPEN_WORLD, sorted(open_world ^ OPEN_WORLD)
    for spec in _tools():
        if spec.method == 'DELETE':
            assert spec.destructive, spec.name
        if spec.read_only:
            assert spec.idempotent, spec.name + ': чтение повторять безопасно'
    for name in ('staff_open_check_run_now', 'staff_salary_sync_gsheet'):
        assert by_name[name].heavy and by_name[name].open_world, name


def test_texts_are_russian_and_mention_units_or_sources():
    for spec in _tools():
        assert re.search('[А-Яа-яЁё]', spec.title), spec.name
        assert re.search('[А-Яа-яЁё]', spec.description), spec.name
        assert len(spec.description) <= 1100, spec.name + ': описание слишком длинное'
        for key, node in spec.input_schema['properties'].items():
            assert node.get('description'), '%s.%s: нет описания аргумента' % (spec.name, key)


def test_payroll_tools_point_to_formulas():
    by_name = {t.name: t for t in _tools()}
    for name in ('staff_bonus_calculate', 'staff_employee_analytics', 'staff_me',
                 'staff_salary_export_xlsx'):
        assert 'common_docs_read(' in by_name[name].description, name
    assert 'календарный месяц' in by_name['staff_kpi_calculate'].description
    assert 'common_bars_reference' in by_name['staff_schedule_locations'].description


def test_staff_me_employee_param_matches_route():
    """Кабинет сотрудника для администратора (2026-09-28): параметр и шаблон id — как у маршрута
    routes/me.py (не админу маршрут отвечает 403, это проверяет tests/test_me_routes.py)."""
    import routes.me as rme
    spec = next(t for t in _tools() if t.name == 'staff_me')
    assert spec.query_params == ('month', 'employee_iiko_id')
    node = spec.input_schema['properties']['employee_iiko_id']
    assert node['pattern'] == staff.EMPLOYEE_ID_PATTERN == rme.EMPLOYEE_ID_RE.pattern
    assert "request.args.get('employee_iiko_id')" in _view_source(_rule_for(spec))
    assert not _check_value(spec.input_schema, {'employee_iiko_id': '0b7c9a1e-5f3d-4c2a-9e8b-1d2f3a4b5c6d'}, 'ok')
    for bad in ('с пробелом и кириллицей', 'x' * 65, ''):
        assert _check_value(spec.input_schema, {'employee_iiko_id': bad}, 'bad'), bad


def test_schemas_serialize_to_json():
    for spec in _tools():
        text = json.dumps({'inputSchema': spec.input_schema,
                           'annotations': spec.annotations()}, ensure_ascii=False)
        assert json.loads(text)['inputSchema']['type'] == 'object'


def test_no_emojis_anywhere():
    chunks = [staff.INSTRUCTIONS]
    for spec in _tools():
        chunks += [spec.title, spec.description, json.dumps(spec.input_schema,
                                                             ensure_ascii=False)]
    for prompt in staff.PROMPTS:
        chunks += [prompt.title, prompt.description,
                   prompt.render({'month': '2026-09', 'employee': 'Роман Юреня'}),
                   prompt.render({})]
        chunks += [a.description for a in prompt.arguments]
    chunks += list(staff.EXCLUDED.values())
    chunks.append(_source('core/mcp/tools/staff.py'))
    for text in chunks:
        assert not EMOJI_RE.search(text), text[:120]


def test_instructions_size_and_rules():
    lines = staff.INSTRUCTIONS.split('\n')
    assert 40 <= len(lines) <= 90, len(lines)
    text = staff.INSTRUCTIONS
    for needle in ('ПРАВИЛА БЕЗОПАСНОСТИ', 'КАЛЕНДАРНЫЙ МЕСЯЦ', 'common_bars_reference',
                   'common_docs_read("employee")', 'staff_schedule_audit', 'iiko_id',
                   'только владельцу', 'прямо не'):
        assert needle in text, needle
    names = {t.name for t in _tools()}
    # Имя инструмента целиком (не часть шаблона «staff_employee_*») должно существовать.
    for spec_name in re.findall(r'staff_[a-z_]+(?![a-z_*])', text):
        assert spec_name in names, spec_name
    prefixes = re.findall(r'(staff_[a-z_]+)\*', text)
    for prefix in prefixes:
        assert any(n.startswith(prefix) for n in names), prefix


def test_instructions_name_every_heavy_tool():
    """Пометка heavy до клиента не доходит (в annotations MCP её нет) — агент узнаёт о
    тяжёлых вызовах только из инструкций, поэтому каждый должен быть назван."""
    text = staff.INSTRUCTIONS
    prefixes = re.findall(r'(staff_[a-z_]+)\*', text)
    for spec in _tools():
        if not spec.heavy:
            continue
        named = re.search(re.escape(spec.name) + r'(?![a-z_])', text) is not None
        wildcard = any(spec.name.startswith(p) for p in prefixes)
        sync = '_sync' in spec.name and 'все синхронизации' in text
        assert named or wildcard or sync, spec.name


def test_prompts_render():
    names = [p.name for p in staff.PROMPTS]
    assert names == ['staff_payroll_check', 'staff_employee_review', 'staff_schedule_gaps']
    by_name = {p.name: p for p in staff.PROMPTS}
    for prompt in staff.PROMPTS:
        assert prompt.domain == 'staff' and TOOL_NAME_RE.match(prompt.name), prompt.name
        assert prompt.title and len(prompt.description) >= 20, prompt.name
        for args in ({}, {'month': '2026-09', 'employee': 'Роман Юреня'}):
            text = prompt.render(args)
            assert isinstance(text, str) and len(text) > 200, prompt.name
            for tool_name in re.findall(r'staff_[a-z_]+', text):
                assert tool_name in {t.name for t in _tools()}, (prompt.name, tool_name)
    required = {p.name: {a.name: a.required for a in p.arguments} for p in staff.PROMPTS}
    assert required['staff_payroll_check'] == {'month': True}
    assert required['staff_employee_review'] == {'employee': True, 'month': False}
    assert required['staff_schedule_gaps'] == {'month': False}
    assert '2026-09' in by_name['staff_payroll_check'].render({'month': '2026-09'})
    review = by_name['staff_employee_review'].render({'employee': 'Роман Юреня'})
    assert 'Роман Юреня' in review
    assert 'уточни у владельца' in by_name['staff_employee_review'].render({})


if __name__ == '__main__':
    import traceback

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and inspect.isfunction(f)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print('  ok  ' + name)
            passed += 1
        except Exception as e:  # noqa: BLE001 — самозапуск без pytest печатает всё
            failed += 1
            print('FAIL  ' + name + ': ' + repr(e))
            traceback.print_exc()
    print('\n%d passed, %d failed' % (passed, failed))
    sys.exit(1 if failed else 0)
