"""
Тесты названий из Честного знака для приёмки на РЦ: команда `chz.py product-info`
(бар-ПК) и core/receiving_chz.py (сервер).

Self-runnable: `py -3 tests/test_receiving_chz.py` (запускает pytest по файлу).

Сеть, SSH и реальный data/ не трогаются: chz.py импортируется как модуль
(в нём только stdlib) с подменёнными load_token/make_request, транспорт SSH —
функция run(cmd, timeout), кэш — фейковый store с get_chz_products/save_chz_products,
пути лока и chz_stock.json — во временной папке (receiving_chz.set_paths).

Что проверяется:
- chz.py: разбор GTIN из аргументов (запятая/пробел, zfill, повторы, мусор, лимит 1000),
  ответ последней строкой-маркером только из ASCII, нет токена / нет GTIN / HTTP-сбой /
  сеть -> ok:false, пакеты по 1000, строка в справке, справка на незнакомую команду;
- сквозной путь: вывод настоящего chz.py с кракозябрами выше маркера разбирается сервером;
- parse_output: побеждает последняя строка с маркером, CRLF, маркер в середине строки,
  устаревший chz.py (справка без маркера) -> ChzError с подсказкой push, ok:false -> ChzError;
- fetch_product_info: пакеты по CHUNK, вид команды и её длина, таймаут, транспорт по
  умолчанию (remote_exec.run_cmd), ChzUnavailable без REMOTE_PASS, тексты сбоев без
  адреса бар-ПК и пароля, частичный результат до сбоя;
- normalize_item: name/fullName, объём из volumeWeight/coreVolume;
- lookup: порядок кэш -> chz_stock.json -> product/info, что сохраняется в кэш,
  срок «в ЧЗ нет» (NEGATIVE_TTL_DAYS), без REMOTE_PASS — без SSH и без ошибок,
  при ошибке «в ЧЗ нет» не запоминается, лок занят -> ошибка, сбои кэша не роняют поиск;
- CLI python -m core.receiving_chz; синтаксис Python 3.10; нет эмодзи.
"""
import ast
import json
import os
import sys
import time
from datetime import timedelta

import portalocker
import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, 'chz_test'))

import chz  # noqa: E402  (chz_test/chz.py: только stdlib, импорт на Linux безопасен)
import remote_exec  # noqa: E402
from core import msk_time  # noqa: E402
from core import receiving_chz as rc  # noqa: E402

G1 = '04610093628430'
G2 = '04607001771234'
G3 = '04600000000017'
G4 = '05410228203582'

# Ответ product/info на G1 — как в ЧЗ (поля из документации /api/v4/true-api/product/info).
RAW_G1 = {
    'gtin': G1,
    'name': 'Пиво светлое FH Helles «ФХ Хеллес»',
    'brand': 'Без товарного знака',
    'fullName': 'Пиво светлое пастеризованное фильтрованное FH Helles «ФХ Хеллес», 4,5%',
    'productGroup': 'beer',
    'productGroupId': 15,
    'volumeWeight': '',
    'coreVolume': 450,
    'packageType': 'UNIT',
    'goodStatus': 'published',
}
RAW_G2 = {'gtin': G2, 'name': '', 'fullName': 'Сидр яблочный  полусладкий', 'brand': 'Кидди',
          'productGroup': 'beer', 'volumeWeight': '0.5', 'packageType': 'UNIT'}
CATALOG = {G1: RAW_G1, G2: RAW_G2}

# Так приходит кириллица из консоли бар-ПК: cp1251 прочитан как cp866 (remote_exec.run_cmd).
MOJIBAKE = 'Получаю новый токен...'.encode('cp1251').decode('cp866')
HOST = '192.0.2.10'           # адрес из документационного диапазона RFC 5737
PASSWORD = 'bar-secret-pass'


# ----- общие фикстуры и фейки -------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path):
    """Лок и chz_stock.json — во временной папке: реальный data/ тесты не трогают."""
    rc.set_paths(lock=tmp_path / 'locks' / 'receiving_chz.lock',
                 stock_file=tmp_path / 'chz_stock.json',
                 nightly_lock=tmp_path / 'debug' / 'refresh.lock')
    yield
    rc.set_paths()


class FakeStore:
    """Кэш chz_products в памяти: тот же контракт, что у core.receiving_store."""

    def __init__(self, rows=None):
        self.rows = {g: dict(r) for g, r in (rows or {}).items()}
        self.saved = []
        self.get_calls = []

    def get_chz_products(self, gtins):
        self.get_calls.append(list(gtins))
        return {g: dict(self.rows[g]) for g in gtins if g in self.rows}

    def save_chz_products(self, rows):
        for row in rows:
            self.saved.append(dict(row))
            self.rows[row['gtin']] = dict(row)


def _sentinel_line(ok=True, items=None, missing=None, error=''):
    payload = {'ok': ok, 'version': 1, 'items': items or {}, 'missing': missing or [], 'error': error}
    return rc.SENTINEL + json.dumps(payload, ensure_ascii=True)


def _gtins_of(cmd):
    """GTIN из команды `... chz.py product-info g1,g2,...`."""
    return cmd.rsplit(' ', 1)[1].split(',')


