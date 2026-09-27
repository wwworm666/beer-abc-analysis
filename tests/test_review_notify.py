"""
Тесты рассылки новых отзывов в бот kulturaopenclosed (core/review_notify.py)
и её вызова из сверки (core/yandex_reviews_sync.sync_all).

Self-runnable: `py -3 tests/test_review_notify.py` (совместимо с pytest).

В Telegram ничего не уходит: отправитель, список подписчиков и очередь
досылки подменяются фейками; токен бота — фиктивный, только в окружении теста.
Что проверяется:
- новые = загруженные, добавлены не раньше notify_since, не отправлены;
  история до первой рассылки не шлётся; ручные не шлются;
- отправка отмечает tg_notified_at — повторная сверка не шлёт дубль;
- недоставленное -> очередь досылки, отзыв отмечен; ни одного получателя
  -> не отмечен; без токена или подписчиков — не шлётся и не отмечается;
- предохранитель: больше NOTIFY_MAX_PER_RUN — сводкой, отмечены все;
- DRY-RUN — только первому получателю, с пометкой;
- текст: HTML экранирован, длинный отзыв обрезан, низкая оценка в заголовке,
  ответ из Яндекса и ссылка на страницу;
- sync_all без notifier ничего не шлёт; с notifier — после загрузки; сбой
  рассылки не меняет статус сверки.
"""
import atexit
import os
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import msk_time  # noqa: E402
from core import review_notify as rn  # noqa: E402
from core import yandex_reviews_sync as ys  # noqa: E402
from core.guest_reviews import ReviewStore  # noqa: E402

TMP = tempfile.mkdtemp(prefix='rn_test_')
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
BY = 'Яндекс Бизнес'
_n = [0]


class _Env:
    def __init__(self, **vals):
        self.vals = vals

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in self.vals}
        for k, v in self.vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _store(now):
    _n[0] += 1
    return ReviewStore(os.path.join(TMP, f'r_{_n[0]}.json'), clock=lambda: now)


def _item(ext, created='2026-09-27T18:30', rating=5, text='Отлично', reply=None):
    return {'external_id': ext, 'created_at': created, 'rating': rating, 'text': text, 'author': 'Иван',
            'owner_reply': reply, 'photos': [], 'author_avatar': None, 'public_rating': True}


class Fake:
    def __init__(self, chats=('1', '2'), fail=()):
        self.chats, self.fail = list(chats), set(fail)
        self.sent, self.queued = [], []

    def send(self, recipients, text):
        self.sent.append((list(recipients), text))
        failed = [c for c in recipients if c in self.fail]
        return {'sent': len(recipients) - len(failed), 'failed': failed}

    def recipients(self):
        return list(self.chats)

    def queue(self, date_str, text, chats, first_try):
        self.queued.append((date_str, chats, first_try))

    def run(self, store, state, now_str):
        return rn.notify_new_reviews(store, state, now_str, send=self.send, recipients=self.recipients,
                                     queue=self.queue)


TOKEN = {'TELEGRAM_OPEN_CHECK_BOT_TOKEN': 'fake-token', 'OPEN_CHECK_DRY_RUN': None}


def _history_then_new(fake):
    """История загружена в 00:38; первая рассылка в 08:30 с одним новым отзывом."""
    s0 = _store(datetime(2026, 9, 28, 0, 38))
    s0.upsert_imported('yandex', 'bolshoy', [_item('old1', created='2025-01-01T10:00'), _item('old2')],
                       history_cutoff='2026-08-29', complete=True, by=BY)
    s = ReviewStore(s0.data_file, clock=lambda: datetime(2026, 9, 28, 8, 30))
    s.upsert_imported('yandex', 'bolshoy', [_item('old1', created='2025-01-01T10:00'), _item('old2'),
                                            _item('new1', rating=2, text='Долго ждали <b>')],
                      history_cutoff='2026-08-29', complete=True, by=BY)
    state = {'started_at': '2026-09-28T08:30'}
    with _Env(**TOKEN):
        res = fake.run(s, state, '2026-09-28T08:31')
    return s, state, res


def test_only_new_after_baseline_sent_once():
    fake = Fake()
    s, state, res = _history_then_new(fake)
    assert res['candidates'] == 1 and res['sent_messages'] == 1 and state['notify_since'] == '2026-09-28T08:30'
    assert len(fake.sent) == 1 and fake.sent[0][0] == ['1', '2']
    by_ext = {r['external_id']: r for r in s.all()}
    assert by_ext['new1']['tg_notified_at'] == '2026-09-28T08:31'
    assert not by_ext['old1']['tg_notified_at'] and not by_ext['old2']['tg_notified_at']
    with _Env(**TOKEN):
        again = fake.run(s, state, '2026-09-29T08:31')
    assert again['candidates'] == 0 and len(fake.sent) == 1


