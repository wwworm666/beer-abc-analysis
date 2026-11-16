"""OpenAI Responses → контракт шагов существующего движка.

История остаётся append-only. В блоке provider_state версии 1 храним исходные
output items (reasoning, tool search, compaction, call IDs) для stateless Responses.
Текст и tool_use рядом — представление для общего исполнителя/старого адаптера.
Старые Anthropic messages переводим без thinking signatures и серверного поиска.
Все функции исполняет только tools.execute: Responses не получает удалённый MCP.
"""
import json
import threading
from types import SimpleNamespace

from kultura_bot import settings
from kultura_bot.engine import claude

_clients = {}
_lock = threading.Lock()


def make_client(key, *, timeout=claude.REQUEST_TIMEOUT_S, max_retries=claude.MAX_RETRIES):
    from openai import OpenAI
    return OpenAI(api_key=key, timeout=timeout, max_retries=max_retries)


def client_for(key):
    with _lock:
        if key not in _clients:
            _clients.clear()
            _clients[key] = make_client(key)
        return _clients[key]


class ResponseError(RuntimeError):
    """Ошибка внутри потока/незавершённый ответ: никакие действия не исполняются."""


def describe_error(exc, secrets=()):
    import openai
    if isinstance(exc, openai.APIStatusError):
        code = exc.status_code
        body = exc.body if isinstance(exc.body, dict) else {}
        nested = body.get('error') if isinstance(body.get('error'), dict) else {}
        error_code = body.get('code') or nested.get('code', '')
        if code == 401:
            kind, text = 'auth', 'OpenAI не принял ключ API. Замените ключ OpenAI на странице «Доступ агентов».'
        elif code == 402 or error_code in ('insufficient_quota', 'billing_hard_limit_reached'):
            kind, text = 'billing', 'Недостаточно средств или исчерпан лимит проекта OpenAI. Проверьте Billing.'
        elif code in (403, 404):
            kind, text = 'denied', 'У проекта OpenAI нет доступа к GPT-6 Astra. Проверьте доступ к модели.'
        elif code == 429:
            kind, text = 'rate', 'OpenAI ограничил частоту запросов. Повторите через минуту.'
        elif code >= 500:
            kind, text = 'server', 'Сбой на стороне OpenAI. Повторите через пару минут.'
        else:
            # Не включаем тело API: оно может содержать весь запрос и данные пользователя.
            kind, text = 'bad_request', f'OpenAI отклонил запрос ({code}). Действия этого шага не выполнены.'
    elif isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        kind, text = 'offline', 'Нет связи с OpenAI. Повторите через минуту.'
    elif isinstance(exc, ResponseError):
        kind, text = 'server', str(exc)
    else:
        kind, text = 'other', f'{type(exc).__name__}: {exc}'
    return kind, claude.scrub(text, secrets)


def check_key(key, model):
    try:
        with make_client(key, timeout=claude.CHECK_TIMEOUT_S, max_retries=0) as client:
            return 'ok', client.models.retrieve(model).id
    except Exception as exc:
        return describe_error(exc, (key,))


def tool_defs(definitions):
    result = []
    for tool in definitions:
        if str(tool.get('type', '')).startswith('tool_search_'):
            result.append({'type': 'tool_search', 'execution': 'server'})
            continue
        if tool['name'] in settings.HIDDEN_TOOLS:
            continue
        item = {'type': 'function', 'name': tool['name'], 'description': tool.get('description', ''),
                'parameters': tool['input_schema'], 'strict': False}
        if tool.get('defer_loading'):
            item['defer_loading'] = True
        result.append(item)
    return result


def _input_block(block):
    kind = block.get('type')
    if kind == 'text':
        return {'type': 'input_text', 'text': block.get('text') or '(пустой ответ)'}
    source = block.get('source') or {}
    if kind in ('image', 'document'):
        if source.get('type') == 'base64':
            url = f'data:{source.get("media_type", "application/octet-stream")};base64,{source.get("data", "")}'
        elif source.get('type') == 'url':
            url = source['url']
        elif kind == 'document' and source.get('type') == 'text':
            return {'type': 'input_text', 'text': source.get('data') or '(пустой документ)'}
        else:
            raise ValueError('Неподдерживаемый формат вложения')
        if kind == 'image':
            return {'type': 'input_image', 'image_url': url}
        if source.get('type') == 'url':
            return {'type': 'input_file', 'file_url': url}
        return {'type': 'input_file', 'filename': 'attachment.pdf', 'file_data': url}
    return None


