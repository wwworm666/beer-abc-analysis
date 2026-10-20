"""
Бот @MCPkulturabot на стороне сайта: секреты (kultura_bot/credentials.py), раздел «Бот»
страницы «Доступ агентов» (routes/mcp.py), ключ сервера бота и команда установки
(kultura_bot/site_api.py), API для сервера бота (/api/bot/*, routes/bot_api.py) и сквозная
связь «сервер бота в Амстердаме -> сайт»: настоящий kultura_bot/engine/site.py ходит в Flask
этого же процесса (requests -> test client). Разговор с Claude и Telegram — подменены, их
проверяет tests/test_kultura_bot.py.

Что проверяется:
- токен сохраняется только проверенным: формат «число:строка» и getMe в Telegram; отказ
  Telegram — ничего не записано; нет связи — записан с предупреждением; имя бота из getMe
  запоминается;
- ключ Anthropic: формат sk-ant-… (живую проверку делает сервер бота); на страницу —
  только подсказки «1234…xyz», серверу бота (engine_view) — целиком;
- страница важнее окружения, пустое — запасной путь из окружения; пауза;
- API страницы только для администратора: без входа 401, не-админу 403; лишние поля (и
  прежний proxy) — 400; ссылка привязки и отвязка; команда установки: ключ целиком только
  в ответе, новая команда отзывает прежний ключ;
- API бота: без ключа, с чужим MCP-токеном, с отозванным ключом и у бывшего администратора
  — 401; config отдаёт секреты и не кэшируется; link и actor; отчёт: проверка полей, расход
  складывается, состояние, ошибка Claude и «сервер не отвечает» на странице;
- сквозная связь: сервер бота по своему ключу читает настройки, берёт правила и
  инструменты по MCP (в журнале вызовов — имя ключа), привязывает Telegram, отвечает на
  вопрос с графиком (график — в чат разговора, токеном со страницы), расход доходит до
  страницы; отключение владельца ключа отзывает ключ — бот замолкает.

Запуск: `py -3 -m pytest tests/test_kultura_bot_site.py`.
"""
import json
import os
import re
import sys
import time
import urllib.parse

import pytest
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from core import msk_time  # noqa: E402
from core.mcp import audit, db, settings, tokens  # noqa: E402
from kultura_bot import access, credentials as cs, settings as bot_settings, site_api, store as bot_store  # noqa: E402

GOOD = '1234567890:' + 'A' * 35
OTHER = '987654321:' + 'b' * 35
KEY = 'sk-ant-api03-' + 'k' * 40
KEY2 = 'sk-ant-api03-' + 'z' * 40
BASE = 'https://kultura.example'
KEY_RE = re.compile(r"KULTURA_BOT_KEY='(kmcp_[A-Za-z0-9_-]+)'")


def getme_ok(username='MCPkulturabot'):
    calls = []

    def fake(token):
        calls.append(token)
        return {'ok': True, 'result': {'id': 1, 'is_bot': True, 'username': username}}
    fake.calls = calls
    return fake


def engine_key(command):
    match = KEY_RE.search(command)
    assert match, command
    return match.group(1)


@pytest.fixture
def store(tmp_path, monkeypatch):
    db.set_db_path(str(tmp_path / 'mcp.db'))
    for name in (cs.BOT_TOKEN_ENV, cs.ANTHROPIC_ENV):
        monkeypatch.delenv(name, raising=False)
    yield monkeypatch
    db.set_db_path(None)


# ------------------------------------------------------------------ секреты

def test_token_saved_after_telegram_check(store):
    fake = getme_ok('MCPkulturabot')
    view = cs.save(token=f'  {GOOD} ', getme=fake)
    assert fake.calls == [GOOD], 'getMe вызывается с токеном без пробелов'
    assert cs.bot_token() == GOOD and cs.token_source() == 'settings'
    assert view['telegram']['configured'] and view['telegram']['bot_username'] == 'MCPkulturabot'
    assert view['warnings'] == [] and view['telegram']['token_hint'] == '1234…AAA'
    assert GOOD not in repr(view), 'токен наружу не выходит'


def test_bad_tokens_are_not_saved(store):
    with pytest.raises(ValueError, match='Это не токен'):
        cs.save(token='не токен', getme=getme_ok())
    refused = lambda token: {'ok': False, 'error_code': 401, 'description': 'Unauthorized'}  # noqa: E731
    with pytest.raises(ValueError, match='Telegram не принял токен: Unauthorized'):
        cs.save(token=GOOD, anthropic_key_value=KEY, getme=refused)
    assert cs.bot_token() == '' and cs.anthropic_key() == '', 'отказ — ничего не записано, даже ключ'


