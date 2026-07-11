# -*- coding: utf-8 -*-
"""
Честный ЗНАК — единый клиент для аутентификации и получения данных.

Рабочая комбинация аутентификации:
  csptest.exe -sfsign -sign -my %THUMB% -in %DATA% -out %SIG% -base64 -cades_strict -add
  POST /auth/simpleSignIn: {"uuid": "...", "data": "подпись"}

ВАЖНО: НЕ использовать -detached! Сервер возвращает 403.
Запускать из cmd ОТ ИМЕНИ АДМИНИСТРАТОРА
"""

import subprocess, os, json, time, ssl, urllib.request, urllib.error
from datetime import datetime, timedelta


# ==================== КОНФИГУРАЦИЯ ====================

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
CHZ_BASE_URL_V4 = "https://markirovka.crpt.ru/api/v4/true-api"
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
INN_ORG = "7801630649"               # ООО "ИНВЕСТАГРО"
ORG_NAME = 'ООО "ИНВЕСТАГРО"'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG_DIR = os.path.join(BASE_DIR, "debug")
TOKEN_FILE = os.path.join(DEBUG_DIR, "token.json")


# ==================== УТИЛИТЫ ====================

def make_request(url, method="GET", data=None, headers=None, raw=False, timeout=60):
    """HTTP запрос к ЧЗ API.

    raw=True — вернуть body как bytes (для скачивания CSV/ZIP).
    raw=False — попытаться распарсить как JSON (default).
    """
    if headers is None:
        headers = {}
    if data and isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
        response = opener.open(req, timeout=timeout)
        body_bytes = response.read()
        if raw:
            return response.status, body_bytes
        body = body_bytes.decode('utf-8')
        return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        try:
            return e.code, json.loads(error_body)
        except Exception:
            return e.code, {"_raw": error_body[:500]}
    except Exception as ex:
        return None, str(ex)


# ==================== ДИСПЕНСЕР: АСИНХРОННЫЕ ОТЧЁТЫ ====================

# productGroupCode в ЧЗ:
#   8  = milk (молочная продукция)
#   11 = alcohol (крепкий алкоголь, сидр, медовуха)
#   13 = water (упакованная вода)
#   15 = beer (пиво и напитки на основе пива)
#   22 = nabeer (безалкогольное пиво)
#   23 = softdrinks (соки, газировки, лимонады, шорли)
DISPENSER_GROUPS = {
    "beer": 15,
    "nabeer": 22,
    "softdrinks": 23,
    "alcohol": 11,
    "water": 13,
    "milk": 8,
}

# Группы которые выгружаем по умолчанию.
# alcohol (11) НЕ нужен — крепкий алкоголь маркируется ЕГАИС-маркой, не ЧЗ.
# Сидр/медовуха/перри попадают в beer (15) как «слабоалкогольные напитки».
# water/milk выключены (бар их не продаёт значимыми объёмами).
DEFAULT_AUTO_GROUPS = ["beer", "nabeer", "softdrinks"]


def dispenser_create_task(token, group_code, filter_dict):
    """POST /dispenser/tasks — создать задание FILTERED_CIS_REPORT."""
    url = f"{CHZ_BASE_URL}/dispenser/tasks"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "format": "CSV",
        "name": "FILTERED_CIS_REPORT",
        "periodicity": "SINGLE",
        "productGroupCode": str(group_code),
        "params": json.dumps(filter_dict, ensure_ascii=False),
    }
    status, resp = make_request(url, method="POST", data=payload, headers=headers)
    return status, resp


def dispenser_poll(token, task_id, group_code, max_seconds=600, interval=5):
    """GET /dispenser/tasks/{id} — опрос статуса до COMPLETED/FAILED."""
    url = f"{CHZ_BASE_URL}/dispenser/tasks/{task_id}?pg={group_code}"
    headers = {"Authorization": f"Bearer {token}"}
    waited = 0
    while waited < max_seconds:
        status, resp = make_request(url, method="GET", headers=headers)
        if status != 200:
            return status, resp
        cur = resp.get("currentStatus", "")
        if cur in ("COMPLETED", "FAILED", "CANCELED"):
            return 200, resp
        time.sleep(interval)
        waited += interval
    return None, {"error": f"timeout after {max_seconds}s"}


def dispenser_get_result_id(token, task_id, group_code):
    """GET /dispenser/results — найти resultId по taskId."""
    url = f"{CHZ_BASE_URL}/dispenser/results?page=0&size=20&pg={group_code}"
    headers = {"Authorization": f"Bearer {token}"}
    status, resp = make_request(url, method="GET", headers=headers)
    if status != 200:
        return status, resp
    # Ищем результат с нашим taskId
    items = resp.get("list") or resp.get("results") or resp.get("content") or []
    for it in items:
        if it.get("taskId") == task_id or it.get("task_id") == task_id:
            return 200, it.get("id") or it.get("resultId")
    # fallback: первый из списка
    if items:
        return 200, items[0].get("id") or items[0].get("resultId")
    return 404, {"error": "no results found", "list_keys": list(resp.keys())}


def dispenser_download(token, result_id, group_code):
    """GET /dispenser/results/{id}/file — скачать CSV (bytes)."""
    url = f"{CHZ_BASE_URL}/dispenser/results/{result_id}/file?pg={group_code}"
    headers = {"Authorization": f"Bearer {token}"}
    return make_request(url, method="GET", headers=headers, raw=True, timeout=300)


def export_csv_via_dispenser(token, group_name, group_code, filter_dict=None, status="INTRODUCED"):
    """Полная цепочка: create → poll → get result_id → download → save CSV.

    Файл сохраняется в chz_test/debug/pg{group_code}_csv/auto-{status}-{timestamp}.csv
    `status` обязателен в API; для покрытия импортного товара вызывайте
    функцию ДВАЖДЫ — со status=INTRODUCED и status=APPLIED. Файлы не
    перетирают друг друга т.к. имеют статус в имени.
    """
    if filter_dict is None:
        filter_dict = {
            "participantInn": INN_ORG,
            "packageType": ["UNIT", "LEVEL1"],
            "status": status,
        }
    elif "status" not in filter_dict:
        filter_dict = {**filter_dict, "status": status}

    print(f"\n[{group_name}/pg{group_code}] Создаём задание...")
    http_status, resp = dispenser_create_task(token, group_code, filter_dict)
    if http_status != 200:
        print(f"  [ERR] create_task HTTP {http_status}: {resp}")
        return False
    task_id = resp.get("id") or resp
    if isinstance(task_id, dict):
        task_id = task_id.get("id")
    print(f"  taskId: {task_id}")

    print(f"  Опрос статуса (макс. 10 минут)...")
    http_status, resp = dispenser_poll(token, task_id, group_code)
    if http_status != 200:
        print(f"  [ERR] poll HTTP {http_status}: {resp}")
        return False
    cur = resp.get("currentStatus")
    print(f"  Финальный статус: {cur}")
    if cur != "COMPLETED":
        print(f"  [SKIP] не COMPLETED, не качаем")
        return False

    print(f"  Получаем resultId...")
    http_status, result_id = dispenser_get_result_id(token, task_id, group_code)
    if http_status != 200 or not result_id:
        print(f"  [ERR] result_id: {http_status} {result_id}")
        return False
    print(f"  resultId: {result_id}")

    print(f"  Скачиваем файл...")
    http_status, content = dispenser_download(token, result_id, group_code)
    if http_status != 200:
        print(f"  [ERR] download HTTP {http_status}")
        return False
    if not isinstance(content, (bytes, bytearray)) or len(content) == 0:
        print(f"  [ERR] empty download")
        return False
    print(f"  Получено {len(content)} bytes")

    out_dir = os.path.join(DEBUG_DIR, f"pg{group_code}_csv")
    os.makedirs(out_dir, exist_ok=True)
    # Удалим старые auto-*.csv ТОЛЬКО для текущего status (не трогаем файлы
    # с других статусов чтобы не потерять, например, APPLIED при перезапуске
    # с status=INTRODUCED).
    import glob as _glob
    status_lc = status.lower()
    for old in _glob.glob(os.path.join(out_dir, f"auto-{status_lc}-*.csv")):
        try:
            os.remove(old)
        except OSError:
            pass

    # Dispenser API возвращает ZIP с одним CSV внутри (signature PK\x03\x04).
    # ЛК отдавала чистый CSV. Поддерживаем оба варианта.
    if content[:4] == b"PK\x03\x04":
        import zipfile, io as iomod
        try:
            zf = zipfile.ZipFile(iomod.BytesIO(content))
        except zipfile.BadZipFile as e:
            print(f"  [ERR] bad ZIP: {e}")
            return False
        names = zf.namelist()
        csv_names = [n for n in names if n.lower().endswith(".csv")]
        if not csv_names:
            print(f"  [ERR] no CSV inside ZIP, contents: {names}")
            return False
        inner = csv_names[0]
        csv_bytes = zf.read(inner)
        print(f"  ZIP содержит {inner} ({len(csv_bytes)} bytes)")
        out_file = os.path.join(out_dir, f"auto-{status_lc}-{int(time.time())}.csv")
        with open(out_file, "wb") as f:
            f.write(csv_bytes)
    else:
        out_file = os.path.join(out_dir, f"auto-{status_lc}-{int(time.time())}.csv")
        with open(out_file, "wb") as f:
            f.write(content)
    print(f"  [OK] {out_file}")
    return True


