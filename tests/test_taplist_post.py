"""«Таплист пятницы»: словарь имён, строка крана, новинки, свежесть кранов, ссылки.

Формат владельца 2026-10-04: «{кран}. {пивоварня и название} — {стиль}, {крепость}%[, новинка]»,
название — ссылка на Untappd, без цен. Правила — docs/content-plan.md, «Живые данные (таплист)».
Отправка со ссылками — tests/test_content_publisher.py (test_live_links_in_caption_and_album).
"""
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from core import content_plan as cp
from core import taplist_post as tp

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_FILE = ROOT / 'resources/iiko_untappd_registry.json'
NAMES = tp.load_names()
POST = datetime(2026, 10, 9, 16, 0)              # пятница, время поста
GUID_X = '44444444-4444-4444-8444-444444444444'   # кега 30 л
GUID_X20 = '55555555-5555-4555-8555-555555555555'  # та же марка, кега 20 л
GUID_Y = '66666666-6666-4666-8666-666666666666'


def _row(guid, bid):
    return {'iiko_product_id': guid, 'iiko_name': f'КЕГ {bid} {guid[:2]}', 'iiko_article': bid,
            'status': 'verified', 'untappd_beer_id': bid,
            'decision': {'status': 'verified', 'untappd_beer_id': bid, 'reason': 'тест',
                         'reviewed_at': '2026-09-01', 'evidence_urls': [f'https://untappd.com/b/beer/{bid}']}}


def _card(bid, name):
    return {'id': bid, 'url': f'https://untappd.com/b/beer/{bid}', 'beer_name': name, 'brewery': 'Festhaus',
            'observed_at': '2026-09-01', 'source_method': 'manual', 'style': 'Lager - Helles', 'abv_percent': 4.5}


REGISTRY = {'schema_version': 1,
            'products': {GUID_X: _row(GUID_X, '201'), GUID_X20: _row(GUID_X20, '201'), GUID_Y: _row(GUID_Y, '202')},
            'beers': {'201': _card('201', 'Helles'), '202': _card('202', 'Weissbier')}}


def ev(stamp, action, guid=None, name=None):
    return {'timestamp': stamp, 'action': action, 'iiko_product_id': guid, 'beer_name': name or f'КЕГ {guid}'}


def tap(number, guid=None, started=None, history=(), status=None):
    active = guid is not None if status is None else status == 'active'
    return {'tap_number': number, 'status': 'active' if active else 'empty',
            'current_beer': f'КЕГ {guid}' if active else None, 'iiko_product_id': guid if active else None,
            'started_at': started if active else None, 'history': list(history)}


def new_keys(*taps):
    return tp.new_beer_keys({'taps': list(taps)}, REGISTRY, POST)


# --------------------------------------------------------------------------- словарь

def test_names_cover_registry():
    """Каждый стиль и пивоварня реестра Untappd есть в словаре; названия со скобками и косой чертой
    («(TAP04)», «Rusalka / Русалка») переписаны; записи beers не устарели. Падает — пересобрали реестр:
    дополните resources/taplist_post_names.json."""
    registry = json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
    raw = json.loads((ROOT / 'resources/taplist_post_names.json').read_text(encoding='utf-8'))
    beers = registry['beers']
    styles = {b.get('style') or '' for b in beers.values()} - {''}
    assert not sorted(styles - set(raw['styles'])), 'стиль реестра без перевода'
    assert not sorted({b['brewery'] for b in beers.values()} - set(raw['breweries'])), 'пивоварня без короткого имени'
    junk = re.compile(r'[()\[\]/\\]')
    missing = sorted(b['beer_name'] for b in beers.values() if junk.search(b['beer_name']) and b['id'] not in raw['beers'])
    assert not missing, f'название со скобками или косой чертой без своего имени в посте: {missing}'
    for bid, item in raw['beers'].items():
        assert bid in beers, f'beers.{bid}: такого сорта в реестре нет'
        assert item['untappd'] == beers[bid]['beer_name'], f'beers.{bid}: имя в реестре поменялось'
        assert tp._clean(item['post']) == item['post'] and item['post']
    for value in list(raw['styles'].values()) + list(raw['breweries'].values()):
        assert value == tp._clean(value)
    # стиль — по-русски (IPA — принятое слово), английских слов нет
    for style, ru in raw['styles'].items():
        assert not re.search(r'[A-Za-z]', ru.replace('IPA', '')), f'{style}: «{ru}»'


