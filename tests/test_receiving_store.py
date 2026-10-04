"""Тесты хранилища приёмки на РЦ (core/receiving_store.py, SQLite receiving.db). Сети нет.

База — во временной папке (set_db_path), часы подменяются через msk_time.now
(детерминированно). Разбор кодов в большинстве тестов — готовые словари того же
вида, что receiving_codes.parse_code (хранилище разбору доверяет); один тест
прогоняет настоящий parse_code.
Что проверяется:
- схема: PRAGMA user_version, WAL, foreign_keys=ON, повторное открытие, более
  новая версия схемы не ломает работу;
- приёмка: создание, формы receipt dict, подпись «кто» (display_name, login,
  « · агент» для MCP), список с фильтром и лимитом, счётчики без N+1;
- add_scan: принятие DataMatrix и EAN (каждый EAN — штука), повтор DataMatrix ->
  'repeat', отклонённый скан хранится, повтор client_id -> тот же ответ
  (replayed), в том числе после закрытия; client_id своё в каждой приёмке;
  обрезка raw/client_time, проверка source и client_id; закрытая -> ReceiptClosed;
- мягкое удаление и повторный скан той же DataMatrix, идемпотентное удаление;
- позиции приёмки (qty, kind mixed), последние сканы, ключи DataMatrix;
- закрытие, взятие обработки (claim) с окнами «зависла» и «повтор после ошибки»,
  receipts_needing_processing, finish_processing;
- фото накладных;
- строки разбора: все ветки upsert_review (вставка found/new, open -> auto,
  not_needed, повторное открытие, closed + found), reclassify_open, list_review
  (фильтры, сортировка, счётчики, q, receipt_id, total/limit), update_review,
  open_review_gtins, форма review row (barcode, supplier_hint, qty, receipts);
- кэш карточек ЧЗ;
- конкурентность: потоки и два отдельных процесса (два воркера gunicorn) на один
  файл — одна бутылка DataMatrix принимается ровно один раз; запись ждёт
  чужую транзакцию;
- битый файл БД -> ReceivingUnavailable, файл не меняется;
- грамматика Python 3.10.
"""
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['SESSION_COOKIE_SECURE'] = '0'

from core import msk_time  # noqa: E402
from core import receiving_store as rs  # noqa: E402

USER = {'login': 'ivan', 'display_name': 'Иван'}
ANNA = {'login': 'anna', 'display_name': 'Анна'}
AGENT = {'login': 'owner', 'display_name': 'Владелец', 'via_mcp': True}

RECEIPT_KEYS = {'id', 'status', 'note', 'created_at', 'created_by', 'closed_at', 'closed_by',
                'process_state', 'processed_at', 'process_note', 'notified_at', 'counts',
                'review', 'reviewed', 'reviewed_at', 'can_delete'}
COUNT_KEYS = {'units', 'gtins', 'rejected', 'repeats', 'invoices'}
SCAN_KEYS = {'id', 'gtin', 'kind', 'accepted', 'reason', 'raw_short', 'scanned_at', 'source', 'by'}
INVOICE_KEYS = {'name', 'url', 'size', 'uploaded_at', 'uploaded_by'}
ROW_KEYS = {'gtin', 'barcode', 'status', 'state', 'resolution', 'cards', 'candidates', 'chz',
            'supplier', 'supplier_hint', 'note', 'qty', 'receipts', 'first_seen_at',
            'last_seen_at', 'classified_at', 'index_built_at', 'updated_at', 'updated_by',
            'resolved_at', 'resolved_by', 'reopened'}


