from flask import Blueprint, request, jsonify, make_response
import time
import json
import os
import csv
import re
from io import StringIO
from urllib.parse import quote
from difflib import SequenceMatcher
from extensions import taps_manager

taps_bp = Blueprint('taps', __name__)


@taps_bp.after_app_request
def add_taps_no_cache(response):
    """Запрет кэширования для API кранов — Safari на iOS агрессивно кэширует GET-ответы,
    из-за чего сотрудники видят устаревшие данные кранов"""
    if request.path.startswith('/api/taps'):
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
        result = taps_manager.get_bar_taps(bar_id)
        if 'error' in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}: {e}")
        return jsonify({'error': str(e)}), 500

@taps_bp.route('/api/taps/<bar_id>/start', methods=['POST'])
def start_tap(bar_id):
    """Подключить кегу (начать работу крана)"""
    try:
        data = request.json
        tap_number = data.get('tap_number')
        beer_name = data.get('beer_name')
        keg_id = data.get('keg_id')

        # Проверяем только обязательные поля (keg_id может быть пустым, тогда создастся AUTO)
        if not tap_number or not beer_name:
            return jsonify({'error': 'Требуются: tap_number, beer_name'}), 400

        # Если keg_id пустой, генерируем автоматический
        if not keg_id:
            keg_id = f'AUTO-{int(time.time() * 1000)}'

        result = taps_manager.start_tap(bar_id, int(tap_number), beer_name, keg_id)

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}/start: {e}")
        return jsonify({'error': str(e)}), 500

@taps_bp.route('/api/taps/<bar_id>/stop', methods=['POST'])
def stop_tap(bar_id):
    """Остановить кран (кега закончилась)"""
    try:
        data = request.json
        tap_number = data.get('tap_number')

        if not tap_number:
            return jsonify({'error': 'Требуется: tap_number'}), 400

        result = taps_manager.stop_tap(bar_id, int(tap_number))

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}/stop: {e}")
        return jsonify({'error': str(e)}), 500

@taps_bp.route('/api/taps/<bar_id>/replace', methods=['POST'])
def replace_tap(bar_id):
    """Заменить кегу (смена сорта пива)"""
    try:
        print(f"[DEBUG] /api/taps/{bar_id}/replace called")
        data = request.json
        print(f"[DEBUG] Request data: {data}")

        tap_number = data.get('tap_number')
        beer_name = data.get('beer_name')
        keg_id = data.get('keg_id')

        print(f"[DEBUG] tap_number={tap_number}, beer_name={beer_name}, keg_id={keg_id}")

        # Проверяем только обязательные поля (keg_id может быть пустым, тогда создастся AUTO)
        if not tap_number or not beer_name:
            print(f"[ERROR] Missing required fields")
            return jsonify({'error': 'Требуются: tap_number, beer_name'}), 400

        # Если keg_id пустой, генерируем автоматический
        if not keg_id:
            keg_id = f'AUTO-{int(time.time() * 1000)}'
            print(f"[DEBUG] Generated auto keg_id: {keg_id}")

        print(f"[DEBUG] Calling taps_manager.replace_tap...")
        result = taps_manager.replace_tap(bar_id, int(tap_number), beer_name, keg_id)
        print(f"[DEBUG] Result: {result}")

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}/replace: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

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

@taps_bp.route('/api/taps/export-taplist', methods=['GET'])
def export_taplist():
    """Экспортировать текущий таплист в CSV формате"""
    try:
        # Опциональный параметр bar_id для фильтрации по конкретному бару
        bar_id_filter = request.args.get('bar_id', None)

        # Получаем список всех баров
        bars = taps_manager.get_bars()

        # Фильтруем по конкретному бару, если указан
        if bar_id_filter:
            bars = [bar for bar in bars if bar['bar_id'] == bar_id_filter]

        # Создаём CSV в памяти
        output = StringIO()
        writer = csv.writer(output, delimiter=',', quoting=csv.QUOTE_MINIMAL)

        # Заголовок
        writer.writerow(['Бар', 'Номер крана', 'Название пива'])

        # Собираем данные по всем барам (или по одному, если bar_id_filter указан)
        for bar in bars:
            bar_id = bar['bar_id']
            bar_name = bar['name']

            # Получаем краны бара
            bar_data = taps_manager.get_bar_taps(bar_id)
            if 'error' in bar_data:
                continue

            # Добавляем все краны (активные и пустые)
            for tap in bar_data.get('taps', []):
                beer_name = tap['current_beer'] if tap['current_beer'] else '(пусто)'
                writer.writerow([
                    bar_name,
                    tap['tap_number'],
                    beer_name
                ])

        # Готовим ответ
        output.seek(0)
        csv_content = output.getvalue()
        output.close()

        # Формируем имя файла
        if bar_id_filter and bars:
            # Используем bar_id вместо имени для безопасности
            filename = f"taplist_{bar_id_filter}.csv"
        else:
            filename = "taplist.csv"

        # Создаём response с правильными заголовками
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        # Используем RFC 5987 для корректной работы с кириллицей
        response.headers['Content-Disposition'] = f"attachment; filename={filename}; filename*=UTF-8''{quote(filename)}"

        return response

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/export-taplist: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def load_beer_info_mapping():
    """Загружает маппинг информации о пиве из JSON файла"""
    mapping_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'beer_info_mapping.json')
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Ошибка загрузки beer_info_mapping.json: {e}")
    return {}


