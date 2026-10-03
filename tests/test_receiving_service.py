"""Тесты обработки приёмок и обновления индекса (core/receiving_service.py). Сети нет.

Модули приёмки (receiving_index, receiving_chz, receiving_store, receiving_notify)
подменяются фейками по контрактам спецификации (docs/receiving.md): тесты не
зависят от их внутренностей. Последний раздел — сквозная проверка с настоящими
receiving_store (временная receiving.db) и receiving_index (индекс из фикстуры
в памяти, iiko — фейк); Честный знак и Telegram — фейки.
Что проверяется:
- process_receipt: статусы found / restore / duplicate / similar / new, запрос ЧЗ
  только для не-found, кандидаты похожей только с названием ЧЗ; пустая приёмка;
  индекса нет -> пересборка, не вышло -> error «Нет индекса iiko»; старый индекс и
  есть не-found -> пересборка (trigger close) и сверка заново, свежий или все found
  -> без пересборки, индекс пересобрали, пока ждали лок -> без второй пересборки;
  сбой пересборки -> предупреждение в заметке; ошибки ЧЗ -> в заметку; сообщение
  бухгалтерии только когда открыты new / similar / restore; сбой -> error с
  текстом без секретов; сбой записи итога не роняет поток;
- start_receipt_processing: claim -> поток-демон с process_receipt; не взяли ->
  без потока; поток не стартовал -> error; retry_stuck_processing;
- start_receiving_index_refresh: 202 / 409 / 503 (нет кредов, лок недоступен,
  поток не стартовал), фоновое тело зовёт пересборку с тем же локом;
- run_index_refresh: пересборка + пересверка, сбой пересверки не роняет;
- reconcile_open_rows: автозакрытие, «новая» -> «похожая» по названию ЧЗ,
  запрос ЧЗ только для строк без названия, счётчики, без индекса — ничего;
- status(), classify_gtins, грамматика Python 3.10.
"""
import os
import re
import sys
import threading
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['SESSION_COOKIE_SECURE'] = '0'

from core import receiving_service as svc  # noqa: E402

# Настоящая проверка кредов: фикстура fakes подменяет её на «креды есть».
REAL_IIKO_CONFIGURED = svc.iiko_configured

# GTIN-ы фейковых тестов: сервис их не проверяет (это делает разбор кода при скане).
G_FOUND, G_RESTORE, G_DUP = '04600000000011', '04600000000028', '04600000000035'
G_SIMILAR, G_NEW_NAMED, G_NEW_BARE = '04600000000042', '04600000000059', '04600000000066'

CARD_A = {'id': 'a', 'name': 'Пиво Хеллес', 'num': '101', 'group': 'Пиво', 'supplier': 'МаркетБир',
          'unit': 'шт', 'deleted': False, 'archived': False, 'keg': False}
CARD_DEL = dict(CARD_A, id='d', name='Сидр старый', deleted=True)
CARD_B = dict(CARD_A, id='b', name='Пиво Хеллес копия')
CAND = dict(CARD_A, id='c', name='Пиво Портер', score=2)


# ----------------------------------------------------------------- фейки модулей

class FakeLock:
    def __init__(self):
        self.released = 0

    def release(self):
        self.released += 1


def make_index(age=2, classes=None, similar=None, built_at='2026-10-03T07:30:00+03:00'):
    """Индекс фейка: classes {gtin: (status, cards)}, similar {название ЧЗ: [кандидаты]}."""
    return {'built_at': built_at, 'age': age, 'classes': dict(classes or {}),
            'similar': dict(similar or {})}


BASE_CLASSES = {G_FOUND: ('found', [CARD_A]), G_RESTORE: ('restore', [CARD_DEL]),
                G_DUP: ('duplicate', [CARD_A, CARD_B])}


class FakeIndexModule:
    """receiving_index по контракту: load_index/index_info/classify/similar_cards/..."""

    class IndexSourceError(Exception):
        pass

    class RefreshBusy(Exception):
        pass

    SIMILAR_LIMIT = 5

    def __init__(self, index=None):
        self.index = index
        self.next_index = None          # что «соберёт» refresh_index
        self.refresh_error = None
        self.busy = False
        self.on_acquire = None          # вызов при взятии лока (чужая пересборка, пока ждали)
        self.refresh_calls = []
        self.acquire_calls = []
        self.similar_calls = []
        self.locks = []
        self.state = {'running': False, 'trigger': 'button', 'started_at': '', 'finished_at': '',
                      'error': '', 'counts': None}

    def load_index(self):
        return self.index

    def index_info(self, index):
        if not index:
            return None
        return {'built_at': index['built_at'], 'age_minutes': index['age'], 'counts': {'products': 3},
                'source': 'v2'}

    def classify(self, gtin, index):
        status, cards = index['classes'].get(gtin, ('missing', []))
        return {'status': status, 'cards': [dict(c) for c in cards]}

    def similar_cards(self, name, index, brand='', limit=5):
        self.similar_calls.append((name, brand))
        return [dict(c) for c in index['similar'].get(name, [])]

    def acquire_run_lock(self, wait=0):
        self.acquire_calls.append(wait)
        if self.busy:
            raise self.RefreshBusy('Индекс iiko уже обновляется')
        if self.on_acquire:
            self.on_acquire()
        lock = FakeLock()
        self.locks.append(lock)
        return lock

    def refresh_index(self, trigger, *, lock=None, wait=0, fetch=None, after_save=None):
        self.refresh_calls.append({'trigger': trigger, 'lock': lock, 'wait': wait,
                                   'after_save': after_save is not None})
        try:
            if self.busy and lock is None:
                raise self.RefreshBusy('Индекс iiko уже обновляется')
            if self.refresh_error is not None:
                raise self.refresh_error
            if self.next_index is not None:
                self.index = self.next_index
            if after_save is not None:
                try:
                    after_save(self.index)          # как настоящий: до «готово», сбой не роняет
                except Exception as error:  # noqa: BLE001
                    self.after_save_error = error
            return self.index_info(self.index)
        finally:
            if lock is not None:
                lock.release()

    def read_state(self):
        return dict(self.state)


class FakeChzModule:
    class ChzError(Exception):
        pass

    def __init__(self, names=None, errors=(), boom=None):
        self.names = dict(names or {})
        self.errors = list(errors)
        self.boom = boom
        self.calls = []

    def lookup(self, gtins, **kwargs):
        self.calls.append(list(gtins))
        if self.boom is not None:
            raise self.boom
        items = {g: dict(self.names[g], source='cache', fetched_at='2026-10-03T14:00:00+03:00')
                 for g in gtins if g in self.names}
        return {'items': items, 'missing': [g for g in gtins if g not in items],
                'errors': list(self.errors), 'remote_used': False}


