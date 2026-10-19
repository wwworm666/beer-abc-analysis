"""Бот в работе: опрос Telegram, очередь разговоров, ответы, состояние для страницы.

## Запуск

app.py зовёт kultura_bot.start(app) в каждом gunicorn-воркере; работает бот ровно в
одном — том, что взял эксклюзивный flock на data/.kultura_bot.lock (как опрос open-check
бота, core/open_check_polling.py). Воркер умер или перезапустился (gunicorn
--max-requests) — ОС снимает лок, новый воркер подхватывает бота при старте. Вопрос,
ответ на который оборвал перезапуск, помечается interrupted, и чат получает «повторите
вопрос». KULTURA_BOT=0 — не запускать (тесты, локальные скрипты).

## Когда бот слушает Telegram

Только когда на странице «Доступ агентов» есть и токен бота, и ключ Anthropic, и бот не
на паузе. До этого он не забирает сообщения вовсе: если токеном пользуется другая
программа (старый бот), она продолжает работать. Ключи появились — бот снимает вебхук
(без сброса очереди) и начинает getUpdates. Telegram отвечает 409 «другой getUpdates» —
токеном пользуется ещё одна программа: состояние conflict на странице, пока её не
остановят.

## Сообщение

1. Только личка и группы (в группе — если к боту обратились: @имя, ответ на его
   сообщение, команда /…@имя). Свои сообщения и сообщения ботов — мимо.
2. /start <код> — привязка Telegram к администратору (kultura_bot/access.py).
3. Кто пишет: привязанный активный администратор, иначе — одна фраза «закрытый бот»
   (в личке, не чаще раза в час) и всё.
4. /new — новый диалог; /help — что умеет бот.
5. Вопрос (текст, фото, PDF) — в очередь чата: в одном чате вопросы идут по порядку,
   разных чатов одновременно — не больше settings.MAX_PARALLEL_DIALOGS.

## Ответ

Диалог чата (store.bot_dialogs) продолжается, если с прошлого вопроса прошло меньше
settings.DIALOG_IDLE_MINUTES и инструкции с инструментами те же (config.fingerprint);
иначе — новый, и ответ начинается с «Прошло много времени…» (или «Обновились
инструкции…»). Пока модель думает, в чате «печатает…». Графики модель отправляет сама
(common_chart_send) — они приходят раньше текста. Ошибка Anthropic — понятный текст в
чат (kultura_bot/claude.describe_error); дневной предел расхода — «лимит на сегодня».
"""
import base64
import logging
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from core import msk_time
from kultura_bot import access, agent, claude, config, credentials, settings, store, tools
from kultura_bot.telegram_io import TelegramIO

log = logging.getLogger('kultura-bot')

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_PATH = os.path.join(_BASE_DIR, 'data', '.kultura_bot.lock')

IDLE_RECHECK_S = 30              # нет ключей или пауза — проверять настройки раз в 30 с
CONFLICT_RETRY_S = 15            # токеном пользуется другая программа — пробовать снова
HEARTBEAT_S = 60                 # как часто обновлять «бот работает» на странице
INTERRUPTED_MAX_AGE_S = 1800     # сообщить об оборванном ответе, если вопрос моложе 30 минут
TYPING_EVERY_S = 4.5             # «печатает…» у Telegram гаснет через ~5 с
MAX_DIALOG_BYTES = 3_000_000     # история длиннее — новый диалог (каждый запрос шлёт её целиком)
PHOTO_MIME = 'image/jpeg'        # Telegram пережимает фото в JPEG
IMAGE_MAX_BYTES = 3_750_000      # Claude API: картинка до 5 МБ в base64 = 3,75 МБ файла
DOCUMENT_MIMES = {'application/pdf': 'document', 'image/jpeg': 'image', 'image/png': 'image',
                  'image/webp': 'image', 'image/gif': 'image'}

HELP_TEXT = ('Я помощник сети «Культура»: отвечаю по данным сайта — продажи и планы, остатки и заказы, '
             'краны, смены и зарплаты, контент-план и отзывы. Пишите вопрос обычными словами, можно '
             'приложить фото или PDF. Графики приходят с кнопкой «Открыть интерактивно».\n\n'
             '/new — начать новый диалог')
