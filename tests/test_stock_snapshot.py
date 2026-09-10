"""
Тесты снимка сети для страниц остатков (core/stock_snapshot.py).

Self-runnable: `py -3 tests/test_stock_snapshot.py` (совместимо с pytest).

Моков iiko нет: OlapReports подменяется атрибутом модуля на класс-заглушку со
счётчиками вызовов, как в tests/test_me_routes.py. Проверяется главное из
S-07/S-08 (docs/technical/audits/STOCKS_AUDIT_2026-09-10.md): удачный снимок
кэшируется и не дёргает iiko повторно, неудачный (None или пустые остатки/
операции) не кэшируется и не маскируется, но SNAPSHOT_FAIL_TTL секунд после
неудачи iiko не дёргается снова (отрицательный кэш); force сбрасывает оба кэша;
сессия iiko закрывается всегда. Номенклатура: OLAP перекрывает XML по id, XML
дополняет и даёт имя верхней группы вместо GUID.
"""

import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SESSION_COOKIE_SECURE'] = '0'

import extensions  # noqa: E402
import core.stock_snapshot as ss  # noqa: E402

# Фиксированное «сейчас», чтобы границы окна не зависели от дня прогона.
FIXED_NOW = datetime(2025, 11, 5, 10, 30, 0)
FIXED_TODAY = date(2025, 11, 5)

BALANCES = [{'store': 'store-a', 'product': 'p1', 'amount': 12.0, 'sum': 100.0}]
OPERATIONS = [{'product': 'p1', 'primaryStore': 'store-a', 'amount': '-1.000000000',
               'incoming': 'false', 'documentType': 'SALES_DOCUMENT', 'date': '20.10.2025'}]


class _FixedDatetime(datetime):
    """datetime с фиксированным now(); остальное поведение штатное."""

    @classmethod
    def now(cls, tz=None):
        return cls(FIXED_NOW.year, FIXED_NOW.month, FIXED_NOW.day,
                   FIXED_NOW.hour, FIXED_NOW.minute, FIXED_NOW.second)


class _FakeOlap:
    """Заглушка OlapReports: отдаёт заданные данные и считает вызовы."""

    calls = None            # общий счётчик для всех экземпляров текущего сценария
    balances = BALANCES
    operations = OPERATIONS
    connect_ok = True
    raise_on_balances = None

    def __init__(self):
        type(self).calls['init'] += 1

    def connect(self):
        type(self).calls['connect'] += 1
        return type(self).connect_ok

    def get_store_balances(self, timestamp=None):
        type(self).calls['balances'] += 1
        if type(self).raise_on_balances is not None:
            raise type(self).raise_on_balances
        return type(self).balances

    def get_store_operations_report(self, date_from, date_to, bar_name=None):
        type(self).calls['operations'] += 1
        type(self).calls['operations_args'] = (date_from, date_to, bar_name)
        return type(self).operations

    def disconnect(self):
        type(self).calls['disconnect'] += 1


def _fresh_calls():
    return {'init': 0, 'connect': 0, 'balances': 0, 'operations': 0, 'disconnect': 0,
            'operations_args': None}


def _install(balances=BALANCES, operations=OPERATIONS, connect_ok=True, raise_on_balances=None):
    """Подменить OlapReports и datetime в модуле, очистить кэш снимка. Возвращает (класс, restore)."""
    fake = type('FakeOlapScenario', (_FakeOlap,), {
        'calls': _fresh_calls(),
        'balances': balances,
        'operations': operations,
        'connect_ok': connect_ok,
        'raise_on_balances': raise_on_balances,
    })
    orig_olap = ss.OlapReports
    orig_datetime = ss.datetime
    ss.OlapReports = fake
    ss.datetime = _FixedDatetime
    extensions.DASHBOARD_OLAP_CACHE.pop(ss.SNAPSHOT_KEY, None)
    ss._last_failure_at = None

    def restore():
        ss.OlapReports = orig_olap
        ss.datetime = orig_datetime
        extensions.DASHBOARD_OLAP_CACHE.pop(ss.SNAPSHOT_KEY, None)
        ss._last_failure_at = None
    return fake, restore