def _fake_run(catalog=None, calls=None, fail_on_call=None, fail_with=None):
    """Транспорт как бар-ПК со свежим chz.py: кракозябры, затем строка-маркер, CRLF."""
    catalog = CATALOG if catalog is None else catalog

    def run(cmd, timeout):
        if calls is not None:
            calls.append((cmd, timeout))
        if fail_on_call is not None and calls is not None and len(calls) == fail_on_call:
            if isinstance(fail_with, BaseException):
                raise fail_with
            return fail_with
        gtins = _gtins_of(cmd)
        items = {g: catalog[g] for g in gtins if g in catalog}
        missing = [g for g in gtins if g not in catalog]
        return '\r\n'.join([MOJIBAKE, '[auth] ok', _sentinel_line(True, items, missing), ''])
    return run


def _configured(monkeypatch):
    monkeypatch.setenv('REMOTE_PASS', PASSWORD)


def _iso(delta=timedelta(0)):
    return (msk_time.now() + delta).isoformat(timespec='seconds')


def _negative_row(gtin, fetched_at):
    return {'gtin': gtin, 'found': 0, 'name': '', 'brand': '', 'full_name': '', 'product_group': '',
            'volume': '', 'package_type': '', 'raw': {}, 'source': 'product_info', 'fetched_at': fetched_at}


def _write_stock(tmp_path, items):
    path = tmp_path / 'chz_stock.json'
    path.write_text(json.dumps(items, ensure_ascii=False), encoding='utf-8')
    return path


# ----- chz.py: команда product-info -------------------------------------------

def test_chz_parse_gtin_args_commas_spaces_junk_and_duplicates():
    args = ['4610093628430,04607001771234', ' 04610093628430 ', 'abc,123456789012345',
            '12 34', '', '٤٦١٠', '04600000000017,,']
    assert chz.parse_gtin_args(args) == [G1, G2, '00000000000012', '00000000000034', G3]


def test_chz_parse_gtin_args_limit_1000():
    args = [','.join(str(10000000 + i) for i in range(1500))]
    gtins = chz.parse_gtin_args(args)
    assert len(gtins) == chz.PRODUCT_INFO_MAX_GTINS == 1000
    assert gtins[0] == '00000010000000' and len(set(gtins)) == 1000


def _run_chz_main(monkeypatch, capsys, argv, token='tok-123', responses=None):
    """Запустить chz.main() как на бар-ПК; -> (stdout, вызовы make_request, payload)."""
    calls = []
    responses = list(responses or [])

    def fake_make_request(url, method='GET', data=None, headers=None, raw=False, timeout=60):
        calls.append({'url': url, 'method': method, 'data': data, 'headers': dict(headers or {})})
        if responses:
            return responses.pop(0)
        gtins = data['gtins']
        return 200, {'results': [CATALOG[g] for g in gtins if g in CATALOG], 'total': 0}

    def fake_load_token():
        print('\n  Получаю новый токен...')
        return token

    monkeypatch.setattr(chz, 'make_request', fake_make_request)
    monkeypatch.setattr(chz, 'load_token', fake_load_token)
    monkeypatch.setattr(sys, 'argv', ['chz.py'] + list(argv))
    chz.main()
    out = capsys.readouterr().out
    last = out.rstrip('\n').splitlines()[-1]
    assert last.startswith(chz.CHZ_JSON_SENTINEL)
    payload = json.loads(last[len(chz.CHZ_JSON_SENTINEL):])
    return out, calls, payload


def test_chz_product_info_prints_ascii_sentinel_last(monkeypatch, capsys):
    out, calls, payload = _run_chz_main(monkeypatch, capsys,
                                        ['product-info', '4610093628430,' + G2, G3])
    last = out.rstrip('\n').splitlines()[-1]
    assert last.isascii()                       # консоль бар-ПК в cp1251: только ASCII
    assert payload['ok'] is True and payload['version'] == 1 and payload['error'] == ''
    assert set(payload['items']) == {G1, G2}
    assert payload['items'][G1] == RAW_G1        # объект results[] целиком, как есть
    assert payload['missing'] == [G3]
    assert len(calls) == 1
    call = calls[0]
    assert call['url'] == chz.CHZ_BASE_URL_V4 + '/product/info'
    assert call['method'] == 'POST'
    assert call['data'] == {'gtins': [G1, G2, G3], 'rdInfo': False}
    assert call['headers']['Authorization'] == 'Bearer tok-123'


def test_chz_product_info_no_token(monkeypatch, capsys):
    _out, calls, payload = _run_chz_main(monkeypatch, capsys, ['product-info', G1], token=None)
    assert payload['ok'] is False and payload['error'] == 'no_token'
    assert payload['items'] == {} and payload['missing'] == []
    assert calls == []


def test_chz_product_info_no_gtins_does_not_touch_token(monkeypatch, capsys):
    monkeypatch.setattr(chz, 'load_token', lambda: pytest.fail('токен не нужен без GTIN'))
    monkeypatch.setattr(sys, 'argv', ['chz.py', 'product-info', 'abc'])
    chz.main()
    last = capsys.readouterr().out.rstrip('\n').splitlines()[-1]
    payload = json.loads(last[len(chz.CHZ_JSON_SENTINEL):])
    assert payload == {'ok': False, 'version': 1, 'items': {}, 'missing': [], 'error': 'no_gtins'}


def test_chz_product_info_http_error_has_no_missing(monkeypatch, capsys):
    _out, _calls, payload = _run_chz_main(monkeypatch, capsys, ['product-info', G1, G3],
                                          responses=[(500, {'_raw': 'Internal'})])
    assert payload['ok'] is False and payload['error'] == 'HTTP 500'
    assert payload['missing'] == []              # при сбое «нет в ЧЗ» неизвестно