UNSUPPORTED_TEXT = 'Пока понимаю текст, фото и PDF. Напишите вопрос словами.'
INTERRUPTED_TEXT = 'Ответ на прошлый вопрос прервался: сервер перезапускался. Повторите вопрос, пожалуйста.'
RESTARTING_TEXT = 'Сервер перезапускается — повторите вопрос через минуту.'
FINGERPRINT_NOTICE = 'Обновились инструкции бота — начинаю новый диалог.'
LONG_DIALOG_NOTICE = 'Диалог стал слишком длинным — начинаю новый.'

_started = False
_start_lock = threading.Lock()
_lock_handle = None


def _disabled() -> bool:
    return os.environ.get('KULTURA_BOT', '1').strip().lower() in ('0', 'false', 'off', 'no')


def start(app) -> None:
    """Запустить бота в этом процессе, если лок свободен. Идемпотентно."""
    global _started, _lock_handle
    with _start_lock:
        if _started:
            return
        if _disabled():
            print('[KULTURA-BOT] KULTURA_BOT=0 — бот не запущен')
            return
        import portalocker
        os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
        handle = open(LOCK_PATH, 'a')
        try:
            portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.exceptions.BaseLockException:
            handle.close()
            return                       # бот уже работает в другом воркере
        try:
            service = Service(app)
            threading.Thread(target=service.run_forever, name='kultura-bot', daemon=True).start()
        except Exception:
            handle.close()               # лок отпускаем: бота подхватит другой воркер
            raise
        _lock_handle = handle
        _started = True


