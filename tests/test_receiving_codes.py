"""
Тесты разбора кода со сканера приёмки РЦ (core/receiving_codes.py) и паритета
с JS-портом static/js/receiving/codes.js.

Self-runnable: `py -3 tests/test_receiving_codes.py` (совместимо с pytest).
Сети и диска нет; Node нужен только для проверки паритета на случайных строках
(нет Node — эта проверка пропускается; фикстуру Node-тест прогоняет сам:
`node tests/test_receiving_codes.mjs`).

Что проверяется:
- общая фикстура tests/fixtures/receiving_codes.json: каждый случай даёт ровно
  ожидаемый словарь (ok, kind, gtin, serial, key, code, reason, message),
  штрихкод для iiko, в фикстуре есть все обязательные виды случаев (DataMatrix
  с GS и без, ]d2, русская раскладка, «␝», криптохвост, EAN-13/EAN-8/UPC-A/
  GTIN-14, неверная контрольная, SSCC, QR, ЕГАИС, пусто, пробелы, (01)(21),
  01 + GTIN без серийника); GTIN в фикстуре — с верной контрольной цифрой;
- контрольная цифра GS1, штрихкод для iiko (EAN-8 / EAN-13 / GTIN-14);
- повторный разбор нормализованного code даёт тот же ключ (идемпотентность:
  страница может прислать на сервер уже нормализованный код);
- раскладка ЙЦУКЕН → QWERTY: все 33 буквы в обоих регистрах, взаимно однозначно;
- паритет Python ↔ Node на тысячах случайных строк (кириллица, GS, «␝», скобки,
  символы вне BMP, одиночный суррогат, граница MAX_CODE_LEN);
- модуль не тянет Flask, синтаксис совместим с Python 3.10, без эмодзи.
"""
import ast
import json
import os
import random
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from core import receiving_codes as rc  # noqa: E402
from core.receiving_codes import barcode_for_iiko, gtin_check_ok, parse_code  # noqa: E402

FIXTURE = os.path.join(ROOT, 'tests', 'fixtures', 'receiving_codes.json')
JS_FILE = os.path.join(ROOT, 'static', 'js', 'receiving', 'codes.js')
RESULT_KEYS = ('ok', 'kind', 'gtin', 'serial', 'key', 'code', 'reason', 'message')
FUZZ_SEED = 20261003      # фиксированное зерно: случайные строки одни и те же при каждом запуске
FUZZ_CASES = 4000         # сколько случайных строк сравнивать с Node (~0,3 с)
NODE_TIMEOUT_SEC = 60


def _cases():
    with open(FIXTURE, encoding='utf-8') as f:
        return json.load(f)


def _expected(case):
    return {k: case[k] for k in RESULT_KEYS}


# ---------------------------------------------------------------- фикстура

def test_fixture_cases_match_exactly():
    mismatches = []
    for case in _cases():
        got = parse_code(case['raw'])
        if got != _expected(case):
            diff = {k: (case[k], got.get(k)) for k in RESULT_KEYS if got.get(k) != case[k]}
            mismatches.append((case['name'], diff))
    assert not mismatches, mismatches


def test_fixture_result_has_exactly_the_contract_keys():
    for case in _cases():
        assert tuple(parse_code(case['raw']).keys()) == RESULT_KEYS, case['name']


def test_fixture_barcode_for_iiko():
    for case in _cases():
        if case['ok']:
            assert barcode_for_iiko(case['gtin']) == case['barcode'], case['name']
        else:
            assert case['barcode'] is None, case['name']


