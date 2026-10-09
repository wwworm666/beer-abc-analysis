from flask import Blueprint, request, jsonify, make_response
import time
import json
import os
import csv
from functools import wraps
from io import StringIO
from urllib.parse import quote
from extensions import taps_manager
from core import taplist_post, untappd_live
from core.auth_guard import current_user
from core.untappd_registry import load_registry
from core.taplist import product_catalog, tap_details, full_taplist, BAR_NAMES
from core.taplist_pricing import enrich_prices
from core.kitchen_menu import render_kitchen_menu
from core.taplist_yml import SHOP_URL, build_yml
from core.yml_overrides import load_overrides, merge_offers

taps_bp = Blueprint('taps', __name__)


@taps_bp.after_app_request
def add_taps_no_cache(response):
    """Запрет кэширования для API кранов — Safari на iOS агрессивно кэширует GET-ответы,
    из-за чего сотрудники видят устаревшие данные кранов"""
    if request.path.startswith(('/api/taps', '/api/untappd')) or request.path == '/api/beers/draft':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@taps_bp.route('/api/taps/bars', methods=['GET'])
def get_bars_list():
    """Получить список всех баров"""
    try:
        bars = taps_manager.get_bars()
        return jsonify(bars)
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/bars: {e}")
        return jsonify({'error': str(e)}), 500

@taps_bp.route('/api/taps/<bar_id>', methods=['GET'])
def get_bar_taps(bar_id):
    """Получить состояние кранов конкретного бара"""
    try:
        registry = load_registry()
        result = taps_manager.get_bar_taps(bar_id, product_catalog(registry))
        if 'taps' in result:
            for tap in result['taps']:
                tap['beer_info'] = tap_details(tap, registry) if tap.get('current_beer') else None
        if 'error' in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}: {e}")
        return jsonify({'error': str(e)}), 500

def _expected(data):
    """Состояние крана, которое видел бармен (страница /taps/<bar>). Нет — без проверки:
    бот и MCP-инструменты вызывают эти эндпоинты без него."""
    expected = data.get('expected')
    if expected is None:
        return None
    if not isinstance(expected, dict):
        raise ValueError('Обновите страницу и повторите')
    return expected


def _action_response(result):
    if result['success']:
        return jsonify(result)
    return jsonify(result), 409 if result.get('conflict') else 400


@taps_bp.route('/api/taps/<bar_id>/start', methods=['POST'])
def start_tap(bar_id):
    """Подключить кегу (начать работу крана)"""
    try:
        data = request.get_json(silent=True) or {}
        tap_number = data.get('tap_number')
        beer_name = data.get('beer_name')
        keg_id = data.get('keg_id')

        # Проверяем только обязательные поля (keg_id может быть пустым, тогда создастся AUTO)
        if not tap_number or not beer_name:
            return jsonify({'error': 'Требуются: tap_number, beer_name'}), 400

        # Если keg_id пустой, генерируем автоматический
        if not keg_id:
            keg_id = f'AUTO-{int(time.time() * 1000)}'

        try:
            product_id = selected_product(data)
            expected = _expected(data)
        except ValueError as error:
            return jsonify({'success': False, 'error': str(error)}), 400
        return _action_response(taps_manager.start_tap(
            bar_id, int(tap_number), beer_name, keg_id, iiko_product_id=product_id, expected=expected))
    except Exception as e:
        print(f"[ERROR] /api/taps/{bar_id}/start: {type(e).__name__}: {e}")
        return jsonify({'error': 'Не удалось подключить кегу'}), 500

@taps_bp.route('/api/taps/<bar_id>/stop', methods=['POST'])
def stop_tap(bar_id):
    """Остановить кран (кега закончилась)"""
    try:
        data = request.get_json(silent=True) or {}
        tap_number = data.get('tap_number')

        if not tap_number:
            return jsonify({'error': 'Требуется: tap_number'}), 400
        try:
            expected = _expected(data)
        except ValueError as error:
            return jsonify({'success': False, 'error': str(error)}), 400
        return _action_response(taps_manager.stop_tap(bar_id, int(tap_number), expected=expected))
    except Exception as e:
        print(f"[ERROR] /api/taps/{bar_id}/stop: {type(e).__name__}: {e}")
        return jsonify({'error': 'Не удалось остановить кран'}), 500

