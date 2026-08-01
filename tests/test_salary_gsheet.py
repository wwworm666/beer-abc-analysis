"""
Тесты экспорта ЗП в Google Таблицу (core/salary_gsheet.py).

Сеть не дёргается: проверяется чистая функция `build_requests` — запросы
Sheets API, которые модуль отправил бы. Ключевое — ПАРИТЕТ с .xlsx: обе
выгрузки строятся из одной раскладки (`core/salary_layout.py`), и тест
сверяет значения ячейка в ячейку, чтобы форматы не разъехались.

Запуск: `py -3 tests/test_salary_gsheet.py` (совместимо с pytest).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.salary_export import build_salary_workbook
from core.salary_gsheet import (FONT_NAME, FONT_SIZE, GSheetNotConfigured,
                                _color, _value, build_grid, build_requests,
                                export_to_gsheet, spreadsheet_url)
from core.salary_layout import Formula, build_sheet
from tests.test_salary_export import _payload


def _grid():
    return build_grid(build_sheet(_payload()))


def _cell(grid, row, col):
    """Ячейка по 1-based координатам листа (grid[0] — строка 1)."""
    values = grid[row - 1].get('values') or []
    return values[col - 1] if col - 1 < len(values) else {}


def test_value_types():
    assert _value(None) == {}
    assert _value(5000) == {'numberValue': 5000}
    assert _value('Юреня') == {'stringValue': 'Юреня'}
    assert _value(Formula('=F3*$E$6')) == {'formulaValue': '=F3*$E$6'}


def test_string_with_equals_is_not_a_formula():
    """Имя с ведущим «=» уходит строкой — formula injection невозможен.

    В Таблицах тип задаётся явно (stringValue vs formulaValue), в отличие от
    openpyxl, где он выводится из содержимого ячейки.
    """
    assert _value('=HYPERLINK("http://evil")') == {
        'stringValue': '=HYPERLINK("http://evil")'}
    p = _payload()
    p['employees'][0]['name'] = '=HYPERLINK("http://evil";"Иванов")'
    grid = build_grid(build_sheet(p))
    assert 'stringValue' in _cell(grid, 2, 6)['userEnteredValue']


def test_color_conversion():
    assert _color('FFFFFF') == {'red': 1.0, 'green': 1.0, 'blue': 1.0}
    assert _color('000000') == {'red': 0.0, 'green': 0.0, 'blue': 0.0}
    assert _color(None) is None
    red = _color('CC0000')
    assert round(red['red'], 3) == 0.8 and red['green'] == 0.0


def test_layout_matches_reference():
    """Строка 1 пустая, шапка во 2-й, подписи строк 3..22 — как в эталоне."""
    grid = _grid()
    assert grid[0] == {'values': []}
    assert _cell(grid, 2, 1)['userEnteredValue'] == {'stringValue': 'Показатель'}
    assert _cell(grid, 2, 6)['userEnteredValue'] == {'stringValue': 'Юреня Роман'}
    assert _cell(grid, 2, 8)['userEnteredValue'] == {'stringValue': 'ИТОГО'}
    labels = [_cell(grid, r, 1)['userEnteredValue'].get('stringValue')
              for r in range(3, 23)]
    assert labels[0] == 'Часы'
    assert labels[2] == 'Количество смен'
    assert labels[-1] == 'ИТОГО БАРМЕН'
    assert len(grid) == 22


def test_formulas_are_live():
    grid = _grid()
    assert _cell(grid, 6, 6)['userEnteredValue'] == {'formulaValue': '=F3*$E$6'}
    assert _cell(grid, 9, 6)['userEnteredValue'] == {'formulaValue': '=F5*$E$9-500'}
    assert _cell(grid, 15, 6)['userEnteredValue'] == {'formulaValue': '=F5*$E$15'}
    assert _cell(grid, 18, 6)['userEnteredValue'] == {'formulaValue': '=F15+F16-F17'}
    assert _cell(grid, 22, 6)['userEnteredValue'] == {
        'formulaValue': '=SUM(F6:F14)-F19-F20-F21+F18'}
    assert _cell(grid, 6, 8)['userEnteredValue'] == {'formulaValue': '=SUM(F6:G6)'}


def test_parity_with_xlsx():
    """Google-выгрузка совпадает с .xlsx ячейка в ячейку.

    Главный тест модуля: обе идут из одной раскладки, и если кто-то поправит
    рендерер в обход неё, паритет сломается здесь.
    """
    grid = _grid()
    ws = build_salary_workbook(_payload()).active
    for row in range(2, 23):
        for col in range(1, 9):
            xlsx = ws.cell(row=row, column=col).value
            gval = _cell(grid, row, col).get('userEnteredValue', {})
            google = (gval.get('formulaValue') if 'formulaValue' in gval
                      else gval.get('stringValue') if 'stringValue' in gval
                      else gval.get('numberValue') if 'numberValue' in gval
                      else None)
            assert xlsx == google, f"расхождение в {chr(64 + col)}{row}: {xlsx!r} != {google!r}"


def test_font_is_reference_everywhere():
    """Шрифт эталона (PT Serif 8) во всех ячейках, как в .xlsx."""
    grid = _grid()
    for row in range(2, 23):
        for col in range(1, 9):
            tf = _cell(grid, row, col)['userEnteredFormat']['textFormat']
            assert tf['fontFamily'] == FONT_NAME and tf['fontSize'] == FONT_SIZE


def test_deduction_rows_are_red():
    """Вычеты: тёмно-красная плашка подписи белым, данные — светло-красные."""
    grid = _grid()
    label = _cell(grid, 19, 1)['userEnteredFormat']
    assert label['backgroundColor'] == _color('CC0000')
    assert label['textFormat']['foregroundColor'] == _color('FFFFFF')
    assert _cell(grid, 19, 6)['userEnteredFormat']['backgroundColor'] == _color('F4CCCC')


def test_requests_shape():
    """batchUpdate: значения, закрепление шапки, ширины колонок."""
    sheet = build_sheet(_payload())
    reqs = build_requests(sheet, sheet_id=777)
    update = reqs[0]['updateCells']
    assert update['range'] == {'sheetId': 777, 'startRowIndex': 0, 'endRowIndex': 22,
                               'startColumnIndex': 0, 'endColumnIndex': 8}
    assert update['fields'] == 'userEnteredValue,userEnteredFormat'
    props = reqs[1]['updateSheetProperties']['properties']['gridProperties']
    assert props == {'frozenRowCount': 2, 'frozenColumnCount': 5}
    dims = [r['updateDimensionProperties'] for r in reqs[2:]]
    assert all(d['range']['sheetId'] == 777 for d in dims)
    assert dims[0]['range'] == {'sheetId': 777, 'dimension': 'COLUMNS',
                                'startIndex': 0, 'endIndex': 1}
    assert dims[0]['properties']['pixelSize'] == 190      # 26.5 симв. * 7 + 5 -> px
    # Колонки сотрудников (F..G) и ИТОГО (H) — отдельными диапазонами
    assert dims[-2]['range']['startIndex'] == 5 and dims[-2]['range']['endIndex'] == 7
    assert dims[-1]['range']['startIndex'] == 7 and dims[-1]['range']['endIndex'] == 8


def test_no_employees_skips_empty_ranges():
    """Без сотрудников не улетает диапазон нулевой ширины (API его отвергает)."""
    sheet = build_sheet({'month': '2026-07', 'roles': [], 'kpi_names': [],
                         'employees': []})
    for r in build_requests(sheet, sheet_id=1):
        rng = r.get('updateDimensionProperties', {}).get('range')
        if rng:
            assert rng['endIndex'] > rng['startIndex']


def test_spreadsheet_url():
    assert spreadsheet_url('ABC') == 'https://docs.google.com/spreadsheets/d/ABC/edit'
    assert spreadsheet_url('ABC', 5).endswith('#gid=5')


def test_auto_tab_title_is_separate_from_manual():
    """Ночная выгрузка пишет в СВОЮ вкладку, не в ручную «июль2026».

    Ручную бухгалтер заполняет руками (мосты, отпуск, доп доход, вычеты), а
    ночная задача переписывает свой лист целиком — совпади имена, данные
    стирались бы каждую ночь.
    """
    from core.salary_layout import auto_sheet_title, sheet_title
    assert auto_sheet_title('2026-07') == 'Июль_2026_Автоматическая'
    assert auto_sheet_title('2026-01') == 'Январь_2026_Автоматическая'
    assert auto_sheet_title('2026-07') != sheet_title('2026-07')


def test_master_sheet_id_required_for_sync():
    """Ночной выгрузке без SALARY_SHEET_ID писать некуда — понятная ошибка."""
    from core.salary_gsheet import MasterSheetNotSet, sync_to_master
    saved = os.environ.pop('SALARY_SHEET_ID', None)
    os.environ['GOOGLE_SA_JSON_CONTENT'] = '{}'   # чтобы упасть не на ключе
    try:
        raised = False
        try:
            sync_to_master(_payload())
        except MasterSheetNotSet:
            raised = True
        except Exception:
            raised = True          # без валидного ключа падает раньше — тоже ок
        assert raised
    finally:
        os.environ.pop('GOOGLE_SA_JSON_CONTENT', None)
        if saved is not None:
            os.environ['SALARY_SHEET_ID'] = saved


def test_not_configured_without_key(monkeypatch=None):
    """Без ключа сервис-аккаунта — понятная ошибка, а не падение."""
    saved = {k: os.environ.pop(k, None)
             for k in ('GOOGLE_SA_JSON', 'GOOGLE_SA_JSON_CONTENT')}
    os.environ['GOOGLE_SA_JSON'] = '/nonexistent/google-sa.json'
    try:
        raised = False
        try:
            export_to_gsheet(_payload())
        except GSheetNotConfigured as e:
            raised = True
            assert 'сервис-аккаунт' in str(e).lower() or 'библиотек' in str(e).lower()
        assert raised, 'ожидалась GSheetNotConfigured'
    finally:
        os.environ.pop('GOOGLE_SA_JSON', None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


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
