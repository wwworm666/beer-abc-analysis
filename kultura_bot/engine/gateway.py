"""ClaudeHub connection metadata for the four approved models.

The gateway key is distinct from the direct Anthropic/OpenAI credentials.
Only the four approved model IDs and fixed HTTPS endpoints are accepted.
Rates must come from the provider catalogue, never from direct-provider defaults.
"""
import math
import os
from dataclasses import dataclass

DEFAULT_EFFORT = 'xhigh'
KEY_ENV = 'ClaudeHub'
ANTHROPIC_URL = 'https://api.claudehub.fun'
OPENAI_URL = 'https://api.claudehub.fun/v1'
MODELS = {
    'claude-opus-5-5': 'anthropic',
    'gpt-6.1-sol': 'chat_completions',
    'claude-fable-5-1': 'anthropic',
    'gpt-6-astra': 'chat_completions',
}


@dataclass(frozen=True)
class Connection:
    model: str
    protocol: str
    base_url: str


def connection(model):
    if model not in MODELS:
        raise ValueError('Модель не входит в разрешённый каталог ClaudeHub')
    protocol = MODELS[model]
    return Connection(model, protocol, ANTHROPIC_URL if protocol == 'anthropic' else OPENAI_URL)


def api_key():
    # Never fall back to a direct-provider key on a third-party endpoint.
    return os.environ.get(KEY_ENV, '').strip()


def prices_from_catalogue(model, catalogue):
    """Return input/output/cache-read/cache-write rates per million tokens.

    Missing, unsupported or invalid rates fail explicitly; no invented fast
    surcharge or long-context multiplier from another provider is applied.
    """
    connection(model)
    record = next((m for m in catalogue.get('data', []) if m.get('id') == model), {})
    pricing = record.get('pricing') or {}
    if pricing.get('billing_mode') != 'token':
        raise ValueError('В каталоге нет токенного тарифа ClaudeHub для этой модели')
    rates = []
    for field in ('price_input_per_1m_usd', 'price_output_per_1m_usd',
                  'price_cache_read_per_1m_usd', 'price_cache_write_per_1m_usd'):
        value = pricing.get(field)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise ValueError('Некорректный или отсутствующий тариф ClaudeHub: ' + field)
        rates.append(float(value))
    return tuple(rates)


def validate_response(payload, key=''):
    """Some gateway failures use HTTP 200; they must not become empty answers."""
    if not isinstance(payload, dict):
        raise ValueError('ClaudeHub вернул некорректный ответ')
    if payload.get('error'):
        error = payload['error']
        message = str(error.get('message', 'Ошибка провайдера') if isinstance(error, dict) else error)
        if key:
            message = message.replace(key, '***')
        raise ValueError('ClaudeHub: ' + message[:500])
    return payload

LABELS = {
    'claude-opus-5-5': 'Claude Opus 5.5',
    'gpt-6.1-sol': 'GPT-6.1 Sol',
    'claude-fable-5-1': 'Claude Fable 5.1',
    'gpt-6-astra': 'GPT-6 Astra',
}


def choices():
    return [{'id': model, 'label': LABELS[model]} for model in MODELS]
