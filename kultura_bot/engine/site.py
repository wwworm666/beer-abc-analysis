"""Связь сервера бота с сайтом beerkultura.ru: API бота и MCP.

Ключ сервера бота (переменная KULTURA_BOT_KEY на сервере) — статический MCP-токен,
который выпускает кнопка «Команда установки» на странице «Доступ агентов». Он открывает:

- MCP (/mcp и /mcp/<раздел>) — те же инструменты, что у ИИ-агентов владельца, тот же
  мост к маршрутам сайта, те же лимиты; в журнале вызовов — клиент «Бот @MCPkulturabot —
  сервер в Амстердаме»;
- API бота (/api/bot/*, routes/bot_api.py) — только этому токену: настройки с секретами
  (токен Telegram, ключ Anthropic, пауза), привязки Telegram к администраторам, отчёт о
  работе для страницы, записки «Как считается» к ответам.

MCP — «старой эпохи» протокола (initialize, tools/list, tools/call: JSON-RPC в теле POST,
ответ — один JSON, сессий нет): её сайт поддерживает для всех клиентов
(core/mcp/protocol.py).

Ключ в журнал не попадает: он только в заголовке Authorization, а в тексты ошибок идут
лишь вид ошибки и код ответа.
"""
import itertools
import logging
import threading
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import requests

log = logging.getLogger('kultura-bot')

MCP_VERSION = '2025-11-25'       # последняя версия «старой эпохи» MCP, её знает сайт
CONNECT_TIMEOUT_S = 10
API_TIMEOUT_S = 30
TOOL_TIMEOUT_S = 240             # тяжёлые инструменты (живой запрос в iiko) идут минуту-две
CLIENT_INFO = {'name': 'kultura-bot', 'version': '2'}


class SiteError(Exception):
    """Сайт не ответил как надо. kind: offline | auth | http | protocol; text — для человека."""

    def __init__(self, kind: str, text: str):
        super().__init__(text)
        self.kind = kind
        self.text = text


class Site:
    def __init__(self, base_url: str, key: str, session_factory: Optional[Callable[[], requests.Session]] = None):
        self.base_url = (base_url or '').rstrip('/')
        self.key = key
        self._ids = itertools.count(1)
        self._local = threading.local()      # requests.Session — своя у каждого потока
        self._session_factory = session_factory or requests.Session    # тесты подставляют сайт в процессе

    def _session(self) -> requests.Session:
        session = getattr(self._local, 'session', None)
        if session is None:
            session = self._local.session = self._session_factory()
        return session

    def _request(self, method: str, path: str, *, body: Optional[Dict[str, Any]] = None,
                 timeout: float = API_TIMEOUT_S, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        sent = {'Authorization': f'Bearer {self.key}', 'Accept': 'application/json'}
        sent.update(headers or {})
        try:
            resp = self._session().request(method, self.base_url + path, json=body, headers=sent,
                                           timeout=(CONNECT_TIMEOUT_S, timeout))
        except requests.RequestException as exc:
            raise SiteError('offline', f'Сайт {self.base_url} не отвечает ({type(exc).__name__}).') from None
        if resp.status_code in (401, 403):
            raise SiteError('auth', 'Сайт не принял ключ сервера бота: на странице «Доступ агентов» выпустите '
                                    'новую команду установки и выполните её на сервере.')
        try:
            data = resp.json()
        except ValueError:
            data = None
        if resp.status_code >= 400 or not isinstance(data, dict):
            detail = data.get('error') if isinstance(data, dict) else ''
            raise SiteError('http', f'Сайт ответил {resp.status_code} на {path}: {detail or "ответ не JSON"}')
        return data

    # ---------------------------------------------------------------- API бота

    def config(self) -> Dict[str, Any]:
        """Настройки со страницы: токен Telegram, имя бота, ключ Anthropic, пауза."""
        return self._request('GET', '/api/bot/config')

    def link(self, code: str, tg_user_id: str, tg_name: str) -> Dict[str, Any]:
        """Привязать Telegram по коду из /start: {'ok': bool, 'text': ответ человеку}."""
        return self._request('POST', '/api/bot/link', body={'code': code, 'tg_user_id': str(tg_user_id),
                                                            'tg_name': tg_name})

    def actor(self, tg_user_id: str) -> Optional[Dict[str, Any]]:
        """Кто пишет: привязанный активный администратор или None."""
        return self._request('GET', f'/api/bot/actor/{int(tg_user_id)}').get('actor')

    def report(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Отчёт для страницы: состояние и расход с прошлого отчёта."""
        return self._request('POST', '/api/bot/report', body=payload)

    def note(self, chat_id: str, text: str, title: str = '') -> str:
        """Записка «Как считается» к ответу: сайт хранит её 90 дней. Вернуть id (rep_…)."""
        body = {'chat_id': str(chat_id), 'text': text}
        if title:
            body['title'] = title
        note_id = self._request('POST', '/api/bot/note', body=body).get('id')
        if not isinstance(note_id, str) or not note_id:
            raise SiteError('protocol', 'Сайт не вернул id записки «Как считается»')
        return note_id

    def replied(self, chat_id: str, message_id: int) -> Optional[Dict[str, Any]]:
        """Что было в сообщении бота, на которое человек ответил в Telegram: отчёт или график этого
        чата текстом для модели {kind, id, title, text}; None — не отчёт и не график (или срок вышел)."""
        query = urlencode({'chat_id': str(chat_id), 'message_id': int(message_id)})
        found = self._request('GET', f'/api/bot/replied?{query}').get('found')
        return found if isinstance(found, dict) and found.get('text') else None

    # ---------------------------------------------------------------- MCP

    def mcp(self, method: str, params: Optional[Dict[str, Any]] = None, connector: str = '/mcp',
            timeout: float = API_TIMEOUT_S) -> Dict[str, Any]:
        body = {'jsonrpc': '2.0', 'id': next(self._ids), 'method': method, 'params': params or {}}
        data = self._request('POST', connector, body=body, timeout=timeout,
                             headers={'Content-Type': 'application/json', 'MCP-Protocol-Version': MCP_VERSION})
        if data.get('error') is not None:
            error = data['error'] if isinstance(data['error'], dict) else {'message': str(data['error'])}
            raise SiteError('protocol', f'MCP {method}: {error.get("message") or error}')
        result = data.get('result')
        if not isinstance(result, dict):
            raise SiteError('protocol', f'MCP {method}: в ответе нет result')
        return result

    def instructions(self, connector: str = '/mcp') -> str:
        """Правила сервиса для коннектора (instructions из initialize)."""
        result = self.mcp('initialize', {'protocolVersion': MCP_VERSION, 'capabilities': {},
                                         'clientInfo': CLIENT_INFO}, connector)
        return str(result.get('instructions') or '')

    def tools(self, connector: str = '/mcp') -> List[Dict[str, Any]]:
        """Инструменты коннектора: [{name, title, description, inputSchema, annotations}]."""
        tools = self.mcp('tools/list', {}, connector).get('tools')
        return [t for t in tools if isinstance(t, dict) and t.get('name')] if isinstance(tools, list) else []

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Вызвать инструмент через полный коннектор: {'content': [...], 'isError': bool}."""
        return self.mcp('tools/call', {'name': name, 'arguments': arguments}, '/mcp', timeout=TOOL_TIMEOUT_S)
