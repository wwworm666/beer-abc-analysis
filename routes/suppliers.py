"""API справочника поставщиков (этап 3 редизайна «Заказы и остатки», 2026-09-10).

Справочник — core/supplier_directory.py: каноническое имя, алиасы написаний
category из iiko, срок поставки в днях доставки, дни доставки (пн = 0),
кратность для фасовки/кухни, самовывоз, заметка. Редактируется на странице
/suppliers; читается доской заказа (routes/stocks) и отправкой заказа
(routes/orders) для группировки, формулы и ожидаемой даты поставки.

Эндпоинты:
    GET    /api/suppliers                 — справочник + категории номенклатуры,
                                            которые ни к кому не привязаны
    PUT    /api/suppliers/<name>          — создать/обновить {aliases, lead_time_days,
                                            delivery_weekdays, pack_size, self_pickup,
                                            note, rename_to?}
    DELETE /api/suppliers/<name>          — удалить
    POST   /api/suppliers/<name>/aliases  — {alias} добавить одно написание
"""
from flask import Blueprint, jsonify, request

from core.auth_guard import current_user
from core.supplier_directory import (DEFAULT_LEAD_TIME_DAYS, DEFAULT_PACK_SIZE, NO_SUPPLIER,
                                     categories_in_use, get_supplier_directory, normalize_name)
from core.supplier_calendar import DEFAULT_DELIVERY_WEEKDAYS

suppliers_bp = Blueprint('suppliers', __name__)

EDITABLE_FIELDS = ('aliases', 'lead_time_days', 'delivery_weekdays', 'pack_size', 'self_pickup', 'note')


def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _error(message: str, status: int = 400):
    return jsonify({'error': message}), status


def _unmapped_categories(view):
    """Категории номенклатуры без записи в справочнике (для подсказки алиасов)."""
    try:
        from core.stock_snapshot import get_stocks_nomenclature
        nomenclature = get_stocks_nomenclature()
    except Exception as e:  # noqa: BLE001 — справочник должен открываться и без iiko
        print(f"[SUPPLIERS] nomenclature unavailable: {e}")
        return [], False
    if not nomenclature:
        return [], False
    counts = categories_in_use(nomenclature)
    result = []
    for cat, n in counts.items():
        if cat == NO_SUPPLIER:
            continue
        resolved = view.resolve(cat)
        if view.get(resolved) is None:
            result.append({'category': cat, 'products': n})
    result.sort(key=lambda r: (-r['products'], normalize_name(r['category'])))
    return result, True


def _payload(directory, with_categories: bool = True):
    view = directory.view()
    unmapped, nomenclature_ok = _unmapped_categories(view) if with_categories else ([], False)
    return {
        'suppliers': directory.list(),
        'unmapped_categories': unmapped,
        'nomenclature_available': nomenclature_ok,
        'defaults': {'lead_time_days': DEFAULT_LEAD_TIME_DAYS, 'pack_size': DEFAULT_PACK_SIZE,
                     'delivery_weekdays': list(DEFAULT_DELIVERY_WEEKDAYS)},
        'stored': directory.is_stored(),
    }


@suppliers_bp.route('/api/suppliers', methods=['GET'])
def list_suppliers():
    return jsonify(_payload(get_supplier_directory()))


@suppliers_bp.route('/api/suppliers/<path:name>', methods=['PUT'])
def upsert_supplier(name):
    body = _json_body()
    fields = {k: body[k] for k in EDITABLE_FIELDS if k in body}
    rename_to = body.get('rename_to')
    directory = get_supplier_directory()
    try:
        record = directory.upsert(name, fields, current_user(), rename_to=rename_to or None)
    except ValueError as e:
        return _error(str(e))
    payload = _payload(directory)
    payload['supplier'] = record
    return jsonify(payload)


@suppliers_bp.route('/api/suppliers/<path:name>', methods=['DELETE'])
def delete_supplier(name):
    directory = get_supplier_directory()
    if not directory.delete(name):
        return _error(f'Поставщик «{name}» не найден', 404)
    return jsonify(_payload(directory))


@suppliers_bp.route('/api/suppliers/<path:name>/aliases', methods=['POST'])
def add_alias(name):
    body = _json_body()
    alias = str(body.get('alias') or '').strip()
    if not alias:
        return _error('alias обязателен')
    directory = get_supplier_directory()
    try:
        record = directory.add_alias(name, alias, current_user())
    except KeyError:
        return _error(f'Поставщик «{name}» не найден', 404)
    except ValueError as e:
        return _error(str(e))
    payload = _payload(directory)
    payload['supplier'] = record
    return jsonify(payload)
