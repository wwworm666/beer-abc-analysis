"""Раздел «Аналитика гостей (CRM)» — HTTP-слой.

Все отчёты считаются по локальной витрине guests.db (core/guest_store.py),
наполняемой фоновым синком из iiko OLAP (core/guest_sync.py) — при просмотре
обращений к iiko нет. Формулы метрик: core/guest_analytics.py (докстринги),
пользователю — тултипы и блок «Как считается» (static/js/guests/formulas.js).

Параметры периода (одинаково у всех отчётных эндпоинтов):
    ?period_type=week|month|quarter|year&anchor=YYYY-MM-DD
anchor — любая дата внутри периода; дефолт: текущий календарный месяц.
Каждый ответ несёт meta: границы срезов (P/YTD/asof), покрытие витрины,
доля fallback-регистраций.

Авторизация: глобальный гейт _auth_gate закрывает всё для неавторизованных;
ручной запуск синка — только админ. Кэш тяжёлых отчётов — cached_olap
(extensions.py) с ключом от версии данных витрины: после ночного синка
ключ меняется и кэш инвалидируется сам.

Документация: docs/guests.md
"""

import csv
import io

from flask import Blueprint, Response, jsonify, render_template, request

from core import guest_analytics as ga
from core import guest_sync
from core.auth_guard import admin_required
from core.guest_store import get_store
from extensions import APP_VERSION, cached_olap

guests_bp = Blueprint('guests', __name__)


def _ctx():
    """Общий разбор параметров периода: (store, period, meta)."""
    store = get_store()
    period = ga.resolve_period(
        request.args.get('period_type', 'month'),
        request.args.get('anchor'))
    meta = ga.build_meta(store, period)
    return store, period, meta


def _cache_key(name, meta, *extra):
    """Ключ кэша отчёта: имя + период + версия данных витрины."""
    version = meta['last_synced_at'] or ''
    parts = [name, meta['p_start'], meta['p_end'], version] + [str(e) for e in extra]
    return 'guests_' + '_'.join(parts)


# ------------------------------------------------------------------ страница

@guests_bp.route('/guests')
def guests_page():
    return render_template('guests.html', app_version=APP_VERSION)


# ------------------------------------------------------------------ отчёты

@guests_bp.route('/api/guests/summary')
def api_summary():
    """Сводка (ТЗ §14)."""
    try:
        store, period, meta = _ctx()
        data = cached_olap(_cache_key('summary', meta),
                           lambda: ga.summary(store, period, meta))
        return jsonify({'meta': meta, 'data': data})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/base-growth')
def api_base_growth():
    """Рост клиентской базы (ТЗ §1)."""
    try:
        store, period, meta = _ctx()
        return jsonify({'meta': meta, 'data': ga.base_growth(store, period, meta)})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/base-dynamics')
def api_base_dynamics():
    """Динамика базы помесячно (ТЗ §13). ?months=24"""
    try:
        months = min(max(int(request.args.get('months', 24)), 3), 60)
        store, period, meta = _ctx()
        data = cached_olap(_cache_key('dynamics', meta, months),
                           lambda: ga.base_dynamics(store, period, meta, months))
        return jsonify({'meta': meta, 'data': data})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/activity')
def api_activity():
    """Активность базы на дату среза (ТЗ §3)."""
    try:
        store, period, meta = _ctx()
        return jsonify({'meta': meta, 'data': ga.activity(store, period, meta)})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/frequency')
def api_frequency():
    """Частота посещений за период (ТЗ §4)."""
    try:
        store, period, meta = _ctx()
        return jsonify({'meta': meta, 'data': ga.frequency(store, period, meta)})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/cohorts/lifecycle')
def api_cohorts_lifecycle():
    """Когорты жизненного цикла от регистрации (ТЗ §2)."""
    try:
        store, period, meta = _ctx()
        data = cached_olap(_cache_key('lifecycle', meta),
                           lambda: ga.lifecycle_cohorts(store, period, meta))
        return jsonify({'meta': meta, 'data': data})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/retention')
def api_retention():
    """Retention-когорты (ТЗ §5; ?basis=registration — retention-слой §2)."""
    try:
        basis = request.args.get('basis', 'first_order')
        if basis not in ('first_order', 'registration'):
            basis = 'first_order'
        store, period, meta = _ctx()
        data = cached_olap(_cache_key('retention', meta, basis),
                           lambda: ga.cohort_retention(store, period, meta, basis))
        return jsonify({'meta': meta, 'data': data})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/cohorts/revenue')
