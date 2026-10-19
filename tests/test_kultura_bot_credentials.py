"""
Секреты бота @MCPkulturabot (kultura_bot/credentials.py) и раздел «Бот» страницы «Доступ
агентов» (GET/PUT /api/admin/mcp/bot, ссылка привязки и отвязка в routes/mcp.py).

Что проверяется:
- токен сохраняется только проверенным: формат «число:строка» и getMe в Telegram; отказ
  Telegram — ничего не записано; нет связи — записан с предупреждением; имя бота из getMe
  запоминается;
- ключ Anthropic: формат sk-ant-…, живая проверка (список моделей); 401 — не сохраняется,
  403 и «нет связи» — сохраняется с предупреждением (нужен прокси); новый прокси —
  повторная проверка ключа уже через него;
- прокси: только http(s) с хостом, на странице без логина и пароля, «-» убирает;
- секреты наружу не выходят: ни в public_view, ни в ответах API — только «1234…xyz»;
- страница важнее окружения, пустое — запасной путь из окружения;
- API только для администратора: без входа 401, не-админу 403; лишние поля — 400; ссылка
  привязки — для текущего администратора; отвязка.

Запуск: `py -3 -m pytest tests/test_kultura_bot_credentials.py`.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from core.mcp import db, settings  # noqa: E402
from kultura_bot import credentials as cs  # noqa: E402

GOOD = '1234567890:' + 'A' * 35
OTHER = '987654321:' + 'b' * 35
KEY = 'sk-ant-api03-' + 'k' * 40
KEY2 = 'sk-ant-api03-' + 'z' * 40


def getme_ok(username='MCPkulturabot'):
    calls = []

    def fake(token):
        calls.append(token)
        return {'ok': True, 'result': {'id': 1, 'is_bot': True, 'username': username}}
    fake.calls = calls
    return fake


def check(kind='ok', detail='claude-opus-5-5'):
    calls = []

    def fake(key, proxy):
        calls.append((key, proxy))
        return kind, detail
    fake.calls = calls
    return fake


@pytest.fixture
def store(tmp_path, monkeypatch):
    db.set_db_path(str(tmp_path / 'mcp.db'))
    for name in (cs.BOT_TOKEN_ENV, cs.ANTHROPIC_ENV, cs.PROXY_ENV):
        monkeypatch.delenv(name, raising=False)
    yield monkeypatch
    db.set_db_path(None)


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
        cs.save(token=GOOD, anthropic_key_value=KEY, getme=refused, check_key=check())
    assert cs.bot_token() == '' and cs.anthropic_key() == '', 'отказ — ничего не записано, даже ключ'


def test_offline_save_keeps_token_with_warning(store):
    cs.save(token=GOOD, getme=getme_ok('FirstBot'))
    view = cs.save(token=OTHER, getme=lambda token: None)
    assert cs.bot_token() == OTHER and 'Нет связи с Telegram' in view['warnings'][0]
    assert view['telegram']['bot_username'] == 'FirstBot', 'имя бота без проверки не меняется'


def test_anthropic_key_checked_and_hidden(store):
    with pytest.raises(ValueError, match='sk-ant-'):
        cs.save(anthropic_key_value='abc', check_key=check())
    fake = check()
    view = cs.save(anthropic_key_value=f' {KEY} ', check_key=fake)
    assert fake.calls == [(KEY, '')] and cs.anthropic_key() == KEY
    assert view['anthropic'] == {'configured': True, 'source': 'settings', 'key_hint': 'sk-a…kkk'}
    assert KEY not in repr(view)
    with pytest.raises(ValueError, match='не принял ключ'):
        cs.save(anthropic_key_value=KEY2, check_key=check('auth', 'Anthropic не принял ключ API (401).'))
    assert cs.anthropic_key() == KEY, '401 — новый ключ не сохранён'
    view = cs.save(anthropic_key_value=KEY2, check_key=check('denied', 'Anthropic отказал серверу (403)'))
    assert cs.anthropic_key() == KEY2 and 'отказал серверу' in view['warnings'][0], '403 — сохранён с подсказкой'


def test_proxy_rechecks_key_and_is_shown_without_password(store):
    cs.save(anthropic_key_value=KEY, check_key=check())
    with pytest.raises(ValueError, match='Прокси'):
        cs.save(proxy='socks5://host:1080', check_key=check())
    with pytest.raises(ValueError, match='Прокси'):
        cs.save(proxy='не адрес', check_key=check())
    for bad_port in ('http://u:p@host:abc', 'http://host:70000'):
        with pytest.raises(ValueError, match='порт'):
            cs.save(proxy=bad_port, check_key=check())
    assert cs.proxy_url() == '', 'кривой порт — ничего не записано'
    store.setenv(cs.PROXY_ENV, 'http://host:abc')
    assert cs.public_view()['proxy']['display'].startswith('задан'), 'кривой адрес из окружения не роняет страницу'
    store.delenv(cs.PROXY_ENV)
    fake = check()
    view = cs.save(proxy='http://user:secret@proxy.example:3128', check_key=fake)
    assert fake.calls == [(KEY, 'http://user:secret@proxy.example:3128')], 'ключ проверен через новый прокси'
    assert view['proxy'] == {'configured': True, 'display': 'http://proxy.example:3128'}
    assert 'secret' not in repr(view)
    cs.save(proxy='', check_key=check())
    assert cs.proxy_url() == ''


def test_settings_win_over_environment_and_clear_falls_back(store):
    store.setenv(cs.BOT_TOKEN_ENV, OTHER)
    store.setenv(cs.ANTHROPIC_ENV, KEY2)
    assert cs.bot_token() == OTHER and cs.token_source() == 'env' and cs.anthropic_key() == KEY2
    cs.save(token=GOOD, anthropic_key_value=KEY, getme=getme_ok(), check_key=check())
    assert cs.bot_token() == GOOD and cs.anthropic_key() == KEY
    view = cs.save(clear_token=True, clear_anthropic_key=True)
    assert cs.bot_token() == OTHER and view['telegram']['source'] == 'env' and cs.anthropic_key() == KEY2
    store.delenv(cs.BOT_TOKEN_ENV)
    assert cs.public_view()['telegram']['configured'] is False


def test_pause(store):
    assert cs.paused() is False
    cs.save(paused_value=True)
    assert cs.paused() is True and cs.public_view()['paused'] is True
    with pytest.raises(ValueError, match='Пауза'):
        cs.save(paused_value='да')


# ------------------------------------------------------------------ API страницы «Доступ агентов»

def test_admin_api(store):
    import test_mcp_tokens as tt
    store.setattr(cs, '_getme', getme_ok('MCPkulturabot'))
    store.setattr(cs, '_check_key', check())
    with tt.Env() as env:
        client = tt._admin_app().test_client()
        assert client.get('/api/admin/mcp/bot').status_code == 401, 'без входа'
        tt._login(client, 'bob', 'bobpass12')
        assert client.get('/api/admin/mcp/bot').status_code == 403
        assert client.put('/api/admin/mcp/bot', json={'token': GOOD}).status_code == 403
        assert client.post('/api/admin/mcp/bot/link').status_code == 403
        client = tt._admin_app().test_client()
        tt._login(client, 'owner', 'ownerpass')
        view = client.get('/api/admin/mcp/bot').get_json()
        assert view['telegram']['configured'] is False and view['anthropic']['configured'] is False
        assert view['status']['state'] == 'stopped' and view['links'] == [] and view['model']
        r = client.put('/api/admin/mcp/bot', json={'token': GOOD, 'anthropic_key': KEY, 'paused': False})
        assert r.status_code == 200, r.get_json()
        body = r.get_data(as_text=True)
        assert GOOD not in body and KEY not in body and r.get_json()['telegram']['token_hint'] == '1234…AAA'
        assert settings.get(cs.KEY_TOKEN) == GOOD and settings.updated_info(cs.KEY_TOKEN)['updated_by'] == 'owner'
        assert client.put('/api/admin/mcp/bot', json={'token': 'плохой'}).status_code == 400
        assert client.put('/api/admin/mcp/bot', json={'anthropic_key': 5}).status_code == 400
        assert client.put('/api/admin/mcp/bot', json={'secret': 1}).status_code == 400
        assert client.put('/api/admin/mcp/bot', json={'paused': 'да'}).status_code == 400

        link = client.post('/api/admin/mcp/bot/link').get_json()
        assert link['url'].startswith('https://t.me/MCPkulturabot?start=') and link['expires_in_s'] == 900
        from kultura_bot import access, store as bot_store
        answer = access.link_by_code(link['code'], '555', 'Анна')
        assert answer['ok'] and 'Владелец' in answer['text']
        links = client.get('/api/admin/mcp/bot').get_json()['links']
        assert [(x['tg_user_id'], x['login'], x['tg_name']) for x in links] == [('555', 'owner', 'Анна')]
        assert client.delete('/api/admin/mcp/bot/links/abc').status_code == 400
        assert client.delete('/api/admin/mcp/bot/links/555').get_json() == {'ok': True}
        assert bot_store.list_links() == []
        assert env.owner['login'] == 'owner'
