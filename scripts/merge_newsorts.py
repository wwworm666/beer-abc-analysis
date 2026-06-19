"""
Вливает новые сорта (ресёрч + цены iiko) в каталог data/menu_cards.json.

Вход:
  data/menu_cards.json            — текущий каталог (существующие НЕ трогаем/не удаляем)
  data/menu_newsorts_output.json  — ресёрч новых сортов (по id 119+)
  data/menu_new_sorts.json        — соответствие id -> name_src (имя сорта из iiko/CSV)
  data/cache/menu_prices_raw_v2.json — кэш продаж iiko (для цен)

Что делает:
  1. Строит карточки из ресёрча (Title-case имени, поля, шкалы).
  2. Тянет цены из iiko по точному имени сорта (name_src ~ имя iiko -> надёжно).
  3. Дедуп: НОВЫЕ карточки сверяются с существующими и между собой (транслит-токены +
     равная крепость/близкая цена). Существующие 108 ПРИОРИТЕТНЫ и никогда не удаляются;
     дубль-новинка вливается в найденную карточку (добивает пустые поля) и отбрасывается.
  4. Нумерует уцелевшие новые (n = max+1...), пишет каталог + отчёт.

Запуск: py -3 scripts/merge_newsorts.py
"""
import os
import re
import sys
import json
import io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import menu_pricing as mp

CARDS = os.path.join(ROOT, "data", "menu_cards.json")
RESEARCH = os.path.join(ROOT, "data", "menu_newsorts_output.json")
NEWSRC = os.path.join(ROOT, "data", "menu_new_sorts.json")
CACHE = os.path.join(ROOT, "data", "cache", "menu_prices_raw_v2.json")
REPORT = os.path.join(ROOT, "data", "_merge_newsorts.txt")

ACRON = {"ИПА", "ДИПА", "АПА", "НЕИПА", "IPA", "APA", "DIPA", "NEIPA", "DDH",
         "ESB", "IPL", "XPA", "APA", "NEIPA", "DIPL", "БША", "БСА"}

# Ручные слияния дублей, не пойманных авто-дедупом (различающие токены лежат в
# латинице/написании/сервинге, не в поле brewery). Проверено по ревью
# data/_dupe_candidates.txt. Формат (loser_id -> winner_id): победитель остаётся.
MANUAL_MERGE = [
    (242, 111),  # Клюквенная Пастила (Black Cat / Culture Code) — одинак. цена
    (218, 95),   # Дортмундер (Konix)
    (147, 71),   # Мунлайт (Starlingtons/Hobsons Moonlight)
    (302, 186),  # Вивизеро (Bullevie Vivizero) — написание
    (267, 32),   # Айриш Ред Нитро -> Айриш Рэд (O'Hara's, нитро=сервинг)
    (221, 169),  # Шрейдер -> Шрадер (Velka Morava Schrader) — написание
    (128, 17),   # Рустик Полусухой -> Рустик (Bullevie Rustiq) — одинак. цена
    (178, 37),   # Фул Мун 12 -> Фулл Мун (Triporteur Full Moon)
    (247, 201),  # Джуси ИПА -> ИПА (Ostrovica) — одинак. цена/крепость
    (285, 66),   # Хель -> Байройтер (Bayreuther Hell)
    (145, 74),   # Дикий Крест Сухой -> Дикий Крест (Rebel Apple, сухой сидр)
]


def smart_title(s):
    out = []
    for w in (s or "").split():
        if w.upper() in ACRON:
            out.append(w.upper())
        elif w.isupper():
            out.append(w[:1].upper() + w[1:].lower())
        else:
            out.append(w)
    return " ".join(out).strip()


def filled(v):
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def richness(c):
    s = 0
    for k in ("name", "latin", "brewery", "country", "style", "abv"):
        s += 1 if filled(c.get(k)) else 0
    s += 2 if [t for t in (c.get("tags") or []) if str(t).strip()] else 0
    r = c.get("ratings") or {}
    s += 2 if any(int(r.get(k) or 0) > 0 for k in ("gor", "plot", "cvet")) else 0
    s += sum(1 for p in ("p025", "p04", "p05") if filled(c.get(p)))
    return s


# Локальная транслитерация для дедупа: дополнительно схлопываем удвоенные согласные
# (urhell~urhel, helles~heles) — ловит расхождения написания, не трогая прайс-матчинг.
_EXTRA = [("ll", "l"), ("nn", "n"), ("ss", "s"), ("tt", "t"), ("mm", "m"),
          ("rr", "r"), ("pp", "p"), ("ff", "f"), ("bb", "b"), ("dd", "d")]


