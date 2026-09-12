"""
Тесты справочника поставщиков (core/supplier_directory.py) и его API
(routes/suppliers.py) — этап 3 редизайна «Заказы и остатки» (2026-09-11).

Self-runnable: `py -3 tests/test_supplier_directory.py` (совместимо с pytest).

Файл справочника — временный; iiko не нужен (номенклатура подменяется).

Что проверяется:
- нормализация написаний (регистр, кавычки, пробелы) и разрешение алиаса в
  каноническое имя; неизвестная категория остаётся собой, пустая — «Без поставщика»;
- стартовый набор без файла; параметры по умолчанию с флагом is_default;
- проверка полей: срок 0..60, кратность >= 1, дни доставки 0..6 непустые,
  алиасы уникальны между поставщиками, имя не совпадает с чужим алиасом;
- upsert/переименование/удаление/добавление алиаса с автором и временем,
  сохранение на диск и чтение новым экземпляром, кэш по mtime;
- API: список с незаведёнными категориями, PUT с ошибками 400, DELETE 404,
  POST alias, конфликт алиаса.
"""

import atexit
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
import routes.suppliers as rsup  # noqa: E402
from routes.suppliers import suppliers_bp  # noqa: E402
from core.supplier_directory import (SupplierDirectory, SupplierDirectoryUnavailable, normalize_name,  # noqa: E402
                                     make_record, seed_records, categories_in_use, NO_SUPPLIER,
                                     DEFAULT_LEAD_TIME_DAYS, DEFAULT_PACK_SIZE, SEED_SUPPLIERS)

USER = {'login': 'anna', 'display_name': 'Анна'}


def _dir():
    tmp = tempfile.mkdtemp(prefix='suppliers_test_')
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    return SupplierDirectory(os.path.join(tmp, 'suppliers.json'))


# --- нормализация и разрешение ---------------------------------------------------

def test_normalize_and_resolve():
    assert normalize_name('  ООО  "Май" ') == 'ооо май'
    assert normalize_name('ООО «МАЙ»') == 'ооо май'
    assert normalize_name('ООО “Май”') == 'ооо май' == normalize_name('ООО „Май“')   # типографские кавычки
    assert normalize_name(None) == ''
    d = _dir()
    d.upsert('Пивной дом', {'aliases': ['ООО "Пивной дом"', 'Пивной Дом СПб']}, USER)
    v = d.view()
    assert v.resolve('ооо пивной дом') == 'Пивной дом'
    assert v.resolve('Пивной  Дом  СПб') == 'Пивной дом'
    assert v.resolve('пивной дом') == 'Пивной дом'
    assert v.resolve('ИП Ромашка') == 'ИП Ромашка'          # неизвестный — как есть
    assert v.resolve('') == NO_SUPPLIER and v.resolve(None) == NO_SUPPLIER
    assert v.get('пивной дом спб')['name'] == 'Пивной дом'
    assert v.get('нет такого') is None
    # стартовый набор: написания МаркетБир склеены, кавычки не мешают
    assert v.resolve('ООО "МаркетБир"') == 'ООО МаркетБир' == v.resolve('Маркет бир') == v.resolve('ООО “МаркетБир”')


def test_seed_and_default_params():
    d = _dir()
    assert not d.is_stored()
    names = {r['name'] for r in d.list()}
    assert names == set(SEED_SUPPLIERS)
    v = d.view()
    metro = v.params('Метро')
    assert metro['lead_time_days'] == 1 and metro['self_pickup'] is True and metro['is_default'] is False
    assert v.params('ООО "МП-Арсенал АО"')['name'] == 'ООО МП Арсенал'       # алиас из стартового набора
    unknown = v.params('ИП Ромашка')
    assert unknown == {'name': 'ИП Ромашка', 'lead_time_days': DEFAULT_LEAD_TIME_DAYS,
                       'pack_size': DEFAULT_PACK_SIZE, 'delivery_weekdays': [0, 1, 2, 3, 4],
                       'self_pickup': False, 'is_default': True}
    assert v.params('')['name'] == NO_SUPPLIER and v.params('')['is_default'] is True
    assert seed_records()['Метро']['delivery_weekdays'] == [0, 1, 2, 3, 4]


# --- проверка полей ----------------------------------------------------------------

