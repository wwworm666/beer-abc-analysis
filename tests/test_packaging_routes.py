# -*- coding: utf-8 -*-
"""POST /api/packaging через загрузчик core/packaging_loader.py (2026-09-19).

Что защищают тесты:
1. Один поход в iiko на страницу: проводки и продажи лежат под одним ключом
   кэша, второй запрос за тот же период iiko не трогает.
2. Сбой любого из двух отчётов — 502 и НИЧЕГО в кэше (половина данных не
   кэшируется), а не 200 с пустым балансом.
3. «Нет данных» только когда пусто и в кассе, и на складе: период с приходом,
   актом или инвентаризацией без продаж — это данные.
4. Ответ iiko без ключа data — сбой (502), а не пустой период.
4. В ответе есть losses и generated_at — их читает страница.
Сеть не трогается: OlapReports подменён.

Запуск:
    py -3 -X utf8 -m unittest -v tests.test_packaging_routes
"""
import os
import re
import sys
import unittest
from unittest.mock import patch

from flask import Flask

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

from extensions import DASHBOARD_OLAP_CACHE  # noqa: E402
from routes.analysis import analysis_bp  # noqa: E402

PERIOD = {"date_from": "2026-08-24", "date_to": "2026-08-30"}
CACHE_KEY_ALL = "packaging_ALL_2026-08-24_2026-08-31"


def sale_row(bar, dish_id, day, qty, revenue, cost, name):
    return {
        "Store.Name": bar, "DishName": name, "DishGroup.ThirdParent": "Лагер (Ф)",
        "DishForeignName": "Россия", "OpenDate.Typed": day, "DishAmountInt": qty,
        "DishDiscountSumInt": revenue, "ProductCostBase.ProductCost": cost, "DishId": dish_id,
    }


def trans_row(bar, product_id, day, kind, out=0.0, inc=0.0, name="Пиво А"):
    return {
        "Account.Name": bar, "Product.Id": product_id, "Product.Name": name,
        "Product.MeasureUnit": "шт", "DateTime.DateTyped": day, "TransactionType": kind,
        "Amount.Out": out, "Amount.In": inc, "Sum.Outgoing": 0.0,
    }


class FakeOlap:
    """iiko отвечает заготовкой и считает обращения."""

    calls = 0
    sales = [sale_row("Лиговский", "dish-a", "2026-08-25", 5, 2500, 1000, "Пиво А")]
    transactions = [
        trans_row("Лиговский", "dish-a", "2026-08-24", "INVOICE", inc=24.0),
        trans_row("Лиговский", "dish-a", "2026-08-25", "SESSION_WRITEOFF", out=5.0),
        trans_row("Лиговский", "dish-a", "2026-08-26", "WRITEOFF", out=1.0),
    ]

    def __init__(self):
        self.api = type("Api", (), {"base_url": "https://example.invalid/resto/api"})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_packaging_writeoff_report(self, date_from, date_to, bar_name=None):
        FakeOlap.calls += 1
        rows = [r for r in self.transactions if not bar_name or r["Account.Name"] == bar_name]
        return {"data": rows}

    def get_packaging_sales_report(self, date_from, date_to, bar_name=None):
        rows = [r for r in self.sales if not bar_name or r["Store.Name"] == bar_name]
        return {"data": rows}


class NoTransactionsOlap(FakeOlap):
    def get_packaging_writeoff_report(self, date_from, date_to, bar_name=None):
        FakeOlap.calls += 1
        return None


class NoSalesOlap(FakeOlap):
    def get_packaging_sales_report(self, date_from, date_to, bar_name=None):
        return None


class StockOnlyOlap(FakeOlap):
    sales = []


class MovementsOnlyOlap(FakeOlap):
    """Бар закрыт: только акт и инвентаризация, ни накладной, ни продаж."""
    sales = []
    transactions = [
        trans_row("Лиговский", "dish-a", "2026-08-26", "WRITEOFF", out=1.0),
        trans_row("Лиговский", "dish-a", "2026-08-27", "INVENTORY_CORRECTION", out=6.0),
    ]


class NoDataKeyOlap(FakeOlap):
    def get_packaging_writeoff_report(self, date_from, date_to, bar_name=None):
        FakeOlap.calls += 1
        return {}


class EmptyOlap(FakeOlap):
    sales = []
    transactions = []


def make_client():
    app = Flask(__name__)
    app.register_blueprint(analysis_bp)
    return app.test_client()


