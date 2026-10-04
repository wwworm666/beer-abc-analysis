"""API связей с Untappd (routes/taps.py, /api/untappd/*) — «автоматический маппинг через
ИИ-агента» (решение владельца 2026-10-04).

Проверяется: очередь видит кегу на кране; предложение агента — черновик (201, без связи);
«Верно», «Не то» и отмена — только администратор (403 бармену); после «Верно» связь сразу
в таплисте кранов; ошибки хранилища — 400/404/409/503, а не 500; в коннекторе «Чтение и
черновики» агент не заменяет предложение сотрудника. Голый Flask, временные файлы кранов,
номенклатуры и связей; без app.py и без сети.
"""
import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask, g

from core import untappd_live as ul
from core.taplist import product_catalog
from core.taps_manager import TapsManager
from tests.test_untappd_live import AGENT, GUID_LINKED, GUID_NEW, NOW, OWNER, PROPOSAL, _registry

ROOT = Path(__file__).resolve().parents[1]
BARTENDER = {'login': 'masha', 'display_name': 'Маша', 'is_admin': False}


@pytest.fixture
def api(tmp_path):
    store = ul.UntappdLinksStore(str(tmp_path / 'untappd_links.json'), now_fn=lambda: NOW)
    ul.set_store(store)
    products = tmp_path / 'all_products.json'
    products.write_text(json.dumps([{'id': GUID_NEW, 'name': 'КЕГ Шнайдер ТАР4 20 л', 'num': '01295'}],
                                   ensure_ascii=False), encoding='utf-8')
    manager = TapsManager(str(tmp_path / 'taps.json'))
    spec = importlib.util.spec_from_file_location('untappd_routes_test', ROOT / 'routes/taps.py')
    routes = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'extensions': types.SimpleNamespace(taps_manager=manager)}):
        spec.loader.exec_module(routes)
    routes.load_registry = lambda: ul.apply(_registry())
    routes.product_catalog = lambda registry: product_catalog(registry, products_path=products)
    app = Flask(__name__)
    app.register_blueprint(routes.taps_bp)
    state = {'user': AGENT}

    @app.before_request
    def _login():
        g._current_user = state['user']

    yield types.SimpleNamespace(client=app.test_client(), store=store, manager=manager, state=state)
    ul.set_store(None)


def _propose(api, **patch_fields):
    return api.client.post('/api/untappd/proposals', json=dict(PROPOSAL, **patch_fields))


def test_agent_proposes_owner_confirms_and_the_tap_gets_the_card(api):
    api.manager.start_tap('bar1', 22, 'КЕГ Шнайдер ТАР4 20 л', '01295', iiko_product_id=GUID_NEW)
    queue = api.client.get('/api/untappd/queue').json
    assert [(row['iiko_product_id'], row['priority']) for row in queue['items']] == [(GUID_NEW, 1)]
    assert queue['items'][0]['on_tap'][0]['bar'] == 'Большой пр. В.О' and queue['counts']['on_tap'] == 1

    created = _propose(api)
    assert created.status_code == 201
    item = created.json
    assert (item['status'], item['created_by'], item['status_name']) == ('proposed', 'Artem · агент', 'на проверке')
    # в словаре репозитория своё имя сорта 11827 и русский стиль «Wheat Beer - Festbier»
    assert item['preview']['line'].startswith('Schneider Weisse Festweisse')
    assert item['preview']['name_from_dictionary'] is True
    # черновик ни на что не влияет: кран всё ещё без карточки
    assert api.client.get('/api/taps/bar1').json['taps'][21]['beer_info']['mapping_status'] != 'verified'

    pending = api.client.get('/api/untappd/proposals').json
    assert [p['id'] for p in pending['items']] == [item['id']] and pending['counts']['proposed'] == 1
    assert pending['items'][0]['on_tap'][0]['tap_number'] == 22 and pending['can_review'] is True

    api.state['user'] = BARTENDER
    denied = api.client.post(f'/api/untappd/proposals/{item["id"]}/confirm', json={})
    assert denied.status_code == 403 and denied.json['code'] == 'admin_required'
    assert api.client.get('/api/untappd/proposals').json['can_review'] is False

    api.state['user'] = OWNER
    done = api.client.post(f'/api/untappd/proposals/{item["id"]}/confirm', json={'style_ru': 'пшеничное'})
    assert done.status_code == 200 and done.json['status'] == 'verified' and done.json['reviewed_by'] == 'Artem'
    info = api.client.get('/api/taps/bar1').json['taps'][21]['beer_info']
    assert info['mapping_status'] == 'verified' and info['untappd_url'].endswith('/11827')
    assert api.client.get('/api/untappd/queue').json['items'] == []
    # повторное «Верно» — 409, а не вторая связь
    assert api.client.post(f'/api/untappd/proposals/{item["id"]}/confirm', json={}).status_code == 409


