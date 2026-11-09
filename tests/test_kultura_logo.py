"""Логотипы сайта «kultura.os» и «kultura.research», которые рисуются как в рендере бренда (static/logo.js,
docs/brand.md).

Кадры считаются той же функцией, что в браузере (node + vm, без DOM). Без node тест кадров
пропускается (локально на Windows node может не стоять; в CI на ubuntu он есть).
"""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which('node')
LOGO = os.path.join(ROOT, 'static', 'logo.js')

# Загружает logo.js в песочнице с поддельным window/document (на странице логотипов нет —
# init ничего не делает) и печатает кадры: сколько букв (path) и прямоугольников (rect).
HARNESS = r'''
const fs = require('fs'), vm = require('vm');
const code = fs.readFileSync(process.argv[1], 'utf8');
const sandbox = {window: {}, document: {readyState: 'complete', querySelectorAll: () => [],
                 addEventListener: () => {}}, sessionStorage: {getItem: () => null, setItem: () => {}}};
sandbox.window.matchMedia = () => ({matches: false});
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const L = sandbox.window.KulturaLogo;
const count = (s, tag) => (s.match(new RegExp('<' + tag + '\\b', 'g')) || []).length;
const frame = (f, t) => { const s = f(t, 'm'); return {paths: count(s, 'path'), rects: count(s, 'rect'),
    orange: count(s, 'rect') ? (s.match(/fill="#FF4B0A"/g) || []).length : 0, current: s.includes('currentColor')}; };
const out = {wordmark: {}, lockup: {}, research: {},
             ends: {wordmark: L.views.wordmark.end, lockup: L.views.lockup.end, research: L.views.research.end},
             viewBoxes: {wordmark: L.views.wordmark.viewBox, lockup: L.views.lockup.viewBox,
                         research: L.views.research.viewBox},
             every: {wordmark: !!L.views.wordmark.every, lockup: !!L.views.lockup.every, research: !!L.views.research.every},
             labels: {wordmark: L.views.wordmark.label, research: L.views.research.label}};
for (const t of [0, 0.17, 0.18, 0.42, 0.70, 1.0, 1.16, 1.32, 5]) out.wordmark[t] = frame(L.wordmark, t);
for (const t of [0, 0.3, 0.58, 1.28, 1.32, 1.90, 5]) out.lockup[t] = frame(L.lockup, t);
for (const t of [0, 0.18, 0.70, 0.99, 1.0, 1.16, 2.12, 2.28, 5]) out.research[t] = frame(L.research, t);
process.stdout.write(JSON.stringify(out));
'''


