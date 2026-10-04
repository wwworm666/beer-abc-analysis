"""Удалённое выполнение команд на бар-ПК через Tailscale + SSH.

Использует paramiko для подключения к бар-ПК (100.98.149.108) по Tailscale IP.

Команды:
    python remote_exec.py status                    - проверить связь
    python remote_exec.py cmd "hostname"            - выполнить команду
    python remote_exec.py push chz.py chz_test/     - отправить файл/папку
    python remote_exec.py pull chz_test/data/ data/ - забрать файлы
    python remote_exec.py run stock                 - обновить токен, запустить chz.py stock, скачать chz_stock.json
    python remote_exec.py run report 2026-03-01     - выполнить chz.py report

Перед run stock, csv-auto и search-stock chz.py на бар-ПК обновляется из репозитория, если
здесь версия новее (sync_chz_script; выключатель — CHZ_AUTO_UPDATE=0 в окружении).
"""

import io
import os
import re
import sys
import json
import time
import socket
import paramiko

from pathlib import Path

REMOTE_HOST = os.environ.get("REMOTE_HOST", "100.98.149.108")
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
    client = connect()
    try:
        stdin, stdout, stderr = client.exec_command(rem_cmd, get_pty=False, timeout=timeout)
        try:
            raw_out = stdout.read()
            raw_err = stderr.read()
        except socket.timeout:
            raise TimeoutError(f"Команда превысила таймаут {timeout}с: {rem_cmd!r}")
        try:
            out = raw_out.decode("utf-8")
        except UnicodeDecodeError:
            out = raw_out.decode("cp866", errors="replace")
        try:
            err = raw_err.decode("utf-8")
        except UnicodeDecodeError:
            err = raw_err.decode("cp866", errors="replace")
        try:
            exit_code = stdout.channel.recv_exit_status()
        except socket.timeout:
            raise TimeoutError(f"Команда превысила таймаут {timeout}с (ожидание завершения): {rem_cmd!r}")
        if verbose:
            if out.strip():
                sys.stdout.buffer.write(out.strip().encode("utf-8") + b"\n")
                sys.stdout.buffer.flush()
            if err.strip():
                sys.stdout.buffer.write(("STDERR: " + err.strip()).encode("utf-8") + b"\n")
                sys.stdout.buffer.flush()
        if exit_code != 0:
            raise RuntimeError(
                f"Remote command failed (exit {exit_code}): {rem_cmd!r}"
                + (f"\nSTDERR: {err.strip()}" if err.strip() else "")
            )
        return out, err
    finally:
        client.close()


def push(local_path, remote_dir):
    client = connect()
    try:
        sftp = client.open_sftp()
        try:
            local = Path(local_path)
            sent = 0
            if local.is_dir():
                for f in local.iterdir():
                    if f.is_file():
                        remote_file = f"{remote_dir}/{f.name}"
                        sftp.put(str(f), remote_file)
                        print(f"  push: {f.name} -> {remote_dir}/")
                        sent += 1
            elif local.is_file():
                remote_file = f"{remote_dir}/{local.name}"
                sftp.put(str(local), remote_file)
                print(f"  push: {local.name} -> {remote_dir}/")
                sent = 1
            else:
                print(f"FAIL: {local_path} не найден")
                return
            print(f"  done: {sent} file(s) sent")
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
            tmp_file = local / (fname + ".tmp")

            try:
                sftp.get(remote_path, str(tmp_file))
                tmp_file.replace(local_file)
            except Exception:
                if tmp_file.exists():
                    tmp_file.unlink()
                raise
            print(f"  pull: {remote_path} -> {local_file}")
        finally:
            sftp.close()
    finally:
        client.close()


REMOTE_STOCK_JSON = REMOTE_CHZ_DIR + r"\debug\chz_stock.json"
TOKEN_FAIL_TEXT = (
    "Токен ЧЗ на бар-ПК не получен (подпись КриптоПро не прошла: тот ли Рутокен "
    "вставлен, тот ли CERT_THUMBPRINT в chz.py). Остатки не собираются, старый "
    "chz_stock.json не скачивается.")


def remote_mtime(remote_path):
    """Время изменения файла на бар-ПК (sftp stat) или None, если файла нет."""
    client = connect()
    try:
        sftp = client.open_sftp()
        try:
            return sftp.stat(remote_path).st_mtime
        except OSError:
            return None
        finally:
            sftp.close()
    finally:
        client.close()