def test_names_rendered_for_real_registry_have_no_junk():
    """На всём реестре: имя в посте без скобок с мусором, без двойных пробелов, стиль не английский."""
    registry = json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
    for card in registry['beers'].values():
        row = {'tap_number': 1, 'untappd_beer_id': card['id'], 'beer_name': card['beer_name'],
               'brewery': card['brewery'], 'style': card.get('style'), 'abv': card.get('abv_percent'),
               'untappd_url': card['url']}
        line, span = tp.tap_line(row, NAMES)
        name = line[span[0]:span[1]]
        assert name == tp.post_name(row, NAMES) and '  ' not in line, line
        assert not re.search(r'\((?:ex |TAP\d)|\s/\s', name), line


# --------------------------------------------------------------------------- имя и строка

def test_post_name_rules():
    names = {'styles': {}, 'breweries': {'Brouwerij Palm': 'Palm', 'Holding': '', 'Brauhaus Riegele': 'Riegele'},
             'beers': {'11827': 'Schneider Weisse Festweisse'}}
    row = lambda **kw: dict({'tap_number': 1}, **kw)  # noqa: E731
    # своё название — целиком, пивоварня не добавляется
    assert tp.post_name(row(untappd_beer_id=11827, beer_name='Festweisse (TAP04)', brewery='X'), names) == \
        'Schneider Weisse Festweisse'
    # короткое имя пивоварни + название; уже есть в названии (без учёта регистра) — не повторяем
    assert tp.post_name(row(beer_name='Steenbrugge Blanche', brewery='Brouwerij Palm'), names) == 'Palm Steenbrugge Blanche'
    assert tp.post_name(row(beer_name='Palm Spéciale', brewery='Brouwerij Palm'), names) == 'Palm Spéciale'
    assert tp.post_name(row(beer_name='Commerzienrat RIEGELE Privat', brewery='Brauhaus Riegele'), names) == \
        'Commerzienrat RIEGELE Privat'
    # пусто в словаре — марка уже в названии
    assert tp.post_name(row(beer_name='Black Sheep Irish Stout', brewery='Holding'), names) == 'Black Sheep Irish Stout'
    # пивоварни нет в словаре — её имя без скобок; неразрывные пробелы схлопнуты
    assert tp.post_name(row(beer_name='Apricot\xa0Mead', brewery='Steppe & Wind (Степь и Ветер)'), names) == \
        'Steppe & Wind Apricot Mead'
    # без карточки Untappd — имя кеги iiko без «КЕГ» и объёма
    assert tp.post_name(row(iiko_name='КЕГ Неизвестное 30 л'), names) == 'Неизвестное'


def test_tap_line_parts_and_link_span():
    row = {'tap_number': 10, 'beer_name': 'Helles', 'brewery': 'Festhaus', 'style': 'Lager - Helles', 'abv': 4.5,
           'untappd_url': 'https://untappd.com/b/beer/201'}
    line, span = tp.tap_line(row, NAMES)
    assert line == '10. Festhaus Helles — светлый лагер, 4,5%' and line[span[0]:span[1]] == 'Festhaus Helles'
    assert tp.tap_line(row, NAMES, is_new=True)[0] == '10. Festhaus Helles — светлый лагер, 4,5%, новинка'
    assert tp.tap_line(dict(row, style=None), NAMES)[0] == '10. Festhaus Helles — 4,5%'
    assert tp.tap_line(dict(row, style=None, abv=0), NAMES, is_new=True)[0] == '10. Festhaus Helles — новинка'
    assert tp.tap_line(dict(row, style='Brewed by Brauerei Königshof'), NAMES)[0] == '10. Festhaus Helles — 4,5%'
    assert tp.tap_line(dict(row, untappd_url=None), NAMES)[1] is None      # без карточки — без ссылки
    assert tp.style_ru('Wheat Beer - Hefeweizen', NAMES) == 'баварское пшеничное'
    assert tp.style_ru('', NAMES) == '' and tp.style_ru('Neue Stil', NAMES) == ''


