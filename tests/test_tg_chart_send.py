"""
Отправка графика ботом @MCPkulturabot (core/tg_chart_send.py) и инструмент common_chart_send.

Что проверяется (картинка и Telegram подменены: рендер — tests/test_tg_chart_browser.py):
- при каждой отправке описание графика сохраняется под новым id (до отправки — id нужен
  кнопке), с чатом, подключением и message_id; включена кнопка или нет;
- кнопка за флагом (страница /admin/mcp, запасной путь — TG_MINIAPP_BUTTON; по умолчанию
  выключен): в личке — web_app на <адрес>?id=<id>, в группе — url на
  t.me/<бот>/<short_name>?startapp=<id>, а без short name в группе кнопки нет;
- получатель — чат разговора, списков допущенных нет; без chat_id — чат отчётов агентов;
- Telegram отказал или картинка не нарисовалась — описание удаляется; ответа нет вовсе —
  описание остаётся (сообщение могло дойти, кнопка под ним должна работать);
- через MCP: чужие ссылки вырезаются из всех строк описания, инструмент виден только в
  полном режиме, ошибки — текстом для агента (нет токена — готовая фраза владельцу со
  ссылкой на страницу), описание прямо говорит слать графики через сервис, а не своей
  картинкой; готовность для common_whoami (readiness) — без токена.

Запуск: `py -3 -m pytest tests/test_tg_chart_send.py`.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from core import tg_chart_settings, tg_charts, tg_chart_send  # noqa: E402
from core.mcp import db, registry, settings  # noqa: E402
from core.mcp.spec import allowed_in_mode  # noqa: E402
from core.tg_chart_fixtures import FIXTURES  # noqa: E402

OWNER = '670033096'
GROUP = '-1001234567890'
PNG = b'\x89PNG\r\n\x1a\nfake'


class FakeTelegram:
    def __init__(self, reply=None, outcome=None):
        self.calls = []
        self.reply = reply if reply is not None else {'ok': True, 'result': {'message_id': 77}}
        self.outcome = outcome

    def __call__(self, fields, png, token, outcome):
        self.calls.append({'fields': dict(fields), 'png': png, 'token': token})
        if self.outcome:
            outcome.append(self.outcome)
        return self.reply


@pytest.fixture
def setup(tmp_path, monkeypatch):
    db.set_db_path(str(tmp_path / 'mcp.db'))
    monkeypatch.setenv('TELEGRAM_MCP_BOT_TOKEN', 'test-mcp-bot-token')
    for name in ('TG_MINIAPP_BUTTON', 'TG_MINIAPP_URL', 'TG_MINIAPP_BOT_USERNAME', 'TG_MINIAPP_SHORT_NAME'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(tg_chart_send, 'notify_chat_id', lambda: '')
    rendered = []
    monkeypatch.setattr(tg_chart_send, '_render', lambda spec: rendered.append(spec) or PNG)
    tg = FakeTelegram()
    monkeypatch.setattr(tg_chart_send, '_transport', tg)
    yield {'tg': tg, 'rendered': rendered, 'monkeypatch': monkeypatch}
    db.set_db_path(None)


def rows():
    tg_charts._ensure()
    with db.read() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM tg_charts ORDER BY created_ts')]


def test_send_stores_description_every_time(setup):
    raw = dict(FIXTURES)['revenue']
    result = tg_chart_send.send_chart(raw, chat_id=OWNER, token_id='st_owner')
    assert result['chat_id'] == OWNER and result['message_id'] == 77 and result['button'] is None
    stored = tg_charts.get(result['chart_id'])
    assert stored['spec'] == tg_charts.normalize(raw, now=None) | {'data_at': stored['spec']['data_at']}
    assert stored['spec']['series'][1]['data'] == [506161, 491396, 601675, 355805]
    assert (stored['chat_id'], stored['token_id'], stored['sent'], stored['message_id']) == (OWNER, 'st_owner', 1, 77)
    call = setup['tg'].calls[0]
    assert call['png'] == PNG and call['token'] == 'test-mcp-bot-token'
    assert call['fields'] == {'chat_id': OWNER, 'caption': raw['title']}, 'флаг выключен — кнопки нет'
    assert setup['rendered'][0]['title'] == raw['title'], 'картинка рисуется по тому же описанию'
    second = tg_chart_send.send_chart(raw, chat_id=OWNER, caption='  Выручка   за ивент ')
    assert second['chart_id'] != result['chart_id'] and len(rows()) == 2, 'новая отправка — новое описание'
    assert setup['tg'].calls[1]['fields']['caption'] == 'Выручка за ивент'


def test_button_in_private_chat_is_web_app(setup):
    settings.set(tg_chart_settings.KEY_BUTTON, True)          # флажок на странице /admin/mcp
    result = tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=OWNER)
    markup = json.loads(setup['tg'].calls[0]['fields']['reply_markup'])
    assert markup == {'inline_keyboard': [[{'text': 'Открыть интерактивно', 'web_app': {
        'url': f'https://beerkultura.ru/tg/chart?id={result["chart_id"]}'}}]]}
    assert result['button'] == 'web_app'


def test_button_in_group_needs_short_name(setup):
    """В группе web_app-кнопки не работают: ссылка на мини-приложение из @BotFather, а без него — без кнопки."""
    mp = setup['monkeypatch']
    settings.set(tg_chart_settings.KEY_BUTTON, True)
    plain = tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=GROUP)
    assert 'reply_markup' not in setup['tg'].calls[0]['fields'] and plain['button'] is None
    assert 'короткое имя' in plain['button_note']
    settings.set(tg_chart_settings.KEY_SHORT_NAME, 'chart')
    result = tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=GROUP)
    markup = json.loads(setup['tg'].calls[1]['fields']['reply_markup'])
    assert markup == {'inline_keyboard': [[{'text': 'Открыть интерактивно',
                                            'url': f'https://t.me/MCPkulturabot/chart?startapp={result["chart_id"]}'}]]}
    assert result['button'] == 'url' and 'button_note' not in result
    settings.set(tg_chart_settings.KEY_USERNAME, 'OtherBot')    # имя бота из getMe при сохранении токена
    mp.setenv('TG_MINIAPP_URL', 'https://example.test/tg/chart')
    assert tg_chart_send.button_markup(GROUP, 'X' * 22)['inline_keyboard'][0][0]['url'] == \
        'https://t.me/OtherBot/chart?startapp=' + 'X' * 22
    assert tg_chart_send.button_markup(OWNER, 'X' * 22)['inline_keyboard'][0][0]['web_app']['url'] == \
        'https://example.test/tg/chart?id=' + 'X' * 22
    settings.set(tg_chart_settings.KEY_BUTTON, False)
    assert tg_chart_send.button_markup(GROUP, 'X' * 22) is None and tg_chart_send.button_markup(OWNER, 'X') is None


def test_button_flag_from_environment_when_not_saved(setup):
    mp = setup['monkeypatch']
    assert tg_chart_send.button_markup(OWNER, 'X' * 22) is None, 'по умолчанию кнопки нет'
    mp.setenv('TG_MINIAPP_BUTTON', '1')
    assert tg_chart_send.button_markup(OWNER, 'X' * 22) is not None
    settings.set(tg_chart_settings.KEY_BUTTON, False)
    assert tg_chart_send.button_markup(OWNER, 'X' * 22) is None, 'сохранённый флажок важнее окружения'


def test_any_conversation_chat_and_default(setup):
    """Списков допущенных нет: график уходит в чат разговора; без chat_id — в чат отчётов агентов."""
    mp = setup['monkeypatch']
    assert tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id='111222333')['chat_id'] == '111222333'
    assert tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id='-100999')['chat_id'] == '-100999'
    for chat in ('abc', '1; drop', '--1'):
        with pytest.raises(tg_chart_send.ChartSendError, match='целое число'):
            tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=chat)
    with pytest.raises(tg_chart_send.ChartSendError, match='Не указан chat_id'):
        tg_chart_send.send_chart(dict(FIXTURES)['check'])
    assert len(setup['tg'].calls) == 2 and len(rows()) == 2, 'отказы ничего не сохранили и не отправили'
    mp.setattr(tg_chart_send, 'notify_chat_id', lambda: '-100777')
    result = tg_chart_send.send_chart(dict(FIXTURES)['check'])
    assert result['chat_id'] == '-100777', 'по умолчанию — чат отчётов агентов'


def test_not_configured_without_token(setup):
    setup['monkeypatch'].delenv('TELEGRAM_MCP_BOT_TOKEN')
    with pytest.raises(tg_chart_send.ChartSendError, match='Доступ агентов') as exc:
        tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=OWNER)
    assert 'Скажи владельцу' in str(exc.value) and 'https://beerkultura.ru/admin/mcp' in str(exc.value), \
        'агент пересказывает владельцу, где вставить токен'
    settings.set(tg_chart_settings.KEY_TOKEN, '1234567890:' + 'B' * 35)     # токен со страницы /admin/mcp
    tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=OWNER)
    assert setup['tg'].calls[-1]['token'] == '1234567890:' + 'B' * 35


def test_readiness_for_whoami(setup):
    setup['monkeypatch'].delenv('TELEGRAM_MCP_BOT_TOKEN')
    ready = tg_chart_send.readiness()
    assert ready['tool'] == 'common_chart_send' and ready['ready'] is False and ready['button'] is False
    assert 'вставить токен бота @MCPkulturabot' in ready['owner_todo'] and '/admin/mcp' in ready['owner_todo']
    settings.set(tg_chart_settings.KEY_TOKEN, '1234567890:' + 'B' * 35)
    ready = tg_chart_send.readiness()
    assert ready['ready'] is True and ready['button'] is False and 'включить кнопку' in ready['owner_todo']
    settings.set(tg_chart_settings.KEY_BUTTON, True)
    assert tg_chart_send.readiness() == {'tool': 'common_chart_send', 'ready': True, 'button': True,
                                         'owner_todo': ''}
    assert '1234567890' not in json.dumps(tg_chart_send.readiness()), 'токен наружу не выходит'


def test_failures_clean_up_or_keep_description(setup):
    mp = setup['monkeypatch']
    mp.setattr(tg_chart_send, '_transport', FakeTelegram(reply={'ok': False, 'description': 'Forbidden: bot was blocked'}))
    with pytest.raises(tg_chart_send.ChartSendError, match='bot was blocked'):
        tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=OWNER)
    assert rows() == [], 'Telegram отказал — описание удалено'

    def broken(spec):
        raise RuntimeError('chromium упал')
    mp.setattr(tg_chart_send, '_render', broken)
    with pytest.raises(tg_chart_send.ChartSendError, match='chromium упал'):
        tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=OWNER)
    assert rows() == [], 'картинки нет — описание удалено'

    mp.setattr(tg_chart_send, '_render', lambda spec: PNG)
    # запрос ушёл, ответа нет: транспорт вернул None и пометил исход «неизвестно»
    mp.setattr(tg_chart_send, '_transport', lambda fields, png, token, outcome: outcome.append('unknown'))
    with pytest.raises(tg_chart_send.ChartSendError, match='Статус неизвестен'):
        tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=OWNER)
    left = rows()
    assert len(left) == 1 and left[0]['sent'] == 0, 'сообщение могло дойти — описание для кнопки осталось'


def test_bad_description_is_reported_before_anything_is_saved(setup):
    raw = dict(dict(FIXTURES)['belgium'], kind='pie')
    with pytest.raises(tg_chart_send.ChartSendError, match='Описание графика: kind'):
        tg_chart_send.send_chart(raw, chat_id=OWNER)
    assert rows() == [] and setup['tg'].calls == []
    with pytest.raises(tg_chart_send.ChartSendError, match='caption'):
        tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=OWNER, caption='x' * 1025)


def test_daily_limit(setup):
    setup['monkeypatch'].setattr(tg_chart_send, 'CHART_DAILY_LIMIT', 2)
    tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=OWNER)
    tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=OWNER)
    with pytest.raises(tg_chart_send.ChartSendError, match='Лимит'):
        tg_chart_send.send_chart(dict(FIXTURES)['check'], chat_id=OWNER)


# ------------------------------------------------------------------ через MCP

def test_mcp_tool_strips_foreign_links_and_returns_ids(setup):
    import test_mcp_protocol as tp
    raw = dict(dict(FIXTURES)['revenue'], title='Выручка, подробности на evil.example/login',
               note='см. https://beerkultura.ru/dashboard и http://phish.example')
    raw['categories'] = [dict(raw['categories'][0], note='пишите @x на bad.example')] + raw['categories'][1:]
    with tp.CommonEnv() as env:
        result = env.call('common_chart_send', {'chart': raw, 'chat_id': OWNER, 'caption': 'Отчёт: phish.example'},
                          connector=None)
        assert not result.is_error, result.text_value
        answer = json.loads(result.text_value)
        stored = tg_charts.get(answer['chart_id'])['spec']
        text = json.dumps(stored, ensure_ascii=False)
        assert 'evil' not in text and 'phish' not in text and 'bad.example' not in text
        assert 'https://beerkultura.ru/dashboard' in stored['note'], 'ссылки на свой сайт остаются'
        assert setup['tg'].calls[-1]['fields']['caption'] == 'Отчёт: [ссылка удалена]'
        assert answer['message_id'] == 77 and answer['daily_limit'] == tg_chart_send.CHART_DAILY_LIMIT
        bad_chat = env.call('common_chart_send', {'chart': raw, 'chat_id': 'чат 123'}, connector=None)
        assert bad_chat.is_error, 'схема инструмента: chat_id — число'
        bad = env.call('common_chart_send', {'chart': dict(raw, kind='pie'), 'chat_id': OWNER}, connector=None)
        assert bad.is_error, 'схема инструмента отсекает неизвестный вид'


def test_mcp_tool_flags_and_modes():
    registry.use_modules(None)
    try:
        spec = registry.get_tool('common_chart_send')
        assert spec.description.startswith('Единственный способ отправить график в Telegram'), \
            'агент бота умеет рисовать сам — описание прямо говорит слать через сервис'
        assert spec.open_world and spec.destructive and not spec.read_only and not spec.idempotent
        assert not spec.owner_notice and not spec.draft_write
        assert allowed_in_mode(spec, 'full') and not allowed_in_mode(spec, 'draft') and not allowed_in_mode(spec, 'read')
        for domain in ('content', 'stocks', 'analytics', 'staff', None):
            assert 'common_chart_send' in [t.name for t in registry.tools_for(domain)], domain
    finally:
        registry.reset()
