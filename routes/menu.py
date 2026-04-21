import base64
import io
import json
import os
import uuid

from flask import Blueprint, request, jsonify, render_template, send_file, current_app

menu_bp = Blueprint("menu", __name__, url_prefix="/menu")

DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "menu_items.json"
)
LOGOS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "static", "menu", "logos"
)


def _load_items():
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_items(items):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _next_id(items):
    return max((i["id"] for i in items), default=0) + 1


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@menu_bp.route("/")
def menu_page():
    return render_template("menu.html")


@menu_bp.route("/card")
def card_page():
    """Standalone card preview — используется Playwright-рендером."""
    item = _build_card_data()
    return render_template("menu_card.html", item=item, standalone=False)


def _build_card_data():
    """Собирает данные карточки из query-параметров или request body."""
    if request.method == "POST" or request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = {
            "logo_url": request.args.get("logo_url", ""),
            "name": request.args.get("name", ""),
            "type": request.args.get("type", ""),
            "country": request.args.get("country", ""),
            "abv": request.args.get("abv", ""),
            "description": request.args.get("description", ""),
            "tags": request.args.get("tags", ""),
            "volumes": json.loads(request.args.get("volumes", "[]")),
        }
    return data


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
    item = {
        "id": _next_id(items),
        "logo_url": data.get("logo_url", ""),
        "name": data.get("name", ""),
        "type": data.get("type", ""),
        "country": data.get("country", ""),
        "abv": data.get("abv", ""),
        "description": data.get("description", ""),
        "tags": data.get("tags", ""),
        "volumes": data.get("volumes", []),
    }
    items.append(item)
    _save_items(items)
    return jsonify(item), 201


@menu_bp.route("/api/items/<int:item_id>", methods=["PUT"])
def update_item(item_id):
    data = request.get_json(force=True, silent=True) or {}
    items = _load_items()
    for item in items:
        if item["id"] == item_id:
            item.update(data)
            _save_items(items)
            return jsonify(item)
    return jsonify({"error": "not found"}), 404


@menu_bp.route("/api/items/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    items = _load_items()
    items = [i for i in items if i["id"] != item_id]
    _save_items(items)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API — Logo upload
# ---------------------------------------------------------------------------


@menu_bp.route("/api/logo", methods=["POST"])
def upload_logo():
    data = request.get_json(force=True, silent=True) or {}
    b64 = data.get("data", "")  # base64 data URI

    if not b64:
        file = request.files.get("file")
        if file:
            ext = os.path.splitext(file.filename)[1] or ".png"
            name = f"{uuid.uuid4().hex}{ext}"
            path = os.path.join(LOGOS_DIR, name)
            file.save(path)
            return jsonify({"url": f"/static/menu/logos/{name}"})
        return jsonify({"error": "no image data"}), 400

    # base64
    if "," in b64:
        header, b64 = b64.split(",", 1)
        ext = ".png"
        if "image/jpeg" in header:
            ext = ".jpg"
        elif "image/webp" in header:
            ext = ".webp"
    else:
        ext = ".png"

    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(LOGOS_DIR, name)
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64))
    return jsonify({"url": f"/static/menu/logos/{name}"})


# ---------------------------------------------------------------------------
# API — Server-side render via Playwright
# ---------------------------------------------------------------------------


@menu_bp.route("/api/render", methods=["POST"])
def render_card():
    """Рендерит карточку в PNG через headless Chromium (Playwright)."""
    data = request.get_json(force=True, silent=True) or {}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return jsonify({"error": "playwright not installed. run: pip install playwright && playwright install chromium"}), 500

    # Собираем полный HTML карточки
    html = _build_card_html(data)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_viewport_size({"width": 1240, "height": 1754})
        page.set_content(html, wait_until="networkidle")
        png_bytes = page.screenshot(full_page=True)
        browser.close()

    return send_file(
        io.BytesIO(png_bytes),
        mimetype="image/png",
        as_attachment=True,
        download_name=f"menu-{data.get('name', 'card')}.png",
    )


