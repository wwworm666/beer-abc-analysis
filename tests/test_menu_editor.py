"""
Тесты редактора меню /menu (routes/menu_editor.py, core/menu_pricing.py) —
реестр объёмов разлива на карточке, в т.ч. 1,0 л (2026-09-18).

Self-runnable: `py -3 tests/test_menu_editor.py` (совместимо с pytest).

Хранилище подменяется временным файлом (routes.menu_editor._path); iiko не нужен.

Что проверяется:
- реестр VOLUMES: ключ = объём без запятой, порядок по возрастанию, 1,0 л есть;
  зеркала согласованы — JS-реестр в templates/menu_editor.html (ключ/подпись/
  поле, порядок, чекбокс и поле цены на форме) и PORTION_FIELD в core/menu_pricing;
- нормализация vols: только известные ключи, канонический порядок, не больше
  MAX_VOLS, пусто/мусор -> легаси-вид 0,25/0,4/0,5;
- sanitize/decorate: p10 сохраняется, колонки цен строятся по vols, «—» вместо
  пустой цены, флаг prices_wide при цене от 4 знаков;
- рендер карточки: класс nN/wide на секции цен, подписи объёмов;
- API: создание/обновление карточки с 1,0 л и чтение через /menu/card и /menu/print;
- цены из iiko: порция 1,0 (имя блюда «… (1,0)») заполняет p10 взвешенной модой.
"""

import atexit
import os
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
import routes.menu_editor as me  # noqa: E402
from routes.menu_editor import (  # noqa: E402
    menu_editor_bp, VOLUMES, DEFAULT_VOLS, MAX_VOLS, PRICE_FIELDS, ITEM_FIELDS,
    WIDE_PRICE_DIGITS, _normalize_vols, _sanitize, _decorate,
)

EDITOR_TEMPLATE = os.path.join(ROOT, 'templates', 'menu_editor.html')


@contextmanager
def _client():
    tmp = tempfile.mkdtemp(prefix='menu_editor_')
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    saved = me._path
    me._path = lambda: os.path.join(tmp, 'menu_cards.json')
    app = Flask('test_menu_editor',
                template_folder=os.path.join(ROOT, 'templates'),
                static_folder=os.path.join(ROOT, 'static'))
    app.register_blueprint(menu_editor_bp)
    try:
        yield app.test_client()
    finally:
        me._path = saved


# ---------------------------------------------------------------------------
# Реестр объёмов и его зеркала
# ---------------------------------------------------------------------------

def test_volumes_registry_has_one_litre_in_ascending_order():
    keys = [k for k, _, _ in VOLUMES]
    assert keys == ['025', '033', '04', '05', '10']
    labels = dict((k, lbl) for k, lbl, _ in VOLUMES)
    assert labels['10'] == '1,0'
    fields = dict((k, f) for k, _, f in VOLUMES)
    assert fields['10'] == 'p10'
    # ключ = подпись без запятой (0,5 -> 05, 1,0 -> 10)
    for key, label, field in VOLUMES:
        assert key == label.replace(',', ''), (key, label)
        assert field == 'p' + key, (key, field)
    # объёмы по возрастанию
    litres = [float(lbl.replace(',', '.')) for _, lbl, _ in VOLUMES]
    assert litres == sorted(litres)


def test_price_fields_cover_registry():
    assert set(PRICE_FIELDS) == {f for _, _, f in VOLUMES}
    for f in PRICE_FIELDS:
        assert f in ITEM_FIELDS, f
    assert 'p03' not in ITEM_FIELDS  # прежний вариант 0,3 убран


def test_js_registry_mirrors_server():
    """VOLUMES в JS редактора (живое превью) должен совпадать с серверным: ключ,
    подпись, поле и порядок; на форме есть чекбокс v-<key> и поле цены f-<field>."""
    src = open(EDITOR_TEMPLATE, encoding='utf-8').read()
    js = re.findall(r'\{\s*key:"(\w+)",\s*label:"([^"]+)",\s*field:"(\w+)"\s*\}', src)
    assert js == [tuple(v) for v in VOLUMES], js
    for key, _, field in VOLUMES:
        assert 'id="v-%s"' % key in src, key
        assert 'id="f-%s"' % field in src, field
    assert re.search(r'DEFAULT_VOLS\s*=\s*\["025","04","05"\],\s*MAX_VOLS\s*=\s*%d' % MAX_VOLS, src)
    assert re.search(r'WIDE_PRICE_DIGITS\s*=\s*%d;' % WIDE_PRICE_DIGITS, src)


