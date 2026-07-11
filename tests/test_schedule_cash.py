"""
Тесты кассы на смене (схема v7 shifts.db).

Касса — ручной ввод бармена в конце смены (без iiko): траты из кассы,
инкассация, наличные на конец смены, заметка «на что». Деньги в КОПЕЙКАХ
(INTEGER). Критичное: миграция v6 -> v7 аддитивна и сохраняет данные.
"""

import sqlite3

from core.shifts_manager import ShiftsManager


def _mgr(tmp_path):
    return ShiftsManager(db_path=str(tmp_path / 'shifts.db'))


def _make_shift(mgr):
    """Создать смену на сидовой точке/роли и вернуть её id."""
    loc = mgr.get_locations()[0]
    role = mgr.get_roles()[0]
    return mgr.create_shift('2026-07-05', 'Тестов Тест', loc['id'], role['id'])


# ==================== Схема ====================

def test_fresh_db_has_cash_columns(tmp_path):
    mgr = _mgr(tmp_path)
    with sqlite3.connect(mgr.db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(shifts)")}
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    for c in ('cash_expense_kop', 'cash_expense_note',
              'cash_collection_kop', 'cash_end_kop'):
        assert c in cols, f"нет колонки {c}"


def test_v6_migration_preserves_data_and_adds_cash(tmp_path):
    """БД схемы v6 со сменой -> после открытия менеджером колонки кассы есть,
    смена цела, касса пустая (NULL)."""
    db = str(tmp_path / 'shifts.db')
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE locations (id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, short_name TEXT NOT NULL, venue_key TEXT)''')
    cur.execute('''CREATE TABLE roles (id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, short_name TEXT, color TEXT,
        sort_order INTEGER DEFAULT 0, rate_per_hour REAL NOT NULL DEFAULT 300)''')
    cur.execute('''CREATE TABLE shifts (id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL, employee_name TEXT NOT NULL, location_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL, notes TEXT, start_time TEXT, fact_minutes INTEGER,
        employee_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute("INSERT INTO locations (name, short_name, venue_key) "
                "VALUES ('Варшавская', 'Варш', 'varshavskaya')")
    cur.execute("INSERT INTO roles (name, short_name, color, sort_order) "
                "VALUES ('бармен', 'Б', '#4CAF50', 1)")
    cur.execute("INSERT INTO shifts (date, employee_name, location_id, role_id, fact_minutes) "
                "VALUES ('2026-06-05', 'Старый Сотрудник', 1, 1, 600)")
    cur.execute("PRAGMA user_version = 6")
    conn.commit()
    conn.close()

    mgr = ShiftsManager(db_path=db)  # триггерит миграцию v6 -> v7

    shifts = mgr.get_shifts_for_month(2026, 6)
    assert len(shifts) == 1
    s = shifts[0]
    assert s['employee_name'] == 'Старый Сотрудник'
    assert s['fact_minutes'] == 600           # данные целы
    assert s['cash_end_kop'] is None          # касса пустая после миграции
    assert s['cash_expense_kop'] is None


# ==================== set_shift_cash ====================

def test_set_and_read_cash(tmp_path):
    mgr = _mgr(tmp_path)
    sid = _make_shift(mgr)
    # траты 350.50 ₽ = 35050 коп, инкассация 20000 ₽, касса на конец 15340.25 ₽
    assert mgr.set_shift_cash(sid, 35050, 2000000, 1534025, 'закупка льда')

    s = mgr.get_shift(sid)
    assert s['cash_expense_kop'] == 35050
    assert s['cash_expense_note'] == 'закупка льда'
    assert s['cash_collection_kop'] == 2000000
    assert s['cash_end_kop'] == 1534025


def test_zero_means_none_happened(tmp_path):
    """0 (трат не было) отличается от NULL (не заполнено)."""
    mgr = _mgr(tmp_path)
    sid = _make_shift(mgr)
    mgr.set_shift_cash(sid, 0, 0, 1200000)
    s = mgr.get_shift(sid)
    assert s['cash_expense_kop'] == 0
    assert s['cash_collection_kop'] == 0
    assert s['cash_end_kop'] == 1200000


def test_clear_cash(tmp_path):
    mgr = _mgr(tmp_path)
    sid = _make_shift(mgr)
    mgr.set_shift_cash(sid, 35050, 0, 1534025, 'лёд')
    mgr.set_shift_cash(sid, None, None, None, None)  # очистка
    s = mgr.get_shift(sid)
    assert s['cash_expense_kop'] is None
    assert s['cash_expense_note'] is None
    assert s['cash_collection_kop'] is None
    assert s['cash_end_kop'] is None


def test_empty_note_normalized_to_none(tmp_path):
    mgr = _mgr(tmp_path)
    sid = _make_shift(mgr)
    mgr.set_shift_cash(sid, 100, 0, 500, '   ')  # пробелы -> None
    assert mgr.get_shift(sid)['cash_expense_note'] is None


def test_set_cash_unknown_shift(tmp_path):
    mgr = _mgr(tmp_path)
    assert mgr.set_shift_cash(999999, 100, 0, 500) is False


def test_cash_independent_from_fact(tmp_path):
    """Очистка часов не трогает кассу и наоборот."""
    mgr = _mgr(tmp_path)
    sid = _make_shift(mgr)
    mgr.set_shift_fact(sid, 600)
    mgr.set_shift_cash(sid, 0, 0, 900000)
    mgr.set_shift_fact(sid, None)              # чистим часы
    s = mgr.get_shift(sid)
    assert s['fact_minutes'] is None
    assert s['cash_end_kop'] == 900000         # касса цела
