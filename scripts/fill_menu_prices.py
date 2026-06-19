"""
Первичная заливка цен в data/menu_cards.json из текущих продаж iiko (та же логика,
что у серверной кнопки «Обновить цены» — core.menu_pricing.refresh_prices).

По умолчанию читает кэш data/cache/menu_prices_raw_v2.json (без обращения к iiko).
Флаг --live тянет свежие данные из iiko.

Запуск: py -3 scripts/fill_menu_prices.py          # из кэша
        py -3 scripts/fill_menu_prices.py --live   # свежие из iiko
"""
import os
import sys
import json
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import menu_pricing as mp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS = os.path.join(ROOT, "data", "menu_cards.json")
CACHE = os.path.join(ROOT, "data", "cache", "menu_prices_raw_v2.json")
REPORT = os.path.join(ROOT, "data", "_price_coverage.txt")


def main():
    live = "--live" in sys.argv
    cards = json.load(open(CARDS, encoding="utf-8"))
    summary = mp.refresh_prices(
        cards,
        date_from="2026-03-01" if not live else None,
        date_to_incl="2026-06-19" if not live else None,
        cache_path=CACHE,
        use_cache=not live,
    )
    json.dump(cards, open(CARDS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    upd = {u["id"]: u for u in summary["updated"]}
    buf = io.StringIO()
    w = buf.write
    w(f"ЦЕНЫ из iiko {summary['date_from']}..{summary['date_to']} "
      f"({'LIVE' if live else 'cache'})\n")
    w(f"Совпало: {summary['matched']}/{summary['total']} карточек\n\n")
    w("--- СОВПАЛИ (карточка -> сорт iiko) ---\n")
    for c in sorted(cards, key=lambda x: x.get("n") or 0):
        if c["id"] in upd:
            u = upd[c["id"]]
            ch = ", ".join(f"{k}:{v['old']}->{v['new']}" for k, v in u["changed"].items()) or "без изменений"
            w(f"  id{c['id']:>3} {c['name'][:24]:24s} <- «{u['iiko_name']}» (score {u['score']})  [{ch}]\n")
    w("\n--- НЕ совпали (сохранили прежнюю цену; вероятно не в текущем меню) ---\n")
    for c in sorted(cards, key=lambda x: x.get("n") or 0):
        if c["id"] not in upd:
            tap = f"кран{c['tap']}" if c.get("tap") else "lib"
            pr = "/".join(str(c.get(k) if c.get(k) is not None else "—") for k in ("p025", "p04", "p05"))
            w(f"  id{c['id']:>3} [{tap}] {c['name'][:24]:24s}  prices={pr}\n")
    open(REPORT, "w", encoding="utf-8").write(buf.getvalue())
    print(f"[ok] matched {summary['matched']}/{summary['total']} -> {CARDS}")
    print(f"[ok] coverage report -> {REPORT}")


if __name__ == "__main__":
    main()
