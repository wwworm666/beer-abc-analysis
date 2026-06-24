"""
Тесты журнала изменений графика (таблица schedule_audit, схема v4 shifts.db).

Журнал append-only: фиксирует «кто что менял» в графике (смены, факт часов,
выходные). actor_name — снимок имени автора, чтобы запись читалась даже после
переименования/удаления аккаунта. entity_date — дата изменения для фильтра по
месяцу.

Запуск: `py -3 tests/test_schedule_audit.py` (pytest локально может быть не
установлен). Функции принимают путь к временной папке и совместимы с pytest
(fixture tmpdir передаёт py.path.local, os.path.join его понимает).
"""

import os
import sys
import sqlite3
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shifts_manager import ShiftsManager


def _fresh_mgr(dirpath):
    return ShiftsManager(db_path=os.path.join(str(dirpath), 'shifts.db'))


def test_fresh_db_has_audit_table_v4(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    conn = sqlite3.connect(mgr.db_path)
    try:
        assert ShiftsManager.SCHEMA_VERSION >= 4
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ShiftsManager.SCHEMA_VERSION
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'schedule_audit' in tables
    finally:
        conn.close()


def test_audit_table_recreated_if_missing(tmpdir):
    """CREATE TABLE IF NOT EXISTS идемпотентен: старую БД без таблицы повторное
    открытие менеджера домигрирует (добавит schedule_audit)."""
    mgr = _fresh_mgr(tmpdir)
    conn = sqlite3.connect(mgr.db_path)
    conn.execute("DROP TABLE schedule_audit")
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()

    ShiftsManager(db_path=mgr.db_path)  # повторное открытие — additive-миграция
    conn = sqlite3.connect(mgr.db_path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'schedule_audit' in tables
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ShiftsManager.SCHEMA_VERSION
    finally:
        conn.close()


def test_log_and_get_audit_newest_first(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    mgr.log_audit('shift_create', 'Добавлена смена A', actor_login='ivan',
                  actor_name='Петров Иван', entity_date='2026-06-05',
                  employee_name='Тестов Тест')
    mgr.log_audit('shift_delete', 'Удалена смена B', actor_login='ivan',
                  actor_name='Петров Иван', entity_date='2026-06-06')

    rows = mgr.get_audit(2026, 6)
    assert len(rows) == 2
    # новые сверху
    assert rows[0]['summary'] == 'Удалена смена B'
    assert rows[1]['summary'] == 'Добавлена смена A'
    assert rows[0]['actor_name'] == 'Петров Иван'
    assert rows[0]['action'] == 'shift_delete'
    assert rows[1]['employee_name'] == 'Тестов Тест'


def test_get_audit_filters_by_month(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    mgr.log_audit('fact_set', 'июнь', actor_name='A', entity_date='2026-06-10')
    mgr.log_audit('fact_set', 'июль', actor_name='A', entity_date='2026-07-10')
    mgr.log_audit('fact_set', 'без даты', actor_name='A', entity_date=None)

    june = mgr.get_audit(2026, 6)
    assert [r['summary'] for r in june] == ['июнь']

    july = mgr.get_audit(2026, 7)
    assert [r['summary'] for r in july] == ['июль']

    # без года/месяца — все последние записи (включая без entity_date)
    allrows = mgr.get_audit()
    assert len(allrows) == 3


def test_get_audit_limit(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    for i in range(5):
        mgr.log_audit('shift_create', 'смена ' + str(i), actor_name='A',
                      entity_date='2026-06-0' + str(i + 1))
    rows = mgr.get_audit(2026, 6, limit=2)
    assert len(rows) == 2
    # последние две по id DESC — это 4 и 3
    assert rows[0]['summary'] == 'смена 4'
    assert rows[1]['summary'] == 'смена 3'


def test_get_shift_returns_joined_names(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    loc = mgr.get_locations()[0]
    role = mgr.get_roles()[0]
    sid = mgr.create_shift('2026-06-05', 'Романов Юрий', loc['id'], role['id'],
                           start_time='18:00')
    sh = mgr.get_shift(sid)
    assert sh is not None
    assert sh['employee_name'] == 'Романов Юрий'
    assert sh['location_name'] == loc['name']
    assert sh['location_short'] == loc['short_name']
    assert sh['role_name'] == role['name']
    assert sh['start_time'] == '18:00'

    assert mgr.get_shift(999999) is None


def test_get_day_off_request_by_id(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    rid = mgr.create_day_off_request('Иванова Елена', '2026-06-10', '2026-06-12', 'отпуск')
    req = mgr.get_day_off_request(rid)
    assert req is not None
    assert req['employee_name'] == 'Иванова Елена'
    assert req['date_from'] == '2026-06-10'
    assert req['date_to'] == '2026-06-12'

    assert mgr.get_day_off_request(999999) is None


if __name__ == '__main__':
    import inspect

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and inspect.isfunction(f)]
    passed = failed = 0
    for name, fn in tests:
        d = tempfile.mkdtemp(prefix='sched_audit_')
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
