"""
Тесты core/nomenclature_xml.py — полной номенклатуры iiko из XML-кэша.

Self-runnable: `py -3 tests/test_nomenclature_xml.py` (совместимо с pytest).

Что защищаем (S-02, S-03 в docs/technical/audits/STOCKS_AUDIT_2026-09-10.md):
товар из XML должен выглядеть как запись OLAP-номенклатуры — `parentId` равен
имени ВЕРХНЕЙ группы, а не GUID прямого родителя, иначе фильтр «Напитки
Фасовка» на /stocks находит только подгруппы. Группы в выдачу не попадают;
сироты, циклы в parentId и битые файлы не роняют парсер; кэш перечитывается по
mtime; слияние с OLAP-номенклатурой не портит входные словари.

Моков нет: маленький XML той же структуры, что data/cache/nomenclature__products.xml
(корень productDtoes, элементы productDto), пишется во временный файл.
Интеграционный тест читает настоящий XML из репозитория.
"""

import copy
import os
import shutil
import sys
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.nomenclature_xml as nx  # noqa: E402

# GUID групп и товаров фикстуры. Значения произвольные, но в формате iiko.
TOP_PACK = '6103ecbf-e6f8-49fe-8cd2-6102d49e14a6'      # верхняя группа «Напитки Фасовка»
SUB_BEER = '4ca1b504-0cff-4997-9a63-d2bcb7b01781'      # подгруппа 2-го уровня «Пиво бут.»
SUB_SUB_IMPORT = '9f0c1b2a-5d6e-4f70-8a91-b2c3d4e5f607'  # подгруппа 3-го уровня «Импорт»
TOP_FOOD = 'c0ffee00-0000-4000-8000-000000000001'      # верхняя группа «ЕДА»
GRP_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
GRP_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
MISSING_GROUP = 'deadbeef-dead-4bee-8eef-deadbeefdead'  # такого id в XML нет

PRD_BOOZY = 'a2dd7913-324a-451f-aa0d-0d8872bfcaa7'
PRD_IMPORT = '11111111-1111-4111-8111-111111111111'
PRD_DIRECT = '22222222-2222-4222-8222-222222222222'
PRD_ORPHAN = '33333333-3333-4333-8333-333333333333'
PRD_NO_PARENT = '44444444-4444-4444-8444-444444444444'
PRD_EMPTY = '55555555-5555-4555-8555-555555555555'
PRD_BARE = '66666666-6666-4666-8666-666666666666'
PRD_IN_A = '77777777-7777-4777-8777-777777777777'
PRD_FOOD = '88888888-8888-4888-8888-888888888888'

XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def _dto(pid, name, parent=None, ptype=None, unit=None, category=None, extra=''):
    """Один productDto в порядке тегов реального файла. Тег с None не пишется вовсе."""
    parts = []
    if pid is not None:
        parts.append(f'<id>{pid}</id>')
    if parent is not None:
        parts.append(f'<parentId>{parent}</parentId>')
    parts.append('<num>1</num><code>1</code>')
    if name is not None:
        parts.append(f'<name>{name}</name>')
    if ptype is not None:
        parts.append(f'<productType>{ptype}</productType>')
    if unit is not None:
        parts.append(f'<mainUnit>{unit}</mainUnit>')
    if category is not None:
        parts.append(f'<productCategory>{category}</productCategory>')
    parts.append(extra)
    parts.append('<containers/><barcodes/>')
    return '<productDto>' + ''.join(parts) + '</productDto>'


def _write_xml(path, dtos):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(XML_HEADER + '<productDtoes>' + ''.join(dtos) + '</productDtoes>')


