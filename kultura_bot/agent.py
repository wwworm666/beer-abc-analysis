"""Разговор с Claude: шаги модели, инструменты, учёт расхода.

## Один вопрос (run_turn)

    история диалога + новый вопрос человека
    -> запрос к Claude (Messages API, beta)
    -> модель вызвала инструменты (stop_reason tool_use): исполняем, отдаём результаты
       одним сообщением, снова запрос — пока модель не ответит текстом
    -> ответ (текст последнего шага) + новая история

История только дописывается, ничего в ней не правится: Claude привязывает рассуждения
модели (thinking) к неизменному началу разговора, а кэш запроса — к неизменному префиксу.
Поэтому системный промпт и инструменты на весь диалог одни (config.fingerprint), а
служебная строка (время, кто пишет) — в самом сообщении человека.

## Параметры запроса

- model, effort, max_tokens — kultura_bot/settings.py; думает модель всегда (adaptive),
  рассуждения не показываются (display по умолчанию);
- инструменты — kultura_bot/tools.py (поиск по описаниям + отложенная загрузка);
- кэш: системный промпт — явная точка кэша, хвост разговора — автоматическая
  (cache_control верхнего уровня); повторные запросы диалога читают начало из кэша;
- context editing: когда контекст больше settings.CONTEXT_CLEAR_AT_TOKENS, Anthropic
  вычищает старые ответы инструментов (кроме результатов поиска инструментов);
- fallbacks="default": отказ модели по правилам безопасности (ложное срабатывание) —
  ответ запасной модели в том же запросе (settings.REFUSAL_FALLBACK);
- thinking.block_binding = drop_block: если начало разговора всё же разошлось с тем, к
  чему привязаны рассуждения, Claude отбрасывает их, а не отвечает ошибкой.

## Необязательные возможности

fallbacks, context editing и block_binding — бета-параметры API. Если Anthropic отвергнет
какой-то из них (400 с его именем в тексте ошибки), бот один раз повторяет запрос без
этой возможности и до перезапуска процесса больше её не шлёт (OPTIONAL_FEATURES,
_disabled) — бот отвечает, а в журнале остаётся предупреждение.

## Пределы

- settings.MAX_TOOL_ROUNDS шагов с инструментами на вопрос (агенту —
  AGENT_MAX_TOOL_ROUNDS): исчерпаны — последний запрос с tool_choice none, модель
  отвечает тем, что уже узнала;
- дневной расход settings.DAILY_BUDGET_USD: перед каждым шагом сверяется с bot_usage;
  исчерпан — BudgetExceeded (бот отвечает «лимит на сегодня»);
- pause_turn (серверный инструмент не уложился в шаг) — запрос повторяется как есть.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from kultura_bot import claude, settings, store, tools

log = logging.getLogger('kultura-bot')

BETA_CONTEXT = 'context-management-2025-06-27'
BETA_THINKING_BINDING = 'thinking-binding-controls-2026-08-01'
BETA_FALLBACK = 'server-side-fallback-2026-07-01'
MAX_PAUSE_RESUMES = 5            # подряд pause_turn без нового содержания — хватит

# Необязательные возможности: имя -> слова в тексте ошибки 400, по которым её узнать.
OPTIONAL_FEATURES = {
    'fallbacks': ('fallbacks', 'server-side-fallback'),
    'context_management': ('context_management', 'clear_tool_uses', 'exclude_tools', 'context-management'),
    'block_binding': ('block_binding', 'thinking-binding', 'prefix_mismatch'),
}
_disabled = set()                # отвергнутые API возможности (до перезапуска процесса)


class BudgetExceeded(Exception):
    """Дневной предел расхода исчерпан."""


@dataclass
class TurnResult:
    text: str                                  # ответ для человека (Markdown)
    messages: List[Dict[str, Any]]             # история после вопроса (дописанная)
    stop_reason: str = ''
    rounds: int = 0
    cost_usd: float = 0.0
    notes: List[str] = field(default_factory=list)   # max_rounds | max_tokens | refusal


def request_params(*, model: str, effort: str, system_text: str, tool_list: List[Dict[str, Any]],
                   messages: List[Dict[str, Any]], final: bool = False) -> Dict[str, Any]:
    """Параметры client.beta.messages.create (отдельно — для тестов и отладки)."""
    betas = []
    params: Dict[str, Any] = {
        'model': model,
        'max_tokens': settings.MAX_TOKENS,
        'system': [{'type': 'text', 'text': system_text, 'cache_control': {'type': 'ephemeral'}}],
        'tools': tool_list,
        'messages': messages,
        'output_config': {'effort': effort},
        'thinking': {'type': 'adaptive'},
        'cache_control': {'type': 'ephemeral'},
    }
    if 'block_binding' not in _disabled:
        params['thinking']['block_binding'] = {'prefix_mismatch_behavior': 'drop_block'}
        betas.append(BETA_THINKING_BINDING)
    if 'context_management' not in _disabled:
        params['context_management'] = {'edits': [{
            'type': 'clear_tool_uses_20250919',
            'trigger': {'type': 'input_tokens', 'value': settings.CONTEXT_CLEAR_AT_TOKENS},
            'keep': {'type': 'tool_uses', 'value': settings.CONTEXT_KEEP_TOOL_RESULTS},
            'exclude_tools': [tools.SEARCH_TOOL['name']],
        }]}
        betas.append(BETA_CONTEXT)
    if settings.REFUSAL_FALLBACK and 'fallbacks' not in _disabled:
        params['fallbacks'] = 'default'
        betas.append(BETA_FALLBACK)
    if final:
        params['tool_choice'] = {'type': 'none'}
    if betas:
        params['betas'] = betas
    return params


def rejected_feature(exc: BaseException) -> Optional[str]:
    """Какую необязательную возможность отверг API (400 с её именем в тексте) или None."""
    import anthropic
    if not isinstance(exc, anthropic.BadRequestError):
        return None
    message = str(getattr(exc, 'message', '') or exc).lower()
    for feature, words in OPTIONAL_FEATURES.items():
        if feature not in _disabled and any(word in message for word in words):
            return feature
    return None


def create_message(client: Any, build: Callable[[], Dict[str, Any]]):
    """Запрос к Claude; отвергнутую необязательную возможность выключить и повторить."""
    while True:
        try:
            return client.beta.messages.create(**build())
        except Exception as exc:  # noqa: BLE001 — разбор ниже, остальное — наверх как есть
            feature = rejected_feature(exc)
            if feature is None:
                raise
            _disabled.add(feature)
            log.warning('[BOT] Anthropic отверг %s — дальше без него: %s', feature, exc)


def _usage_dict(usage: Any) -> Dict[str, int]:
    out = {}
    for key in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'):
        out[key] = int(getattr(usage, key, 0) or 0)
    return out


def _block_dict(block: Any) -> Dict[str, Any]:
    """Блок ответа -> dict ровно в форме API (то, что прислано, без лишних полей)."""
    if isinstance(block, dict):
        return block
    return block.to_dict(mode='json')


def _texts(content: List[Dict[str, Any]]) -> str:
    return '\n\n'.join(b.get('text', '').strip() for b in content if b.get('type') == 'text' and
                       (b.get('text') or '').strip())


def check_budget() -> None:
    limit = settings.DAILY_BUDGET_USD
    if limit and store.spent_on() >= limit:
        raise BudgetExceeded(f'Дневной предел расхода на Claude исчерпан: {store.spent_on():.2f} $ из {limit:.2f} $ '
                             f'(DAILY_BUDGET_USD в kultura_bot/settings.py). Бот снова ответит после полуночи МСК.')


def run_turn(client: Any, *, system_text: str, tool_list: List[Dict[str, Any]], history: List[Dict[str, Any]],
             user_content: List[Dict[str, Any]], ctx: tools.ToolContext, model: Optional[str] = None,
             effort: Optional[str] = None, max_rounds: Optional[int] = None,
             on_step: Optional[Callable[[], None]] = None) -> TurnResult:
    """Ответить на один вопрос. Ошибки API (anthropic.*Error) и BudgetExceeded — наверх."""
    model = model or settings.MODEL
    effort = effort or settings.EFFORT
    max_rounds = settings.MAX_TOOL_ROUNDS if max_rounds is None else max_rounds
    messages = list(history) + [{'role': 'user', 'content': user_content}]
    result = TurnResult(text='', messages=messages)
    final_texts: List[str] = []
    pauses = 0
    final = False
    while True:
        check_budget()
        response = create_message(client, lambda: request_params(
            model=model, effort=effort, system_text=system_text, tool_list=tool_list, messages=messages,
            final=final))
        usage = _usage_dict(response.usage)
        served_by = getattr(response, 'model', None) or model
        cost = claude.cost_usd(served_by, usage)
        result.cost_usd += cost
        try:
            store.add_usage(served_by, usage, cost)
        except Exception:  # noqa: BLE001 — учёт не должен ронять ответ
            log.exception('[BOT] не удалось записать расход')
        content = [_block_dict(b) for b in response.content]
        messages.append({'role': 'assistant', 'content': content})
        result.stop_reason = response.stop_reason or ''
        text = _texts(content)
        if text:
            final_texts = [text]
        if on_step is not None:
            on_step()

        if response.stop_reason == 'pause_turn':
            pauses += 1
            if pauses > MAX_PAUSE_RESUMES:
                result.notes.append('pause_turn')
                break
            continue
        pauses = 0
        if response.stop_reason != 'tool_use':
            if response.stop_reason == 'max_tokens':
                result.notes.append('max_tokens')
            elif response.stop_reason == 'refusal':
                result.notes.append('refusal')
            break
        tool_uses = [b for b in content if b.get('type') == 'tool_use']
        if not tool_uses:
            break
        result.rounds += 1
        if result.rounds > max_rounds:
            # Шаги кончились: на каждый вызов — отказ, затем последний запрос без инструментов.
            result.notes.append('max_rounds')
            messages.append({'role': 'user', 'content': [
                tools.tool_result(b['id'], 'Лимит шагов на этот вопрос исчерпан: ответь тем, что уже знаешь, и '
                                            'скажи, чего не успел проверить.', is_error=True) for b in tool_uses]})
            final = True
            continue
        messages.append({'role': 'user', 'content': [tools.execute(b, ctx) for b in tool_uses]})

    result.text = '\n\n'.join(final_texts).strip()
    if 'refusal' in result.notes and not result.text:
        result.text = 'Модель отказалась отвечать на этот вопрос (правила безопасности Anthropic). Переформулируйте его.'
    if 'max_tokens' in result.notes:
        result.text = (result.text + '\n\n(ответ обрезан: модель упёрлась в предел длины)').strip()
    return result


def run_agent(client: Any, agent_name: str, task: str, *, parent: tools.ToolContext,
              header: str = '') -> str:
    """Поручение агенту: отдельный разговор с его инструкциями и инструментами. Вернуть отчёт."""
    from kultura_bot import config
    agent = config.load_agents()[agent_name]
    ctx = tools.ToolContext(app=parent.app, principal=parent.principal, chat_id=parent.chat_id,
                            domains=agent.domains, charts_sent=parent.charts_sent)
    text = (header + '\n' if header else '') + task
    result = run_turn(client, system_text=config.agent_system_text(agent),
                      tool_list=tools.tool_defs(domains=agent.domains), history=[],
                      user_content=[{'type': 'text', 'text': text}], ctx=ctx, effort=settings.AGENT_EFFORT,
                      max_rounds=settings.AGENT_MAX_TOOL_ROUNDS)
    return result.text
