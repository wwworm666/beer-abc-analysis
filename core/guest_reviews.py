"""Отзывы гостей (раздел «Гости» -> «Отзывы»): хранилище, проверка, метрики.

Зачем. Отзывы с Яндекс Карт и из бота собираются в одном месте, чтобы на
каждый ответили и было видно, сколько отзывов ждут ответа и как быстро
отвечаем. На этом этапе (2026-09-26) интеграций нет: отзывы вносятся вручную,
ответ никуда не отправляется (reply.delivered всегда false) — его копируют и
публикуют в источнике руками.

Хранение. guest_reviews.json на постоянном томе (/kultura) или в data/ локально
(core/storage_paths.get_data_path), формат {version: 1, reviews: {id: R}}.
Запись: threading.Lock + межпроцессный file_lock(<файл>.lock) + строгое
перечитывание файла + atomic_write_json (как core/supplier_directory.py).
Файла нет -> пустое хранилище. Файл есть, но не читается, не JSON, неожиданной
структуры или с битой записью -> ReviewStoreUnavailable и на чтении, и на
записи (API отвечает 503 {error, code: 'reviews_unavailable'}); файл при этом
НИКОГДА не перезаписывается — иначе одна правка стёрла бы все отзывы.

Запись R:
    id            'r_' + 12 hex (secrets.token_hex(6))
    source        'yandex' (Яндекс Карты) | 'bot' (Бот)
    bar           конкретный бар из venues_config.PHYSICAL_VENUES ('all' нельзя)
    rating        null | целое 1..5
    author        строка до 120 знаков, может быть пустой
    text          строка до 5000 знаков
    created_at    'YYYY-MM-DDTHH:MM' по Москве — когда гость оставил отзыв
    status        'new' (без ответа) | 'answered' (отвечен) | 'skipped' (без ответа по решению)
    reply         null | {text, at, by, delivered: false[, edited_at, edited_by]}
    reply_draft   черновик ответа (автосохранение), до 4000 знаков; хранится как
                  набран — без обрезки пробелов по краям (см. «Проверка полей»)
    skip_reason   причина «оставить без ответа», до 500 знаков
    guest         null | {phone, telegram} — только у отзывов из бота
    external_id   null | строка — id в источнике для будущего импорта
                  (повтор (source, external_id) при импорте -> конфликт)
    origin        'manual' (внесён вручную) | 'import' (будущая загрузка)
    material_id   null | id материала контент-плана, сделанного из отзыва
                  (материал могут удалить в контент-плане — см. material_exists)
    added_at, added_by, updated_at, updated_by

Проверка полей (ValueError с понятным текстом -> 400):
- источник обязателен и один из SOURCES;
- бар обязателен и конкретный;
- оценка: пусто/null = без оценки, иначе целое 1..5 ('4' и 4.0 принимаются,
  4.5, 0, 6, true — нет); у отзыва с Яндекс Карт оценка обязательна (там
  отзыв без оценки не оставить), у отзыва из бота — нет. Запись оценки
  длиннее MAX_RATING_INPUT_LEN (10) знаков отклоняется сразу, а границы 1..5
  проверяются ДО перевода в int: запись вида «1e3000000» Decimal принимает
  мгновенно, но int() от неё строил бы число из миллионов цифр — минуты
  процессора под блокировкой файла отзывов;
- нужен текст или оценка (пустой отзыв без оценки бессмыслен);
- дата отзыва 'YYYY-MM-DDTHH:MM' (допустимы секунды и пробел вместо T;
  секунды отбрасываются), год 2010..2100; не позже «сейчас + 5 минут»
  (FUTURE_TOLERANCE: запас на расхождение часов телефона и сервера); при
  добавлении без даты берётся текущий момент;
- контакты гостя есть только у отзывов из бота: у отзыва с Яндекс Карт поле
  guest игнорируется (становится null); пустые телефон и telegram -> null;
- текстовые поля обрезаются по краям, \\r\\n -> \\n, длина проверяется после.
  Исключение — черновик ответа (reply_draft): он хранится как набран
  (\\r\\n -> \\n, длина проверяется без обрезки), потому что автосохранение
  идёт посреди набора — обрезанный пробел или перевод строки в конце
  пропал бы после перезагрузки страницы, и продолжение приклеилось бы к
  последнему предложению. Черновик из одних пробелов -> ''. Сам ответ
  (reply) по-прежнему обрезается по краям.

Правка (update): меняются bar, rating, author, text, created_at, guest,
reply_draft; source — только у внесённых вручную (исправление ошибки ввода).
После слияния запись проверяется целиком по правилам выше.

Переходы статуса:
- reply(text 1..4000): new -> answered; у answered — правка текста ответа
  (момент ответа reply.at сохраняется, пишутся edited_at/edited_by —
  метрика времени ответа не «молодеет» от правки); у skipped — конфликт
  (сначала «Вернуть в работу»). Черновик после ответа очищается.
  Лимит 4000 знаков — с запасом внутри лимита сообщения Telegram (4096),
  чтобы ответ на отзыв из бота потом ушёл одним сообщением.
- skip(reason до 500 знаков, необязательна): только new -> skipped.
- reopen: skipped | answered -> new. Ответ и причина пропуска остаются для
  истории; новый ответ после возврата заменяет прежний (с новым reply.at —
  время ответа считается до него, см. response_hours).
- delete: только origin 'manual' (импортированный отзыв пришёл бы снова).
- link_material: один материал на отзыв; повторно -> конфликт с id
  существующего материала. replace=<id> перезаписывает ссылку, только если
  в записи всё ещё этот id: так «Сделать материалом» заменяет ссылку на
  удалённый в контент-плане материал, а параллельный запрос, успевший
  привязать другой материал, по-прежнему получает конфликт с его id.

Список (listing) — фильтры:
- период по ДАТЕ created_at, включительно: all=1 — без периода; иначе from/to
  ('YYYY-MM-DD', любой из них можно опустить); иначе month='YYYY-MM'; иначе
  текущий месяц по Москве;
- bar (конкретный; '' или 'all' = вся сеть), source, status;
- rating: low = 1–2, mid = 3, high = 4–5, none = без оценки.
Сортировка: сначала status new по created_at по возрастанию (дольше всех
ждущий — первым), затем остальные по created_at по убыванию; при равной дате
— по id по возрастанию (детерминированно).
К каждому отзыву добавляются:
    age_hours      = (сейчас − created_at) в часах, только у new, иначе null;
    response_hours = (reply.at − created_at) в часах, только у answered, иначе null;
                     reply.at — сохранение ответа, которым отзыв перешёл в
                     «Отвечен»: правка ответа его не меняет, после «Вернуть в
                     работу» им становится следующее сохранение ответа;
оба — не меньше 0 (дата отзыва может быть до 5 минут «в будущем»), разница
в целых минутах (время хранится с точностью до минуты), часы = минуты / 60,
округление half-up до 0,1.
    material_exists = есть ли ещё в контент-плане материал из material_id:
                     true — есть; false — ссылка есть, а материала нет (его
                     удалили в контент-плане; «Сделать материалом» снова
                     доступно и заменит ссылку); null — ссылки нет или
                     контент-план недоступен («не проверялось»).
Проверку материалов делает вызывающий (routes/reviews.py) функцией
material_lookup(ids) -> {id: bool} | None: модуль отзывов от контент-плана не
зависит. Она вызывается один раз на запрос — для всех разных id у отзывов
ответа (resolve_materials); её сбой даёт null, а не ошибку списка.

Метрики (metrics.total и metrics.by_bar[бар] для всех четырёх баров) считаются
по отзывам, прошедшим ТОЛЬКО фильтры периода и источника (бар, оценка и статус
на метрики не влияют, чтобы карточки баров оставались сравнимыми):
    count                   число отзывов
    rated                   число отзывов с оценкой
    avg_rating              half-up(сумма оценок / rated, 0,1); rated = 0 -> null
                            (4,25 -> 4,3; 4,35 -> 4,4)
    unanswered              число отзывов со статусом new
    answered, skipped       число отзывов в этих статусах
    unanswered_pct          half-up(unanswered / count × 100, целое); count = 0 -> null
                            (12,5 -> 13)
    median_response_hours   медиана response_hours по отзывам со статусом answered:
                            значения (точные, в минутах) сортируются; нечётное
                            число — среднее по порядку, чётное — полусумма двух
                            средних; затем / 60 и half-up до 0,1; нет ответов -> null.
                            Отзывы, возвращённые в работу (new с прежним ответом),
                            и пропущенные не учитываются.
    oldest_unanswered_hours max(age_hours) по new, half-up до 0,1; нет new -> null
Округление — decimal ROUND_HALF_UP через Decimal(str(x)), никогда round():
round(4.35, 1) в Python даёт 4.3 из-за двоичного представления.
Те же формулы — строками в FORMULAS (API отдаёт их для подсказок в интерфейсе).

Загрузка из источника (upsert_imported, Яндекс Бизнес — docs/yandex-reviews.md):
запись с origin 'import' ищется по паре (source, external_id); нет — создаётся,
есть — обновляются оценка, текст, автор, фото. Статус новой записи:
    в источнике есть ответ организации  -> answered, reply = ответ источника
                                           ({text, at: время ответа в источнике,
                                           by, delivered: true, source});
    ответа нет, дата отзыва < history_cutoff -> skipped с причиной
                                           HISTORY_SKIP_REASON (история до
                                           подключения сервиса, решение владельца
                                           2026-09-28);
    иначе                                -> new.
У существующей записи ответ источника: при new/skipped -> answered с этим
ответом; при нашем answered (сохранён здесь) -> reply.delivered = true, момент
ответа не меняется (published_at, source_text — что и когда вышло в источнике);
при ответе источника — правка текста (reply.at не «молодеет»). Ответ
источника пропал -> new, прежний ответ остаётся для истории. Отзыв пропал из
полного прохода (complete) -> gone_at, запись НЕ удаляется; вернулся ->
gone_at снимается. Дополнительные поля загруженных: photos, author_avatar,
public_rating, gone_at.

Слой календаря (daily): за месяц по дням created_at —
{count, rated, avg}, avg — как avg_rating; дни без отзывов не выводятся.

Время: всё по Москве (core/msk_time), в файле — наивные строки. «Сейчас»
берётся из часов хранилища (clock, подменяется в тестах) и обрезается до минуты.
"""
import copy
import json
import os
import re
import secrets
import threading
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Dict, Iterable, List, Mapping, Optional

