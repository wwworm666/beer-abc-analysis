"""Фиды Яндекса (/yandex): выбор цены 0,5 л, id по сорту, правки, снимок, маршруты.

Без сети и без app.py (он запускает фоновые задачи с боевыми токенами):
голый Flask только с yml_bp, пути данных подменяются на временные.
"""
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import pytest
from flask import Flask

from core import yml_overrides, yml_scheduler
from core.taplist_yml import beer_offers, build_yml, choose_serving, offer_id
from core.yml_feeds import KITCHEN_SCOPE, combine_offers, overrides_for_bar
from core.yml_overrides import (
    OverrideConflict, OverridesCorrupted, apply_changes, ensure_schema, load_document,
    migrate_v1, normalize_override, parse_price,
)


def serving(price, dish, date=None, liters='0.5', size=None):
    return {
        'portion_liters': liters, 'price_rub': price, 'dish_name': dish, 'size_name': size,
        'price_source': {'kind': 'iiko_price_order' if date else 'iiko_default_sale_price',
                         'date_from': date},
    }


def row(**extra):
    base = {
        'bar_id': 'bar1', 'tap_number': 3, 'iiko_product_id': 'keg-1',
        'mapping_status': 'verified', 'untappd_beer_id': 1001,
        'beer_name': 'Pauwel Kwak', 'brewery': 'Brouwerij Bosteels',
        'style': 'Belgian Strong', 'abv': 8.4, 'ibu': 18,
        'description': 'Янтарный эль.', 'description_source': 'untappd',
        'photo_url': 'https://untappd.example/kwak.jpg',
        'servings': [serving('1350.00', 'Квак (0,5)', '2026-03-01')],
        'price_status': 'verified', 'price_message': 'Обычный прайс iiko',
    }
    base.update(extra)
    return base


# ---------- выбор цены 0,5 л ----------

def test_takeaway_portion_never_sets_the_price():
    chosen, note, reason = choose_serving([
        serving('280.00', 'ВО Коникс Черри Руби (0,5) (б)', '2026-09-01'),
        serving('590.00', 'Коникс Черри Руби (0,5)', '2025-05-01'),
    ])
    assert chosen['price_rub'] == '590.00'
    assert note is None and reason is None


def test_takeaway_size_name_is_detected():
    chosen, _, _ = choose_serving([
        serving('350.00', 'Хеллес', '2026-01-01', size='0,5 (б)'),
        serving('310.00', 'Хеллес', '2026-01-01', size='0,5'),
    ])
    assert chosen['price_rub'] == '310.00'


def test_different_prices_take_the_newest_price_order_with_warning():
    chosen, note, reason = choose_serving([
        serving('1580.00', 'ВО Квак (0,5)', '2024-01-10'),
        serving('1350.00', 'Квак (0,5)', '2026-03-01'),
    ])
    assert chosen['dish_name'] == 'Квак (0,5)'
    assert reason is None
    assert '1580' in note and '1350' in note and 'свежего приказа' in note
    assert '10.01.2024' in note and '01.03.2026' in note


def test_same_newest_date_with_different_prices_is_not_guessed():
    chosen, note, reason = choose_serving([
        serving('270.00', 'Зомби Кейк (0,5)', '2026-03-01'),
        serving('770.00', 'Урхелль (0,5)', '2026-03-01'),
    ])
    assert chosen is None and note is None
    assert 'Оставьте в iiko одно блюдо' in reason


def test_different_prices_without_dates_are_not_guessed():
    chosen, _, reason = choose_serving([
        serving('270.00', 'А (0,5)'), serving('770.00', 'Б (0,5)'),
    ])
    assert chosen is None and 'самый свежий приказ не определить' in reason


def test_equal_prices_of_several_dishes_need_no_warning():
    chosen, note, _ = choose_serving([
        serving('490.00', 'А (0,5)', '2024-01-01'), serving('490', 'Б (0,5)', '2026-01-01'),
    ])
    assert chosen is not None and note is None


def test_missing_half_liter_explains_what_exists():
    chosen, _, reason = choose_serving([serving('220', 'Стаут (0,3)', liters='0.3'),
                                        serving('150', 'Стаут (0,25)', liters='0.25')])
    assert chosen is None
    assert reason == 'В iiko нет порции 0,5 л (есть: 0,25 л, 0,3 л)'


def test_only_takeaway_half_liter():
    _, _, reason = choose_serving([serving('300', 'Стаут (0,5) (б)', '2026-01-01')])
    assert reason == 'Порция 0,5 л есть только навынос'