def test_fixture_is_complete_and_consistent():
    cases = _cases()
    assert len(cases) >= 25
    names = [c['name'] for c in cases]
    assert len(names) == len(set(names)), 'имена случаев должны быть уникальны'
    for c in cases:
        assert set(c) == set(RESULT_KEYS) | {'name', 'raw', 'barcode'}, c['name']
        if c['ok']:
            # GTIN в фикстуре — всегда с верной контрольной цифрой.
            assert gtin_check_ok(c['gtin']), c['name']
            assert c['reason'] == '' and c['message'] == 'Принято', c['name']
        else:
            assert c['gtin'] is None and c['serial'] is None, c['name']
    reasons = {c['reason'] for c in cases}
    assert reasons >= {'', 'empty', 'too_long', 'sscc', 'bad_check_digit', 'unsupported'}
    kinds = {c['kind'] for c in cases}
    assert kinds == {'datamatrix', 'ean', 'sscc', 'unknown', 'empty'}

    raws = [c['raw'] for c in cases if isinstance(c['raw'], str)]
    ok_dm = [c for c in cases if c['ok'] and c['kind'] == 'datamatrix']
    assert any(rc.GS in c['raw'] for c in ok_dm), 'DataMatrix с GS'
    assert any(rc.GS not in c['raw'] and rc.GS_PICTURE not in c['raw']
               and not c['raw'].startswith('(') for c in ok_dm), 'DataMatrix без GS'
    assert any(c['raw'].startswith(']d2') for c in ok_dm), 'префикс ]d2'
    assert any(re.search('[\u0400-\u04ff]', c['raw']) for c in ok_dm), 'русская раскладка'
    assert any(rc.GS_PICTURE in c['raw'] for c in ok_dm), 'символ ␝'
    assert any(c['raw'].startswith('(01)') and '(21)' in c['raw'] for c in ok_dm), '(01)(21)'
    assert any(c['serial'] and c['serial'] + '93' in c['code'] and rc.GS not in c['code']
               for c in ok_dm), 'криптохвост без GS'
    ean_lengths = {len(c['code']) for c in cases if c['ok'] and c['kind'] == 'ean' and c['code'].isdigit()}
    assert ean_lengths >= {8, 12, 13, 14, 16}, 'EAN-8, UPC-A, EAN-13, GTIN-14, 01 + GTIN'
    assert any(r.startswith('http') for r in raws), 'QR со ссылкой'
    assert any(len(r) >= 100 and r.isalnum() for r in raws), 'ЕГАИС-подобная строка'
    assert any(c['raw'] is None for c in cases), 'null'
    assert any(isinstance(c['raw'], str) and c['raw'] and not c['raw'].strip() for c in cases), 'пробелы'


def test_normalized_code_parses_to_the_same_key():
    """Страница может прислать нормализованный code — сервер обязан получить тот же ключ."""
    for case in _cases():
        if not case['ok']:
            continue
        again = parse_code(case['code'])
        assert again['ok'], case['name']
        for k in ('kind', 'gtin', 'serial', 'key', 'code'):
            assert again[k] == case[k], (case['name'], k)


# ---------------------------------------------------------------- точечные правила

def test_gtin_check_digit():
    assert gtin_check_ok('04610093628430')
    assert gtin_check_ok('14610093628437')
    assert gtin_check_ok('00000046009999')
    assert gtin_check_ok('00036000291452')
    assert gtin_check_ok('00000000000000')   # формально верно: сумма 0, контрольная 0
    assert not gtin_check_ok('04610093628431')
    assert not gtin_check_ok('4610093628430')      # 13 цифр — не GTIN-14
    assert not gtin_check_ok('046100936284300')    # 15 цифр
    assert not gtin_check_ok('0461009362843A')
    assert not gtin_check_ok(' 04610093628430')
    assert not gtin_check_ok('\u0660\u0664\u0666\u0661\u0660\u0660\u0669\u0663\u0666\u0662\u0668\u0664\u0663\u0660')
    assert not gtin_check_ok('')
    assert not gtin_check_ok(None)
    assert not gtin_check_ok(4610093628430)


def test_every_single_digit_error_is_caught():
    """Mod 10 ловит любую ошибку в одной цифре — на этом держится «прочитан с ошибкой»."""
    base = '04610093628430'
    for pos in range(14):
        for d in '0123456789':
            if d == base[pos]:
                continue
            assert not gtin_check_ok(base[:pos] + d + base[pos + 1:]), (pos, d)


def test_barcode_for_iiko():
    assert barcode_for_iiko('04610093628430') == '4610093628430'      # EAN-13
    assert barcode_for_iiko('00000046009999') == '46009999'           # EAN-8
    assert barcode_for_iiko('00036000291452') == '0036000291452'      # UPC-A как EAN-13
    assert barcode_for_iiko('14610093628437') == '14610093628437'     # GTIN-14
    assert barcode_for_iiko('4610093628430') == '4610093628430'       # короче 14 — дополняется
    assert barcode_for_iiko('46009999') == '46009999'
    assert barcode_for_iiko(' 04610093628430\n') == '4610093628430'
    assert barcode_for_iiko(4610093628430) == '4610093628430'
    assert barcode_for_iiko('') == ''
    assert barcode_for_iiko(None) == ''
    assert barcode_for_iiko('ABC') == 'ABC'                           # не цифры — как есть
    assert barcode_for_iiko('046100936284301') == '046100936284301'   # длиннее 14 — как есть