from core import msk_time
from core.json_store import atomic_write_json, file_lock
from core.storage_paths import get_data_path
from core.venues_config import PHYSICAL_VENUES, VENUES

SCHEMA_VERSION = 1
DATA_FILE_NAME = 'guest_reviews.json'

# Источники отзывов (порядок = порядок в интерфейсе).
SOURCES = (('yandex', 'Яндекс Карты'), ('bot', 'Бот'))
SOURCE_KEYS = tuple(k for k, _ in SOURCES)

# Короткие имена баров для карточек и заголовков материалов (spec, раздел 0).
BAR_SHORT = {'bolshoy': 'ВО', 'ligovskiy': 'Лиг', 'kremenchugskaya': 'Крем', 'varshavskaya': 'Вар'}
BARS = [{'key': k, 'name': VENUES[k]['name'], 'short': BAR_SHORT.get(k, VENUES[k]['name'])}
        for k in PHYSICAL_VENUES]
BAR_KEYS = tuple(PHYSICAL_VENUES)
NETWORK_BAR = 'all'   # в фильтрах: вся сеть; у самого отзыва недопустим

STATUSES = ('new', 'answered', 'skipped')
ORIGINS = ('manual', 'import')

RATING_MIN, RATING_MAX = 1, 5          # шкала Яндекс Карт и бота
# Самая длинная разумная запись оценки — «5.000» или « 4 » с пробелами; 10 знаков —
# с запасом. Длиннее — заведомо не оценка: отклоняется до разбора числа (см. _rating).
MAX_RATING_INPUT_LEN = 10
# Корзины фильтра оценки: низкие / средние / высокие; 'none' — без оценки.
RATING_BUCKETS = {'low': (1, 2), 'mid': (3, 3), 'high': (4, 5)}
RATING_FILTERS = ('low', 'mid', 'high', 'none')

MAX_AUTHOR_LEN = 120        # имя в профиле Яндекса/Telegram с запасом
MAX_TEXT_LEN = 5000         # отзыв на Яндекс Картах короче; запас на пересказ из бота
MAX_REPLY_LEN = 4000        # внутри лимита сообщения Telegram 4096 — ответ уйдёт одним сообщением
MAX_SKIP_REASON_LEN = 500   # короткая причина «почему без ответа»
MAX_PHONE_LEN = 32          # +7 и форматирование с пробелами/скобками
MAX_TELEGRAM_LEN = 64       # @username (до 32) или ссылка t.me/...
MAX_EXTERNAL_ID_LEN = 200   # id отзыва в источнике (для будущего импорта)
MAX_MATERIAL_ID_LEN = 64

# Загрузка из источника (upsert_imported). Причина для истории до подключения:
# отзывы без ответа старше history_cutoff не попадают в «Без ответа» — иначе
# первая загрузка вывалила бы в работу сотню отзывов 2019–2025 годов
# (решение владельца 2026-09-28, docs/yandex-reviews.md).
HISTORY_SKIP_REASON = 'До подключения сервиса: в Яндексе без ответа'
MAX_IMPORT_PROBLEMS = 20    # сколько замечаний загрузки хранить в сводке

# Дата отзыва может быть чуть «в будущем»: часы телефона, с которого вносят
# отзыв, и сервера расходятся на минуты. Больше 5 минут — явная ошибка ввода.
FUTURE_TOLERANCE = timedelta(minutes=5)
# Нижняя граница года: самые старые отзывы наших баров в Яндексе — июль 2018
# (Кременчугская); 2010 — с запасом. Было 2020, и загрузка из Яндекса отбрасывала
# 19 отзывов 2018–2019 годов (2026-09-28).
YEAR_MIN, YEAR_MAX = 2010, 2100

DT_FORMAT = '%Y-%m-%dT%H:%M'
_DT_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$')
_DATE_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')
_MONTH_RE = re.compile(r'^(\d{4})-(\d{2})$')
_TRUE_WORDS = {'1', 'true', 'yes', 'on', 'да'}
_MISSING = object()

