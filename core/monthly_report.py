"""
core/monthly_report.py — витрина данных для вкладки «Месячный отчёт».

АРХИТЕКТУРА: материализованное представление (ETL / витрина).
Исторические месячные агрегаты иммутабельны — закрытый месяц не меняется. Поэтому:

- ПРОСМОТР (serve_*): читает ТОЛЬКО с диска, без обращения к iiko -> мгновенно и не
  нагружает iiko (это устранило всплеск авторизаций, ронявший живой дашборд).
- ПЕРЕСЧЁТ (refresh_*): фоновый, по расписанию (core/monthly_report_scheduler.py).
  Считаются ТОЛЬКО завершённые месяцы (текущий неполный — не нужен). Закрытый месяц
  считается один раз и «замораживается» в кэше навсегда; только что закрывшийся месяц
  подхватывается следующим прогоном. При первом запуске — бэкфилл за N лет.

Обычный дашборд (/api/dashboard-analytics) НЕ затронут — он остаётся живым и онлайн.

Метрики переиспользуют существующие расчёты:
- DashboardMetrics.calculate_metrics() + local_import_revenue()/category_units()/
  revenue_card_split() (core/dashboard_analysis.py);
- DraftAnalysis.get_style_summary() (core/draft_analysis.py);
- OlapReports.get_new_guests_count()/get_rfm_report() (лояльность, ТОП-гости).
"""
import os
import json
import time
from datetime import datetime

import pandas as pd

from core.olap_reports import OlapReports
from core.dashboard_analysis import DashboardMetrics
from core.draft_analysis import DraftAnalysis
from core.venues_config import KEY_TO_IIKO_NAME, VENUE_KEYS_ORDERED
from core.storage_paths import RENDER_DISK_DIR, LOCAL_DATA_DIR
from core.json_store import atomic_write_json, file_lock


RU_MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн',
                   'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

DRAFT_TOP = 'Напитки Розлив'
BOTTLED_TOP = 'Напитки Фасовка'

# Сколько стилей пива показывать на графике литров (остальные -> "Прочее")
TOP_STYLES = 8

# Глубина предрасчёта: текущий год + 2 прошлых (поддерживает YoY-кнопки +N-1/+N-2)
BACKFILL_YEARS = 3

# Все заведения (включая сводное 'all'), чтобы любой выбор открывался мгновенно
PRECOMPUTE_VENUES = list(VENUE_KEYS_ORDERED)  # ['all','bolshoy','ligovskiy',...]

# Пауза между OLAP-запросами в режиме пересчёта — щадим iiko на бэкфилле
COMPUTE_THROTTLE_SEC = 0.3

# Ключи метрик основного (core) блока — из get_all_sales_report за один запрос/месяц
CORE_KEYS = [
    'revenue', 'revenue_draft', 'revenue_packaged', 'revenue_kitchen',
    'share_draft', 'share_packaged', 'share_kitchen',
    'markup_pct', 'markup_draft', 'markup_packaged', 'markup_kitchen',
    'margin', 'checks', 'avg_check', 'loyalty_writeoffs',
    'units_draft', 'units_packaged',
    'local_packaged', 'import_packaged', 'local_draft', 'import_draft',
]

LOYALTY_KEYS = ['new_guests', 'revenue_card', 'revenue_nocard']

META_KEY = '_refreshed_at'  # служебный ключ в кэш-файле (не месяц)


# --------------------------------------------------------------------------- #
# Границы месяца и его состояние
# --------------------------------------------------------------------------- #

def _month_bounds(year, month):
    """(date_from, date_to_exclusive) для месяца. to — exclusive (конвенция iiko OLAP)."""
    date_from = f"{year}-{month:02d}-01"
    if month == 12:
        date_to_excl = f"{year + 1}-01-01"
    else:
        date_to_excl = f"{year}-{month + 1:02d}-01"
    return date_from, date_to_excl


def _month_state(year, month, today):
    """'future' | 'current' | 'completed' относительно сегодняшней даты."""
    if year > today.year or (year == today.year and month > today.month):
        return 'future'
    if year == today.year and month == today.month:
        return 'current'
    return 'completed'


# --------------------------------------------------------------------------- #
# Дисковый кэш (витрина)
# --------------------------------------------------------------------------- #

def _cache_dir():
    """Каталог витрины: на проде — постоянный диск, в dev — repo data/."""
    base = RENDER_DISK_DIR if os.path.exists(RENDER_DISK_DIR) else LOCAL_DATA_DIR
    return os.path.join(base, 'monthly_cache')