def input_items(messages):
    """Сохранить порядок calls/results и opaque output; чужие подписи не отправлять."""
    items = []
    for message in messages:
        role = message['role']
        blocks = message.get('content') or []
        if isinstance(blocks, str):
            blocks = [{'type': 'text', 'text': blocks}]
        state = next((b for b in blocks if b.get('type') == 'provider_state'
                      and b.get('provider') == 'openai'), None)
        if role == 'assistant' and state is not None:
            if state.get('version') != 1:
                raise ValueError('Неизвестная версия истории OpenAI')
            items.extend(state['output'])
            continue
        pending = []

        def flush():
            if pending:
                items.append({'role': role, 'content': list(pending)})
                pending.clear()

        for block in blocks:
            kind = block.get('type')
            if kind == 'tool_use':
                flush()
                items.append({'type': 'function_call', 'call_id': block['id'], 'name': block['name'],
                              'arguments': json.dumps(block['input'], ensure_ascii=False)})
            elif kind == 'tool_result':
                flush()
                content = block.get('content') or []
                if isinstance(content, str):
                    content = [{'type': 'text', 'text': content}]
                output = [part for b in content if (part := _input_block(b)) is not None]
                if block.get('is_error'):
                    output.insert(0, {'type': 'input_text', 'text': 'Ошибка инструмента:'})
                items.append({'type': 'function_call_output', 'call_id': block['tool_use_id'],
                              'output': output or [{'type': 'input_text', 'text': '(пустой ответ)'}]})
            elif role == 'assistant' and kind == 'text':
                pending.append({'type': 'output_text', 'text': block.get('text', ''), 'annotations': []})
            elif role == 'user':
                part = _input_block(block)
                if part is not None:
                    pending.append(part)
        flush()
    # API позволяет отбросить префикс до последней compaction, сохранив сам opaque item.
    last = max((i for i, item in enumerate(items) if item.get('type') == 'compaction'), default=0)
    return items[last:]


def request_params(params):
    instructions = '\n\n'.join(b['text'] for b in params['system'])
    # Каталог/fingerprint остаются прежними, меняется только провайдерная инструкция.
    instructions = instructions.replace(
        'tool_search_tool_regex: шаблон — регулярное выражение Python, регистр не важен, ищет по\n'
        'имени, описанию и параметрам.',
        'tool_search: находи нужные функции по их назначению и схеме поиска, предоставленной API.')
    instructions = instructions.replace(
        'tool_search_tool_regex (регулярное выражение\n  Python, регистр не важен; имена начинаются с раздела — смотри ниже)',
        'tool_search (используй схему поиска, предоставленную API; имена начинаются с раздела)')
    instructions = instructions.replace(
        'Ищи по корням русских слов и по разделу: «выручк|продаж», «смен|график», «остат»,\n'
        '«заказ», «кег|кран», «зарплат|kpi», «^staff_.*shift». Не нашлось — попробуй другие корни\n'
        'или шире; найденные инструменты остаются доступны до конца разговора.',
        'Ищи по задаче и разделу: продажи, смены, остатки, заказы, кеги, зарплата. '
        'Не нашлось — уточни назначение инструмента; найденные функции доступны дальше в разговоре.')
    result = {
        'model': params['model'], 'instructions': instructions,
        'input': input_items(params['messages']),
        'tools': tool_defs(params['tools']),
        'reasoning': {'effort': params['output_config']['effort']},
        'max_output_tokens': params['max_tokens'], 'store': False,
        'include': ['reasoning.encrypted_content'],
        'context_management': [{'type': 'compaction', 'compact_threshold': settings.OPENAI_COMPACT_AT_TOKENS}],
    }
    if params.get('tool_choice', {}).get('type') == 'none':
        result['tool_choice'] = 'none'
    if params.get('speed') == 'fast':
        result['service_tier'] = 'fast'
    return result


