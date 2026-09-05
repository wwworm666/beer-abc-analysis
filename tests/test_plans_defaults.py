# -*- coding: utf-8 -*-
"""
План «Доля чеков с картой» (cardChecksShare, 2026-09-05): дефолт 70% у месяцев без поля.

Что защищают тесты:

1. PLAN_SCHEMA знает cardChecksShare, а 16 прежних полей по-прежнему обязательны;
   PLAN_DEFAULTS = {'cardChecksShare': 70.0}; with_defaults не меняет исходник.

2. Чтение: get_plan/get_all_plans отдают 70.0 старому месяцу без поля и 55 месяцу
   со значением, файл при этом не меняется.

3. Расчёт периода: месяц без поля даёт 70 (а не пропуск), два месяца - средневзвешенное
   по долям взвешенных дней (пт/сб = 2), «Общее» - среднее по барам.

4. Сохранение: план без поля пишется в файл с 70.0; 120, -1 и строка отклоняются
   ValueError, файл не меняется.

5. Миграция файла fill_missing_defaults: dry-run только перечисляет, боевой прогон
   дописывает 70.0 только там, где не было (в т.ч. легаси all_YYYY-MM), 55 не трогает,
   мусорный недельный ключ пропускает, делает .backup, второй прогон - updated == [].
   CLI scripts/fill_plan_defaults.py печатает отчёт и завершается кодом 0.

Файлы проекта в data/ не трогаются: планы во временном каталоге, проверка
daily_plans.json и override весов дней подменены.

Запуск:
    py -3 -X utf8 -m unittest -v tests.test_plans_defaults
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, REPO_ROOT)

from core.day_weights import weighted_days  # noqa: E402
from core.plans_manager import PlansManager  # noqa: E402

# 16 прежних полей схемы (до 2026-09-05).
LEGACY_FIELDS = (
    'revenue', 'checks', 'averageCheck', 'draftShare', 'packagedShare', 'kitchenShare',
    'revenueDraft', 'revenuePackaged', 'revenueKitchen', 'markupPercent', 'profit',
    'markupDraft', 'markupPackaged', 'markupKitchen', 'loyaltyWriteoffs', 'tapActivity',
)


def legacy_plan(**overrides):
    """Месячный план из 16 полей, как лежит в файле у месяцев до 2026-09-05; доли 45+30+25."""
    plan = {
        'revenue': 1000000.0, 'checks': 500, 'averageCheck': 2000.0,
        'draftShare': 45.0, 'packagedShare': 30.0, 'kitchenShare': 25.0,
        'revenueDraft': 450000.0, 'revenuePackaged': 300000.0, 'revenueKitchen': 250000.0,
        'markupPercent': 200.0, 'profit': 500000.0,
        'markupDraft': 250.0, 'markupPackaged': 180.0, 'markupKitchen': 150.0,
        'loyaltyWriteoffs': 50000.0, 'tapActivity': 80.0,
    }
    plan.update(overrides)
    return plan


JUNK_KEY = '2025-11-17_2025-11-23'

FIXTURE = {
    'plans': {
        'bolshoy_2026-01': legacy_plan(),                                    # без поля
        'bolshoy_2026-02': legacy_plan(cardChecksShare=55, createdAt='2026-08-01T10:00:00',
                                       updatedAt='2026-08-02T10:00:00'),    # со значением
        'ligovskiy_2026-01': legacy_plan(cardChecksShare=55),
        'all_2025-09': legacy_plan(),                                        # легаси месячный
        JUNK_KEY: {'loyaltyWriteoffs': 1},                                   # мусорный недельный
    },
    'metadata': {'version': '1.0', 'lastUpdate': '2026-08-02T10:00:00'},
}


class PlansDefaultsCase(unittest.TestCase):
    """Общая фикстура: временный файл планов и менеджер без побочных эффектов на data/."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'plansdashboard.json')
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(FIXTURE, f, ensure_ascii=False, indent=2)
        # __init__ штатно проверяет daily_plans.json проекта - в тесте это лишнее.
        daily = patch('core.daily_plans_generator.ensure_daily_plans_current', return_value=False)
        daily.start()
        self.addCleanup(daily.stop)
        # Override весов дней читаются из data/ проекта - подменяем пустыми.
        overrides = patch.object(PlansManager, '_overrides_for_venue', return_value=lambda y, m: {})
        overrides.start()
        self.addCleanup(overrides.stop)
        self.manager = PlansManager(data_file=self.path)

    def read_plans(self):
        with open(self.path, encoding='utf-8') as f:
            return json.load(f)['plans']

    def file_bytes(self):
        with open(self.path, 'rb') as f:
            return f.read()


