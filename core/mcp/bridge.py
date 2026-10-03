"""Мост MCP -> Flask: исполняет настоящий маршрут сайта внутри процесса от имени владельца.

Главный принцип платформы: инструмент вызывает ТОТ ЖЕ маршрут, что и страница.
Агент видит те же цифры, что владелец на сайте (до копейки), а бизнес-логика
не дублируется. Мост — единственное место, где аргументы MCP превращаются в
HTTP-запрос и ответ маршрута — в результат MCP.

Как исполняется маршрут (execute -> _run_route):
1. Аргументы проверяются по inputSchema (core/mcp/schema_check.py); ошибка ->
   результат isError с русским текстом, агент исправит вызов сам.
2. Аргументы раскладываются в запрос по описанию ToolSpec:
       path_params  -> в путь по <имени>, с URL-экранированием (кириллица, «/»);
       query_params -> строка запроса; список -> повтор ключа (?bar=a&bar=b);
       file_params  -> файлы multipart: {filename, content_base64, mime_type};
       остальное    -> тело: JSON (body='json', всегда объект, пусть пустой),
                       форма (body='form') или multipart (body='multipart').
   Булевы значения в строке запроса и в форме кодируются как '1' / '0': так их
   понимает большинство маршрутов сервиса (`in ('1','true','yes')`, `== '1'`).
   Маршрут, который сравнивает с 'true' (например, active_only в routes/taps.py),
   описывается строкой с enum ['true','false'], а не boolean.
3. СВЕЖИЙ контекст приложения (`with app.app_context()`), в нём
   `app.test_request_context(путь, method, query_string, тело, base_url=<внешний
   адрес сайта>)`. Свежий контекст — это отдельный flask.g: кэши g, которые
   маршрут заводит для себя, не смешиваются с g MCP-запроса, и наоборот.
4. Пользователь: g._current_user = копия записи владельца из auth_manager +
   {'via_mcp': True, 'mcp_mode': действующий режим ('read'|'draft'|'full'),
    'mcp_client': имя клиента, 'mcp_token_id': id токена, 'mcp_connection_id': id
    подключения — грант OAuth или статический токен (Principal.connection_id); учёт «на
    подключение» ведите по нему: id OAuth-токена меняется каждый час}. По mcp_mode
   маршрут может сузить права агента (контент-план в режиме draft правит только свои
   черновики).
   core.auth_guard.current_user() берёт пользователя из g — гейт авторизации и
   маршруты видят владельца. Логин не меняется: журналы маршрутов подписываются
   логином владельца; признак via_mcp позволяет маршруту пометить действие агента.
   Перед исполнением собранный путь сверяется с картой маршрутов приложения
   (url_map.match по раскодированному пути): совпасть должно ровно правило spec.path.
   Иначе значение параметра пути «увело» запрос в другой маршрут (например, id
   'abc/log' превратил бы чтение материала в чтение его журнала) — isError
   «недопустимое значение параметра пути».
5. app.full_dispatch_request() — полный путь запроса: before_request (гейт),
   маршрут, after_request. Тело читается ВНУТРИ контекста (потоковые ответы
   stream_with_context требуют живого запроса), затем resp.close() — всегда.

Упаковка ответа (package_response):
    2xx JSON          -> text: компактный JSON (ensure_ascii=False). Длиннее
                         RESULT_TEXT_LIMIT — структурное обрезание (shrink_json):
                         самые большие списки укорачиваются, в конец вставляется
                         {"_обрезано": "показано N из M; сузьте фильтры"}; JSON
                         всегда валиден; первая строка текста — предупреждение.
    2xx text/*, xml   -> text (обрезка по символам с предупреждением).
    image png/jpeg/webp до IMAGE_INLINE_MAX_BYTES -> image (base64), иначе текст со
                         ссылкой.
    прочее бинарное   -> до BLOB_INLINE_MAX_BYTES — embedded resource (blob), иначе
                         текст с размером и полной ссылкой на маршрут: владелец
                         откроет её в браузере под своим входом.
    3xx               -> текст «перенаправление на …».
    4xx/5xx           -> isError: поле error из JSON (или начало тела) + код.
    Исключение в маршруте -> isError с текстом ошибки, стек — в лог.
У send_file/send_from_directory выставлен direct_passthrough: перед чтением он
сбрасывается (иначе Werkzeug не отдаст тело), размер проверяется ДО чтения по
Content-Length — большой файл не читается в память.

Ограничения:
- heavy=True (живой запрос в iiko): общий на процесс семафор на HEAVY_CONCURRENCY
  вызова; ждём до HEAVY_WAIT_S секунд, потом isError «iiko занят». В проде два
  gunicorn-воркера, значит всего не больше 2 x HEAVY_CONCURRENCY одновременных.
  Число одновременных вызовов инструментов вообще ограничивает protocol.py
  (MAX_CONCURRENT_CALLS, общий для процессов через mcp.db): протокол передаёт в
  execute() «пропуск» admit — мост берёт его только когда действительно исполняет
  маршрут (ответ из кэша места не занимает). Ожидание здесь держит поток воркера,
  который нужен сайту.
- Защита от рекурсии: пути /mcp…, /oauth…, /.well-known/… и /api/admin/mcp… мост не
  исполняет (агент не вызывает сам себя и не управляет доступом к себе).

Кэш тяжёлых чтений (ResponseCache, с 2026-09-28). Агент часто спрашивает одно и то
же дважды подряд (доска заказа бара, затем та же доска «ещё раз посмотреть»), а
каждый такой вызов — живой отчёт iiko на 5–40 с. Поэтому результат запоминается:
- что кэшируется: инструмент heavy и read_only, не open_world (живой ЧЗ и прочее
  «вовне» — только живьём) и без пометки no_cache (проверка связи с iiko); в
  аргументах нет force/refresh/full со значением «да» (1, '1', true, 'true', 'yes',
  'on') — это явная просьба пересчитать, такой вызов идёт мимо кэша и в кэш не
  кладётся. Новых аргументов «мимо кэша» нет и не будет: схемы запрещают лишние поля;
- ключ — (инструмент, владелец токена, нормализованные аргументы с сортировкой
  ключей): {'bar': 'Лиговский'} и тот же вызов через минуту — одно и то же;
- в кэш идёт только успешный результат из одних текстовых блоков (JSON, CSV, XML):
  ошибки, картинки и файлы (PDF, xlsx) — нет;
- срок CACHE_TTL_S = 300 с (5 минут): свежее, чем кэш снимка остатков у самих
  маршрутов (120 с) плюс время разговора; старше — уже заметно расходится с сайтом;
- предел памяти: не больше CACHE_MAX_ENTRIES = 64 записей и CACHE_MAX_BYTES = 2 МБ
  текста (UTF-8) на процесс; одна запись не больше четверти предела. Результат и так
  не длиннее RESULT_TEXT_LIMIT (60 тыс. символов, до ~240 КБ), поэтому 64 записи в
  2 МБ не влезают, и при нехватке вытесняются самые давно использованные (LRU).
  Почему так мало: у воркера gunicorn своя память (2 воркера), а кэш — ускоритель
  повторов в одном разговоре, а не хранилище отчётов;
- в начале ответа (отдельным первым текстовым блоком, JSON во втором блоке остаётся
  валидным) — строка «Данные на ЧЧ:ММ МСК (кэш до 5 минут)»: время, когда маршрут
  посчитал эти данные; у свежего результата — время сейчас;
- любая успешная запись через MCP (инструмент без read_only) очищает кэш процесса:
  агент, который заменил кегу, следом увидит новый таплист, а не пятиминутный.
  Поколение кэша (generation) защищает от гонки: чтение, начатое до записи, не
  положит в кэш данные «до записи». Правки людей на сайте и записи во втором
  воркере кэш не видит — старше 5 минут данные не бывают, и время на ответе названо.

Инструмент без маршрута (handler): handler(args, principal) -> dict | list | str |
ToolResult; упаковывается по тем же правилам. Обработчик может бросить ToolError —
это ошибка для агента без стека в логе. Контекст вызова (коннектор, владелец) —
current_call().
"""
import base64
import binascii
import contextvars
import copy
import io
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlencode, urlsplit

