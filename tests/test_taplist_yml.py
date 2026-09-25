"""YML-фид таплиста: цена, дедуп, экранирование. Сети нет."""
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

from core.auth_guard import PUBLIC_ENDPOINTS
from core.taplist_yml import build_yml, offers_for
from core.yml_feeds import feed_catalog
from core.yml_overrides import normalize_override, save_overrides


ROW = {
    'bar_id': 'bar2',
    'bar': 'Лиговский',
    'tap_number': 4,
    'beer_name': 'Hell & Bock',
    'brewery': 'Zavod',
    'style': 'Helles',
    'abv': 4.8,
    'ibu': 18,
    'description': 'Светлое <b>пиво</b>',
    'photo_url': 'https://untappd.example/photo.jpg',
    'servings': [
        {'portion_liters': '0.5', 'price_rub': '310.00'},
        {'portion_liters': '0.3', 'price_rub': '220'},
    ],
}


def _offers(xml):
    root = ET.fromstring(xml)
    return root.find('shop').find('offers').findall('offer')


def test_feed_lists_priced_portions_with_required_fields():
    xml = build_yml([ROW], when='2026-09-25T12:00:00+03:00')
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(xml)
    assert root.tag == 'yml_catalog'
    assert root.get('date') == '2026-09-25T12:00:00+03:00'
    shop = root.find('shop')
    assert shop.findtext('name') == 'Пивная культура, Лиговский'
    assert shop.findtext('delivery') == 'false'
    assert shop.findtext('pickup') == 'true'
    offers = _offers(xml)
    assert [offer.findtext('price') for offer in offers] == ['310.00', '220.00']
    half = offers[0]
    assert half.get('available') == 'true'
    assert half.findtext('currencyId') == 'RUR'
    assert half.findtext('categoryId') == '2'
    assert half.findtext('name') == 'Zavod Hell & Bock, 0,5 л'
    assert half.findtext('vendor') == 'Zavod'
    assert half.findtext('picture') == 'https://untappd.example/photo.jpg'
    assert 'Светлое <b>пиво</b>' in half.findtext('description')
    assert 'Hell &amp; Bock' in xml


def test_unpriced_duplicate_and_http_photo_are_dropped():
    second = dict(ROW, tap_number=9)
    bare = {
        'bar_id': 'bar1', 'tap_number': 1, 'beer_name': 'Без цены',
        'photo_url': 'http://insecure.example/a.jpg', 'servings': [],
    }
    items = offers_for([ROW, second, bare])
    assert len(items) == 2
    assert all(item['picture'].startswith('https://') for item in items)
    assert bare['beer_name'] not in {item['name'] for item in items}


def test_two_bars_become_two_categories():
    other = dict(ROW, bar_id='bar4', beer_name='Другое', tap_number=1)
    xml = build_yml([ROW, other], when='2026-09-25T12:00:00+03:00')
    names = [node.text for node in ET.fromstring(xml).find('shop/categories')]
    assert names == ['Лиговский', 'Варшавская']
    assert ET.fromstring(xml).findtext('shop/name') == 'Пивная культура'


def test_clock_uses_moscow_offset():
    moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=ZoneInfo('Europe/Moscow'))
    xml = build_yml([], when=moment.replace(microsecond=0).isoformat())
    assert 'date="2026-01-02T03:04:05+03:00"' in xml


def test_yml_route_is_public():
    assert 'taps.taplist_yml' in PUBLIC_ENDPOINTS


def test_page_lists_taplist_and_kitchen_for_every_bar():
    feeds = feed_catalog()
    assert [feed['id'] for feed in feeds] == [
        'taplist-bar1', 'taplist-bar2', 'taplist-bar3', 'taplist-bar4',
        'kitchen-bar1', 'kitchen-bar2', 'kitchen-bar3', 'kitchen-bar4',
    ]
    assert feeds[-1]['public_path'] == '/feeds/kitchen/bar4'


def test_override_roundtrip_keeps_feeds_separate(tmp_path):
    path = tmp_path / 'yml_overrides.json'
    save_overrides('kitchen-bar1', {'ttk-s02': {'hidden': True, 'name': 'Фри'}}, path)
    save_overrides('kitchen-bar2', {'ttk-s02': {'price': '10'}}, path)
    from core.yml_overrides import load_overrides
    stored = load_overrides(path)
    assert stored['kitchen-bar1']['ttk-s02']['hidden'] is True
    assert stored['kitchen-bar1']['ttk-s02']['name'] == 'Фри'
    assert stored['kitchen-bar2']['ttk-s02']['price'] == '10.00'
    assert 'name' not in stored['kitchen-bar2']['ttk-s02']
    try:
        normalize_override({'price': 'нет'})
    except ValueError:
        return
    raise AssertionError('bad price must be rejected')


def test_hidden_and_renamed_offer_changes_the_file():
    items = offers_for([ROW])
    items[0]['hidden'] = True
    items[1]['name'] = 'Своё имя'
    xml = build_yml(items=items, when='2026-09-25T12:00:00+03:00')
    offers = _offers(xml)
    assert len(offers) == 1
    assert offers[0].findtext('name') == 'Своё имя'
    assert '0,5' not in offers[0].findtext('name')