def test_chz_product_info_network_error(monkeypatch, capsys):
    _out, _calls, payload = _run_chz_main(monkeypatch, capsys, ['product-info', G1],
                                          responses=[(None, 'Попытка установить соединение была безуспешной')])
    assert payload['ok'] is False
    assert payload['error'].startswith('network: ')
    assert 'Попытка' in payload['error']         # кириллица доезжает через \\u-экранирование


def test_chz_fetch_product_info_chunks_by_1000(monkeypatch):
    sizes = []

    def fake_make_request(url, method='GET', data=None, headers=None, raw=False, timeout=60):
        sizes.append(len(data['gtins']))
        return 200, {'results': [{'gtin': data['gtins'][0], 'name': 'x'}, {'name': 'без gtin'}, 'мусор']}

    monkeypatch.setattr(chz, 'make_request', fake_make_request)
    gtins = [str(20000000 + i) for i in range(2500)]
    status, items, error = chz.fetch_product_info(gtins, 'tok')
    assert sizes == [1000, 1000, 500]
    assert status == 200 and error == ''
    assert sorted(items) == ['00000020000000', '00000020001000', '00000020002000']


def test_chz_fetch_product_info_stops_on_first_failed_chunk(monkeypatch):
    responses = [(200, {'results': [{'gtin': G1, 'name': 'a'}]}), (401, {'error_message': 'expired'})]
    calls = []

    def fake_make_request(url, method='GET', data=None, headers=None, raw=False, timeout=60):
        calls.append(1)
        return responses.pop(0)

    monkeypatch.setattr(chz, 'make_request', fake_make_request)
    status, items, error = chz.fetch_product_info([G1] + [str(30000000 + i) for i in range(1500)], 'tok')
    assert (status, error) == (401, 'HTTP 401')
    assert list(items) == [G1] and len(calls) == 2


def test_chz_help_lists_product_info_and_unknown_command_prints_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['chz.py', 'no-such-command'])
    chz.main()
    out = capsys.readouterr().out
    assert 'python chz.py product-info' in out
    assert chz.CHZ_JSON_SENTINEL not in out      # так выглядит «старый chz.py» для сервера


def test_end_to_end_real_chz_output_parsed_by_server(monkeypatch, capsys):
    """Вывод настоящего chz.py, прошедший cp1251 -> cp866, сервер разбирает без потерь."""
    out, _calls, _payload = _run_chz_main(monkeypatch, capsys, ['product-info', G1 + ',' + G3])
    over_ssh = out.encode('cp1251').decode('cp866').replace('\n', '\r\n')
    parsed = rc.parse_output(over_ssh)
    assert parsed == {'items': {G1: RAW_G1}, 'missing': [G3]}
    assert rc.normalize_item(parsed['items'][G1])['name'] == RAW_G1['name']


# ----- сервер: разбор ответа ---------------------------------------------------

def test_parse_output_last_sentinel_wins_and_mojibake_skipped():
    stale = _sentinel_line(True, {G2: RAW_G2}, [])
    fresh = _sentinel_line(True, {G1: RAW_G1}, [G3])
    stdout = '\r\n'.join([MOJIBAKE, stale, '├Ёєяяр: beer', fresh, MOJIBAKE, ''])
    assert rc.parse_output(stdout) == {'items': {G1: RAW_G1}, 'missing': [G3]}


def test_parse_output_sentinel_mid_line_and_bytes():
    stdout = ('  [auth] без перевода строки' + _sentinel_line(True, {G1: RAW_G1}, [])).encode('utf-8')
    assert rc.parse_output(stdout)['items'] == {G1: RAW_G1}


def test_parse_output_normalizes_keys_and_drops_junk():
    stdout = _sentinel_line(True, {'4610093628430': RAW_G1, 'junk': {'x': 1}, G2: 'не объект'},
                            ['4600000000017', 'abc', '4610093628430'])
    parsed = rc.parse_output(stdout)
    assert parsed == {'items': {G1: RAW_G1}, 'missing': [G3]}


def test_parse_output_outdated_chz_help_text():
    """Старый chz.py: незнакомая команда -> справка (cp1251 как cp866), код 0, маркера нет."""
    help_text = '\nИспользование:\n  python chz.py token  — получить/обновить токен\n'
    stdout = help_text.encode('cp1251').decode('cp866')
    with pytest.raises(rc.ChzError) as info:
        rc.parse_output(stdout)
    message = str(info.value)
    assert 'устарел' in message
    assert rc.PUSH_HINT in message
    assert 'remote_exec.py push chz_test/chz.py C:\\chz_test' in message


def test_parse_output_empty_stdout_is_outdated():
    with pytest.raises(rc.ChzError, match='устарел'):
        rc.parse_output('')


def test_parse_output_ok_false_errors():
    with pytest.raises(rc.ChzError) as info:
        rc.parse_output(_sentinel_line(False, error='no_token'))
    assert 'Рутокен' in str(info.value)
    with pytest.raises(rc.ChzError, match='HTTP 500'):
        rc.parse_output(_sentinel_line(False, error='HTTP 500'))
    with pytest.raises(rc.ChzError) as info:
        rc.parse_output(_sentinel_line(False, error='x' * 1000))
    assert len(str(info.value)) < 300            # недоверенная строка с бар-ПК обрезана


