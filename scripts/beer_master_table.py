"""
Единая сводная таблица по двум сортам розлива: все найденные данные.
Метрики продаж — YTD 2026 (из кэша). История кранов — с 2025 (из кэша).
Источник API не дёргается (только кэши).

Запуск: py -3 scripts/beer_master_table.py
"""
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from core.draft_analysis import DraftAnalysis

CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'cache')
CACHE_2026 = os.path.join(CACHE_DIR, 'draft_cmp_ytd2026_raw.json')
CACHE_WIDE = os.path.join(CACHE_DIR, 'draft_wide_2025plus_raw.json')
GAP_DAYS = 14

BEERS = {
    "Блек Шип":      ["блек шип", "блэк шип", "black sheep"],
    "Brewlok Stout": ["brewlok stout", "брюлок стаут"],
}

pd.set_option('display.width', 300)
pd.set_option('display.max_colwidth', 30)
pd.set_option('display.max_rows', 200)


def prep(path):
    raw = json.load(open(path, encoding='utf-8'))
    df = pd.DataFrame(raw['data'])
    for c in ['DishAmountInt', 'DishDiscountSumInt', 'ProductCostBase.ProductCost',
              'UniqOrderId.OrdersCount']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    return DraftAnalysis(df.copy()).prepare_draft_data()


def match(p, frags):
    return p[p['BeerNameNorm'].apply(lambda s: any(fr in str(s) for fr in frags))]


def tap_history(sub_store):
    """Для строк одной точки одного сорта: (первая дата, число заходов, дней на кране, литры в окне)."""
    date_col = 'OpenDate.Typed' if 'OpenDate.Typed' in sub_store.columns else 'OpenDate'
    days = sub_store.assign(_d=pd.to_datetime(sub_store[date_col]).dt.normalize()) \
                    .groupby('_d')['VolumeInLiters'].sum().sort_index()
    dates = list(days.index)
    stints, start, prev = [], dates[0], dates[0]
    for d in dates[1:]:
        if (d - prev).days >= GAP_DAYS:
            stints.append((start, prev)); start = d
        prev = d
    stints.append((start, prev))
    total_days = sum((e - s).days + 1 for s, e in stints)
    return dates[0].date(), len(stints), total_days, days.sum()


def metrics(g, store_total_l):
    liters = g['VolumeInLiters'].sum()
    rev = g['DishDiscountSumInt'].sum()
    cost = g['ProductCostBase.ProductCost'].sum()
    margin = rev - cost
    checks = g['UniqOrderId.OrdersCount'].sum() if 'UniqOrderId.OrdersCount' in g else 0
    return {
        'Литры': round(liters, 1),
        'Доля ТТ %': round(liters / store_total_l * 100, 2) if store_total_l else None,
        'Порции': int(g['DishAmountInt'].sum()),
        'Выручка': round(rev),
        'Цена/л': round(rev / liters) if liters else 0,
        'Себест/л': round(cost / liters) if liters else 0,
        'Маржа (вклад)': round(margin),
        'Маржа/л': round(margin / liters) if liters else 0,
        'Наценка%': round(margin / cost * 100) if cost else 0,
        'Чеки': int(checks),
        'Л/чек': round(liters / checks, 2) if checks else 0,
        'Недель': g['Week'].nunique(),
    }


def main():
    p26 = prep(CACHE_2026)
    pw = prep(CACHE_WIDE)
    store_tot = p26.groupby('Store.Name')['VolumeInLiters'].sum()

    rows = []
    for label, frags in BEERS.items():
        sub26 = match(p26, frags)
        subw = match(pw, frags)
        stores = sorted(set(sub26['Store.Name'].dropna().unique()) |
                        set(subw['Store.Name'].dropna().unique()))
        for bar in stores:
            g26 = sub26[sub26['Store.Name'] == bar]
            gw = subw[subw['Store.Name'] == bar]
            m = metrics(g26, store_tot.get(bar, 0)) if not g26.empty else {}
            if not gw.empty:
                first, n_st, t_days, lit_w = tap_history(gw)
                hist = {'Поставлен': str(first), 'Заходов': n_st,
                        'Дней на кране (с 2025)': t_days,
                        'Л/день на кране': round(lit_w / t_days, 2) if t_days else 0}
            else:
                hist = {'Поставлен': '-', 'Заходов': 0, 'Дней на кране (с 2025)': 0, 'Л/день на кране': 0}
            rows.append({'Сорт': label, 'Точка': bar, **hist, **m})
        # сетевой итог
        m = metrics(sub26, None)
        m['Доля ТТ %'] = None
        # сетевая доля от всего розлива
        m['Доля сети %'] = round(sub26['VolumeInLiters'].sum() / p26['VolumeInLiters'].sum() * 100, 2)
        first = pd.to_datetime(subw['OpenDate.Typed']).min().date()
        rows.append({'Сорт': label, 'Точка': '== ИТОГО сеть ==',
                     'Поставлен': str(first), 'Заходов': '-',
                     'Дней на кране (с 2025)': '-', 'Л/день на кране': '-', **m})

    cols = ['Сорт', 'Точка', 'Поставлен', 'Заходов', 'Дней на кране (с 2025)', 'Л/день на кране',
            'Литры', 'Доля ТТ %', 'Доля сети %', 'Порции', 'Выручка', 'Цена/л', 'Себест/л',
            'Маржа (вклад)', 'Маржа/л', 'Наценка%', 'Чеки', 'Л/чек', 'Недель']
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]

    print("СВОДНАЯ ТАБЛИЦА (продажи=YTD2026 01.01-17.06; краны=с 2025-01-01)\n")
    print(df.to_string(index=False))

    out = os.path.join(os.path.dirname(__file__), '..', 'data', 'beer_master_table.csv')
    df.to_csv(out, index=False, encoding='utf-8-sig', sep=';')
    print(f"\n[csv] {out}")


if __name__ == '__main__':
    main()
