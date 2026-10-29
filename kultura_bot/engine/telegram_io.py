"""Telegram для бота: приём (getUpdates), ответы, «печатает…», файлы из сообщений.

Сервер бота в Амстердаме ходит к api.telegram.org напрямую (обход блокировок, как у ботов
сайта в России, ему не нужен). Апдейты бот забирает сам (long polling): вебхук потребовал
бы открытого порта на сервере.

Токен в журнал не попадает: он есть в адресе запроса, поэтому в журнал пишутся только
метод и вид ошибки, а не текст исключения requests (в нём адрес целиком).

Ответ модели (Markdown) режется на части и переводится в HTML Telegram (formatting.py);
Telegram не принял разметку или часть вышла длиннее его предела (4096) — она уходит
простым текстом кусками. Telegram просит подождать (429) — бот ждёт retry_after (не
дольше 30 с) и шлёт ещё раз.
"""
import logging
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from kultura_bot.engine import formatting

log = logging.getLogger('kultura-bot')

API = 'https://api.telegram.org'
POLL_TIMEOUT = 25                    # long poll getUpdates, с
CONNECT_TIMEOUT_S = 10
FILE_TIMEOUT_S = 60
RETRY_AFTER_MAX_S = 30               # Telegram просит подождать (429) — ждём не дольше
HTTP_TIMEOUT = POLL_TIMEOUT + 10
ALLOWED_UPDATES = ['message']
COMMANDS = [
    {'command': 'report', 'description': 'Отчёт: полный разбор на странице'},
    {'command': 'new', 'description': 'Начать новый диалог'},
    {'command': 'help', 'description': 'Что умеет бот'},
]


