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


class GoalsPageTest(PageRender):
    def test_strip_monthly_with_future(self):
        html = self.render('goals.html')
        cfg = self.strip_config(html)
        self.assertEqual((cfg['mode'], cfg['step'], cfg['barMode']), ('monthly', 'month', 'all'))
        self.assertTrue(cfg['allowFuture'], 'цели скидывают заранее — будущие месяцы можно')
        self.assertEqual(cfg['period']['step'], 'month')

    def test_no_own_controls(self):
        html = self.render('goals.html')
        self.assert_no_own_period_controls(html, 'goals.html')
        for needle in ('id="goal-month"', 'id="bar-tabs"', 'selectBar(', 'class="bar-tab'):
            self.assertNotIn(needle, html)
        strip_html = html[html.index('id="kultura-strip"'):html.index('window.KULTURA_STRIP')]
        self.assertIn('window.print()', strip_html, '«Печать / PDF» — в полосе')

    def test_wiring(self):
        src = _read('templates/goals.html')
        self.assertIn('loader = KStripRunner.create(', src)
        self.assertIn('loader.now();', src)
        self.assertIn("if (e.type === 'period') loader.schedule();", src)
        self.assertIn("return (strip && strip.get().bar) || 'all';", src, 'все бары — все точки')
        self.assertIn("BARS.filter(b => b.key === bar)", src)
        self.assertIn('K.toISO(K.today())', src, '«сегодня» — рабочий день с сервера')
        self.assertNotIn('new Date().toISOString()', src)
        self.assertIn('.ks, .no-print', src, 'полоса не печатается')


class SchedulePageTest(PageRender):
    def test_strip_monthly_with_future(self):
        html = self.render('schedule.html')
        cfg = self.strip_config(html)
        self.assertEqual((cfg['mode'], cfg['step'], cfg['barMode']), ('monthly', 'month', 'all'))
        self.assertTrue(cfg['allowFuture'], 'график планируют вперёд')

    def test_no_month_buttons(self):
        html = self.render('schedule.html')
        self.assert_no_own_period_controls(html, 'schedule.html')
        for needle in ('id="prevMonth"', 'id="nextMonth"', 'id="currentMonth"', 'class="month-nav"'):
            self.assertNotIn(needle, html)
        # Загрузка — вверху страницы, с подписью «что грузится».
        self.assertIn('<span class="loading-text">', html)
        self.assertLess(html.index('id="loading"'), html.index('class="sc-mobile"'))
        self.assertLess(html.index('strip_runner.js'), html.index('schedule/view.js'))

    def test_ics_link_in_strip_for_linked_account(self):
        with self.app.test_request_context('/schedule'):
            html = render_template('schedule.html', current_user={'employee_iiko_id': 'g1'})
        strip_html = html[html.index('id="kultura-strip"'):html.index('window.KULTURA_STRIP')]
        self.assertIn('href="/schedule/cal.ics"', strip_html)

    def test_wiring(self):
        common = _read('static/js/schedule/common.js')
        view = _read('static/js/schedule/view.js')
        css = _read('static/schedule/schedule.css')
        self.assertNotIn('new Date().getMonth()', common, 'месяц — не с часов устройства')
        self.assertIn('function syncMonthFromStrip()', common)
        self.assertIn("state.locations[i].venue_key === bar", common, 'точка бара — по venue_key')
        self.assertIn('strip.onChange(onStripChange)', view)
        self.assertIn('monthLoader = KStripRunner.create(', view)
        self.assertIn('monthLoader.schedule();', view)
        self.assertNotIn('shiftMonth', view + common)
        self.assertIn('все точки — выбранный бар выделен', view)
        self.assertNotIn('.month-nav', css)
        self.assertIn('.tb-card.is-focus', css)


