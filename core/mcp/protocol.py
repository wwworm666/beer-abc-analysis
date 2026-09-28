"""Протокол MCP поверх HTTP: JSON-RPC, методы MCP, версии, режимы доступа, лимиты, журнал.

Реализованная редакция спецификации: 2026-07-28 (самая новая на 2026-09-27, сверено
с modelcontextprotocol.io/specification/2026-07-28: basic, versioning,
transports/streamable-http, server/discover, server/tools, server/prompts,
server/utilities/caching, basic/authorization). Сервер «двух эпох» (dual-era):

- СОВРЕМЕННАЯ эпоха (2026-07-28): протокол без состояния, рукопожатия нет. Каждый
  запрос несёт в params._meta версию ('io.modelcontextprotocol/protocolVersion')
  и возможности клиента ('io.modelcontextprotocol/clientCapabilities'); в HTTP —
  заголовки MCP-Protocol-Version, Mcp-Method и (для tools/call, prompts/get)
  Mcp-Name. Проверка («лестница», как в официальном SDK):
    1) _meta с обоими обязательными ключами, иначе -32602 (HTTP 400);
    2) заголовки совпадают с телом, иначе HeaderMismatch -32020 (HTTP 400);
       Mcp-Name может прийти в base64-обёртке '=?base64?…?=' — раскодируется;
    3) версия поддерживается, иначе UnsupportedProtocolVersion -32022 (HTTP 400)
       с data {supported: [...], requested}.
  Методы: server/discover (обязателен), tools/list, tools/call, prompts/list,
  prompts/get. У каждого результата resultType='complete' и
  _meta['io.modelcontextprotocol/serverInfo']; у списков и discover —
  ttlMs (LIST_TTL_MS) и cacheScope='private'. Неизвестный метод — -32601 и HTTP 404.
- СТАРАЯ эпоха (2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05): рукопожатие
  initialize. Версия клиента поддерживается — возвращаем её, иначе предлагаем
  LATEST_LEGACY (2025-11-25; 2026-07-28 через initialize не согласуется — у неё
  рукопожатия нет). Дальше версия — из заголовка MCP-Protocol-Version; без него —
  2025-03-26 (так велит спецификация); неизвестная версия — HTTP 400 и -32022.
  Методы: initialize, ping, tools/list, tools/call, prompts/list, prompts/get.
  Ошибки уровня JSON-RPC — HTTP 200 (старые клиенты читают 404 как «сессия
  истекла» и начинают заново). Пакеты (JSON-массив) — только для 2025-03-26 и
  2024-11-05 (в 2025-06-18 их из протокола убрали) и не длиннее MAX_BATCH.
Эпоха выбирается по запросу: _meta с версией или современный заголовок -> новая;
иначе старая (initialize — всегда старая).

РЕЖИМЫ ДОСТУПА (проверка безопасности 2026-09-28). Адрес коннектора может нести
режим: /mcp/read, /mcp/draft, /mcp/<домен>/read, /mcp/<домен>/draft; без суффикса —
full. Суффикса /full нет (404): у каждой пары (домен, режим) ровно один адрес — OAuth
привязывает токен к каноническому адресу коннектора (core/mcp/oauth.py). У токена свой режим (Principal.mode). Действует более строгий из двух
(spec.stricter_mode): read — только чтение, draft — чтение и draft_write (черновики
внутри сервиса), full — всё. tools/list показывает только разрешённые в режиме
инструменты; вызов неразрешённого — результат isError с названием режима и запись
'denied' в журнале. Режим назван в serverInfo.title и первой строкой instructions.
Зачем: агент по расписанию читает тексты гостей и описания пива — «команда»,
внедрённая в данные, не должна дотянуться до утверждения, отправки и публичных
фидов; запрет держит сервер, а не только инструкция агенту.

HTTP (routes/mcp.py): только POST. GET и DELETE -> 405 (SSE-потока и сессий нет,
Mcp-Session-Id не выдаётся и игнорируется). Уведомления и ответы клиента -> 202
без тела. Ответ на запрос — один объект application/json (SSE не используется).
Порядок проверок: неизвестный домен или режим (404) -> Origin (403, защита от DNS
rebinding: чужой хост, кроме claude.ai/claude.com и локальных) -> токен (401/403,
auth.py) -> метод HTTP (405) -> размер тела (413; тело читается не больше
MAX_REQUEST_BYTES + 1 байта даже без Content-Length) -> разбор JSON (-32700, в том
числе слишком глубокая вложенность).

Ошибки инструментов (контракт 4.2 и раздел Error Handling спецификации tools):
неизвестный или чужой для коннектора инструмент — JSON-RPC -32602; аргументы не
по схеме, ошибка маршрута, лимиты, запрет режима — обычный результат с isError=true
и русским текстом, чтобы агент исправился сам. structuredContent не отдаём.
Имя инструмента проверяется по spec.TOOL_NAME_RE ДО журнала и ответа: кривое имя
не отражается в ответе и пишется в журнал обрезанным до 64 символов.

Лимиты tools/call (порядок проверок):
1) частота — RATE_LIMIT_PER_MINUTE на токен, считается ДО поиска инструмента: отказы
   и неизвестные имена тоже расходуют лимит, иначе ими можно было бы засыпать журнал;
2) одновременность — не больше MAX_CONCURRENT_CALLS исполнений на ВЕСЬ сервис (см.
   константу): сверх — isError «сервер занят» (в журнале 'denied'). Место берётся
   только перед настоящим исполнением маршрута: ответ из кэша тяжёлых чтений
   (bridge.py) места не занимает;
3) тяжёлые вызовы iiko — отдельный семафор в bridge.py (на процесс).

Общие для процессов лимиты (с 2026-09-28). В проде 2 gunicorn-воркера; пока счётчики
жили в памяти процесса, фактический предел был вдвое больше заявленного (240 вызовов
в минуту, 6 одновременных). Теперь оба счёта — в mcp.db (WAL, BEGIN IMMEDIATE,
тот же приём, что журнал и лимит сообщений владельцу):
- частота (RateLimiter, таблица rate_hits): скользящее окно RATE_WINDOW_S — строка
  на каждый вызов (ключ = id токена, время = time.time(), общие часы процессов);
  событие считается, пока с него прошло меньше окна. Проверка «сколько за окно» и
  вставка — одна транзакция записи, поэтому два воркера не проскочат лимит вместе.
  Устаревшие строки удаляются тем же запросом (таблица не растёт); строки «из
  будущего» (часы сервера перевели назад больше чем на окно) — тоже, иначе токен
  был бы заблокирован до тех пор, пока часы их не догонят;
- одновременность (CallLeases, таблица call_leases): «аренда» места — строка с
  истечением LEASE_TTL_S. Взять место = удалить истёкшие аренды, сосчитать живые,
  если меньше предела — вставить свою (одна транзакция). Отпустить = удалить свою
  строку. Истечение нужно на случай, когда процесс погиб посреди вызова (перезапуск
  воркера, OOM): его аренда освободится сама не позже чем через LEASE_TTL_S.
  Проверять «жив ли процесс» по pid нельзя: на Windows os.kill(pid, 0) завершает
  процесс, а в контейнере pid переиспользуются;
- память процесса осталась страховкой: call_slots (BoundedSemaphore на
  MAX_CONCURRENT_CALLS) не даст одному воркеру занять больше мест, даже если mcp.db
  недоступна. Если mcp.db не отвечает (сбой диска, блокировка дольше busy_timeout),
  лимиты считаются в памяти процесса, как до 2026-09-28, и сбой пишется в лог:
  агент не должен получать «сервер занят» из-за журнала на диске.

Сознательно НЕ реализовано: сессии, SSE (в т.ч. потоковые ответы и прогресс),
subscriptions/listen и уведомления list_changed (список меняется только с
выкладкой), resources (данные доступны инструментами), completion, logging,
sampling/elicitation/roots и MRTR (агенту нечего спрашивать у клиента), tasks,
пагинация (курсор игнорируется, nextCursor не отдаётся), x-mcp-header.
"""
import base64
import binascii
import json
import logging
import os
import sys
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from typing import Any, Deque, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urlsplit

