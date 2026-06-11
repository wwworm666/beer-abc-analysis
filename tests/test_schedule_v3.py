"""
Тесты редизайна графика смен (схема v3 shifts.db + core/schedule_plans.py).

Критичное: миграция v2 -> v3 ОБЯЗАНА сохранять данные (прежний код дропал
все таблицы при бампе SCHEMA_VERSION — в проде живые смены).
"""

import os
import sqlite3

import pytest

from core.shifts_manager import ShiftsManager
from core.schedule_plans import (
    build_month_plans,
    compute_month_summary,
    compute_employees_load,
)


# ==================== ShiftsManager: схема и миграция ====================

def _make_v2_db(db_path):
    """Создать БД в схеме v2 (без start_time/fact_minutes/venue_key) с данными."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        short_name TEXT NOT NULL)''')
    cur.execute('''CREATE TABLE roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, short_name TEXT, color TEXT,
        sort_order INTEGER DEFAULT 0)''')
    cur.execute('''CREATE TABLE shifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL, employee_name TEXT NOT NULL,
        location_id INTEGER NOT NULL, role_id INTEGER NOT NULL, notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute('''CREATE TABLE day_off_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_name TEXT NOT NULL, date_from TEXT NOT NULL,
        date_to TEXT NOT NULL, reason TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute('''CREATE TABLE daily_revenue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL, location_id INTEGER NOT NULL,
        plan_revenue REAL DEFAULT 0, fact_revenue REAL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(date, location_id))''')
    cur.execute('''CREATE TABLE wishes (
        employee_name TEXT PRIMARY KEY, text TEXT NOT NULL DEFAULT '',
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

    cur.execute("INSERT INTO locations (name, short_name) VALUES ('Варшавская', 'Вар')")
    cur.execute("INSERT INTO roles (name, short_name, color, sort_order) "
                "VALUES ('бармен', 'Б', '#4CAF50', 1)")
    cur.execute("INSERT INTO shifts (date, employee_name, location_id, role_id) "
                "VALUES ('2026-06-05', 'Тестов Тест', 1, 1)")
    cur.execute("INSERT INTO daily_revenue (date, location_id, plan_revenue, fact_revenue) "
                "VALUES ('2026-06-05', 1, 50000, 48000)")
    cur.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()


def test_fresh_db_creates_v3_schema(tmp_path):
    mgr = ShiftsManager(db_path=str(tmp_path / 'shifts.db'))

    locations = mgr.get_locations()
    assert len(locations) == 4
    # venue_key проставлен всем сидовым точкам
    keys = {loc['name']: loc['venue_key'] for loc in locations}
    assert keys['Варшавская'] == 'varshavskaya'
    assert keys['Большой пр. В.О'] == 'bolshoy'
    assert keys['Кременчугская'] == 'kremenchugskaya'
    assert keys['Лиговский'] == 'ligovskiy'

    # Канонические сокращения владельца: Варш, Крем, ВО, Лиг
    shorts = {loc['name']: loc['short_name'] for loc in locations}
    assert shorts == {'Варшавская': 'Варш', 'Большой пр. В.О': 'ВО',
                      'Кременчугская': 'Крем', 'Лиговский': 'Лиг'}

    conn = sqlite3.connect(mgr.db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == ShiftsManager.SCHEMA_VERSION
    cols = {row[1] for row in conn.execute("PRAGMA table_info(shifts)")}
    assert {'start_time', 'fact_minutes'} <= cols
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'schedule_employees' in tables
    conn.close()


def test_migration_v2_to_v3_preserves_data_and_makes_backup(tmp_path):
    db_path = str(tmp_path / 'shifts.db')
    _make_v2_db(db_path)

    mgr = ShiftsManager(db_path=db_path)

    # Данные v2 живы
    shifts = mgr.get_shifts_for_month(2026, 6)
    assert len(shifts) == 1
    assert shifts[0]['employee_name'] == 'Тестов Тест'
    assert shifts[0]['start_time'] is None
    assert shifts[0]['fact_minutes'] is None

    revenue = mgr.get_revenue_for_month(2026, 6)
    assert revenue[0]['plan_revenue'] == 50000
    assert revenue[0]['fact_revenue'] == 48000

    # venue_key мигрированной точке проставлен, устаревшее сокращение починено
    migrated = mgr.get_locations()[0]
    assert migrated['venue_key'] == 'varshavskaya'
    assert migrated['short_name'] == 'Варш'

    # Бэкап перед миграцией создан и читается
    backup = db_path + '.backup_v2'
    assert os.path.exists(backup)
    bconn = sqlite3.connect(backup)
    assert bconn.execute("SELECT COUNT(*) FROM shifts").fetchone()[0] == 1
    bconn.close()


def test_reopen_same_version_no_new_backup(tmp_path):
    db_path = str(tmp_path / 'shifts.db')
    ShiftsManager(db_path=db_path)
    backups_before = [f for f in os.listdir(tmp_path) if '.backup_' in f]
    ShiftsManager(db_path=db_path)  # повторное открытие той же версии
    backups_after = [f for f in os.listdir(tmp_path) if '.backup_' in f]
    assert backups_before == backups_after


def test_shift_fact_and_start_time(tmp_path):
    mgr = ShiftsManager(db_path=str(tmp_path / 'shifts.db'))
    loc_id = mgr.get_locations()[0]['id']
    role_id = mgr.get_roles()[0]['id']

    shift_id = mgr.create_shift('2026-06-05', 'Тестов Тест', loc_id, role_id,
                                start_time='18:00')
    shift = mgr.get_shifts_for_month(2026, 6)[0]
    assert shift['start_time'] == '18:00'

    assert mgr.set_shift_fact(shift_id, 630)  # 10:30
    assert mgr.get_shifts_for_month(2026, 6)[0]['fact_minutes'] == 630

    assert mgr.set_shift_fact(shift_id, None)  # очистка
    assert mgr.get_shifts_for_month(2026, 6)[0]['fact_minutes'] is None

    assert not mgr.set_shift_fact(99999, 60)  # несуществующая смена


def test_schedule_employees_registry(tmp_path):
    mgr = ShiftsManager(db_path=str(tmp_path / 'shifts.db'))

    added = mgr.upsert_schedule_employees(['Романов Юрий', 'Иванова Елена', ''])
    assert added == 2
    # Повторный upsert ничего не дублирует
    assert mgr.upsert_schedule_employees(['Романов Юрий']) == 0

    mgr.update_schedule_employee('Романов Юрий', short_label='РЮ', sort_order=1)
    mgr.update_schedule_employee('Иванова Елена', active=0)

    active = mgr.get_schedule_employees()
    assert [e['name'] for e in active] == ['Романов Юрий']
    assert active[0]['short_label'] == 'РЮ'

    everyone = mgr.get_schedule_employees(include_inactive=True)
    assert len(everyone) == 2

    # Имя из смен подмешивается виртуально, даже если его нет в реестре
    loc_id = mgr.get_locations()[0]['id']
    role_id = mgr.get_roles()[0]['id']
    mgr.create_shift('2026-06-05', 'Старый Сотрудник', loc_id, role_id)
    names = [e['name'] for e in mgr.get_schedule_employees()]
    assert 'Старый Сотрудник' in names


# ==================== schedule_plans: планы и сводка ====================

LOCATIONS = [
    {'id': 1, 'name': 'Варшавская', 'short_name': 'Вар', 'venue_key': 'varshavskaya'},
    {'id': 2, 'name': 'Лиговский', 'short_name': 'Лиг', 'venue_key': 'ligovskiy'},
]


def test_build_month_plans_sources_and_fallback():
    daily_plans = {
        # 1 июня: план из весов только для varshavskaya
        '2026-06-01': {'varshavskaya': 40000.0, 'all': 40000.0},
    }
    manual_rows = [
        # фоллбэк: ручной план для ligovskiy 1 июня (точка не покрыта daily_plans)
        {'date': '2026-06-01', 'location_id': 2, 'plan_revenue': 30000, 'fact_revenue': 31000},
        # факт без плана 2 июня
        {'date': '2026-06-02', 'location_id': 1, 'plan_revenue': 0, 'fact_revenue': 45000},
    ]

    plans = build_month_plans(2026, 6, LOCATIONS, daily_plans, manual_rows)

    d1 = plans['2026-06-01']
    assert d1['locations'][1] == {'plan': 40000.0, 'plan_source': 'weights', 'fact': None}
    assert d1['locations'][2] == {'plan': 30000.0, 'plan_source': 'manual', 'fact': 31000.0}
    assert d1['plan_total'] == 70000.0
    assert d1['fact_total'] == 31000.0

    d2 = plans['2026-06-02']
    # plan_revenue=0 — это НЕ план: отсутствие плана не равно нулевому плану
    assert d2['locations'][1] == {'plan': None, 'plan_source': None, 'fact': 45000.0}
    assert d2['plan_total'] is None
    assert d2['fact_total'] == 45000.0

    # День без данных вообще
    d3 = plans['2026-06-03']
    assert d3['plan_total'] is None and d3['fact_total'] is None
    # Все дни месяца присутствуют
    assert len(plans) == 30


def test_build_month_plans_olap_fact_priority():
    """Факт из iiko OLAP (как на дашборде) приоритетнее сохранённого daily_revenue;
    при недоступном iiko (olap_fact=None) — фоллбэк на сохранённый факт."""
    manual_rows = [
        {'date': '2026-06-01', 'location_id': 1, 'plan_revenue': 0, 'fact_revenue': 11111},
    ]
    olap_fact = {
        '2026-06-01': {'varshavskaya': 50000.0},
        '2026-06-02': {'ligovskiy': 20000.0},
    }

    plans = build_month_plans(2026, 6, LOCATIONS, {}, manual_rows, olap_fact=olap_fact)
    # OLAP перекрывает сохранённый факт
    assert plans['2026-06-01']['locations'][1]['fact'] == 50000.0
    # OLAP успешен, но по точке/дню данных нет -> факта нет (не из manual)
    assert plans['2026-06-01']['locations'][2]['fact'] is None
    assert plans['2026-06-02']['locations'][2]['fact'] == 20000.0

    # iiko недоступен -> фоллбэк на сохранённый daily_revenue
    plans_offline = build_month_plans(2026, 6, LOCATIONS, {}, manual_rows, olap_fact=None)
    assert plans_offline['2026-06-01']['locations'][1]['fact'] == 11111.0


def test_compute_month_summary_formulas():
    daily_plans = {
        '2026-06-01': {'varshavskaya': 10000.0, 'ligovskiy': 5000.0},
        '2026-06-02': {'varshavskaya': 10000.0, 'ligovskiy': 5000.0},
        '2026-06-03': {'varshavskaya': 20000.0, 'ligovskiy': 10000.0},
    }
    manual_rows = [
        {'date': '2026-06-01', 'location_id': 1, 'plan_revenue': 0, 'fact_revenue': 12000},
        {'date': '2026-06-01', 'location_id': 2, 'plan_revenue': 0, 'fact_revenue': 6000},
    ]
    plans = build_month_plans(2026, 6, LOCATIONS, daily_plans, manual_rows)
    summary = compute_month_summary(plans, LOCATIONS)
    m = summary['month']

    # план: 15000 + 15000 + 30000
    assert m['plan_total'] == 60000.0
    # факт: только 1 июня
    assert m['fact_total'] == 18000.0
    assert m['days_with_fact'] == 1
    assert m['avg_fact'] == 18000.0
    # ожидаемая = факт(1июн) + план(2июн) + план(3июн)
    assert m['expected'] == 18000.0 + 15000.0 + 30000.0
    # выполнение: факт / план того же дня = 18000/15000
    assert m['completion_pct'] == 120.0

    var = next(l for l in summary['locations'] if l['location_id'] == 1)
    assert var['plan_total'] == 40000.0
    assert var['fact_total'] == 12000.0
    assert var['expected'] == 12000.0 + 10000.0 + 20000.0
    assert var['completion_pct'] == 120.0

    # Формулы отдаются текстом для тултипов
    assert 'вес' in summary['formulas']['plan']


def test_compute_month_summary_empty_month():
    plans = build_month_plans(2026, 6, LOCATIONS, {}, [])
    summary = compute_month_summary(plans, LOCATIONS)
    m = summary['month']
    assert m['plan_total'] is None
    assert m['fact_total'] is None
    assert m['avg_fact'] is None
    assert m['expected'] is None
    assert m['completion_pct'] is None


def test_compute_employees_load():
    shifts = [
        {'employee_name': 'А', 'date': '2026-06-01', 'fact_minutes': 720},
        {'employee_name': 'А', 'date': '2026-06-02', 'fact_minutes': 630},
        {'employee_name': 'А', 'date': '2026-06-03', 'fact_minutes': None},  # прошла, факта нет
        {'employee_name': 'А', 'date': '2026-06-25', 'fact_minutes': None},  # будущая
        {'employee_name': 'Б', 'date': '2026-06-01', 'fact_minutes': None},
    ]
    load = compute_employees_load(shifts, today_str='2026-06-10')

    a = next(r for r in load if r['employee_name'] == 'А')
    assert a['shifts_count'] == 4
    assert a['fact_minutes'] == 1350
    assert a['missing_fact'] == 1  # будущая смена «без часов» не считается

    b = next(r for r in load if r['employee_name'] == 'Б')
    assert b['shifts_count'] == 1
    assert b['missing_fact'] == 1

    # Сортировка: по числу смен убыв.
    assert load[0]['employee_name'] == 'А'
