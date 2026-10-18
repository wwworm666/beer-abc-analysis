"""Проверка initData мини-приложения Telegram (вход в /api/tg/charts/<id>).

## Что это

Мини-приложение получает от клиента Telegram строку initData: кто открыл, когда,
с каким start_param, и подпись. Страница присылает её в заголовке
`Authorization: tma <initData>`; сервер проверяет подпись токеном бота и пускает
только людей из списка допущенных. Cookie сайта мини-приложению не нужны: вход
сайта и вход Telegram не смешиваются.

## Как проверяется (документация Telegram, «Validating data received via the Mini App»)

1. initData — строка запроса: `auth_date=…&query_id=…&user=%7B…%7D&signature=…&hash=…`.
   Разбираем её (значения раскодированы), повтор ключа — отказ.
2. data-check-string — все поля, КРОМЕ hash, по алфавиту, в виде `ключ=значение`,
   через перевод строки. signature остаётся в строке (это подпись Ed25519 для
   проверки без токена бота, она тоже входит в данные, которые подписал hash).
3. secret_key = HMAC-SHA256(ключ = "WebAppData", сообщение = токен бота).
4. hash должен совпасть с hex(HMAC-SHA256(ключ = secret_key, сообщение = data-check-string));
   сравнение за постоянное время (hmac.compare_digest).
5. auth_date — не старше INIT_DATA_MAX_AGE_S (сутки) и не из будущего дальше
   CLOCK_SKEW_S (5 минут расхождения часов). Старая подпись — отказ: initData,
   утёкшая из чужого телефона или лога, работает не дольше суток.
6. user — JSON с целым id. Допущены id из TG_MINIAPP_ALLOWED_IDS (через запятую).

initData — пропуск на сутки, поэтому её не пишем в журналы ни целиком, ни частями;
Caddy по умолчанию скрывает заголовок Authorization в журнале доступа.
"""
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any, Dict, FrozenSet, Optional
from urllib.parse import parse_qsl

INIT_DATA_MAX_AGE_S = 24 * 3600      # сутки: дольше одной сессии мини-приложения
CLOCK_SKEW_S = 300                   # 5 минут: часы клиента Telegram и сервера
INIT_DATA_MAX_CHARS = 8192           # реальная initData ~0,5–1 КБ; больше — не от Telegram
AUTH_SCHEME = 'tma'
_HASH_RE = re.compile(r'[0-9a-f]{64}')    # hex SHA-256 в нижнем регистре, как шлёт Telegram

BOT_TOKEN_ENV = 'TELEGRAM_MCP_BOT_TOKEN'
ALLOWED_IDS_ENV = 'TG_MINIAPP_ALLOWED_IDS'


class InitDataError(Exception):
    """initData не прошла проверку. code — для ответа API, текст — для человека."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def bot_token() -> str:
    """Токен бота, к которому привязано мини-приложение (@MCPkulturabot)."""
    return (os.environ.get(BOT_TOKEN_ENV) or '').strip()


def allowed_user_ids() -> FrozenSet[int]:
    """Telegram id людей, которым можно открыть график. Пусто — никому."""
    raw = os.environ.get(ALLOWED_IDS_ENV) or ''
    ids = set()
    for part in raw.replace(';', ',').split(','):
        part = part.strip()
        if part.isascii() and part.isdigit():   # у людей id положительные; группы (с минусом) не люди
            ids.add(int(part))
    return frozenset(ids)


def init_data_from_header(header: Optional[str]) -> str:
    """`tma <initData>` -> initData; другая схема или пусто -> ''."""
    if not header:
        return ''
    scheme, _, value = header.strip().partition(' ')
    if scheme.lower() != AUTH_SCHEME:
        return ''
    return value.strip()


def secret_key(token: str) -> bytes:
    return hmac.new(b'WebAppData', token.encode('utf-8'), hashlib.sha256).digest()


def data_check_string(fields: Dict[str, str]) -> str:
    return '\n'.join(f'{key}={fields[key]}' for key in sorted(fields) if key != 'hash')


def sign(fields: Dict[str, str], token: str) -> str:
    """hex-подпись полей (без hash) — как её считает Telegram. Нужна проверке и тестам."""
    return hmac.new(secret_key(token), data_check_string(fields).encode('utf-8'), hashlib.sha256).hexdigest()


def validate(init_data: str, token: str, *, now: Optional[float] = None,
             max_age: int = INIT_DATA_MAX_AGE_S) -> Dict[str, Any]:
    """Проверить initData. Вернуть {'user': {...}, 'user_id', 'auth_date', 'start_param'}.

    Ошибка — InitDataError с кодом: missing, malformed, bad_hash, expired, no_user.
    """
    if not init_data:
        raise InitDataError('missing', 'Нет initData: откройте график из Telegram')
    if len(init_data) > INIT_DATA_MAX_CHARS:
        raise InitDataError('malformed', 'initData слишком длинная')
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise InitDataError('malformed', 'initData не разбирается') from None
    fields: Dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise InitDataError('malformed', 'initData: повтор поля')
        fields[key] = value
    received = fields.get('hash') or ''
    if not token or not _HASH_RE.fullmatch(received) or not hmac.compare_digest(sign(fields, token), received):
        raise InitDataError('bad_hash', 'Подпись initData не сходится')

    try:
        auth_date = int(fields.get('auth_date') or '')
    except ValueError:
        raise InitDataError('malformed', 'initData: нет auth_date') from None
    now = time.time() if now is None else now
    if now - auth_date > max_age:
        raise InitDataError('expired', 'Сессия Telegram устарела: закройте график и откройте его заново')
    if auth_date - now > CLOCK_SKEW_S:
        raise InitDataError('expired', 'initData из будущего: проверьте часы устройства')

    try:
        user = json.loads(fields.get('user') or '')
    except ValueError:
        user = None
    user_id = user.get('id') if isinstance(user, dict) else None
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise InitDataError('no_user', 'initData: нет пользователя')
    return {'user': user, 'user_id': user_id, 'auth_date': auth_date,
            'start_param': fields.get('start_param') or ''}