def test_offline_save_keeps_token_with_warning(store):
    cs.save(token=GOOD, getme=getme_ok('FirstBot'))
    view = cs.save(token=OTHER, getme=lambda token: None)
    assert cs.bot_token() == OTHER and 'Нет связи с Telegram' in view['warnings'][0]
    assert view['telegram']['bot_username'] == 'FirstBot', 'имя бота без проверки не меняется'


def test_anthropic_key_checked_by_format_and_given_only_to_engine(store):
    with pytest.raises(ValueError, match='sk-ant-'):
        cs.save(anthropic_key_value='abc')
    view = cs.save(anthropic_key_value=f' {KEY} ')
    assert cs.anthropic_key() == KEY and view['warnings'] == []
    assert view['anthropic'] == {'configured': True, 'source': 'settings', 'key_hint': 'sk-a…kkk'}
    assert KEY not in repr(view) and KEY not in repr(cs.public_view())
    cs.save(token=GOOD, getme=getme_ok())
    assert cs.engine_view() == {'telegram': {'token': GOOD, 'username': 'MCPkulturabot'}, 'anthropic_key': KEY,
                                'paused': False}, 'серверу бота — целиком'


def test_settings_win_over_environment_and_clear_falls_back(store):
    store.setenv(cs.BOT_TOKEN_ENV, OTHER)
    store.setenv(cs.ANTHROPIC_ENV, KEY2)
    assert cs.bot_token() == OTHER and cs.token_source() == 'env' and cs.anthropic_key() == KEY2
    cs.save(token=GOOD, anthropic_key_value=KEY, getme=getme_ok())
    assert cs.bot_token() == GOOD and cs.anthropic_key() == KEY
    view = cs.save(clear_token=True, clear_anthropic_key=True)
    assert cs.bot_token() == OTHER and view['telegram']['source'] == 'env' and cs.anthropic_key() == KEY2
    store.delenv(cs.BOT_TOKEN_ENV)
    assert cs.public_view()['telegram']['configured'] is False


def test_pause(store):
    assert cs.paused() is False
    cs.save(paused_value=True)
    assert cs.paused() is True and cs.public_view()['paused'] is True and cs.engine_view()['paused'] is True
    with pytest.raises(ValueError, match='Пауза'):
        cs.save(paused_value='да')


# ------------------------------------------------------------------ API страницы «Доступ агентов»