def test_parse_output_broken_payloads():
    for bad in (rc.SENTINEL + '{"ok": true, "items": {', rc.SENTINEL + '[1, 2]',
                rc.SENTINEL + '{"ok": true, "items": [], "missing": []}',
                rc.SENTINEL + '{"ok": true, "items": {}}'):
        with pytest.raises(rc.ChzError, match='не разобран'):
            rc.parse_output(bad)


# ----- сервер: fetch_product_info ----------------------------------------------

def test_fetch_product_info_chunks_at_chunk_and_builds_command():
    calls = []
    gtins = [str(40000000 + i) for i in range(2 * rc.CHUNK + 5)]
    catalog = {gtins[0].zfill(14): {'gtin': gtins[0].zfill(14), 'name': 'a'}}
    result = rc.fetch_product_info(gtins + ['мусор', gtins[0]], run=_fake_run(catalog, calls))
    assert [len(_gtins_of(cmd)) for cmd, _ in calls] == [rc.CHUNK, rc.CHUNK, 5]
    assert all(timeout == rc.REMOTE_TIMEOUT for _, timeout in calls)
    cmd = calls[0][0]
    assert cmd.startswith('cd /d ' + remote_exec.REMOTE_CHZ_DIR + ' && "' + remote_exec.REMOTE_PYTHON
                          + '" chz.py product-info ')
    assert len(cmd) < 8191                        # лимит строки cmd.exe
    assert _gtins_of(calls[2][0])[-1] == gtins[-1].zfill(14)
    assert list(result['items']) == [gtins[0].zfill(14)]
    assert len(result['missing']) == 2 * rc.CHUNK + 4
    assert result['missing'][0] == gtins[1].zfill(14)


def test_fetch_product_info_empty_input_does_not_run():
    assert rc.fetch_product_info(['', 'abc'], run=lambda cmd, t: pytest.fail('не нужен')) == \
        {'items': {}, 'missing': []}


def test_fetch_product_info_missing_only_what_chz_reported():
    """GTIN, о котором ответ промолчал, — не «в ЧЗ нет» (его не запоминаем на неделю)."""
    def run(cmd, timeout):
        return _sentinel_line(True, {G1: RAW_G1}, [G2])
    assert rc.fetch_product_info([G1, G2, G3], run=run) == {'items': {G1: RAW_G1}, 'missing': [G2]}


def test_fetch_product_info_unavailable_without_remote_pass(monkeypatch):
    monkeypatch.setenv('REMOTE_PASS', '')
    monkeypatch.setattr(remote_exec, 'run_cmd', lambda *a, **k: pytest.fail('SSH без пароля'))
    assert rc.remote_configured() is False
    with pytest.raises(rc.ChzUnavailable):
        rc.fetch_product_info([G1])


def test_fetch_product_info_unavailable_when_remote_exec_imported_without_pass(monkeypatch):
    _configured(monkeypatch)
    monkeypatch.setattr(remote_exec, 'REMOTE_PASS', '')
    monkeypatch.setattr(remote_exec, 'run_cmd', lambda *a, **k: pytest.fail('connect упал бы'))
    with pytest.raises(rc.ChzUnavailable):
        rc.fetch_product_info([G1])


def test_fetch_product_info_default_transport_is_run_cmd(monkeypatch):
    _configured(monkeypatch)
    monkeypatch.setattr(remote_exec, 'REMOTE_PASS', PASSWORD)
    seen = []

    def fake_run_cmd(cmd, verbose=True, timeout=None):
        seen.append({'cmd': cmd, 'verbose': verbose, 'timeout': timeout})
        return _sentinel_line(True, {G1: RAW_G1}, []), ''

    monkeypatch.setattr(remote_exec, 'run_cmd', fake_run_cmd)
    assert rc.fetch_product_info([G1])['items'] == {G1: RAW_G1}
    assert len(seen) == 1
    assert seen[0]['verbose'] is False                     # из Flask не пишем в sys.stdout.buffer
    assert seen[0]['timeout'] == rc.REMOTE_TIMEOUT         # без таймаута run_cmd ждёт вечно
    assert seen[0]['cmd'].endswith('chz.py product-info ' + G1)


@pytest.mark.parametrize('error, expected', [
    (TimeoutError("Команда превысила таймаут 180с: 'cd /d C:\\chz_test'"), 'не ответил за 180 с'),
    (RuntimeError("Remote command failed (exit 1): 'cd /d C:\\chz_test && ...'\nSTDERR: Traceback "
                  "... password=" + PASSWORD), 'завершился с ошибкой (код 1)'),
    (OSError('[Errno 113] No route to host: ' + HOST), 'недоступен по SSH'),
    (ValueError('странное ' + HOST), 'Сбой связи с бар-ПК: ValueError'),
])
def test_fetch_product_info_errors_hide_host_and_password(error, expected):
    def run(cmd, timeout):
        raise error
    with pytest.raises(rc.ChzError) as info:
        rc.fetch_product_info([G1], run=run)
    message = str(info.value)
    assert expected in message
    assert HOST not in message and PASSWORD not in message and 'chz_test' not in message


def test_fetch_product_info_auth_error_from_paramiko():
    import paramiko

    def run(cmd, timeout):
        raise paramiko.AuthenticationException('Authentication failed for ' + HOST)
    with pytest.raises(rc.ChzError) as info:
        rc.fetch_product_info([G1], run=run)
    assert 'не пустил по SSH' in str(info.value) and HOST not in str(info.value)


