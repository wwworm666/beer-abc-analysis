"""
Тесты доступа MCP: статические токены, проверка Bearer (core/mcp/auth.py), настройки,
журнал вызовов и админ-API страницы «Доступ агентов» (routes/mcp.py).

Совместимы с pytest и запускаются сами: `py -3 tests/test_mcp_tokens.py`.
Каждый тест работает на временных mcp.db и auth.db (core.mcp.db.set_db_path,
AuthManager на временном файле) и возвращает глобальное состояние на место —
в CI все тесты идут одним процессом.
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask, request  # noqa: E402

import core.auth_manager as am  # noqa: E402
from core import msk_time  # noqa: E402
from core.mcp import audit, auth, db, settings, tokens  # noqa: E402
from core.mcp.principal import Principal  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'https://kultura.example/'


class Env:
    """Временные БД доступа; __exit__ возвращает прежние синглтоны."""

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix='mcp_tokens_test_')
        self.saved_mgr = am._auth_manager
        self.mgr = am.AuthManager(db_path=os.path.join(self.tmp, 'auth.db'))
        am._auth_manager = self.mgr
        db.set_db_path(os.path.join(self.tmp, 'mcp.db'))
        self.owner = self.mgr.get_by_id(self.mgr.create_user('owner', 'Владелец', 'ownerpass', is_admin=True))
        self.bob = self.mgr.get_by_id(self.mgr.create_user('bob', 'Боб', 'bobpass12'))
        return self

    def __exit__(self, *exc):
        db.set_db_path(None)
        am._auth_manager = self.saved_mgr
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def _set_token_field(token_id, field, value):
    with db.write() as conn:
        conn.execute(f'UPDATE static_tokens SET {field}=? WHERE id=?', (value, token_id))


def _auth(raw=None, domain='content', path=None, scheme='Bearer'):
    app = Flask('mcp_auth_probe')
    headers = {'Authorization': f'{scheme} {raw}'} if raw is not None else {}
    with app.test_request_context(path or ('/mcp' if domain is None else '/mcp/' + domain), method='POST',
                                  base_url=BASE, headers=headers):
        return auth.authenticate(request, domain)


# ------------------------------------------------------------------ токены

def test_create_token_format_and_storage():
    with Env() as env:
        raw, row = tokens.create(env.owner, 'Claude Code, ноутбук', ['staff', 'content'], None)
        assert raw.startswith('kmcp_') and len(raw) == len('kmcp_') + 40, raw
        assert row['prefix'] == raw[:12]
        assert row['domains'] == ['content', 'staff'], 'домены в порядке spec.DOMAINS'
        assert row['status'] == 'active' and row['expires_at'] is None
        assert 'token_hash' not in row
        with db.read() as conn:
            stored = dict(conn.execute('SELECT * FROM static_tokens').fetchone())
        assert raw not in json.dumps(stored, ensure_ascii=False), 'токен целиком не хранится'
        assert stored['token_hash'] == tokens.hash_token(raw)
        raw2, _ = tokens.create(env.owner, 'второй', None, None)
        assert raw2 != raw
        assert [t['name'] for t in tokens.list_tokens()] == ['второй', 'Claude Code, ноутбук']
        assert tokens.list is tokens.list_tokens, 'имя list() из контракта'


def test_create_token_validation():
    with Env() as env:
        for name, domains, days, fragment in (
                ('', None, None, 'имя'),
                ('x' * 81, None, None, 'длиннее'),
                ('ok', ['warehouse'], None, 'Неизвестные разделы'),
                ('ok', [], None, 'хотя бы один'),
                ('ok', None, 0.5, 'от 1'),
                ('ok', None, 'много', 'число дней'),
                ('ok', None, 99999, 'от 1')):
            try:
                tokens.create(env.owner, name, domains, days)
                raise AssertionError(f'ожидалась ошибка для {name!r} {domains!r} {days!r}')
            except ValueError as exc:
                assert fragment in str(exc), (fragment, str(exc))
        _, row = tokens.create(env.owner, 'все', ['content', '*'], 30)
        assert row['domains'] == ['*'], 'звёздочка поглощает остальные'
        _, row = tokens.create(env.owner, 'четыре', ['content', 'stocks', 'analytics', 'staff'], None)
        assert row['domains'] == ['content', 'stocks', 'analytics', 'staff'], 'все четыре — не «*»'
        assert row['expires_at'] is None


def test_verify_static_and_revoke():
    with Env() as env:
        raw, row = tokens.create(env.owner, 'ноутбук', ['content'], None)
        principal = tokens.verify_static(raw)
        assert isinstance(principal, Principal)
        assert principal.user_id == env.owner['id'] and principal.token_id == row['id']
        assert principal.token_kind == 'static' and principal.client_name == 'ноутбук'
        assert principal.domains == ('content',)
        assert principal.allows('content') and not principal.allows('stocks') and not principal.allows(None)
        assert tokens.verify_static(raw + 'x') is None
        assert tokens.verify_static('kmcpo_' + raw[5:]) is None, 'OAuth-префикс — не статический токен'
        assert tokens.verify_static('') is None and tokens.verify_static(None) is None
        assert tokens.revoke(row['id'], by='owner') is True
        assert tokens.revoke(row['id'], by='owner') is False, 'повторный отзыв ничего не меняет'
        assert tokens.revoke('st_missing') is False
        assert tokens.verify_static(raw) is None
        listed = tokens.get(row['id'])
        assert listed['status'] == 'revoked' and listed['revoked_by'] == 'owner'


def test_expired_token_rejected():
    with Env() as env:
        raw, row = tokens.create(env.owner, 'на месяц', None, 30)
        assert tokens.verify_static(raw) is not None
        past = (msk_time.now() - timedelta(minutes=1)).isoformat()
        _set_token_field(row['id'], 'expires_at', past)
        assert tokens.verify_static(raw) is None
        assert tokens.get(row['id'])['status'] == 'expired'


def test_last_used_updated_at_most_once_a_minute():
    with Env() as env:
        raw, row = tokens.create(env.owner, 't', None, None)
        tokens.verify_static(raw)
        first = tokens.get(row['id'])['last_used_at']
        assert first
        old = (msk_time.now() - timedelta(seconds=30)).replace(microsecond=0).isoformat()
        _set_token_field(row['id'], 'last_used_at', old)
        tokens.verify_static(raw)
        assert tokens.get(row['id'])['last_used_at'] == old, 'моложе минуты — не переписываем'
        older = (msk_time.now() - timedelta(seconds=90)).replace(microsecond=0).isoformat()
        _set_token_field(row['id'], 'last_used_at', older)
        tokens.verify_static(raw)
        assert tokens.get(row['id'])['last_used_at'] > older


def test_token_mode_create_verify_and_validation():
    with Env() as env:
        raw_full, row_full = tokens.create(env.owner, 'полный', None, None)
        raw_read, row_read = tokens.create(env.owner, 'дайджест', ['content'], None, mode='read')
        raw_draft, row_draft = tokens.create(env.owner, 'черновики', ['content'], None, mode='DRAFT ')
        assert (row_full['mode'], row_read['mode'], row_draft['mode']) == ('full', 'read', 'draft')
        assert tokens.verify_static(raw_full).mode == 'full'
        assert tokens.verify_static(raw_read).mode == 'read'
        assert tokens.verify_static(raw_draft).mode == 'draft'
        try:
            tokens.create(env.owner, 'x', None, None, mode='admin')
            raise AssertionError('неизвестный режим')
        except ValueError as exc:
            assert 'Режим токена' in str(exc)


def test_mode_column_migration_for_old_tables():
    with Env() as env:
        raw = 'kmcp_' + 'o' * 40
        # Таблица и строка в формате до режимов доступа (без колонки mode).
        with db.write() as conn:
            conn.execute('''CREATE TABLE static_tokens (
                id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, prefix TEXT NOT NULL, name TEXT NOT NULL,
                domains TEXT NOT NULL, user_id INTEGER NOT NULL, user_login TEXT NOT NULL, created_at TEXT NOT NULL,
                created_by TEXT NOT NULL, last_used_at TEXT, expires_at TEXT, revoked_at TEXT, revoked_by TEXT)''')
            conn.execute('INSERT INTO static_tokens (id, token_hash, prefix, name, domains, user_id, user_login, '
                         'created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                         ('st_old', tokens.hash_token(raw), raw[:12], 'старый', '["*"]', env.owner['id'], 'owner',
                          msk_time.now().isoformat(), 'owner'))
        listed = tokens.list_tokens()
        assert [(t['id'], t['mode'], t['status']) for t in listed] == [('st_old', 'full', 'active')]
        assert tokens.verify_static(raw).mode == 'full', 'старые токены работают как раньше — полный доступ'
        with db.read() as conn:
            cols = [r['name'] for r in conn.execute('PRAGMA table_info(static_tokens)').fetchall()]
        assert cols.count('mode') == 1
        _, row = tokens.create(env.owner, 'новый', None, None, mode='read')
        assert tokens.get(row['id'])['mode'] == 'read'


def test_revoke_all_for_user():
    with Env() as env:
        other = env.mgr.get_by_id(env.mgr.create_user('second', 'Второй', 'secondpass', is_admin=True))
        mine = [tokens.create(env.owner, f't{i}', None, None)[0] for i in range(2)]
        _, revoked_before = tokens.create(env.owner, 'уже отозван', None, None)
        tokens.revoke(revoked_before['id'], by='owner')
        theirs, _ = tokens.create(other, 'чужой', None, None)
        assert tokens.revoke_all_for_user(env.owner['id'], by='system') == 2
        assert tokens.revoke_all_for_user(env.owner['id']) == 0, 'повторный вызов ничего не меняет'
        assert all(tokens.verify_static(raw) is None for raw in mine)
        assert tokens.verify_static(theirs) is not None, 'токены другого владельца не тронуты'
        assert {t['revoked_by'] for t in tokens.list_tokens() if t['user_id'] == env.owner['id']} == \
            {'system', 'owner'}


def test_token_list_shows_owner_state():
    with Env() as env:
        env.mgr.create_user('second', 'Второй', 'secondpass', is_admin=True)     # чтобы owner можно было менять
        _, row = tokens.create(env.owner, 't', None, None)

        def state():
            item = tokens.get(row['id'])
            listed = next(t for t in tokens.list_tokens() if t['id'] == row['id'])
            return item['status'], listed['token_status'], listed['status'], listed['owner_state']
        assert state() == ('active', 'active', 'active', 'ok')
        env.mgr.set_active(env.owner['id'], False)
        assert state() == ('active', 'active', 'owner_disabled', 'disabled')
        env.mgr.set_active(env.owner['id'], True)
        env.mgr.set_admin(env.owner['id'], False)
        assert state() == ('active', 'active', 'owner_not_admin', 'not_admin')
        env.mgr.delete_user(env.owner['id'])
        assert state() == ('active', 'active', 'owner_missing', 'missing')
        tokens.revoke(row['id'])
        assert state()[2] == 'revoked', 'отозванный показывается отозванным при любом владельце'
        listed = next(t for t in tokens.list_tokens() if t['id'] == row['id'])
        assert listed['owner_login'] == 'owner' and listed['owner_active'] is False


# ------------------------------------------------------------------ auth.authenticate

def test_authenticate_missing_and_bad_tokens():
    with Env() as env:
        err = _auth(None)
        assert isinstance(err, auth.AuthError) and err.status == 401
        assert err.www_authenticate == ('Bearer resource_metadata="https://kultura.example/.well-known/'
                                        'oauth-protected-resource/mcp/content"'), err.www_authenticate
        err = _auth('kmcp_nope')
        assert err.status == 401 and 'error="invalid_token"' in err.www_authenticate
        raw, _ = tokens.create(env.owner, 't', None, None)
        err = _auth(raw, scheme='Basic')
        assert err.status == 401, 'схема не Bearer'
        err = _auth(None, domain=None)
        assert 'oauth-protected-resource/mcp"' in err.www_authenticate, 'полный коннектор — путь /mcp'
        err = _auth(raw, domain='warehouse')
        assert err.status == 404


def test_authenticate_ok_and_domain_scope():
    with Env() as env:
        raw, _ = tokens.create(env.owner, 'контент', ['content'], None)
        principal = _auth(raw, 'content')
        assert isinstance(principal, Principal), principal
        assert principal.login == 'owner' and principal.display_name == 'Владелец', 'имя — из свежей записи аккаунта'
        err = _auth(raw, 'stocks')
        assert isinstance(err, auth.AuthError) and err.status == 403
        assert 'error="insufficient_scope"' in err.www_authenticate
        assert 'oauth-protected-resource/mcp/stocks' in err.www_authenticate
        err = _auth(raw, None)
        assert err.status == 403, 'полный /mcp — только токену на все разделы'
        raw_all, _ = tokens.create(env.owner, 'всё', ['*'], None)
        assert isinstance(_auth(raw_all, None), Principal)
        assert isinstance(_auth(raw_all, 'staff'), Principal)


def test_authenticate_owner_must_be_active_admin():
    with Env() as env:
        raw, _ = tokens.create(env.owner, 't', None, None)
        env.mgr.create_user('second', 'Второй админ', 'secondpass', is_admin=True)   # чтобы снять флаг у owner
        env.mgr.set_admin(env.owner['id'], False)
        err = _auth(raw)
        assert isinstance(err, auth.AuthError) and err.status == 401, 'не админ — 401'
        env.mgr.set_admin(env.owner['id'], True)
        assert isinstance(_auth(raw), Principal)
        env.mgr.set_active(env.owner['id'], False)
        err = _auth(raw)
        assert isinstance(err, auth.AuthError) and err.status == 401, 'выключенный аккаунт — 401'
        bob_raw, _ = tokens.create(env.bob, 'боб', None, None)
        assert isinstance(_auth(bob_raw), auth.AuthError), 'токен не-админа не действует'


def test_authenticate_revoked_and_expired():
    with Env() as env:
        raw, row = tokens.create(env.owner, 't', None, None)
        tokens.revoke(row['id'])
        assert _auth(raw).status == 401
        raw2, row2 = tokens.create(env.owner, 't2', None, 5)
        _set_token_field(row2['id'], 'expires_at', (msk_time.now() - timedelta(days=1)).isoformat())
        assert _auth(raw2).status == 401


# ------------------------------------------------------------------ настройки

def test_settings_defaults_validation_roundtrip():
    with Env():
        assert settings.get('notify_chat_id') == ''
        assert settings.get('oauth_redirect_hosts') == ['claude.ai', 'claude.com', 'localhost', '127.0.0.1']
        assert settings.get('oauth_redirect_hosts', ['x.example']) == ['x.example'], 'default вызывающего'
        assert settings.get('unknown_key') is None
        assert settings.set('notify_chat_id', ' -1001234567890 ', by='owner') == '-1001234567890'
        assert settings.get('notify_chat_id') == '-1001234567890'
        assert settings.updated_info('notify_chat_id')['updated_by'] == 'owner'
        assert settings.set('oauth_redirect_hosts', 'Claude.AI, claude.com\nlocalhost') == \
            ['claude.ai', 'claude.com', 'localhost']
        for key, bad in (('notify_chat_id', 'abc'), ('oauth_redirect_hosts', ['https://evil.example/cb']),
                         ('oauth_redirect_hosts', ['bad host']), ('oauth_redirect_hosts', 5),
                         ('oauth_redirect_hosts', ['h%d.example' % i for i in range(21)])):
            try:
                settings.set(key, bad)
                raise AssertionError(f'ожидалась ошибка для {key}={bad!r}')
            except ValueError:
                pass
        assert settings.get('oauth_redirect_hosts') == ['claude.ai', 'claude.com', 'localhost']
        settings.set('future_flag', {'a': [1, 2]})
        assert settings.get('future_flag') == {'a': [1, 2]}
        assert set(settings.all_settings()) == {'notify_chat_id', 'oauth_redirect_hosts'}


# ------------------------------------------------------------------ журнал

def test_audit_preview_and_filters():
    with Env():
        long_text = 'я' * 500
        preview = audit.args_preview({'text': long_text, 'file': {'content_base64': 'A' * 10000}, 'n': 5})
        assert '<строка 500 симв.>' in preview and '<строка 10000 симв.>' in preview
        assert len(audit.args_preview({'rows': ['x' * 200] * 50})) <= audit.ARGS_PREVIEW_CHARS
        audit.record(user_login='owner', token_id='st_1', client_name='ноутбук', connector='content',
                     tool='content_plan_get', args={'month': '2026-09'}, status='ok', http_status=200,
                     duration_ms=12, result_chars=100)
        audit.record(user_login='owner', token_id='st_1', client_name='ноутбук', connector='all',
                     tool='stocks_board', args={}, status='error', http_status=500, error='x' * 900)
        audit.record(tool='nope', status='denied', error='нет инструмента')
        rows = audit.recent()
        assert [r['tool'] for r in rows] == ['nope', 'stocks_board', 'content_plan_get'], 'новые сверху'
        assert rows[1]['error_preview'] == 'x' * audit.ERROR_PREVIEW_CHARS
        assert rows[2]['at'].endswith('+03:00'), 'время МСК'
        assert [r['tool'] for r in audit.recent(status='error')] == ['stocks_board']
        assert [r['tool'] for r in audit.recent(tool='content_plan_get')] == ['content_plan_get']
        assert len(audit.recent(limit=1)) == 1
        try:
            audit.recent(status='weird')
            raise AssertionError('неизвестный статус')
        except ValueError:
            pass
        try:
            audit.record(tool='x', status='weird')
            raise AssertionError('неизвестный статус записи')
        except ValueError:
            pass


def _audit_rows():
    with db.read() as conn:
        return [(r['id'], r['status']) for r in conn.execute('SELECT id, status FROM audit ORDER BY id').fetchall()]


def test_audit_retention_denied_separately_and_recent_history_kept():
    with Env():
        saved = (audit.KEEP_ROWS, audit.KEEP_DENIED_ROWS, audit.CLEANUP_EVERY)
        audit.KEEP_ROWS, audit.KEEP_DENIED_ROWS, audit.CLEANUP_EVERY = 3, 2, 10
        try:
            # 6 настоящих вызовов, потом поток из 13 отказов (id 7..19), 20-я запись — снова вызов.
            for i in range(6):
                audit.record(tool=f'ok{i}', status='ok' if i % 2 == 0 else 'error')
            for i in range(13):
                audit.record(tool=f'no{i}', status='denied')
            audit.record(tool='last', status='ok')              # id 20: чистка
            rows = _audit_rows()
            denied = [i for i, s in rows if s == 'denied']
            assert denied == [18, 19], f'отказы — только последние KEEP_DENIED_ROWS: {denied}'
            kept = [i for i, s in rows if s != 'denied']
            assert kept == [1, 2, 3, 4, 5, 6, 20], f'вызовы моложе полугода не удаляются: {kept}'
            # Вызовы старше KEEP_MIN_DAYS сверх KEEP_ROWS удаляются.
            old = (msk_time.now() - timedelta(days=audit.KEEP_MIN_DAYS + 1)).isoformat(timespec='seconds')
            with db.write() as conn:
                conn.execute("UPDATE audit SET at=? WHERE id IN (1, 2, 3, 4)", (old,))
            for i in range(10):                                  # id 21..30, чистка на 30-й
                audit.record(tool=f'more{i}', status='ok')
            kept = [i for i, s in _audit_rows() if s != 'denied']
            assert kept == [5, 6, 20] + list(range(21, 31)), kept
        finally:
            audit.KEEP_ROWS, audit.KEEP_DENIED_ROWS, audit.CLEANUP_EVERY = saved


def test_audit_field_lengths_capped():
    with Env():
        audit.record(user_login='u' * 500, token_id='t' * 500, client_name='c' * 500, connector='x' * 500,
                     tool='n' * 5000, args={'a': 'b' * 100000}, status='denied', error='e' * 100000)
        row = audit.recent(limit=1)[0]
        assert len(row['tool']) == audit.TOOL_CHARS == 64
        assert len(row['user_login']) <= 64 and len(row['token_id']) <= 64
        assert len(row['client_name']) <= 100 and len(row['connector']) <= 32
        assert len(row['args_preview']) <= audit.ARGS_PREVIEW_CHARS
        assert len(row['error_preview']) == audit.ERROR_PREVIEW_CHARS
        assert [r['tool'] for r in audit.recent(token_id='t' * 64)] == ['n' * 64]
        assert audit.recent(token_id='other') == []


# ------------------------------------------------------------------ админ-API

def _admin_app():
    from core.auth_guard import init_auth
    from routes.auth import auth_bp
    from routes.mcp import mcp_bp
    app = Flask('mcp_admin_test', template_folder=os.path.join(ROOT, 'templates'),
                static_folder=os.path.join(ROOT, 'static'))
    app.register_blueprint(auth_bp)
    app.register_blueprint(mcp_bp)
    init_auth(app)
    return app


def _login(client, login, password):
    r = client.post('/login', data={'login': login, 'password': password})
    assert r.status_code in (302, 303), r.status_code


def test_admin_api_tokens_flow():
    with Env() as env:
        client = _admin_app().test_client()
        assert client.get('/api/admin/mcp/tokens').status_code == 401, 'без входа'
        _login(client, 'owner', 'ownerpass')
        r = client.post('/api/admin/mcp/tokens', json={'name': 'Claude Code', 'domains': ['content', 'staff'],
                                                       'expires_days': 30})
        assert r.status_code == 200, r.get_json()
        data = r.get_json()
        raw = data['token']
        assert raw.startswith('kmcp_') and data['row']['domains'] == ['content', 'staff']
        commands = [c['command'] for c in data['commands']]
        assert commands == [
            f'claude mcp add --transport http kultura-content http://localhost/mcp/content '
            f'--header "Authorization: Bearer {raw}"',
            f'claude mcp add --transport http kultura-staff http://localhost/mcp/staff '
            f'--header "Authorization: Bearer {raw}"'], commands
        r = client.post('/api/admin/mcp/tokens', json={'name': 'всё', 'domains': ['*']})
        full = r.get_json()
        assert [c['connector'] for c in full['commands']] == ['/mcp/content', '/mcp/stocks', '/mcp/analytics',
                                                              '/mcp/staff', '/mcp'], 'для «*» — и полный /mcp'
        assert client.post('/api/admin/mcp/tokens', json={'name': ''}).status_code == 400
        listed = client.get('/api/admin/mcp/tokens').get_json()
        assert len(listed['tokens']) == 2 and 'token_hash' not in listed['tokens'][0]
        assert raw not in json.dumps(listed, ensure_ascii=False), 'список не отдаёт токен целиком'
        assert [d['key'] for d in listed['domains']] == ['content', 'stocks', 'analytics', 'staff']
        token_id = data['row']['id']
        assert client.delete(f'/api/admin/mcp/tokens/{token_id}').get_json() == {'ok': True, 'revoked': True}
        assert client.delete('/api/admin/mcp/tokens/st_missing').status_code == 404
        assert tokens.verify_static(raw) is None


def test_admin_api_token_mode_and_commands():
    with Env():
        client = _admin_app().test_client()
        _login(client, 'owner', 'ownerpass')
        data = client.post('/api/admin/mcp/tokens', json={'name': 'ночной', 'domains': ['content'],
                                                          'mode': 'draft'}).get_json()
        raw = data['token']
        assert data['row']['mode'] == 'draft'
        assert [c['command'] for c in data['commands']] == [
            f'claude mcp add --transport http kultura-content-draft http://localhost/mcp/content/draft '
            f'--header "Authorization: Bearer {raw}"']
        assert data['commands'][0]['title'] == 'Контент и отзывы (чтение и черновики)'
        full = client.post('/api/admin/mcp/tokens', json={'name': 'всё', 'domains': ['*'], 'mode': 'read'}).get_json()
        assert [c['connector'] for c in full['commands']] == ['/mcp/content/read', '/mcp/stocks/read',
                                                              '/mcp/analytics/read', '/mcp/staff/read', '/mcp/read']
        assert full['commands'][-1]['command'].startswith('claude mcp add --transport http kultura-read ')
        assert client.post('/api/admin/mcp/tokens', json={'name': 'x', 'mode': 'root'}).status_code == 400
        listed = client.get('/api/admin/mcp/tokens').get_json()
        assert [m['key'] for m in listed['modes']] == ['read', 'draft', 'full']
        assert {t['mode'] for t in listed['tokens']} == {'draft', 'read'}


def test_admin_api_forbidden_for_non_admin():
    with Env():
        client = _admin_app().test_client()
        _login(client, 'bob', 'bobpass12')
        for method, url in (('get', '/api/admin/mcp/tokens'), ('post', '/api/admin/mcp/tokens'),
                            ('get', '/api/admin/mcp/audit'), ('get', '/api/admin/mcp/settings'),
                            ('put', '/api/admin/mcp/settings'), ('get', '/api/admin/mcp/grants'),
                            ('delete', '/api/admin/mcp/tokens/st_x'), ('delete', '/api/admin/mcp/grants/c_x')):
            r = getattr(client, method)(url, json={})
            assert r.status_code == 403, (method, url, r.status_code)
        assert client.get('/admin/mcp').status_code == 403


def test_admin_api_settings_audit_and_page():
    with Env():
        client = _admin_app().test_client()
        _login(client, 'owner', 'ownerpass')
        data = client.get('/api/admin/mcp/settings').get_json()
        assert data['settings']['notify_chat_id'] == '' and 'subscribers' in data and 'bot_configured' in data
        r = client.put('/api/admin/mcp/settings', json={'notify_chat_id': '670033096',
                                                        'oauth_redirect_hosts': ['claude.ai', 'localhost']})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['settings'] == {'notify_chat_id': '670033096',
                                            'oauth_redirect_hosts': ['claude.ai', 'localhost']}
        r = client.put('/api/admin/mcp/settings', json={'notify_chat_id': '1', 'oauth_redirect_hosts': ['bad host']})
        assert r.status_code == 400
        assert settings.get('notify_chat_id') == '670033096', 'ошибка во втором поле не пишет первое'
        assert client.put('/api/admin/mcp/settings', json={'x': 1}).status_code == 400
        assert client.put('/api/admin/mcp/settings', json={}).status_code == 400
        audit.record(tool='common_whoami', status='ok')
        items = client.get('/api/admin/mcp/audit?limit=5&status=ok').get_json()['items']
        assert [i['tool'] for i in items] == ['common_whoami']
        assert client.get('/api/admin/mcp/audit?status=bad').status_code == 400
        grants = client.get('/api/admin/mcp/grants').get_json()
        assert 'available' in grants and isinstance(grants['grants'], list)
        page = client.get('/admin/mcp')
        assert page.status_code == 200
        html = page.get_data(as_text=True)
        assert 'Доступ агентов' in html and 'http://localhost/mcp/content' in html


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
