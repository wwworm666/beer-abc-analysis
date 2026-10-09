"""
Тесты сторожа отзывов с Яндекс Карт (core/yandex_reviews_watchdog.py).

Self-runnable: `py -3 tests/test_yandex_reviews_watchdog.py` (совместимо с pytest).

В Telegram ничего не уходит: доставка подменяется фейком. Что проверяется:
- stale: бар не читался удачно больше 24 часов (ровно 24 — ещё нет); без
  удачного чтения отсчёт от первой проверки Карт; файл от кабинета — не тревога;
- behind: на Картах больше отзывов дольше 6 часов (ровно 6 — ещё нет);
- одно сообщение на поломку: повтор молчит, новый бар — новое сообщение, все
  восстановились — «снова в порядке», часть восстановилась — молча;
- не доставлено — не отмечено (повтор на следующем такте);
- выключатель, занятый замок, текст (бары, числа, ошибка экранирована, ссылка, без эмодзи);
- notify_subscribers: без токена и подписчиков — не доставлено, DRY-RUN — одному.
"""
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from core import review_notify as rn  # noqa: E402
from core import yandex_reviews_watchdog as wd  # noqa: E402

NOW = datetime(2026, 10, 10, 15, 0)
ALL = ('kremenchugskaya', 'bolshoy', 'varshavskaya', 'ligovskiy')


@pytest.fixture
def path():
    tmp = tempfile.mkdtemp(prefix='wd_test_')
    yield os.path.join(tmp, 'state.json')
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key in ('YANDEX_REVIEWS_WATCHDOG', 'YANDEX_REVIEWS_SYNC_ENABLED', 'OPEN_CHECK_DRY_RUN'):
        monkeypatch.delenv(key, raising=False)


def state(**bars):
    """Состояние загрузки с Карт: все бары прочитаны в 14:00, отставания нет; bars — правки."""
    base = {bar: {'synced_at': '2026-10-10T14:00', 'count': 100, 'ours': 100, 'behind_since': None,
                  'error': None} for bar in ALL}
    for bar, over in bars.items():
        base[bar].update(over)
    return {'source': 'maps', 'source_since': '2026-10-09T15:00', 'status': 'ok',
            'finished_at': '2026-10-10T14:00', 'bars': base}


