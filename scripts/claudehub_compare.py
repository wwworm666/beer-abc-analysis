"""Eight isolated read-only model/mode evaluations; reports captured, never sent.

Run on bot host with ClaudeHub in environment. Artifacts may contain business data;
write them outside the public repository. This is not the production agent loop.
"""
import concurrent.futures
import copy
import json
import os
from pathlib import Path
import shlex
import threading
import time

import requests

from kultura_bot import settings
from kultura_bot.engine import gateway, tools
from kultura_bot.engine.local_search import Catalogue, SEARCH_NAME
from kultura_bot.engine.site import Site

QUESTION = 'У кого из барменов самый высокий план факт за последние полгода? На это влияет количество чеков или лучший реально большо продает и средний чек больше? неочевидные срезы'
REQUEST_TIMEOUT = 600
# Anthropic requires this field; maximum advertised by ClaudeHub /v1/models.
ANTHROPIC_MAX_OUTPUT = 128000


_RATE_LOCK = threading.Lock()
_LAST_REQUEST = 0.0


def send_request(url, headers, body):
    global _LAST_REQUEST
    for attempt in range(4):
        with _RATE_LOCK:
            delay = max(0, _LAST_REQUEST + 2.5 - time.monotonic())
            if delay:
                time.sleep(delay)
            _LAST_REQUEST = time.monotonic()
        response = requests.post(url, headers=headers, json=body,
                                 timeout=REQUEST_TIMEOUT, allow_redirects=False)
        if response.status_code != 429 or attempt == 3:
            return response
        time.sleep(30)