@taps_bp.route('/api/taps/<bar_id>/replace', methods=['POST'])
def replace_tap(bar_id):
    """Заменить кегу (смена сорта пива)"""
    try:
        data = request.get_json(silent=True) or {}
        tap_number = data.get('tap_number')
        beer_name = data.get('beer_name')
        keg_id = data.get('keg_id')

        # Проверяем только обязательные поля (keg_id может быть пустым, тогда создастся AUTO)
        if not tap_number or not beer_name:
            return jsonify({'error': 'Требуются: tap_number, beer_name'}), 400

        # Если keg_id пустой, генерируем автоматический
        if not keg_id:
            keg_id = f'AUTO-{int(time.time() * 1000)}'

        try:
            product_id = selected_product(data)
            expected = _expected(data)
        except ValueError as error:
            return jsonify({'success': False, 'error': str(error)}), 400
        return _action_response(taps_manager.replace_tap(
            bar_id, int(tap_number), beer_name, keg_id, iiko_product_id=product_id, expected=expected))
    except Exception as e:
        print(f"[ERROR] /api/taps/{bar_id}/replace: {type(e).__name__}: {e}")
        return jsonify({'error': 'Не удалось заменить кегу'}), 500

@taps_bp.route('/api/taps/<bar_id>/<int:tap_number>/history', methods=['GET'])
def get_tap_history(bar_id, tap_number):
    """Получить историю действий крана"""
    try:
        limit = request.args.get('limit', 50, type=int)
        result = taps_manager.get_tap_history(bar_id, tap_number, limit)

        if 'error' in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}/{tap_number}/history: {e}")
        return jsonify({'error': str(e)}), 500

@taps_bp.route('/api/taps/events/all', methods=['GET'])
def get_all_events():
    """Получить все события"""
    try:
        bar_id = request.args.get('bar_id', None)
        limit = request.args.get('limit', 100, type=int)

        events = taps_manager.get_all_events(bar_id, limit)
        return jsonify({'events': events})
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/events/all: {e}")
        return jsonify({'error': str(e)}), 500

@taps_bp.route('/api/taps/statistics', methods=['GET'])
def get_statistics():
    """Получить статистику по кранам"""
    try:
        bar_id = request.args.get('bar_id', None)
        result = taps_manager.get_statistics(bar_id)

        if 'error' in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/statistics: {e}")
        return jsonify({'error': str(e)}), 500


def selected_product(data, required=False):
    product_id = data.get('iiko_product_id')
    if not product_id:
        if required:
            raise ValueError('Выберите сорт из списка')
        return None
    catalog = product_catalog(load_registry())
    if not isinstance(product_id, str) or product_id not in catalog:
        raise ValueError('Товар не найден. Обновите список кег и выберите сорт снова.')
    if data.get('beer_name') and data['beer_name'].strip() not in catalog[product_id]['names']:
        raise ValueError('Название изменилось после выбора. Выберите сорт из списка снова.')
    return product_id


@taps_bp.route('/api/taps/<bar_id>/identify', methods=['POST'])
def identify_tap(bar_id):
    try:
        data = request.get_json() or {}
        product_id = selected_product(data, required=True)
        expected = data.get('expected')
        if not isinstance(expected, dict) or not all(k in expected for k in
                ('current_beer', 'current_keg_id', 'started_at', 'iiko_product_id')):
            raise ValueError('Обновите страницу перед уточнением сорта')
        result = taps_manager.identify_tap(bar_id, int(data['tap_number']), product_id, expected)
        return jsonify(result), 200 if result['success'] else 409
    except (ValueError, TypeError, KeyError) as error:
        return jsonify({'success': False, 'error': str(error)}), 400
    except Exception:
        return jsonify({'success': False, 'error': 'Не удалось сохранить сорт'}), 500