def test_make_record_validation():
    ok = make_record(' Ромашка ', {'aliases': 'ИП Ромашка, ромашка ; Ромашка', 'lead_time_days': '2',
                                   'delivery_weekdays': [1, '3', 3], 'pack_size': 6.0, 'note': 'x' * 600})
    assert ok['name'] == 'Ромашка' and ok['aliases'] == ['ИП Ромашка']       # дубликаты и своё имя убраны
    assert ok['lead_time_days'] == 2 and ok['delivery_weekdays'] == [1, 3] and ok['pack_size'] == 6
    assert len(ok['note']) == 500
    bad = [
        ('', {}), ('x' * 121, {}),
        ('A', {'lead_time_days': 'два'}), ('A', {'lead_time_days': 61}), ('A', {'lead_time_days': 0}),
        ('A', {'lead_time_days': 1e400}), ('A', {'pack_size': 'inf'}),
        ('A', {'pack_size': 0}), ('A', {'delivery_weekdays': []}), ('A', {'delivery_weekdays': [7]}),
        ('A', {'delivery_weekdays': 'пн'}), ('A', {'aliases': 5}), ('A', {'self_pickup': 'может быть'}),
    ]
    for name, fields in bad:
        try:
            make_record(name, fields)
            assert False, (name, fields)
        except ValueError:
            pass
    # base сохраняет незатронутые поля; null в поле = «не передано», а не сброс
    base = {'lead_time_days': 5, 'aliases': ['a1'], 'self_pickup': True}
    rec = make_record('A', {'note': 'n', 'aliases': None, 'lead_time_days': None}, base=base)
    assert rec['lead_time_days'] == 5 and rec['aliases'] == ['a1'] and rec['self_pickup'] is True
    assert make_record('A', {'self_pickup': 'false'})['self_pickup'] is False
    assert make_record('A', {'self_pickup': 'да'})['self_pickup'] is True
    assert make_record('Лента/', {})['name'] == 'Лента'


def test_upsert_rename_delete_alias_and_persistence():
    d = _dir()
    rec = d.upsert('Ромашка', {'aliases': ['ИП Ромашка'], 'lead_time_days': 2}, USER)
    assert rec['updated_by'] == 'anna' and rec['updated_at']
    assert d.is_stored()
    again = SupplierDirectory(d.data_file)
    assert again.get('ип ромашка')['name'] == 'Ромашка'
    assert 'Метро' in {r['name'] for r in again.list()}                 # стартовый набор сохранён
    # частичное обновление не трогает остальные поля
    rec = d.upsert('ромашка', {'pack_size': 12}, USER)
    assert rec['name'] == 'Ромашка' and rec['lead_time_days'] == 2 and rec['aliases'] == ['ИП Ромашка']
    # переименование: алиасы сохраняются, старое имя становится написанием
    rec = d.upsert('Ромашка', {}, USER, rename_to='ИП Ромашкин')
    assert rec['name'] == 'ИП Ромашкин' and rec['aliases'] == ['ИП Ромашка', 'Ромашка']
    assert d.get('Ромашка')['name'] == 'ИП Ромашкин' and d.get('ип ромашка')['name'] == 'ИП Ромашкин'
    # переименование только регистра/кавычек — одна запись, а не две
    rec = d.upsert('ИП Ромашкин', {}, USER, rename_to='ИП РОМАШКИН')
    assert rec['name'] == 'ИП РОМАШКИН' and [r['name'] for r in d.list() if 'ромашкин' in r['name'].casefold()] == ['ИП РОМАШКИН']
    assert rec['aliases'] == ['ИП Ромашка', 'Ромашка']
    rec = d.upsert('ИП РОМАШКИН', {}, USER, rename_to='ИП Ромашкин')
    # переименовать в чужое имя или написание нельзя
    for taken in ('Метро', 'метро', 'ООО "МП-Арсенал АО"'):
        try:
            d.upsert('ИП Ромашкин', {}, USER, rename_to=taken)
            assert False, taken
        except ValueError:
            pass
    assert d.get('Метро')['lead_time_days'] == 1 and d.get('ИП Ромашкин')['name'] == 'ИП Ромашкин'
    # алиас
    rec = d.add_alias('ИП Ромашкин', 'Ромашка ООО', USER)
    assert rec['aliases'] == ['ИП Ромашка', 'Ромашка', 'Ромашка ООО']      # «Ромашка» осталось от переименования
    try:
        d.add_alias('нет такого', 'x', USER)
        assert False
    except KeyError:
        pass
    # уникальность: чужой алиас и чужое имя
    for name, fields in (('Лента', {'aliases': ['ИП Ромашка']}), ('ип ромашка', {}),
                         ('Новый', {'aliases': ['метро']})):
        try:
            d.upsert(name, fields, USER)
            assert False, (name, fields)
        except ValueError:
            pass
    assert d.delete('ИП РОМАШКИН') is True and d.delete('ИП Ромашкин') is False
    assert d.view().resolve('ИП Ромашка') == 'ИП Ромашка'


