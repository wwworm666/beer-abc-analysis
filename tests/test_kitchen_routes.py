# -*- coding: utf-8 -*-
"""POST /api/kitchen через загрузчик core/kitchen_loader.py (2026-09-27).

Зеркало tests/test_packaging_routes.py:
1. Один поход в iiko на страницу: проводки и продажи под одним ключом кэша.
2. Сбой любого из двух отчётов или ответ без ключа data — 502 и ничего в кэше.
3. «Нет данных» только когда пусто и в кассе, и на складе.
4. Кривой вход — 400, а не 500.
5. В ответе losses в рублях, modifiers и generated_at — их читает страница.
Сеть не трогается: OlapReports подменён.
"""
import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

from extensions import DASHBOARD_OLAP_CACHE  # noqa: E402
from routes.analysis import analysis_bp  # noqa: E402

PERIOD = {"date_from": "2026-08-24", "date_to": "2026-08-30"}
CACHE_KEY_ALL = "kitchen_ALL_2026-08-24_2026-08-31"


def sale_row(bar, dish_id, day, qty, revenue, cost, name, kind="GOOD"):
    return {
        "Store.Name": bar, "DishName": name, "DishGroup.SecondParent": "Вяленое",
        "DishGroup.ThirdParent": None, "DishType": kind, "OpenDate.Typed": day,
        "DishAmountInt": qty, "DishDiscountSumInt": revenue,
        "ProductCostBase.ProductCost": cost, "DishId": dish_id,
    }


def trans_row(bar, product_id, kind, out=0.0, inc=0.0, out_sum=0.0, in_sum=0.0,
              name="Джерки", unit="шт"):
    return {
        "Account.Name": bar, "Product.Id": product_id, "Product.Name": name,
        "Product.MeasureUnit": unit, "TransactionType": kind,
        "Amount.Out": out, "Amount.In": inc, "Sum.Outgoing": out_sum, "Sum.Incoming": in_sum,
    }


class FakeOlap:
    """iiko отвечает заготовкой и считает обращения."""

    calls = 0
    sales = [
        sale_row("Лиговский", "g-jerky", "2026-08-25", 5, 2000, 750, "Джерки"),
        sale_row("Лиговский", "m-ketchup", "2026-08-25", 3, 0, 30, "Кетчуп 50 г", kind="MODIFIER"),
    ]
    transactions = [
        trans_row("Лиговский", "g-jerky", "INVOICE", inc=10, in_sum=1500),
        trans_row("Лиговский", "g-jerky", "SESSION_WRITEOFF", out=5, out_sum=750),
        trans_row("Лиговский", "g-jerky", "WRITEOFF", out=1, out_sum=150),
    ]

    def __init__(self):
        self.api = type("Api", (), {"base_url": "https://example.invalid/resto/api"})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_kitchen_writeoff_report(self, date_from, date_to, bar_name=None):
        FakeOlap.calls += 1
        rows = [r for r in self.transactions if not bar_name or r["Account.Name"] == bar_name]
        return {"data": rows}

    def get_kitchen_page_sales_report(self, date_from, date_to, bar_name=None):
        rows = [r for r in self.sales if not bar_name or r["Store.Name"] == bar_name]
        return {"data": rows}


class NoTransactionsOlap(FakeOlap):
    def get_kitchen_writeoff_report(self, date_from, date_to, bar_name=None):
        FakeOlap.calls += 1
        return None


class NoSalesOlap(FakeOlap):
    def get_kitchen_page_sales_report(self, date_from, date_to, bar_name=None):
        return None


class NoDataKeyOlap(FakeOlap):
    def get_kitchen_writeoff_report(self, date_from, date_to, bar_name=None):
        FakeOlap.calls += 1
        return {}


class StockOnlyOlap(FakeOlap):
    sales = []


class EmptyOlap(FakeOlap):
    sales = []
    transactions = []


def make_client():
    app = Flask(__name__)
    app.register_blueprint(analysis_bp)
    return app.test_client()


