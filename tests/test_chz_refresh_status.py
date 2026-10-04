"""
Тесты статуса обновления кэша Честного знака (routes/stocks.py: /api/chz/refresh и
/api/chz/refresh/status) — одинакового в любом worker'е gunicorn.

Баг 2026-10-04: статус смотрел только _refresh_proc своего worker'а; опрос страницы
«Сроки годности», попавший во второй worker, получал running=false, exit_code=null, и
страница писала «Ошибка (exit null)» посреди обновления. Теперь «идёт ли» — по
refresh.lock и pid обёртки (refresh.pid), код выхода — из refresh.exit, который пишет
сама обёртка _REFRESH_RUNNER, она же снимает лок.

Ревью 2026-10-04: «pid жив» мало — после перезапуска контейнера номер убитой обёртки
достаётся другому процессу или потоку; теперь по /proc/<pid>/cmdline проверяется, что это
обёртка этого лока, лок старше _CHZ_REFRESH_MAX_SEC висячий всегда, os.kill не
используется (на Windows сигнал 0 завершает процесс).

Что проверяется:
- «второй worker» (_refresh_proc нет): лок + живая обёртка -> running, код null; лока
  нет, refresh.exit = 0 -> завершено успешно; лок без pid старше порога, лок с мёртвым
  pid, лок с pid чужого живого процесса (номер переиспользован) и лок старше
  _CHZ_REFRESH_MAX_SEC — висячие; лок без pid моложе порога — идёт;
- код выхода «своего» процесса worker'а берётся, только если это обёртка из refresh.pid;
- start_chz_refresh: обёртка запускается с путями лока и кода, pid записан, прежние
  pid и код удалены; повторный запуск при живой обёртке — already_running; висячий лок
  снимается; без REMOTE_PASS — 503;
- настоящая обёртка: запускает remote_exec.py run search-stock, пишет код выхода, снимает
  лок, дописывает строку «refresh finished» в журнал; зависший remote_exec.py обрывается
  по таймауту с кодом 124.
"""
import json
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HAS_PROC = os.path.isdir('/proc')
needs_proc = pytest.mark.skipif(not HAS_PROC, reason='проверка обёртки — по /proc (Linux, прод)')
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
        '_CHZ_SYNC_FILE': debug / 'chz_sync.json',
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


@pytest.fixture
def runner(chz):
    """Живой процесс, похожий на обёртку: среди аргументов — путь refresh.lock."""
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)', 'remote_exec.py',
                             str(chz.paths['_CHZ_REFRESH_LOCK']), 'refresh.exit', '7200'])
    try:
        yield proc
    finally:
        proc.kill()
        proc.wait()


@needs_proc
def test_other_worker_sees_running(chz, runner):
    chz.paths['_CHZ_REFRESH_LOCK'].write_text('1\n', encoding='ascii')
    chz.paths['_CHZ_REFRESH_PID'].write_text('%d\n' % runner.pid, encoding='ascii')
    chz.paths['_CHZ_REFRESH_EXIT'].write_text('1', encoding='ascii')   # код прошлого прогона
    status = _status(chz)
    assert status['running'] is True and status['exit_code'] is None


@needs_proc
def test_reused_pid_of_other_process_is_not_a_refresh(chz):
    # Контейнер перезапустили посреди обновления: номер из refresh.pid теперь у другого
    # живого процесса (здесь — сам pytest) — это не обёртка, лок висячий.
    chz.paths['_CHZ_REFRESH_LOCK'].write_text('1\n', encoding='ascii')
    chz.paths['_CHZ_REFRESH_PID'].write_text('%d\n' % os.getpid(), encoding='ascii')
    assert _status(chz)['running'] is False
    assert rs._is_refresh_runner(os.getpid()) is False


@needs_proc
def test_lock_older_than_max_is_stale_even_with_live_runner(chz, runner):
    lock = chz.paths['_CHZ_REFRESH_LOCK']
    lock.write_text('1\n', encoding='ascii')
    chz.paths['_CHZ_REFRESH_PID'].write_text('%d\n' % runner.pid, encoding='ascii')
    old = time.time() - rs._CHZ_REFRESH_MAX_SEC - 60
    os.utime(lock, (old, old))
    assert _status(chz)['running'] is False


def test_without_proc_age_decides(chz, monkeypatch):
    # Windows и macOS при разработке: проверить обёртку нечем — решает возраст лока, и
    # никакого os.kill (на Windows сигнал 0 завершил бы процесс).
    monkeypatch.setattr(rs, '_is_refresh_runner', lambda pid: None)
    monkeypatch.setattr(rs.os, 'kill', lambda *a: pytest.fail('os.kill вызван'), raising=False)
    lock = chz.paths['_CHZ_REFRESH_LOCK']
    lock.write_text('1\n', encoding='ascii')
    chz.paths['_CHZ_REFRESH_PID'].write_text('%d\n' % os.getpid(), encoding='ascii')
    assert _status(chz)['running'] is True
    old = time.time() - rs._CHZ_REFRESH_STALE_SEC - 60
    os.utime(lock, (old, old))
    assert _status(chz)['running'] is False


def test_own_exit_code_only_for_the_run_in_pid_file(chz, monkeypatch):
    # Worker держит вчерашнюю обёртку (код 0, не забрана), а текущую запустил другой
    # worker, и её убили до записи кода: «успешно» показывать нельзя.
    class Finished:
        pid = 4242

        def poll(self):
            return 0

    monkeypatch.setattr(rs, '_refresh_proc', Finished())
    chz.paths['_CHZ_REFRESH_PID'].write_text('%d\n' % _dead_pid(), encoding='ascii')
    assert _status(chz)['exit_code'] is None
    monkeypatch.setattr(rs, '_refresh_proc', Finished())
    chz.paths['_CHZ_REFRESH_PID'].write_text('4242\n', encoding='ascii')
    assert _status(chz)['exit_code'] == 0


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
    # С мёртвым pid — висячий сразу, хоть лок и свежий (где есть /proc).
    if HAS_PROC:
        os.utime(lock, None)
        chz.paths['_CHZ_REFRESH_PID'].write_text('%d\n' % _dead_pid(), encoding='ascii')
        assert _status(chz)['running'] is False


