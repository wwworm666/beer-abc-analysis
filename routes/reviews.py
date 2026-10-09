"""Раздел «Гости» -> «Отзывы»: страница, API отзывов и полоса внимания хаба.

Хранилище, проверка полей, формулы метрик и порядок сортировки —
core/guest_reviews.py (докстринг модуля). Отзывы приходят с Яндекс Карт
(core/yandex_reviews_sync.py, раз в 3 часа) и из бота @kult_taplist_bot. Ответ на отзыв Яндекса публикуют в кабинете руками;
ответ на отзыв из бота владелец отправляет гостю кнопкой (send-reply ниже).

Эндпоинты:
    GET    /reviews                         страница (templates/reviews.html)
    GET    /api/reviews                     список + метрики; ?from=&to=|month=|all=1
                                            &bar=&source=&rating=low|mid|high|none
                                            &status=new|answered|skipped
    POST   /api/reviews                     {source, bar, rating?, author?, text?, created_at?,
                                             guest?, reply_draft?} -> {review}
    PATCH  /api/reviews/<id>                {bar?, rating?, author?, text?, created_at?, guest?,
                                             reply_draft?, source? (только ручные)} -> {review}
    DELETE /api/reviews/<id>                -> {deleted: true} (ручные и из бота; из Яндекса — 409)
    POST   /api/reviews/<id>/reply          {text} -> {review}
    POST   /api/reviews/<id>/send-reply     [?force=1] без тела -> {review, delivered_at}:
                                            сохранённый ответ уходит гостю в Telegram (только
                                            отзыв из бота); 400 — не из бота / чат неизвестен /
                                            ответа нет; 409 — уже отправлен (already_delivered),
                                            отправляется (sending), статус неизвестен
                                            (send_unknown: повтор только с force=1), гость
                                            заблокировал бота (guest_blocked), Telegram отклонил
                                            (telegram_rejected); 502 — статус неизвестен после
                                            этой попытки (send_unknown), Telegram недоступен
                                            (telegram_unavailable) или занят; 503 — нет
                                            TELEGRAM_BOT_TOKEN, хранилище занято, или ответ ушёл,
                                            а отметка не записалась (sent_not_recorded)
    POST   /api/reviews/<id>/action         {action: 'skip'|'reopen', reason?} -> {review}
    POST   /api/reviews/<id>/to-material    {month?} -> {review, material_id, month};
                                            409 {error, material_id}, если материал уже есть;
                                            ссылка на удалённый материал -> новый (200)
    GET    /api/reviews/daily               ?month=&bar=&source= -> {month, days}
    GET    /api/guest-hub/attention         ?bar= -> {reviews_unanswered, publications_today,
                                            delivery_errors, overdue, content_available}

Коды ответов: 400 — ошибка ввода {error}; 404 — нет отзыва; 409 — действие
недопустимо в текущем статусе; 503 {error, code: 'reviews_unavailable'} —
файл отзывов не читается (не перезаписывается); 503 {error, code:
'content_plan_unavailable'} — контент-план недоступен при «Сделать материалом».

Каждый отзыв в ответах (список, add/patch/reply/action, «Сделать материалом»)
несёт material_exists: true — материал из material_id есть в контент-плане;
false — ссылка есть, а материал удалён (интерфейс снова предлагает «Сделать
материалом»); null — ссылки нет или контент-план недоступен (не
проверялось). Проверка — _material_presence: один проход на запрос по всем
разным id (get_material_raw на каждый; обычно это единицы материалов), а без
ссылок контент-план не трогается вовсе.

Контент-план (core/content_plan.py) импортируется лениво: полоса внимания,
«Сделать материалом» и проверка material_exists. Его недоступность (нет
модуля, битый файл, любая ошибка) не ломает отзывы: полоса внимания отдаёт
число отзывов без ответа и null в счётчиках контент-плана, material_exists
становится null (никогда 500).
"""
import os
from functools import wraps

from flask import Blueprint, jsonify, render_template, request

from core.auth_guard import current_user
from core.guest_reviews import (BAR_KEYS, NETWORK_BAR, TEXT_SEND_UNKNOWN, ReviewConflict, ReviewNotFound,
                                ReviewStoreUnavailable, get_review_store, material_draft,
                                parse_month)

reviews_bp = Blueprint('reviews', __name__)

