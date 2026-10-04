"""Тесты HTTP-слоя приёмки на РЦ (routes/receiving.py): страницы и /api/receiving/*.

Self-runnable: `py -3 tests/test_receiving_routes.py` (через pytest.main).

Приложение — голый Flask с одним blueprint'ом (app.py не импортируется). Хранилище
настоящее (core/receiving_store на временной receiving.db), фото — во временном
каталоге (receiving_photo_store.set_dir), индекс iiko — временные файлы
(receiving_index.set_paths) и собранный build_index без сети. Пользователь —
атрибут routes.receiving.current_user; запуск фоновой обработки и обновления
индекса (core/receiving_service) подменяется фейком — ни iiko, ни бар-ПК, ни
Telegram тест не трогает. Справочник поставщиков — временный файл (стартовый набор).

Что проверяется (контракт — раздел 7 спецификации, docs/receiving.md «API»):
- список приёмок (фильтр status, limit 1..200, 400 на кривое), создание (note до
  500 символов), одна приёмка (lines, recent, invoices, dm_keys только у открытой,
  rows разбора только у закрытой), 404;
- скан: DataMatrix принята -> повтор той же бутылки repeat («Уже посчитана»),
  EAN — штука на каждый скан, SSCC и битая контрольная — rejected с текстом для
  приёмщика; повтор client_id -> replayed, счётчики не растут; проверка полей
  (code, client_id 8..64 [A-Za-z0-9-], source, client_time) -> 400; закрытая
  приёмка -> 409 receipt_closed; подпись «кто» из current_user;
- отмена скана (повтор безопасен, чужой скан -> 404, закрытая -> 409);
- закрытие: started (202), pending / running без перезапуска (202), done (200,
  обработка не перезапускается), повтор закрытия безопасен, 404;
- фото накладной: загрузка (201, JPEG по сигнатуре), раздача с nosniff и
  приватным кэшем, 400 на не-JPEG и пустое, 413 до чтения тела и после, 404 на
  несуществующую приёмку, удаление записи и файла, осиротевший файл удаляется,
  если запись в БД не легла;
- разбор: фильтры state / status / receipt_id / q / limit (400 на кривые), counts,
  index и job, suppliers из справочника, последние закрытые приёмки;
- решение по строке: поставщик по справочнику (написание -> каноническое имя,
  чужое -> 400, '' — очистить), state done / not_needed / open, note до 500,
  400 без полей и на GTIN не из 14 цифр, 404 на неизвестный GTIN;
- поиск карточек: 503 index_missing без индекса, q от 2 символов, limit 1..100,
  поиск по названию и штрихкоду в собранном индексе;
- обновление индекса: коды 202 / 409 / 503 сервиса проходят как есть, триггер
  'button'; статус — index и job;
- нечитаемая receiving.db -> 503 receiving_unavailable, файл не меняется;
- страницы /receiving и /receiving/review рендерят свои шаблоны с app_version;
- гейт авторизации (настоящий init_auth): аноним на /api/receiving -> 401,
  на /receiving -> редирект на вход; после входа — 200;
- MCP-мост: скан и фото накладной через инструменты stocks_receiving_* доходят до
  маршрута (multipart-файл из base64), действия подписаны « · агент»;
- грамматика Python 3.10.
"""
import base64
import io
import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402

from core import auth_guard  # noqa: E402
from core import receiving_codes  # noqa: E402
from core import receiving_index  # noqa: E402
from core import receiving_photo_store  # noqa: E402
from core import receiving_store  # noqa: E402
from core.supplier_directory import SupplierDirectory  # noqa: E402
import routes.receiving as rr  # noqa: E402
from routes.receiving import receiving_bp  # noqa: E402

USER = {'login': 'ivan', 'display_name': 'Иван'}
JPEG = b'\xff\xd8\xff\xe0' + b'\x00\x10JFIF' + b'0' * 200
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 200
GS = '\x1d'


def _gtin(base13: str) -> str:
    """GTIN-14 с верной контрольной цифрой GS1 (веса 3, 1, 3, … справа налево)."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(base13)))
    return base13 + str((10 - total % 10) % 10)


GTIN_A = _gtin('0461009362843')     # 04610093628430 — EAN-13 4610093628430
GTIN_B = _gtin('0460000000001')
GTIN_C = _gtin('0460123456789')
EAN_A = GTIN_A[1:]                  # EAN-13 того же товара (GTIN без ведущего нуля)
EAN_B = GTIN_B[1:]
SSCC = '00146012340000000018'


def _dm(gtin: str, serial: str) -> str:
    """DataMatrix пива: 01 + GTIN + 21 + серийник + GS + 93 + криптохвост."""
    return '01' + gtin + '21' + serial + GS + '93' + 'dGVz'


# --------------------------------------------------------------------------- окружение

class FakeService:
    """Подмена core.receiving_service: без потоков, iiko, бар-ПК и Telegram."""

    def __init__(self):
        self.processing_calls = []
        self.processing_result = True
        self.claim = False              # True — «взять» обработку в хранилище, как настоящий
        self.refresh_calls = []
        self.refresh_result = ({'status': 'started'}, 202)

    def start_receipt_processing(self, receipt_id, retry_error_now=False):
        self.processing_calls.append(receipt_id)
        self.retry_error_now = retry_error_now
        if self.claim:
            return receiving_store.claim_processing(receipt_id, retry_error_now=retry_error_now)
        return self.processing_result

    def start_receiving_index_refresh(self, trigger='button'):
        self.refresh_calls.append(trigger)
        return self.refresh_result

    def status(self):
        return {'index': receiving_index.index_info(receiving_index.load_index()),
                'job': receiving_index.read_state()}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Клиент + временные БД, фото, индекс, справочник; фейковый сервис."""
    receiving_store.set_db_path(str(tmp_path / 'receiving.db'))
    receiving_photo_store.set_dir(str(tmp_path / 'photos'))
    receiving_index.set_paths(index=str(tmp_path / 'receiving_index.json'),
                              state=str(tmp_path / 'receiving_index_state.json'),
                              run_lock=str(tmp_path / '.receiving_index_run.lock'))
    directory = SupplierDirectory(str(tmp_path / 'suppliers.json'))      # стартовый набор
    service = FakeService()
    monkeypatch.setattr(rr, 'receiving_service', service)
    monkeypatch.setattr(rr, 'current_user', lambda: USER)
    monkeypatch.setattr(rr, 'get_supplier_directory', lambda: directory)
    monkeypatch.setattr(rr, '_app_version', lambda: 'test-ver')

    templates = tmp_path / 'templates'
    templates.mkdir()
    (templates / 'receiving.html').write_text('scan page v={{ app_version }}', encoding='utf-8')
    (templates / 'receiving_review.html').write_text('review page v={{ app_version }}', encoding='utf-8')
    app = Flask('test_receiving', template_folder=str(templates))
    app.register_blueprint(receiving_bp)
    try:
        yield types.SimpleNamespace(client=app.test_client(), app=app, service=service,
                                    directory=directory, tmp=tmp_path)
    finally:
        receiving_store.set_db_path(None)
        receiving_photo_store.set_dir(None)
        receiving_index.set_paths()


