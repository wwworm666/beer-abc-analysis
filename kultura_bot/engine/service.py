"""Сервер бота в работе: настройки с сайта, опрос Telegram, очередь разговоров, ответы, отчёт.

## Запуск

python -m kultura_bot (main.py) на сервере в Амстердаме — systemd-служба kultura-bot
(kultura_bot/deploy/). Один процесс: опрос Telegram — в основном потоке, ответы — в пуле
потоков (settings.MAX_PARALLEL_DIALOGS). Остановка (выкладка, перезагрузка): начатые
ответы доводятся до конца, ждавшие очереди остаются в базе — после запуска их чаты
получают «повторите вопрос».

## Настройки — с сайта

Раз в CONFIG_EVERY_S сервер спрашивает сайт (GET /api/bot/config): токен Telegram, ключ
Anthropic, пауза, имя бота. Владелец меняет их на странице «Доступ агентов» — сервер
подхватывает без перезапуска. Сменился ключ Anthropic — сервер сразу проверяет его
(бесплатный список моделей), ошибка видна на странице. Сайт отверг ключ сервера (новая
команда установки или ключ отозван) — бот замолкает.

## Когда бот слушает Telegram

Есть токен и ключ, не пауза. До этого сообщения не забираются: если токеном пользуется
другая программа (старый бот), она работает как работала. Ключи появились — бот снимает
вебхук (без сброса очереди), ставит команды /new и /help и забирает сообщения сам
(getUpdates). Telegram отвечает 409 — токеном пользуется ещё одна программа: состояние
conflict на странице, пока её не остановят.

## Сообщение

1. Только личка и группы (в группе — если к боту обратились: @имя, ответ на его
   сообщение, команда /…@имя). Свои сообщения и сообщения ботов — мимо.
2. /start <код> — привязка Telegram к администратору сайта (сайт: POST /api/bot/link).
3. Кто пишет — спрашиваем сайт (GET /api/bot/actor/<id>, ответ помнится ACTOR_CACHE_S):
   привязанный активный администратор, иначе одна фраза «закрытый бот» (в личке, не
   чаще раза в REFUSAL_EVERY_S) и всё.
4. /new — новый диалог (в очереди чата); /help — что умеет бот; /report <вопрос> или
   сообщение со слова из settings.REPORT_WORDS («отчёт: …», «исследуй …») — режим отчёта.
5. Вопрос (текст, фото, PDF) — в очередь чата: в одном чате по порядку, разных чатов
   одновременно — не больше settings.MAX_PARALLEL_DIALOGS. Вопрос записан сразу
   (queued): остановка сервера не потеряет его молча.

## Ответ

Права проверяются ещё раз (привязку могли снять, пока вопрос ждал). Диалог чата
продолжается, если с прошлого вопроса прошло меньше settings.DIALOG_IDLE_MINUTES,
инструкции и инструменты те же (отпечаток каталога) и история короче settings.DIALOG_MAX_CHARS;
иначе — новый, с пометкой в начале ответа. Пока модель думает, в чате «печатает…».
Графики модель отправляет сама (common_chart_send — их рисует и шлёт сайт). Ошибка
Anthropic — понятный текст в чат (claude.describe_error); дневной предел — «лимит на
сегодня».

## Вид ответа (решения владельца 2026-10-24, docs/kultura-bot.md «Как выглядит ответ»)

- обычный вопрос — один пузырь: текст модели или подпись к графику (её пишет модель в
  common_chart_send). Пустой текст после графика или отчёта — второго сообщения нет
  (только строка цены, пока она включена: settings.SHOW_COST);
- «Как считается» — блок «>> Как считается» в конце ответа (formatting.split_how): сервер
  вырезает его, сохраняет запиской на сайте (POST /api/bot/note) и ставит ссылку в конец
  ответа или кнопку под ним (kultura_bot/links.py). Сайт не ответил — блок остаётся
  свёрнутой цитатой;
- режим отчёта (/report, «отчёт: …») — предел settings.REPORT_BUDGET_USD и
  REPORT_MAX_TOOL_ROUNDS шагов, в служебной строке «режим: отчёт»: модель собирает страницу
  common_report_send, в чат уходит выжимка с кнопкой «Открыть отчёт».

## Отчёт сайту

Состояние (starting, waiting, paused, running, conflict, error, stopped, последняя ошибка
Claude) и расход с прошлого отчёта уходят сайту при изменении и раз в HEARTBEAT_S
(POST /api/bot/report). Страница считает сервер «не отвечающим», если отчёта нет дольше
трёх минут. Отчёт не дошёл — расход копится до следующего.
"""
import base64
import dataclasses
import logging
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any, Dict, List, Optional

from kultura_bot import links, settings
from kultura_bot.engine import agent, claude, config, formatting, report_text, tools
from kultura_bot.engine.site import SiteError
from kultura_bot.engine.store import msk_day, msk_now
from kultura_bot.engine.telegram_io import TelegramIO

log = logging.getLogger('kultura-bot')