import flask
from flask import current_app, has_request_context
from werkzeug.datastructures import MultiDict

from core import msk_time
from core.mcp import schema_check
from core.mcp.principal import Principal
from core.mcp.spec import ToolSpec

log = logging.getLogger('mcp.bridge')

# --------------------------------------------------------------------- константы

# Предел текста одного результата. ~60 тыс. символов ≈ 15–20 тыс. токенов: больше
# агенту в контекст брать вредно (вытесняет разговор), а сайт почти всегда умеет
# сузить выборку фильтрами — об этом и говорит пометка об обрезании.
RESULT_TEXT_LIMIT = 60000

# Картинка до 700 КБ идёт агенту как изображение: base64 раздувает её на треть
# (~930 КБ в JSON-ответе) — это ещё приемлемо; фото с телефона крупнее — ссылкой.
IMAGE_INLINE_MAX_BYTES = 700 * 1024
IMAGE_MIMETYPES = ('image/png', 'image/jpeg', 'image/webp')

# Прочие файлы (xlsx, pdf) до 2 МБ — вложением (embedded resource blob).
BLOB_INLINE_MAX_BYTES = 2 * 1024 * 1024

# JSON больше 30 МБ не разбираем целиком (память воркера) — отдаём начало текстом.
JSON_PARSE_MAX_BYTES = 30 * 1024 * 1024

# Текстовый ответ читаем не больше 8 МБ: в результат всё равно войдут первые
# RESULT_TEXT_LIMIT символов, остальное нужно только чтобы назвать размер.
TEXT_READ_MAX_BYTES = 8 * 1024 * 1024

# Тело ошибки (4xx/5xx) — первые 64 КБ; в текст для агента идут ERROR_TEXT_LIMIT символов.
ERROR_READ_MAX_BYTES = 64 * 1024
ERROR_TEXT_LIMIT = 4000

# Живые запросы в iiko: не больше двух одновременно на процесс. iiko отвечает на OLAP
# за 5–40 с; два параллельных отчёта iiko держит, больше — начинает отвечать ошибками
# и тормозит кассы. Ждать места — не дольше 10 с (было 90): у воркера gunicorn всего
# 4 потока, и поток, который ждёт iiko для агента, не обслуживает страницы сайта.
# Агенту дешевле получить «iiko занят» и повторить через минуту.
HEAVY_CONCURRENCY = 2
HEAVY_WAIT_S = 10

# Кэш тяжёлых чтений (правила и почему такие числа — в докстринге модуля).
CACHE_TTL_S = 300                            # 5 минут
CACHE_MAX_ENTRIES = 64                       # записей на процесс
CACHE_MAX_BYTES = 2 * 1024 * 1024            # 2 МБ текста (UTF-8) на процесс
CACHE_ENTRY_MAX_BYTES = CACHE_MAX_BYTES // 4  # одна запись не вытесняет весь кэш
# Аргументы «пересчитай»: со значением «да» вызов идёт мимо кэша (у маршрутов они уже есть).
FRESH_ARGS = ('force', 'refresh', 'full')
TRUTHY_VALUES = ('1', 'true', 'yes', 'on')

