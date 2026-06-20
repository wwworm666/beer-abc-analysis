"""Применить результат workflow menu-taste-descriptors к каталогу.

Вход: data/menu_taste_output.json — массив {id, tags[3], rationale, needs_review, note}
(сохранить сюда возврат воркфлоу). Пишет новые tags в data/menu_cards.json и печатает
отчёт old->new: все краны + все needs_review + аномалии (не 3 слова / пробел в слове).

Запуск: py -3 scripts/apply_taste.py            (применить + отчёт)
        py -3 scripts/apply_taste.py --dry      (только отчёт, без записи)
"""
import json, io, sys, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
DRY = "--dry" in sys.argv

cards = json.load(open(ROOT / "data/menu_cards.json", encoding="utf-8"))
res = json.load(open(ROOT / "data/menu_taste_output.json", encoding="utf-8"))
by_id = {c["id"]: c for c in cards}
res_by_id = {r["id"]: r for r in res}

missing = [c["id"] for c in cards if c["id"] not in res_by_id]
anomalies = []   # (id, name, reason, tags)
applied = 0
old_snap = {}

for r in res:
    cid = r["id"]
    c = by_id.get(cid)
    if not c:
        continue
    tags = [str(t).strip() for t in (r.get("tags") or []) if str(t).strip()]
    reasons = []
    if len(tags) != 3:
        reasons.append(f"не 3 слова ({len(tags)})")
    for t in tags:
        if " " in t:
            reasons.append(f"фраза: «{t}»")
    if reasons:
        anomalies.append((cid, c.get("name"), "; ".join(reasons), tags))
    old_snap[cid] = list(c.get("tags") or [])
    if not DRY and 1 <= len(tags) <= 3:
        c["tags"] = tags
        applied += 1

if not DRY:
    json.dump(cards, open(ROOT / "data/menu_cards.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

def line(c, new):
    old = " · ".join(old_snap.get(c["id"], c.get("tags") or []))
    nw = " · ".join(new)
    tap = c.get("tap")
    head = (f"кран {tap:>2}" if tap else f"#{c['id']:>4}")
    print(f"  {head} | {c.get('name',''):<26}")
    print(f"           было:  {old}")
    print(f"           стало: {nw}")

print(f"=== ПРИМЕНЕНО: {applied}/{len(cards)} {'(DRY — не записано)' if DRY else ''}")
if missing:
    print(f"!!! НЕТ результата для {len(missing)} id: {missing[:30]}")
print()

taps = sorted([c for c in cards if c.get("tap")], key=lambda c: c["tap"])
print(f"--- НА КРАНЕ ({len(taps)}) ---")
for c in taps:
    line(c, res_by_id.get(c["id"], {}).get("tags", []))

review = [r for r in res if r.get("needs_review")]
print(f"\n--- needs_review ({len(review)}) — спорные решения агента ---")
for r in sorted(review, key=lambda r: r["id"]):
    c = by_id.get(r["id"])
    if not c:
        continue
    line(c, r.get("tags", []))
    if r.get("note"):
        print(f"           note:  {r['note']}")

if anomalies:
    print(f"\n!!! АНОМАЛИИ ({len(anomalies)}) — проверить вручную:")
    for cid, name, why, tags in anomalies:
        print(f"  #{cid} {name}: {why} -> {tags}")
