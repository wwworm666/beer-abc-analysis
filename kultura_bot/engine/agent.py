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

Запрос идёт потоком (client.beta.messages.stream, итог — get_final_message): на xhigh шаг
бывает долгим, а поток не упирается в таймаут HTTP.

- model, effort, max_tokens — kultura_bot/settings.py; думает модель всегда (adaptive),
  рассуждения не показываются (display по умолчанию);
- speed="fast" — быстрый режим (settings.FAST_MODE): вывод до 2,5 раза быстрее, цена × 2;
  не ответил (429, сбой, отказ именно в нём) — тот же шаг на обычной скорости, и
  settings.FAST_COOLDOWN_S быстрый режим не просится (fast_mode_on);
- инструменты — kultura_bot/engine/tools.py (поиск по описаниям + отложенная загрузка);
- кэш: системный промпт — явная точка кэша, хвост разговора — автоматическая
  (cache_control верхнего уровня); повторные запросы диалога читают начало из кэша;
- context editing: когда контекст больше settings.CONTEXT_CLEAR_AT_TOKENS, Anthropic
  вычищает старые ответы инструментов (кроме результатов поиска инструментов) — не меньше
  settings.CONTEXT_CLEAR_AT_LEAST_TOKENS за раз: каждая чистка заново пишет разговор в кэш,
  поэтому она редкая и крупная;
- fallbacks="default": отказ модели по правилам безопасности (ложное срабатывание) —
  ответ запасной модели в том же запросе (settings.REFUSAL_FALLBACK);
- thinking.block_binding = drop_block: если начало разговора всё же разошлось с тем, к
  чему привязаны рассуждения, Claude отбрасывает их, а не отвечает ошибкой.

## Необязательные возможности

fallbacks, context editing и block_binding — бета-параметры API. Если Anthropic отвергнет
какой-то из них (400 с его именем в тексте ошибки), бот один раз повторяет запрос без
этой возможности и до перезапуска процесса больше её не шлёт (OPTIONAL_FEATURES,
_disabled) — бот отвечает, а в журнале остаётся предупреждение.

## Смена модели посреди ответа (fallbacks)

Отказ основной модели посреди вывода: в потоке остаётся её начало, затем блок fallback и
ответ запасной модели. В историю и на исполнение идёт то, что разрешает документация
Anthropic («Echoing fallback turns back»): до последнего блока fallback — только текст и
парные блоки серверных инструментов; рассуждения и вызовы инструментов отказавшей модели
не исполняются и назад не отправляются (after_fallback).

## Пределы

- settings.MAX_TOOL_ROUNDS шагов с инструментами на вопрос (агенту —
  AGENT_MAX_TOOL_ROUNDS): исчерпаны — последний запрос с tool_choice none, модель
  отвечает тем, что уже узнала;
- дневной расход settings.DAILY_BUDGET_USD: перед каждым шагом сверяется со своей базой
  сервера бота (store.usage); исчерпан — BudgetExceeded (бот отвечает «лимит на сегодня»);
  расход каждого шага пишется туда же и уходит сайту в отчёте (on_usage);
- расход вопроса settings.QUESTION_BUDGET_USD (отчёта — REPORT_BUDGET_USD, Spend.limit) — бот
  и его агенты вместе (Spend в ToolContext): дошёл — к результатам инструментов добавляется
  QUESTION_BUDGET_NOTE, и следующий запрос идёт без инструментов (модель отвечает тем, что
  уже узнала);
- pause_turn (серверный инструмент не уложился в шаг) — запрос повторяется как есть;
- шаг оборвался на пределе длины посреди вызова инструмента — вызов не выполняется (в истории
  на него — ответ-ошибка, чтобы история осталась корректной), последний запрос без инструментов.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from kultura_bot import settings
from kultura_bot.engine import claude, tools

log = logging.getLogger('kultura-bot')

BETA_CONTEXT = 'context-management-2025-06-27'
BETA_THINKING_BINDING = 'thinking-binding-controls-2026-08-01'
BETA_FALLBACK = 'server-side-fallback-2026-07-01'
# Быстрый режим Opus 5.5 беты не требует, а Opus 5 и Opus 4.8 — требуют: они запасные модели
# (fallbacks), и запрос с speed="fast" должен быть верным и для них.
BETA_FAST = 'fast-mode-2026-02-01'
MAX_PAUSE_RESUMES = 5            # подряд pause_turn без нового содержания — хватит
QUESTION_BUDGET_NOTE = ('Предел расхода на этот вопрос (${limit:.2f}) исчерпан: больше не вызывай инструменты — '
                        'ответь тем, что уже знаешь, и коротко скажи, что не успел проверить.')
