"""
Менеджер смен для системы управления графиком.
Использует SQLite для хранения данных.
"""

import sqlite3
import threading
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager


class ShiftsManager:
    """Thread-safe менеджер для работы со сменами в SQLite."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or self._get_default_path()
        self._lock = threading.Lock()
        self._init_database()

    def _get_default_path(self) -> str:
        """Определить путь к БД: Render disk или локальная папка."""
        if os.path.exists('/kultura'):
            return '/kultura/shifts.db'
        # Локальный путь
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

                # Сотрудники
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS employees (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        short_name TEXT,
                        default_role TEXT DEFAULT 'бармен',
                        is_active INTEGER DEFAULT 1,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

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

                # Смены
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS shifts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        employee_id INTEGER NOT NULL,
                        location_id INTEGER NOT NULL,
                        role_id INTEGER NOT NULL,
                        planned_hours REAL DEFAULT 0,
                        actual_hours REAL,
                        notes TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (employee_id) REFERENCES employees(id),
                        FOREIGN KEY (location_id) REFERENCES locations(id),
                        FOREIGN KEY (role_id) REFERENCES roles(id)
                    )
                ''')

                # Пожелания выходных
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS day_off_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        employee_id INTEGER NOT NULL,
                        date_from TEXT NOT NULL,
                        date_to TEXT NOT NULL,
                        reason TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (employee_id) REFERENCES employees(id)
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

                # Индексы
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_shifts_date ON shifts(date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_shifts_employee ON shifts(employee_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_shifts_location ON shifts(location_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_dayoff_employee ON day_off_requests(employee_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_dayoff_dates ON day_off_requests(date_from, date_to)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_revenue_date ON daily_revenue(date)')

                conn.commit()

                # Инициализация справочных данных
                self._seed_data(cursor, conn)

    def _seed_data(self, cursor, conn):
        """Начальные данные: точки и роли."""
        # Проверяем, есть ли данные
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

    # ==================== EMPLOYEES ====================

    def get_employees(self, active_only: bool = True) -> List[Dict]:
        """Получить список сотрудников."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if active_only:
                    cursor.execute('SELECT * FROM employees WHERE is_active = 1 ORDER BY name')
                else:
                    cursor.execute('SELECT * FROM employees ORDER BY name')
                return [dict(row) for row in cursor.fetchall()]

    def get_employee(self, employee_id: int) -> Optional[Dict]:
        """Получить сотрудника по ID."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
                row = cursor.fetchone()
                return dict(row) if row else None

    def create_employee(self, name: str, short_name: str = None, default_role: str = 'бармен') -> int:
        """Создать сотрудника. Возвращает ID."""
        if not short_name:
            # Генерируем инициалы: "Иванов Иван" -> "ИИ"
            parts = name.split()
            short_name = ''.join(p[0].upper() for p in parts[:2]) if len(parts) >= 2 else name[:2].upper()

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO employees (name, short_name, default_role) VALUES (?, ?, ?)',
                    (name, short_name, default_role)
                )
                conn.commit()
                return cursor.lastrowid

    def update_employee(self, employee_id: int, **kwargs) -> bool:
        """Обновить сотрудника."""
        allowed = {'name', 'short_name', 'default_role', 'is_active'}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False

        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values()) + [employee_id]

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f'UPDATE employees SET {set_clause} WHERE id = ?', values)
                conn.commit()
                return cursor.rowcount > 0

    def delete_employee(self, employee_id: int) -> bool:
        """Мягкое удаление сотрудника (деактивация)."""
        return self.update_employee(employee_id, is_active=0)

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
        """Получить все смены за месяц с данными о сотрудниках и точках."""
        # Определяем диапазон дат
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
                        s.id, s.date, s.planned_hours, s.actual_hours, s.notes,
                        e.id as employee_id, e.name as employee_name, e.short_name as employee_short,
                        l.id as location_id, l.name as location_name, l.short_name as location_short,
                        r.id as role_id, r.name as role_name, r.short_name as role_short, r.color as role_color
                    FROM shifts s
                    JOIN employees e ON s.employee_id = e.id
                    JOIN locations l ON s.location_id = l.id
                    JOIN roles r ON s.role_id = r.id
                    WHERE s.date >= ? AND s.date <= ?
                    ORDER BY s.date, l.id, r.sort_order
                ''', (first_day.isoformat(), last_day.isoformat()))
                return [dict(row) for row in cursor.fetchall()]

    def get_shift(self, shift_id: int) -> Optional[Dict]:
        """Получить смену по ID."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT
                        s.*,
                        e.name as employee_name,
                        l.name as location_name,
                        r.name as role_name
                    FROM shifts s
                    JOIN employees e ON s.employee_id = e.id
                    JOIN locations l ON s.location_id = l.id
                    JOIN roles r ON s.role_id = r.id
                    WHERE s.id = ?
                ''', (shift_id,))
                row = cursor.fetchone()
                return dict(row) if row else None

    def create_shift(self, date_str: str, employee_id: int, location_id: int,
                     role_id: int, planned_hours: float = 0, notes: str = None) -> int:
        """Создать смену. Возвращает ID."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO shifts (date, employee_id, location_id, role_id, planned_hours, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (date_str, employee_id, location_id, role_id, planned_hours, notes))
                conn.commit()
                return cursor.lastrowid

    def update_shift(self, shift_id: int, **kwargs) -> bool:
        """Обновить смену."""
        allowed = {'date', 'employee_id', 'location_id', 'role_id', 'planned_hours', 'actual_hours', 'notes'}
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

    def get_day_off_requests(self, employee_id: int = None,
                              date_from: str = None, date_to: str = None) -> List[Dict]:
        """Получить пожелания выходных с фильтрацией."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = '''
                    SELECT d.*, e.name as employee_name
                    FROM day_off_requests d
                    JOIN employees e ON d.employee_id = e.id
                    WHERE 1=1
                '''
                params = []

                if employee_id:
                    query += ' AND d.employee_id = ?'
                    params.append(employee_id)

                if date_from:
                    query += ' AND d.date_to >= ?'
                    params.append(date_from)

                if date_to:
                    query += ' AND d.date_from <= ?'
                    params.append(date_to)

                query += ' ORDER BY d.date_from'
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]

    def check_day_off_conflict(self, employee_id: int, check_date: str) -> bool:
        """Проверить, есть ли пожелание выходного на эту дату."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM day_off_requests
                    WHERE employee_id = ? AND date_from <= ? AND date_to >= ?
                ''', (employee_id, check_date, check_date))
                return cursor.fetchone()[0] > 0

    def create_day_off_request(self, employee_id: int, date_from: str,
                                date_to: str, reason: str = None) -> int:
        """Создать пожелание выходного."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO day_off_requests (employee_id, date_from, date_to, reason)
                    VALUES (?, ?, ?, ?)
                ''', (employee_id, date_from, date_to, reason))
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
        """Получить выручку за месяц."""
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT r.*, l.name as location_name
                    FROM daily_revenue r
                    JOIN locations l ON r.location_id = l.id
                    WHERE r.date >= ? AND r.date <= ?
                    ORDER BY r.date, l.id
                ''', (first_day.isoformat(), last_day.isoformat()))
                return [dict(row) for row in cursor.fetchall()]

    def update_revenue(self, date_str: str, location_id: int,
                       plan_revenue: float = None, fact_revenue: float = None) -> bool:
        """Обновить или создать запись о выручке."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Проверяем существование записи
                cursor.execute(
                    'SELECT id FROM daily_revenue WHERE date = ? AND location_id = ?',
                    (date_str, location_id)
                )
                existing = cursor.fetchone()

                if existing:
                    # Обновляем
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
                    # Создаём
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


# Singleton instance
_shifts_manager = None


def get_shifts_manager() -> ShiftsManager:
    """Получить singleton экземпляр ShiftsManager."""
    global _shifts_manager
    if _shifts_manager is None:
        _shifts_manager = ShiftsManager()
    return _shifts_manager