def _cache_path(block, venue_key, year):
    return os.path.join(_cache_dir(), f"{block}__{venue_key}__{year}.json")


def _read_cache(block, venue_key, year):
    path = _cache_path(block, venue_key, year)
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[MONTHLY] Ne udalos prochitat kesh {path}: {e}")
    return {}


def _write_cache(block, venue_key, year, cache):
    path = _cache_path(block, venue_key, year)
    try:
        with file_lock(path + '.lock'):
            atomic_write_json(path, cache)
    except Exception as e:
        print(f"[MONTHLY] Ne udalos zapisat kesh {path}: {e}")


def _refreshed_at(block, venue_key, year):
    return _read_cache(block, venue_key, year).get(META_KEY)


# --------------------------------------------------------------------------- #
# Чтение месяцев года (serve = только диск; compute = пересчёт + запись)
# --------------------------------------------------------------------------- #

def _serve_months(block, venue_key, year, compute_fn):
    """SERVE: вернуть {str(month): slice} ТОЛЬКО из кэша. Без iiko.
    Отсутствующие месяцы -> пустой срез (compute_fn(None, ...))."""
    bar_name = KEY_TO_IIKO_NAME.get(venue_key)
    cache = _read_cache(block, venue_key, year)
    result = {}
    for month in range(1, 13):
        mk = str(month)
        result[mk] = cache.get(mk) if mk in cache else compute_fn(None, bar_name, year, month)
    return result


def _compute_months(block, venue_key, year, compute_fn, force=False):
    """COMPUTE: пересчитать и записать на диск (режим шедулера/бэкфилла).

    Считаются ТОЛЬКО завершённые месяцы. Текущий (неполный) и будущие месяцы не
    считаются и не кэшируются — отчёт строится по закрытым месяцам. Когда месяц
    закроется, он будет посчитан следующим прогоном (его ещё нет в кэше).

    - future / current -> пропускаем (не считаем, не пишем);
    - completed + уже в кэше + не force -> заморожено, пропускаем;
    - completed (нет в кэше) или force -> считаем через OLAP и пишем (заморозка).
    """
    bar_name = KEY_TO_IIKO_NAME.get(venue_key)
    today = datetime.now().date()
    cache = _read_cache(block, venue_key, year)
    dirty = False
    olap = None
    connect_failed = False

    try:
        for month in range(1, 13):
            mk = str(month)
            state = _month_state(year, month, today)

            if state in ('future', 'current'):
                continue
            if state == 'completed' and not force and mk in cache:
                continue

            if olap is None and not connect_failed:
                olap = OlapReports()
                if not olap.connect():
                    print(f"[MONTHLY] OLAP connect failed ({block}/{venue_key}/{year})")
                    connect_failed = True
                    olap = None
            if olap is None:
                continue  # оставляем что было в кэше

            cache[mk] = compute_fn(olap, bar_name, year, month)
            dirty = True
            time.sleep(COMPUTE_THROTTLE_SEC)
    finally:
        if olap is not None:
            olap.disconnect()

    if dirty:
        cache[META_KEY] = datetime.now().isoformat(timespec='seconds')
        _write_cache(block, venue_key, year, cache)
    return dirty


# --------------------------------------------------------------------------- #
# Расчёт одного месяца по блокам
# --------------------------------------------------------------------------- #

def _compute_core(olap, bar_name, year, month):
    """Метрики core-блока за месяц (один OLAP-запрос get_all_sales_report)."""
    if olap is None:
        return {k: 0 for k in CORE_KEYS}

    date_from, date_to_excl = _month_bounds(year, month)
    data = olap.get_all_sales_report(date_from, date_to_excl, bar_name)
    if not data or not data.get('data'):
        return {k: 0 for k in CORE_KEYS}

    dm = DashboardMetrics()
    m = dm.calculate_metrics(data)
    records = data['data']

    pkg = dm.local_import_revenue(records, BOTTLED_TOP)
    drf = dm.local_import_revenue(records, DRAFT_TOP)

    return {
        'revenue': m['total_revenue'],
        'revenue_draft': m['draft_revenue'],
        'revenue_packaged': m['bottles_revenue'],
        'revenue_kitchen': m['kitchen_revenue'],
        'share_draft': m['draft_share'],
        'share_packaged': m['bottles_share'],
        'share_kitchen': m['kitchen_share'],
        # Наценка в calculate_metrics — дробь (1.95); ×100 для процентов (как на дашборде)
        'markup_pct': round(m['avg_markup'] * 100, 2),
        'markup_draft': round(m['draft_markup'] * 100, 2),
        'markup_packaged': round(m['bottles_markup'] * 100, 2),
        'markup_kitchen': round(m['kitchen_markup'] * 100, 2),
        'margin': m['total_margin'],
        'checks': m['total_checks'],
        'avg_check': m['avg_check'],
        'loyalty_writeoffs': m['loyalty_points_written_off'],
        'units_draft': dm.category_units(records, DRAFT_TOP),
        'units_packaged': dm.category_units(records, BOTTLED_TOP),
        'local_packaged': pkg['local'],
        'import_packaged': pkg['import'],
        'local_draft': drf['local'],
        'import_draft': drf['import'],
    }


