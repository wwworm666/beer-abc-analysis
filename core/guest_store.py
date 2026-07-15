"""Хранилище модуля «Аналитика гостей (CRM)» — SQLite-витрина гостевых чеков.

Зачем локальная база, а не «живой» OLAP: Lifetime-когорты, retention от первой
покупки и сочетаемость товаров требуют полной истории чеков (~с 2017-12), что
невозможно считать на лету из iiko при каждом просмотре. Витрина наполняется
помесячным ETL (core/guest_sync.py) в фоне; все отчёты раздела «Гости» —
SQL-запросы по этой базе без обращений к iiko.

Идентичность гостя: guest_id = канонический телефон (см. normalize_guest_id в
core/guest_sync.py); номер пластиковой карты — псевдоним в guest_aliases.
По разведке Фазы 0 (2026-07-15) оба поля заполнены в 100% гостевых строк OLAP.

Дедуп и конкурентность под gunicorn --workers 2: WAL + busy_timeout (как
core/shifts_manager.py / core/temperature_store.py), запись только из фонового
синка (один процесс за прогон гарантируют O_EXCL-локи шедулера).

Путь к БД: /kultura/guests.db на проде (persistent volume), data/guests.db
локально. Файл в .gitignore (data/*.db).

Документация: docs/guests.md
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from core.venues_config import PHYSICAL_VENUES

SCHEMA_VERSION = 1


def _default_db_path():
    """Путь к БД: persistent volume на проде, иначе локальная папка data/."""
    if os.path.exists("/kultura"):
        return "/kultura/guests.db"
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "guests.db")


def _venue_order_sql(column):
    """SQL CASE для детерминированного tie-break по порядку заведений.

    Используется при выборе «первой точки» гостя, когда в один и тот же первый
    день есть чеки в двух барах: порядок PHYSICAL_VENUES, неизвестные точки
    (исторические, например закрытые бары) — после известных, затем по имени.
    """
    parts = [f"CASE {column}"]
    for i, key in enumerate(PHYSICAL_VENUES):
        parts.append(f" WHEN '{key}' THEN {i}")
    parts.append(" ELSE 99 END")
    return "".join(parts)


class GuestStore:
    """Потокобезопасный доступ к витрине гостевых чеков."""

    def __init__(self, db_path=None):
        self.db_path = db_path or _default_db_path()
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Создание схемы + additive-миграции по PRAGMA user_version.

        Паттерн core/shifts_manager.py: версия схемы в user_version; при будущих
        миграциях (v2+) перед ALTER делается бэкап файла через SQLite backup API.
        v1 — начальная схема.
        """
        with self._lock, self._conn() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS guests (
                        guest_id            TEXT PRIMARY KEY,
                        name                TEXT,
                        phone               TEXT,
                        card_number         TEXT,
                        registration_date   TEXT,
                        registration_source TEXT NOT NULL DEFAULT 'iiko',
                        first_order_date    TEXT,
                        first_order_store   TEXT,
                        last_visit_date     TEXT,
                        updated_at          TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS receipts (
                        open_date TEXT NOT NULL,
                        store     TEXT NOT NULL,
                        order_num TEXT NOT NULL,
                        guest_id  TEXT NOT NULL,
                        revenue   REAL NOT NULL,
                        discount  REAL NOT NULL,
                        full_sum  REAL,
                        PRIMARY KEY (open_date, store, order_num, guest_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_receipts_guest
                        ON receipts(guest_id, open_date);
                    CREATE INDEX IF NOT EXISTS idx_receipts_date
                        ON receipts(open_date);

                    CREATE TABLE IF NOT EXISTS receipt_items (
                        open_date TEXT NOT NULL,
                        store     TEXT NOT NULL,
                        order_num TEXT NOT NULL,
                        guest_id  TEXT NOT NULL,
                        dish_name TEXT NOT NULL,
                        amount    REAL NOT NULL,
                        revenue   REAL NOT NULL,
                        PRIMARY KEY (open_date, store, order_num, guest_id, dish_name)
                    );
                    CREATE INDEX IF NOT EXISTS idx_items_dish
                        ON receipt_items(dish_name, open_date);
                    CREATE INDEX IF NOT EXISTS idx_items_guest
                        ON receipt_items(guest_id);

                    CREATE TABLE IF NOT EXISTS guest_aliases (
                        alias    TEXT PRIMARY KEY,
                        guest_id TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS sync_state (
                        month     TEXT PRIMARY KEY,
                        status    TEXT NOT NULL,
                        receipts  INTEGER,
                        items     INTEGER,
                        synced_at TEXT,
                        frozen    INTEGER NOT NULL DEFAULT 0
                    );
                    """
                )
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                conn.commit()

    # ------------------------------------------------------------------ запись

    def mark_month(self, ym, status):
        """Пометить месяц ('YYYY-MM') как in_progress/error, не трогая данные."""
        now = datetime.now().isoformat(timespec='seconds')
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO sync_state (month, status, synced_at)
                VALUES (?, ?, ?)
                ON CONFLICT(month) DO UPDATE SET status=excluded.status,
                                                 synced_at=excluded.synced_at
                """,
                (ym, status, now),
            )
            conn.commit()

    def replace_month(self, ym, receipts, items, aliases, guest_attrs, frozen):
        """Идемпотентная замена месяца одной транзакцией.

        receipts:    {(open_date, store, order_num, guest_id): {revenue, discount, full_sum}}
        items:       {(open_date, store, order_num, guest_id, dish_name): {amount, revenue}}
        aliases:     {alias: guest_id}
        guest_attrs: {guest_id: {phone, card_number, name, min_created, max_date}}
                     max_date — последняя дата визита гостя в ЭТОМ батче: имя/карта
                     обновляются, только если батч содержит его последний визит
                     (детерминизм при ресинке старого месяца).
        frozen:      1 — месяц закрыт (прошлый), повторный синк только force.

        Шаги: удалить чеки/позиции месяца -> вставить заново -> upsert гостей и
        псевдонимов -> пересчитать денормализацию (first/last visit, первая точка)
        по затронутым гостям -> удалить гостей, оставшихся без чеков -> sync_state.
        """
        month_start = f"{ym}-01"
        month_end_excl = (f"{int(ym[:4]) + 1}-01-01" if ym[5:7] == "12"
                          else f"{ym[:4]}-{int(ym[5:7]) + 1:02d}-01")
        now = datetime.now().isoformat(timespec='seconds')
        venue_order = _venue_order_sql("r.store")

        with self._lock, self._conn() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")

                # Гости, чьи чеки будут удалены (могут исчезнуть при ресинке)
                affected = {row['guest_id'] for row in conn.execute(
                    "SELECT DISTINCT guest_id FROM receipts "
                    "WHERE open_date >= ? AND open_date < ?",
                    (month_start, month_end_excl))}
                affected.update(guest_attrs.keys())

                conn.execute(
                    "DELETE FROM receipts WHERE open_date >= ? AND open_date < ?",
                    (month_start, month_end_excl))
                conn.execute(
                    "DELETE FROM receipt_items WHERE open_date >= ? AND open_date < ?",
                    (month_start, month_end_excl))

                conn.executemany(
                    "INSERT OR REPLACE INTO receipts "
                    "(open_date, store, order_num, guest_id, revenue, discount, full_sum) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(k[0], k[1], k[2], k[3],
                      v['revenue'], v['discount'], v['full_sum'])
                     for k, v in receipts.items()])

                conn.executemany(
                    "INSERT OR REPLACE INTO receipt_items "
                    "(open_date, store, order_num, guest_id, dish_name, amount, revenue) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(k[0], k[1], k[2], k[3], k[4], v['amount'], v['revenue'])
                     for k, v in items.items()])

                conn.executemany(
                    "INSERT OR REPLACE INTO guest_aliases (alias, guest_id) VALUES (?, ?)",
                    list(aliases.items()))

                # Базовый upsert гостя + монотонное MIN-обновление даты регистрации:
                # непустая «Дата создания клиента» из iiko всегда сильнее fallback.
                for gid, a in guest_attrs.items():
                    conn.execute(
                        """
                        INSERT INTO guests (guest_id, name, phone, card_number,
                                            registration_date, registration_source,
                                            updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(guest_id) DO NOTHING
                        """,
                        (gid, a.get('name') or '', a.get('phone') or '',
                         a.get('card_number') or '',
                         a.get('min_created') or None,
                         'iiko' if a.get('min_created') else 'first_order',
                         now),
                    )
                    if a.get('min_created'):
                        conn.execute(
                            """
                            UPDATE guests
                            SET registration_date = CASE
                                    WHEN registration_source = 'first_order'
                                         OR registration_date IS NULL
                                         OR registration_date = ''
                                         OR ? < registration_date
                                    THEN ? ELSE registration_date END,
                                registration_source = 'iiko',
                                updated_at = ?
                            WHERE guest_id = ?
                            """,
                            (a['min_created'], a['min_created'], now, gid),
                        )

                # Денормализация по затронутым гостям (авторитет — receipts)
                for gid in affected:
                    conn.execute(
                        f"""
                        UPDATE guests SET
                            first_order_date = (
                                SELECT MIN(open_date) FROM receipts r
                                WHERE r.guest_id = guests.guest_id),
                            last_visit_date = (
                                SELECT MAX(open_date) FROM receipts r
                                WHERE r.guest_id = guests.guest_id),
                            first_order_store = (
                                SELECT r.store FROM receipts r
                                WHERE r.guest_id = guests.guest_id
                                ORDER BY r.open_date ASC, {venue_order} ASC, r.store ASC
                                LIMIT 1),
                            updated_at = ?
                        WHERE guest_id = ?
                        """,
                        (now, gid),
                    )

                # Имя/карта/телефон — из батча, только если он содержит последний визит
                for gid, a in guest_attrs.items():
                    conn.execute(
                        """
                        UPDATE guests SET name = ?, phone = ?, card_number = ?, updated_at = ?
                        WHERE guest_id = ?
                          AND (last_visit_date IS NULL OR last_visit_date <= ?)
                        """,
                        (a.get('name') or '', a.get('phone') or '',
                         a.get('card_number') or '', now, gid, a.get('max_date') or ''),
                    )

                # Fallback ТЗ: нет даты создания из iiko -> регистрация = первая покупка
                conn.execute(
                    """
                    UPDATE guests
                    SET registration_date = first_order_date,
                        registration_source = 'first_order'
                    WHERE (registration_date IS NULL OR registration_date = '')
                      AND first_order_date IS NOT NULL
                    """
                )

                # Гости без единого чека после ресинка — зеркалу не нужны
                conn.execute(
                    "DELETE FROM guests WHERE guest_id NOT IN "
                    "(SELECT DISTINCT guest_id FROM receipts)")

                conn.execute(
                    """
                    INSERT INTO sync_state (month, status, receipts, items, synced_at, frozen)
                    VALUES (?, 'ok', ?, ?, ?, ?)
                    ON CONFLICT(month) DO UPDATE SET
                        status='ok', receipts=excluded.receipts, items=excluded.items,
                        synced_at=excluded.synced_at, frozen=excluded.frozen
                    """,
                    (ym, len(receipts), len(items), now, 1 if frozen else 0),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # ------------------------------------------------------------------ чтение

    @contextmanager
    def conn(self):
        """Публичное соединение для расчётного слоя (core/guest_analytics.py).
        Только чтение; запись идёт через replace_month/mark_month."""
        with self._conn() as c:
            yield c

    def get_aliases(self):
        """Глобальный словарь псевдонимов {alias: guest_id}."""
        with self._conn() as conn:
            return {row['alias']: row['guest_id'] for row in
                    conn.execute("SELECT alias, guest_id FROM guest_aliases")}

    def sync_state_map(self):
        """{month: {status, receipts, items, synced_at, frozen}}."""
        with self._conn() as conn:
            return {row['month']: dict(row) for row in
                    conn.execute("SELECT * FROM sync_state ORDER BY month")}

    def coverage(self):
        """Покрытие данных: границы дат чеков, размер базы, последний синк."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT MIN(open_date) AS date_from, MAX(open_date) AS date_to, "
                "COUNT(*) AS receipts FROM receipts").fetchone()
            guests = conn.execute("SELECT COUNT(*) AS n FROM guests").fetchone()['n']
            synced = conn.execute(
                "SELECT MAX(synced_at) AS s FROM sync_state WHERE status='ok'"
            ).fetchone()['s']
            return {
                'date_from': row['date_from'],
                'date_to': row['date_to'],
                'receipts': row['receipts'],
                'guests': guests,
                'last_synced_at': synced,
            }

    def data_version(self):
        """Метка версии данных для инвалидации кэшей отчётов после синка."""
        with self._conn() as conn:
            row = conn.execute("SELECT MAX(synced_at) AS s FROM sync_state").fetchone()
            return row['s'] or ''

    def month_counts(self, ym):
        """Контрольные числа месяца для приёмочной сверки (docs/guests.md)."""
        month_start = f"{ym}-01"
        month_end_excl = (f"{int(ym[:4]) + 1}-01-01" if ym[5:7] == "12"
                          else f"{ym[:4]}-{int(ym[5:7]) + 1:02d}-01")
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS receipts,
                       COUNT(DISTINCT guest_id) AS guests,
                       ROUND(SUM(revenue), 2) AS revenue
                FROM receipts WHERE open_date >= ? AND open_date < ?
                """,
                (month_start, month_end_excl)).fetchone()
            regs = conn.execute(
                """
                SELECT COUNT(*) AS n FROM guests
                WHERE registration_source = 'iiko'
                  AND registration_date >= ? AND registration_date < ?
                """,
                (month_start, month_end_excl)).fetchone()['n']
            return {'receipts': row['receipts'], 'guests': row['guests'],
                    'revenue': row['revenue'], 'registrations': regs}


# Синглтон процесса (как temperature_store.get_store()).
_STORE = None
_STORE_LOCK = threading.Lock()


def get_store():
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = GuestStore()
    return _STORE
