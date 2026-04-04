"""
Сбор диагностической информации для отправки в поддержку ЧЗ
Создаёт файл support_request.json со всеми данными
"""

import urllib.request
import urllib.error
import json
import ssl
import subprocess
import os
import base64
from datetime import datetime

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERTMGR_PATH = r"C:\Program Files\Crypto Pro\CSP\certmgr.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")

os.makedirs(DEBUG_DIR, exist_ok=True)

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

def run_command(cmd):
    """Выполнить команду и вернуть результат"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            timeout=30,
            encoding='cp866',
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return result.returncode, result.stdout[:1000], result.stderr[:1000]
    except Exception as ex:
        return None, "", str(ex)

print("=" * 80)
print("СБОР ДИАГНОСТИЧЕСКОЙ ИНФОРМАЦИИ ДЛЯ ПОДДЕРЖКИ ЧЗ")
print("=" * 80)

diagnostics = {
    "timestamp": datetime.now().isoformat(),
    "chz_base_url": CHZ_BASE_URL,
    "cert_thumbprint": CERT_THUMBPRINT,
}

# 1. Информация о сертификате
print("\n1. Получение информации о сертификате...")
ret, out, err = run_command(f'"{CERTMGR_PATH}" -list -all')
diagnostics["cert_info"] = out if out else err

# 2. Информация о контейнерах
print("2. Получение информации о контейнерах...")
ret, out, err = run_command(f'"{CSP_PATH}" -keys -enum')
diagnostics["container_info"] = out if out else err

# 3. Получение данных от ЧЗ
print("3. Получение UUID и DATA от ЧЗ API...")
status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
diagnostics["auth_key_response"] = {
    "status": status,
    "uuid": auth_data.get("uuid") if isinstance(auth_data, dict) else None,
    "data": auth_data.get("data") if isinstance(auth_data, dict) else None,
}

if status == 200:
    uuid = auth_data.get("uuid")
    data_to_sign = auth_data.get("data")

    # 4. Подпись данных
    print("4. Подпись данных...")
    data_file = os.path.join(DEBUG_DIR, "diag_data.txt")
    sig_file = os.path.join(DEBUG_DIR, "diag_sig.p7s")

    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    ret, out, err = run_command(
        f'"{CSP_PATH}" -sfsign -sign -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}"'
    )

    diagnostics["sign_response"] = {
        "returncode": ret,
        "stdout": out[:500],
        "stderr": err[:500],
    }

    if ret == 0 and os.path.exists(sig_file):
        with open(sig_file, 'rb') as f:
            sig_bytes = f.read()
        signature_base64 = base64.b64encode(sig_bytes).decode('ascii')
        diagnostics["signature_base64"] = signature_base64

        # 5. Попытка аутентификации
        print("5. Попытка аутентификации в ЧЗ...")
        payload = {"data": signature_base64, "unitedToken": True}
        status, response = make_request(
            f"{CHZ_BASE_URL}/auth/simpleSignIn",
            method="POST",
            data=payload
        )

        diagnostics["auth_attempt"] = {
            "request": payload,
            "status": status,
            "response": response,
        }

# Сохраняем диагностику
output_file = os.path.join(DEBUG_DIR, "support_request.json")
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(diagnostics, f, indent=2, ensure_ascii=False)

print(f"\n✅ Диагностика сохранена в: {output_file}")
print(f"\n📧 Отправьте этот файл на support@crpt.ru")
print("\n" + "=" * 80)
print("КРАТКАЯ СВОДКА:")
print("=" * 80)

if "auth_attempt" in diagnostics:
    attempt = diagnostics["auth_attempt"]
    print(f"Статус аутентификации: {attempt.get('status')}")
    print(f"Ошибка: {attempt.get('response', {}).get('error_message', 'N/A')}")
else:
    print("Аутентификация не выполнена (ошибка на этапе подписи)")

print(f"\nПолные данные в файле: {output_file}")
input("\nНажми Enter для выхода...")
