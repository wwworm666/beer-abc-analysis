# -*- coding: utf-8 -*-
"""Этап 3 плана единого виджета (docs/planning/period-widget-rollout.md): аналитика на полосе.

Что защищают тесты:
1. Розлив, фасовка, кухня (/draft, /packaging, /kitchen) — общая карточка заголовка и полоса
   «Бар и период» вместо своей шапки и меню; без выбора — последние 30 полных дней (XYZ
   нужно не меньше трёх недель); выбор за последний час и ссылка — сильнее правила.
2. Маршруты /api/draft-kegs, /api/packaging, /api/kitchen принимают бар и ключом
   (ligovskiy -> «Лиговский» по таблице баров), имя iiko и '' работают как раньше.
3. Ежемесячный отчёт (/monthly-report) — помесячная полоса: шаги месяц и год, без выбора —
   последний закрытый месяц (в январе — декабрь прошлого года); своих списков года, месяца
   ТОП-10 и бара у графиков нет.
Сеть не трогается: загрузчики подменены, «сегодня» — 01.11.2026.

Запуск:
    python -m pytest -q tests/test_analytics_strip.py
"""
import json
import os
import sys
import unittest
from datetime import date
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from flask import Flask  # noqa: E402

from core import scope  # noqa: E402
from routes.analysis import analysis_bp, _abc_bar  # noqa: E402
from routes.pages import pages_bp  # noqa: E402

TODAY = date(2026, 11, 1)   # воскресенье; последний полный день — 31.10


def make_app():
    app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'),
                static_folder=os.path.join(ROOT, 'static'))
    app.jinja_env.globals['app_version'] = 'test'
    app.register_blueprint(pages_bp)
    app.register_blueprint(analysis_bp)
    scope.init_scope(app)
    return app


def strip_config(html):
    """window.KULTURA_STRIP из страницы — настройки полосы, которые сервер отдал странице."""
    raw = html.split('window.KULTURA_STRIP = ', 1)[1].split(';</script>', 1)[0]
    return json.loads(raw)


