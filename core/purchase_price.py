"""Цена единицы товара для суммы заказа: последняя приходная накладная, иначе себестоимость остатка.

Зачем. Минимальный заказ поставщика задаётся в рублях (docs/suppliers.md), а доска
«К заказу» считает штуки, килограммы и литры: чтобы понять, набирается ли минимум,
нужна цена единицы. iiko не отдаёт прайс поставщика, но в снимке сети
(core/stock_snapshot) есть два честных источника:

    invoice — строки приходных накладных (storeOperations, documentType
              INCOMING_INVOICE, incoming true): sum / amount — цена, по которой товар
              реально пришёл, в основной единице товара (кеги — литры), как введена в
              накладной (НДС отдельно не выделяется: в выгрузке sumNds = 0);
    stock   — остатки balance/stores: sum / amount — себестоимость остатка, средняя по
              партиям, лежащим на складах.

По реальной выгрузке за 30 дней накладная с ценой есть у 265 из 566 продаваемых
товаров, поэтому запасной источник обязателен; без накладной и без остатка цена
неизвестна (None): такая позиция в сумму заказа не входит и подписывается «без цены».

Правила (детерминированно, тот же снимок — та же цена на доске любого бара):
    1. Накладные считаются по всей сети: цена поставщика одна на все бары. Берутся
       только строки с amount > 0 и sum > 0 (бонусная строка с нулевой суммой,
       сторно и возврат — не цена).
    2. Побеждает самая поздняя дата накладной; несколько строк одной даты (две
       накладные, два склада) складываются: price = Σsum / Σamount. Строка без
       читаемой даты пропускается — порядок событий по ней неизвестен.
    3. Накладной нет → остаток: Σsum / Σamount по записям balances с amount > 0 и
       sum > 0 по всей сети (остаток одного бара может быть нулевым или отрицательным,
       а цена нужна и тогда).
    4. Цена округляется до копеек (PRICE_DECIMALS = 2).
"""
from datetime import date
from typing import Dict, Iterable, Optional

from core.stock_consumption import is_outgoing, parse_ops_date

PRICE_DECIMALS = 2                        # копейки
INCOMING_INVOICE = 'INCOMING_INVOICE'     # documentType приходной накладной iiko
SOURCE_INVOICE = 'invoice'
SOURCE_STOCK = 'stock'


def _num(value) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0.0
    return n if n == n and n not in (float('inf'), float('-inf')) else 0.0


def invoice_prices(operations: Iterable[dict],
                   product_ids: Optional[Iterable[str]] = None) -> Dict[str, dict]:
    """{product_id: {price, source: 'invoice', date: date}} по последней накладной в окне."""
    wanted = set(product_ids) if product_ids is not None else None
    latest: Dict[str, dict] = {}
    for record in operations:
        if record.get('documentType') != INCOMING_INVOICE or is_outgoing(record) is not False:
            continue
        product_id = record.get('product')
        if not product_id or (wanted is not None and product_id not in wanted):
            continue
        amount, total = _num(record.get('amount')), _num(record.get('sum'))
        if amount <= 0 or total <= 0:
            continue
        op_date = parse_ops_date(record.get('date'))
        if op_date is None:
            continue
        current = latest.get(product_id)
        if current is None or op_date > current['date']:
            latest[product_id] = {'date': op_date, 'amount': amount, 'sum': total}
        elif op_date == current['date']:
            current['amount'] += amount
            current['sum'] += total
    return {
        pid: {'price': round(v['sum'] / v['amount'], PRICE_DECIMALS), 'source': SOURCE_INVOICE, 'date': v['date']}
        for pid, v in latest.items()
    }


def stock_prices(balances: Iterable[dict],
                 product_ids: Optional[Iterable[str]] = None) -> Dict[str, dict]:
    """{product_id: {price, source: 'stock', date: None}} — себестоимость остатка по сети."""
    wanted = set(product_ids) if product_ids is not None else None
    totals: Dict[str, list] = {}
    for balance in balances:
        product_id = balance.get('product')
        if not product_id or (wanted is not None and product_id not in wanted):
            continue
        amount, total = _num(balance.get('amount')), _num(balance.get('sum'))
        if amount <= 0 or total <= 0:
            continue
        acc = totals.setdefault(product_id, [0.0, 0.0])
        acc[0] += amount
        acc[1] += total
    return {
        pid: {'price': round(s / a, PRICE_DECIMALS), 'source': SOURCE_STOCK, 'date': None}
        for pid, (a, s) in totals.items()
    }


def resolve_prices(operations: Iterable[dict], balances: Iterable[dict],
                   product_ids: Iterable[str]) -> Dict[str, Optional[dict]]:
    """Цена единицы для каждого товара: накладная, иначе остаток, иначе None.

    Значение: {price: float, source: 'invoice' | 'stock', date: 'YYYY-MM-DD' | None}.
    """
    ids = list(product_ids)
    by_invoice = invoice_prices(operations, ids)
    by_stock = stock_prices(balances, ids)
    result: Dict[str, Optional[dict]] = {}
    for pid in ids:
        found = by_invoice.get(pid) or by_stock.get(pid)
        if found is None:
            result[pid] = None
            continue
        d = found.get('date')
        result[pid] = {'price': found['price'], 'source': found['source'],
                       'date': d.isoformat() if isinstance(d, date) else None}
    return result


def line_sum(price: Optional[float], qty) -> Optional[float]:
    """Сумма позиции = price × qty до копеек; None, если цены нет."""
    if price is None:
        return None
    return round(float(price) * _num(qty), PRICE_DECIMALS)
