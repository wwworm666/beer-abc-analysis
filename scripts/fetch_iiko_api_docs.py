# -*- coding: utf-8 -*-
"""Загрузка документации iiko API с портала ru.iiko.help в docs/iiko-api/.

Источник истины — портал ru.iiko.help (движок ClickHelp).
Скрипт скачивает все статьи раздела api-documentations в формате markdown
и генерирует индекс INDEX.md.

Как работает:
1. Берёт список статей из sitemap:
   https://ru.iiko.help/sitemaps/sitemap_publication_api-documentations.xml
2. Для каждого slug скачивает markdown:
   https://ru.iiko.help/helper/articles/api-documentations/{slug}/?action=getMarkdown
3. Сохраняет в docs/iiko-api/{slug}.md (содержимое файла = ровно то,
   что отдаёт портал, без добавок — чтобы повторный запуск давал чистый diff).
4. Пишет docs/iiko-api/INDEX.md. Названия статей и дерево разделов берёт из
   docs/iiko-api/_toc.json (генерируется scripts/fetch_iiko_api_toc.py;
   markdown-эндпоинт названий статей не отдаёт). Без _toc.json — плоский
   список, название = первый заголовок статьи.

Запуск из корня репозитория:
    py -3 scripts/fetch_iiko_api_docs.py

Повторный запуск безопасен: файлы перезаписываются, удалённые из портала
статьи остаются на диске (скрипт сообщает о них, но не удаляет).
"""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

SECTION = "api-documentations"
SITEMAP_URL = f"https://ru.iiko.help/sitemaps/sitemap_publication_{SECTION}.xml"
ARTICLE_MD_URL = "https://ru.iiko.help/helper/articles/{section}/{slug}/?action=getMarkdown"
ARTICLE_WEB_URL = "https://ru.iiko.help/articles/#!{section}/{slug}"

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "docs" / "iiko-api"

# 3 попытки на статью: портал иногда отвечает 5xx под нагрузкой
RETRIES = 3
RETRY_DELAY_SEC = 2
# 8 параллельных запросов — достаточно быстро и не создаёт нагрузку на портал
WORKERS = 8
TIMEOUT_SEC = 45


def fetch_sitemap() -> list[tuple[str, str]]:
    """Возвращает список (slug, lastmod) из sitemap раздела."""
    resp = requests.get(SITEMAP_URL, timeout=TIMEOUT_SEC)
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig")
    entries = re.findall(
        r"<loc>https://ru\.iiko\.help/articles/#!" + re.escape(SECTION) + r"/([^<]+)</loc>"
        r"\s*<lastmod>([^<]+)</lastmod>",
        text,
    )
    if not entries:
        raise RuntimeError("sitemap не распарсился — формат изменился?")
    return entries


def fetch_article(slug: str) -> str:
    """Скачивает markdown статьи. Бросает исключение, если пришёл HTML/пустота."""
    url = ARTICLE_MD_URL.format(section=SECTION, slug=slug)
    last_err: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT_SEC)
            resp.raise_for_status()
            text = resp.content.decode("utf-8-sig").strip()
            if not text:
                raise RuntimeError("пустой ответ")
            lowered = text[:300].lower()
            if "<!doctype" in lowered or "<html" in lowered:
                raise RuntimeError("пришёл HTML вместо markdown (логин-страница?)")
            return text
        except Exception as exc:  # noqa: BLE001 - ретраим любую сетевую ошибку
            last_err = exc
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY_SEC * attempt)
    raise RuntimeError(f"{slug}: не скачалась после {RETRIES} попыток: {last_err}")


def extract_title(markdown: str, slug: str) -> str:
    """Первый заголовок статьи; если его нет — slug."""
    for line in markdown.splitlines():
        m = re.match(r"#{1,6}\s+(.+)", line.strip())
        if m:
            return m.group(1).strip()
    return slug


def load_toc() -> dict[str, dict]:
    """slug -> {title, path, order} из _toc.json; пусто, если файла нет."""
    toc_path = OUT_DIR / "_toc.json"
    if not toc_path.exists():
        return {}
    return json.loads(toc_path.read_text(encoding="utf-8"))


