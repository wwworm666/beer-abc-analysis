"""Контрольный прогон не отправляет сообщения, не меняет MCP и не раскрывает эталон модели."""
import json
import stat

import pytest

from scripts import kultura_astra_eval as ev
from kultura_bot.engine import tools
from kultura_bot.engine.site import SiteError
from test_kultura_astra import FakeResponses, call, output_text, response
from test_kultura_bot import env, site_tool  # noqa: F401


def test_case_inventory_skips_followups_and_commands():
    data = {'records': [
        {'uid': 'a', 'question': 'Сравни удержание гостей за октябрь по всем барам', 'answer': '42', 'cards': [{'report_id': 'r1'}]},
        {'uid': 'b', 'question': 'А по категориям?'},
        {'uid': 'c', 'question': '/allow ' + 'x' * 50}],
        'reports': {'r1': {'title': 'Отчёт'}}}
    cases = ev.cases_from_saved(data)
    assert len(cases) == 1 and cases[0]['reference_cards'] == [{'title': 'Отчёт'}]


def test_readonly_boundary_denies_missing_annotation_writes_and_hidden_tools():
    class Source:
        calls = []

        def tools(self, connector):
            return [dict(site_tool('read'), annotations={'readOnlyHint': True}),
                    dict(site_tool('write'), annotations={'readOnlyHint': False}), site_tool('missing'),
                    dict(site_tool('common_bot_journal'), annotations={'readOnlyHint': True}),
                    site_tool(tools.REPORT_TOOL)]

        def call_tool(self, name, args):
            self.calls.append(name)
            return {'content': []}

    source = Source()
    site = ev.ReadOnlySite(source)
    assert {t['name'] for t in site.tools()} == {'read', tools.REPORT_TOOL}
    for name in ('write', 'missing', 'common_bot_journal', 'invented'):
        with pytest.raises(SiteError):
            site.call_tool(name, {})
    assert not source.calls
    site.call_tool('read', {})
    assert source.calls == ['read']


def test_report_is_validated_locally_and_not_sent():
    from test_research_page import REPORT

    class NoNetwork:
        def call_tool(self, *args):
            pytest.fail('Доставка в контроле запрещена')

    site = ev.ReadOnlySite(NoNetwork())
    bad = site.call_tool(tools.REPORT_TOOL, {'report': {}})
    assert bad['isError'] and not site.cards
    good = site.web_card('question', tools.REPORT_TOOL, {'report': REPORT, 'chat_id': 'production-chat'})
    assert not good.get('isError') and len(site.cards) == 1
    assert site.cards[0]['body']['title'] == REPORT['title']


def test_evaluation_does_not_show_reference_to_model(env):
    site = ev.ReadOnlySite(env.site)
    catalog = tools.load_catalog(env.site)
    client = FakeResponses(response(output_text('Новый ответ')))
    case = {'id': 'x', 'question': 'Сколько гостей?', 'asked_at': '2026-10-01', 'mode': 'answer',
            'reference_answer': 'SECRET_REFERENCE', 'reference_cards': [{'title': 'SECRET_CARD'}]}
    report = ev.evaluate(case, client, catalog, site, env.store, .5)
    serialized = json.dumps(client.calls)
    assert 'SECRET_REFERENCE' not in serialized and 'SECRET_CARD' not in serialized
    assert report['candidate_answer'] == 'Новый ответ' and report['quality'] == 'requires_review'
    assert report['reference_answer'] == 'SECRET_REFERENCE'


def test_budget_failure_keeps_actual_usage_and_partial_cards(env, monkeypatch):
    from kultura_bot import settings
    monkeypatch.setattr(settings, 'DAILY_BUDGET_USD', .001)
    catalog = tools.load_catalog(env.site)
    site = ev.ReadOnlySite(env.site)
    client = FakeResponses(response(call('analytics_sales')))
    case = {'id': 'x', 'question': 'Сколько гостей?', 'asked_at': '2026-10-01', 'mode': 'answer'}
    report = ev.evaluate(case, client, catalog, site, env.store, .001)
    assert report['status'] == 'budget' and report['steps'] == 1
    assert report['cost_usd'] > 0 and report['usage'][0]['tokens']['input_tokens'] == 1000
    assert report['candidate_answer'] == '' and report['notes'] == ['daily_budget']


def test_dry_run_is_offline_and_output_is_private(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, 'Site', lambda *args: pytest.fail('Сеть в сухом прогоне'))
    baseline = tmp_path / 'baseline.json'
    baseline.write_text(json.dumps({'records': []}))
    out = tmp_path / 'out.json'
    out.touch(mode=0o644)
    assert ev.main(['--baseline', str(baseline), '--out', str(out)]) == 0
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
