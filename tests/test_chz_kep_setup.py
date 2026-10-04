"""
Тесты chz_test/kep_setup.py — настройка нового сертификата КЭП на бар-ПК без клавиатуры
(kep_setup.bat), и защиты ночного обновления ЧЗ от «тихого» сбоя подписи (remote_exec.py).

Windows, КриптоПро и SSH не нужны: команды (PowerShell, csptest, python chz.py, tailscale)
подменяются функцией run, папка C:\\chz_test — временной.

Что проверяется:
- разбор хранилища сертификатов (BOM, регистр, мусор), выбор отпечатка: ожидаемый, иначе
  самый новый действующий по ИНН, сертификаты с ключом раньше; разбор контейнеров csptest,
  контейнеры владельца КЭП новыми первыми; замена строки CERT_THUMBPRINT; разбор ответа
  product-info и названия;
- сценарии main: сертификат уже в Windows; ставится с Рутокена; подпись не прошла и
  прошла после переустановки; всё сломано — код 1 и «НЕ ПОЛУЧИЛОСЬ»; хранилище не
  прочиталось — остаётся отпечаток из файла; прежний chz.py сохраняется копией;
- chz.py: cert_thumbprint отбрасывает невидимый U+200E и пробелы; csptest завис
  (TimeoutExpired) — ошибка, а не падение; product-info при исключении в load_token
  отвечает строкой-маркером; «chz.py token» при сбое — код выхода 1;
- remote_exec: сбой токена ([ERR]) и пустой результат search-stock — RuntimeError, старый
  chz_stock.json не скачивается; удачный прогон скачивает;
- kep_setup.bat с CRLF; без эмодзи; синтаксис Python 3.10.
"""
import ast
import contextlib
import io
import os
import shutil
import subprocess
import sys
import types

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, 'chz_test'))

import chz  # noqa: E402
import kep_setup as ks  # noqa: E402
import remote_exec  # noqa: E402

NEW = '7A4CC550694A9ADFFC1D9A522A49B58B4AB12135'
OLD = '2297E52C1066BCAAB8A9708A66935E56D9761FC2'
OK_PI = ('@@CHZ_JSON@@{"ok": true, "version": 1, "items": {"04610093628430": '
         '{"name": "\\u041f\\u0438\\u0432\\u043e FH Helles"}}, "missing": [], "error": ""}')
SETUP_PY = os.path.join(_REPO, 'chz_test', 'kep_setup.py')
SETUP_BAT = os.path.join(_REPO, 'chz_test', 'kep_setup.bat')


# ----------------------------------------------------------------- чистые функции

def test_parse_store_and_pick():
    text = ('\ufeff' + OLD + '|2025-08-15|2026-11-15|True|CN=Иванов, ИНН=781421365746\n'
            + NEW + '|2026-08-07|2027-11-07|True|CN=Иванов, ИНН=781421365746\n'
            'мусор\n'
            'ABCDEF|2020-01-01|2021-01-01|False|короткий отпечаток\n')
    certs = ks.parse_store(text)
    assert [c['thumb'] for c in certs] == [OLD.lower(), NEW.lower()]
    assert certs[1]['has_key'] is True and certs[1]['not_before'] == '2026-08-07'
    assert ks.pick_thumbprint(certs, today='2026-10-04') == (NEW.lower(), 'expected')
    # Ожидаемого нет (ошибка при чтении с фото) — самый новый действующий по ИНН.
    assert ks.pick_thumbprint(certs, expected='0' * 40, today='2026-10-04') == (NEW.lower(), 'by_inn')
    # Истёкший не берётся; сертификат со ссылкой на ключ раньше более нового без неё.
    nokey = [dict(certs[1], has_key=False, not_before='2026-09-01', thumb='1' * 40), certs[0]]
    assert ks.pick_thumbprint(nokey, expected='0' * 40, today='2026-10-04')[0] == OLD.lower()
    assert ks.pick_thumbprint(certs, expected='0' * 40, today='2028-01-01') == (None, 'none')
    assert ks.pick_thumbprint([], today='2026-10-04') == (None, 'none')
    foreign = [{'thumb': '2' * 40, 'not_before': '2026-09-01', 'not_after': '2027-09-01',
                'has_key': True, 'subject': 'CN=Чужой, ИНН=111'}]
    assert ks.pick_thumbprint(foreign, expected='0' * 40, today='2026-10-04') == (None, 'none')


