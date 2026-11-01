# -*- coding: utf-8 -*-
"""
«Сегодня» на страницах сотрудников, зарплаты и графика — рабочие сутки бара (2026-11-01).

План единого виджета (docs/planning/period-widget-rollout.md, раздел 4.1): там, где «сегодня»
решает, какой день данных брать, сервер считает рабочие сутки бара по Москве
(core/msk_time.business_today: до 06:00 МСК идёт вчерашний день), а не наивный
date.today() / datetime.now() контейнера в UTC. Места до правки:
- /api/employees — окно «последние 30 дней» (ещё и без периода страницы);
- /api/kpi-dishes — окно каталога блюд 90 дней;
- ShiftsManager.get_hours_by_role_for_period — «прошедшая смена без факта» и дневные смены;
- core/salary_payload.current_month и core/salary_scheduler.months_to_sync — какой месяц
  выгружать;
- /api/schedule/summary и /api/schedule/widgets — «без факта» в нагрузке.

Как проверяется: core.msk_time.now подменяется на ночь в 2020 году. Часы сервера при прогоне
показывают другой год, поэтому код, который по-прежнему берёт date.today(), даёт другие даты —
тест это ловит на любом дне прогона. Сеть и iiko не трогаются: OLAP подменён.

Запуск: py -3 -m pytest -q tests/test_business_today_staff.py
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ.setdefault('PERSISTENT_DATA_DIR', tempfile.mkdtemp(prefix='biz_today_test_'))
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, REPO_ROOT)

from flask import Flask  # noqa: E402

from core import msk_time  # noqa: E402
from core.shifts_manager import ShiftsManager  # noqa: E402

# 15.01.2020 01:00 МСК — ночь: календарно уже 15-е, рабочие сутки бара — ещё 14-е.
NIGHT_15 = datetime(2020, 1, 15, 1, 0, tzinfo=msk_time.MOSCOW_TZ)
# 01.02.2020 01:00 МСК — ночь на первое число: рабочие сутки — 31 января.
NIGHT_FEB_1 = datetime(2020, 2, 1, 1, 0, tzinfo=msk_time.MOSCOW_TZ)


class RecordingOlap:
    """iiko: запоминает запрошенные окна, отдаёт два имени."""

    calls = []

    def connect(self):
        return True

    def disconnect(self):
        return None

    def get_draft_sales_by_waiter_report(self, date_from, date_to, bar_name=None):
        RecordingOlap.calls.append(('draft', date_from, date_to, bar_name))
        return {'data': [{'WaiterName': 'Иван Петров'}, {'WaiterName': 'Анна Смирнова'},
                         {'WaiterName': 'Системный пользователь'}]}

    def get_dish_names(self, date_from, date_to):
        RecordingOlap.calls.append(('dishes', date_from, date_to))
        return [{'name': 'Брискет', 'group': 'ЕДА', 'amount': 3}]


def _employee_client():
    import routes.employee as re_mod
    app = Flask(__name__)
    app.register_blueprint(re_mod.employee_bp)
    return app.test_client(), re_mod


@patch.object(msk_time, 'now', lambda: NIGHT_15)
class EmployeesListTest(unittest.TestCase):
    def setUp(self):
        RecordingOlap.calls = []
        self.client, self.mod = _employee_client()
        self.olap = patch.object(self.mod, 'OlapReports', RecordingOlap)
        self.olap.start()
        self.addCleanup(self.olap.stop)

    def test_default_window_is_30_days_by_business_day(self):
        r = self.client.get('/api/employees')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['employees'], ['Анна Смирнова', 'Иван Петров'])
        # Рабочий день — 14.01: окно 15.12 … 14.01 включительно (конец OLAP — исключающий).
        self.assertEqual(RecordingOlap.calls, [('draft', '2019-12-15', '2020-01-15', None)])

    def test_period_of_the_strip(self):
        r = self.client.get('/api/employees?date_from=2020-01-06&date_to=2020-01-12')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(RecordingOlap.calls, [('draft', '2020-01-06', '2020-01-13', None)])

    def test_bar_key_and_iiko_name(self):
        self.client.get('/api/employees?date_from=2020-01-06&date_to=2020-01-12&bar=ligovskiy')
        self.client.get('/api/employees?date_from=2020-01-06&date_to=2020-01-12&bar=Лиговский')
        self.client.get('/api/employees?date_from=2020-01-06&date_to=2020-01-12&bar=all')
        self.assertEqual([c[3] for c in RecordingOlap.calls], ['Лиговский', 'Лиговский', None])

    def test_bad_period_is_400(self):
        for qs in ('date_from=2020-01-12&date_to=2020-01-06', 'date_from=2020-01-06',
                   'date_from=вчера&date_to=2020-01-06'):
            r = self.client.get('/api/employees?' + qs)
            self.assertEqual(r.status_code, 400, qs)
        self.assertEqual(RecordingOlap.calls, [], 'с неверным периодом в iiko не ходим')


@patch.object(msk_time, 'now', lambda: NIGHT_15)
class KpiDishesTest(unittest.TestCase):
    def test_catalog_window_by_business_day(self):
        RecordingOlap.calls = []
        client, mod = _employee_client()
        mod.DISHES_CACHE['data'] = None
        with patch.object(mod, 'OlapReports', RecordingOlap):
            r = client.get('/api/kpi-dishes?refresh=1')
        self.assertEqual(r.status_code, 200)
        # 90 дней назад от рабочего дня 14.01.2020 — 16.10.2019; конец исключающий — 15.01.
        self.assertEqual(RecordingOlap.calls, [('dishes', '2019-10-16', '2020-01-15')])
        mod.DISHES_CACHE['data'] = None


class IikoBarTest(unittest.TestCase):
    def test_every_spelling_to_iiko_name(self):
        from routes.employee import _iiko_bar
        self.assertEqual(_iiko_bar('bolshoy'), 'Большой пр. В.О')
        self.assertEqual(_iiko_bar('Большой пр В.О.'), 'Большой пр. В.О', 'написание целей KPI')
        self.assertEqual(_iiko_bar('bar4'), 'Варшавская')
        for raw in (None, '', '  ', 'all', 'Все бары'):
            self.assertIsNone(_iiko_bar(raw), raw)
        self.assertEqual(_iiko_bar('Склад РЦ'), 'Склад РЦ', 'незнакомое — как пришло')


class AnalyticsPeriodTest(unittest.TestCase):
    """Перевёрнутые даты — 400 до похода в iiko (раньше уходили в OLAP пустым отчётом)."""

    def test_inverted_dates(self):
        client, mod = _employee_client()

        class Boom:
            def __init__(self):
                raise AssertionError('в iiko ходить нельзя')
        with patch.object(mod, 'OlapReports', Boom):
            bodies = [
                ('/api/employee-analytics', {'employee_name': 'Иван Петров'}),
                ('/api/employee-discount-checks', {'employee_name': 'Иван Петров'}),
                ('/api/employee-compare', {'employee_names': ['Иван Петров', 'Анна Смирнова']}),
            ]
            for url, body in bodies:
                body = dict(body, date_from='2020-01-12', date_to='2020-01-06', bar='ligovskiy')
                r = client.post(url, json=body)
                self.assertEqual(r.status_code, 400, url)
                self.assertIn('date_from позже date_to', r.get_json()['error'])


class HoursByRoleTodayTest(unittest.TestCase):
    """Смена рабочего дня ещё идёт — это не «пробел в часах» и не прошедшая дневная смена."""

    def test_default_today_is_business_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ShiftsManager(db_path=os.path.join(tmp, 'shifts.db'))
            loc = mgr.get_locations()[0]
            role = mgr.get_roles()[0]
            mgr.create_shift('2020-01-13', 'Иван Петров', loc['id'], role['id'], employee_id='g1')
            mgr.create_shift('2020-01-14', 'Иван Петров', loc['id'], role['id'], employee_id='g1')
            with patch.object(msk_time, 'now', lambda: NIGHT_15):
                rows = mgr.get_hours_by_role_for_period('2020-01-01', '2020-01-31')
            self.assertEqual(len(rows), 1)
            row = rows[0]
            # 13-е прошло без факта — пробел; 14-е — смена, которая идёт в ночь на 15-е.
            self.assertEqual(row['shifts_without_fact'], 1)
            self.assertEqual(row['day_shifts'], 1)
            self.assertEqual(row['shifts_planned'], 2)


class SalaryMonthTest(unittest.TestCase):
    @patch.object(msk_time, 'now', lambda: NIGHT_FEB_1)
    def test_current_month_by_business_day(self):
        from core import salary_payload
        self.assertEqual(salary_payload.current_month(), '2020-01', 'ночь на 1-е — ещё январь')
        self.assertEqual(salary_payload.previous_month(), '2019-12')

    @patch.object(msk_time, 'now', lambda: NIGHT_FEB_1)
    def test_months_to_sync_by_business_day(self):
        from core import salary_scheduler
        self.assertEqual(salary_scheduler.months_to_sync(), ['2020-01'])

    @patch.object(msk_time, 'now', lambda: datetime(2020, 2, 3, 12, 0, tzinfo=msk_time.MOSCOW_TZ))
    def test_months_to_sync_first_week(self):
        from core import salary_scheduler
        self.assertEqual(salary_scheduler.months_to_sync(), ['2020-02', '2020-01'])


@patch.object(msk_time, 'now', lambda: NIGHT_15)
class ScheduleLoadTodayTest(unittest.TestCase):
    """«Без факта» в нагрузке графика — до рабочего дня бара, а не до даты UTC."""

    def test_widgets_missing_fact_by_business_day(self):
        import routes.schedule as sched
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ShiftsManager(db_path=os.path.join(tmp, 'shifts.db'))
            loc = mgr.get_locations()[0]
            role = mgr.get_roles()[0]
            mgr.create_shift('2020-01-13', 'Иван Петров', loc['id'], role['id'], employee_id='g1')
            mgr.create_shift('2020-01-14', 'Иван Петров', loc['id'], role['id'], employee_id='g1')
            app = Flask(__name__)
            app.register_blueprint(sched.schedule_bp)
            with patch.object(sched, 'shifts_mgr', mgr):
                r = app.test_client().get('/api/schedule/widgets/2020/1')
            self.assertEqual(r.status_code, 200)
            load = r.get_json()['employees_load']
            self.assertEqual(len(load), 1)
            self.assertEqual(load[0]['missing_fact'], 1, '13-е прошло, 14-е ещё идёт')


if __name__ == '__main__':
    unittest.main()
