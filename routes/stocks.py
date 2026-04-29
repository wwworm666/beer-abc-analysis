from flask import Blueprint, request, jsonify
import re
import os
import sys
import json
import math
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta
from core.olap_reports import OlapReports
from core.iiko_barcodes import get_barcode_map, invert_to_product_gtins
from extensions import taps_manager, get_cached_nomenclature, BARS

_BASE_DIR = Path(__file__).resolve().parent.parent
_CHZ_CACHE_FILE = _BASE_DIR / 'chz_test' / 'debug' / 'chz_stock.json'
_CHZ_REFRESH_LOG = _BASE_DIR / 'chz_test' / 'debug' / 'refresh.log'
_refresh_proc: subprocess.Popen | None = None
_refresh_log_file = None
_refresh_lock = threading.Lock()

# Маппинги бар→склад→КПП. Дублируются в 4 endpoint'ах ниже — рефактор отдельной задачей.
_BAR_ID_MAP = {
    'Большой пр. В.О': 'bar1',
    'Лиговский': 'bar2',
    'Кременчугская': 'bar3',
    'Варшавская': 'bar4',
    'Общая': None,
}
_STORE_ID_MAP = {
    'bar1': 'a4c88d1c-be9a-4366-9aca-68ddaf8be40d',
    'bar2': '91d7d070-875b-4d98-a81c-ae628eca45fd',
    'bar3': '1239d270-1bbe-f64f-b7ea-5f00518ef508',
    'bar4': '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d',
}
_BAR_KPP_MAP = {
    'bar1': '780145001',
    'bar2': '781645001',
    'bar3': '784201001',
    'bar4': '781045001',
}

# Параметры поставщиков для расчёта рекомендации к заказу.
# lead_time_days  — типичный срок от размещения заказа до приёмки (рабочих дней).
# pack_size       — минимальная партия (упаковка). Прототип: для всех 1, менеджер
#                   корректирует руками. Будущая задача — вынести в редактируемые настройки.
# Значения подобраны эмпирически по типу поставщика; уточнить с менеджером.
SUPPLIER_PARAMS = {
    'Метро':                       {'lead_time_days': 1, 'pack_size': 1},
    'Лента':                       {'lead_time_days': 1, 'pack_size': 1},
    'ООО "Май"':                   {'lead_time_days': 2, 'pack_size': 1},
    'ИП Тихомиров':                {'lead_time_days': 2, 'pack_size': 1},
    'ООО "Кулинарпродторг"':       {'lead_time_days': 2, 'pack_size': 1},
    'ИП Новиков':                  {'lead_time_days': 3, 'pack_size': 1},
    'ООО "Арбореал"':              {'lead_time_days': 3, 'pack_size': 1},
    'Криспи':                      {'lead_time_days': 3, 'pack_size': 1},
    'ООО "ВУРСТХАУСМАНУФАКТУР"':   {'lead_time_days': 3, 'pack_size': 1},
    'ООО "КВГ"':                   {'lead_time_days': 2, 'pack_size': 1},
    'ГС Маркет':                   {'lead_time_days': 2, 'pack_size': 1},
    'ООО МП Арсенал':              {'lead_time_days': 3, 'pack_size': 1},
    'ООО "МП-Арсенал АО"':         {'lead_time_days': 3, 'pack_size': 1},
}
SUPPLIER_DEFAULT = {'lead_time_days': 3, 'pack_size': 1}

# Параметры формулы рекомендации к заказу
SAFETY_DAYS = 3                  # страховой запас сверх lead_time на колебания спроса
NEAR_EXPIRY_BLOCK_DAYS = 14      # если до конца срока годности < этого — не заказываем
SLOW_MOVER_WEEKLY_SALES = 1.0    # граница slow-mover'а: < 1 продажи в неделю
FAST_MOVER_WEEKLY_SALES = 7.0    # граница fast-mover'а: ≥ 7 продаж в неделю


def _supplier_params(supplier_name):
    """Возвращает {lead_time_days, pack_size} для поставщика. Fallback — SUPPLIER_DEFAULT."""
    if not supplier_name:
        return dict(SUPPLIER_DEFAULT)
    return dict(SUPPLIER_PARAMS.get(supplier_name, SUPPLIER_DEFAULT))


def _velocity(avg_sales):
    """Классификация скорости продаж по 30-дневному среднему (продажи/день).

    Считаем в неделю (avg_sales × 7), это интуитивнее для бара:
        dead:    нет продаж за период (avg_sales = 0)
        slow:    < 1 продажи в неделю — раз в месяц/реже, не пополняем автоматически
        regular: 1–7 в неделю
        fast:    ≥ 7 в неделю
    """
    if avg_sales <= 0:
        return 'dead'
    weekly = avg_sales * 7
    if weekly < SLOW_MOVER_WEEKLY_SALES:
        return 'slow'
    if weekly < FAST_MOVER_WEEKLY_SALES:
        return 'regular'
    return 'fast'


def _calc_recommendation(stock, avg_sales, lead_time_days, pack_size, days_to_expiry, velocity):
    """Расчёт рекомендованного количества к заказу.

    target_stock = avg_sales * (lead_time_days + SAFETY_DAYS)
    deficit      = max(0, target_stock - stock)
    recommended  = ceil(deficit / pack_size) * pack_size

    Спецслучаи (рекомендация принудительно 0):
        velocity in ('dead', 'slow')       → не пополняем редко-продаваемые позиции
        0 <= days_to_expiry < 14           → расходуем то что есть на полке
    """
    if velocity in ('dead', 'slow'):
        return 0
    if avg_sales <= 0:
        return 0
    if days_to_expiry is not None and 0 <= days_to_expiry < NEAR_EXPIRY_BLOCK_DAYS:
        return 0
    target_stock = avg_sales * (lead_time_days + SAFETY_DAYS)
    deficit = target_stock - stock
    if deficit <= 0:
        return 0
    pack = max(1, int(pack_size))
    return int(math.ceil(deficit / pack) * pack)


