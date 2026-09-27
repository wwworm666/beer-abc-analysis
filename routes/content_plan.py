"""Раздел «Гости» -> «Контент-план»: страница и HTTP API.

Модель, правила готовности, переходы статусов, копирование месяца и живые
данные — core/content_plan.py (докстринг модуля); файлы фото/видео —
core/content_media.py. Этот модуль только разбирает запрос, зовёт хранилище и
переводит его исключения в коды ответа. Интеграций нет: ничего никуда не
отправляется (DELIVERY_CONNECTED — все False), «вышло» отмечают вручную.

Эндпоинты:
    GET    /content-plan                                  страница (templates/content_plan.html)
    GET    /api/content-plan?month=YYYY-MM                материалы месяца + справочники + stats
                                                          (месяц по умолчанию — текущий по Москве;
                                                          scope='month')
    GET    /api/content-plan?state=overdue|failed         БЕЗ month — вид «по всем месяцам»: материалы
                                                          любого месяца с размещением в этом
                                                          состоянии (scope='state', state; см.
                                                          ContentPlanStore.state_payload). С month
                                                          или с другим state — обычный месяц: фильтр
                                                          ?state= применяет экран
    GET    /api/content-plan/materials/<id>               {material} (для deep-link ?open=)
    POST   /api/content-plan/materials                    {month, title, kind?, live_source?,
                                                           planned_date?, base_text?, note?,
                                                           media_required?} -> {material}
    PATCH  /api/content-plan/materials/<id>               {title?, kind?, live_source?, planned_date?,
                                                           base_text?, note?, media_required?}
                                                          -> {material, unapproved}
    DELETE /api/content-plan/materials/<id>               -> {deleted: true}; 409 при вышедших
    POST   /api/content-plan/materials/<id>/placements    {channel, bars:[..], date?, time?, text?,
                                                           media?, audience?} -> {material, created}
    PATCH  /api/content-plan/placements/<pid>             {channel?, bar?, date?, time?, text?, media?,
                                                           audience?} -> {material, unapproved}
    DELETE /api/content-plan/placements/<pid>             -> {material}; 409 если вышло
    POST   /api/content-plan/placements/<pid>/action      {action} -> {material}; 409 — не тот статус
    POST   /api/content-plan/materials/<id>/shift         {days} -> {material}
    POST   /api/content-plan/materials/<id>/repeat        {weekdays:[0..6], month?} -> {created}
                                                          (month по умолчанию — месяц материала)
    POST   /api/content-plan/materials/<id>/media         multipart 'file' -> {material, unapproved}
    DELETE /api/content-plan/materials/<id>/media/<name>  -> {material, unapproved}
    GET    /api/content-plan/media/<name>                 файл; 404 на неверное/неизвестное имя
    GET    /api/content-plan/approve-preview              ?month=&bar=&channel= -> {month, will_approve,
                                                          bot, stays_draft}
    POST   /api/content-plan/approve                      {placement_ids:[..], confirm_bot?}
                                                          -> {approved, skipped}
    POST   /api/content-plan/bulk-pause                   {bar, action:'pause'|'resume'}
                                                          -> {changed, skipped}
    POST   /api/content-plan/bulk                         {material_ids:[..], action:'shift'|'delete'|
                                                           'cancel', days?} -> {done, failed:[{id, error}]}
    POST   /api/content-plan/copy-month                   {from?, to, with_content?} -> {created, notes}
                                                          (from по умолчанию — месяц перед to)
    GET    /api/content-plan/live-preview                 ?source=&bar=&material_id=&placement_id=&date=
                                                          &template=&channel=&has_media=
                                                          -> render_live (POST с тем же JSON — для
                                                          длинного шаблона, который не влезает в URL);
                                                          предел длины — по площадке (channel) и
                                                          наличию фото (has_media), см. live_preview
    GET    /api/content-plan/materials/<id>/log           -> {entries: [новые сверху]}

Необязательный ?month=YYYY-MM у изменяющих запросов задаёт месяц просмотра:
по нему считается in_month материала в ответе (без него — true).

Коды ответов: 400 — ошибка ввода {error}; 404 — нет материала/размещения/файла;
409 — действие недопустимо в текущем статусе (+ поля из исключения); 413 —
тело загрузки больше предела видео; 503 {error, code: 'content_plan_unavailable'}
— файл плана есть, но не читается (он НЕ перезаписывается).
"""
from functools import wraps

from flask import Blueprint, jsonify, render_template, request, send_from_directory

from core import content_media
from core.auth_guard import current_user
from core.content_plan import (CHANNELS, CROSS_MONTH_STATES, MATERIAL_MEDIA_MAX, ContentPlanConflict,
                               ContentPlanNotFound, ContentPlanUnavailable, add_months,
                               get_content_plan_store, parse_bool, parse_date, parse_days, parse_month,
                               placement_content, render_live)

