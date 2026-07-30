"""
Тесты экспорта ЗП в Excel (core/salary_export.py).

Проверяется структура листа в формате эталонной таблицы владельца: порядок и
номера строк, значения по сотрудникам, тарифы, формулы Excel (такси, разница,
ИТОГО БАРМЕН, суммы по строкам). Раскладка при 2 ролях и 3 KPI повторяет
эталон бит-в-бит: строки 3..22, сотрудники с колонки F.

Запуск: `py -3 tests/test_salary_export.py` (совместимо с pytest).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.salary_export import build_salary_workbook, month_title, TAXI_RATE_PER_SHIFT


def _payload():
    """2 сотрудника, 2 роли, 3 KPI — числа из эталонного скриншота (Юреня)."""
    return {
        'month': '2026-07',
        'kpi_names': ['Доля кухни (%)', 'Доля розлива (%)', 'Средний чек (₽)'],
        'base_per_kpi': 5000,
        'roles': [
            {'name': 'бармен', 'rate': 300},
            {'name': 'второй бармен', 'rate': 400},
        ],
        'employees': [
            {
                'name': 'Юреня Роман',
                'hours_by_role': {'бармен': 97, 'второй бармен': 20},
                'pay_by_role': {'бармен': 29100, 'второй бармен': 8000},
                'shifts_count': 11,
                'handover_bonus': 5000,
                'day_plan_bonus': 9661,
                'kpi_premiums': [6082.0, 0, 0],
                'late_penalty': 0,
                'adjustments': {
                    'vacation': 0, 'extra_income': 0,
                    'deduction_inventory': 6934,
                    'deduction_discipline': 0, 'deduction_other': 0,
                },
            },
            {
                'name': 'Верещагин Егор',
                'hours_by_role': {'бармен': 95, 'второй бармен': 49},
                'pay_by_role': {'бармен': 28500, 'второй бармен': 19600},
                'shifts_count': 8,
                'handover_bonus': 3500,
                'day_plan_bonus': 13391,
                'kpi_premiums': [9000.0, 0, 0],
                'late_penalty': 500,
                'adjustments': {
                    'vacation': 0, 'extra_income': 1450,
                    'deduction_inventory': 5294,
                    'deduction_discipline': 250, 'deduction_other': 0,
                },
            },
        ],
    }


def _sheet():
    return build_salary_workbook(_payload()).active


def test_month_title():
    assert month_title('2026-07') == 'июль 2026'
    assert month_title('2026-01') == 'январь 2026'
    assert month_title('кривой ввод') == 'кривой ввод'


def test_header_and_layout():
    ws = _sheet()
    assert ws.title == 'ЗП 2026-07'
    assert ws['A1'].value == 'Расчёт ЗП — июль 2026'
    assert ws['A2'].value == 'Показатель'
    assert ws['B2'].value == 'Хозяин цифры'
    assert ws['E2'].value == 'Тариф'
    assert ws['F2'].value == 'Юреня Роман'
    assert ws['G2'].value == 'Верещагин Егор'
    # 2 сотрудника: ИТОГО в колонке H (6 + 2)
    assert ws['H2'].value == 'ИТОГО'
    # Порядок строк — как в эталоне (2 роли, 3 KPI => строки 3..22)
    labels = [ws.cell(row=r, column=1).value for r in range(3, 23)]
    assert labels == [
        'Часы', 'Часы 2-й в смене', 'Количество смен',
        'Ставка по часам', 'Ставка 2-й в смене', 'Отпуск',
        'Премия за приемку-передачу смены', 'Премия за дневной план',
        'KPI 1 — Доля кухни (%)', 'KPI 2 — Доля розлива (%)', 'KPI 3 — Средний чек (₽)',
        'Доп доход', 'Такси за смены расчет.', 'мосты', 'Такси за смены оф.',
        'Такси разница: доплата/удержание',
        'Вычет инвент', 'Вычет дисциплина', 'Доп вычет', 'ИТОГО БАРМЕН',
    ]


def test_values_and_tariffs():
    ws = _sheet()
    assert ws['F3'].value == 97          # часы бармен
    assert ws['F4'].value == 20          # часы 2-й
    assert ws['F5'].value == 11          # смены
    assert ws['E6'].value == 300         # тариф часа
    assert ws['F6'].value == 29100       # оплата часов
    assert ws['E7'].value == 400
    assert ws['F7'].value == 8000
    assert ws['E9'].value == 500         # тариф передачи смены
    assert ws['F9'].value == 5000
    assert ws['E10'].value == 1000       # тариф дневного плана
    assert ws['F10'].value == 9661
    assert ws['E11'].value == 5000       # тариф KPI = фонд / кол-во
    assert ws['F11'].value == 6082.0
    assert ws['G12'].value == 0          # KPI с нулём пишется как 0.00, не пусто
    assert ws['G14'].value == 1450       # доп доход
    assert ws['F19'].value == 6934       # вычет инвент
    assert ws['F20'].value is None       # дисциплина 0 -> пусто


def test_discipline_merges_auto_penalty_and_manual():
    """Строка «Вычет дисциплина» = авто-штраф за опоздания + ручной вычет."""
    ws = _sheet()
    assert ws['G20'].value == 750        # 500 (опоздания) + 250 (ручной)


def test_formulas():
    ws = _sheet()
    # Такси расчёт = смены x тариф (тариф в ячейке, правится в файле)
    assert ws['E15'].value == TAXI_RATE_PER_SHIFT
    assert ws['F15'].value == '=F5*$E15'
    # Оф. = фикс 15 смен x тариф (правило владельца, 10 500); без дневных
    # смен не начисляется. Мосты (F16) — ручная надбавка бухгалтера
    assert ws['F17'].value == '=IF(F5>0,15*$E15,0)'
    assert ws['F16'].value is None
    # Разница = расчёт + мосты - оф. — считается сама (доплата/удержание)
    assert ws['F18'].value == '=F15+F16-F17'
    # ИТОГО БАРМЕН: оплата + отпуск + премии + KPI + доп доход + такси-разница - вычеты
    assert ws['F22'].value == '=F6+F7+F8+F9+F10+F11+F12+F13+F14+F18-F19-F20-F21'
    assert ws['G22'].value == '=G6+G7+G8+G9+G10+G11+G12+G13+G14+G18-G19-G20-G21'
    # ИТОГО по строке — SUM по сотрудникам; итог итога — SUM по строке ИТОГО
    assert ws['H6'].value == '=SUM(F6:G6)'
    assert ws['H22'].value == '=SUM(F22:G22)'


def test_formula_injection_blocked():
    """Строка с ведущим «=» (имя сотрудника) пишется текстом, а не формулой;
    намеренные формулы (такси, ИТОГО, SUM) остаются формулами."""
    p = _payload()
    p['employees'][0]['name'] = '=HYPERLINK("http://evil";"Иванов")'
    ws = build_salary_workbook(p).active
    assert ws['F2'].data_type == 's'      # имя — текст
    assert ws['F15'].data_type == 'f'     # такси — формула
    assert ws['F22'].data_type == 'f'     # ИТОГО БАРМЕН — формула
    assert ws['H6'].data_type == 'f'      # SUM по строке — формула


def test_empty_employees_no_crash():
    wb = build_salary_workbook({'month': '2026-07', 'roles': [], 'kpi_names': [],
                                'employees': []})
    ws = wb.active
    assert ws['A2'].value == 'Показатель'
    # Без сотрудников ИТОГО-колонка сразу за тарифами, без формул
    assert ws['F2'].value == 'ИТОГО'


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
