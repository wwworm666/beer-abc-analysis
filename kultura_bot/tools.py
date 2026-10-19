"""Инструменты бота для Claude: все инструменты сайта, графики и агенты.

## Что видит модель

- **Инструменты сайта** — те же ~250, что у агентов по MCP (core/mcp/registry): каждый
  вызывает настоящий маршрут сайта от имени администратора, который пишет боту
  (core/mcp/bridge.execute — те же проверки аргументов, кэш, лимиты и журнал вызовов).
  Сразу видны только settings.ALWAYS_LOADED_TOOLS; остальные помечены defer_loading и
  находятся поиском (tool_search_tool_regex — серверный инструмент Anthropic): описания
  всех инструментов уходят в запрос, но в контекст модели попадают только найденные.
- **common_chart_send** — график картинкой с кнопкой «Открыть интерактивно»; chat_id
  подставляет бот (чат разговора), что бы ни прислала модель.
- **ask_agent** (только у бота) — поручить задачу агенту раздела (kultura_bot/agents/*.md):
  агент работает со своими инструкциями и инструментами своих разделов и возвращает отчёт.

У агента — инструменты его разделов (и общие common_), без ask_agent.

## Порядок и неизменность

Список инструментов один и тот же на весь диалог (порядок: поиск, видимые сразу по
имени, отложенные по имени): Claude кэширует начало запроса и привязывает рассуждения
модели к неизменному началу разговора. Новый набор инструментов (выкладка) — новый
диалог (kultura_bot/config.fingerprint).

## Журнал

Каждый вызов инструмента сайта пишется в журнал вызовов агентов (страница «Доступ
агентов», common_audit_recent) с клиентом «Бот @…» и коннектором telegram.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from kultura_bot import settings

log = logging.getLogger('kultura-bot')

SEARCH_TOOL = {'type': 'tool_search_tool_regex_20251119', 'name': 'tool_search_tool_regex'}
CHART_TOOL = 'common_chart_send'
ASK_AGENT = 'ask_agent'
AUDIT_CONNECTOR = 'telegram'


def _site_tool_def(spec, deferred: bool) -> Dict[str, Any]:
    definition = {'name': spec.name, 'description': spec.description, 'input_schema': spec.input_schema}
    if deferred:
        definition['defer_loading'] = True
    return definition


def _site_specs(domains: Optional[tuple]) -> List[Any]:
    """Инструменты сайта для бота (domains=None — все) или агента (его разделы + common)."""
    from core.mcp import registry
    from core.mcp.spec import COMMON_DOMAIN
    specs = registry.tools_for(None)
    if domains is not None:
        allowed = set(domains) | {COMMON_DOMAIN}
        specs = [s for s in specs if s.domain in allowed or set(s.also_in) & set(domains)]
    return sorted((s for s in specs if s.name not in settings.HIDDEN_TOOLS), key=lambda s: s.name)


def ask_agent_def(agent_names: List[str]) -> Dict[str, Any]:
    from kultura_bot import config
    agents = config.load_agents()
    choices = '; '.join(f'{name} — {agents[name].title}' for name in agent_names)
    return {
        'name': ASK_AGENT,
        'description': ('Поручить большую задачу агенту раздела: он работает со своими правилами и инструментами '
                        'своего раздела и возвращает отчёт (вывод, таблица, что проверить). Для задач в много '
                        'шагов: проверка зарплаты за месяц, черновики контент-плана, сводка по остаткам и '
                        'заказам, разбор отзывов. Короткие вопросы решай сам. Агенты: ' + choices + '.'),
        'input_schema': {
            'type': 'object', 'additionalProperties': False, 'required': ['agent', 'task'],
            'properties': {
                'agent': {'type': 'string', 'enum': list(agent_names), 'description': 'Кому поручить.'},
                'task': {'type': 'string', 'minLength': 10, 'maxLength': 8000,
                         'description': 'Задача целиком: период, бары, что получить на выходе, что уже '
                                        'известно из разговора. Агент не видит разговор — только этот текст.'},
            },
        },
    }


def tool_defs(*, domains: Optional[tuple] = None, agent_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Список tools для запроса: бот (domains=None, agent_names — кому можно поручать) или агент."""
    specs = _site_specs(domains)
    loaded = [s for s in specs if s.name in settings.ALWAYS_LOADED_TOOLS]
    deferred = [s for s in specs if s.name not in settings.ALWAYS_LOADED_TOOLS]
    tools: List[Dict[str, Any]] = [dict(SEARCH_TOOL)]
    tools += [_site_tool_def(s, deferred=False) for s in loaded]
    if agent_names:
        tools.append(ask_agent_def(agent_names))
    tools += [_site_tool_def(s, deferred=True) for s in deferred]
    return tools


# ------------------------------------------------------------------ исполнение

@dataclass
class ToolContext:
    """С кем и где идёт разговор: от чьего имени инструменты и куда слать графики."""
    app: Any
    principal: Any
    chat_id: str
    domains: Optional[tuple] = None          # None — бот (все разделы); иначе — разделы агента
    run_agent: Optional[Callable[[str, str], str]] = None   # ask_agent: (имя агента, задача) -> отчёт
    charts_sent: List[Dict[str, Any]] = field(default_factory=list)


