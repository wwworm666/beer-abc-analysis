"""Страница управления YML-фидами Яндекс Карт и публичный фид кухни."""
from flask import Blueprint, jsonify, make_response, render_template, request

from core.kitchen_menu import render_for_bar
from core.kitchen_yml import offers_for_bar
from core.taplist import BAR_NAMES
from core.taplist_yml import offers_for
from core.yml_feeds import feed_by_id, feed_catalog
from core.yml_overrides import load_overrides, merge_offers, save_overrides

yml_bp = Blueprint('yml_feeds', __name__)


def _public_url(path):
    base = (request.url_root or '').rstrip('/')
    return base + path


@yml_bp.route('/yandex')
def yandex_page():
    return render_template('yml_feeds.html')


@yml_bp.route('/api/yml/feeds', methods=['GET'])
def list_feeds():
    feeds = []
    for feed in feed_catalog():
        item = dict(feed)
        item['public_url'] = _public_url(feed['public_path'])
        feeds.append(item)
    return jsonify({'feeds': feeds})


def _taplist_items(bar_id):
    from routes.taps import PriceUnavailable, load_reviewed_taplist
    try:
        rows = load_reviewed_taplist(bar_id, True)
    except PriceUnavailable:
        raise
    return offers_for(rows)


@yml_bp.route('/api/yml/feeds/<feed_id>', methods=['GET'])
def feed_detail(feed_id):
    feed = feed_by_id(feed_id)
    if feed is None:
        return jsonify({'error': 'Фид не найден'}), 404
    try:
        if feed['kind'] == 'taplist':
            source = _taplist_items(feed['bar_id'])
            note = ''
        else:
            source = offers_for_bar(feed['bar_id'])
            note = 'Меню кухни общее, а правки — у этой точки. Ссылка ниже ведёт в её карточку на Картах.'
    except Exception as error:
        from routes.taps import PriceUnavailable
        if isinstance(error, PriceUnavailable):
            return jsonify({'error': 'Не удалось получить актуальный прайс iiko'}), 503
        print(f'[ERROR] YML feed {feed_id}: {error}')
        return jsonify({'error': 'Не удалось прочитать фид'}), 503
    items = merge_offers(source, (load_overrides().get(feed_id) or {}))
    return jsonify({
        'feed': {**feed, 'public_url': _public_url(feed['public_path'])},
        'note': note,
        'offers': items,
        'shown': sum(not item.get('hidden') for item in items),
        'hidden': sum(bool(item.get('hidden')) for item in items),
    })


@yml_bp.route('/api/yml/feeds/<feed_id>', methods=['PUT'])
def save_feed(feed_id):
    if feed_by_id(feed_id) is None:
        return jsonify({'error': 'Фид не найден'}), 404
    payload = request.get_json(silent=True) or {}
    changes = payload.get('offers')
    if not isinstance(changes, dict):
        return jsonify({'error': 'Нет списка правок'}), 400
    try:
        save_overrides(feed_id, changes)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except Exception as error:
        print(f'[ERROR] YML save {feed_id}: {error}')
        return jsonify({'error': 'Не удалось сохранить правки'}), 500
    return feed_detail(feed_id)


@yml_bp.route('/feeds/kitchen/<bar_id>', methods=['GET'])
def kitchen_yml(bar_id):
    """YML кухни одной точки. Состав меню общий, правки имени и цены — свои."""
    if bar_id not in BAR_NAMES:
        return jsonify({'error': 'Бар не найден'}), 404
    response = make_response(render_for_bar(
        request.url_root, bar_id, load_overrides().get(f'kitchen-{bar_id}') or {}))
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    response.headers['Cache-Control'] = 'public, max-age=300'
    return response
