"""
Текущие цены меню из iiko OLAP для карточек каталога (data/menu_cards.json).

Идея (как в scripts/menu_prices.py, но ОБОБЩЁННО по любому имени карточки, без
ручного словаря кранов):
  - Тянем продажи разливного (reportType SALES, DishGroup.TopParent="Напитки Розлив")
    с полем DishSumInt ("сумма без скидки" = цена прайса до скидок).
  - Цена порции = МОДА unit-цены (DishSumInt/DishAmountInt по строке бар+дата),
    взвешенная по проданным порциям; тай-брейк — более свежая дата.
  - Карточку сопоставляем с сортом iiko по транслитерированным «фирменным» токенам
    (служебные слова стиля/объёма отбрасываем). Обновляем ТОЛЬКО уверенные совпадения;
    сорта не в текущих продажах сохраняют свою цену.

Используется:
  - сервером (кнопка «Обновить цены») — refresh_prices(cards)
  - скриптом первичной заливки — scripts/fill_menu_prices.py
"""
import os
import re
import json
from datetime import datetime, timedelta

import requests

from core.iiko_api import IikoAPI
from core.draft_analysis import DraftAnalysis

PORTION_FIELD = {0.25: "p025", 0.4: "p04", 0.5: "p05"}  # один вариант разлива

# --- транслитерация для сопоставления имён (кириллица/латиница, варианты написания) ---
_TR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
_SOFT = [("ck", "k"), ("kk", "k"), ("aa", "a"), ("ee", "e"), ("ie", "i"),
        ("ei", "i"), ("yu", "u"), ("ya", "a"), ("yo", "o"), ("ph", "f"),
        ("th", "t"), ("zh", "z"), ("kh", "h"), ("y", "i"), ("oo", "u")]

# Слова СТИЛЯ — не являются «фирменным» признаком сорта (классификатор бренда).
# ВНИМАНИЕ: токены стиля НЕ выкидываются из набора — они нужны для строгого
# сопоставления подмножеств. Стоп лишь определяет, есть ли у карточки «бренд»:
# если у карточки только слова стиля (напр. «Стаут», «Хеллес», «ИПА») — она слишком
# обобщённая, и автосопоставление по ней запрещено (иначе ложные совпадения).
_STYLE = {
    "ipa", "apa", "dipa", "neipa", "ale", "el", "lager", "beer", "bir", "stout",
    "staut", "porter", "weizen", "vaicen", "vaisen", "hefe", "hefevaicen",
    "hefevaisen", "hefevaise", "vaisbir", "vaisse", "pils", "pilsner", "pilzner",
    "blonde", "blond", "tripel", "tripl", "dubbel", "dubel", "quadrupel",
    "kvadrupel", "sidr", "cider", "blanche", "blansh", "vitbir", "witbier",
    "gose", "goze", "helles", "heles", "hell", "amber", "amer", "marzen",
    "mercen", "dunkel", "bock", "saison", "seson", "sour", "saur", "imperial",
    "imperskii", "doppelbock", "dortmunder", "festbir", "draft", "draught",
}
_CONNECT = {"the", "and", "von", "der", "des", "los", "las", "fest"}
_VOL_RE = re.compile(r"\b(0[.,]\d+|\d+[.,]\d+|\d+л|\d+ml|\d+мл)\b")


def _translit(s):
    s = (s or "").lower()
    out = "".join(_TR.get(ch, ch) for ch in s)
    out = re.sub(r"[^a-z0-9 ]", " ", out)
    for a, b in _SOFT:
        out = out.replace(a, b)
    return re.sub(r"\s+", " ", out).strip()


def _tokens(text):
    """Все значимые токены (включая стиль), без объёма/коротышей/союзов."""
    t = _VOL_RE.sub(" ", text or "")
    toks = _translit(t).split()
    return {w for w in toks if len(w) >= 3 and w not in _CONNECT}


def card_tokens(card):
    return _tokens(card.get("name", "") + " " + card.get("latin", ""))


# ---------------------------------------------------------------------------
# Загрузка продаж из iiko
# ---------------------------------------------------------------------------

def _olap_body(date_from, olap_to):
    return {
        "reportType": "SALES",
        "groupByRowFields": ["DishName", "Store.Name", "OpenDate.Typed"],
        "groupByColFields": [],
        "aggregateFields": ["DishAmountInt", "DishSumInt", "DishDiscountSumInt"],
        "filters": {
            "OpenDate.Typed": {"filterType": "DateRange", "periodType": "CUSTOM",
                               "from": date_from, "to": olap_to},
            "DishGroup.TopParent": {"filterType": "IncludeValues", "values": ["Напитки Розлив"]},
            "DeletedWithWriteoff": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]},
            "OrderDeleted": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]},
        },
    }


