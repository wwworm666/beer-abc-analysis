"""Тесты шедулера приёмки на РЦ (core/receiving_scheduler.py). Сети нет, потоков нет.

Потоки не запускаются: _start_thread подменяется записью имён, прогоны (run_daily,
run_startup, retry_once) зовутся напрямую с фейковым receiving_service. Lock-файлы —
во временной папке.
Что проверяется:
- seconds_until: до времени сегодня, ровно в момент и после — завтра, через полночь;
- время из окружения: пусто/мусор/вне диапазона -> по умолчанию (импорт не падает);
- needs_startup_refresh: нет индекса, неизвестный возраст, старше/моложе 26 ч;
- lock-файл на дату: первый воркер берёт, второй нет; уборка старых;
- start_scheduler: идемпотентен; подбор обработок — всегда; утро и старт — только
  с RECEIVING_INDEX_ENABLED != 0 и кредами iiko; сбой не роняет запуск;
- run_daily: без кредов — пропуск, с кредами — run_index_refresh('schedule',
  wait=600), сбой не бросает;
- run_startup: свежий индекс — пропуск, старый/нет — 'startup' без ожидания,
  RefreshBusy — пропуск;
- retry_once зовёт retry_stuck_processing;
- грамматика Python 3.10.
"""
import os
import re
import subprocess
import sys
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import msk_time  # noqa: E402
from core import receiving_index  # noqa: E402
from core import receiving_scheduler as sched  # noqa: E402
from core import receiving_service  # noqa: E402


# ----------------------------------------------------------------- чистые функции

def test_seconds_until_today_and_tomorrow():
    now = datetime(2026, 10, 3, 6, 0, 0)
    assert sched.seconds_until(7, 30, now) == 90 * 60
    assert sched.seconds_until(7, 30, datetime(2026, 10, 3, 7, 30, 0)) == 24 * 3600   # ровно в момент — завтра
    assert sched.seconds_until(7, 30, datetime(2026, 10, 3, 7, 30, 1)) == 24 * 3600 - 1
    assert sched.seconds_until(0, 5, datetime(2026, 10, 3, 23, 55)) == 10 * 60          # через полночь
    assert sched.seconds_until(7, 30, datetime(2026, 12, 31, 8, 0)) == 23.5 * 3600      # через год


def test_defaults_and_constants():
    assert sched.LOCK_PREFIX == '.receiving_index_lock_'
    assert sched.STARTUP_DELAY_SEC == 30 and sched.STARTUP_MAX_AGE_HOURS == 26
    assert sched.RETRY_INTERVAL_SEC == 600 and sched.SCHEDULE_WAIT_SEC == 600
    assert sched.LOCK_DIR == os.path.join(ROOT, 'data')


def test_env_int(monkeypatch):
    monkeypatch.setenv('X_TEST_HOUR', '9')
    assert sched._env_int('X_TEST_HOUR', 7, 0, 23) == 9
    for bad in ('', '  ', 'утро', '24', '-1', '7.5'):
        monkeypatch.setenv('X_TEST_HOUR', bad)
        assert sched._env_int('X_TEST_HOUR', 7, 0, 23) == 7
    monkeypatch.delenv('X_TEST_HOUR')
    assert sched._env_int('X_TEST_HOUR', 7, 0, 23) == 7


def test_env_time_read_at_import():
    """RECEIVING_INDEX_HOUR/MINUTE читаются при импорте: значения и кривые не роняют импорт."""
    code = ('from core import receiving_scheduler as s; print(s.INDEX_HOUR, s.INDEX_MINUTE)')
    env = dict(os.environ, RECEIVING_INDEX_HOUR='6', RECEIVING_INDEX_MINUTE='45', PYTHONDONTWRITEBYTECODE='1')
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == '6 45'
    env.update(RECEIVING_INDEX_HOUR='', RECEIVING_INDEX_MINUTE='99')
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == '7 30'


def test_needs_startup_refresh():
    limit = sched.STARTUP_MAX_AGE_HOURS * 60
    assert sched.needs_startup_refresh(None) is True
    assert sched.needs_startup_refresh({}) is True
    assert sched.needs_startup_refresh({'built_at': 'x', 'age_minutes': None}) is True
    assert sched.needs_startup_refresh({'age_minutes': limit + 1}) is True
    assert sched.needs_startup_refresh({'age_minutes': limit}) is False
    assert sched.needs_startup_refresh({'age_minutes': 5}) is False


