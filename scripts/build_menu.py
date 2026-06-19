"""
Единая детерминированная сборка каталога меню (seed для data/menu_cards.json).
Прогоняет три шага по порядку:

  1. build_menu_catalog.py  — дедуп библиотеки + слияние кранов -> скелет каталога
  2. fill_menu_prices.py     — текущие цены из iiko (по умолчанию из кэша; --live = из iiko)
  3. apply_research.py       — вкусы/теги/шкалы из data/menu_research_output.json

Порядок важен: шаг 1 пересобирает menu_cards.json с нуля, поэтому цены (2) и
ресёрч (3) накладываются ПОСЛЕ него. Источники (menu_items.json, menu_taps.json,
menu_research_output.json) — в репозитории, поэтому сборка воспроизводима.

Запуск:  py -3 scripts/build_menu.py          # цены из кэша
         py -3 scripts/build_menu.py --live   # цены свежие из iiko
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = "--live" in sys.argv


def run(script, *args):
    cmd = [sys.executable, os.path.join(HERE, script), *args]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    print(f"\n=== {script} {' '.join(args)} ===")
    r = subprocess.run(cmd, env=env)
    if r.returncode != 0:
        print(f"[FAIL] {script} exited {r.returncode}")
        sys.exit(r.returncode)


def main():
    run("build_menu_catalog.py")
    run("fill_menu_prices.py", *(["--live"] if LIVE else []))
    run("apply_research.py")
    print("\n[done] data/menu_cards.json пересобран (каталог + цены + ресёрч)")


if __name__ == "__main__":
    main()