def fetch_sales_raw(date_from, date_to_incl, cache_path=None, use_cache=True):
    """Сырой ответ OLAP. cache_path — необязательный кэш (для оффлайн/повторов)."""
    if use_cache and cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)
    olap_to = (datetime.strptime(date_to_incl, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    api = IikoAPI()
    if not api.authenticate():
        raise RuntimeError("iiko auth failed")
    try:
        r = requests.post(f"{api.base_url}/v2/reports/olap", params={"key": api.token},
                          json=_olap_body(date_from, olap_to),
                          headers={"Content-Type": "application/json"}, timeout=120)
    finally:
        api.logout()
    if r.status_code != 200:
        raise RuntimeError(f"OLAP HTTP {r.status_code}: {r.text[:300]}")
    raw = r.json()
    if not raw.get("data"):
        raise RuntimeError("OLAP empty")
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
    return raw


def prepare_sales_df(raw):
    import pandas as pd
    df = pd.DataFrame(raw["data"])
    for c in ["DishAmountInt", "DishSumInt", "DishDiscountSumInt"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    p = DraftAnalysis(df.copy()).prepare_draft_data()
    date_col = "OpenDate.Typed" if "OpenDate.Typed" in p.columns else "OpenDate"
    p["_d"] = pd.to_datetime(p[date_col])
    return p


# ---------------------------------------------------------------------------
# Индекс сортов iiko + цены
# ---------------------------------------------------------------------------

def build_iiko_index(p):
    """{BeerNameNorm: {'tokens': set, 'amt': int, 'sub': DataFrame}}."""
    index = {}
    for name, sub in p.groupby("BeerNameNorm"):
        index[name] = {
            "tokens": _tokens(str(name)),
            "amt": float(sub["DishAmountInt"].sum()),
            "sub": sub,
        }
    return index


def _prices_from_sub(sub):
    """Цена каждой порции = взвешенная мода unit-цены (как в scripts/menu_prices.py)."""
    out = {}
    for vol, field in PORTION_FIELD.items():
        g = sub[(sub["PortionVolume"] - vol).abs() < 1e-6].copy()
        g = g[g["DishAmountInt"] > 0]
        if g.empty:
            continue
        g["unit"] = (g["DishSumInt"] / g["DishAmountInt"]).round().astype(int)
        wsum = g.groupby("unit")["DishAmountInt"].sum()
        recent = g.groupby("unit")["_d"].max()
        best = sorted(wsum.index, key=lambda u: (wsum[u], recent[u]))[-1]
        out[field] = int(best)
    return out


def _brand(toks):
    return toks - _STYLE


def match_card(card, index):
    """Высокоточное совпадение карточки с сортом iiko (или None).

    Правила (precision >> recall — лучше не обновить, чем поставить чужую цену):
      1. У карточки должен быть «бренд»-токен (не только слова стиля). Иначе
         («Стаут», «Хеллес», «ИПА») — слишком обобщённо, не сопоставляем.
      2. Кандидат — сорт iiko, чьи токены являются над/подмножеством токенов
         карточки и делят хотя бы один бренд-токен.
      3. Принимаем только ОДНОЗНАЧНОЕ совпадение: точное равенство наборов, либо
         ровно один кандидат. Несколько разных кандидатов -> неоднозначно -> отказ.
      4. Запасной путь — высокий Жаккар (>=0.7) с явным отрывом и общим брендом.
    """
    ct = card_tokens(card)
    if not _brand(ct):
        return None, 0.0
    cands = []
    for name, info in index.items():
        it = info["tokens"]
        if not it:
            continue
        if (ct <= it or it <= ct) and _brand(ct & it):
            cands.append((name, it, info["amt"]))
    exact = [c for c in cands if c[1] == ct]
    chosen = None
    if len(exact) >= 1:
        chosen = sorted(exact, key=lambda c: -c[2])[0]
    elif len({c[0] for c in cands}) == 1:
        chosen = cands[0]
    if chosen is not None:
        name, it = chosen[0], chosen[1]
        return name, round(len(ct & it) / len(ct | it), 2)
    # неоднозначно или нет подмножества -> строгий Жаккар
    scored = sorted(
        ((len(ct & info["tokens"]) / len(ct | info["tokens"]), name)
         for name, info in index.items() if info["tokens"]),
        reverse=True,
    )
    if scored and scored[0][0] >= 0.7 and (len(scored) < 2 or scored[1][0] < scored[0][0]):
        nm = scored[0][1]
        if _brand(ct & index[nm]["tokens"]):
            return nm, round(scored[0][0], 2)
    return None, round(scored[0][0] if scored else 0.0, 2)


def compute_prices(cards, p):
    """Вернуть {card_id: {'prices': {...}, 'iiko_name': str, 'score': float}} только
    для карточек с уверенным совпадением в текущих продажах."""
    index = build_iiko_index(p)
    result = {}
    for c in cards:
        name, score = match_card(c, index)
        if not name:
            continue
        prices = _prices_from_sub(index[name]["sub"])
        if not prices:
            continue
        result[c["id"]] = {"prices": prices, "iiko_name": str(name), "score": score}
    return result


def refresh_prices(cards, date_from=None, date_to_incl=None, cache_path=None, use_cache=False):
    """Обновить цены карточек ПО МЕСТУ из текущих продаж iiko. Возвращает сводку:
    {'updated': [...], 'matched': N, 'total': N, 'date_from':, 'date_to':}.
    Карточки без совпадения остаются как есть."""
    if date_to_incl is None:
        date_to_incl = datetime.now().strftime("%Y-%m-%d")
    if date_from is None:
        # последние ~3.5 месяца — свежие цены, но достаточно данных для моды
        date_from = (datetime.now() - timedelta(days=105)).strftime("%Y-%m-%d")
    raw = fetch_sales_raw(date_from, date_to_incl, cache_path=cache_path, use_cache=use_cache)
    p = prepare_sales_df(raw)
    priced = compute_prices(cards, p)
    by_id = {c["id"]: c for c in cards}
    updated = []
    for cid, info in priced.items():
        c = by_id.get(cid)
        if not c:
            continue
        changed = {}
        for field, val in info["prices"].items():
            if c.get(field) != val:
                changed[field] = {"old": c.get(field), "new": val}
            c[field] = val
        updated.append({"id": cid, "name": c.get("name"), "iiko_name": info["iiko_name"],
                        "score": info["score"], "changed": changed,
                        "prices": info["prices"]})
    return {
        "updated": updated, "matched": len(priced), "total": len(cards),
        "date_from": date_from, "date_to": date_to_incl,
    }
