"""
Разбивка двух сортов розлива ПО КАЖДОЙ ТОЧКЕ + детект даты постановки на кран.

Часть 1: полная таблица метрик по каждому бару (период YTD-2026, из кэша compare).
Часть 2: дата постановки на кран — по OLAP-первой-продаже и «заходам» (стинтам)
         по широкому окну (с 2025-01-01), т.к. журнал кранов demo-уровневый.

Запуск: py -3 scripts/beer_breakdown.py
"""
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from datetime import datetime, timedelta
from core.olap_reports import OlapReports
from core.draft_analysis import DraftAnalysis

CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'cache')
CACHE_2026 = os.path.join(CACHE_DIR, 'draft_cmp_ytd2026_raw.json')   # уже есть
CACHE_WIDE = os.path.join(CACHE_DIR, 'draft_wide_2025plus_raw.json')

PERIOD_FW = ("2026-01-01", "2026-06-17")     # период для метрик по точкам
WIDE_FROM = "2025-01-01"                       # окно для поиска даты постановки
WIDE_TO = "2026-06-17"
GAP_DAYS = 14                                  # разрыв >= => новый заход на кран

BEERS = {
    "Блек Шип":      ["блек шип", "блэк шип", "black sheep"],
    "Brewlok Stout": ["brewlok stout", "брюлок стаут"],
}

pd.set_option('display.width', 240)
pd.set_option('display.max_colwidth', 40)
pd.set_option('display.max_rows', 200)


def pull(date_from, date_to_incl, cache):
    if os.path.exists(cache):
        with open(cache, encoding='utf-8') as f:
            return json.load(f)
    olap_to = (datetime.strptime(date_to_incl, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"[api] {date_from}..{date_to_incl}")
    olap = OlapReports()
    if not olap.connect():
        print("Не подключиться"); sys.exit(1)
    try:
        raw = olap.get_draft_sales_report(date_from, olap_to)
    finally:
        olap.disconnect()
    if not raw or not raw.get('data'):
        print("Пусто"); sys.exit(1)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, 'w', encoding='utf-8') as f:
        json.dump(raw, f, ensure_ascii=False)
    print(f"[saved] {cache} rows={len(raw['data'])}")
    return raw


def prep(raw):
    df = pd.DataFrame(raw['data'])
    for c in ['DishAmountInt', 'DishDiscountSumInt', 'ProductCostBase.ProductCost',
              'UniqOrderId.OrdersCount']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    p = DraftAnalysis(df.copy()).prepare_draft_data()
    return p


def match(p, frags):
    return p[p['BeerNameNorm'].apply(lambda s: any(fr in str(s) for fr in frags))]


