"""
Тесты статуса обновления кэша Честного знака (routes/stocks.py: /api/chz/refresh и
/api/chz/refresh/status) — одинакового в любом worker'е gunicorn.

Баг 2026-10-04: статус смотрел только _refresh_proc своего worker'а; опрос страницы
«Сроки годности», попавший во второй worker, получал running=false, exit_code=null, и
страница писала «Ошибка (exit null)» посреди обновления. Теперь «идёт ли» — по
refresh.lock и pid обёртки (refresh.pid), код выхода — из refresh.exit, который пишет
сама обёртка _REFRESH_RUNNER, она же снимает лок.

Что проверяется:
- «второй worker» (_refresh_proc нет): лок + живой pid -> running, код null; лока нет,
  refresh.exit = 0 -> завершено успешно; лок без pid старше порога и лок с мёртвым pid —
  висячие (не идёт); лок без pid моложе порога — идёт (миг между локом и Popen);
- start_chz_refresh: обёртка запускается с путями лока и кода, pid записан, прежние
  pid и код удалены; повторный запуск при живой обёртке — already_running; висячий лок
  снимается; без REMOTE_PASS — 503;
- настоящая обёртка: запускает remote_exec.py run search-stock, пишет код выхода, снимает
  лок, дописывает строку «refresh finished» в журнал.
"""
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
import routes.stocks as rs  # noqa: E402


@pytest.fixture
def chz(tmp_path, monkeypatch):
    debug = tmp_path / 'debug'
    debug.mkdir()
    paths = {
        '_CHZ_REFRESH_LOCK': debug / 'refresh.lock',
        '_CHZ_REFRESH_PID': debug / 'refresh.pid',
        '_CHZ_REFRESH_EXIT': debug / 'refresh.exit',
        '_CHZ_REFRESH_LOG': debug / 'refresh.log',
        '_CHZ_CACHE_FILE': debug / 'chz_stock.json',
    }
    for name, path in paths.items():
        monkeypatch.setattr(rs, name, path)
    monkeypatch.setattr(rs, '_refresh_proc', None)
    monkeypatch.setattr(rs, '_refresh_log_file', None)
    app = Flask('test_chz_refresh')
    app.register_blueprint(rs.stocks_bp)
    client = app.test_client()
    client.paths = paths
    return client


def _status(client):
    response = client.get('/api/chz/refresh/status')
    assert response.status_code == 200
    return response.get_json()


def _dead_pid():
    proc = subprocess.Popen([sys.executable, '-c', 'pass'])
    proc.wait()
    return proc.pid


def test_other_worker_sees_running(chz):
    chz.paths['_CHZ_REFRESH_LOCK'].write_text('1\n', encoding='ascii')
    chz.paths['_CHZ_REFRESH_PID'].write_text('%d\n' % os.getpid(), encoding='ascii')
    chz.paths['_CHZ_REFRESH_EXIT'].write_text('1', encoding='ascii')   # код прошлого прогона
    status = _status(chz)
    assert status['running'] is True and status['exit_code'] is None


def test_finished_exit_code_from_file(chz):
    chz.paths['_CHZ_REFRESH_EXIT'].write_text('0', encoding='ascii')
    chz.paths['_CHZ_REFRESH_PID'].write_text('%d\n' % _dead_pid(), encoding='ascii')
    status = _status(chz)
    assert status['running'] is False and status['exit_code'] == 0


def test_stale_and_dead_locks_are_not_running(chz):
    lock = chz.paths['_CHZ_REFRESH_LOCK']
    lock.write_text('1\n', encoding='ascii')
    # Без pid: моложе порога — идёт (между локом и Popen), старше — висячий.
    assert _status(chz)['running'] is True
    old = time.time() - rs._CHZ_REFRESH_STALE_SEC - 60
    os.utime(lock, (old, old))
    assert _status(chz)['running'] is False
    # С мёртвым pid — висячий сразу, хоть лок и свежий.
    os.utime(lock, None)
    chz.paths['_CHZ_REFRESH_PID'].write_text('%d\n' % _dead_pid(), encoding='ascii')
    assert _status(chz)['running'] is False


