"""Страницы «на сейчас» на общей полосе «Бар и период» — этап 6 плана единого виджета
(docs/planning/period-widget-rollout.md, решения владельца 2026-11-01).

Проверяется по настоящим маршрутам (без app.py, iiko и сети):
- каждая страница объявляет полосу с нужным режимом: mode='now'; бар — all (сроки,
  температура), single (склад, фиды Яндекса), none (меню, приёмка, «Связи с Untappd» —
  в tests/test_taps_page.py вместе с кранами);
- своих выборов бара у страниц нет (#bar-select, списки bar1…bar4);
- карточка заголовка у температуры и сроков — на общем месте: своего контейнера 1200 px и
  отступа 32 px нет;
- окна без выбора подписаны датами: окно цен меню (105 дней) — из той же функции, что у
  кнопки «Обновить цены из iiko»;
- скрипты страниц берут бар из полосы и переводят ключ по таблице баров.
"""
import json
import os
import re
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402

from core import periods, scope  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_ID = 7


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


@pytest.fixture
def client(monkeypatch):
    import routes.expiration as rexp
    import routes.menu_editor as rme
    import routes.pages as rp
    import routes.receiving as rrec
    import routes.temperature as rtemp
    import routes.yml_feeds as ryml

    monkeypatch.setattr(scope, '_current_user_id', lambda: USER_ID)
    app = Flask('now_pages_strip', template_folder=os.path.join(ROOT, 'templates'))
    for bp in (rp.pages_bp, rexp.expiration_bp, rtemp.temperature_bp, rme.menu_editor_bp,
               rrec.receiving_bp, ryml.yml_bp):
        app.register_blueprint(bp)
    scope.init_scope(app)
    return app.test_client()


def _strip(html):
    match = re.search(r'window\.KULTURA_STRIP = (\{.*?\});</script>', html)
    assert match, 'на странице нет полосы «Бар и период»'
    return json.loads(match.group(1))


@pytest.mark.parametrize('path, bar_mode', [
    ('/stocks', 'single'),
    ('/expiration', 'all'),
    ('/temperature', 'all'),
    ('/yandex', 'single'),
    ('/menu/', 'none'),
    ('/menu/edit', 'none'),
    ('/receiving', 'none'),
    ('/receiving/review', 'none'),
])
def test_page_declares_now_strip(client, path, bar_mode):
    response = client.get(path)
    html = response.get_data(as_text=True)
    assert response.status_code == 200, path
    config = _strip(html)
    assert (config['mode'], config['barMode']) == ('now', bar_mode), path
    assert 'id="kultura-strip" data-mode="now"' in html
    assert '<span class="kp-title">Сейчас</span>' in html
    # своих выборов бара нет: ни селекта, ни списка bar1…bar4 / имён iiko в <option>
    assert 'id="bar-select"' not in html, path
    assert not re.search(r'<option value="(bar[1-4]|all|Лиговский)"', html), path


def test_single_bar_pages_show_last_single_bar_with_note(client):
    """При «Все бары» на сайте — последний бар страниц «по одному бару» с подписью (ответ Р4)."""
    client.set_cookie(scope.COOKIE_BAR, f'{USER_ID}:all')
    client.set_cookie(scope.COOKIE_BAR_SINGLE, f'{USER_ID}:varshavskaya')
    for path in ('/stocks', '/yandex'):
        html = client.get(path).get_data(as_text=True)
        assert 'id="ks-bar-name">Варшавская<' in html, path
        assert 'по одному бару: показан Варшавская' in html, path
        assert 'data-bar=""' not in html, 'в списке нет «Все бары»'
    # страница со всеми барами показывает «Все бары»
    assert 'id="ks-bar-name">Все бары<' in client.get('/expiration').get_data(as_text=True)


def test_stocks_old_link_with_iiko_name_opens_that_bar(client):
    """Старые ссылки склада ?bar=<имя iiko> — синоним ключа: полоса открывается на этом баре."""
    config = _strip(client.get('/stocks?bar=Лиговский').get_data(as_text=True))
    assert (config['bar'], config['barSource']) == ('ligovskiy', 'url')
    assert {b['key']: b['iiko_name'] for b in config['bars']}['ligovskiy'] == 'Лиговский'


def test_bar_free_pages_label_the_bar(client):
    menu = client.get('/menu/').get_data(as_text=True)
    assert 'id="ks-bar-name">Все бары<' in menu and 'id="ks-bar-hint">вся сеть<' in menu
    receiving = client.get('/receiving').get_data(as_text=True)
    assert 'id="ks-bar-name">Склад<' in receiving and 'id="ks-bar-hint">распределительный<' in receiving
    assert 'disabled title="Страница на бары не делится"' in receiving


def test_header_card_uses_the_common_container():
    """Температура и сроки — без своего контейнера: заголовок там же, где на дашборде."""
    for name in ('temperature.html', 'expiration.html'):
        css = _read('templates', name)
        assert 'max-width: 1200px' not in css, name
        assert 'padding: 32px 20px 64px' not in css, name


def test_menu_price_window_is_labelled_with_dates(client, monkeypatch):
    from core import menu_pricing
    assert menu_pricing.PRICE_WINDOW_DAYS == 105
    assert menu_pricing.price_window(date(2026, 11, 1)) == ('2026-07-19', '2026-11-01')
    date_from, date_to = menu_pricing.price_window()
    label = periods.period_title('custom', date.fromisoformat(date_from), date.fromisoformat(date_to))
    for path in ('/menu/', '/menu/edit'):
        html = client.get(path).get_data(as_text=True)
        assert f'за 105 дней: {label}' in html, path
    # кнопка берёт продажи за то же окно
    calls = []

    def fake_fetch(date_from, date_to_incl, **kwargs):
        calls.append((date_from, date_to_incl))
        raise RuntimeError('iiko недоступна в тесте')
    monkeypatch.setattr(menu_pricing, 'fetch_sales_raw', fake_fetch)
    with pytest.raises(RuntimeError):
        menu_pricing.refresh_prices([])
    assert calls == [(date_from, date_to)]


def test_page_scripts_take_the_bar_from_the_strip():
    stocks = _read('templates', 'stocks.html')
    assert "localStorage.getItem(LEGACY_BAR_KEY)" in stocks and "const LEGACY_BAR_KEY = 'stocks.bar'" in stocks
    assert 'localStorage.setItem' not in stocks.split("const LEGACY_BAR_KEY")[1].split('async function loadStocks')[0], \
        'прежний ключ только читается для перехода'
    assert 'info.iiko_name' in stocks and "KStrip.onChange(function (e) { if (e.type === 'bar') loadStocks(); });" in stocks
    assert 'windowLabel(data.window_days, data.window_from, data.window_to)' in stocks
    expiration = _read('templates', 'expiration.html')
    assert "param: info.bar_id" in expiration and "{ param: 'all', name: 'Все бары' }" in expiration
    temperature = _read('templates', 'temperature.html')
    assert 'HIST_ORDER.filter(barVisible)' in temperature and "renderGrid();" in temperature
    yml = _read('static', 'js', 'yml_feeds', 'page.js')
    assert 'strip.setBar(key)' in yml and 'feedIdFor(strip ? strip.get().bar : null)' in yml
