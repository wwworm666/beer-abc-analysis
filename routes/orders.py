"""API заказов поставщикам (этап 1 редизайна «Заказы и остатки», 2026-09-10).

Заказ — серверная сущность (core/order_store.py): общий черновик на всех
управляющих, история отправленных заказов, статусы «отправлено» → «приехало»
→ «оприходовано» (последний ставится автоматически по приходной накладной
iiko при пересчёте доски заказа, см. routes/stocks.get_order_board).

Черновик хранится по поставщикам: одна карточка = одно сообщение в чат
поставщику по всем барам сразу. Бар в черновике обязателен и должен быть
конкретным (не «Общая»): заказ приезжает на склад конкретного бара.

Ожидаемая дата поставки при отправке считается календарём поставок
(core/supplier_calendar.next_delivery_date) от сегодняшнего дня и срока
поставки поставщика (routes/stocks.SUPPLIER_PARAMS); её можно переопределить
в запросе. Дата ориентировочная: поставщики задерживают на 1–2 дня.

Эндпоинты:
    GET  /api/orders/draft              — все черновики + текст для чата
    POST /api/orders/draft              — одна позиция {supplier, product_id, bar, qty, ...}
    POST /api/orders/draft/batch        — {items: [...]} (кнопка «Применить рекомендации»)
    POST /api/orders/draft/clear        — {supplier?} — очистить черновик(и)
    POST /api/orders/send               — {supplier, expected_at?, note?} → заказ + текст
    GET  /api/orders?days=30            — открытые заказы всегда + закрытые за days дней
    GET  /api/orders/<id>               — один заказ + текст
    POST /api/orders/<id>/received      — {items?: [{product_id, bar, qty}], note?}
    POST /api/orders/<id>/cancel        — {note?}
"""
from datetime import date

from flask import Blueprint, jsonify, request

from core.auth_guard import current_user
from core.order_store import (DEFAULT_HISTORY_DAYS, ALL_STATUSES, get_order_store,
                              order_text)
from core.supplier_calendar import ORDER_OVERDUE_GRACE_DAYS, next_delivery_date
from extensions import BARS
from routes.stocks import _supplier_params

orders_bp = Blueprint('orders', __name__)

MAX_HISTORY_DAYS = 365
ALLOWED_KINDS = ('bottle', 'draft', 'kitchen')


def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _error(message: str, status: int = 400, **extra):
    payload = {'error': message}
    payload.update(extra)
    return jsonify(payload), status


def _validate_item(raw: dict) -> dict:
    """Проверить позицию черновика; ValueError с понятным текстом."""
    if not isinstance(raw, dict):
        raise ValueError('позиция должна быть объектом')
    product_id = str(raw.get('product_id') or '').strip()
    if not product_id:
        raise ValueError('product_id обязателен')
    bar = str(raw.get('bar') or '').strip()
    if bar not in BARS:
        raise ValueError(f'бар «{bar}» неизвестен или не конкретный; допустимы: {", ".join(BARS)}')
    try:
        qty = float(raw.get('qty', 0))
    except (TypeError, ValueError):
        raise ValueError('qty должно быть числом')
    if qty != qty or qty < 0:
        raise ValueError('qty должно быть числом >= 0')
    kind = raw.get('kind') or None
    if kind is not None and kind not in ALLOWED_KINDS:
        raise ValueError(f'kind должен быть одним из {", ".join(ALLOWED_KINDS)}')
    return {
        'product_id': product_id,
        'bar': bar,
        'qty': qty,
        'name': raw.get('name'),
        'unit': raw.get('unit'),
        'kind': kind,
        'recommended': raw.get('recommended'),
    }


def _with_text(order: dict) -> dict:
    result = dict(order)
    result['text'] = order_text(order, BARS)
    return result


def _draft_view(draft: dict) -> dict:
    """Черновик для фронта: позиции списком, отсортированы по бару и названию."""
    items = sorted(draft.get('items', {}).values(), key=lambda i: (i.get('bar') or '', i.get('name') or ''))
    view = {
        'supplier': draft.get('supplier'),
        'updated_at': draft.get('updated_at'),
        'updated_by': draft.get('updated_by'),
        'items': items,
        'total_qty': sum(float(i.get('qty') or 0) for i in items),
    }
    view['text'] = order_text({'supplier': draft.get('supplier'), 'items': items}, BARS)
    return view


def _drafts_response(store):
    drafts = [_draft_view(d) for d in store.get_drafts().values()]
    drafts.sort(key=lambda d: d['supplier'] or '')
    return jsonify({'drafts': drafts, 'bars': list(BARS)})


@orders_bp.route('/api/orders/draft', methods=['GET'])
def get_drafts():
    return _drafts_response(get_order_store())


