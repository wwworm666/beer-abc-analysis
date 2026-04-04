"""
ШАГ 2: Тест запросов к ЧЗ API с готовыми подписями
Читать подписи из файлов и тестировать все комбинации
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
    """Загрузить подпись из файла и очистить"""
    path = os.path.join(DEBUG_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        sig = f.read()
    # Очистка до чистого base64
    return ''.join(c for c in sig if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

def load_text(filename):
    """Загрузить текст из файла"""
    path = os.path.join(DEBUG_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()

print("="*60)
print("ТЕСТ ЗАПРОСОВ К ЧЗ API")
print("="*60)

# Загружаем данные
uuid = load_text("uuid.txt")
data_to_sign = load_text("data.txt")

print(f"\nUUID: {uuid}")
print(f"DATA: {data_to_sign[:50]}...")

# Загружаем подписи
signatures = {}
for name, filename in [("attached", "sig1.txt"), ("detached", "sig2.txt"), ("simple", "sig3.txt")]:
    sig = load_signature(filename)
    if sig:
        signatures[name] = sig
        print(f"✅ {name}: {len(sig)} символов")
    else:
        print(f"❌ {name}: не найдено ({filename})")

if not signatures:
    print("\n❌ Нет подписей! Сначала запусти команды из get_auth.py")
    input("Enter для выхода...")
    exit(1)

# Форматы запросов
request_formats = [
    ("v2: uuid + data", lambda sig: {"uuid": uuid, "data": sig}),
    ("v2: uuid + data + inn", lambda sig: {"uuid": uuid, "data": sig, "inn": "7801630649"}),
    ("v3: data + unitedToken", lambda sig: {"data": sig, "unitedToken": True}),
    ("v3: uuid + data + unitedToken", lambda sig: {"uuid": uuid, "data": sig, "unitedToken": True}),
]

print("\n" + "="*60)
print("ТЕСТИРОВАНИЕ ЗАПРОСОВ")
print("="*60)

results = []

for sig_name, signature in signatures.items():
    print(f"\n{'='*50}")
    print(f"Подпись: {sig_name} ({len(signature)} символов)")
    print(f"{'='*50}")

    for fmt_name, fmt_func in request_formats:
        payload = fmt_func(signature)
        print(f"\n  → {fmt_name}...", end=" ")

        status, response = make_request(
            f"{CHZ_BASE_URL}/auth/simpleSignIn",
            method="POST",
            data=payload
        )

        if status == 200:
            print(f"✅ УСПЕХ!")
            print(f"     Токен: {response}")
            results.append((sig_name, fmt_name, True, str(response)[:100]))
        else:
            error_msg = response.get('error_message', str(response))[:60]
            print(f"❌ {error_msg}")
            results.append((sig_name, fmt_name, False, error_msg))

# Итоги
print("\n" + "="*60)
print("ИТОГИ")
print("="*60)

success = [r for r in results if r[2]]
if success:
    print("\n🎉 УСПЕШНЫЕ КОМБИНАЦИИ:")
    for sig_name, fmt_name, _, token in success:
        print(f"  ✅ {sig_name} + {fmt_name}")
else:
    print("\n❌ НИ ОДНА КОМБИНАЦИЯ НЕ СРАБОТАЛА")
    print("\nВсе ошибки:")
    for sig_name, fmt_name, _, error in results:
        print(f"  • {sig_name} + {fmt_name}: {error}")

print("\n" + "="*60)
input("Нажми Enter для выхода...")
