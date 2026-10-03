"""
Тесты OAuth 2.1 для MCP: core/mcp/oauth.py, routes/mcp_oauth.py, templates/mcp_consent.html.

Совместимы с pytest и запускаются сами: `py -3 tests/test_mcp_oauth.py` прогоняет все
test_*-функции и печатает PASS/FAIL (ненулевой код выхода при падении).

Стенд: голый Flask с blueprint'ами auth (вход) и mcp_oauth + core.auth_guard.init_auth
(гейт, сессии). mcp.db — во временной папке (core.mcp.db.set_db_path), auth.db — временный
AuthManager, подставленный синглтоном. app.py не импортируется (он стартует шедулеры).
Эндпоинты OAuth добавляются в PUBLIC_ENDPOINTS гейта так же, как это делает ядро (контракт 4.6).

Покрывает: метаданные (корень, /mcp, /mcp/<домен>), регистрацию и её проверки, полный путь
(регистрация -> согласие -> код -> токен -> проверка токена -> ротация refresh), PKCE,
redirect_uri (включая loopback с любым портом), повтор кода и refresh, сроки, отказ,
CSRF, не-админа, анонима, аудиторию коннекторов, отзыв клиента и токенов (RFC 7009),
список подключений, лимит регистраций, экранирование страницы согласия; режимы доступа
(суффиксы /read и /draft, выбор режима на согласии, правило аудитории с режимами),
revoke_all_for_user, ограничения DCR (LRU-лимитер, IPv6 /64, размеры, чистка за сутки),
миграцию старой mcp.db без колонки mode.
"""

import base64
import hashlib
import html
import os
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile
import types
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Локальный прогон по http: Secure-cookie выключаем, иначе test client их не сохранит.
os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
from werkzeug.datastructures import MultiDict  # noqa: E402

import core.auth_guard as auth_guard  # noqa: E402
import core.auth_manager as am  # noqa: E402
import core.mcp as mcp_pkg  # noqa: E402
from core.mcp import db as mcp_db  # noqa: E402
from core.mcp import oauth  # noqa: E402
from core.mcp.spec import DOMAINS, MODE_TITLES, MODES  # noqa: E402
from routes.auth import auth_bp  # noqa: E402
from routes.mcp_oauth import mcp_oauth_bp  # noqa: E402

TEMPLATES = os.path.join(ROOT, 'templates')
STATIC = os.path.join(ROOT, 'static')

BASE = 'http://localhost'
CLAUDE_CB = 'https://claude.ai/api/mcp/auth_callback'
PUBLIC_OAUTH_ENDPOINTS = (
    'mcp_oauth.protected_resource_metadata',
    'mcp_oauth.authorization_server_metadata',
    'mcp_oauth.register_client',
    'mcp_oauth.token',
    'mcp_oauth.revoke',
)


# ------------------------------------------------------------------ стенд


def _make_app():
    app = Flask('test_mcp_oauth', template_folder=TEMPLATES, static_folder=STATIC)
    app.register_blueprint(auth_bp)
    app.register_blueprint(mcp_oauth_bp)
    init = auth_guard.init_auth
    init(app)
    app.config['SECRET_KEY'] = 'test-mcp-oauth-secret'
    for name in PUBLIC_OAUTH_ENDPOINTS:      # то, что делает ядро (контракт 4.6)
        auth_guard.PUBLIC_ENDPOINTS.add(name)
    return app