class _FakeProc:
    def __init__(self, args, pid=None, **kwargs):
        self.args = args
        self.pid = pid if pid is not None else os.getpid()

    def poll(self):
        return None


@needs_proc
def test_start_runs_wrapper_and_records_pid(chz, monkeypatch, runner):
    monkeypatch.setenv('REMOTE_PASS', 'x')
    started = []
    monkeypatch.setattr(rs.subprocess, 'Popen',
                        lambda args, **kw: started.append(args) or _FakeProc(args, pid=runner.pid))
    chz.paths['_CHZ_REFRESH_EXIT'].write_text('1', encoding='ascii')     # прошлый прогон
    result, code = rs.start_chz_refresh()
    assert (result['status'], code) == ('started', 200)
    args = started[0]
    assert args[0] == sys.executable and args[1] == '-c' and args[2] == rs._REFRESH_RUNNER
    assert args[3].endswith('remote_exec.py')
    assert args[4] == str(chz.paths['_CHZ_REFRESH_LOCK']) and args[5] == str(chz.paths['_CHZ_REFRESH_EXIT'])
    assert args[6] == str(rs._CHZ_REFRESH_RUN_TIMEOUT_SEC)
    assert rs._CHZ_REFRESH_RUN_TIMEOUT_SEC < rs._CHZ_REFRESH_MAX_SEC      # обёртка кончится раньше лока
    assert chz.paths['_CHZ_REFRESH_PID'].read_text(encoding='ascii').strip() == str(runner.pid)
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


def test_status_shows_chz_sync_of_current_run_only(chz):
    # Итог сверки chz.py с бар-ПК (пишет remote_exec) — только из текущего прогона: файл
    # не старше refresh.pid, который пишет запуск обновления (ревью 2026-10-04).
    pid_file, sync_file = chz.paths['_CHZ_REFRESH_PID'], chz.paths['_CHZ_SYNC_FILE']
    assert _status(chz)['chz_sync'] is None                          # файлов нет
    sync_file.write_text(json.dumps({'result': 'updated', 'message': 'chz.py на бар-ПК обновлён: ...',
                                     'at': '2026-10-04T23:00:00'}, ensure_ascii=False), encoding='utf-8')
    pid_file.write_text('%d\n' % _dead_pid(), encoding='ascii')
    os.utime(sync_file, (time.time() - 3600, time.time() - 3600))   # вчерашний итог
    assert _status(chz)['chz_sync'] is None
    os.utime(sync_file, None)
    assert _status(chz)['chz_sync'] == {'result': 'updated', 'message': 'chz.py на бар-ПК обновлён: ...',
                                        'at': '2026-10-04T23:00:00'}
    sync_file.write_text('не json', encoding='utf-8')
    assert _status(chz)['chz_sync'] is None


def test_start_without_remote_pass(chz, monkeypatch):
    monkeypatch.delenv('REMOTE_PASS', raising=False)
    assert rs.start_chz_refresh()[1] == 503


def test_real_wrapper_writes_exit_and_removes_lock(tmp_path):
    """Обёртка _REFRESH_RUNNER по-настоящему: код выхода, лок, строка в журнале."""
    fake_remote = tmp_path / 'remote_exec.py'
    fake_remote.write_text(
        'import sys\n'
        'assert sys.argv[1:] == ["run", "search-stock", "--sync-chz"], sys.argv\n'
        'print("remote output")\n'
        'sys.exit(3)\n', encoding='utf-8')
    lock = tmp_path / 'refresh.lock'
    lock.write_text('1\n', encoding='ascii')
    exit_file = tmp_path / 'refresh.exit'
    log = tmp_path / 'refresh.log'
    with open(log, 'w', encoding='utf-8') as out:
        code = subprocess.call([sys.executable, '-c', rs._REFRESH_RUNNER, str(fake_remote),
                                str(lock), str(exit_file), '60'], stdout=out, stderr=out)
    assert code == 3
    assert exit_file.read_text(encoding='ascii') == '3'
    assert not lock.exists()
    text = log.read_text(encoding='utf-8')
    assert 'remote output' in text and '=== refresh finished, exit 3 ===' in text


def test_real_wrapper_times_out_hung_remote_exec(tmp_path):
    """Зависший remote_exec.py (передача файлов без таймаута) обрывается: код 124, лок снят."""
    fake_remote = tmp_path / 'remote_exec.py'
    fake_remote.write_text('import time\ntime.sleep(30)\n', encoding='utf-8')
    lock = tmp_path / 'refresh.lock'
    lock.write_text('1\n', encoding='ascii')
    exit_file = tmp_path / 'refresh.exit'
    log = tmp_path / 'refresh.log'
    started = time.time()
    with open(log, 'w', encoding='utf-8') as out:
        code = subprocess.call([sys.executable, '-c', rs._REFRESH_RUNNER, str(fake_remote),
                                str(lock), str(exit_file), '1'], stdout=out, stderr=out)
    assert time.time() - started < 20
    assert code == 124 and exit_file.read_text(encoding='ascii') == '124'
    assert not lock.exists()
    assert '=== refresh timed out after 1 s ===' in log.read_text(encoding='utf-8')
