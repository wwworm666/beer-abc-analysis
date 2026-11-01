"""
Шрифт сайта и метки версии у статики (2026-11-01, владелец: «Это что за шрифт? Откуда?»).

Self-runnable: `py -3 tests/test_site_fonts.py` (совместимо с pytest).

На телефоне владельца сайт шёл «печатной машинкой»: IBM Plex Mono (четыре TTF по ~135 КБ) не
был загружен, а запасной «Courier New» Android подменяет шрифтом Cutive Mono без кириллицы —
цифры шли машинкой, буквы системным шрифтом. Вдобавок Caddy разрешает браузеру 30 дней не
перепроверять файлы /static/: стили без метки ?v= после выпуска месяц оставались старыми.

Проверяется:
1. основной список шрифтов (--font-family) — без «Courier New», в конце monospace;
2. fonts.css: начертания 400/500/600/700, woff2 первым, все файлы есть, woff2 лёгкие;
3. в woff2 есть кириллица, ₽, №, тире, кавычки и стрелки (если стоят fonttools и brotli);
4. каждая ссылка шаблона на свои CSS и JS в /static/ — с ?v= (кроме библиотек и карточек
   меню: их встраивает routes/menu_editor._inline_assets по адресу без метки);
5. предзагрузка шрифта в шаблонах указывает на существующий файл.
"""

import glob
import importlib.util
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEIGHTS = (400, 500, 600, 700)
WOFF2_MAX_BYTES = 40 * 1024          # сейчас ~19 КБ; TTF — ~135 КБ
# Шаблоны, которые сайт не показывает (удаление — отдельной правкой, docs/CHANGELOG.md 2026-11-01).
UNUSED_TEMPLATES = {'templates/discounts.html', 'templates/taps.html'}
STATIC_LINK = re.compile(r'''(?:href|src)=["'](/static/(?!libs/|menu/)[^"']+?\.(?:css|js))(\?[^"']*)?["']''')
NEEDED = 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя0123456789%₽№–—«»…→←↑↓'


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _font_faces():
    css = _read('static/dashboard/styles/fonts.css')
    faces = []
    for block in re.findall(r'@font-face\s*\{(.*?)\}', css, re.S):
        family = re.search(r"font-family:\s*'([^']+)'", block).group(1)
        weight = int(re.search(r'font-weight:\s*(\d+)', block).group(1))
        urls = re.findall(r"url\('([^']+)'\)", block)
        faces.append({'family': family, 'weight': weight, 'urls': urls, 'block': block})
    return faces


def test_main_font_stack_has_no_courier():
    css = _read('static/dashboard/styles/variables.css')
    stack = re.search(r'--font-family:\s*([^;]+);', css).group(1)
    assert stack.startswith("'IBM Plex Mono'"), stack
    assert 'courier' not in stack.lower(), 'Courier New на Android = Cutive Mono без кириллицы: ' + stack
    assert stack.rstrip().endswith('monospace'), stack


def test_font_faces_woff2_first_and_files_exist():
    faces = _font_faces()
    assert sorted(f['weight'] for f in faces) == list(WEIGHTS)
    for face in faces:
        assert face['family'] == 'IBM Plex Mono'
        assert face['urls'][0].endswith('.site.woff2'), face['urls']
        assert "format('woff2')" in face['block']
        assert 'font-display: swap' in face['block']
        for url in face['urls']:
            path = os.path.join(ROOT, url.lstrip('/'))
            assert os.path.isfile(path), url
        size = os.path.getsize(os.path.join(ROOT, face['urls'][0].lstrip('/')))
        assert size < WOFF2_MAX_BYTES, '%s: %d байт' % (face['urls'][0], size)


@pytest.mark.skipif(importlib.util.find_spec('fontTools') is None or importlib.util.find_spec('brotli') is None,
                    reason='нужны fonttools и brotli (чтение woff2)')
def test_woff2_covers_site_text():
    from fontTools.ttLib import TTFont
    for face in _font_faces():
        cmap = TTFont(os.path.join(ROOT, face['urls'][0].lstrip('/'))).getBestCmap()
        missing = ''.join(ch for ch in NEEDED if ord(ch) not in cmap)
        assert not missing, '%s: нет «%s»' % (face['urls'][0], missing)


def test_every_own_static_link_is_versioned():
    bad = []
    for path in sorted(glob.glob(os.path.join(ROOT, 'templates', '**', '*.html'), recursive=True)):
        rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
        if rel in UNUSED_TEMPLATES:
            continue
        with open(path, encoding='utf-8') as f:
            html = f.read()
        for url, query in STATIC_LINK.findall(html):
            if not query or 'v=' not in query:
                bad.append('%s: %s' % (rel, url))
    assert not bad, 'без ?v= браузер до 30 дней держит старый файл (Caddyfile):\n' + '\n'.join(bad)


def test_font_preload_points_to_existing_woff2():
    found = 0
    for path in glob.glob(os.path.join(ROOT, 'templates', '**', '*.html'), recursive=True):
        with open(path, encoding='utf-8') as f:
            html = f.read()
        for tag in re.findall(r'<link rel="preload"[^>]*as="font"[^>]*>', html):
            found += 1
            href = re.search(r'href="([^"]+)"', tag).group(1)
            assert os.path.isfile(os.path.join(ROOT, href.lstrip('/'))), href
            assert 'crossorigin' in tag and 'type="font/woff2"' in tag, tag
    assert found >= 30, 'предзагрузка шрифта пропала из шаблонов: %d' % found


if __name__ == '__main__':
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('ok  ', name)
            except pytest.skip.Exception as e:
                print('skip', name, e)
            except AssertionError as e:
                failed += 1
                print('FAIL', name, e)
    sys.exit(1 if failed else 0)
