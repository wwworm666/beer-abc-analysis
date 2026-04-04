# -*- coding: utf-8 -*-
"""
Запрос сроков годности из ЧЗ API

Использует токен из debug/token.json для запроса остатков кодов маркировки
с датами годности.

Запускать из cmd ОТ ИМЕНИ АДМИНИСТРАТОРА
"""

import urllib.request, urllib.error, json, ssl, os

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")


def load_token():
    token_file = os.path.join(DEBUG_DIR, "token.json")
    if not os.path.exists(token_file):
        print("❌ Файл token.json не найден. Сначала запусти csptest_cades_auth.py")
        return None
    with open(token_file) as f:
        data = json.load(f)
    token = data.get("token", {}).get("token", data.get("token"))
    if not token:
        print("❌ Токен не найден в token.json")
        return None
    print(f"✅ Токен загружен: {token[:50]}...")
    return token


def make_request(url, method="GET", data=None, headers=None):
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
        https_handler = urllib.request.HTTPSHandler(context=ctx)
        opener = urllib.request.build_opener(https_handler)
        response = opener.open(req, timeout=60)
        return response.status, json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        try:
            return e.code, json.loads(error_body)
        except:
            return e.code, {"_raw": error_body[:500]}
    except Exception as ex:
        return None, str(ex)


def search_cises(token, page=0, limit=10):
    """Поиск кодов маркировки с датами годности

    Endpoint: POST /api/v4/true-api/cises/search
    Возвращает коды с полем expiration.expirationStorageDate
    """
    payload = {
        "page": page,
        "limit": limit,
        "filter": {
            "productGroups": ["beer"],
            "ownerInn": "7801630649"
        }
    }

    headers = {"Authorization": f"Bearer {token}"}
    url = "https://markirovka.crpt.ru/api/v4/true-api/cises/search"

    print(f"\nЗапрос: POST {url}")
    print(f"Payload: page={page}, limit={limit}")

    status, response = make_request(url, method="POST", data=payload, headers=headers)

    print(f"Статус: {status}")
    if status != 200:
        print(f"Ошибка: {json.dumps(response, indent=2, ensure_ascii=False)}")
        return status, response

    return status, response


def cises_info(token, cis_list):
    """Получить информацию по списку кодов

    Endpoint: POST /api/v3/true-api/cises/info
    Возвращает публичную информацию включая expirationDate
    """
    payload = {"cisList": cis_list}

    headers = {"Authorization": f"Bearer {token}"}
    url = f"{CHZ_BASE_URL}/cises/info"

    print(f"\nЗапрос: POST {url}")
    print(f"Кодов для запроса: {len(cis_list)}")

    status, response = make_request(url, method="POST", data=payload, headers=headers)

    print(f"Статус: {status}")
    if status != 200:
        print(f"Ошибка: {json.dumps(response, indent=2, ensure_ascii=False)}")
        return status, response

    return status, response


def check_participants(token):
    """Проверить участников по ИНН"""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{CHZ_BASE_URL}/participants?inns=7801630649"

    status, response = make_request(url, headers=headers)
    return status, response


def print_expiration(data):
    """Красивый вывод сроков годности"""
    print(f"\n{'=' * 80}")
    print(f"  СРОКИ ГОДНОСТИ")
    print(f"{'=' * 80}")

    products = data.get("products", [])
    if not products:
        print("  Нет данных о продуктах")
        return

    for i, product in enumerate(products, 1):
        cis = product.get("cis", "N/A")
        status_text = product.get("status", "N/A")
        gtin = product.get("gtin", "N/A")

        print(f"\n  [{i}] Код: {cis}")
        print(f"      Статус: {status_text}")
        print(f"      GTIN:   {gtin}")

        # expiration — массив с датами хранения
        expiration_list = product.get("expiration", [])
        if expiration_list:
            for exp in expiration_list:
                exp_date = exp.get("expirationStorageDate", "")
                cond_id = exp.get("storageConditionId", "")
                print(f"      Срок годности: {exp_date}")
                if cond_id:
                    print(f"      Условие хранения: {cond_id}")
        else:
            # Поле expirationDate на верхнем уровне
            exp_date = product.get("expirationDate", "")
            if exp_date:
                print(f"      Срок годности: {exp_date}")
            else:
                print(f"      Срок годности: не указан")

    # Информация о пагинации
    total = data.get("total")
    page = data.get("page")
    limit = data.get("limit")
    if total is not None:
        print(f"\n  Всего записей: {total}")
        print(f"  Страница: {page + 1}, Лимит: {limit}")


def save_report(status, response, filename):
    """Сохранить полный ответ"""
    report_file = os.path.join(DEBUG_DIR, filename)
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(response, f, indent=2, ensure_ascii=False)
    print(f"\n  Полный ответ сохранён: {report_file}")


def main():
    print("=" * 80)
    print("  ЧЗ API — Запрос сроков годности")
    print("=" * 80)

    token = load_token()
    if not token:
        input("\nНажми Enter для выхода...")
        return

    # ===== Шаг 1: Проверка участников =====
    print(f"\n{'─' * 80}")
    print(f"  [1] Проверка участников (participants)")
    print(f"{'─' * 80}")

    status, participants = check_participants(token)
    print(f"Статус: {status}")
    if status == 200:
        print(f"Ответ: {json.dumps(participants, indent=2, ensure_ascii=False)[:500]}")
        save_report(status, participants, "participants.json")
    else:
        print(f"Ошибка: {json.dumps(participants, indent=2, ensure_ascii=False)}")

    # ===== Шаг 2: Поиск кодов =====
    print(f"\n{'─' * 80}")
    print(f"  [2] Поиск кодов маркировки (cises/search)")
    print(f"{'─' * 80}")

    status, search_result = search_cises(token, page=0, limit=20)

    if status == 200:
        print_expiration(search_result)
        save_report(status, search_result, "cises_search.json")

        # Собираем первые 10 кодов для info-запроса
        products = search_result.get("products", [])
        if products:
            cis_codes = [p.get("cis") for p in products[:10] if p.get("cis")]

            if cis_codes:
                # ===== Шаг 3: Детальная информация =====
                print(f"\n{'─' * 80}")
                print(f"  [3] Детальная информация (cises/info)")
                print(f"{'─' * 80}")

                info_status, info_result = cises_info(token, cis_codes)

                if info_status == 200:
                    print(f"\nОтвет cises/info:")
                    print(json.dumps(info_result, indent=2, ensure_ascii=False)[:1000])
                    save_report(info_status, info_result, "cises_info.json")

    else:
        print(f"❌ Ошибка поиска: {json.dumps(search_result, indent=2, ensure_ascii=False)}")
        save_report(status or 0, search_result, "cises_error.json")

    print(f"\n{'=' * 80}")
    print(f"  Готово!")
    print(f"{'=' * 80}")
    input("\nНажми Enter для выхода...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ CRITICAL: {e}")
        import traceback
        traceback.print_exc()
