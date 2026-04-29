"""Shelf-Life Cockpit — отдельная страница для управления сроками годности.

Расширяет данные `/api/stocks/expiry` полями для action layer:
- price (₽ за шт. из iiko nomenclature),
- risk_rub (stock × price),
- tier (expired/critical/urgent/watch/fresh/unknown),
- recommendations (уценка / перевод).

См. docs/expiration.md для формул.
"""

from flask import Blueprint, request, jsonify, render_template
import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timedelta

from core.olap_reports import OlapReports
from core.iiko_barcodes import get_barcode_map, invert_to_product_gtins
from core.expiry_recommend import classify_tier, recommend
from extensions import get_cached_nomenclature, BARS

expiration_bp = Blueprint('expiration', __name__)

# In-memory TTL-кеш ответа /api/expiration/board.
# Ключ — нормализованная строка bars-параметра (например, "bar1,bar2" или "all").
# TTL=120 сек: балансы и обороты меняются медленно, риск списания — ещё медленнее.
# Force-refresh через ?force=1.
_BOARD_CACHE: dict[str, tuple[float, dict]] = {}
_BOARD_CACHE_TTL = 120  # секунды
_BOARD_CACHE_LOCK = threading.Lock()

_BASE_DIR = Path(__file__).resolve().parent.parent
_CHZ_CACHE_FILE = _BASE_DIR / 'chz_test' / 'debug' / 'chz_stock.json'

