"""
Бот @MCPkulturabot (kultura_bot/): инструкции, инструменты, разговор с Claude, оформление,
привязка Telegram и обработка сообщений. Claude и Telegram подменены — сеть не нужна.

Что проверяется:
- инструкции: все agents/*.md разбираются, у каждого известные разделы; ошибки заголовка
  называют файл; системный промпт бота собран из prompts/bot.md, списка агентов и правил
  сервиса; промпт агента — с правилами его разделов;
- инструменты: поиск первым, видимые сразу — без defer_loading, остальные инструменты
  сайта — отложенные; скрытых нет; ask_agent только у бота; агенту — только его разделы;
  порядок неизменен (иначе кэш и привязка рассуждений сломались бы);
- разговор: параметры запроса (модель, усилие, кэш, context editing, fallbacks,
  block_binding); отвергнутая API необязательная возможность выключается, запрос
  повторяется; история только дописывается; инструмент сайта исполняется мостом от имени
  администратора и пишется в журнал с коннектором telegram; график уходит в чат разговора,
  какой бы chat_id ни прислала модель; pause_turn; предел шагов (последний запрос без
  инструментов); дневной предел расхода; расход пишется в bot_usage;
- ask_agent: агент работает со своими инструкциями и инструментами, отчёт возвращается боту;
- ошибки: понятный текст по виду ошибки, без ключа и прокси (scrub);
- оформление: Markdown -> HTML Telegram с экранированием; таблицы и код — <pre>; длинный
  ответ режется по абзацам, блок кода не рвётся;
- доступ: код привязки одноразовый и живёт 15 минут, не-админ не подключится, снятие
  админства действует сразу; незнакомцу — «закрытый бот» не чаще раза в час;
- сообщения: /start <код>, /new, /help; в группе — только по обращению; ответ и диалог;
  новый диалог после паузы и после смены инструкций; ошибки Anthropic — понятным текстом;
  оборванные перезапуском ответы; 409 от Telegram — состояние conflict.

Запуск: `py -3 -m pytest tests/test_kultura_bot.py`.
"""
import copy
import json
import os
import sys
import time
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from flask import Flask  # noqa: E402

from core.mcp import audit, db, registry  # noqa: E402
from kultura_bot import (access, agent, claude, config, credentials, formatting, service,  # noqa: E402
                         settings, store, tools)
from kultura_bot.charts import send as chart_send  # noqa: E402
from kultura_bot.charts.fixtures import FIXTURES  # noqa: E402

TOKEN = '1234567890:' + 'T' * 35
KEY = 'sk-ant-api03-' + 'k' * 40
OWNER_TG = '555'
PNG = b'\x89PNG\r\n\x1a\nfake'
TOOL_NAME_RE = r'^[a-zA-Z0-9_-]{1,128}$'


# ------------------------------------------------------------------ подмены

def resp(*blocks, stop='end_turn', model='claude-opus-5-5', usage=(1000, 200, 0, 0)):
    return SimpleNamespace(content=list(blocks), stop_reason=stop, model=model,
                           usage=SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1],
                                                 cache_read_input_tokens=usage[2],
                                                 cache_creation_input_tokens=usage[3]))


def text(value):
    return {'type': 'text', 'text': value}


def thinking():
    return {'type': 'thinking', 'thinking': '', 'signature': 'sig-' + str(time.time_ns())}


def use(name, args, id_='toolu_1'):
    return {'type': 'tool_use', 'id': id_, 'name': name, 'input': args}


