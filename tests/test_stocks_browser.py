"""
Сквозной браузерный тест страницы «Заказы и остатки» (/stocks) и справочника
поставщиков (/suppliers) после этапов 1–3 редизайна (2026-09-12).

Self-runnable: `py -3 tests/test_stocks_browser.py` (совместимо с pytest).

Поднимает Flask с stocks_bp + orders_bp + suppliers_bp на синтетических данных из
tests/test_stocks_routes.py (iiko не нужен), хранилища — временные файлы, и
ведёт Chromium через Playwright. Пропускается, если Playwright или Chromium
не установлены (в CI без браузера), поэтому не заменяет юнит-тесты, а
дополняет их: проверяет то, что видит управляющий.

Что проверяется:
- вход без ритуала по ?bar=, шапка, группы по поставщику с датами поставок,
  фраза-причина, заметка о новой формуле, свёрнутый блок «без движения»;
- раскрытие строки: формула в числах, последний приход;
- «Взять N» → черновик, липкая панель, счётчик, имя автора и желаемая дата;
- поиск и чипы; «Отправлено» → «в пути» на доске и отметка на карточке группы;
- «Приехало» с фактом по позициям, кнопка «Закрыть без сверки»;
- смена бара и ленивая вкладка; мобильная разметка без видимых скрытых строк;
- справочник: несохранённые правки переживают сохранение соседней карточки,
  срок и написание меняют доску, новый поставщик, ошибка проверки строкой.
"""

import importlib.util
import os
import shutil
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['SESSION_COOKIE_SECURE'] = '0'

import pytest  # noqa: E402

from flask import Flask, render_template  # noqa: E402
import routes.stocks as rs  # noqa: E402
import routes.orders as ro  # noqa: E402
import routes.suppliers as rsup  # noqa: E402
import core.stock_snapshot as ss  # noqa: E402
from routes.stocks import stocks_bp  # noqa: E402
from routes.orders import orders_bp  # noqa: E402
from routes.suppliers import suppliers_bp  # noqa: E402
from core.order_store import OrderStore  # noqa: E402
from core.supplier_directory import SupplierDirectory  # noqa: E402
from core import msk_time  # noqa: E402
from core.supplier_calendar import next_delivery_date  # noqa: E402
from extensions import BARS  # noqa: E402
import test_stocks_routes as fx  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMIUM = os.environ.get('STOCKS_TEST_CHROMIUM') or '/opt/pw-browsers/chromium'
WD = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')


def fmt_day(d):
    return f'{WD[d.weekday()]} {d.strftime("%d.%m")}'