def write(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def read(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


class Deliver:
    def __init__(self, ok=True):
        self.ok, self.texts = ok, []

    def __call__(self, text, now_str):
        self.texts.append(text)
        return {'delivered': self.ok}


# ----------------------------------------------------------------- условия

def test_stale_after_more_than_24_hours():
    s = state(bolshoy={'synced_at': '2026-10-09T15:00'}, varshavskaya={'synced_at': '2026-10-09T14:59'})
    alerts = wd.evaluate(s, NOW)
    assert [a['bar'] for a in alerts['stale']] == ['varshavskaya']            # ровно 24 ч — ещё нет
    assert alerts['stale'][0] == {'bar': 'varshavskaya', 'since': '2026-10-09T14:59', 'never': False}
    s = state(ligovskiy={'synced_at': None})
    assert wd.evaluate(s, NOW)['stale'] == []                                # от source_since — ровно 24 ч
    assert wd.evaluate(s, datetime(2026, 10, 10, 15, 1))['stale'] == [
        {'bar': 'ligovskiy', 'since': '2026-10-09T15:00', 'never': True}]
    assert wd.evaluate({'status': 'expired', 'bars': {}}, NOW) == {'stale': [], 'behind': []}


def test_behind_after_more_than_6_hours():
    s = state(kremenchugskaya={'count': 110, 'ours': 108, 'behind_since': '2026-10-10T09:00'},
              bolshoy={'count': 101, 'ours': 100, 'behind_since': '2026-10-10T08:59'})
    assert wd.evaluate(s, NOW)['behind'] == [
        {'bar': 'bolshoy', 'count': 101, 'ours': 100, 'since': '2026-10-10T08:59'}]


# ----------------------------------------------------------------- сообщения

def test_one_message_per_incident_then_recovery(path):
    deliver = Deliver()
    write(path, state(kremenchugskaya={'synced_at': '2026-10-09T10:00', 'error': 'Карты ответили кодом <503>'}))
    assert wd.check(path, NOW, deliver=deliver)['stale'] == 'sent'
    text = deliver.texts[-1]
    assert 'Отзывы с Яндекс Карт не обновляются' in text and 'Кременчугская' in text
    assert '9 октября 2026, 10:00' in text and '&lt;503&gt;' in text and text.endswith('/reviews?month=all')
    assert not re.search('[\U0001F300-\U0001FAFF☀-➿]', text)
    assert read(path)['watchdog'] == {'stale': ['kremenchugskaya'], 'stale_at': '2026-10-10T15:00'}
    # Повтор — молчит.
    assert wd.check(path, NOW, deliver=deliver) == {'stale': None, 'behind': None, 'skipped': None}
    assert len(deliver.texts) == 1
    # Ещё один бар — новое сообщение со всеми.
    s = read(path)
    s['bars']['bolshoy']['synced_at'] = '2026-10-09T09:00'
    write(path, s)
    assert wd.check(path, NOW, deliver=deliver)['stale'] == 'sent'
    assert 'Кременчугская' in deliver.texts[-1] and 'Большой' in deliver.texts[-1]
    # Один восстановился — молча сужается.
    s = read(path)
    s['bars']['kremenchugskaya']['synced_at'] = '2026-10-10T14:30'
    write(path, s)
    assert wd.check(path, NOW, deliver=deliver)['stale'] is None and len(deliver.texts) == 2
    assert read(path)['watchdog']['stale'] == ['bolshoy']
    # Все в порядке — «снова обновляются».
    s = read(path)
    s['bars']['bolshoy']['synced_at'] = '2026-10-10T14:45'
    write(path, s)
    assert wd.check(path, NOW, deliver=deliver)['stale'] == 'recovered'
    assert 'снова обновляются' in deliver.texts[-1] and read(path)['watchdog']['stale'] == []


def test_behind_message_has_numbers(path):
    deliver = Deliver()
    write(path, state(varshavskaya={'count': 105, 'ours': 101, 'behind_since': '2026-10-10T06:00',
                                    'error': 'Карты не листают страницы отзывов'}))
    assert wd.check(path, NOW, deliver=deliver)['behind'] == 'sent'
    text = deliver.texts[-1]
    assert 'На Яндекс Картах больше отзывов, чем в сервисе' in text
    assert 'Варшавская — на Картах 105, у нас 101 (с 10 октября 2026, 06:00)' in text
    assert 'не листают' in text
    s = read(path)
    s['bars']['varshavskaya'].update(count=105, ours=105, behind_since=None)
    write(path, s)
    assert wd.check(path, NOW, deliver=deliver)['behind'] == 'recovered'
    assert 'поровну' in deliver.texts[-1]


def test_not_delivered_is_retried(path):
    write(path, state(ligovskiy={'synced_at': '2026-10-08T10:00'}))
    assert wd.check(path, NOW, deliver=Deliver(ok=False))['stale'] == 'not_sent'
    assert 'watchdog' not in read(path)
    deliver = Deliver()
    assert wd.check(path, NOW, deliver=deliver)['stale'] == 'sent' and len(deliver.texts) == 1


def test_switch_lock_and_cabinet_state(path, monkeypatch):
    write(path, state(ligovskiy={'synced_at': '2026-10-08T10:00'}))
    deliver = Deliver()
    monkeypatch.setenv('YANDEX_REVIEWS_WATCHDOG', '0')
    assert wd.check(path, NOW, deliver=deliver)['skipped'] == 'disabled'
    monkeypatch.delenv('YANDEX_REVIEWS_WATCHDOG')
    monkeypatch.setenv('YANDEX_REVIEWS_SYNC_ENABLED', '0')
    assert wd.check(path, NOW, deliver=deliver)['skipped'] == 'disabled'
    monkeypatch.delenv('YANDEX_REVIEWS_SYNC_ENABLED')
    import portalocker
    with portalocker.Lock(path + '.lock', mode='a', timeout=0):
        assert wd.check(path, NOW, deliver=deliver)['skipped'] == 'busy'
    write(path, {'status': 'expired', 'bars': {}})
    assert wd.check(path, NOW, deliver=deliver)['skipped'] == 'no_state'
    assert deliver.texts == []


# ----------------------------------------------------------------- доставка подписчикам

def test_notify_subscribers(monkeypatch):
    sent, queued = [], []

    def send(chats, text):
        sent.append((list(chats), text))
        return {'sent': 1, 'failed': list(chats[1:])}
    kw = dict(send=send, recipients=lambda: ['1', '2'], queue=lambda *a: queued.append(a))
    monkeypatch.delenv('TELEGRAM_OPEN_CHECK_BOT_TOKEN', raising=False)
    assert rn.notify_subscribers('x', '2026-10-10T15:00', **kw)['skipped'] == 'no_token'
    monkeypatch.setenv('TELEGRAM_OPEN_CHECK_BOT_TOKEN', 'test-token')
    assert rn.notify_subscribers('x', '2026-10-10T15:00', send=send, recipients=lambda: [],
                                 queue=kw['queue'])['skipped'] == 'no_recipients'
    res = rn.notify_subscribers('<b>Сторож</b>', '2026-10-10T15:00', **kw)
    assert res['delivered'] and res['sent_messages'] == 1 and res['queued_chats'] == 1
    assert sent[-1] == (['1', '2'], '<b>Сторож</b>') and queued[-1][2] == ['2']
    monkeypatch.setenv('OPEN_CHECK_DRY_RUN', '1')
    rn.notify_subscribers('t', '2026-10-10T15:00', **kw)
    assert sent[-1] == (['1'], '[DRY-RUN] t')


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
