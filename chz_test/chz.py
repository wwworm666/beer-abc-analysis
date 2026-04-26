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

# Группы которые выгружаем по умолчанию (без water — у бара воды немного,
# можно явно указать `chz.py csv-auto water` если потребуется).
DEFAULT_AUTO_GROUPS = ["beer", "nabeer", "softdrinks", "alcohol"]


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


def export_csv_via_dispenser(token, group_name, group_code, filter_dict=None):
    """Полная цепочка: create → poll → get result_id → download → save CSV.

    Файл сохраняется в chz_test/debug/pg{group_code}_csv/auto-{timestamp}.csv
    """
    if filter_dict is None:
        filter_dict = {
            "participantInn": INN_ORG,
            "packageType": ["UNIT", "LEVEL1"],
            "status": "INTRODUCED",
        }

    print(f"\n[{group_name}/pg{group_code}] Создаём задание...")
    status, resp = dispenser_create_task(token, group_code, filter_dict)
    if status != 200:
        print(f"  [ERR] create_task HTTP {status}: {resp}")
        return False
    task_id = resp.get("id") or resp
    if isinstance(task_id, dict):
        task_id = task_id.get("id")
    print(f"  taskId: {task_id}")

    print(f"  Опрос статуса (макс. 10 минут)...")
    status, resp = dispenser_poll(token, task_id, group_code)
    if status != 200:
        print(f"  [ERR] poll HTTP {status}: {resp}")
        return False
    cur = resp.get("currentStatus")
    print(f"  Финальный статус: {cur}")
    if cur != "COMPLETED":
        print(f"  [SKIP] не COMPLETED, не качаем")
        return False

    print(f"  Получаем resultId...")
    status, result_id = dispenser_get_result_id(token, task_id, group_code)
    if status != 200 or not result_id:
        print(f"  [ERR] result_id: {status} {result_id}")
        return False
    print(f"  resultId: {result_id}")

    print(f"  Скачиваем файл...")
    status, content = dispenser_download(token, result_id, group_code)
    if status != 200:
        print(f"  [ERR] download HTTP {status}")
        return False
    if not isinstance(content, (bytes, bytearray)) or len(content) == 0:
        print(f"  [ERR] empty download")
        return False
    print(f"  Получено {len(content)} bytes")

    out_dir = os.path.join(DEBUG_DIR, f"pg{group_code}_csv")
    os.makedirs(out_dir, exist_ok=True)
    # Удалим старые auto-*.csv чтобы не плодить
    import glob as _glob
    for old in _glob.glob(os.path.join(out_dir, "auto-*.csv")):
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
        out_file = os.path.join(out_dir, f"auto-{int(time.time())}.csv")
        with open(out_file, "wb") as f:
            f.write(csv_bytes)
    else:
        out_file = os.path.join(out_dir, f"auto-{int(time.time())}.csv")
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
                # Только INTRODUCED + UNIT + наш ИНН
                if parts[status_i] != "INTRODUCED":
                    continue
                if parts[pkg_i] != "UNIT":
                    continue
                if parts[owner_i] != INN_ORG:
                    continue
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
        # По умолчанию: beer + nabeer + softdrinks + alcohol (без water/milk).
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
            if export_csv_via_dispenser(token, g, code):
                ok_count += 1
        print(f"\nИтог: {ok_count}/{len(groups_arg)} групп выгружено")
        if ok_count > 0:
            print("Перестраиваем chz_stock.json...")
            stock = parse_chz_csv()
            print_stock_report(stock)

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
