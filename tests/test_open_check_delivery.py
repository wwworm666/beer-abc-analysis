"""
Тесты гарантии доставки open-check бота (после пропуска тревоги 2026-08-16).

Что проверяем:
  * _send_with_retries: «мигнувшая» блокировка лечится вторым проходом,
    провалившиеся chat_id возвращаются списком;
  * send_report: недоставленное попадает в очередь досылки (и НЕ попадает в
    DRY-RUN), note дописывается в текст;
  * open_check_pending: досылка с честной пометкой о задержке, частичная
    доставка сохраняет остаток, очередь чужого дня удаляется без отправки,
    занятый лок -> busy (второй воркер не дублирует);
  * планировщик: catch-up после рестарта поверх 14:59 (и только тогда),
    падение run_check шлёт тревогу «проверка упала».

Сеть не трогаем: send_message подменяется, iiko не вызывается (state собран
руками).
"""
import json
import os
import time
from datetime import datetime

import portalocker
import pytest

from core import open_check_bot as bot
from core import open_check_pending as pending
from core import open_check_scheduler as sched


CHECK_DT = datetime(2026, 8, 16, 14, 59)
TODAY = '2026-08-16'


# ==================== Хелперы ====================

def make_state(closed=(), iiko_error=False):
    """Состояние как из check_bars_state, без похода в iiko."""
    from core.venues_config import PHYSICAL_VENUES
    closed = list(closed)
    open_keys = {k for k in PHYSICAL_VENUES if k not in closed}
    return {
        'iiko_error': iiko_error,
        'error_msg': 'boom' if iiko_error else None,
        'open_keys': open_keys,
        'closed_keys': [k for k in PHYSICAL_VENUES if k in closed],
        'other_open': [],
        'unknown_pos': [],
        'open_times': {k: '13:00' for k in open_keys},
        'check_dt': CHECK_DT,
    }