def find_beer_info(beer_name, mapping):
    """
    Ищет информацию о пиве в маппинге с fuzzy matching.
    Использует difflib для нечёткого сравнения строк.
    """
    if not beer_name or not mapping:
        return None

    def normalize(name):
        """Нормализует название для сравнения"""
        name = name.lower()
        # Убираем "кег "
        name = name.replace('кег ', '')
        # Заменяем тире на пробел
        name = name.replace(' — ', ' ').replace('—', ' ').replace('-', ' ')
        # Убираем запятые и точки
        name = name.replace(',', '').replace('.', '')
        # Убираем объёмы и единицы измерения
        name = re.sub(r'\d+\s*(л|l|кг|kg|ml|мл)', '', name)
        # Убираем типичные суффиксы
        for suffix in ['светлое', 'темное', 'тёмное', 'нефильтрованное', 'фильтрованное', 'пшеничное', 'полусухой', 'полусладкий']:
            name = name.replace(suffix, '')
        # Убираем лишние пробелы
        name = ' '.join(name.split())
        return name.strip()

    def similarity(a, b):
        """Возвращает степень схожести двух строк (0-1)"""
        return SequenceMatcher(None, a, b).ratio()

    # Прямое совпадение
    if beer_name in mapping:
        return mapping[beer_name]

    # Нормализуем искомое название
    normalized_search = normalize(beer_name)

    # Ищем лучшее совпадение
    best_match = None
    best_score = 0
    threshold = 0.75  # Минимальная схожесть 75%

    for key in mapping:
        normalized_key = normalize(key)

        # Точное совпадение после нормализации
        if normalized_search == normalized_key:
            return mapping[key]

        # Fuzzy matching
        score = similarity(normalized_search, normalized_key)
        if score > best_score:
            best_score = score
            best_match = key

    # Возвращаем лучшее совпадение если оно выше порога
    if best_match and best_score >= threshold:
        return mapping[best_match]

    return None