def _new_receipt(c, note=None) -> int:
    r = c.post('/api/receiving', json={} if note is None else {'note': note})
    assert r.status_code == 201, r.get_json()
    return r.get_json()['receipt']['id']


_seq = [0]


def _scan(c, rid, code, client_id=None, **extra):
    if client_id is None:
        _seq[0] += 1
        client_id = 'test-scan-%08d' % _seq[0]
    body = dict({'code': code, 'client_id': client_id}, **extra)
    r = c.post('/api/receiving/%d/scan' % rid, json=body)
    return r.status_code, r.get_json()


def _upload(c, rid, data, field='photo'):
    payload = {field: (io.BytesIO(data), 'upd.jpg')}
    r = c.post('/api/receiving/%d/invoice' % rid, data=payload, content_type='multipart/form-data')
    return r.status_code, r.get_json()


def _photos(env) -> list:
    path = env.tmp / 'photos'
    return sorted(os.listdir(path)) if path.exists() else []


# --------------------------------------------------------------------------- приёмки

def test_create_list_and_get(env):
    c = env.client
    r = c.post('/api/receiving', json={'note': '  Машина МаркетБир  '})
    assert r.status_code == 201
    receipt = r.get_json()['receipt']
    assert receipt['status'] == 'open' and receipt['note'] == 'Машина МаркетБир'
    assert receipt['created_by'] == 'Иван'
    assert receipt['counts'] == {'units': 0, 'gtins': 0, 'rejected': 0, 'repeats': 0, 'invoices': 0}
    second = _new_receipt(c)

    data = c.get('/api/receiving').get_json()
    assert [x['id'] for x in data['receipts']] == [second, receipt['id']]      # новые сверху
    assert [x['id'] for x in c.get('/api/receiving?status=open').get_json()['receipts']] == \
        [second, receipt['id']]
    assert c.get('/api/receiving?status=closed').get_json()['receipts'] == []
    assert len(c.get('/api/receiving?status=all&limit=1').get_json()['receipts']) == 1

    got = c.get('/api/receiving/%d' % receipt['id']).get_json()
    assert set(got) == {'receipt', 'lines', 'recent', 'invoices', 'dm_keys', 'rows'}
    assert got['receipt']['id'] == receipt['id']
    assert got['lines'] == [] and got['recent'] == [] and got['invoices'] == []
    assert got['dm_keys'] == [] and got['rows'] == []


@pytest.mark.parametrize('query', ['status=done', 'status=OPEN', 'limit=0', 'limit=201',
                                   'limit=abc', 'limit=-5'])
def test_list_rejects_bad_filters(env, query):
    r = env.client.get('/api/receiving?' + query)
    assert r.status_code == 400 and r.get_json()['error']


def test_create_validates_note(env):
    c = env.client
    assert c.post('/api/receiving', json={'note': 5}).status_code == 400
    assert c.post('/api/receiving', json={'note': 'x' * 501}).status_code == 400
    assert c.post('/api/receiving', json={'note': 'x' * 500}).status_code == 201
    # не объект JSON — как пустое тело: приёмка без заметки
    r = c.post('/api/receiving', data='[]', content_type='application/json')
    assert r.status_code == 201 and r.get_json()['receipt']['note'] == ''
    assert c.get('/api/receiving').get_json()['receipts'][0]['note'] == ''


def test_get_unknown_receipt_404(env):
    r = env.client.get('/api/receiving/999')
    assert r.status_code == 404 and r.get_json()['error'] == 'Приёмка не найдена'


# --------------------------------------------------------------------------- сканы

def test_scan_results_and_counts(env):
    c = env.client
    rid = _new_receipt(c)
    dm = _dm(GTIN_A, 'ABCdef1234567')
    assert receiving_codes.parse_code(dm)['kind'] == 'datamatrix'

    code, body = _scan(c, rid, dm)
    assert code == 200
    assert body['result'] == 'accepted' and body['kind'] == 'datamatrix' and body['gtin'] == GTIN_A
    assert body['message'] == 'Принято' and body['replayed'] is False and body['scan_id'] > 0
    assert set(body) == {'result', 'kind', 'gtin', 'message', 'scan_id', 'replayed', 'counts'}

    code, body = _scan(c, rid, dm)                         # та же бутылка — новый client_id
    assert code == 200 and body['result'] == 'repeat' and body['message'] == 'Уже посчитана'

    for _ in range(2):                                     # EAN — каждый скан ещё штука
        code, body = _scan(c, rid, EAN_B)
        assert body['result'] == 'accepted' and body['kind'] == 'ean' and body['gtin'] == GTIN_B

    code, body = _scan(c, rid, SSCC)
    assert body['result'] == 'rejected' and body['kind'] == 'sscc'
    assert body['message'] == receiving_codes.MSG_SSCC and body['gtin'] is None

    broken = EAN_A[:-1] + str((int(EAN_A[-1]) + 1) % 10)
    code, body = _scan(c, rid, broken)
    assert body['result'] == 'rejected' and body['message'] == receiving_codes.MSG_BAD_CHECK

    code, body = _scan(c, rid, 'https://example.com/qr')
    assert body['result'] == 'rejected' and body['message'] == receiving_codes.MSG_UNREADABLE

    assert body['counts'] == {'units': 3, 'gtins': 2, 'rejected': 3, 'repeats': 1, 'invoices': 0}
    got = c.get('/api/receiving/%d' % rid).get_json()
    assert got['lines'] == [{'gtin': GTIN_B, 'qty': 2, 'kind': 'ean'},
                            {'gtin': GTIN_A, 'qty': 1, 'kind': 'datamatrix'}]
    assert got['dm_keys'] == [GTIN_A + '|ABCdef1234567']
    assert len(got['recent']) == 7 and got['recent'][0]['by'] == 'Иван'
    assert '\x1d' not in json.dumps(got['recent'])         # GS в raw_short заменён пробелом