class StripPageTestCase(unittest.TestCase):
    def setUp(self):
        self.client = make_app().test_client()
        self.patches = [patch('core.msk_time.business_today', return_value=TODAY),
                        patch.object(scope, '_current_user_id', return_value=7)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def page(self, url):
        response = self.client.get(url)
        self.assertEqual(200, response.status_code, url)
        return response.get_data(as_text=True)


class AbcPagesTest(StripPageTestCase):
    # Заголовок — имя пункта меню (длинный не помещался на телефоне), «ABC/XYZ и потери» — в подписи.
    PAGES = {
        '/draft': ('Розлив', 'dr'),
        '/packaging': ('Фасовка', 'pk'),
        '/kitchen': ('Кухня', 'kt'),
    }

    def test_common_header_and_strip_instead_of_own_controls(self):
        for url, (title, prefix) in self.PAGES.items():
            html = self.page(url)
            self.assertIn('<span class="header-bar-page">' + title + '</span>', html, url)
            self.assertIn('<span class="header-bar-sub">ABC/XYZ и потери: ', html, url)
            self.assertIn('id="kultura-strip"', html, url + ': нет полосы «Бар и период»')
            for gone in (prefix + 'BarBtn', prefix + 'PerBtn', prefix + 'Run"', prefix + 'Burger',
                         'Запустить анализ', 'type="date"', '>ПЕРИОД<', '>БАР<'):
                self.assertNotIn(gone, html, url + ': осталось своё ' + gone)

    def test_default_is_last_30_full_days(self):
        """Без выбора — последние 30 полных дней (ответ Р2): XYZ нужно не меньше трёх недель."""
        for url in self.PAGES:
            cfg = strip_config(self.page(url))
            self.assertEqual(('report', 'last30'), (cfg['mode'], cfg['step']), url)
            self.assertEqual({'start': '2026-10-02', 'end': '2026-10-31', 'step': 'custom'}, cfg['period'], url)
            self.assertEqual(['day', 'week', 'month', 'year', 'custom'], cfg['steps'], url)
            self.assertIsNone(cfg['maxDays'], url + ': предел длины не ставим, пока нет замеров')
            self.assertEqual('', cfg['bar'], url)

    def test_choice_and_link_win(self):
        self.client.set_cookie(scope.COOKIE_PERIOD, '7:2026-10-19_2026-10-25')
        self.client.set_cookie(scope.COOKIE_BAR, '7:ligovskiy')
        cfg = strip_config(self.page('/draft'))
        self.assertEqual({'start': '2026-10-19', 'end': '2026-10-25', 'step': 'week'}, cfg['period'])
        self.assertEqual('ligovskiy', cfg['bar'])
        html = self.page('/packaging?date_from=2026-09-01&date_to=2026-09-30&bar=varshavskaya')
        cfg = strip_config(html)
        self.assertEqual({'start': '2026-09-01', 'end': '2026-09-30', 'step': 'month'}, cfg['period'])
        self.assertIn('id="ks-bar-name">Варшавская<', html)
        # Таблица баров в настройках полосы даёт странице имя бара для iiko (KStrip.barInfo).
        bars = {b['key']: b['iiko_name'] for b in cfg['bars']}
        self.assertEqual('Варшавская', bars['varshavskaya'])


class AbcRoutesBarTest(unittest.TestCase):
    """Бар ключом сводится к имени iiko; имя iiko и '' — как раньше."""

    LOADERS = {
        '/api/draft-kegs': 'routes.analysis.load_draft_kegs',
        '/api/packaging': 'routes.analysis.load_packaging',
        '/api/kitchen': 'routes.analysis.load_kitchen',
    }
    PERIOD = {'date_from': '2026-10-02', 'date_to': '2026-10-31'}

    def setUp(self):
        self.client = make_app().test_client()

    def test_mapping(self):
        cases = [('ligovskiy', 'Лиговский'), ('bolshoy', 'Большой пр. В.О'), ('bar4', 'Варшавская'),
                 ('Лиговский', 'Лиговский'), ('Большой пр. В.О', 'Большой пр. В.О'),
                 ('', None), (None, None), ('all', None), ('Общая', None), ('Все бары', None),
                 ('Неизвестный бар', 'Неизвестный бар')]
        for raw, expected in cases:
            self.assertEqual(expected, _abc_bar(raw), raw)

    def test_routes_pass_iiko_name_to_loader(self):
        for url, loader_path in self.LOADERS.items():
            for raw, expected in (('ligovskiy', 'Лиговский'), ('Лиговский', 'Лиговский'), ('', None)):
                # Загрузчик «упал» — маршрут отвечает 502, но имя бара в него уже ушло.
                with patch(loader_path, return_value=None) as loader:
                    response = self.client.post(url, json=dict(self.PERIOD, bar=raw))
                self.assertEqual(502, response.status_code, url)
                loader.assert_called_once_with(expected, '2026-10-02', '2026-10-31')


class MonthlyReportPageTest(StripPageTestCase):
    def test_monthly_strip_without_own_selects(self):
        html = self.page('/monthly-report')
        cfg = strip_config(html)
        self.assertEqual(('monthly', 'last_closed_month'), (cfg['mode'], cfg['step']))
        self.assertEqual(['month', 'year'], cfg['steps'])
        self.assertEqual({'start': '2026-10-01', 'end': '2026-10-31', 'step': 'month'}, cfg['period'],
                         'без выбора — последний закрытый месяц')
        for gone in ('id="mr-year"', 'id="mr-top-month"', 'mr-bar-select', '<select'):
            self.assertNotIn(gone, html)
        self.assertIn('id="mr-top-guests-sub"', html)

    def test_january_opens_on_previous_year(self):
        with patch('core.msk_time.business_today', return_value=date(2027, 1, 2)):
            cfg = strip_config(self.page('/monthly-report'))
        self.assertEqual({'start': '2026-12-01', 'end': '2026-12-31', 'step': 'month'}, cfg['period'])

    def test_chosen_week_shows_its_month(self):
        """Помесячная полоса показывает месяц выбранного (у недели — месяц четверга, ответ Р3)."""
        self.client.set_cookie(scope.COOKIE_PERIOD, '7:2026-10-26_2026-11-01')
        html = self.page('/monthly-report')
        cfg = strip_config(html)
        self.assertEqual({'start': '2026-10-01', 'end': '2026-10-31', 'step': 'month'}, cfg['period'])
        self.assertIn('по месяцам — показан октябрь 2026', html)


if __name__ == '__main__':
    unittest.main()
