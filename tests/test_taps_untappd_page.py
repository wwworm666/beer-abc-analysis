"""Страница «Связи с Untappd» (/taps/untappd, решение владельца 2026-10-04).

Проверяется: страница открывается (статический путь главнее /taps/<bar_id>); шаблон,
скрипт и стили согласованы между собой и с API (узлы, которые ищет JS, эндпоинты
/api/untappd/*, классы tp-*); пояснения свёрнуты в «Как это работает»; без эмодзи;
строка таплиста, которую страница пересобирает при правке стиля по-русски и короткого
имени пивоварни, совпадает с серверной (core/untappd_live.preview -> core/taplist_post).
Паритет — через node, если он есть (в CI он есть). Без app.py и без сети.
"""
import copy
import json
import os
import re
import shutil
import subprocess

import pytest
from flask import Flask

from core import taplist_post
from core import untappd_live as ul

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_FILE = os.path.join(ROOT, 'static', 'js', 'taps', 'untappd.js')
NODE_TIMEOUT_SEC = 30
EMOJI_RE = re.compile('[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]')


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


TEMPLATE = _read('templates', 'taps_untappd.html')
JS = _read('static', 'js', 'taps', 'untappd.js')
CSS = _read('static', 'taps', 'taps.css')
ROUTES = _read('routes', 'taps.py')


def test_page_opens_and_is_not_a_bar():
    import routes.pages as rp
    app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'))
    app.register_blueprint(rp.pages_bp)
    app.context_processor(lambda: {'current_user': {'login': 'masha', 'is_admin': False}})
    response = app.test_client().get('/taps/untappd')
    html = response.get_data(as_text=True)
    assert response.status_code == 200 and 'Связи с Untappd' in html and 'Бар не найден' not in html
    assert '/static/js/taps/untappd.js?v=' + rp.APP_VERSION in html
    # у страниц кранов теперь есть версия для сброса кэша (Safari держит старые bar.js и taps.css)
    main = app.test_client().get('/taps').get_data(as_text=True)
    assert 'taps.css?v=' + rp.APP_VERSION in main and 'href="/taps/untappd"' in main


def test_script_template_styles_and_api_agree():
    ids = set(re.findall(r'id="([a-z0-9-]+)"', TEMPLATE))
    used = set(re.findall(r"\$\('([a-z0-9-]+)'\)", JS))
    assert used and used <= ids, sorted(used - ids)
    # эндпоинты, в которые ходит страница, есть в routes/taps.py
    for path in set(re.findall(r"'(/api/untappd/[a-z/]*[a-z])", JS)):
        assert "'" + path in ROUTES, path
    for action in set(re.findall(r"'/(confirm|reject|revoke)'", JS)):
        assert "'/api/untappd/proposals/<proposal_id>/" + action + "'" in ROUTES, action
    # каждый класс tp-*, который пишет скрипт, описан в стилях
    classes = set(re.findall(r'\btp-[a-z0-9-]+', ' '.join(re.findall(r"'([^'\n]*)'", JS)))) - ids
    missing = sorted(name for name in classes if not re.search(r'\.' + re.escape(name) + r'\b', CSS))
    assert not missing, missing
    # пояснения свёрнуты по умолчанию (принцип 1 в .claude/CLAUDE.md)
    assert '<details class="tp-how">' in TEMPLATE and '<summary>Как это работает</summary>' in TEMPLATE
    assert '<details class="tp-how" open' not in TEMPLATE and 'Почему эта карточка' in JS
    # данные карточек — только textContent: разметку из строк скрипт не собирает
    assert not re.search(r'\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write', JS)
    for name, text in (('template', TEMPLATE), ('js', JS), ('css', CSS)):
        assert not EMOJI_RE.search(text), name


