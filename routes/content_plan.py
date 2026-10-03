"""Раздел «Гости» -> «Контент-план»: страница и HTTP API.

Модель, правила готовности, переходы статусов, копирование месяца и живые
данные — core/content_plan.py (докстринг модуля); файлы фото/видео —
core/content_media.py; отправка в площадки — core/content_publisher.py, настройки
каналов — core/content_channels.py. Этот модуль только разбирает запрос, зовёт
хранилища и переводит их исключения в коды ответа. Отправка — только то, что
владелец включил в «Каналы и отправка»; остальное «вышло» отмечают вручную.

Эндпоинты:
    GET    /content-plan                                  страница (templates/content_plan.html)
    GET    /api/content-plan?month=YYYY-MM                материалы месяца + справочники + stats
                                                          + delivery (что подключено к отправке) и
                                                          delivery_connected (прежний вид); размер
                                                          аудиторий бота — настоящий (месяц по
                                                          умолчанию — текущий по Москве;
                                                          scope='month'); &compact=1 — компактный
                                                          вид для агента (content_plan.compact_material)
    GET    /api/content-plan?state=overdue|failed         БЕЗ month — вид «по всем месяцам»: материалы
                                                          любого месяца с размещением в этом
                                                          состоянии (scope='state', state; см.
                                                          ContentPlanStore.state_payload). С month
                                                          или с другим state — обычный месяц: фильтр
                                                          ?state= применяет экран
    GET    /api/content-plan/materials/<id>               {material} (для deep-link ?open=)
    POST   /api/content-plan/materials                    {month, title, kind?, live_source?,
                                                           planned_date?, base_text?, note?,
                                                           media_required?, agent_rationale?,
                                                           shot_list?} -> {material}
                                                          (origin ставит сервер: через MCP — 'agent')
    PATCH  /api/content-plan/materials/<id>               {title?, kind?, live_source?, planned_date?,
                                                           base_text?, note?, media_required?,
                                                           agent_rationale?, shot_list?}
                                                          -> {material, unapproved}; origin — 400
    DELETE /api/content-plan/materials/<id>               -> {deleted: true}; 409 при вышедших
    POST   /api/content-plan/materials/<id>/placements    {channel, bars:[..], date?, time?, text?,
                                                           media?, audience?} -> {material, created}
    PATCH  /api/content-plan/placements/<pid>             {channel?, bar?, date?, time?, text?, media?,
                                                           audience?} -> {material, unapproved}
    DELETE /api/content-plan/placements/<pid>             -> {material}; 409 если вышло
    POST   /api/content-plan/placements/<pid>/action      {action} -> {material, notice?}; 409 — не тот
                                                          статус; retry / retry_failed / resume — только
                                                          администратор (403 admin_required); пауза или
                                                          отмена идущей рассылки — notice «остановится
                                                          после текущей пачки»
    POST   /api/content-plan/materials/<id>/shift         {days} -> {material}
    POST   /api/content-plan/materials/<id>/repeat        {weekdays:[0..6], month?} -> {created}
                                                          (month по умолчанию — месяц материала)
    POST   /api/content-plan/materials/<id>/media         multipart 'file' -> {material, unapproved}
    DELETE /api/content-plan/materials/<id>/media/<name>  -> {material, unapproved}
    GET    /api/content-plan/media/<name>                 файл; 404 на неверное/неизвестное имя
    POST   /api/content-plan/image-search                 {q, orientation?, site?, page?} -> {search_id,
                                                          candidates [{candidate, n, width, height,
                                                          format, domain, title, page_url,
                                                          image_url}], dropped, collage,
                                                          searches_today, daily_limit} — поиск картинок
                                                          в интернете (Yandex Search API,
                                                          core/content_image_search.py); только
                                                          администратор; 429 — суточный предел (сеть
                                                          и подключение); 502 — Яндекс не ответил;
                                                          503 — ключ не настроен
    GET    /api/content-plan/image-search/<id>/collage    JPEG: варианты поиска одной картинкой с
                                                          номерами; 404 — поиска нет (хранится 3 сут.)
    POST   /api/content-plan/materials/<id>/media/found   {candidate} -> {material, unapproved, file}:
                                                          сервер скачивает вариант из своего файла
                                                          поиска, готовит JPEG и привязывает с
                                                          media[].source; 400 image_download_failed
    GET    /api/content-plan/approve-preview              ?month=&bar=&channel=&origin= -> {month,
                                                          will_approve, bot, stays_draft}; origin
                                                          (agent|human) — фильтр «Только от ИИ»
    POST   /api/content-plan/approve                      {placement_ids:[..], confirm_bot?}
                                                          -> {approved, skipped}; только администратор
    POST   /api/content-plan/bulk-pause                   {bar, action:'pause'|'resume'}
                                                          -> {changed, skipped}; resume — только
                                                          администратор
    POST   /api/content-plan/bulk                         {material_ids:[..], action:'shift'|'delete'|
                                                           'cancel', days?} -> {done, failed:[{id, error}]}
    POST   /api/content-plan/agent-drafts/delete          {month, material_ids?} -> {deleted: [id],
                                                          skipped: [{id, reason}]} — «Удалить черновики
                                                          ИИ»: материалы месяца с origin 'agent', у
                                                          которых все размещения draft или cancelled
                                                          (см. ContentPlanStore.delete_agent_drafts)
    POST   /api/content-plan/copy-month                   {from?, to, with_content?} -> {created, notes}
                                                          (from по умолчанию — месяц перед to)
    GET    /api/content-plan/brief                        бриф сети для ИИ-агента -> {brief, stored,
                                                          total, schema} (core/content_brief.py)
    PUT    /api/content-plan/brief                        {sections: {...частично}} -> {brief, stored,
                                                          total, changed}; сливает переданные поля,
                                                          неизвестные — 400
    GET    /api/content-plan/live-preview                 ?source=&bar=&material_id=&placement_id=&date=
                                                          &template=&channel=&has_media=
                                                          -> render_live (POST с тем же JSON — для
                                                          длинного шаблона, который не влезает в URL);
                                                          предел длины — по площадке (channel) и
                                                          наличию фото (has_media), см. live_preview
    GET    /api/content-plan/materials/<id>/log           -> {entries: [новые сверху]}
    GET    /api/content-plan/materials/<id>/download      zip: тексты по размещениям, файлы и опись
                                                          (для ручного Instagram)
    GET    /api/content-plan/channels                     -> {channels (без токена), bot_username,
                                                          token_source: content|taplist|null, delivery,
                                                          delivery_connected, subscribers_total, limits}
    PUT    /api/content-plan/channels                     {enabled?, telegram?: {бар: {chat?, title?}},
                                                           instagram?: {reminder_chat?,
                                                           reminder_minutes_before?}, bot?: {enabled?,
                                                           signup?}} -> как GET; частичное слияние,
                                                          неизвестное — 400 (signup — кнопки подписки
                                                          и отзыва в гостевом боте)
    POST   /api/content-plan/channels/check               {bar} -> {check, saved, ...как GET} —
                                                          getMe/getChat/getChatMember в Telegram; сбой
                                                          связи — saved=false, прежняя проверка остаётся
    POST   /api/content-plan/channels/test                {bar} -> {ok, message_id, error, chat} —
                                                          сообщение «Проверка связи с сайтом» в канал
    POST   /api/content-plan/publish-now                  {placement_id} -> {placement, material,
                                                          queued: true, message}: в очередь, уйдёт в
                                                          течение минуты (отправляет планировщик); 409 —
                                                          не утверждено, отправляется, отправка
                                                          выключена, площадка не подключена
    GET    /api/content-plan/audience?segment=&bar=       -> {segment, name, bar, size, size_note,
                                                          subscribers_total} — подписчики бота на сейчас
    GET    /api/content-plan/agent-edits?months=3         -> {months, from_month, now, counts, items} —
                                                          правки людей в материалах агента (1..12 мес.)

Необязательный ?month=YYYY-MM у изменяющих запросов задаёт месяц просмотра:
по нему считается in_month материала в ответе (без него — true).

Коды ответов: 400 — ошибка ввода {error}; 404 — нет материала/размещения/файла;
409 — действие недопустимо в текущем статусе (+ поля из исключения); 413 —
тело загрузки больше предела видео; 503 {error, code: 'content_plan_unavailable'}
— файл плана есть, но не читается (он НЕ перезаписывается); 503 {error, code:
'content_brief_unavailable'} — то же для файла брифа; 503 {error, code:
'content_channels_unavailable'} — то же для настроек каналов. Поиск картинок: 503
image_search_not_configured, 502 image_search_failed, 429 image_search_daily_limit,
400 image_download_failed.

Только администратор (403 {error, code: 'admin_required'}): PUT /channels, POST
/channels/check, /channels/test, /publish-now, /approve, действия retry, retry_failed,
resume и bulk-pause с action resume — всё, что может выпустить публикацию наружу; POST
/image-search — запрос в Яндекс платный.

Отправка в тестах: _transport, _guest_transport, _bot_token, _guest_bot_token, _channels,
_audience и _subscribers_total — точки подмены (как _store); в настоящий Telegram
тесты не ходят. Два бота: бот каналов (_transport: TELEGRAM_CONTENT_BOT_TOKEN, иначе
TELEGRAM_BOT_TOKEN) — посты, проверка, тест, напоминание; гостевой (_guest_transport:
только TELEGRAM_BOT_TOKEN) — рассылки гостям (см. core/content_channels.py).

ИИ-агент (MCP): мост core/mcp/bridge.py исполняет эти же маршруты от имени
владельца с 'via_mcp': True в current_user(). По нему хранилище ставит origin
новых материалов ('agent') и подписывает журнал «<login> · агент» — маршрутам
ничего передавать не нужно (core/content_plan.py, раздел «ИИ-агент»).
"""
import io
from functools import wraps