@contextmanager
def _tmp_xml(dtos):
    """Временный XML-файл фикстуры; удаляется вместе с каталогом после теста."""
    d = tempfile.mkdtemp(prefix='nomxml_')
    path = os.path.join(d, 'nomenclature__products.xml')
    try:
        _write_xml(path, dtos)
        yield path
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _fixture():
    """Дерево как в проде: верхняя группа -> подгруппа -> подподгруппа -> товары."""
    return [
        _dto(TOP_PACK, 'Напитки Фасовка'),
        _dto(SUB_BEER, 'Пиво бут.', parent=TOP_PACK),
        _dto(SUB_SUB_IMPORT, 'Импорт', parent=SUB_BEER),
        _dto(TOP_FOOD, 'ЕДА'),
        _dto(PRD_BOOZY, ' Boozy (Полусладкий), бут. 0,500 .', parent=SUB_BEER,
             ptype='GOODS', unit='шт', category='СПБ-Премиум'),
        _dto(PRD_IMPORT, 'Weihenstephaner Hefe 0,5', parent=SUB_SUB_IMPORT,
             ptype='GOODS', unit='шт', category='Импорт'),
        _dto(PRD_DIRECT, 'Товар прямо в верхней группе', parent=TOP_PACK,
             ptype='GOODS', unit='шт'),
        _dto(PRD_FOOD, 'Гренки', parent=TOP_FOOD, ptype='DISH', unit='порц'),
        _dto(PRD_ORPHAN, 'Сирота', parent=MISSING_GROUP, ptype='GOODS', unit='шт'),
    ]


# --- (а) parentId = имя верхней группы, groupId = GUID прямого родителя ---

def test_product_in_subgroup_gets_top_group_name():
    with _tmp_xml(_fixture()) as path:
        products = nx.parse_products_from_xml(path)

    boozy = products[PRD_BOOZY]
    assert boozy['parentId'] == 'Напитки Фасовка', boozy
    assert boozy['groupId'] == SUB_BEER, boozy
    assert boozy['source'] == 'xml'
    assert boozy['name'] == 'Boozy (Полусладкий), бут. 0,500 .'   # пробелы по краям срезаны
    assert boozy['type'] == 'GOODS'
    assert boozy['category'] == 'СПБ-Премиум'
    assert boozy['mainUnit'] == 'шт'
    # набор ключей совпадает с OLAP-номенклатурой плюс служебные groupId/source
    assert set(boozy) == {'name', 'type', 'category', 'mainUnit', 'parentId',
                          'groupId', 'source'}, sorted(boozy)

    # третий уровень вложенности тоже поднимается до верхней группы
    imported = products[PRD_IMPORT]
    assert imported['parentId'] == 'Напитки Фасовка', imported
    assert imported['groupId'] == SUB_SUB_IMPORT

    # другая верхняя группа не подмешивается
    assert products[PRD_FOOD]['parentId'] == 'ЕДА'
    assert products[PRD_FOOD]['type'] == 'DISH'


def test_product_directly_in_top_group():
    """Товар без подгруппы: parentId — имя своей же группы, groupId — её GUID."""
    with _tmp_xml(_fixture()) as path:
        products = nx.parse_products_from_xml(path)
    direct = products[PRD_DIRECT]
    assert direct['parentId'] == 'Напитки Фасовка'
    assert direct['groupId'] == TOP_PACK


# --- (б) группы в результат не попадают ---

def test_groups_are_not_in_result():
    with _tmp_xml(_fixture()) as path:
        products = nx.parse_products_from_xml(path)
    for gid in (TOP_PACK, SUB_BEER, SUB_SUB_IMPORT, TOP_FOOD):
        assert gid not in products, gid
    assert set(products) == {PRD_BOOZY, PRD_IMPORT, PRD_DIRECT, PRD_FOOD, PRD_ORPHAN}
    assert all(p['type'] for p in products.values()), 'у товара всегда есть productType'


# --- (в) сирота: parentId указывает на отсутствующий узел ---

def test_orphan_product_has_no_top_group():
    with _tmp_xml(_fixture()) as path:
        products = nx.parse_products_from_xml(path)
    orphan = products[PRD_ORPHAN]
    assert orphan['parentId'] is None, orphan
    # GUID прямого родителя сохраняем как есть — пригодится для диагностики
    assert orphan['groupId'] == MISSING_GROUP
    assert orphan['name'] == 'Сирота' and orphan['source'] == 'xml'


