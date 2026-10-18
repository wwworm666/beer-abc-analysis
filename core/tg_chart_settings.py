"""Настройки графиков бота @MCPkulturabot: токен, кнопка, короткое имя мини-приложения.

## Где хранятся

Таблица settings в mcp.db (core/mcp/settings.py) под ключами tg_chart_*. Правит владелец
на странице «Доступ агентов» (/admin/mcp, раздел «Графики в Telegram»): вставил токен,
нажал «Сохранить» — работает сразу в обоих воркерах, без передеплоя и без правки .env.

Переменные окружения — запасной путь, когда в настройках пусто:
TELEGRAM_MCP_BOT_TOKEN, TG_MINIAPP_BUTTON, TG_MINIAPP_SHORT_NAME, TG_MINIAPP_BOT_USERNAME.

## Что проверяется при сохранении

Токен — формат «число:строка» и живой вызов getMe в Telegram: неверный токен не
сохраняется («Telegram не принял токен»), у верного запоминается имя бота — из него
собирается ссылка для кнопки в группах. Нет связи с Telegram — токен сохраняется, имя
бота остаётся прежним, на странице предупреждение.

Токен — секрет: в ответах API и на странице только подсказка «8801…HOg» и имя бота.
"""
import os
import re
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlsplit

KEY_TOKEN = 'tg_chart_bot_token'
KEY_USERNAME = 'tg_chart_bot_username'
KEY_BUTTON = 'tg_chart_button'
KEY_SHORT_NAME = 'tg_chart_short_name'

BOT_TOKEN_ENV = 'TELEGRAM_MCP_BOT_TOKEN'
BUTTON_FLAG_ENV = 'TG_MINIAPP_BUTTON'
SHORT_NAME_ENV = 'TG_MINIAPP_SHORT_NAME'
BOT_USERNAME_ENV = 'TG_MINIAPP_BOT_USERNAME'
APP_URL_ENV = 'TG_MINIAPP_URL'

DEFAULT_BOT_USERNAME = 'MCPkulturabot'
DEFAULT_APP_URL = 'https://beerkultura.ru/tg/chart'

TOKEN_RE = re.compile(r'\d{5,15}:[A-Za-z0-9_-]{30,64}')      # формат токена @BotFather
USERNAME_RE = re.compile(r'[A-Za-z][A-Za-z0-9_]{3,31}')
SHORT_NAME_RE = re.compile(r'[A-Za-z0-9_]{3,30}')             # short name из /newapp

GetMe = Callable[[str], Optional[Dict[str, Any]]]


def _stored(key: str) -> Any:
    try:
        from core.mcp import settings
        return settings.get(key)
    except Exception:  # noqa: BLE001 — нет базы настроек: работаем от окружения
        return None


