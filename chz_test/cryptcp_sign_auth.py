# -*- coding: utf-8 -*-
"""
Вариант 2: CryptCP для CMS/CAdES подписи

CryptCP — это отдельный инструмент CryptoPro для создания CMS подписей.
Он поддерживает CAdES-BES из коробки (в отличие от csptest -sfsign).
Находим CryptCP.exe в системе и пробуем несколько команд.

Запускать из cmd ОТ ИМЕНИ АДМИНИСТРАТОРА
"""

import urllib.request, urllib.error, json, ssl, subprocess, os, glob

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")

os.makedirs(DEBUG_DIR, exist_ok=True)


def find_cryptcp():
    """Найти CryptCP.exe в системе"""
    print("Поиск CryptCP.exe...")

    # Ищем в обычных местах
    candidates = (
        glob.glob(r"C:\Program Files\Crypto Pro\CSP\cryptcp*.exe")
        + glob.glob(r"C:\Program Files\Crypto Pro\CryptCP\cryptcp*.exe")
        + glob.glob(r"C:\Program Files (x86)\Crypto Pro\CSP\cryptcp*.exe")
        + glob.glob(r"C:\Program Files (x86)\Crypto Pro\CryptCP\cryptcp*.exe")
        + glob.glob(r"C:\Program Files\CryptoPro\CSP\cryptcp*.exe")
    )

    # Также проверяем файл в текущей директории (мы положили туда x64/win32)
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cryptcp.x64.exe")
    if os.path.exists(local):
        candidates.append(local)
        print(f"  ✅ Найден локальный: {local}")

    local32 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cryptcp.win32.exe")
    if os.path.exists(local32):
        candidates.append(local32)
        print(f"  ✅ Найден локальный 32-bit: {local32}")

    for c in candidates:
        if os.path.exists(c):
            print(f"  ✅ Найден: {c}")
            return c

    print("  ❌ CryptCP.exe не найден")
    return None


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


