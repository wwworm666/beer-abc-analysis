# -*- coding: utf-8 -*-
"""Тесты вкладки «Отток» (§17, core/guest_analytics.churn_all) и LTV на дату (§8).

Определения — докстринг churn_all и docs/guests.md (§17). Сети и прода не касаются:
витрина во временном файле. Запуск: py -3 -m pytest tests/test_guests_churn.py -q

Основная витрина (все чеки в Большом; чеки марта по 1 500 ₽, остальные по 1 000 ₽;
последний день с чеками — 20.05.2026, его задаёт гость H):

    гость  визиты                    март 2026 при X = 30
    A      10.02, 05.03              остался
    B      15.02                     ушёл (1 визит)
    C      01.01, 20.03              вернулся (на 28.02 пауза 58 дней)
    D      10.03, 25.03              новый, вернулся
    E      01.12.2025, 15.01         мёртв на начало и на конец — ни в одной графе
    F      05.01, 15.01, 29.01       жив на начало ровно на границе (пауза 30), ушёл
    G      28.03                     новый, не вернулся
    H      20.05                     задаёт последний день с чеками
"""

import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import guest_analytics as ga           # noqa: E402
from core.guest_store import GuestStore           # noqa: E402
from core.venues_config import PHYSICAL_VENUES   # noqa: E402


def _visits(dates, bar='bolshoy'):
    """Чеки гостя: даты -> [(день, бар, выручка)]; март по 1 500 ₽, остальное по 1 000 ₽."""
    return [(d, bar, 1500.0 if d.startswith('2026-03') else 1000.0) for d in dates]


MAIN = {
    'A': _visits(['2026-02-10', '2026-03-05']),
    'B': _visits(['2026-02-15']),
    'C': _visits(['2026-01-01', '2026-03-20']),
    'D': _visits(['2026-03-10', '2026-03-25']),
    'E': _visits(['2025-12-01', '2026-01-15']),
    'F': _visits(['2026-01-05', '2026-01-15', '2026-01-29']),
    'G': _visits(['2026-03-28']),
    'H': _visits(['2026-05-20']),
}


class ChurnBase(unittest.TestCase):
    GUESTS = MAIN

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        os.unlink(self.db_path)
        self.store = GuestStore(self.db_path)
        with self.store.conn() as conn:
            for n, (key, visits) in enumerate(sorted(self.GUESTS.items())):
                gid = '7900' + str(n)
                first, last = min(visits), max(visits)
                conn.execute(
                    "INSERT INTO guests (guest_id, name, phone, card_number, "
                    "registration_date, registration_source, first_order_date, "
                    "first_order_store, last_visit_date, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'iiko', ?, ?, ?, '2026-01-01')",
                    (gid, key, gid, 'c' + gid, first[0], first[0], first[1], last[0]))
                for k, (day, bar, revenue) in enumerate(visits):
                    conn.execute(
                        "INSERT INTO receipts (open_date, store, order_num, guest_id, "
                        "revenue, discount, full_sum) VALUES (?, ?, ?, ?, ?, 0, ?)",
                        (day, bar, str(k), gid, revenue, revenue))
            conn.commit()

    def tearDown(self):
        for suffix in ('', '-wal', '-shm', '.backup_v1'):
            try:
                os.unlink(self.db_path + suffix)
            except OSError:
                pass

    def ctx(self, period_type='month', anchor='2026-03-15', venue=None):
        period = ga.resolve_period(period_type, anchor)
        return period, ga.build_meta(self.store, period, venue)

    def churn(self, dead_days=30, period_type='month', anchor='2026-03-15', venue=None,
              periods=None):
        period, meta = self.ctx(period_type, anchor, venue)
        return ga.churn(self.store, period, meta, dead_days, periods, venue)