ATTENTION_CONTENT_KEYS = ('publications_today', 'delivery_errors', 'overdue')


def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _error(message: str, status: int = 400, **extra):
    payload = {'error': message}
    payload.update(extra)
    return jsonify(payload), status


def _guard(view):
    """Ошибки хранилища -> понятные коды: 400 / 404 / 409 / 503 (не 500 и не запись поверх)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except ReviewStoreUnavailable as e:
            return _error(str(e), 503, code='reviews_unavailable')
        except ReviewNotFound:
            return _error('Отзыв не найден', 404)
        except ReviewConflict as e:
            return _error(str(e), 409, **e.extra)
        except ValueError as e:
            return _error(str(e), 400)
    return wrapper


def _app_version() -> str:
    """Версия для ?v= (extensions.APP_VERSION выставляет app.py после импорта)."""
    try:
        import extensions
        return extensions.APP_VERSION
    except Exception:  # noqa: BLE001 — страница откроется и без версии
        return ''


def _content_plan_store():
    """Хранилище контент-плана; импорт ленивый — модуля может не быть или он сломан."""
    from core.content_plan import get_content_plan_store
    return get_content_plan_store()


def _material_presence(ids):
    """{material_id: есть ли материал в контент-плане} или None — «не проверялось».

    Один проход на запрос по всем разным id (их собирает
    core.guest_reviews.resolve_materials). ContentPlanNotFound от
    get_material_raw — материала нет (удалён) -> False. Любой другой сбой (нет
    модуля, ContentPlanUnavailable на битом файле, ошибка модуля) -> None для
    всех id: без проверки нельзя считать материал удалённым, а ответ по
    отзывам всё равно 200.
    """
    try:
        from core.content_plan import ContentPlanNotFound
        content = _content_plan_store()
    except Exception as e:  # noqa: BLE001 — ImportError и любые сбои модуля
        print(f'[REVIEWS] material check: content plan unavailable: {e!r}')
        return None
    found = {}
    for material_id in ids:
        try:
            content.get_material_raw(material_id)
        except ContentPlanNotFound:
            found[material_id] = False
            continue
        except Exception as e:  # noqa: BLE001 — ContentPlanUnavailable и любые сбои
            print(f'[REVIEWS] material check: content plan unavailable: {e!r}')
            return None
        found[material_id] = True
    return found


# ------------------------------------------------------------------ страница

@reviews_bp.route('/reviews')
def reviews_page():
    return render_template('reviews.html', app_version=_app_version())


# ------------------------------------------------------------------ отзывы

def _sync_state():
    """Сводка загрузки с Яндекс Карт (core/yandex_reviews_sync.public_state) или None при сбое."""
    try:
        from core.yandex_reviews_sync import public_state
        return public_state()
    except Exception as e:  # noqa: BLE001 — сводка сверки не должна ронять список
        print(f'[REVIEWS] yandex sync state unavailable: {e!r}')
        return None


@reviews_bp.route('/api/reviews', methods=['GET'])
@_guard
def list_reviews():
    payload = get_review_store().listing(request.args, material_lookup=_material_presence)
    payload['yandex_sync'] = _sync_state()
    return jsonify(payload)


@reviews_bp.route('/api/reviews', methods=['POST'])
@_guard
def add_review():
    store = get_review_store()
    review = store.add(_json_body(), current_user(), origin='manual')
    return jsonify({'review': store.decorate(review, _material_presence)})


@reviews_bp.route('/api/reviews/daily', methods=['GET'])
@_guard
def reviews_daily():
    args = request.args
    return jsonify(get_review_store().daily(month=(args.get('month') or '').strip() or None,
                                            bar=(args.get('bar') or '').strip() or None,
                                            source=(args.get('source') or '').strip().lower() or None))


@reviews_bp.route('/api/reviews/<review_id>', methods=['PATCH'])
@_guard
def update_review(review_id):
    store = get_review_store()
    review = store.update(review_id, _json_body(), current_user())
    return jsonify({'review': store.decorate(review, _material_presence)})


@reviews_bp.route('/api/reviews/<review_id>', methods=['DELETE'])
@_guard
def delete_review(review_id):
    get_review_store().delete(review_id)
    return jsonify({'deleted': True})


@reviews_bp.route('/api/reviews/<review_id>/reply', methods=['POST'])
@_guard
def reply_review(review_id):
    store = get_review_store()
    review = store.reply(review_id, _json_body().get('text'), current_user())
    return jsonify({'review': store.decorate(review, _material_presence)})


# ------------------------------------------------------------------ ответ гостю в Telegram

def _send_guest_message(token: str, chat_id: int, text: str, outcome: list = None):
    """Сообщение гостю от гостевого бота: sendMessage без разметки (текст ответа — как
    есть). Тот же HTTP-клиент с обходом блокировок, что у ботов сервиса
    (core/open_check_telegram.api_call), но с safe_resend=True: другим путём запрос
    повторяется, только если ошибка ДОКАЗЫВАЕТ, что он не дошёл. Без ключа api_call
    при ReadTimeout (сообщение уже у гостя) шёл на запасные адреса — гость получал ответ
    2–5 раз (проверка 2026-09-28). Ответ Telegram (dict) или None; причина None —
    в outcome: 'not_sent' (точно не ушло) или 'unknown' (могло дойти).
    Точка подмены в тестах: в настоящий Telegram тесты не ходят."""
    from core.open_check_telegram import api_call
    return api_call('sendMessage', {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True},
                    timeout=20, token=token, safe_resend=True, outcome=outcome)


def _send_outcome(result, outcome=None):
    """Ответ Telegram -> (итог, HTTP-статус, текст для владельца, code, message_id).

    итог: ok; unknown — ответа нет, а запрос мог дойти (outcome не 'not_sent'), 502
    send_unknown: захват остаётся, повтор только с подтверждением; unavailable — ответа
    нет, запрос точно не дошёл (502, повтор свободный); blocked — 403, гость
    заблокировал бота (409); rejected — 400, Telegram не принял сообщение, например чат
    удалён (409: повтор не поможет); busy — 429, Telegram просит подождать (502); прочая
    ошибка, которую Telegram ОТВЕТИЛ, — сообщение не отправлено (502 telegram_error).
    """
    if isinstance(result, dict) and result.get('ok'):
        message_id = (result.get('result') or {}).get('message_id') if isinstance(result.get('result'), dict) else None
        return 'ok', 200, None, None, message_id
    if not isinstance(result, dict):
        if result is None and outcome and outcome[-1] == 'not_sent':
            return ('unavailable', 502, 'Telegram недоступен — запрос не дошёл, ответ гостю не отправлен. '
                    'Попробуйте ещё раз.', 'telegram_unavailable', None)
        return 'unknown', 502, TEXT_SEND_UNKNOWN, 'send_unknown', None
    code = result.get('error_code')
    description = str(result.get('description') or '').strip()
    if code == 403:
        return ('blocked', 409, 'Гость заблокировал бота — ответ не доставлен. Свяжитесь с гостем иначе.',
                'guest_blocked', None)
    if code == 400:
        return ('rejected', 409, 'Telegram не принял сообщение' + (': ' + description if description else '') +
                ' — ответ не доставлен.', 'telegram_rejected', None)
    if code == 429:
        wait = (result.get('parameters') or {}).get('retry_after') if isinstance(result.get('parameters'), dict) else None
        return ('busy', 502, 'Telegram просит подождать' + (' %s с' % wait if wait else '') +
                ' — ответ не отправлен, попробуйте позже.', 'telegram_busy', None)
    return ('unavailable', 502, 'Telegram ответил ошибкой' + (' %s' % code if code else '') +
            (': ' + description if description else '') + ' — ответ не отправлен.', 'telegram_error', None)


def _scrub(exc) -> str:
    """Текст ошибки без токенов ботов (исключения requests содержат URL с токеном)."""
    try:
        from core.open_check_telegram import _scrub as scrub
        return scrub(exc)
    except Exception:  # noqa: BLE001 — логирование не должно падать
        return type(exc).__name__


def _mark_guest_blocked(chat_id) -> None:
    """403 от Telegram: гость заблокировал бота — рассылки ему тоже не слать."""
    try:
        from core import guest_subscribers
        guest_subscribers.mark_blocked(chat_id)
    except Exception as e:  # noqa: BLE001 — отметка подписчика не должна менять ответ
        print(f'[REVIEWS] mark_blocked({chat_id}): {e!r}')


@reviews_bp.route('/api/reviews/<review_id>/send-reply', methods=['POST'])
@_guard
def send_reply_to_guest(review_id):
    """Отправить сохранённый ответ гостю в Telegram — по явному нажатию владельца.

    Порядок: отзыв есть (404) -> проверки и «занять» отправку
    (ReviewStore.start_reply_delivery: 400 / 409; ?force=1 — повтор при «статус
    неизвестен» после подтверждения владельца) -> токен гостевого бота есть (иначе 503,
    захват снимается) -> sendMessage (safe_resend) -> итог:
      доставлено -> reply.delivered…; если отметка не записалась (любая ошибка
        хранилища: файл, замок, диск) — 503 sent_not_recorded, захват НЕ снимается:
        повтор только с подтверждением (гость ответ уже получил);
      статус неизвестен -> reply.send_unknown_at, 502 send_unknown;
      точно не ушло -> захват снимается, код и текст из _send_outcome, при 403 —
        core.guest_subscribers.mark_blocked.
    """
    user = current_user()
    # Правило раздела «Гости»: всё, что уходит наружу (публикации, рассылки, ответ
    # гостю), — только администратор. Бармен со своим входом отправить гостю не может.
    if not (user or {}).get('is_admin'):
        return jsonify({'error': 'Только администратор может отправить ответ гостю',
                        'code': 'admin_required'}), 403
    store = get_review_store()
    force = str(request.args.get('force') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    try:
        claim = store.start_reply_delivery(review_id, user, force=force)
    except (ReviewNotFound, ReviewConflict, ReviewStoreUnavailable, ValueError):
        raise
    except Exception as e:  # noqa: BLE001 — замок хранилища не взят и т.п.: ничего не отправлено
        print(f'[REVIEWS] send-reply {review_id}: claim failed: {e!r}')
        return _error('Хранилище отзывов занято — ответ не отправлен. Попробуйте ещё раз.', 503,
                      code='reviews_busy')
    token = (os.environ.get('TELEGRAM_BOT_TOKEN') or '').strip()
    if not token:
        store.finish_reply_delivery(review_id, user, outcome='not_sent')
        return _error('Гостевой бот не настроен (нет TELEGRAM_BOT_TOKEN) — ответ не отправлен', 503,
                      code='bot_not_configured')
    chat_id = claim['chat_id']
    outcome = []
    try:
        result = _send_guest_message(token, chat_id, claim['text'], outcome)
    except Exception as e:  # noqa: BLE001 — сбой транспорта: дошло ли — неизвестно
        print(f'[REVIEWS] send-reply {review_id}: {_scrub(e)}')
        result = None
        outcome.append('unknown')
    kind, status, message, code, message_id = _send_outcome(result, outcome)
    if kind == 'ok':
        try:
            review = store.finish_reply_delivery(review_id, user, outcome='sent', sent_text=claim['reply_text'],
                                                 message_id=message_id)
        except Exception as e:  # noqa: BLE001 — любая ошибка записи: сообщение уже у гостя
            print(f'[REVIEWS] send-reply {review_id}: sent, but not recorded: {e!r}')
            return _error('Ответ отправлен гостю, но отметка не сохранилась. Не отправляйте повторно: '
                          'повтор возможен только с подтверждением.', 503, code='sent_not_recorded')
        return jsonify({'review': store.decorate(review, _material_presence),
                        'delivered_at': review['reply']['delivered_at']})
    try:
        store.finish_reply_delivery(review_id, user, outcome='unknown' if kind == 'unknown' else 'not_sent')
    except Exception as e:  # noqa: BLE001 — захват останется и станет «статус неизвестен» — безопасно
        print(f'[REVIEWS] send-reply {review_id}: outcome not recorded: {e!r}')
    if kind == 'blocked':
        _mark_guest_blocked(chat_id)
    error_code = result.get('error_code') if isinstance(result, dict) else None
    print(f'[REVIEWS] send-reply {review_id}: {kind} {error_code}')
    return _error(message, status, code=code)


@reviews_bp.route('/api/reviews/<review_id>/action', methods=['POST'])
@_guard
def review_action(review_id):
    body = _json_body()
    action = str(body.get('action') or '').strip().lower()
    store = get_review_store()
    if action == 'skip':
        review = store.skip(review_id, body.get('reason'), current_user())
    elif action == 'reopen':
        review = store.reopen(review_id, current_user())
    else:
        return _error('Неизвестное действие: нужно skip или reopen')
    return jsonify({'review': store.decorate(review, _material_presence)})


@reviews_bp.route('/api/reviews/<review_id>/to-material', methods=['POST'])
@_guard
def review_to_material(review_id):
    """Материал контент-плана из отзыва: заголовок «Отзыв гостя — <бар>», текст-цитата.

    Порядок: отзыв есть (404) -> привязанного материала нет или он удалён
    (иначе 409 с его id) -> месяц (400) -> есть текст (400) -> создание в
    контент-плане (400 на его проверку, 503 на недоступность) -> привязка к
    отзыву. Если между проверкой и привязкой параллельный запрос успел
    привязать другой материал — 409 с его id (созданный вторым материал
    остаётся в плане, его можно удалить).

    Ссылка на материал, которого в контент-плане уже нет (его удалили), —
    устаревшая: создаётся новый материал, и ссылка заменяется
    (link_material(replace=<старый id>) — только если в отзыве всё ещё старый
    id). Если проверить материал нельзя (контент-план недоступен) — прежний
    409: без проверки ссылку не трогаем.
    """
    store = get_review_store()
    review = store.get(review_id)
    if review is None:
        raise ReviewNotFound(review_id)
    stale_id = None
    linked = review.get('material_id')
    if linked:
        presence = _material_presence([linked])
        if presence is None or presence.get(linked) is not False:
            return _error('Материал из этого отзыва уже создан', 409, material_id=linked)
        stale_id = linked   # материал удалён в контент-плане: делаем новый и заменяем ссылку
    raw_month = _json_body().get('month')
    month = parse_month(str(raw_month).strip()) if raw_month else store.now().strftime('%Y-%m')
    fields = material_draft(review)
    fields['month'] = month
    user = current_user()
    try:
        material = _content_plan_store().create_material(fields, user)
    except ValueError as e:
        return _error(str(e), 400)
    except Exception as e:  # noqa: BLE001 — ImportError, ContentPlanUnavailable и любые сбои модуля
        print(f'[REVIEWS] content plan unavailable for to-material: {e!r}')
        return _error('Контент-план недоступен: материал не создан. Попробуйте позже.', 503,
                      code='content_plan_unavailable')
    material_id = material.get('id') if isinstance(material, dict) else None
    if not material_id:
        return _error('Контент-план не вернул id материала', 503, code='content_plan_unavailable')
    review = store.link_material(review_id, material_id, user, replace=stale_id)
    # Материал только что создан — существует без повторного чтения контент-плана.
    return jsonify({'review': store.decorate(review, lambda ids: {material_id: True}),
                    'material_id': material_id, 'month': material.get('month') or month})


# ------------------------------------------------------------------ хаб

@reviews_bp.route('/api/guest-hub/attention', methods=['GET'])
def hub_attention():
    """Счётчики полосы внимания хаба «Гости».

    reviews_unanswered — отзывы со статусом «без ответа» за всё время (бар X — только X);
    publications_today / delivery_errors / overdue — core.content_plan.attention_counts(bar)
    (размещения бара X и сетевые 'all'). Недоступный источник -> null в его счётчиках,
    content_available=false; ответ всегда 200 (кроме неизвестного бара — 400).
    """
    bar = (request.args.get('bar') or '').strip()
    if bar and bar != NETWORK_BAR and bar not in BAR_KEYS:
        return _error(f'Неизвестный бар «{bar}»')
    bar_filter = bar if bar in BAR_KEYS else None
    payload = {'reviews_unanswered': None}
    try:
        payload['reviews_unanswered'] = get_review_store().unanswered_count(bar_filter)
    except Exception as e:  # noqa: BLE001 — полоса внимания не должна ронять страницу
        print(f'[REVIEWS] attention: reviews unavailable: {e!r}')
    counts = None
    try:
        counts = _content_plan_store().attention_counts(bar=bar_filter)
    except Exception as e:  # noqa: BLE001 — ImportError, ContentPlanUnavailable и любые сбои
        print(f'[REVIEWS] attention: content plan unavailable: {e!r}')
    content_ok = isinstance(counts, dict)
    for key in ATTENTION_CONTENT_KEYS:
        value = counts.get(key) if content_ok else None
        payload[key] = value if isinstance(value, int) and not isinstance(value, bool) else None
    payload['content_available'] = content_ok
    return jsonify(payload)