def clean_base64(text):
    """Очистить текст до чистого base64"""
    return ''.join(c for c in text
                   if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')


# ==================== АУТЕНТИФИКАЦИЯ ====================

def get_token():
    """
    Получить новый токен от ЧЗ API.

    Алгоритм (найдено экспериментально):
    1. GET /auth/key → uuid + data (30-символьная строка)
    2. csptest.exe -sfsign -sign -my THUMB -in DATA -out SIG -base64 -cades_strict -add
    3. POST /auth/simpleSignIn {"uuid": uuid, "data": подпись} → токен

    Возвращает: {"token": "eyJ...", "expires_at": 1234567890}
               или {"error": "описание ошибки"}
    """
    os.makedirs(DEBUG_DIR, exist_ok=True)

    # 1. Получить uuid + data
    print("  [auth] Запрос UUID и DATA...", end=" ")
    status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
    if status != 200:
        print(f"[ERR] GET /auth/key: {auth_data}")
        return {"error": f"auth/key failed ({status}): {auth_data}"}

    uuid = auth_data.get('uuid')
    data_to_sign = auth_data.get('data')
    if not uuid or not data_to_sign:
        return {"error": f"No uuid/data: {auth_data}"}
    print(f"[OK] {uuid[:8]}...")

    # 2. Сохранить данные
    data_file = os.path.join(DEBUG_DIR, "_data_to_sign.txt")
    sig_file = os.path.join(DEBUG_DIR, "_signature.txt")
    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    # 3. Подписать
    cmd = (f'"{CSP_PATH}" -sfsign -sign '
           f'-my "{CERT_THUMBPRINT}" '
           f'-in "{data_file}" -out "{sig_file}" '
           f'-base64 -cades_strict -add')

    print(f"  [auth] Подпись...", end=" ")
    result = subprocess.run(cmd, shell=True, capture_output=True,
                            timeout=60, encoding='cp866',
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        print(f"[ERR] csptest rc={result.returncode}")
        return {"error": f"csptest failed ({result.returncode}): {result.stderr[:200]}"}
    print(f"[OK]")

    # 4. Прочитать подпись
    if not os.path.exists(sig_file):
        return {"error": "Signature file not created"}
    with open(sig_file, 'r', encoding='utf-8-sig') as f:
        raw_sig = f.read()
    signature = clean_base64(raw_sig)
    if len(signature) < 100:
        return {"error": f"Signature too short: {len(signature)} chars"}

    # 5. Отправить — v2 формат: uuid + data
    print(f"  [auth] Обмен на токен...", end=" ")
    payload = {"uuid": uuid, "data": signature}
    status, response = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        method="POST", data=payload
    )

    if status == 200:
        token = response.get('token')
        if not token:
            return {"error": f"No token in response: {response}"}

        # Токен действует 10 часов, сохраняем с запасом 9 часов
        expires_at = int(time.time()) + 32400
        token_data = {"token": token, "expires_at": expires_at}

        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f, indent=2, ensure_ascii=False)

        exp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))
        print(f"[OK] действует до {exp_str}")
        return token_data
    else:
        error_msg = response.get('error_message', str(response))
        print(f"[ERR] {status}: {error_msg}")
        return {"error": f"simpleSignIn failed ({status}): {error_msg}"}


def load_token():
    """
    Загрузить токен, обновить если истёк.

    Возвращает строку токена или None.
    """
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE) as f:
                t = json.load(f)
            token = t.get("token")
            expires_at = t.get("expires_at")
            if token and expires_at and time.time() < expires_at:
                return token
        except Exception:
            pass

    # Токен отсутствует или просрочен
    print("\n  Получаю новый токен...")
    result = get_token()
    if "error" in result:
        return None
    # Перечитываем из файла для надёжности
    with open(TOKEN_FILE) as f:
        return json.load(f).get("token")


# ==================== ЗАПРОСЫ ДАННЫХ ====================

def get_participants(inn=None):
    """Проверить участников по ИНН"""
    inn = inn or INN_ORG
    token = load_token()
    if not token:
        return {"error": "Токен не получен"}

    headers = {"Authorization": f"Bearer {token}"}
    url = f"{CHZ_BASE_URL}/participants?inns={inn}"
    status, response = make_request(url, headers=headers)

    if status == 200:
        orgs = response if isinstance(response, list) else [response]
        for org in orgs:
            name = org.get('name', '?')
            status_text = org.get('status', '?')
            groups = org.get('productGroups', [])
            print(f"  {name} — {status_text}"
                  f"\n    Группы: {', '.join(groups)}")
    else:
        print(f"  [ERR] {status}: {response}")

    return {"status": status, "data": response}


def search_cises(token=None, page=0, limit=100, product_group="beer",
                 date_from=None, date_to=None):
    """
    Поиск кодов маркировки.

    API v4: POST /api/v4/true-api/cises/search
    Ответ: {"result": [...], "isLastPage": bool}

    Parameters
    ----------
    token : str
        Токен авторизации (запрашивается автоматически если None)
    page, limit : int
        Пагинация
    product_group : str
        "beer" | "nabeer" | "water" | "dairy" | ...
    date_from, date_to : str
        Период даты введения в оборот (format: "YYYY-MM-DD")
    """
    if token is None:
        token = load_token()
        if not token:
            return {"error": "Токен не получен"}, None, None

    headers = {"Authorization": f"Bearer {token}"}

    # Формируем filter
    filter_data = {
        "productGroups": [product_group],
        "ownerInn": INN_ORG,
    }

    # Период по умолчанию: последние 30 дней
    now = datetime.now()
    if date_to is None:
        date_to = now
    elif isinstance(date_to, str):
        date_to = datetime.strptime(date_to, "%Y-%m-%d")
    if date_from is None:
        date_from = now - timedelta(days=30)
    elif isinstance(date_from, str):
        date_from = datetime.strptime(date_from, "%Y-%m-%d")

    filter_data["introducedDatePeriod"] = {
        "from": date_from.strftime("%Y-%m-%dT00:00:00.000Z"),
        "to": date_to.strftime("%Y-%m-%dT23:59:59.999Z"),
    }

    payload = {
        "page": page,
        "limit": limit,
        "filter": filter_data
    }

    url = f"{CHZ_BASE_URL_V4}/cises/search"
    status, response = make_request(url, method="POST", data=payload, headers=headers)
    return status, response, (date_from, date_to)


