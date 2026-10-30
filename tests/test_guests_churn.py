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

С 2026-10-30 — ущерб от оттока, «Стали ходить реже» (своя витрина SLOWING) и подсказка к
порогу (паузы перед повторными визитами); ожидаемые числа сверены ручным расчётом.
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
        self.assertEqual(p['newbie_matures_on'], '2026-04-30', '31.03 + 30')

    def test_march_leavers(self):
        buckets = {b['segment']: b for b in self.churn(30)['leavers']['buckets']}
        self.assertEqual(self.churn(30)['leavers']['total'], 2)
        self.assertEqual((buckets['1']['count'], buckets['1']['avg_ltv']), (1, 1000), 'B')
        self.assertEqual((buckets['2-3']['count'], buckets['2-3']['avg_ltv']), (1, 3000), 'F')
        self.assertEqual((buckets['4-8']['count'], buckets['4-8']['avg_ltv']), (0, None))
        self.assertEqual(buckets['1']['share_pct'], 50.0)

    def test_march_damage(self):
        """Ущерб = выручка ушедших за год по их последний визит; в месяц — / 12."""
        d = self.churn(30)
        p, leavers = d['period'], d['leavers']
        self.assertEqual((p['damage_year'], p['damage_month']), (4000, 333),
                         'B — 1 000 ₽, F — 3 000 ₽; 4 000 / 12 = 333,3')
        self.assertEqual((leavers['damage_year'], leavers['damage_month']), (4000, 333),
                         'итог «Кто уходит» = плитка')
        self.assertEqual([b['damage_month'] for b in leavers['buckets']], [83, 250, 0, 0],
                         '1 000 / 12 и 3 000 / 12; пустые группы — 0 ₽')

    def test_return_gaps(self):
        """Паузы перед повторными визитами за год по 31.03: 10, 14, 15, 23, 45, 78 дней."""
        gaps = self.churn(30)['return_gaps']
        self.assertEqual((gaps['window_from'], gaps['window_to'], gaps['returns']),
                         ('2025-04-01', '2026-03-31', 6))
        self.assertEqual([(r['days'], r['pct']) for r in gaps['later_than']],
                         [(30, 33.3), (60, 16.7), (90, 0.0), (180, 0.0)],
                         'длиннее 30 — E (45) и C (78); длиннее 60 — только C')
        self.assertEqual([(p['pct'], p['days']) for p in gaps['percentiles']],
                         [(50, 15), (90, 78)], 'ближайший ранг: 3-е и 6-е из 6')
        self.assertEqual(self.churn(90)['return_gaps'], gaps, 'от порога не зависит')

    def test_march_x60_differs_and_is_not_mature(self):
        p = self.churn(60)['period']
        self.assertEqual((p['start_alive'], p['died'], p['end_alive']), (5, 2, 5),
                         'при 60 днях живы на начало ещё C и E, ушли E и F')
        self.assertEqual(p['churn_pct'], 40.0)
        self.assertIsNone(p['newbie_no_return_pct'], '31.03 + 60 = 30.05 — позже 20.05')
        self.assertEqual(p['newbie_matures_on'], '2026-05-30')

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
        self.assertEqual(may['newbie_matures_on'], '2026-06-30')
        june_full = self.churn(30, 'month', '2026-06-15')
        june = june_full['period']
        self.assertEqual(june['state'], 'future')
        for key in ('start_alive', 'died', 'new', 'end_alive', 'churn_pct', 'asof',
                    'damage_month', 'damage_year', 'slowing', 'slowing_base', 'slowing_pct'):
            self.assertIsNone(june[key], key + ': у будущего периода нет чисел, а не нули')
        self.assertIsNone(june_full['return_gaps'], 'у будущего периода нет и подсказки')

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
        # И для закрытого месяца, и для неполного (май, срез 20.05): дата среза одна на все
        # вкладки — последний полный день данных (2026-10-29).
        for anchor in ('2026-03-15', '2026-05-15'):
            period, meta = self.ctx('month', anchor)
            active = {s['segment']: s['count']
                      for s in ga.activity(self.store, period, meta)['segments']}['active']
            p = self.churn(30, 'month', anchor)['period']
            self.assertEqual(p['asof'], meta['asof'], anchor)
            self.assertEqual(p['end_alive'], active, anchor + ': при X = 30 живые = Активные')
            growth = ga.base_growth(self.store, period, meta)
            self.assertEqual(p['new'], growth['period']['first_orders'],
                             anchor + ': «Новые гости» на «Оттоке» и «Росте базы» — одно число')

    def test_base_size_and_ltv_guests_are_on_the_cut_off_date(self):
        period, meta = self.ctx()
        base = ga.base_growth(self.store, period, meta)['lifetime']['base_size']
        self.assertEqual(base, 7, 'H пришёл 20.05 — после среза марта')
        self.assertEqual(base, ga.ltv(self.store, period, meta)['lifetime']['guests'])


