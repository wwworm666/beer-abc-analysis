"""Beer menu card editor blueprint — standalone local version.

Identical to the previous routes/menu.py inside the main app, but data lives
in menu_tool/data/ (relative to this file) instead of going through
core.storage_paths/Render's /kultura disk. Local-only.

Design contract: docs/menu-card.md (mirrored from the original spec).
Each beer renders on a single A4 page; bartender picks one global price
variant (A: 0,3/0,5 — B: 0,25/0,4/0,5) per menu and exports PNG for print.
"""

import io
import json
import os

from flask import Blueprint, request, jsonify, render_template, send_file

menu_bp = Blueprint("menu", __name__, url_prefix="/menu")

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT, "data", "menu_items.json")
SETTINGS_PATH = os.path.join(ROOT, "data", "menu_settings.json")

ITEM_FIELDS = [
    "n", "name", "latin", "brewery", "country", "style", "abv",
    "tags", "ratings", "p025", "p03", "p04", "p05",
]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _load_items():
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_items(items):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _next_id(items):
    return max((i["id"] for i in items), default=0) + 1


def _next_n(items):
    return max((int(i.get("n") or 0) for i in items), default=0) + 1


def _load_settings():
    if not os.path.exists(SETTINGS_PATH):
        return {"variant": "v3"}
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        s = json.load(f)
    if s.get("variant") not in ("v2", "v3"):
        s["variant"] = "v3"
    return s


def _save_settings(s):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _fmt_num(v):
    """Russian decimal display: 770 -> '770', 5.2 -> '5,2', None -> '—'."""
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return "—"
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).replace(".", ",")
    return str(v).replace(".", ",")


def _name_class(name):
    """Auto-fit hook — thresholds locked by the design spec."""
    n = len(name or "")
    if n > 22:
        return "len-xl"
    if n > 16:
        return "len-lg"
    if n > 11:
        return "len-md"
    return ""


def _normalize_tags(tags):
    if tags is None:
        return []
    if isinstance(tags, list):
        out = [str(t).strip() for t in tags if str(t).strip()]
    else:
        parts = str(tags).replace("·", ",").split(",")
        out = [p.strip() for p in parts if p.strip()]
    return out[:3]


def _clamp_rating(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, n))


def _decorate(item):
    """Precompute display fields used by templates/menu_card.html."""
    decorated = dict(item)
    decorated["n"] = int(decorated.get("n") or 0)
    decorated["_name_class"] = _name_class(decorated.get("name"))
    decorated["tags_list"] = _normalize_tags(decorated.get("tags"))
    r = decorated.get("ratings") or {}
    decorated["ratings"] = {
        "gor":  _clamp_rating(r.get("gor", 0)),
        "plot": _clamp_rating(r.get("plot", 0)),
        "cvet": _clamp_rating(r.get("cvet", 0)),
    }
    for k in ("p025", "p03", "p04", "p05"):
        decorated[f"{k}_fmt"] = _fmt_num(decorated.get(k))
    return decorated


def _sanitize(data, base=None):
    out = dict(base) if base else {}
    for k in ITEM_FIELDS:
        if k in data:
            out[k] = data[k]
    out.setdefault("name", "")
    out.setdefault("latin", "")
    out.setdefault("brewery", "")
    out.setdefault("country", "")
    out.setdefault("style", "")
    out.setdefault("abv", "")
    out.setdefault("tags", [])
    out.setdefault("ratings", {"gor": 0, "plot": 0, "cvet": 0})
    for k in ("p025", "p03", "p04", "p05"):
        out.setdefault(k, None)
    return out


def _resolve_variant(value=None):
    if value in ("v2", "v3"):
        return value
    return _load_settings().get("variant", "v3")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@menu_bp.route("/")
def menu_page():
    return render_template("menu.html")


@menu_bp.route("/library")
def library_page():
    return render_template("menu_library.html")


@menu_bp.route("/card")
def card_page():
    """Standalone single-card preview. Used by Playwright and manual inspection.

    Accepts either ?id=N to load from storage, or full item params via query
    string / JSON body. Variant resolves from ?variant=v2|v3 or settings.
    """
    item = _build_card_data()
    variant = _resolve_variant(request.args.get("variant"))
    return render_template(
        "menu_card.html",
        item=_decorate(item),
        variant=variant,
        standalone=True,
    )


