# -*- coding: utf-8 -*-
"""
Вариант 1: csptest с -cades_strict -add
Это ключевой новый подход.

-cades_strict  = генерирует signingCertificateV2 атрибут (обязателен для CAdES-BES)
-add           = добавляет сертификат в PKCS#7 (цепочка доверия)
-detached      = отсоединённая подпись

Запускать из cmd ОТ ИМЕНИ АДМИНИСТРАТОРА
"""

import urllib.request, urllib.error, json, ssl, subprocess, os

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
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
    """Очистить до чистого base64"""
    return ''.join(c for c in text
                   if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')


def sign_with_options(label, cmd, variant_name):
    """Универсальная функция подписи + отправка"""
    print(f"\n{'─' * 70}")
    print(f"  {label}")
    print(f"{'─' * 70}")

    sig_file = os.path.join(DEBUG_DIR, f"sig_{variant_name}.txt")

    # Шаг 1: Получить данные
    print("\n[1] Получение данных от API...")
    status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")
    if status != 200:
        print(f"  ❌ GET /auth/key failed: {auth_data}")
        return None

    uuid = auth_data.get('uuid')
    data_to_sign = auth_data.get('data')
    print(f"  UUID: {uuid}")
    print(f"  DATA: '{data_to_sign}' ({len(data_to_sign)} chars)")

    # Шаг 2: Сохранить
    data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")
    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    # Шаг 3: Подписать
    full_cmd = cmd.format(
        csp=CSP_PATH,
        cert=CERT_THUMBPRINT,
        data_in=data_file,
        data_out=sig_file
    )

    print(f"\n[2] Подпись: {full_cmd}")
    result = subprocess.run(full_cmd, shell=True, capture_output=True,
                            timeout=60, encoding='cp866')

    print(f"  Return code: {result.returncode}")
    if result.stdout:
        print(f"  stdout: {result.stdout[:300]}")
    if result.stderr:
        print(f"  stderr: {result.stderr[:300]}")

    if result.returncode != 0:
        print(f"  ❌ Подпись не создана")
        return None

    # Шаг 4: Прочитать подпись
    if not os.path.exists(sig_file):
        print(f"  ❌ Файл подписи не создан: {sig_file}")
        return None

    with open(sig_file, 'r', encoding='utf-8-sig') as f:
        raw_sig = f.read()

    signature = clean_base64(raw_sig)
    print(f"  ✅ Подпись: {len(signature)} chars")
    print(f"  Первые 60: {signature[:60]}")

    # Сохраняем
    with open(os.path.join(DEBUG_DIR, f"sig_{variant_name}_clean.txt"), 'w') as f:
        f.write(signature)

    # Шаг 5: Локальная проверка
    print(f"\n[3] Локальная проверка...")
    verify_cmd = f'"{CSP_PATH}" -sfsign -verify -my "{CERT_THUMBPRINT}" -in "{data_file}" -signature "{sig_file}" -base64'
    print(f"  {verify_cmd[:150]}...")
    v_result = subprocess.run(verify_cmd, shell=True, capture_output=True,
                              timeout=60, encoding='cp866')
    if v_result.returncode == 0:
        print(f"  ✅ Верификация УСПЕШНА")
    else:
        print(f"  ⚠️ Верификация не прошла (код {v_result.returncode})")
        print(f"     Это НЕ критично — пробуем отправить в API")

    # Шаг 6: Отправить в API (variant v3)
    print(f"\n[4] Отправка в API (v3 format: data + unitedToken)...")
    payload = {"data": signature, "unitedToken": True}

    with open(os.path.join(DEBUG_DIR, f"request_{variant_name}.json"), 'w',
              encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    status, response = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        method="POST", data=payload
    )

    print(f"  Статус: {status}")
    if status == 200:
        print(f"  🎉 УСПЕХ! Токен: {response}")
        with open(os.path.join(DEBUG_DIR, "token.json"), 'w') as f:
            json.dump({"token": response}, f, indent=2)
        return response
    else:
        error_msg = response.get('error_message', str(response))
        print(f"  ❌ {error_msg}")

    # Попробовать v2 variant (uuid + data)
    print(f"\n[5] Отправка в API (v2 format: uuid + data)...")
    payload_v2 = {"uuid": uuid, "data": signature}

    status_v2, response_v2 = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        method="POST", data=payload_v2
    )

    print(f"  Статус: {status_v2}")
    if status_v2 == 200:
        print(f"  🎉 УСПЕХ (v2)! Токен: {response_v2}")
        with open(os.path.join(DEBUG_DIR, "token.json"), 'w') as f:
            json.dump({"token": response_v2}, f, indent=2)
        return response_v2
    else:
        print(f"  ❌ {response_v2.get('error_message', str(response_v2))}")

    return None


def main():
    print("=" * 70)
    print("  ЧЗ API — Аутентификация с опциями CAdES")
    print("=" * 70)

    # Вариант A: detached + cades_strict (без -add)
    variant_a = ('"{csp}" -sfsign -sign -detached -my "{cert}" '
                 '-in "{data_in}" -out "{data_out}" -base64 -cades_strict')

    # Вариант B: detached + cades_strict + add (сертификат в подпись)
    variant_b = ('"{csp}" -sfsign -sign -detached -my "{cert}" '
                 '-in "{data_in}" -out "{data_out}" -base64 -cades_strict -add')

    # Вариант C: attached + cades_strict + add
    variant_c = ('"{csp}" -sfsign -sign -my "{cert}" '
                 '-in "{data_in}" -out "{data_out}" -base64 -cades_strict -add')

    # Вариант D: detached + cades_strict + addsigtime + add
    variant_d = ('"{csp}" -sfsign -sign -detached -my "{cert}" '
                 '-in "{data_in}" -out "{data_out}" -base64 '
                 '-cades_strict -addsigtime -add')

    # Вариант E: detached без cades_strict но с addsigtime
    variant_e = ('"{csp}" -sfsign -sign -detached -my "{cert}" '
                 '-in "{data_in}" -out "{data_out}" -base64 -add -addsigtime')

    variants = [
        ("A: detached + cades_strict", variant_a, "a_cades_detached"),
        ("B: detached + cades_strict + add", variant_b, "b_cades_add"),
        ("C: attached + cades_strict + add", variant_c, "c_cades_attached"),
        ("D: detached + cades_strict + addsigtime + add", variant_d, "d_cades_sigtimе"),
        ("E: detached + addsigtime + add (без cades_strict)", variant_e, "e_sigtimе_add"),
    ]

    for label, cmd, variant_name in variants:
        result = sign_with_options(label, cmd, variant_name)
        if result is not None:
            print(f"\n{'=' * 70}")
            print(f"  ✅ УСПЕХ на варианте: {label}")
            print(f"{'=' * 70}")
            return

        input(f"\n→ Нажми Enter для следующего варианта...")

    print(f"\n{'=' * 70}")
    print(f"  ❌ Все варианты не прошли")
    print(f"{'=' * 70}")
    print(f"\nСледующий шаг: отправить error логи в support@crpt.ru")
    input("\nНажми Enter для выхода...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ CRITICAL: {e}")
        import traceback
        traceback.print_exc()