def test_normalize_thumbprint_drops_invisible_and_spaces():
    assert ks.normalize_thumbprint('\u200e7A 4C cc') == '7a4ccc'
    assert ks.normalize_thumbprint(None) == ''


def test_containers():
    out = ('CSP (Type:80) v5.0.10001 KC1\nAcquireContext: OK.\n'
           '\\\\.\\Aktiv Rutoken ECP 00 00\\2508151514-781421365746\n'
           '\\\\.\\Aktiv Rutoken ECP 00 00\\2608071536-781421365746\n'
           '\\\\.\\FAT12_E\\чужой\n'
           '\\\\.\\Aktiv Rutoken ECP 00 00\\2608071536-781421365746\nOK.\n')
    parsed = ks.parse_containers(out)
    assert len(parsed) == 3
    ordered = ks.owner_containers(parsed)
    assert [c.rsplit('\\', 1)[-1] for c in ordered] == ['2608071536-781421365746',
                                                         '2508151514-781421365746']
    # Контейнеров владельца нет — все найденные.
    assert ks.owner_containers(['\\\\.\\X\\abc']) == ['\\\\.\\X\\abc']
    assert ks.parse_containers('') == []


def test_set_thumbprint_on_real_chz():
    with open(os.path.join(_REPO, 'chz_test', 'chz.py'), encoding='utf-8') as f:
        source = f.read()
    new_text, count = ks.set_thumbprint(source, 'f' * 40)
    assert count == 1
    assert 'CERT_THUMBPRINT = "' + 'f' * 40 + '"' in new_text
    # Комментарий с прежним отпечатком строкой CERT_THUMBPRINT не считается.
    assert new_text.count('2297e52c1066bcaab8a9708a66935e56d9761fc2') == 1
    assert ks.set_thumbprint('нет строки', 'f' * 40)[1] == 0


def test_parse_product_info():
    payload = ks.parse_product_info('журнал\n' + OK_PI + '\n')
    assert payload['ok'] is True
    assert ks.product_name(payload) == 'Пиво FH Helles'
    assert ks.parse_product_info('без маркера') == {}
    assert ks.parse_product_info('@@CHZ_JSON@@{битый') == {}
    assert ks.product_name({'items': {}}) == ''


def test_chz_constants_match_setup():
    """Отпечаток в chz.py и ожидаемый в скрипте — один (КЭП от 07.08.2026)."""
    assert chz.cert_thumbprint() == ks.EXPECTED_THUMBPRINT
    assert chz.INN_ORG == ks.INN_ORG
    assert ks.SENTINEL == chz.CHZ_JSON_SENTINEL


# ----------------------------------------------------------------- сценарии main

def _rows(rows):
    return '\n'.join('{}|{}|{}|True|CN=X, ИНН=781421365746'.format(t, nb, na) for t, nb, na in rows)


@pytest.fixture
def bar(tmp_path, monkeypatch):
    """Флешка (src) с новым chz.py и C:\\chz_test (dst) со старым отпечатком."""
    src = tmp_path / 'flash'
    dst = tmp_path / 'chz_test'
    src.mkdir()
    dst.mkdir()
    with open(os.path.join(_REPO, 'chz_test', 'chz.py'), encoding='utf-8') as f:
        text = f.read()
    (src / 'chz.py').write_text(text, encoding='utf-8')
    (dst / 'chz.py').write_text(text.replace(NEW.lower(), OLD.lower()), encoding='utf-8')
    monkeypatch.setattr(ks, 'CHZ_DIR', str(dst))
    monkeypatch.setattr(ks, '__file__', str(src / 'kep_setup.py'))
    monkeypatch.setattr(ks, 'TAILSCALE', str(tmp_path / 'tailscale.exe'))
    (tmp_path / 'tailscale.exe').write_text('', encoding='utf-8')
    state = types.SimpleNamespace(stores=[], tokens=[True], install_ok=True, calls=[],
                                  store_fails=False, dst=dst)

    def fake_run(args, timeout=120, cwd=None, encoding='cp866', env=None):
        args = list(args)
        state.calls.append(args)
        if args[0] == 'powershell.exe':
            if state.store_fails:
                return 1, 'execution of scripts is disabled'
            rows = state.stores.pop(0) if len(state.stores) > 1 else state.stores[0]
            return 0, _rows(rows)
        if args[0] == ks.CSPTEST and '-enum_cont' in args:
            return 0, '\\\\.\\Aktiv Rutoken ECP 00 00\\2608071536-781421365746\nOK.'
        if args[0] == ks.CSPTEST and '-cinstall' in args:
            return (0, 'OK.') if state.install_ok else (1, 'ERROR 0x80090016')
        if 'chz.py' in args and 'token' in args:
            assert cwd == str(dst) and env['PYTHONIOENCODING'] == 'utf-8'
            ok = state.tokens.pop(0) if len(state.tokens) > 1 else state.tokens[0]
            if ok:
                return 0, '  [auth] Запрос UUID и DATA... [OK] 730f59bf...\n  [OK] Токен действует до: 2026-10-05'
            return 1, '[ERR] csptest rc=2148073494\n  [ERR] csptest failed'
        if 'chz.py' in args and 'product-info' in args:
            return 0, 'журнал\n' + OK_PI
        if args[0] == ks.TAILSCALE:
            return 0, '100.98.149.108 bar-pc windows -'
        return -1, 'unexpected'

    monkeypatch.setattr(ks, 'run', fake_run)
    return state


