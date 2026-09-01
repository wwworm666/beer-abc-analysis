"""Редактор меню (серверная версия).

Перенесён из локального menu_tool/ в основное приложение: данные хранятся на
постоянном диске (/kultura через core.storage_paths), правки идут через дашборд.

Отличия от прежнего menu_tool:
  - объёмы разлива выбираются на карточке (vols: подмножество 0,25/0,33/0,4/0,5,
    до 3 колонок; без vols — легаси-вид 0,25/0,4/0,5), переключателя A/B нет;
  - единый каталог menu_cards.json (библиотека + краны, поле tap = № крана);
  - кнопка «Обновить цены» тянет актуальные цены из iiko (core.menu_pricing);
  - рендер PDF/PNG через Playwright (Chromium есть в прод-образе).

Маршруты (url_prefix=/menu):
  GET  /menu                     — страница-редактор
  GET  /menu/card?id=N           — одиночное превью карточки (для Playwright/печати)
  GET  /menu/print?filter=tap|all— страница со всеми карточками (Ctrl+P)
  GET/POST       /menu/api/items          — список / создание
  PUT/DELETE     /menu/api/items/<id>      — обновление / удаление
  POST           /menu/api/refresh-prices  — обновить цены из iiko
  POST           /menu/api/render-pdf      — PDF одной карточки (Playwright)
  GET            /menu/api/export-pdf?filter=tap|all — PDF всех карточек одним файлом
"""
import io
import json
import os
import re

from flask import Blueprint, request, jsonify, render_template, send_file

from core.storage_paths import get_data_path

ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "static", "menu")
# Справочник стилей (BJCP 2021 + наши специалитеты) — источник для дропдауна и
# чипсов-рекомендаций. Reference-данные (меняются с кодом), читаем из data/ напрямую.
STYLES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "beer_styles.json")

menu_editor_bp = Blueprint("menu_editor", __name__, url_prefix="/menu")

DATA_FILE = "menu_cards.json"

# Канонический набор полей карточки (p03 убран; p033 и vols добавлены 2026-09-01).
ITEM_FIELDS = [
    "n", "tap", "name", "latin", "brewery", "country", "style", "abv",
    "tags", "ratings", "vols", "p025", "p033", "p04", "p05",
]
PRICE_FIELDS = ("p025", "p033", "p04", "p05")

# Реестр объёмов: (ключ, подпись на карточке, поле цены). Порядок кортежа =
# порядок колонок на карточке (по возрастанию объёма) — vols карточки всегда
# нормализуется к нему, порядок из UI/API значения не имеет.
VOLUMES = (
    ("025", "0,25", "p025"),
    ("033", "0,33", "p033"),
    ("04",  "0,4",  "p04"),
    ("05",  "0,5",  "p05"),
)
DEFAULT_VOLS = ["025", "04", "05"]  # вид карточки до появления 0,33 (легаси)
MAX_VOLS = 3  # макет A4 (шрифты/сетка .prices) рассчитан максимум на 3 колонки


def _normalize_vols(vols):
    """Выбор объёмов карточки: только известные ключи, канонический порядок,
    максимум MAX_VOLS. Не список / пусто / мусор -> DEFAULT_VOLS (легаси-вид)."""
    if not isinstance(vols, list):
        return list(DEFAULT_VOLS)
    have = {str(v) for v in vols}
    picked = [key for key, _, _ in VOLUMES if key in have]
    if not picked:
        return list(DEFAULT_VOLS)
    return picked[:MAX_VOLS]


# ---------------------------------------------------------------------------
# Хранилище (постоянный диск /kultura, seed из repo data/menu_cards.json)
# ---------------------------------------------------------------------------

def _path():
    return get_data_path(DATA_FILE, seed_from_local=True)


def _load_items():
    p = _path()
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_items(items):
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _next_id(items):
    return max((int(i.get("id") or 0) for i in items), default=0) + 1


def _next_n(items):
    return max((int(i.get("n") or 0) for i in items), default=0) + 1


# ---------------------------------------------------------------------------
# Подготовка к рендеру
# ---------------------------------------------------------------------------

def _fmt_num(v):
    """Русское отображение: 770 -> '770', 5.2 -> '5,2', None -> '—'."""
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
    d = dict(item)
    d["n"] = int(d.get("n") or 0)
    d["_name_class"] = _name_class(d.get("name"))
    d["tags_list"] = _normalize_tags(d.get("tags"))
    r = d.get("ratings") or {}
    d["ratings"] = {
        "gor": _clamp_rating(r.get("gor", 0)),
        "plot": _clamp_rating(r.get("plot", 0)),
        "cvet": _clamp_rating(r.get("cvet", 0)),
    }
    # Колонки цен на карточке: выбранные объёмы в каноническом порядке.
    d["vols"] = _normalize_vols(d.get("vols"))
    d["servings"] = [
        {"vol": label, "price": _fmt_num(d.get(field))}
        for key, label, field in VOLUMES if key in d["vols"]
    ]
    return d


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
    out.setdefault("tap", None)
    out["vols"] = _normalize_vols(out.get("vols"))
    for k in PRICE_FIELDS:
        out.setdefault(k, None)
    # tap -> int|None
    tap = out.get("tap")
    try:
        out["tap"] = int(tap) if tap not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        out["tap"] = None
    return out


# ---------------------------------------------------------------------------
# Страницы
# ---------------------------------------------------------------------------

@menu_editor_bp.route("", strict_slashes=False)
@menu_editor_bp.route("/")
def menu_page():
    # /menu и /menu/ -> библиотека-таблица (без 308-редиректа, чтобы подсветка
    # активного пункта меню по pathname совпадала с href="/menu").
    return render_template("menu_library.html")