def test_fetch_product_info_partial_items_on_later_chunk_failure():
    calls = []
    gtins = [G1] + [str(50000000 + i) for i in range(rc.CHUNK)]
    run = _fake_run(CATALOG, calls, fail_on_call=2, fail_with='help text, no sentinel')
    with pytest.raises(rc.ChzError) as info:
        rc.fetch_product_info(gtins, run=run)
    assert 'устарел' in str(info.value)
    assert info.value.items == {G1: RAW_G1}      # первый пакет прошёл — его не теряем


# ----- normalize_item ----------------------------------------------------------

def test_normalize_item_fields_and_fallbacks():
    assert rc.normalize_item(RAW_G1) == {
        'name': 'Пиво светлое FH Helles «ФХ Хеллес»', 'brand': 'Без товарного знака',
        'full_name': RAW_G1['fullName'], 'product_group': 'beer', 'volume': '450 мл',
        'package_type': 'UNIT', 'level': '', 'main_gtin': '', 'pack_units': ''}
    info = rc.normalize_item(RAW_G2)
    assert info['name'] == 'Сидр яблочный полусладкий'      # name пуст -> fullName, пробелы схлопнуты
    assert info['volume'] == '0.5'                           # volumeWeight — как есть
    empty = {'name': '', 'brand': '', 'full_name': '', 'product_group': '', 'volume': '', 'package_type': '',
             'level': '', 'main_gtin': '', 'pack_units': ''}
    assert rc.normalize_item(None) == empty
    assert rc.normalize_item({'name': None, 'brand': {'x': 1}}) == empty


def test_normalize_item_group_pack():
    """Групповая упаковка (мультипак): GTIN единицы и сколько их — по спецификации product/info."""
    pack = rc.normalize_item({'name': 'Жигули 6 банок', 'level': 'inner-pack', 'mainGtin': 4610093628430,
                              'multiplier': 6})
    assert (pack['level'], pack['main_gtin'], pack['pack_units']) == ('inner-pack', '04610093628430', '6')
    unit = rc.normalize_item({'name': 'Жигули', 'level': 'trade-unit', 'mainGtin': 4610093628430,
                              'multiplier': 1})
    assert (unit['level'], unit['main_gtin'], unit['pack_units']) == ('trade-unit', '', '')
    odd = rc.normalize_item({'level': 'inner-pack', 'mainGtin': 'abc', 'multiplier': 'x'})
    assert (odd['main_gtin'], odd['pack_units']) == ('', '')
    cached = rc._cache_info({'name': 'Жигули 6 банок', 'raw': {'level': 'inner-pack',
                                                              'mainGtin': '4610093628430', 'multiplier': 6}})
    assert cached['main_gtin'] == '04610093628430' and cached['pack_units'] == '6'


@pytest.mark.parametrize('raw, volume', [
    ({'volumeWeight': ' 0.45 ', 'coreVolume': 450}, '0.45'),
    ({'volumeWeight': 0.33}, '0.33'),
    ({'volumeWeight': 0, 'coreVolume': 330}, '330 мл'),
    ({'volumeWeight': '', 'coreVolume': '500'}, '500 мл'),
    ({'coreVolume': 450.0}, '450 мл'),
    ({'coreVolume': '0,5 л'}, '0,5 л'),
    ({'coreVolume': 0}, ''),
    ({'coreVolume': '0'}, ''),
    ({'coreVolume': True}, ''),
    ({}, ''),
])
def test_normalize_item_volume(raw, volume):
    assert rc.normalize_item(raw)['volume'] == volume


# ----- lookup ------------------------------------------------------------------

def test_lookup_order_cache_then_stock_then_remote(monkeypatch, tmp_path):
    _configured(monkeypatch)
    cached_row = {'gtin': G4, 'found': 1, 'name': 'Кэш', 'brand': 'Б', 'full_name': '', 'product_group': 'beer',
                  'volume': '', 'package_type': '', 'raw': {}, 'source': 'product_info',
                  'fetched_at': '2026-09-01T10:00:00+03:00'}
    store = FakeStore({G4: cached_row})
    _write_stock(tmp_path, [
        {'gtin': G2, 'name': 'Из остатков', 'brand': 'Бренд', 'count': 3, 'product_group': 'BEER',
         'batches': [], 'by_kpp': []},
        {'gtin': G4, 'name': 'Не должно победить кэш', 'brand': '', 'product_group': 'BEER'},
    ])
    calls = []
    result = rc.lookup([G1, G2, G3, G4, G1], store=store, run=_fake_run(CATALOG, calls))

    assert store.get_calls == [[G1, G2, G3, G4]]
    assert [_gtins_of(cmd) for cmd, _ in calls] == [[G1, G3]]     # на бар-ПК — только остаток
    items = result['items']
    assert items[G4]['source'] == 'cache' and items[G4]['name'] == 'Кэш'
    assert items[G4]['fetched_at'] == '2026-09-01T10:00:00+03:00'
    assert items[G2]['source'] == 'stock' and items[G2]['name'] == 'Из остатков'
    assert items[G2]['product_group'] == 'BEER' and items[G2]['volume'] == ''
    assert items[G1]['source'] == 'product_info' and items[G1]['volume'] == '450 мл'
    assert set(items[G1]) == {'name', 'brand', 'full_name', 'product_group', 'volume', 'package_type',
                              'level', 'main_gtin', 'pack_units', 'source', 'fetched_at'}
    assert result['missing'] == [G3]
    assert result['errors'] == [] and result['remote_used'] is True

    saved = {row['gtin']: row for row in store.saved}
    assert set(saved) == {G1, G2, G3}
    assert saved[G2]['found'] == 1 and saved[G2]['source'] == 'stock'
    assert saved[G2]['raw'] == {'gtin': G2, 'name': 'Из остатков', 'brand': 'Бренд', 'product_group': 'BEER'}
    assert saved[G1]['found'] == 1 and saved[G1]['source'] == 'product_info'
    assert saved[G1]['raw'] == RAW_G1 and saved[G1]['name'] == RAW_G1['name']
    assert saved[G3]['found'] == 0 and saved[G3]['source'] == 'product_info' and saved[G3]['raw'] == {}
    for row in saved.values():
        assert set(row) == {'gtin', 'found', 'name', 'brand', 'full_name', 'product_group', 'volume',
                            'package_type', 'raw', 'source', 'fetched_at'}
        assert row['fetched_at'].endswith('+03:00')


