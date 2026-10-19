"""Секреты бота @MCPkulturabot: токен Telegram и ключ Anthropic API — и пауза.

## Почему не в репозитории

Репозиторий публичный: токен бота и ключ API оттуда забрал бы кто угодно. Поэтому
секреты владелец вставляет один раз на странице «Доступ агентов» (/admin/mcp, раздел
«Бот @MCPkulturabot»): без .env и без передеплоя, работает сразу в обоих воркерах.
Остальные настройки бота — в репозитории: kultura_bot/settings.py.

## Кто ими пользуется

- токен — сам сайт (графики common_chart_send, проверка входа в мини-приложение) и
  сервер бота в Амстердаме (Telegram: приём и ответы);
- ключ Anthropic — только сервер бота: сайт стоит в России, где API Anthropic недоступен,
  и к Anthropic не обращается. Ключ сайт хранит и отдаёт серверу бота (GET /api/bot/config,
  только его ключу); проверяет ключ тоже сервер бота — ошибка видна на странице.

## Где хранятся

Таблица settings в mcp.db (core/mcp/settings.py):

    tg_chart_bot_token          токен бота (имя ключа — с первой версии, когда бот только
                                присылал графики: сохранённый тогда токен работает дальше)
    tg_chart_bot_username       имя бота из getMe — из него собирается ссылка для групп
    kultura_bot_anthropic_key   ключ Claude API (sk-ant-…)
    kultura_bot_paused          True — бот молчит (экстренная остановка); графики агентов по
                                MCP (common_chart_send) при этом уходят

Запасной путь — окружение, если на странице пусто: TELEGRAM_MCP_BOT_TOKEN,
KULTURA_BOT_ANTHROPIC_KEY.

## Проверки при сохранении (save)

- токен: формат «число:строка» и getMe в Telegram — неверный не сохраняется, у верного
  запоминается имя бота; нет связи с Telegram — сохраняется с предупреждением;
- ключ Anthropic: формат sk-ant-… (живую проверку делает сервер бота).

Сначала проверяется всё, потом пишется: ошибка в одном поле не сохраняет другие.
Секреты наружу не выходят: страница и API видят только подсказки «8801…HOg».
"""
import os
import re
from typing import Any, Callable, Dict, Optional

from kultura_bot import settings as bot_settings

KEY_TOKEN = 'tg_chart_bot_token'
KEY_USERNAME = 'tg_chart_bot_username'
KEY_ANTHROPIC = 'kultura_bot_anthropic_key'
KEY_PAUSED = 'kultura_bot_paused'

BOT_TOKEN_ENV = 'TELEGRAM_MCP_BOT_TOKEN'
ANTHROPIC_ENV = 'KULTURA_BOT_ANTHROPIC_KEY'

TOKEN_RE = re.compile(r'\d{5,15}:[A-Za-z0-9_-]{30,64}')        # формат токена @BotFather
USERNAME_RE = re.compile(r'[A-Za-z][A-Za-z0-9_]{3,31}')
ANTHROPIC_KEY_RE = re.compile(r'sk-ant-[A-Za-z0-9_-]{20,200}')

GetMe = Callable[[str], Optional[Dict[str, Any]]]


def _stored(key: str) -> Any:
    try:
        from core.mcp import settings
        return settings.get(key)
    except Exception:  # noqa: BLE001 — нет базы настроек: работаем от окружения
        return None


def _text(key: str, env: str) -> str:
    stored = _stored(key)
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    return (os.environ.get(env) or '').strip()


def _source(key: str, env: str) -> str:
    stored = _stored(key)
    if isinstance(stored, str) and stored.strip():
        return 'settings'
    return 'env' if (os.environ.get(env) or '').strip() else ''


# ------------------------------------------------------------------ чтение

def bot_token() -> str:
    """Токен бота: со страницы, иначе TELEGRAM_MCP_BOT_TOKEN."""
    return _text(KEY_TOKEN, BOT_TOKEN_ENV)


def token_source() -> str:
    """Откуда токен: settings, env или '' (не настроен)."""
    return _source(KEY_TOKEN, BOT_TOKEN_ENV)


