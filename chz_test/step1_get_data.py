"""
ШАГ 1: Получить UUID и DATA от ЧЗ API
Сохраняет данные и команду для подписи
"""

import urllib.request
import urllib.error
import json
import ssl
import os

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")

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
    except Exception as ex:
        return None, str(ex)

os.makedirs(DEBUG_DIR, exist_ok=True)

print("=" * 80)
print("ШАГ 1: Получение UUID и DATA от ЧЗ API")
print("=" * 80)

status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
print(f"Статус: {status}")

if status != 200:
    print(f"❌ ОШИБКА: {auth_data}")
    input("Enter для выхода...")
    exit(1)

uuid = auth_data.get('uuid')
data_to_sign = auth_data.get('data')

print(f"✅ UUID: {uuid}")
print(f"✅ DATA: '{data_to_sign}' (длина: {len(data_to_sign)})")

# Сохраняем данные (UTF-8 без BOM, без newline)
with open(os.path.join(DEBUG_DIR, "data_to_sign.txt"), 'w', encoding='utf-8', newline='') as f:
    f.write(data_to_sign)

with open(os.path.join(DEBUG_DIR, "uuid.txt"), 'w') as f:
    f.write(uuid)

print(f"\n✅ Данные сохранены в {DEBUG_DIR}")
print(f"   - data_to_sign.txt")
print(f"   - uuid.txt")

# Генерируем команду для подписи
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")
sig_file = os.path.join(DEBUG_DIR, "sig_attached.txt")

cmd = f'"{CSP_PATH}" -sign -my "{CERT}" -in "{data_file}" -out "{sig_file}" -base64'

print("\n" + "=" * 80)
print("ШАГ 2: Подпиши данные (команда для cmd)")
print("=" * 80)
print("\n1. Открой cmd (Win + R → cmd)")
print("2. Скопируй и выполни команду:")
print("-" * 80)
print(cmd)
print("-" * 80)
print("\n3. После выполнения скопируй содержимое файла:")
print(f"   {sig_file}")
print("\n4. Вставь подпись в файл sig_attached.txt (если команда не создала его автоматически)")

print("\n" + "=" * 80)
print("ШАГ 3: После подписи")
print("=" * 80)
print("\nЗапусти: python step2_send.py")

input("\nНажми Enter для выхода...")
