"""Отчёт/применение BJCP-дескрипторов на уровне стиля.

Вход: data/style_taste_output.json — массив {style, bjcp_code, bjcp_ru, bjcp_en,
bjcp_desc, prior_desc, final, better, note} (сохранить сюда возврат воркфлоу
style-taste-bjcp).

Режимы:
  py -3 scripts/apply_style_taste.py            # отчёт прежнее->BJCP->итог
  py -3 scripts/apply_style_taste.py --build     # собрать data/style_descriptors.json
                                                 # (style -> {bjcp_code, bjcp_ru, rec=final})
"""
import json, io, sys, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = "--build" in sys.argv
res = json.load(open(ROOT / "data/style_taste_output.json", encoding="utf-8"))
cards = json.load(open(ROOT / "data/menu_cards.json", encoding="utf-8"))

from collections import Counter
counts = Counter(c["style"] for c in cards)
res.sort(key=lambda r: (-counts.get(r["style"], 0), r["style"].lower()))

same = chg = 0
print("=== СТИЛЬ: прежнее -> BJCP -> ИТОГ ===")
for r in res:
    st = r["style"]; n = counts.get(st, 0)
    prior = " · ".join(r.get("prior_desc") or [])
    bjcp = " · ".join(r.get("bjcp_desc") or [])
    final = " · ".join(r.get("final") or [])
    code = r.get("bjcp_code", "?"); ru = r.get("bjcp_ru", ""); en = r.get("bjcp_en", "")
    flag = r.get("better", "")
    if (r.get("final") or []) == (r.get("prior_desc") or []):
        same += 1
    else:
        chg += 1
    print(f"\n[{n:>2}] {st}   ->  BJCP {code} {ru} / {en}")
    print(f"      прежнее: {prior}")
    print(f"      BJCP:    {bjcp}")
    print(f"      ИТОГ:    {final}   ({flag})")
    if r.get("note"):
        print(f"      note:    {r['note'][:200]}")

print(f"\nстилей: {len(res)} | итог == прежнего: {same} | изменилось: {chg}")
codes = Counter(r.get("bjcp_code") for r in res)
dups = {c: n for c, n in codes.items() if n > 1 and c != "X1"}
if dups:
    print("\nодин BJCP-код у нескольких стилей (кандидаты на склейку):")
    for c, n in sorted(dups.items()):
        names = [r["style"] for r in res if r.get("bjcp_code") == c]
        print(f"  {c}: {', '.join(names)}")

if BUILD:
    out = {}
    for r in res:
        out[r["style"]] = {
            "bjcp_code": r.get("bjcp_code"),
            "bjcp_ru": r.get("bjcp_ru"),
            "bjcp_en": r.get("bjcp_en"),
            "rec": r.get("final") or [],
        }
    json.dump(out, open(ROOT / "data/style_descriptors.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nсобрано -> data/style_descriptors.json ({len(out)} стилей)")