class TestRetentionComplement(ChurnBase):
    """«Не вернулись после первого визита» = 100% − «Возвраты через X дней» (2026-10-29).

    Одно окно и одно правило созревания: где «Возвраты» показывают прочерк, там его
    показывает и «Отток», а там, где обе доли есть, в сумме они дают 100%.
    """

    def test_both_tabs_agree_for_every_window(self):
        for anchor in ('2026-03-15', '2026-05-15'):
            period, meta = self.ctx('month', anchor)
            cohorts = {c['cohort']: c
                       for c in ga.cohort_retention(self.store, period, meta)['cohorts']}
            for x in ga.CHURN_DEAD_DAYS_CHOICES:
                for row in self.churn(x, 'month', anchor)['series']:
                    cohort = cohorts.get(row['p_start'][:7])
                    if cohort is None:
                        self.assertFalse(row['new'], (anchor, x, row['p_start']))
                        continue
                    back = cohort['returned_pct'][str(x)]
                    gone = row['newbie_no_return_pct']
                    self.assertEqual(back is None, gone is None, (anchor, x, row['p_start']))
                    if back is not None:
                        self.assertAlmostEqual(back + gone, 100.0, delta=0.1,
                                               msg=(anchor, x, row['p_start']))


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
        'R30': _visits(['2026-03-01', '2026-03-31']),   # возврат через 30 дней
        'R31': _visits(['2026-03-01', '2026-04-01']),   # возврат через 31 день
        'S30': _visits(['2026-01-29']),                 # на 28.02 пауза 30
        'S31': _visits(['2026-01-28']),                 # на 28.02 пауза 31
        'RG': _visits(['2025-03-01', '2025-04-01']),    # возврат в первый день окна пауз
        'RH': _visits(['2025-03-02', '2025-03-31']),    # возврат за день до окна
        'Z': _visits(['2026-06-30']),
    }

    def test_return_gap_window_and_strict_threshold(self):
        """Окно пауз — 365 дней по срез; «позже порога» — строго больше: 30 при X = 30 — вовремя."""
        gaps = self.churn(30)['return_gaps']
        self.assertEqual(gaps['window_from'], '2025-04-01')
        self.assertEqual(gaps['returns'], 2, 'R30 (30 дней) и RG (31); RH — до окна, R31 — после среза')
        self.assertEqual([(r['days'], r['pct']) for r in gaps['later_than']][:2],
                         [(30, 50.0), (60, 0.0)])
        self.assertEqual([p['days'] for p in gaps['percentiles']], [30, 31])

    def test_newbie_window_equals_retention_window(self):
        """Окно «не вернулись» — X дней, как «Возвраты через X дней» (решение 2026-10-29)."""
        p = self.churn(30, anchor='2026-03-15')['period']
        self.assertEqual((p['new'], p['newbie_no_return']), (2, 1),
                         'через 30 дней — вернулся, через 31 — уже нет')
        period, meta = self.ctx()
        march = {c['cohort']: c for c in ga.cohort_retention(self.store, period, meta)['cohorts']}
        self.assertEqual(march['2026-03']['returned_pct']['30'] + p['newbie_no_return_pct'], 100.0)

    def test_start_gap_x_is_alive_x_plus_one_is_dead(self):
        p = self.churn(30)['period']
        self.assertEqual((p['start_alive'], p['died']), (1, 1), 'жив только S30, и он ушёл')


class TestDamageWindow(ChurnBase):
    """Окно ущерба — 365 дней по последний визит ушедшего, а не по дату среза."""
    GUESTS = {
        'L': _visits(['2025-03-01', '2025-03-02', '2026-03-01']),
        'Z': _visits(['2026-05-20']),
    }

    def test_window_ends_at_last_visit(self):
        p = self.churn(30, anchor='2026-04-15')['period']
        self.assertEqual(p['died'], 1, 'L жив на 31.03 (пауза 30) и мёртв на 30.04')
        self.assertEqual(p['damage_year'], 2500,
                         '02.03.2025 (ровно за 364 дня) + 01.03.2026; 01.03.2025 — вне окна; '
                         'окно по дату среза дало бы 1 500')
        self.assertEqual(p['damage_month'], 208, '2 500 / 12 = 208,3')