class TestMainNumbers(ChurnBase):
    def test_march_x30(self):
        d = self.churn(30)
        p = d['period']
        self.assertEqual(d['dead_days'], 30)
        self.assertEqual(d['data_to'], '2026-05-20')
        self.assertEqual((p['state'], p['asof']), ('complete', '2026-03-31'))
        self.assertEqual(
            (p['start_alive'], p['died'], p['reactivated'], p['bounced'], p['new'],
             p['new_died'], p['end_alive']),
            (3, 2, 1, 0, 2, 0, 4), 'A, B, F на начало; ушли B и F; вернулся C; новые D и G')
        self.assertEqual(p['churn_pct'], 66.7)
        self.assertEqual((p['newbie_no_return'], p['newbie_no_return_pct']), (1, 50.0),
                         'G не вернулся, D вернулся через 15 дней')
        self.assertEqual(p['newbie_matures_on'], '2026-05-01', '31.03 + 30 + 1')

    def test_march_leavers(self):
        buckets = {b['segment']: b for b in self.churn(30)['leavers']['buckets']}
        self.assertEqual(self.churn(30)['leavers']['total'], 2)
        self.assertEqual((buckets['1']['count'], buckets['1']['avg_ltv']), (1, 1000), 'B')
        self.assertEqual((buckets['2-3']['count'], buckets['2-3']['avg_ltv']), (1, 3000), 'F')
        self.assertEqual((buckets['4-8']['count'], buckets['4-8']['avg_ltv']), (0, None))
        self.assertEqual(buckets['1']['share_pct'], 50.0)

    def test_march_x60_differs_and_is_not_mature(self):
        p = self.churn(60)['period']
        self.assertEqual((p['start_alive'], p['died'], p['end_alive']), (5, 2, 5),
                         'при 60 днях живы на начало ещё C и E, ушли E и F')
        self.assertEqual(p['churn_pct'], 40.0)
        self.assertIsNone(p['newbie_no_return_pct'], '31.03 + 61 = 31.05 — позже 20.05')
        self.assertEqual(p['newbie_matures_on'], '2026-05-31')

    def test_quarter_new_guests_can_leave_in_the_same_period(self):
        p = self.churn(30, 'quarter', '2026-02-01')['period']
        self.assertEqual(
            (p['start_alive'], p['died'], p['new'], p['new_died'], p['end_alive']),
            (1, 1, 6, 2, 4), 'E жив на 31.12 (пауза ровно 30) и ушёл; B и F новые и ушли')
        self.assertEqual(p['churn_pct'], 100.0, 'отток — только от живых на начало')
        self.assertEqual((p['newbie_no_return'], p['newbie_no_return_pct']), (3, 50.0),
                         'B, C (вернулся через 78 дней) и G')

    def test_partial_and_future_periods(self):
        may = self.churn(30, 'month', '2026-05-15')['period']
        self.assertEqual((may['state'], may['asof']), ('partial', '2026-05-20'))
        self.assertIsNone(may['newbie_no_return_pct'])
        self.assertEqual(may['newbie_matures_on'], '2026-07-01')
        june = self.churn(30, 'month', '2026-06-15')['period']
        self.assertEqual(june['state'], 'future')
        for key in ('start_alive', 'died', 'new', 'end_alive', 'churn_pct', 'asof'):
            self.assertIsNone(june[key], key + ': у будущего периода нет чисел, а не нули')

    def test_zero_base_gives_none_not_zero(self):
        p = self.churn(30, 'month', '2025-12-15')['period']
        self.assertEqual((p['start_alive'], p['new']), (0, 1))
        self.assertIsNone(p['churn_pct'], '0 живых на начало — прочерк, а не 0%')

    def test_series_order_and_trim(self):
        series = self.churn(30)['series']
        self.assertEqual([r['p_start'] for r in series],
                         ['2025-12-01', '2026-01-01', '2026-02-01', '2026-03-01'],
                         'от старых к новым, раньше первого чека витрины — ничего')


