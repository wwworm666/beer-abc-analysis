"""Подписчики гостевого бота @kult_taplist_bot: согласие, бары, телефон, сегменты рассылки.

## Что это
Гость в личном чате с ботом нажимает «Подписаться на новости», читает текст согласия
(CONSENT_TEXTS) и нажимает «Согласен» — с этого момента он подписчик. Потом отмечает
бары и по желанию делится телефоном (кнопка Telegram request_contact). Диалог ведёт
core/taplist_polling.py; здесь — хранилище, правила и сегменты. Рассылку делает
отправитель контент-плана (core/content_publisher.py): зовёт recipients() и
mark_blocked() этого модуля, размер аудитории — audience_size(), сводку — stats().

## Файлы
    core/guest_subscribers.py        этот модуль (хранилище, сегменты, текст согласия)
    core/taplist_polling.py          диалог бота: кнопки, согласие, бары, телефон, /stop
    tests/test_guest_subscribers.py  тесты хранилища и сегментов (временные базы)
    docs/guides/TELEGRAM_BOT_GUIDE.md  описание для людей

## Хранение
SQLite guest_subscribers.db через core/storage_paths.get_data_path: /kultura/ на проде,
data/ локально (data/*.db в .gitignore). WAL + busy_timeout 5 с — как
core/auth_manager.py: пишут бот (один процесс — flock в core/taplist_polling.py) и
отправитель (mark_blocked — из любого воркера gunicorn), читают маршруты контент-плана.
Запись — BEGIN IMMEDIATE (межпроцессная блокировка SQLite) + threading.Lock процесса.
Версия схемы — PRAGMA user_version (сейчас 2); миграции только добавляют.
v1 — subscribers; v2 — dialogs (состояние диалога бота, см. ниже).

Таблица dialogs — шаг диалога бота, где бот ждёт от гостя текст, телефон или нажатие
(core/taplist_polling.PersistentDialogStore): chat_id PK, state (JSON), updated_ts
(unix-время). В базе, а не в памяти процесса: воркер gunicorn перезапускается
(--max-requests, деплой), и набранный гостем отзыв иначе пропадал бы молча. Таймаут —
тот же (30 минут), логику сроков держит бот; здесь только чтение и запись.

Таблица subscribers — одна строка на личный чат. Строка появляется только по «Согласен»:
тех, кто просто открыл бота или смотрит краны, не записываем.
    chat_id              PK, id личного чата (у личного чата = id пользователя Telegram)
    user_id              id пользователя Telegram
    username             ник без @ (может не быть)
    first_name           имя из профиля Telegram
    bars                 JSON-список ключей баров в порядке сети; [] — все бары
    subscribed           1 — подписан, 0 — отписался
    consent_at           когда нажал «Согласен» (последнее согласие)
    consent_text_version версия текста согласия — ключ CONSENT_TEXTS
    unsubscribed_at      когда отписался; null у подписанного
    blocked_at           когда заблокировал бота (403 при рассылке или my_chat_member
                         «kicked»); null — доступен
    phone                телефон в каноне витрины гостей (canon_phone); null — не делился
    guest_id             гость guests.db, найденный по телефону в момент, когда гость
                         поделился номером; null — не нашёлся
    created_at, updated_at, last_seen_at
Время — московское (core/msk_time), наивные строки 'YYYY-MM-DDTHH:MM:SS'.

## Как работает
- Подписка: subscribe() ставит subscribed=1, consent_at, consent_text_version и снимает
  unsubscribed_at и blocked_at. Повторное «Согласен» у подписанного согласие не
  переписывает (остаётся время первого). После отписки новое «Согласен» — новое
  согласие с новым временем и версией текста.
- Текст согласия версионируется: в строке хранится ключ CONSENT_TEXTS, сам текст — в
  коде. Поменять формулировку = добавить новую версию и переключить CONSENT_VERSION;
  старые версии не удалять (по ним видно, на что соглашался каждый гость).
- Бары (normalize_bars): только ключи PHYSICAL_VENUES, без повторов, в порядке сети.
  Пустой выбор = все бары; все четыре отмеченных тоже сворачиваются в [] («Все бары»),
  чтобы новый бар сети попал в подписку сам.
- Телефон: только из контакта Telegram (кнопка «Поделиться телефоном» — Telegram
  подтверждает, что номер свой; проверку делает бот) и только у подписанного.
  Канон (canon_phone) — только для российских форм, и он совпадает с guest_id витрины
  гостей (core/guest_sync.normalize_guest_id): 10 цифр с 9 -> '7' + 10 цифр; 11 цифр с
  7 или 8 -> '7' + последние 10; 12 цифр с 77 (лишняя 7 из iiko, docs/guests.md) ->
  '7' + последние 10. «+7 999 123-45-67», «8 999 123 45 67», «79991234567» и
  «779991234567» дают '79991234567'. Номер с «+» или из контакта Telegram
  (international=True: там всегда код страны) российский, только если это 7 и ещё
  10 цифр. Все прочие — зарубежные: '+' и цифры как есть (8..15 цифр), без привязки к
  гостю и без участия в сегментах по визитам. Раньше «'7' + последние 10» превращало
  армянский 37477123456 в чужой казахстанский +77477123456 и привязывало гостя к
  чужой карте (проверка 2026-09-28). Меньше 8 цифр — не телефон (ValueError).
- Связка с гостем (resolve_guest): сохранённый guest_id, если он ещё есть в витрине;
  иначе guests.guest_id = телефон (так хранится почти вся база); иначе guests.phone =
  телефон (при нескольких — с последним визитом, при равенстве — меньший guest_id);
  иначе псевдоним guest_aliases. Витрины нет или она не читается — связки нет, это не
  ошибка: подписка работает и без неё (в лог пишется предупреждение).
- Отписка (/stop, кнопка «Отписаться от новостей»): subscribed=0, unsubscribed_at;
  телефон и guest_id стираются — они были нужны только для подписки, согласие
  отозвано. Имя, ник, бары и время согласия/отписки остаются — это запись о том, на
  что гость соглашался и когда отказался.
- touch (гость написал боту) обновляет имя, ник и last_seen_at только у ПОДПИСАННОГО:
  об отписавшемся новое не копим.
- Блокировка: mark_blocked (403 при рассылке или my_chat_member «kicked») — чат
  рассылку не получает, пока гость снова не напишет боту (touch) или не разблокирует
  его (mark_unblocked). Строк для тех, кто не подписывался, не создаём.

## Сегменты рассылки (recipients / audience_size)
Всегда: subscribed=1 и blocked_at пуст. bar — бар размещения (None, '' или 'all' — вся
сеть). Если бар задан, остаются те, кто отметил этот бар или «Все бары», — для любого
сегмента: гость сам выбрал, новости каких баров получать (BAR_RULE).
    bot_all        все подписчики (с учётом бара, если он задан);
    bot_bar        подписчики бара; бар обязателен (без бара — ValueError);
    bot_recent_30  последний визит в любой бар сети (guests.last_visit_date) не раньше
                   чем RECENT_DAYS - 1 = 29 дней назад: 30 календарных дней, включая
                   сегодня. Сегодня 28.09 — визиты с 30.08 по 28.09;
    bot_lapsed_60  последний визит LAPSED_DAYS = 60 и больше дней назад. Сегодня
                   28.09 — визит 30.07 или раньше.
Визит 30–59 дней назад — ни в одном из двух. Подписчик без телефона или без найденного
гостя в recent/lapsed НЕ попадает: о его визитах мы не знаем. Гость ищется при каждом
расчёте заново (resolve_guest) — так учитывается и первая покупка после подписки.
«Сегодня» — московская дата. Витрина гостей обновляется ночью (core/guest_sync), поэтому
визиты текущего дня в расчёт не попадают.
Порядок recipients — по chat_id по возрастанию (детерминированно).

## API для отправителя (core/content_publisher.py)
    audience_size(segment, bar=None) -> int
    recipients(segment, bar=None) -> [{chat_id, username, first_name, bars, guest_id,
                                       last_visit_date}]   last_visit_date — только у
                                                           recent/lapsed, иначе None
    mark_blocked(chat_id) -> bool        True — отметка поставлена сейчас
    stats() -> {total, subscribed, with_phone, linked, all_bars, by_bar, unsubscribed,
                blocked, consent_version}  — смысл каждого числа в STATS_RULES
ValueError — неизвестный сегмент или бар, bot_bar без бара.
Для тестов: get_store(db_path=..., guests_db_path=..., clock=...) пересоздаёт общий
экземпляр, set_store(store) подставляет свой.

## Changelog
- 2026-09-28: модуль создан — подписка с согласием в @kult_taplist_bot, бары, телефон
  с привязкой к витрине гостей, сегменты для рассылок контент-плана.
"""
import json
import os
import sqlite3
import threading
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import date, datetime
from typing import Callable, Dict, List, Optional