# ---------- позиции пива ----------

def test_offer_id_follows_the_beer_not_the_tap():
    first, _ = beer_offers([row(tap_number=3)])
    moved, _ = beer_offers([row(tap_number=9)])
    assert first[0]['id'] == moved[0]['id'] == offer_id('bar1', '1001') == 'bar1-u1001-p05'


def test_same_beer_on_two_taps_is_one_offer_with_both_taps():
    items, excluded = beer_offers([row(tap_number=3), row(tap_number=5, iiko_product_id='keg-2')])
    assert len(items) == 1 and items[0]['taps'] == [3, 5]
    assert excluded == []


def test_same_name_from_different_breweries_are_two_offers():
    items, _ = beer_offers([
        row(beer_name='Helles', brewery='Festhaus', untappd_beer_id=1),
        row(beer_name='Helles', brewery='Jaws Brewery', untappd_beer_id=2, tap_number=4),
    ])
    assert [item['name'] for item in items] == ['Festhaus Helles, 0,5 л', 'Jaws Brewery Helles, 0,5 л']


def test_unverified_keg_is_listed_as_excluded_not_published():
    items, excluded = beer_offers([row(mapping_status='unverified', untappd_beer_id=None,
                                       beer_name='КЕГ Марстонс Ойстер Стаут 30 л')])
    assert items == []
    assert excluded[0]['taps'] == [3]
    assert 'уточните сорт' in excluded[0]['reason']


def test_beer_without_price_gets_iiko_reason():
    _, excluded = beer_offers([row(servings=[], price_message='Есть цена по расписанию: нужна проверка')])
    assert excluded[0]['reason'] == 'Есть цена по расписанию: нужна проверка'


def test_brewery_already_in_beer_name_is_not_repeated():
    items, _ = beer_offers([
        row(beer_name='Zubr Gold', brewery='Pivovar Zubr', untappd_beer_id=1),
        row(beer_name='Palm Spéciale', brewery='Brouwerij Palm', untappd_beer_id=2, tap_number=4),
    ])
    assert [item['name'] for item in items] == ['Zubr Gold, 0,5 л', 'Palm Spéciale, 0,5 л']
    assert items[0]['vendor'] == 'Pivovar Zubr'


def test_description_has_no_duplicates_double_dots_tap_or_untappd_notes():
    items, _ = beer_offers([
        row(description='Светлое пиво. NB: The bottles are different.', untappd_beer_id=1),
        row(description='Стиль: Witbier. Крепость: 5%. Горечь: 11 IBU.',
            description_source='verified_characteristics', style='Witbier', abv=5, ibu=11,
            untappd_beer_id=2, tap_number=4),
        row(description='Мягкий, с нотами хлеба…', untappd_beer_id=3, tap_number=5),
        row(description='Fresh white bread....', untappd_beer_id=4, tap_number=6),
    ])
    first, second, third, fourth = (item['description'] for item in items)
    assert fourth.startswith('Fresh white bread… Стиль:')
    assert first == 'Светлое пиво. Стиль: Belgian Strong. Крепость: 8,4%. Горечь: 18 IBU. Порция: 0,5 л.'
    assert 'NB' not in first and 'Кран' not in first
    assert second == 'Стиль: Witbier. Крепость: 5%. Горечь: 11 IBU. Порция: 0,5 л.'
    assert third.startswith('Мягкий, с нотами хлеба… Стиль:') and '….' not in third


def test_partial_price_status_becomes_a_warning():
    items, _ = beer_offers([row(price_status='partial', price_message='Свободная цена: нужна проверка')])
    assert any('Свободная цена' in text for text in items[0]['warnings'])


def test_xml_uses_rub_and_no_offer_url():
    items, _ = beer_offers([row()])
    xml = build_yml(items=items, when='2026-09-27T05:00:00+03:00')
    root = ET.fromstring(xml)
    assert root.find('shop/currencies/currency').get('id') == 'RUB'
    offer = root.find('shop/offers/offer')
    assert offer.findtext('currencyId') == 'RUB'
    assert offer.find('url') is None
    assert offer.findtext('price') == '1350.00'
    assert root.findtext('shop/url') == 'https://beerkultura.ru'


# ---------- разделы ----------

