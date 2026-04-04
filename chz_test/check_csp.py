# -*- coding: utf-8 -*-
"""Check CryptoPro CSP installation"""

import os
import subprocess
import platform

print("=" * 80)
print("CRYPTOPRO CSP CHECK")
print("=" * 80)

print(f"\nOS: {platform.version()}")
print(f"Architecture: {platform.machine()}")
print(f"Processor: {platform.processor()}")

# Check common paths
paths_to_check = [
    r"C:\Program Files\Crypto Pro\CSP",
    r"C:\Program Files (x86)\Crypto Pro\CSP",
]

print("\n" + "=" * 80)
print("CHECKING PATHS")
print("=" * 80)

for path in paths_to_check:
    if os.path.exists(path):
        print(f"\n[OK] {path}")
        files = os.listdir(path)
        exe_files = [f for f in files if f.endswith('.exe')]
        print(f"  EXE files: {len(exe_files)}")
        for exe in sorted(exe_files):
            full_path = os.path.join(path, exe)
            print(f"    - {exe}")
    else:
        print(f"\n[NOT FOUND] {path}")

# Try to run csptest -ver
print("\n" + "=" * 80)
print("TRYING csptest.exe -ver")
print("=" * 80)

csptest_paths = [
    r"C:\Program Files\Crypto Pro\CSP\csptest.exe",
    r"C:\Program Files (x86)\Crypto Pro\CSP\csptest.exe",
]

for csptest in csptest_paths:
    if os.path.exists(csptest):
        print(f"\nTrying: {csptest}")
        try:
            result = subprocess.run(
                f'"{csptest}" -ver',
                shell=True,
                capture_output=True,
                timeout=10,
                encoding='cp866'
            )
            print(f"  Return code: {result.returncode}")
            if result.stdout:
                print(f"  Output: {result.stdout[:200]}")
            if result.stderr:
                print(f"  Error: {result.stderr[:200]}")
        except Exception as e:
            print(f"  Exception: {e}")
    else:
        print(f"\n[NOT FOUND] {csptest}")

print("\n" + "=" * 80)
input("Press Enter to exit...")
