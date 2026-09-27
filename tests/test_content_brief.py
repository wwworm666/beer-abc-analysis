"""
Тесты брифа сети для ИИ-агента: core/content_brief.py и маршруты
GET / PUT /api/content-plan/brief в routes/content_plan.py.

Self-runnable: `py -3 tests/test_content_brief.py` (совместимо с pytest).

Данные — временные файлы; часы хранилища заморожены (now_fn): «сейчас» —
2026-10-07 12:00 по Москве. Приложение — голый Flask только с content_plan_bp
(app.py не импортируется: он запускает боевой Telegram).

Что проверяется:
- затравка без файла: «О сети» — названия, адреса и число кранов из
  core/venues_config, остальное пусто; GET файл не создаёт; stored=false;
- слияние: меняются только переданные поля; bars — по барам и полям; examples —
  целым списком, пустые отбрасываются; null — пустая строка; правка без
  изменений файл не пишет; первая правка сохраняет затравку;
- пределы: раздел 3000, пример 4096, примеров 10, поле бара 1000, весь бриф
  40 000 (сокращать сверх предела можно, удлинять — нет); пределы и тексты
  пределов совпадают со схемой ответа;
- неизвестные ключ тела, раздел, бар, поле и неверные типы — 400, ничего не
  сохраняется;
- битый файл — 503 на чтение и запись, файл не перезаписан (не JSON, не та
  структура, неизвестный раздел, версия новее);
- подпись: updated_by — login, через MCP (via_mcp) — «login · агент»;
- размер ответа GET с брифом на пределе меньше предела ответа моста MCP.
"""

import atexit
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
import core.content_brief as cb  # noqa: E402
import routes.content_plan as rcp  # noqa: E402
from core.venues_config import VENUES  # noqa: E402
from routes.content_plan import content_plan_bp  # noqa: E402

USER = {'login': 'anna', 'display_name': 'Анна'}
AGENT = {'login': 'anna', 'display_name': 'Анна', 'via_mcp': True, 'mcp_client': 'Claude', 'mcp_token_id': 't1'}
NOW = datetime(2026, 10, 7, 12, 0)
NOW_STR = '2026-10-07T12:00'
BARS = ('bolshoy', 'ligovskiy', 'kremenchugskaya', 'varshavskaya')


def _tmpdir():
    tmp = tempfile.mkdtemp(prefix='content_brief_test_')
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    return tmp


def _store():
    return cb.ContentBriefStore(os.path.join(_tmpdir(), 'content_brief.json'), now_fn=lambda: NOW)


@contextmanager
def _client(store, user=USER):
    saved = (rcp._brief_store, rcp.current_user)
    rcp._brief_store = lambda: store
    rcp.current_user = lambda: user
    try:
        app = Flask('test_content_brief')
        app.register_blueprint(content_plan_bp)
        yield app.test_client()
    finally:
        rcp._brief_store, rcp.current_user = saved


def _put(c, sections):
    return c.put('/api/content-plan/brief', json={'sections': sections})


def _file(store):
    with open(store.data_file, encoding='utf-8') as f:
        return f.read()


# --------------------------------------------------------------------------- затравка

def test_seed_from_venues_config():
    store = _store()
    with _client(store) as c:
        r = c.get('/api/content-plan/brief')
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
    assert body['stored'] is False and not os.path.exists(store.data_file)      # GET файл не создаёт
    brief = body['brief']
    assert (brief['version'], brief['updated_at'], brief['updated_by']) == (1, None, None)
    sections = brief['sections']
    network = sections['network']
    for key in BARS:
        venue = VENUES[key]
        assert f'— {venue["name"]} — адрес: {venue["address"]}, кранов: {venue["taps"]}' in network, key
    assert network.startswith('Бары сети:\n') and network.endswith('.')
    for key in cb.TEXT_KEYS:
        if key != 'network':
            assert sections[key] == '', key
    assert sections['examples'] == []
    # jsonify сортирует ключи объектов: порядок баров для экрана — список schema.bars
    assert set(sections['bars']) == set(BARS)
    assert [b['key'] for b in body['schema']['bars']] == list(BARS)
    for fields in sections['bars'].values():
        assert fields == {f: '' for f in ('character', 'audience', 'hours', 'kitchen', 'events', 'photo_spots')}
    assert set(sections) == {'network', 'tone', 'rubrics', 'rhythm', 'taboo', 'alcohol_ads_rules', 'photo_rules',
                             'notes', 'examples', 'bars'}
    assert body['total'] == len(network)
    # справочник баров в схеме: ключ -> название, адрес, краны
    refs = {b['key']: b for b in body['schema']['bars']}
    assert refs['ligovskiy'] == {'key': 'ligovskiy', 'name': 'Лиговский', 'short': 'Лиг',
                                 'address': VENUES['ligovskiy']['address'], 'taps': VENUES['ligovskiy']['taps']}