def get_all_cises(product_group="beer", date_from=None, date_to=None,
                  delay_between_pages=0, max_items=100000):
    """
    Загрузить ВСЕ коды маркировки (со всеми страницами).

    Returns: список словарей с полями:
        cis, gtin, status, expirationDate, productionDate,
        introducedDate, producerInn, modId
    """
    token = load_token()
    if not token:
        return []

    # Если даты не указаны — не фильтруем по дате (получаем все коды)
    use_date_filter = date_from is not None or date_to is not None
    if use_date_filter:
        now = datetime.now()
        if date_to is None:
            date_to = now
        if isinstance(date_to, str):
            date_to = datetime.strptime(date_to, "%Y-%m-%d")
        if date_from is None:
            date_from = now - timedelta(days=30)
        if isinstance(date_from, str):
            date_from = datetime.strptime(date_from, "%Y-%m-%d")
        print(f"\n  Загрузка: {product_group} | {date_from.strftime('%Y-%m-%d')} — {date_to.strftime('%Y-%m-%d')}")
    else:
        print(f"\n  Загрузка: {product_group} (все коды, без фильтра по дате)")

    all_items = []
    current_page = 0
    limit = 100  # API ЧЗ жёстко режет страницы до 100, даже если запросить больше.
                 # Если ставить limit=1000, len(items) (=100) < limit и пагинация рвётся.
    retry_count = 0
    max_retries = 3

    while True:
        print(f"  Страница {current_page + 1}...", end=" ")

        if use_date_filter:
            status, response, _ = search_cises(
                token=token, page=current_page, limit=limit,
                product_group=product_group,
                date_from=date_from, date_to=date_to
            )
        else:
            # Без фильтра по дате — прямой запрос
            headers = {"Authorization": f"Bearer {token}"}
            payload = {
                "page": current_page,
                "limit": limit,
                "filter": {
                    "productGroups": [product_group],
                    "ownerInn": INN_ORG,
                }
            }
            url = f"{CHZ_BASE_URL_V4}/cises/search"
            status, response = make_request(url, method="POST", data=payload, headers=headers)

        if status != 200:
            retry_count += 1
            if retry_count >= max_retries:
                raise RuntimeError(f"API error after {max_retries} retries: HTTP {status}, response: {response}")
            print(f"[ERR] HTTP {status}, retry {retry_count}/{max_retries}...")
            time.sleep(10)
            continue
        retry_count = 0

        items = response.get("result", [])
        is_last = response.get("isLastPage", True)
        all_items.extend(items)
        print(f"[OK] +{len(items)} (всего {len(all_items)})")

        if is_last or len(items) < limit or len(all_items) >= max_items:
            break

        current_page += 1
        time.sleep(delay_between_pages)

    return all_items


def print_expiration_report(items):
    """Напечатать отчёт по срокам годности, группируя по GTIN"""
    if not items:
        print("\n  Нет данных")
        return

    # Группировка
    by_gtin = {}
    status_counter = {}
    for item in items:
        gtin = item.get("gtin", "N/A")
        status_val = item.get("status", "UNKNOWN")
        status_counter[status_val] = status_counter.get(status_val, 0) + 1

        if gtin not in by_gtin:
            by_gtin[gtin] = {
                "gtin": gtin,
                "count": 0,
                "producer": item.get("producerInn", "N/A"),
                "manufacturer": item.get("manufacturerInn", "N/A"),
                "expiration_dates": set(),
                "production_dates": set(),
                "mod_ids": set(),
            }

        e = by_gtin[gtin]
        e["count"] += 1

        # Срок годности
        exp = item.get("expirationDate", "")
        if exp and "T" in exp:
            exp = exp.split("T")[0]
        if exp:
            e["expiration_dates"].add(exp)

        # Дата производства
        prod = item.get("productionDate", "")
        if prod and "T" in prod:
            prod = prod.split("T")[0]
        if prod:
            e["production_dates"].add(prod)

        # MOD ID
        m = item.get("modId", "")
        if m:
            e["mod_ids"].add(m)

    # Вывод
    print(f"\n{'='*70}")
    print(f"  ОТЧЁТ: Сроки годности ({ORG_NAME}, ИНН {INN_ORG})")
    print(f"{'='*70}")
    print(f"\n  Всего кодов: {len(items)}")
    print(f"  Статусы: {', '.join(f'{k}={v}' for k, v in status_counter.items())}")
    print(f"  Уникальных GTIN: {len(by_gtin)}")

    # Сохранить JSON
    data_file = os.path.join(DEBUG_DIR, "expiration_data.json")
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(list(by_gtin.values()), f, indent=2, ensure_ascii=False,
                  default=lambda x: list(x) if isinstance(x, set) else x)

    # Сортируем по количеству кодов
    for g in sorted(by_gtin.values(), key=lambda x: x["count"], reverse=True):
        print(f"\n  {'-'*69}")
        print(f"  GTIN:       {g['gtin']}")
        print(f"  Производитель: {g['producer']}")
        print(f"  Кодов:       {g['count']}")
        print(f"  Срок годности: {', '.join(sorted(g['expiration_dates']))}")
        print(f"  Дата произв.:  {', '.join(sorted(g['production_dates']))}")
        print(f"  MOD ID(s):     {', '.join(sorted(g['mod_ids']))}")

    print(f"\n  FILE: Подробная сводка: {data_file}")


# ==================== НАЗВАНИЯ ПРОДУКТОВ ====================

def get_product_names(gtins, token=None):
    """Получить названия товаров по списку GTIN через product/info.

    POST /api/v4/true-api/product/info
    Request: {"gtins": [...], "rdInfo": false}
    Response: {"results": [{"gtin": "...", "name": "...", "brand": "...", ...}], "total": N}

    Returns: dict {gtin: {"name": str, "brand": str, "volumeWeight": str, ...}}
    """
    if token is None:
        token = load_token()
        if not token:
            return {}

    if not gtins:
        return {}

    # Дополняем GTIN до 14 цифр лидирующими нулями
    padded_gtins = [g.zfill(14) for g in gtins]

    headers = {"Authorization": f"Bearer {token}"}
    payload = {"gtins": padded_gtins, "rdInfo": False}

    url = f"{CHZ_BASE_URL_V4}/product/info"
    status, response = make_request(url, method="POST", data=payload, headers=headers)

    if status != 200:
        print(f"  [ERR] product/info: HTTP {status} — {response}")
        return {}

    result = {}
    for item in response.get("results", []):
        gtin = item.get("gtin", "")
        result[gtin] = {
            "name": item.get("name", ""),
            "brand": item.get("brand", ""),
            "privateBrand": item.get("privateBrand", ""),
            "fullName": item.get("fullName", ""),
            "volumeWeight": item.get("volumeWeight", ""),
            "coreVolume": item.get("coreVolume", ""),
            "netWeight": item.get("netWeight", ""),
            "packageType": item.get("packageType", ""),
            "productGroup": item.get("productGroup", ""),
        }

    return result


# ==================== ПАРСЕР CSV-ЭКСПОРТОВ ИЗ ЛК ЧЗ ====================

