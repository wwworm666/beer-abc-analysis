# -*- coding: utf-8 -*-
"""
Честный ЗНАК — единый клиент для аутентификации и получения данных.

Рабочая комбинация аутентификации:
  csptest.exe -sfsign -sign -detached -my %THUMB% -in %DATA% -out %SIG% -base64 -cades_strict -add
  POST /auth/simpleSignIn: {"uuid": "...", "data": "подпись"}

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

def make_request(url, method="GET", data=None, headers=None):
    """HTTP запрос к ЧЗ API"""
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
        response = opener.open(req, timeout=60)
        body = response.read().decode('utf-8')
        return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        try:
            return e.code, json.loads(error_body)
        except:
            return e.code, {"_raw": error_body[:500]}
    except Exception as ex:
        return None, str(ex)


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
    2. csptest.exe -sfsign -sign -detached -my THUMB -in DATA -out SIG -base64 -cades_strict -add
    3. POST /auth/simpleSignIn {"uuid": uuid, "data": подпись} → токен

    Возвращает: {"token": "eyJ...", "expires_at": 1234567890}
               или {"error": "описание ошибки"}
    """
    os.makedirs(DEBUG_DIR, exist_ok=True)

    # 1. Получить uuid + data
    print("  [auth] Запрос UUID и DATA...", end=" ")
    status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
    if status != 200:
        print(f"❌ GET /auth/key: {auth_data}")
        return {"error": f"auth/key failed ({status}): {auth_data}"}

    uuid = auth_data.get('uuid')
    data_to_sign = auth_data.get('data')
    if not uuid or not data_to_sign:
        return {"error": f"No uuid/data: {auth_data}"}
    print(f"✅ {uuid[:8]}...")

    # 2. Сохранить данные
    data_file = os.path.join(DEBUG_DIR, "_data_to_sign.txt")
    sig_file = os.path.join(DEBUG_DIR, "_signature.txt")
    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    # 3. Подписать
    cmd = (f'"{CSP_PATH}" -sfsign -sign -detached '
           f'-my "{CERT_THUMBPRINT}" '
           f'-in "{data_file}" -out "{sig_file}" '
           f'-base64 -cades_strict -add')

    print(f"  [auth] Подпись...", end=" ")
    result = subprocess.run(cmd, shell=True, capture_output=True,
                            timeout=60, encoding='cp866',
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        print(f"❌ csptest rc={result.returncode}")
        return {"error": f"csptest failed ({result.returncode}): {result.stderr[:200]}"}
    print(f"✅")

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
        print(f"✅ действует до {exp_str}")
        return token_data
    else:
        error_msg = response.get('error_message', str(response))
        print(f"❌ {status}: {error_msg}")
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
        except:
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
        print(f"  ❌ {status}: {response}")

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
                  delay_between_pages=2):
    """
    Загрузить ВСЕ коды маркировки (со всеми страницами).

    Returns: список словарей с полями:
        cis, gtin, status, expirationDate, productionDate,
        introducedDate, producerInn, modId
    """
    token = load_token()
    if not token:
        return []

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

    all_items = []
    current_page = 0
    limit = 100

    while True:
        print(f"  Страница {current_page + 1}...", end=" ")
        status, response, _ = search_cises(
            token=token, page=current_page, limit=limit,
            product_group=product_group,
            date_from=date_from, date_to=date_to
        )

        if status != 200:
            print(f"❌ HTTP {status}")
            time.sleep(10)
            continue

        items = response.get("result", [])
        is_last = response.get("isLastPage", True)
        all_items.extend(items)
        print(f"✅ +{len(items)} (всего {len(all_items)})")

        if is_last or len(items) < limit or len(all_items) >= 3000:
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
        print(f"\n  ─{'─'*68}")
        print(f"  GTIN:       {g['gtin']}")
        print(f"  Производитель: {g['producer']}")
        print(f"  Кодов:       {g['count']}")
        print(f"  Срок годности: {', '.join(sorted(g['expiration_dates']))}")
        print(f"  Дата произв.:  {', '.join(sorted(g['production_dates']))}")
        print(f"  MOD ID(s):     {', '.join(sorted(g['mod_ids']))}")

    print(f"\n  📄 Подробная сводка: {data_file}")


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
    print(f"\nПараметры по умолчанию:")
    print(f"  product_group = beer")
    print(f"  период = последние 30 дней")
    print(f"  организация = {ORG_NAME} (ИНН {INN_ORG})")
    print(f"\nРабочая формула аутентификации:")
    print(f"  csptest -sfsign -sign -detached -my THUMB -in DATA -out SIG -base64 -cades_strict -add")
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
            print(f"  ❌ {result['error']}")
        else:
            exp = time.strftime('%Y-%m-%d %H:%M:%S',
                                time.localtime(result['expires_at']))
            print(f"  ✅ Токен действует до: {exp}")

    elif cmd == "participants":
        get_participants()

    elif cmd == "search":
        # python chz.py search [date_from] [date_to]
        date_from = rest[0] if rest else None
        date_to = rest[1] if len(rest) > 1 else None

        token = load_token()
        if not token:
            print("❌ Не удалось получить токен")
            return

        status, response, period = search_cises(
            token=token, page=0, limit=50,
            date_from=date_from, date_to=date_to
        )

        if status == 200:
            items = response.get("result", [])
            print(f"\n  ✅ Загружено: {len(items)} кодов")
            print_expiration_report(items)
        else:
            print(f"  ❌ {status}: {response}")

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
            print(f"\n  📄 Все данные: {full_file}")
        else:
            print("  Нет данных")

    else:
        print_help()


if __name__ == "__main__":
    main()
