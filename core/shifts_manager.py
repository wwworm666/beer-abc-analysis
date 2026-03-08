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


class ShiftsManager:
    """Thread-safe менеджер для работы со сменами в SQLite."""

    # Версия схемы — при увеличении старая БД пересоздаётся
    SCHEMA_VERSION = 2

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
        """Context manager для подключения к БД."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_database(self):
        """Создать таблицы, если не существуют."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Проверяем версию схемы
                cursor.execute("PRAGMA user_version")
                current_version = cursor.fetchone()[0]

                if current_version < self.SCHEMA_VERSION:
                    # Пересоздаём все таблицы
                    cursor.execute('DROP TABLE IF EXISTS shifts')
                    cursor.execute('DROP TABLE IF EXISTS day_off_requests')
                    cursor.execute('DROP TABLE IF EXISTS daily_revenue')
                    cursor.execute('DROP TABLE IF EXISTS employees')  # старая таблица
                    cursor.execute('DROP TABLE IF EXISTS locations')
                    cursor.execute('DROP TABLE IF EXISTS roles')
                    print(f"[ShiftsManager] Миграция схемы v{current_version} -> v{self.SCHEMA_VERSION}")

                # Точки (бары)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS locations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        short_name TEXT NOT NULL
                    )
                ''')

                # Роли
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS roles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        short_name TEXT,
                        color TEXT,
                        sort_order INTEGER DEFAULT 0
                    )
                ''')

                # Смены — employee_name хранится напрямую (из iiko API)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS shifts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        employee_name TEXT NOT NULL,
                        location_id INTEGER NOT NULL,
                        role_id INTEGER NOT NULL,
                        notes TEXT,
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

                # Индексы
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_shifts_date ON shifts(date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_shifts_employee ON shifts(employee_name)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_shifts_location ON shifts(location_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_dayoff_employee ON day_off_requests(employee_name)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_dayoff_dates ON day_off_requests(date_from, date_to)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_revenue_date ON daily_revenue(date)')

                cursor.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
                conn.commit()

                # Seed-данные
                self._seed_data(cursor, conn)

    def _seed_data(self, cursor, conn):
        """Начальные данные: точки и роли."""
        cursor.execute('SELECT COUNT(*) FROM locations')
        if cursor.fetchone()[0] == 0:
            locations = [
                ('Варшавская', 'Вар'),
                ('Большой пр. В.О', 'ВО'),
                ('Кременчугская', 'Кр'),
                ('Лиговский', 'Лиг'),
            ]
            cursor.executemany(
                'INSERT INTO locations (name, short_name) VALUES (?, ?)',
                locations
            )
            print(f"[ShiftsManager] Добавлено {len(locations)} точек")

        cursor.execute('SELECT COUNT(*) FROM roles')
        if cursor.fetchone()[0] == 0:
            roles = [
                ('бармен', 'Б', '#4CAF50', 1),
                ('второй бармен', '2Б', '#2196F3', 2),
                ('стажёр', 'Ст', '#FF9800', 3),
            ]
            cursor.executemany(
                'INSERT INTO roles (name, short_name, color, sort_order) VALUES (?, ?, ?, ?)',
                roles
            )
            print(f"[ShiftsManager] Добавлено {len(roles)} ролей")

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
        """Получить список ролей."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM roles ORDER BY sort_order')
                return [dict(row) for row in cursor.fetchall()]

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
                        s.id, s.date, s.employee_name, s.notes,
                        l.id as location_id, l.name as location_name, l.short_name as location_short,
                        r.id as role_id, r.name as role_name, r.short_name as role_short, r.color as role_color
                    FROM shifts s
                    JOIN locations l ON s.location_id = l.id
                    JOIN roles r ON s.role_id = r.id
                    WHERE s.date >= ? AND s.date <= ?
                    ORDER BY s.date, l.id, r.sort_order
                ''', (first_day.isoformat(), last_day.isoformat()))
                return [dict(row) for row in cursor.fetchall()]

    def create_shift(self, date_str: str, employee_name: str, location_id: int,
                     role_id: int, notes: str = None) -> int:
        """Создать смену. Возвращает ID."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO shifts (date, employee_name, location_id, role_id, notes)
                    VALUES (?, ?, ?, ?, ?)
                ''', (date_str, employee_name, location_id, role_id, notes))
                conn.commit()
                return cursor.lastrowid

    def update_shift(self, shift_id: int, **kwargs) -> bool:
        """Обновить смену."""
        allowed = {'date', 'employee_name', 'location_id', 'role_id', 'notes'}
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

    def update_revenue(self, date_str: str, location_id: int,
                       plan_revenue: float = None, fact_revenue: float = None) -> bool:
        """Обновить или создать запись о выручке."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    'SELECT id FROM daily_revenue WHERE date = ? AND location_id = ?',
                    (date_str, location_id)
                )
                existing = cursor.fetchone()

                if existing:
                    updates = []
                    params = []
                    if plan_revenue is not None:
                        updates.append('plan_revenue = ?')
                        params.append(plan_revenue)
                    if fact_revenue is not None:
                        updates.append('fact_revenue = ?')
                        params.append(fact_revenue)

                    if updates:
                        updates.append('updated_at = ?')
                        params.append(datetime.now().isoformat())
                        params.append(existing['id'])
                        cursor.execute(
                            f'UPDATE daily_revenue SET {", ".join(updates)} WHERE id = ?',
                            params
                        )
                else:
                    cursor.execute('''
                        INSERT INTO daily_revenue (date, location_id, plan_revenue, fact_revenue)
                        VALUES (?, ?, ?, ?)
                    ''', (date_str, location_id, plan_revenue or 0, fact_revenue))

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


# Singleton instance
_shifts_manager = None


def get_shifts_manager() -> ShiftsManager:
    """Получить singleton экземпляр ShiftsManager."""
    global _shifts_manager
    if _shifts_manager is None:
        _shifts_manager = ShiftsManager()
    return _shifts_manager
