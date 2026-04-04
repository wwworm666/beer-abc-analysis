"""
ПОЛНЫЙ ТЕСТ ВСЕХ ВОЗМОЖНЫХ ВАРИАНТОВ ПОДПИСИ ДЛЯ ЧЗ API
Запусти этот скрипт на ПК с Рутокеном и скинь весь вывод
"""

import urllib.request
import urllib.error
import json
import ssl
import subprocess
import tempfile
import os
import base64
import hashlib

# ==================== КОНФИГУРАЦИЯ ====================
CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
# =======================================================

def make_request(url, method="GET", data=None, headers=None):
    """HTTP запрос"""
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

def run_csp(cmd_args, data_file=None):
    """Запуск csptest.exe"""
    cmd = f'"{CSP_PATH}" ' + ' '.join(cmd_args)
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, timeout=60, encoding='cp866')
        return result.returncode, result.stdout, result.stderr
    except Exception as ex:
        return -1, "", str(ex)

def clean_base64(s):
    """Очистка base64 до одной строки"""
    return ''.join(c for c in s if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

def save_debug(name, content):
    """Сохранение в debug файл"""
    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, name)
    mode = 'wb' if isinstance(content, bytes) else 'w'
    with open(path, mode, encoding='utf-8' if mode == 'w' else None) as f:
        f.write(content)
    return path

print("╔" + "="*78 + "╗")
print("║  ПОЛНЫЙ ТЕСТ ПОДПИСИ ДЛЯ ЧЕСТНЫЙ ЗНАК API                        ║")
print("╚" + "="*78 + "╝")

# ==================== ШАГ 1: Получение data ====================
print("\n" + "="*80)
print("ШАГ 1: ПОЛУЧЕНИЕ UUID И DATA ДЛЯ ПОДПИСИ")
print("="*80)

status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
print(f"URL: {CHZ_BASE_URL}/auth/key")
print(f"Статус: {status}")

if status != 200:
    print(f"❌ ОШИБКА: {auth_data}")
    input("\nНажми Enter для выхода...")
    exit(1)

uuid = auth_data.get('uuid')
data_to_sign = auth_data.get('data')

print(f"✅ UUID: {uuid}")
print(f"✅ DATA: '{data_to_sign}' (длина: {len(data_to_sign)} символов)")

save_debug("01_uuid.txt", uuid)
save_debug("02_data_to_sign.txt", data_to_sign)

# ==================== ШАГ 2: Тест различных методов подписи ====================
print("\n" + "="*80)
print("ШАГ 2: ТЕСТ РАЗЛИЧНЫХ МЕТОДОВ ПОДПИСИ")
print("="*80)

temp_dir = tempfile.gettempdir()
data_file = os.path.join(temp_dir, "chz_test_data.txt")
sig_file = os.path.join(temp_dir, "chz_test_sig.txt")
out_file = os.path.join(temp_dir, "chz_test_out.txt")

# Сохраняем данные для подписи (raw bytes, без BOM и newline)
with open(data_file, 'wb') as f:
    f.write(data_to_sign.encode('utf-8'))
print(f"\nДанные сохранены в: {data_file}")
print(f"Размер файла: {os.path.getsize(data_file)} байт")

# ТЕСТ 1: -sfsign -sign (присоединённая)
print("\n" + "-"*80)
print("ТЕСТ 1: -sfsign -sign (присоединённая подпись)")
print("-"*80)
cmd = f'-sfsign -sign -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}" -base64'
rc, out, err = run_csp(cmd.split())
sig1 = None
if rc == 0:
    with open(sig_file, 'r', encoding='utf-8') as f:
        sig1 = clean_base64(f.read())
    print(f"✅ УСПЕХ: {len(sig1)} символов")
    save_debug("03_sig1_attached.txt", sig1)
else:
    print(f"❌ ОШИБКА {rc}: {err[:200] if err else out[:200]}")

# ТЕСТ 2: -sfsign -sign -detached (откреплённая)
print("\n" + "-"*80)
print("ТЕСТ 2: -sfsign -sign -detached (откреплённая подпись)")
print("-"*80)
cmd = f'-sfsign -sign -detached -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}" -base64'
rc, out, err = run_csp(cmd.split())
sig2 = None
if rc == 0:
    with open(sig_file, 'r', encoding='utf-8') as f:
        sig2 = clean_base64(f.read())
    print(f"✅ УСПЕХ: {len(sig2)} символов")
    save_debug("04_sig2_detached.txt", sig2)
else:
    print(f"❌ ОШИБКА {rc}: {err[:200] if err else out[:200]}")

# ТЕСТ 3: -sfsign -sign -cades -detached (CAdES-BES)
print("\n" + "-"*80)
print("ТЕСТ 3: -sfsign -sign -cades -detached (CAdES-BES)")
print("-"*80)
cmd = f'-sfsign -sign -cades -detached -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}" -base64'
rc, out, err = run_csp(cmd.split())
sig3 = None
if rc == 0:
    with open(sig_file, 'r', encoding='utf-8') as f:
        sig3 = clean_base64(f.read())
    print(f"✅ УСПЕХ: {len(sig3)} символов")
    save_debug("05_sig3_cades.txt", sig3)
else:
    print(f"❌ ОШИБКА {rc}: {err[:200] if err else out[:200]}")

# ТЕСТ 4: -sfsign -sign -cades (присоединённая CAdES)
print("\n" + "-"*80)
print("ТЕСТ 4: -sfsign -sign -cades (присоединённая CAdES)")
print("-"*80)
cmd = f'-sfsign -sign -cades -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}" -base64'
rc, out, err = run_csp(cmd.split())
sig4 = None
if rc == 0:
    with open(sig_file, 'r', encoding='utf-8') as f:
        sig4 = clean_base64(f.read())
    print(f"✅ УСПЕХ: {len(sig4)} символов")
    save_debug("06_sig4_cades_attached.txt", sig4)