def test_now_is_moscow_naive(monkeypatch):
    aware = datetime(2026, 10, 3, 7, 30, tzinfo=msk_time.MOSCOW_TZ)
    monkeypatch.setattr(msk_time, 'now', lambda: aware)
    assert sched._now() == datetime(2026, 10, 3, 7, 30)


# ----------------------------------------------------------------- lock-файлы

@pytest.fixture
def lock_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(sched, 'LOCK_DIR', str(tmp_path))
    return tmp_path


def test_daily_lock_once_per_date(lock_dir):
    assert sched._try_acquire_lock(sched.LOCK_PREFIX, '2026-10-03') is True
    assert sched._try_acquire_lock(sched.LOCK_PREFIX, '2026-10-03') is False     # второй воркер
    assert sched._try_acquire_lock(sched.LOCK_PREFIX, '2026-10-04') is True
    content = (lock_dir / '.receiving_index_lock_2026-10-03').read_text()
    assert content.strip() == str(os.getpid())


def test_cleanup_old_locks(lock_dir, monkeypatch):
    monkeypatch.setattr(msk_time, 'now', lambda: datetime(2026, 10, 3, 8, 0, tzinfo=msk_time.MOSCOW_TZ))
    for name in ('.receiving_index_lock_2026-09-29', '.receiving_index_lock_2026-10-01',
                 '.receiving_index_lock_2026-10-02', '.receiving_index_lock_2026-10-03',
                 '.yandex_reviews_lock_2026-09-01', '.receiving_index_run.lock'):
        (lock_dir / name).write_text('1\n')
    sched._cleanup_old_locks()
    left = sorted(p.name for p in lock_dir.iterdir())
    assert left == ['.receiving_index_lock_2026-10-01', '.receiving_index_lock_2026-10-02',
                    '.receiving_index_lock_2026-10-03', '.receiving_index_run.lock',
                    '.yandex_reviews_lock_2026-09-01']


# ----------------------------------------------------------------- start_scheduler (без потоков)

@pytest.fixture
def no_threads(monkeypatch, lock_dir):
    started = []
    monkeypatch.setattr(sched, '_start_thread', lambda target, name: started.append(name))
    monkeypatch.setattr(sched, '_started', False)
    monkeypatch.delenv(sched.ENV_ENABLED, raising=False)
    return started


def test_start_with_creds_starts_three_threads_once(no_threads, monkeypatch):
    monkeypatch.setattr(receiving_service, 'iiko_configured', lambda: True)
    sched.start_scheduler()
    assert no_threads == ['receiving-retry', 'receiving-index-daily', 'receiving-index-startup']
    sched.start_scheduler()                     # идемпотентно
    assert len(no_threads) == 3


def test_start_disabled_only_retry(no_threads, monkeypatch):
    monkeypatch.setattr(receiving_service, 'iiko_configured', lambda: True)
    monkeypatch.setenv(sched.ENV_ENABLED, '0')
    sched.start_scheduler()
    assert no_threads == ['receiving-retry']


def test_start_enabled_values(no_threads, monkeypatch):
    monkeypatch.setattr(receiving_service, 'iiko_configured', lambda: True)
    monkeypatch.setenv(sched.ENV_ENABLED, '')
    assert sched.index_enabled() is True
    monkeypatch.setenv(sched.ENV_ENABLED, ' 0 ')
    assert sched.index_enabled() is False


def test_start_without_creds_only_retry(no_threads, monkeypatch):
    monkeypatch.setattr(receiving_service, 'iiko_configured', lambda: False)
    sched.start_scheduler()
    assert no_threads == ['receiving-retry']


def test_start_failure_does_not_raise(monkeypatch, lock_dir):
    monkeypatch.setattr(sched, '_started', False)

    def broken(target, name):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(sched, '_start_thread', broken)
    sched.start_scheduler()                     # не бросает: запуск приложения не падает
    assert sched._started is True


# ----------------------------------------------------------------- прогоны