# --------------------------------------------------------------------------- новинки

def test_new_beer_rules():
    x, y = 'untappd:201', 'untappd:202'
    # подключили 5 октября, раньше в баре не было — новинка
    assert new_keys(tap(1, GUID_X, '2026-10-05T12:00:00+03:00', [ev('2026-10-05T12:00:00+03:00', 'start', GUID_X)])) == {x}
    # стоит с 20 сентября — не новинка (подключили больше 7 дней назад)
    assert new_keys(tap(1, GUID_X, '2026-09-20T12:00:00+03:00', [ev('2026-09-20T12:00:00+03:00', 'start', GUID_X)])) == set()
    # новая кега того же сорта 6 октября — не новинка: сорт стоял весь сентябрь
    refill = [ev('2026-09-01T12:00:00+03:00', 'start', GUID_X), ev('2026-10-06T12:00:00+03:00', 'stop', GUID_X),
              ev('2026-10-06T12:00:01+03:00', 'replace', GUID_X)]
    assert new_keys(tap(1, GUID_X, '2026-10-06T12:00:01+03:00', refill)) == set()
    # кега другого объёма — тот же сорт по карточке Untappd
    other_keg = [ev('2026-09-01T12:00:00+03:00', 'start', GUID_X20), ev('2026-10-06T12:00:00+03:00', 'stop', GUID_X20),
                 ev('2026-10-06T12:00:01+03:00', 'replace', GUID_X)]
    assert new_keys(tap(1, GUID_X, '2026-10-06T12:00:01+03:00', other_keg)) == set()
    # был в августе, ушёл, вернулся 5 октября — новинка (окно 2 сентября — 2 октября)
    back = [ev('2026-08-01T12:00:00+03:00', 'start', GUID_X), ev('2026-08-20T12:00:00+03:00', 'stop', GUID_X),
            ev('2026-10-05T12:00:00+03:00', 'start', GUID_X)]
    assert new_keys(tap(1, GUID_X, '2026-10-05T12:00:00+03:00', back)) == {x}
    # в сентябре стоял на ДРУГОМ кране бара — не новинка
    elsewhere = tap(2, history=[ev('2026-09-10T12:00:00+03:00', 'start', GUID_X),
                                ev('2026-09-25T12:00:00+03:00', 'stop', GUID_X)])
    assert new_keys(tap(1, GUID_X, '2026-10-05T12:00:00+03:00', [ev('2026-10-05T12:00:00+03:00', 'start', GUID_X)]),
                    elsewhere) == set()
    # граница: подключили ровно за 7 суток до поста — ещё новинка; на минуту раньше — уже нет
    assert new_keys(tap(1, GUID_X, '2026-10-02T16:00:00+03:00', [ev('2026-10-02T16:00:00+03:00', 'start', GUID_X)])) == {x}
    assert new_keys(tap(1, GUID_X, '2026-10-02T15:59:00+03:00', [ev('2026-10-02T15:59:00+03:00', 'start', GUID_X)])) == set()
    # история обрезана: первое событие — снятие этого сорта 15 сентября -> стоял и раньше, не новинка
    cut = [ev('2026-09-15T12:00:00+03:00', 'stop', GUID_X), ev('2026-10-05T12:00:00+03:00', 'start', GUID_X)]
    assert new_keys(tap(1, GUID_X, '2026-10-05T12:00:00+03:00', cut)) == set()
    # старые данные: истории нет — по started_at; без started_at — «давно», не новинка
    assert new_keys(tap(1, GUID_Y, '2026-10-05T12:00:00+03:00')) == {y}
    assert new_keys(tap(1, GUID_Y, None)) == set()
    # старое событие без товара iiko, имя ровно как у товара в реестре — тот же сорт
    legacy = [ev('2026-09-01T12:00:00', 'start', None, name='КЕГ 201 44'),
              ev('2026-10-05T12:00:00+03:00', 'stop', None, name='КЕГ 201 44'),
              ev('2026-10-05T12:00:01+03:00', 'replace', GUID_X)]
    assert new_keys(tap(1, GUID_X, '2026-10-05T12:00:01+03:00', legacy)) == set()


