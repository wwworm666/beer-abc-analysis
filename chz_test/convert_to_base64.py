"""
Конвертирует бинарный файл подписи (.p7s) в base64 строку для отправки в ЧЗ API
"""

import base64
import os
import sys

DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")

# Путь к файлу подписи
sig_file = os.path.join(DEBUG_DIR, "sig_attached.p7s")

if not os.path.exists(sig_file):
    print(f"❌ Файл не найден: {sig_file}")
    print("\nИнструкция:")
    print("1. Открой C:\\chz_test\\debug\\ в Проводнике")
    print("2. Правой кнопкой на data_to_sign.txt → КриптоАРМ → Подписать")
    print("3. Выбери сертификат ВЕРЕЩАГИН ЕГОР ВЯЧЕСЛАВОВИЧ")
    print("4. Выбери ПРИСОЕДИНЁННАЯ подпись")
    print("5. Сохрани как sig_attached.p7s")
    print("6. Запусти этот скрипт снова")
    input("\nНажми Enter для выхода...")
    sys.exit(1)

# Читаем бинарный файл
with open(sig_file, 'rb') as f:
    sig_bytes = f.read()

# Конвертируем в base64
signature_base64 = base64.b64encode(sig_bytes).decode('ascii')

print(f"✅ Файл прочитан: {len(sig_bytes)} байт")
print(f"✅ Base64: {len(signature_base64)} символов")
print(f"\nНачало подписи:")
print(signature_base64[:100] + "...")

# Сохраняем в текстовый файл
output_file = os.path.join(DEBUG_DIR, "sig_attached_base64.txt")
with open(output_file, 'w') as f:
    f.write(signature_base64)

print(f"\n✅ Подпись сохранена в: {output_file}")

# Теперь пробуем отправить в ЧЗ API
print("\n" + "=" * 80)
print("ОТПРАВКА В ЧЗ API...")
print("=" * 80)

import urllib.request
import urllib.error
import json
import ssl

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"

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

# Получаем свежие данные от ЧЗ
print("\n1. Получение UUID и DATA от ЧЗ API...")
status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
print(f"   Статус: {status}")

if status != 200:
    print(f"   ❌ ОШИБКА: {auth_data}")
    input("Enter для выхода...")
    sys.exit(1)

uuid = auth_data.get('uuid')
data_to_sign = auth_data.get('data')
print(f"   DATA: '{data_to_sign}'")

# Проверяем что данные совпадают с теми что подписывали
data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")
if os.path.exists(data_file):
    with open(data_file, 'r', encoding='utf-8') as f:
        signed_data = f.read()

    if signed_data != data_to_sign:
        print(f"\n⚠️  ВНИМАНИЕ: Данные не совпадают!")
        print(f"   Подписывали: '{signed_data}'")
        print(f"   Получили от API: '{data_to_sign}'")
        print(f"\nНужно подписать АКТУАЛЬНЫЕ данные!")

        # Обновляем файл с данными
        with open(data_file, 'w', encoding='utf-8', newline='') as f:
            f.write(data_to_sign)

        print(f"\n✅ Файл {data_file} обновлён")
        print("   1. Подпиши его снова через КриптоАРМ")
        print("   2. Запусти этот скрипт ещё раз")
        input("\nНажми Enter для выхода...")
        sys.exit(1)
    else:
        print("   ✅ Данные совпадают с подписанными")

# Отправляем в API
print("\n2. Отправка подписи в ЧЗ API...")

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
    print(f"\n🎉 УСПЕХ! Токен получен:")
    print(f"   {response}")

    # Сохраняем токен
    token_file = os.path.join(DEBUG_DIR, "token.json")
    with open(token_file, 'w', encoding='utf-8') as f:
        json.dump({"token": response}, f, indent=2)
    print(f"\n✅ Токен сохранён в: {token_file}")
else:
    error_msg = response.get('error_message', str(response))
    print(f"\n❌ ОШИБКА: {error_msg}")

    # Сохраняем ошибку
    error_file = os.path.join(DEBUG_DIR, "error_kriptoarm.json")
    with open(error_file, 'w', encoding='utf-8') as f:
        json.dump({
            "status": status,
            "payload": payload,
            "response": response
        }, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Детали ошибки сохранены в: {error_file}")

input("\nНажми Enter для выхода...")
