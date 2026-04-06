"""Push обновлённых файлов на бар-ПК через git.

Этот скрипт на сервере (100.122.143.1) копирует локальные файлы из chz_test/
в git репо, коммитит и пушит. После этого на бар-ПК достаточно `git pull`.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent

def run(cmd, cwd=None):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd or REPO)
    if r.stderr.strip():
        print(f"  stderr: {r.stderr.strip()}")
    return r.returncode, r.stdout.strip()

def main():
    files_to_sync = [
        "chz_test/chz.py",
        "chz_test/README.md",
        "chz_test/requirements.txt",
    ]

    # Проверить что файлы существуют
    for f in files_to_sync:
        if not (REPO / f).exists():
            print(f"FAIL: {f} не найден")
            sys.exit(1)

    print("=== Push файлов на бар-ПК ===\n")
    print("Файлы:")
    for f in files_to_sync:
        print(f"  - {f}")

    # Git add
    for f in files_to_sync:
        rc, out = run(f'git add "{f}"')
        if rc != 0:
            print(f"  FAIL: git add {f}: {out}")
            sys.exit(1)

    # Git commit
    rc, out = run('git commit -m "chz: push updates to bar-pc"', allow_fail=True)
    # allow_fail — может не быть изменений
    if rc != 0 and "nothing to commit" in out.lower():
        print("\nНет изменений для коммита (всё уже актуально)")
    else:
        print(f"  git commit: {out[:120]}")

    # Git push
    print("\nPush...")
    rc, out = run("git push")
    if rc != 0:
        print(f"  FAIL: {out}")
        sys.exit(1)
    print(f"  done: {out[:120]}")

    print("\nГотово! Теперь на бар-ПК:")
    print("  cd C:\\Users\\1\\Documents\\GitHub\\beer-abc-analysis")
    print("  git pull")

def run(cmd, cwd=None, allow_fail=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd or REPO)
    out = (r.stdout + r.stderr).strip()
    if out and not allow_fail:
        print(f"  {out[:200]}")
    return r.returncode, out

if __name__ == "__main__":
    main()
