"""
Сравнение двух сортов разливного по фреймворку владельца.
Тянет розлив за период (с кэшем сырого ответа), находит сорта по фрагментам имени,
считает: литры, выручка, себестоимость, маржа, наценка, цена/литр, маржа/литр,
доля в розливе (литры и выручка), чеки, недельная динамика, оценка кег.

Запуск:  py -3 scripts/compare_two_beers.py
Период и фрагменты имён — константы ниже.
"""
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from datetime import datetime, timedelta
from core.olap_reports import OlapReports
from core.draft_analysis import DraftAnalysis

# --- Параметры ---
DATE_FROM = "2026-01-01"
DATE_TO = "2026-06-17"          # включительно (UI)
CACHE = os.path.join(os.path.dirname(__file__), '..', 'data', 'cache', 'draft_cmp_ytd2026_raw.json')

# Фрагменты имени (lowercase, substring по BeerNameNorm). Несколько вариантов написания.
BEERS = {
    "Блек Шип":      ["блек шип", "блэк шип", "black sheep", "блек-шип"],
    "Brewlok Stout": ["brewlok stout", "брюлок стаут", "брюлок стаут"],
}

pd.set_option('display.width', 220)
pd.set_option('display.max_colwidth', 40)
pd.set_option('display.max_rows', 120)


