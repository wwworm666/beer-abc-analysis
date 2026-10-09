"""Связи с Untappd без деплоя (core/untappd_live): агент предлагает, владелец подтверждает.

Решение владельца 2026-10-04 — «автоматический маппинг через ИИ-агента». Проверяется:
предложение — черновик и ни на что не влияет; «Верно» — связь сразу работает через
тот же строгий resolve_beer (таплист, пост, бот); «Не то» и «Отменить» возвращают кегу
в очередь; встроенная проверенная связь главнее; битый файл не перезаписывается.
"""
import json
import os
import tempfile
from datetime import datetime

import pytest

from core import taplist_post as tp
from core import untappd_live as ul
from core.untappd_registry import resolve_beer

GUID_LINKED = '11111111-1111-4111-8111-111111111111'   # уже проверен во встроенном реестре
GUID_OPEN = '22222222-2222-4222-8222-222222222222'     # в реестре без связи (needs_source)
GUID_NEW = '33333333-3333-4333-8333-333333333333'      # новая карточка номенклатуры, в реестре нет
GUID_EXCL = '44444444-4444-4444-8444-444444444444'     # техническая карточка
OWNER = {'login': 'Artem', 'display_name': 'Artem', 'is_admin': True}
AGENT = dict(OWNER, via_mcp=True)
NOW = datetime(2026, 10, 5, 10, 0)


def _registry():
    linked = {'iiko_product_id': GUID_LINKED, 'iiko_name': 'КЕГ ФестХаус Хеллес', 'iiko_article': '64449',
              'status': 'verified', 'untappd_beer_id': '6240484',
              'decision': {'status': 'verified', 'untappd_beer_id': '6240484', 'reason': 'тест',
                           'reviewed_at': '2026-09-20',
                           'evidence_urls': ['https://untappd.com/b/festhaus-helles/6240484']}}
    return {'schema_version': 1,
            'products': {GUID_LINKED: linked,
                         GUID_OPEN: {'iiko_product_id': GUID_OPEN, 'iiko_name': 'КЕГ Вудбридж ИПА 30 л',
                                     'iiko_article': '02030', 'status': 'needs_source'},
                         GUID_EXCL: {'iiko_product_id': GUID_EXCL, 'iiko_name': '1', 'iiko_article': '',
                                     'status': 'excluded'}},
            'beers': {'6240484': {'id': '6240484', 'url': 'https://untappd.com/b/festhaus-helles/6240484',
                                  'beer_name': 'Helles', 'brewery': 'Festhaus', 'style': 'Lager - Helles',
                                  'abv_percent': 4.5, 'observed_at': '2026-09-20', 'source_method': 'manual'}}}


def _catalog(registry):
    catalog = {guid: {'id': guid, 'name': row['iiko_name'], 'num': row['iiko_article']}
               for guid, row in registry['products'].items() if row['status'] != 'excluded'}
    catalog[GUID_NEW] = {'id': GUID_NEW, 'name': 'КЕГ Шнайдер ТАР4 20 л', 'num': '01295'}
    return catalog


@pytest.fixture
def store():
    folder = tempfile.mkdtemp()
    s = ul.UntappdLinksStore(os.path.join(folder, 'untappd_links.json'), now_fn=lambda: NOW)
    ul.set_store(s)
    yield s
    ul.set_store(None)


PROPOSAL = {'iiko_product_id': GUID_NEW,
            'untappd_url': 'https://www.untappd.com/b/schneider-weisse-festweisse-tap04/11827?ref=x#top',
            'beer_name': 'Festweisse (TAP04)', 'brewery': 'Schneider Weisse G. Schneider & Sohn',
            'style': 'Wheat Beer - Festbier', 'abv': '6,2', 'ibu': 28,
            'photo_url': 'https://assets.untappd.com/site/beer_logos/beer-11827.jpeg',
            'reason': 'Шнайдер ТАР4 — Festweisse: номер TAP 4 у Schneider, 6,2%, сайт пивоварни.',
            'evidence_urls': ['https://www.schneider-weisse.de/en/tap4'],
            'style_ru': 'праздничное пшеничное', 'brewery_short': 'Schneider Weisse'}


def _propose(store, fields=None, user=AGENT):
    registry = _registry()
    return store.propose(dict(PROPOSAL, **(fields or {})), user, registry, _catalog(registry))


def test_proposal_is_draft_until_confirmed(store):
    item = _propose(store)
    assert (item['status'], item['origin'], item['created_by']) == ('proposed', 'agent', 'Artem · агент')
    assert (item['url'], item['untappd_beer_id']) == (
        'https://untappd.com/b/schneider-weisse-festweisse-tap04/11827', '11827')
    assert item['card']['abv_percent'] == 6.2 and item['card']['ibu'] == 28
    assert item['evidence_urls'][0] == item['url'] and len(item['evidence_urls']) == 2
    # черновик ни на что не влияет: в рабочем реестре связи нет
    assert resolve_beer(ul.apply(_registry()), GUID_NEW) is None
    # подтверждение — связь работает через тот же строгий resolve_beer
    done = store.confirm(item['id'], OWNER, _registry())
    assert (done['status'], done['reviewed_by'], done['reviewed_at']) == ('verified', 'Artem', '2026-10-05T10:00')
    card = resolve_beer(ul.apply(_registry()), GUID_NEW)
    assert card and (card['id'], card['beer_name'], card['abv_percent']) == ('11827', 'Festweisse (TAP04)', 6.2)
    assert card['photo_url'].startswith('https://assets.untappd.com/')
    # встроенный реестр не меняется
    assert GUID_NEW not in _registry()['products']


