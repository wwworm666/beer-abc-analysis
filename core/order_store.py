"""Заказы поставщикам: общий черновик на сеть и отправленные заказы.

Зачем. До 2026-09-10 корзина заказа жила в памяти вкладки браузера и терялась
при перезагрузке, результат уходил только в CSV, а страница не помнила, что уже
заказано, и назавтра просила то же самое (главная причина неудобства по
docs/planning/stocks-order-redesign-2026-09-10.md). Здесь заказ — объект на
сервере: три управляющих видят один черновик и одну историю.

Хранение. Один JSON-файл orders.json на постоянном томе (/kultura) или в data/
локально (core/storage_paths.get_data_path); запись атомарная, read-modify-write
под cross-worker lock (core/json_store), как у заметок к собраниям.

Модель.
    drafts[supplier] = {supplier, updated_at, updated_by,
                        items: {"<product_id>|<bar>": {product_id, bar, name, unit,
                                kind, qty, recommended, updated_at, updated_by}}}
    orders[] = {id, supplier, status, items: [{product_id, bar, name, unit, kind, qty,
                received_qty?, posted_at?}], sent_at, sent_by, expected_at,
                received_at?, received_by?, posted_at?, cancelled_at?, cancelled_by?,
                note?}

Статусы заказа: sent → received (вручную, «Приехало») → posted (автоматически,
когда в iiko появилась приходная накладная по позиции и складу не раньше даты
отправки) ; cancelled. Пока заказ не posted, его количество вычитается из
рекомендации как «в пути / приехало, ещё не оприходовано»: бухгалтерия проводит
накладные с задержкой (решение владельца 2026-09-10).
"""
import json
import os
import threading
import uuid
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional

from core.json_store import atomic_write_json, file_lock
from core.storage_paths import get_data_path

STATUS_SENT = 'sent'
STATUS_RECEIVED = 'received'
STATUS_POSTED = 'posted'
STATUS_CANCELLED = 'cancelled'
OPEN_STATUSES = (STATUS_SENT, STATUS_RECEIVED)     # вычитаются из рекомендации
ALL_STATUSES = (STATUS_SENT, STATUS_RECEIVED, STATUS_POSTED, STATUS_CANCELLED)
INCOMING_INVOICE = 'INCOMING_INVOICE'              # documentType прихода в storeOperations
DEFAULT_HISTORY_DAYS = 30
SCHEMA_VERSION = 1

_WEEKDAYS_RU = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')


def draft_key(product_id: str, bar: str) -> str:
    return f'{product_id}|{bar}'


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _user_login(user: Optional[dict]) -> str:
    if not user:
        return 'unknown'
    return user.get('login') or user.get('display_name') or 'unknown'


def _user_name(user: Optional[dict]) -> str:
    if not user:
        return 'unknown'
    return user.get('display_name') or user.get('login') or 'unknown'


def _qty(value) -> float:
    try:
        q = float(value)
    except (TypeError, ValueError):
        return 0.0
    if q != q:  # NaN
        return 0.0
    return max(0.0, q)


