import json
from types import SimpleNamespace

import pytest

from kultura_bot.engine import gateway, gateway_client, providers, tools
from kultura_bot.engine.local_search import Catalogue
from test_kultura_bot import env, bot, OWNER_TG, turn  # noqa
from test_research_page import site_db, web_app, ADMIN  # noqa


def test_catalogue_replaces_fable_without_alias_to_old_model():
    assert len(gateway.choices()) == 4
    assert 'claude-fable-5-1' in gateway.MODELS
    with pytest.raises(ValueError):
        gateway.connection('claude-fable-5-2')


@pytest.mark.parametrize('model', list(gateway.MODELS))
def test_common_loop_search_then_mcp_then_answer_and_cost(env, monkeypatch, model):
    monkeypatch.setattr(gateway_client.time, 'sleep', lambda _: None)
    monkeypatch.setattr(gateway_client, 'catalogue', lambda: {'data': [dict(id=model, pricing={
        'billing_mode': 'token', 'price_input_per_1m_usd': 1, 'price_output_per_1m_usd': 2,
        'price_cache_read_per_1m_usd': .1, 'price_cache_write_per_1m_usd': 1})]})
    chosen = providers.selection({'provider': 'claudehub', 'model': model})
    client = providers.client_for('test-hub', chosen)
    native = model.startswith('claude')
    calls = []
    tool = next(t for t in env.site.tools() if t['name'].startswith('analytics_'))
    script = [('kultura_find_tools', {'query': tool['name']}), (tool['name'], {}), (None, {})]
    def post(url, **kwargs):
        p = kwargs['json'];calls.append(p)
        assert kwargs['timeout'] == 600
        assert not any(t.get('defer_loading') or t.get('type', '').startswith('tool_search') for t in p['tools'])
        if len(calls) == 2:
            names = [t['name'] if native else t['function']['name'] for t in p['tools']]
            assert tool['name'] in names
        name, args = script.pop(0)
        content = [{'type': 'tool_use', 'id': 'call'+str(len(calls)), 'name': name, 'input': args}] if name else [{'type': 'text', 'text': 'Готово'}]
        if native:
            raw = {'content': content, 'stop_reason': 'tool_use' if name else 'end_turn',
                   'usage': {'input_tokens': 100, 'output_tokens': 10}}
        else:
            msg = {'role': 'assistant', 'content': None if name else 'Готово'}
            if name:
                msg['tool_calls'] = [{'id': content[0]['id'], 'function': {'name': name, 'arguments': json.dumps(args)}}]
            raw = {'choices': [{'message': msg, 'finish_reason': 'tool_calls' if name else 'stop'}],
                   'usage': {'prompt_tokens': 100, 'completion_tokens': 10}}
        return SimpleNamespace(status_code=200, json=lambda: raw)
    monkeypatch.setattr(gateway_client.requests, 'post', post)
    result = turn(env, client, tool_list=tools.build_toolset(env.site.tools(), with_agents=False).defs)
    assert result.text == 'Готово'
    assert len(calls) == 3 and result.cost_usd == pytest.approx(.00036)
    assert any(name == tool['name'] for name, _ in env.site.calls)


def test_native_opaque_thinking_is_replayed_only_for_same_model():
    blocks = [{'type': 'thinking', 'thinking': 'opaque', 'signature': 'signed'}, {'type': 'text', 'text': 'ok'}]
    messages = [{'role': 'assistant', 'content': [{'type': 'provider_state', 'provider': 'claudehub',
                  'model': 'claude-opus-5-5', 'content': blocks}, {'type': 'text', 'text': 'ok'}]}]
    assert gateway_client.native_messages(messages, 'claude-opus-5-5')[0]['content'] == blocks
    assert gateway_client.native_messages(messages, 'claude-fable-5-1')[0]['content'] == [{'type': 'text', 'text': 'ok'}]


def test_search_pages_keep_entire_catalogue_reachable():
    defs = [{'name': 'tool_'+str(i), 'description': 'data', 'input_schema': {'type': 'object'},
             'defer_loading': True} for i in range(250)]
    cat = Catalogue(defs)
    assert cat.search('data')['next_offset'] == 100
    assert cat.search('data', 200)['count'] == 250
    assert cat.can_call('tool_249') and len(cat.chat_tools()) <= 128


def test_web_model_saved_and_returned_to_bot(site_db, monkeypatch):
    from kultura_bot import web, credentials
    monkeypatch.setattr(credentials, 'claudehub_key', lambda: 'test-key')
    q = web.ask(ADMIN, 'Вопрос', model='claude-fable-5-1')
    assert q['model'] == 'claude-fable-5-1'
    assert web.claim()['model'] == 'claude-fable-5-1'
    with pytest.raises(web.WebError):
        web.ask(ADMIN, 'Вопрос', model='claude-fable-5-2')


