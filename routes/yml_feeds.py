"""Страница управления YML-фидами Яндекс Карт и публичный фид кухни."""
from flask import Blueprint, jsonify, make_response, render_template, request

from core.kitchen_yml import offers_for_bar
from core.taplist import BAR_NAMES
from core.taplist_yml import SHOP_COMPANY, build_yml, offers_for
from core.yml_feeds import combine_offers, feed_by_id, feed_catalog, overrides_for_bar
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


def bar_items(bar_id):
    """Кухня и пиво 0,5 л одной точки. Без прайса iiko поднимает PriceUnavailable."""
    from routes.taps import load_reviewed_taplist
    kitchen = offers_for_bar(bar_id)
    drinks = offers_for(load_reviewed_taplist(bar_id, True))
    return combine_offers(kitchen, drinks)


def stored_bar(bar_id):
    """Снимок 05:00, если он уже есть. Иначе None — собирать краны прямо сейчас."""
    from core.yml_scheduler import load_snapshot
    snapshot = load_snapshot() or {}
    bar = (snapshot.get('bars') or {}).get(bar_id)
    if not isinstance(bar, dict) or not isinstance(bar.get('items'), list):
        return None
    return snapshot.get('updated_at'), bar


def render_bar_feed(bar_id):
    stored = stored_bar(bar_id)
    items = stored[1]['items'] if stored else bar_items(bar_id)
    items = merge_offers(items, overrides_for_bar(load_overrides(), bar_id))
    shop = f'{SHOP_COMPANY}, {BAR_NAMES[bar_id]}'
    return build_yml(items=items, shop_name=shop)


@yml_bp.route('/api/yml/feeds/<feed_id>', methods=['GET'])
def feed_detail(feed_id):
    feed = feed_by_id(feed_id)
    if feed is None:
        return jsonify({'error': 'Фид не найден'}), 404
    note = 'Одна ссылка на бар: кухня и пиво 0,5 л. Список фиксируется каждый день в 05:00 МСК.'
    stored = stored_bar(feed['bar_id'])
    if stored:
        updated_at, bar = stored
        source = bar['items']
        note = f'Снимок от {updated_at}. Следующее обновление в 05:00 МСК.'
        if bar.get('error'):
            note += ' ' + bar['error']
    else:
        try:
            source = bar_items(feed['bar_id'])
            note = 'Снимок ещё не снят, показаны краны на сейчас. Дальше список фиксируется каждый день в 05:00 МСК.'
        except Exception as error:
            from routes.taps import PriceUnavailable
            if isinstance(error, PriceUnavailable):
                source = combine_offers(offers_for_bar(feed['bar_id']), [])
                note = 'Прайс пива сейчас недоступен, в списке только кухня.'
            else:
                print(f'[ERROR] YML feed {feed_id}: {error}')
                return jsonify({'error': 'Не удалось прочитать фид'}), 503
    items = merge_offers(source, overrides_for_bar(load_overrides(), feed['bar_id']))
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
        for legacy in (f'kitchen-{feed_id}', f'taplist-{feed_id}'):
            save_overrides(legacy, {offer_id: {} for offer_id in changes})
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except Exception as error:
        print(f'[ERROR] YML save {feed_id}: {error}')
        return jsonify({'error': 'Не удалось сохранить правки'}), 500
    return feed_detail(feed_id)


@yml_bp.route('/feeds/kitchen/<bar_id>', methods=['GET'])
def kitchen_yml(bar_id):
    """Один файл на бар: кухня и пиво 0,5 л. В Картах на это место только одна ссылка."""
    if bar_id not in BAR_NAMES:
        return jsonify({'error': 'Бар не найден'}), 404
    try:
        xml = render_bar_feed(bar_id)
    except Exception as error:
        from routes.taps import PriceUnavailable
        if not isinstance(error, PriceUnavailable):
            print(f'[ERROR] YML bar {bar_id}: {error}')
        return jsonify({'error': 'Не удалось собрать фид'}), 503
    response = make_response(xml)
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    response.headers['Cache-Control'] = 'public, max-age=300'
    return response
