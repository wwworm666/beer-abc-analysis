"""
ШАГ 2: Отправить подписанные данные в ЧЗ API
Читать подпись из файла и отправлять запрос
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

def load_signature(filename):
    """Загрузить подпись из файла и очистить до base64 одной строкой"""
    path = os.path.join(DEBUG_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        sig = f.read()
    # Очистка до чистого base64 (удаляем всё кроме символов base64)
    return ''.join(c for c in sig if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

def load_text(filename):
    """Загрузить текст из файла"""
    path = os.path.join(DEBUG_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()

print("=" * 80)
print("ШАГ 2: Отправка запроса на аутентификацию в ЧЗ API")
print("=" * 80)

# Загружаем данные
uuid = load_text("uuid.txt")
data_to_sign = load_text("data_to_sign.txt")

print(f"\nUUID: {uuid}")
print(f"DATA: {data_to_sign[:50]}...")

# Загружаем подпись
signature = load_signature("sig_attached.txt")

if not signature:
    print("\n❌ ОШИБКА: Файл sig_attached.txt не найден или пуст")
    print("   Сначала выполни команду подписи из step1_get_data.py")
    input("Enter для выхода...")
    exit(1)

print(f"\n✅ Подпись загружена: {len(signature)} символов")
print(f"   Начало: {signature[:50]}...")

# Формируем запрос (формат v3: data + unitedToken)
payload = {
    "data": signature,
    "unitedToken": True
}

# Сохраняем запрос для отладки
with open(os.path.join(DEBUG_DIR, "request_v3.json"), 'w', encoding='utf-8') as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)

print(f"\n✅ Запрос сохранён в: {DEBUG_DIR}\\request_v3.json")

# Отправляем запрос
print(f"\nОтправка POST {CHZ_BASE_URL}/auth/simpleSignIn")
print(f"Payload: data={signature[:50]}..., unitedToken=True")

status, response = make_request(
    f"{CHZ_BASE_URL}/auth/simpleSignIn",
    method="POST",
    data=payload
)

print(f"\nСтатус: {status}")

if status == 200:
    print(f"\n🎉 УСПЕХ! Токен: {response}")

    # Сохраняем токен
    with open(os.path.join(DEBUG_DIR, "token.json"), 'w', encoding='utf-8') as f:
        json.dump({"token": response}, f, indent=2)
    print(f"\n✅ Токен сохранён в: {DEBUG_DIR}\\token.json")
else:
    error_msg = response.get('error_message', str(response))
    print(f"\n❌ ОШИБКА: {error_msg}")

    # Сохраняем ошибку
    with open(os.path.join(DEBUG_DIR, "error.json"), 'w', encoding='utf-8') as f:
        json.dump({
            "status": status,
            "payload": payload,
            "response": response
        }, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Детали ошибки сохранены в: {DEBUG_DIR}\\error.json")

print("\n" + "=" * 80)
input("Нажми Enter для выхода...")