REPORT_FINISH_OVER = ('Шаги на отправку отчёта кончились: ответь текстом в виде отчёта (заголовок-вывод, выжимка, '
                      'разделы) — бот сам соберёт из него страницу.')
FAST_WORDS = ('speed', 'fast mode', 'fast-mode', 'fast_mode')     # отказ именно в быстром режиме

# Необязательные возможности: имя -> слова в тексте ошибки 400, по которым её узнать.
OPTIONAL_FEATURES = {
    'fallbacks': ('fallbacks', 'server-side-fallback'),
    'context_management': ('context_management', 'clear_tool_uses', 'exclude_tools', 'context-management'),
    'block_binding': ('block_binding', 'thinking-binding', 'prefix_mismatch'),
}
_disabled = set()                # отвергнутые API возможности (до перезапуска процесса)
_fast_paused_until = 0.0         # быстрый режим не ответил — до этого времени обычная скорость


def fast_mode_on(now: Optional[float] = None) -> bool:
    """Просить ли быстрый режим: включён в настройках и не на паузе после сбоя."""
    return settings.FAST_MODE and (time.time() if now is None else now) >= _fast_paused_until


def pause_fast_mode(reason: str, now: Optional[float] = None) -> None:
    global _fast_paused_until
    _fast_paused_until = (time.time() if now is None else now) + settings.FAST_COOLDOWN_S
    log.warning('[BOT] быстрый режим не ответил (%s) — %d мин на обычной скорости', reason,
                settings.FAST_COOLDOWN_S // 60)


class BudgetExceeded(Exception):
    """Дневной предел расхода исчерпан."""


@dataclass
class Spend:
    """Расход одного вопроса: бот и его агенты вместе (ToolContext.spend)."""
    usd: float = 0.0
    steps: int = 0                             # запросов к модели
    limit: Optional[float] = None              # предел на вопрос; None — settings.QUESTION_BUDGET_USD
                                               # (у отчёта — settings.REPORT_BUDGET_USD)

    def budget(self) -> float:
        return settings.QUESTION_BUDGET_USD if self.limit is None else self.limit


@dataclass
class TurnResult:
    text: str                                  # ответ для человека (Markdown)
    messages: List[Dict[str, Any]]             # история после вопроса (дописанная)
    stop_reason: str = ''
    rounds: int = 0
    cost_usd: float = 0.0
    notes: List[str] = field(default_factory=list)   # max_rounds | max_tokens | max_tokens_tool | refusal |
    #                                                  question_budget | report_finish


def request_params(*, model: str, effort: str, system_text: str, tool_list: List[Dict[str, Any]],
                   messages: List[Dict[str, Any]], final: bool = False) -> Dict[str, Any]:
    """Параметры client.beta.messages.stream (отдельно — для тестов и отладки)."""
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
            'clear_at_least': {'type': 'input_tokens', 'value': settings.CONTEXT_CLEAR_AT_LEAST_TOKENS},
            'exclude_tools': [tools.SEARCH_TOOL['name']],
        }]}
        betas.append(BETA_CONTEXT)
    if settings.REFUSAL_FALLBACK and 'fallbacks' not in _disabled:
        params['fallbacks'] = 'default'
        betas.append(BETA_FALLBACK)
    if fast_mode_on():
        params['speed'] = 'fast'
        betas.append(BETA_FAST)
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


def fast_failure(exc: BaseException) -> bool:
    """Быстрый режим не дал ответа: нет мощности или сбой (429, 5xx, 529, обрыв связи) либо
    отказ именно в нём (400/403 со словом speed / fast mode)."""
    import anthropic
    if isinstance(exc, anthropic.APIConnectionError):
        return True
    if not isinstance(exc, anthropic.APIStatusError):
        return False
    status = claude.api_status(exc)
    if status == 429 or status >= 500:
        return True
    message = str(getattr(exc, 'message', '') or exc).lower()
    return status in (400, 403) and any(word in message for word in FAST_WORDS)


def send(client: Any, params: Dict[str, Any]):
    """Один запрос потоком; вернуть итоговое сообщение (как у messages.create)."""
    with client.beta.messages.stream(**params) as stream:
        return stream.get_final_message()


def create_message(client: Any, build: Callable[[], Dict[str, Any]]):
    """Запрос к Claude. Отвергнутую необязательную возможность — выключить и повторить;
    быстрый режим не ответил — тот же запрос на обычной скорости (pause_fast_mode)."""
    while True:
        params = build()
        fast = params.get('speed') == 'fast'
        try:
            # Быстрый запрос — без повторов SDK: нет мощности — сразу обычная скорость, а не
            # ожидание (документация fast mode, «Falling back to standard speed»).
            return send(client.with_options(max_retries=0) if fast else client, params)
        except Exception as exc:  # noqa: BLE001 — разбор ниже, остальное — наверх как есть
            if fast and fast_failure(exc):
                status = f' {claude.api_status(exc)}' if hasattr(exc, 'status_code') else ''
                pause_fast_mode(type(exc).__name__ + status)
                continue
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