class Env:
    """Изолированное окружение одного теста: временные mcp.db и auth.db, свежий app."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix='mcp_oauth_test_')
        mcp_db.set_db_path(os.path.join(self.tmp, 'mcp.db'))
        self._saved_mgr = am._auth_manager
        self.mgr = am.AuthManager(db_path=os.path.join(self.tmp, 'auth.db'))
        am._auth_manager = self.mgr
        self.admin_id = self.mgr.create_user('owner', 'Владелец Бара', 'ownerpass', is_admin=True)
        self.user_id = self.mgr.create_user('barman', 'Бармен', 'barpass1')
        self._saved_now = oauth._now
        self._saved_settings = None
        oauth._registration_limiter.reset()
        self.app = _make_app()

    def close(self):
        oauth._now = self._saved_now
        self.restore_settings()
        mcp_db.set_db_path(None)
        am._auth_manager = self._saved_mgr
        oauth._registration_limiter.reset()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- время и настройки

    def shift_time(self, seconds):
        base = self._saved_now
        oauth._now = lambda: base() + seconds

    def fake_settings(self, hosts):
        """Подменить core.mcp.settings модулем, который отдаёт oauth_redirect_hosts=hosts."""
        if self._saved_settings is None:
            self._saved_settings = (sys.modules.get('core.mcp.settings'),
                                    getattr(mcp_pkg, 'settings', None))
        fake = types.ModuleType('core.mcp.settings')
        fake.get = lambda key, default=None: hosts if key == 'oauth_redirect_hosts' else default
        sys.modules['core.mcp.settings'] = fake
        mcp_pkg.settings = fake

    def restore_settings(self):
        if self._saved_settings is None:
            return
        mod, attr = self._saved_settings
        if mod is None:
            sys.modules.pop('core.mcp.settings', None)
        else:
            sys.modules['core.mcp.settings'] = mod
        if attr is None:
            if hasattr(mcp_pkg, 'settings'):
                delattr(mcp_pkg, 'settings')
        else:
            mcp_pkg.settings = attr
        self._saved_settings = None

    # --- HTTP

    def client(self, login=None, password=None):
        c = self.app.test_client()
        if login:
            r = c.post('/login', data={'login': login, 'password': password})
            assert r.status_code == 302, r.status_code
        return c

    def admin(self):
        return self.client('owner', 'ownerpass')

    def register(self, expect=201, **fields):
        body = {'client_name': 'Claude', 'redirect_uris': [CLAUDE_CB],
                'token_endpoint_auth_method': 'none',
                'grant_types': ['authorization_code', 'refresh_token'],
                'response_types': ['code']}
        body.update(fields)
        body = {k: v for k, v in body.items() if v is not _DROP}
        oauth._registration_limiter.reset()   # лимит по IP проверяет отдельный тест
        r = self.app.test_client().post('/oauth/register', json=body)
        assert r.status_code == expect, (r.status_code, r.get_data(as_text=True))
        return r.get_json()

    def token(self, data, headers=None, expect=None):
        r = self.app.test_client().post('/oauth/token', data=data, headers=headers or {})
        if expect is not None:
            assert r.status_code == expect, (r.status_code, r.get_data(as_text=True))
        return r


_DROP = object()


def _pkce():
    verifier = secrets.token_urlsafe(48)[:64]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    return verifier, challenge


def _auth_params(client_id, challenge, **extra):
    params = {'response_type': 'code', 'client_id': client_id, 'redirect_uri': CLAUDE_CB,
              'state': 'st-' + secrets.token_hex(4), 'code_challenge': challenge,
              'code_challenge_method': 'S256', 'resource': BASE + '/mcp/stocks',
              'scope': 'mcp offline_access'}
    params.update(extra)
    return {k: v for k, v in params.items() if v is not _DROP}


def _authorize_url(params):
    return '/oauth/authorize?' + urlencode(params)


def _hidden_fields(page_html):
    fields = []
    for name, value in re.findall(r'<input type="hidden" name="([^"]*)" value="([^"]*)">', page_html):
        fields.append((html.unescape(name), html.unescape(value)))
    return fields


def _consent(c, params, decision='allow'):
    """GET страницы согласия + POST решения. Возвращает (GET-ответ, POST-ответ)."""
    page = c.get(_authorize_url(params))
    assert page.status_code == 200, (page.status_code, page.get_data(as_text=True)[:500])
    fields = _hidden_fields(page.get_data(as_text=True))
    assert any(k == 'csrf_token' for k, _ in fields)
    data = fields + [('decision', decision)]
    post = c.post('/oauth/authorize', data=MultiDict(data))
    return page, post


def _location_params(resp):
    loc = resp.headers['Location']
    parts = urlsplit(loc)
    return parts, {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}


def _get_code(env, client_id, challenge, c=None, **extra):
    c = c or env.admin()
    params = _auth_params(client_id, challenge, **extra)
    _page, post = _consent(c, params)
    assert post.status_code == 303, post.status_code
    parts, q = _location_params(post)
    assert q.get('state') == params.get('state')
    return q['code'], params


def _full_flow(env, resource=BASE + '/mcp/stocks', **reg):
    """Регистрация + согласие + обмен кода. Возвращает (client, tokens_json, verifier)."""
    client = env.register(**reg)
    verifier, challenge = _pkce()
    code, params = _get_code(env, client['client_id'], challenge, resource=resource)
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
            'client_id': client['client_id'], 'code_verifier': verifier, 'resource': resource}
    r = env.token(data, expect=200)
    return client, r.get_json(), verifier


def isolated(fn):
    """Обёртка теста: свежее окружение и уборка. Без functools.wraps — иначе pytest увидит
    параметр env и станет искать такую фикстуру."""
    def wrapper():
        env = Env()
        try:
            fn(env)
        finally:
            env.close()
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# ------------------------------------------------------------------ метаданные


@isolated
def test_metadata_shapes(env):
    c = env.app.test_client()
    as_doc = c.get('/.well-known/oauth-authorization-server')
    assert as_doc.status_code == 200
    assert as_doc.headers['Access-Control-Allow-Origin'] == '*'
    meta = as_doc.get_json()
    assert meta['issuer'] == BASE
    assert meta['authorization_endpoint'] == BASE + '/oauth/authorize'
    assert meta['token_endpoint'] == BASE + '/oauth/token'
    assert meta['registration_endpoint'] == BASE + '/oauth/register'
    assert meta['revocation_endpoint'] == BASE + '/oauth/revoke'
    assert meta['response_types_supported'] == ['code']
    assert meta['grant_types_supported'] == ['authorization_code', 'refresh_token']
    assert meta['code_challenge_methods_supported'] == ['S256']
    assert meta['token_endpoint_auth_methods_supported'] == ['none', 'client_secret_post',
                                                             'client_secret_basic']
    assert 'mcp' in meta['scopes_supported'] and 'offline_access' in meta['scopes_supported']
    assert meta['authorization_response_iss_parameter_supported'] is True
    assert 'client_id_metadata_document_supported' not in meta, 'CIMD не объявляем'

    expected = {'': BASE + '/mcp', '/mcp': BASE + '/mcp', '/mcp/': BASE + '/mcp',
                '/mcp/read': BASE + '/mcp/read', '/mcp/draft/': BASE + '/mcp/draft'}
    for d in DOMAINS:
        expected['/mcp/' + d] = BASE + '/mcp/' + d
        expected['/mcp/' + d + '/read'] = BASE + '/mcp/' + d + '/read'
        expected['/mcp/' + d + '/draft'] = BASE + '/mcp/' + d + '/draft'
    for suffix, resource in expected.items():
        r = c.get('/.well-known/oauth-protected-resource' + suffix)
        assert r.status_code == 200, suffix
        doc = r.get_json()
        assert doc['resource'] == resource, (suffix, doc)
        assert doc['authorization_servers'] == [meta['issuer']]
        assert doc['bearer_methods_supported'] == ['header']
        assert doc['scopes_supported'] == ['mcp']
        assert 'offline_access' not in doc['scopes_supported']
        assert doc['resource_name'].startswith('Культура')
    for bad in ('/mcp/unknown', '/api', '/mcp/stocks/x', '/mcp/full', '/mcp/stocks/full',
                '/mcp/read/stocks', '/mcp/stocks/read/x', '/mcp//stocks'):
        assert c.get('/.well-known/oauth-protected-resource' + bad).status_code == 404, bad
    doc = c.get('/.well-known/oauth-protected-resource/mcp/staff/read').get_json()
    assert MODE_TITLES['read'].lower() in doc['resource_name'], 'режим виден в имени ресурса'
    # openid-configuration не отдаём: для анонима глобальный гейт отвечает редиректом на
    # /login (у несуществующего адреса нет эндпоинта в PUBLIC_ENDPOINTS). Клиенты MCP
    # спрашивают сначала oauth-authorization-server и по редиректам за метаданными не ходят.
    assert c.get('/.well-known/openid-configuration').status_code in (302, 404)
    # адрес для WWW-Authenticate (его строит ядро)
    assert oauth.protected_resource_metadata_url(BASE, '/mcp/stocks') == \
        BASE + '/.well-known/oauth-protected-resource/mcp/stocks'
    # ProxyFix: внешний https-хост из заголовков Caddy попадает в метаданные
    r = c.get('/.well-known/oauth-protected-resource/mcp',
              headers={'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'BeerKultura.ru'})
    assert r.get_json()['resource'] == 'https://beerkultura.ru/mcp'
    assert r.get_json()['authorization_servers'] == ['https://beerkultura.ru']


# ------------------------------------------------------------------ полный путь


@isolated
def test_full_happy_path_and_refresh_rotation(env):
    reg = env.register()
    assert reg['client_id'].startswith('kmcpc_')
    assert 'client_secret' not in reg, 'публичный клиент без секрета'
    assert reg['redirect_uris'] == [CLAUDE_CB]
    assert reg['token_endpoint_auth_method'] == 'none'
    assert 'refresh_token' in reg['grant_types']

    verifier, challenge = _pkce()
    params = _auth_params(reg['client_id'], challenge)

    # аноним -> вход с возвратом на тот же запрос
    anon = env.client()
    r = anon.get(_authorize_url(params))
    assert r.status_code == 302 and '/login' in r.headers['Location']
    nxt = parse_qs(urlsplit(r.headers['Location']).query)['next'][0]
    assert nxt.startswith('/oauth/authorize?') and 'code_challenge=' + challenge in nxt
    r = anon.post('/login?' + urlencode({'next': nxt}),
                  data={'login': 'owner', 'password': 'ownerpass'})
    assert r.status_code == 302 and r.headers['Location'].endswith(nxt)

    page, post = _consent(anon, params)
    text = page.get_data(as_text=True)
    assert 'Claude' in text and 'claude.ai' in text
    assert DOMAINS['stocks'].title in text
    assert 'Владелец Бара' in text and 'owner' in text
    assert page.headers['X-Frame-Options'] == 'DENY'
    assert "frame-ancestors 'none'" in page.headers['Content-Security-Policy']
    assert page.headers['Cache-Control'] == 'no-store'
    assert post.status_code == 303
    parts, q = _location_params(post)
    assert parts.scheme + '://' + parts.netloc + parts.path == CLAUDE_CB
    assert q['state'] == params['state']
    assert q['iss'] == BASE
    code = q['code']

    tok = env.token({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
                     'client_id': reg['client_id'], 'code_verifier': verifier,
                     'resource': BASE + '/mcp/stocks'}, expect=200)
    assert tok.headers['Cache-Control'] == 'no-store'
    body = tok.get_json()
    assert body['token_type'] == 'Bearer'
    assert body['expires_in'] == 3600
    assert body['access_token'].startswith('kmcpo_') and body['refresh_token'].startswith('kmcpr_')
    assert body['scope'] == 'mcp offline_access'

    p = oauth.verify_access_token(body['access_token'], BASE + '/mcp/stocks')
    assert p is not None
    assert p.user_id == env.admin_id and p.login == 'owner' and p.display_name == 'Владелец Бара'
    assert p.token_kind == 'oauth' and p.token_id.startswith('oa_')
    assert p.grant_id.startswith('g_') and p.connection_id() == p.grant_id
    assert p.client_name == 'Claude'
    assert p.domains == ('stocks',)
    assert p.allows('stocks') and not p.allows('staff') and not p.allows(None)
    assert p.expires_at and p.expires_at.endswith('+03:00')
    # регистр хоста и «/» в конце не мешают
    assert oauth.verify_access_token(body['access_token'], 'HTTP://LOCALHOST/mcp/stocks/') is not None

    # ротация refresh: старый сразу недействителен, новая пара работает
    r2 = env.token({'grant_type': 'refresh_token', 'refresh_token': body['refresh_token'],
                    'client_id': reg['client_id'], 'resource': BASE + '/mcp/stocks'}, expect=200)
    body2 = r2.get_json()
    assert body2['refresh_token'] != body['refresh_token']
    assert body2['access_token'] != body['access_token']
    p2 = oauth.verify_access_token(body2['access_token'], BASE + '/mcp/stocks')
    assert p2 is not None
    # новый токен — новый id, но подключение то же: учёт «на подключение» не обнуляется
    # каждый час (предел поиска картинок, docs/lessons.md)
    assert p2.token_id != p.token_id and p2.connection_id() == p.connection_id() == p.grant_id
    r3 = env.token({'grant_type': 'refresh_token', 'refresh_token': body['refresh_token'],
                    'client_id': reg['client_id']})
    assert r3.status_code == 400 and r3.get_json()['error'] == 'invalid_grant'
    # старый access живёт до своего срока (параллельные вызовы Claude не рвутся)
    assert oauth.verify_access_token(body['access_token'], BASE + '/mcp/stocks') is not None
    # новый refresh работает
    env.token({'grant_type': 'refresh_token', 'refresh_token': body2['refresh_token'],
               'client_id': reg['client_id']}, expect=200)


@isolated
def test_confidential_client_basic_and_post(env):
    reg = env.register(token_endpoint_auth_method=_DROP)   # умолчание RFC 7591 — client_secret_basic
    assert reg['token_endpoint_auth_method'] == 'client_secret_basic'
    secret = reg['client_secret']
    assert secret.startswith('kmcps_') and reg['client_secret_expires_at'] == 0
    cid = reg['client_id']

    def basic(i, s):
        return {'Authorization': 'Basic ' + base64.b64encode((i + ':' + s).encode()).decode()}

    verifier, challenge = _pkce()
    code, _ = _get_code(env, cid, challenge)
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
            'code_verifier': verifier}
    bad = env.token(data, headers=basic(cid, secret + 'x'))
    assert bad.status_code == 401 and bad.get_json()['error'] == 'invalid_client'
    assert bad.headers['WWW-Authenticate'].startswith('Basic')
    nosecret = env.token(dict(data, client_id=cid))
    assert nosecret.status_code == 401 and nosecret.get_json()['error'] == 'invalid_client'
    both = env.token(dict(data, client_secret=secret), headers=basic(cid, secret))
    assert both.status_code == 400 and both.get_json()['error'] == 'invalid_request'
    ok = env.token(data, headers=basic(cid, secret), expect=200).get_json()
    # client_secret_post тоже принимается для конфиденциального клиента
    env.token({'grant_type': 'refresh_token', 'refresh_token': ok['refresh_token'],
               'client_id': cid, 'client_secret': secret}, expect=200)
    # секрет хранится только хэшем
    with sqlite3.connect(mcp_db.db_path()) as conn:
        stored = conn.execute('SELECT client_secret_hash FROM oauth_clients WHERE client_id=?',
                              (cid,)).fetchone()[0]
    assert stored == hashlib.sha256(secret.encode()).hexdigest()


# ------------------------------------------------------------------ PKCE и redirect_uri


@isolated
def test_wrong_verifier_rejected_code_not_burned(env):
    reg = env.register()
    verifier, challenge = _pkce()
    code, _ = _get_code(env, reg['client_id'], challenge)
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
            'client_id': reg['client_id']}
    other, _ = _pkce()
    r = env.token(dict(data, code_verifier=other))
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    r = env.token(dict(data, code_verifier='short'))
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    r = env.token(data)
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_request'
    # неудачная попытка не сжигает код: законный клиент с верным verifier проходит
    env.token(dict(data, code_verifier=verifier), expect=200)


@isolated
def test_plain_or_missing_challenge_rejected(env):
    reg = env.register()
    _v, challenge = _pkce()
    c = env.admin()
    cases = [
        dict(code_challenge_method='plain'),
        dict(code_challenge_method=_DROP),
        dict(code_challenge=_DROP),
        dict(code_challenge='short'),
        dict(code_challenge=challenge[:-1] + '+'),
    ]
    for extra in cases:
        params = _auth_params(reg['client_id'], challenge, **extra)
        r = c.get(_authorize_url(params))
        assert r.status_code == 302, (extra, r.status_code)
        parts, q = _location_params(r)
        assert parts.netloc == 'claude.ai'
        assert q['error'] == 'invalid_request', (extra, q)
        assert q['state'] == params['state'] and q['iss'] == BASE
        assert 'code' not in q


@isolated
def test_wrong_redirect_uri(env):
    reg = env.register()
    verifier, challenge = _pkce()
    c = env.admin()
    for uri in ('https://claude.ai/api/mcp/auth_callback/evil', 'https://evil.example/cb',
                'https://claude.com/api/mcp/auth_callback', CLAUDE_CB + '?x=1'):
        r = c.get(_authorize_url(_auth_params(reg['client_id'], challenge, redirect_uri=uri)))
        assert r.status_code == 400, uri
        assert 'Location' not in r.headers, 'на незарегистрированный адрес не перенаправляем'
        assert 'Адрес возврата' in r.get_data(as_text=True)
    # неизвестный клиент и повтор client_id — тоже страница, не редирект
    r = c.get(_authorize_url(_auth_params('kmcpc_nope', challenge)))
    assert r.status_code == 400 and 'Location' not in r.headers
    r = c.get('/oauth/authorize?' + urlencode([('client_id', reg['client_id']),
                                               ('client_id', reg['client_id'])]))
    assert r.status_code == 400 and 'Location' not in r.headers
    # на обмене кода redirect_uri должен совпасть строкой
    code, _ = _get_code(env, reg['client_id'], challenge, c=c)
    base = {'grant_type': 'authorization_code', 'code': code, 'client_id': reg['client_id'],
            'code_verifier': verifier}
    r = env.token(dict(base, redirect_uri=CLAUDE_CB + '/'))
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    r = env.token(base)   # redirect_uri был в запросе авторизации -> обязателен
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    env.token(dict(base, redirect_uri=CLAUDE_CB), expect=200)


@isolated
def test_redirect_uri_omitted_with_single_registration(env):
    reg = env.register()
    verifier, challenge = _pkce()
    code, _ = _get_code(env, reg['client_id'], challenge, redirect_uri=_DROP)
    env.token({'grant_type': 'authorization_code', 'code': code, 'client_id': reg['client_id'],
               'code_verifier': verifier}, expect=200)


@isolated
def test_loopback_port_agnostic(env):
    reg = env.register(client_name='Claude Code',
                       redirect_uris=['http://127.0.0.1:1111/callback', 'http://localhost/callback'])
    verifier, challenge = _pkce()
    c = env.admin()
    for uri in ('http://127.0.0.1:2222/callback', 'http://localhost:3118/callback'):
        params = _auth_params(reg['client_id'], challenge, redirect_uri=uri)
        page, post = _consent(c, params)
        assert 'localhost' in page.get_data(as_text=True)
        assert 'ваш компьютер' in page.get_data(as_text=True), 'предупреждение для loopback'
        assert post.status_code == 303
        assert post.headers['Location'].startswith(uri + '?')
    code = _location_params(post)[1]['code']
    env.token({'grant_type': 'authorization_code', 'code': code, 'client_id': reg['client_id'],
               'redirect_uri': 'http://localhost:3118/callback', 'code_verifier': verifier},
              expect=200)
    # хост сравнивается точно, путь тоже
    for uri in ('http://localhost:2222/other', 'http://127.0.0.1:5/callback/x',
                'http://[::1]:2222/callback'):
        r = c.get(_authorize_url(_auth_params(reg['client_id'], challenge, redirect_uri=uri)))
        assert r.status_code == 400 and 'Location' not in r.headers, uri


# ------------------------------------------------------------------ регистрация


@isolated
def test_registration_validation(env):
    bad_uris = [
        'https://evil.example/cb',                        # хост не разрешён
        'http://claude.ai/api/mcp/auth_callback',         # не https
        'https://claude.ai/other',                        # у claude.ai закреплён путь колбэка
        'https://claude.ai:8443/api/mcp/auth_callback',   # явный порт не у loopback
        'https://user@claude.ai/api/mcp/auth_callback',   # логин в адресе
        'https://evil.com\\@claude.ai/api/mcp/auth_callback',  # «\\»: браузер ушёл бы на evil.com
        'https://claude.ai/api/mcp/auth_callback#frag',
        'https://claude.ai/api/mcp/auth_callback?code=1',
        'https://claudе.ai/api/mcp/auth_callback',        # кириллическая «е»
        'https://claude.ai /api/mcp/auth_callback',
        'javascript:alert(1)',
        '/relative/cb',
        'http://localhost:0/cb',
        'http://localhost/cb?state=x',
    ]
    for uri in bad_uris:
        r = env.register(expect=400, redirect_uris=[uri])
        assert r['error'] == 'invalid_redirect_uri', (uri, r)
    assert env.register(expect=400, redirect_uris=_DROP)['error'] == 'invalid_redirect_uri'
    assert env.register(expect=400, redirect_uris=[])['error'] == 'invalid_redirect_uri'
    assert env.register(expect=400, redirect_uris='https://claude.ai/api/mcp/auth_callback')['error'] \
        == 'invalid_client_metadata'
    assert env.register(expect=400, redirect_uris=[CLAUDE_CB] * 11)['error'] == 'invalid_client_metadata'
    assert env.register(expect=400, token_endpoint_auth_method='private_key_jwt')['error'] \
        == 'invalid_client_metadata'
    assert env.register(expect=400, grant_types=['client_credentials'])['error'] == 'invalid_client_metadata'
    assert env.register(expect=400, response_types=['token'])['error'] == 'invalid_client_metadata'
    # хорошие адреса: оба хоста Claude и loopback по http
    ok = env.register(redirect_uris=[CLAUDE_CB, 'https://claude.com/api/mcp/auth_callback',
                                     'http://localhost:4567/callback', 'http://127.0.0.1/cb?x=1'])
    assert len(ok['redirect_uris']) == 4
    # тело не JSON, не объект, слишком большое
    c = env.app.test_client()
    r = c.post('/oauth/register', data='not json', content_type='application/json')
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_client_metadata'
    r = c.post('/oauth/register', json=[1, 2])
    assert r.status_code == 400
    r = c.post('/oauth/register', data='[' * 2000 + ']' * 2000, content_type='application/json')
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_client_metadata'
    r = c.post('/oauth/register', json={'redirect_uris': [CLAUDE_CB], 'client_name': 'x' * 20000})
    assert r.status_code == 413
    # имя чистится от управляющих символов и режется до 100 символов
    reg = env.register(client_name='Cla‮ude​\nX' + 'y' * 300)
    assert '‮' not in reg['client_name'] and '​' not in reg['client_name']
    assert len(reg['client_name']) == 100


@isolated
def test_redirect_hosts_from_settings(env):
    env.fake_settings(['https://Example.org/', '  LOCALHOST ', 42])
    assert oauth.allowed_redirect_hosts() == ('example.org', 'localhost')
    assert env.register(expect=400)['error'] == 'invalid_redirect_uri'   # claude.ai не в списке
    reg = env.register(redirect_uris=['https://example.org/cb'])
    _v, challenge = _pkce()
    c = env.admin()
    page, _post = _consent(c, _auth_params(reg['client_id'], challenge,
                                           redirect_uri='https://example.org/cb'))
    assert 'Этот хост разрешён' in page.get_data(as_text=True)
    # хост убрали из настроек после регистрации — авторизация закрыта страницей ошибки
    env.fake_settings(['localhost'])
    r = c.get(_authorize_url(_auth_params(reg['client_id'], challenge,
                                          redirect_uri='https://example.org/cb')))
    assert r.status_code == 400 and 'Location' not in r.headers
    # пустой список — OAuth-регистрация закрыта полностью
    env.fake_settings([])
    assert env.register(expect=400, redirect_uris=['http://localhost/cb'])['error'] \
        == 'invalid_redirect_uri'
    # сломанная настройка -> умолчание
    env.fake_settings('claude.ai')
    assert oauth.allowed_redirect_hosts() == oauth.DEFAULT_REDIRECT_HOSTS


@isolated
def test_registration_rate_limit(env):
    c = env.app.test_client()
    body = {'redirect_uris': [CLAUDE_CB], 'token_endpoint_auth_method': 'none'}
    for i in range(oauth.REG_PER_IP_PER_HOUR):
        assert c.post('/oauth/register', json=body).status_code == 201, i
    r = c.post('/oauth/register', json=body)
    assert r.status_code == 429 and r.headers.get('Retry-After')
    # другой адрес (за Caddy — X-Forwarded-For) лимитом не задет
    r = c.post('/oauth/register', json=body, headers={'X-Forwarded-For': '203.0.113.7'})
    assert r.status_code == 201


# ------------------------------------------------------------------ коды


@isolated
def test_code_reuse_revokes_tokens(env):
    reg = env.register()
    verifier, challenge = _pkce()
    code, _ = _get_code(env, reg['client_id'], challenge)
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
            'client_id': reg['client_id'], 'code_verifier': verifier}
    first = env.token(data, expect=200).get_json()
    assert oauth.verify_access_token(first['access_token'], BASE + '/mcp/stocks') is not None
    again = env.token(data)
    assert again.status_code == 400 and again.get_json()['error'] == 'invalid_grant'
    assert oauth.verify_access_token(first['access_token'], BASE + '/mcp/stocks') is None
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': first['refresh_token'],
                   'client_id': reg['client_id']})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    assert oauth.list_grants() == []


@isolated
def test_expired_code(env):
    reg = env.register()
    verifier, challenge = _pkce()
    code, _ = _get_code(env, reg['client_id'], challenge)
    env.shift_time(oauth.CODE_TTL + 1)
    r = env.token({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
                   'client_id': reg['client_id'], 'code_verifier': verifier})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'


@isolated
def test_code_bound_to_client(env):
    a = env.register()
    b = env.register()
    verifier, challenge = _pkce()
    code, _ = _get_code(env, a['client_id'], challenge)
    r = env.token({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
                   'client_id': b['client_id'], 'code_verifier': verifier})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    r = env.token({'grant_type': 'authorization_code', 'code': 'garbage', 'redirect_uri': CLAUDE_CB,
                   'client_id': a['client_id'], 'code_verifier': verifier})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'


# ------------------------------------------------------------------ согласие


@isolated
def test_non_admin_gets_403(env):
    reg = env.register()
    _v, challenge = _pkce()
    c = env.client('barman', 'barpass1')
    r = c.get(_authorize_url(_auth_params(reg['client_id'], challenge)))
    assert r.status_code == 403
    text = r.get_data(as_text=True)
    assert 'только администратор' in text and 'barman' in text
    assert 'Location' not in r.headers
    r = c.post('/oauth/authorize', data={'decision': 'allow', 'client_id': reg['client_id']})
    assert r.status_code == 403


@isolated
def test_anonymous_redirected_to_login(env):
    reg = env.register()
    _v, challenge = _pkce()
    c = env.client()
    r = c.get(_authorize_url(_auth_params(reg['client_id'], challenge)))
    assert r.status_code == 302
    loc = r.headers['Location']
    assert urlsplit(loc).path == '/login'
    assert parse_qs(urlsplit(loc).query)['next'][0].startswith('/oauth/authorize?')
    r = c.post('/oauth/authorize', data={'decision': 'allow'})
    assert r.status_code == 302 and '/login' in r.headers['Location']


@isolated
def test_csrf_required_on_consent(env):
    reg = env.register()
    _v, challenge = _pkce()
    c = env.admin()
    params = _auth_params(reg['client_id'], challenge)
    page = c.get(_authorize_url(params))
    fields = [(k, v) for k, v in _hidden_fields(page.get_data(as_text=True)) if k != 'csrf_token']
    for extra in ([], [('csrf_token', 'x' * 43)], [('csrf_token', 'ж' * 43)]):
        r = c.post('/oauth/authorize', data=MultiDict(fields + extra + [('decision', 'allow')]))
        assert r.status_code == 400 and 'Location' not in r.headers
        assert 'Форма согласия устарела' in r.get_data(as_text=True)
    # токен другой сессии не подходит
    other = env.admin()
    other_page = other.get(_authorize_url(params))
    other_csrf = dict(_hidden_fields(other_page.get_data(as_text=True)))['csrf_token']
    r = c.post('/oauth/authorize', data=MultiDict(fields + [('csrf_token', other_csrf), ('decision', 'allow')]))
    assert r.status_code == 400
    with sqlite3.connect(mcp_db.db_path()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM oauth_codes').fetchone()[0] == 0


@isolated
def test_deny_redirects_access_denied(env):
    reg = env.register()
    _v, challenge = _pkce()
    params = _auth_params(reg['client_id'], challenge)
    _page, post = _consent(env.admin(), params, decision='deny')
    assert post.status_code == 303
    parts, q = _location_params(post)
    assert parts.netloc == 'claude.ai'
    assert q['error'] == 'access_denied' and q['state'] == params['state'] and q['iss'] == BASE
    assert 'code' not in q
    _page, post = _consent(env.admin(), params, decision='maybe')
    assert post.status_code == 400 and 'Location' not in post.headers


@isolated
def test_state_optional_and_prompt_none(env):
    reg = env.register()
    _v, challenge = _pkce()
    _page, post = _consent(env.admin(), _auth_params(reg['client_id'], challenge, state=_DROP))
    parts, q = _location_params(post)
    assert 'code' in q and 'state' not in q
    r = env.admin().get(_authorize_url(_auth_params(reg['client_id'], challenge, prompt='none')))
    assert r.status_code == 302 and _location_params(r)[1]['error'] == 'consent_required'
    r = env.admin().get(_authorize_url(_auth_params(reg['client_id'], challenge,
                                                    response_type='token')))
    assert _location_params(r)[1]['error'] == 'unsupported_response_type'
    r = env.admin().get(_authorize_url(_auth_params(reg['client_id'], challenge,
                                                    response_mode='form_post')))
    assert _location_params(r)[1]['error'] == 'invalid_request'
    r = env.admin().get('/oauth/authorize?' + urlencode(
        list(_auth_params(reg['client_id'], challenge).items()) + [('state', 'second')]))
    assert r.status_code == 302 and _location_params(r)[1]['error'] == 'invalid_request'


@isolated
def test_consent_page_escapes_client_name(env):
    reg = env.register(client_name='<script>alert(1)</script>‮evil')
    _v, challenge = _pkce()
    page = env.admin().get(_authorize_url(_auth_params(reg['client_id'], challenge,
                                                       state='"><b>x')))
    text = page.get_data(as_text=True)
    assert '<script>alert(1)</script>' not in text
    assert '&lt;script&gt;' in text
    assert '‮' not in text
    assert '"><b>x' not in text and '&#34;&gt;&lt;b&gt;x' in text
    # на странице нет эмодзи и HEX-цветов вне переменных
    assert not re.search('[\U0001F300-\U0001FAFF☀-➿]', text)
    style = text[text.index('<style>'):text.index('</style>')]
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b', style)


# ------------------------------------------------------------------ коннекторы и аудитория


@isolated
def test_resource_validation_and_audience(env):
    reg = env.register()
    verifier, challenge = _pkce()
    c = env.admin()
    for bad in ('https://evil.example/mcp', BASE + '/mcp/unknown', BASE + '/api/stocks',
                BASE + '/mcp#x', 'not a url'):
        r = c.get(_authorize_url(_auth_params(reg['client_id'], challenge, resource=bad)))
        assert r.status_code == 302, bad
        assert _location_params(r)[1]['error'] == 'invalid_target', bad
    r = c.get('/oauth/authorize?' + urlencode(
        list(_auth_params(reg['client_id'], challenge).items()) + [('resource', BASE + '/mcp')]))
    assert _location_params(r)[1]['error'] == 'invalid_target', 'два resource'

    # без resource -> полный коннектор /mcp; страница согласия показывает все разделы
    params = _auth_params(reg['client_id'], challenge, resource=_DROP)
    page, post = _consent(c, params)
    text = page.get_data(as_text=True)
    assert 'Все разделы' in text and all(d.title in text for d in DOMAINS.values())
    code = _location_params(post)[1]['code']
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
            'client_id': reg['client_id'], 'code_verifier': verifier}
    r = env.token(dict(data, resource=BASE + '/mcp/stocks'))
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_target'
    full = env.token(dict(data, resource=BASE + '/mcp'), expect=200).get_json()
    p = oauth.verify_access_token(full['access_token'], BASE + '/mcp')
    assert p is not None and p.domains == ('*',) and p.allows(None)
    # токен полного коннектора годится и для коннектора домена (он и так даёт всё)
    p = oauth.verify_access_token(full['access_token'], BASE + '/mcp/staff')
    assert p is not None and p.domains == ('*',)
    # но не для другого сайта и не для чужого пути
    assert oauth.verify_access_token(full['access_token'], 'https://evil.example/mcp') is None
    assert oauth.verify_access_token(full['access_token'], BASE + '/api/x') is None
    assert oauth.verify_access_token(full['access_token'], BASE + '/mcp/unknown') is None

    # токен домена работает только на своём коннекторе
    _c2, content, _v2 = _full_flow(env, resource=BASE + '/mcp/content')
    assert oauth.verify_access_token(content['access_token'], BASE + '/mcp/content').domains == ('content',)
    assert oauth.verify_access_token(content['access_token'], BASE + '/mcp/stocks') is None
    assert oauth.verify_access_token(content['access_token'], BASE + '/mcp') is None
    # refresh не может сменить коннектор
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': content['refresh_token'],
                   'client_id': _c2['client_id'], 'resource': BASE + '/mcp'})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_target'


@isolated
def test_verify_rejects_garbage(env):
    for raw in (None, '', 'kmcp_' + 'a' * 40, 'kmcpo_unknown', 'kmcpo_' + 'a' * 300, 123):
        assert oauth.verify_access_token(raw, BASE + '/mcp') is None
    _c, tok, _v = _full_flow(env)
    assert oauth.verify_access_token(tok['access_token'], None) is None
    assert oauth.verify_access_token(tok['refresh_token'], BASE + '/mcp/stocks') is None, \
        'refresh-токен не пускается как access'
    env.shift_time(oauth.ACCESS_TOKEN_TTL + 1)
    assert oauth.verify_access_token(tok['access_token'], BASE + '/mcp/stocks') is None


# ------------------------------------------------------------------ refresh


@isolated
def test_refresh_reuse_detection(env):
    reg, tok, _v = _full_flow(env)
    cid = reg['client_id']
    new = env.token({'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                     'client_id': cid}, expect=200).get_json()
    # повтор старого refresh сразу (гонка) — отказ, но цепочка жива
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                   'client_id': cid})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    assert oauth.verify_access_token(new['access_token'], BASE + '/mcp/stocks') is not None
    newer = env.token({'grant_type': 'refresh_token', 'refresh_token': new['refresh_token'],
                       'client_id': cid}, expect=200).get_json()
    # повтор старого refresh позже окна — кража: гаснет вся цепочка
    env.shift_time(oauth.REFRESH_REUSE_GRACE + 5)
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': new['refresh_token'],
                   'client_id': cid})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    assert oauth.verify_access_token(newer['access_token'], BASE + '/mcp/stocks') is None
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': newer['refresh_token'],
                   'client_id': cid})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'


@isolated
def test_refresh_expiry_scope_and_client_binding(env):
    reg, tok, _v = _full_flow(env)
    other = env.register()
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                   'client_id': other['client_id']})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                   'client_id': reg['client_id'], 'scope': 'mcp admin'})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_scope'
    ok = env.token({'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                    'client_id': reg['client_id'], 'scope': 'mcp'}, expect=200).get_json()
    env.shift_time(oauth.REFRESH_TOKEN_TTL + 1)
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': ok['refresh_token'],
                   'client_id': reg['client_id']})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'


@isolated
def test_demoted_or_deleted_owner_loses_access(env):
    second = env.mgr.create_user('boss2', 'Второй админ', 'boss2pass', is_admin=True)
    reg, tok, _v = _full_flow(env)
    env.mgr.set_admin(env.admin_id, False)
    assert oauth.verify_access_token(tok['access_token'], BASE + '/mcp/stocks') is None
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                   'client_id': reg['client_id']})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    env.mgr.set_admin(env.admin_id, True)
    assert oauth.verify_access_token(tok['access_token'], BASE + '/mcp/stocks') is not None
    env.mgr.set_active(env.admin_id, False)
    assert oauth.verify_access_token(tok['access_token'], BASE + '/mcp/stocks') is None
    env.mgr.set_active(env.admin_id, True)
    env.mgr.delete_user(env.admin_id)
    assert oauth.verify_access_token(tok['access_token'], BASE + '/mcp/stocks') is None
    assert second


# ------------------------------------------------------------------ отзыв


@isolated
def test_revoked_client(env):
    reg, tok, _v = _full_flow(env)
    assert len(oauth.list_grants()) == 1
    res = oauth.revoke_client(reg['client_id'])
    assert res == {'found': True, 'grants': 1, 'tokens': 2}
    assert oauth.revoke_client(reg['client_id'])['found'] is True
    assert oauth.revoke_client('kmcpc_missing') == {'found': False, 'grants': 0, 'tokens': 0}
    assert oauth.verify_access_token(tok['access_token'], BASE + '/mcp/stocks') is None
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                   'client_id': reg['client_id']})
    assert r.status_code == 401 and r.get_json()['error'] == 'invalid_client'
    assert oauth.list_grants() == []
    _v2, challenge = _pkce()
    r = env.admin().get(_authorize_url(_auth_params(reg['client_id'], challenge)))
    assert r.status_code == 400 and 'Location' not in r.headers
    assert 'отозван' in r.get_data(as_text=True)


@isolated
def test_revocation_endpoint(env):
    reg, tok, _v = _full_flow(env)
    c = env.app.test_client()
    cid = reg['client_id']
    assert c.post('/oauth/revoke', data={'client_id': cid}).status_code == 400
    r = c.post('/oauth/revoke', data={'token': 'kmcpo_unknown', 'client_id': cid})
    assert r.status_code == 200
    # чужой клиент не может отозвать токен (и не узнаёт, что токен существует)
    other = env.register()
    r = c.post('/oauth/revoke', data={'token': tok['access_token'], 'client_id': other['client_id']})
    assert r.status_code == 200
    assert oauth.verify_access_token(tok['access_token'], BASE + '/mcp/stocks') is not None
    # отзыв access гасит только его
    r = c.post('/oauth/revoke', data={'token': tok['access_token'], 'client_id': cid,
                                      'token_type_hint': 'access_token'})
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    assert oauth.verify_access_token(tok['access_token'], BASE + '/mcp/stocks') is None
    new = env.token({'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                     'client_id': cid}, expect=200).get_json()
    # отзыв refresh гасит всю цепочку (и выданный по ней access)
    r = c.post('/oauth/revoke', data={'token': new['refresh_token'], 'client_id': cid})
    assert r.status_code == 200
    assert oauth.verify_access_token(new['access_token'], BASE + '/mcp/stocks') is None
    assert oauth.list_grants() == []
    # конфиденциальный клиент с неверным секретом -> 401
    conf = env.register(token_endpoint_auth_method='client_secret_post')
    r = c.post('/oauth/revoke', data={'token': 'x', 'client_id': conf['client_id'],
                                      'client_secret': 'wrong'})
    assert r.status_code == 401 and r.get_json()['error'] == 'invalid_client'
    # без client_id — отзыв по владению токеном
    _c3, tok3, _v3 = _full_flow(env)
    assert c.post('/oauth/revoke', data={'token': tok3['access_token']}).status_code == 200
    assert oauth.verify_access_token(tok3['access_token'], BASE + '/mcp/stocks') is None


# ------------------------------------------------------------------ список подключений


@isolated
def test_list_grants_shape_and_superseding(env):
    reg, tok, verifier = _full_flow(env)
    grants = oauth.list_grants()
    assert len(grants) == 1
    g = grants[0]
    for key in ('client_id', 'client_name', 'redirect_host', 'user_login', 'resource',
                'created_at', 'last_used_at'):
        assert key in g, key
    assert g['client_id'] == reg['client_id'] and g['client_name'] == 'Claude'
    assert g['redirect_host'] == 'claude.ai' and g['user_login'] == 'owner'
    assert g['resource'] == BASE + '/mcp/stocks'
    assert g['connector'] == 'stocks' and g['domains'] == ['stocks']
    assert g['created_at'].endswith('+03:00') and g['last_used_at'] is None
    oauth.verify_access_token(tok['access_token'], BASE + '/mcp/stocks')
    assert oauth.list_grants()[0]['last_used_at'] is not None
    # повторное согласие того же клиента на тот же коннектор заменяет прежний грант
    verifier2, challenge2 = _pkce()
    code, _ = _get_code(env, reg['client_id'], challenge2)
    env.token({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
               'client_id': reg['client_id'], 'code_verifier': verifier2}, expect=200)
    assert len(oauth.list_grants()) == 1
    assert oauth.verify_access_token(tok['access_token'], BASE + '/mcp/stocks') is None
    # другой коннектор того же клиента — отдельный грант
    verifier3, challenge3 = _pkce()
    code, _ = _get_code(env, reg['client_id'], challenge3, resource=BASE + '/mcp/content')
    env.token({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
               'client_id': reg['client_id'], 'code_verifier': verifier3}, expect=200)
    assert sorted(g['connector'] for g in oauth.list_grants()) == ['content', 'stocks']


# ------------------------------------------------------------------ прочее


@isolated
def test_token_endpoint_misc(env):
    reg, tok, _v = _full_flow(env)
    c = env.app.test_client()
    r = c.post('/oauth/token', data={'grant_type': 'password', 'client_id': reg['client_id']})
    assert r.status_code == 400 and r.get_json()['error'] == 'unsupported_grant_type'
    r = c.post('/oauth/token', data={'client_id': reg['client_id']})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_request'
    r = c.post('/oauth/token', data=MultiDict([('grant_type', 'refresh_token'),
                                               ('grant_type', 'refresh_token'),
                                               ('client_id', reg['client_id'])]))
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_request'
    r = c.post('/oauth/token', data={'grant_type': 'refresh_token', 'refresh_token': 'x'})
    assert r.status_code == 401 and r.get_json()['error'] == 'invalid_client'
    assert r.headers['Cache-Control'] == 'no-store'
    assert c.get('/oauth/token').status_code in (302, 405)   # гейт: у 405 нет эндпоинта
    # параметры из query string не читаются
    r = c.post('/oauth/token?' + urlencode({'grant_type': 'refresh_token',
                                            'refresh_token': tok['refresh_token'],
                                            'client_id': reg['client_id']}))
    assert r.status_code == 401
    # JSON-тело принимается (некоторые клиенты так шлют)
    r = c.post('/oauth/token', json={'grant_type': 'refresh_token',
                                     'refresh_token': tok['refresh_token'],
                                     'client_id': reg['client_id']})
    assert r.status_code == 200
    # тело читается с ограничением (эндпоинт публичный)
    r = c.post('/oauth/token', data={'grant_type': 'refresh_token', 'client_id': reg['client_id'],
                                     'pad': 'x' * (oauth.MAX_FORM_BYTES + 10)})
    assert r.status_code == 413 and r.get_json()['error'] == 'invalid_request'
    r = c.post('/oauth/token', data='&'.join('f%d=1' % i for i in range(oauth.MAX_FORM_FIELDS + 5)),
               content_type='application/x-www-form-urlencoded')
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_request'
    r = c.post('/oauth/token', data='[1]', content_type='application/json')
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_request'
    r = c.post('/oauth/token', data='[' * 8000 + ']' * 8000, content_type='application/json')
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_request'
    # CORS на token есть, на authorize нет
    assert r.headers['Access-Control-Allow-Origin'] == '*'
    assert c.options('/oauth/token').headers['Access-Control-Allow-Origin'] == '*'
    page = env.admin().get('/oauth/authorize')
    assert 'Access-Control-Allow-Origin' not in page.headers


@isolated
def test_scope_granted(env):
    reg = env.register()
    verifier, challenge = _pkce()
    for requested, granted in (('mcp offline_access foo', 'mcp offline_access'),
                               ('openid', 'mcp'), (_DROP, 'mcp')):
        code, _ = _get_code(env, reg['client_id'], challenge, scope=requested)
        body = env.token({'grant_type': 'authorization_code', 'code': code,
                          'redirect_uri': CLAUDE_CB, 'client_id': reg['client_id'],
                          'code_verifier': verifier}, expect=200).get_json()
        assert body['scope'] == granted, (requested, body['scope'])


@isolated
def test_secrets_stored_only_as_hashes(env):
    reg = env.register()
    verifier, challenge = _pkce()
    code, _ = _get_code(env, reg['client_id'], challenge)
    tok = env.token({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
                     'client_id': reg['client_id'], 'code_verifier': verifier},
                    expect=200).get_json()
    dump = []
    with sqlite3.connect(mcp_db.db_path()) as conn:
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            for row in conn.execute('SELECT * FROM ' + table):
                dump.append(repr(row))
    blob = '\n'.join(dump)
    for raw in (code, tok['access_token'], tok['refresh_token'], verifier):
        assert raw not in blob


# ------------------------------------------------------------------ режимы доступа


def _flow_with_mode(env, resource, mode=None, client=None):
    """Согласие на resource с выбранным режимом (None — не присылать поле) и обмен кода."""
    client = client or env.register()
    verifier, challenge = _pkce()
    c = env.admin()
    params = _auth_params(client['client_id'], challenge, resource=resource)
    page = c.get(_authorize_url(params))
    assert page.status_code == 200, page.status_code
    data = _hidden_fields(page.get_data(as_text=True)) + [('decision', 'allow')]
    if mode is not None:
        data.append(('mode', mode))
    post = c.post('/oauth/authorize', data=MultiDict(data))
    assert post.status_code == 303, (post.status_code, post.get_data(as_text=True)[:300])
    code = _location_params(post)[1]['code']
    tok = env.token({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': CLAUDE_CB,
                     'client_id': client['client_id'], 'code_verifier': verifier,
                     'resource': resource}, expect=200).get_json()
    return client, tok


@isolated
def test_mode_names_do_not_collide_with_domains(env):
    assert not set(DOMAINS) & set(MODES), 'иначе /mcp/<x> неоднозначен'
    assert len(oauth.connector_urls(BASE)) == (1 + len(DOMAINS)) * len(MODES)
    assert oauth.parse_connector_path('/mcp/stocks/draft') == ('stocks', 'draft')
    assert oauth.parse_connector_path('/mcp/read') == (None, 'read')
    for bad in ('/mcp/full', '/mcp/stocks/full', '/mcp/read/stocks', '/api/mcp', '/mcp/stocks/read/x'):
        assert oauth.parse_connector_path(bad) is None, bad
    assert oauth.allowed_modes('full') == ('full', 'draft', 'read')
    assert oauth.allowed_modes('draft') == ('draft', 'read')
    assert oauth.allowed_modes('read') == ('read',)
    assert oauth.allowed_modes('bogus') == ('read',)


@isolated
def test_consent_mode_choice_and_principal_mode(env):
    reg = env.register()
    _v, challenge = _pkce()
    page = env.admin().get(_authorize_url(_auth_params(reg['client_id'], challenge)))
    text = page.get_data(as_text=True)
    radios = re.findall(r'<input type="radio" name="mode" value="([a-z]+)"( checked)?>', text)
    assert [r[0] for r in radios] == ['full', 'draft', 'read']
    assert [r[0] for r in radios if r[1]] == ['full'], 'по умолчанию — режим адреса'
    for m in MODES:
        assert MODE_TITLES[m] in text
    # владелец сужает полный адрес до чтения — режим живёт в гранте и в Principal
    client, tok = _flow_with_mode(env, BASE + '/mcp/stocks', mode='read', client=reg)
    p = oauth.verify_access_token(tok['access_token'], BASE + '/mcp/stocks')
    assert p is not None and p.mode == 'read' and p.domains == ('stocks',)
    g = [g for g in oauth.list_grants() if g['client_id'] == client['client_id']][0]
    assert g['mode'] == 'read' and g['url_mode'] == 'full' and g['mode_title'] == MODE_TITLES['read']
    # режим переживает ротацию refresh
    new = env.token({'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                     'client_id': client['client_id']}, expect=200).get_json()
    assert oauth.verify_access_token(new['access_token'], BASE + '/mcp/stocks').mode == 'read'
    # без поля mode — режим адреса
    _c2, tok2 = _flow_with_mode(env, BASE + '/mcp/stocks/draft')
    assert oauth.verify_access_token(tok2['access_token'], BASE + '/mcp/stocks/draft').mode == 'draft'
    _c3, tok3 = _flow_with_mode(env, BASE + '/mcp', mode='draft')
    assert oauth.verify_access_token(tok3['access_token'], BASE + '/mcp').mode == 'draft'


@isolated
def test_mode_cannot_be_softened(env):
    reg = env.register()
    _v, challenge = _pkce()
    c = env.admin()
    params = _auth_params(reg['client_id'], challenge, resource=BASE + '/mcp/content/draft')
    page = c.get(_authorize_url(params))
    text = page.get_data(as_text=True)
    radios = re.findall(r'<input type="radio" name="mode" value="([a-z]+)"', text)
    assert radios == ['draft', 'read'], 'полного режима на странице нет'
    fields = _hidden_fields(text)
    for bad in ('full', 'admin', 'READ'):
        r = c.post('/oauth/authorize', data=MultiDict(fields + [('decision', 'allow'), ('mode', bad)]))
        assert r.status_code == 400 and 'Location' not in r.headers, bad
        assert 'недопустимый режим' in r.get_data(as_text=True)
    with sqlite3.connect(mcp_db.db_path()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM oauth_codes').fetchone()[0] == 0
    # на адресе /read выбора нет вовсе
    page = c.get(_authorize_url(_auth_params(reg['client_id'], challenge,
                                             resource=BASE + '/mcp/read')))
    assert re.findall(r'name="mode" value="([a-z]+)"', page.get_data(as_text=True)) == ['read']
    # и выдать код с режимом мягче адреса нельзя даже в обход формы
    req = oauth.validate_authorization_request(
        {k: [v] for k, v in _auth_params(reg['client_id'], challenge,
                                         resource=BASE + '/mcp/staff/read').items()}, BASE)
    try:
        oauth.issue_code(req, env.admin_id, 'full')
        assert False, 'issue_code должен отказать'
    except ValueError:
        pass


@isolated
def test_mode_resource_validation(env):
    reg = env.register()
    _v, challenge = _pkce()
    c = env.admin()
    for bad in (BASE + '/mcp/full', BASE + '/mcp/stocks/full', BASE + '/mcp/read/stocks',
                BASE + '/mcp/stocks/read/x', BASE + '/mcp/stocks/write'):
        r = c.get(_authorize_url(_auth_params(reg['client_id'], challenge, resource=bad)))
        assert r.status_code == 302 and _location_params(r)[1]['error'] == 'invalid_target', bad
    for good in (BASE + '/mcp/read', BASE + '/mcp/draft', BASE + '/mcp/analytics/read',
                 'HTTP://LOCALHOST/mcp/analytics/draft/'):
        r = c.get(_authorize_url(_auth_params(reg['client_id'], challenge, resource=good)))
        assert r.status_code == 200, good


@isolated
def test_mode_audience_rules(env):
    _c1, domain_draft = _flow_with_mode(env, BASE + '/mcp/stocks/draft')
    t = domain_draft['access_token']
    p = oauth.verify_access_token(t, BASE + '/mcp/stocks/draft')
    assert p is not None and p.domains == ('stocks',) and p.mode == 'draft'
    for other in ('/mcp/stocks', '/mcp/stocks/read', '/mcp/content/draft', '/mcp/draft', '/mcp'):
        assert oauth.verify_access_token(t, BASE + other) is None, other

    _c2, all_read = _flow_with_mode(env, BASE + '/mcp/read')
    t = all_read['access_token']
    assert oauth.verify_access_token(t, BASE + '/mcp/read').domains == ('*',)
    p = oauth.verify_access_token(t, BASE + '/mcp/stocks/read')
    assert p is not None and p.domains == ('*',) and p.mode == 'read', \
        'исключение полного коннектора сохраняет режим'
    for other in ('/mcp', '/mcp/stocks', '/mcp/stocks/draft', '/mcp/draft'):
        assert oauth.verify_access_token(t, BASE + other) is None, other

    # полный адрес /mcp с режимом гранта draft: работает на /mcp/<домен> (full-адрес),
    # режим в Principal — draft; на /mcp/<домен>/draft — нет (режимы адресов разные)
    _c3, all_full_draft = _flow_with_mode(env, BASE + '/mcp', mode='draft')
    t = all_full_draft['access_token']
    p = oauth.verify_access_token(t, BASE + '/mcp/staff')
    assert p is not None and p.domains == ('*',) and p.mode == 'draft'
    assert oauth.verify_access_token(t, BASE + '/mcp/staff/draft') is None
    assert oauth.verify_access_token(t, BASE + '/mcp/staff?x=1') is None
    # refresh не может сменить коннектор на другой режим
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': domain_draft['refresh_token'],
                   'client_id': _c1['client_id'], 'resource': BASE + '/mcp/stocks'})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_target'


@isolated
def test_old_database_is_migrated(env):
    """mcp.db, созданная до режимов (без колонки mode), дополняется, старые гранты — full."""
    path = os.path.join(env.tmp, 'old.db')
    mcp_db.set_db_path(path)
    with sqlite3.connect(path) as conn:
        for sql in oauth.SCHEMA:
            conn.execute(sql.replace(",\n        mode                   TEXT NOT NULL DEFAULT 'full'", '')
                         .replace(",\n        mode            TEXT NOT NULL DEFAULT 'full'", ''))
        cols = [r[1] for r in conn.execute('PRAGMA table_info(oauth_grants)')]
        assert 'mode' not in cols, 'стенд должен воспроизвести старую схему'
        now = oauth._now()
        conn.execute("INSERT INTO oauth_clients (client_id, client_name, redirect_uris, "
                     "token_endpoint_auth_method, grant_types, created_at) VALUES "
                     "('kmcpc_old', 'Old', '[\"%s\"]', 'none', '[]', ?)" % CLAUDE_CB, (now,))
        conn.execute("INSERT INTO oauth_grants (grant_id, client_id, user_id, resource, scope, "
                     "redirect_uri, created_at) VALUES ('g_old', 'kmcpc_old', ?, ?, 'mcp', ?, ?)",
                     (env.admin_id, BASE + '/mcp/stocks', CLAUDE_CB, now))
        raw = oauth.ACCESS_PREFIX + 'legacy-token-value-000000000000000000000'
        conn.execute("INSERT INTO oauth_tokens (token_hash, token_id, kind, grant_id, client_id, "
                     "user_id, resource, scope, created_at, expires_at) VALUES "
                     "(?, 'oa_old', 'access', 'g_old', 'kmcpc_old', ?, ?, 'mcp', ?, ?)",
                     (hashlib.sha256(raw.encode()).hexdigest(), env.admin_id,
                      BASE + '/mcp/stocks', now, now + 3600))
    p = oauth.verify_access_token(raw, BASE + '/mcp/stocks')
    assert p is not None and p.mode == 'full'
    with sqlite3.connect(path) as conn:
        for table in ('oauth_grants', 'oauth_codes'):
            assert 'mode' in [r[1] for r in conn.execute('PRAGMA table_info(%s)' % table)], table
    assert oauth.list_grants()[0]['mode'] == 'full'


# ------------------------------------------------------------------ отзыв всех прав пользователя


@isolated
def test_revoke_all_for_user(env):
    boss2 = env.mgr.create_user('boss2', 'Второй', 'boss2pass', is_admin=True)
    _c1, t1 = _flow_with_mode(env, BASE + '/mcp/stocks')
    _c2, t2 = _flow_with_mode(env, BASE + '/mcp/content/read')
    # грант второго администратора — не должен пострадать
    c_other = env.client('boss2', 'boss2pass')
    reg3 = env.register()
    verifier3, challenge3 = _pkce()
    code3, _ = _get_code(env, reg3['client_id'], challenge3, c=c_other)
    t3 = env.token({'grant_type': 'authorization_code', 'code': code3, 'redirect_uri': CLAUDE_CB,
                    'client_id': reg3['client_id'], 'code_verifier': verifier3},
                   expect=200).get_json()
    # ожидающий код владельца (согласие дано, обмена ещё не было)
    reg4 = env.register()
    verifier4, challenge4 = _pkce()
    code4, _ = _get_code(env, reg4['client_id'], challenge4)

    res = oauth.revoke_all_for_user(env.admin_id)
    assert res == {'grants': 2, 'tokens': 4, 'codes': 1}, res
    assert oauth.verify_access_token(t1['access_token'], BASE + '/mcp/stocks') is None
    assert oauth.verify_access_token(t2['access_token'], BASE + '/mcp/content/read') is None
    assert oauth.verify_access_token(t3['access_token'], BASE + '/mcp/stocks') is not None
    r = env.token({'grant_type': 'refresh_token', 'refresh_token': t1['refresh_token'],
                   'client_id': _c1['client_id']})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    r = env.token({'grant_type': 'authorization_code', 'code': code4, 'redirect_uri': CLAUDE_CB,
                   'client_id': reg4['client_id'], 'code_verifier': verifier4})
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid_grant'
    # возврат прав старые токены не оживляет
    env.mgr.set_admin(env.admin_id, False)
    env.mgr.set_admin(env.admin_id, True)
    assert oauth.verify_access_token(t1['access_token'], BASE + '/mcp/stocks') is None
    assert [g['user_login'] for g in oauth.list_grants()] == ['boss2']
    assert oauth.revoke_all_for_user(env.admin_id) == {'grants': 0, 'tokens': 0, 'codes': 0}
    assert oauth.revoke_all_for_user('not-a-number') == {'grants': 0, 'tokens': 0, 'codes': 0}
    assert boss2


# ------------------------------------------------------------------ ограничения DCR


@isolated
def test_registration_caps(env):
    many = ['http://localhost:%d/cb' % (4000 + i) for i in range(oauth.MAX_REDIRECT_URIS + 1)]
    assert env.register(expect=400, redirect_uris=many)['error'] == 'invalid_client_metadata'
    assert len(env.register(redirect_uris=many[:oauth.MAX_REDIRECT_URIS])['redirect_uris']) == 5
    long_uri = 'http://localhost:4000/' + 'a' * (oauth.MAX_URI_LEN - len('http://localhost:4000/') + 1)
    assert len(long_uri) == oauth.MAX_URI_LEN + 1
    assert env.register(expect=400, redirect_uris=[long_uri])['error'] in (
        'invalid_client_metadata', 'invalid_redirect_uri')
    ok_uri = long_uri[:-1]
    assert env.register(redirect_uris=[ok_uri])['redirect_uris'] == [ok_uri]
    c = env.app.test_client()
    body = {'redirect_uris': [CLAUDE_CB], 'client_name': 'x', 'software_id': 'y' * 200,
            'contacts': ['z' * 200] * 5, 'client_uri': 'https://example.org/' + 'q' * 250,
            'logo_uri': 'https://example.org/' + 'w' * 250, 'tos_uri': 'https://example.org/' + 'e' * 250,
            'policy_uri': 'https://example.org/' + 'r' * 250, 'extra': 'p' * 2500}
    oauth._registration_limiter.reset()
    r = c.post('/oauth/register', json=body)
    assert r.status_code == 413, 'все метаданные вместе не больше 4 КБ'
    assert oauth.MAX_REGISTRATION_BYTES == 4096 and oauth.MAX_CLIENT_NAME == 100


@isolated
def test_limiter_lru_and_ipv6_buckets(env):
    b = oauth.registration_bucket
    assert b('2001:db8:1:2::5') == b('2001:db8:1:2:ffff:ffff:ffff:1') == '2001:db8:1:2::/64'
    assert b('2001:db8:1:3::5') != b('2001:db8:1:2::5')
    assert b('203.0.113.9') == '203.0.113.9' and b('::ffff:203.0.113.9') == '203.0.113.9'
    assert b('fe80::1%eth0') == 'fe80::/64'
    assert b('') == '?' and b('not-an-ip') == 'not-an-ip'

    lim = oauth._SlidingWindowLimiter(limit=2, window=3600, max_keys=3)
    assert lim.hit('a') and lim.hit('a') and not lim.hit('a')   # 'a' исчерпал лимит
    assert lim.hit('b') and lim.hit('c')                         # давность: a, b, c
    assert len(lim) == 3
    assert lim.hit('d'), 'новый ключ проходит'
    assert len(lim) == 3, 'память ограничена: вытеснен самый давний ключ — a'
    # 'a' вытеснен, хотя его отметки свежие: счётчик начинается заново (цена ограничения
    # памяти; общий лимит по БД страхует)
    assert lim.hit('a'), 'вытесненный ключ со свежими отметками начинает с нуля'
    assert len(lim) == 3                                          # теперь вытеснен 'b'
    # 'c' остался в памяти и помнит своё событие: второе проходит, третье — нет
    assert lim.hit('c') and not lim.hit('c')

    # через точку регистрации: одна /64 делит лимит, соседняя — нет
    c = env.app.test_client()
    body = {'redirect_uris': [CLAUDE_CB], 'token_endpoint_auth_method': 'none'}
    oauth._registration_limiter.reset()
    for i in range(oauth.REG_PER_IP_PER_HOUR):
        r = c.post('/oauth/register', json=body,
                   headers={'X-Forwarded-For': '2001:db8:aa:1::%x' % (i + 1)})
        assert r.status_code == 201, i
    r = c.post('/oauth/register', json=body, headers={'X-Forwarded-For': '2001:db8:aa:1::ffff'})
    assert r.status_code == 429
    r = c.post('/oauth/register', json=body, headers={'X-Forwarded-For': '2001:db8:aa:2::1'})
    assert r.status_code == 201


@isolated
def test_unused_registrations_deleted_after_a_day(env):
    idle = env.register()
    used, _tok, _v = _full_flow(env)
    env.shift_time(oauth.UNUSED_CLIENT_TTL - 60)
    env.register()
    assert oauth.get_client(idle['client_id']) is not None, 'моложе суток — живёт'
    env.shift_time(oauth.UNUSED_CLIENT_TTL + 5)
    env.register()                       # чистка идёт при каждой регистрации
    assert oauth.get_client(idle['client_id']) is None
    assert oauth.get_client(used['client_id']) is not None, 'клиент с грантом не удаляется'
    assert oauth.UNUSED_CLIENT_TTL == 24 * 60 * 60


# ------------------------------------------------------------------ самозапуск


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            print(f'FAIL {t.__name__}: {e}')
            traceback.print_exc()
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(_run())