def test_lookup_second_call_served_from_cache(monkeypatch):
    _configured(monkeypatch)
    store = FakeStore()
    calls = []
    rc.lookup([G1, G3], store=store, run=_fake_run(CATALOG, calls))
    again = rc.lookup([G1, G3], store=store, run=_fake_run(CATALOG, calls))
    assert len(calls) == 1                                  # G1 из кэша, G3 — «нет» моложе недели
    assert again['items'][G1]['source'] == 'cache'
    assert again['missing'] == [G3] and again['remote_used'] is False


def test_lookup_negative_ttl(monkeypatch):
    _configured(monkeypatch)
    ttl = rc.NEGATIVE_TTL_DAYS
    store = FakeStore({
        G1: _negative_row(G1, _iso(-timedelta(days=ttl + 1))),     # старое «нет» — переспросить
        G2: _negative_row(G2, _iso(-timedelta(days=ttl - 1))),     # свежее «нет» — не спрашивать
        G3: _negative_row(G3, 'не дата'),                          # битая метка — переспросить
        G4: _negative_row(G4, _iso(timedelta(days=30))),           # метка из будущего — переспросить
    })
    calls = []
    result = rc.lookup([G1, G2, G3, G4], store=store, run=_fake_run(CATALOG, calls))
    assert [_gtins_of(cmd) for cmd, _ in calls] == [[G1, G3, G4]]
    assert result['items'][G1]['source'] == 'product_info'
    assert result['missing'] == [G2, G3, G4]
    assert store.rows[G1]['found'] == 1
    assert {row['gtin'] for row in store.saved} == {G1, G3, G4}   # свежее «нет» не перезаписано


def test_lookup_fresh_negative_still_checks_stock(monkeypatch, tmp_path):
    _configured(monkeypatch)
    store = FakeStore({G2: _negative_row(G2, _iso(-timedelta(days=1)))})
    _write_stock(tmp_path, [{'gtin': int(G2), 'name': 'Появилось в остатках', 'brand': '', 'product_group': 'beer'}])
    result = rc.lookup([G2], store=store, run=lambda cmd, t: pytest.fail('свежее «нет» не переспрашиваем'))
    assert result['items'][G2]['source'] == 'stock'
    assert store.rows[G2]['found'] == 1


def test_lookup_without_remote_pass_is_silent(monkeypatch):
    monkeypatch.setenv('REMOTE_PASS', '')
    store = FakeStore()
    result = rc.lookup([G1, G3], store=store, run=lambda cmd, t: pytest.fail('без REMOTE_PASS — без SSH'))
    assert result == {'items': {}, 'missing': [G1, G3], 'errors': [], 'remote_used': False}
    assert store.saved == []


def test_lookup_remote_false_uses_only_local_sources(monkeypatch, tmp_path):
    _configured(monkeypatch)
    _write_stock(tmp_path, [{'gtin': G2, 'name': 'Из остатков', 'brand': '', 'product_group': 'beer'}])
    result = rc.lookup([G1, G2], remote=False, store=FakeStore(),
                       run=lambda cmd, t: pytest.fail('remote=False'))
    assert list(result['items']) == [G2] and result['missing'] == [G1]
    assert result['remote_used'] is False


def test_lookup_chz_unavailable_from_transport_is_silent(monkeypatch):
    _configured(monkeypatch)

    def run(cmd, timeout):
        raise rc.ChzUnavailable('нет пароля')
    store = FakeStore()
    result = rc.lookup([G1], store=store, run=run)
    assert result == {'items': {}, 'missing': [G1], 'errors': [], 'remote_used': False}
    assert store.saved == []


def test_lookup_error_does_not_save_negatives(monkeypatch):
    _configured(monkeypatch)
    store = FakeStore()
    result = rc.lookup([G1, G3], store=store, run=lambda cmd, t: 'Использование: python chz.py token')
    assert result['missing'] == [G1, G3]
    assert len(result['errors']) == 1 and 'устарел' in result['errors'][0]
    assert result['remote_used'] is True
    assert store.saved == []
    # Следующий раз — снова на бар-ПК (отрицательный ответ не запомнен)
    calls = []
    rc.lookup([G1, G3], store=store, run=_fake_run(CATALOG, calls))
    assert len(calls) == 1


