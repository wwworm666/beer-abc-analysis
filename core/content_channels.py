"""
Каналы и отправка контент-плана: куда публиковать и включена ли отправка.

## Что это

Настройки, без которых отправка публикаций (core/content_publisher.py) ничего не
шлёт: адрес Telegram-канала каждого бара, чат для напоминаний об Instagram,
главный выключатель отправки и отдельный выключатель рассылок гостям. Здесь же —
вычисление «что подключено» (delivery) для страницы и агента и обёртка над
подписчиками гостевого бота (core/guest_subscribers.py) для размера аудитории.

Всё по умолчанию ВЫКЛЮЧЕНО: пока владелец не впишет адреса каналов, не проверит их и
не включит отправку на странице «Контент-план» -> «Каналы и отправка», ни одна
публикация сама не уходит (решение владельца 2026-09-28).

## Файлы

| Файл | Роль |
|------|------|
| `core/content_channels.py` | этот модуль: хранилище настроек, delivery, аудитория бота |
| `core/content_publisher.py` | отправка: читает эти настройки |
| `routes/content_plan.py` | `GET/PUT /api/content-plan/channels`, `POST …/channels/check`, `POST …/channels/test`, `GET …/audience` |
| `core/guest_subscribers.py` | подписчики гостевого бота (пишет другой модуль; нет модуля — подписчиков 0) |
| `tests/test_content_publisher.py` | тесты |

Данные: `content_channels.json` на постоянном томе (`core/storage_paths`), рядом
`content_channels.json.lock`.

## Как работает

Файл:

    {version: 1,
     enabled: bool, enabled_at,                      главный выключатель отправки
     telegram: {<бар>: {chat, title, checked_at, check, connected_since,
                        connected_chat}},              адрес, для которого connected_since
     instagram: {reminder_chat, reminder_minutes_before, since},
     bot: {enabled, enabled_at,                      рассылки гостям
           signup},                                  кнопки «Подписаться на новости» и
                                                     «Оставить отзыв» в гостевом боте
     bot_identity: {username, token_hash, at},       последний ответ getMe
     updated_at, updated_by, history: [{at, by, text}]}

Бар — ключ core/content_plan.BAR_KEYS (bolshoy, ligovskiy, kremenchugskaya,
varshavskaya). Время — Москва, 'YYYY-MM-DDTHH:MM' (как в контент-плане).

Адрес чата (`parse_chat`): '@имя' публичного канала (5–32 знака: латиница, цифры,
«_», первая — буква; так устроены имена Telegram), ссылка t.me/имя (сводится к
@имя) или числовой id ('-100…' у каналов, положительный — у личного чата).
Пригласительная ссылка (t.me/+…) не подходит: бот по ней чат не найдёт.

Адреса по роли (проверка 2026-09-28): канал бара — только канал или группа;
положительный id (личный чат) в канал бара не сохраняется (ValueError -> 400), личный
чат, найденный по @имени, проверка отклоняет (can_post false). Чат напоминаний об
Instagram не может совпадать с каналом бара (`reminder_conflict`: адрес, @имя без
учёта регистра, id и @имя из проверки канала) — служебная заметка ушла бы
подписчикам канала: `update` с НОВЫМ совпадением — ValueError, ничего не пишется;
совпадение, появившееся после проверки канала, правки не блокирует, но Instagram
«не подключён» (reason), и отправщик напоминание не шлёт.

Проверка канала (кнопка «Проверить», core/content_publisher.check_channel):
getMe -> getChat -> getChatMember(бот). Результат `check = {ok, can_post, error,
chat_title, chat_type, chat_username, chat_id, bot_username, chat}` сохраняется у
бара вместе с адресом, для которого он получен (`chat`): смена адреса стирает
проверку. Сбой связи (нет ответа, 429, 5xx) не сохраняется вовсе (решает
check_channel): случайный сбой не выключает рабочий канал.

«Проверенный канал» бара = адрес указан, последняя проверка — для этого адреса,
ok и can_post (бот — администратор с правом публиковать).

`connected_since` бара, `instagram.since`, `bot.enabled_at` и `enabled_at` —
когда соответствующая часть стала готова. Отправщик берёт только публикации со
временем выхода не раньше самого позднего из этих моментов: публикация, время
которой прошло до подключения, остаётся «Время вышло» — её отмечают вручную,
как до подключения (иначе включение отправки выпустило бы или пометило ошибкой
весь накопленный хвост). `connected_since` ставится при первой успешной проверке
адреса (`connected_chat`) и больше не сдвигается — ни провалом, ни повторным
успехом того же адреса; сбрасывает его только смена адреса. Иначе сбой при
«Проверить» и повторная проверка делали пост, время которого уже было, «раньше
подключения» навсегда (проверка 2026-09-28).

Два бота (разделены 2026-09-28 по замечанию проверки):
- бот каналов (`channel_bot_token`): TELEGRAM_CONTENT_BOT_TOKEN (отдельный бот
  контента, необязательный), иначе TELEGRAM_BOT_TOKEN — публикует в каналы баров,
  проверяет каналы, шлёт тестовое сообщение и напоминание об Instagram (чат
  напоминаний должен был запустить этого бота или быть группой, где он есть);
- гостевой бот (`guest_bot_token`): ТОЛЬКО TELEGRAM_BOT_TOKEN (@kult_taplist_bot) —
  рассылки гостям. Гость запускал именно его: бот контента в личный чат гостя
  написать не может (403), и каждый подписчик был бы помечен «заблокировал бота».
Нет токена — «бот не настроен». Токены в ответы API не попадают никогда; имя бота
каналов (`bot_username`) — из последнего getMe, только если он получен с тем же
токеном (`token_hash` — первые 16 знаков sha256).

Что подключено (`delivery_state`):

| Площадка | Подключено, если |
|---|---|
| telegram, бар X | отправка включена, есть бот каналов, у бара X проверенный канал |
| instagram | отправка включена, есть бот каналов, задан чат для напоминаний, он не совпадает с каналом бара |
| bot | отправка включена, есть гостевой бот, рассылки гостям включены |

Instagram требует и токен (контракт называл только выключатель и чат):
напоминание шлёт бот — без токена оно не уйдёт, а «подключено» обманывало бы.

`reason` у площадки — почему не подключено (сначала своя настройка, потом общий
выключатель и токен): «канал не указан», «канал не проверен», «бот не может
публиковать в канале», «отправка выключена», «бот не настроен» …

Размер аудитории бота (`audience_size`) — из core/guest_subscribers.audience_size
на сейчас; сегменты «были за 30 дней» и «не были 60 дней» считают только
подписчиков с телефоном (визиты — из базы гостей по телефону). Модуля подписчиков
ещё нет — размер 0 с пояснением; ошибка чтения — размер неизвестен (None).

Хранение — как core/supplier_directory.py и контент-план: запись под
threading.Lock + файловой блокировкой, строгое перечтение, атомарная запись. Файла
нет — настройки по умолчанию (всё выключено). Файл есть, но не читается, не того
вида или новее этой версии — ContentChannelsUnavailable (API 503), и файл НИКОГДА
не перезаписывается. Неизвестные ключи верхнего уровня сохраняются как есть.

Журнал настроек (`history`): последние HISTORY_MAX = 100 изменений («Отправка
публикаций включена», «Канал ВО: @kult_vo», результат проверки и тестового
сообщения) — кто и когда включил отправку, видно без журнала сервера.

Кнопки подписки в гостевом боте (`bot.signup`, по умолчанию выключено): показывать
ли гостям в @kult_taplist_bot «Подписаться на новости» и «Оставить отзыв».
Включает владелец, когда утвердит текст согласия. Бот (core/taplist_polling.py)
спрашивает `bot_signup_enabled()` на каждый апдейт: файл читается только при
смене его mtime/размера; нет файла или ошибка — False (кнопок нет). Отдельно от
`bot.enabled`: можно собирать подписчиков, ещё не делая рассылок.

## Changelog

- 2026-09-28 — модуль создан: настройки каналов, выключатели, delivery, аудитория бота;
  bot.signup и bot_signup_enabled() — кнопки подписки и отзывов в гостевом боте.
- 2026-09-28 — по независимой проверке: connected_since не сдвигается повторной
  проверкой и не сбрасывается провалом (connected_chat); положительный id у канала
  бара — ошибка; чат напоминаний не может совпадать с каналом бара (reminder_conflict).
"""