def _build_card_data():
    if request.is_json:
        return _sanitize(request.get_json(silent=True) or {})

    item_id = request.args.get("id", type=int)
    if item_id is not None:
        for i in _load_items():
            if i.get("id") == item_id:
                return _sanitize(i)

    data = {
        "n":       request.args.get("n", type=int) or 0,
        "name":    request.args.get("name", ""),
        "latin":   request.args.get("latin", ""),
        "brewery": request.args.get("brewery", ""),
        "country": request.args.get("country", ""),
        "style":   request.args.get("style", ""),
        "abv":     request.args.get("abv", ""),
        "tags":    request.args.get("tags", ""),
        "ratings": {
            "gor":  request.args.get("gor",  type=int) or 0,
            "plot": request.args.get("plot", type=int) or 0,
            "cvet": request.args.get("cvet", type=int) or 0,
        },
        "p025": request.args.get("p025", type=float),
        "p03":  request.args.get("p03",  type=float),
        "p04":  request.args.get("p04",  type=float),
        "p05":  request.args.get("p05",  type=float),
    }
    return _sanitize(data)


# ---------------------------------------------------------------------------
# API — CRUD
# ---------------------------------------------------------------------------


@menu_bp.route("/api/items", methods=["GET"])
def list_items():
    return jsonify(_load_items())


@menu_bp.route("/api/items", methods=["POST"])
def create_item():
    data = request.get_json(force=True, silent=True) or {}
    items = _load_items()
    item = _sanitize(data)
    item["id"] = _next_id(items)
    if not item.get("n"):
        item["n"] = _next_n(items)
    items.append(item)
    _save_items(items)
    return jsonify(item), 201


@menu_bp.route("/api/items/<int:item_id>", methods=["PUT"])
def update_item(item_id):
    data = request.get_json(force=True, silent=True) or {}
    items = _load_items()
    for idx, item in enumerate(items):
        if item.get("id") == item_id:
            items[idx] = {**_sanitize(data, base=item), "id": item_id}
            _save_items(items)
            return jsonify(items[idx])
    return jsonify({"error": "not found"}), 404


@menu_bp.route("/api/items/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    items = _load_items()
    items = [i for i in items if i.get("id") != item_id]
    _save_items(items)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API — Settings (global price variant A/B)
# ---------------------------------------------------------------------------


@menu_bp.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(_load_settings())


@menu_bp.route("/api/settings", methods=["PUT"])
def put_settings():
    data = request.get_json(force=True, silent=True) or {}
    s = _load_settings()
    if data.get("variant") in ("v2", "v3"):
        s["variant"] = data["variant"]
    _save_settings(s)
    return jsonify(s)


# ---------------------------------------------------------------------------
# API — Local Playwright render
#   PNG (~192 DPI растр, для соцсетей/мессенджеров)
#   PDF (вектор, для печати — текст и тонкие линии не растрируются)
# ---------------------------------------------------------------------------


def _render_html(data):
    """Shared between PNG and PDF endpoints — sanitize + decorate + Jinja."""
    item = _decorate(_sanitize(data))
    variant = _resolve_variant(data.get("variant"))
    html = render_template(
        "menu_card.html",
        item=item,
        variant=variant,
        standalone=True,
    )
    return html, item, variant


@menu_bp.route("/api/render", methods=["POST"])
def render_card():
    data = request.get_json(force=True, silent=True) or {}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return jsonify({
            "error": "playwright not installed. "
                     "run: pip install playwright && playwright install chromium",
        }), 500

    html, item, variant = _render_html(data)

    # A4 in CSS pixels (1mm = 3.7795 px @ 96dpi); device_scale_factor=2 ~> 1588×2246 PNG.
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 794, "height": 1123},
            device_scale_factor=2,
        )
        page = context.new_page()
        page.set_content(html, wait_until="networkidle")
        png = page.locator("#menu-card").screenshot(omit_background=False)
        browser.close()

    filename = f"menu-{item.get('name') or 'card'}-{variant}.png"
    return send_file(
        io.BytesIO(png),
        mimetype="image/png",
        as_attachment=True,
        download_name=filename,
    )


@menu_bp.route("/api/render-pdf", methods=["POST"])
def render_pdf():
    """A4 PDF with embedded vectors — the right format for print.

    Текст и линии остаются вектором (не растрируются), печатается на родном
    DPI принтера без потерь качества. format=A4 + margin=0 + print_background
    + prefer_css_page_size — настройки печати пользователя не применяются,
    выход всегда идентичный спецификации.
    """
    data = request.get_json(force=True, silent=True) or {}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return jsonify({
            "error": "playwright not installed. "
                     "run: pip install playwright && playwright install chromium",
        }), 500

    html, item, variant = _render_html(data)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 794, "height": 1123},
        )
        page = context.new_page()
        page.set_content(html, wait_until="networkidle")
        pdf = page.pdf(
            format="A4",
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            print_background=True,
            prefer_css_page_size=True,
        )
        browser.close()

    filename = f"menu-{item.get('name') or 'card'}-{variant}.pdf"
    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
