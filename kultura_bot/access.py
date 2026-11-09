"""Кто может говорить с ботом: администратор сайта со своим Telegram или человек из списка ников.

Бот работает от имени администратора: видит зарплаты, выручку и телефоны гостей и по
прямой просьбе меняет данные. Поэтому он отвечает только двум группам людей; остальным —
одна фраза «Это закрытый бот…» (kultura_bot/engine/service.py). Списков id вручную нет
(решение владельца 2026-10-18).

Администраторы сайта:

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

Люди по нику Telegram (решение владельца 2026-11-09, settings.TELEGRAM_USERNAMES): аккаунта на
сайте у них нет, права в боте те же, что у администратора («всё, как мне»). Владелец присылает им
ссылку t.me/<бот>, они жмут «Старт»:

1. Сервер бота передаёт сайту вместе с номером аккаунта ник и имя из сообщения
   (GET /api/bot/actor/<id>?username=…&name=…).
2. Ник есть в списке и ещё ни за кем не закреплён — сайт закрепляет его за этим аккаунтом
   (store.pin_guest, таблица bot_guests) и пишет владельцу в личку от бота: кто подключился.
3. Дальше человека узнают по номеру аккаунта, ник не нужен: сменил ник — бот его по-прежнему
   знает; другой аккаунт с тем же ником (ник освободили и заняли) не войдёт. Доступ закрывает
   удаление ника из списка: закреплённый ник без строки в списке не пускает.

Вход по нику (`login` в журнале и в служебной строке) — '@ник': так его не спутать с логином сайта.
"""
import logging
import re
import secrets
import threading
from typing import Any, Dict, List, Optional

from kultura_bot import credentials, settings, store

log = logging.getLogger(__name__)

CODE_BYTES = 12                     # token_urlsafe(12) = 16 символов [A-Za-z0-9_-]: годится для ?start=
# Ник Telegram: латиница, цифры и «_», от 5 до 32 символов (правила Telegram); короче 5 бывают только
# коллекционные ники — их тоже пропускаем, длина от 1.
USERNAME_RE = re.compile(r'[A-Za-z0-9_]{1,32}')


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


# ------------------------------------------------------------------ люди по нику

def _listed() -> Dict[str, str]:
    """Ники из settings.TELEGRAM_USERNAMES: строчными -> как записан (для страницы), порядок списка."""
    out: Dict[str, str] = {}
    for raw in getattr(settings, 'TELEGRAM_USERNAMES', ()) or ():
        name = str(raw or '').strip().lstrip('@')
        if USERNAME_RE.fullmatch(name):
            out.setdefault(name.lower(), name)
    return out


def _clean_username(username: Any) -> str:
    name = str(username or '').strip().lstrip('@')
    return name.lower() if USERNAME_RE.fullmatch(name) else ''


def _guest_actor(pin: Dict[str, Any]) -> Dict[str, Any]:
    login = '@' + pin['username']
    return {'tg_user_id': str(pin['tg_user_id']), 'user_id': None, 'login': login,
            'display_name': pin.get('tg_name') or login, 'guest': True}