def load_reviewed_taplist(bar_id=None, active_only=True, sources=None):
    """sources — уже снятый прайс iiko. Без него запрос уходит в iiko один раз."""
    registry = load_registry()
    snapshot = taps_manager.get_snapshot(product_catalog(registry))
    rows = full_taplist(snapshot, registry, bar_id, active_only)
    if rows:
        if sources is None:
            try:
                sources = fetch_price_sources()
            except Exception:
                raise PriceUnavailable from None
        enrich_prices(rows, registry, sources)
    return rows


def reviewed_taplist():
    return load_reviewed_taplist(
        request.args.get('bar_id'),
        request.args.get('active_only', 'true').lower() == 'true')


class PriceUnavailable(Exception):
    pass


def fetch_price_sources():
    from core.taplist_iiko import fetch_price_sources as fetch
    return fetch()


# Порция, цену которой компактный таплист выносит отдельным полем: 0,5 л — основная
# порция разливного в меню и в фидах Яндекса. Строка — как portion_liters у servings
# (core/taplist_pricing.number: Decimal без хвостовых нулей).
COMPACT_MAIN_PORTION = '0.5'


def compact_tap_row(row):
    """Кран таплиста V2 в компактном виде для ИИ-агентов (?compact=1).

    Полная строка — это ещё описание, фото, ссылки Untappd и подробности каждой порции
    (id блюда, техкарта, источник цены): по бару 58–85 тыс. знаков, а мост MCP режет
    ответ на 60 тыс. Здесь только то, что нужно для поста и заказа:
      bar, bar_id, tap_number, beer_name, brewery, style, abv (%), ibu,
      mapped / mapping_status (связь с Untappd проверена или почему нет),
      price_status (verified / partial / unavailable — как в полном ответе),
      prices — все продаваемые порции [{l: литры, rub: цена}] в порядке полного ответа,
      price_0_5 — цена порции 0,5 л строкой «350.00», если у 0,5 л ровно одна цена;
                  None — порции 0,5 л нет или у неё несколько разных цен (тогда
                  варианты видны в prices: выбирать за владельца не будем).
    Числа и строки те же, что в полном ответе, ничего не пересчитывается.
    """
    servings = row.get('servings') or []
    main = {s.get('price_rub') for s in servings if s.get('portion_liters') == COMPACT_MAIN_PORTION}
    return {
        'bar': row.get('bar'), 'bar_id': row.get('bar_id'), 'tap_number': row.get('tap_number'),
        'beer_name': row.get('beer_name'), 'brewery': row.get('brewery'), 'style': row.get('style'),
        'abv': row.get('abv'), 'ibu': row.get('ibu'),
        'mapped': row.get('mapped'), 'mapping_status': row.get('mapping_status'),
        'price_status': row.get('price_status'),
        'price_0_5': next(iter(main)) if len(main) == 1 else None,
        'prices': [{'l': s.get('portion_liters'), 'rub': s.get('price_rub')} for s in servings],
    }


@taps_bp.route('/api/taps/taplist-full', methods=['GET'])
def get_taplist_full():
    """Проверенный таплист V2. ?compact=1 — краткий вид кранов для агентов (compact_tap_row);
    без него (или compact=0) — полный ответ, как на странице. Другое значение — 400."""
    compact = request.args.get('compact', '0')
    if compact not in ('0', '1'):
        return jsonify({'success': False, 'error': 'compact — 1 (кратко) или 0 (полностью)'}), 400
    try:
        rows = reviewed_taplist()
        payload = {'success': True, 'count': len(rows),
                   'mapped_count': sum(row['mapped'] for row in rows), 'taplist': rows}
        if compact == '1':
            payload['compact'] = True
            payload['taplist'] = [compact_tap_row(row) for row in rows]
        return jsonify(payload)
    except PriceUnavailable:
        return jsonify({'success': False, 'error': 'Не удалось получить актуальный прайс iiko. Повторите выгрузку.'}), 503
    except KeyError:
        return jsonify({'success': False, 'error': 'Бар не найден'}), 404
    except Exception as error:
        print(f'[ERROR] Taplist V2: {error}')
        return jsonify({'success': False, 'error': 'Не удалось загрузить проверенный таплист'}), 503


