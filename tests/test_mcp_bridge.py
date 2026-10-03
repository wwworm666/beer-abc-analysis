"""
Тесты моста MCP -> Flask (core/mcp/bridge.py): инструмент исполняет НАСТОЯЩИЙ маршрут
сайта от имени владельца и отдаёт ровно те же данные, что страница.

Совместимы с pytest и запускаются сами: `py -3 tests/test_mcp_bridge.py`.

Что доказывается:
- GET через мост == прямой вызов тестовым клиентом под входом владельца (JSON один в
  один) на реальных маршрутах с данными во временной папке: справочник поставщиков,
  контент-план, отзывы, полоса «требует внимания»;
- изменение через мост идёт от имени владельца с пометкой via_mcp: материал контент-плана
  получает origin='agent' и подпись «owner · агент», а тот же POST со страницы — 'human';
- send_file / send_from_directory (direct_passthrough): картинка приходит image-блоком,
  байты совпадают с файлом; большой файл не читается в память и приходит ссылкой;
- свежий контекст приложения: g внешнего MCP-запроса и g маршрута не смешиваются;
- multipart с файлом, повтор ключей строки запроса, кодирование булевых, экранирование пути;
- структурное обрезание JSON (всегда валидный JSON), текст, бинарные вложения, 3xx, 4xx,
  исключение маршрута, семафор тяжёлых вызовов, защита от рекурсии, обработчики.
Глобальное состояние (каталог данных, синглтоны хранилищ, auth_manager, mcp.db)
возвращается на место после каждого теста — в CI все тесты идут одним процессом.
"""

import base64
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import (Blueprint, Flask, Response, g, jsonify, redirect, request, send_file,  # noqa: E402
                   stream_with_context)

import core.auth_manager as am  # noqa: E402
import core.content_plan as core_cp  # noqa: E402
import core.guest_reviews as core_reviews  # noqa: E402
import core.order_store as core_orders  # noqa: E402
import core.stock_snapshot as stock_snapshot  # noqa: E402
import core.storage_paths as storage_paths  # noqa: E402
import core.supplier_directory as core_suppliers  # noqa: E402
from core.auth_guard import admin_required, current_user, init_auth  # noqa: E402
from core.mcp import bridge, db  # noqa: E402
from core.mcp.bridge import ToolError, ToolResult  # noqa: E402
from core.mcp.principal import Principal  # noqa: E402
from core.mcp.spec import ToolSpec  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTER_BASE = 'https://kultura.example/'
NO_ARGS = {'type': 'object', 'properties': {}, 'additionalProperties': False}


