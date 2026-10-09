"""Long-polling @kult_taplist_bot: краны, подписка гостей на новости, отзывы.

Webhook после отзыва токена Telegram сбрасывает, а входящие соединения от
Telegram до сервера режет ТСПУ. Ответы через aiogram из Flask обрывались по
таймауту даже когда сообщение уже дошло. Поэтому бот сам забирает апдейты и
сам отвечает через тот же HTTP-клиент, что и бот открытия: запасной IP, если
api.telegram.org не открывается.

Один процесс на gunicorn --workers 2: flock на data/.taplist_polling.lock.
Пока webhook зарегистрирован, getUpdates отвечает 409 — webhook снимается
без drop_pending_updates.

Отключение: TAPLIST_POLLING=0.

## Что умеет бот
- Краны: /start, /taplist, /help — меню баров; /taplist1..4, /taplistall. С 2026-10-04 таплист —
  из реестра Untappd (связь по GUID товара iiko, единственный источник правды) теми же строками,
  что «Таплист пятницы»: «{кран}. {пивоварня и название} — {стиль}, {крепость}%[, новинка]», имя —
  ссылка на Untappd (core/taplist_post.bar_message_html). Прежний справочник по названиям
  (data/beer_info_mapping.json, подбор по похожести) больше не читается.
- Подписка на новости (2026-09-28): кнопка «Подписаться на новости» (или /subscribe) ->
  текст согласия (core/guest_subscribers.CONSENT_TEXT) + «Согласен» -> выбор баров
  (несколько или «Все бары») + «Готово» -> по желанию телефон (кнопка Telegram
  «Поделиться телефоном», можно «Пропустить») -> «Готово: вы подписаны…».
  /stop или кнопка «Отписаться от новостей» — отписка. Хранение, телефон, сегменты
  рассылки — core/guest_subscribers.py.
- Отзыв: «Оставить отзыв» (или /review) -> бар -> оценка 1..5 -> текст одним сообщением
  или «Отправить без текста» -> «Спасибо». Пишется в core/guest_reviews: source 'bot',
  origin 'import', external_id 'tg:<chat_id>:<message_id>' (сообщение с текстом, а без
  текста — сообщение бота с кнопкой), guest {telegram: @ник или chat id, phone: телефон
  подписчика, если он им делился}, created_at — время сообщения по Москве.
  /stop стирает телефон и в отзывах гостя (ReviewStore.clear_guest_phone).
- Ссылки для QR-кодов: t.me/kult_taplist_bot?start=subscribe | review | review_<бар>
  (бар — ключ сети: bolshoy, ligovskiy, kremenchugskaya, varshavskaya).
- my_chat_member: гость заблокировал бота -> mark_blocked, разблокировал -> снять отметку.
- Сразу после сохранения отзыва — уведомление владельцу (подписчикам бота
  kulturaopenclosed) в фоновом потоке: core/review_notify.notify_review_in_background,
  с отметкой tg_notified_at — утренняя сверка его не повторит. Пропущенные (перезапуск,
  потолок 20 в час) раз в 10 минут подбирает Housekeeping (notify_pending_in_background).
- Непонятный текст в личке (бот ничего не ждёт) — подсказка TEXT_HINT, не молчание.
Подписка и отзыв — только в личном чате: согласие даёт конкретный человек, а свой
контакт Telegram отдаёт только в личке. В группе бот отвечает, что нужно написать лично,
и меню там — только краны.

## Выключатель записи гостей
signup_enabled_now() — core.content_channels.bot_signup_enabled(), читается на каждый
апдейт; нет модуля или функции, любой сбой — выключено. Выключено: меню — только краны
(подписанному остаётся «Отписаться от новостей», её обещает текст согласия);
/subscribe, /review и ссылки ?start=subscribe|review… ведут в меню; старые кнопки
«Подписаться на новости» и «Оставить отзыв» — тоже в меню; /stop и «Отписаться» —
всегда; начатые при включённом шаги (согласие, бары, телефон, оценка, текст) доходят
до конца — но «Согласен» и кнопки отзыва (rv:…) принимаются, только если у чата есть
ЖИВОЙ шаг диалога в базе (согласие показано, выбор бара или оценки открыт, не старше
30 минут): старые и подделанные кнопки ведут в меню кранов. Меню команд Telegram
(setMyCommands) тоже следует выключателю: без /subscribe и /review, пока выключено;
Housekeeping сверяет выключатель не чаще раза в минуту и переотправляет меню при смене.
План получает флаг параметром plan_update(update, dialog, signup) — остаётся чистой
функцией.

## Как устроен диалог
plan_update(update, dialog) — чистая функция: апдейт + состояние диалога чата -> список
действий (сети, базы и файлов здесь нет — тестируется без Telegram). _execute исполняет
действия: сообщения, база подписчиков, отзывы, состояние диалога; зависимости — в
BotContext (в тестах подменяются подделками). handle_update — одно и другое вместе.

Кнопки несут всё нужное в callback_data (выбор баров — маска в 'sb:<маска>:<действие>',
отзыв — 'rv:…' с баром и оценкой). Шаг диалога (flow: consent — показано согласие;
review — открыт выбор бара или оценки; review_text — ждём текст отзыва; sub_phone — ждём
телефон) хранится в guest_subscribers.db (PersistentDialogStore, таймаут
DIALOG_TIMEOUT = 30 минут): перезапуск воркера (--max-requests, деплой) его не стирает.
База не отвечает — шаг держится в памяти (DialogStore). Через 30 минут текст уже не
принимается как отзыв (иначе «привет» на следующий день стал бы отзывом): первое
сообщение после таймаута получает ответ «время вышло», дальше — подсказка.
Любая команда завершает диалог; на шаге телефона она сначала закрывает подписку без
телефона (сообщение «Готово…» убирает кнопку телефона).

callback_data (не больше 64 байт — предел Telegram):
    taplist_bar1..4, taplist_all        краны (как раньше)
    sub_start / sub_later               «Подписаться на новости» / «Не сейчас»
    sub_agree:<версия>                  «Согласен» с версией текста согласия; версия не
                                        текущая (или её нет) — показать текущий текст
                                        заново, не подписывать
    sub_stop                            «Отписаться от новостей»
    sb:<маска 0..15>:<0..3|a|ok>        выбор баров: отметить бар i / «Все бары» / «Готово»
                                        (маска — текущий выбор, бит i — бар i сети)
    rev_start                           «Оставить отзыв»
    rv:b:<i>                            бар отзыва
    rv:r:<i>:<1..5>                     оценка
    rv:s:<i>:<1..5>                     «Отправить без текста» — только из живого диалога
                                        этого же сообщения (иначе второй отзыв-дубль)
    rv:x                                «Отмена»

Тексты гостей — данные: сообщения диалога уходят без parse_mode (разметка из имени или
текста гостя не сработает), в отзыв текст пишется как есть, экранирует тот, кто
показывает (страница отзывов — GH.esc, уведомления core/review_notify — html.escape).

Защита от спама: не больше REVIEW_DAILY_LIMIT отзывов из одного чата за московские сутки;
уведомлений владельцу об отзывах из бота — не больше 20 в час (дальше — сводкой);
спам удаляется на странице отзывов.

## Changelog
- 2026-09-28: подписка на новости с согласием, выбор баров, телефон; отзыв из бота;
  my_chat_member; ссылки для QR-кодов. Меню и команды кранов не менялись.
- 2026-09-28: выключатель записи гостей (content_channels.bot_signup_enabled);
  уведомление владельцу об отзыве из бота — сразу, а не после утренней сверки.
- 2026-09-28 (проверка): шаг диалога в базе, подсказка на непонятный текст, при
  выключенной записи кнопки — только из живого шага, меню команд по выключателю, версия
  согласия в «Согласен», зарубежный телефон без искажения, /stop стирает телефон в
  отзывах, подбор пропущенных уведомлений, command_name на тексте из пробелов.
- 2026-10-04: краны — из реестра Untappd строками «Таплиста пятницы»
  (core/taplist_post.bar_message_html); справочник по названиям, подбор по похожести и
  label_bars удалены; сбой данных — TEXT_TAPLIST_ERROR вместо молчания.
"""
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import portalocker

from core import guest_subscribers as gsubs
from core import msk_time

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_PATH = os.path.join(_BASE_DIR, 'data', '.taplist_polling.lock')

POLL_TIMEOUT = 25
HTTP_TIMEOUT = POLL_TIMEOUT + 15
# my_chat_member — чтобы узнать о блокировке бота сразу, а не при следующей рассылке.
ALLOWED_UPDATES = ['message', 'callback_query', 'my_chat_member']

