"""Приёмка на РЦ: SQLite-хранилище receiving.db (приёмки, сканы, фото накладных,
строки разбора бухгалтерии, кэш карточек Честного ЗНАКа).

Что это. Приёмщик РЦ сканирует каждую бутылку/банку/кег; сканы копятся в открытой
приёмке. После «Завершить» приёмка закрывается, фоновая обработка
(core/receiving_service.py) сверяет GTIN с индексом iiko и заводит строки разбора
(review_items) — очередь бухгалтерии «завести / восстановить карточку». Модуль
хранит всё это и отдаёт готовые «словари API» (docs/receiving.md, раздел API):
маршруты, страницы и MCP получают одни и те же формы.

Почему SQLite. Сканы летят с телефона по одному, из двух gunicorn-воркеров
одновременно, и каждый должен посчитаться ровно один раз: повтор запроса из
очереди браузера (тот же client_id) и повтор той же бутылки DataMatrix
(тот же code_key) отсекаются внутри одной транзакции BEGIN IMMEDIATE, а
уникальные индексы — страховка на уровне файла. JSON-файл с read-modify-write
под двумя воркерами этого не даёт (docs/lessons.md, «read-modify-write под
gunicorn 2 воркера = гонка»).

Как.
- Путь: core.storage_paths.get_data_path('receiving.db') — /kultura/receiving.db
  в проде, data/receiving.db локально. Тесты подменяют путь через set_db_path().
- Каждое обращение — своё соединение: WAL, busy_timeout, synchronous=NORMAL и
  foreign_keys=ON (в SQLite внешние ключи по умолчанию ВЫКЛЮЧЕНЫ, урок
  «График: FK в SQLite по умолчанию выключены»).
- Чтение — транзакция BEGIN (снимок: строки и их счётчики из одного состояния);
  запись — BEGIN IMMEDIATE на весь блок (проверка + запись атомарны между воркерами).
- Схема — PRAGMA user_version (SCHEMA_VERSION). Миграции только аддитивные
  (ADD COLUMN / новые таблицы и индексы, без DROP): старый код после отката
  деплоя продолжает работать с более новой схемой.
- Файл не читается (битый, не SQLite, нет прав, каталог вместо файла, БД
  заблокирована дольше busy_timeout) → ReceivingUnavailable: маршрут отдаёт 503
  code='receiving_unavailable', файл не трогаем.
- Время — только core.msk_time (в прод-образе наивное datetime.now() — это UTC).
  Метки — ISO 8601 с секундами и смещением: '2026-10-03T14:05:00+03:00'. Смещение
  всегда +03:00, поэтому строки сравниваются лексикографически так же, как время
  (на этом стоят окна PROCESS_STALE_SEC / PROCESS_RETRY_SEC в SQL).

Подсчёт (receipt counts):
- units — принятые неудалённые сканы (accepted=1, deleted_at IS NULL): одна
  DataMatrix = одна бутылка, каждый скан EAN = ещё одна штука;
- gtins — различные GTIN среди них;
- rejected — отклонённые неудалённые сканы, кроме повторов (reason != 'repeat');
- repeats — повторы той же DataMatrix (reason = 'repeat');
- invoices — фото накладных.

Строка разбора (review_items) — одна на GTIN на все приёмки. Правила
upsert_review / reclassify_open / update_review — в их докстрингах и в
docs/receiving.md. Поле updated_* — последняя правка ЧЕЛОВЕКОМ (поставщик,
заметка, «Сделано» / «Не нужно» / «Вернуть в разбор»); системные изменения
видны по classified_at и resolved_* (resolved_by = 'индекс iiko').

Прогресс разбора закрытой приёмки (receipt['review']) — по различным GTIN её
принятых неудалённых сканов: open — строка разбора открыта, closed — закрыта,
missing — строки нет (обработка не дошла или упала); open + closed + missing =
counts.gtins. Строка одна на GTIN, поэтому GTIN, общий с другой приёмкой, считается
в обеих. «Разобрана полностью» (reviewed) — закрыта, сверка done, позиций больше
нуля, open = missing = 0. Удалить (delete_receipt, can_delete) можно закрытую
приёмку, разобранную не полностью; открытую ещё сканируют, а разобранная — запись о
сделанной работе и остаётся в истории.
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

from core import msk_time
from core import receiving_codes
from core.storage_paths import get_data_path

DB_FILE = 'receiving.db'
# Версия схемы в PRAGMA user_version. Растёт на каждую аддитивную миграцию:
# 2 — таблица receipt_deletions (удаление приёмки, 2026-10-04).
SCHEMA_VERSION = 2
BUSY_TIMEOUT_MS = 5000      # сколько ждать чужой write-лок, прежде чем сдаться (как mcp.db)
CONNECT_TIMEOUT_SEC = 10    # таймаут sqlite3.connect на занятый файл (как core/mcp/db.py)

# Сырой код длиннее — мусор (ЕГАИС PDF417 ~150, DataMatrix пива ~31-45);
# = receiving_codes.MAX_CODE_LEN, больше хранить незачем.
MAX_RAW = 512
NOTE_LIMIT = 500            # заметка приёмки / строки разбора (маршрут проверяет тот же предел)
LIST_LIMIT_MAX = 1000       # потолок limit у списков: больше строк страница не рисует
# running дольше 15 мин — воркер умер, можно перехватить (обработка идёт минуты:
# индекс iiko + ЧЗ по SSH до 3 мин на пакет).
PROCESS_STALE_SEC = 900
PROCESS_RETRY_SEC = 3600    # error — повтор не чаще раза в час (iiko/бар-ПК лежат обычно дольше минут)
# Сводка обработки: несколько ошибок ЧЗ + предупреждение об индексе; длиннее
# обрезаем, чтобы строка приёмки не разрасталась.
PROCESS_NOTE_LIMIT = 2000
RAW_SHORT_LEN = 60          # raw_short в scan dict: строка «последний скан» на экране приёмщика
CLIENT_ID_LIMIT = 64        # client_id из браузера: UUID — 36 символов, маршрут пускает 8..64
CLIENT_TIME_LIMIT = 40      # client_time: ISO-время телефона для диагностики (маршрут: ≤ 40)
# Сколько значений в одном IN (...): ниже лимита старых сборок SQLite (999 переменных
# на запрос), чтобы запрос не упал на любой версии библиотеки.
SQL_CHUNK = 500
# Сколько приёмок можно выбрать в фильтре разбора разом: страница показывает выбор из
# неразобранных приёмок (их единицы-десятки), 50 — с запасом и в одном IN (...).
RECEIPT_FILTER_MAX = 50

INVOICE_URL_PREFIX = '/api/receiving/invoice/'   # раздача фото накладной (routes/receiving.py)
AGENT_SUFFIX = ' · агент'   # подпись действий ИИ-агента владельца (вызов через MCP, via_mcp)
INDEX_ACTOR = 'индекс iiko'  # кто закрыл строку автоматически (карточка нашлась в индексе)

RECEIPT_STATUSES = ('open', 'closed')
SOURCES = ('scanner', 'camera', 'manual')          # откуда скан: ручной сканер, камера, руками
DEFAULT_SOURCE = 'scanner'
KIND_DATAMATRIX = 'datamatrix'                       # = receiving_codes.KIND_DATAMATRIX
REASON_REPEAT = 'repeat'                             # повтор уже принятой DataMatrix
RESULT_ACCEPTED, RESULT_REPEAT, RESULT_REJECTED = 'accepted', 'repeat', 'rejected'
# Статусы строки разбора в порядке важности (так сортируется список бухгалтерии).
STATUSES = ('new', 'similar', 'restore', 'duplicate', 'found')
OPEN_COUNT_STATUSES = ('new', 'similar', 'restore', 'duplicate')   # счётчики вкладок
REVIEW_STATES = ('open', 'closed')
LIST_STATES = ('open', 'closed', 'all')
USER_STATES = ('done', 'not_needed', 'open')         # что может выставить бухгалтер
FINISH_STATES = ('done', 'error')
# Поля данных ЧЗ, которые попадают в строку разбора (остальное — в кэше chz_products).
# level / main_gtin / pack_units — групповая упаковка (мультипак): GTIN единицы внутри и
# сколько единиц (core/receiving_chz.normalize_item); у единицы товара пустые.
CHZ_FIELDS = ('name', 'brand', 'full_name', 'product_group', 'volume', 'package_type', 'source',
              'level', 'main_gtin', 'pack_units')
CHZ_TEXT_FIELDS = ('name', 'brand', 'full_name', 'product_group', 'volume', 'package_type')
GTIN_LEN = 14

_SCHEMA_V1 = (
    """CREATE TABLE IF NOT EXISTS receipts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
      note TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL, created_by_login TEXT NOT NULL DEFAULT '',
      created_by_name TEXT NOT NULL DEFAULT '',
      closed_at TEXT, closed_by_login TEXT NOT NULL DEFAULT '', closed_by_name TEXT NOT NULL DEFAULT '',
      process_state TEXT NOT NULL DEFAULT 'none'
        CHECK (process_state IN ('none','pending','running','done','error')),
      process_started_at TEXT, processed_at TEXT, process_note TEXT NOT NULL DEFAULT '',
      notified_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS receipt_scans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      receipt_id INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
      client_id TEXT NOT NULL, raw TEXT NOT NULL, kind TEXT NOT NULL,
      accepted INTEGER NOT NULL, gtin TEXT, code_key TEXT NOT NULL DEFAULT '',
      reason TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT 'scanner' CHECK (source IN ('scanner','camera','manual')),
      scanned_at TEXT NOT NULL, client_time TEXT NOT NULL DEFAULT '',
      scanned_by_login TEXT NOT NULL DEFAULT '', scanned_by_name TEXT NOT NULL DEFAULT '',
      deleted_at TEXT, deleted_by_login TEXT NOT NULL DEFAULT '', deleted_by_name TEXT NOT NULL DEFAULT ''
    )""",
    # Повтор запроса из очереди браузера: один client_id — одна строка в приёмке.
    'CREATE UNIQUE INDEX IF NOT EXISTS ux_scans_client ON receipt_scans(receipt_id, client_id)',
    # Одна бутылка DataMatrix принимается в приёмке один раз (удалённые и повторы не в счёт).
    """CREATE UNIQUE INDEX IF NOT EXISTS ux_scans_dm ON receipt_scans(receipt_id, code_key)
      WHERE kind = 'datamatrix' AND accepted = 1 AND deleted_at IS NULL""",
    'CREATE INDEX IF NOT EXISTS ix_scans_receipt ON receipt_scans(receipt_id, accepted, gtin)',
    # Количество и приёмки по GTIN для строк разбора (qty, receipts): без него каждый
    # список разбора читал бы все сканы за всё время.
    'CREATE INDEX IF NOT EXISTS ix_scans_gtin ON receipt_scans(gtin)',
    """CREATE TABLE IF NOT EXISTS receipt_invoices (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      receipt_id INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
      name TEXT NOT NULL UNIQUE, size INTEGER NOT NULL,
      uploaded_at TEXT NOT NULL, uploaded_by_login TEXT NOT NULL DEFAULT '',
      uploaded_by_name TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS review_items (
      gtin TEXT PRIMARY KEY,
      status TEXT NOT NULL CHECK (status IN ('found','restore','duplicate','similar','new')),
      state TEXT NOT NULL CHECK (state IN ('open','closed')),
      resolution TEXT NOT NULL DEFAULT '' CHECK (resolution IN ('','found','auto','done','not_needed')),
      cards_json TEXT NOT NULL DEFAULT '[]', candidates_json TEXT NOT NULL DEFAULT '[]',
      chz_json TEXT NOT NULL DEFAULT '{}',
      supplier TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
      first_receipt_id INTEGER, last_receipt_id INTEGER,
      first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, classified_at TEXT NOT NULL,
      index_built_at TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL, updated_by_login TEXT NOT NULL DEFAULT '',
      updated_by_name TEXT NOT NULL DEFAULT '',
      resolved_at TEXT, resolved_by_login TEXT NOT NULL DEFAULT '', resolved_by_name TEXT NOT NULL DEFAULT '',
      reopened INTEGER NOT NULL DEFAULT 0,
      notify_receipt_id INTEGER
    )""",
    'CREATE INDEX IF NOT EXISTS ix_review_state ON review_items(state, status)',
    """CREATE TABLE IF NOT EXISTS chz_products (
      gtin TEXT PRIMARY KEY, found INTEGER NOT NULL,
      name TEXT NOT NULL DEFAULT '', brand TEXT NOT NULL DEFAULT '', full_name TEXT NOT NULL DEFAULT '',
      product_group TEXT NOT NULL DEFAULT '', volume TEXT NOT NULL DEFAULT '',
      package_type TEXT NOT NULL DEFAULT '',
      raw_json TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL DEFAULT '', fetched_at TEXT NOT NULL
    )""",
)

# v2 (2026-10-04): удалённые приёмки. Сама приёмка, её сканы и записи о фото удаляются
# насовсем (delete_receipt), а здесь остаётся, кто и когда удалил, и снимок: приёмка,
# позиции, фото, удалённые строки разбора с решениями бухгалтера (snapshot_json).
_SCHEMA_V2 = (
    """CREATE TABLE IF NOT EXISTS receipt_deletions (
      receipt_id INTEGER PRIMARY KEY,
      deleted_at TEXT NOT NULL, deleted_by_login TEXT NOT NULL DEFAULT '',
      deleted_by_name TEXT NOT NULL DEFAULT '',
      snapshot_json TEXT NOT NULL DEFAULT '{}'
    )""",
)

# Колонки, добавленные к схеме v1 до выкладки (2026-10-03, ревью): база, созданная
# раньше (локально), догоняется ALTER TABLE ADD COLUMN — миграции только аддитивные.
# notified_at — когда бухгалтерии ушло сообщение о приёмке (повтор обработки после
# падения дошлёт его, а не потеряет); notify_receipt_id — какая приёмка открыла строку
# (о ней и сообщение).
_ADDED_COLUMNS = (
    ('receipts', 'notified_at', 'TEXT'),
    ('review_items', 'notify_receipt_id', 'INTEGER'),
)

# Порядок сортировки списка разбора: открытые раньше; статус по важности; свежие сверху.
_REVIEW_ORDER_SQL = (
    " ORDER BY CASE state WHEN 'open' THEN 0 ELSE 1 END, CASE status "
    + ' '.join("WHEN '%s' THEN %d" % (s, i) for i, s in enumerate(STATUSES))
    + ' ELSE %d END, last_seen_at DESC, gtin' % len(STATUSES)
)

_path_override: Optional[str] = None
_schema_done = set()        # пути БД, где схема уже проверена этим процессом
_schema_lock = threading.Lock()


# ------------------------------------------------------------------ исключения

class ReceivingUnavailable(Exception):
    """receiving.db не открывается или не читается (маршрут: 503 receiving_unavailable)."""


class ReceiptNotFound(Exception):
    """Нет приёмки с таким номером."""


class ReceiptClosed(Exception):
    """Приёмка уже закрыта: сканы в ней больше не меняются."""


class ScanNotFound(Exception):
    """Нет такого скана в этой приёмке."""


class ReviewItemNotFound(Exception):
    """Нет строки разбора для этого GTIN."""


class ReceiptOpen(Exception):
    """Приёмка ещё открыта (её сканируют): удалить можно только закрытую."""


class ReceiptReviewed(Exception):
    """Приёмка разобрана полностью: она остаётся в истории, удалить нельзя."""


# ------------------------------------------------------------------ соединения

def db_path() -> str:
    """Путь к receiving.db (подмена для тестов — set_db_path)."""
    return _path_override or get_data_path(DB_FILE)


def set_db_path(path: Optional[str]) -> None:
    """Тесты: работать с временным файлом. None — вернуть боевой путь."""
    global _path_override
    _path_override = path
    with _schema_lock:
        _schema_done.clear()


def _unavailable(exc: BaseException) -> ReceivingUnavailable:
    """Исключение для маршрута: текст без пути к файлу (OSError кладёт путь в str)."""
    detail = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
    return ReceivingUnavailable('База приёмки недоступна: ' + (detail or type(exc).__name__))


def _is_unavailable_error(exc: BaseException) -> bool:
    """Ошибка файла/блокировки, а не нарушение ограничения в нашем же запросе.

    IntegrityError (UNIQUE/CHECK/FK) и ProgrammingError — ошибки логики, их
    пробрасываем как есть; прочие DatabaseError («file is not a database»,
    «database is locked», «disk I/O error») — недоступность хранилища.
    """
    return (isinstance(exc, sqlite3.DatabaseError)
            and not isinstance(exc, (sqlite3.IntegrityError, sqlite3.ProgrammingError)))


def _connect():
    """Новое соединение (автокоммит; транзакции открываем явно). -> (conn, путь)."""
    path = db_path()
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False, timeout=CONNECT_TIMEOUT_SEC,
                               isolation_level=None)
    except (OSError, sqlite3.Error) as e:
        raise _unavailable(e) from e
    try:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=%d' % BUSY_TIMEOUT_MS)
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA foreign_keys=ON')
    except sqlite3.Error as e:
        conn.close()
        raise _unavailable(e) from e
    return conn, path


def _rollback_quietly(conn) -> None:
    try:
        conn.execute('ROLLBACK')
    except sqlite3.Error:
        pass   # транзакции уже нет (сбой до BEGIN) или файл недоступен — откатывать нечего


def _ensure_schema(conn, path: str) -> None:
    """Создать/догнать схему один раз на процесс и путь БД (PRAGMA user_version).

    Версия больше нашей (новый код записал, затем откат деплоя) — работаем как
    есть: миграции только аддитивные, старые таблицы и колонки на месте.
    """
    if path in _schema_done:
        return
    with _schema_lock:
        if path in _schema_done:
            return
        conn.execute('BEGIN IMMEDIATE')
        try:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version < 1:
                for sql in _SCHEMA_V1:
                    conn.execute(sql)
            if version < 2:
                for sql in _SCHEMA_V2:
                    conn.execute(sql)
            for table, column, decl in _ADDED_COLUMNS:
                have = {r['name'] for r in conn.execute('PRAGMA table_info(%s)' % table)}
                if column not in have:
                    conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, column, decl))
            if version < SCHEMA_VERSION:
                conn.execute('PRAGMA user_version = %d' % SCHEMA_VERSION)
            conn.execute('COMMIT')
        except BaseException:
            _rollback_quietly(conn)
            raise
        _schema_done.add(path)


@contextmanager
def _transaction(immediate: bool):
    """Транзакция: BEGIN IMMEDIATE (запись) или BEGIN (снимок для чтения).

    Ошибки файла/блокировки превращаются в ReceivingUnavailable; исключения
    логики (ReceiptNotFound и т.п., IntegrityError) проходят как есть.
    """
    conn, path = _connect()
    try:
        try:
            _ensure_schema(conn, path)
            conn.execute('BEGIN IMMEDIATE' if immediate else 'BEGIN')
            try:
                yield conn
                conn.execute('COMMIT')
            except BaseException:
                _rollback_quietly(conn)
                raise
        except sqlite3.DatabaseError as e:
            if 'no such table' in str(e) or 'no such column' in str(e):
                # Файл БД заменили или удалили на ходу (восстановление после сбоя):
                # схема создаётся заново при следующем обращении, а не после рестарта.
                with _schema_lock:
                    _schema_done.discard(path)
            if not _is_unavailable_error(e):
                raise
            raise _unavailable(e) from e
    finally:
        conn.close()


def _read():
    return _transaction(immediate=False)


def _write():
    return _transaction(immediate=True)


# ------------------------------------------------------------------ помощники

def _now() -> datetime:
    """Сейчас по Москве (aware). Подмена часов в тестах — msk_time.now."""
    moment = msk_time.now()
    if moment.tzinfo is None:
        return moment.replace(tzinfo=msk_time.MOSCOW_TZ)
    return moment.astimezone(msk_time.MOSCOW_TZ)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec='seconds')


def _stamp() -> str:
    """Метка «сейчас»: '2026-10-03T14:05:00+03:00'."""
    return _iso(_now())


def _who(user) -> tuple:
    """(login, name) того, кто действует. name = display_name или login;
    действие ИИ-агента через MCP (via_mcp) подписывается « · агент»."""
    if not user:
        return '', ''
    login = str(user.get('login') or '')
    name = str(user.get('display_name') or login)
    if user.get('via_mcp'):
        name = name + AGENT_SUFFIX if name else AGENT_SUFFIX.strip(' ·')
    return login, name


# Наибольшее целое SQLite (INTEGER PRIMARY KEY): номер больше — такой записи быть не может
# (иначе sqlite3 бросил бы OverflowError, а маршрут ответил бы 500 вместо 404).
SQLITE_INT_MAX = 2 ** 63 - 1


def _rid(receipt_id) -> int:
    """Номер приёмки как int; не число или вне 1..SQLITE_INT_MAX -> ReceiptNotFound."""
    if isinstance(receipt_id, bool):
        raise ReceiptNotFound(str(receipt_id))
    try:
        value = int(receipt_id)
    except (TypeError, ValueError):
        raise ReceiptNotFound(str(receipt_id)) from None
    if not 1 <= value <= SQLITE_INT_MAX:
        raise ReceiptNotFound(str(receipt_id))
    return value


def _clamp_limit(limit, default: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(LIST_LIMIT_MAX, value))


def _text(value, limit: Optional[int] = None) -> str:
    s = '' if value is None else str(value)
    return s[:limit] if limit is not None else s


def _note(value, limit: int = NOTE_LIMIT) -> str:
    """Заметка: обрезать края и длину (маршрут уже отказал бы длинной — это страховка)."""
    return _text(value).strip()[:limit]


def _fold(value) -> str:
    """Для поиска: регистр не важен, ё = е."""
    return str(value or '').casefold().replace('ё', 'е')


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _loads(text, default):
    """JSON из колонки; битое или не того типа -> default (строка не должна валить список)."""
    try:
        value = json.loads(text) if text else default
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def _chunks(items: list, size: int = SQL_CHUNK):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _placeholders(n: int) -> str:
    return ','.join('?' * n)


def _check_gtin(gtin) -> str:
    s = str(gtin or '').strip()
    if len(s) != GTIN_LEN or not s.isdigit():
        raise ValueError('GTIN — ровно 14 цифр')
    return s


def _short_raw(raw) -> str:
    """Первые RAW_SHORT_LEN символов сырого кода; GS и прочие управляющие — пробел."""
    s = _text(raw)[:RAW_SHORT_LEN]
    return ''.join(' ' if (ord(ch) < 32 or ord(ch) == 127) else ch for ch in s)


# ------------------------------------------------------------------ словари API

_EMPTY_COUNTS = {'units': 0, 'gtins': 0, 'rejected': 0, 'repeats': 0, 'invoices': 0}


def _counts_for(conn, ids: list) -> Dict[int, dict]:
    """Счётчики приёмок {id: counts} двумя групповыми запросами (без N+1)."""
    out = {rid: dict(_EMPTY_COUNTS) for rid in ids}
    for chunk in _chunks(list(ids)):
        marks = _placeholders(len(chunk))
        for r in conn.execute(
                'SELECT receipt_id,'
                ' SUM(CASE WHEN accepted = 1 THEN 1 ELSE 0 END) AS units,'
                ' COUNT(DISTINCT CASE WHEN accepted = 1 THEN gtin END) AS gtins,'
                " SUM(CASE WHEN accepted = 0 AND reason != 'repeat' THEN 1 ELSE 0 END) AS rejected,"
                " SUM(CASE WHEN accepted = 0 AND reason = 'repeat' THEN 1 ELSE 0 END) AS repeats"
                ' FROM receipt_scans WHERE deleted_at IS NULL AND receipt_id IN (' + marks + ')'
                ' GROUP BY receipt_id', chunk):
            out[r['receipt_id']].update(units=int(r['units'] or 0), gtins=int(r['gtins'] or 0),
                                        rejected=int(r['rejected'] or 0),
                                        repeats=int(r['repeats'] or 0))
        for r in conn.execute(
                'SELECT receipt_id, COUNT(*) AS n FROM receipt_invoices'
                ' WHERE receipt_id IN (' + marks + ') GROUP BY receipt_id', chunk):
            out[r['receipt_id']]['invoices'] = int(r['n'])
    return out


def _counts(conn, receipt_id: int) -> dict:
    return _counts_for(conn, [receipt_id])[receipt_id]


_EMPTY_PROGRESS = {'open': 0, 'closed': 0, 'missing': 0}


def _progress_for(conn, ids: list) -> Dict[int, dict]:
    """Прогресс разбора приёмок {id: {'open','closed','missing'}} групповым запросом.

    По различным GTIN принятых неудалённых сканов приёмки: open — строка разбора
    открыта, closed — закрыта, missing — строки нет (см. докстринг модуля).
    """
    out = {rid: dict(_EMPTY_PROGRESS) for rid in ids}
    for chunk in _chunks(list(ids)):
        for r in conn.execute(
                'SELECT s.receipt_id AS rid,'
                " COUNT(DISTINCT CASE WHEN ri.state = 'open' THEN s.gtin END) AS open_n,"
                " COUNT(DISTINCT CASE WHEN ri.state = 'closed' THEN s.gtin END) AS closed_n,"
                ' COUNT(DISTINCT CASE WHEN ri.gtin IS NULL THEN s.gtin END) AS missing_n'
                ' FROM receipt_scans s LEFT JOIN review_items ri ON ri.gtin = s.gtin'
                ' WHERE s.accepted = 1 AND s.deleted_at IS NULL AND s.gtin IS NOT NULL'
                ' AND s.receipt_id IN (' + _placeholders(len(chunk)) + ') GROUP BY s.receipt_id',
                chunk):
            out[r['rid']] = {'open': int(r['open_n'] or 0), 'closed': int(r['closed_n'] or 0),
                             'missing': int(r['missing_n'] or 0)}
    return out


def _receipt_dict(row, counts: dict, progress: dict) -> dict:
    """receipt dict API. review — прогресс разбора (у открытой приёмки None: её ещё
    сканируют); reviewed — разобрана полностью; can_delete — закрыта и не разобрана
    полностью (правила — докстринг модуля)."""
    closed = row['status'] == 'closed'
    review = dict(progress) if closed else None
    reviewed = bool(closed and row['process_state'] == 'done' and counts.get('gtins', 0) > 0
                    and review['open'] == 0 and review['missing'] == 0)
    return {
        'id': row['id'],
        'status': row['status'],
        'note': row['note'],
        'created_at': row['created_at'],
        'created_by': row['created_by_name'] or row['created_by_login'],
        'closed_at': row['closed_at'],
        'closed_by': row['closed_by_name'] or row['closed_by_login'],
        'process_state': row['process_state'],
        'processed_at': row['processed_at'],
        'process_note': row['process_note'],
        'notified_at': row['notified_at'],
        'counts': counts,
        'review': review,
        'reviewed': reviewed,
        'can_delete': closed and not reviewed,
    }


def _scan_dict(row) -> dict:
    return {
        'id': row['id'],
        'gtin': row['gtin'],
        'kind': row['kind'],
        'accepted': bool(row['accepted']),
        'reason': row['reason'],
        'raw_short': _short_raw(row['raw']),
        'scanned_at': row['scanned_at'],
        'source': row['source'],
        'by': row['scanned_by_name'] or row['scanned_by_login'],
    }


def _invoice_dict(row) -> dict:
    return {
        'name': row['name'],
        'url': INVOICE_URL_PREFIX + row['name'],
        'size': row['size'],
        'uploaded_at': row['uploaded_at'],
        'uploaded_by': row['uploaded_by_name'] or row['uploaded_by_login'],
    }


def _receipt_row(conn, receipt_id: int):
    row = conn.execute('SELECT * FROM receipts WHERE id = ?', (receipt_id,)).fetchone()
    if row is None:
        raise ReceiptNotFound(str(receipt_id))
    return row


def _load_receipt(conn, receipt_id: int) -> dict:
    return _receipt_dict(_receipt_row(conn, receipt_id), _counts(conn, receipt_id),
                         _progress_for(conn, [receipt_id])[receipt_id])


def _receipt_dicts(conn, rows) -> list:
    """Строки receipts -> receipt dict (счётчики и прогресс — групповыми запросами)."""
    ids = [r['id'] for r in rows]
    counts = _counts_for(conn, ids)
    progress = _progress_for(conn, ids)
    return [_receipt_dict(r, counts[r['id']], progress[r['id']]) for r in rows]


def _receipt_ids(value) -> List[int]:
    """Номера приёмок для фильтра: int, строка «2,3» или список. -> без повторов, по порядку.

    Пусто (None, '', []) -> []. Не номер или больше RECEIPT_FILTER_MAX номеров ->
    ValueError (маршрут: 400).
    """
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(',') if part.strip()]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    out = []
    for item in items:
        number = None
        if not isinstance(item, bool):
            try:
                number = int(item)
            except (TypeError, ValueError):
                number = None
        if number is None or not 1 <= number <= SQLITE_INT_MAX:
            raise ValueError('receipt_id — номер приёмки')
        if number not in out:
            out.append(number)
    if len(out) > RECEIPT_FILTER_MAX:
        raise ValueError('receipt_id — не больше %d приёмок' % RECEIPT_FILTER_MAX)
    return out


# ------------------------------------------------------------------ приёмки

def create_receipt(user, note='') -> dict:
    """Открыть новую приёмку. -> receipt dict."""
    login, name = _who(user)
    with _write() as conn:
        cur = conn.execute(
            'INSERT INTO receipts (status, note, created_at, created_by_login, created_by_name)'
            " VALUES ('open', ?, ?, ?, ?)", (_note(note), _stamp(), login, name))
        return _load_receipt(conn, cur.lastrowid)


def get_receipt(receipt_id) -> dict:
    """receipt dict; нет приёмки -> ReceiptNotFound."""
    rid = _rid(receipt_id)
    with _read() as conn:
        return _load_receipt(conn, rid)


def list_receipts(status=None, limit=50) -> list:
    """Приёмки, новые сверху. status: None/'all' — все, 'open' или 'closed'."""
    if status in (None, '', 'all'):
        status = None
    elif status not in RECEIPT_STATUSES:
        raise ValueError('status: open, closed или all')
    limit = _clamp_limit(limit, 50)
    with _read() as conn:
        if status:
            rows = conn.execute('SELECT * FROM receipts WHERE status = ? ORDER BY id DESC LIMIT ?',
                                (status, limit)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM receipts ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return _receipt_dicts(conn, rows)


def review_receipts(recent=20, selected=None) -> list:
    """Приёмки для страницы разбора (выбор приёмок и блок «Приёмки»), новые сверху.

    Все закрытые приёмки, где есть что разбирать (позиции есть, а сверка не done, у
    GTIN нет строки разбора или она открыта — то есть reviewed=False), в любом
    возрасте; плюс последние recent закрытых (история) и выбранные selected, если
    такие номера есть. Кривой selected -> ValueError.
    """
    recent = _clamp_limit(recent, 20)
    wanted = _receipt_ids(selected)
    with _read() as conn:
        ids = {r['id'] for r in conn.execute(
            'SELECT DISTINCT s.receipt_id AS id FROM receipt_scans s'
            ' JOIN receipts r ON r.id = s.receipt_id'
            ' LEFT JOIN review_items ri ON ri.gtin = s.gtin'
            " WHERE r.status = 'closed' AND s.accepted = 1 AND s.deleted_at IS NULL"
            " AND s.gtin IS NOT NULL AND (r.process_state != 'done' OR ri.gtin IS NULL"
            " OR ri.state = 'open')")}
        ids.update(r['id'] for r in conn.execute(
            "SELECT id FROM receipts WHERE status = 'closed' ORDER BY id DESC LIMIT ?", (recent,)))
        ids.update(wanted)
        rows = []
        for chunk in _chunks(sorted(ids)):
            rows.extend(conn.execute('SELECT * FROM receipts WHERE id IN ('
                                     + _placeholders(len(chunk)) + ')', chunk).fetchall())
        rows.sort(key=lambda r: r['id'], reverse=True)
        return _receipt_dicts(conn, rows)


def _lines(conn, rid: int) -> list:
    rows = conn.execute(
        'SELECT gtin, COUNT(*) AS qty, MIN(kind) AS kmin, MAX(kind) AS kmax'
        ' FROM receipt_scans WHERE receipt_id = ? AND accepted = 1 AND deleted_at IS NULL'
        ' AND gtin IS NOT NULL GROUP BY gtin ORDER BY qty DESC, gtin', (rid,)).fetchall()
    return [{'gtin': r['gtin'], 'qty': int(r['qty']),
             'kind': r['kmin'] if r['kmin'] == r['kmax'] else 'mixed'} for r in rows]


def receipt_lines(receipt_id) -> list:
    """Позиции приёмки: [{'gtin','qty','kind'}] по принятым неудалённым сканам.

    kind: 'datamatrix' | 'ean' — все сканы GTIN одного вида; 'mixed' — и так и так
    (часть бутылок прочитали по EAN). Сортировка: qty по убыванию, затем GTIN.
    """
    rid = _rid(receipt_id)
    with _read() as conn:
        _receipt_row(conn, rid)
        return _lines(conn, rid)


def recent_scans(receipt_id, limit=20) -> list:
    """Последние неудалённые сканы (и отклонённые, и повторы), новые сверху."""
    rid = _rid(receipt_id)
    limit = _clamp_limit(limit, 20)
    with _read() as conn:
        _receipt_row(conn, rid)
        rows = conn.execute('SELECT * FROM receipt_scans WHERE receipt_id = ? AND deleted_at IS NULL'
                            ' ORDER BY id DESC LIMIT ?', (rid, limit)).fetchall()
    return [_scan_dict(r) for r in rows]


def dm_keys(receipt_id) -> list:
    """code_key принятых неудалённых DataMatrix: браузер по ним сразу говорит «Уже посчитана»."""
    rid = _rid(receipt_id)
    with _read() as conn:
        _receipt_row(conn, rid)
        rows = conn.execute(
            'SELECT code_key FROM receipt_scans WHERE receipt_id = ? AND kind = ? AND accepted = 1'
            ' AND deleted_at IS NULL ORDER BY id', (rid, KIND_DATAMATRIX)).fetchall()
    return [r['code_key'] for r in rows]


def _replay_result(row) -> str:
    if row['accepted']:
        return RESULT_ACCEPTED
    return RESULT_REPEAT if row['reason'] == REASON_REPEAT else RESULT_REJECTED


def _add_scan_once(rid: int, parsed: dict, raw: str, client_id: str, source: str,
                   client_time: str, login: str, name: str) -> dict:
    with _write() as conn:
        receipt = _receipt_row(conn, rid)
        # Повтор запроса из очереди браузера (ответ потерялся по дороге) — тот же
        # результат. Проверяется ДО «закрыта»: записанный скан уже посчитан, и его
        # ответ не меняется оттого, что приёмку потом закрыли.
        prev = conn.execute('SELECT * FROM receipt_scans WHERE receipt_id = ? AND client_id = ?',
                            (rid, client_id)).fetchone()
        if prev is not None:
            return {'result': _replay_result(prev), 'scan': _scan_dict(prev), 'replayed': True,
                    'counts': _counts(conn, rid)}
        if receipt['status'] != 'open':
            raise ReceiptClosed(str(rid))

        kind = _text(parsed.get('kind') or 'unknown')
        gtin = parsed.get('gtin') or None
        code_key = _text(parsed.get('key'))
        if parsed.get('ok'):
            accepted, reason, result = 1, '', RESULT_ACCEPTED
            if kind == KIND_DATAMATRIX and conn.execute(
                    'SELECT 1 FROM receipt_scans WHERE receipt_id = ? AND code_key = ? AND kind = ?'
                    ' AND accepted = 1 AND deleted_at IS NULL LIMIT 1',
                    (rid, code_key, KIND_DATAMATRIX)).fetchone():
                accepted, reason, result = 0, REASON_REPEAT, RESULT_REPEAT
        else:
            accepted, reason, result = 0, _text(parsed.get('reason') or 'unsupported'), RESULT_REJECTED

        cur = conn.execute(
            'INSERT INTO receipt_scans (receipt_id, client_id, raw, kind, accepted, gtin, code_key,'
            ' reason, source, scanned_at, client_time, scanned_by_login, scanned_by_name)'
            ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (rid, client_id, raw, kind, accepted, gtin, code_key, reason, source, _stamp(),
             client_time, login, name))
        row = conn.execute('SELECT * FROM receipt_scans WHERE id = ?', (cur.lastrowid,)).fetchone()
        return {'result': result, 'scan': _scan_dict(row), 'replayed': False,
                'counts': _counts(conn, rid)}


def add_scan(receipt_id, parsed, raw, client_id, source, client_time, user) -> dict:
    """Записать скан. -> {'result','scan','replayed','counts'}.

    parsed — receiving_codes.parse_code(raw) (маршрут парсит сам; store доверяет).
    - повтор client_id в этой приёмке -> тот же результат, replayed=True, новой строки нет;
    - ok DataMatrix, чей code_key уже принят (и не удалён) -> строка accepted=0,
      reason='repeat', result 'repeat';
    - ok -> accepted=1, result 'accepted' (каждый скан EAN — ещё одна штука);
    - не ok -> accepted=0, reason из разбора, result 'rejected' (храним для диагностики).
    Нет приёмки -> ReceiptNotFound; закрыта -> ReceiptClosed; кривой source или
    пустой client_id -> ValueError.
    """
    rid = _rid(receipt_id)
    client_id = _text(client_id).strip()
    if not client_id or len(client_id) > CLIENT_ID_LIMIT:
        raise ValueError('client_id: от 1 до %d символов' % CLIENT_ID_LIMIT)
    source = source or DEFAULT_SOURCE
    if source not in SOURCES:
        raise ValueError('source: scanner, camera или manual')
    parsed = parsed if isinstance(parsed, dict) else {}
    login, name = _who(user)
    args = (rid, parsed, _text(raw, MAX_RAW), client_id, source,
            _text(client_time, CLIENT_TIME_LIMIT), login, name)
    try:
        return _add_scan_once(*args)
    except sqlite3.IntegrityError:
        # Под BEGIN IMMEDIATE проверка и вставка атомарны, сюда не попадаем. Если всё же
        # сработал уникальный индекс (чужой процесс без нашей транзакции), повторяем:
        # второй проход увидит строку и ответит replay / repeat.
        return _add_scan_once(*args)


def delete_scan(receipt_id, scan_id, user) -> dict:
    """Мягко удалить скан («Отменить последний»). -> {'scan','counts'}.

    Повторное удаление уже удалённого — тот же ответ (повтор запроса безопасен).
    Нет приёмки -> ReceiptNotFound; закрыта -> ReceiptClosed; скан не из этой
    приёмки -> ScanNotFound.
    """
    rid = _rid(receipt_id)
    try:
        sid = int(scan_id)
    except (TypeError, ValueError):
        raise ScanNotFound(str(scan_id)) from None
    if not 1 <= sid <= SQLITE_INT_MAX:
        raise ScanNotFound(str(scan_id))
    login, name = _who(user)
    with _write() as conn:
        receipt = _receipt_row(conn, rid)
        if receipt['status'] != 'open':
            raise ReceiptClosed(str(rid))
        row = conn.execute('SELECT * FROM receipt_scans WHERE id = ? AND receipt_id = ?',
                           (sid, rid)).fetchone()
        if row is None:
            raise ScanNotFound(str(sid))
        if row['deleted_at'] is None:
            conn.execute('UPDATE receipt_scans SET deleted_at = ?, deleted_by_login = ?,'
                         ' deleted_by_name = ? WHERE id = ?', (_stamp(), login, name, sid))
            row = conn.execute('SELECT * FROM receipt_scans WHERE id = ?', (sid,)).fetchone()
        return {'scan': _scan_dict(row), 'counts': _counts(conn, rid)}


def close_receipt(receipt_id, user) -> tuple:
    """Закрыть приёмку и поставить в очередь обработки. -> (receipt, changed).

    open -> closed, process_state='pending'. Уже закрыта -> (receipt, False), ничего
    не меняется (повтор «Завершить» безопасен). Нет приёмки -> ReceiptNotFound.
    """
    rid = _rid(receipt_id)
    login, name = _who(user)
    with _write() as conn:
        cur = conn.execute(
            "UPDATE receipts SET status = 'closed', closed_at = ?, closed_by_login = ?,"
            " closed_by_name = ?, process_state = 'pending' WHERE id = ? AND status = 'open'",
            (_stamp(), login, name, rid))
        return _load_receipt(conn, rid), cur.rowcount == 1


def _claimable_where(now: datetime, retry_error_now: bool = False) -> tuple:
    """Условие «обработку можно (пере)запустить» и его параметры.

    pending — ещё не брали; running с process_started_at не позже now - STALE —
    воркер умер посреди обработки; error с processed_at не позже now - RETRY —
    пора повторить (retry_error_now=True — любую error сразу: человек нажал
    «Завершить» ещё раз). Сравнение строк ISO корректно: формат и смещение +03:00 у
    всех меток одинаковые. Пустая метка ('' через COALESCE) — «очень давно».
    """
    stale_cutoff = _iso(now - timedelta(seconds=PROCESS_STALE_SEC))
    retry_cutoff = _iso(now if retry_error_now else now - timedelta(seconds=PROCESS_RETRY_SEC))
    sql = ("status = 'closed' AND (process_state = 'pending'"
           " OR (process_state = 'running' AND COALESCE(process_started_at, '') <= ?)"
           " OR (process_state = 'error' AND COALESCE(processed_at, '') <= ?))")
    return sql, (stale_cutoff, retry_cutoff)


def claim_processing(receipt_id, retry_error_now: bool = False) -> bool:
    """Атомарно взять обработку приёмки: -> True, если этот вызов её взял.

    Одним UPDATE под BEGIN IMMEDIATE: из двух воркеров (или кнопки и шедулера)
    обработку получит ровно один. retry_error_now — повторное «Завершить» (маршрут
    close): упавшую обработку перезапустить сразу, не дожидаясь PROCESS_RETRY_SEC;
    шедулер повторяет error не чаще раза в час.
    """
    rid = _rid(receipt_id)
    now = _now()
    where, params = _claimable_where(now, retry_error_now)
    with _write() as conn:
        cur = conn.execute("UPDATE receipts SET process_state = 'running', process_started_at = ?"
                           ' WHERE id = ? AND ' + where, (_iso(now), rid) + params)
        return cur.rowcount == 1


def finish_processing(receipt_id, state, note='') -> None:
    """Итог обработки: state 'done' | 'error'; processed_at = сейчас, process_note = note."""
    if state not in FINISH_STATES:
        raise ValueError('state: done или error')
    rid = _rid(receipt_id)
    with _write() as conn:
        cur = conn.execute('UPDATE receipts SET process_state = ?, processed_at = ?, process_note = ?'
                           ' WHERE id = ?', (state, _stamp(), _note(note, PROCESS_NOTE_LIMIT), rid))
        if cur.rowcount != 1:
            raise ReceiptNotFound(str(rid))


def receipts_needing_processing() -> list:
    """Номера закрытых приёмок, которые claim_processing взял бы сейчас (по возрастанию)."""
    where, params = _claimable_where(_now())
    with _read() as conn:
        rows = conn.execute('SELECT id FROM receipts WHERE ' + where + ' ORDER BY id', params).fetchall()
    return [r['id'] for r in rows]


def _deleted_row(item: dict) -> dict:
    """Строка разбора для снимка удалённой приёмки: что было решено по GTIN."""
    chz = item['chz'] if isinstance(item['chz'], dict) else {}
    return {'gtin': item['gtin'], 'status': item['status'], 'state': item['state'],
            'resolution': item['resolution'], 'supplier': item['supplier'], 'note': item['note'],
            'chz_name': _text(chz.get('name')),
            'resolved_at': item['resolved_at'],
            'resolved_by': item['resolved_by_name'] or item['resolved_by_login']}


def delete_receipt(receipt_id, user) -> dict:
    """Удалить закрытую приёмку, разобранную не полностью (блок «Приёмки» на разборе).
    -> {'receipt','lines','invoices','rows_deleted','rows_kept','deleted_at','deleted_by'}.

    Можно только закрытую (открытую ещё сканируют — ReceiptOpen) и только с
    reviewed=False (разобранная полностью — запись о сделанной работе, она остаётся в
    истории — ReceiptReviewed). Нет приёмки — ReceiptNotFound. Одной транзакцией:
    - строки разбора GTIN, которых нет ни в одной другой закрытой приёмке, удаляются
      вместе с решениями по ним (их принесла только эта приёмка; GTIN из ещё открытой
      приёмки заведётся заново при её закрытии);
    - у строк, общих с другими закрытыми приёмками, убираются только ссылки на эту
      (first/last_receipt_id, notify_receipt_id); количество и список приёмок строки
      считаются по сканам и уменьшаются сами;
    - удаляются сама приёмка, её сканы и записи о фото; файлы фото удаляет вызывающий
      (routes/receiving.py) по именам из invoices, когда запись в базе прошла.
    Остаётся запись в receipt_deletions: кто и когда удалил и снимок (приёмка,
    позиции, фото, удалённые строки разбора). Номер не переиспользуется (AUTOINCREMENT).
    Обработка этой приёмки, идущая в ту же секунду, дальше ничего не заведёт:
    upsert_review видит, что приёмки нет, и бросает ReceiptNotFound.
    rows_deleted — число удалённых строк разбора, rows_kept — общих, оставшихся.
    """
    rid = _rid(receipt_id)
    login, name = _who(user)
    now = _stamp()
    with _write() as conn:
        receipt = _load_receipt(conn, rid)
        if receipt['status'] != 'closed':
            raise ReceiptOpen(str(rid))
        if receipt['reviewed']:
            raise ReceiptReviewed(str(rid))
        lines = _lines(conn, rid)
        invoices = [r['name'] for r in conn.execute(
            'SELECT name FROM receipt_invoices WHERE receipt_id = ? ORDER BY id', (rid,))]
        deleted_rows = []
        kept = 0
        for chunk in _chunks([line['gtin'] for line in lines]):
            marks = _placeholders(len(chunk))
            others = {r['gtin']: r for r in conn.execute(
                'SELECT s.gtin AS gtin, MIN(s.receipt_id) AS first_id, MAX(s.receipt_id) AS last_id'
                ' FROM receipt_scans s JOIN receipts r ON r.id = s.receipt_id'
                " WHERE r.status = 'closed' AND s.receipt_id != ? AND s.accepted = 1"
                ' AND s.deleted_at IS NULL AND s.gtin IN (' + marks + ') GROUP BY s.gtin',
                [rid] + chunk)}
            items = {r['gtin']: _parse_review(r) for r in conn.execute(
                'SELECT * FROM review_items WHERE gtin IN (' + marks + ')', chunk)}
            for gtin in chunk:
                item = items.get(gtin)
                if item is None:
                    continue
                other = others.get(gtin)
                if other is None:
                    conn.execute('DELETE FROM review_items WHERE gtin = ?', (gtin,))
                    deleted_rows.append(_deleted_row(item))
                    continue
                conn.execute(
                    'UPDATE review_items SET'
                    ' first_receipt_id = CASE WHEN first_receipt_id = :rid THEN :first'
                    ' ELSE first_receipt_id END,'
                    ' last_receipt_id = CASE WHEN last_receipt_id = :rid THEN :last'
                    ' ELSE last_receipt_id END,'
                    ' notify_receipt_id = CASE WHEN notify_receipt_id = :rid THEN NULL'
                    ' ELSE notify_receipt_id END WHERE gtin = :gtin',
                    {'rid': rid, 'first': other['first_id'], 'last': other['last_id'], 'gtin': gtin})
                kept += 1
        snapshot = {'receipt': receipt, 'lines': lines, 'invoices': invoices,
                    'rows_deleted': deleted_rows, 'rows_kept': kept}
        conn.execute('INSERT OR REPLACE INTO receipt_deletions (receipt_id, deleted_at,'
                     ' deleted_by_login, deleted_by_name, snapshot_json) VALUES (?, ?, ?, ?, ?)',
                     (rid, now, login, name, _dumps(snapshot)))
        # Сканы и фото ушли бы и каскадом (ON DELETE CASCADE, foreign_keys=ON) — явное
        # удаление не зависит от того, включены ли внешние ключи у соединения.
        conn.execute('DELETE FROM receipt_invoices WHERE receipt_id = ?', (rid,))
        conn.execute('DELETE FROM receipt_scans WHERE receipt_id = ?', (rid,))
        conn.execute('DELETE FROM receipts WHERE id = ?', (rid,))
    return {'receipt': receipt, 'lines': lines, 'invoices': invoices,
            'rows_deleted': len(deleted_rows), 'rows_kept': kept,
            'deleted_at': now, 'deleted_by': name or login}


# ------------------------------------------------------------------ фото накладных

def add_invoice(receipt_id, name, size, user) -> dict:
    """Записать фото накладной (файл уже сохранён receiving_photo_store). -> invoice dict.

    Закрытой приёмке фото добавлять можно: накладную часто снимают после пересчёта.
    """
    rid = _rid(receipt_id)
    name = _text(name).strip()
    if not name:
        raise ValueError('Нет имени файла')
    login, name_by = _who(user)
    with _write() as conn:
        _receipt_row(conn, rid)
        try:
            cur = conn.execute('INSERT INTO receipt_invoices (receipt_id, name, size, uploaded_at,'
                               ' uploaded_by_login, uploaded_by_name) VALUES (?, ?, ?, ?, ?, ?)',
                               (rid, name, int(size or 0), _stamp(), login, name_by))
        except sqlite3.IntegrityError:
            raise ValueError('Фото с таким именем уже есть') from None
        row = conn.execute('SELECT * FROM receipt_invoices WHERE id = ?', (cur.lastrowid,)).fetchone()
        return _invoice_dict(row)


def list_invoices(receipt_id) -> list:
    """Фото накладных приёмки в порядке загрузки."""
    rid = _rid(receipt_id)
    with _read() as conn:
        _receipt_row(conn, rid)
        rows = conn.execute('SELECT * FROM receipt_invoices WHERE receipt_id = ? ORDER BY id',
                            (rid,)).fetchall()
    return [_invoice_dict(r) for r in rows]


def delete_invoice(receipt_id, name) -> bool:
    """Удалить запись о фото. -> True, если запись была (файл удаляет маршрут)."""
    rid = _rid(receipt_id)
    with _write() as conn:
        cur = conn.execute('DELETE FROM receipt_invoices WHERE receipt_id = ? AND name = ?',
                           (rid, _text(name)))
        return cur.rowcount > 0


# ------------------------------------------------------------------ строки разбора

def _clean_chz(chz) -> dict:
    """Данные ЧЗ для строки разбора: только CHZ_FIELDS, строками. Пусто -> {}.

    «Пусто» — нет ни одного текстового поля (одна пометка source без названия
    ничего не сообщает бухгалтеру и не должна затирать прежние данные).
    """
    if not isinstance(chz, dict):
        return {}
    out = {k: _text(chz.get(k)).strip() for k in CHZ_FIELDS}
    if not any(out[k] for k in CHZ_TEXT_FIELDS):
        return {}
    return out


def _clean_list(items) -> list:
    return [dict(x) for x in (items or []) if isinstance(x, dict)]


def _check_status(status) -> str:
    if status not in STATUSES:
        raise ValueError('status: ' + ', '.join(STATUSES))
    return status


def _parse_review(row) -> dict:
    """Строка таблицы -> словарь с разобранным JSON (ещё без qty/receipts)."""
    item = dict(row)
    item['cards'] = _loads(item.pop('cards_json', None), [])
    item['candidates'] = _loads(item.pop('candidates_json', None), [])
    item['chz'] = _loads(item.pop('chz_json', None), {})
    return item


def _review_receipts(conn, gtins: List[str]) -> Dict[str, list]:
    """{gtin: [{'id','qty','closed_at'}]} по ЗАКРЫТЫМ приёмкам, новые сверху."""
    out = {g: [] for g in gtins}
    for chunk in _chunks(list(gtins)):
        for r in conn.execute(
                'SELECT s.gtin AS gtin, s.receipt_id AS rid, COUNT(*) AS qty, r.closed_at AS closed_at'
                ' FROM receipt_scans s JOIN receipts r ON r.id = s.receipt_id'
                " WHERE r.status = 'closed' AND s.accepted = 1 AND s.deleted_at IS NULL"
                ' AND s.gtin IN (' + _placeholders(len(chunk)) + ')'
                ' GROUP BY s.gtin, s.receipt_id ORDER BY s.receipt_id DESC', chunk):
            out[r['gtin']].append({'id': r['rid'], 'qty': int(r['qty']), 'closed_at': r['closed_at']})
    return out


def _review_row(item: dict, receipts: list) -> dict:
    cards = item['cards']
    first = cards[0] if cards and isinstance(cards[0], dict) else {}
    return {
        'gtin': item['gtin'],
        'barcode': receiving_codes.barcode_for_iiko(item['gtin']),
        'status': item['status'],
        'state': item['state'],
        'resolution': item['resolution'],
        'cards': cards,
        'candidates': item['candidates'],
        'chz': item['chz'],
        'supplier': item['supplier'],
        'supplier_hint': _text(first.get('supplier')),
        'note': item['note'],
        'qty': sum(r['qty'] for r in receipts),
        'receipts': receipts,
        'first_seen_at': item['first_seen_at'],
        'last_seen_at': item['last_seen_at'],
        'classified_at': item['classified_at'],
        'index_built_at': item['index_built_at'],
        'updated_at': item['updated_at'],
        'updated_by': item['updated_by_name'] or item['updated_by_login'],
        'resolved_at': item['resolved_at'],
        'resolved_by': item['resolved_by_name'] or item['resolved_by_login'],
        'reopened': int(item['reopened'] or 0),
    }


def _load_review(conn, gtin: str) -> dict:
    row = conn.execute('SELECT * FROM review_items WHERE gtin = ?', (gtin,)).fetchone()
    if row is None:
        raise ReviewItemNotFound(gtin)
    return _review_row(_parse_review(row), _review_receipts(conn, [gtin])[gtin])


def _auto_close_sql() -> str:
    """SET-часть автозакрытия: карточка нашлась в индексе -> closed/auto."""
    return ("state = 'closed', resolution = 'auto', resolved_at = :now,"
            " resolved_by_login = '', resolved_by_name = :actor")


def _older(built: str, than) -> bool:
    """Индекс built старше метки than (обе — ISO с +03:00, сравнение строк корректно).

    Пустой built — время индекса неизвестно, считаем его старым; пустая than —
    сравнивать не с чем, built не старше."""
    than = str(than or '')
    return bool(than) and (not built or built < than)


def upsert_review(gtin, receipt_id, status, cards, candidates, chz, index_built_at) -> dict:
    """Строка разбора по итогам обработки приёмки. -> {'row','opened','reopened'}.

    - Строки нет -> вставить. status 'found' -> сразу closed/found (сводка для
      истории); иначе open (opened=True, notify_receipt_id = эта приёмка).
    - Строка есть, а индекс СТАРШЕ того, по которому строка уже сверена
      (index_built_at), -> устаревшие сведения: обновить только last_receipt_id,
      last_seen_at и chz (если новый не пуст); статус и состояние не трогать.
    - Иначе всегда обновить status, cards, candidates, classified_at,
      index_built_at, last_receipt_id, last_seen_at; chz — только если новый не пуст.
      Дальше по состоянию:
      - open и status 'found' -> closed, resolution 'auto', resolved_by 'индекс iiko';
        open и не found -> остаётся open (opened=False: строка уже в очереди);
      - closed/not_needed -> остаётся закрытой (бухгалтер решил: не заводим);
      - closed/(found|auto|done) и status != 'found' -> снова open, resolution '',
        resolved_* очищены, reopened += 1, notify_receipt_id = эта приёмка
        (opened=True, reopened=True): карточку удалили, заархивировали или
        задублировали после закрытия. НО только если индекс собран ПОЗЖЕ закрытия
        (resolved_at): индекс старше решения бухгалтера ещё не видит карточку,
        которую он только что завёл, — такую строку не трогаем (иначе «Сделано»
        вернулось бы «Новой» и толкнуло бы завести в iiko дубль).
    - supplier и note не трогаются никогда.
    Приёмки receipt_id нет (удалили во время обработки) -> ReceiptNotFound, ничего не пишется.
    """
    gtin = _check_gtin(gtin)
    status = _check_status(status)
    rid = None if receipt_id is None else _rid(receipt_id)
    cards_json = _dumps(_clean_list(cards))
    candidates_json = _dumps(_clean_list(candidates))
    chz_clean = _clean_chz(chz)
    built = _text(index_built_at)
    now = _stamp()
    opened = reopened = False
    with _write() as conn:
        if rid is not None and conn.execute('SELECT 1 FROM receipts WHERE id = ?', (rid,)).fetchone() is None:
            # Приёмку удалили, пока шла её обработка (delete_receipt): строк ей не заводим.
            raise ReceiptNotFound(str(rid))
        row = conn.execute('SELECT state, resolution, resolved_at, index_built_at FROM review_items'
                           ' WHERE gtin = ?', (gtin,)).fetchone()
        if row is None:
            found = status == 'found'
            conn.execute(
                'INSERT INTO review_items (gtin, status, state, resolution, cards_json,'
                ' candidates_json, chz_json, first_receipt_id, last_receipt_id, first_seen_at,'
                ' last_seen_at, classified_at, index_built_at, updated_at, resolved_at,'
                ' resolved_by_name, notify_receipt_id)'
                ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (gtin, status, 'closed' if found else 'open', 'found' if found else '',
                 cards_json, candidates_json, _dumps(chz_clean), rid, rid, now, now, now, built,
                 now, now if found else None, INDEX_ACTOR if found else '',
                 None if found else rid))
            opened = not found
        else:
            params = {'gtin': gtin, 'status': status, 'cards': cards_json,
                      'candidates': candidates_json, 'now': now, 'built': built, 'rid': rid,
                      'chz': _dumps(chz_clean), 'actor': INDEX_ACTOR}
            sets = ['last_receipt_id = :rid', 'last_seen_at = :now']
            if chz_clean:
                sets.append('chz_json = :chz')
            resolved_late = (row['state'] == 'closed' and row['resolution'] != 'not_needed'
                             and status != 'found' and _older(built, row['resolved_at']))
            if not (_older(built, row['index_built_at']) or resolved_late):
                sets += ['status = :status', 'cards_json = :cards', 'candidates_json = :candidates',
                         'classified_at = :now', 'index_built_at = :built']
                if row['state'] == 'open':
                    if status == 'found':
                        sets.append(_auto_close_sql())
                elif row['resolution'] != 'not_needed' and status != 'found':
                    sets.append("state = 'open', resolution = '', resolved_at = NULL,"
                                " resolved_by_login = '', resolved_by_name = '',"
                                ' reopened = reopened + 1, notify_receipt_id = :rid')
                    opened = reopened = True
            conn.execute('UPDATE review_items SET ' + ', '.join(sets) + ' WHERE gtin = :gtin', params)
        return {'row': _load_review(conn, gtin), 'opened': opened, 'reopened': reopened}


def reclassify_open(gtin, status, cards, candidates, chz=None, index_built_at='') -> dict:
    """Пересверка открытой строки после обновления индекса. -> {'row','auto_closed'}.

    Только для state='open' (закрытая возвращается как есть) и только если индекс не
    старше того, по которому строка уже сверена: обновить status, cards, candidates,
    classified_at, index_built_at (если передан), chz (если не пуст). status 'found'
    -> закрыть: resolution 'auto', resolved_by 'индекс iiko'.
    Нет строки -> ReviewItemNotFound.
    """
    gtin = _check_gtin(gtin)
    status = _check_status(status)
    chz_clean = _clean_chz(chz)
    built = _text(index_built_at)
    with _write() as conn:
        row = conn.execute('SELECT state, index_built_at FROM review_items WHERE gtin = ?',
                           (gtin,)).fetchone()
        if row is None:
            raise ReviewItemNotFound(gtin)
        if row['state'] != 'open' or (built and _older(built, row['index_built_at'])):
            return {'row': _load_review(conn, gtin), 'auto_closed': False}
        params = {'gtin': gtin, 'status': status, 'cards': _dumps(_clean_list(cards)),
                  'candidates': _dumps(_clean_list(candidates)), 'now': _stamp(),
                  'built': built, 'chz': _dumps(chz_clean), 'actor': INDEX_ACTOR}
        sets = ['status = :status', 'cards_json = :cards', 'candidates_json = :candidates',
                'classified_at = :now']
        if built:
            sets.append('index_built_at = :built')
        if chz_clean:
            sets.append('chz_json = :chz')
        auto_closed = status == 'found'
        if auto_closed:
            sets.append(_auto_close_sql())
        conn.execute('UPDATE review_items SET ' + ', '.join(sets) + ' WHERE gtin = :gtin', params)
        return {'row': _load_review(conn, gtin), 'auto_closed': auto_closed}


def recheck_done(gtin, status, cards, candidates, index_built_at) -> dict:
    """Проверка «Сделано» свежим индексом. -> {'row','reopened'}.

    Только для строк closed/done и только индексом, собранным ПОЗЖЕ решения
    (resolved_at): иначе строка возвращается как есть. Карточка нашлась (found) —
    строка остаётся закрытой, статус и карточки обновляются (сделано подтверждено).
    Не нашлась — бухгалтер нажал «Сделано», а GTIN в iiko так и не появился на
    актуальной карточке (опечатка в штрихкоде, привязали не к той карточке): строка
    снова open, reopened += 1. Сообщения в Telegram это не вызывает (приёмки нет).
    """
    gtin = _check_gtin(gtin)
    status = _check_status(status)
    built = _text(index_built_at)
    with _write() as conn:
        row = conn.execute('SELECT state, resolution, resolved_at FROM review_items WHERE gtin = ?',
                           (gtin,)).fetchone()
        if row is None:
            raise ReviewItemNotFound(gtin)
        if (row['state'] != 'closed' or row['resolution'] != 'done' or not built
                or _older(built, row['resolved_at']) or built == str(row['resolved_at'] or '')):
            return {'row': _load_review(conn, gtin), 'reopened': False}
        params = {'gtin': gtin, 'status': status, 'cards': _dumps(_clean_list(cards)),
                  'candidates': _dumps(_clean_list(candidates)), 'now': _stamp(), 'built': built}
        sets = ['status = :status', 'cards_json = :cards', 'candidates_json = :candidates',
                'classified_at = :now', 'index_built_at = :built']
        reopened = status != 'found'
        if reopened:
            # notify_receipt_id = NULL: переоткрыла не приёмка, сообщение о ней не шлём заново.
            sets.append("state = 'open', resolution = '', resolved_at = NULL,"
                        " resolved_by_login = '', resolved_by_name = '', reopened = reopened + 1,"
                        ' notify_receipt_id = NULL')
        conn.execute('UPDATE review_items SET ' + ', '.join(sets) + ' WHERE gtin = :gtin', params)
        return {'row': _load_review(conn, gtin), 'reopened': reopened}


def done_review_gtins() -> list:
    """GTIN строк «Сделано», ещё не подтверждённых индексом (статус не found) — для recheck_done."""
    with _read() as conn:
        rows = conn.execute("SELECT gtin FROM review_items WHERE state = 'closed'"
                            " AND resolution = 'done' AND status != 'found' ORDER BY gtin").fetchall()
    return [r['gtin'] for r in rows]


def rows_to_notify(receipt_id) -> list:
    """Строки, открытые этой приёмкой и всё ещё открытые, — о них сообщение бухгалтерии.

    Берётся из базы, а не из итога одного прогона обработки: прогон, упавший между
    открытием строк и отправкой, повторится — и сообщение уйдёт, а не потеряется.
    """
    rid = _rid(receipt_id)
    with _read() as conn:
        gtins = [r['gtin'] for r in conn.execute(
            "SELECT gtin FROM review_items WHERE state = 'open' AND notify_receipt_id = ?"
            ' ORDER BY gtin', (rid,)).fetchall()]
        return [_load_review(conn, g) for g in gtins]


def mark_notified(receipt_id) -> None:
    """Отметить: о приёмке бухгалтерии сообщено (или сообщать было не о чем)."""
    rid = _rid(receipt_id)
    with _write() as conn:
        cur = conn.execute('UPDATE receipts SET notified_at = ? WHERE id = ?', (_stamp(), rid))
        if cur.rowcount != 1:
            raise ReceiptNotFound(str(rid))


def get_review_item(gtin) -> dict:
    """review row по GTIN; нет -> ReviewItemNotFound."""
    gtin = _text(gtin).strip()
    with _read() as conn:
        return _load_review(conn, gtin)


def _haystack(item: dict) -> str:
    """Текст, в котором ищет q: GTIN, штрихкод для iiko, ЧЗ, имена карточек, поставщик, заметка."""
    chz = item['chz'] if isinstance(item['chz'], dict) else {}
    parts = [item['gtin'], receiving_codes.barcode_for_iiko(item['gtin']),
             chz.get('name'), chz.get('brand'), item['supplier'], item['note']]
    for card in list(item['cards']) + list(item['candidates']):
        if isinstance(card, dict):
            parts.append(card.get('name'))
    return _fold('\n'.join(str(p) for p in parts if p))


def _review_counts(items: Iterable[dict]) -> dict:
    counts = {'open': {s: 0 for s in OPEN_COUNT_STATUSES}, 'open_total': 0, 'closed_total': 0}
    for item in items:
        if item['state'] == 'open':
            counts['open_total'] += 1
            if item['status'] in counts['open']:
                counts['open'][item['status']] += 1
        else:
            counts['closed_total'] += 1
    return counts


def list_review(state='open', statuses=None, receipt_id=None, q='', limit=200) -> dict:
    """Очередь бухгалтерии. -> {'rows','total','counts'}.

    state: 'open' | 'closed' | 'all'; statuses — список из STATUSES (пусто — все);
    receipt_id — только GTIN, принятые в этих приёмках (по неудалённым сканам): номер,
    строка «2,3» или список, до RECEIPT_FILTER_MAX номеров;
    q — подстрока (регистр не важен, ё = е) в GTIN, штрихкоде для iiko, названии и
    бренде ЧЗ, именах карточек и кандидатов, поставщике, заметке.
    Сортировка: открытые раньше; статус new, similar, restore, duplicate, found;
    затем last_seen_at по убыванию; затем GTIN.
    total — сколько строк подошло до limit. counts — счётчики вкладок в той же
    области (receipt_id и q учтены, state и statuses — нет: вкладки их и
    переключают): {'open': {new, similar, restore, duplicate}, 'open_total',
    'closed_total'}. Кривой state, статус или receipt_id -> ValueError (маршрут: 400).
    """
    state = state or 'open'
    if state not in LIST_STATES:
        raise ValueError('state: open, closed или all')
    if isinstance(statuses, str):
        statuses = [s.strip() for s in statuses.split(',') if s.strip()]
    wanted = set(statuses or ())
    bad = wanted - set(STATUSES)
    if bad:
        raise ValueError('status: ' + ', '.join(STATUSES))
    rids = _receipt_ids(receipt_id)
    limit = _clamp_limit(limit, 200)
    needle = _fold(q).strip()
    with _read() as conn:
        if rids:
            rows = conn.execute(
                'SELECT * FROM review_items WHERE gtin IN (SELECT gtin FROM receipt_scans'
                ' WHERE receipt_id IN (' + _placeholders(len(rids)) + ') AND accepted = 1'
                ' AND deleted_at IS NULL AND gtin IS NOT NULL)' + _REVIEW_ORDER_SQL, rids).fetchall()
        else:
            rows = conn.execute('SELECT * FROM review_items' + _REVIEW_ORDER_SQL).fetchall()
        items = [_parse_review(r) for r in rows]
        if needle:
            items = [it for it in items if needle in _haystack(it)]
        counts = _review_counts(items)
        selected = [it for it in items
                    if (state == 'all' or it['state'] == state)
                    and (not wanted or it['status'] in wanted)]
        page = selected[:limit]
        receipts = _review_receipts(conn, [it['gtin'] for it in page])
        return {'rows': [_review_row(it, receipts[it['gtin']]) for it in page],
                'total': len(selected), 'counts': counts}


def update_review(gtin, user, supplier=None, state=None, note=None) -> dict:
    """Правка бухгалтера. -> review row.

    supplier — строка ('' — очистить; маршрут уже проверил по справочнику и
    передаёт каноническое имя); state: 'done' | 'not_needed' -> closed +
    resolution + resolved_* (кто и когда), 'open' -> open, resolution '',
    resolved_* очищены («Вернуть в разбор»); note — до NOTE_LIMIT символов.
    Ничего не передано или кривой state -> ValueError; нет строки -> ReviewItemNotFound.
    """
    if supplier is None and state is None and note is None:
        raise ValueError('Нечего менять: supplier, state или note')
    if state is not None and state not in USER_STATES:
        raise ValueError('state: done, not_needed или open')
    gtin = _text(gtin).strip()
    login, name = _who(user)
    now = _stamp()
    params = {'gtin': gtin, 'now': now, 'login': login, 'name': name}
    sets = ['updated_at = :now', 'updated_by_login = :login', 'updated_by_name = :name']
    if supplier is not None:
        params['supplier'] = _text(supplier).strip()
        sets.append('supplier = :supplier')
    if note is not None:
        params['note'] = _note(note)
        sets.append('note = :note')
    if state == 'open':
        sets.append("state = 'open', resolution = '', resolved_at = NULL,"
                    " resolved_by_login = '', resolved_by_name = ''")
    elif state is not None:
        params['resolution'] = state
        sets.append("state = 'closed', resolution = :resolution, resolved_at = :now,"
                    ' resolved_by_login = :login, resolved_by_name = :name')
    with _write() as conn:
        cur = conn.execute('UPDATE review_items SET ' + ', '.join(sets) + ' WHERE gtin = :gtin', params)
        if cur.rowcount != 1:
            raise ReviewItemNotFound(gtin)
        return _load_review(conn, gtin)


def open_review_gtins() -> list:
    """GTIN открытых строк разбора (по возрастанию) — для пересверки после обновления индекса."""
    with _read() as conn:
        rows = conn.execute("SELECT gtin FROM review_items WHERE state = 'open' ORDER BY gtin").fetchall()
    return [r['gtin'] for r in rows]


# ------------------------------------------------------------------ кэш карточек ЧЗ

def _chz_dict(row) -> dict:
    return {
        'gtin': row['gtin'],
        'found': bool(row['found']),
        'name': row['name'],
        'brand': row['brand'],
        'full_name': row['full_name'],
        'product_group': row['product_group'],
        'volume': row['volume'],
        'package_type': row['package_type'],
        'raw': _loads(row['raw_json'], {}),
        'source': row['source'],
        'fetched_at': row['fetched_at'],
    }


def get_chz_products(gtins) -> dict:
    """Кэш ответов ЧЗ: {gtin: {'gtin','found': bool, name..., 'raw': dict, 'source','fetched_at'}}.

    Нет в кэше — GTIN в ответе отсутствует. found=False — «в ЧЗ такого нет» на
    момент fetched_at (receiving_chz не переспрашивает такие NEGATIVE_TTL_DAYS).
    """
    wanted = []
    seen = set()
    for g in gtins or ():
        s = _text(g).strip()
        if s and s not in seen:
            seen.add(s)
            wanted.append(s)
    if not wanted:
        return {}
    out = {}
    with _read() as conn:
        for chunk in _chunks(wanted):
            for r in conn.execute('SELECT * FROM chz_products WHERE gtin IN ('
                                  + _placeholders(len(chunk)) + ')', chunk):
                out[r['gtin']] = _chz_dict(r)
    return out


def save_chz_products(rows: list) -> None:
    """Сохранить ответы ЧЗ (upsert по GTIN) одной транзакцией.

    row: {'gtin','found','name','brand','full_name','product_group','volume',
    'package_type','raw','source','fetched_at'?}; fetched_at нет — сейчас.
    Строка без GTIN -> ValueError (ничего не пишется).
    """
    prepared = []
    now = _stamp()
    for row in rows or ():
        gtin = _text(row.get('gtin')).strip()
        if not gtin:
            raise ValueError('Строка ЧЗ без GTIN')
        raw = row.get('raw')
        prepared.append((
            gtin, 1 if row.get('found') else 0,
            _text(row.get('name')), _text(row.get('brand')), _text(row.get('full_name')),
            _text(row.get('product_group')), _text(row.get('volume')),
            _text(row.get('package_type')),
            _dumps(raw if isinstance(raw, dict) else {}), _text(row.get('source')),
            _text(row.get('fetched_at')) or now))
    if not prepared:
        return
    with _write() as conn:
        conn.executemany(
            'INSERT INTO chz_products (gtin, found, name, brand, full_name, product_group, volume,'
            ' package_type, raw_json, source, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            ' ON CONFLICT(gtin) DO UPDATE SET found = excluded.found, name = excluded.name,'
            ' brand = excluded.brand, full_name = excluded.full_name,'
            ' product_group = excluded.product_group, volume = excluded.volume,'
            ' package_type = excluded.package_type, raw_json = excluded.raw_json,'
            ' source = excluded.source, fetched_at = excluded.fetched_at', prepared)