# --- (г) цикл в parentId не зацикливает парсер ---

def _run_with_timeout(fn, timeout_sec=5.0):
    """Запустить fn в потоке: зависание -> провал теста, а не вечный прогон."""
    box = {}

    def target():
        try:
            box['result'] = fn()
        except Exception as e:  # noqa: BLE001 — пробрасываем в основной поток
            box['error'] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout_sec)
    assert not t.is_alive(), 'парсер завис (цикл в parentId?)'
    if 'error' in box:
        raise box['error']
    return box['result']


def test_parent_cycle_does_not_hang():
    dtos = [
        _dto(GRP_A, 'Группа A', parent=GRP_B),
        _dto(GRP_B, 'Группа B', parent=GRP_A),
        _dto(PRD_IN_A, 'Товар в цикле', parent=GRP_A, ptype='GOODS', unit='шт'),
        _dto(TOP_FOOD, 'ЕДА'),
        _dto(PRD_FOOD, 'Гренки', parent=TOP_FOOD, ptype='DISH', unit='порц'),
    ]
    with _tmp_xml(dtos) as path:
        first = _run_with_timeout(lambda: nx.parse_products_from_xml(path))
        second = _run_with_timeout(lambda: nx.parse_products_from_xml(path))

    looped = first[PRD_IN_A]
    # верхней группы у цикла нет; парсер обязан остановиться и отдать имя
    # одной из групп цикла, а не GUID и не пустую строку
    assert looped['parentId'] in ('Группа A', 'Группа B'), looped
    assert looped['groupId'] == GRP_A
    assert first == second, 'один вход -> один выход'
    # остальные товары от цикла не пострадали
    assert first[PRD_FOOD]['parentId'] == 'ЕДА'
    assert GRP_A not in first and GRP_B not in first


# --- (д) пустые и отсутствующие теги -> None ---

def test_empty_and_missing_tags_give_none():
    dtos = [
        _dto(TOP_PACK, 'Напитки Фасовка'),
        # пустые теги: <productCategory></productCategory>, <mainUnit/>, имя из пробелов
        _dto(PRD_EMPTY, '   ', parent=TOP_PACK, ptype='GOODS',
             extra='<productCategory></productCategory><mainUnit/>'),
        # тегов нет вовсе: ни parentId, ни mainUnit, ни productCategory
        _dto(PRD_BARE, 'Без тегов', ptype='OUTER'),
        # productDto без id — пропускается, не роняет парсер
        _dto(None, 'Без id', parent=TOP_PACK, ptype='GOODS'),
        # id из пробелов — то же самое
        _dto('  ', 'Пустой id', parent=TOP_PACK, ptype='GOODS'),
    ]
    with _tmp_xml(dtos) as path:
        products = nx.parse_products_from_xml(path)

    assert set(products) == {PRD_EMPTY, PRD_BARE}, sorted(products)

    empty = products[PRD_EMPTY]
    assert empty['name'] is None, empty
    assert empty['category'] is None, empty
    assert empty['mainUnit'] is None, empty
    assert empty['parentId'] == 'Напитки Фасовка'

    bare = products[PRD_BARE]
    assert bare['parentId'] is None, bare
    assert bare['groupId'] is None, bare
    assert bare['mainUnit'] is None and bare['category'] is None, bare
    assert bare['type'] == 'OUTER'
    # нигде не должно быть пустых строк вместо None
    for rec in products.values():
        for key, value in rec.items():
            assert value != '', (key, rec)


# --- (е) отсутствующий файл и битый XML -> {} ---