def _background(fn, *args) -> None:
    """Письмо владельцу — в отдельном потоке: сервер бота ждёт ответа «кто пишет» (тесты подменяют)."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def _send(chat_id: str, text: str, token: str) -> bool:
    """sendMessage от бота kultura.research (тесты подменяют)."""
    from core.open_check_telegram import api_call
    data = api_call('sendMessage', {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True},
                    timeout=20, token=token)
    return bool(data and data.get('ok'))


def owner_chats() -> List[str]:
    """Личные чаты владельца сайта с ботом: его привязанные аккаунты Telegram (номер чата = номер аккаунта)."""
    try:
        from core.auth_manager import get_auth_manager
        owner = get_auth_manager().owner_id()
    except Exception:  # noqa: BLE001 — без базы пользователей просто некому писать
        log.exception('[BOT] владелец сайта не определён')
        return []
    if owner is None:
        return []
    return [link['tg_user_id'] for link in store.list_links() if link['user_id'] == owner]


def notify_new_guest(pin: Dict[str, Any]) -> None:
    """Сообщить владельцу: ник из списка закрепился за аккаунтом Telegram. Не вышло — только в лог."""
    token = credentials.bot_token()           # от имени kultura.research; нет токена — бот и так молчит
    chats = owner_chats()
    if not token or not chats:
        log.warning('[BOT] @%s подключился, владельцу не сообщить: %s', pin['username'],
                    'нет токена бота' if not token else 'у владельца не подключён Telegram')
        return
    name = f' ({pin["tg_name"]})' if pin.get('tg_name') else ''
    text = (f'kultura.research: подключился @{pin["username"]}{name} — ник из вашего списка, бот закрепил его '
            f'за аккаунтом Telegram {pin["tg_user_id"]} и отвечает ему, как вам.\n\n'
            'Если это не тот человек — уберите ник из TELEGRAM_USERNAMES в kultura_bot/settings.py; срочно — '
            f'«Пауза» бота на странице {settings.ADMIN_PAGE_URL}.')
    for chat_id in chats:
        try:
            if not _send(chat_id, text, token):
                log.warning('[BOT] Telegram не принял сообщение владельцу о @%s', pin['username'])
        except Exception:  # noqa: BLE001
            log.exception('[BOT] сообщение владельцу о @%s не ушло', pin['username'])


def guest_for(tg_user_id: Any, username: Any = '', tg_name: str = '') -> Optional[Dict[str, Any]]:
    """Человек по нику из settings.TELEGRAM_USERNAMES или None (ник не в списке, занят другим аккаунтом)."""
    listed = _listed()
    tg_user_id = str(tg_user_id)
    pin = store.get_guest(tg_user_id)
    if pin is None:
        name = _clean_username(username)
        if not name or name not in listed:
            return None
        pin, created = store.pin_guest(tg_user_id, name, str(tg_name or ''))
        if pin is None:                        # ник закреплён за другим аккаунтом Telegram
            log.warning('[BOT] ник @%s уже закреплён за другим аккаунтом — аккаунт %s не пущен', name, tg_user_id)
            return None
        if created:
            _background(notify_new_guest, dict(pin))
    elif tg_name and tg_name != pin.get('tg_name'):
        store.rename_guest(tg_user_id, tg_name)
        pin = dict(pin, tg_name=tg_name[:100])
    if pin['username'] not in listed:          # ник убрали из списка — доступ закрыт
        return None
    return _guest_actor(pin)


def actor_for(tg_user_id: Any, username: Any = '', tg_name: str = '') -> Optional[Dict[str, Any]]:
    """Кто пишет: привязанный активный администратор, человек из списка ников или None.

    username и tg_name — из сообщения (сервер бота передаёт их сайту); нужны только в первый раз,
    чтобы закрепить ник, потом человека узнают по номеру аккаунта."""
    link = store.get_link(str(tg_user_id))
    if link is not None:
        user = _user(link['user_id'])
        if _is_admin(user):
            return {'tg_user_id': str(tg_user_id), 'user_id': user['id'], 'login': user['login'],
                    'display_name': user.get('display_name') or user['login']}
    return guest_for(tg_user_id, username, tg_name)


def links_view() -> list:
    """Привязки для страницы: кто, к какому логину, когда; без лишнего."""
    return [{'tg_user_id': r['tg_user_id'], 'login': r['login'], 'tg_name': r['tg_name'],
             'linked_at': r['linked_at']} for r in store.list_links()]


def guests_view() -> list:
    """Ники для страницы: из списка (писал ли уже боту) и закреплённые, но убранные из списка."""
    listed = _listed()
    pins = {g['username']: g for g in store.list_guests()}
    rows = []
    for name, shown in listed.items():
        pin = pins.get(name) or {}
        rows.append({'username': shown, 'listed': True, 'tg_user_id': pin.get('tg_user_id', ''),
                     'tg_name': pin.get('tg_name', ''), 'first_seen': pin.get('first_seen', '')})
    for name, pin in pins.items():
        if name not in listed:
            rows.append({'username': name, 'listed': False, 'tg_user_id': pin['tg_user_id'],
                         'tg_name': pin['tg_name'], 'first_seen': pin['first_seen']})
    return rows
