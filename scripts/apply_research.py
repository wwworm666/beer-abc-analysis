"""
Вносит результат веб-ресёрча (data/menu_research_output.json: tags + шкалы
gor/plot/cvet по id) в data/menu_cards.json. Применяется ТОЛЬКО к карточкам,
присутствующим в ресёрче (это библиотека, которой не хватало вкусов/тегов);
21 кран и заранее заполненные карточки не трогаются.

Запуск: py -3 scripts/apply_research.py
"""
import os
import sys
import json
import io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "data", "menu_cards.json")
RESEARCH = os.path.join(ROOT, "data", "menu_research_output.json")
REPORT = os.path.join(ROOT, "data", "_research_applied.txt")


def main():
    cards = json.load(open(CARDS, encoding="utf-8"))
    research = {r["id"]: r for r in json.load(open(RESEARCH, encoding="utf-8"))}
    by_id = {c["id"]: c for c in cards}

    applied, missing_card = [], []
    for rid, r in research.items():
        c = by_id.get(rid)
        if not c:
            missing_card.append(rid)
            continue
        c["tags"] = [str(t).strip() for t in (r.get("tags") or [])][:3]
        c["ratings"] = {
            "gor": int(r.get("gor") or 0),
            "plot": int(r.get("plot") or 0),
            "cvet": int(r.get("cvet") or 0),
        }
        applied.append(rid)

    json.dump(cards, open(CARDS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # карточки всё ещё без тегов/шкал?
    def empty(c):
        tg = [t for t in (c.get("tags") or []) if str(t).strip()]
        r = c.get("ratings") or {}
        rated = any(int(r.get(k) or 0) > 0 for k in ("gor", "plot", "cvet"))
        return (not tg) or (not rated)
    still = [c for c in cards if empty(c)]

    buf = io.StringIO()
    buf.write(f"Ресёрч внесён: {len(applied)} карточек\n")
    buf.write(f"confidence: ")
    from collections import Counter
    cc = Counter(research[i].get("confidence") for i in applied)
    buf.write(", ".join(f"{k}={v}" for k, v in cc.items()) + "\n")
    if missing_card:
        buf.write(f"ВНИМАНИЕ: research id без карточки: {missing_card}\n")
    buf.write(f"Карточек всё ещё без тегов/шкал: {len(still)}\n")
    for c in still:
        buf.write(f"   id{c['id']} {c.get('name')}\n")
    buf.write("\n--- low/medium confidence (стоит перепроверить вручную) ---\n")
    for i in applied:
        r = research[i]
        if r.get("confidence") != "high":
            c = by_id[i]
            buf.write(f"   [{r['confidence']}] id{i} {c.get('name'):<22} "
                      f"tags={c['tags']} g{c['ratings']['gor']}p{c['ratings']['plot']}c{c['ratings']['cvet']}\n")
    open(REPORT, "w", encoding="utf-8").write(buf.getvalue())
    print(f"[ok] applied research to {len(applied)} cards -> {CARDS}")
    print(f"[ok] still empty: {len(still)} | report -> {REPORT}")


if __name__ == "__main__":
    main()