def test_manual_reviews_not_sent():
    s = _store(datetime(2026, 9, 28, 8, 30))
    s.add({'source': 'yandex', 'bar': 'bolshoy', 'rating': 5, 'text': 'руками', 'created_at': '2026-09-28T08:00'},
          {'login': 'owner'})
    assert rn.candidates(s.all(), '2026-09-28T00:00') == []


def test_failed_chat_queued_and_marked():
    fake = Fake(fail={'2'})
    s, _, res = _history_then_new(fake)
    assert res['queued_chats'] == 1 and fake.queued == [('2026-09-28', ['2'], '08:31')]
    assert {r['external_id']: r for r in s.all()}['new1']['tg_notified_at']


def test_no_token_or_no_recipients_not_marked():
    s = _store(datetime(2026, 9, 28, 8, 30))
    s.upsert_imported('yandex', 'bolshoy', [_item('n')], history_cutoff='2026-08-29', complete=True, by=BY)
    fake = Fake()
    with _Env(TELEGRAM_OPEN_CHECK_BOT_TOKEN=None):
        res = fake.run(s, {'started_at': '2026-09-28T08:30'}, '2026-09-28T08:31')
    assert res['skipped'] == 'no_token' and fake.sent == []
    with _Env(**TOKEN):
        res = Fake(chats=()).run(s, {'started_at': '2026-09-28T08:30'}, '2026-09-28T08:31')
    assert res['skipped'] == 'no_recipients'
    assert not s.all()[0]['tg_notified_at']


def test_all_chats_failed_in_dry_run_not_marked():
    s = _store(datetime(2026, 9, 28, 8, 30))
    s.upsert_imported('yandex', 'bolshoy', [_item('n')], history_cutoff='2026-08-29', complete=True, by=BY)
    fake = Fake(fail={'1', '2'})
    with _Env(TELEGRAM_OPEN_CHECK_BOT_TOKEN='x', OPEN_CHECK_DRY_RUN='1'):
        res = fake.run(s, {'started_at': '2026-09-28T08:30'}, '2026-09-28T08:31')
    assert fake.sent[0][0] == ['1'] and fake.sent[0][1].startswith('[DRY-RUN] ')
    assert fake.queued == [] and res['sent_messages'] == 0
    assert not s.all()[0]['tg_notified_at']       # в dry-run очереди нет — не доставлено, не отмечено


def test_overflow_summary_and_all_marked():
    s = _store(datetime(2026, 9, 28, 8, 30))
    items = [_item(f'x{i:02d}', created=f'2026-09-27T{10 + i % 10:02d}:{i:02d}') for i in range(13)]
    s.upsert_imported('yandex', 'bolshoy', items, history_cutoff='2026-08-29', complete=True, by=BY)
    fake = Fake()
    with _Env(**TOKEN):
        res = fake.run(s, {'started_at': '2026-09-28T08:30'}, '2026-09-28T08:31')
    assert res['overflow'] == 3 and len(fake.sent) == rn.NOTIFY_MAX_PER_RUN + 1
    assert 'Ещё 3 новых отзывов' in fake.sent[-1][1]
    assert all(r['tg_notified_at'] for r in s.all())


def test_message_text():
    long_text = 'а' * (rn.TEXT_PREVIEW_LEN + 50)
    r = {'bar': 'kremenchugskaya', 'source': 'yandex', 'rating': 1, 'author': 'Иван <script>',
         'created_at': '2026-09-27T18:30', 'text': long_text, 'status': 'new'}
    t = rn.format_review(r)
    assert t.startswith('<b>Новый отзыв — низкая оценка · ')
    assert '&lt;script&gt;' in t and '<script>' not in t
    assert '27 сентября 2026, 18:30' in t and 'оценка 1 из 5' in t
    assert ('а' * (rn.TEXT_PREVIEW_LEN - 1) + '…') in t and ('а' * rn.TEXT_PREVIEW_LEN) not in t
    assert 'Ответа в Яндексе пока нет.' in t and t.endswith('/reviews?status=new&month=all')
    a = rn.format_review({'bar': 'bolshoy', 'source': 'yandex', 'rating': 5, 'author': '', 'text': '',
                          'created_at': '2026-09-27T18:30', 'status': 'answered',
                          'reply': {'text': 'Спасибо & до встречи'}})
    assert a.startswith('<b>Новый отзыв · ') and 'без имени' in a and 'Текста нет' in a
    assert 'Ответ в Яндексе уже есть: «Спасибо &amp; до встречи»' in a
    assert not any(ord(ch) > 0xFFFF for ch in t + a)     # без эмодзи


# ----------------------------------------------------------------- кнопка «Последние отзывы»

def _rv(i, created, status='answered', **over):
    r = {'id': f'r_{i:03d}', 'bar': 'bolshoy', 'source': 'yandex', 'rating': 5, 'author': f'Гость {i}',
         'text': f'Отзыв {i}', 'created_at': created, 'status': status}
    r.update(over)
    return r