import copy
import hashlib
import json
import os
import re
import threading
from typing import Callable, Dict, List, Optional, Tuple

from core import msk_time
from core.content_plan import (AUDIENCE_BY_KEY, BAR_BY_KEY, BAR_KEYS, actor_label, fmt_stamp)
from core.json_store import atomic_write_json, file_lock
from core.storage_paths import get_data_path

SCHEMA_VERSION = 1
DATA_FILE_NAME = 'content_channels.json'

CONTENT_TOKEN_ENV = 'TELEGRAM_CONTENT_BOT_TOKEN'   # отдельный бот контента (необязательно)
TAPLIST_TOKEN_ENV = 'TELEGRAM_BOT_TOKEN'           # гостевой бот @kult_taplist_bot

# Напоминание об Instagram заранее: 0..720 минут. 12 часов — вечером о посте на
# утро; раньше напоминание «пора выложить» теряет смысл (его забудут до выхода).
REMINDER_MINUTES_MAX = 720
# Подпись канала бара на экране («Культура ВО»): строка списка, не текст поста.
TITLE_MAX = 100
# Журнал настроек: 100 записей — годы редких правок; больше — разбухание файла.
HISTORY_MAX = 100

TEST_MESSAGE_TEXT = 'Проверка связи с сайтом'

# Имя Telegram: 5–32 знака, латиница, цифры и «_», первая — буква, последняя — не «_».
_USERNAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]{3,30}[A-Za-z0-9]\Z')
_CHAT_ID_RE = re.compile(r'^-?\d{1,20}\Z')
_TME_RE = re.compile(r'^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(?:s/)?([^/?#]+)/?\Z', re.IGNORECASE)
_WS = re.compile(r'\s+')
_TRUE_WORDS = {'1', 'true', 'yes', 'on', 'да'}
_FALSE_WORDS = {'', '0', 'false', 'no', 'off', 'нет', 'none', 'null'}

TOP_KEYS = ('enabled', 'telegram', 'instagram', 'bot')
BAR_FIELDS = ('chat', 'title')
INSTAGRAM_FIELDS = ('reminder_chat', 'reminder_minutes_before')
BOT_FIELDS = ('enabled', 'signup')

