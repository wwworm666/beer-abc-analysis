"""
ШАГ 1: Получить UUID и DATA от ЧЗ API
Сохраняет данные и команды для подписи
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

# Создаём директорию
os.makedirs(DEBUG_DIR, exist_ok=True)

print("="*60)
print("ШАГ 1: Получение UUID и DATA от ЧЗ API")
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
print(f"DATA: '{data_to_sign}' (len={len(data_to_sign)})")

# Сохраняем данные
with open(os.path.join(DEBUG_DIR, "uuid.txt"), 'w') as f:
    f.write(uuid)

with open(os.path.join(DEBUG_DIR, "data.txt"), 'w', encoding='utf-8', newline='') as f:
    f.write(data_to_sign)

# Сохраняем данные для подписи (raw bytes без newline)
with open(os.path.join(DEBUG_DIR, "data_to_sign.raw"), 'wb') as f:
    f.write(data_to_sign.encode('utf-8'))

print(f"\nФайлы сохранены в {DEBUG_DIR}")
print(f"  - uuid.txt")
print(f"  - data.txt")
print(f"  - data_to_sign.raw")

# Генерируем команды для подписи
print("\n" + "="*60)
print("ШАГ 2: Команды для подписи (запустить вручную)")
print("="*60)

csp_path = r'"C:\Program Files\Crypto Pro\CSP\csptest.exe"'
cert = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
data_raw = os.path.join(DEBUG_DIR, "data_to_sign.raw")

commands = [
    ("TEST 1: Attached (присоединённая)",
     f'{csp_path} -sfsign -sign -my "{cert}" -in "{data_raw}" -out "{DEBUG_DIR}\\sig1.txt" -base64'),

    ("TEST 2: Detached (откреплённая)",
     f'{csp_path} -sfsign -sign -detached -my "{cert}" -in "{data_raw}" -out "{DEBUG_DIR}\\sig2.txt" -base64'),

    ("TEST 3: Simple (простая)",
     f'{csp_path} -sign -my "{cert}" -in "{data_raw}" -out "{DEBUG_DIR}\\sig3.txt" -base64'),
]

print("\nЗапусти эти команды по очереди в cmd:")
print("-"*60)
for name, cmd in commands:
    print(f"\n{name}:")
    print(f"  {cmd}")

print("\n" + "="*60)
print("ШАГ 3: После создания подписей")
print("="*60)
print("\n1. Запусти test_requests.py (следующий скрипт)")
print("2. Он протестирует все варианты запросов к API")

input("\nНажми Enter для выхода...")
