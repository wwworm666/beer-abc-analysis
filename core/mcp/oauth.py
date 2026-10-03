"""OAuth 2.1 для приложения Claude и расписаний Claude (авторизация MCP).

Что это
-------
Claude Code подключается к /mcp по статическому токену (core/mcp/tokens.py), а
пользовательский коннектор в приложении Claude (claude.ai, Desktop, мобильное,
Cowork) и расписания Claude умеют подключаться только по OAuth. Этот модуль —
сервер авторизации (authorization server) для MCP-коннекторов сервиса и проверка
выданных им токенов. HTTP-обвязка — routes/mcp_oauth.py, страница согласия —
templates/mcp_consent.html. Доступ — только у активного администратора
(решение владельца 2026-09-27, «доступ пока только для меня»).

Стандарты (актуальная ревизия MCP на 2026-09-27 — 2026-07-28):
- MCP Authorization: modelcontextprotocol.io/specification/2026-07-28/basic/authorization;
- OAuth 2.1 (draft-ietf-oauth-v2-1-13): только authorization code + PKCE S256;
- RFC 9728 — метаданные защищённого ресурса (где сервер авторизации);
- RFC 8414 — метаданные сервера авторизации;
- RFC 7591 — динамическая регистрация клиента (DCR);
- RFC 8707 — resource indicator: токен привязан к URL коннектора;
- RFC 7009 — отзыв токена; RFC 9207 — параметр iss в ответе авторизации.

Как подключается Claude (по шагам)
----------------------------------
1. POST /mcp/stocks без токена -> 401 и заголовок
   WWW-Authenticate: Bearer resource_metadata="<base>/.well-known/oauth-protected-resource/mcp/stocks"
   (это делает routes/mcp.py; адрес строит protected_resource_metadata_url()).
2. GET этого адреса -> {"resource": "<base>/mcp/stocks", "authorization_servers": ["<base>"], ...}.
3. GET <base>/.well-known/oauth-authorization-server -> адреса /oauth/authorize, /oauth/token,
   /oauth/register, /oauth/revoke и поддерживаемые режимы.
4. POST /oauth/register (DCR) -> client_id. Claude регистрируется заново на каждое новое
   подключение, поэтому регистрация публичная и ограничена по частоте.
5. Браузер владельца: GET /oauth/authorize?... -> вход на сайт (если нужно) -> страница
   согласия -> «Разрешить» -> 303 на https://claude.ai/api/mcp/auth_callback?code=…&state=…&iss=…
6. POST /oauth/token: code + code_verifier -> access (1 час) + refresh (30 дней).
7. Каждый вызов MCP: Authorization: Bearer kmcpo_… -> verify_access_token(raw, url_коннектора).
8. За несколько минут до истечения или по 401 Claude меняет refresh на новую пару (ротация).

<base> — request.host_url без завершающего «/»: https://beerkultura.ru в проде (Caddy +
ProxyFix из core/auth_guard.py делают host_url внешним https-адресом).

Правила (что проверяется и почему)
----------------------------------
- Коннекторы (resource, RFC 8707): <base>/mcp — все разделы, <base>/mcp/<домен> — один
  домен из core.mcp.spec.DOMAINS; к обоим можно добавить суффикс режима доступа
  /read или /draft (без суффикса — full), всего 15 адресов (connector_urls). Сравнение —
  в каноническом виде canonical_url(): схема и хост в нижнем регистре, без порта по
  умолчанию, без «/» в конце, без фрагмента (Claude присылает resource именно так).
  Запрос без resource -> коннектор /mcp (full).
- Режим доступа (spec.MODES: read — только чтение, draft — чтение и черновики, full —
  всё). Режим адреса — из суффикса resource. На странице согласия владелец выбирает режим
  гранта: равный режиму адреса или строже (allowed_modes/choose_mode; по умолчанию —
  режим адреса). Режим хранится в гранте, переживает ротацию refresh и приходит в
  Principal.mode; протокол применяет более строгий из режима токена и режима адреса.
- Аудитория токена (token_domains_for): точное совпадение resource с адресом вызова.
  Единственное расширение: токен полного коннектора /mcp[/<режим>] (домены «*»)
  принимается на /mcp/<домен>[/<тот же режим>] того же сайта — режим адреса должен
  совпасть точно (токен /mcp/read — только на /mcp/<домен>/read). Прав это не расширяет.
  Токен /mcp/<домен>/draft не работает на /mcp/<домен> (full), на /mcp/<домен>/read, на
  другом домене и на /mcp/draft (защита от смешения коннекторов и режимов).
- redirect_uri: абсолютный http(s)-адрес без фрагмента, логина/пароля в адресе, пробелов,
  обратной косой черты и не-ASCII (иначе браузер и Python по-разному поймут хост — классика
  открытого редиректа). Хост — из списка разрешённых (настройка oauth_redirect_hosts в
  core/mcp/settings.py, по умолчанию DEFAULT_REDIRECT_HOSTS). https обязателен, кроме
  loopback (localhost, 127.0.0.1, ::1). Для claude.ai и claude.com путь закреплён:
  только /api/mcp/auth_callback (PINNED_CALLBACK_PATHS) — разрешённый хост не значит, что
  любая страница на нём может принять код.
- Сравнение redirect_uri при авторизации — точное строковое; для loopback порт не
  сравнивается (RFC 8252 §7.3; Claude Code слушает случайный порт в каждой сессии).
- Никогда не перенаправляем на незарегистрированный адрес: неизвестный клиент или чужой
  redirect_uri -> страница ошибки (AuthorizeError без redirect_uri), а не редирект.
- PKCE обязателен, только S256: code_challenge = BASE64URL(SHA256(code_verifier)) без «=»
  (RFC 7636 §4.2), вызов длиной ровно 43 символа; code_verifier — 43..128 символов из
  [A-Za-z0-9-._~]. Метод plain и запрос без вызова отклоняются.
- Код авторизации: 10 минут, одноразовый, хранится как sha256. Повторное предъявление уже
  использованного кода (кем угодно) отзывает все токены, выданные по нему (RFC 6749
  §4.1.2), — это признак перехвата кода.
- Refresh-токен: 30 дней от выдачи, ротация при каждом обмене (старый сразу недействителен).
  Повтор старого refresh позже REFRESH_REUSE_GRACE секунд после ротации — признак кражи:
  отзываем всю цепочку (грант). Повтор внутри окна — вероятная гонка двух параллельных
  обновлений того же клиента: отвечаем invalid_grant, цепочку не трогаем.
- Новое согласие того же клиента на тот же коннектор заменяет прежний грант (старые токены
  отзываются, reason='superseded'): у одного подключения одна живая цепочка.
- Токен действует, только пока владелец — существующий активный администратор; это же
  повторно проверяет core/mcp/auth.py на каждом вызове. При удалении, отключении и снятии
  админа routes/auth.py вызывает revoke_all_for_user(): гранты и токены отзываются, чтобы
  возврат флага не оживил старые подключения.
- Все секреты (коды, токены, client_secret) хранятся только как sha256; сырые значения
  не пишутся ни в БД, ни в лог.
- Описания ошибок протокола (error_description) — ASCII по-английски: RFC 6749 §5.2 и
  RFC 7591 §3.2.2 запрещают в нём символы вне ASCII. Всё, что видит человек (страница
  согласия и ошибок), — по-русски (AuthorizeError.message_ru, шаблон).

Форматы
-------
access  `kmcpo_` + 43 символа secrets.token_urlsafe(32) (256 бит)
refresh `kmcpr_` + 43 символа
client_id `kmcpc_` + 24 символа (публичный, не секрет); client_secret `kmcps_` + 43 символа
token_id (для журнала и Principal.token_id): `oa_` + 12 hex у access, `or_` + 12 hex у refresh.

Время хранится целыми секундами Unix (сравнения сроков), наружу отдаётся ISO по Москве
(core.msk_time.MOSCOW_TZ, фиксированное +03:00).

Крайние случаи
--------------
- Нет модуля core/mcp/settings.py или сбой чтения -> DEFAULT_REDIRECT_HOSTS. Пустой список
  в настройке — осознанное «никаких хостов»: регистрация и вход по OAuth закрыты.
- Хост убрали из списка после регистрации -> авторизация этого клиента даёт страницу ошибки.
- revoke_client() гасит все токены и гранты клиента и отключает сам client_id: новые
  авторизации по нему — страница ошибки; Claude при новом подключении регистрируется заново.
- Регистрация (DCR) — публичная точка, поэтому ограничена со всех сторон: тело не больше
  MAX_REGISTRATION_BYTES (4 КБ, все метаданные), не больше MAX_REDIRECT_URIS (5) адресов по
  MAX_URI_LEN (512) символов, имя до MAX_CLIENT_NAME (100) символов. Лимит частоты — по
  адресу (IPv6 — по сети /64) в памяти процесса: LRU не больше REG_LIMITER_MAX_KEYS ключей
  (в проде 2 воркера gunicorn — фактически вдвое больше); общий лимит в час считается по
  БД и действует на все воркеры.
- Регистрации без единого гранта старше UNUSED_CLIENT_TTL (сутки) удаляются при каждой
  новой регистрации; истёкшие коды и токены и пустые гранты чистятся попутно (не чаще
  раза в CLEANUP_EVERY секунд на процесс).
- CIMD (client_id в виде URL) сознательно НЕ поддерживается и не объявляется: серверу
  пришлось бы ходить наружу за документом клиента (SSRF-риск; с прод-сервера claude.ai может
  быть недоступен). Claude без client_id_metadata_document_supported использует DCR.
"""

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit, urlunsplit

from core.mcp import db
from core.mcp.principal import ALL_DOMAINS, Principal
from core.mcp.spec import DOMAINS, MODE_TITLES, MODES, stricter_mode
from core.msk_time import MOSCOW_TZ

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ сроки

ACCESS_TOKEN_TTL = 60 * 60              # 1 час (контракт 4.3). Короткий срок ограничивает вред
                                        # утёкшего токена (MCP: access tokens SHOULD be short-lived).
REFRESH_TOKEN_TTL = 30 * 24 * 60 * 60   # 30 дней с ротацией (контракт 4.3): подключение живёт,
                                        # пока Claude пользуется им хотя бы раз в 30 дней.
CODE_TTL = 10 * 60                      # 10 минут (контракт 4.3; OAuth 2.1 рекомендует <= 10 мин).
REFRESH_REUSE_GRACE = 120               # сек. Повтор старого refresh в это окно после ротации —
                                        # гонка параллельных обновлений (два разговора/расписания
                                        # Claude одновременно), а не кража; позже — кража.
LAST_USED_WRITE_EVERY = 60              # сек. Отметку «последнее использование» пишем не чаще,
                                        # чтобы не брать write-лок mcp.db на каждый вызов MCP.