CONFIG_EVERY_S = 30              # как часто спрашивать сайт о токене, ключе и паузе
IDLE_RECHECK_S = 30              # нет ключей или пауза — проверять настройки раз в 30 с
CONFLICT_RETRY_S = 15            # токеном пользуется другая программа — пробовать снова
HEARTBEAT_S = 60                 # отчёт сайту не реже раза в минуту
ACTOR_CACHE_S = 60               # ответ сайта «кто пишет» помнится минуту
REFUSAL_EVERY_S = 3600           # незнакомцу «закрытый бот» — не чаще раза в час
INTERRUPTED_MAX_AGE_S = 1800     # сообщить об оборванном ответе, если вопрос моложе 30 минут
TYPING_EVERY_S = 4.5             # «печатает…» у Telegram гаснет через ~5 с
PHOTO_MIME = 'image/jpeg'        # Telegram пережимает фото в JPEG
IMAGE_MAX_BYTES = 3_750_000      # Claude API: картинка до 5 МБ в base64 = 3,75 МБ файла
DOCUMENT_MIMES = {'application/pdf': 'document', 'image/jpeg': 'image', 'image/png': 'image',
                  'image/webp': 'image', 'image/gif': 'image'}
BUSINESS_DAY_SHIFT = timedelta(hours=6)    # рабочие сутки бара длятся до 06:00 МСК (core/msk_time.py)

HELP_TEXT = ('Я помощник сети «Культура»: отвечаю по данным сайта — продажи и планы, остатки и заказы, '
             'краны, смены и зарплаты, контент-план и отзывы. Пишите вопрос обычными словами, можно '
             'приложить фото или PDF. Графики приходят с кнопкой «Открыть интерактивно», пояснение '
             'расчёта — по ссылке «Как считается».\n\n'
             'Большой вопрос — отчётом: «/report вопрос» или «Отчёт: вопрос». Соберу полный разбор на '
             'странице (графики, таблицы), в чат пришлю выжимку с кнопкой «Открыть отчёт».\n\n'
             'Вернуться к прошлой работе — ответьте на моё сообщение с отчётом или графиком («Ответить»): '
             'вопрос — отвечу с опорой на неё, «/report …» — соберу новую версию отчёта.\n\n'
             '/new — начать новый диалог')
REPORT_EMPTY_TEXT = 'Напишите вопрос для отчёта: «/report как прошёл сентябрь по барам».'
# Ответ на сообщение бота (2026-10-29, продолжение работы): текст обычного сообщения — не длиннее.
REPLY_QUOTE_MAX = 4000
# Режим отчёта, а модель ответила текстом (2026-10-28): одна просьба оформить ответ страницей.
REPORT_NUDGE = ('Это режим отчёта: ответ должен уйти страницей, а не сообщением. Отправь его сейчас инструментом '
                'common_report_send (title, summary, sections, how) с тем, что уже есть; данные заново не '
                'запрашивай. После отправки ничего не пиши.')
# Как кончился режим отчёта без страницы с первого раза — в журнал вопросов (jobs.error).
REPORT_PATHS = {'nudge': 'страница после просьбы', 'auto': 'страница собрана из текста',
                'unknown': 'статус отправки неизвестен', 'empty': 'нет текста для страницы'}
WEEKDAYS = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')
MONTHS = ('янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек')
UNSUPPORTED_TEXT = 'Пока понимаю текст, фото и PDF. Напишите вопрос словами.'
UNSUPPORTED_FILE_TEXT = ('Этот файл я не читаю: понимаю фото, картинки (JPEG, PNG, WebP, GIF) и PDF. '
                         'Отвечаю по тексту сообщения.')
NEW_DIALOG_TEXT = 'Начинаю новый диалог.'
INTERRUPTED_TEXT = 'Ответ на прошлый вопрос прервался: сервер перезапускался. Повторите вопрос, пожалуйста.'
RESTARTING_TEXT = 'Сервер перезапускается — повторите вопрос через минуту.'
SITE_DOWN_TEXT = 'Сайт сейчас не отвечает, без него я не вижу данных. Повторите вопрос через пару минут.'
FINGERPRINT_NOTICE = 'Обновились инструкции бота — начинаю новый диалог.'
LONG_DIALOG_NOTICE = 'Диалог стал слишком длинным — начинаю новый.'


def cost_line(spend: agent.Spend) -> str:
    """Последняя строка ответа: во что он обошёлся (бот и агенты вместе); упёрся в предел на
    вопрос — так и сказано."""
    line = f'Ответ обошёлся в ${spend.usd:.2f} (запросов к модели: {spend.steps})'
    limit = spend.budget()
    if limit and spend.usd >= limit:
        line += f' — остановился на пределе ${limit:.2f} на вопрос'
    return f'*{line}.*'


def _day(d) -> str:
    return f'{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}'


def _span(a, b) -> str:
    """«16–22 окт» или «28 сен – 4 окт» и ISO-границы в скобках: модель копирует, а не считает."""
    if a == b:
        text = f'{b.day} {MONTHS[b.month - 1]}'
    elif (a.year, a.month) == (b.year, b.month):
        text = f'{a.day}–{b.day} {MONTHS[b.month - 1]}'
    else:
        text = f'{a.day} {MONTHS[a.month - 1]} – {b.day} {MONTHS[b.month - 1]}'
    return f'{text} ({a.isoformat()}..{b.isoformat()})'


