# -*- coding: utf-8 -*-
"""
Диагностика: распаковать PKCS#7 и посмотреть что внутри.

Сравниваем:
1. Структуру подписи от csptest -sfsign -sign
2. Структуру подписи от csptest -sfsign -sign -cades_strict
3. Какие атрибуты есть в PKCS#7 (есть ли signingCertificateV2?)

Это поможет понять ПОЧЕМУ API отвергает подпись.

Запускать из cmd ОТ ИМЕНИ АДМИНИСТРАТОРА
"""

import subprocess, os, base64, binascii

CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")

os.makedirs(DEBUG_DIR, exist_ok=True)


def decode_base64_to_der(b64_text):
    """Base64 → DER bytes"""
    cleaned = ''.join(c for c in b64_text if c in
                      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
    try:
        return base64.b64decode(cleaned)
    except Exception as e:
        print(f"  ❌ Ошибка декодирования base64: {e}")
        return None


def asn1_dump(der_bytes, indent=0):
    """Простой дамп ASN.1 структуры"""
    prefix = "  " * indent
    if len(der_bytes) < 2:
        return f"{prefix} Too short: {der_bytes.hex()}"

    pos = 0
    lines = []

    while pos < len(der_bytes):
        if pos + 1 >= len(der_bytes):
            lines.append(f"{prefix} Truncated tag at {pos}")
            break

        tag = der_bytes[pos]
        pos += 1

        tag_name = TAG_NAMES.get(tag, f"Tag(0x{tag:02x})")

        # Длина
        if pos >= len(der_bytes):
            lines.append(f"{prefix} {tag_name}: truncated length")
            break

        length_byte = der_bytes[pos]
        pos += 1

        if length_byte & 0x80:
            num_length_bytes = length_byte & 0x7f
            if num_length_bytes > 4:
                lines.append(f"{prefix} {tag_name}: indefinite length")
                break
            length = 0
            for i in range(num_length_bytes):
                if pos >= len(der_bytes):
                    break
                length = (length << 8) | der_bytes[pos]
                pos += 1
        else:
            length = length_byte

        end = pos + length
        if end > len(der_bytes):
            lines.append(f"{prefix} {tag_name}: truncated content (need {length}, have {len(der_bytes) - pos + length - (end - len(der_bytes))})")
            break

        content = der_bytes[pos:end]
        pos = end

        # Конструириованный тег?
        if tag & 0x20:
            lines.append(f"{prefix} {tag_name} ({length} bytes)")
            lines.append(asn1_dump(content, indent + 1))
        else:
            if length <= 32:
                lines.append(f"{prefix} {tag_name}: {content.hex()}")
            else:
                lines.append(f"{prefix} {tag_name}: ({length} bytes) {content[:16].hex()}...")

    return '\n'.join(lines)


# ASN.1 tag names
TAG_NAMES = {
    0x30: "SEQUENCE",
    0x31: "SET",
    0x02: "INTEGER",
    0x06: "OBJECT IDENTIFIER",
    0x04: "OCTET STRING",
    0x05: "NULL",
    0x0c: "UTF8String",
    0x13: "PrintableString",
    0x17: "UTCTime",
    0x18: "GeneralizedTime",
    0xa0: "Context(0)",
    0xa1: "Context(1)",
    0xa2: "Context(2)",
    0xa3: "Context(3)",
    0xa4: "Context(4)",
    0xa5: "Context(5)",
    0xa6: "Context(6)",
    0xa7: "Context(7)",
    0xa8: "Context(8)",
    0xa9: "Context(9)",
    0x80: "Context(0)[primitive]",
    0x81: "Context(1)[prim]",
    0x82: "Context(2)[prim]",
    0x83: "Context(3)[prim]",
    0x84: "Context(4)[prim]",
    0x85: "Context(5)[prim]",
    0x86: "Context(6)[prim]",
    0x87: "Context(7)[prim]",
    0x0c: "UTF8String",
    0x16: "IA5String",
    0x03: "BIT STRING",
    0x0a: "Enumerated",
    0x01: "BOOLEAN",
    0x0e: "External",
    0x10: "Sequence/Of",
    0x11: "Set/Of",
    0x15: "T61String",
    0x1c: "UniversalString",
    0x1e: "BMPString",
}


def sign_and_dump(label, sign_cmd, variant_name):
    """Подписать, загрузить, распарсить PKCS#7"""
    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")

    data_file = os.path.join(DEBUG_DIR, "data_to_sign_diag.txt")
    sig_file = os.path.join(DEBUG_DIR, f"sig_diag_{variant_name}.txt")

    # Данные
    data_to_sign = "GNUFBAZBMPIUUMLXNMIOGSHTGFXZMT"  # test data (не от API, просто для диагностики)
    # Или получить реальные данные от API
    print(f"  DATA: '{data_to_sign}'")

    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    # Подписать
    full_cmd = sign_cmd.format(csp=CSP_PATH, cert=CERT_THUMBPRINT,
                                data_in=data_file, data_out=sig_file)
    print(f"  Команда: {full_cmd[:120]}...")

    result = subprocess.run(full_cmd, shell=True, capture_output=True,
                            timeout=60, encoding='cp866')

    print(f"  Return code: {result.returncode}")
    if result.stdout:
        print(f"  stdout: {result.stdout[:300]}")
    if result.stderr:
        print(f"  stderr: {result.stderr[:300]}")

    if result.returncode != 0 or not os.path.exists(sig_file):
        print(f"  ❌ Подпись не создана")
        return

    # Загрузить подпись
    with open(sig_file, 'r', encoding='utf-8-sig') as f:
        raw_sig = f.read()

    # Попробовать извлечь DER из PEM или из base64 файла
    der_bytes = None

    if '-----BEGIN ' in raw_sig:
        print(f"  📄 PEM формат обнаружен")
        # Извлечь из PEM
        pem_type = ''
        b64 = ''
        for line in raw_sig.splitlines():
            if line.startswith('-----BEGIN'):
                pem_type = line
                continue
            if line.startswith('-----END'):
                break
            b64 += line.strip()
        der_bytes = decode_base64_to_der(b64)
        print(f"  PEM type: {pem_type}")
    else:
        # Считать весь файл как base64
        cleaned = ''.join(c for c in raw_sig if c in
                          'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
        der_bytes = decode_base64_to_der(cleaned)

    if not der_bytes:
        print(f"  ❌ Не удалось декодировать")
        return

    print(f"\n  Размер PKCS#7: {len(der_bytes)} bytes")
    print(f"  Первые 32 байта (hex): {der_bytes[:32].hex()}")

    # Определить тип
    if der_bytes[0] == 0x30:
        print(f"  ✅ SEQUENCE — валидный ASN.1")
    elif der_bytes[0] == 0x06:
        print(f"  ⚠️ OID на верхнем уровне (возможно detached)")
    elif der_bytes[0] == 0x04:
        print(f"  ⚠️ OCTET STRING на верхнем уровне")
    else:
        print(f"  ⚠️ Не SEQUENCE (тег 0x{der_bytes[0]:02x})")

    # Простой дамп верхнего уровня
    print(f"\n  ASN.1 дамп (верхние 3 уровня):")
    print(asn1_dump(der_bytes, indent=1))

    # Проверить наличие OID-ов подписи
    oid_map = {
        '1.2.840.113549.1.7.2': 'signedData (PKCS#7)',
        '1.2.840.113549.1.7.1': 'data',
        '1.2.840.113549.1.9.16.1.11': 'signingCertificate',
        '1.2.840.113549.1.9.16.2.12': 'signingCertificateV2 (CAdES)',
        '1.2.840.113549.1.9.5': 'signingTime',
        '1.2.840.113549.1.9.3': 'contentType',
        '1.2.840.113549.1.9.4': 'messageDigest',
        '1.2.840.113549.1.9.1': 'emailAddress',
        '1.2.643.2.2.35.1': 'GOST R 34.10-2012 256',
        '1.2.643.2.2.3': 'GOST R 34.10-2001',
        '1.2.643.7.1.1.1.1': 'GOST R 34.10-2012 256',
        '1.2.643.2.2.31.1': 'GOST 28147-89',
        '1.2.643.7.1.1.3.1': 'GOST 28147-89 (2015)',
        '1.2.643.2.2.9': 'GOST R 34.11-94',
        '1.2.643.7.1.1.2.2': 'GOST R 34.11-2012 256',
    }

    print(f"\n  Поиск OID-ов в структуре:")
    found_oids = find_oids_in_der(der_bytes, oid_map)
    for oid_str, oid_name in sorted(found_oids, key=lambda x: x[1]):
        print(f"    {oid_str} = {oid_name}")

    # Сохранить hex-дамп
    hex_file = os.path.join(DEBUG_DIR, f"sig_diag_{variant_name}.hex")
    with open(hex_file, 'w') as f:
        f.write(der_bytes.hex())
    print(f"\n  Hex-дамп сохранён: {hex_file}")

    # Сохранить DER
    der_save = os.path.join(DEBUG_DIR, f"sig_diag_{variant_name}.der")
    with open(der_save, 'wb') as f:
        f.write(der_bytes)
    print(f"  DER сохранён: {der_save}")


def find_oids_in_der(data, oid_map):
    """Найти OID-ы в DER-данных"""
    # OID кодируется тегом 0x06
    found = set()
    for i in range(len(data) - 3):
        if data[i] == 0x06:
            length = data[i + 1]
            if 1 <= length <= 10 and i + 2 + length <= len(data):
                oid_bytes = data[i + 2:i + 2 + length]
                oid_str = decode_oid(oid_bytes)
                if oid_str in oid_map:
                    found.add((oid_str, oid_map[oid_str]))
    return sorted(found)


def decode_oid(oid_bytes):
    """Декодировать OID из DER-байтов"""
    if len(oid_bytes) < 1:
        return "???"

    first = oid_bytes[0]
    components = [first // 40, first % 40]

    value = 0
    for b in oid_bytes[1:]:
        value = (value << 7) | (b & 0x7f)
        if b & 0x80 == 0:
            components.append(value)
            value = 0

    return '.'.join(str(c) for c in components)


def main():
    print("=" * 70)
    print("  Диагностика формата подписи PKCS#7")
    print("=" * 70)

    variants = [
        (
            "csptest -sfsign -sign (базовый, без флагов)",
            '"{csp}" -sfsign -sign -my "{cert}" -in "{data_in}" -out "{data_out}" -base64',
            "basic"
        ),
        (
            "csptest -sfsign -sign -detached -cades_strict",
            '"{csp}" -sfsign -sign -detached -my "{cert}" '
            '-in "{data_in}" -out "{data_out}" -base64 -cades_strict',
            "cades_strict"
        ),
        (
            "csptest -sfsign -sign -detached -cades_strict -add",
            '"{csp}" -sfsign -sign -detached -my "{cert}" '
            '-in "{data_in}" -out "{data_out}" -base64 -cades_strict -add',
            "cades_strict_add"
        ),
        (
            "csptest -sfsign -sign -detached -cades_strict -add -addsigtime",
            '"{csp}" -sfsign -sign -detached -my "{cert}" '
            '-in "{data_in}" -out "{data_out}" -base64 -cades_strict -add -addsigtime',
            "cades_sigtimе_add"
        ),
    ]

    for label, cmd, name in variants:
        try:
            sign_and_dump(label, cmd, name)
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
        input(f"\n→ Нажми Enter для следующего варианта...")

    print(f"\n{'=' * 70}")
    print(f"  Диагностика завершена. Изучите файлы в {DEBUG_DIR}")
    print(f"{'=' * 70}")
    input("\nНажми Enter для выхода...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ CRITICAL: {e}")
        import traceback
        traceback.print_exc()