def test_gateway_key_does_not_fall_back_to_direct_keys():
    sel = providers.selection({'provider': 'claudehub', 'model': 'gpt-6.1-sol'})
    assert providers.api_key({'openai_key': 'direct', 'anthropic_key': 'direct'}, sel) == ''
    assert providers.api_key({'claudehub_key': 'hub'}, sel) == 'hub'


def test_telegram_selection_is_per_user_and_queue_keeps_snapshot(bot, monkeypatch):
    from test_kultura_bot import callback
    from kultura_bot.engine.service import Service
    bot.svc.config['claudehub_key'] = 'hub'
    bot.svc.handle_update(callback('model:claude-fable-5-1'))
    assert bot.env.store.get_meta('model:' + OWNER_TG) == 'claude-fable-5-1'
    bot.svc.handle_update(callback('model:claude-fable-5-2'))
    assert bot.env.store.get_meta('model:' + OWNER_TG) == 'claude-fable-5-1'
    monkeypatch.setattr(bot.svc.executor, 'submit', lambda *a: None)
    job = {'actor': {'tg_user_id': OWNER_TG}, 'text': 'test'}
    Service.enqueue(bot.svc, OWNER_TG, job)
    bot.env.store.set_meta('model:' + OWNER_TG, 'gpt-6.1-sol')
    assert job['model'] == 'claude-fable-5-1'
    assert bot.env.store.get_meta('model:another-user') is None


def test_research_selector_lists_new_four_models(web_app, monkeypatch):
    from kultura_bot import credentials
    monkeypatch.setattr(credentials, 'claudehub_key', lambda: 'secret-never-in-html')
    page = web_app.client.get('/research').get_data(as_text=True)
    assert 'id="rsModel"' in page
    assert 'secret-never-in-html' not in page
    assert 'claude-fable-5-2' not in page
    for name in gateway.MODELS:
        assert 'data-model="' + name + '"' in page
    response = web_app.client.post('/api/research/ask', json={'question': 'test', 'model': 'gpt-6.1-sol'})
    assert response.status_code in (200, 201)
    from kultura_bot import web
    assert web.claim()['model'] == 'gpt-6.1-sol'


def test_research_model_selector_in_browser(web_app, monkeypatch, tmp_path):
    import os
    if not os.path.exists('/usr/bin/chromium'):
        pytest.skip('Chromium unavailable')
    pytest.importorskip('playwright.sync_api')
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server
    import threading
    from kultura_bot import credentials, web
    monkeypatch.setattr(credentials, 'claudehub_key', lambda: 'fake-key')
    monkeypatch.setattr(web, 'engine_state', lambda now=None: {'ok': True, 'text': ''})
    server = make_server('127.0.0.1', 0, web_app.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width': 390, 'height': 844})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/research')
            page.click('#rsModelBtn')
            page.wait_for_timeout(200)
            page.screenshot(path=str(tmp_path / 'model-menu-open.png'), full_page=True)
            page.set_viewport_size({'width': 1280, 'height': 900})
            page.screenshot(path=str(tmp_path / 'model-menu-desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            page.click('[data-model="claude-fable-5-1"]')
            page.click('#rsModelBtn')
            page.keyboard.press('Escape')
            assert not page.is_visible('#rsModelMenu')
            assert page.locator('#rsModelBtn').evaluate('(el) => el === document.activeElement')
            page.reload()
            assert page.input_value('#rsModel') == 'claude-fable-5-1'
            assert page.locator('#rsFast').count() == 0
            page.fill('#rsInput', 'Тест выбора модели')
            with page.expect_response('**/api/research/ask') as response:
                page.click('#rsSend')
            assert response.value.status in (200, 201)
            assert web.claim()['model'] == 'claude-fable-5-1'
            page.wait_for_timeout(300)
            page.screenshot(path=str(tmp_path / 'model-selector-mobile.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors
            browser.close()
    finally:
        server.shutdown()


def test_switch_to_claude_preserves_foreign_calls_as_context_without_foreign_signatures():
    history = [{'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'old', 'name': 'sales', 'input': {}}]},
               {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'old', 'content': '12345'}]}]
    result = gateway_client.native_messages(history, 'claude-fable-5-1')
    assert all(b['type'] == 'text' for m in result for b in m['content'])
    assert 'sales' in str(result) and '12345' in str(result)