def test_missing_file_and_broken_xml_give_empty_dict():
    d = tempfile.mkdtemp(prefix='nomxml_')
    try:
        missing = os.path.join(d, 'no_such_file.xml')
        assert nx.parse_products_from_xml(missing) == {}

        truncated = os.path.join(d, 'truncated.xml')
        with open(truncated, 'w', encoding='utf-8') as f:
            f.write(XML_HEADER + '<productDtoes><productDto><id>x</id><name>обрыв')
        assert nx.parse_products_from_xml(truncated) == {}

        garbage = os.path.join(d, 'garbage.xml')
        with open(garbage, 'w', encoding='utf-8') as f:
            f.write('{"это": "не xml"}')
        assert nx.parse_products_from_xml(garbage) == {}

        empty_tree = os.path.join(d, 'empty.xml')
        with open(empty_tree, 'w', encoding='utf-8') as f:
            f.write(XML_HEADER + '<productDtoes/>')
        assert nx.parse_products_from_xml(empty_tree) == {}
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- (ж) кэш по mtime ---

def test_get_xml_nomenclature_caches_by_mtime():
    saved = (nx._cache, nx._cache_mtime, nx._cache_path)
    d = tempfile.mkdtemp(prefix='nomxml_')
    path = os.path.join(d, 'products.xml')
    base = [_dto(TOP_PACK, 'Напитки Фасовка'),
            _dto(PRD_DIRECT, 'Товар 1', parent=TOP_PACK, ptype='GOODS', unit='шт')]
    try:
        _write_xml(path, base)
        first = nx.get_xml_nomenclature(path)
        assert set(first) == {PRD_DIRECT}
        assert nx.get_xml_nomenclature(path) is first, 'без изменений файла — тот же объект'

        # перезапись с другим mtime -> перечитано
        _write_xml(path, base + [_dto(PRD_BOOZY, 'Товар 2', parent=TOP_PACK,
                                       ptype='GOODS', unit='шт')])
        mtime = os.path.getmtime(path)
        os.utime(path, (mtime + 10, mtime + 10))
        third = nx.get_xml_nomenclature(path)
        assert third is not first
        assert set(third) == {PRD_DIRECT, PRD_BOOZY}, sorted(third)
        assert nx.get_xml_nomenclature(path) is third

        # ключ кэша — именно mtime: содержимое сменилось, mtime вернули прежний -> кэш
        _write_xml(path, base)
        os.utime(path, (mtime + 10, mtime + 10))
        assert nx.get_xml_nomenclature(path) is third, 'при том же mtime файл не перечитывается'

        # force_refresh перечитывает независимо от mtime
        forced = nx.get_xml_nomenclature(path, force_refresh=True)
        assert forced is not third
        assert set(forced) == {PRD_DIRECT}, sorted(forced)
        assert nx.get_xml_nomenclature(path) is forced, 'после force_refresh кэш обновлён'
    finally:
        nx._cache, nx._cache_mtime, nx._cache_path = saved
        shutil.rmtree(d, ignore_errors=True)


# --- (з) слияние с OLAP-номенклатурой ---

def test_merge_primary_overrides_fallback():
    primary = {
        'p1': {'name': 'OLAP имя', 'type': 'GOODS', 'category': None,
               'mainUnit': 'шт', 'parentId': 'Напитки Фасовка'},
    }
    fallback = {
        'p1': {'name': 'XML имя', 'type': 'GOODS', 'category': 'Импорт',
               'mainUnit': 'шт', 'parentId': 'Напитки Фасовка',
               'groupId': SUB_BEER, 'source': 'xml'},
        'p2': {'name': 'Только в XML', 'type': 'GOODS', 'category': None,
               'mainUnit': 'л', 'parentId': 'Напитки Розлив',
               'groupId': TOP_PACK, 'source': 'xml'},
    }
    primary_before = copy.deepcopy(primary)
    fallback_before = copy.deepcopy(fallback)

    merged = nx.merge_nomenclature(primary, fallback)
    assert set(merged) == {'p1', 'p2'}
    assert merged['p1'] is primary['p1'], 'по id побеждает primary целиком, без смешивания полей'
    assert merged['p1']['name'] == 'OLAP имя'
    assert merged['p2']['name'] == 'Только в XML'

    # входные словари не тронуты
    assert primary == primary_before and fallback == fallback_before
    assert merged is not primary and merged is not fallback
    merged['p3'] = {'name': 'мутация результата'}
    assert 'p3' not in primary and 'p3' not in fallback

    # вырожденные случаи
    assert nx.merge_nomenclature(None, None) == {}
    assert nx.merge_nomenclature({}, {}) == {}
    only_fallback = nx.merge_nomenclature(None, fallback)
    assert only_fallback == fallback and only_fallback is not fallback
    only_primary = nx.merge_nomenclature(primary, None)
    assert only_primary == primary and only_primary is not primary
    assert primary == primary_before and fallback == fallback_before


