"""Настройка нового сертификата КЭП для chz.py на бар-ПК — без клавиатуры.

Запуск: двойной щелчок по kep_setup.bat (рядом должны лежать kep_setup.py и chz.py,
например на флешке). Всё, что нужно ввести руками, — PIN-код Рутокена, если КриптоПро
его спросит (экранной клавиатурой, с галочкой «Запомнить пароль»).

Зачем. chz.py подписывает вход в Честный знак сертификатом CERT_THUMBPRINT. После
перевыпуска КЭП на новый Рутокен отпечаток другой; со старым КриптоПро ждёт старый
Рутокен (окно «Выбор ключевого носителя», «Вставлен носитель с другим уникальным
номером») — так было 2026-10-04 (README, раздел «Перевыпуск КЭП»).

Что делает (каждый шаг печатается):
1. Копирует chz.py из своей папки в C:\\chz_test; прежний остаётся рядом копией
   chz_backup_<дата-время>.py.
2. Ищет сертификат в хранилище «Личное» текущего пользователя: ожидаемый отпечаток
   EXPECTED_THUMBPRINT; нет его — ставит сертификат из контейнера на вставленном
   Рутокене (csptest -property -cinstall, запасной путь — certmgr -inst) и ищет
   снова; ожидаемого так и нет — берёт самый новый действующий сертификат, где есть
   ИНН владельца КЭП (KEY_OWNER_INN) или ИНН организации (INN_ORG).
3. Записывает найденный отпечаток в строку CERT_THUMBPRINT файла C:\\chz_test\\chz.py.
4. Проверяет: «chz.py token» (подпись КриптоПро, токен Честного знака) и
   «chz.py product-info CHECK_GTIN» (название из каталога ЧЗ). Подпись не прошла,
   а сертификат из контейнера ещё не ставили, — ставит и проверяет ещё раз.
5. Показывает, подключён ли Tailscale (через него сервер ночью ходит на бар-ПК).

Ничего не удаляет. Только Windows и КриптоПро CSP; чистые функции (разбор вывода,
выбор отпечатка, правка chz.py) проверяются тестами на любой ОС
(tests/test_chz_kep_setup.py).
"""
import base64
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

CHZ_DIR = r"C:\chz_test"
CSPTEST = r"C:\Program Files\Crypto Pro\CSP\csptest.exe"
CERTMGR = r"C:\Program Files\Crypto Pro\CSP\certmgr.exe"
TAILSCALE = r"C:\Program Files\Tailscale\tailscale.exe"

# Отпечаток КЭП от 07.08.2026 (контейнер 2608071536-781421365746), снят с фото окна
# «Сертификат -> Состав -> Отпечаток» 2026-10-04. Ошибка в одном символе не страшна:
# такого отпечатка не будет в хранилище, и скрипт возьмёт сертификат по ИНН.
EXPECTED_THUMBPRINT = "7a4cc550694a9adffc1d9a522a49b58b4ab12135"
# ИНН владельца КЭП — в имени контейнера («2608071536-781421365746») и в сертификате.
KEY_OWNER_INN = "781421365746"
INN_ORG = "7801630649"            # ООО «ИНВЕСТАГРО», как в chz.py
CHECK_GTIN = "04610093628430"     # FH Helles — есть в каталоге ЧЗ (docs/receiving.md)
SENTINEL = "@@CHZ_JSON@@"         # маркер ответа chz.py product-info
THUMB_LINE_RE = re.compile(r'^CERT_THUMBPRINT\s*=\s*"[^"\n]*"', re.MULTILINE)
HEX40_RE = re.compile(r"[0-9a-f]{40}")
# Строка версии в chz.py: CHZ_VERSION = "2026-10-04" (дата ISO, сравнивается строкой).
CHZ_VERSION_RE = re.compile(r'^CHZ_VERSION\s*=\s*["\']([0-9-]+)["\']', re.M)

# Сколько ждать: подпись КриптоПро (csptest в chz.py ждёт 60 с, столько же есть на
# ввод PIN) плюс сеть до Честного знака.
TOKEN_TIMEOUT_SEC = 180
PRODUCT_INFO_TIMEOUT_SEC = 180

# Хранилище «Личное»: отпечаток|начало|конец|есть ли ключ|субъект — по строке на
# сертификат, вывод в UTF-8 (без этого кириллица субъекта приходит в OEM-кодировке).
STORE_PS = (
    "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false\n"
    "Get-ChildItem Cert:\\CurrentUser\\My | ForEach-Object {\n"
    "  $hk = $false; try { $hk = $_.HasPrivateKey } catch {}\n"
    "  $_.Thumbprint + '|' + $_.NotBefore.ToString('yyyy-MM-dd') + '|' + "
    "$_.NotAfter.ToString('yyyy-MM-dd') + '|' + $hk + '|' + $_.Subject\n"
    "}\n"
)