def pull_stock_if_rewritten(before, command):
    """Скачать chz_stock.json, только если команда его перезаписала (время файла сменилось).

    Иначе — RuntimeError: старый файл со свежим временем выглядел бы новыми данными
    (урок «тихий сбой подписи», docs/lessons.md). Ревью 2026-10-04: chz.py stock и
    csv-auto при пустом результате ничего не пишут и маркера [WARN] не печатают.
    """
    after = remote_mtime(REMOTE_STOCK_JSON)
    if after is None or after == before:
        raise RuntimeError(
            f"chz.py {command} не обновил chz_stock.json на бар-ПК — старый файл не скачивается.")
    print("\nСкачивание chz_stock.json...")
    pull(REMOTE_STOCK_JSON, str(REPO_DIR / "chz_test" / "debug"))


def refresh_token_or_fail():
    """Обновить токен ЧЗ на бар-ПК; не получилось — RuntimeError (код выхода 1).

    chz.py token до 2026-10-04 при сбое подписи печатал «[ERR] ...» и выходил с кодом 0:
    ночное обновление шло дальше, сбор остатков без токена ничего не писал, а старый
    chz_stock.json скачивался заново — время файла обновлялось, и сроки годности
    выглядели свежими, хотя данные ЧЗ стояли с августа 2026 (КЭП перевыпустили на новый
    Рутокен, отпечаток в chz.py остался старым). «[ERR]» — ASCII: кириллица вывода
    бар-ПК по SSH приходит кракозябрами, маркер — нет. С 2026-10-04 chz.py token при сбое
    выходит с кодом 1 — run_cmd бросает общее «Remote command failed», его заменяет
    понятный текст (последняя строка журнала, её и показывает страница).
    """
    print("Обновление токена...")
    token_cmd = f'cd /d {REMOTE_CHZ_DIR} && "{REMOTE_PYTHON}" chz.py token'
    try:
        out, _err = run_cmd(token_cmd, timeout=120)
    except RuntimeError as exc:
        raise RuntimeError(TOKEN_FAIL_TEXT) from exc
    if "[ERR]" in (out or ""):
        raise RuntimeError(TOKEN_FAIL_TEXT)


# ----- chz.py на бар-ПК: обновление с сервера ------------------------------------------
#
# Решение владельца 2026-10-04: новый chz.py на бар-ПК кладёт сервер — тем же путём, которым
# ходит туда каждую ночь (Tailscale + SSH), а не человек командой push. Версия — строка
# CHZ_VERSION в chz.py (дата ISO, сравнивается строкой, как в chz_test/kep_setup.py; второй
# выпуск за день — «2026-10-04-2»). Строку CERT_THUMBPRINT на бар-ПК пишет kep_setup.bat
# под вставленный Рутокен — она переносится в новый файл: иначе после следующего
# перевыпуска КЭП обновление вернуло бы отпечаток из репозитория, и ночной вход в ЧЗ
# сломался бы.
CHZ_VERSION_RE = re.compile(r'^CHZ_VERSION\s*=\s*["\']([0-9-]+)["\']', re.M)
THUMB_LINE_RE = re.compile(r'^CERT_THUMBPRINT\s*=\s*"[^"\n]*"', re.M)
REMOTE_CHZ_PY = REMOTE_CHZ_DIR + r"\chz.py"
# CHZ_AUTO_UPDATE=0 в окружении сервера — chz.py на бар-ПК не трогать (только вручную push).
AUTO_UPDATE_ENV = "CHZ_AUTO_UPDATE"


def chz_version(text) -> str:
    """CHZ_VERSION из текста chz.py; '' — строки нет (файлы до 2026-10-04)."""
    match = CHZ_VERSION_RE.search(text or "")
    return match.group(1) if match else ""


def with_remote_thumbprint(local_text: str, remote_text: str) -> str:
    """Текст chz.py из репозитория со строкой CERT_THUMBPRINT из файла на бар-ПК.

    На бар-ПК строки нет (файла нет, файл чужой) — текст из репозитория как есть.
    """
    found = THUMB_LINE_RE.search(remote_text or "")
    if not found:
        return local_text
    line = found.group(0)
    new_text, count = THUMB_LINE_RE.subn(lambda _match: line, local_text)
    return new_text if count == 1 else local_text


def _sftp_read(sftp, path):
    """Байты файла на бар-ПК; None — файла нет. Другие ошибки чтения — наружу."""
    try:
        with sftp.open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _quiet_remove(sftp, path):
    try:
        sftp.remove(path)
    except IOError:
        pass