def test_add_alias_merges_under_lock_between_instances():
    """Два воркера добавляют написания одному поставщику: ни одно не теряется."""
    d1 = _dir()
    d2 = SupplierDirectory(d1.data_file)
    d1.upsert('Криспи', {'aliases': ['ООО Криспи']}, USER)
    d1.add_alias('Криспи', 'Crispy', USER)
    d2.add_alias('криспи', 'Криспи СПб', USER)
    assert d1.get('Криспи')['aliases'] == ['ООО Криспи', 'Crispy', 'Криспи СПб']
    assert SupplierDirectory(d1.data_file).view().resolve('crispy') == 'Криспи'


def test_corrupted_file_reads_seed_but_refuses_writes():
    """Битый файл: чтение отдаёт стартовый набор, запись запрещена, файл не перезаписан."""
    d = _dir()
    with open(d.data_file, 'w', encoding='utf-8') as f:
        f.write('{broken')
    assert {r['name'] for r in d.list()} == set(SEED_SUPPLIERS)
    for call in (lambda: d.upsert('Метро', {'note': 'x'}, USER), lambda: d.delete('Метро'),
                 lambda: d.add_alias('Метро', 'Metro', USER)):
        try:
            call()
            assert False
        except SupplierDirectoryUnavailable:
            pass
    assert open(d.data_file, encoding='utf-8').read() == '{broken'
    with open(d.data_file, 'w', encoding='utf-8') as f:
        f.write('{"version": 1, "suppliers": {"Ок": {"lead_time_days": 2}, "Плохой": {"lead_time_days": 99}}}')
    assert {r['name'] for r in d.list()} == {'Ок'}                      # битая запись пропущена при чтении
    try:
        d.upsert('Ок', {'note': 'x'}, USER)                             # но не удаляется молча при записи
        assert False
    except SupplierDirectoryUnavailable:
        pass
    assert 'Плохой' in open(d.data_file, encoding='utf-8').read()


def test_categories_in_use():
    nom = {
        'a': {'type': 'GOODS', 'category': 'Метро'},
        'b': {'type': 'GOODS', 'category': ' Метро '},
        'c': {'type': 'DISH', 'category': 'Кухня'},
        'd': {'type': 'GOODS', 'category': None},
        'e': 'мусор',
    }
    assert categories_in_use(nom) == {'Метро': 2, NO_SUPPLIER: 1}


# --- API ----------------------------------------------------------------------------------

@contextmanager
def _client(nomenclature=None):
    d = _dir()
    saved = (rsup.get_supplier_directory, rsup.current_user)
    rsup.get_supplier_directory = lambda: d
    rsup.current_user = lambda: USER
    import core.stock_snapshot as ss
    saved_nom = ss.get_stocks_nomenclature
    ss.get_stocks_nomenclature = lambda *a, **k: nomenclature
    app = Flask('test_suppliers')
    app.register_blueprint(suppliers_bp)
    try:
        yield app.test_client(), d
    finally:
        rsup.get_supplier_directory, rsup.current_user = saved
        ss.get_stocks_nomenclature = saved_nom