def test_scan_replay_same_client_id(env):
    c = env.client
    rid = _new_receipt(c)
    code, first = _scan(c, rid, EAN_A, client_id='0f8e7d6c-1a2b-4c3d-9e8f-0123456789ab',
                        source='camera', client_time='2026-10-03T14:05:00+03:00')
    assert code == 200 and first['replayed'] is False
    code, again = _scan(c, rid, EAN_A, client_id='0f8e7d6c-1a2b-4c3d-9e8f-0123456789ab')
    assert code == 200 and again['replayed'] is True
    assert again['scan_id'] == first['scan_id'] and again['result'] == 'accepted'
    assert again['counts']['units'] == 1
    recent = c.get('/api/receiving/%d' % rid).get_json()['recent']
    assert len(recent) == 1 and recent[0]['source'] == 'camera'


def test_scan_replay_of_rejected_keeps_message(env):
    c = env.client
    rid = _new_receipt(c)
    _code, first = _scan(c, rid, SSCC, client_id='replay-rejected-1')
    _code, again = _scan(c, rid, SSCC, client_id='replay-rejected-1')
    assert again['replayed'] is True and again['result'] == 'rejected'
    assert again['message'] == first['message'] == receiving_codes.MSG_SSCC


@pytest.mark.parametrize('body', [
    {'client_id': 'abcdefgh-1234'},                                    # нет code
    {'code': 4610093628430, 'client_id': 'abcdefgh-1234'},             # code не строка
    {'code': '4610093628430'},                                         # нет client_id
    {'code': '4610093628430', 'client_id': 'short'},                   # короче 8
    {'code': '4610093628430', 'client_id': 'a' * 65},                  # длиннее 64
    {'code': '4610093628430', 'client_id': 'abc_defgh'},               # недопустимый символ
    {'code': '4610093628430', 'client_id': 'abcdefgh-1234\n'},         # перевод строки в конце
    {'code': '4610093628430', 'client_id': 12345678},
    {'code': '4610093628430', 'client_id': 'abcdefgh-1234', 'source': 'phone'},
    {'code': '4610093628430', 'client_id': 'abcdefgh-1234', 'client_time': 'x' * 41},
    {'code': '4610093628430', 'client_id': 'abcdefgh-1234', 'client_time': 1700000000},
])
def test_scan_validation_400(env, body):
    c = env.client
    rid = _new_receipt(c)
    r = c.post('/api/receiving/%d/scan' % rid, json=body)
    assert r.status_code == 400 and r.get_json()['error']
    assert c.get('/api/receiving/%d' % rid).get_json()['recent'] == []       # ничего не записано


def test_scan_unknown_receipt_404(env):
    code, body = _scan(env.client, 4242, EAN_A)
    assert code == 404 and body['error'] == 'Приёмка не найдена'


def test_scan_closed_receipt_409(env):
    c = env.client
    rid = _new_receipt(c)
    _scan(c, rid, EAN_A, client_id='before-close-1')
    assert c.post('/api/receiving/%d/close' % rid).status_code == 202
    code, body = _scan(c, rid, EAN_A)
    assert code == 409 and body['code'] == 'receipt_closed'
    # повтор скана, записанного до закрытия, — тот же ответ (очередь браузера)
    code, body = _scan(c, rid, EAN_A, client_id='before-close-1')
    assert code == 200 and body['replayed'] is True


def test_scan_signed_by_agent_via_mcp(env, monkeypatch):
    monkeypatch.setattr(rr, 'current_user',
                        lambda: {'login': 'owner', 'display_name': 'Владелец', 'via_mcp': True})
    c = env.client
    rid = _new_receipt(c)
    _scan(c, rid, EAN_A)
    got = c.get('/api/receiving/%d' % rid).get_json()
    assert got['receipt']['created_by'] == 'Владелец · агент'
    assert got['recent'][0]['by'] == 'Владелец · агент'


def test_scan_delete(env):
    c = env.client
    rid = _new_receipt(c)
    _code, first = _scan(c, rid, EAN_A)
    _scan(c, rid, EAN_A)
    r = c.delete('/api/receiving/%d/scans/%d' % (rid, first['scan_id']))
    assert r.status_code == 200
    body = r.get_json()
    assert body['deleted'] is True and body['counts']['units'] == 1
    again = c.delete('/api/receiving/%d/scans/%d' % (rid, first['scan_id']))
    assert again.status_code == 200 and again.get_json()['counts']['units'] == 1     # повтор безопасен
    assert c.delete('/api/receiving/%d/scans/99999' % rid).status_code == 404

    other = _new_receipt(c)
    r = c.delete('/api/receiving/%d/scans/%d' % (other, first['scan_id']))
    assert r.status_code == 404 and r.get_json()['error'] == 'Скан не найден'
    assert c.delete('/api/receiving/777/scans/1').status_code == 404

    c.post('/api/receiving/%d/close' % rid)
    last = c.get('/api/receiving/%d' % rid).get_json()['recent'][0]
    r = c.delete('/api/receiving/%d/scans/%d' % (rid, last['id']))
    assert r.status_code == 409 and r.get_json()['code'] == 'receipt_closed'