def clean_base64(text):
    return ''.join(c for c in text
                   if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')


def send_to_api(signature, uuid, variant_label):
    """Попробовать v3 и v2 форматы"""
    # v3
    print(f"  Отправка (v3: data + unitedToken)...")
    payload = {"data": signature, "unitedToken": True}
    status, response = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn", method="POST", data=payload)
    print(f"  Статус: {status}")
    if status == 200:
        print(f"  🎉 УСПЕХ! Токен получен")
        with open(os.path.join(DEBUG_DIR, "token.json"), 'w') as f:
            json.dump({"token": response}, f, indent=2)
        return response
    print(f"  ❌ {response.get('error_message', str(response))}")

    # Сохраняем ошибку для этого варианта
    with open(os.path.join(DEBUG_DIR, f"error_{variant_label}.json"), 'w') as f:
        json.dump({"status": status, "payload": payload, "response": response},
                  f, indent=2, ensure_ascii=False)

    # v2
    print(f"  Отправка (v2: uuid + data)...")
    payload_v2 = {"uuid": uuid, "data": signature}
    status_v2, response_v2 = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn", method="POST", data=payload_v2)
    print(f"  Статус: {status_v2}")
    if status_v2 == 200:
        print(f"  🎉 УСПЕХ (v2)!")
        with open(os.path.join(DEBUG_DIR, "token.json"), 'w') as f:
            json.dump({"token": response_v2}, f, indent=2)
        return response_v2
    print(f"  ❌ {response_v2.get('error_message', str(response_v2))}")

    return None


def sign_with_cryptcp(cryptcp_path, data_file, sig_file, cmd_template, label):
    """Подписать через CryptCP и вернуть подпись"""
    cmd = cmd_template.format(cryptcp=cryptcp_path, data_in=data_file, data_out=sig_file)
    print(f"  Команда: {cmd}")

    result = subprocess.run(cmd, shell=True, capture_output=True,
                            timeout=60, encoding='cp866')

    print(f"  Return code: {result.returncode}")
    if result.stdout:
        print(f"  stdout: {result.stdout[:500]}")
    if result.stderr:
        print(f"  stderr: {result.stderr[:500]}")

    if result.returncode != 0:
        print(f"  ❌ Подпись не создана")
        return None

    # Проверить разные возможные имена выходных файлов
    candidates = [sig_file, sig_file + ".sig", data_file + ".sig"]
    for candidate in candidates:
        if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
            with open(candidate, 'r', encoding='utf-8-sig') as f:
                raw = f.read()
            sig = clean_base64(raw)
            if len(sig) > 100:
                print(f"  ✅ Подпись: {len(sig)} chars (файл: {candidate})")
                return sig

    print(f"  ⚠️ Подпись возможно создана но не в текстовом формате")
    # Проверить бинарный .sig
    bin_sig = sig_file if os.path.exists(sig_file) else None
    if bin_sig and os.path.getsize(bin_sig) > 0:
        with open(bin_sig, 'rb') as f:
            raw_bytes = f.read()
        print(f"  Бинарный размер: {len(raw_bytes)} bytes")
        # Попробовать декодировать как base64
        try:
            import base64
            sig_str = raw_bytes.decode('ascii', errors='ignore')
            sig = clean_base64(sig_str)
            if len(sig) > 100:
                print(f"  ✅ Подпись (из binary): {len(sig)} chars")
                return sig
        except:
            pass

    return None


def main():
    print("=" * 70)
    print("  ЧЗ API — CryptCP подпись")
    print("=" * 70)

    cryptcp = find_cryptcp()
    if not cryptcp:
        print("\nCryptCP не найден. Попробуйте установить:")
        print("  https://www.cryptopro.ru/products/cryptcp")
        input("\nНажми Enter для выхода...")
        return

    # Шаг 1: Получить данные
    print("\n[1] Получение данных от API...")
    status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
    if status != 200:
        print(f"  ❌ Ошибка: {auth_data}")
        input("\nНажми Enter для выхода...")
        return

    uuid = auth_data.get('uuid')
    data_to_sign = auth_data.get('data')
    print(f"  UUID: {uuid}")
    print(f"  DATA: '{data_to_sign}' ({len(data_to_sign)} chars)")

    # Сохранить
    data_file = os.path.join(DEBUG_DIR, "data_to_sign_ccp.txt")
    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    # Варианты подписи через CryptCP
    variants = [
        (
            "CryptCP: CMS подпись по отпечатку (detached, base64)",
            '"{cryptcp}" -sign -thumb "{cert}" -detached -base64 -add "{data_in}" "{data_out}"',
            "ccp_detached_thumb"
        ),
        (
            "CryptCP: CMS подпись (не detached — присоединённая)",
            '"{cryptcp}" -sign -thumb "{cert}" -base64 -add "{data_in}" "{data_out}"',
            "ccp_attached"
        ),
        (
            "CryptCP: CAdES-BES подписанное сообщение",
            '"{cryptcp}" -sign -thumb "{cert}" -base64 -cert -add "{data_in}" "{data_out}"',
            "ccp_cades_cert"
        ),
    ]

    for label, cmd_template, variant_name in variants:
        print(f"\n{'─' * 70}")
        print(f"  {label}")
        print(f"{'─' * 70}")

        sig_file = os.path.join(DEBUG_DIR, f"sig_{variant_name}.txt")
        sig = sign_with_cryptcp(cryptcp, data_file, sig_file, cmd_template, variant_name)

        if sig:
            print(f"\n  Отправка в API...")
            result = send_to_api(sig, uuid, variant_name)
            if result:
                print(f"\n  ✅ УСПЕХ: {label}")
                input("\nНажми Enter для выхода...")
                return

        input(f"\n→ Нажми Enter для следующего варианта...")

    print(f"\n{'=' * 70}")
    print(f"  ❌ Все варианты не прошли")
    print(f"{'=' * 70}")
    input("\nНажми Enter для выхода...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ CRITICAL: {e}")
        import traceback
        traceback.print_exc()