def _compute_loyalty(olap, bar_name, year, month):
    """Лояльность за месяц: новые гости + выручка по картам/без (2 OLAP-запроса)."""
    if olap is None:
        return {k: 0 for k in LOYALTY_KEYS}

    date_from, date_to_excl = _month_bounds(year, month)

    new_guests = olap.get_new_guests_count(date_from, date_to_excl, bar_name)

    rfm = olap.get_rfm_report(date_from, date_to_excl, bar_name)
    rows = (rfm or {}).get('data', [])
    split = DashboardMetrics().revenue_card_split(rows) if rows else {'card': 0, 'nocard': 0}

    return {
        'new_guests': new_guests,
        'revenue_card': split['card'],
        'revenue_nocard': split['nocard'],
    }


def _compute_liters(olap, bar_name, year, month):
    """Литры розлива по стилям за месяц: {style: liters} (1 OLAP-запрос)."""
    if olap is None:
        return {}

    date_from, date_to_excl = _month_bounds(year, month)
    data = olap.get_draft_sales_report(date_from, date_to_excl, bar_name)
    if not data or not data.get('data'):
        return {}

    frame = pd.DataFrame(data['data'])
    if 'DishAmountInt' in frame.columns:
        frame['DishAmountInt'] = pd.to_numeric(frame['DishAmountInt'], errors='coerce').fillna(0)

    analysis = DraftAnalysis(frame)
    # bar_name=None: отчёт уже отфильтрован по бару на уровне OLAP-запроса
    summary = analysis.get_style_summary(bar_name=None)
    return {str(row['Style']): float(row['TotalLiters']) for _, row in summary.iterrows()}


def _compute_topguests(olap, bar_name, year, month, limit=5):
    """ТОП гостей по тратам за месяц: [{name, card, visits, spend}] (1 OLAP-запрос).
    Гость идентифицируется картой лояльности; без карты — исключается.

    Визит = уникальная ДАТА (OpenDate.Typed), как в каноничном RFM-разделе скидок
    (routes/analysis.py: total_visits = len(visit_dates)). НЕ число заказов: гость с
    двумя заказами за один день — это один визит. RFM-отчёт сгруппирован по OrderNum,
    поэтому в один день у гостя может быть несколько строк, но дата одна.
    """
    if olap is None:
        return []

    date_from, date_to_excl = _month_bounds(year, month)
    rfm = olap.get_rfm_report(date_from, date_to_excl, bar_name)
    rows = (rfm or {}).get('data', [])

    guests = {}
    for row in rows:
        card = (row.get('Delivery.CustomerCardNumber') or '').strip()
        if not card:
            continue
        name = (row.get('Delivery.CustomerName') or '').strip()
        visit_date = row.get('OpenDate.Typed', '')
        revenue = float(row.get('DishDiscountSumInt', 0) or 0)

        g = guests.setdefault(card, {'card': card, 'name': name, 'dates': set(), 'spend': 0.0})
        if visit_date:
            g['dates'].add(visit_date)
        if name and not g['name']:
            g['name'] = name
        g['spend'] += revenue

    ranked = sorted(guests.values(), key=lambda x: x['spend'], reverse=True)[:limit]
    return [
        {'card': g['card'], 'name': g['name'] or 'Без имени',
         'visits': len(g['dates']), 'spend': round(g['spend'], 2)}
        for g in ranked
    ]


# Реестр блоков: имя -> функция расчёта месяца
_BLOCKS = {
    'core': _compute_core,
    'loyalty': _compute_loyalty,
    'liters': _compute_liters,
    'topguests': _compute_topguests,
}