class FakeClient:
    """client.beta.messages.create: ответы по сценарию; каждый запрос запоминается копией."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params):
        self.calls.append(copy.deepcopy(params))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item(params) if callable(item) else item


class FakeTelegram:
    def __init__(self, token=TOKEN):
        self.token = token
        self.sent = []          # (chat_id, text, reply_to)
        self.updates = []
        self.webhook_deleted = 0
        self.typing_count = 0

    def get_me(self):
        return {'ok': True, 'result': {'id': 999, 'username': 'MCPkulturabot'}}

    def delete_webhook(self):
        self.webhook_deleted += 1
        return {'ok': True}

    def set_commands(self):
        return None

    def get_updates(self, offset):
        return self.updates.pop(0) if self.updates else {'ok': True, 'result': []}

    def typing(self, chat_id):
        self.typing_count += 1

    def send_plain(self, chat_id, text_value, reply_to=None):
        self.sent.append((str(chat_id), text_value, reply_to))
        return 1

    def send_markdown(self, chat_id, markdown, reply_to=None):
        self.sent.append((str(chat_id), markdown, reply_to))
        return [1]

    def download(self, file_id, max_bytes):
        return b'jpegbytes'


class FakeChartTelegram:
    def __init__(self):
        self.calls = []

    def __call__(self, fields, png, token, outcome):
        self.calls.append(dict(fields))
        return {'ok': True, 'result': {'message_id': 77}}


@pytest.fixture
def env(monkeypatch):
    import test_mcp_tokens as tt
    with tt.Env() as accounts:
        monkeypatch.setenv(credentials.BOT_TOKEN_ENV, TOKEN)
        monkeypatch.setenv(credentials.ANTHROPIC_ENV, KEY)
        monkeypatch.setattr(settings, 'DAILY_BUDGET_USD', 15.0)
        monkeypatch.setattr(agent, '_disabled', set())
        monkeypatch.setattr(chart_send, '_render', lambda spec: PNG)
        charts = FakeChartTelegram()
        monkeypatch.setattr(chart_send, '_transport', charts)
        monkeypatch.setattr(chart_send, 'notify_chat_id', lambda: '')
        from core.mcp import protocol
        protocol.rate_limiter.reset()
        app = Flask('kultura_bot_test')
        yield SimpleNamespace(app=app, accounts=accounts, charts=charts, monkeypatch=monkeypatch)


def owner_actor(env):
    return {'tg_user_id': OWNER_TG, 'user_id': env.accounts.owner['id'], 'login': 'owner',
            'display_name': 'Владелец'}


def ctx_for(env, chat_id=OWNER_TG):
    return tools.ToolContext(app=env.app, principal=access.principal_for(owner_actor(env)), chat_id=chat_id)


# ------------------------------------------------------------------ инструкции

def test_agents_and_prompts_load():
    agents = config.load_agents()
    assert set(agents) == {'analyst', 'payroll', 'content'}
    assert agents['payroll'].domains == ('staff',) and agents['analyst'].domains == ('stocks', 'analytics')
    text_bot = config.bot_system_text()
    assert text_bot.startswith(config.bot_prompt()[:60])
    assert '- payroll — Зарплаты и график:' in text_bot and 'ПРАВИЛА БЕЗОПАСНОСТИ' in text_bot
    payroll = config.agent_system_text(agents['payroll'])
    assert config.agent_prompt()[:40] in payroll and agents['payroll'].instructions[:40] in payroll
    assert '# Правила раздела «Сотрудники, график и зарплаты» (staff)' in payroll
    assert '(stocks)' not in payroll, 'агенту — только правила его разделов'


@pytest.mark.parametrize('text_value, error', [
    ('нет заголовка', 'начинается со строки'),
    ('---\nname: x\n', 'не закрыт'),
    ('---\nname: payroll\ntitle: t\ndomains: staff\n---\nтекст', 'description'),
    ('---\nname: Pay Roll\ntitle: t\ndomains: staff\ndescription: d\n---\nтекст', 'name'),
    ('---\nname: pp\ntitle: t\ndomains: kitchen\ndescription: d\n---\nтекст', 'неизвестные: kitchen'),
    ('---\nname: pp\ntitle: t\ndomains: staff\ndescription: d\n---\n', 'нет текста'),
    ('---\nname: pp\ntitle t\n---\nтекст', 'ключ: значение'),
])
def test_agent_file_errors_name_the_file(text_value, error):
    with pytest.raises(config.ConfigError, match=error) as exc:
        config.parse_agent(text_value, path='agents/x.md')
    assert 'agents/x.md' in str(exc.value)


# ------------------------------------------------------------------ инструменты

def test_bot_tools_search_loaded_and_deferred():
    defs = tools.tool_defs(agent_names=['analyst', 'payroll', 'content'])
    assert defs[0] == tools.SEARCH_TOOL
    names = [d['name'] for d in defs]
    loaded = [d['name'] for d in defs[1:] if not d.get('defer_loading')]
    assert loaded == sorted(settings.ALWAYS_LOADED_TOOLS) + [tools.ASK_AGENT]
    deferred = [d for d in defs if d.get('defer_loading')]
    site = {t.name for t in registry.all_tools()} - set(settings.HIDDEN_TOOLS)
    assert {d['name'] for d in deferred} | set(settings.ALWAYS_LOADED_TOOLS) == site
    assert 'common_notify_owner' not in names, 'сообщение владельцу через другого бота боту не нужно'
    import re
    assert all(re.match(TOOL_NAME_RE, n) for n in names) and len(names) == len(set(names))
    assert all(d['input_schema'].get('type') == 'object' for d in defs[1:])
    ask = next(d for d in defs if d['name'] == tools.ASK_AGENT)
    assert ask['input_schema']['properties']['agent']['enum'] == ['analyst', 'payroll', 'content']
    assert tools.tool_defs(agent_names=['analyst', 'payroll', 'content']) == defs, 'порядок неизменен'


def test_agent_tools_only_its_domains():
    defs = tools.tool_defs(domains=('staff',))
    names = {d['name'] for d in defs[1:]}
    assert tools.ASK_AGENT not in names
    expected = {t.name for t in registry.tools_for('staff')} - set(settings.HIDDEN_TOOLS)
    assert names == expected, 'агенту — то же, что коннектору раздела /mcp/staff (с also_in)'
    assert not any(n.startswith(('stocks_', 'content_')) for n in names) and 'common_chart_send' in names


# ------------------------------------------------------------------ разговор

def test_turn_runs_site_tool_and_keeps_history_append_only(env):
    client = FakeClient(
        resp(thinking(), use('common_whoami', {}), stop='tool_use'),
        resp(thinking(), text('Сегодня **19 октября**.')),
    )
    ctx = ctx_for(env)
    history = [{'role': 'user', 'content': [text('[время] привет')]},
               {'role': 'assistant', 'content': [thinking(), text('Здравствуйте')]}]
    frozen = copy.deepcopy(history)
    result = agent.run_turn(client, system_text='СИСТЕМА', tool_list=[tools.SEARCH_TOOL], history=history,
                            user_content=[text('какое сегодня число?')], ctx=ctx)
    assert result.text == 'Сегодня **19 октября**.' and result.rounds == 1 and result.stop_reason == 'end_turn'
    first, second = client.calls
    assert first['messages'][:2] == frozen and second['messages'][:len(first['messages'])] == first['messages'], \
        'история только дописывается'
    assert first['model'] == settings.MODEL and first['output_config'] == {'effort': settings.EFFORT}
    assert first['system'] == [{'type': 'text', 'text': 'СИСТЕМА', 'cache_control': {'type': 'ephemeral'}}]
    assert first['cache_control'] == {'type': 'ephemeral'} and first['fallbacks'] == 'default'
    assert set(first['betas']) == {agent.BETA_CONTEXT, agent.BETA_THINKING_BINDING, agent.BETA_FALLBACK}
    assert first['thinking'] == {'type': 'adaptive', 'block_binding': {'prefix_mismatch_behavior': 'drop_block'}}
    edit = first['context_management']['edits'][0]
    assert edit['type'] == 'clear_tool_uses_20250919' and edit['exclude_tools'] == ['tool_search_tool_regex']
    assert 'tool_choice' not in first
    tool_result = second['messages'][-1]['content'][0]
    assert tool_result['type'] == 'tool_result' and tool_result['tool_use_id'] == 'toolu_1'
    assert 'is_error' not in tool_result and json.loads(tool_result['content'][0]['text'])['owner']['login'] == 'owner'
    row = audit.recent(limit=1)[0]
    assert (row['tool'], row['connector'], row['status'], row['token_id']) == \
        ('common_whoami', 'telegram', 'ok', f'tg_{OWNER_TG}')
    assert row['client_name'] == 'Бот @MCPkulturabot'
    assert result.cost_usd == pytest.approx(2 * claude.cost_usd('claude-opus-5-5', {'input_tokens': 1000,
                                                                                    'output_tokens': 200}))
    assert store.spent_on() == pytest.approx(result.cost_usd)


def test_chart_goes_to_conversation_chat(env):
    raw = dict(FIXTURES)['check']
    client = FakeClient(
        resp(use('common_chart_send', {'chart': raw, 'chat_id': '-100666'}), stop='tool_use'),
        resp(text('Средний чек вырос.')),
    )
    ctx = ctx_for(env, chat_id='-100123')
    result = agent.run_turn(client, system_text='S', tool_list=[], history=[], user_content=[text('график')],
                            ctx=ctx)
    assert env.charts.calls[0]['chat_id'] == '-100123', 'чат подставляет бот, а не модель'
    assert len(ctx.charts_sent) == 1 and result.text == 'Средний чек вырос.'


def test_unknown_tool_and_bad_args_are_errors_for_model(env):
    ctx = ctx_for(env)
    assert tools.execute(use('no_such_tool', {}), ctx)['is_error'] is True
    assert tools.execute({'type': 'tool_use', 'id': 't', 'name': 'common_whoami', 'input': 'x'}, ctx)['is_error']
    agent_ctx = tools.ToolContext(app=env.app, principal=ctx.principal, chat_id='1', domains=('staff',))
    assert tools.execute(use('stocks_suppliers_list', {}), agent_ctx)['is_error'], 'агенту чужой раздел не виден'
    assert tools.execute(use(tools.ASK_AGENT, {'agent': 'payroll', 'task': 'проверь зарплату'}), agent_ctx)['is_error']


def test_pause_turn_is_resumed_without_new_message(env):
    client = FakeClient(resp(text('…'), stop='pause_turn'), resp(text('Готово')))
    result = agent.run_turn(client, system_text='S', tool_list=[], history=[], user_content=[text('?')],
                            ctx=ctx_for(env))
    assert result.text == 'Готово'
    assert client.calls[1]['messages'][-1]['role'] == 'assistant', 'повтор без нового сообщения человека'


def test_round_limit_forces_final_answer(env):
    env.monkeypatch.setattr(settings, 'MAX_TOOL_ROUNDS', 1)
    client = FakeClient(
        resp(use('common_whoami', {}, 't1'), stop='tool_use'),
        resp(use('common_whoami', {}, 't2'), stop='tool_use'),
        resp(text('Что успел — то знаю.')),
    )
    result = agent.run_turn(client, system_text='S', tool_list=[], history=[], user_content=[text('?')],
                            ctx=ctx_for(env))
    assert 'max_rounds' in result.notes and result.text == 'Что успел — то знаю.'
    assert client.calls[2]['tool_choice'] == {'type': 'none'}
    refusal = client.calls[2]['messages'][-1]['content'][0]
    assert refusal['tool_use_id'] == 't2' and refusal['is_error'] is True


def test_rejected_optional_feature_is_dropped_and_retried(env):
    import anthropic
    import httpx2
    req = httpx2.Request('POST', 'https://api.anthropic.com/v1/messages')

    def bad(message):
        return anthropic.BadRequestError(message, response=httpx2.Response(400, request=req), body=None)

    client = FakeClient(bad('fallbacks: Extra inputs are not permitted'), resp(text('Ответ')),
                        resp(text('Второй')), bad('messages.0: что-то другое'))
    result = agent.run_turn(client, system_text='S', tool_list=[], history=[], user_content=[text('?')],
                            ctx=ctx_for(env))
    assert result.text == 'Ответ' and len(client.calls) == 2
    assert 'fallbacks' in client.calls[0] and 'fallbacks' not in client.calls[1]
    assert agent.BETA_FALLBACK not in client.calls[1]['betas'], 'без возможности — и без её беты'
    assert client.calls[1]['context_management'] and client.calls[1]['thinking']['block_binding'], \
        'остальное не тронуто'
    agent.run_turn(client, system_text='S', tool_list=[], history=[], user_content=[text('?')], ctx=ctx_for(env))
    assert 'fallbacks' not in client.calls[2], 'отвергнутое больше не шлём'
    with pytest.raises(anthropic.BadRequestError):
        agent.run_turn(client, system_text='S', tool_list=[], history=[], user_content=[text('?')],
                       ctx=ctx_for(env))
    assert len(client.calls) == 4, 'чужая ошибка 400 — наверх без повтора'


def test_daily_budget_stops_before_request(env):
    env.monkeypatch.setattr(settings, 'DAILY_BUDGET_USD', 0.01)
    store.add_usage('claude-opus-5-5', {'input_tokens': 10_000}, 0.04)
    client = FakeClient()
    with pytest.raises(agent.BudgetExceeded, match='исчерпан'):
        agent.run_turn(client, system_text='S', tool_list=[], history=[], user_content=[text('?')], ctx=ctx_for(env))
    assert client.calls == []


def test_ask_agent_runs_role_agent(env):
    seen = {}

    def agent_answer(params):
        seen['system'] = params['system'][0]['text']
        seen['tools'] = [t['name'] for t in params['tools']]
        seen['effort'] = params['output_config']['effort']
        return resp(text('Отчёт: ЗП за сентябрь сходится.'))

    client = FakeClient(
        resp(use(tools.ASK_AGENT, {'agent': 'payroll', 'task': 'Проверь ЗП за сентябрь 2026 по всем барам'}),
             stop='tool_use'),
        agent_answer,
        resp(text('Агент проверил: всё сходится.')),
    )
    ctx = ctx_for(env)
    ctx.run_agent = lambda name, task: agent.run_agent(client, name, task, parent=ctx, header='[шапка]')
    result = agent.run_turn(client, system_text='S', tool_list=[], history=[], user_content=[text('?')], ctx=ctx)
    assert result.text == 'Агент проверил: всё сходится.'
    assert '# Ты — агент «Зарплаты и график»' in seen['system'] and seen['effort'] == settings.AGENT_EFFORT
    assert tools.ASK_AGENT not in seen['tools'] and not any(t.startswith('stocks_') for t in seen['tools'])
    assert client.calls[1]['messages'][0]['content'][0]['text'].startswith('[шапка]\nПроверь ЗП')
    report = client.calls[2]['messages'][-1]['content'][0]
    assert report['content'][0]['text'] == 'Отчёт: ЗП за сентябрь сходится.'
    assert audit.recent(limit=1)[0]['tool'] == 'ask_agent:payroll'


# ------------------------------------------------------------------ claude.py

def test_describe_error_and_cost():
    import anthropic
    import httpx2
    req = httpx2.Request('POST', 'https://api.anthropic.com/v1/messages')

    def status(cls, code, message):
        return cls(message, response=httpx2.Response(code, request=req), body=None)

    assert claude.describe_error(status(anthropic.AuthenticationError, 401, 'bad key'))[0] == 'auth'
    kind, message = claude.describe_error(status(anthropic.PermissionDeniedError, 403, 'Request not allowed'))
    assert kind == 'denied' and 'прокси' in message
    assert claude.describe_error(status(anthropic.RateLimitError, 429, 'slow'))[0] == 'rate'
    assert claude.describe_error(status(anthropic.InternalServerError, 529, 'Overloaded'))[0] == 'overloaded'
    assert claude.describe_error(status(anthropic.BadRequestError, 400,
                                        'Your credit balance is too low'))[0] == 'billing'
    assert claude.describe_error(anthropic.APIConnectionError(request=req))[0] == 'offline'
    assert claude.describe_error(ValueError('x'))[0] == 'other'
    proxy = 'http://user:proxy-secret@proxy.example:3128'
    kind, message = claude.describe_error(ValueError(f'boom {KEY} via {proxy} pw proxy-secret'),
                                          secrets=(KEY, proxy, ''))
    assert kind == 'other' and KEY not in message and 'proxy-secret' not in message and proxy not in message
    assert message == 'ValueError: boom *** via *** pw ***'
    usage = {'input_tokens': 1_000_000, 'output_tokens': 100_000, 'cache_read_input_tokens': 2_000_000,
             'cache_creation_input_tokens': 0}
    assert claude.cost_usd('claude-opus-5-5', usage) == pytest.approx(4.0 + 2.0 + 0.4)
    assert claude.cost_usd('claude-opus-5-5-20261001', usage) == pytest.approx(4.0 + 2.0 + 0.4), \
        'claude-opus-5-5 не путается с claude-opus-5'
    assert claude.cost_usd('claude-opus-5', usage) == pytest.approx(5.0 + 2.5 + 1.0), 'запасная модель — своя цена'
    assert claude.cost_usd('claude-unknown', usage) == claude.cost_usd(settings.MODEL, usage)


# ------------------------------------------------------------------ оформление

def test_markdown_to_telegram_html():
    md = ('# Итог\n**Выручка** выросла на *5%* — см. [дашборд](https://beerkultura.ru/dashboard).\n'
          '- первый <пункт>\n* второй & `код<1>`\n\n```\nБар     Сумма\nВО        10\n```\n'
          '| Бар | Литры |\n|---|---|\n| ВО | 12 |')
    out = formatting.to_html(md)
    assert '<b>Итог</b>' in out and '<b>Выручка</b>' in out and '<i>5%</i>' in out
    assert '<a href="https://beerkultura.ru/dashboard">дашборд</a>' in out
    assert '• первый &lt;пункт&gt;' in out and '• второй &amp; <code>код&lt;1&gt;</code>' in out
    assert '<pre>Бар     Сумма\nВО        10</pre>' in out
    assert '<pre>| Бар | Литры |\n| ВО | 12 |</pre>' in out, 'таблица без строки разделителя — моноширинно'
    assert formatting.to_html('2 * 3 * 4 и snake_case_name') == '2 * 3 * 4 и snake_case_name'


def test_long_answer_is_split_by_paragraphs_and_code_kept_whole():
    paragraph = 'Абзац. ' * 60
    code = '```\n' + '\n'.join(f'строка {i:03d}' for i in range(40)) + '\n```'
    parts = formatting.split('\n\n'.join([paragraph] * 6 + [code]), limit=1000)
    assert all(len(p) <= 1000 for p in parts)
    assert any(p.startswith('```') and p.endswith('```') for p in parts), 'блок кода не разорван'
    long_code = '```\n' + '\n'.join(f'строка {i:04d}' for i in range(400)) + '\n```'
    pieces = formatting.split(long_code, limit=500)
    assert len(pieces) > 1 and all(p.startswith('```') and p.endswith('```') and len(p) <= 500 for p in pieces)
    assert formatting.split('') == [] and formatting.split('коротко') == ['коротко']


# ------------------------------------------------------------------ доступ

def test_link_code_is_one_time_and_only_for_admins(env):
    owner, bob = env.accounts.owner, env.accounts.bob
    link = access.create_code(owner['id'], owner['login'])
    assert link['url'] == f'https://t.me/MCPkulturabot?start={link["code"]}' and len(link['code']) == 16
    assert access.link_by_code(link['code'], OWNER_TG, 'Анна')['ok'] is True
    assert access.link_by_code(link['code'], '777')['ok'] is False, 'код одноразовый'
    assert access.actor_for(OWNER_TG)['login'] == 'owner' and access.actor_for('777') is None
    bob_code = access.create_code(bob['id'], bob['login'])['code']
    assert access.link_by_code(bob_code, '888')['ok'] is False, 'не администратор не подключится'
    old = access.create_code(owner['id'], owner['login'])['code']
    with db.write() as conn:
        conn.execute('UPDATE bot_link_codes SET expires_ts = 1 WHERE code = ?', (old,))
    assert access.link_by_code(old, '999')['ok'] is False, 'просроченный код не работает'
    principal = access.principal_for(access.actor_for(OWNER_TG))
    assert principal.token_id == f'tg_{OWNER_TG}' and principal.mode == 'full' and principal.allows(None)
    assert principal.user_id == owner['id'] and principal.client_name == 'Бот @MCPkulturabot'


def test_actor_lost_when_admin_flag_removed(env):
    mgr = env.accounts.mgr
    second = mgr.get_by_id(mgr.create_user('ann', 'Анна', 'annpass12', is_admin=True))
    store.save_link('321', second['id'], 'ann')
    assert access.actor_for('321')['login'] == 'ann'
    mgr.set_admin(second['id'], False)
    assert access.actor_for('321') is None, 'права проверяются на каждом сообщении'


def test_refusal_at_most_hourly():
    assert access.refusal_due('42', now=1000.0) is True
    assert access.refusal_due('42', now=1000.0 + 600) is False
    assert access.refusal_due('42', now=1000.0 + access.REFUSAL_EVERY_S + 1) is True


# ------------------------------------------------------------------ сообщения

def message(text_value, chat_id=OWNER_TG, user_id=OWNER_TG, chat_type='private', **extra):
    msg = {'message_id': 10, 'chat': {'id': int(chat_id), 'type': chat_type},
           'from': {'id': int(user_id), 'first_name': 'Анна'}, 'text': text_value}
    msg.update(extra)
    return {'update_id': 1, 'message': msg}


@pytest.fixture
def bot(env):
    tg = FakeTelegram()
    svc = service.Service(env.app, io_factory=lambda token: tg)
    assert svc.ready() is True
    svc.enqueue = lambda chat_id, job: svc.answer(chat_id, job)        # без потоков: ответ сразу
    client = FakeClient()
    env.monkeypatch.setattr(claude, 'client_for', lambda key, proxy: client)
    return SimpleNamespace(svc=svc, tg=tg, client=client, env=env)


def test_stranger_gets_one_refusal_and_costs_nothing(bot):
    access._refused_at.clear()
    bot.svc.handle_update(message('покажи зарплаты', user_id='4040', chat_id='4040'))
    bot.svc.handle_update(message('ещё раз', user_id='4040', chat_id='4040'))
    assert len(bot.tg.sent) == 1 and 'закрытый бот' in bot.tg.sent[0][1] and bot.client.calls == []


def test_start_with_code_links_and_question_is_answered(bot):
    code = access.create_code(bot.env.accounts.owner['id'], 'owner')['code']
    bot.svc.handle_update(message(f'/start {code}'))
    assert 'Готово' in bot.tg.sent[-1][1]
    bot.client.script += [resp(thinking(), text('Выручка за вчера — **412 300 ₽**.'))]
    bot.svc.handle_update(message('какая выручка вчера?'))
    assert bot.tg.sent[-1] == (OWNER_TG, 'Выручка за вчера — **412 300 ₽**.', None)
    request = bot.client.calls[-1]
    first_text = request['messages'][0]['content'][0]['text']
    assert first_text.startswith('[') and 'пишет Владелец (owner)]\nкакая выручка вчера?' in first_text
    assert request['system'][0]['text'] == config.bot_system_text()
    dialog = store.get_dialog(OWNER_TG)
    assert dialog['turns'] == 1 and len(dialog['messages']) == 2
    bot.client.script += [resp(text('А позавчера — 398 000 ₽.'))]
    bot.svc.handle_update(message('а позавчера?'))
    assert len(bot.client.calls[-1]['messages']) == 3, 'диалог продолжается'
    assert store.recent_jobs()[0]['status'] == 'done'


def test_new_dialog_after_pause_and_after_instructions_change(bot):
    store.save_link(OWNER_TG, bot.env.accounts.owner['id'], 'owner')
    bot.client.script += [resp(text('Первый ответ'))]
    bot.svc.handle_update(message('вопрос'))
    with db.write() as conn:
        conn.execute('UPDATE bot_dialogs SET last_ts = ?', (time.time() - settings.DIALOG_IDLE_MINUTES * 60 - 5,))
    bot.client.script += [resp(text('Ответ после паузы'))]
    bot.svc.handle_update(message('вопрос через три часа'))
    assert bot.tg.sent[-1][1].startswith('*' + settings.NEW_DIALOG_NOTICE + '*')
    assert len(bot.client.calls[-1]['messages']) == 1
    with db.write() as conn:
        conn.execute("UPDATE bot_dialogs SET fingerprint = 'old'")
    bot.client.script += [resp(text('Ответ'))]
    bot.svc.handle_update(message('ещё'))
    assert service.FINGERPRINT_NOTICE in bot.tg.sent[-1][1] and len(bot.client.calls[-1]['messages']) == 1
    bot.svc.handle_update(message('/new'))
    assert store.get_dialog(OWNER_TG) is None and bot.tg.sent[-1][1] == 'Начинаю новый диалог.'


def test_group_only_when_addressed(bot):
    store.save_link(OWNER_TG, bot.env.accounts.owner['id'], 'owner')
    bot.svc.handle_update(message('просто болтаем', chat_id='-100500', chat_type='supergroup'))
    assert bot.client.calls == [] and bot.tg.sent == []
    bot.client.script += [resp(text('Отвечаю в группе'))]
    bot.svc.handle_update(message('@MCPkulturabot сколько кег?', chat_id='-100500', chat_type='supergroup'))
    assert bot.tg.sent[-1] == ('-100500', 'Отвечаю в группе', 10), 'в группе — ответом на сообщение'
    assert bot.client.calls[-1]['messages'][0]['content'][0]['text'].endswith('\nсколько кег?')
    bot.client.script += [resp(text('И на ответ тоже'))]
    bot.svc.handle_update(message('а вчера?', chat_id='-100500', chat_type='supergroup',
                                  reply_to_message={'from': {'id': 999}}))
    assert bot.tg.sent[-1][1] == 'И на ответ тоже'
    bot.svc.bot_id = None                      # getMe при запуске не ответил — узнаём бота по имени
    bot.client.script += [resp(text('По имени'))]
    bot.svc.handle_update(message('а позавчера?', chat_id='-100500', chat_type='supergroup',
                                  reply_to_message={'from': {'id': 999, 'is_bot': True, 'username': 'MCPkulturabot'}}))
    assert bot.tg.sent[-1][1] == 'По имени'
    sent = len(bot.tg.sent)
    bot.svc.handle_update(message('а ты?', chat_id='-100500', chat_type='supergroup',
                                  reply_to_message={'from': {'id': 5, 'is_bot': True, 'username': 'OtherBot'}}))
    assert len(bot.tg.sent) == sent, 'ответ другому боту — не к нам'


def test_anthropic_errors_become_plain_text(bot):
    import anthropic
    import httpx2
    store.save_link(OWNER_TG, bot.env.accounts.owner['id'], 'owner')
    req = httpx2.Request('POST', 'https://api.anthropic.com/v1/messages')
    bot.client.script += [anthropic.PermissionDeniedError('Request not allowed',
                                                          response=httpx2.Response(403, request=req), body=None)]
    bot.svc.handle_update(message('вопрос'))
    assert 'Anthropic отказал серверу (403)' in bot.tg.sent[-1][1] and 'прокси' in bot.tg.sent[-1][1]
    assert store.get_status()['state'] == 'error'
    assert store.recent_jobs()[0]['status'] == 'error'
    bot.client.script += [anthropic.BadRequestError('messages.1: bad', response=httpx2.Response(400, request=req),
                                                    body=None)]
    store.save_dialog(OWNER_TG, 'fp', '2026-10-19T10:00:00+03:00', [], 1)
    bot.svc.handle_update(message('вопрос 2'))
    assert 'Диалог начат заново' in bot.tg.sent[-1][1] and store.get_dialog(OWNER_TG) is None


def test_question_during_worker_shutdown_is_not_lost_silently(bot):
    store.save_link(OWNER_TG, bot.env.accounts.owner['id'], 'owner')

    def closed(*args, **kwargs):
        raise RuntimeError('cannot schedule new futures after interpreter shutdown')

    del bot.svc.enqueue                        # настоящая очередь, а не ответ сразу
    bot.svc.executor.submit = closed
    bot.svc.handle_update(message('сколько кег?'))
    assert bot.tg.sent[-1] == (OWNER_TG, service.RESTARTING_TEXT, None)
    assert OWNER_TG not in bot.svc.busy and OWNER_TG not in bot.svc.queues, 'чат не завис «занятым»'


def test_photo_is_passed_to_model(bot):
    store.save_link(OWNER_TG, bot.env.accounts.owner['id'], 'owner')
    bot.client.script += [resp(text('На фото накладная'))]
    update = message('', photo=[{'file_id': 'small', 'file_size': 10}, {'file_id': 'big', 'file_size': 99}])
    update['message'].pop('text')
    update['message']['caption'] = 'что это?'
    bot.svc.handle_update(update)
    content = bot.client.calls[-1]['messages'][0]['content']
    assert content[1]['type'] == 'image' and content[1]['source']['media_type'] == 'image/jpeg'
    assert content[0]['text'].endswith('\nчто это?')
    asked = []
    bot.tg.download = lambda file_id, max_bytes: asked.append((file_id, max_bytes))   # не скачалось
    bot.client.script += [resp(text('Без файла'))]
    update = message('вот счёт', document={'file_id': 'pdf1', 'mime_type': 'application/pdf'})
    bot.svc.handle_update(update)
    assert asked == [('pdf1', settings.INPUT_FILE_MAX_BYTES)]
    assert 'PDF — до 10 МБ' in bot.tg.sent[-2][1] and bot.tg.sent[-1][1] == 'Без файла'
    assert service.Service._limit('image') == service.IMAGE_MAX_BYTES, 'картинка — в пределе Claude API'


def test_waiting_states_and_conflict(env):
    tg = FakeTelegram()
    svc = service.Service(env.app, io_factory=lambda token: tg)
    env.monkeypatch.delenv(credentials.ANTHROPIC_ENV)
    assert svc.ready() is False and store.get_status()['state'] == 'waiting'
    assert 'Anthropic' in store.get_status()['detail']
    env.monkeypatch.setenv(credentials.ANTHROPIC_ENV, KEY)
    credentials.save(paused_value=True)
    assert svc.ready() is False and store.get_status()['state'] == 'paused'
    credentials.save(paused_value=False)
    assert svc.ready() is True and tg.webhook_deleted == 1
    env.monkeypatch.setattr(service, 'CONFLICT_RETRY_S', 0)
    tg.updates.append({'ok': False, 'error_code': 409, 'description': 'Conflict: terminated by other getUpdates'})
    svc.poll_once()
    assert store.get_status()['state'] == 'conflict'
    tg.updates.append({'ok': False, 'error_code': 409, 'description': "can't use getUpdates while webhook is active"})
    svc.poll_once()
    assert tg.webhook_deleted == 2


def test_interrupted_answers_are_reported_once(env):
    job = store.start_job('777', '555')
    store.start_job('777', '555')
    tg = FakeTelegram()
    svc = service.Service(env.app, io_factory=lambda token: tg)
    assert svc.ready() is True
    assert [s[0] for s in tg.sent] == ['777'], 'один раз на чат'
    assert all(j['status'] == 'interrupted' for j in store.recent_jobs()) and job


def test_start_failure_does_not_break_the_site(env, tmp_path):
    import kultura_bot
    env.monkeypatch.setenv('KULTURA_BOT', '1')
    env.monkeypatch.setattr(service, '_started', False)
    env.monkeypatch.setattr(service, 'LOCK_PATH', str(tmp_path / 'bot.lock'))

    def broken(app, io_factory=None):
        raise RuntimeError('нет базы')

    env.monkeypatch.setattr(service, 'Service', broken)
    kultura_bot.start(env.app)                 # не бросает: сайт поднимается дальше
    assert service._started is False
    import portalocker
    with open(tmp_path / 'bot.lock', 'a') as handle:
        portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)   # лок отпущен


def test_status_view_for_page(env):
    store.set_status('running', 'бот слушает Telegram')
    view = service.status_view()
    assert view['status']['state'] == 'running' and view['status']['stale'] is False
    assert view['model'] == settings.MODEL and [a['name'] for a in view['agents']] == ['analyst', 'content',
                                                                                       'payroll']
    assert 'today' in view['usage'] and view['links'] == []
