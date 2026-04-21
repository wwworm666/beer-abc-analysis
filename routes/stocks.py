from flask import Blueprint, request, jsonify
import re
import json
from datetime import datetime, timedelta
from core.olap_reports import OlapReports
from extensions import taps_manager, get_cached_nomenclature, BARS

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

            # НЕ пропускаем отрицательные остатки - они важны для контроля!
            # Пропускаем только нулевые, если кега не активна
            if amount == 0:
                # Пропустим потом при проверке на активность
                pass

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
        import sys
        import os
        chz_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chz_test')
        if chz_path not in sys.path:
            sys.path.insert(0, chz_path)

        from chz import get_chz_stock

        stock = get_chz_stock()

        # Подсчёт GTIN близких к окончанию срока (< 30 дней)
        from datetime import datetime
        today = datetime.now().date()
        near_expiry = 0
        for item in stock:
            for exp_str in item.get("expiration_dates", []):
                try:
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    if (exp_date - today).days < 30:
                        near_expiry += 1
                        break
                except ValueError:
                    pass

        return jsonify({
            'total_items': len(stock),
            'total_codes': sum(s['count'] for s in stock),
            'near_expiry': near_expiry,
            'items': stock
        })

    except ImportError:
        return jsonify({'error': 'ЧЗ модуль недоступен. Требуется бар-ПК с CryptoPro CSP.'}), 503
    except Exception as e:
        print(f"[ERROR] Oshibka v /api/stocks/chz: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