@orders_bp.route('/api/orders/draft', methods=['POST'])
def set_draft_item():
    body = _json_body()
    supplier = str(body.get('supplier') or '').strip()
    if not supplier:
        return _error('supplier обязателен')
    try:
        item = _validate_item(body)
    except ValueError as e:
        return _error(str(e))
    store = get_order_store()
    store.set_draft_item(supplier, item, current_user())
    return _drafts_response(store)


@orders_bp.route('/api/orders/draft/batch', methods=['POST'])
def set_draft_batch():
    """Много позиций разом; каждая несёт своего поставщика (supplier)."""
    body = _json_body()
    raw_items = body.get('items')
    if not isinstance(raw_items, list) or not raw_items:
        return _error('items должен быть непустым списком')
    by_supplier = {}
    for idx, raw in enumerate(raw_items):
        supplier = str((raw or {}).get('supplier') or '').strip() if isinstance(raw, dict) else ''
        if not supplier:
            return _error(f'позиция {idx}: supplier обязателен')
        try:
            item = _validate_item(raw)
        except ValueError as e:
            return _error(f'позиция {idx}: {e}')
        by_supplier.setdefault(supplier, []).append(item)
    store = get_order_store()
    user = current_user()
    for supplier, items in by_supplier.items():
        store.set_draft_items(supplier, items, user)
    return _drafts_response(store)


@orders_bp.route('/api/orders/draft/clear', methods=['POST'])
def clear_draft():
    body = _json_body()
    supplier = body.get('supplier')
    supplier = str(supplier).strip() if supplier else None
    store = get_order_store()
    removed = store.clear_drafts(supplier)
    response = _drafts_response(store)
    payload = response.get_json()
    payload['removed'] = removed
    return jsonify(payload)


@orders_bp.route('/api/orders/send', methods=['POST'])
def send_order():
    body = _json_body()
    supplier = str(body.get('supplier') or '').strip()
    if not supplier:
        return _error('supplier обязателен')
    expected_at = body.get('expected_at')
    if expected_at:
        try:
            date.fromisoformat(str(expected_at))
        except ValueError:
            return _error('expected_at должен быть датой YYYY-MM-DD')
        expected_at = str(expected_at)[:10]
    else:
        lead = _supplier_params(supplier)['lead_time_days']
        expected_at = next_delivery_date(date.today(), lead).isoformat()
    note = body.get('note')
    store = get_order_store()
    try:
        order = store.send(supplier, current_user(), expected_at=expected_at, note=note)
    except ValueError as e:
        return _error(str(e), 409)
    return jsonify({'order': _with_text(order)})


@orders_bp.route('/api/orders', methods=['GET'])
def list_orders():
    try:
        days = int(request.args.get('days', DEFAULT_HISTORY_DAYS))
    except ValueError:
        return _error('days должен быть целым числом')
    days = max(1, min(MAX_HISTORY_DAYS, days))
    status = request.args.get('status')
    statuses = None
    if status:
        statuses = [s for s in status.split(',') if s]
        unknown = [s for s in statuses if s not in ALL_STATUSES]
        if unknown:
            return _error(f'неизвестный статус: {", ".join(unknown)}', known_statuses=list(ALL_STATUSES))
    orders = get_order_store().list_orders(days=days, statuses=statuses)
    return jsonify({'orders': [_with_text(o) for o in orders], 'days': days,
                    'overdue_grace_days': ORDER_OVERDUE_GRACE_DAYS})


@orders_bp.route('/api/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    order = get_order_store().get_order(order_id)
    if not order:
        return _error(f'Заказ {order_id} не найден', 404)
    return jsonify({'order': _with_text(order)})


@orders_bp.route('/api/orders/<order_id>/received', methods=['POST'])
def mark_received(order_id):
    body = _json_body()
    raw_items = body.get('items') or []
    if not isinstance(raw_items, list):
        return _error('items должен быть списком')
    received = []
    for idx, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            return _error(f'позиция {idx}: должна быть объектом')
        try:
            qty = float(raw.get('qty', 0))
        except (TypeError, ValueError):
            return _error(f'позиция {idx}: qty должно быть числом')
        received.append({'product_id': raw.get('product_id'), 'bar': raw.get('bar'), 'qty': qty})
    store = get_order_store()
    try:
        order = store.mark_received(order_id, current_user(), received_items=received, note=body.get('note'))
    except KeyError:
        return _error(f'Заказ {order_id} не найден', 404)
    except ValueError as e:
        return _error(str(e), 409)
    return jsonify({'order': _with_text(order)})


@orders_bp.route('/api/orders/<order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    body = _json_body()
    store = get_order_store()
    try:
        order = store.cancel(order_id, current_user(), note=body.get('note'))
    except KeyError:
        return _error(f'Заказ {order_id} не найден', 404)
    except ValueError as e:
        return _error(str(e), 409)
    return jsonify({'order': _with_text(order)})