class FakeStoreModule:
    """receiving_store по контракту: строки разбора по правилам upsert_review/reclassify_open."""

    class ReceivingUnavailable(Exception):
        pass

    class ReceiptNotFound(Exception):
        pass

    class ReviewItemNotFound(Exception):
        pass

    def __init__(self):
        self.lines = {}
        self.rows = {}
        self.finished = []
        self.upserts = []
        self.reclassified = []
        self.claimable = set()
        self.claims = []
        self.needing = []
        self.fail_upsert = None
        self.fail_finish = None
        self.fail_claim = None
        self.notified = {}
        self.rechecked = []

    # приёмки
    def receipt_lines(self, rid):
        if rid not in self.lines:
            raise self.ReceiptNotFound(str(rid))
        return [dict(x) for x in self.lines[rid]]

    def get_receipt(self, rid):
        return {'id': rid, 'status': 'closed', 'closed_at': '2026-10-03T14:05:00+03:00',
                'closed_by': 'Иван', 'notified_at': self.notified.get(rid),
                'counts': {'units': 10, 'gtins': len(self.lines.get(rid, []))}}

    def rows_to_notify(self, rid):
        return [self._row(g) for g in sorted(self.rows)
                if self.rows[g]['state'] == 'open' and self.rows[g].get('notify_receipt_id') == rid]

    def mark_notified(self, rid):
        self.notified[rid] = '2026-10-03T14:06:00+03:00'

    def done_review_gtins(self):
        return sorted(g for g, r in self.rows.items()
                      if r['state'] == 'closed' and r['resolution'] == 'done' and r['status'] != 'found')

    def recheck_done(self, gtin, status, cards, candidates, index_built_at):
        self.rechecked.append({'gtin': gtin, 'status': status, 'index_built_at': index_built_at})
        if gtin not in self.rows:
            raise self.ReviewItemNotFound(gtin)
        row = self.rows[gtin]
        if (row['state'] != 'closed' or row['resolution'] != 'done'
                or not index_built_at or index_built_at <= str(row.get('resolved_at') or '')):
            return {'row': self._row(gtin), 'reopened': False}
        row.update(status=status, cards=list(cards), candidates=list(candidates))
        reopened = status != 'found'
        if reopened:
            row.update(state='open', resolution='', reopened=row['reopened'] + 1,
                       notify_receipt_id=None)
        return {'row': self._row(gtin), 'reopened': reopened}

    def finish_processing(self, rid, state, note=''):
        if self.fail_finish is not None:
            raise self.fail_finish
        self.finished.append((rid, state, note))

    def claim_processing(self, rid, retry_error_now=False):
        self.claims.append(rid)
        self.retry_error_now = retry_error_now
        if self.fail_claim is not None:
            raise self.fail_claim
        if rid in self.claimable:
            self.claimable.discard(rid)
            return True
        return False

    def receipts_needing_processing(self):
        return list(self.needing)

    # строки разбора
    def _row(self, gtin):
        return {k: (list(v) if isinstance(v, list) else (dict(v) if isinstance(v, dict) else v))
                for k, v in self.rows[gtin].items()}

    def upsert_review(self, gtin, receipt_id, status, cards, candidates, chz, index_built_at):
        self.upserts.append({'gtin': gtin, 'receipt_id': receipt_id, 'status': status,
                             'cards': cards, 'candidates': candidates, 'chz': chz,
                             'index_built_at': index_built_at})
        if self.fail_upsert is not None:
            raise self.fail_upsert
        opened = reopened = False
        row = self.rows.get(gtin)
        if row is None:
            found = status == 'found'
            row = {'gtin': gtin, 'state': 'closed' if found else 'open',
                   'resolution': 'found' if found else '', 'chz': {}, 'reopened': 0,
                   'notify_receipt_id': None if found else receipt_id}
            self.rows[gtin] = row
            opened = not found
        elif row['state'] == 'open':
            if status == 'found':
                row.update(state='closed', resolution='auto')
        elif row['resolution'] != 'not_needed' and status != 'found':
            row.update(state='open', resolution='', reopened=row['reopened'] + 1,
                       notify_receipt_id=receipt_id)
            opened = reopened = True
        row.update(status=status, cards=list(cards), candidates=list(candidates),
                   index_built_at=index_built_at)
        if chz:
            row['chz'] = dict(chz)
        return {'row': self._row(gtin), 'opened': opened, 'reopened': reopened}

    def reclassify_open(self, gtin, status, cards, candidates, chz=None, index_built_at=''):
        self.reclassified.append({'gtin': gtin, 'status': status, 'cards': cards,
                                  'candidates': candidates, 'chz': chz,
                                  'index_built_at': index_built_at})
        if gtin not in self.rows:
            raise self.ReviewItemNotFound(gtin)
        row = self.rows[gtin]
        if row['state'] != 'open':
            return {'row': self._row(gtin), 'auto_closed': False}
        row.update(status=status, cards=list(cards), candidates=list(candidates))
        if chz:
            row['chz'] = dict(chz)
        auto = status == 'found'
        if auto:
            row.update(state='closed', resolution='auto')
        return {'row': self._row(gtin), 'auto_closed': auto}

    def open_review_gtins(self):
        return sorted(g for g, r in self.rows.items() if r['state'] == 'open')

    def get_review_item(self, gtin):
        if gtin not in self.rows:
            raise self.ReviewItemNotFound(gtin)
        return self._row(gtin)

    def add_row(self, gtin, status, state='open', resolution='', cards=(), candidates=(), chz=None,
                resolved_at=None, notify_receipt_id=None):
        self.rows[gtin] = {'gtin': gtin, 'status': status, 'state': state, 'resolution': resolution,
                           'cards': [dict(c) for c in cards], 'candidates': [dict(c) for c in candidates],
                           'chz': dict(chz or {}), 'reopened': 0, 'resolved_at': resolved_at,
                           'notify_receipt_id': notify_receipt_id}


class FakeNotifyModule:
    def __init__(self, boom=None):
        self.calls = []
        self.boom = boom

    def notify_receipt(self, receipt, rows):
        if self.boom is not None:
            raise self.boom
        self.calls.append((receipt, rows))
        return {'sent': 1, 'failed': [], 'skipped': None}


class Fakes:
    def __init__(self, index, store, chz, notify):
        self.index, self.store, self.chz, self.notify = index, store, chz, notify


