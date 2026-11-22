"""Portable plugin wiring and complete, permission-scoped instruction loading."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.mcp import bridge, protocol, registry, schema_check
from core.mcp.principal import Principal
from core.mcp.spec import DOMAINS
from core.mcp.tools import common

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/kultura-os'


@pytest.fixture
def real_registry():
    registry.use_modules(None)
    yield
    registry.reset()


def principal(domains=('*',), mode='full'):
    return Principal(1, 'test', 'Test', 'test', 'oauth', 'plugin', domains=domains, mode=mode)


def test_all_instructions_complete_and_bounded(real_registry):
    tool = registry.get_tool('common_instructions')
    assert not schema_check.validate_arguments(tool.input_schema, {'domain': 'all'})
    result = common._instructions({'domain': 'all'}, principal()).text_value
    for domain in DOMAINS:
        assert registry.domain_instructions(domain) in result
    assert common.INSTRUCTIONS in result
    assert len(result) < bridge.RESULT_TEXT_LIMIT


def test_all_instructions_respect_token_and_connector(real_registry, monkeypatch):
    monkeypatch.setattr(bridge, 'current_call', lambda: SimpleNamespace(connector='staff', mode='read'))
    text = common._instructions({'domain': 'all'}, principal()).text_value
    assert 'Только чтение' in text
    assert registry.domain_instructions('staff') in text
    assert registry.domain_instructions('analytics') not in text
    monkeypatch.setattr(bridge, 'current_call', lambda: None)
    text = common._instructions({'domain': 'all'}, principal(('content',), 'draft')).text_value
    assert registry.domain_instructions('content') in text
    assert registry.domain_instructions('staff') not in text


def test_plugin_full_endpoint_oauth_and_assets():
    manifest = json.loads((PLUGIN / 'plugin.json').read_text())
    server = json.loads((PLUGIN / 'mcp.json').read_text())['mcpServers']['kultura']
    assert server['url'] == 'https://beerkultura.ru/mcp'
    assert server['type'] == 'streamable-http'
    assert 'headers' not in server
    extension = manifest['extensions']['com.openai']
    for path in (extension['onboardingSkill'], extension['interface']['logo'], extension['interface']['composerIcon']):
        assert (PLUGIN / path).is_file()
    market = json.loads((ROOT / '.agents/plugins/marketplace.json').read_text())
    assert (ROOT / market['plugins'][0]['source']['path']).resolve() == PLUGIN.resolve()
    assert (PLUGIN / 'skills/kultura-os/SKILL.md').is_file()


@pytest.mark.parametrize('origin,allowed', [
    ('https://chatgpt.com', True), ('https://chat.openai.com', True),
    ('https://chatgpt.com.attacker.example', False), ('https://attacker.example', False),
])
def test_chatgpt_origins_are_exact(origin, allowed):
    request = SimpleNamespace(headers={'Origin': origin}, host_url='https://beerkultura.ru/')
    assert protocol.origin_allowed(request) is allowed