from flask import Response, current_app

from core.mcp import audit, auth, bridge, db, registry
from core.mcp.principal import Principal
from core.mcp.spec import (COMMON_DOMAIN, DOMAINS, MODE_TITLES, MODES, PROMPT_NAME_RE, TOOL_NAME_RE,
                           allowed_in_mode, prompt_allowed_in_mode, stricter_mode)

# Режимы, которые пишутся в адресе. full — адрес без суффикса (один адрес на пару).
URL_MODES: Tuple[str, ...] = tuple(m for m in MODES if m != 'full')

log = logging.getLogger('mcp.protocol')

# ------------------------------------------------------------------ версии и ключи

MODERN_VERSIONS: Tuple[str, ...] = ('2026-07-28',)
LEGACY_VERSIONS: Tuple[str, ...] = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')
SUPPORTED_VERSIONS: Tuple[str, ...] = MODERN_VERSIONS + LEGACY_VERSIONS     # новые первыми
LATEST_LEGACY = '2025-11-25'
DEFAULT_LEGACY = '2025-03-26'          # запрос без MCP-Protocol-Version (правило спецификации)
BATCH_VERSIONS: Tuple[str, ...] = ('2025-03-26', '2024-11-05')

META_VERSION = 'io.modelcontextprotocol/protocolVersion'
META_CAPABILITIES = 'io.modelcontextprotocol/clientCapabilities'
META_CLIENT = 'io.modelcontextprotocol/clientInfo'
META_SERVER = 'io.modelcontextprotocol/serverInfo'

HEADER_VERSION = 'MCP-Protocol-Version'
HEADER_METHOD = 'Mcp-Method'
HEADER_NAME = 'Mcp-Name'
NAME_BEARING = {'tools/call': 'name', 'prompts/get': 'name', 'resources/read': 'uri'}

# ------------------------------------------------------------------ коды JSON-RPC

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
HEADER_MISMATCH = -32020
UNSUPPORTED_VERSION = -32022

# HTTP-код ответа на ошибку в современной эпохе (таблица из официального SDK:
# transports/streamable-http требует 400 для проверки заголовков и версии, 404 —
# для неизвестного метода; внутренняя ошибка остаётся 200).
MODERN_ERROR_HTTP = {PARSE_ERROR: 400, INVALID_REQUEST: 400, INVALID_PARAMS: 400, HEADER_MISMATCH: 400,
                     -32021: 400, UNSUPPORTED_VERSION: 400, METHOD_NOT_FOUND: 404}

# ------------------------------------------------------------------ правила сервера

SERVER_NAME = 'kultura'

# Сколько клиент может считать списки свежими. Инструменты меняются только с
# выкладкой; 5 минут — компромисс между лишними запросами списка и тем, как
# быстро агент увидит новые инструменты после деплоя.
LIST_TTL_MS = 5 * 60 * 1000

# Лимит частоты на токен: 120 вызовов инструментов в минуту = 2 в секунду — на весь
# сервис (оба воркера, счёт в mcp.db). Агенту с живыми рассуждениями этого с запасом
# хватает; зацикленный агент упрётся и не положит iiko и диск.
RATE_LIMIT_PER_MINUTE = 120
RATE_WINDOW_S = 60

