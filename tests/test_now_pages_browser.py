"""
Страницы «на сейчас» на общей полосе «Бар и период» (этап 6 плана единого виджета,
docs/planning/period-widget-rollout.md, 2026-11-01) — в настоящем браузере.

Self-runnable: `py -3 tests/test_now_pages_browser.py` (совместимо с pytest).

Поднимает Flask только с шаблонами страниц и core.scope (как app.py), ответы API подменяет
Playwright (page.route), поэтому ни iiko, ни датчики, ни файлы фидов не нужны. Пропускается,
если Playwright или Chromium не установлены. «Заказы и остатки» проверяет
tests/test_stocks_browser.py.

Что проверяется:
- «Сроки годности»: своего выбора бара нет; «Все бары» -> bars=all, бар в полосе -> bar1…bar4
  по таблице баров; окно расхода подписано датами из ответа;
- «Краны»: «Все бары» — четыре карточки, выбран бар — только его карточка (ответ Р9), окно
  «Активность за 7 дней» подписано датами;
- «Температура»: выбран бар — только его карточка (Р9), «Все бары» — снова все;
- «Фиды Яндекса»: открыт фид бара из полосы; нажатие на вкладку меняет бар сайта; выбор бара
  в полосе открывает его вкладку;
- новых ошибок страницы нет.
"""

import importlib.util
import json
import os
import socket
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from flask import Flask, render_template  # noqa: E402

import core.scope as scope  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMIUM = os.environ.get('STOCKS_TEST_CHROMIUM') or '/opt/pw-browsers/chromium'
USER_ID = 7
TAP_BARS = [{'id': 'bar1', 'name': 'Большой пр. В.О', 'taps': 24}, {'id': 'bar2', 'name': 'Лиговский', 'taps': 12},
            {'id': 'bar3', 'name': 'Кременчугская', 'taps': 12}, {'id': 'bar4', 'name': 'Варшавская', 'taps': 12}]
VENUES = [('bolshoy', 'Большой пр. В.О'), ('ligovskiy', 'Лиговский'), ('kremenchugskaya', 'Кременчугская'),
          ('varshavskaya', 'Варшавская')]


def _browser_available():
    return importlib.util.find_spec('playwright') is not None and os.path.exists(CHROMIUM)


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _app():
    app = Flask('now_pages_browser_test', template_folder=os.path.join(REPO, 'templates'),
                static_folder=os.path.join(REPO, 'static'))
    scope.init_scope(app)
    app.add_url_rule('/expiration', 'expiration', lambda: render_template('expiration.html'))
    app.add_url_rule('/taps', 'taps', lambda: render_template('taps_main.html', bars=TAP_BARS, app_version='t'))
    app.add_url_rule('/temperature', 'temperature', lambda: render_template('temperature.html', app_version='t'))
    app.add_url_rule('/yandex', 'yandex', lambda: render_template('yml_feeds.html'))
    return app


def _json(route, payload, status=200):
    route.fulfill(status=status, content_type='application/json', body=json.dumps(payload, ensure_ascii=False))


def _fake_api(page, seen):
    """Ответы API страниц; seen — какие запросы ушли (для проверки параметров)."""
    def expiration(route):
        bars = parse_qs(urlparse(route.request.url).query).get('bars', [''])[0]
        seen.setdefault('expiration', []).append(bars)
        _json(route, {'updated_at': '2025-11-05T10:00:00', 'chz_updated_at': None, 'bars': [],
                      'window_days': 30, 'window_from': '2025-10-06', 'window_to': '2025-11-05',
                      'kpi': {'risk_rub': 0, 'critical_count': 0, 'surplus_units': 0},
                      'tier_counts': {}, 'items': [], 'cache': {'hit': False, 'age_sec': 0}})

    def tap_stats(route):
        bar = urlparse(route.request.url).path.split('/')[3]
        seen.setdefault('stats', []).append(bar)
        _json(route, {'active': 3, 'empty': 9, 'total': 12, 'unverified': 0, 'activity_7d': 25.0,
                      'activity_from': '2025-10-30', 'activity_to': '2025-11-05'})

    def temperature(route):
        _json(route, {'success': True, 'source': 'live', 'updated_at': int(time.time()),
                      'meta': {'configured': True, 'bands': [{'key': 'ok', 'label': 'Норма', 'min': 16, 'max': 25}]},
                      'bars': [{'venue_key': k, 'venue_name': n, 'temperature': 21.5, 'humidity': 40, 'battery': 90,
                                'online': True, 'ts': int(time.time()), 'band': 'ok', 'error': None}
                               for k, n in VENUES]})

    def feeds(route):
        _json(route, {'feeds': [{'id': b['id'], 'kind': 'bar', 'bar_id': b['id'], 'title': b['name'],
                                 'public_url': 'http://example.invalid/feeds/kitchen/' + b['id'],
                                 'beer': 1, 'excluded': 0, 'attention': 0, 'error': None, 'maps': None}
                                for b in TAP_BARS], 'snapshot': {}})

    def feed(route):
        seen.setdefault('feed', []).append(urlparse(route.request.url).path.rsplit('/', 1)[1])
        _json(route, {'error': 'нет фида в тесте'}, status=404)

    page.route('**/api/expiration/board*', expiration)
    page.route('**/api/taps/*/stats', tap_stats)
    page.route('**/api/untappd/proposals*', lambda r: _json(r, {'counts': {'proposed': 0}, 'proposals': []}))
    page.route('**/api/temperature/current*', temperature)
    page.route('**/api/temperature/history*', lambda r: _json(r, {'success': True, 'bars': {}}))
    page.route('**/api/yml/feeds', feeds)
    page.route('**/api/yml/feeds/*', feed)
    page.route('**/api/connection-status', lambda r: _json(r, {'status': 'connected'}))


