# -*- coding: utf-8 -*-
"""
Разбивка карточки дашборда по сотрудникам (2026-09-04).

Владелец видел, что сумма по барменам под карточкой не сходится с карточкой
(«карточка 10к, бармен1 5к, бармен2 4к»). Замер на живых данных iiko показал:
арифметика двух путей сходилась до рубля, расходились экран (топ-5 без итога)
и источник данных - четыре отдельных OLAP-запроса без кэша против единого
запроса карточки из кэша на 10 минут, плюс сбой любого из четырёх молча
обнулял категорию. Разбивка переведена на тот же единый запрос: строки
раскладываются по AuthUser, для каждого сотрудника вызывается calculate_metrics.

Что защищают тесты:

1. calculate_metrics_by_employee: сумма выручки, чеков, прибыли и списаний по
   сотрудникам равна итогу calculate_metrics по всем строкам; пустой AuthUser
   сотрудника не даёт, но в итог входит; чек с двумя AuthUser (на живых данных
   не встречается) попадает в чеки обоих - документированное поведение.

2. Регрессия OLAP-запроса: без AuthUser в groupByRowFields разбивка молча
   опустеет - iiko не вернёт ошибку.

3. Сквозной /api/employee-metrics-breakdown: ключи фронта (= id метрик в
   config.js), наценка в процентах, сортировка по выручке, 'total' равен ответу
   /api/dashboard-analytics за тот же период, и в iiko за двумя ответами ходят
   ОДИН раз - оба эндпоинта читают один кэш, ключ 'all' и '' совпадают.

Сеть не трогается: OLAP замокан.

Запуск:
    py -3 -m unittest -v tests.test_dashboard_employee_breakdown
"""

import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

from core.dashboard_analysis import DashboardMetrics  # noqa: E402
from core.olap_reports import OlapReports  # noqa: E402
from extensions import DASHBOARD_OLAP_CACHE  # noqa: E402
from routes.dashboard import dashboard_bp  # noqa: E402
from routes.employee import employee_bp  # noqa: E402


def olap_row(order_id, revenue, cost, employee, category="Напитки Розлив", discount=0):
    """Строка единого OLAP-отчёта дашборда с минимально нужными полями."""
    return {
        "UniqOrderId.Id": order_id,
        "DishDiscountSumInt": revenue,
        "ProductCostBase.ProductCost": cost,
        "DishGroup.TopParent": category,
        "DiscountSum": discount,
        "AuthUser": employee,
    }


# Егор: чек A (розлив + кухня). Артем: чеки B (фасовка) и C (розлив + прочее).
# Чек D пробит без сотрудника (пустой AuthUser) - в итог входит, в разбивку нет.
FIXTURE_ROWS = [
    olap_row("A", 300, 100, "Егор", discount=10),
    olap_row("A", 200, 100, "Егор", category="ЕДА"),
    olap_row("B", 150, 50, "Артем", category="Напитки Фасовка"),
    olap_row("C", 100, 40, "Артем"),
    olap_row("C", 50, 10, "Артем", category="НАБОРЫ"),
    olap_row("D", 250, 100, ""),
]
FIXTURE_TOTAL_REVENUE = 1050.0
FIXTURE_TOTAL_CHECKS = 4


class FixtureOlap:
    """iiko отвечает фиксированным набором строк и считает обращения."""

    calls = 0

    def __init__(self):
        self.api = type("Api", (), {"base_url": "https://example.invalid/resto/api"})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_all_sales_report(self, date_from, date_to, bar_name=None):
        FixtureOlap.calls += 1
        return {"data": [dict(r) for r in FIXTURE_ROWS]}


def make_client():
    app = Flask(__name__)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(employee_bp)
    return app.test_client()


class MetricsByEmployee(unittest.TestCase):
    """calculate_metrics_by_employee: те же формулы, что у карточки, по каждому AuthUser."""

    def setUp(self):
        self.calc = DashboardMetrics()
        self.total = self.calc.calculate_metrics({"data": FIXTURE_ROWS})
        self.by_employee = self.calc.calculate_metrics_by_employee({"data": FIXTURE_ROWS})

    def test_employees_and_per_employee_metrics(self):
        self.assertEqual({"Егор", "Артем"}, set(self.by_employee))

        egor = self.by_employee["Егор"]
        self.assertEqual(500.0, egor["total_revenue"])
        self.assertEqual(1, egor["total_checks"])
        self.assertEqual(500.0, egor["avg_check"])
        self.assertEqual(300.0, egor["draft_revenue"])
        self.assertEqual(200.0, egor["kitchen_revenue"])
        self.assertEqual(300.0, egor["total_margin"])
        self.assertAlmostEqual(1.5, egor["avg_markup"], places=4)  # (500 - 200) / 200
        self.assertEqual(10.0, egor["loyalty_points_written_off"])

        artem = self.by_employee["Артем"]
        self.assertEqual(300.0, artem["total_revenue"])
        self.assertEqual(2, artem["total_checks"])
        self.assertEqual(150.0, artem["avg_check"])
        self.assertEqual(150.0, artem["bottles_revenue"])
        self.assertEqual(50.0, artem["other_revenue"])

    def test_additive_metrics_sum_to_total_plus_unattributed(self):
        """Σ по сотрудникам + строки без AuthUser == итог по всем строкам."""
        unattributed = self.calc.calculate_metrics({"data": [r for r in FIXTURE_ROWS if not r["AuthUser"]]})
        for key in ("total_revenue", "total_checks", "draft_revenue", "bottles_revenue",
                    "kitchen_revenue", "other_revenue", "total_margin", "loyalty_points_written_off"):
            employees_sum = sum(m[key] for m in self.by_employee.values())
            self.assertAlmostEqual(self.total[key], employees_sum + unattributed[key], places=2, msg=key)

    def test_without_unattributed_rows_sum_equals_total_exactly(self):
        rows = [r for r in FIXTURE_ROWS if r["AuthUser"]]
        total = self.calc.calculate_metrics({"data": rows})
        by_employee = self.calc.calculate_metrics_by_employee({"data": rows})
        for key in ("total_revenue", "total_checks", "total_margin", "loyalty_points_written_off"):
            self.assertAlmostEqual(total[key], sum(m[key] for m in by_employee.values()), places=2, msg=key)

    def test_empty_and_blank_authuser_are_skipped(self):
        rows = [olap_row("X", 10, 1, ""), olap_row("Y", 10, 1, "   "), olap_row("Z", 10, 1, None)]
        self.assertEqual({}, self.calc.calculate_metrics_by_employee({"data": rows}))
        self.assertEqual({}, self.calc.calculate_metrics_by_employee({"data": []}))
        self.assertEqual({}, self.calc.calculate_metrics_by_employee(None))

    def test_order_with_two_authusers_counted_for_both(self):
        """Документированное поведение: чек с двумя AuthUser - в чеках обоих."""
        rows = [olap_row("S", 60, 20, "Егор"), olap_row("S", 40, 10, "Артем")]
        total = self.calc.calculate_metrics({"data": rows})
        by_employee = self.calc.calculate_metrics_by_employee({"data": rows})
        self.assertEqual(1, total["total_checks"])
        self.assertEqual(2, sum(m["total_checks"] for m in by_employee.values()))
        # Деньги при этом не двоятся
        self.assertEqual(100.0, sum(m["total_revenue"] for m in by_employee.values()))


