"""Приёмка на РЦ: страницы `/receiving`, `/receiving/review` и API `/api/receiving/*`.

## Что это

Приёмщик распределительного центра сканирует каждую бутылку, банку и кегу
(страница `/receiving`); после «Завершить» фоновая обработка сверяет GTIN с
индексом карточек iiko и Честным знаком и заводит строки разбора; бухгалтерия
разбирает их на `/receiving/review` (завести, восстановить карточку, выбрать
поставщика, «Сделано» / «Не нужно»). Здесь только HTTP: разбор запроса,
проверка полей, коды ответов. Правила живут в модулях ядра:

| Модуль | Что делает |
|--------|-----------|
| `core/receiving_codes.py` | разбор кода сканера (DataMatrix, EAN, SSCC) |
| `core/receiving_store.py` | SQLite `receiving.db`: приёмки, сканы, фото, строки разбора |
| `core/receiving_photo_store.py` | фото накладных на диске |
| `core/receiving_index.py` | индекс «GTIN -> карточки iiko», поиск карточек |
| `core/receiving_service.py` | обработка закрытой приёмки и обновление индекса (в фоне) |

Модули вызываются через атрибуты (`receiving_store.add_scan(...)`), а не через
импорт имён: тесты подменяют их фейками.

## Права

Как у всех бизнес-страниц: любой вошедший аккаунт (решение владельца о равных
правах, `core/auth_guard.py`). Приёмщику — экран сканирования, бухгалтерии —
разбор, ссылки друг на друга есть на обеих страницах. Действия ИИ-агента
владельца (вызов через MCP, `via_mcp`) хранилище подписывает « · агент».

## Эндпоинты (форматы ответов — docs/receiving.md, раздел API)

    GET    /api/receiving?status=open|closed|all&limit=     — список приёмок
    POST   /api/receiving                                   — {note?} новая приёмка (201)
    GET    /api/receiving/<id>                              — приёмка: позиции, сканы, фото, разбор
    POST   /api/receiving/<id>/scan                         — {code, client_id, source?, client_time?}
    DELETE /api/receiving/<id>/scans/<scan_id>              — отменить скан (мягкое удаление)
    POST   /api/receiving/<id>/invoice                      — multipart photo: фото накладной (201)
    GET    /api/receiving/invoice/<name>                    — само фото (image/jpeg)
    DELETE /api/receiving/<id>/invoice/<name>               — удалить фото
    POST   /api/receiving/<id>/close                        — завершить и запустить обработку
    GET    /api/receiving/review?state=&status=&receipt_id=&q=&limit=   — очередь бухгалтерии
    PUT    /api/receiving/review/<gtin>                     — {supplier?, state?, note?}
    GET    /api/receiving/products?q=&limit=                — поиск карточек в индексе iiko
    POST   /api/receiving/barcodes/refresh                  — обновить индекс из iiko (в фоне)
    GET    /api/receiving/barcodes/status                   — возраст индекса и ход обновления

Коды ошибок: 400 — кривое поле или фильтр (текст по-русски), 404 — нет приёмки,
скана, фото или строки разбора, 409 `code='receipt_closed'` — сканы закрытой
приёмки не меняются, 411 — фото без Content-Length, 413 — фото больше предела, 503 `code='receiving_unavailable'` —
`receiving.db` не читается (файл не трогаем), 503 `code='index_missing'` — индекс
iiko ещё не собран (поиск карточек).

## Почему закрытие и обновление индекса — в фоне

Обработка приёмки ждёт iiko (пересборка индекса — минуты), бар-ПК (названия ЧЗ по
SSH) и Telegram; gunicorn убивает запрос дольше 180 с (урок 21). Поэтому маршрут
закрывает приёмку, атомарно «берёт» обработку и сразу отвечает 202; ход виден в
`process_state` приёмки. Повтор «Завершить» безопасен: закрытая приёмка не
закрывается второй раз, сделанная обработка не перезапускается, упавшая —
перезапускается сразу (шедулер сам повторяет её не чаще раза в час).

## Changelog

- 2026-10-03 — модуль создан (приёмка на РЦ, первый этап).
"""
import re
from functools import wraps

from flask import Blueprint, jsonify, render_template, request, send_from_directory

from core import receiving_codes
from core import receiving_index
from core import receiving_photo_store
from core import receiving_service
from core import receiving_store
from core.auth_guard import current_user
from core.supplier_directory import get_supplier_directory