# «Стали ходить реже»: срез 31.03.2026 — последние 90 дней 01.01–31.03, прошлые 03.10–31.12.
SLOWING = {
    'S1': _visits(['2025-10-10', '2025-11-01', '2025-11-20', '2025-12-15',
                   '2026-01-20', '2026-03-25']),                    # 4 -> 2: реже, пауза 6
    'S2': _visits(['2025-10-10', '2025-11-01', '2025-11-20', '2025-12-15',
                   '2026-01-10', '2026-02-10', '2026-03-20']),      # 4 -> 3: не вдвое
    'S3': _visits(['2025-10-20', '2025-11-20', '2026-03-01']),      # 2 -> 1: ходил реже раза в месяц
    'S4': _visits(['2025-10-10', '2025-11-10', '2025-12-10']),      # 3 -> 0: перестал ходить
    'S5': _visits(['2025-10-05', '2025-11-05', '2025-12-05', '2026-01-15']),  # 3 -> 1, пауза 75
    'BND': _visits(['2025-10-02', '2025-10-03', '2025-11-15', '2025-12-31',
                    '2026-01-01']),                                 # края окон: 3 -> 1, пауза 89
    'BND2': _visits(['2025-10-02', '2025-10-03', '2025-12-31', '2026-01-01']),  # 02.10 вне окна: 2 -> 1
    'Z': _visits(['2026-05-20']),
}


class TestSlowing(ChurnBase):
    GUESTS = SLOWING

    def test_counts_by_threshold(self):
        expected = {30: (1, 2, 50.0), 60: (1, 2, 50.0), 90: (3, 4, 75.0), 180: (3, 4, 75.0)}
        for dead_days, counts in expected.items():
            p = self.churn(dead_days)['period']
            self.assertEqual((p['slowing'], p['slowing_base'], p['slowing_pct']), counts,
                             dead_days)

    def test_window_edges(self):
        """03.10 и 31.12 — прошлое окно, 01.01 — последнее, 02.10 — вне окон (BND2 не в базе)."""
        period, meta = self.ctx()
        names = [g['name'] for g in ga.churn_guests(self.store, period, meta, 'slowing', 90)['guests']]
        self.assertIn('BND', names)
        self.assertNotIn('BND2', names)

    def test_list_matches_counter_and_is_sorted_by_revenue(self):
        period, meta = self.ctx()
        for dead_days in ga.CHURN_DEAD_DAYS_CHOICES:
            listed = ga.churn_guests(self.store, period, meta, 'slowing', dead_days)
            self.assertEqual(listed['total'], self.churn(dead_days)['period']['slowing'],
                             'список и плитка — одно правило')
        listed = ga.churn_guests(self.store, period, meta, 'slowing', 90)
        self.assertEqual((listed['asof'], listed['dead_days']), ('2026-03-31', 90))
        rows = [(g['name'], g['visits_prev'], g['visits_recent'], g['recency_days'],
                 g['last_visit'], g['revenue_12m']) for g in listed['guests']]
        self.assertEqual(rows, [
            ('S1', 4, 2, 6, '2026-03-25', 6500),
            ('BND', 3, 1, 89, '2026-01-01', 5000),
            ('S5', 3, 1, 75, '2026-01-15', 4000),
        ], 'по убыванию выручки за 12 мес; 02.10.2025 у BND — в окне выручки, но не в окне визитов')
        self.assertTrue(listed['guests'][0]['phone'], 'телефон для обзвона')

    def test_future_period_list_is_empty(self):
        period, meta = self.ctx(anchor='2026-06-15')
        listed = ga.churn_guests(self.store, period, meta, 'slowing', 30)
        self.assertEqual((listed['asof'], listed['total'], listed['guests']), (None, 0, []))


