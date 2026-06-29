"""Клиент Tuya Cloud для чтения температуры/влажности с датчиков по барам.

В каждом баре стоит умный термо-гигрометр (Tuya / Smart Life). Этот модуль
авторизуется в Tuya Cloud, опрашивает 4 устройства и отдаёт показания,
привязанные к каноническим ключам заведений (см. core/venues_config.py).

Подпись запроса (Tuya OpenAPI v2.0, HMAC-SHA256) — деталь протокола, перенесена
из рабочего прототипа без изменений алгоритма:

    stringToSign = METHOD + "\n" + sha256(body) + "\n" + <headers> + "\n" + path
    sign         = HMAC_SHA256(secret, clientId + [accessToken] + t + stringToSign).hex().upper()

Масштаб показаний берём ИЗ СПЕЦИФИКАЦИИ устройства (`scale` в DP), а не угадываем по
величине: датчик отдаёт температуру целым числом в десятых долях (226 => 22.6 при
scale=1). Это важно для корректности на холоде: 95 при scale=1 — это 9.5 C, а не 95 C.
Если спецификация недоступна — применяем задокументированный фоллбэк-масштаб.

Секреты (TUYA_ACCESS_ID / TUYA_ACCESS_SECRET) читаются из окружения (.env), в репозиторий
не попадают. Маппинг устройство->бар — не секрет, задаётся константой DEVICE_TO_VENUE
(переопределяется через env TUYA_DEVICE_MAP, JSON).

Документация: docs/temperature.md
"""

import os
import json
import time
import hmac
import hashlib
import threading

import requests
from dotenv import load_dotenv

from core.venues_config import VENUES

# Загружаем .env из каталога проекта (как config.py) — модуль самодостаточен и не
# зависит от того, импортировался ли config ранее.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))


# --- Маппинг устройств на бары -------------------------------------------------

# Устройство Tuya (device_id) -> канонический ключ заведения (venues_config.VENUES).
# Метки справа («Andr»/«varsh»/...) — как назвал устройства владелец в прототипе.
# «Andr» (Андреевский, Васильевский остров) = бар «Большой пр. В.О» — единственный
# оставшийся после трёх однозначных. Если устройство переедет в другой бар —
# поправьте здесь (или задайте TUYA_DEVICE_MAP в .env).
DEVICE_TO_VENUE = {
    "bf8ab757f8944e3d8axvho": "bolshoy",          # «Andr»  -> Большой пр. В.О
    "bf0f60c862cdea3c6ef4ns": "varshavskaya",     # «varsh» -> Варшавская
    "bf3e8e6edadef4fe3c6duz": "ligovskiy",        # «lig»   -> Лиговский
    "bf0ce7ccba0473fc0ecc0i": "kremenchugskaya",  # «krem»  -> Кременчугская
}


def _device_map():
    """Маппинг устройство->бар. Env TUYA_DEVICE_MAP (JSON) переопределяет константу."""
    raw = os.getenv("TUYA_DEVICE_MAP")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except (ValueError, TypeError):
            print("[TUYA] TUYA_DEVICE_MAP не распарсился как JSON — использую DEVICE_TO_VENUE")
    return DEVICE_TO_VENUE


# --- Температурные диапазоны (единый источник правды для окраски карточек) ------

# Это температура ВОЗДУХА в зале бара (показания датчиков ~22-24 C). Границы — ориентир
# комфорта, не жёсткая норма. Меняются здесь в одном месте; UI берёт их из API
# (/api/temperature/current -> meta.bands), чтобы цвет и легенда всегда совпадали с кодом.
TEMP_BANDS = [
    {"key": "cold", "label": "Холодно", "min": None, "max": 16.0},  # < 16 C
    {"key": "ok",   "label": "Норма",   "min": 16.0, "max": 25.0},  # 16-25 C
    {"key": "warm", "label": "Тепло",   "min": 25.0, "max": 28.0},  # 25-28 C
    {"key": "hot",  "label": "Жарко",   "min": 28.0, "max": None},  # > 28 C
]


def classify_temp(temp):
    """Вернуть ключ диапазона ('cold'|'ok'|'warm'|'hot') для температуры в C или None."""
    if temp is None:
        return None
    for band in TEMP_BANDS:
        lo = band["min"]
        hi = band["max"]
        if (lo is None or temp >= lo) and (hi is None or temp < hi):
            return band["key"]
    return None


# --- DP-коды датчика -----------------------------------------------------------

# Коды Data Point (DP) у термо-гигрометров Tuya. Список синонимов — разные прошивки
# называют один и тот же параметр по-разному.
TEMP_CODES = ("va_temperature", "temp_current", "cur_temp", "temperature")
HUMIDITY_CODES = ("va_humidity", "humidity_value", "cur_humidity", "humidity")
BATTERY_CODES = ("battery_percentage", "battery_value", "residual_electricity")