from flask import Blueprint, jsonify, render_template, request, send_file, send_from_directory

from core import content_channels, content_image_search, content_media, content_publisher
from core.auth_guard import current_user
from core.content_brief import ContentBriefUnavailable, get_content_brief_store
from core.content_channels import ContentChannelsUnavailable, get_channels_store
from core.content_image_search import (ImageDownloadFailed, ImageSearchFailed, ImageSearchLimit,
                                       ImageSearchNotConfigured, ImageSearchNotFound)
from core.content_plan import (AUDIENCE_BY_KEY, BAR_ALL, CHANNELS, CROSS_MONTH_STATES, MATERIAL_MEDIA_MAX,
                               ContentPlanConflict, ContentPlanNotFound, ContentPlanUnavailable, add_months,
                               get_content_plan_store, guard_draft_mode, parse_bar, parse_bool, parse_date,
                               parse_days, parse_month, placement_content, render_live)

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


class AdminRequired(Exception):
    """Действие только для администратора (API 403, code 'admin_required')."""


# Что может выпустить публикацию наружу — только администратор (решение
# оркестратора 2026-09-28 по итогам проверки: у каждого бармена личный вход, все
# аккаунты равны, лимита попыток входа нет). Чтение (каналы, аудитория, zip) — всем.
# MCP работает от имени администратора-владельца (мост), его это не ограничивает.
ADMIN_PLACEMENT_ACTIONS = {'retry': 'повторять отправку', 'retry_failed': 'повторять рассылку',
                           'resume': 'снимать публикации с паузы'}