@taps_bp.route('/api/taps/taplist-full', methods=['GET'])
def get_taplist_full():
    """
    Получить полный таплист с расширенной информацией о пиве.
    Возвращает JSON с данными: пивоварня, название, untappd URL, стиль, ABV, IBU, описание.

    Параметры:
    - bar_id: фильтр по конкретному бару (опционально)
    - active_only: true - только активные краны (по умолчанию true)
    """
    try:
        bar_id_filter = request.args.get('bar_id', None)
        active_only = request.args.get('active_only', 'true').lower() == 'true'

        # Загружаем маппинг
        beer_mapping = load_beer_info_mapping()

        # Получаем список баров
        bars = taps_manager.get_bars()

        if bar_id_filter:
            bars = [bar for bar in bars if bar['bar_id'] == bar_id_filter]

        result = []

        for bar in bars:
            bar_id = bar['bar_id']
            bar_name = bar['name']

            bar_data = taps_manager.get_bar_taps(bar_id)
            if 'error' in bar_data:
                continue

            for tap in bar_data.get('taps', []):
                if active_only and tap['status'] != 'active':
                    continue

                beer_name = tap.get('current_beer')
                if not beer_name:
                    continue

                # Ищем расширенную информацию
                beer_info = find_beer_info(beer_name, beer_mapping)

                tap_data = {
                    'bar': bar_name,
                    'bar_id': bar_id,
                    'tap_number': tap['tap_number'],
                    'iiko_name': beer_name,
                    'started_at': tap.get('started_at'),
                }

                if beer_info:
                    tap_data.update({
                        'brewery': beer_info.get('brewery'),
                        'beer_name': beer_info.get('beer_name'),
                        'untappd_url': beer_info.get('untappd_url'),
                        'style': beer_info.get('style'),
                        'abv': beer_info.get('abv'),
                        'ibu': beer_info.get('ibu'),
                        'description': beer_info.get('description'),
                        'mapped': True
                    })
                else:
                    tap_data['mapped'] = False

                result.append(tap_data)

        return jsonify({
            'success': True,
            'count': len(result),
            'taplist': result
        })

    except Exception as e:
        print(f"[ERROR] Ошибка в /api/taps/taplist-full: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@taps_bp.route('/api/taps/export-taplist-full', methods=['GET'])
def export_taplist_full():
    """
    Экспортировать расширенный таплист в CSV формате.
    Включает: Бар, Кран, Пивоварня, Название пива, Untappd URL, Стиль, ABV, IBU, Описание
    """
    try:
        bar_id_filter = request.args.get('bar_id', None)
        active_only = request.args.get('active_only', 'true').lower() == 'true'

        # Загружаем маппинг
        beer_mapping = load_beer_info_mapping()

        bars = taps_manager.get_bars()

        if bar_id_filter:
            bars = [bar for bar in bars if bar['bar_id'] == bar_id_filter]

        output = StringIO()
        writer = csv.writer(output, delimiter=',', quoting=csv.QUOTE_ALL)

        # Заголовок
        writer.writerow(['Бар', 'Кран', 'Пивоварня', 'Название пива', 'Untappd URL', 'Стиль', 'ABV', 'IBU', 'Описание'])

        for bar in bars:
            bar_id = bar['bar_id']
            bar_name = bar['name']

            bar_data = taps_manager.get_bar_taps(bar_id)
            if 'error' in bar_data:
                continue

            for tap in bar_data.get('taps', []):
                if active_only and tap['status'] != 'active':
                    continue

                beer_name = tap.get('current_beer')
                if not beer_name:
                    continue

                beer_info = find_beer_info(beer_name, beer_mapping)

                if beer_info:
                    writer.writerow([
                        bar_name,
                        tap['tap_number'],
                        beer_info.get('brewery', ''),
                        beer_info.get('beer_name', ''),
                        beer_info.get('untappd_url', ''),
                        beer_info.get('style', ''),
                        beer_info.get('abv', ''),
                        beer_info.get('ibu', ''),
                        beer_info.get('description', '')
                    ])
                else:
                    # Если нет маппинга - используем название из iiko
                    writer.writerow([
                        bar_name,
                        tap['tap_number'],
                        '',
                        beer_name,
                        '',
                        '',
                        '',
                        '',
                        ''
                    ])

        output.seek(0)
        csv_content = output.getvalue()
        output.close()

        if bar_id_filter and bars:
            filename = f"taplist_full_{bar_id_filter}.csv"
        else:
            filename = "taplist_full.csv"

        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f"attachment; filename={filename}; filename*=UTF-8''{quote(filename)}"

        return response

    except Exception as e:
        print(f"[ERROR] Ошибка в /api/taps/export-taplist-full: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@taps_bp.route('/api/taps/<bar_id>/stats', methods=['GET'])
def get_bar_stats(bar_id):
    """Получить краткую статистику для карточки бара"""
    try:
        result = taps_manager.get_bar_taps(bar_id)
        if 'error' in result:
            return jsonify({'active': 0, 'empty': 12, 'activity_7d': 0}), 200

        taps = result.get('taps', [])
        active = len([t for t in taps if t.get('status') == 'active'])
        total = result.get('total_taps', 12)
        empty = total - len([t for t in taps if t.get('status') in ['active', 'replacing']])

        # Рассчитываем активность за последние 7 дней
        from datetime import datetime, timedelta
        today = datetime.now()
        week_ago = today - timedelta(days=7)
        date_from = week_ago.strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')

        activity_7d = taps_manager.calculate_tap_activity_for_period(bar_id, date_from, date_to)

        return jsonify({
            'active': active,
            'empty': empty,
            'total': total,
            'activity_7d': round(activity_7d, 1)  # Процент активности за последние 7 дней
        })
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/taps/{bar_id}/stats: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'active': 0, 'empty': 12, 'activity_7d': 0}), 200

@taps_bp.route('/api/beers/draft', methods=['GET'])
def get_draft_beers():
    """Получить список разливного пива из номенклатуры"""
    try:
        # Читаем файл с номенклатурой
        products_file = os.path.join('data', 'all_products.json')

        if not os.path.exists(products_file):
            # Если файла нет, возвращаем пустой список
            return jsonify({'beers': []})

        with open(products_file, 'r', encoding='utf-8') as f:
            products = json.load(f)

        # Фильтруем только разливное пиво
        # Разливное обычно содержит "кег", "KEG", "30L", "50L" в названии
        draft_beers = []
        seen_names = set()

        for product in products:
            name = product.get('name', '')
            # Ищем признаки разливного пива
            if any(keyword in name.upper() for keyword in ['КЕГ', 'KEG', '30L', '50L', 'DRAFT']):
                # Убираем дубликаты по названию
                clean_name = name.strip()
                if clean_name and clean_name not in seen_names:
                    draft_beers.append({
                        'id': product.get('id'),
                        'name': clean_name,
                        'num': product.get('num')
                    })
                    seen_names.add(clean_name)

        # Сортируем по названию
        draft_beers.sort(key=lambda x: x['name'])

        return jsonify({'beers': draft_beers})
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/beers/draft: {e}")
        return jsonify({'beers': []}), 200

@taps_bp.route('/api/update-nomenclature', methods=['POST'])
def update_nomenclature():
    """Обновить список продуктов из iiko"""
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
            api.logout()
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

        api.logout()

        print(f"[OK] Обновлено продуктов: {len(products)}")
        return jsonify({'success': True, 'count': len(products)})

    except Exception as e:
        print(f"[ERROR] Ошибка при обновлении номенклатуры: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