def test_new_mark_in_rendered_post():
    snapshot = {'bar4': {'name': 'Варшавская', 'taps': [
        tap(1, GUID_X, '2026-10-06T12:00:00+03:00', [ev('2026-10-06T12:00:00+03:00', 'start', GUID_X)]),
        tap(2, GUID_Y, '2026-09-20T12:00:00+03:00', [ev('2026-09-20T12:00:00+03:00', 'start', GUID_Y)])]}}
    r = cp.render_live('taplist', 'varshavskaya', '{таплист}', snapshot=snapshot, registry=REGISTRY, now=POST)
    assert r['ok'] is True
    assert r['text'] == ('1. Festhaus Helles — светлый лагер, 4,5%, новинка\n'
                         '2. Festhaus Weissbier — светлый лагер, 4,5%')
    assert [row['new'] for row in r['rows']] == [True, False]


# --------------------------------------------------------------------------- свежесть кранов

def test_stale_taps_rule():
    def bar(stamp):
        return {'taps': [tap(1, GUID_X, stamp, [ev(stamp, 'start', GUID_X)])]}

    assert tp.stale_problem(bar('2026-09-25T16:00:00+03:00'), POST, cp.fmt_date_ru) is None     # ровно 14 суток
    text = tp.stale_problem(bar('2026-09-25T15:59:00+03:00'), POST, cp.fmt_date_ru)
    assert text == 'краны бара не обновлялись 14 дней (последнее изменение 25 сентября) — список мог устареть'
    assert '59 дней' in tp.stale_problem(bar('2026-08-11T14:22:15+03:00'), POST, cp.fmt_date_ru)
    # снятие кеги — тоже изменение
    fresh = {'taps': [tap(1, GUID_X, '2026-08-01T12:00:00+03:00', [ev('2026-08-01T12:00:00+03:00', 'start', GUID_X)]),
                      tap(2, history=[ev('2026-08-01T12:00:00+03:00', 'start', GUID_Y),
                                      ev('2026-10-08T12:00:00+03:00', 'stop', GUID_Y)])]}
    assert tp.last_change(fresh) == datetime(2026, 10, 8, 12, 0)
    assert tp.stale_problem(fresh, POST, cp.fmt_date_ru) is None
    assert tp.stale_problem({'taps': [tap(1, GUID_X, None)]}, POST, cp.fmt_date_ru).startswith(
        'на странице кранов бара нет ни одной отметки')
    assert [tp.days_word(n) for n in (1, 2, 4, 5, 11, 14, 21, 22, 25, 111)] == [
        'день', 'дня', 'дня', 'дней', 'дней', 'дней', 'день', 'дня', 'дней', 'дней']


def test_stale_taps_stops_rendered_post():
    snapshot = {'bar3': {'name': 'Кременчугская', 'taps': [
        tap(9, GUID_X, '2026-08-11T14:22:15+03:00', [ev('2026-08-11T14:22:15+03:00', 'replace', GUID_X)])]}}
    r = cp.render_live('taplist', 'kremenchugskaya', '{таплист}', snapshot=snapshot, registry=REGISTRY, now=POST)
    assert r['ok'] is False and [p['code'] for p in r['problems']] == ['stale_taps']
    assert r['problems'][0]['text'] == ('краны бара не обновлялись 59 дней (последнее изменение 11 августа) — '
                                        'список мог устареть')
    assert r['taps_changed_at'] == '2026-08-11T14:22' and r['text'] == '9. Festhaus Helles — светлый лагер, 4,5%'


# --------------------------------------------------------------------------- ссылки

def test_entities_offsets_in_utf16_and_every_occurrence():
    """Символ вне основной плоскости до {таплист} (Telegram считает его за 2) и два {таплист} в шаблоне."""
    snapshot = {'bar4': {'name': 'Варшавская', 'taps': [
        tap(1, GUID_X, '2026-10-06T12:00:00+03:00', [ev('2026-10-06T12:00:00+03:00', 'start', GUID_X)])]}}
    template = '\U0001D504 {бар}\n{таплист}\n---\n{таплист}'
    r = cp.render_live('taplist', 'varshavskaya', template, snapshot=snapshot, registry=REGISTRY, now=POST)
    encoded = r['text'].encode('utf-16-le')
    assert len(r['entities']) == 2
    for entity in r['entities']:
        start = entity['offset'] * 2
        assert encoded[start:start + entity['length'] * 2].decode('utf-16-le') == 'Festhaus Helles'
        assert entity == dict(entity, type='text_link', url='https://untappd.com/b/beer/201')
    assert r['entities'][0]['offset'] == tp.utf16_len('\U0001D504 Варшавская\n1. ')


