"""
Получение токена Честный ЗНАК
Использует известные рабочие значения:
- Контейнер: SCARD\pkcs11_rutoken_ecp_46c444f8\2508151514-781421365746
- Отпечаток: 2297e52c1066bcaab8a9708a66935e56d9761fc2
"""

import subprocess
import urllib.request
import urllib.error
import json
import base64
import ssl
import os
import sys
from datetime import datetime

# ==================== КОНФИГУРАЦИЯ ====================

CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"

# РАБОЧИЕ ЗНАЧЕНИЯ (из certmgr -list и csptest -keys -enum)
KEY_CONTAINER = r"SCARD\pkcs11_rutoken_ecp_46c444f8\2508151514-781421365746"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"

print("=" * 60)
print("📡 ПОЛУЧЕНИЕ ТОКЕНА ЧЕСТНЫЙ ЗНАК")
print("=" * 60)
print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Сертификат: {CERT_THUMBPRINT}")
print(f"Контейнер: {KEY_CONTAINER}")
print()

# ==================== ШАГ 1: GET /auth/key ====================

print("=" * 60)
print("1️⃣ ПОЛУЧЕНИЕ UUID И СТРОКИ ДЛЯ ПОДПИСИ")
print("=" * 60)

try:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    opener = urllib.request.build_opener(https_handler)

    response = opener.open(f"{CHZ_BASE_URL}/auth/key", timeout=30)
    auth_data = json.loads(response.read().decode('utf-8'))

    uuid = auth_data.get('uuid')
    data_to_sign = auth_data.get('data')

    print(f"✅ UUID: {uuid}")
    print(f"✅ Data: {data_to_sign}")

except Exception as e:
    print(f"❌ Ошибка: {e}")
    input("\nНажмите Enter для выхода...")
    sys.exit(1)

# ==================== ШАГ 2: ПОДПИСЬ ДАННЫХ ====================

print("\n" + "=" * 60)
print("2️⃣ ПОДПИСЬ ДАННЫХ (CAdES-BES через csptest)")
print("=" * 60)

temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
os.makedirs(temp_dir, exist_ok=True)

data_file = os.path.join(temp_dir, "data.txt")
sig_file = os.path.join(temp_dir, "signature.txt")

try:
    # Сохраняем данные (RAW байты, без BOM, без newline)
    with open(data_file, 'wb') as f:
        f.write(data_to_sign.encode('utf-8'))

    print(f"📁 Данные сохранены: {data_file}")
    print(f"📄 Размер: {len(data_to_sign)} байт")

    # Команда подписи: -sfsign -sign создаёт присоединённую подпись (PKCS#7 с данными)
    sign_cmd = (
        f'"{CSP_PATH}" -sfsign -sign -my "{CERT_THUMBPRINT}" '
        f'-in "{data_file}" -out "{sig_file}" -base64'
    )

    print(f"\n🔧 Команда:")
    print(f"   {sign_cmd}")
    print(f"\n⏳ Подпись...")

    result = subprocess.run(
        sign_cmd,
        shell=True,
        capture_output=True,
        timeout=60,
        encoding='cp866'
    )

    if result.returncode != 0:
        print(f"❌ Ошибка подписи (код {result.returncode})")
        print(f"   {result.stderr[:300]}")
        input("\nНажмите Enter для выхода...")
        sys.exit(1)

    # Читаем подпись
    with open(sig_file, 'r', encoding='utf-8') as f:
        signature = f.read().strip()

    # Очищаем от лишних символов (оставляем только base64)
    signature = ''.join(c for c in signature
                       if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

    if len(signature) < 100:
        print(f"❌ Подпись слишком короткая: {len(signature)} символов")
        input("\nНажмите Enter для выхода...")
        sys.exit(1)

    print(f"✅ Подпись создана!")
    print(f"   Длина: {len(signature)} символов")
    print(f"   Начало: {signature[:60]}...")

    # Сохраняем для отладки
    with open(os.path.join(temp_dir, "signature_clean.txt"), 'w') as f:
        f.write(signature)

except Exception as e:
    print(f"❌ Ошибка: {e}")
    input("\nНажмите Enter для выхода...")
    sys.exit(1)

# ==================== ШАГ 3: POST /auth/simpleSignIn ====================

print("\n" + "=" * 60)
print("3️⃣ ОБМЕН ПОДПИСИ НА ТОКЕН")
print("=" * 60)

request_body = {
    "uuid": uuid,
    "data": signature  # Отправляем подпись в base64
}

print(f"📤 Запрос:")
print(f"   URL: {CHZ_BASE_URL}/auth/simpleSignIn")
print(f"   uuid: {uuid}")
print(f"   data: {signature[:50]}...")

try:
    json_data = json.dumps(request_body).encode('utf-8')

    req = urllib.request.Request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        data=json_data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        method="POST"
    )

    response = opener.open(req, timeout=30)
    token_data = json.loads(response.read().decode('utf-8'))

    if response.status == 200:
        token = token_data.get('token')
        print(f"\n🎉 ТОКЕН ПОЛУЧЕН!")
        print(f"   Токен: {token[:50]}...")
        print(f"   Длина: {len(token)} символов")

        # Сохраняем токен
        with open(os.path.join(temp_dir, "token.txt"), 'w') as f:
            f.write(token)
        print(f"📁 Токен сохранён: {os.path.join(temp_dir, 'token.txt')}")

        # ТЕСТОВЫЙ ЗАПРОС
        print("\n" + "=" * 60)
        print("🧪 ТЕСТОВЫЙ ЗАПРОС: /participants")
        print("=" * 60)

        test_req = urllib.request.Request(
            f"{CHZ_BASE_URL}/participants?inns=7801630649",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            },
            method="GET"
        )

        test_response = opener.open(test_req, timeout=30)
        test_data = json.loads(test_response.read().decode('utf-8'))

        print(f"✅ Статус: {test_response.status}")
        print(f"📊 Ответ:")
        print(json.dumps(test_data, indent=2, ensure_ascii=False)[:500])

    else:
        print(f"❌ Статус: {response.status}")
        print(f"   {token_data}")

except urllib.error.HTTPError as e:
    error_body = e.read().decode('utf-8') if e.fp else str(e)
    print(f"\n❌ HTTP {e.code}")
    print(f"   {error_body[:300]}")

    if e.code == 403:
        print("\n⚠️  Возможные причины:")
        print("   1. Подпись невалидна (не тот формат)")
        print("   2. Сертификат не связан с учётной записью ЧЗ")
        print("   3. Истёк срок действия сертификата")

except Exception as e:
    print(f"❌ Ошибка: {e}")

print("\n" + "=" * 60)
print("Тест завершён")
print("=" * 60)
input("\nНажмите Enter для выхода...")