from core import msk_time
from core.guest_sync import normalize_guest_id
from core.storage_paths import get_data_path
from core.venues_config import PHYSICAL_VENUES, VENUES

SCHEMA_VERSION = 2
DB_FILE_NAME = 'guest_subscribers.db'
STAMP_FORMAT = '%Y-%m-%dT%H:%M:%S'

# Бары в порядке сети; индекс бара здесь — номер бита в маске выбора кнопок бота.
BAR_KEYS = tuple(PHYSICAL_VENUES)
BAR_NAMES = {k: VENUES[k]['name'] for k in BAR_KEYS}
NETWORK_BAR = 'all'            # бар размещения «вся сеть» (как BAR_ALL контент-плана)

SEGMENTS = ('bot_all', 'bot_bar', 'bot_recent_30', 'bot_lapsed_60')
VISIT_SEGMENTS = ('bot_recent_30', 'bot_lapsed_60')
RECENT_DAYS = 30               # «были за последние 30 дней»: 30 календарных дней, включая сегодня
LAPSED_DAYS = 60               # «не были 60 дней и дольше»

# Зарубежный номер (всё, что не российская форма): от 8 до 15 цифр — короче номеров с
# кодом страны не бывает, 15 — предел международного формата E.164. Иначе — не телефон.
FOREIGN_MIN_DIGITS = 8
MAX_PHONE_DIGITS = 15
# Имя и ник из профиля Telegram: у Telegram до 64 знаков, 128 — с запасом.
MAX_NAME_LEN = 128

