"""
Тест: создаём присоединённую подпись (attached) вручную
Формируем PKCS#7 с данными внутри
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
print("ТЕСТ: Присоединённая подпись (Attached Signature)")
print("=" * 80)

# Шаг 1: Получаем данные
print("\n1. Получение UUID и DATA от ЧЗ API...")
status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
print(f"   Статус: {status}")

if status != 200:
    print(f"   ❌ ОШИБКА: {auth_data}")
    input("Enter для выхода...")
    exit(1)

uuid = auth_data.get('uuid')
data_to_sign = auth_data.get('data')

print(f"   UUID: {uuid}")
print(f"   DATA: '{data_to_sign}'")

# Шаг 2: Сохраняем данные (UTF-8 без BOM, без newline)
data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")
with open(data_file, 'w', encoding='utf-8', newline='') as f:
    f.write(data_to_sign)

print(f"\n2. Данные сохранены в {data_file}")

# Шаг 3: Пробуем создать ПРИСОЕДИНЁННУЮ подпись через csptest
# Ключ -sfsign -sign создаёт подпись в формате PKCS#7
# Но нам нужно чтобы данные были ВНУТРИ подписи

print("\n3. Создание присоединённой подписи...")

# Команда: -sfsign -sign создаёт PKCS#7 подпись
# Без -detached флаг означает attached по умолчанию
sig_file = os.path.join(DEBUG_DIR, "sig_attached.p7s")

cmd = f'"{CSP_PATH}" -sfsign -sign -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}"'
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

    print(f"   Размер: {len(sig_bytes)} байт")
    print(f"   Base64: {len(signature_base64)} символов")

    # Сохраняем для отладки
    with open(os.path.join(DEBUG_DIR, "sig_attached_base64.txt"), 'w') as f:
        f.write(signature_base64)

    # Шаг 4: Отправляем в API
    print("\n4. Отправка в ЧЗ API...")

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
        with open(os.path.join(DEBUG_DIR, "error_attached.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "payload": payload,
                "response": response
            }, f, indent=2, ensure_ascii=False)
        print(f"   Детали сохранены в error_attached.json")
else:
    print(f"   ❌ ОШИБКА: {result.returncode}")
    print(f"   stdout: {result.stdout[:300] if result.stdout else 'пусто'}")
    print(f"   stderr: {result.stderr[:300] if result.stderr else 'пусто'}")

input("\nEnter для выхода...")
