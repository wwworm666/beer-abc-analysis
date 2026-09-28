# -*- coding: utf-8 -*-
"""
«Сегодня» по Москве, а не по часам сервера (2026-09-28).

Прод-контейнер живёт в UTC (core/msk_time.py): с 00:00 до 03:00 МСК наивный
datetime.now() отстаёт на календарный день. Ошибки до правки:
- /api/revenue-metrics: в первую ночь после конца периода он ещё считался идущим,
  и «Ожидаемая» экстраполировалась вместо «= факт»;
- /api/widget/revenue: период «с 1-го по сегодня» — в ночь на 1-е число виджет
  показывал процент ПРОШЛОГО месяца;
- /api/draft-analyze (старый анализ розлива): окно «последние N дней» — на сутки назад;
- RevenueMetricsCalculator._calculate_expected_revenue — то же, что у revenue-metrics.

Как проверяется: core.msk_time.now подменяется на момент в 2020 году. Часы сервера
при прогоне показывают другой год, поэтому код, который по-прежнему берёт
datetime.now(), даёт другие даты и числа — тест это ловит на любом дне прогона.

Сеть не трогается: OLAP подменён.
Запуск: py -3 -m pytest -q tests/test_msk_today_routes.py
"""

import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

from flask import Flask

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

from core import msk_time  # noqa: E402
from core.revenue_metrics import RevenueMetricsCalculator  # noqa: E402
from extensions import DASHBOARD_OLAP_CACHE  # noqa: E402
import routes.dashboard as rd  # noqa: E402
from routes.analysis import analysis_bp  # noqa: E402
from routes.dashboard import dashboard_bp  # noqa: E402

# Москва 15.01.2020 01:00 — середина месяца, ночь (время, когда UTC ещё «вчера»).
MSK_NOW = datetime(2020, 1, 15, 1, 0, tzinfo=msk_time.MOSCOW_TZ)


class RecordingOlap:
    """iiko: запоминает запрошенные даты; продажи — одна строка на 1000 ₽."""

    calls = []

    def __init__(self):
        self.api = type('Api', (), {'base_url': 'https://example.invalid/resto/api'})()

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_all_sales_report(self, date_from, date_to, bar_name=None):
        RecordingOlap.calls.append(('all_sales', date_from, date_to))
        return {'data': [{'UniqOrderId.Id': 'A', 'DishDiscountSumInt': 1000.0,
                          'DishGroup.TopParent': 'ЕДА', 'ProductCostBase.ProductCost': 100.0,
                          'DiscountSum': 0}]}

    def get_draft_sales_report(self, date_from, date_to, bar_name=None):
        RecordingOlap.calls.append(('draft', date_from, date_to))
        return {'data': []}


@patch.object(msk_time, 'now', lambda: MSK_NOW)
class TodayIsMoscow(unittest.TestCase):
    def setUp(self):
        DASHBOARD_OLAP_CACHE.clear()
        rd.WIDGET_CACHE.clear()
        RecordingOlap.calls = []
        app = Flask(__name__)
        app.register_blueprint(dashboard_bp)
        app.register_blueprint(analysis_bp)
        self.client = app.test_client()

    @patch('routes.dashboard.taps_manager.calculate_tap_activity_for_period', return_value=0)
    @patch('routes.dashboard.OlapReports', RecordingOlap)
    def test_revenue_metrics_period_still_running_by_moscow_date(self, _taps):
        """Факт за 14 дней января из 31: по МСК период идёт — ожидаемая экстраполируется."""
        body = self.client.post('/api/revenue-metrics', json={
            'bar': 'bolshoy', 'date_from': '2020-01-01', 'date_to': '2020-01-14',
            'period_from': '2020-01-01', 'period_to': '2020-01-31'}).get_json()
        self.assertEqual(1000.0, body['current'])
        # 1000 / 14 × 31 = 2214.29; по часам сервера (не 2020 год) было бы 1000 = факт.
        self.assertEqual(2214.29, body['expected'])

    @patch('routes.dashboard.taps_manager.calculate_tap_activity_for_period', return_value=0)
    @patch('routes.dashboard.OlapReports', RecordingOlap)
    def test_revenue_metrics_period_finished_after_its_last_moscow_day(self, _taps):
        body = self.client.post('/api/revenue-metrics', json={
            'bar': 'bolshoy', 'date_from': '2020-01-01', 'date_to': '2020-01-13',
            'period_from': '2020-01-01', 'period_to': '2020-01-14'}).get_json()
        self.assertEqual(body['current'], body['expected'], 'период закончился вчера по МСК')

    @patch('routes.dashboard.OlapReports', RecordingOlap)
    def test_widget_month_by_moscow_date(self):
        response = self.client.get('/api/widget/revenue')
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        # С 1-го числа по «сегодня» МСК; правая граница iiko — эксклюзивная (+1 день).
        self.assertEqual([('all_sales', '2020-01-01', '2020-01-16')], RecordingOlap.calls)

    @patch('routes.analysis.OlapReports', RecordingOlap)
    def test_draft_analyze_last_days_by_moscow_date(self):
        self.client.post('/api/draft-analyze', json={'bar': '', 'days': 7})
        # Последние 7 дней до «сегодня» МСК включительно; правая граница iiko +1 день.
        self.assertEqual([('draft', '2020-01-08', '2020-01-16')], RecordingOlap.calls)

    def test_revenue_metrics_calculator_expected(self):
        expected = RevenueMetricsCalculator()._calculate_expected_revenue(
            900.0, 0.0, '2020-01-01', '2020-01-31')
        # Прошло 15 дней (с 1-го по «сегодня» 15-е): 900 + 60 × 16 = 1860.
        self.assertEqual(1860.0, expected)