def parse_chz_csv(csv_dir=None):
    """Прочитать CSV-экспорт из личного кабинета ЧЗ и собрать остатки.

    Формат CSV: первая строка — фильтр, вторая строка — заголовки (внутри
    поля могут быть запятые, поэтому весь заголовок и данные хранятся в
    одном поле с разделителем CSV `,` внутри, а внешний разделитель `;`).

    Parameters
    ----------
    csv_dir : str | None
        Путь к папке с CSV-файлами. Если None, ищет все pg*_csv/ в debug/.

    Returns
    -------
    list[dict]: Записи {gtin, name, brand, count, expiration_dates,
                        production_dates, product_group}.
    """
    import csv as csvmod
    import io as iomod
    import glob

    if csv_dir is None:
        # все папки pg*_csv в debug/
        pattern = os.path.join(DEBUG_DIR, "pg*_csv")
        dirs = glob.glob(pattern)
    else:
        dirs = [csv_dir]

    by_gtin = {}
    parsed_rows = 0
    for d in dirs:
        for csv_file in glob.glob(os.path.join(d, "*.csv")):
            # ЛК-выгрузка отдаёт UTF-8, dispenser API — cp1251.
            # Пробуем оба, без BOM-контроля (utf-8-sig тоже работает).
            rows = None
            for enc in ("utf-8-sig", "utf-8", "cp1251"):
                try:
                    with open(csv_file, encoding=enc) as f:
                        reader = csvmod.reader(f, delimiter=";")
                        rows = list(reader)
                    break
                except UnicodeDecodeError:
                    rows = None
                    continue
            if rows is None or len(rows) < 2:
                print(f"  [SKIP] {csv_file}: не удалось декодировать или пустой")
                continue
            # rows[0] = фильтр, rows[1] = заголовки CSV-в-CSV
            header = list(csvmod.reader(iomod.StringIO(rows[1][0])))[0]
            try:
                gtin_i = header.index("gtin")
                name_i = header.index("productName")
                brand_i = header.index("brand")
                status_i = header.index("status")
                exp_i = header.index("expirationDate")
                prod_i = header.index("productionDate")
                group_i = header.index("productGroup")
                pkg_i = header.index("packageType")
                owner_i = header.index("ownerInn")
                kpp_i = header.index("kpp") if "kpp" in header else None
                fias_i = header.index("fiasId") if "fiasId" in header else None
            except ValueError as e:
                print(f"  [SKIP] {csv_file}: missing column ({e})")
                continue

            for row in rows[2:]:
                if not row or not row[0]:
                    continue
                parts = list(csvmod.reader(iomod.StringIO(row[0])))[0]
                if len(parts) <= max(gtin_i, name_i, status_i, exp_i):
                    continue
                # Принимаем in-circulation статусы:
                #   INTRODUCED — В обороте (основная масса)
                #   APPLIED    — Нанесён (типично для импорта в пути)
                #   EMITTED    — Эмитирован (свежие коды только что произведённые)
                # Отбрасываем: RETIRED, WRITTEN_OFF, DISAGGREGATION
                if parts[status_i] not in ("INTRODUCED", "APPLIED", "EMITTED"):
                    continue
                if parts[pkg_i] != "UNIT":
                    continue
                # Не фильтруем по ownerInn — для импорта/неподписанных УПД
                # ownerInn может быть = поставщик, не наш ИНН. Бутылка
                # физически у нас, но числится за поставщиком до подписания.
                gtin = parts[gtin_i]
                if not gtin:
                    continue
                parsed_rows += 1

                # Очистка дат: формат "2027-03-10T00:00:00.000Z" -> "2027-03-10"
                exp = parts[exp_i].split("T")[0] if parts[exp_i] else ""
                prod = parts[prod_i].split("T")[0] if parts[prod_i] else ""

                # КПП места осуществления деятельности (МОД).
                # Иногда колонки kpp/fiasId сдвинуты из-за запятых в predшествующих
                # полях — фильтруем только валидные 9-значные КПП.
                kpp = ""
                if kpp_i is not None and len(parts) > kpp_i:
                    raw_kpp = (parts[kpp_i] or "").strip()
                    if raw_kpp.isdigit() and len(raw_kpp) == 9:
                        kpp = raw_kpp
                fias = ""
                if fias_i is not None and len(parts) > fias_i:
                    raw_fias = (parts[fias_i] or "").strip()
                    # FIAS — UUID (36 символов с дефисами); отсеиваем если случайно КПП
                    if len(raw_fias) == 36 and raw_fias.count("-") == 4:
                        fias = raw_fias

                if gtin not in by_gtin:
                    by_gtin[gtin] = {
                        "gtin": gtin,
                        "name": parts[name_i] or "",
                        "brand": parts[brand_i] or "",
                        "count": 0,
                        "expiration_dates": set(),
                        "production_dates": set(),
                        "batches": {},          # {(prod, exp): count} — по всему юрлицу
                        "by_kpp": {},           # {kpp: {count, batches: {(prod, exp): count}, fiasId}}
                        "product_group": parts[group_i] or "",
                    }
                e = by_gtin[gtin]
                e["count"] += 1
                if exp:
                    e["expiration_dates"].add(exp)
                if prod:
                    e["production_dates"].add(prod)
                key = (prod, exp)
                e["batches"][key] = e["batches"].get(key, 0) + 1

                # Привязка к месту деятельности
                kpp_key = kpp or "_unknown"
                if kpp_key not in e["by_kpp"]:
                    e["by_kpp"][kpp_key] = {
                        "kpp": kpp,
                        "fiasId": fias,
                        "count": 0,
                        "batches": {},
                    }
                slot = e["by_kpp"][kpp_key]
                slot["count"] += 1
                slot["batches"][key] = slot["batches"].get(key, 0) + 1
                if not slot["fiasId"] and fias:
                    slot["fiasId"] = fias

    print(f"  [CSV] обработано {parsed_rows} строк, {len(by_gtin)} уникальных GTIN")

    def _batches_to_list(batches_dict):
        out = [
            {"production_date": p, "expiration_date": x, "count": c}
            for (p, x), c in batches_dict.items()
        ]
        out.sort(key=lambda b: b["production_date"], reverse=True)
        return out

    # set/dict -> сериализуемые списки
    stock = []
    for entry in by_gtin.values():
        by_kpp_out = []
        for slot in entry["by_kpp"].values():
            by_kpp_out.append({
                "kpp": slot["kpp"],
                "fiasId": slot["fiasId"],
                "count": slot["count"],
                "batches": _batches_to_list(slot["batches"]),
            })
        by_kpp_out.sort(key=lambda s: -s["count"])
        stock.append({
            **{k: v for k, v in entry.items() if k not in ("batches", "by_kpp")},
            "expiration_dates": sorted(entry["expiration_dates"]),
            "production_dates": sorted(entry["production_dates"]),
            "batches": _batches_to_list(entry["batches"]),
            "by_kpp": by_kpp_out,
        })
    stock.sort(key=lambda x: x["count"], reverse=True)
    return stock


# ==================== ОСТАТКИ ЧЗ (НАЗВАНИЕ + КОЛ-ВО + СРОК) ====================

PRODUCT_GROUPS = ["beer", "nabeer", "softdrinks"]