# Внешний адрес, если мост вызван вне HTTP-запроса (тесты, фоновые задачи).
DEFAULT_BASE_URL = 'http://localhost/'

# Пути, которые мост не исполняет (рекурсия и управление доступом).
FORBIDDEN_PREFIXES = ('/mcp', '/oauth', '/.well-known', '/api/admin/mcp')

TRUNCATION_KEY = '_обрезано'
MAX_SHRINK_ROUNDS = 500          # страховка от бесконечного цикла обрезания
MIN_STRING_KEEP = 200            # короче этого строки при обрезании не режем

TEXT_MIMETYPES = ('application/xml', 'application/javascript', 'application/x-yaml',
                  'application/yaml', 'application/csv', 'application/x-ndjson')

_HEAVY = threading.BoundedSemaphore(HEAVY_CONCURRENCY)


# --------------------------------------------------------------------- результат

@dataclass
class ToolResult:
    """Результат инструмента: блоки content MCP + признак ошибки + данные для журнала.

    denied — отказ ДО исполнения (нет свободного места для вызова): протокол пишет
    его в журнал статусом 'denied', а не 'error'. cached — ответ взят из кэша
    тяжёлых чтений (для тестов и отладки; агенту это говорит строка «Данные на …»).
    """
    content: List[Dict[str, Any]]
    is_error: bool = False
    http_status: Optional[int] = None
    error: str = ''
    truncated: bool = False
    denied: bool = False
    cached: bool = False

    @classmethod
    def text(cls, text: str, *, is_error: bool = False, http_status: Optional[int] = None,
             truncated: bool = False) -> 'ToolResult':
        return cls([{'type': 'text', 'text': text}], is_error=is_error, http_status=http_status,
                   error=text if is_error else '', truncated=truncated)

    @classmethod
    def fail(cls, message: str, http_status: Optional[int] = None) -> 'ToolResult':
        return cls.text(message, is_error=True, http_status=http_status)

    @classmethod
    def refuse(cls, message: str, http_status: Optional[int] = None) -> 'ToolResult':
        """Отказ до исполнения (сервер занят): isError для агента, 'denied' для журнала."""
        result = cls.fail(message, http_status=http_status)
        result.denied = True
        return result

    def to_mcp(self) -> Dict[str, Any]:
        """Поле result ответа tools/call (без structuredContent — контракт 4.2)."""
        return {'content': self.content, 'isError': self.is_error}

    @property
    def result_chars(self) -> int:
        total = 0
        for block in self.content:
            if block.get('type') == 'text':
                total += len(block.get('text') or '')
            elif block.get('type') == 'image':
                total += len(block.get('data') or '')
            elif block.get('type') == 'resource':
                res = block.get('resource') or {}
                total += len(res.get('blob') or res.get('text') or '')
        return total

    @property
    def text_value(self) -> str:
        """Весь текст результата одной строкой (тесты, журнал)."""
        return '\n'.join(b.get('text') or '' for b in self.content if b.get('type') == 'text')


class ToolError(Exception):
    """Ошибка обработчика для агента: текст уходит в isError, стек в лог не пишется."""


@dataclass(frozen=True)
class CallContext:
    principal: Optional[Principal]
    connector: Optional[str]
    tool: str
    mode: str = 'full'            # действующий режим доступа (spec.MODES)


_CALL: 'contextvars.ContextVar[Optional[CallContext]]' = contextvars.ContextVar('mcp_call', default=None)


def current_call() -> Optional[CallContext]:
    """Контекст текущего вызова инструмента (для обработчиков: коннектор, владелец)."""
    return _CALL.get()


# --------------------------------------------------------------------- исполнение

def execute(spec: ToolSpec, args: Optional[Dict[str, Any]], principal: Principal,
            connector: Optional[str] = None, mode: str = 'full',
            admit: Optional[Callable[[], Any]] = None) -> ToolResult:
    """Исполнить инструмент. Никогда не бросает: любая беда -> ToolResult(is_error=True).

    mode — действующий режим доступа (его уже применил protocol.py к списку и вызову);
    мост передаёт его маршруту в g._current_user['mcp_mode'] и обработчикам в current_call().

    admit — «пропуск» протокола: функция, возвращающая контекстный менеджер, который
    отдаёт None (место есть, держим его до конца исполнения) или ToolResult отказа
    («сервер занят», denied). Берётся только перед настоящим исполнением: проверка
    аргументов и ответ из кэша места не занимают. None — без пропуска (тесты, фон).

    Порядок: проверка аргументов -> кэш тяжёлых чтений -> пропуск -> семафор heavy ->
    маршрут или обработчик -> кэш / очистка кэша после записи (см. докстринг модуля).
    """
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return ToolResult.fail('Аргументы инструмента должны быть объектом JSON.')
    problem = schema_check.validate_arguments(spec.input_schema, args, spec.name)
    if problem:
        return ToolResult.fail(problem)
    args = schema_check.normalize(spec.input_schema, args)
    token = _CALL.set(CallContext(principal=principal, connector=connector, tool=spec.name, mode=mode))
    try:
        key = cache_key(spec, args, principal) if cacheable(spec, args) else None
        if key is not None:
            entry = response_cache.get(key)
            if entry is not None:
                return with_freshness(entry.result, entry.stored_at, cached=True)
        generation = response_cache.generation
        if admit is None:
            result = _run_limited(spec, args, principal, mode)
        else:
            with admit() as refusal:
                if refusal is not None:
                    return refusal
                result = _run_limited(spec, args, principal, mode)
        if key is not None:
            if not cache_worthy(result):
                return result
            stored_at = msk_time.now()
            response_cache.put(key, result, stored_at, generation=generation)
            return with_freshness(result, stored_at)
        if not spec.read_only and not result.is_error:
            # Запись через MCP: всё, что было в кэше, могло устареть (кега, заказ, план).
            response_cache.clear()
        return result
    finally:
        _CALL.reset(token)