def _replace_remote_chz(sftp, new_bytes: bytes, old_bytes) -> str:
    """Заменить chz.py на бар-ПК: новый — через chz.py.new, прежний — в chz_backup_<время>.py.

    SFTP на Windows не переименовывает поверх существующего файла, поэтому прежний сначала
    уходит в копию. Сбой на любом шаге или файл не совпал с отправленным — прежний
    возвращается на место (переименованием, а не вышло — записью старых байтов), ошибка —
    наружу. old_bytes=None — на бар-ПК файла не было. Возврат: имя копии прежнего или ''.
    """
    temp_path = REMOTE_CHZ_PY + ".new"
    backup_name = "chz_backup_" + time.strftime("%Y%m%d_%H%M%S") + ".py"
    backup_path = REMOTE_CHZ_DIR + "\\" + backup_name
    moved = False
    try:
        sftp.putfo(io.BytesIO(new_bytes), temp_path)
        if old_bytes is not None:
            sftp.rename(REMOTE_CHZ_PY, backup_path)
            moved = True
        sftp.rename(temp_path, REMOTE_CHZ_PY)
        if _sftp_read(sftp, REMOTE_CHZ_PY) != new_bytes:
            raise IOError("chz.py на бар-ПК не совпал с отправленным")
    except Exception:
        if moved:
            try:
                _quiet_remove(sftp, REMOTE_CHZ_PY)
                sftp.rename(backup_path, REMOTE_CHZ_PY)
            except Exception:
                sftp.putfo(io.BytesIO(old_bytes), REMOTE_CHZ_PY)
        _quiet_remove(sftp, temp_path)
        raise
    return backup_name if moved else ""


def sync_chz_script() -> str:
    """Положить на бар-ПК chz.py из репозитория, если здесь CHZ_VERSION новее.

    На бар-ПК версия та же или новее — файл не трогается (как kep_setup: старое не
    откатывает новое). Иначе новый текст (с отпечатком КЭП с бар-ПК) заменяет chz.py, а
    прежний остаётся рядом копией chz_backup_<время>.py. Любая ошибка — строка [WARN] в
    журнале, а обновление ЧЗ идёт на прежнем chz.py: свежий файл полезен, но не стоит ночи
    без данных. Возврат: 'off' | 'no-local' | 'current' | 'updated' | 'failed'.
    """
    if os.environ.get(AUTO_UPDATE_ENV, "1").strip() == "0":
        print(f"chz.py на бар-ПК: автообновление выключено ({AUTO_UPDATE_ENV}=0)")
        return "off"
    try:
        local_text = (REPO_DIR / "chz_test" / "chz.py").read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"[WARN] chz.py: файл репозитория не прочитан ({e}) — бар-ПК не обновляется")
        return "no-local"
    local_version = chz_version(local_text)
    if not local_version:
        print("[WARN] chz.py: в репозитории нет CHZ_VERSION — бар-ПК не обновляется")
        return "no-local"
    try:
        client = connect()
    except Exception as e:
        print(f"[WARN] chz.py на бар-ПК не проверен ({e}) — работает прежний")
        return "failed"
    try:
        sftp = client.open_sftp()
        try:
            remote_bytes = _sftp_read(sftp, REMOTE_CHZ_PY)
            remote_text = remote_bytes.decode("utf-8", errors="replace") if remote_bytes else ""
            remote_version = chz_version(remote_text)
            if remote_bytes is not None and remote_version >= local_version:
                print(f"chz.py на бар-ПК: версия {remote_version} — обновлять не нужно")
                return "current"
            new_bytes = with_remote_thumbprint(local_text, remote_text).encode("utf-8")
            backup = _replace_remote_chz(sftp, new_bytes, remote_bytes)
        finally:
            sftp.close()
    except Exception as e:
        print(f"[WARN] chz.py на бар-ПК не обновлён ({e}) — работает прежний")
        return "failed"
    finally:
        client.close()
    thumb = "отпечаток КЭП с бар-ПК" if THUMB_LINE_RE.search(remote_text) else "отпечаток КЭП из репозитория"
    kept = f"; прежний — {backup}" if backup else ""
    print(f"chz.py на бар-ПК обновлён: {remote_version or 'без версии'} -> {local_version} ({thumb}{kept})")
    return "updated"


