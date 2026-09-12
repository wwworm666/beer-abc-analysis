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
поставки и дней доставки поставщика (справочник core/supplier_directory); её можно переопределить
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
    POST /api/orders/<id>/close         — {note?} закрыть без сверки (posted вручную)
    POST /api/orders/<id>/cancel        — {note?}

Поставщик черновика приводится к каноническому имени справочника
(core/supplier_directory), чтобы «Фасовка» с сырой категорией iiko и «К заказу»
с именем справочника писали в один черновик. Нечитаемый файл заказов — 503
с кодом orders_unavailable у всех эндпоинтов (запись поверх запрещена).
"""
import math
from datetime import date
from functools import wraps

from flask import Blueprint, jsonify, request

from core import msk_time
from core.auth_guard import current_user
from core.order_store import (DEFAULT_HISTORY_DAYS, ALL_STATUSES, MAX_QTY, OrderStoreUnavailable,
                              get_order_store, order_text, overdue_days, unmatched_days)
from core.supplier_calendar import ORDER_OVERDUE_GRACE_DAYS, next_delivery_date
from core.supplier_directory import get_supplier_directory
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


def _today() -> date:
    """Московская дата (сервер живёт в UTC, бары работают за полночь)."""
    return msk_time.today()


def _store_guard(view):
    """Нечитаемый файл заказов — 503 с кодом, а не 500 и не тихая запись поверх."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except OrderStoreUnavailable as e:
            return _error(str(e), 503, code='orders_unavailable')
    return wrapper


def _canonical_supplier(raw) -> str:
    """Имя поставщика через справочник: «ИП Ромашка» и «Ромашка» — один черновик."""
    return get_supplier_directory().view().resolve(str(raw or '').strip())


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
    if not math.isfinite(qty) or qty < 0:
        raise ValueError('qty должно быть числом >= 0')
    if qty > MAX_QTY:
        raise ValueError(f'qty не может быть больше {int(MAX_QTY)}')
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
    today = _today()
    result['overdue_days'] = overdue_days(order, today)
    result['unmatched_days'] = unmatched_days(order, today)
    return result


def _expected_for(supplier: str) -> str:
    """Ожидаемая дата поставки при отправке сегодня по календарю поставщика."""
    params = _supplier_params(supplier)
    return next_delivery_date(_today(), params['lead_time_days'], params['delivery_weekdays']).isoformat()


def _draft_view(draft: dict) -> dict:
    """Черновик для фронта: позиции списком, отсортированы по бару и названию.

    Текст черновика уже содержит желаемую дату поставки: управляющий копирует
    его в чат до нажатия «Отправлено», и поставщик должен видеть дату.
    """
    items = sorted(draft.get('items', {}).values(), key=lambda i: (i.get('bar') or '', i.get('name') or ''))
    expected_at = _expected_for(draft.get('supplier') or '')
    view = {
        'supplier': draft.get('supplier'),
        'updated_at': draft.get('updated_at'),
        'updated_by': draft.get('updated_by'),
        'updated_by_name': draft.get('updated_by_name') or draft.get('updated_by'),
        'expected_at': expected_at,
        'items': items,
        'total_qty': sum(float(i.get('qty') or 0) for i in items),
    }
    view['text'] = order_text({'supplier': draft.get('supplier'), 'items': items, 'expected_at': expected_at},
                              BARS, expected_label='Желаемая поставка')
    return view


def _drafts_response(store):
    drafts = [_draft_view(d) for d in store.get_drafts().values()]
    drafts.sort(key=lambda d: d['supplier'] or '')
    return jsonify({'drafts': drafts, 'bars': list(BARS)})


@orders_bp.route('/api/orders/draft', methods=['GET'])
@_store_guard
def get_drafts():
    return _drafts_response(get_order_store())


@orders_bp.route('/api/orders/draft', methods=['POST'])
@_store_guard
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
    store.set_draft_item(_canonical_supplier(supplier), item, current_user())
    return _drafts_response(store)


@orders_bp.route('/api/orders/draft/batch', methods=['POST'])
@_store_guard
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
        by_supplier.setdefault(_canonical_supplier(supplier), []).append(item)
    store = get_order_store()
    user = current_user()
    for supplier, items in by_supplier.items():
        store.set_draft_items(supplier, items, user)
    return _drafts_response(store)


@orders_bp.route('/api/orders/draft/clear', methods=['POST'])
@_store_guard
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
@_store_guard
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
        expected_at = _expected_for(supplier)
    note = body.get('note')
    store = get_order_store()
    try:
        order = store.send(supplier, current_user(), expected_at=expected_at, note=note)
    except ValueError as e:
        return _error(str(e), 409)
    return jsonify({'order': _with_text(order)})


@orders_bp.route('/api/orders', methods=['GET'])
@_store_guard
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
@_store_guard
def get_order(order_id):
    order = get_order_store().get_order(order_id)
    if not order:
        return _error(f'Заказ {order_id} не найден', 404)
    return jsonify({'order': _with_text(order)})


@orders_bp.route('/api/orders/<order_id>/received', methods=['POST'])
@_store_guard
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
        if not math.isfinite(qty) or qty < 0 or qty > MAX_QTY:
            return _error(f'позиция {idx}: qty должно быть числом от 0 до {int(MAX_QTY)}')
        received.append({'product_id': str(raw.get('product_id') or '').strip(),
                         'bar': str(raw.get('bar') or '').strip(), 'qty': qty})
    store = get_order_store()
    try:
        order = store.mark_received(order_id, current_user(), received_items=received, note=body.get('note'))
    except KeyError:
        return _error(f'Заказ {order_id} не найден', 404)
    except ValueError as e:
        return _error(str(e), 400 if 'нет позиций' in str(e) else 409)
    return jsonify({'order': _with_text(order)})


@orders_bp.route('/api/orders/<order_id>/close', methods=['POST'])
@_store_guard
def close_order(order_id):
    """«Закрыть без сверки»: открытый заказ → posted вручную (накладная не совпадёт)."""
    body = _json_body()
    store = get_order_store()
    try:
        order = store.close(order_id, current_user(), note=body.get('note'))
    except KeyError:
        return _error(f'Заказ {order_id} не найден', 404)
    except ValueError as e:
        return _error(str(e), 409)
    return jsonify({'order': _with_text(order)})


@orders_bp.route('/api/orders/<order_id>/cancel', methods=['POST'])
@_store_guard
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