def _run_limited(spec: ToolSpec, args: Dict[str, Any], principal: Principal, mode: str) -> ToolResult:
    """Исполнение с семафором тяжёлых вызовов (HEAVY_CONCURRENCY, ожидание HEAVY_WAIT_S)."""
    if spec.heavy:
        if not _HEAVY.acquire(timeout=HEAVY_WAIT_S):
            return ToolResult.fail('iiko занят: уже идут тяжёлые запросы к iiko. Повторите через минуту.')
        try:
            return _run(spec, args, principal, mode)
        finally:
            _HEAVY.release()
    return _run(spec, args, principal, mode)


# --------------------------------------------------------------------- кэш тяжёлых чтений

def wants_fresh(args: Dict[str, Any]) -> bool:
    """В аргументах явная просьба пересчитать: force/refresh/full со значением «да»."""
    for name in FRESH_ARGS:
        value = args.get(name)
        if value is True or (isinstance(value, (int, float)) and not isinstance(value, bool) and value == 1):
            return True
        if isinstance(value, str) and value.strip().lower() in TRUTHY_VALUES:
            return True
    return False


def cacheable(spec: ToolSpec, args: Dict[str, Any]) -> bool:
    """Можно ли брать ответ инструмента из кэша (правило — докстринг модуля)."""
    if not (spec.heavy and spec.read_only) or spec.open_world or spec.no_cache:
        return False
    return not wants_fresh(args)


def cache_key(spec: ToolSpec, args: Dict[str, Any], principal: Principal) -> str:
    """Ключ: инструмент + владелец токена + аргументы (ключи отсортированы, JSON компактный)."""
    return json.dumps([spec.name, getattr(principal, 'user_id', None), args], ensure_ascii=False,
                      sort_keys=True, separators=(',', ':'), default=str)


def cache_worthy(result: ToolResult) -> bool:
    """В кэш — только успешный ответ из одних текстовых блоков (не ошибки, не файлы)."""
    if result.is_error or result.denied or not result.content:
        return False
    return all(block.get('type') == 'text' for block in result.content)


def freshness_line(stored_at: datetime) -> str:
    """«Данные на ЧЧ:ММ МСК (кэш до 5 минут)» — первая строка ответа кэшируемого инструмента."""
    return f'Данные на {stored_at.strftime("%H:%M")} МСК (кэш до {CACHE_TTL_S // 60} минут)'


def with_freshness(result: ToolResult, stored_at: datetime, cached: bool = False) -> ToolResult:
    """Копия результата с первым текстовым блоком «Данные на …» (сам результат не меняется)."""
    return ToolResult([{'type': 'text', 'text': freshness_line(stored_at)}] + [dict(b) for b in result.content],
                      is_error=result.is_error, http_status=result.http_status, error=result.error,
                      truncated=result.truncated, cached=cached)


@dataclass
class CacheEntry:
    result: ToolResult          # без строки свежести
    stored_at: datetime         # МСК: когда маршрут посчитал данные
    expires: float              # time.monotonic() истечения
    size: int                   # байт текста (UTF-8)


def _result_bytes(result: ToolResult) -> int:
    return sum(len((block.get('text') or '').encode('utf-8')) for block in result.content)


class ResponseCache:
    """LRU-кэш ответов тяжёлых чтений в памяти процесса (правила — докстринг модуля).

    Потокобезопасен: воркер gunicorn обслуживает несколько потоков. generation растёт
    при каждой очистке; put() с устаревшим поколением ничего не кладёт — так чтение,
    начатое до записи через MCP, не вернёт в кэш данные «до записи».
    """

    def __init__(self, ttl: float = CACHE_TTL_S, max_entries: int = CACHE_MAX_ENTRIES,
                 max_bytes: int = CACHE_MAX_BYTES, entry_max_bytes: int = CACHE_ENTRY_MAX_BYTES):
        self.ttl = ttl
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.entry_max_bytes = entry_max_bytes
        self.generation = 0
        self._data: 'OrderedDict[str, CacheEntry]' = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def get(self, key: str, now: Optional[float] = None) -> Optional[CacheEntry]:
        now = time.monotonic() if now is None else now
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires <= now:
                self._drop(key)
                return None
            self._data.move_to_end(key)            # недавно использованная — в конец очереди
            return entry

    def put(self, key: str, result: ToolResult, stored_at: datetime, generation: Optional[int] = None,
            now: Optional[float] = None) -> bool:
        """Положить ответ. False — не положен (другое поколение или слишком большой)."""
        now = time.monotonic() if now is None else now
        size = _result_bytes(result)
        if size > self.entry_max_bytes:
            return False
        with self._lock:
            if generation is not None and generation != self.generation:
                return False
            if key in self._data:
                self._drop(key)
            self._data[key] = CacheEntry(result=ToolResult([dict(b) for b in result.content],
                                                           http_status=result.http_status,
                                                           truncated=result.truncated),
                                         stored_at=stored_at, expires=now + self.ttl, size=size)
            self._bytes += size
            for stale in [k for k, e in self._data.items() if e.expires <= now]:
                self._drop(stale)
            while self._data and (len(self._data) > self.max_entries or self._bytes > self.max_bytes):
                self._drop(next(iter(self._data)))   # самая давно использованная
            return key in self._data

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._bytes = 0
            self.generation += 1

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {'entries': len(self._data), 'bytes': self._bytes, 'generation': self.generation}

    def _drop(self, key: str) -> None:
        entry = self._data.pop(key, None)
        if entry is not None:
            self._bytes -= entry.size


response_cache = ResponseCache()