class TelegramIO:
    def __init__(self, token: str):
        self.token = token
        self._local = threading.local()      # requests.Session — своя у каждого потока

    def _session(self) -> requests.Session:
        session = getattr(self._local, 'session', None)
        if session is None:
            session = self._local.session = requests.Session()
        return session

    def call(self, method: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 8):
        """Метод Bot API: ответ Telegram (dict) или None — нет связи."""
        try:
            resp = self._session().post(f'{API}/bot{self.token}/{method}', json=payload or {},
                                        timeout=(CONNECT_TIMEOUT_S, timeout))
        except requests.RequestException as exc:
            log.warning('[BOT] Telegram %s: нет связи (%s)', method, type(exc).__name__)
            return None
        try:
            data = resp.json()
        except ValueError:
            return {'ok': False, 'error_code': resp.status_code, 'description': f'HTTP {resp.status_code}'}
        return data if isinstance(data, dict) else {'ok': False, 'description': 'ответ не объект'}

    # ---------------------------------------------------------------- служебное

    def get_me(self) -> Optional[Dict[str, Any]]:
        return self.call('getMe')

    def delete_webhook(self) -> Optional[Dict[str, Any]]:
        # Без drop_pending_updates: накопленные вопросы бот прочтёт.
        return self.call('deleteWebhook', {'drop_pending_updates': False})

    def set_commands(self) -> None:
        self.call('setMyCommands', {'commands': COMMANDS})

    def get_updates(self, offset: Optional[int]) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {'timeout': POLL_TIMEOUT, 'allowed_updates': ALLOWED_UPDATES}
        if offset is not None:
            payload['offset'] = offset
        return self.call('getUpdates', payload, timeout=HTTP_TIMEOUT)

    def typing(self, chat_id: str) -> None:
        self.call('sendChatAction', {'chat_id': chat_id, 'action': 'typing'}, timeout=5)

    # ---------------------------------------------------------------- ответы

    def _send(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """sendMessage; Telegram просит подождать (429) — ждём (не дольше 30 с) и шлём ещё раз."""
        data = self.call('sendMessage', payload, timeout=20)
        if data and not data.get('ok') and data.get('error_code') == 429:
            wait = (data.get('parameters') or {}).get('retry_after') or 1
            time.sleep(min(float(wait), RETRY_AFTER_MAX_S))
            data = self.call('sendMessage', payload, timeout=20)
        return data

    def send_html(self, chat_id: str, text_html: str, *, fallback_text: str = '',
                  reply_to: Optional[int] = None,
                  reply_markup: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """Одно сообщение HTML. Разметку не приняли или текст длиннее предела Telegram — простым
        текстом, кусками (кнопки — у первого куска). message_id первого ушедшего или None."""
        payload: Dict[str, Any] = {'chat_id': chat_id, 'text': text_html, 'parse_mode': 'HTML',
                                   'link_preview_options': {'is_disabled': True}}
        if reply_to:
            payload['reply_parameters'] = {'message_id': reply_to, 'allow_sending_without_reply': True}
        if reply_markup:
            payload['reply_markup'] = reply_markup
        data = self._send(payload) if len(text_html) <= formatting.TELEGRAM_MAX else \
            {'ok': False, 'description': 'message is too long'}
        if data and data.get('ok'):
            return (data.get('result') or {}).get('message_id')
        description = str((data or {}).get('description') or '').lower()
        if data and ('parse' in description or 'too long' in description):
            payload.pop('parse_mode', None)
            text = fallback_text or text_html
            first = None
            for start in range(0, len(text), formatting.TELEGRAM_MAX):
                payload['text'] = text[start:start + formatting.TELEGRAM_MAX]
                data = self._send(payload)
                if data and data.get('ok') and first is None:
                    first = (data.get('result') or {}).get('message_id')
                payload.pop('reply_parameters', None)          # ответом — только первый кусок
                payload.pop('reply_markup', None)              # кнопки — только у первого
            if first is not None:
                return first
        log.warning('[BOT] сообщение не ушло в чат %s: %s', chat_id, (data or {}).get('description'))
        return None

    def send_markdown(self, chat_id: str, markdown: str, *, reply_to: Optional[int] = None,
                      reply_markup: Optional[Dict[str, Any]] = None) -> List[int]:
        """Ответ модели: части по formatting.LIMIT, каждая — HTML; кнопки (reply_markup) — под
        последней частью. Вернуть message_id отправленных."""
        sent: List[int] = []
        parts = formatting.split(markdown)
        for n, part in enumerate(parts):
            message_id = self.send_html(chat_id, formatting.to_html(part), fallback_text=formatting.plain(part),
                                        reply_to=reply_to if n == 0 else None,
                                        reply_markup=reply_markup if n == len(parts) - 1 else None)
            if message_id is not None:
                sent.append(message_id)
        return sent

    def send_plain(self, chat_id: str, text: str, *, reply_to: Optional[int] = None) -> Optional[int]:
        import html
        return self.send_html(chat_id, html.escape(text, quote=False), fallback_text=text, reply_to=reply_to)

    # ---------------------------------------------------------------- прогресс (engine/progress.py)

    def send_status(self, chat_id: str, text_html: str, *, reply_to: Optional[int] = None) -> Optional[int]:
        """Сообщение о прогрессе (HTML). message_id или None."""
        return self.send_html(chat_id, text_html, reply_to=reply_to)

    def edit_status(self, chat_id: str, message_id: int, text_html: str) -> bool:
        """Поправить сообщение о прогрессе. Telegram отказал (в том числе «не изменилось») — False."""
        data = self.call('editMessageText', {'chat_id': chat_id, 'message_id': message_id, 'text': text_html,
                                             'parse_mode': 'HTML', 'link_preview_options': {'is_disabled': True}},
                         timeout=8)
        return bool(data and data.get('ok'))

    def delete_message(self, chat_id: str, message_id: int) -> bool:
        data = self.call('deleteMessage', {'chat_id': chat_id, 'message_id': message_id}, timeout=8)
        return bool(data and data.get('ok'))

    # ---------------------------------------------------------------- файлы

    def download(self, file_id: str, max_bytes: int) -> Optional[bytes]:
        """Файл из сообщения (фото, документ): getFile + скачивание. None — не вышло или велик.

        Размер проверяется по мере чтения: больше max_bytes — None, файл целиком в память
        не берётся."""
        info = self.call('getFile', {'file_id': file_id}, timeout=15)
        if not info or not info.get('ok'):
            return None
        result = info.get('result') or {}
        size = result.get('file_size') or 0
        path = str(result.get('file_path') or '').lstrip('/')
        if not path or (size and size > max_bytes):
            return None
        try:
            with self._session().get(f'{API}/file/bot{self.token}/{path}', stream=True,
                                     timeout=(CONNECT_TIMEOUT_S, FILE_TIMEOUT_S)) as resp:
                if resp.status_code != 200:
                    return None
                data = bytearray()
                for chunk in resp.iter_content(64 * 1024):
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        return None
                return bytes(data)
        except requests.RequestException as exc:
            log.warning('[BOT] файл из сообщения не скачался (%s)', type(exc).__name__)
            return None