receiving_bp = Blueprint('receiving', __name__)

# ------------------------------------------------------------------ пределы запросов
# Фильтр списка приёмок: открытые (продолжить сканирование), закрытые, все.
RECEIPT_FILTERS = ('open', 'closed', 'all')
# Список приёмок: по умолчанию 50 последних, не больше 200 — экран приёмщика
# показывает открытые (их единицы), а историю целиком никто не листает.
RECEIPTS_LIMIT_DEFAULT = 50
RECEIPTS_LIMIT_MAX = 200
# Очередь бухгалтерии: 200 строк по умолчанию (страница рисует их без подгрузки),
# потолок — общий предел списков хранилища (1000).
REVIEW_LIMIT_DEFAULT = 200
REVIEW_LIMIT_MAX = receiving_store.LIST_LIMIT_MAX
# В ответ разбора — последние 20 закрытых приёмок для блока «Приёмки».
REVIEW_RECENT_RECEIPTS = 20
# Поиск карточек: от 2 символов (одна буква находит пол-номенклатуры), 20 по
# умолчанию, не больше 100 — глазами больше не сравнивают.
PRODUCTS_MIN_Q = 2
PRODUCTS_LIMIT_DEFAULT = 20
PRODUCTS_LIMIT_MAX = 100
# Длина строки поиска (q) — 200 символов: название с брендом и объёмом укладывается.
SEARCH_Q_MAX = 200
# Заметка приёмки и строки разбора — предел хранилища (500 символов).
NOTE_LIMIT = receiving_store.NOTE_LIMIT
# client_id скана: UUID (36 символов) или запасной id браузера; 8..64 латиницы,
# цифр и дефиса — по нему повтор запроса из очереди браузера не считается дважды.
CLIENT_ID_RE = re.compile(r'^[A-Za-z0-9-]{8,64}\Z')
# client_time — время телефона для диагностики (ISO), предел хранилища — 40 символов.
CLIENT_TIME_LIMIT = receiving_store.CLIENT_TIME_LIMIT
# Откуда скан: ручной сканер, камера телефона, набран руками.
SCAN_SOURCES = receiving_store.SOURCES
# Разбор: какие строки показать (open — к разбору, closed — закрытые, all — все)
# и фильтр статусов (раздел 1 спецификации: new, similar, restore, duplicate, found).
REVIEW_STATES = receiving_store.LIST_STATES
REVIEW_STATUSES = receiving_store.STATUSES
# Что выставляет бухгалтер: «Сделано», «Не нужно», «Вернуть в разбор».
REVIEW_USER_STATES = receiving_store.USER_STATES
# GTIN строки разбора — всегда 14 цифр (EAN-13 дополнен нулём слева).
GTIN_RE = re.compile(r'^[0-9]{14}\Z')
# Номер приёмки в фильтре разбора: до 9 цифр (как в имени фото накладной).
RECEIPT_ID_RE = re.compile(r'^[0-9]{1,9}\Z')
# Запас на заголовки multipart сверх самого фото: тело больше MAX_PHOTO_BYTES + 64 КБ
# отсекаем ДО чтения (Flask читает форму целиком в память).
UPLOAD_OVERHEAD_BYTES = 64 * 1024
# Сигнал приёмщику на повтор той же DataMatrix (бутылка уже посчитана).
REPEAT_MESSAGE = 'Уже посчитана'
# Кнопка «Обновить из iiko» на странице разбора (и вызов агента через MCP).
REFRESH_TRIGGER = 'button'


# ------------------------------------------------------------------ помощники

def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _error(message: str, status: int = 400, **extra):
    payload = {'error': message}
    payload.update(extra)
    return jsonify(payload), status


def _app_version() -> str:
    """Версия для ?v= (extensions.APP_VERSION выставляет app.py после импорта)."""
    try:
        import extensions
        return extensions.APP_VERSION
    except Exception:  # noqa: BLE001 — страница откроется и без версии
        return ''