def get_chz_stock(product_groups=None, date_from=None, date_to=None):
    """Полный запрос остатков ЧЗ: коды + названия.

    Parameters
    ----------
    product_groups : list[str] | str | None
        Список групп или одна строка. По умолчанию: beer + nabeer + softdrinks.
    date_from, date_to : str | datetime
        Период даты введения в оборот.

    Returns: список словарей {gtin, name, brand, count, expiration_dates, production_dates, product_group}
    """
    # Нормализуем группы
    if product_groups is None:
        groups = PRODUCT_GROUPS
    elif isinstance(product_groups, str):
        groups = [product_groups]
    else:
        groups = product_groups

    # БЕЗ фильтра по дате: фильтр ownerInn (ИНН организации) сам ограничивает выборку
    # до ~5000 кодов. Фильтр по introducedDate отрезает старые коды, которые ещё в стоке —
    # пиво может лежать на складе год+ после маркировки, дата введения в оборот не важна.

    # 1. Загружаем коды из всех групп (без фильтра по дате)
    all_items = []
    for g in groups:
        print(f"\n  Группа: {g}")
        items = get_all_cises(
            product_group=g,
            date_from=date_from, date_to=date_to
        )
        all_items.extend(items)

    if not all_items:
        return []

    # 2. Фильтруем только INTRODUCED (в обороте = на складе)
    introduced = [i for i in all_items if i.get("status") == "INTRODUCED"]
    if not introduced:
        print("  Нет кодов со статусом INTRODUCED")
        return []

    print(f"\n  В обороте: {len(introduced)} из {len(all_items)} кодов")

    # 3. Группируем по GTIN
    by_gtin = {}
    for item in introduced:
        gtin = item.get("gtin") or ""
        if not gtin:
            continue  # пропустить записи без GTIN или с отсутствующим полем
        pg = item.get("productGroup", "")
        if gtin not in by_gtin:
            by_gtin[gtin] = {
                "gtin": gtin,
                "count": 0,
                "expiration_dates": set(),
                "production_dates": set(),
                "product_group": pg,
            }
        e = by_gtin[gtin]
        e["count"] += 1

        exp = item.get("expirationDate", "")
        if exp and "T" in exp:
            exp = exp.split("T")[0]
        if exp:
            e["expiration_dates"].add(exp)

        prod = item.get("productionDate", "")
        if prod and "T" in prod:
            prod = prod.split("T")[0]
        if prod:
            e["production_dates"].add(prod)

    # 4. Получаем названия
    unique_gtins = list(by_gtin.keys())
    product_names = get_product_names(unique_gtins)

    # 5. Объединяем
    stock = []
    for gtin, data in by_gtin.items():
        info = product_names.get(gtin, {})
        entry = {
            "gtin": gtin,
            "name": info.get("name", ""),
            "brand": info.get("brand", ""),
            "privateBrand": info.get("privateBrand", ""),
            "fullName": info.get("fullName", ""),
            "volumeWeight": info.get("volumeWeight", ""),
            "coreVolume": info.get("coreVolume", ""),
            "count": data["count"],
            "expiration_dates": sorted(data["expiration_dates"]),
            "production_dates": sorted(data["production_dates"]),
            "product_group": data.get("product_group", ""),
        }
        stock.append(entry)

    # Сортируем по количеству (убывание)
    stock.sort(key=lambda x: x["count"], reverse=True)
    return stock


# ==================== ОСТАТКИ ЧЗ ЧЕРЕЗ /cises/search (с 2026-06) ====================
# Контекст: общепит по послаблению ГИС МТ выводит коды из оборота СРАЗУ при приёмке
# (status=RETIRED, причина OWN_USE/PRODUCTION_USE). Поэтому:
#   - старый фильтр INTRODUCED больше не отдаёт остаток (коды мгновенно RETIRED);
#   - dispenser-выгрузка (csv-auto) по RETIRED виснет в PREPARATION часами.
# Рабочий путь — синхронный /cises/search (любой статус) + привязка к бару по
# modId -> ownerMod.kpp (через /cises/info). Структура результата идентична
# parse_chz_csv (с полем by_kpp), чтобы /expiration и /stocks работали без правок.

# Окно по дате введения в оборот (дней). Код вводится+выводится при приёмке,
# поэтому свежий introducedDate ~ то, что ещё может стоять на складе. Очень старые,
# но ещё не проданные партии в окно не попадут (для них на странице просто не будет
# срока ЧЗ) — приемлемая деградация, пиво в баре оборачивается быстрее.
SEARCH_STOCK_WINDOW_DAYS = 60

# Early-stop по сходимости: выведенные коды копятся тысячами на каждый GTIN
# (одна выгрузка beer/60д = 100k+ кодов), но уникальных партий (gtin,kpp,срок)
# всего ~40. Каждая партия встречается на почти каждой странице, поэтому после
# того как N страниц подряд не принесли НОВОЙ партии — дальше только дубли,
# можно останавливаться. Так пул кодов падает со 100k до ~2-4k (секунды вместо минут).
SEARCH_CONVERGE_PAGES = 25
MAX_SEARCH_PAGES_PER_GROUP = 250


def resolve_mod_to_kpp(token, sample_cis_by_mod):
    """modId -> (kpp, fiasId) бара через /cises/info (поле ownerMod).

    Один вызов на каждый уникальный modId (~4 бара). ВАЖНО: брать именно
    ownerMod.* — это наш бар; applicationMod и верхнеуровневый kpp относятся
    к поставщику (склад-отправитель), не к бару.
    """
    out = {}
    url = f"{CHZ_BASE_URL}/cises/info"
    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for mod_id, cis in sample_cis_by_mod.items():
        kpp, fias = "", ""
        try:
            body = json.dumps([cis], ensure_ascii=False).encode("utf-8")
            st, r = make_request(url, method="POST", data=body, headers=hdr)
            if st == 200 and isinstance(r, list) and r:
                owner = (r[0].get("cisInfo") or {}).get("ownerMod") or {}
                k = str(owner.get("kpp") or "").strip()
                if k.isdigit() and len(k) == 9:
                    kpp = k
                f = str(owner.get("fiasId") or "").strip()
                if len(f) == 36 and f.count("-") == 4:
                    fias = f
        except Exception as e:
            print(f"  [MOD] {mod_id}: ошибка /cises/info — {e}")
        print(f"  [MOD] {mod_id} -> kpp={kpp or '?'}")
        out[str(mod_id)] = (kpp, fias)
    return out


def resolve_mod_kpp(token, cis):
    """(kpp, fiasId) бара по одному коду через /cises/info (ownerMod).

    Для ленивого резолва modId в потоковой выгрузке: МОД мало (~4), вызываем
    один раз на каждый новый modId. Берём ownerMod.* (наш бар), НЕ applicationMod
    и НЕ верхнеуровневый kpp (это поставщик).
    """
    kpp, fias = "", ""
    if not cis:
        return kpp, fias
    try:
        url = f"{CHZ_BASE_URL}/cises/info"
        hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = json.dumps([cis], ensure_ascii=False).encode("utf-8")
        st, r = make_request(url, method="POST", data=body, headers=hdr)
        if st == 200 and isinstance(r, list) and r:
            owner = (r[0].get("cisInfo") or {}).get("ownerMod") or {}
            k = str(owner.get("kpp") or "").strip()
            if k.isdigit() and len(k) == 9:
                kpp = k
            f = str(owner.get("fiasId") or "").strip()
            if len(f) == 36 and f.count("-") == 4:
                fias = f
    except Exception as e:
        print(f"  [MOD] ошибка /cises/info — {e}")
    return kpp, fias


# ==================== ПРИВЯЗКА К БАРУ ЧЕРЕЗ УПД (ЭДО-приёмки) ====================
# У ПИВА каждый код в /cises/search несёт modId места приёмки -> ownerMod.kpp
# (основной механизм, НЕ трогаем). У NABEER/SOFTDRINKS modId пустой: вывод из
# оборота бухгалтерия подаёт одним LK_RECEIPT от юрлица, без точки (проверено
# 2026-07-11 по /cises/info и телу документа вывода). Но ПРИЁМКА этих групп идёт
# по ЭДО: входящий УПД несёт КПП точки-грузополучателя (receiverMod.kpp — ставит
# сам ЧЗ; buyerInfo.kpp — от поставщика) и, у современных поставщиков, поштучные
# коды. Старые поставки/Метро — ОСУ-строки "02<gtin>37<кол-во>" без кодов, их
# привязать нельзя (для них прод показывает срок «по юрлицу»).
#
# Отсюда КАРТА cis -> КПП бара: fallback ТОЛЬКО для кодов без modId.
# Кэш инкрементальный (upd_kpp_map.json): обработанный УПД не перечитывается,
# новые документы подхватываются каждым search-stock автоматически — новые
# позиции/поставки не требуют ручных действий.

