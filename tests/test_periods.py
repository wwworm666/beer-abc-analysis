# -*- coding: utf-8 -*-
"""Тесты стандарта периодов на сервере (core/periods.py, docs/period-standard.md).

Подписи, состояния и правила открытия сверяются с общими примерами
tests/fixtures/period_labels.json — те же примеры проверяет клиентский модуль
(tests/test_period_core.mjs), поэтому сервер и страница пишут период одинаково.
Запуск: py -3 -m pytest tests/test_periods.py -q
"""

import json
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import periods as P  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures',
                       'period_labels.json')
with open(FIXTURE, encoding='utf-8') as fh:
    CASES = json.load(fh)


def d(iso):
    return date.fromisoformat(iso) if iso else None


class TestSharedExamples(unittest.TestCase):
    def test_titles_and_short(self):
        for c in CASES['titles']:
            p = P.from_bounds(d(c['from']), d(c['to']))
            self.assertEqual(p.step, c['step'], c)
            self.assertEqual(p.title(), c['title'], c)
            self.assertEqual(P.period_short(p.step, p.start, p.end), c['short'], c)
            self.assertEqual(P.period_title_compact(p.step, p.start, p.end), c['compact'], c)

    def test_states_sub_and_cutoff(self):
        for c in CASES['states']:
            p = P.from_bounds(d(c['from']), d(c['to']))
            lfd, mx = d(c['last_full_day']), d(c['max_date'])
            self.assertEqual(p.state(lfd, mx), c['state'], c)
            self.assertEqual(P.cutoff_of(p, lfd, mx), c['cutoff'], c)
            self.assertEqual(P.period_sub(p, lfd, mx), c['sub'], c)
            self.assertEqual(P.period_sub_compact(c['sub']), c['sub_compact'], c)

    def test_last_closed(self):
        for c in CASES['last_closed']:
            p = P.last_closed(c['step'], d(c['last_full_day']))
            self.assertEqual((p.start.isoformat(), p.end.isoformat()), (c['from'], c['to']), c)

    def test_last_days(self):
        for c in CASES['last_days']:
            p = P.last_days(c['n'], d(c['last_full_day']))
            self.assertEqual((p.start.isoformat(), p.end.isoformat()), (c['from'], c['to']), c)
            self.assertEqual(p.days, c['n'], 'ровно N дат, не N + 1')


class TestModel(unittest.TestCase):
    def test_steps_by_bounds(self):
        self.assertEqual(P.detect_step(d('2026-10-01'), d('2026-10-31')), 'month')
        self.assertEqual(P.detect_step(d('2026-10-26'), d('2026-11-01')), 'week')
        self.assertEqual(P.detect_step(d('2026-10-27'), d('2026-11-01')), 'custom')
        self.assertEqual(P.from_bounds(d('2026-10-31'), d('2026-10-01')).step, 'month',
                         'порядок дат нормализуется')

    def test_shift(self):
        self.assertEqual(P.shift(P.period_for('month', d('2026-01-31')), 1).start, d('2026-02-01'))
        self.assertEqual(P.shift(P.period_for('month', d('2026-12-14')), 1).start,
                         d('2027-01-01'), 'через границу года')
        self.assertEqual(P.shift(P.period_for('week', d('2026-12-30')), 1).start, d('2027-01-04'))
        custom = P.from_bounds(d('2026-10-12'), d('2026-10-25'))
        self.assertEqual((P.shift(custom, -1).start, P.shift(custom, -1).end),
                         (d('2026-09-28'), d('2026-10-11')), 'свой период — на свою длину')

    def test_no_quarters(self):
        """Кварталов нет (решение владельца 2026-11-01): 1 июля – 30 сентября — свой период."""
        self.assertNotIn('quarter', P.STEPS)
        self.assertEqual(P.detect_step(d('2026-07-01'), d('2026-09-30')), 'custom')
        self.assertEqual(P.period_for('quarter', d('2026-08-15')).step, 'day',
                         'неизвестный шаг — день, а не квартал')

    def test_month_of(self):
        for c in CASES['month_of']:
            p = P.from_bounds(d(c['from']), d(c['to']))
            self.assertEqual(P.month_of(p).start.isoformat(), c['month'], c)

    def test_reversed_dates_are_an_error(self):
        with self.assertRaises(P.PeriodError):
            P.parse_period({'date_from': '2026-10-31', 'date_to': '2026-10-01'})
        self.assertEqual(P.parse_period({'date_from': '2026-10-01', 'date_to': '2026-10-31'}).step,
                         'month')

    def test_key_matches_weeks_api(self):
        self.assertEqual(P.period_for('week', d('2026-10-28')).key, '2026-10-26_2026-11-01')

    def test_to_meta(self):
        meta = P.period_for('month', d('2026-10-15')).to_meta(d('2026-10-29'), d('2026-10-29'))
        self.assertEqual(meta, {
            'key': '2026-10-01_2026-10-31', 'step': 'month', 'date_from': '2026-10-01',
            'date_to': '2026-10-31', 'title': 'Октябрь 2026', 'sub': 'идёт, по 29.10',
            'short': 'окт 26', 'state': 'partial', 'cutoff': '2026-10-29'})


class TestParse(unittest.TestCase):
    def test_dates_and_aliases(self):
        default = P.period_for('week', d('2026-10-19'))
        self.assertIs(P.parse_period({}, default), default)
        p = P.parse_period({'date_from': '2026-10-01', 'date_to': '2026-10-31'})
        self.assertEqual((p.step, p.start, p.end), ('month', d('2026-10-01'), d('2026-10-31')))
        p = P.parse_period({'key': '2026-10-26_2026-11-01'})
        self.assertEqual(p.step, 'week', 'ключ /api/weeks — синоним')

    def test_bad_input_is_period_error(self):
        for args in ({'date_from': '2026-10-01'}, {'date_from': '01.10.2026', 'date_to': '2026-10-31'},
                     {'key': '2026-10-01'}, {'date_from': '2026-02-30', 'date_to': '2026-03-01'}):
            with self.assertRaises(P.PeriodError, msg=args):
                P.parse_period(args)


class TestPageConfig(unittest.TestCase):
    def test_live_and_nightly(self):
        today = d('2026-11-01')
        self.assertEqual(P.page_config(live=True, today=today), {
            'today': '2026-11-01', 'last_full_day': '2026-10-31', 'max_date': '2026-11-01',
            'data_start': None})
        cfg = P.page_config(live=False, last_full_day=d('2026-10-29'), today=today,
                            data_start=d('2017-12-18'))
        self.assertEqual((cfg['last_full_day'], cfg['max_date'], cfg['data_start']),
                         ('2026-10-29', '2026-10-29', '2017-12-18'))
        cfg = P.page_config(live=False, last_full_day=d('2026-11-01'), today=today)
        self.assertEqual(cfg['last_full_day'], '2026-10-31', 'неполный сегодняшний день не в счёт')

    def test_business_day_rollover_at_six(self):
        """В 03:00 МСК 2 ноября ещё идут рабочие сутки 1 ноября."""
        night = datetime(2026, 11, 2, 3, 0, tzinfo=timezone(timedelta(hours=3)))
        with mock.patch('core.msk_time.now', return_value=night):
            self.assertEqual(P.page_config()['today'], '2026-11-01')
        morning = datetime(2026, 11, 2, 6, 0, tzinfo=timezone(timedelta(hours=3)))
        with mock.patch('core.msk_time.now', return_value=morning):
            self.assertEqual(P.page_config()['today'], '2026-11-02')


if __name__ == '__main__':
    unittest.main()