def _truthy(value: Optional[str]) -> bool:
    return (value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def bot_token() -> str:
    """Токен бота графиков: из настроек, иначе из TELEGRAM_MCP_BOT_TOKEN."""
    stored = _stored(KEY_TOKEN)
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    return (os.environ.get(BOT_TOKEN_ENV) or '').strip()


def token_source() -> str:
    """Откуда токен: settings, env или '' (не настроен)."""
    stored = _stored(KEY_TOKEN)
    if isinstance(stored, str) and stored.strip():
        return 'settings'
    return 'env' if (os.environ.get(BOT_TOKEN_ENV) or '').strip() else ''


def bot_username() -> str:
    """Имя бота без @ (для ссылки в группах): из getMe при сохранении токена, иначе окружение."""
    for value in (_stored(KEY_USERNAME), os.environ.get(BOT_USERNAME_ENV)):
        name = str(value or '').strip().lstrip('@')
        if USERNAME_RE.fullmatch(name):
            return name
    return DEFAULT_BOT_USERNAME


def button_enabled() -> bool:
    """Кнопка «Открыть интерактивно»: флажок в настройках; не сохранён — TG_MINIAPP_BUTTON."""
    stored = _stored(KEY_BUTTON)
    if isinstance(stored, bool):
        return stored
    return _truthy(os.environ.get(BUTTON_FLAG_ENV))


def short_name() -> str:
    """Short name мини-приложения из @BotFather (/newapp); без него в группах кнопки нет."""
    for value in (_stored(KEY_SHORT_NAME), os.environ.get(SHORT_NAME_ENV)):
        name = str(value or '').strip()
        if SHORT_NAME_RE.fullmatch(name):
            return name
    return ''


def app_url() -> str:
    return (os.environ.get(APP_URL_ENV) or '').strip() or DEFAULT_APP_URL


def admin_url() -> str:
    """Страница, где владелец вставляет токен: тот же сайт, что мини-приложение."""
    parts = urlsplit(app_url())
    origin = f'{parts.scheme}://{parts.netloc}' if parts.scheme and parts.netloc else 'https://beerkultura.ru'
    return origin + '/admin/mcp'


def token_hint(token: str) -> str:
    """«8801…HOg» — чтобы владелец узнал свой токен, не показывая его."""
    token = token or ''
    return f'{token[:4]}…{token[-3:]}' if len(token) > 10 else ''


def public_view() -> Dict[str, Any]:
    """Состояние для страницы «Доступ агентов» — без самого токена."""
    token = bot_token()
    return {
        'configured': bool(token),
        'source': token_source(),
        'token_hint': token_hint(token),
        'bot_username': bot_username(),
        'button': button_enabled(),
        'short_name': short_name(),
        'app_url': app_url(),
    }


def _getme(token: str) -> Optional[Dict[str, Any]]:
    from core.open_check_telegram import api_call
    return api_call('getMe', {}, token=token)


def save(*, token: Optional[str] = None, clear_token: bool = False, button: Optional[bool] = None,
         short_name_value: Optional[str] = None, by: str = '', getme: GetMe = None) -> Dict[str, Any]:
    """Сохранить то, что передано (None — не менять). Вернуть public_view() + warning.

    Ошибка ввода — ValueError с текстом для владельца (API отдаёт его как 400). Сначала
    проверяется всё, потом пишется: ошибка в одном поле не сохраняет другие наполовину.
    """
    from core.mcp import settings
    getme = getme or _getme
    writes = []
    warning = ''
    if clear_token:
        writes += [(KEY_TOKEN, ''), (KEY_USERNAME, '')]
    elif token is not None and token.strip():
        token = token.strip()
        if not TOKEN_RE.fullmatch(token):
            raise ValueError('Это не токен бота: он выглядит как «1234567890:AA…» — скопируйте его из @BotFather '
                             'целиком (/mybots → бот → API Token)')
        answer = getme(token)
        if answer is None:
            warning = 'Нет связи с Telegram: токен сохранён, но не проверен. Проверьте позже — пришлите график.'
            writes.append((KEY_TOKEN, token))
        elif not answer.get('ok'):
            raise ValueError(f'Telegram не принял токен: {answer.get("description") or "ошибка"}. '
                             f'Скопируйте его из @BotFather заново')
        else:
            username = str((answer.get('result') or {}).get('username') or '')
            writes += [(KEY_TOKEN, token), (KEY_USERNAME, username if USERNAME_RE.fullmatch(username) else '')]
    if button is not None:
        if not isinstance(button, bool):
            raise ValueError('Кнопка: да или нет')
        writes.append((KEY_BUTTON, button))
    if short_name_value is not None:
        name = str(short_name_value).strip()
        if name and not SHORT_NAME_RE.fullmatch(name):
            raise ValueError('Короткое имя мини-приложения — латиница, цифры и «_», от 3 до 30 символов, как в '
                             '@BotFather (например chart)')
        writes.append((KEY_SHORT_NAME, name))
    for key, value in writes:
        settings.set(key, value, by=by)
    return dict(public_view(), warning=warning)