def test_schema_describes_every_field_and_limit():
    schema = cb.schema()
    keys = [s['key'] for s in schema['sections']]
    assert keys == ['network', 'tone', 'rubrics', 'rhythm', 'taboo', 'alcohol_ads_rules', 'photo_rules',
                    'examples', 'bars', 'notes']
    for spec in schema['sections']:
        assert spec['label'] and spec['hint'], spec
        if spec['type'] == 'text':
            assert spec['max'] == cb.SECTION_TEXT_MAX == 3000
    ex = next(s for s in schema['sections'] if s['key'] == 'examples')
    assert (ex['type'], ex['max'], ex['max_items']) == ('list', 4096, 10)
    assert [f['key'] for f in schema['bar_fields']] == ['character', 'audience', 'hours', 'kitchen', 'events',
                                                         'photo_spots']
    assert all(f['max'] == cb.BAR_FIELD_MAX == 1000 and f['label'] and f['hint'] for f in schema['bar_fields'])
    assert schema['total_max'] == cb.BRIEF_TOTAL_MAX == 40000
    # пояснение пределов называет те же числа, что проверяет код
    for number in ('3 000', '4 096', '1 000', '40 000', '60 000'):
        assert number in schema['limits_note'], number
    assert 'MCP' in schema['purpose'] and '«ИИ»' in schema['purpose']
    assert len(schema['merge_rules']) >= 4
    # предел примера — предел сообщения Telegram из контент-плана
    from core.content_plan import TG_TEXT_LIMIT
    assert cb.EXAMPLE_TEXT_MAX == TG_TEXT_LIMIT


# --------------------------------------------------------------------------- слияние

def test_partial_merge():
    store = _store()
    with _client(store) as c:
        r = _put(c, {'tone': 'На «вы», коротко'})
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert (body['stored'], body['changed']) == (True, ['tone'])
        assert body['brief']['updated_at'] == NOW_STR and body['brief']['updated_by'] == 'anna'
        seed = cb.seed_network_text()
        assert body['brief']['sections']['network'] == seed                # затравка сохранилась с первой правкой
        on_disk = json.loads(_file(store))
        assert on_disk['sections']['tone'] == 'На «вы», коротко' and on_disk['sections']['network'] == seed
        assert set(on_disk) == {'version', 'sections', 'updated_at', 'updated_by'}
        # бары: сливаются по барам и полям
        r = _put(c, {'bars': {'ligovskiy': {'hours': '12:00–02:00'}}})
        assert r.get_json()['changed'] == ['bars.ligovskiy.hours']
        r = _put(c, {'bars': {'ligovskiy': {'kitchen': 'Бургеры'}, 'bolshoy': {'character': 'Большой зал'}}})
        sections = r.get_json()['brief']['sections']
        assert sections['bars']['ligovskiy'] == {'character': '', 'audience': '', 'hours': '12:00–02:00',
                                                 'kitchen': 'Бургеры', 'events': '', 'photo_spots': ''}
        assert sections['bars']['bolshoy']['character'] == 'Большой зал'
        assert sections['tone'] == 'На «вы», коротко'                      # не переданное — не тронуто
        # примеры: заменяются целым списком, пустые (из пробелов) отбрасываются
        r = _put(c, {'examples': ['Первый пост', '   ', None, 'Второй\nпост']})
        assert r.get_json()['brief']['sections']['examples'] == ['Первый пост', 'Второй\nпост']
        r = _put(c, {'examples': ['Второй\nпост']})
        assert r.get_json()['brief']['sections']['examples'] == ['Второй\nпост']
        # null — пустая строка
        r = _put(c, {'network': None})
        assert r.get_json()['brief']['sections']['network'] == ''
        # то же значение — не правка: файл не пишется, updated_at не меняется
        before = _file(store)
        store._now_fn = lambda: datetime(2026, 10, 8, 9, 30)
        r = _put(c, {'tone': 'На «вы», коротко', 'bars': {'ligovskiy': {'hours': '12:00–02:00'}}})
        assert r.status_code == 200 and r.get_json()['changed'] == []
        assert r.get_json()['brief']['updated_at'] == NOW_STR and _file(store) == before
        r = _put(c, {})
        assert r.status_code == 200 and r.get_json()['changed'] == []
        # новая правка — новое время
        r = _put(c, {'taboo': 'Не пишем про политику'})
        assert r.get_json()['brief']['updated_at'] == '2026-10-08T09:30'
        # GET отдаёт сохранённое
        body = c.get('/api/content-plan/brief').get_json()
        assert body['stored'] is True and body['brief']['sections']['taboo'] == 'Не пишем про политику'
        assert body['total'] == cb.brief_total(body['brief']['sections'])


