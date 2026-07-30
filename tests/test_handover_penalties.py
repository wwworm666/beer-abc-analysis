"""
Тесты ручного штрафа за кассовую смену (handover_cash_penalties, схема v9).

Модель: строка (date, employee_name) = день, за который владелец руками снял
премию «передача смены» (500 ₽) — сумма кассы указана неверно, забыты траты.
Работает поверх автоправила «нет кассы — нет премии» и не задваивается с ним:
день, уже не оплаченный автоправилом, повторно не вычитается
(_manual_penalty_days в routes/employee.py).

Запуск: `py -3 tests/test_handover_penalties.py` (совместимо с pytest, fixture tmpdir).
"""

import os
import sys
import sqlite3
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shifts_manager import ShiftsManager
from routes.employee import _manual_penalty_days


def _fresh_mgr(dirpath):
    return ShiftsManager(db_path=os.path.join(str(dirpath), 'shifts.db'))


def test_v9_schema_has_penalties_table(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    assert ShiftsManager.SCHEMA_VERSION >= 9
    conn = sqlite3.connect(mgr.db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ShiftsManager.SCHEMA_VERSION
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'handover_cash_penalties' in tables
        # v8-таблица корректировок оставлена (additive-only), хотя UI убран
        assert 'salary_adjustments' in tables
    finally:
        conn.close()


def test_v8_db_migrates_to_v9(tmpdir):
    """Старая БД (v8, без таблицы штрафов) домигрируется при открытии."""
    mgr = _fresh_mgr(tmpdir)
    conn = sqlite3.connect(mgr.db_path)
    conn.execute("DROP TABLE handover_cash_penalties")
    conn.execute("PRAGMA user_version = 8")
    conn.commit()
    conn.close()

    mgr2 = ShiftsManager(db_path=mgr.db_path)
    assert mgr2.get_handover_penalties('2026-07-01', '2026-07-31') == []


def test_set_get_roundtrip(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    assert mgr.set_handover_penalty('2026-07-12', 'Юреня Роман', True,
                                    note='неверная сумма кассы')
    rows = mgr.get_handover_penalties('2026-07-01', '2026-07-31')
    assert rows == [{'date': '2026-07-12', 'employee_name': 'Юреня Роман',
                     'note': 'неверная сумма кассы'}]


def test_unset_removes_row(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    mgr.set_handover_penalty('2026-07-12', 'Юреня Роман', True)
    assert mgr.set_handover_penalty('2026-07-12', 'Юреня Роман', False)
    assert mgr.get_handover_penalties('2026-07-01', '2026-07-31') == []
    # Повторное снятие — состояние не менялось (не событие для журнала)
    assert not mgr.set_handover_penalty('2026-07-12', 'Юреня Роман', False)


def test_repeat_set_same_state_not_changed(tmpdir):
    """Повторная простановка того же штрафа с той же причиной — changed=False
    (журнал не засоряется), смена причины — changed=True и note обновляется."""
    mgr = _fresh_mgr(tmpdir)
    assert mgr.set_handover_penalty('2026-07-12', 'Юреня Роман', True, note='а')
    assert not mgr.set_handover_penalty('2026-07-12', 'Юреня Роман', True, note='а')
    assert mgr.set_handover_penalty('2026-07-12', 'Юреня Роман', True, note='б')
    rows = mgr.get_handover_penalties('2026-07-01', '2026-07-31')
    assert len(rows) == 1 and rows[0]['note'] == 'б'


def test_one_row_per_day_and_employee(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    mgr.set_handover_penalty('2026-07-12', 'Юреня Роман', True)
    mgr.set_handover_penalty('2026-07-12', 'Верещагин Егор', True)
    mgr.set_handover_penalty('2026-07-13', 'Юреня Роман', True)
    assert len(mgr.get_handover_penalties('2026-07-01', '2026-07-31')) == 3


def test_period_filter_inclusive(tmpdir):
    mgr = _fresh_mgr(tmpdir)
    mgr.set_handover_penalty('2026-06-30', 'Юреня Роман', True)
    mgr.set_handover_penalty('2026-07-01', 'Юреня Роман', True)
    mgr.set_handover_penalty('2026-07-31', 'Юреня Роман', True)
    mgr.set_handover_penalty('2026-08-01', 'Юреня Роман', True)
    rows = mgr.get_handover_penalties('2026-07-01', '2026-07-31')
    assert [r['date'] for r in rows] == ['2026-07-01', '2026-07-31']


# ==================== _manual_penalty_days (чистая логика вычета) ====================

def _day(manual, rule_applies=True, cash_filled=True):
    return {'manual_cash_penalty': manual,
            'cash_rule_applies': rule_applies,
            'cash_filled': cash_filled}


def test_manual_penalty_days_counts_paid_days():
    """Штраф вычитает только дни, которые иначе были бы оплачены."""
    days = [
        _day(True, rule_applies=True, cash_filled=True),    # оплачен -> вычитаем
        _day(True, rule_applies=False, cash_filled=False),  # до отсечки -> вычитаем
        _day(True, rule_applies=True, cash_filled=None),    # график недоступен (fail-open платит) -> вычитаем
        _day(False, rule_applies=True, cash_filled=True),   # без штрафа
    ]
    assert _manual_penalty_days(days) == 3


def test_manual_penalty_days_no_double_subtraction():
    """День, уже не оплаченный автоправилом (нет кассы после отсечки), повторно
    не вычитается — иначе штраф резал бы двойные 500 за один день."""
    days = [_day(True, rule_applies=True, cash_filled=False)]
    assert _manual_penalty_days(days) == 0


if __name__ == '__main__':
    import inspect

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and inspect.isfunction(f)]
    passed = failed = 0
    for name, fn in tests:
        params = len(inspect.signature(fn).parameters)
        d = tempfile.mkdtemp(prefix='handover_pen_') if params else None
        try:
            fn(d) if params else fn()
            print('  ok  ' + name)
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print('FAIL  ' + name + ': ' + repr(e))
            traceback.print_exc()
        finally:
            if d:
                shutil.rmtree(d, ignore_errors=True)
    print('\n%d passed, %d failed' % (passed, failed))
    sys.exit(1 if failed else 0)