def dtok(text):
    base = mp._translit(text or "")
    for a, b in _EXTRA:
        base = base.replace(a, b)
    return {w for w in base.split() if len(w) >= 3 and w not in mp._CONNECT}


def card_dtok(c):
    return dtok(c.get("name", "") + " " + c.get("latin", ""))


def brew_dtok(c):
    return dtok(c.get("brewery", ""))


def brand(t):
    return t - mp._STYLE


def _norm_abv(c):
    return str(c.get("abv") or "").replace(",", ".").replace("%", "").strip()


def is_dup(a_tok, a, b_tok, b):
    """Высокоточная проверка дубля. Главное: подмножество сливаем ТОЛЬКО если лишний
    токен — это пивоварня-префикс («Мораван» ⊂ «Литовел Мораван»), а НЕ вкусовой/
    продуктовый признак («Кутс» ⊂ «Кутс Халапеньо» — это РАЗНЫЕ сорта, не сливать)."""
    if not (brand(a_tok) and brand(b_tok)):
        return False
    if not brand(a_tok & b_tok):
        return False
    union = a_tok | b_tok
    j = len(a_tok & b_tok) / len(union) if union else 0
    if j >= 0.7:
        return True
    if a_tok <= b_tok or b_tok <= a_tok:
        extra = (b_tok - a_tok) if a_tok <= b_tok else (a_tok - b_tok)
        meaningful = extra - mp._STYLE           # стиль/сервинг (draft/nitro/ipa) не различают
        if not meaningful:
            return True                          # «Гиннесс Драфт» ~ «Гиннес», «Оверфол ИПА» ~ «Оверфол»
        bt = brew_dtok(a) | brew_dtok(b)
        return meaningful <= bt                  # иначе сливаем только пивоварня-префикс
    abv_eq = _norm_abv(a) == _norm_abv(b) and _norm_abv(a) != ""
    diffs = []
    for f in ("p025", "p04", "p05"):
        x, y = a.get(f), b.get(f)
        if x and y:
            diffs.append(abs(x - y) / max(x, y))
    price_close = (sum(diffs) / len(diffs)) < 0.08 if diffs else False
    if j >= 0.5 and abv_eq and price_close:
        return True
    return False