def _require_admin(what: str) -> None:
    user = current_user() or {}
    if not user.get('is_admin'):
        raise AdminRequired(f'Только администратор может {what}')


def _guard(view):
    """Исключения хранилища -> 400 / 403 / 404 / 409 / 503 (не 500 и не запись поверх)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except AdminRequired as e:
            return _error(str(e), 403, code='admin_required')
        except ContentPlanUnavailable as e:
            return _error(str(e), 503, code='content_plan_unavailable')
        except ContentBriefUnavailable as e:
            return _error(str(e), 503, code='content_brief_unavailable')
        except ContentChannelsUnavailable as e:
            return _error(str(e), 503, code='content_channels_unavailable')
        except ImageSearchNotConfigured as e:
            return _error(str(e), 503, code='image_search_not_configured')
        except ImageSearchFailed as e:
            return _error(str(e), 502, code='image_search_failed')
        except ImageSearchLimit as e:
            return _error(str(e), 429, code='image_search_daily_limit')
        except (ContentPlanNotFound, ImageSearchNotFound) as e:
            return _error(str(e), 404)
        except ContentPlanConflict as e:
            return _error(str(e), 409, **e.extra)
        except ImageDownloadFailed as e:
            return _error(str(e), 400, code='image_download_failed')
        except ValueError as e:
            return _error(str(e), 400)
    return wrapper


def _store():
    """Хранилище плана (отдельная функция — тесты подменяют её временным файлом)."""
    return get_content_plan_store()


def _brief_store():
    """Хранилище брифа для агента (тесты подменяют так же, как _store)."""
    return get_content_brief_store()


def _image_finder():
    """Поиск картинок (core/content_image_search.py): ключ Яндекса из окружения, поиски
    на постоянном диске. Тесты подменяют поддельным Яндексом и сайтами."""
    return content_image_search.get_finder()


# ---- отправка: точки подмены для тестов (в настоящий Telegram тесты не ходят) ----

def _channels():
    """Настройки каналов и выключатели отправки (core/content_channels.py)."""
    return get_channels_store()


def _bot_token():
    """(токен, источник) бота каналов — content_channels.channel_bot_token."""
    return content_channels.channel_bot_token()


def _guest_bot_token():
    """(токен, источник) гостевого бота — только TELEGRAM_BOT_TOKEN (рассылки гостям)."""
    return content_channels.guest_bot_token()


def _transport():
    """Транспорт бота каналов (посты, проверка, тест, напоминание) или None."""
    token, _source = _bot_token()
    return content_publisher.TelegramTransport(token) if token else None


def _guest_transport():
    """Транспорт гостевого бота @kult_taplist_bot (рассылки гостям) или None."""
    token, _source = _guest_bot_token()
    return content_publisher.TelegramTransport(token) if token else None


def _audience(segment, bar):
    """(размер, пояснение) аудитории рассылки бота на сейчас."""
    return content_channels.audience_size(segment, bar)


def _subscribers_total():
    """Сколько гостей подписано на рассылки сейчас (None — не прочиталось)."""
    return content_channels.subscribers_total()


def _channels_payload(settings: dict) -> dict:
    """Ответ маршрутов настроек каналов: сами настройки (без токена), имя бота,
    откуда токен, что подключено (delivery) и пределы полей формы."""
    token, source = _bot_token()
    guest, guest_source = _guest_bot_token()
    total = _subscribers_total()
    delivery = content_channels.delivery_state(settings, bool(token), total, guest_token_present=bool(guest))
    return {'channels': content_channels.public_view(settings),
            'bot_username': content_channels.bot_username(settings, token),
            'token_source': source, 'guest_token_source': guest_source, 'delivery': delivery,
            'delivery_connected': content_channels.delivery_connected(delivery),
            'subscribers_total': total,
            'limits': {'reminder_minutes_max': content_channels.REMINDER_MINUTES_MAX,
                       'title_max': content_channels.TITLE_MAX}}


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
    (ссылки полосы внимания: их счётчики считают любой месяц). ?compact=1 —
    компактный вид для агента: материалы без текстов, файлов и справочников."""
    store = _store()
    raw = (request.args.get('month') or '').strip()
    state = (request.args.get('state') or '').strip()
    raw_compact = request.args.get('compact')
    compact = parse_bool(raw_compact, 'Компактный вид') if raw_compact not in (None, '') else False
    if not raw and state in CROSS_MONTH_STATES:
        return jsonify(store.state_payload(state, compact=compact))
    month = parse_month(raw) if raw else _current_month(store)
    return jsonify(store.month_payload(month, compact=compact))


