"""Баланс и потери кухни в рублях по закупке — зеркало «Баланса фасовки».

Что это
-------
По проводкам склада iiko (OLAP TRANSACTIONS, группа «ЕДА») считает за период:
приход по накладным, перемещения, списано при продаже, списано актами,
недостача по инвентаризациям, изменение остатка — и раскладку расхождений по
продуктам склада. Формула баланса та же, что у фасовки и кегов
(core/packaging_losses.py, core/draft_kegs.py), только единица — рубли.

Почему рубли, а не штуки
------------------------
Решение владельца 2026-09-27: «в рублях по всему складу кухни». На складе кухни
лежат и товары, которые продаются как есть (орехи, джерки, чипсы — в штуках), и
ингредиенты блюд в кг, штуках и литрах. Штуки с килограммами не складываются, а
деньги складываются: каждая проводка iiko несёт сумму по себестоимости
(Sum.Outgoing — расход, Sum.Incoming — приход). Количество в своей единице
сохраняется по каждому продукту — для строки расхождений («3,2 кг»).

Чем отличается от фасовки
-------------------------
- Единица — рубли по закупке; строки не отбрасываются по единице измерения.
- «Продано» — себестоимость списанного при продаже по складу: у блюд это
  ингредиенты по техкартам, у товаров — сам товар.
- Связка «продукт склада — позиция продаж» есть только у товаров, которые
  продаются как есть (Product.Id совпадает с DishId). Ингредиенты блюд своей
  позиции не имеют — это не ошибка, а устройство кухни; в диагностике они
  считаются отдельно.
- Сверка «касса против склада» — в рублях: себестоимость проданного по кассе
  (позиции плюс модификаторы) против списанного при продаже по складу. Доля
  покрытия показывает, какую часть закупки проданного объясняют продукты
  группы «ЕДА»: если ингредиенты лежат в другой группе номенклатуры, покрытие
  будет заметно ниже 100%.

Файлы
-----
- core/kitchen_analysis.py — вызывает build_kitchen_losses из build()
- core/kitchen_loader.py — сырьё (проводки + продажи) под одним ключом кэша
- docs/kitchen.md — формулы и оговорки
"""

from core.draft_kegs import TT_INVENTORY, TT_INVOICE, TT_SOLD, TT_TRANSFER, TT_WRITEOFF

# Единица баланса кухни. Строка, а не символ: так же, как 'шт' у фасовки,
# она уходит в ответ и печатается страницей.
RUB_UNIT = '₽'

# Типы проводок, из которых складывается баланс. Те же пять, что у кегов и
# фасовки, — «изменение остатка» на трёх страницах означает одно и то же.
BALANCE_TYPES = (TT_SOLD, TT_WRITEOFF, TT_INVENTORY, TT_INVOICE, TT_TRANSFER)

# Рублёвые поля агрегата по продукту. Порядок важен для детерминированного сложения.
_FIELDS = ('sold', 'writeoff', 'inventory_out', 'inventory_in',
           'invoice_in', 'transfer_in', 'transfer_out')
# Количества в единице продукта — только для подписи строки расхождений.
_QTY_FIELDS = ('writeoff_qty', 'inventory_out_qty', 'inventory_in_qty')