def test_sections_draft_first_and_dish_without_section_is_not_dessert():
    rows = combine_offers(
        [{'id': 'a', 'name': 'Фри', 'price': '370', 'category_id': '2'},
         {'id': 'b', 'name': 'Без раздела', 'price': '100', 'category_id': ''},
         {'id': 'c', 'name': 'Брауни', 'price': '490', 'category_id': '7'}],
        [{'id': 'bar1-u1-p05', 'name': 'Сидр, 0,5 л', 'price': '400'}],
    )
    assert [(item['id'], item['category_name']) for item in rows] == [
        ('bar1-u1-p05', 'Разливное'), ('a', 'Горячие закуски'), ('c', 'Десерты'), ('b', 'Меню')]
    assert [item['kind'] for item in rows] == ['beer', 'kitchen', 'kitchen', 'kitchen']


# ---------- правки ----------

@pytest.mark.parametrize('raw, expected', [
    ('1 000,5', '1000.50'), ('350', '350.00'), ('0,125', '0.13'), ('1\xa0000', '1000.00'),
    ('0.001', None), ('0', None), ('-5', None), ('1e30', None), ('100000.01', None),
    ('abc', None), ('', ''), (None, ''),
])
def test_price_parsing(raw, expected):
    assert parse_price(raw) == expected


def test_override_cleanup_and_error_names_the_item():
    stored = normalize_override({'name': 'Фри\x00\x07 большая', 'description': 'Строка 1\nСтрока 2',
                                 'hidden': 'false'})
    assert stored == {'hidden': False, 'name': 'Фри большая', 'description': 'Строка 1 Строка 2'}
    with pytest.raises(ValueError, match='«Фри»: цена'):
        normalize_override({'price': 'много'}, 'Фри')


def test_kitchen_edit_is_common_and_clears_bar_edits(tmp_path):
    path = str(tmp_path / 'ov.json')
    yml_overrides.save_overrides('bar2', {'ttk-s02': {'hidden': True}}, path)
    apply_changes('bar1', {'ttk-s02': {'name': 'Картофель фри большой', 'hidden': False}}, {'ttk-s02'}, path)
    feeds = load_document(path)['feeds']
    assert feeds[KITCHEN_SCOPE]['ttk-s02'] == {'hidden': False, 'name': 'Картофель фри большой'}
    assert 'bar2' not in feeds
    for bar in ('bar1', 'bar2', 'bar3', 'bar4'):
        assert overrides_for_bar(feeds, bar)['ttk-s02']['name'] == 'Картофель фри большой'


def test_beer_edit_stays_in_its_bar_and_empty_edit_removes_it(tmp_path):
    path = str(tmp_path / 'ov.json')
    apply_changes('bar3', {'bar3-u7-p05': {'price': '450'}}, set(), path)
    assert load_document(path)['feeds']['bar3']['bar3-u7-p05'] == {'hidden': False, 'price': '450.00'}
    apply_changes('bar3', {'bar3-u7-p05': {'price': '', 'name': '', 'description': ''}}, set(), path)
    assert load_document(path)['feeds'] == {}
    assert load_document(path)['schema'] == 2


def test_conflict_writes_nothing(tmp_path):
    path = str(tmp_path / 'ov.json')
    apply_changes('bar1', {'bar1-u7-p05': {'price': '450'}}, set(), path)
    seen = {'hidden': False, 'price': '450.00'}
    apply_changes('bar1', {'bar1-u7-p05': {'price': '470', 'base': seen}}, set(), path)
    with pytest.raises(OverrideConflict) as conflict:
        apply_changes('bar1', {'bar1-u7-p05': {'price': '999', 'base': seen},
                               'bar1-u8-p05': {'hidden': True, 'base': None}}, set(), path)
    assert conflict.value.ids == ['bar1-u7-p05']
    feeds = load_document(path)['feeds']
    assert feeds['bar1'] == {'bar1-u7-p05': {'hidden': False, 'price': '470.00'}}


def test_corrupted_file_falls_back_to_backup_then_refuses(tmp_path):
    path = str(tmp_path / 'ov.json')
    apply_changes('bar1', {'a': {'hidden': True}}, set(), path)
    apply_changes('bar1', {'b': {'hidden': True}}, set(), path)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('{broken')
    assert set(load_document(path)['feeds']['bar1']) == {'a'}
    with open(path + '.bak', 'w', encoding='utf-8') as handle:
        handle.write('also broken')
    with pytest.raises(OverridesCorrupted):
        load_document(path)


