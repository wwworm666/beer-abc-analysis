"""Конструктор отчётов /explorer — конструктор OLAP-отчётов iiko в сервисе.

Страница и API. Логика — в core/olap_constructor.py (заявка, запросы, сводная),
core/olap_catalog.py (каталог полей), core/olap_export.py (Excel),
core/olap_saved_reports.py (сохранённые отчёты). Контракт и формулы — docs/explorer.md.

Каждый API-маршрут описан инструментом MCP (core/mcp/tools/analytics.py,
analytics_explorer_*): агент строит тот же отчёт, что и страница.
"""
from flask import Blueprint, Response, jsonify, render_template, request

from core import olap_catalog, olap_constructor, olap_export, olap_saved_reports
from core.auth_guard import current_user
from core.olap_client import IikoError
from core.olap_constructor import ConstructorError

explorer_bp = Blueprint('explorer', __name__)

# Поля заявки отчёта (тело POST /api/explorer/report и /api/explorer/export).
REPORT_KEYS = ('report_type', 'rows', 'columns', 'measures', 'filters', 'include_deleted',
               'date_from', 'date_to', 'period', 'format', 'sort', 'order', 'limit', 'having')
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

# Отчёт, который страница показывает при первом открытии (строится по кнопке).
DEFAULT_CONFIG = {
    'report_type': 'SALES',
    'rows': ['DishGroup.TopParent'],
    'columns': ['Store.Name'],
    'measures': ['DishDiscountSumInt', 'UniqOrderId'],
    'filters': [{'field': fid, 'op': 'in', 'values': list(values)}
                for fid, values in olap_constructor.DELETION_GUARDS],
    'include_deleted': True,
    'period': {'preset': 'last_week'},
}


def _error(error):
    """ConstructorError / IikoError / ValueError -> JSON-ответ с кодом."""
    if isinstance(error, ConstructorError):
        body = {'error': error.message, 'code': error.code}
        body.update(error.extra)
        return jsonify(body), error.status
    if isinstance(error, IikoError):
        return jsonify({'error': error.message, 'code': 'iiko'}), error.status
    return jsonify({'error': str(error), 'code': 'bad_request'}), 400


def _payload():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ConstructorError('Нужно тело JSON с заявкой отчёта.')
    unknown = sorted(set(body) - set(REPORT_KEYS))
    if unknown:
        raise ConstructorError('Неизвестные поля заявки: ' + ', '.join(unknown) +
                               '. Допустимы: ' + ', '.join(REPORT_KEYS) + '.')
    return {key: body.get(key) for key in REPORT_KEYS if key in body}


def _author() -> str:
    user = current_user() or {}
    name = user.get('display_name') or user.get('login') or 'неизвестно'
    return name + (' (агент)' if user.get('via_mcp') else '')


def _flag(name: str) -> bool:
    return str(request.args.get(name) or '').strip().lower() in ('1', 'true', 'yes')


@explorer_bp.route('/explorer')
def explorer_page():
    """Страница конструктора."""
    bootstrap = {
        'report_types': [{'id': rt, 'title': olap_catalog.REPORT_TYPE_TITLES[rt],
                          'hint': olap_catalog.REPORT_TYPE_HINTS[rt]}
                         for rt in olap_catalog.REPORT_TYPES],
        'periods': olap_constructor.period_table(),
        'default': DEFAULT_CONFIG,
        'guarded_types': list(olap_constructor.GUARDED_TYPES),
        'guard_filters': DEFAULT_CONFIG['filters'],
        'limits': {'rows': olap_constructor.MAX_ROW_FIELDS,
                   'columns': olap_constructor.MAX_COLUMN_FIELDS,
                   'measures': olap_constructor.MAX_MEASURES,
                   'filters': olap_constructor.MAX_FILTERS,
                   'leaves': olap_constructor.PIVOT_MAX_LEAVES,
                   'recommended_fields': olap_constructor.RECOMMENDED_FIELDS},
    }
    return render_template('explorer.html', bootstrap=bootstrap)