# Пояснения к размеру аудитории (показываются под «Как считается»).
AUDIENCE_NOTES = {
    'bot_all': 'Все подписчики бота, согласившиеся получать новости',
    'bot_bar': 'Подписчики бота, выбравшие этот бар',
    'bot_recent_30': ('Подписчики, которые были в баре за последние 30 дней: считаются только '
                      'поделившиеся телефоном (визиты — из базы гостей по телефону)'),
    'bot_lapsed_60': ('Подписчики, которые не были в баре 60 дней и дольше: считаются только '
                      'поделившиеся телефоном (визиты — из базы гостей по телефону)'),
}
SIZE_NOW_NOTE = 'Размер — на сейчас: к моменту рассылки он может измениться (подписки и отписки)'
NO_MODULE_NOTE = 'Подписка на новости в боте ещё не подключена: подписчиков пока нет'
READ_ERROR_NOTE = 'Не удалось прочитать подписчиков бота — размер неизвестен'
NEEDS_BAR_NOTE = 'Размер зависит от бара: выберите бар у размещения'


class ContentChannelsUnavailable(RuntimeError):
    """Файл настроек каналов есть, но прочитать его нельзя: писать поверх запрещено."""


# ---------------------------------------------------------------------------
# Токен бота
# ---------------------------------------------------------------------------

def channel_bot_token() -> Tuple[Optional[str], Optional[str]]:
    """Бот, который публикует в каналы баров, проверяет каналы, шлёт тестовое
    сообщение и напоминание об Instagram: (токен, источник) — 'content'
    (TELEGRAM_CONTENT_BOT_TOKEN), иначе 'taplist' (TELEGRAM_BOT_TOKEN); (None, None) —
    бот не настроен."""
    for env, source in ((CONTENT_TOKEN_ENV, 'content'), (TAPLIST_TOKEN_ENV, 'taplist')):
        value = (os.environ.get(env) or '').strip()
        if value:
            return value, source
    return None, None


def guest_bot_token() -> Tuple[Optional[str], Optional[str]]:
    """Бот, которому пишут гости, — ТОЛЬКО @kult_taplist_bot (TELEGRAM_BOT_TOKEN).

    Рассылки гостям и всё, что уходит в личные чаты гостей, — только им: гость
    запускал этого бота. Отдельный бот контента писать гостю не может — Telegram
    ответит 403, и отправщик пометил бы каждого подписчика «заблокировал бота».
    -> (токен, 'taplist') или (None, None)."""
    value = (os.environ.get(TAPLIST_TOKEN_ENV) or '').strip()
    return (value, 'taplist') if value else (None, None)


# Прежнее имя: бот каналов (так его звали маршруты и планировщик до разделения).
bot_token = channel_bot_token


def token_hash(token: Optional[str]) -> Optional[str]:
    """Отпечаток токена (16 знаков sha256): по нему видно, что имя бота получено с
    тем же токеном. Сам токен не хранится и не отдаётся."""
    if not token:
        return None
    return hashlib.sha256(('content-bot:' + token).encode('utf-8')).hexdigest()[:16]


def bot_username(settings: dict, token: Optional[str]) -> Optional[str]:
    """Имя бота из последнего getMe — только если оно получено с этим же токеном."""
    identity = settings.get('bot_identity') or {}
    if token and isinstance(identity, dict) and identity.get('token_hash') == token_hash(token):
        return identity.get('username') or None
    return None


# ---------------------------------------------------------------------------
# Разбор ввода
# ---------------------------------------------------------------------------

def parse_bool(value, field: str) -> bool:
    if isinstance(value, str):
        word = value.strip().casefold()
        if word in _FALSE_WORDS:
            return False
        if word in _TRUE_WORDS:
            return True
        raise ValueError(f'{field}: нужно да/нет')
    if value is None or isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return bool(value)
    raise ValueError(f'{field}: нужно да/нет')


def parse_chat(value, field: str = 'Канал') -> str:
    """Адрес чата -> '@имя' или числовой id строкой; '' — не задан.

    Принимается '@имя', 'имя', ссылка t.me/имя и числовой id. Пригласительная
    ссылка (t.me/+…, t.me/joinchat/…) — ValueError: бот по ней чат не найдёт."""
    if value is None:
        return ''
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError(f'{field}: нужен @имя канала, ссылка t.me/имя или числовой id чата')
    text = str(value).strip()
    if not text:
        return ''
    if _CHAT_ID_RE.match(text):
        return str(int(text))
    match = _TME_RE.match(text)
    if match:
        text = match.group(1)
        if text.startswith('+') or text.lower() == 'joinchat':
            raise ValueError(f'{field}: пригласительная ссылка не подходит — нужен @имя публичного канала '
                             'или числовой id чата (-100…)')
    if text.startswith('@'):
        text = text[1:]
    if not _USERNAME_RE.match(text):
        raise ValueError(f'{field}: нужен @имя канала (5–32 знака: латиница, цифры, «_»), ссылка t.me/имя '
                         'или числовой id чата (-100…)')
    return '@' + text


def parse_title(value, field: str = 'Подпись канала') -> str:
    text = _WS.sub(' ', '' if value is None else str(value)).strip()
    if len(text) > TITLE_MAX:
        raise ValueError(f'{field} длиннее {TITLE_MAX} знаков')
    return text


def parse_minutes(value) -> int:
    text = f'Напоминание заранее: целое число минут от 0 до {REMINDER_MINUTES_MAX}'
    if isinstance(value, bool) or value is None or value == '':
        raise ValueError(text)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(text) from None
    if number != number or number != int(number):
        raise ValueError(text)
    number = int(number)
    if not 0 <= number <= REMINDER_MINUTES_MAX:
        raise ValueError(text)
    return number


def bar_short(bar: str) -> str:
    return BAR_BY_KEY.get(bar, {}).get('short', bar)


# ---------------------------------------------------------------------------
# Настройки: умолчания и проверка файла
# ---------------------------------------------------------------------------