@content_plan_bp.route('/api/content-plan/materials/<material_id>', methods=['GET'])
@_guard
def get_material(material_id):
    return jsonify({'material': _store().get_material(material_id, _view_month())})


@content_plan_bp.route('/api/content-plan/materials/<material_id>/log', methods=['GET'])
@_guard
def material_log(material_id):
    return jsonify({'entries': _store().log_for(material_id)})


@content_plan_bp.route('/api/content-plan/materials/<material_id>/download', methods=['GET'])
@_guard
def download_material(material_id):
    """zip для ручного Instagram: тексты по размещениям, файлы и опись
    (content_publisher.build_material_zip). 404 — материала нет."""
    store = _store()
    material = store.get_material_raw(material_id)
    archive = content_publisher.build_material_zip(store, material)
    return send_file(archive, mimetype='application/zip', as_attachment=True,
                     download_name=f'kultura_{material["id"]}.zip', max_age=0)


@content_plan_bp.route('/api/content-plan/agent-edits', methods=['GET'])
@_guard
def agent_edits():
    """Правки людей в материалах агента за ?months= (1..12, по умолчанию 3) —
    чтобы агент подстраивал тон (ContentPlanStore.agent_edits)."""
    return jsonify(_store().agent_edits(request.args.get('months')))


@content_plan_bp.route('/api/content-plan/audience', methods=['GET'])
@_guard
def audience():
    """Размер аудитории рассылки бота на сейчас: ?segment= (обязателен), ?bar=
    (пусто или all — вся сеть). Сегменту «выбравшие бар» без бара — size null."""
    segment = (request.args.get('segment') or '').strip()
    spec = AUDIENCE_BY_KEY.get(segment)
    if spec is None:
        raise ValueError('Аудитория: bot_all, bot_bar, bot_recent_30 или bot_lapsed_60')
    raw_bar = (request.args.get('bar') or '').strip()
    bar = None if raw_bar in ('', BAR_ALL) else parse_bar(raw_bar)
    size, note = _audience(segment, bar)
    return jsonify({'segment': segment, 'name': spec['name'], 'bar': bar or BAR_ALL, 'size': size,
                    'size_note': note, 'subscribers_total': _subscribers_total()})