def _cases():
    """(предпросмотр сервера, ввод «стиль по-русски», ввод «пивоварня в посте», ожидаемая
    строка). Ввод None — поля на странице нет (как в untappd.js: стиль — если у карточки
    есть стиль и его нет в словаре; пивоварня — если ни название, ни пивоварни нет в словаре)."""
    names = taplist_post.load_names(taplist_post.NAMES_PATH)
    known_style = sorted(names['styles'])[0]
    known_brewery = sorted(name for name, short in names['breweries'].items() if short)[0]
    own_name = sorted(names['beers'])[0]
    cards = [
        ('900001', {'beer_name': 'Oyster Stout', 'brewery': "Marston's Brewery (Wolverhampton & Dudley)",
                    'style': 'Stout - Oyster', 'abv_percent': 4.5}, {'style_ru': 'устричный стаут'}),
        ('900002', {'beer_name': 'Palm Spéciale', 'brewery': 'Palm Belgian Craft Brewers',
                    'style': known_style, 'abv_percent': 5.2}, {'brewery_short': 'Palm'}),
        ('900003', {'beer_name': 'Helles', 'brewery': known_brewery, 'style': 'Lager - Imaginary',
                    'abv_percent': 0}, {}),
        (own_name, {'beer_name': 'Whatever', 'brewery': 'Some Brewery', 'style': '', 'abv_percent': 6.25}, {}),
        ('900005', {'beer_name': 'Test', 'brewery': 'Tiny Brew Co', 'style': 'IPA - Imaginary',
                    'abv_percent': None}, {'style_ru': '', 'brewery_short': ''}),
    ]
    inputs = [(None, None), ('', ''), ('  светлое   пшеничное ', '  Big  Brew  '), ('лагер', 'palm'),
              ('стаут', 'OYSTER'), ('ипа', 'Test')]
    out = []
    for bid, card, proposed in cards:
        item = {'untappd_beer_id': bid, 'url': 'https://untappd.com/b/x/' + bid, 'card': card,
                'names': dict({'style_ru': '', 'brewery_short': None}, **proposed)}
        preview = ul.preview(item, names)
        style_field = bool(preview['style']) and not preview['style_from_dictionary']
        brewery_field = not preview['name_from_dictionary'] and not preview['brewery_from_dictionary'] \
            and bool(card['brewery'])
        for style_in, brewery_in in inputs:
            style_in = style_in if style_field else None
            brewery_in = brewery_in if brewery_field else None
            edited = copy.deepcopy(item)
            if style_in is not None:
                edited['names']['style_ru'] = ' '.join(style_in.split())
            if brewery_in is not None:
                edited['names']['brewery_short'] = ' '.join(brewery_in.split())
            out.append({'preview': preview, 'style': style_in, 'brewery': brewery_in,
                        'expected': ul.preview(edited, names)['line']})
    return out


_NODE_SCRIPT = r"""
const page = require(process.argv[1]);
let buf = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (d) => { buf += d; });
process.stdin.on('end', () => {
    const cases = JSON.parse(buf);
    process.stdout.write(JSON.stringify(cases.map((c) => page.composeLine(c.preview, c.style, c.brewery))));
});
"""


def test_page_line_matches_server_line():
    node = shutil.which('node')
    if not node:
        pytest.skip('node не найден — паритет строки страницы и сервера не проверить')
    cases = _cases()
    proc = subprocess.run([node, '-e', _NODE_SCRIPT, JS_FILE], input=json.dumps(cases, ensure_ascii=True),
                          capture_output=True, text=True, encoding='utf-8', timeout=NODE_TIMEOUT_SEC)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    mismatches = [(c['preview']['line'], c['style'], c['brewery'], c['expected'], line)
                  for c, line in zip(cases, got) if line != c['expected']]
    assert not mismatches, mismatches[:5]
    # без правок страница показывает ровно строку сервера
    assert all(line == c['preview']['line'] for c, line in zip(cases, got) if c['style'] is None and c['brewery'] is None)
    # набор задел все ветки: пивоварня в названии, пустая пивоварня, имя из словаря, без стиля
    lines = {c['expected'] for c in cases}
    assert 'Palm Spéciale — ' + taplist_post.style_ru(cases[6]['preview']['style'], taplist_post.load_names(
        taplist_post.NAMES_PATH)) + ', 5,2%' in lines
    assert any(line.startswith('Test') for line in lines) and any(line.startswith('Big Brew Test') for line in lines)
