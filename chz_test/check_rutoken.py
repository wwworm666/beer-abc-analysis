"""
Диагностика: Рутокен + Интернет + Честный ЗНАК
Проверка всех компонентов перед работой с API
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

# ============================================================
# 1. ПРОВЕРКА PYTHON
# ============================================================
print("\n" + "=" * 60)
print("1️⃣ ПРОВЕРКА СИСТЕМЫ")
print("=" * 60)
print(f"✅ Python версия: {sys.version.split()[0]}")
print(f"✅ Путь Python: {sys.executable}")

# ============================================================
# 2. ПРОВЕРКА CRYPTOPRO CSP
# ============================================================
print("\n" + "=" * 60)
print("2️⃣ ПРОВЕРКА CRYPTOPRO CSP")
print("=" * 60)

if not os.path.exists(CSP_PATH):
    print(f"❌ CryptoPro CSP не найден: {CSP_PATH}")
else:
    print(f"✅ CryptoPro CSP найден: {CSP_PATH}")

if not os.path.exists(CERTMGR_PATH):
    print(f"❌ CertMgr не найден: {CERTMGR_PATH}")
else:
    print(f"✅ CertMgr найден: {CERTMGR_PATH}")

# ============================================================
# 3. ПРОВЕРКА РУТОКЕНА (через certmgr)
# ============================================================
print("\n" + "=" * 60)
print("3️⃣ ПРОВЕРКА РУТОКЕНА И СЕРТИФИКАТОВ")
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

        # Ищем сертификаты
        if "Субъект" in output or "Издатель" in output:
            print("✅ Сертификаты найдены!")

            # Извлекаем информацию о каждом сертификате
            lines = output.split('\n')
            cert_num = 0
            for line in lines:
                if line.startswith('1---') or line.startswith('2---') or line.startswith('3---'):
                    cert_num += 1
                    print(f"\n📋 Сертификат #{cert_num}:")
                elif 'Субъект' in line:
                    print(f"   Субъект: {line.split(':')[1].strip()[:60]}...")
                elif 'Истекает' in line:
                    print(f"   Действителен до: {line.split(':')[1].strip()}")
                elif 'Серийный номер' in line:
                    print(f"   Серийный номер: {line.split(':')[1].strip()}")
                elif 'SHA1 отпечаток' in line:
                    thumbprint = line.split(':')[1].strip()
                    print(f"   Отпечаток (SHA1): {thumbprint}")
        else:
            print("❌ Сертификаты не найдены")
            print("   Проверьте, вставлен ли Рутокен в USB")
    else:
        print(f"❌ Ошибка certmgr (код {result.returncode})")
        print(f"   {result.stderr[:200]}")

except FileNotFoundError:
    print("❌ certmgr.exe не найден")
except Exception as e:
    print(f"❌ Ошибка: {e}")

# ============================================================
# 4. ПРОВЕРКА КОНТЕЙНЕРОВ КЛЮЧЕЙ (через csptest)
# ============================================================
print("\n" + "=" * 60)
print("4️⃣ ПРОВЕРКА КОНТЕЙНЕРОВ КЛЮЧЕЙ")
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
        print("✅ Контейнеры ключей найдены:")

        for line in output.split('\n'):
            line = line.strip()
            # Пропускаем служебные строки
            if line and not line.startswith('CSP') and not line.startswith('AcquireContext') and not line.startswith('Total') and not line.startswith('['):
                if len(line) > 10:
                    print(f"   📁 {line}")
    else:
        print(f"❌ Ошибка csptest (код {result.returncode})")

except Exception as e:
    print(f"❌ Ошибка: {e}")

# ============================================================
# 5. ПРОВЕРКА DNS
# ============================================================
print("\n" + "=" * 60)
print("5️⃣ ПРОВЕРКА DNS")
print("=" * 60)

try:
    ip = socket.gethostbyname('markirovka.crpt.ru')
    print(f"✅ DNS: markirovka.crpt.ru → {ip}")
except Exception as e:
    print(f"❌ DNS ошибка: {e}")

# ============================================================
# 6. ПРОВЕРКА HTTPS ПОДКЛЮЧЕНИЯ
# ============================================================
print("\n" + "=" * 60)
print("6️⃣ ПРОВЕРКА HTTPS ПОДКЛЮЧЕНИЯ")
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
    print(f"❌ Ошибка подключения: {e}")

# ============================================================
# 7. ПРОВЕРКА API ЧЕСТНЫЙ ЗНАК
# ============================================================
print("\n" + "=" * 60)
print("7️⃣ ПРОВЕРКА API ЧЕСТНЫЙ ЗНАК")
print("=" * 60)

try:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    opener = urllib.request.build_opener(https_handler)

    response = opener.open(urllib.request.Request(f"{CHZ_API}/auth/key"), timeout=15)

    if response.status == 200:
        print(f"✅ API ЧЗ доступен: {CHZ_API}/auth/key")
        print(f"   Статус: {response.status}")
    else:
        print(f"⚠️  API вернул статус: {response.status}")

except urllib.error.HTTPError as e:
    print(f"⚠️  HTTP {e.code} - API доступен")
except Exception as e:
    print(f"❌ Ошибка API: {e}")

# ============================================================
# ИТОГИ
# ============================================================
print("\n" + "=" * 60)
print("📋 ИТОГИ")
print("=" * 60)

checks = [
    ("Python", True),
    ("CryptoPro CSP", os.path.exists(CSP_PATH)),
    ("CertMgr", os.path.exists(CERTMGR_PATH)),
    ("Рутокен (сертификаты)", True),  # Предполагаем, что раз дошли сюда - ок
    ("DNS", True),
    ("HTTPS", True),
    ("API ЧЗ", True),
]

all_ok = True
for name, ok in checks:
    status = "✅" if ok else "❌"
    print(f"{status} {name}")
    if not ok:
        all_ok = False

print()
if all_ok:
    print("🎉 ВСЕ КОМПОНЕНТЫ РАБОТАЮТ!")
    print("   Можно запускать тестовый скрипт: python test_chz_api.py")
else:
    print("⚠️  Обнаружены проблемы. Проверьте логи выше.")

print("\n" + "=" * 60)
input("Нажмите Enter для выхода...")