def _png() -> bytes:
    """Настоящий PNG 1x1 (сигнатуру проверяет core/content_media.check)."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b''))


def spec(name='content_t_tool', path='/api/t/echo', method='GET', **kw):
    """ToolSpec для теста (домен content — любой подходит, мосту всё равно)."""
    base = dict(name=name, domain='content', title='Тест', description='Тестовый инструмент проверки моста MCP.',
                input_schema=kw.pop('input_schema', NO_ARGS), method=method, path=path,
                read_only=method == 'GET')
    base.update(kw)
    return ToolSpec(**base)


# ------------------------------------------------------------------ тестовые маршруты

test_bp = Blueprint('bridge_test', __name__)
STATE = {'big_file': None, 'calls': 0}


@test_bp.route('/api/t/whoami')
def t_whoami():
    user = current_user() or {}
    return jsonify({k: user.get(k) for k in ('login', 'display_name', 'is_admin', 'via_mcp', 'mcp_mode',
                                            'mcp_client', 'mcp_token_id', 'mcp_connection_id')})


@test_bp.route('/api/t/item/<item_id>')
def t_item(item_id):
    STATE['calls'] += 1
    return jsonify({'route': 'item', 'item_id': item_id})


@test_bp.route('/api/t/item/<item_id>/log')
def t_item_log(item_id):
    STATE['calls'] += 1
    return jsonify({'route': 'log', 'item_id': item_id})


@test_bp.route('/api/t/admin-only')
@admin_required
def t_admin_only():
    return jsonify({'ok': True, 'login': current_user()['login']})


@test_bp.route('/api/t/g')
def t_g():
    seen = {'outer_marker_visible': 'outer_marker' in g,
            'current_user_login': (g.get('_current_user') or {}).get('login')}
    g.inner_marker = 'inner'
    return jsonify(seen)


@test_bp.route('/api/t/echo', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def t_echo():
    STATE['calls'] += 1
    files = {}
    for key, storage in request.files.items():
        data = storage.read()
        files[key] = {'filename': storage.filename, 'mimetype': storage.mimetype, 'size': len(data),
                      'sha': base64.b64encode(data[:16]).decode('ascii')}
    return jsonify({'method': request.method, 'args': request.args.to_dict(flat=False),
                    'json': request.get_json(silent=True), 'form': request.form.to_dict(flat=False),
                    'files': files, 'host_url': request.host_url, 'remote_addr': request.remote_addr,
                    'content_type': request.mimetype})


@test_bp.route('/api/t/path/<path:name>')
def t_path(name):
    return jsonify({'name': name})


@test_bp.route('/api/t/int/<int:num>')
def t_int(num):
    return jsonify({'num': num, 'type': type(num).__name__})


@test_bp.route('/api/t/big-json')
def t_big_json():
    n = int(request.args.get('n', 5000))
    return jsonify({'total': n, 'rows': [{'i': i, 'text': 'строка номер %d' % i} for i in range(n)]})


@test_bp.route('/api/t/csv')
def t_csv():
    n = int(request.args.get('n', 10))
    body = 'id;name\n' + ''.join('%d;пиво %d\n' % (i, i) for i in range(n))
    return Response(body, mimetype='text/csv')


@test_bp.route('/api/t/stream')
def t_stream():
    def gen():
        yield 'начало '
        yield request.args.get('word', '')         # нужен живой запрос: stream_with_context
    return Response(stream_with_context(gen()), mimetype='text/plain')


@test_bp.route('/api/t/pdf')
def t_pdf():
    size = int(request.args.get('size', 100))
    return send_file(io.BytesIO(b'%PDF' + b'0' * size), mimetype='application/pdf', download_name='a.pdf')


@test_bp.route('/api/t/disk-file')
def t_disk_file():
    return send_file(STATE['big_file'], mimetype='application/octet-stream')


@test_bp.route('/api/t/empty', methods=['POST'])
def t_empty():
    return '', 204


@test_bp.route('/api/t/redirect')
def t_redirect():
    return redirect('/elsewhere?x=1')


@test_bp.route('/api/t/error')
def t_error():
    return jsonify({'error': 'Неизвестный бар', 'code': 'bad_bar'}), 400


@test_bp.route('/api/t/boom')
def t_boom():
    raise RuntimeError('маршрут сломался')


# ------------------------------------------------------------------ окружение

class Env:
    """Временный каталог данных + свежие синглтоны хранилищ + владелец-админ + приложение."""

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix='mcp_bridge_test_')
        self.saved = {
            'disk': storage_paths.RENDER_DISK_DIR,
            'mgr': am._auth_manager,
            'suppliers': core_suppliers._directory,
            'content_plan': core_cp._store,
            'reviews': core_reviews._store,
            'orders': core_orders._store,
            'nomenclature': stock_snapshot.get_stocks_nomenclature,
            'heavy_wait': bridge.HEAVY_WAIT_S,
        }
        storage_paths.RENDER_DISK_DIR = self.tmp
        core_suppliers._directory = None
        core_cp._store = None
        core_reviews._store = None
        core_orders._store = None
        stock_snapshot.get_stocks_nomenclature = lambda *a, **k: None     # справочник без iiko
        bridge.response_cache.clear()     # кэш тяжёлых чтений общий на процесс: тесты не делят его
        self.mgr = am.AuthManager(db_path=os.path.join(self.tmp, 'auth.db'))
        am._auth_manager = self.mgr
        db.set_db_path(os.path.join(self.tmp, 'mcp.db'))
        self.owner = self.mgr.get_by_id(self.mgr.create_user('owner', 'Владелец', 'ownerpass', is_admin=True))
        self.bob = self.mgr.get_by_id(self.mgr.create_user('bob', 'Боб', 'bobpass12'))
        self.principal = Principal(user_id=self.owner['id'], login='owner', display_name='Владелец',
                                   token_id='st_test', token_kind='static', client_name='тест-клиент')
        self.app = self._app()
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.owner['id']
        return self

    def __exit__(self, *exc):
        storage_paths.RENDER_DISK_DIR = self.saved['disk']
        am._auth_manager = self.saved['mgr']
        core_suppliers._directory = self.saved['suppliers']
        core_cp._store = self.saved['content_plan']
        core_reviews._store = self.saved['reviews']
        core_orders._store = self.saved['orders']
        stock_snapshot.get_stocks_nomenclature = self.saved['nomenclature']
        bridge.HEAVY_WAIT_S = self.saved['heavy_wait']
        bridge.response_cache.clear()
        db.set_db_path(None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    @staticmethod
    def _app():
        from routes.content_plan import content_plan_bp
        from routes.mcp import mcp_bp
        from routes.reviews import reviews_bp
        from routes.suppliers import suppliers_bp
        app = Flask('mcp_bridge_test', template_folder=os.path.join(ROOT, 'templates'),
                    static_folder=os.path.join(ROOT, 'static'))
        for bp in (suppliers_bp, content_plan_bp, reviews_bp, mcp_bp, test_bp):
            app.register_blueprint(bp)
        init_auth(app)          # настоящий гейт: мост обязан пройти его как владелец
        return app

    def run(self, tool, args=None, principal=None, connector='content'):
        """Вызов моста так, как его делает протокол: внутри внешнего MCP-запроса."""
        with self.app.test_request_context('/mcp/content', method='POST', base_url=OUTER_BASE,
                                           environ_base={'REMOTE_ADDR': '10.1.2.3'}):
            return bridge.execute(tool, args or {}, principal or self.principal, connector=connector)


def _json_of(result: ToolResult):
    assert not result.is_error, result.text_value
    return json.loads(result.text_value)


def _drop(value, keys=('now',)):
    if isinstance(value, dict):
        return {k: _drop(v, keys) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [_drop(v, keys) for v in value]
    return value


# ------------------------------------------------------------------ совпадение с сайтом

def test_get_suppliers_same_json_as_page():
    with Env() as env:
        tool = spec('stocks_t_suppliers', '/api/suppliers')
        direct = env.client.get('/api/suppliers')
        assert direct.status_code == 200
        result = env.run(tool)
        assert result.http_status == 200
        assert _json_of(result) == direct.get_json()


def test_get_content_plan_same_json_as_page():
    with Env() as env:
        env.client.post('/api/content-plan/materials', json={'month': '2026-09', 'title': 'Пятничный таплист'})
        tool = spec('content_t_plan', '/api/content-plan', query_params=('month',),
                    input_schema={'type': 'object', 'additionalProperties': False,
                                  'properties': {'month': {'type': 'string'}}})
        direct = env.client.get('/api/content-plan?month=2026-09')
        assert direct.status_code == 200, direct.get_json()
        via_bridge = _json_of(env.run(tool, {'month': '2026-09'}))
        assert _drop(via_bridge) == _drop(direct.get_json())
        assert [m['title'] for m in via_bridge['materials']] == ['Пятничный таплист']


def test_get_reviews_and_attention_same_json_as_page():
    with Env() as env:
        for path in ('/api/reviews', '/api/guest-hub/attention'):
            direct = env.client.get(path)
            assert direct.status_code == 200, (path, direct.status_code)
            result = env.run(spec('content_t_reviews', path))
            assert _drop(_json_of(result)) == _drop(direct.get_json()), path


# ------------------------------------------------------------------ изменения от имени владельца

def test_post_creates_material_as_owner_marked_agent():
    with Env() as env:
        tool = spec('content_t_create', '/api/content-plan/materials', method='POST', body='json',
                    read_only=False, input_schema={
                        'type': 'object', 'additionalProperties': False, 'required': ['month', 'title'],
                        'properties': {'month': {'type': 'string'}, 'title': {'type': 'string'},
                                       'agent_rationale': {'type': 'string'}}})
        result = env.run(tool, {'month': '2026-09', 'title': 'Новинки недели',
                                'agent_rationale': 'Пятница — пик продаж'})
        created = _json_of(result)['material']
        assert created['origin'] == 'agent', created.get('origin')
        assert created['created_by'] == 'owner · агент', created.get('created_by')
        assert created['agent_rationale'] == 'Пятница — пик продаж'
        # Тот же POST со страницы — материал человека.
        human = env.client.post('/api/content-plan/materials', json={'month': '2026-09', 'title': 'Руками'})
        assert human.get_json()['material']['origin'] == 'human'
        assert human.get_json()['material']['created_by'] == 'owner'
        # Страница видит оба материала с их происхождением (данные записаны, а не только отданы).
        listed = env.client.get('/api/content-plan?month=2026-09').get_json()['materials']
        assert {m['title']: m['origin'] for m in listed} == {'Новинки недели': 'agent', 'Руками': 'human'}


def test_put_supplier_with_cyrillic_path_changes_state():
    with Env() as env:
        tool = spec('stocks_t_supplier_put', '/api/suppliers/<path:name>', method='PUT', body='json',
                    read_only=False, path_params=('name',), input_schema={
                        'type': 'object', 'additionalProperties': False, 'required': ['name'],
                        'properties': {'name': {'type': 'string'}, 'lead_time_days': {'type': 'integer'},
                                       'delivery_weekdays': {'type': 'array', 'items': {'type': 'integer'}},
                                       'note': {'type': 'string'}}})
        result = env.run(tool, {'name': 'Пивной дом «Север»', 'lead_time_days': 3.0,
                                'delivery_weekdays': [1, 4], 'note': 'до 12:00'})
        payload = _json_of(result)
        record = payload['supplier']
        assert record['name'] == 'Пивной дом «Север»' and record['lead_time_days'] == 3
        assert record['delivery_weekdays'] == [1, 4]
        assert record['updated_by'] == 'owner', 'изменение подписано логином владельца'
        stored = core_suppliers.get_supplier_directory().get('Пивной дом «Север»')
        assert stored is not None and stored['note'] == 'до 12:00'
        # Прямой список со страницы видит то же изменение.
        names = {s['name'] for s in env.client.get('/api/suppliers').get_json()['suppliers']}
        assert 'Пивной дом «Север»' in names
        bad = env.run(tool, {'name': 'Пивной дом «Север»', 'lead_time_days': 999})
        assert bad.is_error and bad.http_status == 400 and 'Ошибка HTTP 400' in bad.text_value


# ------------------------------------------------------------------ файлы

def test_send_from_directory_image_matches_file():
    with Env() as env:
        store = core_cp.get_content_plan_store()
        png = _png()
        ok, name = store.media.save(png, store.today())
        assert ok, name
        tool = spec('content_t_media', '/api/content-plan/media/<name>', path_params=('name',), input_schema={
            'type': 'object', 'additionalProperties': False, 'required': ['name'],
            'properties': {'name': {'type': 'string'}}})
        direct = env.client.get(f'/api/content-plan/media/{name}')
        assert direct.status_code == 200 and direct.data == png
        result = env.run(tool, {'name': name})
        assert not result.is_error, result.text_value
        kinds = [b['type'] for b in result.content]
        assert kinds == ['text', 'image'], kinds
        image = result.content[1]
        assert image['mimeType'] == 'image/png'
        assert base64.b64decode(image['data']) == png == direct.data
        assert f'{OUTER_BASE}api/content-plan/media/{name}' in result.content[0]['text'], 'полный внешний адрес'
        missing = env.run(tool, {'name': 'cp_20260101_000000000000.png'})
        assert missing.is_error and missing.http_status == 404


def test_binary_blob_and_big_files_as_links():
    with Env() as env:
        small = env.run(spec('content_t_pdf', '/api/t/pdf', query_params=('size',), input_schema={
            'type': 'object', 'additionalProperties': False, 'properties': {'size': {'type': 'integer'}}}),
            {'size': 1000})
        assert [b['type'] for b in small.content] == ['text', 'resource']
        res = small.content[1]['resource']
        assert res['mimeType'] == 'application/pdf' and base64.b64decode(res['blob']).startswith(b'%PDF')
        assert res['uri'] == OUTER_BASE + 'api/t/pdf?size=1000'
        big = env.run(spec('content_t_pdf', '/api/t/pdf', query_params=('size',), input_schema={
            'type': 'object', 'additionalProperties': False, 'properties': {'size': {'type': 'integer'}}}),
            {'size': bridge.BLOB_INLINE_MAX_BYTES + 10})
        assert not big.is_error and [b['type'] for b in big.content] == ['text']
        assert 'больше предела' in big.text_value and OUTER_BASE + 'api/t/pdf?size=' in big.text_value
        # Файл на диске (send_file по пути, direct_passthrough) больше предела: ссылка, тело не читается.
        path = os.path.join(env.tmp, 'big.bin')
        with open(path, 'wb') as f:
            f.write(b'\0' * (bridge.BLOB_INLINE_MAX_BYTES + 1))
        STATE['big_file'] = path
        on_disk = env.run(spec('content_t_disk', '/api/t/disk-file'))
        assert not on_disk.is_error and 'больше предела' in on_disk.text_value, on_disk.text_value
        with open(path, 'wb') as f:
            f.write(b'abc')
        small_disk = env.run(spec('content_t_disk', '/api/t/disk-file'))
        assert base64.b64decode(small_disk.content[1]['resource']['blob']) == b'abc'


def test_multipart_upload_with_fields():
    with Env() as env:
        tool = spec('content_t_upload', '/api/t/echo', method='POST', body='multipart', read_only=False,
                    file_params=('file',), input_schema={
                        'type': 'object', 'additionalProperties': False, 'required': ['file'],
                        'properties': {'file': {'type': 'object'}, 'status': {'type': 'string'},
                                       'keep_photo': {'type': 'boolean'}, 'tags': {'type': 'array'}}})
        png = _png()
        result = env.run(tool, {'file': {'filename': 'фото.png', 'content_base64': base64.b64encode(png).decode(),
                                         'mime_type': 'image/png'},
                                'status': 'clean', 'keep_photo': True, 'tags': ['a', 'b']})
        echo = _json_of(result)
        assert echo['method'] == 'POST' and echo['content_type'] == 'multipart/form-data'
        assert echo['files']['file']['filename'] == 'фото.png' and echo['files']['file']['size'] == len(png)
        assert echo['files']['file']['mimetype'] == 'image/png'
        assert echo['form'] == {'keep_photo': ['1'], 'status': ['clean'], 'tags': ['a', 'b']}
        bad = env.run(tool, {'file': {'filename': 'x.png', 'content_base64': 'не base64!'}})
        assert bad.is_error and 'base64' in bad.text_value


# ------------------------------------------------------------------ запрос и пользователь

def test_query_lists_bools_and_json_body():
    with Env() as env:
        tool = spec('content_t_query', '/api/t/echo', query_params=('bar', 'force', 'limit'), input_schema={
            'type': 'object', 'additionalProperties': False,
            'properties': {'bar': {'type': 'array', 'items': {'type': 'string'}}, 'force': {'type': 'boolean'},
                           'limit': {'type': 'integer'}}})
        echo = _json_of(env.run(tool, {'bar': ['bar1', 'bar3'], 'force': True, 'limit': 5.0}))
        assert echo['args'] == {'bar': ['bar1', 'bar3'], 'force': ['1'], 'limit': ['5']}
        assert echo['host_url'] == OUTER_BASE, 'внешний адрес сайта проброшен в маршрут'
        assert echo['remote_addr'] == '10.1.2.3'
        assert _json_of(env.run(tool, {'force': False}))['args'] == {'force': ['0']}
        post = spec('content_t_post', '/api/t/echo', method='POST', body='json', read_only=False,
                    query_params=('month',), input_schema={
                        'type': 'object', 'additionalProperties': False,
                        'properties': {'month': {'type': 'string'}, 'ids': {'type': 'array'},
                                       'flag': {'type': 'boolean'}}})
        echo = _json_of(env.run(post, {'month': '2026-09', 'ids': [1, 2], 'flag': False}))
        assert echo['args'] == {'month': ['2026-09']} and echo['json'] == {'ids': [1, 2], 'flag': False}
        echo = _json_of(env.run(post, {}))
        assert echo['json'] == {}, 'body=json всегда шлёт объект (маршруты с get_json() без silent)'
        form = spec('content_t_form', '/api/t/echo', method='POST', body='form', read_only=False, input_schema={
            'type': 'object', 'additionalProperties': False,
            'properties': {'note': {'type': 'string'}, 'n': {'type': 'integer'}}})
        echo = _json_of(env.run(form, {'note': 'привет', 'n': 2}))
        assert echo['form'] == {'n': ['2'], 'note': ['привет']}
        assert echo['content_type'] == 'application/x-www-form-urlencoded'


def test_path_params_escaping():
    with Env() as env:
        tool = spec('content_t_path', '/api/t/path/<path:name>', path_params=('name',), input_schema={
            'type': 'object', 'additionalProperties': False, 'required': ['name'],
            'properties': {'name': {'type': 'string'}}})
        for value in ('Пивной дом/СПб', 'a b?c#d&e=f', '100%'):
            assert _json_of(env.run(tool, {'name': value})) == {'name': value}, value
        num = spec('content_t_int', '/api/t/int/<int:num>', path_params=('num',), input_schema={
            'type': 'object', 'additionalProperties': False, 'required': ['num'],
            'properties': {'num': {'type': 'integer'}}})
        assert _json_of(env.run(num, {'num': 42})) == {'num': 42, 'type': 'int'}
        assert bridge.build_path(num, {'num': 7.0}) == '/api/t/int/7'


def test_owner_injected_and_gate_passed():
    with Env() as env:
        who = _json_of(env.run(spec('content_t_who', '/api/t/whoami')))
        assert who == {'login': 'owner', 'display_name': 'Владелец', 'is_admin': True, 'via_mcp': True,
                       'mcp_mode': 'full', 'mcp_client': 'тест-клиент', 'mcp_token_id': 'st_test',
                       'mcp_connection_id': 'st_test'}            # статический токен — сам себе подключение
        assert _json_of(env.run(spec('content_t_admin', '/api/t/admin-only'))) == {'ok': True, 'login': 'owner'}
        anonymous = env.app.test_client().get('/api/t/whoami')
        assert anonymous.status_code == 401, 'без входа гейт закрыт — мост проходит его только как владелец'
        not_admin = Principal(user_id=env.bob['id'], login='bob', display_name='Боб', token_id='st_bob',
                              token_kind='static', client_name='x')
        denied = env.run(spec('content_t_who', '/api/t/whoami'), principal=not_admin)
        assert denied.is_error and denied.http_status == 401
        # OAuth: подключение — грант, а не access-токен (тот меняется каждый час)
        oauth_principal = Principal(user_id=env.principal.user_id, login='owner', display_name='Владелец',
                                    token_id='oa_0123456789ab', token_kind='oauth', client_name='Claude',
                                    grant_id='g_0123456789abcdef')
        who = _json_of(env.run(spec('content_t_who', '/api/t/whoami'), principal=oauth_principal))
        assert who['mcp_token_id'] == 'oa_0123456789ab' and who['mcp_connection_id'] == 'g_0123456789abcdef'


def test_effective_mode_reaches_route_and_handlers():
    """Маршрут видит действующий режим (контент-план в draft правит только черновики агента)."""
    with Env() as env:
        tool = spec('content_t_who', '/api/t/whoami')
        for mode in ('read', 'draft', 'full'):
            with env.app.test_request_context('/mcp/content', method='POST', base_url=OUTER_BASE):
                who = _json_of(bridge.execute(tool, {}, env.principal, connector='content', mode=mode))
            assert who['mcp_mode'] == mode and who['via_mcp'] is True and who['login'] == 'owner'
        seen = {}

        def handler(args, principal):
            seen['mode'] = bridge.current_call().mode
            return {}
        env.run(ToolSpec(name='common_t_mode', domain='common', title='т', description='тестовый обработчик '
                         'для режима вызова', input_schema=NO_ARGS, handler=handler))
        assert seen['mode'] == 'full'


def test_path_param_cannot_escape_its_route():
    """Значение параметра пути не уводит запрос в соседний маршрут (проверка по url_map)."""
    with Env() as env:
        item = spec('content_t_item', '/api/t/item/<item_id>', path_params=('item_id',), input_schema={
            'type': 'object', 'additionalProperties': False, 'required': ['item_id'],
            'properties': {'item_id': {'type': 'string'}}})
        assert _json_of(env.run(item, {'item_id': 'abc'})) == {'route': 'item', 'item_id': 'abc'}
        before = STATE['calls']
        escaped = env.run(item, {'item_id': 'abc/log'})
        assert escaped.is_error and 'Недопустимое значение параметра пути' in escaped.text_value
        assert '/api/t/item/<item_id>/log' in escaped.text_value
        assert STATE['calls'] == before, 'соседний маршрут не вызывался'
        # '%2F' остаётся литералом: одна раскодировка, как у настоящего запроса — тот же маршрут.
        assert _json_of(env.run(item, {'item_id': '%2F'})) == {'route': 'item', 'item_id': '%2F'}
        assert _json_of(env.run(item, {'item_id': 'a%2Flog'})) == {'route': 'item', 'item_id': 'a%2Flog'}
        for bad in ('', '/', 'x/'):
            result = env.run(item, {'item_id': bad})
            assert result.is_error and 'Недопустимое значение параметра пути' in result.text_value, bad
        # Настоящий случай из проверки: материал контент-плана и его журнал.
        material = spec('content_t_material', '/api/content-plan/materials/<material_id>',
                        path_params=('material_id',), input_schema={
                            'type': 'object', 'additionalProperties': False, 'required': ['material_id'],
                            'properties': {'material_id': {'type': 'string'}}})
        result = env.run(material, {'material_id': 'abc/log'})
        assert result.is_error and 'Недопустимое значение параметра пути' in result.text_value
        # path-конвертер законно принимает «/»: имя поставщика со слэшем проходит.
        supplier = spec('stocks_t_supplier', '/api/suppliers/<path:name>', method='PUT', body='json',
                        read_only=False, path_params=('name',), input_schema={
                            'type': 'object', 'additionalProperties': False, 'required': ['name'],
                            'properties': {'name': {'type': 'string'}, 'note': {'type': 'string'}}})
        record = _json_of(env.run(supplier, {'name': 'Пивной дом/СПб', 'note': 'x'}))['supplier']
        assert record['name'] == 'Пивной дом/СПб'


def test_heavy_wait_is_short():
    assert bridge.HEAVY_WAIT_S == 10, 'поток воркера нужен сайту: ждать iiko не дольше 10 с'


def test_fresh_app_context_isolates_g():
    with Env() as env:
        tool = spec('content_t_g', '/api/t/g')
        with env.app.test_request_context('/mcp/content', method='POST', base_url=OUTER_BASE):
            g.outer_marker = 'outer'
            g._current_user = {'login': 'intruder', 'is_admin': True, 'active': True}
            result = bridge.execute(tool, {}, env.principal, connector='content')
            seen = _json_of(result)
            assert seen == {'outer_marker_visible': False, 'current_user_login': 'owner'}, seen
            assert 'inner_marker' not in g, 'g маршрута не протёк в MCP-запрос'
            assert g.outer_marker == 'outer' and g._current_user['login'] == 'intruder'


# ------------------------------------------------------------------ упаковка ответов

def test_big_json_truncated_structurally_and_valid():
    with Env() as env:
        tool = spec('content_t_big', '/api/t/big-json', query_params=('n',), input_schema={
            'type': 'object', 'additionalProperties': False, 'properties': {'n': {'type': 'integer'}}})
        result = env.run(tool, {'n': 20000})
        assert result.truncated and not result.is_error
        text = result.text_value
        assert len(text) <= bridge.RESULT_TEXT_LIMIT
        first, rest = text.split('\n', 1)
        assert first.startswith('ВНИМАНИЕ: ответ обрезан')
        data = json.loads(rest)
        assert data['total'] == 20000
        marker = data['rows'][-1]
        assert set(marker) == {bridge.TRUNCATION_KEY}
        shown = len(data['rows']) - 1
        assert marker[bridge.TRUNCATION_KEY] == f'показано {shown} из 20000; сузьте фильтры'
        assert data['rows'][0] == {'i': 0, 'text': 'строка номер 0'}
        small = env.run(tool, {'n': 3})
        assert not small.truncated and json.loads(small.text_value)['total'] == 3


def test_shrink_json_edge_cases():
    for value in ({'a': ['x' * 50] * 3000}, ['я' * 100000], {'k%05d' % i: i for i in range(20000)},
                  'z' * 200000, [[list(range(50))] * 50] * 50):
        for budget in (5000, 20000):
            out = bridge.shrink_json(value, budget)
            assert len(out) <= budget, (budget, len(out))
            json.loads(out)
    assert bridge.shrink_json({'a': 1}, 100) == '{"a":1}'


def test_text_stream_redirect_empty_errors_exception():
    with Env() as env:
        csv_tool = spec('content_t_csv', '/api/t/csv', query_params=('n',), input_schema={
            'type': 'object', 'additionalProperties': False, 'properties': {'n': {'type': 'integer'}}})
        small = env.run(csv_tool, {'n': 2})
        assert small.text_value == 'id;name\n0;пиво 0\n1;пиво 1\n'
        big = env.run(csv_tool, {'n': 20000})
        assert big.truncated and len(big.text_value) <= bridge.RESULT_TEXT_LIMIT
        assert big.text_value.startswith('ВНИМАНИЕ: ответ обрезан — показаны первые')
        stream = spec('content_t_stream', '/api/t/stream', query_params=('word',), input_schema={
            'type': 'object', 'additionalProperties': False, 'properties': {'word': {'type': 'string'}}})
        assert env.run(stream, {'word': 'конец'}).text_value == 'начало конец'
        moved = env.run(spec('content_t_redirect', '/api/t/redirect'))
        assert not moved.is_error and moved.http_status == 302 and 'Перенаправление на' in moved.text_value
        assert '/elsewhere?x=1' in moved.text_value
        empty = env.run(spec('content_t_empty', '/api/t/empty', method='POST', read_only=False))
        assert not empty.is_error and 'ответ пустой' in empty.text_value
        err = env.run(spec('content_t_error', '/api/t/error'))
        assert err.is_error and err.http_status == 400
        assert err.text_value == 'Ошибка HTTP 400: Неизвестный бар\nПодробности: {"code":"bad_bar"}'
        assert err.error == 'Неизвестный бар'
        missing = env.run(spec('content_t_missing', '/api/t/no-such-route'))
        assert missing.is_error and missing.http_status == 404 and 'Ошибка HTTP 404' in missing.text_value
        wrong_method = env.run(spec('content_t_wrong', '/api/t/redirect', method='POST', read_only=False))
        assert wrong_method.is_error and wrong_method.http_status == 405
        boom = env.run(spec('content_t_boom', '/api/t/boom'))
        assert boom.is_error and boom.http_status == 500
        assert 'RuntimeError: маршрут сломался' in boom.text_value


# ------------------------------------------------------------------ ограничения

def test_schema_check_before_execution():
    with Env() as env:
        tool = spec('content_t_echo_q', '/api/t/echo', query_params=('limit',), input_schema={
            'type': 'object', 'additionalProperties': False, 'required': ['limit'],
            'properties': {'limit': {'type': 'integer', 'minimum': 1}}})
        before = STATE['calls']
        result = env.run(tool, {'limit': 'пять', 'extra': 1})
        assert result.is_error
        assert 'Поле «limit»: ожидается целое число' in result.text_value
        assert 'Лишнее поле «extra»' in result.text_value
        assert STATE['calls'] == before, 'маршрут не вызывался'
        assert env.run(tool, None).is_error, 'нет обязательного поля'
        assert bridge.execute(tool, ['не объект'], env.principal).is_error


def test_heavy_semaphore_times_out():
    with Env() as env:
        # no_cache: второй вызов должен идти в семафор, а не в кэш тяжёлых чтений.
        tool = spec('content_t_heavy', '/api/t/echo', heavy=True, no_cache=True)
        assert not env.run(tool).is_error, 'свободный семафор — вызов проходит и отпускает место'
        bridge.HEAVY_WAIT_S = 0.2
        taken = 0
        try:
            while bridge._HEAVY.acquire(blocking=False):
                taken += 1
            assert taken == bridge.HEAVY_CONCURRENCY
            before = STATE['calls']
            busy = env.run(tool)
            assert busy.is_error and 'iiko занят' in busy.text_value
            assert STATE['calls'] == before
        finally:
            for _ in range(taken):
                bridge._HEAVY.release()
        assert not env.run(tool).is_error


# ------------------------------------------------------------------ кэш тяжёлых чтений

_Q_SCHEMA = {'type': 'object', 'additionalProperties': False,
             'properties': {'bar': {'type': 'string'}, 'force': {'type': 'string', 'enum': ['0', '1']},
                            'n': {'type': 'integer'}}}


def test_heavy_read_cached_with_freshness_line():
    """Тяжёлое чтение: второй такой же вызов — из кэша, без маршрута; первая строка ответа
    «Данные на ЧЧ:ММ МСК (кэш до 5 минут)», JSON во втором блоке валиден."""
    import re as _re
    with Env() as env:
        tool = spec('content_t_heavy_read', '/api/t/echo', heavy=True, query_params=('bar', 'force', 'n'),
                    input_schema=_Q_SCHEMA)
        before = STATE['calls']
        first = env.run(tool, {'bar': 'Лиговский', 'n': 2.0})
        assert not first.is_error and not first.cached and STATE['calls'] == before + 1
        assert [b['type'] for b in first.content] == ['text', 'text']
        assert _re.fullmatch(r'Данные на \d\d:\d\d МСК \(кэш до 5 минут\)', first.content[0]['text']), \
            first.content[0]['text']
        payload = json.loads(first.content[1]['text'])
        assert payload['args'] == {'bar': ['Лиговский'], 'n': ['2']}
        again = env.run(tool, {'n': 2, 'bar': 'Лиговский'})        # порядок ключей и 2.0 -> 2 не важны
        assert again.cached and STATE['calls'] == before + 1, 'повтор не пошёл в маршрут'
        assert again.content[0]['text'] == first.content[0]['text'], 'время данных — время расчёта'
        assert json.loads(again.content[1]['text']) == payload
        other = env.run(tool, {'bar': 'Варшавская'})
        assert not other.cached and STATE['calls'] == before + 2, 'другие аргументы — другой ключ'
        # force='1' — явная просьба пересчитать: мимо кэша и без строки свежести.
        forced = env.run(tool, {'bar': 'Лиговский', 'n': 2, 'force': '1'})
        forced_again = env.run(tool, {'bar': 'Лиговский', 'n': 2, 'force': '1'})
        assert STATE['calls'] == before + 4 and not forced.cached and not forced_again.cached
        assert forced.content[0]['text'].startswith('{'), 'без строки «Данные на»'
        # Другой владелец токена — свой ключ.
        other_owner = Principal(user_id=env.owner['id'] + 100, login='owner', display_name='В', token_id='st_x',
                                token_kind='static', client_name='x')
        assert bridge.cache_key(tool, {'bar': 'Лиговский'}, env.principal) != \
            bridge.cache_key(tool, {'bar': 'Лиговский'}, other_owner)


def test_what_is_not_cached():
    """Не кэшируются: лёгкие чтения, open_world, no_cache, ошибки, файлы; запись очищает кэш."""
    with Env() as env:
        light = spec('content_t_light', '/api/t/echo')
        before = STATE['calls']
        assert not env.run(light).is_error and not env.run(light).cached
        assert STATE['calls'] == before + 2 and env.run(light).content[0]['text'].startswith('{')
        for flags in ({'open_world': True}, {'no_cache': True}):
            tool = spec('content_t_live', '/api/t/echo', heavy=True, **flags)
            n = STATE['calls']
            env.run(tool)
            second = env.run(tool)
            assert not second.cached and STATE['calls'] == n + 2, flags
        failing = spec('content_t_err', '/api/t/error', heavy=True)
        assert env.run(failing).is_error and not bridge.response_cache.stats()['entries']
        pdf = spec('content_t_pdf_heavy', '/api/t/pdf', heavy=True)
        result = env.run(pdf)
        assert [b['type'] for b in result.content] == ['text', 'resource'], 'файл — без строки свежести'
        assert bridge.response_cache.stats()['entries'] == 0
        # Запись через MCP (read_only=False, успешно) сбрасывает кэш тяжёлых чтений.
        heavy = spec('content_t_heavy_read', '/api/t/echo', heavy=True)
        env.run(heavy)
        assert env.run(heavy).cached and bridge.response_cache.stats()['entries'] == 1
        write = spec('content_t_write', '/api/t/echo', method='POST', body='json', read_only=False)
        assert not env.run(write).is_error
        assert bridge.response_cache.stats()['entries'] == 0
        n = STATE['calls']
        assert not env.run(heavy).cached and STATE['calls'] == n + 1, 'после записи — снова маршрут'
        # Неудачная запись (405 — маршрут не принимает POST) кэш не трогает.
        assert env.run(heavy).cached
        bad_write = spec('content_t_bad_write', '/api/t/error', method='POST', read_only=False)
        assert env.run(bad_write).is_error
        assert bridge.response_cache.stats()['entries'] == 1


def test_response_cache_limits_ttl_and_generation():
    """Пределы памяти (записи, байты, запись не больше четверти), срок, LRU, поколение."""
    from datetime import datetime
    stamp = datetime(2026, 9, 28, 14, 5)
    text = ToolResult.text
    cache = bridge.ResponseCache(ttl=300, max_entries=2, max_bytes=1000, entry_max_bytes=400)
    assert cache.put('a', text('x' * 100), stamp, now=0) and cache.put('b', text('y' * 100), stamp, now=0)
    assert cache.get('a', now=1) is not None                      # a — недавно использована
    assert cache.put('c', text('z' * 100), stamp, now=2)
    assert cache.get('b', now=3) is None, 'вытеснена самая давно использованная'
    assert cache.get('a', now=3) is not None and cache.get('c', now=3) is not None
    assert cache.get('a', now=1000) is None, 'срок 300 с истёк'
    assert not cache.put('big', text('я' * 300), stamp, now=0), 'больше entry_max_bytes (600 байт UTF-8)'
    by_bytes = bridge.ResponseCache(ttl=300, max_entries=10, max_bytes=500, entry_max_bytes=400)
    for i in range(4):
        by_bytes.put(str(i), text('q' * 200), stamp, now=0)
    assert by_bytes.stats()['entries'] == 2 and by_bytes.stats()['bytes'] <= 500
    gen = cache.generation
    cache.clear()
    assert not cache.put('late', text('старое'), stamp, generation=gen, now=0), \
        'чтение, начатое до записи, не кладёт данные «до записи»'
    assert cache.put('late', text('новое'), stamp, generation=cache.generation, now=0)
    assert bridge.freshness_line(stamp) == 'Данные на 14:05 МСК (кэш до 5 минут)'
    assert bridge.CACHE_TTL_S == 300 and bridge.CACHE_MAX_ENTRIES == 64
    assert bridge.CACHE_MAX_BYTES == 2 * 1024 * 1024
    for args, fresh in (({'force': '1'}, True), ({'refresh': True}, True), ({'full': 'true'}, True),
                        ({'force': '0'}, False), ({'force': False}, False), ({}, False), ({'bar': '1'}, False)):
        assert bridge.wants_fresh(args) is fresh, args


def test_admission_taken_only_for_real_execution():
    """Пропуск протокола (admit) берётся только перед исполнением: отказ — denied, маршрут не
    вызывается; ответ из кэша и ошибка схемы пропуск не берут."""
    from contextlib import contextmanager
    taken = []

    @contextmanager
    def admit_ok():
        taken.append('ok')
        yield None

    @contextmanager
    def admit_busy():
        taken.append('busy')
        yield ToolResult.refuse('Сервер занят', http_status=503)

    with Env() as env:
        tool = spec('content_t_heavy_read', '/api/t/echo', heavy=True, query_params=('n',),
                    input_schema=_Q_SCHEMA)
        with env.app.test_request_context('/mcp/content', method='POST', base_url=OUTER_BASE):
            before = STATE['calls']
            refused = bridge.execute(tool, {'n': 1}, env.principal, admit=admit_busy)
            assert refused.is_error and refused.denied and STATE['calls'] == before
            first = bridge.execute(tool, {'n': 1}, env.principal, admit=admit_ok)
            assert not first.is_error and STATE['calls'] == before + 1
            cached = bridge.execute(tool, {'n': 1}, env.principal, admit=admit_busy)
            assert cached.cached and not cached.is_error, 'кэш отвечает, даже когда мест нет'
            bad = bridge.execute(tool, {'n': 'пять'}, env.principal, admit=admit_ok)
            assert bad.is_error and not bad.denied
        assert taken == ['busy', 'ok'], taken


def test_recursion_guard():
    with Env() as env:
        for path in ('/mcp', '/mcp/<domain>', '/oauth/token', '/.well-known/oauth-protected-resource',
                     '/api/admin/mcp/tokens'):
            params = ('domain',) if '<domain>' in path else ()
            schema = {'type': 'object', 'additionalProperties': False, 'required': list(params),
                      'properties': {p: {'type': 'string'} for p in params}}
            tool = spec('content_t_rec', path, method='POST', read_only=False, path_params=params,
                        input_schema=schema)
            result = env.run(tool, {'domain': 'content'} if params else {})
            assert result.is_error and 'не исполняется' in result.text_value, path
        assert not bridge.is_forbidden_path('/mcpx') and not bridge.is_forbidden_path('/api/mcp-report')
        assert bridge.is_forbidden_path('/mcp/') and bridge.is_forbidden_path('/api/admin/mcp')


def test_handler_tools():
    seen = {}

    def ok_dict(args, principal):
        call = bridge.current_call()
        seen['connector'] = call.connector if call else None
        return {'hello': principal.login, 'n': args.get('n')}

    def fail(args, principal):
        raise ToolError('Не настроено: нет чата')

    def crash(args, principal):
        raise KeyError('oops')

    schema = {'type': 'object', 'additionalProperties': False, 'properties': {'n': {'type': 'integer'}}}
    with Env() as env:
        result = env.run(ToolSpec(name='common_t_h', domain='common', title='т', description='тестовый обработчик '
                                  'без маршрута', input_schema=schema, handler=ok_dict), {'n': 2}, connector='staff')
        assert json.loads(result.text_value) == {'hello': 'owner', 'n': 2} and seen['connector'] == 'staff'
        assert bridge.current_call() is None, 'контекст вызова сброшен'
        for handler, expected in ((fail, 'Не настроено: нет чата'), (crash, "KeyError: 'oops'")):
            res = env.run(ToolSpec(name='common_t_h', domain='common', title='т', description='тестовый '
                                   'обработчик без маршрута', input_schema=schema, handler=handler))
            assert res.is_error and expected in res.text_value, res.text_value
        for out, text in ((None, 'Готово.'), ('строка', 'строка'), (ToolResult.text('свой'), 'свой')):
            res = env.run(ToolSpec(name='common_t_h', domain='common', title='т', description='тестовый '
                                   'обработчик без маршрута', input_schema=schema,
                                   handler=lambda a, p, o=out: o))
            assert res.text_value == text and not res.is_error


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
