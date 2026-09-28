"""
Тесты протокола MCP (core/mcp/protocol.py, routes/mcp.py), реестра и проверки аргументов.

Совместимы с pytest и запускаются сами: `py -3 tests/test_mcp_protocol.py`.

Сервер «двух эпох»:
- старая (2025-11-25 … 2024-11-05): initialize и согласование версии, заголовок
  MCP-Protocol-Version, ping, уведомления 202, пакеты только до 2025-06-18;
- новая (2026-07-28, без состояния): server/discover, обязательный params._meta,
  проверка заголовков Mcp-Method / Mcp-Name / MCP-Protocol-Version (HeaderMismatch
  -32020), UnsupportedProtocolVersion -32022, resultType и serverInfo в каждом
  результате, ttlMs/cacheScope у списков, 404 на неизвестный метод.
Плюс HTTP-обвязка: GET/DELETE 405, Origin 403, 401 с WWW-Authenticate на метаданные
нужного коннектора, 403 для токена другого раздела, не-админ 401, отозванный и
истёкший токен, лимит частоты, журнал вызовов. Реестр подменяется тестовыми модулями
(registry.use_modules) — тесты не зависят от описаний доменов.
"""

import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Blueprint, Flask, jsonify, request  # noqa: E402

import core.auth_manager as am  # noqa: E402
from core import msk_time  # noqa: E402
from core.auth_guard import init_auth  # noqa: E402
from core.mcp import audit, db, protocol, registry, schema_check, tokens  # noqa: E402
from core.mcp.bridge import ToolError  # noqa: E402
from core.mcp.spec import PromptArg, PromptSpec, ToolSpec  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODERN = '2026-07-28'
NO_ARGS = {'type': 'object', 'properties': {}, 'additionalProperties': False}

# ------------------------------------------------------------------ тестовые модули реестра

route_bp = Blueprint('proto_test', __name__)


@route_bp.route('/api/t/hello')
def t_hello():
    from core.auth_guard import current_user
    return jsonify({'hello': request.args.get('name', ''), 'by': current_user()['login']})


@route_bp.route('/api/t/fail')
def t_fail():
    return jsonify({'error': 'Нет такого бара'}), 400


def _echo(args, principal):
    return {'args': args, 'login': principal.login}


def _refuse(args, principal):
    raise ToolError('Не настроено')


def _render_week(args):
    return f'Составь план на {args["month"]} для {args.get("bar") or "всех баров"}.'


def _render_broken(args):
    raise RuntimeError('шаблон сломан')


def _modules():
    common = registry.module_from_parts(
        tools=[ToolSpec(name='common_echo', domain='common', title='Эхо', description='Эхо аргументов для '
                        'проверки протокола.', input_schema={'type': 'object', 'additionalProperties': False,
                                                              'properties': {'x': {'type': 'integer'}}},
                        handler=_echo, examples=({'x': 1},)),
               ToolSpec(name='common_refuse', domain='common', title='Отказ', description='Всегда ошибка '
                        'обработчика «не настроено».', input_schema=NO_ARGS, handler=_refuse, read_only=False)],
        instructions='ОБЩИЕ ПРАВИЛА ТЕСТА.')
    content = registry.module_from_parts(
        tools=[ToolSpec(name='content_hello', domain='content', title='Привет', description='Маршрут '
                        'GET /api/t/hello через мост.', input_schema={
                            'type': 'object', 'additionalProperties': False, 'required': ['name'],
                            'properties': {'name': {'type': 'string', 'minLength': 1}}},
                        path='/api/t/hello', query_params=('name',), examples=({'name': 'мир'},)),
               ToolSpec(name='content_fail', domain='content', title='Ошибка', description='Маршрут, '
                        'который отвечает 400 с полем error.', input_schema=NO_ARGS, path='/api/t/fail'),
               # Сломанное описание: имя без префикса домена — реестр не публикует.
               ToolSpec(name='broken_name', domain='content', title='Сломан', description='Описание с '
                        'неверным именем без префикса.', input_schema=NO_ARGS, path='/api/t/fail')],
        prompts=[PromptSpec(name='content_week', domain='content', title='Неделя', description='План недели',
                            arguments=(PromptArg('month', 'Месяц YYYY-MM', True), PromptArg('bar', 'Бар')),
                            render=_render_week),
                 PromptSpec(name='content_broken', domain='content', title='Сломан', description='Падает',
                            render=_render_broken)],
        instructions='ПРАВИЛА КОНТЕНТА.')
    stocks = registry.module_from_parts(
        tools=[ToolSpec(name='stocks_board', domain='stocks', title='Доска', description='Общий инструмент '
                        'остатков, виден и в контенте.', input_schema=NO_ARGS, handler=_echo,
                        also_in=('content',)),
               ToolSpec(name='stocks_secret', domain='stocks', title='Только остатки', description='Виден '
                        'только в коннекторе остатков.', input_schema=NO_ARGS, handler=_echo),
               # Дубль имени — второй экземпляр отбрасывается.
               ToolSpec(name='stocks_board', domain='stocks', title='Дубль', description='Второй инструмент '
                        'с тем же именем.', input_schema=NO_ARGS, handler=_echo)],
        instructions='ПРАВИЛА ОСТАТКОВ.')
    analytics = registry.module_from_parts(instructions='ПРАВИЛА АНАЛИТИКИ.')
    # staff нет вовсе: реестр обязан пережить отсутствующий модуль.
    return {'common': common, 'content': content, 'stocks': stocks, 'analytics': analytics}