def test_lookup_ok_false_goes_to_errors(monkeypatch):
    _configured(monkeypatch)
    result = rc.lookup([G1], store=FakeStore(), run=lambda cmd, t: _sentinel_line(False, error='no_token'))
    assert result['missing'] == [G1] and 'Рутокен' in result['errors'][0]


def test_lookup_partial_results_saved_but_no_negatives(monkeypatch):
    _configured(monkeypatch)
    store = FakeStore()
    calls = []
    filler = [str(60000000 + i).zfill(14) for i in range(rc.CHUNK)]
    run = _fake_run(CATALOG, calls, fail_on_call=2, fail_with=TimeoutError('timeout ' + HOST))
    result = rc.lookup([G1, G3] + filler[:-2] + [G2], store=store, run=run)
    assert len(calls) == 2
    assert list(result['items']) == [G1]
    assert G3 in result['missing'] and G2 in result['missing']
    assert result['errors'] == ['Бар-ПК не ответил за 180 с']
    assert [(row['gtin'], row['found']) for row in store.saved] == [(G1, 1)]


def test_lookup_lock_busy_reports_error(monkeypatch, tmp_path):
    _configured(monkeypatch)
    monkeypatch.setattr(rc, 'LOCK_WAIT_SEC', 0.3)
    lock_file = tmp_path / 'locks' / 'receiving_chz.lock'
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    holder = portalocker.Lock(str(lock_file), timeout=0, fail_when_locked=True)
    holder.acquire()
    try:
        result = rc.lookup([G1], store=FakeStore(), run=lambda cmd, t: pytest.fail('лок занят'))
    finally:
        holder.release()
    assert result['missing'] == [G1] and result['remote_used'] is False
    assert 'занят' in result['errors'][0]


def test_lookup_lock_is_taken_at_override_path_and_released(monkeypatch, tmp_path):
    _configured(monkeypatch)
    lock_file = tmp_path / 'locks' / 'receiving_chz.lock'
    assert rc.lock_path() == str(lock_file)
    seen = []

    def run(cmd, timeout):
        probe = portalocker.Lock(str(lock_file), timeout=0, fail_when_locked=True)
        try:
            probe.acquire()
            seen.append('free')            # лок не взят — так быть не должно
            probe.release()
        except portalocker.exceptions.LockException:
            seen.append('held')
        return _sentinel_line(True, {G1: RAW_G1}, [])

    rc.lookup([G1], store=FakeStore(), run=run)
    assert seen == ['held'] and lock_file.exists()
    probe = portalocker.Lock(str(lock_file), timeout=0, fail_when_locked=True)
    probe.acquire()                         # после lookup лок свободен
    probe.release()


def test_nightly_refresh_defers_product_info(monkeypatch, tmp_path):
    """Ночная search-stock обновляет токен на бар-ПК — product-info в это время не шлём."""
    _configured(monkeypatch)
    lock = tmp_path / 'debug' / 'refresh.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text('123')
    calls = []
    store = FakeStore()
    result = rc.lookup([G1], store=store, run=lambda cmd, timeout: calls.append(cmd) or '')
    assert calls == [] and result['remote_used'] is False
    assert result['errors'] == [rc.NIGHTLY_BUSY_ERROR] and result['missing'] == [G1]
    assert store.saved == []                                   # «в ЧЗ нет» не записываем
    old = time.time() - rc.NIGHTLY_LOCK_STALE_SEC - 5
    os.utime(lock, (old, old))                                 # висячий лок — не мешает
    assert rc.nightly_refresh_running() is False


def test_set_paths_defaults():
    rc.set_paths()
    assert rc.nightly_lock_path() == rc.NIGHTLY_LOCK_FILE == os.path.join(
        _REPO, 'chz_test', 'debug', 'refresh.lock')
    assert rc.lock_path() == rc.LOCK_FILE == os.path.join(_REPO, 'data', '.receiving_chz.lock')
    assert rc.stock_file_path() == rc.CHZ_STOCK_FILE == os.path.join(_REPO, 'chz_test', 'debug',
                                                                     'chz_stock.json')


def test_lookup_stock_file_edge_cases(monkeypatch, tmp_path):
    _configured(monkeypatch)
    # нет файла — не ошибка
    result = rc.lookup([G1], remote=False, store=FakeStore())
    assert result['missing'] == [G1] and result['errors'] == []
    # битый файл — не ошибка
    (tmp_path / 'chz_stock.json').write_text('{oops', encoding='utf-8')
    assert rc.lookup([G1], remote=False, store=FakeStore())['errors'] == []
    # позиция без названия (product/info ночью не ответил) — идём на бар-ПК
    _write_stock(tmp_path, [{'gtin': G1, 'name': '', 'brand': '', 'product_group': 'beer'}, 'мусор', {'x': 1}])
    calls = []
    result = rc.lookup([G1], store=FakeStore(), run=_fake_run(CATALOG, calls))
    assert len(calls) == 1 and result['items'][G1]['source'] == 'product_info'
    # явный stock_file важнее пути по умолчанию
    other = tmp_path / 'other.json'
    other.write_text(json.dumps([{'gtin': G3, 'name': 'Другой файл'}]), encoding='utf-8')
    result = rc.lookup([G3], remote=False, store=FakeStore(), stock_file=other)
    assert result['items'][G3]['name'] == 'Другой файл'


