"""iiko Parameter Explorer - конструктор сводных отчётов из OLAP-данных.

Универсальная агрегация сырых OLAP-записей по выбранным:
- метрика (revenue в MVP, задел на qty/cost/margin/checks),
- измерение (top_category / third_parent / dish_name),
- гранулярность времени (day / week / month),
- фильтр верхней категории (kitchen / draft / bottled / all).

Логика читает строки из get_all_sales_report (кэш в DASHBOARD_OLAP_CACHE,
namespaced ключом explorer_*), затем pandas-агрегирует и возвращает
плоскую структуру pivot для рендера на фронте.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from core.olap_reports import OlapReports
from core.venues_config import KEY_TO_IIKO_NAME
from extensions import DASHBOARD_OLAP_CACHE, DASHBOARD_OLAP_CACHE_TTL


DRAFT_TOP = 'Напитки Розлив'
BOTTLED_TOP = 'Напитки Фасовка'

TOP_CATEGORY_FILTERS = {'kitchen', 'draft', 'bottled'}
GROUP_BY_FIELD = {
    'top_category': 'DishGroup.TopParent',
    'second_parent': 'DishGroup.SecondParent',
    'third_parent': 'DishGroup.ThirdParent',
    'dish_name': 'DishName',
}
GRANULARITIES = {'day', 'week', 'month'}
MAX_COLUMNS = 50  # сверх 50 - сворачиваем в "Прочее"

RU_MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн',
             'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']


def _fetch_raw_sales(venue_key: str, date_from: str, date_to: str) -> dict | None:
    """Получить сырые OLAP-данные за период с кэшированием.

    iiko API трактует date_to как exclusive end - чтобы получить включительно
    последний день, добавляем +1 к date_to при запросе.
    Ключ кэша имеет префикс explorer_ чтобы не конфликтовать с дашбордом,
    который может класть туда отфильтрованные ответы.
    """
    date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
    date_to_inclusive = (date_to_obj + timedelta(days=1)).strftime('%Y-%m-%d')

    cache_key = f"explorer_{venue_key}_{date_from}_{date_to_inclusive}"
    now = time.time()

    if cache_key in DASHBOARD_OLAP_CACHE:
        entry = DASHBOARD_OLAP_CACHE[cache_key]
        age = now - entry['timestamp']
        if age < DASHBOARD_OLAP_CACHE_TTL:
            print(f"[EXPLORER] Cache hit ({int(age)}s old, key={cache_key})")
            return entry['data']
        del DASHBOARD_OLAP_CACHE[cache_key]

    bar_name = KEY_TO_IIKO_NAME.get(venue_key)  # None для 'all'

    olap = OlapReports()
    if not olap.connect():
        print("[EXPLORER] OLAP connect failed")
        return None
    try:
        # Свой OLAP-запрос с полной иерархией DishGroup (Top/Second/Third) —
        # стандартный get_all_sales_report() запрашивает только TopParent,
        # чего недостаточно для подкатегорийной группировки розлива.
        data = olap.get_explorer_sales(date_from, date_to_inclusive, bar_name)
    finally:
        olap.disconnect()

    if not data or not data.get('data'):
        return None

    DASHBOARD_OLAP_CACHE[cache_key] = {'data': data, 'timestamp': now}
    return data


def _apply_top_category_filter(df: pd.DataFrame, top_category: str | None) -> pd.DataFrame:
    """Фильтр по верхней категории. None/'' = без фильтра."""
    if not top_category:
        return df
    top = df.get('DishGroup.TopParent', pd.Series(dtype=str)).fillna('')
    if top_category == 'draft':
        return df[top == DRAFT_TOP]
    if top_category == 'bottled':
        return df[top == BOTTLED_TOP]
    if top_category == 'kitchen':
        return df[~top.isin([DRAFT_TOP, BOTTLED_TOP])]
    return df


def _bucket_series(dt_series: pd.Series, granularity: str) -> pd.Series:
    """Привести даты к строковому ключу бакета."""
    if granularity == 'day':
        return dt_series.dt.strftime('%Y-%m-%d')
    if granularity == 'week':
        # ISO week (та же конвенция, что в core/data_processor.py)
        iso = dt_series.dt.isocalendar()
        return iso['year'].astype(str) + '-W' + iso['week'].astype(str).str.zfill(2)
    if granularity == 'month':
        return dt_series.dt.strftime('%Y-%m')
    raise ValueError(f"Unknown granularity: {granularity}")


def _full_bucket_range(date_from: str, date_to: str, granularity: str) -> list[str]:
    """Полный диапазон бакетов для reindex (чтобы пустые периоды показывались как 0)."""
    start = datetime.strptime(date_from, '%Y-%m-%d')
    end = datetime.strptime(date_to, '%Y-%m-%d')
    buckets: list[str] = []
    seen: set[str] = set()

    if granularity == 'day':
        cur = start
        while cur <= end:
            buckets.append(cur.strftime('%Y-%m-%d'))
            cur += timedelta(days=1)
    elif granularity == 'week':
        cur = start
        while cur <= end:
            iso = cur.isocalendar()
            key = f"{iso.year}-W{iso.week:02d}"
            if key not in seen:
                buckets.append(key)
                seen.add(key)
            cur += timedelta(days=1)
    elif granularity == 'month':
        cur = start.replace(day=1)
        while cur <= end:
            key = cur.strftime('%Y-%m')
            if key not in seen:
                buckets.append(key)
                seen.add(key)
            # к 1-му числу следующего месяца
            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)
    return buckets


def _bucket_label(bucket: str, granularity: str) -> str:
    """Человекочитаемая подпись для UI (например, '01 май' вместо '2026-05-01')."""
    if granularity == 'day':
        try:
            d = datetime.strptime(bucket, '%Y-%m-%d')
            return f"{d.day:02d} {RU_MONTHS[d.month - 1]}"
        except ValueError:
            return bucket
    if granularity == 'week':
        # '2026-W19' -> 'W19 26'
        try:
            year, week = bucket.split('-W')
            return f"W{week} {year[-2:]}"
        except ValueError:
            return bucket
    if granularity == 'month':
        try:
            d = datetime.strptime(bucket, '%Y-%m')
            return f"{RU_MONTHS[d.month - 1]} {d.year}"
        except ValueError:
            return bucket
    return bucket


def build_pivot(
    venue: str,
    date_from: str,
    date_to: str,
    granularity: str,
    group_by: str,
    top_category: str | None = None,
    metric: str = 'revenue',
) -> dict[str, Any]:
    """Главная функция: вернуть готовую сводную таблицу для фронта.

    Структура ответа описана в .claude/docs/explorer.md.
    """
    if granularity not in GRANULARITIES:
        raise ValueError(f"granularity must be one of {GRANULARITIES}")
    if group_by not in GROUP_BY_FIELD:
        raise ValueError(f"group_by must be one of {list(GROUP_BY_FIELD)}")
    if top_category and top_category not in TOP_CATEGORY_FILTERS:
        raise ValueError(f"top_category must be one of {TOP_CATEGORY_FILTERS} or empty")
    if metric != 'revenue':
        # Контракт оставляет параметр для будущих метрик, но реализована только выручка
        raise NotImplementedError(f"metric '{metric}' not implemented yet (MVP supports revenue only)")

    raw = _fetch_raw_sales(venue, date_from, date_to)
    if not raw:
        return _empty_response(venue, date_from, date_to, granularity, group_by, top_category, metric)

    records = raw.get('data', [])
    if not records:
        return _empty_response(venue, date_from, date_to, granularity, group_by, top_category, metric)

    df = pd.DataFrame(records)

    # Числовые колонки могут прийти строками
    if 'DishDiscountSumInt' in df.columns:
        df['revenue'] = pd.to_numeric(df['DishDiscountSumInt'], errors='coerce').fillna(0.0)
    else:
        df['revenue'] = 0.0

    # Парсим дату
    if 'OpenDate.Typed' not in df.columns:
        return _empty_response(venue, date_from, date_to, granularity, group_by, top_category, metric)
    df['_dt'] = pd.to_datetime(df['OpenDate.Typed'], errors='coerce')
    df = df.dropna(subset=['_dt'])

    # Фильтр верхней категории
    df = _apply_top_category_filter(df, top_category)
    if df.empty:
        return _empty_response(venue, date_from, date_to, granularity, group_by, top_category, metric)

    # Бакет времени и колонка группировки
    df['_bucket'] = _bucket_series(df['_dt'], granularity)
    group_col = GROUP_BY_FIELD[group_by]
    if group_col not in df.columns:
        df[group_col] = '(нет данных)'
    df['_group'] = df[group_col].fillna('(нет данных)').astype(str).replace('', '(нет данных)')

    # Pivot: bucket × group → sum(revenue)
    pivot = df.groupby(['_bucket', '_group'])['revenue'].sum().unstack(fill_value=0.0)

    # Дозаполняем пропущенные бакеты по времени нулями
    full_buckets = _full_bucket_range(date_from, date_to, granularity)
    pivot = pivot.reindex(full_buckets, fill_value=0.0)

    # Сортируем колонки по убыванию суммы
    col_totals = pivot.sum(axis=0).sort_values(ascending=False)
    pivot = pivot[col_totals.index]

    # Топ-N + "Прочее"
    if len(pivot.columns) > MAX_COLUMNS:
        top_cols = list(pivot.columns[:MAX_COLUMNS])
        rest_cols = list(pivot.columns[MAX_COLUMNS:])
        pivot['Прочее'] = pivot[rest_cols].sum(axis=1)
        pivot = pivot[top_cols + ['Прочее']]
        col_totals = pivot.sum(axis=0).sort_values(ascending=False)
        pivot = pivot[col_totals.index]

    # Округляем до целых рублей
    pivot = pivot.round(0).astype('int64')

    columns = [str(c) for c in pivot.columns]
    column_totals = {str(c): int(pivot[c].sum()) for c in columns}
    grand_total = int(pivot.values.sum())

    rows = []
    for bucket in pivot.index:
        row_values = {str(c): int(pivot.loc[bucket, c]) for c in columns}
        row_total = sum(row_values.values())
        rows.append({
            'bucket': bucket,
            'label': _bucket_label(bucket, granularity),
            'values': row_values,
            'total': row_total,
        })

    return {
        'meta': {
            'date_from': date_from,
            'date_to': date_to,
            'venue': venue,
            'granularity': granularity,
            'group_by': group_by,
            'top_category': top_category or None,
            'metric': metric,
            'row_count': len(rows),
            'col_count': len(columns),
            'generated_at': datetime.now().isoformat(timespec='seconds'),
        },
        'columns': columns,
        'rows': rows,
        'column_totals': column_totals,
        'grand_total': grand_total,
    }


def _empty_response(venue, date_from, date_to, granularity, group_by, top_category, metric) -> dict[str, Any]:
    """Пустой ответ — нет данных за период / нет колонок после фильтра."""
    buckets = _full_bucket_range(date_from, date_to, granularity)
    rows = [{
        'bucket': b,
        'label': _bucket_label(b, granularity),
        'values': {},
        'total': 0,
    } for b in buckets]
    return {
        'meta': {
            'date_from': date_from,
            'date_to': date_to,
            'venue': venue,
            'granularity': granularity,
            'group_by': group_by,
            'top_category': top_category or None,
            'metric': metric,
            'row_count': len(rows),
            'col_count': 0,
            'generated_at': datetime.now().isoformat(timespec='seconds'),
        },
        'columns': [],
        'rows': rows,
        'column_totals': {},
        'grand_total': 0,
    }
