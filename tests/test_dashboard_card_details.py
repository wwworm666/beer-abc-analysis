# -*- coding: utf-8 -*-
"""
Детали внутри карточки дашборда (2026-09-04): секции-вкладки раскрытой карточки.

Что защищают тесты:

1. core/dashboard_details.py считает секции из строк единого OLAP-запроса теми
   же хелперами, что и карточка: у складываемых секций Σ строк + «Остальные» ==
   «Итого», а «Итого» == числу карточки (calculate_metrics). Реестр покрывает
   все 20 id из config.js, ошибка одной секции не ломает остальные, пустой
   период даёт пустые строки без исключений.

2. Конкретные формулы: сорта розлива схлопывают объёмы, локал/импорт по стране,
   слабая наценка исключает позиции без себестоимости и упоминает их в заметке,
   «Дни» показывают все дни недели хронологически и топ-5 на длинном периоде,
   «Бары» только для «Все заведения», гости по номеру карты (без маски).

3. Ленивые источники: секция «Литры» из блока /draft (kegs[:5], доля, итог,
   ссылка), TapsManager.tap_activity_by_tap даёт то же число, что карточка.

4. Сквозной /api/dashboard-card-details: один поход в iiko на карточку и
   детали (общий кэш, '' и 'all' - один ключ), итог секции равен карточке,
   400/500/502, ленивые секции через подменённый загрузчик.

Сеть не трогается: OLAP и загрузчик /draft замоканы.

Запуск:
    py -3 -X utf8 -m unittest -v tests.test_dashboard_card_details
"""

import json
import os
import re
import sys
import unittest
from unittest.mock import patch

from flask import Flask

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

from core import dashboard_details as details  # noqa: E402
from core.dashboard_analysis import DashboardMetrics  # noqa: E402
from core.dashboard_details import (  # noqa: E402
    CARD_SECTIONS, LAZY_ONLY_METRICS, METRIC_IDS, build_card_details, normalize_date,
    section_draft_liters, section_taps,
)
from core.taps_manager import TapsManager  # noqa: E402
from extensions import DASHBOARD_OLAP_CACHE  # noqa: E402
from routes.analysis import analysis_bp  # noqa: E402
from routes.dashboard import dashboard_bp  # noqa: E402
from routes.employee import employee_bp  # noqa: E402


def olap_row(order_id, store, day, dish, category, revenue, cost, units=1, discount=0,
             country='', card='', employee='Егор'):
    """Строка единого OLAP-отчёта дашборда со всеми полями, которые читают секции."""
    return {
        "Store.Name": store,
        "DishName": dish,
        "DishGroup.TopParent": category,
        "DishForeignName": country,
        "OpenDate.Typed": day,
        "UniqOrderId.Id": order_id,
        "Delivery.CustomerCardNumber": card,
        "AuthUser": employee,
        "DishAmountInt": units,
        "DishDiscountSumInt": revenue,
        "DiscountSum": discount,
        "ProductCostBase.ProductCost": cost,
    }


DRAFT, BOTTLES, KITCHEN, OTHER = "Напитки Розлив", "Напитки Фасовка", "ЕДА", "Чай/Кофе"
LIG, KREM = "Лиговский", "Кременчугская"
CARD_1, CARD_2 = "79161234567", "100001"

# Неделя 24.08 (Пн) - 30.08.2026, продажи в три дня.
FIXTURE_ROWS = [
    # Чек A: Лиговский, Пн, карта 1, Егор - два объёма одного сорта + бургер
    olap_row("A", LIG, "2026-08-24", "ФестХаус Хеллес (0,5)", DRAFT, 600, 200, units=2, card=CARD_1),
    olap_row("A", LIG, "2026-08-24", "ФестХаус Хеллес (0,3)", DRAFT, 200, 70, units=1, card=CARD_1),
    olap_row("A", LIG, "2026-08-24", "Бургер", KITCHEN, 400, 150, units=1, discount=40, card=CARD_1),
    # Чек B: Кременчугская, Вт, без карты, Артем - фасовка импорт и локал
    olap_row("B", KREM, "2026-08-25", "Вайнштефан бут.", BOTTLES, 900, 500, units=3, country="Германия", employee="Артем"),
    olap_row("B", KREM, "2026-08-25", "Балтика бут.", BOTTLES, 300, 150, units=2, country="Россия", employee="Артем"),
    # Чек C: Лиговский, Ср, карта 1, Артем - розлив без себестоимости и прочее
    olap_row("C", LIG, "2026-08-26", "Крафт ИПА (0,5)", DRAFT, 350, 0, units=1, card=CARD_1, employee="Артем"),
    olap_row("C", LIG, "2026-08-26", "Чай", OTHER, 100, 20, units=1, discount=10, card=CARD_1, employee="Артем"),
    # Чек D: Кременчугская, Ср, карта 2, Егор - кухня
    olap_row("D", KREM, "2026-08-26", "Бургер", KITCHEN, 800, 300, units=2, card=CARD_2),
    olap_row("D", KREM, "2026-08-26", "Фри", KITCHEN, 150, 40, units=1, card=CARD_2),
    # Чек E: Лиговский, Вт, без карты и без сотрудника
    olap_row("E", LIG, "2026-08-25", "ФестХаус Хеллес (0,5)", DRAFT, 300, 100, units=1, employee=""),
]
TOTAL_REVENUE = 4100.0
TOTAL_CHECKS = 5
PERIOD = {"date_from": "2026-08-24", "date_to": "2026-08-30"}
DATA = {"data": FIXTURE_ROWS}