BAR_NAMES = {
    'bar1': 'Большой пр. В.О',
    'bar2': 'Лиговский',
    'bar3': 'Кременчугская',
    'bar4': 'Варшавская',
}

_COMMANDS = [
    {"command": "start", "description": "Кнопки баров"},
    {"command": "taplist", "description": "Выбрать бар"},
    {"command": "taplist1", "description": "Большой пр. В.О"},
    {"command": "taplist2", "description": "Лиговский"},
    {"command": "taplist3", "description": "Кременчугская"},
    {"command": "taplist4", "description": "Варшавская"},
    {"command": "taplistall", "description": "Все бары"},
    {"command": "subscribe", "description": "Подписаться на новости"},
    {"command": "review", "description": "Оставить отзыв"},
    {"command": "stop", "description": "Отписаться от новостей"},
    {"command": "help", "description": "Кнопки баров"},
]
# Команды входа в подписку и отзыв: в меню команд Telegram — только при включённой
# записи гостей (commands_for). /stop остаётся всегда: отписка работает всегда.
_SIGNUP_COMMANDS = ('subscribe', 'review')
# Как часто цикл опроса сверяет выключатель записи гостей с меню команд (setMyCommands):
# не чаще раза в минуту — выключатель читается из файла, Telegram не дёргаем зря.
COMMANDS_CHECK_SEC = 60


def commands_for(signup: bool) -> list:
    """Меню команд бота для setMyCommands: при выключенной записи — без /subscribe и /review."""
    if signup:
        return [dict(c) for c in _COMMANDS]
    return [dict(c) for c in _COMMANDS if c['command'] not in _SIGNUP_COMMANDS]

# Диалог: сколько ждём текст отзыва или телефон; сколько помним истёкший шаг, чтобы
# ответить «время вышло» (дальше запись просто забывается).
DIALOG_TIMEOUT = timedelta(minutes=30)
DIALOG_FORGET = timedelta(hours=24)
# Не больше стольких отзывов из одного чата за московские сутки (защита от спама).
REVIEW_DAILY_LIMIT = 3
# Подпись «кто добавил» у отзывов из бота (added_by в core/guest_reviews).
REVIEW_ADDED_BY = 'Бот @kult_taplist_bot'

# ----------------------------------------------------------------- кнопки и тексты

MENU_TEXT = 'Нажми бар:'
BTN_SUBSCRIBE = 'Подписаться на новости'
BTN_UNSUBSCRIBE = 'Отписаться от новостей'
BTN_REVIEW = 'Оставить отзыв'
BTN_AGREE = 'Согласен'
BTN_LATER = 'Не сейчас'
BTN_ALL_BARS = 'Все бары'
BTN_DONE = 'Готово'
BTN_SHARE_PHONE = 'Поделиться телефоном'
BTN_SKIP = 'Пропустить'
BTN_NO_TEXT = 'Отправить без текста'
BTN_CANCEL = 'Отмена'
MARK_ON = '✓ '    # отметка выбранного бара (галочка U+2713 — знак, не эмодзи)

CB_SUB_START = 'sub_start'
CB_SUB_AGREE = 'sub_agree'       # кнопка «Согласен» несёт версию: 'sub_agree:<CONSENT_VERSION>'
CB_SUB_LATER = 'sub_later'
CB_SUB_STOP = 'sub_stop'
CB_REV_START = 'rev_start'
_GUEST_CALLBACKS = (CB_SUB_START, CB_SUB_AGREE, CB_SUB_LATER, CB_SUB_STOP, CB_REV_START)

TEXT_PRIVATE_ONLY = 'Подписка на новости и отзывы работают в личном чате с ботом — напишите ему лично.'
TEXT_SUB_ALREADY = ('Вы уже подписаны на новости ({bars}). Чтобы изменить бары, отметьте нужные '
                    'и нажмите «Готово».')
TEXT_SUB_BARS = ('Подписка оформлена. Новости каких баров присылать? Отметьте один или несколько '
                 'и нажмите «Готово». Если ничего не отмечать — будут новости всех баров.')
TEXT_SUB_LATER = 'Хорошо. Подписаться можно в любой момент: /start, затем «Подписаться на новости».'
TEXT_SUB_BARS_SAVED = 'Бары для новостей: {bars}.'
TEXT_SUB_PHONE = ('Последний шаг, по желанию: поделитесь номером телефона — так подписка свяжется '
                  'с вашей картой гостя «Культуры». Нажмите «Поделиться телефоном» внизу '
                  'или «Пропустить».')
TEXT_SUB_PHONE_HINT = ('Номер принимаем только кнопкой «Поделиться телефоном» — так Telegram '
                       'подтверждает, что он ваш. Или нажмите «Пропустить».')
TEXT_SUB_PHONE_NOT_OWN = 'Это не ваш номер. Чтобы поделиться своим, нажмите кнопку «Поделиться телефоном».'
TEXT_SUB_PHONE_NO_SUB = ('Телефон сохраняем только у подписчиков новостей. Подписаться: /start, '
                         'затем «Подписаться на новости».')
TEXT_SUB_PHONE_BAD = 'Не получилось прочитать номер. Можно попробовать ещё раз: /subscribe.'
TEXT_SUB_PHONE_SAVED = 'Телефон сохранён.'
TEXT_SUB_DONE = ('Готово: вы подписаны на новости баров «Культура» ({bars}).\n'
                 'Изменить бары — /subscribe. Отписаться — кнопкой «Отписаться от новостей» '
                 'в меню (/start) или командой /stop.')
TEXT_SUB_NOT = 'Подписка не оформлена. Подписаться: /start, затем «Подписаться на новости».'
TEXT_UNSUB_DONE = ('Вы отписались от новостей баров «Культура» — сообщения больше не придут. '
                   'Телефон, если вы им делились, удалён. Подписаться снова: /start, '
                   'затем «Подписаться на новости».')
TEXT_UNSUB_NOT = 'Вы и так не подписаны на новости. Подписаться: /start, затем «Подписаться на новости».'
# Запись гостей выключена (signup_enabled_now) — без приглашения подписаться снова.
TEXT_UNSUB_DONE_CLOSED = ('Вы отписались от новостей баров «Культура» — сообщения больше не придут. '
                          'Телефон, если вы им делились, удалён.')
TEXT_UNSUB_NOT_CLOSED = 'Вы и так не подписаны на новости.'

TEXT_REV_BAR = 'О каком баре отзыв?'
TEXT_REV_RATING = '{bar}: оцените визит от 1 до 5, где 5 — отлично.'
TEXT_REV_TEXT = ('{bar}, оценка {rating} из 5.\n'
                 'Теперь напишите отзыв одним сообщением — или нажмите «Отправить без текста», '
                 'чтобы оставить только оценку. Вместе с отзывом сохраним ваше имя и ник в Telegram, '
                 'чтобы при необходимости связаться с вами.')
TEXT_REV_TEXT_ONLY = ('Бот сохраняет только текст. Напишите отзыв одним сообщением или нажмите '
                      '«Отправить без текста» в сообщении выше.')
TEXT_REV_SAVED_HEAD = '{bar}, оценка {rating} из 5.'
TEXT_REV_THANKS = 'Спасибо за отзыв! Его прочитает команда «Культуры».'
TEXT_REV_DUPLICATE = 'Этот отзыв уже сохранён. Спасибо!'
TEXT_REV_CANCELLED = 'Отзыв отменён.'
TEXT_REV_EXPIRED = ('Время на отзыв вышло ({duration}), этот текст не сохранён. '
                    'Чтобы оставить отзыв: /start, затем «Оставить отзыв».')
TEXT_REV_STALE = 'Этот отзыв уже сохранён или время на него вышло. Новый: /start, затем «Оставить отзыв».'
TEXT_REV_LIMIT = 'Сегодня вы уже оставили {count} — спасибо! Новый отзыв можно будет оставить завтра.'
TEXT_REV_FAILED = 'Не получилось сохранить отзыв — попробуйте позже: /start, затем «Оставить отзыв».'
TEXT_ERROR = 'Что-то пошло не так — попробуйте ещё раз позже.'
TEXT_TAPLIST_ERROR = 'Не удалось получить данные о кранах. Попробуйте позже.'
# Кнопка «Согласен» со старой версией текста согласия: показываем текущий текст заново.
TEXT_CONSENT_UPDATED = 'Текст согласия обновился — прочитайте его, пожалуйста, ещё раз.'
# Непонятный текст в личке (нет шага диалога): подсказка вместо молчания. После
# перезапуска воркера набранный отзыв иначе пропадал бы без ответа.
TEXT_HINT = 'Я бот баров «Культура». Что на кранах — /start, оставить отзыв — /review, новости — /subscribe.'
TEXT_HINT_CLOSED = 'Я бот баров «Культура». Что на кранах — /start.'