def _run(spec: ToolSpec, args: Dict[str, Any], principal: Principal, mode: str = 'full') -> ToolResult:
    if spec.handler is not None:
        return _run_handler(spec, args, principal)
    return _run_route(spec, args, principal, mode)


def _run_handler(spec: ToolSpec, args: Dict[str, Any], principal: Principal) -> ToolResult:
    try:
        out = spec.handler(args, principal)
    except ToolError as exc:
        return ToolResult.fail(str(exc))
    except Exception as exc:  # noqa: BLE001 — сбой обработчика -> isError, а не 500 всему коннектору
        log.exception('[MCP] обработчик %s упал', spec.name)
        return ToolResult.fail(f'Инструмент {spec.name} упал: {type(exc).__name__}: {exc}')
    if isinstance(out, ToolResult):
        return out
    if out is None:
        return ToolResult.text('Готово.')
    if isinstance(out, (dict, list)):
        return json_result(out)
    return text_result(str(out))


# --------------------------------------------------------------------- сборка запроса

def is_forbidden_path(path: str) -> bool:
    """Путь, который мост не исполняет (см. FORBIDDEN_PREFIXES)."""
    clean = '/' + path.lstrip('/')
    for prefix in FORBIDDEN_PREFIXES:
        if clean == prefix or clean.startswith(prefix + '/') or clean.startswith(prefix + '?'):
            return True
    return False


_PARAM_RE = re.compile(r'<(?:([a-z_]+)(?:\([^)]*\))?:)?([A-Za-z_][A-Za-z0-9_]*)>')


def build_path(spec: ToolSpec, args: Dict[str, Any]) -> str:
    """Подставить параметры пути (URL-экранирование; '/' тоже экранируется)."""
    def repl(match):
        name = match.group(2)
        if name not in args or args[name] is None:
            raise ValueError(f'Не хватает параметра пути «{name}»')
        return quote(_scalar(args[name]), safe='')
    return _PARAM_RE.sub(repl, spec.path)


def _scalar(value: Any) -> str:
    """Скаляр для пути, строки запроса и формы (правило булевых — в докстринге модуля)."""
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return str(value)


def _pairs(names, args: Dict[str, Any]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for name in names:
        value = args.get(name)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            pairs.extend((name, _scalar(v)) for v in value if v is not None)
        else:
            pairs.append((name, _scalar(value)))
    return pairs


def build_query(spec: ToolSpec, args: Dict[str, Any]) -> str:
    return urlencode(_pairs(spec.query_params, args))


def _decode_file(name: str, value: Any) -> Tuple[io.BytesIO, str, str]:
    if not isinstance(value, dict):
        raise ValueError(f'Поле «{name}»: файл передаётся объектом {{filename, content_base64, mime_type}}')
    filename = str(value.get('filename') or 'file').strip() or 'file'
    mime = str(value.get('mime_type') or 'application/octet-stream').strip()
    raw = value.get('content_base64')
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f'Поле «{name}»: пустой content_base64')
    text = raw.strip()
    if text.startswith('data:') and ',' in text:     # data:image/png;base64,....
        text = text.split(',', 1)[1]
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f'Поле «{name}»: content_base64 — не base64')
    return io.BytesIO(data), filename, mime


def build_body(spec: ToolSpec, args: Dict[str, Any]) -> Dict[str, Any]:
    """Аргументы тела -> kwargs для test_request_context (json= / data= / content_type=)."""
    routed = set(spec.path_params) | set(spec.query_params) | set(spec.file_params)
    body = {k: v for k, v in args.items() if k not in routed}
    if spec.body == 'json':
        return {'json': body}
    if spec.body == 'form':
        return {'data': MultiDict(_pairs(sorted(body), body)), 'content_type': 'application/x-www-form-urlencoded'}
    if spec.body == 'multipart':
        fields: Dict[str, Any] = {}
        for key, value in _pairs(sorted(body), body):
            fields.setdefault(key, []).append(value)
        for name in spec.file_params:
            if args.get(name) is not None:
                fields[name] = _decode_file(name, args[name])
        data = {k: (v[0] if isinstance(v, list) and len(v) == 1 else v) for k, v in fields.items()}
        return {'data': data, 'content_type': 'multipart/form-data'}
    return {}


def _external_base() -> str:
    if has_request_context():
        try:
            return flask.request.host_url
        except Exception:  # noqa: BLE001
            pass
    return DEFAULT_BASE_URL


def _remote_addr() -> str:
    if has_request_context():
        return flask.request.remote_addr or '127.0.0.1'
    return '127.0.0.1'


def owner_record(principal: Principal, mode: str = 'full') -> Optional[Dict[str, Any]]:
    """Запись владельца для g._current_user (None — не активный администратор)."""
    from core.auth_manager import get_auth_manager
    user = get_auth_manager().get_by_id(principal.user_id)
    if not user or not user.get('active') or not user.get('is_admin'):
        return None
    record = dict(user)
    record.update({'via_mcp': True, 'mcp_mode': mode, 'mcp_client': principal.client_name,
                   'mcp_token_id': principal.token_id, 'mcp_connection_id': principal.connection_id()})
    return record


PATH_PARAM_ERROR = 'Недопустимое значение параметра пути'