def _main():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = ks.main()
    return code, buf.getvalue()


def _thumb_line(state):
    with open(os.path.join(str(state.dst), 'chz.py'), encoding='utf-8') as f:
        return [line.strip() for line in f if line.startswith('CERT_THUMBPRINT')][0]


def _installs(state):
    return sum(1 for call in state.calls if '-cinstall' in call)


def test_main_certificate_already_in_windows(bar):
    bar.stores = [[(NEW, '2026-08-07', '2027-11-07'), (OLD, '2025-08-15', '2026-11-15')]]
    code, out = _main()
    assert code == 0
    assert _thumb_line(bar) == 'CERT_THUMBPRINT = "' + NEW.lower() + '"'
    assert _installs(bar) == 0
    assert 'Честный знак ответил: Пиво FH Helles' in out and 'ГОТОВО.' in out
    assert 'Tailscale подключён' in out
    backups = [n for n in os.listdir(str(bar.dst)) if n.startswith('chz_backup_')]
    assert len(backups) == 1   # прежний chz.py сохранён копией


def test_main_installs_from_token_when_not_in_windows(bar):
    bar.stores = [[(OLD, '2025-08-15', '2026-11-15')],
                  [(NEW, '2026-08-07', '2027-11-07'), (OLD, '2025-08-15', '2026-11-15')]]
    code, out = _main()
    assert code == 0 and _installs(bar) == 1
    assert 'Сертификат из контейнера установлен' in out
    assert _thumb_line(bar) == 'CERT_THUMBPRINT = "' + NEW.lower() + '"'


def test_main_signature_fails_then_reinstall_fixes(bar):
    bar.stores = [[(NEW, '2026-08-07', '2027-11-07')]]
    bar.tokens = [False, True]
    code, out = _main()
    assert code == 0 and _installs(bar) == 1
    assert 'Подпись прошла' in out


def test_main_everything_broken(bar):
    bar.stores = [[(OLD, '2025-08-15', '2026-11-15')]]
    bar.tokens = [False]
    bar.install_ok = False
    code, out = _main()
    assert code == 1
    assert 'НЕ ПОЛУЧИЛОСЬ' in out and 'ГОТОВО.' not in out
    assert '[ERR] csptest' in out          # хвост вывода chz.py показан для фото


def test_main_store_unreadable_keeps_file_thumbprint(bar):
    bar.store_fails = True
    bar.stores = [[]]
    code, out = _main()
    assert code == 0
    assert 'оставляю отпечаток из файла' in out
    assert _thumb_line(bar) == 'CERT_THUMBPRINT = "' + ks.EXPECTED_THUMBPRINT + '"'


def test_main_without_chz_dir(bar, monkeypatch, tmp_path):
    monkeypatch.setattr(ks, 'CHZ_DIR', str(tmp_path / 'нет'))
    code, out = _main()
    assert code == 1 and 'Нет папки' in out


# ----------------------------------------------------------------- chz.py

def test_chz_cert_thumbprint_strips_invisible(monkeypatch):
    monkeypatch.setattr(chz, 'CERT_THUMBPRINT', '\u200e7a 4c cc')
    assert chz.cert_thumbprint() == '7a4ccc'


