# -*- coding: utf-8 -*-
"""
Крепкий алкоголь — отдельная категория дашборда (2026-11-03).

На Лиговском с 09.10.2026 продаётся группа iiko 1-го уровня «Крепкий алкоголь»
(DishGroup.TopParent): порции виски, рома, водки, мескаля, портвейна и вина. До
правки её строки молча уходили в скрытое «Прочее»: выручка сети их включала, но ни
одной карточки, доли или наценки у категории не было. Замер за 04.10–02.11.2026:
37 988,76 ₽ выручки, 10 679,48 ₽ себестоимости, 62 порции, 29 чеков — только
Лиговский.

Что защищают тесты:

1. Расчёт (DashboardMetrics.calculate_metrics): строки группы «Крепкий алкоголь» —
   в strong_*, а не в other_*; пять категорий не пересекаются: выручки и маржи
   складываются в итог, доли — в 100%; наценка — агрегатом, как «Итого» в iiko.
2. Ключи экрана: revenueStrong / strongShare / markupStrong (наценка ×100); каждый
   actualKey карточек config.js отдаёт маршрут; сквозной /api/dashboard-analytics.
3. Детали карточек: секции трёх новых карточек сходятся с карточкой; строка
   «Крепкий алкоголь» в секциях «Категории» есть только при его продажах.
4. Разбивка по сотрудникам: ключи крепкого в строках, сумма выручки = карточке.
5. Планы: поля схемы, дефолт 0 = «не задан», сумма долей с крепким = 100 ± 1, доля
   ≤ 100; план периода: выручка складывается, доля — среднее с нулями, наценка —
   среднее только там, где она задана.
6. Выгрузка Excel и сравнение периодов: строки крепкого с фактом экрана; у периода
   без крепкого строк нет (как группы на экране).

Сеть не трогается: OLAP, журнал кранов и планы подменены.
Запуск: py -3 -m pytest -q tests/test_dashboard_strong_alcohol.py
"""

import json
import os
import re
import sys
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch

from flask import Flask

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

from core import dashboard_details as details  # noqa: E402
from core.dashboard_analysis import DashboardMetrics  # noqa: E402
from core.dashboard_details import CARD_SECTIONS, METRIC_IDS, build_card_details  # noqa: E402
from core.plans_manager import PlansManager  # noqa: E402
from extensions import DASHBOARD_OLAP_CACHE  # noqa: E402
from routes.dashboard import (  # noqa: E402
    DASHBOARD_FRONTEND_KEYS, MARKUP_FRONTEND_KEYS, dashboard_bp, map_dashboard_metrics,
)
from routes.employee import employee_bp  # noqa: E402

STRONG = "Крепкий алкоголь"
DRAFT, BOTTLES, KITCHEN = "Напитки Розлив", "Напитки Фасовка", "ЕДА"
LIG = "Лиговский"
STRONG_KEYS = ("revenueStrong", "strongShare", "markupStrong")


def olap_row(order_id, dish, category, revenue, cost, units=1, day="2026-10-30",
             employee="Егор", discount=0.0, card=""):
    """Строка единого OLAP-запроса дашборда с полями, которые читают расчёт и детали."""
    return {
        "Store.Name": LIG, "DishName": dish, "DishGroup.TopParent": category,
        "DishForeignName": "", "OpenDate.Typed": day, "UniqOrderId.Id": order_id,
        "Delivery.CustomerCardNumber": card, "AuthUser": employee,
        "DishAmountInt": units, "DishDiscountSumInt": revenue, "DiscountSum": discount,
        "ProductCostBase.ProductCost": cost,
    }


