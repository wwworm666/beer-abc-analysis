"""Тесты индекса «GTIN -> карточки iiko» для приёмки (core/receiving_index.py). Сети нет.

Файлы индекса, состояния и лока — во временной папке (set_paths), реальный data/ не
трогается. iiko подменяется фейковой requests.Session, часы — подменой msk_time.now.
Что проверяется:
- build_index на синтетических справочниках: удалённые, архив по GUID и по имени
  предка (в том числе предок, которого нет в справочнике), кеги по группе и по
  фасовке, дубли штрихкодов (между карточками и внутри одной), сирота, цикл и
  слишком глубокая цепочка групп, какие типы попадают в индекс, запасной XML;
- classify: found / duplicate / restore (удалена, архив) / missing, нормализация GTIN;
- similar_cards: направление сравнения, стоп-слова, ё = е, уникальные слова, порядок,
  только SEARCH_TYPES, limit;
- search_cards: по штрихкоду (любой тип), по артикулу, по словам, порядок, limit;
- save/load: кэш по (mtime_ns, размер), перечитывание после записи, битый файл,
  чужая версия, сброс кэша в set_paths; index_info;
- состояние и refresh_index: running во время обновления, done, error (текст
  IndexSourceError и тип прочих), файл индекса при сбое не трогается, лок занят
  (второй держатель в этом же и в другом процессе) -> RefreshBusy, лок отпускается;
- fetch_iiko_sources: один вход, includeDeleted везде, разворот {result, response},
  XML-запас, выход в finally при любом исходе, токен не попадает в текст ошибки.
"""
import ast
import hashlib
import json
import os
import subprocess
import sys
import threading
from datetime import datetime

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import msk_time  # noqa: E402
from core import receiving_index as ri  # noqa: E402


# ----- синтетическая номенклатура ----------------------------------------------------

G_TOP = 'g-top-0000'           # Напитки Фасовка
G_BEER = 'g-beer-0000'         # Напитки Фасовка / Пиво бутылочное
G_OLD = 'g-old-0000'           # Старое и неактуальное
G_ARCHIVE = 'be375ee4-671f-4c7b-87ae-ab945b1f8edc'        # «Архив» (GUID из ARCHIVE_GROUP_IDS)
G_ARCHIVE_GOODS = '14bc1f9d-e172-1a9d-0196-f2627515aab6'  # «Архив товаров»
G_NAMED_ARCHIVE = 'g-named-archive'   # группа с именем «  АРХИВ », GUID не из списка
G_DRAFT = 'g-draft-0000'       # Напитки Розлив
G_KEG = ri.KEG_GROUP_ID        # Kеги
G_CYCLE_A = 'g-cycle-a'
G_CYCLE_B = 'g-cycle-b'
CAT_MB = 'cat-marketbeer'
UNIT_PCS = 'unit-pcs'
UNIT_L = 'unit-l'

GTIN_FOUND = '04870009003625'
GTIN_DELETED = '04600000000017'
GTIN_ARCHIVED = '04600000000024'
GTIN_NAMED_ARCH = '04600000000031'
GTIN_DUP = '04607082009899'
GTIN_ONE_ACTUAL = '04602864021304'
GTIN_DISH = '04600000000048'
GTIN_EAN8 = '00000046012345'
GTIN_XML = '04610093628430'

GROUPS = [
    {'id': G_TOP, 'name': 'Напитки Фасовка', 'parent': None, 'deleted': False},
    {'id': G_BEER, 'name': ' Пиво  бутылочное ', 'parent': G_TOP, 'deleted': False},
    {'id': G_OLD, 'name': 'Старое и неактуальное', 'parent': None, 'deleted': False},
    {'id': G_ARCHIVE, 'name': 'Архив', 'parent': G_OLD, 'deleted': False},
    {'id': G_ARCHIVE_GOODS, 'name': 'Архив товаров', 'parent': G_ARCHIVE, 'deleted': False},
    {'id': G_NAMED_ARCHIVE, 'name': '  АРХИВ ', 'parent': G_TOP, 'deleted': False},
    {'id': G_DRAFT, 'name': 'Напитки Розлив', 'parent': None, 'deleted': False},
    {'id': G_KEG, 'name': 'Kеги', 'parent': G_DRAFT, 'deleted': False},
    {'id': G_CYCLE_A, 'name': 'Цикл А', 'parent': G_CYCLE_B, 'deleted': False},
    {'id': G_CYCLE_B, 'name': 'Цикл Б', 'parent': G_CYCLE_A, 'deleted': False},
    'не словарь',
    {'name': 'без id'},
]
CATEGORIES = [{'id': CAT_MB, 'rootType': 'ProductCategory', 'name': 'ООО  МаркетБир', 'deleted': False}]
UNITS = [{'id': UNIT_PCS, 'name': 'шт'}, {'id': UNIT_L, 'name': 'л'}]


def _product(pid, name, *, type_='GOODS', parent=G_BEER, barcodes=(), deleted=False,
             num='', category=CAT_MB, unit=UNIT_PCS, containers=None, code=''):
    return {'id': pid, 'name': name, 'type': type_, 'parent': parent, 'deleted': deleted,
            'num': num, 'code': code, 'category': category, 'mainUnit': unit,
            'containers': containers or [],
            'barcodes': [{'barcode': b, 'containerId': None} for b in barcodes]}


def _products():
    return [
        _product('p-found', ' Boozy  (Полусладкий), бут. 0,500 .', num='00019', code='5619',
                 barcodes=['4870009003625', '4870009003625', '04870009003625']),
        _product('p-deleted', 'Удалённое пиво', deleted=True, barcodes=['4600000000017']),
        _product('p-archived', 'Архивное пиво', parent=G_ARCHIVE_GOODS, barcodes=['4600000000024']),
        _product('p-named-arch', 'Пиво из архива по имени', parent=G_NAMED_ARCHIVE,
                 barcodes=['4600000000031']),
        _product('p-dup-b', 'Konix 0,45 банка', barcodes=['4607082009899']),
        _product('p-dup-a', 'Konix 0,45 бутылка', barcodes=['4607082009899']),
        _product('p-dup-del', 'Konix старый', deleted=True, barcodes=['4607082009899']),
        _product('p-one-del', 'Аббатское удалённое', deleted=True, barcodes=['4602864021304']),
        _product('p-one-act', 'Аббатское', barcodes=['4602864021304']),
        _product('p-keg-group', 'Кег Жигулёвское', parent=G_KEG, unit=UNIT_L, num='0076'),
        _product('p-keg-cont', 'Lager Brewery', unit=UNIT_L,
                 containers=[{'name': 'кег(30)', 'count': 30.0, 'deleted': False},
                             {'name': 'старая тара', 'count': 1, 'deleted': True}]),
        _product('p-keg-deleted-cont', 'Не кег', containers=[
            {'name': 'кега 20', 'count': 20, 'deleted': True},
            {'name': ' бутылка  0,5 ', 'count': 0.5, 'deleted': False}]),
        _product('p-dish-bc', 'Порция с баркодом', type_='DISH', parent=G_DRAFT,
                 barcodes=['4600000000048']),
        _product('p-dish', 'Аббатское (Р)', type_='DISH', parent=G_DRAFT),
        _product('p-modifier', 'Модификатор', type_='MODIFIER', parent=None),
        _product('p-prepared', 'Заготовка сидр', type_='PREPARED', parent=None, category=None),
        _product('p-orphan', 'Сирота', parent='g-missing-0000', unit='unit-missing'),
        _product('p-cycle', 'Цикличная', parent=G_CYCLE_A),
        _product('p-bad-codes', 'Кривые коды', barcodes=['468.623940318', '123456789012345',
                                                         '', '46012345']),
        _product('p-found', 'Повтор той же карточки', barcodes=['4600000000099']),
        'мусор',
        {'name': 'без id', 'type': 'GOODS'},
    ]


