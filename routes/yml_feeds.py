"""Страница /yandex: правки позиций в фидах Яндекса, её API и публичный фид бара.

Документация: docs/yandex-feeds.md.
"""
from datetime import datetime

from flask import Blueprint, jsonify, make_response, render_template, request

from core import yml_scheduler as scheduler
from core.kitchen_menu import catalog_offers
from core.kitchen_yml import offers_for_bar
from core.taplist import BAR_NAMES
from core.taplist_yml import SHOP_COMPANY, beer_offers, build_yml
from core.yml_feeds import (
    FEED_ORDER, KITCHEN_SCOPE, bar_scoped, combine_offers, feed_by_id, feed_catalog,
    overrides_for_bar,
)
from core.yml_overrides import (
    OverrideConflict, OverridesCorrupted, apply_changes, ensure_schema, load_document,
    load_overrides, merge_offer, merge_offers, notice_key, set_acks,
)

yml_bp = Blueprint('yml_feeds', __name__)
_schema_ready = False


@yml_bp.after_request
def _no_store(response):
    # Данные страницы меняются правками и снимком — браузер не должен их кэшировать.
    if request.path.startswith('/api/yml/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def _public_url(path):
    base = (request.url_root or '').rstrip('/')
    return base + path


def kitchen_ids():
    return {item['id'] for item in catalog_offers()}


def _tap_to_beer():
    """{(бар, кран): id сорта Untappd} по текущему таплисту — для переноса старых правок."""
    from extensions import taps_manager
    from core.taplist import full_taplist, product_catalog
    from core.untappd_registry import load_registry
    registry = load_registry()
    rows = full_taplist(taps_manager.get_snapshot(product_catalog(registry)), registry)
    return {(row['bar_id'], row['tap_number']): str(row['untappd_beer_id'])
            for row in rows if row.get('mapping_status') == 'verified' and row.get('untappd_beer_id')}


def ensure_overrides_schema():
    """Правки старой схемы (по кранам) переносятся один раз при первом обращении."""
    global _schema_ready
    if _schema_ready:
        return
    ensure_schema(kitchen_ids(), _tap_to_beer)
    _schema_ready = True


def bar_state(bar_id):
    """Пиво бара: из снимка, а до первого снимка — прямо сейчас из iiko.

    -> (позиции пива, не попавшие в фид, сведения о снимке)
    """
    data = scheduler.load_snapshot()
    status = scheduler.snapshot_status(data or {})
    if scheduler.snapshot_ok(data) and isinstance(data['bars'].get(bar_id), dict):
        bar = data['bars'][bar_id]
        return bar.get('beer') or [], bar.get('excluded') or [], {
            **status, 'source': 'snapshot', 'error': bar.get('error'),
            'beer_updated_at': bar.get('beer_updated_at')}
    from routes.taps import PriceUnavailable, load_reviewed_taplist
    info = {**status, 'source': 'live', 'error': None, 'beer_updated_at': None}
    try:
        beer, excluded = beer_offers(load_reviewed_taplist(bar_id, True))
    except PriceUnavailable:
        beer, excluded = [], []
        info['error'] = 'Прайс iiko сейчас недоступен, пиво не показано. Нажмите «Переснять» позже.'
    return beer, excluded, info


def bar_items(bar_id):
    """Кухня и пиво одной точки в порядке файла, без правок."""
    beer, _, _ = bar_state(bar_id)
    return combine_offers(offers_for_bar(bar_id), beer)


def render_bar_feed(bar_id):
    ensure_overrides_schema()
    items = merge_offers(bar_items(bar_id), overrides_for_bar(load_overrides(), bar_id))
    return build_yml(items=items, shop_name=f'{SHOP_COMPANY}, {BAR_NAMES[bar_id]}')


def notices_for(item, acks):
    """Предупреждения позиции с ключом и отметкой «Всё верно»."""
    notices = []
    for text in item.get('warnings') or []:
        key = notice_key(text)
        notices.append({'key': key, 'text': text, 'acked': key in acks})
    return notices


def excluded_key(bar_id, entry):
    """Не попавший в файл сорт отмечается по бару: сорт, кран и причина. Сменилась
    причина или кран — нужна новая отметка."""
    return notice_key(f"excluded|{bar_id}|{entry.get('name')}|{entry.get('taps')}|{entry.get('reason')}")


def attention_count(bar_id, beer, excluded, acks):
    """Что ещё не просмотрено: предупреждения позиций и сорта не в файле."""
    notices = sum(1 for item in beer for text in item.get('warnings') or []
                  if notice_key(text) not in acks)
    return notices + sum(1 for entry in excluded if excluded_key(bar_id, entry) not in acks)


def feed_detail_data(bar_id):
    """Всё для страницы бара: позиции с правками, не попавшее в фид, правки без позиций."""
    ensure_overrides_schema()
    feed = feed_by_id(bar_id)
    beer, excluded, info = bar_state(bar_id)
    document = load_document()
    stored, acks = document['feeds'], document['acks']
    effective = overrides_for_bar(stored, bar_id)
    items = combine_offers(offers_for_bar(bar_id), beer)
    offers = []
    for item in items:
        override = effective.get(item['id'])
        merged = merge_offer(item, override)
        merged['override'] = override
        merged['bar_only'] = bool(item['kind'] == 'kitchen' and override
                                  and bar_scoped(stored, bar_id, item['id']))
        merged['notices'] = notices_for(item, acks)
        offers.append(merged)
    excluded = [{**entry, 'key': excluded_key(bar_id, entry),
                 'acked': excluded_key(bar_id, entry) in acks} for entry in excluded]
    present = {item['id'] for item in items}
    kitchen_stored = stored.get(KITCHEN_SCOPE) or {}
    orphans = [{'id': offer_id, 'override': override, 'kitchen': offer_id in kitchen_stored}
               for offer_id, override in sorted(effective.items()) if offer_id not in present]
    return {
        'feed': {**feed, 'public_url': _public_url(feed['public_path'])},
        'snapshot': info,
        'offers': offers,
        'excluded': excluded,
        'orphans': orphans,
        'counts': {
            'shown': sum(not item['hidden'] for item in offers),
            'hidden': sum(item['hidden'] for item in offers),
            'beer': sum(item['kind'] == 'beer' for item in offers),
            'kitchen': sum(item['kind'] == 'kitchen' for item in offers),
            'edited': sum(item['edited'] for item in offers),
            'excluded': len(excluded),
            'excluded_open': sum(not entry['acked'] for entry in excluded),
            'notices_open': sum(not notice['acked'] for item in offers for notice in item['notices']),
        },
    }


@yml_bp.route('/yandex')
def yandex_page():
    return render_template('yml_feeds.html')


@yml_bp.route('/api/yml/feeds', methods=['GET'])
def list_feeds():
    """Бары и краткое состояние снимка — для переключателя баров."""
    data = scheduler.load_snapshot()
    bars = data['bars'] if scheduler.snapshot_ok(data) else {}
    try:
        acks = load_document()['acks']
    except OverridesCorrupted:
        acks = {}
    feeds = []
    for feed in feed_catalog():
        bar = bars.get(feed['bar_id']) if isinstance(bars.get(feed['bar_id']), dict) else None
        feeds.append({
            **feed,
            'public_url': _public_url(feed['public_path']),
            'beer': len(bar.get('beer') or []) if bar else None,
            'excluded': len(bar.get('excluded') or []) if bar else None,
            'attention': attention_count(feed['bar_id'], bar.get('beer') or [],
                                         bar.get('excluded') or [], acks) if bar else None,
            'error': bar.get('error') if bar else None,
        })
    return jsonify({'feeds': feeds, 'snapshot': scheduler.snapshot_status(data or {})})


@yml_bp.route('/api/yml/feeds/<feed_id>', methods=['GET'])
def feed_detail(feed_id):
    if feed_by_id(feed_id) is None:
        return jsonify({'error': 'Бар не найден'}), 404
    try:
        return jsonify(feed_detail_data(feed_id))
    except OverridesCorrupted as error:
        return jsonify({'error': str(error)}), 503
    except Exception as error:
        print(f'[ERROR] YML feed {feed_id}: {type(error).__name__}: {error}')
        return jsonify({'error': 'Не удалось прочитать фид'}), 503


@yml_bp.route('/api/yml/feeds/<feed_id>', methods=['PUT'])
def save_feed(feed_id):
    """Сохранить изменённые позиции: {changes: {id: {hidden, name, price, description, base}}}."""
    if feed_by_id(feed_id) is None:
        return jsonify({'error': 'Бар не найден'}), 404
    payload = request.get_json(silent=True) or {}
    changes = payload.get('changes')
    if not isinstance(changes, dict) or not changes:
        return jsonify({'error': 'Нет изменений для сохранения'}), 400
    try:
        ensure_overrides_schema()
        apply_changes(feed_id, changes, kitchen_ids())
    except OverrideConflict as conflict:
        return jsonify({
            'error': 'Пока страница была открыта, эти позиции сохранил кто-то ещё. '
                     'Их значения обновлены, проверьте и повторите.',
            'conflicts': conflict.ids,
            **feed_detail_data(feed_id),
        }), 409
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except OverridesCorrupted as error:
        return jsonify({'error': str(error)}), 503
    except Exception as error:
        print(f'[ERROR] YML save {feed_id}: {type(error).__name__}: {error}')
        return jsonify({'error': 'Не удалось сохранить правки'}), 500
    return jsonify(feed_detail_data(feed_id))


@yml_bp.route('/api/yml/feeds/<feed_id>/ack', methods=['POST'])
def acknowledge(feed_id):
    """«Всё верно»: скрыть предупреждения или сорта не в файле. {keys: [...], acked: true|false}.

    Отметка хранится по тексту предупреждения: изменится ситуация — вернётся."""
    if feed_by_id(feed_id) is None:
        return jsonify({'error': 'Бар не найден'}), 404
    payload = request.get_json(silent=True) or {}
    keys = payload.get('keys')
    if not isinstance(keys, list):
        return jsonify({'error': 'Нет списка предупреждений'}), 400
    try:
        when = datetime.now(scheduler.MOSCOW).replace(microsecond=0).isoformat()
        set_acks(keys, payload.get('acked') is not False, when)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except OverridesCorrupted as error:
        return jsonify({'error': str(error)}), 503
    return jsonify(feed_detail_data(feed_id))


@yml_bp.route('/api/yml/refresh', methods=['POST'])
def refresh_now():
    """Переснять пиво по всем барам сейчас (кнопка «Переснять»)."""
    if not request.is_json:
        return jsonify({'error': 'Нужен JSON'}), 415
    try:
        data = scheduler.refresh_snapshot(wait=0)
    except scheduler.RefreshBusy:
        return jsonify({'error': 'Снимок уже снимается, подождите минуту'}), 409
    except Exception as error:
        print(f'[ERROR] YML refresh: {type(error).__name__}: {error}')
        return jsonify({'error': 'Прайс iiko сейчас недоступен, снимок не снят. '
                                 'В файлах остаётся прошлый снимок.'}), 503
    return jsonify({
        'snapshot': scheduler.snapshot_status(data),
        'bars': {bar_id: {'beer': len(state['beer']), 'excluded': len(state['excluded']),
                          'error': state['error']}
                 for bar_id, state in data['bars'].items()},
    })


@yml_bp.route('/feeds/kitchen/<bar_id>', methods=['GET'])
def kitchen_yml(bar_id):
    """Один файл на бар: кухня и пиво 0,5 л. В Картах на это место только одна ссылка."""
    if bar_id not in FEED_ORDER:
        return jsonify({'error': 'Бар не найден'}), 404
    try:
        xml = render_bar_feed(bar_id)
    except Exception as error:
        print(f'[ERROR] YML bar {bar_id}: {type(error).__name__}: {error}')
        return jsonify({'error': 'Не удалось собрать фид'}), 503
    response = make_response(xml)
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    response.headers['Cache-Control'] = 'public, max-age=300'
    return response