def _default_bar() -> dict:
    # connected_chat — адрес, для которого получен connected_since: повторная успешная
    # проверка того же адреса момент подключения не сдвигает (см. save_check).
    return {'chat': '', 'title': '', 'checked_at': None, 'check': None, 'connected_since': None,
            'connected_chat': None}


def default_settings() -> dict:
    """Настройки, когда файла ещё нет: всё выключено, каналов нет."""
    return {
        'version': SCHEMA_VERSION, 'enabled': False, 'enabled_at': None,
        'telegram': {bar: _default_bar() for bar in BAR_KEYS},
        'instagram': {'reminder_chat': '', 'reminder_minutes_before': 0, 'since': None},
        'bot': {'enabled': False, 'enabled_at': None, 'signup': False},
        'bot_identity': None,
        'updated_at': None, 'updated_by': None, 'history': [],
    }


def _broken(text: str) -> ContentChannelsUnavailable:
    return ContentChannelsUnavailable(f'Файл настроек каналов повреждён: {text}')


def _opt_str(value) -> bool:
    return value is None or isinstance(value, str)


def _check_settings(data) -> dict:
    """Проверить файл и дополнить отсутствующие поля умолчаниями. Неожиданный тип
    известного поля — ContentChannelsUnavailable (не чиним молча: запись поверх
    стёрла бы то, чего эта версия не понимает). Неизвестные ключи — сохраняются."""
    if not isinstance(data, dict):
        raise _broken('неожиданная структура')
    version = data.get('version', SCHEMA_VERSION)
    if not isinstance(version, int) or isinstance(version, bool) or version > SCHEMA_VERSION:
        raise _broken('версия файла новее этой версии сервиса')
    out = default_settings()
    for key, value in data.items():
        if key not in out:
            out[key] = copy.deepcopy(value)          # неизвестное — как есть
    if not isinstance(data.get('enabled', False), bool) or not _opt_str(data.get('enabled_at')):
        raise _broken('главный выключатель')
    out['enabled'] = data.get('enabled', False)
    out['enabled_at'] = data.get('enabled_at')
    telegram = data.get('telegram', {})
    if not isinstance(telegram, dict):
        raise _broken('каналы Telegram')
    for bar, entry in telegram.items():
        if bar not in BAR_KEYS:
            out['telegram'][bar] = copy.deepcopy(entry)   # бар, которого эта версия не знает
            continue
        if not isinstance(entry, dict):
            raise _broken(f'канал бара {bar}')
        cfg = _default_bar()
        for key, value in entry.items():
            cfg[key] = copy.deepcopy(value)
        if (not isinstance(cfg['chat'], str) or not isinstance(cfg['title'], str)
                or not _opt_str(cfg['checked_at']) or not _opt_str(cfg['connected_since'])
                or not _opt_str(cfg['connected_chat'])
                or not (cfg['check'] is None or isinstance(cfg['check'], dict))):
            raise _broken(f'канал бара {bar}')
        out['telegram'][bar] = cfg
    instagram = data.get('instagram', {})
    if not isinstance(instagram, dict):
        raise _broken('Instagram')
    for key, value in instagram.items():
        out['instagram'][key] = copy.deepcopy(value)
    minutes = out['instagram']['reminder_minutes_before']
    if (not isinstance(out['instagram']['reminder_chat'], str) or isinstance(minutes, bool)
            or not isinstance(minutes, int) or not 0 <= minutes <= REMINDER_MINUTES_MAX
            or not _opt_str(out['instagram']['since'])):
        raise _broken('Instagram')
    bot = data.get('bot', {})
    if not isinstance(bot, dict):
        raise _broken('рассылки бота')
    for key, value in bot.items():
        out['bot'][key] = copy.deepcopy(value)
    if (not isinstance(out['bot']['enabled'], bool) or not _opt_str(out['bot']['enabled_at'])
            or not isinstance(out['bot']['signup'], bool)):
        raise _broken('рассылки бота')
    identity = data.get('bot_identity')
    if not (identity is None or isinstance(identity, dict)):
        raise _broken('имя бота')
    out['bot_identity'] = copy.deepcopy(identity)
    if not _opt_str(data.get('updated_at')) or not _opt_str(data.get('updated_by')):
        raise _broken('отметка изменения')
    out['updated_at'], out['updated_by'] = data.get('updated_at'), data.get('updated_by')
    history = data.get('history', [])
    if not isinstance(history, list):
        raise _broken('журнал настроек')
    out['history'] = copy.deepcopy(history)
    out['version'] = SCHEMA_VERSION
    return out


def public_view(settings: dict) -> dict:
    """Настройки для API: без отпечатка токена (bot_identity)."""
    out = copy.deepcopy(settings)
    out.pop('bot_identity', None)
    return out


# ---------------------------------------------------------------------------
# Что подключено
# ---------------------------------------------------------------------------

def telegram_bar_ready(cfg: Optional[dict]) -> bool:
    """Проверенный канал: адрес есть, последняя проверка — для этого адреса,
    Telegram его нашёл (ok) и бот может публиковать (can_post)."""
    if not isinstance(cfg, dict) or not cfg.get('chat'):
        return False
    check = cfg.get('check')
    return (isinstance(check, dict) and bool(check.get('ok')) and bool(check.get('can_post'))
            and check.get('chat') == cfg.get('chat'))


def _same_chat(a: str, b: str) -> bool:
    """Один и тот же чат: @имена — без учёта регистра (имена Telegram
    регистронезависимы), числовые id — точно."""
    a, b = str(a or '').strip(), str(b or '').strip()
    if not a or not b:
        return False
    if a.startswith('@') and b.startswith('@'):
        return a.casefold() == b.casefold()
    return a == b