# Неделя 26.10 (Пн) — 01.11.2026 на Лиговском. Позиции крепкого — настоящие названия iiko.
ROWS = [
    olap_row("A", "Хеллес (0,5)", DRAFT, 1000.0, 300.0, units=2),
    olap_row("A", "Порция Джим Бим бурбон, 40 мл", STRONG, 1350.0, 287.0, units=3),
    olap_row("B", "Бургер", KITCHEN, 800.0, 300.0, employee="Артем", day="2026-10-31"),
    olap_row("B", "Порция Лафройг, 40 мл", STRONG, 1955.0, 557.0, employee="Артем", day="2026-10-31",
             discount=100.0, card="79161234567"),
    olap_row("C", "Вайнштефан бут.", BOTTLES, 600.0, 300.0, units=2, employee="Артем", day="2026-11-01"),
    # Позиция без себестоимости (нет техкарты): в наценке участвует только выручкой.
    olap_row("C", "Порция Пила де Винь водка, 40 мл", STRONG, 690.0, 0.0, employee="Артем", day="2026-11-01"),
    olap_row("D", "Чай", "Чай/Кофе", 200.0, 20.0, day="2026-11-01"),
]
STRONG_REVENUE = 1350.0 + 1955.0 + 690.0          # 3 995
STRONG_COST = 287.0 + 557.0 + 0.0                  # 844
TOTAL_REVENUE = 1000.0 + 800.0 + 600.0 + 200.0 + STRONG_REVENUE   # 6 595
PERIOD = ("2026-10-26", "2026-11-01")


class FixtureOlap:
    """iiko отвечает строками ROWS за неделю PERIOD; другой период — пустой (закрытый день)."""

    def __init__(self):
        self.api = type("Api", (), {"base_url": "https://example.invalid/resto/api"})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_all_sales_report(self, date_from, date_to, bar_name=None):
        return {"data": [dict(r) for r in ROWS] if date_from == PERIOD[0] else []}


def make_client():
    app = Flask(__name__)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(employee_bp)
    return app.test_client()


class CategorySplit(unittest.TestCase):
    """calculate_metrics: крепкий алкоголь — своя категория, не «Прочее»."""

    def setUp(self):
        self.calc = DashboardMetrics()
        self.m = self.calc.calculate_metrics({"data": ROWS})

    def test_group_name_is_iiko_top_parent(self):
        self.assertEqual("Крепкий алкоголь", DashboardMetrics.TOP_PARENT_STRONG)

    def test_strong_rows_leave_other(self):
        self.assertEqual(STRONG_REVENUE, self.m["strong_revenue"])
        self.assertEqual(200.0, self.m["other_revenue"], "в «Прочем» остался только чай")
        self.assertEqual(round(STRONG_REVENUE - STRONG_COST, 2), self.m["strong_margin"])
        self.assertEqual(round(STRONG_REVENUE / TOTAL_REVENUE * 100, 2), self.m["strong_share"])

    def test_markup_is_aggregate_like_iiko_total(self):
        # (Σ выручка − Σ себестоимость) / Σ себестоимость; водка без себестоимости — выручкой.
        self.assertEqual(round((STRONG_REVENUE - STRONG_COST) / STRONG_COST, 4), self.m["strong_markup"])

    def test_five_categories_partition_the_total(self):
        cats = ("draft", "bottles", "kitchen", "strong", "other")
        self.assertAlmostEqual(self.m["total_revenue"], sum(self.m[c + "_revenue"] for c in cats), places=2)
        self.assertAlmostEqual(self.m["total_margin"], sum(self.m[c + "_margin"] for c in cats), places=2)
        self.assertAlmostEqual(100.0, sum(self.m[c + "_share"] for c in cats), delta=0.05)
        self.assertEqual(TOTAL_REVENUE, self.m["total_revenue"])

    def test_bar_without_strong_and_empty_period_give_zeros(self):
        without = self.calc.calculate_metrics({"data": [r for r in ROWS if r["DishGroup.TopParent"] != STRONG]})
        empty = self.calc.calculate_metrics({"data": []})
        for metrics in (without, empty):
            for key in ("strong_revenue", "strong_share", "strong_markup", "strong_margin"):
                self.assertEqual(0, metrics[key], key)

    def test_table_data_rows_appended_at_the_end(self):
        table = self.calc.get_table_data(self.m)
        self.assertEqual(["Доля крепкого алкоголя", "Выручка крепкий алкоголь", "Наценка крепкий алкоголь"],
                         [row["metric"] for row in table[-3:]])
        self.assertEqual(STRONG_REVENUE, table[-2]["value"])
        self.assertEqual("Выручка по картам", table[-4]["metric"], "прежние строки не сдвинулись")


