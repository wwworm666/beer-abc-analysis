# -*- coding: utf-8 -*-
"""
Вариант 3: PowerShell + .NET GOST через CSP CAdES COM

Этот скрипт генерирует PowerShell-скрипт который:
1. Получает данные от ChZ API
2. Использует CryptoPro .NET / CSP через COM для создания CAdES-BES подписи
3. Отправляет обратно в API

Также пробуем certutil.exe для CMS подписи.

Запускать из cmd ОТ ИМЕНИ АДМИНИСТРАТОРА
"""

import urllib.request, urllib.error, json, ssl, subprocess, os, tempfile

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
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


def clean_base64(text):
    return ''.join(c for c in text
                   if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')


def send_to_api(signature, uuid):
    """Попробовать все форматы отправки"""
    formats = [
        ("v3: data + unitedToken", {"data": signature, "unitedToken": True}),
        ("v2: uuid + data", {"uuid": uuid, "data": signature}),
    ]

    for label, payload in formats:
        print(f"\n  Попытка: {label}")
        status, response = make_request(
            f"{CHZ_BASE_URL}/auth/simpleSignIn", method="POST", data=payload)
        print(f"  Статус: {status}")

        if status == 200:
            print(f"  🎉 УСПЕХ! Токен получен")
            with open(os.path.join(DEBUG_DIR, "token.json"), 'w') as f:
                json.dump({"token": response}, f, indent=2)
            return response
        else:
            print(f"  ❌ {response.get('error_message', str(response))}")

        with open(os.path.join(DEBUG_DIR, f"error_ps_{label[:30].replace(' ', '_')}.json"), 'w') as f:
            json.dump({"status": status, "payload": payload, "response": response},
                      f, indent=2, ensure_ascii=False)

    return None


def run_ps_sign_variant(label, ps_script_lines):
    """Запустить PowerShell скрипт и получить подпись"""
    print(f"\n{'─' * 70}")
    print(f"  {label}")
    print(f"{'─' * 70}")

    ps_content = '\n'.join(ps_script_lines)

    # Сохранить PS-скрипт
    ps_file = os.path.join(DEBUG_DIR, "sign_temp.ps1")
    with open(ps_file, 'w', encoding='utf-8') as f:
        f.write(ps_content)

    # Для диагностики: вывести PS скрипт
    print(f"  PS-скрипт сохранён в: {ps_file}")

    result = subprocess.run(
        f'powershell -ExecutionPolicy Bypass -File "{ps_file}"',
        shell=True,
        capture_output=True,
        timeout=120,
        encoding='utf-8'
    )

    print(f"  Return code: {result.returncode}")
    if result.stdout:
        print(f"  stdout: {result.stdout[:800]}")
    if result.stderr:
        print(f"  stderr: {result.stderr[:800]}")

    # Попробовать прочитать подпись из выходного файла
    sig_file = os.path.join(DEBUG_DIR, "ps_signature.txt")
    if os.path.exists(sig_file):
        with open(sig_file, 'r', encoding='utf-8') as f:
            sig = clean_base64(f.read())
        if len(sig) > 100:
            print(f"  ✅ Подпись из файла: {len(sig)} chars")
            return sig

    return None


def main():
    print("=" * 70)
    print("  ЧЗ API — PowerShell / certutil / альтернативные методы")
    print("=" * 70)

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

    data_file = os.path.join(DEBUG_DIR, "data_to_sign_ps.txt")
    with open(data_file, 'wb') as f:
        f.write(data_to_sign.encode('utf-8'))

    # ==============================================
    # ВАРИАНТ PS1: certutil с PKCS#7
    # ==============================================
    # certutil.exe может создавать подписи через CNG
    # Но certutil не поддерживает GOST — пропускаем если CSP не установлен

    # Проверяем certutil и его возможности
    print(f"\n[DIAG] Проверка certutil.exe...")
    r = subprocess.run('certutil.exe -v -?', shell=True, capture_output=True,
                       timeout=10, encoding='utf-8', errors='replace')
    has_gost = 'GOST' in r.stdout or 'Gost' in r.stdout
    print(f"  certutil GOST support: {'YES' if has_gost else 'NO'}")

    # ==============================================
    # ВАРИАНТ PS1: certreq.exe через CryptoPro CNG
    # ==============================================
    # certreq может использовать GOST CNG provider

    # ==============================================
    # ВАРИАНТ PS2: Python через ctypes cpcsp.dll
    # ==============================================
    # Попробуем напрямую вызвать CryptoPro CSP через ctypes

    print(f"\n[DIAG] Попытка через ctypes cpcsp.dll...")
    cpcsp_path = r"C:\Program Files\Crypto Pro\CSP\cpcsp.dll"
    if os.path.exists(cpcsp_path):
        print(f"  cpcsp.dll найден: {cpcsp_path}")
        print(f"  Размер: {os.path.getsize(cpcsp_path)} bytes")
        # Это C API — нужны обёртки для Crypto API (CryptSignMessage и т.д.)
        # Для простой подписи можно попробовать CryptQueryObject / CryptSignMessage
        # через ctypes — но эти функции из crypt32.dll, а cpcsp.dll — это провайдер
        print(f"  Для GOST подписи через ctypes нужен КриптоПро .NET SDK")
        print(f"  Пропускаем — нет SDK")
    else:
        print(f"  cpcsp.dll не найден")

    # ==============================================
    # ВАРИАНТ 1: certutil -sign (если GOST доступен)
    # ==============================================
    # certutil НЕ поддерживает GOST без CryptoPro CNG CSP
    # Но проверим есть ли CryptoPro CNG CSP

    print(f"\n[DIAG] Проверка CryptoPro CNG CSP через certutil...")
    r = subprocess.run('certutil.exe -csptype', shell=True, capture_output=True,
                       timeout=10, encoding='cp866', errors='replace')
    if r.stdout:
        print(f"  Output: {r.stdout[:300]}")

    # ==============================================
    # ВАРИАНТ 2: PowerShell с CryptoPro CSP через Add-Type
    # ==============================================
    # Попробуем использовать System.Security.Cryptography.Pkcs
    # через CryptoPro GOST алгоритмы

    ps_sign_script = f'''
# PowerShell CAdES-BES через CryptoPro CSP (COM/CNG)
$ErrorActionPreference = "Stop"

$certThumb = "{CERT_THUMBPRINT}"
$dataToSign = "{data_to_sign}"
$dataBytes = [System.Text.Encoding]::UTF8.GetBytes($dataToSign)
$outFile = "{DEBUG_DIR}\\ps_signature.txt"

Write-Host "Сертификат: $certThumb"
Write-Host "Данные: $dataToSign ($($dataBytes.Length) bytes)"

# Попытка 1: Найти сертификат в хранилище
try {{
    $cert = Get-ChildItem -Path Cert:\\CurrentUser\\My | Where-Object {{ $_.Thumbprint -eq $certThumb }}
    if ($cert) {{
        Write-Host "Найден сертификат: $($cert.Subject)"
        Write-Host "Алгоритм: $($cert.SignatureAlgorithm.FriendlyName)"

        # Попытка подписать через System.Security.Cryptography.Pkcs
        $content = New-Object System.Security.Cryptography.Pkcs.ContentInfo @(,$dataBytes)
        $signer = New-Object System.Security.Cryptography.Pkcs.CmsSigner($cert)
        $signedCms = New-Object System.Security.Cryptography.Pkcs.SignedCms($content, $false)  # detached
        $signedCms.ComputeSignature($signer)
        $pkcsBytes = $signedCms.Encode()
        $base64 = [Convert]::ToBase64String($pkcsBytes)
        $base64 | Set-Content -Path $outFile -NoNewline
        Write-Host "УСПЕХ: подпись создана ($($base64.Length) chars)"
        exit 0
    }} else {{
        Write-Host "Сертификат не найден в CurrentUser\\My"
    }}
}} catch {{
    Write-Host "Ошибка 1: $_"
}}

# Попытка 2: Поиск в LocalMachine
try {{
    $cert = Get-ChildItem -Path Cert:\\LocalMachine\\My | Where-Object {{ $_.Thumbprint -eq $certThumb }}
    if ($cert) {{
        Write-Host "Найден в LocalMachine: $($cert.Subject)"

        $content = New-Object System.Security.Cryptography.Pkcs.ContentInfo @(,$dataBytes)
        $signer = New-Object System.Security.Cryptography.Pkcs.CmsSigner($cert)
        $signedCms = New-Object System.Security.Cryptography.Pkcs.SignedCms($content, $false)
        $signedCms.ComputeSignature($signer)
        $pkcsBytes = $signedCms.Encode()
        $base64 = [Convert]::ToBase64String($pkcsBytes)
        $base64 | Set-Content -Path $outFile -NoNewline
        Write-Host "УСПЕХ: подпись создана ($($base64.Length) chars)"
        exit 0
    }}
}} catch {{
    Write-Host "Ошибка 2: $_"
}}

Write-Host "Все попытки не удались"
exit 1
'''

    # Сначала перечислим сертификаты
    print(f"\n{'─' * 70}")
    print(f"  [DIAG] Поиск сертификата через PowerShell...")
    print(f"{'─' * 70}")

    diag_ps = f'''
$certs = Get-ChildItem -Path Cert:\\CurrentUser\\My, Cert:\\LocalMachine\\My -ErrorAction SilentlyContinue
foreach ($c in $certs) {{
    Write-Host "Thumb: $($c.Thumbprint) | Subject: $($c.Subject) | Algo: $($c.SignatureAlgorithm.FriendlyName)"
}}
if ($certs.Count -eq 0) {{
    Write-Host "Сертификаты в хранилище не найдены"
}}
'''

    diag_file = os.path.join(DEBUG_DIR, "diag_certs.ps1")
    with open(diag_file, 'w') as f:
        f.write(diag_ps)

    diag_result = subprocess.run(
        f'powershell -ExecutionPolicy Bypass -File "{diag_file}"',
        shell=True, capture_output=True, timeout=30, encoding='utf-8'
    )

    if diag_result.stdout:
        print(f"  {diag_result.stdout.strip()}")

    # Попытка PowerShell подписи
    if CERT_THUMBPRINT.upper() in (diag_result.stdout or ''):
        ps_file = os.path.join(DEBUG_DIR, "ps_sign.ps1")
        with open(ps_file, 'w') as f:
            f.write(ps_sign_script)

        print(f"\n{'─' * 70}")
        print(f"  PowerShell CMS подпись (.NET SignedCms)")
        print(f"{'─' * 70}")

        ps_result = subprocess.run(
            f'powershell -ExecutionPolicy Bypass -File "{ps_file}"',
            shell=True, capture_output=True, timeout=60, encoding='utf-8'
        )

        print(f"  Return code: {ps_result.returncode}")
        if ps_result.stdout:
            print(f"  stdout: {ps_result.stdout[:500]}")
        if ps_result.stderr:
            print(f"  stderr: {ps_result.stderr[:500]}")

        sig_file = os.path.join(DEBUG_DIR, "ps_signature.txt")
        if os.path.exists(sig_file):
            with open(sig_file, 'r') as f:
                sig = clean_base64(f.read())
            if len(sig) > 100:
                print(f"\n  ✅ Подпись: {len(sig)} chars")
                print(f"  Первые 60: {sig[:60]}")

                result_api = send_to_api(sig, uuid)
                if result_api:
                    print(f"\n  ✅ УСПЕХ через PowerShell SignedCms!")
                    input("\nНажми Enter для выхода...")
                    return

    else:
        print(f"  ⚠️ Сертификат не найден в Windows Certificate Store")
        print(f"  Он на Рутокене (SCARD), PowerShell не видит его как Cert:")

    # ==============================================
    # ВАРИАНТ 3: certutil -pfx для импорта из Рутокена
    # ==============================================
    print(f"\n{'─' * 70}")
    print(f"  certutil.exe -sign с GOST (если поддерживается)")
    print(f"{'─' * 70}")

    # certutil -sign использует CryptoAPI — если CryptoPro CSP
    # зарегистрирован как провайдер, он может работать
    sign_data_file = os.path.join(DEBUG_DIR, "data_to_sign_ct.txt")
    with open(sign_data_file, 'wb') as f:
        f.write(data_to_sign.encode('utf-8'))

    sig_out = os.path.join(DEBUG_DIR, "certutil_sig.p7s")

    # Попробуем certutil -sign (это требует сертификата в хранилище)
    ct_cmd = f'certutil.exe -sign -sid "{CERT_THUMBPRINT}" "{sign_data_file}" "{sig_out}"'
    print(f"  Команда: {ct_cmd}")

    ct_result = subprocess.run(ct_cmd, shell=True, capture_output=True,
                               timeout=60, encoding='cp866', errors='replace')
    print(f"  Return code: {ct_result.returncode}")
    if ct_result.stdout:
        print(f"  stdout: {ct_result.stdout[:300]}")
    if ct_result.stderr:
        print(f"  stderr: {ct_result.stderr[:300]}")

    if ct_result.returncode == 0 and os.path.exists(sig_out):
        # Конвертировать из бинарного в base64
        import base64
        with open(sig_out, 'rb') as f:
            raw = f.read()
        sig_b64 = base64.b64encode(raw).decode('ascii')
        print(f"  ✅ certutil создал подпись: {len(sig_b64)} chars")

        result_api = send_to_api(sig_b64, uuid)
        if result_api:
            print(f"\n  ✅ УСПЕХ через certutil!")
            input("\nНажми Enter для выхода...")
            return
    else:
        print(f"  ❌ certutil не смог подписать")

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