def check_path_matches(app, spec: ToolSpec, path: str, base: str) -> Optional[str]:
    """Собранный путь ведёт ровно в маршрут spec.path? None — да, иначе текст ошибки.

    Сверка по карте маршрутов приложения (url_map, привязка к внешнему хосту) и по
    РАСКОДИРОВАННОМУ пути — так же маршрут выберет сам запрос: %2F в значении станет
    «/» и может увести в соседнее правило. Метод не подходит (405) — это не про
    значение параметра: такое пропускаем, ответ 405 даст сам маршрут.
    """
    from werkzeug.exceptions import MethodNotAllowed, NotFound
    from werkzeug.routing import RequestRedirect
    parts = urlsplit(base)
    adapter = app.url_map.bind(parts.netloc or 'localhost', url_scheme=parts.scheme or 'http')
    try:
        rule, _ = adapter.match(unquote(path), method=spec.method, return_rule=True)
    except MethodNotAllowed:
        return None
    except (NotFound, RequestRedirect):
        return f'{PATH_PARAM_ERROR}: адрес {path} не ведёт в маршрут {spec.path}.'
    if rule.rule != spec.path:
        return (f'{PATH_PARAM_ERROR}: значение увело запрос в другой маршрут ({rule.rule} вместо '
                f'{spec.path}). Проверьте id: в нём не должно быть «/».')
    return None


def _run_route(spec: ToolSpec, args: Dict[str, Any], principal: Principal, mode: str = 'full') -> ToolResult:
    try:
        path = build_path(spec, args)
        query = build_query(spec, args)
        body_kwargs = build_body(spec, args)
    except ValueError as exc:
        return ToolResult.fail(str(exc))
    if is_forbidden_path(path):
        return ToolResult.fail(f'Путь {path} мостом не исполняется: агент не вызывает MCP и не управляет '
                               f'доступом к себе.')
    # owner_record(principal) — вызов с одним аргументом: тесты доменов подменяют эту функцию
    # своей заглушкой старой формы. Режим дописывается отдельно — маршрут видит его всегда.
    owner = owner_record(principal)
    if owner is None:
        return ToolResult.fail('Нет доступа: владелец токена не найден или больше не активный администратор.',
                               http_status=401)
    owner = dict(owner, mcp_mode=mode)
    base = _external_base()
    full_url = base.rstrip('/') + path + ('?' + query if query else '')
    app = current_app._get_current_object()
    if spec.path_params:
        mismatch = check_path_matches(app, spec, path, base)
        if mismatch:
            return ToolResult.fail(mismatch)
    headers = {'Accept': 'application/json', 'User-Agent': 'kultura-mcp-bridge/1',
               'X-MCP-Tool': spec.name}
    try:
        with app.app_context():
            with app.test_request_context(path, method=spec.method, query_string=query, base_url=base,
                                          headers=headers, environ_base={'REMOTE_ADDR': _remote_addr()},
                                          **body_kwargs):
                flask.g._current_user = owner
                resp = app.full_dispatch_request()
                try:
                    return package_response(resp, full_url)
                finally:
                    resp.close()
    except Exception as exc:  # noqa: BLE001 — исключение маршрута -> isError, стек в лог
        log.exception('[MCP] маршрут %s %s упал (инструмент %s)', spec.method, path, spec.name)
        return ToolResult.fail(f'Маршрут {spec.method} {path} упал: {type(exc).__name__}: {exc}', http_status=500)


# --------------------------------------------------------------------- упаковка ответа

def _read_limited(resp, limit: int) -> Tuple[bytes, bool]:
    """Тело ответа не длиннее limit байт. (данные, True если тело больше limit)."""
    resp.direct_passthrough = False
    length = resp.content_length
    if length is not None and length > limit:
        return b'', True
    if length is not None:
        return resp.get_data(), False
    chunks: List[bytes] = []
    total = 0
    for chunk in resp.iter_encoded():
        total += len(chunk)
        if total > limit:
            return b''.join(chunks), True
        chunks.append(chunk)
    return b''.join(chunks), False


def _human_size(size: Optional[int]) -> str:
    if size is None:
        return 'неизвестного размера'
    if size < 1024:
        return f'{size} Б'
    if size < 1024 * 1024:
        return f'{size / 1024:.0f} КБ'
    return f'{size / (1024 * 1024):.1f} МБ'.replace('.', ',')


def _charset(resp) -> str:
    return (resp.mimetype_params or {}).get('charset') or 'utf-8'


def _is_text_mimetype(mimetype: str) -> bool:
    return mimetype.startswith('text/') or mimetype in TEXT_MIMETYPES or mimetype.endswith('+xml')


def package_response(resp, url: str) -> ToolResult:
    """Ответ маршрута -> ToolResult (правила — в докстринге модуля)."""
    status = resp.status_code
    mimetype = (resp.mimetype or '').lower()
    if 300 <= status < 400:
        location = resp.headers.get('Location') or ''
        return ToolResult.text(f'Перенаправление на {location or "(адрес не указан)"} (HTTP {status}).',
                               http_status=status)
    if status >= 400:
        return _error_result(resp, status, mimetype)

    if resp.is_json:
        data, too_big = _read_limited(resp, JSON_PARSE_MAX_BYTES)
        if too_big:
            return ToolResult.text(f'Ответ JSON {_human_size(resp.content_length)} слишком велик для разбора. '
                                   f'Сузьте фильтры (период, бар) и повторите. Адрес: {url}',
                                   http_status=status, truncated=True)
        if not data.strip():
            return ToolResult.text(f'Готово (HTTP {status}), ответ пустой.', http_status=status)
        try:
            value = json.loads(data.decode(_charset(resp), errors='replace'))
        except ValueError:
            return text_result(data.decode(_charset(resp), errors='replace'), http_status=status)
        return json_result(value, http_status=status)

    if mimetype in IMAGE_MIMETYPES:
        data, too_big = _read_limited(resp, IMAGE_INLINE_MAX_BYTES)
        if too_big:
            return ToolResult.text(_link_text(mimetype, resp.content_length, IMAGE_INLINE_MAX_BYTES, url),
                                   http_status=status)
        return ToolResult([
            {'type': 'text', 'text': f'Изображение {mimetype}, {_human_size(len(data))}. Адрес: {url}'},
            {'type': 'image', 'data': base64.b64encode(data).decode('ascii'), 'mimeType': mimetype},
        ], http_status=status)

    if _is_text_mimetype(mimetype) or not mimetype:
        data, too_big = _read_limited(resp, TEXT_READ_MAX_BYTES)
        text = data.decode(_charset(resp), errors='replace')
        if not text.strip() and not too_big:
            return ToolResult.text(f'Готово (HTTP {status}), ответ пустой.', http_status=status)
        return text_result(text, http_status=status, total_hint=None if not too_big else resp.content_length,
                           cut_by_reader=too_big)

    data, too_big = _read_limited(resp, BLOB_INLINE_MAX_BYTES)
    if too_big:
        return ToolResult.text(_link_text(mimetype, resp.content_length, BLOB_INLINE_MAX_BYTES, url),
                               http_status=status)
    return ToolResult([
        {'type': 'text', 'text': f'Файл {mimetype}, {_human_size(len(data))}. Адрес: {url}'},
        {'type': 'resource', 'resource': {'uri': url, 'mimeType': mimetype,
                                          'blob': base64.b64encode(data).decode('ascii')}},
    ], http_status=status)


