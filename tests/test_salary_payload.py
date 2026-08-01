"""
Тесты серверной сборки payload ЗП (core/salary_payload.py) и выбора месяцев
ночной выгрузки (core/salary_scheduler.py).

Сеть и БД не дёргаются: проверяется чистая часть — сопоставление имён, мёрж
трёх источников, порядок колонок и границы месяца. Это то, что должно
совпадать с мёржем страницы `templates/bonus.html` (`mergeAndRender`,
`recalcEmployeeTotals`); расхождение здесь = ночная выгрузка разойдётся с
кнопкой.

Запуск: `py -3 tests/test_salary_payload.py` (совместимо с pytest).
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.salary_payload import (_merge_employees, _names_match, _sorted_kpi_keys,
                                 _total_salary, month_bounds, previous_month)


def test_month_bounds():
    assert month_bounds('2026-07') == ('2026-07-01', '2026-07-31')
    assert month_bounds('2026-02') == ('2026-02-01', '2026-02-28')
    assert month_bounds('2028-02') == ('2028-02-01', '2028-02-29')   # високосный
    assert month_bounds('2026-12') == ('2026-12-01', '2026-12-31')


def test_previous_month():
    assert previous_month('2026-07') == '2026-06'
    assert previous_month('2026-01') == '2025-12'
    assert previous_month('2026-10') == '2026-09'


def test_names_match_is_subset_by_words():
    """Как namesMatch в bonus.html: одно имя — подмножество другого по словам."""
    assert _names_match('Юреня Роман', 'Юреня Роман')
    assert _names_match('Юреня Роман', 'юреня роман')          # регистр
    assert _names_match('Юреня Роман', 'Юреня')                # график короче
    assert _names_match('Юреня', 'Юреня Роман Сергеевич')
    assert _names_match('Роман Юреня', 'Юреня Роман')          # порядок слов
    assert not _names_match('Юреня Роман', 'Верещагин Егор')
    assert not _names_match('', 'Юреня')
    assert not _names_match('Юреня Роман', 'Юреня Егор')       # разные вторые слова


def test_sorted_kpi_keys_numeric():
    """kpi10 идёт после kpi2, а не между kpi1 и kpi2 (сортировка по числу)."""
    keys = _sorted_kpi_keys({'kpi10': 1, 'kpi2': 1, 'kpi1': 1, 'мусор': 1})
    assert keys == ['kpi1', 'kpi2', 'kpi10']


def test_merge_three_sources():
    """Мёрж: bonus + KPI + часы, несопоставленные добавляются в хвост."""
    bonus = [{'name': 'Юреня Роман'}, {'name': 'Верещагин Егор'}]
    kpi = [{'employee_name': 'Верещагин'}, {'employee_name': 'Новый Сотрудник'}]
    hours = [{'employee_name': 'Юреня'}, {'employee_name': 'Только В Графике'}]
    merged = _merge_employees(bonus, kpi, hours)
    names = [m['name'] for m in merged]
    assert names == ['Юреня Роман', 'Верещагин Егор', 'Новый Сотрудник',
                     'Только В Графике']
    by_name = {m['name']: m for m in merged}
    assert by_name['Верещагин Егор']['kpi'] == {'employee_name': 'Верещагин'}
    assert by_name['Юреня Роман']['hours'] == {'employee_name': 'Юреня'}
    assert by_name['Юреня Роман']['kpi'] is None
    assert by_name['Только В Графике']['bonus'] is None


def test_merge_does_not_reuse_one_source_row_twice():
    """Один и тот же KPI-сотрудник не привязывается к двум людям."""
    bonus = [{'name': 'Юреня'}, {'name': 'Юреня Роман'}]
    merged = _merge_employees(bonus, [{'employee_name': 'Юреня'}], [])
    assert merged[0]['kpi'] is not None
    assert merged[1]['kpi'] is None


def test_total_salary_drives_column_order():
    """Итог = премия + передача - штраф + KPI + оплата часов + такси."""
    entry = {
        'bonus': {'bonus': 1000, 'shift_handover_bonus': 500, 'penalty': 250},
        'kpi': {'total_premium': 2000},
        'hours': {'total_pay': 30000, 'day_shifts': 10},
    }
    assert _total_salary(entry, 700) == 1000 + 500 - 250 + 2000 + 30000 + 7000
    assert _total_salary({'bonus': None, 'kpi': None, 'hours': None}, 700) == 0


def test_no_data_for_period_is_not_an_error():
    """404 «нет данных за период» — штатная ситуация, а не сбой.

    В первые дни месяца продажи ещё не закрыты. Месяц всё равно выгружается
    (часы и смены есть в графике), а вот 500 маскировать нельзя.
    """
    from flask import Flask, jsonify

    from core.salary_payload import NoDataForPeriod, _call_view

    app = Flask(__name__)

    def view_404():
        return jsonify({'error': 'Нет данных за выбранный период'}), 404

    def view_500():
        return jsonify({'error': 'внутренняя ошибка'}), 500

    try:
        _call_view(app, view_404, '/api/bonus-calculate', method='POST', json={})
        assert False, 'ожидалась NoDataForPeriod'
    except NoDataForPeriod:
        pass
    # Прочие ошибки маскировать нельзя — они должны быть видны
    try:
        _call_view(app, view_500, '/api/bonus-calculate', method='POST', json={})
        assert False, 'ожидалась RuntimeError'
    except NoDataForPeriod:
        assert False, '500 не должен превращаться в «нет данных»'
    except RuntimeError:
        pass


def test_months_to_sync():
    """Текущий месяц всегда; предыдущий — первую неделю месяца."""
    from core.salary_scheduler import PREV_UNTIL_DAY, months_to_sync
    assert PREV_UNTIL_DAY == 7
    assert months_to_sync(date(2026, 8, 1)) == ['2026-08', '2026-07']
    assert months_to_sync(date(2026, 8, 7)) == ['2026-08', '2026-07']
    assert months_to_sync(date(2026, 8, 8)) == ['2026-08']
    assert months_to_sync(date(2026, 8, 31)) == ['2026-08']
    assert months_to_sync(date(2026, 1, 3)) == ['2026-01', '2025-12']


def test_payload_survives_month_without_sales():
    """Месяц без закрытых продаж всё равно собирается — из графика.

    1-го числа iiko отвечает 404, но часы и смены уже есть; вкладка должна
    появиться сразу и наполняться по ходу месяца, а не ждать первых продаж.
    """
    from flask import Flask, jsonify

    import core.salary_payload as sp

    app = Flask(__name__)

    class _FakeShiftsMgr:
        def get_hours_by_role_for_period(self, a, b):
            return [{'employee_name': 'Юреня Роман', 'total_pay': 29100,
                     'day_shifts': 11, 'roles': [
                         {'role_name': 'бармен', 'hours': 97, 'pay': 29100}]}]

        def get_roles(self):
            return [{'name': 'бармен', 'rate_per_hour': 300, 'sort_order': 1}]

    def _fake_call(app_, view, path, **kw):
        raise sp.NoDataForPeriod(path)

    # Подменяем только источник часов: расчёт iiko не дёргается (_call_view
    # замокан), а график отдаёт фиксированного сотрудника
    import extensions

    real_call, real_mgr = sp._call_view, extensions.shifts_mgr
    sp._call_view = _fake_call
    extensions.shifts_mgr = _FakeShiftsMgr()
    try:
        payload = sp.build_payload_for_month(app, '2026-08')
    finally:
        sp._call_view = real_call
        extensions.shifts_mgr = real_mgr

    assert len(payload['employees']) == 1
    emp = payload['employees'][0]
    assert emp['name'] == 'Юреня Роман'
    assert emp['hours_by_role'] == {'бармен': 97}
    assert emp['shifts_count'] == 11
    # Премий ещё нет — они честно нулевые, а не «потерялись»
    assert emp['handover_bonus'] == 0 and emp['day_plan_bonus'] == 0
    assert payload['kpi_names'] == []


if __name__ == '__main__':
    import inspect

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and inspect.isfunction(f)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print('  ok  ' + name)
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print('FAIL  ' + name + ': ' + repr(e))
            traceback.print_exc()
    print('\n%d passed, %d failed' % (passed, failed))
    sys.exit(1 if failed else 0)