UNUSED_CLIENT_TTL = 24 * 60 * 60        # регистрация без единого гранта удаляется через сутки
                                        # (при каждой новой регистрации): Claude регистрируется
                                        # на каждое подключение, мёртвые записи не копим
CLEANUP_EVERY = 10 * 60                 # попутная чистка не чаще раза в 10 минут на процесс
EXPIRED_KEEP = 24 * 60 * 60             # истёкшие коды/токены держим сутки: повтор кода или
                                        # старого refresh в эти сутки ещё распознаётся как повтор

# ------------------------------------------------------------------ форматы

ACCESS_PREFIX = 'kmcpo_'
REFRESH_PREFIX = 'kmcpr_'
CLIENT_ID_PREFIX = 'kmcpc_'
CLIENT_SECRET_PREFIX = 'kmcps_'
TOKEN_BYTES = 32                        # secrets.token_urlsafe(32) -> 43 символа, 256 бит энтропии

# ------------------------------------------------------------------ области (scope)

SCOPE_MCP = 'mcp'                       # «пользоваться коннектором, указанным в resource»
SCOPE_OFFLINE = 'offline_access'        # просьба о refresh-токене. Refresh выдаём всегда, но
                                        # объявляем scope: Claude и SDK добавляют его сами, если
                                        # он есть в метаданных сервера авторизации.
RESOURCE_SCOPES = (SCOPE_MCP,)          # для метаданных ресурса (offline_access туда не кладут)
SUPPORTED_SCOPES = (SCOPE_MCP, SCOPE_OFFLINE)

# ------------------------------------------------------------------ клиенты и адреса возврата

AUTH_METHODS = ('none', 'client_secret_post', 'client_secret_basic')
DEFAULT_AUTH_METHOD = 'client_secret_basic'   # RFC 7591 §2: умолчание, если клиент не указал
PUBLIC_AUTH_METHOD = 'none'

DEFAULT_REDIRECT_HOSTS = ('claude.ai', 'claude.com', 'localhost', '127.0.0.1')
LOOPBACK_HOSTS = ('localhost', '127.0.0.1', '::1')
# Для хостов Claude разрешён только адрес возврата хостовых приложений Claude
# (claude.com/docs/connectors/building/authentication; справка Anthropic: адрес может
# переехать на claude.com с тем же путём). Если Anthropic сменит путь — дописать сюда.
PINNED_CALLBACK_PATHS = {
    'claude.ai': ('/api/mcp/auth_callback',),
    'claude.com': ('/api/mcp/auth_callback',),
}
# Параметры ответа авторизации: в query адреса возврата их быть не должно, иначе клиент
# получит два значения code/state и может взять чужое.
RESERVED_REDIRECT_PARAMS = frozenset({'code', 'state', 'error', 'error_description',
                                      'error_uri', 'iss'})

MCP_BASE_PATH = '/mcp'                  # полный коннектор; домены — /mcp/<домен> (контракт 4.2)

# Режимы доступа (core/mcp/spec.MODES, от строгого к полному: read, draft, full).
# Режим задаётся суффиксом адреса коннектора: /mcp/read, /mcp/draft, /mcp/<домен>/read,
# /mcp/<домен>/draft; без суффикса — full. Суффикса '/full' нет: у каждой пары
# (домен, режим) ровно один адрес, иначе точное сравнение аудитории разъехалось бы.
FULL_MODE = 'full'
SUFFIX_MODES = tuple(m for m in MODES if m != FULL_MODE)
# Пояснения режимов для страницы согласия (что приложение сможет в этом режиме).
MODE_DESCRIPTIONS = {
    'read': 'Отчёты и данные раздела без каких-либо изменений.',
    'draft': 'Чтение и черновики внутри сервиса (например, черновики контент-плана). '
             'Утвердить, отправить или опубликовать что-либо приложение не сможет.',
    'full': 'Все инструменты раздела: чтение, изменения, отправки и выгрузки — '
            'как вы сами на сайте.',
}

# ------------------------------------------------------------------ лимиты входных данных

MAX_REGISTRATION_BYTES = 4 * 1024       # всё тело регистрации (все метаданные); реальные клиенты
                                        # шлют < 1 КБ, больше — только чтобы раздуть БД
MAX_FORM_BYTES = 16 * 1024              # тело token/revoke (реально < 2 КБ). Эндпоинты публичные,
                                        # а в Flask 3.0 нет лимита на запрос: читаем не больше этого
MAX_FORM_FIELDS = 50                    # полей в теле token/revoke (реально <= 8)
MAX_REDIRECT_URIS = 5                   # Claude регистрирует 1, Claude Code — 1-2
MAX_URI_LEN = 512                       # колбэк Claude — 39 символов, loopback — ~40
MAX_CLIENT_NAME = 100                   # длиннее — обрезаем (имя только для показа)
MAX_META_STR = 300                      # прочие строковые поля регистрации (эхо в ответе)
MAX_STATE_LEN = 1024
MAX_SCOPE_LEN = 512
MAX_PARAM_LEN = 2048                    # client_id, resource, code, токены и прочее
REG_PER_IP_PER_HOUR = 20                # на один IP в час (в памяти процесса)
REG_GLOBAL_PER_HOUR = 200               # на весь сервис в час (по БД, для всех воркеров)
REG_LIMITER_MAX_KEYS = 4096             # ключей в памяти лимитера; сверх — вытесняем самые
                                        # давние (LRU), даже со свежими отметками: память
                                        # ограничена всегда, общий лимит по БД страхует
REG_IPV6_PREFIX = 64                    # IPv6 считаем по сети /64: у одного абонента их
                                        # 2^64 адресов, по одному адресу лимит обходился бы

_CHALLENGE_RE = re.compile(r'^[A-Za-z0-9_-]{43}$')          # BASE64URL(SHA256) без «=»
_VERIFIER_RE = re.compile(r'^[A-Za-z0-9._~-]{43,128}$')     # RFC 7636 §4.1
_SCOPE_TOKEN_RE = re.compile(r'^[\x21\x23-\x5b\x5d-\x7e]+$')  # RFC 6749 §3.3 scope-token
_HOST_LABEL = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
_HOST_RE = re.compile(r'^' + _HOST_LABEL + r'(?:\.' + _HOST_LABEL + r')*$')

# ------------------------------------------------------------------ ошибки


class OAuthError(Exception):
    """Ошибка протокола для JSON-ответа (token, register, revoke).

    error — код из RFC 6749 §5.2 / RFC 7591 §3.2.2 / RFC 8707 (invalid_target);
    description — ASCII-пояснение (RFC запрещает не-ASCII в error_description);
    status — HTTP-статус; www_authenticate — заголовок для 401 при Basic-аутентификации.
    """

    def __init__(self, error: str, description: str = '', status: int = 400,
                 www_authenticate: Optional[str] = None):
        super().__init__(error)
        self.error = error
        self.description = description
        self.status = status
        self.www_authenticate = www_authenticate

    def body(self) -> dict:
        out = {'error': self.error}
        if self.description:
            out['error_description'] = self.description
        return out


class AuthorizeError(Exception):
    """Ошибка запроса авторизации (/oauth/authorize).

    redirect_uri=None — адресу возврата доверять нельзя (неизвестный клиент, чужой адрес):
    показываем страницу ошибки с message_ru. Иначе ошибка уходит клиенту редиректом
    (RFC 6749 §4.1.2.1) с error/error_description/state/iss.
    """

    def __init__(self, error: str, description: str, message_ru: str = '',
                 redirect_uri: Optional[str] = None, state: Optional[str] = None):
        super().__init__(error)
        self.error = error
        self.description = description
        self.message_ru = message_ru or 'Запрос на подключение некорректен.'
        self.redirect_uri = redirect_uri
        self.state = state


class _ParamError(Exception):
    """Параметр повторён или слишком длинный (RFC 6749 §3.1: параметры не повторяются)."""

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name


# ------------------------------------------------------------------ схема БД