class ScreenKeys(unittest.TestCase):
    """Ключи экрана: config.js читает ровно то, что отдаёт маршрут."""

    def test_mapping_and_markup_percent(self):
        m = DashboardMetrics().calculate_metrics({"data": ROWS})
        mapped = map_dashboard_metrics(m)
        self.assertEqual(STRONG_REVENUE, mapped["revenueStrong"])
        self.assertEqual(m["strong_share"], mapped["strongShare"])
        self.assertAlmostEqual(m["strong_markup"] * 100, mapped["markupStrong"], places=6)
        self.assertIn("markupStrong", MARKUP_FRONTEND_KEYS)

    def test_every_card_actual_key_is_served(self):
        with open(os.path.join(REPO_ROOT, "static", "js", "dashboard", "core", "config.js"),
                  encoding="utf-8") as f:
            config = f.read()
        actual_keys = re.findall(r"actualKey: '([A-Za-z]+)'", config)
        self.assertEqual(20, len(actual_keys))
        served = set(DASHBOARD_FRONTEND_KEYS.values())
        self.assertEqual([], [k for k in actual_keys if k not in served])

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", FixtureOlap)
    def test_dashboard_analytics_end_to_end(self, *_mocks):
        DASHBOARD_OLAP_CACHE.clear()
        response = make_client().post("/api/dashboard-analytics", json={
            "bar": "ligovskiy", "date_from": PERIOD[0], "date_to": PERIOD[1]})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        body = response.get_json()
        self.assertEqual(STRONG_REVENUE, body["revenueStrong"])
        self.assertEqual(round(STRONG_REVENUE / TOTAL_REVENUE * 100, 2), body["strongShare"])
        self.assertAlmostEqual((STRONG_REVENUE - STRONG_COST) / STRONG_COST * 100, body["markupStrong"], places=2)
        self.assertEqual(TOTAL_REVENUE, body["revenue"])
        DASHBOARD_OLAP_CACHE.clear()