class TestSlowingVenue(ChurnBase):
    """Бар как отдельное заведение: в сети гость стал ходить реже, в каждом баре — нет."""
    GUESTS = {
        'SV': [(d, 'bolshoy', 1000.0) for d in ('2025-10-10', '2025-11-01', '2025-11-20',
                                                 '2025-12-15')] +
              [(d, 'ligovskiy', 1000.0) for d in ('2026-01-20', '2026-03-25')],
        'Z': [('2026-05-20', 'bolshoy', 1000.0)],
    }

    def test_bar_rules(self):
        self.assertEqual(self.churn(30)['period']['slowing'], 1, 'в сети 4 -> 2')
        self.assertEqual(self.churn(30, venue='bolshoy')['period']['slowing'], 0,
                         'в Большом 4 -> 0: перестал ходить, а не стал реже')
        self.assertEqual(self.churn(30, venue='ligovskiy')['period']['slowing'], 0,
                         'в Лиговском раньше не ходил')
        period, meta = self.ctx(venue='ligovskiy')
        self.assertEqual(
            ga.churn_guests(self.store, period, meta, 'slowing', 30, 'ligovskiy')['total'], 0)


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
        self.assertIsNone(d['return_gaps'])
        period, meta = self.ctx()
        for group in ga.CHURN_GUEST_GROUPS:
            self.assertFalse(ga.churn_guests(self.store, period, meta, group)['total'], group)


class TestLtvOnDate(ChurnBase):
    """LTV на дату (§8): суммы по чекам не позже среза, LTV = средний чек × чеков на гостя."""

    def ltv(self, anchor='2026-03-15', period_type='month', venue=None, periods=None):
        period, meta = self.ctx(period_type, anchor, venue)
        return ga.ltv(self.store, period, meta, venue, periods)

    def test_march_numbers_and_structure(self):
        d = self.ltv()
        self.assertEqual(d['asof'], '2026-03-31')
        life = d['lifetime']
        self.assertEqual((life['guests'], life['revenue'], life['avg_ltv']), (7, 15500, 2214),
                         'A-G; H пришёл 20.05 — после среза')
        self.assertEqual((life['checks'], life['avg_check'], life['checks_per_guest']),
                         (13, 1192, 1.86))
        # Произведение показанных сомножителей расходится с LTV на рубли — оговорка в UI.
        self.assertEqual(round(life['avg_check'] * life['checks_per_guest']), 2217)

    def test_series_and_decomposition(self):
        rows = {r['p_start'][:7]: r for r in self.ltv()['series']}
        feb, mar = rows['2026-02'], rows['2026-03']
        self.assertEqual((feb['ltv'], feb['avg_check'], feb['checks_per_guest']), (1600, 1000, 1.6))
        self.assertEqual((mar['delta'], mar['check_effect'], mar['frequency_effect']),
                         (614, 332, 282), 'чек вырос с 1 000 до 1 192, частота — с 1,60 до 1,86')
        self.assertEqual((feb['delta'], feb['check_effect'], feb['frequency_effect']),
                         (-400, 0, -400), 'новые A и B разбавили частоту')
        self.assertIsNone(rows['2025-12']['delta'], 'у первой точки ряда нет предыдущей')
        for row in rows.values():
            if row['delta'] is not None:
                self.assertEqual(row['check_effect'] + row['frequency_effect'], row['delta'])

    def test_past_period_ignores_later_receipts(self):
        before = self.ltv()
        with self.store.conn() as conn:
            conn.execute("INSERT INTO receipts (open_date, store, order_num, guest_id, revenue, "
                         "discount, full_sum) VALUES ('2026-04-10', 'bolshoy', '9', '79000', "
                         "5000, 0, 5000)")
            conn.commit()
        after = self.ltv()
        self.assertEqual(after['lifetime'], before['lifetime'],
                         'чек 10.04 не должен менять LTV на 31.03')
        self.assertEqual(after['by_venue'], before['by_venue'])

    def test_partial_and_future_rows(self):
        rows = {r['p_start'][:7]: r for r in self.ltv('2026-06-15')['series']}
        self.assertEqual((rows['2026-05']['state'], rows['2026-05']['asof']),
                         ('partial', '2026-05-20'))
        self.assertEqual(rows['2026-06']['state'], 'future')
        self.assertIsNone(rows['2026-06']['ltv'])
        self.assertEqual(self.ltv('2026-06-15')['asof'], '2026-05-20',
                         'будущий период: LTV на последний полный день данных')

    def test_bar_and_summary(self):
        net, bol = self.ltv(), self.ltv(venue='bolshoy')
        self.assertEqual(bol['lifetime'], net['lifetime'], 'все чеки витрины — в Большом')
        self.assertEqual(bol['by_venue'], [], 'сравнение баров — только для всей сети')
        self.assertTrue(net['by_venue'])
        period, meta = self.ctx()
        summary = ga.summary(self.store, period, meta)
        self.assertEqual((summary['avg_ltv'], summary['avg_ltv_asof']), (2214, '2026-03-31'))


