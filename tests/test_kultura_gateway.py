import pytest
from kultura_bot.engine import gateway, astra, claude


@pytest.mark.parametrize('model', list(gateway.MODELS))
def test_gateway_selects_fixed_endpoint(model):
    selected = gateway.connection(model)
    assert selected.model == model
    assert selected.base_url == (gateway.ANTHROPIC_URL if model.startswith('claude-') else gateway.OPENAI_URL)
    with pytest.raises(ValueError):
        gateway.connection('https://other.example/model')


def test_gateway_never_reuses_direct_key(monkeypatch):
    monkeypatch.delenv('ClaudeHub', raising=False)
    monkeypatch.setenv('KULTURA_BOT_OPENAI_KEY', 'direct-openai-key')
    monkeypatch.setenv('KULTURA_BOT_ANTHROPIC_KEY', 'direct-anthropic-key')
    assert gateway.api_key() == ''
    monkeypatch.setenv('ClaudeHub', ' gateway-key ')
    assert gateway.api_key() == 'gateway-key'


def test_provider_rates_require_complete_explicit_catalogue():
    fields = ['price_input_per_1m_usd', 'price_output_per_1m_usd',
              'price_cache_read_per_1m_usd', 'price_cache_write_per_1m_usd']
    pricing = dict(zip(fields, [.4, .4, .4, .4]), billing_mode='token')
    catalogue = {'data': [{'id': 'gpt-6-astra', 'pricing': pricing}]}
    assert gateway.prices_from_catalogue('gpt-6-astra', catalogue) == (.4,) * 4
    for value in (None, True, -1, float('nan'), float('inf')):
        pricing[fields[0]] = value
        with pytest.raises(ValueError):
            gateway.prices_from_catalogue('gpt-6-astra', catalogue)


def test_sdk_endpoint_override_does_not_change_defaults():
    with astra.make_client('test', base_url=gateway.OPENAI_URL) as client:
        assert str(client.base_url) == gateway.OPENAI_URL + '/'
    with claude.make_client('test', base_url=gateway.ANTHROPIC_URL) as client:
        assert str(client.base_url) == gateway.ANTHROPIC_URL
    with astra.make_client('test') as client:
        assert str(client.base_url).startswith('https://api.openai.com/')


def test_http_200_with_error_is_not_an_empty_success():
    with pytest.raises(ValueError, match='unsupported') as err:
        gateway.validate_response({'error': {'message': 'unsupported secret-key'}}, key='secret-key')
    assert 'secret-key' not in str(err.value)
    assert gateway.validate_response({'choices': []}) == {'choices': []}