class ScriptedSender:
    """send_message с расписанием ответов: {chat_id: [False, True, ...]}.
    Когда сценарий чата исчерпан — всегда True. Пишет журнал вызовов."""

    def __init__(self, script=None, default=True):
        self.script = {str(k): list(v) for k, v in (script or {}).items()}
        self.default = default
        self.calls = []  # [(chat_id, text, html)]

    def __call__(self, chat_id, text, html=False, **kwargs):
        self.calls.append((str(chat_id), text, html))
        seq = self.script.get(str(chat_id))
        if seq:
            return seq.pop(0)
        return self.default

    def sent_to(self):
        return [c for c, _, _ in self.calls]


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Изоляция: env-получатели, пустые подписчики, pending в tmp, sleep=no-op."""
    monkeypatch.setenv('TELEGRAM_OPEN_CHECK_BOT_TOKEN', 'test-token')
    monkeypatch.setenv('TELEGRAM_GROUP_CHAT_ID', '111')
    monkeypatch.setenv('TELEGRAM_ALARM_CHAT_IDS', '111,222')
    monkeypatch.delenv('OPEN_CHECK_DRY_RUN', raising=False)

    from core import open_check_subscribers as subs
    monkeypatch.setattr(subs, 'get_recipients', lambda: [])

    pending_file = tmp_path / 'open_check_pending.json'
    monkeypatch.setattr(pending, '_path', lambda: str(pending_file))
    monkeypatch.setattr(pending, '_delivered_cache', set())

    monkeypatch.setattr(time, 'sleep', lambda s: None)
    return {'pending_file': pending_file, 'tmp_path': tmp_path}


def read_pending(env):
    with open(env['pending_file'], encoding='utf-8') as f:
        return json.load(f)


# ==================== _send_with_retries ====================

def test_retry_recovers_after_flap(env, monkeypatch):
    """Сценарий 2026-08-16: чат падает на первом проходе, второй проход
    доставляет (тот же IP ожил через секунды)."""
    sender = ScriptedSender({'111': [False, True]})
    from core import open_check_telegram as tg
    monkeypatch.setattr(tg, 'send_message', sender)

    result = bot._send_with_retries(['111', '222'], 'hello')
    assert result == {'sent': 2, 'failed': []}
    # проход 1: 111 (fail), 222 (ok); проход 2: только 111
    assert sender.sent_to() == ['111', '222', '111']


def test_retry_reports_failed_in_order(env, monkeypatch):
    sender = ScriptedSender(default=False)
    from core import open_check_telegram as tg
    monkeypatch.setattr(tg, 'send_message', sender)

    result = bot._send_with_retries(['a1', 'b2', 'c3'], 'x', passes=2)
    assert result == {'sent': 0, 'failed': ['a1', 'b2', 'c3']}
    assert len(sender.calls) == 6  # 3 чата x 2 прохода


# ==================== send_report -> очередь ====================

def test_send_report_queues_failures(env, monkeypatch):
    sender = ScriptedSender({'222': [False, False]})
    from core import open_check_telegram as tg
    monkeypatch.setattr(tg, 'send_message', sender)

    report = bot.send_report(make_state(closed=['bolshoy']), CHECK_DT)
    assert report['target'] == 'alarm'
    assert report['sent'] == 1
    assert report['failed'] == ['222']

    d = read_pending(env)
    assert d['date'] == TODAY
    assert len(d['items']) == 1
    item = d['items'][0]
    assert item['chats'] == ['222']
    assert item['target'] == 'alarm'
    assert item['first_try'] == '14:59'
    assert 'ALARM' in item['text']


def test_send_report_positive_also_queued(env, monkeypatch):
    sender = ScriptedSender(default=False)
    from core import open_check_telegram as tg
    monkeypatch.setattr(tg, 'send_message', sender)

    report = bot.send_report(make_state(), CHECK_DT)
    assert report['target'] == 'positive'
    assert report['failed'] == ['111']
    assert read_pending(env)['items'][0]['target'] == 'positive'


def test_send_report_all_delivered_no_queue(env, monkeypatch):
    sender = ScriptedSender()
    from core import open_check_telegram as tg
    monkeypatch.setattr(tg, 'send_message', sender)

    report = bot.send_report(make_state(closed=['bolshoy']), CHECK_DT)
    assert report['sent'] == 2 and report['failed'] == []
    assert not os.path.exists(env['pending_file'])


def test_send_report_dry_run_never_queues(env, monkeypatch):
    monkeypatch.setenv('OPEN_CHECK_DRY_RUN', '1')
    sender = ScriptedSender(default=False)
    from core import open_check_telegram as tg
    monkeypatch.setattr(tg, 'send_message', sender)

    report = bot.send_report(make_state(closed=['bolshoy']), CHECK_DT)
    assert report['target'] == 'dry-run'
    assert report['failed']  # доставка «провалилась»...
    assert not os.path.exists(env['pending_file'])  # ...но в очередь не пишем


def test_send_report_queue_failures_false_never_queues(env, monkeypatch):
    """Ручной /run-now (queue_failures=False): тестовый прогон при лежащем
    Telegram не должен ставить в очередь протухшую тревогу."""
    sender = ScriptedSender(default=False)
    from core import open_check_telegram as tg
    monkeypatch.setattr(tg, 'send_message', sender)

    report = bot.send_report(make_state(closed=['bolshoy']), CHECK_DT,
                             queue_failures=False)
    assert report['failed'] == ['111', '222']
    assert not os.path.exists(env['pending_file'])


def test_add_write_error_does_not_raise(env, monkeypatch):
    """Ошибка записи очереди (диск полон) не должна вылетать в send_report и
    превращать частично доставленный отчёт в ложную crash-тревогу."""
    def boom(path, data, **kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(pending, 'atomic_write_json', boom)
    pending.add(date_str=TODAY, text='t', chats=['111'], target='alarm',
                first_try='14:59')  # не бросает
    assert not os.path.exists(env['pending_file'])


def test_send_report_appends_note(env, monkeypatch):
    sender = ScriptedSender()
    from core import open_check_telegram as tg
    monkeypatch.setattr(tg, 'send_message', sender)

    note = 'Проверка должна была пройти в 14:59 МСК, выполнена позже из-за перезапуска сервиса'
    report = bot.send_report(make_state(), CHECK_DT, note=note)
    assert report['text'].endswith(note)
    assert sender.calls[0][1].endswith(note)


# ==================== send_crash_alarm ====================

def test_crash_alarm_sends_and_queues(env, monkeypatch):
    sender = ScriptedSender({'111': [False, False]})
    from core import open_check_telegram as tg
    monkeypatch.setattr(tg, 'send_message', sender)

    result = bot.send_crash_alarm(CHECK_DT, 'KeyError: <pos>')
    assert result['sent'] == 1
    assert result['failed'] == ['111']
    text = sender.calls[0][1]
    assert 'проверка баров упала' in text
    assert '&lt;pos&gt;' in text  # динамика экранирована под parse_mode=HTML
    assert read_pending(env)['items'][0]['chats'] == ['111']


def test_crash_alarm_dry_run_marked_and_single_recipient(env, monkeypatch):
    """DRY-RUN crash-тревога помечена [DRY-RUN] (dev с прод-.env не должен
    выглядеть как настоящий сбой прода) и идёт одному получателю без очереди."""
    monkeypatch.setenv('OPEN_CHECK_DRY_RUN', '1')
    sender = ScriptedSender(default=False)
    from core import open_check_telegram as tg
    monkeypatch.setattr(tg, 'send_message', sender)

    bot.send_crash_alarm(CHECK_DT, 'boom')
    assert sender.calls[0][1].startswith('[DRY-RUN] ')
    assert sender.sent_to() == ['111', '111']  # один получатель x 2 прохода
    assert not os.path.exists(env['pending_file'])


# ==================== open_check_pending: досылка ====================

def seed_pending(env, chats, date=TODAY, text='<b>!!! ALARM !!!</b>\nЗАКРЫТ — ВО',
                 target='alarm', first_try='14:59'):
    pending.add(date_str=date, text=text, chats=chats, target=target, first_try=first_try)
    assert read_pending(env)['date'] == date


def test_resend_delivers_with_delay_note(env):
    seed_pending(env, ['111', '222'])
    sender = ScriptedSender()

    result = pending.resend_due(TODAY, send_fn=sender)
    assert result == {'status': 'ok', 'delivered': 2, 'remaining': 0}
    assert not os.path.exists(env['pending_file'])  # очередь опустела
    chat, text, html = sender.calls[0]
    assert html is True
    assert 'ЗАКРЫТ — ВО' in text
    assert 'Доставлено с задержкой' in text
    assert '14:59' in text


def test_resend_partial_keeps_remainder(env):
    seed_pending(env, ['111', '222'])
    sender = ScriptedSender({'222': [False]})

    result = pending.resend_due(TODAY, send_fn=sender)
    assert result == {'status': 'ok', 'delivered': 1, 'remaining': 1}
    assert read_pending(env)['items'][0]['chats'] == ['222']

    # следующий тик добивает остаток
    sender2 = ScriptedSender()
    result2 = pending.resend_due(TODAY, send_fn=sender2)
    assert result2 == {'status': 'ok', 'delivered': 1, 'remaining': 0}
    assert sender2.sent_to() == ['222']
    assert not os.path.exists(env['pending_file'])


def test_resend_stale_day_dropped_without_send(env):
    seed_pending(env, ['111'], date='2026-08-15')
    sender = ScriptedSender()

    result = pending.resend_due(TODAY, send_fn=sender)
    assert result == {'status': 'stale', 'dropped': 1}
    assert sender.calls == []  # вчерашнее «Проверка 14:59» не шлём
    assert not os.path.exists(env['pending_file'])


def test_resend_empty(env):
    assert pending.resend_due(TODAY, send_fn=ScriptedSender()) == {'status': 'empty'}


def test_resend_busy_when_locked(env):
    """Второй воркер при занятом локе выходит с busy, не дублируя отправку."""
    seed_pending(env, ['111'])
    sender = ScriptedSender()
    lock_path = str(env['pending_file']) + '.lock'
    with portalocker.Lock(lock_path, mode='a', timeout=1):
        result = pending.resend_due(TODAY, send_fn=sender)
    assert result == {'status': 'busy'}
    assert sender.calls == []


def test_add_evicts_other_day(env):
    seed_pending(env, ['111'], date='2026-08-15')
    pending.add(date_str=TODAY, text='t', chats=['222'], target='alarm', first_try='14:59')
    d = read_pending(env)
    assert d['date'] == TODAY
    assert [i['chats'] for i in d['items']] == [['222']]


def test_add_empty_chats_noop(env):
    pending.add(date_str=TODAY, text='t', chats=[], target='alarm', first_try='14:59')
    assert not os.path.exists(env['pending_file'])


# ==================== open_check_pending: клейм ====================

def set_claim(env, age_sec):
    d = read_pending(env)
    d['claimed_at'] = time.time() - age_sec
    with open(env['pending_file'], 'w', encoding='utf-8') as f:
        json.dump(d, f)


def test_resend_fresh_claim_busy(env):
    """Свежий клейм = другой воркер досылает прямо сейчас — не дублируем."""
    seed_pending(env, ['111'])
    set_claim(env, age_sec=30)
    sender = ScriptedSender()
    assert pending.resend_due(TODAY, send_fn=sender) == {'status': 'busy'}
    assert sender.calls == []


def test_resend_stale_claim_reclaimed(env):
    """Устаревший клейм (процесс умер во время досылки) переигрывается."""
    seed_pending(env, ['111'])
    set_claim(env, age_sec=pending._CLAIM_TTL_SEC + 60)
    sender = ScriptedSender()
    result = pending.resend_due(TODAY, send_fn=sender)
    assert result == {'status': 'ok', 'delivered': 1, 'remaining': 0}
    assert not os.path.exists(env['pending_file'])


def test_add_works_while_resend_is_sending(env):
    """Главный фикс по ревью 2026-08-16: во время сетевой фазы досылки лок
    свободен — add() со свежей тревогой 14:59 не теряется, а дописывается;
    слияние сохраняет и остаток досылки, и новое сообщение."""
    seed_pending(env, ['111', '222'], text='OLD')

    def sender(chat_id, text, html=False):
        if str(chat_id) == '111':
            # Пока идёт отправка (лок не держится) прилетает новый отчёт.
            pending.add(date_str=TODAY, text='NEW', chats=['333'],
                        target='alarm', first_try='14:59')
            return True
        return False  # '222' не доставлен — останется в очереди

    result = pending.resend_due(TODAY, send_fn=sender)
    assert result == {'status': 'ok', 'delivered': 1, 'remaining': 1}
    d = read_pending(env)
    assert d['date'] == TODAY
    assert [(i['text'], i['chats']) for i in d['items']] == [
        ('OLD', ['222']),   # остаток досылки
        ('NEW', ['333']),   # добавленное во время отправки — НЕ потеряно
    ]
    assert 'claimed_at' not in d  # клейм снят


def test_delivered_cache_prevents_duplicate_after_failed_merge(env, monkeypatch):
    """Файл не переписался после досылки (диск полон) — процессная память не
    даёт послать тот же текст тому же чату второй раз."""
    seed_pending(env, ['111', '222'])
    calls = {'n': 0}
    real_write = pending.atomic_write_json

    def flaky(path, data, **kwargs):
        calls['n'] += 1
        if calls['n'] == 2:  # 1-й вызов — клейм, 2-й — слияние остатка
            raise OSError('disk full')
        real_write(path, data, **kwargs)

    monkeypatch.setattr(pending, 'atomic_write_json', flaky)
    sender = ScriptedSender({'222': [False]})  # '111' доставлен, '222' нет
    r1 = pending.resend_due(TODAY, send_fn=sender)
    assert r1 == {'status': 'ok', 'delivered': 1, 'remaining': 1}
    # Слияние упало: на диске по-прежнему оба чата, включая уже доставленный.
    assert read_pending(env)['items'][0]['chats'] == ['111', '222']

    # Следующий тик (клейм состарим руками): '111' дубля не получает,
    # '222' доставляется, очередь очищается.
    set_claim(env, age_sec=pending._CLAIM_TTL_SEC + 60)
    sender2 = ScriptedSender()
    r2 = pending.resend_due(TODAY, send_fn=sender2)
    assert sender2.sent_to() == ['222']
    assert r2 == {'status': 'ok', 'delivered': 1, 'remaining': 0}
    assert not os.path.exists(env['pending_file'])


# ==================== Планировщик: catch-up ====================

@pytest.fixture
def sched_env(monkeypatch, tmp_path):
    lock_dir = tmp_path / 'locks'
    monkeypatch.setattr(sched, 'LOCK_DIR', str(lock_dir))
    monkeypatch.setattr(sched, 'CHECK_HOUR', 14)
    monkeypatch.setattr(sched, 'CHECK_MINUTE', 59)
    monkeypatch.setattr(sched, '_done_dates', set())
    runs = []
    monkeypatch.setattr(sched, '_run_once', lambda note=None: runs.append(note))
    return {'lock_dir': lock_dir, 'runs': runs}


def test_catch_up_runs_after_missed_time(sched_env):
    assert sched._catch_up_if_missed(now=datetime(2026, 8, 16, 16, 20)) is True
    assert len(sched_env['runs']) == 1
    assert 'перезапуска' in sched_env['runs'][0]  # честная пометка в сообщении


def test_catch_up_skips_before_check_time(sched_env):
    assert sched._catch_up_if_missed(now=datetime(2026, 8, 16, 12, 0)) is False
    assert sched_env['runs'] == []


def test_catch_up_skips_if_already_ran(sched_env):
    lock_dir = sched_env['lock_dir']
    lock_dir.mkdir(parents=True)
    (lock_dir / f'{sched.LOCK_PREFIX}2026-08-16').write_text('1')
    assert sched._catch_up_if_missed(now=datetime(2026, 8, 16, 16, 20)) is False
    assert sched_env['runs'] == []


def test_catch_up_exactly_at_check_minute_runs(sched_env):
    """Граница: рестарт ровно в 14:59:00 — проверка не должна потеряться."""
    assert sched._catch_up_if_missed(now=datetime(2026, 8, 16, 14, 59, 0)) is True
    assert len(sched_env['runs']) == 1


# ==================== Планировщик: падение run_check -> тревога ====================

@pytest.fixture
def run_env(monkeypatch, tmp_path):
    """Изоляция _run_once/recovery: свой LOCK_DIR и чистая память дней."""
    lock_dir = tmp_path / 'locks'
    monkeypatch.setattr(sched, 'LOCK_DIR', str(lock_dir))
    monkeypatch.setattr(sched, 'CHECK_HOUR', 14)
    monkeypatch.setattr(sched, 'CHECK_MINUTE', 59)
    monkeypatch.setattr(sched, '_done_dates', set())
    return {'lock_dir': lock_dir}


def test_run_once_crash_sends_alarm(run_env, monkeypatch):
    def boom(check_dt=None, note=None, queue_failures=True):
        raise RuntimeError('unexpected bug')
    monkeypatch.setattr(sched, 'run_check', boom)

    alarms = []
    monkeypatch.setattr(sched, 'send_crash_alarm',
                        lambda dt, err: alarms.append((dt, err)) or {'sent': 1})

    sched._run_once()
    assert len(alarms) == 1
    assert 'unexpected bug' in alarms[0][1]


def test_run_once_crash_alarm_crash_is_contained(run_env, monkeypatch, capsys):
    """Даже двойное падение (run_check + send_crash_alarm) не роняет поток."""
    monkeypatch.setattr(sched, 'run_check',
                        lambda check_dt=None, note=None, queue_failures=True:
                        (_ for _ in ()).throw(RuntimeError('x')))
    monkeypatch.setattr(sched, 'send_crash_alarm',
                        lambda dt, err: (_ for _ in ()).throw(RuntimeError('y')))
    sched._run_once()  # не должно бросить
    out = capsys.readouterr().out
    assert 'send_crash_alarm тоже упал' in out


def test_run_once_marks_lock_done(run_env, monkeypatch):
    """Штатный прогон оставляет в lock маркер 'done' — recovery его не тронет."""
    monkeypatch.setattr(sched, 'run_check',
                        lambda check_dt=None, note=None, queue_failures=True: {})
    sched._run_once()
    date_str = sched.now_msk().strftime('%Y-%m-%d')
    assert sched._lock_content(date_str).startswith('done')


def test_run_once_lock_oserror_sends_alarm(run_env, monkeypatch):
    """Диск не даёт создать lock: раньше OSError тихо съедал день,
    теперь уходит crash-тревога (Telegram диска не требует)."""
    def no_disk(date_str):
        raise OSError('No space left on device')
    monkeypatch.setattr(sched, '_try_acquire_daily_lock', no_disk)
    ran, alarms = [], []
    monkeypatch.setattr(sched, 'run_check',
                        lambda **kw: ran.append(1))
    monkeypatch.setattr(sched, 'send_crash_alarm',
                        lambda dt, err: alarms.append(err) or {'sent': 1})
    sched._run_once()  # не бросает
    assert ran == []  # без lock-а проверку не запускаем (дубль от 2-го воркера)
    assert len(alarms) == 1 and 'lock-файл не создан' in alarms[0]


# ==================== Планировщик: recovery прерванного прогона ====================

RECOVERY_NOW = datetime(2026, 8, 16, 16, 20)  # > 14:59 + 15 мин grace


def write_lock(run_env, content, age_sec=None, date='2026-08-16'):
    lock_dir = run_env['lock_dir']
    lock_dir.mkdir(parents=True, exist_ok=True)
    p = lock_dir / f'{sched.LOCK_PREFIX}{date}'
    p.write_text(content, encoding='utf-8')
    if age_sec is not None:
        old = time.time() - age_sec
        os.utime(p, (old, old))
    return p


def test_recovery_reruns_interrupted_run(run_env, monkeypatch):
    """Lock 'running' со старым mtime = процесс убит посреди прогона
    (SIGTERM деплоя / рецикл gunicorn) — проверка переигрывается."""
    write_lock(run_env, 'running 123\n', age_sec=sched._RUN_GRACE_SEC + 120)
    runs = []
    monkeypatch.setattr(sched, 'run_check',
                        lambda check_dt=None, note=None, queue_failures=True:
                        runs.append(note) or {})
    assert sched._recover_interrupted_run(now=RECOVERY_NOW) is True
    assert len(runs) == 1 and 'прервана' in runs[0]
    assert sched._lock_content('2026-08-16').startswith('done')
    # Повторный тик — день уже закрыт.
    assert sched._recover_interrupted_run(now=RECOVERY_NOW) is False
    assert len(runs) == 1


def test_recovery_skips_done_lock(run_env, monkeypatch):
    write_lock(run_env, 'done\n', age_sec=7200)
    monkeypatch.setattr(sched, 'run_check',
                        lambda **kw: pytest.fail('не должен вызываться'))
    assert sched._recover_interrupted_run(now=RECOVERY_NOW) is False


def test_recovery_skips_old_format_pid_lock(run_env, monkeypatch):
    """Lock старого формата (только pid) — день до деплоя отработал; повторный
    прогон в день выката дал бы дубль."""
    write_lock(run_env, '12345\n', age_sec=7200)
    monkeypatch.setattr(sched, 'run_check',
                        lambda **kw: pytest.fail('не должен вызываться'))
    assert sched._recover_interrupted_run(now=RECOVERY_NOW) is False


def test_recovery_skips_fresh_running_lock(run_env, monkeypatch):
    """Свежий 'running' — прогон, возможно, ещё идёт (долгие таймауты отправки)."""
    write_lock(run_env, 'running 123\n', age_sec=60)
    monkeypatch.setattr(sched, 'run_check',
                        lambda **kw: pytest.fail('не должен вызываться'))
    assert sched._recover_interrupted_run(now=RECOVERY_NOW) is False


def test_recovery_waits_grace_after_target(run_env, monkeypatch):
    """До target+grace recovery молчит — штатный прогон мог ещё не закончиться."""
    write_lock(run_env, 'running 123\n', age_sec=sched._RUN_GRACE_SEC + 120)
    monkeypatch.setattr(sched, 'run_check',
                        lambda **kw: pytest.fail('не должен вызываться'))
    assert sched._recover_interrupted_run(now=datetime(2026, 8, 16, 15, 5)) is False


def test_recovery_no_lock_runs_check(run_env, monkeypatch):
    """Спустя grace после 14:59 lock-а нет вообще (поток проверки мёртв) —
    recovery запускает _run_once сам."""
    runs = []
    monkeypatch.setattr(sched, '_run_once', lambda note=None: runs.append(note))
    assert sched._recover_interrupted_run(now=RECOVERY_NOW) is True
    assert len(runs) == 1 and 'контрольным циклом' in runs[0]
