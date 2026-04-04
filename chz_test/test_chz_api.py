"""
Тестовый скрипт для проверки работы с API Честный ЗНАК
Получение токена через simpleSignIn с правильной подписью CAdES-BES

Требования:
- Python 3.8+
- Рутокен с УКЭП вставлен в USB
- Установлен CryptoPro CSP 5.0+
- Интернет для доступа к API ЧЗ
"""

import urllib.request
import urllib.error
import json
import base64
import ssl
import sys
import subprocess
import tempfile
import os
from datetime import datetime

# ==================== КОНФИГУРАЦИЯ ====================

# URL API Честный ЗНАК
CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"

# ИНН вашей организации (для проверки)
YOUR_INN = "7801630649"

# Пути к утилитам CryptoPro
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"

# Контейнер ключа (полный путь из вывода certmgr)
KEY_CONTAINER = r"SCARD\pkcs11_rutoken_ecp_46c444f8\2508151514-781421365746"

# Отпечаток сертификата (SHA1) - из certmgr -list
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def make_request(url, method="GET", data=None, headers=None, timeout=60):
    """HTTP запросы через urllib"""
    if headers is None:
        headers = {}

    if data and isinstance(data, dict):
        data = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    elif data and isinstance(data, str):
        data = data.encode('utf-8')

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        https_handler = urllib.request.HTTPSHandler(context=ctx)
        opener = urllib.request.build_opener(https_handler)

        response = opener.open(req, timeout=timeout)
        status = response.status
        body = response.read().decode('utf-8')
        return status, json.loads(body) if body else {}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        try:
            return e.code, json.loads(error_body)
        except:
            return e.code, {"_raw": error_body[:500]}
    except urllib.error.URLError as e:
        return None, f"Ошибка подключения: {e.reason}"
    except Exception as e:
        return None, f"Ошибка: {e}"


def sign_data_cades_bes(data_to_sign: str) -> str | None:
    """
    Подпись данных в формате CAdES-BES через csptest.exe
    Для /auth/simpleSignIn нужна присоединённая подпись (данные + подпись в одном PKCS#7)

    Возвращает: signature (base64 одной строкой) или None
    """
    temp_dir = tempfile.gettempdir()
    data_file = os.path.join(temp_dir, "chz_sign_data.txt")
    sig_file = os.path.join(temp_dir, "chz_signature.txt")
    out_file = os.path.join(temp_dir, "chz_sign_out.txt")

    try:
        # 1. Сохраняем данные для подписи (RAW байты, без BOM, без newline!)
        # Точно как echo|set /p=DATA > file
        print(f"   Данные для подписи: '{data_to_sign}' (len={len(data_to_sign)})")
        with open(data_file, 'wb') as f:
            f.write(data_to_sign.encode('utf-8'))

        # 2. Создаём ПРИСОЕДИНЁННУЮ подпись (attached signature)
        # data должна содержать PKCS#7 с данными внутри (не detached!)
        sign_cmd = (
            f'"{CSP_PATH}" -sfsign -sign -my "{CERT_THUMBPRINT}" '
            f'-in "{data_file}" -out "{sig_file}" -base64'
        )
        print(f"   Создание присоединённой подписи...")
        print(f"   Команда: {sign_cmd}")

        result = subprocess.run(
            sign_cmd,
            shell=True,
            timeout=60,
            encoding='cp866',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        if result.returncode != 0:
            print(f"   ❌ Ошибка подписи (код {result.returncode})")
            stderr_output = result.stderr.strip()
            if stderr_output:
                print(f"   {stderr_output}")
            return None

        # 3. Читаем подпись из файла
        signature = None
        try:
            with open(sig_file, 'r', encoding='utf-8') as f:
                signature = f.read().strip()
        except FileNotFoundError:
            print(f"   ❌ Файл подписи не создан: {sig_file}")
            return None

        if not signature:
            print(f"   ❌ Подпись пуста")
            return None

        # 4. Очищаем: оставляем ТОЛЬКО base64 символы (удаляем \r\n, пробелы, заголовки)
        signature = ''.join(c for c in signature
                          if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

        if len(signature) < 100:
            print(f"   ❌ Подпись слишком короткая: {len(signature)} символов")
            return None

        print(f"   ✅ Подпись CAdES-BES создана ({len(signature)} символов)")

        # ОТЛАДКА: Сохраняем файлы для проверки
        debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, "data_to_sign.txt"), 'w', encoding='utf-8') as f:
            f.write(data_to_sign)
        with open(os.path.join(debug_dir, "signed_data.txt"), 'w', encoding='utf-8') as f:
            f.write(signature)
        print(f"   📁 Файлы сохранены в {debug_dir}")

        return signature

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return None

    finally:
        # Очистка временных файлов
        for fname in [data_file, sig_file, out_file]:
            try:
                if os.path.exists(fname):
                    os.unlink(fname)
            except:
                pass