def _browser_available():
    return importlib.util.find_spec('playwright') is not None and os.path.exists(CHROMIUM)


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.mark.skipif(not _browser_available(), reason='Playwright или Chromium не установлены')
def test_stocks_screen_end_to_end():
    from playwright.sync_api import sync_playwright

    tmp = tempfile.mkdtemp(prefix='stocks_browser_')
    store = OrderStore(os.path.join(tmp, 'orders.json'))
    directory = SupplierDirectory(os.path.join(tmp, 'suppliers.json'))
    snap = fx._snapshot()
    nom = fx._nomenclature()
    saved = {
        'rs': {k: getattr(rs, k) for k in ('get_stock_snapshot', 'get_stocks_nomenclature', 'get_barcode_map',
                                           '_CHZ_CACHE_FILE', 'get_order_store', 'get_supplier_directory')},
        'ss': ss.get_stocks_nomenclature,
        'ro': (ro.get_order_store, ro.current_user, ro.get_supplier_directory),
        'rsup': (rsup.get_supplier_directory, rsup.current_user),
    }
    user = {'login': 'anna', 'display_name': 'Анна'}
    rs.get_stock_snapshot = lambda *a, **k: snap
    rs.get_stocks_nomenclature = lambda *a, **k: nom
    ss.get_stocks_nomenclature = lambda *a, **k: nom
    rs.get_barcode_map = lambda *a, **k: {}
    rs._CHZ_CACHE_FILE = fx.NO_CHZ_FILE
    rs.taps_manager.get_bar_taps = fx._fake_bar_taps
    rs.get_order_store = lambda: store
    rs.get_supplier_directory = lambda: directory
    ro.get_order_store = lambda: store
    ro.current_user = lambda: user
    ro.get_supplier_directory = lambda: directory
    rsup.get_supplier_directory = lambda: directory
    rsup.current_user = lambda: user

    app = Flask('stocks_browser_test', template_folder=os.path.join(REPO, 'templates'),
                static_folder=os.path.join(REPO, 'static'))
    app.register_blueprint(stocks_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(suppliers_bp)
    app.context_processor(lambda: {'current_user': {'display_name': 'Анна', 'is_admin': False}})
    app.add_url_rule('/stocks', 'stocks', lambda: render_template('stocks.html', bars=BARS))
    app.add_url_rule('/suppliers', 'suppliers', lambda: render_template('suppliers.html'))
    app.add_url_rule('/api/connection-status', 'conn', lambda: {'status': 'connected'})

    port = _free_port()
    threading.Thread(target=lambda: app.run(port=port, use_reloader=False), daemon=True).start()
    time.sleep(1.5)
    BASE = f'http://127.0.0.1:{port}'
    # ожидаемая дата отправки считается от реального «сегодня» (московского), а не от даты снимка
    MAI_EXPECTED = fmt_day(next_delivery_date(msk_time.today(), 2))

    try:
        _scenario(sync_playwright, BASE, MAI_EXPECTED, store, directory)
    finally:
        for k, v in saved['rs'].items():
            setattr(rs, k, v)
        rs.taps_manager.__dict__.pop('get_bar_taps', None)
        ss.get_stocks_nomenclature = saved['ss']
        ro.get_order_store, ro.current_user, ro.get_supplier_directory = saved['ro']
        rsup.get_supplier_directory, rsup.current_user = saved['rsup']
        shutil.rmtree(tmp, ignore_errors=True)


def _scenario(sync_playwright, BASE, MAI_EXPECTED, store, directory):
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM, headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
        # 400 от намеренно неверного сохранения справочника — ожидаемый ответ, не ошибка страницы
        page.on('console', lambda m: errors.append(f'console.{m.type}: {m.text}')
                if m.type == 'error' and 'status of 400' not in m.text else None)
        page.on('dialog', lambda d: d.accept())

        def tab(name):
            page.click(f'button.tab:has-text("{name}")')

        # 1. Вход без ритуала: ?bar= → доска грузится сама, бар запоминается в URL
        page.goto(BASE + '/stocks?bar=' + fx.BAR_LIG)
        page.wait_for_selector('#order-board-content', state='visible')
        assert page.input_value('#bar-select') == fx.BAR_LIG
        meta = page.inner_text('#ob-meta')
        assert fx.BAR_LIG in meta and 'остатки iiko' in meta and 'ср 05.11' in meta, meta
        groups = page.eval_on_selector_all('#ob-groups .ob-group h3', 'els => els.map(e => e.textContent)')
        assert groups[0] == 'Лента', groups          # critical P_NEG первым
        assert 'ООО "Май"' in groups, groups
        head = page.inner_text('#ob-groups .ob-group:has-text(\'ООО "Май"\') .ob-group-head')
        assert 'поставка пт 07.11, следующая пн 10.11' in head and 'срок 2 дн.' in head and 'по умолчанию' not in head, head
        lenta_head = page.inner_text('#ob-groups .ob-group:has-text("Лента") .ob-group-head')
        assert 'срок 1 дн.' in lenta_head, lenta_head
        # причина и кнопка «Взять 8» у P_BOTTLE
        row = page.locator(f'#ob-groups tr.ob-row:has(input[data-product-id="{fx.P_BOTTLE}"])')
        assert 'до поставки пн 10.11 нужно 12 шт (1.5 в день × 8 дн. с запасом), есть 4: заказать 8 к пт 07.11' in row.inner_text()
        # заметка о новой формуле видна и прячется по «Понятно»
        assert page.locator('#ob-note').is_visible()
        page.click('#ob-note button')
        assert page.locator('#ob-note').is_hidden()
        assert row.locator('.ob-take').inner_text() == 'Взять 8'
        # отрицательный остаток — фраза «проверить учёт», в decide
        neg = page.locator(f'#ob-groups tr.ob-row:has(input[data-product-id="{fx.P_NEG}"])')
        assert 'проверить учёт' in neg.inner_text()
        # блок «без движения» свёрнут и содержит P_IDLE
        idle_summary = page.inner_text('#ob-idle-summary')
        assert idle_summary.startswith('Без движения или редко (2)'), idle_summary
        # хватающие позиции скрыты, пока не включён переключатель
        assert page.locator(f'#ob-groups input[data-product-id="{fx.P_NEW}"]').count() == 0
        page.check('#ob-show-all')
        page.wait_for_selector(f'#ob-groups input[data-product-id="{fx.P_NEW}"]', state='attached')
        page.uncheck('#ob-show-all')
    
        # 2. Раскрытие строки: формула с числами и последний приход
        page.click(f'#ob-groups tr.ob-row:has(input[data-product-id="{fx.P_BOTTLE}"]) .ob-name')
        detail = page.locator(f'tr.ob-detail[data-detail-for="{fx.P_BOTTLE}"]')
        page.wait_for_function(f'() => !document.querySelector(\'tr.ob-detail[data-detail-for="{fx.P_BOTTLE}"]\').hidden')
        dt = detail.inner_text()
        assert 'Нужно 12 шт = 1.5 в день × (5 дн.' in dt and 'Последний приход пн 06.10: 20 шт' in dt and 'продажи 45' in dt, dt

        # 3. «Взять 8» → черновик, липкая панель, счётчик на вкладке, кнопка «Взять» прячется
        row.locator('.ob-take').click()
        page.wait_for_function(f'() => document.querySelector(\'#ob-groups input[data-product-id="{fx.P_BOTTLE}"]\').value === "8"')
        page.wait_for_function('() => document.querySelector("#ob-sticky").classList.contains("visible")')
        assert 'Заказ: 1 поз. · 1 поставщик' in page.inner_text('#ob-sticky')
        # черновик показывает имя автора и желаемую дату; текст уже с датой
        assert 'Анна' in page.inner_text('#order-drafts .order-card .order-meta')
        assert f'Желаемая поставка: {MAI_EXPECTED}' in page.input_value('#order-drafts .order-text')
        assert page.inner_text('#order-tab-count') == '1'
        assert row.locator('.ob-take').is_hidden()

        # 4. Поиск и чипы фильтруют; «Взять все рекомендации» кладёт видимые
        page.fill('#ob-search', 'кола')
        page.wait_for_function('() => document.querySelectorAll("#ob-groups tr.ob-row").length === 0')
        page.fill('#ob-search', '')
        page.click('#ob-chips .chip[data-kind="draft"]')
        page.wait_for_function('() => document.querySelectorAll("#ob-groups tr.ob-row").length === 0')   # кеги: рекомендаций нет
        page.click('#ob-chips .chip[data-kind=""]')
        page.wait_for_function('() => document.querySelectorAll("#ob-groups tr.ob-row").length >= 2')

        # 5. К отправке → Отправлено → доска: «в пути 8», фраза in_transit
        page.click('#ob-sticky button')
        page.wait_for_function('() => document.querySelectorAll("#order-drafts .order-card").length === 1')
        assert not page.locator('#ob-sticky').evaluate('el => el.classList.contains("visible")')
        page.click('#order-drafts .order-card button:has-text("Отправлено поставщику")')
        page.wait_for_function('() => document.querySelectorAll("#order-open .order-card").length === 1')
        tab('К заказу')
        page.wait_for_function(f'() => {{ const r = document.querySelector(\'#ob-groups tr.ob-row:has(input[data-product-id="{fx.P_BOTTLE}"])\'); return !r; }}')
        page.check('#ob-show-all')
        page.wait_for_selector(f'#ob-groups tr.ob-row:has(input[data-product-id="{fx.P_BOTTLE}"])', state='attached')
        txt = page.inner_text(f'#ob-groups tr.ob-row:has(input[data-product-id="{fx.P_BOTTLE}"])')
        assert 'в пути 8' in txt and 'с ним хватит до поставки пн 10.11' in txt, txt
        # на карточке группы видно, что коллега уже отправил заказ
        group_head = page.inner_text('#ob-groups .ob-group:has-text(\'ООО "Май"\') .ob-group-head')
        assert 'отправлено' in group_head and 'Анна' in group_head and f'ожидается {MAI_EXPECTED}' in group_head, group_head
        page.uncheck('#ob-show-all')

        # «Приехало» с фактом: форма, правим количество, подтверждаем; «Закрыть без сверки» есть
        tab('К отправке')
        page.click('#order-open button:has-text("Приехало")')
        page.wait_for_selector('#order-open .recv-form input[data-recv-product]', state='visible')
        page.fill('#order-open .recv-form input[data-recv-product]', '6')
        page.click('#order-open button:has-text("Подтвердить приёмку")')
        page.wait_for_function('() => document.querySelector("#order-open .order-status.received") !== null')
        assert '(приехало 6)' in page.inner_text('#order-open .order-card')
        assert page.locator('#order-open button:has-text("Закрыть без сверки")').count() == 1
        tab('К заказу')

        # 6. Смена бара: фильтр над снимком; поздний ответ не ломает; вкладка Фасовка грузится лениво
        page.select_option('#bar-select', fx.BAR_BOL)
        page.wait_for_function(f'() => document.querySelector("#ob-meta").textContent.includes("{fx.BAR_BOL}")')
        assert 'bar=' in page.url, page.url
        assert page.locator('#bottles-content').is_hidden()
        tab('Фасовка')
        page.wait_for_selector('#bottles-content', state='visible')
        tab('К заказу')

        # 7. Мобильная разметка: карточки без заголовка таблицы; скрытые подробности не показываются
        page.set_viewport_size({'width': 400, 'height': 800})
        page.wait_for_timeout(300)
        thead_visible = page.locator('#ob-groups .ob-table thead').first.is_visible()
        assert not thead_visible
        # подробности P_BOTTLE были раскрыты раньше: закрываем и проверяем, что скрытые строки не видны
        page.click(f'#ob-groups tr.ob-row:has(input[data-product-id="{fx.P_BOTTLE}"]) .ob-name')
        page.wait_for_function(f'() => document.querySelector(\'tr.ob-detail[data-detail-for="{fx.P_BOTTLE}"]\').hidden')
        assert page.locator('#ob-groups tr.ob-detail[hidden]').count() >= 1
        hidden_visible = page.evaluate('() => [...document.querySelectorAll("#ob-groups tr.ob-detail[hidden]")].filter(tr => getComputedStyle(tr).display !== "none").length')
        assert hidden_visible == 0, hidden_visible
        page.set_viewport_size({'width': 1280, 'height': 900})

        # 8. Справочник: изменить срок Ленты → на доске «срок 3 дн.» и другая дата
        # Сначала: правки в другой карточке переживают сохранение соседней
        page.goto(BASE + '/suppliers')
        page.wait_for_selector('.supplier')
        assert 'стартовый набор' in page.inner_text('#stored-status')
        metro = page.locator('.supplier[data-name="Метро"]')
        metro.locator('[data-field="note"]').fill('черновик заметки')
        metro.locator('[data-field="note"]').dispatch_event('input')
        lenta0 = page.locator('.supplier[data-name="Лента"]')
        lenta0.locator('[data-action="save"]').click()
        page.wait_for_function('() => document.querySelector("#banner").textContent.includes("Сохранено")')
        assert page.locator('.supplier[data-name="Метро"] [data-field="note"]').input_value() == 'черновик заметки'
        assert 'несохранённые' in page.inner_text('.supplier[data-name="Метро"] [data-role="status"]')
        page.wait_for_selector('.supplier')
        assert page.locator('.unmapped').count() == 1 and 'ИП Ромашка' in page.inner_text('.unmapped')
        card = page.locator('.supplier[data-name="Лента"]')
        card.locator('[data-field="lead_time_days"]').fill('3')
        card.locator('[data-action="save"]').click()
        page.wait_for_function('() => document.querySelector("#banner").textContent.includes("Сохранено")')
        assert page.inner_text('#stored-status') == ''
        # привязать категорию ИП Ромашка к Ленте как написание
        row_u = page.locator('.unmapped:has-text("ИП Ромашка")')
        row_u.locator('select').select_option('Лента')
        row_u.locator('[data-action="alias"]').click()
        page.wait_for_function('() => document.querySelector("#banner").textContent.includes("написание")')
        assert 'ИП Ромашка' in page.locator('.supplier[data-name="Лента"] [data-field="aliases"]').input_value()
        page.wait_for_function('() => document.querySelector("#unmapped").textContent.includes("Все категории привязаны")')
        # завести нового поставщика вручную
        page.fill('#new-name', 'Фёст')
        page.click('button:has-text("Добавить поставщика")')
        page.wait_for_selector('.supplier[data-name="Фёст"]')
        # ошибка валидации показывается в строке карточки, а не alert
        fest = page.locator('.supplier[data-name="Фёст"]')
        fest.locator('[data-field="lead_time_days"]').fill('99')
        fest.locator('[data-action="save"]').click()
        page.wait_for_function('() => document.querySelector(\'.supplier[data-name="Фёст"] [data-role="status"]\').textContent.includes("Срок поставки")')
    
        page.goto(BASE + '/stocks?bar=' + fx.BAR_LIG)
        page.wait_for_selector('#order-board-content', state='visible')
        lenta_head = page.inner_text('#ob-groups .ob-group:has-text("Лента") .ob-group-head')
        assert 'срок 3 дн.' in lenta_head and 'поставка пн 10.11' in lenta_head, lenta_head
        # соус (ИП Ромашка) теперь в группе Лента: кг не бывает slow, хватает → виден с переключателем
        page.check('#ob-show-all')
        page.wait_for_selector(f'#ob-groups .ob-group:has-text("Лента") input[data-product-id="{fx.P_SAUCE}"]', state='attached')
        lenta_txt = page.inner_text('#ob-groups .ob-group:has-text("Лента")')
        assert 'Соус Барбекю' in lenta_txt and 'хватит на 50 дн.' in lenta_txt, lenta_txt

        browser.close()

    assert not errors, errors
    assert [(o['supplier'], o['status']) for o in store.list_orders(days=365)] == [('ООО "Май"', 'received')]
    assert {s['name'] for s in directory.list() if s.get('updated_at')} == {'Лента', 'Фёст'}


if __name__ == '__main__':
    if not _browser_available():
        print('SKIP: Playwright или Chromium не установлены')
        sys.exit(0)
    test_stocks_screen_end_to_end()
    print('ok   test_stocks_screen_end_to_end')
