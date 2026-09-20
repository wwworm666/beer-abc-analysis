# -*- coding: utf-8 -*-
"""Пересборка tests/fixtures/packaging_sample.json — ответа /api/packaging, на
котором исполняются tests/test_packaging_runtime.mjs и test_packaging_render.mjs.

    python3 tests/fixtures/build_packaging_sample.py

Продажи — настоящие строки data/beer_report.json (4 бара, 30 дней), урезанные до
пяти позиций на категорию, чтобы фикстура оставалась обозримой. Проводки склада
синтетические: в репозитории нет ни одной живой строки OLAP TRANSACTIONS по
фасовке. Правила синтетики детерминированы (индекс позиции в отсортированном
списке имён, без случайностей) и покрывают все ветки страницы: акты, недостачи,
излишек, перемещения, товар склада без продаж, весовой товар с продажей в кассе,
чужой тип проводки, расхождение касса/склад.

Меняется расчёт — перезапустить скрипт и закоммитить фикстуру вместе с кодом.
"""

import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.packaging_analysis import PackagingAnalysis  # noqa: E402

SOURCE = os.path.join(ROOT, 'data', 'beer_report.json')
TARGET = os.path.join(ROOT, 'tests', 'fixtures', 'packaging_sample.json')

PER_CATEGORY = 5
# Одна позиция в категории — чтобы была категория из единственной строки.
SINGLE = {'Темная столовая бельгия (Ф)': 1}
BOX = 24            # бутылок в коробке: приход по накладным кратен коробке
REGISTER_GAP = 4    # бутылок «уехало» за границу учётного дня: разница касса/склад


def load_rows():
    with open(SOURCE, encoding='utf-8') as f:
        raw = json.load(f)
    return raw['data'] if isinstance(raw, dict) else raw


def pick_names(rows):
    """Top-N имён по выручке в каждой категории (пустая категория — своя группа)."""
    revenue = {}
    for r in rows:
        key = (r.get('DishGroup.ThirdParent') or '', r['DishName'])
        revenue[key] = revenue.get(key, 0.0) + float(r.get('DishDiscountSumInt') or 0)
    by_cat = {}
    for (cat, name), rev in revenue.items():
        by_cat.setdefault(cat, []).append((-rev, name))
    chosen = set()
    for cat, items in by_cat.items():
        items.sort()
        chosen.update(name for _, name in items[:SINGLE.get(cat, PER_CATEGORY)])
    return chosen


def main():
    rows = load_rows()
    chosen = pick_names(rows)
    sales = [dict(r) for r in rows if r['DishName'] in chosen]
    names = sorted(chosen)
    dish_id = {name: 'dish-%03d' % i for i, name in enumerate(names)}
    for r in sales:
        r['DishId'] = dish_id[r['DishName']]

    days = sorted({r['OpenDate.Typed'] for r in rows})
    first_day, last_day, mid_day = days[0], days[-1], days[len(days) // 2]

    # Весовая закуска в группе фасовки: в кассе есть, на складе — в кг.
    sales.append({
        'Store.Name': 'Лиговский', 'DishName': 'Орехи тест', 'DishGroup.ThirdParent': None,
        'DishForeignName': 'Россия', 'OpenDate.Typed': first_day, 'DishAmountInt': 1.5,
        'DishDiscountSumInt': 450.0, 'ProductCostBase.ProductCost': 200.0, 'DishId': 'kg-nuts',
    })

    trans = []

    def row(bar, pid, name, day, kind, out=0.0, inc=0.0, unit='шт'):
        trans.append({'Account.Name': bar, 'Product.Id': pid, 'Product.Name': name,
                      'Product.MeasureUnit': unit, 'DateTime.DateTyped': day,
                      'TransactionType': kind, 'Amount.Out': out, 'Amount.In': inc,
                      'Sum.Outgoing': 0.0})

    # Продажи по складу — зеркало чеков; в первой подходящей строке часть
    # бутылок ушла за границу учётного дня, отсюда разница касса/склад.
    gap = REGISTER_GAP
    for r in sales:
        qty = float(r['DishAmountInt'])
        unit = 'кг' if r['DishId'] == 'kg-nuts' else 'шт'
        if gap and unit == 'шт' and qty > gap:
            qty -= gap
            gap = 0
        row(r['Store.Name'], r['DishId'], r['DishName'], r['OpenDate.Typed'],
            'SESSION_WRITEOFF', out=qty, unit=unit)

    # Приход по накладным — коробками, одной накладной на позицию в тот бар,
    # где она продавалась больше всего (у сети общий поставщик).
    per_bar = {}
    for r in sales:
        if r['DishId'] == 'kg-nuts':
            continue
        key = (r['DishId'], r['DishName'])
        bars = per_bar.setdefault(key, {})
        bars[r['Store.Name']] = bars.get(r['Store.Name'], 0.0) + float(r['DishAmountInt'])
    for (pid, name), bars in sorted(per_bar.items()):
        top_bar = sorted(bars.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        total = sum(bars.values())
        row(top_bar, pid, name, first_day, 'INVOICE', inc=float(math.ceil(total / BOX) * BOX))

    # Акты, недостачи и излишки — по индексу позиции.
    for i, name in enumerate(names):
        pid = dish_id[name]
        bar = 'Лиговский' if i % 2 == 0 else 'Варшавская'
        if i % 4 == 1:
            row(bar, pid, name, mid_day, 'WRITEOFF', out=1.0 + i % 3)
        if i % 3 == 2:
            if i % 9 == 8:
                row(bar, pid, name, last_day, 'INVENTORY_CORRECTION', inc=1.0 + i % 4)
            else:
                row(bar, pid, name, last_day, 'INVENTORY_CORRECTION', out=1.0 + i % 5)

    # Перемещение между барами, товар склада без продаж, возврат поставщику.
    row('Лиговский', dish_id[names[3]], names[3], mid_day, 'TRANSFER', out=26.0)
    row('Варшавская', dish_id[names[3]], names[3], mid_day, 'TRANSFER', inc=26.0)
    row('Лиговский', 'stock-only-1', 'Сидр яблочный тест, 0,330 бут.', mid_day, 'WRITEOFF', out=2.0)
    row('Лиговский', dish_id[names[5]], names[5], mid_day, 'OUTGOING_INVOICE', out=12.0)

    block = PackagingAnalysis(sales, days[0], days[-1], transactions=trans).build(None)
    block['generated_at'] = '12:34'
    with open(TARGET, 'w', encoding='utf-8') as f:
        json.dump(block, f, ensure_ascii=False)

    losses = block['losses']
    print(f"positions {len(block['positions'])}, categories {len(block['categories'])}, "
          f"by_item {len(losses['by_item'])}, surplus rows "
          f"{sum(1 for k in losses['by_item'] if k['InventoryNetQty'] < 0)}, "
          f"unmatched {losses['diagnostics']['unmatched_products']}, "
          f"sold_delta {losses['diagnostics']['sold_delta']}, "
          f"non_piece {len(losses['diagnostics']['non_piece_products'])}, "
          f"ignored {losses['diagnostics']['ignored_types']}")
    print(f"received {losses['received']} − spent {losses['spent']} = balance {losses['balance']}")


if __name__ == '__main__':
    main()