class FakeService:
    def __init__(self, configured=True, error=None):
        self.configured = configured
        self.error = error
        self.refresh_calls = []
        self.retry_calls = 0

    def iiko_configured(self):
        return self.configured

    def run_index_refresh(self, trigger, *, lock=None, wait=0):
        self.refresh_calls.append((trigger, wait))
        if self.error is not None:
            raise self.error
        return {'index': {'built_at': 'now'}, 'reconcile': {'checked': 0}, 'reconcile_error': ''}

    def retry_stuck_processing(self):
        self.retry_calls += 1
        return [5]


@pytest.fixture
def fake_service(monkeypatch):
    import core
    fake = FakeService()
    # Прогоны импортируют модуль лениво (from core import receiving_service) — подменяем атрибут пакета.
    monkeypatch.setattr(core, 'receiving_service', fake, raising=False)
    monkeypatch.setitem(sys.modules, 'core.receiving_service', fake)
    return fake


def test_run_daily(fake_service):
    assert sched.run_daily()['index'] == {'built_at': 'now'}
    assert fake_service.refresh_calls == [('schedule', sched.SCHEDULE_WAIT_SEC)]


def test_run_daily_without_creds_skips(fake_service):
    fake_service.configured = False
    assert sched.run_daily() is None
    assert fake_service.refresh_calls == []


def test_run_daily_failure_does_not_raise(fake_service):
    fake_service.error = receiving_index.IndexSourceError('iiko ответил HTTP 500 (товары)')
    assert sched.run_daily() is None


def test_run_startup_refreshes_stale_or_missing(fake_service, monkeypatch):
    monkeypatch.setattr(receiving_index, 'load_index', lambda: None)
    assert sched.run_startup() is not None
    assert fake_service.refresh_calls == [('startup', 0)]


def test_run_startup_skips_fresh(fake_service, monkeypatch):
    monkeypatch.setattr(receiving_index, 'load_index', lambda: {'built_at': 'x'})
    monkeypatch.setattr(receiving_index, 'index_info',
                        lambda index: {'built_at': '2026-10-03T07:30:00+03:00', 'age_minutes': 60,
                                       'counts': {}, 'source': 'v2'})
    assert sched.run_startup() is None
    assert fake_service.refresh_calls == []


def test_run_startup_stale_and_busy(fake_service, monkeypatch):
    monkeypatch.setattr(receiving_index, 'load_index', lambda: {'built_at': 'x'})
    monkeypatch.setattr(receiving_index, 'index_info',
                        lambda index: {'built_at': 'x', 'age_minutes': 27 * 60, 'counts': {}, 'source': 'v2'})
    fake_service.error = receiving_index.RefreshBusy('Индекс iiko уже обновляется')
    assert sched.run_startup() is None
    assert fake_service.refresh_calls == [('startup', 0)]
    fake_service.error = RuntimeError('boom')
    assert sched.run_startup() is None


def test_run_startup_without_creds(fake_service, monkeypatch):
    fake_service.configured = False
    monkeypatch.setattr(receiving_index, 'load_index', lambda: None)
    assert sched.run_startup() is None
    assert fake_service.refresh_calls == []


def test_retry_once(fake_service):
    assert sched.retry_once() == [5]
    assert fake_service.retry_calls == 1


def test_py310_compatible_syntax():
    """CI и прод — Python 3.10: модуль должен разбираться грамматикой 3.10."""
    import ast
    src = open(sched.__file__, encoding='utf-8').read()
    tree = ast.parse(src, feature_version=(3, 10))
    assert not re.search('[\U0001F000-\U0001FAFF☀-➿️•]', src)
    # Время — только через core.msk_time: в коде нет вызова datetime.now()/today()
    naive = [node.lineno for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr in ('now', 'today', 'utcnow')
             and isinstance(node.func.value, ast.Name) and node.func.value.id in ('datetime', 'date')]
    assert naive == []


def test_app_starts_receiving_scheduler():
    """app.py подключает шедулер в _start_background_jobs (тест не импортирует app.py)."""
    src = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
    body = src[src.index('def _start_background_jobs'):src.index("if os.environ.get('BEER_SCHEDULERS'")]
    assert 'from core.receiving_scheduler import start_scheduler as start_receiving_scheduler' in body
    assert 'start_receiving_scheduler()' in body


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
