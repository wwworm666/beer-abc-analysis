"""Раздел «Гости» -> «Отзывы»: страница, API отзывов и полоса внимания хаба.

Хранилище, проверка полей, формулы метрик и порядок сортировки —
core/guest_reviews.py (докстринг модуля). Интеграций нет: отзывы вносятся
вручную, ответ никуда не отправляется.

Эндпоинты:
    GET    /reviews                         страница (templates/reviews.html)
    GET    /api/reviews                     список + метрики; ?from=&to=|month=|all=1
                                            &bar=&source=&rating=low|mid|high|none
                                            &status=new|answered|skipped
    POST   /api/reviews                     {source, bar, rating?, author?, text?, created_at?,
                                             guest?, reply_draft?} -> {review}
    PATCH  /api/reviews/<id>                {bar?, rating?, author?, text?, created_at?, guest?,
                                             reply_draft?, source? (только ручные)} -> {review}
    DELETE /api/reviews/<id>                -> {deleted: true} (только ручные, иначе 409)
    POST   /api/reviews/<id>/reply          {text} -> {review}
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
from functools import wraps

from flask import Blueprint, jsonify, render_template, request

from core.auth_guard import current_user
from core.guest_reviews import (BAR_KEYS, NETWORK_BAR, ReviewConflict, ReviewNotFound,
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
    """Сводка сверки с Яндекс Бизнесом (core/yandex_reviews_sync.public_state) или None при сбое."""
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