class CardDetails(unittest.TestCase):
    """Секции трёх карточек крепкого и строка «Крепкий алкоголь» в «Категориях»."""

    DATA = {"data": ROWS}

    def build(self, metric, data=None):
        return {s["id"]: s for s in build_card_details(metric, data or self.DATA, "ligovskiy", *PERIOD)}

    def test_registry(self):
        self.assertEqual(["revenueStrong", "strongShare", "markupStrong"], METRIC_IDS[-3:])
        self.assertEqual(["top_revenue", "days"], [s["id"] for s in self.build("revenueStrong").values()])
        self.assertEqual(["top_units"], list(self.build("strongShare")))
        self.assertEqual(["top_margin", "low_markup"], list(self.build("markupStrong")))
        for metric in STRONG_KEYS:
            self.assertIn(metric, CARD_SECTIONS)

    def test_sections_match_card(self):
        m = DashboardMetrics().calculate_metrics(self.DATA)
        rev = self.build("revenueStrong")
        self.assertEqual(round(STRONG_REVENUE), rev["top_revenue"]["total"]["value"])
        self.assertEqual(["Порция Лафройг, 40 мл", "Порция Джим Бим бурбон, 40 мл",
                          "Порция Пила де Винь водка, 40 мл"], [r["name"] for r in rev["top_revenue"]["rows"]])
        self.assertEqual(round(STRONG_REVENUE), sum(r["value"] for r in rev["top_revenue"]["rows"]))
        self.assertEqual(round(STRONG_REVENUE), rev["days"]["total"]["value"])
        self.assertEqual(round(STRONG_REVENUE), sum(r["value"] for r in rev["days"]["rows"]))
        units = self.build("strongShare")["top_units"]
        self.assertEqual(5, units["total"]["value"])
        self.assertEqual("Всего порц.", units["total"]["name"])
        markup = self.build("markupStrong")
        self.assertEqual(round(m["strong_margin"]), markup["top_margin"]["total"]["value"])
        self.assertEqual(round(m["strong_markup"] * 100, 1), markup["low_markup"]["total"]["value"])
        # Водка без себестоимости не ранжируется, а названа в заметке.
        self.assertNotIn("Порция Пила де Винь водка, 40 мл", [r["name"] for r in markup["low_markup"]["rows"]])
        self.assertIn("Без себестоимости: 1 поз.", markup["low_markup"]["note"])
        for sec in list(rev.values()) + [units] + list(markup.values()):
            self.assertTrue(sec["formula"], sec["id"])
            self.assertIsNone(sec["error"], sec["id"])

    def test_categories_row_only_with_sales(self):
        with_strong = self.build("revenue")["categories"]
        names = [r["name"] for r in with_strong["rows"]]
        self.assertIn("Крепкий алкоголь", names)
        self.assertEqual(round(TOTAL_REVENUE), sum(r["value"] for r in with_strong["rows"]))
        self.assertEqual(round(STRONG_REVENUE),
                         [r for r in with_strong["rows"] if r["name"] == "Крепкий алкоголь"][0]["value"])
        for metric in ("markupPercent", "profit", "loyaltyWriteoffs"):
            self.assertIn("Крепкий алкоголь", [r["name"] for r in self.build(metric)["categories"]["rows"]], metric)
        # Бар без крепкого: строки нет, четыре прежние категории на месте.
        without = {"data": [r for r in ROWS if r["DishGroup.TopParent"] != STRONG]}
        for metric in ("revenue", "markupPercent", "profit"):
            rows = self.build(metric, without)["categories"]["rows"]
            self.assertEqual({"Розлив", "Фасовка", "Кухня", "Прочее"}, {r["name"] for r in rows}, metric)
        # Единственная скидка фикстуры была на крепком: без него списаний нет — «Нет данных».
        self.assertEqual([], self.build("loyaltyWriteoffs", without)["categories"]["rows"])

    def test_empty_period_has_no_rows(self):
        for metric in STRONG_KEYS:
            for sec in build_card_details(metric, {"data": []}, "all", *PERIOD):
                self.assertEqual([], sec["rows"], (metric, sec["id"]))
                self.assertIsNone(sec["error"])

    def test_unit_word_and_label(self):
        self.assertEqual("порц.", details.UNIT_WORD["strong"])
        self.assertEqual("Крепкий алкоголь", details.CATEGORY_LABEL["strong"])
        self.assertEqual("strong", details.category_of({"DishGroup.TopParent": STRONG}))


class EmployeeBreakdown(unittest.TestCase):

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", FixtureOlap)
    def test_rows_have_strong_keys_and_sum_to_card(self, *_mocks):
        DASHBOARD_OLAP_CACHE.clear()
        response = make_client().post("/api/employee-metrics-breakdown", json={
            "venue_key": "ligovskiy", "date_from": PERIOD[0], "date_to": PERIOD[1]})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        body = response.get_json()
        for row in body["employees"] + [body["total"]]:
            for key in STRONG_KEYS:
                self.assertIn(key, row)
        self.assertEqual(round(STRONG_REVENUE), body["total"]["revenueStrong"])
        self.assertEqual(round(STRONG_REVENUE), sum(r["revenueStrong"] for r in body["employees"]))
        artem = [r for r in body["employees"] if r["name"] == "Артем"][0]
        self.assertEqual(round(1955.0 + 690.0), artem["revenueStrong"])
        self.assertEqual(round((2645.0 - 557.0) / 557.0 * 100, 1), artem["markupStrong"])
        DASHBOARD_OLAP_CACHE.clear()


def legacy_plan(**overrides):
    """Месячный план без полей крепкого (как все планы до 2026-11-03): доли 45 + 30 + 25."""
    plan = {
        "revenue": 1000000.0, "checks": 500, "averageCheck": 2000.0,
        "draftShare": 45.0, "packagedShare": 30.0, "kitchenShare": 25.0,
        "revenueDraft": 450000.0, "revenuePackaged": 300000.0, "revenueKitchen": 250000.0,
        "markupPercent": 200.0, "profit": 500000.0,
        "markupDraft": 250.0, "markupPackaged": 180.0, "markupKitchen": 150.0,
        "loyaltyWriteoffs": 50000.0, "tapActivity": 80.0, "cardChecksShare": 70.0,
    }
    plan.update(overrides)
    return plan