def reminder_conflict(settings: dict) -> Optional[str]:
    """Бар, чей канал совпадает с чатом напоминаний об Instagram (по адресу, по
    @имени или числовому id, которые вернула проверка канала), или None. Служебное
    напоминание в канал бара ушло бы его подписчикам (проверка 2026-09-28)."""
    chat = ((settings.get('instagram') or {}).get('reminder_chat') or '').strip()
    if not chat:
        return None
    for bar in BAR_KEYS:
        cfg = (settings.get('telegram') or {}).get(bar) or {}
        check = cfg.get('check') if isinstance(cfg.get('check'), dict) else {}
        names = [cfg.get('chat') or '']
        if check.get('chat_id') is not None:
            names.append(str(check['chat_id']))
        if check.get('chat_username'):
            names.append('@' + str(check['chat_username']).lstrip('@'))
        if any(_same_chat(chat, name) for name in names):
            return bar
    return None


def telegram_bar_reason(cfg: Optional[dict]) -> Optional[str]:
    """Почему канал бара не готов (своя настройка) или None."""
    if not isinstance(cfg, dict) or not cfg.get('chat'):
        return 'канал не указан'
    check = cfg.get('check')
    if not isinstance(check, dict) or check.get('chat') != cfg.get('chat'):
        return 'канал не проверен'
    if not check.get('ok'):
        return 'проверка не прошла: ' + (check.get('error') or 'канал не найден')
    if not check.get('can_post'):
        return check.get('error') or 'бот не может публиковать в канале'
    return None


GUEST_BOT_MISSING = 'гостевой бот не настроен (нет TELEGRAM_BOT_TOKEN)'


def _global_reason(settings: dict, token_present: bool, missing: str = 'бот не настроен') -> Optional[str]:
    if not token_present:
        return missing
    if not settings.get('enabled'):
        return 'отправка выключена'
    return None


def delivery_state(settings: dict, token_present: bool, subscribers_total: Optional[int] = None, *,
                   guest_token_present: bool) -> dict:
    """Что подключено (правила — в докстроке модуля).

    token_present — есть бот каналов (channel_bot_token): Telegram и Instagram;
    guest_token_present — есть гостевой бот (guest_bot_token): рассылки гостям.
    -> {enabled, bot_configured, guest_bot_configured, telegram: {бар: {connected,
        chat, title, reason}}, instagram: {connected, reminder_chat,
        reminder_minutes_before, reason}, bot: {connected, enabled, signup,
        subscribers_total, reason}}."""
    enabled = bool(settings.get('enabled'))
    common = _global_reason(settings, token_present)
    guest_common = _global_reason(settings, guest_token_present, GUEST_BOT_MISSING)
    telegram = {}
    for bar in BAR_KEYS:
        cfg = (settings.get('telegram') or {}).get(bar) or {}
        own = telegram_bar_reason(cfg)
        telegram[bar] = {'connected': own is None and common is None, 'chat': cfg.get('chat') or '',
                         'title': cfg.get('title') or '', 'reason': own or common}
    ig = settings.get('instagram') or {}
    conflict = reminder_conflict(settings)
    if not ig.get('reminder_chat'):
        ig_own = 'не указан чат для напоминаний'
    elif conflict:
        ig_own = f'чат для напоминаний совпадает с каналом бара {bar_short(conflict)}'
    else:
        ig_own = None
    bot = settings.get('bot') or {}
    bot_own = None if bot.get('enabled') else 'рассылки гостям выключены'
    return {
        'enabled': enabled,
        'bot_configured': bool(token_present),
        'guest_bot_configured': bool(guest_token_present),
        'telegram': telegram,
        'instagram': {'connected': ig_own is None and common is None,
                      'reminder_chat': ig.get('reminder_chat') or '',
                      'reminder_minutes_before': ig.get('reminder_minutes_before') or 0,
                      'reason': ig_own or common},
        'bot': {'connected': bot_own is None and guest_common is None, 'enabled': bool(bot.get('enabled')),
                'signup': bool(bot.get('signup')), 'subscribers_total': subscribers_total,
                'reason': bot_own or guest_common},
    }


def delivery_connected(delivery: dict) -> dict:
    """Прежнее поле ответа месяца (совместимость страницы): telegram — хоть один
    бар подключён; instagram; bot."""
    return {'telegram': any(v.get('connected') for v in (delivery.get('telegram') or {}).values()),
            'instagram': bool((delivery.get('instagram') or {}).get('connected')),
            'bot': bool((delivery.get('bot') or {}).get('connected'))}


def disconnected_delivery(error: Optional[str] = None) -> dict:
    """delivery «ничего не подключено» (файл настроек не читается и т. п.)."""
    delivery = delivery_state(default_settings(), bool(channel_bot_token()[0]), None,
                              guest_token_present=bool(guest_bot_token()[0]))
    if error:
        delivery['error'] = error
    return delivery


def since_for(settings: dict, channel: str, bar: Optional[str] = None) -> str:
    """С какого момента публикации площадки отправляются сами: самый поздний из
    моментов включения отправки и готовности площадки ('' — не задан)."""
    marks = [settings.get('enabled_at') or '']
    if channel == 'telegram':
        marks.append(((settings.get('telegram') or {}).get(bar) or {}).get('connected_since') or '')
    elif channel == 'instagram':
        marks.append((settings.get('instagram') or {}).get('since') or '')
    elif channel == 'bot':
        marks.append((settings.get('bot') or {}).get('enabled_at') or '')
    return max(marks)


