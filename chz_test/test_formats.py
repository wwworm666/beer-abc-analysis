# -*- coding: utf-8 -*-
"""
Test ALL auth formats for Chestny Znak API
Uses READY signature from file
"""

import urllib.request
import urllib.error
import json
import ssl
import os
import sys

# Fix Windows console encoding
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
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

def load_text(filename):
    path = os.path.join(DEBUG_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()

def load_signature(filename):
    path = os.path.join(DEBUG_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        sig = f.read().strip()
    return ''.join(c for c in sig if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

def test_format(name, payload):
    status, resp = make_request(f"{CHZ_BASE_URL}/auth/simpleSignIn", "POST", payload)
    ok = status == 200
    mark = "[OK]" if ok else "[FAIL]"
    print(f"{mark} {name}: status={status}")
    if ok:
        print(f"    Token: {resp}")
    else:
        err = resp.get('error_message', str(resp))[:100] if isinstance(resp, dict) else str(resp)[:100]
        print(f"    Error: {err}")
    return status

print("-" * 80)
print("TEST ALL AUTH FORMATS")
print("-" * 80)

uuid = load_text("uuid.txt")
data_to_sign = load_text("data_to_sign.txt")
signature = load_signature("sig_attached.txt")

if not uuid or not data_to_sign or not signature:
    print("[ERROR] Files not found in debug/")
    print("Run chz_auth.py first")
    input("Enter to exit...")
    exit(1)

print(f"UUID: {uuid}")
print(f"DATA: {data_to_sign}")
print(f"Signature: {len(signature)} chars")
print()

results = []

# Test 1: v3 (data + unitedToken=true)
print("-" * 40)
print("Test 1: v3 (data + unitedToken=true)")
results.append(("v3: data+unitedToken=true", test_format("v3", {"data": signature, "unitedToken": True})))

# Test 2: v3 (data + unitedToken=false)
print("-" * 40)
print("Test 2: v3 (data + unitedToken=false)")
results.append(("v3: data+unitedToken=false", test_format("v3", {"data": signature, "unitedToken": False})))

# Test 3: v2 (uuid + data)
print("-" * 40)
print("Test 3: v2 (uuid + data)")
results.append(("v2: uuid+data", test_format("v2", {"uuid": uuid, "data": signature})))

# Test 4: v2 (uuid + data + inn)
print("-" * 40)
print("Test 4: v2 (uuid + data + inn)")
results.append(("v2: uuid+data+inn", test_format("v2", {"uuid": uuid, "data": signature, "inn": "7801630649"})))

# Test 5: v3 (uuid + data + unitedToken=true)
print("-" * 40)
print("Test 5: v3 (uuid + data + unitedToken=true)")
results.append(("v3: uuid+data+unitedToken=true", test_format("v3", {"uuid": uuid, "data": signature, "unitedToken": True})))

# Summary
print()
print("=" * 80)
print("SUMMARY")
print("=" * 80)
for name, status in results:
    mark = "[OK]" if status == 200 else "[FAIL]"
    print(f"{mark} {name}: {status}")

success = [s for s in results if s[1] == 200]
if success:
    print()
    print(f"SUCCESS: {success[0][0]}")
else:
    print()
    print("ALL TESTS FAILED")
    print("Check error.json for details")

print("=" * 80)
input("Enter to exit...")