def test_chz_get_token_csptest_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(chz, 'DEBUG_DIR', str(tmp_path))
    monkeypatch.setattr(chz, 'make_request', lambda *a, **k: (200, {'uuid': 'u' * 36, 'data': 'd' * 30}))

    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd='csptest', timeout=60)

    monkeypatch.setattr(chz.subprocess, 'run', hang)
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        result = chz.get_token()
    assert 'error' in result and 'timeout' in result['error']
    assert 'ждёт человека' in buf.getvalue()


def test_chz_product_info_answers_when_token_raises(monkeypatch):
    def boom():
        raise subprocess.TimeoutExpired(cmd='csptest', timeout=60)

    monkeypatch.setattr(chz, 'load_token', boom)
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        chz.run_product_info(['04610093628430'])
    last = buf.getvalue().strip().splitlines()[-1]
    assert last.startswith(chz.CHZ_JSON_SENTINEL) and '"no_token"' in last


def test_chz_token_command_exits_1_on_failure(monkeypatch):
    monkeypatch.setattr(chz, 'get_token', lambda: {'error': 'csptest failed'})
    monkeypatch.setattr(sys, 'argv', ['chz.py', 'token'])
    with contextlib.redirect_stdout(io.StringIO()):
        with pytest.raises(SystemExit) as exc:
            chz.main()
    assert exc.value.code == 1


# ----------------------------------------------------------------- remote_exec

def _remote(monkeypatch, token_out, search_out):
    calls = []

    def fake_run_cmd(cmd, verbose=True, timeout=None):
        calls.append(cmd)
        if cmd.endswith('chz.py token'):
            return token_out, ''
        if cmd.endswith('chz.py search-stock'):
            return search_out, ''
        return '', ''

    pulled = []
    monkeypatch.setattr(remote_exec, 'run_cmd', fake_run_cmd)
    monkeypatch.setattr(remote_exec, 'push', lambda *a, **k: None)
    monkeypatch.setattr(remote_exec, 'pull', lambda *a, **k: pulled.append(a))
    fake = types.ModuleType('core.chz_needed_gtins')
    fake.compute_needed_gtins = lambda: ['04610093628430']
    monkeypatch.setitem(sys.modules, 'core.chz_needed_gtins', fake)
    monkeypatch.setattr(sys, 'argv', ['remote_exec.py', 'run', 'search-stock'])
    return calls, pulled


def test_remote_search_stock_stops_on_token_error(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_exec, 'REPO_DIR', tmp_path)
    calls, pulled = _remote(monkeypatch, '  [auth] [OK] 730f\n[ERR] csptest rc=1\n  [ERR] csptest failed', 'x')
    with contextlib.redirect_stdout(io.StringIO()):
        with pytest.raises(RuntimeError) as exc:
            remote_exec.main()
    assert 'Токен ЧЗ' in str(exc.value)
    assert not any(c.endswith('search-stock') for c in calls) and pulled == []


def test_remote_search_stock_stops_on_empty_result(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_exec, 'REPO_DIR', tmp_path)
    # Кириллица по SSH — кракозябры; ASCII-части строки остаются.
    _calls, pulled = _remote(monkeypatch, '  [OK] Token', '[WARN] ????? ????????? \u2014 chz_stock.json ?? ??????????')
    with contextlib.redirect_stdout(io.StringIO()):
        with pytest.raises(RuntimeError):
            remote_exec.main()
    assert pulled == []


def test_remote_search_stock_ok_pulls(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_exec, 'REPO_DIR', tmp_path)
    _calls, pulled = _remote(monkeypatch, '  [OK] Token', '[OK] 312 GTIN\n[WARN] needed_gtins.json old')
    with contextlib.redirect_stdout(io.StringIO()):
        remote_exec.main()
    assert len(pulled) == 1


# ----------------------------------------------------------------- файлы

def test_bat_has_crlf_and_calls_setup():
    with open(SETUP_BAT, 'rb') as f:
        raw = f.read()
    assert b'\r\n' in raw and b'\n' not in raw.replace(b'\r\n', b'')
    text = raw.decode('ascii')       # cmd.exe: только ASCII, без кодовых страниц
    assert 'kep_setup.py' in text and 'Python312' in text and 'pause' in text


def test_python310_syntax_and_no_emoji():
    for path in (SETUP_PY, os.path.join(_REPO, 'chz_test', 'chz.py'),
                 os.path.join(_REPO, 'remote_exec.py')):
        with open(path, encoding='utf-8') as f:
            source = f.read()
        ast.parse(source, feature_version=(3, 10))
        assert not any(0x1F300 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF
                       for ch in source), path