# ---------- ЧАСТЬ 1: метрики по точкам (YTD-2026) ----------
def part1(p):
    has_checks = 'UniqOrderId.OrdersCount' in p.columns
    store_total_l = p.groupby('Store.Name')['VolumeInLiters'].sum()
    print("\n" + "=" * 72)
    print(f"ЧАСТЬ 1. МЕТРИКИ ПО КАЖДОЙ ТОЧКЕ  (период {PERIOD_FW[0]}..{PERIOD_FW[1]})")
    print("=" * 72)
    for label, frags in BEERS.items():
        sub = match(p, frags)
        print(f"\n### {label}")
        if sub.empty:
            print("  нет данных"); continue
        rows = []
        for bar in sorted(sub['Store.Name'].dropna().unique()):
            g = sub[sub['Store.Name'] == bar]
            liters = g['VolumeInLiters'].sum()
            rev = g['DishDiscountSumInt'].sum()
            cost = g['ProductCostBase.ProductCost'].sum()
            margin = rev - cost
            checks = g['UniqOrderId.OrdersCount'].sum() if has_checks else 0
            weeks = g['Week'].nunique()
            stl = store_total_l.get(bar, 0)
            rows.append({
                'Точка': bar,
                'Литры': round(liters, 1),
                'Доля розлива ТТ %': round(liters / stl * 100, 2) if stl else 0,
                'Порции': int(g['DishAmountInt'].sum()),
                'Выручка': round(rev),
                'Цена/л': round(rev / liters) if liters else 0,
                'Себест/л': round(cost / liters) if liters else 0,
                'Маржа (вклад)': round(margin),
                'Маржа/л': round(margin / liters) if liters else 0,
                'Наценка%': round(margin / cost * 100) if cost else 0,
                'Чеки': int(checks),
                'Л/чек': round(liters / checks, 2) if checks else 0,
                'Недель': weeks,
                'Кег~30л': round(liters / 30, 1),
            })
        # строка ИТОГО
        liters = sub['VolumeInLiters'].sum(); rev = sub['DishDiscountSumInt'].sum()
        cost = sub['ProductCostBase.ProductCost'].sum(); margin = rev - cost
        checks = sub['UniqOrderId.OrdersCount'].sum() if has_checks else 0
        rows.append({
            'Точка': 'ИТОГО (сеть)', 'Литры': round(liters, 1),
            'Доля розлива ТТ %': '-', 'Порции': int(sub['DishAmountInt'].sum()),
            'Выручка': round(rev), 'Цена/л': round(rev / liters) if liters else 0,
            'Себест/л': round(cost / liters) if liters else 0, 'Маржа (вклад)': round(margin),
            'Маржа/л': round(margin / liters) if liters else 0,
            'Наценка%': round(margin / cost * 100) if cost else 0,
            'Чеки': int(checks), 'Л/чек': round(liters / checks, 2) if checks else 0,
            'Недель': sub['Week'].nunique(), 'Кег~30л': round(liters / 30, 1),
        })
        print(pd.DataFrame(rows).to_string(index=False))


# ---------- ЧАСТЬ 2: дата постановки на кран ----------
def part2(pw):
    print("\n" + "=" * 72)
    print(f"ЧАСТЬ 2. ДАТА ПОСТАНОВКИ НА КРАН  (окно OLAP {WIDE_FROM}..{WIDE_TO}, разрыв>={GAP_DAYS}д = новый заход)")
    print("журнал кранов demo-уровневый -> только первая продажа из OLAP (нижняя оценка)")
    print("=" * 72)
    date_col = 'OpenDate.Typed' if 'OpenDate.Typed' in pw.columns else 'OpenDate'
    pw = pw.copy()
    pw['_d'] = pd.to_datetime(pw[date_col]).dt.normalize()
    win_start = pd.Timestamp(WIDE_FROM)
    for label, frags in BEERS.items():
        sub = match(pw, frags)
        print(f"\n### {label}")
        if sub.empty:
            print("  нет данных в окне"); continue
        gmin = sub['_d'].min()
        capped = " (= начало окна; на кране был ещё раньше, до 2025)" if gmin == win_start else ""
        print(f"  Первая продажа в сети: {gmin.date()}{capped}")
        rows = []
        for bar in sorted(sub['Store.Name'].dropna().unique()):
            g = sub[sub['Store.Name'] == bar].sort_values('_d')
            days = g.groupby('_d')['VolumeInLiters'].sum()
            dates = list(days.index)
            # разбиваем на стинты по разрыву
            stints = []
            start = prev = dates[0]
            acc = days.loc[dates[0]]
            for d in dates[1:]:
                if (d - prev).days >= GAP_DAYS:
                    stints.append((start, prev, acc))
                    start = d; acc = 0.0
                acc += days.loc[d]
                prev = d
            stints.append((start, prev, acc))
            for i, (s, e, lit) in enumerate(stints, 1):
                first_cap = " (раньше окна)" if s == win_start and i == 1 else ""
                rows.append({
                    'Точка': bar,
                    'Заход №': i,
                    'Поставлен (1-я прод.)': f"{s.date()}{first_cap}",
                    'Последняя прод.': str(e.date()),
                    'Дней на кране': (e - s).days + 1,
                    'Литры за заход': round(lit, 1),
                })
        print(pd.DataFrame(rows).to_string(index=False))


def main():
    p26 = prep(pull(*PERIOD_FW, CACHE_2026))
    part1(p26)
    pw = prep(pull(WIDE_FROM, WIDE_TO, CACHE_WIDE))
    part2(pw)


if __name__ == '__main__':
    main()