# --- успешный снимок --------------------------------------------------------

def test_snapshot_success_shape():
    fake, restore = _install()
    try:
        snap = ss.get_stock_snapshot()
        assert snap is not None
        assert snap['balances'] is BALANCES
        assert snap['operations'] is OPERATIONS
        assert snap['today'] == FIXED_TODAY.isoformat()
        assert snap['date_from'] == '06.10.2025'        # today − 30
        assert snap['date_to'] == '05.11.2025'
        assert snap['window_days'] == ss.WINDOW_DAYS == 30
        assert snap['fetched_at'] == '2025-11-05T10:30:00'
        assert set(snap) == {'balances', 'operations', 'today', 'date_from', 'date_to',
                             'window_days', 'fetched_at'}
        # окно в iiko ушло теми же границами, без фильтра по бару (вся сеть)
        assert fake.calls['operations_args'] == ('06.10.2025', '05.11.2025', None)
        assert fake.calls['connect'] == 1 and fake.calls['disconnect'] == 1
    finally:
        restore()


def test_snapshot_custom_window():
    fake, restore = _install()
    try:
        snap = ss.get_stock_snapshot(window_days=7)
        assert snap['date_from'] == '29.10.2025'
        assert snap['window_days'] == 7
        assert fake.calls['operations_args'] == ('29.10.2025', '05.11.2025', None)
    finally:
        restore()


def test_snapshot_is_cached_and_does_not_refetch():
    fake, restore = _install()
    try:
        first = ss.get_stock_snapshot()
        second = ss.get_stock_snapshot()
        third = ss.get_stock_snapshot()
        assert first is second is third
        assert fake.calls['init'] == 1
        assert fake.calls['connect'] == 1
        assert fake.calls['balances'] == 1
        assert fake.calls['operations'] == 1
        assert fake.calls['disconnect'] == 1
        assert extensions.DASHBOARD_OLAP_CACHE[ss.SNAPSHOT_KEY]['data'] is first
    finally:
        restore()


def test_snapshot_cache_respects_ttl():
    """ttl=0 — каждый вызов заново дёргает iiko (кэш есть, но протух)."""
    fake, restore = _install()
    try:
        ss.get_stock_snapshot(ttl=0)
        ss.get_stock_snapshot(ttl=0)
        assert fake.calls['connect'] == 2
        assert fake.calls['disconnect'] == 2
    finally:
        restore()


# --- сбой iiko: None и не кэшируется ----------------------------------------

def test_balances_none_gives_none_and_is_not_cached():
    fake, restore = _install(balances=None)
    try:
        assert ss.get_stock_snapshot() is None
        assert ss.SNAPSHOT_KEY not in extensions.DASHBOARD_OLAP_CACHE
        assert ss._last_failure_at is not None
        # Отрицательный кэш: повторный вызов в течение SNAPSHOT_FAIL_TTL в iiko не ходит.
        assert ss.get_stock_snapshot() is None
        assert fake.calls['connect'] == 1
        assert fake.calls['balances'] == 1
        assert fake.calls['operations'] == 0       # до операций дело не дошло
        assert fake.calls['disconnect'] == 1
        # Срок отрицательного кэша вышел — снова идём в iiko.
        ss._last_failure_at -= ss.SNAPSHOT_FAIL_TTL + 1
        assert ss.get_stock_snapshot() is None
        assert fake.calls['connect'] == 2
        assert fake.calls['disconnect'] == 2
    finally:
        restore()


def test_operations_none_gives_none_and_is_not_cached():
    fake, restore = _install(operations=None)
    try:
        assert ss.get_stock_snapshot() is None
        assert ss.SNAPSHOT_KEY not in extensions.DASHBOARD_OLAP_CACHE
        assert fake.calls['operations'] == 1 and fake.calls['disconnect'] == 1
        assert ss.get_stock_snapshot(force=True) is None      # force сбрасывает отрицательный кэш
        assert fake.calls['connect'] == 2
        assert fake.calls['operations'] == 2
        assert fake.calls['disconnect'] == 2
    finally:
        restore()