UPD_KPP_GROUPS = ["nabeer", "softdrinks"]  # у beer входящих УПД в ЧЗ нет (там modId)
UPD_KPP_CACHE = os.path.join(DEBUG_DIR, "upd_kpp_map.json")


def _cis_key(code):
    """Нормализовать КИ к ключу 'gtin|serial'.

    Формат UNIT-кода: 01<gtin, 14 цифр>21<serial до GS-разделителя \\x1d>.
    В УПД и /cises/search серийники совпадают, но крипто-хвосты (группы 91/92/93)
    могут отличаться — сравниваем только gtin+serial.
    """
    if not code or not code.startswith("01") or len(code) < 19:
        return ""
    gtin = code[2:16]
    if not gtin.isdigit() or code[16:18] != "21":
        return ""
    serial = code[18:].split("\x1d")[0]
    return f"{gtin}|{serial}" if serial else ""


def _harvest_upd_codes(token, pg, doc_number, kpp_hint, cache):
    """Обработать один УПД: КПП точки + поштучные коды -> в кэш.

    Возвращает (units, osu): сколько кодов привязано / сколько ОСУ-строк без кодов.
    """
    hdr = {"Authorization": f"Bearer {token}"}
    st, resp = make_request(
        f"{CHZ_BASE_URL_V4}/doc/{doc_number}/info?pg={pg}&body=true", headers=hdr)
    if st != 200 or not isinstance(resp, list) or not resp:
        # Запомнить с ошибкой, чтобы не долбить каждый прогон; err очистится
        # при ручной пересборке кэша (удалить upd_kpp_map.json).
        cache["docs"][doc_number] = {"kpp": "", "units": 0, "err": f"HTTP {st}"}
        return 0, 0
    doc = resp[0]
    body = doc.get("body") or {}
    kpp = str((doc.get("receiverMod") or {}).get("kpp")
              or kpp_hint
              or (body.get("buyerInfo") or {}).get("kpp") or "")
    units = osu = 0
    if kpp.isdigit() and len(kpp) == 9:
        for p in (body.get("products") or []):
            code = p.get("code") or p.get("cis") or ""
            key = _cis_key(code)
            if key:
                cache["cis"][key] = kpp
                units += 1
            elif code.startswith("02"):
                osu += 1
    cache["docs"][doc_number] = {"kpp": kpp, "units": units}
    return units, osu


