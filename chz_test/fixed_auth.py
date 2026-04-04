# -*- coding: utf-8 -*-
"""
ИСПРАВЛЕННАЯ АУТЕНТИФИКАЦИЯ В ЧЕСТНЫЙ ЗНАК API
Критические исправления по результатам анализа документации:

1. Команда подписи: -sign (без -sfsign)
   -sfsign создаёт detached signature (откреплённая подпись)
   -sign создаёт attached signature (присоединённая подпись) - ТРЕБУЕТСЯ для /auth/simpleSignIn

2. Режим сохранения данных: текстовый UTF-8 без BOM
   Было: wb + encode('utf-8') → бинарный режим с BOM
   Стало: 'w' + encoding='utf-8' + newline='' → чистый текст

3. Путь DEBUG_DIR обновлён на правильный: C:\chz_test\debug

Документация: memory/chz-discrepancies.md строки 13-22, 42-62
"""

import urllib.request
import urllib.error
import json
import ssl
import subprocess
import os
import sys

# Enable UTF-8 output on Windows
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
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

def main():
    print("=" * 80)
    print("ИСПРАВЛЕННАЯ АУТЕНТИФИКАЦИЯ В ЧЕСТНЫЙ ЗНАК API")
    print("=" * 80)
    print()
    print("Критические исправления:")
    print("  1. Команда: -sign (без -sfsign) → attached signature")
    print("  2. Режим файла: текстовый UTF-8 (не binary)")
    print("  3. Путь: C:\\chz_test\\debug")
    print()

    os.makedirs(DEBUG_DIR, exist_ok=True)

    # ===== ШАГ 1: Получить данные =====
    print("[1/4] Получение UUID и DATA от ЧЗ API...")
    status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")

    if status != 200:
        print(f"    ❌ ОШИБКА API: {auth_data}")
        input("Enter для выхода...")
        return None

    uuid = auth_data.get('uuid')
    data_to_sign = auth_data.get('data')

    print(f"    ✅ UUID: {uuid}")
    print(f"    ✅ DATA: '{data_to_sign}' ({len(data_to_sign)} символов)")

    # ===== ШАГ 2: Сохранить данные (ТЕКСТОВЫЙ РЕЖИМ!) =====
    print()
    print("[2/4] Сохранение данных для подписи...")

    data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")

    # ✅ ИСПРАВЛЕНО: текстовый режим, не бинарный!
    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)  # Просто строка, без BOM, без newline

    with open(os.path.join(DEBUG_DIR, "uuid.txt"), 'w', encoding='utf-8') as f:
        f.write(uuid)

    print(f"    ✅ Сохранено в {data_file}")

    # Проверка размера файла
    file_size = os.path.getsize(data_file)
    print(f"    ✅ Размер файла: {file_size} байт")

    # ===== ШАГ 3: Подписать (ПРАВИЛЬНАЯ КОМАНДА!) =====
    print()
    print("[3/4] Подпись данных...")

    sig_file = os.path.join(DEBUG_DIR, "sig_attached.txt")

    # ✅ ИСПРАВЛЕНО: -sign без -sfsign!
    cmd = f'"{CSP_PATH}" -sign -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}" -base64'

    print(f"    Команда: {cmd}")
    print("    Выполнение...")

    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        timeout=60,
        encoding='cp866'
    )

    if result.returncode != 0:
        print(f"\n    ❌ ОШИБКА подписи: {result.returncode}")
        if result.stderr:
            print(f"    stderr: {result.stderr[:300]}")
        if result.stdout:
            print(f"    stdout: {result.stdout[:300]}")

        print()
        print("    Возможные причины:")
        print("    1. Рутокен не подключён")
        print("    2. Нет прав администратора")
        print("    3. CryptoPro CSP не установлен")
        print()

        error_file = os.path.join(DEBUG_DIR, "sign_error.json")
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump({
                "returncode": result.returncode,
                "stderr": result.stderr,
                "stdout": result.stdout,
                "command": cmd
            }, f, indent=2, ensure_ascii=False)
        print(f"    Детали сохранены в {error_file}")

        input("    Enter для выхода...")
        return None

    # Читаем подпись
    with open(sig_file, 'r', encoding='utf-8') as f:
        signature_raw = f.read()

    # Очистка до одной строки base64
    signature = ''.join(c for c in signature_raw if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

    print(f"    ✅ Подпись создана: {len(signature)} символов")
    print(f"    Начало: {signature[:60]}...")

    # Сохраняем подпись
    clean_sig_file = os.path.join(DEBUG_DIR, "sig_attached_clean.txt")
    with open(clean_sig_file, 'w', encoding='utf-8') as f:
        f.write(signature)

    # ===== ШАГ 4: Отправить в API =====
    print()
    print("[4/4] Отправка запроса на аутентификацию...")

    payload = {
        "data": signature,
        "unitedToken": True
    }

    with open(os.path.join(DEBUG_DIR, "request.json"), 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    status, response = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        method="POST",
        data=payload
    )

    print(f"    Статус: {status}")

    if status == 200:
        print()
        print("=" * 80)
        print("🎉 УСПЕХ! ТОКЕН ПОЛУЧЕН!")
        print("=" * 80)
        print(f"Токен: {response}")
        print()

        token_file = os.path.join(DEBUG_DIR, "token.json")
        with open(token_file, 'w', encoding='utf-8') as f:
            json.dump({
                "token": response,
                "uuid": uuid,
                "data_signed": data_to_sign,
                "signature_len": len(signature)
            }, f, indent=2, ensure_ascii=False)
        print(f"✅ Токен сохранён в: {token_file}")

        return response
    else:
        print()
        print("=" * 80)
        print("❌ ОШИБКА АУТЕНТИФИКАЦИИ")
        print("=" * 80)

        error_msg = response.get('error_message', str(response))
        print(f"Ошибка: {error_msg}")
        print()

        error_file = os.path.join(DEBUG_DIR, "error_fixed.json")
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "uuid": uuid,
                "data_to_sign": data_to_sign,
                "signature_len": len(signature),
                "payload": payload,
                "response": response,
                "command_used": cmd
            }, f, indent=2, ensure_ascii=False)
        print(f"✅ Детали ошибки сохранены в: {error_file}")
        print()
        print("Следующий шаг: отправить error_fixed.json на support@crpt.ru")

        return None

if __name__ == "__main__":
    try:
        result = main()
        if result:
            print()
            print("=" * 80)
            print("СКРИПТ ЗАВЕРШЁН УСПЕШНО!")
            print("=" * 80)
        else:
            print()
            print("=" * 80)
            print("СКРИПТ ЗАВЕРШЁН С ОШИБКОЙ")
            print("=" * 80)
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        input("Enter для выхода...")