"""Resolve reviewed links by exact iiko product UUID. See docs/untappd-links.md.

No name/article fallback: unresolved or malformed entries return no card.
Loading is explicit so consumers control refresh; importing performs no I/O.
"""
from copy import deepcopy
import os
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from uuid import UUID


DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "data/iiko_untappd_registry.json"
BUNDLED_REGISTRY = Path(__file__).resolve().parents[1] / "resources/iiko_untappd_registry.json"


def load_registry(path=None, live=None):
    """Рабочий реестр: встроенный файл + связи, подтверждённые на сайте.

    live — наложить связи с сайта (core/untappd_live: агент предлагает, владелец
    подтверждает, без деплоя). По умолчанию — да, если path не задан (так читают
    сайт, бот и посты); при явном path — нет (тесты, сборка реестра)."""
    explicit = path is not None
    if path is None:
        path = os.environ.get('UNTAPPD_REGISTRY_PATH') or (
            BUNDLED_REGISTRY if BUNDLED_REGISTRY.exists() else DEFAULT_REGISTRY)
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1:
        raise ValueError("Unsupported iiko/Untappd registry version")
    if (not explicit) if live is None else live:
        from core import untappd_live
        registry = untappd_live.apply(registry)
    return registry


def resolve_beer(registry, iiko_product_id):
    """Return a detached verified card, or None; never guess an identity."""
    if registry.get("schema_version") != 1:
        return None
    try:
        guid = str(UUID(str(iiko_product_id)))
    except (ValueError, TypeError, AttributeError):
        return None
    row = registry.get("products", {}).get(guid)
    if not row or row.get("iiko_product_id") != guid or row.get("status") != "verified":
        return None
    decision = row.get("decision") or {}
    bid = row.get("untappd_beer_id")
    if not isinstance(bid, str) or not re.fullmatch(r"[1-9][0-9]*", bid):
        return None
    if decision.get("status") != "verified" or str(decision.get("untappd_beer_id")) != bid:
        return None
    if not decision.get("reason") or not decision.get("reviewed_at"):
        return None
    card = registry.get("beers", {}).get(bid)
    if not card or str(card.get("id")) != bid:
        return None
    url = card.get("url", "")
    try:
        parts = urlparse(url)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.netloc != "untappd.com":
        return None
    if not re.fullmatch(r"/b/[^/]+/" + re.escape(bid) + r"/?", parts.path):
        return None
    if not all(card.get(k) for k in ("beer_name", "brewery", "observed_at", "source_method")):
        return None
    if url not in decision.get("evidence_urls", []):
        return None
    return deepcopy(card)