# ----------------------------------------------------------------- чистые функции

def normalize_thumbprint(value) -> str:
    """Отпечаток в нижнем регистре только из hex-символов (без пробелов и U+200E)."""
    return "".join(ch for ch in str(value or "").lower() if ch in "0123456789abcdef")


def parse_store(text) -> list:
    """Вывод STORE_PS -> [{'thumb', 'not_before', 'not_after', 'has_key', 'subject'}]."""
    certs = []
    for line in str(text or "").replace("\ufeff", "").splitlines():
        parts = line.strip().split("|", 4)
        if len(parts) != 5:
            continue
        thumb = normalize_thumbprint(parts[0])
        if not HEX40_RE.fullmatch(thumb):
            continue
        certs.append({
            "thumb": thumb,
            "not_before": parts[1].strip(),
            "not_after": parts[2].strip(),
            "has_key": parts[3].strip().lower() == "true",
            "subject": parts[4].strip(),
        })
    return certs


def pick_thumbprint(certs, expected=EXPECTED_THUMBPRINT, today=None, exclude=()) -> tuple:
    """Какой сертификат ставить в chz.py: (отпечаток | None, как найден).

    Ожидаемый отпечаток есть в хранилище, действует и нет более нового действующего
    сертификата с ключом по ИНН — он ('expected'). Иначе — самый новый (по дате начала)
    действующий сертификат с KEY_OWNER_INN или INN_ORG в субъекте, сертификаты со ссылкой
    на ключ раньше ('by_inn'). Ничего — (None, 'none'). exclude — отпечатки, которые уже
    не подошли (повтор после установки с Рутокена не выбирает их снова).
    Ревью 2026-10-04: прежде ожидаемый отпечаток выигрывал всегда — при следующем
    перевыпуске КЭП старый сертификат (он остаётся в хранилище) выбирался снова, и
    kep_setup не мог уйти с него, даже поставив новый.
    """
    today = today or datetime.date.today().isoformat()
    expected = normalize_thumbprint(expected)
    skip = {normalize_thumbprint(t) for t in exclude}
    ours = [c for c in certs
            if c["thumb"] not in skip
            and (KEY_OWNER_INN in c["subject"] or INN_ORG in c["subject"])
            and c["not_after"] >= today]
    ours.sort(key=lambda c: (c["has_key"], c["not_before"]), reverse=True)
    exp = next((c for c in certs if c["thumb"] == expected and expected not in skip), None)
    if exp is not None and exp["not_after"] >= today:
        newer = [c for c in ours if c["thumb"] != expected and c["has_key"]
                 and c["not_before"] > exp["not_before"]]
        if not newer:
            return expected, "expected"
    if not ours:
        return None, "none"
    return ours[0]["thumb"], "by_inn"


def parse_containers(text) -> list:
    """Вывод csptest -keyset -enum_cont -fqcn -> полные имена контейнеров («\\\\.\\...»)."""
    out = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if line.startswith("\\\\.\\") and line not in out:
            out.append(line)
    return out


def owner_containers(containers) -> list:
    """Контейнеры КЭП владельца (KEY_OWNER_INN в имени), новые первыми.

    Имя контейнера ФНС — «ГГММДДччмм-ИНН»: обратная сортировка по имени = по дате.
    Контейнеров владельца нет — все найденные (на Рутокене может быть один чужой по имени).
    """
    ours = [c for c in containers if KEY_OWNER_INN in c]
    return sorted(ours or containers, key=lambda c: c.rsplit("\\", 1)[-1], reverse=True)


def set_thumbprint(source: str, thumb: str) -> tuple:
    """Текст chz.py -> (новый текст, сколько строк CERT_THUMBPRINT заменено)."""
    return THUMB_LINE_RE.subn('CERT_THUMBPRINT = "' + thumb + '"', source)


def parse_product_info(output) -> dict:
    """Вывод chz.py product-info -> JSON последней строки с маркером ({} — маркера нет)."""
    for line in reversed(str(output or "").splitlines()):
        position = line.rfind(SENTINEL)
        if position >= 0:
            try:
                payload = json.loads(line[position + len(SENTINEL):].strip())
            except ValueError:
                return {}
            return payload if isinstance(payload, dict) else {}
    return {}