@pytest.fixture
def fakes(monkeypatch):
    index = FakeIndexModule(make_index(classes=BASE_CLASSES))
    store = FakeStoreModule()
    chz = FakeChzModule()
    notify = FakeNotifyModule()
    monkeypatch.setattr(svc, 'receiving_index', index)
    monkeypatch.setattr(svc, 'receiving_store', store)
    monkeypatch.setattr(svc, 'receiving_chz', chz)
    monkeypatch.setattr(svc, 'receiving_notify', notify)
    monkeypatch.setattr(svc, 'iiko_configured', lambda: True)
    return Fakes(index, store, chz, notify)


def _lines(*gtins, qty=1):
    return [{'gtin': g, 'qty': qty, 'kind': 'datamatrix'} for g in gtins]


def _by_gtin(upserts):
    return {u['gtin']: u for u in upserts}


# ----------------------------------------------------------------- process_receipt

def test_process_full_flow_statuses_chz_and_notify(fakes):
    fakes.store.lines[7] = _lines(G_FOUND, G_RESTORE, G_DUP, G_SIMILAR, G_NEW_NAMED, G_NEW_BARE)
    fakes.chz.names = {G_SIMILAR: {'name': 'Пиво Портер тёмное', 'brand': 'Бровари'},
                       G_NEW_NAMED: {'name': 'Квас живой', 'brand': ''}}
    fakes.index.index['similar'] = {'Пиво Портер тёмное': [CAND]}

    res = svc.process_receipt(7)

    assert res['state'] == 'done' and res['note'] == ''
    assert res['gtins'] == 6
    assert res['statuses'] == {'found': 1, 'restore': 1, 'duplicate': 1, 'similar': 1, 'new': 2}
    assert res['opened'] == 5 and res['notified'] is True
    assert fakes.store.finished == [(7, 'done', '')]
    # Индекс свежий (2 мин) — без пересборки и без лока
    assert fakes.index.refresh_calls == [] and fakes.index.acquire_calls == []
    # ЧЗ — один запрос, только не-found, в порядке позиций
    assert fakes.chz.calls == [[G_RESTORE, G_DUP, G_SIMILAR, G_NEW_NAMED, G_NEW_BARE]]
    # Похожие — только для missing с названием ЧЗ (бренд передан)
    assert fakes.index.similar_calls == [('Пиво Портер тёмное', 'Бровари'), ('Квас живой', '')]

    ups = _by_gtin(fakes.store.upserts)
    assert {g: u['status'] for g, u in ups.items()} == {
        G_FOUND: 'found', G_RESTORE: 'restore', G_DUP: 'duplicate', G_SIMILAR: 'similar',
        G_NEW_NAMED: 'new', G_NEW_BARE: 'new'}
    assert all(u['receipt_id'] == 7 and u['index_built_at'] == '2026-10-03T07:30:00+03:00'
               for u in ups.values())
    assert [c['id'] for c in ups[G_DUP]['cards']] == ['a', 'b']
    assert ups[G_DUP]['candidates'] == []
    assert ups[G_SIMILAR]['candidates'] == [CAND] and ups[G_SIMILAR]['cards'] == []
    assert ups[G_SIMILAR]['chz']['name'] == 'Пиво Портер тёмное'
    assert ups[G_NEW_NAMED]['chz']['name'] == 'Квас живой'
    assert ups[G_FOUND]['chz'] == {} and ups[G_NEW_BARE]['chz'] == {}

    assert len(fakes.notify.calls) == 1
    receipt, rows = fakes.notify.calls[0]
    assert receipt['id'] == 7
    assert sorted(r['gtin'] for r in rows) == sorted([G_RESTORE, G_DUP, G_SIMILAR, G_NEW_NAMED, G_NEW_BARE])


def test_process_all_found_no_chz_no_notify(fakes):
    fakes.store.lines[1] = _lines(G_FOUND)
    fakes.index.index['age'] = 600          # старый индекс, но всё найдено — пересборка не нужна
    res = svc.process_receipt(1)
    assert res['state'] == 'done' and res['statuses'] == {'found': 1} and res['opened'] == 0
    assert fakes.index.refresh_calls == [] and fakes.chz.calls == [] and fakes.notify.calls == []
    assert fakes.store.finished == [(1, 'done', '')]


def test_process_empty_receipt(fakes):
    fakes.store.lines[2] = []
    fakes.index.index = None
    res = svc.process_receipt(2)
    assert res['state'] == 'done' and res['note'] == 'Пустая приёмка'
    assert fakes.store.finished == [(2, 'done', 'Пустая приёмка')]
    assert fakes.index.refresh_calls == [] and fakes.store.upserts == []


def test_process_stale_index_with_missing_refreshes_and_reclassifies(fakes):
    fakes.store.lines[3] = _lines(G_FOUND, G_NEW_BARE)
    fakes.index.index['age'] = svc.INDEX_RECHECK_MIN + 1
    # бухгалтер завёл карточку утром: в новом индексе GTIN найден
    fakes.index.next_index = make_index(age=0, classes=dict(BASE_CLASSES, **{G_NEW_BARE: ('found', [CARD_B])}),
                                        built_at='2026-10-03T14:06:00+03:00')
    res = svc.process_receipt(3)
    assert res['state'] == 'done' and res['note'] == ''
    assert fakes.index.acquire_calls == [svc.INDEX_WAIT_SEC]
    assert len(fakes.index.refresh_calls) == 1
    call = fakes.index.refresh_calls[0]
    assert call['trigger'] == 'close' and call['lock'] is fakes.index.locks[0]
    assert fakes.index.locks[0].released == 1
    ups = _by_gtin(fakes.store.upserts)
    assert ups[G_NEW_BARE]['status'] == 'found'
    assert ups[G_NEW_BARE]['index_built_at'] == '2026-10-03T14:06:00+03:00'
    assert fakes.chz.calls == []           # после пересборки всё найдено
    assert fakes.notify.calls == []


def test_process_fresh_index_with_missing_does_not_refresh(fakes):
    fakes.store.lines[3] = _lines(G_NEW_BARE)
    fakes.index.index['age'] = svc.INDEX_RECHECK_MIN       # ровно на границе — ещё свежий
    res = svc.process_receipt(3)
    assert res['statuses'] == {'new': 1}
    assert fakes.index.refresh_calls == [] and fakes.index.acquire_calls == []


def test_process_index_refreshed_while_waiting_for_lock(fakes):
    fakes.store.lines[4] = _lines(G_NEW_BARE)
    fakes.index.index['age'] = 90
    fresh = make_index(age=0, classes=dict(BASE_CLASSES, **{G_NEW_BARE: ('found', [CARD_A])}))

    def other_worker_refreshed():
        fakes.index.index = fresh

    fakes.index.on_acquire = other_worker_refreshed
    res = svc.process_receipt(4)
    assert fakes.index.refresh_calls == []                 # второй пересборки нет
    assert fakes.index.locks[0].released == 1
    assert res['statuses'] == {'found': 1} and res['note'] == ''


