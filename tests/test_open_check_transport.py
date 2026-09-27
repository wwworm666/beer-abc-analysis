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