def test_confirmed_link_reaches_the_post_line(store):
    item = _propose(store)
    store.confirm(item['id'], OWNER, _registry(), {'style_ru': 'праздничное пшеничное'})
    names = tp.load_names()
    assert names['styles']['Wheat Beer - Festbier'] == 'праздничное пшеничное'
    registry = ul.apply(_registry())
    row = {'tap_number': 22, 'untappd_beer_id': '11827', 'beer_name': 'Festweisse (TAP04)',
           'brewery': 'Schneider Weisse G. Schneider & Sohn', 'style': 'Wheat Beer - Festbier', 'abv': 6.2,
           'untappd_url': resolve_beer(registry, GUID_NEW)['url']}
    # своё название сорта из словаря репозитория (11827) главнее
    assert tp.tap_line(row, names)[0] == '22. Schneider Weisse Festweisse — праздничное пшеничное, 6,2%'


def test_bundled_link_wins_and_names_only_fill_gaps(store):
    item = _propose(store, {'style': 'Lager - Helles', 'style_ru': 'другое'})
    store.confirm(item['id'], OWNER, _registry())
    assert tp.load_names()['styles']['Lager - Helles'] == 'светлый лагер'     # словарь главнее
    # GUID уже проверен во встроенном реестре — предложить нельзя
    with pytest.raises(ul.UntappdLinksError) as err:
        _propose(store, {'iiko_product_id': GUID_LINKED})
    assert err.value.code == 'conflict'


def test_validation():
    folder = tempfile.mkdtemp()
    s = ul.UntappdLinksStore(os.path.join(folder, 'x.json'), now_fn=lambda: NOW)
    bad = [({'untappd_url': 'https://untappd.com/beer/11827'}, 'untappd_url'),
           ({'untappd_url': 'https://untapped.com/b/x/1'}, 'untappd_url'),
           ({'iiko_product_id': 'not-a-guid'}, 'GUID'),
           ({'beer_name': ' '}, 'beer_name'),
           ({'abv': '95'}, 'abv'),
           ({'ibu': 12.5}, 'ibu'),
           ({'reason': ''}, 'reason'),
           ({'evidence_urls': ['javascript:alert(1)']}, 'evidence_urls'),
           ({'evidence_urls': 'https://x'}, 'evidence_urls')]
    for patch, word in bad:
        with pytest.raises(ul.UntappdLinksError) as err:
            _propose(s, patch)
        assert word in str(err.value), (patch, str(err.value))
    with pytest.raises(ul.UntappdLinksError) as err:
        _propose(s, {'iiko_product_id': '55555555-5555-4555-8555-555555555555'})
    assert err.value.code == 'not_found'
    # фото не с Untappd — предложение проходит без фото, с предупреждением
    item = _propose(s, {'photo_url': 'https://example.com/a.jpg'})
    assert item['card']['photo_url'] is None and item['warnings']


def test_reject_revoke_and_supersede_return_to_queue(store):
    first = _propose(store)
    second = _propose(store, {'untappd_url': 'https://untappd.com/b/schneider-weisse-aventinus-tap06/16851'})
    statuses = {p['id']: p['status'] for p in store.proposals()}
    assert statuses[first['id']] == 'superseded' and statuses[second['id']] == 'proposed'
    rejected = store.reject(second['id'], OWNER, 'Это TAP06 Aventinus, а на кране TAP4')
    assert rejected['status'] == 'rejected'
    with pytest.raises(ul.UntappdLinksError) as err:
        store.confirm(second['id'], OWNER, _registry())
    assert err.value.code == 'conflict'
    third = _propose(store)
    store.confirm(third['id'], OWNER, _registry())
    revoked = store.revoke(third['id'], OWNER, 'ошибся')
    assert revoked['status'] == 'revoked' and resolve_beer(ul.apply(_registry()), GUID_NEW) is None
    with pytest.raises(ul.UntappdLinksError):
        store.revoke(third['id'], OWNER)
    with pytest.raises(ul.UntappdLinksError) as err:
        store.confirm('up_nope', OWNER, _registry())
    assert err.value.code == 'not_found'
    log = [entry['text'] for entry in store.load()['log']]
    assert any(text.startswith('Подтверждена связь') for text in log) and any('Отменена' in t for t in log)