class PackagingEndpoint(unittest.TestCase):

    def setUp(self):
        DASHBOARD_OLAP_CACHE.clear()
        FakeOlap.calls = 0

    def test_one_trip_to_iiko_and_losses_in_response(self):
        client = make_client()
        with patch("core.packaging_loader.OlapReports", FakeOlap):
            first = client.post("/api/packaging", json={"bar": "", **PERIOD})
            second = client.post("/api/packaging", json={"bar": "", **PERIOD})
        self.assertEqual(200, first.status_code, first.get_data(as_text=True))
        self.assertEqual(200, second.status_code)
        self.assertEqual(1, FakeOlap.calls, "второй запрос за тот же период сходил в iiko")
        self.assertIn(CACHE_KEY_ALL, DASHBOARD_OLAP_CACHE)

        block = first.get_json()
        self.assertRegex(block["generated_at"], r"^\d\d:\d\d$")
        losses = block["losses"]
        self.assertEqual("шт", losses["unit"])
        self.assertEqual(24.0, losses["invoice_in"])
        self.assertEqual(5.0, losses["sold"])
        self.assertEqual(1.0, losses["writeoff"])
        # 24 − 5 − 1 = 18
        self.assertAlmostEqual(18.0, losses["balance"])
        position = block["positions"][0]
        self.assertEqual("dish-a", position["DishId"])
        self.assertEqual(1.0, position["WriteoffQty"])
        self.assertEqual(position["Id"], losses["by_item"][0]["PositionId"])

    def test_bar_scope_has_its_own_cache_key(self):
        client = make_client()
        with patch("core.packaging_loader.OlapReports", FakeOlap):
            response = client.post("/api/packaging", json={"bar": "Лиговский", **PERIOD})
        self.assertEqual(200, response.status_code)
        self.assertIn("packaging_Лиговский_2026-08-24_2026-08-31", DASHBOARD_OLAP_CACHE)
        self.assertEqual("bar", response.get_json()["scope"])

    def test_failed_transactions_report_is_502_and_not_cached(self):
        client = make_client()
        with patch("core.packaging_loader.OlapReports", NoTransactionsOlap):
            response = client.post("/api/packaging", json={"bar": "", **PERIOD})
        self.assertEqual(502, response.status_code)
        self.assertNotIn(CACHE_KEY_ALL, DASHBOARD_OLAP_CACHE, "половина данных попала в кэш")

    def test_failed_sales_report_is_502_and_not_cached(self):
        client = make_client()
        with patch("core.packaging_loader.OlapReports", NoSalesOlap):
            response = client.post("/api/packaging", json={"bar": "", **PERIOD})
        self.assertEqual(502, response.status_code)
        self.assertEqual({}, DASHBOARD_OLAP_CACHE)

    def test_stock_movements_without_sales_are_data_not_404(self):
        client = make_client()
        with patch("core.packaging_loader.OlapReports", StockOnlyOlap):
            response = client.post("/api/packaging", json={"bar": "", **PERIOD})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        block = response.get_json()
        self.assertEqual([], block["positions"])
        self.assertEqual(24.0, block["losses"]["invoice_in"])
        # Товар с потерями, но без продаж — в расхождениях, не сопоставлен.
        self.assertIsNone(block["losses"]["by_item"][0]["PositionId"])
        self.assertEqual(1, block["losses"]["diagnostics"]["unmatched_products"])

    def test_writeoff_and_inventory_without_sales_are_data_not_404(self):
        client = make_client()
        with patch("core.packaging_loader.OlapReports", MovementsOnlyOlap):
            response = client.post("/api/packaging", json={"bar": "", **PERIOD})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        losses = response.get_json()["losses"]
        self.assertEqual(0.0, losses["invoice_in"])
        # 0 − 0 − 1 − 6 = −7: остаток уменьшился без единой продажи.
        self.assertAlmostEqual(-7.0, losses["balance"])

    def test_response_without_data_key_is_502_and_not_cached(self):
        client = make_client()
        with patch("core.packaging_loader.OlapReports", NoDataKeyOlap):
            response = client.post("/api/packaging", json={"bar": "", **PERIOD})
        self.assertEqual(502, response.status_code)
        self.assertEqual({}, DASHBOARD_OLAP_CACHE)

    def test_empty_everything_is_404(self):
        client = make_client()
        with patch("core.packaging_loader.OlapReports", EmptyOlap):
            response = client.post("/api/packaging", json={"bar": "", **PERIOD})
        self.assertEqual(404, response.status_code)

    def test_inverted_period_is_400_before_iiko(self):
        client = make_client()
        with patch("core.packaging_loader.OlapReports", FakeOlap):
            response = client.post("/api/packaging",
                                   json={"bar": "", "date_from": "2026-08-30", "date_to": "2026-08-24"})
        self.assertEqual(400, response.status_code)
        self.assertEqual(0, FakeOlap.calls)


if __name__ == "__main__":
    unittest.main()