def _link_text(mimetype: str, size: Optional[int], limit: int, url: str) -> str:
    return (f'Файл {mimetype} ({_human_size(size)}) больше предела {_human_size(limit)} для передачи агенту. '
            f'Владелец может открыть его в браузере под своим входом: {url}')


_TAG_RE = re.compile(r'<[^>]+>')
_SPACE_RE = re.compile(r'\s+')


def _error_result(resp, status: int, mimetype: str) -> ToolResult:
    data, _ = _read_limited(resp, ERROR_READ_MAX_BYTES)
    text = data.decode(_charset(resp), errors='replace')
    message, details = '', ''
    if resp.is_json:
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            message = str(payload.get('error') or payload.get('message') or '').strip()
            extra = {k: v for k, v in payload.items() if k not in ('error', 'message')}
            if extra:
                details = json.dumps(extra, ensure_ascii=False, separators=(',', ':'))
        elif payload is not None:
            details = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    if not message and not details:
        plain = text
        if 'html' in mimetype:
            plain = _TAG_RE.sub(' ', text)
        message = _SPACE_RE.sub(' ', plain).strip()
    if not message:
        message = resp.status
    out = f'Ошибка HTTP {status}: {message}'
    if details:
        out += '\nПодробности: ' + details
    if len(out) > ERROR_TEXT_LIMIT:
        out = out[:ERROR_TEXT_LIMIT - 1] + '…'
    return ToolResult([{'type': 'text', 'text': out}], is_error=True, http_status=status, error=message or out)


# --------------------------------------------------------------------- JSON и текст

def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)


def json_result(value: Any, http_status: Optional[int] = None) -> ToolResult:
    """JSON-значение -> text-блок (со структурным обрезанием при превышении предела)."""
    text = _dumps(value)
    if len(text) <= RESULT_TEXT_LIMIT:
        return ToolResult.text(text, http_status=http_status)
    warning = (f'ВНИМАНИЕ: ответ обрезан до {RESULT_TEXT_LIMIT} символов (полный — {len(text)}). '
               f'Самые длинные списки укорочены, в их конце стоит элемент '
               f'{{"{TRUNCATION_KEY}": "показано N из M; сузьте фильтры"}}. Нужны все строки — '
               f'сузьте период, бар или другие фильтры. Ниже — валидный JSON.')
    budget = RESULT_TEXT_LIMIT - len(warning) - 1
    return ToolResult.text(warning + '\n' + shrink_json(value, budget), http_status=http_status, truncated=True)


def text_result(text: str, http_status: Optional[int] = None, total_hint: Optional[int] = None,
                cut_by_reader: bool = False) -> ToolResult:
    """Текст -> text-блок; длиннее предела — начало с предупреждением первой строкой."""
    if len(text) <= RESULT_TEXT_LIMIT and not cut_by_reader:
        return ToolResult.text(text, http_status=http_status)
    total = f'{len(text)} символов' if not cut_by_reader else f'больше {len(text)} символов' + (
        f' ({_human_size(total_hint)})' if total_hint else '')
    shown = min(len(text), RESULT_TEXT_LIMIT - 200)
    warning = f'ВНИМАНИЕ: ответ обрезан — показаны первые {shown} из {total}. Сузьте запрос.'
    return ToolResult.text(warning + '\n' + text[:shown], http_status=http_status, truncated=True)


# --- структурное обрезание JSON ---

def _node_size(node: Any, sizes: Dict[int, int], containers: List[Any]) -> int:
    """Длина компактной записи node; попутно запоминает размеры списков и объектов."""
    if isinstance(node, list):
        total = 2 + max(len(node) - 1, 0)
        for item in node:
            total += _node_size(item, sizes, containers)
        sizes[id(node)] = total
        containers.append(node)
        return total
    if isinstance(node, dict):
        total = 2 + max(len(node) - 1, 0)
        for key, item in node.items():
            total += len(_dumps(str(key))) + 1 + _node_size(item, sizes, containers)
        sizes[id(node)] = total
        containers.append(node)
        return total
    return len(_dumps(node))


def _marker_text(shown: int, total: int, unit: str) -> str:
    return f'показано {shown} из {total}{unit}; сузьте фильтры'