# ---------------------------------------------------------------------------
# Подписчики гостевого бота (core/guest_subscribers.py пишет другой модуль)
# ---------------------------------------------------------------------------

def _subscribers_module():
    """core.guest_subscribers или None, если модуля ещё нет (тогда подписчиков 0)."""
    try:
        from core import guest_subscribers
    except ImportError:
        return None
    return guest_subscribers


def audience_size(segment: str, bar: Optional[str] = None) -> Tuple[Optional[int], str]:
    """(размер, пояснение) аудитории рассылки на сейчас. bar None — вся сеть.

    Сегмент, которому нужен бар, без бара — (None, «выберите бар»); модуля
    подписчиков нет — (0, «подписка не подключена»); сбой чтения — (None, …)."""
    spec = AUDIENCE_BY_KEY.get(segment)
    if spec is None:
        raise ValueError(f'Неизвестная аудитория «{segment}»')
    if spec['needs_bar'] and not bar:
        return None, NEEDS_BAR_NOTE
    module = _subscribers_module()
    if module is None:
        return 0, NO_MODULE_NOTE
    try:
        size = int(module.audience_size(segment, bar))
    except Exception as e:  # noqa: BLE001 — размер аудитории не должен ронять страницу
        print(f'[CONTENT-CHANNELS] audience_size({segment}, {bar}): {e!r}')
        return None, READ_ERROR_NOTE
    return size, f'{AUDIENCE_NOTES[segment]}. {SIZE_NOW_NOTE}.'


def subscribers_total() -> Optional[int]:
    """Сколько гостей подписано на рассылки сейчас (stats()['subscribed']);
    модуля нет — 0; сбой — None."""
    module = _subscribers_module()
    if module is None:
        return 0
    try:
        stats = module.stats() or {}
        value = stats.get('subscribed', stats.get('total', 0))
        return int(value or 0)
    except Exception as e:  # noqa: BLE001
        print(f'[CONTENT-CHANNELS] subscribers stats: {e!r}')
        return None


def recipients(segment: str, bar: Optional[str] = None) -> List:
    """chat_id получателей рассылки (как их отдаёт core.guest_subscribers.recipients),
    без повторов, в исходном порядке. Модуля нет — []. Ошибка чтения — исключение:
    рассылка не должна уйти «никому» молча."""
    module = _subscribers_module()
    if module is None:
        return []
    out, seen = [], set()
    for row in module.recipients(segment, bar) or []:
        chat_id = row.get('chat_id') if isinstance(row, dict) else row
        if chat_id is None or str(chat_id) in seen:
            continue
        seen.add(str(chat_id))
        out.append(chat_id)
    return out


def mark_blocked(chat_id) -> None:
    """Гость заблокировал бота (Telegram 403): отметить в подписчиках. Сбой — в лог."""
    module = _subscribers_module()
    if module is None:
        return
    try:
        module.mark_blocked(chat_id)
    except Exception as e:  # noqa: BLE001
        print(f'[CONTENT-CHANNELS] mark_blocked({chat_id}): {e!r}')


# ---------------------------------------------------------------------------
# Хранилище
# ---------------------------------------------------------------------------