def test_reject_and_revoke_return_the_keg_to_the_queue(api):
    item = _propose(api).json
    api.state['user'] = OWNER
    rejected = api.client.post(f'/api/untappd/proposals/{item["id"]}/reject', json={'note': 'это TAP06'})
    assert rejected.status_code == 200 and rejected.json['review_note'] == 'это TAP06'
    row = api.client.get('/api/untappd/queue').json['items'][0]
    assert row['proposal']['status'] == 'rejected' and row['proposal']['review_note'] == 'это TAP06'

    second = _propose(api).json
    api.client.post(f'/api/untappd/proposals/{second["id"]}/confirm', json={})
    revoked = api.client.post(f'/api/untappd/proposals/{second["id"]}/revoke', json={'note': 'ошибся'})
    assert revoked.status_code == 200 and revoked.json['status'] == 'revoked'
    assert [r['iiko_product_id'] for r in api.client.get('/api/untappd/queue').json['items']] == [GUID_NEW]
    history = api.client.get('/api/untappd/proposals?status=all').json
    assert [p['status'] for p in history['items']] == ['revoked', 'rejected']
    assert history['counts'] == {'proposed': 0, 'verified': 0, 'rejected': 1, 'superseded': 0, 'revoked': 1}


def test_errors_are_answers_not_crashes(api):
    bad_url = _propose(api, untappd_url='https://untappd.com/brewery/1')
    assert bad_url.status_code == 400 and 'untappd_url' in bad_url.json['error']
    assert _propose(api, iiko_product_id='55555555-5555-4555-8555-555555555555').status_code == 404
    assert _propose(api, iiko_product_id=GUID_LINKED).status_code == 409   # связь уже проверена
    assert api.client.post('/api/untappd/proposals', json=['не объект']).status_code == 400
    api.state['user'] = OWNER
    assert api.client.post('/api/untappd/proposals/up_000000000000/confirm', json={}).status_code == 404
    assert api.client.get('/api/untappd/queue?scope=soon').status_code == 400
    assert api.client.get('/api/untappd/queue?limit=0').status_code == 400
    assert api.client.get('/api/untappd/proposals?status=maybe').status_code == 400
    # битый файл связей: 503 и файл не перезаписывается
    Path(api.store.data_file).write_text('{"schema_version": 7}', encoding='utf-8')
    broken = _propose(api)
    assert broken.status_code == 503 and broken.json['code'] == 'untappd_links_unavailable'
    assert Path(api.store.data_file).read_text(encoding='utf-8') == '{"schema_version": 7}'


def test_draft_connector_does_not_replace_a_staff_proposal(api):
    api.state['user'] = BARTENDER
    staff = _propose(api).json
    assert staff['origin'] == 'human' and staff['created_by'] == 'Маша'
    api.state['user'] = dict(AGENT, mcp_mode='draft')
    blocked = _propose(api)
    assert blocked.status_code == 409 and 'сотрудника' in blocked.json['error']
    # в полном коннекторе (живой разговор с владельцем) — можно
    api.state['user'] = dict(AGENT, mcp_mode='full')
    assert _propose(api).status_code == 201
    statuses = {p['id']: p['status'] for p in api.client.get('/api/untappd/proposals?status=all').json['items']}
    assert statuses[staff['id']] == 'superseded'


def test_queue_search_and_limit(api):
    api.manager.start_tap('bar2', 3, 'КЕГ Шнайдер ТАР4 20 л', '01295', iiko_product_id=GUID_NEW)
    full = api.client.get('/api/untappd/queue?scope=all').json
    assert full['counts']['total'] == 2 and full['matched'] == 2
    found = api.client.get('/api/untappd/queue?scope=all&q=вудбридж').json
    assert [row['iiko_name'] for row in found['items']] == ['КЕГ Вудбридж ИПА 30 л']
    assert found['counts']['total'] == 2 and found['matched'] == 1
    limited = api.client.get('/api/untappd/queue?scope=all&limit=1').json
    assert [row['priority'] for row in limited['items']] == [1]
    response = api.client.get('/api/untappd/queue')
    assert 'no-store' in response.headers['Cache-Control']
