"""Explicit live, read-only proof of local discovery -> MCP -> final answer.

Run on the bot host with ClaudeHub in the environment. Uses its existing MCP
credential; permits execution of common_bars_reference only. No Telegram sends.
This is a compatibility probe, not the production conversation/billing loop.
"""
import json
import os
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from kultura_bot import settings
from kultura_bot.engine import gateway, tools
from kultura_bot.engine.local_search import Catalogue, SEARCH_NAME
from kultura_bot.engine.site import Site


def run(site, key, model='gpt-6-astra', post=requests.post):
    if gateway.connection(model).protocol != 'chat_completions':
        raise ValueError('This probe uses Chat Completions')
    definitions = tools.build_toolset(site.tools(), with_agents=False).defs
    catalogue = Catalogue(definitions)
    # Initial selection deliberately uses the same search as subsequent discovery.
    selected = catalogue.search('справочник')
    ctx = tools.ToolContext(site=site, chat_id='gateway-readonly-probe',
                            allowed=frozenset({'common_bars_reference'}))
    messages = [
        {'role': 'system', 'content': 'Проверка подключения. Найди и вызови common_bars_reference, '
         'если его нет — найди через kultura_find_tools. Никакие другие MCP-функции не вызывай. '
         'По результату напиши названия баров. Не придумывай данные.'},
        {'role': 'user', 'content': 'Какие бары есть в справочнике?'},
    ]
    trace, usage, seen = [], [], set()
    for _ in range(6):  # Explicit cap on paid probe requests, not a production limit.
        payload = {'model': model, 'messages': messages, 'tools': catalogue.chat_tools(),
                   'max_completion_tokens': 1024, 'reasoning_effort': gateway.DEFAULT_EFFORT}
        response = post(gateway.OPENAI_URL + '/chat/completions', json=payload,
                        headers={'Authorization': 'Bearer ' + key}, timeout=90, allow_redirects=False)
        response.raise_for_status()
        raw = gateway.validate_response(response.json(), key)
        usage.append(raw.get('usage'))
        choice = raw['choices'][0]
        if choice.get('finish_reason') not in ('stop', 'tool_calls'):
            raise RuntimeError('Incomplete gateway response')
        message = choice['message']
        calls = message.get('tool_calls') or []
        messages.append({k: message[k] for k in ('role', 'content', 'tool_calls') if k in message})
        if not calls:
            if not any(c.get('name') == 'common_bars_reference' and c.get('ok') for c in trace):
                raise RuntimeError('Text without successful MCP execution is not a passing test')
            if not message.get('content'):
                raise RuntimeError('Empty final answer')
            return {'model': model, 'initial_matches': selected['count'], 'trace': trace,
                    'answer': message['content'], 'usage': usage}
        for call in calls:
            if not call.get('id') or call['id'] in seen:
                raise RuntimeError('Invalid or repeated call ID')
            seen.add(call['id'])
            name = call['function']['name']
            args = json.loads(call['function']['arguments'])
            if not isinstance(args, dict):
                raise RuntimeError('Function arguments must be an object')
            if name == SEARCH_NAME:
                result = catalogue.search(args.get('query'))
                trace.append({'name': name, 'matches': result['count']})
            elif catalogue.can_call(name):
                result = tools.execute({'id': call['id'], 'name': name, 'input': args}, ctx)
                trace.append({'name': name, 'ok': not result.get('is_error'), 'result': result})
            else:
                raise RuntimeError('Gateway requested a function not provided in tools')
            messages.append({'role': 'tool', 'tool_call_id': call['id'],
                             'content': json.dumps(result, ensure_ascii=False)})
    raise RuntimeError('Probe step limit reached')


if __name__ == '__main__':
    for line in Path('/etc/kultura-bot.env').read_text().splitlines():
        name, sep, value = line.strip().partition('=')
        if sep and name in ('KULTURA_BOT_KEY', 'KULTURA_SITE_URL'):
            os.environ[name] = shlex.split(value)[0]
    key = gateway.api_key()
    if not key:
        raise RuntimeError('ClaudeHub key missing')
    site = Site(os.environ.get('KULTURA_SITE_URL', settings.SITE_URL), os.environ['KULTURA_BOT_KEY'])
    print(json.dumps(run(site, key), ensure_ascii=False, indent=2))