_BAR_ID_MAP = {
    'Большой пр. В.О': 'bar1',
    'Лиговский': 'bar2',
    'Кременчугская': 'bar3',
    'Варшавская': 'bar4',
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
_ID_TO_BAR = {v: k for k, v in _BAR_ID_MAP.items()}

DAYS_IN_PERIOD = 30


@expiration_bp.route('/expiration')
def expiration_page():
    """Страница Shelf-Life Cockpit."""
    return render_template('expiration.html', bars=BARS)


def _stock_level(stock: float, velocity: float) -> str:
    """Уровень запаса по дням хватания (дублирует логику routes/stocks.py)."""
    if velocity <= 0:
        return 'high'
    days_left = stock / velocity
    if days_left < 3:
        return 'low'
    if days_left < 7:
        return 'medium'
    return 'high'


def _build_bar_data(olap, nomenclature, bar_id: str, fasovka_ids: set,
                    balances: list, ops: list) -> dict:
    """Собрать data {product_id: {stock, outgoing, price}} по конкретному бару.

    `balances` и `ops` уже подгружены снаружи (балансы — общий список по всем складам,
    операции — по конкретному бару). Это снимает N лишних запросов /balances в цикле.

    price — себестоимость единицы (cost basis), считается как cost_sum / stock,
    где cost_sum — сумма из balances (поле `sum`), а stock — суммарный остаток.
    Это честная база для оценки риска списания: сколько денег уйдёт «в минус»
    при списании партии. Не цена продажи (sale price отсутствует в nomenclature).
    """
    target_store = _STORE_ID_MAP.get(bar_id)

    products = {}
    for b in balances:
        pid = b.get('product')
        if pid not in fasovka_ids:
            continue
        if b.get('store') != target_store:
            continue
        info = nomenclature.get(pid) or {}
        if pid not in products:
            products[pid] = {
                'name': info.get('name', pid),
                'category': info.get('category', 'Без поставщика'),
                'price': 0.0,
                'stock': 0.0,
                'cost_sum': 0.0,
                'outgoing': 0.0,
            }
        products[pid]['stock'] += float(b.get('amount', 0) or 0)
        products[pid]['cost_sum'] += float(b.get('sum', 0) or 0)

    # Себестоимость за единицу = cost_sum / stock (если stock > 0).
    for pid, p in products.items():
        if p['stock'] > 0:
            p['price'] = round(p['cost_sum'] / p['stock'], 2)

    for r in ops:
        pid = r.get('product')
        if pid not in products:
            continue
        amt = float(r.get('amount', 0) or 0)
        if r.get('incoming', 'false') != 'true':
            products[pid]['outgoing'] += abs(amt)

    return products


def _bar_batches_for(chz_item: dict, target_kpp: str | None):
    """Партии этого GTIN для конкретного КПП (бара) или для всего юрлица."""
    bar_count = 0
    bar_batches = []
    if target_kpp:
        for slot in chz_item.get('by_kpp', []):
            if slot.get('kpp') == target_kpp:
                bar_count += slot.get('count', 0)
                for b in slot.get('batches', []):
                    bar_batches.append(b)
    else:
        bar_count = chz_item.get('count', 0)
        for b in chz_item.get('batches', []):
            bar_batches.append(b)
    return bar_count, bar_batches


@expiration_bp.route('/api/expiration/board', methods=['GET'])
def expiration_board():
    """Сводный board по 1..N барам.

    Параметры:
        bars=bar1,bar2 — список ID, либо bars=all → все 4 бара.

    Ответ:
        {
            updated_at, chz_updated_at,
            kpi: {risk_rub, critical_count, surplus_units},
            tier_counts: {expired, critical, urgent, watch, fresh, unknown},
            calendar: [{date, risk_rub}, ...30],
            items: [{...}, ...]
        }

    Каждый item: name, category, bar, gtin, stock, avg_sales, price,
    days_to_expiry, nearest_expiry, surplus, risk_rub, tier, recommendations,
    inferred_batches, has_chz_data.
    """
    bars_param = request.args.get('bars', 'all')
    force = request.args.get('force', '0') == '1'
    if bars_param == 'all':
        target_bar_ids = list(_STORE_ID_MAP.keys())
    else:
        target_bar_ids = [b.strip() for b in bars_param.split(',') if b.strip() in _STORE_ID_MAP]
    if not target_bar_ids:
        return jsonify({'error': 'Нет валидных bar_id в параметре bars'}), 400

    cache_key = ','.join(sorted(target_bar_ids))
    if not force:
        with _BOARD_CACHE_LOCK:
            entry = _BOARD_CACHE.get(cache_key)
        if entry and (time.time() - entry[0]) < _BOARD_CACHE_TTL:
            cached = dict(entry[1])
            cached['cache'] = {'hit': True, 'age_sec': int(time.time() - entry[0])}
            return jsonify(cached)

    olap = OlapReports()
    if not olap.connect():
        return jsonify({'error': 'Не удалось подключиться к iiko API'}), 500

    try:
        nomenclature = get_cached_nomenclature(olap)
        if not nomenclature:
            return jsonify({'error': 'Не удалось получить номенклатуру'}), 500

        FASOVKA_GROUP_ID = '6103ecbf-e6f8-49fe-8cd2-6102d49e14a6'
        FASOVKA_GROUP_NAME = 'Напитки Фасовка'
        fasovka_ids = {
            pid for pid, info in nomenclature.items()
            if info.get('parentId') in (FASOVKA_GROUP_ID, FASOVKA_GROUP_NAME)
        }
        if not fasovka_ids:
            fasovka_ids = olap.get_products_in_group(FASOVKA_GROUP_ID, nomenclature)

        # 1) Балансы — ОДИН запрос на все бары (раньше было N).
        balances = olap.get_store_balances() or []

        # 2) Операции — параллельно по барам через ThreadPoolExecutor.
        date_to = datetime.now().strftime("%d.%m.%Y")
        date_from = (datetime.now() - timedelta(days=DAYS_IN_PERIOD)).strftime("%d.%m.%Y")

        def fetch_ops(bid):
            bar_name = _ID_TO_BAR.get(bid)
            return bid, (olap.get_store_operations_report(date_from, date_to, bar_name) or [])

        ops_by_bar: dict[str, list] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(target_bar_ids))) as ex:
            for bid, ops in ex.map(fetch_ops, target_bar_ids):
                ops_by_bar[bid] = ops

        bar_data = {
            bid: _build_bar_data(olap, nomenclature, bid, fasovka_ids,
                                 balances, ops_by_bar.get(bid, []))
            for bid in target_bar_ids
        }
    finally:
        olap.disconnect()

    # ЧЗ-кэш
    chz_by_gtin = {}
    chz_updated_at = None
    try:
        chz_updated_at = datetime.fromtimestamp(_CHZ_CACHE_FILE.stat().st_mtime).isoformat()
        with open(_CHZ_CACHE_FILE, encoding='utf-8') as f:
            for it in json.load(f):
                gtin = str(it.get('gtin', '')).zfill(14)
                chz_by_gtin[gtin] = it
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f"[EXPIRATION] CHZ cache unavailable: {e}")

    barcode_map = get_barcode_map()
    product_to_gtins = invert_to_product_gtins(barcode_map)

    today = datetime.now().date()
    items = []

    # Сначала собираем «сырые» позиции по всем барам, потом считаем
    # transfer_candidates (нужны cross-bar данные).
    raw = []  # [(bar_id, product_id, item_dict)]
    for bar_id in target_bar_ids:
        target_kpp = _BAR_KPP_MAP.get(bar_id)
        for pid, data in bar_data[bar_id].items():
            stock = data['stock']
            velocity = data['outgoing'] / DAYS_IN_PERIOD if DAYS_IN_PERIOD > 0 else 0

            gtins = product_to_gtins.get(pid, [])
            matched_gtins = []
            bar_batches = []
            bar_chz_count = 0
            chz_total_count = 0
            for g in gtins:
                ci = chz_by_gtin.get(g)
                if not ci:
                    continue
                matched_gtins.append(g)
                chz_total_count += ci.get('count', 0)
                cnt, batches = _bar_batches_for(ci, target_kpp)
                bar_chz_count += cnt
                bar_batches.extend(batches)

            bar_batches.sort(key=lambda b: b.get('production_date', ''), reverse=True)

            expirations = sorted({b['expiration_date'] for b in bar_batches if b.get('expiration_date')})
            productions = sorted({b['production_date'] for b in bar_batches if b.get('production_date')})

            has_chz = bool(matched_gtins) and bool(bar_batches)
            nearest_expiry = None
            days_to_expiry = None
            if expirations:
                future = [d for d in expirations if d >= today.isoformat()]
                nearest_expiry = future[0] if future else expirations[-1]
                try:
                    exp_date = datetime.strptime(nearest_expiry, "%Y-%m-%d").date()
                    days_to_expiry = (exp_date - today).days
                except ValueError:
                    pass

            raw.append((bar_id, pid, {
                'bar_id': bar_id,
                'bar': _ID_TO_BAR.get(bar_id, bar_id),
                'product_id': pid,
                'name': data['name'],
                'category': data['category'],
                'price': data['price'],
                'stock': round(stock, 1),
                'avg_sales': round(velocity, 2),
                'gtins': matched_gtins,
                'has_chz_data': has_chz,
                'bar_chz_count': bar_chz_count,
                'chz_total_count': chz_total_count,
                'expiration_dates': expirations,
                'production_dates': productions,
                'inferred_batches': bar_batches,
                'nearest_expiry': nearest_expiry,
                'days_to_expiry': days_to_expiry,
            }))

    # Индекс кандидатов на перевод по product_id (другие бары с тем же товаром).
    candidates_by_pid: dict[str, list[dict]] = {}
    for bar_id, pid, it in raw:
        candidates_by_pid.setdefault(pid, []).append({
            'bar': it['bar'],
            'bar_id': bar_id,
            'velocity': it['avg_sales'],
            'stock': it['stock'],
            'stock_level': _stock_level(it['stock'], it['avg_sales']),
        })

    # Финальная сборка с tier/recommendations/risk_rub.
    tier_counts = {'expired': 0, 'critical': 0, 'urgent': 0, 'watch': 0, 'fresh': 0, 'unknown': 0}
    risk_rub_total = 0.0
    surplus_units_total = 0.0
    critical_count = 0

    for bar_id, pid, it in raw:
        # Кандидаты — другие бары с этим же товаром.
        cands = [c for c in candidates_by_pid.get(pid, []) if c['bar_id'] != bar_id]
        rec = recommend(it, cands)

        tier = rec['tier']
        surplus = rec['surplus']
        price = it['price']
        risk = round(surplus * price, 0) if surplus > 0 and price > 0 else 0

        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        if tier in ('critical', 'expired'):
            critical_count += 1
        if tier != 'unknown' and tier != 'fresh':
            risk_rub_total += risk
            surplus_units_total += surplus

        it['tier'] = tier
        it['surplus'] = surplus
        it['risk_rub'] = int(risk)
        it['recommendation'] = rec
        items.append(it)

    # Сортировка: tier severity → days → risk
    tier_order = {'expired': 0, 'critical': 1, 'urgent': 2, 'watch': 3, 'fresh': 4, 'unknown': 5}

    def sort_key(it):
        return (
            tier_order.get(it['tier'], 99),
            it['days_to_expiry'] if it['days_to_expiry'] is not None else 9999,
            -it['risk_rub'],
        )

    items.sort(key=sort_key)

    response = {
        'updated_at': datetime.now().isoformat(),
        'chz_updated_at': chz_updated_at,
        'bars': [_ID_TO_BAR.get(b, b) for b in target_bar_ids],
        'kpi': {
            'risk_rub': int(round(risk_rub_total)),
            'critical_count': critical_count,
            'surplus_units': round(surplus_units_total, 1),
        },
        'tier_counts': tier_counts,
        'items': items,
        'cache': {'hit': False, 'age_sec': 0},
    }

    with _BOARD_CACHE_LOCK:
        _BOARD_CACHE[cache_key] = (time.time(), response)

    return jsonify(response)