def _urgency_level(stock, avg_sales, lead_time_days, velocity):
    """Уровень срочности позиции.

    critical: stock < 0 (учётная ошибка) — независимо от скорости продаж
    low:      velocity in ('dead', 'slow') — редко продаётся, не критично
    critical: days_left < 1
    high:     days_left < lead_time_days (поставка не успеет)
    medium:   days_left < lead_time_days + SAFETY_DAYS
    low:      остальное
    """
    if stock < 0:
        return 'critical'
    if velocity in ('dead', 'slow'):
        return 'low'
    if avg_sales <= 0:
        return 'low'
    days_left = stock / avg_sales
    if days_left < 1:
        return 'critical'
    if days_left < lead_time_days:
        return 'high'
    if days_left < lead_time_days + SAFETY_DAYS:
        return 'medium'
    return 'low'


stocks_bp = Blueprint('stocks', __name__)


@stocks_bp.route('/api/stocks/taplist', methods=['GET'])
def get_taplist_stocks():
    """API endpoint для получения остатков КЕГ из iiko API (только активные на кранах)"""
    try:
        bar = request.args.get('bar', '')

        if not bar:
            return jsonify({'error': 'Требуется параметр bar'}), 400

        # Получаем список активных кег из taps_manager
        bar_id_map = {
            'Большой пр. В.О': 'bar1',
            'Лиговский': 'bar2',
            'Кременчугская': 'bar3',
            'Варшавская': 'bar4',
            'Общая': None  # Для "Общая" покажем все бары
        }

        # Маппинг баров на склады iiko (store_id)
        store_id_map = {
            'bar1': 'a4c88d1c-be9a-4366-9aca-68ddaf8be40d',  # Большой пр. В.О
            'bar2': '91d7d070-875b-4d98-a81c-ae628eca45fd',  # Лиговский
            'bar3': '1239d270-1bbe-f64f-b7ea-5f00518ef508',  # Кременчугская
            'bar4': '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d',  # Варшавская
        }

        # Собираем список активных кег со всех кранов с номерами кранов
        active_beers = set()
        beer_to_taps = {}  # { beer_name: [tap_numbers] }

        if bar == 'Общая':
            # Для "Общая" собираем со всех баров
            for bar_id in ['bar1', 'bar2', 'bar3', 'bar4']:
                result = taps_manager.get_bar_taps(bar_id)
                if 'taps' in result:
                    for tap in result['taps']:
                        if tap.get('status') == 'active' and tap.get('current_beer'):
                            beer_name = tap['current_beer']
                            tap_number = tap.get('tap_number', '?')
                            # Обрабатываем название так же, как из остатков
                            beer_name = re.sub(r'^КЕГ\s+', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r'^Кег\s+', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r',?\s*\d+\s*л.*', '', beer_name)
                            beer_name = re.sub(r'\s+л\s*$', '', beer_name)
                            beer_name = re.sub(r',?\s*кег.*', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r',\s*$', '', beer_name)
                            beer_name = beer_name.strip()
                            active_beers.add(beer_name)
                            if beer_name not in beer_to_taps:
                                beer_to_taps[beer_name] = []
                            beer_to_taps[beer_name].append(tap_number)
        else:
            bar_id = bar_id_map.get(bar)
            if bar_id:
                result = taps_manager.get_bar_taps(bar_id)
                if 'taps' in result:
                    for tap in result['taps']:
                        if tap.get('status') == 'active' and tap.get('current_beer'):
                            beer_name = tap['current_beer']
                            tap_number = tap.get('tap_number', '?')
                            # Обрабатываем название так же, как из остатков
                            beer_name = re.sub(r'^КЕГ\s+', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r'^Кег\s+', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r',?\s*\d+\s*л.*', '', beer_name)
                            beer_name = re.sub(r'\s+л\s*$', '', beer_name)
                            beer_name = re.sub(r',?\s*кег.*', '', beer_name, flags=re.IGNORECASE)
                            beer_name = re.sub(r',\s*$', '', beer_name)
                            beer_name = beer_name.strip()
                            active_beers.add(beer_name)
                            if beer_name not in beer_to_taps:
                                beer_to_taps[beer_name] = []
                            beer_to_taps[beer_name].append(tap_number)

        # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            # Получаем номенклатуру для маппинга GUID -> информация о товаре
            nomenclature = get_cached_nomenclature(olap)
            if not nomenclature:
                return jsonify({'error': 'Не удалось получить номенклатуру'}), 500

            # Получаем РЕАЛЬНЫЕ остатки на складах (текущее время)
            current_time = datetime.now()
            print(f"[DEBUG] Текущее время сервера: {current_time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

            balances = olap.get_store_balances()
            if not balances:
                return jsonify({'error': 'Не удалось получить остатки'}), 500

            print(f"[DEBUG] Получено {len(balances)} записей остатков", flush=True)
        finally:
            olap.disconnect()

        # Определяем склад для фильтрации
        target_store_id = None
        if bar != 'Общая':
            bar_id = bar_id_map.get(bar)
            if bar_id:
                target_store_id = store_id_map.get(bar_id)

        # Обрабатываем остатки кег (GOODS в литрах)
        beer_stocks = {}

        for balance in balances:
            product_id = balance.get('product')
            amount = balance.get('amount', 0)
            store_id = balance.get('store')

            # Фильтруем по складу конкретного бара (если не "Общая")
            if target_store_id and store_id != target_store_id:
                continue

            # Получаем информацию о товаре из номенклатуры
            product_info = nomenclature.get(product_id)
            if not product_info:
                continue

            # Берем только GOODS (кеги - это товары, а не блюда!)
            if product_info.get('type') != 'GOODS':
                continue

            # Берем только литры (кеги измеряются в литрах)
            if product_info.get('mainUnit') != 'л':
                continue

            product_name = product_info.get('name', product_id)

            # Убираем "Кег" и объёмы из названия для агрегации
            base_name = product_name
            base_name = re.sub(r'^Кег\s+', '', base_name, flags=re.IGNORECASE)
            # Убираем объемы: ", 20 л", "20 л", или просто " л" в конце
            base_name = re.sub(r',?\s*\d+\s*л.*', '', base_name)
            base_name = re.sub(r'\s+л\s*$', '', base_name)  # Убираем " л" в конце если осталось
            base_name = re.sub(r',?\s*кег.*', '', base_name, flags=re.IGNORECASE)
            base_name = re.sub(r',\s*$', '', base_name)  # Убираем запятую в конце
            base_name = base_name.strip()

            # ФИЛЬТР: Показываем только кеги, которые стоят на кранах
            # Названия идентичны в iiko и на кранах, поэтому только точное сравнение
            if active_beers:
                is_active = base_name in active_beers

                # Если кега не активна, пропускаем
                if not is_active:
                    continue

            category = product_info.get('category', 'Разливное')

            if base_name not in beer_stocks:
                beer_stocks[base_name] = {
                    'remaining_liters': 0,
                    'category': category,
                    'on_tap': base_name in active_beers if active_beers else False
                }

            # Суммируем остатки по базовому названию
            beer_stocks[base_name]['remaining_liters'] += amount

        # Добавляем активные краны, которых нет в остатках (с нулевым остатком)
        for active_beer in active_beers:
            if active_beer not in beer_stocks:
                beer_stocks[active_beer] = {
                    'remaining_liters': 0,
                    'category': 'Разливное',
                    'on_tap': True
                }

        # Формируем итоговый список
        taps_data = []
        total_liters = 0
        low_stock_count = 0
        negative_stock_count = 0
        active_taps_count = len(active_beers)

        for beer_name, beer_data in beer_stocks.items():
            remaining_liters = beer_data['remaining_liters']

            # НЕ пропускаем активные краны даже с нулевым или отрицательным остатком
            # (чтобы видеть какие кеги нужно пополнить)
            if remaining_liters == 0 and not beer_data.get('on_tap', False):
                continue

            total_liters += remaining_liters if remaining_liters > 0 else 0

            # Определяем уровень остатка
            if remaining_liters < 0:
                stock_level = 'negative'
                negative_stock_count += 1
                low_stock_count += 1
            elif remaining_liters < 10:
                stock_level = 'low'
                low_stock_count += 1
            elif remaining_liters < 25:
                stock_level = 'medium'
            else:
                stock_level = 'high'

            # Получаем номера кранов для этого пива
            tap_numbers = beer_to_taps.get(beer_name, [])
            tap_numbers_str = ', '.join(map(str, sorted(tap_numbers))) if tap_numbers else '—'

            taps_data.append({
                'beer_name': beer_name,
                'category': beer_data['category'],
                'remaining_liters': round(remaining_liters, 1),
                'stock_level': stock_level,
                'on_tap': beer_data.get('on_tap', False),
                'tap_numbers': tap_numbers_str,
                'taps_count': len(tap_numbers)
            })

        # Сортируем по остатку (от меньшего к большему - что заканчивается сверху)
        taps_data.sort(key=lambda x: x['remaining_liters'])

        return jsonify({
            'total_items': len(taps_data),
            'total_liters': round(total_liters, 1),
            'low_stock_count': low_stock_count,
            'negative_stock_count': negative_stock_count,
            'active_taps_count': active_taps_count,
            'taps': taps_data
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/taplist: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@stocks_bp.route('/api/stocks/kitchen', methods=['GET'])
def get_kitchen_stocks():
    """API endpoint для получения товаров с реальными остатками из iiko"""
    try:
        bar = request.args.get('bar', '')

        if not bar:
            return jsonify({'error': 'Требуется параметр bar'}), 400

        # Маппинг баров на склады iiko (store_id)
        bar_id_map = {
            'Большой пр. В.О': 'bar1',
            'Лиговский': 'bar2',
            'Кременчугская': 'bar3',
            'Варшавская': 'bar4',
            'Общая': None
        }

        store_id_map = {
            'bar1': 'a4c88d1c-be9a-4366-9aca-68ddaf8be40d',
            'bar2': '91d7d070-875b-4d98-a81c-ae628eca45fd',
            'bar3': '1239d270-1bbe-f64f-b7ea-5f00518ef508',
            'bar4': '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d',
        }

        # Определяем склад для фильтрации
        target_store_id = None
        if bar != 'Общая':
            bar_id = bar_id_map.get(bar)
            if bar_id:
                target_store_id = store_id_map.get(bar_id)

        # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            # Получаем номенклатуру товаров (GUID -> название)
            nomenclature = get_cached_nomenclature(olap)

            if not nomenclature:
                return jsonify({'error': 'Не удалось получить номенклатуру товаров'}), 500

            # Получаем РЕАЛЬНЫЕ остатки на складах (текущий момент)
            balances = olap.get_store_balances()
            if not balances:
                return jsonify({'error': 'Не удалось получить остатки'}), 500

            # Также получаем операции за 30 дней для расчёта средних продаж
            date_to_obj = datetime.now()
            date_from_obj = datetime.now() - timedelta(days=30)
            date_to = date_to_obj.strftime("%d.%m.%Y")
            date_from = date_from_obj.strftime("%d.%m.%Y")

            bar_name = bar if bar != 'Общая' else None
            store_data = olap.get_store_operations_report(date_from, date_to, bar_name)
        finally:
            olap.disconnect()

        # Белый список категорий (поставщики кухни)
        food_categories = [
            'Метро', 'ООО "Май"', 'ООО "КВГ"', 'ГС Маркет',
            'ИП Тихомиров', 'ООО "Кулинарпродторг"',
            'ИП Новиков', 'ООО МП Арсенал', 'Лента',
            'ООО "МП-Арсенал АО"', 'Криспи',
            'ООО "ВУРСТХАУСМАНУФАКТУР"', 'ООО "Арбореал"'
        ]

        beer_keywords = ['пиво', 'beer', 'ipa', 'лагер', 'эль', 'стаут']

        def is_kitchen_product(product_info):
            """Проверяет, является ли товар продуктом кухни"""
            if not product_info:
                return False
            if product_info.get('type') == 'DISH':
                return False
            category = product_info.get('category', '') or ''
            if not category or not any(fc in category for fc in food_categories):
                return False
            product_name = product_info.get('name', '')
            if any(kw in product_name.lower() for kw in beer_keywords):
                return False
            return True

        # Шаг 1: Реальные остатки из get_store_balances
        products_dict = {}

        for balance in balances:
            product_id = balance.get('product')
            amount = balance.get('amount', 0)
            store_id = balance.get('store')

            # Фильтруем по складу
            if target_store_id and store_id != target_store_id:
                continue

            product_info = nomenclature.get(product_id)
            if not is_kitchen_product(product_info):
                continue

            product_name = product_info.get('name', product_id)
            category = product_info.get('category', '') or 'Товары'

            if product_id not in products_dict:
                products_dict[product_id] = {
                    'name': product_name,
                    'category': category,
                    'stock': 0,
                    'outgoing': 0,
                }

            products_dict[product_id]['stock'] += amount

        # Шаг 2: Средние продажи из операций за 30 дней (если данные есть)
        if store_data:
            for record in store_data:
                product_id = record.get('product')
                if not product_id or product_id not in products_dict:
                    continue

                amount = float(record.get('amount', 0) or 0)
                is_incoming = record.get('incoming', 'false') == 'true'

                if not is_incoming:
                    products_dict[product_id]['outgoing'] += abs(amount)

        # Шаг 3: Формируем итоговый список
        items = []
        days_in_period = 30

        for product_id, data in products_dict.items():
            current_stock = data['stock']
            avg_consumption = data['outgoing'] / days_in_period if days_in_period > 0 else 0

            # Определяем уровень остатков (сколько дней хватит)
            if avg_consumption > 0:
                days_left = current_stock / avg_consumption
                if days_left < 3:
                    stock_level = 'low'
                elif days_left < 7:
                    stock_level = 'medium'
                else:
                    stock_level = 'high'
            else:
                stock_level = 'high'

            items.append({
                'category': data['category'],
                'name': data['name'],
                'stock': round(current_stock, 1),
                'avg_sales': round(avg_consumption, 2),
                'stock_level': stock_level
            })

        # Сортируем по категориям и названиям
        items.sort(key=lambda x: (x['category'], x['name']))

        low_stock_count = len([item for item in items if item['stock_level'] == 'low'])

        return jsonify({
            'total_items': len(items),
            'low_stock_count': low_stock_count,
            'items': items
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/kitchen: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@stocks_bp.route('/api/stocks/bottles', methods=['GET'])
def get_bottles_stocks():
    """API endpoint для получения фасованного пива с реальными остатками из iiko"""
    try:
        bar = request.args.get('bar', '')

        if not bar:
            return jsonify({'error': 'Требуется параметр bar'}), 400

        # Маппинг баров на склады iiko (store_id)
        bar_id_map = {
            'Большой пр. В.О': 'bar1',
            'Лиговский': 'bar2',
            'Кременчугская': 'bar3',
            'Варшавская': 'bar4',
            'Общая': None
        }

        store_id_map = {
            'bar1': 'a4c88d1c-be9a-4366-9aca-68ddaf8be40d',
            'bar2': '91d7d070-875b-4d98-a81c-ae628eca45fd',
            'bar3': '1239d270-1bbe-f64f-b7ea-5f00518ef508',
            'bar4': '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d',
        }

        # Определяем склад для фильтрации
        target_store_id = None
        if bar != 'Общая':
            bar_id = bar_id_map.get(bar)
            if bar_id:
                target_store_id = store_id_map.get(bar_id)

        # Подключаемся к iiko API
        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            # Получаем номенклатуру товаров
            nomenclature = get_cached_nomenclature(olap)

            if not nomenclature:
                return jsonify({'error': 'Не удалось получить номенклатуру товаров'}), 500

            # Фильтруем товары группы "Напитки Фасовка"
            # OLAP-номенклатура: parentId = название группы (Product.TopParent)
            # XML-номенклатура: parentId = GUID группы
            FASOVKA_GROUP_ID = '6103ecbf-e6f8-49fe-8cd2-6102d49e14a6'
            FASOVKA_GROUP_NAME = 'Напитки Фасовка'

            fasovka_product_ids = set()
            for pid, pinfo in nomenclature.items():
                parent = pinfo.get('parentId', '')
                if parent == FASOVKA_GROUP_ID or parent == FASOVKA_GROUP_NAME:
                    fasovka_product_ids.add(pid)

            # Fallback: рекурсивный поиск по GUID (XML-номенклатура)
            if not fasovka_product_ids:
                fasovka_product_ids = olap.get_products_in_group(FASOVKA_GROUP_ID, nomenclature)

            print(f"[BOTTLES DEBUG] Товаров в группе 'Напитки Фасовка': {len(fasovka_product_ids)}")

            # Получаем РЕАЛЬНЫЕ остатки на складах (текущий момент)
            balances = olap.get_store_balances()
            if not balances:
                return jsonify({'error': 'Не удалось получить остатки'}), 500

            # Также получаем операции за 30 дней для расчёта средних продаж
            date_to_obj = datetime.now()
            date_from_obj = datetime.now() - timedelta(days=30)
            date_to = date_to_obj.strftime("%d.%m.%Y")
            date_from = date_from_obj.strftime("%d.%m.%Y")

            bar_name = bar if bar != 'Общая' else None
            store_data = olap.get_store_operations_report(date_from, date_to, bar_name)
        finally:
            olap.disconnect()

        # Шаг 1: Реальные остатки из get_store_balances
        products_dict = {}

        for balance in balances:
            product_id = balance.get('product')
            amount = balance.get('amount', 0)
            store_id = balance.get('store')

            # Фильтруем по складу
            if target_store_id and store_id != target_store_id:
                continue

            # Фильтруем по группе "Напитки Фасовка"
            if product_id not in fasovka_product_ids:
                continue

            product_info = nomenclature.get(product_id)
            if not product_info:
                continue

            product_name = product_info.get('name', product_id)
            supplier = product_info.get('category', 'Без поставщика')

            if product_id not in products_dict:
                products_dict[product_id] = {
                    'name': product_name,
                    'category': supplier,
                    'stock': 0,
                    'outgoing': 0,
                }

            products_dict[product_id]['stock'] += amount

        # Шаг 2: Средние продажи из операций за 30 дней (если данные есть)
        if store_data:
            for record in store_data:
                product_id = record.get('product')
                if not product_id or product_id not in products_dict:
                    continue

                amount = float(record.get('amount', 0) or 0)
                is_incoming = record.get('incoming', 'false') == 'true'

                if not is_incoming:
                    products_dict[product_id]['outgoing'] += abs(amount)

        # Шаг 3: Формируем итоговый список
        items = []
        days_in_period = 30

        for product_id, data in products_dict.items():
            current_stock = data['stock']
            avg_consumption = data['outgoing'] / days_in_period if days_in_period > 0 else 0

            # Определяем уровень остатков (сколько дней хватит)
            if avg_consumption > 0:
                days_left = current_stock / avg_consumption
                if days_left < 3:
                    stock_level = 'low'
                elif days_left < 7:
                    stock_level = 'medium'
                else:
                    stock_level = 'high'
            else:
                stock_level = 'high'

            items.append({
                'category': data['category'],
                'name': data['name'],
                'stock': round(current_stock, 1),
                'avg_sales': round(avg_consumption, 2),
                'stock_level': stock_level
            })

        # Сортируем по категориям и названиям
        items.sort(key=lambda x: (x['category'], x['name']))

        low_stock_count = len([item for item in items if item['stock_level'] == 'low'])

        print(f"\n[BOTTLES DEBUG] Итого позиций: {len(items)}, требуют пополнения: {low_stock_count}")

        return jsonify({
            'total_items': len(items),
            'low_stock_count': low_stock_count,
            'items': items
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/bottles: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@stocks_bp.route('/api/stocks/chz', methods=['GET'])
def get_chz_stocks():
    """Остатки фасованного пива из Честный ЗНАК.

    Возвращает: название - количество - срок годности
    Данные получаются через ЧЗ API (cises/search + product/info).
    Работает только на бар-ПК с установленным CryptoPro CSP и Рутокеном.
    """
    try:
        chz_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chz_test')
        if chz_path not in sys.path:
            sys.path.insert(0, chz_path)

        from chz import get_chz_stock

        stock = get_chz_stock()

        # Подсчёт кодов близких к окончанию срока (< 30 дней)
        today = datetime.now().date()
        near_expiry_codes = 0
        for item in stock:
            has_near_expiry = False
            for exp_str in item.get("expiration_dates", []):
                try:
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    if 0 <= (exp_date - today).days < 30:
                        has_near_expiry = True
                        break
                except ValueError:
                    pass
            if has_near_expiry:
                near_expiry_codes += item.get('count', 0)

        return jsonify({
            'total_items': len(stock),
            'total_codes': sum(s['count'] for s in stock),
            'near_expiry_codes': near_expiry_codes,
            'items': stock
        })

    except ImportError:
        return jsonify({'error': 'ЧЗ модуль недоступен. Требуется бар-ПК с CryptoPro CSP.'}), 503
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/chz: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@stocks_bp.route('/api/chz/stock', methods=['GET'])
def get_chz_stock_api():
    """Остатки ЧЗ с датами годности. Читает из кеша chz_stock.json."""
    try:
        mtime = os.path.getmtime(str(_CHZ_CACHE_FILE))
        updated_at = datetime.fromtimestamp(mtime).isoformat()
        with open(_CHZ_CACHE_FILE, encoding='utf-8') as f:
            items = json.load(f)
    except FileNotFoundError:
        return jsonify({'items': [], 'updated_at': None, 'error': 'no data'}), 404
    except (json.JSONDecodeError, OSError):
        return jsonify({'items': [], 'updated_at': None, 'error': 'cache corrupted or updating'}), 500

    return jsonify({'items': items, 'updated_at': updated_at})


@stocks_bp.route('/api/chz/refresh', methods=['POST'])
def refresh_chz_stock():
    """Запускает обновление кеша ЧЗ в фоне через dispenser API ЧЗ.

    Делает на бар-ПК: token refresh → chz.py csv-auto (beer+water+nabeer) →
    pull chz_stock.json. Возвращает сразу status=started; прогресс в
    chz_test/debug/refresh.log.
    """
    global _refresh_proc, _refresh_log_file
    if not os.environ.get('REMOTE_PASS'):
        return jsonify({'status': 'error', 'error': 'REMOTE_PASS not configured'}), 503
    with _refresh_lock:
        if _refresh_proc is not None:
            if _refresh_proc.poll() is None:
                return jsonify({'status': 'already_running'}), 409
            _refresh_proc = None
            if _refresh_log_file is not None:
                _refresh_log_file.close()
                _refresh_log_file = None
        remote_exec = str(_BASE_DIR / 'remote_exec.py')
        log_file = None
        try:
            # Truncate log so each refresh starts fresh
            log_file = open(_CHZ_REFRESH_LOG, 'w', encoding='utf-8')
            log_file.write(f'=== refresh started {datetime.now().isoformat()} ===\n')
            log_file.flush()
            _refresh_proc = subprocess.Popen(
                [sys.executable, remote_exec, 'run', 'csv-auto'],
                stdout=log_file,
                stderr=log_file
            )
            _refresh_log_file = log_file
        except OSError as e:
            if log_file is not None:
                log_file.close()
            return jsonify({'status': 'error', 'error': str(e)}), 500
    return jsonify({'status': 'started'})


@stocks_bp.route('/api/chz/refresh/status', methods=['GET'])
def refresh_chz_status():
    """Статус последнего/текущего refresh: running/done/idle + хвост лога."""
    global _refresh_proc
    with _refresh_lock:
        if _refresh_proc is not None:
            poll = _refresh_proc.poll()
            running = poll is None
            exit_code = poll
        else:
            running = False
            exit_code = None
    log_tail = ''
    try:
        if _CHZ_REFRESH_LOG.exists():
            with open(_CHZ_REFRESH_LOG, encoding='utf-8', errors='replace') as f:
                log_tail = f.read()[-3000:]
    except OSError:
        pass
    cache_updated = None
    try:
        cache_updated = datetime.fromtimestamp(_CHZ_CACHE_FILE.stat().st_mtime).isoformat()
    except OSError:
        pass
    return jsonify({
        'running': running,
        'exit_code': exit_code,
        'cache_updated_at': cache_updated,
        'log_tail': log_tail,
    })


@stocks_bp.route('/api/stocks/expiry', methods=['GET'])
def get_bottles_with_expiry():
    """Остатки фасовки из iiko, обогащённые сроками годности из ЧЗ.

    Стыковка iiko↔ЧЗ по barcode (EAN-13) ↔ gtin (GTIN-14, lpad'0').
    Позиции без матча в ЧЗ возвращаются с пустыми expiration_dates.
    """
    bar = request.args.get('bar', '')
    if not bar:
        return jsonify({'error': 'Требуется параметр bar'}), 400

    bar_id_map = {
        'Большой пр. В.О': 'bar1',
        'Лиговский': 'bar2',
        'Кременчугская': 'bar3',
        'Варшавская': 'bar4',
        'Общая': None,
    }
    store_id_map = {
        'bar1': 'a4c88d1c-be9a-4366-9aca-68ddaf8be40d',
        'bar2': '91d7d070-875b-4d98-a81c-ae628eca45fd',
        'bar3': '1239d270-1bbe-f64f-b7ea-5f00518ef508',
        'bar4': '1ebd631f-2e6d-4f74-8b32-0e54d9efd97d',
    }
    # Маппинг бар → КПП в ЧЗ (получен через GET /api/v3/true-api/mods/list,
    # см. chz_test/debug/mods.json). Каждая бар-точка — отдельная МОД с
    # уникальным КПП. По этому КПП в CSV-выгрузке ЧЗ привязан каждый CIS-код.
    bar_kpp_map = {
        'bar1': '780145001',  # Большой пр. В.О
        'bar2': '781645001',  # Лиговский
        'bar3': '784201001',  # Кременчугская
        'bar4': '781045001',  # Варшавская
    }

    target_store_id = None
    target_kpp = None
    if bar != 'Общая':
        bar_id = bar_id_map.get(bar)
        if bar_id:
            target_store_id = store_id_map.get(bar_id)
            target_kpp = bar_kpp_map.get(bar_id)

    olap = OlapReports()
    if not olap.connect():
        return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

    try:
        nomenclature = get_cached_nomenclature(olap)
        if not nomenclature:
            return jsonify({'error': 'Не удалось получить номенклатуру товаров'}), 500

        FASOVKA_GROUP_ID = '6103ecbf-e6f8-49fe-8cd2-6102d49e14a6'
        FASOVKA_GROUP_NAME = 'Напитки Фасовка'

        fasovka_product_ids = set()
        for pid, pinfo in nomenclature.items():
            parent = pinfo.get('parentId', '')
            if parent == FASOVKA_GROUP_ID or parent == FASOVKA_GROUP_NAME:
                fasovka_product_ids.add(pid)
        if not fasovka_product_ids:
            fasovka_product_ids = olap.get_products_in_group(FASOVKA_GROUP_ID, nomenclature)

        balances = olap.get_store_balances()
        if not balances:
            return jsonify({'error': 'Не удалось получить остатки'}), 500

        date_to_obj = datetime.now()
        date_from_obj = datetime.now() - timedelta(days=30)
        date_to = date_to_obj.strftime("%d.%m.%Y")
        date_from = date_from_obj.strftime("%d.%m.%Y")
        bar_name = bar if bar != 'Общая' else None
        store_data = olap.get_store_operations_report(date_from, date_to, bar_name)
    finally:
        olap.disconnect()

    products_dict = {}
    for balance in balances:
        product_id = balance.get('product')
        amount = balance.get('amount', 0)
        store_id = balance.get('store')

        if target_store_id and store_id != target_store_id:
            continue
        if product_id not in fasovka_product_ids:
            continue

        product_info = nomenclature.get(product_id)
        if not product_info:
            continue

        if product_id not in products_dict:
            products_dict[product_id] = {
                'name': product_info.get('name', product_id),
                'category': product_info.get('category', 'Без поставщика'),
                'stock': 0,
                'outgoing': 0,
            }
        products_dict[product_id]['stock'] += amount

    if store_data:
        for record in store_data:
            product_id = record.get('product')
            if not product_id or product_id not in products_dict:
                continue
            amount = float(record.get('amount', 0) or 0)
            is_incoming = record.get('incoming', 'false') == 'true'
            if not is_incoming:
                products_dict[product_id]['outgoing'] += abs(amount)

    barcode_map = get_barcode_map()
    product_to_gtins = invert_to_product_gtins(barcode_map)

    chz_by_gtin = {}
    chz_updated_at = None
    try:
        chz_mtime = os.path.getmtime(str(_CHZ_CACHE_FILE))
        chz_updated_at = datetime.fromtimestamp(chz_mtime).isoformat()
        with open(_CHZ_CACHE_FILE, encoding='utf-8') as f:
            chz_items = json.load(f)
        for item in chz_items:
            gtin = str(item.get('gtin', '')).zfill(14)
            chz_by_gtin[gtin] = item
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f"[EXPIRY] CHZ cache unavailable: {e}")

    today = datetime.now().date()
    days_in_period = 30
    items = []
    matched_count = 0
    near_expiry_count = 0

    for product_id, data in products_dict.items():
        current_stock = data['stock']
        avg_consumption = data['outgoing'] / days_in_period if days_in_period > 0 else 0
        if avg_consumption > 0:
            days_left = current_stock / avg_consumption
            if days_left < 3:
                stock_level = 'low'
            elif days_left < 7:
                stock_level = 'medium'
            else:
                stock_level = 'high'
        else:
            stock_level = 'high'

        gtins = product_to_gtins.get(product_id, [])
        matched_gtins = []
        # Собираем партии: либо ТОЛЬКО для нашего КПП (когда выбран
        # конкретный бар), либо со всех КПП юрлица (когда bar='Общая').
        bar_batches = []           # список {production_date, expiration_date, count}
        bar_chz_count = 0          # сколько кодов в ЧЗ числится за этим баром
        chz_total_count = 0        # итог по всему юрлицу (для контекста)
        for g in gtins:
            chz_item = chz_by_gtin.get(g)
            if not chz_item:
                continue
            matched_gtins.append(g)
            chz_total_count += chz_item.get('count', 0)
            by_kpp = chz_item.get('by_kpp', [])
            if target_kpp:
                # фильтруем только наш бар
                for slot in by_kpp:
                    if slot.get('kpp') == target_kpp:
                        bar_chz_count += slot.get('count', 0)
                        for b in slot.get('batches', []):
                            bar_batches.append(b)
            else:
                # bar='Общая' — все партии юрлица
                bar_chz_count = chz_total_count
                for b in chz_item.get('batches', []):
                    bar_batches.append(b)

        bar_batches.sort(key=lambda b: b.get('production_date', ''), reverse=True)

        # Объединённые даты ИЗ НАШИХ партий (не со всего юрлица)
        expiration_dates = sorted({b['expiration_date'] for b in bar_batches if b.get('expiration_date')})
        production_dates = sorted({b['production_date'] for b in bar_batches if b.get('production_date')})

        has_chz_data = bool(matched_gtins) and bool(bar_batches)
        # Note: матч по GTIN найден, но конкретно за этим баром нет партий —
        # отдельный кейс: товар у нас в iiko есть, в ЧЗ есть для юрлица,
        # но не на этом КПП. Тогда has_chz_data=False для этого бара.
        if has_chz_data:
            matched_count += 1

        # Партии от свежих к старым, но без эвристики «обрезаем под iiko-сток» —
        # данные точные, показываем все партии этого бара (бар не RETIRE'ит,
        # поэтому bar_chz_count может быть > current_stock, что нормально).
        nearest_expiry = None
        latest_expiry = None
        days_to_expiry = None
        if expiration_dates:
            future = [d for d in expiration_dates if d >= today.isoformat()]
            nearest_expiry = future[0] if future else expiration_dates[-1]
            latest_expiry = expiration_dates[-1]
            try:
                exp_date = datetime.strptime(nearest_expiry, "%Y-%m-%d").date()
                days_to_expiry = (exp_date - today).days
                if 0 <= days_to_expiry < 30:
                    near_expiry_count += 1
            except ValueError:
                pass

        items.append({
            'name': data['name'],
            'category': data['category'],
            'stock': round(current_stock, 1),
            'avg_sales': round(avg_consumption, 2),
            'stock_level': stock_level,
            'gtins': matched_gtins,
            'chz_total_count': chz_total_count,    # коды по всему юрлицу
            'bar_chz_count': bar_chz_count,        # коды на КПП этого бара
            'expiration_dates': expiration_dates,
            'production_dates': production_dates,
            'inferred_batches': bar_batches,       # партии этого бара (точные, не эвристика)
            'nearest_expiry': nearest_expiry,
            'latest_expiry': latest_expiry,
            'days_to_expiry': days_to_expiry,
            'has_chz_data': has_chz_data,
        })

    def sort_key(it):
        d = it['days_to_expiry']
        if d is None:
            return (2, 0)
        if d < 30:
            return (0, d)
        return (1, d)

    items.sort(key=sort_key)

    return jsonify({
        'bar': bar,
        'updated_at': datetime.now().isoformat(),
        'chz_updated_at': chz_updated_at,
        'total_items': len(items),
        'matched_items': matched_count,
        'near_expiry_count': near_expiry_count,
        'items': items,
    })


@stocks_bp.route('/api/stocks/order-board', methods=['GET'])
def get_order_board():
    """Сводная таблица заказа: фасовка + кеги + кухня в одной таблице.

    Каждая позиция содержит расчёт рекомендованного количества к заказу.
    Ответ сортируется по срочности (critical→high→medium→low), внутри — по days_left.

    Формула рекомендации (см. _calc_recommendation):
        target_stock = avg_sales × (lead_time_days + SAFETY_DAYS)
        deficit      = max(0, target_stock − stock)
        recommended  = ceil(deficit / pack_size) × pack_size

    Где:
        avg_sales        — расход/день за последние 30 дней (get_store_operations_report)
        lead_time_days   — срок поставки от поставщика (SUPPLIER_PARAMS)
        SAFETY_DAYS = 3  — страховой запас на колебания спроса
        pack_size        — минимальная партия (упаковка)

    Если для позиции есть данные ЧЗ и ближайшая партия истекает <14 дней —
    рекомендация принудительно 0 (расходуем то что есть на полке).
    Срочность: см. _urgency_level.
    """
    try:
        bar = request.args.get('bar', '')
        if not bar:
            return jsonify({'error': 'Требуется параметр bar'}), 400

        target_store_id = None
        target_kpp = None
        if bar != 'Общая':
            bar_id = _BAR_ID_MAP.get(bar)
            if bar_id:
                target_store_id = _STORE_ID_MAP.get(bar_id)
                target_kpp = _BAR_KPP_MAP.get(bar_id)

        olap = OlapReports()
        if not olap.connect():
            return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

        try:
            nomenclature = get_cached_nomenclature(olap)
            if not nomenclature:
                return jsonify({'error': 'Не удалось получить номенклатуру товаров'}), 500

            FASOVKA_GROUP_ID = '6103ecbf-e6f8-49fe-8cd2-6102d49e14a6'
            FASOVKA_GROUP_NAME = 'Напитки Фасовка'
            fasovka_ids = set()
            for pid, pinfo in nomenclature.items():
                parent = pinfo.get('parentId', '')
                if parent == FASOVKA_GROUP_ID or parent == FASOVKA_GROUP_NAME:
                    fasovka_ids.add(pid)
            if not fasovka_ids:
                fasovka_ids = olap.get_products_in_group(FASOVKA_GROUP_ID, nomenclature)

            balances = olap.get_store_balances() or []

            date_to = datetime.now().strftime("%d.%m.%Y")
            date_from = (datetime.now() - timedelta(days=30)).strftime("%d.%m.%Y")
            bar_name = bar if bar != 'Общая' else None
            store_data = olap.get_store_operations_report(date_from, date_to, bar_name) or []
        finally:
            olap.disconnect()

        # Кухонный белый список (тот же что в /api/stocks/kitchen)
        food_categories = [
            'Метро', 'ООО "Май"', 'ООО "КВГ"', 'ГС Маркет',
            'ИП Тихомиров', 'ООО "Кулинарпродторг"',
            'ИП Новиков', 'ООО МП Арсенал', 'Лента',
            'ООО "МП-Арсенал АО"', 'Криспи',
            'ООО "ВУРСТХАУСМАНУФАКТУР"', 'ООО "Арбореал"'
        ]
        beer_keywords = ['пиво', 'beer', 'ipa', 'лагер', 'эль', 'стаут']

        def classify(product_id, product_info):
            """Возвращает 'bottle' | 'draft' | 'kitchen' | None."""
            if not product_info:
                return None
            if product_info.get('type') == 'DISH':
                return None
            if product_id in fasovka_ids:
                return 'bottle'
            if product_info.get('type') == 'GOODS' and product_info.get('mainUnit') == 'л':
                return 'draft'
            category = product_info.get('category', '') or ''
            if not category or not any(fc in category for fc in food_categories):
                return None
            product_name = product_info.get('name', '')
            if any(kw in product_name.lower() for kw in beer_keywords):
                return None
            return 'kitchen'

        # Шаг 1: остатки
        products_dict = {}
        for balance in balances:
            product_id = balance.get('product')
            amount = balance.get('amount', 0)
            store_id = balance.get('store')
            if target_store_id and store_id != target_store_id:
                continue
            product_info = nomenclature.get(product_id)
            kind = classify(product_id, product_info)
            if not kind:
                continue
            if product_id not in products_dict:
                products_dict[product_id] = {
                    'name': product_info.get('name', product_id),
                    'supplier': product_info.get('category', 'Без поставщика') or 'Без поставщика',
                    'type': kind,
                    'unit': product_info.get('mainUnit', 'шт') or 'шт',
                    'stock': 0,
                    'outgoing': 0,
                }
            products_dict[product_id]['stock'] += amount

        # Шаг 2: расход за 30 дней
        for record in store_data:
            product_id = record.get('product')
            if not product_id or product_id not in products_dict:
                continue
            amount = float(record.get('amount', 0) or 0)
            if record.get('incoming', 'false') != 'true':
                products_dict[product_id]['outgoing'] += abs(amount)

        # Шаг 3: ЧЗ-обогащение для bottle
        barcode_map = get_barcode_map()
        product_to_gtins = invert_to_product_gtins(barcode_map)
        chz_by_gtin = {}
        chz_updated_at = None
        try:
            chz_mtime = os.path.getmtime(str(_CHZ_CACHE_FILE))
            chz_updated_at = datetime.fromtimestamp(chz_mtime).isoformat()
            with open(_CHZ_CACHE_FILE, encoding='utf-8') as f:
                chz_items = json.load(f)
            for item in chz_items:
                gtin = str(item.get('gtin', '')).zfill(14)
                chz_by_gtin[gtin] = item
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

        today = datetime.now().date()
        days_in_period = 30
        items = []

        for product_id, data in products_dict.items():
            stock = data['stock']
            avg_sales = data['outgoing'] / days_in_period

            nearest_expiry = None
            days_to_expiry = None
            if data['type'] == 'bottle':
                gtins = product_to_gtins.get(product_id, [])
                bar_batches = []
                for g in gtins:
                    chz_item = chz_by_gtin.get(g)
                    if not chz_item:
                        continue
                    if target_kpp:
                        for slot in chz_item.get('by_kpp', []):
                            if slot.get('kpp') == target_kpp:
                                for b in slot.get('batches', []):
                                    bar_batches.append(b)
                    else:
                        for b in chz_item.get('batches', []):
                            bar_batches.append(b)
                exp_dates = sorted({b['expiration_date'] for b in bar_batches if b.get('expiration_date')})
                if exp_dates:
                    future = [d for d in exp_dates if d >= today.isoformat()]
                    nearest_expiry = future[0] if future else exp_dates[-1]
                    try:
                        exp = datetime.strptime(nearest_expiry, "%Y-%m-%d").date()
                        days_to_expiry = (exp - today).days
                    except ValueError:
                        pass

            params = _supplier_params(data['supplier'])
            lead_time = params['lead_time_days']
            pack_size = params['pack_size']
            velocity = _velocity(avg_sales)
            weekly_sales = avg_sales * 7
            days_left = (stock / avg_sales) if avg_sales > 0 else None
            recommended = _calc_recommendation(stock, avg_sales, lead_time, pack_size, days_to_expiry, velocity)
            urgency = _urgency_level(stock, avg_sales, lead_time, velocity)

            items.append({
                'product_id': product_id,
                'type': data['type'],
                'name': data['name'],
                'supplier': data['supplier'],
                'unit': data['unit'],
                'stock': round(stock, 1),
                'avg_sales': round(avg_sales, 2),
                'weekly_sales': round(weekly_sales, 2),
                'velocity': velocity,
                'days_left': round(days_left, 1) if days_left is not None else None,
                'lead_time_days': lead_time,
                'pack_size': pack_size,
                'recommended': recommended,
                'urgency': urgency,
                'nearest_expiry': nearest_expiry,
                'days_to_expiry': days_to_expiry,
            })

        # Сортировка: сначала срочность, внутри — по days_left возрастающе
        urgency_rank = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}

        def sort_key(it):
            u = urgency_rank.get(it['urgency'], 99)
            d = it['days_left'] if it['days_left'] is not None else 9999
            return (u, d)

        items.sort(key=sort_key)

        return jsonify({
            'bar': bar,
            'updated_at': datetime.now().isoformat(),
            'chz_updated_at': chz_updated_at,
            'safety_days': SAFETY_DAYS,
            'near_expiry_block_days': NEAR_EXPIRY_BLOCK_DAYS,
            'slow_mover_weekly_sales': SLOW_MOVER_WEEKLY_SALES,
            'fast_mover_weekly_sales': FAST_MOVER_WEEKLY_SALES,
            'total_items': len(items),
            'critical_count': sum(1 for i in items if i['urgency'] == 'critical'),
            'high_count': sum(1 for i in items if i['urgency'] == 'high'),
            'medium_count': sum(1 for i in items if i['urgency'] == 'medium'),
            'active_count': sum(1 for i in items if i['velocity'] in ('regular', 'fast')),
            'slow_count': sum(1 for i in items if i['velocity'] == 'slow'),
            'dead_count': sum(1 for i in items if i['velocity'] == 'dead'),
            'recommended_total': sum(i['recommended'] for i in items),
            'items': items,
        })

    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/order-board: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