def _largest_fit(entry_sizes: List[int], target: int, marker_size) -> int:
    """Наибольшее k (1..n-1), при котором k первых элементов + пометка влезают в target; иначе 1.

    Размер с k элементами строго растёт с k (каждый элемент добавляет ≥ 2 символа,
    а пометка удлиняется максимум на цифру), поэтому годится двоичный поиск.
    """
    prefix = [0]
    for size in entry_sizes:
        prefix.append(prefix[-1] + size)

    def size_with(k: int) -> int:
        return 2 + prefix[k] + (k - 1) + 1 + marker_size(k)

    low, high, best = 1, len(entry_sizes) - 1, 1
    while low <= high:
        mid = (low + high) // 2
        if size_with(mid) <= target:
            best, low = mid, mid + 1
        else:
            high = mid - 1
    return best


def _cut_list(node: list, excess: int, sizes: Dict[int, int], cut: Dict[int, Tuple[int, int]]) -> bool:
    """Укоротить список на ≥ excess символов (сколько получится). False — резать уже нечего."""
    real = node[:-1] if id(node) in cut else node[:]
    original = cut.get(id(node), (len(real), len(real)))[1]
    if len(real) <= 1:
        return False
    item_sizes = [_node_size(item, {}, []) for item in real]
    best = _largest_fit(item_sizes, sizes[id(node)] - excess,
                        lambda k: len(_dumps({TRUNCATION_KEY: _marker_text(k, original, '')})))
    node[:] = real[:best] + [{TRUNCATION_KEY: _marker_text(best, original, '')}]
    cut[id(node)] = (best, original)
    return True


def _cut_dict(node: dict, excess: int, sizes: Dict[int, int], cut: Dict[int, Tuple[int, int]]) -> bool:
    """То же для объекта: остаются первые k ключей + ключ-пометка."""
    keys = [k for k in node if k != TRUNCATION_KEY]
    original = cut.get(id(node), (len(keys), len(keys)))[1]
    if len(keys) <= 1:
        return False
    entry_sizes = [len(_dumps(str(k))) + 1 + _node_size(node[k], {}, []) for k in keys]
    best = _largest_fit(entry_sizes, sizes[id(node)] - excess,
                        lambda k: len(_dumps(TRUNCATION_KEY)) + 1 + len(_dumps(_marker_text(k, original, ' ключей'))))
    kept = {k: node[k] for k in keys[:best]}
    node.clear()
    node.update(kept)
    node[TRUNCATION_KEY] = _marker_text(best, original, ' ключей')
    cut[id(node)] = (best, original)
    return True


def _longest_string(node: Any, best: List[Any]) -> None:
    """best = [длина, контейнер, ключ] самой длинной строки-значения."""
    if isinstance(node, list):
        for index, item in enumerate(node):
            if isinstance(item, str):
                if len(item) > best[0]:
                    best[:] = [len(item), node, index]
            else:
                _longest_string(item, best)
    elif isinstance(node, dict):
        for key, item in node.items():
            if isinstance(item, str):
                if len(item) > best[0] and key != TRUNCATION_KEY:
                    best[:] = [len(item), node, key]
            else:
                _longest_string(item, best)


def shrink_json(value: Any, budget: int) -> str:
    """Валидный JSON не длиннее budget символов (см. докстринг модуля).

    Порядок: 1) самые большие списки укорачиваются (пропорционально превышению);
    2) если списки кончились — большие объекты по ключам; 3) самые длинные строки;
    4) крайний случай — объект с началом исходного текста.
    """
    work = copy.deepcopy(value)
    cut: Dict[int, Tuple[int, int]] = {}
    frozen = set()
    for _ in range(MAX_SHRINK_ROUNDS):
        sizes: Dict[int, int] = {}
        containers: List[Any] = []
        total = _node_size(work, sizes, containers)
        if total <= budget:
            return _dumps(work)
        excess = total - budget
        lists = [c for c in containers if isinstance(c, list) and id(c) not in frozen]
        dicts = [c for c in containers if isinstance(c, dict) and id(c) not in frozen]
        pool = lists or dicts
        if not pool:
            break
        target = max(pool, key=lambda c: sizes[id(c)])
        cutter = _cut_list if isinstance(target, list) else _cut_dict
        if not cutter(target, excess, sizes, cut):
            frozen.add(id(target))
    if isinstance(work, str) and len(_dumps(work)) > budget:
        # Ответ — одна длинная строка: режем её саму, тип значения сохраняется.
        keep = max(0, budget - 80)
        while keep and len(_dumps(work[:keep] + '…')) + 40 > budget:
            keep = max(0, keep - (len(_dumps(work[:keep] + '…')) + 40 - budget) - 1)
        work = work[:keep] + f'… [{TRUNCATION_KEY}: {keep} из {len(value)} симв.]'
    for _ in range(MAX_SHRINK_ROUNDS):
        text = _dumps(work)
        if len(text) <= budget:
            return text
        best: List[Any] = [MIN_STRING_KEEP, None, None]
        _longest_string(work, best)
        if best[1] is None:
            break
        length, holder, key = best
        excess = len(text) - budget
        keep = max(MIN_STRING_KEEP // 2, length - excess - 60)
        holder[key] = holder[key][:keep] + f'… [{TRUNCATION_KEY}: {keep} из {length} симв.]'
    text = _dumps(work)
    if len(text) <= budget:
        return text
    raw = _dumps(value)
    keep = max(0, budget - 200)
    while True:
        fallback = _dumps({TRUNCATION_KEY: 'ответ слишком велик даже после сокращения списков; '
                                           'ниже — начало исходного JSON строкой',
                           'начало': raw[:keep]})
        if len(fallback) <= budget or keep == 0:
            if len(fallback) <= budget:
                return fallback
            tiny = _dumps({TRUNCATION_KEY: 'ответ слишком велик'})
            return tiny if len(tiny) <= budget else '{}'   # предел меньше любой пометки — пустой объект
        keep = max(0, keep - (len(fallback) - budget) - 10)