def test_lookup_store_failures_do_not_break_lookup(monkeypatch):
    _configured(monkeypatch)

    class BrokenStore(FakeStore):
        def get_chz_products(self, gtins):
            raise RuntimeError('database is locked')

        def save_chz_products(self, rows):
            raise RuntimeError('disk I/O error')

    result = rc.lookup([G1], store=BrokenStore(), run=_fake_run(CATALOG, []))
    assert result['items'][G1]['source'] == 'product_info'
    assert result['errors'] == ['Кэш названий ЧЗ не прочитан: RuntimeError',
                                'Кэш названий ЧЗ не сохранён: RuntimeError']


def test_lookup_ignores_junk_and_empty_input(monkeypatch):
    _configured(monkeypatch)
    store = FakeStore()
    assert rc.lookup([], store=store) == {'items': {}, 'missing': [], 'errors': [], 'remote_used': False}
    assert store.get_calls == []
    result = rc.lookup(['abc', None, '4610093628430', G1], store=store, run=_fake_run(CATALOG, []))
    assert list(result['items']) == [G1] and result['missing'] == []


def test_lookup_default_store_is_receiving_store(monkeypatch):
    """store=None -> модуль core.receiving_store (подменяем в sys.modules: модуль другой зоны)."""
    import types
    fake = types.ModuleType('core.receiving_store')
    backing = FakeStore({G1: dict(_negative_row(G1, ''), found=1, name='Из БД', fetched_at=_iso())})
    fake.get_chz_products = backing.get_chz_products
    fake.save_chz_products = backing.save_chz_products
    import core
    monkeypatch.setitem(sys.modules, 'core.receiving_store', fake)
    monkeypatch.setattr(core, 'receiving_store', fake, raising=False)
    result = rc.lookup([G1], remote=False)
    assert result['items'][G1]['name'] == 'Из БД' and result['items'][G1]['source'] == 'cache'


def test_lookup_with_real_receiving_store(monkeypatch, tmp_path):
    """Контракт с core.receiving_store (found там bool): кэш и «в ЧЗ нет» на временной БД."""
    store = pytest.importorskip('core.receiving_store')
    _configured(monkeypatch)
    store.set_db_path(str(tmp_path / 'receiving.db'))
    try:
        calls = []
        first = rc.lookup([G1, G3], store=store, run=_fake_run(CATALOG, calls))
        assert first['items'][G1]['source'] == 'product_info' and first['missing'] == [G3]
        cached = store.get_chz_products([G1, G3])
        assert cached[G1]['found'] is True and cached[G1]['raw'] == RAW_G1
        assert cached[G3]['found'] is False
        second = rc.lookup([G1, G3], store=store, run=_fake_run(CATALOG, calls))
        assert len(calls) == 1                       # G1 из кэша, G3 — «нет» моложе недели
        assert second['items'][G1]['source'] == 'cache'
        assert second['items'][G1]['name'] == RAW_G1['name']
        assert second['items'][G1]['volume'] == '450 мл'
        assert second['missing'] == [G3] and second['remote_used'] is False
    finally:
        store.set_db_path(None)


# ----- CLI ---------------------------------------------------------------------

def test_cli_prints_fetch_result(monkeypatch, capsys):
    _configured(monkeypatch)
    monkeypatch.setattr(rc, '_default_run', _fake_run(CATALOG, []))
    assert rc._main(['4610093628430,' + G3]) == 0
    out = capsys.readouterr().out
    assert 'ФХ Хеллес' in out                    # ensure_ascii=False
    assert json.loads(out) == {'items': {G1: RAW_G1}, 'missing': [G3]}


def test_cli_usage_and_errors(monkeypatch, capsys):
    assert rc._main([]) == 2
    assert 'Использование' in capsys.readouterr().err
    monkeypatch.setenv('REMOTE_PASS', '')
    assert rc._main([G1]) == 1
    assert 'REMOTE_PASS' in capsys.readouterr().err
    _configured(monkeypatch)
    monkeypatch.setattr(rc, '_default_run', lambda cmd, t: 'old chz.py help')
    assert rc._main([G1]) == 1
    assert 'устарел' in capsys.readouterr().err


# ----- контракт и стиль -----------------------------------------------------------

def test_constants_contract():
    assert rc.SENTINEL == chz.CHZ_JSON_SENTINEL == '@@CHZ_JSON@@'
    assert rc.CHUNK == 400 and rc.CHUNK <= chz.PRODUCT_INFO_MAX_GTINS
    assert rc.REMOTE_TIMEOUT == 180 and rc.NEGATIVE_TTL_DAYS == 7
    assert rc.LOCK_WAIT_SEC >= rc.REMOTE_TIMEOUT       # дождаться одну чужую команду
    longest = ('cd /d ' + remote_exec.REMOTE_CHZ_DIR + ' && "' + remote_exec.REMOTE_PYTHON
               + '" chz.py product-info ' + ','.join(['9' * 14] * rc.CHUNK))
    assert len(longest) < 8191


def test_py310_compatible_syntax():
    """CI и прод — Python 3.10 (chz.py на бар-ПК — 3.12, но тесты импортируют его на 3.10)."""
    for path in (rc.__file__, chz.__file__):
        ast.parse(open(path, encoding='utf-8').read(), feature_version=(3, 10))


def test_no_emoji_or_bullet():
    for path in (rc.__file__, chz.__file__, __file__):
        src = open(path, encoding='utf-8').read()
        assert chr(0x2022) not in src          # «жирная точка» запрещена правилами проекта
        assert not any(ord(ch) >= 0x1F000 for ch in src)


if __name__ == '__main__':
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, '-q']))