@pytest.fixture(autouse=True)
def paths(tmp_path):
    """Все файлы модуля — во временной папке; после теста — пути по умолчанию."""
    ri.set_paths(index=tmp_path / 'receiving_index.json',
                 state=tmp_path / 'receiving_index_state.json',
                 run_lock=tmp_path / 'locks' / '.receiving_index_run.lock')
    yield tmp_path
    ri.set_paths()


@pytest.fixture
def index():
    return ri.build_index(_products(), GROUPS, CATEGORIES, UNITS, built_at='2026-10-03T07:30:05+03:00')


def _freeze(monkeypatch, moment):
    monkeypatch.setattr(msk_time, 'now', lambda: moment)


def _msk(*args):
    return datetime(*args, tzinfo=msk_time.MOSCOW_TZ)


# ----- build_index ---------------------------------------------------------------------

def test_build_card_fields_and_cleanup(index):
    card = index['cards']['p-found']
    assert card == {
        'id': 'p-found', 'name': 'Boozy (Полусладкий), бут. 0,500 .', 'num': '00019',
        'code': '5619', 'type': 'GOODS', 'deleted': False, 'archived': False,
        'group': 'Напитки Фасовка / Пиво бутылочное', 'group_id': G_BEER,
        'supplier': 'ООО МаркетБир', 'unit': 'шт', 'containers': [],
        'barcodes': [GTIN_FOUND], 'keg': False,
    }
    assert index['version'] == ri.INDEX_VERSION == 1
    assert index['built_at'] == '2026-10-03T07:30:05+03:00'
    assert index['source'] == 'v2'


def test_build_repeated_product_id_keeps_first(index):
    assert index['cards']['p-found']['name'].startswith('Boozy')
    assert '04600000000099' not in index['by_gtin']


def test_build_types_in_index(index):
    cards = index['cards']
    assert 'p-dish-bc' in cards and cards['p-dish-bc']['type'] == 'DISH'   # DISH со штрихкодом
    assert 'p-dish' not in cards          # порция без штрихкода не нужна
    assert 'p-modifier' not in cards
    assert 'p-prepared' in cards          # PREPARED без штрихкода — кандидат поиска
    assert cards['p-prepared']['supplier'] == '' and cards['p-prepared']['group'] == ''
    assert 'p-keg-group' in cards and cards['p-keg-group']['barcodes'] == []


def test_build_deleted_and_archived(index):
    cards = index['cards']
    assert cards['p-deleted']['deleted'] is True and cards['p-deleted']['archived'] is False
    arch = cards['p-archived']
    assert arch['archived'] is True and arch['deleted'] is False
    assert arch['group'] == 'Старое и неактуальное / Архив / Архив товаров'
    named = cards['p-named-arch']
    assert named['archived'] is True
    assert named['group'] == 'Напитки Фасовка / АРХИВ'
    # «Старое и неактуальное» само по себе — не архив (решение спецификации).
    assert ri.build_index([_product('x', 'В старом', parent=G_OLD)], GROUPS)['cards']['x']['archived'] is False


def test_build_archive_by_missing_parent_id():
    """Родителя-архива нет в справочнике групп — архив узнаётся по его GUID."""
    idx = ri.build_index([_product('x', 'Пиво', parent=G_ARCHIVE_GOODS)], groups=[])
    assert idx['cards']['x']['archived'] is True
    assert idx['cards']['x']['group'] == ''


def test_build_archive_name_must_match_exactly():
    groups = [{'id': 'g1', 'name': 'Архивное пиво', 'parent': None}]
    idx = ri.build_index([_product('x', 'Пиво', parent='g1')], groups)
    assert idx['cards']['x']['archived'] is False


def test_build_keg_by_group_and_container(index):
    cards = index['cards']
    assert cards['p-keg-group']['keg'] is True
    assert cards['p-keg-group']['group'] == 'Напитки Розлив / Kеги'
    assert cards['p-keg-group']['unit'] == 'л'
    assert cards['p-keg-cont']['keg'] is True
    assert cards['p-keg-cont']['containers'] == [{'name': 'кег(30)', 'count': 30.0}]
    # Удалённая кеговая фасовка не делает карточку кегом.
    assert cards['p-keg-deleted-cont']['keg'] is False
    assert cards['p-keg-deleted-cont']['containers'] == [{'name': 'бутылка 0,5', 'count': 0.5}]
    assert cards['p-found']['keg'] is False


def test_build_orphan_cycle_and_deep_chain(index):
    cards = index['cards']
    assert cards['p-orphan']['group'] == '' and cards['p-orphan']['archived'] is False
    assert cards['p-orphan']['group_id'] == 'g-missing-0000'
    assert cards['p-orphan']['unit'] == ''
    assert cards['p-cycle']['group'] == 'Цикл Б / Цикл А'
    deep = [{'id': f'd{i}', 'name': f'Уровень {i}', 'parent': f'd{i + 1}' if i < 79 else None}
            for i in range(80)]
    deep[79]['id'] = 'd79'
    deep.append({'id': 'd80-archive', 'name': 'Архив', 'parent': None})
    deep[79]['parent'] = 'd80-archive'
    idx = ri.build_index([_product('x', 'Глубоко', parent='d0')], deep)
    card = idx['cards']['x']
    assert len(card['group'].split(' / ')) == ri.MAX_GROUP_DEPTH
    assert card['group'].endswith('Уровень 0')
    assert card['archived'] is False   # архив выше предела глубины не виден — и не падаем


def test_build_barcode_normalization(index):
    cards = index['cards']
    assert cards['p-found']['barcodes'] == [GTIN_FOUND]          # дубли внутри карточки убраны
    assert cards['p-bad-codes']['barcodes'] == [GTIN_EAN8]        # мусор и >14 цифр пропущены
    assert index['by_gtin'][GTIN_EAN8] == ['p-bad-codes']


