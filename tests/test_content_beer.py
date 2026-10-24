"""Сорт в посте: сверка строки про сорт с кранами и замена снятого сорта (core/content_beer.py).

Решение владельца 2026-10-23: пост про пиво выходит всегда; если согласованный сорт сняли,
строка переписывается под сорт, который стоит сейчас. Правила — docs/content-plan.md, раздел
«Сорт в посте».
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import content_beer as cb  # noqa: E402

BAR_IDS = {'bolshoy': 'bar1', 'ligovskiy': 'bar2', 'kremenchugskaya': 'bar3', 'varshavskaya': 'bar4'}
NOW = datetime(2026, 10, 23, 12, 0)
FRESH = '2026-10-20T12:00:00+03:00'

GUIDS = {name: f'{i:08d}-0000-4000-8000-000000000000' for i, name in enumerate(
    ['riegele', 'festhaus', 'stout', 'porter', 'ipa', 'cider', 'gose', 'tomato', 'pils', 'kwak'], start=1)}


def _card(bid, name, brewery, style, abv):
    return {'id': bid, 'url': f'https://untappd.com/b/beer/{bid}', 'beer_name': name, 'brewery': brewery,
            'observed_at': '2026-09-01', 'source_method': 'manual', 'style': style, 'abv_percent': abv}


def _product(key, bid):
    guid = GUIDS[key]
    return guid, {'iiko_product_id': guid, 'iiko_name': f'КЕГ {key} 30 л', 'iiko_article': bid,
                  'status': 'verified', 'untappd_beer_id': bid,
                  'decision': {'status': 'verified', 'untappd_beer_id': bid, 'reason': 'тест',
                               'reviewed_at': '2026-09-01',
                               'evidence_urls': [f'https://untappd.com/b/beer/{bid}']}}


CARDS = {
    'riegele': ('201', 'Feines Urhell', 'Brauhaus Riegele', 'Lager - Helles', 4.7),
    'festhaus': ('202', 'Helles', 'Festhaus', 'Lager - Helles', 4.5),
    'stout': ('203', 'Black Sheep Irish Stout', 'Black Sheep', 'Stout - Irish Dry', 4.0),
    'porter': ('204', 'Baltic Night', 'Тёмная', 'Porter - Baltic', 7.0),
    'ipa': ('205', 'Hop Storm', 'Хмель', 'IPA - American', 6.5),
    'cider': ('206', 'Rustiq Semi Dry', 'Bullevie', 'Cider - Traditional / Apfelwein', 5.5),
    'gose': ('207', 'Just: Gose', 'Midnight Project', 'Sour - Traditional Gose', 5.5),
    'tomato': ('208', 'Morning Manya', 'Zavod', 'Sour - Tomato / Vegetable Gose', 4.1),
    'pils': ('209', 'Zubr Gold', 'Pivovar Zubr', 'Pilsner - Czech / Bohemian', 4.6),
    'kwak': ('210', 'Pauwel Kwak', 'Brouwerij Bosteels', 'Pale Ale - Belgian', 8.4),
}
REGISTRY = {'schema_version': 1, 'products': {}, 'beers': {}}
for _key, (_bid, _name, _brewery, _style, _abv) in CARDS.items():
    _guid, _row = _product(_key, _bid)
    REGISTRY['products'][_guid] = _row
    REGISTRY['beers'][_bid] = _card(_bid, _name, _brewery, _style, _abv)

NAMES = {'styles': {'Lager - Helles': 'светлый лагер', 'Stout - Irish Dry': 'ирландский стаут',
                    'Porter - Baltic': 'балтийский портер', 'IPA - American': 'американский IPA',
                    'Cider - Traditional / Apfelwein': 'традиционный сидр', 'Sour - Traditional Gose': 'гозе',
                    'Sour - Tomato / Vegetable Gose': 'томатный гозе',
                    'Pilsner - Czech / Bohemian': 'чешский пилснер', 'Pale Ale - Belgian': 'бельгийский эль'},
         'breweries': {'Brauhaus Riegele': 'Riegele', 'Festhaus': 'Festhaus', 'Black Sheep': '',
                       'Тёмная': 'Тёмная', 'Хмель': 'Хмель', 'Bullevie': 'Bullevie',
                       'Midnight Project': 'Midnight Project', 'Zavod': 'Zavod', 'Pivovar Zubr': '',
                       'Brouwerij Bosteels': ''},
         'beers': {}}


def _tap(number, key=None, started=FRESH, status='active'):
    if key is None:
        return {'tap_number': number, 'current_beer': None, 'status': 'empty', 'iiko_product_id': None,
                'started_at': None, 'history': []}
    return {'tap_number': number, 'current_beer': f'КЕГ {key} 30 л', 'status': status,
            'iiko_product_id': GUIDS[key], 'started_at': started,
            'history': [{'timestamp': started, 'action': 'start', 'beer_name': f'КЕГ {key} 30 л',
                         'iiko_product_id': GUIDS[key]}]}


def _ctx(bars, **kw):
    snapshot = {BAR_IDS[bar]: {'name': bar, 'taps': taps} for bar, taps in bars.items()}
    return cb.TapsContext(snapshot, REGISTRY, BAR_IDS, names=NAMES, now=NOW, **kw)


HELLES = ('Как Мюнхен сдался светлому\n\nМюнхен варил тёмное.\n\n'
          'Сегодня на восьмом кране «Культуры Каск» — Riegele Feines Urhell, хеллес из Аугсбурга, 4,7%: '
          'чистый и непастеризованный.')


def test_last_paragraph_and_body():
    assert cb.last_paragraph('') is None and cb.last_paragraph('  \n ') is None
    text = 'Заголовок\n\nИстория.\n\n  Строка про сорт.\n\n'
    start, end = cb.last_paragraph(text)
    assert text[start:end] == 'Строка про сорт.'
    assert cb.last_paragraph('Один абзац') == (0, len('Один абзац'))
    # тело — без последнего абзаца: у каждого бара своя строка про сорт
    assert cb.body_of('А.\n\nБ.\n\nСегодня на кране X.') == cb.body_of('А.\n\nБ.\n\nСегодня на кране Y.')
    assert cb.body_of('Один абзац.') == 'один абзац'
    assert cb.norm('Just: Gose — Ёлка!') == 'just gose елка'


def test_tap_phrase_and_find_tap():
    assert cb.tap_phrase(6) == 'на шестом кране'
    assert cb.tap_phrase('24') == 'на двадцать четвёртом кране'
    assert cb.tap_phrase(30) == 'на кране № 30' and cb.tap_phrase('A') == 'на кране № A'
    assert len(cb.TAP_ORDINALS) == 24
    found = cb.find_tap('Сегодня на двадцать втором кране «Культуры» — X')
    assert found['number'] == 22 and found['form'] == 'word'
    assert cb.find_tap('Сегодня на четвертом кране')['number'] == 4      # «е» вместо «ё»
    assert cb.find_tap('на 8-м кране')['number'] == 8
    assert cb.find_tap('стоит в кране № 12')['number'] == 12
    assert cb.find_tap('Сегодня в «Культуре»') is None
    line = 'Сегодня на восьмом кране «Культуры Каск» — Riegele'
    assert cb.replace_tap(line, cb.find_tap(line), 5) == 'Сегодня на пятом кране «Культуры Каск» — Riegele'
    line = 'Сегодня на 8-м кране — Riegele'
    assert cb.replace_tap(line, cb.find_tap(line), 11) == 'Сегодня на 11-м кране — Riegele'


def test_style_groups():
    assert cb.style_family('Stout - Irish Dry') == 'Stout' and cb.style_family('Festbier') == 'Festbier'
    assert cb.style_family('Brewed by Delirium - Huyghe Brewery') == '' and cb.style_family(None) == ''
    assert cb.style_group('Porter - Baltic') == cb.style_group('Stout - Irish Dry') == 'dark'
    assert cb.style_group('Lager - Munich Dunkel') == 'dark'          # тёмный лагер — к тёмному
    assert cb.style_group('Pilsner - German') == cb.style_group('Lager - Helles') == 'lager'
    assert cb.drink_kind('Cider - Dry') == 'cider' and cb.drink_kind('Mead - Melomel') == 'mead'
    assert cb.drink_kind('Lager - Helles') == 'beer' and cb.drink_kind(None) == 'beer'


def test_every_style_family_classified():
    """Каждое семейство стилей словаря — в группе или вид напитка (как тест словаря требует
    перевод каждого стиля): иначе снятый сорт этого семейства пропускал бы уровень «группа»."""
    names = json.loads(Path('resources/taplist_post_names.json').read_text(encoding='utf-8'))
    families = {cb.style_family(style) for style in names['styles']} - {''}
    grouped = {family for _name, items in cb.STYLE_GROUPS.values() for family in items}
    missing = sorted(families - grouped - set(cb.DRINK_KINDS))
    assert missing == [], f'добавьте семейства в STYLE_GROUPS или DRINK_KINDS: {missing}'


def test_on_tap_moved_and_none():
    ctx = _ctx({'ligovskiy': [_tap(8, 'riegele'), _tap(5, 'festhaus')]})
    check = cb.check_post(HELLES, 'ligovskiy', ctx)
    assert check['state'] == 'on_tap' and check['text'] == HELLES and check['new_line'] is None
    assert [b['name'] for b in check['beers']] == ['Riegele Feines Urhell'] and check['beers'][0]['tap'] == 8
    # переехал на другой кран — меняется только номер
    ctx = _ctx({'ligovskiy': [_tap(11, 'riegele'), _tap(5, 'festhaus')]})
    check = cb.check_post(HELLES, 'ligovskiy', ctx)
    assert check['state'] == 'moved'
    assert check['new_line'].startswith('Сегодня на одиннадцатом кране «Культуры Каск» — Riegele Feines Urhell, хеллес')
    assert check['text'].endswith(check['new_line']) and 'теперь на кране 11' in check['note']
    # сорта в последнем абзаце нет — пост как есть
    check = cb.check_post('История.\n\nЖдём вас вечером.', 'ligovskiy', ctx)
    assert check['state'] == 'none' and check['text'] == 'История.\n\nЖдём вас вечером.'
    assert cb.check_post('', 'ligovskiy', ctx)['state'] == 'none'


def test_swap_same_style_then_family_group_any():
    # Riegele сняли, Festhaus Helles — тот же стиль
    ctx = _ctx({'ligovskiy': [_tap(5, 'festhaus'), _tap(6, 'pils'), _tap(1, 'stout')]})
    check = cb.check_post(HELLES, 'ligovskiy', ctx)
    assert check['state'] == 'swap'
    assert check['new_line'] == 'Сегодня на пятом кране «Культуры Каск» — Festhaus Helles, светлый лагер, 4,5%.'
    assert check['text'] == HELLES.rsplit('\n\n', 1)[0] + '\n\n' + check['new_line']
    assert check['replacement']['level'] == 'same_style' and 'тот же стиль' in check['note']
    assert check['beers'][0]['on_tap'] is False
    # того же стиля нет — та же группа (пилснер — тоже лагер)
    ctx = _ctx({'ligovskiy': [_tap(6, 'pils'), _tap(1, 'stout')]})
    check = cb.check_post(HELLES, 'ligovskiy', ctx)
    assert check['replacement']['level'] == 'same_group' and check['replacement']['name'] == 'Zubr Gold'
    assert check['replacement']['level_text'] == 'та же группа: лагер'
    # стаут снят — портер той же группы «тёмное»
    stout = 'История.\n\nСегодня на шестом кране «Культуры» — Black Sheep Irish Stout, 4%.'
    ctx = _ctx({'varshavskaya': [_tap(3, 'porter'), _tap(2, 'ipa'), _tap(4, 'cider')]})
    check = cb.check_post(stout, 'varshavskaya', ctx)
    assert check['replacement']['name'] == 'Тёмная Baltic Night' and check['replacement']['tap'] == 3
    # ни тёмного, ни похожего — любое пиво, но не сидр
    ctx = _ctx({'varshavskaya': [_tap(4, 'cider'), _tap(2, 'ipa')]})
    check = cb.check_post(stout, 'varshavskaya', ctx)
    assert check['state'] == 'swap' and check['replacement']['level'] == 'any'
    assert check['replacement']['name'] == 'Хмель Hop Storm' and 'другой стиль' in check['note']
    # только сидр на кранах — пиву замены нет
    ctx = _ctx({'varshavskaya': [_tap(4, 'cider')]})
    check = cb.check_post(stout, 'varshavskaya', ctx)
    assert check['state'] == 'no_beer' and check['text'] == stout and 'пост не уйдёт' in check['note']


def test_cider_post_takes_only_cider():
    post = 'День яблока.\n\nСегодня на втором кране «Культуры» — Bullevie Rustiq Semi Dry, 5,5%.'
    ctx = _ctx({'varshavskaya': [_tap(2, 'ipa')]})
    assert cb.check_post(post, 'varshavskaya', ctx)['state'] == 'no_beer'


def test_replacement_order_mapped_then_latest_then_tap():
    ctx = _ctx({'ligovskiy': [_tap(9, 'festhaus', started='2026-10-01T12:00:00+03:00'),
                              _tap(3, 'pils', started='2026-10-15T12:00:00+03:00')]})
    # оба — группа «лагер»… но Festhaus Helles — тот же стиль: уровень важнее даты
    assert cb.check_post(HELLES, 'ligovskiy', ctx)['replacement']['name'] == 'Festhaus Helles'
    stout = 'История.\n\nСегодня на шестом кране «Культуры» — Black Sheep Irish Stout, 4%.'
    ctx = _ctx({'varshavskaya': [_tap(9, 'ipa', started='2026-10-01T12:00:00+03:00'),
                                 _tap(3, 'kwak', started='2026-10-15T12:00:00+03:00')]})
    # уровень any: подключённый позже — Kwak
    assert cb.check_post(stout, 'varshavskaya', ctx)['replacement']['name'] == 'Pauwel Kwak'


def test_two_beers_in_line_keep_remaining():
    post = ('Гозе.\n\nСегодня в «Культуре» гозе на двух кранах: на шестом — Midnight Project Just: Gose, 5,5%, '
            'на девятом — томатный Zavod Morning Manya, 4,1%.')
    ctx = _ctx({'bolshoy': [_tap(6, 'gose'), _tap(9, 'tomato')]})
    check = cb.check_post(post, 'bolshoy', ctx)
    assert check['state'] == 'on_tap' and len(check['beers']) == 2
    ctx = _ctx({'bolshoy': [_tap(9, 'tomato')]})
    check = cb.check_post(post, 'bolshoy', ctx)
    assert check['state'] == 'swap' and check['replacement']['level'] == 'kept'
    assert check['new_line'] == 'Сегодня на девятом кране «Культуры» — Zavod Morning Manya, томатный гозе, 4,1%.'


def test_no_data_and_short_names():
    assert cb.check_post(HELLES, 'ligovskiy', None)['state'] == 'no_data'
    assert cb.check_post(HELLES, 'ligovskiy', cb.TapsContext(error='нет файла'))['state'] == 'no_data'
    # «Helles» одним коротким словом — не сорт: стиль в тексте не путается с Festhaus Helles
    ctx = _ctx({'ligovskiy': [_tap(5, 'festhaus')]})
    assert cb.check_post('История.\n\nHelles в Мюнхене любят.', 'ligovskiy', ctx)['state'] == 'none'
    # но полное имя находится
    assert cb.check_post('История.\n\nНа кране Festhaus Helles.', 'ligovskiy', ctx)['state'] == 'on_tap'


def test_beer_line_parts():
    row = {'tap_number': 3, 'beer_name': 'Zubr Gold', 'brewery': 'Pivovar Zubr', 'untappd_beer_id': '209',
           'style': 'Pilsner - Czech / Bohemian', 'abv': 4.6}
    assert cb.beer_line(row, 'kremenchugskaya', NAMES) == 'Сегодня на третьем кране «Культуры» — Zubr Gold, чешский пилснер, 4,6%.'
    row = {'tap_number': 30, 'beer_name': 'Неизвестное'}
    assert cb.beer_line(row, 'ligovskiy', NAMES) == 'Сегодня на кране № 30 «Культуры Каск» — Неизвестное.'


# --------------------------------------------------------------------------- самозапуск

if __name__ == '__main__':
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith('test_') and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print('ok   ', name)
        except Exception as e:  # noqa: BLE001 — отчёт по каждому тесту
            failed += 1
            print('FAIL ', name, '-', repr(e)[:800])
    print('\n' + str(len(tests) - failed) + ' passed, ' + str(failed) + ' failed')
    sys.exit(1 if failed else 0)
