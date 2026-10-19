"""Секреты бота @MCPkulturabot: токен Telegram, ключ Anthropic API, прокси — и пауза.

## Почему не в репозитории

Репозиторий публичный: токен бота и ключ API оттуда забрал бы кто угодно. Поэтому
секреты владелец вставляет один раз на странице «Доступ агентов» (/admin/mcp, раздел
«Бот @MCPkulturabot»): без .env и без передеплоя, работает сразу в обоих воркерах.
Остальные настройки бота — в репозитории: kultura_bot/settings.py.

## Где хранятся

Таблица settings в mcp.db (core/mcp/settings.py):

    tg_chart_bot_token          токен бота (имя ключа — с первой версии, когда бот только
                                присылал графики: сохранённый тогда токен работает дальше)
    tg_chart_bot_username       имя бота из getMe — из него собирается ссылка для групп
    kultura_bot_anthropic_key   ключ Claude API (sk-ant-…)
    kultura_bot_proxy           прокси для запросов к Anthropic (http(s)://…); '' — напрямую
    kultura_bot_paused          True — бот молчит (экстренная остановка); графики агентов по
                                MCP (common_chart_send) при этом уходят

Запасной путь — окружение, если на странице пусто: TELEGRAM_MCP_BOT_TOKEN,
KULTURA_BOT_ANTHROPIC_KEY, KULTURA_BOT_PROXY.

## Проверки при сохранении (save)

- токен: формат «число:строка» и getMe в Telegram — неверный не сохраняется, у верного
  запоминается имя бота; нет связи с Telegram — сохраняется с предупреждением;
- ключ Anthropic: формат sk-ant-… и бесплатный запрос списка моделей через тот же прокси
  (kultura_bot/claude.check_key): 401 — не сохраняется; 403 (Anthropic не пускает сервер)
  и «нет связи» — сохраняется с предупреждением, что нужен прокси;
- прокси: http:// или https:// с хостом; новый прокси проверяется вместе с ключом.

Сначала проверяется всё, потом пишется: ошибка в одном поле не сохраняет другие.
Секреты наружу не выходят: страница и API видят только подсказки «8801…HOg».
"""
import os
import re
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlsplit

from kultura_bot import settings as bot_settings

KEY_TOKEN = 'tg_chart_bot_token'
KEY_USERNAME = 'tg_chart_bot_username'
KEY_ANTHROPIC = 'kultura_bot_anthropic_key'
KEY_PROXY = 'kultura_bot_proxy'
KEY_PAUSED = 'kultura_bot_paused'

BOT_TOKEN_ENV = 'TELEGRAM_MCP_BOT_TOKEN'
ANTHROPIC_ENV = 'KULTURA_BOT_ANTHROPIC_KEY'
PROXY_ENV = 'KULTURA_BOT_PROXY'

TOKEN_RE = re.compile(r'\d{5,15}:[A-Za-z0-9_-]{30,64}')        # формат токена @BotFather
USERNAME_RE = re.compile(r'[A-Za-z][A-Za-z0-9_]{3,31}')
ANTHROPIC_KEY_RE = re.compile(r'sk-ant-[A-Za-z0-9_-]{20,200}')
PROXY_SCHEMES = ('http', 'https')

GetMe = Callable[[str], Optional[Dict[str, Any]]]
CheckKey = Callable[[str, str], Tuple[str, str]]


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


def proxy_url() -> str:
    """Прокси для Anthropic: со страницы, иначе KULTURA_BOT_PROXY; '' — напрямую."""
    return _text(KEY_PROXY, PROXY_ENV)


def paused() -> bool:
    return _stored(KEY_PAUSED) is True


def hint(secret: str) -> str:
    """«8801…HOg» — чтобы владелец узнал свой секрет, не показывая его."""
    secret = secret or ''
    return f'{secret[:4]}…{secret[-3:]}' if len(secret) > 10 else ''