def test_build_by_gtin_order_and_counts(index):
    by_gtin = index['by_gtin']
    # Актуальные раньше, затем по имени (банка < бутылка), удалённые в конце.
    assert by_gtin[GTIN_DUP] == ['p-dup-b', 'p-dup-a', 'p-dup-del']
    assert by_gtin[GTIN_ONE_ACTUAL] == ['p-one-act', 'p-one-del']
    assert list(by_gtin) == sorted(by_gtin)
    assert index['counts'] == {
        'products': len(index['cards']),
        'gtins': len(by_gtin),
        'with_barcodes': 11,
        'deleted': 3,
        'archived': 2,
        'duplicates': 1,
    }
    assert len(index['cards']) == 17
    assert len(by_gtin) == 8


def test_build_xml_fallback():
    products = [_product('a', 'Пиво А'), _product('b', 'Пиво Б'), _product('c', 'Пиво В')]
    for product in products:
        del product['barcodes']
    products[2]['barcodes'] = []   # поле есть, пустое: v2 главнее XML
    xml = {'a': ['4610093628430', ' 4610093628430 '], 'c': ['4600000000017'], 'zzz': ['4600000000024']}
    idx = ri.build_index(products, GROUPS, xml_barcodes=xml)
    assert idx['source'] == 'v2+xml'
    assert idx['cards']['a']['barcodes'] == [GTIN_XML]
    assert idx['cards']['b']['barcodes'] == []
    assert idx['cards']['c']['barcodes'] == []
    assert idx['by_gtin'] == {GTIN_XML: ['a']}


def test_build_defaults_built_at(monkeypatch):
    _freeze(monkeypatch, _msk(2026, 10, 3, 14, 5, 0, 123456))
    idx = ri.build_index([], [])
    assert idx['built_at'] == '2026-10-03T14:05:00+03:00'
    assert idx['cards'] == {} and idx['by_gtin'] == {}
    assert idx['counts']['products'] == 0


def test_build_is_deterministic():
    a = ri.build_index(_products(), GROUPS, CATEGORIES, UNITS, built_at='2026-10-03T07:30:05+03:00')
    b = ri.build_index(_products(), GROUPS, CATEGORIES, UNITS, built_at='2026-10-03T07:30:05+03:00')
    assert json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False)


# ----- classify -------------------------------------------------------------------------

def test_classify_all_branches(index):
    found = ri.classify(GTIN_FOUND, index)
    assert found['status'] == 'found'
    assert [c['id'] for c in found['cards']] == ['p-found']

    one = ri.classify(GTIN_ONE_ACTUAL, index)
    assert one['status'] == 'found'
    assert [c['id'] for c in one['cards']] == ['p-one-act', 'p-one-del']

    dup = ri.classify(GTIN_DUP, index)
    assert dup['status'] == 'duplicate'
    assert [c['id'] for c in dup['cards']] == ['p-dup-b', 'p-dup-a', 'p-dup-del']

    assert ri.classify(GTIN_DELETED, index)['status'] == 'restore'
    assert ri.classify(GTIN_ARCHIVED, index)['status'] == 'restore'
    assert ri.classify(GTIN_NAMED_ARCH, index)['status'] == 'restore'
    assert ri.classify(GTIN_DISH, index)['status'] == 'found'      # штрихкод на порции DISH

    missing = ri.classify('04699999999999', index)
    assert missing == {'status': 'missing', 'cards': []}


def test_classify_normalizes_and_rejects_garbage(index):
    assert ri.classify('4870009003625', index)['status'] == 'found'     # EAN-13 без нуля
    assert ri.classify('46012345', index)['status'] == 'found'          # EAN-8
    for bad in ('', None, 'abc', '123456789012345', '0487000900362X'):
        assert ri.classify(bad, index) == {'status': 'missing', 'cards': []}
    assert ri.classify(GTIN_FOUND, {})['status'] == 'missing'
    assert ri.classify(GTIN_FOUND, None)['status'] == 'missing'


def test_card_summary_shape(index):
    summary = ri.card_summary(index['cards']['p-archived'])
    assert summary == {'id': 'p-archived', 'name': 'Архивное пиво', 'num': '',
                       'group': 'Старое и неактуальное / Архив / Архив товаров',
                       'supplier': 'ООО МаркетБир', 'unit': 'шт', 'deleted': False,
                       'archived': True, 'keg': False}
    summary['name'] = 'изменено'
    assert index['cards']['p-archived']['name'] == 'Архивное пиво'   # копия, не ссылка


# ----- similar_cards -----------------------------------------------------------------------

def _similar_index():
    products = [
        _product('c-pale', 'Konix Pale Ale, бут. 0,45'),
        _product('c-stout', 'Konix Stout, бут. 0,45'),
        _product('c-pale-old', 'Konix Pale Ale (старая)', deleted=True),
        _product('c-pale-dish', 'Konix Pale Ale (Р)', type_='DISH', barcodes=['4600000000048']),
        _product('c-generic', 'Пиво светлое фильтрованное пастеризованное'),
        _product('c-zhig', 'Жигулёвское Барное'),
        _product('c-repeat', 'Ale Ale Pale'),
        _product('c-digits', '1516 Lager 0,5'),
        _product('c-four', 'Konix Pale Ale Session'),
        _product('c-prepared', 'Konix Pale заготовка', type_='PREPARED'),
    ]
    return ri.build_index(products, GROUPS, built_at='2026-10-03T07:30:05+03:00')


def test_similar_scores_and_order():
    idx = _similar_index()
    found = ri.similar_cards('Пиво светлое пастеризованное Konix Pale Ale Session', idx, brand='Konix')
    ids = [c['id'] for c in found]
    # 4 слова у c-four; по 3 — актуальная раньше удалённой; по 2 — по имени
    # (c-repeat: «ale ale pale» — повтор слова не считается дважды).
    assert ids == ['c-four', 'c-pale', 'c-pale-old', 'c-repeat', 'c-prepared']
    assert [c['score'] for c in found] == [4, 3, 3, 2, 2]
    assert found[2]['deleted'] is True
    assert set(found[0]) == {'id', 'name', 'num', 'group', 'supplier', 'unit', 'deleted',
                             'archived', 'keg', 'score'}
    assert 'c-pale-dish' not in ids    # DISH — не кандидат
    assert 'c-stout' not in ids        # одно общее слово (konix) — мало


