"""Проверка доступа к MCP-коннектору: Bearer-токен -> Principal или отказ.

Порядок (контракт 4.3):
1. Заголовок `Authorization: Bearer <токен>`. Токен в строке запроса не принимается
   (спецификация авторизации MCP запрещает: адреса оседают в логах прокси).
2. Статический токен (core/mcp/tokens.py, префикс kmcp_).
3. Если не он — OAuth access token (core/mcp/oauth.py, импорт ленивый: модуля может
   ещё не быть). Токен OAuth привязан к адресу коннектора (RFC 8707), поэтому в
   проверку передаётся resource_url — полный адрес коннектора вместе с режимом:
   <сайт>/mcp[/<домен>][/<режим>]. Режим OAuth-токена (Principal.mode) ставит
   core/mcp/oauth.py по гранту.
4. Владелец токена по user_id из auth_manager: только АКТИВНЫЙ АДМИНИСТРАТОР
   (решение владельца 2026-09-27 «доступ пока только для меня»). Проверка на
   каждом запросе: пока владелец выключен или не администратор, его токены не
   действуют. При удалении, отключении и снятии админства routes/auth.py ещё и
   отзывает их (tokens.revoke_all_for_user, oauth.revoke_all_for_user) — возврат
   флага не оживляет старые токены.
5. Домен коннектора: токен на «content» не открывает /mcp/stocks и полный /mcp.
Режим доступа (read / draft / full) здесь не проверяется — его применяет protocol.py:
действует более строгий из режима токена и режима адреса.

Отказы:
    401 — нет токена, токен неизвестен/отозван/истёк, владелец не активный админ.
          Заголовок WWW-Authenticate: Bearer resource_metadata="<сайт>/.well-known/
          oauth-protected-resource<путь коннектора с режимом>" — по нему клиент Claude
          находит сервер авторизации (RFC 9728). Если токен был, но не подошёл,
          добавляется error="invalid_token" (RFC 6750, раздел 3.1).
    403 — токен действует, но не для этого коннектора: error="insufficient_scope".

authenticate() ВОЗВРАЩАЕТ Principal или AuthError (не бросает) — так вызывающему
коду не нужен try вокруг обычного отказа. AuthError — исключение, его можно и бросить.
Сбой хранилища (SQLite недоступна) — исключение наверх: это «повторите позже» (503),
а не «токен неверен» (401), иначе клиент зря начнёт авторизацию заново.
"""
import dataclasses
import logging
from typing import Optional, Union

from core.mcp.principal import Principal
from core.mcp.spec import DOMAINS, MODES

URL_MODES = tuple(m for m in MODES if m != 'full')    # full — адрес без суффикса

log = logging.getLogger('mcp.auth')

RESOURCE_METADATA_PATH = '/.well-known/oauth-protected-resource'


class AuthError(Exception):
    """Отказ в доступе: HTTP-код, текст для клиента и заголовок WWW-Authenticate."""

    def __init__(self, status: int, message: str, www_authenticate: str = ''):
        super().__init__(message)
        self.status = status
        self.message = message
        self.www_authenticate = www_authenticate


def connector_path(domain: Optional[str], mode: Optional[str] = None) -> str:
    """Путь коннектора: '/mcp', '/mcp/<домен>', плюс '/<режим>', если режим в адресе."""
    path = '/mcp' if domain is None else '/mcp/' + domain
    return path + ('/' + mode if mode else '')


def base_url(request) -> str:
    """Внешний адрес сайта без завершающего «/» (за Caddy — через ProxyFix)."""
    return request.host_url.rstrip('/')


def resource_url(request, domain: Optional[str], mode: Optional[str] = None) -> str:
    """Адрес коннектора — «resource» в терминах OAuth (RFC 8707)."""
    return base_url(request) + connector_path(domain, mode)


def resource_metadata_url(request, domain: Optional[str], mode: Optional[str] = None) -> str:
    """Где лежат метаданные защищённого ресурса этого коннектора (RFC 9728)."""
    return base_url(request) + RESOURCE_METADATA_PATH + connector_path(domain, mode)


def _quote(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def www_authenticate(request, domain: Optional[str], error: str = '', description: str = '',
                     mode: Optional[str] = None) -> str:
    """Значение WWW-Authenticate. Описание ошибки — латиницей: заголовок HTTP только ASCII."""
    parts = ['resource_metadata=' + _quote(resource_metadata_url(request, domain, mode))]
    if error:
        parts.append('error=' + _quote(error))
    if description:
        parts.append('error_description=' + _quote(description))
    return 'Bearer ' + ', '.join(parts)


def bearer_token(request) -> Optional[str]:
    """Токен из Authorization: Bearer … (схема без учёта регистра). None — заголовка нет."""
    header = (request.headers.get('Authorization') or '').strip()
    if not header:
        return None
    scheme, _, value = header.partition(' ')
    if scheme.lower() != 'bearer':
        return ''
    return value.strip()


def _verify_oauth(raw: str, resource: str) -> Optional[Principal]:
    """OAuth-проверка, если модуль есть. Сбой хранилища НЕ превращается в 401: иначе
    клиент решил бы, что токен плох, и погнал владельца заново авторизоваться. Исключение
    уходит наверх — protocol.handle_http отвечает 503 «повторите позже»."""
    try:
        from core.mcp import oauth
    except ImportError:
        return None
    verify = getattr(oauth, 'verify_access_token', None)
    if verify is None:
        return None
    return verify(raw, resource)


def authenticate(request, domain: Optional[str], mode: Optional[str] = None) -> Union[Principal, AuthError]:
    """Проверить запрос к коннектору domain (None — полный /mcp) с режимом адреса mode.

    mode — суффикс адреса (read | draft) или None (адрес без суффикса). См. докстринг модуля.
    """
    if domain is not None and domain not in DOMAINS:
        return AuthError(404, f'Нет коннектора /mcp/{domain}')
    if mode is not None and mode not in URL_MODES:
        return AuthError(404, f'Нет режима {mode}: в адресе бывает {", ".join(URL_MODES)}')
    raw = bearer_token(request)
    if not raw:
        return AuthError(401, 'Нужен токен доступа: заголовок Authorization: Bearer <токен>. '
                              'Токен выпускает владелец на странице «Доступ агентов» (/admin/mcp).',
                         www_authenticate(request, domain, mode=mode))
    from core.mcp import tokens
    principal = tokens.verify_static(raw)
    if principal is None:
        principal = _verify_oauth(raw, resource_url(request, domain, mode))
    if principal is None:
        return AuthError(401, 'Токен недействителен: неизвестен, отозван или истёк.',
                         www_authenticate(request, domain, 'invalid_token', 'token is unknown, revoked or expired',
                                          mode=mode))
    from core.auth_manager import get_auth_manager
    user = get_auth_manager().get_by_id(principal.user_id)   # сбой БД — наверх (503), не «нет доступа»
    if not user or not user.get('active') or not user.get('is_admin'):
        return AuthError(401, 'Нет доступа: владелец токена не активный администратор.',
                         www_authenticate(request, domain, 'invalid_token', 'token owner is not an active admin',
                                          mode=mode))
    principal = dataclasses.replace(principal, login=user.get('login') or principal.login,
                                    display_name=user.get('display_name') or principal.display_name)
    if not principal.allows(domain):
        where = connector_path(domain, mode)
        return AuthError(403, f'Токен не для этого коннектора ({where}). Разделы токена: '
                              f'{", ".join(principal.domains)}.',
                         www_authenticate(request, domain, 'insufficient_scope',
                                          'token is not valid for this connector', mode=mode))
    return principal