def test_process_refresh_failure_is_warning(fakes):
    fakes.store.lines[5] = _lines(G_NEW_BARE)
    fakes.index.index['age'] = 600
    fakes.index.refresh_error = fakes.index.IndexSourceError('iiko ответил HTTP 500 (товары)')
    res = svc.process_receipt(5)
    assert res['state'] == 'done'
    assert res['note'] == 'Индекс iiko не обновлён, сверено по прежнему: iiko ответил HTTP 500 (товары)'
    assert _by_gtin(fakes.store.upserts)[G_NEW_BARE]['status'] == 'new'
    assert fakes.store.finished[-1][1] == 'done'


def test_process_refresh_busy_is_warning(fakes):
    fakes.store.lines[5] = _lines(G_NEW_BARE)
    fakes.index.index['age'] = 600
    fakes.index.busy = True
    res = svc.process_receipt(5)
    assert res['state'] == 'done'
    assert 'Индекс iiko уже обновляется' in res['note']
    assert fakes.index.acquire_calls == [svc.INDEX_WAIT_SEC]


def test_process_without_index_refreshes_first(fakes):
    fakes.store.lines[6] = _lines(G_FOUND)
    built = fakes.index.index
    fakes.index.index = None
    fakes.index.next_index = dict(built, age=0)
    res = svc.process_receipt(6)
    assert res['state'] == 'done' and res['statuses'] == {'found': 1}
    assert [c['trigger'] for c in fakes.index.refresh_calls] == ['close']
    assert fakes.index.acquire_calls == [svc.INDEX_WAIT_SEC]


def test_process_without_index_and_failed_refresh_is_error(fakes):
    fakes.store.lines[6] = _lines(G_FOUND, G_NEW_BARE)
    fakes.index.index = None
    fakes.index.refresh_error = fakes.index.IndexSourceError('Не настроено подключение к iiko')
    res = svc.process_receipt(6)
    assert res['state'] == 'error'
    assert fakes.store.finished == [(6, 'error', 'Нет индекса iiko: Не настроено подключение к iiko')]
    assert fakes.store.upserts == [] and fakes.chz.calls == [] and fakes.notify.calls == []


def test_process_without_creds_does_not_touch_lock(fakes, monkeypatch):
    monkeypatch.setattr(svc, 'iiko_configured', lambda: False)
    fakes.store.lines[6] = _lines(G_FOUND)
    fakes.index.index = None
    res = svc.process_receipt(6)
    assert res['state'] == 'error'
    assert res['note'] == 'Нет индекса iiko: Не настроено подключение к iiko'
    assert fakes.index.acquire_calls == [] and fakes.index.refresh_calls == []
    # Индекс есть, но старый: без кредов сверка по нему с предупреждением
    fakes.index.index = make_index(age=600, classes=BASE_CLASSES)
    fakes.store.lines[7] = _lines(G_NEW_BARE)
    res = svc.process_receipt(7)
    assert res['state'] == 'done'
    assert res['note'] == 'Индекс iiko не обновлён, сверено по прежнему: Не настроено подключение к iiko'
    assert fakes.index.acquire_calls == []


def test_process_without_index_busy_is_error(fakes):
    fakes.store.lines[6] = _lines(G_FOUND)
    fakes.index.index = None
    fakes.index.busy = True
    res = svc.process_receipt(6)
    assert res['state'] == 'error'
    assert res['note'] == 'Нет индекса iiko: Индекс iiko уже обновляется'


def test_process_without_index_unexpected_refresh_error_hides_details(fakes):
    fakes.store.lines[6] = _lines(G_FOUND)
    fakes.index.index = None
    fakes.index.refresh_error = RuntimeError('GET https://iiko/api?key=SECRET-TOKEN failed')
    res = svc.process_receipt(6)
    assert res['state'] == 'error'
    assert res['note'] == 'Нет индекса iiko: Сбой: RuntimeError'
    assert 'SECRET' not in res['note']


def test_process_chz_errors_go_to_note(fakes):
    fakes.store.lines[8] = _lines(G_NEW_BARE, G_SIMILAR)
    fakes.chz.names = {G_SIMILAR: {'name': 'Пиво Портер', 'brand': ''}}
    fakes.chz.errors = ['chz.py на бар-ПК устарел: обновите', 'Бар-ПК занят  другим\nзапросом']
    fakes.index.index['similar'] = {'Пиво Портер': [CAND]}
    res = svc.process_receipt(8)
    assert res['state'] == 'done'
    assert res['note'] == ('Честный знак: chz.py на бар-ПК устарел: обновите; '
                           'Честный знак: Бар-ПК занят другим запросом')
    assert res['statuses'] == {'new': 1, 'similar': 1}


def test_process_chz_crash_is_warning_without_details(fakes):
    fakes.store.lines[8] = _lines(G_NEW_NAMED)
    fakes.chz.boom = RuntimeError('ssh Администратор@100.98.149.108 password=xyz')
    res = svc.process_receipt(8)
    assert res['state'] == 'done'
    assert res['note'] == 'Названия ЧЗ не получены: Сбой: RuntimeError'
    assert res['statuses'] == {'new': 1}


def test_process_chz_error_class_text_is_shown(fakes):
    fakes.store.lines[8] = _lines(G_NEW_NAMED)
    fakes.chz.boom = fakes.chz.ChzError('chz.py на бар-ПК устарел')
    res = svc.process_receipt(8)
    assert res['note'] == 'Названия ЧЗ не получены: chz.py на бар-ПК устарел'


def test_notify_only_for_new_similar_restore(fakes):
    # Открыт только дубль — бухгалтерии не пишем
    fakes.store.lines[9] = _lines(G_DUP, G_FOUND)
    res = svc.process_receipt(9)
    assert res['opened'] == 1 and res['notified'] is False and fakes.notify.calls == []

    # Строка уже открыта прошлой приёмкой — повторно не пишем
    fakes.store.add_row(G_NEW_BARE, 'new')
    fakes.store.lines[10] = _lines(G_NEW_BARE)
    res = svc.process_receipt(10)
    assert res['opened'] == 0 and fakes.notify.calls == []

    # Не нужна (not_needed) — остаётся закрытой, не пишем
    fakes.store.add_row(G_NEW_NAMED, 'new', state='closed', resolution='not_needed')
    fakes.store.lines[11] = _lines(G_NEW_NAMED)
    res = svc.process_receipt(11)
    assert res['opened'] == 0 and fakes.notify.calls == []

    # Закрыта «Сделано», а карточку удалили — строка открывается снова, пишем
    fakes.store.add_row(G_RESTORE, 'found', state='closed', resolution='done')
    fakes.store.lines[12] = _lines(G_RESTORE)
    res = svc.process_receipt(12)
    assert res['opened'] == 1 and res['notified'] is True
    assert [r['gtin'] for r in fakes.notify.calls[0][1]] == [G_RESTORE]