class ChannelsStore:
    """Настройки каналов на диске. now_fn — часы (для тестов)."""

    def __init__(self, data_file: Optional[str] = None, now_fn: Optional[Callable] = None):
        self.data_file = data_file or get_data_path(DATA_FILE_NAME)
        self._now_fn = now_fn or msk_time.now
        self._lock = threading.Lock()
        self._lock_path = self.data_file + '.lock'

    def now_str(self) -> str:
        moment = self._now_fn()
        if moment.tzinfo is not None:
            moment = moment.astimezone(msk_time.MOSCOW_TZ).replace(tzinfo=None)
        return fmt_stamp(moment)

    # ----- файл --------------------------------------------------------------

    def _load(self) -> dict:
        if not os.path.exists(self.data_file):
            return default_settings()
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f'[CONTENT-CHANNELS] cannot read {self.data_file}: {e}')
            raise ContentChannelsUnavailable(f'Файл настроек каналов не читается: {e}') from e
        return _check_settings(data)

    def _save(self, settings: dict) -> None:
        if len(settings['history']) > HISTORY_MAX:
            settings['history'] = settings['history'][-HISTORY_MAX:]
        atomic_write_json(self.data_file, settings)

    @staticmethod
    def _note(settings: dict, at: str, by: str, text: str) -> None:
        settings['history'].append({'at': at, 'by': by, 'text': text})

    def load(self) -> dict:
        """Настройки (копия). Файл повреждён — ContentChannelsUnavailable."""
        return self._load()

    def is_stored(self) -> bool:
        return os.path.exists(self.data_file)

    # ----- запись ------------------------------------------------------------

    def update(self, patch, user: Optional[dict]) -> dict:
        """Частичное слияние: {enabled?, telegram?: {бар: {chat?, title?}}, instagram?:
        {reminder_chat?, reminder_minutes_before?}, bot?: {enabled?}} -> настройки.

        Неизвестный ключ, бар или поле, неверное значение — ValueError, не
        сохраняется ничего (проверка до записи). Смена адреса канала стирает его
        проверку. Включение выключателя ставит момент включения (enabled_at,
        bot.enabled_at); новый чат напоминаний — instagram.since. Правка без
        изменений файл не пишет."""
        if not isinstance(patch, dict):
            raise ValueError('Нужен объект с настройками каналов')
        unknown = [key for key in patch if key not in TOP_KEYS]
        if unknown:
            raise ValueError(f'Неизвестное поле «{unknown[0]}»: можно enabled, telegram, instagram, bot')
        clean: Dict[str, object] = {}
        if 'enabled' in patch:
            clean['enabled'] = parse_bool(patch['enabled'], 'Отправка публикаций')
        if 'telegram' in patch:
            tg = patch['telegram']
            if not isinstance(tg, dict):
                raise ValueError('Каналы Telegram: нужен объект {бар: {chat, title}}')
            bars = {}
            for bar, fields in tg.items():
                if bar not in BAR_KEYS:
                    raise ValueError(f'Неизвестный бар «{bar}»')
                if not isinstance(fields, dict):
                    raise ValueError(f'Канал бара {bar_short(bar)}: нужен объект {{chat, title}}')
                extra = [k for k in fields if k not in BAR_FIELDS]
                if extra:
                    raise ValueError(f'Канал бара {bar_short(bar)}: неизвестное поле «{extra[0]}» '
                                     '(можно chat, title)')
                item = {}
                if 'chat' in fields:
                    item['chat'] = parse_chat(fields['chat'], f'Канал бара {bar_short(bar)}')
                    if item['chat'] and not item['chat'].startswith('@') and not item['chat'].startswith('-'):
                        raise ValueError(f'Канал бара {bar_short(bar)}: положительный id — это личный чат, а не '
                                         'канал; нужен @имя канала или id канала (-100…)')
                if 'title' in fields:
                    item['title'] = parse_title(fields['title'])
                bars[bar] = item
            clean['telegram'] = bars
        if 'instagram' in patch:
            ig = patch['instagram']
            if not isinstance(ig, dict):
                raise ValueError('Instagram: нужен объект {reminder_chat, reminder_minutes_before}')
            extra = [k for k in ig if k not in INSTAGRAM_FIELDS]
            if extra:
                raise ValueError(f'Instagram: неизвестное поле «{extra[0]}»')
            item = {}
            if 'reminder_chat' in ig:
                item['reminder_chat'] = parse_chat(ig['reminder_chat'], 'Чат для напоминаний')
            if 'reminder_minutes_before' in ig:
                item['reminder_minutes_before'] = parse_minutes(ig['reminder_minutes_before'])
            clean['instagram'] = item
        if 'bot' in patch:
            bot = patch['bot']
            if not isinstance(bot, dict):
                raise ValueError('Гостевой бот: нужен объект {enabled, signup}')
            extra = [k for k in bot if k not in BOT_FIELDS]
            if extra:
                raise ValueError(f'Гостевой бот: неизвестное поле «{extra[0]}» (можно enabled, signup)')
            item = {}
            if 'enabled' in bot:
                item['enabled'] = parse_bool(bot['enabled'], 'Рассылки гостям')
            if 'signup' in bot:
                item['signup'] = parse_bool(bot['signup'], 'Кнопки подписки и отзывов в боте')
            clean['bot'] = item

        by = actor_label(user)
        with self._lock, file_lock(self._lock_path):
            settings = self._load()
            now = self.now_str()
            notes: List[str] = []
            # Совпадение, которое было и раньше (например, проверка канала вернула тот же id),
            # правку не блокирует: иначе нельзя было бы даже выключить отправку. Его видно в
            # delivery (reason) и отправщик такое напоминание не шлёт.
            conflict_before = reminder_conflict(settings)
            if 'enabled' in clean and clean['enabled'] != settings['enabled']:
                settings['enabled'] = clean['enabled']
                if clean['enabled']:
                    settings['enabled_at'] = now
                notes.append('Отправка публикаций включена' if clean['enabled'] else 'Отправка публикаций выключена')
            for bar, item in (clean.get('telegram') or {}).items():
                cfg = settings['telegram'][bar]
                if 'chat' in item and item['chat'] != cfg['chat']:
                    cfg['chat'] = item['chat']
                    cfg['check'], cfg['checked_at'], cfg['connected_since'] = None, None, None
                    cfg['connected_chat'] = None
                    notes.append(f'Канал {bar_short(bar)}: {item["chat"]}' if item['chat']
                                 else f'Канал {bar_short(bar)} убран')
                if 'title' in item and item['title'] != cfg['title']:
                    cfg['title'] = item['title']
                    notes.append(f'Подпись канала {bar_short(bar)}: «{item["title"]}»')
            ig_item = clean.get('instagram') or {}
            ig = settings['instagram']
            if 'reminder_chat' in ig_item and ig_item['reminder_chat'] != ig['reminder_chat']:
                ig['reminder_chat'] = ig_item['reminder_chat']
                ig['since'] = now if ig_item['reminder_chat'] else None
                notes.append(f'Чат для напоминаний об Instagram: {ig_item["reminder_chat"]}'
                             if ig_item['reminder_chat'] else 'Чат для напоминаний об Instagram убран')
            if ('reminder_minutes_before' in ig_item
                    and ig_item['reminder_minutes_before'] != ig['reminder_minutes_before']):
                ig['reminder_minutes_before'] = ig_item['reminder_minutes_before']
                notes.append(f'Напоминание об Instagram за {ig_item["reminder_minutes_before"]} мин')
            bot_item = clean.get('bot') or {}
            if 'enabled' in bot_item and bot_item['enabled'] != settings['bot']['enabled']:
                settings['bot']['enabled'] = bot_item['enabled']
                if bot_item['enabled']:
                    settings['bot']['enabled_at'] = now
                notes.append('Рассылки гостям включены' if bot_item['enabled'] else 'Рассылки гостям выключены')
            if 'signup' in bot_item and bot_item['signup'] != settings['bot']['signup']:
                settings['bot']['signup'] = bot_item['signup']
                notes.append('Кнопки «Подписаться на новости» и «Оставить отзыв» в боте '
                             + ('включены' if bot_item['signup'] else 'выключены'))
            conflict = reminder_conflict(settings)
            if conflict and conflict != conflict_before:
                # Проверка до записи: служебное напоминание не должно уйти подписчикам канала.
                raise ValueError(f'Чат для напоминаний об Instagram совпадает с каналом бара '
                                 f'{bar_short(conflict)}: напоминание ушло бы подписчикам канала — '
                                 'укажите личный чат или служебную группу')
            if notes:
                settings['updated_at'], settings['updated_by'] = now, by
                for text in notes:
                    self._note(settings, now, by, text)
                self._save(settings)
        return settings

    def save_check(self, bar: str, chat: str, check: dict, user: Optional[dict],
                   identity: Optional[dict] = None) -> dict:
        """Сохранить результат проверки канала бара. Если адрес канала за время
        проверки поменяли — результат устарел и не сохраняется. identity —
        {username, token_hash} из getMe (имя бота на экране)."""
        if bar not in BAR_KEYS:
            raise ValueError(f'Неизвестный бар «{bar}»')
        by = actor_label(user)
        with self._lock, file_lock(self._lock_path):
            settings = self._load()
            now = self.now_str()
            if identity:
                settings['bot_identity'] = dict(identity, at=now)
            cfg = settings['telegram'][bar]
            if cfg['chat'] == chat and chat:
                cfg['check'] = dict(check, chat=chat)
                cfg['checked_at'] = now
                ready = telegram_bar_ready(cfg)
                # Момент подключения ставится при первой успешной проверке адреса и больше
                # не сдвигается ни провалом, ни повторным успехом того же адреса (проверка
                # 2026-09-28: сбой связи при «Проверить», затем успех -> connected_since =
                # сейчас, и пост, время которого уже было, «раньше подключения» не уходил).
                # Сбрасывает его только смена адреса (update).
                if ready and not (cfg.get('connected_since') and cfg.get('connected_chat') == chat):
                    cfg['connected_since'], cfg['connected_chat'] = now, chat
                result = ('бот может публиковать' if ready
                          else (telegram_bar_reason(cfg) or 'не готов'))
                self._note(settings, now, by, f'Проверка канала {bar_short(bar)} ({chat}): {result}')
            self._save(settings)
        return settings

    def note(self, text: str, user: Optional[dict], identity: Optional[dict] = None) -> None:
        """Запись в журнал настроек (например, тестовое сообщение)."""
        by = actor_label(user)
        with self._lock, file_lock(self._lock_path):
            settings = self._load()
            now = self.now_str()
            if identity:
                settings['bot_identity'] = dict(identity, at=now)
            self._note(settings, now, by, text)
            self._save(settings)