def test_empty_lists_are_a_failure_and_not_cached():
    """Пустые остатки или операции по всей сети — сбой iiko, не данные: None и не в кэше."""
    for balances, operations in (([], OPERATIONS), (BALANCES, [])):
        fake, restore = _install(balances=balances, operations=operations)
        try:
            assert ss.get_stock_snapshot() is None, (balances, operations)
            assert ss.SNAPSHOT_KEY not in extensions.DASHBOARD_OLAP_CACHE
            assert fake.calls['disconnect'] == 1
        finally:
            restore()


def test_connect_failure_gives_none_without_disconnect():
    fake, restore = _install(connect_ok=False)
    try:
        assert ss.get_stock_snapshot() is None
        assert ss.SNAPSHOT_KEY not in extensions.DASHBOARD_OLAP_CACHE
        assert fake.calls['connect'] == 1
        assert fake.calls['balances'] == 0
        assert fake.calls['disconnect'] == 0       # сессии не было — закрывать нечего
        assert ss.get_stock_snapshot() is None
        assert fake.calls['connect'] == 1          # отрицательный кэш
        assert ss.get_stock_snapshot(force=True) is None
        assert fake.calls['connect'] == 2
    finally:
        restore()


def test_force_refetches_fresh_snapshot():
    fake, restore = _install()
    try:
        first = ss.get_stock_snapshot()
        assert first is not None and fake.calls['connect'] == 1
        assert ss.get_stock_snapshot() is first                # кэш
        assert fake.calls['connect'] == 1
        second = ss.get_stock_snapshot(force=True)
        assert second is not None and second is not first
        assert fake.calls['connect'] == 2
        assert ss.get_stock_snapshot() is second               # новый снимок в кэше
    finally:
        restore()


def test_success_clears_negative_cache():
    fake, restore = _install(balances=None)
    try:
        assert ss.get_stock_snapshot() is None
        fake.balances = BALANCES
        ss._last_failure_at -= ss.SNAPSHOT_FAIL_TTL + 1
        assert ss.get_stock_snapshot() is not None
        assert ss._last_failure_at is None
    finally:
        restore()


# --- disconnect при ошибке --------------------------------------------------

def test_disconnect_called_on_exception():
    fake, restore = _install(raise_on_balances=RuntimeError('iiko timeout'))
    try:
        raised = False
        try:
            ss.get_stock_snapshot()
        except RuntimeError as e:
            raised = 'iiko timeout' in str(e)
        assert raised, 'исключение iiko должно дойти до вызывающего, а не превратиться в нули'
        assert fake.calls['disconnect'] == 1
        assert ss.SNAPSHOT_KEY not in extensions.DASHBOARD_OLAP_CACHE
        # single-flight лок отпущен: следующий вызов не виснет и снова идёт в iiko
        fake.raise_on_balances = None
        assert ss.get_stock_snapshot() is not None
        assert fake.calls['disconnect'] == 2
    finally:
        restore()


def test_disconnect_called_on_none_result():
    fake, restore = _install(balances=None)
    try:
        ss.get_stock_snapshot()
        assert fake.calls['disconnect'] == fake.calls['connect'] == 1
    finally:
        restore()


# --- get_stocks_nomenclature ------------------------------------------------

def _install_nomenclature(olap_nom, xml_nom):
    orig_olap = ss.get_cached_nomenclature
    orig_xml = ss.get_xml_nomenclature
    seen = {}

    def fake_cached(olap):
        seen['olap_arg'] = olap
        return olap_nom

    ss.get_cached_nomenclature = fake_cached
    ss.get_xml_nomenclature = lambda *a, **k: xml_nom

    def restore():
        ss.get_cached_nomenclature = orig_olap
        ss.get_xml_nomenclature = orig_xml
    return seen, restore