SCHEMA_NAME = 'oauth'
SCHEMA = (
    # Зарегистрированные клиенты (DCR). metadata — эхо необязательных полей регистрации.
    """CREATE TABLE IF NOT EXISTS oauth_clients (
        client_id                  TEXT PRIMARY KEY,
        client_secret_hash         TEXT,
        client_name                TEXT NOT NULL,
        redirect_uris              TEXT NOT NULL,
        token_endpoint_auth_method TEXT NOT NULL,
        grant_types                TEXT NOT NULL,
        scope                      TEXT NOT NULL DEFAULT '',
        metadata                   TEXT NOT NULL DEFAULT '{}',
        registered_ip              TEXT NOT NULL DEFAULT '',
        created_at                 INTEGER NOT NULL,
        revoked_at                 INTEGER
    )""",
    "CREATE INDEX IF NOT EXISTS idx_oauth_clients_created ON oauth_clients(created_at)",
    # Коды авторизации. grant_id заранее: по нему токены, выданные по коду, находятся при
    # повторе кода.
    """CREATE TABLE IF NOT EXISTS oauth_codes (
        code_hash              TEXT PRIMARY KEY,
        client_id              TEXT NOT NULL,
        user_id                INTEGER NOT NULL,
        redirect_uri           TEXT NOT NULL,
        redirect_uri_explicit  INTEGER NOT NULL,
        code_challenge         TEXT NOT NULL,
        resource               TEXT NOT NULL,
        scope                  TEXT NOT NULL,
        grant_id               TEXT NOT NULL,
        created_at             INTEGER NOT NULL,
        expires_at             INTEGER NOT NULL,
        used_at                INTEGER,
        mode                   TEXT NOT NULL DEFAULT 'full'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_oauth_codes_expires ON oauth_codes(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_oauth_codes_client ON oauth_codes(client_id)",
    # Грант = одно согласие владельца = цепочка токенов (начальная пара и все ротации).
    """CREATE TABLE IF NOT EXISTS oauth_grants (
        grant_id        TEXT PRIMARY KEY,
        client_id       TEXT NOT NULL,
        user_id         INTEGER NOT NULL,
        resource        TEXT NOT NULL,
        scope           TEXT NOT NULL,
        redirect_uri    TEXT NOT NULL,
        created_at      INTEGER NOT NULL,
        last_used_at    INTEGER,
        revoked_at      INTEGER,
        revoked_reason  TEXT,
        mode            TEXT NOT NULL DEFAULT 'full'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_oauth_grants_client ON oauth_grants(client_id)",
    "CREATE INDEX IF NOT EXISTS idx_oauth_grants_user ON oauth_grants(user_id)",
    # Токены (access и refresh). rotated_at/replaced_by — только у refresh после обмена.
    """CREATE TABLE IF NOT EXISTS oauth_tokens (
        token_hash    TEXT PRIMARY KEY,
        token_id      TEXT NOT NULL UNIQUE,
        kind          TEXT NOT NULL,
        grant_id      TEXT NOT NULL,
        client_id     TEXT NOT NULL,
        user_id       INTEGER NOT NULL,
        resource      TEXT NOT NULL,
        scope         TEXT NOT NULL,
        created_at    INTEGER NOT NULL,
        expires_at    INTEGER NOT NULL,
        last_used_at  INTEGER,
        revoked_at    INTEGER,
        rotated_at    INTEGER,
        replaced_by   TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_oauth_tokens_grant ON oauth_tokens(grant_id)",
    "CREATE INDEX IF NOT EXISTS idx_oauth_tokens_client ON oauth_tokens(client_id)",
    "CREATE INDEX IF NOT EXISTS idx_oauth_tokens_expires ON oauth_tokens(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_oauth_tokens_user ON oauth_tokens(user_id)",
)

# Аддитивные миграции (ADD COLUMN; DROP в проекте запрещён): БД, созданные до режимов
# доступа, получают колонку mode. Старые коды и гранты — 'full': другого режима тогда не было,
# владелец соглашался именно на полный доступ.
_MIGRATIONS = (
    ('oauth_codes', 'mode', "ALTER TABLE oauth_codes ADD COLUMN mode TEXT NOT NULL DEFAULT 'full'"),
    ('oauth_grants', 'mode', "ALTER TABLE oauth_grants ADD COLUMN mode TEXT NOT NULL DEFAULT 'full'"),
)
_migrated = set()
_migrate_lock = threading.Lock()


def _ensure() -> None:
    """Схема и миграции — один раз на процесс и путь БД."""
    db.ensure_schema(SCHEMA_NAME, SCHEMA)
    key = db.db_path()
    if key in _migrated:
        return
    with _migrate_lock:
        if key in _migrated:
            return
        with db.write() as conn:
            for table, column, ddl in _MIGRATIONS:
                columns = {row['name'] for row in conn.execute('PRAGMA table_info(%s)' % table)}
                if column not in columns:
                    conn.execute(ddl)
        _migrated.add(key)


# ------------------------------------------------------------------ мелкие помощники


def _now() -> int:
    """Текущее время, секунды Unix. Тесты подменяют oauth._now для проверки сроков."""
    return int(time.time())


def _iso(ts: Optional[int]) -> Optional[str]:
    """Секунды Unix -> ISO по Москве ('2026-09-27T17:40:00+03:00'); None -> None."""
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), MOSCOW_TZ).isoformat(timespec='seconds')


def format_msk(ts: Optional[int]) -> str:
    """Секунды Unix -> '27.09.2026 17:40' по Москве (для людей); None -> ''."""
    if ts is None:
        return ''
    return datetime.fromtimestamp(int(ts), MOSCOW_TZ).strftime('%d.%m.%Y %H:%M')


def _hash(raw: str) -> str:
    """sha256 секрета (hex). Секреты — 256 бит случайности, соль не нужна."""
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _printable_ascii(value: str) -> bool:
    """Только видимые ASCII-символы 0x21..0x7E: без пробелов, управляющих и не-ASCII."""
    return all(0x21 <= ord(ch) <= 0x7E for ch in value)


def _clean_text(value, max_len: int) -> str:
    """Строка для показа человеку: без управляющих и «невидимых» символов.

    Убираются категории Unicode Cc/Cf/Cs/Co/Cn/Zl/Zp — в том числе переключатели
    направления текста (U+202E и др.) и символы нулевой ширины, которыми подделывают
    имена. Пробелы схлопываются, длина обрезается до max_len.
    """
    if not isinstance(value, str):
        return ''
    kept = []
    for ch in value:
        if ch in '\t\n\r':
            kept.append(' ')
        elif unicodedata.category(ch) not in ('Cc', 'Cf', 'Cs', 'Co', 'Cn', 'Zl', 'Zp'):
            kept.append(ch)
    return ' '.join(''.join(kept).split())[:max_len]


def pkce_s256(verifier: str) -> str:
    """code_challenge для S256: BASE64URL(SHA256(ASCII(code_verifier))) без «=» (RFC 7636 §4.2)."""
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')


# ------------------------------------------------------------------ адреса и коннекторы


def canonical_url(url) -> Optional[str]:
    """Канонический вид URL для сравнения resource/аудитории (RFC 8707 §2).

    Схема и хост в нижнем регистре, порт по умолчанию (443/80) убран, «/» в конце пути
    убран, фрагмент запрещён. Query сохраняется (у коннекторов его нет — такой resource
    просто не совпадёт). None — если строка не абсолютный http(s)-URL или содержит
    пробелы, не-ASCII, «\\», «#», логин/пароль в адресе.

    Пример: 'HTTPS://BeerKultura.ru:443/mcp/stocks/' -> 'https://beerkultura.ru/mcp/stocks'.
    """
    if not isinstance(url, str) or not url or len(url) > MAX_PARAM_LEN:
        return None
    if not _printable_ascii(url) or '\\' in url or '#' in url:
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in ('http', 'https') or not parts.netloc or '@' in parts.netloc:
        return None
    host = (parts.hostname or '').lower()
    if not host:
        return None
    host_part = '[' + host + ']' if ':' in host else host
    default_port = 443 if scheme == 'https' else 80
    netloc = host_part if port in (None, default_port) else '%s:%d' % (host_part, port)
    path = parts.path.rstrip('/')
    return urlunsplit((scheme, netloc, path, parts.query, ''))


def base_url(host_url: str) -> str:
    """request.host_url -> база без «/» в конце ('https://beerkultura.ru/' -> 'https://beerkultura.ru')."""
    return canonical_url(host_url) or (host_url or '').rstrip('/')


def issuer_for(base: str) -> str:
    """Идентификатор сервера авторизации (issuer) = база сайта, без «/» в конце.

    Один и тот же в метаданных ресурса (authorization_servers), в метаданных сервера
    (issuer) и в параметре iss ответа авторизации — клиенты сравнивают их как строки.
    """
    return base


def connector_path(domain: Optional[str] = None, mode: str = FULL_MODE) -> str:
    """Путь коннектора по домену и режиму адреса.

    (None, 'full') -> '/mcp'; (None, 'read') -> '/mcp/read'; ('stocks', 'full') -> '/mcp/stocks';
    ('stocks', 'draft') -> '/mcp/stocks/draft'.
    """
    path = MCP_BASE_PATH if domain is None else MCP_BASE_PATH + '/' + domain
    return path if mode == FULL_MODE else path + '/' + mode


def parse_connector_path(path) -> Optional[Tuple[Optional[str], str]]:
    """Путь -> (домен|None, режим адреса) или None, если это не адрес коннектора.

    '/mcp' -> (None, 'full'); '/mcp/draft' -> (None, 'draft'); '/mcp/staff' -> ('staff', 'full');
    '/mcp/staff/read' -> ('staff', 'read'). Не коннектор: '/mcp/full', '/mcp/staff/full',
    '/mcp/read/staff', '/mcp/unknown', '/mcp//staff'. Ключи DOMAINS и имена режимов не
    пересекаются (проверяет tests/test_mcp_oauth.py), поэтому первый сегмент однозначен.
    """
    if not isinstance(path, str):
        return None
    parts = path.strip('/').split('/')
    if parts[0] != MCP_BASE_PATH.strip('/'):
        return None
    rest = parts[1:]
    if not rest:
        return None, FULL_MODE
    if len(rest) == 1:
        if rest[0] in DOMAINS:
            return rest[0], FULL_MODE
        if rest[0] in SUFFIX_MODES:
            return None, rest[0]
        return None
    if len(rest) == 2 and rest[0] in DOMAINS and rest[1] in SUFFIX_MODES:
        return rest[0], rest[1]
    return None


def connector_urls(base: str) -> Dict[str, Tuple[Optional[str], str]]:
    """Все коннекторы сайта: канонический URL -> (домен|None, режим адреса).

    (1 полный + 4 домена) x 3 режима = 15 адресов — это и есть список допустимых resource.
    """
    out: Dict[str, Tuple[Optional[str], str]] = {}
    for domain in [None] + list(DOMAINS):
        for mode in MODES:
            url = canonical_url(base + connector_path(domain, mode))
            if url:
                out[url] = (domain, mode)
    return out


def resolve_resource(base: str, value) -> Optional[Tuple[str, Optional[str], str]]:
    """resource из запроса -> (канонический URL коннектора, домен|None, режим адреса) или None."""
    url = canonical_url(value)
    if url is None:
        return None
    found = connector_urls(base).get(url)
    if found is None:
        return None
    return url, found[0], found[1]


def _connector_of(resource) -> Optional[Tuple[Optional[str], str]]:
    """Коннектор сохранённого канонического resource: (домен|None, режим адреса) или None.

    Адрес с query коннектором не считается (канонические адреса коннекторов без query).
    """
    try:
        parts = urlsplit(resource)
    except (TypeError, ValueError, AttributeError):
        return None
    if parts.query:
        return None
    return parse_connector_path(parts.path)


def _domains_of(resource: str) -> Tuple[str, ...]:
    found = _connector_of(resource)
    if found is None:
        return ()
    return (ALL_DOMAINS,) if found[0] is None else (found[0],)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return parts.scheme + '://' + parts.netloc


def token_domains_for(token_resource: str, target_url: str) -> Optional[Tuple[str, ...]]:
    """Правило аудитории: где работает токен, выданный для коннектора token_resource.

    Возвращает домены для Principal или None (на target_url токен не принимается):
    1. Совпадение с точностью до канонического вида -> домены коннектора токена.
    2. Исключение полного коннектора: токен /mcp[/<режим>] (все домены) принимается на
       /mcp/<домен>[/<ТОТ ЖЕ режим>] того же сайта -> ('*',). Режим адреса должен совпасть
       точно: токен /mcp/read — только на /mcp/<домен>/read, токен /mcp — только на
       /mcp/<домен>. Прав это не расширяет: полный коннектор и так даёт все домены.
    3. Всё остальное — None. Токен /mcp/<домен>/draft не работает ни на /mcp/<домен>
       (full), ни на /mcp/<домен>/read, ни на другом домене, ни на /mcp/draft.
    Режим, выбранный владельцем на согласии (строже или равный режиму адреса), живёт в
    гранте и уходит в Principal.mode; протокол применяет более строгий из режима токена
    и режима адреса вызова.
    """
    token_url = canonical_url(token_resource)
    target = canonical_url(target_url)
    if not token_url or not target:
        return None
    tok = _connector_of(token_url)
    if tok is None:
        return None
    if token_url == target:
        return (ALL_DOMAINS,) if tok[0] is None else (tok[0],)
    tgt = _connector_of(target)
    if (tgt is not None and tok[0] is None and tgt[0] is not None and tok[1] == tgt[1]
            and _origin(token_url) == _origin(target)):
        return (ALL_DOMAINS,)
    return None


def allowed_modes(url_mode: str) -> Tuple[str, ...]:
    """Режимы, которые владелец может выбрать на согласии: равный режиму адреса или строже.

    Порядок — от полного к строгому (первый — режим адреса, он же выбран по умолчанию):
    full -> (full, draft, read); draft -> (draft, read); read -> (read,).
    Неизвестный режим адреса -> только read (безопасная сторона, как stricter_mode).
    """
    base_mode = stricter_mode(url_mode)
    return tuple(m for m in reversed(MODES) if stricter_mode(m, base_mode) == m)


def choose_mode(url_mode: str, chosen) -> str:
    """Режим гранта по выбору владельца. Пусто -> режим адреса. Мягче адреса или неизвестный
    -> ValueError (форму подделали: выбрать можно только равный или более строгий)."""
    if chosen is None or chosen == '':
        return stricter_mode(url_mode)
    if chosen not in allowed_modes(url_mode):
        raise ValueError('mode %r is not allowed for connector mode %r' % (chosen, url_mode))
    return chosen


def protected_resource_metadata_url(base: str, path: str = '') -> str:
    """Адрес метаданных ресурса (RFC 9728 §3.1): '/.well-known/oauth-protected-resource' + путь коннектора.

    Для WWW-Authenticate в 401 (routes/mcp.py): path = connector_path(домен, режим),
    например '/mcp', '/mcp/stocks', '/mcp/stocks/read'.
    """
    path = path or ''
    if path and not path.startswith('/'):
        path = '/' + path
    return base + '/.well-known/oauth-protected-resource' + path.rstrip('/')


def describe_connector(resource: str) -> dict:
    """Подпись коннектора для страницы согласия и списка подключений (с режимом адреса)."""
    found = _connector_of(resource)
    if found is None:   # домен убрали из DOMAINS после выдачи — токен уже не работает
        mode = stricter_mode(None)
        return {'domain': None, 'key': 'unknown', 'title': resource, 'url': resource,
                'domains': [], 'mode': mode, 'mode_title': MODE_TITLES[mode]}
    domain, mode = found
    if domain is None:
        title = 'Все разделы'
        domains = [{'key': d.key, 'title': d.title, 'summary': d.summary}
                   for d in DOMAINS.values()]
    else:
        d = DOMAINS[domain]
        title = d.title
        domains = [{'key': d.key, 'title': d.title, 'summary': d.summary}]
    return {'domain': domain, 'key': 'all' if domain is None else domain, 'title': title,
            'url': resource, 'domains': domains, 'mode': mode, 'mode_title': MODE_TITLES[mode]}


def protected_resource_metadata(base: str, subpath: str) -> Optional[dict]:
    """Документ RFC 9728 для коннектора по хвосту well-known адреса.

    '' (корень) и 'mcp' -> /mcp; 'mcp/read' -> /mcp/read; 'mcp/<домен>' -> /mcp/<домен>;
    'mcp/<домен>/draft' -> /mcp/<домен>/draft; прочее -> None (404). resource совпадает с
    URL коннектора, как его вводят в Claude.
    """
    tail = (subpath or '').strip('/')
    found = (None, FULL_MODE) if tail == '' else parse_connector_path('/' + tail)
    if found is None:
        return None
    domain, mode = found
    path = connector_path(domain, mode)
    resource = canonical_url(base + path) or (base + path)
    name = 'Культура — ' + ('все разделы' if domain is None else DOMAINS[domain].title)
    if mode != FULL_MODE:
        name += ' (' + MODE_TITLES[mode].lower() + ')'
    return {
        'resource': resource,
        'authorization_servers': [issuer_for(base)],
        'scopes_supported': list(RESOURCE_SCOPES),
        'bearer_methods_supported': ['header'],
        'resource_name': name,
    }


def authorization_server_metadata(base: str, endpoints: Mapping[str, str]) -> dict:
    """Документ RFC 8414. endpoints — абсолютные адреса authorization/token/registration/revocation.

    client_id_metadata_document_supported не объявляем (CIMD не поддерживается, см. модуль).
    """
    doc = {
        'issuer': issuer_for(base),
        'authorization_endpoint': endpoints['authorization_endpoint'],
        'token_endpoint': endpoints['token_endpoint'],
        'registration_endpoint': endpoints['registration_endpoint'],
        'revocation_endpoint': endpoints['revocation_endpoint'],
        'scopes_supported': list(SUPPORTED_SCOPES),
        'response_types_supported': ['code'],
        'response_modes_supported': ['query'],
        'grant_types_supported': ['authorization_code', 'refresh_token'],
        'token_endpoint_auth_methods_supported': list(AUTH_METHODS),
        'revocation_endpoint_auth_methods_supported': list(AUTH_METHODS),
        'code_challenge_methods_supported': ['S256'],
        'authorization_response_iss_parameter_supported': True,
    }
    return doc


# ------------------------------------------------------------------ адреса возврата


def allowed_redirect_hosts() -> Tuple[str, ...]:
    """Разрешённые хосты redirect_uri: настройка oauth_redirect_hosts или умолчание.

    core/mcp/settings.py импортируется лениво (модуль пишется параллельно; его отсутствие
    или сбой чтения не должны ломать OAuth). Элементы нормализуются: нижний регистр, без
    схемы, пути и порта ('https://Claude.ai/' -> 'claude.ai'); мусор отбрасывается.
    """
    value = None
    try:
        from core.mcp import settings as mcp_settings  # noqa: WPS433 — ленивый импорт
        value = mcp_settings.get('oauth_redirect_hosts', None)
    except Exception as e:  # noqa: BLE001 — нет модуля/таблицы -> умолчание
        log.debug('oauth: settings unavailable, default redirect hosts (%s)', type(e).__name__)
        value = None
    if not isinstance(value, (list, tuple)):
        return DEFAULT_REDIRECT_HOSTS
    hosts = []
    for item in value:
        host = _normalize_host_entry(item)
        if host and host not in hosts:
            hosts.append(host)
    return tuple(hosts)


def _normalize_host_entry(item) -> Optional[str]:
    if not isinstance(item, str):
        return None
    text = item.strip().lower()
    if not text:
        return None
    if text in ('::1', '[::1]'):
        return '::1'
    if '://' not in text:
        text = 'https://' + text
    try:
        host = urlsplit(text).hostname or ''
    except ValueError:
        return None
    host = host.rstrip('.')
    if host == '::1' or _HOST_RE.match(host):
        return host
    return None


@dataclass(frozen=True)
class _RedirectParts:
    scheme: str
    host: str
    port: Optional[int]
    path: str
    query: str
    loopback: bool


def _parse_redirect_uri(uri) -> Optional[_RedirectParts]:
    """Строгий разбор redirect_uri. None — адрес недопустим синтаксически.

    Запрещено то, что браузер и Python понимают по-разному: «\\» (браузер считает её «/»,
    и 'https://evil.com\\@claude.ai/' для браузера ведёт на evil.com), логин/пароль в адресе
    («@»), пробелы, управляющие и не-ASCII символы, фрагмент, странная запись порта.
    """
    if not isinstance(uri, str) or not uri or len(uri) > MAX_URI_LEN:
        return None
    if not _printable_ascii(uri) or '\\' in uri or '#' in uri:
        return None
    try:
        parts = urlsplit(uri)
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme
    if scheme not in ('http', 'https'):
        return None
    netloc = parts.netloc
    if not netloc or '@' in netloc:
        return None
    host = parts.hostname or ''
    if host == '::1':
        expected = '[::1]'
    elif _HOST_RE.match(host):
        expected = host
    else:
        return None
    if port is not None:
        if not 1 <= port <= 65535:
            return None
        expected += ':%d' % port
    if netloc.lower() != expected:
        return None
    return _RedirectParts(scheme, host, port, parts.path or '', parts.query,
                          host in LOOPBACK_HOSTS)


def validate_redirect_uri(uri, allowed_hosts: Optional[Sequence[str]] = None) -> _RedirectParts:
    """Проверка адреса возврата при регистрации и при каждой авторизации.

    Бросает OAuthError('invalid_redirect_uri'). Правила — в docstring модуля.
    """
    hosts = allowed_redirect_hosts() if allowed_hosts is None else allowed_hosts
    parts = _parse_redirect_uri(uri)
    if parts is None:
        raise OAuthError('invalid_redirect_uri',
                         'redirect_uri must be an absolute http(s) URI without fragment, '
                         'userinfo, spaces, backslashes or non-ASCII characters')
    if parts.host not in hosts:
        raise OAuthError('invalid_redirect_uri',
                         'redirect_uri host is not allowed by this server')
    if not parts.loopback:
        if parts.scheme != 'https':
            raise OAuthError('invalid_redirect_uri', 'redirect_uri must use https')
        if parts.port not in (None, 443):
            raise OAuthError('invalid_redirect_uri',
                             'explicit port is allowed only for loopback redirect_uri')
    pinned = PINNED_CALLBACK_PATHS.get(parts.host)
    if pinned and (parts.path not in pinned or parts.query):
        raise OAuthError('invalid_redirect_uri',
                         'this host allows only its known OAuth callback path')
    if parts.query:
        keys = {k for k, _v in parse_qsl(parts.query, keep_blank_values=True)}
        if keys & RESERVED_REDIRECT_PARAMS:
            raise OAuthError('invalid_redirect_uri',
                             'redirect_uri query must not contain OAuth response parameters')
    return parts


def match_redirect_uri(requested: str, registered: Sequence[str]) -> Optional[str]:
    """Найти redirect_uri запроса среди зарегистрированных. Возвращает адрес для редиректа.

    Точное строковое совпадение; для loopback порт не сравнивается (RFC 8252 §7.3):
    зарегистрирован 'http://127.0.0.1:1111/cb' -> подходит 'http://127.0.0.1:2222/cb'.
    Схема, хост, путь и query сравниваются точно ('localhost' не равен '127.0.0.1').
    """
    if not isinstance(requested, str):
        return None
    if requested in registered:
        return requested
    req = _parse_redirect_uri(requested)
    if req is None or not req.loopback:
        return None
    for item in registered:
        reg = _parse_redirect_uri(item)
        if (reg is not None and reg.loopback and reg.scheme == req.scheme
                and reg.host == req.host and reg.path == req.path and reg.query == req.query):
            return requested
    return None


def build_redirect(uri: str, params: Sequence[Tuple[str, Optional[str]]]) -> str:
    """Добавить параметры ответа к адресу возврата, сохранив его собственный query (RFC 6749 §3.1.2)."""
    parts = urlsplit(uri)
    extra = urlencode([(k, v) for k, v in params if v is not None])
    query = parts.query + ('&' if parts.query and extra else '') + extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ''))


def redirect_host(uri: str) -> str:
    try:
        return (urlsplit(uri).hostname or '').lower()
    except ValueError:
        return ''


def is_loopback_redirect(uri: str) -> bool:
    return redirect_host(uri) in LOOPBACK_HOSTS


# ------------------------------------------------------------------ частота регистраций


class _SlidingWindowLimiter:
    """Не больше limit событий на ключ за window секунд (в памяти процесса, потокобезопасно).

    Память ограничена жёстко: не больше max_keys ключей; при переполнении вытесняются
    ключи, к которым дольше всех не обращались (LRU), — даже если у них свежие отметки.
    Иначе поток запросов с разных адресов раздувал бы словарь без предела. Вытеснение
    ослабляет лимит только для самых давних ключей; общий лимит по БД (REG_GLOBAL_PER_HOUR)
    страхует. Отказанная попытка не считается событием, но ключ становится «свежим».
    """

    def __init__(self, limit: int, window: int, max_keys: int = REG_LIMITER_MAX_KEYS):
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self._hits = OrderedDict()   # ключ -> [monotonic-время событий]; порядок = давность
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            recent = [t for t in self._hits.pop(key, ()) if t > cutoff]
            allowed = len(recent) < self.limit
            if allowed:
                recent.append(now)
            self._hits[key] = recent            # в конец: самый свежий ключ
            while len(self._hits) > self.max_keys:
                self._hits.popitem(last=False)  # самый давний, даже со свежими отметками
            return allowed

    def __len__(self) -> int:
        with self._lock:
            return len(self._hits)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_registration_limiter = _SlidingWindowLimiter(REG_PER_IP_PER_HOUR, 60 * 60)


def registration_bucket(ip: str) -> str:
    """Ключ лимита регистраций по адресу клиента.

    IPv4 — сам адрес; IPv6 — сеть /REG_IPV6_PREFIX (абоненту обычно выдают целую /64, и по
    одному адресу лимит обходился бы перебором); IPv4-mapped IPv6 (::ffff:1.2.3.4) — как IPv4.
    Нечитаемая строка — она сама (обрезанная): лимит всё равно действует.
    """
    text = (ip or '').strip()
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return text[:64] or '?'
    if addr.version == 6:
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        try:
            bare = ipaddress.IPv6Address(text.split('%', 1)[0])   # без зоны (fe80::1%eth0)
            return str(ipaddress.ip_network((bare, REG_IPV6_PREFIX), strict=False))
        except ValueError:
            return str(addr)
    return str(addr)


def registration_allowed(ip: str) -> bool:
    """Ещё можно регистрироваться с этого адреса (IPv6 — с этой /64) в этом часу?"""
    return _registration_limiter.hit(registration_bucket(ip))


# ------------------------------------------------------------------ попутная чистка

_cleanup_lock = threading.Lock()
_last_cleanup = [0]


def _delete_unused_clients(conn: sqlite3.Connection, now: int) -> int:
    """Удалить регистрации старше UNUSED_CLIENT_TTL, так и не получившие гранта (и без
    ожидающего кода). Вызывается при каждой регистрации — Claude регистрируется на каждое
    подключение, брошенные записи не копятся. Возвращает число удалённых."""
    cur = conn.execute(
        'DELETE FROM oauth_clients WHERE created_at < ? '
        'AND NOT EXISTS (SELECT 1 FROM oauth_grants g WHERE g.client_id = oauth_clients.client_id) '
        'AND NOT EXISTS (SELECT 1 FROM oauth_codes c WHERE c.client_id = oauth_clients.client_id)',
        (now - UNUSED_CLIENT_TTL,))
    return cur.rowcount


def _maybe_cleanup(conn: sqlite3.Connection, now: int) -> None:
    """Удалить истёкшие коды и токены, пустые гранты и неиспользованные регистрации.

    Выполняется внутри уже открытой write-транзакции, не чаще CLEANUP_EVERY на процесс.
    """
    with _cleanup_lock:
        if now - _last_cleanup[0] < CLEANUP_EVERY:
            return
        _last_cleanup[0] = now
    conn.execute('DELETE FROM oauth_codes WHERE expires_at < ?', (now - EXPIRED_KEEP,))
    conn.execute('DELETE FROM oauth_tokens WHERE expires_at < ?', (now - EXPIRED_KEEP,))
    conn.execute('DELETE FROM oauth_grants WHERE created_at < ? AND NOT EXISTS '
                 '(SELECT 1 FROM oauth_tokens t WHERE t.grant_id = oauth_grants.grant_id)',
                 (now - EXPIRED_KEEP,))
    _delete_unused_clients(conn, now)


# ------------------------------------------------------------------ регистрация клиента (RFC 7591)


def _str_list(value, name: str, max_items: int, max_len: int) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise OAuthError('invalid_client_metadata', '%s must be an array of strings' % name)
    if len(value) > max_items:
        raise OAuthError('invalid_client_metadata', 'too many values in %s' % name)
    if any(len(v) > max_len for v in value):
        raise OAuthError('invalid_client_metadata', 'value in %s is too long' % name)
    return value


def register_client(body, ip: str = '') -> dict:
    """Зарегистрировать клиента по RFC 7591. Возвращает тело ответа 201.

    Проверки: redirect_uris обязательны (1..MAX_REDIRECT_URIS, каждый — validate_redirect_uri);
    token_endpoint_auth_method из AUTH_METHODS (по умолчанию client_secret_basic — тогда
    выдаётся client_secret); grant_types должны включать authorization_code (refresh_token
    разрешён всегда — без него подключение умирало бы через час); response_types — code.
    Необязательные поля (client_uri, logo_uri, contacts, software_*) только эхом в ответе:
    на странице согласия их не показываем. Неизвестные поля игнорируются (RFC 7591 §2).
    """
    if not isinstance(body, dict):
        raise OAuthError('invalid_client_metadata', 'registration body must be a JSON object')
    _ensure()
    hosts = allowed_redirect_hosts()

    raw_uris = body.get('redirect_uris')
    if raw_uris is None:
        raise OAuthError('invalid_redirect_uri', 'redirect_uris is required')
    uris = _str_list(raw_uris, 'redirect_uris', MAX_REDIRECT_URIS, MAX_URI_LEN)
    if not uris:
        raise OAuthError('invalid_redirect_uri', 'redirect_uris must not be empty')
    redirect_uris: List[str] = []
    for uri in uris:
        validate_redirect_uri(uri, hosts)
        if uri not in redirect_uris:
            redirect_uris.append(uri)

    # null/пустое значение = поле не передано (умолчание RFC 7591)
    method = body.get('token_endpoint_auth_method') or DEFAULT_AUTH_METHOD
    if method not in AUTH_METHODS:
        raise OAuthError('invalid_client_metadata',
                         'token_endpoint_auth_method must be one of: ' + ', '.join(AUTH_METHODS))

    grant_types = body.get('grant_types') or ['authorization_code']
    grant_types = _str_list(grant_types, 'grant_types', 10, 200)
    if 'authorization_code' not in grant_types:
        raise OAuthError('invalid_client_metadata',
                         'grant_types must include authorization_code')
    response_types = body.get('response_types') or ['code']
    response_types = _str_list(response_types, 'response_types', 10, 100)
    if 'code' not in response_types:
        raise OAuthError('invalid_client_metadata', 'response_types must include code')

    client_name = _clean_text(body.get('client_name'), MAX_CLIENT_NAME) or 'Без названия'
    scope_value = body.get('scope')
    scope = _clean_text(scope_value, MAX_SCOPE_LEN) if isinstance(scope_value, str) else ''

    echo: Dict[str, object] = {}
    for key in ('client_uri', 'logo_uri', 'tos_uri', 'policy_uri', 'software_id',
                'software_version'):
        value = body.get(key)
        if isinstance(value, str) and value and len(value) <= MAX_META_STR:
            echo[key] = _clean_text(value, MAX_META_STR)
    contacts = body.get('contacts')
    if isinstance(contacts, list):
        echo['contacts'] = [_clean_text(c, MAX_META_STR) for c in contacts[:5]
                            if isinstance(c, str)]
    if body.get('application_type') in ('web', 'native'):
        echo['application_type'] = body['application_type']

    now = _now()
    client_id = CLIENT_ID_PREFIX + secrets.token_urlsafe(18)
    client_secret = None
    if method != PUBLIC_AUTH_METHOD:
        client_secret = CLIENT_SECRET_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)
    stored_grants = ['authorization_code', 'refresh_token']

    with db.write() as conn:
        _delete_unused_clients(conn, now)
        recent = conn.execute('SELECT COUNT(*) AS n FROM oauth_clients WHERE created_at > ?',
                              (now - 3600,)).fetchone()['n']
        if recent >= REG_GLOBAL_PER_HOUR:
            raise OAuthError('temporarily_unavailable',
                             'too many client registrations, retry later', status=429)
        conn.execute(
            'INSERT INTO oauth_clients (client_id, client_secret_hash, client_name, redirect_uris, '
            'token_endpoint_auth_method, grant_types, scope, metadata, registered_ip, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (client_id, _hash(client_secret) if client_secret else None, client_name,
             json.dumps(redirect_uris), method, json.dumps(stored_grants), scope,
             json.dumps(echo, ensure_ascii=False), (ip or '')[:64], now))
        _maybe_cleanup(conn, now)

    log.info('oauth: registered client %s (%s) redirect hosts=%s ip=%s method=%s',
             client_id, client_name, sorted({redirect_host(u) for u in redirect_uris}), ip, method)

    response = {
        'client_id': client_id,
        'client_id_issued_at': now,
        'client_name': client_name,
        'redirect_uris': redirect_uris,
        'grant_types': stored_grants,
        'response_types': ['code'],
        'token_endpoint_auth_method': method,
    }
    if client_secret:
        response['client_secret'] = client_secret
        response['client_secret_expires_at'] = 0   # 0 — секрет бессрочный (RFC 7591 §3.2.1)
    if scope:
        response['scope'] = scope
    response.update(echo)
    return response


def _client_from_row(row) -> dict:
    try:
        metadata = json.loads(row['metadata'] or '{}')
    except ValueError:
        metadata = {}
    return {
        'client_id': row['client_id'],
        'client_name': row['client_name'],
        'redirect_uris': json.loads(row['redirect_uris']),
        'token_endpoint_auth_method': row['token_endpoint_auth_method'],
        'grant_types': json.loads(row['grant_types']),
        'scope': row['scope'],
        'metadata': metadata,
        'registered_ip': row['registered_ip'],
        'created_at': row['created_at'],
        'revoked_at': row['revoked_at'],
        '_secret_hash': row['client_secret_hash'],
    }


def get_client(client_id) -> Optional[dict]:
    """Клиент по client_id (внутренний словарь, включая отозванных) или None."""
    if not isinstance(client_id, str) or not client_id or len(client_id) > 128:
        return None
    _ensure()
    with db.read() as conn:
        row = conn.execute('SELECT * FROM oauth_clients WHERE client_id = ?',
                           (client_id,)).fetchone()
    return _client_from_row(row) if row else None


# ------------------------------------------------------------------ параметры запросов


def single_params(items: Iterable[Tuple[str, Sequence[str]]]) -> Dict[str, str]:
    """Параметры формы -> {имя: значение}. Повтор параметра или слишком длинное значение
    -> OAuthError('invalid_request') (RFC 6749 §3.1: параметры не повторяются)."""
    out: Dict[str, str] = {}
    for key, values in items:
        vals = list(values)
        if len(vals) > 1:
            raise OAuthError('invalid_request', 'request parameters must not be repeated')
        if not vals:
            continue
        value = vals[0]
        if not isinstance(value, str) or len(value) > MAX_PARAM_LEN:
            raise OAuthError('invalid_request', 'request parameter is too long or malformed')
        out[key] = value
    return out


def _single(params: Mapping[str, Sequence[str]], name: str, max_len: int) -> Optional[str]:
    vals = params.get(name)
    if vals is None:
        return None
    if isinstance(vals, str):
        vals = [vals]
    vals = list(vals)
    if not vals:
        return None
    if len(vals) > 1 or not isinstance(vals[0], str) or len(vals[0]) > max_len:
        raise _ParamError(name)
    return vals[0]


def _parse_scope(value: Optional[str]) -> List[str]:
    """Строка scope -> список (без повторов). ValueError — недопустимые символы."""
    if value is None:
        return []
    out: List[str] = []
    for token in value.split():
        if not _SCOPE_TOKEN_RE.match(token):
            raise ValueError(token)
        if token not in out:
            out.append(token)
    return out


def _granted_scope(requested: Sequence[str]) -> str:
    """Выданный scope: всегда 'mcp', плюс 'offline_access', если просили. Неизвестные
    scope игнорируются (RFC 6749 §3.3 разрешает выдать меньше запрошенного; фактический
    scope возвращается в ответе токена)."""
    granted = [SCOPE_MCP]
    if SCOPE_OFFLINE in requested:
        granted.append(SCOPE_OFFLINE)
    return ' '.join(granted)


# ------------------------------------------------------------------ авторизация (/oauth/authorize)


@dataclass(frozen=True)
class AuthorizationRequest:
    """Проверенный запрос авторизации. echo — поля формы согласия для повторной проверки при POST."""
    client: dict
    redirect_uri: str
    redirect_uri_explicit: bool
    state: Optional[str]
    code_challenge: str
    resource: str
    domain: Optional[str]
    url_mode: str                  # режим адреса коннектора (read | draft | full)
    scope: str
    echo: Tuple[Tuple[str, str], ...]


def validate_authorization_request(params: Mapping[str, Sequence[str]],
                                   base: str) -> AuthorizationRequest:
    """Проверить запрос /oauth/authorize (GET и повторно POST формы согласия).

    params — {имя: [значения]} (повторы видны). Порядок важен: сначала клиент и адрес
    возврата — пока они не проверены, ошибки показываются страницей (redirect_uri=None);
    после — ошибки уходят клиенту редиректом с state и iss.
    """
    _ensure()
    try:
        client_id = _single(params, 'client_id', 128)
    except _ParamError:
        raise AuthorizeError('invalid_request', 'client_id is repeated or too long',
                             'Некорректный идентификатор приложения (client_id).')
    if not client_id:
        raise AuthorizeError('invalid_request', 'client_id is required',
                             'В запросе нет идентификатора приложения (client_id).')
    client = get_client(client_id)
    if client is None:
        raise AuthorizeError('invalid_client', 'unknown client_id',
                             'Приложение не зарегистрировано на этом сайте или его регистрация '
                             'устарела. Удалите коннектор в приложении и добавьте заново.')
    if client['revoked_at']:
        raise AuthorizeError('invalid_client', 'client access was revoked',
                             'Доступ этого приложения отозван на странице «Доступ агентов». '
                             'Чтобы подключиться снова, удалите коннектор в приложении и '
                             'добавьте его заново.')

    try:
        requested_uri = _single(params, 'redirect_uri', MAX_URI_LEN)
    except _ParamError:
        raise AuthorizeError('invalid_request', 'redirect_uri is repeated or too long',
                             'Некорректный адрес возврата (redirect_uri).')
    if requested_uri is None:
        if len(client['redirect_uris']) != 1:
            raise AuthorizeError('invalid_request', 'redirect_uri is required',
                                 'В запросе нет адреса возврата (redirect_uri).')
        redirect_uri = client['redirect_uris'][0]
        explicit = False
    else:
        redirect_uri = match_redirect_uri(requested_uri, client['redirect_uris'])
        if redirect_uri is None:
            raise AuthorizeError('invalid_request', 'redirect_uri is not registered for this client',
                                 'Адрес возврата не совпадает с зарегистрированным для этого '
                                 'приложения. Перенаправлять туда код доступа нельзя.')
        explicit = True
    try:
        validate_redirect_uri(redirect_uri)
    except OAuthError:
        raise AuthorizeError('invalid_request', 'redirect_uri host is no longer allowed',
                             'Адрес возврата этого приложения больше не входит в список '
                             'разрешённых (настройки на странице «Доступ агентов»).')

    state = None
    try:
        state = _single(params, 'state', MAX_STATE_LEN)
    except _ParamError:
        raise AuthorizeError('invalid_request', 'state is repeated or too long',
                             redirect_uri=redirect_uri, state=None)

    def fail(error: str, description: str):
        raise AuthorizeError(error, description, redirect_uri=redirect_uri, state=state)

    try:
        response_type = _single(params, 'response_type', 64)
        response_mode = _single(params, 'response_mode', 32)
        method = _single(params, 'code_challenge_method', 16)
        challenge = _single(params, 'code_challenge', 128)
        scope_raw = _single(params, 'scope', MAX_SCOPE_LEN)
        prompt = _single(params, 'prompt', 64)
    except _ParamError as e:
        fail('invalid_request', 'parameter %s is repeated or too long' % e.name)

    if not response_type:
        fail('invalid_request', 'response_type is required')
    if response_type != 'code':
        fail('unsupported_response_type', 'only response_type=code is supported')
    if response_mode not in (None, '', 'query'):
        fail('invalid_request', 'only response_mode=query is supported')
    if not challenge:
        fail('invalid_request', 'code_challenge is required (PKCE with S256)')
    if method != 'S256':
        fail('invalid_request', 'code_challenge_method must be S256')
    if not _CHALLENGE_RE.match(challenge):
        fail('invalid_request', 'malformed code_challenge')

    resources = params.get('resource') or []
    if isinstance(resources, str):
        resources = [resources]
    resources = list(resources)
    if len(resources) > 1:
        fail('invalid_target', 'only one resource per request is supported')
    if resources:
        resolved = resolve_resource(base, resources[0])
        if resolved is None:
            fail('invalid_target', 'resource is not an MCP connector of this server')
    else:
        resolved = resolve_resource(base, base + MCP_BASE_PATH)
        if resolved is None:   # база сайта нечитаема — не должно случаться
            fail('server_error', 'cannot determine the default resource')
    resource, domain, url_mode = resolved

    try:
        scope = _granted_scope(_parse_scope(scope_raw))
    except ValueError:
        fail('invalid_scope', 'malformed scope')
    if prompt and 'none' in prompt.split():
        fail('consent_required', 'user consent is required')

    echo = [('client_id', client_id), ('response_type', 'code'),
            ('code_challenge', challenge), ('code_challenge_method', 'S256'),
            ('resource', resource), ('scope', scope)]
    if explicit:
        echo.append(('redirect_uri', redirect_uri))
    if state is not None:
        echo.append(('state', state))
    return AuthorizationRequest(client=client, redirect_uri=redirect_uri,
                                redirect_uri_explicit=explicit, state=state,
                                code_challenge=challenge, resource=resource, domain=domain,
                                url_mode=url_mode, scope=scope, echo=tuple(echo))


def authorization_error_redirect(err: AuthorizeError, issuer: str) -> str:
    """Адрес редиректа с ошибкой (RFC 6749 §4.1.2.1 + iss по RFC 9207)."""
    return build_redirect(err.redirect_uri, [('error', err.error),
                                             ('error_description', err.description or None),
                                             ('state', err.state),
                                             ('iss', issuer)])


def issue_code(req: AuthorizationRequest, user_id: int, mode: Optional[str] = None) -> str:
    """Выдать код авторизации (после «Разрешить»). Возвращает сырой код — только для редиректа.

    mode — режим, выбранный владельцем на согласии (None — режим адреса); проверяется ещё
    раз через choose_mode (ValueError, если мягче режима адреса). Режим уходит в грант.
    """
    grant_mode = choose_mode(req.url_mode, mode)
    _ensure()
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    now = _now()
    grant_id = 'g_' + secrets.token_hex(8)
    with db.write() as conn:
        conn.execute(
            'INSERT INTO oauth_codes (code_hash, client_id, user_id, redirect_uri, '
            'redirect_uri_explicit, code_challenge, resource, scope, grant_id, created_at, '
            'expires_at, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (_hash(raw), req.client['client_id'], int(user_id), req.redirect_uri,
             1 if req.redirect_uri_explicit else 0, req.code_challenge, req.resource,
             req.scope, grant_id, now, now + CODE_TTL, grant_mode))
        _maybe_cleanup(conn, now)
    log.info('oauth: consent granted client=%s user_id=%s resource=%s mode=%s grant=%s',
             req.client['client_id'], user_id, req.resource, grant_mode, grant_id)
    return raw


def success_redirect(req: AuthorizationRequest, code: str, issuer: str) -> str:
    return build_redirect(req.redirect_uri, [('code', code), ('state', req.state),
                                             ('iss', issuer)])


def denied_redirect(req: AuthorizationRequest, issuer: str) -> str:
    return build_redirect(req.redirect_uri, [('error', 'access_denied'),
                                             ('error_description', 'the owner denied access'),
                                             ('state', req.state), ('iss', issuer)])


# ------------------------------------------------------------------ точка токенов (/oauth/token)

_BASIC_CHALLENGE = 'Basic realm="kultura-oauth"'


def _parse_basic(header: Optional[str]) -> Optional[Tuple[str, str]]:
    """Authorization: Basic base64(urlencode(id):urlencode(secret)) (RFC 6749 §2.3.1).
    Не-Basic заголовок (например Bearer) игнорируется — None."""
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != 'basic':
        return None
    try:
        decoded = base64.b64decode(parts[1].strip(), validate=True).decode('utf-8')
    except (ValueError, UnicodeDecodeError):
        raise OAuthError('invalid_client', 'malformed Basic credentials', 401, _BASIC_CHALLENGE)
    if ':' not in decoded:
        raise OAuthError('invalid_client', 'malformed Basic credentials', 401, _BASIC_CHALLENGE)
    cid, secret = decoded.split(':', 1)
    return unquote_plus(cid), unquote_plus(secret)


def authenticate_client(authorization_header: Optional[str], params: Mapping[str, str]) -> dict:
    """Аутентификация клиента на token/revoke.

    - Basic-заголовок (client_secret_basic) или client_id+client_secret в теле
      (client_secret_post) — для конфиденциальных клиентов, любой из двух способов;
      оба сразу — invalid_request (RFC 6749 §2.3).
    - Публичный клиент ('none') — только client_id в теле; присланный секрет игнорируется.
    - Неизвестный или отозванный клиент, неверный/отсутствующий секрет -> 401 invalid_client.
    Секрет сравнивается через hmac.compare_digest по sha256.
    """
    basic = _parse_basic(authorization_header)
    body_id = params.get('client_id')
    body_secret = params.get('client_secret')
    if basic is not None:
        if body_secret:
            raise OAuthError('invalid_request', 'use only one client authentication method')
        client_id, secret = basic
        if body_id and body_id != client_id:
            raise OAuthError('invalid_client', 'client_id mismatch', 401, _BASIC_CHALLENGE)
    else:
        client_id, secret = body_id, body_secret
    challenge = _BASIC_CHALLENGE if basic is not None else None
    if not client_id:
        raise OAuthError('invalid_client', 'client authentication required', 401, challenge)
    client = get_client(client_id)
    if client is None or client['revoked_at']:
        raise OAuthError('invalid_client', 'unknown or revoked client', 401, challenge)
    if client['token_endpoint_auth_method'] == PUBLIC_AUTH_METHOD:
        return client
    expected = client['_secret_hash'] or ''
    if not secret or not expected or not hmac.compare_digest(_hash(secret), expected):
        raise OAuthError('invalid_client', 'invalid client credentials', 401, challenge)
    return client


def _user_can_hold_tokens(user_id: int) -> bool:
    """Владелец токена — существующий активный администратор (контракт 0 и 4.3)."""
    try:
        from core.auth_manager import get_auth_manager
        user = get_auth_manager().get_by_id(int(user_id))
    except Exception:  # noqa: BLE001 — нет auth.db = нет пользователя
        log.exception('oauth: cannot load user %s', user_id)
        return False
    return bool(user and user.get('active') and user.get('is_admin'))


def _revoke_grant(conn: sqlite3.Connection, grant_id: str, now: int, reason: str) -> int:
    """Отозвать грант и все его токены. Возвращает число отозванных токенов."""
    conn.execute('UPDATE oauth_grants SET revoked_at = ?, revoked_reason = ? '
                 'WHERE grant_id = ? AND revoked_at IS NULL', (now, reason, grant_id))
    cur = conn.execute('UPDATE oauth_tokens SET revoked_at = ? '
                       'WHERE grant_id = ? AND revoked_at IS NULL', (now, grant_id))
    return cur.rowcount


def _issue_pair(conn: sqlite3.Connection, grant: Mapping, now: int) -> dict:
    """Новая пара access + refresh в гранте. Возвращает тело ответа токенов (RFC 6749 §5.1)."""
    access = ACCESS_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)
    refresh = REFRESH_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)
    rows = (
        (access, 'oa_' + secrets.token_hex(6), 'access', now + ACCESS_TOKEN_TTL),
        (refresh, 'or_' + secrets.token_hex(6), 'refresh', now + REFRESH_TOKEN_TTL),
    )
    for raw, token_id, kind, expires in rows:
        conn.execute(
            'INSERT INTO oauth_tokens (token_hash, token_id, kind, grant_id, client_id, user_id, '
            'resource, scope, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (_hash(raw), token_id, kind, grant['grant_id'], grant['client_id'], grant['user_id'],
             grant['resource'], grant['scope'], now, expires))
    return {
        'access_token': access,
        'token_type': 'Bearer',
        'expires_in': ACCESS_TOKEN_TTL,
        'refresh_token': refresh,
        'scope': grant['scope'],
        '_token_id': rows[0][1],
    }


def _public_token_body(body: dict) -> dict:
    return {k: v for k, v in body.items() if not k.startswith('_')}


def exchange_authorization_code(client: dict, params: Mapping[str, str]) -> dict:
    """grant_type=authorization_code: код -> access + refresh.

    Проверки по порядку: код существует; не использован (иначе — отзыв всех токенов,
    выданных по нему, и invalid_grant); не истёк; выдан этому клиенту; redirect_uri совпадает
    (если был в запросе авторизации — обязателен и равен строке); PKCE S256; resource, если
    прислан, равен ресурсу кода (invalid_target); владелец — активный администратор.
    Неудачная проверка не «сжигает» код (256-битный verifier не подобрать), кроме повтора.
    """
    code = params.get('code')
    if not code:
        raise OAuthError('invalid_request', 'code is required')
    _ensure()
    now = _now()
    error: Optional[OAuthError] = None
    body: Optional[dict] = None
    with db.write() as conn:
        row = conn.execute('SELECT * FROM oauth_codes WHERE code_hash = ?',
                           (_hash(code),)).fetchone()
        if row is None:
            raise OAuthError('invalid_grant', 'invalid authorization code')
        if row['used_at'] is not None:
            revoked = _revoke_grant(conn, row['grant_id'], now, 'code_reuse')
            log.warning('oauth: authorization code reuse, client=%s grant=%s revoked_tokens=%s',
                        row['client_id'], row['grant_id'], revoked)
            error = OAuthError('invalid_grant', 'authorization code was already used')
        elif row['expires_at'] <= now:
            error = OAuthError('invalid_grant', 'authorization code expired')
        elif row['client_id'] != client['client_id']:
            error = OAuthError('invalid_grant', 'authorization code was issued to another client')
        else:
            given_uri = params.get('redirect_uri')
            verifier = params.get('code_verifier')
            resource = params.get('resource')
            if row['redirect_uri_explicit'] and given_uri != row['redirect_uri']:
                error = OAuthError('invalid_grant', 'redirect_uri does not match')
            elif not row['redirect_uri_explicit'] and given_uri is not None \
                    and given_uri != row['redirect_uri']:
                error = OAuthError('invalid_grant', 'redirect_uri does not match')
            elif not verifier:
                error = OAuthError('invalid_request', 'code_verifier is required')
            elif not _VERIFIER_RE.match(verifier):
                error = OAuthError('invalid_grant', 'malformed code_verifier')
            elif not hmac.compare_digest(pkce_s256(verifier), row['code_challenge']):
                error = OAuthError('invalid_grant', 'PKCE verification failed')
            elif resource is not None and canonical_url(resource) != row['resource']:
                error = OAuthError('invalid_target', 'resource does not match the authorization')
            elif not _user_can_hold_tokens(row['user_id']):
                error = OAuthError('invalid_grant', 'resource owner is no longer an active admin')
            else:
                conn.execute('UPDATE oauth_codes SET used_at = ? WHERE code_hash = ?',
                             (now, row['code_hash']))
                grant = {'grant_id': row['grant_id'], 'client_id': row['client_id'],
                         'user_id': row['user_id'], 'resource': row['resource'],
                         'scope': row['scope']}
                conn.execute(
                    'INSERT INTO oauth_grants (grant_id, client_id, user_id, resource, scope, '
                    'redirect_uri, created_at, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (grant['grant_id'], grant['client_id'], grant['user_id'], grant['resource'],
                     grant['scope'], row['redirect_uri'], now, stricter_mode(row['mode'])))
                older = conn.execute(
                    'SELECT grant_id FROM oauth_grants WHERE client_id = ? AND user_id = ? '
                    'AND resource = ? AND grant_id <> ? AND revoked_at IS NULL',
                    (grant['client_id'], grant['user_id'], grant['resource'],
                     grant['grant_id'])).fetchall()
                for old in older:
                    _revoke_grant(conn, old['grant_id'], now, 'superseded')
                body = _issue_pair(conn, grant, now)
                _maybe_cleanup(conn, now)
    if error is not None:
        raise error
    log.info('oauth: tokens issued by code client=%s grant=%s access=%s',
             client['client_id'], row['grant_id'], body['_token_id'])
    return _public_token_body(body)


def refresh_tokens(client: dict, params: Mapping[str, str]) -> dict:
    """grant_type=refresh_token: ротация — старый refresh гасится, выдаётся новая пара.

    Ошибки — invalid_grant (Claude по нему понимает, что нужна новая авторизация).
    Повтор уже обменянного refresh позже REFRESH_REUSE_GRACE — отзыв всей цепочки.
    scope, если прислан, должен быть подмножеством выданного (invalid_scope); новый токен
    получает scope гранта. resource, если прислан, — ресурс гранта (invalid_target).
    """
    raw = params.get('refresh_token')
    if not raw:
        raise OAuthError('invalid_request', 'refresh_token is required')
    if not raw.startswith(REFRESH_PREFIX):
        raise OAuthError('invalid_grant', 'invalid refresh token')
    _ensure()
    now = _now()
    error: Optional[OAuthError] = None
    body: Optional[dict] = None
    with db.write() as conn:
        row = conn.execute(
            'SELECT t.*, g.revoked_at AS grant_revoked_at FROM oauth_tokens t '
            'JOIN oauth_grants g ON g.grant_id = t.grant_id '
            "WHERE t.token_hash = ? AND t.kind = 'refresh'", (_hash(raw),)).fetchone()
        if row is None or row['client_id'] != client['client_id']:
            error = OAuthError('invalid_grant', 'invalid refresh token')
        elif row['rotated_at'] is not None:
            if now - row['rotated_at'] > REFRESH_REUSE_GRACE:
                revoked = _revoke_grant(conn, row['grant_id'], now, 'refresh_reuse')
                log.warning('oauth: rotated refresh token reused, client=%s grant=%s '
                            'revoked_tokens=%s', row['client_id'], row['grant_id'], revoked)
            error = OAuthError('invalid_grant', 'refresh token was already used')
        elif row['revoked_at'] is not None or row['grant_revoked_at'] is not None:
            error = OAuthError('invalid_grant', 'refresh token was revoked')
        elif row['expires_at'] <= now:
            error = OAuthError('invalid_grant', 'refresh token expired')
        else:
            resource = params.get('resource')
            try:
                requested_scope = _parse_scope(params.get('scope'))
            except ValueError:
                requested_scope = None
            granted = row['scope'].split()
            if requested_scope is None:
                error = OAuthError('invalid_scope', 'malformed scope')
            elif any(s not in granted for s in requested_scope):
                error = OAuthError('invalid_scope', 'scope exceeds the original grant')
            elif resource is not None and canonical_url(resource) != row['resource']:
                error = OAuthError('invalid_target', 'resource does not match the grant')
            elif not _user_can_hold_tokens(row['user_id']):
                error = OAuthError('invalid_grant', 'resource owner is no longer an active admin')
            else:
                grant = {'grant_id': row['grant_id'], 'client_id': row['client_id'],
                         'user_id': row['user_id'], 'resource': row['resource'],
                         'scope': row['scope']}
                body = _issue_pair(conn, grant, now)
                conn.execute('UPDATE oauth_tokens SET rotated_at = ?, revoked_at = ?, '
                             'replaced_by = ? WHERE token_hash = ?',
                             (now, now, body['_token_id'], row['token_hash']))
                conn.execute('UPDATE oauth_grants SET last_used_at = ? WHERE grant_id = ?',
                             (now, row['grant_id']))
    if error is not None:
        raise error
    log.info('oauth: refresh rotated client=%s grant=%s access=%s',
             client['client_id'], row['grant_id'], body['_token_id'])
    return _public_token_body(body)


# ------------------------------------------------------------------ отзыв (RFC 7009)


def revoke_token(raw: str, client: Optional[dict]) -> bool:
    """Отозвать токен. True — что-то отозвано (наружу всегда 200, RFC 7009 §2.2).

    refresh -> гаснет весь грант (все токены цепочки, RFC 7009 §2.1 SHOULD);
    access -> только он. client=None (клиент не представился) — отзыв по факту владения
    токеном: это может только навредить держателю. Токен чужого клиента не трогаем и
    не сообщаем об этом (не даём проверять чужие токены).
    """
    if not raw or not isinstance(raw, str) or len(raw) > MAX_PARAM_LEN:
        return False
    _ensure()
    now = _now()
    with db.write() as conn:
        row = conn.execute('SELECT token_hash, token_id, kind, grant_id, client_id '
                           'FROM oauth_tokens WHERE token_hash = ?', (_hash(raw),)).fetchone()
        if row is None:
            return False
        if client is not None and row['client_id'] != client['client_id']:
            return False
        if row['kind'] == 'refresh':
            n = _revoke_grant(conn, row['grant_id'], now, 'revoked_by_client')
        else:
            n = conn.execute('UPDATE oauth_tokens SET revoked_at = ? '
                             'WHERE token_hash = ? AND revoked_at IS NULL',
                             (now, row['token_hash'])).rowcount
    log.info('oauth: token %s (%s) revoked by client request, affected=%s',
             row['token_id'], row['kind'], n)
    return n > 0


# ------------------------------------------------------------------ проверка access-токена


def verify_access_token(raw, resource_url) -> Optional[Principal]:
    """Проверить Bearer-токен OAuth для коннектора resource_url (контракт 4.3).

    raw — значение после 'Bearer '; resource_url — URL коннектора, куда пришёл вызов
    (<base>/mcp или <base>/mcp/<домен>, любой регистр хоста и «/» в конце допустимы).
    None — не наш формат, неизвестен, истёк, отозван (сам, грант или клиент), аудитория
    не подходит (token_domains_for) или владелец больше не активный администратор.
    Иначе Principal(token_kind='oauth', token_id='oa_…', grant_id='g_…' (подключение,
    переживает обновление токена), client_name из регистрации, domains по resource
    токена, expires_at — ISO МСК). Ошибки БД пробрасываются
    (сбой хранилища — это 5xx, а не «токен неверен» с повторной авторизацией).
    """
    if not isinstance(raw, str) or not raw.startswith(ACCESS_PREFIX) or len(raw) > 200:
        return None
    target = canonical_url(resource_url)
    if target is None:
        return None
    _ensure()
    now = _now()
    token_hash = _hash(raw)
    with db.read() as conn:
        row = conn.execute(
            'SELECT t.token_id, t.user_id, t.client_id, t.resource, t.expires_at, t.last_used_at, '
            't.grant_id, t.revoked_at, c.client_name, c.revoked_at AS client_revoked_at, '
            'g.revoked_at AS grant_revoked_at, g.mode AS grant_mode '
            'FROM oauth_tokens t '
            'JOIN oauth_clients c ON c.client_id = t.client_id '
            'JOIN oauth_grants g ON g.grant_id = t.grant_id '
            "WHERE t.token_hash = ? AND t.kind = 'access'", (token_hash,)).fetchone()
    if row is None or row['revoked_at'] is not None or row['client_revoked_at'] is not None \
            or row['grant_revoked_at'] is not None or row['expires_at'] <= now:
        return None
    domains = token_domains_for(row['resource'], target)
    if not domains:
        return None
    try:
        from core.auth_manager import get_auth_manager
        user = get_auth_manager().get_by_id(int(row['user_id']))
    except Exception:  # noqa: BLE001
        log.exception('oauth: cannot load token owner')
        return None
    if not user or not user.get('active') or not user.get('is_admin'):
        return None
    if row['last_used_at'] is None or now - row['last_used_at'] >= LAST_USED_WRITE_EVERY:
        try:
            with db.write() as conn:
                conn.execute('UPDATE oauth_tokens SET last_used_at = ? WHERE token_hash = ?',
                             (now, token_hash))
                conn.execute('UPDATE oauth_grants SET last_used_at = ? WHERE grant_id = ?',
                             (now, row['grant_id']))
        except sqlite3.Error:
            log.warning('oauth: cannot update last_used_at for %s', row['token_id'])
    return Principal(
        user_id=int(user['id']),
        login=user['login'],
        display_name=user.get('display_name') or user['login'],
        token_id=row['token_id'],
        token_kind='oauth',
        client_name=row['client_name'],
        domains=tuple(domains),
        expires_at=_iso(row['expires_at']),
        mode=stricter_mode(row['grant_mode']),
        grant_id=row['grant_id'],
    )


# ------------------------------------------------------------------ страница «Доступ агентов»


def list_grants() -> List[dict]:
    """Действующие подключения OAuth (для /admin/mcp): одна строка на грант с живыми токенами.

    Поля контракта: client_id, client_name, redirect_host, user_login, resource, created_at,
    last_used_at (ISO МСК или None). Дополнительно: grant_id, connector ('all' или домен),
    connector_title, domains, scope, user_display_name, expires_at (когда подключение умрёт
    без использования — срок последнего refresh).
    """
    _ensure()
    now = _now()
    with db.read() as conn:
        rows = conn.execute(
            'SELECT g.grant_id, g.client_id, g.user_id, g.resource, g.scope, g.redirect_uri, '
            'g.created_at, g.last_used_at, g.mode, c.client_name, MAX(t.expires_at) AS expires_at '
            'FROM oauth_grants g '
            'JOIN oauth_clients c ON c.client_id = g.client_id '
            'JOIN oauth_tokens t ON t.grant_id = g.grant_id '
            '     AND t.revoked_at IS NULL AND t.expires_at > ? '
            'WHERE g.revoked_at IS NULL AND c.revoked_at IS NULL '
            'GROUP BY g.grant_id '
            # grant_id в конце — детерминированный порядок при равных секундах
            'ORDER BY COALESCE(g.last_used_at, g.created_at) DESC, g.created_at DESC, g.grant_id',
            (now,)).fetchall()
    users: Dict[int, Optional[dict]] = {}
    try:
        from core.auth_manager import get_auth_manager
        mgr = get_auth_manager()
    except Exception:  # noqa: BLE001
        mgr = None
    out = []
    for r in rows:
        uid = int(r['user_id'])
        if uid not in users:
            try:
                users[uid] = mgr.get_by_id(uid) if mgr else None
            except Exception:  # noqa: BLE001
                users[uid] = None
        user = users[uid]
        info = describe_connector(r['resource'])
        out.append({
            'client_id': r['client_id'],
            'client_name': r['client_name'],
            'redirect_host': redirect_host(r['redirect_uri']),
            'user_login': user['login'] if user else '(аккаунт удалён)',
            'user_display_name': user.get('display_name') if user else None,
            'resource': r['resource'],
            'created_at': _iso(r['created_at']),
            'last_used_at': _iso(r['last_used_at']),
            'grant_id': r['grant_id'],
            'connector': info['key'],
            'connector_title': info['title'],
            'url_mode': info['mode'],
            'mode': stricter_mode(r['mode']),
            'mode_title': MODE_TITLES[stricter_mode(r['mode'])],
            'domains': list(_domains_of(r['resource'])),
            'scope': r['scope'],
            'expires_at': _iso(r['expires_at']),
        })
    return out


def revoke_client(client_id: str) -> dict:
    """Отключить приложение: все его гранты и токены гаснут сразу, client_id больше не
    принимается (ни авторизация, ни token). Возвращает {'found', 'grants', 'tokens'}.
    Повторный вызов безопасен (found=True, нули)."""
    if not isinstance(client_id, str) or not client_id:
        return {'found': False, 'grants': 0, 'tokens': 0}
    _ensure()
    now = _now()
    with db.write() as conn:
        row = conn.execute('SELECT client_id FROM oauth_clients WHERE client_id = ?',
                           (client_id,)).fetchone()
        if row is None:
            return {'found': False, 'grants': 0, 'tokens': 0}
        tokens = conn.execute('UPDATE oauth_tokens SET revoked_at = ? '
                              'WHERE client_id = ? AND revoked_at IS NULL',
                              (now, client_id)).rowcount
        grants = conn.execute("UPDATE oauth_grants SET revoked_at = ?, revoked_reason = 'admin' "
                              'WHERE client_id = ? AND revoked_at IS NULL',
                              (now, client_id)).rowcount
        conn.execute('UPDATE oauth_clients SET revoked_at = ? '
                     'WHERE client_id = ? AND revoked_at IS NULL', (now, client_id))
    log.info('oauth: client %s revoked by admin, grants=%s tokens=%s', client_id, grants, tokens)
    return {'found': True, 'grants': grants, 'tokens': tokens}


def revoke_all_for_user(user_id) -> dict:
    """Отозвать все гранты и токены пользователя и удалить его неиспользованные коды.

    Вызывает routes/auth.py при удалении, отключении и снятии прав администратора: без
    этого возврат флага оживил бы старые подключения (проверка на каждом вызове лишь
    приостанавливает их). Неиспользованный код тоже удаляется — иначе по нему можно было бы
    получить новый токен после возврата прав. Возвращает {'grants', 'tokens', 'codes'};
    повторный вызов безопасен (нули). Сбой хранилища — sqlite3.Error наверх.
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return {'grants': 0, 'tokens': 0, 'codes': 0}
    _ensure()
    now = _now()
    with db.write() as conn:
        grants = conn.execute("UPDATE oauth_grants SET revoked_at = ?, revoked_reason = 'user_access' "
                              'WHERE user_id = ? AND revoked_at IS NULL', (now, uid)).rowcount
        tokens = conn.execute('UPDATE oauth_tokens SET revoked_at = ? '
                              'WHERE user_id = ? AND revoked_at IS NULL', (now, uid)).rowcount
        codes = conn.execute('DELETE FROM oauth_codes WHERE user_id = ? AND used_at IS NULL',
                             (uid,)).rowcount
    log.info('oauth: all access of user_id=%s revoked, grants=%s tokens=%s codes=%s',
             uid, grants, tokens, codes)
    return {'grants': grants, 'tokens': tokens, 'codes': codes}