class SchemaAndDefaults(PlansDefaultsCase):

    def test_schema_has_card_checks_share_and_legacy_fields_required(self):
        self.assertIn('cardChecksShare', PlansManager.PLAN_SCHEMA)
        self.assertEqual({'cardChecksShare': 70.0}, PlansManager.PLAN_DEFAULTS)
        self.assertEqual(set(LEGACY_FIELDS),
                         set(PlansManager.PLAN_SCHEMA) - set(PlansManager.PLAN_DEFAULTS))
        # 16 прежних полей по-прежнему обязательны
        without_revenue = legacy_plan()
        del without_revenue['revenue']
        with self.assertRaisesRegex(ValueError, 'revenue'):
            self.manager.save_plan('varshavskaya_2026-03', without_revenue)
        self.assertNotIn('varshavskaya_2026-03', self.read_plans())

    def test_with_defaults_copies_and_keeps_none(self):
        plan = legacy_plan()
        filled = self.manager.with_defaults(plan)
        self.assertEqual(70.0, filled['cardChecksShare'])
        self.assertNotIn('cardChecksShare', plan)  # исходный словарь не изменён
        self.assertEqual(55, self.manager.with_defaults(legacy_plan(cardChecksShare=55))['cardChecksShare'])
        self.assertEqual(70.0, self.manager.with_defaults({'cardChecksShare': None})['cardChecksShare'])
        self.assertIsNone(self.manager.with_defaults(None))


class ReadWithDefaults(PlansDefaultsCase):

    def test_get_plan_old_month_gets_default_without_touching_file(self):
        before, mtime = self.file_bytes(), os.path.getmtime(self.path)
        plan = self.manager.get_plan('bolshoy_2026-01')
        self.assertEqual(70.0, plan['cardChecksShare'])
        self.assertEqual(1000000.0, plan['revenue'])
        self.assertEqual(before, self.file_bytes())
        self.assertEqual(mtime, os.path.getmtime(self.path))
        self.assertNotIn('cardChecksShare', self.read_plans()['bolshoy_2026-01'])
        self.assertFalse(os.path.exists(self.path + '.backup'))

    def test_get_plan_keeps_explicit_value(self):
        self.assertEqual(55, self.manager.get_plan('bolshoy_2026-02')['cardChecksShare'])
        self.assertEqual(55, self.manager.get_monthly_plan('bolshoy', 2026, 2)['cardChecksShare'])
        self.assertIsNone(self.manager.get_plan('bolshoy_2026-03'))

    def test_get_all_plans_fills_every_plan(self):
        before = self.file_bytes()
        plans = self.manager.get_all_plans()
        self.assertEqual(70.0, plans['bolshoy_2026-01']['cardChecksShare'])
        self.assertEqual(70.0, plans['all_2025-09']['cardChecksShare'])
        self.assertEqual(55, plans['bolshoy_2026-02']['cardChecksShare'])
        self.assertEqual(before, self.file_bytes())


class PeriodCalculation(PlansDefaultsCase):

    def test_month_without_field_gives_default(self):
        plan = self.manager.calculate_plan_for_period('bolshoy', '2026-01-01', '2026-01-31')
        self.assertEqual(70.0, plan['cardChecksShare'])
        self.assertEqual(45.0, plan['draftShare'])  # остальные относительные не задеты
        self.assertEqual(1, plan['_months_used'])

    def test_two_months_weighted_average(self):
        # Два полных месяца: доли по 1 -> (70 + 55) / 2
        plan = self.manager.calculate_plan_for_period('bolshoy', '2026-01-01', '2026-02-28')
        self.assertEqual(62.5, plan['cardChecksShare'])
        self.assertEqual(2, plan['_months_used'])
        # Полмесяца января + весь февраль: вес января = доля взвешенных дней (пт/сб = 2)
        ratio_jan = (weighted_days(date(2026, 1, 16), date(2026, 1, 31))
                     / weighted_days(date(2026, 1, 1), date(2026, 1, 31)))
        expected = (70.0 * ratio_jan + 55.0 * 1.0) / (ratio_jan + 1.0)
        plan = self.manager.calculate_plan_for_period('bolshoy', '2026-01-16', '2026-02-28')
        self.assertAlmostEqual(expected, plan['cardChecksShare'], places=2)
        self.assertLess(55.0, plan['cardChecksShare'])
        self.assertLess(plan['cardChecksShare'], 62.5)

    def test_all_venues_average_over_bars(self):
        # «Общее» = сумма баров: Большой без поля (70) + Лиговский 55, двух других баров нет
        for venue in ('all', ''):
            plan = self.manager.calculate_plan_for_period(venue, '2026-01-01', '2026-01-31')
            self.assertEqual(62.5, plan['cardChecksShare'], venue)
            self.assertEqual(2, plan['_months_used'])
            self.assertEqual(2000000.0, plan['revenue'])