def load_raw():
    olap_to = (datetime.strptime(DATE_TO, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    if os.path.exists(CACHE):
        print(f"[cache] {CACHE}")
        with open(CACHE, encoding='utf-8') as f:
            return json.load(f)
    print(f"[api] тяну розлив {DATE_FROM}..{DATE_TO} (olap to={olap_to})")
    olap = OlapReports()
    if not olap.connect():
        print("Не удалось подключиться к iiko API")
        sys.exit(1)
    try:
        raw = olap.get_draft_sales_report(DATE_FROM, olap_to)
    finally:
        olap.disconnect()
    if not raw or not raw.get('data'):
        print("Пустой ответ OLAP")
        sys.exit(1)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, 'w', encoding='utf-8') as f:
        json.dump(raw, f, ensure_ascii=False)
    print(f"[saved] {CACHE}  rows={len(raw['data'])}")
    return raw


def main():
    raw = load_raw()
    df = pd.DataFrame(raw['data'])
    print("\n=== COLUMNS ===")
    print(list(df.columns))

    # числовые
    for c in ['DishAmountInt', 'DishDiscountSumInt', 'ProductCostBase.ProductCost',
              'ProductCostBase.MarkUp', 'UniqOrderId.OrdersCount']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

    da = DraftAnalysis(df.copy())
    prep = da.prepare_draft_data()   # добавит BeerName, BeerNameNorm, PortionVolume, VolumeInLiters, Week
    prep['Margin'] = prep.get('DishDiscountSumInt', 0) - prep.get('ProductCostBase.ProductCost', 0)

    # знаменатели для доли (весь розлив за период, все бары)
    TOTAL_L = prep['VolumeInLiters'].sum()
    TOTAL_R = prep['DishDiscountSumInt'].sum() if 'DishDiscountSumInt' in prep else 0
    print(f"\n=== РОЗЛИВ ИТОГО за период: {TOTAL_L:,.0f} л, выручка {TOTAL_R:,.0f} р ===")

    # топ сортов — чтобы увидеть точные имена
    top = (prep.groupby('BeerNameNorm')
              .agg(L=('VolumeInLiters', 'sum'), R=('DishDiscountSumInt', 'sum'),
                   name=('BeerNameOriginal', 'first'))
              .sort_values('L', ascending=False).reset_index())
    print("\n=== ТОП-30 сортов по литрам (для сверки имён) ===")
    print(top.head(30).to_string(index=False))

    has_checks = 'UniqOrderId.OrdersCount' in prep.columns

    def agg_beer(mask_df):
        g = mask_df
        liters = g['VolumeInLiters'].sum()
        portions = g['DishAmountInt'].sum()
        revenue = g['DishDiscountSumInt'].sum() if 'DishDiscountSumInt' in g else 0
        cost = g['ProductCostBase.ProductCost'].sum() if 'ProductCostBase.ProductCost' in g else 0
        margin = revenue - cost
        weeks = g['Week'].nunique()
        checks = g['UniqOrderId.OrdersCount'].sum() if has_checks else None
        portion_sizes = sorted(g['PortionVolume'].dropna().unique().tolist())
        names = sorted(g['BeerNameOriginal'].dropna().unique().tolist())
        return {
            'liters': liters, 'portions': portions, 'revenue': revenue, 'cost': cost,
            'margin': margin, 'weeks': weeks, 'checks': checks,
            'price_l': revenue / liters if liters else 0,
            'margin_l': margin / liters if liters else 0,
            'markup_pct': (margin / cost * 100) if cost else 0,
            'share_l': liters / TOTAL_L * 100 if TOTAL_L else 0,
            'share_r': revenue / TOTAL_R * 100 if TOTAL_R else 0,
            'avg_l_week': liters / weeks if weeks else 0,
            'kegs30': liters / 30, 'kegs50': liters / 50,
            'portion_sizes': portion_sizes, 'names': names,
            'liters_per_check': liters / checks if (checks and checks > 0) else None,
        }

    results = {}
    for label, frags in BEERS.items():
        mask = prep['BeerNameNorm'].apply(lambda s: any(fr in str(s) for fr in frags))
        sub = prep[mask]
        if sub.empty:
            print(f"\n!!! '{label}': НЕ найдено по фрагментам {frags}")
            results[label] = None
            continue
        results[label] = agg_beer(sub)
        results[label]['_per_bar'] = {
            bar: agg_beer(sub[sub['Store.Name'] == bar])
            for bar in sorted(sub['Store.Name'].dropna().unique())
        }
        # недельная динамика (литры)
        wk = (sub.groupby('Week').agg(L=('VolumeInLiters', 'sum')).reset_index())
        wk['Week'] = wk['Week'].astype(str)
        results[label]['_weekly'] = wk

    # --- ВЫВОД ---
    print("\n" + "=" * 70)
    print("СРАВНЕНИЕ ДВУХ СОРТОВ (все 4 бара, период {}..{})".format(DATE_FROM, DATE_TO))
    print("=" * 70)
    rows = []
    for label in BEERS:
        r = results.get(label)
        if not r:
            rows.append({'Метрика': label, 'значение': 'НЕ НАЙДЕНО'})
            continue
        rows.append({'Сорт': label,
                     'Имена в iiko': " | ".join(r['names'])[:80],
                     'Размеры порций (л)': r['portion_sizes'],
                     'Литры': round(r['liters'], 1),
                     'Порции': int(r['portions']),
                     'Доля в розливе, литры %': round(r['share_l'], 2),
                     'Выручка р': round(r['revenue']),
                     'Доля в розливе, выручка %': round(r['share_r'], 2),
                     'Цена/литр р': round(r['price_l']),
                     'Себестоимость р': round(r['cost']),
                     'Маржа р (вклад)': round(r['margin']),
                     'Маржа/литр р': round(r['margin_l']),
                     'Наценка %': round(r['markup_pct']),
                     'Недель с продажами': r['weeks'],
                     'Сред. литров/неделю': round(r['avg_l_week'], 1),
                     'Чеки (где сорт был)': int(r['checks']) if r['checks'] is not None else 'н/д',
                     'Литры/чек': round(r['liters_per_check'], 3) if r['liters_per_check'] else 'н/д',
                     'Оценка кег 30л': round(r['kegs30'], 1),
                     'Оценка кег 50л': round(r['kegs50'], 1)})
    cmp_df = pd.DataFrame(rows)
    print(cmp_df.to_string(index=False))

    # по барам
    for label in BEERS:
        r = results.get(label)
        if not r:
            continue
        print(f"\n--- {label}: по барам ---")
        br = []
        for bar, rr in r['_per_bar'].items():
            br.append({'Бар': bar, 'Литры': round(rr['liters'], 1),
                       'Выручка': round(rr['revenue']), 'Маржа': round(rr['margin']),
                       'Цена/л': round(rr['price_l']), 'Маржа/л': round(rr['margin_l']),
                       'Наценка%': round(rr['markup_pct'])})
        print(pd.DataFrame(br).to_string(index=False))

    # недельная динамика рядом
    print("\n--- Недельная динамика (литры) ---")
    wk_all = None
    for label in BEERS:
        r = results.get(label)
        if not r:
            continue
        w = r['_weekly'].rename(columns={'L': label})
        wk_all = w if wk_all is None else wk_all.merge(w, on='Week', how='outer')
    if wk_all is not None:
        wk_all = wk_all.sort_values('Week').fillna(0)
        for c in BEERS:
            if c in wk_all:
                wk_all[c] = wk_all[c].round(1)
        print(wk_all.to_string(index=False))

    # CSV
    out = os.path.join(os.path.dirname(__file__), '..', 'data', 'compare_two_beers.csv')
    cmp_df.to_csv(out, index=False, encoding='utf-8-sig', sep=';')
    print(f"\n[csv] {out}")


if __name__ == '__main__':
    main()