FORMULAS = {
    'count': 'Отзывов: все отзывы за период по выбранному источнику. Фильтры бара, оценки и статуса '
             'на карточки не влияют.',
    'rated': 'С оценкой: отзывы, где стоит оценка от 1 до 5.',
    'avg_rating': 'Средняя оценка = сумма оценок / число отзывов с оценкой. Отзывы без оценки не '
                  'учитываются. Округление до 0,1 «половина вверх»: 4,25 -> 4,3; 4,35 -> 4,4. '
                  'Нет оценок — прочерк.',
    'unanswered': 'Без ответа: отзывы в статусе «Без ответа». Оставленные без ответа по решению сюда '
                  'не входят.',
    'answered': 'Отвечены: отзывы, на которые сохранён ответ.',
    'skipped': 'Без ответа по решению: отзывы, которые решили оставить без ответа (с причиной).',
    'unanswered_pct': 'Доля без ответа = без ответа / все отзывы × 100, до целого процента '
                      '«половина вверх»: 12,5 -> 13. Нет отзывов — прочерк.',
    'median_response_hours': 'Медиана времени ответа. Время ответа = момент ответа − дата отзыва, в '
                             'часах (меньше нуля не бывает). Момент ответа — сохранение ответа, которым '
                             'отзыв перешёл в «Отвечен»: правка ответа его не меняет, после «Вернуть в '
                             'работу» им становится следующее сохранение ответа. Берутся только '
                             'отвеченные отзывы; возвращённые в работу до нового ответа не учитываются. '
                             'Значения упорядочиваются: при нечётном числе берётся среднее по порядку, '
                             'при чётном — полусумма двух средних. Округление до 0,1 ч «половина '
                             'вверх». Нет ответов — прочерк.',
    'oldest_unanswered_hours': 'Дольше всех ждёт: сейчас − дата самого раннего отзыва без ответа, в '
                               'часах, до 0,1 «половина вверх».',
    'age_hours': 'Ждёт ответа: сейчас − дата отзыва, в часах (время по Москве).',
    'response_hours': 'Время ответа = момент ответа − дата отзыва, в часах, до 0,1 «половина вверх» '
                      '(меньше нуля не бывает). Момент ответа — сохранение ответа, которым отзыв '
                      'перешёл в «Отвечен»: правка ответа его не меняет, после «Вернуть в работу» им '
                      'становится следующее сохранение ответа.',
    'period': 'Период — по дате отзыва, границы включительно, время московское. «За всё время» — без '
              'ограничения по дате.',
    'rating_filter': 'Оценки: 1–2 — низкие, 3 — средние, 4–5 — высокие; «Без оценки» — оценка не стоит '
                     '(бывает только у отзывов из бота).',
    'sort': 'Порядок: сначала отзывы без ответа, от самого давнего; затем остальные, от новых к старым.',
    'daily_avg': 'Средняя за день = сумма оценок / число отзывов с оценкой за этот день, до 0,1 '
                 '«половина вверх».',
}


class ReviewStoreUnavailable(RuntimeError):
    """Файл отзывов есть, но прочитать его нельзя: читать и писать поверх запрещено."""


class ReviewNotFound(LookupError):
    """Отзыва с таким id нет."""


class ReviewConflict(RuntimeError):
    """Действие недопустимо в текущем состоянии отзыва (API: 409)."""

    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.extra = extra


# ----------------------------------------------------------------- числа

def round_half_up(value, digits: int = 1):
    """Округление «половина вверх» через Decimal(str(x)); digits=0 -> int, иначе float.

    None -> None. Decimal принимается как есть (точные частные вроде 17/4).
    """
    if value is None:
        return None
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    q = d.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return int(q) if digits == 0 else float(q)


def median(values: Iterable) -> Optional[Decimal]:
    """Медиана: нечётное число — среднее по порядку, чётное — полусумма двух средних.

    Пустой набор -> None. Результат — Decimal (без округления).
    """
    vals = sorted(Decimal(v) if not isinstance(v, Decimal) else v for v in values)
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def _hours(minutes) -> Decimal:
    return Decimal(minutes) / Decimal(60)


def _minutes_between(start: datetime, end: datetime) -> int:
    """Целые минуты от start до end (обе даты с точностью до минуты)."""
    return int((end - start).total_seconds() // 60)


# ----------------------------------------------------------------- время

def naive_msk(dt: datetime) -> datetime:
    """Наивный московский момент с точностью до минуты (aware переводится в МСК)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(msk_time.MOSCOW_TZ).replace(tzinfo=None)
    return dt.replace(second=0, microsecond=0)


def fmt_dt(dt: datetime) -> str:
    return dt.strftime(DT_FORMAT)


def parse_dt(value, field: str = 'Дата отзыва') -> datetime:
    """'YYYY-MM-DDTHH:MM' (секунды и пробел вместо T допустимы, секунды отбрасываются)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field}: укажите дату и время')
    m = _DT_RE.match(value.strip())
    if not m:
        raise ValueError(f'{field}: нужен формат ГГГГ-ММ-ДДTЧЧ:ММ, а не «{value}»')
    y, mo, d, h, mi = (int(m.group(i)) for i in range(1, 6))
    if not YEAR_MIN <= y <= YEAR_MAX:
        raise ValueError(f'{field}: год от {YEAR_MIN} до {YEAR_MAX}')
    try:
        return datetime(y, mo, d, h, mi)
    except ValueError:
        raise ValueError(f'{field}: такой даты нет — «{value}»')


def parse_date(value, field: str = 'Дата') -> date:
    if not isinstance(value, str):
        raise ValueError(f'{field}: нужен формат ГГГГ-ММ-ДД')
    m = _DATE_RE.match(value.strip())
    if not m:
        raise ValueError(f'{field}: нужен формат ГГГГ-ММ-ДД, а не «{value}»')
    y, mo, d = (int(m.group(i)) for i in range(1, 4))
    if not YEAR_MIN <= y <= YEAR_MAX:
        raise ValueError(f'{field}: год от {YEAR_MIN} до {YEAR_MAX}')
    try:
        return date(y, mo, d)
    except ValueError:
        raise ValueError(f'{field}: такой даты нет — «{value}»')


def parse_month(value, field: str = 'Месяц') -> str:
    """'YYYY-MM' с годом YEAR_MIN..YEAR_MAX и месяцем 1..12 -> та же строка."""
    if not isinstance(value, str):
        raise ValueError(f'{field}: нужен формат ГГГГ-ММ')
    m = _MONTH_RE.match(value.strip())
    if not m:
        raise ValueError(f'{field}: нужен формат ГГГГ-ММ, а не «{value}»')
    y, mo = int(m.group(1)), int(m.group(2))
    if not YEAR_MIN <= y <= YEAR_MAX:
        raise ValueError(f'{field}: год от {YEAR_MIN} до {YEAR_MAX}')
    if not 1 <= mo <= 12:
        raise ValueError(f'{field}: месяц от 01 до 12')
    return f'{y:04d}-{mo:02d}'


