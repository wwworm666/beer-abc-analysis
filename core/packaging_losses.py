"""Баланс и потери фасовки в штуках — зеркало «Баланса кегов» на /draft.

Что это
-------
По проводкам склада iiko (OLAP TRANSACTIONS, группа «Напитки Фасовка») считает
за период: приход по накладным, перемещения, продано через кассу, списано
актами, недостача по инвентаризациям, изменение остатка — и раскладку
расхождений по товарам. Формулы те же, что у кегов (core/draft_kegs.py,
_build_losses), только единица — штуки, а не литры: товар фасовки списывается
при продаже сам, техкарты не нужны.

Чем отличается от розлива
-------------------------
- Единица: строки не в «шт» отбрасываются, но НЕ молча — они уходят в
  диагностику (у розлива «шт» в группе кегов отбрасывались без следа).
- Типы проводок вне пяти базовых (возвраты поставщику, возвраты от гостя)
  в баланс не входят, чтобы формула осталась той же, что у розлива, но
  считаются и показываются — у товаров такие движения реальны.
- Связь «товар склада <-> позиция таблицы продаж»: у розлива это техкарты по
  GUID, здесь товар и блюдо — один элемент номенклатуры, поэтому связка по
  DishId из продаж и Product.Id из проводок; если продажи пришли без DishId
  (вызов без get_packaging_sales_report, старая фикстура), запасной вариант —
  по имени с обрезкой пробелов, и режим сопоставления печатается в диагностике.
- Проценты и суммы считаются здесь, а не в JS: по .claude/CLAUDE.md расчёт
  живёт на сервере, страница только печатает.

Файлы
-----
- core/packaging_analysis.py — вызывает build_losses_block из build()
- core/packaging_loader.py — сырьё (проводки + продажи) под одним ключом кэша
- docs/abc-xyz-analysis.md — формулы и оговорки
"""

from core.draft_kegs import TT_INVENTORY, TT_INVOICE, TT_SOLD, TT_TRANSFER, TT_WRITEOFF

# Единица штучного товара в номенклатуре iiko. Значение то же, что в
# routes/stocks.py (PIECE_UNITS); в выгрузке номенклатуры у 4378 товаров
# фасовки — «шт», у 11 — «кг» (весовые закуски, попавшие в группу).
PIECE_UNIT = 'шт'

# Типы проводок, из которых складывается баланс. Ровно те же пять, что у
# кегов — чтобы «изменение остатка» на двух страницах означало одно и то же.
BALANCE_TYPES = (TT_SOLD, TT_WRITEOFF, TT_INVENTORY, TT_INVOICE, TT_TRANSFER)

# Поля агрегата по товару. Порядок важен для детерминированного сложения.
_FIELDS = ('sold', 'writeoff', 'inventory_out', 'inventory_in',
           'invoice_in', 'transfer_in', 'transfer_out', 'sold_cost')