# Правила для подсказок интерфейса («Как считается»): формулы словами.
BAR_RULE = ('Если у рассылки выбран бар, её получают только подписчики, отметившие этот бар '
            'или «Все бары» (так для любой аудитории). Рассылка на всю сеть — всем подписчикам.')
SEGMENT_RULES = {
    'bot_all': 'Все, кто подписался на новости в боте и не заблокировал его.',
    'bot_bar': 'Подписчики, которые получают новости выбранного бара: отметили его или «Все бары».',
    'bot_recent_30': ('Подписчики, у которых по телефону нашлась карта гостя и последний визит в любой '
                      'бар сети был за последние 30 дней, включая сегодня. Без телефона гость сюда не '
                      'попадает. Визиты — по базе гостей, она обновляется ночью.'),
    'bot_lapsed_60': ('Подписчики, у которых по телефону нашлась карта гостя и последний визит в любой '
                      'бар сети был 60 и больше дней назад. Без телефона гость сюда не попадает.'),
}
STATS_RULES = {
    'total': 'Все, кто когда-либо нажал «Согласен», включая отписавшихся.',
    'subscribed': 'Подписаны сейчас и не заблокировали бота — им уходит рассылка «Все подписчики».',
    'with_phone': 'Из подписанных — поделились телефоном.',
    'linked': 'Из подписанных — по телефону нашлась карта гостя (на момент, когда поделились).',
    'all_bars': 'Из подписанных — выбрали «Все бары».',
    'by_bar': 'Из подписанных — получают новости бара: отметили его или «Все бары».',
    'unsubscribed': 'Отписались (кнопкой или /stop).',
    'blocked': 'Подписаны, но заблокировали бота — рассылка им не уходит.',
}

# Текст согласия. Версия (ключ) пишется в строку подписчика; старые версии не удалять.
CONSENT_VERSION = '2026-09-28'
CONSENT_TEXTS = {
    '2026-09-28': (
        'Новости баров «Культура»\n\n'
        'Нажимая «Согласен», вы соглашаетесь получать в этом чате новости и акции баров '
        '«Культура»: новинки на кранах, события, скидки.\n\n'
        'Что мы сохраняем: имя, ник и id аккаунта в Telegram, выбранные бары и — только если '
        'вы сами поделитесь — номер телефона. Телефон нужен, чтобы связать подписку с картой гостя '
        '«Культуры» и, если вы оставите отзыв, связаться с вами по нему.\n\n'
        'Отписаться можно в любой момент: кнопкой «Отписаться от новостей» в меню бота или '
        'командой /stop. При отписке телефон удаляется.'
    ),
}
CONSENT_TEXT = CONSENT_TEXTS[CONSENT_VERSION]

_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS subscribers (
        chat_id              INTEGER PRIMARY KEY,
        user_id              INTEGER,
        username             TEXT,
        first_name           TEXT,
        bars                 TEXT NOT NULL DEFAULT '[]',
        subscribed           INTEGER NOT NULL DEFAULT 0,
        consent_at           TEXT,
        consent_text_version TEXT,
        unsubscribed_at      TEXT,
        blocked_at           TEXT,
        phone                TEXT,
        guest_id             TEXT,
        created_at           TEXT NOT NULL,
        updated_at           TEXT NOT NULL,
        last_seen_at         TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_subscribers_active ON subscribers(subscribed, blocked_at)",
)
# v2: состояние диалога бота (см. «Таблица dialogs» в докстринге).
_SCHEMA_V2_SQL = (
    """
    CREATE TABLE IF NOT EXISTS dialogs (
        chat_id    INTEGER PRIMARY KEY,
        state      TEXT NOT NULL,
        updated_ts REAL NOT NULL
    )
    """,
)

_ACTIVE_SQL = ("SELECT chat_id, user_id, username, first_name, bars, phone, guest_id "
               "FROM subscribers WHERE subscribed = 1 AND blocked_at IS NULL ORDER BY chat_id")


# ----------------------------------------------------------------- чистые функции

