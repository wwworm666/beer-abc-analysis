"""
Проверка подключения к Рутокену и Честный ЗНАК API
Без подписи - только тест доступности
"""
import subprocess
import urllib.request
import ssl
import json
import sys

# ==================== НАСТРОЙКИ ====================
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
CHZ_AUTH_URL = "https://markirovka.crpt.ru/api/v3/true-api/auth/key"

def check_rutoken():
    """Проверка видимости Рутокена и сертификата"""
    print("\n" + "="*50)
    print("1️⃣ ПРОВЕРКА РУТОКЕНА")
    print("="*50)

    # Проверка csptest.exe через shell (обходит проблему Win32)
    try:
        result = subprocess.run(
            f'"{CSP_PATH}" -info',
            capture_output=True,
            timeout=10,
            encoding='cp866',
            shell=True
        )
        print(f"✅ CryptoPro CSP найден: {CSP_PATH}")
    except FileNotFoundError:
        print(f"❌ CryptoPro CSP не найден: {CSP_PATH}")
        return False
    except Exception as e:
        print(f"❌ Ошибка CSP: {e}")
        return False

    # Проверка сертификата
    try:
        result = subprocess.run(
            f'"{CSP_PATH}" -certcheck -my "{CERT_THUMBPRINT}"',
            capture_output=True,
            timeout=10,
            encoding='cp866',
            shell=True
        )
        if result.returncode == 0:
            print(f"✅ Сертификат найден: {CERT_THUMBPRINT}")
        else:
            print(f"❌ Сертификат не найден")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"❌ Ошибка проверки сертификата: {e}")
        return False

    # Список контейнеров
    try:
        result = subprocess.run(
            f'"{CSP_PATH}" -keys -enum',
            capture_output=True,
            timeout=10,
            encoding='cp866',
            shell=True
        )
        if "OK" in result.stdout:
            print(f"✅ Контейнеры ключей доступны")
        else:
            print(f"⚠ Контейнеры не найдены или Рутокен не вставлен")
    except Exception as e:
        print(f"⚠ Ошибка доступа к контейнерам: {e}")

    return True


def check_internet():
    """Проверка интернета"""
    print("\n" + "="*50)
    print("2️⃣ ПРОВЕРКА ИНТЕРНЕТА")
    print("="*50)

    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request("https://www.google.com", method='HEAD')
        urllib.request.urlopen(req, timeout=10, context=ctx)
        print("✅ Интернет работает")
        return True
    except Exception as e:
        print(f"❌ Нет интернета: {e}")
        return False


def check_chz_auth():
    """Проверка доступности ЧЗ API (без подписи)"""
    print("\n" + "="*50)
    print("3️⃣ ПРОВЕРКА ЧЗ API")
    print("="*50)

    # Проверка доступности сервера
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(CHZ_AUTH_URL, method='GET')
        response = urllib.request.urlopen(req, timeout=30, context=ctx)
        print(f"✅ ЧЗ API доступен: {CHZ_AUTH_URL}")
        print(f"   Статус: {response.status}")
        return True
    except urllib.error.HTTPError as e:
        # 400/401 - это нормально, сервер ответил
        print(f"✅ ЧЗ API доступен (ответил {e.code})")
        return True
    except urllib.error.URLError as e:
        print(f"❌ ЧЗ API недоступен: {e.reason}")
        return False
    except Exception as e:
        print(f"❌ Ошибка подключения к ЧЗ: {e}")
        return False


def check_chz_dns():
    """Проверка DNS разрешения"""
    print("\n" + "="*50)
    print("4️⃣ ПРОВЕРКА DNS")
    print("="*50)

    import socket
    try:
        ip = socket.gethostbyname('markirovka.crpt.ru')
        print(f"✅ DNS: markirovka.crpt.ru → {ip}")
        return True
    except Exception as e:
        print(f"❌ DNS не работает: {e}")
        return False


if __name__ == "__main__":
    print("╔" + "="*48 + "╗")
    print("║  ПРОВЕРКА ПОДКЛЮЧЕНИЯ К ЧЕСТНЫЙ ЗНАК   ║")
    print("║  " + subprocess.getoutput("date /T") + "                  ║")
    print("╚" + "="*48 + "╝")

    results = {
        "Рутокен": check_rutoken(),
        "Интернет": check_internet(),
        "ЧЗ API": check_chz_auth(),
        "DNS": check_chz_dns()
    }

    print("\n" + "="*50)
    print("📊 ИТОГИ")
    print("="*50)

    all_ok = True
    for name, result in results.items():
        status = "✅ OK" if result else "❌ FAIL"
        print(f"  {name}: {status}")
        if not result:
            all_ok = False

    print("\n" + "="*50)
    if all_ok:
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
        print("   Можно запускать test_chz_api.py")
    else:
        print("❌ ЕСТЬ ПРОБЛЕМЫ С ПОДКЛЮЧЕНИЕМ")
        print("   Устраните их перед запуском подписи")
    print("="*50)

    input("\nEnter для выхода...")