def _result_blocks(result) -> List[Dict[str, Any]]:
    """Блоки ToolResult моста (формат MCP) -> content для tool_result Claude."""
    blocks: List[Dict[str, Any]] = []
    for block in result.content:
        kind = block.get('type')
        if kind == 'text':
            blocks.append({'type': 'text', 'text': block.get('text') or ''})
        elif kind == 'image' and block.get('data'):
            blocks.append({'type': 'image', 'source': {'type': 'base64', 'media_type': block.get('mimeType') or
                                                       'image/png', 'data': block['data']}})
        elif kind == 'resource':
            res = block.get('resource') or {}
            blocks.append({'type': 'text', 'text': f'[файл {res.get("mimeType") or ""}: {res.get("uri") or ""} — '
                                                   f'показать его в чате бот не может, дайте ссылку человеку]'})
    return blocks or [{'type': 'text', 'text': '(пустой ответ)'}]


def tool_result(tool_use_id: str, content: Any, is_error: bool = False) -> Dict[str, Any]:
    if isinstance(content, str):
        content = [{'type': 'text', 'text': content or '(пустой ответ)'}]
    out = {'type': 'tool_result', 'tool_use_id': tool_use_id, 'content': content}
    if is_error:
        out['is_error'] = True
    return out


def _audit(principal, tool: str, args: Any, status: str, result=None, duration_ms=None, error: str = '') -> None:
    from core.mcp import audit
    try:
        audit.record(user_login=principal.login, token_id=principal.token_id, client_name=principal.client_name,
                     connector=AUDIT_CONNECTOR, tool=tool, args=args, status=status,
                     http_status=result.http_status if result else None, duration_ms=duration_ms,
                     result_chars=result.result_chars if result else None,
                     error=error or (result.error if result is not None and result.is_error else ''))
    except Exception:  # noqa: BLE001 — журнал не должен ломать ответ
        log.exception('[BOT] не удалось записать журнал вызова %s', tool)


def execute(block: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    """Исполнить tool_use (dict из ответа Claude) -> tool_result. Никогда не бросает."""
    name = block.get('name') or ''
    tool_use_id = block.get('id') or ''
    args = block.get('input')
    if not isinstance(args, dict):
        return tool_result(tool_use_id, 'Аргументы инструмента должны быть объектом JSON.', is_error=True)
    if name == ASK_AGENT:
        return _run_ask_agent(tool_use_id, args, ctx)
    from core.mcp import registry
    spec = registry.get_tool(name)
    visible = {s.name for s in _site_specs(ctx.domains)}
    if spec is None or name not in visible:
        return tool_result(tool_use_id, f'Нет инструмента {name}. Найди нужный поиском tool_search_tool_regex.',
                            is_error=True)
    if name == CHART_TOOL:
        args = dict(args, chat_id=str(ctx.chat_id))     # график — только в чат разговора
    return _run_site_tool(tool_use_id, spec, args, ctx)


def _run_site_tool(tool_use_id: str, spec, args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    from core.mcp import bridge, protocol
    principal = ctx.principal
    wait = protocol.rate_limiter.hit(principal.token_id)
    if wait is not None:
        message = (f'Слишком часто: не больше {protocol.RATE_LIMIT_PER_MINUTE} вызовов инструментов в минуту. '
                   f'Подожди {wait} с.')
        _audit(principal, spec.name, args, 'denied', error=message)
        return tool_result(tool_use_id, message, is_error=True)
    started = time.monotonic()
    try:
        with ctx.app.app_context():
            result = bridge.execute(spec, args, principal, connector=None, mode='full',
                                    admit=lambda: protocol.admission(principal.token_id, spec.name))
    except Exception as exc:  # noqa: BLE001 — мост сам не бросает; это страховка
        log.exception('[BOT] инструмент %s упал', spec.name)
        _audit(principal, spec.name, args, 'error', error=f'{type(exc).__name__}: {exc}')
        return tool_result(tool_use_id, f'Инструмент упал: {type(exc).__name__}: {exc}', is_error=True)
    if result.denied:
        _audit(principal, spec.name, args, 'denied', error=result.error)
    else:
        _audit(principal, spec.name, args, 'error' if result.is_error else 'ok', result,
               int((time.monotonic() - started) * 1000))
    if spec.name == CHART_TOOL and not result.is_error:
        try:
            ctx.charts_sent.append(json.loads(result.text_value))
        except ValueError:
            ctx.charts_sent.append({})
    return tool_result(tool_use_id, _result_blocks(result), is_error=result.is_error)


def _run_ask_agent(tool_use_id: str, args: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
    from kultura_bot import config
    agent_name = args.get('agent')
    task = args.get('task')
    if ctx.run_agent is None or ctx.domains is not None:
        return tool_result(tool_use_id, 'Агент не может поручать задачи другим агентам.', is_error=True)
    if agent_name not in config.load_agents():
        return tool_result(tool_use_id, f'Нет агента {agent_name}.', is_error=True)
    if not isinstance(task, str) or len(task.strip()) < 10:
        return tool_result(tool_use_id, 'Задача для агента — текст не короче 10 символов.', is_error=True)
    started = time.monotonic()
    try:
        report = ctx.run_agent(agent_name, task.strip())
    except Exception as exc:  # noqa: BLE001 — сбой агента -> ошибка инструмента, разговор продолжается
        log.exception('[BOT] агент %s упал', agent_name)
        _audit(ctx.principal, f'{ASK_AGENT}:{agent_name}', {'task': task}, 'error',
               error=f'{type(exc).__name__}: {exc}')
        return tool_result(tool_use_id, f'Агент {agent_name} не справился: {type(exc).__name__}: {exc}',
                            is_error=True)
    _audit(ctx.principal, f'{ASK_AGENT}:{agent_name}', {'task': task}, 'ok',
           duration_ms=int((time.monotonic() - started) * 1000))
    limit = settings.AGENT_ANSWER_MAX_CHARS
    if len(report) > limit:
        report = report[:limit] + f'\n\n[отчёт агента обрезан до {limit} символов]'
    return tool_result(tool_use_id, report or 'Агент вернул пустой отчёт.')