def after_fallback(content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Блоки ответа для истории и исполнения, если посреди вывода сменилась модель.

    До последнего блока fallback остаются только текст и парные блоки серверных инструментов
    (server_tool_use с его результатом); рассуждения, вызовы инструментов и прочие блоки
    отказавшей модели отбрасываются. Блок fallback и всё после него — как есть."""
    last = max((i for i, b in enumerate(content) if b.get('type') == 'fallback'), default=-1)
    if last <= 0:
        return content
    before = content[:last]
    results = {b.get('tool_use_id') for b in before if str(b.get('type') or '').endswith('_tool_result')}
    paired = {b.get('id') for b in before if b.get('type') == 'server_tool_use' and b.get('id') in results}
    kept = [b for b in before if b.get('type') == 'text'
            or (b.get('type') == 'server_tool_use' and b.get('id') in paired)
            or (str(b.get('type') or '').endswith('_tool_result') and b.get('tool_use_id') in paired)]
    return kept + content[last:]


def _texts(content: List[Dict[str, Any]]) -> str:
    return '\n\n'.join(b.get('text', '').strip() for b in content if b.get('type') == 'text' and
                       (b.get('text') or '').strip())


def check_budget(store) -> None:
    limit = settings.DAILY_BUDGET_USD
    spent = store.spent_on()
    if limit and spent >= limit:
        raise BudgetExceeded(f'Дневной предел расхода на Claude исчерпан: {spent:.2f} $ из {limit:.2f} $ '
                             f'(DAILY_BUDGET_USD в kultura_bot/settings.py). Бот снова ответит после полуночи МСК.')


UsageHook = Callable[[str, Dict[str, int], float], None]


def _finishing_report(ctx: tools.ToolContext) -> bool:
    """Режим отчёта у бота, страница ещё не ушла и шаги «только отчёт» не начаты: предел
    исчерпан — не «ответь текстом», а «отправь отчёт с тем, что есть»."""
    return ctx.report_mode and not ctx.is_agent and not ctx.report_only and not ctx.reports_sent


def run_turn(client: Any, *, system_text: str, tool_list: List[Dict[str, Any]], history: List[Dict[str, Any]],
             user_content: List[Dict[str, Any]], ctx: tools.ToolContext, store, model: Optional[str] = None,
             effort: Optional[str] = None, max_rounds: Optional[int] = None,
             on_step: Optional[Callable[[], None]] = None, on_usage: Optional[UsageHook] = None) -> TurnResult:
    """Ответить на один вопрос. Ошибки API (anthropic.*Error) и BudgetExceeded — наверх.

    store — своя база сервера бота (engine/store.py): дневной предел и расход; on_usage —
    расход шага для отчёта сайту."""
    model = model or settings.MODEL
    effort = effort or settings.EFFORT
    max_rounds = settings.MAX_TOOL_ROUNDS if max_rounds is None else max_rounds
    spend = ctx.spend if ctx.spend is not None else Spend()
    messages = list(history) + [{'role': 'user', 'content': user_content}]
    result = TurnResult(text='', messages=messages)
    final_texts: List[str] = []
    pauses = 0
    final = False
    finish_left = -1          # режим отчёта, предел исчерпан: сколько ещё шагов «только отчёт» (-1 — не начаты)
    while True:
        check_budget(store)
        response = create_message(client, lambda: request_params(
            model=model, effort=effort, system_text=system_text, tool_list=tool_list, messages=messages,
            final=final))
        usage = _usage_dict(response.usage)
        served_by = getattr(response, 'model', None) or model
        cost = claude.cost_usd(served_by, usage, speed=getattr(response.usage, 'speed', None))
        result.cost_usd += cost
        spend.usd += cost
        spend.steps += 1
        try:
            store.add_usage(served_by, usage, cost)
            if on_usage is not None:
                on_usage(served_by, usage, cost)
        except Exception:  # noqa: BLE001 — учёт не должен ронять ответ
            log.exception('[BOT] не удалось записать расход')
        content = after_fallback([_block_dict(b) for b in response.content])
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
        tool_uses = [b for b in content if b.get('type') == 'tool_use']
        if response.stop_reason != 'tool_use':
            if tool_uses:
                # Шаг оборвался на вызове инструмента (предел длины, отказ): вызов не выполняется,
                # но на каждый tool_use в истории должен быть tool_result, иначе следующий запрос
                # диалога Claude отклонит (400).
                messages.append({'role': 'user', 'content': [
                    tools.tool_result(b['id'], 'Вызов не выполнен: ответ модели оборвался на пределе длины. '
                                                'Ответь тем, что уже знаешь, и скажи, что не успел.', is_error=True)
                    for b in tool_uses]})
                if response.stop_reason == 'max_tokens' and not final:
                    result.notes.append('max_tokens_tool')
                    final = True                       # последний запрос — без инструментов, ответ текстом
                    continue
            if response.stop_reason == 'max_tokens':
                result.notes.append('max_tokens')
            elif response.stop_reason == 'refusal':
                result.notes.append('refusal')
            break
        if not tool_uses:
            break
        result.rounds += 1
        if finish_left == 0:
            # Режим отчёта: и шаги на отправку отчёта кончились — последний запрос без инструментов,
            # из текста страницу соберёт сервер бота (service.finish_report).
            result.notes.append('report_finish')
            messages.append({'role': 'user', 'content': [
                tools.tool_result(b['id'], REPORT_FINISH_OVER, is_error=True) for b in tool_uses]})
            final = True
            continue
        if finish_left > 0:
            finish_left -= 1
        elif result.rounds > max_rounds:
            result.notes.append('max_rounds')
            if _finishing_report(ctx):
                # Режим отчёта: не «ответь текстом», а ещё REPORT_FINISH_ROUNDS шагов (этот — первый),
                # где можно только отправить отчёт (tools.execute отказывает остальным).
                ctx.report_only = True
                finish_left = settings.REPORT_FINISH_ROUNDS - 1
            else:
                # Шаги кончились: на каждый вызов — отказ, затем последний запрос без инструментов.
                messages.append({'role': 'user', 'content': [
                    tools.tool_result(b['id'], 'Лимит шагов на этот вопрос исчерпан: ответь тем, что уже знаешь, и '
                                                'скажи, чего не успел проверить.', is_error=True) for b in tool_uses]})
                final = True
                continue
        sent_before = len(ctx.charts_sent) + len(ctx.reports_sent)
        results = [tools.execute(b, ctx) for b in tool_uses]
        if not ctx.is_agent and len(ctx.charts_sent) + len(ctx.reports_sent) > sent_before:
            # Карточка (график с подписью-ответом или отчёт) ушла — она и есть ответ: текст до неё
            # («Посмотрю выручку…») вторым сообщением не отправляется. Текст после неё — да.
            final_texts = []
        limit = spend.budget()
        if limit and spend.usd >= limit and not final and finish_left < 0:
            result.notes.append('question_budget')
            if _finishing_report(ctx):
                # Режим отчёта: данные больше не запрашиваются, но отчёт отправить можно —
                # REPORT_FINISH_ROUNDS шагов «только отчёт».
                ctx.report_only = True
                finish_left = settings.REPORT_FINISH_ROUNDS
                results.append({'type': 'text', 'text': tools.REPORT_ONLY_TEXT})
            else:
                # Вопрос разросся: следующий запрос — без инструментов, ответ тем, что уже есть.
                # Текст — в том же сообщении после результатов (история только дописывается).
                results.append({'type': 'text', 'text': QUESTION_BUDGET_NOTE.format(limit=limit)})
                final = True
        messages.append({'role': 'user', 'content': results})

    result.text = '\n\n'.join(final_texts).strip()
    if 'refusal' in result.notes and not result.text:
        result.text = 'Модель отказалась отвечать на этот вопрос (правила безопасности Anthropic). Переформулируйте его.'
    if 'max_tokens' in result.notes:
        result.text = (result.text + '\n\n(ответ обрезан: модель упёрлась в предел длины)').strip()
    return result


def run_agent(client: Any, persona: tools.Persona, task: str, *, parent: tools.ToolContext, store,
              header: str = '', on_usage: Optional[UsageHook] = None) -> str:
    """Поручение агенту: отдельный разговор с его инструкциями и инструментами. Вернуть отчёт."""
    ctx = tools.ToolContext(site=parent.site, chat_id=parent.chat_id, allowed=persona.toolset.names,
                            is_agent=True, charts_sent=parent.charts_sent, reports_sent=parent.reports_sent,
                            spend=parent.spend, report_mode=parent.report_mode)
    text = (header + '\n' if header else '') + task
    result = run_turn(client, system_text=persona.system, tool_list=persona.toolset.defs, history=[],
                      user_content=[{'type': 'text', 'text': text}], ctx=ctx, store=store,
                      effort=settings.AGENT_EFFORT, max_rounds=settings.AGENT_MAX_TOOL_ROUNDS, on_usage=on_usage)
    return result.text
