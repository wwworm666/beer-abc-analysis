"""Сверка прайсов на Яндекс Картах с нашими файлами (/yandex, 2026-09-29).

Страницы Карт — синтетические, в том же формате, что встраивает Яндекс
(fullObjects, fullObjectsCount, relevance, source). Без сети и без app.py.
"""
import json

import pytest
from flask import Flask

from core import yandex_maps_status as maps


def page(items_by_category, upload='2026-09-28T09:38:57.8Z', update='2026-09-25T14:21:45.5Z', noise=True):
    categories = [{'categoryName': name, 'categoryItems': [
        {'title': title, 'description': '', 'photoLink': 'https://x/{size}', 'price': price, 'currency': '₽'}
        for title, price in items]} for name, items in items_by_category.items()]
    full = json.dumps({'hasPhotos': True, 'rubric': 'bar', 'categories': categories}, ensure_ascii=False)
    count = sum(len(items) for items in items_by_category.values())
    small = json.dumps({'categories': [{'categoryName': 'Пиво', 'categoryItems': []}]})
    return ('<html><title>Цены — Яндекс Карты</title><script>{"state":{'
            + (f'"preview":{{"fullObjects":{small}}},' if noise else '')
            + f'"prices":{{"fullObjects":{full},"fullObjectsCount":{count},'
            + f'"relevance":{{"lastUploadTime":"{upload}","lastUpdateTime":"{update}"}},'
            + '"source":{"id":"TYCOON","name":"Представитель организации"}}}}</script></html>')


def test_all_bars_have_a_maps_card():
    assert maps.ORG_BY_BAR == {'bar1': 48832698165, 'bar2': 161689116864,
                               'bar3': 31434555884, 'bar4': 149836365055}
    assert maps.maps_url(48832698165) == 'https://yandex.ru/maps/org/48832698165/prices/'


def test_parse_takes_the_fullest_price_block_and_both_times():
    parsed = maps.parse_prices_page(page({'Пиво': [('Pauwel Kwak, 0,5 л', '1580')],
                                          'Закуски': [('Солёный арахис', '190')]}))
    assert [(i['title'], i['price'], i['category']) for i in parsed['items']] == [
        ('Pauwel Kwak, 0,5 л', '1580', 'Пиво'), ('Солёный арахис', '190', 'Закуски')]
    assert parsed['count'] == 2
    assert parsed['last_upload'].startswith('2026-09-28T09:38')
    assert parsed['last_update'].startswith('2026-09-25T14:21')
    assert parsed['source'] == 'Представитель организации'


def test_captcha_or_unknown_markup_is_an_error_not_an_empty_price_list():
    with pytest.raises(maps.MapsPageError, match='не робот'):
        maps.parse_prices_page('<html><form action="/showcaptcha">...</form></html>')
    with pytest.raises(maps.MapsPageError, match='разметку'):
        maps.parse_prices_page('<html><title>Карты</title></html>')
    assert maps.parse_prices_page('{"fullObjectsCount":0}')['items'] == []


def test_compare_by_name_and_price():
    ours = [{'name': 'Pauwel Kwak, 0,5 л', 'price': '1350.00'},
            {'name': 'Солёный арахис', 'price': '190'},
            {'name': 'Zubr Gold, 0,5 л', 'price': '450.00'}]
    on_maps = [{'title': 'pauwel  kwak, 0,5 л', 'price': '1580'},
               {'title': 'Соленый арахис', 'price': '190'},
               {'title': 'Pivovar Zubr Zubr Gold, 0,5 л', 'price': '450'},
               {'title': 'Пицца Маргарита', 'price': '790'}]
    diff = maps.compare(ours, on_maps)
    assert diff['price'] == [{'title': 'Pauwel Kwak, 0,5 л', 'file': '1350.00', 'maps': '1580'}]
    assert diff['missing'] == ['Zubr Gold, 0,5 л']
    assert diff['extra'] == ['Pivovar Zubr Zubr Gold, 0,5 л', 'Пицца Маргарита']
    assert diff['total'] == 4
    assert maps.compare([{'name': 'Фри', 'price': '1 350'}], [{'title': 'Фри', 'price': '1350,00'}])['total'] == 0


def stored(items, upload, update, **extra):
    return {'bar1': {'items': [{'title': t, 'price': p} for t, p in items], 'last_upload': upload,
                     'last_update': update, 'checked_at': '2026-09-29T15:00:00+03:00', 'error': None, **extra}}


