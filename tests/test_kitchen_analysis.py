# -*- coding: utf-8 -*-
"""Расчёт страницы /kitchen (core/kitchen_analysis.py, core/kitchen_losses.py).

Что защищают тесты:
1. Пороги наценки кухни 180/150 применяются к букве, к группе решения и к
   правилам групп — а не пороги фасовки 120/100.
2. Соусы-модификаторы не становятся позициями, но их закупка видна в блоке
   modifiers и входит в сверку «касса против склада».
3. Категория — третий уровень дерева, если он есть, иначе второй, иначе
   «Без категории (К)».
4. Баланс и потери — в рублях по закупке, формула та же, что у фасовки;
   недостача одного бара не гасится излишком другого.
5. Товар «как есть» связывается с позицией по GUID, ингредиент блюда — нет,
   и это не ошибка, а отдельный счётчик.
6. Одинаковый вход — одинаковый ответ, в любом порядке строк.

Запуск:
    python3 -m pytest -q tests/test_kitchen_analysis.py
"""
import json
import os
import random
import sys

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

from core.abc_thresholds import (  # noqa: E402
    KITCHEN_MARKUP_A_MIN,
    KITCHEN_MARKUP_B_MIN,
    UNCATEGORIZED_KITCHEN,
)
from core.kitchen_analysis import KitchenAnalysis  # noqa: E402

DAYS = ("2026-09-01", "2026-09-28")   # 28 дней: четыре полные недели, «вывести» разрешено


def sale(name, qty, revenue, cost, bar="Лиговский", day="2026-09-10", kind="DISH",
         second="Горячее", third=None, dish_id=None):
    return {
        "Store.Name": bar, "DishName": name, "DishGroup.SecondParent": second,
        "DishGroup.ThirdParent": third, "DishType": kind, "OpenDate.Typed": day,
        "DishId": dish_id or "dish-" + name, "DishAmountInt": qty,
        "DishDiscountSumInt": revenue, "ProductCostBase.ProductCost": cost,
    }


def trans(bar, pid, name, kind, unit="шт", out=0.0, inc=0.0, out_sum=0.0, in_sum=0.0):
    return {
        "Account.Name": bar, "Product.Id": pid, "Product.Name": name,
        "Product.MeasureUnit": unit, "TransactionType": kind,
        "Amount.Out": out, "Amount.In": inc, "Sum.Outgoing": out_sum, "Sum.Incoming": in_sum,
    }


def weekly(name, per_week, revenue_per_unit, cost_per_unit, **kw):
    """Продажи каждую неделю периода: XYZ считается, решение выносится."""
    days = ["2026-09-02", "2026-09-09", "2026-09-16", "2026-09-23"]
    return [sale(name, per_week, per_week * revenue_per_unit, per_week * cost_per_unit,
                 day=d, **kw) for d in days]


def build(rows, transactions=None, bar=None):
    return KitchenAnalysis(rows, *DAYS, transactions=transactions or []).build(bar)


def by_name(block, name):
    return next(p for p in block["positions"] if p["Beer"] == name)


def test_kitchen_markup_thresholds_are_180_and_150():
    assert KITCHEN_MARKUP_A_MIN == 1.8
    assert KITCHEN_MARKUP_B_MIN == 1.5
    rows = (weekly("Фри", 10, 290, 100)          # наценка 190% -> A
            + weekly("Джерки", 10, 270, 100)     # 170% -> B, ниже минимума кухни
            + weekly("Орехи", 10, 230, 100))     # 130% -> C (у фасовки была бы A)
    block = build(rows)
    assert by_name(block, "Фри")["ABC_Markup"] == "A"
    assert by_name(block, "Джерки")["ABC_Markup"] == "B"
    assert by_name(block, "Орехи")["ABC_Markup"] == "C"
    # 170% ниже минимума 180% — «поднять цену», а не «основа выручки».
    assert by_name(block, "Джерки")["ABC_Bucket"] == "low_markup"
    assert by_name(block, "Фри")["ABC_Bucket"] == "core"
    rule = next(b for b in block["buckets"] if b["key"] == "low_markup")["rule"]
    assert "180%" in rule and "120%" not in rule


def test_modifiers_are_not_positions_but_are_reported():
    rows = weekly("Фри", 10, 300, 100) + [
        sale("Кетчуп 50 г", 20, 0, 60, kind="MODIFIER", second="Соусы"),
        sale("Сырный 50 г", 5, 40, 25, kind="MODIFIER", second="Соусы", bar="Варшавская"),
    ]
    block = build(rows)
    assert [p["Beer"] for p in block["positions"]] == ["Фри"]
    mods = block["modifiers"]
    assert mods["count"] == 2
    assert mods["qty"] == 25
    assert mods["revenue"] == 40
    assert mods["cost"] == 85
    assert [m["Name"] for m in mods["items"]] == ["Кетчуп 50 г", "Сырный 50 г"]
    # Итоги страницы — без модификаторов.
    assert block["totals"]["cost"] == 4000     # 4 недели × 10 × 100 ₽
    # В сверку со складом модификаторы входят: их ингредиенты списываются.
    assert block["losses"]["diagnostics"]["sold_cost_by_register"] == 4085
    assert block["losses"]["diagnostics"]["modifiers_cost"] == 85