# Фоллбэк-масштаб (степень десятки), если спецификация устройства недоступна.
# Температура у этих датчиков приходит в десятых (scale=1 => делим на 10); влажность
# и батарея — целым процентом (scale=0).
FALLBACK_SCALE = {"temp": 1, "humidity": 0, "battery": 0}


# --- HTTP / подпись ------------------------------------------------------------

def _endpoint():
    return os.getenv("TUYA_ENDPOINT", "https://openapi.tuyaeu.com").rstrip("/")


def _access():
    """(access_id, access_secret) из окружения. Пустые строки, если не заданы."""
    return os.getenv("TUYA_ACCESS_ID", ""), os.getenv("TUYA_ACCESS_SECRET", "")


def is_configured():
    """True, если заданы и ACCESS_ID, и ACCESS_SECRET (без них опрос невозможен)."""
    access_id, access_secret = _access()
    return bool(access_id and access_secret)


def _sign(access_id, access_secret, timestamp, token, method, path):
    """Подпись Tuya OpenAPI v2.0 (HMAC-SHA256), см. docstring модуля."""
    content_sha256 = hashlib.sha256(b"").hexdigest()  # тело пустое для GET
    string_to_sign = f"{method}\n{content_sha256}\n\n{path}"
    message = access_id + token + timestamp + string_to_sign
    return hmac.new(
        access_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()


# Кэш токена в памяти процесса. Под gunicorn у каждого воркера свой — это нормально.
_TOKEN = {"value": None, "expires_at": 0.0}
_TOKEN_LOCK = threading.Lock()

# Безопасный зазор: обновляем токен за 60 с до фактического истечения.
_TOKEN_SAFETY_MARGIN_S = 60

# Кэш спецификаций устройств (scale по DP). Спека не меняется — кэшируем на весь
# процесс. {device_id: {dp_code: scale_int}}
_SPEC_CACHE = {}
_SPEC_LOCK = threading.Lock()

_HTTP_TIMEOUT_S = 10


class TuyaError(Exception):
    """Ошибка обращения к Tuya Cloud (сеть или API-ответ success=false)."""


def _get_token(force=False):
    """Получить (и закэшировать) access_token. Потокобезопасно."""
    now = time.time()
    if not force and _TOKEN["value"] and now < _TOKEN["expires_at"]:
        return _TOKEN["value"]

    with _TOKEN_LOCK:
        now = time.time()
        if not force and _TOKEN["value"] and now < _TOKEN["expires_at"]:
            return _TOKEN["value"]

        access_id, access_secret = _access()
        if not (access_id and access_secret):
            raise TuyaError("TUYA_ACCESS_ID / TUYA_ACCESS_SECRET не заданы")

        path = "/v1.0/token?grant_type=1"
        timestamp = str(int(time.time() * 1000))
        sign = _sign(access_id, access_secret, timestamp, "", "GET", path)
        headers = {
            "client_id": access_id,
            "sign": sign,
            "t": timestamp,
            "sign_method": "HMAC-SHA256",
        }
        try:
            resp = requests.get(_endpoint() + path, headers=headers, timeout=_HTTP_TIMEOUT_S).json()
        except requests.RequestException as e:
            raise TuyaError(f"сеть при получении токена: {e}")

        if not resp.get("success"):
            raise TuyaError(f"token: {resp.get('msg')} (code={resp.get('code')})")

        result = resp["result"]
        _TOKEN["value"] = result["access_token"]
        # expire_time приходит в секундах (обычно 7200). Кэшируем с запасом.
        expire_s = int(result.get("expire_time", 7200))
        _TOKEN["expires_at"] = time.time() + max(0, expire_s - _TOKEN_SAFETY_MARGIN_S)
        return _TOKEN["value"]


def _signed_get(path, retry_on_token=True):
    """GET к Tuya с подписью и access_token. Возвращает поле result (dict).

    При ответе «token invalid» один раз форсит обновление токена и повторяет.
    """
    access_id, access_secret = _access()
    token = _get_token()
    timestamp = str(int(time.time() * 1000))
    sign = _sign(access_id, access_secret, timestamp, token, "GET", path)
    headers = {
        "client_id": access_id,
        "access_token": token,
        "sign": sign,
        "t": timestamp,
        "sign_method": "HMAC-SHA256",
    }
    try:
        resp = requests.get(_endpoint() + path, headers=headers, timeout=_HTTP_TIMEOUT_S).json()
    except requests.RequestException as e:
        raise TuyaError(f"сеть: {e}")

    if not resp.get("success"):
        # 1010/1011/1012 — протухший/невалидный токен: обновляем и повторяем один раз.
        if retry_on_token and resp.get("code") in (1010, 1011, 1012):
            _get_token(force=True)
            return _signed_get(path, retry_on_token=False)
        raise TuyaError(f"{path}: {resp.get('msg')} (code={resp.get('code')})")

    return resp.get("result")


# --- Спецификация устройства (масштаб DP) --------------------------------------

def _get_scales(device_id):
    """Вернуть {dp_code: scale} для устройства, кэшируя на весь процесс.

    Источник — GET /v1.0/devices/{id}/specifications (поле status[].values.scale).
    При ошибке возвращаем пустой dict (вызывающий применит FALLBACK_SCALE).
    """
    if device_id in _SPEC_CACHE:
        return _SPEC_CACHE[device_id]

    with _SPEC_LOCK:
        if device_id in _SPEC_CACHE:
            return _SPEC_CACHE[device_id]
        scales = {}
        try:
            result = _signed_get(f"/v1.0/devices/{device_id}/specifications")
            for item in (result or {}).get("status", []):
                code = item.get("code")
                values = item.get("values")
                if not code or not values:
                    continue
                try:
                    spec = json.loads(values) if isinstance(values, str) else values
                    if isinstance(spec, dict) and "scale" in spec:
                        scales[code] = int(spec["scale"])
                except (ValueError, TypeError):
                    continue
        except TuyaError as e:
            print(f"[TUYA] спецификация {device_id} недоступна ({e}) — фоллбэк-масштаб")
        _SPEC_CACHE[device_id] = scales
        return scales


def _pick(status_by_code, codes):
    """Вернуть (code, raw_value) для первого присутствующего кода из codes, иначе (None, None)."""
    for code in codes:
        if code in status_by_code:
            return code, status_by_code[code]
    return None, None


def _scaled(raw, code, scales, fallback_pow10):
    """Применить масштаб: raw / 10**scale. scale берём из спеки, иначе fallback."""
    if raw is None:
        return None
    try:
        raw = float(raw)
    except (ValueError, TypeError):
        return None
    scale = scales.get(code, fallback_pow10)
    return round(raw / (10 ** scale), 1)


# --- Чтение устройств ----------------------------------------------------------

def _read_one(device_id):
    """Прочитать одно устройство. Возвращает dict показаний (без привязки к бару).

    Использует GET /v1.0/devices/{id} (online + update_time + status одним вызовом);
    при ошибке падает на проверенный GET /v1.0/devices/{id}/status (без online/времени).
    """
    online = None
    ts = None
    status_list = None

    try:
        detail = _signed_get(f"/v1.0/devices/{device_id}")
        if detail:
            online = detail.get("online")
            # update_time — секунды unix последнего апдейта устройства.
            ts = detail.get("update_time")
            status_list = detail.get("status")
    except TuyaError as e:
        print(f"[TUYA] /devices/{device_id} не отдал детали ({e}) — пробую /status")

    if status_list is None:
        # Фоллбэк на проверенный endpoint (он точно авторизован для этого аккаунта).
        status_list = _signed_get(f"/v1.0/devices/{device_id}/status") or []

    status_by_code = {item.get("code"): item.get("value") for item in status_list if item.get("code")}
    scales = _get_scales(device_id)

    t_code, t_raw = _pick(status_by_code, TEMP_CODES)
    h_code, h_raw = _pick(status_by_code, HUMIDITY_CODES)
    b_code, b_raw = _pick(status_by_code, BATTERY_CODES)

    temperature = _scaled(t_raw, t_code, scales, FALLBACK_SCALE["temp"])
    humidity = _scaled(h_raw, h_code, scales, FALLBACK_SCALE["humidity"])
    battery = _scaled(b_raw, b_code, scales, FALLBACK_SCALE["battery"])
    if battery is not None:
        battery = int(round(battery))

    return {
        "device_id": device_id,
        "temperature": temperature,
        "humidity": humidity,
        "battery": battery,
        "online": online,
        "ts": int(ts) if ts else int(time.time()),
        "band": classify_temp(temperature),
    }


def read_all():
    """Опросить все устройства из маппинга. Вернуть {venue_key: reading}.

    Каждый reading содержит venue_key/venue_name + поля _read_one. Ошибка одного
    устройства не валит остальные: в его reading попадает error и temperature=None.
    """
    out = {}
    for device_id, venue_key in _device_map().items():
        venue = VENUES.get(venue_key, {})
        base = {
            "venue_key": venue_key,
            "venue_name": venue.get("name", venue_key),
            "device_id": device_id,
            "temperature": None,
            "humidity": None,
            "battery": None,
            "online": None,
            "ts": None,
            "band": None,
            "error": None,
        }
        try:
            base.update(_read_one(device_id))
            base["error"] = None
        except TuyaError as e:
            base["error"] = str(e)
            print(f"[TUYA] устройство {device_id} ({venue_key}): {e}")
        out[venue_key] = base
    return out


def bands_payload():
    """Диапазоны для UI (легенда/окраска). Единый источник — TEMP_BANDS."""
    return TEMP_BANDS
