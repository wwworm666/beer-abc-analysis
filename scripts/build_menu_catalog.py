"""
Строит ЕДИНЫЙ каталог карточек меню из двух исторически раздельных источников:

  menu_tool/data/menu_items.json  — библиотека (100 карточек: имя/пивоварня/стиль/
                                    крепость, но у 99 нет вкусов/тегов/шкал; есть дубли)
  menu_tool/data/menu_taps.json   — 21 карточка текущих кранов (полностью заполнены)

Результат:
  data/menu_cards.json            — канонический объединённый каталог (seed для /kultura)
  data/menu_research_input.json   — карточки, которым нужен веб-ресёрч (нет тегов/шкал)
  data/_catalog_report.txt        — человекочитаемый отчёт (UTF-8; консоль рвёт кириллицу)

Что делает:
  1. Дедуп библиотеки: карточки с одинаковым именем (нормализованным) сливаются в одну
     (берём самую заполненную, недостающие поля добиваем из дублей).
  2. Слияние кранов: кран, совпавший с карточкой библиотеки по латинице+пивоварне или
     имени, сливается в неё (данные крана свежее) и помечается tap=<номер>. Остальные
     краны добавляются новыми карточками.
  3. Единая схема: один вариант разлива 0,25/0,4/0,5 (p03 удалён). Поле tap = номер крана,
     если сорт сейчас на кране, иначе null. n (число на карточке) = tap для кранов, иначе
     прежний номер библиотеки.

Запуск: py -3 scripts/build_menu_catalog.py
"""
import os
import re
import sys
import json
import io

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIB_IN = os.path.join(ROOT, "menu_tool", "data", "menu_items.json")
TAPS_IN = os.path.join(ROOT, "menu_tool", "data", "menu_taps.json")
OUT = os.path.join(ROOT, "data", "menu_cards.json")
RESEARCH_OUT = os.path.join(ROOT, "data", "menu_research_input.json")
REPORT = os.path.join(ROOT, "data", "_catalog_report.txt")

PRICE_FIELDS = ("p025", "p04", "p05")  # один вариант: 0,25 / 0,4 / 0,5 (p03 убран)

# Семантические дубли, не пойманные точным сравнением имён (кириллица/латиница,
# разное написание, суффиксы). Победитель (winner) остаётся, проигравший (loser)
# вливается в него (добивает пустые поля) и удаляется. Победитель кранов = текущая
# правда; цены всё равно обновятся из iiko на следующем шаге.
# Селектор: {"tap": N} либо {"name": "<норм. имя>"}. Подтверждено ревью
# data/_dupe_candidates.txt (см. scripts/find_menu_dupes.py).
SEMANTIC_DUPES = [
    ({"tap": 23}, {"name": "коммерцинрат"}),       # Riegele Commerzienrat (Privat)
    ({"name": "бланш"}, {"name": "бланш де лютин"}),  # Blanche de Lutin (краткое имя)
    ({"tap": 2}, {"name": "гульден драак"}),       # Gulden Draak (708)
    ({"tap": 17}, {"name": "cherry ruby"}),        # Konix Cherry Ruby
    ({"tap": 18}, {"name": "палм"}),               # Palm (Speciale)
]


def _match(card, sel):
    if "tap" in sel:
        return card.get("tap") == sel["tap"]
    if "name" in sel:
        return norm_name(card.get("name")) == sel["name"]
    return False


def apply_semantic_dupes(catalog):
    """Слить подтверждённые семантические дубли. Возвращает (catalog, actions)."""
    drop = set()
    actions = []
    for win_sel, lose_sel in SEMANTIC_DUPES:
        winner = next((c for c in catalog if _match(c, win_sel) and id(c) not in drop), None)
        loser = next((c for c in catalog if _match(c, lose_sel) and c is not winner), None)
        if winner is None or loser is None:
            actions.append((str(win_sel), str(lose_sel), "НЕ НАЙДЕНО"))
            continue
        merge_fill(winner, loser)
        drop.add(id(loser))
        actions.append((winner["name"], loser["name"], f"id{loser.get('id')} -> id{winner.get('id')}"))
    catalog = [c for c in catalog if id(c) not in drop]
    return catalog, actions


def norm_name(s):
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s]", "", s, flags=re.U)
    s = re.sub(r"\s+", " ", s)
    return s


