"""
Ищет СЕМАНТИЧЕСКИЕ дубли в data/menu_cards.json, которые не ловит точное сравнение
имён: один и тот же сорт записан по-разному (кириллица/латиница, разное написание,
суффиксы вроде «Приват»/«708»). Сигналы: транслитерация имени+латиницы (Jaccard по
токенам) + совпадение крепости + близость тройки цен.

Не меняет данные — печатает кандидатов в data/_dupe_candidates.txt для ревью.
Запуск: py -3 scripts/find_menu_dupes.py
"""
import os
import re
import json
import itertools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "data", "menu_cards.json")
OUT = os.path.join(ROOT, "data", "_dupe_candidates.txt")

# грубая кириллица -> латиница (для сопоставления, не для отображения)
TR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
# частые англ<->рус вариации звуков, чтобы «cherry»~«cherri», «draak»~«drak»
SOFT = [("ck", "k"), ("kk", "k"), ("aa", "a"), ("ee", "e"), ("oo", "u"),
        ("yu", "u"), ("ya", "a"), ("yo", "o"), ("ph", "f"), ("th", "t"),
        ("y", "i"), ("zh", "z"), ("kh", "h"), ("ie", "i"), ("ei", "i")]


def translit(s):
    s = (s or "").lower()
    out = "".join(TR.get(ch, ch) for ch in s)
    out = re.sub(r"[^a-z0-9 ]", " ", out)
    for a, b in SOFT:
        out = out.replace(a, b)
    return re.sub(r"\s+", " ", out).strip()


STOP = {"ipa", "ale", "el", "lager", "lager", "beer", "bir", "the", "de", "and"}


def tokens(card):
    raw = translit(card.get("name", "")) + " " + translit(card.get("latin", ""))
    toks = {t for t in raw.split() if len(t) >= 3 and t not in STOP}
    return toks


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def price_close(c1, c2):
    fs = ("p025", "p04", "p05")
    diffs = []
    for f in fs:
        a, b = c1.get(f), c2.get(f)
        if a and b:
            diffs.append(abs(a - b) / max(a, b))
    if not diffs:
        return None
    return sum(diffs) / len(diffs)  # средняя относительная разница


def abv_eq(c1, c2):
    def norm(v):
        return str(v or "").replace(",", ".").strip()
    return norm(c1.get("abv")) == norm(c2.get("abv")) and norm(c1.get("abv")) != ""


def main():
    cards = json.load(open(CARDS, encoding="utf-8"))
    toks = {c["id"]: tokens(c) for c in cards}
    cand = []
    for a, b in itertools.combinations(cards, 2):
        j = jaccard(toks[a["id"]], toks[b["id"]])
        pc = price_close(a, b)
        ab = abv_eq(a, b)
        # сигнал дубля: заметное пересечение токенов, усиленное равной крепостью/ценой
        score = j
        if ab:
            score += 0.25
        if pc is not None and pc < 0.05:
            score += 0.25
        if j >= 0.34 or (j >= 0.25 and ab) or (j >= 0.2 and pc is not None and pc < 0.04 and ab):
            cand.append((score, j, ab, pc, a, b))
    cand.sort(key=lambda x: -x[0])

    lines = [f"КАНДИДАТЫ В ДУБЛИ: {len(cand)} пар (порог по токенам/крепости/цене)\n"]
    for score, j, ab, pc, a, b in cand:
        ta = f"кран{a['tap']}" if a.get("tap") else "lib"
        tb = f"кран{b['tap']}" if b.get("tap") else "lib"
        pca = "n/a" if pc is None else f"{pc*100:.0f}%"
        lines.append(
            f"score={score:.2f} jac={j:.2f} abv_eq={int(ab)} priceΔ={pca}\n"
            f"   [{ta}] id{a['id']:>3} {a['name']:<26} {a.get('abv',''):>5} "
            f"{a.get('p025')}/{a.get('p04')}/{a.get('p05')}  «{a.get('latin','')}»\n"
            f"   [{tb}] id{b['id']:>3} {b['name']:<26} {b.get('abv',''):>5} "
            f"{b.get('p025')}/{b.get('p04')}/{b.get('p05')}  «{b.get('latin','')}»\n"
        )
    open(OUT, "w", encoding="utf-8").write("\n".join(lines))
    print(f"[ok] {len(cand)} candidate pairs -> {OUT}")


if __name__ == "__main__":
    main()