# ---------------------------------------------------------------- недели и месячный отчёт
# Ночь на 1 марта 2020 по Москве (01:00): в UTC ещё 29 февраля. Часы сервера при
# прогоне показывают другой год, поэтому оставшийся datetime.now() тест ловит.
MSK_MARCH_NIGHT = datetime(2020, 3, 1, 1, 0, tzinfo=msk_time.MOSCOW_TZ)


class WeeksByMoscowDate(unittest.TestCase):
    """core/weeks_generator.py и /api/weeks: год и текущая неделя — по Москве."""

    def test_current_week_on_monday_night(self):
        from core.weeks_generator import WeeksGenerator
        # Понедельник 00:30 МСК = воскресенье 21:30 UTC: неделя уже новая.
        with patch.object(msk_time, 'now',
                          lambda: datetime(2020, 1, 6, 0, 30, tzinfo=msk_time.MOSCOW_TZ)):
            week = WeeksGenerator.get_current_week()
        self.assertEqual(('2020-01-06', '2020-01-12', '2020-01-06_2020-01-12'),
                         (week['start'], week['end'], week['key']))

    def test_default_year_and_current_flag(self):
        from core.weeks_generator import WeeksGenerator
        with patch.object(msk_time, 'now',
                          lambda: datetime(2020, 1, 1, 1, 0, tzinfo=msk_time.MOSCOW_TZ)):
            weeks = WeeksGenerator.generate_weeks_for_year()
        self.assertEqual('2019-12-30', weeks[0]['start'], 'год по умолчанию — 2020 по Москве')
        current = [w['key'] for w in weeks if w['is_current']]
        self.assertEqual(['2019-12-30_2020-01-05'], current)

    def test_weeks_route(self):
        app = Flask(__name__)
        app.register_blueprint(dashboard_bp)
        with patch.object(msk_time, 'now', lambda: MSK_MARCH_NIGHT):
            body = app.test_client().get('/api/weeks').get_json()
        self.assertEqual('2020-02-24_2020-03-01', body['current_week']['key'])
        self.assertTrue(body['weeks'][0]['start'].startswith('2019-12'))


@patch.object(msk_time, 'now', lambda: MSK_MARCH_NIGHT)
class MonthlyReportByMoscowDate(unittest.TestCase):
    """core/monthly_report.py: какой месяц текущий, год по умолчанию, «данные на»."""

    def setUp(self):
        import tempfile
        from core import monthly_report
        self.mr = monthly_report
        self.tmp = tempfile.mkdtemp(prefix='monthly_msk_')
        self.patches = [patch.object(monthly_report, '_cache_dir', lambda: self.tmp),
                        patch.object(monthly_report, 'COMPUTE_THROTTLE_SEC', 0),
                        patch.object(monthly_report, 'OlapReports', RecordingOlap)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        import shutil
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_closed_month_is_computed_current_month_is_not(self):
        """1 марта 01:00 МСК: февраль закрыт и считается, март — текущий, не считается."""
        computed = []

        def compute(olap, bar_name, year, month):
            computed.append(month)
            return {'revenue': month}

        self.assertTrue(self.mr._compute_months('core', 'all', 2020, compute))
        self.assertEqual([1, 2], computed)
        cache = self.mr._read_cache('core', 'all', 2020)
        self.assertEqual('2020-03-01T01:00:00+03:00', cache[self.mr.META_KEY],
                         '«данные на» — московское время, а не UTC')

    def test_default_years(self):
        calls = []
        with patch.object(self.mr, 'refresh_year',
                          lambda venue, year, force=False: calls.append(year) or False):
            self.mr.refresh_all(venues=['all'])
        self.assertEqual([2020, 2019, 2018], calls)
        seen = []
        with patch.object(self.mr, '_refreshed_at', lambda block, venue, year: seen.append(year)):
            self.mr.get_core('all', [])
        self.assertEqual([2020], seen)


@patch.object(msk_time, 'now', lambda: MSK_MARCH_NIGHT)
class MonthlyReportRouteDefaults(unittest.TestCase):
    """routes/dashboard.py: год и месяц месячного отчёта по умолчанию — по Москве."""

    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(dashboard_bp)
        self.client = app.test_client()
        self.calls = []

    def record(self, name):
        return lambda *args, **kwargs: self.calls.append((name,) + args) or {}

    def test_defaults(self):
        mr = rd.monthly_report
        with patch.object(mr, 'get_core', self.record('core')), \
                patch.object(mr, 'get_loyalty', self.record('loyalty')), \
                patch.object(mr, 'get_draft_liters', self.record('liters')), \
                patch.object(mr, 'get_top_guests', self.record('top')), \
                patch.object(mr, 'refresh_block', self.record('refresh')):
            self.client.get('/api/monthly-report?venue=all')
            self.client.get('/api/monthly-report/loyalty?venue=all')
            self.client.get('/api/monthly-report/draft-liters?venue=all')
            self.client.get('/api/monthly-report/top-guests?venue=all&force=1')
        self.assertEqual([('core', 'all', [2020]), ('loyalty', 'all', 2020),
                          ('liters', 'all', 2020), ('refresh', 'topguests', 'all', 2020),
                          ('top', 'all', 2020, 3)], self.calls)


if __name__ == '__main__':
    unittest.main(verbosity=2)