def proxy_display(url: str) -> str:
    """Прокси без логина и пароля: «http://proxy.example:3128». Адрес не разбирается (старое
    значение из окружения) — «задан» без подробностей: страница не должна падать из-за него."""
    if not url:
        return ''
    try:
        parts = urlsplit(url)
        host = parts.hostname or ''
        port = f':{parts.port}' if parts.port else ''
    except ValueError:
        return 'задан (адрес не разобрать — сохраните заново)'
    return f'{parts.scheme}://{host}{port}'


def public_view() -> Dict[str, Any]:
    """Состояние для страницы «Доступ агентов» — без самих секретов."""
    token, key, proxy = bot_token(), anthropic_key(), proxy_url()
    return {
        'telegram': {'configured': bool(token), 'source': token_source(), 'token_hint': hint(token),
                     'bot_username': bot_username()},
        'anthropic': {'configured': bool(key), 'source': _source(KEY_ANTHROPIC, ANTHROPIC_ENV),
                      'key_hint': hint(key)},
        'proxy': {'configured': bool(proxy), 'display': proxy_display(proxy)},
        'paused': paused(),
    }


# ------------------------------------------------------------------ запись

def _getme(token: str) -> Optional[Dict[str, Any]]:
    from core.open_check_telegram import api_call
    return api_call('getMe', {}, token=token)


def _check_key(key: str, proxy: str) -> Tuple[str, str]:
    from kultura_bot import claude
    return claude.check_key(key, proxy)


def _clean_proxy(value: Any) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    message = 'Прокси — адрес вида http://логин:пароль@хост:порт или https://хост:порт (порт — число 1–65535)'
    try:
        parts = urlsplit(text)
        port = parts.port                # порт не число или больше 65535 — ValueError
    except ValueError:
        raise ValueError(message) from None
    if parts.scheme not in PROXY_SCHEMES or not parts.hostname or port == 0:
        raise ValueError(message)
    return text


def save(*, token: Optional[str] = None, clear_token: bool = False,
         anthropic_key_value: Optional[str] = None, clear_anthropic_key: bool = False,
         proxy: Optional[str] = None, paused_value: Optional[bool] = None, by: str = '',
         getme: Optional[GetMe] = None, check_key: Optional[CheckKey] = None) -> Dict[str, Any]:
    """Сохранить переданное (None — не менять). Вернуть public_view() + warnings.

    Ошибка ввода — ValueError с текстом для владельца (API отдаёт его как 400).
    """
    from core.mcp import settings
    getme = getme or _getme
    check_key = check_key or _check_key
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

    new_proxy = None
    if proxy is not None:
        new_proxy = _clean_proxy(proxy)
        writes.append((KEY_PROXY, new_proxy))

    new_key = None
    if clear_anthropic_key:
        writes.append((KEY_ANTHROPIC, ''))
    elif anthropic_key_value is not None and anthropic_key_value.strip():
        new_key = anthropic_key_value.strip()
        if not ANTHROPIC_KEY_RE.fullmatch(new_key):
            raise ValueError('Это не ключ Claude API: он начинается с «sk-ant-». Скопируйте его из консоли '
                             'Anthropic (API Keys) целиком')
        writes.append((KEY_ANTHROPIC, new_key))

    # Ключ проверяем, если он новый или сменился прокси (с другим прокси он мог перестать доходить).
    key_to_check = new_key or (anthropic_key() if new_proxy is not None and not clear_anthropic_key else '')
    if key_to_check:
        kind, detail = check_key(key_to_check, new_proxy if new_proxy is not None else proxy_url())
        if kind == 'auth':
            raise ValueError(detail)
        if kind != 'ok':
            warnings.append(f'Ключ сохранён, но запрос к Anthropic не прошёл: {detail}')

    if paused_value is not None:
        if not isinstance(paused_value, bool):
            raise ValueError('Пауза: да или нет')
        writes.append((KEY_PAUSED, paused_value))

    for key, value in writes:
        settings.set(key, value, by=by)
    return dict(public_view(), warnings=warnings)