# --------------------------------------------------------------------------- гостевой бот

class FakeManager:
    """Менеджер кранов для bar_message_html: снимок как у TapsManager.get_snapshot."""

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.catalogs = []

    def get_snapshot(self, catalog=None):
        self.catalogs.append(catalog)
        return self.snapshot


def test_iiko_display_and_tap_order():
    assert tp.iiko_display('КЕГ Вудбридж ИПА 30 л') == 'Вудбридж ИПА'
    assert tp.iiko_display('КЕГ Бульви Семи Драй л') == 'Бульви Семи Драй'
    assert tp.iiko_display('КЕГ Джоус Мюних Хеллес, светлое,') == 'Джоус Мюних Хеллес, светлое'
    assert tp.iiko_display('KEG Saldens Double IPA 30л.') == 'Saldens Double IPA'
    assert tp.iiko_display('нишко') == 'нишко' and tp.iiko_display('КЕГ') == 'КЕГ'
    rows = [{'tap_number': 10}, {'tap_number': 'B'}, {'tap_number': 2}]
    assert [r['tap_number'] for r in sorted(rows, key=tp.tap_order)] == [2, 10, 'B']


def test_line_html_escapes_and_links():
    line, span = tp.tap_line({'tap_number': 1, 'beer_name': 'Ale <&> Co', 'untappd_url': 'https://untappd.com/b/x/1'},
                             NAMES)
    assert tp.line_html(line, span, 'https://untappd.com/b/x/1?a="1"') == (
        '1. <a href="https://untappd.com/b/x/1?a=&quot;1&quot;">Ale &lt;&amp;&gt; Co</a>')
    assert tp.line_html('1. A & B — 5%', None, None) == '1. A &amp; B — 5%'


def test_bot_message_from_registry():
    """Бот берёт сорт по GUID из реестра (не по похожему названию): строки «Таплиста пятницы» в HTML."""
    snapshot = {'bar2': {'name': 'Лиговский', 'taps': [
        tap(5, GUID_X, '2026-09-20T12:00:00+03:00', [ev('2026-09-20T12:00:00+03:00', 'start', GUID_X)]),
        tap(6, GUID_Y, '2026-10-06T12:00:00+03:00', [ev('2026-10-06T12:00:00+03:00', 'start', GUID_Y)]),
        dict(tap(7, None), status='active', current_beer='КЕГ Вудбридж ИПА 30 л', started_at='2026-09-20T12:00:00+03:00'),
        tap(8)]}}
    manager = FakeManager(snapshot)
    text = tp.bar_message_html(manager, 'bar2', 'Лиговский', moment=POST, registry=REGISTRY)
    assert text == ('<b>Лиговский</b>\n\n'
                    '5. <a href="https://untappd.com/b/beer/201">Festhaus Helles</a> — светлый лагер, 4,5%\n'
                    '6. <a href="https://untappd.com/b/beer/202">Festhaus Weissbier</a> — светлый лагер, 4,5%, новинка\n'
                    '7. Вудбридж ИПА')
    assert manager.catalogs and GUID_X in manager.catalogs[0]          # снимок с каталогом реестра
    empty = FakeManager({'bar2': {'name': 'Лиговский', 'taps': [tap(1)]}})
    assert tp.bar_message_html(empty, 'bar2', 'Лиговский & Ко', moment=POST, registry=REGISTRY) == \
        'Лиговский &amp; Ко: нет активных кранов'


# ---------------------------------------------------------------------------
# Вступление и концовка (решение владельца 2026-10-09: «писать по-разному»)
# ---------------------------------------------------------------------------

EMOJI_RE = re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]')