class TestCohortTotalsOnDate(ChurnBase):
    """§2 и §6 по дату среза (2026-10-27): чек после среза не меняет прошлый период."""

    def snapshot(self, anchor='2026-03-15'):
        period, meta = self.ctx('month', anchor)
        life = {c['cohort']: c
                for c in ga.lifecycle_cohorts(self.store, period, meta)['cohorts']}
        rev = {c['cohort']: c
               for c in ga.cohort_revenue(self.store, period, meta)['cohorts']}
        return life, rev

    def test_later_receipt_does_not_change_past_cohorts(self):
        life, rev = self.snapshot()
        self.assertEqual(life['2026-02']['order2_pct'], 50.0, 'к 31.03 два чека у A, один у B')
        self.assertEqual((rev['2026-02']['revenue'], rev['2026-02']['ltv']), (3500, 1750))
        with self.store.conn() as conn:   # B возвращается 10.04 — после среза марта
            conn.execute("INSERT INTO receipts (open_date, store, order_num, guest_id, revenue, "
                         "discount, full_sum) VALUES ('2026-04-10', 'bolshoy', '9', '79001', "
                         "5000, 0, 5000)")
            conn.commit()
        life, rev = self.snapshot()
        self.assertEqual(life['2026-02']['order2_pct'], 50.0)
        self.assertEqual(rev['2026-02']['revenue'], 3500)
        life_may, rev_may = self.snapshot('2026-05-15')
        self.assertEqual(life_may['2026-02']['order2_pct'], 100.0, 'срез мая чек 10.04 видит')
        self.assertEqual(rev_may['2026-02']['revenue'], 8500)


class TestLtvEmptyStore(ChurnBase):
    GUESTS = {}

    def test_empty_store(self):
        period, meta = self.ctx()
        d = ga.ltv(self.store, period, meta)
        self.assertEqual((d['asof'], d['series'], d['lifetime']['guests']), (None, [], 0))
        self.assertIsNone(d['lifetime']['avg_check'])


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


class RouteMixin:
    """Flask test client с маршрутами «Маркетинга» на временной витрине теста (кэш очищен)."""

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


class TestChurnRoute(RouteMixin, ChurnBase):
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

    def test_ltv_route_reads_periods(self):
        response = self.client.get('/api/guests/ltv', query_string={
            'period_type': 'month', 'anchor': '2026-03-15', 'periods': '3'})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        series = response.get_json()['data']['series']
        self.assertEqual([r['p_start'] for r in series],
                         ['2026-01-01', '2026-02-01', '2026-03-01'])


