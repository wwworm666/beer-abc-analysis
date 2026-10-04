"""Удалённое выполнение команд на бар-ПК через Tailscale + SSH.

Использует paramiko для подключения к бар-ПК (100.98.149.108) по Tailscale IP.

Команды:
    python remote_exec.py status                    - проверить связь
    python remote_exec.py cmd "hostname"            - выполнить команду
    python remote_exec.py push chz.py chz_test/     - отправить файл/папку
    python remote_exec.py pull chz_test/data/ data/ - забрать файлы
    python remote_exec.py run stock                 - обновить токен, запустить chz.py stock, скачать chz_stock.json
    python remote_exec.py run report 2026-03-01     - выполнить chz.py report

run stock, csv-auto и search-stock с флагом --sync-chz (так их зовёт обновление ЧЗ на сервере)
сначала приводят chz.py на бар-ПК к серверному (sync_chz_script; выключатель —
CHZ_AUTO_UPDATE=0 в окружении).
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
            error = RuntimeError(
                f"Remote command failed (exit {exit_code}): {rem_cmd!r}"
                + (f"\nSTDERR: {err.strip()}" if err.strip() else "")
            )
            error.out = out      # вывод команды — для понятной причины (refresh_token_or_fail)
            raise error
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
# Сбой подписи (в выводе chz.py token строка «[ERR] csptest …»): дело в Рутокене или отпечатке.
TOKEN_FAIL_TEXT = (
    "Токен ЧЗ на бар-ПК не получен (подпись КриптоПро не прошла: тот ли Рутокен "
    "вставлен, тот ли CERT_THUMBPRINT в chz.py). Остатки не собираются, старый "
    "chz_stock.json не скачивается.")
# Остальные сбои (ЧЗ не ответил, сеть бар-ПК, 5xx): причина — последняя строка [ERR]
# вывода, без догадок про Рутокен (ревью 2026-10-04: любой сбой выглядел сбоем подписи).
TOKEN_FAIL_OTHER = (
    "Токен ЧЗ на бар-ПК не получен: {detail}. Остатки не собираются, старый "
    "chz_stock.json не скачивается.")
TOKEN_DETAIL_LIMIT = 200


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
        raise RuntimeError(token_error_text(getattr(exc, "out", ""), str(exc))) from exc
    if "[ERR]" in (out or ""):
        raise RuntimeError(token_error_text(out, ""))


def token_error_text(out, fallback: str) -> str:
    """Причина сбоя «chz.py token» по его выводу: подпись (csptest) — TOKEN_FAIL_TEXT;
    иначе последняя строка [ERR] (ASCII: кириллица по SSH — кракозябры), а без неё —
    первая строка fallback (текст ошибки run_cmd)."""
    errors = [line.strip() for line in str(out or "").splitlines() if "[ERR]" in line]
    if any("[ERR] csptest" in line for line in errors):
        return TOKEN_FAIL_TEXT
    if errors:
        detail = errors[-1][errors[-1].index("[ERR]"):]
    else:
        detail = (str(fallback or "").strip().splitlines() or ["нет вывода"])[0]
    detail = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in detail)[:TOKEN_DETAIL_LIMIT]
    return TOKEN_FAIL_OTHER.format(detail=detail)


# ----- chz.py на бар-ПК: обновление с сервера ------------------------------------------
#
# Решение владельца 2026-10-04: chz.py на бар-ПК кладёт сервер — тем же путём, которым ходит
# туда каждую ночь (Tailscale + SSH), а не человек командой push. Правило: на бар-ПК тот же
# chz.py, что выложен на сервере, но со своей строкой CERT_THUMBPRINT — её пишет
# kep_setup.bat под вставленный Рутокен, и после следующего перевыпуска КЭП отпечаток из
# репозитория сломал бы ночной вход в ЧЗ. Файлы сравниваются целиком без этой строки и без
# разницы в переводах строк: отличаются — файл на бар-ПК заменяется серверным, в том числе
# если там версия «новее» (откат выпуска на сервере доезжает до бар-ПК, а случайно залитый
# с другого компьютера файл не остаётся). Заменяет только обёртка обновления ЧЗ на сервере
# (флаг SYNC_FLAG у run, его передаёт routes/stocks.py): ручной запуск из другой копии
# репозитория свой chz.py на бар-ПК не кладёт (ревью 2026-10-04).
CHZ_VERSION_RE = re.compile(r'^CHZ_VERSION\s*=\s*["\']([0-9-]+)["\']', re.M)
THUMB_LINE_RE = re.compile(r'^CERT_THUMBPRINT\s*=\s*"[^"\n]*"', re.M)
REMOTE_CHZ_PY = REMOTE_CHZ_DIR + r"\chz.py"
# Копии прежнего chz.py: то же имя, что у копий kep_setup (chz_backup_<время>.py) — по
# имени они сортируются по времени.
BACKUP_PREFIX = "chz_backup_"
SYNC_FLAG = "--sync-chz"
# CHZ_AUTO_UPDATE=0 в окружении сервера — chz.py на бар-ПК не трогать (только вручную push).
AUTO_UPDATE_ENV = "CHZ_AUTO_UPDATE"


def chz_version(text) -> str:
    """CHZ_VERSION из текста chz.py (для журнала); '' — строки нет (файлы до 2026-10-04)."""
    match = CHZ_VERSION_RE.search(text or "")
    return match.group(1) if match else ""


def _body(text) -> str:
    """Текст chz.py для сравнения: без строки CERT_THUMBPRINT, переводы строк — LF."""
    return THUMB_LINE_RE.sub('CERT_THUMBPRINT = ""', (text or "").replace("\r\n", "\n"))


def with_remote_thumbprint(local_text: str, remote_text: str) -> str:
    """Текст chz.py с сервера со строкой CERT_THUMBPRINT из текста с бар-ПК.

    В тексте с бар-ПК строки нет — текст с сервера как есть.
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