class KitchenEndpoint(unittest.TestCase):

    def setUp(self):
        DASHBOARD_OLAP_CACHE.clear()
        FakeOlap.calls = 0

    def test_one_trip_to_iiko_rubles_and_modifiers_in_response(self):
        client = make_client()
        with patch("core.kitchen_loader.OlapReports", FakeOlap):
            first = client.post("/api/kitchen", json={"bar": "", **PERIOD})
            second = client.post("/api/kitchen", json={"bar": "", **PERIOD})
        self.assertEqual(200, first.status_code, first.get_data(as_text=True))
        self.assertEqual(200, second.status_code)
        self.assertEqual(1, FakeOlap.calls, "второй запрос за тот же период сходил в iiko")
        self.assertIn(CACHE_KEY_ALL, DASHBOARD_OLAP_CACHE)

        block = first.get_json()
        self.assertRegex(block["generated_at"], r"^\d\d:\d\d$")
        self.assertEqual(["Джерки"], [p["Beer"] for p in block["positions"]])
        self.assertEqual(1, block["modifiers"]["count"])
        self.assertEqual(30.0, block["modifiers"]["cost"])
        losses = block["losses"]
        self.assertEqual("₽", losses["unit"])
        # 1500 − 750 − 150 = 600 ₽
        self.assertAlmostEqual(600.0, losses["balance"])
        self.assertEqual(150.0, block["positions"][0]["WriteoffRub"])
        self.assertEqual(780.0, losses["diagnostics"]["sold_cost_by_register"])

    def test_bar_scope_has_its_own_cache_key(self):
        client = make_client()
        with patch("core.kitchen_loader.OlapReports", FakeOlap):
            response = client.post("/api/kitchen", json={"bar": "Лиговский", **PERIOD})
        self.assertEqual(200, response.status_code)
        self.assertIn("kitchen_Лиговский_2026-08-24_2026-08-31", DASHBOARD_OLAP_CACHE)
        self.assertEqual("bar", response.get_json()["scope"])

    def test_failed_reports_are_502_and_not_cached(self):
        client = make_client()
        for olap in (NoTransactionsOlap, NoSalesOlap, NoDataKeyOlap):
            DASHBOARD_OLAP_CACHE.clear()
            with patch("core.kitchen_loader.OlapReports", olap):
                response = client.post("/api/kitchen", json={"bar": "", **PERIOD})
            self.assertEqual(502, response.status_code, olap.__name__)
            self.assertEqual({}, DASHBOARD_OLAP_CACHE, olap.__name__)

    def test_stock_movements_without_sales_are_data_not_404(self):
        client = make_client()
        with patch("core.kitchen_loader.OlapReports", StockOnlyOlap):
            response = client.post("/api/kitchen", json={"bar": "", **PERIOD})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        block = response.get_json()
        self.assertEqual([], block["positions"])
        self.assertEqual(1500.0, block["losses"]["invoice_in"])

    def test_empty_period_is_404(self):
        client = make_client()
        with patch("core.kitchen_loader.OlapReports", EmptyOlap):
            response = client.post("/api/kitchen", json={"bar": "", **PERIOD})
        self.assertEqual(404, response.status_code)

    def test_bad_input_is_400_not_500(self):
        client = make_client()
        with patch("core.kitchen_loader.OlapReports", FakeOlap):
            bad_dates = client.post("/api/kitchen", json={"date_from": "27.09", "date_to": "x"})
            reversed_period = client.post("/api/kitchen", json={
                "date_from": "2026-08-30", "date_to": "2026-08-24"})
            bad_days = client.post("/api/kitchen", json={"days": "много"})
            bad_json = client.post("/api/kitchen", data="{", content_type="application/json")
        self.assertEqual(400, bad_dates.status_code)
        self.assertEqual(400, reversed_period.status_code)
        self.assertEqual(400, bad_days.status_code)
        # Кривой JSON — пустой вход: период по умолчанию, а не 500.
        self.assertEqual(200, bad_json.status_code)


class KitchenOlapRequests(unittest.TestCase):
    """Форма запросов к iiko: группа «ЕДА», тип позиции, суммы склада."""

    def capture(self, method, *args):
        from core.olap_reports import OlapReports
        olap = OlapReports()
        olap.token = "t"
        bodies = []
        with patch.object(OlapReports, "_post_olap_interactive",
                          lambda self, body, tag: bodies.append(body) or {"data": []}):
            getattr(olap, method)(*args)
        return bodies[0]

    def test_sales_request_filters_food_and_groups_by_type_and_levels(self):
        body = self.capture("get_kitchen_page_sales_report", "2026-09-01", "2026-09-29", "Лиговский")
        self.assertEqual("SALES", body["reportType"])
        self.assertEqual(["ЕДА"], body["filters"]["DishGroup.TopParent"]["values"])
        for field in ("DishType", "DishGroup.SecondParent", "DishGroup.ThirdParent", "DishId"):
            self.assertIn(field, body["groupByRowFields"])
        self.assertEqual(["Лиговский"], body["filters"]["Store.Name"]["values"])
        self.assertEqual(["DishAmountInt", "DishDiscountSumInt", "ProductCostBase.ProductCost"],
                         body["aggregateFields"])

    def test_stock_request_is_food_group_in_rubles(self):
        body = self.capture("get_kitchen_writeoff_report", "2026-09-01", "2026-09-29")
        self.assertEqual("TRANSACTIONS", body["reportType"])
        self.assertEqual(["ЕДА"], body["filters"]["Product.TopParent"]["values"])
        self.assertIn("Sum.Outgoing", body["aggregateFields"])
        self.assertIn("Sum.Incoming", body["aggregateFields"])
        self.assertNotIn("DateTime.DateTyped", body["groupByRowFields"])

    def test_packaging_stock_request_unchanged(self):
        body = self.capture("get_packaging_writeoff_report", "2026-09-01", "2026-09-29")
        self.assertEqual(["Amount.Out", "Amount.In", "Sum.Outgoing"], body["aggregateFields"])


if __name__ == "__main__":
    unittest.main()
