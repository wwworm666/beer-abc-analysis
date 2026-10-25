"""
Сервер бота @MCPkulturabot (kultura_bot/engine/): инструкции, каталог инструментов с сайта,
разговор с Claude, оформление, Telegram, очередь и ответы. Сайт, Claude и Telegram
подменены — сеть не нужна. API бота на сайте и сквозная связь «сервер бота -> сайт» —
tests/test_kultura_bot_site.py.

Что проверяется:
- инструкции: все agents/*.md разбираются, ошибки заголовка называют файл, разделы
  совпадают с разделами сайта; сервер бота не импортирует код сайта;
- каталог: правила и инструменты — с сайта по MCP; поиск первым, видимые сразу — без
  defer_loading, остальные отложены, скрытых нет, ask_agent только у бота; агенту —
  инструменты его разделов (объединение коннекторов) и правила разделов
  (common_instructions); порядок и отпечаток неизменны, новые инструменты сайта — новый
  отпечаток;
- разговор: параметры запроса (модель, усилие, кэш, context editing, fallbacks,
  block_binding); отвергнутая необязательная возможность выключается, запрос повторяется;
  история только дописывается; инструмент вызывается на сайте; график — в чат разговора;
  сайт не ответил — ошибка инструмента; неизвестный инструмент; pause_turn; предел шагов;
  шаг, оборванный посреди вызова инструмента; дневной предел; ask_agent;
- ошибки и цена: describe_error, scrub, цена (в том числе запасной модели);
- оформление и Telegram: Markdown -> HTML, нарезка, однострочный и длинный код, 429 и
  «слишком длинное»;
- сервер: настройки с сайта (нет токена, нет ключа, пауза, ключ не принят, ключ сервера
  отозван), незнакомцу «закрытый бот» раз в час, /start <код>, группы, /new в очереди,
  вопросы из очереди переживают перезапуск, права ещё раз перед ответом, сайт не ответил,
  ошибка Claude держится в отчёте, расход уходит в отчёт, фото и PDF, неподдерживаемые
  файлы, остановка сервера, оборванные ответы, 409, запуск без ключа.

Запуск: `py -3 -m pytest tests/test_kultura_bot.py`.
"""
import copy
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from kultura_bot import settings  # noqa: E402
from kultura_bot.engine import agent, claude, config, formatting, service, tools  # noqa: E402
from kultura_bot.engine.site import SiteError  # noqa: E402
from kultura_bot.engine.store import Store  # noqa: E402

TOKEN = '1234567890:' + 'T' * 35
KEY = 'sk-ant-api03-' + 'k' * 40
ENGINE_KEY = 'kmcp_' + 'e' * 40
OWNER_TG = '555'
OWNER = {'tg_user_id': OWNER_TG, 'user_id': 1, 'login': 'owner', 'display_name': 'Владелец'}
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


def site_tool(name, description='инструмент'):
    return {'name': name, 'title': name, 'description': description,
            'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
            'annotations': {}}


DOMAIN_TOOLS = {
    'common': ['common_bars_reference', 'common_chart_send', 'common_docs_read', 'common_instructions',
               'common_notify_owner', 'common_report_send', 'common_whoami'],
    'content': ['content_plan_get', 'content_reviews_list'],
    'stocks': ['stocks_orders_board', 'stocks_taps_list'],
    'analytics': ['analytics_dashboard', 'analytics_sales'],
    'staff': ['staff_salary_month', 'staff_schedule_get'],
}


class FakeSite:
    """Сайт для сервера бота: API бота и MCP — в памяти; каждый вызов запоминается."""

    def __init__(self):
        self.key = ENGINE_KEY
        self.cfg = {'telegram': {'token': TOKEN, 'username': 'MCPkulturabot'}, 'anthropic_key': KEY,
                    'paused': False}
        self.links = {OWNER_TG: dict(OWNER)}
        self.codes = {}
        self.reports = []
        self.calls = []                     # (name, arguments)
        self.down = False
        self.config_error = None
        self.extra_tools = []
        self.results = {}                   # имя -> {'content', 'isError'}
        self.notes = []                     # (chat_id, text) — записки «Как считается»
        self.note_error = None

    def _check(self):
        if self.down:
            raise SiteError('offline', 'Сайт https://beerkultura.ru не отвечает (ConnectionError).')

    def config(self):
        if self.config_error is not None:
            raise self.config_error
        self._check()
        return copy.deepcopy(self.cfg)

    def link(self, code, tg_user_id, tg_name):
        self._check()
        actor = self.codes.pop(code, None)
        if actor is None:
            return {'ok': False, 'text': 'Ссылка не подошла'}
        self.links[str(tg_user_id)] = dict(actor, tg_user_id=str(tg_user_id))
        return {'ok': True, 'text': f'Готово: вы подключены как {actor["display_name"]}.'}

    def actor(self, tg_user_id):
        self._check()
        return copy.deepcopy(self.links.get(str(tg_user_id)))

    def report(self, payload):
        self._check()
        self.reports.append(copy.deepcopy(payload))
        return {'ok': True}

    def note(self, chat_id, text_value, title=''):
        self._check()
        if self.note_error is not None:
            raise self.note_error
        self.notes.append((str(chat_id), text_value))
        return 'rep_' + f'{len(self.notes):022x}'

    def instructions(self, connector='/mcp'):
        self._check()
        return f'Правила коннектора {connector}.'

    def tools(self, connector='/mcp'):
        self._check()
        domain = connector.rsplit('/', 1)[-1]
        names = list(DOMAIN_TOOLS['common'])
        if domain == 'mcp':
            for key, items in DOMAIN_TOOLS.items():
                if key != 'common':
                    names += items
        else:
            names += DOMAIN_TOOLS[domain]
        return [site_tool(n) for n in names] + list(self.extra_tools)

    def call_tool(self, name, arguments):
        self._check()
        self.calls.append((name, copy.deepcopy(arguments)))
        if name == 'common_instructions':
            return {'content': [text(f'# Раздел ({arguments["domain"]})\n\nПравила {arguments["domain"]}.')],
                    'isError': False}
        if name == tools.CHART_TOOL:
            return {'content': [text(json.dumps({'chart_id': 'X' * 22, 'chat_id': arguments.get('chat_id')}))],
                    'isError': False}
        if name == tools.REPORT_TOOL:
            return {'content': [text(json.dumps({'report_id': 'rep_' + 'a' * 22, 'chat_id': arguments.get('chat_id'),
                                                 'message_id': 9}))], 'isError': False}
        return copy.deepcopy(self.results.get(name, {'content': [text(json.dumps({'ok': name}))],
                                                     'isError': False}))


