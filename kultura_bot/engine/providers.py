"""Выбор модели на один вопрос. Старый ответ /api/bot/config означает Anthropic.

Клиент фиксирует ключ, модель и усилие для вопроса и всех его агентов. Изменение
настроек в соседнем потоке не меняет уже начатое исследование.
"""
from dataclasses import dataclass

from kultura_bot import settings
from kultura_bot.engine import claude


@dataclass(frozen=True)
class Selection:
    provider: str = 'anthropic'
    model: str = settings.MODEL
    effort: str = settings.EFFORT
    agent_effort: str = settings.AGENT_EFFORT


def selection(config=None):
    config = config or {}
    provider = config.get('provider') or 'anthropic'
    if provider not in ('anthropic', 'openai'):
        raise ValueError('Неизвестный провайдер модели')
    model = config.get('model') or (settings.OPENAI_MODEL if provider == 'openai' else settings.MODEL)
    if provider == 'openai' and model != settings.OPENAI_MODEL:
        raise ValueError('Для OpenAI поддерживается модель ' + settings.OPENAI_MODEL)
    effort = config.get('effort') or (settings.OPENAI_EFFORT if provider == 'openai' else settings.EFFORT)
    agent_effort = config.get('agent_effort') or effort
    if effort not in settings.MODEL_EFFORTS or agent_effort not in settings.MODEL_EFFORTS:
        raise ValueError('Неизвестное усилие модели')
    return Selection(provider, model, effort, agent_effort)


def api_key(config, selected):
    return str((config or {}).get(selected.provider + '_key') or '')


class BoundClient:
    def __init__(self, client, selected):
        self.client = client
        self.provider = selected.provider
        self.model = selected.model
        self.effort = selected.effort
        self.agent_effort = selected.agent_effort

    def __getattr__(self, name):
        return getattr(self.client, name)


def client_for(key, selected):
    if selected.provider == 'openai':
        from kultura_bot.engine import astra
        return BoundClient(astra.client_for(key), selected)
    return BoundClient(claude.client_for(key), selected)


def check_key(key, selected):
    if selected.provider == 'openai':
        from kultura_bot.engine import astra
        return astra.check_key(key, selected.model)
    return claude.check_key(key)


def describe_error(exc, selected, secrets=()):
    if selected.provider == 'openai':
        from kultura_bot.engine import astra
        return astra.describe_error(exc, secrets)
    return claude.describe_error(exc, secrets)


def cost_usd(client, model, usage, speed):
    if getattr(client, 'provider', '') == 'openai':
        from kultura_bot.engine import astra
        return astra.cost_usd(usage, speed)
    return claude.cost_usd(model, usage, speed)


def timing_profile(mode, selected, fast=False):
    """Astra learns its own timings; retain legacy Anthropic statistics unchanged."""
    if selected.provider != 'openai':
        return mode
    return ':'.join((mode, selected.provider, selected.model, selected.effort,
                     selected.agent_effort, 'fast' if fast else 'standard'))