def test_similar_one_chz_word_counts_once():
    """Ревью 2026-10-03: подстрокой «pale» в ЧЗ давало и «pale», и «ale» — счёт 2 у
    любой карточки «… Pale Ale». Теперь слово ЧЗ засчитывается одному слову карточки."""
    products = [
        _product('c-hop', 'Victory Hop Devil Pale Ale 0,355 бут.'),
        _product('c-bak', 'Бакунин Pale Ale 0,5'),
        _product('c-sald', "Salden's Ale Pale 0,45 банка"),
        _product('c-rig', 'Ригеле Файнес Урхель 0,5 бут.'),
        _product('c-lager', 'Волковская Лагер светлый'),
    ]
    idx = ri.build_index(products, GROUPS, built_at='2026-10-03T07:30:05+03:00')
    assert ri.similar_cards('Пиво светлое нефильтрованное Stamm Beer West Coast Pale', idx,
                            brand='Stamm Beer') == []
    rig = ri.similar_cards('Пиво светлое непастеризованное фильтрованное Ригеле Файнес Урхель', idx)
    assert [(c['id'], c['score']) for c in rig] == [('c-rig', 3)]
    # Окончания: слово карточки — начало слова ЧЗ и наоборот.
    lager = ri.similar_cards('Пиво Волковская лагерное', idx)
    assert [(c['id'], c['score']) for c in lager] == [('c-lager', 2)]
    pale_ale = ri.similar_cards('Бакунин Pale Ale светлый эль', idx)
    assert [c['id'] for c in pale_ale][0] == 'c-bak' and pale_ale[0]['score'] == 3


def test_similar_stop_words_do_not_count():
    idx = _similar_index()
    # Все слова карточки c-generic — стоп-слова: без них был бы счёт 3.
    assert ri.similar_cards('Пиво светлое фильтрованное пастеризованное Балтика', idx) == []
    assert ri._name_words('Пиво светлое фильтрованное пастеризованное') == []
    assert ri._name_words('Пиво ТЁМНОЕ нефильтрованное, бут. 0,5 л КЕГ') == []


def test_similar_yo_digits_brand_limit():
    idx = _similar_index()
    zhig = ri.similar_cards('ЖИГУЛЕВСКОЕ барное', idx)
    assert [c['id'] for c in zhig] == ['c-zhig'] and zhig[0]['score'] == 2
    # Цифры не слово: у c-digits остаётся одно слово lager.
    assert ri.similar_cards('1516 Lager', idx) == []
    # Бренд участвует в тексте ЧЗ.
    assert [c['id'] for c in ri.similar_cards('Pale Ale', idx, brand='Konix')][:2] == ['c-four', 'c-pale']
    assert len(ri.similar_cards('Konix Pale Ale Session', idx, limit=2)) == 2
    assert ri.similar_cards('Konix Pale Ale Session', idx, limit=0) == []
    assert ri.similar_cards('', idx) == []
    assert ri.similar_cards('  ', idx, brand='') == []
    assert ri.similar_cards('Konix Pale', {}) == []


def test_similar_words_cache_follows_index():
    """Кэш слов привязан к объекту индекса: новый индекс — новые кандидаты."""
    first = _similar_index()
    assert [c['id'] for c in ri.similar_cards('Жигулевское барное', first)] == ['c-zhig']
    pairs = ri._candidate_words(first)
    assert ri._candidate_words(first) is pairs          # тот же индекс — из кэша
    assert 'c-generic' not in {card['id'] for card, _ in pairs}   # слов меньше порога
    second = ri.build_index([_product('z', 'Жигулёвское Барное разливное')], GROUPS,
                            built_at=first['built_at'])
    assert [c['id'] for c in ri.similar_cards('Жигулевское барное', second)] == ['z']
    assert [c['id'] for c in ri.similar_cards('Жигулевское барное', first)] == ['c-zhig']


# ----- search_cards ---------------------------------------------------------------------------

def test_search_by_barcode_any_type(index):
    found = ri.search_cards('4870009003625', index)
    assert [c['id'] for c in found] == ['p-found']
    assert found[0]['barcodes'] == [GTIN_FOUND]
    dish = ri.search_cards(GTIN_DISH, index)
    assert [c['id'] for c in dish] == ['p-dish-bc']        # по штрихкоду — любой тип
    dup = ri.search_cards(GTIN_DUP, index)
    assert [c['id'] for c in dup] == ['p-dup-b', 'p-dup-a', 'p-dup-del']
    assert ri.search_cards('04699999999999', index) == []


def test_search_by_long_num():
    idx = ri.build_index([_product('a', 'Артикул длинный', num='12345678'),
                          _product('b', 'Порция', type_='DISH', num='12345678',
                                   barcodes=['4600000000017'])], GROUPS)
    assert [c['id'] for c in ri.search_cards('12345678', idx)] == ['a']


def test_search_by_words_and_num(index):
    assert [c['id'] for c in ri.search_cards('boozy ПОЛУСЛАДКИЙ', index)] == ['p-found']
    assert [c['id'] for c in ri.search_cards('жигулев', index)] == ['p-keg-group']   # ё = е
    assert [c['id'] for c in ri.search_cards('0076', index)] == ['p-keg-group']      # артикул
    assert [c['id'] for c in ri.search_cards('00019', index)] == ['p-found']
    # DISH по словам не ищется; удалённые — после актуальных.
    abbey = ri.search_cards('аббатское', index)
    assert [c['id'] for c in abbey] == ['p-one-act', 'p-one-del']
    assert abbey[1]['deleted'] is True and 'barcodes' in abbey[0]
    konix = ri.search_cards('konix', index)
    assert [c['id'] for c in konix] == ['p-dup-b', 'p-dup-a', 'p-dup-del']
    assert len(ri.search_cards('konix', index, limit=1)) == 1
    assert ri.search_cards('', index) == []
    assert ri.search_cards('   ', index) == []
    assert ri.search_cards('konix', None) == []


# ----- файл индекса, кэш, index_info --------------------------------------------------------

def test_save_and_load_with_cache(index, paths):
    assert ri.load_index() is None
    ri.save_index(index)
    path = ri.index_path()
    assert path == str(paths / 'receiving_index.json')
    assert '\n' not in open(path, encoding='utf-8').read()     # indent=None
    assert not os.path.exists(path + '.tmp')
    loaded = ri.load_index()
    assert loaded == index
    assert ri.load_index() is loaded                       # из кэша, без перечитывания

    # Другой воркер записал новый индекс -> перечитываем по (mtime_ns, размер).
    newer = ri.build_index(_products()[:3], GROUPS, built_at='2026-10-04T07:30:00+03:00')
    ri.save_index(newer)
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000))
    reloaded = ri.load_index()
    assert reloaded is not loaded and reloaded == newer


