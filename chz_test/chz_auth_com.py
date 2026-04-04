# -*- coding: utf-8 -*-
"""
CHESTNY ZNAK API AUTHENTICATION (COM version)
Uses CryptoPro COM object instead of csptest.exe
Run from cmd AS ADMINISTRATOR
"""

import urllib.request
import urllib.error
import json
import ssl
import os
import time
import base64

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
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

def sign_with_com(data_to_sign):
    """Sign data using CryptoPro COM object"""
    try:
        # Try to create CryptoPro COM object
        import win32com.client

        # Create CPSign object
        cades_sign = win32com.client.Dispatch("CPSignCades.Native.1")

        # Find certificate by thumbprint
        store = win32com.client.Dispatch("CPCertStore.Native.1")
        store.OpenSystemStore()

        cert = None
        for c in store.Certificates:
            thumbprint = c.Thumbprint.replace(" ", "").lower()
            if thumbprint == CERT_THUMBPRINT.lower():
                cert = c
                break

        store.Close()

        if not cert:
            print(f"Certificate {CERT_THUMBPRINT} not found")
            return None

        # Sign data (CAdES BES format)
        # CAPICOM_ENCODING_BASE64 = 0
        # CADESCOM_CADES_BES = 0
        signed_data = cades_sign.SignCades(
            data_to_sign.encode('utf-8'),
            0,  # CAdES BES
            cert,
            True  # Detached signature
        )

        # Convert to base64 string
        signature = base64.b64encode(signed_data).decode('utf-8')
        return signature

    except Exception as e:
        print(f"COM signing error: {e}")
        return None

def sign_with_certmgr(data_to_sign):
    """Alternative: try certmgr.exe"""
    import subprocess

    certmgr_paths = [
        r"C:\Program Files\Crypto Pro\CSP\certmgr.exe",
        r"C:\Program Files (x86)\Crypto Pro\CSP\certmgr.exe",
    ]

    certmgr = None
    for path in certmgr_paths:
        if os.path.exists(path):
            certmgr = path
            break

    if not certmgr:
        print("certmgr.exe not found")
        return None

    # Save data to temp file
    temp_file = os.path.join(DEBUG_DIR, "temp_data.txt")
    sig_file = os.path.join(DEBUG_DIR, "sig_com.txt")

    with open(temp_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    # Try to sign
    cmd = f'"{certmgr}" -sign -thumbprint "{CERT_THUMBPRINT}" -in "{temp_file}" -out "{sig_file}" -base64'
    print(f"Trying: {cmd}")

    result = subprocess.run(cmd, shell=True, capture_output=True, timeout=60, encoding='cp866')

    if result.returncode == 0:
        with open(sig_file, 'r', encoding='utf-8') as f:
            signature = f.read().strip()
        signature = ''.join(c for c in signature if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
        return signature
    else:
        print(f"certmgr error: {result.returncode}")
        if result.stderr:
            print(f"Error: {result.stderr.strip()}")
        return None

def main():
    print("Starting script (COM version)...")
    time.sleep(1)

    print("=" * 80)
    print("CHESTNY ZNAK API AUTHENTICATION (COM)")
    print("=" * 80)

    os.makedirs(DEBUG_DIR, exist_ok=True)

    # STEP 1: Get data from API
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

    # Save data
    data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")
    with open(data_file, 'w', encoding='utf-8', newline='') as f:
        f.write(data_to_sign)

    with open(os.path.join(DEBUG_DIR, "uuid.txt"), 'w') as f:
        f.write(uuid)

    print(f"OK Data saved to {DEBUG_DIR}")

    # STEP 2: Sign data (try COM first, then certmgr)
    print("\n[STEP 2] Signing data...")

    # Try COM first
    print("Trying CryptoPro COM object...")
    signature = sign_with_com(data_to_sign)

    if not signature:
        print("COM failed, trying certmgr.exe...")
        signature = sign_with_certmgr(data_to_sign)

    if not signature:
        print("\nERROR: Could not sign data")
        print("Make sure:")
        print("1. Rutoken is connected")
        print("2. CryptoPro CSP is installed correctly")
        print("3. Running as administrator")
        input("Press Enter to exit...")
        return

    print(f"OK Signature created: {len(signature)} chars")

    # Save signature
    sig_file = os.path.join(DEBUG_DIR, "sig_com.txt")
    with open(sig_file, 'w', encoding='utf-8') as f:
        f.write(signature)

    # STEP 3: Send to API
    print("\n[STEP 3] Sending authentication request...")

    payload = {
        "data": signature,
        "unitedToken": True
    }

    # Save request
    with open(os.path.join(DEBUG_DIR, "request.json"), 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    status, response = make_request(
        f"{CHZ_BASE_URL}/auth/simpleSignIn",
        method="POST",
        data=payload
    )

    print(f"Status: {status}")

    if status == 200:
        print(f"\nSUCCESS! Token received:")
        print(f"   {response}")

        # Save token
        with open(os.path.join(DEBUG_DIR, "token.json"), 'w', encoding='utf-8') as f:
            json.dump({"token": response}, f, indent=2)
        print(f"\nOK Token saved to: " + DEBUG_DIR + "\\token.json")
    else:
        error_msg = response.get('error_message', str(response))
        print(f"\nERROR: {error_msg}")

        # Save error
        with open(os.path.join(DEBUG_DIR, "error.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "payload": payload,
                "response": response
            }, f, indent=2, ensure_ascii=False)
        print(f"OK Error details: " + DEBUG_DIR + "\\error.json")

    print("\n" + "=" * 80)
    input("Press Enter to exit...")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        print(f"Type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 80)
        input("Press Enter to exit...")