def _build_card_html(item):
    """Генерирует полный HTML карточки из данных (для Playwright рендера)."""
    logo_html = ""
    if item.get("logo_url"):
        logo_html = f'<img src="{item["logo_url"]}" class="card-logo" alt="Logo"/>'
    else:
        logo_html = '<div class="card-logo-placeholder">LOGO</div>'

    vols = item.get("volumes", [])
    vols_html = ""
    for i, v in enumerate(vols[:2]):
        if i > 0:
            vols_html += '<div class="vol-divider"></div>'
        vols_html += f"""
        <div class="vol-col">
            <span class="vol-label">{v.get("vol", "")}</span>
            <span class="vol-price">{v.get("price", "")}</span>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<link href="https://fonts.googleapis.com/css2?family=PT+Serif:ital,wght@0,400;0,700;1,400;1,700&amp;family=Space+Grotesk:wght@300..700&amp;display=swap" rel="stylesheet"/>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #e5e7eb;
    display: flex; justify-content: center; align-items: center;
    margin: 0; padding: 40px;
}}
.a4-page {{
    width: 1240px; height: 1754px;
    background: #F9F9F7;
    position: relative;
    display: flex; flex-direction: column;
    padding: 60px 100px 100px 100px;
    overflow: hidden;
}}
.corner {{
    position: absolute; width: 60px; height: 60px;
    border: 1px solid #1A1A1A; opacity: 0.3;
}}
.corner.tl {{ top: 60px; left: 60px; border-right: 0; border-bottom: 0; }}
.corner.tr {{ top: 60px; right: 60px; border-left: 0; border-bottom: 0; }}
.corner.bl {{ bottom: 60px; left: 60px; border-right: 0; border-top: 0; }}
.corner.br {{ bottom: 60px; right: 60px; border-left: 0; border-top: 0; }}
.inner {{
    height: 100%; width: 100%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: space-between;
}}
.card-logo {{
    width: 200px; height: 200px; border-radius: 50%;
    object-fit: cover; background: #fff;
    border: 1px solid rgba(26,26,26,0.05);
}}
.card-logo-placeholder {{
    width: 200px; height: 200px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    background: #fff; border: 1px solid rgba(26,26,26,0.05);
    font-family: 'Space Grotesk', sans-serif; font-size: 24px;
    color: #999; letter-spacing: 0.2em;
}}
.divider {{
    width: 80%; height: 1px; background: #1A1A1A; opacity: 0.1; margin: 30px 0;
}}
.title {{
    font-family: 'PT Serif', serif; font-size: 110px;
    font-weight: 700; color: #1A1A1A; text-transform: uppercase;
    text-align: center; letter-spacing: -0.02em; line-height: 1;
    margin-bottom: 32px; word-break: break-word;
}}
.sub-type {{
    font-family: 'PT Serif', serif; font-size: 52px;
    color: #1A1A1A; text-transform: uppercase;
    letter-spacing: 0.3em; text-align: center;
}}
.sub-origin {{
    font-family: 'PT Serif', serif; font-size: 44px;
    color: rgba(26,26,26,0.5); font-style: italic; text-align: center;
}}
.desc {{
    font-family: 'PT Serif', serif; font-size: 72px;
    color: #1A1A1A; font-style: italic; line-height: 1.3;
    text-align: center; padding: 0 160px;
}}
.tags {{
    font-family: 'PT Serif', serif; font-size: 48px;
    color: #1A1A1A; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.15em; text-align: center;
}}
.vols {{
    display: flex; justify-content: center; align-items: center;
    gap: 160px; width: 100%; padding-bottom: 40px;
}}
.vol-col {{
    display: flex; flex-direction: column; align-items: center;
}}
.vol-label {{
    font-family: 'PT Serif', serif; font-size: 60px;
    color: rgba(26,26,26,0.4); text-transform: uppercase;
    letter-spacing: 0.15em; margin-bottom: 8px;
}}
.vol-price {{
    font-family: 'PT Serif', serif; font-size: 104px;
    font-weight: 700; color: #1A1A1A; line-height: 1;
}}
.vol-divider {{
    width: 1px; height: 176px; background: rgba(26,26,26,0.1);
}}
</style>
</head>
<body>
<div class="a4-page">
    <div class="corner tl"></div>
    <div class="corner tr"></div>
    <div class="corner bl"></div>
    <div class="corner br"></div>
    <div class="inner">
        <div class="logo-section">{logo_html}</div>
        <div class="divider"></div>
        <div class="title-section">
            <div class="title">{item.get('name', '')}</div>
            <div class="sub-type">{item.get('type', '')}</div>
            <div class="sub-origin">{item.get('country', '')} · {item.get('abv', '')}</div>
        </div>
        <div class="divider"></div>
        <div class="desc-section">
            <div class="desc">{item.get('description', '')}</div>
            <div class="tags">{item.get('tags', '')}</div>
        </div>
        <div class="divider"></div>
        <div class="vols">{vols_html}</div>
    </div>
</div>
</body>
</html>"""
    return html