def norm_key(s):
    """Ключ для сопоставления (только буквы/цифры, без пробелов)."""
    return re.sub(r"[^\w]", "", (s or "").strip().lower(), flags=re.U)


def filled(v):
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def tags_filled(c):
    return len([t for t in (c.get("tags") or []) if str(t).strip()]) > 0


def ratings_filled(c):
    r = c.get("ratings") or {}
    return any(int(r.get(k) or 0) > 0 for k in ("gor", "plot", "cvet"))


def richness(c):
    """Сколько значимых полей заполнено — для выбора «лучшей» из дублей."""
    score = 0
    for k in ("name", "latin", "brewery", "country", "style", "abv"):
        score += 1 if filled(c.get(k)) else 0
    score += 2 if tags_filled(c) else 0
    score += 2 if ratings_filled(c) else 0
    score += sum(1 for p in PRICE_FIELDS if filled(c.get(p)))
    return score


def clean_ratings(r):
    r = r or {}
    out = {}
    for k in ("gor", "plot", "cvet"):
        try:
            out[k] = max(0, min(5, int(r.get(k) or 0)))
        except (TypeError, ValueError):
            out[k] = 0
    return out


def base_card(c, tap=None):
    """Привести запись к канонической схеме (один вариант разлива, поле tap)."""
    return {
        "id": c.get("id"),
        "n": int(c.get("n") or 0),
        "tap": tap,
        "name": (c.get("name") or "").strip(),
        "latin": (c.get("latin") or "").strip(),
        "brewery": (c.get("brewery") or "").strip(),
        "country": (c.get("country") or "").strip(),
        "style": (c.get("style") or "").strip(),
        "abv": str(c.get("abv") or "").strip(),
        "tags": [str(t).strip() for t in (c.get("tags") or []) if str(t).strip()][:3],
        "ratings": clean_ratings(c.get("ratings")),
        "p025": c.get("p025"),
        "p04": c.get("p04"),
        "p05": c.get("p05"),
    }


def merge_fill(base, other):
    """Добить пустые поля base значениями из other (base приоритетнее)."""
    for k in ("name", "latin", "brewery", "country", "style", "abv"):
        if not filled(base.get(k)) and filled(other.get(k)):
            base[k] = other[k]
    if not tags_filled(base) and tags_filled(other):
        base["tags"] = other["tags"]
    if not ratings_filled(base) and ratings_filled(other):
        base["ratings"] = other["ratings"]
    for p in PRICE_FIELDS:
        if not filled(base.get(p)) and filled(other.get(p)):
            base[p] = other[p]
    return base


def dedup_library(lib):
    """Слить карточки библиотеки с одинаковым нормализованным именем."""
    groups = {}
    order = []
    for c in lib:
        k = norm_name(c.get("name"))
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(c)
    merged = []
    actions = []
    for k in order:
        members = groups[k]
        if len(members) == 1:
            merged.append(base_card(members[0]))
            continue
        members_sorted = sorted(members, key=lambda c: (-richness(c), c.get("id", 1e9)))
        winner = base_card(members_sorted[0])
        for loser in members_sorted[1:]:
            merge_fill(winner, base_card(loser))
        actions.append((winner["name"], [m.get("id") for m in members], winner["id"]))
        merged.append(winner)
    return merged, actions


