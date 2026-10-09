"""Реестр Untappd — единственный источник правды о пиве (решение владельца 2026-10-04).

Проверяется, что потребители, кроме сайта и поста, берут сорта только из реестра:
граф знаний (knowledge_graph/etl/registry_beers.py) и webhook-вариант гостевого бота
(telegram_webhook.taplist_messages). Основной бот — tests/test_taplist_polling.py,
строки таплиста — tests/test_taplist_post.py.
"""
import importlib
import sys

from tests.test_taplist_post import FakeManager, GUID_X20, POST, REGISTRY, _card, _row, ev, tap


def test_graph_beers_come_from_registry():
    from knowledge_graph.etl.registry_beers import registry_beer_rows
    beers, contains = registry_beer_rows(REGISTRY)
    assert [(b['name'], b['untappd_id'], b['untappd_url']) for b in beers] == [
        ('Festhaus Helles', '201', 'https://untappd.com/b/beer/201'),
        ('Festhaus Weissbier', '202', 'https://untappd.com/b/beer/202')]
    assert beers[0]['abv'] == 4.5 and beers[0]['style'] == 'Lager - Helles'
    # две кеги (30 и 20 л) — один сорт; связь по точному имени товара iiko
    assert sorted((c['keg_name'], c['beer_name']) for c in contains) == [
        ('КЕГ 201 44', 'Festhaus Helles'), ('КЕГ 201 55', 'Festhaus Helles'), ('КЕГ 202 66', 'Festhaus Weissbier')]


def test_graph_same_display_name_does_not_merge_beers():
    guid_z = '77777777-7777-4777-8777-777777777777'
    registry = {'schema_version': 1,
                'products': dict(REGISTRY['products'], **{guid_z: _row(guid_z, '203')}),
                'beers': dict(REGISTRY['beers'], **{'203': _card('203', 'Helles')})}
    from knowledge_graph.etl.registry_beers import registry_beer_rows
    names = sorted(b['name'] for b in registry_beer_rows(registry)[0])
    assert names == ['Festhaus Helles', 'Festhaus Helles #203', 'Festhaus Weissbier']


def test_webhook_bot_taplist_uses_registry(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', '123456:TEST')
    sys.modules.pop('telegram_webhook', None)
    tw = importlib.import_module('telegram_webhook')
    from core import taplist_post

    real = taplist_post.bar_message_html
    monkeypatch.setattr(taplist_post, 'bar_message_html',
                        lambda manager, bar_id, title: real(manager, bar_id, title, moment=POST, registry=REGISTRY))
    snapshot = {'bar2': {'name': 'Лиговский', 'taps': [
        tap(5, GUID_X20, '2026-09-20T12:00:00+03:00', [ev('2026-09-20T12:00:00+03:00', 'start', GUID_X20)])]}}
    assert tw.taplist_messages('bar2', FakeManager(snapshot)) == [
        '<b>Лиговский</b>\n\n5. <a href="https://untappd.com/b/beer/201">Festhaus Helles</a> — светлый лагер, 4,5%']
    # без менеджера и при сбое бара — извинение вместо молчания
    assert tw.taplist_messages('bar2', None) == [tw.TAPLIST_ERROR_TEXT]
    assert tw.taplist_messages('bar1', FakeManager(snapshot)) == [tw.TAPLIST_ERROR_TEXT]
    assert not hasattr(tw, 'find_beer_info_local') and not hasattr(tw, 'get_taplist_data')
    sys.modules.pop('telegram_webhook', None)