def test_messages_match_spec():
    assert parse_code('4610093628430')['message'] == 'Принято'
    assert parse_code('')['message'] == 'Код не распознан — повторите'
    assert parse_code('https://x')['message'] == 'Код не распознан — повторите'
    assert parse_code('1' * (rc.MAX_CODE_LEN + 1))['message'] == 'Код не распознан — повторите'
    assert parse_code('4610093628431')['message'] == 'Код прочитан с ошибкой — повторите'
    assert parse_code('00146012340000000018')['message'] == 'Код короба или паллеты — отсканируйте бутылку'
    assert set(rc.MESSAGES) == {rc.REASON_EMPTY, rc.REASON_TOO_LONG, rc.REASON_SSCC,
                                rc.REASON_BAD_CHECK, rc.REASON_UNSUPPORTED}


def test_non_string_input_is_stringified():
    r = parse_code(4610093628430)
    assert r['ok'] and r['gtin'] == '04610093628430'


def test_dedup_keys():
    """Одна бутылка — один ключ при любом виде скана; EAN — ключ = GTIN."""
    same_bottle = [
        '010461009362843021GLTP9kqZn5QRt\x1d93dGVz',
        '010461009362843021GLTP9kqZn5QRt93dGVz',
        ']d2010461009362843021GLTP9kqZn5QRt\u241d93dGVz',
        '010461009362843021ПДЕЗ9лйЯт5ЙКе\x1d93вПМя',
        '(01)04610093628430(21)GLTP9kqZn5QRt(93)dGVz',
    ]
    keys = {parse_code(raw)['key'] for raw in same_bottle}
    assert keys == {'04610093628430|GLTP9kqZn5QRt'}
    other = parse_code('010461009362843021GLTP9kqZn5QRT\x1d93dGVz')   # другой регистр — другая бутылка
    assert other['key'] == '04610093628430|GLTP9kqZn5QRT'
    assert parse_code('4610093628430')['key'] == parse_code('0104610093628430')['key'] == '04610093628430'


def test_layout_map_covers_all_russian_letters_one_to_one():
    lower = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
    assert len(lower) == 33
    for ch in lower + lower.upper():
        assert ord(ch) in rc._RU_TO_EN, ch
    values = list(rc._RU_TO_EN.values())
    assert len(values) == len(set(values)), 'раскладка должна переводиться взаимно однозначно'
    assert all(len(v) == 1 and ord(v) < 128 for v in values)
    # Цифры не трогаются, перевод — только при наличии кириллицы.
    assert parse_code('ъв2' + '0104610093628430')['code'] == '0104610093628430'
    assert parse_code('0104610093628430.')['code'] == '0104610093628430.'


def test_max_len_counts_code_points_after_strip():
    limit = rc.MAX_CODE_LEN
    assert parse_code('A' * limit)['reason'] == 'unsupported'
    assert parse_code('A' * (limit + 1))['reason'] == 'too_long'
    assert parse_code('\n' + 'A' * limit + ' ')['reason'] == 'unsupported'
    long_raw = '\U0001D400' * (limit + 1)
    r = parse_code(long_raw)
    assert r['reason'] == 'too_long' and len(r['code']) == limit and len(r['key']) == rc.KEY_LEN


# ---------------------------------------------------------------- паритет с Node

_FUZZ_PIECES = (
    '0', '1', '2', '3', '4', '6', '9', '01', '21', '93', '00', '17',
    '04610093628430', '4610093628430', '0104610093628430', '010461009362843021',
    '46009999', '036000291452', '14610093628437', '00146012340000000018',
    '\x1d', '\u241d', ']d2', ']E0', ']Q3', ']', 'd', '(', ')', '(01)', '(21)', '(00)', '(93)',
    'A', 'z', 'Q', 'G', 'x', ' ', '\t', '\r\n', '+', '/', '.', ',', '?', '"', '&', ';', ':',
    'й', 'Ъ', 'ъ', 'в', 'П', 'ё', 'Ё', '№', 'я', 'Ю', 'Э',
    '\U0001D400', '\ud800', '\u0663', '\u00a0', 'GLTP9kqZn5QRt', 'dGVz', 'a1B2c3D',
)


