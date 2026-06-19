"""
Тянет ТЕКУЩИЕ цены меню (по порциям 0.25/0.3/0.4/0.5 л) для сортов на кранах
из iiko OLAP. Ключевое отличие от обычного draft-отчёта: добавлено поле
DishSumInt ("Сумма без скидки") — это и есть цена по меню (до скидок).
Цена порции = sum(DishSumInt) / sum(DishAmountInt) по последней дате,
где порция продавалась (чтобы взять актуальную цену, а не средневзвешенную
по периоду со старыми ценами).

Запуск: py -3 scripts/menu_prices.py
Выход:  data/menu_tap_prices.json  +  печать таблицы.
"""
import sys
import os
import json
import requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from datetime import datetime, timedelta
from core.iiko_api import IikoAPI
from core.draft_analysis import DraftAnalysis

DATE_FROM = "2026-03-01"
DATE_TO_INCL = "2026-06-19"          # включительно
CACHE = os.path.join(os.path.dirname(__file__), '..', 'data', 'cache', 'menu_prices_raw_v2.json')
OUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'menu_tap_prices.json')

# Краны со скрина (номер -> (подпись, список AND-групп токенов в lower)).
# Совпадение, если ХОТЯ БЫ ОДНА группа целиком входит в BeerNameNorm.
TAPS = {
    1:  ("ФестХаус Хеллес",          [["фестхаус", "хеллес"]]),
    2:  ("Гулден Драк 708",          [["гулден", "драк"], ["gulden", "drak"], ["708"]]),
    3:  ("ФестХаус Вайцен",          [["фестхаус", "вайцен"]]),
    5:  ("Plan B Emanation",         [["plan b", "emanation"], ["эманейшн"], ["emanation"]]),
    6:  ("Островица Гозе",           [["островица", "гозе"]]),
    7:  ("Brewlok IPA",              [["brewlok", "ipa"], ["брюлок", "ипа"], ["брулок", "ипа"]]),
    8:  ("Степь и Ветер Мёд и Абрикос", [["степь", "ветер"], ["мёд", "абрикос"], ["мед", "абрикос"]]),
    9:  ("Zavod Morning Manya",      [["morning", "manya"], ["манnet"], ["маня"], ["manya"]]),
    10: ("Бьюльви Рустик полусухой", [["бьюльви", "рустик"], ["бьюльви"], ["bjuly"], ["рустик", "полусух"]]),
    12: ("Бургунь де Фландер",       [["бургунь", "фландер"], ["bourgogne"]]),
    13: ("Rework Nutty Nut",         [["rework", "nutty"], ["реворк"], ["nutty", "nut"]]),
    14: ("ЛеФорт Трипель",           [["лефорт", "трипель"], ["lefort"], ["leffort"]]),
    15: ("Black Cat Клюквенная Пастила", [["black cat", "клюквен"], ["клюквенная", "пастила"], ["клюквен", "пастил"]]),
    16: ("Polnochnyj Project Signal Fire", [["signal", "fire"], ["сигнал", "файр"], ["сигнал", "фаер"]]),
    17: ("Коникс Черри Руби",        [["коникс", "черри"], ["черри", "руби"], ["cherry", "ruby"]]),
    18: ("Палм",                     [["палм"], ["palm"]]),
    20: ("Alaska Фейхоа",            [["alaska", "фейхоа"], ["аляска", "фейхоа"], ["фейхоа"]]),
    21: ("Островица Холи ДИПА",      [["островица", "холи"], ["холи", "дипа"], ["holy"]]),
    22: ("Gravity Heartless Bitch 2.0", [["heartless", "bitch"], ["хартлесс", "бич"], ["heartless"]]),
    23: ("Ригеле Коммерцинрат",      [["ригеле", "коммерци"], ["коммерциенрат"], ["commerzienrat"]]),
    24: ("Brewlok Stout",            [["brewlok", "stout"], ["брюлок", "стаут"], ["брулок", "стаут"]]),
}

PORTION_FIELD = {0.25: "p025", 0.3: "p03", 0.4: "p04", 0.5: "p05"}


