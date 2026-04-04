# -*- coding: utf-8 -*-
"""
Check what we're actually signing
"""

import os

DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")

# Check data_to_sign.txt
data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")
with open(data_file, 'rb') as f:
    raw_data = f.read()

with open(data_file, 'r', encoding='utf-8') as f:
    text_data = f.read()

print("=" * 80)
print("CHECKING data_to_sign.txt")
print("=" * 80)
print(f"Raw bytes: {raw_data}")
print(f"Raw hex: {raw_data.hex()}")
print(f"Text: '{text_data}'")
print(f"Length: {len(text_data)} chars, {len(raw_data)} bytes")
print()

# Check for BOM
if raw_data.startswith(b'\xef\xbb\xbf'):
    print("[WARNING] File has UTF-8 BOM!")
else:
    print("[OK] No UTF-8 BOM")

# Check for newline
if raw_data.endswith(b'\n') or raw_data.endswith(b'\r'):
    print("[WARNING] File ends with newline!")
else:
    print("[OK] No trailing newline")

print()
print("=" * 80)
print("COMPARING WITH API RESPONSE")
print("=" * 80)

# What the API sent
import urllib.request, urllib.error, json, ssl

CHZ_BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))

req = urllib.request.Request(f"{CHZ_BASE_URL}/auth/key")
response = opener.open(req, timeout=30)
api_data = json.loads(response.read().decode('utf-8'))

api_uuid = api_data.get('uuid')
api_data_str = api_data.get('data')

print(f"API UUID: {api_uuid}")
print(f"API DATA: '{api_data_str}' ({len(api_data_str)} chars)")
print()

if api_data_str == text_data:
    print("[OK] Data matches API response")
else:
    print(f"[MISMATCH] File contains '{text_data}' but API returned '{api_data_str}'")

print("=" * 80)
