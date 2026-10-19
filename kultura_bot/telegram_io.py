"""Telegram для бота: приём (getUpdates), ответы, «печатает…», файлы из сообщений.

Транспорт — core/open_check_telegram (api_call, download_file): тот же путь с обходом
блокировок, что у остальных ботов сайта (основной адрес, при сбое — запасные IP с SNI).
Вебхук сюда не годится: входящие соединения от Telegram до сервера режет ТСПУ
(docs/open-check-bot.md, «Блокировки»), поэтому апдейты бот забирает сам.

Ответ модели (Markdown) режется на части и переводится в HTML Telegram
(kultura_bot/formatting.py); Telegram не принял разметку — часть уходит простым текстом.
"""
import logging
from typing import Any, Dict, List, Optional

from kultura_bot import formatting

log = logging.getLogger('kultura-bot')

POLL_TIMEOUT = 25                    # long poll getUpdates, с
HTTP_TIMEOUT = POLL_TIMEOUT + 10
ALLOWED_UPDATES = ['message']
COMMANDS = [
    {'command': 'new', 'description': 'Начать новый диалог'},
    {'command': 'help', 'description': 'Что умеет бот'},
]


class TelegramIO:
    def __init__(self, token: str):
        self.token = token

    def call(self, method: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 8):
        from core.open_check_telegram import api_call
        return api_call(method, payload or {}, timeout=timeout, token=self.token)

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

    def send_html(self, chat_id: str, text_html: str, *, fallback_text: str = '',
                  reply_to: Optional[int] = None) -> Optional[int]:
        """Одно сообщение HTML; разметку не приняли — простым текстом. message_id или None."""
        payload: Dict[str, Any] = {'chat_id': chat_id, 'text': text_html, 'parse_mode': 'HTML',
                                   'link_preview_options': {'is_disabled': True}}
        if reply_to:
            payload['reply_parameters'] = {'message_id': reply_to, 'allow_sending_without_reply': True}
        data = self.call('sendMessage', payload, timeout=20)
        if data and data.get('ok'):
            return (data.get('result') or {}).get('message_id')
        if data and 'parse' in str(data.get('description') or '').lower():
            payload.pop('parse_mode', None)
            payload['text'] = fallback_text or text_html
            data = self.call('sendMessage', payload, timeout=20)
            if data and data.get('ok'):
                return (data.get('result') or {}).get('message_id')
        log.warning('[BOT] сообщение не ушло в чат %s: %s', chat_id, (data or {}).get('description'))
        return None

    def send_markdown(self, chat_id: str, markdown: str, *, reply_to: Optional[int] = None) -> List[int]:
        """Ответ модели: части по formatting.LIMIT, каждая — HTML. Вернуть message_id отправленных."""
        sent: List[int] = []
        for n, part in enumerate(formatting.split(markdown)):
            message_id = self.send_html(chat_id, formatting.to_html(part), fallback_text=formatting.plain(part),
                                        reply_to=reply_to if n == 0 else None)
            if message_id is not None:
                sent.append(message_id)
        return sent

    def send_plain(self, chat_id: str, text: str, *, reply_to: Optional[int] = None) -> Optional[int]:
        import html
        return self.send_html(chat_id, html.escape(text, quote=False), fallback_text=text, reply_to=reply_to)

    # ---------------------------------------------------------------- файлы

    def download(self, file_id: str, max_bytes: int) -> Optional[bytes]:
        """Файл из сообщения (фото, документ): getFile + скачивание. None — не вышло или велик."""
        from core.open_check_telegram import download_file
        info = self.call('getFile', {'file_id': file_id}, timeout=15)
        if not info or not info.get('ok'):
            return None
        result = info.get('result') or {}
        size = result.get('file_size') or 0
        if size and size > max_bytes:
            return None
        return download_file(result.get('file_path') or '', token=self.token, max_bytes=max_bytes)