def product_name(payload, gtin=CHECK_GTIN) -> str:
    """Название товара из ответа product-info (name, иначе fullName)."""
    item = (payload.get("items") or {}).get(gtin) if isinstance(payload, dict) else None
    if not isinstance(item, dict):
        return ""
    return str(item.get("name") or item.get("fullName") or "").strip()


# ----------------------------------------------------------------- Windows

def run(args, timeout=120, cwd=None, encoding="cp866", env=None) -> tuple:
    """Команда -> (код возврата, вывод stdout+stderr). Не найдена / таймаут — код -1."""
    try:
        result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=timeout,
                                encoding=encoding, errors="replace")
    except FileNotFoundError:
        return -1, "не найдено: " + str(args[0])
    except subprocess.TimeoutExpired:
        return -1, "не ответило за " + str(timeout) + " с"
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def store_certs() -> list:
    encoded = base64.b64encode(STORE_PS.encode("utf-16-le")).decode("ascii")
    code, out = run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                     "Bypass", "-EncodedCommand", encoded], timeout=60, encoding="utf-8")
    if code != 0:
        say("  [!] PowerShell не прочитал хранилище сертификатов: " + out.strip()[-300:])
    return parse_store(out)


def install_from_containers() -> bool:
    """Поставить сертификат из контейнера КЭП в хранилище «Личное» (со ссылкой на ключ)."""
    code, out = run([CSPTEST, "-keyset", "-enum_cont", "-fqcn", "-verifyc"], timeout=120)
    containers = owner_containers(parse_containers(out))
    if not containers:
        say("  [!] На вставленном Рутокене не найден ни один контейнер ключа.")
        say("      Вывод csptest: " + out.strip()[-400:])
        return False
    for fqcn in containers:
        say("  Контейнер: " + fqcn)
        code, out = run([CSPTEST, "-property", "-cinstall", "-cont", fqcn], timeout=120)
        if code == 0:
            say("  [OK] Сертификат из контейнера установлен (csptest).")
            return True
        if os.path.exists(CERTMGR):
            code, out2 = run([CERTMGR, "-inst", "-store", "uMy", "-cont", fqcn], timeout=120)
            if code == 0:
                say("  [OK] Сертификат из контейнера установлен (certmgr).")
                return True
            out = out + "\n" + out2
        say("  [!] Не установился: " + out.strip()[-400:])
    return False


def run_chz(args, timeout) -> tuple:
    """python chz.py <args> в C:\\chz_test; вывод в UTF-8 (кириллица без кракозябр)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return run([sys.executable, "chz.py"] + list(args), timeout=timeout, cwd=CHZ_DIR,
               encoding="utf-8", env=env)


def say(text=""):
    print(text, flush=True)


def show_tail(output, lines=12):
    for line in str(output or "").strip().splitlines()[-lines:]:
        say("    " + line)


def check_signature() -> tuple:
    """(подпись прошла, вывод) — chz.py token: свежий токен Честного знака по КЭП."""
    code, out = run_chz(["token"], TOKEN_TIMEOUT_SEC)
    return code == 0 and "[ERR]" not in out and "[OK]" in out, out


def chz_version(path: str) -> str:
    """CHZ_VERSION из файла chz.py ('' — нет строки или файла): дата ISO, сравнивается строкой."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            match = CHZ_VERSION_RE.search(f.read())
    except OSError:
        return ""
    return match.group(1) if match else ""


def copy_chz(here: str) -> bool:
    """Скопировать chz.py с флешки в CHZ_DIR (прежний — в chz_backup_<время>.py).

    На компьютере chz.py новее (CHZ_VERSION больше, его обновили по SSH после того, как
    готовили флешку) — не копирует: старая флешка не откатывает код (ревью 2026-10-04).
    """
    source = os.path.join(here, "chz.py")
    target = os.path.join(CHZ_DIR, "chz.py")
    if not os.path.isdir(CHZ_DIR):
        say("[!] Нет папки " + CHZ_DIR + " — это не тот компьютер?")
        return False
    if os.path.abspath(source).lower() == os.path.abspath(target).lower():
        say("1. chz.py уже в " + CHZ_DIR + " — копировать не нужно.")
        return True
    if not os.path.exists(source):
        say("[!] Рядом со скриптом нет chz.py — положите его в ту же папку на флешке.")
        return False
    if os.path.exists(target) and chz_version(target) > chz_version(source):
        say("1. На компьютере chz.py новее (версия " + chz_version(target) + "), чем на флешке ("
            + (chz_version(source) or "без версии") + ") — оставляю его.")
        return True
    if os.path.exists(target):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = os.path.join(CHZ_DIR, "chz_backup_" + stamp + ".py")
        shutil.copy2(target, backup)
        say("1. Прежний chz.py сохранён как " + os.path.basename(backup))
    shutil.copy2(source, target)
    say("   Новый chz.py скопирован в " + CHZ_DIR)
    return True


