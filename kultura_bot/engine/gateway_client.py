"""ClaudeHub adapter for the existing billed, cancellable MCP/agent loop.

Only discovery is local. Actual tools still go through tools.execute (permissions,
reports, web/Telegram delivery). Client owns no per-conversation mutable state.
"""
import json
import threading
import time
from types import SimpleNamespace

import requests

from kultura_bot.engine import gateway, claude

_catalogue = None
_catalogue_at = 0.0
_lock = threading.Lock()
_request_lock = threading.Lock()
_last_request = 0.0


def catalogue():
    global _catalogue, _catalogue_at
    with _lock:
        if _catalogue is None or time.monotonic() - _catalogue_at > 300:
            response = requests.get(gateway.OPENAI_URL + '/models', timeout=20)
            response.raise_for_status()
            _catalogue = gateway.validate_response(response.json())
            _catalogue_at = time.monotonic()
        return _catalogue


class Client:
    def __init__(self, key, model):
        self.key = key
        self.model = model
        self.rates = gateway.prices_from_catalogue(model, catalogue())


class GatewayError(RuntimeError):
    pass


def cost(usage, rates):
    fields = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')
    return round(sum(usage.get(k, 0) * price for k, price in zip(fields, rates)) / 1_000_000, 6)


def chat_messages(messages):
    result = []
    for message in messages:
        blocks = message.get('content') or []
        if isinstance(blocks, str):
            blocks = [{'type': 'text', 'text': blocks}]
        if message['role'] == 'assistant':
            text = '\n'.join(b['text'] for b in blocks if b.get('type') == 'text')
            calls = [{'id': b['id'], 'type': 'function', 'function': {
                'name': b['name'], 'arguments': json.dumps(b['input'], ensure_ascii=False)}}
                for b in blocks if b.get('type') == 'tool_use']
            if text or calls:
                result.append({'role': 'assistant', 'content': text or None,
                               **({'tool_calls': calls} if calls else {})})
            continue
        pending = []
        for b in blocks:
            if b.get('type') == 'tool_result':
                if pending:
                    result.append({'role': 'user', 'content': pending}); pending = []
                result.append({'role': 'tool', 'tool_call_id': b['tool_use_id'],
                               'content': json.dumps(b.get('content') or [], ensure_ascii=False)})
            elif b.get('type') == 'text':
                pending.append({'type': 'text', 'text': b['text']})
            elif b.get('type') in ('image', 'document'):
                src = b.get('source') or {}
                if src.get('type') == 'text':
                    pending.append({'type': 'text', 'text': src.get('data', '')})
                elif src.get('type') == 'base64':
                    data = 'data:' + src['media_type'] + ';base64,' + src['data']
                    pending.append({'type': 'image_url', 'image_url': {'url': data}} if b['type'] == 'image'
                                   else {'type': 'file', 'file': {'filename': 'attachment.pdf', 'file_data': data}})
                elif src.get('type') == 'url' and b['type'] == 'image':
                    pending.append({'type': 'image_url', 'image_url': {'url': src['url']}})
                else:
                    raise GatewayError('Неподдерживаемое вложение для этой модели.')
        if pending:
            result.append({'role': 'user', 'content': pending})
    return result


def native_messages(messages, model=None):
    # Only canonical blocks: never replay Responses opaque state to Anthropic.
    result = []
    live_calls = set()
    for m in messages:
        blocks = m.get('content') or []
        if isinstance(blocks, str):
            blocks = [{'type': 'text', 'text': blocks}]
        state = next((b for b in blocks if b.get('type') == 'provider_state' and b.get('provider') == 'claudehub' and b.get('model') == model), None)
        if m['role'] == 'assistant' and state is not None:
            result.append({'role': 'assistant', 'content': state['content']})
            live_calls.update(b['id'] for b in state['content'] if b.get('type') == 'tool_use')
            continue
        blocks = [b for b in blocks if b.get('type') in ('text', 'image', 'document', 'tool_use', 'tool_result')]
        safe = []
        for block in blocks:
            if block.get('type') == 'tool_use' or (block.get('type') == 'tool_result' and block.get('tool_use_id') not in live_calls):
                safe.append({'type': 'text', 'text': 'Предыдущий шаг разговора: ' + json.dumps(block, ensure_ascii=False)})
            else:
                safe.append(block)
        if safe:
            result.append({'role': m['role'], 'content': safe})
    return result


