# -*- coding: utf-8 -*-
"""Тесты разбивки «Маркетинга» по барам (параметр store / venue, 2026-09-29).

Правило (core/guest_analytics.py, докстринг модуля): бар как отдельное заведение —
только его чеки; регистрация закреплена за баром первой покупки в сети; сравнения
баров — только для всей сети; «Точки» с баром — его гости во всех барах; Orderia и
карточка гостя на бары не делятся.

Сети и прода не касаются: витрина во временном файле.
Запуск: py -3 -m pytest tests/test_guests_venue.py -q

Витрина (все регистрации — из iiko):

    гость  регистрация  чеки (дата, бар, выручка, позиции)
    A      2026-01-05   01-05 bolshoy 1000 [Пиво А]; 01-20 ligovskiy 2000 [Пиво Б];
                        03-20 ligovskiy 700 [Пиво Б]
    B      2026-03-01   03-02 ligovskiy 1500 [Пиво Б 1000, Сыр 500];
                        03-15 ligovskiy 800 [Пиво В]
    C      2026-03-10   03-10 bolshoy 300 [Сыр]

Первая покупка в сети: A — bolshoy, B — ligovskiy, C — bolshoy. В ligovskiy гость A
«новый» 20 января, хотя в сети он с 5-го.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import guest_analytics as ga           # noqa: E402
from core.guest_store import GuestStore           # noqa: E402
from core.venues_config import PHYSICAL_VENUES   # noqa: E402

GUESTS = {
    '79001': ('2026-01-05', [('2026-01-05', 'bolshoy', 1000.0, [('Пиво А', 2, 1000.0)]),
                             ('2026-01-20', 'ligovskiy', 2000.0, [('Пиво Б', 4, 2000.0)]),
                             ('2026-03-20', 'ligovskiy', 700.0, [('Пиво Б', 1, 700.0)])]),
    '79002': ('2026-03-01', [('2026-03-02', 'ligovskiy', 1500.0, [('Пиво Б', 2, 1000.0),
                                                                  ('Сыр', 1, 500.0)]),
                             ('2026-03-15', 'ligovskiy', 800.0, [('Пиво В', 1, 800.0)])]),
    '79003': ('2026-03-10', [('2026-03-10', 'bolshoy', 300.0, [('Сыр', 1, 300.0)])]),
}


class VenueBase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        os.unlink(self.db_path)
        self.store = GuestStore(self.db_path)
        with self.store.conn() as conn:
            for gid, (reg, visits) in GUESTS.items():
                first = min(visits)
                conn.execute(
                    "INSERT INTO guests (guest_id, name, phone, card_number, "
                    "registration_date, registration_source, first_order_date, "
                    "first_order_store, last_visit_date, updated_at) "
                    "VALUES (?, 'Гость', ?, ?, ?, 'iiko', ?, ?, ?, '2026-01-01')",
                    (gid, gid, 'c' + gid, reg, first[0], first[1], max(visits)[0]))
                for n, (day, bar, revenue, items) in enumerate(visits):
                    conn.execute(
                        "INSERT INTO receipts (open_date, store, order_num, guest_id, "
                        "revenue, discount, full_sum) VALUES (?, ?, ?, ?, ?, 0, ?)",
                        (day, bar, str(n), gid, revenue, revenue))
                    for dish, amount, dish_revenue in items:
                        conn.execute(
                            "INSERT INTO receipt_items (open_date, store, order_num, "
                            "guest_id, dish_name, amount, revenue) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (day, bar, str(n), gid, dish, amount, dish_revenue))
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


class TestVenueParam(VenueBase):
    def test_resolve_venue(self):
        for key in PHYSICAL_VENUES:
            self.assertEqual(ga.resolve_venue(key), key)
        for bad in (None, '', 'all', 'Лиговский', "bolshoy'; DROP TABLE guests;--"):
            self.assertIsNone(ga.resolve_venue(bad), bad)

    def test_meta_says_which_bar(self):
        _, meta = self.ctx(venue='ligovskiy')
        self.assertEqual(meta['venue'], 'ligovskiy')
        self.assertEqual(meta['venue_name'], 'Лиговский')
        _, meta = self.ctx(venue='нет-такого')
        self.assertIsNone(meta['venue'])
        self.assertIsNone(meta['venue_name'])


class TestGrowthAndActivity(VenueBase):
    def test_registrations_by_bar_add_up_to_network(self):
        """Регистрация — за баром первой покупки: по барам в сумме ровно сеть."""
        period, meta = self.ctx('quarter', '2026-02-01')
        net = ga.base_growth(self.store, period, meta)['period']['registrations']
        per_bar = {v: ga.base_growth(self.store, period, meta, v)['period']['registrations']
                   for v in PHYSICAL_VENUES}
        self.assertEqual(net, 3)
        self.assertEqual(per_bar['bolshoy'], 2, 'A и C начали в Большом')
        self.assertEqual(per_bar['ligovskiy'], 1, 'только B: A пришёл в Лиговский из Большого')
        self.assertEqual(sum(per_bar.values()), net)

    def test_first_orders_are_first_check_in_this_bar(self):
        """Новый гость бара — первый чек В ЭТОМ баре, поэтому сумма по барам больше сети."""
        period, meta = self.ctx('quarter', '2026-02-01')
        net = ga.base_growth(self.store, period, meta)['period']['first_orders']
        bolshoy = ga.base_growth(self.store, period, meta, 'bolshoy')['period']['first_orders']
        ligovskiy = ga.base_growth(self.store, period, meta, 'ligovskiy')['period']['first_orders']
        self.assertEqual((net, bolshoy, ligovskiy), (3, 2, 2))
        # В марте A в Лиговском уже не новый (первый визит — 20 января).
        period, meta = self.ctx('month', '2026-03-15')
        march = ga.base_growth(self.store, period, meta, 'ligovskiy')['period']
        self.assertEqual(march['first_orders'], 1)
        self.assertEqual(march['registrations'], 1)
        self.assertEqual(march['conversion_pct'], 100.0)

    def test_base_size_is_guests_with_a_check_in_the_bar(self):
        period, meta = self.ctx()
        self.assertEqual(ga.base_growth(self.store, period, meta)['lifetime']['base_size'], 3)
        self.assertEqual(ga.base_growth(self.store, period, meta, 'bolshoy')
                         ['lifetime']['base_size'], 2)
        self.assertEqual(ga.base_growth(self.store, period, meta, 'varshavskaya')
                         ['lifetime']['base_size'], 0)

    def test_activity_counts_last_visit_to_this_bar(self):
        period, meta = self.ctx()          # срез 31.03
        net = {s['segment']: s['count'] for s in ga.activity(self.store, period, meta)['segments']}
        bolshoy = {s['segment']: s['count']
                   for s in ga.activity(self.store, period, meta, 'bolshoy')['segments']}
        self.assertEqual(net['active'], 3)
        # A в Большом последний раз 05.01 — 85 дней до среза: «спит» для этого бара.
        self.assertEqual((bolshoy['active'], bolshoy['sleeping']), (1, 1))

    def test_frequency_counts_visits_to_this_bar(self):
        period, meta = self.ctx()
        lig = ga.frequency(self.store, period, meta, 'ligovskiy')['period']
        self.assertEqual((lig['guests_with_visits'], lig['total_visits']), (2, 3))
        bol = ga.frequency(self.store, period, meta, 'bolshoy')['period']
        self.assertEqual((bol['guests_with_visits'], bol['total_visits']), (1, 1))

    def test_dynamics_balance_holds_per_bar(self):
        period, meta = self.ctx()
        for venue in (None,) + tuple(PHYSICAL_VENUES):
            rows = ga.base_dynamics(self.store, period, meta, 3, venue)['months']
            for row in rows:
                self.assertEqual(row['active_end'], row['active_start'] + row['new']
                                 + row['reactivated'] - row['churned'], (venue, row))
        lig = {r['month']: r for r in ga.base_dynamics(self.store, period, meta, 3, 'ligovskiy')['months']}
        self.assertEqual(lig['2026-01']['new'], 1, 'A — новый гость Лиговского в январе')
        self.assertEqual(lig['2026-03']['new'], 1, 'B')
        self.assertEqual(lig['2026-03']['reactivated'], 1, 'A вернулся после паузы > 30 дней')


class TestCohorts(VenueBase):
    def test_retention_counts_returns_to_this_bar(self):
        period, meta = self.ctx('month', '2026-06-15')      # срез 30.06
        net = {c['cohort']: c for c in ga.cohort_retention(self.store, period, meta)['cohorts']}
        bol = {c['cohort']: c for c in
               ga.cohort_retention(self.store, period, meta, venue='bolshoy')['cohorts']}
        lig = {c['cohort']: c for c in
               ga.cohort_retention(self.store, period, meta, venue='ligovskiy')['cohorts']}
        self.assertEqual(net['2026-01']['returned_pct']['30'], 100.0, 'A вернулся в сеть через 15 дней')
        self.assertEqual(bol['2026-01']['returned_pct']['30'], 0.0, 'в Большой A не вернулся')
        self.assertEqual(bol['2026-01']['returned_pct']['90'], 0.0)
        # В Лиговском A «новый» 20.01, следующий визит 20.03 — через 59 дней.
        self.assertEqual(lig['2026-01']['returned_pct']['30'], 0.0)
        self.assertEqual(lig['2026-01']['returned_pct']['60'], 100.0)
        self.assertEqual(lig['2026-03']['returned_pct']['30'], 100.0, 'B вернулся через 13 дней')

    def test_lifecycle_takes_registrations_of_the_bar(self):
        period, meta = self.ctx('month', '2026-06-15')
        lig = ga.lifecycle_cohorts(self.store, period, meta, venue='ligovskiy')['cohorts']
        self.assertEqual([(c['cohort'], c['guests']) for c in lig], [('2026-03', 1)],
                         'A зарегистрирован в Большом — в когортах Лиговского его нет')
        self.assertEqual(lig[0]['order2_pct'], 100.0, 'у B два чека в Лиговском')
        bol = {c['cohort']: c for c in
               ga.lifecycle_cohorts(self.store, period, meta, venue='bolshoy')['cohorts']}
        self.assertEqual(bol['2026-01']['order2_pct'], 0.0,
                         'в Большом у A один чек, остальные — в другом баре')

    def test_cohort_revenue_counts_only_the_bar(self):
        period, meta = self.ctx('month', '2026-06-15')
        reg = {c['cohort']: c['revenue'] for c in
               ga.cohort_revenue(self.store, period, meta, 'registration', venue='ligovskiy')['cohorts']}
        self.assertEqual(reg, {'2026-03': 2300})
        first = {c['cohort']: c['revenue'] for c in
                 ga.cohort_revenue(self.store, period, meta, 'first_order', venue='ligovskiy')['cohorts']}
        self.assertEqual(first, {'2026-01': 2700, '2026-03': 2300})


class TestLtvProductsVenues(VenueBase):
    def test_ltv_of_the_bar_and_no_bar_comparison(self):
        period, meta = self.ctx()
        net = ga.ltv(self.store, period, meta)
        bol = ga.ltv(self.store, period, meta, 'bolshoy')
        self.assertEqual((net['lifetime']['guests'], net['lifetime']['revenue']), (3, 6300))
        self.assertTrue(net['by_venue'], 'у сети сравнение баров есть')
        self.assertEqual((bol['lifetime']['guests'], bol['lifetime']['revenue'],
                          bol['lifetime']['avg_ltv']), (2, 1300, 650))
        self.assertEqual(bol['by_venue'], [], 'сравнение баров — только для всей сети')

    def test_products_first_is_first_visit_to_the_bar(self):
        period, meta = self.ctx('quarter', '2026-02-01')
        lig = {i['dish_name']: i['guests'] for i in
               ga.products(self.store, period, meta, 'first', venue='ligovskiy')['items']}
        self.assertEqual(lig, {'Пиво Б': 2, 'Сыр': 1},
                         'A — 20.01 в Лиговском, B — 02.03; Пиво А из Большого не входит')
        net = {i['dish_name']: i['guests'] for i in
               ga.products(self.store, period, meta, 'first')['items']}
        self.assertEqual(net, {'Сыр': 2, 'Пиво А': 1, 'Пиво Б': 1})
        repeat = {i['dish_name']: i['revenue'] for i in
                  ga.products(self.store, period, meta, 'repeat', venue='ligovskiy')['items']}
        self.assertEqual(repeat, {'Пиво Б': 700, 'Пиво В': 800})

    def test_products_top_and_order_of_ties(self):
        """Равные по главному показателю — по названию (детерминированный порядок)."""
        period, meta = self.ctx('quarter', '2026-02-01')
        top = ga.products(self.store, period, meta, 'top', venue='bolshoy')['items']
        self.assertEqual([i['dish_name'] for i in top], ['Пиво А', 'Сыр'])
        first = ga.products(self.store, period, meta, 'first')['items']
        self.assertEqual([i['dish_name'] for i in first], ['Сыр', 'Пиво А', 'Пиво Б'])

    def test_pairs_only_in_checks_of_the_bar(self):
        period, meta = self.ctx()
        lig = ga.product_pairs(self.store, period, meta, venue='ligovskiy')
        self.assertEqual(lig['checks_with_2plus_items'], 1)
        self.assertEqual([(p['dish_a'], p['dish_b']) for p in lig['pairs']], [('Пиво Б', 'Сыр')])
        bol = ga.product_pairs(self.store, period, meta, venue='bolshoy')
        self.assertEqual((bol['checks_with_2plus_items'], bol['pairs']), (0, []))

    def test_venues_report_takes_guests_of_the_bar_in_all_bars(self):
        period, meta = self.ctx()
        lig = ga.venues_analytics(self.store, period, meta, 'ligovskiy')
        self.assertEqual(lig['guests_total'], 2, 'A и B')
        self.assertEqual({r['store']: r['guests'] for r in lig['first_store']},
                         {'bolshoy': 1, 'ligovskiy': 1}, 'A пришёл в сеть через Большой')
        self.assertEqual({r['store']: r['visits'] for r in lig['distribution_lifetime']},
                         {'bolshoy': 1, 'ligovskiy': 4}, 'визиты гостей бара во ВСЕ бары')
        self.assertEqual((lig['multi_store_guests'], lig['multi_store_share_pct']), (1, 50.0))
        self.assertEqual(ga.venues_analytics(self.store, period, meta)['guests_total'], 3)

    def test_summary_of_the_bar(self):
        period, meta = self.ctx()
        s = ga.summary(self.store, period, meta, 'ligovskiy')
        self.assertEqual((s['revenue_period'], s['orders_period']), (3000, 3))
        self.assertEqual(s['avg_check'], 1000)
        self.assertEqual(s['registrations_by_store'], [], 'сравнение баров — только для сети')
        self.assertFalse(s['never']['available'])
        self.assertEqual(s['never']['reason'], 'venue')
        net = ga.summary(self.store, period, ga.build_meta(self.store, period))
        self.assertIsNone(net['never']['reason'])
        self.assertTrue(net['registrations_by_store'])


class TestRoutes(VenueBase):
    """HTTP: ?store= доходит до расчёта, кэш не путает бары, Orderia и карточка — сеть."""

    def setUp(self):
        super().setUp()
        from flask import Flask
        import extensions
        import routes.guests as rg
        self.rg = rg
        self.saved_get_store = rg.get_store
        rg.get_store = lambda: self.store
        # Кэш отчётов общий на процесс: чужой тест с той же датой не должен
        # подсунуть свои цифры.
        extensions.DASHBOARD_OLAP_CACHE.clear()
        app = Flask(__name__)
        app.register_blueprint(rg.guests_bp)
        self.client = app.test_client()

    def tearDown(self):
        self.rg.get_store = self.saved_get_store
        super().tearDown()

    def get(self, path, **params):
        query = dict({'period_type': 'month', 'anchor': '2026-03-15'}, **params)
        response = self.client.get(path, query_string=query)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def test_store_reaches_every_report_and_meta(self):
        for path in ('/api/guests/summary', '/api/guests/base-growth', '/api/guests/base-dynamics',
                     '/api/guests/activity', '/api/guests/frequency',
                     '/api/guests/cohorts/lifecycle', '/api/guests/retention',
                     '/api/guests/cohorts/revenue', '/api/guests/rfm', '/api/guests/ltv',
                     '/api/guests/products', '/api/guests/product-pairs', '/api/guests/venues'):
            body = self.get(path, store='ligovskiy')
            self.assertEqual(body['meta']['venue'], 'ligovskiy', path)
            self.assertEqual(body['meta']['venue_name'], 'Лиговский', path)
            self.assertIsNone(self.get(path)['meta']['venue'], path)

    def test_cache_keeps_bars_apart(self):
        """Ключ кэша включает бар: сеть, потом бар — разные цифры, а не копия."""
        net = self.get('/api/guests/cohorts/lifecycle', anchor='2026-06-15')['data']['cohorts']
        lig = self.get('/api/guests/cohorts/lifecycle', anchor='2026-06-15',
                       store='ligovskiy')['data']['cohorts']
        self.assertNotEqual(net, lig)
        self.assertEqual([c['cohort'] for c in lig], ['2026-03'])
        summary_net = self.get('/api/guests/summary')['data']
        summary_bol = self.get('/api/guests/summary', store='bolshoy')['data']
        self.assertEqual((summary_net['orders_period'], summary_bol['orders_period']), (4, 1))

    def test_unknown_store_is_network(self):
        self.assertEqual(self.get('/api/guests/summary', store='Лиговский')['data'],
                         self.get('/api/guests/summary')['data'])

    def test_never_and_guest_card_ignore_store(self):
        body = self.get('/api/guests/never', store='ligovskiy')
        self.assertIsNone(body['meta']['venue'], 'Orderia на бары не делится')
        self.assertEqual(body['data'], self.get('/api/guests/never')['data'])
        card = self.get('/api/guests/guest/79001', store='bolshoy')
        self.assertIsNone(card['meta']['venue'])
        self.assertEqual(card['data']['slices']['lifetime']['orders'], 3,
                         'карточка — все чеки гостя, во всех барах')

    def test_rfm_csv_carries_bar(self):
        response = self.client.get('/api/guests/rfm', query_string={
            'period_type': 'month', 'anchor': '2026-03-15', 'store': 'bolshoy',
            'export': 'csv'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('_bolshoy.csv', response.headers['Content-Disposition'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
