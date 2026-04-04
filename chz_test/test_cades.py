"""
Тест CAdES-BES подписи для ЧЗ API
Используем -cades флаг для правильного формата
"""

import urllib.request
import urllib.error
import json
import ssl
import subprocess
import tempfile
import os

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"

def make_request(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    if data and isinstance(data, dict):
        data = json.dumps(data).encode('utf-8')
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

def sign_cades_bes(data_to_sign: str) -> str:
    """CAdES-BES подпись через -sfsign -cades -detached"""
    temp_dir = tempfile.gettempdir()
    data_file = os.path.join(temp_dir, "chz_data.txt")
    sig_file = os.path.join(temp_dir, "chz_sig.txt")
    out_file = os.path.join(temp_dir, "chz_out.txt")

    # Сохраняем данные БЕЗ newline в конце
    with open(data_file, 'wb') as f:
        f.write(data_to_sign.encode('utf-8'))

    # CAdES-BES detached signature
    cmd = f'"{CSP_PATH}" -sfsign -sign -cades -detached -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}" -base64'
    print(f"Команда: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, timeout=60, encoding='cp866')

    print(f"Код возврата: {result.returncode}")
    if result.stdout:
        print(f"STDOUT: {result.stdout[:500]}")
    if result.stderr:
        print(f"STDERR: {result.stderr[:500]}")

    if result.returncode != 0:
        return None

    with open(sig_file, 'r', encoding='utf-8') as f:
        signature = f.read()

    # Очистка до одной строки base64
    signature = ''.join(c for c in signature if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

    print(f"Подпись создана: {len(signature)} символов")

    # Сохраняем для отладки
    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    with open(os.path.join(debug_dir, "cades_data.txt"), 'w', encoding='utf-8') as f:
        f.write(data_to_sign)
    with open(os.path.join(debug_dir, "cades_sig.txt"), 'w', encoding='utf-8') as f:
        f.write(signature)

    return signature

# Шаг 1: Получаем uuid и data
print("="*60)
print("ШАГ 1: Получение uuid и data для подписи")
print("="*60)
status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
print(f"Статус: {status}")

if status != 200:
    print(f"Ошибка: {auth_data}")
    input("Enter для выхода...")
    exit(1)

uuid = auth_data.get('uuid')
data_to_sign = auth_data.get('data')
print(f"UUID: {uuid}")
print(f"Data: '{data_to_sign}' (len={len(data_to_sign)})")

# Шаг 2: Создаём CAdES-BES подпись
print("\n" + "="*60)
print("ШАГ 2: Создание CAdES-BES подписи")
print("="*60)

signature = sign_cades_bes(data_to_sign)
if not signature:
    print("❌ Не удалось создать подпись")
    input("Enter для выхода...")
    exit(1)

# Шаг 3: Тестируем запрос
print("\n" + "="*60)
print("ШАГ 3: Отправка запроса")
print("="*60)

# Пробуем ОБА формата
test_cases = [
    ("v2: uuid + data", {"uuid": uuid, "data": signature}),
    ("v3: data + unitedToken", {"data": signature, "unitedToken": True}),
]

for name, payload in test_cases:
    print(f"\n--- {name} ---")
    status, response = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        method="POST",
        data=payload
    )
    print(f"Статус: {status}")
    if status == 200:
        print(f"✅ УСПЕХ! Токен получен!")
        print(f"Токен: {response}")
        input("Enter для выхода...")
        exit(0)
    else:
        print(f"Ошибка: {response}")

print("\n❌ Не получилось :(")
input("Enter для выхода...")
