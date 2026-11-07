"""
Тесты транспорта open-check бота (core/open_check_telegram.api_call): повтор
при обрыве соединения, который добавлен 2026-09-28 — ночью ТСПУ «мигал», и
бот с одной попыткой на адрес отвечал примерно через раз.

Self-runnable: `py -3 tests/test_open_check_transport.py` (совместимо с pytest).

Сети нет: requests.post и _post_via_ip подменяются. Что проверяется:
- основной путь: таймаут соединения повторяется до CONNECT_ATTEMPTS раз,
  успех на второй попытке — ответ без перехода на запасные;
- таймаут чтения не повторяется (сообщение могло уйти — повтор дал бы дубль);
- основной путь мёртв: первый запасной адрес повторяется до CONNECT_ATTEMPTS,
  остальные — по разу; все провалились — None;
- connect-таймаут в запросе — CONNECT_TIMEOUT.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import requests  # noqa: E402

from core import open_check_telegram as tg  # noqa: E402


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _Patch:
    """Подмена requests.post / _post_via_ip / DoH и сброс состояния основного пути."""

    def __init__(self, post_script, ip_script=None):
        self.post_script, self.ip_script = list(post_script), dict(ip_script or {})
        self.post_calls, self.ip_calls = [], []

    def __enter__(self):
        self.saved = (tg.requests.post, tg._post_via_ip, tg._doh_resolve, tg._primary_dead_until,
                      tg._working_ip, os.environ.get('TELEGRAM_OPEN_CHECK_BOT_TOKEN'))
        os.environ['TELEGRAM_OPEN_CHECK_BOT_TOKEN'] = 'test-token'
        tg._primary_dead_until, tg._working_ip = 0.0, None
        tg._doh_resolve = lambda: []

        def post(url, json=None, timeout=None):
            self.post_calls.append(timeout)
            r = self.post_script.pop(0)
            if isinstance(r, Exception):
                raise r
            return _Resp(r)

        def via_ip(ip, method, token, payload, timeout):
            self.ip_calls.append(ip)
            script = self.ip_script.get(ip, [])
            r = script.pop(0) if script else requests.exceptions.ConnectTimeout('blocked')
            if isinstance(r, Exception):
                raise r
            return r
        tg.requests.post = post
        tg._post_via_ip = via_ip
        return self

    def __exit__(self, *exc):
        (tg.requests.post, tg._post_via_ip, tg._doh_resolve, tg._primary_dead_until,
         tg._working_ip, token) = self.saved
        if token is None:
            os.environ.pop('TELEGRAM_OPEN_CHECK_BOT_TOKEN', None)
        else:
            os.environ['TELEGRAM_OPEN_CHECK_BOT_TOKEN'] = token


CT = requests.exceptions.ConnectTimeout
OK = {'ok': True, 'result': {}}


def test_primary_retries_connect_timeout():
    with _Patch([CT('flap'), OK]) as p:
        assert tg.api_call('sendMessage', {'chat_id': 1, 'text': 'x'}) == OK
        assert len(p.post_calls) == 2 and p.ip_calls == []
        assert p.post_calls[0] == (tg.CONNECT_TIMEOUT, 8)
        assert tg._primary_dead_until == 0.0          # основной путь не объявлен мёртвым


def test_read_timeout_not_retried():
    with _Patch([requests.exceptions.ReadTimeout('slow')], {tg._FALLBACK_IPS[0]: [OK]}) as p:
        assert tg.api_call('sendMessage', {}) == OK
        assert len(p.post_calls) == 1                 # без повтора основного пути
        assert p.ip_calls == [tg._FALLBACK_IPS[0]]


def test_fallback_first_ip_retried_others_once():
    dead = [CT('x')] * tg.CONNECT_ATTEMPTS
    first, second = tg._FALLBACK_IPS[0], tg._FALLBACK_IPS[1]
    with _Patch(dead, {first: [CT('a'), CT('b'), OK]}) as p:
        assert tg.api_call('getUpdates', {}) == OK
        assert len(p.post_calls) == tg.CONNECT_ATTEMPTS
        assert p.ip_calls == [first] * 3 and tg._working_ip == first
    with _Patch(dead) as p:
        assert tg.api_call('getUpdates', {}) is None
        assert p.ip_calls == [first] * tg.CONNECT_ATTEMPTS + [second]


if __name__ == '__main__':
    import inspect
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and inspect.isfunction(fn):
            try:
                fn()
                print(f'ok   {name}')
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f'FAIL {name}: {e!r}')
    sys.exit(1 if failed else 0)


# ------------------------------------------------------------------ имя kultura.pulse (2026-11-07)

def test_bot_name_and_descriptions_fit_telegram():
    assert tg.BOT_NAME == 'kultura.pulse'
    assert 0 < len(tg.BOT_NAME) <= 64 and 0 < len(tg.BOT_SHORT_DESCRIPTION) <= 120
    assert 0 < len(tg.BOT_DESCRIPTION) <= 512
    assert tg._start_text(42, False).startswith('kultura.pulse — пульс баров'), 'бот называет себя так же'


def test_sync_profile_sets_only_what_differs(monkeypatch, tmp_path):
    monkeypatch.setattr(tg, '_profile_state_path', lambda: str(tmp_path / 'open_check_profile.json'))
    stored = {'name': 'KULT open check', 'short_description': tg.BOT_SHORT_DESCRIPTION, 'description': ''}
    calls = []

    def fake_api_call(method, payload=None, timeout=8, **kwargs):
        calls.append(method)
        assert 'token' not in kwargs, 'свой бот — токен open-check по умолчанию'
        if method == 'getMe':
            return {'ok': True, 'result': {'username': 'kultura_open_bot'}}
        for field, getter, setter, _ in tg.PROFILE_METHODS:
            if method == getter:
                return {'ok': True, 'result': {field: stored[field]}}
            if method == setter:
                stored[field] = payload[field]
                return {'ok': True, 'result': True}
        raise AssertionError(method)

    monkeypatch.setattr(tg, 'api_call', fake_api_call)
    monkeypatch.setattr(tg, '_sync_avatar', lambda errors=None: 'same')
    assert tg.sync_profile() == {'name': 'set', 'short_description': 'same', 'description': 'set', 'avatar': 'same'}
    assert stored == {'name': 'kultura.pulse', 'short_description': tg.BOT_SHORT_DESCRIPTION,
                      'description': tg.BOT_DESCRIPTION}
    calls.clear()
    assert set(tg.sync_profile().values()) == {'same'}
    assert all(m.startswith('getMy') or m == 'getMe' for m in calls), 'всё на месте — ничего не ставит'
    monkeypatch.setattr(tg, 'api_call', lambda *a, **k: None)
    silent = tg.sync_profile()
    assert {silent[f] for f in ('name', 'short_description', 'description')} == {'no_answer'}, \
        'Telegram молчит — без падения'


def _mp4(data):
    """(секунд, ширина, высота, есть ли звук) — по коробкам mvhd и tkhd, без ffprobe."""
    i = data.find(b'mvhd') + 4
    if data[i] == 1:
        scale, dur = int.from_bytes(data[i + 20:i + 24], 'big'), int.from_bytes(data[i + 24:i + 32], 'big')
    else:
        scale, dur = int.from_bytes(data[i + 12:i + 16], 'big'), int.from_bytes(data[i + 16:i + 20], 'big')
    box = data.find(b'tkhd') - 4
    end = box + int.from_bytes(data[box:box + 4], 'big')
    return (dur / scale, int.from_bytes(data[end - 8:end - 4], 'big') >> 16,
            int.from_bytes(data[end - 4:end], 'big') >> 16, b'soun' in data)


def test_pulse_avatar_is_a_telegram_profile_video():
    data = open(tg.BOT_AVATAR, 'rb').read()
    assert data[4:8] == b'ftyp', 'живая аватарка — MPEG4 (GIF Telegram для аватарки не берёт)'
    seconds, width, height, sound = _mp4(data)
    assert seconds <= 10 and width == height and 160 <= width <= 1280 and not sound and len(data) <= 2 * 1024 * 1024
    assert 0 < tg.BOT_AVATAR_MAIN_FRAME_S < seconds


def test_pulse_avatar_is_uploaded_once_per_file(monkeypatch, tmp_path):
    state = tmp_path / 'open_check_profile.json'
    monkeypatch.setattr(tg, '_profile_state_path', lambda: str(state))
    monkeypatch.setattr(tg, '_token', lambda: '12345:secret')
    uploads = []

    def fake_files(method, fields=None, files=None, **kwargs):
        uploads.append((method, json.loads(fields['photo']), files[0][:2], files[0][3]))
        assert 'token' not in kwargs, 'свой бот — токен open-check по умолчанию'
        return {'ok': True, 'result': True}

    monkeypatch.setattr(tg, 'api_call_files', fake_files)
    assert tg._sync_avatar() == 'set'
    assert uploads == [('setMyProfilePhoto', {'type': 'animated', 'animation': 'attach://avatar',
                                               'main_frame_timestamp': tg.BOT_AVATAR_MAIN_FRAME_S},
                        ('avatar', 'avatar.mp4'), 'video/mp4')]
    assert '12345:secret' not in state.read_text(encoding='utf-8'), 'в файле — id бота, не токен'
    assert tg._sync_avatar() == 'same' and len(uploads) == 1, 'тот же файл — второй раз не грузится'
    monkeypatch.setattr(tg, '_token', lambda: '777:other')
    assert tg._sync_avatar() == 'set' and len(uploads) == 2, 'другой бот — ставится заново'
    monkeypatch.setattr(tg, 'api_call_files', lambda *a, **k: {'ok': False, 'description': 'Bad Request'})
    monkeypatch.setattr(tg, '_token', lambda: '888:third')
    assert tg._sync_avatar() == 'error'
    monkeypatch.setattr(tg, 'BOT_AVATAR', str(tmp_path / 'нет.mp4'))
    assert tg._sync_avatar() == 'no_file'


def test_sync_records_what_telegram_answered(monkeypatch, tmp_path):
    state = tmp_path / 'open_check_profile.json'
    monkeypatch.setattr(tg, '_profile_state_path', lambda: str(state))
    monkeypatch.setattr(tg, '_token', lambda: '12345:secret')

    def fake_api_call(method, payload=None, timeout=8, **kwargs):
        if method == 'getMe':
            return {'ok': True, 'result': {'username': 'kultura_open_bot'}}
        if method.startswith('getMy'):
            field = {'getMyName': 'name', 'getMyShortDescription': 'short_description',
                     'getMyDescription': 'description'}[method]
            return {'ok': True, 'result': {field: getattr(tg, {'name': 'BOT_NAME', 'short_description':
                                                               'BOT_SHORT_DESCRIPTION', 'description':
                                                               'BOT_DESCRIPTION'}[field])}}
        raise AssertionError(method)

    monkeypatch.setattr(tg, 'api_call', fake_api_call)
    monkeypatch.setattr(tg, 'api_call_files', lambda *a, **k: {'ok': False, 'error_code': 400,
                                                               'description': 'Bad Request: PHOTO_INVALID'})
    result = tg.sync_profile()
    assert result == {'name': 'same', 'short_description': 'same', 'description': 'same', 'avatar': 'error'}
    last = tg.profile_status()['last']
    assert last['bot'] == 'kultura_open_bot', 'какой бот на самом деле у токена'
    assert last['errors'] == {'avatar': 'Bad Request: PHOTO_INVALID'} and last['at'].endswith('+03:00')
    assert 'secret' not in state.read_text(encoding='utf-8')


def test_pulse_avatar_is_the_light_version():
    assert tg.BOT_AVATAR.endswith('kultura-pulse-grid-light.mp4'), 'для ботов — светлая версия (2026-11-07)'


def test_polling_retries_profile_hourly_when_something_failed(monkeypatch):
    from core import open_check_polling as poll

    class Fake:
        PROFILE_RETRY_S = tg.PROFILE_RETRY_S
        answers = [{'name': 'same', 'avatar': 'error'}, {'name': 'same', 'avatar': 'set'}]

        @staticmethod
        def sync_profile():
            return Fake.answers.pop(0)

        @staticmethod
        def _scrub(e):
            return str(e)

    monkeypatch.setattr(poll.time, 'time', lambda: 1000.0)
    assert poll._sync_profile(Fake) == 1000.0 + tg.PROFILE_RETRY_S, 'не встало — ещё раз через час'
    assert poll._sync_profile(Fake) == 0.0, 'встало — больше не сверяем до перезапуска'