def _fmt_qty(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f'{value:g}'


def _fmt_date(value: Optional[str]) -> str:
    if not value:
        return ''
    try:
        d = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f'{_WEEKDAYS_RU[d.weekday()]} {d.strftime("%d.%m")}'


def order_text(order: dict, bar_order: Optional[Iterable[str]] = None) -> str:
    """Текст заказа для чата поставщику: по барам, «название — количество единица».

    Одинаков для черновика и отправленного заказа; ожидаемая поставка помечена
    как ориентировочная (поставщики задерживают на 1–2 дня).
    """
    items = list(order.get('items') or [])
    order_index = {b: i for i, b in enumerate(bar_order or [])}
    bars = sorted({it.get('bar') or '' for it in items},
                  key=lambda b: (order_index.get(b, len(order_index)), b))
    lines = [f"Заказ, {_fmt_date(order.get('sent_at') or _now())}",
             f"Поставщик: {order.get('supplier') or ''}"]
    for bar in bars:
        lines.append(f'{bar}:')
        for it in sorted((i for i in items if (i.get('bar') or '') == bar), key=lambda i: i.get('name') or ''):
            lines.append(f"- {it.get('name') or it.get('product_id')} — {_fmt_qty(_qty(it.get('qty')))} {it.get('unit') or 'шт'}")
    if order.get('expected_at'):
        lines.append(f"Ожидаемая поставка: {_fmt_date(order['expected_at'])} (ориентировочно)")
    return '\n'.join(lines)


class OrderStore:
    def __init__(self, data_file: Optional[str] = None):
        self.data_file = data_file or get_data_path('orders.json')
        self._lock = threading.Lock()
        self._lock_path = self.data_file + '.lock'

    # ----- низкоуровневое -----------------------------------------------

    def _empty(self) -> dict:
        return {'version': SCHEMA_VERSION, 'drafts': {}, 'orders': []}

    def _load(self) -> dict:
        if not os.path.exists(self.data_file):
            return self._empty()
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[ORDERS] cannot read {self.data_file}: {e}")
            return self._empty()
        if not isinstance(data, dict):
            return self._empty()
        data.setdefault('version', SCHEMA_VERSION)
        data.setdefault('drafts', {})
        data.setdefault('orders', [])
        return data

    def _save(self, data: dict) -> None:
        atomic_write_json(self.data_file, data)

    # ----- черновики -----------------------------------------------------

    def get_drafts(self) -> Dict[str, dict]:
        return self._load()['drafts']

    def get_draft(self, supplier: str) -> Optional[dict]:
        return self._load()['drafts'].get(supplier)

    @staticmethod
    def _normalize_item(item: dict) -> dict:
        product_id = str(item.get('product_id') or '').strip()
        bar = str(item.get('bar') or '').strip()
        if not product_id or not bar:
            raise ValueError('product_id и bar обязательны')
        return {
            'product_id': product_id,
            'bar': bar,
            'name': str(item.get('name') or product_id),
            'unit': str(item.get('unit') or 'шт'),
            'kind': item.get('kind') or None,
            'qty': _qty(item.get('qty')),
            'recommended': item.get('recommended'),
        }

    def set_draft_items(self, supplier: str, items: Iterable[dict], user: Optional[dict]) -> Optional[dict]:
        """Положить/обновить позиции черновика поставщика; qty <= 0 удаляет позицию.

        Возвращает черновик поставщика или None, если он опустел и удалён.
        """
        supplier = (supplier or '').strip()
        if not supplier:
            raise ValueError('supplier обязателен')
        normalized = [self._normalize_item(it) for it in items]
        stamp = _now()
        login = _user_login(user)
        with self._lock, file_lock(self._lock_path):
            data = self._load()
            draft = data['drafts'].get(supplier) or {'supplier': supplier, 'items': {}}
            for it in normalized:
                key = draft_key(it['product_id'], it['bar'])
                if it['qty'] <= 0:
                    draft['items'].pop(key, None)
                    continue
                it['updated_at'] = stamp
                it['updated_by'] = login
                draft['items'][key] = it
            if draft['items']:
                draft['updated_at'] = stamp
                draft['updated_by'] = login
                data['drafts'][supplier] = draft
            else:
                data['drafts'].pop(supplier, None)
                draft = None
            self._save(data)
        return draft

    def set_draft_item(self, supplier: str, item: dict, user: Optional[dict]) -> Optional[dict]:
        return self.set_draft_items(supplier, [item], user)

    def clear_drafts(self, supplier: Optional[str] = None) -> int:
        """Удалить черновик поставщика или все черновики; возвращает число удалённых."""
        with self._lock, file_lock(self._lock_path):
            data = self._load()
            if supplier is None:
                removed = len(data['drafts'])
                data['drafts'] = {}
            else:
                removed = 1 if data['drafts'].pop(supplier, None) is not None else 0
            if removed:
                self._save(data)
        return removed

    def draft_quantities(self, bar: Optional[str] = None) -> Dict[str, float]:
        """{product_id: qty} по всем черновикам для бара (None — сумма по барам)."""
        result: Dict[str, float] = {}
        for draft in self._load()['drafts'].values():
            for it in draft['items'].values():
                if bar is not None and it.get('bar') != bar:
                    continue
                result[it['product_id']] = result.get(it['product_id'], 0.0) + _qty(it.get('qty'))
        return result

    # ----- заказы --------------------------------------------------------

    def send(self, supplier: str, user: Optional[dict], expected_at: Optional[str] = None,
             note: Optional[str] = None) -> dict:
        """Превратить черновик поставщика в отправленный заказ."""
        supplier = (supplier or '').strip()
        if expected_at:
            date.fromisoformat(expected_at)  # ValueError на мусор
        with self._lock, file_lock(self._lock_path):
            data = self._load()
            draft = data['drafts'].pop(supplier, None)
            if not draft or not draft.get('items'):
                raise ValueError(f'Черновик поставщика «{supplier}» пуст')
            stamp = _now()
            order = {
                'id': f"ord-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
                'supplier': supplier,
                'status': STATUS_SENT,
                'items': [
                    {'product_id': it['product_id'], 'bar': it['bar'], 'name': it['name'],
                     'unit': it['unit'], 'kind': it.get('kind'), 'qty': _qty(it['qty'])}
                    for it in sorted(draft['items'].values(), key=lambda i: (i['bar'], i['name']))
                ],
                'sent_at': stamp,
                'sent_by': _user_login(user),
                'sent_by_name': _user_name(user),
                'expected_at': expected_at,
                'note': note or None,
            }
            data['orders'].append(order)
            self._save(data)
        return order

    def list_orders(self, days: int = DEFAULT_HISTORY_DAYS,
                    statuses: Optional[Iterable[str]] = None) -> List[dict]:
        """Заказы за последние days дней (по sent_at), новые первыми; открытые — всегда."""
        wanted = set(statuses) if statuses else None
        cutoff = None
        if days is not None and days > 0:
            cutoff = (datetime.now().date().toordinal() - days)
        result = []
        for order in self._load()['orders']:
            if wanted and order.get('status') not in wanted:
                continue
            if cutoff is not None and order.get('status') not in OPEN_STATUSES:
                try:
                    sent_day = date.fromisoformat(order['sent_at'][:10]).toordinal()
                except (KeyError, ValueError):
                    sent_day = cutoff
                if sent_day < cutoff:
                    continue
            result.append(order)
        result.sort(key=lambda o: o.get('sent_at') or '', reverse=True)
        return result

    def get_order(self, order_id: str) -> Optional[dict]:
        for order in self._load()['orders']:
            if order.get('id') == order_id:
                return order
        return None

    def _update(self, order_id: str, mutate) -> dict:
        with self._lock, file_lock(self._lock_path):
            data = self._load()
            for order in data['orders']:
                if order.get('id') == order_id:
                    mutate(order)
                    self._save(data)
                    return order
        raise KeyError(order_id)

    def mark_received(self, order_id: str, user: Optional[dict],
                      received_items: Optional[Iterable[dict]] = None,
                      note: Optional[str] = None) -> dict:
        """«Приехало»: статус received; received_items = [{product_id, bar, qty}] корректируют факт."""
        adjustments = {}
        for it in received_items or []:
            adjustments[draft_key(str(it.get('product_id')), str(it.get('bar')))] = _qty(it.get('qty'))

        def mutate(order):
            if order.get('status') not in OPEN_STATUSES:
                raise ValueError(f"Заказ {order_id} в статусе {order.get('status')}, «приехало» неприменимо")
            for it in order['items']:
                key = draft_key(it['product_id'], it['bar'])
                if key in adjustments:
                    it['received_qty'] = adjustments[key]
            order['status'] = STATUS_RECEIVED
            order['received_at'] = _now()
            order['received_by'] = _user_login(user)
            if note:
                order['note'] = note
        return self._update(order_id, mutate)

    def cancel(self, order_id: str, user: Optional[dict], note: Optional[str] = None) -> dict:
        def mutate(order):
            if order.get('status') == STATUS_POSTED:
                raise ValueError(f'Заказ {order_id} уже оприходован, отменять нечего')
            order['status'] = STATUS_CANCELLED
            order['cancelled_at'] = _now()
            order['cancelled_by'] = _user_login(user)
            if note:
                order['note'] = note
        return self._update(order_id, mutate)

    def open_quantities(self, bar: Optional[str] = None) -> Dict[str, float]:
        """{product_id: qty} по открытым заказам (sent/received) для бара; None — сумма по барам.

        Для received берётся фактическое received_qty, если его ввели.
        """
        result: Dict[str, float] = {}
        for order in self._load()['orders']:
            if order.get('status') not in OPEN_STATUSES:
                continue
            for it in order['items']:
                if bar is not None and it.get('bar') != bar:
                    continue
                if it.get('posted_at'):
                    continue
                qty = it.get('received_qty') if it.get('received_qty') is not None else it.get('qty')
                result[it['product_id']] = result.get(it['product_id'], 0.0) + _qty(qty)
        return result

    def open_orders_for(self, bar: Optional[str] = None) -> Dict[str, List[dict]]:
        """{product_id: [{order_id, supplier, qty, expected_at, status}]} по открытым заказам."""
        result: Dict[str, List[dict]] = {}
        for order in self._load()['orders']:
            if order.get('status') not in OPEN_STATUSES:
                continue
            for it in order['items']:
                if bar is not None and it.get('bar') != bar:
                    continue
                if it.get('posted_at'):
                    continue
                result.setdefault(it['product_id'], []).append({
                    'order_id': order['id'], 'supplier': order['supplier'],
                    'qty': _qty(it.get('received_qty') if it.get('received_qty') is not None else it.get('qty')),
                    'expected_at': order.get('expected_at'), 'status': order['status'],
                })
        return result

    def reconcile_with_operations(self, operations: Iterable[dict],
                                  bar_store_map: Dict[str, str]) -> int:
        """Отметить оприходованные позиции по приходным накладным iiko.

        Позиция считается оприходованной, если в операциях есть приход
        INCOMING_INVOICE по её товару и складу её бара с датой не раньше дня
        отправки заказа. Заказ становится posted, когда оприходованы все позиции.
        Возвращает число изменённых заказов; без изменений файл не пишется.
        """
        invoices: Dict[tuple, List[date]] = {}
        for r in operations:
            if str(r.get('incoming', 'false')).lower() != 'true':
                continue
            if r.get('documentType') != INCOMING_INVOICE:
                continue
            pid, store = r.get('product'), r.get('primaryStore')
            if not pid or not store:
                continue
            try:
                d = datetime.strptime(str(r.get('date')), '%d.%m.%Y').date()
            except (TypeError, ValueError):
                continue
            invoices.setdefault((pid, store), []).append(d)
        if not invoices:
            return 0
        changed = 0
        with self._lock, file_lock(self._lock_path):
            data = self._load()
            for order in data['orders']:
                if order.get('status') not in OPEN_STATUSES:
                    continue
                try:
                    sent_day = date.fromisoformat(order['sent_at'][:10])
                except (KeyError, ValueError):
                    continue
                touched = False
                for it in order['items']:
                    if it.get('posted_at'):
                        continue
                    store = bar_store_map.get(it.get('bar'))
                    dates = [d for d in invoices.get((it['product_id'], store), []) if d >= sent_day]
                    if dates:
                        it['posted_at'] = min(dates).isoformat()
                        touched = True
                if touched:
                    changed += 1
                    if all(it.get('posted_at') for it in order['items']):
                        order['status'] = STATUS_POSTED
                        order['posted_at'] = _now()
            if changed:
                self._save(data)
        return changed


_store: Optional[OrderStore] = None
_store_guard = threading.Lock()


def get_order_store() -> OrderStore:
    """Ленивый синглтон на процесс (файл на томе общий для воркеров)."""
    global _store
    with _store_guard:
        if _store is None:
            _store = OrderStore()
        return _store