def main():
    catalog = json.load(open(CARDS, encoding="utf-8"))
    research = {r["id"]: r for r in json.load(open(RESEARCH, encoding="utf-8"))}
    srcmap = {s["id"]: s["name_src"] for s in json.load(open(NEWSRC, encoding="utf-8"))}

    # 1. карточки из ресёрча
    new_cards = []
    for rid, r in research.items():
        new_cards.append({
            "id": rid, "n": 0, "tap": None,
            "name": smart_title(r.get("name_ru", "")),
            "latin": (r.get("latin") or "").strip(),
            "brewery": (r.get("brewery") or "").strip(),
            "country": (r.get("country") or "").strip(),
            "style": (r.get("style") or "").strip(),
            "abv": str(r.get("abv") or "").strip().replace("%", "").strip(),
            "tags": [str(t).strip() for t in (r.get("tags") or [])][:3],
            "ratings": {"gor": int(r.get("gor") or 0), "plot": int(r.get("plot") or 0),
                        "cvet": int(r.get("cvet") or 0)},
            "p025": None, "p04": None, "p05": None,
            "_src": srcmap.get(rid, ""),
        })

    # 2. цены новых из iiko (по точному имени сорта)
    raw = mp.fetch_sales_raw("2026-03-01", "2026-06-19", cache_path=CACHE, use_cache=True)
    p = mp.prepare_sales_df(raw)
    index = mp.build_iiko_index(p)
    priced = 0
    for c in new_cards:
        probe = {"name": c["_src"] or c["name"], "latin": c["latin"]}
        name, score = mp.match_card(probe, index)
        if name:
            pr = mp._prices_from_sub(index[name]["sub"])
            for k, v in pr.items():
                c[k] = v
            if pr:
                priced += 1

    # 3. дедуп: существующие приоритетны, новые сверяем с kept
    cat_tok = {c["id"]: card_dtok(c) for c in catalog}
    new_tok = {c["id"]: card_dtok(c) for c in new_cards}
    kept = list(catalog)  # существующие всегда остаются
    kept_tok = dict(cat_tok)
    dropped = []  # (loser_name, winner_name)

    # сначала более заполненные новинки (они становятся «победителями» среди новых)
    for c in sorted(new_cards, key=lambda x: (-richness(x), x["id"])):
        ct = new_tok[c["id"]]
        match = None
        for k in kept:
            if is_dup(ct, c, kept_tok[k["id"]], k):
                match = k
                break
        if match is not None:
            # влить недостающие поля новинки в найденную карточку
            for fld in ("latin", "brewery", "country", "style", "abv"):
                if not filled(match.get(fld)) and filled(c.get(fld)):
                    match[fld] = c[fld]
            if not [t for t in (match.get("tags") or []) if str(t).strip()] and c.get("tags"):
                match["tags"] = c["tags"]
            mr = match.get("ratings") or {}
            if not any(int(mr.get(x) or 0) > 0 for x in ("gor", "plot", "cvet")):
                match["ratings"] = c["ratings"]
            for pf in ("p025", "p04", "p05"):
                if not filled(match.get(pf)) and filled(c.get(pf)):
                    match[pf] = c[pf]
            dropped.append((c["name"], match["name"]))
        else:
            kept.append(c)
            kept_tok[c["id"]] = ct

    # 3b. ручные слияния (по ревью кандидатов)
    by_id = {c["id"]: c for c in kept}
    man = 0
    for lose_id, win_id in MANUAL_MERGE:
        lose, win = by_id.get(lose_id), by_id.get(win_id)
        if not lose or not win:
            continue
        for fld in ("latin", "brewery", "country", "style", "abv"):
            if not filled(win.get(fld)) and filled(lose.get(fld)):
                win[fld] = lose[fld]
        if not [t for t in (win.get("tags") or []) if str(t).strip()] and lose.get("tags"):
            win["tags"] = lose["tags"]
        wr = win.get("ratings") or {}
        if not any(int(wr.get(x) or 0) > 0 for x in ("gor", "plot", "cvet")):
            win["ratings"] = lose["ratings"]
        for pf in ("p025", "p04", "p05"):
            if not filled(win.get(pf)) and filled(lose.get(pf)):
                win[pf] = lose[pf]
        kept = [c for c in kept if c["id"] != lose_id]
        dropped.append((lose["name"], win["name"]))
        man += 1

    # 4. нумерация новых уцелевших + очистка служебных полей
    survivors_new = [c for c in kept if c.get("id", 0) >= 119]
    max_n = max((int(c.get("n") or 0) for c in catalog), default=0)
    survivors_new.sort(key=lambda x: x["id"])
    for i, c in enumerate(survivors_new, start=1):
        c["n"] = max_n + i
    for c in kept:
        c.pop("_src", None)

    # 5. косметика: убрать скобочные пояснения из латиницы, схлопнуть пробелы,
    #    починить мусорные имена.
    name_fix = {44: {"name": "Пилгерштофф Мерцен", "latin": "Pilgerstoff Märzen"}}
    for c in kept:
        if c.get("latin"):
            c["latin"] = re.sub(r"\s*\([^)]*\)", "", c["latin"]).strip()
        if c.get("name"):
            c["name"] = re.sub(r"\s+", " ", c["name"]).strip()
        if c["id"] in name_fix:
            c.update(name_fix[c["id"]])

    json.dump(kept, open(CARDS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # отчёт
    buf = io.StringIO()
    buf.write(f"Было: {len(catalog)} | новых из ресёрча: {len(new_cards)} | "
              f"дублей отброшено: {len(dropped)} | добавлено: {len(survivors_new)} | "
              f"ИТОГО: {len(kept)}\n")
    buf.write(f"Цены подтянуты у новых: {priced}/{len(new_cards)}\n\n")
    buf.write("--- ОТБРОШЕННЫЕ ДУБЛИ (новинка -> в какую карточку влита) ---\n")
    for lose, win in sorted(dropped):
        buf.write(f"   «{lose}» -> «{win}»\n")
    buf.write("\n--- ДОБАВЛЕНЫ (новые карточки) ---\n")
    for c in survivors_new:
        r = c["ratings"]
        pr = "/".join(str(c.get(k) if c.get(k) is not None else "—") for k in ("p025", "p04", "p05"))
        buf.write(f"   n{c['n']:>3} {c['name'][:26]:26s} {c['style'][:16]:16s} {c['abv']:>4}% "
                  f"g{r['gor']}p{r['plot']}c{r['cvet']} {pr}  {', '.join(c['tags'])}\n")
    open(REPORT, "w", encoding="utf-8").write(buf.getvalue())
    print(f"[ok] было {len(catalog)} -> стало {len(kept)} (добавлено {len(survivors_new)}, "
          f"дублей {len(dropped)}, цены {priced}) -> {CARDS}")
    print(f"[ok] отчёт -> {REPORT}")


if __name__ == "__main__":
    main()
