import json

import pytest

from kultura_bot.engine.local_search import Catalogue, SEARCH_NAME
from scripts.claudehub_roundtrip import run


def definition(name, description='Продажи', deferred=True):
    return {'name': name, 'description': description, 'input_schema': {
        'type': 'object', 'properties': {}, 'additionalProperties': False},
        'defer_loading': deferred}


def test_search_has_no_six_result_cutoff_and_preserves_discovered_tools():
    definitions = [definition('sales_' + str(i)) for i in range(12)] + [definition('stock', 'Остатки')]
    cat = Catalogue(definitions)
    assert cat.search('продаж')['count'] == 12
    assert cat.search('остат')['count'] == 1
    assert len(cat.chat_tools()) == 14  # thirteen functions plus discovery
    assert not cat.can_call('private_tool')
    assert all(t['type'] == 'function' and 'defer_loading' not in t['function'] for t in cat.chat_tools())
    sent = cat.chat_tools()
    sent[-1]['function']['parameters']['properties']['tampered'] = {}
    assert 'tampered' not in cat.chat_tools()[-1]['function']['parameters']['properties']
    assert 'tampered' not in definitions[-1]['input_schema']['properties']


def test_literal_search_empty_catalogue_and_hidden(monkeypatch):
    monkeypatch.setattr('kultura_bot.settings.HIDDEN_TOOLS', {'secret'})
    cat = Catalogue([definition('secret'), definition('visible')])
    assert cat.search('')['count'] == 1
    assert not cat.can_call('secret')
    assert Catalogue([]).search('anything')['count'] == 0
    with pytest.raises(ValueError):
        cat.search(None)


class Site:
    def __init__(self):
        self.calls = []

    def tools(self):
        return [{'name': 'common_bars_reference', 'description': 'Locations', 'inputSchema': {
            'type': 'object', 'properties': {}, 'additionalProperties': False}}]

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {'content': [{'type': 'text', 'text': 'Test Bar'}]}


def transport(messages):
    def post(url, **kwargs):
        response = messages.pop(0)(kwargs['json'])
        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return response
        return Response()
    return post


def reply(name=None, args=None, call_id='1', text=None):
    msg = {'role': 'assistant', 'content': text}
    if name:
        msg['tool_calls'] = [{'id': call_id, 'type': 'function', 'function': {
            'name': name, 'arguments': json.dumps(args or {})}}]
    return {'choices': [{'message': msg, 'finish_reason': 'tool_calls' if name else 'stop'}]}


def test_discovery_mcp_result_and_final_answer():
    site = Site()
    def call_function(payload):
        assert any(t['function']['name'] == 'common_bars_reference' for t in payload['tools'])
        return reply('common_bars_reference', call_id='2')

    def final(payload):
        assert 'Test Bar' in payload['messages'][-1]['content']
        assert payload['messages'][-1]['tool_call_id'] == '2'
        return reply(text='Test Bar')

    result = run(site, 'fake', post=transport([
        lambda p: reply(SEARCH_NAME, {'query': 'Locations'}), call_function, final]))
    assert result['answer'] == 'Test Bar'
    assert site.calls == [('common_bars_reference', {})]


def test_text_without_mcp_is_not_success():
    with pytest.raises(RuntimeError, match='without successful MCP'):
        run(Site(), 'fake', post=transport([lambda p: reply(text='Invented Bar')]))


def test_unknown_function_never_reaches_mcp():
    site = Site()
    with pytest.raises(RuntimeError, match='not provided'):
        run(site, 'fake', post=transport([lambda p: reply('destroy_everything')]))
    assert not site.calls


@pytest.mark.parametrize('model', ['gpt-6-astra', 'gpt-6.1-sol', 'claude-opus-5-5', 'claude-fable-5-1'])
def test_comparison_uses_xhigh_and_captures_report_without_sending(monkeypatch, model):
    from scripts import claudehub_compare as compare
    calls = []
    native = model.startswith('claude-')
    def post(url, **kwargs):
        body = kwargs['json']
        assert kwargs['timeout'] == 600
        assert 'max_completion_tokens' not in body
        assert body.get('max_tokens') == (128000 if native else None)
        assert next(m['content'] for m in body['messages'] if m['role'] == 'user') == compare.QUESTION
        assert (body['output_config']['effort'] if native else body['reasoning_effort']) == 'xhigh'
        calls.append(body)
        if native:
            raw = {'stop_reason': 'tool_use' if len(calls) == 1 else 'end_turn',
                   'content': [{'type': 'tool_use', 'id': 'report1', 'name': 'common_report_send',
                                'input': {'report': {'title': 'Test'}}}] if len(calls) == 1 else []}
        else:
            raw = reply('common_report_send', {'report': {'title': 'Test'}}) if len(calls) == 1 else reply(text='')
        class Response:
            status_code = 200
            def json(self):
                return raw
        return Response()
    monkeypatch.setattr(compare.requests, 'post', post)
    catalogue = [{'name': 'common_report_send', 'description': 'план', 'inputSchema': {'type': 'object'}}]
    result = compare.evaluate(None, catalogue, 'fake', model, 'report',
                              lambda *a: pytest.fail('No MCP sends allowed'))
    assert result['status'] == 'completed'
    assert result['reports'] == [{'report': {'title': 'Test'}}]