def build(metric, venue="all", date_from=PERIOD["date_from"], date_to=PERIOD["date_to"], plans=None):
    return build_card_details(metric, DATA, venue, date_from, date_to, plans)


def section(metric, sid, **kwargs):
    found = [s for s in build(metric, **kwargs) if s["id"] == sid]
    assert found, f"{metric}: нет секции {sid}"
    return found[0]


def shown_sum(sec):
    total = sum(r["value"] for r in sec["rows"])
    if sec["rest"]:
        total += sec["rest"]["value"]
    return total


class RegistryAndInvariants(unittest.TestCase):
    """Реестр покрывает config.js; складываемые секции сходятся с карточкой."""

    def test_metric_ids_match_config_js(self):
        with open(os.path.join(REPO_ROOT, "static", "js", "dashboard", "core", "config.js"),
                  encoding="utf-8") as f:
            config = f.read()
        metrics_block = config[config.index("export const METRICS = ["):]
        ids = re.findall(r"^\s+id: '([A-Za-z]+)',", metrics_block, flags=re.MULTILINE)
        self.assertEqual(ids, METRIC_IDS)
        self.assertEqual(set(ids), set(CARD_SECTIONS))

    # (метрика, секция) -> чем должен быть «Итого»: ключ calculate_metrics и формат.
    # 'markup' = дробь x100 до 0,1; 'units:<категория>' = category_units по категории.
    CARD_TOTALS = {
        ("revenue", "days"): ("total_revenue", "money"), ("revenue", "stores"): ("total_revenue", "money"),
        ("revenue", "categories"): ("total_revenue", "money"), ("revenue", "weekdays"): ("total_revenue", "money"),
        ("checks", "days"): ("total_checks", "number"), ("checks", "stores"): ("total_checks", "number"),
        ("checks", "weekdays"): ("total_checks", "number"),
        ("averageCheck", "card_split"): ("avg_check", "money"), ("averageCheck", "stores"): ("avg_check", "money"),
        ("averageCheck", "days"): ("avg_check", "money"),
        ("markupPercent", "categories"): ("avg_markup", "markup"), ("markupPercent", "top_margin"): ("total_margin", "money"),
        ("markupPercent", "low_markup"): ("avg_markup", "markup"),
        ("draftShare", "categories"): ("total_revenue", "money"),
        ("revenueDraft", "top_revenue"): ("draft_revenue", "money"), ("revenueDraft", "local_import"): ("draft_revenue", "money"),
        ("markupDraft", "top_margin"): ("draft_margin", "money"), ("markupDraft", "low_markup"): ("draft_markup", "markup"),
        ("packagedShare", "top_units"): ("units:" + BOTTLES, "number"),
        ("packagedShare", "local_import"): ("bottles_revenue", "money"), ("packagedShare", "categories"): ("total_revenue", "money"),
        ("revenuePackaged", "top_revenue"): ("bottles_revenue", "money"), ("revenuePackaged", "local_import"): ("bottles_revenue", "money"),
        ("markupPackaged", "top_margin"): ("bottles_margin", "money"), ("markupPackaged", "low_markup"): ("bottles_markup", "markup"),
        ("kitchenShare", "top_units"): ("units:" + KITCHEN, "number"), ("kitchenShare", "categories"): ("total_revenue", "money"),
        ("revenueKitchen", "top_revenue"): ("kitchen_revenue", "money"), ("revenueKitchen", "days"): ("kitchen_revenue", "money"),
        ("markupKitchen", "top_margin"): ("kitchen_margin", "money"), ("markupKitchen", "low_markup"): ("kitchen_markup", "markup"),
        ("profit", "categories"): ("total_margin", "money"), ("profit", "top_margin"): ("total_margin", "money"),
        ("profit", "stores"): ("total_margin", "money"),
        ("loyaltyWriteoffs", "categories"): ("loyalty_points_written_off", "money"),
        ("loyaltyWriteoffs", "top_discount"): ("loyalty_points_written_off", "money"),
        ("loyaltyWriteoffs", "days"): ("loyalty_points_written_off", "money"),
        ("cardChecks", "guests"): ("card_checks", "number"), ("cardChecks", "days"): ("card_checks", "number"),
        ("cardChecks", "stores"): ("card_checks", "number"),
        ("nocardChecks", "days"): ("nocard_checks", "number"), ("nocardChecks", "stores"): ("nocard_checks", "number"),
        ("cardChecksShare", "stores"): ("card_checks_share", "percent"), ("cardChecksShare", "days"): ("card_checks_share", "percent"),
        ("cardRevenue", "guests"): ("card_revenue", "money"), ("cardRevenue", "card_split"): ("total_revenue", "money"),
        ("cardRevenue", "stores"): ("card_revenue", "money"),
    }

    def test_sections_sum_to_total_and_total_equals_card(self):
        """Каждая не-ленивая секция каждой из 20 метрик: строки сходятся с «Итого», «Итого» = карточка."""
        calc = DashboardMetrics()
        card = calc.calculate_metrics(DATA)
        seen = set()
        for metric in METRIC_IDS:
            for sec in build(metric):
                if sec["lazy"]:
                    continue
                label = f"{metric}/{sec['id']}"
                self.assertIsNone(sec["error"], f"{label}: {sec['error']}")
                self.assertTrue(sec["formula"], f"{label}: формула пуста")
                self.assertLessEqual(len(sec["rows"]), max(details.TOP_N, 7), label)
                if sec["additive"] and sec["total"]:
                    values = [r["value"] for r in sec["rows"]] + [sec["total"]["value"]]
                    if all(isinstance(v, int) for v in values):
                        # Целые счётчики не округлялись - тождество точное.
                        self.assertEqual(shown_sum(sec), sec["total"]["value"], f"{label}: строки не сходятся с итогом")
                    else:
                        self.assertLessEqual(abs(shown_sum(sec) - sec["total"]["value"]), len(sec["rows"]),
                                             f"{label}: строки не сходятся с итогом")
                    # Фикстура размечена полностью: остаток - только «Остальные», и не отрицательный.
                    if sec["rest"]:
                        self.assertTrue(sec["rest"]["name"].startswith("Остальные"), f"{label}: {sec['rest']}")
                        self.assertGreaterEqual(sec["rest"]["value"], 0, label)
                    if sec["total"]["value"] > 0:
                        shares = sum(r.get("share", 0) for r in sec["rows"])
                        if sec["rest"]:
                            shares += sec["rest"].get("share", 0)
                        self.assertAlmostEqual(100.0, shares, delta=0.5, msg=f"{label}: доли")
                spec = self.CARD_TOTALS.get((metric, sec["id"]))
                if spec is None:
                    continue
                key, fmt = spec
                if fmt == "markup":
                    expected = round(card[key] * 100, 1)
                elif key.startswith("units:"):
                    expected = details._round(calc.category_units(FIXTURE_ROWS, key[len("units:"):]), "number")
                else:
                    expected = details._round(card[key], fmt)
                self.assertEqual(expected, sec["total"]["value"], f"{label}: итог != карточка")
                seen.add((metric, sec["id"]))
        # Таблица ожиданий покрывает все не-ленивые секции реестра.
        self.assertEqual(set(self.CARD_TOTALS), seen)

    def test_unassigned_and_duplicated_rows_are_visible(self):
        """Чеки без бара/даты и чек в двух барах - остаток показывается точно, не прячется."""
        rows = FIXTURE_ROWS + [olap_row("F", "", "", "Фри", KITCHEN, 150, 40)]
        data = {"data": rows}
        by_id = {s["id"]: s for s in build_card_details("checks", data, "all", PERIOD["date_from"], PERIOD["date_to"])}
        self.assertEqual({"name": "Без разбивки", "value": 1, "share": round(1 / 6 * 100, 1)}, by_id["stores"]["rest"])
        self.assertEqual(("Без даты", 1), (by_id["days"]["rest"]["name"], by_id["days"]["rest"]["value"]))
        long_days = [s for s in build_card_details("checks", data, "all", "2026-08-01", "2026-08-31") if s["id"] == "days"][0]
        self.assertEqual("Без даты", long_days["rest"]["name"])
        # Деньги строки без бара тоже видны.
        rev = {s["id"]: s for s in build_card_details("revenue", data, "all", PERIOD["date_from"], PERIOD["date_to"])}
        self.assertEqual(("Без разбивки", 150), (rev["stores"]["rest"]["name"], rev["stores"]["rest"]["value"]))
        # Задвоение: чек A и в Кременчугской - по барам 3 + 3 при итоге 5.
        dup = {"data": FIXTURE_ROWS + [olap_row("A", KREM, "2026-08-24", "Фри", KITCHEN, 150, 40, card=CARD_1)]}
        stores = [s for s in build_card_details("checks", dup, "all", PERIOD["date_from"], PERIOD["date_to"]) if s["id"] == "stores"][0]
        self.assertEqual(-1, stores["rest"]["value"])
        # На полностью размеченной фикстуре копеечных «Без разбивки» нет.
        self.assertIsNone(section("revenue", "stores")["rest"])

    def test_lazy_only_metrics_match_registry(self):
        for metric in METRIC_IDS:
            sections = build_card_details(metric, {"data": []}, "all", PERIOD["date_from"], PERIOD["date_to"])
            self.assertEqual(metric in LAZY_ONLY_METRICS, all(s["lazy"] for s in sections), metric)

    def test_unknown_metric_raises(self):
        with self.assertRaises(ValueError):
            build("nope")

    def test_empty_period_gives_empty_rows_without_errors(self):
        for metric in METRIC_IDS:
            for sec in build_card_details(metric, {"data": []}, "all", "2026-08-24", "2026-08-30"):
                self.assertIsNone(sec["error"], f"{metric}/{sec['id']}")
                # Строки из нулей - шум: клиент покажет «Нет данных».
                self.assertEqual([], sec["rows"], f"{metric}/{sec['id']}")

    def test_section_error_is_isolated(self):
        def boom(ctx):
            raise RuntimeError("сломалось")
        with patch.dict(CARD_SECTIONS, {"revenue": [boom, CARD_SECTIONS["revenue"][0]]}):
            sections = build("revenue")
        self.assertEqual(2, len(sections))
        self.assertEqual("Не удалось посчитать", sections[0]["error"])
        self.assertEqual([], sections[0]["rows"])
        self.assertIsNone(sections[1]["error"])
        self.assertEqual("days", sections[1]["id"])


