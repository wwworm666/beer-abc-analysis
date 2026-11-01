# -*- coding: utf-8 -*-
"""
Страницы сотрудников и рабочие страницы на полосе «Бар и период» (план единого виджета,
docs/planning/period-widget-rollout.md, этапы 4 и 5; стандарт — docs/period-standard.md).

Что защищают:
1. Каждая страница объявляет полосу с нужным режимом (отчёт / помесячный), шагом, баром и
   будущими месяцами — сервер рисует её уже с выбором (core/scope.build_strip).
2. Своих выборов бара и периода у страниц нет: календарей Flatpickr, полей месяца, стрелок
   месяца, вкладок и списков баров (виды страницы, которые не бар и не период, остаются).
3. Страницы берут бар и период из window.KStrip, слушают KStrip.onChange и считают сразу —
   без кнопок «Рассчитать» / «Анализировать» (ответ владельца Р5), через общий запуск
   static/js/shared/strip_runner.js (пауза, отбрасывание устаревшего ответа).
4. Node-проверки страниц (tests/test_strip_runner.mjs, tests/test_schedule_strip_runtime.mjs,
   tests/test_cleanliness_strip_runtime.mjs) и синтаксис изменённых скриптов — когда node есть
   (в CI на ubuntu он есть).

Шаблоны рендерятся голым Flask с core.scope.init_scope (как tests/test_scope.py): без app.py,
без iiko и без сети.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from flask import Flask, render_template  # noqa: E402

from core import scope  # noqa: E402

NODE = shutil.which('node')
TEMPLATES = os.path.join(ROOT, 'templates')


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


class PageRender(unittest.TestCase):
    """Рендер шаблона страницы с полосой: пользователь 7, без выбора в cookie."""

    def setUp(self):
        self.app = Flask(__name__, template_folder=TEMPLATES)
        self.app.jinja_env.globals['app_version'] = 'test'
        scope.init_scope(self.app)
        self.saved = scope._current_user_id
        scope._current_user_id = lambda: 7

    def tearDown(self):
        scope._current_user_id = self.saved

    def render(self, template, url='/page', **ctx):
        with self.app.test_request_context(url):
            return render_template(template, **ctx)

    @staticmethod
    def strip_config(html):
        m = re.search(r'window\.KULTURA_STRIP = (\{.*?\});</script>', html)
        assert m, 'полоса не нарисована'
        return json.loads(m.group(1))

    def assert_no_own_period_controls(self, html, name, month_inputs=0):
        """Нет своих выборов периода и бара. month_inputs — поля месяца, которые правят данные
        (месяц целей KPI в редакторе зарплаты), а не выбирают период страницы."""
        for needle in ('flatpickr', 'id="date-range"', 'id="compare-date-range"', 'id="bar-select"'):
            self.assertNotIn(needle, html, '%s: свой выбор периода или бара (%s)' % (name, needle))
        self.assertEqual(html.count('type="month"'), month_inputs, name + ': своё поле месяца')


class EmployeePageTest(PageRender):
    def test_strip_report_week(self):
        html = self.render('employee.html')
        cfg = self.strip_config(html)
        self.assertEqual(cfg['mode'], 'report')
        self.assertEqual(cfg['step'], 'week')
        self.assertEqual(cfg['barMode'], 'all')
        self.assertEqual(cfg['period']['step'], 'week', 'без выбора — эта неделя (Р2)')
        self.assertIn('data-mode="report"', html)

    def test_no_own_controls(self):
        html = self.render('employee.html')
        self.assert_no_own_period_controls(html, 'employee.html')
        for needle in ('id="analyze-btn"', 'id="compare-btn"', 'Анализировать</button>',
                       'Сравнить</button>', 'cdn.jsdelivr.net'):
            self.assertNotIn(needle, html)
        self.assertIn('/static/libs/chart.umd.min.js', html, 'Chart.js — своя копия, не CDN')

    def test_wiring(self):
        src = _read('templates/employee.html')
        self.assertIn('/static/js/shared/strip_runner.js', src)
        self.assertIn('strip.onChange(', src)
        self.assertIn('strip.barInfo(s.bar)', src, 'бар в API — имя iiko из таблицы баров')
        self.assertIn('iikoBar: info ? info.iiko_name : null', src)
        # Список сотрудников — за период и бар полосы.
        self.assertRegex(src, r"/api/employees\?' \+ q\.toString\(\)")
        self.assertIn("q.set('bar', sc.iikoBar)", src)
        # Анализ и сравнение — сразу, через общий запуск.
        self.assertIn('analysisRunner = KStripRunner.create(', src)
        self.assertIn('compareRunner = KStripRunner.create(', src)
        self.assertIn('Считаю показатели: ', src)


class SalaryPageTest(PageRender):
    def test_strip_monthly_networkwide(self):
        html = self.render('bonus.html')
        cfg = self.strip_config(html)
        self.assertEqual(cfg['mode'], 'monthly')
        self.assertEqual(cfg['step'], 'month')
        self.assertEqual(cfg['steps'], ['month'])
        self.assertEqual(cfg['barMode'], 'none', 'сеть на бары не делится — бар серый')
        self.assertFalse(cfg['allowFuture'], 'будущий месяц не считается')
        self.assertEqual(cfg['period']['step'], 'month', 'без выбора — этот месяц (Р2)')
        self.assertIn('id="ks-bar-name">Все бары<', html)
        self.assertIn('id="ks-bar-hint">вся сеть<', html)

    def test_week_choice_shows_month_of_thursday(self):
        """Неделя 26 окт – 1 ноя: показан октябрь (четверг 29.10), подпись в полосе (Р3)."""
        with self.app.test_request_context('/salary', headers={
                'Cookie': scope.COOKIE_PERIOD + '=7:2026-10-26_2026-11-01'}):
            html = render_template('bonus.html')
        cfg = self.strip_config(html)
        self.assertEqual(cfg['period'], {'start': '2026-10-01', 'end': '2026-10-31', 'step': 'month'})
        self.assertIn('по месяцам — показан октябрь 2026', html)

    def test_no_own_controls_and_exports_in_strip(self):
        html = self.render('bonus.html')
        self.assert_no_own_period_controls(html, 'bonus.html', month_inputs=1)
        self.assertNotIn('id="calc-btn"', html)
        self.assertNotIn('Рассчитать</button>', html)
        # Выгрузка — в полосе (strip_actions), до расчёта выключена.
        strip_html = html[html.index('id="kultura-strip"'):html.index('window.KULTURA_STRIP')]
        self.assertIn('id="export-btn"', strip_html)
        self.assertIn('id="export-gsheet-btn"', strip_html)
        self.assertIn('id="export-menu"', strip_html, 'лист выгрузки для телефона')
        # Редактор целей KPI — правка данных, а не период страницы: его поле месяца остаётся.
        self.assertIn('id="target-month"', html)

    def test_wiring(self):
        src = _read('templates/bonus.html')
        self.assertIn('/static/js/shared/strip_runner.js', src)
        self.assertIn('calcRunner = KStripRunner.create(', src)
        self.assertIn('calcRunner.now();', src, 'расчёт сразу при открытии')
        self.assertIn("strip.onChange(e => { if (e.type === 'period') calcRunner.schedule(); })", src)
        self.assertIn("'Считаю зарплату за ' + m.phrase", src)
        self.assertIn('K.monthOf(p)', src)
        # «Весь текущий месяц» и месяц редактора — с сервера, не с часов устройства.
        self.assertNotIn('Date.now() + 3 * 3600', src)
        self.assertNotIn('const now = new Date();', src)


@unittest.skipIf(NODE is None, 'node не установлен')
class NodeChecks(unittest.TestCase):
    def run_node(self, *args):
        return subprocess.run([NODE] + list(args), capture_output=True, text=True,
                              encoding='utf-8', timeout=120, cwd=ROOT)

    def test_strip_runner(self):
        run = self.run_node('tests/test_strip_runner.mjs')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_changed_scripts_syntax(self):
        for rel in ('static/js/shared/strip_runner.js',):
            run = self.run_node('--check', rel)
            self.assertEqual(run.returncode, 0, rel + ': ' + run.stderr)


if __name__ == '__main__':
    unittest.main()
