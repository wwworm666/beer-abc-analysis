"""Build explicit iiko GUID -> Untappd beer ID links and a separate review queue.

Historical name matches are suggestions only. Only an explicit reviewed decision
with a recorded primary source can create a usable link. See docs/untappd-links.md.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlparse
import uuid

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "output/kegs-2026-09-20/keg-register.json"
OUTPUT = ROOT / "output/untappd-links-2026-09-20"
REVIEWS = ROOT / "resources/iiko_untappd_reviews.json"
OBSERVATIONS = ROOT / "resources/untappd_observations.json"
REGISTRY = ROOT / "resources/iiko_untappd_registry.json"
STATUS_LABELS = {"verified": "Связь проверена", "needs_identity": "Уточнить сорт/производителя",
    "needs_variant": "Уточнить версию", "needs_source": "Нужна точная карточка",
    "approximate": "Примерная замена по разрешению владельца",
    "excluded": "Не является сортом", "skipped": "Пропущено владельцем",
    "not_found": "Карточка не найдена", "candidate": "Кандидат", "unresearched": "Не исследовано"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def alias_key(name):
    """Candidate lookup only: retain sweetness, style, version and recipe words."""
    text = unicodedata.normalize("NFKC", name).casefold().replace("ё", "е")
    text = re.sub(r"^\s*кег\s+", "", text)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:л|l|литр(?:а|ов)?)\b", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def beer_id(url):
    parts = urlparse(url)
    if parts.scheme != "https" or parts.netloc != "untappd.com":
        raise ValueError(f"Not an HTTPS Untappd beer URL: {url}")
    match = re.fullmatch(r"/b/[^/]+/([1-9][0-9]*)(?:/(?:photos|activity))?/?", parts.path)
    if not match:
        raise ValueError(f"Not a concrete Untappd beer card: {url}")
    return match.group(1)


def historical_records():
    records = []
    legacy = ROOT / "data/beer_info_mapping.json"
    for alias, info in read(legacy).items():
        records.append({"alias": alias, "brewery": info.get("brewery"),
            "beer_name": info.get("beer_name"), "urls": [info["untappd_url"]] if info.get("untappd_url") else [],
            "source_file": str(legacy.relative_to(ROOT)), "source_key": alias})
    for source, research in [("menu_new_sorts", "menu_newsorts_output"),
                              ("menu_research_input", "menu_research_output")]:
        answers = {str(row["id"]): row for row in read(ROOT / f"data/{research}.json")}
        for row in read(ROOT / f"data/{source}.json"):
            info = answers.get(str(row["id"]), {})
            urls = []
            for url in info.get("sources", []):
                try:
                    beer_id(url)
                except ValueError:
                    continue
                urls.append(url)
            records.append({"alias": row.get("name_src", row.get("name", "")),
                "brewery": info.get("brewery", row.get("brewery")),
                "beer_name": info.get("latin", row.get("latin")), "urls": urls,
                "source_file": f"data/{research}.json", "source_key": str(row["id"]),
                "alias_source": f"data/{source}.json"})
    return records


def build():
    snapshot = read(SNAPSHOT)
    reviews = read(REVIEWS) if REVIEWS.exists() else {}
    observations = read(OBSERVATIONS) if OBSERVATIONS.exists() else {}
    historical = historical_records()
    index = defaultdict(list)
    for record in historical:
        index[alias_key(record["alias"])].append(record)
    source_products = {row["id"]: row for row in read(SNAPSHOT.parent / "source-products.json")}
    products, beers = {}, {}
    known_ids = {row["id"] for row in snapshot["allKegs"]}
    if set(reviews) - known_ids:
        raise ValueError("Review contains an unknown iiko GUID")
    for keg in snapshot["allKegs"]:
        guid = str(uuid.UUID(keg["id"]))
        hints = index.get(alias_key(keg["name"]), [])
        candidates = {}
        for hint in hints:
            for url in hint["urls"]:
                bid = beer_id(url)
                candidates.setdefault(bid, {"untappd_beer_id": bid, "url": url.split("?")[0],
                                           "historical_evidence": []})["historical_evidence"].append(hint)
        decision = reviews.get(guid)
        for bid in (decision or {}).get("candidate_ids", []):
            observed = observations.get(str(bid))
            if observed:
                candidates.setdefault(str(bid), {"untappd_beer_id": str(bid),
                    "url": observed["url"], "historical_evidence": [],
                    "research_evidence": "Карточка найдена при исследовании; кандидат не является связью"})
        for url in (decision or {}).get("candidate_urls", []):
            bid = beer_id(url)
            candidates.setdefault(bid, {"untappd_beer_id": bid, "url": url,
                "historical_evidence": [],
                "research_evidence": "Найдена ссылка; содержимое/соответствие ещё требует проверки"})
        row = {"iiko_product_id": guid, "iiko_article": keg["article"], "iiko_name": keg["name"],
            "iiko_status": keg["status"], "used_last_two_years": keg["usedInPeriod"],
            "sales_liters_two_years": keg["salesOut"] if keg["unit"] == "л" else None,
            "barcodes": [b["barcode"] for b in source_products[guid].get("barcodes") or []],
            "status": "candidate" if candidates else "unresearched",
            "untappd_beer_id": None, "candidates": list(candidates.values()),
            "historical_aliases": hints, "decision": decision}
        if decision:
            if not decision.get("reason") or not decision.get("reviewed_at"):
                raise ValueError(f"Decision lacks rationale/time: {guid}")
            status = decision["status"]
            if status not in {"verified", "approximate", "excluded", "skipped",
                              "needs_identity", "needs_variant", "needs_source", "not_found"}:
                raise ValueError(f"Unknown review status: {status}")
            row["status"] = status
            if status in {"verified", "approximate"}:
                if status == "approximate" and not decision.get("owner_substitution_permission"):
                    raise ValueError(f"Approximate link lacks owner permission: {guid}")
                bid = str(decision["untappd_beer_id"])
                observed = observations[bid]
                if beer_id(observed["url"]) != bid or not all(observed.get(k) for k in
                        ("beer_name", "brewery", "observed_at", "source_method")):
                    raise ValueError(f"Invalid primary observation: {bid}")
                if not decision.get("evidence_urls") or observed["url"] not in decision["evidence_urls"]:
                    raise ValueError(f"Review does not cite its primary card: {guid}")
                row["untappd_beer_id"] = bid
                beers[bid] = observed
        products[guid] = row
    recent = [row for row in products.values() if row["used_last_two_years"]]
    all_counts = Counter(row["status"] for row in products.values())
    counts = Counter(row["status"] for row in recent)
    total_sales = sum((Decimal(str(row["sales_liters_two_years"] or 0)) for row in recent), Decimal(0))
    linked_sales = sum((Decimal(str(row["sales_liters_two_years"] or 0)) for row in recent
                        if row["status"] == "verified"), Decimal(0))
    coverage = (100 * linked_sales / total_sales).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total_sales else None
    inputs = [SNAPSHOT, SNAPSHOT.parent / "source-products.json", REVIEWS, OBSERVATIONS,
              *(ROOT / f"data/{name}.json" for name in ("beer_info_mapping", "menu_new_sorts",
                "menu_newsorts_output", "menu_research_input", "menu_research_output"))]
    result = {"schema_version": 1, "iiko_snapshot_date": "2026-09-20",
        "scope": "Internal keg SKU; recent = stock movement 2024-09-20 through 2026-09-20 inclusive",
        "runtime_policy": "Resolve only verified exact iiko_product_id; never resolve from name or candidate",
        "source_sha256": hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest(),
        "input_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in inputs if path.exists()},
        "summary": {"all_products": len(products), "recent_products": len(recent),
                    "all_status_counts": dict(all_counts),
                    "recent_status_counts": dict(counts),
                    "verified_beers": len({r["untappd_beer_id"] for r in products.values()
                                           if r["status"] == "verified"}),
                    "approximate_beers": len({r["untappd_beer_id"] for r in products.values()
                                              if r["status"] == "approximate"}),
                    "recent_verified_beers": len({r["untappd_beer_id"] for r in recent if r["status"] == "verified"}),
                    "sales_liters_total": float(total_sales), "sales_liters_verified": float(linked_sales),
                    "sales_coverage_percent": float(coverage) if coverage is not None else None},
        "products": products, "beers": beers}
    write(REGISTRY, result)
    queue = sorted(products.values(), key=lambda r: (r["status"] == "verified",
        not r["used_last_two_years"], -(r["sales_liters_two_years"] or 0), r["iiko_product_id"]))
    write(OUTPUT / "review-queue.json", queue)
    with (OUTPUT / "review-queue.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["GUID iiko", "Артикул", "Название iiko", "Статус связи", "ID Untappd",
                         "Пиво Untappd", "Пивоварня Untappd", "Ссылка", "Литры по продажам за 2 года", "Причина", "Кандидаты",
                         "Движение за 2 года", "Состояние карточки iiko"])
        for row in queue:
            card = beers.get(row["untappd_beer_id"], {})
            values = [row["iiko_product_id"], row["iiko_article"], row["iiko_name"], STATUS_LABELS[row["status"]],
                      row["untappd_beer_id"], card.get("beer_name"), card.get("brewery"), card.get("url"),
                      row["sales_liters_two_years"], (row["decision"] or {}).get("reason"),
                      " | ".join(c["url"] for c in row["candidates"]),
                      "Да" if row["used_last_two_years"] else "Нет", row["iiko_status"]]
            writer.writerow(["'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v for v in values])
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    build()
