"""
Менеджер смен для системы управления графиком.
Использует SQLite для хранения данных.
Сотрудники берутся из iiko API — здесь хранятся только смены, выходные и выручка.
"""

import sqlite3
import threading
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from contextlib import contextmanager


# Маппинг точек на ключи заведений в data/daily_plans.json / plansdashboard.json.
# Единственное место связи locations <-> venue_key.
LOCATION_VENUE_KEYS = {
    'Варшавская': 'varshavskaya',
    'Большой пр. В.О': 'bolshoy',
    'Кременчугская': 'kremenchugskaya',
    'Лиговский': 'ligovskiy',
}


class ShiftsManager:
    """Thread-safe менеджер для работы со сменами в SQLite."""

    # Версия схемы. Миграции ТОЛЬКО additive (ALTER TABLE ADD COLUMN /
    # CREATE TABLE IF NOT EXISTS) — DROP запрещён: в проде живые данные.
    # Перед миграцией файл БД копируется в shifts.db.backup_v{N}.
    # v4: таблица schedule_audit (журнал «кто что менял в графике»).
    # v5: roles.rate_per_hour — ставка за час по ролям (расчёт ЗП считает часы
    #     из графика × ставку роли; iiko как источник часов оплаты больше не нужен).
    # v6: shifts.employee_id + schedule_employees.iiko_id — стабильный ключ
    #     сотрудника из iiko (GUID). employee_name остаётся только для показа/
    #     фоллбэка и обновляется на актуальное при синке. Переименование сотрудника
    #     в iiko больше не плодит дублей: смены и реестр привязаны к id, а не к
    #     строке-имени. См. sync_employees() и docs/schedule.md.
    SCHEMA_VERSION = 6

    def __init__(self, db_path: str = None):
        self.db_path = db_path or self._get_default_path()
        self._lock = threading.Lock()
        self._init_database()

    def _get_default_path(self) -> str:
        """Определить путь к БД: Render disk или локальная папка."""
        if os.path.exists('/kultura'):
            return '/kultura/shifts.db'
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, 'shifts.db')

    @contextmanager
    def _get_connection(self):
        """Context manager для подключения к БД.

        WAL-mode + busy_timeout: под gunicorn 2 worker'а пишут в shifts.db одновременно;
        с дефолтным rollback journal писатели блокируют читателей и друг друга.
        WAL даёт concurrent read+write; busy_timeout=5000 ретраит блокировки.
        """
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            # FK в SQLite по умолчанию выключены, хотя в схеме объявлены. Без этого
            # смена создаётся с несуществующими location_id/role_id (orphan), а INNER JOIN
            # потом прячет её из сетки и занижает часы. Включаем на каждом подключении.
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            conn.close()

    def _backup_before_migration(self, conn, current_version: int):
        """Снять консистентный снапшот БД перед миграцией схемы.

        Используется SQLite backup API (а не копирование файла): при WAL-режиме
        простой copy главного файла без -wal даёт неконсистентный снимок.
        """
        if not os.path.exists(self.db_path):
            return
        backup_path = f"{self.db_path}.backup_v{current_version}"
        try:
            dst = sqlite3.connect(backup_path)
            try:
                conn.backup(dst)
            finally:
                dst.close()
            print(f"[ShiftsManager] Бэкап БД перед миграцией: {backup_path}")
        except Exception as e:
            print(f"[ShiftsManager WARNING] Не удалось создать бэкап БД: {e}")

    @staticmethod
    def _ensure_columns(cursor, table: str, columns: Dict[str, str]):
        """Additive-миграция: добавить недостающие колонки таблицы.

        columns: {имя: SQL-объявление типа}. Существующие колонки не трогаются —
        ALTER TABLE ADD COLUMN в SQLite не меняет имеющиеся данные.

        'duplicate column' глотается: под gunicorn 2 воркера мигрируют
        одновременно, и второй может проиграть гонку между проверкой и ALTER.
        """
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        for name, decl in columns.items():
            if name in existing:
                continue
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                print(f"[ShiftsManager] Миграция: ALTER TABLE {table} ADD COLUMN {name} {decl}")
            except sqlite3.OperationalError as e:
                if 'duplicate column' in str(e).lower():
                    print(f"[ShiftsManager] Колонка {table}.{name} уже добавлена другим воркером")
                else:
                    raise

    def _init_database(self):
        """Создать недостающие таблицы/колонки. Никогда не удаляет данные."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Проверяем версию схемы
                cursor.execute("PRAGMA user_version")
                current_version = cursor.fetchone()[0]

                if current_version < self.SCHEMA_VERSION:
                    self._backup_before_migration(conn, current_version)
                    print(f"[ShiftsManager] Миграция схемы v{current_version} -> v{self.SCHEMA_VERSION} (additive)")

                # Точки (бары). venue_key — мост к планам (data/daily_plans.json).
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS locations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        short_name TEXT NOT NULL,
                        venue_key TEXT
                    )
                ''')

                # Роли. rate_per_hour — ставка за час (v5): расчёт ЗП берёт часы из
                # графика (fact_minutes) и умножает на ставку роли смены.
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS roles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        short_name TEXT,
                        color TEXT,
                        sort_order INTEGER DEFAULT 0,
                        rate_per_hour REAL NOT NULL DEFAULT 300
                    )
                ''')

                # Смены — employee_name хранится напрямую (из iiko API).
                # start_time — ПЛАНОВОЕ время начала 'HH:MM'; NULL = стандартная смена.
                # fact_minutes — ФАКТ отработанных минут, вводится барменом руками
                # в конце смены (единственный источник факта часов: смена может
                # длиться дольше кассовой, по API это не вытащить).
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS shifts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        employee_name TEXT NOT NULL,
                        location_id INTEGER NOT NULL,
                        role_id INTEGER NOT NULL,
                        notes TEXT,
                        start_time TEXT,
                        fact_minutes INTEGER,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (location_id) REFERENCES locations(id),
                        FOREIGN KEY (role_id) REFERENCES roles(id)
                    )
                ''')

                # Пожелания выходных — employee_name напрямую
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS day_off_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        employee_name TEXT NOT NULL,
                        date_from TEXT NOT NULL,
                        date_to TEXT NOT NULL,
                        reason TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Выручка по дням
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS daily_revenue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        location_id INTEGER NOT NULL,
                        plan_revenue REAL DEFAULT 0,
                        fact_revenue REAL,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (location_id) REFERENCES locations(id),
                        UNIQUE(date, location_id)
                    )
                ''')

                # Пожелания сотрудников (свободный текст)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS wishes (
                        employee_name TEXT PRIMARY KEY,
                        text TEXT NOT NULL DEFAULT '',
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Реестр сотрудников графика. iiko — поставщик кандидатов (upsert,
                # никогда не удаляет): сотрудник в отпуске >30 дней пропадает из
                # OLAP-выборки, но остаётся здесь. Ключ — имя как в iiko, чтобы
                # не мигрировать shifts.employee_name.
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS schedule_employees (
                        name TEXT PRIMARY KEY,
                        short_label TEXT,
                        active INTEGER NOT NULL DEFAULT 1,
                        sort_order INTEGER NOT NULL DEFAULT 0
                    )
                ''')

                # Журнал изменений графика (v4): append-only «кто что менял».
                # actor_name — снимок display_name автора (журнал читается, даже
                # если аккаунт потом переименуют/удалят). entity_date — дата, к
                # которой относится изменение (для фильтра истории по месяцу).
                # summary — готовая русская строка для показа. Журнал ничего не
                # удаляет и не редактирует — только добавляет записи.
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS schedule_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        actor_login TEXT,
                        actor_name TEXT,
                        action TEXT NOT NULL,
                        entity_date TEXT,
                        employee_name TEXT,
                        summary TEXT NOT NULL
                    )
                ''')

                # Additive-миграции для БД, созданных прошлыми версиями схемы
                self._ensure_columns(cursor, 'shifts', {
                    'start_time': 'TEXT',
                    'fact_minutes': 'INTEGER',
                })
                self._ensure_columns(cursor, 'locations', {
                    'venue_key': 'TEXT',
                })
                # v5: ставка за час по ролям. DEFAULT 300 = текущая единая ставка,
                # поэтому до правок владельцем оплата не меняется.
                self._ensure_columns(cursor, 'roles', {
                    'rate_per_hour': 'REAL NOT NULL DEFAULT 300',
                })
                # v6: стабильный ключ сотрудника из iiko (GUID). employee_name —
                # только показ/фоллбэк, обновляется на актуальное при синке.
                # day_off/wishes получают employee_id впрок (на будущее).
                self._ensure_columns(cursor, 'shifts', {'employee_id': 'TEXT'})
                self._ensure_columns(cursor, 'schedule_employees', {'iiko_id': 'TEXT'})
                self._ensure_columns(cursor, 'day_off_requests', {'employee_id': 'TEXT'})
                self._ensure_columns(cursor, 'wishes', {'employee_id': 'TEXT'})

                # Индексы
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_shifts_date ON shifts(date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_shifts_employee ON shifts(employee_name)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_shifts_emp_id ON shifts(employee_id)')
                cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_emp_iiko_id '
                               'ON schedule_employees(iiko_id) WHERE iiko_id IS NOT NULL')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_shifts_location ON shifts(location_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_dayoff_employee ON day_off_requests(employee_name)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_dayoff_dates ON day_off_requests(date_from, date_to)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_revenue_date ON daily_revenue(date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_entity_date ON schedule_audit(entity_date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_id ON schedule_audit(id)')

                cursor.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
                conn.commit()

                # Seed-данные
                self._seed_data(cursor, conn)

    def _seed_data(self, cursor, conn):
        """Начальные данные: точки и роли."""
        cursor.execute('SELECT COUNT(*) FROM locations')
        if cursor.fetchone()[0] == 0:
            # Сокращения — канонические, как у владельца: Варш, Крем, ВО, Лиг
            locations = [
                ('Варшавская', 'Варш'),
                ('Большой пр. В.О', 'ВО'),
                ('Кременчугская', 'Крем'),
                ('Лиговский', 'Лиг'),
            ]
            cursor.executemany(
                'INSERT INTO locations (name, short_name) VALUES (?, ?)',
                locations
            )
            print(f"[ShiftsManager] Добавлено {len(locations)} точек")

        # Проставить venue_key существующим точкам (идемпотентно)
        for name, venue_key in LOCATION_VENUE_KEYS.items():
            cursor.execute(
                "UPDATE locations SET venue_key = ? WHERE name = ? "
                "AND (venue_key IS NULL OR venue_key = '')",
                (venue_key, name)
            )

        # Починить устаревшие сокращения в существующих БД (только известные
        # старые значения — пользовательские правки не трогаются)
        for name, old_short, new_short in (
            ('Варшавская', 'Вар', 'Варш'),
            ('Кременчугская', 'Кр', 'Крем'),
        ):
            cursor.execute(
                "UPDATE locations SET short_name = ? WHERE name = ? AND short_name = ?",
                (new_short, name, old_short)
            )

        cursor.execute('SELECT COUNT(*) FROM roles')
        if cursor.fetchone()[0] == 0:
            roles = [
                ('бармен', 'Б', '#4CAF50', 1),
                ('второй бармен', '2Б', '#2196F3', 2),
            ]
            cursor.executemany(
                'INSERT INTO roles (name, short_name, color, sort_order) VALUES (?, ?, ?, ?)',
                roles
            )
            print(f"[ShiftsManager] Добавлено {len(roles)} ролей")

        # Роль «стажёр» убрана (владелец: только бармен и второй бармен).
        # Удаляем ТОЛЬКО если на неё не ссылается ни одна смена — иначе смены
        # осиротели бы (role_id FK). Идемпотентно, как прочие seed-фиксы выше.
        cursor.execute('''
            DELETE FROM roles
            WHERE name = 'стажёр'
              AND id NOT IN (SELECT DISTINCT role_id FROM shifts)
        ''')

        conn.commit()

    # ==================== LOCATIONS ====================

    def get_locations(self) -> List[Dict]:
        """Получить список точек."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM locations ORDER BY id')
                return [dict(row) for row in cursor.fetchall()]

    # ==================== ROLES ====================

    def get_roles(self) -> List[Dict]:
        """Получить список ролей (включая rate_per_hour — ставку за час)."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM roles ORDER BY sort_order')
                return [dict(row) for row in cursor.fetchall()]

    def set_role_rate(self, role_id: int, rate_per_hour: float) -> bool:
        """Установить ставку за час для роли (используется в расчёте ЗП)."""
        rate = max(0.0, float(rate_per_hour))
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE roles SET rate_per_hour = ? WHERE id = ?',
                               (rate, role_id))
                conn.commit()
                return cursor.rowcount > 0

    # ==================== SHIFTS ====================

    def get_shifts_for_month(self, year: int, month: int) -> List[Dict]:
        """Получить все смены за месяц."""
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT
                        s.id, s.date, s.employee_name, s.employee_id, s.notes,
                        s.start_time, s.fact_minutes,
                        l.id as location_id, l.name as location_name, l.short_name as location_short,
                        r.id as role_id, r.name as role_name, r.short_name as role_short, r.color as role_color
                    FROM shifts s
                    JOIN locations l ON s.location_id = l.id
                    JOIN roles r ON s.role_id = r.id
                    WHERE s.date >= ? AND s.date <= ?
                    ORDER BY s.date, l.id, r.sort_order
                ''', (first_day.isoformat(), last_day.isoformat()))
                return [dict(row) for row in cursor.fetchall()]

    def get_shifts_for_employee(self, employee_id: str,
                                date_from: str, date_to: str) -> List[Dict]:
        """Смены одного сотрудника (по стабильному employee_id) за диапазон дат
        включительно — для экспорта личного графика в календарь (.ics,
        core/calendar_ics.py). Пустой employee_id -> []."""
        if not employee_id:
            return []
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT
                        s.id, s.date, s.employee_name, s.employee_id,
                        s.start_time, s.fact_minutes,
                        l.id as location_id, l.name as location_name, l.short_name as location_short,
                        l.venue_key as venue_key,
                        r.id as role_id, r.name as role_name
                    FROM shifts s
                    JOIN locations l ON s.location_id = l.id
                    JOIN roles r ON s.role_id = r.id
                    WHERE s.employee_id = ? AND s.date >= ? AND s.date <= ?
                    ORDER BY s.date, s.start_time
                ''', (employee_id, date_from, date_to))
                return [dict(row) for row in cursor.fetchall()]

    def get_shift(self, shift_id: int) -> Optional[Dict]:
        """Одна смена с именами точки и роли (для журнала: читаемое описание
        изменения и снимок состояния перед удалением)."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT
                        s.id, s.date, s.employee_name, s.employee_id, s.notes,
                        s.start_time, s.fact_minutes,
                        l.id as location_id, l.name as location_name, l.short_name as location_short,
                        r.id as role_id, r.name as role_name, r.short_name as role_short
                    FROM shifts s
                    JOIN locations l ON s.location_id = l.id
                    JOIN roles r ON s.role_id = r.id
                    WHERE s.id = ?
                ''', (shift_id,))
                row = cursor.fetchone()
                return dict(row) if row else None

    def get_hours_by_role_for_period(self, date_from: str, date_to: str) -> List[Dict]:
        """Часы по ролям и оплата для каждого сотрудника за период (для расчёта ЗП).

        Источник часов — fact_minutes из графика: это единственный верный источник
        часов оплаты (iiko-часы для оплаты больше не используются). Смены без факта
        (fact_minutes NULL) часов не дают, но попадают в shifts_without_fact, чтобы
        на странице ЗП было видно пробелы. Оплата роли = часы × roles.rate_per_hour.
        Даты включительно (date >= from AND date <= to).
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Идентичность сотрудника — стабильный employee_id (v6), имя только
                # для показа. Фоллбэк на имя, пока у смены нет id (до бэкофилла).
                cursor.execute('''
                    SELECT COALESCE(s.employee_id, s.employee_name) AS emp_key,
                           MIN(s.employee_name) AS employee_name,
                           r.id AS role_id, r.name AS role_name, r.short_name AS role_short,
                           COALESCE(r.rate_per_hour, 0) AS rate_per_hour,
                           r.sort_order AS sort_order,
                           COALESCE(SUM(s.fact_minutes), 0) AS minutes,
                           SUM(CASE WHEN s.fact_minutes IS NOT NULL THEN 1 ELSE 0 END) AS shifts_with_fact,
                           SUM(CASE WHEN s.fact_minutes IS NULL THEN 1 ELSE 0 END) AS shifts_without_fact
                    FROM shifts s
                    JOIN roles r ON s.role_id = r.id
                    WHERE s.date >= ? AND s.date <= ?
                    GROUP BY emp_key, r.id
                    ORDER BY employee_name, r.sort_order
                ''', (date_from, date_to))
                rows = [dict(row) for row in cursor.fetchall()]

        by_emp = {}
        for row in rows:
            emp = by_emp.setdefault(row['emp_key'], {
                'employee_name': row['employee_name'],
                'roles': [], 'total_minutes': 0, 'total_pay': 0.0,
                'shifts_with_fact': 0, 'shifts_without_fact': 0,
            })
            minutes = row['minutes'] or 0
            rate = row['rate_per_hour'] or 0
            pay = minutes / 60.0 * rate
            emp['roles'].append({
                'role_id': row['role_id'], 'role_name': row['role_name'],
                'role_short': row['role_short'], 'rate_per_hour': rate,
                'minutes': minutes, 'hours': round(minutes / 60.0, 2),
                'pay': round(pay, 2),
            })
            emp['total_minutes'] += minutes
            emp['total_pay'] += pay
            emp['shifts_with_fact'] += row['shifts_with_fact']
            emp['shifts_without_fact'] += row['shifts_without_fact']

        result = []
        for emp in by_emp.values():
            emp['total_hours'] = round(emp['total_minutes'] / 60.0, 2)
            emp['total_pay'] = round(emp['total_pay'], 2)
            result.append(emp)
        result.sort(key=lambda e: -e['total_pay'])
        return result

    def create_shift(self, date_str: str, employee_name: str, location_id: int,
                     role_id: int, notes: str = None, start_time: str = None,
                     employee_id: str = None) -> int:
        """Создать смену. start_time 'HH:MM' — плановое начало (NULL = стандарт).
        employee_id — стабильный id сотрудника из iiko (v6); employee_name пишется
        как снимок для показа/фоллбэка."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO shifts (date, employee_name, location_id, role_id, notes, start_time, employee_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (date_str, employee_name, location_id, role_id, notes, start_time, employee_id))
                conn.commit()
                return cursor.lastrowid

    def set_shift_fact(self, shift_id: int, fact_minutes: Optional[int]) -> bool:
        """Записать факт отработанных минут (None = очистить).

        Вводится барменом руками в конце смены — единственный источник факта часов.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE shifts SET fact_minutes = ?, updated_at = ? WHERE id = ?',
                    (fact_minutes, datetime.now().isoformat(), shift_id)
                )
                conn.commit()
                return cursor.rowcount > 0

    def update_shift(self, shift_id: int, **kwargs) -> bool:
        """Обновить смену. Факт часов сюда НЕ входит — он меняется только через
        set_shift_fact (роут /fact с проверкой 0..1440), чтобы битые минуты не
        попадали в расчёт ЗП в обход валидации."""
        allowed = {'date', 'employee_name', 'location_id', 'role_id', 'notes',
                   'start_time'}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False

        updates['updated_at'] = datetime.now().isoformat()
        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values()) + [shift_id]

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f'UPDATE shifts SET {set_clause} WHERE id = ?', values)
                conn.commit()
                return cursor.rowcount > 0

    def delete_shift(self, shift_id: int) -> bool:
        """Удалить смену."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM shifts WHERE id = ?', (shift_id,))
                conn.commit()
                return cursor.rowcount > 0

    # ==================== DAY OFF REQUESTS ====================

    def get_day_off_requests(self, employee_name: str = None,
                              date_from: str = None, date_to: str = None) -> List[Dict]:
        """Получить пожелания выходных с фильтрацией."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = 'SELECT * FROM day_off_requests WHERE 1=1'
                params = []

                if employee_name:
                    query += ' AND employee_name = ?'
                    params.append(employee_name)

                if date_from:
                    query += ' AND date_to >= ?'
                    params.append(date_from)

                if date_to:
                    query += ' AND date_from <= ?'
                    params.append(date_to)

                query += ' ORDER BY date_from'
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]

    def get_day_off_request(self, request_id: int) -> Optional[Dict]:
        """Одна заявка на выходной по id (для журнала перед удалением)."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM day_off_requests WHERE id = ?', (request_id,))
                row = cursor.fetchone()
                return dict(row) if row else None

    def create_day_off_request(self, employee_name: str, date_from: str,
                                date_to: str, reason: str = None) -> int:
        """Создать пожелание выходного."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO day_off_requests (employee_name, date_from, date_to, reason)
                    VALUES (?, ?, ?, ?)
                ''', (employee_name, date_from, date_to, reason))
                conn.commit()
                return cursor.lastrowid

    def delete_day_off_request(self, request_id: int) -> bool:
        """Удалить пожелание выходного."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM day_off_requests WHERE id = ?', (request_id,))
                conn.commit()
                return cursor.rowcount > 0

    # ==================== REVENUE ====================

    def get_revenue_for_day(self, date_str: str) -> List[Dict]:
        """Получить выручку по всем точкам за день."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT
                        l.id as location_id, l.name as location_name, l.short_name,
                        COALESCE(r.plan_revenue, 0) as plan_revenue,
                        r.fact_revenue
                    FROM locations l
                    LEFT JOIN daily_revenue r ON l.id = r.location_id AND r.date = ?
                    ORDER BY l.id
                ''', (date_str,))
                return [dict(row) for row in cursor.fetchall()]

    def get_revenue_for_month(self, year: int, month: int) -> List[Dict]:
        """Все записи план/факт выручки за месяц (для сводки и фоллбэка планов)."""
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT date, location_id, plan_revenue, fact_revenue
                    FROM daily_revenue
                    WHERE date >= ? AND date <= ?
                    ORDER BY date, location_id
                ''', (first_day.isoformat(), last_day.isoformat()))
                return [dict(row) for row in cursor.fetchall()]

    def update_revenue(self, date_str: str, location_id: int,
                       plan_revenue: float = None, fact_revenue: float = None) -> bool:
        """Обновить или создать запись о выручке (атомарный UPSERT).

        Read-modify-write (SELECT, затем UPDATE/INSERT) под per-process Lock не защищал
        от гонки между 2 воркерами gunicorn: оба видели «строки нет» и шли в INSERT ->
        UNIQUE(date, location_id) -> IntegrityError у второго -> 500, а sync-month рвался
        на середине месяца. Единый INSERT ... ON CONFLICT делает это одной атомарной
        операцией и идемпотентно. None-аргумент сохраняет прежнее значение (COALESCE);
        у новой строки plan по умолчанию 0, fact = NULL — как раньше.
        """
        now = datetime.now().isoformat()
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO daily_revenue (date, location_id, plan_revenue, fact_revenue, updated_at)
                    VALUES (?, ?, COALESCE(?, 0), ?, ?)
                    ON CONFLICT(date, location_id) DO UPDATE SET
                        plan_revenue = COALESCE(?, plan_revenue),
                        fact_revenue = COALESCE(?, fact_revenue),
                        updated_at = ?
                ''', (date_str, location_id, plan_revenue, fact_revenue, now,
                      plan_revenue, fact_revenue, now))
                conn.commit()
                return True

    def sync_revenue_from_iiko(self, date_str: str, revenue_by_location: Dict[str, float]) -> int:
        """Синхронизировать фактическую выручку из iiko."""
        updated = 0
        locations = {loc['name']: loc['id'] for loc in self.get_locations()}

        for location_name, fact_revenue in revenue_by_location.items():
            location_id = locations.get(location_name)
            if location_id:
                self.update_revenue(date_str, location_id, fact_revenue=fact_revenue)
                updated += 1

        return updated

    # ==================== WISHES ====================

    def get_wishes(self) -> List[Dict]:
        """Получить все пожелания."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT employee_name, text FROM wishes ORDER BY employee_name')
                return [dict(row) for row in cursor.fetchall()]

    def save_wish(self, employee_name: str, text: str) -> bool:
        """Сохранить или обновить пожелание сотрудника."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO wishes (employee_name, text, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(employee_name) DO UPDATE SET
                        text = excluded.text,
                        updated_at = excluded.updated_at
                ''', (employee_name, text, datetime.now().isoformat()))
                conn.commit()
                return True

    # ==================== SCHEDULE EMPLOYEES ====================

    @staticmethod
    def _norm_name(n: str) -> str:
        """Нормализация имени для сопоставления независимо от порядка слов
        («Васильев Никита» == «Никита Васильев»)."""
        return ' '.join(sorted((n or '').strip().lower().split()))

    def get_schedule_employees(self, include_inactive: bool = False) -> List[Dict]:
        """Реестр сотрудников графика + люди из смен, которых нет в реестре.

        Идентичность — стабильный iiko_id (поле `id`). Имя — для показа.
        Записи из shifts (по id или, если id ещё нет, по имени) добавляются
        виртуально, чтобы история смен никогда не осталась без сотрудника в списке.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT iiko_id AS id, name, short_label, active, sort_order, 1 AS in_registry
                    FROM schedule_employees
                    UNION
                    SELECT DISTINCT s.employee_id AS id, s.employee_name AS name,
                           NULL, 1, 999, 0
                    FROM shifts s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM schedule_employees e
                        WHERE (e.iiko_id IS NOT NULL AND e.iiko_id = s.employee_id)
                           OR e.name = s.employee_name
                    )
                    ORDER BY sort_order, name
                ''')
                rows = [dict(row) for row in cursor.fetchall()]
        if not include_inactive:
            rows = [r for r in rows if r['active']]
        return rows

    def sync_employees(self, pairs, overrides=None) -> Dict:
        """Синхронизация реестра графика с iiko по СТАБИЛЬНОМУ id (v6).

        pairs: список (iiko_id, name) — текущий справочник iiko.
        overrides: {старое_имя_в_сменах: iiko_id_или_текущее_имя} — ручная привязка
            для редких случаев, где имя изменилось так, что авто-сопоставление по
            строке невозможно (напр. «Артемий»→«Артем»). Разовая чистка наследия.

        В одной транзакции (идемпотентно):
          1) upsert реестра по iiko_id (имя обновляется на текущее; legacy-строка с
             тем же именем «усыновляется» — получает id, сохраняя метку/порядок);
          2) распространение переименований: shifts.employee_name по employee_id;
          3) бэкофилл shifts.employee_id у смен без него (override → точное имя →
             однозначная перестановка слов); имя смены при этом канонизируется;
          4) удаление осиротевших legacy-строк реестра (без id и без смен по имени).
        Возвращает отчёт с числами и списком несопоставленных имён.
        """
        overrides = overrides or {}
        pairs = [(str(i).strip(), (n or '').strip())
                 for i, n in pairs if i and (n or '').strip()]
        id_to_name, name_to_id, norm_to_ids = {}, {}, {}
        for i, n in pairs:
            id_to_name[i] = n
            name_to_id.setdefault(n, i)
            norm_to_ids.setdefault(self._norm_name(n), set()).add(i)

        def resolve(name):
            ov = overrides.get(name)
            if ov:
                if ov in id_to_name:
                    return ov
                if ov in name_to_id:
                    return name_to_id[ov]
            if name in name_to_id:
                return name_to_id[name]
            ids = norm_to_ids.get(self._norm_name(name))
            if ids and len(ids) == 1:
                return next(iter(ids))
            return None

        added = updated = refreshed = backfilled = removed = 0
        unmatched = []
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                # 1) распространить переименования на смены, уже привязанные по id
                for i, n in pairs:
                    cur.execute(
                        'UPDATE shifts SET employee_name = ? '
                        'WHERE employee_id = ? AND employee_name <> ?', (n, i, n))
                    refreshed += cur.rowcount
                # 2) бэкофилл employee_id у смен без него (+ канонизация имени)
                rows = cur.execute(
                    'SELECT employee_name, COUNT(*) c FROM shifts '
                    'WHERE employee_id IS NULL GROUP BY employee_name').fetchall()
                for r in rows:
                    nm, c = r['employee_name'], r['c']
                    eid = resolve(nm)
                    if eid and eid in id_to_name:
                        cur.execute(
                            'UPDATE shifts SET employee_id = ?, employee_name = ? '
                            'WHERE employee_name = ? AND employee_id IS NULL',
                            (eid, id_to_name[eid], nm))
                        backfilled += cur.rowcount
                    else:
                        unmatched.append({'name': nm, 'shifts': c})
                # 3) upsert реестра по id. Новых людей без смен добавляем неактивными
                #    (видны в админке, скрыты из кисти — владелец включает барменов);
                #    у кого есть смены — активными. Legacy-строку с тем же именем
                #    усыновляем (даём id), сохраняя метку/порядок/активность владельца.
                for i, n in pairs:
                    row = cur.execute(
                        'SELECT name FROM schedule_employees WHERE iiko_id = ?', (i,)).fetchone()
                    if row:
                        if row['name'] != n:
                            cur.execute(
                                'UPDATE schedule_employees SET name = ? WHERE iiko_id = ?', (n, i))
                            updated += 1
                        continue
                    legacy = cur.execute(
                        'SELECT 1 FROM schedule_employees WHERE name = ? AND iiko_id IS NULL',
                        (n,)).fetchone()
                    if legacy:
                        cur.execute(
                            'UPDATE schedule_employees SET iiko_id = ? WHERE name = ?', (i, n))
                        updated += 1
                    else:
                        has_shifts = cur.execute(
                            'SELECT 1 FROM shifts WHERE employee_id = ? LIMIT 1', (i,)).fetchone()
                        cur.execute(
                            'INSERT OR IGNORE INTO schedule_employees (name, iiko_id, active) '
                            'VALUES (?, ?, ?)', (n, i, 1 if has_shifts else 0))
                        added += cur.rowcount
                # 4) убрать осиротевшие legacy-строки реестра (без id и без смен по имени)
                cur.execute(
                    'DELETE FROM schedule_employees WHERE iiko_id IS NULL '
                    'AND name NOT IN (SELECT DISTINCT employee_name FROM shifts '
                    '                 WHERE employee_id IS NULL)')
                removed = cur.rowcount
                conn.commit()
        return {'added': added, 'updated': updated, 'names_refreshed': refreshed,
                'shifts_backfilled': backfilled, 'legacy_removed': removed,
                'unmatched': unmatched}

    def update_schedule_employee(self, iiko_id: str, short_label: str = None,
                                 active: int = None, sort_order: int = None) -> bool:
        """Обновить параметры сотрудника в реестре по стабильному iiko_id (v6)."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                updates, params = [], []
                if short_label is not None:
                    updates.append('short_label = ?')
                    params.append(short_label.strip() or None)
                if active is not None:
                    updates.append('active = ?')
                    params.append(1 if active else 0)
                if sort_order is not None:
                    updates.append('sort_order = ?')
                    params.append(int(sort_order))
                if not updates:
                    return False
                params.append(iiko_id)
                cursor.execute(
                    f'UPDATE schedule_employees SET {", ".join(updates)} WHERE iiko_id = ?',
                    params)
                conn.commit()
                return cursor.rowcount > 0

    # ==================== AUDIT (журнал изменений графика) ====================

    def log_audit(self, action: str, summary: str, actor_login: str = None,
                  actor_name: str = None, entity_date: str = None,
                  employee_name: str = None) -> int:
        """Записать действие в журнал изменений графика (append-only).

        action — машинный код (shift_create / shift_update / shift_delete /
        fact_set / fact_clear / dayoff_create / dayoff_delete / role_rate /
        revenue_set / revenue_sync / revenue_sync_month / employee_update /
        employees_sync). summary — готовая русская строка для показа. Изменения без
        собственной даты (ставка, реестр) логируются с entity_date = сегодня, чтобы
        попасть в историю текущего месяца. actor_name — снимок display_name автора
        (журнал читается, даже если аккаунт потом переименуют/удалят).
        entity_date — дата, к которой относится изменение (фильтр истории по
        месяцу). ts — локальное серверное время, как created_at/updated_at в
        остальных таблицах (не UTC-дефолт SQLite).
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO schedule_audit
                        (ts, actor_login, actor_name, action, entity_date, employee_name, summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (datetime.now().isoformat(), actor_login, actor_name, action,
                      entity_date, employee_name, summary))
                conn.commit()
                return cursor.lastrowid

    def get_audit(self, year: int = None, month: int = None,
                  limit: int = 200) -> List[Dict]:
        """Журнал изменений, новые сверху. Если задан год+месяц — только записи
        того месяца (по entity_date); иначе последние `limit` записей.

        Порядок по id DESC (монотонен вставке) — стабилен при равных ts.
        """
        limit = max(1, min(int(limit), 1000))
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if year and month:
                    prefix = f"{year}-{int(month):02d}-%"
                    cursor.execute('''
                        SELECT id, ts, actor_login, actor_name, action,
                               entity_date, employee_name, summary
                        FROM schedule_audit
                        WHERE entity_date LIKE ?
                        ORDER BY id DESC
                        LIMIT ?
                    ''', (prefix, limit))
                else:
                    cursor.execute('''
                        SELECT id, ts, actor_login, actor_name, action,
                               entity_date, employee_name, summary
                        FROM schedule_audit
                        ORDER BY id DESC
                        LIMIT ?
                    ''', (limit,))
                return [dict(row) for row in cursor.fetchall()]


# Singleton instance
_shifts_manager = None


def get_shifts_manager() -> ShiftsManager:
    """Получить singleton экземпляр ShiftsManager."""
    global _shifts_manager
    if _shifts_manager is None:
        _shifts_manager = ShiftsManager()
    return _shifts_manager