def test_load_reloads_on_mtime_change_with_same_size(paths):
    first = ri.build_index([_product('a', 'Пиво А')], [], built_at='2026-10-03T07:30:05+03:00')
    second = ri.build_index([_product('b', 'Пиво Б')], [], built_at='2026-10-03T07:30:05+03:00')
    ri.save_index(first)
    path = ri.index_path()
    size_before = os.path.getsize(path)
    loaded = ri.load_index()
    st = os.stat(path)
    ri.save_index(second)
    assert os.path.getsize(path) == size_before
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert ri.load_index() is not loaded
    assert list(ri.load_index()['cards']) == ['b']


def test_load_reloads_on_size_change_with_same_mtime(paths):
    """Грубые часы ФС: mtime не сменился, а размер сменился — всё равно перечитываем."""
    ri.save_index(ri.build_index([_product('a', 'Пиво А')], [], built_at='2026-10-03T07:30:05+03:00'))
    path = ri.index_path()
    st = os.stat(path)
    loaded = ri.load_index()
    ri.save_index(ri.build_index([_product('a', 'Пиво А'), _product('b', 'Пиво Б')], [],
                                 built_at='2026-10-03T07:30:05+03:00'))
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert os.stat(path).st_mtime_ns == st.st_mtime_ns
    assert os.path.getsize(path) != st.st_size
    reloaded = ri.load_index()
    assert reloaded is not loaded and list(reloaded['cards']) == ['a', 'b']


def test_load_broken_and_foreign_version(paths, capsys):
    path = ri.index_path()
    with open(path, 'w', encoding='utf-8') as f:
        f.write('{"version": 1, "cards": ')
    assert ri.load_index() is None
    assert ri.load_index() is None
    assert capsys.readouterr().out.count('не читается') == 1    # битый файл тоже в кэше
    for bad in ({'version': 2, 'built_at': '2026-10-03T07:30:05+03:00', 'cards': {}, 'by_gtin': {}},
                {'version': 1, 'built_at': 'вчера', 'cards': {}, 'by_gtin': {}},
                {'version': 1, 'built_at': '2026-10-03T07:30:05+03:00', 'cards': [], 'by_gtin': {}},
                ['не словарь']):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(bad, f)
        st = os.stat(path)
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 7_000_000))
        assert ri.load_index() is None


def test_set_paths_resets_cache(index, tmp_path):
    ri.save_index(index)
    assert ri.load_index() is not None
    other = tmp_path / 'other'
    ri.set_paths(index=other / 'idx.json', state=other / 'state.json', run_lock=other / 'run.lock')
    assert ri.load_index() is None
    assert ri.state_path() == str(other / 'state.json')
    assert ri.run_lock_path() == str(other / 'run.lock')


def test_default_paths():
    ri.set_paths()
    assert ri.run_lock_path().endswith(os.path.join('data', '.receiving_index_run.lock'))
    assert ri.index_path().endswith('receiving_index.json')
    assert ri.state_path().endswith('receiving_index_state.json')


def test_index_info(monkeypatch, index):
    _freeze(monkeypatch, _msk(2026, 10, 3, 9, 0, 59))
    info = ri.index_info(index)
    assert info == {'built_at': '2026-10-03T07:30:05+03:00', 'age_minutes': 90,
                    'counts': index['counts'], 'source': 'v2'}
    info['counts']['products'] = -1
    assert index['counts']['products'] != -1
    assert ri.index_info(None) is None
    assert ri.index_info({}) is None
    _freeze(monkeypatch, _msk(2026, 10, 3, 7, 0))       # часы позади built_at -> 0, не минус
    assert ri.index_info(index)['age_minutes'] == 0
    naive = dict(index, built_at='2026-10-03T08:30:05')  # без зоны = МСК
    _freeze(monkeypatch, _msk(2026, 10, 3, 8, 40, 5))
    assert ri.index_info(naive)['age_minutes'] == 10
    assert ri.index_info(dict(index, built_at=''))['age_minutes'] is None


# ----- состояние ---------------------------------------------------------------------------

def _write_raw_state(data):
    with open(ri.state_path(), 'w', encoding='utf-8') as f:
        json.dump(data, f)


def test_read_state_missing_and_broken():
    empty = {'running': False, 'trigger': '', 'started_at': '', 'finished_at': '',
             'error': '', 'counts': None}
    assert ri.read_state() == empty
    with open(ri.state_path(), 'w', encoding='utf-8') as f:
        f.write('{oops')
    assert ri.read_state() == empty
    _write_raw_state(['list'])
    assert ri.read_state() == empty


def test_read_state_running_fresh_and_stale(monkeypatch):
    _freeze(monkeypatch, _msk(2026, 10, 3, 12, 0, 0))
    _write_raw_state({'running': True, 'trigger': 'button', 'started_at': '2026-10-03T11:50:00+03:00',
                      'finished_at': '', 'error': '', 'counts': None})
    state = ri.read_state()
    assert state['running'] is True and state['trigger'] == 'button' and state['error'] == ''

    _write_raw_state({'running': True, 'trigger': 'button', 'started_at': '2026-10-03T11:44:59+03:00',
                      'finished_at': '', 'error': '', 'counts': None})
    state = ri.read_state()
    assert state['running'] is False
    assert state['error'] == ri.STALE_RUNNING_ERROR

    _write_raw_state({'running': True, 'trigger': 'close', 'started_at': '', 'counts': {'products': 3}})
    state = ri.read_state()
    assert state['running'] is False and state['counts'] == {'products': 3}


def test_read_state_running_but_lock_free_is_dead(monkeypatch, paths):
    """Ревью 2026-10-03: воркер умер посреди обновления — лок свободен, кнопка доступна сразу,
    без ожидания STALE_RUNNING_SEC."""
    _freeze(monkeypatch, _msk(2026, 10, 3, 12, 0, 0))
    ri.acquire_run_lock().release()                      # каталог лока есть, лок свободен
    _write_raw_state({'running': True, 'trigger': 'button', 'started_at': '2026-10-03T11:59:00+03:00',
                      'finished_at': '', 'error': '', 'counts': None})
    state = ri.read_state()
    assert state['running'] is False and state['error'] == ri.STALE_RUNNING_ERROR
    lock = ri.acquire_run_lock()                         # идёт настоящее обновление
    try:
        assert ri.read_state()['running'] is True
    finally:
        lock.release()


def test_refresh_after_save_runs_before_done(monkeypatch, paths):
    _freeze(monkeypatch, _msk(2026, 10, 3, 7, 30, 5))
    seen = {}

    def after(index):
        seen['state'] = ri.read_state()
        seen['cards'] = len(index['cards'])
        seen['loaded'] = ri.load_index() is not None
        with pytest.raises(ri.RefreshBusy):
            ri.acquire_run_lock()                        # лок ещё у обновления

    ri.refresh_index('button', fetch=_sources, after_save=after)
    assert seen['state']['running'] is True and seen['cards'] > 0 and seen['loaded'] is True
    assert ri.read_state()['running'] is False and ri.read_state()['error'] == ''