def canon_phone(value, international: bool = False) -> str:
    """Телефон -> канон (правила — докстринг модуля, «Телефон»); не телефон -> ''.

    Российская форма -> '7' + 10 цифр (то же, что core/guest_sync.normalize_guest_id
    даёт для этих форм, — по нему посчитан guest_id витрины гостей). Прочее —
    зарубежный номер: '+' и цифры как есть. international=True (контакт Telegram) и
    номер, записанный с '+', содержат код страны: российский — только 7 и 10 цифр.
    Цифры — только ASCII 0-9 (иначе «٣» из другой письменности давала бы другой канон).
    """
    raw = str(value or '').strip()
    digits = ''.join(ch for ch in raw if ch in '0123456789')
    n = len(digits)
    if international or raw.startswith('+'):
        if n == 11 and digits[0] == '7':
            return digits
    elif n == 10 and digits[0] == '9':
        return normalize_guest_id(digits)
    elif n == 11 and digits[0] in '78':
        return normalize_guest_id(digits)
    elif n == 12 and digits.startswith('77'):
        return normalize_guest_id(digits)
    if FOREIGN_MIN_DIGITS <= n <= MAX_PHONE_DIGITS:
        return '+' + digits
    return ''


def is_russian_phone(canon: Optional[str]) -> bool:
    """Российский канон ('7' + 10 цифр): только такой ищется в витрине гостей."""
    return bool(canon) and not canon.startswith('+') and len(canon) == 11


def phone_display(canon: Optional[str]) -> str:
    """Канон -> как номер набирают: '79991234567' -> '+79991234567'; зарубежный '+…' — как есть."""
    if not canon:
        return ''
    return canon if canon.startswith('+') else '+' + canon


def _bar_key(value) -> str:
    key = str(value or '').strip()
    if key not in BAR_KEYS:
        raise ValueError(f'Неизвестный бар «{value}»')
    return key


