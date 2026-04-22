"""Удалённое выполнение команд на бар-ПК через Tailscale + SSH.

Использует paramiko для подключения к бар-ПК (100.98.149.108) по Tailscale IP.

Команды:
    python remote_exec.py status                    - проверить связь
    python remote_exec.py cmd "hostname"            - выполнить команду
    python remote_exec.py push chz.py chz_test/     - отправить файл/папку
    python remote_exec.py pull chz_test/data/ data/ - забрать файлы
    python remote_exec.py run stock                 - обновить токен, запустить chz.py stock, скачать chz_stock.json
    python remote_exec.py run report 2026-03-01     - выполнить chz.py report
"""

import os
import sys
import paramiko
import subprocess
from pathlib import Path

REMOTE_HOST = "100.98.149.108"
REMOTE_USER = os.environ.get("REMOTE_USER", "Администратор")
REMOTE_PASS = os.environ.get("REMOTE_PASS")
REPO_DIR = Path(__file__).parent.resolve()

# Full path to Python on bar PC (confirmed: C:\Program Files\Python312\python.exe)
REMOTE_PYTHON = r"C:\Program Files\Python312\python.exe"

# chz_test directory on bar PC (repo is not present, scripts live at C:\chz_test)
REMOTE_CHZ_DIR = r"C:\chz_test"


def connect(timeout=15):
    if not REMOTE_PASS:
        raise EnvironmentError("REMOTE_PASS environment variable is not set")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(REMOTE_HOST, username=REMOTE_USER, password=REMOTE_PASS,
                   timeout=timeout, look_for_keys=False, allow_agent=False)
    return client


def run_cmd(rem_cmd, verbose=True, timeout=None):
    import socket as _socket
    client = connect()
    try:
        stdin, stdout, stderr = client.exec_command(rem_cmd, get_pty=False, timeout=timeout)
        try:
            raw_out = stdout.read()
            raw_err = stderr.read()
        except _socket.timeout:
            raise TimeoutError(f"Команда превысила таймаут {timeout}с: {rem_cmd!r}")
        try:
            out = raw_out.decode("utf-8")
        except UnicodeDecodeError:
            out = raw_out.decode("cp866", errors="replace")
        try:
            err = raw_err.decode("utf-8")
        except UnicodeDecodeError:
            err = raw_err.decode("cp866", errors="replace")
        if verbose:
            if out.strip():
                sys.stdout.buffer.write(out.strip().encode("utf-8") + b"\n")
                sys.stdout.buffer.flush()
            if err.strip():
                sys.stdout.buffer.write(("STDERR: " + err.strip()).encode("utf-8") + b"\n")
                sys.stdout.buffer.flush()
        return out, err
    finally:
        client.close()


def push(local_path, remote_dir):
    client = connect()
    try:
        sftp = client.open_sftp()
        try:
            local = Path(local_path)
            if local.is_dir():
                for f in local.iterdir():
                    if f.is_file():
                        remote_file = f"{remote_dir}/{f.name}"
                        sftp.put(str(f), remote_file)
                        print(f"  push: {f.name} -> {remote_dir}/")
            elif local.is_file():
                remote_file = f"{remote_dir}/{local.name}"
                sftp.put(str(local), remote_file)
                print(f"  push: {local.name} -> {remote_dir}/")
            else:
                print(f"FAIL: {local_path} не найден")
                return
            print(f"  done: {len([f for f in Path(local_path).iterdir()]) if Path(local_path).is_dir() else 1} file(s) sent")
        finally:
            sftp.close()
    finally:
        client.close()


def pull(remote_path, local_dir):
    client = connect()
    try:
        sftp = client.open_sftp()
        try:
            local = Path(local_dir)
            local.mkdir(parents=True, exist_ok=True)

            fname = Path(remote_path.replace("\\", "/")).name
            local_file = local / fname

            sftp.get(remote_path, str(local_file))
            print(f"  pull: {remote_path} -> {local_file}")
        finally:
            sftp.close()
    finally:
        client.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    action = sys.argv[1]

    if action == "status":
        try:
            out, _ = run_cmd("hostname && whoami", verbose=False)
            lines = out.strip().split("\n")
            print(f"HOST: {lines[0].strip()}")
            if len(lines) > 1:
                print(f"USER: {lines[1].strip()}")
            print("STATUS: ONLINE")
        except Exception as e:
            print(f"STATUS: OFFLINE (Ошибка: {e})")

    elif action == "cmd":
        remote_command = " ".join(sys.argv[2:])
        run_cmd(remote_command)

    elif action == "push":
        if len(sys.argv) < 4:
            print("Использование: remote_exec.py push <local_path> <remote_dir>")
            return
        push(sys.argv[2], sys.argv[3])

    elif action == "pull":
        if len(sys.argv) < 4:
            print("Использование: remote_exec.py pull <remote_path> <local_dir>")
            return
        pull(sys.argv[2], sys.argv[3])

    elif action == "run":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "stock":
            # Special: refresh token, run stock, pull result
            print("Обновление токена...")
            token_cmd = f'cd /d {REMOTE_CHZ_DIR} && "{REMOTE_PYTHON}" chz.py token'
            run_cmd(token_cmd)
            print("\nЗапуск сбора остатков (таймаут 600с)...")
            stock_cmd = f'cd /d {REMOTE_CHZ_DIR} && "{REMOTE_PYTHON}" chz.py stock'
            run_cmd(stock_cmd, timeout=600)
            print("\nСкачивание результата...")
            remote_json = REMOTE_CHZ_DIR + r"\debug\chz_stock.json"
            pull(remote_json, str(REPO_DIR / "chz_test" / "debug"))
        else:
            # Запустить chz.py на бар-ПК из C:\chz_test
            args = " ".join(sys.argv[2:])
            remote_cmd = (
                f'cd /d {REMOTE_CHZ_DIR} && '
                f'"{REMOTE_PYTHON}" chz.py {args}'
            )
            print(f"Запуск: chz.py {args}\n")
            run_cmd(remote_cmd)

    else:
        print(f"Неизвестная команда: {action}")


if __name__ == "__main__":
    main()