def calendar_text(now) -> str:
    """Даты для служебной строки: дни недели и окна «вчера», «последние 7 дней», месяцы.

    Модель дат не вычисляет (день недели «из памяти» — частая ошибка): подписи и границы
    окон она копирует отсюда. Рабочие сутки бара — до 06:00 МСК, поэтому «вчера» и окна
    считаются от рабочего дня, а не от календарной даты."""
    from datetime import timedelta as _td
    business = (now - BUSINESS_DAY_SHIFT).date()
    yesterday = business - _td(days=1)
    month_start = business.replace(day=1)
    prev_end = month_start - _td(days=1)
    parts = [f'рабочий день бара {_day(business)} ({business.isoformat()})',
             f'вчера {_day(yesterday)} ({yesterday.isoformat()})',
             f'последние 7 дней {_span(business - _td(days=7), yesterday)}',
             f'предыдущие 7 дней {_span(business - _td(days=14), business - _td(days=8))}']
    if business.day > 1:
        parts.append(f'этот месяц до вчера {_span(month_start, yesterday)}')
    parts.append(f'прошлый месяц {_span(prev_end.replace(day=1), prev_end)}')
    return ' · '.join(parts)


def refusal_text() -> str:
    return ('Это закрытый бот сети «Культура». Если вы администратор сайта, подключите Telegram на странице '
            f'{settings.ADMIN_PAGE_URL}, раздел «Бот».')