def test_admin_api(store):
    import test_mcp_tokens as tt
    store.setattr(cs, '_getme', getme_ok('MCPkulturabot'))
    with tt.Env() as env:
        client = tt._admin_app().test_client()
        assert client.get('/api/admin/mcp/bot').status_code == 401, 'без входа'
        assert client.post('/api/admin/mcp/bot/install').status_code == 401
        tt._login(client, 'bob', 'bobpass12')
        assert client.get('/api/admin/mcp/bot').status_code == 403
        assert client.put('/api/admin/mcp/bot', json={'token': GOOD}).status_code == 403
        assert client.post('/api/admin/mcp/bot/link').status_code == 403
        assert client.post('/api/admin/mcp/bot/install').status_code == 403
        assert site_api.engine_token_id() == '', 'не-админ ключ не выпустил'
        client = tt._admin_app().test_client()
        tt._login(client, 'owner', 'ownerpass')
        view = client.get('/api/admin/mcp/bot').get_json()
        assert view['telegram']['configured'] is False and view['anthropic']['configured'] is False
        assert view['status']['state'] == 'stopped' and view['links'] == [] and view['model']
        assert view['engine'] == {'issued': False} and 'proxy' not in view
        r = client.put('/api/admin/mcp/bot', json={'token': GOOD, 'anthropic_key': KEY, 'paused': False})
        assert r.status_code == 200, r.get_json()
        body = r.get_data(as_text=True)
        assert GOOD not in body and KEY not in body and r.get_json()['telegram']['token_hint'] == '1234…AAA'
        assert settings.get(cs.KEY_TOKEN) == GOOD and settings.updated_info(cs.KEY_TOKEN)['updated_by'] == 'owner'
        for bad in ({'token': 'плохой'}, {'anthropic_key': 5}, {'secret': 1}, {'paused': 'да'},
                    {'proxy': 'http://proxy.example:3128'}):
            assert client.put('/api/admin/mcp/bot', json=bad).status_code == 400, bad

        link = client.post('/api/admin/mcp/bot/link').get_json()
        assert link['url'].startswith('https://t.me/MCPkulturabot?start=') and link['expires_in_s'] == 900
        answer = access.link_by_code(link['code'], '555', 'Анна')
        assert answer['ok'] and 'Владелец' in answer['text']
        links = client.get('/api/admin/mcp/bot').get_json()['links']
        assert [(x['tg_user_id'], x['login'], x['tg_name']) for x in links] == [('555', 'owner', 'Анна')]
        assert client.delete('/api/admin/mcp/bot/links/abc').status_code == 400
        assert client.delete('/api/admin/mcp/bot/links/555').get_json() == {'ok': True}
        assert bot_store.list_links() == []

        first = client.post('/api/admin/mcp/bot/install').get_json()
        key1 = engine_key(first['command'])
        assert first['command'] == f"curl -fsSL {bot_settings.INSTALL_SCRIPT_URL} | KULTURA_BOT_KEY='{key1}' bash"
        assert first['token_prefix'] == key1[:12] and first['script_url'] == bot_settings.INSTALL_SCRIPT_URL
        row = tokens.get(site_api.engine_token_id())
        assert (row['name'], row['domains'], row['mode'], row['expires_at'], row['user_login']) == \
            (site_api.ENGINE_TOKEN_NAME, ['*'], 'full', None, 'owner')
        view = client.get('/api/admin/mcp/bot').get_json()
        assert view['engine']['issued'] and view['engine']['active'] and view['engine']['prefix'] == key1[:12]
        assert view['engine']['owner'] == 'owner'
        assert key1 not in json.dumps(view, ensure_ascii=False), 'ключ целиком — только в ответе на кнопку'
        second = client.post('/api/admin/mcp/bot/install').get_json()
        key2 = engine_key(second['command'])
        assert key2 != key1 and tokens.get(row['id'])['status'] == 'revoked', 'новая команда — прежний ключ отозван'
        assert site_api.verify_engine(key1) is None and site_api.verify_engine(key2) is not None
        assert env.owner['login'] == 'owner'


# ------------------------------------------------------------------ API сервера бота

class FlaskAdapter(requests.adapters.BaseAdapter):
    """requests -> Flask этого процесса: сервер бота говорит с сайтом без сети."""

    def __init__(self, app):
        super().__init__()
        self.client = app.test_client()
        self.sent = []          # (метод, путь, Authorization)

    def send(self, request, **kwargs):
        url = urllib.parse.urlsplit(request.url)
        headers = {k: v for k, v in request.headers.items() if k.lower() != 'content-length'}
        self.sent.append((request.method, url.path, headers.get('Authorization', '')))
        got = self.client.open(url.path, method=request.method, headers=headers, data=request.body,
                               query_string=url.query, base_url=f'{url.scheme}://{url.netloc}')
        resp = requests.Response()
        resp.status_code = got.status_code
        resp.headers = requests.structures.CaseInsensitiveDict(dict(got.headers))
        resp._content = got.get_data()
        resp.encoding = 'utf-8'
        resp.url = request.url
        resp.request = request
        return resp

    def close(self):
        pass


@pytest.fixture
def site_env(monkeypatch):
    """Сайт в процессе: вход, страница «Доступ агентов» с MCP, API бота; настоящий реестр инструментов."""
    import test_mcp_tokens as tt
    from flask import Flask

    from core.auth_guard import init_auth
    from core.mcp import protocol, registry
    from routes.auth import auth_bp
    from routes.bot_api import bot_api_bp
    from routes.mcp import mcp_bp
    for name in (cs.BOT_TOKEN_ENV, cs.ANTHROPIC_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cs, '_getme', getme_ok())
    monkeypatch.setattr(protocol, 'rate_limiter', protocol.RateLimiter())
    registry.use_modules(None)
    with tt.Env() as env:
        env.anna = env.mgr.get_by_id(env.mgr.create_user('anna', 'Анна', 'annapass12', is_admin=True))
        app = Flask('kultura_bot_site_test', template_folder=os.path.join(ROOT, 'templates'),
                    static_folder=os.path.join(ROOT, 'static'))
        for blueprint in (auth_bp, mcp_bp, bot_api_bp):
            app.register_blueprint(blueprint)
        app.jinja_env.globals['app_version'] = 'test'
        init_auth(app)
        env.app = app
        env.client = app.test_client()
        yield env


