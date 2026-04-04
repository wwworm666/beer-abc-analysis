# -*- coding: utf-8 -*-
"""
Тест ВСЕХ форматов аутентификации ЧЗ API
Используем ГОТОВУЮ подпись из файла (не создаём новую)
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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

def load_text(filename):
    path = os.path.join(DEBUG_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()

def load_signature(filename):
    path = os.path.join(DEBUG_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        sig = f.read().strip()
    # Очистка до чистого base64
    return ''.join(c for c in sig if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

print("-" * 80)
print("ТЕСТ ВСЕХ ФОРМАТОВ АУТЕНТИФИКАЦИИ ЧЗ API")
print("-" * 80)

# Загружаем данные
uuid = load_text("uuid.txt")
data_to_sign = load_text("data_to_sign.txt")
signature = load_signature("sig_attached.txt")

if not uuid or not data_to_sign or not signature:
    print("[ERROR] Ne naideny faily v debug/")
    print("   Сначала запусти chz_auth.py для получения данных и подписи")
    input("Enter для выхода...")
    exit(1)

print(f"\nДанные:")
print(f"  UUID: {uuid}")
print(f"  DATA: {data_to_sign}")
print(f"  Подпись: {len(signature)} символов")
print()

# ============================================================
# ТЕСТ 1: v3 формат (data + unitedToken=true) — ТЕКУЩИЙ
# ============================================================
print("-" * 80)
print("ТЕСТ 1: v3 формат (data + unitedToken=true)")
print("-" * 80)

payload1 = {
    "data": signature,
    "unitedToken": True
}

status1, resp1 = make_request(f"{CHZ_BASE_URL}/auth/simpleSignIn", "POST", payload1)
print(f"Статус: {status1}")
if status1 == 200:
    print(f"[SUCCESS] Token: {resp1}")
else:
    print(f"[ERROR] {resp1.get('error_message', resp1)}")

print()

# ============================================================
# ТЕСТ 2: v3 формат с unitedToken=false (без uuid)
# ============================================================
print("-" * 80)
print("ТЕСТ 2: v3 формат (data + unitedToken=false)")
print("-" * 80)

payload2 = {
    "data": signature,
    "unitedToken": False
}

status2, resp2 = make_request(f"{CHZ_BASE_URL}/auth/simpleSignIn", "POST", payload2)
print(f"Статус: {status2}")
if status2 == 200:
    print(f"✅ УСПЕХ! Токен: {resp2}")
else:
    print(f"❌ Ошибка: {resp2.get('error_message', resp2)}")

print()

# ============================================================
# ТЕСТ 3: v2 формат (uuid + data) — без inn
# ============================================================
print("-" * 80)
print("ТЕСТ 3: v2 формат (uuid + data)")
print("-" * 80)

payload3 = {
    "uuid": uuid,
    "data": signature
}

status3, resp3 = make_request(f"{CHZ_BASE_URL}/auth/simpleSignIn", "POST", payload3)
print(f"Статус: {status3}")
if status3 == 200:
    print(f"✅ УСПЕХ! Токен: {resp3}")
else:
    print(f"❌ Ошибка: {resp3.get('error_message', resp3)}")

print()

# ============================================================
# ТЕСТ 4: v2 формат (uuid + data + inn)
# ============================================================
print("-" * 80)
print("ТЕСТ 4: v2 формат (uuid + data + inn)")
print("-" * 80)

payload4 = {
    "uuid": uuid,
    "data": signature,
    "inn": "7801630649"
}

status4, resp4 = make_request(f"{CHZ_BASE_URL}/auth/simpleSignIn", "POST", payload4)
print(f"Статус: {status4}")
if status4 == 200:
    print(f"✅ УСПЕХ! Токен: {resp4}")
else:
    print(f"❌ Ошибка: {resp4.get('error_message', resp4)}")

print()

# ============================================================
# ТЕСТ 5: v3 формат (uuid + data + unitedToken=true)
# ============================================================
print("-" * 80)
print("ТЕСТ 5: v3 формат (uuid + data + unitedToken=true)")
print("-" * 80)

payload5 = {
    "uuid": uuid,
    "data": signature,
    "unitedToken": True
}

status5, resp5 = make_request(f"{CHZ_BASE_URL}/auth/simpleSignIn", "POST", payload5)
print(f"Статус: {status5}")
if status5 == 200:
    print(f"✅ УСПЕХ! Токен: {resp5}")
else:
    print(f"❌ Ошибка: {resp5.get('error_message', resp5)}")

print()

# ============================================================
# ТЕСТ 6: v3 формат (data=ИНН + unitedToken=true)
# ============================================================
print("-" * 80)
print("ТЕСТ 6: v3 формат (data=ИНН + unitedToken=true)")
print("-" * 80)
print("Примечание: подписываем ИНН вместо data из API")

# Для этого теста нужна подпись ИНН — пропускаем если нет
inn_sig_file = os.path.join(DEBUG_DIR, "sig_inn.txt")
if os.path.exists(inn_sig_file):
    inn_sig = load_signature("sig_inn.txt")
    payload6 = {
        "data": inn_sig,
        "unitedToken": True
    }
    status6, resp6 = make_request(f"{CHZ_BASE_URL}/auth/simpleSignIn", "POST", payload6)
    print(f"Статус: {status6}")
    if status6 == 200:
        print(f"✅ УСПЕХ! Токен: {resp6}")
    else:
        print(f"❌ Ошибка: {resp6.get('error_message', resp6)}")
else:
    print("⊘ ПРОПУЩЕНО: нет файла sig_inn.txt")

print()

# ============================================================
# ИТОГИ
# ============================================================
print("-" * 80)
print("ИТОГИ:")
print("-" * 80)

results = [
    ("v3: data + unitedToken=true", status1, "❌" if status1 != 200 else "✅"),
    ("v3: data + unitedToken=false", status2, "❌" if status2 != 200 else "✅"),
    ("v2: uuid + data", status3, "❌" if status3 != 200 else "✅"),
    ("v2: uuid + data + inn", status4, "❌" if status4 != 200 else "✅"),
    ("v3: uuid + data + unitedToken=true", status5, "❌" if status5 != 200 else "✅"),
]

for name, status, mark in results:
    print(f"{mark} {name}: {status}")

print()
print("-" * 80)
input("Enter для выхода...")