def payload_delivery(store: Optional[ChannelsStore] = None,
                     total_fn: Optional[Callable[[], Optional[int]]] = None) -> dict:
    """delivery и delivery_connected для ответа месяца контент-плана.
    Файл настроек не читается — «ничего не подключено» с текстом ошибки (месяц
    плана всё равно открывается)."""
    try:
        settings = (store or get_channels_store()).load()
    except ContentChannelsUnavailable as e:
        delivery = disconnected_delivery(str(e))
        return {'delivery': delivery, 'delivery_connected': delivery_connected(delivery)}
    token, _source = channel_bot_token()
    guest, _guest_source = guest_bot_token()
    total = (total_fn or subscribers_total)()
    delivery = delivery_state(settings, bool(token), total, guest_token_present=bool(guest))
    return {'delivery': delivery, 'delivery_connected': delivery_connected(delivery)}


_store: Optional[ChannelsStore] = None
_store_guard = threading.Lock()


def get_channels_store() -> ChannelsStore:
    """Ленивый синглтон на процесс (файл на томе общий для воркеров)."""
    global _store
    with _store_guard:
        if _store is None:
            _store = ChannelsStore()
        return _store


# Кэш bot_signup_enabled: (путь, mtime_ns, размер) -> значение. Бот зовёт проверку на
# каждый апдейт; перечитывать и разбирать JSON каждый раз незачем — файл меняется
# только правкой на странице (атомарная запись меняет mtime и, как правило, размер).
_signup_cache: dict = {}
_signup_guard = threading.Lock()


def bot_signup_enabled(data_file: Optional[str] = None) -> bool:
    """Показывать ли гостям в @kult_taplist_bot кнопки «Подписаться на новости» и
    «Оставить отзыв» (bot.signup; включает владелец, когда утвердит текст согласия).

    Читает сохранённый файл настроек (кэш по mtime и размеру). Файла нет, он не
    читается или повреждён — False: без явного решения владельца кнопок нет.
    Зовёт core/taplist_polling.py на каждый апдейт — функция не бросает исключений."""
    try:
        path = data_file or get_channels_store().data_file
        stat = os.stat(path)
    except (OSError, ValueError):
        return False
    key = (path, stat.st_mtime_ns, stat.st_size)
    with _signup_guard:
        if key in _signup_cache:
            return _signup_cache[key]
    try:
        with open(path, 'r', encoding='utf-8') as f:
            value = bool(_check_settings(json.load(f))['bot'].get('signup'))
    except Exception as e:  # noqa: BLE001 — любой сбой = «кнопок нет»
        print(f'[CONTENT-CHANNELS] bot_signup_enabled: {e!r}')
        value = False
    with _signup_guard:
        _signup_cache.clear()           # храним только последнее состояние файла
        _signup_cache[key] = value
    return value
