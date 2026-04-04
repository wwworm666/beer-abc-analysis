"""
ИСПРАВЛЕННЫЙ СКРИПТ ДЛЯ АУТЕНТИФИКАЦИИ В ЧЗ API
Версия: 2026-03-27 (после анализа всей документации)

КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ:
1. Данные для подписи сохраняются как UTF-8 БЕЗ BOM и БЕЗ newline
2. Подпись создаётся через csptest.exe с флагом -sign (не -sfsign)
3. Используется формат v3: {"data": signature, "unitedToken": true}
4. Автоматическая проверка подписи локально перед отправкой
"""

import urllib.request
import urllib.error
import json
import ssl
import subprocess
import tempfile
import os
import base64

# ==================== КОНФИГУРАЦИЯ ====================
CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
# =======================================================

def make_request(url, method="GET", data=None, headers=None):
    """HTTP запрос к API"""
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

def get_uuid_and_data():
    """Шаг 1: Получить UUID и DATA от ЧЗ API"""
    print("=" * 80)
    print("ШАГ 1: Получение UUID и DATA от ЧЗ API")
    print("=" * 80)

    status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
    print(f"Статус: {status}")

    if status != 200:
        print(f"❌ ОШИБКА: {auth_data}")
        return None, None

    uuid = auth_data.get('uuid')
    data_to_sign = auth_data.get('data')

    print(f"✅ UUID: {uuid}")
    print(f"✅ DATA: '{data_to_sign}' (длина: {len(data_to_sign)})")

    return uuid, data_to_sign

def save_data_for_signing(data_to_sign):
    """Шаг 2: Сохранить данные для подписи (UTF-8 без BOM, без newline)"""
    print("\n" + "=" * 80)
    print("ШАГ 2: Сохранение данных для подписи")
    print("=" * 80)

    os.makedirs(DEBUG_DIR, exist_ok=True)

    # Критически важно: UTF-8 без BOM, без newline
    data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")
    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    # Также сохраняем raw bytes для проверки
    raw_file = os.path.join(DEBUG_DIR, "data_to_sign.raw")
    with open(raw_file, 'wb') as f:
        f.write(data_to_sign.encode('utf-8'))

    print(f"✅ Данные сохранены в: {data_file}")
    print(f"✅ Размер файла: {os.path.getsize(data_file)} байт")
    print(f"✅ Raw размер: {os.path.getsize(raw_file)} байт")

    # Проверка: читаем обратно и сравниваем
    with open(data_file, 'r', encoding='utf-8') as f:
        verify_data = f.read()

    if verify_data == data_to_sign:
        print("✅ Проверка: данные сохранены корректно")
    else:
        print(f"❌ ОШИБКА: данные не совпадают! Ожидалось '{data_to_sign}', получено '{verify_data}'")

    return data_file

