# -*- coding: utf-8 -*-
"""Пересборка tests/fixtures/kitchen_sample.json — ответа /api/kitchen, на котором
исполняются tests/test_kitchen_runtime.mjs и tests/test_kitchen_render.mjs.

    python3 tests/fixtures/build_kitchen_sample.py

Продажи — настоящие строки data/cache/kitchen_report.json: группа «ЕДА», 4 бара,
07.10-05.11.2025, 46 позиций. В этой выгрузке нет групп второго и третьего уровня,
типа позиции и GUID, поэтому они дописаны:
- DishType и DishId — из номенклатуры (data/cache/nomenclature_full.json) по имени;
- категории — по кухонному меню для Яндекс Карт (resources/kitchen_menu.yml):
  Горячее, Колбаски, Смокер, Пицца, Орехи, Вяленое, Соусы. Пицца лежит на третьем
  уровне («Кухня / Пицца»), остальные на втором — так проверяются обе ветки выбора
  категории; «Гренки Чеснок 100гр» оставлены без группы («Без категории (К)»).

Проводки склада синтетические, в рублях: в репозитории нет ни одной живой строки
OLAP TRANSACTIONS по кухне. Правила детерминированы (индекс позиции в списке имён,
без случайностей) и покрывают все ветки страницы: товары «как есть» со связкой по
GUID, ингредиенты блюд в кг и литрах, акты, недостачи, излишек в другом баре,
перемещение, продукт без продаж, чужой тип проводки. Ингредиенты блюд покрывают
90% их закупки — так в диагностике видна сверка «касса против склада» меньше 100%.

Меняется расчёт — перезапустить скрипт и закоммитить фикстуру вместе с кодом.
"""

import json
import math
import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.kitchen_analysis import KitchenAnalysis  # noqa: E402

SOURCE = os.path.join(ROOT, 'data', 'cache', 'kitchen_report.json')
NOMENCLATURE = os.path.join(ROOT, 'data', 'cache', 'nomenclature_full.json')
TARGET = os.path.join(ROOT, 'tests', 'fixtures', 'kitchen_sample.json')

BOX = 10               # штук в упаковке: приход товаров «как есть» кратен упаковке
DISH_COVERAGE = 0.9    # доля закупки блюд, которую объясняют ингредиенты группы «ЕДА»

# (подстрока имени, SecondParent, ThirdParent) — первая подходящая побеждает.
CATEGORIES = [
    ('Гренки Чеснок 100гр', None, None),
    ('арахис', 'Орехи', None), ('кешью', 'Орехи', None), ('миндаль', 'Орехи', None),
    ('фисташ', 'Орехи', None),
    ('джерки', 'Вяленое', None), ('бастурма', 'Вяленое', None), ('оленина', 'Вяленое', None),
    ('сальсичча', 'Вяленое', None), ('чипсы', 'Вяленое', None),
    ('ветчина', 'Кухня', 'Пицца'), ('горгонзола', 'Кухня', 'Пицца'), ('маргарита', 'Кухня', 'Пицца'),
    ('мясная', 'Кухня', 'Пицца'), ('пеперони', 'Кухня', 'Пицца'), ('страчателла', 'Кухня', 'Пицца'),
    ('три сыра', 'Кухня', 'Пицца'),
    ('колбас', 'Колбаски', None),
    ('пастрами', 'Смокер', None),
    ('соус', 'Соусы', None), (' 50 г', 'Соусы', None),
]

# Ингредиент блюда: (подстрока имени блюда, продукт склада, единица, ₽ за единицу).
INGREDIENTS = [
    ('колбас', 'Колбаски для жарки, товар', 'кг', 820.0),
    ('картофель фри', 'Картофель фри товар', 'кг', 210.0),
    ('дольки', 'Картофельные дольки, Товар', 'кг', 230.0),
    ('гренки', 'Хлеб ржаной, товар', 'кг', 160.0),
    ('медальоны', 'Медальоны сырные Моцарелла', 'кг', 940.0),
    ('пастрами', 'Пастрами, товар', 'кг', 1850.0),
    ('соус', 'Соусы, товар', 'кг', 380.0),
    ('', 'Полуфабрикаты фритюр, товар', 'кг', 520.0),
]


