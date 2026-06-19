"""
Готовит список НОВЫХ сортов из data/_draft_sorts_2y.csv (полный ассортимент разливного
за 2 года) для добавления в каталог: отсеивает те, что уже есть в data/menu_cards.json
(сопоставление по транслитерированным токенам имени/латиницы + общий бренд-токен).

Выход:
  data/menu_new_sorts.json — [{id, name_src, portions}] для воркфлоу-ресёрча.

Дедуп здесь грубый (precision важнее): часть близких дублей он пропустит как «новые»,
их добьёт повторный прогон scripts/find_menu_dupes.py после слияния.

Запуск: py -3 scripts/add_csv_sorts.py
"""
import os
import sys
import csv
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.menu_pricing import card_tokens, _STYLE

CARDS = os.path.join(ROOT, "data", "menu_cards.json")
CSV = os.path.join(ROOT, "data", "_draft_sorts_2y.csv")
OUT = os.path.join(ROOT, "data", "menu_new_sorts.json")


def brand(t):
    return t - _STYLE


def main():
    cat = json.load(open(CARDS, encoding="utf-8"))
    cat_toks = [card_tokens(c) for c in cat]
    max_id = max((int(c.get("id") or 0) for c in cat), default=0)

    def matches_existing(name):
        ct = card_tokens({"name": name, "latin": ""})
        if not brand(ct):
            return False  # только стиль -> ненадёжно, считаем новым
        for it in cat_toks:
            if not it:
                continue
            if (ct <= it or it <= ct) and brand(ct & it):
                return True
            if ct and it and len(ct & it) / len(ct | it) >= 0.6 and brand(ct & it):
                return True
        return False

    rows = []
    with open(CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            s = (row.get("Сорт") or "").strip()
            if not s:
                continue
            try:
                portions = int(row.get("Порций") or 0)
            except ValueError:
                portions = 0
            rows.append((s, portions))

    new = []
    nid = max_id
    for name, portions in rows:
        if matches_existing(name):
            continue
        nid += 1
        new.append({"id": nid, "name_src": name, "portions": portions})

    new.sort(key=lambda x: -x["portions"])
    json.dump(new, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"CSV сортов: {len(rows)} | в каталоге: {len(rows)-len(new)} | НОВЫХ: {len(new)}")
    print(f"[ok] -> {OUT} (id с {max_id+1})")


if __name__ == "__main__":
    main()