@pytest.mark.skipif(not _browser_available(), reason='Playwright или Chromium не установлены')
def test_now_pages_follow_the_strip():
    from playwright.sync_api import sync_playwright

    saved = scope._current_user_id
    scope._current_user_id = lambda: USER_ID   # выбор в cookie — с номером пользователя, как у вошедшего
    port = _free_port()
    threading.Thread(target=lambda: _app().run(port=port, use_reloader=False), daemon=True).start()
    time.sleep(1.2)
    try:
        _scenario(sync_playwright, f'http://127.0.0.1:{port}')
    finally:
        scope._current_user_id = saved


def _scenario(sync_playwright, base):
    errors, seen = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM, headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
        # 404 фида — подмена теста, а не ошибка страницы
        page.on('console', lambda m: errors.append(f'console.{m.type}: {m.text}')
                if m.type == 'error' and 'status of 404' not in m.text else None)
        _fake_api(page, seen)

        def pick(key):
            page.click('#ks-bar-trigger')
            page.click(f'#ks-bar-menu [data-bar="{key}"]')

        # --- «Сроки годности»: «Все бары» -> all, бар полосы -> bar2; окно расхода датами
        page.goto(base + '/expiration')
        page.wait_for_function('() => document.getElementById("meta-info").textContent.includes("расход")')
        assert page.locator('#bar-select').count() == 0
        assert page.get_attribute('#kultura-strip', 'data-mode') == 'now'
        assert seen['expiration'] == ['all'], seen
        assert 'расход за 30 дней: 6 окт – 5 ноя 2025' in page.inner_text('#meta-info')
        pick('ligovskiy')
        page.wait_for_function('() => location.search.includes("bar=ligovskiy")')
        page.wait_for_timeout(300)
        assert seen['expiration'][-1] == 'bar2', seen
        pick('')
        page.wait_for_timeout(300)
        assert seen['expiration'][-1] == 'all', seen

        # --- «Краны»: все карточки; выбран бар — только его (Р9); окно активности датами
        def visible_cards():
            return page.eval_on_selector_all(
                '.tp-barcard', 'els => els.filter(e => getComputedStyle(e).display !== "none").map(e => e.dataset.key)')
        page.goto(base + '/taps')
        page.wait_for_function('() => document.querySelector(\'[data-field="activity-dates"]\').textContent !== ""')
        assert visible_cards() == ['bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya']
        assert page.inner_text('.tp-barcard[data-key="bolshoy"] [data-field="activity-dates"]') == '30 окт – 5 ноя 2025'
        seen['stats'] = []
        pick('kremenchugskaya')
        page.wait_for_timeout(300)
        assert visible_cards() == ['kremenchugskaya']
        assert seen['stats'] == ['bar3'], seen
        page.goto(base + '/taps')   # сервер прячет чужие карточки сразу
        assert visible_cards() == ['kremenchugskaya']

        # --- «Температура»: выбран бар (Кременчугская из cookie) — одна карточка; «Все бары» — все
        page.goto(base + '/temperature')
        page.wait_for_selector('#grid .temp-card')
        names = page.eval_on_selector_all('#grid .temp-card .bar-name', 'els => els.map(e => e.textContent)')
        assert names == ['Кременчугская'], names
        pick('')
        page.wait_for_timeout(200)
        assert page.locator('#grid .temp-card').count() == 4

        # --- «Фиды Яндекса»: при «Все бары» — последний бар страниц «по одному бару» или первый
        page.goto(base + '/yandex')
        page.wait_for_selector('#yf-bars [aria-selected="true"]')
        assert page.get_attribute('#yf-bars [aria-selected="true"]', 'data-id') == 'bar1'
        assert 'по одному бару: показан Большой пр. В.О' in page.inner_text('#ks-note')
        page.click('#yf-bars [data-id="bar4"]')   # вкладка — тот же выбор, что в полосе
        page.wait_for_function('() => document.getElementById("ks-bar-name").textContent === "Варшавская"')
        assert 'bar=varshavskaya' in page.url, page.url
        pick('ligovskiy')                          # бар в полосе — открыта его вкладка
        page.wait_for_function('() => document.querySelector(\'#yf-bars [aria-selected="true"]\').dataset.id === "bar2"')
        assert seen['feed'] == ['bar1', 'bar4', 'bar2'], seen
        page.goto(base + '/yandex')                # выбор сохранён для сайта
        page.wait_for_selector('#yf-bars [aria-selected="true"]')
        assert page.get_attribute('#yf-bars [aria-selected="true"]', 'data-id') == 'bar2'
        # Бар из ссылки на странице «по одному бару» — и последний бар таких страниц (Р4).
        page.goto(base + '/yandex?bar=kremenchugskaya')
        page.wait_for_selector('#yf-bars [aria-selected="true"]')
        single = {c['name']: c['value'] for c in page.context.cookies()}.get(scope.COOKIE_BAR_SINGLE)
        assert single == str(USER_ID) + '%3Akremenchugskaya', single

        browser.close()
    assert not errors, errors


if __name__ == '__main__':
    if not _browser_available():
        print('SKIP: Playwright или Chromium не установлены')
        sys.exit(0)
    test_now_pages_follow_the_strip()
    print('ok   test_now_pages_follow_the_strip')
