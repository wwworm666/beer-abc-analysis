# -*- coding: utf-8 -*-
"""Test cryptcp.win32 signing"""

import subprocess
import os

DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
CRYPTCP = r"C:\Program Files\Crypto Pro\CSP\cryptcp.win32"
CERT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"

# Load data to sign
data_file = os.path.join(DEBUG_DIR, "data_to_sign.txt")
with open(data_file, 'r', encoding='utf-8') as f:
    data = f.read().strip()

print(f"Data to sign: {data}")
print(f"Cert: {CERT}")
print()

# Try different command formats
commands = [
    # Format 1: -sign -cert
    f'"{CRYPTCP}" -sign -cert "{CERT}" -in "{data_file}" -out "{DEBUG_DIR}\\sig1.txt" -base64',

    # Format 2: -sign -thumbprint
    f'"{CRYPTCP}" -sign -thumbprint "{CERT}" -in "{data_file}" -out "{DEBUG_DIR}\\sig2.txt" -base64',

    # Format 3: -sign -container
    f'"{CRYPTCP}" -sign -container "{CERT}" -in "{data_file}" -out "{DEBUG_DIR}\\sig3.txt" -base64',

    # Format 4: just -sign with file
    f'"{CRYPTCP}" -sign "{data_file}" -out "{DEBUG_DIR}\\sig4.txt" -base64',

    # Format 5: -f -sign
    f'"{CRYPTCP}" -f -sign -cert "{CERT}" "{data_file}" "{DEBUG_DIR}\\sig5.txt" -base64',
]

for i, cmd in enumerate(commands, 1):
    print(f"\n=== TEST {i} ===")
    print(f"Command: {cmd}")

    result = subprocess.run(cmd, shell=True, capture_output=True, timeout=30, encoding='cp866')

    print(f"Return code: {result.returncode}")
    if result.returncode == 0:
        print("SUCCESS!")
        if os.path.exists(f"{DEBUG_DIR}\\sig{i}.txt"):
            with open(f"{DEBUG_DIR}\\sig{i}.txt", 'r') as f:
                sig = f.read().strip()
            print(f"Signature length: {len(sig)}")
            print(f"First 50 chars: {sig[:50]}")
        break
    else:
        if result.stdout:
            print(f"Output: {result.stdout[:200]}")
        if result.stderr:
            print(f"Error: {result.stderr[:200]}")

print("\n" + "=" * 80)
input("Press Enter to exit...")