def test_refresh_after_save_failure_keeps_index(monkeypatch, paths):
    _freeze(monkeypatch, _msk(2026, 10, 3, 7, 30, 5))

    def after(index):
        raise RuntimeError('boom')

    info = ri.refresh_index('button', fetch=_sources, after_save=after)
    state = ri.read_state()
    assert info['counts']['products'] > 0 and ri.load_index() is not None
    assert state['running'] is False and state['counts'] == info['counts']
    assert state['error'].startswith('Индекс обновлён, но пересверка') and 'boom' not in state['error']
    ri.acquire_run_lock().release()


def test_logout_on_exit_calls_active_session():
    calls = []
    saved = ri._active_logout[0]
    try:
        ri._active_logout[0] = lambda: calls.append('logout')
        ri._logout_on_exit()
        assert calls == ['logout']
        ri._active_logout[0] = None
        ri._logout_on_exit()                              # нечего закрывать — тихо
        assert calls == ['logout']
    finally:
        ri._active_logout[0] = saved


# ----- refresh_index и лок -----------------------------------------------------------------

def _sources(products=None):
    return {'products': _products() if products is None else products, 'groups': GROUPS,
            'categories': CATEGORIES, 'units': UNITS, 'xml_barcodes': None}


def test_refresh_success_states_and_lock(monkeypatch, paths):
    _freeze(monkeypatch, _msk(2026, 10, 3, 7, 30, 5))
    seen = {}

    def fetch():
        seen['state'] = ri.read_state()
        with pytest.raises(ri.RefreshBusy):
            ri.acquire_run_lock()          # пока идёт обновление, лок занят
        return _sources()

    info = ri.refresh_index('schedule', fetch=fetch)
    assert seen['state']['running'] is True
    assert seen['state']['trigger'] == 'schedule'
    assert seen['state']['started_at'] == '2026-10-03T07:30:05+03:00'
    assert info['built_at'] == '2026-10-03T07:30:05+03:00' and info['age_minutes'] == 0
    assert info['counts']['duplicates'] == 1 and info['source'] == 'v2'

    state = ri.read_state()
    assert state == {'running': False, 'trigger': 'schedule',
                     'started_at': '2026-10-03T07:30:05+03:00',
                     'finished_at': '2026-10-03T07:30:05+03:00', 'error': '',
                     'counts': info['counts']}
    assert ri.load_index()['counts'] == info['counts']
    ri.acquire_run_lock().release()        # лок отпущен


def test_refresh_source_error_keeps_old_index(paths):
    ri.refresh_index('button', fetch=_sources)
    before = open(ri.index_path(), encoding='utf-8').read()

    def fetch():
        raise ri.IndexSourceError('Не настроено подключение к iiko')

    with pytest.raises(ri.IndexSourceError):
        ri.refresh_index('button', fetch=fetch)
    state = ri.read_state()
    assert state['running'] is False
    assert state['error'] == 'Не настроено подключение к iiko'
    assert state['finished_at'] and state['counts'] is None
    assert open(ri.index_path(), encoding='utf-8').read() == before
    ri.acquire_run_lock().release()


def test_refresh_unexpected_error_hides_text(paths):
    def fetch():
        raise KeyError('https://iiko.example/resto/api/x?key=SECRET-TOKEN')

    with pytest.raises(KeyError):
        ri.refresh_index('close', fetch=fetch)
    state = ri.read_state()
    assert state['error'] == 'Сбой обновления индекса: KeyError'
    assert 'SECRET' not in json.dumps(state)
    assert not os.path.exists(ri.index_path())
    ri.acquire_run_lock().release()


def test_refresh_requests_error_no_traceback(paths, capsys):
    def fetch():
        raise requests.ConnectionError('GET https://iiko.example/resto/api/x?key=SECRET-TOKEN failed')

    with pytest.raises(requests.ConnectionError):
        ri.refresh_index('close', fetch=fetch)
    captured = capsys.readouterr()
    assert 'SECRET' not in captured.out + captured.err
    assert ri.read_state()['error'] == 'Сбой обновления индекса: ConnectionError'


def test_refresh_error_survives_state_write_failure(paths, monkeypatch):
    """Не записалось состояние ошибки — наружу всё равно исходная ошибка, лок отпущен."""
    real_write = ri._write_state

    def write_state(state):
        if state['error']:
            raise OSError('диск полон')
        real_write(state)
    monkeypatch.setattr(ri, '_write_state', write_state)

    def fetch():
        raise ri.IndexSourceError('iiko ответил HTTP 500 (товары)')

    with pytest.raises(ri.IndexSourceError) as err:
        ri.refresh_index('button', fetch=fetch)
    assert str(err.value) == 'iiko ответил HTTP 500 (товары)'
    ri.acquire_run_lock().release()


def test_refresh_empty_catalog_does_not_overwrite(paths):
    ri.refresh_index('button', fetch=_sources)
    before = open(ri.index_path(), encoding='utf-8').read()
    only_dishes = [_product('d', 'Порция', type_='DISH')]
    with pytest.raises(ri.IndexSourceError):
        ri.refresh_index('button', fetch=lambda: _sources(only_dishes))
    assert open(ri.index_path(), encoding='utf-8').read() == before
    assert 'ни одной карточки' in ri.read_state()['error']


def test_refresh_busy_from_second_holder(paths):
    ri.refresh_index('button', fetch=_sources)
    state_before = ri.read_state()
    holder = ri.acquire_run_lock()
    calls = []
    try:
        with pytest.raises(ri.RefreshBusy):
            ri.refresh_index('button', fetch=lambda: calls.append(1) or _sources())
        with pytest.raises(ri.RefreshBusy):
            ri.acquire_run_lock(wait=0.3)        # подождали и сдались
    finally:
        holder.release()
    assert calls == []
    assert ri.read_state() == state_before      # занятый лок состояние не трогает


