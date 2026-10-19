"""Кто может говорить с ботом: Telegram, привязанный к администратору сайта.

Бот работает от имени администратора: видит зарплаты, выручку и телефоны гостей и по
прямой просьбе меняет данные. Поэтому он отвечает только тем, чей Telegram привязан к
активному администратору сайта. Списков id вручную нет (решение владельца 2026-10-18):

1. Администратор на странице «Доступ агентов» (/admin/mcp), раздел «Бот», нажимает
   «Подключить мой Telegram» — страница показывает ссылку t.me/<бот>?start=<код>. Код
   одноразовый, живёт 15 минут и привязан к этому администратору.
2. Он открывает ссылку в Telegram и жмёт «Старт» — бот получает /start <код> и
   запоминает: этот Telegram = этот администратор.
3. Дальше бот отвечает ему в личке, а в группах — когда к боту обратились. Привязку
   снимают на той же странице. Снятие флага администратора или отключение аккаунта
   действует сразу: права проверяются на каждом сообщении (actor_for) и на каждом вызове
   инструмента (core/mcp/bridge.owner_record).

Остальным бот отвечает одной фразой «Это закрытый бот…» не чаще раза в REFUSAL_EVERY_S
на человека и ничего не тратит.
"""
import secrets
import threading
import time
from typing import Any, Dict, Optional

from core.mcp.principal import ALL_DOMAINS, Principal
from kultura_bot import credentials, settings, store

REFUSAL_EVERY_S = 3600
CODE_BYTES = 12                     # token_urlsafe(12) = 16 символов [A-Za-z0-9_-]: годится для ?start=

_refused_at: Dict[str, float] = {}
_refused_lock = threading.Lock()


def _user(user_id: int) -> Optional[Dict[str, Any]]:
    from core.auth_manager import get_auth_manager
    return get_auth_manager().get_by_id(int(user_id))


def _is_admin(user: Optional[Dict[str, Any]]) -> bool:
    return bool(user and user.get('active') and user.get('is_admin'))


def link_url(code: str) -> str:
    return f'https://t.me/{credentials.bot_username()}?start={code}'


def create_code(user_id: int, login: str) -> Dict[str, Any]:
    """Одноразовая ссылка привязки для администратора: {code, url, expires_in_s}."""
    code = secrets.token_urlsafe(CODE_BYTES)
    store.add_link_code(code, user_id, login)
    return {'code': code, 'url': link_url(code), 'expires_in_s': store.LINK_CODE_TTL_S}


def link_by_code(code: str, tg_user_id: str, tg_name: str = '') -> Dict[str, Any]:
    """Привязать Telegram по коду из /start. {'ok': bool, 'text': ответ человеку}."""
    record = store.take_link_code(code) if code else None
    if record is None:
        return {'ok': False, 'text': ('Ссылка не подошла: она одноразовая и действует 15 минут. Откройте '
                                      f'{settings.ADMIN_PAGE_URL}, раздел «Бот», и нажмите «Подключить мой '
                                      'Telegram» ещё раз.')}
    user = _user(record['user_id'])
    if not _is_admin(user):
        return {'ok': False, 'text': 'Подключить бота может только активный администратор сайта.'}
    store.save_link(tg_user_id, user['id'], user['login'], tg_name=tg_name, by=user['login'])
    name = user.get('display_name') or user['login']
    return {'ok': True, 'text': f'Готово: вы подключены как {name}. Спрашивайте — я отвечу по данным сайта.'}


def actor_for(tg_user_id: Any) -> Optional[Dict[str, Any]]:
    """Кто пишет: привязанный активный администратор или None."""
    link = store.get_link(str(tg_user_id))
    if link is None:
        return None
    user = _user(link['user_id'])
    if not _is_admin(user):
        return None
    return {'tg_user_id': str(tg_user_id), 'user_id': user['id'], 'login': user['login'],
            'display_name': user.get('display_name') or user['login']}


def principal_for(actor: Dict[str, Any]) -> Principal:
    """Principal для моста MCP: инструменты сайта — от имени этого администратора."""
    return Principal(user_id=int(actor['user_id']), login=actor['login'], display_name=actor['display_name'],
                     token_id=f'tg_{actor["tg_user_id"]}', token_kind='telegram',
                     client_name=f'Бот @{credentials.bot_username()}', domains=(ALL_DOMAINS,), mode='full')


def refusal_due(tg_user_id: Any, now: Optional[float] = None) -> bool:
    """Пора ли ответить незнакомцу «закрытый бот» (не чаще раза в REFUSAL_EVERY_S)."""
    now = time.time() if now is None else now
    key = str(tg_user_id)
    with _refused_lock:
        last = _refused_at.get(key)
        if last is not None and now - last < REFUSAL_EVERY_S:
            return False
        _refused_at[key] = now
        if len(_refused_at) > 5000:            # не копим память на спамерах
            _refused_at.clear()
            _refused_at[key] = now
        return True


def refusal_text() -> str:
    return ('Это закрытый бот сети «Культура». Если вы администратор сайта, подключите Telegram на странице '
            f'{settings.ADMIN_PAGE_URL}, раздел «Бот».')


def links_view() -> list:
    """Привязки для страницы: кто, к какому логину, когда; без лишнего."""
    return [{'tg_user_id': r['tg_user_id'], 'login': r['login'], 'tg_name': r['tg_name'],
             'linked_at': r['linked_at']} for r in store.list_links()]
