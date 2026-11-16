"""Контракт Responses и общие гарантии Research/Telegram. Ни одной внешней отправки."""
import copy
import json
import threading
from types import SimpleNamespace

import pytest

from kultura_bot import settings
from kultura_bot.engine import agent, astra, providers, service, tools
from test_kultura_bot import (FakeClient, FakeTelegram, OWNER_TG, bot, ctx_for, env, resp, text, turn, use)  # noqa: F401


def output_text(value):
    return {'type': 'message', 'id': 'msg_test', 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': value, 'annotations': []}]}


def call(name, args=None, call_id='call_test'):
    return {'type': 'function_call', 'id': 'fc_' + call_id, 'call_id': call_id, 'name': name,
            'arguments': json.dumps(args or {}), 'status': 'completed'}


def response(*items, status='completed', reason=None, tokens=1000, cached=0, written=0, tier='default'):
    return {'status': status, 'model': settings.OPENAI_MODEL, 'output': list(items), 'service_tier': tier,
            'incomplete_details': {'reason': reason} if reason else None,
            'usage': {'input_tokens': tokens, 'input_tokens_details': {'cached_tokens': cached,
                                                                     'cache_write_tokens': written},
                      'output_tokens': 200, 'output_tokens_details': {'reasoning_tokens': 150}}}


class Stream:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_final_response(self):
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


class FakeResponses:
    provider = 'openai'
    model = settings.OPENAI_MODEL
    effort = 'xhigh'
    agent_effort = 'high'

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []
        self.responses = SimpleNamespace(stream=self.stream)

    def stream(self, **params):
        self.calls.append(copy.deepcopy(params))
        item = self.script.pop(0)
        return Stream(item(params) if callable(item) else item)

    def with_options(self, **options):
        return self


def test_catalog_export_preserves_optional_arguments_and_hidden_tools(env):
    catalog = tools.load_catalog(env.site)
    fingerprint = catalog.bot.fingerprint
    exported = astra.tool_defs(catalog.bot.toolset.defs)
    assert exported[0]['type'] == 'tool_search' and exported[0]['execution'] == 'server'
    assert tools.load_catalog(env.site).bot.fingerprint == fingerprint
    assert not any(t.get('name') in settings.HIDDEN_TOOLS for t in exported)
    assert next(t for t in exported if t.get('name') == 'analytics_sales')['defer_loading']
    assert not next(t for t in exported if t.get('name') == tools.REPORT_TOOL).get('defer_loading')
    definition = astra.tool_defs([{'name': 'x', 'input_schema': {'type': 'object', 'properties': {
        'optional': {'type': 'string'}}}}])[0]
    assert definition['strict'] is False and 'required' not in definition['parameters']


def test_provider_instructions_describe_actual_search_without_resetting_catalog(env):
    catalog = tools.load_catalog(env.site)
    for persona in [catalog.bot, *catalog.agents.values()]:
        params = agent.request_params(model=settings.OPENAI_MODEL, effort='xhigh', system_text=persona.system,
                                      tool_list=persona.toolset.defs, messages=[])
        rewritten = astra.request_params(params)['instructions']
        assert 'tool_search_tool_regex' not in rewritten and 'регулярное выражение' not in rewritten
        assert 'tool_search_tool_regex' in persona.system


def test_search_only_response_resumes_without_executing_a_function(env):
    client = FakeResponses(response({'type': 'tool_search_output', 'execution': 'server', 'tools': []}),
                           response(output_text('Готово')))
    result = turn(env, client)
    assert len(client.calls) == 2 and result.text == 'Готово' and not env.site.calls


def test_duplicate_call_ids_abort_before_any_side_effect(env):
    with pytest.raises(astra.ResponseError):
        turn(env, FakeResponses(response(call(tools.REPORT_TOOL), call(tools.REPORT_TOOL))))
    assert not env.site.calls


def test_old_history_keeps_facts_calls_and_attachments_without_thinking():
    history = [
        {'role': 'assistant', 'content': [{'type': 'thinking', 'signature': 'secret-sig', 'thinking': 'private'},
                                        use('analytics_sales', {'date': '2026-11-01'}, 'old_call')]},
        {'role': 'user', 'content': [tools.tool_result('old_call', 'Выручка: 1234') ]},
        {'role': 'assistant', 'content': [text('Получилось 1234')]},
        {'role': 'user', 'content': [text('Продолжи'),
            {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': 'AAA'}},
            {'type': 'document', 'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': 'BBB'}}]},
    ]
    original = copy.deepcopy(history)
    items = astra.input_items(history)
    assert history == original
    assert items[0]['call_id'] == items[1]['call_id'] == 'old_call'
    assert 'secret-sig' not in json.dumps(items) and 'private' not in json.dumps(items)
    assert items[2]['content'][0]['text'] == 'Получилось 1234'
    assert items[-1]['content'][1]['image_url'] == 'data:image/png;base64,AAA'
    assert items[-1]['content'][2]['file_data'] == 'data:application/pdf;base64,BBB'


def test_reasoning_and_hosted_search_replayed_once_in_original_order(env):
    opaque = {'type': 'reasoning', 'id': 'rs_1', 'encrypted_content': 'opaque', 'summary': []}
    search = {'type': 'tool_search_call', 'execution': 'server', 'status': 'completed', 'arguments': {}}
    loaded = {'type': 'tool_search_output', 'execution': 'server', 'status': 'completed', 'tools': []}
    invocation = call('analytics_sales')
    client = FakeResponses(response(opaque, search, loaded, invocation), response(output_text('42')))
    result = turn(env, client)
    items = client.calls[1]['input']
    assert items[1:5] == [opaque, search, loaded, invocation]
    assert sum(i['type'] == 'function_call' for i in items if 'type' in i) == 1
    assert items[5]['type'] == 'function_call_output' and items[5]['call_id'] == invocation['call_id']
    assert result.text == '42' and client.calls[0]['model'] == settings.OPENAI_MODEL
    assert client.calls[0]['store'] is False and client.calls[0]['reasoning'] == {'effort': 'xhigh'}
    assert 'thinking' not in client.calls[0] and 'betas' not in client.calls[0]


@pytest.mark.parametrize('web', [False, True])
def test_cards_go_to_original_channel_and_chat(env, web):
    ctx = ctx_for(env)
    if web:
        ctx.web_question = 'question1'
    client = FakeResponses(response(call(tools.REPORT_TOOL, {'chat_id': 'someone-else', 'title': 'Отчёт'})),
                           response(output_text('')))
    turn(env, client, ctx=ctx)
    assert len(ctx.reports_sent) == 1
    if web:
        assert env.site.web_cards[0][0] == 'question1'
        assert not env.site.calls
    else:
        assert env.site.calls[0][1]['chat_id'] == OWNER_TG
        assert not env.site.web_cards


def test_unknown_tool_and_malformed_arguments_do_not_reach_site(env):
    malformed = call('analytics_sales', call_id='call_malformed')
    malformed['arguments'] = '{'
    client = FakeResponses(response(call('common_bot_journal'), malformed), response(output_text('Ошибка')))
    allowed = tools.load_catalog(env.site).bot.toolset.names
    env.site.calls.clear()
    turn(env, client, ctx=ctx_for(env, allowed=allowed))
    assert not env.site.calls
    results = [i for i in client.calls[1]['input'] if i.get('type') == 'function_call_output']
    assert len(results) == 2 and all(i['output'][0]['text'] == 'Ошибка инструмента:' for i in results)


@pytest.mark.parametrize('status,reason', [('incomplete', 'max_output_tokens'), ('incomplete', 'content_filter')])
def test_incomplete_calls_are_not_executed(env, status, reason):
    client = FakeResponses(response(call(tools.REPORT_TOOL), status=status, reason=reason),
                           response(output_text('Неполный ответ')))
    result = turn(env, client)
    assert not env.site.calls and not env.site.web_cards
    assert result.notes
    if reason == 'max_output_tokens':
        assert client.calls[1]['tool_choice'] == 'none'


def test_failed_stream_does_not_execute_partial_calls(env):
    with pytest.raises(astra.ResponseError):
        turn(env, FakeResponses(response(call(tools.REPORT_TOOL), status='failed')))
    assert not env.site.calls


def test_refusal_with_calls_does_not_execute_them(env):
    refusal = output_text('')
    refusal['content'] = [{'type': 'refusal', 'refusal': 'Не могу выполнить.'}]
    result = turn(env, FakeResponses(response(call(tools.REPORT_TOOL), refusal)))
    assert not env.site.calls and result.stop_reason == 'refusal'


def test_usage_categories_long_context_fast_and_reasoning():
    reply = astra.normalize(response(tokens=1000, cached=300, written=200, tier='fast'))
    usage = agent._usage_dict(reply.usage)
    assert usage == {'input_tokens': 500, 'output_tokens': 200, 'cache_read_input_tokens': 300,
                     'cache_creation_input_tokens': 200}
    assert astra.cost_usd(usage) == .0178
    assert astra.cost_usd(usage, 'fast') == .0356
    long = dict(usage, input_tokens=272000)
    assert astra.cost_usd(long) == pytest.approx((2720000 + 300 + 2500) * 2 / 1e6 + .015)
    assert astra.normalize(response(tier='default')).usage.speed == 'standard'


def test_budget_and_stop_apply_before_next_astra_request(env):
    ctx = ctx_for(env)
    ctx.spend = agent.Spend(limit=.001)
    client = FakeResponses(response(call('analytics_sales')), response(output_text('Итог')))
    result = turn(env, client, ctx=ctx)
    assert 'question_budget' in result.notes and client.calls[1]['tool_choice'] == 'none'
    ctx.stop = threading.Event()
    ctx.stop.set()
    empty = FakeResponses()
    with pytest.raises(agent.Stopped):
        turn(env, empty, ctx=ctx)
    assert not empty.calls


@pytest.mark.parametrize('budget', ['question', 'daily', 'personal'])
@pytest.mark.parametrize('web', [False, True])
def test_delivered_report_finishes_successfully_when_budget_exhausted(env, budget, web):
    ctx = ctx_for(env)
    ctx.user = 'reviewer'
    if web:
        ctx.web_question = 'question1'
    if budget == 'question':
        ctx.spend = agent.Spend(limit=.001)
    else:
        env.monkeypatch.setattr(settings, 'DAILY_BUDGET_USD' if budget == 'daily'
                                else 'USER_DAILY_BUDGET_USD', .001)
    client = FakeResponses(response(call(tools.REPORT_TOOL, {'title': 'Отчёт'})))
    result = turn(env, client, ctx=ctx)
    assert len(client.calls) == len(ctx.reports_sent) == 1
    assert result.text == ''
    assert ('question_budget' if budget == 'question' else 'daily_budget') in result.notes
    paired = result.messages[-1]['content'][0]
    assert paired['type'] == 'tool_result' and paired['tool_use_id'] == 'call_test'
    assert not paired.get('is_error')


def test_failed_report_is_not_success_when_budget_exhausted(env):
    env.monkeypatch.setattr(settings, 'DAILY_BUDGET_USD', .001)
    env.site.report_error = 'Не доставлено'
    ctx = ctx_for(env)
    client = FakeResponses(response(call(tools.REPORT_TOOL, {'title': 'Отчёт'})))
    with pytest.raises(agent.BudgetExceeded):
        turn(env, client, ctx=ctx)
    assert not ctx.reports_sent and len(client.calls) == 1


def test_compaction_keeps_opaque_state_and_following_items():
    compact = {'type': 'compaction', 'id': 'cmp_1', 'encrypted_content': 'compact'}
    normalized = astra.normalize(response(compact, output_text('Итог')))
    items = astra.input_items([{'role': 'user', 'content': [text('old')]},
                              {'role': 'assistant', 'content': normalized.content},
                              {'role': 'user', 'content': [text('new')]}])
    assert items[0] == compact and len(items) == 3


def test_provider_switch_does_not_send_openai_state_to_anthropic(env):
    history = turn(env, FakeResponses(response(output_text('Astra')))).messages
    old_client = FakeClient(resp(text('Claude')))
    result = turn(env, old_client, history=history)
    assert result.text == 'Claude'
    assert 'provider_state' not in json.dumps(old_client.calls)
    assert any(b.get('type') == 'provider_state' for m in history for b in m['content'])


def test_openai_ready_without_claude_key_and_key_removal(env):
    env.site.cfg.update(provider='openai', openai_key='sk-test', anthropic_key='')
    tg = FakeTelegram()
    checked = []
    svc = service.Service(env.site, env.store, io_factory=lambda key: tg,
                          check_key=lambda key: checked.append(key) or ('ok', settings.OPENAI_MODEL))
    try:
        assert svc.ready() and svc.web_ready() and checked == ['sk-test']
        assert svc.model_selection.model == settings.OPENAI_MODEL
        env.site.cfg['openai_key'] = ''
        svc.refresh_config(force=True)
        assert not svc.web_ready() and not svc.ready()
        env.site.cfg['openai_key'] = 'sk-test'
        svc.refresh_config(force=True)
        assert svc.ready() and svc.web_ready() and checked == ['sk-test', 'sk-test']
    finally:
        svc.executor.shutdown(wait=False)


def test_agents_use_same_provider_with_agent_effort(env):
    catalog = tools.load_catalog(env.site)
    client = FakeResponses(response(output_text('Отчёт агента')))
    result = agent.run_agent(client, next(iter(catalog.agents.values())), 'Проверь цифры',
                             parent=ctx_for(env), store=env.store)
    assert result == 'Отчёт агента'
    assert client.calls[0]['model'] == settings.OPENAI_MODEL
    assert client.calls[0]['reasoning']['effort'] == 'high'
    assert not any(t.get('name') == tools.ASK_AGENT for t in client.calls[0]['tools'])


@pytest.mark.parametrize('code,body,kind', [(401, {}, 'auth'), (403, {}, 'denied'), (404, {}, 'denied'),
    (429, {'code': 'insufficient_quota'}, 'billing'), (429, {}, 'rate'), (500, {}, 'server'), (400, {}, 'bad_request')])
def test_errors_are_classified_without_leaking_key_or_request(code, body, kind):
    import httpx2
    import openai
    exc = openai.APIStatusError('sk-secret private question',
        response=httpx2.Response(code, request=httpx2.Request('POST', 'https://api.openai.com/v1/responses')),
        body=body)
    actual, message = astra.describe_error(exc, ('sk-secret',))
    assert actual == kind and 'sk-secret' not in message and 'private question' not in message


def test_fast_falls_back_without_replaying_actions(env):
    import httpx2
    import openai
    error = openai.RateLimitError('no capacity', body={}, response=httpx2.Response(429,
        request=httpx2.Request('POST', 'https://api.openai.com/v1/responses')))
    client = FakeResponses(error, response(call('analytics_sales')), response(output_text('Ответ')))
    turn(env, client, fast=True)
    assert client.calls[0]['service_tier'] == 'fast'
    assert all('service_tier' not in c for c in client.calls[1:])
    assert len(env.site.calls) == 1


def test_selection_is_immutable_and_old_config_still_works():
    from dataclasses import FrozenInstanceError
    assert providers.selection({}).provider == 'anthropic'
    cfg = {'provider': 'openai', 'effort': 'high'}
    selected = providers.selection(cfg)
    cfg['provider'] = 'anthropic'
    assert selected.provider == 'openai' and selected.model == settings.OPENAI_MODEL
    with pytest.raises(FrozenInstanceError):
        selected.model = 'other'


@pytest.mark.parametrize('web', [False, True])
def test_service_continues_existing_dialog_and_pins_model_during_config_change(bot, web):
    from test_kultura_bot import message
    from test_research_page import web_job, TID
    chat_id = 'web:' + TID if web else OWNER_TG
    persona = bot.svc.get_catalog().bot
    import time
    bot.env.store.save_dialog(chat_id, persona.fingerprint, '2026-11-16T10:00:00+03:00',
                             [{'role': 'user', 'content': [text('Прошлый вопрос')]},
                              {'role': 'assistant', 'content': [text('Прошлый ответ: 1234')]}], 1)
    bot.env.site.cfg.update(provider='openai', openai_key='sk-astra', anthropic_key='')
    bot.svc.refresh_config(force=True)
    bot.svc.ready()
    keys = []

    def first(params):
        bot.env.site.cfg.update(provider='anthropic', anthropic_key='new-key')
        bot.svc.refresh_config(force=True)
        return response(call('analytics_sales'))

    client = FakeResponses(first, response(output_text('**Итог:** 42\n\n>> Как считается\n>> Сумма.\n\n[[По дням]]')))
    bot.svc.client_factory = lambda key: keys.append(key) or client
    if web:
        bot.env.site.web_queue.append(web_job(question='Продолжи'))
        bot.svc.take_web_job()
        assert not bot.tg.sent
        body = bot.env.site.web_finished[-1][1]
        assert body['answer'] == '**Итог:** 42' and body['how'] == 'Сумма.'
    else:
        bot.svc.handle_update(message('Продолжи'))
        assert bot.tg.sent
    assert keys == ['sk-astra']
    assert all(c['model'] == settings.OPENAI_MODEL for c in client.calls)
    assert 'Прошлый ответ: 1234' in str(client.calls[0]['input'])
    assert bot.env.store.get_dialog(chat_id)['turns'] == 2
    record = bot.env.site.journal_records[-1]
    assert record['model'] == settings.OPENAI_MODEL and record['provider'] == 'openai'
    assert record['cost_usd'] > 0


def test_real_sdk_stream_contract_with_mock_transport(env):
    """Проверяем сериализацию и сборку SSE настоящим закреплённым SDK, без сети."""
    import httpx2
    import openai
    captured = []
    answer = dict(response(output_text('SDK работает')), id='resp_test', created_at=1, object='response')

    def transport(request):
        captured.append(json.loads(request.content))
        initial = dict(answer, status='in_progress', output=[])
        events = [('response.created', {'response': initial}),
                  ('response.completed', {'response': answer})]
        wire = ''.join('event: ' + name + '\ndata: ' + json.dumps({'type': name, 'sequence_number': i, **data})
                       + '\n\n' for i, (name, data) in enumerate(events))
        return httpx2.Response(200, headers={'content-type': 'text/event-stream'}, content=wire)

    with openai.OpenAI(api_key='sk-test', http_client=httpx2.Client(transport=httpx2.MockTransport(transport))) as sdk:
        client = providers.BoundClient(sdk, providers.selection({'provider': 'openai'}))
        result = turn(env, client, tool_list=tools.load_catalog(env.site).bot.toolset.defs)
    assert result.text == 'SDK работает'
    assert captured[0]['stream'] is True and captured[0]['store'] is False
    assert captured[0]['tools'][0] == {'type': 'tool_search', 'execution': 'server'}
    assert captured[0]['reasoning']['effort'] == 'medium'


def test_astra_medium_default_and_full_role_catalog(env):
    selected = providers.selection({'provider': 'openai'})
    assert selected.effort == selected.agent_effort == 'medium'
    catalog = tools.load_catalog(env.site)
    for persona in [catalog.bot, *catalog.agents.values()]:
        params = agent.request_params(model=selected.model, effort=selected.effort,
                                      system_text=persona.system, tool_list=persona.toolset.defs, messages=[])
        request = astra.request_params(params)
        expected = {t['name'] for t in astra.tool_defs(persona.toolset.defs)
                    if t.get('type') == 'function' and t['name'] not in settings.HIDDEN_TOOLS}
        assert {t['name'] for t in request['tools'] if t['type'] == 'function'} == expected
        assert request['tools'][0] == {'type': 'tool_search', 'execution': 'server'}
        assert request['reasoning']['effort'] == 'medium'
        assert any(t.get('defer_loading') for t in request['tools'])


def test_unexpected_client_search_does_not_execute_tools(env):
    client = FakeResponses(response({'type': 'tool_search_call', 'execution': 'client',
                                     'call_id': 'search1', 'arguments': {'terms': ['sales']}}))
    with pytest.raises(astra.ResponseError):
        turn(env, client)
    assert not env.site.calls


def test_hosted_search_with_planning_text_continues(env):
    client = FakeResponses(response(output_text('Ищу данные.'),
                           {'type': 'tool_search_output', 'execution': 'server', 'tools': []}),
                           response(output_text('Итог')))
    result = turn(env, client)
    assert len(client.calls) == 2 and result.text == 'Итог'


def test_astra_timing_does_not_mix_models_efforts_or_speed(env):
    from kultura_bot.engine import progress
    from dataclasses import replace
    selected = providers.selection({'provider': 'openai'})
    keys = {providers.timing_profile('report', selected),
            providers.timing_profile('report', selected, True),
            providers.timing_profile('report', replace(selected, effort='high')),
            providers.timing_profile('report', replace(selected, agent_effort='high')),
            providers.timing_profile('answer', selected),
            providers.timing_profile('report', providers.selection())}
    assert len(keys) == 6
    tracker = progress.Tracker('report', agent.Spend(), limit=5, durations=[],
                               tool_typical={}, titles={}, clock=lambda: 0)
    tracker.use_default_history = False
    assert tracker.estimate()[0] is None
    assert 'оцениваю время' in tracker.render()
    assert 'дольше обычного' not in tracker.render()
    assert 'оцениваю время' in tracker.draft_lines()[1]
    tracker.durations = [20, 30, 40, 50, 60]
    assert tracker.estimate()[0] == 40
