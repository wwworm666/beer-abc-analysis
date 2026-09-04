# -*- coding: utf-8 -*-
"""
Чеки с картой лояльности / без карты на дашборде (2026-09-04).

Владелец попросил показать на дашборде число чеков с картой лояльности и без
карты - как «Выручка карты/без карт» в месячном отчёте. Месячный отчёт берёт
это из ОТДЕЛЬНОГО RFM-запроса; дашборд вместо второго запроса получил поле
Delivery.CustomerCardNumber в едином OLAP-запросе (get_all_sales_report).

Что защищают тесты:

1. Формула. Чек «с картой», если Delivery.CustomerCardNumber непусто (после strip)
   хотя бы в одной его строке; пусто / одни пробелы / отсутствующий ключ = без карты.
   Инварианты: card + nocard == total_checks; card_revenue + nocard_revenue == total.

2. Пустой период не роняет расчёт долей (ZeroDivisionError).

3. Регрессия OLAP-запроса: если Delivery.CustomerCardNumber выпадет из
   groupByRowFields, метрики молча обнулятся - iiko не вернёт ошибку. Заодно
   проверяем, что aggregateFields не изменились (единый запрос питает все метрики).

4. Сквозной путь /api/dashboard-analytics: snake_case -> camelCase маппинг и
   строки table_data.

Сеть не трогается: OLAP замокан.

Запуск:
    py -3 -m unittest -v tests.test_dashboard_loyalty_checks
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

CARD_FIELD = "Delivery.CustomerCardNumber"
MISSING = object()  # маркер «ключа нет в строке»


def olap_row(order_id, revenue, card=MISSING, category="Напитки Розлив"):
    """Строка единого OLAP-отчёта дашборда с минимально нужными полями."""
    row = {
        "UniqOrderId.Id": order_id,
        "DishDiscountSumInt": revenue,
        "DishGroup.TopParent": category,
        "ProductCostBase.ProductCost": 0,
        "DiscountSum": 0,
    }
    if card is not MISSING:
        row[CARD_FIELD] = card
    return row


# Заказ A - карта; B - пустая строка; C - одни пробелы; D - ключа нет вовсе.
FIXTURE_ROWS = [
    olap_row("A", 300, card="79001112233"),
    olap_row("A", 200, card="79001112233", category="ЕДА"),
    olap_row("B", 150, card=""),
    olap_row("C", 100, card="   "),
    olap_row("C", 50, card="   ", category="Напитки Фасовка"),
    olap_row("D", 250),
]
FIXTURE_CARD_REVENUE = 500.0    # A: 300 + 200
FIXTURE_NOCARD_REVENUE = 550.0  # B 150 + C 150 + D 250
FIXTURE_TOTAL_REVENUE = 1050.0


class FixtureOlap:
    """iiko отвечает фиксированным набором строк (см. FIXTURE_ROWS)."""

    def __init__(self):
        self.api = type("Api", (), {"base_url": "https://example.invalid/resto/api"})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_all_sales_report(self, date_from, date_to, bar_name=None):
        return {"data": [dict(r) for r in FIXTURE_ROWS]}


def make_client():
    app = Flask(__name__)
    app.register_blueprint(dashboard_bp)
    return app.test_client()


class CardChecksFormula(unittest.TestCase):
    """calculate_metrics: чеки и выручка с картой / без карты."""

    def setUp(self):
        self.calc = DashboardMetrics()

    def test_fixture_split_and_invariants(self):
        metrics = self.calc.calculate_metrics({"data": FIXTURE_ROWS})

        self.assertEqual(4, metrics["total_checks"])
        self.assertEqual(1, metrics["card_checks"])
        self.assertEqual(3, metrics["nocard_checks"])
        self.assertEqual(25.0, metrics["card_checks_share"])
        self.assertEqual(FIXTURE_CARD_REVENUE, metrics["card_revenue"])
        self.assertEqual(FIXTURE_NOCARD_REVENUE, metrics["nocard_revenue"])

        # Инварианты
        self.assertEqual(metrics["total_checks"], metrics["card_checks"] + metrics["nocard_checks"])
        self.assertAlmostEqual(
            metrics["total_revenue"],
            metrics["card_revenue"] + metrics["nocard_revenue"],
            places=2,
        )
        self.assertEqual(FIXTURE_TOTAL_REVENUE, metrics["total_revenue"])

    def test_any_row_rule_counts_mixed_order_once_as_card(self):
        """Чек с пустой картой в одной строке и картой в другой - один чек С картой."""
        rows = [
            olap_row("E", 100, card=""),
            olap_row("E", 100, card="123"),
            olap_row("F", 70, card=""),
        ]
        metrics = self.calc.calculate_metrics({"data": rows})

        self.assertEqual(2, metrics["total_checks"])
        self.assertEqual(1, metrics["card_checks"])
        self.assertEqual(1, metrics["nocard_checks"])
        self.assertEqual(50.0, metrics["card_checks_share"])
        self.assertEqual(metrics["total_checks"], metrics["card_checks"] + metrics["nocard_checks"])
        # Выручка режется ПОСТРОЧНО (как в месячном отчёте): смешанный чек
        # даёт 100 в «карты» и 100 в «без карты»; инвариант по сумме держится.
        self.assertAlmostEqual(
            metrics["total_revenue"],
            metrics["card_revenue"] + metrics["nocard_revenue"],
            places=2,
        )

    def test_empty_data_gives_zeros_without_error(self):
        for payload in ({"data": []}, {}, None):
            metrics = self.calc.calculate_metrics(payload)
            self.assertEqual(0, metrics["card_checks"], payload)
            self.assertEqual(0, metrics["nocard_checks"], payload)
            self.assertEqual(0, metrics["card_checks_share"], payload)
            self.assertEqual(0, metrics["card_revenue"], payload)
            self.assertEqual(0, metrics["nocard_revenue"], payload)

    def test_table_data_has_loyalty_rows(self):
        metrics = self.calc.calculate_metrics({"data": FIXTURE_ROWS})
        table = {row["metric"]: row for row in self.calc.get_table_data(metrics)}

        expected = {
            "Чеки с картой": (1, "шт", "number"),
            "Чеки без карты": (3, "шт", "number"),
            "Доля чеков с картой": (25.0, "%", "percent"),
            "Выручка по картам": (FIXTURE_CARD_REVENUE, "₽", "money"),
        }
        for label, (value, unit, fmt) in expected.items():
            self.assertIn(label, table)
            self.assertEqual(value, table[label]["value"], label)
            self.assertEqual(unit, table[label]["unit"], label)
            self.assertEqual(fmt, table[label]["format"], label)

        # Новые строки идут сразу после «Списания баллов»
        labels = [row["metric"] for row in self.calc.get_table_data(metrics)]
        idx = labels.index("Списания баллов")
        self.assertEqual(
            ["Чеки с картой", "Чеки без карты", "Доля чеков с картой", "Выручка по картам"],
            labels[idx + 1:idx + 5],
        )


class OlapRequestKeepsCardField(unittest.TestCase):
    """Регрессия: без Delivery.CustomerCardNumber метрики лояльности молча обнулятся."""

    def _request(self):
        # Конструктор OlapReports создаёт IikoAPI (читает конфиг); построителю
        # запроса состояние объекта не нужно - обходим __init__.
        olap = OlapReports.__new__(OlapReports)
        return olap._build_all_sales_olap_request("2026-08-24", "2026-08-31")

    def test_group_by_rows_contains_card_field(self):
        request = self._request()
        self.assertIn(CARD_FIELD, request["groupByRowFields"])
        # Поле чека тоже обязано остаться - по нему считаются чеки
        self.assertIn("UniqOrderId.Id", request["groupByRowFields"])

    def test_aggregate_fields_unchanged(self):
        request = self._request()
        self.assertEqual(
            [
                "UniqOrderId.OrdersCount",
                "DishAmountInt",
                "DishDiscountSumInt",
                "DiscountSum",
                "ProductCostBase.ProductCost",
                "ProductCostBase.OneItem",
                "ProductCostBase.MarkUp",
            ],
            request["aggregateFields"],
        )


class DashboardAnalyticsEndpoint(unittest.TestCase):
    """/api/dashboard-analytics отдаёт метрики лояльности в camelCase и в table_data."""

    def setUp(self):
        DASHBOARD_OLAP_CACHE.clear()

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", FixtureOlap)
    def test_response_has_loyalty_metrics(self, _tap_activity):
        client = make_client()

        response = client.post(
            "/api/dashboard-analytics",
            json={"bar": "all", "date_from": "2026-08-24", "date_to": "2026-08-30"},
        )

        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        payload = response.get_json()

        self.assertEqual(4, payload["checks"])
        self.assertEqual(1, payload["cardChecks"])
        self.assertEqual(3, payload["nocardChecks"])
        self.assertEqual(25.0, payload["cardChecksShare"])
        self.assertEqual(FIXTURE_CARD_REVENUE, payload["cardRevenue"])
        self.assertEqual(FIXTURE_NOCARD_REVENUE, payload["nocardRevenue"])
        self.assertEqual(payload["checks"], payload["cardChecks"] + payload["nocardChecks"])

        table = {row["metric"]: row for row in payload["table_data"]}
        self.assertEqual(1, table["Чеки с картой"]["value"])
        self.assertEqual(3, table["Чеки без карты"]["value"])
        self.assertEqual(25.0, table["Доля чеков с картой"]["value"])
        self.assertEqual(FIXTURE_CARD_REVENUE, table["Выручка по картам"]["value"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