class TestInvariants(ChurnBase):
    def test_balance_holds_in_every_row(self):
        for dead_days in ga.CHURN_DEAD_DAYS_CHOICES:
            for period_type, anchor in (('week', '2026-03-15'), ('month', '2026-05-15'),
                                        ('quarter', '2026-05-15'), ('year', '2026-05-15')):
                for row in self.churn(dead_days, period_type, anchor)['series']:
                    if row['state'] == 'future':
                        continue
                    self.assertEqual(row['end_alive'],
                                     row['start_alive'] + row['new'] + row['reactivated']
                                     - row['died'] - row['new_died'],
                                     (dead_days, period_type, row))

    def test_end_of_period_is_start_of_next(self):
        for dead_days in ga.CHURN_DEAD_DAYS_CHOICES:
            for period_type in ('week', 'month', 'quarter'):
                for venue in (None, 'bolshoy'):
                    rows = [r for r in self.churn(dead_days, period_type, '2026-05-15', venue,
                                                  periods=60)['series']
                            if r['state'] == 'complete']
                    for prev, nxt in zip(rows, rows[1:]):
                        self.assertEqual(prev['end_alive'], nxt['start_alive'],
                                         (dead_days, period_type, venue, nxt['p_start']))

    def test_x30_alive_is_active_and_new_is_first_orders(self):
        period, meta = self.ctx()
        active = {s['segment']: s['count']
                  for s in ga.activity(self.store, period, meta)['segments']}['active']
        p = self.churn(30)['period']
        self.assertEqual(p['end_alive'], active, 'при X = 30 живые = Active (закрытый месяц)')
        first_orders = ga.base_growth(self.store, period, meta)['period']['first_orders']
        self.assertEqual(p['new'], first_orders)


class TestLostEquivalence(ChurnBase):
    GUESTS = dict(MAIN, K=_visits(['2025-06-01']))

    def test_x180_dead_is_lost(self):
        period, meta = self.ctx()
        lost = {s['segment']: s['count']
                for s in ga.activity(self.store, period, meta)['segments']}['lost']
        p = self.churn(180)['period']
        customers = 8   # A-G и K: первый визит не позже 31.03
        self.assertEqual(customers - p['end_alive'], lost)
        self.assertEqual(lost, 1, 'K: последний визит 01.06.2025')


class TestBoundaries(ChurnBase):
    GUESTS = {
        'R31': _visits(['2026-03-01', '2026-04-01']),   # возврат на 31-й день
        'R32': _visits(['2026-03-01', '2026-04-02']),   # возврат на 32-й день
        'S30': _visits(['2026-01-29']),                 # на 28.02 пауза 30
        'S31': _visits(['2026-01-28']),                 # на 28.02 пауза 31
        'Z': _visits(['2026-06-30']),
    }

    def test_newbie_window_matches_the_dead_rule(self):
        p = self.churn(30)['period']
        self.assertEqual((p['new'], p['newbie_no_return']), (2, 1),
                         'вернувшийся на 31-й день ни дня не был мёртвым, на 32-й — был')

    def test_start_gap_x_is_alive_x_plus_one_is_dead(self):
        p = self.churn(30)['period']
        self.assertEqual((p['start_alive'], p['died']), (1, 1), 'жив только S30, и он ушёл')


class TestVenue(ChurnBase):
    GUESTS = {
        'V': [('2026-02-20', 'bolshoy', 1000.0), ('2026-03-15', 'ligovskiy', 1000.0)],
        'W': [('2026-02-01', 'bolshoy', 1000.0)],
        'Z': [('2026-05-20', 'ligovskiy', 1000.0)],
    }

    def test_bar_as_separate_venue(self):
        net = self.churn(30)['period']
        bol = self.churn(30, venue='bolshoy')['period']
        lig = self.churn(30, venue='ligovskiy')['period']
        self.assertEqual((net['start_alive'], net['died'], net['end_alive']), (2, 1, 1),
                         'в сети V остался (был в Лиговском 15.03), W ушёл')
        self.assertEqual((bol['start_alive'], bol['died'], bol['end_alive']), (2, 2, 0),
                         'из Большого ушли оба')
        self.assertEqual((lig['new'], lig['end_alive']), (1, 1), 'в Лиговском V — новый')

    def test_bar_without_late_checks_still_loses_guests(self):
        """Срез — последний полный день сети, а не последний чек бара (Большой: 20.02)."""
        bol = self.churn(30, venue='bolshoy')['period']
        self.assertEqual((bol['state'], bol['asof']), ('complete', '2026-03-31'))

    def test_venue_series_starts_with_first_check_of_the_bar(self):
        lig = self.churn(30, venue='ligovskiy')['series']
        self.assertEqual(lig[0]['p_start'], '2026-03-01', 'первый чек Лиговского — 15.03')