def check_internet():
    """Проверка подключения к ЧЗ"""
    try:
        import socket
        ip = socket.gethostbyname('markirovka.crpt.ru')
        print(f"✅ DNS: markirovka.crpt.ru → {ip}")

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        https_handler = urllib.request.HTTPSHandler(context=ctx)
        opener = urllib.request.build_opener(https_handler)

        response = opener.open(urllib.request.Request("https://markirovka.crpt.ru"), timeout=15)
        print(f"✅ HTTPS: OK (статус {response.status})")
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def get_token() -> str | None:
    """
    Получение токена через /auth/simpleSignIn

    Процесс:
    1. GET /auth/key - UUID и строка для подписи
    2. Подписать строку в формате CAdES-BES
    3. POST /auth/simpleSignIn с uuid, data, signature
    """
    print("\n" + "="*50)
    print("📡 ПОЛУЧЕНИЕ ТОКЕНА ЧЕСТНЫЙ ЗНАК")
    print("="*50)

    # Шаг 1: Получаем UUID и строку
    print("\n1️⃣ Получение UUID и строки для подписи...")
    status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")

    if status != 200:
        print(f"❌ Ошибка: {status}")
        print(f"   {auth_data}")
        return None

    uuid = auth_data.get('uuid')
    data_to_sign = auth_data.get('data')

    if not uuid or not data_to_sign:
        print(f"❌ Не получен uuid или data")
        return None

    print(f"   ✅ UUID: {uuid}")
    print(f"   ✅ Data (для подписи): {data_to_sign}")

    # Шаг 2: Подписываем строку (присоединённая подпись)
    print("\n2️⃣ Подпись данных (присоединённая подпись)...")
    signed_data = sign_data_cades_bes(data_to_sign)

    if not signed_data:
        print("   ❌ Не удалось подписать")
        return None

    # Шаг 3: Отправляем на обмен
    # v3 API требует: {"data": "PKCS#7 signature", "unitedToken": true}
    # uuid НЕ НУЖЕН для v3 API!
    print("\n3️⃣ Обмен на токен...")

    # Полный JSON для отладки
    request_json = json.dumps({
        "data": signed_data,
        "unitedToken": True
    }, indent=2)
    print(f"   Запрос:\n{request_json[:500]}...")

    # Сохраняем полный запрос в файл
    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    with open(os.path.join(debug_dir, "request.json"), 'w', encoding='utf-8') as f:
        f.write(request_json)

    status, token_data = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        method="POST",
        data={
            "data": signed_data,
            "unitedToken": True
        }
    )

    print(f"   Статус: {status}")

    if status == 200:
        token = token_data.get('token')
        if token:
            print(f"   ✅ ТОКЕН ПОЛУЧЕН!")
            print(f"   Токен: {token[:50]}...")
            print(f"   Срок действия: 10 часов")
            return token
        else:
            print(f"   ❌ Нет token в ответе: {token_data}")
            return None
    else:
        print(f"   ❌ Ошибка {status}: {token_data}")
        return None


def test_api(token: str):
    """Тестовый запрос к /participants"""
    print("\n" + "="*50)
    print("🧪 ТЕСТ API: /participants")
    print("="*50)

    status, data = make_request(
        f"{CHZ_BASE_URL}/participants?inns={YOUR_INN}",
        headers={"Authorization": f"Bearer {token}"}
    )

    print(f"Статус: {status}")
    if status == 200:
        print(f"✅ Успех:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"❌ Ошибка: {data}")


# ==================== ЗАПУСК ====================

if __name__ == "__main__":
    print("╔" + "="*48 + "╗")
    print("║  ЧЕСТНЫЙ ЗНАК API TEST               ║")
    print("║  Версия: CAdES-BES signature         ║")
    print("║  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "                  ║")
    print("╚" + "="*48 + "╝")

    print("\n🔍 ПРОВЕРКА СИСТЕМЫ")
    print("-" * 30)
    print(f"Python: {sys.version.split()[0]}")
    print(f"CSP: {CSP_PATH}")
    print(f"Container: {KEY_CONTAINER}")
    print(f"Cert: {CERT_THUMBPRINT}")

    if not check_internet():
        print("\n❌ НЕТ ИНТЕРНЕТА")
        input("\nEnter для выхода...")
        exit(1)

    token = get_token()

    if token:
        print("\n✅ ТОКЕН ПОЛУЧЕН!")
        test_api(token)
    else:
        print("\n❌ ТОКЕН НЕ ПОЛУЧЕН")
        print("\nВозможные причины:")
        print("1. Неверный отпечаток сертификата (CERT_THUMBPRINT)")
        print("2. Проблемы с CryptoPro CSP")
        print("3. Сертификат недействителен")

    print("\n" + "="*50)
    input("Enter для выхода...")