# --------------------------------------------------------------------------- закрытие

def test_close_starts_processing_then_done_is_not_restarted(env):
    c = env.client
    svc = env.service
    rid = _new_receipt(c)
    _scan(c, rid, EAN_A)

    svc.claim = True
    r = c.post('/api/receiving/%d/close' % rid)
    assert r.status_code == 202
    body = r.get_json()
    assert body['processing'] == 'started'
    assert body['receipt']['status'] == 'closed' and body['receipt']['closed_by'] == 'Иван'
    assert body['receipt']['process_state'] == 'running'
    assert svc.processing_calls == [rid]

    r = c.post('/api/receiving/%d/close' % rid)          # обработка идёт — не перезапускаем
    assert r.status_code == 202 and r.get_json()['processing'] == 'running'

    receiving_store.finish_processing(rid, 'done', 'ok')
    r = c.post('/api/receiving/%d/close' % rid)
    assert r.status_code == 200
    assert r.get_json()['processing'] == 'done' and r.get_json()['receipt']['process_note'] == 'ok'
    assert svc.processing_calls == [rid, rid]            # done — сервис даже не зовём


def test_close_not_taken_reports_state(env):
    c = env.client
    svc = env.service
    rid = _new_receipt(c)
    svc.processing_result = False                        # обработку не взяли (другой воркер)
    r = c.post('/api/receiving/%d/close' % rid)
    assert r.status_code == 202 and r.get_json()['processing'] == 'pending'
    receiving_store.claim_processing(rid)
    receiving_store.finish_processing(rid, 'error', 'Нет индекса iiko: нет связи')
    r = c.post('/api/receiving/%d/close' % rid)
    body = r.get_json()
    assert r.status_code == 202 and body['processing'] == 'error'
    assert body['receipt']['process_note'] == 'Нет индекса iiko: нет связи'
    assert svc.retry_error_now is True                   # повтор человеком — без часового окна


def test_close_again_restarts_failed_processing_at_once(env):
    c = env.client
    svc = env.service
    rid = _new_receipt(c)
    _scan(c, rid, EAN_A)
    svc.claim = True
    assert c.post('/api/receiving/%d/close' % rid).get_json()['processing'] == 'started'
    receiving_store.finish_processing(rid, 'error', 'Нет индекса iiko: нет связи')
    r = c.post('/api/receiving/%d/close' % rid)          # «Завершить» ещё раз сразу после сбоя
    assert r.status_code == 202 and r.get_json()['processing'] == 'started'
    assert r.get_json()['receipt']['process_state'] == 'running'