def month_bounds(month: str):
    """Первый и последний день месяца 'YYYY-MM'."""
    y, mo = int(month[:4]), int(month[5:7])
    first = date(y, mo, 1)
    nxt = date(y + 1, 1, 1) if mo == 12 else date(y, mo + 1, 1)
    return first, nxt - timedelta(days=1)


# ----------------------------------------------------------------- поля

def _user_login(user: Optional[dict]) -> str:
    if not user:
        return 'unknown'
    return user.get('login') or user.get('display_name') or 'unknown'


def _as_text(value, field: str) -> str:
    """Строка с переводами строк \\n (\\r\\n и \\r -> \\n), без обрезки. null -> ''."""
    if value is None:
        return ''
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f'{field}: нужна строка')
    return str(value).replace('\r\n', '\n').replace('\r', '\n')


def _check_len(s: str, limit: int, field: str) -> str:
    if len(s) > limit:
        raise ValueError(f'{field}: длиннее {limit} знаков ({len(s)})')
    return s


def _text(value, limit: int, field: str) -> str:
    """Строка: обрезка по краям, \\r\\n -> \\n, длина <= limit (после обрезки). null -> ''."""
    return _check_len(_as_text(value, field).strip(), limit, field)


def _draft(value, limit: int, field: str) -> str:
    """Черновик ответа — как набран: \\r\\n -> \\n, длина <= limit, БЕЗ обрезки по краям.

    Черновик автосохраняется посреди набора. Если обрезать пробел или перевод
    строки в конце, после перезагрузки страницы их не станет, и продолжение
    приклеится к последнему предложению («...ожидание.В выходные...»).
    Длина считается по тексту как есть, с пробелами. Только пробелы -> ''
    (пустой черновик). Итоговый ответ (reply) обрезается отдельно, в _text.
    """
    s = _as_text(value, field)
    if not s.strip():
        return ''
    return _check_len(s, limit, field)


def _source(value) -> str:
    s = str(value or '').strip().lower()
    if not s:
        raise ValueError('Выберите источник отзыва')
    if s not in SOURCE_KEYS:
        raise ValueError(f'Неизвестный источник «{value}»')
    return s


def _bar(value) -> str:
    s = str(value or '').strip()
    if not s or s == NETWORK_BAR:
        raise ValueError('Выберите бар, к которому относится отзыв')
    if s not in BAR_KEYS:
        raise ValueError(f'Неизвестный бар «{value}»')
    return s