def call(env, method, path, key, **kwargs):
    headers = {'Authorization': f'Bearer {key}'} if key is not None else {}
    return env.client.open(path, method=method, headers=headers, **kwargs)


def test_bot_api_only_for_engine_key(site_env):
    env = site_env
    cs.save(token=GOOD, anthropic_key_value=KEY)
    other, _ = tokens.create(env.owner, 'Claude Code, ноутбук', ['*'], None)
    key1 = engine_key(site_api.issue_install(env.owner)['command'])
    for key in (None, '', 'kmcp_' + 'x' * 40, other):
        r = call(env, 'GET', '/api/bot/config', key)
        assert r.status_code == 401 and 'команду установки' in r.get_json()['error'], key
        assert GOOD not in r.get_data(as_text=True)
    for method, path in (('POST', '/api/bot/link'), ('GET', '/api/bot/actor/555'), ('POST', '/api/bot/report')):
        assert call(env, method, path, other, json={}).status_code == 401, 'MCP-токен агента секреты не открывает'
    r = call(env, 'GET', '/api/bot/config', key1)
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    assert r.get_json() == {'telegram': {'token': GOOD, 'username': 'MCPkulturabot'}, 'anthropic_key': KEY,
                            'paused': False}

    key2 = engine_key(site_api.issue_install(env.owner)['command'])
    assert call(env, 'GET', '/api/bot/config', key1).status_code == 401, 'новая команда — прежний ключ отозван'
    assert call(env, 'GET', '/api/bot/config', key2).status_code == 200

    key3 = engine_key(site_api.issue_install(env.anna)['command'])
    env.mgr.set_admin(env.anna['id'], False)
    assert call(env, 'GET', '/api/bot/config', key3).status_code == 401, 'владелец ключа больше не админ'
    env.mgr.set_admin(env.anna['id'], True)
    assert call(env, 'GET', '/api/bot/config', key3).status_code == 200


def test_link_and_actor(site_env):
    env = site_env
    key = engine_key(site_api.issue_install(env.owner)['command'])
    assert call(env, 'GET', '/api/bot/actor/555', key).get_json() == {'actor': None}
    assert call(env, 'GET', '/api/bot/actor/abc', key).status_code == 400
    r = call(env, 'POST', '/api/bot/link', key, json={'code': 'nope', 'tg_user_id': '555', 'tg_name': 'Анна'})
    assert r.status_code == 200 and r.get_json()['ok'] is False and 'одноразовая' in r.get_json()['text']
    assert call(env, 'POST', '/api/bot/link', key, json={'code': 'x', 'tg_user_id': 'abc'}).status_code == 400
    assert call(env, 'POST', '/api/bot/link', key, data='не json', content_type='application/json').status_code == 400
    code = access.create_code(env.owner['id'], 'owner')['code']
    r = call(env, 'POST', '/api/bot/link', key, json={'code': code, 'tg_user_id': 555, 'tg_name': 'Анна'})
    assert r.get_json()['ok'] is True and 'вы подключены как Владелец' in r.get_json()['text']
    assert call(env, 'GET', '/api/bot/actor/555', key).get_json() == {
        'actor': {'tg_user_id': '555', 'user_id': env.owner['id'], 'login': 'owner', 'display_name': 'Владелец'}}
    again = call(env, 'POST', '/api/bot/link', key, json={'code': code, 'tg_user_id': '777', 'tg_name': 'Чужой'})
    assert again.get_json()['ok'] is False, 'код одноразовый'
    assert [x['tg_user_id'] for x in bot_store.list_links()] == ['555']