def _num(value):
    """Число из ответа OLAP: None и мусор -> 0.0."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _new_entry(product_id, name):
    entry = {field: 0.0 for field in _FIELDS}
    entry['product_id'] = product_id
    entry['product_name'] = name
    return entry


def collect_stock(transactions, bar_name=None):
    """Агрегаты по (склад, товар) из строк проводок.

    Возвращает (stock, diagnostics), где stock — {(bar, product_id): entry},
    diagnostics — что отброшено и почему. bar_name сужает разрез до одного
    склада (Account.Name — то поле, которое iiko рекомендует как однозначное);
    None — все склады как есть.
    """
    stock = {}
    non_piece = {}
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
        out = _num(row.get('Amount.Out'))
        inc = _num(row.get('Amount.In'))

        if unit != PIECE_UNIT:
            # Складывать штуки с килограммами нельзя, а переводить не по чему.
            # Показываем, что именно выпало и сколько, вместо молчаливого нуля.
            if out or inc:
                item = non_piece.setdefault(product_id, {
                    'ProductId': product_id,
                    'ProductName': name,
                    'Unit': unit or '',
                    'Out': 0.0,
                    'In': 0.0,
                })
                item['Out'] += out
                item['In'] += inc
            continue

        kind = row.get('TransactionType')
        if kind not in BALANCE_TYPES:
            # Не в балансе, но виден: сколько строк и сколько штук ушло и пришло.
            # Одна строка «× 1» не отличала бы возврат одной бутылки от ста.
            if out or inc:
                item = ignored_types.setdefault(kind or '', {'rows': 0, 'out': 0.0, 'in': 0.0})
                item['rows'] += 1
                item['out'] += out
                item['in'] += inc
            continue

        entry = stock.get((bar, product_id))
        if entry is None:
            entry = stock[(bar, product_id)] = _new_entry(product_id, name)

        # Раскладка буквально как у кегов (core/draft_kegs.py, collect_kegs).
        if kind == TT_SOLD:
            entry['sold'] += out
            entry['sold_cost'] += _num(row.get('Sum.Outgoing'))
        elif kind == TT_WRITEOFF:
            entry['writeoff'] += out
        elif kind == TT_INVENTORY:
            entry['inventory_out'] += out
            entry['inventory_in'] += inc
        elif kind == TT_INVOICE:
            entry['invoice_in'] += inc
        elif kind == TT_TRANSFER:
            entry['transfer_in'] += inc
            entry['transfer_out'] += out

    diagnostics = {
        'non_piece_products': sorted(non_piece.values(),
                                     key=lambda p: (p['ProductName'], p['ProductId'])),
        'ignored_types': dict(sorted(ignored_types.items())),
    }
    return stock, diagnostics


def merge_by_product(stock):
    """Схлопнуть склады: ключ — товар. Для разреза «Общая» и для одного бара
    результат одинаков по форме, поэтому дальше код один."""
    merged = {}
    for (_bar, product_id), entry in sorted(stock.items(), key=lambda kv: (kv[0][1], kv[0][0] or '')):
        target = merged.get(product_id)
        if target is None:
            merged[product_id] = dict(entry)
            continue
        for field in _FIELDS:
            target[field] += entry[field]
    return merged


def _position_indexes(positions):
    """Два индекса для связки товара с позицией: по GUID и по имени."""
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


def build_losses_block(transactions, bar_name, positions, sold_by_register):
    """Блок losses для ответа /api/packaging. Мутирует positions: добавляет
    каждой позиции поля движений склада.

    positions — список позиций таблицы (у каждой есть Id, Beer, DishId/DishIds,
    TotalQty); sold_by_register — сумма DishAmountInt из продаж (totals.qty),
    нужна для диагностики «касса против склада».

    Поля позиции после вызова: SoldQtyStock, WriteoffQty, InventoryNetQty,
    InventoryShortQty, InventorySurplusQty, LossQty, LossPercentOfSold,
    WriteoffPercentOfSold, InventoryPercentOfSold, InventoryShortPercentOfSold,
    InventorySurplusPercentOfSold (проценты None, если по складу не продано) и
    StockUnit — единица товара на складе, если она не «шт» (такая позиция в
    баланс не входит).

    Недостача и излишек считаются ПО КАЖДОМУ БАРУ (с 2026-09-26): инвентаризация —
    пересчёт одного склада, и излишек в баре B не отменяет пропажу в баре A. В
    разрезе «Общая» они раньше гасили друг друга, и позиция с −5 в одном баре и
    +5 в другом исчезала из расхождений. Баланс сверху остаётся нетто по сети —
    это честное изменение остатка.
    """
    for position in positions:
        position['SoldQtyStock'] = 0.0
        position['WriteoffQty'] = 0.0
        position['InventoryNetQty'] = 0.0
        position['InventoryShortQty'] = 0.0
        position['InventorySurplusQty'] = 0.0
        position['LossQty'] = 0.0
        position['LossPercentOfSold'] = None
        position['WriteoffPercentOfSold'] = None
        position['InventoryPercentOfSold'] = None
        position['InventoryShortPercentOfSold'] = None
        position['InventorySurplusPercentOfSold'] = None
        position['StockUnit'] = None

    stock, diagnostics = collect_stock(transactions, bar_name)
    merged = merge_by_product(stock)
    by_guid, by_name = _position_indexes(positions)
    by_id = {p['Id']: p for p in positions}
    has_guids = any(p.get('DishId') for p in positions)

    # Товар не в штуках, у которого есть строка в кассе (весовые закуски в
    # группе фасовки): в баланс не входит, поэтому и из сверки «касса против
    # склада» выпадает — иначе разница была бы ненулевой каждый период, а
    # причина называлась бы неверно. Позиция получает StockUnit для карточки.
    register_non_piece = 0.0
    non_piece_positions = set()
    for product in diagnostics['non_piece_products']:
        position_id = by_guid.get(product['ProductId'])
        if position_id is None:
            position_id = by_name.get(str(product['ProductName']).strip())
        if position_id is None or position_id in non_piece_positions:
            continue
        non_piece_positions.add(position_id)
        by_id[position_id]['StockUnit'] = product['Unit']
        register_non_piece += _num(by_id[position_id].get('TotalQty'))
    sold_by_register_pieces = sold_by_register - register_non_piece

    sold = sum(e['sold'] for e in merged.values())
    writeoff = sum(e['writeoff'] for e in merged.values())
    inventory_out = sum(e['inventory_out'] for e in merged.values())
    inventory_in = sum(e['inventory_in'] for e in merged.values())
    invoice_in = sum(e['invoice_in'] for e in merged.values())
    transfer_in = sum(e['transfer_in'] for e in merged.values())
    transfer_out = sum(e['transfer_out'] for e in merged.values())
    inventory_net = inventory_out - inventory_in

    def position_of(product_id, product_name):
        position_id = by_guid.get(product_id)
        if position_id is not None:
            return position_id, 'guid'
        position_id = by_name.get(str(product_name).strip())
        return position_id, ('name' if position_id is not None else None)

    # Недостача и излишек по барам: для товара — сумма по его складам; для
    # позиции — сначала нетто по всем её GUID внутри бара (пересозданная карточка
    # — тот же товар на той же полке, её GUID гасят друг друга), потом по барам.
    product_split = {}      # product_id -> [недостача, излишек]
    position_bar_net = {}   # (position_id, bar) -> нетто
    for (bar, product_id), entry in sorted(stock.items(),
                                           key=lambda kv: (kv[0][1], kv[0][0] or '')):
        net = entry['inventory_out'] - entry['inventory_in']
        split = product_split.setdefault(product_id, [0.0, 0.0])
        split[0] += max(net, 0.0)
        split[1] += max(-net, 0.0)
        position_id, _ = position_of(product_id, entry['product_name'])
        if position_id is not None:
            key = (position_id, bar)
            position_bar_net[key] = position_bar_net.get(key, 0.0) + net
    for (position_id, _bar), net in sorted(position_bar_net.items(),
                                           key=lambda kv: (kv[0][0], kv[0][1] or '')):
        position = by_id[position_id]
        position['InventoryShortQty'] += max(net, 0.0)
        position['InventorySurplusQty'] += max(-net, 0.0)

    by_item = []
    unmatched = 0
    for entry in merged.values():
        position_id, matched_by = position_of(entry['product_id'], entry['product_name'])

        net = entry['inventory_out'] - entry['inventory_in']
        short, surplus = product_split.get(entry['product_id'], (max(net, 0.0), max(-net, 0.0)))
        loss = entry['writeoff'] + short

        if position_id is not None:
            position = by_id[position_id]
            position['SoldQtyStock'] += entry['sold']
            position['WriteoffQty'] += entry['writeoff']
            position['InventoryNetQty'] += net

        # Только товары с расхождениями, без обрезки: страница показывает первые
        # восемь, остальные прячет под «ещё N» — но решает это интерфейс.
        if entry['writeoff'] > 0 or short > 0 or surplus > 0:
            if position_id is None:
                unmatched += 1
            by_item.append({
                'ProductId': entry['product_id'],
                'ProductName': entry['product_name'],
                'PositionId': position_id,
                'MatchedBy': matched_by,
                'SoldQty': entry['sold'],
                'WriteoffQty': entry['writeoff'],
                'InventoryNetQty': net,
                'InventoryShortQty': short,
                'InventorySurplusQty': surplus,
                'LossQty': loss,
                'LossPercentOfSold': (loss / entry['sold'] * 100) if entry['sold'] > 0 else None,
            })

    for position in positions:
        # Потери позиции — акты плюс недостача по барам (см. выше): GUID одной
        # позиции внутри бара гасят друг друга, разные бары — нет.
        position['LossQty'] = position['WriteoffQty'] + position['InventoryShortQty']
        stock_sold = position['SoldQtyStock']
        if stock_sold > 0:
            position['LossPercentOfSold'] = position['LossQty'] / stock_sold * 100
            position['WriteoffPercentOfSold'] = position['WriteoffQty'] / stock_sold * 100
            position['InventoryPercentOfSold'] = position['InventoryNetQty'] / stock_sold * 100
            position['InventoryShortPercentOfSold'] = (position['InventoryShortQty']
                                                       / stock_sold * 100)
            position['InventorySurplusPercentOfSold'] = (position['InventorySurplusQty']
                                                         / stock_sold * 100)

    # Сортировка как у кегов — по величине расхождения; тай-брейк по имени,
    # чтобы порядок не зависел от порядка строк OLAP.
    by_item.sort(key=lambda k: (-(k['WriteoffQty'] + k['InventoryShortQty']
                                  + k['InventorySurplusQty']),
                                k['ProductName'], k['ProductId']))

    diagnostics.update({
        # Касса без позиций не в штуках: их продажи в баланс не входят.
        'sold_by_register': sold_by_register_pieces,
        'register_non_piece_qty': register_non_piece,
        'sold_by_stock': sold,
        'sold_delta': sold - sold_by_register_pieces,
        'unmatched_products': unmatched,
        'match_mode': 'guid' if has_guids else 'name',
        'has_transactions': bool(transactions),
    })

    return {
        'unit': PIECE_UNIT,
        # Приход одним числом — для подписи «приход X − расход Y» под итогом;
        # страница ничего не складывает сама.
        'received': invoice_in + transfer_in,
        'invoice_in': invoice_in,
        'transfer_in': transfer_in,
        'transfer_out': transfer_out,
        'sold': sold,
        'writeoff': writeoff,
        'inventory_out': inventory_out,
        'inventory_in': inventory_in,
        'inventory_net': inventory_net,
        # Та же формула, что у кегов: приход минус весь расход. Недостача
        # инвентаризации — нетто, излишек её уменьшает.
        'balance': (invoice_in + transfer_in
                    - sold - writeoff - inventory_net - transfer_out),
        'writeoff_percent_of_sold': (writeoff / sold * 100) if sold > 0 else 0.0,
        'inventory_percent_of_sold': (inventory_net / sold * 100) if sold > 0 else 0.0,
        # Сумма расхода одним числом — для подписи под итогом; раньше на /draft
        # её складывал JS.
        'spent': sold + writeoff + inventory_net + transfer_out,
        'by_item': by_item,
        'diagnostics': diagnostics,
    }