def _rating(value) -> Optional[int]:
    """Оценка: пусто/null -> None; иначе целое RATING_MIN..RATING_MAX, иначе ValueError.

    Порядок проверок выбран ради скорости на любом входе:
      bool и не число/строка -> отказ; int -> только сравнение с границами;
      строка/float -> запись длиннее MAX_RATING_INPUT_LEN -> отказ -> Decimal ->
      конечное -> в границах 1..5 -> целое -> int().
    Сравнение Decimal с границами мгновенно при любом показателе степени, а
    int(Decimal('1e3000000')) строил бы число из 3 млн цифр: минуты процессора
    с удержанием GIL и блокировки файла отзывов (воркер gunicorn убивается по
    таймауту). Поэтому int() берётся только у значения, уже лежащего в 1..5.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    msg = f'Оценка: целое число от {RATING_MIN} до {RATING_MAX}'
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(msg)
    if isinstance(value, int):
        if not RATING_MIN <= value <= RATING_MAX:
            raise ValueError(msg)
        return value
    raw = str(value).strip()
    if len(raw) > MAX_RATING_INPUT_LEN:
        raise ValueError(msg)
    try:
        d = Decimal(raw)
    except Exception:  # noqa: BLE001 — любая нечисловая строка
        raise ValueError(msg)
    if not d.is_finite() or not Decimal(RATING_MIN) <= d <= Decimal(RATING_MAX) \
            or d != d.to_integral_value():
        raise ValueError(msg)
    return int(d)


def _guest(value) -> Optional[dict]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('Контакты гостя: нужен объект {phone, telegram}')
    phone = _text(value.get('phone'), MAX_PHONE_LEN, 'Телефон гостя')
    telegram = _text(value.get('telegram'), MAX_TELEGRAM_LEN, 'Telegram гостя')
    if not phone and not telegram:
        return None
    return {'phone': phone, 'telegram': telegram}


def _optional_id(value, limit: int, field: str) -> Optional[str]:
    if value is None:
        return None
    s = _text(value, limit, field)
    return s or None


def clean_core(data: Mapping, now: datetime) -> dict:
    """Проверить содержательные поля отзыва целиком; ValueError с текстом для 400.

    data — полный набор полей (при правке: запись, поверх которой наложены
    переданные поля). created_at обязателен (умолчание подставляет add()).
    """
    source = _source(data.get('source'))
    bar = _bar(data.get('bar'))
    rating = _rating(data.get('rating'))
    author = _text(data.get('author'), MAX_AUTHOR_LEN, 'Имя автора')
    text = _text(data.get('text'), MAX_TEXT_LEN, 'Текст отзыва')
    created = parse_dt(data.get('created_at'), 'Дата отзыва')
    if created > naive_msk(now) + FUTURE_TOLERANCE:
        raise ValueError('Дата отзыва в будущем: проверьте дату и время')
    if source == 'yandex' and rating is None:
        raise ValueError('У отзыва с Яндекс Карт нужна оценка от 1 до 5')
    if not text and rating is None:
        raise ValueError('Нужен текст отзыва или оценка')
    # Контакты — только у отзывов из бота; у Яндекса их нет, поле игнорируется.
    guest = _guest(data.get('guest')) if source == 'bot' else None
    reply_draft = _draft(data.get('reply_draft'), MAX_REPLY_LEN, 'Черновик ответа')
    return {'source': source, 'bar': bar, 'rating': rating, 'author': author, 'text': text,
            'created_at': fmt_dt(created), 'guest': guest, 'reply_draft': reply_draft}


def _check_record(rid, rec) -> dict:
    """Проверка записи при чтении файла; битая запись -> ReviewStoreUnavailable."""
    try:
        if not isinstance(rec, dict):
            raise ValueError('запись не объект')
        if rec.get('id') != rid:
            raise ValueError('id записи не совпадает с ключом')
        if rec.get('source') not in SOURCE_KEYS:
            raise ValueError('неизвестный источник')
        if rec.get('bar') not in BAR_KEYS:
            raise ValueError('неизвестный бар')
        if rec.get('status') not in STATUSES:
            raise ValueError('неизвестный статус')
        parse_dt(rec.get('created_at'))
        rating = rec.get('rating')
        if rating is not None and (isinstance(rating, bool) or not isinstance(rating, int)
                                   or not RATING_MIN <= rating <= RATING_MAX):
            raise ValueError('оценка вне 1..5')
        if not isinstance(rec.get('text', ''), str):
            raise ValueError('текст не строка')
        reply = rec.get('reply')
        if reply is not None:
            if not isinstance(reply, dict) or not isinstance(reply.get('text'), str):
                raise ValueError('ответ повреждён')
            parse_dt(reply.get('at'), 'Дата ответа')
        if rec['status'] == 'answered' and reply is None:
            raise ValueError('статус «отвечен» без ответа')
    except ValueError as e:
        raise ReviewStoreUnavailable(f'Файл отзывов повреждён: запись «{rid}» — {e}') from e
    fixed = dict(rec)
    for key, default in (('author', ''), ('text', ''), ('rating', None), ('reply', None),
                         ('reply_draft', ''), ('skip_reason', ''), ('guest', None),
                         ('external_id', None), ('origin', 'manual'), ('material_id', None),
                         ('added_at', None), ('added_by', None), ('updated_at', None),
                         ('updated_by', None), ('photos', []), ('author_avatar', None),
                         ('public_rating', None), ('gone_at', None)):
        fixed.setdefault(key, default)
    return fixed


def _import_item(item: Mapping) -> dict:
    """Отзыв из источника (как core.yandex_business.parse_review) -> поля записи; ValueError — не загружать.

    Обязательны id, дата и оценка 1..5 (отзыв на Яндекс Картах без оценки не
    оставить). Текст и имя берутся как есть: длины источника — не ошибка
    ввода, обрезать чужой отзыв нельзя.
    """
    if not isinstance(item, Mapping):
        raise ValueError('запись не объект')
    ext = item.get('external_id')
    if not isinstance(ext, str) or not ext.strip() or len(ext) > MAX_EXTERNAL_ID_LEN:
        raise ValueError('нет id')
    created = fmt_dt(parse_dt(item.get('created_at'), 'Дата отзыва'))
    rating = item.get('rating')
    if isinstance(rating, bool) or not isinstance(rating, int) or not RATING_MIN <= rating <= RATING_MAX:
        raise ValueError(f'оценка не 1..5: {rating!r}')
    reply = item.get('owner_reply')
    if isinstance(reply, Mapping) and isinstance(reply.get('text'), str) and reply['text'].strip():
        at = reply.get('at')
        reply = {'text': reply['text'].strip(),
                 'at': fmt_dt(parse_dt(at, 'Дата ответа')) if at else None}
    else:
        reply = None
    photos = [dict(p) for p in (item.get('photos') or []) if isinstance(p, Mapping) and p.get('link')]
    public = item.get('public_rating')
    return {
        'external_id': ext.strip(),
        'created_at': created,
        'rating': rating,
        'text': _as_text(item.get('text'), 'Текст отзыва').strip(),
        'author': _as_text(item.get('author'), 'Имя автора').strip(),
        'owner_reply': reply,
        'photos': photos,
        'author_avatar': item.get('author_avatar') if isinstance(item.get('author_avatar'), str) else None,
        'public_rating': public if isinstance(public, bool) else None,
    }


# ----------------------------------------------------------------- вывод

# Проверка материалов контент-плана: ids (отсортированные, без повторов) ->
# {id: есть ли материал} или None (контент-план недоступен — «не проверялось»).
MaterialLookup = Callable[[List[str]], Optional[Mapping[str, bool]]]


def resolve_materials(reviews: Iterable[dict],
                      lookup: Optional[MaterialLookup]) -> Optional[Mapping[str, bool]]:
    """Один вызов lookup на все разные material_id отзывов -> {id: bool} или None.

    Ссылок нет -> {} (lookup не вызывается: контент-план не трогаем зря).
    lookup не передан, упал или вернул не словарь -> None: material_exists
    станет null («не проверялось»), список и ответы по отзывам не падают из-за
    контент-плана.
    """
    ids = sorted({r['material_id'] for r in reviews if r.get('material_id')})
    if not ids:
        return {}
    if lookup is None:
        return None
    try:
        found = lookup(ids)
    except Exception as e:  # noqa: BLE001 — сбой проверки не должен ронять отзывы
        print(f'[REVIEWS] material lookup failed: {e!r}')
        return None
    return found if isinstance(found, Mapping) else None


def decorate(review: dict, now: datetime, materials: Optional[Mapping[str, bool]] = None) -> dict:
    """Копия отзыва + age_hours (для new), response_hours (для answered), material_exists.

    materials — результат resolve_materials: {material_id: есть ли материал}
    или None (не проверялось). material_exists: true / false по нему; null —
    ссылки нет, id нет в словаре или materials = None.
    """
    r = copy.deepcopy(review)
    mid = r.get('material_id')
    exists = materials.get(mid) if (mid and materials is not None) else None
    r['material_exists'] = exists if isinstance(exists, bool) else None
    created = parse_dt(r['created_at'])
    r['age_hours'] = None
    r['response_hours'] = None
    if r['status'] == 'new':
        r['age_hours'] = round_half_up(_hours(max(0, _minutes_between(created, naive_msk(now)))), 1)
    elif r['status'] == 'answered' and r.get('reply'):
        r['response_hours'] = round_half_up(_hours(_response_minutes(r)), 1)
    return r


def _response_minutes(review: dict) -> int:
    created = parse_dt(review['created_at'])
    replied = parse_dt(review['reply']['at'], 'Дата ответа')
    return max(0, _minutes_between(created, replied))


def sort_reviews(reviews: Iterable[dict]) -> List[dict]:
    """new по created_at по возрастанию, затем остальные по created_at по убыванию; при равенстве — id по возрастанию."""
    items = sorted(reviews, key=lambda r: r['id'])
    new = sorted((r for r in items if r['status'] == 'new'), key=lambda r: r['created_at'])
    rest = sorted((r for r in items if r['status'] != 'new'), key=lambda r: r['created_at'], reverse=True)
    return new + rest


def _avg(ratings: List[int]):
    if not ratings:
        return None
    return round_half_up(Decimal(sum(ratings)) / Decimal(len(ratings)), 1)


def compute_metrics(reviews: Iterable[dict], now: datetime) -> dict:
    """Метрики одного набора отзывов (формулы — в докстринге модуля и FORMULAS)."""
    reviews = list(reviews)
    now = naive_msk(now)
    ratings = [r['rating'] for r in reviews if r.get('rating') is not None]
    count = len(reviews)
    new = [r for r in reviews if r['status'] == 'new']
    answered = [r for r in reviews if r['status'] == 'answered' and r.get('reply')]
    med = median(_response_minutes(r) for r in answered)
    ages = [max(0, _minutes_between(parse_dt(r['created_at']), now)) for r in new]
    return {
        'count': count,
        'rated': len(ratings),
        'avg_rating': _avg(ratings),
        'unanswered': len(new),
        'answered': sum(1 for r in reviews if r['status'] == 'answered'),
        'skipped': sum(1 for r in reviews if r['status'] == 'skipped'),
        'unanswered_pct': (round_half_up(Decimal(len(new) * 100) / Decimal(count), 0) if count else None),
        'median_response_hours': round_half_up(med / Decimal(60), 1) if med is not None else None,
        'oldest_unanswered_hours': round_half_up(_hours(max(ages)), 1) if ages else None,
    }


def _flag(value) -> bool:
    return str(value or '').strip().lower() in _TRUE_WORDS


def _arg(args: Mapping, key: str) -> str:
    value = args.get(key)
    return str(value).strip() if value is not None else ''


def parse_list_query(args: Mapping, now: datetime) -> dict:
    """Разбор параметров списка; ValueError -> 400.

    Период: all=1 > from/to > month > текущий месяц. Границы включительно.
    """
    now = naive_msk(now)
    q = {'all': _flag(args.get('all')), 'from': None, 'to': None, 'month': None,
         'bar': None, 'source': None, 'rating': None, 'status': None}
    if not q['all']:
        date_from, date_to = _arg(args, 'from'), _arg(args, 'to')
        if date_from or date_to:
            q['from'] = parse_date(date_from, 'Начало периода').isoformat() if date_from else None
            q['to'] = parse_date(date_to, 'Конец периода').isoformat() if date_to else None
            if q['from'] and q['to'] and q['from'] > q['to']:
                raise ValueError('Начало периода позже конца')
        else:
            month = _arg(args, 'month')
            month = parse_month(month) if month else now.strftime('%Y-%m')
            first, last = month_bounds(month)
            q['month'] = month
            q['from'], q['to'] = first.isoformat(), last.isoformat()
    bar = _arg(args, 'bar')
    if bar and bar != NETWORK_BAR:
        if bar not in BAR_KEYS:
            raise ValueError(f'Неизвестный бар «{bar}»')
        q['bar'] = bar
    source = _arg(args, 'source').lower()
    if source and source != 'all':
        if source not in SOURCE_KEYS:
            raise ValueError(f'Неизвестный источник «{source}»')
        q['source'] = source
    rating = _arg(args, 'rating').lower()
    if rating and rating != 'all':
        if rating not in RATING_FILTERS:
            raise ValueError('Фильтр оценки: low, mid, high или none')
        q['rating'] = rating
    status = _arg(args, 'status').lower()
    if status and status != 'all':
        if status not in STATUSES:
            raise ValueError('Фильтр статуса: new, answered или skipped')
        q['status'] = status
    return q


def _in_period(review: dict, q: dict) -> bool:
    day = review['created_at'][:10]
    if q['from'] and day < q['from']:
        return False
    if q['to'] and day > q['to']:
        return False
    return True


def _rating_match(review: dict, bucket: Optional[str]) -> bool:
    if not bucket:
        return True
    rating = review.get('rating')
    if bucket == 'none':
        return rating is None
    lo, hi = RATING_BUCKETS[bucket]
    return rating is not None and lo <= rating <= hi


def build_listing(reviews: Iterable[dict], q: dict, now: datetime,
                  material_lookup: Optional[MaterialLookup] = None) -> dict:
    """Ответ GET /api/reviews: список по всем фильтрам + метрики по периоду и источнику.

    material_lookup вызывается один раз на все ссылки показанных отзывов (не
    на каждый отзыв) — см. resolve_materials.
    """
    now = naive_msk(now)
    base = [r for r in reviews if _in_period(r, q) and (not q['source'] or r['source'] == q['source'])]
    shown = sort_reviews(r for r in base
                         if (not q['bar'] or r['bar'] == q['bar'])
                         and (not q['status'] or r['status'] == q['status'])
                         and _rating_match(r, q['rating']))
    materials = resolve_materials(shown, material_lookup)
    return {
        'now': fmt_dt(now),
        'from': q['from'],
        'to': q['to'],
        'month': q['month'],
        'all': q['all'],
        'reviews': [decorate(r, now, materials) for r in shown],
        'metrics': {
            'total': compute_metrics(base, now),
            'by_bar': {b: compute_metrics([r for r in base if r['bar'] == b], now) for b in BAR_KEYS},
        },
        'formulas': dict(FORMULAS),
        'sources': [{'key': k, 'name': n} for k, n in SOURCES],
        'bars': copy.deepcopy(BARS),
    }


def build_daily(reviews: Iterable[dict], month: str, bar: Optional[str] = None,
                source: Optional[str] = None) -> dict:
    """Слой календаря: {month, days: {'YYYY-MM-DD': {count, rated, avg}}} только для дней с отзывами."""
    by_day: Dict[str, List[dict]] = {}
    for r in reviews:
        if r['created_at'][:7] != month:
            continue
        if bar and r['bar'] != bar:
            continue
        if source and r['source'] != source:
            continue
        by_day.setdefault(r['created_at'][:10], []).append(r)
    days = {}
    for day in sorted(by_day):
        ratings = [r['rating'] for r in by_day[day] if r.get('rating') is not None]
        days[day] = {'count': len(by_day[day]), 'rated': len(ratings), 'avg': _avg(ratings)}
    return {'month': month, 'days': days}


# ----------------------------------------------------------------- хранилище

class ReviewStore:
    def __init__(self, data_file: Optional[str] = None, clock: Optional[Callable[[], datetime]] = None):
        self.data_file = data_file or get_data_path(DATA_FILE_NAME)
        self._clock = clock or msk_time.now
        self._lock = threading.Lock()
        self._lock_path = self.data_file + '.lock'
        # Кэш чтения: один неизменяемый кортеж (ключ файла, данные).
        self._cache: Optional[tuple] = None

    def now(self) -> datetime:
        """«Сейчас» по Москве, наивное, с точностью до минуты."""
        return naive_msk(self._clock())

    # ----- файл ------------------------------------------------------------

    def _read(self, use_cache: bool = True) -> Dict[str, dict]:
        """Все записи. Нет файла -> {}; файл не читается/битый -> ReviewStoreUnavailable."""
        if not os.path.exists(self.data_file):
            return {}
        try:
            st = os.stat(self.data_file)
            key = (st.st_mtime_ns, st.st_size)
            cached = self._cache
            if use_cache and cached is not None and cached[0] == key:
                return copy.deepcopy(cached[1])
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f'[REVIEWS] cannot read {self.data_file}: {e}')
            raise ReviewStoreUnavailable(f'Файл отзывов не читается: {e}') from e
        raw = data.get('reviews') if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            print(f'[REVIEWS] unexpected structure in {self.data_file}')
            raise ReviewStoreUnavailable('Файл отзывов повреждён: неожиданная структура')
        result = {rid: _check_record(rid, rec) for rid, rec in raw.items()}
        self._cache = (key, copy.deepcopy(result))
        return result

    def _save(self, reviews: Dict[str, dict]) -> None:
        atomic_write_json(self.data_file, {'version': SCHEMA_VERSION, 'reviews': reviews})
        self._cache = None

    def _write(self, fn):
        """read-modify-write под обеими блокировками со строгим перечитыванием файла."""
        with self._lock, file_lock(self._lock_path):
            reviews = self._read(use_cache=False)
            result = fn(reviews, self.now())
            self._save(reviews)
        return copy.deepcopy(result)

    @staticmethod
    def _require(reviews: Dict[str, dict], review_id: str) -> dict:
        rec = reviews.get(str(review_id or ''))
        if rec is None:
            raise ReviewNotFound(review_id)
        return rec

    @staticmethod
    def _touch(rec: dict, now: datetime, user: Optional[dict]) -> None:
        rec['updated_at'] = fmt_dt(now)
        rec['updated_by'] = _user_login(user)

    # ----- чтение ----------------------------------------------------------

    def is_stored(self) -> bool:
        return os.path.exists(self.data_file)

    def all(self) -> List[dict]:
        return list(self._read().values())

    def get(self, review_id: str) -> Optional[dict]:
        return self._read().get(str(review_id or ''))

    def listing(self, args: Mapping, material_lookup: Optional[MaterialLookup] = None) -> dict:
        now = self.now()
        return build_listing(self.all(), parse_list_query(args, now), now, material_lookup)

    def daily(self, month: Optional[str] = None, bar: Optional[str] = None,
              source: Optional[str] = None) -> dict:
        month = parse_month(month) if month else self.now().strftime('%Y-%m')
        if bar in ('', NETWORK_BAR):
            bar = None
        if bar is not None and bar not in BAR_KEYS:
            raise ValueError(f'Неизвестный бар «{bar}»')
        if source in ('', 'all'):
            source = None
        if source is not None and source not in SOURCE_KEYS:
            raise ValueError(f'Неизвестный источник «{source}»')
        return build_daily(self.all(), month, bar, source)

    def unanswered_count(self, bar: Optional[str] = None) -> int:
        """Отзывы со статусом new за всё время; bar None / 'all' — вся сеть."""
        bar = None if bar in (None, '', NETWORK_BAR) else bar
        return sum(1 for r in self._read().values() if r['status'] == 'new' and (bar is None or r['bar'] == bar))

    def decorate(self, review: dict, material_lookup: Optional[MaterialLookup] = None) -> dict:
        return decorate(review, self.now(), resolve_materials([review], material_lookup))

    # ----- запись ----------------------------------------------------------

    def add(self, fields: Mapping, user: Optional[dict], origin: str = 'manual') -> dict:
        """Новый отзыв (status new). Без created_at — текущий момент.

        origin 'import' принимает external_id; повтор (source, external_id) -> ReviewConflict.
        """
        if origin not in ORIGINS:
            raise ValueError(f'Неизвестное происхождение «{origin}»')
        fields = dict(fields or {})

        def op(reviews, now):
            data = dict(fields)
            if data.get('created_at') in (None, ''):
                data['created_at'] = fmt_dt(now)
            core = clean_core(data, now)
            external_id = (_optional_id(fields.get('external_id'), MAX_EXTERNAL_ID_LEN, 'Внешний id')
                           if origin == 'import' else None)
            if external_id is not None:
                dup = next((r for r in reviews.values()
                            if r['source'] == core['source'] and r.get('external_id') == external_id), None)
                if dup is not None:
                    raise ReviewConflict('Этот отзыв уже загружен', review_id=dup['id'])
            rid = 'r_' + secrets.token_hex(6)
            while rid in reviews:
                rid = 'r_' + secrets.token_hex(6)
            stamp, login = fmt_dt(now), _user_login(user)
            rec = {'id': rid, **core, 'status': 'new', 'reply': None, 'skip_reason': '',
                   'external_id': external_id, 'origin': origin, 'material_id': None,
                   'added_at': stamp, 'added_by': login, 'updated_at': stamp, 'updated_by': login}
            reviews[rid] = rec
            return rec
        return self._write(op)

    EDITABLE_FIELDS = ('bar', 'rating', 'author', 'text', 'created_at', 'guest', 'reply_draft', 'source')

    def update(self, review_id: str, fields: Mapping, user: Optional[dict]) -> dict:
        """Правка: только EDITABLE_FIELDS из fields; запись проверяется целиком.

        source меняется только у отзывов, внесённых вручную. created_at: null -> 400.
        """
        changes = {k: v for k, v in (fields or {}).items() if k in self.EDITABLE_FIELDS}

        def op(reviews, now):
            rec = self._require(reviews, review_id)
            if 'source' in changes and str(changes['source'] or '').strip().lower() != rec['source'] \
                    and rec.get('origin') != 'manual':
                raise ValueError('Источник загруженного отзыва менять нельзя')
            merged = dict(rec)
            merged.update(changes)
            rec.update(clean_core(merged, now))
            self._touch(rec, now, user)
            return rec
        return self._write(op)

    def delete(self, review_id: str) -> None:
        def op(reviews, now):
            rec = self._require(reviews, review_id)
            if rec.get('origin') != 'manual':
                raise ReviewConflict('Загруженный отзыв удалить нельзя: он придёт снова при следующей загрузке. '
                                     'Оставьте его без ответа.')
            del reviews[rec['id']]
            return None
        self._write(op)

    def reply(self, review_id: str, text, user: Optional[dict]) -> dict:
        """Сохранить ответ: new -> answered; у answered — правка текста (reply.at не меняется)."""
        clean = _text(text, MAX_REPLY_LEN, 'Ответ')
        if not clean:
            raise ValueError('Напишите текст ответа')

        def op(reviews, now):
            rec = self._require(reviews, review_id)
            stamp, login = fmt_dt(now), _user_login(user)
            if rec['status'] == 'skipped':
                raise ReviewConflict('Отзыв оставлен без ответа по решению — сначала верните его в работу')
            if rec['status'] == 'answered' and rec.get('reply'):
                rec['reply']['text'] = clean
                rec['reply']['edited_at'] = stamp
                rec['reply']['edited_by'] = login
            else:
                rec['reply'] = {'text': clean, 'at': stamp, 'by': login, 'delivered': False}
            rec['status'] = 'answered'
            rec['reply_draft'] = ''
            self._touch(rec, now, user)
            return rec
        return self._write(op)

    def skip(self, review_id: str, reason, user: Optional[dict]) -> dict:
        """Оставить без ответа по решению: только new -> skipped."""
        clean = _text(reason, MAX_SKIP_REASON_LEN, 'Причина')

        def op(reviews, now):
            rec = self._require(reviews, review_id)
            if rec['status'] != 'new':
                raise ReviewConflict('Оставить без ответа можно только отзыв, который ждёт ответа')
            rec['status'] = 'skipped'
            rec['skip_reason'] = clean
            self._touch(rec, now, user)
            return rec
        return self._write(op)

    def reopen(self, review_id: str, user: Optional[dict]) -> dict:
        """Вернуть в работу: skipped | answered -> new (ответ и причина остаются для истории)."""
        def op(reviews, now):
            rec = self._require(reviews, review_id)
            if rec['status'] == 'new':
                raise ReviewConflict('Отзыв и так ждёт ответа')
            rec['status'] = 'new'
            self._touch(rec, now, user)
            return rec
        return self._write(op)

    def link_material(self, review_id: str, material_id: str, user: Optional[dict],
                      replace: Optional[str] = None) -> dict:
        """Запомнить материал контент-плана; уже есть другой -> ReviewConflict(material_id=...).

        replace — id устаревшей ссылки (материал удалён в контент-плане): её
        можно перезаписать, но только если в записи всё ещё именно он. Если
        параллельный запрос успел привязать другой материал — конфликт с его id,
        как и без replace (проверка гонки сохраняется).
        """
        mid = _optional_id(material_id, MAX_MATERIAL_ID_LEN, 'Материал')
        if not mid:
            raise ValueError('Нет id материала')

        def op(reviews, now):
            rec = self._require(reviews, review_id)
            current = rec.get('material_id')
            if current and (replace is None or current != replace):
                raise ReviewConflict('Материал из этого отзыва уже создан', material_id=current)
            rec['material_id'] = mid
            self._touch(rec, now, user)
            return rec
        return self._write(op)

    # ----- загрузка из источника ------------------------------------------

    IMPORT_FIELDS = ('rating', 'text', 'author', 'photos', 'author_avatar', 'public_rating')

    def upsert_imported(self, source: str, bar: str, items: Iterable[Mapping], *,
                        history_cutoff: str, complete: bool, by: str) -> dict:
        """Загрузить отзывы одного бара из источника; правила — докстринг модуля.

        items — отзывы как у core.yandex_business.parse_review (external_id,
        created_at, rating, text, author, owner_reply {text, at}, photos, ...).
        history_cutoff — 'YYYY-MM-DD': новый отзыв без ответа с датой раньше
        него получает skipped с HISTORY_SKIP_REASON. complete=True — items
        содержат ВСЕ отзывы бара в источнике: пропавшие получают gone_at
        (без удаления). by — подпись загрузки (added_by / updated_by / reply.by).
        Одна запись файла на вызов. Ответ — сводка:
            added_new, added_answered, added_history — созданы со статусом
                new / answered / skipped;
            updated — изменились оценка, текст, автор или фото;
            answered_in_source — ждал ответа или был «без ответа», в источнике ответили;
            published — наш сохранённый ответ появился в источнике;
            reply_removed — ответ источника пропал, отзыв снова ждёт ответа;
            gone / back — пропал из источника / вернулся;
            invalid — не загружены (problems — первые MAX_IMPORT_PROBLEMS причин).
        """
        source = _source(source)
        bar = _bar(bar)
        cutoff = parse_date(history_cutoff, 'Граница истории').isoformat()
        user = {'login': by}
        stats = {k: 0 for k in ('added_new', 'added_answered', 'added_history', 'updated',
                                'answered_in_source', 'published', 'reply_removed', 'gone', 'back',
                                'invalid')}
        stats['problems'] = []
        clean: Dict[str, dict] = {}
        # Все id, пришедшие из источника, включая не прошедшие проверку: отзыв,
        # который есть в источнике, но не разобрался, — не «пропавший».
        present = set()
        for item in items or []:
            if isinstance(item, Mapping) and isinstance(item.get('external_id'), str):
                present.add(item['external_id'].strip())
            try:
                fields = _import_item(item)
            except ValueError as e:
                stats['invalid'] += 1
                if len(stats['problems']) < MAX_IMPORT_PROBLEMS:
                    ext = item.get('external_id') if isinstance(item, Mapping) else None
                    stats['problems'].append(f'{ext or "(без id)"}: {e}')
                continue
            clean.setdefault(fields['external_id'], fields)

        def source_reply(fields, now):
            r = fields['owner_reply']
            return {'text': r['text'], 'at': r['at'] or fmt_dt(now), 'by': by,
                    'delivered': True, 'source': source}

        def op(reviews, now):
            stamp = fmt_dt(now)
            existing = {r['external_id']: r for r in reviews.values()
                        if r['source'] == source and r.get('origin') == 'import' and r.get('external_id')}
            for ext, fields in clean.items():
                rec = existing.get(ext)
                if rec is None:
                    rid = 'r_' + secrets.token_hex(6)
                    while rid in reviews:
                        rid = 'r_' + secrets.token_hex(6)
                    rec = {'id': rid, 'source': source, 'bar': bar, 'created_at': fields['created_at'],
                           'status': 'new', 'reply': None, 'reply_draft': '', 'skip_reason': '',
                           'guest': None, 'external_id': ext, 'origin': 'import', 'material_id': None,
                           'gone_at': None, 'added_at': stamp, 'added_by': by,
                           'updated_at': stamp, 'updated_by': by}
                    rec.update({k: fields[k] for k in self.IMPORT_FIELDS})
                    if fields['owner_reply']:
                        rec['status'] = 'answered'
                        rec['reply'] = source_reply(fields, now)
                        stats['added_answered'] += 1
                    elif fields['created_at'][:10] < cutoff:
                        rec['status'] = 'skipped'
                        rec['skip_reason'] = HISTORY_SKIP_REASON
                        stats['added_history'] += 1
                    else:
                        stats['added_new'] += 1
                    reviews[rid] = rec
                    continue

                changed = False
                if any(rec.get(k) != fields[k] for k in self.IMPORT_FIELDS):
                    rec.update({k: fields[k] for k in self.IMPORT_FIELDS})
                    stats['updated'] += 1
                    changed = True
                if rec.get('gone_at'):
                    rec['gone_at'] = None
                    stats['back'] += 1
                    changed = True
                reply = rec.get('reply') if isinstance(rec.get('reply'), dict) else None
                from_source = bool(reply and reply.get('source') == source)
                src = fields['owner_reply']
                if src:
                    if rec['status'] == 'answered' and from_source:
                        if reply['text'] != src['text']:
                            reply['text'] = src['text']
                            reply['edited_at'] = src['at'] or stamp
                            reply['edited_by'] = by
                            changed = True
                    elif rec['status'] == 'answered':
                        if not reply.get('delivered') or reply.get('source_text') != src['text']:
                            reply['delivered'] = True
                            reply['published_at'] = src['at'] or stamp
                            reply['source_text'] = src['text']
                            stats['published'] += 1
                            changed = True
                    else:
                        rec['status'] = 'answered'
                        rec['reply'] = source_reply(fields, now)
                        stats['answered_in_source'] += 1
                        changed = True
                elif rec['status'] == 'answered' and from_source:
                    rec['status'] = 'new'
                    reply['removed_in_source_at'] = stamp
                    stats['reply_removed'] += 1
                    changed = True
                if changed:
                    self._touch(rec, now, user)

            if complete:
                for rec in reviews.values():
                    if (rec['source'] == source and rec.get('origin') == 'import' and rec['bar'] == bar
                            and rec.get('external_id') not in present and not rec.get('gone_at')):
                        rec['gone_at'] = stamp
                        stats['gone'] += 1
                        self._touch(rec, now, user)
            return stats
        return self._write(op)


_store: Optional[ReviewStore] = None
_store_guard = threading.Lock()


def get_review_store(data_file: Optional[str] = None,
                     clock: Optional[Callable[[], datetime]] = None) -> ReviewStore:
    """Ленивый синглтон на процесс (файл на томе общий для воркеров).

    С data_file/clock (тесты, локальный стенд) синглтон пересоздаётся с ними.
    """
    global _store
    with _store_guard:
        if data_file is not None or clock is not None:
            _store = ReviewStore(data_file, clock)
        elif _store is None:
            _store = ReviewStore()
        return _store


def material_draft(review: dict) -> dict:
    """Поля материала контент-плана из отзыва (заголовок, текст-цитата, ссылка на отзыв).

    base_text: «<текст>», перевод строки, «— <автор или "гость">». Нет текста -> ValueError.
    """
    text = (review.get('text') or '').strip()
    if not text:
        raise ValueError('У отзыва нет текста — материал из него не сделать')
    author = (review.get('author') or '').strip() or 'гость'
    return {
        'title': f'Отзыв гостя — {BAR_SHORT.get(review["bar"], review["bar"])}',
        'kind': 'fixed',
        'base_text': f'«{text}»\n— {author}',
        'source_review_id': review['id'],
    }