class _FakeProc:
    def __init__(self, args, **kwargs):
        self.args = args
        self.pid = os.getpid()      # «живой» процесс

    def poll(self):
        return None


def test_start_runs_wrapper_and_records_pid(chz, monkeypatch):
    monkeypatch.setenv('REMOTE_PASS', 'x')
    started = []
    monkeypatch.setattr(rs.subprocess, 'Popen', lambda args, **kw: started.append(args) or _FakeProc(args))
    chz.paths['_CHZ_REFRESH_EXIT'].write_text('1', encoding='ascii')     # прошлый прогон
    result, code = rs.start_chz_refresh()
    assert (result['status'], code) == ('started', 200)
    args = started[0]
    assert args[0] == sys.executable and args[1] == '-c' and args[2] == rs._REFRESH_RUNNER
    assert args[3].endswith('remote_exec.py')
    assert args[4] == str(chz.paths['_CHZ_REFRESH_LOCK']) and args[5] == str(chz.paths['_CHZ_REFRESH_EXIT'])
    assert chz.paths['_CHZ_REFRESH_PID'].read_text(encoding='ascii').strip() == str(os.getpid())
    assert not chz.paths['_CHZ_REFRESH_EXIT'].exists()
    assert chz.paths['_CHZ_REFRESH_LOCK'].exists()
    # Второй worker: свой _refresh_proc пуст, но обёртка жива — already_running.
    monkeypatch.setattr(rs, '_refresh_proc', None)
    result, code = rs.start_chz_refresh()
    assert code == 409 and result['status'] == 'already_running'
    assert _status(chz)['running'] is True
    rs._refresh_log_file.close()


def test_start_replaces_stale_lock(chz, monkeypatch):
    monkeypatch.setenv('REMOTE_PASS', 'x')
    dead = _dead_pid()          # до подмены Popen: rs.subprocess — общий модуль
    monkeypatch.setattr(rs.subprocess, 'Popen', lambda args, **kw: _FakeProc(args))
    chz.paths['_CHZ_REFRESH_LOCK'].write_text('1\n', encoding='ascii')
    chz.paths['_CHZ_REFRESH_PID'].write_text('%d\n' % dead, encoding='ascii')
    result, code = rs.start_chz_refresh()
    assert (result['status'], code) == ('started', 200)
    rs._refresh_log_file.close()


def test_start_without_remote_pass(chz, monkeypatch):
    monkeypatch.delenv('REMOTE_PASS', raising=False)
    assert rs.start_chz_refresh()[1] == 503


def test_real_wrapper_writes_exit_and_removes_lock(tmp_path):
    """Обёртка _REFRESH_RUNNER по-настоящему: код выхода, лок, строка в журнале."""
    fake_remote = tmp_path / 'remote_exec.py'
    fake_remote.write_text(
        'import sys\n'
        'assert sys.argv[1:] == ["run", "search-stock"], sys.argv\n'
        'print("remote output")\n'
        'sys.exit(3)\n', encoding='utf-8')
    lock = tmp_path / 'refresh.lock'
    lock.write_text('1\n', encoding='ascii')
    exit_file = tmp_path / 'refresh.exit'
    log = tmp_path / 'refresh.log'
    with open(log, 'w', encoding='utf-8') as out:
        code = subprocess.call([sys.executable, '-c', rs._REFRESH_RUNNER, str(fake_remote),
                                str(lock), str(exit_file)], stdout=out, stderr=out)
    assert code == 3
    assert exit_file.read_text(encoding='ascii') == '3'
    assert not lock.exists()
    text = log.read_text(encoding='utf-8')
    assert 'remote output' in text and '=== refresh finished, exit 3 ===' in text