def _gtin(body13: str) -> str:
    """GTIN-14 с верной контрольной цифрой GS1 (веса 3,1,3,... слева)."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(body13))
    return body13 + str((10 - total % 10) % 10)


G1 = _gtin('0461009362843')    # EAN-13 с ведущим нулём -> штрихкод для iiko 13 цифр
G2 = _gtin('0460000000001')
G3 = _gtin('0000004600123')    # EAN-8 -> штрихкод для iiko 8 цифр
G4 = _gtin('1461009362843')    # GTIN-14 без ведущего нуля
G5 = _gtin('0461111111111')


def _dm(gtin, serial):
    """Словарь разбора принятой DataMatrix (форма receiving_codes.parse_code)."""
    code = '01' + gtin + '21' + serial
    return {'ok': True, 'kind': 'datamatrix', 'gtin': gtin, 'serial': serial,
            'key': gtin + '|' + serial, 'code': code, 'reason': '', 'message': 'Принято'}


def _ean(gtin):
    return {'ok': True, 'kind': 'ean', 'gtin': gtin, 'serial': None, 'key': gtin,
            'code': gtin, 'reason': '', 'message': 'Принято'}


def _bad(reason='unsupported', kind='unknown', code='https://example.org/qr'):
    return {'ok': False, 'kind': kind, 'gtin': None, 'serial': None, 'key': code[:200],
            'code': code, 'reason': reason, 'message': 'Код не распознан — повторите'}


class Clock:
    """Подменяемые часы (aware МСК)."""

    def __init__(self):
        self.value = datetime(2026, 10, 3, 14, 5, 0, tzinfo=msk_time.MOSCOW_TZ)

    def __call__(self):
        return self.value

    def move(self, **delta):
        self.value = self.value + timedelta(**delta)

    def iso(self):
        return self.value.isoformat(timespec='seconds')


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / 'receiving.db')
    rs.set_db_path(path)
    try:
        yield path
    finally:
        rs.set_db_path(None)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(msk_time, 'now', c)
    return c


_seq = [0]


def _cid():
    _seq[0] += 1
    return 'cid-%06d' % _seq[0]


def _scan(rid, parsed, raw=None, client_id=None, source='scanner', user=USER):
    return rs.add_scan(rid, parsed, raw if raw is not None else parsed['code'],
                       client_id or _cid(), source, '2026-10-03T14:05:00+03:00', user)


def _closed_receipt_with(scans, user=USER):
    """Приёмка с принятыми сканами [(parsed), ...], закрытая. -> id."""
    rid = rs.create_receipt(user)['id']
    for parsed in scans:
        _scan(rid, parsed)
    rs.close_receipt(rid, user)
    return rid


def _card(cid, name, supplier='', **extra):
    out = {'id': cid, 'name': name, 'num': 'A-' + cid, 'group': 'Пиво / Бутылка',
           'supplier': supplier, 'unit': 'шт', 'deleted': False, 'archived': False, 'keg': False}
    out.update(extra)
    return out


CHZ = {'name': 'Пиво Жигулёвское светлое', 'brand': 'Жигули', 'full_name': 'Пиво светлое 0,5',
       'product_group': 'beer', 'volume': '500 мл', 'package_type': 'UNIT', 'source': 'cache',
       'fetched_at': '2026-10-01T10:00:00+03:00'}


# ------------------------------------------------------------------ схема

def test_schema_version_pragmas_and_foreign_keys(db, clock):
    rs.create_receipt(USER)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == rs.SCHEMA_VERSION == 3
        assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {'receipts', 'receipt_scans', 'receipt_invoices', 'review_items',
                'chz_products', 'receipt_deletions'} <= tables
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert {'ux_scans_client', 'ux_scans_dm', 'ix_scans_receipt', 'ix_review_state'} <= indexes
    finally:
        conn.close()
    with rs._write() as conn:
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO receipt_scans (receipt_id, client_id, raw, kind, accepted,"
                         " scanned_at) VALUES (999, 'x', 'x', 'ean', 1, 'now')")


def test_schema_reopen_keeps_data(db, clock):
    rid = rs.create_receipt(USER, note='Первая')['id']
    rs.set_db_path(db)          # сбрасывает «схема готова» — DDL выполнится ещё раз
    assert rs.get_receipt(rid)['note'] == 'Первая'
    assert [r['id'] for r in rs.list_receipts()] == [rid]


def test_newer_schema_version_is_tolerated(db, clock):
    rid = rs.create_receipt(USER)['id']
    conn = sqlite3.connect(db)
    conn.execute('PRAGMA user_version = 7')
    conn.commit()
    conn.close()
    rs.set_db_path(db)
    _scan(rid, _ean(G1))
    assert rs.get_receipt(rid)['counts']['units'] == 1
    conn = sqlite3.connect(db)
    try:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 7   # не понижаем
    finally:
        conn.close()


# ------------------------------------------------------------------ приёмки

def test_create_and_get_receipt_shape(db, clock):
    r = rs.create_receipt(USER, note='  Машина Балтики  ')
    assert set(r) == RECEIPT_KEYS
    assert set(r['counts']) == COUNT_KEYS
    assert r['status'] == 'open'
    assert r['note'] == 'Машина Балтики'
    assert r['created_at'] == '2026-10-03T14:05:00+03:00'
    assert r['created_by'] == 'Иван'
    assert r['closed_at'] is None and r['closed_by'] == ''
    assert r['process_state'] == 'none' and r['processed_at'] is None and r['process_note'] == ''
    assert r['counts'] == {'units': 0, 'gtins': 0, 'rejected': 0, 'repeats': 0, 'invoices': 0}
    assert rs.get_receipt(r['id']) == r
    assert rs.get_receipt(str(r['id'])) == r


def test_receipt_author_variants(db, clock):
    assert rs.create_receipt({'login': 'petr'})['created_by'] == 'petr'
    assert rs.create_receipt(AGENT)['created_by'] == 'Владелец · агент'
    assert rs.create_receipt({'login': 'bot', 'via_mcp': True})['created_by'] == 'bot · агент'
    assert rs.create_receipt(None)['created_by'] == ''
    long_note = 'н' * (rs.NOTE_LIMIT + 50)
    assert len(rs.create_receipt(USER, note=long_note)['note']) == rs.NOTE_LIMIT


def test_get_receipt_not_found(db, clock):
    with pytest.raises(rs.ReceiptNotFound):
        rs.get_receipt(42)
    with pytest.raises(rs.ReceiptNotFound):
        rs.get_receipt('abc')
    with pytest.raises(rs.ReceiptNotFound):
        rs.get_receipt(None)


def test_list_receipts_filters_order_and_counts(db, clock):
    a = rs.create_receipt(USER)['id']
    clock.move(minutes=1)
    b = rs.create_receipt(USER)['id']
    clock.move(minutes=1)
    c = rs.create_receipt(USER)['id']
    _scan(a, _dm(G1, 'AAA'))
    _scan(a, _dm(G1, 'BBB'))
    _scan(a, _ean(G2))
    _scan(a, _bad())
    _scan(c, _ean(G3))
    rs.add_invoice(c, 'r3_20261003T140500_0123abcd.jpg', 1000, USER)
    rs.close_receipt(b, USER)
    assert [r['id'] for r in rs.list_receipts()] == [c, b, a]
    assert [r['id'] for r in rs.list_receipts('all')] == [c, b, a]
    assert [r['id'] for r in rs.list_receipts('open')] == [c, a]
    assert [r['id'] for r in rs.list_receipts('closed')] == [b]
    assert [r['id'] for r in rs.list_receipts(limit=2)] == [c, b]
    assert len(rs.list_receipts(limit=0)) == 1          # limit приводится к 1..LIST_LIMIT_MAX
    assert len(rs.list_receipts(limit='мусор')) == 3
    by_id = {r['id']: r['counts'] for r in rs.list_receipts()}
    assert by_id[a] == {'units': 3, 'gtins': 2, 'rejected': 1, 'repeats': 0, 'invoices': 0}
    assert by_id[b] == {'units': 0, 'gtins': 0, 'rejected': 0, 'repeats': 0, 'invoices': 0}
    assert by_id[c] == {'units': 1, 'gtins': 1, 'rejected': 0, 'repeats': 0, 'invoices': 1}
    with pytest.raises(ValueError):
        rs.list_receipts('pending')


# ------------------------------------------------------------------ сканы

def test_add_scan_datamatrix_accepted_then_repeat(db, clock):
    rid = rs.create_receipt(USER)['id']
    first = _scan(rid, _dm(G1, 'SER1'), raw='01' + G1 + '21SER1\x1d93abcd')
    assert set(first) == {'result', 'scan', 'replayed', 'counts'}
    assert first['result'] == 'accepted' and first['replayed'] is False
    scan = first['scan']
    assert set(scan) == SCAN_KEYS
    assert scan['gtin'] == G1 and scan['kind'] == 'datamatrix' and scan['accepted'] is True
    assert scan['reason'] == '' and scan['source'] == 'scanner' and scan['by'] == 'Иван'
    assert scan['scanned_at'] == clock.iso()
    assert scan['raw_short'] == '01' + G1 + '21SER1 93abcd'       # GS -> пробел
    assert first['counts'] == {'units': 1, 'gtins': 1, 'rejected': 0, 'repeats': 0, 'invoices': 0}

    again = _scan(rid, _dm(G1, 'SER1'), source='camera')
    assert again['result'] == 'repeat' and again['replayed'] is False
    assert again['scan']['accepted'] is False and again['scan']['reason'] == 'repeat'
    assert again['scan']['source'] == 'camera'
    assert again['counts'] == {'units': 1, 'gtins': 1, 'rejected': 0, 'repeats': 1, 'invoices': 0}
    assert rs.dm_keys(rid) == [G1 + '|SER1']

    other = _scan(rid, _dm(G1, 'SER2'))
    assert other['result'] == 'accepted'
    assert other['counts']['units'] == 2 and other['counts']['gtins'] == 1
    assert rs.dm_keys(rid) == [G1 + '|SER1', G1 + '|SER2']


def test_add_scan_ean_counts_each(db, clock):
    rid = rs.create_receipt(USER)['id']
    for _ in range(3):
        res = _scan(rid, _ean(G2))
        assert res['result'] == 'accepted'
    assert res['counts'] == {'units': 3, 'gtins': 1, 'rejected': 0, 'repeats': 0, 'invoices': 0}
    assert rs.receipt_lines(rid) == [{'gtin': G2, 'qty': 3, 'kind': 'ean'}]
    assert rs.dm_keys(rid) == []


def test_add_scan_rejected_is_stored(db, clock):
    rid = rs.create_receipt(USER)['id']
    res = _scan(rid, _bad('sscc', 'sscc', '00' + '4' * 18), source='manual')
    assert res['result'] == 'rejected'
    assert res['scan']['accepted'] is False and res['scan']['reason'] == 'sscc'
    assert res['scan']['kind'] == 'sscc' and res['scan']['gtin'] is None
    assert res['counts'] == {'units': 0, 'gtins': 0, 'rejected': 1, 'repeats': 0, 'invoices': 0}
    bad_check = _scan(rid, {'ok': False, 'kind': 'ean', 'gtin': None, 'serial': None,
                            'key': '4600000000001', 'code': '4600000000001',
                            'reason': 'bad_check_digit', 'message': ''})
    assert bad_check['scan']['reason'] == 'bad_check_digit'
    no_reason = _scan(rid, {'ok': False, 'kind': 'unknown', 'key': 'x', 'code': 'x'})
    assert no_reason['scan']['reason'] == 'unsupported'    # пустая причина -> unsupported
    assert rs.receipt_lines(rid) == []
    recent = rs.recent_scans(rid)
    assert [s['reason'] for s in recent] == ['unsupported', 'bad_check_digit', 'sscc']
    assert rs.get_receipt(rid)['counts']['rejected'] == 3


def test_add_scan_replay_by_client_id(db, clock):
    rid = rs.create_receipt(USER)['id']
    first = _scan(rid, _dm(G1, 'R1'), client_id='client-aaaa-1')
    clock.move(seconds=30)
    # Повтор запроса из очереди браузера: другой сырой код уже не важен — ответ тот же.
    replay = _scan(rid, _ean(G2), client_id='client-aaaa-1')
    assert replay['replayed'] is True and replay['result'] == 'accepted'
    assert replay['scan'] == first['scan']
    assert replay['counts']['units'] == 1

    rep = _scan(rid, _dm(G1, 'R1'), client_id='client-aaaa-2')
    assert rep['result'] == 'repeat'
    rep_again = _scan(rid, _dm(G1, 'R1'), client_id='client-aaaa-2')
    assert rep_again['result'] == 'repeat' and rep_again['replayed'] is True

    rej = _scan(rid, _bad(), client_id='client-aaaa-3')
    rej_again = _scan(rid, _bad(), client_id='client-aaaa-3')
    assert rej['result'] == rej_again['result'] == 'rejected' and rej_again['replayed'] is True

    with rs._read() as conn:
        assert conn.execute('SELECT COUNT(*) FROM receipt_scans').fetchone()[0] == 3

    # После закрытия повтор уже записанного скана — тот же ответ, а не «закрыта».
    rs.close_receipt(rid, USER)
    late = _scan(rid, _dm(G1, 'R1'), client_id='client-aaaa-1')
    assert late['replayed'] is True and late['result'] == 'accepted'
    with pytest.raises(rs.ReceiptClosed):
        _scan(rid, _dm(G1, 'R9'), client_id='client-aaaa-9')


def test_client_id_is_scoped_per_receipt(db, clock):
    a = rs.create_receipt(USER)['id']
    b = rs.create_receipt(USER)['id']
    ra = _scan(a, _dm(G1, 'X'), client_id='same-client-id')
    rb = _scan(b, _dm(G1, 'X'), client_id='same-client-id')
    assert ra['replayed'] is False and rb['replayed'] is False
    assert ra['result'] == rb['result'] == 'accepted'   # та же бутылка в другой приёмке — своя
    assert rs.get_receipt(a)['counts']['units'] == rs.get_receipt(b)['counts']['units'] == 1


def test_add_scan_validation_and_truncation(db, clock):
    rid = rs.create_receipt(USER)['id']
    with pytest.raises(ValueError):
        rs.add_scan(rid, _ean(G1), G1, 'cid-x', 'telepathy', '', USER)
    with pytest.raises(ValueError):
        rs.add_scan(rid, _ean(G1), G1, '   ', 'scanner', '', USER)
    with pytest.raises(ValueError):
        rs.add_scan(rid, _ean(G1), G1, 'c' * (rs.CLIENT_ID_LIMIT + 1), 'scanner', '', USER)
    res = rs.add_scan(rid, _bad('too_long'), 'Z' * 2000, 'cid-long', None, 'T' * 100, None)
    assert res['scan']['source'] == 'scanner'          # source не передан -> scanner
    assert res['scan']['by'] == ''
    assert len(res['scan']['raw_short']) == rs.RAW_SHORT_LEN
    with rs._read() as conn:
        row = conn.execute("SELECT raw, client_time FROM receipt_scans WHERE client_id = 'cid-long'"
                           ).fetchone()
    assert len(row['raw']) == rs.MAX_RAW
    assert len(row['client_time']) == rs.CLIENT_TIME_LIMIT
    with pytest.raises(rs.ReceiptNotFound):
        rs.add_scan(999, _ean(G1), G1, 'cid-404', 'scanner', '', USER)


def test_soft_delete_then_rescan_same_datamatrix(db, clock):
    rid = rs.create_receipt(USER)['id']
    first = _scan(rid, _dm(G1, 'DEL'))
    _scan(rid, _ean(G2))
    res = rs.delete_scan(rid, first['scan']['id'], ANNA)
    assert set(res) == {'scan', 'counts'}
    assert res['counts'] == {'units': 1, 'gtins': 1, 'rejected': 0, 'repeats': 0, 'invoices': 0}
    assert rs.dm_keys(rid) == []
    assert all(s['id'] != first['scan']['id'] for s in rs.recent_scans(rid))
    with rs._read() as conn:
        row = conn.execute('SELECT deleted_at, deleted_by_name FROM receipt_scans WHERE id = ?',
                           (first['scan']['id'],)).fetchone()
    assert row['deleted_at'] == clock.iso() and row['deleted_by_name'] == 'Анна'

    again = _scan(rid, _dm(G1, 'DEL'))
    assert again['result'] == 'accepted' and again['replayed'] is False
    assert rs.dm_keys(rid) == [G1 + '|DEL']
    assert again['counts']['units'] == 2

    # Повторное удаление — тот же ответ, метка удаления не переписывается.
    clock.move(minutes=5)
    twice = rs.delete_scan(rid, first['scan']['id'], USER)
    assert twice['counts'] == again['counts']
    with rs._read() as conn:
        row = conn.execute('SELECT deleted_at, deleted_by_name FROM receipt_scans WHERE id = ?',
                           (first['scan']['id'],)).fetchone()
    assert row['deleted_by_name'] == 'Анна'

    other = rs.create_receipt(USER)['id']
    foreign = _scan(other, _ean(G3))
    with pytest.raises(rs.ScanNotFound):
        rs.delete_scan(rid, foreign['scan']['id'], USER)     # скан другой приёмки
    with pytest.raises(rs.ScanNotFound):
        rs.delete_scan(rid, 99999, USER)
    with pytest.raises(rs.ScanNotFound):
        rs.delete_scan(rid, 'abc', USER)
    with pytest.raises(rs.ReceiptNotFound):
        rs.delete_scan(9999, first['scan']['id'], USER)


def test_closed_receipt_rejects_changes(db, clock):
    rid = rs.create_receipt(USER)['id']
    res = _scan(rid, _ean(G1))
    rs.close_receipt(rid, USER)
    with pytest.raises(rs.ReceiptClosed):
        _scan(rid, _ean(G1))
    with pytest.raises(rs.ReceiptClosed):
        rs.delete_scan(rid, res['scan']['id'], USER)
    assert rs.get_receipt(rid)['counts']['units'] == 1


def test_receipt_lines_kinds_and_order(db, clock):
    rid = rs.create_receipt(USER)['id']
    _scan(rid, _ean(G1))
    _scan(rid, _dm(G1, 'M1'))               # G1: и EAN, и DataMatrix -> mixed
    for serial in ('A', 'B', 'C'):
        _scan(rid, _dm(G2, serial))
    _scan(rid, _ean(G3))
    _scan(rid, _ean(G4))
    _scan(rid, _bad())
    dropped = _scan(rid, _ean(G5))
    rs.delete_scan(rid, dropped['scan']['id'], USER)
    assert rs.receipt_lines(rid) == [
        {'gtin': G2, 'qty': 3, 'kind': 'datamatrix'},
        {'gtin': G1, 'qty': 2, 'kind': 'mixed'},
        {'gtin': G3, 'qty': 1, 'kind': 'ean'},
        {'gtin': G4, 'qty': 1, 'kind': 'ean'},
    ]
    with pytest.raises(rs.ReceiptNotFound):
        rs.receipt_lines(404)


def test_recent_scans_order_limit_and_raw_short(db, clock):
    rid = rs.create_receipt(USER)['id']
    ids = [_scan(rid, _ean(G1))['scan']['id'] for _ in range(5)]
    rs.delete_scan(rid, ids[-1], USER)
    rep = _scan(rid, _dm(G2, 'Q'))
    _scan(rid, _dm(G2, 'Q'))
    recent = rs.recent_scans(rid, limit=3)
    assert len(recent) == 3
    assert recent[1]['id'] == rep['scan']['id']
    assert recent[0]['reason'] == 'repeat'          # повторы видны в истории
    assert [s['id'] for s in rs.recent_scans(rid)][2:] == ids[3::-1]
    long_raw = '01' + G1 + '21' + 'S\x1d' * 40
    res = _scan(rid, _ean(G1), raw=long_raw)
    assert res['scan']['raw_short'] == long_raw[:60].replace('\x1d', ' ')
    with pytest.raises(rs.ReceiptNotFound):
        rs.recent_scans(404)
    with pytest.raises(rs.ReceiptNotFound):
        rs.dm_keys(404)


# ------------------------------------------------------------------ закрытие и обработка

def test_close_receipt(db, clock):
    rid = rs.create_receipt(USER)['id']
    _scan(rid, _ean(G1))
    clock.move(minutes=20)
    receipt, changed = rs.close_receipt(rid, AGENT)
    assert changed is True
    assert receipt['status'] == 'closed' and receipt['process_state'] == 'pending'
    assert receipt['closed_at'] == clock.iso() and receipt['closed_by'] == 'Владелец · агент'
    clock.move(minutes=1)
    again, changed = rs.close_receipt(rid, USER)
    assert changed is False and again == receipt
    with pytest.raises(rs.ReceiptNotFound):
        rs.close_receipt(404, USER)


def test_claim_finish_and_retry_windows(db, clock):
    open_id = rs.create_receipt(USER)['id']
    rid = rs.create_receipt(USER)['id']
    assert rs.receipts_needing_processing() == []
    assert rs.claim_processing(open_id) is False        # открытую не обрабатываем
    rs.close_receipt(rid, USER)
    assert rs.receipts_needing_processing() == [rid]

    assert rs.claim_processing(rid) is True
    assert rs.get_receipt(rid)['process_state'] == 'running'
    assert rs.claim_processing(rid) is False            # второй воркер не берёт
    assert rs.receipts_needing_processing() == []

    clock.move(seconds=rs.PROCESS_STALE_SEC - 1)
    assert rs.claim_processing(rid) is False            # ещё не «зависла»
    clock.move(seconds=1)
    assert rs.receipts_needing_processing() == [rid]
    assert rs.claim_processing(rid) is True             # воркер умер — перехватили
    assert rs.claim_processing(rid) is False

    clock.move(minutes=2)
    rs.finish_processing(rid, 'error', 'Нет индекса iiko: нет связи')
    r = rs.get_receipt(rid)
    assert r['process_state'] == 'error' and r['processed_at'] == clock.iso()
    assert r['process_note'] == 'Нет индекса iiko: нет связи'
    assert rs.receipts_needing_processing() == []
    clock.move(seconds=rs.PROCESS_RETRY_SEC - 1)
    assert rs.claim_processing(rid) is False            # повтор не чаще раза в час
    assert rs.receipts_needing_processing() == []
    clock.move(seconds=1)
    assert rs.receipts_needing_processing() == [rid]
    assert rs.claim_processing(rid) is True

    rs.finish_processing(rid, 'done', 'н' * (rs.PROCESS_NOTE_LIMIT + 10))
    r = rs.get_receipt(rid)
    assert r['process_state'] == 'done' and len(r['process_note']) == rs.PROCESS_NOTE_LIMIT
    clock.move(days=30)
    assert rs.claim_processing(rid) is False            # готовую не трогаем никогда
    assert rs.receipts_needing_processing() == []

    with pytest.raises(ValueError):
        rs.finish_processing(rid, 'running')
    with pytest.raises(rs.ReceiptNotFound):
        rs.finish_processing(404, 'done')
    assert rs.claim_processing(404) is False


def test_claim_error_at_once_when_asked(db, clock):
    rid = _closed_receipt_with([_ean(G1)])
    assert rs.claim_processing(rid) is True
    rs.finish_processing(rid, 'error', 'сбой')
    clock.move(seconds=1)
    assert rs.claim_processing(rid) is False                       # шедулер ждёт час
    assert rs.claim_processing(rid, retry_error_now=True) is True  # «Завершить» ещё раз
    assert rs.claim_processing(rid, retry_error_now=True) is False # уже running
    rs.finish_processing(rid, 'done')
    assert rs.claim_processing(rid, retry_error_now=True) is False # done не перезапускаем


def test_receipts_needing_processing_lists_several(db, clock):
    a = _closed_receipt_with([_ean(G1)])
    b = _closed_receipt_with([_ean(G2)])
    c = _closed_receipt_with([_ean(G3)])
    assert rs.claim_processing(b) is True
    rs.finish_processing(b, 'done')
    assert rs.receipts_needing_processing() == [a, c]


def test_naive_clock_is_treated_as_msk(db, monkeypatch):
    monkeypatch.setattr(msk_time, 'now', lambda: datetime(2026, 10, 3, 9, 0, 0))
    assert rs.create_receipt(USER)['created_at'] == '2026-10-03T09:00:00+03:00'


# ------------------------------------------------------------------ фото накладных

def test_invoices(db, clock):
    rid = rs.create_receipt(USER)['id']
    name1 = 'r%d_20261003T140500_0a1b2c3d.jpg' % rid
    name2 = 'r%d_20261003T140600_ffeeddcc.jpg' % rid
    inv = rs.add_invoice(rid, name1, 123456, USER)
    assert set(inv) == INVOICE_KEYS
    assert inv == {'name': name1, 'url': '/api/receiving/invoice/' + name1, 'size': 123456,
                   'uploaded_at': clock.iso(), 'uploaded_by': 'Иван'}
    rs.close_receipt(rid, USER)
    clock.move(minutes=1)
    rs.add_invoice(rid, name2, 10, ANNA)                 # после закрытия — можно
    assert [i['name'] for i in rs.list_invoices(rid)] == [name1, name2]
    assert rs.get_receipt(rid)['counts']['invoices'] == 2
    with pytest.raises(ValueError):
        rs.add_invoice(rid, name1, 1, USER)              # имя уникально
    with pytest.raises(ValueError):
        rs.add_invoice(rid, '  ', 1, USER)
    assert rs.delete_invoice(rid, name1) is True
    assert rs.delete_invoice(rid, name1) is False
    other = rs.create_receipt(USER)['id']
    assert rs.delete_invoice(other, name2) is False      # чужая приёмка
    assert [i['name'] for i in rs.list_invoices(rid)] == [name2]
    with pytest.raises(rs.ReceiptNotFound):
        rs.add_invoice(404, 'r404_20261003T140500_0a1b2c3d.jpg', 1, USER)
    with pytest.raises(rs.ReceiptNotFound):
        rs.list_invoices(404)


# ------------------------------------------------------------------ строки разбора

def test_upsert_review_insert_new_and_found(db, clock):
    rid = _closed_receipt_with([_ean(G1), _ean(G1), _ean(G2)])
    cands = [dict(_card('c1', 'Жигули Барное'), score=2)]
    res = rs.upsert_review(G1, rid, 'similar', [], cands, CHZ, '2026-10-03T07:30:05+03:00')
    assert res['opened'] is True and res['reopened'] is False
    row = res['row']
    assert set(row) == ROW_KEYS
    assert row['state'] == 'open' and row['resolution'] == '' and row['status'] == 'similar'
    assert row['barcode'] == G1[1:]                      # EAN-13 для iiko
    assert row['candidates'] == cands and row['cards'] == []
    assert row['chz'] == {k: CHZ.get(k, '') for k in rs.CHZ_FIELDS}     # без fetched_at
    assert row['qty'] == 2 and row['receipts'] == [{'id': rid, 'qty': 2, 'closed_at': clock.iso()}]
    assert row['first_seen_at'] == row['last_seen_at'] == row['classified_at'] == clock.iso()
    assert row['index_built_at'] == '2026-10-03T07:30:05+03:00'
    assert row['updated_by'] == '' and row['resolved_at'] is None and row['resolved_by'] == ''
    assert row['supplier'] == '' and row['supplier_hint'] == '' and row['note'] == ''
    assert row['reopened'] == 0

    found = rs.upsert_review(G2, rid, 'found', [_card('k2', 'Балтика 7', supplier='Балтика')],
                             [], {}, '2026-10-03T07:30:05+03:00')
    assert found['opened'] is False and found['reopened'] is False
    assert found['row']['state'] == 'closed' and found['row']['resolution'] == 'found'
    assert found['row']['resolved_by'] == 'индекс iiko' and found['row']['resolved_at'] == clock.iso()
    assert found['row']['supplier_hint'] == 'Балтика' and found['row']['chz'] == {}


def test_upsert_review_existing_open_updates_fields(db, clock):
    r1 = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, r1, 'new', [], [], CHZ, 'idx-1')
    rs.update_review(G1, ANNA, supplier='Балтика', note='звонила')
    clock.move(hours=2)
    r2 = _closed_receipt_with([_ean(G1), _ean(G1)])
    cands = [dict(_card('c9', 'Жигули'), score=3)]
    res = rs.upsert_review(G1, r2, 'similar', [], cands, {}, 'idx-2')
    assert res['opened'] is False and res['reopened'] is False
    row = res['row']
    assert row['state'] == 'open' and row['status'] == 'similar'
    assert row['candidates'] == cands
    assert row['chz']['name'] == CHZ['name']             # пустой chz не затирает прежний
    assert row['supplier'] == 'Балтика' and row['note'] == 'звонила'   # не трогаем
    assert row['last_seen_at'] == row['classified_at'] == clock.iso()
    assert row['first_seen_at'] != row['last_seen_at']
    assert row['index_built_at'] == 'idx-2'
    assert row['qty'] == 3 and [r['id'] for r in row['receipts']] == [r2, r1]
    assert row['updated_by'] == 'Анна'                   # системное обновление — не правка человека

    fresh = dict(CHZ, name='Жигулёвское новое', source='product_info')
    row = rs.upsert_review(G1, r2, 'new', [], [], fresh, 'idx-3')['row']
    assert row['chz']['name'] == 'Жигулёвское новое' and row['chz']['source'] == 'product_info'
    # Одна пометка source без текста — «пусто», прежние данные остаются.
    row = rs.upsert_review(G1, r2, 'new', [], [], {'source': 'cache'}, 'idx-4')['row']
    assert row['chz']['name'] == 'Жигулёвское новое'
    with rs._read() as conn:
        rec = conn.execute('SELECT first_receipt_id, last_receipt_id FROM review_items WHERE gtin = ?',
                           (G1,)).fetchone()
    assert (rec['first_receipt_id'], rec['last_receipt_id']) == (r1, r2)


def test_upsert_review_open_found_auto_closes(db, clock):
    rid = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, rid, 'new', [], [], CHZ, 'idx-1')
    clock.move(hours=1)
    res = rs.upsert_review(G1, rid, 'found', [_card('k1', 'Жигули', supplier='МаркетБир')], [], {},
                           'idx-2')
    assert res['opened'] is False and res['reopened'] is False
    row = res['row']
    assert row['state'] == 'closed' and row['resolution'] == 'auto'
    assert row['resolved_by'] == 'индекс iiko' and row['resolved_at'] == clock.iso()
    assert row['status'] == 'found' and row['supplier_hint'] == 'МаркетБир'


def test_upsert_review_not_needed_stays_closed(db, clock):
    rid = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, rid, 'new', [], [], CHZ, 'idx-1')
    rs.update_review(G1, ANNA, state='not_needed')
    for status in ('new', 'restore', 'found'):
        res = rs.upsert_review(G1, rid, status, [], [], {}, 'idx-2')
        assert res['opened'] is False and res['reopened'] is False
        assert res['row']['state'] == 'closed' and res['row']['resolution'] == 'not_needed'
        assert res['row']['status'] == status
        assert res['row']['resolved_by'] == 'Анна'


@pytest.mark.parametrize('how', ['found', 'auto', 'done'])
def test_upsert_review_reopens_closed(db, clock, how):
    rid = _closed_receipt_with([_ean(G1)])
    if how == 'found':
        rs.upsert_review(G1, rid, 'found', [_card('k1', 'Жигули')], [], {}, 'idx-1')
    else:
        rs.upsert_review(G1, rid, 'new', [], [], CHZ, 'idx-1')
        if how == 'auto':
            rs.upsert_review(G1, rid, 'found', [_card('k1', 'Жигули')], [], {}, 'idx-1')
        else:
            rs.update_review(G1, ANNA, state='done')
    assert rs.get_review_item(G1)['resolution'] == how

    # Карточку потом удалили или заархивировали — строка снова в очереди.
    gone = [_card('k1', 'Жигули', deleted=True)]
    res = rs.upsert_review(G1, rid, 'restore', gone, [], {}, 'idx-2')
    assert res['opened'] is True and res['reopened'] is True
    row = res['row']
    assert row['state'] == 'open' and row['resolution'] == ''
    assert row['resolved_at'] is None and row['resolved_by'] == ''
    assert row['reopened'] == 1 and row['cards'] == gone

    rs.upsert_review(G1, rid, 'found', [_card('k1', 'Жигули')], [], {}, 'idx-3')   # снова auto
    res = rs.upsert_review(G1, rid, 'duplicate', [], [], {}, 'idx-4')
    assert res['reopened'] is True and res['row']['reopened'] == 2


def test_upsert_review_closed_stays_closed_when_found(db, clock):
    rid = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, rid, 'new', [], [], CHZ, 'idx-1')
    rs.update_review(G1, ANNA, state='done')
    res = rs.upsert_review(G1, rid, 'found', [_card('k1', 'Жигули')], [], {}, 'idx-2')
    assert res['opened'] is False and res['reopened'] is False
    assert res['row']['state'] == 'closed' and res['row']['resolution'] == 'done'
    assert res['row']['status'] == 'found'


# Метки индексов в настоящем формате (ISO с +03:00): решения сравниваются с ними.
IDX_0700 = '2026-10-03T07:00:00+03:00'
IDX_0730 = '2026-10-03T07:30:00+03:00'


def test_stale_index_does_not_reopen_done_row(db, clock):
    """Ревью 2026-10-03: индекс, собранный ДО «Сделано», не видит новую карточку —
    строка не должна вернуться «Новой» (и толкнуть завести дубль в iiko)."""
    r1 = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, r1, 'new', [], [], CHZ, IDX_0700)
    clock.move(hours=1)                                   # 10:00 > 07:00 и 07:30
    rs.update_review(G1, ANNA, state='done')
    r2 = _closed_receipt_with([_ean(G1)])
    res = rs.upsert_review(G1, r2, 'new', [], [], {}, IDX_0730)   # индекс старше решения
    assert res['opened'] is False and res['reopened'] is False
    row = res['row']
    assert row['state'] == 'closed' and row['resolution'] == 'done' and row['reopened'] == 0
    assert row['index_built_at'] == IDX_0700              # статус не перезаписан устаревшим
    assert [r['id'] for r in row['receipts']] == [r2, r1]  # приёмку при этом учли
    assert rs.rows_to_notify(r2) == []
    # Индекс, собранный после решения, а GTIN всё ещё не на карточке — снова в разбор.
    later = (clock.value + timedelta(minutes=5)).isoformat(timespec='seconds')
    res = rs.upsert_review(G1, r2, 'new', [], [], {}, later)
    assert res['opened'] is True and res['row']['state'] == 'open' and res['row']['reopened'] == 1
    assert [r['gtin'] for r in rs.rows_to_notify(r2)] == [G1]


def test_older_index_does_not_overwrite_status(db, clock):
    rid = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, rid, 'similar', [], [dict(_card('c1', 'Жигули'), score=2)], CHZ, IDX_0730)
    res = rs.upsert_review(G1, rid, 'new', [], [], {}, IDX_0700)
    assert res['row']['status'] == 'similar' and res['row']['index_built_at'] == IDX_0730
    done = rs.reclassify_open(G1, 'found', [_card('k1', 'Жигули')], [], index_built_at=IDX_0700)
    assert done['auto_closed'] is False and done['row']['state'] == 'open'
    done = rs.reclassify_open(G1, 'found', [_card('k1', 'Жигули')], [], index_built_at=IDX_0730)
    assert done['auto_closed'] is True and done['row']['resolution'] == 'auto'


def test_recheck_done(db, clock):
    rid = _closed_receipt_with([_ean(G1), _ean(G2)])
    for g in (G1, G2):
        rs.upsert_review(g, rid, 'new', [], [], CHZ, IDX_0700)
        rs.update_review(g, ANNA, state='done')
    resolved = rs.get_review_item(G1)['resolved_at']
    assert rs.done_review_gtins() == sorted([G1, G2])
    # Индекс не новее решения — ничего не меняем.
    for built in (IDX_0730, resolved, ''):
        res = rs.recheck_done(G1, 'new', [], [], built)
        assert res['reopened'] is False and res['row']['state'] == 'closed'
    later = (clock.value + timedelta(minutes=1)).isoformat(timespec='seconds')
    ok = rs.recheck_done(G1, 'found', [_card('k1', 'Жигули')], [], later)
    assert ok['reopened'] is False and ok['row']['resolution'] == 'done' and ok['row']['status'] == 'found'
    bad = rs.recheck_done(G2, 'new', [], [], later)
    assert bad['reopened'] is True and bad['row']['state'] == 'open' and bad['row']['reopened'] == 1
    assert rs.done_review_gtins() == []                    # G1 подтверждён, G2 снова открыт
    assert rs.rows_to_notify(rid) == []                   # перепроверка «Сделано» не шлёт сообщение
    with pytest.raises(rs.ReviewItemNotFound):
        rs.recheck_done(G3, 'new', [], [], later)


def test_rows_to_notify_and_mark_notified(db, clock):
    rid = _closed_receipt_with([_ean(G1), _ean(G2), _ean(G3)])
    rs.upsert_review(G1, rid, 'new', [], [], CHZ, IDX_0700)
    rs.upsert_review(G2, rid, 'found', [_card('k2', 'Балтика')], [], {}, IDX_0700)
    rs.upsert_review(G3, rid, 'restore', [_card('k3', 'Старое', deleted=True)], [], {}, IDX_0700)
    assert sorted(r['gtin'] for r in rs.rows_to_notify(rid)) == sorted([G1, G3])
    rs.update_review(G3, ANNA, state='done')
    assert [r['gtin'] for r in rs.rows_to_notify(rid)] == [G1]
    assert rs.get_receipt(rid)['notified_at'] is None
    rs.mark_notified(rid)
    assert rs.get_receipt(rid)['notified_at'] == clock.iso()
    with pytest.raises(rs.ReceiptNotFound):
        rs.mark_notified(999)


def test_huge_ids_are_not_found(db, clock):
    rid = rs.create_receipt(USER)['id']
    for bad in (2 ** 63, 10 ** 20, 0, -1):
        with pytest.raises(rs.ReceiptNotFound):
            rs.get_receipt(bad)
    with pytest.raises(rs.ScanNotFound):
        rs.delete_scan(rid, 2 ** 63, USER)


def test_existing_db_gets_added_columns(tmp_path, clock):
    path = str(tmp_path / 'old.db')
    conn = sqlite3.connect(path)
    for sql in rs._SCHEMA_V1:
        conn.execute(sql.replace(',\n      notified_at TEXT', '').replace(',\n      notify_receipt_id INTEGER', ''))
    conn.execute('PRAGMA user_version = 1')
    conn.commit()
    cols = {r[1] for r in conn.execute('PRAGMA table_info(receipts)')}
    assert 'notified_at' not in cols
    conn.close()
    rs.set_db_path(path)
    try:
        rid = rs.create_receipt(USER)['id']
        assert rs.get_receipt(rid)['notified_at'] is None
        rs.mark_notified(rid)
    finally:
        rs.set_db_path(None)


def test_upsert_review_validation(db, clock):
    with pytest.raises(ValueError):
        rs.upsert_review(G1, None, 'missing', [], [], {}, '')
    with pytest.raises(ValueError):
        rs.upsert_review('4600000000001', None, 'new', [], [], {}, '')   # 13 цифр
    with pytest.raises(ValueError):
        rs.upsert_review('0460000000000A', None, 'new', [], [], {}, '')
    res = rs.upsert_review(G1, None, 'new', None, [None, 'мусор'], None, None)
    assert res['row']['cards'] == [] and res['row']['candidates'] == []
    assert res['row']['receipts'] == [] and res['row']['qty'] == 0


def test_reclassify_open(db, clock):
    rid = _closed_receipt_with([_ean(G1), _ean(G2)])
    rs.upsert_review(G1, rid, 'new', [], [], {}, 'idx-1')
    rs.upsert_review(G2, rid, 'new', [], [], CHZ, 'idx-1')
    clock.move(hours=3)
    cands = [dict(_card('c1', 'Жигули'), score=2)]
    res = rs.reclassify_open(G1, 'similar', [], cands, CHZ, 'idx-2')
    assert res['auto_closed'] is False
    row = res['row']
    assert row['status'] == 'similar' and row['state'] == 'open' and row['candidates'] == cands
    assert row['chz']['name'] == CHZ['name'] and row['index_built_at'] == 'idx-2'
    assert row['classified_at'] == clock.iso()
    assert row['last_seen_at'] != clock.iso()            # в приёмке её не видели
    # index_built_at не передан — прежний остаётся.
    assert rs.reclassify_open(G1, 'new', [], [], None)['row']['index_built_at'] == 'idx-2'

    res = rs.reclassify_open(G2, 'found', [_card('k2', 'Балтика')], [], None, 'idx-3')
    assert res['auto_closed'] is True
    assert res['row']['state'] == 'closed' and res['row']['resolution'] == 'auto'
    assert res['row']['resolved_by'] == 'индекс iiko'

    # Закрытую не трогаем.
    res = rs.reclassify_open(G2, 'restore', [], [], None, 'idx-4')
    assert res['auto_closed'] is False and res['row']['status'] == 'found'
    assert res['row']['index_built_at'] == 'idx-3'
    with pytest.raises(rs.ReviewItemNotFound):
        rs.reclassify_open(G5, 'new', [], [], None)
    with pytest.raises(ValueError):
        rs.reclassify_open(G1, 'missing', [], [], None)


def _review_fixture(clock):
    """Набор строк разбора разных статусов/состояний. -> (r1, r2)."""
    r1 = _closed_receipt_with([_ean(G1), _ean(G2), _ean(G2), _ean(G3)])
    rs.upsert_review(G1, r1, 'duplicate', [_card('d1', 'Охота крепкое'), _card('d2', 'Охота')],
                     [], {}, 'idx')
    clock.move(minutes=1)
    rs.upsert_review(G2, r1, 'new', [], [], dict(CHZ, name='Пиво Ёршик светлое', brand='Ёрш'),
                     'idx')
    clock.move(minutes=1)
    rs.upsert_review(G3, r1, 'found', [_card('f3', 'Балтика 0', supplier='Балтика')], [], {}, 'idx')
    clock.move(minutes=1)
    r2 = _closed_receipt_with([_ean(G4), _dm(G5, 'S1'), _ean(G1)])
    rs.upsert_review(G4, r2, 'restore', [_card('r4', 'Козел тёмное', deleted=True)], [], {}, 'idx')
    clock.move(minutes=1)
    rs.upsert_review(G5, r2, 'similar', [], [dict(_card('c5', 'Хамовники Венское'), score=2)],
                     dict(CHZ, name='Хамовники Венское', brand='Хамовники'), 'idx')
    clock.move(minutes=1)
    rs.upsert_review(G1, r2, 'duplicate', [_card('d1', 'Охота крепкое'), _card('d2', 'Охота')],
                     [], {}, 'idx')     # G1 позже увиден снова — last_seen свежее
    return r1, r2


def test_list_review_filters_sort_and_counts(db, clock):
    r1, r2 = _review_fixture(clock)
    res = rs.list_review()
    assert set(res) == {'rows', 'total', 'counts'}
    assert [r['gtin'] for r in res['rows']] == [G2, G5, G4, G1]
    assert all(set(r) == ROW_KEYS for r in res['rows'])
    assert res['total'] == 4
    assert res['counts'] == {'open': {'new': 1, 'similar': 1, 'restore': 1, 'duplicate': 1},
                             'open_total': 4, 'closed_total': 1}
    assert [r['gtin'] for r in rs.list_review(state='closed')['rows']] == [G3]
    assert [r['gtin'] for r in rs.list_review(state='all')['rows']] == [G2, G5, G4, G1, G3]
    assert [r['gtin'] for r in rs.list_review(statuses=['restore', 'new'])['rows']] == [G2, G4]
    assert [r['gtin'] for r in rs.list_review(statuses='similar,duplicate')['rows']] == [G5, G1]
    assert rs.list_review(statuses=[])['total'] == 4
    page = rs.list_review(state='all', limit=2)
    assert [r['gtin'] for r in page['rows']] == [G2, G5] and page['total'] == 5
    assert rs.list_review(state='all', limit=0)['total'] == 5      # limit -> 1..LIST_LIMIT_MAX
    assert len(rs.list_review(state='all', limit=0)['rows']) == 1

    # Две строки одного статуса — свежие (last_seen_at) сверху.
    rs.update_review(G4, ANNA, state='open')          # ничего не меняет в порядке
    clock.move(minutes=1)
    rs.upsert_review(G3, r2, 'new', [], [], {}, 'idx')  # found/closed -> снова open как new
    assert [r['gtin'] for r in rs.list_review()['rows']][:2] == [G3, G2]

    with pytest.raises(ValueError):
        rs.list_review(state='pending')
    with pytest.raises(ValueError):
        rs.list_review(statuses=['missing'])
    with pytest.raises(ValueError):
        rs.list_review(receipt_id='abc')


def test_list_review_receipt_filter_and_qty(db, clock):
    r1, r2 = _review_fixture(clock)
    res = rs.list_review(state='all', receipt_id=r2)
    assert [r['gtin'] for r in res['rows']] == [G5, G4, G1]
    assert res['counts'] == {'open': {'new': 0, 'similar': 1, 'restore': 1, 'duplicate': 1},
                             'open_total': 3, 'closed_total': 0}
    assert rs.list_review(receipt_id=str(r1))['total'] == 2       # G1, G2 открытые; G3 закрыта
    by_gtin = {r['gtin']: r for r in rs.list_review(state='all')['rows']}
    assert by_gtin[G2]['qty'] == 2 and by_gtin[G2]['receipts'] == [
        {'id': r1, 'qty': 2, 'closed_at': rs.get_receipt(r1)['closed_at']}]
    assert by_gtin[G1]['qty'] == 2 and [x['id'] for x in by_gtin[G1]['receipts']] == [r2, r1]
    assert by_gtin[G4]['barcode'] == G4                  # GTIN-14 как есть
    assert by_gtin[G3]['barcode'] == G3[-8:]             # EAN-8

    # Открытая приёмка с тем же GTIN не входит в qty (считаются только закрытые);
    # удалённый скан не делает GTIN «этой приёмки».
    r3 = rs.create_receipt(USER)['id']
    _scan(r3, _ean(G2))
    dropped = _scan(r3, _ean(G4))
    rs.delete_scan(r3, dropped['scan']['id'], USER)
    assert rs.get_review_item(G2)['qty'] == 2
    assert [r['gtin'] for r in rs.list_review(state='all', receipt_id=r3)['rows']] == [G2]
    assert rs.list_review(receipt_id=99999)['rows'] == []


def test_list_review_search(db, clock):
    _review_fixture(clock)
    rs.update_review(G4, ANNA, supplier='МаркетБир', note='Ждём ответ поставщика')

    def gtins(q, state='all'):
        return [r['gtin'] for r in rs.list_review(state=state, q=q)['rows']]

    assert gtins(G2[-6:]) == [G2]                         # подстрока GTIN
    assert gtins(G3[-8:]) == [G3]                         # штрихкод для iiko (EAN-8)
    assert gtins('ЕРШИК') == [G2]                         # регистр и ё=е в названии ЧЗ
    assert gtins('ёрш') == [G2]                           # бренд ЧЗ
    assert gtins('Охота') == [G1]                         # имена карточек
    assert gtins('венское') == [G5]                       # кандидаты и ЧЗ
    assert gtins('маркетбир') == [G4]                     # поставщик
    assert gtins('ждём') == [G4]                          # заметка
    assert gtins('козел') == [G4]                         # имя удалённой карточки
    assert gtins('нет такого') == []
    assert gtins('  ') == [G2, G5, G4, G1, G3]            # пустой q — без фильтра
    res = rs.list_review(q='охота')
    assert res['counts']['open_total'] == 1 and res['counts']['open']['duplicate'] == 1
    assert rs.list_review(q='балтика')['rows'] == []     # найдена, но закрыта
    assert rs.list_review(q='балтика')['counts']['closed_total'] == 1


def test_update_review_states(db, clock):
    rid = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, rid, 'new', [], [], CHZ, 'idx')
    clock.move(minutes=5)
    row = rs.update_review(G1, ANNA, supplier='  Балтика  ')
    assert row['supplier'] == 'Балтика' and row['state'] == 'open'
    assert row['updated_at'] == clock.iso() and row['updated_by'] == 'Анна'
    assert rs.update_review(G1, ANNA, supplier='')['supplier'] == ''

    clock.move(minutes=5)
    row = rs.update_review(G1, AGENT, state='done', note='Завела карточку')
    assert row['state'] == 'closed' and row['resolution'] == 'done'
    assert row['resolved_at'] == clock.iso() and row['resolved_by'] == 'Владелец · агент'
    assert row['note'] == 'Завела карточку' and row['updated_by'] == 'Владелец · агент'

    row = rs.update_review(G1, ANNA, state='open')
    assert row['state'] == 'open' and row['resolution'] == ''
    assert row['resolved_at'] is None and row['resolved_by'] == ''
    assert row['reopened'] == 0                          # человек вернул — не «переоткрыто индексом»

    row = rs.update_review(G1, ANNA, state='not_needed')
    assert row['state'] == 'closed' and row['resolution'] == 'not_needed'
    assert row['resolved_by'] == 'Анна'

    row = rs.update_review(G1, ANNA, note='x' * (rs.NOTE_LIMIT + 20))
    assert len(row['note']) == rs.NOTE_LIMIT and row['state'] == 'closed'
    assert rs.update_review(G1, ANNA, note='')['note'] == ''

    with pytest.raises(ValueError):
        rs.update_review(G1, ANNA)
    with pytest.raises(ValueError):
        rs.update_review(G1, ANNA, state='closed')
    with pytest.raises(rs.ReviewItemNotFound):
        rs.update_review(G5, ANNA, note='нет строки')
    with pytest.raises(rs.ReviewItemNotFound):
        rs.get_review_item(G5)


def test_open_review_gtins(db, clock):
    _review_fixture(clock)
    assert rs.open_review_gtins() == sorted([G1, G2, G4, G5])
    rs.update_review(G2, ANNA, state='done')
    assert rs.open_review_gtins() == sorted([G1, G4, G5])


def test_review_row_survives_broken_json(db, clock):
    rid = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, rid, 'new', [], [], CHZ, 'idx')
    with rs._write() as conn:
        conn.execute("UPDATE review_items SET cards_json = '{битый', chz_json = '[1]' WHERE gtin = ?",
                     (G1,))
    row = rs.get_review_item(G1)
    assert row['cards'] == [] and row['chz'] == {} and row['supplier_hint'] == ''


# ------------------------------------------------------------------ кэш ЧЗ

def test_chz_products_cache(db, clock):
    assert rs.get_chz_products([]) == {}
    assert rs.get_chz_products([G1]) == {}
    raw = {'gtin': G1, 'name': 'Жигули', 'volumeWeight': '0,5 л'}
    rs.save_chz_products([
        {'gtin': G1, 'found': True, 'name': 'Жигули', 'brand': 'Жигули', 'full_name': 'Пиво Жигули',
         'product_group': 'beer', 'volume': '0,5 л', 'package_type': 'UNIT', 'raw': raw,
         'source': 'product_info', 'fetched_at': '2026-10-01T10:00:00+03:00'},
        {'gtin': G2, 'found': False, 'source': 'product_info'},
    ])
    got = rs.get_chz_products([G1, G2, G3, G1, '', None])
    assert set(got) == {G1, G2}
    assert got[G1] == {'gtin': G1, 'found': True, 'name': 'Жигули', 'brand': 'Жигули',
                       'full_name': 'Пиво Жигули', 'product_group': 'beer', 'volume': '0,5 л',
                       'package_type': 'UNIT', 'raw': raw, 'source': 'product_info',
                       'fetched_at': '2026-10-01T10:00:00+03:00'}
    assert got[G2]['found'] is False and got[G2]['name'] == '' and got[G2]['raw'] == {}
    assert got[G2]['fetched_at'] == clock.iso()          # нет fetched_at -> сейчас

    clock.move(days=8)
    rs.save_chz_products([{'gtin': G2, 'found': 1, 'name': 'Появилось', 'source': 'stock'}])
    again = rs.get_chz_products([G2])[G2]
    assert again['found'] is True and again['name'] == 'Появилось' and again['source'] == 'stock'
    assert again['fetched_at'] == clock.iso()
    rs.save_chz_products([])                              # пусто — ничего не делаем
    with pytest.raises(ValueError):
        rs.save_chz_products([{'gtin': G3, 'found': True}, {'found': True}])
    assert rs.get_chz_products([G3]) == {}                # транзакция не началась


def test_chz_products_many_gtins_chunked(db, clock):
    gtins = [str(i).zfill(14) for i in range(1, rs.SQL_CHUNK * 2 + 7)]
    rs.save_chz_products([{'gtin': g, 'found': False} for g in gtins])
    assert len(rs.get_chz_products(gtins)) == len(gtins)


# ------------------------------------------------------------------ конкурентность

def test_concurrent_threads_accept_datamatrix_once(db, clock):
    rid = rs.create_receipt(USER)['id']
    results, errors = [], []
    start = threading.Barrier(8)

    def worker(i):
        try:
            start.wait()
            results.append(rs.add_scan(rid, _dm(G1, 'RACE'), '01' + G1 + '21RACE',
                                       'thread-%d' % i, 'scanner', '', USER)['result'])
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert errors == []
    assert sorted(results) == ['accepted'] + ['repeat'] * 7
    assert rs.get_receipt(rid)['counts'] == {'units': 1, 'gtins': 1, 'rejected': 0, 'repeats': 7,
                                             'invoices': 0}


def test_concurrent_threads_same_client_id_one_row(db, clock):
    rid = rs.create_receipt(USER)['id']
    results, errors = [], []
    start = threading.Barrier(6)

    def worker():
        try:
            start.wait()
            results.append(rs.add_scan(rid, _ean(G2), G2, 'same-client', 'scanner', '', USER))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert errors == []
    assert sorted(r['replayed'] for r in results) == [False] + [True] * 5
    assert {r['scan']['id'] for r in results} == {results[0]['scan']['id']}
    assert rs.get_receipt(rid)['counts']['units'] == 1


_WORKER_SCRIPT = r'''
import sys, time
sys.path.insert(0, sys.argv[1])
from core import receiving_store as rs
rs.set_db_path(sys.argv[2])
rid, tag, go = int(sys.argv[3]), sys.argv[4], float(sys.argv[5])
while time.time() < go:
    time.sleep(0.005)
out = []
for i in range(25):
    gtin = sys.argv[6]
    parsed = {'ok': True, 'kind': 'datamatrix', 'gtin': gtin, 'serial': 'S%d' % i,
              'key': gtin + '|S%d' % i, 'code': '01' + gtin + '21S%d' % i, 'reason': '',
              'message': ''}
    res = rs.add_scan(rid, parsed, parsed['code'], tag + '-%d' % i, 'scanner', '', None)
    out.append(res['result'][0])
print(''.join(out))
'''


def test_two_processes_accept_each_datamatrix_once(db, clock, tmp_path):
    """Два воркера gunicorn = два процесса на один файл: каждая бутылка — ровно один раз."""
    rid = rs.create_receipt(USER)['id']
    script = tmp_path / 'worker.py'
    script.write_text(_WORKER_SCRIPT, encoding='utf-8')
    go = time.time() + 1.5          # оба процесса успевают импортироваться и стартуют вместе
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    procs = [subprocess.Popen([sys.executable, str(script), ROOT, db, str(rid), tag, str(go), G1],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
             for tag in ('w1', 'w2')]
    outs = []
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err.decode('utf-8', 'replace')
        outs.append(out.decode().strip())
    # Каждая из 25 бутылок принята ровно одним процессом, второй получил «повтор».
    for i in range(25):
        assert sorted(o[i] for o in outs) == ['a', 'r'], (i, outs)
    counts = rs.get_receipt(rid)['counts']
    assert counts['units'] == 25 and counts['repeats'] == 25
    assert len(rs.dm_keys(rid)) == 25


def test_write_waits_for_other_writer(db, clock):
    rid = rs.create_receipt(USER)['id']
    other = sqlite3.connect(db, isolation_level=None, timeout=10)
    other.execute('BEGIN IMMEDIATE')         # «второй воркер» держит write-лок
    done = []

    def worker():
        done.append(_scan(rid, _ean(G1))['result'])

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.3)
    assert done == []                        # ждёт чужую транзакцию, а не падает
    other.execute('COMMIT')
    other.close()
    t.join(10)
    assert done == ['accepted']


# ------------------------------------------------------------------ недоступность

def test_unreadable_db_raises_unavailable(tmp_path, clock):
    path = tmp_path / 'receiving.db'
    garbage = b'this is not a sqlite database at all ' * 200
    path.write_bytes(garbage)
    rs.set_db_path(str(path))
    try:
        with pytest.raises(rs.ReceivingUnavailable) as exc:
            rs.create_receipt(USER)
        assert str(path) not in str(exc.value)
        assert str(exc.value).startswith('База приёмки недоступна')
        with pytest.raises(rs.ReceivingUnavailable):
            rs.list_receipts()
        with pytest.raises(rs.ReceivingUnavailable):
            rs.list_review()
        with pytest.raises(rs.ReceivingUnavailable):
            rs.receipts_needing_processing()
        assert path.read_bytes() == garbage      # файл не тронут
    finally:
        rs.set_db_path(None)


def test_directory_instead_of_db_raises_unavailable(tmp_path, clock):
    folder = tmp_path / 'receiving.db'
    folder.mkdir()
    rs.set_db_path(str(folder))
    try:
        with pytest.raises(rs.ReceivingUnavailable):
            rs.get_receipt(1)
    finally:
        rs.set_db_path(None)


def test_db_path_default_uses_data_path(monkeypatch):
    monkeypatch.setattr(rs, 'get_data_path', lambda name: '/kultura/' + name)
    rs.set_db_path(None)
    assert rs.db_path() == '/kultura/receiving.db'
    rs.set_db_path('/tmp/x.db')
    try:
        assert rs.db_path() == '/tmp/x.db'
    finally:
        rs.set_db_path(None)


# ------------------------------------------------------------------ интеграция и синтаксис

def test_with_real_parse_code(db, clock):
    from core import receiving_codes
    rid = rs.create_receipt(USER)['id']
    raw = '01' + G1 + '21' + 'aBc12!x' + '\x1d' + '93' + 'Zx9Q'
    parsed = receiving_codes.parse_code(raw)
    assert parsed['ok'] and parsed['kind'] == 'datamatrix'
    assert _scan(rid, parsed, raw=raw)['result'] == 'accepted'
    assert _scan(rid, receiving_codes.parse_code(raw), raw=raw)['result'] == 'repeat'
    assert _scan(rid, receiving_codes.parse_code(G2[1:]), raw=G2[1:])['result'] == 'accepted'
    assert _scan(rid, receiving_codes.parse_code('https://example.org'))['result'] == 'rejected'
    assert rs.receipt_lines(rid) == [{'gtin': G2, 'qty': 1, 'kind': 'ean'},
                                     {'gtin': G1, 'qty': 1, 'kind': 'datamatrix'}]


def test_api_dicts_are_json_serializable(db, clock):
    r1, _ = _review_fixture(clock)
    payload = {'receipt': rs.get_receipt(r1), 'lines': rs.receipt_lines(r1),
               'recent': rs.recent_scans(r1), 'review': rs.list_review(state='all'),
               'receipts': rs.review_receipts()}
    json.dumps(payload, ensure_ascii=False)


# ------------------------------------------------------------------ прогресс разбора и удаление

def _processed(rid):
    rs.claim_processing(rid)
    rs.finish_processing(rid, 'done')


def test_receipt_review_progress_and_flags(db, clock):
    open_rid = rs.create_receipt(USER)['id']
    _scan(open_rid, _dm(G1, 'o1'))
    r = rs.get_receipt(open_rid)
    assert (r['review'], r['reviewed'], r['can_delete']) == (None, False, False)

    rid = _closed_receipt_with([_dm(G1, 'a1'), _dm(G1, 'a2'), _ean(G2), _bad()])
    r = rs.get_receipt(rid)
    assert r['review'] == {'open': 0, 'closed': 0, 'missing': 2}        # сверка ещё не прошла
    assert (r['reviewed'], r['can_delete']) == (False, True)

    rs.upsert_review(G1, rid, 'new', [], [], CHZ, 'idx')
    rs.upsert_review(G2, rid, 'found', [_card('k2', 'Балтика')], [], {}, 'idx')
    _processed(rid)
    r = rs.get_receipt(rid)
    assert r['review'] == {'open': 1, 'closed': 1, 'missing': 0}
    assert (r['reviewed'], r['can_delete']) == (False, True)

    rs.update_review(G1, USER, state='done')
    r = rs.get_receipt(rid)
    assert r['review'] == {'open': 0, 'closed': 2, 'missing': 0}
    assert (r['reviewed'], r['can_delete']) == (True, False)
    assert [x['reviewed'] for x in rs.list_receipts()] == [True, False]   # новые сверху: rid, open_rid

    empty = _closed_receipt_with([_bad()])                               # «Пустая приёмка»
    _processed(empty)
    r = rs.get_receipt(empty)
    assert r['review'] == {'open': 0, 'closed': 0, 'missing': 0}
    assert (r['reviewed'], r['can_delete']) == (False, True)             # разбирать нечего, удалить можно


def test_delete_receipt_rules(db, clock):
    open_rid = rs.create_receipt(USER)['id']
    with pytest.raises(rs.ReceiptOpen):
        rs.delete_receipt(open_rid, USER)
    done = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, done, 'found', [_card('k1', 'Жигули')], [], {}, 'idx')
    _processed(done)
    with pytest.raises(rs.ReceiptReviewed):
        rs.delete_receipt(done, USER)
    with pytest.raises(rs.ReceiptNotFound):
        rs.delete_receipt(999, USER)
    with pytest.raises(rs.ReceiptNotFound):
        rs.delete_receipt('abc', USER)
    assert rs.get_receipt(open_rid)['status'] == 'open'                  # отказ ничего не трогает
    assert rs.get_receipt(done)['reviewed'] is True

    pending = _closed_receipt_with([_ean(G2)])                           # сверка не прошла — можно
    res = rs.delete_receipt(pending, USER)
    assert res['receipt']['id'] == pending and res['deleted_by'] == 'Иван'
    assert res['lines'] == [{'gtin': G2, 'qty': 1, 'kind': 'ean'}]
    with pytest.raises(rs.ReceiptNotFound):
        rs.get_receipt(pending)
    with pytest.raises(rs.ReceiptNotFound):
        rs.delete_receipt(pending, USER)                                 # повтор — уже нет
    assert rs.create_receipt(USER)['id'] > pending                       # номер не переиспользуется


def test_delete_receipt_removes_own_rows_keeps_shared(db, clock):
    r1 = _closed_receipt_with([_dm(G1, 'a1'), _dm(G2, 'b1'), _dm(G2, 'b2')])
    rs.upsert_review(G1, r1, 'new', [], [], CHZ, 'idx-1')
    rs.upsert_review(G2, r1, 'new', [], [], {}, 'idx-1')
    rs.update_review(G1, USER, supplier='МаркетБир', note='завести')
    _processed(r1)
    clock.move(minutes=5)
    r2 = _closed_receipt_with([_ean(G2), _ean(G3)])
    rs.upsert_review(G2, r2, 'new', [], [], {}, 'idx-1')
    rs.upsert_review(G3, r2, 'found', [_card('k3', 'Балтика')], [], {}, 'idx-1')
    _processed(r2)
    assert rs.get_review_item(G2)['qty'] == 3

    res = rs.delete_receipt(r1, AGENT)
    assert (res['rows_deleted'], res['rows_kept']) == (1, 1)
    assert res['deleted_by'] == 'Владелец · агент'
    with pytest.raises(rs.ReviewItemNotFound):
        rs.get_review_item(G1)                                           # был только в r1
    shared = rs.get_review_item(G2)
    assert shared['qty'] == 1 and [x['id'] for x in shared['receipts']] == [r2]
    assert shared['state'] == 'open'                                     # r2 его ещё не разобрала
    assert rs.rows_to_notify(r1) == []
    with rs._read() as conn:
        ref = conn.execute('SELECT first_receipt_id, last_receipt_id, notify_receipt_id FROM review_items'
                           ' WHERE gtin = ?', (G2,)).fetchone()
        # Сообщения о r1 ещё не было (notified_at пусто) — объявит r2, которая тоже ещё не объявлена.
        assert (ref['first_receipt_id'], ref['last_receipt_id'], ref['notify_receipt_id']) == (r2, r2, r2)
        tomb = conn.execute('SELECT * FROM receipt_deletions WHERE receipt_id = ?', (r1,)).fetchone()
    assert tomb['deleted_by_name'] == 'Владелец · агент' and tomb['deleted_at'] == clock.iso()
    snap = json.loads(tomb['snapshot_json'])
    assert snap['receipt']['id'] == r1 and snap['rows_kept'] == 1
    assert [(x['gtin'], x['supplier'], x['note'], x['chz_name']) for x in snap['rows_deleted']] == \
        [(G1, 'МаркетБир', 'завести', CHZ['name'])]
    assert [x['gtin'] for x in rs.list_review(state='all')['rows']] == [G2, G3]
    assert rs.get_receipt(r2)['review'] == {'open': 1, 'closed': 1, 'missing': 0}


def test_delete_receipt_removes_scans_and_invoices(db, clock):
    rid = _closed_receipt_with([_ean(G1), _bad()])
    rs.add_invoice(rid, 'r%d_20261003T140500_0123abcd.jpg' % rid, 1000, USER)
    keep = _closed_receipt_with([_ean(G1)])
    rs.add_invoice(keep, 'r%d_20261003T140500_89abcdef.jpg' % keep, 1000, USER)
    res = rs.delete_receipt(rid, USER)
    assert res['invoices'] == ['r%d_20261003T140500_0123abcd.jpg' % rid]
    with rs._read() as conn:
        assert conn.execute('SELECT COUNT(*) FROM receipt_scans WHERE receipt_id = ?', (rid,)).fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM receipt_invoices WHERE receipt_id = ?', (rid,)).fetchone()[0] == 0
    assert len(rs.list_invoices(keep)) == 1 and rs.receipt_lines(keep)[0]['gtin'] == G1


def test_upsert_review_refuses_deleted_receipt(db, clock):
    rid = _closed_receipt_with([_ean(G1)])
    rs.delete_receipt(rid, USER)
    with pytest.raises(rs.ReceiptNotFound):
        rs.upsert_review(G1, rid, 'new', [], [], CHZ, 'idx')
    with pytest.raises(rs.ReviewItemNotFound):
        rs.get_review_item(G1)
    assert rs.upsert_review(G1, None, 'new', [], [], {}, 'idx')['opened'] is True   # без приёмки — как раньше


def test_review_receipts_pending_recent_and_selected(db, clock):
    reviewed = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, reviewed, 'found', [_card('k1', 'Жигули')], [], {}, 'idx')
    _processed(reviewed)
    with_open_row = _closed_receipt_with([_ean(G2)])
    rs.upsert_review(G2, with_open_row, 'new', [], [], {}, 'idx')
    _processed(with_open_row)
    scanning = rs.create_receipt(USER)['id']
    _scan(scanning, _ean(G3))
    pending = _closed_receipt_with([_ean(G3)])                           # сверка ещё не прошла
    empty = _closed_receipt_with([_bad()])
    _processed(empty)

    ids = [r['id'] for r in rs.review_receipts(recent=1)]
    assert ids == [empty, pending, with_open_row]                       # последняя закрытая + неразобранные
    ids = [r['id'] for r in rs.review_receipts(recent=1, selected=[reviewed, scanning, 999])]
    assert ids == [empty, pending, scanning, with_open_row, reviewed]   # выбранные — какие есть
    assert [r['id'] for r in rs.review_receipts(recent=20)] == [empty, pending, with_open_row, reviewed]
    with pytest.raises(ValueError):
        rs.review_receipts(selected='1,x')


def test_list_review_several_receipts(db, clock):
    r1 = _closed_receipt_with([_ean(G1)])
    r2 = _closed_receipt_with([_ean(G2)])
    r3 = _closed_receipt_with([_ean(G3), _ean(G1)])
    for gtin, rid in ((G1, r1), (G2, r2), (G3, r3)):
        rs.upsert_review(gtin, rid, 'new', [], [], {}, 'idx')
    pick = lambda value: sorted(x['gtin'] for x in rs.list_review(receipt_id=value)['rows'])  # noqa: E731
    assert pick([r1, r2]) == sorted([G1, G2])
    assert pick('%d,%d' % (r2, r3)) == sorted([G1, G2, G3])
    assert pick([r1, r1]) == [G1]
    assert pick(r2) == [G2] and pick(str(r2)) == [G2]
    assert pick('') == pick(None) == sorted([G1, G2, G3])
    assert rs.list_review(receipt_id=[r1, r2])['counts']['open_total'] == 2
    for bad in ('x', [0], [True], '1,,x', list(range(1, rs.RECEIPT_FILTER_MAX + 2))):
        with pytest.raises(ValueError):
            rs.list_review(receipt_id=bad)


def test_reviewed_sticks_when_shared_row_reopened_later(db, clock):
    # R1 разобрана полностью; через 20 дней R2 с тем же GTIN переоткрывает общую строку
    # (карточку в iiko заархивировали) — это работа R2, R1 остаётся разобранной.
    r1 = _closed_receipt_with([_ean(G1), _ean(G2)])
    rs.upsert_review(G1, r1, 'found', [_card('k1', 'Жигули')], [], {}, IDX_0700)
    rs.upsert_review(G2, r1, 'new', [], [], CHZ, IDX_0700)
    _processed(r1)
    assert rs.get_receipt(r1)['reviewed'] is False
    rs.update_review(G2, USER, state='done', supplier='МаркетБир', note='завели')
    stamped = rs.get_receipt(r1)
    assert stamped['reviewed'] is True and stamped['reviewed_at'] == clock.iso()
    clock.move(days=20)
    r2 = _closed_receipt_with([_ean(G1)])
    later = clock.iso()
    rs.upsert_review(G1, r2, 'restore', [_card('k1', 'Жигули', archived=True)], [], {}, later)
    assert rs.get_review_item(G1)['state'] == 'open'
    again = rs.get_receipt(r1)
    assert again['review'] == {'open': 1, 'closed': 1, 'missing': 0}     # прогресс — как сейчас
    assert (again['reviewed'], again['can_delete']) == (True, False)
    with pytest.raises(rs.ReceiptReviewed):
        rs.delete_receipt(r1, USER)
    assert [r['id'] for r in rs.review_receipts(recent=1)] == [r2]         # в выборе только новая
    assert rs.get_receipt(r2)['reviewed'] is False


def test_reviewed_cleared_when_own_decision_is_reverted(db, clock):
    # Ревью 2026-10-04: «Вернуть в разбор» и «Сделано», не подтверждённое индексом
    # (опечатка в штрихкоде), — пересмотр решения: приёмка снова не разобрана — в выборе
    # приёмок и удаляется; чужие отметки не трогаются.
    rid = _closed_receipt_with([_ean(G2)])
    rs.upsert_review(G2, rid, 'new', [], [], CHZ, IDX_0700)
    _processed(rid)
    later = _closed_receipt_with([_ean(G1)])                              # новее: в recent=1 — она
    rs.upsert_review(G1, later, 'found', [_card('k1', 'Жигули')], [], {}, IDX_0700)
    _processed(later)

    def picked():
        return [r['id'] for r in rs.review_receipts(recent=1)]

    rs.update_review(G2, USER, state='not_needed')
    assert rs.get_receipt(rid)['reviewed'] is True and picked() == [later]
    clock.move(minutes=1)
    rs.update_review(G2, USER, state='open')                              # «Вернуть в разбор»
    back = rs.get_receipt(rid)
    assert (back['reviewed'], back['reviewed_at'], back['can_delete']) == (False, None, True)
    assert picked() == [later, rid]
    rs.update_review(G2, USER, state='done')
    assert rs.get_receipt(rid)['reviewed'] is True and picked() == [later]
    clock.move(hours=1)
    assert rs.recheck_done(G2, 'new', [], [], clock.iso())['reopened'] is True
    again = rs.get_receipt(rid)
    assert (again['reviewed'], again['can_delete']) == (False, True)
    assert picked() == [later, rid]
    assert rs.get_receipt(later)['reviewed'] is True
    rs.update_review(G2, USER, state='open')                              # уже открыта — ничего
    assert rs.get_receipt(later)['reviewed'] is True


def test_redecided_closed_row_then_reverted_unstamps(db, clock):
    # Ревью 2026-10-04: решение по уже закрытой строке (устаревшая вкладка, агент) сдвигает
    # resolved_at; отметка приёмки переходит к новому решению, и «Вернуть в разбор» её снимает.
    rid = _closed_receipt_with([_ean(G2)])
    rs.upsert_review(G2, rid, 'new', [], [], CHZ, IDX_0700)
    _processed(rid)
    rs.update_review(G2, USER, state='not_needed')
    assert rs.get_receipt(rid)['reviewed'] is True
    clock.move(minutes=5)
    rs.update_review(G2, USER, state='done')
    assert rs.get_receipt(rid)['reviewed_at'] == clock.iso()
    clock.move(minutes=5)
    rs.update_review(G2, USER, state='open')
    back = rs.get_receipt(rid)
    assert (back['reviewed'], back['can_delete']) == (False, True)


def test_revert_keeps_stamps_of_previous_cycle(db, clock):
    # R1 разобрана («Сделано»); через 20 дней R2 переоткрыла общую строку, бухгалтер решил
    # её снова и вернул в разбор: отметку теряет только R2 — R1 разобрана в прошлом круге.
    r1 = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, r1, 'new', [], [], CHZ, IDX_0700)
    _processed(r1)
    rs.update_review(G1, USER, state='done')
    clock.move(days=20)
    r2 = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, r2, 'restore', [_card('k1', 'Жигули', archived=True)], [], {}, clock.iso())
    _processed(r2)
    clock.move(minutes=5)
    rs.update_review(G1, USER, state='done')
    assert rs.get_receipt(r2)['reviewed'] is True
    clock.move(minutes=5)
    rs.update_review(G1, USER, state='open')
    assert rs.get_receipt(r1)['reviewed'] is True
    assert rs.get_receipt(r2)['reviewed'] is False


def test_v1_copy_restored_on_the_fly_does_not_break_receipt_lists(db, clock, tmp_path):
    # Ревью 2026-10-04: файл БД заменили копией до v3 (без reviewed_at), не перезапуская
    # сервис: списки приёмок не падают, а схема догоняется при первом запросе к колонке.
    rid = _closed_receipt_with([_ean(G1)])
    path = rs.db_path()
    conn = sqlite3.connect(path)
    conn.execute('ALTER TABLE receipts DROP COLUMN reviewed_at')
    conn.execute('PRAGMA user_version = 1')
    conn.commit()
    conn.close()
    assert [r['id'] for r in rs.list_receipts()] == [rid]
    assert rs.get_receipt(rid)['reviewed_at'] is None
    with pytest.raises(rs.ReceivingUnavailable):
        rs.review_receipts()                         # «no such column» — схема догоняется
    assert [r['id'] for r in rs.review_receipts()] == [rid]


def test_reviewed_stamped_by_auto_close_and_found_on_finish(db, clock):
    allfound = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, allfound, 'found', [_card('k1', 'Жигули')], [], {}, IDX_0700)
    _processed(allfound)                                                  # всё сразу в iiko
    assert rs.get_receipt(allfound)['reviewed_at'] == clock.iso()
    pending = _closed_receipt_with([_ean(G2)])
    rs.upsert_review(G2, pending, 'new', [], [], CHZ, IDX_0700)
    _processed(pending)
    assert rs.get_receipt(pending)['reviewed_at'] is None
    clock.move(hours=1)
    rs.reclassify_open(G2, 'found', [_card('k2', 'Балтика')], [], index_built_at=clock.iso())
    assert rs.get_receipt(pending)['reviewed_at'] == clock.iso()          # карточку завели — нашлась сама


def test_schema_v3_backfills_reviewed_at(db, clock):
    rid = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, rid, 'found', [_card('k1', 'Жигули')], [], {}, IDX_0700)
    _processed(rid)
    conn = sqlite3.connect(db)
    try:
        conn.execute('UPDATE receipts SET reviewed_at = NULL')
        conn.execute('PRAGMA user_version = 2')
        conn.commit()
    finally:
        conn.close()
    clock.move(minutes=3)
    rs.set_db_path(db)                                                    # новый «процесс»
    assert rs.get_receipt(rid)['reviewed_at'] == clock.iso()


def test_delete_keeps_decided_rows_of_a_receipt_still_scanning(db, clock):
    r1 = _closed_receipt_with([_ean(G1), _ean(G2), _ean(G3)])
    for gtin in (G1, G2, G3):
        rs.upsert_review(gtin, r1, 'new', [], [], CHZ, IDX_0700)
    rs.update_review(G1, USER, state='not_needed', note='промо, не заводим')
    rs.update_review(G2, USER, supplier='МаркетБир')
    scanning = rs.create_receipt(USER)['id']                             # ту же поставку досканируют
    for gtin in (G1, G2, G3):
        _scan(scanning, _ean(gtin))
    res = rs.delete_receipt(r1, USER)
    assert (res['rows_deleted'], res['rows_kept']) == (1, 2)
    kept = rs.get_review_item(G1)
    assert (kept['state'], kept['resolution'], kept['note']) == ('closed', 'not_needed', 'промо, не заводим')
    assert rs.get_review_item(G2)['supplier'] == 'МаркетБир'
    with pytest.raises(rs.ReviewItemNotFound):
        rs.get_review_item(G3)                                            # нетронутую заведёт закрытие
    with rs._read() as conn:
        ref = conn.execute('SELECT notify_receipt_id FROM review_items WHERE gtin = ?', (G2,)).fetchone()
    assert ref['notify_receipt_id'] == scanning                          # о G2 сообщит новая приёмка
    rs.close_receipt(scanning, USER)
    again = rs.upsert_review(G1, scanning, 'new', [], [], {}, IDX_0730)
    assert again['row']['resolution'] == 'not_needed' and again['opened'] is False   # «Не нужно» дожило


def test_delete_announced_receipt_does_not_announce_kept_rows_again(db, clock):
    r1 = _closed_receipt_with([_ean(G1)])
    rs.upsert_review(G1, r1, 'new', [], [], CHZ, IDX_0700)
    _processed(r1)
    rs.mark_notified(r1)                                                  # о G1 уже сообщили
    r2 = _closed_receipt_with([_ean(G1)])
    rs.delete_receipt(r1, USER)
    with rs._read() as conn:
        ref = conn.execute('SELECT notify_receipt_id FROM review_items WHERE gtin = ?', (G1,)).fetchone()
    assert ref['notify_receipt_id'] is None
    assert rs.rows_to_notify(r2) == []


def test_scan_into_deleted_receipt_is_closed_not_missing(db, clock):
    rid = _closed_receipt_with([_ean(G1)])
    rs.delete_receipt(rid, USER)
    with pytest.raises(rs.ReceiptDeleted) as info:
        _scan(rid, _ean(G2))
    assert isinstance(info.value, rs.ReceiptClosed)                       # телефон перенесёт сканы
    with pytest.raises(rs.ReceiptNotFound):
        _scan(rid + 100, _ean(G2))                                        # такой не было — 404


def test_delete_refused_while_processing_runs(db, clock):
    rid = _closed_receipt_with([_ean(G1)])
    assert rs.claim_processing(rid) is True
    r = rs.get_receipt(rid)
    assert (r['process_state'], r['can_delete']) == ('running', False)
    with pytest.raises(rs.ReceiptProcessing):
        rs.delete_receipt(rid, USER)
    clock.move(seconds=rs.PROCESS_STALE_SEC + 1)                          # обработка зависла
    assert rs.get_receipt(rid)['can_delete'] is True
    assert rs.delete_receipt(rid, USER)['receipt']['id'] == rid


def test_schema_v1_database_gets_deletions_table(db, clock):
    rid = rs.create_receipt(USER)['id']
    conn = sqlite3.connect(db)
    try:
        conn.execute('DROP TABLE receipt_deletions')
        conn.execute('PRAGMA user_version = 1')
        conn.commit()
    finally:
        conn.close()
    rs.set_db_path(db)                                                    # новый «процесс»
    assert rs.get_receipt(rid)['id'] == rid
    conn = sqlite3.connect(db)
    try:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 3
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert 'receipt_deletions' in tables
    finally:
        conn.close()


def test_py310_compatible_syntax():
    """CI и прод — Python 3.10: модуль должен разбираться грамматикой 3.10 (без PEP 701 и т.п.)."""
    import ast
    src = open(rs.__file__, encoding='utf-8').read()
    ast.parse(src, feature_version=(3, 10))


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
