"""Выгрузка отчёта конструктора в Excel (POST /api/explorer/export).

Что это
    Тот же отчёт, что на странице /explorer, файлом .xlsx из трёх листов:

    «Отчёт»      — сводная как на экране: поля строк отдельными колонками, группы с
                   итогами (жирным, с отступом уровня), для каждого столбца — показатели,
                   затем «Итого» по строке; внизу общий итог. Итоги — по тем же правилам,
                   что на странице (core/olap_constructor.py, «Итоги»).
    «Данные»     — все строки ответа iiko плоской таблицей (разрезы и показатели) с
                   автофильтром: для своих сводных в Excel.
    «Параметры»  — тип отчёта, период, фильтры словами, правило итогов и тела запросов
                   к iiko: по ним любую цифру можно воспроизвести в iikoOffice.

Пределы
    Строк данных не больше EXPORT_MAX_ROWS (core/olap_constructor.py, 200 000). Лист
    «Отчёт» строится, пока строк сводной не больше EXPORT_PIVOT_MAX_LEAVES (50 000);
    больше — на листе объяснение, данные всё равно на листе «Данные». Книга пишется в
    режиме write_only: на 200 000 строк обычный режим openpyxl съел бы сотни мегабайт.

Форматы чисел: деньги — два знака с разделителем разрядов, количество — до трёх
знаков, проценты iiko (доля 0..1) — процентным форматом Excel, длительности (секунды)
— [ч]:мм:сс, даты — ДД.ММ.ГГГГ.

Текст из iiko пишется только как текст (_safe_cell): названия, комментарии и причины
удаления вводит персонал. Строка «=…» без этого стала бы формулой Excel (неверное
значение или HYPERLINK-инъекция), а управляющий символ (\\x0b) уронил бы выгрузку.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from io import BytesIO
from typing import Any, List, Optional, Tuple

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from core.olap_catalog import Catalog, Field
from core.olap_constructor import (BLANK_LABEL, EMPTY_LABEL, EXPORT_MAX_ROWS,
                                   EXPORT_PIVOT_MAX_LEAVES, ConstructorError, ReportSpec,
                                   build_pivot, execute, norm_key, report_meta, to_number)

NUMBER_FORMATS = {
    'MONEY': '#,##0.00',
    'AMOUNT': '#,##0.###',
    'INTEGER': '#,##0',
    'PERCENT': '0.00%',
    'DURATION_IN_SECONDS': '[h]:mm:ss',
}
BOLD = Font(bold=True)
HEADER = Font(bold=True)


def _safe_cell(ws, value) -> WriteOnlyCell:
    """Ячейка, в которой строка остаётся строкой: без управляющих символов и не формулой."""
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub('', value)
    cell = WriteOnlyCell(ws, value=value)
    if isinstance(value, str) and cell.data_type == 'f':
        cell.data_type = 's'
    return cell


def _dim_value(value, item: Optional[Field]):
    """Значение разреза для ячейки: подпись кода, дата датой, пусто — «(пусто)»."""
    if value is None:
        return EMPTY_LABEL
    if value == '':
        return BLANK_LABEL
    if item is not None:
        label = item.enum_label(value)
        if label:
            return label
        if item.type == 'DATE' and isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return value
        if item.type == 'DATETIME' and isinstance(value, str):
            try:
                return datetime.fromisoformat(value[:19])
            except ValueError:
                return value
    return value


def _dim_format(item: Optional[Field]) -> Optional[str]:
    if item is None:
        return None
    if item.type == 'DATE':
        return 'DD.MM.YYYY'
    if item.type == 'DATETIME':
        return 'DD.MM.YYYY HH:MM:SS'
    return None


def _measure_cell(ws, value, item: Field, bold: bool = False) -> WriteOnlyCell:
    number = to_number(value)
    if number is not None and item.type == 'DURATION_IN_SECONDS':
        number = number / 86400.0          # секунды -> доля суток для формата времени Excel
    if number is None and isinstance(value, str) and value:
        # Показатель-не число (время последней сервисной печати): дата — датой, иначе текст.
        shown = _dim_value(value, item) if item.type in ('DATE', 'DATETIME') else value
        cell = _safe_cell(ws, shown)
        if isinstance(shown, datetime):
            cell.number_format = 'DD.MM.YYYY HH:MM:SS'
        if bold:
            cell.font = BOLD
        return cell
    cell = WriteOnlyCell(ws, value=number)
    fmt = NUMBER_FORMATS.get(item.type)
    if fmt:
        cell.number_format = fmt
    if bold:
        cell.font = BOLD
    return cell


def _text_cell(ws, value, bold: bool = False, fmt: Optional[str] = None,
               indent: int = 0) -> WriteOnlyCell:
    cell = _safe_cell(ws, value)
    if bold:
        cell.font = BOLD
    if fmt:
        cell.number_format = fmt
    if indent:
        cell.alignment = Alignment(indent=indent)
    return cell


def _set_widths(ws, widths: List[int]) -> None:
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = max(8, min(60, width))


def _plain(value, item: Optional[Field]) -> str:
    """Значение разреза одной строкой (заголовок столбца)."""
    shown = _dim_value(value, item)
    if isinstance(shown, datetime):
        return shown.strftime('%d.%m.%Y %H:%M:%S')
    if isinstance(shown, date):
        return shown.strftime('%d.%m.%Y')
    return str(shown)


def _col_label(ck: list, col_items: List[Field]) -> str:
    return ' · '.join(_plain(value, col_items[i]) for i, value in enumerate(ck))


def _write_pivot(ws, spec: ReportSpec, catalog: Catalog, pivot: dict) -> None:
    row_items = [catalog.get(fid) for fid in spec.rows]
    col_items = [catalog.get(fid) for fid in spec.columns]
    meas_items = [catalog.get(fid) for fid in spec.measures]
    col_keys = pivot['columns']
    widths = [max(14, len(item.name) + 2) for item in row_items] or [14]
    measure_widths = [max(12, len(item.name) + 2) for item in meas_items]
    if col_keys:
        for _ck in col_keys + [None]:
            widths += measure_widths
    else:
        widths += measure_widths
    _set_widths(ws, widths)
    lead = len(row_items) or 1

    if col_keys:
        top = [_text_cell(ws, '') for _ in range(lead)]
        for ck in col_keys:
            top.append(_text_cell(ws, _col_label(ck, col_items), bold=True))
            top += [_text_cell(ws, '') for _ in range(len(meas_items) - 1)]
        top.append(_text_cell(ws, 'Итого', bold=True))
        ws.append(top)
    header = [_text_cell(ws, item.name, bold=True) for item in row_items] or \
        [_text_cell(ws, '', bold=True)]
    for _ck in (col_keys + [None]) if col_keys else [None]:
        header += [_text_cell(ws, item.name, bold=True) for item in meas_items]
    ws.append(header)

    def values_cells(node: dict, bold: bool) -> list:
        cells = []
        if col_keys:
            for cell in node.get('c') or [None] * len(col_keys):
                for i, item in enumerate(meas_items):
                    cells.append(_measure_cell(ws, cell[i] if cell else None, item, bold))
        for i, item in enumerate(meas_items):
            cells.append(_measure_cell(ws, node['t'][i], item, bold))
        return cells

    def walk(node: dict, depth: int, path: list) -> None:
        for child in node.get('ch') or []:
            key = child.get('k')
            item = row_items[depth]
            is_group = 'ch' in child
            label = _dim_value(key, item)
            line = []
            for level in range(lead):
                if level < depth:
                    line.append(_text_cell(ws, _dim_value(path[level], row_items[level]),
                                           fmt=_dim_format(row_items[level])))
                elif level == depth:
                    line.append(_text_cell(ws, label, bold=is_group, fmt=_dim_format(item),
                                           indent=0))
                else:
                    line.append(_text_cell(ws, ''))
            ws.append(line + values_cells(child, is_group))
            if is_group:
                walk(child, depth + 1, path + [key])

    if spec.rows:
        walk(pivot['tree'], 0, [])
    total = [_text_cell(ws, 'Итого', bold=True)] + [_text_cell(ws, '') for _ in range(lead - 1)]
    ws.append(total + values_cells(pivot['tree'], True))


def _write_data(ws, spec: ReportSpec, catalog: Catalog, data: List[dict]) -> None:
    dim_items = [catalog.get(fid) for fid in spec.dims]
    meas_items = [catalog.get(fid) for fid in spec.measures]
    _set_widths(ws, [max(14, len(item.name) + 2) for item in dim_items + meas_items])
    ws.append([_text_cell(ws, item.name, bold=True) for item in dim_items + meas_items])
    for row in data:
        line = [_text_cell(ws, _dim_value(norm_key(row.get(item.id)), item),
                           fmt=_dim_format(item)) for item in dim_items]
        line += [_measure_cell(ws, row.get(item.id), item) for item in meas_items]
        ws.append(line)
    ws.auto_filter.ref = 'A1:' + get_column_letter(max(1, len(dim_items) + len(meas_items))) + \
        str(len(data) + 1)


def _write_params(ws, meta: dict, catalog: Catalog, spec: ReportSpec,
                  pivot_note: Optional[str]) -> None:
    _set_widths(ws, [28, 110])
    names = lambda ids: ', '.join(catalog.get(fid).name for fid in ids) or '—'  # noqa: E731
    lines = [
        ('Отчёт', meta['title'] + ' (' + meta['report_type'] + ')'),
        ('Период', meta['date_from'] + ' — ' + meta['date_to'] + ' включительно, по полю «' +
         meta['date_field_name'] + '»' + (' (' + meta['period_title'] + ')'
                                          if meta.get('period_title') else '')),
        ('Строки', names(spec.rows)),
        ('Столбцы', names(spec.columns)),
        ('Показатели', names(spec.measures)),
        ('Фильтры', '; '.join(meta['filters']) or 'нет'),
        ('Итоги сложением строк', names(meta['totals']['sum'])),
        ('Итоги из iiko (buildSummary)', names(meta['totals']['server'])),
        ('Данные iiko на', (meta.get('fetched_at') or '—') + ' МСК'),
        ('Выгружено', meta['generated_at'] + ' МСК'),
    ]
    if pivot_note:
        lines.append(('Лист «Отчёт»', pivot_note))
    if meta.get('catalog_note'):
        lines.append(('Каталог полей', meta['catalog_note']))
    for key, value in lines:
        ws.append([_text_cell(ws, key, bold=True), _text_cell(ws, value)])
    ws.append([])
    for request in meta['requests']:
        ws.append([_text_cell(ws, 'Запрос iiko: ' + request['name'], bold=True),
                   _text_cell(ws, request['purpose'])])
        ws.append([_text_cell(ws, 'POST /v2/reports/olap'),
                   _text_cell(ws, json.dumps(request['body'], ensure_ascii=False))])


def export_report(payload: dict) -> Tuple[bytes, str]:
    """Построить отчёт по заявке и вернуть (содержимое .xlsx, имя файла)."""
    spec, catalog, steps, bodies, answers = execute(payload, 'pivot')
    main = answers.get('cells') or answers['main']
    data = main.get('data') or []
    if len(data) > EXPORT_MAX_ROWS:
        raise ConstructorError(
            'В отчёте ' + str(len(data)) + ' строк — больше, чем помещается в выгрузку (' +
            str(EXPORT_MAX_ROWS) + '). Сузьте период или уберите поле.', code='too_many_rows')
    pivot, pivot_note = None, None
    try:
        pivot = build_pivot(spec, catalog, answers, max_leaves=EXPORT_PIVOT_MAX_LEAVES,
                            max_cells=EXPORT_MAX_ROWS * 20)
    except ConstructorError as error:
        if error.code not in ('too_many_rows', 'too_many_cells'):
            raise
        pivot_note = ('Сводная не построена: ' + error.message + ' Все строки — на листе '
                      '«Данные».')
    meta = report_meta(spec, catalog, steps, bodies, answers)
    book = Workbook(write_only=True)
    sheet = book.create_sheet('Отчёт')
    if pivot is not None:
        _write_pivot(sheet, spec, catalog, pivot)
    else:
        sheet.append([_safe_cell(sheet, pivot_note)])
    _write_data(book.create_sheet('Данные'), spec, catalog, data)
    _write_params(book.create_sheet('Параметры'), meta, catalog, spec, pivot_note)
    buffer = BytesIO()
    book.save(buffer)
    filename = ('olap_' + spec.report_type.lower() + '_' + spec.date_from.isoformat() + '_' +
                spec.date_to.isoformat() + '.xlsx')
    return buffer.getvalue(), filename
