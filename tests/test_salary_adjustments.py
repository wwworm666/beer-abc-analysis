"""
Тесты ручных корректировок ЗП (salary_adjustments, схема v8 shifts.db).

Модель: одна строка на месяц + сотрудника + категорию (UPSERT). Суммы в рублях,
хранятся положительными — знак задаёт категория (SALARY_ADJUSTMENT_CATEGORIES:
deduction_* вычитаются из ЗП, остальные прибавляются). Сумма 0 без заметки =
корректировки нет, строка удаляется.

Запуск: `py -3 tests/test_salary_adjustments.py` (совместимо с pytest, fixture tmpdir).
"""

import os
import sys
import sqlite3
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shifts_manager import ShiftsManager, SALARY_ADJUSTMENT_CATEGORIES


def _fresh_mgr(dirpath):
    return ShiftsManager(db_path=os.path.join(str(dirpath), 'shifts.db'))


def test_v8_schema_has_adjustments_table(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    assert ShiftsManager.SCHEMA_VERSION >= 8
    conn = sqlite3.connect(mgr.db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ShiftsManager.SCHEMA_VERSION
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'salary_adjustments' in tables
    finally:
        conn.close()


def test_v7_db_migrates_to_v8(tmpdir):
    """Старая БД (v7, без таблицы) домигрируется при открытии менеджера."""
    mgr = _fresh_mgr(tmpdir)
    conn = sqlite3.connect(mgr.db_path)
    conn.execute("DROP TABLE salary_adjustments")
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()

    mgr2 = ShiftsManager(db_path=mgr.db_path)
    assert mgr2.get_salary_adjustments('2026-07') == {}
    conn = sqlite3.connect(mgr.db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == ShiftsManager.SCHEMA_VERSION
    conn.close()


def test_set_get_roundtrip(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    old = mgr.set_salary_adjustment('2026-07', 'Юреня Роман', 'deduction_inventory',
                                    6934, note='недостача по инвентаризации')
    assert old is None  # раньше корректировки не было
    adj = mgr.get_salary_adjustments('2026-07')
    assert adj['Юреня Роман']['deduction_inventory']['amount'] == 6934
    assert adj['Юреня Роман']['deduction_inventory']['note'] == 'недостача по инвентаризации'


def test_upsert_overwrites_and_returns_old(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    mgr.set_salary_adjustment('2026-07', 'Юреня Роман', 'deduction_other', 10000)
    old = mgr.set_salary_adjustment('2026-07', 'Юреня Роман', 'deduction_other', 12000)
    assert old == 10000
    adj = mgr.get_salary_adjustments('2026-07')
    assert adj['Юреня Роман']['deduction_other']['amount'] == 12000
    # По-прежнему одна строка (UPSERT, не дубль)
    conn = sqlite3.connect(mgr.db_path)
    n = conn.execute("SELECT COUNT(*) FROM salary_adjustments").fetchone()[0]
    conn.close()
    assert n == 1


def test_zero_without_note_deletes_row(tmpdir):
    """Сумма 0 без заметки = «корректировки нет» — строка удаляется,
    таблица не зарастает нулями."""
    mgr = _fresh_mgr(tmpdir)
    mgr.set_salary_adjustment('2026-07', 'Юреня Роман', 'vacation', 46818)
    old = mgr.set_salary_adjustment('2026-07', 'Юреня Роман', 'vacation', 0)
    assert old == 46818
    assert mgr.get_salary_adjustments('2026-07') == {}


def test_negative_amount_clamped_to_zero(tmpdir):
    """Отрицательная сумма зажимается в 0 (знак задаёт категория, не ввод) —
    0 без заметки означает удаление."""
    mgr = _fresh_mgr(tmpdir)
    mgr.set_salary_adjustment('2026-07', 'Юреня Роман', 'extra_income', 1450)
    mgr.set_salary_adjustment('2026-07', 'Юреня Роман', 'extra_income', -500)
    assert mgr.get_salary_adjustments('2026-07') == {}


def test_months_are_isolated(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    mgr.set_salary_adjustment('2026-07', 'Юреня Роман', 'deduction_inventory', 6934)
    mgr.set_salary_adjustment('2026-08', 'Юреня Роман', 'deduction_inventory', 100)
    assert mgr.get_salary_adjustments('2026-07')['Юреня Роман']['deduction_inventory']['amount'] == 6934
    assert mgr.get_salary_adjustments('2026-08')['Юреня Роман']['deduction_inventory']['amount'] == 100
    assert mgr.get_salary_adjustments('2026-06') == {}


def test_categories_dict_covers_export_rows(tmpdir):
    """Категории — единый источник для роутов и экспорта: все пять строк
    эталонной таблицы присутствуют."""
    assert set(SALARY_ADJUSTMENT_CATEGORIES) == {
        'vacation', 'extra_income',
        'deduction_inventory', 'deduction_discipline', 'deduction_other',
    }


if __name__ == '__main__':
    import inspect

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and inspect.isfunction(f)]
    passed = failed = 0
    for name, fn in tests:
        d = tempfile.mkdtemp(prefix='salary_adj_')
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
