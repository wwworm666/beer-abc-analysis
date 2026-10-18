"""
Настройки графиков бота @MCPkulturabot (core/tg_chart_settings.py) и их API на странице
«Доступ агентов» (GET/PUT /api/admin/mcp/charts в routes/mcp.py).

Что проверяется:
- токен сохраняется только проверенным: формат «число:строка» и getMe в Telegram;
  отказ Telegram — ничего не записано; нет связи — записан с предупреждением; имя бота
  из getMe запоминается (оно в ссылке для групп);
- токен не выходит наружу: ни в public_view, ни в ответах API — только «1234…xyz»;
- настройки страницы важнее переменных окружения, пустые — запасной путь из окружения;
- флажок кнопки и короткое имя мини-приложения проверяются, ошибка в одном поле не
  сохраняет другие;
- API только для администратора: без входа 401, не-админу 403; лишние поля — 400.

Запуск: `py -3 -m pytest tests/test_tg_chart_settings.py`.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from core import tg_chart_settings as cs  # noqa: E402
from core.mcp import db, settings  # noqa: E402

GOOD = '1234567890:' + 'A' * 35
OTHER = '987654321:' + 'b' * 35


def getme_ok(username='MCPkulturabot'):
    calls = []

    def fake(token):
        calls.append(token)
        return {'ok': True, 'result': {'id': 1, 'is_bot': True, 'username': username}}
    fake.calls = calls
    return fake


@pytest.fixture
def store(tmp_path, monkeypatch):
    db.set_db_path(str(tmp_path / 'mcp.db'))
    for name in (cs.BOT_TOKEN_ENV, cs.BUTTON_FLAG_ENV, cs.SHORT_NAME_ENV, cs.BOT_USERNAME_ENV, cs.APP_URL_ENV):
        monkeypatch.delenv(name, raising=False)
    yield monkeypatch
    db.set_db_path(None)


def test_token_saved_after_telegram_check(store):
    fake = getme_ok('MCPkulturabot')
    view = cs.save(token=f'  {GOOD} ', getme=fake)
    assert fake.calls == [GOOD], 'getMe вызывается с токеном без пробелов'
    assert cs.bot_token() == GOOD and cs.token_source() == 'settings'
    assert view['configured'] and view['bot_username'] == 'MCPkulturabot' and view['warning'] == ''
    assert view['token_hint'] == '1234…AAA' and GOOD not in repr(view), 'токен наружу не выходит'


def test_bad_tokens_are_not_saved(store):
    with pytest.raises(ValueError, match='Это не токен'):
        cs.save(token='не токен', getme=getme_ok())
    with pytest.raises(ValueError, match='Это не токен'):
        cs.save(token='123:short', getme=getme_ok())
    refused = lambda token: {'ok': False, 'error_code': 401, 'description': 'Unauthorized'}  # noqa: E731
    with pytest.raises(ValueError, match='Telegram не принял токен: Unauthorized'):
        cs.save(token=GOOD, button=True, getme=refused)
    assert cs.bot_token() == '' and cs.button_enabled() is False, 'отказ — ничего не записано, даже флажок'


def test_offline_save_keeps_token_with_warning(store):
    cs.save(token=GOOD, getme=getme_ok('FirstBot'))
    view = cs.save(token=OTHER, getme=lambda token: None)
    assert cs.bot_token() == OTHER and 'Нет связи с Telegram' in view['warning']
    assert view['bot_username'] == 'FirstBot', 'имя бота без проверки не меняется'


def test_settings_win_over_environment_and_clear_falls_back(store):
    store.setenv(cs.BOT_TOKEN_ENV, OTHER)
    store.setenv(cs.BOT_USERNAME_ENV, '@EnvBot')
    assert cs.bot_token() == OTHER and cs.token_source() == 'env' and cs.bot_username() == 'EnvBot'
    cs.save(token=GOOD, getme=getme_ok('MCPkulturabot'))
    assert cs.bot_token() == GOOD and cs.bot_username() == 'MCPkulturabot'
    view = cs.save(clear_token=True)
    assert cs.bot_token() == OTHER and view['source'] == 'env' and cs.bot_username() == 'EnvBot'
    store.delenv(cs.BOT_TOKEN_ENV)
    assert cs.public_view()['configured'] is False and cs.public_view()['token_hint'] == ''


def test_button_and_short_name(store):
    assert cs.button_enabled() is False and cs.short_name() == '', 'по умолчанию: кнопки нет, имени нет'
    store.setenv(cs.BUTTON_FLAG_ENV, 'on')
    store.setenv(cs.SHORT_NAME_ENV, 'envapp')
    assert cs.button_enabled() is True and cs.short_name() == 'envapp'
    cs.save(button=False, short_name_value='chart')
    assert cs.button_enabled() is False and cs.short_name() == 'chart', 'сохранённое важнее окружения'
    with pytest.raises(ValueError, match='Короткое имя'):
        cs.save(short_name_value='плохое имя')
    with pytest.raises(ValueError, match='Кнопка'):
        cs.save(button='да')
    assert cs.short_name() == 'chart'
    cs.save(short_name_value='')
    assert cs.short_name() == 'envapp', 'пустое имя — запасной путь из окружения'
    assert cs.app_url() == 'https://beerkultura.ru/tg/chart'


# ------------------------------------------------------------------ API страницы «Доступ агентов»

def test_admin_api(store):
    import test_mcp_tokens as tt
    store.setattr(cs, '_getme', getme_ok('MCPkulturabot'))
    with tt.Env():
        client = tt._admin_app().test_client()
        assert client.get('/api/admin/mcp/charts').status_code == 401, 'без входа'
        tt._login(client, 'bob', 'bobpass12')
        assert client.get('/api/admin/mcp/charts').status_code == 403
        assert client.put('/api/admin/mcp/charts', json={'token': GOOD}).status_code == 403
        client = tt._admin_app().test_client()
        tt._login(client, 'owner', 'ownerpass')
        view = client.get('/api/admin/mcp/charts').get_json()
        assert view['configured'] is False and view['button'] is False
        r = client.put('/api/admin/mcp/charts', json={'token': GOOD, 'button': True, 'short_name': 'chart'})
        assert r.status_code == 200, r.get_json()
        body = r.get_data(as_text=True)
        assert GOOD not in body and '1234…AAA' in r.get_json()['token_hint']
        assert r.get_json()['button'] is True and r.get_json()['short_name'] == 'chart'
        assert settings.get(cs.KEY_TOKEN) == GOOD and settings.updated_info(cs.KEY_TOKEN)['updated_by'] == 'owner'
        assert GOOD not in client.get('/api/admin/mcp/charts').get_data(as_text=True)
        assert client.put('/api/admin/mcp/charts', json={'token': 'плохой'}).status_code == 400
        assert client.put('/api/admin/mcp/charts', json={'token': 5}).status_code == 400
        assert client.put('/api/admin/mcp/charts', json={'secret': 1}).status_code == 400
        assert client.put('/api/admin/mcp/charts', json={'clear_token': True}).get_json()['configured'] is False