def _fuzz_inputs():
    rnd = random.Random(FUZZ_SEED)
    out = []
    fixture_raws = [c['raw'] for c in _cases() if isinstance(c['raw'], str) and len(c['raw']) < 100]
    for _ in range(FUZZ_CASES):
        mode = rnd.random()
        if mode < 0.55:
            s = ''.join(rnd.choice(_FUZZ_PIECES) for _ in range(rnd.randint(0, 10)))
        elif mode < 0.9:
            # Мутации настоящих кодов: вставка, удаление, замена одного символа.
            s = list(rnd.choice(fixture_raws))
            for _ in range(rnd.randint(1, 3)):
                op = rnd.random()
                pos = rnd.randint(0, len(s))
                if op < 0.4:
                    s.insert(pos, rnd.choice(_FUZZ_PIECES))
                elif s and op < 0.7:
                    del s[min(pos, len(s) - 1)]
                elif s:
                    s[min(pos, len(s) - 1)] = rnd.choice(_FUZZ_PIECES)
            s = ''.join(s)
        else:
            # Около границы MAX_CODE_LEN, в том числе символы вне BMP.
            n = rc.MAX_CODE_LEN + rnd.randint(-3, 3)
            s = ''.join(rnd.choice(('A', '1', '\U0001D400', 'й')) for _ in range(n))
            if rnd.random() < 0.5:
                s = ' ' + s + '\n'
        out.append(s)
    digit_inputs = [''.join(rnd.choice('0123456789') for _ in range(rnd.randint(0, 16)))
                    for _ in range(500)]
    return out, digit_inputs


_NODE_SCRIPT = r"""
const rc = require(process.argv[1]);
let buf = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (d) => { buf += d; });
process.stdin.on('end', () => {
    const data = JSON.parse(buf);
    process.stdout.write(JSON.stringify({
        parse: data.codes.map((s) => rc.parseCode(s)),
        check: data.digits.map((s) => rc.gtinCheckOk(s)),
        barcode: data.digits.map((s) => rc.barcodeForIiko(s)),
    }));
});
"""


def _node():
    return shutil.which('node')


def test_parity_with_node_on_random_strings():
    node = _node()
    if not node:
        pytest.skip('node не найден — паритет на случайных строках не проверить')
    codes, digits = _fuzz_inputs()
    payload = json.dumps({'codes': codes, 'digits': digits}, ensure_ascii=True)
    proc = subprocess.run([node, '-e', _NODE_SCRIPT, JS_FILE], input=payload,
                          capture_output=True, text=True, encoding='utf-8',
                          timeout=NODE_TIMEOUT_SEC)
    assert proc.returncode == 0, proc.stderr
    js = json.loads(proc.stdout)
    mismatches = []
    for raw, got in zip(codes, js['parse']):
        exp = parse_code(raw)
        if got != exp:
            mismatches.append((raw, exp, got))
    assert not mismatches, mismatches[:5]
    assert js['check'] == [gtin_check_ok(s) for s in digits]
    assert js['barcode'] == [barcode_for_iiko(s) for s in digits]
    # Случайные строки действительно задели все ветки.
    reasons = {parse_code(s)['reason'] for s in codes}
    assert reasons == {'', 'empty', 'too_long', 'sscc', 'bad_check_digit', 'unsupported'}
    kinds = {parse_code(s)['kind'] for s in codes}
    assert kinds == {'datamatrix', 'ean', 'sscc', 'unknown', 'empty'}


def test_js_port_syntax():
    node = _node()
    if not node:
        pytest.skip('node не найден')
    proc = subprocess.run([node, '--check', JS_FILE], capture_output=True, text=True,
                          timeout=NODE_TIMEOUT_SEC)
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------- модуль

def test_module_is_flask_free():
    code = ('import sys; import core.receiving_codes; '
            'bad = [m for m in ("flask", "requests", "sqlite3") if m in sys.modules]; '
            'print(",".join(bad))')
    proc = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True,
                          text=True, timeout=NODE_TIMEOUT_SEC)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ''


def test_py310_compatible_syntax():
    with open(rc.__file__, encoding='utf-8') as f:
        ast.parse(f.read(), feature_version=(3, 10))
    with open(__file__, encoding='utf-8') as f:
        ast.parse(f.read(), feature_version=(3, 10))


def test_no_emoji_in_sources():
    emoji = re.compile('[\U0001F300-\U0001FAFF\u2600-\u27bf\u2b50\u2705]')
    for path in (rc.__file__, JS_FILE, FIXTURE, __file__, os.path.join(ROOT, 'tests', 'test_receiving_codes.mjs')):
        with open(path, encoding='utf-8') as f:
            assert not emoji.search(f.read()), path


if __name__ == '__main__':
    import inspect
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and inspect.isfunction(fn):
            try:
                fn()
                print(f'ok   {name}')
            except pytest.skip.Exception as e:
                print(f'skip {name}: {e}')
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f'FAIL {name}: {e!r}')
    sys.exit(1 if failed else 0)