# --- интеграция: настоящий XML из репозитория (регресс S-03) ---

def _top_groups_from_xml(path):
    """{GUID: имя} групп без родителя в XML — независимо от проверяемого модуля."""
    nodes = {}
    for el in ET.parse(path).getroot().iter('productDto'):
        rec = {child.tag: (child.text or '').strip() for child in el}
        if rec.get('id'):
            nodes[rec['id']] = rec
    return {gid: rec['name'] for gid, rec in nodes.items()
            if not rec.get('productType') and rec.get('parentId', '') not in nodes}


def test_real_xml_full_nomenclature_top_groups():
    path = nx.DEFAULT_XML_PATH
    if not os.path.exists(path):
        raise unittest.SkipTest(f'нет XML-кэша номенклатуры: {path}')

    products = nx.parse_products_from_xml(path)
    assert len(products) >= 8000, len(products)

    top_groups = _top_groups_from_xml(path)
    top_names = set(top_groups.values())
    for name in ('Напитки Фасовка', 'Напитки Розлив', 'ЕДА'):
        assert name in top_names, (name, sorted(top_names))

    parent_names = {p['parentId'] for p in products.values()}
    for name in ('Напитки Фасовка', 'Напитки Розлив', 'ЕДА'):
        assert name in parent_names, (name, sorted(n for n in parent_names if n))
    # parentId — всегда имя верхней группы (или None у сироты), никогда GUID
    assert parent_names - {None} <= top_names, sorted(parent_names - {None} - top_names)

    # S-03: в проде товары «Напитки Фасовка» лежат в подгруппах, а не в самой
    # группе. По сырому XML фильтр по группе находил только подгруппы; после
    # нормализации у группы должны быть товары
    pack_guid = [gid for gid, name in top_groups.items() if name == 'Напитки Фасовка']
    assert len(pack_guid) == 1, pack_guid
    packed = [p for p in products.values() if p['parentId'] == 'Напитки Фасовка']
    assert packed, 'у «Напитки Фасовка» нет ни одного товара — регресс S-03'
    assert any(p['groupId'] != pack_guid[0] for p in packed), \
        'ожидались товары из подгрупп «Напитки Фасовка»'

    # формат каждой записи совпадает с OLAP-номенклатурой
    for pid, p in products.items():
        assert p['source'] == 'xml' and p['type'], (pid, p)
        assert p['name'] != '' and p['mainUnit'] != '' and p['category'] != '', (pid, p)
    assert not set(top_groups) & set(products), 'группы попали в товары'


if __name__ == '__main__':
    import inspect
    import traceback

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith('test_') and inspect.isfunction(f)]
    passed = failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
            print('  ok  ' + name)
            passed += 1
        except unittest.SkipTest as e:
            skipped += 1
            print('SKIP  ' + name + ': ' + str(e))
        except Exception as e:
            failed += 1
            print('FAIL  ' + name + ': ' + repr(e))
            traceback.print_exc()
    print('\n%d passed, %d failed, %d skipped' % (passed, failed, skipped))
    sys.exit(1 if failed else 0)