def test_modifiers_follow_bar_scope():
    rows = weekly("Фри", 10, 300, 100) + [
        sale("Кетчуп 50 г", 20, 0, 60, kind="MODIFIER"),
        sale("Сырный 50 г", 5, 40, 25, kind="MODIFIER", bar="Варшавская"),
    ]
    block = build(rows, bar="Варшавская")
    assert block["modifiers"]["count"] == 1
    assert block["modifiers"]["cost"] == 25


def test_category_prefers_third_level_then_second_then_label():
    rows = [
        sale("Пепперони", 3, 900, 300, second="Кухня", third="Пицца"),
        sale("Фри", 3, 900, 300, second="Горячее", third=None),
        sale("Гренки", 3, 900, 300, second=None, third=None),
        sale("Пустая строка", 3, 900, 300, second="  ", third=""),
    ]
    block = build(rows)
    assert by_name(block, "Пепперони")["Category"] == "Пицца"
    assert by_name(block, "Фри")["Category"] == "Горячее"
    assert by_name(block, "Гренки")["Category"] == UNCATEGORIZED_KITCHEN
    assert by_name(block, "Пустая строка")["Category"] == UNCATEGORIZED_KITCHEN
    assert UNCATEGORIZED_KITCHEN == "Без категории (К)"


def test_balance_in_rubles_uses_same_formula_as_packaging():
    rows = weekly("Джерки", 10, 400, 150, kind="GOOD", dish_id="g-jerky")
    tr = [
        trans("Лиговский", "g-jerky", "Джерки", "INVOICE", inc=50, in_sum=7500),
        trans("Лиговский", "g-jerky", "Джерки", "SESSION_WRITEOFF", out=40, out_sum=6000),
        trans("Лиговский", "g-jerky", "Джерки", "WRITEOFF", out=2, out_sum=300),
        trans("Лиговский", "g-jerky", "Джерки", "INVENTORY_CORRECTION", out=1, out_sum=150),
        trans("Лиговский", "fries-kg", "Картофель фри товар", "TRANSFER", unit="кг",
              out=5, out_sum=1050),
        trans("Варшавская", "fries-kg", "Картофель фри товар", "TRANSFER", unit="кг",
              inc=5, in_sum=1050),
    ]
    losses = build(rows, tr)["losses"]
    assert losses["unit"] == "₽"
    assert losses["received"] == 7500 + 1050
    assert losses["spent"] == 6000 + 300 + 150 + 1050
    # приход − (продано + акты + недостача + перемещения)
    assert losses["balance"] == 8550 - 7500
    assert losses["writeoff_percent_of_sold"] == 300 / 6000 * 100
    assert losses["inventory_percent_of_sold"] == 150 / 6000 * 100


def test_goods_link_to_position_by_guid_and_ingredients_do_not():
    rows = (weekly("Джерки", 10, 400, 150, kind="GOOD", dish_id="g-jerky")
            + weekly("Фри", 10, 300, 40, dish_id="dish-fries"))
    tr = [
        trans("Лиговский", "g-jerky", "Джерки 40 г. ЕДА", "SESSION_WRITEOFF", out=40, out_sum=6000),
        trans("Лиговский", "g-jerky", "Джерки 40 г. ЕДА", "WRITEOFF", out=2, out_sum=300),
        trans("Лиговский", "fries-kg", "Картофель фри товар", "SESSION_WRITEOFF", unit="кг",
              out=7.5, out_sum=1575),
        trans("Лиговский", "fries-kg", "Картофель фри товар", "WRITEOFF", unit="кг",
              out=3.2, out_sum=672),
    ]
    block = build(rows, tr)
    jerky = by_name(block, "Джерки")
    assert jerky["WriteoffRub"] == 300
    assert jerky["SoldCostStock"] == 6000
    assert jerky["LossPercentOfSold"] == 300 / 6000 * 100
    fries = by_name(block, "Фри")
    assert fries["LossRub"] == 0 and fries["SoldCostStock"] == 0
    rows_by_product = {r["ProductName"]: r for r in block["losses"]["by_item"]}
    assert rows_by_product["Джерки 40 г. ЕДА"]["PositionId"] == jerky["Id"]
    ingredient = rows_by_product["Картофель фри товар"]
    assert ingredient["PositionId"] is None
    assert ingredient["Unit"] == "кг"
    assert ingredient["WriteoffQty"] == 3.2
    assert ingredient["LossRub"] == 672
    assert ingredient["LossPercentOfSold"] == 672 / 1575 * 100
    diag = block["losses"]["diagnostics"]
    assert diag["linked_products"] == 1
    assert diag["ingredient_products"] == 1
    # Касса: 40 × 150 + 40 × 40 = 7600 ₽ закупки; склад списал 7575 ₽.
    assert diag["sold_cost_by_register"] == 7600
    assert diag["sold_by_stock"] == 7575
    assert diag["coverage_percent"] == 7575 / 7600 * 100