@explorer_bp.route('/api/explorer/columns')
def explorer_columns():
    """Каталог полей типа отчёта (живой iiko, запасная копия — если iiko недоступен)."""
    try:
        report_type = olap_constructor.parse_report_type(
            {'report_type': request.args.get('report_type')})
        catalog = olap_catalog.get_catalog(report_type, refresh=_flag('refresh'))
        return jsonify(catalog.to_json(q=request.args.get('q') or '',
                                       tag=request.args.get('tag') or '',
                                       compact=_flag('compact')))
    except (ConstructorError, IikoError, ValueError) as error:
        return _error(error)


@explorer_bp.route('/api/explorer/values')
def explorer_values():
    """Значения поля за период — для списка в фильтре."""
    try:
        report_type = olap_constructor.parse_report_type(
            {'report_type': request.args.get('report_type')})
        field_id = (request.args.get('field') or '').strip()
        if not field_id:
            raise ConstructorError('field: id поля обязателен.')
        period = {key: request.args.get(key) for key in ('date_from', 'date_to', 'period')
                  if request.args.get(key)}
        limit_raw = request.args.get('limit')
        limit = olap_constructor.VALUES_MAX
        if limit_raw:
            if not limit_raw.isdigit() or not 1 <= int(limit_raw) <= olap_constructor.VALUES_MAX:
                raise ConstructorError('limit: целое от 1 до ' +
                                       str(olap_constructor.VALUES_MAX) + '.')
            limit = int(limit_raw)
        return jsonify(olap_constructor.field_values(report_type, field_id, period,
                                                     q=request.args.get('q') or '', limit=limit))
    except (ConstructorError, IikoError, ValueError) as error:
        return _error(error)


@explorer_bp.route('/api/explorer/report', methods=['POST'])
def explorer_report():
    """Построить отчёт: format 'pivot' — сводная страницы, 'flat' — список строк."""
    try:
        return jsonify(olap_constructor.run_report(_payload()))
    except (ConstructorError, IikoError, ValueError) as error:
        return _error(error)


@explorer_bp.route('/api/explorer/export', methods=['POST'])
def explorer_export():
    """Тот же отчёт файлом Excel: листы «Отчёт», «Данные», «Параметры»."""
    try:
        content, filename = olap_export.export_report(_payload())
    except (ConstructorError, IikoError, ValueError) as error:
        return _error(error)
    return Response(content, mimetype=XLSX_MIME, headers={
        'Content-Disposition': 'attachment; filename="' + filename + '"',
        'Content-Length': str(len(content)),
    })


@explorer_bp.route('/api/explorer/presets')
def explorer_presets():
    """Отчёты, сохранённые в iikoOffice, — в виде конфигураций конструктора."""
    try:
        return jsonify(olap_constructor.iiko_presets(refresh=_flag('refresh')))
    except (ConstructorError, IikoError, ValueError) as error:
        return _error(error)


@explorer_bp.route('/api/explorer/saved')
def explorer_saved_list():
    """Отчёты, сохранённые в сервисе."""
    try:
        return jsonify({'reports': olap_saved_reports.list_reports()})
    except (ConstructorError, ValueError) as error:
        return _error(error)


@explorer_bp.route('/api/explorer/saved', methods=['POST'])
def explorer_saved_save():
    """Сохранить отчёт: без id — новый, с id — заменить существующий."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error(ConstructorError('Нужно тело JSON: {name, config, id?}.'))
    report_id = body.get('id')
    try:
        record = olap_saved_reports.save_report(body.get('name'), body.get('config'), _author(),
                                                report_id=None if report_id in (None, '') else report_id)
        return jsonify({'report': record})
    except (ConstructorError, ValueError) as error:
        return _error(error)


@explorer_bp.route('/api/explorer/saved/<report_id>', methods=['DELETE'])
def explorer_saved_delete(report_id):
    """Удалить сохранённый отчёт."""
    try:
        return jsonify({'deleted': olap_saved_reports.delete_report(report_id)})
    except (ConstructorError, ValueError) as error:
        return _error(error)