def api_cohorts_revenue():
    """Когортные доходы (ТЗ §6). ?basis=registration|first_order"""
    try:
        basis = request.args.get('basis', 'registration')
        if basis not in ('registration', 'first_order'):
            basis = 'registration'
        store, period, meta = _ctx()
        data = cached_olap(_cache_key('cohort_rev', meta, basis),
                           lambda: ga.cohort_revenue(store, period, meta, basis))
        return jsonify({'meta': meta, 'data': data})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/rfm')
def api_rfm():
    """RFM-сегментация на дату среза, окно 12 мес (ТЗ §7). ?export=csv"""
    try:
        store, period, meta = _ctx()
        data = ga.rfm(store, period, meta, include_guests=True)
        if request.args.get('export') == 'csv':
            buf = io.StringIO()
            w = csv.writer(buf, delimiter=';')
            w.writerow(['Телефон', 'Карта', 'Имя', 'Дней с визита',
                        'Визитов за 12 мес', 'Выручка за 12 мес', 'Сегмент'])
            for g in data['guests']:
                w.writerow([g['phone'], g['card_number'], g['name'],
                            g['recency_days'], g['frequency'], g['monetary'],
                            g['segment']])
            out = buf.getvalue().encode('utf-8-sig')  # BOM для Excel
            return Response(out, mimetype='text/csv; charset=utf-8', headers={
                'Content-Disposition':
                    f"attachment; filename=rfm_{meta['asof']}.csv"})
        return jsonify({'meta': meta, 'data': data})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/ltv')
def api_ltv():
    """LTV: средний, YTD, по точкам (ТЗ §8)."""
    try:
        store, period, meta = _ctx()
        return jsonify({'meta': meta, 'data': ga.ltv(store, period, meta)})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/products')
def api_products():
    """Анализ покупок (ТЗ §9). ?mode=top|first|repeat|trend"""
    try:
        mode = request.args.get('mode', 'top')
        if mode not in ('top', 'first', 'repeat', 'trend'):
            mode = 'top'
        store, period, meta = _ctx()
        data = cached_olap(_cache_key('products', meta, mode),
                           lambda: ga.products(store, period, meta, mode))
        return jsonify({'meta': meta, 'data': data})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/product-pairs')
def api_product_pairs():
    """Сочетаемость товаров (ТЗ §10). ?scope=lifetime|period"""
    try:
        scope = request.args.get('scope', 'lifetime')
        if scope not in ('lifetime', 'period'):
            scope = 'lifetime'
        store, period, meta = _ctx()
        data = cached_olap(_cache_key('pairs', meta, scope),
                           lambda: ga.product_pairs(store, period, meta, scope))
        return jsonify({'meta': meta, 'data': data})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/venues')
def api_venues():
    """Аналитика по точкам (ТЗ §11)."""
    try:
        store, period, meta = _ctx()
        data = cached_olap(_cache_key('venues', meta),
                           lambda: ga.venues_analytics(store, period, meta))
        return jsonify({'meta': meta, 'data': data})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/search')
def api_search():
    """Поиск гостя по телефону/карте/имени (ТЗ §12). ?q="""
    try:
        q = (request.args.get('q') or '').strip()
        if len(q) < 2:
            return jsonify({'guests': []})
        return jsonify({'guests': ga.search_guests(get_store(), q)})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


@guests_bp.route('/api/guests/guest/<guest_id>')
def api_guest_card(guest_id):
    """Карточка гостя (ТЗ §12)."""
    try:
        store, period, meta = _ctx()
        data = ga.guest_card(store, guest_id, period, meta)
        if data is None:
            return jsonify({'error': 'Гость не найден'}), 404
        return jsonify({'meta': meta, 'data': data})
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500


# ------------------------------------------------------------------ сервис

@guests_bp.route('/api/guests/sync', methods=['POST'])
@admin_required
def api_guests_sync():
    """Ручной запуск синхронизации витрины (админ).

    ?force=1 — пересинк и замороженных месяцев (полная перезаливка истории).
    Прогон идёт в фоне; прогресс — GET /api/guests/sync-status.
    """
    force = request.args.get('force') == '1'
    started = guest_sync.start_background_sync(force=force, tag='manual')
    if not started:
        return jsonify({'started': False, 'error': 'Синхронизация уже идёт',
                        'progress': guest_sync.get_sync_progress()}), 409
    return jsonify({'started': True, 'progress': guest_sync.get_sync_progress()})


@guests_bp.route('/api/guests/sync-status')
def api_guests_sync_status():
    """Состояние витрины: прогресс текущего прогона, покрытие, месяцы."""
    store = get_store()
    return jsonify({
        'progress': guest_sync.get_sync_progress(),
        'coverage': store.coverage(),
        'months': store.sync_state_map(),
    })
