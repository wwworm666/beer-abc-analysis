# -*- coding: utf-8 -*-
"""Find signing tool in CryptoPro folders"""

import os
import subprocess

paths = [
    r"C:\Program Files\Crypto Pro\CSP",
    r"C:\Program Files (x86)\Crypto Pro\CSP",
]

print("=" * 80)
print("CRYPTOPRO EXE FILES")
print("=" * 80)

for path in paths:
    if os.path.exists(path):
        print(f"\n{path}:")
        files = os.listdir(path)
        exe_files = sorted([f for f in files if f.endswith('.exe')])
        for exe in exe_files:
            full_path = os.path.join(path, exe)
            print(f"  {exe}")

print("\n" + "=" * 80)
print("TESTING SIGNING COMMANDS")
print("=" * 80)

data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug", "data_to_sign.txt")
cert = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")

# Try different tools and commands
tests = [
    # csptest.exe variations
    (r"C:\Program Files (x86)\Crypto Pro\CSP\csptest.exe", "-sfsign -sign -my \"{0}\" -in \"{1}\" -out \"{2}\" -base64"),
    (r"C:\Program Files (x86)\Crypto Pro\CSP\csptest.exe", "-sign -my \"{0}\" -in \"{1}\" -out \"{2}\" -base64"),

    # certmgr.exe variations
    (r"C:\Program Files (x86)\Crypto Pro\CSP\certmgr.exe", "-sign -thumb \"{0}\" -in \"{1}\" -out \"{2}\" -base64"),
    (r"C:\Program Files (x86)\Crypto Pro\CSP\certmgr.exe", "-sign -thumbprint \"{0}\" -in \"{1}\" -out \"{2}\" -base64"),
    (r"C:\Program Files (x86)\Crypto Pro\CSP\certmgr.exe", "-sign -cert \"{0}\" -in \"{1}\" -out \"{2}\" -base64"),

    # Try 64-bit versions
    (r"C:\Program Files\Crypto Pro\CSP\csptest.exe", "-sfsign -sign -my \"{0}\" -in \"{1}\" -out \"{2}\" -base64"),
    (r"C:\Program Files\Crypto Pro\CSP\certmgr.exe", "-sign -thumb \"{0}\" -in \"{1}\" -out \"{2}\" -base64"),
]

for tool_path, cmd_format in tests:
    if not os.path.exists(tool_path):
        print(f"\n[SKIP] {tool_path} - not found")
        continue

    cmd = cmd_format.format(cert, data_file, debug_dir + "\\sig_test.txt")
    tool_name = os.path.basename(tool_path)

    print(f"\n[TEST] {tool_name}: {cmd_format.split(' -')[0]}")
    print(f"  Full: {cmd[:100]}...")

    result = subprocess.run(cmd, shell=True, capture_output=True, timeout=30, encoding='cp866')

    if result.returncode == 0:
        print(f"  SUCCESS! Return code: {result.returncode}")
        sig_file = debug_dir + "\\sig_test.txt"
        if os.path.exists(sig_file):
            with open(sig_file, 'r', encoding='utf-8') as f:
                sig = f.read().strip()
            sig = ''.join(c for c in sig if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
            print(f"  Signature: {len(sig)} chars")
        break
    else:
        error = result.stdout[:100] if result.stdout else result.stderr[:100] if result.stderr else "unknown"
        print(f"  FAILED: {error.strip()}")

print("\n" + "=" * 80)
input("Press Enter to exit...")