def test_pricing_portion_map_mirrors_registry():
    from core.menu_pricing import PORTION_FIELD
    assert PORTION_FIELD[1.0] == 'p10'
    assert set(PORTION_FIELD.values()) == {f for _, _, f in VOLUMES}
    by_field = {f: float(lbl.replace(',', '.')) for _, lbl, f in VOLUMES}
    for vol, field in PORTION_FIELD.items():
        assert abs(by_field[field] - vol) < 1e-9, (vol, field)


# ---------------------------------------------------------------------------
# Нормализация vols
# ---------------------------------------------------------------------------

def test_normalize_vols_canonical_order_and_limits():
    assert _normalize_vols(['10', '025']) == ['025', '10']
    assert _normalize_vols(['10']) == ['10']
    assert _normalize_vols(['05', '10', '033']) == ['033', '05', '10']
    # больше MAX_VOLS -> первые по порядку объёма (самый большой отпадает)
    assert _normalize_vols(['10', '05', '04', '025']) == ['025', '04', '05']
    assert len(_normalize_vols([k for k, _, _ in VOLUMES])) == MAX_VOLS
    # неизвестные ключи игнорируются, пусто/мусор -> легаси-вид
    assert _normalize_vols(['10', '1', '1.0', 'xx']) == ['10']
    assert _normalize_vols(['xx']) == DEFAULT_VOLS
    assert _normalize_vols([]) == DEFAULT_VOLS
    assert _normalize_vols(None) == DEFAULT_VOLS
    assert _normalize_vols('10') == DEFAULT_VOLS
    assert DEFAULT_VOLS == ['025', '04', '05']


# ---------------------------------------------------------------------------
# sanitize / decorate
# ---------------------------------------------------------------------------

def test_sanitize_keeps_p10_and_defaults_it():
    item = _sanitize({'name': 'Тест', 'vols': ['10', '05'], 'p10': 1900, 'p05': 990})
    assert item['p10'] == 1900 and item['p05'] == 990
    assert item['vols'] == ['05', '10']
    assert item['p025'] is None and item['p033'] is None and item['p04'] is None
    legacy = _sanitize({'name': 'Старая', 'p025': 230, 'p04': 390, 'p05': 450})
    assert legacy['p10'] is None
    assert legacy['vols'] == DEFAULT_VOLS
    # PUT с base: поле цены не теряется, если в запросе его нет
    merged = _sanitize({'name': 'Новое имя'}, base=item)
    assert merged['p10'] == 1900 and merged['vols'] == ['05', '10']


def test_decorate_builds_servings_from_vols():
    d = _decorate({'name': 'Тест', 'vols': ['10', '025'], 'p025': 550, 'p10': 1900})
    assert [(s['vol'], s['price']) for s in d['servings']] == [('0,25', '550'), ('1,0', '1900')]
    assert d['prices_wide'] is True  # 1900 — 4 знака
    d = _decorate({'name': 'Тест', 'vols': ['10'], 'p10': None})
    assert [(s['vol'], s['price']) for s in d['servings']] == [('1,0', '—')]
    assert d['prices_wide'] is False
    d = _decorate({'name': 'Тест', 'vols': ['025', '05', '10'], 'p025': 230, 'p05': 450, 'p10': 850})
    assert d['prices_wide'] is False
    # цена хранится независимо от выбора колонок
    d = _decorate({'name': 'Тест', 'vols': ['05'], 'p05': 450, 'p10': 850})
    assert [s['vol'] for s in d['servings']] == ['0,5']
    assert d['p10'] == 850


# ---------------------------------------------------------------------------
# Рендер карточки и API
# ---------------------------------------------------------------------------

def _prices_section(html):
    m = re.search(r'<section class="(prices [^"]+)">(.*?)</section>', html, re.S)
    assert m, 'нет секции цен'
    cells = re.findall(r'<span class="vol">([^<]*)</span><span class="num">([^<]*)</span>', m.group(2))
    return m.group(1), cells