def test_refresh_busy_from_other_process(paths):
    """Лок межпроцессный: держатель — отдельный процесс Python."""
    code = ('import sys, portalocker\n'
            'lock = portalocker.Lock(sys.argv[1], timeout=0, fail_when_locked=True)\n'
            'lock.acquire()\n'
            'print("locked", flush=True)\n'
            'sys.stdin.read()\n'
            'lock.release()\n')
    os.makedirs(os.path.dirname(ri.run_lock_path()), exist_ok=True)
    proc = subprocess.Popen([sys.executable, '-c', code, ri.run_lock_path()],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == 'locked'
        with pytest.raises(ri.RefreshBusy):
            ri.refresh_index('schedule', fetch=_sources)
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
    ri.refresh_index('schedule', fetch=_sources)     # держатель ушёл — обновляемся
    assert ri.read_state()['error'] == ''


def test_refresh_waits_for_other_holder(paths):
    holder = ri.acquire_run_lock()
    timer = threading.Timer(0.3, holder.release)
    timer.start()
    try:
        info = ri.refresh_index('close', wait=5, fetch=_sources)
    finally:
        timer.cancel()
    assert info['counts']['products'] == 17


def test_refresh_with_given_lock_releases_it(paths):
    lock = ri.acquire_run_lock()
    ri.refresh_index('button', lock=lock, fetch=_sources)
    ri.acquire_run_lock().release()
    lock2 = ri.acquire_run_lock()
    with pytest.raises(ValueError):
        ri.refresh_index('button', lock=lock2, fetch=lambda: (_ for _ in ()).throw(ValueError('x')))
    ri.acquire_run_lock().release()       # и при сбое тоже отпущен


# ----- fetch_iiko_sources с фейковым iiko ----------------------------------------------------------

TOKEN = '0b5e5b2c-1a2b-4c3d-8e9f-001122334455'
BASE = 'https://iiko.test:443/resto/api'


class FakeResponse:
    def __init__(self, status=200, payload=None, text=None, content=None):
        self.status_code = status
        self._payload = payload
        if text is None and payload is not None:
            text = json.dumps(payload)
        self.text = text if text is not None else ''
        self.content = content if content is not None else self.text.encode('utf-8')

    def json(self):
        if self._payload is None:
            return json.loads(self.text)       # ValueError на не-JSON, как у requests
        return self._payload


class FakeIiko:
    """Фейковый сервер iiko: handlers {path: FakeResponse | Exception | callable}."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []
        self.sessions = 0
        self.closed = 0

    def session_factory(self):
        fake = self

        class Session:
            def __enter__(self):
                fake.sessions += 1
                return self

            def __exit__(self, *exc):
                fake.closed += 1
                return False

            def get(self, url, params=None, headers=None, timeout=None, allow_redirects=True):
                assert url.startswith(BASE)
                path = url[len(BASE):]
                fake.calls.append({'path': path, 'params': dict(params or {}), 'headers': headers,
                                   'timeout': timeout, 'allow_redirects': allow_redirects})
                handler = fake.handlers.get(path)
                if handler is None:
                    return FakeResponse(404, text='not found')
                if callable(handler) and not isinstance(handler, FakeResponse):
                    handler = handler(path, params)
                if isinstance(handler, Exception):
                    raise handler
                return handler

        return Session

    def paths(self):
        return [c['path'] for c in self.calls]


def _v2_products():
    return [_product('p1', 'Пиво 1', barcodes=['4870009003625']),
            _product('p2', 'Пиво 2', barcodes=[])]


def _handlers(**override):
    handlers = {
        '/auth': FakeResponse(text=TOKEN),
        '/v2/entities/products/list': FakeResponse(payload=_v2_products()),
        '/v2/entities/products/group/list': FakeResponse(payload={'result': 'SUCCESS', 'response': GROUPS[:2]}),
        '/v2/entities/products/category/list': FakeResponse(payload=CATEGORIES),
        '/v2/entities/list': FakeResponse(payload=UNITS),
        '/logout': FakeResponse(text=''),
    }
    handlers.update(override)
    return handlers


@pytest.fixture
def iiko(monkeypatch):
    import config
    monkeypatch.setattr(config, 'IIKO_LOGIN', 'robot')
    monkeypatch.setattr(config, 'IIKO_PASSWORD', 'pa55word')
    monkeypatch.setattr(config, 'IIKO_BASE_URL', BASE)

    def install(**override):
        fake = FakeIiko(_handlers(**override))
        monkeypatch.setattr(requests, 'Session', fake.session_factory())
        return fake
    return install


def _assert_no_secrets(text):
    for secret in (TOKEN, 'key=', 'iiko.test', 'pa55word', hashlib.sha1(b'pa55word').hexdigest(), 'robot'):
        assert secret not in text, secret


def test_fetch_happy_path(iiko):
    fake = iiko()
    sources = ri.fetch_iiko_sources()
    assert fake.paths() == ['/auth', '/v2/entities/products/list', '/v2/entities/products/group/list',
                            '/v2/entities/products/category/list', '/v2/entities/list', '/logout']
    auth = fake.calls[0]
    assert auth['params'] == {'login': 'robot', 'pass': hashlib.sha1(b'pa55word').hexdigest()}
    for call in fake.calls[1:5]:
        assert call['params']['includeDeleted'] == 'true'
        assert call['params']['key'] == TOKEN
        assert call['timeout'] == ri.IIKO_TIMEOUT
        assert call['allow_redirects'] is False
        assert call['headers'] == {'Accept': 'application/json'}
    assert fake.calls[4]['params']['rootType'] == 'MeasureUnit'
    assert fake.calls[5]['params'] == {'key': TOKEN}
    assert fake.calls[5]['timeout'] == ri.LOGOUT_TIMEOUT
    assert fake.sessions == fake.closed == 1
    assert sources['products'] == _v2_products()
    assert sources['groups'] == GROUPS[:2]          # {'result','response'} развёрнут
    assert sources['categories'] == CATEGORIES and sources['units'] == UNITS
    assert sources['xml_barcodes'] is None


def test_fetch_xml_fallback(iiko):
    products = _v2_products()
    for product in products:
        del product['barcodes']
    xml = ('<?xml version="1.0" encoding="UTF-8"?><productDtoes>'
           '<productDto><id>p1</id><name>Пиво 1</name><productType>GOODS</productType>'
           '<barcodes><barcodeContainer><barcode> 4870009003625 </barcode></barcodeContainer>'
           '<barcodeContainer><barcode>46012345</barcode></barcodeContainer></barcodes></productDto>'
           '<productDto><id>p2</id><name>Без кодов</name></productDto>'
           '<productDto><id>g1</id><name>Группа</name><productGroupType>PRODUCTS</productGroupType></productDto>'
           '</productDtoes>')
    fake = iiko(**{'/v2/entities/products/list': FakeResponse(payload=products),
                   '/products': FakeResponse(text=xml, content=xml.encode('utf-8'))})
    sources = ri.fetch_iiko_sources()
    assert fake.paths()[-2:] == ['/products', '/logout']
    xml_call = fake.calls[-2]
    assert xml_call['params'] == {'includeDeleted': 'true', 'key': TOKEN}
    assert xml_call['headers'] == {'Accept': 'application/xml'}
    assert sources['xml_barcodes'] == {'p1': ['4870009003625', '46012345']}
    idx = ri.build_index(sources['products'], sources['groups'], xml_barcodes=sources['xml_barcodes'])
    assert idx['source'] == 'v2+xml'
    assert idx['by_gtin'] == {GTIN_EAN8: ['p1'], GTIN_FOUND: ['p1']}


def test_fetch_auth_variants(iiko):
    fake = iiko(**{'/auth': FakeResponse(text='<string>' + TOKEN + '</string>')})
    ri.fetch_iiko_sources()
    assert fake.calls[1]['params']['key'] == TOKEN

    fake = iiko(**{'/auth': FakeResponse(text='Wrong password for robot')})
    with pytest.raises(ri.IndexSourceError) as err:
        ri.fetch_iiko_sources()
    assert 'ключ входа' in str(err.value)
    assert fake.paths() == ['/auth']             # входа не было — и выхода нет
    _assert_no_secrets(str(err.value))

    fake = iiko(**{'/auth': FakeResponse(403, text='No licence ' + TOKEN)})
    with pytest.raises(ri.IndexSourceError) as err:
        ri.fetch_iiko_sources()
    assert 'HTTP 403' in str(err.value)
    assert fake.paths() == ['/auth']
    _assert_no_secrets(str(err.value))


def test_fetch_network_error_hides_token_and_logs_out(iiko):
    leak = requests.ConnectionError(f'HTTPSConnectionPool: {BASE}/v2/entities/products/group/list'
                                    f'?includeDeleted=true&key={TOKEN} timed out')
    fake = iiko(**{'/v2/entities/products/group/list': leak})
    with pytest.raises(ri.IndexSourceError) as err:
        ri.fetch_iiko_sources()
    text = str(err.value)
    assert 'ConnectionError' in text and 'группы' in text
    _assert_no_secrets(text)
    assert err.value.__cause__ is None and err.value.__suppress_context__ is True
    assert fake.paths()[-1] == '/logout'
    assert fake.paths().count('/logout') == 1


def test_fetch_http_and_payload_errors_log_out(iiko):
    cases = [
        ({'/v2/entities/products/category/list': FakeResponse(500, text=f'error key={TOKEN}')}, 'HTTP 500'),
        ({'/v2/entities/list': FakeResponse(payload={'result': 'ERROR', 'response': f'key={TOKEN}'})},
         'отклонил'),
        ({'/v2/entities/products/list': FakeResponse(text='<html>oops</html>')}, 'не JSON'),
        ({'/v2/entities/products/list': FakeResponse(payload={'unexpected': True})}, 'неожиданный'),
        ({'/v2/entities/products/list': FakeResponse(payload=[])}, 'пустой список'),
    ]
    for override, needle in cases:
        fake = iiko(**override)
        with pytest.raises(ri.IndexSourceError) as err:
            ri.fetch_iiko_sources()
        assert needle in str(err.value), (needle, str(err.value))
        _assert_no_secrets(str(err.value))
        assert fake.paths()[-1] == '/logout', needle


def test_fetch_broken_xml(iiko):
    products = _v2_products()
    for product in products:
        del product['barcodes']
    fake = iiko(**{'/v2/entities/products/list': FakeResponse(payload=products),
                   '/products': FakeResponse(text='<productDtoes><productDto>', content=b'<productDtoes><productDto>')})
    with pytest.raises(ri.IndexSourceError) as err:
        ri.fetch_iiko_sources()
    assert 'XML' in str(err.value)
    assert fake.paths()[-1] == '/logout'


def test_fetch_logout_failure_does_not_mask(iiko, capsys):
    fake = iiko(**{'/logout': requests.ConnectionError(f'{BASE}/logout?key={TOKEN}')})
    sources = ri.fetch_iiko_sources()            # результат есть, сбой выхода только в логе
    assert sources['products'] == _v2_products()
    out = capsys.readouterr().out
    assert 'выход из iiko не прошёл' in out
    _assert_no_secrets(out)

    fake = iiko(**{'/logout': FakeResponse(500),
                   '/v2/entities/products/group/list': FakeResponse(502, text='bad gateway')})
    with pytest.raises(ri.IndexSourceError) as err:
        ri.fetch_iiko_sources()
    assert 'HTTP 502' in str(err.value)            # основная ошибка, а не ошибка выхода
    assert fake.paths()[-1] == '/logout'


def test_fetch_without_credentials(monkeypatch):
    import config
    monkeypatch.setattr(config, 'IIKO_LOGIN', '')
    monkeypatch.setattr(config, 'IIKO_PASSWORD', 'x')

    def no_session():
        raise AssertionError('сессия не должна создаваться')
    monkeypatch.setattr(requests, 'Session', no_session)
    with pytest.raises(ri.IndexSourceError) as err:
        ri.fetch_iiko_sources()
    assert str(err.value) == 'Не настроено подключение к iiko'
    monkeypatch.setattr(config, 'IIKO_LOGIN', 'robot')
    monkeypatch.setattr(config, 'IIKO_PASSWORD', None)
    with pytest.raises(ri.IndexSourceError):
        ri.fetch_iiko_sources()


def test_refresh_with_default_fetch(iiko, monkeypatch):
    _freeze(monkeypatch, _msk(2026, 10, 3, 7, 30, 0))
    fake = iiko()
    info = ri.refresh_index('schedule')
    assert fake.paths()[-1] == '/logout'
    assert info['counts']['products'] == 2 and info['counts']['gtins'] == 1
    assert ri.classify(GTIN_FOUND, ri.load_index())['status'] == 'found'

    iiko(**{'/v2/entities/products/list': FakeResponse(503, text=f'key={TOKEN}')})
    with pytest.raises(ri.IndexSourceError):
        ri.refresh_index('button')
    state = ri.read_state()
    assert 'HTTP 503' in state['error']
    _assert_no_secrets(json.dumps(state, ensure_ascii=False))


# ----- общее ---------------------------------------------------------------------------------

def test_constants_contract():
    assert ri.IIKO_TIMEOUT[1] < 180               # ниже gunicorn --timeout (урок 21)
    assert ri.SEARCH_TYPES == ('GOODS', 'PREPARED')
    assert ri.SIMILAR_MIN_SCORE == 2 and ri.SIMILAR_LIMIT == 5
    assert ri.STALE_RUNNING_SEC == 900
    assert ri.ARCHIVE_GROUP_NAMES == ('архив товаров', 'архив')
    assert ri.INDEX_FILE == 'receiving_index.json'
    assert ri.STATE_FILE == 'receiving_index_state.json'
    assert ri.RUN_LOCK_FILE == '.receiving_index_run.lock'


def test_py310_compatible_syntax():
    """CI и прод — Python 3.10: модуль должен разбираться грамматикой 3.10 (без PEP 701 и т.п.)."""
    src = open(ri.__file__, encoding='utf-8').read()
    ast.parse(src, feature_version=(3, 10))


def test_no_emoji_or_bullet_in_module():
    src = open(ri.__file__, encoding='utf-8').read()
    assert chr(0x2022) not in src          # «жирная точка» запрещена правилами проекта
    assert not any(ord(ch) >= 0x1F000 for ch in src)


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
