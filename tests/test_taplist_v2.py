"""Isolated API/storage regressions. Never modify production or repository tap data."""
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from flask import Flask
from core.taps_manager import TapsManager
from core.taplist import product_catalog, legacy_product_id, full_taplist
from core.untappd_registry import load_registry

ROOT = Path(__file__).resolve().parents[1]


class TaplistV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'taps.json'
        self.manager = TapsManager(str(self.path))
        self.registry = load_registry(ROOT / 'resources/iiko_untappd_registry.json')
        self.catalog = product_catalog(self.registry, Path(self.temp.name) / 'absent.json')
        self.zubr = next(r for r in self.registry['products'].values() if r['iiko_article'] == '03312')
        self.dopamine = next(r for r in self.registry['products'].values() if r['iiko_article'] == '3030502409')
        spec = importlib.util.spec_from_file_location('taplist_test_routes', ROOT / 'routes/taps.py')
        self.routes = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'extensions': types.SimpleNamespace(taps_manager=self.manager)}):
            spec.loader.exec_module(self.routes)
        app = Flask(__name__)
        app.register_blueprint(self.routes.taps_bp)
        self.client = app.test_client()

    def connect(self, row=None, **extra):
        row = row or self.zubr
        return self.client.post('/api/taps/bar1/start', json={
            'tap_number': 1, 'beer_name': row['iiko_name'], 'keg_id': row['iiko_article'],
            'iiko_product_id': row['iiko_product_id'], **extra})

    def tap(self):
        return self.manager.get_bar_taps('bar1')['taps'][0]

    def test_guid_selection_survives_workers_and_exports_owner_correction(self):
        second_worker = TapsManager(str(self.path))
        self.assertEqual(self.connect(self.dopamine).status_code, 200)
        self.assertEqual(second_worker.get_bar_taps('bar1')['taps'][0]['iiko_product_id'],
                         self.dopamine['iiko_product_id'])
        row = self.client.get('/api/taps/taplist-full?bar_id=bar1').json['taplist'][0]
        self.assertEqual(row['brewery'], 'Zavod')
        self.assertEqual(row['untappd_beer_id'], '3636325')
        self.assertIn('Bumblebeer', row['iiko_name'])
        response = self.client.get('/api/taps/export-taplist-full?bar_id=bar1')
        rows = list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
        self.assertEqual(rows[1][2:8], ['Zavod', 'Dopamine', row['untappd_url'], row['style'], '7.2', '95'])
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_legacy_migration_is_persisted_without_restarting_or_changing_history(self):
        self.manager.start_tap('bar1', 1, self.zubr['iiko_name'], self.zubr['iiko_article'])
        before = self.tap()
        after = self.manager.get_bar_taps('bar1', self.catalog)['taps'][0]
        self.assertEqual(after['iiko_product_id'], self.zubr['iiko_product_id'])
        self.assertEqual(after['history'], before['history'])
        self.assertEqual(after['started_at'], before['started_at'])
        self.assertEqual(TapsManager(str(self.path)).get_bar_taps('bar1')['taps'][0], after)

    def test_migration_rejects_ambiguous_names_conflicting_article_and_similar_name(self):
        name = self.zubr['iiko_name']
        tap = {'current_beer': name, 'current_keg_id': 'AUTO-1'}
        catalog = {'a': {'names': {name}, 'articles': {'1'}},
                   'b': {'names': {name}, 'articles': {'2'}}}
        self.assertIsNone(legacy_product_id(tap, catalog))
        tap['current_keg_id'] = '2'
        self.assertEqual(legacy_product_id(tap, catalog), 'b')
        tap['current_keg_id'] = '3'
        self.assertIsNone(legacy_product_id(tap, catalog))
        tap['current_keg_id'] = '1'
        tap['current_beer'] += ' special'
        self.assertIsNone(legacy_product_id(tap, catalog))

    def test_edit_after_selection_is_rejected(self):
        self.assertEqual(self.connect(beer_name='Другое пиво').status_code, 400)
        self.assertEqual(self.connect(iiko_product_id='not-a-guid').status_code, 400)
        self.assertEqual(self.tap()['status'], 'empty')

    def test_replace_and_stop_do_not_retain_previous_identity(self):
        self.connect()
        response = self.client.post('/api/taps/bar1/replace', json={
            'tap_number': 1, 'beer_name': 'Новый неизвестный сорт', 'keg_id': 'AUTO-new'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.tap()['iiko_product_id'])
        row = self.client.get('/api/taps/taplist-full').json['taplist'][0]
        self.assertFalse(row['mapped'])
        self.assertIsNone(row['abv'])
        self.client.post('/api/taps/bar1/stop', json={'tap_number': 1})
        self.assertIsNone(self.tap()['iiko_product_id'])
        self.assertEqual(self.client.get('/api/taps/taplist-full').json['count'], 0)

    def test_manual_identity_does_not_change_keg_or_accept_stale_state(self):
        self.manager.start_tap('bar1', 1, 'Сокращённое имя', 'AUTO-1')
        before = self.tap()
        payload = {'tap_number': 1, 'iiko_product_id': self.zubr['iiko_product_id'],
                   'expected': {k: before[k] for k in ('current_beer', 'current_keg_id', 'started_at', 'iiko_product_id')}}
        self.assertEqual(self.client.post('/api/taps/bar1/identify', json=payload).status_code, 200)
        after = self.tap()
        for key in ('history', 'started_at', 'current_beer', 'current_keg_id'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(self.client.post('/api/taps/bar1/identify', json=payload).status_code, 409)

    def test_unavailable_registry_never_falls_back_to_name_mapping(self):
        self.connect()
        with patch.object(self.routes, 'load_registry', side_effect=ValueError('bad registry')):
            self.assertEqual(self.client.get('/api/taps/taplist-full').status_code, 503)
            self.assertEqual(self.client.get('/api/taps/export-taplist-full').status_code, 503)
        self.assertEqual(self.client.get('/api/taps/export-taplist-full?bar_id=unknown').status_code, 404)

    def test_null_ibu_csv_escaping_and_unmapped_rows_are_retained(self):
        self.connect()
        self.manager.start_tap('bar1', 2, '=SUM(1,2)', 'AUTO-2')
        response = self.client.get('/api/taps/export-taplist-full?bar_id=bar1')
        rows = list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
        self.assertEqual(rows[1][7], '')
        self.assertEqual(rows[2][3], "'=SUM(1,2)")
        self.assertEqual(response.headers['X-Taplist-Unmapped-Count'], '1')

    def test_corrupt_state_is_not_overwritten_and_write_errors_are_reported(self):
        self.path.write_text('{bad json', encoding='utf8')
        self.assertEqual(self.connect().status_code, 500)
        self.assertEqual(self.path.read_text(), '{bad json')
        self.path.write_text('{}', encoding='utf8')
        with patch('core.taps_manager.os.replace', side_effect=OSError('write failed')):
            self.assertEqual(self.connect().status_code, 500)
        self.assertEqual(self.tap()['status'], 'empty')

    def test_catalog_keeps_distinct_guids_with_identical_names(self):
        registry = {'products': {guid: {'iiko_name': 'КЕГ Одинаково', 'iiko_article': '1', 'status': 'verified'}
                                 for guid in ('a', 'b')}}
        catalog = product_catalog(registry, Path(self.temp.name) / 'absent.json')
        self.assertEqual(set(catalog), {'a', 'b'})

    def test_bundled_registry_survives_data_mount_and_corruption_is_explicit(self):
        import core.untappd_registry as module
        bundled = Path(self.temp.name) / 'bundled.json'
        bundled.write_text(json.dumps(self.registry), encoding='utf8')
        with patch.dict('os.environ', {}, clear=True), patch.object(module, 'BUNDLED_REGISTRY', bundled), \
                patch.object(module, 'DEFAULT_REGISTRY', Path(self.temp.name) / 'missing.json'):
            self.assertEqual(load_registry()['summary']['all_products'], 479)
            bundled.write_text('{bad', encoding='utf8')
            with self.assertRaises(ValueError):
                load_registry()


if __name__ == '__main__':
    unittest.main()