def _latest_backup_text(sftp) -> str:
    """Текст самой новой копии chz_backup_<время>.py на бар-ПК ('' — копий нет).

    Источник отпечатка КЭП, когда в chz.py на бар-ПК строки нет или самого файла нет
    (связь оборвалась посреди прошлой замены).
    """
    try:
        names = sorted(n for n in sftp.listdir(REMOTE_CHZ_DIR)
                       if n.startswith(BACKUP_PREFIX) and n.endswith(".py"))
    except IOError:
        return ""
    if not names:
        return ""
    data = _sftp_read(sftp, REMOTE_CHZ_DIR + "\\" + names[-1])
    return data.decode("utf-8", errors="replace") if data else ""


def _replace_remote_chz(sftp, new_bytes: bytes, old_bytes) -> str:
    """Заменить chz.py на бар-ПК так, чтобы файл не пропадал. -> имя копии прежнего или ''.

    1. Прежний — копией chz_backup_<время>.py (запись байтов; сам chz.py не трогается).
    2. Новый — в chz.py.new и posix-rename поверх chz.py: OpenSSH заменяет файл одной
       операцией. Сервер без posix-rename (обычное переименование на Windows поверх файла
       не идёт) — chz.py удаляется, chz.py.new переименовывается; оборвись связь между
       этими шагами — chz.py не будет до следующего обновления, отпечаток тогда берётся из
       копии (_latest_backup_text).
    3. chz.py читается обратно и сверяется побайтно.
    Сбой на шагах 2–3 — прежние байты пишутся в chz.py обратно, ошибка — наружу.
    old_bytes=None — файла на бар-ПК не было.
    """
    temp_path = REMOTE_CHZ_PY + ".new"
    backup_name = ""
    if old_bytes is not None:
        backup_name = BACKUP_PREFIX + time.strftime("%Y%m%d_%H%M%S") + ".py"
        sftp.putfo(io.BytesIO(old_bytes), REMOTE_CHZ_DIR + "\\" + backup_name)
    try:
        sftp.putfo(io.BytesIO(new_bytes), temp_path)
        try:
            sftp.posix_rename(temp_path, REMOTE_CHZ_PY)
        except IOError:
            if old_bytes is not None:
                sftp.remove(REMOTE_CHZ_PY)
            sftp.rename(temp_path, REMOTE_CHZ_PY)
        if _sftp_read(sftp, REMOTE_CHZ_PY) != new_bytes:
            raise IOError("chz.py на бар-ПК не совпал с отправленным")
    except Exception:
        if old_bytes is not None:
            sftp.putfo(io.BytesIO(old_bytes), REMOTE_CHZ_PY)
        _quiet_remove(sftp, temp_path)
        raise
    return backup_name


