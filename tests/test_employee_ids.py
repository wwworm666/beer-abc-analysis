"""
Тесты привязки сотрудников графика к стабильному id из iiko (схема v6).

Проверяют sync_employees: бэкофилл employee_id у смен, сопоставление по точному
имени / перестановке слов / ручному override, канонизацию имени, дедуп legacy-
строк реестра, распространение переименования и идемпотентность.

Запуск: `py -3 tests/test_employee_ids.py` (pytest локально может быть не
установлен). Совместимо с pytest (fixture tmpdir).
"""

import os
import sys
import sqlite3
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shifts_manager import ShiftsManager
from core.schedule_plans import (compute_employees_load, _max_consecutive_days,
                                 compute_coverage_by_dow, SHIFT_NORM)

# Стабильные id (как GUID из iiko, но короткие для теста)
ID_NOVAEV = 'id-novaev'
ID_VASILIEV = 'id-vasiliev'
ID_KIZATOV = 'id-kizatov'
ID_VERESH = 'id-veresh'
ID_BOBRIKOV = 'id-bobrikov'
ID_MAKAROVA = 'id-makarova'
ID_COOK = 'id-cook'

# Текущий справочник iiko (id, имя). Имена — в текущем порядке/написании.
IIKO_DIR = [
    (ID_NOVAEV, 'Артем Новаев'),
    (ID_VASILIEV, 'Никита Васильев'),
    (ID_KIZATOV, 'Дамир Кизатов'),
    (ID_VERESH, 'Егор Верещагин'),
    (ID_BOBRIKOV, 'Егор Бобриков'),
    (ID_MAKAROVA, 'Татьяна Макарова'),
    (ID_COOK, 'Повар Иван'),
]


def _fresh_mgr(dirpath):
    return ShiftsManager(db_path=os.path.join(str(dirpath), 'shifts.db'))


def _seed_legacy(mgr):
    """Сымитировать состояние «до v6»: смены под старыми именами (employee_id
    NULL) + дублирующиеся legacy-строки реестра без iiko_id."""
    loc = mgr.get_locations()[0]['id']
    role = mgr.get_roles()[0]['id']
    # Смены под СТАРЫМИ именами, без employee_id
    legacy_shifts = [
        ('2026-06-01', 'Артемий Новаев'),   # переименование Артемий->Артем (override)
        ('2026-06-02', 'Артемий Новаев'),
        ('2026-06-03', 'Васильев Никита'),  # перестановка слов
        ('2026-06-04', 'Кизатов Дамир'),    # перестановка слов
        ('2026-06-05', 'Егор Верещагин'),   # точное совпадение
    ]
    conn = sqlite3.connect(mgr.db_path)
    for d, nm in legacy_shifts:
        conn.execute('INSERT INTO shifts (date, employee_name, location_id, role_id) '
                     'VALUES (?, ?, ?, ?)', (d, nm, loc, role))
    # Legacy-реестр: старые имена + пустые дубли (как накопилось прошлыми синками)
    for nm in ['Артемий Новаев', 'Артем Новаев', 'Васильев Никита', 'Кизатов Дамир',
               'Макарова Татьяна', 'Татьяна Макарова']:
        conn.execute('INSERT OR IGNORE INTO schedule_employees (name) VALUES (?)', (nm,))
    conn.commit()
    conn.close()


def _shift_emp(mgr, date_str):
    conn = sqlite3.connect(mgr.db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT employee_id, employee_name FROM shifts WHERE date = ?',
                       (date_str,)).fetchone()
    conn.close()
    return (row['employee_id'], row['employee_name'])