def main():
    lib = json.load(open(LIB_IN, encoding="utf-8"))
    taps = json.load(open(TAPS_IN, encoding="utf-8"))

    merged_lib, dedup_actions = dedup_library(lib)

    # индексы библиотеки для сопоставления кранов
    by_latin = {}
    by_name = {}
    for c in merged_lib:
        if norm_key(c.get("latin")):
            by_latin.setdefault(norm_key(c["latin"]), c)
        by_name.setdefault(norm_name(c.get("name")), c)

    max_id = max([c.get("id") or 0 for c in merged_lib], default=0)
    tap_merges = []
    tap_new = []
    for t in taps:
        tnum = int(t.get("n") or t.get("tap") or 0)
        cand = base_card(t, tap=tnum)
        # сопоставление с библиотекой: латиница+пивоварня, затем имя
        match = None
        lk = norm_key(cand["latin"])
        if lk and lk in by_latin and norm_key(by_latin[lk].get("brewery")) == norm_key(cand.get("brewery")):
            match = by_latin[lk]
        if match is None:
            nm = norm_name(cand["name"])
            if nm in by_name:
                match = by_name[nm]
        if match is not None:
            # данные крана свежее -> переносим в карточку библиотеки, помечаем краном
            match["tap"] = tnum
            match["n"] = tnum
            for k in ("name", "latin", "brewery", "country", "style", "abv"):
                if filled(cand.get(k)):
                    match[k] = cand[k]
            if tags_filled(cand):
                match["tags"] = cand["tags"]
            if ratings_filled(cand):
                match["ratings"] = cand["ratings"]
            for p in PRICE_FIELDS:
                if filled(cand.get(p)):
                    match[p] = cand[p]
            tap_merges.append((tnum, cand["name"], match["id"]))
        else:
            max_id += 1
            cand["id"] = max_id
            cand["n"] = tnum  # на карточке крана № = номер крана
            tap_new.append(cand)

    catalog = merged_lib + tap_new
    catalog, sem_actions = apply_semantic_dupes(catalog)
    # порядок: сначала краны по номеру, потом библиотека по n
    catalog.sort(key=lambda c: (0, c["tap"]) if c.get("tap") else (1, c.get("n") or 0))

    # гарантируем уникальные id
    seen_ids = set()
    nid = max([c.get("id") or 0 for c in catalog], default=0)
    for c in catalog:
        if c.get("id") in seen_ids or not c.get("id"):
            nid += 1
            c["id"] = nid
        seen_ids.add(c["id"])

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(catalog, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # вход для ресёрча: всё, где нет тегов ИЛИ нет шкал
    need = [c for c in catalog if not (tags_filled(c) and ratings_filled(c))]
    research_in = [{
        "id": c["id"], "name": c["name"], "latin": c["latin"],
        "brewery": c["brewery"], "country": c["country"],
        "style": c["style"], "abv": c["abv"],
        "has_tags": tags_filled(c), "has_ratings": ratings_filled(c),
    } for c in need]
    json.dump(research_in, open(RESEARCH_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # читаемый отчёт (UTF-8)
    buf = io.StringIO()
    w = buf.write
    w(f"КАТАЛОГ: {len(catalog)} карточек (краны {sum(1 for c in catalog if c.get('tap'))}, "
      f"библиотека {sum(1 for c in catalog if not c.get('tap'))})\n")
    w(f"Дедуп библиотеки: слито {len(dedup_actions)} групп дублей\n")
    for nm, ids, keep in dedup_actions:
        w(f"   дубль '{nm}': ids {ids} -> оставлен id {keep}\n")
    w(f"Слияние кранов с библиотекой: {len(tap_merges)}\n")
    for tn, nm, mid in tap_merges:
        w(f"   кран #{tn} '{nm}' -> слит в библиотечную id {mid}\n")
    w(f"Семантические дубли (слиты вручную по ревью): {len([a for a in sem_actions if 'НЕ' not in a[2]])}\n")
    for win, lose, info in sem_actions:
        w(f"   '{lose}' -> '{win}'  ({info})\n")
    w(f"Новых карточек из кранов: {len(tap_new)}\n")
    w(f"Нужен ресёрч (нет тегов/шкал): {len(need)} карточек\n")
    missing_price = [c for c in catalog if not all(filled(c.get(p)) for p in PRICE_FIELDS)]
    w(f"Без полной тройки цен: {len(missing_price)} карточек\n")
    w("\n--- ВЕСЬ КАТАЛОГ ---\n")
    for c in catalog:
        tg = ", ".join(c["tags"]) if c["tags"] else "-"
        r = c["ratings"]
        tap = f"кран{c['tap']}" if c.get("tap") else "  -  "
        pr = "/".join(str(c.get(p) if c.get(p) is not None else "—") for p in PRICE_FIELDS)
        w(f"id{c['id']:>3} n{c['n']:>3} {tap} | {c['name'][:24]:24s} | "
          f"{c['style'][:16]:16s} {c['abv']:>4} | g{r['gor']}p{r['plot']}c{r['cvet']} | "
          f"{pr:>14} | {tg}\n")
    open(REPORT, "w", encoding="utf-8").write(buf.getvalue())

    print(f"[ok] {len(catalog)} cards -> {OUT}")
    print(f"[ok] research input {len(need)} -> {RESEARCH_OUT}")
    print(f"[ok] report -> {REPORT}")


if __name__ == "__main__":
    main()