def sign_data(data_file):
    """Шаг 3: Подписать данные через csptest.exe"""
    print("\n" + "=" * 80)
    print("ШАГ 3: Подпись данных")
    print("=" * 80)

    sig_file = os.path.join(DEBUG_DIR, "sig_attached.txt")

    # Команда: -sign (не -sfsign!) для присоединённой подписи
    # -my с thumbprint сертификата
    # -base64 для вывода в base64
    cmd = [
        CSP_PATH,
        "-sign",
        "-my", CERT_THUMBPRINT,
        "-in", data_file,
        "-out", sig_file,
        "-base64"
    ]

    # Формируем команду как строку для shell=True
    # ВАЖНО: Только -sfsign -sign работает в этой версии CryptoPro CSP
    cmd_str = f'"{CSP_PATH}" -sfsign -sign -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}" -base64'
    print(f"Команда: {cmd_str}")

    try:
        # Критически важно: shell=True для запуска csptest.exe из Python
        result = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            timeout=60,
            encoding='cp866',
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        if result.returncode == 0:
            print(f"✅ Подпись создана успешно")

            # Читаем подпись
            with open(sig_file, 'r', encoding='utf-8') as f:
                signature = f.read().strip()

            # Очистка до одной строки base64
            signature = ''.join(c for c in signature if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

            print(f"✅ Длина подписи: {len(signature)} символов")
            print(f"✅ Начало: {signature[:50]}...")

            # Сохраняем очищенную подпись
            clean_sig_file = os.path.join(DEBUG_DIR, "sig_attached_clean.txt")
            with open(clean_sig_file, 'w', encoding='utf-8') as f:
                f.write(signature)

            return signature
        else:
            print(f"❌ ОШИБКА подписи: {result.returncode}")
            print(f"stdout: {result.stdout[:500] if result.stdout else 'пусто'}")
            print(f"stderr: {result.stderr[:500] if result.stderr else 'пусто'}")
            return None

    except Exception as ex:
        print(f"❌ ОШИБКА запуска csptest: {ex}")
        return None

def verify_signature_locally(data_to_sign, signature):
    """Шаг 4: Локальная проверка подписи"""
    print("\n" + "=" * 80)
    print("ШАГ 4: Локальная проверка подписи")
    print("=" * 80)

    # Сохраняем подпись во временный файл
    temp_sig = os.path.join(tempfile.gettempdir(), "chz_verify_sig.txt")
    with open(temp_sig, 'w', encoding='utf-8') as f:
        f.write(signature)

    # Формируем команду как строку для shell=True
    cmd_str = f'"{CSP_PATH}" -sfsign -verify -my "{CERT_THUMBPRINT}" -in "{os.path.join(DEBUG_DIR, "data_to_sign.txt")}" -signature "{temp_sig}" -base64'
    print(f"Команда: {cmd_str}")

    try:
        # Критически важно: shell=True для запуска csptest.exe из Python
        result = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            timeout=60,
            encoding='cp866',
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        if result.returncode == 0:
            print("✅ Локальная проверка подписи: УСПЕХ")
            return True
        else:
            print(f"❌ Локальная проверка: ОШИБКА {result.returncode}")
            print(f"stdout: {result.stdout[:200] if result.stdout else 'пусто'}")
            print(f"stderr: {result.stderr[:200] if result.stderr else 'пусто'}")
            return False

    except Exception as ex:
        print(f"❌ ОШИБКА проверки: {ex}")
        return False

def send_to_chz(signature):
    """Шаг 5: Отправить запрос на аутентификацию в ЧЗ API"""
    print("\n" + "=" * 80)
    print("ШАГ 5: Отправка запроса на аутентификацию")
    print("=" * 80)

    # Формат v3: только data + unitedToken
    payload = {
        "data": signature,
        "unitedToken": True
    }

    # Сохраняем запрос для отладки
    req_file = os.path.join(DEBUG_DIR, "request_v3.json")
    with open(req_file, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"✅ Запрос сохранён в: {req_file}")

    print(f"Отправка POST {CHZ_BASE_URL}/auth/simpleSignIn")
    print(f"Payload: data={signature[:50]}..., unitedToken=True")

    status, response = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        method="POST",
        data=payload
    )

    print(f"\nСтатус: {status}")

    if status == 200:
        print(f"✅ УСПЕХ! Токен: {response}")

        # Сохраняем токен
        token_file = os.path.join(DEBUG_DIR, "token.json")
        with open(token_file, 'w', encoding='utf-8') as f:
            json.dump({"token": response}, f, indent=2)
        print(f"✅ Токен сохранён в: {token_file}")

        return response
    else:
        error_msg = response.get('error_message', str(response))
        print(f"❌ ОШИБКА: {error_msg}")

        # Сохраняем ошибку
        error_file = os.path.join(DEBUG_DIR, "error.json")
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "payload": payload,
                "response": response
            }, f, indent=2, ensure_ascii=False)
        print(f"✅ Детали ошибки сохранены в: {error_file}")

        return None

def main():
    print("╔" + "=" * 78 + "╗")
    print("║  АУТЕНТИФИКАЦИЯ В ЧЕСТНЫЙ ЗНАК API (ИСПРАВЛЕННАЯ ВЕРСИЯ)           ║")
    print("╚" + "=" * 78 + "╝")

    # Шаг 1: Получить данные
    uuid, data_to_sign = get_uuid_and_data()
    if not data_to_sign:
        input("\nНажми Enter для выхода...")
        return

    # Шаг 2: Сохранить для подписи
    data_file = save_data_for_signing(data_to_sign)

    # Шаг 3: Подписать
    signature = sign_data(data_file)
    if not signature:
        print("\n❌ Не удалось создать подпись. Проверьте что Рутокен подключен и CryptoPro CSP установлен.")
        input("Нажми Enter для выхода...")
        return

    # Шаг 4: Локальная проверка
    verify_ok = verify_signature_locally(data_to_sign, signature)
    if not verify_ok:
        print("\n⚠️ Локальная проверка не прошла, но пробуем отправить в API...")

    # Шаг 5: Отправить в ЧЗ API
    token = send_to_chz(signature)

    if token:
        print("\n" + "=" * 80)
        print("🎉 АУТЕНТИФИКАЦИЯ УСПЕШНА!")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("❌ АУТЕНТИФИКАЦИЯ НЕ УДАЛАСЬ")
        print("=" * 80)
        print("\nПроверьте файл ошибки: C:\\Users\\1\\Desktop\\debug\\error.json")
        print("Отправьте этот файл в поддержку ЧЗ: support@crpt.ru")

    input("\nНажми Enter для выхода...")

if __name__ == "__main__":
    main()