# Лиговский с крепким в ноябре (3% выручки, наценка 300%), кухня уступила ему 3 п.п.
LIG_NOV = legacy_plan(kitchenShare=22.0, revenueKitchen=220000.0, strongShare=3.0,
                      revenueStrong=30000.0, markupStrong=300.0)


class PlansCase(unittest.TestCase):
    """Временный файл планов; data/ проекта не трогается."""

    PLANS = {
        "ligovskiy_2026-10": legacy_plan(),
        "ligovskiy_2026-11": LIG_NOV,
        "bolshoy_2026-11": legacy_plan(),
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "plansdashboard.json")
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"plans": self.PLANS, "metadata": {"version": "1.0"}}, f, ensure_ascii=False)
        daily = patch("core.daily_plans_generator.ensure_daily_plans_current", return_value=False)
        daily.start()
        self.addCleanup(daily.stop)
        overrides = patch.object(PlansManager, "_overrides_for_venue", return_value=lambda y, m: {})
        overrides.start()
        self.addCleanup(overrides.stop)
        self.manager = PlansManager(data_file=self.path)

    def read_plans(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)["plans"]


class PlanSchema(PlansCase):

    def test_fields_and_defaults(self):
        for key in STRONG_KEYS:
            self.assertIn(key, PlansManager.PLAN_SCHEMA)
            self.assertEqual(0.0, PlansManager.PLAN_DEFAULTS[key], key)
        self.assertEqual(("draftShare", "packagedShare", "kitchenShare", "strongShare"),
                         PlansManager.SHARE_FIELDS)
        # Старый план читается с нулями крепкого: на экране «План не задан».
        plan = self.manager.get_plan("ligovskiy_2026-10")
        self.assertEqual((0.0, 0.0, 0.0), tuple(plan[k] for k in STRONG_KEYS))

    def test_save_old_plan_still_valid_and_gets_zeros(self):
        self.assertTrue(self.manager.save_plan("varshavskaya_2026-11", legacy_plan()))
        saved = self.read_plans()["varshavskaya_2026-11"]
        self.assertEqual((0.0, 0.0, 0.0), tuple(saved[k] for k in STRONG_KEYS))

    def test_shares_sum_includes_strong(self):
        self.assertTrue(self.manager.save_plan("ligovskiy_2026-12", dict(LIG_NOV)))
        with self.assertRaisesRegex(ValueError, "Sum of shares"):
            # 45 + 30 + 25 + 3 = 103: кухня не уступила крепкому
            self.manager.save_plan("ligovskiy_2026-12", legacy_plan(strongShare=3.0))
        with self.assertRaisesRegex(ValueError, "strongShare"):
            self.manager.save_plan("ligovskiy_2026-12", legacy_plan(strongShare=120.0))
        with self.assertRaisesRegex(ValueError, "markupStrong"):
            self.manager.save_plan("ligovskiy_2026-12", dict(LIG_NOV, markupStrong=-1))
        self.assertEqual(3.0, self.read_plans()["ligovskiy_2026-12"]["strongShare"])


