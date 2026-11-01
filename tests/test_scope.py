"""Общий выбор бара и периода на весь сайт (core/scope.py, core/venues_config.bar_key).

План единого виджета — docs/planning/period-widget-rollout.md; решения владельца 2026-11-01:
период помнится час, у каждого пользователя свой (Р1); без выбора — текущий период шага
страницы (Р2); помесячная страница показывает месяц выбранного (Р3) и пишет это в полосе.
"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template_string  # noqa: E402

from core import periods, scope  # noqa: E402
from core.venues_config import ALL_BARS_LABEL, SITE_BARS, bar_key  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Воскресенье 1 ноября 2026, живые данные iiko: сегодня — 01.11, последний полный — 31.10.
CLOCK = periods.page_config(live=True, today=date(2026, 11, 1))


class TestBars(unittest.TestCase):
    def test_every_spelling_maps_to_key_and_back(self):
        for bar in SITE_BARS:
            for spelling in [bar['key'], bar['name'], bar['iiko_name'], bar['bar_id']] + bar['aliases']:
                self.assertEqual(bar_key(spelling), bar['key'], spelling)
                self.assertEqual(bar_key('  ' + spelling.upper() + ' '), bar['key'], 'регистр и пробелы')

    def test_kpi_spelling_of_bolshoy(self):
        self.assertEqual(bar_key('Большой пр В.О.'), 'bolshoy', 'написание целей KPI')

    def test_all_bars_spellings(self):
        for raw in ['', 'all', 'Общая', 'Все бары', 'вся сеть', 'Все заведения', 'Все точки', None]:
            self.assertEqual(bar_key(raw), '', raw)
        self.assertIsNone(bar_key('bar9'))
        self.assertEqual(ALL_BARS_LABEL, 'Все бары', 'одна подпись всей сети (Р6)')


class TestCookies(unittest.TestCase):
    def test_owned_by_this_user_only(self):
        cookies = {scope.COOKIE_PERIOD: '7:2026-10-01_2026-10-31', scope.COOKIE_BAR: '7:ligovskiy'}
        self.assertEqual(scope.read_period(cookies, 7).key, '2026-10-01_2026-10-31')
        self.assertEqual(scope.read_bar(cookies, 7), 'ligovskiy')
        self.assertIsNone(scope.read_period(cookies, 8), 'чужой выбор на общем компьютере не подхватывается')
        self.assertIsNone(scope.read_bar(cookies, 8))
        self.assertIsNone(scope.read_period(cookies, None))

    def test_value_encoded_by_page(self):
        """Страница пишет encodeURIComponent: двоеточие приходит как %3A."""
        cookies = {scope.COOKIE_PERIOD: '7%3A2026-10-01_2026-10-31', scope.COOKIE_BAR: '7%3Aall'}
        self.assertEqual(scope.read_period(cookies, 7).key, '2026-10-01_2026-10-31')
        self.assertEqual(scope.read_bar(cookies, 7), '', 'вся сеть — явным all')

    def test_garbage_is_no_choice(self):
        for raw in ['7:', '7:2026-10-31_2026-10-01', '7:вчера', 'ligovskiy', '7:bar9']:
            cookies = {scope.COOKIE_PERIOD: raw, scope.COOKIE_BAR: raw}
            self.assertIsNone(scope.read_period(cookies, 7), raw)
            self.assertIsNone(scope.read_bar(cookies, 7), raw)

    def test_period_remembered_for_an_hour(self):
        self.assertEqual(scope.PERIOD_TTL_SECONDS, 3600, 'ответ владельца Р1')


class TestResolve(unittest.TestCase):
    def test_default_is_current_period_of_page_step(self):
        """Без выбора — текущий период шага страницы (Р2)."""
        week = scope.resolve({}, {}, 7, step='week', clock=CLOCK)
        self.assertEqual(week['period'].key, '2026-10-26_2026-11-01', 'идущая неделя')
        self.assertIsNone(week['chosen'])
        self.assertEqual(scope.resolve({}, {}, 7, step='month', clock=CLOCK)['period'].key,
                         '2026-11-01_2026-11-30')
        self.assertEqual(scope.resolve({}, {}, 7, step='day', clock=CLOCK)['period'].key,
                         '2026-11-01_2026-11-01')
        self.assertEqual(scope.resolve({}, {}, 7, step='last30', clock=CLOCK)['period'].key,
                         '2026-10-02_2026-10-31', 'ABC/XYZ — 30 полных дней')

    def test_nightly_data_current_month_by_last_full_day(self):
        """Витрина с ночной загрузкой: 1-го числа «текущий» месяц — ещё прошлый, а не пустой."""
        clock = periods.page_config(live=False, last_full_day=date(2026, 10, 31), today=date(2026, 11, 1))
        self.assertEqual(scope.page_default('month', clock).key, '2026-10-01_2026-10-31')

    def test_link_beats_choice_beats_default(self):
        cookies = {scope.COOKIE_PERIOD: '7:2026-09-01_2026-09-30', scope.COOKIE_BAR: '7:bolshoy'}
        res = scope.resolve({}, cookies, 7, clock=CLOCK)
        self.assertEqual((res['period'].key, res['chosen_source'], res['bar']),
                         ('2026-09-01_2026-09-30', 'choice', 'bolshoy'))
        args = {'date_from': '2026-10-01', 'date_to': '2026-10-31', 'bar': 'ligovskiy'}
        res = scope.resolve(args, cookies, 7, clock=CLOCK)
        self.assertEqual((res['period'].key, res['chosen_source'], res['bar'], res['bar_source']),
                         ('2026-10-01_2026-10-31', 'url', 'ligovskiy', 'url'))

    def test_bad_link_falls_back_with_note(self):
        res = scope.resolve({'date_from': '2026-10-31', 'date_to': '2026-10-01'}, {}, 7, clock=CLOCK)
        self.assertIsNone(res['chosen'])
        self.assertIn('Период из ссылки не распознан', res['note'])
        self.assertEqual(res['period'].key, '2026-10-26_2026-11-01')
        res = scope.resolve({'date_from': '2026-12-01', 'date_to': '2026-12-31'}, {}, 7, clock=CLOCK)
        self.assertIn('ещё не начался', res['note'])
        planning = scope.resolve({'date_from': '2026-12-01', 'date_to': '2026-12-31'}, {}, 7,
                                 clock=CLOCK, allow_future=True)
        self.assertEqual(planning['period'].key, '2026-12-01_2026-12-31', 'планирование — вперёд можно')

    def test_monthly_page_shows_month_of_choice(self):
        """Р3: неделя 27 окт – 2 ноя -> октябрь (там 5 дней из 7); общий выбор не меняется."""
        cookies = {scope.COOKIE_PERIOD: '7:2026-10-26_2026-11-01'}
        res = scope.resolve({}, cookies, 7, mode='monthly', step='month', clock=CLOCK)
        self.assertEqual(res['period'].key, '2026-10-01_2026-10-31')
        self.assertEqual(res['chosen'].key, '2026-10-26_2026-11-01', 'выбор остаётся неделей')
        self.assertEqual(res['note'], 'по месяцам — показан октябрь 2026')
        year = scope.resolve({}, {scope.COOKIE_PERIOD: '7:2025-01-01_2025-12-31'}, 7, mode='monthly',
                             step='month', clock=CLOCK)
        self.assertEqual(year['period'].key, '2025-12-01_2025-12-31', 'длинный период — последний месяц')

    def test_now_page_has_no_period(self):
        res = scope.resolve({}, {scope.COOKIE_PERIOD: '7:2026-10-01_2026-10-31'}, 7, mode='now', clock=CLOCK)
        self.assertIsNone(res['period'])


class TestStrip(unittest.TestCase):
    def test_labels_for_first_paint(self):
        strip = scope.build_strip(7, {}, {scope.COOKIE_BAR: '7:ligovskiy'}, step='week')
        self.assertEqual((strip['bar_name'], strip['bar_hint']), ('Лиговский', 'Лиг'))
        self.assertEqual(strip['bar_options'][0], {'key': '', 'name': 'Все бары', 'hint': 'вся сеть'})
        self.assertEqual(len(strip['bar_options']), 5)
        self.assertEqual(strip['client']['ttl']['period'], 3600)
        self.assertEqual(strip['client']['user'], 7)
        self.assertNotIn('quarter', strip['client']['steps'])

    def test_single_and_networkwide_bar_modes(self):
        single = scope.build_strip(7, {}, {}, bar_mode='single')
        self.assertEqual([o['key'] for o in single['bar_options']],
                         ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya'], 'без «Все бары»')
        none = scope.build_strip(7, {}, {scope.COOKIE_BAR: '7:ligovskiy'}, bar_mode='none')
        self.assertEqual(none['bar_name'], 'Все бары', 'страница на бары не делится')

    def test_now_mode_title(self):
        strip = scope.build_strip(7, {}, {}, mode='now')
        self.assertEqual((strip['title'], strip['sub']), ('Сейчас', 'данные на сейчас'))

    def test_unknown_mode_is_an_error(self):
        with self.assertRaises(ValueError):
            scope.build_strip(7, {}, {}, mode='quarter')


class TestTemplate(unittest.TestCase):
    """Полоса рисуется сервером уже с выбором — при переходе между страницами она не мигает."""

    def setUp(self):
        self.app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'))
        scope.init_scope(self.app)
        self.saved = scope._current_user_id
        scope._current_user_id = lambda: 7

        @self.app.route('/page')
        def page():
            return render_template_string(
                "{% set strip = kultura_strip(mode='report', step='week') %}"
                "{% include 'shared/scope_strip.html' %}")
        self.client = self.app.test_client()

    def tearDown(self):
        scope._current_user_id = self.saved

    def test_strip_rendered_with_choice(self):
        self.client.set_cookie(scope.COOKIE_PERIOD, '7:2024-03-01_2026-10-31')
        self.client.set_cookie(scope.COOKIE_BAR, '7:ligovskiy')
        html = self.client.get('/page').get_data(as_text=True)
        self.assertIn('<span class="kp-title">1 мар 2024 – 31 окт 2026</span>', html, 'больше года')
        self.assertIn('id="ks-bar-name">Лиговский<', html)
        self.assertIn('Бар и период — общие для всех страниц', html)
        self.assertIn('window.KULTURA_STRIP', html)

    def test_foreign_choice_ignored(self):
        self.client.set_cookie(scope.COOKIE_PERIOD, '8:2024-03-01_2026-10-31')
        html = self.client.get('/page').get_data(as_text=True)
        self.assertNotIn('1 мар 2024', html)
        self.assertIn('id="ks-bar-name">Все бары<', html)

    def test_link_in_address_wins(self):
        self.client.set_cookie(scope.COOKIE_PERIOD, '7:2024-03-01_2026-10-31')
        html = self.client.get('/page?date_from=2026-10-01&date_to=2026-10-31&bar=bolshoy').get_data(as_text=True)
        self.assertIn('<span class="kp-title">Октябрь 2026</span>', html)
        self.assertIn('id="ks-bar-name">Большой пр. В.О<', html)


if __name__ == '__main__':
    unittest.main()
