# -*- coding: utf-8 -*-
"""Генерация docs/iiko-api/_toc.json — названия и иерархия статей iiko API.

Зачем отдельный скрипт: markdown-эндпоинт портала (?action=getMarkdown) отдаёт
только тело статьи без её названия, а TOC-эндпоинты ClickHelp закрыты логином
(401/405). Названия и дерево разделов есть только в SPA-странице портала,
поэтому страница рендерится в headless Chrome и дерево забирается из DOM-дампа
(embedded JSON: узлы {"t": название, "c": дети, "vals": {"e": slug}}).

Требует установленный Google Chrome.

Запуск из корня репозитория:
    py -3 scripts/fetch_iiko_api_toc.py

Результат: docs/iiko-api/_toc.json — {slug: {title, path, order}},
где path — путь разделов портала, order — порядок обхода дерева.
INDEX.md собирает scripts/fetch_iiko_api_docs.py, читая этот файл.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SECTION = "api-documentations"
# Любая статья раздела: SPA рендерит полное дерево публикации на каждой странице
ENTRY_URL = f"https://ru.iiko.help/articles/#!{SECTION}/rukovodstvo-po-nachalu-raboty"

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "docs" / "iiko-api" / "_toc.json"

CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]
# 20 секунд виртуального времени — SPA успевает загрузить дерево публикации
VIRTUAL_TIME_BUDGET_MS = 20000


def dump_dom() -> str:
    chrome = next((p for p in CHROME_CANDIDATES if p.exists()), None)
    if chrome is None:
        raise SystemExit("Google Chrome не найден: " + ", ".join(map(str, CHROME_CANDIDATES)))
    proc = subprocess.run(
        [
            str(chrome),
            "--headless=new",
            "--disable-gpu",
            "--dump-dom",
            f"--virtual-time-budget={VIRTUAL_TIME_BUDGET_MS}",
            ENTRY_URL,
        ],
        capture_output=True,
        timeout=120,
    )
    html = proc.stdout.decode("utf-8", errors="replace")
    if len(html) < 100_000:
        raise SystemExit(f"подозрительно маленький дамп ({len(html)} байт) — SPA не загрузился?")
    return html


def extract_tree(html: str) -> list:
    """Самый большой валидный JSON-массив узлов вида [{"id":"...","t":"...",...}]."""
    decoder = json.JSONDecoder()
    best = None
    for m in re.finditer(r'\[\{"id":"\d+","t":"', html):
        try:
            obj, _ = decoder.raw_decode(html, m.start())
        except json.JSONDecodeError:
            continue
        size = len(json.dumps(obj))
        if best is None or size > best[0]:
            best = (size, obj)
    if best is None:
        raise SystemExit("дерево TOC не найдено в дампе — формат портала изменился?")
    return best[1]


def main() -> int:
    print(f"Рендер: {ENTRY_URL}")
    html = dump_dom()
    tree = extract_tree(html)

    result: dict[str, dict] = {}
    counter = iter(range(1, 10_000))

    def walk(nodes: list, path: list[str]) -> None:
        for node in nodes:
            title = re.sub(r"\s+", " ", node.get("t", "")).strip()
            slug = (node.get("vals") or {}).get("e")
            if slug:
                result[slug] = {"title": title, "path": path, "order": next(counter)}
            walk(node.get("c") or [], path + [title])

    walk(tree, [])
    if not result:
        raise SystemExit("в дереве нет ни одной статьи со slug")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"Готово: {len(result)} статей -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