def test_notify_failure_is_warning(fakes):
    fakes.notify.boom = RuntimeError('no threads')
    fakes.store.lines[13] = _lines(G_NEW_BARE)
    res = svc.process_receipt(13)
    assert res['state'] == 'done' and res['notified'] is False
    assert res['note'] == 'Сообщение бухгалтерии не отправлено: Сбой: RuntimeError'


def test_process_store_failure_is_error_without_secrets(fakes):
    fakes.store.lines[14] = _lines(G_NEW_BARE)
    fakes.store.fail_upsert = RuntimeError('token=abc /kultura/receiving.db')
    res = svc.process_receipt(14)
    assert res['state'] == 'error'
    assert fakes.store.finished == [(14, 'error', 'Сбой: RuntimeError')]


def test_process_store_unavailable_text_is_shown(fakes):
    fakes.store.lines[14] = _lines(G_NEW_BARE)
    fakes.store.fail_upsert = fakes.store.ReceivingUnavailable('База приёмки недоступна: database is locked')
    res = svc.process_receipt(14)
    assert fakes.store.finished == [(14, 'error', 'База приёмки недоступна: database is locked')]
    assert res['note'] == 'База приёмки недоступна: database is locked'


def test_process_unknown_receipt_is_error(fakes):
    res = svc.process_receipt(404)
    assert res['state'] == 'error'
    assert fakes.store.finished == [(404, 'error', 'Приёмка не найдена')]


def test_process_finish_failure_does_not_raise(fakes):
    fakes.store.lines[15] = _lines(G_FOUND)
    fakes.store.fail_finish = fakes.store.ReceivingUnavailable('База приёмки недоступна: disk I/O error')
    res = svc.process_receipt(15)
    assert res['state'] == 'error'


def test_classify_gtins(fakes):
    index = make_index(classes=BASE_CLASSES, similar={'Эль': [CAND]})
    out = svc.classify_gtins([G_FOUND, G_SIMILAR, G_NEW_BARE, G_NEW_NAMED], index,
                             {G_SIMILAR: {'name': '', 'full_name': 'Эль'},
                              G_NEW_NAMED: {'name': 'Неизвестное'}})
    assert out[G_FOUND] == {'status': 'found', 'cards': [CARD_A], 'candidates': []}
    assert out[G_SIMILAR] == {'status': 'similar', 'cards': [], 'candidates': [CAND]}   # full_name
    assert out[G_NEW_BARE]['status'] == 'new'
    assert out[G_NEW_NAMED]['status'] == 'new'
    assert svc.classify_gtins([], index, None) == {}


# ----------------------------------------------------------------- запуск обработки

def test_start_processing_claims_and_runs_thread(fakes, monkeypatch):
    done = threading.Event()
    seen = []

    def fake_process(rid):
        seen.append((rid, threading.current_thread().name, threading.current_thread().daemon))
        done.set()

    monkeypatch.setattr(svc, 'process_receipt', fake_process)
    fakes.store.claimable = {21}
    assert svc.start_receipt_processing(21) is True
    assert done.wait(5)
    assert seen == [(21, 'receiving-process-21', True)]
    assert fakes.store.claims == [21]


def test_start_processing_not_claimed_no_thread(fakes, monkeypatch):
    spawned = []
    monkeypatch.setattr(svc, '_spawn', lambda *a: spawned.append(a))
    assert svc.start_receipt_processing(22) is False
    assert spawned == []


def test_start_processing_thread_failure_marks_error(fakes, monkeypatch):
    def broken_spawn(*args):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(svc, '_spawn', broken_spawn)
    fakes.store.claimable = {23}
    assert svc.start_receipt_processing(23) is False
    assert fakes.store.finished == [(23, 'error', 'Обработка не запустилась: Сбой: RuntimeError')]


def test_start_processing_claim_unavailable_propagates(fakes):
    fakes.store.fail_claim = fakes.store.ReceivingUnavailable('База приёмки недоступна: locked')
    with pytest.raises(fakes.store.ReceivingUnavailable):
        svc.start_receipt_processing(24)


def test_process_thread_body_survives_errors(fakes, monkeypatch):
    def boom(rid):
        raise RuntimeError('unexpected')

    monkeypatch.setattr(svc, 'process_receipt', boom)
    svc._process_safely(25)       # не бросает


def test_retry_stuck_processing(fakes, monkeypatch):
    spawned = []
    monkeypatch.setattr(svc, '_spawn', lambda target, name, *args: spawned.append((name, args)))
    fakes.store.needing = [1, 2, 3]
    fakes.store.claimable = {1, 3}
    assert svc.retry_stuck_processing() == [1, 3]
    assert spawned == [('receiving-process-1', (1,)), ('receiving-process-3', (3,))]
    assert fakes.store.claims == [1, 2, 3]


def test_retry_stuck_one_failure_does_not_stop_others(fakes, monkeypatch):
    spawned = []
    monkeypatch.setattr(svc, '_spawn', lambda target, name, *args: spawned.append(args[0]))
    real_claim = fakes.store.claim_processing

    def claim(rid, retry_error_now=False):
        if rid == 1:
            raise fakes.store.ReceivingUnavailable('База приёмки недоступна: locked')
        return real_claim(rid, retry_error_now=retry_error_now)

    fakes.store.claim_processing = claim
    fakes.store.needing = [1, 2]
    fakes.store.claimable = {2}
    assert svc.retry_stuck_processing() == [2]
    assert spawned == [2]


# ----------------------------------------------------------------- кнопка «Обновить из iiko»

@pytest.fixture
def iiko_creds(monkeypatch):
    """Креды iiko заданы — через настоящую проверку config (после фикстуры fakes)."""
    import config
    monkeypatch.setattr(svc, 'iiko_configured', REAL_IIKO_CONFIGURED)
    monkeypatch.setattr(config, 'IIKO_LOGIN', 'test-login', raising=False)
    monkeypatch.setattr(config, 'IIKO_PASSWORD', 'test-pass', raising=False)


