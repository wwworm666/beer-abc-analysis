"""
Мини-приложение «Графики» и PNG-карточка в настоящем Chromium (Playwright).

Пропускается, если нет Playwright или Chromium (в CI браузера нет; путь — TG_CHART_CHROMIUM
или /opt/pw-browsers/chromium, как в tests/test_stocks_browser.py).

Что проверяется:
- PNG всех фикстур рисуется (core/tg_chart_png.py): картинка 1290 px по ширине, длинная
  сторона не больше 2560, обе темы; без сети — все запросы страницы перехвачены;
- мини-приложение в «Telegram» (заглушка telegram-web-app.js отдаётся вместо telegram.org):
  ready() и expand() вызваны, цвет шапки и фона = фон страницы, initData уходит в заголовке
  Authorization: tma …, карточка рисуется, переключатель «Проценты» работает с HapticFeedback,
  событие themeChanged перекрашивает страницу; id приходит и из ?id=, и из start_param;
- официальный скрипт не загрузился (telegram.org недоступен): initData и тема берутся из
  #tgWebAppData и #tgWebAppThemeParams, график всё равно открывается;
- вне Telegram — «Откройте из Telegram»; человек не из чата графика — «Нет доступа к графику»;
- dev-страница: шесть карточек в обеих темах без ошибок.
"""
import importlib.util
import json
import os
import sys
import threading
from urllib.parse import quote, urlencode

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

from core import tg_charts  # noqa: E402
from core.mcp import db  # noqa: E402
from core.tg_chart_fixtures import FIXTURES  # noqa: E402
from test_tg_miniapp import OWNER, STRANGER, TOKEN, init_data, make_app  # noqa: E402

CHROMIUM = os.environ.get('TG_CHART_CHROMIUM') or '/opt/pw-browsers/chromium'


def _browser_available():
    return importlib.util.find_spec('playwright') is not None and os.path.exists(CHROMIUM)


pytestmark = pytest.mark.skipif(not _browser_available(), reason='Playwright или Chromium не установлены')

TG_STUB = """
window.__tgCalls = [];
window.__tgHandlers = {};
window.Telegram = { WebApp: {
  initData: %(init)s, initDataUnsafe: { start_param: %(start)s }, colorScheme: 'light', version: '8.0',
  isVersionAtLeast: function () { return true; },
  ready: function () { __tgCalls.push('ready'); },
  expand: function () { __tgCalls.push('expand'); },
  disableVerticalSwipes: function () { __tgCalls.push('swipes'); },
  setHeaderColor: function (c) { __tgCalls.push('header:' + c); },
  setBackgroundColor: function (c) { __tgCalls.push('bg:' + c); },
  onEvent: function (name, cb) { __tgHandlers[name] = cb; },
  HapticFeedback: { selectionChanged: function () { __tgCalls.push('haptic'); } }
} };
"""


@pytest.fixture
def server(tmp_path, monkeypatch):
    from werkzeug.serving import make_server
    db.set_db_path(str(tmp_path / 'mcp.db'))
    monkeypatch.setenv('TELEGRAM_MCP_BOT_TOKEN', TOKEN)
    monkeypatch.setenv('TG_CHART_CHROMIUM', CHROMIUM)
    app = make_app(debug=True)
    seen = []

    @app.before_request
    def remember_auth():
        from flask import request
        if request.path.startswith('/api/tg/'):
            seen.append(request.headers.get('Authorization', ''))

    srv = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield {'base': f'http://127.0.0.1:{srv.server_port}', 'seen': seen}
    srv.shutdown()
    db.set_db_path(None)


@pytest.fixture
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROMIUM, headless=True)
        yield b
        b.close()


def _page(browser, stub=None, color_scheme='light'):
    context = browser.new_context(viewport={'width': 390, 'height': 800}, color_scheme=color_scheme)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda exc: errors.append(str(exc)))

    def telegram(route):
        if stub is None:
            return route.abort()                 # telegram.org недоступен
        return route.fulfill(status=200, content_type='application/javascript', body=stub)
    page.route('https://telegram.org/**', telegram)
    return page, errors


def _saved(name='belgium'):
    return tg_charts.create(tg_charts.normalize(dict(FIXTURES)[name]), chat_id=str(OWNER))['id']


def test_png_renders_for_every_fixture(monkeypatch):
    from core import tg_chart_png
    monkeypatch.setenv('TG_CHART_CHROMIUM', CHROMIUM)
    for name, raw in FIXTURES:
        png = tg_chart_png.render_png(tg_charts.normalize(raw))
        assert png[:8] == b'\x89PNG\r\n\x1a\n', name
        width, height = int.from_bytes(png[16:20], 'big'), int.from_bytes(png[20:24], 'big')
        assert width == tg_chart_png.CARD_WIDTH_PX * tg_chart_png.DEVICE_SCALE or max(width, height) == 2560, name
        assert max(width, height) <= tg_chart_png.PHOTO_LONG_SIDE_MAX, name
    dark = tg_chart_png.render_png(tg_charts.normalize(dict(FIXTURES)['revenue']), theme='dark')
    assert dark[:8] == b'\x89PNG\r\n\x1a\n'


