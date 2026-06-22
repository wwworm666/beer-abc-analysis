"""
Менеджер пользователей для авторизации.

Личный аккаунт на каждого (бармен/владелец), вход по логину и паролю.
Пароли хранятся только как хэш (werkzeug). Данные — отдельная SQLite-база
auth.db на persistent-томе (/kultura на проде), чтобы аккаунты переживали
редеплой (код запекается в образ, БД — на томе).

Связь с графиком смен: display_name совпадает с именем в реестре
schedule_employees -> «кто менял смену» подставляется из залогиненного юзера.
"""

import os
import re
import sqlite3
import threading
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import contextmanager

from werkzeug.security import generate_password_hash, check_password_hash


# Минимальная длина пароля. Команда маленькая и доверенная (решение владельца — 4).
# Единственное место правила. Вход длину не проверяет — менять порог безопасно.
MIN_PASSWORD_LEN = 4

# Макс. длина сокращения (типа «АН»). Вводится ВРУЧНУЮ, без авто-генерации.
SHORT_LABEL_MAXLEN = 12

# Логин: латиница/цифры/._- , 2..32 символа. Регистр не важен (COLLATE NOCASE).
LOGIN_RE = re.compile(r'^[A-Za-z0-9_.\-]{2,32}$')


class AuthManager:
    """Thread-safe менеджер пользователей в SQLite.

    Схема additive (как в ShiftsManager): миграции только ALTER TABLE ADD COLUMN,
    DROP запрещён — в проде живые аккаунты.
    """

    SCHEMA_VERSION = 2

    def __init__(self, db_path: str = None):
        self.db_path = db_path or self._get_default_path()
        self._lock = threading.Lock()
        self._init_database()

    def _get_default_path(self) -> str:
        if os.path.isdir('/kultura'):
            return '/kultura/auth.db'
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, 'auth.db')

    @contextmanager
    def _get_connection(self):
        """WAL + busy_timeout: под gunicorn 2 воркера могут писать одновременно."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write_txn(self):
        """Соединение с НЕМЕДЛЕННЫМ write-локом (BEGIN IMMEDIATE) на весь блок.

        Нужен для инвариантов вида check-then-act («последний админ», «первый
        владелец»): threading.Lock сериализует только внутри процесса, а в проде
        gunicorn 2 воркера = 2 процесса. BEGIN IMMEDIATE берёт write-лок БД сразу,
        второй воркер ждёт на busy_timeout — проверка и запись атомарны меж-процессно.
        autocommit (isolation_level=None) — транзакцией управляем сами.
        """
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10,
                               isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    def _init_database(self):
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        login         TEXT NOT NULL UNIQUE COLLATE NOCASE,
                        display_name  TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        is_admin      INTEGER NOT NULL DEFAULT 0,
                        active        INTEGER NOT NULL DEFAULT 1,
                        created_at    TEXT NOT NULL,
                        last_login_at TEXT
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_login ON users(login)")
                # Additive-миграция: сокращение (АН). На уже существующих БД (прод)
                # таблица создана без колонки — добавляем через ALTER, данные не трогаем.
                cur.execute("PRAGMA table_info(users)")
                cols = {r[1] for r in cur.fetchall()}
                if 'short_label' not in cols:
                    cur.execute("ALTER TABLE users ADD COLUMN short_label TEXT NOT NULL DEFAULT ''")
                cur.execute(f"PRAGMA user_version={self.SCHEMA_VERSION}")
                conn.commit()
        # Опциональный bootstrap из окружения (для автоматизированного деплоя).
        # При отсутствии env первый владелец создаётся через first-run setup на /login.
        self._bootstrap_from_env()

    def _bootstrap_from_env(self):
        login = os.getenv('AUTH_BOOTSTRAP_LOGIN')
        password = os.getenv('AUTH_BOOTSTRAP_PASSWORD')
        if not login or not password:
            return
        if self.count_users() > 0:
            return
        try:
            self.create_user(
                login=login,
                display_name=os.getenv('AUTH_BOOTSTRAP_NAME', login),
                password=password,
                is_admin=True,
            )
            print(f"[AuthManager] Bootstrap: создан владелец '{login}' из переменных окружения")
        except Exception as e:
            print(f"[AuthManager WARNING] Bootstrap не удался: {e}")

    # --- helpers ---

    @staticmethod
    def _row_to_public(row) -> Dict:
        """Строка БД -> публичный словарь (без password_hash)."""
        keys = row.keys()
        return {
            'id': row['id'],
            'login': row['login'],
            'display_name': row['display_name'],
            'short_label': row['short_label'] if 'short_label' in keys else '',
            'is_admin': bool(row['is_admin']),
            'active': bool(row['active']),
            'created_at': row['created_at'],
            'last_login_at': row['last_login_at'],
        }

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec='seconds')

    # --- queries ---

    def count_users(self) -> int:
        with self._get_connection() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()['n']

    def count_admins(self, active_only: bool = True) -> int:
        sql = "SELECT COUNT(*) AS n FROM users WHERE is_admin=1"
        if active_only:
            sql += " AND active=1"
        with self._get_connection() as conn:
            return conn.execute(sql).fetchone()['n']

    def list_users(self) -> List[Dict]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY is_admin DESC, login COLLATE NOCASE"
            ).fetchall()
            return [self._row_to_public(r) for r in rows]

    def get_by_id(self, user_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            return self._row_to_public(row) if row else None

    def get_by_login(self, login: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE login=? COLLATE NOCASE", (login,)
            ).fetchone()
            return self._row_to_public(row) if row else None

    # --- mutations ---

    @staticmethod
    def _normalize_new(login: str, display_name: str, password: str, short_label: str = ''):
        """Проверить и нормализовать данные нового аккаунта.
        Возвращает (login, display_name, password_hash, short_label) или бросает ValueError.
        short_label («АН») — ВРУЧНУЮ, без авто-генерации из имени."""
        login = (login or '').strip()
        display_name = (display_name or '').strip() or login
        short_label = (short_label or '').strip()[:SHORT_LABEL_MAXLEN]
        if not LOGIN_RE.match(login):
            raise ValueError('Логин: 2-32 символа, латиница/цифры/._-')
        if not password or len(password) < MIN_PASSWORD_LEN:
            raise ValueError(f'Пароль не короче {MIN_PASSWORD_LEN} символов')
        return login, display_name, generate_password_hash(password), short_label

    def create_user(self, login: str, display_name: str, password: str,
                    is_admin: bool = False, short_label: str = '') -> int:
        login, display_name, pwd_hash, short_label = self._normalize_new(
            login, display_name, password, short_label)
        with self._lock:
            with self._get_connection() as conn:
                try:
                    cur = conn.execute(
                        """INSERT INTO users (login, display_name, short_label,
                                              password_hash, is_admin, active, created_at)
                           VALUES (?, ?, ?, ?, ?, 1, ?)""",
                        (login, display_name, short_label, pwd_hash,
                         1 if is_admin else 0, self._now()),
                    )
                    conn.commit()
                    return cur.lastrowid
                except sqlite3.IntegrityError:
                    raise ValueError('Логин уже занят')

    def create_first_owner(self, login: str, display_name: str, password: str,
                           short_label: str = '') -> int:
        """Создать первого владельца (admin) — только пока в системе НЕТ аккаунтов.

        Проверка «нет аккаунтов» и INSERT — в одной транзакции под write-локом
        (BEGIN IMMEDIATE), иначе два одновременных POST /setup с разными логинами
        создали бы двух владельцев (cross-process гонка first-run)."""
        login, display_name, pwd_hash, short_label = self._normalize_new(
            login, display_name, password, short_label)
        with self._lock:
            with self._write_txn() as conn:
                n = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()['n']
                if n > 0:
                    raise ValueError('Аккаунты уже существуют')
                try:
                    cur = conn.execute(
                        """INSERT INTO users (login, display_name, short_label,
                                              password_hash, is_admin, active, created_at)
                           VALUES (?, ?, ?, ?, 1, 1, ?)""",
                        (login, display_name, short_label, pwd_hash, self._now()),
                    )
                    return cur.lastrowid
                except sqlite3.IntegrityError:
                    raise ValueError('Логин уже занят')

    def update_profile(self, user_id: int, display_name: str = None,
                       short_label: str = None):
        """Изменить имя и/или сокращение аккаунта. Сокращение — вручную.
        Передавай только те поля, что меняешь (None = не трогать)."""
        sets, params = [], []
        if display_name is not None:
            dn = display_name.strip()
            if not dn:
                raise ValueError('Имя не может быть пустым')
            sets.append('display_name=?')
            params.append(dn)
        if short_label is not None:
            sets.append('short_label=?')
            params.append(short_label.strip()[:SHORT_LABEL_MAXLEN])
        if not sets:
            return
        params.append(user_id)
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", params)
                conn.commit()

    def verify_credentials(self, login: str, password: str) -> Optional[Dict]:
        """Проверить логин+пароль. Возвращает публичный словарь юзера или None.

        Возвращает None для несуществующего, неактивного или с неверным паролем.
        check_password_hash вызывается всегда, когда юзер найден, — но для ровного
        времени ответа отдельную «фиктивную» проверку не делаем (приложение
        внутреннее, без публичного перебора)."""
        if not login or not password:
            return None
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE login=? COLLATE NOCASE", (login,)
            ).fetchone()
            if row is None or not row['active']:
                return None
            if not check_password_hash(row['password_hash'], password):
                return None
            conn.execute("UPDATE users SET last_login_at=? WHERE id=?",
                         (self._now(), row['id']))
            conn.commit()
            return self._row_to_public(row)

    def set_password(self, user_id: int, new_password: str):
        if not new_password or len(new_password) < MIN_PASSWORD_LEN:
            raise ValueError(f'Пароль не короче {MIN_PASSWORD_LEN} символов')
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                             (generate_password_hash(new_password), user_id))
                conn.commit()

    @staticmethod
    def _active_admins(conn) -> int:
        """Число активных админов В ТЕКУЩЕЙ транзакции conn (не отдельным соединением)."""
        return conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE is_admin=1 AND active=1"
        ).fetchone()['n']

    def set_active(self, user_id: int, active: bool):
        """Включить/выключить аккаунт. Нельзя выключить последнего активного админа.

        Проверка и UPDATE атомарны под BEGIN IMMEDIATE — иначе два воркера могли бы
        одновременно выключить двух последних админов (cross-process TOCTOU)."""
        with self._lock:
            with self._write_txn() as conn:
                row = conn.execute("SELECT is_admin, active FROM users WHERE id=?",
                                   (user_id,)).fetchone()
                if row is None:
                    raise ValueError('Пользователь не найден')
                if row['is_admin'] and row['active'] and not active:
                    if self._active_admins(conn) <= 1:
                        raise ValueError('Нельзя отключить последнего админа')
                conn.execute("UPDATE users SET active=? WHERE id=?",
                             (1 if active else 0, user_id))

    def set_admin(self, user_id: int, is_admin: bool):
        """Выдать/снять права админа. Нельзя снять с последнего активного админа."""
        with self._lock:
            with self._write_txn() as conn:
                row = conn.execute("SELECT is_admin, active FROM users WHERE id=?",
                                   (user_id,)).fetchone()
                if row is None:
                    raise ValueError('Пользователь не найден')
                if row['is_admin'] and not is_admin and self._active_admins(conn) <= 1:
                    raise ValueError('Нельзя снять права с последнего админа')
                conn.execute("UPDATE users SET is_admin=? WHERE id=?",
                             (1 if is_admin else 0, user_id))

    def delete_user(self, user_id: int):
        """Удалить аккаунт. Нельзя удалить последнего активного админа."""
        with self._lock:
            with self._write_txn() as conn:
                row = conn.execute("SELECT is_admin, active FROM users WHERE id=?",
                                   (user_id,)).fetchone()
                if row is None:
                    return
                if row['is_admin'] and row['active'] and self._active_admins(conn) <= 1:
                    raise ValueError('Нельзя удалить последнего админа')
                conn.execute("DELETE FROM users WHERE id=?", (user_id,))


_auth_manager = None
_auth_manager_lock = threading.Lock()


def get_auth_manager() -> AuthManager:
    """Синглтон с ленивой инициализацией (как get_shifts_manager)."""
    global _auth_manager
    if _auth_manager is None:
        with _auth_manager_lock:
            if _auth_manager is None:
                _auth_manager = AuthManager()
    return _auth_manager
