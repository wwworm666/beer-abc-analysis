# -*- coding: utf-8 -*-
"""
Offline regression suite for the April 2026 logic audit.

This file intentionally contains a mix of:
- passing guard tests that protect healthy OLAP contracts
- expected-failure tests that document confirmed open defects

Run:
    python -m unittest -v tests.test_logic_audit_regressions
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

from core.olap_reports import OlapReports
from core.revenue_metrics import RevenueMetricsCalculator
from routes.analysis import analysis_bp
from routes.dashboard import DASHBOARD_OLAP_CACHE, dashboard_bp


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "audit")


def load_fixture(filename):
    with open(os.path.join(FIXTURES_DIR, filename), "r", encoding="utf-8") as fh:
        return json.load(fh)


class FakeRevenueOlap:
    def __init__(self):
        self.api = type("Api", (), {"base_url": "https://example.invalid/resto/api"})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_beer_sales_report(self, date_from, date_to, bar_name=None):
        full_payload = load_fixture("all_sales_sample.json")
        packaged_rows = [
            row for row in full_payload["data"]
            if row.get("DishGroup.TopParent") == "Напитки Фасовка"
        ]
        return {"data": packaged_rows}

    def get_all_sales_report(self, date_from, date_to, bar_name=None):
        return load_fixture("all_sales_sample.json")


class FakeDiscountOlap:
    def __init__(self):
        self.api = type("Api", (), {"base_url": "https://example.invalid/resto/api"})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_discount_report(self, date_from, date_to, bar_name=None):
        return load_fixture("discount_order_collision.json")


class FakeDashboardOlap:
    def __init__(self):
        self.api = type("Api", (), {"base_url": "https://example.invalid/resto/api"})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_all_sales_report(self, date_from, date_to, bar_name=None):
        return load_fixture("all_sales_sample.json")


class OlapContractGuards(unittest.TestCase):
    def test_all_sales_request_keeps_unique_order_id_and_delete_filters(self):
        request = OlapReports()._build_all_sales_olap_request(
            "2026-03-01",
            "2026-04-01",
            None,
        )

        self.assertEqual("SALES", request["reportType"])
        self.assertIn("OpenDate.Typed", request["filters"])
        self.assertIn("UniqOrderId.Id", request["groupByRowFields"])
        self.assertEqual(
            ["NOT_DELETED"],
            request["filters"]["DeletedWithWriteoff"]["values"],
        )
        self.assertEqual(
            ["NOT_DELETED"],
            request["filters"]["OrderDeleted"]["values"],
        )

    def test_waiter_requests_group_by_authuser_not_order_waiter_name(self):
        # Идентичность сотрудника во всех отчётах — AuthUser ("Авторизовал"),
        # единый ключ (аудит OLAP #11). Геттеры алиасят AuthUser -> WaiterName в ответе.
        request = OlapReports()._build_olap_request(
            "2026-03-01",
            "2026-04-01",
            None,
            draft=True,
            include_waiter=True,
        )

        self.assertIn("AuthUser", request["groupByRowFields"])
        self.assertNotIn("WaiterName", request["groupByRowFields"])
        self.assertNotIn("OrderWaiter.Name", request["groupByRowFields"])

    def test_draft_sales_by_dish_groups_by_dish_id_and_author(self):
        # Страница /draft берёт из этого запроса и деньги кегов, и разрез по барменам:
        # DishId нужен для связки с кегом по GUID, AuthUser — ключ сотрудника (аудит #11).
        # OpenDate.Typed в группировке быть НЕ должно: день никем не используется, а число
        # строк умножал на длину периода.
        olap = OlapReports()
        olap.token = "test-token"
        captured = {}

        def capture(_self, request_body, tag):
            captured.update(request_body)
            return {"data": []}

        with patch.object(OlapReports, "_post_olap_interactive", capture):
            olap.get_draft_sales_by_dish("2026-03-01", "2026-04-01")

        self.assertEqual("SALES", captured["reportType"])
        self.assertIn("DishId", captured["groupByRowFields"])
        self.assertIn("AuthUser", captured["groupByRowFields"])
        self.assertNotIn("WaiterName", captured["groupByRowFields"])
        self.assertNotIn("OrderWaiter.Name", captured["groupByRowFields"])
        self.assertNotIn("OpenDate.Typed", captured["groupByRowFields"])
        self.assertIn("OpenDate.Typed", captured["filters"])


class PackagingReportBuilders(unittest.TestCase):
    """Построители отчётов страницы /packaging (2026-09-19): проводки по фасовке и
    продажи с DishId. Общий SALES-построитель без флага форму строки не меняет —
    им пользуются revenue_metrics и knowledge_graph."""

    def _capture(self, call):
        olap = OlapReports()
        olap.token = "test-token"
        captured = {}

        def capture(_self, request_body, tag):
            captured.update(request_body)
            return {"data": []}

        with patch.object(OlapReports, "_post_olap_interactive", capture):
            call(olap)
        return captured

    def test_packaging_writeoff_report_filters_bottles_group(self):
        body = self._capture(lambda o: o.get_packaging_writeoff_report("2026-03-01", "2026-04-01"))
        self.assertEqual("TRANSACTIONS", body["reportType"])
        self.assertEqual(["Напитки Фасовка"], body["filters"]["Product.TopParent"]["values"])
        for field in ("Product.Id", "Product.Name", "Product.MeasureUnit", "TransactionType"):
            self.assertIn(field, body["groupByRowFields"])
        self.assertNotIn("Account.Name", body["filters"])

    def test_packaging_writeoff_report_filters_bar_by_account(self):
        body = self._capture(lambda o: o.get_packaging_writeoff_report("2026-03-01", "2026-04-01", "Лиговский"))
        self.assertEqual(["Лиговский"], body["filters"]["Account.Name"]["values"])

    def test_draft_writeoff_report_unchanged_after_refactor(self):
        body = self._capture(lambda o: o.get_draft_writeoff_report("2026-03-01", "2026-04-01"))
        self.assertEqual(["Напитки Розлив"], body["filters"]["Product.TopParent"]["values"])
        # Розливу день нужен: недельные корзины XYZ строятся из проводок.
        self.assertIn("DateTime.DateTyped", body["groupByRowFields"])

    def test_packaging_writeoff_report_has_no_day(self):
        """Фасовке день проводки не нужен (баланс — суммы за период, XYZ — из
        продаж), а в группировке он умножал строки на число дней (2026-09-26)."""
        body = self._capture(lambda o: o.get_packaging_writeoff_report("2026-03-01", "2026-04-01"))
        self.assertNotIn("DateTime.DateTyped", body["groupByRowFields"])
        self.assertIn("TransactionType", body["groupByRowFields"])

    def test_packaging_sales_report_is_lean_and_interactive(self):
        """Продажи фасовки: только три агрегата, которые читает расчёт, и путь с
        повтором (_post_olap_interactive), а не одна попытка на 30 с."""
        body = self._capture(lambda o: o.get_packaging_sales_report("2026-03-01", "2026-04-01"))
        self.assertEqual(["DishAmountInt", "DishDiscountSumInt", "ProductCostBase.ProductCost"],
                         body["aggregateFields"])
        for field in ("Store.Name", "DishName", "DishGroup.ThirdParent", "DishForeignName",
                      "OpenDate.Typed", "DishId"):
            self.assertIn(field, body["groupByRowFields"])

    def test_packaging_sales_report_requests_dish_id_through_public_path(self):
        """Публичный путь get_packaging_sales_report -> get_beer_sales_report ->
        _build_olap_request: флаг должен доехать до тела запроса."""
        olap = OlapReports()
        olap.token = "test-token"
        bodies = []

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"data": []}

        def fake_post(url, params=None, json=None, headers=None, timeout=None):
            bodies.append(json)
            return FakeResponse()

        with patch("core.olap_reports.requests.post", fake_post):
            olap.get_packaging_sales_report("2026-03-01", "2026-04-01")
            olap.get_beer_sales_report("2026-03-01", "2026-04-01")
        self.assertEqual(2, len(bodies))
        self.assertEqual("SALES", bodies[0]["reportType"])
        self.assertIn("DishId", bodies[0]["groupByRowFields"])
        self.assertNotIn("DishId", bodies[1]["groupByRowFields"])

    def test_sales_builder_adds_dish_id_only_on_request(self):
        olap = OlapReports()
        plain = olap._build_olap_request("2026-03-01", "2026-04-01")
        self.assertNotIn("DishId", plain["groupByRowFields"])
        self.assertEqual(["Напитки Фасовка"], plain["filters"]["DishGroup.TopParent"]["values"])
        with_id = olap._build_olap_request("2026-03-01", "2026-04-01", include_dish_id=True)
        self.assertIn("DishId", with_id["groupByRowFields"])
        self.assertEqual(plain["aggregateFields"], with_id["aggregateFields"])


class AssemblyCachePruneTests(unittest.TestCase):
    """Кэш связки «блюдо -> кег» заводит файл на каждый период; до 2026-09-26
    файлы копились без конца. Чистка удаляет только старые файлы связки."""

    def test_old_files_removed_fresh_and_foreign_kept(self):
        import tempfile
        import time
        directory = tempfile.mkdtemp()
        olap = OlapReports()
        olap._assembly_cache_dir = lambda: directory
        old = os.path.join(directory, "assembly_map_v2_2026-01-01_2026-01-08.json")
        fresh = os.path.join(directory, "assembly_map_v2_2026-09-01_2026-09-08.json")
        foreign = os.path.join(directory, "nomenclature_full.json")
        for path in (old, fresh, foreign):
            with open(path, "w", encoding="utf-8") as f:
                f.write("{}")
        past = time.time() - (OlapReports.ASSEMBLY_CACHE_KEEP_DAYS + 1) * 86400
        os.utime(old, (past, past))
        os.utime(foreign, (past, past))
        target = olap._assembly_cache_path("2026-09-20", "2026-09-27")
        olap._write_assembly_cache(target, {"dish": [["keg", 0.5]]})
        names = set(os.listdir(directory))
        self.assertNotIn(os.path.basename(old), names)
        self.assertIn(os.path.basename(fresh), names)
        self.assertIn(os.path.basename(foreign), names)
        self.assertIn(os.path.basename(target), names)


class AuditExpectedFailures(unittest.TestCase):
    @unittest.expectedFailure
    @patch("core.revenue_metrics.OlapReports", FakeRevenueOlap)
    def test_revenue_metrics_should_use_full_sales_source(self):
        calculator = RevenueMetricsCalculator()

        actual_revenue = calculator._calculate_actual_revenue(
            "2026-03-01",
            "2026-03-31",
            "",
        )

        # Desired behavior: current fact revenue must include draft, bottles and kitchen.
        self.assertEqual(600.0, actual_revenue)

    @patch("routes.analysis.OlapReports", FakeDiscountOlap)
    def test_discount_store_summary_should_not_collapse_same_order_number_on_different_days(self):
        app = Flask(__name__)
        app.register_blueprint(analysis_bp)
        client = app.test_client()

        response = client.post(
            "/api/discount-analyze",
            json={
                "bar": "",
                "date_from": "2026-03-01",
                "date_to": "2026-03-31",
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        orders_count = payload["stores_summary"]["Loyalty"][0]["orders_count"]

        # Desired behavior: same OrderNum on different dates must count as two orders.
        self.assertEqual(2, orders_count)

    @unittest.expectedFailure
    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", FakeDashboardOlap)
    def test_dashboard_table_markup_should_match_top_level_percent_units(self, _olap, _tap_activity):
        DASHBOARD_OLAP_CACHE.clear()

        app = Flask(__name__)
        app.register_blueprint(dashboard_bp)
        client = app.test_client()

        response = client.post(
            "/api/dashboard-analytics",
            json={
                "bar": "all",
                "date_from": "2026-03-01",
                "date_to": "2026-03-31",
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()

        markup_row = next(
            row for row in payload["table_data"]
            if row.get("metric") == "% наценки"
        )

        # Desired behavior: table_data must use the same percent units as markupPercent.
        self.assertAlmostEqual(
            payload["markupPercent"],
            markup_row["value"],
            places=2,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
