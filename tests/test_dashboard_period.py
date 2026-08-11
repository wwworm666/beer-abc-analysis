# -*- coding: utf-8 -*-
"""
Регрессии единой панели периода на дашборде (2026-08-11).

Покрывает бэкенд-часть перехода на гранулярности День/Неделя/Месяц/Год:

1. Пустой период (закрытый день, будущая дата) отдаёт НУЛИ и HTTP 200,
   а не 500 «Не удалось получить данные из OLAP». Раньше листание стрелкой
   упиралось в красную ошибку на любом дне без продаж, и пустой ответ ещё
   и не кэшировался — каждый клик шёл в iiko заново.

2. /api/revenue-metrics принимает явные границы периода (period_from/period_to)
   и считает план и «Ожидаемую» относительно них, а не относительно календарного
   месяца date_from. Без period_* поведение обязано остаться прежним (месяц) —
   у пользователей неделями висят вкладки со старым JS.

Сеть не трогается: OLAP замокан.

Запуск:
    py -3 -m unittest -v tests.test_dashboard_period
"""

import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

from extensions import DASHBOARD_OLAP_CACHE  # noqa: E402
from routes.dashboard import dashboard_bp  # noqa: E402


class EmptyOlap:
    """iiko отвечает успешно, но продаж за период нет (закрытый/будущий день)."""

    calls = 0

    def __init__(self):
        self.api = type("Api", (), {"base_url": "https://example.invalid/resto/api"})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_all_sales_report(self, date_from, date_to, bar_name=None):
        EmptyOlap.calls += 1
        return {"data": []}


class BrokenOlap:
    """iiko недоступна: get_all_sales_report возвращает None."""

    def __init__(self):
        self.api = type("Api", (), {"base_url": "https://example.invalid/resto/api"})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_all_sales_report(self, date_from, date_to, bar_name=None):
        return None


def make_client():
    app = Flask(__name__)
    app.register_blueprint(dashboard_bp)
    return app.test_client()


class EmptyPeriodReturnsZeros(unittest.TestCase):
    """Пустой период — валидный ответ с нулями, а не ошибка."""

    def setUp(self):
        DASHBOARD_OLAP_CACHE.clear()
        EmptyOlap.calls = 0

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", EmptyOlap)
    def test_analytics_empty_day_returns_zero_metrics(self, _tap_activity):
        client = make_client()

        response = client.post(
            "/api/dashboard-analytics",
            json={"bar": "all", "date_from": "2026-08-11", "date_to": "2026-08-11"},
        )

        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(0, payload["revenue"])
        self.assertEqual(0, payload["checks"])
        self.assertNotIn("error", payload)

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", EmptyOlap)
    def test_empty_period_is_cached(self, _tap_activity):
        """Второй заход за тот же пустой день не идёт в iiko повторно."""
        client = make_client()
        body = {"bar": "all", "date_from": "2026-08-11", "date_to": "2026-08-11"}

        client.post("/api/dashboard-analytics", json=body)
        first_calls = EmptyOlap.calls
        client.post("/api/dashboard-analytics", json=body)

        self.assertEqual(1, first_calls)
        self.assertEqual(1, EmptyOlap.calls, "пустой период должен попадать в кэш")

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", EmptyOlap)
    def test_revenue_metrics_empty_period_returns_zeros(self, _tap_activity):
        client = make_client()

        response = client.post(
            "/api/revenue-metrics",
            json={
                "bar": "",
                "date_from": "2026-08-11",
                "date_to": "2026-08-11",
                "period_from": "2026-08-11",
                "period_to": "2026-08-11",
            },
        )

        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        self.assertEqual(0, response.get_json()["current"])

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", BrokenOlap)
    def test_olap_failure_still_returns_500(self, _tap_activity):
        """Сбой iiko обязан остаться ошибкой — его нельзя путать с пустым периодом."""
        client = make_client()

        response = client.post(
            "/api/dashboard-analytics",
            json={"bar": "all", "date_from": "2026-08-11", "date_to": "2026-08-11"},
        )

        self.assertEqual(500, response.status_code)
        self.assertIn("error", response.get_json())


class RevenueMetricsPeriodBounds(unittest.TestCase):
    """План и «Ожидаемая» на вкладке «Выручка» привязаны ко всему периоду."""

    def setUp(self):
        DASHBOARD_OLAP_CACHE.clear()

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", EmptyOlap)
    def test_explicit_month_bounds_match_legacy_request(self, _tap_activity):
        """Старый запрос (без period_*) и новый с границами месяца дают одно и то же."""
        client = make_client()

        legacy = client.post("/api/revenue-metrics", json={
            "bar": "bolshoy",
            "date_from": "2026-03-01",
            "date_to": "2026-03-31",
        }).get_json()

        explicit = client.post("/api/revenue-metrics", json={
            "bar": "bolshoy",
            "date_from": "2026-03-01",
            "date_to": "2026-03-31",
            "period_from": "2026-03-01",
            "period_to": "2026-03-31",
        }).get_json()

        self.assertEqual(legacy["plan"], explicit["plan"])
        self.assertEqual(legacy["days_in_month"], explicit["days_in_month"])
        self.assertEqual(31, explicit["days_in_month"])

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", EmptyOlap)
    def test_week_period_plan_is_smaller_than_month_plan(self, _tap_activity):
        """Недельный период должен получать НЕДЕЛЬНЫЙ план, а не месячный."""
        client = make_client()

        month = client.post("/api/revenue-metrics", json={
            "bar": "bolshoy",
            "date_from": "2026-03-01",
            "date_to": "2026-03-31",
            "period_from": "2026-03-01",
            "period_to": "2026-03-31",
        }).get_json()

        week = client.post("/api/revenue-metrics", json={
            "bar": "bolshoy",
            "date_from": "2026-03-02",
            "date_to": "2026-03-08",
            "period_from": "2026-03-02",
            "period_to": "2026-03-08",
        }).get_json()

        self.assertEqual(7, week["days_in_month"])
        self.assertGreater(month["plan"], 0, "нужен заведённый месячный план на март 2026")
        self.assertLess(week["plan"], month["plan"])
        # Неделя из 31-дневного марта: план заметно меньше месячного, но не ноль.
        self.assertGreater(week["plan"], 0)

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", EmptyOlap)
    def test_year_period_plan_exceeds_single_month(self, _tap_activity):
        """Годовой период суммирует месячные планы, а не берёт январь."""
        client = make_client()

        year = client.post("/api/revenue-metrics", json={
            "bar": "bolshoy",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "period_from": "2026-01-01",
            "period_to": "2026-12-31",
        }).get_json()

        january = client.post("/api/revenue-metrics", json={
            "bar": "bolshoy",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "period_from": "2026-01-01",
            "period_to": "2026-01-31",
        }).get_json()

        self.assertEqual(365, year["days_in_month"])
        self.assertGreater(year["plan"], january["plan"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