def write_thumbprint(thumb: str) -> bool:
    path = os.path.join(CHZ_DIR, "chz.py")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new_text, count = set_thumbprint(text, thumb)
    if count != 1:
        say("[!] В chz.py не нашлась строка CERT_THUMBPRINT — файл не тот?")
        return False
    if new_text != text:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
    say("3. В chz.py записан отпечаток " + thumb)
    return True


def find_thumbprint(allow_install: bool) -> tuple:
    """(отпечаток | None, как найден, ставили ли сертификат из контейнера)."""
    certs = store_certs()
    thumb, how = pick_thumbprint(certs)
    if how == "expected" or not allow_install:
        return thumb, how, False
    say("   В хранилище нет ожидаемого сертификата — ставлю его с Рутокена...")
    installed = install_from_containers()
    if installed:
        thumb, how = pick_thumbprint(store_certs())
    return thumb, how, installed


def tailscale_note():
    if not os.path.exists(TAILSCALE):
        say("5. Tailscale не найден по пути " + TAILSCALE + " — проверьте значок у часов.")
        return
    code, out = run([TAILSCALE, "status"], timeout=30, encoding="utf-8")
    if code == 0:
        say("5. Tailscale подключён — сервер сможет ночью зайти на этот компьютер.")
    else:
        say("5. [!] Tailscale не подключён: " + out.strip()[-200:])
        say("      Включите его (значок у часов), иначе ночное обновление не дойдёт.")


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    say("=== Настройка КЭП для Честного знака (chz.py) ===")
    say()
    if not copy_chz(here):
        return 1

    say()
    say("2. Ищу сертификат КЭП в Windows...")
    thumb, how, installed = find_thumbprint(allow_install=True)
    if not thumb:
        # Хранилище не прочиталось (PowerShell запрещён и т. п.) — отпечаток с фото уже
        # в chz.py; проверка подписи ниже покажет, подходит ли он.
        say("   [!] Сертификат в Windows не найден — оставляю отпечаток из файла.")
        thumb, how = EXPECTED_THUMBPRINT, "file"
    if how == "expected":
        say("   [OK] Найден сертификат с отпечатком " + thumb)
    elif how == "by_inn":
        say("   [!] Беру самый новый действующий сертификат по ИНН: " + thumb)
        say("       (ожидаемого в Windows нет, он истёк или есть новее)")
    if not write_thumbprint(thumb):
        return 1

    say()
    say("4. Проверяю подпись и вход в Честный знак.")
    say("   Если КриптоПро спросит PIN-код Рутокена — введите его экранной клавиатурой")
    say("   и поставьте галочку «Запомнить пароль» (на ввод есть минута).")
    say("   Если появится окно «Выбор ключевого носителя» — нажмите «Отмена».")
    ok, out = check_signature()
    if not ok and not installed:
        say("   Подпись не прошла — ставлю сертификат с Рутокена заново и пробую ещё раз...")
        if install_from_containers():
            installed = True
            thumb2, _how2 = pick_thumbprint(store_certs(), exclude={thumb})
            if thumb2 and thumb2 != thumb and write_thumbprint(thumb2):
                thumb = thumb2
            ok, out = check_signature()
    if not ok:
        say("   [!] Подпись не прошла. Хвост вывода chz.py:")
        show_tail(out)
        say()
        say("НЕ ПОЛУЧИЛОСЬ. Сфотографируйте это окно и пришлите. Старый файл не тронут:")
        say("   он лежит рядом копией chz_backup_*.py.")
        return 1
    say("   [OK] Подпись прошла, токен Честного знака получен.")

    code, out = run_chz(["product-info", CHECK_GTIN], PRODUCT_INFO_TIMEOUT_SEC)
    payload = parse_product_info(out)
    if payload.get("ok"):
        name = product_name(payload)
        say("   [OK] Честный знак ответил: " + (name or "карточка без названия"))
    else:
        say("   [!] Подпись есть, но product-info не ответил: " + str(payload.get("error") or "нет ответа"))
        show_tail(out)

    say()
    tailscale_note()
    say()
    say("ГОТОВО." if payload.get("ok") else "Подпись настроена, названия — см. выше.")
    say("Отпечаток в chz.py: " + thumb)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # noqa: BLE001 — человеку нужен текст, а не тишина
        say()
        say("[!] Ошибка скрипта: " + type(error).__name__ + ": " + str(error))
        say("Сфотографируйте это окно и пришлите.")
        sys.exit(1)