def test_invoice_upload_without_content_length_411(env):
    """Ревью 2026-10-03: тело частями (chunked) без длины не читается целиком в память."""
    c = env.client
    rid = _new_receipt(c)
    body = (b'--B\r\nContent-Disposition: form-data; name="photo"; filename="p.jpg"\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + JPEG + b'\r\n--B--\r\n')
    r = c.post('/api/receiving/%d/invoice' % rid, input_stream=io.BytesIO(body),
               headers={'Content-Type': 'multipart/form-data; boundary=B',
                        'Transfer-Encoding': 'chunked'})
    assert r.status_code == 411
    assert c.get('/api/receiving/%d' % rid).get_json()['invoices'] == []


def test_huge_ids_are_404_not_500(env):
    c = env.client
    assert c.get('/api/receiving/99999999999999999999').status_code == 404
    rid = _new_receipt(c)
    r = c.delete('/api/receiving/%d/scans/99999999999999999999' % rid)
    assert r.status_code == 404


def test_close_unknown_receipt_404(env):
    assert env.client.post('/api/receiving/31337/close').status_code == 404
    assert env.service.processing_calls == []


# --------------------------------------------------------------------------- фото накладных

def test_invoice_upload_serve_delete(env):
    c = env.client
    rid = _new_receipt(c)
    code, body = _upload(c, rid, JPEG)
    assert code == 201, body
    invoice = body['invoice']
    assert receiving_photo_store.is_valid_name(invoice['name'])
    assert invoice['url'] == '/api/receiving/invoice/' + invoice['name']
    assert invoice['size'] == len(JPEG) and invoice['uploaded_by'] == 'Иван'
    assert body['invoices'] == [invoice]
    assert _photos(env) == [invoice['name']]
    assert c.get('/api/receiving/%d' % rid).get_json()['receipt']['counts']['invoices'] == 1

    r = c.get(invoice['url'])
    assert r.status_code == 200 and r.mimetype == 'image/jpeg' and r.data == JPEG
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['Cache-Control'] == 'private, max-age=86400'
    assert c.get('/api/receiving/invoice/r1_20261003T140500_0123abcd.jpg').status_code == 404
    assert c.get('/api/receiving/invoice/receiving.db').status_code == 404
    assert c.get('/api/receiving/invoice/..%2Freceiving.db').status_code == 404

    r = c.delete('/api/receiving/%d/invoice/%s' % (rid, invoice['name']))
    assert r.status_code == 200 and r.get_json() == {'deleted': True, 'invoices': []}
    assert _photos(env) == []
    r = c.delete('/api/receiving/%d/invoice/%s' % (rid, invoice['name']))
    assert r.status_code == 404 and r.get_json()['error'] == 'Фото не найдено'
    r = c.delete('/api/receiving/555/invoice/%s' % invoice['name'])
    assert r.status_code == 404 and r.get_json()['error'] == 'Приёмка не найдена'
    assert c.delete('/api/receiving/%d/invoice/notaphoto.jpg' % rid).status_code == 404


def test_invoice_of_other_receipt_is_not_deleted(env):
    c = env.client
    rid, other = _new_receipt(c), _new_receipt(c)
    _code, body = _upload(c, rid, JPEG)
    name = body['invoice']['name']
    assert c.delete('/api/receiving/%d/invoice/%s' % (other, name)).status_code == 404
    assert _photos(env) == [name]


def test_invoice_allowed_on_closed_receipt(env):
    c = env.client
    rid = _new_receipt(c)
    c.post('/api/receiving/%d/close' % rid)
    code, body = _upload(c, rid, JPEG)
    assert code == 201 and len(body['invoices']) == 1


def test_invoice_rejects_bad_files(env):
    c = env.client
    rid = _new_receipt(c)
    code, body = _upload(c, rid, PNG)
    assert code == 400 and 'JPEG' in body['error']
    code, body = _upload(c, rid, b'')
    assert code == 400
    r = c.post('/api/receiving/%d/invoice' % rid, data={}, content_type='multipart/form-data')
    assert r.status_code == 400
    code, body = _upload(c, rid, JPEG, field='file')                 # не то поле
    assert code == 400
    code, body = _upload(c, 9090, JPEG)
    assert code == 404
    assert _photos(env) == []


def test_invoice_too_big_413(env, monkeypatch):
    c = env.client
    rid = _new_receipt(c)
    monkeypatch.setattr(receiving_photo_store, 'MAX_PHOTO_BYTES', 100)
    # тело больше предела + запас на заголовки — отказ ДО чтения формы
    code, body = _upload(c, rid, JPEG + b'0' * (rr.UPLOAD_OVERHEAD_BYTES + 200))
    assert code == 413 and 'МБ' in body['error']
    # тело в пределах запаса, но сам файл больше предела
    code, body = _upload(c, rid, JPEG)
    assert code == 413
    assert _photos(env) == []


def test_invoice_file_removed_when_db_write_fails(env, monkeypatch):
    c = env.client
    rid = _new_receipt(c)

    def broken(*_a, **_k):
        raise receiving_store.ReceivingUnavailable('База приёмки недоступна: disk I/O error')
    monkeypatch.setattr(receiving_store, 'add_invoice', broken)
    code, body = _upload(c, rid, JPEG)
    assert code == 503 and body['code'] == 'receiving_unavailable'
    assert _photos(env) == []


def test_invoice_save_failure_500(env, monkeypatch):
    c = env.client
    rid = _new_receipt(c)
    monkeypatch.setattr(receiving_photo_store, 'save',
                        lambda data, receipt_id: (False, 'Фото не сохранилось: No space'))
    code, body = _upload(c, rid, JPEG)
    assert code == 500 and body['error'] == 'Фото не сохранилось: No space'
    assert c.get('/api/receiving/%d' % rid).get_json()['invoices'] == []


# --------------------------------------------------------------------------- разбор

def _seed_review(c):
    """Две закрытые приёмки и строки разбора: A new (обе приёмки), B similar, C found."""
    first = _new_receipt(c)
    _scan(c, first, EAN_A)
    _scan(c, first, EAN_A)
    _scan(c, first, EAN_B)
    c.post('/api/receiving/%d/close' % first)
    second = _new_receipt(c)
    _scan(c, second, EAN_A)
    _scan(c, second, _dm(GTIN_C, 'serial0000001'))
    c.post('/api/receiving/%d/close' % second)
    card = {'id': 'c1', 'name': 'Жигули Барное', 'num': '00123', 'group': 'Пиво / Фасовка',
            'supplier': 'ООО МаркетБир', 'unit': 'шт', 'deleted': False, 'archived': False, 'keg': False}
    receiving_store.upsert_review(GTIN_A, first, 'new', [], [], {'name': 'Пиво Тестовое Светлое',
                                                                  'brand': 'Тест', 'source': 'cache'},
                                  '2026-10-03T07:30:00+03:00')
    receiving_store.upsert_review(GTIN_B, first, 'similar', [], [dict(card, score=2)],
                                  {'name': 'Жигули Барное Новое'}, '2026-10-03T07:30:00+03:00')
    receiving_store.upsert_review(GTIN_C, second, 'found', [card], [], {}, '2026-10-03T07:30:00+03:00')
    return first, second


def test_review_default_and_shape(env):
    c = env.client
    first, second = _seed_review(c)
    r = c.get('/api/receiving/review')
    assert r.status_code == 200
    data = r.get_json()
    assert set(data) == {'rows', 'total', 'counts', 'index', 'job', 'suppliers', 'receipts'}
    assert [row['gtin'] for row in data['rows']] == [GTIN_A, GTIN_B]       # open: new, затем similar
    assert data['total'] == 2
    assert data['counts'] == {'open': {'new': 1, 'similar': 1, 'restore': 0, 'duplicate': 0},
                              'open_total': 2, 'closed_total': 1}
    row = data['rows'][0]
    assert row['barcode'] == EAN_A and row['qty'] == 3
    assert [x['id'] for x in row['receipts']] == [second, first]
    assert data['index'] is None
    assert data['job']['running'] is False
    assert 'ООО МаркетБир' in data['suppliers'] and data['suppliers'] == \
        [rec['name'] for rec in env.directory.list()]
    assert [x['id'] for x in data['receipts']] == [second, first]
    assert all(x['status'] == 'closed' for x in data['receipts'])


def test_review_filters(env):
    c = env.client
    first, second = _seed_review(c)

    def gtins(query):
        r = c.get('/api/receiving/review?' + query)
        assert r.status_code == 200, r.get_json()
        return [row['gtin'] for row in r.get_json()['rows']]

    assert gtins('status=new') == [GTIN_A]
    assert gtins('status=similar,new') == [GTIN_A, GTIN_B]
    assert gtins('state=closed') == [GTIN_C]
    assert gtins('state=all') == [GTIN_A, GTIN_B, GTIN_C]
    assert gtins('state=all&receipt_id=%d' % second) == [GTIN_A, GTIN_C]
    assert gtins('state=all&receipt_id=%d' % first) == [GTIN_A, GTIN_B]
    assert gtins('state=all&receipt_id=%d,%d' % (first, second)) == [GTIN_A, GTIN_B, GTIN_C]
    assert gtins('state=all&receipt_id=%d,%d' % (second, second)) == [GTIN_A, GTIN_C]
    assert gtins('q=' + 'жигули') == [GTIN_B]                # имя кандидата, регистр не важен
    assert gtins('q=' + EAN_A[:7]) == [GTIN_A]
    assert gtins('state=all&q=маркетбир') == []               # поставщик карточки в q не ищется
    r = c.get('/api/receiving/review?state=all&limit=1')
    assert r.get_json()['total'] == 3 and len(r.get_json()['rows']) == 1


@pytest.mark.parametrize('query', ['state=done', 'status=open', 'status=new,bogus', 'receipt_id=abc',
                                   'receipt_id=-1', 'receipt_id=1234567890', 'receipt_id=0',
                                   'receipt_id=1,', 'receipt_id=1,x', 'receipt_id=1;2',
                                   'receipt_id=' + ','.join(str(n) for n in range(1, 52)),
                                   'limit=0', 'limit=1001', 'q=' + 'x' * 201])
def test_review_rejects_bad_filters(env, query):
    r = env.client.get('/api/receiving/review?' + query)
    assert r.status_code == 400 and r.get_json()['error']


def test_review_receipts_pending_recent_and_selected(env):
    c = env.client
    first, second = _seed_review(c)
    for rid in (first, second):
        receiving_store.claim_processing(rid)
        receiving_store.finish_processing(rid, 'done')
    scanning = _new_receipt(c)
    _scan(c, scanning, EAN_B)
    data = c.get('/api/receiving/review').get_json()
    assert [x['id'] for x in data['receipts']] == [second, first]          # открытая не в списке
    by_id = {x['id']: x for x in data['receipts']}
    assert by_id[first]['review'] == {'open': 2, 'closed': 0, 'missing': 0}   # A и B ждут разбора
    assert by_id[second]['review'] == {'open': 1, 'closed': 1, 'missing': 0}  # A общая, C есть в iiko
    assert by_id[first]['can_delete'] and not by_id[first]['reviewed']
    data = c.get('/api/receiving/review?receipt_id=%d' % scanning).get_json()
    assert [x['id'] for x in data['receipts']] == [scanning, second, first]   # выбранная — тоже
    assert data['receipts'][0]['review'] is None and data['receipts'][0]['can_delete'] is False


def test_delete_receipt_route(env):
    c = env.client
    first, second = _seed_review(c)
    code, body = _upload(c, first, JPEG)
    assert code == 201
    photo = body['invoice']['name']
    assert receiving_photo_store.exists(photo)

    r = c.delete('/api/receiving/%d' % first)
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data['deleted'] is True and data['receipt']['id'] == first
    assert (data['rows_deleted'], data['rows_kept'], data['invoices_deleted']) == (1, 1, 1)
    assert not receiving_photo_store.exists(photo)                        # файл фото удалён
    assert c.get('/api/receiving/%d' % first).status_code == 404
    rows = {row['gtin']: row for row in c.get('/api/receiving/review?state=all').get_json()['rows']}
    assert set(rows) == {GTIN_A, GTIN_C}                                  # B была только в первой
    assert rows[GTIN_A]['qty'] == 1 and [x['id'] for x in rows[GTIN_A]['receipts']] == [second]

    r = c.delete('/api/receiving/%d' % first)                             # повтор — уже нет
    assert r.status_code == 404 and r.get_json()['error'] == 'Приёмка не найдена'


def test_delete_receipt_route_refuses_open_and_reviewed(env):
    c = env.client
    scanning = _new_receipt(c)
    _scan(c, scanning, EAN_A)
    r = c.delete('/api/receiving/%d' % scanning)
    assert r.status_code == 409 and r.get_json()['code'] == 'receipt_open'
    done = _new_receipt(c)
    _scan(c, done, EAN_B)
    c.post('/api/receiving/%d/close' % done)
    receiving_store.upsert_review(GTIN_B, done, 'found', [], [], {}, '2026-10-03T07:30:00+03:00')
    receiving_store.claim_processing(done)
    receiving_store.finish_processing(done, 'done')
    r = c.delete('/api/receiving/%d' % done)
    assert r.status_code == 409 and r.get_json()['code'] == 'receipt_reviewed'
    assert r.get_json()['error'] == 'Приёмка разобрана полностью — она остаётся в истории'
    assert c.get('/api/receiving/%d' % done).status_code == 200
    assert c.get('/api/receiving/%d' % scanning).get_json()['receipt']['status'] == 'open'


def test_review_includes_index_info(env):
    index = receiving_index.build_index(
        [{'id': 'p1', 'name': 'Тест Лагер', 'type': 'GOODS', 'barcodes': [{'barcode': EAN_A}]}], [],
        built_at='2026-10-03T07:30:00+03:00')
    receiving_index.save_index(index)
    data = env.client.get('/api/receiving/review').get_json()
    assert data['index']['built_at'] == '2026-10-03T07:30:00+03:00'
    assert data['index']['counts']['products'] == 1


def test_get_closed_receipt_has_rows_not_dm_keys(env):
    c = env.client
    first, second = _seed_review(c)
    got = c.get('/api/receiving/%d' % second).get_json()
    assert got['dm_keys'] == []
    assert [row['gtin'] for row in got['rows']] == [GTIN_A, GTIN_C]       # и закрытая found тоже
    open_rid = _new_receipt(c)
    _scan(c, open_rid, _dm(GTIN_A, 'xyzSERIAL0001'))
    got = c.get('/api/receiving/%d' % open_rid).get_json()
    assert got['rows'] == [] and got['dm_keys'] == [GTIN_A + '|xyzSERIAL0001']


def test_review_update(env, monkeypatch):
    c = env.client
    _seed_review(c)
    url = '/api/receiving/review/' + GTIN_A

    r = c.put(url, json={'supplier': '  маркет   бир '})            # написание -> каноническое имя
    assert r.status_code == 200
    row = r.get_json()['row']
    assert row['supplier'] == 'ООО МаркетБир' and row['updated_by'] == 'Иван' and row['state'] == 'open'

    r = c.put(url, json={'supplier': 'ООО Ромашка'})
    assert r.status_code == 400 and r.get_json()['error'] == 'Поставщика нет в справочнике'
    assert c.put(url, json={'supplier': ''}).get_json()['row']['supplier'] == ''

    r = c.put(url, json={'state': 'done', 'note': '  завели карточку  '})
    row = r.get_json()['row']
    assert row['state'] == 'closed' and row['resolution'] == 'done'
    assert row['resolved_by'] == 'Иван' and row['note'] == 'завели карточку'

    row = c.put(url, json={'state': 'open'}).get_json()['row']
    assert row['state'] == 'open' and row['resolution'] == '' and row['resolved_by'] == ''
    row = c.put(url, json={'state': 'not_needed'}).get_json()['row']
    assert row['resolution'] == 'not_needed'
    assert c.put(url, json={'note': ''}).get_json()['row']['note'] == ''

    monkeypatch.setattr(rr, 'current_user',
                        lambda: {'login': 'owner', 'display_name': 'Владелец', 'via_mcp': True})
    row = c.put(url, json={'note': 'проверил агент'}).get_json()['row']
    assert row['updated_by'] == 'Владелец · агент'


@pytest.mark.parametrize('gtin,body,status', [
    (GTIN_A, {}, 400),                                    # нечего менять
    (GTIN_A, {'other': 1}, 400),
    (GTIN_A, {'state': 'closed'}, 400),
    (GTIN_A, {'state': 'auto'}, 400),                     # автозакрытие — только индексом
    (GTIN_A, {'supplier': 7}, 400),
    (GTIN_A, {'note': 'x' * 501}, 400),
    (GTIN_A, {'note': ['x']}, 400),
    (EAN_A, {'state': 'done'}, 400),                      # 13 цифр
    ('0461009362843a', {'state': 'done'}, 400),
    ('09999999999999', {'state': 'done'}, 404),           # такого GTIN в разборе нет
])
def test_review_update_errors(env, gtin, body, status):
    c = env.client
    _seed_review(c)
    r = c.put('/api/receiving/review/' + gtin, json=body)
    assert r.status_code == status and r.get_json()['error']


# --------------------------------------------------------------------------- поиск карточек

def _save_index():
    products = [
        {'id': 'p1', 'name': 'Жигули  Барное светлое', 'num': '00123', 'type': 'GOODS',
         'barcodes': [{'barcode': EAN_A}], 'category': 'cat1'},
        {'id': 'p2', 'name': 'Жигули Барное (Р)', 'num': '00124', 'type': 'DISH', 'barcodes': []},
        {'id': 'p3', 'name': 'Старое Жигули', 'num': '00999', 'type': 'GOODS', 'deleted': True,
         'barcodes': [{'barcode': EAN_B}]},
    ]
    index = receiving_index.build_index(products, [], categories=[{'id': 'cat1', 'name': 'ООО МаркетБир'}],
                                        built_at='2026-10-03T07:30:00+03:00')
    receiving_index.save_index(index)
    return index


def test_products_without_index_503(env):
    r = env.client.get('/api/receiving/products?q=жигули')
    assert r.status_code == 503 and r.get_json()['code'] == 'index_missing'


def test_products_search(env):
    _save_index()
    c = env.client
    r = c.get('/api/receiving/products?q=жигули')
    assert r.status_code == 200
    data = r.get_json()
    assert [card['id'] for card in data['cards']] == ['p1', 'p3']         # DISH не ищем; актуальные раньше
    assert data['cards'][0]['barcodes'] == [GTIN_A] and data['cards'][0]['supplier'] == 'ООО МаркетБир'
    assert data['cards'][1]['deleted'] is True
    assert data['index']['built_at'] == '2026-10-03T07:30:00+03:00'
    assert [x['id'] for x in c.get('/api/receiving/products?q=' + EAN_B).get_json()['cards']] == ['p3']
    assert len(c.get('/api/receiving/products?q=жигули&limit=1').get_json()['cards']) == 1


@pytest.mark.parametrize('query', ['', 'q=', 'q=ж', 'q=%20%20ж%20', 'q=жигули&limit=0',
                                   'q=жигули&limit=101', 'q=' + 'x' * 201])
def test_products_rejects_bad_query(env, query):
    _save_index()
    r = env.client.get('/api/receiving/products?' + query)
    assert r.status_code == 400 and r.get_json()['error']


# --------------------------------------------------------------------------- индекс iiko

@pytest.mark.parametrize('result', [
    ({'status': 'started'}, 202),
    ({'status': 'already_running'}, 409),
    ({'status': 'error', 'error': 'Не настроено подключение к iiko'}, 503),
])
def test_barcodes_refresh_passes_service_answer(env, result):
    env.service.refresh_result = result
    r = env.client.post('/api/receiving/barcodes/refresh')
    assert (r.get_json(), r.status_code) == result
    assert env.service.refresh_calls == ['button']


def test_barcodes_status(env):
    c = env.client
    data = c.get('/api/receiving/barcodes/status').get_json()
    assert data['index'] is None and data['job']['running'] is False
    _save_index()
    data = c.get('/api/receiving/barcodes/status').get_json()
    assert data['index']['counts']['products'] == 2 and data['index']['source'] == 'v2'


# --------------------------------------------------------------------------- недоступная БД

def test_unreadable_db_503(env):
    path = env.tmp / 'broken.db'
    path.write_bytes(b'this is not a sqlite database at all' * 100)
    before = path.read_bytes()
    receiving_store.set_db_path(str(path))
    c = env.client
    for method, url in (('get', '/api/receiving'), ('post', '/api/receiving'),
                        ('get', '/api/receiving/1'), ('get', '/api/receiving/review'),
                        ('post', '/api/receiving/1/close')):
        r = getattr(c, method)(url, json={}) if method == 'post' else c.get(url)
        assert r.status_code == 503, (url, r.status_code)
        assert r.get_json()['code'] == 'receiving_unavailable', url
    assert path.read_bytes() == before


# --------------------------------------------------------------------------- страницы

def test_pages_render_with_version(env):
    c = env.client
    r = c.get('/receiving')
    assert r.status_code == 200 and r.data.decode() == 'scan page v=test-ver'
    r = c.get('/receiving/review')
    assert r.status_code == 200 and r.data.decode() == 'review page v=test-ver'


def test_routes_and_methods_registered():
    app = Flask('test_receiving_rules')
    app.register_blueprint(receiving_bp)
    rules = {(m, r.rule) for r in app.url_map.iter_rules() if r.endpoint.startswith('receiving.')
             for m in r.methods if m not in ('HEAD', 'OPTIONS')}
    expected = {
        ('GET', '/receiving'), ('GET', '/receiving/review'),
        ('GET', '/api/receiving'), ('POST', '/api/receiving'),
        ('GET', '/api/receiving/<int:receipt_id>'), ('DELETE', '/api/receiving/<int:receipt_id>'),
        ('POST', '/api/receiving/<int:receipt_id>/scan'),
        ('DELETE', '/api/receiving/<int:receipt_id>/scans/<int:scan_id>'),
        ('POST', '/api/receiving/<int:receipt_id>/invoice'),
        ('GET', '/api/receiving/invoice/<name>'),
        ('DELETE', '/api/receiving/<int:receipt_id>/invoice/<name>'),
        ('POST', '/api/receiving/<int:receipt_id>/close'),
        ('GET', '/api/receiving/review'), ('PUT', '/api/receiving/review/<gtin>'),
        ('GET', '/api/receiving/products'),
        ('POST', '/api/receiving/barcodes/refresh'), ('GET', '/api/receiving/barcodes/status'),
    }
    assert rules == expected


# --------------------------------------------------------------------------- авторизация

def test_auth_gate(tmp_path, monkeypatch):
    """Настоящий гейт: аноним на API — 401 JSON, на страницу — редирект на вход."""
    from core import auth_manager as am
    from core.auth_guard import init_auth
    from routes.auth import auth_bp

    receiving_store.set_db_path(str(tmp_path / 'receiving.db'))
    auth = am.AuthManager(db_path=str(tmp_path / 'auth.db'))
    monkeypatch.setattr(am, '_auth_manager', auth)
    templates = tmp_path / 'templates'
    templates.mkdir()
    (templates / 'receiving.html').write_text('scan', encoding='utf-8')
    try:
        app = Flask('test_receiving_auth', template_folder=str(templates))
        app.register_blueprint(auth_bp)
        app.register_blueprint(receiving_bp)
        init_auth(app)
        c = app.test_client()

        r = c.get('/api/receiving')
        assert r.status_code == 401 and r.get_json()['auth_required'] is True
        r = c.post('/api/receiving/1/scan', json={'code': EAN_A, 'client_id': 'abcdefgh-1234'})
        assert r.status_code == 401
        assert c.get('/api/receiving/invoice/r1_20261003T140500_0123abcd.jpg').status_code == 401
        r = c.get('/receiving')
        assert r.status_code == 302 and '/login' in r.headers['Location']
        assert 'next=' in r.headers['Location'] and 'receiving' in r.headers['Location']
        assert receiving_store.list_receipts() == []

        auth.create_user('priemka', 'Приёмщик', 'passpass')
        r = c.post('/login', data={'login': 'priemka', 'password': 'passpass'})
        assert r.status_code in (200, 302)
        r = c.post('/api/receiving', json={})
        assert r.status_code == 201 and r.get_json()['receipt']['created_by'] == 'Приёмщик'
        assert c.get('/api/receiving').status_code == 200
    finally:
        receiving_store.set_db_path(None)


# --------------------------------------------------------------------------- MCP-мост

def test_mcp_bridge_scan_and_invoice(env, monkeypatch):
    """Инструменты stocks_receiving_* исполняют тот же маршрут; файл приходит из base64."""
    from core.mcp import bridge
    from core.mcp.principal import Principal
    from core.mcp.tools import stocks

    monkeypatch.setattr(rr, 'current_user', auth_guard.current_user)     # владелец из моста (g)
    monkeypatch.setattr(bridge, 'owner_record', lambda principal: {
        'id': 1, 'login': 'owner', 'display_name': 'Владелец', 'is_admin': True, 'active': True,
        'via_mcp': True})
    tools = {spec.name: spec for spec in stocks.TOOLS}
    principal = Principal(user_id=1, login='owner', display_name='Владелец', token_id='st_t',
                          token_kind='static', client_name='pytest')
    rid = receiving_store.create_receipt({'login': 'ivan', 'display_name': 'Иван'})['id']
    try:
        with env.app.app_context():
            result = bridge.execute(tools['stocks_receiving_scan'],
                                    {'receipt_id': rid, 'code': EAN_A, 'client_id': 'agent-scan-0001'},
                                    principal)
            assert not result.is_error, result.text_value
            assert json.loads(result.text_value.splitlines()[-1])['result'] == 'accepted'

            photo = {'filename': 'upd.jpg', 'content_base64': base64.b64encode(JPEG).decode('ascii'),
                     'mime_type': 'image/jpeg'}
            result = bridge.execute(tools['stocks_receiving_invoice_upload'],
                                    {'receipt_id': rid, 'photo': photo}, principal)
            assert not result.is_error, result.text_value

            result = bridge.execute(tools['stocks_receiving_get'], {'receipt_id': rid}, principal)
            assert not result.is_error, result.text_value
            got = json.loads(result.text_value.splitlines()[-1])
            assert got['recent'][0]['by'] == 'Владелец · агент'
            assert got['invoices'][0]['uploaded_by'] == 'Владелец · агент'
            assert got['receipt']['counts']['invoices'] == 1

            result = bridge.execute(tools['stocks_receiving_scan'],
                                    {'receipt_id': rid, 'code': EAN_A, 'client_id': 'bad id'}, principal)
            assert result.is_error                         # схема отбивает до маршрута
    finally:
        bridge.response_cache.clear()


# --------------------------------------------------------------------------- Python 3.10

def test_py310_compatible_syntax():
    """CI и прод — Python 3.10: модуль маршрутов разбирается грамматикой 3.10."""
    import ast
    src = open(rr.__file__, encoding='utf-8').read()
    ast.parse(src, feature_version=(3, 10))


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
