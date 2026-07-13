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


def test_latest_cash_by_location(tmp_path):
    """Последняя сданная касса по точке: свежая дата побеждает, смена без кассы
    не перебивает, точка без кассы отсутствует."""
    mgr = _mgr(tmp_path)
    locs = mgr.get_locations()
    role = mgr.get_roles()[0]['id']
    l0, l1, l2 = locs[0]['id'], locs[1]['id'], locs[2]['id']
    s_old = mgr.create_shift('2026-07-01', 'A', l0, role)
    mgr.set_shift_cash(s_old, 0, 0, 1000000)          # 10 000, старая
    s_new = mgr.create_shift('2026-07-05', 'A', l0, role)
    mgr.set_shift_cash(s_new, 0, 0, 1500000)          # 15 000, свежая
    s1 = mgr.create_shift('2026-07-03', 'B', l1, role)
    mgr.set_shift_cash(s1, 0, 0, 300000)              # 3 000
    mgr.create_shift('2026-07-06', 'C', l1, role)      # без кассы — не перебивает

    latest = mgr.get_latest_cash_by_location()
    assert latest[l0]['cash_end_kop'] == 1500000
    assert latest[l0]['date'] == '2026-07-05'
    assert latest[l1]['cash_end_kop'] == 300000
    assert l2 not in latest                            # нет ни одной сданной кассы


def test_collectable_math():
    """Инкассируем сверх размена, округляя вниз до 1000 ₽ (остаток в баре)."""
    from core.open_check_telegram import (
        collectable_kop, CASH_CHANGE_FLOAT_RUB, INCASS_STEP_RUB)
    assert CASH_CHANGE_FLOAT_RUB == 5000
    assert INCASS_STEP_RUB == 1000
    f = 5000 * 100
    assert collectable_kop(1500000, f) == 1000000     # 15000 -> 10000
    assert collectable_kop(1534050, f) == 1000000     # 15340.50 -> сверх 10340.50 -> 10000
    assert collectable_kop(300000, f) == 0            # ниже размена
    assert collectable_kop(500000, f) == 0            # ровно размен
    assert collectable_kop(500100, f) == 0            # +1 ₽ — меньше шага, не берём
    assert collectable_kop(600000, f) == 100000       # сверх 1000 -> 1000
    assert collectable_kop(659900, f) == 100000       # сверх 1599 -> 1000 (599 в баре)


def test_cash_edit_lock_window():
    """Касса замораживается через 72 ч от даты смены (окно правок)."""
    from datetime import datetime, timedelta
    from routes.schedule import _cash_edit_locked, CASH_EDIT_WINDOW_HOURS
    assert CASH_EDIT_WINDOW_HOURS == 72
    today = datetime.now()
    fmt = lambda d: d.strftime('%Y-%m-%d')
    assert _cash_edit_locked(fmt(today)) is False              # сегодня — открыто
    assert _cash_edit_locked(fmt(today - timedelta(days=2))) is False   # в окне
    assert _cash_edit_locked(fmt(today - timedelta(days=4))) is True    # вышло из окна
    assert _cash_edit_locked(fmt(today - timedelta(days=30))) is True
    assert _cash_edit_locked('bad-date') is False              # мусор — не блокируем


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