@menu_editor_bp.route("/edit")
def edit_page():
    # Редактор одной карточки (?id=N — открыть существующую, без id — новая).
    return render_template("menu_editor.html")


@menu_editor_bp.route("/card")
def card_page():
    item_id = request.args.get("id", type=int)
    item = None
    if item_id is not None:
        for i in _load_items():
            if int(i.get("id") or 0) == item_id:
                item = i
                break
    if item is None:
        item = _sanitize({"n": request.args.get("n", type=int) or 0})
    return render_template("menu_card.html", item=_decorate(item), standalone=True)


def _filtered(items, flt):
    if flt == "tap":
        on = [i for i in items if i.get("tap")]
        on.sort(key=lambda x: int(x.get("tap") or 0))
        return on
    return sorted(items, key=lambda x: (0, x["tap"]) if x.get("tap") else (1, int(x.get("n") or 0)))


@menu_editor_bp.route("/print")
def print_page():
    flt = request.args.get("filter", "tap")
    items = [_decorate(i) for i in _filtered(_load_items(), flt)]
    return render_template("menu_print.html", items=items)


# ---------------------------------------------------------------------------
# API — CRUD
# ---------------------------------------------------------------------------

@menu_editor_bp.route("/api/styles", methods=["GET"])
def list_styles():
    """Справочник стилей для дропдауна: {styles:[{name,code,en,group,rec[3]}]}."""
    try:
        with open(STYLES_FILE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except OSError:
        return jsonify({"styles": []})


@menu_editor_bp.route("/api/items", methods=["GET"])
def list_items():
    return jsonify(_load_items())


@menu_editor_bp.route("/api/items", methods=["POST"])
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


@menu_editor_bp.route("/api/items/<int:item_id>", methods=["PUT"])
def update_item(item_id):
    data = request.get_json(force=True, silent=True) or {}
    items = _load_items()
    for idx, item in enumerate(items):
        if int(item.get("id") or 0) == item_id:
            items[idx] = {**_sanitize(data, base=item), "id": item_id}
            _save_items(items)
            return jsonify(items[idx])
    return jsonify({"error": "not found"}), 404


@menu_editor_bp.route("/api/items/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    items = _load_items()
    items = [i for i in items if int(i.get("id") or 0) != item_id]
    _save_items(items)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API — Обновление цен из iiko
# ---------------------------------------------------------------------------

@menu_editor_bp.route("/api/refresh-prices", methods=["POST"])
def refresh_prices_route():
    from core import menu_pricing
    items = _load_items()
    try:
        summary = menu_pricing.refresh_prices(items, use_cache=False)
    except Exception as e:  # iiko недоступна / ошибка OLAP
        return jsonify({"error": str(e)}), 502
    _save_items(items)
    # компактная сводка для UI
    return jsonify({
        "matched": summary["matched"],
        "total": summary["total"],
        "date_from": summary["date_from"],
        "date_to": summary["date_to"],
        "updated": [u for u in summary["updated"] if u["changed"]],
    })


# ---------------------------------------------------------------------------
# API — Рендер через Playwright (Chromium есть в прод-образе)
# ---------------------------------------------------------------------------

def _inline_assets(html):
    """Встроить CSS/шрифт в HTML. Playwright рендерит через set_content (без
    серверного контекста), поэтому абсолютные ссылки /static/... не резолвятся —
    подставляем содержимое файлов как <style>, иначе PDF выходит без стилей."""
    def repl(m):
        fname = m.group(1).rsplit("/", 1)[-1]
        try:
            with open(os.path.join(ASSET_DIR, fname), encoding="utf-8") as f:
                return "<style>\n" + f.read() + "\n</style>"
        except OSError:
            return m.group(0)
    return re.sub(r'<link[^>]+href="(/static/menu/[^"]+\.css)"[^>]*>', repl, html)


def _render_pdf_html(html):
    from playwright.sync_api import sync_playwright
    html = _inline_assets(html)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 794, "height": 1123})
        page = context.new_page()
        page.set_content(html, wait_until="networkidle")
        # Дождаться загрузки PT Serif и перемерить авто-ужатие строк: первый прогон
        # fit-функций идёт на запасном шрифте (уже), без перемера PT Serif шире и
        # строки («Дескрипторы», «Стиль», имя) обрезает overflow:hidden.
        page.wait_for_function("document.fonts.status === 'loaded'")
        page.evaluate("window.fitAll && window.fitAll()")
        pdf = page.pdf(format="A4",
                       margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                       print_background=True, prefer_css_page_size=True)
        browser.close()
    return pdf


@menu_editor_bp.route("/api/render-pdf", methods=["POST"])
def render_pdf():
    data = request.get_json(force=True, silent=True) or {}
    try:
        item = _decorate(_sanitize(data))
        html = render_template("menu_card.html", item=item, standalone=True)
        pdf = _render_pdf_html(html)
    except ImportError:
        return jsonify({"error": "playwright not installed"}), 500
    filename = f"menu-{item.get('name') or 'card'}.pdf"
    return send_file(io.BytesIO(pdf), mimetype="application/pdf",
                     as_attachment=True, download_name=filename)


@menu_editor_bp.route("/api/export-pdf", methods=["GET"])
def export_pdf():
    flt = request.args.get("filter", "tap")
    items = [_decorate(i) for i in _filtered(_load_items(), flt)]
    if not items:
        return jsonify({"error": "нет карточек"}), 404
    try:
        html = render_template("menu_print.html", items=items)
        pdf = _render_pdf_html(html)
    except ImportError:
        return jsonify({"error": "playwright not installed"}), 500
    name = "menu-taps.pdf" if flt == "tap" else "menu-all.pdf"
    return send_file(io.BytesIO(pdf), mimetype="application/pdf",
                     as_attachment=True, download_name=name)
