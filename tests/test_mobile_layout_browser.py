"""
Мобильная версия (макет утверждён владельцем 2026-11-01) — в настоящем браузере.

Self-runnable: `py -3 tests/test_mobile_layout_browser.py` (совместимо с pytest).

Поднимает Flask только с шаблонами и core.scope (как app.py), ответы API подменяет Playwright,
поэтому ни iiko, ни витрина гостей не нужны. Пропускается, если нет Playwright или Chromium.

На телефоне (390 px):
- полоса «Бар и период» — одна строка: бар коротким именем, период — коротким названием в две
  строки (core/periods.period_title_compact, period_core.js), название не обрезано; у страницы
  «на сейчас» периода нет, бар — полным именем;
- раздел «Гости»: строки счётчиков нет, числа — значками на вкладках;
- «Маркетинг»: вкладки — одна строка с прокруткой вбок.
На компьютере (1280 px) всё как было: полные подписи, строка счётчиков, значков нет.
"""

import importlib.util
import json
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from flask import Flask, render_template, render_template_string  # noqa: E402

import core.scope as scope  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMIUM = os.environ.get('STOCKS_TEST_CHROMIUM') or '/opt/pw-browsers/chromium'
USER_ID = 7
PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/static/dashboard/styles/variables.css">
<link rel="stylesheet" href="/static/dashboard/styles/base.css">
<link rel="stylesheet" href="/static/dashboard/styles/sidebar.css">
<link rel="stylesheet" href="/static/dashboard/styles/mobile.css">
</head><body>{{ strip_decl }}<div class="container">{% set page_title = title %}
{% include 'shared/nav.html' %}</div></body></html>"""
ATTENTION = {'reviews_unanswered': 3, 'publications_today': 1, 'delivery_errors': 0, 'overdue': 2}


def _browser_available():
    return importlib.util.find_spec('playwright') is not None and os.path.exists(CHROMIUM)


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _strip_page(title, **opts):
    def view():
        return render_template_string(
            PAGE.replace('{{ strip_decl }}', '{% set strip = kultura_strip(**opts) %}'),
            opts=opts, title=title)
    return view


def _app():
    app = Flask('mobile_layout_test', template_folder=os.path.join(REPO, 'templates'),
                static_folder=os.path.join(REPO, 'static'))
    scope.init_scope(app)
    app.add_url_rule('/report', 'report', _strip_page('Отчёт', mode='report', step='month', live=True))
    app.add_url_rule('/now', 'now', _strip_page('Заказы и остатки', mode='now', bar_mode='single'))
    app.add_url_rule('/personal', 'personal', _strip_page('Я', mode='monthly', step='month', live=True,
                                                          bar_mode='none', bar_label='Личная страница',
                                                          bar_hint=''))
    app.add_url_rule('/guests', 'guests', lambda: render_template(
        'guests.html', app_version='t', bars=['Лиговский'], last_full_day='2026-10-29',
        coverage_from='2017-12-18', freshness=None))
    return app


def _json(route, payload):
    route.fulfill(status=200, content_type='application/json', body=json.dumps(payload, ensure_ascii=False))


def _box(page, sel):
    return page.evaluate("""(sel) => {
        const e = document.querySelector(sel);
        if (!e) return null;
        const cs = getComputedStyle(e), r = e.getBoundingClientRect();
        return {shown: cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0,
                h: Math.round(r.height), cut: e.scrollWidth > e.clientWidth + 1, text: e.textContent.trim(),
                scrolls: e.scrollWidth > e.clientWidth + 1};
    }""", sel)


@pytest.mark.skipif(not _browser_available(), reason='Playwright или Chromium не установлены')
def test_phone_layout():
    from playwright.sync_api import sync_playwright

    saved = scope._current_user_id
    scope._current_user_id = lambda: USER_ID
    port = _free_port()
    threading.Thread(target=lambda: _app().run(port=port, use_reloader=False), daemon=True).start()
    time.sleep(1.2)
    try:
        _scenario(sync_playwright, f'http://127.0.0.1:{port}')
    finally:
        scope._current_user_id = saved


def _scenario(sync_playwright, base):
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM, headless=True)
        phone = browser.new_context(viewport={'width': 390, 'height': 844})
        page = phone.new_page()
        page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
        page.route('**/api/guest-hub/attention**', lambda r: _json(r, ATTENTION))
        page.route('**/api/guests/**', lambda r: _json(r, {'meta': {}, 'data': {}}))

        # --- Отчёт: одна строка, короткое название периода целиком, «Все бары»
        page.goto(base + '/report')
        page.wait_for_selector('#ks-period .kp-title-c')
        strip = _box(page, '#kultura-strip')
        assert strip['h'] <= 64, 'полоса на телефоне не в одну строку: %s px' % strip['h']
        title_c = _box(page, '#ks-period .kp-title-c')
        expected = page.evaluate('KPeriod.periodTitleCompact(KStrip.get().period)')
        assert title_c['shown'] and title_c['text'] == expected and not title_c['cut'], title_c
        assert not _box(page, '#ks-period .kp-title')['shown'], 'полное название видно на телефоне'
        bar = _box(page, '#ks-bar-short')
        assert bar['shown'] and bar['text'] == 'Все бары' and not bar['cut'], bar
        assert not _box(page, '#ks-bar-name')['shown']
        header = _box(page, '.header-bar')
        assert header['h'] <= 56, 'карточка заголовка на телефоне выше 52 px: %s' % header['h']

        # Длинный свой период и бар — короткие подписи, ничего не обрезано
        phone.add_cookies([
            {'name': scope.COOKIE_PERIOD, 'value': '%d%%3A2024-03-01_2026-10-29' % USER_ID, 'url': base},
            {'name': scope.COOKIE_BAR, 'value': '%d%%3Abolshoy' % USER_ID, 'url': base}])
        page.goto(base + '/report')
        page.wait_for_selector('#ks-period .kp-title-c')
        title_c = _box(page, '#ks-period .kp-title-c')
        assert title_c['text'] == '01.03.24–29.10.26' and not title_c['cut'], title_c
        assert _box(page, '#ks-period .kp-sub-c')['text'] == '973 дня'
        bar = _box(page, '#ks-bar-short')
        assert bar['text'] == 'ВО' and not bar['cut'], bar
        assert _box(page, '#kultura-strip')['h'] <= 64

        # --- «На сейчас»: периода нет, бар — полным именем на всю строку
        page.goto(base + '/now')
        page.wait_for_selector('#kultura-strip')
        assert not _box(page, '#ks-period')['shown'], 'у страницы «на сейчас» на телефоне виден период'
        name = _box(page, '#ks-bar-name')
        assert name['shown'] and name['text'] == 'Большой пр. В.О' and not name['cut'], name
        assert _box(page, '#kultura-strip')['h'] <= 64

        # --- Страница без баров («Я», зарплата): серой подписи бара на телефоне нет
        page.goto(base + '/personal')
        page.wait_for_selector('#ks-period .kp-title-c')
        assert not _box(page, '#ks-bar-trigger')['shown'], 'серая подпись бара занимает место на телефоне'
        assert not _box(page, '#ks-period .kp-title-c')['cut']
        # Выбран свой период (cookie выше) — помесячная страница подписывает месяц второй строкой.
        note = _box(page, '#ks-note')
        assert note['shown'] and note['text'].startswith('по месяцам — показан'), note
        assert _box(page, '#kultura-strip')['h'] <= 84, 'полоса с подписью выше двух строк'
        assert _box(page, '#ks-period')['h'] <= 46

        # --- «Маркетинг»: счётчики — значками на вкладках, вкладки — одна строка
        page.goto(base + '/guests')
        page.wait_for_selector('.gh-tab-n:not([hidden])')
        assert not _box(page, '.gh-embed .gh-attn')['shown'], 'строка счётчиков видна на телефоне'
        badges = page.evaluate("""() => [...document.querySelectorAll('.gh-tab-n')]
            .map((b) => [b.dataset.attnBadge, b.hidden ? '' : b.textContent])""")
        assert badges == [['publications_today', '1'], ['delivery_errors overdue', '2'],
                          ['reviews_unanswered', '3']], badges
        tabs = _box(page, '#guestsTabs')
        assert tabs['h'] <= 50 and tabs['scrolls'], 'вкладки «Маркетинга» не в одну строку: %s' % tabs
        overflow = page.evaluate('document.documentElement.scrollWidth - innerWidth')
        assert overflow <= 1, 'страница шире экрана на %s px' % overflow
        phone.close()

        # --- Компьютер: как было
        desk = browser.new_context(viewport={'width': 1280, 'height': 900})
        page = desk.new_page()
        page.route('**/api/guest-hub/attention**', lambda r: _json(r, ATTENTION))
        page.route('**/api/guests/**', lambda r: _json(r, {'meta': {}, 'data': {}}))
        page.goto(base + '/report')
        page.wait_for_selector('#ks-period .kp-title')
        assert _box(page, '#ks-period .kp-title')['shown'] and not _box(page, '#ks-period .kp-title-c')['shown']
        assert _box(page, '#ks-bar-name')['shown'] and not _box(page, '#ks-bar-short')['shown']
        page.goto(base + '/guests')
        page.wait_for_selector('#ghAttention:not(.is-loading)')
        assert _box(page, '.gh-embed .gh-attn')['shown'], 'на компьютере пропала строка счётчиков'
        assert not _box(page, '.gh-tab-n:not([hidden])')['shown'], 'на компьютере видны значки'
        browser.close()
    assert not errors, errors


if __name__ == '__main__':
    if not _browser_available():
        print('SKIP: Playwright или Chromium не установлены')
        sys.exit(0)
    test_phone_layout()
    print('ok   test_phone_layout')