def test_migration_moves_tap_edits_to_the_beer_on_that_tap_now():
    old = {
        'bar1': {'bar1-tap3-p05': {'hidden': False, 'price': '1490.00'},
                 'bar1-tap9-p05': {'hidden': True}},
        'taplist-bar2': {'bar2-tap1-p05': {'hidden': False, 'name': 'Стаут'}},
        'kitchen-bar1': {'ttk-s19': {'hidden': True}, 'ttk-s02': {'hidden': False, 'price': '390.00'}},
        'kitchen-bar2': {'ttk-s19': {'hidden': True}},
        'kitchen-bar3': {'ttk-s19': {'hidden': True}},
        'kitchen-bar4': {'ttk-s19': {'hidden': True}},
    }
    feeds, report = migrate_v1(old, {'ttk-s19', 'ttk-s02'}, {('bar1', 3): '1001', ('bar2', 1): '55'})
    assert feeds[KITCHEN_SCOPE] == {'ttk-s19': {'hidden': True}}
    assert feeds['bar1']['ttk-s02'] == {'hidden': False, 'price': '390.00'}
    assert feeds['bar1']['bar1-u1001-p05'] == {'hidden': False, 'price': '1490.00', 'migrated_from_tap': 3}
    assert feeds['bar2']['bar2-u55-p05']['name'] == 'Стаут'
    assert not any('tap9' in key for bucket in feeds.values() for key in bucket)
    assert any('кран 9' in line for line in report)


def test_ensure_schema_runs_once_and_keeps_the_old_file(tmp_path):
    path = tmp_path / 'ov.json'
    path.write_text(json.dumps({'feeds': {'bar1': {'bar1-tap3-p05': {'hidden': True}}}}), encoding='utf-8')
    calls = []

    def taps():
        calls.append(1)
        return {('bar1', 3): '1001'}

    report = ensure_schema(set(), taps, str(path))
    assert report and calls == [1]
    document = load_document(str(path))
    assert document['schema'] == 2
    assert document['feeds']['bar1']['bar1-u1001-p05']['migrated_from_tap'] == 3
    assert (tmp_path / 'ov.json.v1.bak').exists()
    assert ensure_schema(set(), taps, str(path)) is None and calls == [1]


# ---------- снимок ----------

MSK = yml_scheduler.MOSCOW


def test_old_snapshot_schema_is_refreshed_immediately():
    night = datetime(2026, 9, 27, 3, 0, tzinfo=MSK)
    assert yml_scheduler.needs_refresh(night, None, schema_ok=False) is True
    assert yml_scheduler.needs_refresh(night, None, schema_ok=True) is False


def _patch_taplist(monkeypatch, rows_by_bar):
    import routes.taps as taps

    def fake(bar_id, active_only=True, sources=None):
        value = rows_by_bar.get(bar_id, [])
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(taps, 'load_reviewed_taplist', fake)
    monkeypatch.setattr(taps, 'fetch_price_sources', lambda: {'prices': []})


def test_empty_beer_with_active_taps_keeps_yesterdays_list(monkeypatch):
    _patch_taplist(monkeypatch, {'bar1': [row(servings=[], price_message='Нет цены')]})
    now = datetime(2026, 9, 27, 5, 0, tzinfo=MSK)
    old = {'beer': [{'id': 'bar1-u1-p05'}], 'beer_updated_at': (now - timedelta(hours=24)).isoformat()}
    state = yml_scheduler._bar_snapshot('bar1', {}, old, now)
    assert state['beer'] == old['beer']
    assert 'Пиво не обновилось (0 позиций пива при 1 активных кранах)' in state['error']
    assert state['excluded'][0]['reason'] == 'Нет цены'
    too_old = {**old, 'beer_updated_at': (now - timedelta(hours=49)).isoformat()}
    state = yml_scheduler._bar_snapshot('bar1', {}, too_old, now)
    assert state['beer'] == [] and 'не показывается' in state['error']


def test_bar_failure_is_reported_and_others_are_fine(monkeypatch):
    _patch_taplist(monkeypatch, {'bar1': [row()], 'bar2': RuntimeError('нет данных')})
    now = datetime(2026, 9, 27, 5, 0, tzinfo=MSK)
    good = yml_scheduler._bar_snapshot('bar1', {}, {}, now)
    assert good['error'] is None and good['beer'][0]['id'] == 'bar1-u1001-p05'
    bad = yml_scheduler._bar_snapshot('bar2', {}, {}, now)
    assert bad['beer'] == [] and 'RuntimeError' in bad['error']


