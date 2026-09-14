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
from functools import wraps

from flask import Blueprint, jsonify, request

from core.auth_guard import current_user
from core.order_store import OrderStoreUnavailable, get_order_store
from core.supplier_directory import (DEFAULT_LEAD_TIME_DAYS, DEFAULT_PACK_SIZE, MIN_LEAD_TIME_DAYS,
                                     MAX_LEAD_TIME_DAYS, NO_SUPPLIER, SupplierDirectoryUnavailable,
                                     categories_in_use, clean_name, get_supplier_directory, normalize_name)
from core.supplier_calendar import DEFAULT_DELIVERY_WEEKDAYS

suppliers_bp = Blueprint('suppliers', __name__)

EDITABLE_FIELDS = ('aliases', 'lead_time_days', 'delivery_weekdays', 'pack_size', 'self_pickup', 'note')


def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _error(message: str, status: int = 400, **extra):
    payload = {'error': message}
    payload.update(extra)
    return jsonify(payload), status


def _directory_guard(view):
    """Нечитаемый файл справочника — 503 с кодом, а не 500 и не запись поверх."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except SupplierDirectoryUnavailable as e:
            return _error(str(e), 503, code='suppliers_unavailable')
    return wrapper


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
                     'delivery_weekdays': list(DEFAULT_DELIVERY_WEEKDAYS),
                     'min_lead_time_days': MIN_LEAD_TIME_DAYS, 'max_lead_time_days': MAX_LEAD_TIME_DAYS},
        'stored': directory.is_stored(),
    }


@suppliers_bp.route('/api/suppliers', methods=['GET'])
def list_suppliers():
    return jsonify(_payload(get_supplier_directory()))


@suppliers_bp.route('/api/suppliers/<path:name>', methods=['PUT'])
@_directory_guard
def upsert_supplier(name):
    name = clean_name(name)
    body = _json_body()
    fields = {k: body[k] for k in EDITABLE_FIELDS if k in body}
    rename_to = clean_name(body.get('rename_to')) or None
    directory = get_supplier_directory()
    before = directory.get(name)
    try:
        record = directory.upsert(name, fields, current_user(), rename_to=rename_to)
    except ValueError as e:
        return _error(str(e))
    payload = _payload(directory)
    payload['supplier'] = record
    # Переименование: черновики и заказы под старым именем переезжают под новое,
    # иначе они остались бы «по умолчанию» и отдельной карточкой.
    if before and before['name'] != record['name']:
        try:
            payload['orders_renamed'] = get_order_store().rename_supplier(before['name'], record['name'])
        except OrderStoreUnavailable as e:
            print(f"[SUPPLIERS] orders not renamed: {e}")
            payload['orders_renamed'] = None
            payload['warning'] = 'Поставщик переименован, но файл заказов недоступен: черновики и заказы остались под старым именем'
    return jsonify(payload)


@suppliers_bp.route('/api/suppliers/<path:name>', methods=['DELETE'])
@_directory_guard
def delete_supplier(name):
    directory = get_supplier_directory()
    if not directory.delete(clean_name(name)):
        return _error(f'Поставщик «{name}» не найден', 404)
    return jsonify(_payload(directory))


@suppliers_bp.route('/api/suppliers/<path:name>/aliases', methods=['POST'])
@_directory_guard
def add_alias(name):
    body = _json_body()
    alias = str(body.get('alias') or '').strip()
    if not alias:
        return _error('alias обязателен')
    directory = get_supplier_directory()
    try:
        record = directory.add_alias(clean_name(name), alias, current_user())
    except KeyError:
        return _error(f'Поставщик «{name}» не найден', 404)
    except ValueError as e:
        return _error(str(e))
    payload = _payload(directory)
    payload['supplier'] = record
    return jsonify(payload)