content_plan_bp = Blueprint('content_plan', __name__)

# Массовое действие над выделенными строками таблицы: месяц — это десятки
# материалов (серия «каждую пятницу» x 4 бара — ещё ~20), 500 — запас на порядок
# и защита от случайного «выделить всё за год» одним запросом.
BULK_MAX = 500
BULK_ACTIONS = ('shift', 'delete', 'cancel')

# Верхний предел тела загрузки: самый большой допустимый файл (видео 50 МБ) +
# запас на заголовки multipart. Проверяется ДО чтения тела (Flask читает форму
# целиком в память) — приём routes/cleanliness.py.
UPLOAD_BODY_MAX = content_media.MAX_VIDEO_BYTES + content_media.UPLOAD_OVERHEAD_BYTES


def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _error(message: str, status: int = 400, **extra):
    payload = {'error': message}
    payload.update(extra)
    return jsonify(payload), status


def _guard(view):
    """Исключения хранилища -> 400 / 404 / 409 / 503 (не 500 и не запись поверх)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except ContentPlanUnavailable as e:
            return _error(str(e), 503, code='content_plan_unavailable')
        except ContentPlanNotFound as e:
            return _error(str(e), 404)
        except ContentPlanConflict as e:
            return _error(str(e), 409, **e.extra)
        except ValueError as e:
            return _error(str(e), 400)
    return wrapper


def _store():
    """Хранилище плана (отдельная функция — тесты подменяют её временным файлом)."""
    return get_content_plan_store()


def _app_version() -> str:
    """Версия для ?v= (extensions.APP_VERSION выставляет app.py после импорта)."""
    try:
        import extensions
        return extensions.APP_VERSION
    except Exception:  # noqa: BLE001 — страница откроется и без версии
        return ''


def _view_month():
    """Месяц просмотра из ?month= (для in_month в ответе) или None."""
    raw = (request.args.get('month') or '').strip()
    return parse_month(raw) if raw else None


def _current_month(store) -> str:
    return store.now().strftime('%Y-%m')


# ------------------------------------------------------------------ страница

@content_plan_bp.route('/content-plan')
def content_plan_page():
    return render_template('content_plan.html', app_version=_app_version())


# ------------------------------------------------------------------ чтение

@content_plan_bp.route('/api/content-plan', methods=['GET'])
@_guard
def content_plan_month():
    """Месяц плана; ?state=overdue|failed без month — вид «по всем месяцам»
    (ссылки полосы внимания: их счётчики считают любой месяц)."""
    store = _store()
    raw = (request.args.get('month') or '').strip()
    state = (request.args.get('state') or '').strip()
    if not raw and state in CROSS_MONTH_STATES:
        return jsonify(store.state_payload(state))
    month = parse_month(raw) if raw else _current_month(store)
    return jsonify(store.month_payload(month))


@content_plan_bp.route('/api/content-plan/materials/<material_id>', methods=['GET'])
@_guard
def get_material(material_id):
    return jsonify({'material': _store().get_material(material_id, _view_month())})


@content_plan_bp.route('/api/content-plan/materials/<material_id>/log', methods=['GET'])
@_guard
def material_log(material_id):
    return jsonify({'entries': _store().log_for(material_id)})


# ------------------------------------------------------------------ материалы

@content_plan_bp.route('/api/content-plan/materials', methods=['POST'])
@_guard
def create_material():
    material = _store().create_material(_json_body(), current_user())
    return jsonify({'material': material})


@content_plan_bp.route('/api/content-plan/materials/<material_id>', methods=['PATCH'])
@_guard
def update_material(material_id):
    material, unapproved = _store().update_material(material_id, _json_body(), current_user(),
                                                    _view_month())
    return jsonify({'material': material, 'unapproved': unapproved})


@content_plan_bp.route('/api/content-plan/materials/<material_id>', methods=['DELETE'])
@_guard
def delete_material(material_id):
    _store().delete_material(material_id, current_user())
    return jsonify({'deleted': True})


@content_plan_bp.route('/api/content-plan/materials/<material_id>/shift', methods=['POST'])
@_guard
def shift_material(material_id):
    material = _store().shift(material_id, _json_body().get('days'), current_user(), _view_month())
    return jsonify({'material': material})


@content_plan_bp.route('/api/content-plan/materials/<material_id>/repeat', methods=['POST'])
@_guard
def repeat_material(material_id):
    body = _json_body()
    store = _store()
    raw_month = str(body.get('month') or '').strip()
    month = raw_month or store.get_material_raw(material_id)['month']
    return jsonify(store.repeat(material_id, body.get('weekdays'), month, current_user()))


# ------------------------------------------------------------------ размещения

@content_plan_bp.route('/api/content-plan/materials/<material_id>/placements', methods=['POST'])
@_guard
def add_placements(material_id):
    material, created = _store().add_placements(material_id, _json_body(), current_user(),
                                                _view_month())
    return jsonify({'material': material, 'created': created})


@content_plan_bp.route('/api/content-plan/placements/<placement_id>', methods=['PATCH'])
@_guard
def update_placement(placement_id):
    material, unapproved = _store().update_placement(placement_id, _json_body(), current_user(),
                                                     _view_month())
    return jsonify({'material': material, 'unapproved': unapproved})


@content_plan_bp.route('/api/content-plan/placements/<placement_id>', methods=['DELETE'])
@_guard
def delete_placement(placement_id):
    return jsonify({'material': _store().delete_placement(placement_id, current_user(), _view_month())})


@content_plan_bp.route('/api/content-plan/placements/<placement_id>/action', methods=['POST'])
@_guard
def placement_action(placement_id):
    material = _store().placement_action(placement_id, _json_body().get('action'), current_user(),
                                         _view_month())
    return jsonify({'material': material})


# ------------------------------------------------------------------ утверждение и массовые

@content_plan_bp.route('/api/content-plan/approve-preview', methods=['GET'])
@_guard
def approve_preview():
    store = _store()
    args = request.args
    raw = (args.get('month') or '').strip()
    month = parse_month(raw) if raw else _current_month(store)
    return jsonify(store.approve_preview(month, bar=args.get('bar'), channel=args.get('channel')))


@content_plan_bp.route('/api/content-plan/approve', methods=['POST'])
@_guard
def approve():
    body = _json_body()
    return jsonify(_store().approve(body.get('placement_ids'), current_user(),
                                    confirm_bot=body.get('confirm_bot', False)))


@content_plan_bp.route('/api/content-plan/bulk-pause', methods=['POST'])
@_guard
def bulk_pause():
    body = _json_body()
    action = str(body.get('action') or '').strip()
    return jsonify(_store().bulk_pause(body.get('bar'), action, current_user()))


@content_plan_bp.route('/api/content-plan/bulk', methods=['POST'])
@_guard
def bulk_materials():
    """Массовое действие над выделенными материалами. Каждый материал — своя
    запись (не одна транзакция): ошибка по одному не отменяет остальные и
    попадает в failed с текстом. Недоступный файл плана прерывает всё (503)."""
    body = _json_body()
    action = str(body.get('action') or '').strip()
    if action not in BULK_ACTIONS:
        return _error('Действие: shift (сдвиг), delete (удаление) или cancel (отмена размещений)')
    ids = body.get('material_ids')
    if not isinstance(ids, list) or not ids:
        return _error('Не выбраны материалы')
    if len(ids) > BULK_MAX:
        return _error(f'За один раз — не больше {BULK_MAX} материалов')
    days = parse_days(body.get('days')) if action == 'shift' else None
    store = _store()
    user = current_user()
    month = _view_month()
    done, failed, seen = 0, [], []
    for raw_id in ids:
        material_id = str(raw_id)
        if material_id in seen:
            continue
        seen.append(material_id)
        try:
            if action == 'shift':
                store.shift(material_id, days, user, month)
            elif action == 'delete':
                store.delete_material(material_id, user)
            else:
                store.cancel_material(material_id, user, month)
            done += 1
        except (ValueError, ContentPlanNotFound, ContentPlanConflict) as e:
            failed.append({'id': material_id, 'error': str(e)})
    return jsonify({'done': done, 'failed': failed})


@content_plan_bp.route('/api/content-plan/copy-month', methods=['POST'])
@_guard
def copy_month():
    body = _json_body()
    to_month = parse_month(body.get('to'), 'Месяц назначения')
    raw_from = str(body.get('from') or '').strip()
    from_month = raw_from or add_months(to_month, -1)
    with_content = body.get('with_content')
    with_content = parse_bool(with_content, 'Копировать тексты и фото') if with_content is not None else False
    return jsonify(_store().copy_month(from_month, to_month, with_content, current_user()))


# ------------------------------------------------------------------ живые данные

@content_plan_bp.route('/api/content-plan/live-preview', methods=['GET', 'POST'])
@_guard
def live_preview():
    """Предпросмотр живых данных.

    Откуда что берётся (переданный параметр всегда главнее):
    - ?placement_id= — размещение: его материал, шаблон (текст размещения; у
      вышедшего — из снимка), бар, дата, площадка и есть ли у него фото;
    - ?material_id= — материал: шаблон — общий текст, фото — все файлы материала
      (так выходит размещение без своей подборки);
    - шаблон — ?template=; источник — ?source=, иначе источник материала;
      дата {дата} — ?date=, иначе дата размещения, иначе сегодня;
    - ?channel= (telegram|instagram|bot) и ?has_media= (да/нет) задают предел
      длины: 1024 у Telegram/бота с фото, 4096 без фото, 2200 у Instagram. Без
      площадки — 4096 (общая проверка «на текущих данных»).
    Проблемы данных (нет бара, нет кранов, непроверенная связь, длина) — это
    не ошибка запроса: ответ 200 с ok=false и списком problems. Неизвестная
    площадка, чужое размещение или неверная дата — 400; нет материала или
    размещения — 404."""
    params = _json_body() if request.method == 'POST' else request.args
    store = _store()
    material = placement = None
    material_id = str(params.get('material_id') or '').strip()
    placement_id = str(params.get('placement_id') or '').strip()
    if placement_id:
        material, placement = store.get_placement_raw(placement_id)
        if material_id and material_id != material['id']:
            raise ValueError('Размещение относится к другому материалу')
    elif material_id:
        material = store.get_material_raw(material_id)
    content = placement_content(material, placement) if placement else None
    if params.get('template') is not None:
        template = str(params.get('template'))
    elif content:
        template = content[0]
    else:
        template = (material or {}).get('base_text') or ''
    source = str(params.get('source') or '').strip() or (material or {}).get('live_source')
    bar = str(params.get('bar') or '').strip() or (placement or {}).get('bar') or ''
    raw_date = params.get('date')
    if raw_date in (None, '') and placement:
        raw_date = placement.get('date')
    pub_date = parse_date(raw_date, 'Дата выхода')
    channel = str(params.get('channel') or '').strip() or (placement or {}).get('channel') or None
    if channel is not None and channel not in CHANNELS:
        raise ValueError('Площадка: Telegram, Instagram или Бот')
    raw_media = params.get('has_media')
    if raw_media not in (None, ''):
        has_media = parse_bool(raw_media, 'Есть фото')
    elif content:
        has_media = bool(content[1])
    else:
        has_media = bool((material or {}).get('media'))
    return jsonify(render_live(source, bar, template, pub_date=pub_date, now=store.now(),
                               channel=channel, has_media=has_media))


# ------------------------------------------------------------------ файлы

@content_plan_bp.route('/api/content-plan/materials/<material_id>/media', methods=['POST'])
@_guard
def upload_media(material_id):
    """Загрузить фото/видео. Порядок: размер тела (413) -> материал есть (404) и
    не набрал предел файлов -> сигнатура и размер файла (400) -> запись на
    диск -> привязка к материалу. Если привязка не удалась (материал удалили
    параллельно, предел файлов), записанный файл удаляется — сирот не остаётся."""
    if (request.content_length or 0) > UPLOAD_BODY_MAX:
        return _error(f'Файл больше {content_media.MAX_VIDEO_BYTES // (1024 * 1024)} МБ', 413)
    store = _store()
    material = store.get_material_raw(material_id)
    if len(material.get('media') or []) >= MATERIAL_MEDIA_MAX:
        return _error(f'У материала уже {MATERIAL_MEDIA_MAX} файлов — удалите лишние')
    upload = request.files.get('file')
    if upload is None:
        return _error('Выберите файл')
    # Чтение с пределом: тело без Content-Length (chunked) не прочитается больше
    # максимума; превышение даст понятную ошибку размера из content_media.check.
    data = upload.read(content_media.MAX_VIDEO_BYTES + 1)
    ok, name_or_err = store.media.save(data, store.today())
    if not ok:
        return _error(name_or_err)
    try:
        material_view, unapproved = store.add_media(material_id, name_or_err, len(data),
                                                    upload.filename, current_user(), _view_month())
    except Exception:
        store.media.delete(name_or_err)
        raise
    return jsonify({'material': material_view, 'unapproved': unapproved})


@content_plan_bp.route('/api/content-plan/materials/<material_id>/media/<name>', methods=['DELETE'])
@_guard
def delete_media(material_id, name):
    material, unapproved = _store().remove_media(material_id, name, current_user(), _view_month())
    return jsonify({'material': material, 'unapproved': unapproved})


@content_plan_bp.route('/api/content-plan/media/<name>', methods=['GET'])
def serve_media(name):
    """Отдать файл. Имя проверяется формой (content_media.NAME_RE) ДО любого
    обращения к диску — конкатенации пользовательской строки с путём нет.
    Явный mimetype по расширению + nosniff: браузер не угадывает тип файла,
    загруженного пользователем. Кэш приватный: имя файла неизменно (новая
    загрузка — новое имя), поэтому сутки кэша безопасны. Видео отдаётся с
    поддержкой Range (conditional) — перемотка в плеере."""
    if not content_media.is_valid_name(name):
        return _error('Файл не найден', 404)
    media = _store().media
    if not media.exists(name):
        return _error('Файл не найден', 404)
    resp = send_from_directory(media.directory, name, mimetype=content_media.mimetype_of(name),
                               conditional=True)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Cache-Control'] = 'private, max-age=86400'
    return resp