def create_message(client, build, discovery):
    params = build()
    instructions = '\n\n'.join(b['text'] for b in params['system'])
    instructions = instructions.replace('tool_search_tool_regex', 'kultura_find_tools')
    instructions = instructions.replace('шаблон — регулярное выражение Python, регистр не важен, ищет по',
                                        'запрос — слова или основы слов через пробел (ИЛИ), ищет по')
    instructions = instructions.replace('регулярное выражение\n  Python, регистр не важен;',
                                        'слова или основы слов через пробел (ИЛИ);')
    instructions += ('\nПоиск kultura_find_tools выполняется в сервисе, regex не используется. '
                     'Выдача по 100 совпадений: next_offset передавай как offset для следующей страницы. '
                     'Найденные функции доступны на следующем шаге; для старой функции можно повторить поиск по имени.\n')
    native = gateway.connection(params['model']).protocol == 'anthropic'
    functions = discovery.chat_tools()
    none = params.get('tool_choice', {}).get('type') == 'none'
    if native:
        body = {'model': params['model'], 'system': instructions, 'messages': native_messages(params['messages'], params['model']),
                'max_tokens': 128000, 'thinking': {'type': 'adaptive'},
                'output_config': params['output_config'],
                'tools': [{'name': t['function']['name'], 'description': t['function']['description'],
                           'input_schema': t['function']['parameters']} for t in functions]}
        if none:
            body['tool_choice'] = {'type': 'none'}
        url = gateway.ANTHROPIC_URL + '/v1/messages'
        headers = {'x-api-key': client.key, 'anthropic-version': '2023-06-01'}
    else:
        body = {'model': params['model'], 'messages': [{'role': 'system', 'content': instructions}]
                + chat_messages(params['messages']), 'tools': functions,
                'reasoning_effort': params['output_config']['effort']}
        if none:
            body['tool_choice'] = 'none'
        url = gateway.OPENAI_URL + '/chat/completions'
        headers = {'Authorization': 'Bearer ' + client.key}
    # No automatic replay after a timeout: upstream may already have billed the request.
    global _last_request
    with _request_lock:
        delay = max(0, _last_request + 2.5 - time.monotonic())
        if delay:
            time.sleep(delay)
        _last_request = time.monotonic()
    r = requests.post(url, headers=headers, json=body, timeout=600, allow_redirects=False)
    if r.status_code != 200:
        raise GatewayError('ClaudeHub отклонил запрос: HTTP ' + str(r.status_code))
    raw = gateway.validate_response(r.json(), client.key)
    u = raw.get('usage') or {}
    required_usage = ('input_tokens', 'output_tokens') if native else ('prompt_tokens', 'completion_tokens')
    if not all(k in u for k in required_usage):
        raise GatewayError('ClaudeHub не вернул учёт токенов; действия этого шага не выполнены.')
    if native:
        content = [b for b in raw.get('content', []) if b.get('type') in ('text', 'tool_use')]
        content.insert(0, {'type': 'provider_state', 'provider': 'claudehub', 'model': params['model'], 'version': 1, 'content': raw.get('content') or []})
        stop = raw.get('stop_reason')
        stats = {k: int(u.get(k) or 0) for k in ('input_tokens', 'output_tokens',
                  'cache_read_input_tokens', 'cache_creation_input_tokens')}
    else:
        choice = raw['choices'][0]; msg = choice['message']
        content = [{'type': 'text', 'text': msg['content']}] if msg.get('content') else []
        for call in msg.get('tool_calls') or []:
            try:
                args = json.loads(call['function']['arguments'])
            except (ValueError, TypeError):
                args = None
            content.append({'type': 'tool_use', 'id': call['id'], 'name': call['function']['name'], 'input': args})
        stop = {'stop': 'end_turn', 'tool_calls': 'tool_use', 'length': 'max_tokens',
                'content_filter': 'refusal'}.get(choice['finish_reason'])
        cached = int((u.get('prompt_tokens_details') or {}).get('cached_tokens') or 0)
        stats = {'input_tokens': int(u.get('prompt_tokens') or 0) - cached,
                 'output_tokens': int(u.get('completion_tokens') or 0),
                 'cache_read_input_tokens': cached, 'cache_creation_input_tokens': 0}
    if stop not in ('end_turn', 'tool_use', 'max_tokens', 'refusal') or min(stats.values()) < 0:
        raise GatewayError('ClaudeHub вернул незавершённый ответ или некорректный учёт токенов.')
    ids = [b['id'] for b in content if b['type'] == 'tool_use']
    if any(not i for i in ids) or len(ids) != len(set(ids)):
        raise GatewayError('Повторные идентификаторы инструментов; действия не выполнены.')
    return SimpleNamespace(content=content, stop_reason=stop, model=params['model'],
                           usage=SimpleNamespace(**stats, speed='standard'))
