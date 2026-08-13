# -*- coding: utf-8 -*-
"""Тесты слияния /discounts в «Маркетинг»: фильтр точки в RFM и правки анализа акций.

Сети и прода не касаются: витрина во временном файле, iiko подменяется фейком.
Запуск: py -3 -m pytest tests/test_guests_marketing.py -q
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import guest_analytics as ga           # noqa: E402
from core.guest_store import GuestStore           # noqa: E402


class RfmVenueBase(unittest.TestCase):
    """Витрина с чеками в разных барах."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        os.unlink(self.db_path)
        self.store = GuestStore(self.db_path)

    def tearDown(self):
        for suffix in ('', '-wal', '-shm', '.backup_v1'):
            try:
                os.unlink(self.db_path + suffix)
            except OSError:
                pass

    def add_guest(self, guest_id, card, visits):
        """visits — список (дата, бар, выручка)."""
        first = min(v[0] for v in visits)
        last = max(v[0] for v in visits)
        with self.store.conn() as conn:
            conn.execute(
                "INSERT INTO guests (guest_id, name, phone, card_number, "
                "registration_date, registration_source, first_order_date, "
                "first_order_store, last_visit_date, updated_at) "
                "VALUES (?, 'Гость', ?, ?, ?, 'iiko', ?, ?, ?, '2026-01-01')",
                (guest_id, guest_id, card, first, first, visits[0][1], last))
            for i, (day, venue, revenue) in enumerate(visits):
                conn.execute(
                    "INSERT INTO receipts (open_date, store, order_num, guest_id, "
                    "revenue, discount, full_sum) VALUES (?, ?, ?, ?, ?, 0, ?)",
                    (day, venue, str(i), guest_id, revenue, revenue))
            conn.commit()

    def rfm(self, venue=None, anchor='2026-08-12'):
        period = ga.resolve_period('month', anchor)
        meta = ga.build_meta(self.store, period)
        return ga.rfm(self.store, period, meta, include_guests=True, venue=venue)


class TestRfmVenueFilter(RfmVenueBase):
    def test_network_counts_every_guest_once(self):
        self.add_guest('79001', '2001', [('2026-08-01', 'bolshoy', 1000.0)])
        self.add_guest('79002', '2002', [('2026-08-02', 'ligovskiy', 2000.0)])
        d = self.rfm()
        self.assertEqual(d['total_guests'], 2)
        self.assertIsNone(d['venue'])

    def test_venue_filter_narrows_population(self):
        self.add_guest('79001', '2001', [('2026-08-01', 'bolshoy', 1000.0)])
        self.add_guest('79002', '2002', [('2026-08-02', 'ligovskiy', 2000.0)])
        d = self.rfm(venue='bolshoy')
        self.assertEqual(d['total_guests'], 1)
        self.assertEqual(d['venue'], 'bolshoy')
        self.assertEqual(d['guests'][0]['guest_id'], '79001')

    def test_metrics_counted_only_for_selected_venue(self):
        """R/F/M считаются по чекам выбранной точки, а не по всем чекам гостя."""
        self.add_guest('79001', '2001', [
            ('2026-06-01', 'bolshoy', 500.0),
            ('2026-06-02', 'bolshoy', 700.0),
            ('2026-08-10', 'ligovskiy', 9000.0),   # свежий визит в ДРУГОМ баре
        ])
        network = self.rfm()['guests'][0]
        bolshoy = self.rfm(venue='bolshoy')['guests'][0]
        self.assertEqual(network['frequency'], 3)
        self.assertEqual(network['monetary'], 10200)
        self.assertEqual(bolshoy['frequency'], 2, 'только визиты Большого')
        self.assertEqual(bolshoy['monetary'], 1200, 'выручка только Большого')
        self.assertGreater(bolshoy['recency_days'], network['recency_days'],
                           'последний визит в этом баре давнее последнего вообще')

    def test_guest_of_two_bars_appears_in_both_slices(self):
        """Сумма по барам больше сетевой — это ожидаемо, гость в двух срезах."""
        self.add_guest('79001', '2001', [
            ('2026-08-01', 'bolshoy', 1000.0),
            ('2026-08-02', 'varshavskaya', 1000.0),
        ])
        self.assertEqual(self.rfm()['total_guests'], 1)
        per_bar = sum(self.rfm(venue=v)['total_guests']
                      for v in ('bolshoy', 'varshavskaya'))
        self.assertEqual(per_bar, 2)

    def test_unknown_venue_key_falls_back_to_network(self):
        """Мусор в параметре не должен давать пустой отчёт или падение."""
        self.add_guest('79001', '2001', [('2026-08-01', 'bolshoy', 1000.0)])
        for bad in ('нет-такого-бара', "bolshoy'; DROP TABLE guests;--", ''):
            d = self.rfm(venue=bad)
            self.assertEqual(d['total_guests'], 1, bad)
            self.assertIsNone(d['venue'], bad)
        with self.store.conn() as conn:  # таблица цела
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM guests").fetchone()[0], 1)

    def test_output_carries_venue_list_for_ui(self):
        self.add_guest('79001', '2001', [('2026-08-01', 'bolshoy', 1000.0)])
        d = self.rfm()
        keys = [v['key'] for v in d['venues']]
        self.assertEqual(keys, ['bolshoy', 'ligovskiy',
                                'kremenchugskaya', 'varshavskaya'])
        self.assertTrue(all(v['name'] for v in d['venues']))


