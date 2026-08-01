"""
Тесты экспорта ЗП в Excel (core/salary_export.py).

Проверяется структура листа в формате таблицы бухгалтерии: порядок и номера
строк, значения по сотрудникам, тарифы, шрифт эталона (PT Serif 8), живые
формулы Excel (оплата, передача смены, такси, разница, ИТОГО БАРМЕН, суммы по
строкам). Раскладка при 2 ролях и 3 KPI повторяет эталон: строки 3..22,
сотрудники с колонки F.

Ключевой тест — test_formulas_evaluate_to_page_numbers: формулы листа
вычисляются мини-интерпретатором и сверяются с суммами страницы ЗП (Юреня
48 109 — из эталонного файла бухгалтерии). Это гарантия, что переход на
формулы не изменил результат.

Запуск: `py -3 tests/test_salary_export.py` (совместимо с pytest).
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.salary_export import (FONT_NAME, FONT_SIZE, TAXI_RATE_PER_SHIFT,
                                build_salary_workbook, month_title, sheet_title)


def _payload():
    """2 сотрудника, 2 роли, 3 KPI — числа из эталонной таблицы (Юреня)."""
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


# --- Мини-интерпретатор формул листа --------------------------------------
# Понимает грамматику, которую пишет экспорт: ссылки на ячейки (в т.ч. $E$6),
# SUM(диапазон), + - *, целые литералы. Пустая ячейка = 0.
def _eval(ws, coord):
    v = ws[coord].value
    if v is None:
        return 0
    if not isinstance(v, str) or not v.startswith('='):
        return v
    expr = v[1:].replace('$', '')
    expr = re.sub(r'SUM\(([A-Z]+\d+:[A-Z]+\d+)\)',
                  lambda m: '(' + '+'.join(c.coordinate for r in ws[m.group(1)]
                                           for c in r) + ')', expr)
    expr = re.sub(r'([A-Z]+\d+)', lambda m: f'_E("{m.group(1)}")', expr)
    return eval(expr, {'_E': lambda c: _eval(ws, c)})


def test_month_title():
    assert month_title('2026-07') == 'июль 2026'
    assert month_title('2026-01') == 'январь 2026'
    assert month_title('кривой ввод') == 'кривой ввод'


def test_sheet_title_matches_reference_style():
    """Имя листа — как в таблице бухгалтерии: «июнь2026»."""
    assert sheet_title('2026-07') == 'июль2026'
    assert _sheet().title == 'июль2026'


def test_header_and_layout():
    ws = _sheet()
    # Строка 1 пустая — данные начинаются с шапки в строке 2 (как в эталоне)
    assert ws['A1'].value is None
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


def test_font_matches_reference():
    """Весь лист — шрифтом эталонной таблицы (PT Serif 8)."""
    ws = _sheet()
    for row in ws.iter_rows(min_row=2, max_row=22):
        for cell in row:
            assert cell.font.name == FONT_NAME, cell.coordinate
            assert cell.font.size == FONT_SIZE, cell.coordinate
    assert FONT_NAME == 'PT Serif' and FONT_SIZE == 8


def test_primary_values_are_numbers():
    """Первичные данные (часы, смены, план, KPI, вычеты) — числа, не формулы."""
    ws = _sheet()
    assert ws['F3'].value == 97          # часы бармен
    assert ws['F4'].value == 20          # часы 2-й
    assert ws['F5'].value == 11          # смены
    assert ws['E6'].value == 300         # тариф часа
    assert ws['E7'].value == 400
    assert ws['E9'].value == 500         # тариф передачи смены
    assert ws['E10'].value == 1000       # тариф дневного плана
    assert ws['F10'].value == 9661
    assert ws['E11'].value == 5000       # тариф KPI = фонд / кол-во
    assert ws['F11'].value == 6082.0
    assert ws['G12'].value == 0          # KPI с нулём пишется как 0.00, не пусто
    assert ws['G14'].value == 1450       # доп доход
    assert ws['F17'].value == 10500      # такси оф. — фикс 15 смен
    assert ws['F19'].value == 6934       # вычет инвент
    assert ws['F20'].value is None       # дисциплина 0 -> пусто
    assert ws['F16'].value is None       # мосты — ручная строка бухгалтера


def test_discipline_merges_auto_penalty_and_manual():
    """Строка «Вычет дисциплина» = авто-штраф за опоздания + ручной вычет."""
    assert _sheet()['G20'].value == 750  # 500 (опоздания) + 250 (ручной)


def test_formulas_match_reference_shape():
    """Выводимые строки — живые формулы в той же форме, что у бухгалтерии."""
    ws = _sheet()
    assert ws['F6'].value == '=F3*$E$6'          # оплата = часы x тариф
    assert ws['G7'].value == '=G4*$E$7'
    assert ws['F9'].value == '=F5*$E$9-500'      # смены x тариф - неоплаченный день
    assert ws['G9'].value == '=G5*$E$9-500'
    assert ws['E15'].value == TAXI_RATE_PER_SHIFT
    assert ws['F15'].value == '=F5*$E$15'        # такси = смены x тариф
    assert ws['F18'].value == '=F15+F16-F17'     # разница = расчёт + мосты - оф.
    assert ws['F22'].value == '=SUM(F6:F14)-F19-F20-F21+F18'   # как в эталоне
    assert ws['G22'].value == '=SUM(G6:G14)-G19-G20-G21+G18'
    assert ws['H6'].value == '=SUM(F6:G6)'       # колонка ИТОГО — SUM по строке
    assert ws['H22'].value == '=SUM(F22:G22)'
    # У «Количества смен» итога по строке нет (как в таблице бухгалтерии)
    assert ws['H5'].value is None


def test_formulas_evaluate_to_page_numbers():
    """Формулы дают ровно те суммы, что показывает страница ЗП.

    Юреня = 48 109 — число из эталонного файла бухгалтерии; это же значение
    проверялось до перехода на формулы.
    """
    ws = _sheet()
    assert _eval(ws, 'F6') == 29100              # 97 x 300
    assert _eval(ws, 'F7') == 8000               # 20 x 400
    assert _eval(ws, 'F9') == 5000               # премия за передачу смены
    assert _eval(ws, 'G9') == 3500
    assert _eval(ws, 'F15') == 11 * 700          # такси расчёт
    assert _eval(ws, 'F18') == 7700 - 10500      # -2 800, как в эталоне
    assert _eval(ws, 'G18') == 5600 - 10500      # -4 900
    assert _eval(ws, 'F22') == 48109             # ИТОГО Юреня
    assert _eval(ws, 'G22') == 64497             # ИТОГО Верещагин
    assert _eval(ws, 'H6') == 29100 + 28500
    assert _eval(ws, 'H18') == -2800 + -4900
    assert _eval(ws, 'H22') == 48109 + 64497


def test_bridges_flow_into_totals():
    """Вписанные бухгалтером «мосты» пересчитывают разницу и ИТОГО."""
    ws = _sheet()
    ws['F16'] = 2100                             # мосты = 7 x 300, как в эталоне
    assert _eval(ws, 'F18') == 7700 + 2100 - 10500
    assert _eval(ws, 'F22') == 48109 + 2100


def test_full_calc_on_load():
    """Книга помечена на пересчёт при открытии — иначе формулы видны пустыми."""
    assert build_salary_workbook(_payload()).calculation.fullCalcOnLoad is True


def test_handover_falls_back_to_number_when_not_reconcilable():
    """Премия не сходится с «Количеством смен» -> в файл идёт число, не формула.

    Премия считается по кассовым сменам iiko, строка «Количество смен» — по
    дневным сменам графика; когда они расходятся, формула соврала бы.
    """
    p = _payload()
    p['employees'][0]['handover_bonus'] = 5250   # не кратно тарифу 500
    ws = build_salary_workbook(p).active
    assert ws['F9'].value == 5250
    # Премия больше, чем «смены x тариф» (дневных смен меньше кассовых)
    p2 = _payload()
    p2['employees'][0]['handover_bonus'] = 7000  # > 11 x 500
    assert build_salary_workbook(p2).active['F9'].value == 7000


def test_pay_falls_back_to_number_on_rounding_drift():
    """«часы x тариф» не воспроизводит сумму страницы -> в файл идёт число.

    Страница считает оплату из неокруглённых часов, поэтому формула от
    округлённых часов иногда расходится с ней на рубль.
    """
    p = _payload()
    p['employees'][0]['hours_by_role']['бармен'] = 92.58   # округлено с 92.5833
    p['employees'][0]['pay_by_role']['бармен'] = 27775     # страница: 92.5833 x 300
    ws = build_salary_workbook(p).active
    assert ws['F6'].value == 27775                          # число, не формула
    assert ws['G6'].value == '=G3*$E$6'                     # у второго формула цела


def test_formula_injection_blocked():
    """Строка с ведущим «=» (имя сотрудника) пишется текстом, а не формулой."""
    p = _payload()
    p['employees'][0]['name'] = '=HYPERLINK("http://evil";"Иванов")'
    ws = build_salary_workbook(p).active
    assert ws['F2'].data_type == 's'      # имя — текст, а не живая формула


def test_empty_employees_no_crash():
    wb = build_salary_workbook({'month': '2026-07', 'roles': [], 'kpi_names': [],
                                'employees': []})
    ws = wb.active
    assert ws['A2'].value == 'Показатель'
    # Без сотрудников ИТОГО-колонка сразу за тарифами, без формул
    assert ws['F2'].value == 'ИТОГО'
    assert ws['F3'].value is None


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