def test_refresh_writes_beer_only_snapshot_and_refuses_when_busy(monkeypatch, tmp_path):
    _patch_taplist(monkeypatch, {'bar1': [row()]})
    monkeypatch.setattr(yml_scheduler, 'RUN_LOCK_PATH', str(tmp_path / 'run.lock'))
    path = str(tmp_path / 'snap.json')
    data = yml_scheduler.refresh_snapshot(path, wait=0)
    assert data['schema'] == 2 and set(data['bars']) == {'bar1', 'bar2', 'bar3', 'bar4'}
    assert data['bars']['bar1']['beer'][0]['kind'] == 'beer'
    assert yml_scheduler.snapshot_ok(yml_scheduler.load_snapshot(path))
    import portalocker
    with portalocker.Lock(str(tmp_path / 'run.lock'), timeout=1):
        with pytest.raises(yml_scheduler.RefreshBusy):
            yml_scheduler.refresh_snapshot(path, wait=0)


def test_alarm_text_escapes_and_names_bars():
    text = yml_scheduler.alarm_text({'bar2': 'Пиво <не> обновилось', 'all': 'iiko'})
    assert 'Лиговский: Пиво &lt;не&gt; обновилось' in text and 'Все бары: iiko' in text


# ---------- маршруты ----------

@pytest.fixture()
def client(monkeypatch, tmp_path):
    import routes.yml_feeds as feeds
    overrides = str(tmp_path / 'ov.json')
    snapshot = str(tmp_path / 'snap.json')
    monkeypatch.setattr(yml_overrides, 'overrides_path', lambda: overrides)
    monkeypatch.setattr(yml_scheduler, 'snapshot_path', lambda: snapshot)
    monkeypatch.setattr(yml_scheduler, 'RUN_LOCK_PATH', str(tmp_path / 'run.lock'))
    monkeypatch.setattr(feeds, '_schema_ready', False)
    _patch_taplist(monkeypatch, {'bar1': [row(), row(tap_number=4, untappd_beer_id=None,
                                                     mapping_status='unverified', beer_name='КЕГ Икс')]})
    app = Flask('test_yml_feeds')
    app.register_blueprint(feeds.yml_bp)
    return app.test_client()


def test_detail_lists_offers_excluded_and_no_store(client):
    response = client.get('/api/yml/feeds/bar1')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    data = response.get_json()
    assert data['snapshot']['source'] == 'live'
    beer = [offer for offer in data['offers'] if offer['kind'] == 'beer']
    assert beer[0]['id'] == 'bar1-u1001-p05' and beer[0]['price'] == '1350.00'
    assert data['counts']['excluded'] == 1 and data['excluded'][0]['taps'] == [4]
    assert data['counts']['kitchen'] == 29
    assert client.get('/api/yml/feeds/bar9').status_code == 404


def test_save_conflict_and_public_feed(client):
    first = client.put('/api/yml/feeds/bar1', json={'changes': {
        'bar1-u1001-p05': {'hidden': False, 'price': '1400', 'name': '', 'description': '', 'base': None},
        'ttk-s02': {'hidden': True, 'name': '', 'price': '', 'description': '', 'base': None},
    }})
    assert first.status_code == 200
    beer = next(offer for offer in first.get_json()['offers'] if offer['id'] == 'bar1-u1001-p05')
    assert beer['price'] == '1400.00' and beer['source_price'] == '1350.00'
    stale = client.put('/api/yml/feeds/bar1', json={'changes': {
        'bar1-u1001-p05': {'hidden': False, 'price': '1500', 'base': None}}})
    assert stale.status_code == 409 and stale.get_json()['conflicts'] == ['bar1-u1001-p05']
    bad = client.put('/api/yml/feeds/bar1', json={'changes': {
        'bar1-u1001-p05': {'price': 'дорого', 'label': 'Kwak'}}})
    assert bad.status_code == 400 and '«Kwak»' in bad.get_json()['error']
    xml = client.get('/feeds/kitchen/bar4')
    assert xml.status_code == 200 and xml.headers['Content-Type'].startswith('application/xml')
    ids = [offer.get('id') for offer in ET.fromstring(xml.data).iter('offer')]
    assert 'ttk-s02' not in ids, 'скрытое блюдо кухни скрыто во всех барах'
    feed1 = ET.fromstring(client.get('/feeds/kitchen/bar1').data)
    kwak = next(offer for offer in feed1.iter('offer') if offer.get('id') == 'bar1-u1001-p05')
    assert kwak.findtext('price') == '1400.00' and kwak.findtext('currencyId') == 'RUB'