class Service:
    def __init__(self, site, store, io_factory=TelegramIO, client_factory=None, check_key=None):
        self.site = site
        self.store = store
        self.io_factory = io_factory
        self.client_factory = client_factory or claude.client_for
        self.check_key = check_key or claude.check_key
        self.tg: Optional[TelegramIO] = None
        self.token = ''
        self.key = ''
        self.config: Optional[Dict[str, Any]] = None
        self.config_at = 0.0
        self.bot_id: Optional[int] = None
        self.username = settings.BOT_USERNAME
        self.offset: Optional[int] = None
        self.executor = ThreadPoolExecutor(max_workers=max(1, settings.MAX_PARALLEL_DIALOGS),
                                           thread_name_prefix='kultura-bot-chat')
        self.queues: Dict[str, deque] = {}
        self.busy: set = set()
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.status: Dict[str, str] = {'state': 'starting', 'detail': 'сервер бота запускается', 'claude_error': ''}
        self.status_lock = threading.Lock()
        self.reported_at = 0.0
        self.usage_pending: Dict[tuple, Dict[str, Any]] = {}
        self.usage_lock = threading.Lock()
        self.catalog: Optional[tools.Catalog] = None
        self.catalog_at = 0.0
        self.catalog_lock = threading.Lock()
        self.actor_cache: Dict[str, tuple] = {}
        self.refused_at: Dict[str, float] = {}
        self._interrupted_checked = False

    # ---------------------------------------------------------------- состояние и отчёт

    def _secrets(self) -> tuple:
        """Что не должно попасть в текст ошибки для чата и страницы."""
        return (self.token, self.key, getattr(self.site, 'key', ''))

    def set_status(self, state: str, detail: str = '', *, claude_error: Optional[str] = None) -> None:
        with self.status_lock:
            before = dict(self.status)
            self.status['state'], self.status['detail'] = state, detail
            if claude_error is not None:
                self.status['claude_error'] = claude_error
            changed = self.status != before
        if changed:
            log.info('[BOT] состояние: %s — %s', state, detail)
            self.report(force=True)

    def add_usage(self, model: str, usage: Dict[str, int], cost: float) -> None:
        """Расход шага модели — в отчёт сайту (своя база пишется в agent.run_turn)."""
        key = (msk_day(), model or '')
        with self.usage_lock:
            item = self.usage_pending.setdefault(key, {'day': key[0], 'model': key[1], 'requests': 0,
                                                       'input_tokens': 0, 'output_tokens': 0, 'cache_read': 0,
                                                       'cache_write': 0, 'cost_usd': 0.0})
            item['requests'] += 1
            item['input_tokens'] += int(usage.get('input_tokens', 0))
            item['output_tokens'] += int(usage.get('output_tokens', 0))
            item['cache_read'] += int(usage.get('cache_read_input_tokens', 0))
            item['cache_write'] += int(usage.get('cache_creation_input_tokens', 0))
            item['cost_usd'] += float(cost)

    def report(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self.reported_at < HEARTBEAT_S:
            return
        with self.usage_lock:
            pending, self.usage_pending = self.usage_pending, {}
        with self.status_lock:
            # version — коммит кода (config.code_version, читается каждый раз): страница видит, обновился ли бот
            status = dict(self.status, bot=self.username, version=config.code_version())
        try:
            self.site.report({'status': status, 'usage': list(pending.values())})
            self.reported_at = now
        except SiteError as exc:
            log.warning('[BOT] отчёт сайту не ушёл: %s', exc.text)
            with self.usage_lock:                      # расход не теряем — уйдёт со следующим отчётом
                for key, item in pending.items():
                    merged = self.usage_pending.setdefault(key, dict(item, requests=0, input_tokens=0,
                                                                     output_tokens=0, cache_read=0, cache_write=0,
                                                                     cost_usd=0.0))
                    for field_name in ('requests', 'input_tokens', 'output_tokens', 'cache_read', 'cache_write',
                                       'cost_usd'):
                        merged[field_name] += item[field_name]

    # ---------------------------------------------------------------- настройки с сайта

    def refresh_config(self, force: bool = False) -> bool:
        """Настройки со страницы. False — их нет (сайт не ответил при запуске или отверг ключ)."""
        now = time.time()
        if not force and self.config is not None and now - self.config_at < CONFIG_EVERY_S:
            return True
        try:
            data = self.site.config()
        except SiteError as exc:
            self.config_at = now
            if exc.kind == 'auth':
                self.config = None                     # ключ сервера отозван — молчим
            if self.config is None:
                self.set_status('error', exc.text)
                return False
            log.warning('[BOT] настройки с сайта не обновились: %s', exc.text)
            return True
        self.config, self.config_at = data, now
        return True

    def ready(self) -> bool:
        """Есть токен и ключ, не пауза. Сменился токен — новый клиент Telegram, ключ — проверка."""
        if not self.refresh_config():
            return False
        telegram = self.config.get('telegram') or {}
        token = str(telegram.get('token') or '')
        key = str(self.config.get('anthropic_key') or '')
        if not token:
            self.set_status('waiting', 'нет токена бота: вставьте его на странице «Доступ агентов»')
            return False
        if not key:
            self.set_status('waiting', 'нет ключа Claude API: вставьте его на странице «Доступ агентов»')
            return False
        if self.config.get('paused'):
            self.set_status('paused', 'бот на паузе')
            return False
        if key != self.key:
            self.key = key
            kind, text = self.check_key(key)
            self.set_status(self.status['state'], self.status['detail'],
                            claude_error='' if kind in ('ok', 'offline', 'rate', 'overloaded', 'server') else text)
        if token != self.token:
            self.token = token
            self.tg = self.io_factory(token)
            self.offset = None
            result = (self.tg.get_me() or {}).get('result') or {}
            self.bot_id = result.get('id')
            self.username = result.get('username') or telegram.get('username') or self.username
            self.tg.delete_webhook()
            self.tg.set_commands()
        self.set_status('running', 'бот слушает Telegram')
        if not self._interrupted_checked:
            self._interrupted_checked = True
            chats = {job['chat_id'] for job in self.store.take_interrupted_jobs(INTERRUPTED_MAX_AGE_S)}
            for chat_id in sorted(chats):
                self.tg.send_plain(chat_id, INTERRUPTED_TEXT)
        return True

    # ---------------------------------------------------------------- цикл опроса

    def run_forever(self) -> None:
        self.set_status('starting', 'сервер бота запускается')
        while not self.stopping.is_set():
            try:
                if self.ready():
                    self.poll_once()
                else:
                    self.stopping.wait(IDLE_RECHECK_S)
                self.report()
            except Exception as exc:  # noqa: BLE001 — цикл опроса не должен умирать
                log.exception('[BOT] сбой цикла опроса')
                self.set_status('error', claude.scrub(f'{type(exc).__name__}: {exc}', self._secrets()))
                self.stopping.wait(10)
        log.info('[BOT] остановка: дожидаюсь начатых ответов')
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.set_status('stopped', 'сервер бота остановлен')

    def stop(self) -> None:
        self.stopping.set()

    def poll_once(self) -> None:
        data = self.tg.get_updates(self.offset)
        if data is None:
            self.set_status('error', 'нет связи с Telegram — повторяю')
            self.stopping.wait(5)
            return
        if not data.get('ok'):
            code, description = data.get('error_code'), str(data.get('description') or '')
            if code == 409 and 'webhook' in description.lower():
                self.tg.delete_webhook()
            elif code == 409:
                self.set_status('conflict', 'токеном бота пользуется другая программа (старый бот?) — остановите '
                                            'её или выпустите новый токен в @BotFather; пока она работает, '
                                            'Telegram отдаёт сообщения то ей, то сюда')
                self.stopping.wait(CONFLICT_RETRY_S)
            elif code == 401:
                self.set_status('error', 'Telegram не принимает токен бота — вставьте новый на странице «Доступ '
                                         'агентов»')
                self.stopping.wait(IDLE_RECHECK_S)
            else:
                self.set_status('error', f'Telegram: {description or code}')
                self.stopping.wait(5)
            return
        self.set_status('running', 'бот слушает Telegram')
        for update in data.get('result') or []:
            self.offset = update['update_id'] + 1
            try:
                self.handle_update(update)
            except Exception:  # noqa: BLE001 — одно кривое сообщение не останавливает бота
                log.exception('[BOT] сообщение %s не обработано', update.get('update_id'))

    # ---------------------------------------------------------------- кто пишет

    def actor(self, tg_user_id: str, fresh: bool = False) -> Optional[Dict[str, Any]]:
        """Привязанный активный администратор (спрашиваем сайт) или None. SiteError — наверх."""
        now = time.time()
        cached = self.actor_cache.get(tg_user_id)
        if cached is not None and not fresh and now - cached[0] < ACTOR_CACHE_S:
            return cached[1]
        actor = self.site.actor(tg_user_id)
        if len(self.actor_cache) > 5000:           # не копим память на спамерах
            self.actor_cache.clear()
        self.actor_cache[tg_user_id] = (now, actor)
        return actor

    def refusal_due(self, tg_user_id: str, now: Optional[float] = None) -> bool:
        """Пора ли ответить незнакомцу «закрытый бот» (не чаще раза в REFUSAL_EVERY_S)."""
        now = time.time() if now is None else now
        last = self.refused_at.get(tg_user_id)
        if last is not None and now - last < REFUSAL_EVERY_S:
            return False
        if len(self.refused_at) > 5000:
            self.refused_at.clear()
        self.refused_at[tg_user_id] = now
        return True

    # ---------------------------------------------------------------- сообщение

    def _addressed(self, message: Dict[str, Any], text: str) -> bool:
        """В группе: к боту обратились — @имя, ответ на его сообщение, команда /…@имя."""
        name = '@' + (self.username or '').lower()
        if name != '@' and name in text.lower():
            return True
        return self._from_bot(message.get('reply_to_message'))

    def _from_bot(self, msg: Optional[Dict[str, Any]]) -> bool:
        """Сообщение написал этот бот."""
        author = (msg or {}).get('from') or {}
        if self.bot_id:
            return author.get('id') == self.bot_id
        # getMe при запуске не ответил — узнаём бота по имени
        name = '@' + (self.username or '').lower()
        return bool(author.get('is_bot') and name != '@' and '@' + (author.get('username') or '').lower() == name)

    def reply_block(self, chat_id: str, message: Dict[str, Any]) -> str:
        """Ответ на сообщение бота (Reply в Telegram) — продолжение той работы (2026-10-29).

        Отчёт или график этого чата сайт отдаёт целиком текстом (GET /api/bot/replied: выводы,
        разделы, таблицы и описания графиков); иначе — текст самого сообщения. Блок идёт перед
        вопросом, между строками «<<<» и «>>>» (prompts/bot.md, «Продолжение работы»)."""
        replied = message.get('reply_to_message') or {}
        if not replied or not self._from_bot(replied):
            return ''
        quoted = str(replied.get('text') or replied.get('caption') or '').strip()
        found = None
        if replied.get('message_id'):
            try:
                found = self.site.replied(chat_id, replied['message_id'])
            except SiteError as exc:
                log.warning('[BOT] не узнал, на что ответили: %s', exc.text)
        if found and found.get('kind') == 'report':
            log.info('[BOT] ответ на отчёт %s', found.get('id'))
            return (f'[Ответ на отчёт «{found.get("title") or ""}» — продолжение той работы. Отчёт целиком — '
                    f'между строками <<< и >>>.]\n<<<\n{found["text"]}\n>>>\n')
        if found and found.get('kind') == 'chart':
            log.info('[BOT] ответ на график %s', found.get('id'))
            caption = f'Подпись к графику (ответ бота):\n{quoted[:REPLY_QUOTE_MAX]}\n\n' if quoted else ''
            return (f'[Ответ на график «{found.get("title") or ""}» — продолжение той работы. Подпись и описание '
                    f'графика — между строками <<< и >>>.]\n<<<\n{caption}{found["text"]}\n>>>\n')
        if quoted:
            return (f'[Ответ на сообщение бота — его текст между строками <<< и >>>.]\n<<<\n'
                    f'{quoted[:REPLY_QUOTE_MAX]}\n>>>\n')
        return ''

    def _strip_mention(self, text: str) -> str:
        """Убрать @имя бота и знаки, которые остаются после обращения: «@бот, отчёт: …» -> «отчёт: …»."""
        if not self.username:
            return text
        text = re.sub(r'@' + re.escape(self.username) + r'\b', '', text, flags=re.I)
        return re.sub(r'^[\s,.:;!—–-]+', '', text).strip()

    @staticmethod
    def _command(text: str):
        """('/new@bot аргументы') -> ('new', 'аргументы'); не команда -> (None, текст).
        Аргументы — после любого пробела, в том числе перевода строки («/report\nвопрос»)."""
        if not text.startswith('/'):
            return None, text
        parts = text.split(None, 1)
        rest = parts[1].strip() if len(parts) > 1 else ''
        return parts[0][1:].split('@', 1)[0].lower(), rest

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

        try:
            if command == 'start' and rest and chat_type == 'private':
                answer = self.site.link(rest, tg_user_id, tg_name)
                self.actor_cache.pop(tg_user_id, None)
                self.tg.send_plain(chat_id, str(answer.get('text') or ''))
                return
            actor = self.actor(tg_user_id)
        except SiteError as exc:
            log.warning('[BOT] сайт не ответил на вопрос о доступе: %s', exc.text)
            self.tg.send_plain(chat_id, SITE_DOWN_TEXT)
            return
        if command == 'start':
            if actor:
                self.tg.send_plain(chat_id, HELP_TEXT)
            elif chat_type == 'private':
                self.tg.send_plain(chat_id, refusal_text())
            return
        if actor is None:
            if chat_type == 'private' and self.refusal_due(tg_user_id):
                self.tg.send_plain(chat_id, refusal_text())
            return
        if command == 'new':
            # Через очередь чата: ответ, который ещё пишется, иначе сохранил бы старый диалог обратно.
            self.enqueue(chat_id, {'kind': 'new', 'message': message, 'actor': actor, 'text': '',
                                   'chat_type': chat_type})
            return
        if command == 'help':
            self.tg.send_plain(chat_id, HELP_TEXT)
            return
        has_file = bool(message.get('photo') or (message.get('document') or {}).get('mime_type') in DOCUMENT_MIMES)
        mode = 'answer'
        if command == settings.REPORT_COMMAND:
            mode, text = 'report', rest
            if not text and not has_file:             # «/report» подписью к PDF — отчёт по файлу
                self.tg.send_plain(chat_id, REPORT_EMPTY_TEXT)
                return
        elif text.lower().startswith(tuple(w.lower() for w in settings.REPORT_WORDS)):
            mode = 'report'
        if not text and not has_file:
            self.tg.send_plain(chat_id, UNSUPPORTED_TEXT)
            return
        self.enqueue(chat_id, {'message': message, 'actor': actor, 'text': text, 'chat_type': chat_type,
                               'mode': mode})

    # ---------------------------------------------------------------- очередь

    def enqueue(self, chat_id: str, job: Dict[str, Any]) -> None:
        if job.get('kind') != 'new':
            # Вопрос записан сразу ('queued'): остановка, пока он ждёт очереди, не потеряет его
            # молча — после запуска чат получит «повторите вопрос» (store.take_interrupted_jobs).
            job['job_id'] = self.store.start_job(chat_id, job['actor']['tg_user_id'], status='queued')
        with self.lock:
            self.queues.setdefault(chat_id, deque()).append(job)
            if chat_id in self.busy:
                return
            self.busy.add(chat_id)
        try:
            self.executor.submit(self._drain, chat_id)
        except RuntimeError:
            # Сервер останавливается: начатые ответы доводятся до конца, новых не берём.
            # Вопрос не теряем молча — просим повторить.
            with self.lock:
                self.busy.discard(chat_id)
                dropped = list(self.queues.pop(chat_id, None) or [])
            for item in dropped:
                if item.get('job_id'):
                    self.store.finish_job(item['job_id'], 'error', 'restarting')
            self.tg.send_plain(chat_id, RESTARTING_TEXT)

    def _drain(self, chat_id: str) -> None:
        while True:
            with self.lock:
                queue = self.queues.get(chat_id)
                if not queue or self.stopping.is_set():
                    # остановка: ждавшие очереди остаются 'queued' — после запуска «повторите вопрос»
                    self.busy.discard(chat_id)
                    self.queues.pop(chat_id, None)
                    return
                job = queue.popleft()
            try:
                self.run_job(chat_id, job)
            except Exception:  # noqa: BLE001
                log.exception('[BOT] ответ в чат %s упал', chat_id)

    def run_job(self, chat_id: str, job: Dict[str, Any]) -> None:
        """Задание из очереди чата: /new или вопрос."""
        if job.get('kind') == 'new':
            self.store.delete_dialog(chat_id)
            self.tg.send_plain(chat_id, NEW_DIALOG_TEXT)
            return
        self.answer(chat_id, job)

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
    def header(actor: Dict[str, Any], mode: str = 'answer', limit: Optional[float] = None) -> str:
        now = msk_now()
        limit = settings.REPORT_BUDGET_USD if limit is None else limit
        report = f' · режим: отчёт — страница common_report_send, предел ${limit:.2f}' if mode == 'report' else ''
        return (f'[{WEEKDAYS[now.weekday()]} {now.strftime("%d.%m.%Y %H:%M")} МСК · {calendar_text(now)}{report} · '
                f'пишет {actor["display_name"]} ({actor["login"]})]')

    def how_link(self, chat_id: str, visible: str, how: str):
        """«Как считается» -> записка на сайте и ссылка или кнопка. Вернуть (текст, reply_markup).

        Сайт не ответил — блок возвращается в ответ свёрнутой цитатой (ничего не теряется)."""
        try:
            note_id = self.site.note(chat_id, how)
        except SiteError as exc:
            log.warning('[BOT] записка «Как считается» не сохранилась: %s', exc.text)
            quoted = '\n'.join('>> ' + line if line.strip() else '>>' for line in
                               [links.HOW_TEXT] + how.split('\n'))
            return (f'{visible}\n\n{quoted}' if visible else quoted), None
        target = links.how_target(chat_id, note_id, self.username)
        if 'link' in target:
            return formatting.with_link(visible, links.HOW_TEXT, target['link']), None
        return visible, {'inline_keyboard': [[target['button']]]}

    def get_catalog(self) -> tools.Catalog:
        """Правила и инструменты с сайта (обновляются раз в settings.CATALOG_TTL_S)."""
        with self.catalog_lock:
            if self.catalog is not None and time.time() - self.catalog_at < settings.CATALOG_TTL_S:
                return self.catalog
            try:
                self.catalog = tools.load_catalog(self.site)
                self.catalog_at = time.time()
            except SiteError as exc:
                if self.catalog is None:
                    raise
                log.warning('[BOT] каталог не обновился, отвечаю по прежнему: %s', exc.text)
                self.catalog_at = time.time() - settings.CATALOG_TTL_S + 60     # ещё раз через минуту
            return self.catalog

    def deliver(self, chat_id: str, answer: str, *, ctx: tools.ToolContext, spend: agent.Spend,
                notice: str = '', reply_to: Optional[int] = None) -> None:
        """Ответ модели -> Telegram: «Как считается» за ссылкой, строка цены, уведомление.

        График или отчёт уже ушли подписью-ответом, а текста нет — второго сообщения нет
        (кроме уведомления и строки цены, пока она включена)."""
        visible, how = formatting.split_how(answer or '')
        if ctx.report_mode and ctx.reports_sent:
            # Режим отчёта: ответ — страница; текст модели после неё («Отчёт отправлен») не нужен.
            if visible.strip():
                log.info('[BOT] отчёт ушёл страницей, текст после него не отправлен: %s', visible[:200])
            visible, how = '', ''
        markup = None
        if how:
            visible, markup = self.how_link(chat_id, visible, how)
        sent_card = bool(ctx.charts_sent or ctx.reports_sent)
        text = visible or ('' if sent_card or markup else 'Готово.')
        if notice:
            text = f'*{notice}*\n\n{text}' if text else f'*{notice}*'
        limit = spend.budget()
        if settings.SHOW_COST or (limit and spend.usd >= limit):
            text = f'{text}\n\n{cost_line(spend)}' if text else cost_line(spend)
        if text or markup:
            self.tg.send_markdown(chat_id, text or links.HOW_TEXT, reply_to=reply_to, reply_markup=markup)

    def finish_report(self, client, persona, ctx: tools.ToolContext, result: agent.TurnResult,
                      question: str):
        """Режим отчёта, а страница не ушла (модель ответила текстом сама или упёршись в предел).

        Сначала одна просьба оформить ответ страницей (REPORT_NUDGE: REPORT_FINISH_ROUNDS шагов, можно
        только common_report_send — данные уже собраны). Не помогло — страницу из текста ответа
        собирает сам бот (report_text.build) тем же инструментом: ни одного запроса к Claude, поэтому
        и при исчерпанном дневном пределе. Вернуть (итог хода, как кончилось):
            'nudge'    страницу отправила модель после просьбы
            'auto'     страницу собрал бот из текста
            'unknown'  отправка «статус неизвестен» (Telegram не ответил, страница могла дойти) —
                       повторять нельзя, текст модели уходит как есть
            'empty'    текста нет (отказ модели) — собирать не из чего
            иначе      причина, почему страница не собралась (текст уходит сообщением)"""
        if ctx.report_unknown:
            return result, 'unknown'
        if not ctx.report_only and 'refusal' not in result.notes and self._daily_budget_left():
            ctx.report_only = True
            log.warning('[BOT] отчёт: модель ответила текстом — прошу оформить его страницей')
            try:
                retry = agent.run_turn(client, system_text=persona.system, tool_list=persona.toolset.defs,
                                       history=result.messages, user_content=[{'type': 'text', 'text': REPORT_NUDGE}],
                                       ctx=ctx, store=self.store, max_rounds=settings.REPORT_FINISH_ROUNDS,
                                       on_usage=self.add_usage, fast=settings.REPORT_FAST_MODE)
            except Exception as exc:  # noqa: BLE001 — и дневной предел: готовый ответ не теряем, страница — из текста
                log.warning('[BOT] отчёт: просьба оформить страницей не удалась: %s', exc)
            else:
                text = retry.text if ctx.reports_sent else max(result.text, retry.text, key=len)
                result = dataclasses.replace(retry, text=text, notes=result.notes + retry.notes,
                                             cost_usd=result.cost_usd + retry.cost_usd)
            if ctx.reports_sent:
                return result, 'nudge'
            if ctx.report_unknown:
                return result, 'unknown'
        if 'refusal' in result.notes or not result.text.strip():
            return result, 'empty'
        log.warning('[BOT] отчёт: модель не отправила страницу — собираю её из текста ответа')
        block = {'id': 'auto_report', 'name': tools.REPORT_TOOL,
                 'input': {'report': report_text.build(result.text, question)}}
        outcome = tools.execute(block, ctx)
        if ctx.report_unknown:
            return result, 'unknown'
        if outcome.get('is_error'):
            reason = ' '.join(str(b.get('text') or '') for b in outcome.get('content') or [] if isinstance(b, dict))
            log.warning('[BOT] отчёт: страница из текста не собралась: %s', reason)
            return result, reason.strip()[:300] or 'сайт не ответил'
        return dataclasses.replace(result, text=''), 'auto'

    def question_limit(self, report_mode: bool) -> float:
        """Предел расхода на этот вопрос: обычный или отчёта, но не больше остатка дня минус
        DAILY_RESERVE_USD — вопрос завершается ответом (страницей) раньше дневной остановки."""
        limit = settings.REPORT_BUDGET_USD if report_mode else settings.QUESTION_BUDGET_USD
        if settings.DAILY_BUDGET_USD:
            # Остаток дня не меньше цента: 0 значил бы «без предела».
            left = max(settings.DAILY_BUDGET_USD - self.store.spent_on() - settings.DAILY_RESERVE_USD, 0.01)
            limit = min(limit, left) if limit else left
        return limit

    def _daily_budget_left(self) -> bool:
        """Дневной предел ещё не исчерпан (просьба — это запрос к Claude)."""
        try:
            agent.check_budget(self.store)
        except agent.BudgetExceeded:
            return False
        return True

    def answer(self, chat_id: str, job: Dict[str, Any]) -> None:
        message = job['message']
        reply_to = message.get('message_id') if job['chat_type'] != 'private' else None
        job_id = job.get('job_id') or self.store.start_job(chat_id, job['actor']['tg_user_id'])
        self.store.run_job(job_id)
        try:
            # Права — ещё раз: пока вопрос ждал очереди, привязку могли снять, а админство — отозвать.
            actor = self.actor(job['actor']['tg_user_id'], fresh=True)
            catalog = self.get_catalog()
        except SiteError as exc:
            log.warning('[BOT] сайт не ответил перед ответом: %s', exc.text)
            self.tg.send_plain(chat_id, SITE_DOWN_TEXT, reply_to=reply_to)
            self.store.finish_job(job_id, 'error', f'site: {exc.text}')
            return
        if actor is None:
            self.store.finish_job(job_id, 'error', 'no access')
            return
        stop = threading.Event()
        threading.Thread(target=self._typing, args=(chat_id, stop), daemon=True).start()
        status, error = 'done', ''
        report_mode = job.get('mode') == 'report'
        try:
            limit = self.question_limit(report_mode)
            header = self.header(actor, 'report' if report_mode else 'answer', limit)
            reply = self.reply_block(chat_id, message)
            user_content = [{'type': 'text', 'text': f'{header}\n{reply}{job["text"] or "(без текста)"}'}]
            files = self._files(message)
            document = message.get('document') or {}
            if document and document.get('mime_type') not in DOCUMENT_MIMES:
                self.tg.send_plain(chat_id, UNSUPPORTED_FILE_TEXT, reply_to=reply_to)
            elif (message.get('photo') or document) and not files:
                self.tg.send_plain(chat_id, f'Файл не скачался или слишком большой (картинка — до '
                                            f'{self._limit("image") / 1e6:.1f} МБ, PDF — до '
                                            f'{self._limit("document") / 1e6:.0f} МБ) — отвечаю без него.',
                                   reply_to=reply_to)
            user_content += files

            persona = catalog.bot
            dialog = self.store.get_dialog(chat_id)
            notice = ''
            if dialog is not None:
                idle = time.time() - dialog['last_ts'] > settings.DIALOG_IDLE_MINUTES * 60
                if idle:
                    notice, dialog = settings.NEW_DIALOG_NOTICE, None
                elif dialog['fingerprint'] != persona.fingerprint:
                    notice, dialog = FINGERPRINT_NOTICE, None
                elif len(str(dialog['messages'])) > settings.DIALOG_MAX_CHARS:
                    notice, dialog = LONG_DIALOG_NOTICE, None
            history = dialog['messages'] if dialog else []
            started_at = dialog['started_at'] if dialog else msk_now().isoformat(timespec='seconds')
            turns = dialog['turns'] if dialog else 0

            client = self.client_factory(self.key)
            spend = agent.Spend(limit=limit)
            ctx = tools.ToolContext(site=self.site, chat_id=chat_id, allowed=persona.toolset.names, spend=spend,
                                    report_mode=report_mode)
            agent_header = self.header(actor)          # агенту — без «режим: отчёт»: страницу собирает бот
            ctx.run_agent = lambda name, task: agent.run_agent(client, catalog.agents[name], task, parent=ctx,
                                                               store=self.store, header=agent_header,
                                                               on_usage=self.add_usage)
            result = agent.run_turn(client, system_text=persona.system, tool_list=persona.toolset.defs,
                                    history=history, user_content=user_content, ctx=ctx, store=self.store,
                                    max_rounds=settings.REPORT_MAX_TOOL_ROUNDS if report_mode else None,
                                    on_usage=self.add_usage,
                                    fast=settings.REPORT_FAST_MODE if report_mode else True)
            if report_mode and not ctx.reports_sent:
                result, path = self.finish_report(client, persona, ctx, result, job['text'])
                error = 'report: ' + REPORT_PATHS.get(path, path)
                if path not in REPORT_PATHS:
                    notice = f'{notice} ' if notice else ''
                    notice += f'Страницу отчёта собрать не удалось ({path}) — ответ ниже сообщением.'
            self.store.save_dialog(chat_id, persona.fingerprint, started_at, result.messages, turns + 1)
            self.deliver(chat_id, result.text, ctx=ctx, spend=spend, notice=notice, reply_to=reply_to)
            if self.status['claude_error']:             # Claude снова отвечает — ошибку со страницы убрать
                self.set_status(self.status['state'], self.status['detail'], claude_error='')
        except agent.BudgetExceeded as exc:
            status, error = 'error', 'budget'
            self.tg.send_plain(chat_id, str(exc), reply_to=reply_to)
        except Exception as exc:  # noqa: BLE001 — любая беда -> понятный ответ в чат
            kind, text = claude.describe_error(exc, secrets=self._secrets())
            status, error = 'error', f'{kind}: {text}'
            log.warning('[BOT] ответ не получился (%s): %s', kind, text)
            if kind == 'bad_request':
                self.store.delete_dialog(chat_id)        # битая история не должна ломать следующие вопросы
                text += ' Диалог начат заново — повторите вопрос.'
            elif kind == 'other':
                log.exception('[BOT] сбой ответа')
                text = f'Не получилось ответить: {text}'
            self.tg.send_plain(chat_id, text, reply_to=reply_to)
            if kind in ('auth', 'denied', 'billing', 'offline'):
                # Опрос Telegram идёт и пишет «работает» — ошибка Claude держится отдельным полем,
                # пока следующий ответ не получится.
                self.set_status(self.status['state'], self.status['detail'], claude_error=text)
        finally:
            stop.set()
            self.store.finish_job(job_id, status, error)