REMOVE_KEYBOARD = {"remove_keyboard": True}

_started = False
_thread_lock = threading.Lock()
_lock_handle = None


class WebhookConflict(Exception):
    """Telegram отклонил getUpdates, потому что на боте висит webhook."""


def _polling_disabled() -> bool:
    return os.environ.get('TAPLIST_POLLING', '1').lower() in ('0', 'false', 'off', 'no')


def command_name(text) -> str:
    """'/start@bot payload' -> 'start'; не команда -> ''. Текст из одних пробелов
    (в том числе неразрывный и «широкий» U+3000) — не команда, а не IndexError."""
    if not text:
        return ''
    parts = str(text).split()
    if not parts:
        return ''
    token = parts[0]
    if not token.startswith('/'):
        return ''
    return token[1:].split('@', 1)[0].lower()


def _start_payload(text) -> str:
    """Параметр ссылки t.me/<бот>?start=<параметр>: второе слово после /start."""
    parts = str(text or '').strip().split()
    return parts[1].strip().lower() if len(parts) > 1 else ''


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Русское склонение по числу: 1 отзыв, 2 отзыва, 5 отзывов, 21 отзыв, 11 отзывов."""
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


# ----------------------------------------------------------------- клавиатуры

def bar_keyboard() -> dict:
    rows = [
        [{"text": name, "callback_data": "taplist_" + bar_id}]
        for bar_id, name in BAR_NAMES.items()
    ]
    rows.append([{"text": "Все бары", "callback_data": "taplist_all"}])
    return {"inline_keyboard": rows}


def menu_keyboard(subscribed: bool = False, guest_buttons: bool = True, signup: bool = True) -> dict:
    """Меню кранов; в личном чате ниже — подписка (или отписка) и отзыв.

    signup=False (запись гостей выключена): только краны, но подписанному остаётся
    «Отписаться от новостей» — текст согласия обещает эту кнопку в меню.
    """
    keyboard = bar_keyboard()
    if guest_buttons:
        rows = keyboard["inline_keyboard"]
        if subscribed:
            rows.append([{"text": BTN_UNSUBSCRIBE, "callback_data": CB_SUB_STOP}])
        elif signup:
            rows.append([{"text": BTN_SUBSCRIBE, "callback_data": CB_SUB_START}])
        if signup:
            rows.append([{"text": BTN_REVIEW, "callback_data": CB_REV_START}])
    return keyboard


def consent_keyboard() -> dict:
    """«Согласен» несёт версию текста согласия: нажатие под старым текстом не подписывает,
    а показывает текущий текст заново (гость соглашается с тем, что прочитал)."""
    return {"inline_keyboard": [[{"text": BTN_AGREE, "callback_data": CB_SUB_AGREE + ':' + gsubs.CONSENT_VERSION}],
                                [{"text": BTN_LATER, "callback_data": CB_SUB_LATER}]]}


def _known_bars(bars) -> list:
    """Выбор баров для кнопок: только известные ключи, все четыре -> [] (как normalize_bars)."""
    chosen = [k for k in gsubs.BAR_KEYS if k in (bars or [])]
    return [] if len(chosen) == len(gsubs.BAR_KEYS) else chosen


def bars_select_keyboard(bars) -> dict:
    """Выбор баров подписки: отмеченные — с «✓ »; ни одного — отмечено «Все бары»."""
    chosen = _known_bars(bars)
    mask = gsubs.bars_to_mask(chosen)
    rows = [[{"text": (MARK_ON if key in chosen else '') + gsubs.BAR_NAMES[key],
              "callback_data": "sb:%d:%d" % (mask, i)}]
            for i, key in enumerate(gsubs.BAR_KEYS)]
    rows.append([{"text": (MARK_ON if not chosen else '') + BTN_ALL_BARS, "callback_data": "sb:%d:a" % mask}])
    rows.append([{"text": BTN_DONE, "callback_data": "sb:%d:ok" % mask}])
    return {"inline_keyboard": rows}


def phone_keyboard() -> dict:
    """Кнопка Telegram «Поделиться телефоном» (request_contact) и «Пропустить»."""
    return {"keyboard": [[{"text": BTN_SHARE_PHONE, "request_contact": True}], [{"text": BTN_SKIP}]],
            "resize_keyboard": True, "one_time_keyboard": True}


def review_bar_keyboard() -> dict:
    rows = [[{"text": gsubs.BAR_NAMES[key], "callback_data": "rv:b:%d" % i}]
            for i, key in enumerate(gsubs.BAR_KEYS)]
    rows.append([{"text": BTN_CANCEL, "callback_data": "rv:x"}])
    return {"inline_keyboard": rows}


def rating_keyboard(bar_index: int) -> dict:
    return {"inline_keyboard": [
        [{"text": str(n), "callback_data": "rv:r:%d:%d" % (bar_index, n)} for n in range(1, 6)],
        [{"text": BTN_CANCEL, "callback_data": "rv:x"}],
    ]}


def review_text_keyboard(bar_index: int, rating: int) -> dict:
    return {"inline_keyboard": [
        [{"text": BTN_NO_TEXT, "callback_data": "rv:s:%d:%d" % (bar_index, rating)}],
        [{"text": BTN_CANCEL, "callback_data": "rv:x"}],
    ]}


def sub_done_text(bars) -> str:
    return TEXT_SUB_DONE.format(bars=gsubs.bars_label(bars))


# ----------------------------------------------------------------- план (чистые функции)

def _msg(chat_id, text, markup=None) -> dict:
    action = {"op": "say", "chat_id": chat_id, "text": text}
    if markup is not None:
        action["markup"] = markup
    return action


def _user_fields(sender) -> dict:
    sender = sender or {}
    return {'user_id': sender.get('id'), 'username': sender.get('username'),
            'first_name': sender.get('first_name'), 'last_name': sender.get('last_name')}


def _small_int(text, lo: int, hi: int) -> Optional[int]:
    """Целое lo..hi из callback_data (только ASCII-цифры); иначе None."""
    text = str(text or '')
    if not text.isascii() or not text.isdigit():
        return None
    n = int(text)
    return n if lo <= n <= hi else None


def _bar_by_index(text) -> Optional[str]:
    i = _small_int(text, 0, len(gsubs.BAR_KEYS) - 1)
    return None if i is None else gsubs.BAR_KEYS[i]


def _live(dialog) -> Optional[dict]:
    """Действующее состояние диалога (истёкшее — None)."""
    return dialog if dialog and not dialog.get('expired') else None


def update_chat_id(update):
    """id чата апдейта (сообщение, кнопка, my_chat_member) или None."""
    update = update or {}
    if update.get('callback_query'):
        return ((update['callback_query'].get('message') or {}).get('chat') or {}).get('id')
    for key in ('message', 'my_chat_member'):
        if update.get(key):
            return (update[key].get('chat') or {}).get('id')
    return None


def _menu(chat_id, signup: bool) -> dict:
    """Действие «меню»; при выключенной записи гостей — с пометкой signup False."""
    action = {"op": "menu", "chat_id": chat_id}
    if not signup:
        action["signup"] = False
    return action


def plan_update(update, dialog=None, signup: bool = True) -> list:
    """Что ответить на один апдейт. Сеть, база, краны и часы сюда не входят.

    dialog — состояние диалога этого чата (DialogStore.get): None — нет; с ключом
    expired — таймаут только что истёк. Без dialog поведение кранов — как раньше.
    signup — включена ли запись гостей (BotContext.signup_enabled): выключена —
    входы в подписку и отзыв (кнопки меню, /subscribe, /review, ссылки ?start=…)
    ведут в меню кранов; /stop и «Отписаться» работают, начатые шаги доходят до конца.
    Действия ('op'):
        ack {callback_id}                         подтвердить нажатие кнопки
        menu {chat_id[, signup: False]}           меню кранов (+ подписка и отзыв в личке)
        taplist {chat_id, bar_id}                 краны бара (None — все бары)
        say {chat_id, text[, markup]}             сообщение без разметки
        sub_offer {chat_id}                       текст согласия, у подписанного — выбор баров
        sub_agree {chat_id, user}                 «Согласен»: подписать, показать выбор баров
        sub_bars {chat_id, message_id, bars}      перерисовать отметки баров
        sub_bars_done {chat_id, message_id, bars} «Готово»: сохранить бары, спросить телефон
        sub_phone {chat_id, phone}                контакт гостя — его собственный номер
        sub_phone_skip {chat_id}                  «Пропустить» телефон
        unsubscribe {chat_id}                     /stop, «Отписаться от новостей»
        blocked / unblocked {chat_id}             гость заблокировал / разблокировал бота
        rev_start {chat_id}                       выбор бара отзыва
        rev_bar {chat_id, message_id, bar}        оценка (message_id None — новым сообщением)
        rev_rating {chat_id, message_id, bar, rating}  просьба написать текст
        rev_save {chat_id, message_id, prompt_message_id, bar, rating, text, date, user}
        rev_cancel {chat_id, message_id}
        dialog_set {chat_id, state} / dialog_clear {chat_id}
    """
    update = update or {}
    member = update.get('my_chat_member')
    if member:
        return _plan_member(member)
    callback = update.get('callback_query')
    if callback:
        return _plan_callback(callback, dialog, signup)
    return _plan_message(update.get('message') or {}, dialog, signup)


def _plan_member(member) -> list:
    chat = member.get('chat') or {}
    chat_id = chat.get('id')
    if chat.get('type') != 'private' or not chat_id:
        return []
    status = (member.get('new_chat_member') or {}).get('status')
    if status == 'kicked':
        return [{"op": "blocked", "chat_id": chat_id}]
    if status == 'member':
        return [{"op": "unblocked", "chat_id": chat_id}]
    return []


def _plan_callback(callback, dialog, signup: bool = True) -> list:
    actions = []
    if callback.get('id'):
        actions.append({"op": "ack", "callback_id": callback.get('id')})
    data = callback.get('data') or ''
    message = callback.get('message') or {}
    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    if chat_id and data.startswith('taplist_'):
        bar_id = data.replace('taplist_', '', 1)
        actions.append({
            "op": "taplist",
            "chat_id": chat_id,
            "bar_id": None if bar_id == 'all' else bar_id,
        })
        return actions
    guest = data.split(':', 1)[0] in _GUEST_CALLBACKS or data.startswith('sb:') or data.startswith('rv:')
    if not chat_id or not guest:
        return actions
    if chat.get('type') != 'private':
        actions.append(_msg(chat_id, TEXT_PRIVATE_ONLY))
        return actions
    user = _user_fields(callback.get('from'))
    return actions + _plan_guest_button(data, chat_id, message.get('message_id'), user, dialog, signup)


def _clear(dialog, chat_id) -> list:
    return [{"op": "dialog_clear", "chat_id": chat_id}] if dialog else []


def _plan_guest_button(data, chat_id, message_id, user, dialog, signup: bool = True) -> list:
    live = _live(dialog)
    flow = (live or {}).get('flow')
    if data in (CB_SUB_START, CB_REV_START) and not signup:
        # Запись гостей выключена: старая кнопка входа ведёт в меню кранов.
        return [_menu(chat_id, signup)]
    agree = data == CB_SUB_AGREE or data.startswith(CB_SUB_AGREE + ':')
    if not signup and ((agree and flow != 'consent')
                       or (data.startswith('rv:') and flow not in ('review', 'review_text'))):
        # Выключено: «Согласен» и кнопки отзыва — только из живого диалога этого чата
        # (начатого при включённом). Старые и подделанные кнопки ведут в меню кранов.
        return [_menu(chat_id, signup)]
    if data == CB_SUB_START:
        return [{"op": "sub_offer", "chat_id": chat_id}]
    if agree:
        version = data.split(':', 1)[1] if ':' in data else ''
        if version != gsubs.CONSENT_VERSION:
            # Кнопка под старым текстом согласия: не подписывать, показать текущий текст.
            return [{"op": "sub_offer", "chat_id": chat_id, "outdated": True}]
        return [{"op": "sub_agree", "chat_id": chat_id, "user": user, "version": version}]
    if data == CB_SUB_LATER:
        return [_msg(chat_id, TEXT_SUB_LATER)]
    if data == CB_SUB_STOP:
        return _clear(dialog, chat_id) + [{"op": "unsubscribe", "chat_id": chat_id}]
    if data == CB_REV_START:
        return _clear(dialog, chat_id) + [{"op": "rev_start", "chat_id": chat_id}]
    parts = data.split(':')
    if parts[0] == 'sb' and len(parts) == 3:
        mask = _small_int(parts[1], 0, (1 << len(gsubs.BAR_KEYS)) - 1)
        if mask is None:
            return []
        current = gsubs.mask_to_bars(mask)
        act = parts[2]
        if act == 'ok':
            return [{"op": "sub_bars_done", "chat_id": chat_id, "message_id": message_id, "bars": current}]
        if act == 'a':
            chosen = []
        else:
            bar = _bar_by_index(act)
            if bar is None:
                return []
            chosen = gsubs.toggle_bar(current, bar)
        if chosen == current:
            return []      # «Все бары» при уже выбранных всех — перерисовывать нечего
        return [{"op": "sub_bars", "chat_id": chat_id, "message_id": message_id, "bars": chosen}]
    if parts[0] != 'rv':
        return []
    if parts[1:] == ['x']:
        return _clear(dialog, chat_id) + [{"op": "rev_cancel", "chat_id": chat_id, "message_id": message_id}]
    if len(parts) == 3 and parts[1] == 'b':
        bar = _bar_by_index(parts[2])
        if bar is None:
            return []
        return [{"op": "rev_bar", "chat_id": chat_id, "message_id": message_id, "bar": bar}]
    if len(parts) != 4 or parts[1] not in ('r', 's'):
        return []
    bar = _bar_by_index(parts[2])
    rating = _small_int(parts[3], 1, 5)
    if bar is None or rating is None:
        return []
    if parts[1] == 'r':
        state = {"flow": "review_text", "bar": bar, "rating": rating, "prompt_message_id": message_id}
        return [{"op": "rev_rating", "chat_id": chat_id, "message_id": message_id, "bar": bar, "rating": rating},
                {"op": "dialog_set", "chat_id": chat_id, "state": state}]
    # «Отправить без текста»: только кнопка того самого сообщения из живого диалога.
    if not live or live.get('flow') != 'review_text' or live.get('prompt_message_id') != message_id:
        return [_msg(chat_id, TEXT_REV_STALE)]
    return [{"op": "rev_save", "chat_id": chat_id, "message_id": message_id, "prompt_message_id": message_id,
             "bar": live['bar'], "rating": live['rating'], "text": '', "date": None, "user": user},
            {"op": "dialog_clear", "chat_id": chat_id}]


def _plan_message(message, dialog, signup: bool = True) -> list:
    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    if not chat_id:
        return []
    private = chat.get('type') == 'private'
    live = _live(dialog)
    flow = (live or {}).get('flow')
    if message.get('contact') is not None:
        return _plan_contact(message, chat_id) if private else []
    text = message.get('text') or ''
    cmd = command_name(text)
    if cmd:
        return _plan_command(cmd, text, chat_id, private, dialog, flow, signup)
    if not private:
        return []
    if flow == 'review_text':
        body = text.strip()
        if not body:
            return [_msg(chat_id, TEXT_REV_TEXT_ONLY)]
        return [{"op": "rev_save", "chat_id": chat_id, "message_id": message.get('message_id'),
                 "prompt_message_id": live.get('prompt_message_id'), "bar": live['bar'],
                 "rating": live['rating'], "text": body, "date": message.get('date'),
                 "user": _user_fields(message.get('from'))},
                {"op": "dialog_clear", "chat_id": chat_id}]
    skip = text.strip().lower() == BTN_SKIP.lower()
    if flow == 'sub_phone':
        if skip:
            return [{"op": "sub_phone_skip", "chat_id": chat_id}]
        return [_msg(chat_id, TEXT_SUB_PHONE_HINT)]
    if skip and dialog and dialog.get('expired') and dialog.get('flow') == 'sub_phone':
        # Кнопка «Пропустить» нажата после таймаута: закрыть шаг и убрать кнопку телефона.
        return [{"op": "sub_phone_skip", "chat_id": chat_id}]
    if dialog and dialog.get('expired') and dialog.get('flow') == 'review_text' and text.strip():
        minutes = int(DIALOG_TIMEOUT.total_seconds() // 60)
        duration = '%d %s' % (minutes, _plural(minutes, 'минута', 'минуты', 'минут'))
        return [_msg(chat_id, TEXT_REV_EXPIRED.format(duration=duration))]
    # Бот ничего не ждёт от гостя — подсказка вместо молчания.
    return [_msg(chat_id, TEXT_HINT if signup else TEXT_HINT_CLOSED)]


def _plan_contact(message, chat_id) -> list:
    """Контакт принимается, только если он свой: user_id контакта = отправитель
    (кнопка request_contact присылает именно так; чужая карточка контакта — нет)."""
    contact = message.get('contact') or {}
    sender = (message.get('from') or {}).get('id')
    if not sender or contact.get('user_id') != sender:
        return [_msg(chat_id, TEXT_SUB_PHONE_NOT_OWN)]
    return [{"op": "sub_phone", "chat_id": chat_id, "phone": str(contact.get('phone_number') or '')}]


def _plan_deep_link(payload, chat_id) -> Optional[list]:
    """Параметр ссылки для QR-кода -> действия; неизвестный -> None (обычное меню)."""
    if payload == 'subscribe':
        return [{"op": "sub_offer", "chat_id": chat_id}]
    if payload == 'review':
        return [{"op": "rev_start", "chat_id": chat_id}]
    if payload.startswith('review_') and payload[len('review_'):] in gsubs.BAR_KEYS:
        return [{"op": "rev_bar", "chat_id": chat_id, "message_id": None, "bar": payload[len('review_'):]}]
    return None


def _plan_command(cmd, text, chat_id, private, dialog, flow, signup: bool = True) -> list:
    pre = _clear(dialog, chat_id)
    if flow == 'sub_phone' and cmd not in ('stop', 'unsubscribe'):
        pre = [{"op": "sub_phone_skip", "chat_id": chat_id}] + pre
    if cmd in ('start', 'help', 'taplist'):
        payload = _start_payload(text) if cmd == 'start' else ''
        deep = _plan_deep_link(payload, chat_id) if (private and payload and signup) else None
        return pre + (deep if deep is not None else [_menu(chat_id, signup)])
    if cmd in ('taplist1', 'taplist2', 'taplist3', 'taplist4'):
        return pre + [{"op": "taplist", "chat_id": chat_id, "bar_id": "bar" + cmd[-1]}]
    if cmd == 'taplistall':
        return pre + [{"op": "taplist", "chat_id": chat_id, "bar_id": None}]
    if cmd in ('stop', 'unsubscribe'):
        # Отписка работает всегда, даже при выключенной записи гостей.
        if not private:
            return pre + [_msg(chat_id, TEXT_PRIVATE_ONLY)]
        return pre + [{"op": "unsubscribe", "chat_id": chat_id}]
    entry_ops = {'subscribe': 'sub_offer', 'news': 'sub_offer', 'review': 'rev_start', 'отзыв': 'rev_start'}
    if cmd in entry_ops:
        if not signup:
            return pre + [_menu(chat_id, signup)]
        if not private:
            return pre + [_msg(chat_id, TEXT_PRIVATE_ONLY)]
        return pre + [{"op": entry_ops[cmd], "chat_id": chat_id}]
    return pre + [_menu(chat_id, signup)]


# ----------------------------------------------------------------- состояние диалога

class DialogStore:
    """Состояние диалога по чатам в памяти процесса (правила — докстринг модуля).

    get() отдаёт копию; шаг старше timeout удаляется и отдаётся один раз с expired=True
    (ответить «время вышло»); записи старше forget забываются молча.
    """

    def __init__(self, timeout: timedelta = DIALOG_TIMEOUT, forget: timedelta = DIALOG_FORGET):
        self.timeout = timeout
        self.forget = forget
        self._items = {}
        self._lock = threading.Lock()

    def get(self, chat_id, now: datetime) -> Optional[dict]:
        with self._lock:
            for key in [k for k, (_, at) in self._items.items() if now - at > self.forget]:
                del self._items[key]
            item = self._items.get(chat_id)
            if item is None:
                return None
            state, at = item
            if now - at > self.timeout:
                del self._items[chat_id]
                return dict(state, expired=True)
            return dict(state)

    def set(self, chat_id, state: dict, now: datetime) -> None:
        with self._lock:
            self._items[chat_id] = (dict(state), now)

    def clear(self, chat_id) -> None:
        with self._lock:
            self._items.pop(chat_id, None)


DIALOGS = DialogStore()


class PersistentDialogStore:
    """Состояние диалога в guest_subscribers.db (таблица dialogs) — переживает перезапуск
    воркера (--max-requests, деплой): набранный отзыв больше не пропадает молча.

    Те же правила сроков, что у DialogStore: шаг старше timeout отдаётся один раз с
    expired=True и удаляется; старше forget — удаляется молча (чистка не чаще раза в
    SWEEP_SEC). База не отвечает — запасной DialogStore в памяти: бот продолжает
    отвечать, пока диск не вернётся (сбой пишется в лог).
    """
    SWEEP_SEC = 60

    def __init__(self, subs_getter, timeout: timedelta = DIALOG_TIMEOUT, forget: timedelta = DIALOG_FORGET):
        self._subs = subs_getter            # () -> core.guest_subscribers.SubscriberStore
        self.timeout = timeout
        self.forget = forget
        self._fallback = DialogStore(timeout, forget)
        self._last_sweep = None

    def _sweep(self, subs, now: datetime) -> None:
        ts = now.timestamp()
        if self._last_sweep is not None and ts - self._last_sweep < self.SWEEP_SEC:
            return
        self._last_sweep = ts
        subs.dialog_sweep(ts - self.forget.total_seconds())

    def get(self, chat_id, now: datetime) -> Optional[dict]:
        try:
            subs = self._subs()
            self._sweep(subs, now)
            item = subs.dialog_get(chat_id)
        except Exception as exc:  # noqa: BLE001 — диск или база: работаем из памяти
            print(f"[TAPLIST-POLL] диалоги в базе не читаются: {exc!r}")
            return self._fallback.get(chat_id, now)
        if item is None:
            return self._fallback.get(chat_id, now)
        state, ts = item
        if now.timestamp() - ts > self.timeout.total_seconds():
            try:
                subs.dialog_clear(chat_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[TAPLIST-POLL] диалог не удалён: {exc!r}")
            return dict(state, expired=True)
        return dict(state)

    def set(self, chat_id, state: dict, now: datetime) -> None:
        try:
            self._subs().dialog_set(chat_id, dict(state), now.timestamp())
            self._fallback.clear(chat_id)
        except Exception as exc:  # noqa: BLE001
            print(f"[TAPLIST-POLL] диалог не записан в базу, держим в памяти: {exc!r}")
            self._fallback.set(chat_id, state, now)

    def clear(self, chat_id) -> None:
        self._fallback.clear(chat_id)
        try:
            self._subs().dialog_clear(chat_id)
        except Exception as exc:  # noqa: BLE001
            print(f"[TAPLIST-POLL] диалог не удалён: {exc!r}")


def signup_enabled_now() -> bool:
    """Выключатель записи гостей: подписка на новости и отзывы через бота.

    Источник — core.content_channels.bot_signup_enabled() (владелец включает на
    странице контент-плана). Читается на каждый апдейт — включение и выключение
    действуют без перезапуска. Модуля или функции нет, любой сбой -> False:
    новое по умолчанию выключено (решение владельца). Выключено: в меню только
    краны; /subscribe, /review и ссылки ?start=subscribe|review… ведут в меню;
    /stop и «Отписаться от новостей» работают всегда; начатый при включённом
    диалог (согласие, бары, телефон, отзыв) можно закончить.
    """
    try:
        from core.content_channels import bot_signup_enabled
    except Exception:  # noqa: BLE001 — модуля или функции ещё нет: выключено
        return False
    try:
        return bool(bot_signup_enabled())
    except Exception as exc:  # noqa: BLE001 — сбой настроек: выключено, бот отвечает кранами
        print(f"[TAPLIST-POLL] выключатель записи гостей не читается: {exc!r}")
        return False


class BotContext:
    """Зависимости исполнителя. По умолчанию — боевые: api_call с токеном бота, общие
    хранилища подписчиков и отзывов, состояние диалога в базе подписчиков
    (PersistentDialogStore), московские часы, выключатель записи гостей
    (signup_enabled_now), уведомление владельца об отзыве
    (core.review_notify.notify_review_in_background) и подбор пропущенных
    (notify_pending_in_background). В тестах всё подменяется: api(method, payload) ->
    dict, subs, reviews, dialogs, clock, signup() -> bool, notify(review_id), sweep()."""

    def __init__(self, token=None, *, api=None, subs=None, reviews=None, dialogs=None, clock=None,
                 signup=None, notify=None, sweep=None):
        self.token = token
        self._api = api
        self._subs = subs
        self._reviews = reviews
        self._dialogs = dialogs
        self._clock = clock or msk_time.now
        self._signup = signup
        self._notify = notify
        self._sweep = sweep

    @property
    def dialogs(self):
        if self._dialogs is None:
            self._dialogs = PersistentDialogStore(lambda: self.subs)
        return self._dialogs

    @dialogs.setter
    def dialogs(self, value):
        self._dialogs = value

    def sweep_reviews(self) -> None:
        """Подбор отзывов из бота без уведомления (цикл опроса зовёт раз в 10 минут)."""
        if self._sweep is not None:
            self._sweep()
            return
        from core.review_notify import notify_pending_in_background
        notify_pending_in_background()

    def signup_enabled(self) -> bool:
        """Включена ли запись гостей (подписка и отзывы); любой сбой — выключена."""
        try:
            return bool((self._signup or signup_enabled_now)())
        except Exception:  # noqa: BLE001
            return False

    def notify_review(self, review_id) -> None:
        """Сообщить владельцу о новом отзыве сразу (фоновый поток — гость не ждёт)."""
        if self._notify is not None:
            self._notify(review_id)
            return
        from core.review_notify import notify_review_in_background
        notify_review_in_background(review_id)

    def call(self, method, payload=None, timeout=20):
        if self._api is not None:
            return self._api(method, payload or {})
        from core.open_check_telegram import api_call
        return api_call(method, payload, timeout=timeout, token=self.token)

    @property
    def subs(self):
        if self._subs is None:
            self._subs = gsubs.get_store()
        return self._subs

    @property
    def reviews(self):
        if self._reviews is None:
            from core.guest_reviews import get_review_store
            self._reviews = get_review_store()
        return self._reviews

    def now(self) -> datetime:
        return self._clock()


# ----------------------------------------------------------------- краны

def consume_batch(data, offset, feed, on_error=None):
    """Разобрать один ответ getUpdates.

    offset двигается даже если feed упал: один битый апдейт не должен
    застрять в очереди навсегда. 409 — WebhookConflict, offset не меняется.
    Не-ok ответ (кроме 409) возвращает прежний offset.
    """
    if not data or not data.get('ok'):
        if data and data.get('error_code') == 409:
            raise WebhookConflict(data.get('description') or 'webhook is active')
        return offset
    for upd in data.get('result') or []:
        offset = int(upd['update_id']) + 1
        try:
            feed(upd)
        except Exception as exc:
            if on_error is None:
                raise
            on_error(exc)
    return offset


def _taps_path() -> str:
    if os.path.isdir('/kultura'):
        return '/kultura/taps_data.json'
    return os.path.join(_BASE_DIR, 'data', 'taps_data.json')


def _render_taplist(bar_id, manager) -> str:
    """Краны бара для гостя (HTML): реестр Untappd и строки «Таплиста пятницы».
    Сбой данных (реестр, файл кранов) — короткое извинение, а не молчание."""
    from core import taplist_post
    try:
        return taplist_post.bar_message_html(manager, bar_id, BAR_NAMES.get(bar_id, 'Бар'))
    except Exception as exc:  # noqa: BLE001 — сбой данных не должен ронять бота
        print(f"[TAPLIST-POLL] таплист {bar_id} не собран: {exc!r}")
        return TEXT_TAPLIST_ERROR


# ----------------------------------------------------------------- исполнение

def _scrub_text(exc, token) -> str:
    try:
        from core.open_check_telegram import _scrub
        return _scrub(exc, token)
    except Exception:  # noqa: BLE001 — логирование не должно падать
        return type(exc).__name__


def _log_fail(method, chat_id, data) -> None:
    if not data or not data.get('ok'):
        print(f"[TAPLIST-POLL] {method} fail chat={chat_id} {(data or {}).get('error_code')} "
              f"{(data or {}).get('description')}")


def _send(ctx, chat_id, text, markup=None) -> None:
    """Сообщение кранов и меню (как раньше: HTML, если в тексте есть разметка)."""
    payload = {
        "chat_id": chat_id,
        "text": text or "Нет данных",
        "disable_web_page_preview": True,
    }
    if '<' in (text or ''):
        payload['parse_mode'] = 'HTML'
    if markup is not None:
        payload['reply_markup'] = markup
    _log_fail('sendMessage', chat_id, ctx.call('sendMessage', payload))


def _say(ctx, chat_id, text, markup=None):
    """Сообщение диалога: всегда без parse_mode — текст как есть."""
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if markup is not None:
        payload["reply_markup"] = markup
    data = ctx.call('sendMessage', payload)
    _log_fail('sendMessage', chat_id, data)
    return data


def _edit(ctx, chat_id, message_id, text, markup=None):
    """Заменить текст сообщения бота (без markup кнопки у сообщения исчезают); нет
    message_id — отправить новым сообщением."""
    if not message_id:
        return _say(ctx, chat_id, text, markup)
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "disable_web_page_preview": True}
    if markup is not None:
        payload["reply_markup"] = markup
    data = ctx.call('editMessageText', payload)
    _log_fail('editMessageText', chat_id, data)
    return data


def _edit_markup(ctx, chat_id, message_id, markup):
    """Заменить только кнопки сообщения бота (отметки баров)."""
    if not message_id:
        return None
    data = ctx.call('editMessageReplyMarkup', {"chat_id": chat_id, "message_id": message_id,
                                               "reply_markup": markup})
    _log_fail('editMessageReplyMarkup', chat_id, data)
    return data


def _is_private_chat_id(chat_id) -> bool:
    """У личного чата id положительный (= id пользователя), у групп и каналов — отрицательный."""
    try:
        return int(chat_id) > 0
    except (TypeError, ValueError):
        return False


def _send_menu(ctx, chat_id, signup: bool = True) -> None:
    private = _is_private_chat_id(chat_id)
    subscribed = False
    if private:
        try:
            subscribed = ctx.subs.is_subscribed(chat_id)
        except Exception as exc:  # noqa: BLE001 — меню кранов не зависит от базы подписчиков
            print(f"[TAPLIST-POLL] подписчики не читаются: {_scrub_text(exc, ctx.token)}")
    _send(ctx, chat_id, MENU_TEXT, menu_keyboard(subscribed, guest_buttons=private, signup=signup))


def _msk_minute(unix_ts) -> Optional[str]:
    """Время сообщения Telegram (unix, UTC) -> 'YYYY-MM-DDTHH:MM' по Москве; нет -> None."""
    if unix_ts is None or isinstance(unix_ts, bool):
        return None
    try:
        moment = datetime.fromtimestamp(int(unix_ts), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    from core.guest_reviews import fmt_dt, naive_msk
    return fmt_dt(naive_msk(moment))


def review_fields(action: dict, subscriber: Optional[dict], now: datetime) -> dict:
    """Поля отзыва для ReviewStore.add из действия rev_save (правила — докстринг модуля).

    Имя автора — имя и фамилия из профиля Telegram (обрезка до MAX_AUTHOR_LEN);
    телефон — только у подписанного, который им делился ('+7…', чтобы набирался).
    """
    from core.guest_reviews import MAX_AUTHOR_LEN, MAX_TEXT_LEN, fmt_dt, naive_msk
    user = action.get('user') or {}
    chat_id = action['chat_id']
    username = str(user.get('username') or '').strip().lstrip('@')
    phone = ''
    if subscriber and subscriber.get('subscribed') and subscriber.get('phone'):
        phone = gsubs.phone_display(subscriber['phone'])
    author = ' '.join(str(p) for p in (user.get('first_name'), user.get('last_name')) if p)
    message_id = action.get('message_id') or action.get('prompt_message_id')
    return {
        'source': 'bot',
        'bar': action['bar'],
        'rating': action['rating'],
        'text': str(action.get('text') or '').strip()[:MAX_TEXT_LEN],
        'author': ' '.join(author.split())[:MAX_AUTHOR_LEN],
        'created_at': _msk_minute(action.get('date')) or fmt_dt(naive_msk(now)),
        'guest': {'telegram': '@' + username if username else str(chat_id), 'phone': phone},
        'external_id': 'tg:%s:%s' % (chat_id, message_id),
    }


def reviews_today(reviews, chat_id, day: str) -> int:
    """Сколько отзывов из этого чата с датой day ('YYYY-MM-DD', по Москве)."""
    prefix = 'tg:%s:' % chat_id
    return sum(1 for r in reviews
               if r.get('source') == 'bot' and str(r.get('external_id') or '').startswith(prefix)
               and str(r.get('created_at') or '')[:10] == day)


def _review_limit_text(ctx, chat_id) -> str:
    """Текст «на сегодня хватит» или '' (лимит не достигнут или отзывы не читаются —
    тогда о сбое скажет само сохранение)."""
    from core.guest_reviews import naive_msk
    day = naive_msk(ctx.now()).strftime('%Y-%m-%d')
    try:
        count = reviews_today(ctx.reviews.all(), chat_id, day)
    except Exception as exc:  # noqa: BLE001
        print(f"[TAPLIST-POLL] отзывы не читаются: {_scrub_text(exc, ctx.token)}")
        return ''
    if count < REVIEW_DAILY_LIMIT:
        return ''
    word = _plural(count, 'отзыв', 'отзыва', 'отзывов')
    return TEXT_REV_LIMIT.format(count='%d %s' % (count, word))


def _op_say(ctx, a):
    _say(ctx, a['chat_id'], a['text'], a.get('markup'))


def _op_sub_offer(ctx, a):
    chat_id = a['chat_id']
    row = ctx.subs.get(chat_id)
    if row and row['subscribed']:
        _say(ctx, chat_id, TEXT_SUB_ALREADY.format(bars=gsubs.bars_label(row['bars'])),
             bars_select_keyboard(row['bars']))
        return
    text = gsubs.CONSENT_TEXT
    if a.get('outdated'):               # «Согласен» под старым текстом — показать текущий
        text = TEXT_CONSENT_UPDATED + '\n\n' + text
    _say(ctx, chat_id, text, consent_keyboard())
    # Живой шаг «согласие»: при выключенной записи «Согласен» принимается только из него.
    ctx.dialogs.set(chat_id, {"flow": "consent", "version": gsubs.CONSENT_VERSION}, ctx.now())


def _op_sub_agree(ctx, a):
    chat_id, user = a['chat_id'], a.get('user') or {}
    row = ctx.subs.subscribe(chat_id, user_id=user.get('user_id'), username=user.get('username'),
                             first_name=user.get('first_name'),
                             consent_version=a.get('version') or gsubs.CONSENT_VERSION)
    ctx.dialogs.clear(chat_id)          # согласие получено — шаг «согласие» закрыт
    _say(ctx, chat_id, TEXT_SUB_BARS, bars_select_keyboard(row['bars']))


def _op_sub_bars(ctx, a):
    _edit_markup(ctx, a['chat_id'], a.get('message_id'), bars_select_keyboard(a['bars']))


def _op_sub_bars_done(ctx, a):
    chat_id, bars = a['chat_id'], a['bars']
    if not ctx.subs.set_bars(chat_id, bars):
        _edit(ctx, chat_id, a.get('message_id'), TEXT_SUB_NOT)
        return
    _edit(ctx, chat_id, a.get('message_id'), TEXT_SUB_BARS_SAVED.format(bars=gsubs.bars_label(bars)))
    row = ctx.subs.get(chat_id) or {}
    if row.get('phone'):
        _say(ctx, chat_id, sub_done_text(row.get('bars')))
        return
    _say(ctx, chat_id, TEXT_SUB_PHONE, phone_keyboard())
    ctx.dialogs.set(chat_id, {"flow": "sub_phone"}, ctx.now())


def _op_sub_phone(ctx, a):
    chat_id = a['chat_id']
    ctx.dialogs.clear(chat_id)
    row = ctx.subs.get(chat_id)
    if not row or not row['subscribed']:
        _say(ctx, chat_id, TEXT_SUB_PHONE_NO_SUB, REMOVE_KEYBOARD)
        return
    try:
        # В контакте Telegram номер всегда с кодом страны: international=True.
        saved = ctx.subs.set_phone(chat_id, a.get('phone'), international=True)
    except ValueError:
        _say(ctx, chat_id, TEXT_SUB_PHONE_BAD, REMOVE_KEYBOARD)
        return
    if saved is None:
        _say(ctx, chat_id, TEXT_SUB_PHONE_NO_SUB, REMOVE_KEYBOARD)
        return
    _say(ctx, chat_id, TEXT_SUB_PHONE_SAVED + '\n\n' + sub_done_text(row['bars']), REMOVE_KEYBOARD)


def _op_sub_phone_skip(ctx, a):
    chat_id = a['chat_id']
    ctx.dialogs.clear(chat_id)
    row = ctx.subs.get(chat_id)
    text = sub_done_text(row['bars']) if row and row['subscribed'] else TEXT_SUB_NOT
    _say(ctx, chat_id, text, REMOVE_KEYBOARD)


def _op_unsubscribe(ctx, a):
    chat_id = a['chat_id']
    was = ctx.subs.unsubscribe(chat_id)
    # Бот обещает «телефон удалён» — стираем его и в отзывах гостя из бота.
    try:
        ctx.reviews.clear_guest_phone(chat_id)
    except Exception as exc:  # noqa: BLE001 — отписка важнее; сбой — в лог
        print(f"[TAPLIST-POLL] телефон в отзывах не стёрт: {_scrub_text(exc, ctx.token)}")
    if ctx.signup_enabled():
        text = TEXT_UNSUB_DONE if was else TEXT_UNSUB_NOT
    else:   # запись выключена: кнопки «Подписаться» в меню нет — не зовём к ней
        text = TEXT_UNSUB_DONE_CLOSED if was else TEXT_UNSUB_NOT_CLOSED
    _say(ctx, chat_id, text, REMOVE_KEYBOARD)


def _op_blocked(ctx, a):
    ctx.subs.mark_blocked(a['chat_id'])


def _op_unblocked(ctx, a):
    ctx.subs.mark_unblocked(a['chat_id'])


def _op_rev_start(ctx, a):
    chat_id = a['chat_id']
    limit = _review_limit_text(ctx, chat_id)
    if limit:
        _say(ctx, chat_id, limit)
        return
    _say(ctx, chat_id, TEXT_REV_BAR, review_bar_keyboard())
    ctx.dialogs.set(chat_id, {"flow": "review"}, ctx.now())


def _op_rev_bar(ctx, a):
    chat_id, bar = a['chat_id'], a['bar']
    if not a.get('message_id'):          # вход по ссылке review_<бар> — лимит ещё не проверялся
        limit = _review_limit_text(ctx, chat_id)
        if limit:
            _say(ctx, chat_id, limit)
            return
    _edit(ctx, chat_id, a.get('message_id'), TEXT_REV_RATING.format(bar=gsubs.BAR_NAMES[bar]),
          rating_keyboard(gsubs.BAR_KEYS.index(bar)))
    ctx.dialogs.set(chat_id, {"flow": "review", "bar": bar}, ctx.now())


def _op_rev_rating(ctx, a):
    bar, rating = a['bar'], a['rating']
    _edit(ctx, a['chat_id'], a.get('message_id'),
          TEXT_REV_TEXT.format(bar=gsubs.BAR_NAMES[bar], rating=rating),
          review_text_keyboard(gsubs.BAR_KEYS.index(bar), rating))


def _op_rev_cancel(ctx, a):
    _edit(ctx, a['chat_id'], a.get('message_id'), TEXT_REV_CANCELLED)


def _op_rev_save(ctx, a):
    from core.guest_reviews import ReviewConflict, ReviewStoreUnavailable
    chat_id = a['chat_id']
    limit = _review_limit_text(ctx, chat_id)
    if limit:
        _say(ctx, chat_id, limit)
        return
    try:
        subscriber = ctx.subs.get(chat_id)
    except Exception as exc:  # noqa: BLE001 — отзыв сохраняем и без данных подписки
        print(f"[TAPLIST-POLL] подписчик не читается: {_scrub_text(exc, ctx.token)}")
        subscriber = None
    fields = review_fields(a, subscriber, ctx.now())
    try:
        saved = ctx.reviews.add(fields, {'login': REVIEW_ADDED_BY}, origin='import')
    except ReviewConflict:
        _say(ctx, chat_id, TEXT_REV_DUPLICATE)
        return
    except (ReviewStoreUnavailable, ValueError, OSError) as exc:
        print(f"[TAPLIST-POLL] отзыв не сохранён: {_scrub_text(exc, ctx.token)}")
        _say(ctx, chat_id, TEXT_REV_FAILED)
        return
    head = TEXT_REV_SAVED_HEAD.format(bar=gsubs.BAR_NAMES[a['bar']], rating=a['rating'])
    prompt = a.get('prompt_message_id')
    if fields['text']:
        if prompt:
            _edit(ctx, chat_id, prompt, head)   # убрать «Отправить без текста» — второго отзыва не будет
        _say(ctx, chat_id, TEXT_REV_THANKS)
    else:
        _edit(ctx, chat_id, prompt or a.get('message_id'), head + '\n\n' + TEXT_REV_THANKS)
    # Владельцу — сразу, не дожидаясь утренней сверки (core/review_notify.notify_review_now).
    try:
        ctx.notify_review(saved['id'])
    except Exception as exc:  # noqa: BLE001 — уведомление не должно ломать ответ гостю
        print(f"[TAPLIST-POLL] уведомление об отзыве не запущено: {_scrub_text(exc, ctx.token)}")


def _op_dialog_set(ctx, a):
    ctx.dialogs.set(a['chat_id'], a.get('state') or {}, ctx.now())


def _op_dialog_clear(ctx, a):
    ctx.dialogs.clear(a['chat_id'])


_GUEST_OPS = {
    'say': _op_say,
    'sub_offer': _op_sub_offer,
    'sub_agree': _op_sub_agree,
    'sub_bars': _op_sub_bars,
    'sub_bars_done': _op_sub_bars_done,
    'sub_phone': _op_sub_phone,
    'sub_phone_skip': _op_sub_phone_skip,
    'unsubscribe': _op_unsubscribe,
    'blocked': _op_blocked,
    'unblocked': _op_unblocked,
    'rev_start': _op_rev_start,
    'rev_bar': _op_rev_bar,
    'rev_rating': _op_rev_rating,
    'rev_save': _op_rev_save,
    'rev_cancel': _op_rev_cancel,
    'dialog_set': _op_dialog_set,
    'dialog_clear': _op_dialog_clear,
}
# Служебные шаги: при сбое гостю ничего не пишем.
_SILENT_OPS = ('blocked', 'unblocked', 'dialog_set', 'dialog_clear')


def _execute(actions, token, manager, ctx=None) -> None:
    """Исполнить план. Сбой шага подписки или отзыва не ломает остальные шаги и краны:
    он пишется в лог, гость получает TEXT_ERROR."""
    ctx = ctx or BotContext(token)
    for action in actions:
        op = action.get('op')
        if op == 'ack':
            ctx.call('answerCallbackQuery', {'callback_query_id': action['callback_id']}, timeout=10)
            continue
        if op == 'menu':
            _send_menu(ctx, action['chat_id'], signup=action.get('signup', True))
            continue
        if op == 'taplist':
            from core.taps_manager import TapsManager
            # Краны читаем с диска на каждый запрос: страница кранов пишет файл,
            # а этот процесс живёт сутками.
            manager = TapsManager(data_file=_taps_path())
            bar_id = action.get('bar_id')
            targets = list(BAR_NAMES) if bar_id is None else [bar_id]
            for bid in targets:
                _send(ctx, action['chat_id'], _render_taplist(bid, manager))
            continue
        handler = _GUEST_OPS.get(op)
        if handler is None:
            continue
        try:
            handler(ctx, action)
        except Exception as exc:  # noqa: BLE001 — один сбойный шаг не должен ронять бота
            print(f"[TAPLIST-POLL] {op} failed: {_scrub_text(exc, ctx.token)}")
            if op not in _SILENT_OPS and action.get('chat_id'):
                _say(ctx, action['chat_id'], TEXT_ERROR)


def _private_sender(update):
    """(chat_id, профиль отправителя) для сообщения или кнопки в личном чате, иначе None."""
    update = update or {}
    callback = update.get('callback_query')
    if callback:
        chat = (callback.get('message') or {}).get('chat') or {}
        sender = callback.get('from')
    else:
        message = update.get('message') or {}
        chat = message.get('chat') or {}
        sender = message.get('from')
    if chat.get('type') != 'private' or not chat.get('id'):
        return None
    return chat['id'], _user_fields(sender)


def _touch(ctx, update) -> None:
    """Гость на связи: last_seen_at, снять отметку блокировки (только у записанных)."""
    info = _private_sender(update)
    if info is None:
        return
    chat_id, user = info
    try:
        ctx.subs.touch(chat_id, user_id=user.get('user_id'), username=user.get('username'),
                       first_name=user.get('first_name'))
    except Exception as exc:  # noqa: BLE001 — отметка не должна мешать ответу
        print(f"[TAPLIST-POLL] touch failed: {_scrub_text(exc, ctx.token)}")


def handle_update(update, ctx, token=None) -> list:
    """Один апдейт целиком: состояние диалога -> план -> «гость на связи» -> исполнение.

    Ответ — план (для тестов и логов).
    """
    chat_id = update_chat_id(update)
    dialog = ctx.dialogs.get(chat_id, ctx.now()) if chat_id is not None else None
    actions = plan_update(update, dialog, signup=ctx.signup_enabled())
    _touch(ctx, update)
    _execute(actions, token or ctx.token, None, ctx)
    return actions


# Подбор отзывов из бота, о которых владельцу не сообщили сразу (core/review_notify:
# SWEEP_INTERVAL_SEC — то же значение): раз в 10 минут, из цикла опроса.
REVIEW_SWEEP_SEC = 600


class Housekeeping:
    """Периодические дела цикла опроса.

    - Меню команд бота (setMyCommands) — по выключателю записи гостей: выключатель
      сверяется не чаще раза в COMMANDS_CHECK_SEC, меню переотправляется только при
      смене (или если прошлая отправка не удалась). При выключенной записи в меню нет
      /subscribe и /review (commands_for).
    - Подбор отзывов из бота без уведомления — раз в REVIEW_SWEEP_SEC (ctx.sweep_reviews:
      фоновый поток, опрос не ждёт блокировку рассылки). Первый — сразу при старте:
      отзыв, сохранённый прямо перед перезапуском воркера, не ждёт 10 минут.
    clock — монотонные секунды (подменяется в тестах).
    """

    def __init__(self, ctx, set_commands, clock=time.monotonic):
        self.ctx = ctx
        self.set_commands = set_commands     # (список команд) -> ответ Telegram
        self.clock = clock
        self.published = None                # выключатель, под который опубликовано меню
        self._checked = None
        self._swept = None

    def tick(self) -> None:
        now = self.clock()
        if self._checked is None or now - self._checked >= COMMANDS_CHECK_SEC:
            self._checked = now
            signup = self.ctx.signup_enabled()
            if signup != self.published:
                res = self.set_commands(commands_for(signup))
                if res and res.get('ok'):
                    self.published = signup
        if self._swept is None or now - self._swept >= REVIEW_SWEEP_SEC:
            self._swept = now
            try:
                self.ctx.sweep_reviews()
            except Exception as exc:  # noqa: BLE001 — подбор не должен ронять опрос
                print(f"[TAPLIST-POLL] подбор отзывов не запущен: {_scrub_text(exc, self.ctx.token)}")


def _poll_loop() -> None:
    from core.open_check_telegram import _scrub, api_call

    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    ctx = BotContext(token)
    api_call('deleteWebhook', {'drop_pending_updates': False}, token=token)
    house = Housekeeping(ctx, lambda commands: api_call('setMyCommands', {'commands': commands}, token=token))
    house.tick()                             # меню команд под текущий выключатель + первый подбор

    me = api_call('getMe', token=token)
    if me and me.get('ok'):
        print(f"[TAPLIST-POLL] polling стартовал, бот @{me['result'].get('username')}")
    else:
        desc = (me or {}).get('description') or 'нет ответа'
        print(f"[TAPLIST-POLL] getMe не подтвердил токен ({desc}) — polling продолжит пытаться")

    offset = None
    while True:
        try:
            payload = {
                'timeout': POLL_TIMEOUT,
                'allowed_updates': ALLOWED_UPDATES,
            }
            if offset is not None:
                payload['offset'] = offset
            data = api_call('getUpdates', payload, timeout=HTTP_TIMEOUT, token=token)
            if data and data.get('error_code') == 401:
                print('[TAPLIST-POLL] Telegram отклонил токен. Проверьте TELEGRAM_BOT_TOKEN и перезапустите приложение.')
                time.sleep(60)
                continue
            try:
                def feed(upd, token=token, ctx=ctx):
                    handle_update(upd, ctx, token)

                def on_error(exc, token=token):
                    print(f"[TAPLIST-POLL] update failed: {_scrub(exc, token)}")

                offset = consume_batch(data, offset, feed, on_error)
            except WebhookConflict:
                api_call('deleteWebhook', {'drop_pending_updates': False}, token=token)
                time.sleep(2)
                continue
            house.tick()
            if not data or not data.get('ok'):
                time.sleep(5)
        except Exception as exc:
            print(f"[TAPLIST-POLL] исключение в цикле: {_scrub(exc, token)}")
            time.sleep(10)


def start_polling() -> None:
    """Запустить daemon-поток polling'а. Идемпотентно; лок отдаёт его одному процессу."""
    global _started, _lock_handle
    with _thread_lock:
        if _started:
            return
        if not os.environ.get('TELEGRAM_BOT_TOKEN'):
            print('[TAPLIST-POLL] TELEGRAM_BOT_TOKEN не задан — polling отключён')
            return
        if _polling_disabled():
            print('[TAPLIST-POLL] TAPLIST_POLLING=0 — polling отключён')
            return

        os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
        handle = open(LOCK_PATH, 'a')
        try:
            portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.exceptions.BaseLockException:
            handle.close()
            print('[TAPLIST-POLL] лок занят другим воркером — в этом процессе polling не нужен')
            return

        _lock_handle = handle
        thread = threading.Thread(target=_poll_loop, name='taplist-polling', daemon=True)
        thread.start()
        _started = True