# --------------------------------------------------------------------------- #
# SERVE — сборка ответов для фронтенда (только диск)
# --------------------------------------------------------------------------- #

def _to_series(months, keys):
    """{str(month): slice} -> {labels:[12], <key>:[12]}."""
    series = {'labels': list(RU_MONTHS_SHORT)}
    for k in keys:
        series[k] = [round(float((months.get(str(m)) or {}).get(k, 0) or 0), 2)
                     for m in range(1, 13)]
    return series


def get_core(venue_key, years):
    """Core-блок помесячно за указанные годы (YoY). Только из витрины."""
    data = {}
    for year in years:
        months = _serve_months('core', venue_key, year, _compute_core)
        data[str(year)] = _to_series(months, CORE_KEYS)
    primary = years[0] if years else datetime.now().year
    return {
        'venue': venue_key,
        'years': years,
        'months': list(RU_MONTHS_SHORT),
        'data': data,
        'refreshed_at': _refreshed_at('core', venue_key, primary),
    }


def get_loyalty(venue_key, year):
    """Лояльность помесячно за один год. Только из витрины."""
    months = _serve_months('loyalty', venue_key, year, _compute_loyalty)
    return {
        'venue': venue_key,
        'year': year,
        'data': _to_series(months, LOYALTY_KEYS),
        'refreshed_at': _refreshed_at('loyalty', venue_key, year),
    }


def get_draft_liters(venue_key, year):
    """Литры розлива по стилям помесячно за год (top-N + 'Прочее'). Только из витрины."""
    months = _serve_months('liters', venue_key, year, _compute_liters)

    totals = {}
    for m in range(1, 13):
        for style, liters in (months.get(str(m)) or {}).items():
            totals[style] = totals.get(style, 0.0) + liters

    ordered = sorted(totals, key=lambda s: totals[s], reverse=True)
    top = ordered[:TOP_STYLES]
    rest = ordered[TOP_STYLES:]

    series = {}
    for style in top:
        series[style] = [round((months.get(str(m)) or {}).get(style, 0.0), 1)
                         for m in range(1, 13)]
    if rest:
        series['Прочее'] = [round(sum((months.get(str(m)) or {}).get(s, 0.0) for s in rest), 1)
                            for m in range(1, 13)]

    return {
        'venue': venue_key,
        'year': year,
        'labels': list(RU_MONTHS_SHORT),
        'styles': list(series.keys()),
        'series': series,
        'refreshed_at': _refreshed_at('liters', venue_key, year),
    }


def get_top_guests(venue_key, year, month):
    """ТОП гостей за конкретный месяц. Только из витрины."""
    cache = _read_cache('topguests', venue_key, year)
    guests = cache.get(str(month), [])
    return {
        'venue': venue_key,
        'year': year,
        'month': month,
        'guests': guests,
        'refreshed_at': cache.get(META_KEY),
    }


# --------------------------------------------------------------------------- #
# REFRESH — пересчёт витрины (шедулер / бэкфилл / ручная кнопка)
# --------------------------------------------------------------------------- #

def refresh_block(block, venue_key, year, force=False):
    """Пересчитать один блок за год и записать в витрину."""
    compute_fn = _BLOCKS[block]
    return _compute_months(block, venue_key, year, compute_fn, force=force)


def refresh_year(venue_key, year, force=False):
    """Пересчитать все блоки за год (current месяц обновится, closed — заморозятся)."""
    changed = False
    for block in _BLOCKS:
        try:
            if refresh_block(block, venue_key, year, force=force):
                changed = True
        except Exception as e:
            print(f"[MONTHLY] refresh {block}/{venue_key}/{year} oshibka: {e}")
    return changed


def refresh_all(venues=None, years=None, force=False):
    """Пересчёт витрины для всех заведений и годов глубины (шедулер/бэкфилл).

    Считаются только завершённые месяцы (закрытые — один раз, заморожены; текущий
    неполный не считается). Возвращает кол-во (venue, year), где что-то пересчиталось.
    """
    venues = venues or PRECOMPUTE_VENUES
    if years is None:
        cur = datetime.now().year
        years = [cur - i for i in range(BACKFILL_YEARS)]

    print(f"[MONTHLY] refresh_all: venues={venues} years={years} force={force}")
    changed = 0
    for venue_key in venues:
        for year in years:
            if refresh_year(venue_key, year, force=force):
                changed += 1
    print(f"[MONTHLY] refresh_all gotovo: izmeneno {changed} (venue,year)")
    return changed
