"""Удалённое выполнение команд на бар-ПК через Tailscale + SSH.

Использует paramiko для подключения к бар-ПК (100.98.149.108) по Tailscale IP.

Команды:
    python remote_exec.py status                    - проверить связь
    python remote_exec.py cmd "hostname"            - выполнить команду
    python remote_exec.py push chz.py chz_test/     - отправить файл/папку
    python remote_exec.py pull chz_test/data/ data/ - забрать файлы
    python remote_exec.py run report 2026-03-01     - выполнить chz.py report
"""

import sys
import paramiko
import subprocess
from pathlib import Path

REMOTE_HOST = "100.98.149.108"
REMOTE_USER = "Администратор"
REMOTE_PASS = "Krem2026"
REPO_DIR = Path(__file__).parent.resolve()

# Full path to Python on bar PC (python.exe stub in WindowsApps doesn't work)
REMOTE_PYTHON = r"C:\Users\1\AppData\Local\Python\bin\python.exe"


def connect(timeout=15):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(REMOTE_HOST, username=REMOTE_USER, password=REMOTE_PASS,
                   timeout=timeout, look_for_keys=True)
    return client


def run_cmd(rem_cmd, verbose=True):
    client = connect()
    stdin, stdout, stderr = client.exec_command(rem_cmd, get_pty=False)
    raw_out = stdout.read()
    raw_err = stderr.read()
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
            print(out.strip())
        if err.strip():
            print(f"STDERR: {err.strip()}")
    client.close()
    return out, err


def push(local_path, remote_dir):
    client = connect()
    sftp = client.open_sftp()

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
        client.close()
        return

    sftp.close()
    client.close()
    print(f"  done: {len([f for f in Path(local_path).iterdir()]) if Path(local_path).is_dir() else 1} file(s) sent")


def pull(remote_path, local_dir):
    client = connect()
    sftp = client.open_sftp()

    local = Path(local_dir)
    local.mkdir(parents=True, exist_ok=True)

    fname = Path(remote_path.replace("\\", "/")).name
    local_file = local / fname

    sftp.get(remote_path, str(local_file))
    print(f"  pull: {remote_path} -> {local_file}")

    sftp.close()
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
        # Запустить chz.py report на бар-ПК
        args = " ".join(sys.argv[2:])
        remote_cmd = (
            'cd C:\\Users\\1\\Documents\\GitHub\\beer-abc-analysis && '
            f'"{REMOTE_PYTHON}" chz_test\\chz.py {args}'
        )
        print(f"Запуск: chz.py {args}\n")
        run_cmd(remote_cmd)

    else:
        print(f"Неизвестная команда: {action}")


if __name__ == "__main__":
    main()
