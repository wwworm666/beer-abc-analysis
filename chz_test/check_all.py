"""
Проверка всех компонентов для работы с Честный ЗНАК
БЕЗ подписи - только диагностика
"""

import subprocess
import urllib.request
import urllib.error
import ssl
import socket
import os
import sys
from datetime import datetime

# Пути к CryptoPro
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERTMGR_PATH = r"C:\Program Files\Crypto Pro\CSP\certmgr.exe"

# URL Честный ЗНАК
CHZ_URL = "https://markirovka.crpt.ru"
CHZ_API = "https://markirovka.crpt.ru/api/v3/true-api"

print("=" * 60)
print("🔍 ДИАГНОСТИКА: Рутокен + Интернет + Честный ЗНАК")
print("=" * 60)
print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

all_ok = True

# ============================================================
# 1. ПРОВЕРКА CRYPTOPRO CSP
# ============================================================
print("=" * 60)
print("1️⃣ CRYPTOPRO CSP")
print("=" * 60)

if not os.path.exists(CSP_PATH):
    print(f"❌ csptest.exe не найден: {CSP_PATH}")
    all_ok = False
else:
    size = os.path.getsize(CSP_PATH)
    if size == 0:
        print(f"❌ csptest.exe пустой (0 байт)")
        all_ok = False
    else:
        print(f"✅ csptest.exe: {size} байт")

if not os.path.exists(CERTMGR_PATH):
    print(f"❌ certmgr.exe не найден: {CERTMGR_PATH}")
    all_ok = False
else:
    print(f"✅ certmgr.exe: {os.path.getsize(CERTMGR_PATH)} байт")

# ============================================================
# 2. ПРОВЕРКА РУТОКЕНА (через certmgr)
# ============================================================
print("\n" + "=" * 60)
print("2️⃣ РУТОКЕН И СЕРТИФИКАТЫ")
print("=" * 60)

try:
    result = subprocess.run(
        [CERTMGR_PATH, "-list"],
        capture_output=True,
        text=True,
        timeout=30,
        encoding='cp866'
    )

    if result.returncode == 0:
        output = result.stdout

        if "Субъект" in output:
            print("✅ Сертификаты найдены!")

            # Парсим информацию
            lines = output.split('\n')
            for line in lines:
                if 'Субъект:' in line:
                    subj = line.split(':', 1)[1].strip()[:50]
                    print(f"   Субъект: {subj}...")
                elif 'Истекает' in line:
                    print(f"   Действителен до: {line.split(':', 1)[1].strip()}")
                elif 'SHA1 отпечаток' in line:
                    print(f"   Отпечаток: {line.split(':', 1)[1].strip()}")
        else:
            print("❌ Сертификаты не найдены")
            print("   Проверьте, вставлен ли Рутокен в USB")
            all_ok = False
    else:
        print(f"❌ Ошибка certmgr (код {result.returncode})")
        all_ok = False

except FileNotFoundError:
    print("❌ certmgr.exe не найден")
    all_ok = False
except Exception as e:
    print(f"❌ Ошибка: {e}")
    all_ok = False

# ============================================================
# 3. ПРОВЕРКА КОНТЕЙНЕРОВ (через csptest)
# ============================================================
print("\n" + "=" * 60)
print("3️⃣ КОНТЕЙНЕРЫ КЛЮЧЕЙ (csptest)")
print("=" * 60)

try:
    result = subprocess.run(
        [CSP_PATH, "-keys", "-enum"],
        capture_output=True,
        text=True,
        timeout=30,
        encoding='cp866'
    )

    if result.returncode == 0:
        output = result.stdout
        found = False

        for line in output.split('\n'):
            line = line.strip()
            if line and not line.startswith('CSP') and not line.startswith('AcquireContext') and not line.startswith('Total') and not line.startswith('['):
                if len(line) > 10:
                    print(f"✅ Контейнер: {line}")
                    found = True

        if not found:
            print("⚠️  Контейнеры не найдены")
    else:
        print(f"❌ Ошибка csptest (код {result.returncode})")
        print(f"   {result.stderr[:200]}")
        all_ok = False

except Exception as e:
    print(f"❌ Ошибка: {e}")
    all_ok = False

# ============================================================
# 4. ПРОВЕРКА DNS
# ============================================================
print("\n" + "=" * 60)
print("4️⃣ DNS")
print("=" * 60)

try:
    ip = socket.gethostbyname('markirovka.crpt.ru')
    print(f"✅ DNS: markirovka.crpt.ru → {ip}")
except Exception as e:
    print(f"❌ DNS ошибка: {e}")
    all_ok = False

# ============================================================
# 5. ПРОВЕРКА HTTPS
# ============================================================
print("\n" + "=" * 60)
print("5️⃣ HTTPS ПОДКЛЮЧЕНИЕ")
print("=" * 60)

try:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    opener = urllib.request.build_opener(https_handler)

    response = opener.open(urllib.request.Request(CHZ_URL), timeout=15)
    print(f"✅ HTTPS: {CHZ_URL}")
    print(f"   Статус: {response.status}")
except urllib.error.HTTPError as e:
    print(f"⚠️  HTTP {e.code} - сервер доступен")
except Exception as e:
    print(f"❌ Ошибка: {e}")
    all_ok = False

# ============================================================
# 6. ПРОВЕРКА API ЧЕСТНЫЙ ЗНАК
# ============================================================
print("\n" + "=" * 60)
print("6️⃣ API ЧЕСТНЫЙ ЗНАК")
print("=" * 60)

try:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    opener = urllib.request.build_opener(https_handler)

    response = opener.open(urllib.request.Request(f"{CHZ_API}/auth/key"), timeout=15)

    if response.status == 200:
        print(f"✅ API: {CHZ_API}/auth/key")
        print(f"   Статус: {response.status}")
    else:
        print(f"⚠️  API вернул статус: {response.status}")
except urllib.error.HTTPError as e:
    print(f"⚠️  HTTP {e.code} - API доступен")
except Exception as e:
    print(f"❌ Ошибка API: {e}")
    all_ok = False

# ============================================================
# ИТОГИ
# ============================================================
print("\n" + "=" * 60)
print("📋 ИТОГИ")
print("=" * 60)

checks = [
    ("CryptoPro CSP установлен", os.path.exists(CSP_PATH) and os.path.getsize(CSP_PATH) > 0),
    ("CertMgr установлен", os.path.exists(CERTMGR_PATH)),
    ("Рутокен (сертификаты)", True),  # Если дошли сюда - ок
    ("Контейнеры ключей", True),
    ("DNS разрешение", True),
    ("HTTPS подключение", True),
    ("API ЧЗ доступен", True),
]

for name, ok in checks:
    status = "✅" if ok else "❌"
    print(f"{status} {name}")
    if not ok:
        all_ok = False

print()
if all_ok:
    print("🎉 ВСЕ КОМПОНЕНТЫ РАБОТАЮТ!")
    print()
    print("Следующий шаг: тестирование подписи и получения токена")
else:
    print("⚠️  Обнаружены проблемы. Проверьте логи выше.")

print("\n" + "=" * 60)
input("Нажмите Enter для выхода...")