def test_phrase_bank_is_valid():
    variants = tp.load_phrases()
    assert len(variants) >= 8
    intros = [intro for intro, _outro in variants]
    assert len(set(intros)) == len(intros), 'вступления не повторяются'
    # первые четыре — примеры владельца 2026-10-09, слово в слово
    assert variants[:4] == (
        ('Идеальный набор для пятницы.', 'Культурное разнообразие: всё свежее, разное и вкусное. Ждём!'),
        ('Друзья, ловите актуальный пятничный таплист!', 'Всем хороших выходных, и конечно же, ждём на бокальчик'),
        ('Традиционный пятничный таплист!', ''),
        ('Пятничный таплист {где}!', ''))
    for intro, outro in variants:
        assert intro and len(intro) <= tp.PHRASE_INTRO_MAX and len(outro) <= tp.PHRASE_OUTRO_MAX, intro
        for text in (intro, outro):
            assert not EMOJI_RE.search(text) and '\n' not in text, text
            assert set(re.findall(r'\{[^{}]*\}', text)) <= set(tp.PHRASE_TOKENS), text


def test_phrase_rotation_by_week_and_bar():
    total = len(tp.load_phrases())
    friday = date(2026, 10, 9)
    # пример из докстроки phrase_index: неделя 39, у bar1 — 39 mod 16, у bar3 — (39 + 8) mod 16
    assert (tp.phrase_index(friday, 'bar1', 16), tp.phrase_index(friday, 'bar3', 16)) == (7, 15)
    # в одну пятницу у четырёх баров разные фразы
    assert len({tp.phrase_index(friday, bar, total) for bar in tp.PHRASE_BARS}) == 4
    for bar in tp.PHRASE_BARS:
        seen = [tp.phrase_index(friday + timedelta(weeks=week), bar, total) for week in range(total)]
        assert sorted(seen) == list(range(total)), 'за total недель — каждый вариант по разу'
        assert all(a != b for a, b in zip(seen, seen[1:])), 'две пятницы подряд — разные фразы'
    # пост перенесли на субботу той же недели — фраза та же; новая неделя — следующая фраза
    assert tp.phrase_index(friday + timedelta(days=1), 'bar2', total) == tp.phrase_index(friday, 'bar2', total)
    assert tp.phrase_index(friday + timedelta(days=3), 'bar2', total) == (
        tp.phrase_index(friday, 'bar2', total) + 1) % total
    # стык годов: недели идут подряд (номер ISO-недели прыгнул бы с 53 на 1)
    assert tp.phrase_index(date(2027, 1, 1), 'bar1', total) == (tp.phrase_index(date(2026, 12, 25), 'bar1', total) + 1) % total
    # даты до начала отсчёта и маленький набор — номер в пределах
    assert 0 <= tp.phrase_index(date(2025, 6, 6), 'bar4', total) < total
    assert {tp.phrase_index(friday, bar, 2) for bar in tp.PHRASE_BARS} <= {0, 1}
    assert tp.phrase_index(friday, 'bar9', total) == tp.phrase_index(friday, 'bar1', total)   # чужой бар — без сдвига


def test_phrases_fill_their_own_placeholders():
    variants = (('Таплист {где}, {дата}!', 'До встречи {где}. {цена}'),)
    values = {'{где}': 'на Кременчугской', '{дата}': '9 октября'}
    assert tp.phrases_for(date(2026, 10, 9), 'bar3', values, variants) == (
        'Таплист на Кременчугской, 9 октября!', 'До встречи на Кременчугской. {цена}', 1, 1)
    # подставленное значение повторно не разбирается
    assert tp.phrases_for(date(2026, 10, 9), 'bar1', {'{где}': '{дата}', '{дата}': 'X'}, (('{где}', ''),))[0] == '{дата}'


def test_broken_phrase_bank_fails_loudly(tmp_path):
    blank = tmp_path / 'blank.json'
    blank.write_text('{"variants": [{"intro": " ", "outro": "x"}]}', encoding='utf-8')
    empty = tmp_path / 'empty.json'
    empty.write_text('{"variants": []}', encoding='utf-8')
    for path in (blank, empty):
        with pytest.raises(ValueError):
            tp.load_phrases(path)