def test_agent_signature():
    store = _store()
    with _client(store, user=AGENT) as c:
        r = _put(c, {'rhythm': '3 поста в неделю'})
        assert r.get_json()['brief']['updated_by'] == 'anna · агент'
    assert json.loads(_file(store))['updated_by'] == 'anna · агент'
    r = store.update({'sections': {'rhythm': '2 поста'}}, USER)
    assert r['brief']['updated_by'] == 'anna'
    assert store.update({'sections': {'rhythm': '1 пост'}}, None)['brief']['updated_by'] == 'unknown'


# --------------------------------------------------------------------------- пределы

def test_field_limits():
    store = _store()
    with _client(store) as c:
        assert _put(c, {'tone': 'x' * 3000}).status_code == 200
        r = _put(c, {'tone': 'x' * 3001})
        assert r.status_code == 400 and 'длиннее 3 000' in r.get_json()['error']
        assert 'Тон и голос' in r.get_json()['error']
        assert _put(c, {'examples': ['x' * 4096]}).status_code == 200
        r = _put(c, {'examples': ['ok', 'x' * 4097]})
        assert r.status_code == 400 and r.get_json()['error'].startswith('Пример 2 длиннее 4 096')
        assert _put(c, {'examples': [f'пример {i}' for i in range(10)]}).status_code == 200
        r = _put(c, {'examples': [f'пример {i}' for i in range(11)]})
        assert r.status_code == 400 and 'больше 10' in r.get_json()['error']
        # пустые не считаются: 10 настоящих + пустые — можно
        assert _put(c, {'examples': [f'пример {i}' for i in range(10)] + ['', '  ']}).status_code == 200
        assert _put(c, {'bars': {'varshavskaya': {'events': 'x' * 1000}}}).status_code == 200
        r = _put(c, {'bars': {'varshavskaya': {'events': 'x' * 1001}}})
        assert r.status_code == 400 and 'Варшавская' in r.get_json()['error'] and '«События»' in r.get_json()['error']
    # отклонённые правки ничего не записали
    sections = store.payload()['brief']['sections']
    assert len(sections['tone']) == 3000 and len(sections['examples']) == 10
    assert len(sections['bars']['varshavskaya']['events']) == 1000