def refresh_upd_kpp_map(token, groups=None):
    """Инкрементально обновить и вернуть карту {cis_key: kpp} из входящих УПД.

    Ошибки сети/API не фатальны: возвращаем то, что накоплено в кэше, — сбор
    остатков продолжит работать как раньше (привязка только по modId).
    """
    groups = groups or UPD_KPP_GROUPS
    cache = {"docs": {}, "cis": {}}
    if os.path.exists(UPD_KPP_CACHE):
        try:
            with open(UPD_KPP_CACHE, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and isinstance(loaded.get("cis"), dict):
                cache = loaded
        except Exception as e:
            print(f"  [UPD] кэш не прочитан ({e}) — пересобираем с нуля")

    hdr = {"Authorization": f"Bearer {token}"}
    new_docs = osu_total = 0
    for pg in groups:
        date_from = None
        for _ in range(10):  # предохранитель пагинации
            url = (f"{CHZ_BASE_URL_V4}/doc/list?limit=1000&pg={pg}"
                   f"&documentType=UNIVERSAL_TRANSFER_DOCUMENT")
            if date_from:
                url += f"&dateFrom={date_from}"
            try:
                st, resp = make_request(url, headers=hdr)
            except Exception as e:
                print(f"  [UPD/{pg}] doc/list: {e} — пропуск группы")
                break
            if st != 200 or not isinstance(resp, dict):
                print(f"  [UPD/{pg}] doc/list HTTP {st} — пропуск группы")
                break
            docs = resp.get("results") or []
            for d in docs:
                num = d.get("number")
                if (not num or num in cache["docs"]
                        or not d.get("input") or d.get("status") != "CHECKED_OK"):
                    continue
                kpp_hint = str((d.get("receiverMod") or {}).get("kpp") or "")
                try:
                    _, osu = _harvest_upd_codes(token, pg, num, kpp_hint, cache)
                    osu_total += osu
                    new_docs += 1
                except Exception as e:
                    print(f"  [UPD/{pg}] {num[:40]}: {e}")
            if not resp.get("nextPage") or not docs:
                break
            date_from = docs[-1].get("receivedAt")  # список ascending по receivedAt

    try:
        with open(UPD_KPP_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as e:
        print(f"  [UPD] кэш не сохранён: {e}")
    if new_docs or osu_total:
        print(f"  [UPD] новых УПД: {new_docs}, ОСУ-строк без кодов: {osu_total}")
    return cache["cis"]


# Точечный режим: сколько страниц (×100 кодов) тянуть на один GTIN. Большинство
# GTIN держат <100 кодов → хватает 1 страницы; высокообъёмным берём пару про запас.
SEARCH_GTIN_MAX_PAGES = 3


def _accumulate_code(by_gtin, mod_to_place, token, it, default_group, upd_map=None):
    """Учесть один код ЧЗ в структуре by_gtin (как parse_chz_csv).

    Возвращает batch_key (gtin, kpp_key, prod, exp) если код штучный (UNIT) и учтён,
    иначе None. modId резолвится в КПП лениво (кешируется в mod_to_place).

    Привязка к бару двухступенчатая:
    1. modId -> ownerMod.kpp (пиво; основной механизм, как раньше);
    2. если modId пуст (nabeer/softdrinks) — карта cis->КПП из входящих УПД
       (upd_map, см. refresh_upd_kpp_map). Без карты поведение прежнее.
    """
    gtin = it.get("gtin") or ""
    if not gtin:
        return None
    pkg = it.get("generalPackageType") or it.get("packageType")
    if pkg and pkg != "UNIT":
        return None
    exp = (it.get("expirationDate") or "").split("T")[0]
    prod = (it.get("productionDate") or "").split("T")[0]
    mid = str(it.get("modId")) if it.get("modId") is not None else ""
    if mid and mid not in mod_to_place:
        mod_to_place[mid] = resolve_mod_kpp(token, it.get("cis"))
        print(f"  [MOD] {mid} -> kpp={mod_to_place[mid][0] or '?'}")
    kpp, fias = mod_to_place.get(mid, ("", ""))
    if not kpp and upd_map:
        upd_kpp = upd_map.get(_cis_key(it.get("cis") or ""))
        if upd_kpp:
            kpp, fias = upd_kpp, ""

    e = by_gtin.get(gtin)
    if e is None:
        e = by_gtin[gtin] = {
            "gtin": gtin, "name": "", "brand": "", "count": 0,
            "expiration_dates": set(), "production_dates": set(),
            "batches": {}, "by_kpp": {}, "product_group": it.get("productGroup") or default_group,
        }
    e["count"] += 1
    if exp:
        e["expiration_dates"].add(exp)
    if prod:
        e["production_dates"].add(prod)
    key = (prod, exp)
    e["batches"][key] = e["batches"].get(key, 0) + 1

    kpp_key = kpp or "_unknown"
    slot = e["by_kpp"].get(kpp_key)
    if slot is None:
        slot = e["by_kpp"][kpp_key] = {"kpp": kpp, "fiasId": fias, "count": 0, "batches": {}}
    slot["count"] += 1
    slot["batches"][key] = slot["batches"].get(key, 0) + 1
    if not slot["fiasId"] and fias:
        slot["fiasId"] = fias
    return (gtin, kpp_key, prod, exp)


def _search_by_gtins(token, groups, gtins_chunk, page, limit=100):
    """POST /cises/search с фильтром по списку GTIN (единственный фильтр, который
    API реально уважает — kpp/modId игнорируются). Без окна по дате: тянем весь
    набор кодов конкретного GTIN, чтобы поймать и старые партии."""
    filt = {"productGroups": groups, "ownerInn": INN_ORG, "gtins": gtins_chunk}
    url = f"{CHZ_BASE_URL_V4}/cises/search"
    st, resp = make_request(url, method="POST",
                            data={"page": page, "limit": limit, "filter": filt},
                            headers={"Authorization": f"Bearer {token}"})
    return resp if isinstance(resp, dict) else {}


def get_chz_stock_via_search(product_groups=None, days=SEARCH_STOCK_WINDOW_DAYS, gtins=None):
    """Остатки ЧЗ через синхронный /cises/search (замена dispenser csv-auto).

    Возвращает структуру идентичную parse_chz_csv: список
    {gtin, name, brand, count, expiration_dates, production_dates,
     product_group, batches, by_kpp}. Привязка к бару (by_kpp) — по modId.
    """
    if product_groups is None:
        groups = PRODUCT_GROUPS
    elif isinstance(product_groups, str):
        groups = [product_groups]
    else:
        groups = product_groups

    token = load_token()
    if not token:
        print("[ERR] Нет токена")
        return []

    # Карта cis -> КПП из входящих УПД (для кодов без modId: nabeer/softdrinks).
    # Любой сбой здесь НЕ ломает сбор — просто работаем как раньше (только modId).
    upd_map = {}
    try:
        upd_map = refresh_upd_kpp_map(token)
        if upd_map:
            print(f"  [UPD] карта приёмок ЭДО: {len(upd_map)} кодов -> КПП")
    except Exception as e:
        print(f"  [UPD] карта приёмок недоступна ({e}) — привязка только по modId")

    by_gtin = {}
    mod_to_place = {}      # modId -> (kpp, fiasId), резолвим лениво по мере встречи

    if gtins:
        # ТОЧЕЧНО: тянем именно те GTIN, что бар держит на остатке (список из iiko).
        # «по ownerInn без gtins» /cises/search отдаёт лишь ~20 высокообъёмных GTIN
        # (newest-first, длинный хвост недостижим), поэтому фильтруем по gtins —
        # единственный фильтр, который API реально уважает.
        uniq = list(dict.fromkeys(str(x).zfill(14) for x in gtins if x))
        print(f"  Точечный режим: {len(uniq)} GTIN из iiko")
        for idx, g in enumerate(uniq):
            for page in range(SEARCH_GTIN_MAX_PAGES):
                resp = _search_by_gtins(token, groups, [g], page)
                items = resp.get("result", [])
                if not items:
                    break
                for it in items:
                    _accumulate_code(by_gtin, mod_to_place, token, it, groups[0], upd_map)
                if resp.get("isLastPage") or len(items) < 100:
                    break
            if (idx + 1) % 100 == 0:
                print(f"  ... {idx + 1}/{len(uniq)} GTIN, найдено {len(by_gtin)}")
        print(f"  [SEARCH] точечно: запрошено {len(uniq)}, найдено {len(by_gtin)} GTIN, "
              f"{len(mod_to_place)} МОД")
    else:
        # БРОД (fallback без списка GTIN): потоковая выгрузка с early-stop по
        # сходимости партий. Покрывает лишь высокообъёмные GTIN — для боевого сбора
        # нужен список gtins (его готовит /api/chz/refresh из остатков iiko).
        date_to = datetime.now()
        date_from = date_to - timedelta(days=days)
        seen_batches = set()
        total = 0
        for g in groups:
            no_new_pages = 0
            for page in range(MAX_SEARCH_PAGES_PER_GROUP):
                st, resp, _ = search_cises(
                    token=token, page=page, limit=100,
                    product_group=g, date_from=date_from, date_to=date_to,
                )
                items = resp.get("result", []) if isinstance(resp, dict) else []
                if not items:
                    break
                new_here = 0
                for it in items:
                    total += 1
                    bk = _accumulate_code(by_gtin, mod_to_place, token, it, g, upd_map)
                    if bk and bk not in seen_batches:
                        seen_batches.add(bk)
                        new_here += 1
                if new_here == 0:
                    no_new_pages += 1
                    if no_new_pages >= SEARCH_CONVERGE_PAGES:
                        print(f"  [{g}] сходимость на стр.{page + 1} (просмотрено {total})")
                        break
                else:
                    no_new_pages = 0
                if resp.get("isLastPage") or len(items) < 100:
                    break

    if not by_gtin:
        print("  /cises/search не вернул кодов")
        return []

    # Названия по GTIN
    names = get_product_names(list(by_gtin.keys()))
    for gtin, e in by_gtin.items():
        info = names.get(gtin, {})
        e["name"] = info.get("name") or info.get("fullName") or ""
        e["brand"] = info.get("brand") or ""

    def _batches_to_list(bd):
        out = [
            {"production_date": p, "expiration_date": x, "count": c}
            for (p, x), c in bd.items()
        ]
        out.sort(key=lambda b: b["production_date"], reverse=True)
        return out

    stock = []
    for entry in by_gtin.values():
        by_kpp_out = []
        for slot in entry["by_kpp"].values():
            by_kpp_out.append({
                "kpp": slot["kpp"],
                "fiasId": slot["fiasId"],
                "count": slot["count"],
                "batches": _batches_to_list(slot["batches"]),
            })
        by_kpp_out.sort(key=lambda s: -s["count"])
        stock.append({
            **{k: v for k, v in entry.items() if k not in ("batches", "by_kpp")},
            "expiration_dates": sorted(entry["expiration_dates"]),
            "production_dates": sorted(entry["production_dates"]),
            "batches": _batches_to_list(entry["batches"]),
            "by_kpp": by_kpp_out,
        })
    stock.sort(key=lambda x: x["count"], reverse=True)
    print(f"  [SEARCH] итог: {len(stock)} GTIN, {len(mod_to_place)} МОД")
    return stock


def print_stock_report(stock):
    """Напечатать отчёт по остаткам ЧЗ: название — количество — срок"""
    if not stock:
        print("\n  Нет данных")
        return

    print(f"\n{'='*80}")
    print(f"  ОСТАТКИ ЧЗ: {ORG_NAME} (ИНН {INN_ORG})")
    print(f"{'='*80}")
    total_count = sum(s["count"] for s in stock)
    print(f"  Уникальных GTIN: {len(stock)}")
    print(f"  Всего кодов в обороте: {total_count}")

    # Сохранить JSON
    data_file = os.path.join(DEBUG_DIR, "chz_stock.json")
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(stock, f, indent=2, ensure_ascii=False,
                  default=lambda x: list(x) if isinstance(x, set) else x)

    # Таблица
    print(f"\n  {'GTIN':<16} {'Название':<35} {'Кол':>4}  {'Срок годности':<12}")
    print(f"  {'-'*78}")

    for s in stock:
        name = s.get("name") or s.get("fullName") or s.get("brand") or "?"
        # Обрезаем длинные названия
        if len(name) > 33:
            name = name[:32] + ".."
        exp = ", ".join(s["expiration_dates"])
        if len(exp) > 12:
            exp = exp[:11] + ".."
        try:
            print(f"  {s['gtin']:<16} {name:<35} {s['count']:>4}  {exp:<12}")
        except UnicodeEncodeError:
            # Windows console (cp1251/cp866) не умеет некоторые символы — пропускаем
            print(f"  {s['gtin']:<16} <name with unprintable chars>      {s['count']:>4}  {exp:<12}")

    print(f"\n  FILE: {data_file}")


# ==================== CLI ====================

def print_help():
    print("\nИспользование:")
    print(f"  python chz.py token              — получить/обновить токен")
    print(f"  python chz.py participants       — проверить участников")
    print(f"  python chz.py search             — поиск кодов (30 дней)")
    print(f"  python chz.py search 2026-03-01  — поиск с даты до сегодня")
    print(f"  python chz.py search 2026-03-01 2026-04-05  — период")
    print(f"  python chz.py report             — полный отчёт + загрузка всех данных")
    print(f"  python chz.py report 2026-03-01  — отчёт с даты")
    print(f"  python chz.py stock              — остатки: название, кол-во, срок (6 мес)")
    print(f"  python chz.py stock 2025-10-01   — остатки с даты")
    print(f"  python chz.py stock 2025-10-01 2026-04-05  — период")
    print(f"\nПараметры по умолчанию:")
    print(f"  группы = beer + nabeer + softdrinks")
    print(f"  период = последние 6 месяцев")
    print(f"  организация = {ORG_NAME} (ИНН {INN_ORG})")
    print(f"\nРабочая формула аутентификации:")
    print(f"  csptest -sfsign -sign -my THUMB -in DATA -out SIG -base64 -cades_strict -add")
    print(f"  POST /auth/simpleSignIn: {{\"uuid\": uuid, \"data\": подпись}}")
    print(f"  Токен: {TOKEN_FILE}")


def main():
    import sys
    args = sys.argv[1:]
    cmd = args[0] if args else "help"
    rest = args[1:]

    if cmd == "token":
        print("Обновляю токен...")
        result = get_token()
        if "error" in result:
            print(f"  [ERR] {result['error']}")
        else:
            exp = time.strftime('%Y-%m-%d %H:%M:%S',
                                time.localtime(result['expires_at']))
            print(f"  [OK] Токен действует до: {exp}")

    elif cmd == "participants":
        get_participants()

    elif cmd == "search":
        # python chz.py search [date_from] [date_to]
        date_from = rest[0] if rest else None
        date_to = rest[1] if len(rest) > 1 else None

        token = load_token()
        if not token:
            print("[ERR] Не удалось получить токен")
            return

        status, response, period = search_cises(
            token=token, page=0, limit=50,
            date_from=date_from, date_to=date_to
        )

        if status == 200:
            items = response.get("result", [])
            print(f"\n  [OK] Загружено: {len(items)} кодов")
            print_expiration_report(items)
        else:
            print(f"  [ERR] {status}: {response}")

    elif cmd == "report":
        # python chz.py report [date_from] [date_to]
        date_from = rest[0] if rest else None
        date_to = rest[1] if len(rest) > 1 else None

        items = get_all_cises(date_from=date_from, date_to=date_to)
        if items:
            print_expiration_report(items)

            # Сохранить полный JSON
            full_file = os.path.join(DEBUG_DIR, "expiration_full.json")
            with open(full_file, 'w', encoding='utf-8') as f:
                json.dump(items, f, indent=2, ensure_ascii=False,
                          default=lambda x: list(x) if isinstance(x, set) else x)
            print(f"\n  FILE: Все данные: {full_file}")
        else:
            print("  Нет данных")

    elif cmd == "stock":
        # python chz.py stock [date_from] [date_to]
        date_from = rest[0] if rest else None
        date_to = rest[1] if len(rest) > 1 else None

        stock = get_chz_stock(date_from=date_from, date_to=date_to)
        print_stock_report(stock)

    elif cmd == "csv":
        # python chz.py csv — построить chz_stock.json из CSV-экспортов
        print("Чтение CSV-экспортов из chz_test/debug/pg*_csv/...")
        stock = parse_chz_csv()
        print_stock_report(stock)

    elif cmd == "csv-auto":
        # python chz.py csv-auto [groups...] — авто-выгрузка CSV через dispenser API
        # По умолчанию: beer + nabeer + softdrinks (без water/milk/alcohol).
        # Только status=INTRODUCED — APPLIED не работает с participantInn=наш
        # (коды APPLIED принадлежат producer-у, не нам).
        # Импортные/неподписанные через ЭДО бутылки в этом отчёте НЕ ВИДНЫ —
        # они числятся за поставщиком до подписания УПД на наш ИНН.
        groups_arg = rest if rest else DEFAULT_AUTO_GROUPS
        token = load_token()
        if not token:
            print("[ERR] Нет токена")
            return
        ok_count = 0
        for g in groups_arg:
            code = DISPENSER_GROUPS.get(g)
            if not code:
                print(f"[SKIP] неизвестная группа: {g}")
                continue
            if export_csv_via_dispenser(token, g, code, status="INTRODUCED"):
                ok_count += 1
        print(f"\nИтог: {ok_count}/{len(groups_arg)} групп выгружено")
        if ok_count > 0:
            print("Перестраиваем chz_stock.json...")
            stock = parse_chz_csv()
            print_stock_report(stock)

    elif cmd == "search-stock":
        # python chz.py search-stock [days] [groups...]
        # Остатки ЧЗ через /cises/search (с 2026-06: коды сразу RETIRED/OWN_USE,
        # dispenser-выгрузка по RETIRED виснет — тянем синхронным API).
        days = SEARCH_STOCK_WINDOW_DAYS
        groups_arg = None
        if rest:
            if rest[0].isdigit():
                days = int(rest[0])
                groups_arg = rest[1:] or None
            else:
                groups_arg = rest
        # Список нужных GTIN (что бар реально держит на остатке) готовит прод из iiko
        # и кладёт рядом (needed_gtins.json). Есть список → точечный режим (полное
        # покрытие); нет → брод (только высокообъёмные GTIN, для дев/отладки).
        needed = None
        needed_path = os.path.join(DEBUG_DIR, "needed_gtins.json")
        if os.path.exists(needed_path):
            try:
                with open(needed_path, encoding="utf-8") as f:
                    needed = json.load(f)
            except Exception as e:
                print(f"[WARN] не прочитал {needed_path}: {e}")
        mode = (f"точечно по iiko ({len(needed)} GTIN)" if needed
                else f"брод, окно {days}д")
        print(f"Остатки ЧЗ через /cises/search ({mode})...")
        stock = get_chz_stock_via_search(product_groups=groups_arg, days=days, gtins=needed)
        # Защита: не затирать рабочий chz_stock.json пустым результатом
        # (например при сбое токена/сети). Пустой ответ — оставляем старый файл.
        if not stock:
            print("[WARN] пустой результат — chz_stock.json НЕ перезаписан")
        else:
            print_stock_report(stock)

    elif cmd == "upd-map":
        # python chz.py upd-map — вручную обновить карту cis->КПП из УПД (диагностика).
        # В боевом режиме карта обновляется автоматически внутри search-stock.
        token = load_token()
        if not token:
            print("[ERR] Нет токена")
            return
        m = refresh_upd_kpp_map(token)
        by_kpp_cnt = {}
        for v in m.values():
            by_kpp_cnt[v] = by_kpp_cnt.get(v, 0) + 1
        print(f"Карта УПД: {len(m)} кодов; по КПП: {by_kpp_cnt}")

    elif cmd == "mods":
        # python chz.py mods — справочник МОД (мест осуществления деятельности)
        token = load_token()
        if not token:
            print("[ERR] Нет токена")
            return
        url = (
            f"{CHZ_BASE_URL}/mods/list"
            f"?productGroups=beer&inns={INN_ORG}&limit=1000&page=0"
        )
        headers = {"Authorization": f"Bearer {token}"}
        status, resp = make_request(url, method="GET", headers=headers)
        if status != 200:
            print(f"  [ERR] HTTP {status}: {resp}")
            return
        out_file = os.path.join(DEBUG_DIR, "mods.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(resp, f, ensure_ascii=False, indent=2)
        result = resp.get("result", [])
        print(f"  [OK] МОД для ИНН {INN_ORG}: найдено {len(result)}")
        for m in result:
            print(f"    KPP={m.get('kpp')} | fiasId={m.get('fiasId')}")
            print(f"      address: {m.get('address')}")
            print(f"      productGroups: {m.get('productGroups')}")
        print(f"\n  FILE: {out_file}")

    else:
        print_help()


if __name__ == "__main__":
    main()
