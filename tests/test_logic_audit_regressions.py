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

    def test_waiter_requests_do_not_group_by_order_waiter_name(self):
        request = OlapReports()._build_olap_request(
            "2026-03-01",
            "2026-04-01",
            None,
            draft=True,
            include_waiter=True,
        )

        self.assertIn("WaiterName", request["groupByRowFields"])
        self.assertNotIn("OrderWaiter.Name", request["groupByRowFields"])


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

    @unittest.expectedFailure
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