def test_nomenclature_olap_overrides_xml_and_xml_fills_gaps():
    olap_nom = {
        'p1': {'name': 'Пиво (OLAP)', 'type': 'GOODS', 'category': None, 'mainUnit': 'л',
               'parentId': 'Напитки Разлив'},
    }
    xml_nom = {
        'p1': {'name': 'Пиво (XML)', 'type': 'GOODS', 'category': None, 'mainUnit': 'л',
               'parentId': 'Напитки Разлив', 'groupId': 'g1', 'source': 'xml'},
        'p2': {'name': 'Чипсы', 'type': 'GOODS', 'category': None, 'mainUnit': 'шт',
               'parentId': 'ЕДА', 'groupId': 'g2', 'source': 'xml'},
    }
    seen, restore = _install_nomenclature(olap_nom, xml_nom)
    try:
        merged = ss.get_stocks_nomenclature()
        assert set(merged) == {'p1', 'p2'}
        assert merged['p1'] is olap_nom['p1']                # OLAP перекрывает XML
        assert merged['p1']['name'] == 'Пиво (OLAP)'
        assert merged['p2'] is xml_nom['p2']                 # XML дополняет
        # входные словари не тронуты
        assert set(olap_nom) == {'p1'} and set(xml_nom) == {'p1', 'p2'}
        # в get_cached_nomenclature ушёл ленивый клиент с методом get_nomenclature
        assert hasattr(seen['olap_arg'], 'get_nomenclature')
    finally:
        restore()


def test_nomenclature_parent_id_normalized_from_xml():
    """OLAP или старый дисковый кэш с GUID в parentId: верхняя группа берётся из XML."""
    olap_nom = {
        'p1': {'name': 'Пиво (OLAP)', 'type': 'GOODS', 'category': 'ООО Фёст', 'mainUnit': 'л',
               'parentId': '4a5b2a76-8f86-4365-b8e6-5c9aeecd3323'},
        'p3': {'name': 'Без XML', 'type': 'GOODS', 'category': None, 'mainUnit': 'шт',
               'parentId': 'guid-without-xml'},
    }
    xml_nom = {
        'p1': {'name': 'Пиво (XML)', 'type': 'GOODS', 'category': None, 'mainUnit': 'л',
               'parentId': 'Напитки Розлив', 'groupId': 'g1', 'source': 'xml'},
        'p2': {'name': 'Чипсы', 'type': 'GOODS', 'category': None, 'mainUnit': 'шт',
               'parentId': 'ЕДА', 'groupId': 'g2', 'source': 'xml'},
    }
    _, restore = _install_nomenclature(olap_nom, xml_nom)
    try:
        merged = ss.get_stocks_nomenclature()
        assert merged['p1']['parentId'] == 'Напитки Розлив'
        assert merged['p1']['name'] == 'Пиво (OLAP)' and merged['p1']['category'] == 'ООО Фёст'
        assert olap_nom['p1']['parentId'].startswith('4a5b')          # вход не тронут
        assert merged['p3']['parentId'] == 'guid-without-xml'          # нечем заменить
        assert merged['p2']['parentId'] == 'ЕДА'
    finally:
        restore()


def test_nomenclature_xml_only_when_olap_missing():
    xml_nom = {'p2': {'name': 'Чипсы', 'type': 'GOODS', 'category': None, 'mainUnit': 'шт',
                      'parentId': 'ЕДА', 'groupId': 'g2', 'source': 'xml'}}
    _, restore = _install_nomenclature(None, xml_nom)
    try:
        assert ss.get_stocks_nomenclature() == xml_nom
    finally:
        restore()


def test_nomenclature_olap_only_when_xml_missing():
    olap_nom = {'p1': {'name': 'Пиво', 'type': 'GOODS', 'category': None, 'mainUnit': 'л',
                       'parentId': 'Напитки Разлив'}}
    _, restore = _install_nomenclature(olap_nom, {})
    try:
        assert ss.get_stocks_nomenclature() == olap_nom
    finally:
        restore()


def test_nomenclature_both_empty_gives_none():
    for olap_nom, xml_nom in ((None, None), ({}, {}), (None, {}), ({}, None)):
        _, restore = _install_nomenclature(olap_nom, xml_nom)
        try:
            assert ss.get_stocks_nomenclature() is None, (olap_nom, xml_nom)
        finally:
            restore()


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:
            failed += 1
            import traceback
            print(f'FAIL {t.__name__}: {e}')
            traceback.print_exc()
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(_run())