def _guid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'kitchen-fixture:' + name))


def categorize(name):
    low = name.lower()
    for needle, second, third in CATEGORIES:
        if needle.lower() in low:
            return second, third
    return 'Горячее', None


def ingredient_of(name):
    low = name.lower()
    for needle, product, unit, price in INGREDIENTS:
        if needle in low:
            return product, unit, price
    return INGREDIENTS[-1][1:]


def main():
    with open(SOURCE, encoding='utf-8') as f:
        rows = [r for r in json.load(f)['data'] if r.get('DishGroup.TopParent') == 'ЕДА']
    with open(NOMENCLATURE, encoding='utf-8') as f:
        nomenclature = json.load(f)
    by_name = {}
    for guid, item in sorted(nomenclature.items()):
        by_name.setdefault(item['name'].strip(), (guid, item['type']))

    dish_type = {'GOODS': 'GOOD', 'DISH': 'DISH', 'MODIFIER': 'MODIFIER'}
    sales = []
    for r in rows:
        name = r['DishName']
        guid, kind = by_name.get(name.strip(), (_guid(name), 'DISH'))
        second, third = categorize(name)
        sales.append({
            'Store.Name': r['Store.Name'], 'DishName': name,
            'DishGroup.SecondParent': second, 'DishGroup.ThirdParent': third,
            'DishType': dish_type.get(kind, 'DISH'), 'OpenDate.Typed': r['OpenDate.Typed'],
            'DishId': guid, 'DishAmountInt': r['DishAmountInt'],
            'DishDiscountSumInt': r['DishDiscountSumInt'],
            'ProductCostBase.ProductCost': r['ProductCostBase.ProductCost'],
        })

    days = sorted({r['OpenDate.Typed'] for r in sales})
    first_day, last_day, mid_day = days[0], days[-1], days[len(days) // 2]
    trans = []

    def row(bar, pid, name, kind, unit, out=0.0, inc=0.0, out_sum=0.0, in_sum=0.0):
        trans.append({'Account.Name': bar, 'Product.Id': pid, 'Product.Name': name,
                      'Product.MeasureUnit': unit, 'TransactionType': kind,
                      'Amount.Out': out, 'Amount.In': inc,
                      'Sum.Outgoing': round(out_sum, 2), 'Sum.Incoming': round(in_sum, 2)})

    # Продажи по складу: товар «как есть» списывается сам, у блюд и модификаторов —
    # ингредиенты (90% закупки: остальное лежит вне группы «ЕДА»).
    goods = {}
    ingredients = {}
    for r in sales:
        qty, cost = float(r['DishAmountInt'] or 0), float(r['ProductCostBase.ProductCost'] or 0)
        bar = r['Store.Name']
        if r['DishType'] == 'GOOD':
            g = goods.setdefault((r['DishId'], r['DishName']), {})
            q, c = g.get(bar, (0.0, 0.0))
            g[bar] = (q + qty, c + cost)
        else:
            product, unit, price = ingredient_of(r['DishName'])
            i = ingredients.setdefault(product, {'unit': unit, 'price': price, 'bars': {}})
            i['bars'][bar] = i['bars'].get(bar, 0.0) + cost * DISH_COVERAGE

    for (pid, name), bars in sorted(goods.items(), key=lambda kv: kv[0][1]):
        total_qty = sum(q for q, _ in bars.values())
        total_cost = sum(c for _, c in bars.values())
        unit_cost = total_cost / total_qty if total_qty else 0.0
        for bar, (q, c) in sorted(bars.items()):
            row(bar, pid, name, 'SESSION_WRITEOFF', 'шт', out=q, out_sum=c)
        top_bar = sorted(bars.items(), key=lambda kv: (-kv[1][0], kv[0]))[0][0]
        received = float(math.ceil(total_qty / BOX) * BOX + BOX)
        row(top_bar, pid, name, 'INVOICE', 'шт', inc=received, in_sum=received * unit_cost)

    for product, info in sorted(ingredients.items()):
        pid = _guid(product)
        total = sum(info['bars'].values())
        for bar, cost in sorted(info['bars'].items()):
            row(bar, pid, product, 'SESSION_WRITEOFF', info['unit'],
                out=round(cost / info['price'], 3), out_sum=cost)
        received_sum = math.ceil(total * 1.1 / 1000) * 1000
        row('Варшавская', pid, product, 'INVOICE', info['unit'],
            inc=round(received_sum / info['price'], 3), in_sum=received_sum)

    # Акты, недостачи и излишки — по индексу товара «как есть».
    goods_list = sorted(goods.items(), key=lambda kv: kv[0][1])
    for i, ((pid, name), bars) in enumerate(goods_list):
        total_qty = sum(q for q, _ in bars.values())
        unit_cost = sum(c for _, c in bars.values()) / total_qty if total_qty else 0.0
        bar = 'Лиговский' if i % 2 == 0 else 'Варшавская'
        if i % 4 == 1:
            n = 1.0 + i % 3
            row(bar, pid, name, 'WRITEOFF', 'шт', out=n, out_sum=n * unit_cost)
        if i % 3 == 2:
            n = 1.0 + i % 4
            row(bar, pid, name, 'INVENTORY_CORRECTION', 'шт', out=n, out_sum=n * unit_cost)
        if i % 7 == 3:
            # Излишек в другом баре: недостачу первого бара он не гасит.
            other = 'Кременчугская'
            row(other, pid, name, 'INVENTORY_CORRECTION', 'шт', inc=1.0, in_sum=unit_cost)

    # Ингредиенты: акт на фри, недостача колбасок, излишек соусов.
    fries = _guid('Картофель фри товар')
    row('Лиговский', fries, 'Картофель фри товар', 'WRITEOFF', 'кг', out=3.2, out_sum=3.2 * 210.0)
    sausages = _guid('Колбаски для жарки, товар')
    row('Большой пр. В.О', sausages, 'Колбаски для жарки, товар', 'INVENTORY_CORRECTION', 'кг',
        out=1.4, out_sum=1.4 * 820.0)
    sauces = _guid('Соусы, товар')
    row('Варшавская', sauces, 'Соусы, товар', 'INVENTORY_CORRECTION', 'кг', inc=0.6, in_sum=0.6 * 380.0)

    # Перемещение, продукт без продаж (масло для фритюра), возврат поставщику.
    pid, name = goods_list[3][0]
    row('Лиговский', pid, name, 'TRANSFER', 'шт', out=10.0, out_sum=10.0 * 150.0)
    row('Варшавская', pid, name, 'TRANSFER', 'шт', inc=10.0, in_sum=10.0 * 150.0)
    oil = _guid('Масло фритюрное, товар')
    row('Лиговский', oil, 'Масло фритюрное, товар', 'INVENTORY_CORRECTION', 'л',
        out=4.0, out_sum=4.0 * 190.0)
    row('Лиговский', goods_list[5][0][0], goods_list[5][0][1], 'OUTGOING_INVOICE', 'шт',
        out=5.0, out_sum=900.0)

    block = KitchenAnalysis(sales, first_day, last_day, transactions=trans).build(None)
    block['generated_at'] = '12:34'
    with open(TARGET, 'w', encoding='utf-8') as f:
        json.dump(block, f, ensure_ascii=False)

    losses = block['losses']
    diag = losses['diagnostics']
    print(f"positions {len(block['positions'])}, categories {len(block['categories'])}, "
          f"modifiers {block['modifiers']['count']} ({block['modifiers']['cost']:.0f} rub), "
          f"by_item {len(losses['by_item'])}, linked {diag['linked_products']}, "
          f"ingredients {diag['ingredient_products']}, coverage {diag['coverage_percent']:.1f}%")
    print(f"received {losses['received']:.0f} - spent {losses['spent']:.0f} = "
          f"balance {losses['balance']:.0f}; shortage {losses['inventory_net']:.0f}; "
          f"ignored {diag['ignored_types']}")
    print('buckets', {b['key']: b['count'] for b in block['buckets']})
    print('categories', [(c['Category'], c['BeersCount']) for c in block['categories']])


if __name__ == '__main__':
    main()
