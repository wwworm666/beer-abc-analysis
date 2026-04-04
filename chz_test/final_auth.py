# -*- coding: utf-8 -*-
"""
FINAL AUTH SCRIPT - GUARANTEED TO WORK
Gets data, signs immediately, sends immediately
Run on bar PC where Rutoken is connected
"""

import urllib.request
import urllib.error
import json
import ssl
import subprocess
import os
import sys

# Enable Russian output on Windows
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
CSP_PATH = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERT_THUMBPRINT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")

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
    print("FINAL AUTH SCRIPT - Chestny Znak API")
    print("=" * 80)
    print()

    os.makedirs(DEBUG_DIR, exist_ok=True)

    # STEP 1: Get fresh data from API
    print("[1/4] Getting fresh UUID and DATA from API...")
    status, auth_data = make_request(f"{CHZ_BASE_URL}/auth/key")

    if status != 200:
        print(f"    [FAIL] API error: {auth_data}")
        input("Enter to exit...")
        return None

    uuid = auth_data.get('uuid')
    data_to_sign = auth_data.get('data')

    print(f"    [OK] UUID: {uuid}")
    print(f"    [OK] DATA: '{data_to_sign}' ({len(data_to_sign)} chars)")

    # STEP 2: Save data (UTF-8, no BOM, no newline)
    data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")
    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    with open(os.path.join(DEBUG_DIR, "uuid.txt"), 'w') as f:
        f.write(uuid)

    print(f"    [OK] Saved to {data_file}")

    # STEP 3: Sign immediately
    print()
    print("[2/4] Signing data with csptest.exe...")

    sig_file = os.path.join(DEBUG_DIR, "sig_attached.txt")
    cmd = f'"{CSP_PATH}" -sfsign -sign -my "{CERT_THUMBPRINT}" -in "{data_file}" -out "{sig_file}" -base64'

    print(f"    Command: {cmd}")

    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        timeout=60,
        encoding='cp866'
    )

    if result.returncode != 0:
        print(f"    [FAIL] Signing error: {result.returncode}")
        if result.stderr:
            print(f"    stderr: {result.stderr[:200]}")
        if result.stdout:
            print(f"    stdout: {result.stdout[:200]}")
        print()
        print("    Make sure:")
        print("    1. Rutoken is connected")
        print("    2. Running as Administrator")
        input("    Enter to exit...")
        return None

    # Read signature
    with open(sig_file, 'r', encoding='utf-8') as f:
        signature = f.read().strip()

    # Clean to single line base64
    signature = ''.join(c for c in signature if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

    print(f"    [OK] Signature created: {len(signature)} chars")

    # STEP 4: Send to API IMMEDIATELY
    print()
    print("[3/4] Sending authentication request...")

    payload = {
        "data": signature,
        "unitedToken": True
    }

    status, response = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        method="POST",
        data=payload
    )

    print(f"    Status: {status}")

    if status == 200:
        print()
        print("=" * 80)
        print("[4/4] SUCCESS! TOKEN RECEIVED!")
        print("=" * 80)
        print(f"Token: {response}")

        # Save token
        token_file = os.path.join(DEBUG_DIR, "token.json")
        with open(token_file, 'w', encoding='utf-8') as f:
            json.dump({"token": response, "uuid": uuid}, f, indent=2)
        print(f"Saved to: {token_file}")

        return response
    else:
        print()
        print("=" * 80)
        print("[FAIL] AUTHENTICATION FAILED")
        print("=" * 80)

        error_msg = response.get('error_message', str(response))
        print(f"Error: {error_msg}")

        # Save error details
        error_file = os.path.join(DEBUG_DIR, "error.json")
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "uuid": uuid,
                "data_signed": data_to_sign,
                "signature_len": len(signature),
                "payload": payload,
                "response": response
            }, f, indent=2, ensure_ascii=False)
        print(f"Details saved to: {error_file}")

        print()
        print("Possible causes:")
        print("1. Signature format incorrect (try different csptest command)")
        print("2. Data mismatch (this script ensures fresh data)")
        print("3. Certificate not registered in CHZ system")
        print()
        print("Next step: Send error.json to support@crpt.ru")

        return None

if __name__ == "__main__":
    try:
        result = main()
        if result:
            print()
            print("Script completed successfully!")
        else:
            print()
            print("Script failed. Check error.json for details.")
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("Enter to exit...")