# Одновременные исполнения tools/call на весь сервис (аренды в mcp.db) и, страховкой,
# на процесс (call_slots). В проде gunicorn — 2 воркера по 4 потока; каждый вызов
# инструмента держит поток воркера (маршрут исполняется в нём же). 3 на сервис: даже
# если все три попадут в один воркер, у него останется поток для сайта, чтобы бармены
# и владелец не ждали, пока агент гоняет отчёты. Столько же обещают агентам общие
# правила (common.INSTRUCTIONS). Сверх — isError «сервер занят», агент повторит.
MAX_CONCURRENT_CALLS = 3

# Срок аренды места вызова. Самый долгий законный вызов — тяжёлый отчёт iiko с
# повтором (2 попытки по 60 с + пауза, см. --timeout 180 в Dockerfile) — короче.
# Аренда погибшего посреди вызова процесса освобождается сама не позже этого срока;
# вызов дольше срока продолжится, но его место на время превысит предел на единицу.
LEASE_TTL_S = 300

# Пакет JSON-RPC (старые версии): 20 сообщений — с запасом для клиентов, которые
# группируют initialize/list; сотни в одном POST — только способ обойти лимиты.
MAX_BATCH = 20

# Предел тела запроса: файл для загрузки приходит в base64 (+33 %). 25 МБ хватает
# на фото и короткое видео; больше агенту передавать незачем. Тело читается кусками
# по READ_CHUNK и не дальше MAX_REQUEST_BYTES + 1 байта — и при Content-Length, и при
# chunked-передаче без него.
MAX_REQUEST_BYTES = 25 * 1024 * 1024
READ_CHUNK = 64 * 1024

# Сколько символов пользовательского ввода (имя метода, версия) отражать в ответах.
ECHO_LIMIT = 64

# Кому можно слать запросы из браузера (заголовок Origin): наш сайт, приложения
# Claude (и их поддомены) и локальные адреса (Claude Code, разработка).
ALLOWED_ORIGIN_HOSTS = ('claude.ai', 'claude.com', 'localhost', '127.0.0.1', '::1')
ALLOWED_ORIGIN_SUFFIXES = ('.claude.ai', '.claude.com')

CAPABILITIES = {'tools': {'listChanged': False}, 'prompts': {'listChanged': False}}

# Первая строка instructions: агент должен сразу знать границы подключения. Одна
# строка без переводов (тесты и клиенты берут её как первую). Сообщение владельцу
# (common_notify_owner, пометка owner_notice) сервер разрешает в любом режиме — строка
# называет это прямо, иначе агент расписания решил бы, что отчёт прислать нельзя.
MODE_LINES = {
    'read': 'Режим этого подключения — «Только чтение»: инструменты, которые меняют данные или что-то '
            'отправляют, здесь недоступны; исключение — сообщение владельцу в Telegram (common_notify_owner), '
            'им присылают итог, когда об этом просит задание.',
    'draft': 'Режим этого подключения — «Чтение и черновики»: можно читать и готовить черновики внутри '
             'сервиса (они ждут утверждения владельца); утверждение, отправка, удаление и прочие изменения '
             'здесь недоступны; исключение — сообщение владельцу в Telegram (common_notify_owner), им '
             'присылают итог, когда об этом просит задание.',
    'full': 'Режим этого подключения — «Полный доступ»: доступны все инструменты раздела; изменения — только '
            'по прямой просьбе владельца.',
}