def evaluate(site, catalogue, key, model, mode, fetch):
    started = time.monotonic()
    result = {'model': model, 'mode': mode, 'effort': gateway.DEFAULT_EFFORT,
              'question': QUESTION, 'timeout_seconds': REQUEST_TIMEOUT, 'calls': [], 'usage': [], 'reports': [], 'charts': []}
    permitted = [t for t in catalogue if t.get('annotations', {}).get('readOnlyHint') is True]
    cards = [t for t in catalogue if t['name'] in (tools.REPORT_TOOL, tools.CHART_TOOL)]
    search = Catalogue([tools.claude_tool(t, t['name'] not in settings.ALWAYS_LOADED_TOOLS)
                        for t in permitted + cards])
    prompt = Path('kultura_bot/prompts/bot.md').read_text()
    # Keep business and presentation instructions; replace only discovery syntax.
    begin, end = prompt.index('# Как найти инструмент'), prompt.index('# Что считать')
    prompt = prompt[:begin] + ('# Как найти инструмент\nОбычная функция kultura_find_tools ищет по словам '
        'или основам слов, разделённым пробелами (ИЛИ), по всему разрешённому каталогу. '
        'Не используй регулярные выражения. Найденные функции доступны на следующем шаге.\n\n') + prompt[end:]
    prompt += ('\nТЕСТОВЫЙ РЕЖИМ: вызовы common_report_send и common_chart_send сохраняют '
        'артефакт для проверки и ничего не публикуют. Не вызывай внешние отправки. '
        'Агенты в этом изолированном тесте недоступны; проведи анализ самостоятельно. '
        'Служебная дата 2026-11-17, Europe/Moscow. '
        + ('Режим: отчёт. Подготовь полный отчёт с таблицей и графиком через common_report_send.'
           if mode == 'report' else 'Режим: краткий ответ. Дай краткий вывод с цифрами.'))
    anthropic = gateway.connection(model).protocol == 'anthropic'
    messages = [{'role': 'user', 'content': QUESTION}]
    if not anthropic:
        messages.insert(0, {'role': 'system', 'content': prompt})
    seen = set()
    try:
        for step in range(settings.MAX_TOOL_ROUNDS):
            functions = search.chat_tools()
            if anthropic:
                body = {'model': model, 'system': prompt, 'messages': messages, 'max_tokens': ANTHROPIC_MAX_OUTPUT,
                        'thinking': {'type': 'adaptive'}, 'output_config': {'effort': gateway.DEFAULT_EFFORT},
                        'tools': [{'name': t['function']['name'], 'description': t['function']['description'],
                                   'input_schema': t['function']['parameters']} for t in functions]}
                url = gateway.ANTHROPIC_URL + '/v1/messages'
                headers = {'x-api-key': key, 'anthropic-version': '2023-06-01'}
            else:
                body = {'model': model, 'messages': messages, 'tools': functions,
                        'reasoning_effort': gateway.DEFAULT_EFFORT}
                url = gateway.OPENAI_URL + '/chat/completions'
                headers = {'Authorization': 'Bearer ' + key}
            r = send_request(url, headers, body)
            if r.status_code != 200:
                raise RuntimeError('Gateway HTTP ' + str(r.status_code) + ': ' + r.text[:500])
            raw = gateway.validate_response(r.json(), key)
            result['usage'].append(raw.get('usage'))
            print(json.dumps({'event': 'step', 'model': model, 'mode': mode, 'step': step + 1}, ensure_ascii=False), flush=True)
            if anthropic:
                blocks = raw.get('content') or []
                messages.append({'role': 'assistant', 'content': blocks})
                calls = [b for b in blocks if b.get('type') == 'tool_use']
                answer = '\n'.join(b.get('text', '') for b in blocks if b.get('type') == 'text')
                stop = raw.get('stop_reason')
                if stop not in ('end_turn', 'tool_use'):
                    raise RuntimeError('Incomplete response: ' + str(stop))
            else:
                choice = raw['choices'][0]
                m = choice['message']
                messages.append({k: m[k] for k in ('role', 'content', 'tool_calls') if k in m})
                calls = [{'id': c['id'], 'name': c['function']['name'],
                          'input': json.loads(c['function']['arguments'])} for c in m.get('tool_calls', [])]
                answer = m.get('content') or ''
                if choice['finish_reason'] not in ('stop', 'tool_calls'):
                    raise RuntimeError('Incomplete response: ' + str(choice['finish_reason']))
            if not calls:
                result['answer'] = answer
                result['status'] = 'completed'
                break
            outputs = []
            for call in calls:
                name, args = call['name'], call['input']
                if not call['id'] or call['id'] in seen or not isinstance(args, dict):
                    raise RuntimeError('Invalid tool call')
                seen.add(call['id'])
                entry = {'name': name, 'args': args}
                if name == SEARCH_NAME:
                    out = search.search(args.get('query'))
                elif not search.can_call(name):
                    out = {'isError': True, 'error': 'Function not loaded; use kultura_find_tools'}
                elif name in (tools.REPORT_TOOL, tools.CHART_TOOL):
                    target = 'reports' if name == tools.REPORT_TOOL else 'charts'
                    result[target].append(copy.deepcopy(args))
                    out = {'captured_for_test': True, 'published': False}
                elif name in {t['name'] for t in permitted}:
                    out = fetch(name, args)
                    entry['result'] = out
                else:
                    out = {'isError': True, 'error': 'Read-only test: execution denied'}
                entry['result'] = out
                entry['ok'] = not out.get('isError')
                result['calls'].append(entry)
                text = json.dumps(out, ensure_ascii=False)
                if anthropic:
                    outputs.append({'type': 'tool_result', 'tool_use_id': call['id'], 'content': text})
                else:
                    messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': text})
            if mode == 'report' and result['reports']:
                result['status'] = 'completed'
                result['answer'] = ''
                break  # The report is the final deliverable; no extra paid request.
            if anthropic:
                messages.append({'role': 'user', 'content': outputs})
        else:
            result['status'] = 'step_limit'
    except Exception as exc:
        result['status'] = 'error'
        result['error'] = str(exc).replace(key, '[REDACTED]')[:1000]
    result['seconds'] = round(time.monotonic() - started, 1)
    return result


def main():
    for line in Path('/etc/kultura-bot.env').read_text().splitlines():
        k, sep, v = line.strip().partition('=')
        if sep and k in ('KULTURA_BOT_KEY', 'KULTURA_SITE_URL'):
            os.environ[k] = shlex.split(v)[0]
    key = gateway.api_key()
    if not key:
        raise RuntimeError('ClaudeHub missing')
    site = Site(os.environ.get('KULTURA_SITE_URL', settings.SITE_URL), os.environ['KULTURA_BOT_KEY'])
    catalogue = site.tools()
    cache, lock = {}, threading.Lock()
    def fetch(name, args):
        cache_key = json.dumps([name, args], sort_keys=True, ensure_ascii=False)
        with lock:
            if cache_key not in cache:
                cache[cache_key] = site.call_tool(name, args)
            return copy.deepcopy(cache[cache_key])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(evaluate, site, catalogue, key, model, mode, fetch)
                for model in gateway.MODELS for mode in ('answer', 'report')]
        for job in concurrent.futures.as_completed(jobs):
            print(json.dumps(job.result(), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