class TestDataTo(ChurnBase):
    def test_partial_day_is_not_data(self):
        """Дневной пересинк приносит неполный сегодняшний день — его в срез не берём."""
        with mock.patch('core.msk_time.business_today', return_value=date(2026, 5, 20)):
            d = self.churn(30, 'month', '2026-05-15')
        self.assertEqual(d['data_to'], '2026-05-19')
        self.assertEqual((d['period']['asof'], d['period']['new']), ('2026-05-19', 0),
                         'H пришёл 20.05 — этот день ещё не закончен')

    def test_meta_without_receipts(self):
        self.assertIsNone(ga.data_to({'coverage_to': None}))


class TestEmptyStore(ChurnBase):
    GUESTS = {}

    def test_empty_store_does_not_crash(self):
        d = self.churn(30)
        self.assertEqual((d['series'], d['period'], d['data_to']), ([], None, None))
        self.assertEqual(d['leavers']['total'], 0)


class TestParams(unittest.TestCase):
    def test_dead_days(self):
        self.assertEqual(ga.parse_dead_days('90'), 90)
        self.assertEqual(ga.parse_dead_days(60), 60)
        for bad in (None, '', '45', 'abc', '30.5', '-30'):
            self.assertEqual(ga.parse_dead_days(bad), ga.CHURN_DEAD_DAYS_DEFAULT, bad)

    def test_series_len(self):
        self.assertEqual(ga.parse_series_len(None, 'month'), 24)
        self.assertEqual(ga.parse_series_len('x', 'week'), 26)
        self.assertEqual(ga.parse_series_len('', 'quarter'), 12)
        self.assertEqual(ga.parse_series_len('1', 'month'), ga.CHURN_SERIES_MIN)
        self.assertEqual(ga.parse_series_len('999', 'year'), ga.CHURN_SERIES_MAX)
        self.assertEqual(ga.parse_series_len('12', 'month'), 12)


class TestChurnRoute(ChurnBase):
    def setUp(self):
        super().setUp()
        from flask import Flask
        import extensions
        import routes.guests as rg
        self.rg = rg
        self.saved_get_store = rg.get_store
        rg.get_store = lambda: self.store
        extensions.DASHBOARD_OLAP_CACHE.clear()
        app = Flask(__name__)
        app.register_blueprint(rg.guests_bp)
        self.client = app.test_client()

    def tearDown(self):
        self.rg.get_store = self.saved_get_store
        super().tearDown()

    def get(self, **params):
        query = dict({'period_type': 'month', 'anchor': '2026-03-15'}, **params)
        response = self.client.get('/api/guests/churn', query_string=query)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()['data']

    def test_threshold_is_echoed_and_cache_keeps_thresholds_apart(self):
        x30 = self.get()
        x60 = self.get(dead_days='60')
        self.assertEqual((x30['dead_days'], x30['period']['churn_pct']), (30, 66.7))
        self.assertEqual((x60['dead_days'], x60['period']['churn_pct']), (60, 40.0),
                         'один расчёт на все пороги в кэше — отдаётся запрошенный')
        self.assertEqual(x60['choices'], list(ga.CHURN_DEAD_DAYS_CHOICES))

    def test_bad_params_fall_back(self):
        d = self.get(dead_days='45', periods='много')
        self.assertEqual(d['dead_days'], 30)
        self.assertEqual(len(d['series']), 4, 'длина по умолчанию, обрезанная началом витрины')


if __name__ == '__main__':
    unittest.main()