class Formulas(unittest.TestCase):
    """Конкретные секции на фикстуре с заранее посчитанными числами."""

    def test_draft_sorts_merge_volumes(self):
        sec = section("revenueDraft", "top_revenue")
        by_name = {r["name"]: r for r in sec["rows"]}
        self.assertEqual({"ФестХаус Хеллес", "Крафт ИПА"}, set(by_name))
        self.assertEqual(1100, by_name["ФестХаус Хеллес"]["value"])  # 600 + 200 + 300
        self.assertEqual("4 порц.", by_name["ФестХаус Хеллес"]["sub"])
        self.assertEqual(350, by_name["Крафт ИПА"]["value"])
        self.assertEqual(1450, sec["total"]["value"])
        self.assertIsNone(sec["rest"])
        self.assertEqual("money", sec["format"])

    def test_local_import_for_bottles(self):
        sec = section("revenuePackaged", "local_import")
        self.assertEqual([("Россия", 300), ("Импорт", 900)],
                         [(r["name"], r["value"]) for r in sorted(sec["rows"], key=lambda r: r["value"])])
        self.assertEqual(1200, sec["total"]["value"])
        self.assertEqual("2 шт", [r for r in sec["rows"] if r["name"] == "Россия"][0]["sub"])

    def test_low_markup_skips_zero_cost_and_notes_it(self):
        sec = section("markupDraft", "low_markup")
        names = [r["name"] for r in sec["rows"]]
        self.assertEqual(["ФестХаус Хеллес"], names)
        self.assertEqual(round((1100 - 370) / 370 * 100, 1), sec["rows"][0]["value"])
        self.assertIn("Без себестоимости: 1 поз.", sec["note"])
        self.assertFalse(sec["additive"])
        # Итог - наценка розлива по всем строкам: (1450 - 370) / 370
        self.assertEqual(round((1450 - 370) / 370 * 100, 1), sec["total"]["value"])

    def test_top_units_and_margin(self):
        units = section("packagedShare", "top_units")
        self.assertEqual([("Вайнштефан бут.", 3), ("Балтика бут.", 2)], [(r["name"], r["value"]) for r in units["rows"]])
        self.assertEqual(5, units["total"]["value"])
        margin = section("markupKitchen", "top_margin")
        self.assertEqual("Бургер", margin["rows"][0]["name"])
        self.assertEqual(750, margin["rows"][0]["value"])  # 1200 - 450
        self.assertEqual("наценка 166,7%", margin["rows"][0]["sub"])

    def test_days_week_shows_all_days_with_plan(self):
        plans = {"2026-08-24": {"all": 1000.0, "ligovskiy": 900.0}}
        sec = section("revenue", "days", plans=plans)
        self.assertEqual("По дням", sec["heading"])
        self.assertEqual(["Пн 24.08", "Вт 25.08", "Ср 26.08"], [r["name"] for r in sec["rows"]])
        self.assertEqual([1200, 1500, 1400], [r["value"] for r in sec["rows"]])
        self.assertEqual("план 1 000 ₽ · 120%", sec["rows"][0]["sub"])
        self.assertEqual("2 чек.", sec["rows"][1]["sub"])  # плана на день нет
        self.assertEqual(4100, sec["total"]["value"])

    def test_days_long_period_top_five(self):
        sec = section("checks", "days", date_from="2026-08-01", date_to="2026-08-31")
        self.assertEqual("Топ-5 дней", sec["heading"])
        # Вторник и среда - по два чека, понедельник - один.
        self.assertEqual({"Вт 25.08", "Ср 26.08"}, {r["name"] for r in sec["rows"][:2]})
        self.assertEqual([2, 2, 1], [r["value"] for r in sec["rows"]])
        self.assertEqual(TOTAL_CHECKS, sec["total"]["value"])
        worst = section("cardChecksShare", "days", date_from="2026-08-01", date_to="2026-08-31")
        self.assertEqual("5 худших дней", worst["heading"])
        self.assertEqual("Вт 25.08", worst["rows"][0]["name"])  # 0 чеков с картой из 2
        self.assertEqual(0.0, worst["rows"][0]["value"])

    def test_weekdays_average_over_calendar_days(self):
        sec = section("revenue", "weekdays")
        self.assertEqual(7, len(sec["rows"]))
        self.assertEqual(("Пн", 1200), (sec["rows"][0]["name"], sec["rows"][0]["value"]))
        self.assertEqual(0, sec["rows"][6]["value"])  # воскресенье без продаж = 0
        self.assertFalse(sec["additive"])

    def test_stores_only_for_all_venues(self):
        sec = section("revenue", "stores")
        self.assertEqual([("Кременчугская", 2150), ("Лиговский", 1950)], [(r["name"], r["value"]) for r in sec["rows"]])
        self.assertEqual(4100, sec["total"]["value"])
        self.assertEqual([], [s for s in build("revenue", venue="ligovskiy") if s["id"] == "stores"])

    def test_categories(self):
        rev = section("revenue", "categories")
        self.assertEqual({"Розлив": 1450, "Фасовка": 1200, "Кухня": 1350, "Прочее": 100},
                         {r["name"]: r["value"] for r in rev["rows"]})
        discount = section("loyaltyWriteoffs", "categories")
        self.assertEqual({"Розлив": 0, "Фасовка": 0, "Кухня": 40, "Прочее": 10},
                         {r["name"]: r["value"] for r in discount["rows"]})
        self.assertEqual(50, discount["total"]["value"])

    def test_guests_by_card_number_without_mask(self):
        sec = section("cardRevenue", "guests")
        self.assertEqual([(CARD_1, 1650), (CARD_2, 950)], [(r["name"], r["value"]) for r in sec["rows"]])
        self.assertEqual("2 чек. · 2 визит.", sec["rows"][0]["sub"])
        self.assertEqual(2600, sec["total"]["value"])
        checks = section("cardChecks", "guests")
        self.assertEqual(2, checks["rows"][0]["value"])
        self.assertEqual(3, checks["total"]["value"])

    def test_card_split_average_check(self):
        sec = section("averageCheck", "card_split")
        self.assertEqual([867, 750], [r["value"] for r in sec["rows"]])  # 2600/3, 1500/2
        self.assertEqual(820, sec["total"]["value"])  # 4100 / 5
        self.assertFalse(sec["additive"])

    def test_lazy_stubs_in_bulk(self):
        ids = [s["id"] for s in build("draftShare")]
        self.assertIn("draft_liters", ids)
        stub = [s for s in build("draftShare") if s["id"] == "draft_liters"][0]
        self.assertTrue(stub["lazy"])
        self.assertEqual([], stub["rows"])
        self.assertEqual(["taps"], [s["id"] for s in build("tapActivity")])

    def test_normalize_date_accepts_both_iiko_formats(self):
        self.assertEqual("2026-08-24", normalize_date("2026-08-24"))
        self.assertEqual("2026-08-24", normalize_date("2026-08-24T00:00:00"))
        self.assertEqual("2026-08-24", normalize_date("24.08.2026"))
        self.assertEqual("2026-08-24", normalize_date("2026.08.24"))
        self.assertIsNone(normalize_date(""))
        self.assertIsNone(normalize_date(None))


