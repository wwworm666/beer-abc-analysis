"""Логотип сайта «kultura.os», который рисуется как в рендере бренда (static/logo.js, docs/brand.md).

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
const out = {wordmark: {}, lockup: {}, ends: {wordmark: L.views.wordmark.end, lockup: L.views.lockup.end},
             viewBoxes: {wordmark: L.views.wordmark.viewBox, lockup: L.views.lockup.viewBox}};
for (const t of [0, 0.17, 0.18, 0.42, 0.70, 1.0, 1.16, 1.32, 5]) out.wordmark[t] = frame(L.wordmark, t);
for (const t of [0, 0.3, 0.58, 1.28, 1.32, 1.90, 5]) out.lockup[t] = frame(L.lockup, t);
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
    consent = read('templates', 'mcp_consent.html')
    assert 'data-kultura-logo="lockup"' in consent and 'nonce="{{ csp_nonce }}" src="/static/logo.js' in consent, \
        'на странице согласия скрипты — только с nonce (CSP)'
    for text in (nav, login, consent):
        assert 'class="cursor"' not in text and 'class="prompt"' not in text, 'бренд — без курсора и «>»'
    code = read('static', 'logo.js')
    assert '#FF4B0A' in code and not re.search(r'[\U0001F300-\U0001FAFF]', code)
    favicon = read('static', 'favicon.svg')
    assert '#FF4B0A' in favicon and 'M88 740H197V293' in favicon, 'вкладка — знак kultura.os («k» и точка)'


@pytest.mark.skipif(NODE is None, reason='node не установлен')
def test_logo_script_syntax():
    run = subprocess.run([NODE, '--check', LOGO], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