def bot_username() -> str:
    """Имя бота без @: из getMe при сохранении токена, иначе kultura_bot/settings.py."""
    name = str(_stored(KEY_USERNAME) or '').strip().lstrip('@')
    return name if USERNAME_RE.fullmatch(name) else bot_settings.BOT_USERNAME


def anthropic_key() -> str:
    """Ключ Claude API: со страницы, иначе KULTURA_BOT_ANTHROPIC_KEY."""
    return _text(KEY_ANTHROPIC, ANTHROPIC_ENV)


def paused() -> bool:
    return _stored(KEY_PAUSED) is True


def hint(secret: str) -> str:
    """«8801…HOg» — чтобы владелец узнал свой секрет, не показывая его."""
    secret = secret or ''
    return f'{secret[:4]}…{secret[-3:]}' if len(secret) > 10 else ''


def public_view() -> Dict[str, Any]:
    """Состояние для страницы «Доступ агентов» — без самих секретов."""
    token, key = bot_token(), anthropic_key()
    return {
        'telegram': {'configured': bool(token), 'source': token_source(), 'token_hint': hint(token),
                     'bot_username': bot_username()},
        'anthropic': {'configured': bool(key), 'source': _source(KEY_ANTHROPIC, ANTHROPIC_ENV),
                      'key_hint': hint(key)},
        'paused': paused(),
    }


def engine_view() -> Dict[str, Any]:
    """Настройки для сервера бота (GET /api/bot/config) — с секретами, только его ключу."""
    return {'telegram': {'token': bot_token(), 'username': bot_username()},
            'anthropic_key': anthropic_key(), 'paused': paused()}


# ------------------------------------------------------------------ запись

def _getme(token: str) -> Optional[Dict[str, Any]]:
    from core.open_check_telegram import api_call
    return api_call('getMe', {}, token=token)


def save(*, token: Optional[str] = None, clear_token: bool = False,
         anthropic_key_value: Optional[str] = None, clear_anthropic_key: bool = False,
         paused_value: Optional[bool] = None, by: str = '', getme: Optional[GetMe] = None) -> Dict[str, Any]:
    """Сохранить переданное (None — не менять). Вернуть public_view() + warnings.

    Ошибка ввода — ValueError с текстом для владельца (API отдаёт его как 400).
    """
    from core.mcp import settings
    getme = getme or _getme
    writes = []
    warnings = []

    if clear_token:
        writes += [(KEY_TOKEN, ''), (KEY_USERNAME, '')]
    elif token is not None and token.strip():
        token = token.strip()
        if not TOKEN_RE.fullmatch(token):
            raise ValueError('Это не токен бота: он выглядит как «1234567890:AA…» — скопируйте его из @BotFather '
                             'целиком (/mybots → бот → API Token)')
        answer = getme(token)
        if answer is None:
            warnings.append('Нет связи с Telegram: токен сохранён, но не проверен.')
            writes.append((KEY_TOKEN, token))
        elif not answer.get('ok'):
            raise ValueError(f'Telegram не принял токен: {answer.get("description") or "ошибка"}. '
                             f'Скопируйте его из @BotFather заново')
        else:
            username = str((answer.get('result') or {}).get('username') or '')
            writes += [(KEY_TOKEN, token), (KEY_USERNAME, username if USERNAME_RE.fullmatch(username) else '')]

    if clear_anthropic_key:
        writes.append((KEY_ANTHROPIC, ''))
    elif anthropic_key_value is not None and anthropic_key_value.strip():
        new_key = anthropic_key_value.strip()
        if not ANTHROPIC_KEY_RE.fullmatch(new_key):
            raise ValueError('Это не ключ Claude API: он начинается с «sk-ant-». Скопируйте его из консоли '
                             'Anthropic (API Keys) целиком')
        writes.append((KEY_ANTHROPIC, new_key))

    if paused_value is not None:
        if not isinstance(paused_value, bool):
            raise ValueError('Пауза: да или нет')
        writes.append((KEY_PAUSED, paused_value))

    for key, value in writes:
        settings.set(key, value, by=by)
    return dict(public_view(), warnings=warnings)