def test_latest_order_count_and_waiting():
    reviews = [_rv(i, f'2026-09-{10 + i:02d}T12:00') for i in range(8)]
    reviews.append(_rv(99, '2025-01-01T10:00', status='new'))
    reviews.append(_rv(98, '2026-09-17T12:00', status='new', gone_at='2026-09-28T08:30', rating=None, text=''))
    t = rn.format_latest(reviews)
    assert t.startswith('<b>Последние 5 отзывов</b> · ждут ответа: 2')
    order = [x for x in ('Гость 98', 'Гость 7', 'Гость 6', 'Гость 5', 'Гость 4', 'Гость 3') if x in t]
    assert order == ['Гость 98', 'Гость 7', 'Гость 6', 'Гость 5', 'Гость 4'], order   # 17.09 и 7 делят дату — по id
    assert 'Гость 99' not in t
    assert 'без оценки' in t and 'Текста нет' in t and 'Ответа нет · нет в Яндексе' in t
    assert t.endswith('https://beerkultura.ru/reviews?month=all')
    assert rn.format_latest([]) == 'Отзывов пока нет.'


def test_latest_escaping_and_telegram_limit():
    long = [_rv(i, f'2026-09-2{i}T12:00', text='<i>' + 'я' * 5000, author='A&B') for i in range(5)]
    t = rn.format_latest(long)
    assert '<i>' not in t and '&lt;i&gt;' in t and 'A&amp;B' in t
    assert len(t) < 4096


def test_bot_button_and_command_send_latest():
    from core import open_check_telegram as tg
    import core.review_notify as rnmod
    sent, answered, saved = [], [], (tg.send_message, tg.answer_callback, rnmod.latest_reviews_text, tg.api_call)
    tg.send_message = lambda chat_id, text, reply_markup=None, html=False: sent.append((chat_id, text, html)) or True
    tg.answer_callback = lambda cq_id, text=None: answered.append(cq_id)
    rnmod.latest_reviews_text = lambda: 'СПИСОК'
    calls = []
    tg.api_call = lambda method, payload=None, **kw: calls.append((method, payload)) or {}
    try:
        kb = tg._menu_keyboard(False)['inline_keyboard']
        assert ['oc_reviews'] in [[b['callback_data'] for b in row] for row in kb]
        tg.handle_update({'callback_query': {'id': 'q1', 'data': 'oc_reviews',
                                             'message': {'chat': {'id': 42}, 'message_id': 7}}})
        tg.handle_update({'message': {'text': '/reviews', 'chat': {'id': 43}}})
        tg.handle_update({'message': {'text': '/отзывы', 'chat': {'id': 44}}})
        assert sent == [(42, 'СПИСОК', True), (43, 'СПИСОК', True), (44, 'СПИСОК', True)] and answered == ['q1']
        tg.set_my_commands()
        assert 'reviews' in [c['command'] for c in calls[0][1]['commands']]
    finally:
        tg.send_message, tg.answer_callback, rnmod.latest_reviews_text, tg.api_call = saved


# ----------------------------------------------------------------- из сверки

class _Client:
    def branches(self):
        return [{'permanent_id': pid, 'name': 'Культура'} for pid in ys.BAR_BY_PERMANENT_ID]

    def iter_review_pages(self, pid, max_pages=200):
        ts = int(datetime(2026, 9, 27, 18, 30, tzinfo=msk_time.MOSCOW_TZ).timestamp())
        items = [{'id': f'r{pid}', 'rating': 5, 'full_text': 'Хорошо', 'time_created': ts,
                  'author': {'user': 'Гость'}}]
        yield {'page': 1, 'total': 1, 'offset': 0, 'items': items}

    def close(self):
        pass


def _sync(notifier, store):
    now = datetime(2026, 9, 28, 8, 30, tzinfo=msk_time.MOSCOW_TZ)
    _n[0] += 1
    with _Env(YANDEX_BUSINESS_SESSION_ID='test-sid-one', YANDEX_BUSINESS_SESSION_ID2='test-sid-two', **TOKEN):
        return ys.sync_all(store=store, client_factory=lambda a, b: _Client(), clock=lambda: now,
                           path=os.path.join(TMP, f'state_{_n[0]}.json'), notifier=notifier)


def test_sync_without_notifier_sends_nothing():
    state = _sync(None, _store(datetime(2026, 9, 28, 8, 30)))
    assert state['status'] == 'ok' and 'notify' not in state


def test_sync_with_notifier_and_failing_notifier():
    fake = Fake()
    store = _store(datetime(2026, 9, 28, 8, 30))
    state = _sync(fake.run, store)
    assert state['status'] == 'ok' and state['notify']['sent_messages'] == 4 and len(fake.sent) == 4

    def boom(*a):
        raise RuntimeError('telegram down')
    state = _sync(boom, _store(datetime(2026, 9, 28, 8, 30)))
    assert state['status'] == 'ok' and 'telegram down' in state['notify']['error']


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