class LazySources(unittest.TestCase):
    """Литры из блока /draft и краны из TapsManager."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(REPO_ROOT, "tests", "fixtures", "draft_kegs_sample.json"), encoding="utf-8") as f:
            payload = json.load(f)
        cls.block = payload[next(iter(payload))]

    def test_section_draft_liters_from_draft_block(self):
        sec = section_draft_liters(self.block)
        kegs = sorted(self.block["kegs"], key=lambda k: k["TotalLiters"], reverse=True)
        self.assertEqual([k["KegName"] for k in kegs[:5]], [r["name"] for r in sec["rows"]])
        self.assertEqual([round(k["TotalLiters"], 1) for k in kegs[:5]], [r["value"] for r in sec["rows"]])
        self.assertEqual([round(k["LitersSharePercent"], 1) for k in kegs[:5]], [r["share"] for r in sec["rows"]])
        self.assertEqual(round(self.block["total_liters"], 1), sec["total"]["value"])
        self.assertEqual(f"Остальные кеги ({len(kegs) - 5})", sec["rest"]["name"])
        self.assertAlmostEqual(sec["total"]["value"], shown_sum(sec), delta=0.6)
        self.assertEqual("liters", sec["format"])
        self.assertEqual("/draft", sec["link"]["href"])
        self.assertNotIn("TotalRevenue", json.dumps(sec, ensure_ascii=False))

    def test_tap_activity_by_tap_matches_card_formula(self):
        manager = TapsManager(data_file=os.path.join(REPO_ROOT, "tests", "fixtures", "no_such_taps.json"))
        bar = manager.bars["bar2"]  # 12 кранов
        bar.taps[1].history = [{"timestamp": "2026-08-20T12:00:00+03:00", "action": "start"}]
        bar.taps[2].history = [{"timestamp": "2026-08-25T12:00:00+03:00", "action": "start"},
                               {"timestamp": "2026-08-27T18:00:00+03:00", "action": "stop"}]
        bar.taps[3].history = [{"timestamp": "2026-08-01T12:00:00", "action": "replace"},
                               {"timestamp": "bad", "action": "start"}]
        detail = manager.tap_activity_by_tap("bar2", "2026-08-24", "2026-08-30")
        by_tap = {t["tap_number"]: t["active_days"] for t in detail["taps"]}
        self.assertEqual(7, detail["days"])
        self.assertEqual(12, detail["total_taps"])
        self.assertEqual(7, by_tap[1])   # подключён до периода, работал всю неделю
        # 25 и 26 августа; 27-го срез на конец дня уже видит stop (18:00) - день пустой
        self.assertEqual(2, by_tap[2])
        self.assertEqual(7, by_tap[3])   # replace - активен, битое событие пропущено
        self.assertEqual(0, by_tap[4])
        self.assertEqual(16, detail["active_tap_days"])
        self.assertEqual(detail["active_tap_days"], sum(t["active_days"] for t in detail["taps"]))
        self.assertEqual(12, len(detail["taps"]))
        self.assertEqual(round(16 / (12 * 7) * 100, 2), detail["percent"])
        self.assertEqual(detail["percent"], manager.calculate_tap_activity_for_period("bar2", "2026-08-24", "2026-08-30"))
        self.assertEqual(0.0, manager.calculate_tap_activity_for_period("bar9", "2026-08-24", "2026-08-30"))
        # Все бары: 60 кранов, те же 16 активных кран-дней
        all_bars = manager.tap_activity_by_tap(None, "2026-08-24", "2026-08-30")
        self.assertEqual(60, all_bars["total_taps"])
        self.assertEqual(60, len(all_bars["taps"]))
        self.assertEqual(all_bars["active_tap_days"], sum(t["active_days"] for t in all_bars["taps"]))
        self.assertEqual(round(16 / (60 * 7) * 100, 2), all_bars["percent"])

        sec = section_taps(detail, bar_names={"bar2": "Лиговский"}, link_href="/taps/bar2")
        self.assertEqual("Кран 4 · Лиговский", sec["rows"][0]["name"])  # простой - первым
        self.assertEqual(0.0, sec["rows"][0]["value"])
        self.assertEqual("0 из 7 дн.", sec["rows"][0]["sub"])
        self.assertIn("Простаивали весь период: 9 из 12", sec["note"])
        self.assertEqual(round(detail["percent"], 1), sec["total"]["value"])
        self.assertEqual("/taps/bar2", sec["link"]["href"])

    def test_section_taps_all_idle_keeps_rows(self):
        """Бар без событий: нули у кранов - это содержание секции, а не «Нет данных»."""
        manager = TapsManager(data_file=os.path.join(REPO_ROOT, "tests", "fixtures", "no_such_taps.json"))
        detail = manager.tap_activity_by_tap("bar3", "2026-08-24", "2026-08-30")
        self.assertEqual(0.0, detail["percent"])
        sec = section_taps(detail, bar_names={"bar3": "Кременчугская"}, link_href="/taps/bar3")
        self.assertEqual(5, len(sec["rows"]))
        self.assertEqual("0 из 7 дн.", sec["rows"][0]["sub"])
        self.assertIn("Простаивали весь период: 12 из 12", sec["note"])
        self.assertEqual(0.0, sec["total"]["value"])


class FixtureOlap:
    """iiko отвечает фикстурой и считает обращения."""

    calls = 0

    def __init__(self):
        self.api = type("Api", (), {"base_url": "https://example.invalid/resto/api"})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_all_sales_report(self, date_from, date_to, bar_name=None):
        FixtureOlap.calls += 1
        # Как iiko: фильтр Store.Name оставляет строки одного бара.
        rows = [dict(r) for r in FIXTURE_ROWS if not bar_name or r["Store.Name"] == bar_name]
        return {"data": rows}


class FailingOlap(FixtureOlap):
    def get_all_sales_report(self, date_from, date_to, bar_name=None):
        FixtureOlap.calls += 1
        return None


def make_client():
    app = Flask(__name__)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(employee_bp)
    app.register_blueprint(analysis_bp)
    return app.test_client()


class DetailsEndpoint(unittest.TestCase):
    """POST /api/dashboard-card-details."""

    def setUp(self):
        DASHBOARD_OLAP_CACHE.clear()
        FixtureOlap.calls = 0

    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", FixtureOlap)
    def test_details_share_cache_and_match_card(self, _tap_activity):
        client = make_client()
        card = client.post("/api/dashboard-analytics", json={"bar": "", **PERIOD})
        self.assertEqual(200, card.status_code, card.get_data(as_text=True))
        card = card.get_json()

        response = client.post("/api/dashboard-card-details",
                               json={"venue_key": "all", "metric": "revenueDraft", **PERIOD})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(1, FixtureOlap.calls)  # один поход в iiko на карточку и детали
        self.assertEqual("revenueDraft", payload["metric"])
        self.assertEqual({"from": PERIOD["date_from"], "to": PERIOD["date_to"]}, payload["period"])
        sections = {s["id"]: s for s in payload["sections"]}
        self.assertEqual(["top_revenue", "local_import", "draft_liters"], [s["id"] for s in payload["sections"]])
        self.assertEqual(round(card["revenueDraft"]), sections["top_revenue"]["total"]["value"])
        self.assertTrue(sections["draft_liters"]["lazy"])

        employees = client.post("/api/employee-metrics-breakdown", json={"venue_key": "all", **PERIOD}).get_json()
        self.assertEqual(1, FixtureOlap.calls)
        egor = [e for e in employees["employees"] if e["name"] == "Егор"][0]
        self.assertEqual(2, egor["cardChecks"])
        self.assertEqual(0, egor["nocardChecks"])
        self.assertEqual(round(card["cardRevenue"]), employees["total"]["cardRevenue"])
        self.assertEqual(card["cardChecks"], employees["total"]["cardChecks"])

    @patch("routes.dashboard.OlapReports", FixtureOlap)
    def test_validation(self):
        client = make_client()
        self.assertEqual(400, client.post("/api/dashboard-card-details", json={"metric": "revenue"}).status_code)
        self.assertEqual(400, client.post("/api/dashboard-card-details", json={"metric": "nope", **PERIOD}).status_code)
        self.assertEqual(400, client.post("/api/dashboard-card-details",
                                          json={"metric": "revenue", "section": "nope", **PERIOD}).status_code)
        self.assertEqual(0, FixtureOlap.calls)

    @patch("routes.dashboard.OlapReports", FailingOlap)
    def test_iiko_failure_is_500_and_not_cached(self):
        client = make_client()
        for _ in range(2):
            response = client.post("/api/dashboard-card-details", json={"metric": "revenue", **PERIOD})
            self.assertEqual(500, response.status_code)
        self.assertEqual(2, FixtureOlap.calls)

    @patch("routes.dashboard.OlapReports", FailingOlap)
    def test_taps_bulk_does_not_touch_olap(self):
        """У кранов все секции ленивые: недоступный iiko не прячет локальные данные кранов."""
        client = make_client()
        response = client.post("/api/dashboard-card-details", json={"metric": "tapActivity", **PERIOD})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        sections = response.get_json()["sections"]
        self.assertEqual(["taps"], [s["id"] for s in sections])
        self.assertTrue(sections[0]["lazy"])
        self.assertEqual(0, FixtureOlap.calls)

    @patch("routes.dashboard.DailyPlansGenerator")
    @patch("routes.dashboard.taps_manager.calculate_tap_activity_for_period", return_value=0)
    @patch("routes.dashboard.OlapReports", FixtureOlap)
    def test_single_venue_without_stores_and_with_daily_plan(self, _tap_activity, plans_cls):
        plans_cls.return_value.load_daily_plans.return_value = {"2026-08-24": {"ligovskiy": 900.0, "all": 1000.0}}
        client = make_client()
        response = client.post("/api/dashboard-card-details",
                               json={"venue_key": "ligovskiy", "metric": "revenue", **PERIOD})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        sections = {s["id"]: s for s in response.get_json()["sections"]}
        self.assertNotIn("stores", sections)  # один бар - разреза по барам нет
        days = sections["days"]
        self.assertEqual(1950, days["total"]["value"])  # только Лиговский: 1200 + 300 + 450
        self.assertEqual("план 900 ₽ · 133%", days["rows"][0]["sub"])  # 1200 / 900
        self.assertEqual(1, FixtureOlap.calls)
        plans_cls.return_value.load_daily_plans.assert_called_once_with()

    @patch("routes.dashboard.load_draft_kegs")
    @patch("routes.dashboard.DraftKegAnalysis")
    def test_lazy_draft_liters(self, analysis_cls, loader):
        with open(os.path.join(REPO_ROOT, "tests", "fixtures", "draft_kegs_sample.json"), encoding="utf-8") as f:
            block = json.load(f)["Общая"]
        loader.return_value = {"transactions": [], "sales": [], "dish_map": {}, "fetched_at": "12:34"}
        analysis_cls.return_value.build.return_value = block
        client = make_client()
        response = client.post("/api/dashboard-card-details",
                               json={"venue_key": "ligovskiy", "metric": "draftShare", "section": "draft_liters", **PERIOD})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        sec = response.get_json()["section"]
        self.assertEqual("draft_liters", sec["id"])
        self.assertEqual(5, len(sec["rows"]))
        self.assertIn("данные iiko на 12:34", sec["note"])
        loader.assert_called_once_with("Лиговский", PERIOD["date_from"], PERIOD["date_to"])
        # Сырьё и ВКЛЮЧИТЕЛЬНЫЕ даты уходят в расчёт ровно как на /draft.
        analysis_cls.assert_called_once_with(transactions=[], sales=[], dish_map={},
                                             date_from=PERIOD["date_from"], date_to=PERIOD["date_to"])
        analysis_cls.return_value.build.assert_called_once_with("Лиговский")

        loader.return_value = None
        response = client.post("/api/dashboard-card-details",
                               json={"venue_key": "all", "metric": "draftShare", "section": "draft_liters", **PERIOD})
        self.assertEqual(502, response.status_code)

    def test_lazy_taps_uses_taps_manager(self):
        client = make_client()
        with patch("routes.dashboard.taps_manager") as manager:
            manager.tap_activity_by_tap.return_value = {
                "days": 7, "total_taps": 12, "active_tap_days": 14, "percent": 16.67,
                "taps": [{"bar_id": "bar2", "bar_name": "Бар 2", "tap_number": n, "active_days": 7 if n < 3 else 0,
                          "current_beer": None} for n in range(1, 13)],
            }
            response = client.post("/api/dashboard-card-details",
                                   json={"venue_key": "ligovskiy", "metric": "tapActivity", "section": "taps", **PERIOD})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        sec = response.get_json()["section"]
        manager.tap_activity_by_tap.assert_called_once_with("bar2", PERIOD["date_from"], PERIOD["date_to"])
        self.assertEqual("/taps/bar2", sec["link"]["href"])
        self.assertEqual(16.7, sec["total"]["value"])  # проценты в секции - до 0,1, как на карточке
        self.assertTrue(sec["rows"][0]["name"].endswith("Лиговский"))


class DraftLoaderSharesCache(unittest.TestCase):
    """core/draft_loader.py: /api/draft-kegs и карточка читают одну запись кэша."""

    class DraftOlap(FixtureOlap):
        def get_draft_writeoff_report(self, date_from, date_to, bar_name=None):
            FixtureOlap.calls += 1
            return {"data": []}

        def get_draft_sales_by_dish(self, date_from, date_to, bar_name=None):
            return {"data": []}

        def get_dish_ingredient_map(self, date_from, date_to, use_cache=True):
            return {}

    def setUp(self):
        DASHBOARD_OLAP_CACHE.clear()
        FixtureOlap.calls = 0

    def test_same_cache_key_for_page_and_card(self):
        from core.draft_loader import load_draft_kegs
        with patch("core.draft_loader.OlapReports", self.DraftOlap):
            raw = load_draft_kegs(None, PERIOD["date_from"], PERIOD["date_to"])
            self.assertEqual({"transactions", "sales", "dish_map", "fetched_at"}, set(raw))
            self.assertIn("draft_kegs_ALL_2026-08-24_2026-08-31", DASHBOARD_OLAP_CACHE)
            client = make_client()
            response = client.post("/api/draft-kegs", json={"bar": "", **PERIOD})
            # Пустые проводки: страница честно отдаёт 404 «Нет данных», но в iiko не ходит -
            # сырьё взято из той же записи кэша, что положил load_draft_kegs.
            self.assertEqual(404, response.status_code)
        self.assertEqual(1, FixtureOlap.calls)


if __name__ == "__main__":
    unittest.main()