def test_shortage_in_one_bar_is_not_netted_by_surplus_in_another():
    rows = weekly("Джерки", 10, 400, 150, kind="GOOD", dish_id="g-jerky")
    tr = [
        trans("Лиговский", "g-jerky", "Джерки", "SESSION_WRITEOFF", out=40, out_sum=6000),
        trans("Лиговский", "g-jerky", "Джерки", "INVENTORY_CORRECTION", out=2, out_sum=300),
        trans("Варшавская", "g-jerky", "Джерки", "INVENTORY_CORRECTION", inc=2, in_sum=300),
    ]
    block = build(rows, tr)
    losses = block["losses"]
    # Баланс сети — нетто: недостача и излишек гасят друг друга.
    assert losses["inventory_net"] == 0
    item = losses["by_item"][0]
    assert item["InventoryShortRub"] == 300
    assert item["InventorySurplusRub"] == 300
    assert item["LossRub"] == 300
    assert item["InventoryShortQty"] == 2 and item["InventorySurplusQty"] == 2
    position = by_name(block, "Джерки")
    assert position["InventoryShortRub"] == 300
    assert position["LossRub"] == 300


def test_product_without_sales_has_no_percent_and_unknown_types_are_counted():
    tr = [
        trans("Лиговский", "oil", "Масло фритюрное", "INVENTORY_CORRECTION", unit="л",
              out=4, out_sum=760),
        trans("Лиговский", "oil", "Масло фритюрное", "OUTGOING_INVOICE", unit="л",
              out=10, out_sum=1900),
    ]
    losses = build([], tr)["losses"]
    item = losses["by_item"][0]
    assert item["LossRub"] == 760
    assert item["LossPercentOfSold"] is None
    assert losses["diagnostics"]["ignored_types"] == {
        "OUTGOING_INVOICE": {"rows": 1, "out": 1900.0, "in": 0.0}}
    # Возврат поставщику в баланс не входит.
    assert losses["spent"] == 760
    assert losses["diagnostics"]["coverage_percent"] is None


def test_by_item_sorted_by_rubles_then_name():
    tr = [
        trans("Лиговский", "b", "Б-продукт", "WRITEOFF", out=1, out_sum=100),
        trans("Лиговский", "a", "А-продукт", "WRITEOFF", out=1, out_sum=100),
        trans("Лиговский", "c", "В-продукт", "WRITEOFF", out=1, out_sum=900),
    ]
    names = [r["ProductName"] for r in build([], tr)["losses"]["by_item"]]
    assert names == ["В-продукт", "А-продукт", "Б-продукт"]


def test_deterministic_regardless_of_row_order():
    rows = (weekly("Фри", 10, 290, 100) + weekly("Джерки", 7, 270, 100, kind="GOOD")
            + [sale("Кетчуп 50 г", 20, 0, 60, kind="MODIFIER")])
    tr = [
        trans("Лиговский", "dish-Джерки", "Джерки", "SESSION_WRITEOFF", out=28, out_sum=2800),
        trans("Варшавская", "dish-Джерки", "Джерки", "INVENTORY_CORRECTION", out=1, out_sum=100),
        trans("Лиговский", "fries", "Картофель", "WRITEOFF", unit="кг", out=1, out_sum=210),
    ]
    first = json.dumps(build(rows, tr), ensure_ascii=False, sort_keys=True)
    shuffled_rows, shuffled_tr = rows[:], tr[:]
    random.Random(7).shuffle(shuffled_rows)
    random.Random(7).shuffle(shuffled_tr)
    second = json.dumps(build(shuffled_rows, shuffled_tr), ensure_ascii=False, sort_keys=True)
    assert first == second


def test_fixture_is_current():
    """tests/fixtures/kitchen_sample.json пересобран после последней правки расчёта."""
    path = os.path.join(REPO_ROOT, "tests", "fixtures", "kitchen_sample.json")
    with open(path, encoding="utf-8") as f:
        block = json.load(f)
    assert block["modifiers"]["count"] == 6
    assert {c["Category"] for c in block["categories"]} >= {"Пицца", "Горячее", UNCATEGORIZED_KITCHEN}
    rule = next(b for b in block["buckets"] if b["key"] == "low_markup")["rule"]
    assert "180%" in rule
    assert block["losses"]["unit"] == "₽"