def test_iiko_configured_reads_config(monkeypatch):
    import config
    monkeypatch.setattr(config, 'IIKO_LOGIN', 'login', raising=False)
    monkeypatch.setattr(config, 'IIKO_PASSWORD', 'pass', raising=False)
    assert REAL_IIKO_CONFIGURED() is True
    monkeypatch.setattr(config, 'IIKO_PASSWORD', '', raising=False)
    assert REAL_IIKO_CONFIGURED() is False
    monkeypatch.setattr(config, 'IIKO_LOGIN', None, raising=False)
    monkeypatch.setattr(config, 'IIKO_PASSWORD', 'pass', raising=False)
    assert REAL_IIKO_CONFIGURED() is False


def test_refresh_button_without_creds_503(fakes, monkeypatch):
    import config
    monkeypatch.setattr(svc, 'iiko_configured', REAL_IIKO_CONFIGURED)
    monkeypatch.setattr(config, 'IIKO_LOGIN', None, raising=False)
    monkeypatch.setattr(config, 'IIKO_PASSWORD', 'x', raising=False)
    assert svc.start_receiving_index_refresh() == (
        {'status': 'error', 'error': 'Не настроено подключение к iiko'}, 503)
    assert fakes.index.acquire_calls == []


def test_refresh_button_started_runs_refresh_with_lock(fakes, iiko_creds, monkeypatch):
    spawned = []

    def sync_spawn(target, name, *args):
        spawned.append(name)
        target(*args)

    monkeypatch.setattr(svc, '_spawn', sync_spawn)
    fakes.store.add_row(G_NEW_BARE, 'new')
    result = svc.start_receiving_index_refresh()
    assert result == ({'status': 'started'}, 202)
    assert fakes.index.acquire_calls == [0]                # кнопка не ждёт чужую пересборку
    assert spawned == ['receiving-index-button']
    call = fakes.index.refresh_calls[0]
    assert call['trigger'] == 'button' and call['lock'] is fakes.index.locks[0]
    assert fakes.index.locks[0].released == 1
    assert {r['gtin'] for r in fakes.store.reclassified} == {G_NEW_BARE}   # пересверка прошла
    assert call['after_save'] is True                      # быстрый проход — до «готово»


def test_refresh_button_real_thread(fakes, iiko_creds):
    done = threading.Event()
    real_refresh = fakes.index.refresh_index

    def refresh(trigger, **kwargs):
        try:
            return real_refresh(trigger, **kwargs)
        finally:
            done.set()

    fakes.index.refresh_index = refresh
    assert svc.start_receiving_index_refresh('button')[1] == 202
    assert done.wait(5)


def test_refresh_button_busy_409(fakes, iiko_creds, monkeypatch):
    spawned = []
    monkeypatch.setattr(svc, '_spawn', lambda *a: spawned.append(a))
    fakes.index.busy = True
    assert svc.start_receiving_index_refresh() == ({'status': 'already_running'}, 409)
    assert spawned == [] and fakes.index.refresh_calls == []


def test_refresh_button_thread_failure_releases_lock(fakes, iiko_creds, monkeypatch):
    def broken_spawn(*args):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(svc, '_spawn', broken_spawn)
    body, code = svc.start_receiving_index_refresh()
    assert code == 503 and body['status'] == 'error'
    assert fakes.index.locks[0].released == 1


def test_refresh_button_lock_file_error_503(fakes, iiko_creds):
    def broken_acquire(wait=0):
        raise PermissionError(13, 'Permission denied', '/app/data/.receiving_index_run.lock')

    fakes.index.acquire_run_lock = broken_acquire
    body, code = svc.start_receiving_index_refresh()
    assert code == 503 and body['status'] == 'error'
    assert '/app/data' not in body['error']


def test_refresh_background_failure_is_logged_not_raised(fakes):
    fakes.index.refresh_error = fakes.index.IndexSourceError('Нет связи с iiko (товары): ConnectTimeout')
    lock = FakeLock()
    svc._refresh_in_background('button', lock)   # не бросает
    assert lock.released == 1


def test_process_decision_newer_than_index_forces_refresh(fakes):
    """Ревью 2026-10-03: «Сделано» нажато после сборки индекса (индексу 2 минуты) —
    перед сверкой индекс пересобирается, иначе он не видит заведённую карточку."""
    fakes.store.lines[3] = _lines(G_NEW_BARE)
    fakes.store.add_row(G_NEW_BARE, 'new', state='closed', resolution='done',
                        resolved_at='2026-10-03T07:45:00+03:00')    # индекс — 07:30
    fakes.index.next_index = make_index(age=0, classes=dict(BASE_CLASSES, **{G_NEW_BARE: ('found', [CARD_A])}),
                                        built_at='2026-10-03T07:50:00+03:00')
    res = svc.process_receipt(3)
    assert [c['trigger'] for c in fakes.index.refresh_calls] == ['close']
    assert res['statuses'] == {'found': 1} and res['state'] == 'done'
    assert fakes.store.rows[G_NEW_BARE]['state'] == 'closed'


def test_process_notifies_rows_opened_by_failed_run(fakes):
    """Ревью 2026-10-03: прогон упал после открытия строк, но до сообщения — повтор дошлёт."""
    fakes.store.lines[4] = _lines(G_NEW_BARE)
    real_get = fakes.store.get_receipt
    calls = {'n': 0}

    def flaky_get(rid):
        calls['n'] += 1
        if calls['n'] == 1:
            raise fakes.store.ReceivingUnavailable('База приёмки недоступна: locked')
        return real_get(rid)

    fakes.store.get_receipt = flaky_get
    first = svc.process_receipt(4)
    assert first['opened'] == 1 and first['notified'] is False and fakes.notify.calls == []
    second = svc.process_receipt(4)                       # повтор обработки (шедулер или кнопка)
    assert second['opened'] == 0 and second['notified'] is True
    assert [r['gtin'] for r in fakes.notify.calls[0][1]] == [G_NEW_BARE]
    third = svc.process_receipt(4)                        # уже сообщили — второй раз не шлём
    assert third['notified'] is False and len(fakes.notify.calls) == 1


def test_reconcile_reopens_done_row_not_found_by_newer_index(fakes):
    fakes.index.index = make_index(classes=BASE_CLASSES, built_at='2026-10-03T12:00:00+03:00')
    fakes.store.add_row(G_NEW_BARE, 'new', state='closed', resolution='done',
                        resolved_at='2026-10-03T10:00:00+03:00')
    fakes.store.add_row(G_FOUND, 'new', state='closed', resolution='done',
                        resolved_at='2026-10-03T10:00:00+03:00')
    res = svc.reconcile_open_rows(fetch_chz=False)
    assert res['done_checked'] == 2 and res['done_reopened'] == 1
    assert fakes.store.rows[G_NEW_BARE]['state'] == 'open'        # «Сделано», а GTIN так и не появился
    assert fakes.store.rows[G_FOUND]['state'] == 'closed' and fakes.store.rows[G_FOUND]['status'] == 'found'
    assert fakes.chz.calls == []                                   # быстрый проход — без ЧЗ