def test_report_checked_summed_and_shown(site_env):
    env = site_env
    key = engine_key(site_api.issue_install(env.owner)['command'])
    today = msk_time.now().date().isoformat()
    item = {'day': today, 'model': 'claude-opus-5-5', 'requests': 2, 'input_tokens': 1000, 'output_tokens': 200,
            'cache_read': 500, 'cache_write': 100, 'cost_usd': 0.25}
    running = {'state': 'running', 'detail': 'бот слушает Telegram', 'claude_error': '', 'bot': 'MCPkulturabot'}
    for body, error in (
            ([], 'объект JSON'),
            ({'status': {'state': 'dancing'}}, 'status.state'),
            ({'status': running, 'usage': {}}, 'usage — список'),
            ({'status': running, 'usage': [item] * 101}, 'не длиннее'),
            ({'status': running, 'usage': [item, 5]}, 'каждый элемент'),
            ({'status': running, 'usage': [dict(item, day='19.10.2026')]}, 'YYYY-MM-DD'),
            ({'status': running, 'usage': [dict(item, model='Claude Opus!')]}, 'имя модели'),
            ({'status': running, 'usage': [item, dict(item, input_tokens=-1)]}, 'usage.input_tokens'),
            ({'status': running, 'usage': [dict(item, requests=True)]}, 'usage.requests'),
            ({'status': running, 'usage': [dict(item, cost_usd='1')]}, 'cost_usd')):
        r = call(env, 'POST', '/api/bot/report', key, json=body)
        assert r.status_code == 400 and error in r.get_json()['error'], (body, r.get_json())
    big = json.dumps({'status': running, 'detail': 'x' * 300_000})
    assert call(env, 'POST', '/api/bot/report', key, data=big, content_type='application/json').status_code == 400
    assert bot_store.usage_summary(30)['period']['requests'] == 0, 'отказ — ничего не записано'
    assert site_api.page_view()['status']['state'] == 'stopped'

    for _ in range(2):
        r = call(env, 'POST', '/api/bot/report', key, json={'status': running, 'usage': [item]})
        assert r.status_code == 200 and r.get_json() == {'ok': True}
    view = site_api.page_view()
    assert view['status']['state'] == 'running' and view['status']['stale'] is False
    assert view['status']['bot'] == 'MCPkulturabot'
    assert view['usage']['today'] == {'requests': 4, 'input_tokens': 2000, 'output_tokens': 400, 'cache_read': 1000,
                                      'cache_write': 200, 'cost_usd': 0.5}
    assert bot_store.spent_on(today) == 0.5

    denied = 'Anthropic отказал (403): проверьте ключ в консоли Anthropic'
    call(env, 'POST', '/api/bot/report', key, json={'status': dict(running, claude_error=denied)})
    assert site_api.page_view()['status']['claude_error'] == denied

    saved = settings.get(bot_store.STATUS_KEY)
    settings.set(bot_store.STATUS_KEY, dict(saved, at_ts=time.time() - site_api.STALE_AFTER_S - 1))
    assert site_api.status_view()['status']['stale'] is True, 'отчёта нет 3 минуты — «сервер не отвечает»'
    call(env, 'POST', '/api/bot/report', key, json={'status': {'state': 'stopped', 'detail': 'остановлен'}})
    saved = settings.get(bot_store.STATUS_KEY)
    settings.set(bot_store.STATUS_KEY, dict(saved, at_ts=time.time() - 86400))
    assert site_api.status_view()['status']['stale'] is False, 'остановленный сервер не «молчит», он остановлен'

    call(env, 'POST', '/api/bot/report', key, json={'status': running})
    site_api.issue_install(env.owner)
    status = site_api.page_view()['status']
    assert (status['state'], status['at'], status['stale']) == ('stopped', '', False), \
        'новая команда установки — ждём первого отчёта нового сервера'
    assert call(env, 'POST', '/api/bot/report', key, json={'status': running}).status_code == 401, 'прежний ключ'


# ------------------------------------------------------------------ сервер бота -> сайт