def _num(value):
    """Число из ответа OLAP: None и мусор -> 0.0."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _new_entry(product_id, name, unit):
    entry = {field: 0.0 for field in _FIELDS + _QTY_FIELDS}
    entry['product_id'] = product_id
    entry['product_name'] = name
    entry['unit'] = unit or ''
    return entry


def collect_stock(transactions, bar_name=None):
    """Агрегаты по (склад, продукт) из строк проводок, в рублях.

    Возвращает (stock, diagnostics): stock — {(bar, product_id): entry},
    diagnostics — какие типы проводок в баланс не вошли и на какую сумму.
    bar_name сужает разрез до одного склада (Account.Name); None — все склады.
    """
    stock = {}
    ignored_types = {}

    for row in transactions or []:
        product_id = row.get('Product.Id')
        if not product_id:
            continue
        bar = row.get('Account.Name')
        if bar_name and bar != bar_name:
            continue
        name = row.get('Product.Name') or product_id
        unit = row.get('Product.MeasureUnit')
        out = _num(row.get('Sum.Outgoing'))
        inc = _num(row.get('Sum.Incoming'))
        out_qty = _num(row.get('Amount.Out'))
        in_qty = _num(row.get('Amount.In'))

        kind = row.get('TransactionType')
        if kind not in BALANCE_TYPES:
            # Не в балансе, но виден: сколько строк и на какую сумму ушло и пришло.
            if out or inc:
                item = ignored_types.setdefault(kind or '', {'rows': 0, 'out': 0.0, 'in': 0.0})
                item['rows'] += 1
                item['out'] += out
                item['in'] += inc
            continue

        entry = stock.get((bar, product_id))
        if entry is None:
            entry = stock[(bar, product_id)] = _new_entry(product_id, name, unit)

        # Раскладка та же, что у фасовки (core/packaging_losses.py), в рублях.
        if kind == TT_SOLD:
            entry['sold'] += out
        elif kind == TT_WRITEOFF:
            entry['writeoff'] += out
            entry['writeoff_qty'] += out_qty
        elif kind == TT_INVENTORY:
            entry['inventory_out'] += out
            entry['inventory_in'] += inc
            entry['inventory_out_qty'] += out_qty
            entry['inventory_in_qty'] += in_qty
        elif kind == TT_INVOICE:
            entry['invoice_in'] += inc
        elif kind == TT_TRANSFER:
            entry['transfer_in'] += inc
            entry['transfer_out'] += out

    diagnostics = {'ignored_types': dict(sorted(ignored_types.items()))}
    return stock, diagnostics


def merge_by_product(stock):
    """Схлопнуть склады: ключ — продукт. Порядок сложения фиксирован."""
    merged = {}
    for (_bar, product_id), entry in sorted(stock.items(), key=lambda kv: (kv[0][1], kv[0][0] or '')):
        target = merged.get(product_id)
        if target is None:
            merged[product_id] = dict(entry)
            continue
        for field in _FIELDS + _QTY_FIELDS:
            target[field] += entry[field]
    return merged


def _position_indexes(positions):
    """Два индекса для связки продукта с позицией: по GUID и по имени."""
    by_guid = {}
    by_name = {}
    for position in positions:
        for dish_id in position.get('DishIds') or ():
            by_guid.setdefault(dish_id, position['Id'])
        if position.get('DishId'):
            by_guid.setdefault(position['DishId'], position['Id'])
        name = str(position.get('Beer') or '').strip()
        if name:
            by_name.setdefault(name, position['Id'])
    return by_guid, by_name


def _pct(part, whole):
    return (part / whole * 100) if whole > 0 else None


def build_kitchen_losses(transactions, bar_name, positions, sold_cost_by_register,
                         modifiers_cost=0.0):
    """Блок losses для ответа /api/kitchen. Мутирует positions: добавляет
    позициям, которые продаются как есть, поля движений склада в рублях.

    sold_cost_by_register — себестоимость проданных позиций по кассе
    (totals.cost), modifiers_cost — себестоимость отданных модификаторов: они не
    позиции, но списываются со склада, поэтому входят в сверку.

    Поля позиции после вызова (рубли по закупке): SoldCostStock, WriteoffRub,
    InventoryNetRub, InventoryShortRub, InventorySurplusRub, LossRub и проценты
    к списанному при продаже по складу (None, если по складу не продано).

    Недостача и излишек считаются ПО КАЖДОМУ БАРУ, как у фасовки: излишек в баре
    B не отменяет пропажу в баре A. Баланс сверху остаётся нетто по сети.
    """
    for position in positions:
        position['SoldCostStock'] = 0.0
        position['WriteoffRub'] = 0.0
        position['InventoryNetRub'] = 0.0
        position['InventoryShortRub'] = 0.0
        position['InventorySurplusRub'] = 0.0
        position['LossRub'] = 0.0
        position['LossPercentOfSold'] = None
        position['WriteoffPercentOfSold'] = None
        position['InventoryShortPercentOfSold'] = None
        position['InventorySurplusPercentOfSold'] = None

    stock, diagnostics = collect_stock(transactions, bar_name)
    merged = merge_by_product(stock)
    by_guid, by_name = _position_indexes(positions)
    by_id = {p['Id']: p for p in positions}
    has_guids = any(p.get('DishId') for p in positions)

    def position_of(product_id, product_name):
        position_id = by_guid.get(product_id)
        if position_id is not None:
            return position_id, 'guid'
        position_id = by_name.get(str(product_name).strip())
        return position_id, ('name' if position_id is not None else None)

    sold = sum(e['sold'] for e in merged.values())
    writeoff = sum(e['writeoff'] for e in merged.values())
    inventory_out = sum(e['inventory_out'] for e in merged.values())
    inventory_in = sum(e['inventory_in'] for e in merged.values())
    invoice_in = sum(e['invoice_in'] for e in merged.values())
    transfer_in = sum(e['transfer_in'] for e in merged.values())
    transfer_out = sum(e['transfer_out'] for e in merged.values())
    inventory_net = inventory_out - inventory_in

    # Недостача и излишек по барам — в рублях и в единице продукта. Для позиции
    # — сначала нетто по всем её GUID внутри бара, потом по барам (как у фасовки).
    product_split = {}      # product_id -> [недостача ₽, излишек ₽, недостача ед., излишек ед.]
    position_bar_net = {}   # (position_id, bar) -> нетто ₽
    for (bar, product_id), entry in sorted(stock.items(),
                                           key=lambda kv: (kv[0][1], kv[0][0] or '')):
        net = entry['inventory_out'] - entry['inventory_in']
        net_qty = entry['inventory_out_qty'] - entry['inventory_in_qty']
        split = product_split.setdefault(product_id, [0.0, 0.0, 0.0, 0.0])
        split[0] += max(net, 0.0)
        split[1] += max(-net, 0.0)
        split[2] += max(net_qty, 0.0)
        split[3] += max(-net_qty, 0.0)
        position_id, _ = position_of(product_id, entry['product_name'])
        if position_id is not None:
            key = (position_id, bar)
            position_bar_net[key] = position_bar_net.get(key, 0.0) + net
    for (position_id, _bar), net in sorted(position_bar_net.items(),
                                           key=lambda kv: (kv[0][0], kv[0][1] or '')):
        position = by_id[position_id]
        position['InventoryShortRub'] += max(net, 0.0)
        position['InventorySurplusRub'] += max(-net, 0.0)

    by_item = []
    linked_products = 0
    ingredient_products = 0
    for entry in merged.values():
        position_id, matched_by = position_of(entry['product_id'], entry['product_name'])
        if position_id is None:
            ingredient_products += 1
        else:
            linked_products += 1
            position = by_id[position_id]
            position['SoldCostStock'] += entry['sold']
            position['WriteoffRub'] += entry['writeoff']
            position['InventoryNetRub'] += entry['inventory_out'] - entry['inventory_in']

        net = entry['inventory_out'] - entry['inventory_in']
        short, surplus, short_qty, surplus_qty = product_split.get(
            entry['product_id'], (max(net, 0.0), max(-net, 0.0), 0.0, 0.0))
        loss = entry['writeoff'] + short

        # Только продукты с расхождениями, без обрезки: сколько показать сразу,
        # решает страница.
        if entry['writeoff'] > 0 or short > 0 or surplus > 0:
            by_item.append({
                'ProductId': entry['product_id'],
                'ProductName': entry['product_name'],
                'Unit': entry['unit'],
                'PositionId': position_id,
                'MatchedBy': matched_by,
                'SoldRub': entry['sold'],
                'WriteoffRub': entry['writeoff'],
                'InventoryNetRub': net,
                'InventoryShortRub': short,
                'InventorySurplusRub': surplus,
                'LossRub': loss,
                'LossPercentOfSold': _pct(loss, entry['sold']),
                'WriteoffQty': entry['writeoff_qty'],
                'InventoryShortQty': short_qty,
                'InventorySurplusQty': surplus_qty,
            })

    for position in positions:
        position['LossRub'] = position['WriteoffRub'] + position['InventoryShortRub']
        stock_sold = position['SoldCostStock']
        position['LossPercentOfSold'] = _pct(position['LossRub'], stock_sold)
        position['WriteoffPercentOfSold'] = _pct(position['WriteoffRub'], stock_sold)
        position['InventoryShortPercentOfSold'] = _pct(position['InventoryShortRub'], stock_sold)
        position['InventorySurplusPercentOfSold'] = _pct(position['InventorySurplusRub'], stock_sold)

    # По величине расхождения в рублях; тай-брейк по имени и GUID, чтобы порядок
    # не зависел от порядка строк OLAP.
    by_item.sort(key=lambda k: (-(k['WriteoffRub'] + k['InventoryShortRub']
                                  + k['InventorySurplusRub']),
                                k['ProductName'], k['ProductId']))

    register_cost = sold_cost_by_register + modifiers_cost
    diagnostics.update({
        # Себестоимость проданного по кассе: позиции плюс отданные модификаторы.
        'sold_cost_by_register': register_cost,
        'modifiers_cost': modifiers_cost,
        'sold_by_stock': sold,
        'sold_delta': sold - register_cost,
        # Какую долю закупки проданного объясняет склад группы «ЕДА».
        'coverage_percent': _pct(sold, register_cost),
        'linked_products': linked_products,
        'ingredient_products': ingredient_products,
        'match_mode': 'guid' if has_guids else 'name',
        'has_transactions': bool(transactions),
    })

    return {
        'unit': RUB_UNIT,
        'received': invoice_in + transfer_in,
        'invoice_in': invoice_in,
        'transfer_in': transfer_in,
        'transfer_out': transfer_out,
        'sold': sold,
        'writeoff': writeoff,
        'inventory_out': inventory_out,
        'inventory_in': inventory_in,
        'inventory_net': inventory_net,
        # Та же формула, что у кегов и фасовки: приход минус весь расход.
        'balance': (invoice_in + transfer_in
                    - sold - writeoff - inventory_net - transfer_out),
        'writeoff_percent_of_sold': (writeoff / sold * 100) if sold > 0 else 0.0,
        'inventory_percent_of_sold': (inventory_net / sold * 100) if sold > 0 else 0.0,
        'spent': sold + writeoff + inventory_net + transfer_out,
        'by_item': by_item,
        'diagnostics': diagnostics,
    }