class Service:
    def __init__(self, app, io_factory=TelegramIO):
        self.app = app
        self.io_factory = io_factory
        self.tg: Optional[TelegramIO] = None
        self.token = ''
        self.bot_id: Optional[int] = None
        self.username = credentials.bot_username()
        self.offset: Optional[int] = None
        self.executor = ThreadPoolExecutor(max_workers=max(1, settings.MAX_PARALLEL_DIALOGS),
                                           thread_name_prefix='kultura-bot-chat')
        self.queues: Dict[str, deque] = {}
        self.busy: set = set()
        self.lock = threading.Lock()
        self._status_at = 0.0
        self._status_state = ''
        self._interrupted_checked = False

    # ---------------------------------------------------------------- состояние

    def _status(self, state: str, detail: str = '', force: bool = False) -> None:
        now = time.time()
        if not force and state == self._status_state and now - self._status_at < HEARTBEAT_S:
            return
        self._status_state, self._status_at = state, now
        store.set_status(state, detail, bot=self.username, pid=os.getpid())

    # ---------------------------------------------------------------- цикл опроса

    def run_forever(self) -> None:
        self._status('starting', 'бот запускается', force=True)
        while True:
            try:
                if not self.ready():
                    time.sleep(IDLE_RECHECK_S)
                    continue
                self.poll_once()
            except Exception as exc:  # noqa: BLE001 — поток опроса не должен умирать
                log.exception('[KULTURA-BOT] сбой цикла опроса')
                self._status('error', claude.scrub(f'{type(exc).__name__}: {exc}', self._secrets()), force=True)
                time.sleep(10)

    def _secrets(self) -> tuple:
        """Что не должно попасть в текст ошибки для чата и страницы."""
        try:
            return (self.token, credentials.bot_token(), credentials.anthropic_key(), credentials.proxy_url())
        except Exception:  # noqa: BLE001 — настройки недоступны: хотя бы токен из памяти
            return (self.token,)

    def ready(self) -> bool:
        """Есть токен и ключ, не пауза. Сменился токен — новый клиент Telegram."""
        token = credentials.bot_token()
        if not token:
            self._status('waiting', 'нет токена бота: вставьте его на этой странице')
            return False
        if not credentials.anthropic_key():
            self._status('waiting', 'нет ключа Anthropic API: вставьте его на этой странице')
            return False
        if credentials.paused():
            self._status('paused', 'бот на паузе')
            return False
        if token != self.token:
            self.token = token
            self.tg = self.io_factory(token)
            self.offset = None
            me = self.tg.get_me() or {}
            result = me.get('result') or {}
            self.bot_id = result.get('id')
            self.username = result.get('username') or credentials.bot_username()
            self.tg.delete_webhook()
            self.tg.set_commands()
            self._status('running', 'бот слушает Telegram', force=True)
        if not self._interrupted_checked:
            self._interrupted_checked = True
            chats = {job['chat_id'] for job in store.take_interrupted_jobs(INTERRUPTED_MAX_AGE_S)}
            for chat_id in sorted(chats):
                self.tg.send_plain(chat_id, INTERRUPTED_TEXT)
        return True

    def poll_once(self) -> None:
        data = self.tg.get_updates(self.offset)
        if data is None:
            self._status('error', 'нет связи с Telegram — повторяю')
            time.sleep(5)
            return
        if not data.get('ok'):
            code, description = data.get('error_code'), str(data.get('description') or '')
            if code == 409 and 'webhook' in description.lower():
                self.tg.delete_webhook()
            elif code == 409:
                self._status('conflict', 'токеном бота пользуется другая программа (старый бот?) — остановите её; '
                                         'пока она работает, Telegram отдаёт сообщения то ей, то сюда', force=True)
                time.sleep(CONFLICT_RETRY_S)
            elif code == 401:
                self._status('error', 'Telegram не принимает токен бота — вставьте новый на этой странице', force=True)
                time.sleep(IDLE_RECHECK_S)
            else:
                self._status('error', f'Telegram: {description or code}')
                time.sleep(5)
            return
        self._status('running', 'бот слушает Telegram')
        for update in data.get('result') or []:
            self.offset = update['update_id'] + 1
            try:
                self.handle_update(update)
            except Exception:  # noqa: BLE001 — одно кривое сообщение не останавливает бота
                log.exception('[KULTURA-BOT] сообщение %s не обработано', update.get('update_id'))

    # ---------------------------------------------------------------- сообщение

    def _addressed(self, message: Dict[str, Any], text: str) -> bool:
        """В группе: к боту обратились — @имя, ответ на его сообщение, команда /…@имя."""
        name = '@' + (self.username or '').lower()
        if name != '@' and name in text.lower():
            return True
        reply = message.get('reply_to_message') or {}
        author = reply.get('from') or {}
        if self.bot_id:
            return author.get('id') == self.bot_id
        # getMe при запуске не ответил — узнаём бота по имени
        return bool(author.get('is_bot') and name != '@' and '@' + (author.get('username') or '').lower() == name)

    def _strip_mention(self, text: str) -> str:
        if not self.username:
            return text
        import re
        return re.sub(r'@' + re.escape(self.username) + r'\b', '', text, flags=re.I).strip()

    @staticmethod
    def _command(text: str):
        """('/new@bot аргументы') -> ('new', 'аргументы'); не команда -> (None, текст)."""
        if not text.startswith('/'):
            return None, text
        head, _, rest = text.partition(' ')
        return head[1:].split('@', 1)[0].lower(), rest.strip()

    def handle_update(self, update: Dict[str, Any]) -> None:
        message = update.get('message')
        if not message:
            return
        chat = message.get('chat') or {}
        chat_type = chat.get('type')
        chat_id = str(chat.get('id'))
        author = message.get('from') or {}
        if author.get('is_bot') or not author.get('id'):
            return
        tg_user_id = str(author['id'])
        text = (message.get('text') or message.get('caption') or '').strip()
        if chat_type in ('group', 'supergroup'):
            if not settings.ANSWER_IN_GROUPS or not self._addressed(message, text):
                return
            text = self._strip_mention(text)
        elif chat_type != 'private':
            return
        command, rest = self._command(text)
        tg_name = ' '.join(filter(None, [author.get('first_name'), author.get('last_name')])) or \
            author.get('username') or ''

        if command == 'start':
            if rest and chat_type == 'private':
                answer = access.link_by_code(rest, tg_user_id, tg_name)
                self.tg.send_plain(chat_id, answer['text'])
                return
            if access.actor_for(tg_user_id):
                self.tg.send_plain(chat_id, HELP_TEXT)
            elif chat_type == 'private':
                self.tg.send_plain(chat_id, access.refusal_text())
            return
        actor = access.actor_for(tg_user_id)
        if actor is None:
            if chat_type == 'private' and access.refusal_due(tg_user_id):
                self.tg.send_plain(chat_id, access.refusal_text())
            return
        if command == 'new':
            store.delete_dialog(chat_id)
            self.tg.send_plain(chat_id, 'Начинаю новый диалог.')
            return
        if command == 'help':
            self.tg.send_plain(chat_id, HELP_TEXT)
            return
        has_file = bool(message.get('photo') or (message.get('document') or {}).get('mime_type') in DOCUMENT_MIMES)
        if not text and not has_file:
            self.tg.send_plain(chat_id, UNSUPPORTED_TEXT)
            return
        self.enqueue(chat_id, {'message': message, 'actor': actor, 'text': text, 'chat_type': chat_type})

    # ---------------------------------------------------------------- очередь

    def enqueue(self, chat_id: str, job: Dict[str, Any]) -> None:
        with self.lock:
            self.queues.setdefault(chat_id, deque()).append(job)
            if chat_id in self.busy:
                return
            self.busy.add(chat_id)
        try:
            self.executor.submit(self._drain, chat_id)
        except RuntimeError:
            # Воркер завершается (выкладка, --max-requests): начатые ответы Python доводит до
            # конца, новых не берёт. Вопрос не теряем молча — просим повторить.
            with self.lock:
                self.busy.discard(chat_id)
                self.queues.pop(chat_id, None)
            self.tg.send_plain(chat_id, RESTARTING_TEXT)

    def _drain(self, chat_id: str) -> None:
        while True:
            with self.lock:
                queue = self.queues.get(chat_id)
                if not queue:
                    self.busy.discard(chat_id)
                    self.queues.pop(chat_id, None)
                    return
                job = queue.popleft()
            try:
                self.answer(chat_id, job)
            except Exception:  # noqa: BLE001
                log.exception('[KULTURA-BOT] ответ в чат %s упал', chat_id)

    # ---------------------------------------------------------------- ответ

    def _typing(self, chat_id: str, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.tg.typing(chat_id)
            except Exception:  # noqa: BLE001
                pass
            stop.wait(TYPING_EVERY_S)

    @staticmethod
    def _limit(kind: str) -> int:
        """Предел файла: settings.INPUT_FILE_MAX_BYTES, картинке — не больше предела Claude API."""
        limit = settings.INPUT_FILE_MAX_BYTES
        return min(limit, IMAGE_MAX_BYTES) if kind == 'image' else limit

    def _files(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Фото и PDF из сообщения -> блоки image/document для Claude (base64)."""
        found = []
        if message.get('photo'):
            biggest = max(message['photo'], key=lambda p: p.get('file_size') or 0)
            found.append(('image', PHOTO_MIME, biggest['file_id']))
        document = message.get('document') or {}
        kind = DOCUMENT_MIMES.get(document.get('mime_type'))
        if kind:
            found.append((kind, document['mime_type'], document['file_id']))
        blocks: List[Dict[str, Any]] = []
        for kind, mime, file_id in found:
            data = self.tg.download(file_id, self._limit(kind))
            if data:
                blocks.append({'type': kind, 'source': {'type': 'base64', 'media_type': mime,
                                                        'data': base64.b64encode(data).decode('ascii')}})
        return blocks

    @staticmethod
    def header(actor: Dict[str, Any]) -> str:
        now = msk_time.now()
        return (f'[{now.strftime("%d.%m.%Y %H:%M")} МСК · рабочий день бара {msk_time.business_today().isoformat()} · '
                f'пишет {actor["display_name"]} ({actor["login"]})]')

    def answer(self, chat_id: str, job: Dict[str, Any]) -> None:
        message, actor = job['message'], job['actor']
        reply_to = message.get('message_id') if job['chat_type'] != 'private' else None
        job_id = store.start_job(chat_id, actor['tg_user_id'])
        stop = threading.Event()
        threading.Thread(target=self._typing, args=(chat_id, stop), daemon=True).start()
        status, error = 'done', ''
        try:
            header = self.header(actor)
            user_content = [{'type': 'text', 'text': f'{header}\n{job["text"] or "(без текста)"}'}]
            files = self._files(message)
            if (message.get('photo') or message.get('document')) and not files:
                self.tg.send_plain(chat_id, f'Файл не скачался или слишком большой (картинка — до '
                                            f'{self._limit("image") / 1e6:.1f} МБ, PDF — до '
                                            f'{self._limit("document") / 1e6:.0f} МБ) — отвечаю без него.',
                                   reply_to=reply_to)
            user_content += files

            system_text = config.bot_system_text()
            agent_names = list(config.load_agents())
            tool_list = tools.tool_defs(agent_names=agent_names)
            fingerprint = config.fingerprint(system_text, tool_list)
            dialog = store.get_dialog(chat_id)
            notice = ''
            if dialog is not None:
                idle = time.time() - dialog['last_ts'] > settings.DIALOG_IDLE_MINUTES * 60
                if idle:
                    notice, dialog = settings.NEW_DIALOG_NOTICE, None
                elif dialog['fingerprint'] != fingerprint:
                    notice, dialog = FINGERPRINT_NOTICE, None
                elif len(str(dialog['messages'])) > MAX_DIALOG_BYTES:
                    notice, dialog = LONG_DIALOG_NOTICE, None
            history = dialog['messages'] if dialog else []
            started_at = dialog['started_at'] if dialog else msk_time.now().isoformat(timespec='seconds')
            turns = dialog['turns'] if dialog else 0

            client = claude.client_for(credentials.anthropic_key(), credentials.proxy_url())
            ctx = tools.ToolContext(app=self.app, principal=access.principal_for(actor), chat_id=chat_id)
            ctx.run_agent = lambda name, task: agent.run_agent(client, name, task, parent=ctx, header=header)
            result = agent.run_turn(client, system_text=system_text, tool_list=tool_list, history=history,
                                    user_content=user_content, ctx=ctx)
            store.save_dialog(chat_id, fingerprint, started_at, result.messages, turns + 1)
            text = result.text or ('Готово: график выше.' if ctx.charts_sent else 'Готово.')
            if notice:
                text = f'*{notice}*\n\n{text}'
            self.tg.send_markdown(chat_id, text, reply_to=reply_to)
        except agent.BudgetExceeded as exc:
            status, error = 'error', 'budget'
            self.tg.send_plain(chat_id, str(exc), reply_to=reply_to)
        except Exception as exc:  # noqa: BLE001 — любая беда -> понятный ответ в чат
            kind, text = claude.describe_error(exc, secrets=self._secrets())
            status, error = 'error', f'{kind}: {text}'
            log.warning('[KULTURA-BOT] ответ не получился (%s): %s', kind, text)
            if kind == 'bad_request':
                store.delete_dialog(chat_id)             # битая история не должна ломать следующие вопросы
                text += ' Диалог начат заново — повторите вопрос.'
            elif kind == 'other':
                log.exception('[KULTURA-BOT] сбой ответа')
                text = f'Не получилось ответить: {text}'
            self.tg.send_plain(chat_id, text, reply_to=reply_to)
            self._status('error' if kind in ('auth', 'denied', 'billing', 'offline') else 'running',
                         text if kind in ('auth', 'denied', 'billing', 'offline') else 'бот слушает Telegram',
                         force=True)
        finally:
            stop.set()
            store.finish_job(job_id, status, error)


def status_view() -> Dict[str, Any]:
    """Состояние бота для страницы: что делает, свежесть, расход, привязки."""
    status = store.get_status()
    age = time.time() - float(status.get('at_ts') or 0)
    stale = status.get('state') in ('running', 'conflict') and age > 3 * 60
    return {'status': dict(status, stale=stale), 'usage': store.usage_summary(30),
            'budget_usd': settings.DAILY_BUDGET_USD, 'model': settings.MODEL, 'effort': settings.EFFORT,
            'links': access.links_view(), 'agents': [{'name': a.name, 'title': a.title}
                                                     for a in config.load_agents().values()]}
