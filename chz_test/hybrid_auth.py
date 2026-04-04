# -*- coding: utf-8 -*-
"""
HYBRID AUTH - Python gets data, manual sign, Python sends to API
Run on bar PC with Rutoken connected
"""

import urllib.request
import urllib.error
import json
import ssl
import os

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"

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

def main():
    print("=" * 80)
    print("CHESTNY ZNAK API - HYBRID AUTHENTICATION")
    print("=" * 80)

    os.makedirs(DEBUG_DIR, exist_ok=True)

    # ===== STEP 1: Get data from API =====
    print("\n[STEP 1] Getting UUID and DATA from CHZ API...")
    status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")

    if status != 200:
        print(f"ERROR: {auth_data}")
        input("Press Enter to exit...")
        return

    uuid = auth_data.get('uuid')
    data_to_sign = auth_data.get('data')

    print(f"OK UUID: {uuid}")
    print(f"OK DATA: '{data_to_sign}' ({len(data_to_sign)} chars)")

    # Save data (UTF-8 without BOM, without newline)
    data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")
    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    with open(os.path.join(DEBUG_DIR, "uuid.txt"), 'w') as f:
        f.write(uuid)

    print(f"\nOK Data saved to: {data_file}")

    # ===== STEP 2: Manual signing =====
    print("\n" + "=" * 80)
    print("[STEP 2] SIGN DATA MANUALLY")
    print("=" * 80)
    print("\nRun ONE of these commands in cmd (as administrator):")
    print()
    print("Option A (csptest.exe):")
    print(f'  "C:\\Program Files\\Crypto Pro\\CSP\\csptest.exe" -sfsign -sign -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{DEBUG_DIR}\\sig.txt" -base64')
    print()
    print("Option B (certmgr.exe):")
    print(f'  "C:\\Program Files (x86)\\Crypto Pro\\CSP\\certmgr.exe" -sign -thumb "{CERT_THUMBPRINT}" -in "{data_file}" -out "{DEBUG_DIR}\\sig.txt" -base64')
    print()
    print("OR open CryptoARM GUI and sign the file manually.")
    print()
    print(f"\nAfter signing, paste the signature content into: {DEBUG_DIR}\\sig.txt")
    print("The signature should be base64 (can be multi-line or single line)")

    input("\nPress Enter after you created the signature file...")

    # ===== STEP 3: Read signature and send =====
    print("\n[STEP 3] Reading signature and sending to API...")

    sig_file = os.path.join(DEBUG_DIR, "sig.txt")
    if not os.path.exists(sig_file):
        print(f"ERROR: Signature file not found: {sig_file}")
        print("Please create it using one of the commands above.")
        input("Press Enter to exit...")
        return

    with open(sig_file, 'r', encoding='utf-8') as f:
        signature = f.read().strip()

    # Clean to single line base64
    signature = ''.join(c for c in signature if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

    print(f"OK Signature loaded: {len(signature)} chars")

    # ===== STEP 4: Send to API =====
    print("\n[STEP 4] Sending authentication request...")

    # Try different formats
    formats = [
        ("v3: data + unitedToken", {"data": signature, "unitedToken": True}),
        ("v2: uuid + data", {"uuid": uuid, "data": signature}),
        ("v2: uuid + data + inn", {"uuid": uuid, "data": signature, "inn": "7801630649"}),
    ]

    for name, payload in formats:
        print(f"\n  Trying: {name}")

        # Save request for debug
        with open(os.path.join(DEBUG_DIR, f"request_{name.split(':')[0]}.json"), 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        status, response = make_request(
            f"{CHZ_BASE_URL}/auth/simpleSignIn",
            method="POST",
            data=payload
        )

        print(f"  Status: {status}")

        if status == 200:
            print(f"\n{'='*60}")
            print("SUCCESS! TOKEN RECEIVED!")
            print(f"{'='*60}")
            print(f"Token: {response}")

            # Save token
            with open(os.path.join(DEBUG_DIR, "token.json"), 'w', encoding='utf-8') as f:
                json.dump({"token": response}, f, indent=2)
            print(f"\nOK Token saved to: {DEBUG_DIR}\\token.json")

            print("\n" + "=" * 80)
            input("Press Enter to exit...")
            return
        else:
            error_msg = response.get('error_message', str(response))
            print(f"  Error: {error_msg}")

    # All formats failed
    print("\n" + "=" * 80)
    print("ALL FORMATS FAILED")
    print("=" * 80)

    # Save error details
    with open(os.path.join(DEBUG_DIR, "error.json"), 'w', encoding='utf-8') as f:
        json.dump({
            "uuid": uuid,
            "data_to_sign": data_to_sign,
            "signature_length": len(signature),
            "formats_tried": [f[0] for f in formats],
            "last_response": response
        }, f, indent=2, ensure_ascii=False)

    print(f"\nError details saved to: {DEBUG_DIR}\\error.json")
    print("\nPossible fixes:")
    print("1. Check if signature is CAdES-BES format (try -cades flag)")
    print("2. Check if signature is attached (not detached)")
    print("3. Verify certificate is valid and trusted by CHZ")
    print("\nSend error.json to CHZ support: support@crpt.ru")

    print("\n" + "=" * 80)
    input("Press Enter to exit...")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 80)
        input("Press Enter to exit...")