def test_group_pack_points_to_unit_card(fakes):
    """Ревью 2026-10-03: код на плёнке мультипака — GTIN упаковки в iiko нет, но единица есть:
    «похожая» с карточкой единицы (пометка pack), а не «новая»."""
    g_pack = '04600000000073'
    fakes.store.lines[5] = _lines(g_pack)
    fakes.chz.names = {g_pack: {'name': 'Пиво Хеллес 6 банок', 'brand': '', 'level': 'inner-pack',
                                'main_gtin': G_FOUND, 'pack_units': '6'}}
    res = svc.process_receipt(5)
    assert res['statuses'] == {'similar': 1}
    up = _by_gtin(fakes.store.upserts)[g_pack]
    assert up['candidates'][0]['id'] == CARD_A['id']
    assert up['candidates'][0]['pack'] is True and up['candidates'][0]['pack_units'] == '6'
    assert up['candidates'][0]['unit_gtin'] == G_FOUND


# ----------------------------------------------------------------- run_index_refresh / пересверка

def test_run_index_refresh_reconciles(fakes):
    fakes.index.next_index = make_index(age=0, classes=dict(BASE_CLASSES, **{G_NEW_BARE: ('found', [CARD_A])}),
                                        built_at='2026-10-03T07:30:05+03:00')
    fakes.store.add_row(G_NEW_BARE, 'new')
    res = svc.run_index_refresh('schedule', wait=600)
    assert fakes.index.refresh_calls == [{'trigger': 'schedule', 'lock': None, 'wait': 600,
                                          'after_save': True}]
    assert res['index']['built_at'] == '2026-10-03T07:30:05+03:00'
    # Автозакрытие — в быстром проходе, ещё до отметки «готово» (ревью 2026-10-03).
    assert res['reconcile_fast'] == {'checked': 1, 'auto_closed': 1, 'changed': 1, 'done_checked': 0,
                                     'done_reopened': 0, 'chz_errors': []}
    assert res['reconcile'] == {'checked': 0, 'auto_closed': 0, 'changed': 0, 'done_checked': 0,
                                'done_reopened': 0, 'chz_errors': []}
    assert res['reconcile_error'] == ''
    assert fakes.store.rows[G_NEW_BARE]['state'] == 'closed'
    assert fakes.store.reclassified[0]['index_built_at'] == '2026-10-03T07:30:05+03:00'


def test_run_index_refresh_error_propagates_without_reconcile(fakes):
    fakes.index.refresh_error = fakes.index.IndexSourceError('iiko не пустил (HTTP 401)')
    fakes.store.add_row(G_NEW_BARE, 'new')
    with pytest.raises(fakes.index.IndexSourceError):
        svc.run_index_refresh('button')
    assert fakes.store.reclassified == []


def test_run_index_refresh_reconcile_failure_is_reported(fakes):
    def broken():
        raise fakes.store.ReceivingUnavailable('База приёмки недоступна: file is not a database')

    fakes.store.open_review_gtins = broken
    res = svc.run_index_refresh('schedule')
    assert res['reconcile'] is None
    assert res['reconcile_error'] == 'База приёмки недоступна: file is not a database'
    assert res['index'] is not None


def test_reconcile_auto_close_similar_upgrade_and_counts(fakes):
    g1, g2, g3, g4, g5, g6 = ('04610000000001', '04610000000002', '04610000000003',
                              '04610000000004', '04610000000005', '04610000000006')
    index = make_index(classes={g1: ('found', [CARD_A]), g4: ('restore', [CARD_DEL]),
                                g6: ('found', [CARD_B])},
                       similar={'Пиво Портер': [CAND], 'Квас': []})
    fakes.index.index = index
    fakes.store.add_row(g1, 'new')                                    # завели карточку -> auto
    fakes.store.add_row(g2, 'new')                                    # без названия ЧЗ -> similar
    fakes.store.add_row(g3, 'similar', candidates=[CAND], chz={'name': 'Квас'})  # кандидата больше нет
    fakes.store.add_row(g4, 'restore', cards=[CARD_DEL])              # без изменений
    fakes.store.add_row(g5, 'new', chz={'name': 'Неизвестное пиво'})  # название есть — ЧЗ не спрашиваем
    fakes.store.add_row(g6, 'duplicate', cards=[CARD_A, CARD_B])      # дубль убрали -> auto
    fakes.store.add_row('04610000000007', 'new', state='closed', resolution='done',   # закрытая после
                        resolved_at='2026-10-03T10:00:00+03:00')                    # индекса — не трогаем
    fakes.chz.names = {g2: {'name': 'Пиво Портер', 'brand': 'Бровари'}}
    fakes.chz.errors = ['Бар-ПК занят']

    res = svc.reconcile_open_rows()

    assert res == {'checked': 6, 'auto_closed': 2, 'changed': 4, 'done_checked': 1,
                   'done_reopened': 0, 'chz_errors': ['Бар-ПК занят']}
    assert fakes.chz.calls == [[g2]]
    rows = fakes.store.rows
    assert rows[g1]['state'] == 'closed' and rows[g1]['resolution'] == 'auto'
    assert rows[g6]['state'] == 'closed'
    assert rows[g2]['status'] == 'similar' and rows[g2]['candidates'] == [CAND]
    assert rows[g2]['chz']['name'] == 'Пиво Портер'
    assert rows[g3]['status'] == 'new' and rows[g3]['candidates'] == []
    assert rows[g4]['status'] == 'restore'
    assert rows[g5]['status'] == 'new'
    by = {r['gtin']: r for r in fakes.store.reclassified}
    assert by[g2]['chz']['name'] == 'Пиво Портер'          # свежий ответ ЧЗ сохраняется в строку
    assert by[g5]['chz'] is None                           # старое название не перезаписываем
    assert all(r['index_built_at'] == '2026-10-03T07:30:00+03:00' for r in fakes.store.reclassified)
    assert '04610000000007' not in by


def test_reconcile_without_index_does_nothing(fakes):
    fakes.index.index = None
    fakes.store.add_row(G_NEW_BARE, 'new')
    assert svc.reconcile_open_rows() == {'checked': 0, 'auto_closed': 0, 'changed': 0,
                                         'done_checked': 0, 'done_reopened': 0, 'chz_errors': []}
    assert fakes.store.reclassified == [] and fakes.chz.calls == []


