# -*- coding: utf-8 -*-
"""
Тест различных инструментов подписи CryptoPro
Ничего не отправляет в API - только локальная проверка
"""

import subprocess
import os

CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERTMGR_PATH = r"C:\Program Files\Crypto Pro\CSP\certmgr.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")

# Тестовые данные
TEST_DATA = "TEST1234567890ABCDEF"

os.makedirs(DEBUG_DIR, exist_ok=True)

# Сохраняем тестовые данные
test_file = os.path.join(DEBUG_DIR, "test_data.txt")
with open(test_file, 'w', encoding='utf-8', newline='') as f:
    f.write(TEST_DATA)

print("=" * 80)
print("ТЕСТ ИНСТРУМЕНТОВ ПОДПИСИ CRYPTOPRO")
print("=" * 80)
print(f"Данные для подписи: '{TEST_DATA}'")
print(f"Файл: {test_file}")
print()

# ============================================================
# ТЕСТ 1: csptest.exe -sign (присоединённая подпись)
# ============================================================
print("-" * 80)
print("ТЕСТ 1: csptest.exe -sign (присоединённая подпись)")
print("-" * 80)

sig1_file = os.path.join(DEBUG_DIR, "test_sig1.txt")
cmd1 = f'"{CSP_PATH}" -sign -my "{CERT_THUMBPRINT}" -in "{test_file}" -out "{sig1_file}" -base64'
print(f"Команда: {cmd1}")

result1 = subprocess.run(
    cmd1,
    shell=True,
    capture_output=True,
    timeout=60,
    encoding='cp866'
)

if result1.returncode == 0:
    print("✅ УСПЕХ!")
    if os.path.exists(sig1_file):
        with open(sig1_file, 'r') as f:
            sig1 = f.read().strip()
        print(f"Размер подписи: {len(sig1)} символов")
        print(f"Начало: {sig1[:60]}...")
else:
    print(f"❌ ОШИБКА: {result1.returncode}")
    if result1.stderr:
        print(f"stderr: {result1.stderr[:300]}")
    if result1.stdout:
        print(f"stdout: {result1.stdout[:300]}")

print()

# ============================================================
# ТЕСТ 2: csptest.exe -sfsign -sign (присоединённая через SFSIGN)
# ============================================================
print("-" * 80)
print("ТЕСТ 2: csptest.exe -sfsign -sign")
print("-" * 80)

sig2_file = os.path.join(DEBUG_DIR, "test_sig2.txt")
cmd2 = f'"{CSP_PATH}" -sfsign -sign -my "{CERT_THUMBPRINT}" -in "{test_file}" -out "{sig2_file}" -base64'
print(f"Команда: {cmd2}")

result2 = subprocess.run(
    cmd2,
    shell=True,
    capture_output=True,
    timeout=60,
    encoding='cp866'
)

if result2.returncode == 0:
    print("✅ УСПЕХ!")
    if os.path.exists(sig2_file):
        with open(sig2_file, 'r') as f:
            sig2 = f.read().strip()
        print(f"Размер подписи: {len(sig2)} символов")
        print(f"Начало: {sig2[:60]}...")
else:
    print(f"❌ ОШИБКА: {result2.returncode}")
    if result2.stderr:
        print(f"stderr: {result2.stderr[:300]}")
    if result2.stdout:
        print(f"stdout: {result2.stdout[:300]}")

print()

# ============================================================
# ТЕСТ 3: csptest.exe -hash -sign (хэш + подпись)
# ============================================================
print("-" * 80)
print("ТЕСТ 3: csptest.exe -hash -sign (хэш + подпись)")
print("-" * 80)

sig3_file = os.path.join(DEBUG_DIR, "test_sig3.txt")
cmd3 = f'"{CSP_PATH}" -hash -sign -my "{CERT_THUMBPRINT}" -in "{test_file}" -out "{sig3_file}" -base64'
print(f"Команда: {cmd3}")

result3 = subprocess.run(
    cmd3,
    shell=True,
    capture_output=True,
    timeout=60,
    encoding='cp866'
)

if result3.returncode == 0:
    print("✅ УСПЕХ!")
    if os.path.exists(sig3_file):
        with open(sig3_file, 'r') as f:
            sig3 = f.read().strip()
        print(f"Размер подписи: {len(sig3)} символов")
        print(f"Начало: {sig3[:60]}...")
else:
    print(f"❌ ОШИБКА: {result3.returncode}")
    if result3.stderr:
        print(f"stderr: {result3.stderr[:300]}")
    if result3.stdout:
        print(f"stdout: {result3.stdout[:300]}")

print()

# ============================================================
# ИТОГИ
# ============================================================
print("=" * 80)
print("ИТОГИ:")
print("=" * 80)

results = [
    ("csptest -sign", result1.returncode == 0),
    ("csptest -sfsign -sign", result2.returncode == 0),
    ("csptest -hash -sign", result3.returncode == 0),
]

for name, ok in results:
    status = "✅" if ok else "❌"
    print(f"{status} {name}")

print()
print("Следующий шаг: запустить этот скрипт и показать результат")
print("=" * 80)
input("Нажмите Enter для выхода...")