class Env:
    def __init__(self, modules=None):
        self.modules = modules

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix='mcp_protocol_test_')
        self.saved_mgr = am._auth_manager
        self.saved_limiter = protocol.rate_limiter
        self.saved_max = protocol.MAX_REQUEST_BYTES
        self.mgr = am.AuthManager(db_path=os.path.join(self.tmp, 'auth.db'))
        am._auth_manager = self.mgr
        db.set_db_path(os.path.join(self.tmp, 'mcp.db'))
        registry.use_modules(self.modules or _modules())
        protocol.rate_limiter = protocol.RateLimiter()
        self.owner = self.mgr.get_by_id(self.mgr.create_user('owner', 'Владелец', 'ownerpass', is_admin=True))
        self.bob = self.mgr.get_by_id(self.mgr.create_user('bob', 'Боб', 'bobpass12'))
        self.token_all, self.row_all = tokens.create(self.owner, 'всё', ['*'], None)
        self.token_content, self.row_content = tokens.create(self.owner, 'контент', ['content'], None)
        app = Flask('mcp_protocol_test', template_folder=os.path.join(ROOT, 'templates'))
        from routes.mcp import mcp_bp
        app.register_blueprint(mcp_bp)
        app.register_blueprint(route_bp)
        app.jinja_env.globals['app_version'] = 'abc1234'
        init_auth(app)
        self.app = app
        self.client = app.test_client()
        return self

    def __exit__(self, *exc):
        registry.use_modules(None)
        protocol.rate_limiter = self.saved_limiter
        protocol.MAX_REQUEST_BYTES = self.saved_max
        am._auth_manager = self.saved_mgr
        db.set_db_path(None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def post(self, path, body, token='all', headers=None, raw=None):
        hdrs = {}
        if token:
            hdrs['Authorization'] = 'Bearer ' + (self.token_all if token == 'all' else
                                                 self.token_content if token == 'content' else token)
        hdrs.update(headers or {})
        if raw is not None:
            return self.client.post(path, data=raw, headers=hdrs, content_type='application/json')
        return self.client.post(path, data=json.dumps(body), headers=hdrs, content_type='application/json')

    def rpc(self, path, method, params=None, rid=1, token='all', version='2025-11-25', headers=None):
        body = {'jsonrpc': '2.0', 'id': rid, 'method': method}
        if params is not None:
            body['params'] = params
        hdrs = {'MCP-Protocol-Version': version} if version else {}
        hdrs.update(headers or {})
        return self.post(path, body, token=token, headers=hdrs)

    def modern(self, path, method, params=None, rid=1, token='all', headers=None, meta=None, name_header=None):
        params = dict(params or {})
        params['_meta'] = meta if meta is not None else {
            'io.modelcontextprotocol/protocolVersion': MODERN,
            'io.modelcontextprotocol/clientCapabilities': {},
            'io.modelcontextprotocol/clientInfo': {'name': 'test', 'version': '1'}}
        hdrs = {'MCP-Protocol-Version': MODERN, 'Mcp-Method': method}
        if name_header is not None:
            hdrs['Mcp-Name'] = name_header
        elif 'name' in params:
            hdrs['Mcp-Name'] = params['name']
        hdrs.update(headers or {})
        hdrs = {k: v for k, v in hdrs.items() if v is not None}
        return self.post(path, {'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params},
                         token=token, headers=hdrs)


def _result(resp):
    data = resp.get_json()
    assert 'result' in data, data
    return data['result']


def _error(resp):
    data = resp.get_json()
    assert 'error' in data, data
    return data['error']


# ------------------------------------------------------------------ старая эпоха

def test_initialize_version_negotiation_and_server_info():
    with Env() as env:
        for asked, got in (('2025-06-18', '2025-06-18'), ('2024-11-05', '2024-11-05'),
                           ('2025-03-26', '2025-03-26'), ('2025-11-25', '2025-11-25'),
                           ('2099-01-01', '2025-11-25'), (MODERN, '2025-11-25'), (None, '2025-11-25')):
            resp = env.rpc('/mcp/content', 'initialize', {'protocolVersion': asked, 'capabilities': {},
                                                          'clientInfo': {'name': 't', 'version': '1'}},
                           version=None)
            assert resp.status_code == 200 and resp.mimetype == 'application/json'
            result = _result(resp)
            assert result['protocolVersion'] == got, (asked, result['protocolVersion'])
            assert 'Mcp-Session-Id' not in resp.headers, 'сессий нет'
        assert result['capabilities'] == {'tools': {'listChanged': False}, 'prompts': {'listChanged': False}}
        assert result['serverInfo'] == {'name': 'kultura', 'title': 'Культура — Контент и отзывы · Полный доступ',
                                        'version': 'abc1234'}
        assert result['instructions'] == protocol.MODE_LINES['full'] + '\n\nОБЩИЕ ПРАВИЛА ТЕСТА.\n\nПРАВИЛА КОНТЕНТА.'
        full = _result(env.rpc('/mcp', 'initialize', {'protocolVersion': '2025-06-18'}, version=None))
        assert full['serverInfo']['title'] == 'Культура — все разделы · Полный доступ'
        assert full['instructions'].startswith(protocol.MODE_LINES['full'] + '\n\nОБЩИЕ ПРАВИЛА ТЕСТА.\n\nРазделы сервиса')
        assert 'common_instructions(domain="stocks")' in full['instructions']


def test_tools_list_per_connector():
    with Env() as env:
        names = [t['name'] for t in _result(env.rpc('/mcp/content', 'tools/list'))['tools']]
        assert names == ['common_echo', 'common_refuse', 'content_hello', 'content_fail', 'stocks_board'], names
        names = [t['name'] for t in _result(env.rpc('/mcp/stocks', 'tools/list'))['tools']]
        assert names == ['common_echo', 'common_refuse', 'stocks_board', 'stocks_secret']
        names = [t['name'] for t in _result(env.rpc('/mcp/staff', 'tools/list'))['tools']]
        assert names == ['common_echo', 'common_refuse'], 'модуля staff нет — только общие'
        tools = _result(env.rpc('/mcp', 'tools/list', {'cursor': 'ignored'}))
        assert 'nextCursor' not in tools
        assert [t['name'] for t in tools['tools']] == ['common_echo', 'common_refuse', 'content_hello',
                                                       'content_fail', 'stocks_board', 'stocks_secret']
        hello = next(t for t in tools['tools'] if t['name'] == 'content_hello')
        assert set(hello) == {'name', 'title', 'description', 'inputSchema', 'annotations'}
        assert hello['inputSchema']['required'] == ['name']
        assert hello['annotations'] == {'title': 'Привет', 'readOnlyHint': True, 'destructiveHint': False,
                                        'idempotentHint': False, 'openWorldHint': False}
        errors = registry.load_errors()
        assert any('broken_name' in e for e in errors), errors
        assert any('stocks_board: имя уже занято' in e for e in errors), errors
        assert any(e.startswith('staff: модуль не загрузился') for e in errors), errors


def test_tools_call_ok_error_unknown_schema():
    with Env() as env:
        result = _result(env.rpc('/mcp/content', 'tools/call', {'name': 'content_hello',
                                                                'arguments': {'name': 'мир'}}))
        assert result['isError'] is False and 'structuredContent' not in result
        assert json.loads(result['content'][0]['text']) == {'hello': 'мир', 'by': 'owner'}
        failed = _result(env.rpc('/mcp/content', 'tools/call', {'name': 'content_fail', 'arguments': {}}))
        assert failed['isError'] is True and failed['content'][0]['text'] == 'Ошибка HTTP 400: Нет такого бара'
        refused = _result(env.rpc('/mcp/content', 'tools/call', {'name': 'common_refuse'}))
        assert refused['isError'] is True and refused['content'][0]['text'] == 'Не настроено'
        bad = _result(env.rpc('/mcp/content', 'tools/call', {'name': 'content_hello', 'arguments': {'name': 5}}))
        assert bad['isError'] is True
        assert 'Поле «name»: ожидается строка, получено целое число 5' in bad['content'][0]['text']
        resp = env.rpc('/mcp/content', 'tools/call', {'name': 'no_such_tool', 'arguments': {}})
        assert resp.status_code == 200 and _error(resp)['code'] == -32602, 'старая эпоха: ошибки JSON-RPC — 200'
        assert _error(env.rpc('/mcp/content', 'tools/call', {'name': 'stocks_secret'}))['code'] == -32602, \
            'инструмент другого коннектора'
        assert _error(env.rpc('/mcp/content', 'tools/call', {'name': 'content_hello', 'arguments': [1]}))['code'] \
            == -32602
        assert _error(env.rpc('/mcp/content', 'tools/call', {}))['code'] == -32602
        also = _result(env.rpc('/mcp/content', 'tools/call', {'name': 'stocks_board'}))
        assert also['isError'] is False, 'also_in: инструмент остатков виден в контенте'
        statuses = [(r['tool'], r['status'], r['connector']) for r in audit.recent()]
        assert statuses == [('stocks_board', 'ok', 'content'), ('<не строка>', 'denied', 'content'),
                            ('stocks_secret', 'denied', 'content'),
                            ('no_such_tool', 'denied', 'content'), ('content_hello', 'error', 'content'),
                            ('common_refuse', 'error', 'content'), ('content_fail', 'error', 'content'),
                            ('content_hello', 'ok', 'content')], statuses
        first = audit.recent(tool='content_hello', status='ok')[0]
        assert first['user_login'] == 'owner' and first['client_name'] == 'всё' and first['http_status'] == 200
        assert json.loads(first['args_preview']) == {'name': 'мир'} and first['result_chars'] > 0
        assert audit.recent(tool='content_fail')[0]['error_preview'] == 'Нет такого бара'


def test_prompts_list_and_get():
    with Env() as env:
        prompts = _result(env.rpc('/mcp/content', 'prompts/list'))['prompts']
        assert [p['name'] for p in prompts] == ['content_week', 'content_broken']
        assert prompts[0]['arguments'] == [{'name': 'month', 'description': 'Месяц YYYY-MM', 'required': True},
                                           {'name': 'bar', 'description': 'Бар', 'required': False}]
        assert _result(env.rpc('/mcp/stocks', 'prompts/list'))['prompts'] == []
        got = _result(env.rpc('/mcp/content', 'prompts/get', {'name': 'content_week',
                                                              'arguments': {'month': '2026-10'}}))
        assert got == {'description': 'План недели', 'messages': [
            {'role': 'user', 'content': {'type': 'text', 'text': 'Составь план на 2026-10 для всех баров.'}}]}
        assert _error(env.rpc('/mcp/content', 'prompts/get', {'name': 'content_week'}))['code'] == -32602
        assert _error(env.rpc('/mcp/stocks', 'prompts/get', {'name': 'content_week',
                                                             'arguments': {'month': 'x'}}))['code'] == -32602
        assert _error(env.rpc('/mcp/content', 'prompts/get', {'name': 'content_broken'}))['code'] == -32603


def test_ping_notifications_and_client_responses():
    with Env() as env:
        assert _result(env.rpc('/mcp', 'ping')) == {}
        resp = env.post('/mcp', {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        assert resp.status_code == 202 and resp.data == b''
        resp = env.post('/mcp', {'jsonrpc': '2.0', 'id': 5, 'result': {}})
        assert resp.status_code == 202, 'ответ клиента на наш запрос'
        resp = env.post('/mcp', {'jsonrpc': '2.0', 'method': 'notifications/cancelled',
                                 'params': {'requestId': 1}}, headers={'MCP-Protocol-Version': '2025-06-18'})
        assert resp.status_code == 202
        assert _error(env.rpc('/mcp', 'resources/list'))['code'] == -32601
        assert _error(env.rpc('/mcp', 'logging/setLevel', {'level': 'info'}))['code'] == -32601


def test_get_delete_405_unknown_domain_404():
    with Env() as env:
        auth = {'Authorization': 'Bearer ' + env.token_all}
        for method in ('get', 'delete'):
            for path in ('/mcp', '/mcp/content'):
                resp = getattr(env.client, method)(path, headers=auth)
                assert resp.status_code == 405 and resp.headers['Allow'] == 'POST', (method, path)
        assert env.client.get('/mcp/content').status_code == 401, 'без токена — сначала 401'
        resp = env.rpc('/mcp/warehouse', 'tools/list')
        assert resp.status_code == 404 and '/mcp/content' in resp.get_json()['error']
        assert env.rpc('/mcp/', 'ping').status_code == 200, 'завершающий слэш'


def test_origin_check():
    with Env() as env:
        for origin, status in (('https://evil.example', 403), ('null', 403), ('https://claude.ai', 200),
                               ('https://app.claude.ai', 200), ('https://claude.com', 200),
                               ('http://localhost:6274', 200), ('http://127.0.0.1:3000', 200),
                               ('http://localhost', 200), ('https://notclaude.ai', 403)):
            resp = env.rpc('/mcp', 'ping', headers={'Origin': origin})
            assert resp.status_code == status, (origin, resp.status_code)
            if status == 403:
                assert resp.get_json()['error']['code'] == -32600 and resp.get_json()['id'] is None
        assert env.rpc('/mcp', 'ping').status_code == 200, 'без Origin (Claude Code, сервер) — можно'


def test_auth_errors_and_www_authenticate():
    with Env() as env:
        resp = env.rpc('/mcp/content', 'tools/list', token=None)
        assert resp.status_code == 401 and 'error' in resp.get_json()
        assert resp.headers['WWW-Authenticate'] == ('Bearer resource_metadata="http://localhost/.well-known/'
                                                    'oauth-protected-resource/mcp/content"')
        resp = env.rpc('/mcp', 'tools/list', token=None)
        assert resp.headers['WWW-Authenticate'] == ('Bearer resource_metadata="http://localhost/.well-known/'
                                                    'oauth-protected-resource/mcp"')
        resp = env.rpc('/mcp/content', 'tools/list', token='kmcp_unknown')
        assert resp.status_code == 401 and 'error="invalid_token"' in resp.headers['WWW-Authenticate']
        resp = env.rpc('/mcp/stocks', 'tools/list', token='content')
        assert resp.status_code == 403 and 'error="insufficient_scope"' in resp.headers['WWW-Authenticate']
        assert 'oauth-protected-resource/mcp/stocks' in resp.headers['WWW-Authenticate']
        assert env.rpc('/mcp', 'tools/list', token='content').status_code == 403, 'полный /mcp — только «*»'
        assert env.rpc('/mcp/content', 'tools/list', token='content').status_code == 200
        bob_token, _ = tokens.create(env.bob, 'боб', ['*'], None)
        assert env.rpc('/mcp', 'ping', token=bob_token).status_code == 401, 'владелец не админ'
        tokens.revoke(env.row_content['id'])
        assert env.rpc('/mcp/content', 'ping', token='content').status_code == 401, 'отозван'
        raw, row = tokens.create(env.owner, 'истёк', ['*'], 1)
        with db.write() as conn:
            conn.execute('UPDATE static_tokens SET expires_at=? WHERE id=?',
                         ((msk_time.now() - timedelta(seconds=5)).isoformat(), row['id']))
        assert env.rpc('/mcp', 'ping', token=raw).status_code == 401, 'истёк'


def test_auth_storage_failure_is_503_not_401():
    with Env() as env:
        saved = tokens.verify_static

        def broken(raw):
            raise sqlite3.OperationalError('database is locked')
        tokens.verify_static = broken
        try:
            resp = env.rpc('/mcp', 'ping')
            assert resp.status_code == 503 and resp.headers.get('Retry-After') == '30'
        finally:
            tokens.verify_static = saved


def test_legacy_version_header_and_batches():
    with Env() as env:
        resp = env.rpc('/mcp', 'tools/list', version='1999-01-01')
        assert resp.status_code == 400
        err = _error(resp)
        assert err['code'] == -32022 and err['data']['requested'] == '1999-01-01'
        assert err['data']['supported'] == ['2026-07-28', '2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05']
        assert env.rpc('/mcp', 'tools/list', version=None).status_code == 200, 'без заголовка — 2025-03-26'
        batch = [{'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
                 {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                 {'jsonrpc': '2.0', 'id': 'b', 'method': 'tools/call',
                  'params': {'name': 'common_echo', 'arguments': {'x': 2}}}]
        resp = env.post('/mcp', batch, headers={'MCP-Protocol-Version': '2025-03-26'})
        assert resp.status_code == 200
        out = resp.get_json()
        assert [r['id'] for r in out] == [1, 'b'] and out[0]['result'] == {}
        assert json.loads(out[1]['result']['content'][0]['text'])['args'] == {'x': 2}
        assert env.post('/mcp', batch).status_code == 200, 'без заголовка — 2025-03-26, пакеты можно'
        resp = env.post('/mcp', [{'jsonrpc': '2.0', 'method': 'notifications/initialized'}])
        assert resp.status_code == 202
        resp = env.post('/mcp', batch, headers={'MCP-Protocol-Version': '2025-06-18'})
        assert resp.status_code == 400 and _error(resp)['code'] == -32600, 'в 2025-06-18 пакеты убраны'
        assert env.post('/mcp', []).status_code == 400
        resp = env.post('/mcp', batch, headers={'MCP-Protocol-Version': MODERN})
        assert resp.status_code == 400 and _error(resp)['code'] == -32600


def test_parse_and_invalid_requests():
    with Env() as env:
        resp = env.post('/mcp', None, raw='{bad json')
        assert resp.status_code == 400 and resp.get_json() == {
            'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Некорректный JSON'}}
        resp = env.post('/mcp', 5)
        assert resp.status_code == 400 and _error(resp)['code'] == -32600
        resp = env.post('/mcp', {'jsonrpc': '2.0', 'id': 3})
        assert resp.status_code == 400 and _error(resp)['code'] == -32600 and resp.get_json()['id'] == 3
        resp = env.post('/mcp', {'jsonrpc': '2.0', 'id': True, 'method': 'ping'})
        assert resp.status_code == 400 and resp.get_json()['id'] is None
        resp = env.post('/mcp', {'jsonrpc': '1.0', 'id': 4, 'method': 'ping'})
        assert resp.status_code == 400 and _error(resp)['code'] == -32600
        resp = env.post('/mcp', {'jsonrpc': '2.0', 'id': 6, 'method': 'tools/list', 'params': [1]})
        assert _error(resp)['code'] == -32602
        protocol.MAX_REQUEST_BYTES = 100
        resp = env.post('/mcp', {'jsonrpc': '2.0', 'id': 7, 'method': 'ping', 'params': {'pad': 'x' * 500}})
        assert resp.status_code == 413


# ------------------------------------------------------------------ новая эпоха (2026-07-28)

def test_modern_discover_list_call_prompt():
    with Env() as env:
        resp = env.modern('/mcp/content', 'server/discover', rid='d1')
        assert resp.status_code == 200
        result = _result(resp)
        assert result['resultType'] == 'complete'
        assert result['supportedVersions'] == ['2026-07-28', '2025-11-25', '2025-06-18', '2025-03-26',
                                               '2024-11-05']
        assert result['capabilities'] == {'tools': {'listChanged': False}, 'prompts': {'listChanged': False}}
        assert result['_meta'] == {'io.modelcontextprotocol/serverInfo': {
            'name': 'kultura', 'title': 'Культура — Контент и отзывы · Полный доступ', 'version': 'abc1234'}}
        assert result['ttlMs'] == protocol.LIST_TTL_MS and result['cacheScope'] == 'private'
        assert result['instructions'] == protocol.MODE_LINES['full'] + '\n\nОБЩИЕ ПРАВИЛА ТЕСТА.\n\nПРАВИЛА КОНТЕНТА.'
        tools = _result(env.modern('/mcp/content', 'tools/list'))
        assert tools['resultType'] == 'complete' and tools['ttlMs'] == protocol.LIST_TTL_MS
        assert tools['cacheScope'] == 'private' and len(tools['tools']) == 5
        called = _result(env.modern('/mcp/content', 'tools/call', {'name': 'content_hello',
                                                                   'arguments': {'name': 'мир'}}))
        assert called['resultType'] == 'complete' and called['isError'] is False
        assert json.loads(called['content'][0]['text']) == {'hello': 'мир', 'by': 'owner'}
        assert 'io.modelcontextprotocol/serverInfo' in called['_meta']
        prompts = _result(env.modern('/mcp/content', 'prompts/list'))
        assert prompts['ttlMs'] == protocol.LIST_TTL_MS and len(prompts['prompts']) == 2
        got = _result(env.modern('/mcp/content', 'prompts/get', {'name': 'content_week',
                                                                 'arguments': {'month': '2026-11'}}))
        assert got['resultType'] == 'complete' and 'на 2026-11' in got['messages'][0]['content']['text']
        encoded = '=?base64?' + base64.b64encode('content_hello'.encode()).decode() + '?='
        ok = env.modern('/mcp/content', 'tools/call', {'name': 'content_hello', 'arguments': {'name': 'x'}},
                        name_header=encoded)
        assert ok.status_code == 200, 'Mcp-Name в base64-обёртке раскодируется'
        assert env.post('/mcp', {'jsonrpc': '2.0', 'method': 'notifications/whatever'},
                        headers={'MCP-Protocol-Version': MODERN}).status_code == 202


def test_modern_validation_ladder():
    with Env() as env:
        def err(resp, code, status):
            assert resp.status_code == status, (resp.status_code, resp.get_json())
            assert _error(resp)['code'] == code, resp.get_json()
            return _error(resp)
        # 1) _meta обязателен, и в нём обе обязательные записи.
        err(env.post('/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                     headers={'MCP-Protocol-Version': MODERN, 'Mcp-Method': 'tools/list'}), -32602, 400)
        err(env.modern('/mcp', 'tools/list', meta={'io.modelcontextprotocol/protocolVersion': MODERN}), -32602, 400)
        # 2) заголовки совпадают с телом.
        err(env.modern('/mcp', 'tools/list', headers={'MCP-Protocol-Version': None}), -32020, 400)
        err(env.modern('/mcp', 'tools/list', headers={'Mcp-Method': 'prompts/list'}), -32020, 400)
        err(env.modern('/mcp', 'tools/call', {'name': 'common_echo'}, name_header='common_other'), -32020, 400)
        err(env.modern('/mcp', 'tools/call', {'name': 'common_echo'}, name_header='=?base64?###?='), -32020, 400)
        # 3) версия из _meta поддерживается в новой эпохе.
        data = err(env.modern('/mcp', 'tools/list', headers={'MCP-Protocol-Version': '2025-06-18'},
                              meta={'io.modelcontextprotocol/protocolVersion': '2025-06-18',
                                    'io.modelcontextprotocol/clientCapabilities': {}}), -32022, 400)
        assert data['data']['requested'] == '2025-06-18' and MODERN in data['data']['supported']
        # Неизвестный метод новой эпохи — 404; ping в 2026-07-28 удалён.
        err(env.modern('/mcp', 'resources/list'), -32601, 404)
        err(env.modern('/mcp', 'ping'), -32601, 404)
        err(env.modern('/mcp', 'tools/call', {'name': 'no_such'}), -32602, 400)


def test_rate_limit_per_token():
    with Env() as env:
        protocol.rate_limiter = protocol.RateLimiter(limit=3, window=60)
        for i in range(3):
            assert _result(env.rpc('/mcp', 'tools/call', {'name': 'common_echo', 'arguments': {'x': i}}))['isError'] \
                is False
        limited = _result(env.rpc('/mcp', 'tools/call', {'name': 'common_echo', 'arguments': {'x': 9}}))
        assert limited['isError'] is True and 'Слишком часто' in limited['content'][0]['text']
        assert audit.recent(limit=1)[0]['status'] == 'denied'
        other = _result(env.rpc('/mcp/content', 'tools/call', {'name': 'common_echo'}, token='content'))
        assert other['isError'] is False, 'у другого токена свой счётчик'
        assert _result(env.rpc('/mcp', 'tools/list'))['tools'], 'список инструментов лимит не считает'
        limiter = protocol.RateLimiter(limit=2, window=60)
        assert limiter.hit('t', now=0) is None and limiter.hit('t', now=1) is None
        assert limiter.hit('t', now=2) == 59 and limiter.hit('t', now=61) is None


# ------------------------------------------------------------------ режимы доступа

def _draft(args, principal):
    from core.mcp import bridge
    call = bridge.current_call()
    return {'draft': True, 'mode': call.mode if call else None}


def _mode_modules():
    common = registry.module_from_parts(
        tools=[ToolSpec(name='common_echo', domain='common', title='Эхо', description='Эхо аргументов для '
                        'проверки протокола.', input_schema=NO_ARGS, handler=_echo)],
        instructions='ОБЩИЕ ПРАВИЛА ТЕСТА.')
    content = registry.module_from_parts(
        tools=[ToolSpec(name='content_hello', domain='content', title='Привет', description='Маршрут '
                        'GET /api/t/hello через мост.', input_schema={
                            'type': 'object', 'additionalProperties': False,
                            'properties': {'name': {'type': 'string'}}},
                        path='/api/t/hello', query_params=('name',)),
               ToolSpec(name='content_draft_save', domain='content', title='Черновик', description='Запись '
                        'черновика внутри сервиса (draft_write).', input_schema=NO_ARGS, handler=_draft,
                        read_only=False, draft_write=True),
               ToolSpec(name='content_approve', domain='content', title='Утвердить', description='Утверждение '
                        'публикации — необратимо, только полный доступ.', input_schema=NO_ARGS, handler=_echo,
                        read_only=False, destructive=True)],
        instructions='ПРАВИЛА КОНТЕНТА.')
    return {'common': common, 'content': content}


def _names(resp):
    return [t['name'] for t in _result(resp)['tools']]


def test_mode_urls_route_to_same_endpoints():
    with Env(_mode_modules()) as env:
        for path, expected in (('/mcp/content', ['common_echo', 'content_hello', 'content_draft_save',
                                                 'content_approve']),
                               ('/mcp/content/draft', ['common_echo', 'content_hello', 'content_draft_save']),
                               ('/mcp/content/read', ['common_echo', 'content_hello']),
                               ('/mcp/read', ['common_echo', 'content_hello']),
                               ('/mcp/draft', ['common_echo', 'content_hello', 'content_draft_save'])):
            resp = env.rpc(path, 'tools/list')
            assert resp.status_code == 200, (path, resp.status_code)
            assert _names(resp) == expected, (path, _names(resp))
        # Полный доступ — адрес без суффикса: /full не существует, у пары (домен, режим) один адрес.
        for path in ('/mcp/full', '/mcp/content/full', '/mcp/read/draft', '/mcp/content/admin', '/mcp/warehouse',
                     '/mcp/warehouse/read', '/mcp/draft/content', '/mcp/content/read/x'):
            assert env.rpc(path, 'tools/list').status_code == 404, path
        assert env.rpc('/mcp/content/full', 'tools/list', token=None).status_code == 404, '404 раньше 401'
        assert env.client.post('/mcp/full', json={}).status_code == 404
        endpoints = {r.rule: r.endpoint for r in env.app.url_map.iter_rules() if r.rule.startswith('/mcp')}
        assert endpoints == {'/mcp': 'mcp.mcp_all', '/mcp/<domain>': 'mcp.mcp_domain',
                             '/mcp/<domain>/<mode>': 'mcp.mcp_domain',
                             '/mcp/<domain>/<mode>/<path:rest>': 'mcp.mcp_domain'}, endpoints


def test_mode_blocks_calls_and_audits_denied():
    with Env(_mode_modules()) as env:
        result = _result(env.rpc('/mcp/content/read', 'tools/call', {'name': 'content_draft_save'}))
        assert result['isError'] is True
        assert 'недоступен в режиме «Только чтение»' in result['content'][0]['text']
        result = _result(env.rpc('/mcp/content/draft', 'tools/call', {'name': 'content_approve'}))
        assert result['isError'] is True and '«Чтение и черновики»' in result['content'][0]['text']
        ok = _result(env.rpc('/mcp/content/draft', 'tools/call', {'name': 'content_draft_save'}))
        assert ok['isError'] is False and json.loads(ok['content'][0]['text']) == {'draft': True, 'mode': 'draft'}
        assert _result(env.rpc('/mcp/content/read', 'tools/call', {'name': 'content_hello'}))['isError'] is False
        assert _result(env.rpc('/mcp/content', 'tools/call', {'name': 'content_approve'}))['isError'] is False
        rows = [(r['tool'], r['status'], r['connector']) for r in audit.recent()]
        assert rows == [('content_approve', 'ok', 'content'), ('content_hello', 'ok', 'content/read'),
                        ('content_draft_save', 'ok', 'content/draft'),
                        ('content_approve', 'denied', 'content/draft'),
                        ('content_draft_save', 'denied', 'content/read')], rows


def test_token_mode_and_url_mode_stricter_wins():
    with Env(_mode_modules()) as env:
        read_token, _ = tokens.create(env.owner, 'дайджест', ['*'], None, mode='read')
        draft_token, _ = tokens.create(env.owner, 'черновики', ['*'], None, mode='draft')
        assert _names(env.rpc('/mcp/content', 'tools/list', token=read_token)) == ['common_echo', 'content_hello'], \
            'адрес без суффикса не расширяет токен «только чтение»'
        assert _names(env.rpc('/mcp/content', 'tools/list', token=draft_token)) == \
            ['common_echo', 'content_hello', 'content_draft_save']
        assert _names(env.rpc('/mcp/content/read', 'tools/list', token=draft_token)) == \
            ['common_echo', 'content_hello'], 'адрес строже токена'
        denied = _result(env.rpc('/mcp/content', 'tools/call', {'name': 'content_approve'}, token=read_token))
        assert denied['isError'] is True and '«Только чтение»' in denied['content'][0]['text']
        who = _result(env.rpc('/mcp/content', 'initialize', {'protocolVersion': '2025-06-18'}, token=draft_token,
                              version=None))
        assert who['serverInfo']['title'] == 'Культура — Контент и отзывы · Чтение и черновики'


def test_mode_named_in_server_info_and_instructions():
    with Env(_mode_modules()) as env:
        init = _result(env.rpc('/mcp/content/read', 'initialize', {'protocolVersion': '2025-11-25'}, version=None))
        assert init['serverInfo']['title'] == 'Культура — Контент и отзывы · Только чтение'
        assert init['instructions'].split('\n', 1)[0] == protocol.MODE_LINES['read']
        disc = _result(env.modern('/mcp/draft', 'server/discover'))
        assert disc['_meta']['io.modelcontextprotocol/serverInfo']['title'] == 'Культура — все разделы · ' \
                                                                                'Чтение и черновики'
        assert disc['instructions'].startswith(protocol.MODE_LINES['draft'] + '\n\n')
        listed = _result(env.modern('/mcp/content/read', 'tools/list'))
        assert [t['name'] for t in listed['tools']] == ['common_echo', 'content_hello']


def test_www_authenticate_and_oauth_resource_include_mode():
    from core.mcp import oauth
    with Env(_mode_modules()) as env:
        for path in ('/mcp/content/read', '/mcp/draft', '/mcp/content/draft'):
            resp = env.rpc(path, 'tools/list', token=None)
            assert resp.status_code == 401
            assert resp.headers['WWW-Authenticate'] == ('Bearer resource_metadata="http://localhost/.well-known/'
                                                        f'oauth-protected-resource{path}"'), path
        seen = []
        saved = oauth.verify_access_token
        oauth.verify_access_token = lambda raw, resource: seen.append(resource)
        try:
            assert env.rpc('/mcp/content/draft', 'ping', token='kmcpo_' + 'x' * 43).status_code == 401
            assert env.rpc('/mcp/read', 'ping', token='kmcpo_' + 'y' * 43).status_code == 401
        finally:
            oauth.verify_access_token = saved
        assert seen == ['http://localhost/mcp/content/draft', 'http://localhost/mcp/read']


# ------------------------------------------------------------------ защита от перегрузки и мусора

def test_tool_names_validated_before_audit_and_echo():
    with Env() as env:
        long_name = 'x' * 5000
        for bad in (long_name, 'DROP TABLE tools', 'пиво', 123, None, ['a']):
            resp = env.rpc('/mcp', 'tools/call', {'name': bad, 'arguments': {}})
            err = _error(resp)
            assert err['code'] == -32602 and 'Некорректное имя инструмента' in err['message'], bad
            assert (not isinstance(bad, str)) or bad not in err['message'], 'кривое имя не отражается'
        rows = audit.recent(limit=10)
        assert all(r['status'] == 'denied' and len(r['tool']) <= 64 for r in rows)
        assert rows[-1]['tool'] == 'x' * 63 + '…'
        assert rows[0]['tool'] == '<не строка>', 'список вместо имени'
        err = _error(env.rpc('/mcp', 'tools/call', {'name': 'no_such_tool'}))
        assert err['message'] == 'Неизвестный инструмент в этом коннекторе: no_such_tool'
        err = _error(env.rpc('/mcp', 'prompts/get', {'name': 'y' * 3000}))
        assert err['code'] == -32602 and 'y' * 100 not in err['message']
        err = _error(env.rpc('/mcp', 'z' * 3000))
        assert err['code'] == -32601 and len(err['message']) < 120, 'имя метода обрезано'
        resp = env.rpc('/mcp', 'tools/list', version='v' * 3000)
        assert len(_error(resp)['data']['requested']) <= protocol.ECHO_LIMIT


def test_rate_limit_counts_unknown_and_invalid_calls():
    with Env() as env:
        protocol.rate_limiter = protocol.RateLimiter(limit=3, window=60)
        env.rpc('/mcp', 'tools/call', {'name': 'no_such_tool'})
        env.rpc('/mcp', 'tools/call', {'name': 'BAD NAME'})
        env.rpc('/mcp', 'tools/call', {'name': 'common_echo'})
        limited = _result(env.rpc('/mcp', 'tools/call', {'name': 'common_echo'}))
        assert limited['isError'] is True and 'Слишком часто' in limited['content'][0]['text'], \
            'отказы и неизвестные имена тоже расходуют лимит'
        limited_bad = _result(env.rpc('/mcp', 'tools/call', {'name': 'BAD NAME 2'}))
        assert limited_bad['isError'] is True, 'сверх лимита — отказ по частоте, даже для кривого имени'


def test_batch_length_capped():
    with Env() as env:
        ping = {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}
        resp = env.post('/mcp', [dict(ping, id=i) for i in range(protocol.MAX_BATCH)])
        assert resp.status_code == 200 and len(resp.get_json()) == protocol.MAX_BATCH
        resp = env.post('/mcp', [dict(ping, id=i) for i in range(protocol.MAX_BATCH + 1)])
        assert resp.status_code == 400 and _error(resp)['code'] == -32600
        assert 'не больше 20' in _error(resp)['message']


def test_deeply_nested_json_is_parse_error():
    with Env() as env:
        depth = 100000
        raw = '{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":' + '[' * depth + ']' * depth + '}}'
        resp = env.post('/mcp', None, raw=raw)
        assert resp.status_code == 400 and _error(resp)['code'] == -32700


def test_body_cap_without_content_length():
    import io as _io
    with Env() as env:
        protocol.MAX_REQUEST_BYTES = 1000
        headers = {'Authorization': 'Bearer ' + env.token_all, 'Content-Type': 'application/json',
                   'Transfer-Encoding': 'chunked'}
        big = b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"pad":"' + b'x' * 5000 + b'"}}'
        resp = env.client.post('/mcp', input_stream=_io.BytesIO(big), headers=headers,
                               environ_overrides={'wsgi.input_terminated': True})
        assert resp.status_code == 413, 'без Content-Length тело читается не дальше предела'
        small = b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
        resp = env.client.post('/mcp', input_stream=_io.BytesIO(small), headers=headers,
                               environ_overrides={'wsgi.input_terminated': True})
        assert resp.status_code == 200 and resp.get_json()['result'] == {}
        prefix = b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"p":"'
        for size, status in ((1000, 200), (1001, 413)):          # ровно предел — можно, байт сверху — нет
            body = prefix + b'x' * (size - len(prefix) - 3) + b'"}}'
            assert len(body) == size
            resp = env.client.post('/mcp', input_stream=_io.BytesIO(body), headers=headers,
                                   environ_overrides={'wsgi.input_terminated': True})
            assert resp.status_code == status, (size, resp.status_code)


def test_concurrent_calls_capped_per_process():
    with Env() as env:
        taken = 0
        try:
            while protocol.call_slots.acquire(blocking=False):
                taken += 1
            assert taken == protocol.MAX_CONCURRENT_CALLS == 3
            busy = _result(env.rpc('/mcp', 'tools/call', {'name': 'common_echo'}))
            assert busy['isError'] is True and 'Сервер занят' in busy['content'][0]['text']
            assert audit.recent(limit=1)[0]['status'] == 'denied'
        finally:
            for _ in range(taken):
                protocol.call_slots.release()
        assert _result(env.rpc('/mcp', 'tools/call', {'name': 'common_echo'}))['isError'] is False, \
            'место освобождается после вызова'
        assert _result(env.rpc('/mcp', 'tools/call', {'name': 'common_echo'}))['isError'] is False


def test_rate_limit_shared_between_processes():
    """Два лимитера на одной mcp.db — как два gunicorn-воркера: счёт общий."""
    import time as _time
    with Env():
        worker_a = protocol.RateLimiter(limit=3, window=60)
        worker_b = protocol.RateLimiter(limit=3, window=60)
        now = _time.time()
        assert worker_a.hit('st_shared', now=now) is None
        assert worker_b.hit('st_shared', now=now + 1) is None
        assert worker_a.hit('st_shared', now=now + 2) is None
        assert worker_b.hit('st_shared', now=now + 3) == 58, 'четвёртый вызов за минуту — отказ во втором воркере'
        assert worker_a.hit('st_other', now=now + 3) is None, 'у другого токена свой счёт'
        assert worker_b.hit('st_shared', now=now + 61) is None, 'окно скользит: через минуту снова можно'
        # Строки «из будущего» (часы перевели назад больше чем на окно) удаляются, а не блокируют токен.
        worker_a.hit('st_clock', now=now + 10000)
        assert worker_b.hit('st_clock', now=now) is None
        with db.read() as conn:
            left = conn.execute("SELECT COUNT(*) AS n FROM rate_hits WHERE key='st_clock'").fetchone()['n']
        assert left == 1, 'осталась только своя строка'


def test_rate_limit_falls_back_to_process_memory():
    """mcp.db недоступна — лимит считается в памяти процесса, а не пропадает и не роняет вызов."""
    with Env() as env:
        broken = os.path.join(env.tmp, 'dir_instead_of_db')
        os.makedirs(broken)
        db.set_db_path(broken)                   # sqlite не откроет каталог как файл БД
        limiter = protocol.RateLimiter(limit=2, window=60)
        assert limiter.hit('t', now=0) is None and limiter.hit('t', now=1) is None
        assert limiter.hit('t', now=2) == 59
        lease = protocol.CallLeases(limit=1).acquire('t', 'x')
        assert lease == protocol.CallLeases.LOCAL_LEASE, 'без mcp.db остаётся предел процесса'
        db.set_db_path(os.path.join(env.tmp, 'mcp.db'))


def test_call_leases_shared_and_expire():
    """Места вызовов общие на сервис: занятые «другим воркером» места дают «Сервер занят»;
    аренда погибшего процесса истекает сама."""
    import time as _time
    with Env() as env:
        leases = protocol.call_leases
        other_worker = [leases.acquire('st_night', 'stocks_order_board') for _ in range(protocol.MAX_CONCURRENT_CALLS)]
        assert all(other_worker) and leases.active() == protocol.MAX_CONCURRENT_CALLS
        assert leases.acquire('st_x', 'y') is None, 'сверх предела — отказ'
        busy = _result(env.rpc('/mcp', 'tools/call', {'name': 'common_echo', 'arguments': {'x': 1}}))
        assert busy['isError'] is True and 'Сервер занят' in busy['content'][0]['text']
        row = audit.recent(limit=1)[0]
        assert row['status'] == 'denied' and row['http_status'] is None and 'Сервер занят' in row['error_preview']
        leases.release(other_worker[0])
        ok = _result(env.rpc('/mcp', 'tools/call', {'name': 'common_echo', 'arguments': {'x': 2}}))
        assert ok['isError'] is False, 'место освободилось'
        assert leases.active() == protocol.MAX_CONCURRENT_CALLS - 1, 'свой вызов вернул место'
        for lease in other_worker[1:]:
            leases.release(lease)
        # Аренда с истёкшим сроком (процесс умер посреди вызова) не считается.
        stale = protocol.CallLeases(limit=1, ttl=5)
        assert stale.acquire('st_dead', 'x', now=_time.time() - 60)
        assert stale.acquire('st_live', 'x') is not None, 'истёкшая аренда освободилась сама'
        assert protocol.LEASE_TTL_S == 300 and protocol.MAX_CONCURRENT_CALLS == 3


def test_mode_lines_name_owner_notice():
    """Строка режима read/draft говорит, что сообщение владельцу доступно (сервер его пускает)."""
    for mode in ('read', 'draft'):
        line = protocol.MODE_LINES[mode]
        assert 'common_notify_owner' in line and '\n' not in line, mode
    assert 'common_notify_owner' not in protocol.MODE_LINES['full']


def test_prompt_spec_validation_in_registry():
    """Опечатка в mode_required не публикует сценарий (иначе он был бы виден в …/read)."""
    from core.mcp.spec import validate_prompt_spec
    good = PromptSpec(name='content_ok', domain='content', title='Ок', description='Норма',
                      render=lambda a: 'x', mode_required='draft')
    assert validate_prompt_spec(good) == []
    cases = {
        'mode_required': PromptSpec(name='content_typo', domain='content', title='Т', description='Опечатка',
                                    render=lambda a: 'x', mode_required='drfat'),
        'домен': PromptSpec(name='warehouse_x', domain='warehouse', title='Т', description='Д', render=lambda a: ''),
        'начинаться': PromptSpec(name='stocks_x', domain='content', title='Т', description='Д', render=lambda a: ''),
        'title': PromptSpec(name='content_notitle', domain='content', title=' ', description='Д', render=lambda a: ''),
        'render': PromptSpec(name='content_norender', domain='content', title='Т', description='Д', render=None),
        'повторяется': PromptSpec(name='content_dup', domain='content', title='Т', description='Д',
                                  arguments=(PromptArg('m', 'a'), PromptArg('m', 'b')), render=lambda a: ''),
        'имя аргумента': PromptSpec(name='content_badarg', domain='content', title='Т', description='Д',
                                    arguments=(PromptArg('месяц', 'a'),), render=lambda a: ''),
    }
    for needle, prompt in cases.items():
        errors = validate_prompt_spec(prompt)
        assert any(needle in e for e in errors), (needle, errors)
    modules = _modules()
    modules['content'].PROMPTS.append(cases['mode_required'])
    with Env(modules):
        assert registry.get_prompt('content_typo') is None
        assert any('mode_required' in e and 'content_typo' in e for e in registry.load_errors())
        assert registry.get_prompt('content_week') is not None, 'остальные сценарии опубликованы'


# ------------------------------------------------------------------ реестр и схемы

def test_registry_instructions_and_visibility():
    with Env():
        assert registry.domain_instructions('stocks') == 'ПРАВИЛА ОСТАТКОВ.'
        assert registry.instructions_for('analytics') == 'ОБЩИЕ ПРАВИЛА ТЕСТА.\n\nПРАВИЛА АНАЛИТИКИ.'
        assert registry.instructions_for('staff') == 'ОБЩИЕ ПРАВИЛА ТЕСТА.'
        assert [t.name for t in registry.tools_for('analytics')] == ['common_echo', 'common_refuse']
        assert registry.get_tool('broken_name') is None
        summary = {row['path']: row['tools'] for row in registry.summary()}
        assert summary == {'/mcp': 6, '/mcp/content': 5, '/mcp/stocks': 4, '/mcp/analytics': 2, '/mcp/staff': 2}
        assert registry.loaded_modules() == ['common', 'content', 'stocks', 'analytics']


def test_schema_check_rules():
    int_schema = {'type': 'integer', 'minimum': 1, 'maximum': 10}
    assert schema_check.check(int_schema, 5) == [] and schema_check.check(int_schema, 5.0) == []
    assert schema_check.check(int_schema, True), 'bool — не целое'
    assert schema_check.check(int_schema, 5.5) and schema_check.check(int_schema, 0) and schema_check.check(int_schema, 11)
    assert schema_check.check({'type': 'number'}, 1) == [] and schema_check.check({'type': 'number'}, False)
    assert schema_check.check({'type': 'number'}, float('inf'))
    assert schema_check.check({'type': 'boolean'}, 0) and schema_check.check({'type': 'boolean'}, True) == []
    assert schema_check.check({'type': ['string', 'null']}, None) == []
    assert schema_check.check({'enum': [1, 2]}, True), 'True не равен 1 для enum'
    assert schema_check.check({'enum': ['bar1']}, 'bar1') == [] and schema_check.check({'const': 'x'}, 'y')
    obj = {'type': 'object', 'additionalProperties': False, 'required': ['a'],
           'properties': {'a': {'type': 'string', 'minLength': 2, 'maxLength': 4, 'pattern': r'^\d+$'},
                          'items': {'type': 'array', 'minItems': 1, 'maxItems': 2, 'uniqueItems': True,
                                    'items': {'type': 'object', 'required': ['q'],
                                              'properties': {'q': {'type': 'integer'}}}},
                          'day': {'type': 'string', 'format': 'date'},
                          'at': {'type': 'string', 'format': 'date-time'}}}
    assert schema_check.check(obj, {'a': '12', 'items': [{'q': 1}], 'day': '2026-02-28',
                                    'at': '2026-02-28T10:00:00+03:00'}) == []
    errors = schema_check.check(obj, {'items': [{'q': 1}, {'q': 1}, {}], 'x': 1, 'day': '2026-02-30',
                                      'at': 'вчера'})
    text = '\n'.join(errors)
    for fragment in ('Не хватает обязательного поля «a»', 'Лишнее поле «x»', 'не больше 2 элем.',
                     'уникальными', 'Не хватает обязательного поля «items[2].q»', 'Поле «day»: ожидается дата',
                     'Поле «at»: ожидается дата и время'):
        assert fragment in text, (fragment, text)
    assert schema_check.check(obj, {'a': '1'})[0].startswith('Поле «a»: строка короче 2')
    assert 'не подходит под шаблон' in schema_check.check(obj, {'a': 'ab'})[0]
    assert schema_check.check({'anyOf': [{'type': 'string'}, {'type': 'integer'}]}, 1.5)
    assert schema_check.check({'oneOf': [{'type': 'integer'}, {'type': 'number'}]}, 3), 'подходит под оба'
    many = schema_check.check({'type': 'object', 'additionalProperties': False, 'properties': {}},
                              {str(i): i for i in range(30)})
    assert len(many) == schema_check.MAX_ERRORS
    assert schema_check.validate_arguments(NO_ARGS, {}) is None and schema_check.validate_arguments(NO_ARGS, None) is None
    message = schema_check.validate_arguments(obj, {}, 'content_x')
    assert message.startswith('Аргументы инструмента content_x не прошли проверку:')
    assert schema_check.normalize(obj, {'items': [{'q': 2.0}], 'a': '12'}) == {'items': [{'q': 2}], 'a': '12'}
    assert schema_check.normalize({'type': 'number'}, 2.0) == 2.0


# ------------------------------------------------------------------ служебные инструменты common

class CommonEnv:
    """Настоящие модули реестра, временные mcp.db/auth.db, владелец-админ."""

    def __enter__(self):
        from core.mcp.principal import Principal
        self.tmp = tempfile.mkdtemp(prefix='mcp_common_test_')
        self.saved_mgr = am._auth_manager
        self.saved_token = os.environ.get('TELEGRAM_OPEN_CHECK_BOT_TOKEN')
        self.mgr = am.AuthManager(db_path=os.path.join(self.tmp, 'auth.db'))
        am._auth_manager = self.mgr
        db.set_db_path(os.path.join(self.tmp, 'mcp.db'))
        registry.use_modules(None)
        owner = self.mgr.get_by_id(self.mgr.create_user('owner', 'Владелец', 'ownerpass', is_admin=True))
        self.principal = Principal(user_id=owner['id'], login='owner', display_name='Владелец', token_id='st_c',
                                   token_kind='static', client_name='ноутбук', domains=('content',))
        return self

    def __exit__(self, *exc):
        if self.saved_token is None:
            os.environ.pop('TELEGRAM_OPEN_CHECK_BOT_TOKEN', None)
        else:
            os.environ['TELEGRAM_OPEN_CHECK_BOT_TOKEN'] = self.saved_token
        am._auth_manager = self.saved_mgr
        db.set_db_path(None)
        registry.reset()
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def call(self, name, args=None, connector='content', mode='full'):
        from core.mcp import bridge
        return bridge.execute(registry.get_tool(name), args or {}, self.principal, connector=connector, mode=mode)


def test_common_whoami_and_instructions():
    with CommonEnv() as env:
        who = json.loads(env.call('common_whoami').text_value)
        assert who['owner'] == {'login': 'owner', 'display_name': 'Владелец'}
        assert who['token']['domains'] == ['content'] and who['token']['client'] == 'ноутбук'
        assert who['connector']['path'] == '/mcp/content' and who['connector']['tools'] == \
            len(registry.tools_for('content'))
        assert who['now_msk'].endswith('+03:00') and len(who['business_day']) == 10
        assert [d['domain'] for d in who['domains']] == ['content', 'stocks', 'analytics', 'staff']
        assert [d['token_allows'] for d in who['domains']] == [True, False, False, False]
        assert who['connector']['mode'] == 'full' and who['connector']['tools_hidden_by_mode'] == 0
        assert who['token']['mode'] == 'full'
        assert json.loads(env.call('common_whoami', connector=None).text_value)['connector']['path'] == '/mcp'
        read = json.loads(env.call('common_whoami', mode='read').text_value)['connector']
        assert read['mode'] == 'read' and read['mode_title'] == 'Только чтение'
        assert read['tools_hidden_by_mode'] > 0 and read['tools'] + read['tools_hidden_by_mode'] == \
            len(registry.tools_for('content'))
        text = env.call('common_instructions', {'domain': 'common'}).text_value
        assert text.startswith('# Общие правила (common)') and 'ПРАВИЛА БЕЗОПАСНОСТИ' in text
        for domain in ('content', 'stocks', 'analytics', 'staff'):
            result = env.call('common_instructions', {'domain': domain})
            assert not result.is_error and len(result.text_value) > 500, domain
        assert env.call('common_instructions', {'domain': 'warehouse'}).is_error


def test_common_bars_reference_from_code():
    from core import venues_config
    from core.taplist import BAR_NAMES
    with CommonEnv() as env:
        ref = json.loads(env.call('common_bars_reference').text_value)
        bars = {b['venue_key']: b for b in ref['bars']}
        assert list(bars) == venues_config.PHYSICAL_VENUES
        for key, bar in bars.items():
            assert bar['iiko_name'] == venues_config.KEY_TO_IIKO_NAME[key]
            assert BAR_NAMES[bar['bar_id']] == bar['iiko_name'], 'bar1..bar4 сведены через имя iiko'
            assert bar['taps'] == venues_config.VENUES[key]['taps']
        assert bars['bolshoy']['bar_id'] == 'bar1' and bars['varshavskaya']['bar_id'] == 'bar4'
        assert ref['all_venues']['venue_key'] == 'all'
        assert any('Варш' in n and 'Вар' in n for n in ref['notes']), 'расхождение коротких подписей названо'
        assert any('schedule_location_id' in n for n in ref['notes'])


def test_common_docs_whitelist_and_reading():
    from core.mcp.tools import common
    with CommonEnv() as env:
        listed = json.loads(env.call('common_docs_list').text_value)
        names = [d['name'] for d in listed['docs']]
        assert 'wiki/content.md' in names
        whitelist = common.docs_whitelist()
        assert set(whitelist) <= set(common.DOCS_ALLOWLIST) | {'wiki/content.md'}, 'только явный список'
        assert sorted(names) == sorted(whitelist)
        assert not any(n.startswith(('docs/archive/', 'docs/iiko-api/')) for n in whitelist)
        filtered = json.loads(env.call('common_docs_list', {'query': 'wiki'}).text_value)
        assert [d['name'] for d in filtered['docs']] == ['wiki/content.md']
        first = json.loads(env.call('common_docs_read', {'name': 'wiki/content.md', 'limit': 300}).text_value)
        assert first['returned_chars'] == 300 and first['next_offset'] == 300 and first['headings']
        rest = json.loads(env.call('common_docs_read', {'name': 'wiki/content.md', 'offset': 300,
                                                        'limit': 50000}).text_value)
        assert rest['offset'] == 300 and 'headings' not in rest
        heading = first['headings'][0].lstrip('#').strip()
        section = json.loads(env.call('common_docs_read', {'name': 'wiki/content.md',
                                                           'section': heading}).text_value)
        assert section['section'] == heading and section['text'].lstrip('#').strip().startswith(heading)
        missing_section = env.call('common_docs_read', {'name': 'wiki/content.md', 'section': 'нет такого раздела'})
        assert missing_section.is_error and 'Разделы:' in missing_section.text_value
        for bad in ('../config.py', 'docs/../config.py', 'wiki/../config.py', '/etc/passwd', 'C:/Windows/win.ini',
                    'docs/archive/anything.md', '..\\app.py', 'config', 'docs/CONNECTIVITY.md', 'CONNECTIVITY',
                    'docs/remote-sync.md', 'docs/auth.md', 'docs/guides/DEPLOYMENT_GUIDE.md'):
            result = env.call('common_docs_read', {'name': bad})
            assert result.is_error and 'нет в списке' in result.text_value, bad
        if 'docs/lessons.md' in whitelist:
            short = json.loads(env.call('common_docs_read', {'name': 'lessons', 'limit': 10}).text_value)
            assert short['name'] == 'docs/lessons.md', 'имя без docs/ и .md'


def test_common_notify_owner_rules():
    from core.mcp import settings
    from core.mcp.tools import common
    import core.open_check_telegram as tg
    sent = []
    saved = (tg.send_message, common.NOTIFY_DAILY_LIMIT)
    tg.send_message = lambda chat_id, text, **kw: sent.append((chat_id, text)) or True
    try:
        with CommonEnv() as env:
            os.environ.pop('TELEGRAM_OPEN_CHECK_BOT_TOKEN', None)
            result = env.call('common_notify_owner', {'text': 'Отчёт готов'})
            assert result.is_error and 'не выбран' in result.text_value, 'нет чата'
            settings.set('notify_chat_id', '670033096')
            result = env.call('common_notify_owner', {'text': 'Отчёт готов'})
            assert result.is_error and 'TELEGRAM_OPEN_CHECK_BOT_TOKEN' in result.text_value, 'нет токена бота'
            os.environ['TELEGRAM_OPEN_CHECK_BOT_TOKEN'] = 'test-token'
            common.NOTIFY_DAILY_LIMIT = 2
            ok = env.call('common_notify_owner', {'text': 'Отчёт готов'})
            assert not ok.is_error and 'Отправлено в чат 670033096' in ok.text_value, ok.text_value
            assert sent == [('670033096', 'Агент «ноутбук» (MCP):\n\nОтчёт готов')]
            tg.send_message = lambda chat_id, text, **kw: False
            failed = env.call('common_notify_owner', {'text': 'второй'})
            assert failed.is_error and 'не отправлено' in failed.text_value
            tg.send_message = lambda chat_id, text, **kw: True
            assert not env.call('common_notify_owner', {'text': 'третий'}).is_error, \
                'неудачная отправка не съела место в лимите'
            limited = env.call('common_notify_owner', {'text': 'четвёртый'})
            assert limited.is_error and 'Лимит' in limited.text_value
            assert env.call('common_notify_owner', {'text': ''}).is_error, 'minLength'
            spec = registry.get_tool('common_notify_owner')
            assert spec.open_world and not spec.read_only and spec.destructive
    finally:
        tg.send_message, common.NOTIFY_DAILY_LIMIT = saved


def test_common_audit_recent_and_connection_status_spec():
    with CommonEnv() as env:
        mine = env.principal.token_id
        audit.record(tool='content_plan_get', status='ok', connector='content', token_id=mine)
        audit.record(tool='stocks_board', status='error', connector='stocks', error='iiko недоступен', token_id=mine)
        audit.record(tool='staff_salary_calc', status='ok', connector='staff', token_id='st_other_night_agent')
        own = json.loads(env.call('common_audit_recent', {'limit': 5}).text_value)
        assert own['scope'] == 'this_token'
        assert [i['tool'] for i in own['items']] == ['stocks_board', 'content_plan_get'], 'чужой токен не виден'
        only = json.loads(env.call('common_audit_recent', {'status': 'error'}).text_value)
        assert only['count'] == 1 and only['items'][0]['error_preview'] == 'iiko недоступен'
        for connector, mode in (('content', 'full'), (None, 'draft'), (None, 'read')):
            denied = env.call('common_audit_recent', {'all_tokens': True}, connector=connector, mode=mode)
            assert denied.is_error and 'полном режиме полного коннектора' in denied.text_value, (connector, mode)
        everything = json.loads(env.call('common_audit_recent', {'all_tokens': True}, connector=None).text_value)
        assert everything['scope'] == 'all_tokens' and len(everything['items']) == 3
        spec = registry.get_tool('common_connection_status')
        assert (spec.method, spec.path, spec.heavy, spec.read_only) == ('GET', '/api/connection-status', True, True)


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