def test_reconcile_skips_rows_gone_between_calls(fakes):
    fakes.store.add_row(G_NEW_BARE, 'new')
    fakes.store.open_review_gtins = lambda: [G_NEW_BARE, '04699999999999']
    res = svc.reconcile_open_rows()
    assert res['checked'] == 1


def test_reconcile_chz_crash_is_reported(fakes):
    fakes.store.add_row(G_NEW_BARE, 'new')
    fakes.chz.boom = RuntimeError('ssh password=xyz')
    res = svc.reconcile_open_rows()
    assert res['checked'] == 1
    assert res['chz_errors'] == ['Названия ЧЗ не получены: Сбой: RuntimeError']


def test_status(fakes):
    fakes.index.state['error'] = 'iiko ответил HTTP 500 (товары)'
    st = svc.status()
    assert st['index']['built_at'] == '2026-10-03T07:30:00+03:00'
    assert st['job']['error'] == 'iiko ответил HTTP 500 (товары)'
    fakes.index.index = None
    assert svc.status()['index'] is None


def test_py310_compatible_syntax():
    """CI и прод — Python 3.10: модуль должен разбираться грамматикой 3.10."""
    import ast
    src = open(svc.__file__, encoding='utf-8').read()
    ast.parse(src, feature_version=(3, 10))
    assert not re.search('[\U0001F000-\U0001FAFF☀-➿️•]', src)


# ----------------------------------------------------------------- сквозная проверка

def _gtin(body13: str) -> str:
    """GTIN-14 с верной контрольной цифрой GS1 (веса 3,1,3,... слева)."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(body13))
    return body13 + str((10 - total % 10) % 10)


@pytest.fixture
def real_modules(tmp_path, monkeypatch):
    """Настоящие store и index во временной папке; ЧЗ и Telegram — фейки."""
    from core import msk_time
    from core import receiving_index as ri
    from core import receiving_store as rst
    rst.set_db_path(str(tmp_path / 'receiving.db'))
    ri.set_paths(index=str(tmp_path / 'idx.json'), state=str(tmp_path / 'state.json'),
                 run_lock=str(tmp_path / 'run.lock'))
    chz = FakeChzModule()
    notify = FakeNotifyModule()
    monkeypatch.setattr(svc, 'receiving_chz', chz)
    monkeypatch.setattr(svc, 'receiving_notify', notify)
    now = datetime(2026, 10, 3, 14, 5, tzinfo=msk_time.MOSCOW_TZ)
    monkeypatch.setattr(msk_time, 'now', lambda: now)
    yield rst, ri, chz, notify
    rst.set_db_path(None)
    ri.set_paths()


def test_end_to_end_with_real_store_and_index(real_modules, monkeypatch):
    rst, ri, chz, notify = real_modules
    from core import receiving_codes
    g_found, g_del, g_dup, g_sim, g_new = (_gtin('0460000000011'), _gtin('0460000000022'),
                                           _gtin('0460000000033'), _gtin('0460000000044'),
                                           _gtin('0460000000055'))
    products = [
        {'id': 'p1', 'name': 'Пиво Хеллес светлое', 'type': 'GOODS', 'barcodes': [{'barcode': g_found}]},
        {'id': 'p2', 'name': 'Сидр Яблочный', 'type': 'GOODS', 'deleted': True,
         'barcodes': [{'barcode': g_del}]},
        {'id': 'p3', 'name': 'Лагер Один', 'type': 'GOODS', 'barcodes': [{'barcode': g_dup}]},
        {'id': 'p4', 'name': 'Лагер Два', 'type': 'GOODS', 'barcodes': [{'barcode': g_dup}]},
        {'id': 'p5', 'name': 'Портер Бровари Тёмный', 'type': 'GOODS', 'barcodes': []},
    ]
    sources = {'products': products, 'groups': [], 'categories': [], 'units': [], 'xml_barcodes': None}
    monkeypatch.setattr(ri, 'fetch_iiko_sources', lambda: sources)
    ri.refresh_index('test')
    assert ri.load_index() is not None

    user = {'login': 'ivan', 'display_name': 'Иван'}
    receipt = rst.create_receipt(user)
    rid = receipt['id']
    for n, gtin in enumerate([g_found, g_found, g_del, g_dup, g_sim, g_new]):
        raw = gtin[1:]                                   # EAN-13
        rst.add_scan(rid, receiving_codes.parse_code(raw), raw, 'client-%04d' % n, 'scanner', '', user)
    rst.close_receipt(rid, user)
    assert rst.claim_processing(rid) is True
    chz.names = {g_sim: {'name': 'Пиво Портер Бровари', 'brand': 'Бровари'},
                 g_new: {'name': 'Квас Живой', 'brand': ''}}

    res = svc.process_receipt(rid)

    assert res['state'] == 'done', res
    assert res['statuses'] == {'found': 1, 'restore': 1, 'duplicate': 1, 'similar': 1, 'new': 1}
    got = rst.get_receipt(rid)
    assert got['process_state'] == 'done' and got['process_note'] == ''
    rows = {r['gtin']: r for r in rst.list_review(state='all')['rows']}
    assert rows[g_found]['state'] == 'closed' and rows[g_found]['resolution'] == 'found'
    assert rows[g_found]['qty'] == 2
    assert rows[g_del]['status'] == 'restore' and rows[g_del]['cards'][0]['deleted'] is True
    assert rows[g_dup]['status'] == 'duplicate' and len(rows[g_dup]['cards']) == 2
    assert rows[g_sim]['status'] == 'similar' and rows[g_sim]['candidates'][0]['id'] == 'p5'
    assert rows[g_sim]['chz']['name'] == 'Пиво Портер Бровари'
    assert rows[g_new]['status'] == 'new' and rows[g_new]['state'] == 'open'
    assert len(notify.calls) == 1
    assert sorted(r['gtin'] for r in notify.calls[0][1]) == sorted([g_del, g_dup, g_sim, g_new])
    assert notify.calls[0][0]['id'] == rid

    # Бухгалтер завёл карточку «новой» позиции -> после пересборки строка закрылась сама
    products.append({'id': 'p6', 'name': 'Квас Живой', 'type': 'GOODS', 'barcodes': [{'barcode': g_new}]})
    summary = svc.run_index_refresh('button')
    assert summary['reconcile_fast']['auto_closed'] == 1, summary
    row = rst.get_review_item(g_new)
    assert row['state'] == 'closed' and row['resolution'] == 'auto'


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
