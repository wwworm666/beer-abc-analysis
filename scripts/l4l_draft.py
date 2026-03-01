"""
L4L (Like-for-Like) сравнение разливного пива: YTD 2025 vs YTD 2026
По каждому сорту, по каждому бару + итого
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from datetime import datetime, timedelta
from core.olap_reports import OlapReports
from core.draft_analysis import DraftAnalysis

BARS = [
    "Большой пр. В.О",
    "Лиговский",
    "Кременчугская",
    "Варшавская"
]

def fetch_period(olap, date_from, olap_date_to):
    """Один OLAP-запрос, возвращает DataFrame с подготовленными данными"""
    raw = olap.get_draft_sales_report(date_from, olap_date_to)
    if not raw or not raw.get('data'):
        return pd.DataFrame()
    df = pd.DataFrame(raw['data'])
    df['DishAmountInt'] = pd.to_numeric(df['DishAmountInt'], errors='coerce').fillna(0)
    df['DishDiscountSumInt'] = pd.to_numeric(df['DishDiscountSumInt'], errors='coerce').fillna(0)
    df['ProductCostBase.ProductCost'] = pd.to_numeric(df['ProductCostBase.ProductCost'], errors='coerce').fillna(0)
    df['ProductCostBase.MarkUp'] = pd.to_numeric(df['ProductCostBase.MarkUp'], errors='coerce').fillna(0)
    df['OpenDate.Typed'] = pd.to_datetime(df['OpenDate.Typed'])
    df['Margin'] = df['DishDiscountSumInt'] - df['ProductCostBase.ProductCost']
    return df


def get_bar_summary(df, bar_name=None):
    """Агрегация по сортам пива для одного бара (или всех)"""
    if df.empty:
        return pd.DataFrame(columns=['BeerName', 'Bar', 'TotalLiters', 'TotalRevenue'])
    analyzer = DraftAnalysis(df.copy())
    summary = analyzer.get_beer_summary(bar_name, include_financials=True)
    return summary


def pct_change(old, new):
    if old == 0:
        return None
    return round((new - old) / old * 100, 1)


def fmt_delta(val):
    if val is None:
        return "NEW"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.1f}%"


def main():
    today = datetime(2026, 2, 26)

    ytd_2025_from = "2025-01-01"
    ytd_2025_to = today.replace(year=2025).strftime("%Y-%m-%d")
    ytd_2026_from = "2026-01-01"
    ytd_2026_to = today.strftime("%Y-%m-%d")

    # +1 день — OLAP exclusive
    olap_to_2025 = (datetime.strptime(ytd_2025_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    olap_to_2026 = (datetime.strptime(ytd_2026_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

    print(f"L4L Разливное пиво")
    print(f"2025: {ytd_2025_from} — {ytd_2025_to}")
    print(f"2026: {ytd_2026_from} — {ytd_2026_to}")
    print()

    olap = OlapReports()
    if not olap.connect():
        print("Не удалось подключиться к iiko API")
        return

    try:
        print("Загружаю данные за 2025...")
        df_2025 = fetch_period(olap, ytd_2025_from, olap_to_2025)
        print(f"  Строк: {len(df_2025)}")

        print("Загружаю данные за 2026...")
        df_2026 = fetch_period(olap, ytd_2026_from, olap_to_2026)
        print(f"  Строк: {len(df_2026)}")
    finally:
        olap.disconnect()

    if df_2025.empty and df_2026.empty:
        print("Нет данных за оба периода")
        return

    # Собираем L4L для каждого бара + итого
    bar_list = BARS + [None]  # None = итого по всем
    all_rows = []

    for bar in bar_list:
        bar_label = bar if bar else "ИТОГО"

        s25 = get_bar_summary(df_2025, bar)
        s26 = get_bar_summary(df_2026, bar)

        # Собираем все сорта из обоих периодов
        beers_25 = {}
        for _, r in s25.iterrows():
            beers_25[r['BeerName']] = {
                'liters': float(r['TotalLiters']),
                'revenue': float(r.get('TotalRevenue', 0)),
                'markup': float(r.get('AvgMarkupPercent', 0)),
                'margin': float(r.get('TotalMargin', 0)),
            }

        beers_26 = {}
        for _, r in s26.iterrows():
            beers_26[r['BeerName']] = {
                'liters': float(r['TotalLiters']),
                'revenue': float(r.get('TotalRevenue', 0)),
                'markup': float(r.get('AvgMarkupPercent', 0)),
                'margin': float(r.get('TotalMargin', 0)),
            }

        all_beers = sorted(set(list(beers_25.keys()) + list(beers_26.keys())))

        zero = {'liters': 0, 'revenue': 0, 'markup': 0, 'margin': 0}

        for beer in all_beers:
            d25 = beers_25.get(beer, zero)
            d26 = beers_26.get(beer, zero)
            ppl25 = round(d25['revenue'] / d25['liters']) if d25['liters'] > 0 else 0
            ppl26 = round(d26['revenue'] / d26['liters']) if d26['liters'] > 0 else 0
            mpl25 = round(d25['margin'] / d25['liters']) if d25['liters'] > 0 else 0
            mpl26 = round(d26['margin'] / d26['liters']) if d26['liters'] > 0 else 0
            all_rows.append({
                'Бар': bar_label,
                'Пиво': beer,
                'Литры 2025': round(d25['liters'], 1),
                'Литры 2026': round(d26['liters'], 1),
                'Д Литры': fmt_delta(pct_change(d25['liters'], d26['liters'])),
                'Выручка 2025': round(d25['revenue']),
                'Выручка 2026': round(d26['revenue']),
                'Д Выручка': fmt_delta(pct_change(d25['revenue'], d26['revenue'])),
                'Р/литр 25': ppl25 if ppl25 else '-',
                'Р/литр 26': ppl26 if ppl26 else '-',
                'Наценка 2025': f"{d25['markup'] * 100:.0f}%" if d25['markup'] else '-',
                'Наценка 2026': f"{d26['markup'] * 100:.0f}%" if d26['markup'] else '-',
                'Маржа 2025': round(d25['margin']),
                'Маржа 2026': round(d26['margin']),
                'Д Маржа': fmt_delta(pct_change(d25['margin'], d26['margin'])),
                'Маржа/литр 25': mpl25 if mpl25 else '-',
                'Маржа/литр 26': mpl26 if mpl26 else '-',
            })

        # Итого по бару
        total_l25 = sum(v['liters'] for v in beers_25.values())
        total_l26 = sum(v['liters'] for v in beers_26.values())
        total_r25 = sum(v['revenue'] for v in beers_25.values())
        total_r26 = sum(v['revenue'] for v in beers_26.values())
        total_m25 = sum(v['margin'] for v in beers_25.values())
        total_m26 = sum(v['margin'] for v in beers_26.values())
        # Средневзвешенная наценка = маржа / себестоимость
        total_cost25 = total_r25 - total_m25
        total_cost26 = total_r26 - total_m26
        avg_markup25 = (total_m25 / total_cost25 * 100) if total_cost25 > 0 else 0
        avg_markup26 = (total_m26 / total_cost26 * 100) if total_cost26 > 0 else 0
        t_ppl25 = round(total_r25 / total_l25) if total_l25 > 0 else 0
        t_ppl26 = round(total_r26 / total_l26) if total_l26 > 0 else 0
        t_mpl25 = round(total_m25 / total_l25) if total_l25 > 0 else 0
        t_mpl26 = round(total_m26 / total_l26) if total_l26 > 0 else 0
        all_rows.append({
            'Бар': bar_label,
            'Пиво': '*** ВСЕГО ***',
            'Литры 2025': round(total_l25, 1),
            'Литры 2026': round(total_l26, 1),
            'Д Литры': fmt_delta(pct_change(total_l25, total_l26)),
            'Выручка 2025': round(total_r25),
            'Выручка 2026': round(total_r26),
            'Д Выручка': fmt_delta(pct_change(total_r25, total_r26)),
            'Р/литр 25': t_ppl25 if t_ppl25 else '-',
            'Р/литр 26': t_ppl26 if t_ppl26 else '-',
            'Наценка 2025': f"{avg_markup25:.0f}%" if total_cost25 > 0 else '-',
            'Наценка 2026': f"{avg_markup26:.0f}%" if total_cost26 > 0 else '-',
            'Маржа 2025': round(total_m25),
            'Маржа 2026': round(total_m26),
            'Д Маржа': fmt_delta(pct_change(total_m25, total_m26)),
            'Маржа/литр 25': t_mpl25 if t_mpl25 else '-',
            'Маржа/литр 26': t_mpl26 if t_mpl26 else '-',
        })

    result_df = pd.DataFrame(all_rows)

    # Краткая сводка ИТОГО по барам в консоль
    print("\n" + "=" * 100)
    print("L4L DRAFT BEER: YTD 2025 vs YTD 2026 -- ITOGI")
    print("=" * 100)

    totals = result_df[result_df['Пиво'] == '*** ВСЕГО ***']
    summary_cols = ['Бар', 'Литры 2025', 'Литры 2026', 'Д Литры',
                    'Выручка 2025', 'Выручка 2026', 'Д Выручка',
                    'Маржа 2025', 'Маржа 2026', 'Д Маржа']
    pd.set_option('display.width', 200)
    pd.set_option('display.max_colwidth', 25)
    print(totals[summary_cols].to_string(index=False))

    # Сохраняем полную таблицу в CSV
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'l4l_draft_ytd_v2.csv')
    result_df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=';')
    print(f"\nPolnaya tablitsa: {csv_path}")
    print("Otkroy v Excel dlya prosmotra vsekh stolbtsov")


if __name__ == '__main__':
    main()