class TestChurnGuests(ChurnBase):
    """Гости плиток поимённо (кликабельные плитки, 2026-10-30): список = счётчик плитки."""

    def guests(self, group, dead_days=30, anchor='2026-03-15', period_type='month', bucket=None):
        period, meta = self.ctx(period_type, anchor)
        return ga.churn_guests(self.store, period, meta, group, dead_days, bucket=bucket)

    def test_every_list_matches_its_tile(self):
        for anchor, period_type in (('2026-03-15', 'month'), ('2026-02-01', 'quarter'),
                                    ('2026-05-15', 'month'), ('2026-01-15', 'month')):
            for dead_days in ga.CHURN_DEAD_DAYS_CHOICES:
                d = self.churn(dead_days, period_type, anchor)
                p = d['period']
                tiles = {'left': p['died'] + p['new_died'], 'reactivated': p['reactivated'],
                         'new': p['new'], 'newbie_no_return': p['newbie_no_return'],
                         'slowing': p['slowing']}
                for group, count in tiles.items():
                    got = self.guests(group, dead_days, anchor, period_type)['total']
                    self.assertEqual(got, count, (anchor, period_type, dead_days, group))
                for b in d['leavers']['buckets']:
                    got = self.guests('left', dead_days, anchor, period_type, b['segment'])['total']
                    self.assertEqual(got, b['count'], (anchor, dead_days, b['segment']))

    def test_march_rows(self):
        left = self.guests('left')['guests']
        self.assertEqual([(g['name'], g['visits_total'], g['damage_month'], g['ltv']) for g in left],
                         [('F', 3, 250, 3000), ('B', 1, 83, 1000)], 'по ущербу в месяц')
        self.assertEqual([g['name'] for g in self.guests('left', bucket='1')['guests']], ['B'])
        back = self.guests('reactivated')['guests']
        self.assertEqual([(g['name'], g['pause_days'], g['visits_period'], g['revenue_period'])
                          for g in back], [('C', 78, 1, 1500)], '01.01 → 20.03 — пауза 78 дней')
        new = self.guests('new')['guests']
        self.assertEqual([(g['name'], g['first_visit'], g['revenue_period']) for g in new],
                         [('D', '2026-03-10', 3000), ('G', '2026-03-28', 1500)], 'по выручке')
        self.assertEqual([g['name'] for g in self.guests('newbie_no_return')['guests']], ['G'])

    def test_newbie_list_waits_for_maturity(self):
        d = self.guests('newbie_no_return', 60)
        self.assertEqual((d['mature'], d['total'], d['guests'], d['matures_on']),
                         (False, None, [], '2026-05-30'), '31.03 + 60 — позже 20.05')

    def test_params(self):
        self.assertEqual(ga.parse_churn_group('LEFT'), 'left')
        for bad in (None, '', 'died', 'all'):
            with self.assertRaises(ValueError):
                ga.parse_churn_group(bad)
        self.assertEqual(ga.parse_leaver_bucket('9 '), '9+', 'плюс в адресе приходит пробелом')
        self.assertIsNone(ga.parse_leaver_bucket(''))
        with self.assertRaises(ValueError):
            ga.parse_leaver_bucket('10+')
        with self.assertRaises(ValueError):
            self.guests('new', bucket='1')


class TestChurnGuestsRoute(RouteMixin, ChurnBase):
    GUESTS = SLOWING

    def get(self, **params):
        query = dict({'period_type': 'month', 'anchor': '2026-03-15'}, **params)
        return self.client.get('/api/guests/churn-guests', query_string=query)

    def test_json_limit_and_counter(self):
        response = self.get(group='slowing', dead_days='90', limit='2')
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        d = response.get_json()['data']
        self.assertEqual((d['group'], d['total'], d['returned'], d['limit'], d['dead_days']),
                         ('slowing', 3, 2, 2, 90))
        self.assertEqual([g['name'] for g in d['guests']], ['S1', 'BND'], 'самые ценные сверху')
        churn = self.client.get('/api/guests/churn', query_string={
            'period_type': 'month', 'anchor': '2026-03-15', 'dead_days': '90'}).get_json()
        self.assertEqual(churn['data']['period']['slowing'], d['total'], 'плитка = список')

    def test_default_threshold_and_full_list(self):
        d = self.get(group='slowing').get_json()['data']
        self.assertEqual((d['dead_days'], d['total'], d['returned'], d['limit']), (30, 1, 1, None))

    def test_bucket_with_plus(self):
        d = self.get(group='left', dead_days='90', bucket='9+').get_json()['data']
        self.assertEqual((d['bucket'], d['total']), ('9+', 0))

    def test_csv_is_whole_list(self):
        response = self.get(group='slowing', dead_days='90', limit='1', export='csv')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.mimetype.startswith('text/csv'))
        self.assertIn('churn_slowing_2026-03-31_90d.csv',
                      response.headers['Content-Disposition'])
        body = response.get_data().decode('utf-8-sig').strip().splitlines()
        self.assertEqual(body[0].split(';')[0], 'Телефон')
        self.assertEqual(len(body), 1 + 3, 'выгрузка — весь список, limit не действует')

    def test_bad_params_are_400(self):
        for params, word in (({'group': 'slowing', 'limit': '0'}, 'limit'),
                             ({'group': 'slowing', 'limit': '1.5'}, 'limit'),
                             ({}, 'group'), ({'group': 'died'}, 'group'),
                             ({'group': 'left', 'bucket': '10+'}, 'bucket'),
                             ({'group': 'new', 'bucket': '1'}, 'bucket')):
            response = self.get(**params)
            self.assertEqual(response.status_code, 400, params)
            self.assertIn(word, response.get_json()['error'], params)


if __name__ == '__main__':
    unittest.main()
