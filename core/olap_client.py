"""Доступ конструктора отчётов (/explorer) к iiko: сессия, запросы, ошибки, нагрузка, кэш.

Что это
    Тонкий слой между конструктором OLAP (core/olap_constructor.py, core/olap_catalog.py)
    и iiko Server API. Авторизация — общая для проекта (OlapReports.connect /
    disconnect: SHA-1 пароля, слот лицензии освобождается logout). Своё здесь то,
    что нужно конструктору и чего нет у готовых помощников OlapReports:

    - ТЕКСТ ОШИБКИ iiko. Конструктор собирает запрос из любых полей, и iiko может его
      отклонить («Filtering is not allowed for field …»). Пользователь должен увидеть
      эту причину, а не «нет данных» — поэтому ответ не 200 превращается в IikoError
      с текстом iiko (_post_olap_interactive в OlapReports молча возвращает None).
    - ОДИН ВХОД НА СЕРИЮ ЗАПРОСОВ. Отчёт со столбцами и «итогами iiko» — это два
      запроса (core/olap_constructor.py, «План запросов»); они идут по одному токену и
      параллельно, вход и выход — один раз.
    - БЕРЕЖНОСТЬ К БОЕВОМУ СЕРВЕРУ. Тот же сервер обслуживает кассы баров. На процесс
      не больше MAX_PARALLEL мест: сессия берёт столько мест, сколько у неё
      параллельных запросов (серия из двух — два), ДО входа в iiko и отдаёт после
      выхода. Так ограничены и запросы, и входы (слоты лицензии API): в проде два
      воркера gunicorn — не больше 4 всего. Место ждём WAIT_SLOT_S секунд, потом
      честная ошибка «iiko занят».
    - КЭШ ОТВЕТОВ. Одна и та же СЕРИЯ запросов за CACHE_TTL_S секунд отдаётся из памяти
      (повторное «Построить», выгрузка в Excel того же отчёта, агент спросил дважды).
      Ключ — хэш всех тел серии вместе: ответы серии всегда из одного похода в iiko.
      По отдельным телам кэшировать нельзя: запрос «только строки» совпадает с
      запросом 'rows' отчёта со столбцами, и итог «Итого» взялся бы из ответа
      десятиминутной давности, а ячейки — из свежего (итог меньше суммы столбцов).

Константы (почему такие)
    CONNECT_TIMEOUT = 10 с   — как у интерактивных отчётов проекта: TLS-рукопожатие с iiko
                               изредка зависает (замер 2026-08-13, core/olap_reports.py).
    READ_TIMEOUT = 120 с     — отчёт за год строится 14 с, разовые выбросы до 63 с
                               (docs/lessons.md, 2026-08-11); gunicorn обрывает воркер на
                               180 с (Dockerfile), с запасом на вход в iiko.
    MAX_PARALLEL = 2         — как у тяжёлых вызовов MCP (core/mcp/bridge.py).
    WAIT_SLOT_S = 60 с       — дольше ждать место бессмысленно: пользователь уйдёт.
    CACHE_TTL_S = 600 с      — как DASHBOARD_OLAP_CACHE (extensions.py).
    CACHE_MAX_CELLS = 1 000 000 и CACHE_ENTRY_MAX_CELLS = 300 000 — предел памяти кэша
                               в значениях (ячейка ответа iiko: поле строки data или
                               summary). Замер на ответе iiko: строка из 10 полей в
                               памяти Python ~940 байт, т.е. ~94 байта на значение —
                               весь кэш не больше ~100 МБ на воркер, одна серия — ~30 МБ.
                               Серия крупнее не кэшируется: кэш — ускоритель повторов,
                               а не хранилище (год по позициям — 37 МБ JSON).
    CACHE_MAX_ENTRIES = 64   — предел числа серий (мелкие списки значений фильтров).

Повтор запроса
    Один повтор через 1,5 с — только если связь не установилась (соединение не
    открылось или оборвалось до ответа). Если iiko уже считал отчёт и оборвал его
    на середине или не уложился в READ_TIMEOUT, повтора нет: тяжёлый отчёт ушёл бы в
    iiko второй раз.

Как тесты подменяют iiko
    set_session_factory(фабрика) — фабрика возвращает объект с методами post_olap(body)
    и get_json(path, params) и протоколом with (вход/выход). Настоящая — IikoSession.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import requests
from urllib3.exceptions import ReadTimeoutError

from core import msk_time

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 120
MAX_PARALLEL = 2
WAIT_SLOT_S = 60
CACHE_TTL_S = 600
CACHE_MAX_CELLS = 1000000
CACHE_ENTRY_MAX_CELLS = 300000
CACHE_MAX_ENTRIES = 64
ERROR_TEXT_LIMIT = 400      # сколько символов текста ошибки iiko показывать


class IikoError(Exception):
    """Ошибка обращения к iiko. status — HTTP-код, который вернёт наш маршрут."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


