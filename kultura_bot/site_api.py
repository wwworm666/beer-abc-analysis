"""Сайт <-> сервер бота: ключ сервера, команда установки, API бота, состояние для страницы.

Сам бот работает на сервере в Амстердаме (kultura_bot/engine/): сайт стоит в России, где
API Anthropic недоступен, и к Anthropic не обращается. Сайт хранит настройки и привязки и
отвечает серверу бота.

## Ключ сервера бота

Статический MCP-токен (core/mcp/tokens.py: kmcp_…, все разделы, полный режим, без срока)
выпускает кнопка «Команда установки» на странице «Доступ агентов»; его id — в settings
(ENGINE_TOKEN_KEY). Новая команда выпускает новый ключ и отзывает прежний: старый сервер
бота замолкает. Ключ виден в списке «Статические токены» той же страницы — там его можно
отозвать.

Ключ открывает MCP (инструменты — как у агентов владельца, в журнале вызовов клиент
ENGINE_TOKEN_NAME) и API бота (/api/bot/*, routes/bot_api.py) — только с ним сайт отдаёт
секреты (токен Telegram, ключ Anthropic). Другие MCP-токены API бота не открывают:
агент не получает секреты бота. Владелец ключа — администратор, нажавший кнопку: его
отключение или снятие админства отзывает ключ (routes/auth._revoke_agent_access) — бот
замолкает до новой установки.

## Команда установки

    curl -fsSL <settings.INSTALL_SCRIPT_URL> | KULTURA_BOT_KEY='kmcp_…' bash

Выполняется один раз на сервере в Амстердаме под root (kultura_bot/deploy/install.sh):
ставит бота службой и самообновление из GitHub. Показывается один раз; в базе — только
хэш ключа. Новая команда стирает прежнее состояние сервера: до первого отчёта нового
страница пишет «ещё не отзывался».

## Отчёт сервера бота (POST /api/bot/report)

    {"status": {"state": …, "detail": …, "claude_error": …, "bot": …},
     "usage": [{"day", "model", "requests", "input_tokens", "output_tokens",
                "cache_read", "cache_write", "cost_usd"}, …]}

Состояние пишется в settings с временем прихода (store.set_status), расход прибавляется
к bot_usage. Отчёта нет дольше STALE_AFTER_S — страница пишет «сервер бота не отвечает».
"""
import re
import time
from typing import Any, Dict, Optional

from kultura_bot import credentials, settings, store

ENGINE_TOKEN_KEY = 'kultura_bot_engine_token'
ENGINE_TOKEN_NAME = 'Бот @MCPkulturabot — сервер в Амстердаме'
STALE_AFTER_S = 3 * 60                 # сервер бота отчитывается раз в минуту
STATES = ('starting', 'waiting', 'paused', 'running', 'conflict', 'error', 'stopped')
MAX_USAGE_ITEMS = 100
MAX_TOKENS_FIELD = 10 ** 10
MAX_COST_ITEM_USD = 1000.0
DAY_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
MODEL_RE = re.compile(r'[a-z0-9][a-z0-9.\-]{0,63}')


def _settings():
    from core.mcp import settings as mcp_settings
    return mcp_settings


# ------------------------------------------------------------------ ключ и установка

def engine_token_id() -> str:
    value = _settings().get(ENGINE_TOKEN_KEY)
    return value if isinstance(value, str) else ''


def install_command(raw_key: str) -> str:
    return f"curl -fsSL {settings.INSTALL_SCRIPT_URL} | KULTURA_BOT_KEY='{raw_key}' bash"


def issue_install(user: Dict[str, Any]) -> Dict[str, Any]:
    """Новый ключ сервера бота (прежний отзывается) и команда установки с ним — один раз."""
    from core.mcp import tokens
    by = user.get('login') or ''
    raw, row = tokens.create(user, ENGINE_TOKEN_NAME, domains=['*'], expires_days=None, mode='full')
    old = engine_token_id()
    _settings().set(ENGINE_TOKEN_KEY, row['id'], by=by)
    if old and old != row['id']:
        tokens.revoke(old, by=by)
    store.clear_status(by=by)           # прежний сервер замолчал; страница ждёт отчёта нового
    return {'command': install_command(raw), 'token_prefix': row.get('prefix') or raw[:12],
            'script_url': settings.INSTALL_SCRIPT_URL}