@taps_bp.route('/api/taps/export-taplist-full', methods=['GET'])
def export_taplist_full():
    try:
        rows = reviewed_taplist()
        output = StringIO()
        writer = csv.writer(output, delimiter=',', quoting=csv.QUOTE_ALL)
        writer.writerow(['Название', 'Цена, руб.', 'Порция, л', 'Бренд / производитель',
                         'Фото (ссылка)', 'Описание', 'Бар', 'Кран', 'Позиция iiko',
                         'Untappd URL', 'Стиль', 'ABV', 'IBU', 'Статус связи',
                         'Статус цены', 'Цены проверены', 'Статус фото и описания'])
        for row in rows:
            media_status = []
            if not row.get('photo_url'):
                media_status.append('Фото отсутствует в источнике')
            elif row.get('photo_kind') == 'community_photo':
                media_status.append('Фото посетителя из карточки Untappd')
            if not row.get('description'):
                media_status.append('Описание отсутствует в источнике')
            elif row.get('description_source') == 'verified_characteristics':
                media_status.append('Описание по подтверждённым характеристикам')
            elif row.get('description_is_excerpt'):
                media_status.append('Краткая выдержка; полное описание по ссылке Untappd')
            for serving in row.get('servings') or [{}]:
                values = [row.get('beer_name'), serving.get('price_rub'), serving.get('portion_liters'),
                          row.get('brewery'), row.get('photo_url'), row.get('description'),
                          row['bar'], row['tap_number'],
                          (serving['dish_name'] + (' / ' + serving['size_name'] if serving.get('size_name') else ''))
                          if serving else row.get('iiko_name'),
                          row.get('untappd_url'), row.get('style'), row.get('abv'), row.get('ibu'),
                          row['mapping_message'], row.get('price_message'), row.get('prices_checked_at'),
                          '; '.join(media_status) or 'Фото и описание из Untappd']
                # Spreadsheet applications must not execute imported product names.
                writer.writerow(["'" + v if isinstance(v, str) and v.lstrip()[:1] in
                                 ('=', '+', '-', '@') else v for v in values])
        bar_id = request.args.get('bar_id')
        filename = f'taplist_full_{bar_id}.csv' if bar_id else 'taplist_full.csv'
        response = make_response('\ufeff' + output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f"attachment; filename={filename}; filename*=UTF-8''{quote(filename)}"
        response.headers['X-Taplist-Unmapped-Count'] = str(sum(not r['mapped'] for r in rows))
        response.headers['X-Taplist-Unpriced-Count'] = str(sum(not r.get('servings') for r in rows))
        return response
    except PriceUnavailable:
        return jsonify({'success': False, 'error': 'Не удалось получить актуальный прайс iiko. Повторите выгрузку.'}), 503
    except KeyError:
        return jsonify({'success': False, 'error': 'Бар не найден'}), 404
    except Exception as error:
        print(f'[ERROR] Taplist V2 export: {error}')
        return jsonify({'success': False, 'error': 'Не удалось загрузить проверенный таплист'}), 503


@taps_bp.route('/feeds/taplist.yml', methods=['GET'])
def taplist_yml():
    """Публичный YML. bar=bar1…bar4 — тот же файл, что /feeds/kitchen/<bar>
    (кухня и пиво). Без bar — пиво всех баров из снимка, разделы = бары;
    в iiko на каждый анонимный запрос не ходит."""
    bar_id = request.args.get('bar') or request.args.get('bar_id') or None
    if bar_id is not None and bar_id not in BAR_NAMES:
        return jsonify({'error': 'Бар не найден'}), 404
    try:
        if bar_id:
            from routes.yml_feeds import render_bar_feed
            body = render_bar_feed(bar_id)
        else:
            from core.yml_feeds import FEED_ORDER, overrides_for_bar
            from routes.yml_feeds import bar_state, ensure_overrides_schema
            ensure_overrides_schema()
            stored = load_overrides()
            items = []
            for bar in FEED_ORDER:
                beer, _, _ = bar_state(bar)
                items.extend(merge_offers(beer, overrides_for_bar(stored, bar)))
            body = build_yml(items=items)
    except PriceUnavailable:
        return jsonify({'error': 'Не удалось получить актуальный прайс iiko'}), 503
    except KeyError:
        return jsonify({'error': 'Бар не найден'}), 404
    except Exception as error:
        print(f'[ERROR] Taplist YML: {error}')
        return jsonify({'error': 'Не удалось собрать фид'}), 503
    response = make_response(body)
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    response.headers['Cache-Control'] = 'public, max-age=300'
    return response


@taps_bp.route('/feeds/kitchen.yml', methods=['GET'])
def kitchen_yml():
    """Старый публичный YML кухни (исходный файл меню). Общие правки кухни со
    страницы /yandex применяются: скрытое блюдо не попадает и сюда. Фото отдаёт сам сайт."""
    from core.kitchen_menu import apply_overrides
    from core.yml_feeds import KITCHEN_SCOPE
    from routes.yml_feeds import ensure_overrides_schema
    try:
        ensure_overrides_schema()
        common = load_overrides().get(KITCHEN_SCOPE) or {}
    except Exception as error:
        print(f'[ERROR] Kitchen YML overrides: {type(error).__name__}: {error}')
        return jsonify({'error': 'Не удалось собрать фид'}), 503
    response = make_response(apply_overrides(render_kitchen_menu(SHOP_URL + '/'), common))
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    response.headers['Cache-Control'] = 'public, max-age=300'
    return response


@taps_bp.route('/api/taps/<bar_id>/stats', methods=['GET'])
def get_bar_stats(bar_id):
    """Краткая статистика для карточки бара на /taps.

    active / empty — краны сейчас; unverified — активные краны без проверенной
    карточки сорта (в фид Яндекса не попадают); activity_7d — доля кран-дней
    с подключённой кегой за 7 дней, включая сегодня (формула — TapsManager.tap_activity_by_tap).
    Ошибка — 503, а не выдуманные нули.
    """
    try:
        registry = load_registry()
        result = taps_manager.get_bar_taps(bar_id, product_catalog(registry))
        if 'error' in result:
            return jsonify({'error': result['error']}), 404

        taps = result.get('taps', [])
        active = [t for t in taps if t.get('status') == 'active']
        total = result.get('total_taps', len(taps))
        unverified = sum(1 for tap in active if tap.get('current_beer')
                         and tap_details(tap, registry)['mapping_status'] != 'verified')

        from datetime import datetime, timedelta
        today = datetime.now()
        date_from = (today - timedelta(days=6)).strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')
        activity_7d = taps_manager.calculate_tap_activity_for_period(bar_id, date_from, date_to)

        return jsonify({
            'active': len(active),
            'empty': total - len(active),
            'total': total,
            'unverified': unverified,
            'activity_7d': round(activity_7d, 1),
        })
    except Exception as e:
        print(f"[ERROR] /api/taps/{bar_id}/stats: {type(e).__name__}: {e}")
        return jsonify({'error': 'Не удалось посчитать краны'}), 503

# Поиск в списке кег для агентов (?q=, ?limit=). Предел limit — 1000: кег в справочнике
# сотни, больше за раз агенту не нужно (весь список — без limit).
LIST_LIMIT_MAX = 1000
BEER_SEARCH_FIELDS = ('name', 'beer_name', 'brewery', 'style', 'num', 'id')


def _search_key(value):
    """Строка для поиска без учёта регистра; «ё» = «е» (так пишут и так ищут)."""
    return str(value or '').casefold().replace('ё', 'е')


def search_args():
    """?q= и ?limit= списка -> (подстрока поиска или None, число или None).

    q — подстрока без учёта регистра и «ё»; пустая — поиска нет. limit — целое
    1..LIST_LIMIT_MAX, иначе ValueError с текстом для ответа 400 (молча подменять
    кривой предел нельзя: агент решил бы, что позиций меньше, чем есть).
    """
    query = _search_key((request.args.get('q') or '').strip())
    raw = (request.args.get('limit') or '').strip()
    limit = None
    if raw:
        try:
            limit = int(raw)
        except ValueError:
            limit = 0
        if not 1 <= limit <= LIST_LIMIT_MAX:
            raise ValueError(f'limit — целое число от 1 до {LIST_LIMIT_MAX}')
    return query or None, limit


@taps_bp.route('/api/beers/draft', methods=['GET'])
def get_draft_beers():
    """Кеги для выбора на странице кранов. У проверенных — название сорта и
    пивоварня из карточки Untappd, чтобы искать можно было и по «Festhaus»,
    и по «ФестХаус».

    Для агентов: ?q= — подстрока в name, beer_name, brewery, style, num или id (без
    учёта регистра и «ё»), ?limit= — не больше N записей (1..1000) после поиска, в
    алфавитном порядке. С любым из них ответ — {beers, total (всего кег), matched
    (подошло до limit), q, limit}; без них — прежний {beers} (страница /taps).
    """
    try:
        query, limit = search_args()
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    try:
        registry = load_registry()
        catalog = product_catalog(registry)
        beers = []
        for row in catalog.values():
            details = tap_details({'iiko_product_id': row['id'], 'current_beer': row['name']}, registry)
            mapped = details['mapping_status'] == 'verified'
            beers.append({'id': row['id'], 'name': row['name'], 'num': row['num'], 'mapped': mapped,
                          'beer_name': details['beer_name'] if mapped else None,
                          'brewery': details['brewery'] if mapped else None,
                          'style': details['style'] if mapped else None})
        beers.sort(key=lambda row: (row['name'], row['id']))
        if query is None and limit is None:
            return jsonify({'beers': beers})
        matched = beers if query is None else [
            b for b in beers if query in _search_key(' '.join(str(b.get(f) or '') for f in BEER_SEARCH_FIELDS))]
        return jsonify({'beers': matched[:limit] if limit else matched, 'total': len(beers),
                        'matched': len(matched), 'q': query, 'limit': limit})
    except Exception as error:
        print(f'[ERROR] Draft catalog: {error}')
        return jsonify({'error': 'Не удалось загрузить список кег'}), 503

# ---------------------------------------------------------------------------
# Связи с Untappd без деплоя: ИИ-агент предлагает, администратор подтверждает
# (core/untappd_live, docs/untappd-links.md). Предложение — черновик; «Верно» сразу
# меняет таплист, «Таплист пятницы», гостевого бота, фиды Яндекса и граф знаний.
# ---------------------------------------------------------------------------

class UntappdAdminOnly(Exception):
    """Подтвердить, отклонить или отменить связь может только администратор (403)."""


def _untappd_admin(what):
    if not (current_user() or {}).get('is_admin'):
        raise UntappdAdminOnly(f'Только администратор может {what}')


def _untappd_guard(view):
    """Ошибки связей -> 400 / 403 / 404 / 409 / 503 (не 500 и не запись поверх битого файла)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except UntappdAdminOnly as error:
            return jsonify({'error': str(error), 'code': 'admin_required'}), 403
        except untappd_live.UntappdLinksUnavailable as error:
            return jsonify({'error': str(error), 'code': 'untappd_links_unavailable'}), 503
        except untappd_live.UntappdLinksError as error:
            status = {'not_found': 404, 'conflict': 409}.get(error.code, 400)
            return jsonify({'error': str(error), 'code': error.code}), status
        except ValueError as error:
            return jsonify({'error': str(error)}), 400
    return wrapper


def _proposal_rows(items, registry, snapshot=None):
    """Предложения для ответа: + status_name, preview (как сорт будет в таплисте) и
    on_tap (где кега стоит сейчас; без snapshot — пусто)."""
    names = taplist_post.load_names()
    on_tap = untappd_live.taps_by_product(snapshot, BAR_NAMES)[0] if snapshot is not None else {}
    return [dict(item, status_name=untappd_live.STATUS_NAMES[item['status']],
                 preview=untappd_live.preview(item, names, registry),
                 on_tap=on_tap.get(item['iiko_product_id'], [])) for item in items]


@taps_bp.route('/api/untappd/queue', methods=['GET'])
@_untappd_guard
def untappd_queue():
    """Кеги без проверенной связи с Untappd — работа для ИИ-агента и страницы
    /taps/untappd (core/untappd_live.queue).

    ?scope=urgent (по умолчанию) — стоят на кране сейчас (приоритет 1) и новые
    карточки iiko (2); all — и остальные нерешённые (3). ?q= — подстрока в имени кеги
    iiko, ?limit= — не больше N после поиска (1..1000). counts — по всей очереди,
    до q и limit; matched — сколько подошло под q."""
    query, limit = search_args()
    registry = load_registry()
    catalog = product_catalog(registry)
    snapshot = taps_manager.get_snapshot(catalog)
    result = untappd_live.queue(registry, catalog, snapshot, untappd_live.get_store().load(),
                                scope=request.args.get('scope') or 'urgent', bar_names=BAR_NAMES)
    items = result['items']
    if query is not None:
        items = [row for row in items if query in _search_key(row['iiko_name'])]
    result['matched'] = len(items)
    result['items'] = items[:limit] if limit else items
    return jsonify(result)


@taps_bp.route('/api/untappd/proposals', methods=['GET'])
@_untappd_guard
def untappd_proposals():
    """Предложения связей, новые первыми. ?status= proposed (по умолчанию: ждут
    решения), verified, rejected, superseded, revoked или all. ?q= — подстрока в
    имени кеги iiko, названии сорта или пивоварни; ?limit= — не больше N (1..1000).
    counts — число предложений по статусам; can_review — может ли текущий
    пользователь подтверждать (администратор)."""
    query, limit = search_args()
    status = request.args.get('status') or 'proposed'
    if status != 'all' and status not in untappd_live.STATUSES:
        raise ValueError('status: ' + ', '.join(untappd_live.STATUSES + ('all',)))
    store = untappd_live.get_store()
    everything = store.proposals()
    counts = {name: sum(1 for item in everything if item['status'] == name) for name in untappd_live.STATUSES}
    items = everything if status == 'all' else [item for item in everything if item['status'] == status]
    if query is not None:
        items = [item for item in items if query in _search_key(' '.join(
            str(value or '') for value in (item.get('iiko_name'), (item.get('card') or {}).get('beer_name'),
                                           (item.get('card') or {}).get('brewery'))))]
    matched = len(items)
    items = items[:limit] if limit else items
    registry = load_registry()
    snapshot = taps_manager.get_snapshot(product_catalog(registry))
    return jsonify({'status': status, 'items': _proposal_rows(items, registry, snapshot),
                    'matched': matched, 'counts': counts,
                    'can_review': bool((current_user() or {}).get('is_admin'))})


@taps_bp.route('/api/untappd/proposals', methods=['POST'])
@_untappd_guard
def untappd_propose():
    """Предложить связь кеги iiko (GUID из очереди) с карточкой пива Untappd. Черновик:
    до «Верно» администратора ни на что не влияет; прежнее предложение для той же
    кеги заменяется. Поля и проверки — core/untappd_live.UntappdLinksStore.propose. 201."""
    data = request.get_json(silent=True) or {}
    registry = load_registry()
    item = untappd_live.get_store().propose(data, current_user(), registry, product_catalog(registry))
    return jsonify(_proposal_rows([item], registry)[0]), 201


@taps_bp.route('/api/untappd/proposals/<proposal_id>/confirm', methods=['POST'])
@_untappd_guard
def untappd_confirm(proposal_id):
    """«Верно»: связь проверена и действует сразу. Только администратор. Тело
    (необязательно): style_ru и brewery_short — стиль по-русски и короткое имя
    пивоварни для поста, если их нет в словаре репозитория."""
    _untappd_admin('подтверждать связи с Untappd')
    data = request.get_json(silent=True) or {}
    names = {'style_ru': data.get('style_ru'), 'brewery_short': data.get('brewery_short')}
    item = untappd_live.get_store().confirm(proposal_id, current_user(), load_registry(), names)
    return jsonify(_proposal_rows([item], load_registry())[0])


@taps_bp.route('/api/untappd/proposals/<proposal_id>/reject', methods=['POST'])
@_untappd_guard
def untappd_reject(proposal_id):
    """«Не то»: предложение отклонено, кега остаётся в очереди; note — что не так
    (агент читает её в очереди и ищет снова). Только администратор."""
    _untappd_admin('отклонять предложения связей с Untappd')
    data = request.get_json(silent=True) or {}
    item = untappd_live.get_store().reject(proposal_id, current_user(), data.get('note'))
    return jsonify(_proposal_rows([item], load_registry())[0])


@taps_bp.route('/api/untappd/proposals/<proposal_id>/revoke', methods=['POST'])
@_untappd_guard
def untappd_revoke(proposal_id):
    """Отменить связь, подтверждённую на сайте: кега снова в очереди, ссылка из
    таплиста пропадает сразу. Связи встроенного реестра меняет только деплой.
    note — причина (необязательно). Только администратор."""
    _untappd_admin('отменять связи с Untappd')
    data = request.get_json(silent=True) or {}
    item = untappd_live.get_store().revoke(proposal_id, current_user(), data.get('note'))
    return jsonify(_proposal_rows([item], load_registry())[0])


@taps_bp.route('/api/update-nomenclature', methods=['POST'])
def update_nomenclature():
    """Обновить список продуктов из iiko"""
    api = None
    try:
        import requests
        import xml.etree.ElementTree as ET
        from core.iiko_api import IikoAPI

        print("[INFO] Начинаем обновление номенклатуры...")

        # Подключаемся к iiko
        api = IikoAPI()
        if not api.authenticate():
            print("[ERROR] Не удалось авторизоваться в iiko")
            return jsonify({'success': False, 'error': 'Authentication failed'}), 500

        # Получаем список продуктов
        url = f"{api.base_url}/products"
        params = {"key": api.token}

        response = requests.get(url, params=params, timeout=30)

        if response.status_code != 200:
            print(f"[ERROR] Ошибка получения продуктов: {response.status_code}")
            return jsonify({'success': False, 'error': f'API error: {response.status_code}'}), 500

        # Парсим XML
        root = ET.fromstring(response.content)
        products = []

        for product in root.findall('.//productDto'):
            product_id = product.find('id').text if product.find('id') is not None else None
            name = product.find('name').text if product.find('name') is not None else None
            parent_id = product.find('parentId').text if product.find('parentId') is not None else None
            num = product.find('num').text if product.find('num') is not None else None

            products.append({
                'id': product_id,
                'name': name,
                'parent_id': parent_id,
                'num': num
            })

        # Сохраняем в файл
        products_file = os.path.join('data', 'all_products.json')
        with open(products_file, 'w', encoding='utf-8') as f:
            json.dump(products, f, indent=2, ensure_ascii=False)

        print(f"[OK] Обновлено продуктов: {len(products)}")
        return jsonify({'success': True, 'count': len(products)})

    except Exception as e:
        print(f"[ERROR] Ошибка при обновлении номенклатуры: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        # Логаут в любом случае: даже если ET.fromstring/запись файла бросили исключение
        # (logout() — no-op без токена, безопасно при неудачной авторизации).
        if api is not None:
            api.logout()