def test_api_list_put_delete_alias():
    nom = {'a': {'type': 'GOODS', 'category': 'ООО "Ромашка"'}, 'b': {'type': 'GOODS', 'category': 'Метро'},
           'c': {'type': 'GOODS', 'category': 'ООО "Ромашка"'}, 'd': {'type': 'GOODS', 'category': 'ООО “Фёст”'}}
    with _client(nom) as (c, d):
        r = c.get('/api/suppliers')
        payload = r.get_json()
        assert r.status_code == 200 and payload['stored'] is False and payload['nomenclature_available'] is True
        # «ООО “Фёст”» с типографскими кавычками — это стартовый «ООО Фёст», не «без поставщика»
        assert payload['unmapped_categories'] == [{'category': 'ООО "Ромашка"', 'products': 2}]
        assert payload['defaults'] == {'lead_time_days': DEFAULT_LEAD_TIME_DAYS, 'pack_size': DEFAULT_PACK_SIZE,
                                       'delivery_weekdays': [0, 1, 2, 3, 4],
                                       'min_lead_time_days': 1, 'max_lead_time_days': 60}
        assert 'Метро' in {s['name'] for s in payload['suppliers']}

        r = c.put('/api/suppliers/Ромашка', json={'aliases': ['ООО "Ромашка"'], 'lead_time_days': 2,
                                                  'delivery_weekdays': [1, 4], 'self_pickup': 'false'})
        payload = r.get_json()
        assert r.status_code == 200, payload
        assert payload['supplier']['name'] == 'Ромашка' and payload['supplier']['delivery_weekdays'] == [1, 4]
        assert payload['supplier']['self_pickup'] is False
        assert payload['unmapped_categories'] == [] and payload['stored'] is True

        r = c.put('/api/suppliers/Ромашка', json={'lead_time_days': 'много'})
        assert r.status_code == 400 and 'Срок поставки' in r.get_json()['error']
        r = c.put('/api/suppliers/Ромашка', json={'lead_time_days': 1e400})
        assert r.status_code == 400
        r = c.put('/api/suppliers/Лента', json={'aliases': ['ООО "Ромашка"']})
        assert r.status_code == 400 and 'Ромашка' in r.get_json()['error']
        r = c.put('/api/suppliers/Ромашка', json={'rename_to': 'Метро'})
        assert r.status_code == 400 and 'занято' in r.get_json()['error']
        r = c.put('/api/suppliers/Ромашка', json={'rename_to': 'ИП Ромашкин'})
        assert r.status_code == 200 and r.get_json()['supplier']['name'] == 'ИП Ромашкин'
        assert r.get_json()['orders_renamed'] == 0
        assert d.get('ромашка')['name'] == 'ИП Ромашкин' and d.get('ооо "ромашка"')['name'] == 'ИП Ромашкин'
        # завершающий слэш в пути не создаёт нового поставщика
        r = c.put('/api/suppliers/ИП Ромашкин/', json={'note': 'x'})
        assert r.status_code == 200 and [s['name'] for s in r.get_json()['suppliers'] if 'Ромашкин' in s['name']] == ['ИП Ромашкин']

        r = c.post('/api/suppliers/ИП Ромашкин/aliases', json={'alias': 'Romashka'})
        assert r.status_code == 200 and 'Romashka' in r.get_json()['supplier']['aliases']
        assert c.post('/api/suppliers/ИП Ромашкин/aliases', json={}).status_code == 400
        assert c.post('/api/suppliers/Нет/aliases', json={'alias': 'x'}).status_code == 404

        assert c.delete('/api/suppliers/Нет').status_code == 404
        r = c.delete('/api/suppliers/ИП Ромашкин')
        assert r.status_code == 200 and d.get('ИП Ромашкин') is None

        # нечитаемый файл → 503 с кодом, файл цел
        with open(d.data_file, 'w', encoding='utf-8') as f:
            f.write('{broken')
        r = c.put('/api/suppliers/Лента', json={'note': 'x'})
        assert r.status_code == 503 and r.get_json()['code'] == 'suppliers_unavailable'
        assert c.get('/api/suppliers').status_code == 200          # чтение: стартовый набор
        assert open(d.data_file, encoding='utf-8').read() == '{broken'


def test_api_without_nomenclature():
    with _client(None) as (c, _):
        payload = c.get('/api/suppliers').get_json()
        assert payload['nomenclature_available'] is False and payload['unmapped_categories'] == []


if __name__ == '__main__':
    import inspect
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and inspect.isfunction(fn):
            try:
                fn()
                print(f'ok   {name}')
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f'FAIL {name}: {e!r}')
    sys.exit(1 if failed else 0)