def verify_engine(raw: Optional[str]):
    """Principal ключа сервера бота или None: не тот токен, отозван, владелец не активный админ."""
    from core.mcp import tokens
    principal = tokens.verify_static(raw)
    expected = engine_token_id()
    if principal is None or not expected or principal.token_id != expected:
        return None
    from core.auth_manager import get_auth_manager
    user = get_auth_manager().get_by_id(principal.user_id)
    if not user or not user.get('active') or not user.get('is_admin'):
        return None
    return principal


def engine_info() -> Dict[str, Any]:
    """Ключ сервера для страницы: установлен ли, начало ключа, когда выпущен и использован."""
    token_id = engine_token_id()
    if not token_id:
        return {'issued': False}
    from core.mcp import tokens
    row = tokens.get(token_id)
    if not row:
        return {'issued': False}
    return {'issued': True, 'active': row.get('status') == 'active', 'prefix': row.get('prefix'),
            'created_at': row.get('created_at'), 'last_used_at': row.get('last_used_at'),
            'owner': row.get('user_login')}


# ------------------------------------------------------------------ отчёт сервера бота

def _short(value: Any, limit: int = 500) -> str:
    return str(value or '')[:limit]


def accept_report(payload: Any) -> None:
    """Проверить и сохранить отчёт. Ошибка ввода — ValueError (API отвечает 400)."""
    if not isinstance(payload, dict):
        raise ValueError('Отчёт — объект JSON')
    status = payload.get('status')
    usage = payload.get('usage')
    usage = [] if usage is None else usage
    if not isinstance(status, dict) or status.get('state') not in STATES:
        raise ValueError(f'status.state — одно из: {", ".join(STATES)}')
    if not isinstance(usage, list) or len(usage) > MAX_USAGE_ITEMS:
        raise ValueError(f'usage — список не длиннее {MAX_USAGE_ITEMS}')
    items = []
    for item in usage:
        if not isinstance(item, dict):
            raise ValueError('usage: каждый элемент — объект')
        day, model = str(item.get('day') or ''), str(item.get('model') or '')
        if not DAY_RE.fullmatch(day) or not MODEL_RE.fullmatch(model):
            raise ValueError('usage: day — YYYY-MM-DD, model — имя модели')
        counts = {}
        for key in store.USAGE_FIELDS:
            value = item.get(key, 0)
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_TOKENS_FIELD:
                raise ValueError(f'usage.{key} — целое от 0')
            counts[key] = value
        cost = item.get('cost_usd', 0)
        if not isinstance(cost, (int, float)) or isinstance(cost, bool) or not 0 <= cost <= MAX_COST_ITEM_USD:
            raise ValueError('usage.cost_usd — число от 0')
        items.append((day, model, counts, float(cost)))
    for day, model, counts, cost in items:
        store.add_usage(day, model, counts, cost)
    store.set_status(status['state'], _short(status.get('detail')), claude_error=_short(status.get('claude_error')),
                     bot=_short(status.get('bot'), 64))


# ------------------------------------------------------------------ страница

def status_view() -> Dict[str, Any]:
    """Состояние для страницы: что делает сервер бота, свежесть отчёта, расход, привязки."""
    from kultura_bot import access
    from kultura_bot.engine import config
    status = store.get_status()
    age = time.time() - float(status.get('at_ts') or 0)
    stale = status.get('state') not in ('stopped', None) and bool(status.get('at_ts')) and age > STALE_AFTER_S
    return {'status': dict(status, stale=stale), 'usage': store.usage_summary(30),
            'budget_usd': settings.DAILY_BUDGET_USD, 'model': settings.MODEL, 'effort': settings.EFFORT,
            'agent_effort': settings.AGENT_EFFORT, 'fast_mode': settings.FAST_MODE,
            'links': access.links_view(), 'engine': engine_info(),
            'agents': [{'name': a.name, 'title': a.title} for a in config.load_agents().values()]}


def page_view(warnings=None) -> Dict[str, Any]:
    """Ответ GET/PUT /api/admin/mcp/bot: секреты подсказками + состояние сервера бота."""
    return dict(credentials.public_view(), **status_view(), warnings=list(warnings or []))
