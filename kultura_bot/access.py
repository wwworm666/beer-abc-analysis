"""Кто может говорить с ботом: Telegram, привязанный к администратору сайта.

Бот работает от имени администратора: видит зарплаты, выручку и телефоны гостей и по
прямой просьбе меняет данные. Поэтому он отвечает только тем, чей Telegram привязан к
активному администратору сайта. Списков id вручную нет (решение владельца 2026-10-18):

1. Администратор на странице «Доступ агентов» (/admin/mcp), раздел «Бот», нажимает
   «Подключить мой Telegram» — страница показывает ссылку t.me/<бот>?start=<код>. Код
   одноразовый, живёт 15 минут и привязан к этому администратору.
2. Он открывает ссылку в Telegram и жмёт «Старт» — сервер бота получает /start <код> и
   передаёт сайту (POST /api/bot/link -> link_by_code): этот Telegram = этот администратор.
3. Дальше бот отвечает ему в личке, а в группах — когда к боту обратились. Привязку
   снимают на той же странице. Снятие флага администратора или отключение аккаунта
   действует сразу: сервер бота спрашивает сайт на каждом сообщении (GET
   /api/bot/actor/<id> -> actor_for), а отзыв доступа снимает и привязки
   (routes/auth._revoke_agent_access).

Остальным бот отвечает одной фразой «Это закрытый бот…» (kultura_bot/engine/service.py).
"""
import secrets
from typing import Any, Dict, Optional

from kultura_bot import credentials, settings, store

CODE_BYTES = 12                     # token_urlsafe(12) = 16 символов [A-Za-z0-9_-]: годится для ?start=


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


def links_view() -> list:
    """Привязки для страницы: кто, к какому логину, когда; без лишнего."""
    return [{'tg_user_id': r['tg_user_id'], 'login': r['login'], 'tg_name': r['tg_name'],
             'linked_at': r['linked_at']} for r in store.list_links()]