def normalize(response, definitions=()):
    raw = response.model_dump(mode='json', exclude_none=True) if hasattr(response, 'model_dump') else response
    if raw.get('status') not in ('completed', 'incomplete'):
        raise ResponseError('OpenAI не завершил ответ. Действия этого шага не выполнены.')
    output = list(raw.get('output') or [])
    searches = [item for item in output if item.get('type') == 'tool_search_call'
                and item.get('execution') == 'client']
    if searches:
        raise ResponseError('OpenAI запросил клиентский поиск вместо настроенного серверного.')
    content = [{'type': 'provider_state', 'provider': 'openai', 'version': 1, 'output': output}]
    calls, refused, truncated = False, False, False
    seen_calls = set()
    for item in output:
        if item['type'] == 'message':
            for block in item.get('content', []):
                if block['type'] == 'output_text':
                    content.append({'type': 'text', 'text': block['text']})
                elif block['type'] == 'refusal':
                    refused = True
                    content.append({'type': 'text', 'text': block.get('refusal', '')})
        elif item['type'] == 'function_call':
            if not item.get('call_id') or item['call_id'] in seen_calls:
                raise ResponseError('OpenAI вернул повторный или пустой идентификатор вызова. Действия не выполнены.')
            seen_calls.add(item['call_id'])
            truncated = truncated or item.get('status') == 'incomplete'
            calls = True
            try:
                arguments = json.loads(item['arguments'])
            except (ValueError, TypeError):
                arguments = None     # tools.execute вернёт ошибку, не вызовет сайт
            content.append({'type': 'tool_use', 'id': item['call_id'], 'name': item['name'], 'input': arguments})
    stop = 'refusal' if refused else ('tool_use' if calls else 'end_turn')
    if not calls and not refused and (any(item.get('type') == 'tool_search_output' for item in output)
            or (not any(b['type'] == 'text' for b in content)
                and any(item.get('type') == 'compaction' for item in output))):
        stop = 'pause_turn'
    if truncated:
        stop = 'max_tokens'
    if raw.get('status') == 'incomplete':
        reason = (raw.get('incomplete_details') or {}).get('reason')
        stop = 'max_tokens' if reason == 'max_output_tokens' else 'refusal'
    usage = raw.get('usage') or {}
    details = usage.get('input_tokens_details') or {}
    cached = int(details.get('cached_tokens') or 0)
    written = int(details.get('cache_write_tokens') or 0)
    total_in = int(usage.get('input_tokens') or 0)
    if total_in < cached + written:
        raise ResponseError('OpenAI вернул некорректный учёт токенов.')
    # Общий движок хранит НЕпересекающиеся категории, Responses — суммарный input.
    stats = SimpleNamespace(input_tokens=total_in - cached - written,
                            output_tokens=int(usage.get('output_tokens') or 0),
                            cache_read_input_tokens=cached, cache_creation_input_tokens=written,
                            speed='fast' if raw.get('service_tier') in ('fast', 'priority') else 'standard')
    return SimpleNamespace(content=content, stop_reason=stop, model=raw.get('model'), usage=stats)


def create_message(client, build):
    from openai import APIConnectionError, APIStatusError
    from kultura_bot.engine import agent
    while True:
        source = build()
        params = request_params(source)
        fast = params.get('service_tier') == 'fast'
        try:
            sdk = client.with_options(max_retries=0) if fast else client
            with sdk.responses.stream(**params) as stream:
                return normalize(stream.get_final_response(), source['tools'])
        except (APIConnectionError, APIStatusError) as exc:
            status = getattr(exc, 'status_code', 0)
            rejected_fast = status in (400, 403) and any(
                word in str(exc).lower() for word in ('service_tier', 'fast', 'priority'))
            if fast and (isinstance(exc, APIConnectionError) or status == 429 or status >= 500 or rejected_fast):
                agent.pause_fast_mode(type(exc).__name__)
                continue
            raise


def cost_usd(usage, speed=None):
    """Astra: $10/$50, cache read $1, write $12.50 за M; длинный вход >272K: ×2/×1.5."""
    normal = usage.get('input_tokens', 0)
    cached = usage.get('cache_read_input_tokens', 0)
    written = usage.get('cache_creation_input_tokens', 0)
    long = normal + cached + written > 272_000
    cost = (normal * 10 + cached + written * 12.5) * (2 if long else 1)
    cost += usage.get('output_tokens', 0) * 50 * (1.5 if long else 1)
    return round(cost * (2 if speed == 'fast' else 1) / 1_000_000, 6)