else:
    print(f"❌ ОШИБКА {rc}: {err[:200] if err else out[:200]}")

# ТЕСТ 5: -sign (простая подпись без -sfsign)
print("\n" + "-"*80)
print("ТЕСТ 5: -sign (простая подпись)")
print("-"*80)
cmd = f'-sign -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}" -base64'
rc, out, err = run_csp(cmd.split())
sig5 = None
if rc == 0:
    with open(sig_file, 'r', encoding='utf-8') as f:
        sig5 = clean_base64(f.read())
    print(f"✅ УСПЕХ: {len(sig5)} символов")
    save_debug("07_sig5_simple.txt", sig5)
else:
    print(f"❌ ОШИБКА {rc}: {err[:200] if err else out[:200]}")

# ТЕСТ 6: Хэш + подпись хэша
print("\n" + "-"*80)
print("ТЕСТ 6: -hash + -sfsign -sign -hash (подпись хэша)")
print("-"*80)
hash_file = os.path.join(temp_dir, "chz_test_hash.txt")
cmd = f'-hash -in "{data_file}" -out "{hash_file}"'
rc, out, err = run_csp(cmd.split())
hash_value = None
if rc == 0:
    with open(hash_file, 'r', encoding='utf-8') as f:
        hash_content = f.read()
    # Извлекаем сам хэш из вывода
    hash_value = hash_content.strip()
    print(f"✅ Хэш создан: {hash_value[:50]}...")
    save_debug("08_hash.txt", hash_value)

    # Теперь подписываем хэш
    cmd = f'-sfsign -sign -my "{CERT_THUMBPRINT}" -hash "{hash_file}" -out "{sig_file}" -base64'
    rc, out, err = run_csp(cmd.split())
    sig6 = None
    if rc == 0:
        with open(sig_file, 'r', encoding='utf-8') as f:
            sig6 = clean_base64(f.read())
        print(f"✅ Подпись хэша: {len(sig6)} символов")
        save_debug("09_sig6_hash_signed.txt", sig6)
    else:
        print(f"❌ ОШИБКА подписи: {err[:200] if err else out[:200]}")
else:
    print(f"❌ ОШИБКА хэша: {rc}")

# ==================== ШАГ 3: Тест всех комбинаций запросов ====================
print("\n" + "="*80)
print("ШАГ 3: ТЕСТ ВСЕХ КОМБИНАЦИЙ ЗАПРОСОВ К API")
print("="*80)

signatures = {
    "attached": sig1,
    "detached": sig2,
    "cades_detached": sig3,
    "cades_attached": sig4,
    "simple": sig5,
}

# Фильтруем None
signatures = {k: v for k, v in signatures.items() if v}

print(f"\nДоступно подписей для теста: {list(signatures.keys())}")

# Форматы запросов
request_formats = [
    ("v2: uuid + data", lambda sig: {"uuid": uuid, "data": sig}),
    ("v2: uuid + data + inn", lambda sig: {"uuid": uuid, "data": sig, "inn": "7801630649"}),
    ("v3: data + unitedToken", lambda sig: {"data": sig, "unitedToken": True}),
    ("v3: uuid + data + unitedToken", lambda sig: {"uuid": uuid, "data": sig, "unitedToken": True}),
]

results = []

for sig_name, signature in signatures.items():
    print(f"\n{'='*60}")
    print(f"Подпись: {sig_name} ({len(signature)} символов)")
    print(f"{'='*60}")

    for fmt_name, fmt_func in request_formats:
        payload = fmt_func(signature)
        print(f"\n  → {fmt_name}...")

        status, response = make_request(
            f"{CHZ_BASE_URL}/auth/simpleSignIn",
            method="POST",
            data=payload
        )

        result_str = f"Статус: {status}"
        if status == 200:
            result_str = f"✅ УСПЕХ! Токен: {response}"
            results.append((sig_name, fmt_name, True, response))
        else:
            error_msg = response.get('error_message', str(response))[:80]
            result_str = f"❌ {error_msg}"
            results.append((sig_name, fmt_name, False, error_msg))

        print(f"    {result_str}")

# ==================== ШАГ 4: Итоги ====================
print("\n" + "="*80)
print("ИТОГИ: ВСЕ РЕЗУЛЬТАТЫ ТЕСТА")
print("="*80)

success_results = [r for r in results if r[2]]
fail_results = [r for r in results if not r[2]]

if success_results:
    print("\n🎉 УСПЕШНЫЕ КОМБИНАЦИИ:")
    for sig_name, fmt_name, _, token in success_results:
        print(f"  ✅ {sig_name} + {fmt_name}")
        print(f"     Токен: {token}")
else:
    print("\n❌ НИ ОДНА КОМБИНАЦИЯ НЕ СРАБОТАЛА")
    print("\nВсе ошибки:")
    for sig_name, fmt_name, _, error in fail_results:
        print(f"  • {sig_name} + {fmt_name}: {error}")

# Сохраняем итоги
save_debug("10_results.txt", json.dumps({
    "uuid": uuid,
    "data_to_sign": data_to_sign,
    "signatures": {k: len(v) for k, v in signatures.items()},
    "results": results
}, indent=2, ensure_ascii=False))

print(f"\n📁 Результаты сохранены в C:\\chz_test\\debug\\10_results.txt")
print("\n" + "="*80)
input("Нажми Enter для выхода...")