def check_bar(value) -> Optional[str]:
    """Бар размещения: None, '' или 'all' -> None (вся сеть); иначе ключ бара или ValueError."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == NETWORK_BAR:
        return None
    return _bar_key(text)


def check_segment(value) -> str:
    seg = str(value or '').strip()
    if seg not in SEGMENTS:
        raise ValueError(f'Неизвестная аудитория «{value}»')
    return seg


def normalize_bars(bars: Optional[Iterable]) -> List[str]:
    """Проверить выбор баров: ключи сети, без повторов, в порядке сети; все четыре -> [].

    None -> [] (все бары). Строка вместо списка и неизвестный ключ -> ValueError.
    """
    if bars is None:
        return []
    if isinstance(bars, (str, bytes)) or not isinstance(bars, Iterable):
        raise ValueError('Бары: нужен список')
    chosen = {_bar_key(b) for b in bars}
    out = [k for k in BAR_KEYS if k in chosen]
    return [] if len(out) == len(BAR_KEYS) else out


def bars_to_mask(bars) -> int:
    """Выбор баров -> маска (бит i — BAR_KEYS[i]); все бары = 0."""
    return sum(1 << BAR_KEYS.index(k) for k in normalize_bars(bars))


def mask_to_bars(mask) -> List[str]:
    """Маска из кнопки бота -> выбор баров. Не целое 0..2^N-1 -> ValueError."""
    if isinstance(mask, bool):
        raise ValueError('Маска баров: нужно целое число')
    m = int(str(mask).strip())
    if not 0 <= m < (1 << len(BAR_KEYS)):
        raise ValueError(f'Маска баров вне диапазона: {mask}')
    return normalize_bars([k for i, k in enumerate(BAR_KEYS) if m & (1 << i)])


def toggle_bar(bars, bar) -> List[str]:
    """Отметить или снять бар. Снят последний -> [] (все бары); отмечены все -> []."""
    current = normalize_bars(bars)
    key = _bar_key(bar)
    if key in current:
        current.remove(key)
    else:
        current.append(key)
    return normalize_bars(current)


def wants_bar(bars: List[str], bar: str) -> bool:
    """Получает ли подписчик новости бара: выбрал «Все бары» ([]) или этот бар."""
    return not bars or bar in bars


def bars_label(bars) -> str:
    """Выбор баров словами: [] -> 'все бары'; иначе названия через запятую."""
    if not bars:
        return 'все бары'
    names = [BAR_NAMES[k] for k in BAR_KEYS if k in bars]
    return ', '.join(names) if names else 'только новости всей сети'


def days_since(last_visit, today: date) -> Optional[int]:
    """Сколько дней от даты визита до today; дата не читается -> None."""
    try:
        visit = date.fromisoformat(str(last_visit or '')[:10])
    except ValueError:
        return None
    return (today - visit).days


def visit_matches(segment: str, last_visit, today: date) -> bool:
    """Попадает ли последний визит в сегмент по визитам (правило — докстринг модуля).

    Дата визита позже сегодня (часы разошлись) считается недавним визитом.
    """
    n = days_since(last_visit, today)
    if n is None:
        return False
    if segment == 'bot_recent_30':
        return n < RECENT_DAYS
    if segment == 'bot_lapsed_60':
        return n >= LAPSED_DAYS
    return False


def resolve_guest(index: Optional[dict], phone, stored_guest_id=None) -> Optional[dict]:
    """Гость витрины для подписчика -> {guest_id, last_visit_date} или None.

    index — снимок витрины (SubscriberStore._guest_index): by_id {guest_id: last_visit},
    by_phone {phone: (guest_id, last_visit)}, aliases {alias: guest_id}. Порядок поиска
    — докстринг модуля («Связка с гостем»).
    """
    if not index:
        return None
    canon = canon_phone(phone)
    if phone and not is_russian_phone(canon):
        return None               # зарубежный номер в витрине не ищется (канон витрины — российский)
    by_id = index['by_id']
    if stored_guest_id and stored_guest_id in by_id:
        return {'guest_id': stored_guest_id, 'last_visit_date': by_id[stored_guest_id]}
    if not canon:
        return None
    if canon in by_id:
        return {'guest_id': canon, 'last_visit_date': by_id[canon]}
    hit = index['by_phone'].get(canon)
    if hit:
        return {'guest_id': hit[0], 'last_visit_date': hit[1]}
    target = index['aliases'].get(canon)
    if target and target in by_id:
        return {'guest_id': target, 'last_visit_date': by_id[target]}
    return None


def _chat_id(value) -> int:
    if isinstance(value, bool):
        raise ValueError('chat_id: нужно целое число')
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f'chat_id: нужно целое число, а не «{value}»')


def _clean_name(value) -> Optional[str]:
    if value is None:
        return None
    text = ' '.join(str(value).split())[:MAX_NAME_LEN]
    return text or None


def _clean_username(value) -> Optional[str]:
    """Ник без @ и пробелов по краям; пусто -> None."""
    text = _clean_name(value)
    if not text:
        return None
    return text.lstrip('@') or None


def _load_bars(raw) -> List[str]:
    """bars из базы. Пишет их только этот модуль; битое значение (не бывает, но если)
    становится списком с неизвестным ключом: такой подписчик получает лишь рассылки
    на всю сеть — шире выбора гостя не шлём."""
    try:
        value = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        print(f'[GUEST-SUBS] битый выбор баров: {raw!r}')
        return ['?']
    if not isinstance(value, list):
        return ['?']
    return [str(v) for v in value]


def _row(row) -> dict:
    out = dict(row)
    out['bars'] = _load_bars(out.get('bars'))
    if 'subscribed' in out:
        out['subscribed'] = bool(out['subscribed'])
    return out


# ----------------------------------------------------------------- хранилище

class SubscriberStore:
    """Подписчики бота в SQLite. Потокобезопасно; несколько процессов — через WAL."""

    def __init__(self, db_path: Optional[str] = None, guests_db_path: Optional[str] = None,
                 clock: Optional[Callable[[], datetime]] = None):
        self.db_path = db_path or get_data_path(DB_FILE_NAME)
        self.guests_db_path = guests_db_path
        self._clock = clock or msk_time.now
        self._lock = threading.Lock()
        self._init_db()

    # ----- соединения -----------------------------------------------------

    def _connect(self, **kwargs) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10, **kwargs)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=5000')
        conn.execute('PRAGMA synchronous=NORMAL')
        return conn

    @contextmanager
    def _read(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write(self):
        """Транзакция записи: BEGIN IMMEDIATE сразу берёт блокировку записи SQLite, и
        проверка + запись атомарны и между процессами (как auth_manager._write_txn)."""
        with self._lock:
            conn = self._connect(isolation_level=None)
            try:
                conn.execute('BEGIN IMMEDIATE')
                try:
                    yield conn
                    conn.execute('COMMIT')
                except Exception:
                    conn.execute('ROLLBACK')
                    raise
            finally:
                conn.close()

    def _init_db(self) -> None:
        folder = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(folder, exist_ok=True)
        with self._write() as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version < 1:
                for sql in _SCHEMA_SQL:
                    conn.execute(sql)
            if version < 2:
                for sql in _SCHEMA_V2_SQL:
                    conn.execute(sql)
            if version < SCHEMA_VERSION:
                conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')

    # ----- время ----------------------------------------------------------

    def now(self) -> datetime:
        """«Сейчас» по Москве, наивное, с точностью до секунды."""
        moment = self._clock()
        if moment.tzinfo is not None:
            moment = moment.astimezone(msk_time.MOSCOW_TZ).replace(tzinfo=None)
        return moment.replace(microsecond=0)

    def _stamp(self) -> str:
        return self.now().strftime(STAMP_FORMAT)

    def today(self) -> date:
        return self.now().date()

    # ----- запись ---------------------------------------------------------

    def subscribe(self, chat_id, *, user_id=None, username=None, first_name=None,
                  consent_version: str = CONSENT_VERSION) -> dict:
        """«Согласен»: подписать чат (правила — докстринг модуля). Ответ — строка подписчика.

        Имя, ник и user_id обновляются, если передан хоть один из них (бот передаёт все
        три из профиля Telegram: ника нет -> ник стирается).
        """
        cid = _chat_id(chat_id)
        if consent_version not in CONSENT_TEXTS:
            raise ValueError(f'Неизвестная версия текста согласия «{consent_version}»')
        stamp = self._stamp()
        uid = _chat_id(user_id) if user_id is not None else None
        uname, fname = _clean_username(username), _clean_name(first_name)
        profile = any(v is not None for v in (user_id, username, first_name))
        with self._write() as conn:
            row = conn.execute('SELECT subscribed FROM subscribers WHERE chat_id = ?', (cid,)).fetchone()
            if row is None:
                conn.execute(
                    'INSERT INTO subscribers (chat_id, user_id, username, first_name, bars, subscribed, '
                    'consent_at, consent_text_version, created_at, updated_at, last_seen_at) '
                    "VALUES (?, ?, ?, ?, '[]', 1, ?, ?, ?, ?, ?)",
                    (cid, uid, uname, fname, stamp, consent_version, stamp, stamp, stamp))
            else:
                if not row['subscribed']:
                    conn.execute(
                        'UPDATE subscribers SET subscribed = 1, consent_at = ?, consent_text_version = ?, '
                        'unsubscribed_at = NULL, updated_at = ? WHERE chat_id = ?',
                        (stamp, consent_version, stamp, cid))
                conn.execute('UPDATE subscribers SET blocked_at = NULL, last_seen_at = ? WHERE chat_id = ?',
                             (stamp, cid))
                if profile:
                    conn.execute('UPDATE subscribers SET user_id = ?, username = ?, first_name = ? '
                                 'WHERE chat_id = ?', (uid, uname, fname, cid))
            out = conn.execute('SELECT * FROM subscribers WHERE chat_id = ?', (cid,)).fetchone()
        return _row(out)

    def set_bars(self, chat_id, bars) -> bool:
        """Сохранить выбор баров подписанного чата. False — чат не подписан."""
        cid = _chat_id(chat_id)
        clean = normalize_bars(bars)
        with self._write() as conn:
            cur = conn.execute('UPDATE subscribers SET bars = ?, updated_at = ? '
                               'WHERE chat_id = ? AND subscribed = 1',
                               (json.dumps(clean), self._stamp(), cid))
            return cur.rowcount > 0

    def set_phone(self, chat_id, phone, international: bool = False) -> Optional[dict]:
        """Сохранить телефон подписанного чата и связать с гостем витрины.

        Ответ — {phone (канон), guest_id, last_visit_date} или None (чат не подписан).
        Не телефон -> ValueError. Проверку «номер свой» делает бот; он же передаёт
        international=True (в контакте Telegram номер всегда с кодом страны).
        Зарубежный номер сохраняется как есть и с гостем витрины не связывается.
        """
        cid = _chat_id(chat_id)
        canon = canon_phone(phone, international=international)
        if not canon:
            raise ValueError('Не похоже на номер телефона')
        guest = self.find_guest(canon) if is_russian_phone(canon) else None
        gid = guest['guest_id'] if guest else None
        with self._write() as conn:
            cur = conn.execute('UPDATE subscribers SET phone = ?, guest_id = ?, updated_at = ? '
                               'WHERE chat_id = ? AND subscribed = 1', (canon, gid, self._stamp(), cid))
            if cur.rowcount == 0:
                return None
        return {'phone': canon, 'guest_id': gid,
                'last_visit_date': guest['last_visit_date'] if guest else None}

    def unsubscribe(self, chat_id) -> bool:
        """Отписать: subscribed=0, телефон и guest_id стираются. False — и так не подписан."""
        cid = _chat_id(chat_id)
        stamp = self._stamp()
        with self._write() as conn:
            cur = conn.execute('UPDATE subscribers SET subscribed = 0, unsubscribed_at = ?, phone = NULL, '
                               'guest_id = NULL, updated_at = ? WHERE chat_id = ? AND subscribed = 1',
                               (stamp, stamp, cid))
            return cur.rowcount > 0

    def mark_blocked(self, chat_id) -> bool:
        """Гость заблокировал бота: рассылка ему не уходит. True — отметка поставлена сейчас."""
        cid = _chat_id(chat_id)
        stamp = self._stamp()
        with self._write() as conn:
            cur = conn.execute('UPDATE subscribers SET blocked_at = ?, updated_at = ? '
                               'WHERE chat_id = ? AND blocked_at IS NULL', (stamp, stamp, cid))
            return cur.rowcount > 0

    def mark_unblocked(self, chat_id) -> bool:
        """Гость разблокировал бота (my_chat_member «member»). True — отметка снята."""
        cid = _chat_id(chat_id)
        with self._write() as conn:
            cur = conn.execute('UPDATE subscribers SET blocked_at = NULL, updated_at = ? '
                               'WHERE chat_id = ? AND blocked_at IS NOT NULL', (self._stamp(), cid))
            return cur.rowcount > 0

    def touch(self, chat_id, *, user_id=None, username=None, first_name=None) -> bool:
        """Гость написал боту: last_seen_at, снять blocked_at (раз пишет — не блокирует),
        обновить имя и ник. Только у ПОДПИСАННОГО (subscribed = 1): об отписавшемся
        новые данные не копим. False — строки нет или гость отписан."""
        cid = _chat_id(chat_id)
        stamp = self._stamp()
        profile = any(v is not None for v in (user_id, username, first_name))
        uid = _chat_id(user_id) if user_id is not None else None
        with self._write() as conn:
            if profile:
                cur = conn.execute('UPDATE subscribers SET last_seen_at = ?, blocked_at = NULL, user_id = ?, '
                                   'username = ?, first_name = ? WHERE chat_id = ? AND subscribed = 1',
                                   (stamp, uid, _clean_username(username), _clean_name(first_name), cid))
            else:
                cur = conn.execute('UPDATE subscribers SET last_seen_at = ?, blocked_at = NULL '
                                   'WHERE chat_id = ? AND subscribed = 1', (stamp, cid))
            return cur.rowcount > 0

    # ----- состояние диалога бота (таблица dialogs) -----------------------

    def dialog_get(self, chat_id):
        """(state dict, updated_ts) или None. Сроки (таймаут) решает бот."""
        cid = _chat_id(chat_id)
        with self._read() as conn:
            row = conn.execute('SELECT state, updated_ts FROM dialogs WHERE chat_id = ?', (cid,)).fetchone()
        if row is None:
            return None
        try:
            state = json.loads(row['state'])
        except (TypeError, ValueError):
            return None
        return (state, float(row['updated_ts'])) if isinstance(state, dict) else None

    def dialog_set(self, chat_id, state: dict, ts: float) -> None:
        cid = _chat_id(chat_id)
        with self._write() as conn:
            conn.execute('INSERT INTO dialogs (chat_id, state, updated_ts) VALUES (?, ?, ?) '
                         'ON CONFLICT(chat_id) DO UPDATE SET state = excluded.state, '
                         'updated_ts = excluded.updated_ts',
                         (cid, json.dumps(state, ensure_ascii=False), float(ts)))

    def dialog_clear(self, chat_id) -> None:
        cid = _chat_id(chat_id)
        with self._write() as conn:
            conn.execute('DELETE FROM dialogs WHERE chat_id = ?', (cid,))

    def dialog_sweep(self, older_than_ts: float) -> int:
        """Забыть шаги диалога старше older_than_ts (unix-время). Ответ — сколько удалено."""
        with self._write() as conn:
            return conn.execute('DELETE FROM dialogs WHERE updated_ts < ?', (float(older_than_ts),)).rowcount

    # ----- чтение ---------------------------------------------------------

    def get(self, chat_id) -> Optional[dict]:
        cid = _chat_id(chat_id)
        with self._read() as conn:
            row = conn.execute('SELECT * FROM subscribers WHERE chat_id = ?', (cid,)).fetchone()
        return _row(row) if row else None

    def is_subscribed(self, chat_id) -> bool:
        row = self.get(chat_id)
        return bool(row and row['subscribed'])

    def recipients(self, segment, bar=None, today: Optional[date] = None) -> List[dict]:
        """Получатели рассылки сегмента (правила — докстринг модуля, «Сегменты»)."""
        seg = check_segment(segment)
        bar_key = check_bar(bar)
        if seg == 'bot_bar' and bar_key is None:
            raise ValueError('Для аудитории «Подписчики, выбравшие бар» нужен бар')
        with self._read() as conn:
            rows = [_row(r) for r in conn.execute(_ACTIVE_SQL)]
        if bar_key is not None:
            rows = [r for r in rows if wants_bar(r['bars'], bar_key)]
        last_visit: Dict[int, Optional[str]] = {}
        if seg in VISIT_SEGMENTS:
            day = today or self.today()
            candidates = [r for r in rows if r.get('phone') or r.get('guest_id')]
            index = self._guest_index() if candidates else None
            kept = []
            for r in candidates:
                guest = resolve_guest(index, r.get('phone'), r.get('guest_id'))
                if guest and visit_matches(seg, guest['last_visit_date'], day):
                    last_visit[r['chat_id']] = guest['last_visit_date']
                    kept.append(r)
            rows = kept
        return [{'chat_id': r['chat_id'], 'username': r.get('username'), 'first_name': r.get('first_name'),
                 'bars': r['bars'], 'guest_id': r.get('guest_id'),
                 'last_visit_date': last_visit.get(r['chat_id'])} for r in rows]

    def audience_size(self, segment, bar=None, today: Optional[date] = None) -> int:
        return len(self.recipients(segment, bar, today))

    def stats(self) -> dict:
        """Сводка подписчиков; смысл каждого числа — STATS_RULES."""
        with self._read() as conn:
            rows = [_row(r) for r in conn.execute(
                'SELECT chat_id, bars, subscribed, blocked_at, phone, guest_id FROM subscribers')]
        active = [r for r in rows if r['subscribed'] and not r.get('blocked_at')]
        return {
            'total': len(rows),
            'subscribed': len(active),
            'with_phone': sum(1 for r in active if r.get('phone')),
            'linked': sum(1 for r in active if r.get('guest_id')),
            'all_bars': sum(1 for r in active if not r['bars']),
            'by_bar': {k: sum(1 for r in active if wants_bar(r['bars'], k)) for k in BAR_KEYS},
            'unsubscribed': sum(1 for r in rows if not r['subscribed']),
            'blocked': sum(1 for r in rows if r['subscribed'] and r.get('blocked_at')),
            'consent_version': CONSENT_VERSION,
        }

    # ----- витрина гостей -------------------------------------------------

    def _guests_path(self) -> str:
        if self.guests_db_path:
            return self.guests_db_path
        # Тот же путь, что у самой витрины (core/guest_store): /kultura/guests.db на проде.
        from core.guest_store import _default_db_path
        return _default_db_path()

    def _guest_index(self) -> Optional[dict]:
        """Снимок витрины для связки по телефону; нет файла или не читается -> None.

        Только чтение (PRAGMA query_only): витрину пишет лишь ночной синк. Файла нет —
        не создаём (sqlite3.connect создал бы пустую базу). ~4 тыс. гостей — весь снимок
        читается за миллисекунды, поэтому без выборочных запросов.
        """
        path = self._guests_path()
        if not path or not os.path.exists(path):
            return None
        try:
            conn = sqlite3.connect(path, timeout=15)
        except sqlite3.Error as e:
            print(f'[GUEST-SUBS] витрина гостей не открылась ({e}) — связки по телефону нет')
            return None
        try:
            conn.execute('PRAGMA query_only = ON')
            conn.execute('PRAGMA busy_timeout = 5000')
            by_id, by_phone = {}, {}
            for gid, phone, last in conn.execute('SELECT guest_id, phone, last_visit_date FROM guests'):
                by_id[gid] = last
                if phone:
                    prev = by_phone.get(phone)
                    if prev is None or ((last or ''), prev[0]) > ((prev[1] or ''), gid):
                        by_phone[phone] = (gid, last)
            aliases = {alias: gid for alias, gid in conn.execute('SELECT alias, guest_id FROM guest_aliases')}
        except sqlite3.Error as e:
            print(f'[GUEST-SUBS] витрина гостей не читается ({e}) — связки по телефону нет')
            return None
        finally:
            conn.close()
        return {'by_id': by_id, 'by_phone': by_phone, 'aliases': aliases}

    def find_guest(self, phone) -> Optional[dict]:
        """Гость витрины по телефону -> {guest_id, last_visit_date} или None.
        Зарубежный номер в витрине не ищется (её канон — российский)."""
        canon = canon_phone(phone)
        if not is_russian_phone(canon):
            return None
        return resolve_guest(self._guest_index(), canon)


# ----------------------------------------------------------------- общий экземпляр

_store: Optional[SubscriberStore] = None
_store_guard = threading.Lock()


def get_store(db_path: Optional[str] = None, guests_db_path: Optional[str] = None,
              clock: Optional[Callable[[], datetime]] = None) -> SubscriberStore:
    """Ленивый общий экземпляр на процесс. С аргументами (тесты, стенд) — пересоздаётся с ними."""
    global _store
    with _store_guard:
        if db_path is not None or guests_db_path is not None or clock is not None:
            _store = SubscriberStore(db_path, guests_db_path, clock)
        elif _store is None:
            _store = SubscriberStore()
        return _store


def set_store(store: Optional[SubscriberStore]) -> Optional[SubscriberStore]:
    """Подставить свой экземпляр (тесты); ответ — прежний (None — ещё не создавался)."""
    global _store
    with _store_guard:
        previous, _store = _store, store
        return previous


def audience_size(segment, bar=None) -> int:
    """Сколько подписчиков получит рассылку сегмента (для контент-плана)."""
    return get_store().audience_size(segment, bar)


def recipients(segment, bar=None) -> List[dict]:
    """Кому отправлять рассылку сегмента (для core/content_publisher.py)."""
    return get_store().recipients(segment, bar)


def mark_blocked(chat_id) -> bool:
    """Telegram ответил 403 (бот заблокирован) — больше не слать этому чату."""
    return get_store().mark_blocked(chat_id)


def stats() -> dict:
    """Сводка подписчиков (для страницы каналов контент-плана)."""
    return get_store().stats()