class PlanForPeriod(PlansCase):

    def test_single_month_as_entered(self):
        plan = self.manager.calculate_plan_for_period("ligovskiy", "2026-11-01", "2026-11-30")
        self.assertEqual((30000.0, 3.0, 300.0), tuple(plan[k] for k in STRONG_KEYS))

    def test_network_sums_revenue_averages_share_with_zeros_markup_only_where_planned(self):
        plan = self.manager.calculate_plan_for_period("all", "2026-11-01", "2026-11-30")
        self.assertEqual(30000.0, plan["revenueStrong"])     # сумма баров
        self.assertEqual(1.5, plan["strongShare"])           # (3 + 0) / 2 бара
        self.assertEqual(300.0, plan["markupStrong"])        # Большой наценку не планирует
        self.assertEqual(2, plan["_months_used"])

    def test_month_without_strong_does_not_dilute_markup(self):
        # Октябрь Лиговского без крепкого + ноябрь с ним: два полных месяца, веса по 1.
        plan = self.manager.calculate_plan_for_period("ligovskiy", "2026-10-01", "2026-11-30")
        self.assertEqual(30000.0, plan["revenueStrong"])
        self.assertEqual(1.5, plan["strongShare"])
        self.assertEqual(300.0, plan["markupStrong"])

    def test_nothing_planned_gives_zeros(self):
        plan = self.manager.calculate_plan_for_period("bolshoy", "2026-11-01", "2026-11-30")
        self.assertEqual((0.0, 0.0, 0.0), tuple(plan[k] for k in STRONG_KEYS))


@patch("routes.dashboard.plans_manager.calculate_plan_for_period", return_value=None)
@patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
@patch("routes.dashboard.OlapReports", FixtureOlap)
class ExportAndCompare(unittest.TestCase):
    """Выгрузка и сравнение: строки крепкого = экран; без продаж и плана — строк нет."""

    def setUp(self):
        DASHBOARD_OLAP_CACHE.clear()
        self.addCleanup(DASHBOARD_OLAP_CACHE.clear)
        self.client = make_client()

    def excel(self, period):
        from openpyxl import load_workbook
        response = self.client.post("/api/export/excel", json={
            "bar": "ligovskiy", "date_from": period[0], "date_to": period[1]})
        self.assertEqual(200, response.status_code, response.data[:300])
        sheet = load_workbook(BytesIO(response.data)).active
        return {label: fact for label, _plan, fact in sheet.iter_rows(min_row=5, max_col=3, values_only=True)
                if label}

    def test_excel_rows(self, *_mocks):
        rows = self.excel(PERIOD)
        self.assertEqual(STRONG_REVENUE, rows["Выручка крепкий алкоголь (₽)"])
        self.assertEqual(round(STRONG_REVENUE / TOTAL_REVENUE * 100, 2), rows["Доля крепкого алкоголя (%)"])
        self.assertIn("Наценка крепкий алкоголь (%)", rows)
        empty = self.excel(("2026-10-05", "2026-10-05"))
        self.assertFalse([label for label in empty if "крепк" in label], "у пустого периода строк крепкого нет")

    def test_compare_has_strong_metrics_equal_to_page(self, *_mocks):
        response = self.client.post("/api/comparison/periods", json={
            "venue_key": "ligovskiy", "period1_key": "_".join(PERIOD),
            "period2_key": "2026-10-19_2026-10-25"})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        comparison = response.get_json()["comparison"]
        self.assertEqual((STRONG_REVENUE, 0.0), (comparison["revenueStrong"]["period1"],
                                                 comparison["revenueStrong"]["period2"]))
        self.assertEqual("п.п.", comparison["strongShare"]["diff_unit"])
        self.assertIsNone(comparison["markupStrong"]["diff_percent"], "база 0 — Δ% не определён")


class McpSchema(unittest.TestCase):
    """Инструменты агентов знают три новые карточки и поля плана."""

    def test_card_ids_and_plan_fields(self):
        from core.mcp.tools import analytics
        tools = {spec.name: spec for spec in analytics.TOOLS}
        metric = tools["analytics_dashboard_card_details"].input_schema["properties"]["metric"]
        for key in STRONG_KEYS:
            self.assertIn(key, metric["enum"])
            self.assertIn(key, metric["description"])
            self.assertIn(key, tools["analytics_dashboard"].description)
        props = tools["analytics_plan_save"].input_schema["properties"]
        self.assertEqual(100, props["strongShare"]["maximum"])
        self.assertNotIn("strongShare", tools["analytics_plan_save"].input_schema["required"])
        self.assertIn("strongShare", tools["analytics_plan_save"].description)


if __name__ == "__main__":
    unittest.main(verbosity=2)
