# -*- coding: utf-8 -*-
"""POST /api/draft-kegs: разбор входа и критерий «нет данных» (2026-09-26).

Что защищают тесты:
1. Кривой JSON и мусор в days при валидных датах — не 500: days разбирается,
   только когда дат нет, как у /api/packaging.
2. Период «конец раньше начала» и даты не в формате YYYY-MM-DD — 400, и iiko
   при этом не трогается.
3. «Нет данных» (404) — только когда нет ни продаж, ни движения кегов: период с
   одним актом списания или инвентаризацией — это данные. Раньше хватало
   отсутствия прихода по накладным.
Сеть не трогается: загрузчик подменён.

Запуск:
    py -3 -X utf8 -m unittest -v tests.test_draft_routes
"""
import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

from routes.analysis import analysis_bp  # noqa: E402

PERIOD = {"date_from": "2026-08-03", "date_to": "2026-08-09"}


def trans(kind, out=0.0, inc=0.0):
    return {
        "Account.Name": "Лиговский", "Product.Id": "keg-a", "Product.Name": "КЕГ А",
        "Product.MeasureUnit": "л", "DateTime.DateTyped": "2026-08-05",
        "TransactionType": kind, "Amount.Out": out, "Amount.In": inc, "Sum.Outgoing": 0.0,
    }


def raw(transactions=()):
    return {"transactions": list(transactions), "sales": [], "dish_map": {},
            "fetched_at": "10:00"}


class DraftKegsRouteTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(analysis_bp)
        self.client = app.test_client()

    def post(self, loader_result, **kwargs):
        with patch("routes.analysis.load_draft_kegs", return_value=loader_result) as loader:
            response = self.client.post("/api/draft-kegs", **kwargs)
        return response, loader

    def test_garbage_days_with_valid_dates_is_not_500(self):
        response, loader = self.post(raw([trans("SESSION_WRITEOFF", out=5.0)]),
                                     json=dict(PERIOD, days="abc"))
        self.assertEqual(200, response.status_code, response.get_json())
        loader.assert_called_once()

    def test_garbage_days_without_dates_is_400(self):
        response, loader = self.post(raw(), json={"days": "abc"})
        self.assertEqual(400, response.status_code)
        loader.assert_not_called()

    def test_broken_json_is_not_500(self):
        response, _ = self.post(raw(), data="{bad json", content_type="application/json")
        self.assertNotEqual(500, response.status_code, response.get_json())

    def test_reversed_period_is_400_without_iiko(self):
        response, loader = self.post(raw(), json={"date_from": "2026-08-09",
                                                  "date_to": "2026-08-03"})
        self.assertEqual(400, response.status_code)
        self.assertIn("позже", response.get_json()["error"])
        loader.assert_not_called()

    def test_bad_date_format_is_400_without_iiko(self):
        response, loader = self.post(raw(), json={"date_from": "03.08.2026",
                                                  "date_to": "2026-08-09"})
        self.assertEqual(400, response.status_code)
        loader.assert_not_called()

    def test_writeoff_only_period_is_data_not_404(self):
        response, _ = self.post(raw([trans("WRITEOFF", out=12.0)]), json=PERIOD)
        self.assertEqual(200, response.status_code, response.get_json())
        block = response.get_json()["Общая"]
        self.assertEqual(12.0, block["losses"]["writeoff"])
        self.assertEqual([], block["kegs"])

    def test_inventory_only_period_is_data_not_404(self):
        response, _ = self.post(raw([trans("INVENTORY_CORRECTION", out=3.0)]), json=PERIOD)
        self.assertEqual(200, response.status_code)

    def test_empty_period_is_404(self):
        response, _ = self.post(raw(), json=PERIOD)
        self.assertEqual(404, response.status_code)

    def test_iiko_failure_is_502(self):
        response, _ = self.post(None, json=PERIOD)
        self.assertEqual(502, response.status_code)

    def test_balance_caption_totals_come_from_server(self):
        """Приход в подписи баланса включает перемещения — иначе «приход − расход»
        не сходится с «изменением остатка» (раньше подпись складывал JS)."""
        rows = [trans("INVOICE", inc=30.0), trans("TRANSFER", inc=50.0),
                trans("SESSION_WRITEOFF", out=40.0), trans("INVENTORY_CORRECTION", inc=6.0)]
        response, _ = self.post(raw(rows), json=PERIOD)
        losses = response.get_json()["Общая"]["losses"]
        self.assertEqual(80.0, losses["received"])
        self.assertEqual(34.0, losses["spent"])            # 40 продано − 6 излишка
        self.assertAlmostEqual(losses["balance"], losses["received"] - losses["spent"])


if __name__ == "__main__":
    unittest.main()