class RpcError(Exception):
    """Ошибка JSON-RPC: код, текст, data. http — код ответа, если отличается от правил эпохи."""

    def __init__(self, code: int, message: str, data: Any = None, http: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
        self.http = http

    def body(self, rid: Any) -> Dict[str, Any]:
        err: Dict[str, Any] = {'code': self.code, 'message': self.message}
        if self.data is not None:
            err['data'] = self.data
        return {'jsonrpc': '2.0', 'id': rid, 'error': err}


# ------------------------------------------------------------------ лимиты

LIMITS_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS rate_hits (
        id  INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL,                 -- id токена ('st_…', 'oa_…')
        at  REAL NOT NULL                  -- time.time(): общие часы процессов
    )''',
    'CREATE INDEX IF NOT EXISTS idx_rate_hits_key_at ON rate_hits(key, at)',
    'CREATE INDEX IF NOT EXISTS idx_rate_hits_at ON rate_hits(at)',
    '''CREATE TABLE IF NOT EXISTS call_leases (
        id          TEXT PRIMARY KEY,      -- случайный uuid аренды
        token_id    TEXT NOT NULL DEFAULT '',
        tool        TEXT NOT NULL DEFAULT '',
        pid         INTEGER NOT NULL DEFAULT 0,   -- для разбора; живость по нему не проверяется
        acquired_at REAL NOT NULL,
        expires_at  REAL NOT NULL
    )''',
    'CREATE INDEX IF NOT EXISTS idx_call_leases_expires ON call_leases(expires_at)',
)


def _ensure_limits_schema() -> None:
    db.ensure_schema('limits', LIMITS_SCHEMA)


class LocalRateLimiter:
    """Скользящее окно в памяти процесса: не больше limit событий за window секунд на ключ.

    Запасной счёт, когда mcp.db недоступна (и как было до 2026-09-28). Время —
    переданное now или time.monotonic() (внутри процесса часы не прыгают).
    """

    def __init__(self, limit: int = RATE_LIMIT_PER_MINUTE, window: float = RATE_WINDOW_S):
        self.limit = limit
        self.window = window
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, now: Optional[float] = None) -> Optional[int]:
        """Учесть вызов. None — можно; число — сколько секунд подождать."""
        now = time.monotonic() if now is None else now
        with self._lock:
            queue = self._hits.setdefault(key, deque())
            while queue and now - queue[0] >= self.window:
                queue.popleft()
            if len(queue) >= self.limit:
                return max(1, int(self.window - (now - queue[0])) + 1)
            queue.append(now)
            if len(self._hits) > 1000:       # уборка ключей отозванных токенов
                for stale in [k for k, q in self._hits.items() if not q or now - q[-1] >= self.window]:
                    self._hits.pop(stale, None)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RateLimiter:
    """Скользящее окно в mcp.db — один счёт на все процессы (правила — докстринг модуля).

    hit(key, now) -> None (можно) или число секунд, через сколько повторить. Событие
    считается, пока now - at < window: с limit=2, window=60 вызовы в 0 и 1 проходят,
    в 2 — «подождите 59 с», в 61 — снова можно. Без now берётся time.time(): у
    процессов общие только настенные часы. Сбой mcp.db — счёт в памяти процесса.
    """

    def __init__(self, limit: int = RATE_LIMIT_PER_MINUTE, window: float = RATE_WINDOW_S):
        self.limit = limit
        self.window = window
        self.fallback = LocalRateLimiter(limit, window)

    def hit(self, key: str, now: Optional[float] = None) -> Optional[int]:
        """Учесть вызов. None — можно; число — сколько секунд подождать."""
        at = time.time() if now is None else float(now)
        try:
            _ensure_limits_schema()
            with db.write() as conn:
                conn.execute('DELETE FROM rate_hits WHERE at <= ? OR at > ?',
                             (at - self.window, at + self.window))
                row = conn.execute('SELECT COUNT(*) AS n, MIN(at) AS first FROM rate_hits WHERE key = ?',
                                   (key,)).fetchone()
                if row['n'] >= self.limit:
                    return max(1, int(self.window - (at - row['first'])) + 1)
                conn.execute('INSERT INTO rate_hits (key, at) VALUES (?, ?)', (key, at))
                return None
        except Exception:  # noqa: BLE001 — сбой диска не должен останавливать агента
            log.exception('[MCP] лимит частоты: mcp.db недоступна, считаю в памяти процесса')
            return self.fallback.hit(key, None if now is None else now)

    def reset(self) -> None:
        """Забыть все вызовы (тесты)."""
        self.fallback.reset()
        try:
            _ensure_limits_schema()
            with db.write() as conn:
                conn.execute('DELETE FROM rate_hits')
        except Exception:  # noqa: BLE001
            log.exception('[MCP] лимит частоты: не удалось очистить rate_hits')


class CallLeases:
    """Места одновременных вызовов на весь сервис: аренда с истечением в mcp.db.

    acquire(token_id, tool) -> id аренды или None (мест нет); release(id) отпускает.
    Сбой mcp.db — LOCAL_LEASE: вызов идёт под одной страховкой call_slots (на процесс).
    """

    LOCAL_LEASE = 'local'

    def __init__(self, limit: int = MAX_CONCURRENT_CALLS, ttl: float = LEASE_TTL_S):
        self.limit = limit
        self.ttl = ttl

    def acquire(self, token_id: str = '', tool: str = '', now: Optional[float] = None) -> Optional[str]:
        at = time.time() if now is None else float(now)
        lease_id = uuid.uuid4().hex
        try:
            _ensure_limits_schema()
            with db.write() as conn:
                conn.execute('DELETE FROM call_leases WHERE expires_at <= ?', (at,))
                busy = conn.execute('SELECT COUNT(*) AS n FROM call_leases').fetchone()['n']
                if busy >= self.limit:
                    return None
                conn.execute('INSERT INTO call_leases (id, token_id, tool, pid, acquired_at, expires_at) '
                             'VALUES (?, ?, ?, ?, ?, ?)',
                             (lease_id, str(token_id or '')[:64], str(tool or '')[:64], os.getpid(), at,
                              at + self.ttl))
            return lease_id
        except Exception:  # noqa: BLE001
            log.exception('[MCP] места вызовов: mcp.db недоступна, остаётся предел процесса')
            return self.LOCAL_LEASE

    def release(self, lease_id: Optional[str]) -> None:
        if not lease_id or lease_id == self.LOCAL_LEASE:
            return
        try:
            with db.write() as conn:
                conn.execute('DELETE FROM call_leases WHERE id = ?', (lease_id,))
        except Exception:  # noqa: BLE001 — аренда истечёт сама через ttl
            log.exception('[MCP] не удалось отпустить место вызова %s (освободится через %s с)',
                          lease_id, int(self.ttl))

    def active(self, now: Optional[float] = None) -> int:
        """Сколько мест занято сейчас (для тестов и страницы доступа)."""
        at = time.time() if now is None else float(now)
        _ensure_limits_schema()
        with db.read() as conn:
            return conn.execute('SELECT COUNT(*) AS n FROM call_leases WHERE expires_at > ?',
                                (at,)).fetchone()['n']

    def reset(self) -> None:
        """Отпустить все места (тесты)."""
        try:
            _ensure_limits_schema()
            with db.write() as conn:
                conn.execute('DELETE FROM call_leases')
        except Exception:  # noqa: BLE001
            log.exception('[MCP] не удалось очистить call_leases')


rate_limiter = RateLimiter()
call_leases = CallLeases()
call_slots = threading.BoundedSemaphore(MAX_CONCURRENT_CALLS)

BUSY_MESSAGE = ('Сервер занят: уже идут другие вызовы агентов. Повторите через минуту — сайт '
                'обслуживает сотрудников в первую очередь.')


@contextmanager
def admission(token_id: str, tool: str) -> Iterator[Optional['bridge.ToolResult']]:
    """Пропуск на исполнение инструмента: None — место есть и держится до выхода из блока;
    ToolResult (denied) — мест нет. Сначала страховка процесса, потом аренда на сервис."""
    if not call_slots.acquire(blocking=False):
        yield bridge.ToolResult.refuse(BUSY_MESSAGE, http_status=503)
        return
    try:
        lease = call_leases.acquire(token_id, tool)
        if lease is None:
            yield bridge.ToolResult.refuse(BUSY_MESSAGE, http_status=503)
            return
        try:
            yield None
        finally:
            call_leases.release(lease)
    finally:
        call_slots.release()


# ------------------------------------------------------------------ помощники

def app_version() -> str:
    """Версия приложения (git-хэш) без импорта extensions (он тяжёлый)."""
    version = None
    try:
        version = current_app.jinja_env.globals.get('app_version')
    except Exception:  # noqa: BLE001 — вне контекста приложения
        version = None
    if not version:
        version = getattr(sys.modules.get('extensions'), 'APP_VERSION', None)
    return str(version or 'dev')


def effective_mode(url_mode: Optional[str], principal: Principal) -> str:
    """Действующий режим: более строгий из режима адреса (нет суффикса — full) и токена."""
    return stricter_mode(url_mode or 'full', getattr(principal, 'mode', 'full'))


def server_info(domain: Optional[str], mode: str = 'full') -> Dict[str, str]:
    title = DOMAINS[domain].title if domain in DOMAINS else 'все разделы'
    return {'name': SERVER_NAME, 'title': f'Культура — {title} · {MODE_TITLES.get(mode, mode)}',
            'version': app_version()}


def instructions(domain: Optional[str], mode: str) -> str:
    """instructions: строка о режиме + правила (registry.instructions_for)."""
    text = registry.instructions_for(domain)
    line = MODE_LINES.get(mode, '')
    return line + ('\n\n' + text if text else '') if line else text


def connector_label(domain: Optional[str], mode: str = 'full') -> str:
    """Коннектор для журнала: 'content', 'all', с режимом — 'content/read'."""
    base = domain or 'all'
    return base if mode == 'full' else f'{base}/{mode}'


def _clip(value: Any, limit: int = ECHO_LIMIT) -> str:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _json_response(payload: Any, status: int = 200, headers: Optional[Dict[str, str]] = None) -> Response:
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    resp = Response(body, status=status, mimetype='application/json')
    resp.headers['Cache-Control'] = 'no-store'
    for key, value in (headers or {}).items():
        resp.headers[key] = value
    return resp


def not_found(message: str) -> Response:
    """404 JSON для адресов, которых у MCP нет."""
    return _json_response({'error': message}, 404)


def _accepted() -> Response:
    resp = Response(b'', status=202)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def origin_allowed(request) -> bool:
    """Защита от DNS rebinding: Origin есть -> хост свой, Claude или локальный."""
    origin = request.headers.get('Origin')
    if origin is None:
        return True
    try:
        host = (urlsplit(origin.strip()).hostname or '').lower()
    except ValueError:
        return False
    if not host:
        return False                                   # 'null' и мусор
    own = (urlsplit(request.host_url).hostname or '').lower()
    if host == own or host in ALLOWED_ORIGIN_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in ALLOWED_ORIGIN_SUFFIXES)


def _valid_id(value: Any) -> bool:
    return (isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool)))


def _decode_header(value: Optional[str]) -> Optional[str]:
    """Mcp-Name: значение как есть или из base64-обёртки '=?base64?…?='. Битая обёртка -> None."""
    if value is None:
        return None
    if value.startswith('=?base64?') and value.endswith('?=') and len(value) >= 11:
        payload = value[len('=?base64?'):-2]
        try:
            raw = base64.b64decode(payload, validate=True)
            if base64.b64encode(raw).decode('ascii') != payload:
                return None
            return raw.decode('utf-8')
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return None
    return value


def read_body(request) -> Optional[bytes]:
    """Тело запроса не длиннее MAX_REQUEST_BYTES; None — больше предела.

    Читается кусками из request.stream и не дальше MAX_REQUEST_BYTES + 1 байта: при
    chunked-передаче (без Content-Length) get_data() прочитал бы в память всё, что
    пришлёт клиент.
    """
    length = request.content_length
    if length is not None and length > MAX_REQUEST_BYTES:
        return None
    stream = request.stream
    chunks: List[bytes] = []
    total = 0
    while True:
        chunk = stream.read(min(READ_CHUNK, MAX_REQUEST_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_REQUEST_BYTES:
            return None
    return b''.join(chunks)


# ------------------------------------------------------------------ вход HTTP

def handle_http(request, domain: Optional[str], mode: Optional[str] = None) -> Response:
    """Обработать HTTP-запрос к коннектору: /mcp[/<домен>][/<режим>] (None — не задано)."""
    if domain is not None and domain not in DOMAINS:
        return _json_response({'error': f'Нет коннектора /mcp/{_clip(domain)}. Есть: /mcp и '
                                        + ', '.join(d.connector_path for d in DOMAINS.values())}, 404)
    if mode is not None and mode not in URL_MODES:
        return _json_response({'error': f'Нет режима {_clip(mode)}: к адресу коннектора можно добавить '
                                        f'/read или /draft (полный доступ — адрес без суффикса)'}, 404)
    if not origin_allowed(request):
        return _json_response(RpcError(INVALID_REQUEST, 'Запрос с этого сайта (Origin) запрещён').body(None), 403)

    try:
        checked = auth.authenticate(request, domain, mode)
    except Exception:  # noqa: BLE001 — сбой хранилища токенов/аккаунтов: «повторите позже», не 401
        log.exception('[MCP] проверка токена упала')
        return _json_response({'error': 'Проверка доступа временно недоступна, повторите позже.'}, 503,
                              {'Retry-After': '30'})
    if isinstance(checked, auth.AuthError):
        headers = {'WWW-Authenticate': checked.www_authenticate} if checked.www_authenticate else None
        return _json_response({'error': checked.message}, checked.status, headers)
    principal: Principal = checked

    if request.method != 'POST':
        return _json_response({'error': 'Этот сервер MCP не держит SSE-поток и сессии: только POST.'}, 405,
                              {'Allow': 'POST'})
    raw = read_body(request)
    if raw is None:
        return _json_response(RpcError(INVALID_REQUEST, f'Тело запроса больше '
                                                        f'{MAX_REQUEST_BYTES // (1024 * 1024)} МБ').body(None), 413)
    try:
        body = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return _json_response(RpcError(PARSE_ERROR, 'Некорректный JSON').body(None), 400)

    session = _Call(request, domain, principal, effective_mode(mode, principal))
    if isinstance(body, list):
        return session.batch(body)
    if isinstance(body, dict):
        return session.single(body)
    return _json_response(RpcError(INVALID_REQUEST, 'Ожидается объект JSON-RPC').body(None), 400)


class _Call:
    """Обработка одного HTTP-запроса (сервер без состояния: ничего между запросами не помнит)."""

    def __init__(self, request, domain: Optional[str], principal: Principal, mode: str = 'full'):
        self.request = request
        self.domain = domain
        self.principal = principal
        self.mode = mode
        self.header_version = request.headers.get(HEADER_VERSION)

    # --- разбор сообщения ---

    def _era(self, msg: Dict[str, Any]) -> str:
        params = msg.get('params')
        meta = params.get('_meta') if isinstance(params, dict) else None
        if isinstance(meta, dict) and META_VERSION in meta:
            return 'modern'
        if self.header_version is not None and self.header_version in MODERN_VERSIONS:
            return 'modern'
        if msg.get('method') == 'initialize':
            return 'legacy'
        if self.header_version is not None and self.header_version not in LEGACY_VERSIONS:
            return 'unsupported'
        return 'legacy'

    def single(self, msg: Dict[str, Any]) -> Response:
        method = msg.get('method')
        if not isinstance(method, str):
            if 'id' in msg and ('result' in msg or 'error' in msg):
                return _accepted()                      # ответ клиента на наш запрос (мы их не шлём)
            rid = msg.get('id') if _valid_id(msg.get('id')) else None
            return _json_response(RpcError(INVALID_REQUEST, 'Нет поля method').body(rid), 400)
        if 'id' not in msg:
            return _accepted()                          # уведомление: notifications/initialized и др.
        rid = msg.get('id')
        if not _valid_id(rid):
            return _json_response(RpcError(INVALID_REQUEST, 'id должен быть строкой или целым числом')
                                  .body(None), 400)
        era = self._era(msg)
        if era == 'unsupported':
            return _json_response(self._unsupported(self.header_version).body(rid), 400)
        if era == 'modern':
            return self._modern(msg, rid, method)
        response = self._legacy_message(msg, self.header_version or DEFAULT_LEGACY)
        if response is None:
            return _accepted()
        return _json_response(response, 400 if response.get('error', {}).get('code') == INVALID_REQUEST else 200)

    def batch(self, messages: List[Any]) -> Response:
        if not messages:
            return _json_response(RpcError(INVALID_REQUEST, 'Пустой пакет').body(None), 400)
        if len(messages) > MAX_BATCH:
            return _json_response(RpcError(INVALID_REQUEST, f'В пакете не больше {MAX_BATCH} сообщений')
                                  .body(None), 400)
        version = self.header_version or DEFAULT_LEGACY
        if version in MODERN_VERSIONS or any(
                isinstance(m, dict) and isinstance(m.get('params'), dict)
                and isinstance(m['params'].get('_meta'), dict) and META_VERSION in m['params']['_meta']
                for m in messages):
            return _json_response(RpcError(INVALID_REQUEST, 'Пакеты запросов в MCP 2026-07-28 не поддерживаются: '
                                                            'один запрос — один POST').body(None), 400)
        if version not in LEGACY_VERSIONS:
            return _json_response(self._unsupported(version).body(None), 400)
        if version not in BATCH_VERSIONS:
            return _json_response(RpcError(INVALID_REQUEST, f'Пакеты запросов (JSON-массив) есть только в версиях '
                                                            f'{", ".join(BATCH_VERSIONS)}; в {version} их нет')
                                  .body(None), 400)
        responses = []
        for msg in messages:
            if not isinstance(msg, dict):
                responses.append(RpcError(INVALID_REQUEST, 'Элемент пакета — не объект').body(None))
                continue
            response = self._legacy_message(msg, version)
            if response is not None:
                responses.append(response)
        if not responses:
            return _accepted()
        return _json_response(responses)

    def _unsupported(self, requested: Any) -> RpcError:
        return RpcError(UNSUPPORTED_VERSION, 'Unsupported protocol version',
                        {'supported': list(SUPPORTED_VERSIONS), 'requested': _clip(requested)})

    # --- старая эпоха (initialize) ---

    def _legacy_message(self, msg: Dict[str, Any], version: str) -> Optional[Dict[str, Any]]:
        method = msg.get('method')
        if not isinstance(method, str):
            if 'id' in msg and ('result' in msg or 'error' in msg):
                return None
            rid = msg.get('id') if _valid_id(msg.get('id')) else None
            return RpcError(INVALID_REQUEST, 'Нет поля method').body(rid)
        if 'id' not in msg:
            return None
        rid = msg.get('id')
        if not _valid_id(rid):
            return RpcError(INVALID_REQUEST, 'id должен быть строкой или целым числом').body(None)
        if msg.get('jsonrpc') != '2.0':
            return RpcError(INVALID_REQUEST, 'Поле jsonrpc должно быть "2.0"').body(rid)
        params = msg.get('params')
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return RpcError(INVALID_PARAMS, 'params должен быть объектом').body(rid)
        try:
            if method == 'initialize':
                result = self._initialize(params)
            elif method == 'ping':
                result = {}
            else:
                result = self._dispatch(method, params)
        except RpcError as err:
            return err.body(rid)
        except Exception:  # noqa: BLE001
            log.exception('[MCP] сбой метода %s', _clip(method))
            return RpcError(INTERNAL_ERROR, 'Внутренняя ошибка сервера MCP').body(rid)
        return {'jsonrpc': '2.0', 'id': rid, 'result': result}

    def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        requested = params.get('protocolVersion')
        negotiated = requested if requested in LEGACY_VERSIONS else LATEST_LEGACY
        result: Dict[str, Any] = {'protocolVersion': negotiated, 'capabilities': CAPABILITIES,
                                  'serverInfo': server_info(self.domain, self.mode)}
        text = instructions(self.domain, self.mode)
        if text:
            result['instructions'] = text
        return result

    # --- новая эпоха (2026-07-28) ---

    def _modern(self, msg: Dict[str, Any], rid: Any, method: str) -> Response:
        try:
            if msg.get('jsonrpc') != '2.0':
                raise RpcError(INVALID_REQUEST, 'Поле jsonrpc должно быть "2.0"')
            params = msg.get('params')
            meta = params.get('_meta') if isinstance(params, dict) else None
            if not isinstance(meta, dict):
                raise RpcError(INVALID_PARAMS, f'params._meta должен быть объектом с ключами {META_VERSION} '
                                               f'и {META_CAPABILITIES}')
            missing = [k for k in (META_VERSION, META_CAPABILITIES) if k not in meta]
            if missing:
                raise RpcError(INVALID_PARAMS, 'В params._meta нет обязательных ключей: ' + ', '.join(missing))
            version = meta[META_VERSION]
            if self.header_version is None or self.header_version != version:
                raise RpcError(HEADER_MISMATCH, f'Header mismatch: {HEADER_VERSION} не совпадает с версией в _meta')
            if self.request.headers.get(HEADER_METHOD) != method:
                raise RpcError(HEADER_MISMATCH, f'Header mismatch: {HEADER_METHOD} не совпадает с method')
            name_key = NAME_BEARING.get(method)
            if name_key is not None:
                body_name = params.get(name_key)
                if body_name is not None and _decode_header(self.request.headers.get(HEADER_NAME)) != body_name:
                    raise RpcError(HEADER_MISMATCH, f'Header mismatch: {HEADER_NAME} не совпадает с params.{name_key}')
            if not isinstance(version, str):
                raise RpcError(INVALID_PARAMS, 'Версия протокола в _meta должна быть строкой')
            if version not in MODERN_VERSIONS:
                raise self._unsupported(version)
            if method == 'server/discover':
                result = {'supportedVersions': list(SUPPORTED_VERSIONS), 'capabilities': CAPABILITIES}
                text = instructions(self.domain, self.mode)
                if text:
                    result['instructions'] = text
                result.update(ttlMs=LIST_TTL_MS, cacheScope='private')
            else:
                result = self._dispatch(method, params)
                if method in ('tools/list', 'prompts/list'):
                    result.update(ttlMs=LIST_TTL_MS, cacheScope='private')
        except RpcError as err:
            status = err.http or MODERN_ERROR_HTTP.get(err.code, 200)
            return _json_response(err.body(rid), status)
        except Exception:  # noqa: BLE001
            log.exception('[MCP] сбой метода %s', _clip(method))
            return _json_response(RpcError(INTERNAL_ERROR, 'Внутренняя ошибка сервера MCP').body(rid), 200)
        result['resultType'] = 'complete'
        result['_meta'] = {META_SERVER: server_info(self.domain, self.mode)}
        return _json_response({'jsonrpc': '2.0', 'id': rid, 'result': result})

    # --- общие методы ---

    def _dispatch(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if method == 'tools/list':
            return {'tools': [tool_json(t) for t in registry.tools_for(self.domain)
                              if allowed_in_mode(t, self.mode)]}
        if method == 'tools/call':
            return self._call_tool(params)
        if method == 'prompts/list':
            # Сценарий, которому нужен режим мягче коннектора, не показываем: агент
            # упёрся бы в отказ сервера на первой же записи (spec.PromptSpec.mode_required).
            return {'prompts': [prompt_json(p) for p in registry.prompts_for(self.domain)
                                if prompt_allowed_in_mode(p, self.mode)]}
        if method == 'prompts/get':
            return self._get_prompt(params)
        raise RpcError(METHOD_NOT_FOUND, f'Метод не поддерживается: {_clip(method)}')

    def _audit(self, tool: str, args: Any, status: str, result: Optional[bridge.ToolResult] = None,
               duration_ms: Optional[int] = None, error: str = '') -> None:
        try:
            audit.record(user_login=self.principal.login, token_id=self.principal.token_id,
                         client_name=self.principal.client_name,
                         connector=connector_label(self.domain, self.mode),
                         tool=tool, args=args, status=status,
                         http_status=result.http_status if result else None, duration_ms=duration_ms,
                         result_chars=result.result_chars if result else None,
                         error=error or (result.error if result and result.is_error else ''))
        except Exception:  # noqa: BLE001 — журнал не должен ломать ответ агенту
            log.exception('[MCP] не удалось записать журнал вызова %s', _clip(tool))

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get('name')
        args = params.get('arguments')
        valid_name = isinstance(name, str) and bool(TOOL_NAME_RE.match(name))
        # Имя для журнала: корректное — как есть (≤ 64 символов по TOOL_NAME_RE),
        # иначе обрезанное; в ответ кривое имя не попадает вовсе.
        logged = name if valid_name else _clip(name if isinstance(name, str) else '<не строка>')
        # 1) Лимит частоты — до поиска инструмента: отказы тоже его расходуют.
        wait = rate_limiter.hit(self.principal.token_id)
        if wait is not None:
            message = (f'Слишком часто: не больше {RATE_LIMIT_PER_MINUTE} вызовов инструментов в минуту '
                       f'на токен. Подождите {wait} с и повторите.')
            self._audit(logged, args if valid_name else None, 'denied', error=message)
            return bridge.ToolResult.fail(message, http_status=429).to_mcp()
        if not valid_name:
            self._audit(logged, None, 'denied', error='некорректное имя инструмента')
            raise RpcError(INVALID_PARAMS, 'Некорректное имя инструмента: нужна латиница в нижнем регистре, '
                                           'цифры и «_», 3–64 символа (список — tools/list)')
        spec = registry.get_tool(name)
        if spec is None or not registry.tool_visible(spec, self.domain):
            self._audit(name, args, 'denied', error='инструмент не найден в этом коннекторе')
            raise RpcError(INVALID_PARAMS, f'Неизвестный инструмент в этом коннекторе: {name}')
        if not allowed_in_mode(spec, self.mode):
            message = (f'Инструмент {name} недоступен в режиме «{MODE_TITLES.get(self.mode, self.mode)}»: '
                       f'в этом подключении можно только '
                       f'{"читать" if self.mode == "read" else "читать и готовить черновики"}. '
                       f'Такие действия владелец выполняет сам или в подключении с полным доступом.')
            self._audit(name, args, 'denied', error=message)
            return bridge.ToolResult.fail(message, http_status=403).to_mcp()
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise RpcError(INVALID_PARAMS, 'params.arguments должен быть объектом')
        # Место для исполнения (на процесс и на сервис) мост берёт сам, только когда
        # действительно исполняет маршрут: ответ из кэша тяжёлых чтений места не занимает.
        token_id = self.principal.token_id
        started = time.monotonic()
        result = bridge.execute(spec, args, self.principal, connector=self.domain, mode=self.mode,
                                admit=lambda: admission(token_id, name))
        if result.denied:
            self._audit(name, args, 'denied', error=result.error)
            return result.to_mcp()
        duration = int((time.monotonic() - started) * 1000)
        self._audit(name, args, 'error' if result.is_error else 'ok', result, duration)
        return result.to_mcp()

    def _get_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get('name')
        if not isinstance(name, str) or not name:
            raise RpcError(INVALID_PARAMS, 'Нужно имя подсказки: params.name')
        if not PROMPT_NAME_RE.match(name):
            raise RpcError(INVALID_PARAMS, 'Некорректное имя подсказки (список — prompts/list)')
        prompt = registry.get_prompt(name)
        if prompt is None or (self.domain is not None and prompt.domain not in (self.domain, COMMON_DOMAIN)):
            raise RpcError(INVALID_PARAMS, f'Неизвестная подсказка в этом коннекторе: {name}')
        if not prompt_allowed_in_mode(prompt, self.mode):
            raise RpcError(INVALID_PARAMS,
                           f'Сценарий {name} требует режим «{MODE_TITLES.get(prompt.mode_required, prompt.mode_required)}», '
                           f'а этот коннектор — «{MODE_TITLES.get(self.mode, self.mode)}».')
        args = params.get('arguments') or {}
        if not isinstance(args, dict):
            raise RpcError(INVALID_PARAMS, 'params.arguments должен быть объектом')
        clean = {str(k): ('' if v is None else str(v)) for k, v in args.items()}
        missing = [a.name for a in prompt.arguments if a.required and not clean.get(a.name, '').strip()]
        if missing:
            raise RpcError(INVALID_PARAMS, 'Не хватает аргументов подсказки: ' + ', '.join(missing))
        try:
            text = prompt.render(clean)
        except Exception as exc:  # noqa: BLE001
            log.exception('[MCP] подсказка %s упала', name)
            raise RpcError(INTERNAL_ERROR, f'Подсказка {name} не собралась: {type(exc).__name__}: {exc}')
        return {'description': prompt.description,
                'messages': [{'role': 'user', 'content': {'type': 'text', 'text': str(text)}}]}


# ------------------------------------------------------------------ JSON описаний

def tool_json(spec) -> Dict[str, Any]:
    """Инструмент для tools/list."""
    return {'name': spec.name, 'title': spec.title, 'description': spec.description,
            'inputSchema': spec.input_schema, 'annotations': spec.annotations()}


def prompt_json(prompt) -> Dict[str, Any]:
    """Подсказка для prompts/list."""
    return {'name': prompt.name, 'title': prompt.title, 'description': prompt.description,
            'arguments': [{'name': a.name, 'description': a.description, 'required': a.required}
                          for a in prompt.arguments]}