# ------------------------------------------------------------------ каналы и отправка

@content_plan_bp.route('/api/content-plan/channels', methods=['GET'])
@_guard
def get_channels():
    """Настройки «Каналы и отправка» (без токена) и что подключено."""
    return jsonify(_channels_payload(_channels().load()))


@content_plan_bp.route('/api/content-plan/channels', methods=['PUT'])
@_guard
def update_channels():
    """Частичная правка настроек каналов (content_channels.ChannelsStore.update):
    неизвестный ключ, бар или поле, неверный адрес — 400, не сохраняется ничего.
    Только администратор (403 admin_required)."""
    _require_admin('менять каналы и отправку')
    settings = _channels().update(request.get_json(silent=True), current_user())
    return jsonify(_channels_payload(settings))


def _bar_from_body() -> str:
    bar = str(_json_body().get('bar') or '').strip()
    if not bar:
        raise ValueError('Не выбран бар')
    return bar


@content_plan_bp.route('/api/content-plan/channels/check', methods=['POST'])
@_guard
def check_channel():
    """Проверить канал бара в Telegram (getMe, getChat, getChatMember); итог
    сохраняется у бара (сбой связи — нет: saved=false, прежняя проверка остаётся).
    Ошибка Telegram — не ошибка запроса: 200 и check.ok=false. Только администратор."""
    _require_admin('проверять каналы')
    result = content_publisher.check_channel(_bar_from_body(), current_user(), transport=_transport(),
                                             channels=_channels())
    payload = _channels_payload(result['channels'])
    payload.update({'check': result['check'], 'saved': result['saved']})
    return jsonify(payload)


@content_plan_bp.route('/api/content-plan/channels/test', methods=['POST'])
@_guard
def test_channel():
    """Тестовое сообщение «Проверка связи с сайтом» в канал бара -> {ok, message_id,
    error, chat}. Его видят подписчики канала. Только администратор."""
    _require_admin('отправлять тестовое сообщение')
    return jsonify(content_publisher.send_test(_bar_from_body(), current_user(), transport=_transport(),
                                               channels=_channels()))