def fetch_raw():
    if os.path.exists(CACHE):
        print(f"[cache] {CACHE}")
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    olap_to = (datetime.strptime(DATE_TO_INCL, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    api = IikoAPI()
    print(f"[auth] {api.base_url}")
    if not api.authenticate():
        print("[ERROR] auth failed"); sys.exit(1)
    body = {
        "reportType": "SALES",
        "groupByRowFields": ["DishName", "Store.Name", "OpenDate.Typed"],
        "groupByColFields": [],
        "aggregateFields": ["DishAmountInt", "DishSumInt", "DishDiscountSumInt"],
        "filters": {
            "OpenDate.Typed": {"filterType": "DateRange", "periodType": "CUSTOM",
                               "from": DATE_FROM, "to": olap_to},
            "DishGroup.TopParent": {"filterType": "IncludeValues", "values": ["Напитки Розлив"]},
            "DeletedWithWriteoff": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]},
            "OrderDeleted": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]},
        },
    }
    print(f"[api] draft + DishSumInt {DATE_FROM}..{DATE_TO_INCL}")
    r = requests.post(f"{api.base_url}/v2/reports/olap", params={"key": api.token},
                      json=body, headers={"Content-Type": "application/json"}, timeout=120)
    api.logout()
    if r.status_code != 200:
        print(f"[ERROR] HTTP {r.status_code}: {r.text[:300]}"); sys.exit(1)
    raw = r.json()
    if not raw.get("data"):
        print("[ERROR] empty"); sys.exit(1)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
    print(f"[saved] {CACHE} rows={len(raw['data'])}")
    return raw


def matches(norm, groups):
    return any(all(tok in norm for tok in grp) for grp in groups)


def main():
    raw = fetch_raw()
    df = pd.DataFrame(raw["data"])
    for c in ["DishAmountInt", "DishSumInt", "DishDiscountSumInt"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    p = DraftAnalysis(df.copy()).prepare_draft_data()
    date_col = "OpenDate.Typed" if "OpenDate.Typed" in p.columns else "OpenDate"
    p["_d"] = pd.to_datetime(p[date_col])

    result = {}
    print("\n=== ЦЕНЫ ПО КРАНАМ (цена порции = сумма без скидки / кол-во; актуальная дата) ===\n")
    for tn in sorted(TAPS):
        label, groups = TAPS[tn]
        sub = p[p["BeerNameNorm"].apply(lambda s: matches(str(s), groups))]
        entry = {"tap": tn, "label": label, "matched_names": [], "prices": {},
                 "price_history": {}, "found": False}
        if sub.empty:
            print(f"#{tn:2d} {label:32s}  НЕ НАЙДЕНО В ПРОДАЖАХ")
            result[tn] = entry
            continue
        entry["found"] = True
        entry["matched_names"] = sorted(sub["BeerNameOriginal"].dropna().unique().tolist())[:6]
        store_col = "Store.Name" if "Store.Name" in sub.columns else None
        prices = {}
        hist = {}
        for vol, field in PORTION_FIELD.items():
            g = sub[(sub["PortionVolume"] - vol).abs() < 1e-6].copy()
            g = g[g["DishAmountInt"] > 0]
            if g.empty:
                continue
            # Каждая строка = (блюдо, бар, дата): в пределах одной такой строки
            # цена фиксированная, поэтому unit = DishSumInt/DishAmountInt — чистая
            # цена прайса (без блендинга по барам/дням).
            g["unit"] = (g["DishSumInt"] / g["DishAmountInt"]).round().astype(int)
            # Цена прайса = МОДА, взвешенная по проданным порциям (по какой цене
            # реально продан максимум объёма). Тай-брейк — более свежая дата.
            wsum = g.groupby("unit")["DishAmountInt"].sum()
            recent = g.groupby("unit")["_d"].max()
            best = sorted(wsum.index, key=lambda u: (wsum[u], recent[u]))[-1]
            distinct = sorted(int(u) for u in wsum.index)
            prices[field] = int(best)
            hist[field] = {
                "list_price": int(best),
                "portions_at_list": int(wsum[best]),
                "portions_total": int(g["DishAmountInt"].sum()),
                "distinct": distinct,
                "latest_date": str(g["_d"].max().date()),
            }
        entry["prices"] = prices
        entry["price_history"] = hist
        result[tn] = entry
        pr = "  ".join(f"{f}={prices[f]}" for f in ("p025", "p03", "p04", "p05") if f in prices)
        warn = ""
        for f, h in hist.items():
            if len(h["distinct"]) > 1:
                warn += f"  [{f} менялась: {h['distinct']}]"
        print(f"#{tn:2d} {label:32s}  {pr}{warn}")
        print(f"      iiko: {entry['matched_names']}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[out] {OUT}")
    miss = [TAPS[t][0] for t in sorted(TAPS) if not result[t]["found"]]
    if miss:
        print(f"\nНЕ НАЙДЕНЫ ({len(miss)}): {miss}")


if __name__ == "__main__":
    main()