def _store_guard(view):
    """Исключения хранилища -> коды ответа; одна точка вместо копий в каждом view.

    Нечитаемая receiving.db — 503 с кодом (страница показывает «база недоступна», а
    не пустой список); ValueError хранилища и разбора полей — 400 с его текстом.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except receiving_store.ReceivingUnavailable as e:
            return _error(str(e), 503, code='receiving_unavailable')
        except receiving_store.ReceiptNotFound:
            return _error('Приёмка не найдена', 404)
        except receiving_store.ReceiptClosed:
            return _error('Приёмка уже закрыта — сканы в ней не меняются', 409, code='receipt_closed')
        except receiving_store.ScanNotFound:
            return _error('Скан не найден', 404)
        except receiving_store.ReviewItemNotFound:
            return _error('Позиции с таким GTIN нет в разборе', 404)
        except ValueError as e:
            return _error(str(e), 400)
    return wrapper


def _parse_limit(raw, default: int, maximum: int) -> int:
    """?limit= -> целое 1..maximum; не задано — default.

    Кривое значение — ValueError (400), а не молчаливая подмена: агент решил бы,
    что строк меньше, чем есть на самом деле (как routes/stocks._parse_limit).
    """
    text = str(raw or '').strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError:
        value = 0
    if not 1 <= value <= maximum:
        raise ValueError('limit — целое число от 1 до ' + str(maximum))
    return value


def _search_text(raw, minimum: int = 0) -> str:
    """?q= без пробелов по краям; длиннее SEARCH_Q_MAX или короче minimum — ValueError."""
    text = str(raw or '').strip()
    if len(text) > SEARCH_Q_MAX:
        raise ValueError('q — не длиннее ' + str(SEARCH_Q_MAX) + ' символов')
    if len(text) < minimum:
        raise ValueError('q — от ' + str(minimum) + ' символов')
    return text


def _note_text(raw) -> str:
    """Заметка: строка до NOTE_LIMIT символов (края обрезаются); иначе ValueError."""
    if raw is None:
        return ''
    if not isinstance(raw, str):
        raise ValueError('note — строка')
    text = raw.strip()
    if len(text) > NOTE_LIMIT:
        raise ValueError('note — не длиннее ' + str(NOTE_LIMIT) + ' символов')
    return text


def _scan_message(result: str, scan: dict) -> str:
    """Короткая фраза для экрана приёмщика по итогу записи скана.

    Берётся по сохранённому скану (а не по новому разбору): у повтора запроса из
    очереди браузера ответ тот же, что в первый раз.
    """
    if result == receiving_store.RESULT_ACCEPTED:
        return receiving_codes.MSG_OK
    if result == receiving_store.RESULT_REPEAT:
        return REPEAT_MESSAGE
    return receiving_codes.MESSAGES.get(scan.get('reason'), receiving_codes.MSG_UNREADABLE)


def _canonical_supplier(raw: str) -> str:
    """Поставщик строки разбора -> каноническое имя справочника ('' — очистить).

    Принимается имя или написание (алиас) из core/supplier_directory; чужое имя —
    ValueError: выбор бухгалтера потом станет поставщиком карточки, опечатка в нём
    разошлась бы со справочником сроков и минимальных заказов.
    """
    name = ' '.join(raw.split())
    if not name:
        return ''
    view = get_supplier_directory().view()
    record = view.get(view.resolve(name))
    if record is None:
        raise ValueError('Поставщика нет в справочнике')
    return record['name']


def _supplier_names() -> list:
    """Имена справочника поставщиков для выпадающего списка разбора (по алфавиту)."""
    return [rec['name'] for rec in get_supplier_directory().list()]


# ------------------------------------------------------------------ страницы

@receiving_bp.route('/receiving')
def receiving_page():
    """Экран приёмщика: сканирование. Данные — /api/receiving/*; `?r=<id>` — продолжить."""
    return render_template('receiving.html', app_version=_app_version())


@receiving_bp.route('/receiving/review')
def receiving_review_page():
    """Разбор приёмок для бухгалтерии. `?receipt=<id>` — только позиции этой приёмки."""
    return render_template('receiving_review.html', app_version=_app_version())


# ------------------------------------------------------------------ приёмки

@receiving_bp.route('/api/receiving', methods=['GET'])
@_store_guard
def receiving_list():
    """Приёмки, новые сверху: ?status=open|closed|all (по умолчанию all), ?limit=1..200."""
    status = (request.args.get('status') or 'all').strip()
    if status not in RECEIPT_FILTERS:
        return _error('status — open, closed или all')
    limit = _parse_limit(request.args.get('limit'), RECEIPTS_LIMIT_DEFAULT, RECEIPTS_LIMIT_MAX)
    receipts = receiving_store.list_receipts(status=None if status == 'all' else status, limit=limit)
    return jsonify({'receipts': receipts})


@receiving_bp.route('/api/receiving', methods=['POST'])
@_store_guard
def receiving_create():
    """Открыть новую приёмку (кнопка «Новая приёмка»). Тело: {note?} до 500 символов."""
    body = _json_body()
    note = _note_text(body.get('note'))
    receipt = receiving_store.create_receipt(current_user(), note)
    return jsonify({'receipt': receipt}), 201


@receiving_bp.route('/api/receiving/<int:receipt_id>', methods=['GET'])
@_store_guard
def receiving_get(receipt_id):
    """Приёмка целиком: позиции (GTIN и штуки), последние сканы, фото накладных.

    dm_keys — ключи уже принятых DataMatrix (только у открытой: браузер по ним сразу
    говорит «Уже посчитана»); rows — строки разбора GTIN этой приёмки (только у
    закрытой: что с ними решила обработка и бухгалтерия).
    """
    receipt = receiving_store.get_receipt(receipt_id)
    is_open = receipt['status'] == 'open'
    rows = []
    if not is_open:
        rows = receiving_store.list_review(state='all', receipt_id=receipt_id,
                                           limit=REVIEW_LIMIT_MAX)['rows']
    return jsonify({
        'receipt': receipt,
        'lines': receiving_store.receipt_lines(receipt_id),
        'recent': receiving_store.recent_scans(receipt_id),
        'invoices': receiving_store.list_invoices(receipt_id),
        'dm_keys': receiving_store.dm_keys(receipt_id) if is_open else [],
        'rows': rows,
    })


@receiving_bp.route('/api/receiving/<int:receipt_id>/scan', methods=['POST'])
@_store_guard
def receiving_scan(receipt_id):
    """Записать один скан. Тело: {code, client_id, source?, client_time?}.

    Код разбирается здесь (core/receiving_codes), хранилище доверяет разбору.
    Записывается и отклонённый скан — для диагностики («что прочитал сканер»).
    result: accepted — посчитан; repeat — та же DataMatrix уже посчитана в этой
    приёмке; rejected — код не распознан (message — что сказать приёмщику).
    Повтор того же client_id — тот же ответ, replayed=True, второй раз не считается.
    """
    body = _json_body()
    code = body.get('code')
    if not isinstance(code, str):
        return _error('code — строка с прочитанным кодом')
    client_id = body.get('client_id')
    if not isinstance(client_id, str) or not CLIENT_ID_RE.match(client_id):
        return _error('client_id — от 8 до 64 символов: латиница, цифры, дефис')
    source = body.get('source') or receiving_store.DEFAULT_SOURCE
    if source not in SCAN_SOURCES:
        return _error('source — scanner, camera или manual')
    client_time = body.get('client_time') or ''
    if not isinstance(client_time, str) or len(client_time) > CLIENT_TIME_LIMIT:
        return _error('client_time — строка до ' + str(CLIENT_TIME_LIMIT) + ' символов')

    parsed = receiving_codes.parse_code(code)
    saved = receiving_store.add_scan(receipt_id, parsed, code, client_id, source, client_time,
                                     current_user())
    scan = saved['scan']
    return jsonify({
        'result': saved['result'],
        'kind': scan['kind'],
        'gtin': scan['gtin'],
        'message': _scan_message(saved['result'], scan),
        'scan_id': scan['id'],
        'replayed': saved['replayed'],
        'counts': saved['counts'],
    })


@receiving_bp.route('/api/receiving/<int:receipt_id>/scans/<int:scan_id>', methods=['DELETE'])
@_store_guard
def receiving_scan_delete(receipt_id, scan_id):
    """«Отменить последний»: мягко удалить скан открытой приёмки (повтор безопасен)."""
    result = receiving_store.delete_scan(receipt_id, scan_id, current_user())
    return jsonify({'deleted': True, 'counts': result['counts']})


@receiving_bp.route('/api/receiving/<int:receipt_id>/close', methods=['POST'])
@_store_guard
def receiving_close(receipt_id):
    """«Завершить»: закрыть приёмку и запустить обработку в фоне.

    processing: started — обработку запустил этот запрос (202; упавшую обработку
    повторное «Завершить» перезапускает сразу); running — её уже ведёт другой поток
    или воркер (202); pending — ждёт шедулера (202); done — обработка уже сделана,
    повтор ничего не перезапускает (200).
    """
    receipt, _changed = receiving_store.close_receipt(receipt_id, current_user())
    if receipt['process_state'] == 'done':
        return jsonify({'receipt': receipt, 'processing': 'done'}), 200
    started = receiving_service.start_receipt_processing(receipt_id, retry_error_now=True)
    receipt = receiving_store.get_receipt(receipt_id)
    processing = 'started' if started else receipt['process_state']
    return jsonify({'receipt': receipt, 'processing': processing}), 200 if processing == 'done' else 202


# ------------------------------------------------------------------ фото накладных

@receiving_bp.route('/api/receiving/<int:receipt_id>/invoice', methods=['POST'])
@_store_guard
def receiving_invoice_upload(receipt_id):
    """Фото накладной (multipart, поле photo, JPEG до 8 МБ). Можно и у закрытой приёмки.

    Порядок: размер тела -> приёмка есть -> содержимое в памяти -> файл на диск ->
    запись в БД. Запись не легла — файл удаляется, чтобы не осиротел.
    Тело без Content-Length (chunked) — 411: его размер нельзя проверить до чтения,
    а Flask разобрал бы форму целиком (браузер и мост MCP длину всегда присылают).
    """
    if request.content_length is None:
        return _error('Нужен заголовок Content-Length: загрузка частями не принимается', 411)
    if request.content_length > receiving_photo_store.MAX_PHOTO_BYTES + UPLOAD_OVERHEAD_BYTES:
        mb = receiving_photo_store.MAX_PHOTO_BYTES // (1024 * 1024)
        return _error('Фото больше ' + str(mb) + ' МБ — сделайте снимок меньшего размера', 413)
    receiving_store.get_receipt(receipt_id)
    upload = request.files.get('photo')
    data = upload.read() if upload else b''
    if not data:
        return _error('Нет фото: передайте файл в поле photo')
    if len(data) > receiving_photo_store.MAX_PHOTO_BYTES:
        mb = receiving_photo_store.MAX_PHOTO_BYTES // (1024 * 1024)
        return _error('Фото больше ' + str(mb) + ' МБ — сделайте снимок меньшего размера', 413)
    ok, err = receiving_photo_store.check(data)
    if not ok:
        return _error(err)
    saved, name_or_err = receiving_photo_store.save(data, receipt_id)
    if not saved:
        return _error(name_or_err, 500)
    try:
        invoice = receiving_store.add_invoice(receipt_id, name_or_err, len(data), current_user())
    except Exception:
        receiving_photo_store.delete(name_or_err)
        raise
    return jsonify({'invoice': invoice, 'invoices': receiving_store.list_invoices(receipt_id)}), 201


@receiving_bp.route('/api/receiving/invoice/<name>', methods=['GET'])
def receiving_invoice_file(name):
    """Отдать фото накладной. Имя проверяется формой до любого обращения к диску.

    `nosniff` + явный mimetype: браузер не угадывает тип загруженного файла. Кэш
    приватный: накладная — внутренний документ (имя со случайной частью не меняется).
    """
    if not receiving_photo_store.is_valid_name(name) or not receiving_photo_store.exists(name):
        return _error('Фото не найдено', 404)
    resp = send_from_directory(receiving_photo_store.photo_dir(), name, mimetype='image/jpeg')
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Cache-Control'] = 'private, max-age=86400'
    return resp


@receiving_bp.route('/api/receiving/<int:receipt_id>/invoice/<name>', methods=['DELETE'])
@_store_guard
def receiving_invoice_delete(receipt_id, name):
    """Удалить фото накладной приёмки: запись в БД, затем файл (best-effort)."""
    if not receiving_photo_store.is_valid_name(name):
        return _error('Фото не найдено', 404)
    if not receiving_store.delete_invoice(receipt_id, name):
        receiving_store.get_receipt(receipt_id)     # нет самой приёмки — 404 «Приёмка не найдена»
        return _error('Фото не найдено', 404)
    receiving_photo_store.delete(name)
    return jsonify({'deleted': True, 'invoices': receiving_store.list_invoices(receipt_id)})


# ------------------------------------------------------------------ разбор бухгалтерии

@receiving_bp.route('/api/receiving/review', methods=['GET'])
@_store_guard
def receiving_review():
    """Очередь бухгалтерии: строки разбора + индекс iiko + справочник поставщиков.

    Фильтры: ?state=open|closed|all (по умолчанию open), ?status=new,similar (через
    запятую из found, restore, duplicate, similar, new), ?receipt_id= (GTIN одной
    приёмки), ?q= (GTIN, штрихкод, название ЧЗ, карточки, поставщик, заметка),
    ?limit=1..1000. Кривой фильтр — 400. counts — счётчики вкладок без state и status.
    """
    state = (request.args.get('state') or 'open').strip()
    if state not in REVIEW_STATES:
        return _error('state — open, closed или all')
    status_raw = request.args.get('status') or ''
    statuses = [s.strip() for s in status_raw.split(',') if s.strip()]
    unknown = [s for s in statuses if s not in REVIEW_STATUSES]
    if unknown:
        return _error('status — через запятую из: ' + ', '.join(REVIEW_STATUSES))
    receipt_raw = (request.args.get('receipt_id') or '').strip()
    if receipt_raw and not RECEIPT_ID_RE.match(receipt_raw):
        return _error('receipt_id — номер приёмки')
    q = _search_text(request.args.get('q'))
    limit = _parse_limit(request.args.get('limit'), REVIEW_LIMIT_DEFAULT, REVIEW_LIMIT_MAX)

    data = receiving_store.list_review(state=state, statuses=statuses,
                                       receipt_id=int(receipt_raw) if receipt_raw else None,
                                       q=q, limit=limit)
    data.update(receiving_service.status())
    data['suppliers'] = _supplier_names()
    data['receipts'] = receiving_store.list_receipts(status='closed', limit=REVIEW_RECENT_RECEIPTS)
    return jsonify(data)


@receiving_bp.route('/api/receiving/review/<gtin>', methods=['PUT'])
@_store_guard
def receiving_review_update(gtin):
    """Решение бухгалтерии по строке. Тело — хотя бы одно из {supplier, state, note}.

    supplier: имя или написание из справочника поставщиков ('' — очистить),
    сохраняется каноническое имя; state: done («Сделано») / not_needed («Не нужно»)
    закрывают строку, open — «Вернуть в разбор»; note — до 500 символов.
    """
    if not GTIN_RE.match(gtin):
        return _error('GTIN — ровно 14 цифр')
    body = _json_body()
    supplier = body.get('supplier')
    state = body.get('state')
    note = body.get('note')
    if supplier is None and state is None and note is None:
        return _error('Нечего менять: передайте supplier, state или note')
    if supplier is not None:
        if not isinstance(supplier, str):
            return _error('supplier — строка (имя из справочника поставщиков)')
        supplier = _canonical_supplier(supplier)
    if state is not None and state not in REVIEW_USER_STATES:
        return _error('state — done, not_needed или open')
    if note is not None:
        note = _note_text(note)
    row = receiving_store.update_review(gtin, current_user(), supplier=supplier, state=state, note=note)
    return jsonify({'row': row})


@receiving_bp.route('/api/receiving/products', methods=['GET'])
@_store_guard
def receiving_products():
    """«Найти в iiko»: карточки индекса по названию, артикулу или штрихкоду.

    Ищет только в файле индекса (iiko в момент запроса не трогает). Индекса ещё
    нет — 503 index_missing: сначала «Обновить из iiko».
    """
    q = _search_text(request.args.get('q'), minimum=PRODUCTS_MIN_Q)
    limit = _parse_limit(request.args.get('limit'), PRODUCTS_LIMIT_DEFAULT, PRODUCTS_LIMIT_MAX)
    index = receiving_index.load_index()
    if index is None:
        return _error('Индекс карточек iiko ещё не собран — нажмите «Обновить из iiko»', 503,
                      code='index_missing')
    return jsonify({'cards': receiving_index.search_cards(q, index, limit),
                    'index': receiving_index.index_info(index)})


# ------------------------------------------------------------------ индекс iiko

@receiving_bp.route('/api/receiving/barcodes/refresh', methods=['POST'])
@_store_guard
def receiving_barcodes_refresh():
    """«Обновить из iiko»: пересобрать индекс карточек в фоне (затем пересверить разбор).

    202 started; 409 already_running — обновляет другой воркер, утренний шедулер или
    обработка приёмки; 503 — нет подключения к iiko. Ход — /api/receiving/barcodes/status.
    """
    result, code = receiving_service.start_receiving_index_refresh(REFRESH_TRIGGER)
    return jsonify(result), code


@receiving_bp.route('/api/receiving/barcodes/status', methods=['GET'])
@_store_guard
def receiving_barcodes_status():
    """Индекс iiko (когда собран, сколько карточек) и ход обновления (running, error)."""
    return jsonify(receiving_service.status())
