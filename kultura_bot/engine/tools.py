"""Инструменты бота для Claude: инструменты сайта по MCP, графики и агенты.

## Что видит модель

- **Инструменты сайта** — те же ~250, что у ИИ-агентов владельца: список и описания сервер
  бота берёт у сайта (MCP tools/list), вызов идёт туда же (tools/call через полный
  коннектор /mcp, site.py). Сайт сам проверяет аргументы, держит лимиты и пишет журнал
  вызовов (клиент — имя ключа сервера бота). Сразу видны только
  settings.ALWAYS_LOADED_TOOLS; остальные помечены defer_loading и находятся поиском
  (tool_search_tool_regex — серверный инструмент Anthropic): описания всех уходят в
  запрос, но в контекст модели попадают только найденные.
- **common_chart_send** — график картинкой с кнопкой «Открыть интерактивно» (рисует и
  отправляет сайт); chat_id подставляет бот — чат разговора, что бы ни прислала модель.
- **common_report_send** — отчёт: страница с разделами на сайте и выжимка в чат с кнопкой
  «Открыть отчёт»; chat_id — так же, только чат разговора.
- **ask_agent** (только у бота) — поручить задачу агенту раздела (kultura_bot/agents/*.md):
  агент работает со своими инструкциями и инструментами своих разделов (коннекторы
  /mcp/<раздел>) и возвращает отчёт.

## Каталог (load_catalog)

Правила сервиса и списки инструментов сайт отдаёт по MCP; сервер бота запоминает их на
settings.CATALOG_TTL_S и обновляет по истечении. Порядок инструментов неизменен
(поиск, видимые сразу по имени, ask_agent, отложенные по имени): Claude кэширует начало
запроса и привязывает рассуждения модели к неизменному началу разговора. Сайт
выложил новые инструменты или правила — у каталога новый отпечаток, диалоги начинаются
заново (config.fingerprint).
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional

from kultura_bot import settings
from kultura_bot.engine import config
from kultura_bot.engine.site import SiteError

log = logging.getLogger('kultura-bot')

SEARCH_TOOL = {'type': 'tool_search_tool_regex_20251119', 'name': 'tool_search_tool_regex'}
CHART_TOOL = 'common_chart_send'
REPORT_TOOL = 'common_report_send'
SENDING_TOOLS = (CHART_TOOL, REPORT_TOOL)        # шлют в Telegram: чат — только чат разговора
INSTRUCTIONS_TOOL = 'common_instructions'
ASK_AGENT = 'ask_agent'
FULL_CONNECTOR = '/mcp'


# ------------------------------------------------------------------ каталог

@dataclass(frozen=True)
class Toolset:
    defs: List[Dict[str, Any]]           # tools для запроса к Claude
    names: FrozenSet[str]                # инструменты сайта, которые можно вызвать


@dataclass(frozen=True)
class Persona:
    system: str
    toolset: Toolset
    fingerprint: str


@dataclass(frozen=True)
class Catalog:
    bot: Persona
    agents: Dict[str, Persona]


def claude_tool(tool: Dict[str, Any], deferred: bool) -> Dict[str, Any]:
    """Инструмент MCP -> определение инструмента Claude."""
    definition = {'name': tool['name'],
                  'description': str(tool.get('description') or tool.get('title') or tool['name']),
                  'input_schema': tool.get('inputSchema') or {'type': 'object', 'properties': {}}}
    if deferred:
        definition['defer_loading'] = True
    return definition


def ask_agent_def() -> Dict[str, Any]:
    agents = config.load_agents()
    choices = '; '.join(f'{name} — {agent.title}' for name, agent in agents.items())
    return {
        'name': ASK_AGENT,
        'description': ('Поручить большую задачу агенту раздела: он работает со своими правилами и инструментами '
                        'своего раздела и возвращает отчёт (вывод, таблица, что проверить). Для задач в много '
                        'шагов: проверка зарплаты за месяц, черновики контент-плана, сводка по остаткам и '
                        'заказам, разбор отзывов. Короткие вопросы решай сам. Агенты: ' + choices + '.'),
        'input_schema': {
            'type': 'object', 'additionalProperties': False, 'required': ['agent', 'task'],
            'properties': {
                'agent': {'type': 'string', 'enum': list(agents), 'description': 'Кому поручить.'},
                'task': {'type': 'string', 'minLength': 10, 'maxLength': 8000,
                         'description': 'Задача целиком: период, бары, что получить на выходе, что уже '
                                        'известно из разговора. Агент не видит разговор — только этот текст.'},
            },
        },
    }


def build_toolset(site_tools: List[Dict[str, Any]], *, with_agents: bool) -> Toolset:
    """Список tools для запроса: поиск, видимые сразу, ask_agent (боту), отложенные."""
    by_name = {t['name']: t for t in site_tools if t['name'] not in settings.HIDDEN_TOOLS}
    tools = [by_name[name] for name in sorted(by_name)]
    loaded = [t for t in tools if t['name'] in settings.ALWAYS_LOADED_TOOLS]
    deferred = [t for t in tools if t['name'] not in settings.ALWAYS_LOADED_TOOLS]
    defs: List[Dict[str, Any]] = [dict(SEARCH_TOOL)]
    defs += [claude_tool(t, deferred=False) for t in loaded]
    if with_agents:
        defs.append(ask_agent_def())
    defs += [claude_tool(t, deferred=True) for t in deferred]
    return Toolset(defs=defs, names=frozenset(by_name))


def _text(result: Dict[str, Any]) -> str:
    return '\n'.join(str(b.get('text') or '') for b in result.get('content') or []
                     if isinstance(b, dict) and b.get('type') == 'text').strip()


def load_catalog(site) -> Catalog:
    """Правила и инструменты с сайта -> системные промпты и наборы инструментов бота и агентов."""
    service_rules = site.instructions(FULL_CONNECTOR)
    bot_system = config.bot_system_text(service_rules)
    bot_tools = build_toolset(site.tools(FULL_CONNECTOR), with_agents=True)
    bot = Persona(bot_system, bot_tools, config.fingerprint(bot_system, bot_tools.defs))
    agents: Dict[str, Persona] = {}
    for name, agent in config.load_agents().items():
        merged: Dict[str, Dict[str, Any]] = {}
        rules: List[str] = []
        for domain in agent.domains:
            for tool in site.tools(f'{FULL_CONNECTOR}/{domain}'):
                merged.setdefault(tool['name'], tool)
            answer = site.call_tool(INSTRUCTIONS_TOOL, {'domain': domain})
            if not answer.get('isError'):
                rules.append(_text(answer))
        system = config.agent_system_text(agent, rules, service_rules)
        toolset = build_toolset(list(merged.values()), with_agents=False)
        agents[name] = Persona(system, toolset, config.fingerprint(system, toolset.defs))
    return Catalog(bot=bot, agents=agents)


# ------------------------------------------------------------------ исполнение

@dataclass
class ToolContext:
    """С кем и где идёт разговор: куда слать графики, что можно вызывать."""
    site: Any
    chat_id: str
    allowed: FrozenSet[str]                                  # инструменты сайта этого разговора
    run_agent: Optional[Callable[[str, str], str]] = None    # ask_agent: (имя агента, задача) -> отчёт
    is_agent: bool = False                                   # агент не поручает задачи другим агентам
    charts_sent: List[Dict[str, Any]] = field(default_factory=list)
    reports_sent: List[Dict[str, Any]] = field(default_factory=list)
    spend: Any = None                                        # расход вопроса (agent.Spend): общий у бота и агентов


def tool_result(tool_use_id: str, content: Any, is_error: bool = False) -> Dict[str, Any]:
    if isinstance(content, str):
        content = [{'type': 'text', 'text': content or '(пустой ответ)'}]
    out = {'type': 'tool_result', 'tool_use_id': tool_use_id, 'content': content}
    if is_error:
        out['is_error'] = True
    return out


def _result_blocks(content: List[Any]) -> List[Dict[str, Any]]:
    """Блоки ответа MCP -> content для tool_result Claude."""
    blocks: List[Dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get('type')
        if kind == 'text':
            blocks.append({'type': 'text', 'text': str(block.get('text') or '')})
        elif kind == 'image' and block.get('data'):
            blocks.append({'type': 'image', 'source': {'type': 'base64', 'media_type': block.get('mimeType') or
                                                       'image/png', 'data': block['data']}})
        elif kind == 'resource':
            res = block.get('resource') or {}
            blocks.append({'type': 'text', 'text': f'[файл {res.get("mimeType") or ""}: {res.get("uri") or ""} — '
                                                   f'показать его в чате бот не может, дайте ссылку человеку]'})
    return blocks or [{'type': 'text', 'text': '(пустой ответ)'}]


def execute(block: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    """Исполнить tool_use (dict из ответа Claude) -> tool_result. Никогда не бросает."""
    name = block.get('name') or ''
    tool_use_id = block.get('id') or ''
    args = block.get('input')
    if not isinstance(args, dict):
        return tool_result(tool_use_id, 'Аргументы инструмента должны быть объектом JSON.', is_error=True)
    if name == ASK_AGENT:
        return _run_ask_agent(tool_use_id, args, ctx)
    if name not in ctx.allowed:
        return tool_result(tool_use_id, f'Нет инструмента {name}. Найди нужный поиском tool_search_tool_regex.',
                           is_error=True)
    if name in SENDING_TOOLS:
        args = dict(args, chat_id=str(ctx.chat_id))     # график и отчёт — только в чат разговора
    try:
        result = ctx.site.call_tool(name, args)
    except SiteError as exc:
        return tool_result(tool_use_id, f'Сайт не выполнил вызов: {exc.text}', is_error=True)
    is_error = bool(result.get('isError'))
    if name in SENDING_TOOLS and not is_error:
        try:
            sent = json.loads(_text(result))
        except ValueError:
            sent = {}
        (ctx.charts_sent if name == CHART_TOOL else ctx.reports_sent).append(sent if isinstance(sent, dict) else {})
    return tool_result(tool_use_id, _result_blocks(result.get('content') or []), is_error=is_error)


def _run_ask_agent(tool_use_id: str, args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    agent_name = args.get('agent')
    task = args.get('task')
    if ctx.run_agent is None or ctx.is_agent:
        return tool_result(tool_use_id, 'Агент не может поручать задачи другим агентам.', is_error=True)
    if agent_name not in config.load_agents():
        return tool_result(tool_use_id, f'Нет агента {agent_name}.', is_error=True)
    if not isinstance(task, str) or len(task.strip()) < 10:
        return tool_result(tool_use_id, 'Задача для агента — текст не короче 10 символов.', is_error=True)
    log.info('[BOT] поручение агенту %s', agent_name)
    try:
        report = ctx.run_agent(agent_name, task.strip())
    except Exception as exc:  # noqa: BLE001 — сбой агента -> ошибка инструмента, разговор продолжается
        log.exception('[BOT] агент %s упал', agent_name)
        return tool_result(tool_use_id, f'Агент {agent_name} не справился: {type(exc).__name__}: {exc}',
                           is_error=True)
    limit = settings.AGENT_ANSWER_MAX_CHARS
    if len(report) > limit:
        report = report[:limit] + f'\n\n[отчёт агента обрезан до {limit} символов]'
    return tool_result(tool_use_id, report or 'Агент вернул пустой отчёт.')