@content_plan_bp.route('/api/content-plan/publish-now', methods=['POST'])
@_guard
def publish_now():
    """«Отправить сейчас»: утверждённое размещение встаёт в очередь, его отправит
    планировщик в течение минуты (content_publisher.publish_now) -> {placement,
    material, queued: true, message}. Только администратор."""
    _require_admin('отправлять публикации')
    placement_id = str(_json_body().get('placement_id') or '').strip()
    if not placement_id:
        raise ValueError('Не выбрано размещение')
    return jsonify(content_publisher.publish_now(placement_id, current_user(), store=_store(),
                                                 channels=_channels(), transport=_transport(),
                                                 guest_transport=_guest_transport()))


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
    """Переход статуса размещения. retry, retry_failed и resume выпускают
    публикацию наружу — только администратор (403). Пауза или отмена идущей
    рассылки ставит её остановку: в ответе notice «остановится после текущей пачки»."""
    action = str(_json_body().get('action') or '').strip()
    if action in ADMIN_PLACEMENT_ACTIONS:
        _require_admin(ADMIN_PLACEMENT_ACTIONS[action])
    material = _store().placement_action(placement_id, action, current_user(), _view_month())
    payload = {'material': material}
    view = next((p for p in material.get('placements') or [] if p.get('id') == placement_id), None)
    if view and (view.get('delivery') or {}).get('stop_requested'):
        payload['notice'] = 'Рассылка остановится после текущей пачки: получившим повторно не уйдёт'
    return jsonify(payload)


# ------------------------------------------------------------------ утверждение и массовые

@content_plan_bp.route('/api/content-plan/approve-preview', methods=['GET'])
@_guard
def approve_preview():
    """Что утвердит «Утвердить готовые». ?origin=agent|human — только материалы
    этого происхождения (фильтр «Только от ИИ» на экране)."""
    store = _store()
    args = request.args
    raw = (args.get('month') or '').strip()
    month = parse_month(raw) if raw else _current_month(store)
    return jsonify(store.approve_preview(month, bar=args.get('bar'), channel=args.get('channel'),
                                         origin=args.get('origin')))


@content_plan_bp.route('/api/content-plan/approve', methods=['POST'])
@_guard
def approve():
    """Утвердить готовые черновики. Утверждённое уходит само, если площадка
    подключена, — только администратор (403 admin_required)."""
    _require_admin('утверждать публикации')
    body = _json_body()
    return jsonify(_store().approve(body.get('placement_ids'), current_user(),
                                    confirm_bot=body.get('confirm_bot', False)))


@content_plan_bp.route('/api/content-plan/bulk-pause', methods=['POST'])
@_guard
def bulk_pause():
    """Пауза или снятие паузы по бару или сети. Снятие паузы выпускает публикации —
    только администратор; пауза — всем (остановить можно любому)."""
    body = _json_body()
    action = str(body.get('action') or '').strip()
    if action == 'resume':
        _require_admin('снимать публикации с паузы')
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


@content_plan_bp.route('/api/content-plan/agent-drafts/delete', methods=['POST'])
@_guard
def delete_agent_drafts():
    """«Удалить черновики ИИ»: {month, material_ids?} -> {deleted, skipped}.

    Удаляет материалы плана месяца month с origin 'agent', у которых все
    размещения — черновики или отменены (ContentPlanStore.delete_agent_drafts).
    material_ids сужает набор (экран шлёт ровно те id, число которых показал
    в подтверждении); без них — все черновики агента месяца. Всё одной
    записью; то, что удалить нельзя, — в skipped с причиной. 400 — нет или
    неверный month, material_ids не список, пустой или длиннее BULK_MAX."""
    body = _json_body()
    ids = body.get('material_ids')
    if isinstance(ids, list) and len(ids) > BULK_MAX:
        return _error(f'За один раз — не больше {BULK_MAX} материалов')
    return jsonify(_store().delete_agent_drafts(body.get('month'), current_user(), material_ids=ids))


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


# ------------------------------------------------------------------ бриф для агента

@content_plan_bp.route('/api/content-plan/brief', methods=['GET'])
@_guard
def get_brief():
    """Бриф сети для ИИ-агента: {brief, stored, total, schema}.

    stored=false — файла ещё нет, показана затравка (бары из справочника);
    schema — подписи, подсказки и пределы полей, назначение брифа и правила
    слияния (core/content_brief.py). 503 — файл брифа не читается."""
    return jsonify(_brief_store().payload())


