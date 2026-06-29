"""Маршруты мониторинга температуры по барам.

- GET /temperature                  — страница (карточки 4 баров + спарклайн)
- GET /api/temperature/current      — текущие показания (живой опрос Tuya, кэш 60 с,
                                       фоллбэк на последнее из БД, если Tuya недоступна)
- GET /api/temperature/history?hours=24 — история для спарклайна из БД

Документация: docs/temperature.md
"""

import time
import threading

from flask import Blueprint, jsonify, render_template, request

from core.venues_config import PHYSICAL_VENUES, VENUES
from core import tuya_temperature as tuya
from core.temperature_store import get_store
from core.temperature_scheduler import _poll_minutes
from extensions import APP_VERSION

temperature_bp = Blueprint("temperature", __name__)


# Короткий кэш текущих показаний: при авто-рефреше страницы и нескольких зрителях
# не дёргаем Tuya чаще раза в минуту (один источник правды на воркер).
_CURRENT_CACHE = {"data": None, "ts": 0.0}
_CURRENT_TTL_S = 60
_CURRENT_LOCK = threading.Lock()


@temperature_bp.route("/temperature")
def temperature_page():
    """Страница мониторинга температуры."""
    return render_template("temperature.html", app_version=APP_VERSION)


def _ordered_bars(by_venue):
    """Список баров в порядке отображения (PHYSICAL_VENUES)."""
    bars = []
    for vk in PHYSICAL_VENUES:
        r = by_venue.get(vk)
        if r is None:
            venue = VENUES.get(vk, {})
            r = {
                "venue_key": vk,
                "venue_name": venue.get("name", vk),
                "device_id": None,
                "temperature": None,
                "humidity": None,
                "battery": None,
                "online": None,
                "ts": None,
                "band": None,
                "error": "нет данных",
            }
        bars.append(r)
    return bars


def _from_store():
    """Собрать ответ из последних показаний в БД (когда Tuya недоступна/не настроена)."""
    latest = get_store().latest()
    by_venue = {}
    newest = 0
    for vk in PHYSICAL_VENUES:
        venue = VENUES.get(vk, {})
        row = latest.get(vk)
        if row:
            newest = max(newest, int(row.get("ts") or 0))
            by_venue[vk] = {
                "venue_key": vk,
                "venue_name": venue.get("name", vk),
                "device_id": None,
                "temperature": row.get("temperature"),
                "humidity": row.get("humidity"),
                "battery": row.get("battery"),
                "online": (bool(row["online"]) if row.get("online") is not None else None),
                "ts": row.get("ts"),
                "band": tuya.classify_temp(row.get("temperature")),
                "error": None,
            }
    return by_venue, newest


@temperature_bp.route("/api/temperature/current")
def api_current():
    """Текущие показания. ?force=1 обходит 60-секундный кэш (кнопка «Обновить»)."""
    force = request.args.get("force") in ("1", "true", "yes")
    now = time.time()

    if not force and _CURRENT_CACHE["data"] and (now - _CURRENT_CACHE["ts"]) < _CURRENT_TTL_S:
        payload = dict(_CURRENT_CACHE["data"])
        payload["source"] = "cache"
        return jsonify(payload)

    bands = tuya.bands_payload()
    poll_minutes = _poll_minutes()
    meta = {"bands": bands, "configured": tuya.is_configured(), "poll_minutes": poll_minutes}

    if not tuya.is_configured():
        # Tuya не настроена — отдаём что есть в истории (может быть пусто).
        by_venue, newest = _from_store()
        return jsonify({
            "success": True,
            "source": "store",
            "updated_at": newest or int(now),
            "bars": _ordered_bars(by_venue),
            "meta": meta,
        })

    with _CURRENT_LOCK:
        now = time.time()
        if not force and _CURRENT_CACHE["data"] and (now - _CURRENT_CACHE["ts"]) < _CURRENT_TTL_S:
            payload = dict(_CURRENT_CACHE["data"])
            payload["source"] = "cache"
            return jsonify(payload)

        try:
            by_venue = tuya.read_all()
            # Живой опрос тоже пополняет историю (тем же бакетом, что и фоновый опрос).
            try:
                get_store().save_readings(by_venue, max(1, poll_minutes) * 60)
            except Exception as e:
                print(f"[TUYA] save_readings из /current не удался: {e}")
            source = "live"
            updated_at = int(now)
        except Exception as e:
            # Полный провал опроса — фоллбэк на последнее известное из БД.
            print(f"[TUYA] /current read_all не удался: {e}")
            by_venue, newest = _from_store()
            source = "store"
            updated_at = newest or int(now)

        payload = {
            "success": True,
            "source": source,
            "updated_at": updated_at,
            "bars": _ordered_bars(by_venue),
            "meta": meta,
        }
        _CURRENT_CACHE["data"] = payload
        _CURRENT_CACHE["ts"] = time.time()
        return jsonify(payload)


def _downsample(points, max_points):
    """Проредить точки до max_points равномерно (лёгкий график на больших периодах).

    Берём равномерно распределённые индексы + всегда последнюю точку, порядок по ts
    сохраняется. На периодах <= max_points возвращаем как есть.
    """
    n = len(points)
    if n <= max_points or max_points <= 0:
        return points
    step = n / float(max_points)
    idxs = sorted({min(int(k * step), n - 1) for k in range(max_points)})
    if idxs[-1] != n - 1:
        idxs.append(n - 1)
    return [points[i] for i in idxs]


@temperature_bp.route("/api/temperature/history")
def api_history():
    """История показаний. ?hours=24 (1..720 — до 30 дней). ?max_points ограничивает
    плотность точек (прорежывание для лёгких графиков на длинных периодах)."""
    try:
        hours = int(request.args.get("hours", "24"))
    except (ValueError, TypeError):
        hours = 24
    hours = max(1, min(720, hours))

    try:
        max_points = int(request.args.get("max_points", "1500"))
    except (ValueError, TypeError):
        max_points = 1500
    max_points = max(50, min(5000, max_points))

    hist = get_store().history(hours=hours)
    return jsonify({
        "success": True,
        "hours": hours,
        "bars": {vk: _downsample(hist.get(vk, []), max_points) for vk in PHYSICAL_VENUES},
    })