class _Slots:
    """Места для запросов к iiko на процесс. Сессия берёт сразу столько мест, сколько у
    неё параллельных запросов: по одному две серии могли бы взять по месту и ждать
    второго вечно."""

    def __init__(self, total: int):
        self.total = total
        self._free = total
        self._cond = threading.Condition()

    def acquire(self, count: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._free < count:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self._cond.wait(left)
            self._free -= count
            return True

    def release(self, count: int) -> None:
        with self._cond:
            self._free += count
            self._cond.notify_all()


_slots = _Slots(MAX_PARALLEL)


def _timeout_error() -> IikoError:
    return IikoError('iiko не ответил за ' + str(READ_TIMEOUT) + ' с. Сузьте период или '
                     'уберите поля с большим числом значений.', 504)


def _clean_error_text(text: str) -> str:
    """Текст ошибки iiko для человека: без HTML, одной строкой, не длиннее предела."""
    text = (text or '').strip()
    if text.lower().startswith('<!doctype') or text.lower().startswith('<html'):
        return 'сервер iiko вернул HTML вместо ответа API (сетевая ошибка или настройка сервера)'
    text = ' '.join(text.split())
    if len(text) > ERROR_TEXT_LIMIT:
        text = text[:ERROR_TEXT_LIMIT] + '…'
    return text


class IikoSession:
    """Один вход в iiko на серию запросов; выход (освобождение слота лицензии) — в __exit__."""

    def __init__(self):
        from core.olap_reports import OlapReports   # тяжёлый импорт — только когда нужен iiko
        self._olap = OlapReports()
        self._open = False

    def __enter__(self):
        if not self._olap.connect():
            raise IikoError('Не удалось войти в iiko: сервер недоступен, неверный логин или '
                            'заняты все слоты лицензии API. Повторите через минуту.', 502)
        self._open = True
        return self

    def __exit__(self, *exc):
        if self._open:
            try:
                self._olap.disconnect()
            except Exception:  # noqa: BLE001 — выход не должен ронять ответ
                pass
            self._open = False
        return False

    def _request(self, method: str, path: str, params: Optional[dict] = None,
                 body: Optional[dict] = None) -> Any:
        """Один запрос к iiko. Место на него сессия взяла при входе (open_session)."""
        url = self._olap.api.base_url + path
        query = dict(params or {})
        query['key'] = self._olap.token
        response = None
        for attempt in (1, 2):
            try:
                response = requests.request(
                    method, url, params=query, json=body,
                    headers={'Content-Type': 'application/json'} if body is not None else None,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
                break
            except requests.exceptions.ReadTimeout:
                raise _timeout_error()
            except requests.exceptions.ConnectionError as error:
                # Таймаут посреди тела ответа requests поднимает как ConnectionError:
                # iiko уже считал отчёт — не повторяем (см. «Повтор запроса»).
                reason = error.args[0] if error.args else None
                if isinstance(reason, ReadTimeoutError) or 'Read timed out' in str(error):
                    raise _timeout_error()
                if attempt == 2:
                    raise IikoError('Нет связи с iiko: ' + type(error).__name__ + '.', 502)
                time.sleep(1.5)
            except (requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ContentDecodingError) as error:
                raise IikoError('iiko оборвал ответ на середине (' + type(error).__name__ +
                                '). Повторите; если повторяется — сузьте период.', 502)
            except requests.exceptions.RequestException as error:
                raise IikoError('Запрос к iiko не выполнен: ' + type(error).__name__ + '.', 502)

        if response.status_code == 200:
            try:
                return response.json()
            except ValueError:
                raise IikoError('iiko вернул ответ, который не читается как JSON.', 502)
        text = _clean_error_text(response.text)
        if response.status_code in (401, 403):
            raise IikoError('iiko отказал в доступе (HTTP ' + str(response.status_code) + '): ' +
                            (text or 'нет права или слота лицензии API') + '.', 502)
        if 400 <= response.status_code < 500:
            raise IikoError('iiko отклонил запрос: ' + (text or 'без пояснения') + '.', 400)
        raise IikoError('Ошибка сервера iiko (HTTP ' + str(response.status_code) + '): ' +
                        (text or 'без пояснения') + '.', 502)

    def post_olap(self, body: dict) -> dict:
        """POST /v2/reports/olap — ответ {data, summary}."""
        data = self._request('POST', '/v2/reports/olap', body=body)
        if not isinstance(data, dict) or not isinstance(data.get('data'), list):
            raise IikoError('iiko вернул OLAP-ответ без списка data.', 502)
        return data

    def get_json(self, path: str, params: Optional[dict] = None) -> Any:
        """GET пути API (например, /v2/reports/olap/columns) — разобранный JSON."""
        return self._request('GET', path, params=params)


_session_factory: Callable[[], Any] = IikoSession


def set_session_factory(factory: Optional[Callable[[], Any]]) -> None:
    """Тесты: подменить iiko. None — вернуть настоящую сессию."""
    global _session_factory
    _session_factory = factory or IikoSession


class _SlottedSession:
    """Сессия iiko, которая держит места (_slots) от входа до выхода."""

    def __init__(self, session: Any, parallel: int):
        self._session = session
        self._count = max(1, min(parallel, _slots.total))

    def __enter__(self):
        if not _slots.acquire(self._count, WAIT_SLOT_S):
            raise IikoError('iiko занят другими отчётами конструктора — повторите через '
                            'минуту.', 503)
        try:
            return self._session.__enter__()
        except BaseException:
            _slots.release(self._count)
            raise

    def __exit__(self, *exc):
        try:
            return self._session.__exit__(*exc)
        finally:
            _slots.release(self._count)


def open_session(parallel: int = 1):
    """Новая сессия iiko (контекстный менеджер) на parallel одновременных запросов."""
    return _SlottedSession(_session_factory(), parallel)


# ---------------------------------------------------------------- кэш ответов OLAP

# ключ серии -> (время, ответы серии, 'ЧЧ:ММ', число значений)
_cache: Dict[str, Tuple[float, List[dict], str, int]] = {}
_cache_cells = 0
_cache_lock = threading.Lock()
_inflight: Dict[str, list] = {}           # ключ серии -> [замок, сколько потоков его ждут]


def series_key(bodies: List[dict]) -> str:
    """Ключ кэша: хэш канонического JSON всех тел серии (порядок важен)."""
    raw = json.dumps(bodies, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()


def _cells(answers: List[dict]) -> int:
    """Размер серии в значениях — мера памяти кэша (см. CACHE_MAX_CELLS)."""
    total = 0
    for answer in answers:
        for row in answer['data']:
            total += len(row) if isinstance(row, dict) else 1
        for block in answer['summary']:
            if isinstance(block, (list, tuple)):
                total += sum(len(part) if isinstance(part, dict) else 1 for part in block)
            else:
                total += 1
    return total


def _cache_get(key: str) -> Optional[Tuple[List[dict], str]]:
    global _cache_cells
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        stamp, answers, clock, cells = entry
        if time.time() - stamp >= CACHE_TTL_S:
            _cache.pop(key, None)
            _cache_cells -= cells
            return None
        return answers, clock


def _cache_put(key: str, answers: List[dict], clock: str) -> None:
    global _cache_cells
    cells = _cells(answers)
    if cells > CACHE_ENTRY_MAX_CELLS:
        return
    with _cache_lock:
        old = _cache.pop(key, None)
        if old is not None:
            _cache_cells -= old[3]
        _cache[key] = (time.time(), answers, clock, cells)
        _cache_cells += cells
        if _cache_cells > CACHE_MAX_CELLS or len(_cache) > CACHE_MAX_ENTRIES:
            for old_key, entry in sorted(_cache.items(), key=lambda item: item[1][0]):
                if _cache_cells <= CACHE_MAX_CELLS and len(_cache) <= CACHE_MAX_ENTRIES:
                    break
                if old_key == key:
                    continue
                _cache.pop(old_key, None)
                _cache_cells -= entry[3]


def clear_cache() -> None:
    global _cache_cells
    with _cache_lock:
        _cache.clear()
        _cache_cells = 0


def cache_stats() -> dict:
    """Сколько серий и значений в кэше (тесты, диагностика)."""
    with _cache_lock:
        return {'entries': len(_cache), 'cells': _cache_cells, 'waiting': len(_inflight)}


@contextmanager
def _single_flight(key: str) -> Iterator[None]:
    """Одинаковые серии в параллельных вызовах идут в iiko один раз: второй ждёт первого
    и берёт его ответ из кэша. Замок удаляется, когда его никто не ждёт."""
    with _cache_lock:
        entry = _inflight.get(key)
        if entry is None:
            entry = [threading.Lock(), 0]
            _inflight[key] = entry
        entry[1] += 1
    entry[0].acquire()
    try:
        yield
    finally:
        entry[0].release()
        with _cache_lock:
            entry[1] -= 1
            if entry[1] == 0 and _inflight.get(key) is entry:
                del _inflight[key]


def _run_series(bodies: List[dict]) -> List[dict]:
    """Все тела серии — одной сессией iiko, параллельно (одинаковые тела — один раз)."""
    keys = [series_key([body]) for body in bodies]
    unique: Dict[str, dict] = {}
    for key, body in zip(keys, bodies):
        unique.setdefault(key, body)
    with open_session(parallel=len(unique)) as session:
        if len(unique) == 1:
            answers = {key: session.post_olap(body) for key, body in unique.items()}
        else:
            with ThreadPoolExecutor(max_workers=min(len(unique), MAX_PARALLEL)) as pool:
                futures = {key: pool.submit(session.post_olap, body)
                           for key, body in unique.items()}
                answers = {key: future.result() for key, future in futures.items()}
    return [{'data': answers[key].get('data') or [], 'summary': answers[key].get('summary') or []}
            for key in keys]


def fetch_olap(bodies: List[dict], use_cache: bool = True) -> List[dict]:
    """Выполнить серию тел OLAP-запросов; ответы — в том же порядке.

    Каждый элемент результата: {'data': [...], 'summary': [...], 'cached': bool,
    'fetched_at': 'ЧЧ:ММ'} — время, когда iiko посчитал ответ (для «Данные на …»).
    Серия — одна единица кэша: все ответы либо из одного прошлого похода в iiko, либо
    свежие (см. «КЭШ ОТВЕТОВ»). Одинаковые серии в параллельных вызовах ждут друг
    друга (single-flight).
    """
    key = series_key(bodies)
    if use_cache:
        hit = _cache_get(key)
        if hit is not None:
            return [dict(answer, cached=True, fetched_at=hit[1]) for answer in hit[0]]
    with _single_flight(key):
        if use_cache:
            hit = _cache_get(key)
            if hit is not None:
                return [dict(answer, cached=True, fetched_at=hit[1]) for answer in hit[0]]
        answers = _run_series(bodies)
        clock = msk_time.now().strftime('%H:%M')
        if use_cache:
            _cache_put(key, answers, clock)
    return [dict(answer, cached=False, fetched_at=clock) for answer in answers]