class SavePlan(PlansDefaultsCase):

    def test_save_without_field_writes_default(self):
        self.assertTrue(self.manager.save_plan('varshavskaya_2026-03', legacy_plan()))
        saved = self.read_plans()['varshavskaya_2026-03']
        self.assertEqual(70.0, saved['cardChecksShare'])
        self.assertIn('createdAt', saved)
        self.assertEqual(70.0, self.manager.get_plan('varshavskaya_2026-03')['cardChecksShare'])

    def test_save_keeps_explicit_value(self):
        self.manager.save_plan('varshavskaya_2026-03', legacy_plan(cardChecksShare=55))
        self.assertEqual(55, self.read_plans()['varshavskaya_2026-03']['cardChecksShare'])
        # Обновление существующего: 0 и 100 - допустимые границы процента
        self.manager.save_plan('varshavskaya_2026-03', legacy_plan(cardChecksShare=0))
        self.assertEqual(0, self.read_plans()['varshavskaya_2026-03']['cardChecksShare'])
        self.manager.save_plan('varshavskaya_2026-03', legacy_plan(cardChecksShare=100))
        self.assertEqual(100, self.read_plans()['varshavskaya_2026-03']['cardChecksShare'])

    def test_save_rejects_percent_out_of_range(self):
        before = self.file_bytes()
        for bad in (120, -1, 100.5):
            with self.assertRaisesRegex(ValueError, 'cardChecksShare'):
                self.manager.save_plan('varshavskaya_2026-03', legacy_plan(cardChecksShare=bad))
        with self.assertRaisesRegex(ValueError, 'cardChecksShare'):
            self.manager.save_plan('varshavskaya_2026-03', legacy_plan(cardChecksShare='70'))
        self.assertEqual(before, self.file_bytes())


class FillMissingDefaults(PlansDefaultsCase):

    EXPECTED_UPDATED = ['bolshoy_2026-01', 'all_2025-09']
    EXPECTED_UNCHANGED = ['bolshoy_2026-02', 'ligovskiy_2026-01']

    def test_dry_run_lists_keys_and_keeps_file(self):
        before = self.file_bytes()
        result = self.manager.fill_missing_defaults(dry_run=True)
        self.assertEqual(self.EXPECTED_UPDATED, result['updated'])
        self.assertEqual(self.EXPECTED_UNCHANGED, result['unchanged'])
        self.assertEqual([JUNK_KEY], result['skipped'])
        self.assertTrue(result['dry_run'])
        self.assertEqual(self.path, result['file'])
        self.assertEqual(before, self.file_bytes())
        self.assertFalse(os.path.exists(self.path + '.backup'))

    def test_fill_writes_only_missing_and_is_idempotent(self):
        before = self.file_bytes()
        result = self.manager.fill_missing_defaults()
        self.assertEqual(self.EXPECTED_UPDATED, result['updated'])
        self.assertEqual(self.EXPECTED_UNCHANGED, result['unchanged'])
        self.assertEqual([JUNK_KEY], result['skipped'])
        self.assertFalse(result['dry_run'])

        plans = self.read_plans()
        self.assertEqual(70.0, plans['bolshoy_2026-01']['cardChecksShare'])
        self.assertEqual(70.0, plans['all_2025-09']['cardChecksShare'])
        self.assertEqual(55, plans['bolshoy_2026-02']['cardChecksShare'])
        self.assertEqual(55, plans['ligovskiy_2026-01']['cardChecksShare'])
        self.assertEqual({'loyaltyWriteoffs': 1}, plans[JUNK_KEY])
        # Таймстампы не тронуты: у старого не появились, у нового прежние
        self.assertNotIn('updatedAt', plans['bolshoy_2026-01'])
        self.assertEqual('2026-08-02T10:00:00', plans['bolshoy_2026-02']['updatedAt'])
        # Остальные поля как были
        for key in self.EXPECTED_UPDATED:
            self.assertEqual(FIXTURE['plans'][key],
                             {k: v for k, v in plans[key].items() if k != 'cardChecksShare'})
        # Бэкап - файл до миграции
        with open(self.path + '.backup', 'rb') as f:
            self.assertEqual(before, f.read())

        # Второй прогон ничего не дописывает
        again = self.manager.fill_missing_defaults()
        self.assertEqual([], again['updated'])
        self.assertEqual(sorted(self.EXPECTED_UPDATED + self.EXPECTED_UNCHANGED), sorted(again['unchanged']))
        self.assertEqual([JUNK_KEY], again['skipped'])


class CliScript(PlansDefaultsCase):
    """scripts/fill_plan_defaults.py: dry-run печатает отчёт и не меняет файл, боевой - дописывает."""

    @staticmethod
    def load_script():
        spec = importlib.util.spec_from_file_location(
            'fill_plan_defaults', os.path.join(REPO_ROOT, 'scripts', 'fill_plan_defaults.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_script(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.load_script().main(list(args))
        return code, out.getvalue()

    def test_dry_run_then_write(self):
        before = self.file_bytes()
        code, text = self.run_script('--dry-run', '--file', self.path)
        self.assertEqual(0, code)
        self.assertEqual(before, self.file_bytes())
        self.assertIn('dry-run', text)
        self.assertIn('Будет обновлено (2)', text)
        self.assertIn('  bolshoy_2026-01', text)
        self.assertIn('Пропущено (не месячный ключ) (1)', text)
        self.assertIn(JUNK_KEY, text)

        code, text = self.run_script('--file', self.path)
        self.assertEqual(0, code)
        self.assertIn('Обновлено (2)', text)
        self.assertEqual(70.0, self.read_plans()['bolshoy_2026-01']['cardChecksShare'])


if __name__ == "__main__":
    unittest.main()