def test_mini_app_inside_telegram(server, browser):
    chart_id = _saved('belgium')
    data = init_data()
    stub = TG_STUB % {'init': json.dumps(data), 'start': json.dumps('')}
    page, errors = _page(browser, stub)
    page.goto(f'{server["base"]}/tg/chart?id={chart_id}')
    page.wait_for_selector('#card svg', timeout=15000)
    assert page.inner_text('#card h2') == 'Бельгия на розливе\n2–13 сен к 19–30 авг 2026 · Все'
    assert server['seen'] == ['tma ' + data], 'initData — в заголовке Authorization'
    calls = page.evaluate('window.__tgCalls')
    assert calls[:2] == ['bg:#FAF9F7', 'header:#FAF9F7'] and 'ready' in calls and 'expand' in calls
    assert 'swipes' in calls, 'свайп по графику не сворачивает окно'
    page.click('#card .seg button:has-text("Проценты")')
    page.wait_for_timeout(300)
    assert page.evaluate('window.__tgCalls').count('haptic') == 1
    assert page.inner_text('#card .unit') == '% к 19–30 авг'
    assert page.get_attribute('html', 'data-theme') == 'light'
    page.evaluate("Telegram.WebApp.colorScheme = 'dark'; __tgHandlers.themeChanged()")
    assert page.get_attribute('html', 'data-theme') == 'dark'
    assert 'bg:#151413' in page.evaluate('window.__tgCalls')
    page.click('#card details.tbl summary')
    assert '−100,0%' in page.inner_text('#card details.tbl')
    assert errors == []


def test_mini_app_from_group_link_uses_start_param(server, browser):
    chart_id = _saved('desserts')
    stub = TG_STUB % {'init': json.dumps(init_data(start_param=chart_id)), 'start': json.dumps(chart_id)}
    page, errors = _page(browser, stub)
    page.goto(f'{server["base"]}/tg/chart')
    page.wait_for_selector('#card svg', timeout=15000)
    assert page.inner_text('#card h2').startswith('Десерты, порции') and errors == []


def test_mini_app_without_official_script_reads_launch_params(server, browser):
    chart_id = _saved('revenue')
    theme = json.dumps({'bg_color': '#17212b', 'text_color': '#f5f5f5'})
    hash_part = urlencode({'tgWebAppData': init_data(), 'tgWebAppVersion': '8.0', 'tgWebAppPlatform': 'android',
                           'tgWebAppThemeParams': theme}, quote_via=quote)
    page, errors = _page(browser, stub=None)
    page.goto(f'{server["base"]}/tg/chart?id={chart_id}#{hash_part}')
    page.wait_for_selector('#card svg', timeout=15000)
    assert page.inner_text('#card h2').startswith('Выручка')
    assert page.get_attribute('html', 'data-theme') == 'dark', 'тёмный фон темы Telegram -> тёмная тема'
    assert errors == []


def test_mini_app_outside_telegram_and_for_strangers(server, browser):
    page, errors = _page(browser, stub=None)
    page.goto(f'{server["base"]}/tg/chart?id=' + 'A' * 22)
    page.wait_for_selector('#state b')
    assert page.inner_text('#state b') == 'Откройте из Telegram'
    assert server['seen'] == [], 'без initData сервер не спрашивают'
    chart_id = _saved()
    stub = TG_STUB % {'init': json.dumps(init_data(user_id=STRANGER)), 'start': json.dumps('')}
    page, errors = _page(browser, stub)
    page.goto(f'{server["base"]}/tg/chart?id={chart_id}')
    page.wait_for_function("document.querySelector('#state b').textContent === 'Нет доступа к графику'")
    assert 'участники чата' in page.inner_text('#state') and errors == []


def test_dev_page_both_themes(server, browser):
    for scheme in ('light', 'dark'):
        page, errors = _page(browser, color_scheme=scheme)
        page.goto(f'{server["base"]}/tg/chart/dev?theme={scheme}')
        page.wait_for_function("document.querySelectorAll('section.card svg').length === 6", timeout=15000)
        assert page.get_attribute('html', 'data-theme') == scheme
        assert [c.get_attribute('id') for c in page.query_selector_all('section.card')] == \
            ['liters', 'belgium', 'check', 'revenue', 'desserts', 'days']
        page.click('#days .seg button:has-text("7 дн")')
        page.wait_for_timeout(300)
        assert page.inner_text('#days .sum').startswith('24 сен – 30 сен 2026')
        assert errors == [], errors