def test_card_render_marks_columns_and_wide_prices():
    with _client() as c:
        r = c.post('/menu/api/items', json={
            'name': 'Гулден Драк', 'vols': ['10', '05', '025'],
            'p025': 550, 'p05': 990, 'p10': 1900,
        })
        assert r.status_code == 201, r.data
        created = r.get_json()
        assert created['vols'] == ['025', '05', '10'] and created['p10'] == 1900
        cid = created['id']

        html = c.get('/menu/card?id=%d' % cid).get_data(as_text=True)
        cls, cells = _prices_section(html)
        assert cls == 'prices n3 wide'
        assert cells == [('0,25', '550'), ('0,5', '990'), ('1,0', '1900')]

        # две колонки, цена трёхзначная -> без wide
        r = c.put('/menu/api/items/%d' % cid, json={'vols': ['05', '10'], 'p10': 850})
        assert r.status_code == 200
        html = c.get('/menu/card?id=%d' % cid).get_data(as_text=True)
        cls, cells = _prices_section(html)
        assert cls == 'prices n2'
        assert cells == [('0,5', '990'), ('1,0', '850')]

        # одна колонка 1,0 без цены -> «—»
        r = c.put('/menu/api/items/%d' % cid, json={'vols': ['10'], 'p10': None})
        assert r.status_code == 200
        html = c.get('/menu/card?id=%d' % cid).get_data(as_text=True)
        cls, cells = _prices_section(html)
        assert cls == 'prices n1'
        assert cells == [('1,0', '—')]

        # список и печать всех карточек видят 1,0
        items = c.get('/menu/api/items').get_json()
        assert items[0]['vols'] == ['10'] and items[0]['p10'] is None
        html = c.get('/menu/print?filter=all').get_data(as_text=True)
        assert '<span class="vol">1,0</span>' in html


def test_legacy_card_without_vols_keeps_three_columns():
    with _client() as c:
        r = c.post('/menu/api/items', json={'name': 'ФестХаус Хеллес', 'p025': 230, 'p04': 390, 'p05': 450})
        cid = r.get_json()['id']
        html = c.get('/menu/card?id=%d' % cid).get_data(as_text=True)
        cls, cells = _prices_section(html)
        assert cls == 'prices n3'
        assert cells == [('0,25', '230'), ('0,4', '390'), ('0,5', '450')]


# ---------------------------------------------------------------------------
# Цены из iiko: порция 1,0
# ---------------------------------------------------------------------------

def test_prices_from_sales_fill_one_litre():
    import pandas as pd
    from core.menu_pricing import _prices_from_sub, prepare_sales_df
    raw = {'data': [
        # DishName, Store, дата, порций, сумма без скидки (unit = сумма/порции)
        {'DishName': 'ФестХаус Хеллес (0,5)', 'Store.Name': 'Лиговский', 'OpenDate.Typed': '2026-09-01',
         'DishAmountInt': 10, 'DishSumInt': 4500, 'DishDiscountSumInt': 0},
        {'DishName': 'ФестХаус Хеллес (1,0)', 'Store.Name': 'Лиговский', 'OpenDate.Typed': '2026-09-01',
         'DishAmountInt': 3, 'DishSumInt': 2550, 'DishDiscountSumInt': 0},
        {'DishName': 'ФестХаус Хеллес (1,0)', 'Store.Name': 'Варшавская', 'OpenDate.Typed': '2026-09-03',
         'DishAmountInt': 1, 'DishSumInt': 900, 'DishDiscountSumInt': 0},   # редкая цена — не мода
        {'DishName': 'ФестХаус Хеллес (1,0)', 'Store.Name': 'Лиговский', 'OpenDate.Typed': '2026-09-02',
         'DishAmountInt': 2, 'DishSumInt': 1700, 'DishDiscountSumInt': 0},
    ]}
    p = prepare_sales_df(raw)
    assert sorted(p['PortionVolume'].unique().tolist()) == [0.5, 1.0]
    sub = p[p['BeerNameNorm'] == p['BeerNameNorm'].iloc[0]]
    prices = _prices_from_sub(sub)
    assert prices == {'p05': 450, 'p10': 850}, prices
    assert isinstance(prices['p10'], int)


if __name__ == '__main__':
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('ok   ', name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print('FAIL ', name, '->', repr(e))
    sys.exit(1 if failed else 0)