# Итог последней сверки chz.py с бар-ПК (chz_test/debug/chz_sync.json): его отдаёт статус
# обновления ЧЗ (поле chz_sync, routes/stocks.py) — строка в журнале тонет в выводе сбора
# остатков, а страница показывает только хвост журнала (ревью 2026-10-04).
SYNC_RESULT_FILE = "chz_sync.json"


def sync_chz_script() -> str:
    """Привести chz.py на бар-ПК к серверному, сохранив строку отпечатка КЭП бар-ПК.

    Совпадает (без строки CERT_THUMBPRINT и разницы в переводах строк) — файл не
    трогается. Иначе — _replace_remote_chz. Строка CERT_THUMBPRINT — из chz.py на бар-ПК,
    нет её там (или файла) — из самой новой копии chz_backup_*.py, нет и копий — с сервера.
    Любая ошибка — строка [WARN], а обновление ЧЗ идёт дальше: свежий файл полезен, но не
    стоит ночи без данных. Итог печатается в журнал и пишется в SYNC_RESULT_FILE.
    Возврат: 'off' | 'no-local' | 'current' | 'updated' | 'failed'.
    """
    result, message = _sync_chz()
    print(message)
    try:
        path = REPO_DIR / "chz_test" / "debug" / SYNC_RESULT_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"result": result, "message": message,
                                    "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                   ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return result


def _sync_chz() -> tuple:
    """Сверка и замена chz.py на бар-ПК -> (итог, строка для журнала)."""
    if os.environ.get(AUTO_UPDATE_ENV, "1").strip() == "0":
        return "off", f"chz.py на бар-ПК: автообновление выключено ({AUTO_UPDATE_ENV}=0)"
    try:
        local_text = (REPO_DIR / "chz_test" / "chz.py").read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return "no-local", f"[WARN] chz.py на сервере не прочитан ({e}) — бар-ПК не обновляется"
    if not THUMB_LINE_RE.search(local_text):
        return "no-local", "[WARN] chz.py на сервере без строки CERT_THUMBPRINT — бар-ПК не обновляется"
    version = chz_version(local_text) or "без версии"
    try:
        client = connect()
    except Exception as e:
        return "failed", f"[WARN] chz.py на бар-ПК не проверен ({e})"
    try:
        sftp = client.open_sftp()
        try:
            remote_bytes = _sftp_read(sftp, REMOTE_CHZ_PY)
            remote_text = remote_bytes.decode("utf-8", errors="replace") if remote_bytes is not None else ""
            if remote_bytes is not None and _body(remote_text) == _body(local_text):
                return "current", f"chz.py на бар-ПК совпадает с сервером (версия {version})"
            if THUMB_LINE_RE.search(remote_text):
                thumb_text, thumb_from = remote_text, "с бар-ПК"
            else:
                thumb_text, thumb_from = _latest_backup_text(sftp), "из копии на бар-ПК"
                if not THUMB_LINE_RE.search(thumb_text):
                    thumb_from = "с сервера"
            new_bytes = with_remote_thumbprint(local_text, thumb_text).encode("utf-8")
            backup = _replace_remote_chz(sftp, new_bytes, remote_bytes)
        finally:
            sftp.close()
    except Exception as e:
        return "failed", f"[WARN] chz.py на бар-ПК не обновлён ({e})"
    finally:
        client.close()
    was = "файла не было" if remote_bytes is None else (chz_version(remote_text) or "без версии")
    kept = f"; прежний — {backup}" if backup else ""
    return "updated", (f"chz.py на бар-ПК обновлён: {was} -> {version} "
                       f"(отпечаток КЭП {thumb_from}{kept})")


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
        if subcmd in ("stock", "csv-auto", "search-stock") and SYNC_FLAG in sys.argv[3:]:
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