class MePageTest(PageRender):
    def test_strip_monthly_personal(self):
        html = self.render('me.html')
        cfg = self.strip_config(html)
        self.assertEqual((cfg['mode'], cfg['step'], cfg['barMode']), ('monthly', 'month', 'none'))
        self.assertFalse(cfg['allowFuture'])
        self.assertIn('id="ks-bar-name">Личная страница<', html)
        self.assertIn('id="ks-bar-hint"></span>', html, 'подсказки под личной страницей нет')

    def test_common_header_instead_of_own(self):
        html = self.render('me.html', current_user={'display_name': 'Анна Смирнова'})
        self.assertNotIn('class="me-head"', html)
        self.assertNotIn('id="meBurger"', html)
        self.assertIn('<span class="header-bar-page">Я</span>', html)
        self.assertIn('<span class="header-bar-sub">Анна Смирнова</span>', html)
        css = _read('static/me/me.css')
        self.assertNotRegex(css, r'body\.me-page \.header-bar\s*\{\s*display:\s*none',
                            'общий заголовок не прячется')

    def test_wiring(self):
        src = _read('static/js/me/view.js')
        self.assertIn("S.api('/api/me?month=' + monthKey())", src, 'снимок — за месяц полосы')
        self.assertIn("if (e.type !== 'period' || !S.syncMonthFromStrip()) return;", src)
        self.assertIn('if (seq !== snapSeq) return;', src, 'устаревший снимок отбрасывается')
        self.assertIn('if (seq !== liveSeq) return;', src)
        self.assertIn("document.querySelector('.header-bar-sub')", src, 'роль и точки — в общий заголовок')


class CleanlinessPageTest(PageRender):
    def test_strip_monthly_from_rule_start(self):
        html = self.render('cleanliness.html')
        cfg = self.strip_config(html)
        self.assertEqual((cfg['mode'], cfg['step'], cfg['barMode']), ('monthly', 'month', 'all'))
        self.assertEqual(cfg['clock']['data_start'], '2026-08-24', 'журнал ведётся с 24.08.2026')
        self.assertFalse(cfg['allowFuture'])

    def test_no_month_arrows_and_point_select(self):
        html = self.render('cleanliness.html')
        self.assert_no_own_period_controls(html, 'cleanliness.html')
        for needle in ('id="clPrev"', 'id="clNext"', 'id="clMonthLabel"', 'id="clVenue"', 'Все точки'):
            self.assertNotIn(needle, html)
        self.assertIn('id="clStatus"', html, 'фильтр ответа — вид журнала, он остаётся')
        self.assertIn('id="clSearch"', html)

    def test_wiring(self):
        src = _read('static/js/cleanliness/view.js')
        self.assertIn("api('/api/schedule/locations')", src, 'точки графика — для ключа бара')
        self.assertIn('places[i].venue_key === bar', src)
        self.assertIn('totals_by_location', src, 'плитки бара — итоги точки с сервера')
        self.assertIn('if (seq !== loadSeq) return;', src, 'ответ за прежний месяц отбрасывается')
        self.assertNotIn('new Date()', src, 'месяц — не с часов устройства')


@unittest.skipIf(NODE is None, 'node не установлен')
class NodeChecks(unittest.TestCase):
    def run_node(self, *args):
        return subprocess.run([NODE] + list(args), capture_output=True, text=True,
                              encoding='utf-8', timeout=120, cwd=ROOT)

    def test_strip_runner(self):
        run = self.run_node('tests/test_strip_runner.mjs')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_schedule_runtime(self):
        run = self.run_node('tests/test_schedule_strip_runtime.mjs')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_cleanliness_runtime(self):
        run = self.run_node('tests/test_cleanliness_strip_runtime.mjs')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_me_calendar_runtime(self):
        run = self.run_node('tests/test_me_calendar_runtime.mjs')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_changed_scripts_syntax(self):
        for rel in ('static/js/shared/strip_runner.js', 'static/js/schedule/common.js',
                    'static/js/schedule/screens.js', 'static/js/schedule/view.js',
                    'static/js/me/view.js', 'static/js/cleanliness/view.js'):
            run = self.run_node('--check', rel)
            self.assertEqual(run.returncode, 0, rel + ': ' + run.stderr)


if __name__ == '__main__':
    unittest.main()
