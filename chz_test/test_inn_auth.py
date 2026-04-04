"""
Тест: Аутентификация с ИНН вместо случайной строки
Документация говорит: "При unitedToken=true передаётся случайный набор данных,
либо ИНН организации для авторизации с МЧД"
"""

import urllib.request
import urllib.error
import json
import ssl
import subprocess
import os
import base64

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")

# ИНН из сертификата (СНИЛС: 15626094269, ИНН: 781421365746)
INN = "781421365746"

os.makedirs(DEBUG_DIR, exist_ok=True)

def make_request(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    if data and isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))

    try:
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

print("=" * 80)
print("ТЕСТ: Аутентификация с ИНН")
print("=" * 80)

# Шаг 1: Получаем UUID (он не нужен для unitedToken=true, но получим для отладки)
print("\n1. Получение UUID от ЧЗ API...")
status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
print(f"   Статус: {status}")
uuid = auth_data.get('uuid', 'N/A')
print(f"   UUID: {uuid}")

# Шаг 2: Подписываем ИНН (вместо случайной строки)
print(f"\n2. Подпись ИНН: {INN}")

inn_file = os.path.join(DEBUG_DIR, "inn_to_sign.txt")
with open(inn_file, 'w', encoding='utf-8', newline='') as f:
    f.write(INN)

sig_file = os.path.join(DEBUG_DIR, "sig_inn.p7s")

# Команда: подписываем ИНН
cmd = f'"{CSP_PATH}" -sfsign -sign -my "{CERT_THUMBPRINT}" -in "{inn_file}" -out "{sig_file}"'
print(f"   Команда: {cmd}")

result = subprocess.run(
    cmd,
    shell=True,
    capture_output=True,
    timeout=60,
    encoding='cp866',
    creationflags=subprocess.CREATE_NO_WINDOW
)

if result.returncode == 0:
    print(f"   ✅ Подпись создана!")

    # Читаем бинарный файл и конвертируем в base64
    with open(sig_file, 'rb') as f:
        sig_bytes = f.read()

    signature_base64 = base64.b64encode(sig_bytes).decode('ascii')
    print(f"   Размер подписи: {len(signature_base64)} символов")

    # Сохраняем для отладки
    with open(os.path.join(DEBUG_DIR, "sig_inn_base64.txt"), 'w') as f:
        f.write(signature_base64)

    # Шаг 3: Отправляем в API с ИНН
    print(f"\n3. Отправка в ЧЗ API (ИНН={INN})...")

    # Формат 1: только data + unitedToken
    payload = {
        "data": signature_base64,
        "unitedToken": True
    }

    status, response = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        method="POST",
        data=payload
    )

    print(f"   Статус: {status}")

    if status == 200:
        print(f"\n🎉 УСПЕХ! Токен: {response}")
    else:
        error_msg = response.get('error_message', str(response))
        print(f"   ❌ ОШИБКА: {error_msg}")

        # Сохраняем ошибку
        with open(os.path.join(DEBUG_DIR, "error_inn.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "payload": payload,
                "response": response
            }, f, indent=2, ensure_ascii=False)
        print(f"   Детали сохранены в error_inn.json")

        # Пробуем Формат 2: с uuid + data + unitedToken
        print(f"\n4. Попытка #2: с uuid...")

        payload2 = {
            "uuid": uuid,
            "data": signature_base64,
            "unitedToken": True
        }

        status2, response2 = make_request(
            f"{CHZ_BASE_URL}/auth/simpleSignIn",
            method="POST",
            data=payload2
        )

        print(f"   Статус: {status2}")

        if status2 == 200:
            print(f"\n🎉 УСПЕХ! Токен: {response2}")
        else:
            error_msg2 = response2.get('error_message', str(response2))
            print(f"   ❌ ОШИБКА: {error_msg2}")

            with open(os.path.join(DEBUG_DIR, "error_inn_v2.json"), 'w', encoding='utf-8') as f:
                json.dump({
                    "status": status2,
                    "payload": payload2,
                    "response": response2
                }, f, indent=2, ensure_ascii=False)
            print(f"   Детали сохранены в error_inn_v2.json")
else:
    print(f"   ❌ ОШИБКА: {result.returncode}")
    print(f"   stderr: {result.stderr[:300] if result.stderr else 'пусто'}")

input("\nEnter для выхода...")