@pytest.fixture(scope='module')
def frames():
    if NODE is None:
        pytest.skip('node не установлен')
    run = subprocess.run([NODE, '-e', HARNESS, LOGO], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_wordmark_types_in_fixed_cells_like_the_render(frames):
    w = frames['wordmark']
    assert frames['viewBoxes']['wordmark'] == '0 0 600 80'
    # «kultura» целыми состояниями: пусто, ku (0,18 с), kult (0,42), kultura и точка (0,70).
    assert [w[k]['paths'] for k in ('0', '0.17', '0.18', '0.42', '0.7')] == [0, 0, 2, 4, 7]
    assert w['0.42']['rects'] == 0 and w['0.7']['rects'] == 1 and w['0.7']['orange'] == 1, 'точка — с kultura'
    # «os» — по букве раз в 160 мс с 1,0 с; дальше логотип не меняется.
    assert [w[k]['paths'] for k in ('1', '1.16', '1.32', '5')] == [7, 8, 9, 9]
    assert frames['ends']['wordmark'] == pytest.approx(1.32)
    assert w['5']['current'], 'буквы — цвет текста темы'


def test_research_wordmark_types_like_the_header(frames):
    """Пустая беседа /research (решение владельца 2026-11-09: «динамичный логотип из надписи
    kultura.research»): тот же набор, что у шапки, — «kultura» группами, точка на 0,70 с, «research» по
    букве с 1,0 с; 16 ячеек по 60 — viewBox 0 0 960 80. Рисуется при каждом показе, не раз за сеанс."""
    r = frames['research']
    assert frames['viewBoxes']['research'] == '0 0 960 80'
    assert [r[k]['paths'] for k in ('0', '0.18', '0.7', '0.99')] == [0, 2, 7, 7]
    assert r['0.7']['rects'] == 1 and r['0.7']['orange'] == 1, 'точка — с kultura'
    assert [r[k]['paths'] for k in ('1', '1.16', '2.12', '2.28', '5')] == [7, 8, 14, 15, 15]
    assert frames['ends']['research'] == pytest.approx(1.0 + 8 * 0.16)
    assert r['5']['current'] and r['5']['orange'] == 1, 'буквы — цвет текста, точка — оранжевая'
    assert frames['every'] == {'wordmark': False, 'lockup': False, 'research': True}
    assert frames['labels'] == {'wordmark': 'kultura.os', 'research': 'kultura.research'}


def test_logo_letters_are_the_brand_outlines():
    """Буквы — контуры IBM Plex Mono Medium из набора бренда слово в слово (не рисовать заново)."""
    with open(os.path.join(ROOT, 'brand', 'kultura-grid-motion', 'source', 'assets', 'glyphs.json'),
              encoding='utf-8') as f:
        brand = json.load(f)['glyphs']
    with open(LOGO, encoding='utf-8') as f:
        font = json.loads(re.search(r'var FONT = (\{.*?\});\n', f.read()).group(1))['glyphs']
    assert set('kultura.osresearch') <= set(font), 'есть все буквы обоих названий'
    for ch, glyph in font.items():
        assert glyph['path'] == brand[ch]['path'], ch


def test_lockup_lands_mark_and_name_together(frames):
    lk = frames['lockup']
    assert lk['0']['paths'] == 0 and lk['0']['rects'] == 1, 'начало — один оранжевый квадрат'
    assert lk['1.28']['paths'] == 7, 'kultura — к 1,28 с'
    assert lk['1.9']['paths'] == 10 and lk['1.9']['orange'] == 2, 'os, буква k знака, точка и квадрат знака — на 1,90 с'
    assert frames['ends']['lockup'] == pytest.approx(1.95)
    assert lk['5'] == lk['1.9'], 'после приземления ничего не двигается'


def test_logo_is_on_every_entry_point():
    def read(*parts):
        with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
            return f.read()
    nav = read('templates', 'shared', 'nav.html')
    assert nav.count('data-kultura-logo="wordmark"') == 2 and '/static/logo.js' in nav
    login = read('templates', 'login.html')
    assert 'data-kultura-logo="lockup"' in login and '/static/logo.js?v={{ app_version }}' in login
    research = read('templates', 'research.html')
    assert research.count('data-kultura-logo="research"') == 3 and '/static/logo.js?v={{ app_version }}' in research, \
        '/research: крупный логотип пустой беседы, название в панели бесед и в верхней строке телефона'
    assert research.count('data-kultura-logo-still') == 2, 'мелкие названия — сразу готовые'
    consent = read('templates', 'mcp_consent.html')
    assert 'data-kultura-logo="lockup"' in consent and 'nonce="{{ csp_nonce }}" src="/static/logo.js' in consent, \
        'на странице согласия скрипты — только с nonce (CSP)'
    for text in (nav, login, consent, research):
        assert 'class="cursor"' not in text and 'class="prompt"' not in text, 'бренд — без курсора и «>»'
    code = read('static', 'logo.js')
    assert '#FF4B0A' in code and not re.search(r'[\U0001F300-\U0001FAFF]', code)
    favicon = read('static', 'favicon.svg')
    assert '#FF4B0A' in favicon and 'M88 740H197V293' in favicon, 'вкладка — знак kultura.os («k» и точка)'


@pytest.mark.skipif(NODE is None, reason='node не установлен')
def test_logo_script_syntax():
    run = subprocess.run([NODE, '--check', LOGO], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr


def test_tab_and_home_screen_icons_are_the_new_mark_and_not_cached():
    """2026-11-07: «не поменялось в значке вкладки» — у ссылок не было метки версии, а статика
    кэшируется на 30 дней; на телефоне и в манифесте стоял старый logo.jpg."""
    import glob
    from PIL import Image
    for path in glob.glob(os.path.join(ROOT, 'templates', '**', '*.html'), recursive=True):
        with open(path, encoding='utf-8') as f:
            text = f.read()
        if 'rel="icon"' not in text:
            continue
        rel = os.path.relpath(path, ROOT)
        assert 'href="/static/favicon.svg?v={{ app_version }}"' in text, rel
        assert 'favicon-32.png?v={{ app_version }}' in text and 'apple-touch-icon.png?v={{ app_version }}' in text, rel
        assert 'logo.jpg' not in text, rel
    sizes = {'favicon-32.png': 32, 'apple-touch-icon.png': 180, 'icon-192.png': 192, 'icon-512.png': 512}
    for name, size in sizes.items():
        assert Image.open(os.path.join(ROOT, 'static', name)).size == (size, size), name
    with open(os.path.join(ROOT, 'static', 'manifest.json'), encoding='utf-8') as f:
        manifest = json.load(f)
    assert manifest['short_name'] == 'kultura.os'
    for icon in manifest['icons']:
        assert icon['type'] == 'image/png' and os.path.exists(os.path.join(ROOT, icon['src'].lstrip('/')))


def test_schedule_board_uses_the_same_logo():
    with open(os.path.join(ROOT, 'static', 'js', 'schedule', 'screens.js'), encoding='utf-8') as f:
        code = f.read()
    assert '&gt; kultura.os' not in code and 'data-kultura-logo="wordmark"' in code
    assert 'window.KulturaLogo.init()' in code, 'новый борд — логотип дорисовывается'
