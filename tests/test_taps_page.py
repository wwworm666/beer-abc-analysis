"""Страницы кранов /taps и /taps/<bar> (переработка 2026-09-27): защита от устаревших
действий, «X → Y» в замене, порядок истории, свежесть между воркерами, сводка бара,
поиск кег по названию сорта. Временный файл кранов, без app.py и без сети."""
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from core.taplist import BAR_NAMES
from core.taps_manager import TapsManager
from core.untappd_registry import load_registry

ROOT = Path(__file__).resolve().parents[1]


class TapsPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'taps.json'
        self.manager = TapsManager(str(self.path))
        self.registry = load_registry(ROOT / 'resources/iiko_untappd_registry.json')
        self.zubr = next(r for r in self.registry['products'].values() if r['iiko_article'] == '03312')
        self.dopamine = next(r for r in self.registry['products'].values() if r['iiko_article'] == '3030502409')
        spec = importlib.util.spec_from_file_location('taps_page_test_routes', ROOT / 'routes/taps.py')
        self.routes = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'extensions': types.SimpleNamespace(taps_manager=self.manager)}):
            spec.loader.exec_module(self.routes)
        app = Flask(__name__)
        app.register_blueprint(self.routes.taps_bp)
        self.client = app.test_client()

    def post(self, action, row=None, **extra):
        body = {'tap_number': 1}
        if row:
            body.update({'beer_name': row['iiko_name'], 'keg_id': row['iiko_article'],
                         'iiko_product_id': row['iiko_product_id']})
        body.update(extra)
        return self.client.post(f'/api/taps/bar1/{action}', json=body)

    def tap(self, number=1):
        return next(t for t in self.manager.get_bar_taps('bar1')['taps'] if t['tap_number'] == number)

    def expected(self, number=1):
        tap = self.tap(number)
        return {'status': tap['status'], 'current_beer': tap['current_beer'], 'started_at': tap['started_at']}

    def test_stale_page_cannot_overwrite_a_tap_changed_by_someone_else(self):
        seen_empty = self.expected()
        self.assertEqual(self.post('start', self.zubr, expected=seen_empty).status_code, 200)
        # второй бармен со страницей, открытой до подключения, пытается подключить другую кегу
        stale = self.post('start', self.dopamine, expected=seen_empty)
        self.assertEqual(stale.status_code, 409)
        self.assertIn('Кран уже изменили', stale.json['error'])
        self.assertEqual(self.tap()['iiko_product_id'], self.zubr['iiko_product_id'])
        # двойное нажатие «Кега закончилась»: второе приходит с устаревшим ожиданием
        seen_active = self.expected()
        self.assertEqual(self.post('stop', expected=seen_active).status_code, 200)
        self.assertEqual(self.post('stop', expected=seen_active).status_code, 409)
        # без expected (бот, MCP) всё работает как раньше
        self.assertEqual(self.post('start', self.dopamine).status_code, 200)
        self.assertEqual(self.post('replace', self.zubr, expected='мусор').status_code, 400)

    def test_replace_records_what_was_on_the_tap(self):
        self.post('start', self.zubr)
        self.assertEqual(self.post('replace', self.dopamine, expected=self.expected()).status_code, 200)
        replace = self.manager.get_tap_history('bar1', 1)['history'][0]
        self.assertEqual(replace['action'], 'replace')
        self.assertEqual(replace['old_beer'], self.zubr['iiko_name'])
        self.assertEqual(replace['old_iiko_product_id'], self.zubr['iiko_product_id'])
        self.assertEqual(replace['beer_name'], self.dopamine['iiko_name'])

    def test_history_returns_newest_events_first(self):
        for _ in range(4):
            self.post('start', self.zubr)
            self.post('stop')
        history = self.manager.get_tap_history('bar1', 1, limit=3)['history']
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]['action'], 'stop')
        stamps = [event['timestamp'] for event in history]
        self.assertEqual(stamps, sorted(stamps, reverse=True))
        full = self.manager.get_tap_history('bar1', 1, limit=50)['history']
        self.assertEqual(history, full[:3])

    def test_events_from_another_worker_are_visible(self):
        other_worker = TapsManager(str(self.path))
        other_worker.start_tap('bar1', 2, self.zubr['iiko_name'], self.zubr['iiko_article'],
                               self.zubr['iiko_product_id'])
        events = self.client.get('/api/taps/events/all?bar_id=bar1').json['events']
        self.assertEqual([(e['tap_number'], e['action']) for e in events], [(2, 'start')])
        self.assertEqual(events[0]['bar_name'], BAR_NAMES['bar1'])

    def test_stats_count_empty_unverified_and_fail_loudly(self):
        self.post('start', self.zubr)
        self.manager.start_tap('bar1', 2, 'КЕГ Неизвестный сорт 30 л', 'AUTO-1')
        stats = self.client.get('/api/taps/bar1/stats').json
        self.assertEqual((stats['active'], stats['empty'], stats['total'], stats['unverified']), (2, 22, 24, 1))
        self.assertIsInstance(stats['activity_7d'], float)
        full = self.client.get('/api/taps/bar3/stats').json
        self.assertEqual((full['active'], full['empty']), (0, 12))
        self.assertEqual(self.client.get('/api/taps/bar9/stats').status_code, 404)
        with patch.object(self.manager, 'get_bar_taps', side_effect=RuntimeError('диск')):
            broken = self.client.get('/api/taps/bar1/stats')
        self.assertEqual(broken.status_code, 503)
        self.assertNotIn('empty', broken.json)

    def test_keg_list_is_searchable_by_beer_name_and_brewery(self):
        beers = self.client.get('/api/beers/draft').json['beers']
        dopamine = next(b for b in beers if b['id'] == self.dopamine['iiko_product_id'])
        self.assertTrue(dopamine['mapped'])
        self.assertEqual((dopamine['beer_name'], dopamine['brewery']), ('Dopamine', 'Zavod'))
        unmapped = [b for b in beers if not b['mapped']]
        self.assertTrue(all(b['beer_name'] is None for b in unmapped))

    def test_bars_have_real_names_everywhere(self):
        self.assertEqual({bar['bar_id']: bar['name'] for bar in self.manager.get_bars()}, BAR_NAMES)
        self.assertEqual(self.manager.get_bar_taps('bar2')['bar_name'], 'Лиговский')

    def test_pages_render_with_tap_counts_from_one_place(self):
        from routes.pages import _tap_bars
        bars = _tap_bars()
        self.assertEqual([(b['id'], b['taps']) for b in bars],
                         [(k, v['taps']) for k, v in TapsManager.BARS_CONFIG.items()])
        app = Flask('taps_pages', template_folder=str(ROOT / 'templates'))
        app.jinja_env.globals['app_version'] = 'test'
        with app.test_request_context('/taps/bar1'):
            from flask import render_template
            main = render_template('taps_main.html', bars=bars)
            bar = render_template('taps_bar.html', bar_id='bar1', bar_name=BAR_NAMES['bar1'],
                                  tap_count=24, bars=bars)
        for name in BAR_NAMES.values():
            self.assertIn(name, main)
        self.assertIn('data-taps="24"', bar)
        self.assertIn('aria-current="page"', bar)
        self.assertIn('/static/js/taps/bar.js', bar)
        for page in (main, bar):
            self.assertNotRegex(page, '[\U0001F300-\U0001FAFF☀-➿]')


if __name__ == '__main__':
    unittest.main()