def test_engine_works_with_site_end_to_end(site_env, tmp_path, monkeypatch):
    import test_kultura_bot as eng
    from kultura_bot.charts import send as chart_send
    from kultura_bot.charts.fixtures import FIXTURES
    from kultura_bot.engine import service, tools
    from kultura_bot.engine.site import Site, SiteError
    from kultura_bot.engine.store import Store

    env = site_env
    monkeypatch.setattr(bot_settings, 'SHOW_COST', False)        # строку цены проверяет test_kultura_bot.py
    cs.save(token=GOOD, anthropic_key_value=KEY)
    raw = engine_key(site_api.issue_install(env.owner)['command'])
    adapter = FlaskAdapter(env.app)

    def session_factory():
        session = requests.Session()
        session.trust_env = False
        session.mount('https://', adapter)
        return session

    site = Site(BASE, raw, session_factory=session_factory)
    assert site.config()['anthropic_key'] == KEY

    rules = site.instructions()
    assert 'common_instructions(domain="stocks")' in rules, 'правила полного коннектора'
    names = {t['name'] for t in site.tools()}
    assert {'common_whoami', 'common_instructions', 'common_chart_send'} <= names
    assert any(n.startswith('staff_') for n in names) and any(n.startswith('stocks_') for n in names)
    whoami = site.call_tool('common_whoami', {})
    assert whoami['isError'] is False and '"owner"' in whoami['content'][0]['text']
    row = audit.recent(1)[0]
    assert (row['tool'], row['client_name'], row['user_login']) == ('common_whoami', site_api.ENGINE_TOKEN_NAME,
                                                                    'owner'), 'в журнале — имя ключа сервера бота'

    catalog = tools.load_catalog(site)
    assert set(catalog.agents) == {'analyst', 'payroll', 'content'}
    assert tools.CHART_TOOL in catalog.bot.toolset.names
    payroll = catalog.agents['payroll'].toolset.names
    assert any(n.startswith('staff_') for n in payroll) and not any(n.startswith('stocks_') for n in payroll)
    assert '# Ты — агент «Зарплаты и график»' in catalog.agents['payroll'].system

    sent = []
    monkeypatch.setattr(chart_send, '_render', lambda spec: b'\x89PNG\r\n\x1a\nfake')
    monkeypatch.setattr(chart_send, '_transport', lambda fields, png, token, outcome: sent.append(
        (dict(fields), token)) or {'ok': True, 'result': {'message_id': 42}})
    chart = dict(FIXTURES[0][1])
    tg = eng.FakeTelegram(token=GOOD)
    client = eng.FakeClient(
        eng.resp(eng.thinking(), eng.use('common_chart_send', {'chart': chart, 'chat_id': '-100999'}), stop='tool_use'),
        eng.resp(eng.thinking(), eng.text('Литры — на графике выше.')))
    store = Store(str(tmp_path / 'bot.db'))
    svc = service.Service(site, store, io_factory=lambda token: tg, client_factory=lambda key: client,
                          check_key=lambda key: ('ok', 'claude-opus-5-5'))
    try:
        assert svc.ready() is True and svc.status['state'] == 'running'
        assert site_api.page_view()['status']['state'] == 'running', 'состояние дошло до страницы'
        svc.enqueue = lambda chat_id, job: svc.run_job(chat_id, job)        # без потоков: ответ сразу

        svc.handle_update(eng.message('Сколько литров?'))
        assert tg.sent[-1] == ('555', service.refusal_text(), None), 'Telegram не привязан — закрытый бот'
        code = access.create_code(env.owner['id'], 'owner')['code']
        svc.handle_update(eng.message(f'/start {code}'))
        assert 'вы подключены как Владелец' in tg.sent[-1][1]

        svc.handle_update(eng.message('Покажи литры Gravity Project графиком'))
        assert tg.sent[-1] == ('555', 'Литры — на графике выше.', None)
        assert [(fields['chat_id'], token) for fields, token in sent] == [('555', GOOD)], \
            'график — в чат разговора, рисует и шлёт сайт токеном со страницы'
        assert client.calls[0]['model'] == bot_settings.MODEL
        assert [r['tool'] for r in audit.recent(3)][0] == 'common_chart_send'

        svc.report(force=True)
        usage = site_api.page_view()['usage']['today']
        assert usage['requests'] == 2 and usage['input_tokens'] == 2000 and usage['cost_usd'] > 0
        assert all(auth == f'Bearer {raw}' for _, _, auth in adapter.sent), 'везде — ключ сервера бота'
        assert {path for _, path, _ in adapter.sent} >= {'/api/bot/config', '/api/bot/actor/555', '/api/bot/link',
                                                          '/api/bot/report', '/mcp', '/mcp/staff'}

        admin = env.app.test_client()
        r = admin.post('/login', data={'login': 'anna', 'password': 'annapass12'})
        assert r.status_code in (302, 303)
        assert admin.post(f'/api/auth/users/{env.owner["id"]}/active', json={'active': False}).get_json() == \
            {'ok': True}
        assert tokens.get(site_api.engine_token_id())['status'] == 'revoked', 'отключение владельца отзывает ключ'
        with pytest.raises(SiteError) as exc:
            site.tools()
        assert exc.value.kind == 'auth'
        assert svc.refresh_config(force=True) is False and svc.ready() is False
        assert svc.status['state'] == 'error' and 'команду установки' in svc.status['detail']
    finally:
        svc.executor.shutdown(wait=False)
        store.close()