def test_queue_priorities_and_proposals(store):
    snapshot = {'bar1': {'name': 'Большой пр. В.О', 'taps': [
        {'tap_number': 22, 'status': 'active', 'current_beer': 'КЕГ Шнайдер ТАР4 20 л', 'iiko_product_id': GUID_NEW,
         'started_at': '2026-10-01T15:30:24+03:00'},
        {'tap_number': 5, 'status': 'active', 'current_beer': 'нишко', 'iiko_product_id': None},
        {'tap_number': 1, 'status': 'active', 'current_beer': 'КЕГ ФестХаус Хеллес', 'iiko_product_id': GUID_LINKED}]}}
    registry = _registry()
    q = ul.queue(registry, _catalog(registry), snapshot, store.load())
    assert [(row['iiko_product_id'], row['priority']) for row in q['items']] == [(GUID_NEW, 1)]
    assert q['items'][0]['on_tap'][0]['tap_number'] == 22 and q['items'][0]['registry_status'] == 'new'
    assert q['unidentified_taps'] == [{'bar_id': 'bar1', 'bar': 'Большой пр. В.О', 'tap_number': 5,
                                       'started_at': None, 'current_beer': 'нишко'}]
    full = ul.queue(registry, _catalog(registry), snapshot, store.load(), scope='all')
    assert [row['iiko_product_id'] for row in full['items']] == [GUID_NEW, GUID_OPEN]   # без техкарточки
    # «пропущено владельцем» — только когда кега на кране
    registry['products'][GUID_OPEN]['status'] = 'skipped'
    full = ul.queue(registry, _catalog(registry), snapshot, store.load(), scope='all')
    assert [row['iiko_product_id'] for row in full['items']] == [GUID_NEW]
    snapshot['bar1']['taps'].append({'tap_number': 7, 'status': 'active', 'current_beer': 'КЕГ Вудбридж ИПА 30 л',
                                     'iiko_product_id': GUID_OPEN, 'started_at': None})
    urgent = ul.queue(registry, _catalog(registry), snapshot, store.load())
    assert [(row['iiko_product_id'], row['registry_status']) for row in urgent['items']] == [
        (GUID_OPEN, 'skipped'), (GUID_NEW, 'new')]       # оба на кране, порядок по имени
    snapshot['bar1']['taps'].pop()
    registry = _registry()
    item = _propose(store)
    q = ul.queue(registry, _catalog(registry), snapshot, store.load())
    assert q['items'][0]['proposal']['status'] == 'proposed' and q['counts']['proposed'] == 1
    store.reject(item['id'], OWNER, 'не тот TAP')
    q = ul.queue(registry, _catalog(registry), snapshot, store.load())
    assert q['items'][0]['proposal']['review_note'] == 'не тот TAP' and q['counts']['waiting'] == 1
    item = _propose(store)
    store.confirm(item['id'], OWNER, registry)
    q = ul.queue(ul.apply(registry), _catalog(registry), snapshot, store.load())
    assert q['items'] == [] and q['counts']['total'] == 0
    with pytest.raises(ul.UntappdLinksError):
        ul.queue(registry, _catalog(registry), snapshot, store.load(), scope='soon')


def test_broken_file_is_never_overwritten(store):
    with open(store.data_file, 'w', encoding='utf-8') as f:
        f.write('{"schema_version": 1, "proposals": [{"broken": true}], "log": []}')
    with pytest.raises(ul.UntappdLinksUnavailable):
        store.load()
    with pytest.raises(ul.UntappdLinksUnavailable):
        _propose(store)
    assert json.load(open(store.data_file, encoding='utf-8'))['proposals'] == [{'broken': True}]
    # сайт при этом работает по встроенному реестру
    assert ul.apply(_registry()) == _registry()
    assert ul.live_names() == {'styles': {}, 'breweries': {}}


def test_preview_shows_the_card_that_will_be_used():
    """Карточка с этим id уже есть в реестре — в таплист пойдут её проверенные данные,
    а не то, что прислал агент; страница показывает именно их."""
    names = tp.load_names(tp.NAMES_PATH)
    item = {'untappd_beer_id': '6240484', 'url': 'https://untappd.com/b/festhaus-helles/6240484',
            'card': {'beer_name': 'Другое', 'brewery': 'X', 'style': 'IPA - American', 'abv_percent': 9},
            'names': {'style_ru': 'другое', 'brewery_short': None}}
    pv = ul.preview(item, names, _registry())
    assert pv['known_card'] and pv['card']['beer_name'] == 'Helles' and pv['card']['abv_percent'] == 4.5
    assert pv['line'] == 'Festhaus Helles — светлый лагер, 4,5%' and pv['style_from_dictionary']
    assert (pv['name'], pv['style_ru'], pv['abv'], pv['beer_name'], pv['brewery_short']) == (
        'Festhaus Helles', 'светлый лагер', '4,5', 'Helles', 'Festhaus')
    fresh = ul.preview(dict(item, untappd_beer_id='777'), names, _registry())
    assert not fresh['known_card'] and fresh['card']['beer_name'] == 'Другое'