def build_index_tree(results: dict[str, dict], toc: dict[str, dict]) -> list[str]:
    """Иерархический список в порядке оглавления портала."""
    lines: list[str] = []
    in_toc = [slug for slug in results if slug in toc]
    in_toc.sort(key=lambda s: toc[s]["order"])
    emitted_path: list[str] = []
    for slug in in_toc:
        info, node = results[slug], toc[slug]
        path = node["path"]
        # Закрываем/открываем разделы: печатаем компоненты пути, которых ещё не было
        common = 0
        while common < min(len(emitted_path), len(path)) and emitted_path[common] == path[common]:
            common += 1
        for depth in range(common, len(path)):
            lines.append("  " * depth + f"- **{path[depth]}**")
        emitted_path = path
        indent = "  " * len(path)
        title = node["title"].replace("|", "\\|")
        lines.append(f"{indent}- [{title}]({slug}.md) — обновлено {info['lastmod'][:10]}")

    missing = sorted(set(results) - set(toc))
    if missing:
        lines += ["", "## Вне оглавления портала", ""]
        for slug in missing:
            lines.append(f"- [{results[slug]['title']}]({slug}.md) — обновлено {results[slug]['lastmod'][:10]}")
    return lines


def build_index_flat(results: dict[str, dict]) -> list[str]:
    """Плоская таблица — фоллбэк, когда _toc.json не сгенерирован."""
    lines = [
        "| Статья | Файл | Обновлено на портале |",
        "|--------|------|----------------------|",
    ]
    for slug in sorted(results, key=lambda s: results[s]["title"].lower()):
        info = results[slug]
        web_url = ARTICLE_WEB_URL.format(section=SECTION, slug=slug)
        title = info["title"].replace("|", "\\|")
        lines.append(f"| [{title}]({web_url}) | [{slug}.md]({slug}.md) | {info['lastmod'][:10]} |")
    return lines


def main() -> int:
    print(f"Sitemap: {SITEMAP_URL}")
    entries = fetch_sitemap()
    print(f"Статей в разделе {SECTION}: {len(entries)}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    failures: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        future_to_slug = {pool.submit(fetch_article, slug): (slug, lastmod) for slug, lastmod in entries}
        for future in as_completed(future_to_slug):
            slug, lastmod = future_to_slug[future]
            try:
                text = future.result()
            except Exception as exc:  # noqa: BLE001
                failures[slug] = str(exc)
                print(f"  FAIL {slug}: {exc}")
                continue
            (OUT_DIR / f"{slug}.md").write_text(text + "\n", encoding="utf-8")
            results[slug] = {"title": extract_title(text, slug), "lastmod": lastmod}
            print(f"  ok   {slug}")

    # Файлы, которых больше нет в sitemap (не удаляем — только предупреждаем)
    known = {f"{slug}.md" for slug, _ in entries} | {"INDEX.md"}
    orphans = sorted(p.name for p in OUT_DIR.glob("*.md") if p.name not in known)

    toc = load_toc()
    index_lines = [
        "# Документация iiko API (локальная копия)",
        "",
        f"Источник: раздел `{SECTION}` портала ru.iiko.help.",
        "Файлы — точные копии markdown статей портала, без правок.",
        "",
        "Пересинхронизация: `py -3 scripts/fetch_iiko_api_docs.py` из корня репозитория",
        "(названия/дерево разделов: `py -3 scripts/fetch_iiko_api_toc.py`, нужен Chrome).",
        "",
        f"Всего статей: {len(results)}",
        "",
    ]
    index_lines += build_index_tree(results, toc) if toc else build_index_flat(results)

    if failures:
        index_lines += ["", "## Не скачались", ""]
        index_lines += [f"- `{slug}` — {err}" for slug, err in sorted(failures.items())]

    (OUT_DIR / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    print(f"\nГотово: {len(results)} ok, {len(failures)} fail -> {OUT_DIR}")
    if orphans:
        print(f"В папке остались файлы, которых нет в sitemap ({len(orphans)}): " + ", ".join(orphans))
    if failures:
        print("ОШИБКИ:")
        for slug, err in sorted(failures.items()):
            print(f"  {slug}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
