"""
Тесты тревог по температуре (core/temperature_alarm.evaluate): «жарко» и
добавленное 2026-09-28 «холодно» (ниже 19 C — решение владельца).

Self-runnable: `py -3 tests/test_temperature_alarm.py` (совместимо с pytest).

В Telegram ничего не уходит: хранилище состояний, отправка и тихие часы
подменяются. Что проверяется:
- «холодно»: ниже 19 — одна тревога; повторные опросы — тишина; зона
  гистерезиса 19..20 состояние не меняет; выше 20 — снятие без сообщения,
  следующий холод снова тревожит;
- «жарко» работает как раньше, состояния «жарко» и «холодно» независимы;
- отправка не удалась — состояние откатывается, следующий опрос повторяет;
- тихие часы и отсутствие токена — ни тревог, ни изменения состояния;
- пороги из окружения, снятие «холодно» не ниже порога.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import temperature_alarm as ta  # noqa: E402


class FakeStore:
    """set_alarm_state как в temperature_store: True только при реальном переходе."""

    def __init__(self):
        self.state = {}

    def set_alarm_state(self, key, alarming):
        target = bool(alarming)
        if self.state.get(key, False) == target:
            return False
        self.state[key] = target
        return True


class Rig:
    def __init__(self, send_ok=True, quiet=False, env=None):
        self.store, self.sent, self.send_ok, self.quiet = FakeStore(), [], send_ok, quiet
        self.env = {'TELEGRAM_OPEN_CHECK_BOT_TOKEN': 'x', 'TUYA_ALARM_TEMP_C': None, 'TUYA_ALARM_CLEAR_C': None,
                    'TUYA_ALARM_COLD_C': None, 'TUYA_ALARM_COLD_CLEAR_C': None}
        self.env.update(env or {})

    def __enter__(self):
        self.saved = (ta.get_store, ta._send, ta._in_quiet_hours, ta._now_hhmm,
                      {k: os.environ.get(k) for k in self.env})
        ta.get_store = lambda: self.store
        ta._send = lambda text: self.sent.append(text) or self.send_ok
        ta._in_quiet_hours = lambda: self.quiet
        ta._now_hhmm = lambda: '18:00'
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        ta.get_store, ta._send, ta._in_quiet_hours, ta._now_hhmm, env = self.saved
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def poll(self, **temps):
        ta.evaluate({bar: {'temperature': t} for bar, t in temps.items()})


def test_cold_alarm_once_hysteresis_and_clear():
    with Rig() as r:
        r.poll(bolshoy=18.4)
        assert len(r.sent) == 1 and 'ХОЛОДНО В БАРЕ' in r.sent[0] and '18.4 C' in r.sent[0]
        assert 'Порог 19 C' in r.sent[0]
        r.poll(bolshoy=17.0)
        r.poll(bolshoy=19.6)                  # зона гистерезиса 19..20 — тревога держится
        r.poll(bolshoy=18.9)
        assert len(r.sent) == 1
        r.poll(bolshoy=20.4)                  # выше 20 — снято молча
        assert len(r.sent) == 1 and r.store.state['bolshoy:cold'] is False
        r.poll(bolshoy=18.0)                  # новый холод — новая тревога
        assert len(r.sent) == 2


def test_boundaries_exact_threshold_no_alarm():
    with Rig() as r:
        r.poll(bolshoy=19.0, ligovskiy=26.0)  # ровно на порогах — не тревога
        assert r.sent == []


def test_hot_unchanged_and_independent_from_cold():
    with Rig() as r:
        r.poll(bolshoy=27.0, ligovskiy=18.0)
        assert sorted(t.split('\n')[0] for t in r.sent) == ['<b>!!! ЖАРКО В БАРЕ !!!</b>',
                                                           '<b>!!! ХОЛОДНО В БАРЕ !!!</b>']
        assert r.store.state == {'bolshoy': True, 'ligovskiy:cold': True}
        r.poll(bolshoy=24.0, ligovskiy=21.0)  # оба ушли в норму — молча
        assert len(r.sent) == 2 and not any(r.store.state.values())


def test_failed_send_rolls_back_and_retries():
    with Rig(send_ok=False) as r:
        r.poll(varshavskaya=17.5)
        assert r.store.state['varshavskaya:cold'] is False
        r.send_ok = True
        r.poll(varshavskaya=17.5)
        assert len(r.sent) == 2 and r.store.state['varshavskaya:cold'] is True


def test_quiet_hours_and_no_token_do_nothing():
    with Rig(quiet=True) as r:
        r.poll(bolshoy=15.0)
        assert r.sent == [] and r.store.state == {}
    with Rig(env={'TELEGRAM_OPEN_CHECK_BOT_TOKEN': None}) as r:
        r.poll(bolshoy=15.0)
        assert r.sent == [] and r.store.state == {}


def test_thresholds_from_env():
    with Rig(env={'TUYA_ALARM_COLD_C': '17', 'TUYA_ALARM_COLD_CLEAR_C': '16'}) as r:
        assert ta._cold_temp() == 17.0 and ta._cold_clear_temp(17.0) == 17.0   # снятие не ниже порога
        r.poll(bolshoy=18.0)
        assert r.sent == []
    with Rig(env={'TUYA_ALARM_COLD_C': 'мусор'}) as r:
        assert ta._cold_temp() == 19.0 and ta._cold_clear_temp(19.0) == 20.0


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