class FakeClient:
    """client.beta.messages.stream: ответы по сценарию; каждый запрос запоминается копией.

    Бот шлёт запросы потоком (agent.send): with ...stream(**params) as s: s.get_final_message().
    with_options(...) запоминается в options (быстрый запрос — max_retries=0)."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []
        self.options = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def with_options(self, **options):
        self.options.append(options)
        return self

    def _stream(self, **params):
        self.calls.append(copy.deepcopy(params))
        item = self.script.pop(0)
        return _FakeStream(item(params) if callable(item) and not isinstance(item, Exception) else item)


class _FakeStream:
    def __init__(self, item):
        self.item = item

    def __enter__(self):
        if isinstance(self.item, Exception):          # ошибка до потока (HTTP 4xx/5xx)
            raise self.item
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if isinstance(self.item, BaseException):
            raise self.item
        return self.item


class FakeTelegram:
    def __init__(self, token=TOKEN):
        self.token = token
        self.sent = []          # (chat_id, text, reply_to)
        self.markups = []       # reply_markup каждого send_markdown (None — без кнопок)
        self.updates = []
        self.webhook_deleted = 0
        self.typing_count = 0
        self.files = {}

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

    def send_markdown(self, chat_id, markdown, reply_to=None, reply_markup=None):
        self.sent.append((str(chat_id), markdown, reply_to))
        self.markups.append(reply_markup)
        return [1]

    def download(self, file_id, max_bytes):
        return self.files.get(file_id, b'jpegbytes')


def api_error(cls, code, message='ошибка', body=None):
    import httpx2
    req = httpx2.Request('POST', 'https://api.anthropic.com/v1/messages')
    return cls(message, response=httpx2.Response(code, request=req), body=body)


def stream_error(kind, message='ошибка'):
    """Ошибка посреди потока: событие error при HTTP 200 (так её отдаёт SDK)."""
    import anthropic
    body = {'type': 'error', 'error': {'type': kind, 'message': message}}
    return api_error(anthropic.APIStatusError, 200, str(body), body=body)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'DAILY_BUDGET_USD', 15.0)
    monkeypatch.setattr(settings, 'FAST_MODE', True)
    monkeypatch.setattr(settings, 'SHOW_COST', False)          # строку цены проверяет свой тест
    monkeypatch.setattr(settings, 'QUESTION_BUDGET_USD', 2.0)
    monkeypatch.setattr(agent, '_disabled', set())
    monkeypatch.setattr(agent, '_fast_paused_until', 0.0)
    site = FakeSite()
    store = Store(str(tmp_path / 'bot.db'))
    yield SimpleNamespace(site=site, store=store, monkeypatch=monkeypatch, tmp_path=tmp_path)
    store.close()


def ctx_for(env, chat_id=OWNER_TG, allowed=None):
    names = allowed if allowed is not None else frozenset(n for v in DOMAIN_TOOLS.values() for n in v)
    return tools.ToolContext(site=env.site, chat_id=chat_id, allowed=frozenset(names))


def turn(env, client, ctx=None, **kwargs):
    return agent.run_turn(client, system_text=kwargs.pop('system_text', 'S'), tool_list=kwargs.pop('tool_list', []),
                          history=kwargs.pop('history', []), user_content=kwargs.pop('user_content', [text('?')]),
                          ctx=ctx or ctx_for(env), store=env.store, **kwargs)


# ------------------------------------------------------------------ инструкции

def test_agents_and_prompts_load():
    agents = config.load_agents()
    assert set(agents) == {'analyst', 'payroll', 'content'}
    for name, item in agents.items():
        assert item.title and item.description and item.instructions
        assert set(item.domains) <= set(config.DOMAINS)
    assert config.bot_prompt().startswith('Ты — помощник владельца') and config.agent_prompt()
    from core.mcp.spec import DOMAINS
    assert set(config.DOMAINS) == set(DOMAINS), 'разделы сервера бота = разделы сайта'
    system = config.bot_system_text('ПРАВИЛА САЙТА')
    assert '# Агенты для поручений (ask_agent)' in system and '- payroll — Зарплаты и график' in system
    assert system.endswith('ПРАВИЛА САЙТА')


@pytest.mark.parametrize('text_value,error', [
    ('name: x', 'начинается со строки «---»'),
    ('---\nname: pp\n', 'не закрыт строкой'),
    ('---\nname: pp\ntitle: T\ndomains: staff\n---\nтекст', 'нет description'),
    ('---\nname: Payroll\ntitle: T\ndomains: staff\ndescription: d\n---\nтекст', 'латиница в нижнем'),
    ('---\nname: pp\ntitle: T\ndomains: kitchen\ndescription: d\n---\nтекст', 'неизвестные: kitchen'),
    ('---\nname: pp\ntitle: T\ndomains: staff\ndescription: d\n---\n', 'нет текста инструкций'),
])
def test_agent_file_errors_name_the_file(text_value, error):
    with pytest.raises(config.ConfigError, match=error) as exc:
        config.parse_agent(text_value, path='kultura_bot/agents/x.md')
    assert 'kultura_bot/agents/x.md' in str(exc.value)


def test_engine_does_not_import_site_code():
    """На сервере бота кода сайта нет: импорт core/flask/routes — ошибка."""
    code = ('import importlib.abc, sys\n'
            'class Block(importlib.abc.MetaPathFinder):\n'
            '    def find_spec(self, name, path, target=None):\n'
            '        if name.split(".")[0] in ("core", "flask", "routes", "pandas", "werkzeug"):\n'
            '            raise ImportError("сервер бота импортирует " + name)\n'
            'sys.meta_path.insert(0, Block())\n'
            'import kultura_bot.__main__\n'
            'from kultura_bot.engine import service, tools, agent, config, site, store, main\n'
            'print(sorted(config.load_agents()))\n')
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "['analyst', 'content', 'payroll']" in out.stdout


# ------------------------------------------------------------------ каталог

def test_catalog_from_site_tools_and_rules(env):
    catalog = tools.load_catalog(env.site)
    bot = catalog.bot
    names = [t['name'] for t in bot.toolset.defs]
    assert names[0] == 'tool_search_tool_regex'
    loaded = [t['name'] for t in bot.toolset.defs if 'defer_loading' not in t and t['name'] != names[0]]
    assert loaded == sorted(settings.ALWAYS_LOADED_TOOLS) + [tools.ASK_AGENT]
    deferred = [t['name'] for t in bot.toolset.defs if t.get('defer_loading')]
    assert deferred == sorted(deferred) and 'staff_salary_month' in deferred
    assert 'common_notify_owner' not in names and 'common_notify_owner' not in bot.toolset.names, 'скрытый'
    assert all(__import__('re').match(TOOL_NAME_RE, n) for n in names)
    assert bot.system.endswith('Правила коннектора /mcp.')

    analyst = catalog.agents['analyst']
    agent_names = {t['name'] for t in analyst.toolset.defs}
    assert tools.ASK_AGENT not in agent_names
    assert {'stocks_taps_list', 'analytics_sales', 'common_whoami'} <= agent_names
    assert not any(n.startswith(('staff_', 'content_')) for n in agent_names), 'только свои разделы'
    assert '# Ты — агент «Аналитик»' in analyst.system
    assert 'Правила stocks.' in analyst.system and 'Правила analytics.' in analyst.system
    assert ('common_instructions', {'domain': 'stocks'}) in env.site.calls

    again = tools.load_catalog(env.site)
    assert again.bot.fingerprint == bot.fingerprint, 'тот же сайт — тот же отпечаток'
    env.site.extra_tools = [site_tool('stocks_new_tool')]
    assert tools.load_catalog(env.site).bot.fingerprint != bot.fingerprint, 'новый инструмент сайта — новый диалог'


# ------------------------------------------------------------------ разговор

def test_turn_calls_site_tool_and_keeps_history_append_only(env):
    client = FakeClient(
        resp(thinking(), use('common_whoami', {}), stop='tool_use'),
        resp(thinking(), text('Сегодня **19 октября**.')),
    )
    history = [{'role': 'user', 'content': [text('[время] привет')]},
               {'role': 'assistant', 'content': [thinking(), text('Здравствуйте')]}]
    frozen = copy.deepcopy(history)
    seen = []
    result = turn(env, client, system_text='СИСТЕМА', tool_list=[tools.SEARCH_TOOL], history=history,
                  user_content=[text('какое сегодня число?')], on_usage=lambda *a: seen.append(a))
    assert result.text == 'Сегодня **19 октября**.' and result.rounds == 1 and result.stop_reason == 'end_turn'
    first, second = client.calls
    assert first['messages'][:2] == frozen and second['messages'][:len(first['messages'])] == first['messages'], \
        'история только дописывается'
    assert first['model'] == settings.MODEL and first['output_config'] == {'effort': settings.EFFORT}
    assert settings.EFFORT == 'xhigh' and settings.AGENT_EFFORT == 'xhigh', 'решение владельца 2026-10-20'
    assert first['max_tokens'] == settings.MAX_TOKENS == 64000 and first['speed'] == 'fast'
    assert client.options == [{'max_retries': 0}] * 2, 'быстрый запрос — без повторов SDK'
    assert first['system'] == [{'type': 'text', 'text': 'СИСТЕМА', 'cache_control': {'type': 'ephemeral'}}]
    assert first['cache_control'] == {'type': 'ephemeral'} and first['fallbacks'] == 'default'
    assert set(first['betas']) == {agent.BETA_CONTEXT, agent.BETA_THINKING_BINDING, agent.BETA_FALLBACK,
                                   agent.BETA_FAST}
    assert first['thinking'] == {'type': 'adaptive', 'block_binding': {'prefix_mismatch_behavior': 'drop_block'}}
    edit = first['context_management']['edits'][0]
    assert edit['type'] == 'clear_tool_uses_20250919' and edit['exclude_tools'] == ['tool_search_tool_regex']
    assert edit['trigger'] == {'type': 'input_tokens', 'value': 300000}
    assert edit['clear_at_least'] == {'type': 'input_tokens', 'value': 150000}, \
        'чистка редкая и крупная: каждая заново пишет разговор в кэш'
    assert 'tool_choice' not in first
    assert env.site.calls == [('common_whoami', {})], 'инструмент исполнил сайт'
    tool_result = second['messages'][-1]['content'][0]
    assert tool_result['type'] == 'tool_result' and tool_result['tool_use_id'] == 'toolu_1'
    assert 'is_error' not in tool_result and json.loads(tool_result['content'][0]['text']) == {'ok': 'common_whoami'}
    one = claude.cost_usd('claude-opus-5-5', {'input_tokens': 1000, 'output_tokens': 200})
    assert result.cost_usd == pytest.approx(2 * one) and env.store.spent_on() == pytest.approx(2 * one)
    assert [s[0] for s in seen] == ['claude-opus-5-5', 'claude-opus-5-5'], 'расход шагов — в отчёт сайту'


def test_chart_goes_to_conversation_chat_and_site_errors_are_tool_errors(env):
    client = FakeClient(resp(use(tools.CHART_TOOL, {'kind': 'rating', 'chat_id': '-100666'}), stop='tool_use'),
                        resp(text('Готово')))
    ctx = ctx_for(env, chat_id='-100500')
    turn(env, client, ctx=ctx)
    assert env.site.calls[-1] == (tools.CHART_TOOL, {'kind': 'rating', 'chat_id': '-100500'}), \
        'chat_id из данных не проходит — только чат разговора'
    assert ctx.charts_sent and ctx.charts_sent[0]['chat_id'] == '-100500'
    unknown = tools.execute(use('stocks_secret', {}), ctx)
    assert unknown['is_error'] and 'Нет инструмента stocks_secret' in unknown['content'][0]['text']
    assert tools.execute({'id': 't', 'name': 'common_whoami', 'input': 'x'}, ctx)['is_error']
    env.site.down = True
    failed = tools.execute(use('common_whoami', {}), ctx)
    assert failed['is_error'] and 'Сайт не выполнил вызов' in failed['content'][0]['text']
    env.site.down = False
    env.site.results['analytics_sales'] = {'content': [text('Ошибка HTTP 400: нет бара')], 'isError': True}
    assert tools.execute(use('analytics_sales', {}), ctx)['is_error'], 'ошибка инструмента сайта — модели'


def test_rejected_optional_feature_is_dropped_and_retried(env):
    import anthropic
    client = FakeClient(api_error(anthropic.BadRequestError, 400, 'fallbacks: Extra inputs are not permitted'),
                        resp(text('Ответ')), resp(text('Второй')),
                        api_error(anthropic.BadRequestError, 400, 'messages.0: что-то другое'))
    result = turn(env, client)
    assert result.text == 'Ответ' and len(client.calls) == 2
    assert 'fallbacks' in client.calls[0] and 'fallbacks' not in client.calls[1]
    assert agent.BETA_FALLBACK not in client.calls[1]['betas'], 'без возможности — и без её беты'
    assert client.calls[1]['context_management'] and client.calls[1]['thinking']['block_binding'], \
        'остальное не тронуто'
    turn(env, client)
    assert 'fallbacks' not in client.calls[2], 'отвергнутое больше не шлём'
    with pytest.raises(anthropic.BadRequestError):
        turn(env, client)
    assert len(client.calls) == 4, 'чужая ошибка 400 — наверх без повтора'


def test_fast_mode_falls_back_to_standard_and_pauses(env):
    import anthropic
    client = FakeClient(api_error(anthropic.RateLimitError, 429, 'Fast mode rate limit exceeded'),
                        resp(text('Ответ')), resp(text('Ещё')), stream_error('overloaded_error', 'Overloaded'),
                        resp(text('Снова')), api_error(anthropic.BadRequestError, 400, 'speed: fast mode is not '
                                                       'available for this organization'), resp(text('Обычно')),
                        api_error(anthropic.BadRequestError, 400, 'messages.0: что-то другое'))
    assert turn(env, client).text == 'Ответ'
    first, second = client.calls
    assert first['speed'] == 'fast' and agent.BETA_FAST in first['betas']
    assert 'speed' not in second and agent.BETA_FAST not in second['betas'], 'тот же шаг — на обычной скорости'
    assert second['messages'] == first['messages'] and second['output_config'] == first['output_config']
    assert client.options == [{'max_retries': 0}], 'быстрый — без повторов SDK, обычный — с ними'
    assert agent.fast_mode_on() is False and agent.fast_mode_on(agent._fast_paused_until) is True, \
        'пауза FAST_COOLDOWN_S'
    turn(env, client)
    assert 'speed' not in client.calls[2], 'на паузе — обычная скорость'
    for expected in ('Снова', 'Обычно'):                  # ошибка посреди потока; отказ в быстром режиме
        env.monkeypatch.setattr(agent, '_fast_paused_until', 0.0)
        before = len(client.calls)
        assert turn(env, client).text == expected
        fast, standard = client.calls[before:]
        assert fast['speed'] == 'fast' and 'speed' not in standard
    env.monkeypatch.setattr(agent, '_fast_paused_until', 0.0)
    with pytest.raises(anthropic.BadRequestError):
        turn(env, client)
    assert agent.fast_mode_on(), 'чужая ошибка 400 — наверх, быстрый режим не на паузе'


def test_fast_mode_off_and_fast_price(env):
    env.monkeypatch.setattr(settings, 'FAST_MODE', False)
    client = FakeClient(resp(text('Ответ')))
    turn(env, client)
    assert 'speed' not in client.calls[0] and agent.BETA_FAST not in client.calls[0]['betas']
    assert client.options == [], 'обычная скорость — с повторами SDK'
    env.monkeypatch.setattr(settings, 'FAST_MODE', True)
    fast = resp(text('Быстро'))
    fast.usage.speed = 'fast'
    result = turn(env, FakeClient(fast))
    usage = {'input_tokens': 1000, 'output_tokens': 200}
    assert result.cost_usd == pytest.approx(2 * claude.cost_usd('claude-opus-5-5', usage)), \
        'шаг в быстром режиме — по двойной цене'


def test_mid_output_fallback_drops_declined_partial(env):
    declined = [text('Начинаю. '), thinking(), use('stocks_taps_list', {}, 'declined'),
                {'type': 'fallback', 'from': {'model': 'claude-opus-5-5'}, 'to': {'model': 'claude-opus-5'}},
                thinking(), use('common_whoami', {}, 'ok')]
    client = FakeClient(resp(*declined, stop='tool_use', model='claude-opus-5'), resp(text('Готово')))
    result = turn(env, client)
    assert result.text == 'Готово'
    assert env.site.calls == [('common_whoami', {})], 'вызов отказавшей модели не исполняется'
    echoed = client.calls[1]['messages'][-2]['content']
    assert [b['type'] for b in echoed] == ['text', 'fallback', 'thinking', 'tool_use']
    assert echoed[-1]['id'] == 'ok' and client.calls[1]['messages'][-1]['content'][0]['tool_use_id'] == 'ok'
    paired = [{'type': 'server_tool_use', 'id': 's1', 'name': 'tool_search_tool_regex', 'input': {}},
              {'type': 'tool_search_tool_result', 'tool_use_id': 's1', 'content': {}},
              {'type': 'server_tool_use', 'id': 's2', 'name': 'tool_search_tool_regex', 'input': {}},
              {'type': 'fallback'}, text('Дальше')]
    assert [b.get('id') or b.get('tool_use_id') or b['type'] for b in agent.after_fallback(paired)] == \
        ['s1', 's1', 'fallback', 'text'], 'парный серверный вызов остаётся, непарный — нет'
    assert agent.after_fallback([{'type': 'fallback'}, text('x')]) == [{'type': 'fallback'}, text('x')]


def test_question_budget_stops_tools_and_is_shared_with_agent(env):
    step = claude.cost_usd('claude-opus-5-5', {'input_tokens': 1000, 'output_tokens': 200})     # $0.008
    env.monkeypatch.setattr(settings, 'QUESTION_BUDGET_USD', 1.5 * step)
    client = FakeClient(resp(use('common_whoami', {}, 't1'), stop='tool_use'),
                        resp(use('common_whoami', {}, 't2'), stop='tool_use'),
                        resp(text('Что успел — то знаю.')))
    spend = agent.Spend()
    ctx = ctx_for(env)
    ctx.spend = spend
    result = turn(env, client, ctx=ctx)
    assert result.text == 'Что успел — то знаю.' and 'question_budget' in result.notes
    assert 'tool_choice' not in client.calls[1], 'первый шаг предел не перешёл'
    last = client.calls[2]['messages'][-1]['content']
    assert client.calls[2]['tool_choice'] == {'type': 'none'}
    assert [b['type'] for b in last] == ['tool_result', 'text'] and 'Предел расхода' in last[1]['text'], \
        'пояснение — в том же сообщении после результатов'
    assert spend.steps == 3 and spend.usd == pytest.approx(3 * step)

    env.monkeypatch.setattr(settings, 'QUESTION_BUDGET_USD', 1.5 * step)
    client = FakeClient(
        resp(use(tools.ASK_AGENT, {'agent': 'payroll', 'task': 'Проверь ЗП за сентябрь 2026 по всем барам'}),
             stop='tool_use'),
        resp(use('staff_salary_month', {}, 'a1'), stop='tool_use'),          # агент: шаг 1
        resp(text('Отчёт: успел посмотреть ЗП.')),                           # агент: шаг 2 — без инструментов
        resp(text('Агент успел посмотреть ЗП.')))                            # бот — без инструментов
    catalog = tools.load_catalog(env.site)
    spend = agent.Spend()
    ctx = ctx_for(env, allowed=catalog.bot.toolset.names)
    ctx.spend = spend
    ctx.run_agent = lambda name, task: agent.run_agent(client, catalog.agents[name], task, parent=ctx,
                                                       store=env.store)
    result = turn(env, client, ctx=ctx)
    assert result.text == 'Агент успел посмотреть ЗП.' and spend.steps == 4
    assert client.calls[2]['tool_choice'] == {'type': 'none'} and client.calls[3]['tool_choice'] == {'type': 'none'}, \
        'предел общий: агент и бот заканчивают без инструментов'


def test_pause_turn_is_resumed_without_new_message(env):
    client = FakeClient(resp(text('…'), stop='pause_turn'), resp(text('Готово')))
    result = turn(env, client)
    assert result.text == 'Готово'
    assert client.calls[1]['messages'][-1]['role'] == 'assistant', 'повтор без нового сообщения человека'


def test_round_limit_forces_final_answer(env):
    env.monkeypatch.setattr(settings, 'MAX_TOOL_ROUNDS', 1)
    client = FakeClient(
        resp(use('common_whoami', {}, 't1'), stop='tool_use'),
        resp(use('common_whoami', {}, 't2'), stop='tool_use'),
        resp(text('Что успел — то знаю.')),
    )
    result = turn(env, client)
    assert 'max_rounds' in result.notes and result.text == 'Что успел — то знаю.'
    assert client.calls[2]['tool_choice'] == {'type': 'none'}
    refusal = client.calls[2]['messages'][-1]['content'][0]
    assert refusal['tool_use_id'] == 't2' and refusal['is_error'] is True


def test_max_tokens_mid_tool_call_keeps_history_valid(env):
    client = FakeClient(
        resp(thinking(), use('common_whoami', {}, 'cut'), stop='max_tokens'),
        resp(text('Ответ без инструмента.')),
    )
    result = turn(env, client)
    assert result.text == 'Ответ без инструмента.' and 'max_tokens_tool' in result.notes
    assert 'max_tokens' not in result.notes, 'итоговый ответ не помечен обрезанным'
    closing = client.calls[1]['messages'][-1]
    assert closing['role'] == 'user' and closing['content'][0]['tool_use_id'] == 'cut'
    assert closing['content'][0]['is_error'] is True and client.calls[1]['tool_choice'] == {'type': 'none'}
    assert env.site.calls == [], 'обрезанный вызов не исполняется'
    assert [m['role'] for m in result.messages] == ['user', 'assistant', 'user', 'assistant']


def test_daily_budget_stops_before_request(env):
    env.monkeypatch.setattr(settings, 'DAILY_BUDGET_USD', 0.01)
    env.store.add_usage('claude-opus-5-5', {'input_tokens': 10_000}, 0.04)
    client = FakeClient()
    with pytest.raises(agent.BudgetExceeded, match='исчерпан'):
        turn(env, client)
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
    catalog = tools.load_catalog(env.site)
    ctx = ctx_for(env, allowed=catalog.bot.toolset.names)
    ctx.run_agent = lambda name, task: agent.run_agent(client, catalog.agents[name], task, parent=ctx,
                                                       store=env.store, header='[шапка]')
    result = turn(env, client, ctx=ctx)
    assert result.text == 'Агент проверил: всё сходится.'
    assert '# Ты — агент «Зарплаты и график»' in seen['system'] and seen['effort'] == settings.AGENT_EFFORT
    assert tools.ASK_AGENT not in seen['tools'] and not any(t.startswith('stocks_') for t in seen['tools'])
    assert client.calls[1]['messages'][0]['content'][0]['text'].startswith('[шапка]\nПроверь ЗП')
    report = client.calls[2]['messages'][-1]['content'][0]
    assert report['content'][0]['text'] == 'Отчёт: ЗП за сентябрь сходится.'
    agent_ctx = tools.ToolContext(site=env.site, chat_id=OWNER_TG, allowed=frozenset(), is_agent=True,
                                  run_agent=lambda n, t: 'x')
    assert tools.execute(use(tools.ASK_AGENT, {'agent': 'payroll', 'task': 'проверь зарплату'}), agent_ctx)['is_error']


# ------------------------------------------------------------------ claude.py

def test_describe_error_scrub_and_cost():
    import anthropic
    import httpx2
    assert claude.describe_error(api_error(anthropic.AuthenticationError, 401, 'bad key'))[0] == 'auth'
    kind, message = claude.describe_error(api_error(anthropic.PermissionDeniedError, 403, 'no access'))
    assert kind == 'denied' and 'проверьте ключ' in message and 'прокси' not in message.lower()
    assert claude.describe_error(api_error(anthropic.RateLimitError, 429, 'slow'))[0] == 'rate'
    assert claude.describe_error(api_error(anthropic.InternalServerError, 529, 'Overloaded'))[0] == 'overloaded'
    assert claude.describe_error(api_error(anthropic.BadRequestError, 400,
                                           'Your credit balance is too low'))[0] == 'billing'
    assert claude.describe_error(stream_error('overloaded_error', 'Overloaded'))[0] == 'overloaded', \
        'ошибка посреди потока (HTTP 200) — по её типу'
    assert claude.describe_error(stream_error('api_error', 'Internal'))[0] == 'server', 'а не «битый диалог»'
    assert claude.describe_error(stream_error('invalid_request_error', 'bad'))[0] == 'bad_request'
    req = httpx2.Request('POST', 'https://api.anthropic.com/v1/messages')
    assert claude.describe_error(anthropic.APIConnectionError(request=req))[0] == 'offline'
    kind, message = claude.describe_error(ValueError(f'boom {KEY} {ENGINE_KEY} {TOKEN}'), secrets=(KEY, ENGINE_KEY, TOKEN, ''))
    assert kind == 'other' and message == 'ValueError: boom *** *** ***'
    usage = {'input_tokens': 1_000_000, 'output_tokens': 100_000, 'cache_read_input_tokens': 2_000_000,
             'cache_creation_input_tokens': 0}
    assert claude.cost_usd('claude-opus-5-5', usage) == pytest.approx(4.0 + 2.0 + 0.4)
    assert claude.cost_usd('claude-opus-5-5-20261001', usage) == pytest.approx(4.0 + 2.0 + 0.4)
    assert claude.cost_usd('claude-opus-5', usage) == pytest.approx(5.0 + 2.5 + 1.0), 'запасная модель — своя цена'
    assert claude.cost_usd('claude-unknown', usage) == claude.cost_usd(settings.MODEL, usage)
    assert claude.cost_usd('claude-opus-5-5', usage, speed='fast') == pytest.approx(2 * (4.0 + 2.0 + 0.4)), \
        'быстрый режим: $8 / $40, кэш — поверх'
    assert claude.cost_usd('claude-opus-5', usage, speed='fast') == pytest.approx(2 * (5.0 + 2.5 + 1.0))
    assert claude.cost_usd('claude-opus-5-5', usage, speed='standard') == claude.cost_usd('claude-opus-5-5', usage)


# ------------------------------------------------------------------ оформление и Telegram

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


def test_single_line_fence_and_very_long_code_line():
    assert formatting.to_html('Команда ```ls -la``` выводит') == 'Команда <pre>ls -la</pre> выводит'
    assert formatting.plain('Команда ```ls -la``` выводит') == 'Команда ls -la выводит'
    parts = formatting.split('Вот JSON:\n\n```json\n' + 'x' * 5000 + '\n```')
    assert all(len(formatting.to_html(p)) <= formatting.TELEGRAM_MAX for p in parts)
    assert ''.join(formatting.to_html(p) for p in parts).count('x') == 5000, 'длинная строка не потерялась'


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


def test_telegram_waits_on_429_and_sends_too_long_as_plain_chunks(monkeypatch):
    from kultura_bot.engine import telegram_io
    calls = []
    total = []

    class IO(telegram_io.TelegramIO):
        def call(self, method, payload=None, timeout=8):
            calls.append(dict(payload or {}))
            total.append(1)
            if len(total) == 1:                # самый первый запрос — «подождите 3 с»
                return {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 3}}
            return {'ok': True, 'result': {'message_id': len(calls)}}

    slept = []
    monkeypatch.setattr(telegram_io.time, 'sleep', slept.append)
    io = IO('t')
    assert io.send_html('1', 'привет') == 2 and slept == [3], '429 — подождать и повторить'
    calls.clear()
    big = 'я' * 5000
    assert io.send_html('1', big, fallback_text=big, reply_to=7) == 1
    assert [len(c['text']) for c in calls] == [4096, 904], 'длиннее предела — простым текстом, кусками'
    assert all('parse_mode' not in c for c in calls)
    assert 'reply_parameters' in calls[0] and 'reply_parameters' not in calls[1], 'ответом — только первый кусок'


def test_telegram_errors_do_not_leak_token(monkeypatch, caplog):
    import requests
    from kultura_bot.engine import telegram_io

    def boom(*args, **kwargs):
        raise requests.ConnectionError(f'Max retries exceeded with url: /bot{TOKEN}/getUpdates')

    io = telegram_io.TelegramIO(TOKEN)
    monkeypatch.setattr(io._session(), 'post', boom)
    with caplog.at_level('WARNING'):
        assert io.call('getUpdates') is None
    assert TOKEN not in caplog.text and 'ConnectionError' in caplog.text


# ------------------------------------------------------------------ сервер бота

def message(text_value, chat_id=OWNER_TG, user_id=OWNER_TG, chat_type='private', **extra):
    msg = {'message_id': 10, 'chat': {'id': int(chat_id), 'type': chat_type},
           'from': {'id': int(user_id), 'first_name': 'Анна'}, 'text': text_value}
    msg.update(extra)
    return {'update_id': 1, 'message': msg}


@pytest.fixture
def bot(env):
    tg = FakeTelegram()
    client = FakeClient()
    keys = []
    svc = service.Service(env.site, env.store, io_factory=lambda token: tg, client_factory=lambda key: client,
                          check_key=lambda key: keys.append(key) or ('ok', 'claude-opus-5-5'))
    assert svc.ready() is True
    svc.enqueue = lambda chat_id, job: svc.run_job(chat_id, job)        # без потоков: ответ сразу
    yield SimpleNamespace(svc=svc, tg=tg, client=client, env=env, keys=keys)
    svc.executor.shutdown(wait=False)


def test_settings_come_from_site(env):
    tg = FakeTelegram()
    checks = []
    svc = service.Service(env.site, env.store, io_factory=lambda token: tg,
                          check_key=lambda key: checks.append(key) or ('auth', 'Anthropic не принял ключ API (401).'))
    env.site.cfg['telegram']['token'] = ''
    assert svc.ready() is False and svc.status['state'] == 'waiting' and 'токена' in svc.status['detail']
    env.site.cfg['telegram']['token'] = TOKEN
    env.site.cfg['anthropic_key'] = ''
    svc.refresh_config(force=True)
    assert svc.ready() is False and 'ключа Claude API' in svc.status['detail']
    env.site.cfg['anthropic_key'] = KEY
    env.site.cfg['paused'] = True
    svc.refresh_config(force=True)
    assert svc.ready() is False and svc.status['state'] == 'paused'
    env.site.cfg['paused'] = False
    svc.refresh_config(force=True)
    assert svc.ready() is True and svc.status['state'] == 'running'
    assert tg.webhook_deleted == 1 and svc.bot_id == 999
    assert checks == [KEY] and 'не принял ключ' in svc.status['claude_error'], 'ключ проверен при смене'
    assert env.site.reports[-1]['status']['claude_error'].startswith('Anthropic не принял ключ'), 'страница видит'
    env.site.config_error = SiteError('auth', 'Сайт не принял ключ сервера бота')
    svc.refresh_config(force=True)
    assert svc.ready() is False and svc.status['state'] == 'error', 'ключ сервера отозван — бот молчит'
    env.site.config_error = SiteError('offline', 'Сайт не отвечает')
    assert svc.refresh_config(force=True) is False, 'настроек нет — без них не работаем'


def test_site_offline_keeps_last_settings(env):
    tg = FakeTelegram()
    svc = service.Service(env.site, env.store, io_factory=lambda token: tg, check_key=lambda key: ('ok', ''))
    assert svc.ready() is True
    env.site.down = True
    assert svc.refresh_config(force=True) is True and svc.ready() is True, 'сайт моргнул — работаем на прежних'


def test_stranger_gets_one_refusal_and_costs_nothing(bot):
    bot.svc.handle_update(message('покажи зарплаты', user_id='4040', chat_id='4040'))
    bot.svc.handle_update(message('ну покажи', user_id='4040', chat_id='4040'))
    assert [s[1].startswith('Это закрытый бот') for s in bot.tg.sent] == [True]
    assert bot.client.calls == []


def test_start_with_code_links_and_question_is_answered(bot):
    bot.env.site.links.clear()
    bot.env.site.codes['abcdefgh'] = dict(OWNER)
    bot.svc.handle_update(message('/start abcdefgh'))
    assert bot.tg.sent[-1][1] == 'Готово: вы подключены как Владелец.'
    bot.client.script += [resp(thinking(), text('Ответ: **42** кеги'))]
    bot.svc.handle_update(message('сколько кег?'))
    assert bot.tg.sent[-1] == (OWNER_TG, 'Ответ: **42** кеги', None)
    first = bot.client.calls[-1]['messages'][0]['content'][0]['text']
    assert first.startswith('[') and 'пишет Владелец (owner)]' in first and first.endswith('\nсколько кег?')
    dialog = bot.env.store.get_dialog(OWNER_TG)
    assert dialog['turns'] == 1 and dialog['fingerprint'] == bot.svc.get_catalog().bot.fingerprint
    bot.client.script += [resp(text('Второй'))]
    bot.svc.handle_update(message('а вчера?'))
    assert len(bot.client.calls[-1]['messages']) == 3, 'диалог продолжается'


def test_usage_goes_to_site_report(bot):
    bot.client.script += [resp(text('Ответ'))]
    bot.svc.handle_update(message('вопрос'))
    bot.svc.report(force=True)
    usage = [item for r in bot.env.site.reports for item in r['usage']]
    assert usage and usage[-1]['model'] == 'claude-opus-5-5' and usage[-1]['requests'] == 1
    assert usage[-1]['input_tokens'] == 1000 and usage[-1]['cost_usd'] > 0
    bot.env.site.down = True
    bot.svc.add_usage('claude-opus-5-5', {'input_tokens': 5}, 0.5)
    bot.svc.report(force=True)
    bot.env.site.down = False
    bot.svc.report(force=True)
    assert bot.env.site.reports[-1]['usage'][0]['cost_usd'] == pytest.approx(0.5), 'отчёт не дошёл — расход не потерян'


def test_new_dialog_after_pause_and_after_catalog_change(bot):
    bot.client.script += [resp(text('Первый ответ'))]
    bot.svc.handle_update(message('вопрос'))
    dialog = bot.env.store.get_dialog(OWNER_TG)
    bot.env.store.save_dialog(OWNER_TG, dialog['fingerprint'], dialog['started_at'], dialog['messages'],
                              dialog['turns'], now=time.time() - settings.DIALOG_IDLE_MINUTES * 60 - 5)
    bot.client.script += [resp(text('Ответ после паузы'))]
    bot.svc.handle_update(message('вопрос через три часа'))
    assert bot.tg.sent[-1][1].startswith('*' + settings.NEW_DIALOG_NOTICE + '*')
    assert len(bot.client.calls[-1]['messages']) == 1
    bot.env.site.extra_tools = [site_tool('stocks_new_tool')]
    bot.svc.catalog_at = 0                     # каталог устарел — сайт выложил новый инструмент
    bot.client.script += [resp(text('Ответ'))]
    bot.svc.handle_update(message('ещё'))
    assert service.FINGERPRINT_NOTICE in bot.tg.sent[-1][1] and len(bot.client.calls[-1]['messages']) == 1


def test_cost_line_and_long_dialog(bot):
    bot.env.monkeypatch.setattr(settings, 'SHOW_COST', True)
    bot.client.script += [resp(text('Ответ'))]
    bot.svc.handle_update(message('вопрос'))
    one = claude.cost_usd('claude-opus-5-5', {'input_tokens': 1000, 'output_tokens': 200})
    assert bot.tg.sent[-1][1] == f'Ответ\n\n*Ответ обошёлся в ${one:.2f} (запросов к модели: 1).*'
    assert formatting.to_html('*Ответ обошёлся в $0.01 (запросов к модели: 1).*') == \
        '<i>Ответ обошёлся в $0.01 (запросов к модели: 1).</i>'
    bot.env.monkeypatch.setattr(settings, 'SHOW_COST', False)
    bot.env.monkeypatch.setattr(settings, 'QUESTION_BUDGET_USD', one / 2)
    bot.client.script += [resp(use('common_whoami', {}), stop='tool_use'), resp(text('Коротко'))]
    bot.svc.handle_update(message('ещё вопрос'))
    assert bot.tg.sent[-1][1].startswith('Коротко\n\n*Ответ обошёлся в $0.02 (запросов к модели: 2) — '
                                         'остановился на пределе $0.00 на вопрос.*'), 'предел — строка есть всегда'
    bot.env.monkeypatch.setattr(settings, 'QUESTION_BUDGET_USD', 2.0)
    bot.env.monkeypatch.setattr(settings, 'DIALOG_MAX_CHARS', 100)
    bot.client.script += [resp(text('С чистого листа'))]
    bot.svc.handle_update(message('третий вопрос'))
    assert bot.tg.sent[-1][1] == f'*{service.LONG_DIALOG_NOTICE}*\n\nС чистого листа'
    assert len(bot.client.calls[-1]['messages']) == 1, 'длинная история не тянется в новый вопрос'


def test_new_waits_for_answer_in_progress_and_queued_questions_survive_restart(bot):
    del bot.svc.enqueue                        # настоящая очередь
    submitted = []
    bot.svc.executor = SimpleNamespace(submit=lambda fn, *args: submitted.append((fn, args)),
                                       shutdown=lambda **kw: None)
    bot.svc.handle_update(message('вопрос 1'))
    bot.svc.handle_update(message('/new'))
    bot.svc.handle_update(message('вопрос 2'))
    assert len(submitted) == 1 and bot.tg.sent == [], 'всё ждёт в очереди чата'
    assert [j['status'] for j in bot.env.store.recent_jobs()] == ['queued', 'queued'], 'вопросы записаны сразу'
    assert len(bot.env.store.take_interrupted_jobs(1800)) == 2, 'остановка, пока ждали, — «повторите»'

    bot.svc.queues.clear()                     # как после перезапуска
    bot.svc.busy.clear()
    submitted.clear()
    bot.svc.handle_update(message('вопрос 1'))
    bot.svc.handle_update(message('/new'))
    bot.svc.handle_update(message('вопрос 2'))
    bot.client.script += [resp(text('Ответ 1')), resp(text('Ответ 2'))]
    fn, args = submitted[0]
    fn(*args)                                  # очередь чата: вопрос 1, /new, вопрос 2
    assert [m[1] for m in bot.tg.sent] == ['Ответ 1', service.NEW_DIALOG_TEXT, 'Ответ 2']
    assert len(bot.client.calls[-1]['messages']) == 1, 'вопрос 2 — в новом диалоге, /new не отменён'


def test_answer_rechecks_access_and_site_down_is_said_plainly(bot):
    job = {'message': message('вопрос')['message'], 'actor': dict(OWNER), 'text': 'вопрос', 'chat_type': 'private'}
    bot.env.site.links.clear()                 # привязку сняли, пока вопрос ждал очереди
    bot.svc.actor_cache.clear()
    bot.svc.run_job(OWNER_TG, job)
    assert bot.client.calls == [] and bot.tg.sent == [], 'без доступа — ни Claude, ни ответа'
    assert bot.env.store.recent_jobs()[0]['error'] == 'no access'
    bot.env.site.links[OWNER_TG] = dict(OWNER)
    bot.env.site.down = True
    bot.svc.run_job(OWNER_TG, job)
    assert bot.tg.sent[-1][1] == service.SITE_DOWN_TEXT and bot.client.calls == []
    bot.svc.actor_cache.clear()
    bot.svc.handle_update(message('ещё вопрос'))
    assert bot.tg.sent[-1][1] == service.SITE_DOWN_TEXT, 'не знаем, кто пишет, — честно говорим'


def test_group_only_when_addressed(bot):
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


def test_anthropic_errors_become_plain_text_and_stay_on_page(bot):
    import anthropic
    bot.client.script += [api_error(anthropic.AuthenticationError, 401, 'invalid x-api-key')]
    bot.svc.handle_update(message('вопрос'))
    assert 'Anthropic не принял ключ API' in bot.tg.sent[-1][1]
    assert 'не принял ключ' in bot.env.site.reports[-1]['status']['claude_error']
    assert bot.env.store.recent_jobs()[0]['status'] == 'error'
    bot.svc.tg.updates.append({'ok': True, 'result': []})
    bot.svc.poll_once()                         # опрос Telegram пишет «работает» — ошибка Claude остаётся
    assert 'не принял ключ' in bot.svc.status['claude_error']
    bot.client.script += [api_error(anthropic.BadRequestError, 400, 'messages.1: bad')]
    bot.env.store.save_dialog(OWNER_TG, 'fp', '2026-10-19T10:00:00+03:00', [], 1)
    bot.svc.handle_update(message('вопрос 2'))
    assert 'Диалог начат заново' in bot.tg.sent[-1][1] and bot.env.store.get_dialog(OWNER_TG) is None
    bot.client.script += [resp(text('Снова отвечаю'))]
    bot.svc.handle_update(message('вопрос 3'))
    assert bot.svc.status['claude_error'] == '' and bot.env.site.reports[-1]['status']['claude_error'] == ''


def test_photo_pdf_and_unsupported_files(bot):
    bot.client.script += [resp(text('На фото накладная'))]
    update = message('', photo=[{'file_id': 'small', 'file_size': 10}, {'file_id': 'big', 'file_size': 99}])
    update['message'].pop('text')
    update['message']['caption'] = 'что это?'
    bot.svc.handle_update(update)
    content = bot.client.calls[-1]['messages'][0]['content']
    assert content[1]['type'] == 'image' and content[1]['source']['media_type'] == 'image/jpeg'
    assert content[0]['text'].endswith('\nчто это?')
    bot.client.script += [resp(text('По тексту'))]
    bot.svc.handle_update(message('посмотри смету', document={'file_id': 'x1', 'mime_type': 'application/msword'}))
    assert bot.tg.sent[-2][1] == service.UNSUPPORTED_FILE_TEXT and bot.tg.sent[-1][1] == 'По тексту'
    asked = []
    bot.tg.download = lambda file_id, max_bytes: asked.append((file_id, max_bytes))   # не скачалось
    bot.client.script += [resp(text('Без файла'))]
    bot.svc.handle_update(message('вот счёт', document={'file_id': 'pdf1', 'mime_type': 'application/pdf'}))
    assert asked == [('pdf1', settings.INPUT_FILE_MAX_BYTES)]
    assert 'PDF — до 10 МБ' in bot.tg.sent[-2][1] and bot.tg.sent[-1][1] == 'Без файла'
    assert service.Service._limit('image') == service.IMAGE_MAX_BYTES, 'картинка — в пределе Claude API'
    update = message('')
    update['message'].pop('text')
    update['message']['sticker'] = {'file_id': 's'}
    bot.svc.handle_update(update)
    assert bot.tg.sent[-1][1] == service.UNSUPPORTED_TEXT


def test_question_during_shutdown_is_not_lost_silently(bot):
    del bot.svc.enqueue                        # настоящая очередь, а не ответ сразу

    def closed(*args, **kwargs):
        raise RuntimeError('cannot schedule new futures after shutdown')

    bot.svc.executor.submit = closed
    bot.svc.handle_update(message('сколько кег?'))
    assert bot.tg.sent[-1] == (OWNER_TG, service.RESTARTING_TEXT, None)
    assert OWNER_TG not in bot.svc.busy and OWNER_TG not in bot.svc.queues, 'чат не завис «занятым»'
    assert bot.env.store.recent_jobs()[0]['status'] == 'error'


def test_interrupted_answers_are_reported_once(env):
    env.store.start_job('100', '555')
    env.store.start_job('100', '555', status='queued')
    env.store.start_job('200', '555', now=time.time() - 7200)            # давно — не тревожим
    tg = FakeTelegram()
    svc = service.Service(env.site, env.store, io_factory=lambda token: tg, check_key=lambda key: ('ok', ''))
    assert svc.ready() is True
    assert tg.sent == [('100', service.INTERRUPTED_TEXT, None)], 'одно сообщение на чат'
    svc.ready()
    assert len(tg.sent) == 1


def test_conflict_and_bad_token_states(env):
    tg = FakeTelegram()
    svc = service.Service(env.site, env.store, io_factory=lambda token: tg, check_key=lambda key: ('ok', ''))
    svc.stopping.wait = lambda timeout=None: None        # без пауз
    assert svc.ready() is True
    tg.updates.append({'ok': False, 'error_code': 409, 'description': 'Conflict: terminated by other getUpdates'})
    svc.poll_once()
    assert svc.status['state'] == 'conflict' and 'другая программа' in svc.status['detail']
    tg.updates.append({'ok': False, 'error_code': 409, 'description': "Conflict: can't use getUpdates while webhook is active"})
    svc.poll_once()
    assert tg.webhook_deleted == 2
    tg.updates.append({'ok': False, 'error_code': 401, 'description': 'Unauthorized'})
    svc.poll_once()
    assert svc.status['state'] == 'error' and 'не принимает токен' in svc.status['detail']


def test_main_without_key_exits_with_hint(monkeypatch, capsys):
    from kultura_bot.engine import main
    monkeypatch.delenv('KULTURA_BOT_KEY', raising=False)
    assert main.main() == 2
    assert 'KULTURA_BOT_KEY' in capsys.readouterr().err


# ------------------------------------------------------------------ вид ответа (решения 2026-10-24)

HOW_ANSWER = ('**Неделя 16–22 окт: 4 412 тыс. ₽ — 98% плана.**\n\n'
              '> **Вчера, тыс. ₽ · % плана**\n> Лиговский · 171 · 104%\n> Кременчугская · 129 · 86%\n\n'
              'Могу разложить Кременчугскую по дням.\n\n'
              '>> Как считается\n>> % плана = 4 412 / 4 520 = 98%; metrics.avg_rating — из инструмента.')


def test_quotes_become_blockquotes_and_survive_splitting():
    html = formatting.to_html('Вывод\n> **Вчера** · 171 · 104%\n> Лиг · <b>\n>> Как считается\n>> формула\nконец')
    assert html == ('Вывод\n<blockquote><b>Вчера</b> · 171 · 104%\nЛиг · &lt;b&gt;</blockquote>\n'
                    '<blockquote expandable>Как считается\nформула</blockquote>\nконец'), \
        'подряд идущие строки — одна цитата, смена вида — новая, текст экранирован'
    assert formatting.to_html('>5 смен подряд') == '&gt;5 смен подряд', 'без пробела после «>» — не цитата'
    assert formatting.to_html('> - пункт') == '<blockquote>• пункт</blockquote>'
    parts = formatting.split('> ' + 'а' * 50 + '\n> ' + 'б' * 50, limit=60)
    assert parts == ['> ' + 'а' * 50, '> ' + 'б' * 50], 'длинная цитата режется по строкам, знак цитаты остаётся'
    assert all(formatting.to_html(p).startswith('<blockquote>') for p in parts)
    long_line = '> ' + 'в' * 130
    assert all(p.startswith('> ') for p in formatting.split(long_line, limit=60)), 'и у кусков длинной строки'
    assert formatting.plain('> цитата\n>> свёрнуто\n[сайт](https://beerkultura.ru)') == \
        'цитата\nсвёрнуто\nсайт: https://beerkultura.ru'
    assert formatting.visible_len('<b>a&amp;b</b>\n<blockquote expandable>в</blockquote>') == 5
    assert formatting.visible_len('🍺 ₽') == 4, 'Telegram считает в UTF-16: эмодзи — за два'
    assert formatting.to_html('    > Лиговский · 171') == '<blockquote>Лиговский · 171</blockquote>', \
        'цитата с отступом (модель копирует его из примеров) — тоже цитата'


def test_numbers_keep_together_across_line_breaks():
    """Решение 2026-10-25: перенос не отрывает «426 ₽» от «1» и «₽» от «24 тыс.» — пробелы внутри
    числа и перед единицей неразрывные. Код, адреса и обычные слова не трогаются; длина та же."""
    nb = '\u00a0'
    html = formatting.to_html('**−24 тыс. ₽** к 1 931 тыс. ₽; 12 345 678 л, 16,4 %, 2 ч, 100 шт\n'
                              '> Кременчугская · 503 · −16,4%\n- 2 часа, 5 литров, 2–13 сен 2026\n'
                              '`1 426 ₽` [1 426 ₽](https://beerkultura.ru/r?n=1%20426)\n```\n1 426 ₽\n```')
    assert f'<b>−24{nb}тыс.{nb}₽</b> к 1{nb}931{nb}тыс.{nb}₽; 12{nb}345{nb}678{nb}л, 16,4{nb}%, 2{nb}ч, 100{nb}шт' in html
    assert '• 2 часа, 5 литров, 2–13 сен 2026' in html, 'слова и даты — как были'
    assert '<code>1 426 ₽</code>' in html and '<pre>1 426 ₽</pre>' in html, 'код — как есть'
    assert f'<a href="https://beerkultura.ru/r?n=1%20426">1{nb}426{nb}₽</a>' in html, 'адрес — как был'
    assert formatting.visible_len(formatting.to_html('к 1 426 ₽')) == len('к 1 426 ₽')
    assert formatting.plain('**Итог 1 426 ₽**') == f'Итог 1{nb}426{nb}₽'
    assert formatting.nbsp('5 120 часов, 1 2345') == f'5{nb}120 часов, 1 2345', 'группа — ровно три цифры'


def test_split_how_and_with_link():
    visible, how = formatting.split_how(HOW_ANSWER)
    assert visible.endswith('Могу разложить Кременчугскую по дням.') and '>>' not in visible
    assert how == '% плана = 4 412 / 4 520 = 98%; metrics.avg_rating — из инструмента.'
    assert formatting.split_how('Ответ без пояснения') == ('Ответ без пояснения', '')
    other = 'Ответ\n\n>> Ещё 5 позиций\n>> Палм · 2'
    assert formatting.split_how(other) == (other, ''), 'свёрнутый хвост списка — не «Как считается»'
    visible, how = formatting.split_how('Ответ\n\n>> **Как считается:** доля = 136 / 327 = 42%\n>> iiko')
    assert (visible, how) == ('Ответ', 'доля = 136 / 327 = 42%\niiko'), 'текст в строке заголовка не теряется'
    url = 'https://t.me/MCPkulturabot/app?startapp=rep_' + 'a' * 22
    assert formatting.with_link('Могу показать по дням.', 'Как считается', url) == \
        f'Могу показать по дням. [Как считается]({url})', 'ни строки места: в конец последней строки'
    assert formatting.with_link('Итог 98%', 'Как считается', url).endswith(f'98% · [Как считается]({url})')
    assert formatting.with_link('> Лиг · 171', 'Как считается', url) == f'> Лиг · 171\n[Как считается]({url})', \
        'после цитаты — отдельной строкой'
    assert f'<a href="{url}">Как считается</a>' in formatting.to_html(formatting.with_link('Итог.', 'Как считается',
                                                                                             url))


def test_how_goes_behind_link_or_button(bot):
    mp = bot.env.monkeypatch
    mp.setattr(settings, 'MINIAPP_SHORT_NAME', 'app')
    bot.client.script += [resp(text(HOW_ANSWER))]
    bot.svc.handle_update(message('как выручка?'))
    sent = bot.tg.sent[-1][1]
    note_id = 'rep_' + f'{1:022x}'
    assert bot.env.site.notes == [(OWNER_TG, '% плана = 4 412 / 4 520 = 98%; metrics.avg_rating — из инструмента.')]
    assert sent.endswith(f'по дням. [Как считается](https://t.me/MCPkulturabot/app?startapp={note_id})')
    assert '>>' not in sent and bot.tg.markups[-1] is None, 'с коротким именем — ссылка текстом, без кнопок'

    mp.setattr(settings, 'MINIAPP_SHORT_NAME', '')
    bot.client.script += [resp(text(HOW_ANSWER))]
    bot.svc.handle_update(message('ещё раз'))
    assert bot.tg.sent[-1][1].endswith('Могу разложить Кременчугскую по дням.')
    assert bot.tg.markups[-1] == {'inline_keyboard': [[{'text': 'Как считается', 'web_app': {
        'url': 'https://beerkultura.ru/tg/chart?id=rep_' + f'{2:022x}'}}]]}, 'личка без имени — кнопка web_app'

    group = '-100500'
    bot.client.script += [resp(text(HOW_ANSWER))]
    bot.svc.handle_update(message('@MCPkulturabot как выручка?', chat_id=group, chat_type='supergroup'))
    assert bot.tg.sent[-1][1].endswith('по дням. [Как считается](https://beerkultura.ru/tg/report/rep_'
                                       + f'{3:022x})'), 'группа без имени — страница сайта'

    bot.env.site.note_error = SiteError('offline', 'Сайт не отвечает')
    bot.client.script += [resp(text(HOW_ANSWER))]
    bot.svc.handle_update(message('и ещё'))
    sent = bot.tg.sent[-1][1]
    assert sent.endswith('>> Как считается\n>> % плана = 4 412 / 4 520 = 98%; metrics.avg_rating — из инструмента.')
    assert formatting.to_html(sent).count('<blockquote expandable>') == 1, 'сайт не ответил — свёрнутая цитата'


def test_card_with_empty_text_sends_nothing_more(bot):
    bot.client.script += [resp(use('common_chart_send', {'chart': {}, 'caption': 'Ответ подписью'}),
                               stop='tool_use'), resp(text(''))]
    bot.svc.handle_update(message('график выручки'))
    assert bot.tg.sent == [], 'подпись к графику — это ответ: второго сообщения нет'
    bot.env.monkeypatch.setattr(settings, 'SHOW_COST', True)
    bot.client.script += [resp(use('common_report_send', {'report': {}}), stop='tool_use'), resp(text(''))]
    bot.svc.handle_update(message('отчёт: сентябрь'))
    assert len(bot.tg.sent) == 1 and bot.tg.sent[0][1].startswith('*Ответ обошёлся в $'), \
        'пока строка цены включена — только она'
    call = [c for c in bot.env.site.calls if c[0] == 'common_report_send'][-1]
    assert call[1]['chat_id'] == OWNER_TG, 'отчёт — только в чат разговора'


def test_report_mode_trigger_budget_and_header(bot):
    mp = bot.env.monkeypatch
    step = claude.cost_usd('claude-opus-5-5', {'input_tokens': 1000, 'output_tokens': 200})
    mp.setattr(settings, 'QUESTION_BUDGET_USD', 1.5 * step)
    mp.setattr(settings, 'REPORT_BUDGET_USD', 10 * step)
    bot.svc.handle_update(message('/report'))
    assert bot.tg.sent[-1][1] == service.REPORT_EMPTY_TEXT and not bot.client.calls
    bot.client.script += [resp(use('common_whoami', {}, 't1'), stop='tool_use'),
                          resp(use('common_whoami', {}, 't2'), stop='tool_use'),
                          resp(use('common_whoami', {}, 't3'), stop='tool_use'),
                          resp(text('Отчёт ушёл.'))]
    bot.svc.handle_update(message('/report как прошёл сентябрь'))
    first = bot.client.calls[-4]['messages'][0]['content'][0]['text']
    assert 'режим: отчёт' in first and first.endswith('\nкак прошёл сентябрь'), 'команда снята, режим назван'
    assert all('tool_choice' not in c for c in bot.client.calls[-4:]), 'предел отчёта больше: три шага с инструментами'
    bot.client.script += [resp(use('common_whoami', {}, 't4'), stop='tool_use'),
                          resp(use('common_whoami', {}, 't5'), stop='tool_use'), resp(text('Коротко.'))]
    bot.svc.handle_update(message('отчёт по выручке за вчера'))
    assert 'режим: отчёт' not in bot.client.calls[-3]['messages'][-1]['content'][0]['text'], \
        '«отчёт» без двоеточия — обычный вопрос'
    assert bot.client.calls[-1]['tool_choice'] == {'type': 'none'}, 'обычный предел — меньше'
    bot.client.script += [resp(text('Ок'))]
    bot.svc.handle_update(message('Исследуй продажи бельгийских сортов'))
    assert 'режим: отчёт' in bot.client.calls[-1]['messages'][-1]['content'][0]['text']


def test_header_has_weekdays_and_windows():
    from datetime import datetime
    from kultura_bot.engine.store import msk_now
    tz = msk_now().tzinfo
    text_value = service.calendar_text(datetime(2026, 10, 23, 9, 12, tzinfo=tz))
    assert text_value == ('рабочий день бара пт 23 окт (2026-10-23) · вчера чт 22 окт (2026-10-22) · '
                          'последние 7 дней 16–22 окт (2026-10-16..2026-10-22) · '
                          'предыдущие 7 дней 9–15 окт (2026-10-09..2026-10-15) · '
                          'этот месяц до вчера 1–22 окт (2026-10-01..2026-10-22) · '
                          'прошлый месяц 1–30 сен (2026-09-01..2026-09-30)')
    night = service.calendar_text(datetime(2026, 11, 1, 3, 0, tzinfo=tz))
    assert night.startswith('рабочий день бара сб 31 окт'), 'до 06:00 — ещё вчерашний рабочий день'
    monday = service.calendar_text(datetime(2026, 11, 2, 9, 0, tzinfo=tz))
    assert 'последние 7 дней 26 окт – 1 ноя (2026-10-26..2026-11-01)' in monday
    assert 'этот месяц до вчера 1 ноя (2026-11-01..2026-11-01)' in monday
    first = service.calendar_text(datetime(2026, 12, 1, 12, 0, tzinfo=tz))
    assert 'этот месяц' not in first and 'прошлый месяц 1–30 ноя' in first, 'первое число — месяц ещё пуст'


def test_buttons_go_under_the_last_part(monkeypatch):
    from kultura_bot.engine import telegram_io
    calls = []

    class IO(telegram_io.TelegramIO):
        def call(self, method, payload=None, timeout=8):
            calls.append(dict(payload or {}))
            return {'ok': True, 'result': {'message_id': len(calls)}}

    markup = {'inline_keyboard': [[{'text': 'Как считается', 'web_app': {'url': 'https://x/y'}}]]}
    long_answer = ('абзац ' * 400 + '\n\n') * 2
    IO('t').send_markdown('1', long_answer, reply_markup=markup)
    assert len(calls) == 2 and 'reply_markup' not in calls[0] and calls[1]['reply_markup'] == markup


# ------------------------------------------------------------------ замечания независимой проверки 2026-10-24

def test_unsafe_link_targets_are_not_links():
    for url in ('https://beerkultura.ru:x@evil.example/login', 'https://"@evil.example/login',
                'https://beerkultura.ru"@evil.example/login', 'javascript:alert(1)'):
        assert '<a ' not in formatting.to_html(f'[Войти]({url})'), url
    assert formatting.to_html('[ок](https://beerkultura.ru/x)') == '<a href="https://beerkultura.ru/x">ок</a>'


def test_how_blocks_all_cut_and_heading_variants():
    visible, how = formatting.split_how('Итог\n>> Как считается\n>> первый\n\nЕщё\n>> **Как считается:** % плана = 1\n'
                                        '>> второй')
    assert visible == 'Итог\n\nЕщё' and how == 'первый\n\n% плана = 1\nвторой', 'все блоки — в одну записку'
    for head, body in (('«Как считается» — (факт − план) / план', '(факт − план) / план'),
                       ('Как считается: −5% к плану', '−5% к плану'), ('_Как считается_', '')):
        assert formatting.split_how(f'Ответ\n>> {head}\n>> x')[1] == (f'{body}\nx' if body else 'x'), head
    body = 'б' * 130
    for prefix in ('> ', '>> '):
        parts = formatting.split(prefix + body, limit=40)
        assert ''.join(p[len(prefix):] for p in parts) == body, 'длинная строка цитаты — без повторов'
        assert all(len(p) <= 40 for p in parts)
    assert formatting.truncate_utf16('ab🍺c', 3) == 'ab' and formatting.truncate_utf16('ab🍺c', 4) == 'ab🍺'


def test_report_command_forms_and_group_mention(bot):
    assert bot.svc._command('/report\nкак сентябрь') == ('report', 'как сентябрь')
    assert bot.svc._command('/report@MCPkulturabot\tвопрос') == ('report', 'вопрос')
    assert bot.svc._strip_mention('@MCPkulturabot, отчёт: сентябрь') == 'отчёт: сентябрь'
    bot.client.script += [resp(text('Ок'))]
    bot.svc.handle_update(message('@MCPkulturabot, отчёт: сентябрь', chat_id='-100500', chat_type='supergroup'))
    assert 'режим: отчёт' in bot.client.calls[-1]['messages'][-1]['content'][0]['text']
    bot.client.script += [resp(text('Ок'))]
    pdf = message('', document={'file_id': 'f1', 'mime_type': 'application/pdf'}, caption='/report')
    pdf['message'].pop('text')
    bot.svc.handle_update(pdf)
    first = bot.client.calls[-1]['messages'][-1]['content']
    assert 'режим: отчёт' in first[0]['text'] and first[1]['type'] == 'document', '«/report» подписью к PDF'


def test_narration_before_card_is_not_a_second_bubble(bot):
    bot.client.script += [resp(text('Посмотрю выручку.'), use('common_whoami', {}, 't0'), stop='tool_use'),
                          resp(use('common_chart_send', {'chart': {}, 'caption': 'Ответ'}, 't1'), stop='tool_use'),
                          resp(text(''))]
    bot.svc.handle_update(message('график'))
    assert bot.tg.sent == [], 'текст до карточки — не ответ'
    bot.client.script += [resp(text('Смотрю.'), use('common_chart_send', {'chart': {}, 'caption': 'Ответ'}, 't2'),
                               stop='tool_use'), resp(text('И ещё одно уточнение.'))]
    bot.svc.handle_update(message('ещё график'))
    assert [m[1] for m in bot.tg.sent] == ['И ещё одно уточнение.'], 'текст после карточки остаётся'


def test_agents_build_no_report_pages(bot):
    catalog = bot.svc.get_catalog()
    assert tools.REPORT_TOOL in catalog.bot.toolset.names
    assert all(tools.REPORT_TOOL not in a.toolset.names for a in catalog.agents.values()), \
        'отчёт собирает бот, агент его не шлёт'
    bot.client.script += [
        resp(use(tools.ASK_AGENT, {'agent': 'payroll', 'task': 'Проверь ЗП за сентябрь 2026 по всем барам'}),
             stop='tool_use'),
        resp(text('Отчёт агента.')), resp(text('Готово.'))]
    bot.svc.handle_update(message('/report зарплата за сентябрь'))
    agent_first = bot.client.calls[-2]['messages'][0]['content'][0]['text']
    assert 'режим: отчёт' not in agent_first and 'последние 7 дней' in agent_first
