"""
Тесты ставок по ролям и часов-по-ролям для расчёта ЗП (схема v5 shifts.db).

Модель оплаты: часы — из графика (fact_minutes, единственный источник часов
оплаты; iiko как источник часов больше не используется), ставка — у роли смены.
Оплата сотрудника = сумма по сменам: часы × ставка роли.

Запуск: `py -3 tests/test_salary_hours.py` (pytest локально может быть не
установлен). Совместимо с pytest (fixture tmpdir).
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


def _role_id(mgr, name):
    return next(r['id'] for r in mgr.get_roles() if r['name'] == name)


def test_v5_roles_have_rate_default_300(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    assert ShiftsManager.SCHEMA_VERSION >= 5
    conn = sqlite3.connect(mgr.db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ShiftsManager.SCHEMA_VERSION
        cols = {r[1] for r in conn.execute("PRAGMA table_info(roles)")}
        assert 'rate_per_hour' in cols
    finally:
        conn.close()
    # Все сидовые роли получают ставку 300 по умолчанию
    for r in mgr.get_roles():
        assert r['rate_per_hour'] == 300


def test_v4_roles_migrated_to_rate_300(tmpdir):
    """Старая БД без rate_per_hour домигрируется: колонка добавляется со
    значением 300 для существующих ролей (оплата не меняется до правок)."""
    mgr = _fresh_mgr(tmpdir)
    conn = sqlite3.connect(mgr.db_path)
    conn.execute("ALTER TABLE roles DROP COLUMN rate_per_hour")
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    conn.close()

    mgr2 = ShiftsManager(db_path=mgr.db_path)
    for r in mgr2.get_roles():
        assert r['rate_per_hour'] == 300
    conn = sqlite3.connect(mgr.db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == ShiftsManager.SCHEMA_VERSION
    conn.close()


def test_set_role_rate(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    rid = _role_id(mgr, 'второй бармен')
    assert mgr.set_role_rate(rid, 250)
    assert next(r['rate_per_hour'] for r in mgr.get_roles() if r['id'] == rid) == 250
    # Отрицательная ставка зажимается в 0
    assert mgr.set_role_rate(rid, -100)
    assert next(r['rate_per_hour'] for r in mgr.get_roles() if r['id'] == rid) == 0
    # Несуществующая роль
    assert not mgr.set_role_rate(999999, 100)


def test_hours_by_role_pay_and_breakdown(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    loc = mgr.get_locations()[0]['id']
    barmen = _role_id(mgr, 'бармен')           # ставка 300
    vtoroy = _role_id(mgr, 'второй бармен')     # ставим 250
    mgr.set_role_rate(vtoroy, 250)

    # Романов: полная смена (бармен, 12ч) + вечер (второй бармен, 8ч) + бармен без факта
    s1 = mgr.create_shift('2026-07-05', 'Романов Юрий', loc, barmen)
    mgr.set_shift_fact(s1, 720)  # 12:00
    s2 = mgr.create_shift('2026-07-06', 'Романов Юрий', loc, vtoroy, start_time='18:00')
    mgr.set_shift_fact(s2, 480)  # 8:00
    mgr.create_shift('2026-07-07', 'Романов Юрий', loc, barmen)  # факт не введён
    # Иванова: бармен 10ч (ставка 300)
    s4 = mgr.create_shift('2026-07-05', 'Иванова Елена', loc, barmen)
    mgr.set_shift_fact(s4, 600)  # 10:00
    # Смена в августе — не должна попасть в июльский период
    s5 = mgr.create_shift('2026-08-01', 'Романов Юрий', loc, barmen)
    mgr.set_shift_fact(s5, 600)

    rows = mgr.get_hours_by_role_for_period('2026-07-01', '2026-07-31')
    by_name = {e['employee_name']: e for e in rows}

    rom = by_name['Романов Юрий']
    roles = {r['role_name']: r for r in rom['roles']}
    assert roles['бармен']['minutes'] == 720           # август не учтён, факт-NULL не суммируется
    assert roles['бармен']['hours'] == 12.0
    assert roles['бармен']['pay'] == 3600.0            # 12 × 300
    assert roles['второй бармен']['minutes'] == 480
    assert roles['второй бармен']['pay'] == 2000.0     # 8 × 250
    assert rom['total_minutes'] == 1200
    assert rom['total_hours'] == 20.0
    assert rom['total_pay'] == 5600.0
    assert rom['shifts_without_fact'] == 1             # бармен-смена 07 без факта

    iva = by_name['Иванова Елена']
    assert iva['total_pay'] == 3000.0                  # 10 × 300 (бармен)
    assert iva['shifts_without_fact'] == 0

    # Сортировка по убыванию оплаты
    assert rows[0]['employee_name'] == 'Романов Юрий'


def test_hours_by_role_empty_period(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    assert mgr.get_hours_by_role_for_period('2026-07-01', '2026-07-31') == []


def test_only_two_roles_no_intern(tmpdir):
    """Роль «стажёр» убрана: остаются только бармен и второй бармен."""
    mgr = _fresh_mgr(tmpdir)
    names = [r['name'] for r in mgr.get_roles()]
    assert names == ['бармен', 'второй бармен']
    assert 'стажёр' not in names


def test_intern_removed_only_when_unused(tmpdir):
    """Идемпотентное удаление стажёра не трогает роль, если на неё есть смена
    (защита от осиротевших смен). Симулируем старую БД со стажёром + сменой."""
    mgr = _fresh_mgr(tmpdir)
    conn = sqlite3.connect(mgr.db_path)
    conn.execute("INSERT INTO roles (name, short_name, color, sort_order) "
                 "VALUES ('стажёр', 'Ст', '#FF9800', 3)")
    sid = conn.execute("SELECT id FROM roles WHERE name='стажёр'").fetchone()[0]
    loc = conn.execute("SELECT id FROM locations LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO shifts (date, employee_name, location_id, role_id) "
                 "VALUES ('2026-07-05', 'Кто-то', ?, ?)", (loc, sid))
    conn.commit(); conn.close()

    # Переоткрытие менеджера запускает seed-фиксы: стажёр НЕ удалён (есть смена)
    mgr2 = ShiftsManager(db_path=mgr.db_path)
    assert 'стажёр' in [r['name'] for r in mgr2.get_roles()]


if __name__ == '__main__':
    import inspect

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and inspect.isfunction(f)]
    passed = failed = 0
    for name, fn in tests:
        d = tempfile.mkdtemp(prefix='salary_hours_')
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