@content_plan_bp.route('/api/content-plan/brief', methods=['PUT'])
@_guard
def update_brief():
    """Правка брифа: {sections: {...частично}} -> {brief, stored, total, changed}.

    Меняются только переданные поля (bars — по барам и полям, examples —
    целым списком); неизвестный ключ, раздел, бар или поле, неверный тип,
    превышение предела — 400, не сохраняется ничего; 503 — файл не читается
    (не перезаписывается). Подпись updated_by через MCP — «<login> · агент»."""
    body = request.get_json(silent=True)
    return jsonify(_brief_store().update(body, current_user()))


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


# ------------------------------------------------------- картинки из интернета

@content_plan_bp.route('/api/content-plan/image-search', methods=['POST'])
@_guard
def image_search():
    """Найти картинки к посту (core/content_image_search.py): {q, orientation?, site?, page?}
    -> до 12 вариантов и id поиска. POST, а не GET: поиск пишет файл поиска и тратит платный
    суточный предел — это запись (в MCP — черновик, в коннекторе «Только чтение» его нет).
    Только администратор: запрос в Яндекс платный (MCP работает от имени владельца). Предел
    считается и на подключение: подключение MCP (mcp_connection_id — грант OAuth или
    статический токен; не id OAuth-токена, он меняется каждый час) или вход человека.
    Ответы: 400 — неверный запрос; 429 — суточный предел поисков; 502 — Яндекс не
    ответил; 503 — ключ Яндекса не настроен."""
    _require_admin('искать картинки (запрос в Яндекс платный)')
    body = _json_body()
    user = current_user() or {}
    caller = (str(user.get('mcp_connection_id') or user.get('mcp_token_id') or '')
              or ('login:' + str(user.get('login') or '')))
    return jsonify(_image_finder().search(body.get('q'), orientation=body.get('orientation'),
                                          site=body.get('site'), page=body.get('page'), caller=caller))


@content_plan_bp.route('/api/content-plan/image-search/<search_id>/collage', methods=['GET'])
@_guard
def image_search_collage(search_id):
    """Коллаж вариантов поиска одной картинкой JPEG: номер, размер оригинала, домен.
    404 — поиска нет или он устарел (хранится 3 суток)."""
    data = _image_finder().collage(search_id)
    resp = send_file(io.BytesIO(data), mimetype='image/jpeg', download_name=search_id + '.jpg')
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Cache-Control'] = 'private, max-age=3600'
    return resp


@content_plan_bp.route('/api/content-plan/materials/<material_id>/media/found', methods=['POST'])
@_guard
def add_found_media(material_id):
    """Прикрепить к материалу вариант из поиска: {candidate} -> {material, unapproved, file}.
    Порядок: материал есть (404), режим черновиков пускает (409), предел файлов (400) ->
    сервер сам скачивает картинку по адресу ИЗ СВОЕГО файла поиска (адрес из запроса не
    принимается) и готовит JPEG (400 image_download_failed — сайт не отдал, мелкая,
    не картинка) -> запись на диск -> привязка с media[].source. Не привязалось — файл
    удаляется, сирот не остаётся."""
    candidate = _json_body().get('candidate')
    store = _store()
    user = current_user()
    material = store.get_material_raw(material_id)
    guard_draft_mode(user, material)
    if len(material.get('media') or []) >= MATERIAL_MEDIA_MAX:
        return _error(f'У материала уже {MATERIAL_MEDIA_MAX} файлов — удалите лишние')
    data, source = _image_finder().download(candidate)
    ok, name_or_err = store.media.save(data, store.today())
    if not ok:
        return _error(name_or_err)
    try:
        material_view, unapproved = store.add_media(
            material_id, name_or_err, len(data),
            content_image_search.found_media_name(source.get('domain'), name_or_err),
            user, _view_month(), source=source)
    except Exception:
        store.media.delete(name_or_err)
        raise
    return jsonify({'material': material_view, 'unapproved': unapproved,
                    'file': {'name': name_or_err, 'size': len(data), 'width': source.get('width'),
                             'height': source.get('height'), 'source': source}})
