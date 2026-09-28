# -*- coding: utf-8 -*-
"""
Комментарии к периодам дашборда (POST/GET /api/comments/<venue_key>/<period_key>).

Ошибка до 2026-09-28: комментарий писался В ФАЙЛ ПЛАНОВ по ключу периода и проходил
проверку полного плана — для ключа периода дашборда ('2026-09-14_2026-09-20') плана нет,
и КАЖДОЕ сохранение отвечало 500 «Missing required field: revenue»; venue_key не
использовался вовсе. Теперь комментарии — отдельный файл period_comments.json
(core/plans_manager.PeriodCommentsStore), ключ (заведение, период).

Что проверяется:
- сохранение ключом периода дашборда — 200, а не 500; у каждого заведения свой текст;
- файл планов маршрут не трогает (save_plan не вызывается, байты файла те же);
- перенос старых комментариев из файла планов: виден у любого заведения (legacy),
  файл планов не меняется, перенос один раз; свой текст заведения важнее старого;
  пустой текст очищает комментарий заведения и скрывает старый;
- файл планов не читается — перенос откладывается, комментарии работают;
- проверки ввода: заведение, формат ключа периода и даты, тип и длина текста,
  тело не объект — 400; битый файл комментариев — 503 и файл не перезаписан;
- автор: логин, через MCP — «логин · агент».

Сеть и iiko не трогаются; данные — во временной папке.
Запуск: py -3 -m pytest -q tests/test_dashboard_comments.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

from flask import Flask

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

import routes.dashboard as rd  # noqa: E402
from core import plans_manager as pm  # noqa: E402
from routes.dashboard import dashboard_bp  # noqa: E402

PERIOD = '2026-09-14_2026-09-20'

# Запись полного плана (как в plansdashboard.json) — для файла планов в тесте.
FULL_PLAN = {
    'revenue': 1000000.0, 'checks': 500, 'averageCheck': 2000.0, 'draftShare': 50.0,
    'packagedShare': 30.0, 'kitchenShare': 20.0, 'revenueDraft': 500000.0,
    'revenuePackaged': 300000.0, 'revenueKitchen': 200000.0, 'markupPercent': 200.0,
    'profit': 600000.0, 'markupDraft': 250.0, 'markupPackaged': 120.0,
    'markupKitchen': 180.0, 'loyaltyWriteoffs': 50000.0, 'tapActivity': 100.0,
}


class CommentsBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='comments_')
        self.comments_file = os.path.join(self.tmp, 'period_comments.json')
        self.plans_file = os.path.join(self.tmp, 'plansdashboard.json')
        self.saved_store = rd._comments_store
        self.saved_user = rd.current_user
        rd.current_user = lambda: None
        self.use_store()
        app = Flask(__name__)
        app.register_blueprint(dashboard_bp)
        self.client = app.test_client()

    def tearDown(self):
        rd._comments_store = self.saved_store
        rd.current_user = self.saved_user
        shutil.rmtree(self.tmp, ignore_errors=True)

    def use_store(self):
        """Новый экземпляр хранилища на тех же файлах (как новый процесс/воркер)."""
        rd._comments_store = pm.PeriodCommentsStore(
            data_file=self.comments_file, legacy_plans_file=self.plans_file)
        return rd._comments_store

    def write_plans(self, plans):
        with open(self.plans_file, 'w', encoding='utf-8') as f:
            json.dump({'plans': plans, 'metadata': {}}, f, ensure_ascii=False, indent=2)
        with open(self.plans_file, 'rb') as f:
            return f.read()

    def post(self, venue, period, body):
        return self.client.post('/api/comments/%s/%s' % (venue, period), json=body)

    def get(self, venue, period):
        return self.client.get('/api/comments/%s/%s' % (venue, period))


class SaveAndReadPerVenue(CommentsBase):
    def test_save_with_dashboard_period_key_is_200_not_500(self):
        """Регрессия: раньше «Missing required field: revenue» на любом ключе периода."""
        response = self.post('bolshoy', PERIOD, {'comment': '  Пятница вытянула неделю.  '})
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        body = response.get_json()
        self.assertTrue(body['success'])
        self.assertEqual('Пятница вытянула неделю.', body['comment'])
        self.assertEqual('bolshoy', body['venue_key'])
        self.assertFalse(body['legacy'])
        self.assertTrue(body['updated_at'].startswith('20'))

    def test_each_venue_has_its_own_comment(self):
        """Регрессия: venue_key раньше игнорировался — текст был общий."""
        self.post('bolshoy', PERIOD, {'comment': 'Большой: мало кухни'})
        self.post('all', PERIOD, {'comment': 'Сеть: ровно'})
        self.assertEqual('Большой: мало кухни', self.get('bolshoy', PERIOD).get_json()['comment'])
        self.assertEqual('Сеть: ровно', self.get('all', PERIOD).get_json()['comment'])
        other = self.get('ligovskiy', PERIOD)
        self.assertEqual(200, other.status_code)
        self.assertIsNone(other.get_json()['comment'])

    def test_resave_replaces_text_and_survives_new_process(self):
        self.post('ligovskiy', PERIOD, {'comment': 'первый'})
        self.post('ligovskiy', PERIOD, {'comment': 'второй'})
        self.use_store()
        self.assertEqual('второй', self.get('ligovskiy', PERIOD).get_json()['comment'])

    def test_plans_file_untouched(self):
        """Комментарий не проходит через файл планов: save_plan не вызывается."""
        before = self.write_plans({'bolshoy_2026-09': dict(FULL_PLAN)})
        original = rd.plans_manager.save_plan

        def forbidden(*_args, **_kwargs):
            raise AssertionError('комментарий не должен писаться в файл планов')
        rd.plans_manager.save_plan = forbidden
        try:
            response = self.post('bolshoy', PERIOD, {'comment': 'текст'})
        finally:
            rd.plans_manager.save_plan = original
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        with open(self.plans_file, 'rb') as f:
            self.assertEqual(before, f.read())

    def test_author_login_and_agent_suffix(self):
        rd.current_user = lambda: {'login': 'anna', 'display_name': 'Анна'}
        self.assertEqual('anna', self.post('all', PERIOD, {'comment': 'x'}).get_json()['updated_by'])
        rd.current_user = lambda: {'login': 'anna', 'via_mcp': True}
        body = self.post('all', PERIOD, {'comment': 'y'}).get_json()
        self.assertEqual('anna · агент', body['updated_by'])
        self.assertEqual('anna · агент', self.get('all', PERIOD).get_json()['updated_by'])


class LegacyMigration(CommentsBase):
    def test_old_comment_readable_for_any_venue_and_plans_file_unchanged(self):
        before = self.write_plans({
            # Старый недельный ключ: комментарий лежал внутри записи файла планов.
            '2025-11-17_2025-11-23': dict(FULL_PLAN, comment='Старый анализ недели',
                                          updatedAt='2025-11-24T10:00:00'),
            'bolshoy_2026-09': dict(FULL_PLAN),
        })
        for venue in ('all', 'bolshoy', 'varshavskaya'):
            body = self.get(venue, '2025-11-17_2025-11-23').get_json()
            self.assertEqual('Старый анализ недели', body['comment'], venue)
            self.assertTrue(body['legacy'], venue)
            self.assertEqual('2025-11-24T10:00:00', body['updated_at'])
        with open(self.plans_file, 'rb') as f:
            self.assertEqual(before, f.read(), 'файл планов не меняется')
        with open(self.comments_file, encoding='utf-8') as f:
            stored = json.load(f)
        self.assertEqual(['2025-11-17_2025-11-23'], stored['legacy_keys'])
        self.assertTrue(stored['legacy_migrated_at'])
        self.assertIn('2025-11-17_2025-11-23', stored['comments'][pm.LEGACY_VENUE])

    def test_legacy_key_of_other_format_is_still_readable(self):
        """Чтение принимает любой ключ, под которым мог лежать старый комментарий."""
        self.write_plans({'bolshoy_2026-09': dict(FULL_PLAN, comment='внутри плана')})
        body = self.get('all', 'bolshoy_2026-09').get_json()
        self.assertEqual('внутри плана', body['comment'])
        self.assertTrue(body['legacy'])

    def test_migration_runs_once(self):
        self.write_plans({'2025-11-17_2025-11-23': dict(FULL_PLAN, comment='один')})
        self.get('all', PERIOD)
        # Файл планов поменялся после переноса: второй экземпляр (новый процесс) не
        # переносит заново и не затирает уже перенесённое.
        self.write_plans({'2025-11-17_2025-11-23': dict(FULL_PLAN, comment='другой')})
        self.use_store()
        body = self.get('bolshoy', '2025-11-17_2025-11-23').get_json()
        self.assertEqual('один', body['comment'])

    def test_own_comment_beats_legacy_and_empty_text_clears(self):
        self.write_plans({PERIOD: dict(FULL_PLAN, comment='общий старый')})
        self.post('bolshoy', PERIOD, {'comment': 'свой у Большого'})
        self.assertEqual('свой у Большого', self.get('bolshoy', PERIOD).get_json()['comment'])
        self.assertEqual('общий старый', self.get('ligovskiy', PERIOD).get_json()['comment'])
        cleared = self.post('bolshoy', PERIOD, {'comment': '   '})
        self.assertEqual(200, cleared.status_code)
        self.assertIsNone(cleared.get_json()['comment'])
        self.assertIsNone(self.get('bolshoy', PERIOD).get_json()['comment'],
                          'очищенный комментарий не показывает и старый общий')
        self.assertEqual('общий старый', self.get('ligovskiy', PERIOD).get_json()['comment'])

    def test_unreadable_plans_file_postpones_migration(self):
        with open(self.plans_file, 'w', encoding='utf-8') as f:
            f.write('{битый json')
        self.assertEqual(200, self.get('all', PERIOD).status_code)
        self.assertEqual(200, self.post('all', PERIOD, {'comment': 'новый'}).status_code)
        with open(self.comments_file, encoding='utf-8') as f:
            self.assertNotIn('legacy_migrated_at', json.load(f))
        # Файл планов починили — следующий процесс переносит старое.
        self.write_plans({'2025-11-17_2025-11-23': dict(FULL_PLAN, comment='старый')})
        self.use_store()
        self.assertEqual('старый', self.get('all', '2025-11-17_2025-11-23').get_json()['comment'])
        self.assertEqual('новый', self.get('all', PERIOD).get_json()['comment'])


class Validation(CommentsBase):
    def test_bad_requests_are_400(self):
        cases = [
            ('bolshoy', '2026-09', {'comment': 'x'}, 'месячный ключ плана'),
            ('bolshoy', 'bolshoy_2026-09', {'comment': 'x'}, 'ключ плана'),
            ('bolshoy', '2026-02-30_2026-03-01', {'comment': 'x'}, 'несуществующая дата'),
            ('bolshoy', '2026-09-20_2026-09-14', {'comment': 'x'}, 'начало позже конца'),
            ('Лиговский', PERIOD, {'comment': 'x'}, 'русское имя бара'),
            ('total', PERIOD, {'comment': 'x'}, 'не ключ заведения'),
            ('bolshoy', PERIOD, {'comment': 42}, 'текст не строкой'),
            ('bolshoy', PERIOD, {'comment': 'я' * (pm.COMMENT_MAX_LEN + 1)}, 'длиннее предела'),
            ('bolshoy', PERIOD, ['comment'], 'тело не объект'),
        ]
        for venue, period, body, why in cases:
            response = self.post(venue, period, body)
            self.assertEqual(400, response.status_code, why)
            self.assertIn('error', response.get_json(), why)
        # Проверка ввода идёт до хранилища: файл комментариев даже не создан.
        self.assertFalse(os.path.exists(self.comments_file))

    def test_get_validates_venue_and_key_length(self):
        self.assertEqual(400, self.get('nevsky', PERIOD).status_code)
        self.assertEqual(400, self.get('all', 'x' * (pm.PERIOD_KEY_MAX_LEN + 1)).status_code)

    def test_limit_is_inclusive(self):
        response = self.post('all', PERIOD, {'comment': 'я' * pm.COMMENT_MAX_LEN})
        self.assertEqual(200, response.status_code)

    def test_corrupt_comments_file_is_503_and_not_overwritten(self):
        with open(self.comments_file, 'w', encoding='utf-8') as f:
            f.write('{"comments": [')
        with open(self.comments_file, 'rb') as f:
            before = f.read()
        self.assertEqual(503, self.get('all', PERIOD).status_code)
        self.assertEqual(503, self.post('all', PERIOD, {'comment': 'x'}).status_code)
        with open(self.comments_file, 'rb') as f:
            self.assertEqual(before, f.read())


if __name__ == '__main__':
    unittest.main(verbosity=2)