def test_refresh_needs_json_and_builds_snapshot(client):
    assert client.post('/api/yml/refresh', data='x').status_code == 415
    response = client.post('/api/yml/refresh', json={})
    assert response.status_code == 200
    assert response.get_json()['bars']['bar1']['beer'] == 1
    detail = client.get('/api/yml/feeds/bar1').get_json()
    assert detail['snapshot']['source'] == 'snapshot'
    listing = client.get('/api/yml/feeds').get_json()
    assert [feed['id'] for feed in listing['feeds']] == ['bar1', 'bar2', 'bar3', 'bar4']
    assert listing['feeds'][0]['beer'] == 1 and listing['feeds'][0]['excluded'] == 1


def test_acknowledged_warnings_stop_counting_until_the_situation_changes(client, monkeypatch):
    conflict = [serving('1580.00', 'ВО Квак (0,5)', '2024-01-10'), serving('1350.00', 'Квак (0,5)', '2026-03-01')]
    _patch_taplist(monkeypatch, {'bar1': [row(servings=conflict)], 'bar4': [row(bar_id='bar4', servings=conflict)],
                                 'bar2': [row(bar_id='bar2', mapping_status='unverified', untappd_beer_id=None)]})
    client.post('/api/yml/refresh', json={})
    listing = {feed['id']: feed for feed in client.get('/api/yml/feeds').get_json()['feeds']}
    assert listing['bar1']['attention'] == 1 and listing['bar2']['attention'] == 1 and listing['bar3']['attention'] == 0
    detail = client.get('/api/yml/feeds/bar1').get_json()
    notice = detail['offers'][0]['notices'][0]
    assert notice['acked'] is False and 'свежего приказа' in notice['text']
    assert detail['counts']['notices_open'] == 1
    acked = client.post('/api/yml/feeds/bar1/ack', json={'keys': [notice['key']], 'acked': True})
    assert acked.status_code == 200
    assert acked.get_json()['offers'][0]['notices'][0]['acked'] is True
    assert acked.get_json()['counts']['notices_open'] == 0
    listing = {feed['id']: feed for feed in client.get('/api/yml/feeds').get_json()['feeds']}
    assert listing['bar1']['attention'] == 0
    assert listing['bar4']['attention'] == 0, 'тот же текст предупреждения в другом баре тоже отмечен'
    excluded = client.get('/api/yml/feeds/bar2').get_json()['excluded'][0]
    assert excluded['acked'] is False
    client.post('/api/yml/feeds/bar2/ack', json={'keys': [excluded['key']]})
    assert client.get('/api/yml/feeds/bar2').get_json()['excluded'][0]['acked'] is True
    # отметка переживает сохранение правок
    client.put('/api/yml/feeds/bar1', json={'changes': {'ttk-s02': {'hidden': True}}})
    assert client.get('/api/yml/feeds/bar1').get_json()['offers'][0]['notices'][0]['acked'] is True
    # сменилась цена в iiko — новое предупреждение, отметки нет
    changed = [serving('1590.00', 'ВО Квак (0,5)', '2024-01-10'), serving('1350.00', 'Квак (0,5)', '2026-03-01')]
    _patch_taplist(monkeypatch, {'bar1': [row(servings=changed)]})
    client.post('/api/yml/refresh', json={})
    assert client.get('/api/yml/feeds/bar1').get_json()['offers'][0]['notices'][0]['acked'] is False
    # вернуть и проверка ключей
    client.post('/api/yml/feeds/bar1/ack', json={'keys': [notice['key']], 'acked': False})
    assert client.post('/api/yml/feeds/bar1/ack', json={'keys': ['../../x']}).status_code == 400
    assert client.post('/api/yml/feeds/bar1/ack', json={}).status_code == 400


def test_orphan_override_is_listed_and_can_be_removed(client):
    client.put('/api/yml/feeds/bar1', json={'changes': {'bar1-u9999-p05': {'hidden': True}}})
    data = client.get('/api/yml/feeds/bar1').get_json()
    assert [orphan['id'] for orphan in data['orphans']] == ['bar1-u9999-p05']
    removed = client.put('/api/yml/feeds/bar1', json={'changes': {'bar1-u9999-p05': {
        'hidden': False, 'name': '', 'price': '', 'description': '',
        'base': data['orphans'][0]['override']}}})
    assert removed.status_code == 200 and removed.get_json()['orphans'] == []