def test_schema_v6_columns(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    assert ShiftsManager.SCHEMA_VERSION >= 6
    conn = sqlite3.connect(mgr.db_path)
    assert conn.execute('PRAGMA user_version').fetchone()[0] >= 6
    scols = {r[1] for r in conn.execute('PRAGMA table_info(shifts)')}
    ecols = {r[1] for r in conn.execute('PRAGMA table_info(schedule_employees)')}
    conn.close()
    assert 'employee_id' in scols
    assert 'iiko_id' in ecols


def test_sync_backfills_by_exact_norm_and_override(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    _seed_legacy(mgr)
    report = mgr.sync_employees(IIKO_DIR, overrides={'Артемий Новаев': ID_NOVAEV})

    # Все 5 смен привязаны, несопоставленных нет
    assert report['unmatched'] == []
    assert report['shifts_backfilled'] == 5

    # Override (переименование Артемий->Артем)
    assert _shift_emp(mgr, '2026-06-01') == (ID_NOVAEV, 'Артем Новаев')
    assert _shift_emp(mgr, '2026-06-02') == (ID_NOVAEV, 'Артем Новаев')
    # Перестановка слов
    assert _shift_emp(mgr, '2026-06-03') == (ID_VASILIEV, 'Никита Васильев')
    assert _shift_emp(mgr, '2026-06-04') == (ID_KIZATOV, 'Дамир Кизатов')
    # Точное совпадение
    assert _shift_emp(mgr, '2026-06-05') == (ID_VERESH, 'Егор Верещагин')


def test_sync_dedups_registry_and_activeness(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    _seed_legacy(mgr)
    mgr.sync_employees(IIKO_DIR, overrides={'Артемий Новаев': ID_NOVAEV})

    allr = mgr.get_schedule_employees(include_inactive=True)
    by_name = {r['name']: r for r in allr}
    names = list(by_name)

    # Старые имена и пустые дубли убраны
    for gone in ['Артемий Новаев', 'Васильев Никита', 'Кизатов Дамир', 'Макарова Татьяна']:
        assert gone not in names, f'{gone} должен был быть слит/удалён'
    # Канонические записи на месте, с id
    for nm, eid in [('Артем Новаев', ID_NOVAEV), ('Никита Васильев', ID_VASILIEV),
                    ('Дамир Кизатов', ID_KIZATOV), ('Егор Верещагин', ID_VERESH)]:
        assert by_name[nm]['id'] == eid
    # Один человек на id (нет дублей)
    ids = [r['id'] for r in allr if r['id']]
    assert len(ids) == len(set(ids))

    # Люди со сменами — активны; новые из справочника без смен — неактивны (скрыты)
    assert by_name['Артем Новаев']['active'] == 1
    assert by_name['Дамир Кизатов']['active'] == 1
    assert by_name['Повар Иван']['active'] == 0      # не бармен, смен нет
    assert by_name['Егор Бобриков']['active'] == 0   # отдельный человек, смен нет

    # Активный список (для кисти) не содержит скрытых
    active = mgr.get_schedule_employees(include_inactive=False)
    active_names = {r['name'] for r in active}
    assert 'Повар Иван' not in active_names
    assert 'Артем Новаев' in active_names


def test_rename_propagates_no_duplicate(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    _seed_legacy(mgr)
    mgr.sync_employees(IIKO_DIR, overrides={'Артемий Новаев': ID_NOVAEV})

    # Владелец переименовал в iiko: Артем -> Артём (тот же id)
    renamed = [(ID_NOVAEV, 'Артём Новаев') if i == ID_NOVAEV else (i, n)
               for i, n in IIKO_DIR]
    report = mgr.sync_employees(renamed)

    # Смены этого id переименованы, новых строк/дублей нет
    assert _shift_emp(mgr, '2026-06-01') == (ID_NOVAEV, 'Артём Новаев')
    assert _shift_emp(mgr, '2026-06-02') == (ID_NOVAEV, 'Артём Новаев')
    assert report['names_refreshed'] == 2
    assert report['shifts_backfilled'] == 0

    allr = mgr.get_schedule_employees(include_inactive=True)
    novaev_rows = [r for r in allr if r['id'] == ID_NOVAEV]
    assert len(novaev_rows) == 1
    assert novaev_rows[0]['name'] == 'Артём Новаев'


def test_sync_idempotent(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    _seed_legacy(mgr)
    mgr.sync_employees(IIKO_DIR, overrides={'Артемий Новаев': ID_NOVAEV})
    before = mgr.get_schedule_employees(include_inactive=True)
    # Повторный синк ничего не ломает: ни бэкофилла, ни новых строк
    rep2 = mgr.sync_employees(IIKO_DIR)
    after = mgr.get_schedule_employees(include_inactive=True)
    assert rep2['shifts_backfilled'] == 0
    assert rep2['added'] == 0
    assert rep2['legacy_removed'] == 0
    assert len(before) == len(after)


def test_hours_by_role_grouped_by_id(tmpdir):
    """Часы группируются по стабильному id: смены одного человека под разными
    написаниями имени (после бэкофилла) считаются вместе."""
    mgr = _fresh_mgr(tmpdir)
    _seed_legacy(mgr)
    # Факт на обе смены Новаева (под старым именем) — до синка
    conn = sqlite3.connect(mgr.db_path)
    conn.execute("UPDATE shifts SET fact_minutes = 600 WHERE date IN ('2026-06-01','2026-06-02')")
    conn.commit(); conn.close()

    mgr.sync_employees(IIKO_DIR, overrides={'Артемий Новаев': ID_NOVAEV})
    rows = mgr.get_hours_by_role_for_period('2026-06-01', '2026-06-30')
    nv = [e for e in rows if e['employee_name'] == 'Артем Новаев']
    assert len(nv) == 1
    assert nv[0]['total_minutes'] == 1200  # 2 × 600, под одним id


def test_create_shift_stores_employee_id(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    loc = mgr.get_locations()[0]['id']
    role = mgr.get_roles()[0]['id']
    sid = mgr.create_shift('2026-07-01', 'Артем Новаев', loc, role, employee_id=ID_NOVAEV)
    sh = mgr.get_shift(sid)
    assert sh['employee_id'] == ID_NOVAEV
    assert sh['employee_name'] == 'Артем Новаев'


def test_load_streak_and_grouping(tmpdir):
    """Нагрузка: норма 15, макс. серия смен подряд (по дням), группировка по id."""
    assert SHIFT_NORM == 15
    assert _max_consecutive_days([]) == 0
    assert _max_consecutive_days(['2026-06-10']) == 1
    assert _max_consecutive_days(['2026-06-01', '2026-06-02', '2026-06-03', '2026-06-05']) == 3
    # день+вечер одной даты не удлиняет серию (серия — по календарным дням)
    assert _max_consecutive_days(['2026-06-01', '2026-06-01', '2026-06-02']) == 2

    shifts = [
        {'employee_id': 'id1', 'employee_name': 'Артем Новаев', 'date': '2026-06-01', 'fact_minutes': 600},
        {'employee_id': 'id1', 'employee_name': 'Артем Новаев', 'date': '2026-06-02', 'fact_minutes': None},
        {'employee_id': 'id1', 'employee_name': 'Артем Новаев', 'date': '2026-06-03', 'fact_minutes': None},
        {'employee_id': 'id1', 'employee_name': 'Артем Новаев', 'date': '2026-06-03', 'fact_minutes': None},  # вечер
        {'employee_id': 'id2', 'employee_name': 'Иванова Елена', 'date': '2026-06-01', 'fact_minutes': None},
    ]
    load = compute_employees_load(shifts, today_str='2026-06-10')
    by = {r['employee_name']: r for r in load}
    a = by['Артем Новаев']
    assert a['shifts_count'] == 4          # 4 смены (включая вечер 03-го)
    assert a['max_streak'] == 3            # 01,02,03 подряд
    assert a['fact_minutes'] == 600
    assert a['missing_fact'] == 3          # 02 и оба 03 прошли без факта (< 06-10)
    assert by['Иванова Елена']['max_streak'] == 1


def test_coverage_by_dow(tmpdir):
    """Покрытие по дням недели: относительный спрос (money-free) + смены/день."""
    from datetime import date as _date
    month_plans = {
        '2026-06-01': {'plan_total': 100.0},
        '2026-06-05': {'plan_total': 200.0},
        '2026-06-06': {'plan_total': 200.0},
    }
    shifts = [
        {'date': '2026-06-01'}, {'date': '2026-06-01'},   # 2 смены
        {'date': '2026-06-05'},                            # 1
        {'date': '2026-06-06'},                            # 1
    ]
    rows = compute_coverage_by_dow(shifts, month_plans)
    assert len(rows) == 7
    assert [r['label'] for r in rows] == ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    # наружу не уходят рубли — только относительные доли
    assert all('plan' not in r and '_avg_plan' not in r for r in rows)

    by_dow = {r['dow']: r for r in rows}
    mon = by_dow[_date.fromisoformat('2026-06-01').weekday()]
    fri = by_dow[_date.fromisoformat('2026-06-05').weekday()]
    assert mon['avg_shifts'] == 2.0 and mon['demand'] == 0.5 and mon['coverage'] == 2.0
    assert fri['avg_shifts'] == 1.0 and fri['demand'] == 1.0 and fri['coverage'] == 0.5

    # день без данных: спрос 0, coverage None
    empty = [r for r in rows if r['days'] == 0][0]
    assert empty['demand'] == 0.0 and empty['coverage'] is None


if __name__ == '__main__':
    import inspect
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and inspect.isfunction(f)]
    passed = failed = 0
    for name, fn in tests:
        d = tempfile.mkdtemp(prefix='emp_ids_')
        try:
            fn(d)
            print('  ok  ' + name)
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print('FAIL  ' + name + ': ' + repr(e))
            traceback.print_exc()
        finally:
            shutil.rmtree(d, ignore_errors=True)
    print('\n%d passed, %d failed' % (passed, failed))
    sys.exit(1 if failed else 0)
