# -*- coding: utf-8 -*-
"""
АУТЕНТИФИКАЦИЯ В ЧЕСТНЫЙ ЗНАК API
Запускать из cmd ОТ ИМЕНИ АДМИНИСТРАТОРА

Команда подписи: csptest.exe -sfsign -sign (подтверждено тестом)
"""

import urllib.request
import urllib.error
import json
import ssl
import subprocess
import os

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
    print("АУТЕНТИФИКАЦИЯ В ЧЕСТНЫЙ ЗНАК API")
    print("=" * 80)

    os.makedirs(DEBUG_DIR, exist_ok=True)

    # ===== ШАГ 1: Получить данные =====
    print("\n[ШАГ 1] Получение UUID и DATA от ЧЗ API...")
    status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")

    if status != 200:
        print(f"❌ ОШИБКА: {auth_data}")
        input("Enter для выхода...")
        return

    uuid = auth_data.get('uuid')
    data_to_sign = auth_data.get('data')

    print(f"✅ UUID: {uuid}")
    print(f"✅ DATA: '{data_to_sign}' ({len(data_to_sign)} символов)")

    # Сохраняем данные (UTF-8 без BOM, без newline)
    data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")
    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    with open(os.path.join(DEBUG_DIR, "uuid.txt"), 'w') as f:
        f.write(uuid)

    print(f"✅ Данные сохранены в {DEBUG_DIR}")

    # ===== ШАГ 2: Подписать =====
    print("\n[ШАГ 2] Подпись данных (csptest -sfsign -sign)...")

    sig_file = os.path.join(DEBUG_DIR, "sig_attached.txt")

    # ПРАВИЛЬНАЯ КОМАНДА (подтверждена тестом test_sign_tool.py)
    cmd = f'"{CSP_PATH}" -sfsign -sign -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}" -base64'

    print(f"Команда: {cmd}")
    print("Выполнение...")

    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        timeout=60,
        encoding='cp866'
    )

    if result.returncode != 0:
        print(f"\n❌ ОШИБКА подписи: {result.returncode}")
        if result.stderr:
            print(f"Ошибка: {result.stderr.strip()}")
        if result.stdout:
            print(f"Вывод: {result.stdout.strip()}")

        print("\n" + "=" * 80)
        print("ВОЗМОЖНЫЕ ПРИЧИНЫ:")
        print("1. Рутокен не подключён")
        print("2. Нет прав администратора (запусти cmd от имени администратора)")
        print("3. CryptoPro CSP не установлен")
        print("=" * 80)
        input("Enter для выхода...")
        return

    # Читаем подпись
    with open(sig_file, 'r', encoding='utf-8') as f:
        signature = f.read().strip()

    # Очистка до одной строки base64
    signature = ''.join(c for c in signature if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

    print(f"✅ Подпись создана: {len(signature)} символов")

    # Сохраняем очищенную подпись
    clean_sig_file = os.path.join(DEBUG_DIR, "sig_attached_clean.txt")
    with open(clean_sig_file, 'w', encoding='utf-8') as f:
        f.write(signature)

    # ===== ШАГ 3: Отправить в API =====
    print("\n[ШАГ 3] Отправка запроса на аутентификацию...")

    payload = {
        "data": signature,
        "unitedToken": True
    }

    # Сохраняем запрос
    with open(os.path.join(DEBUG_DIR, "request.json"), 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    status, response = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        method="POST",
        data=payload
    )

    print(f"Статус: {status}")

    if status == 200:
        print(f"\n🎉 УСПЕХ! Токен получен:")
        print(f"   {response}")

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
        print(f"✅ Детали ошибки: {DEBUG_DIR}\\error.json")

    print("\n" + "=" * 80)
    input("Enter для выхода...")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 80)
        input("Enter для выхода...")
