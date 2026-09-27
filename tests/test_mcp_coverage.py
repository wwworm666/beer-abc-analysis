"""
Охват MCP (core/mcp/coverage.py, контракт 4.9): всё API сайта доступно агенту или
сознательно исключено с причиной.

Совместим с pytest и запускается сам: `py -3 tests/test_mcp_coverage.py`
(подробный отчёт: `py -3 -m core.mcp.coverage`).

Приложение — голый Flask со ВСЕМИ blueprint'ами сервиса (routes.register_blueprints +
mcp + mcp_oauth), тот же набор маршрутов, что на проде. Новый API-маршрут без
инструмента и без записи в EXCLUDED роняет test_every_api_route_covered_or_excluded —
в тексте падения перечислены пары (метод, правило), сгруппированные по файлам маршрутов,
чтобы было видно, чей это раздел.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SESSION_COOKIE_SECURE'] = '0'

from core.mcp import coverage, registry  # noqa: E402

_CACHE = {}


def _report():
    """Отчёт строится один раз на прогон (сборка приложения со всеми маршрутами небыстрая)."""
    if 'report' not in _CACHE:
        registry.use_modules(None)          # настоящие модули core.mcp.tools.*, свежая загрузка
        app = coverage.build_full_app()
        _CACHE['app'] = app
        _CACHE['report'] = coverage.check(app)
    return _CACHE['report']


def test_every_api_route_covered_or_excluded():
    report = _report()
    assert report.required, 'охват пуст — приложение собралось без маршрутов?'
    assert not report.uncovered, report.format_uncovered()


def test_registry_loaded_without_errors():
    report = _report()
    assert not report.load_errors, 'Ошибки загрузки реестра (инструмент не опубликован):\n' + \
        '\n'.join(report.load_errors)
    assert set(registry.loaded_modules()) == {'common', 'content', 'stocks', 'analytics', 'staff'}, \
        registry.loaded_modules()


def test_tools_point_to_existing_routes():
    report = _report()
    problems = report.dangling_tools + report.path_param_errors
    assert not problems, 'Инструменты ссылаются на несуществующие маршруты или методы:\n' + '\n'.join(problems)


def test_each_pair_has_exactly_one_tool_and_no_conflicts():
    report = _report()
    lines = [f'{m} {r}: {", ".join(tools)}' for (m, r), tools in sorted(report.duplicates.items())]
    assert not lines, 'Одна пара (метод, правило) описана несколькими инструментами:\n' + '\n'.join(lines)
    assert not report.conflicts, 'Пара и описана инструментом, и исключена:\n' + '\n'.join(report.conflicts)


def test_exclusions_point_to_existing_routes():
    report = _report()
    assert not report.dangling_exclusions, 'Исключения без маршрута:\n' + '\n'.join(report.dangling_exclusions)
    for key, reason in registry.exclusions().items():
        assert len(reason.strip()) >= 10, f'{key}: слишком короткая причина исключения «{reason}»'


def test_examples_pass_schema_check():
    report = _report()
    assert not report.example_errors, 'Примеры не проходят схему:\n' + '\n'.join(report.example_errors)


def test_tool_names_unique_and_read_only_tools_have_examples():
    _report()
    names = [t.name for t in registry.all_tools()]
    assert len(names) == len(set(names))
    missing = [t.name for t in registry.all_tools()
               if t.read_only and not t.heavy and not t.examples and t.route_backed]
    assert not missing, 'read_only и не heavy без examples (нужны для дымового прогона): ' + ', '.join(missing)


def test_access_management_is_not_exposed():
    report = _report()
    exclusions = registry.exclusions()
    admin_pairs = [pair for pair in report.required if pair[1].startswith('/api/admin/mcp')]
    assert len(admin_pairs) == 8, admin_pairs
    for pair in admin_pairs:
        assert pair in exclusions and 'доступом к себе' in exclusions[pair], pair
    tool_paths = {t.path for t in registry.all_tools() if t.route_backed}
    assert not any(p.startswith('/api/admin/mcp') or p.startswith('/mcp') or p.startswith('/oauth')
                   for p in tool_paths), 'инструмент ведёт на управление доступом или на сам MCP'


def test_public_endpoints_for_mcp():
    from core.auth_guard import PUBLIC_ENDPOINTS
    report = _report()
    app = _CACHE['app']
    expected = {'mcp.mcp_all', 'mcp.mcp_domain', 'mcp_oauth.protected_resource_metadata',
                'mcp_oauth.authorization_server_metadata', 'mcp_oauth.register_client', 'mcp_oauth.token',
                'mcp_oauth.revoke'}
    assert expected <= PUBLIC_ENDPOINTS
    assert 'mcp_oauth.authorize' not in PUBLIC_ENDPOINTS, 'согласие OAuth требует входа в сайт'
    assert not any(e.startswith('mcp.admin') for e in PUBLIC_ENDPOINTS)
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert {'mcp.mcp_all', 'mcp.mcp_domain', 'mcp.admin_mcp_page'} <= endpoints
    if 'mcp_oauth' in app.blueprints:
        assert {e for e in expected if e.startswith('mcp_oauth.')} <= endpoints
    assert report.covered_by_tools + report.covered_by_exclusions == len(report.required) - report.uncovered_count


def test_report_lists_uncovered_pairs_by_route_file():
    """Формат падения: пары (метод, правило) по файлам маршрутов; мусорные ссылки видны."""
    from flask import Blueprint, Flask, jsonify
    from core.mcp.spec import ToolSpec
    bp = Blueprint('cov_probe', __name__)

    @bp.route('/api/zz/items', methods=['GET', 'POST'])
    def zz_items():
        return jsonify({})

    @bp.route('/api/zz/items/<item_id>', methods=['DELETE'])
    def zz_item(item_id):
        return jsonify({})

    @bp.route('/zz/page')
    def zz_page():
        return 'страница — вне охвата'

    app = Flask('cov_probe')
    app.register_blueprint(bp)
    schema = {'type': 'object', 'additionalProperties': False, 'properties': {}}
    tools = [ToolSpec(name='content_zz_list', domain='content', title='Список', description='Тестовый список '
                      'для проверки отчёта охвата.', input_schema=schema, path='/api/zz/items'),
             ToolSpec(name='content_zz_ghost', domain='content', title='Призрак', description='Ссылается на '
                      'маршрут, которого нет.', input_schema=schema, path='/api/zz/ghost')]
    module = registry.module_from_parts(tools=tools, excluded={('GET', '/api/zz/nothing'): 'нет такого маршрута'})
    registry.use_modules({'common': registry.module_from_parts(), 'content': module})
    try:
        report = coverage.check(app)
    finally:
        registry.use_modules(None)
    this_file = 'tests/test_mcp_coverage.py'
    assert report.uncovered == {this_file: [('POST', '/api/zz/items'), ('DELETE', '/api/zz/items/<item_id>')]}, \
        report.uncovered
    text = report.format_uncovered()
    assert text.splitlines() == [
        'Не покрыто 2 пар (метод, правило) — нужен инструмент или запись в EXCLUDED с причиной:',
        f'  {this_file}:',
        '    POST   /api/zz/items',
        '    DELETE /api/zz/items/<item_id>'], text
    assert report.dangling_tools == ['content_zz_ghost: нет маршрута /api/zz/ghost']
    assert report.dangling_exclusions == ['GET /api/zz/nothing (content): такого маршрута нет']
    assert report.covered_by_tools == 1 and not report.ok()


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:
            failed += 1
            print(f'FAIL {t.__name__}:\n{e}')
    report = _CACHE.get('report')
    if report is not None:
        print('\n' + report.format().splitlines()[0])
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(_run())