class TestDiscountAnalyzeFixes(unittest.TestCase):
    """Правки /api/discount-analyze, который обслуживает вкладку «Акции»."""

    def setUp(self):
        from flask import Flask
        from routes.analysis import analysis_bp
        self.app = Flask(__name__)
        self.app.register_blueprint(analysis_bp)
        self.client = self.app.test_client()

    def _rows(self, rows):
        """Фейковый OLAP, отдающий заданные строки."""
        class FakeOlap:
            def connect(self_inner):
                return True

            def disconnect(self_inner):
                return None

            def get_discount_report(self_inner, *a, **kw):
                return {'data': rows}

        return FakeOlap

    def _analyze(self, rows):
        from unittest.mock import patch
        with patch('routes.analysis.OlapReports', self._rows(rows)):
            resp = self.client.post('/api/discount-analyze', json={
                'bar': '', 'date_from': '2026-03-01', 'date_to': '2026-03-31'})
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        return resp.get_json()

    @staticmethod
    def row(date, order, card='2001', dish='Пиво', total=1000.0, disc=100.0,
            store='Лиговский', promo='Акция'):
        return {
            'ItemSaleEventDiscountType': promo,
            'Delivery.CustomerCardNumber': card,
            'Delivery.CustomerName': 'Гость',
            'OrderNum': order,
            'DishName': dish,
            'Store.Name': store,
            'OpenDate.Typed': date,
            'DishDiscountSumInt': total,
            'DiscountSum': disc,
        }

    def test_same_order_number_on_different_days_is_two_checks(self):
        """Ключ чека — дата+бар+номер, иначе номера повторяются между днями."""
        payload = self._analyze([
            self.row('2026-03-01', '5'),
            self.row('2026-03-02', '5'),
        ])
        guest = payload['discounts']['Акция'][0]
        self.assertEqual(guest['orders'], 2)
        self.assertEqual(payload['stores_summary']['Акция'][0]['orders_count'], 2)

    def test_two_checks_in_one_day_are_two_checks_but_one_visit(self):
        payload = self._analyze([
            self.row('2026-03-01', '5', total=1000.0),
            self.row('2026-03-01', '6', total=3000.0),
        ])
        guest = payload['discounts']['Акция'][0]
        self.assertEqual(guest['visits'], 1, 'визит — это день')
        self.assertEqual(guest['orders'], 2, 'чека два')
        self.assertEqual(guest['avg_check'], 2000,
                         'средний чек = выручка / ЧЕКИ, а не / визиты')

    def test_freshest_guest_sorted_first(self):
        """recency 0 не должен уезжать в конец из-за `or 999`."""
        payload = self._analyze([
            self.row('2026-03-31', '1', card='FRESH'),   # recency 0
            self.row('2026-03-20', '2', card='OLD'),     # recency 11
        ])
        cards = [g['card_number'] for g in payload['discounts']['Акция']]
        self.assertEqual(cards[0], 'FRESH')

    def test_all_bucket_dedups_check_across_promos(self):
        """Один чек с двумя акциями — это ОДИН чек в сводке «Все акции».

        Тип скидки — измерение позиции, поэтому такой чек лежит в множествах
        обеих акций. Складывать их количества на клиенте нельзя: чеки удвоятся,
        средний чек упадёт вдвое. Сводку считает сервер в ведре __all__.
        """
        payload = self._analyze([
            self.row('2026-03-01', '7', dish='Пиво', total=600.0, promo='Часы'),
            self.row('2026-03-01', '7', dish='Еда', total=400.0, promo='Гостю'),
        ])
        per_promo = payload['stores_summary']
        self.assertEqual(per_promo['Часы'][0]['orders_count'], 1)
        self.assertEqual(per_promo['Гостю'][0]['orders_count'], 1)
        # Наивное сложение дало бы 2 — сводное ведро знает, что чек один.
        combined = per_promo['__all__'][0]
        self.assertEqual(combined['orders_count'], 1)
        self.assertEqual(combined['sum_with_discount'], 1000.0)
        guest = payload['discounts']['__all__'][0]
        self.assertEqual(guest['orders'], 1)
        self.assertEqual(guest['visits'], 1)
        self.assertEqual(guest['avg_check'], 1000)

    def test_all_bucket_not_offered_as_a_promo_name(self):
        payload = self._analyze([self.row('2026-03-01', '1')])
        self.assertNotIn('__all__', payload['discount_names'])

    def test_all_bucket_carries_no_dishes(self):
        """Позиции в сводном ведре не дублируются — иначе ответ удваивается."""
        payload = self._analyze([
            self.row('2026-03-01', '1', dish='Пиво', promo='Часы'),
            self.row('2026-03-01', '1', dish='Еда', promo='Гостю'),
        ])
        self.assertEqual(payload['discounts']['__all__'][0]['dishes'], [])
        self.assertEqual(len(payload['discounts']['Часы'][0]['dishes']), 1)

    def test_discount_names_respects_requested_range(self):
        """Раньше окно было зашито на 365 дней, а параметры молча игнорировались."""
        from unittest.mock import patch
        seen = {}

        class FakeOlap:
            def connect(self_inner):
                return True

            def disconnect(self_inner):
                return None

            def get_discount_names(self_inner, date_from, date_to):
                seen['from'] = date_from
                seen['to'] = date_to
                return {'data': [{'ItemSaleEventDiscountType': 'Акция'}]}

        with patch('routes.analysis.OlapReports', FakeOlap):
            resp = self.client.get(
                '/api/discount-names?date_from=2026-05-01&date_to=2026-05-31')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(seen['from'], '2026-05-01')
        # Правая граница OLAP эксклюзивная — сдвиг на день.
        self.assertEqual(seen['to'], '2026-06-01')
        self.assertEqual(resp.get_json()['names'], ['Акция'])

    def test_discount_names_rejects_broken_dates(self):
        resp = self.client.get('/api/discount-names?date_from=не-дата')
        self.assertEqual(resp.status_code, 400)

    def test_rfm_analyze_endpoint_is_gone(self):
        """Дубль RFM удалён: каноничный живёт в /api/guests/rfm."""
        resp = self.client.post('/api/rfm-analyze', json={
            'date_from': '2026-03-01', 'date_to': '2026-03-31'})
        self.assertEqual(resp.status_code, 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