def _stock_not_written(out) -> bool:
    """chz.py search-stock не перезаписал chz_stock.json (пустой результат).

    Строка «[WARN] пустой результат — chz_stock.json НЕ перезаписан»: ищем ASCII-части,
    кириллица по SSH приходит кракозябрами.
    """
    return any("[WARN]" in line and "chz_stock.json" in line
               for line in str(out or "").splitlines())


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
        if subcmd in ("stock", "csv-auto", "search-stock"):
            sync_chz_script()
        if subcmd == "stock":
            # Special: refresh token, run stock, pull result
            refresh_token_or_fail()
            before = remote_mtime(REMOTE_STOCK_JSON)
            print("\nЗапуск сбора остатков (таймаут 600с)...")
            stock_cmd = f'cd /d {REMOTE_CHZ_DIR} && "{REMOTE_PYTHON}" chz.py stock'
            run_cmd(stock_cmd, timeout=600)
            pull_stock_if_rewritten(before, "stock")
        elif subcmd == "csv-auto":
            # Special: refresh token, run csv-auto через dispenser API,
            # перестроить chz_stock.json, скачать на локалку.
            refresh_token_or_fail()
            before = remote_mtime(REMOTE_STOCK_JSON)
            print("\nАвтовыгрузка CSV через dispenser API (beer + water + nabeer, таймаут 1200с)...")
            csv_cmd = f'cd /d {REMOTE_CHZ_DIR} && "{REMOTE_PYTHON}" chz.py csv-auto'
            run_cmd(csv_cmd, timeout=1200)
            pull_stock_if_rewritten(before, "csv-auto")
        elif subcmd == "search-stock":
            # Special (с 2026-06): обновить токен, собрать остатки через
            # синхронный /cises/search (коды теперь сразу RETIRED/OWN_USE,
            # dispenser-выгрузка по RETIRED виснет), скачать chz_stock.json.
            # 0) Список нужных GTIN из iiko (фасовка на остатке) → точечная выгрузка.
            #    Запускается в контейнере прода, где есть iiko и баркоды. Не собрался
            #    (исключение: дев, нет iiko) — на бар-ПК остаётся прежний список.
            #    ПУСТОЙ список (iiko не дал остатки, compute_needed_gtins отвечает []) — стоп:
            #    chz.py принял бы его за «списка нет» и в брод-режиме (~20 GTIN) заменил бы
            #    полный chz_stock.json урезанным, с кодом 0 (ревью 2026-10-04).
            try:
                from core.chz_needed_gtins import compute_needed_gtins
                needed = compute_needed_gtins()
            except Exception as e:
                needed = None
                print(f"[WARN] список GTIN не собран ({e}) — на бар-ПК прежний список")
            if needed is not None:
                if not needed:
                    raise RuntimeError(
                        "Список нужных GTIN из iiko пуст (iiko недоступен или не отдал остатки) — "
                        "обновление ЧЗ не запускается, прежние данные остаются.")
                print(f"Нужных GTIN из iiko (фасовка на остатке): {len(needed)}")
                try:
                    needed_local = REPO_DIR / "chz_test" / "debug" / "needed_gtins.json"
                    needed_local.parent.mkdir(parents=True, exist_ok=True)
                    needed_local.write_text(json.dumps(needed), encoding="utf-8")
                    push(str(needed_local), REMOTE_CHZ_DIR + r"\debug")
                except Exception as e:
                    print(f"[WARN] список GTIN не отправлен ({e}) — на бар-ПК прежний список")
            refresh_token_or_fail()
            before = remote_mtime(REMOTE_STOCK_JSON)
            print("\nОстатки через /cises/search (таймаут 1800с)...")
            search_cmd = f'cd /d {REMOTE_CHZ_DIR} && "{REMOTE_PYTHON}" chz.py search-stock'
            search_out, _err = run_cmd(search_cmd, timeout=1800)
            if _stock_not_written(search_out):
                raise RuntimeError(
                    "chz.py search-stock не обновил chz_stock.json (пустой результат) — "
                    "старый файл не скачивается.")
            pull_stock_if_rewritten(before, "search-stock")
        else:
            # Запустить chz.py на бар-ПК из C:\chz_test
            ALLOWED_SUBCMDS = {"token", "stock", "report", "status", "mods", "csv-auto", "search-stock"}
            if subcmd not in ALLOWED_SUBCMDS:
                print(f"Неизвестная подкоманда: {subcmd}")
                print(f"Допустимые: {', '.join(sorted(ALLOWED_SUBCMDS))}")
                return
            extra_args = sys.argv[3:]
            safe_args = " ".join(a for a in extra_args if a.isalnum() or a.replace("-", "").isalnum())
            remote_cmd = (
                f'cd /d {REMOTE_CHZ_DIR} && '
                f'"{REMOTE_PYTHON}" chz.py {subcmd}'
            )
            if safe_args:
                remote_cmd += f' {safe_args}'
            print(f"Запуск: chz.py {subcmd} {safe_args}\n")
            run_cmd(remote_cmd)

    else:
        print(f"Неизвестная команда: {action}")


if __name__ == "__main__":
    main()