def test_total_limit_blocks_growth_but_allows_shrinking():
    store = _store()
    full = {key: 'x' * 3000 for key in cb.TEXT_KEYS}                           # 8 x 3000 = 24 000
    with _client(store) as c:
        assert _put(c, full).status_code == 200
        assert _put(c, {'examples': ['y' * 4000] * 4}).status_code == 200       # 40 000 ровно — можно
        assert store.payload()['total'] == 40000
        r = _put(c, {'bars': {'bolshoy': {'hours': 'z'}}})                     # 40 001 — нельзя
        assert r.status_code == 400
        assert r.get_json()['error'].startswith('Бриф длиннее 40 000 знаков (стало бы 40 001)')
        assert store.payload()['brief']['sections']['bars']['bolshoy']['hours'] == ''
        # замена без роста длины проходит
        assert _put(c, {'tone': 'q' * 3000}).status_code == 200
    # бриф сверх предела (например, предел понизили): сокращать можно, удлинять нельзя
    data = json.loads(_file(store))
    data['sections']['notes'] = 'n' * 3000
    data['sections']['examples'] = ['y' * 4096] * 10                            # 24 000 + 40 960 = 64 960
    with open(store.data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    total = store.payload()['total']
    assert total == 64960
    with _client(store) as c:
        r = _put(c, {'examples': ['y' * 4096] * 9})                            # короче, но всё ещё сверх — можно
        assert r.status_code == 200 and r.get_json()['total'] == total - 4096
        assert _put(c, {'rubrics': 'x' * 2999}).status_code == 200              # тоже сокращение
        assert _put(c, {'rubrics': 'x' * 3000}).status_code == 400              # рост сверх предела


def test_unknown_fields_and_types_are_400_and_nothing_saved():
    store = _store()
    with _client(store) as c:
        bad = [
            ({'sections': {'tone': 'a', 'colour': 'b'}}, 'Неизвестный раздел брифа «colour»'),
            ({'sections': {'bars': {'moon': {'hours': '1'}}}}, 'Неизвестный бар «moon»'),
            ({'sections': {'bars': {'bolshoy': {'wifi': 'есть'}}}}, 'Неизвестное поле бара «wifi»'),
            ({'sections': {'tone': 'a'}, 'extra': 1}, 'Неизвестные поля запроса: extra'),
            ({'tone': 'a'}, 'Неизвестные поля запроса: tone'),
            ({}, 'Нет sections'),
            ({'sections': 'текст'}, 'sections: нужен объект'),
            ({'sections': {'tone': 5}}, 'Раздел «Тон и голос»: нужна строка'),
            ({'sections': {'examples': 'один'}}, 'Примеры: нужен список строк'),
            ({'sections': {'examples': ['a', 3]}}, 'Пример 2: нужна строка'),
            ({'sections': {'bars': []}}, 'Бары: нужен объект'),
            ({'sections': {'bars': {'bolshoy': 'текст'}}}, 'Бар bolshoy: нужен объект'),
            ({'sections': {'bars': {'bolshoy': {'hours': ['12']}}}}, 'нужна строка'),
        ]
        for body, text in bad:
            r = c.put('/api/content-plan/brief', json=body)
            assert r.status_code == 400, body
            assert text in r.get_json()['error'], (body, r.get_json())
        r = c.put('/api/content-plan/brief', data='not json', content_type='application/json')
        assert r.status_code == 400 and 'JSON-объект' in r.get_json()['error']
        r = c.put('/api/content-plan/brief', json=['sections'])
        assert r.status_code == 400
    assert not os.path.exists(store.data_file)                                  # ни одна правка не записалась
    assert store.update({'sections': {'tone': 'ok'}}, USER)['changed'] == ['tone']


# --------------------------------------------------------------------------- битый файл

def test_corrupt_file_503_and_not_overwritten():
    good_sections = {'tone': 'ok'}
    variants = (
        'not json {',
        '[]',
        '{"version": 1, "sections": []}',
        '{"version": 1}',
        json.dumps({'version': 1, 'sections': {'tone': 5}}),
        json.dumps({'version': 1, 'sections': {'mood': 'new section from the future'}}),
        json.dumps({'version': 2, 'sections': good_sections}),
        json.dumps({'version': 1, 'sections': {'bars': {'moon': {}}}}),
        json.dumps({'version': 1, 'sections': {'bars': {'bolshoy': {'wifi': 'x'}}}}),
        json.dumps({'version': 1, 'sections': {'examples': [1]}}),
        json.dumps({'version': 1, 'sections': good_sections, 'owner_notes': 'x'}),
    )
    for content in variants:
        store = _store()
        with open(store.data_file, 'w', encoding='utf-8') as f:
            f.write(content)
        with _client(store) as c:
            r = c.get('/api/content-plan/brief')
            assert r.status_code == 503, (content, r.status_code)
            assert r.get_json()['code'] == 'content_brief_unavailable' and r.get_json()['error']
            r = _put(c, {'tone': 'новый тон'})
            assert r.status_code == 503, content
            assert r.get_json()['code'] == 'content_brief_unavailable'
        try:
            store.update({'sections': {'tone': 'x'}}, USER)
            raise AssertionError('update must raise on a broken file')
        except cb.ContentBriefUnavailable:
            pass
        assert _file(store) == content, content                                  # файл не перезаписан
    # старый файл без части разделов — не битый: недостающее пустое
    store = _store()
    with open(store.data_file, 'w', encoding='utf-8') as f:
        json.dump({'sections': {'tone': 'старый тон', 'bars': {'bolshoy': {'hours': '12-24'}}}}, f)
    body = store.payload()
    assert body['stored'] is True and body['brief']['sections']['tone'] == 'старый тон'
    assert body['brief']['sections']['network'] == ''                          # файл есть — затравки нет
    assert body['brief']['sections']['bars']['bolshoy'] == {'character': '', 'audience': '', 'hours': '12-24',
                                                           'kitchen': '', 'events': '', 'photo_spots': ''}
    assert body['brief']['version'] == 1 and body['brief']['updated_at'] is None


def test_response_fits_mcp_result_limit():
    """Бриф на пределе (40 000 знаков с переводами строк) + схема — меньше
    предела ответа моста MCP (60 000 знаков компактного JSON): агент читает
    бриф целиком, без обрезания."""
    store = _store()
    line = ('ё' * 49 + '\n')                                                     # перевод строки в JSON — 2 знака
    sections = {key: (line * 60)[:3000] for key in cb.TEXT_KEYS}
    sections['examples'] = [(line * 100)[:4000]] * 4
    assert store.update({'sections': sections}, USER)['total'] == 40000
    text = json.dumps(store.payload(), ensure_ascii=False, separators=(',', ':'))
    assert len(text) < cb.MCP_RESULT_LIMIT, len(text)


def test_singleton_accessor():
    saved = cb._store
    try:
        tmp = os.path.join(_tmpdir(), 'content_brief.json')
        a = cb.get_content_brief_store(tmp)
        assert a.data_file == tmp and cb.get_content_brief_store() is a
    finally:
        cb._store = saved


if __name__ == '__main__':
    import inspect
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith('test_') and inspect.isfunction(fn):
            try:
                fn()
                print(f'ok   {name}')
            except Exception as e:  # noqa: BLE001
                failed += 1
                import traceback
                traceback.print_exc()
                print(f'FAIL {name}: {e!r}')
    sys.exit(1 if failed else 0)