class OlapRequestKeepsAuthUser(unittest.TestCase):
    """Регрессия: без AuthUser в groupByRowFields разбивка молча опустеет."""

    def test_group_by_rows_contains_authuser(self):
        olap = OlapReports.__new__(OlapReports)  # builder не трогает состояние объекта
        request = olap._build_all_sales_olap_request("2026-08-24", "2026-08-31")
        self.assertIn(DashboardMetrics.EMPLOYEE_FIELD, request["groupByRowFields"])
        self.assertEqual("AuthUser", DashboardMetrics.EMPLOYEE_FIELD)


class BreakdownEndpoint(unittest.TestCase):
    """/api/employee-metrics-breakdown: те же данные и числа, что у /api/dashboard-analytics."""

    PERIOD = {"date_from": "2026-08-24", "date_to": "2026-08-30"}

    def setUp(self):
        DASHBOARD_OLAP_CACHE.clear()
        FixtureOlap.calls = 0

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", FixtureOlap)
    def test_breakdown_matches_card_and_shares_cache(self, _tap_activity):
        client = make_client()

        card = client.post("/api/dashboard-analytics", json={"bar": "", **self.PERIOD})
        self.assertEqual(200, card.status_code, card.get_data(as_text=True))
        card = card.get_json()

        response = client.post("/api/employee-metrics-breakdown", json={"venue_key": "all", **self.PERIOD})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        payload = response.get_json()

        # Один поход в iiko на оба ответа: '' и 'all' - один ключ кэша.
        self.assertEqual(1, FixtureOlap.calls)

        # Итог разбивки - буквально числа карточки (в единицах фронта).
        total = payload["total"]
        self.assertEqual("Итого", total["name"])
        self.assertEqual(card["revenue"], total["revenue"])
        self.assertEqual(card["checks"], total["checks"])
        self.assertEqual(round(card["profit"]), total["profit"])
        self.assertEqual(card["loyaltyWriteoffs"], total["loyaltyWriteoffs"])
        self.assertAlmostEqual(card["markupPercent"], total["markupPercent"], places=1)
        self.assertAlmostEqual(card["draftShare"], total["draftShare"], places=1)
        self.assertEqual(FIXTURE_TOTAL_REVENUE, total["revenue"])
        self.assertEqual(FIXTURE_TOTAL_CHECKS, total["checks"])

        # Сотрудники отсортированы по выручке, ключи - как id метрик на фронте.
        employees = payload["employees"]
        self.assertEqual(["Егор", "Артем"], [e["name"] for e in employees])
        egor = employees[0]
        for key in ("revenue", "checks", "averageCheck", "draftShare", "packagedShare", "kitchenShare",
                    "revenueDraft", "revenuePackaged", "revenueKitchen", "profit", "markupPercent",
                    "markupDraft", "markupPackaged", "markupKitchen", "loyaltyWriteoffs"):
            self.assertIn(key, egor)
        self.assertEqual(500, egor["revenue"])
        self.assertEqual(1, egor["checks"])
        self.assertEqual(150.0, egor["markupPercent"])  # дробь 1.5 -> проценты, как на карточке
        self.assertEqual(60.0, egor["draftShare"])
        self.assertEqual(300, egor["profit"])

        # Строки без сотрудника видны как разница «итог - Σ сотрудников».
        self.assertEqual(250, total["revenue"] - sum(e["revenue"] for e in employees))
        self.assertEqual(payload["period"], {"from": "2026-08-24", "to": "2026-08-30"})

    @patch("routes.dashboard.OlapReports", FixtureOlap)
    def test_requires_dates(self):
        client = make_client()
        response = client.post("/api/employee-metrics-breakdown", json={"venue_key": "all"})
        self.assertEqual(400, response.status_code)
        self.assertEqual(0, FixtureOlap.calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