def test_states_synced_review_waiting_error_unknown():
    ours = [{'name': 'Kwak', 'price': '1350.00'}]
    synced = maps.status_for('bar1', ours, stored([('Kwak', '1350')], '2026-09-28T09:00:00Z', '2026-09-28T10:00:00Z'))
    assert synced['state'] == 'synced' and synced['diff']['total'] == 0
    assert synced['last_update'] == '2026-09-28T13:00:00+03:00'
    review = maps.status_for('bar1', ours, stored([('Kwak', '1580')], '2026-09-28T09:38:00Z', '2026-09-25T14:21:00Z'))
    assert review['state'] == 'review' and review['diff']['price'][0]['maps'] == '1580'
    waiting = maps.status_for('bar1', ours, stored([('Kwak', '1580')], '2026-09-25T14:00:00Z', '2026-09-25T14:21:00Z'))
    assert waiting['state'] == 'waiting'
    failed = maps.status_for('bar1', ours, {'bar1': {'error': 'Карты ответили кодом 503', 'attempt_at': 'x'}})
    assert failed['state'] == 'error' and '503' in failed['error']
    assert maps.status_for('bar1', ours, {})['state'] == 'unknown'
    stale = maps.status_for('bar1', ours, stored([('Kwak', '1350')], None, None, error='капча'))
    assert stale['state'] == 'synced' and stale['error'] == 'капча'


class FakeResponse:
    def __init__(self, status, text):
        self.status_code, self.text = status, text


def test_refresh_keeps_last_good_prices_when_a_check_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(maps, 'RUN_LOCK_PATH', str(tmp_path / 'run.lock'))
    path = str(tmp_path / 'maps.json')
    good = page({'Пиво': [('Kwak', '1580')]})
    maps.refresh(['bar1', 'bar2'], get=lambda url, **kw: FakeResponse(200, good), path=path, sleep=lambda s: None)
    first = maps.load_status(path)
    assert first['bar1']['items'][0]['price'] == '1580' and first['bar1']['error'] is None
    assert first['bar2']['org_id'] == 161689116864
    maps.refresh(['bar1'], get=lambda url, **kw: FakeResponse(429, ''), path=path, sleep=lambda s: None)
    second = maps.load_status(path)
    assert second['bar1']['items'][0]['price'] == '1580', 'прошлый удачный снимок не стирается'
    assert second['bar1']['error'] == 'Карты ответили кодом 429'
    assert second['bar1']['checked_at'] == first['bar1']['checked_at']
    # кнопка сразу после проверки — без повторного запроса к Картам
    calls = []
    maps.refresh(['bar1'], get=lambda url, **kw: calls.append(url) or FakeResponse(200, good),
                 path=path, manual=True, sleep=lambda s: None)
    assert calls == []


def test_routes_show_state_and_check_button(tmp_path, monkeypatch):
    from core import yml_overrides, yml_scheduler
    import routes.taps as taps
    import routes.yml_feeds as feeds
    monkeypatch.setattr(yml_overrides, 'overrides_path', lambda: str(tmp_path / 'ov.json'))
    monkeypatch.setattr(yml_scheduler, 'snapshot_path', lambda: str(tmp_path / 'snap.json'))
    monkeypatch.setattr(yml_scheduler, 'RUN_LOCK_PATH', str(tmp_path / 'run.lock'))
    monkeypatch.setattr(maps, 'status_path', lambda: str(tmp_path / 'maps.json'))
    monkeypatch.setattr(maps, 'RUN_LOCK_PATH', str(tmp_path / 'maps.lock'))
    monkeypatch.setattr(maps, 'PAUSE_BETWEEN_BARS', 0)
    monkeypatch.setattr(feeds, '_schema_ready', False)
    monkeypatch.setattr(taps, 'load_reviewed_taplist', lambda bar_id=None, active_only=True, sources=None: [])
    monkeypatch.setattr(taps, 'fetch_price_sources', lambda: {})
    monkeypatch.setattr(maps, 'fetch_bar', lambda bar, get=None: maps.parse_prices_page(
        page({'Горячие закуски': [('Картофель фри', '370')],
              'Пицца': [('Пицца Маргарита со страчателлой', '790')],
              'Пиво': [('Старое пиво, 0,5 л', '420')]})))
    app = Flask('maps_routes')
    app.register_blueprint(feeds.yml_bp)
    client = app.test_client()

    assert client.get('/api/yml/feeds/bar1').get_json()['maps']['state'] == 'unknown'
    assert client.post('/api/yml/maps/check', data='x').status_code == 415
    assert client.post('/api/yml/maps/check', json={'bar_id': 'bar9'}).status_code == 404
    checked = client.post('/api/yml/maps/check', json={})
    assert checked.status_code == 200 and set(checked.get_json()['bars']) == {'bar1', 'bar2', 'bar3', 'bar4'}
    detail = client.get('/api/yml/feeds/bar1').get_json()['maps']
    assert detail['state'] == 'review'
    assert 'Картофель фри' not in detail['diff']['missing']
    assert 'Пицца Маргарита со страчателлой' not in detail['diff']['extra']
    assert detail['diff']['extra'] == ['Старое пиво, 0,5 л']
    listing = client.get('/api/yml/feeds').get_json()['feeds']
    assert listing[0]['maps'] is None or listing[0]['maps']['state'] in ('review', 'waiting', 'synced')
