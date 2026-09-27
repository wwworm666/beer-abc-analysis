"""
Тесты загрузки отзывов из Яндекс Бизнеса: ReviewStore.upsert_imported
(core/guest_reviews.py), сверка sync_all (core/yandex_reviews_sync.py) и
расчёт времени планировщика (core/yandex_reviews_scheduler.py).

Self-runnable: `py -3 tests/test_yandex_reviews_sync.py` (совместимо с pytest).

Сети нет: клиент кабинета подменяется фейком, файлы — временные, часы
подменяются. Что проверяется:
- новый отзыв: с ответом в Яндексе -> «Отвечен» со временем из Яндекса;
  без ответа до границы истории -> «Без ответа по решению» с причиной; после
  границы -> «Без ответа»;
- повторная загрузка не плодит дублей; правка оценки и текста обновляется;
- ответ в Яндексе у ждущего -> «Отвечен»; у сохранённого здесь -> отметка
  «опубликован», момент ответа не меняется; правка ответа в Яндексе не
  «молодит» время; ответ пропал -> снова ждёт, прежний остаётся;
- пропавший из полного прохода -> gone_at без удаления; вернулся -> снят;
  неполный проход пропавших не отмечает; не разобравшийся — не «пропавший»;
- ручные отзывы загрузка не трогает;
- sync_all: без cookies — not_configured; бары по permanent_id, не-бары не
  читаются; граница истории ставится один раз; сессия не принята -> expired
  и cookies не попадают в состояние; капча; сбой одного бара не ломает
  остальные; организации нет -> partial; получено меньше счётчика —
  предупреждение без пометки пропавших; вторая сверка в это же время — пропуск;
- планировщик: время до сверки по МСК, стартовая сверка только без свежей.
"""
import atexit
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import msk_time  # noqa: E402
from core import yandex_reviews_scheduler as sched  # noqa: E402
from core import yandex_reviews_sync as ys  # noqa: E402
from core.guest_reviews import HISTORY_SKIP_REASON, ReviewStore  # noqa: E402
from core.yandex_business import YandexAuthError, YandexCaptchaError, YandexTemporaryError  # noqa: E402

TMP = tempfile.mkdtemp(prefix='yrs_test_')
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
SID, SID2 = 'SECRET-sid-aaa', 'SECRET-sid2-bbb'
NOW = datetime(2026, 9, 28, 8, 30)
CUTOFF = '2026-08-29'
BY = 'Яндекс Бизнес'
USER = {'login': 'owner'}
_n = [0]


def _store(now=NOW):
    _n[0] += 1
    return ReviewStore(os.path.join(TMP, f'reviews_{_n[0]}.json'), clock=lambda: now)


def _item(ext, created='2026-09-20T12:00', rating=5, text='Отлично', reply=None, **over):
    it = {'external_id': ext, 'created_at': created, 'rating': rating, 'text': text, 'author': 'Иван',
          'owner_reply': reply, 'photos': [], 'author_avatar': None, 'public_rating': True}
    it.update(over)
    return it


def _by_ext(store):
    return {r['external_id']: r for r in store.all() if r.get('external_id')}


def _up(store, items, complete=True, bar='bolshoy'):
    return store.upsert_imported('yandex', bar, items, history_cutoff=CUTOFF, complete=complete, by=BY)


# ----------------------------------------------------------------- upsert_imported

def test_new_reviews_statuses():
    s = _store()
    st = _up(s, [_item('a', reply={'text': 'Спасибо!', 'at': '2026-09-21T10:00'}),
                 _item('b', created='2025-05-01T12:00'),
                 _item('c', created='2026-08-29T00:10'),
                 _item('d', created='2026-08-28T23:59')])
    assert (st['added_answered'], st['added_history'], st['added_new']) == (1, 2, 1), st
    r = _by_ext(s)
    assert r['a']['status'] == 'answered' and r['a']['origin'] == 'import'
    assert r['a']['reply'] == {'text': 'Спасибо!', 'at': '2026-09-21T10:00', 'by': BY, 'delivered': True,
                               'source': 'yandex'}
    assert r['b']['status'] == 'skipped' and r['b']['skip_reason'] == HISTORY_SKIP_REASON
    assert r['c']['status'] == 'new'          # граница включительно: 29.08 — уже не история
    assert r['d']['status'] == 'skipped'
    assert r['a']['added_by'] == BY and r['a']['bar'] == 'bolshoy'
    # Время ответа считается от ответа в Яндексе: 20.09 12:00 -> 21.09 10:00 = 22 ч.
    listing = s.listing({'all': '1'})
    a = next(x for x in listing['reviews'] if x['external_id'] == 'a')
    assert a['response_hours'] == 22.0


def test_rerun_no_duplicates_and_updates():
    s = _store()
    _up(s, [_item('a'), _item('b')])
    st = _up(s, [_item('a'), _item('b')])
    assert len(s.all()) == 2
    assert all(st[k] == 0 for k in st if k != 'problems'), st
    st = _up(s, [_item('a', rating=3, text='Исправил'), _item('b')])
    assert st['updated'] == 1
    assert _by_ext(s)['a']['rating'] == 3 and _by_ext(s)['a']['text'] == 'Исправил'


def test_answer_appears_in_yandex_for_waiting():
    s = _store()
    _up(s, [_item('a'), _item('h', created='2024-01-01T10:00')])
    st = _up(s, [_item('a', reply={'text': 'Ответ', 'at': '2026-09-27T09:00'}),
                 _item('h', created='2024-01-01T10:00', reply={'text': 'Поздно', 'at': '2026-09-27T09:00'})])
    assert st['answered_in_source'] == 2
    r = _by_ext(s)
    assert r['a']['status'] == 'answered' and r['a']['reply']['at'] == '2026-09-27T09:00'
    assert r['h']['status'] == 'answered' and r['h']['skip_reason'] == HISTORY_SKIP_REASON   # причина — для истории


def test_local_reply_marked_published_keeps_moment():
    s = _store()
    _up(s, [_item('a')])
    rid = _by_ext(s)['a']['id']
    s.reply(rid, 'Наш ответ', USER)
    st = _up(s, [_item('a', reply={'text': 'Наш ответ', 'at': '2026-09-28T11:00'})])
    assert st['published'] == 1
    rep = _by_ext(s)['a']['reply']
    assert rep['at'] == '2026-09-28T08:30' and rep['by'] == 'owner'      # момент — наше сохранение
    assert rep['delivered'] is True and rep['published_at'] == '2026-09-28T11:00'
    assert 'source' not in rep
    # Повтор той же сверки ничего не меняет.
    assert _up(s, [_item('a', reply={'text': 'Наш ответ', 'at': '2026-09-28T11:00'})])['published'] == 0


def test_yandex_reply_edit_and_removal():
    s = _store()
    _up(s, [_item('a', reply={'text': 'Раз', 'at': '2026-09-21T10:00'})])
    _up(s, [_item('a', reply={'text': 'Два', 'at': '2026-09-25T10:00'})])
    rep = _by_ext(s)['a']['reply']
    assert rep['text'] == 'Два' and rep['at'] == '2026-09-21T10:00' and rep['edited_at'] == '2026-09-25T10:00'
    st = _up(s, [_item('a')])
    assert st['reply_removed'] == 1
    r = _by_ext(s)['a']
    assert r['status'] == 'new' and r['reply']['text'] == 'Два' and r['reply']['removed_in_source_at']


def test_gone_and_back_never_deleted():
    s = _store()
    _up(s, [_item('a'), _item('b')])
    st = _up(s, [_item('a')])
    assert st['gone'] == 1 and len(s.all()) == 2
    assert _by_ext(s)['b']['gone_at'] == '2026-09-28T08:30'
    assert _up(s, [_item('a')])['gone'] == 0      # уже отмечен
    st = _up(s, [_item('a'), _item('b')])
    assert st['back'] == 1 and _by_ext(s)['b']['gone_at'] is None


def test_incomplete_pass_and_invalid_not_gone():
    s = _store()
    _up(s, [_item('a'), _item('b')])
    assert _up(s, [_item('a')], complete=False)['gone'] == 0
    st = _up(s, [_item('a'), _item('b', rating=0), {'external_id': '', 'created_at': 'x'}, 'мусор'])
    assert st['invalid'] == 3 and st['gone'] == 0 and len(st['problems']) == 3
    assert _by_ext(s)['b']['gone_at'] is None


def test_other_bar_and_manual_untouched():
    s = _store()
    manual = s.add({'source': 'yandex', 'bar': 'bolshoy', 'rating': 4, 'text': 'Руками',
                    'created_at': '2026-09-20T10:00'}, USER)
    _up(s, [_item('k')], bar='kremenchugskaya')
    st = _up(s, [_item('a')], bar='bolshoy')
    assert st['gone'] == 0     # отзыв другого бара и ручной — не «пропавшие» бара bolshoy
    assert s.get(manual['id'])['origin'] == 'manual' and not s.get(manual['id']).get('gone_at')
    assert _by_ext(s)['k']['bar'] == 'kremenchugskaya'


def test_old_reviews_from_2018_load():
    # Регресс 2026-09-28: граница года 2020 отбрасывала 19 отзывов 2018–2019 гг.
    s = _store()
    st = _up(s, [_item('y2018', created='2018-07-12T15:00', reply={'text': 'Спасибо', 'at': '2018-07-13T15:40'}),
                 _item('y2019', created='2019-11-02T12:00')])
    assert st['invalid'] == 0 and st['added_answered'] == 1 and st['added_history'] == 1
    assert ReviewStore(s.data_file, clock=lambda: NOW).listing({'month': '2018-07'})['metrics']['total']['count'] == 1


def test_imported_record_survives_reload():
    s = _store()
    _up(s, [_item('a', photos=[{'link': '/get-altay/1/x/orig', 'width': 1, 'height': 2}])])
    fresh = ReviewStore(s.data_file, clock=lambda: NOW)
    r = fresh.all()[0]
    assert r['photos'][0]['link'] == '/get-altay/1/x/orig' and r['origin'] == 'import'


# ----------------------------------------------------------------- sync_all

class FakeClient:
    def __init__(self, orgs, pages, fail=None):
        self.orgs, self.pages, self.fail = orgs, pages, fail or {}
        self.read = []
        self.closed = False

    def branches(self):
        if 'branches' in self.fail:
            raise self.fail['branches']
        return [{'permanent_id': pid, 'name': name} for pid, name in self.orgs.items()]

    def iter_review_pages(self, pid, max_pages=200):
        self.read.append(pid)
        if pid in self.fail:
            raise self.fail[pid]
        items = self.pages.get(pid, [])
        total = len(items) + self.pages.get(('extra', pid), 0)
        yield {'page': 1, 'total': total, 'offset': 0, 'items': items}

    def close(self):
        self.closed = True


def _raw(rid, ts=None, reply=None):
    ts = ts or int(datetime(2026, 9, 20, 12, 0, tzinfo=msk_time.MOSCOW_TZ).timestamp())
    r = {'id': rid, 'rating': 5, 'full_text': 'Хорошо', 'time_created': ts, 'author': {'user': 'Гость'}}
    if reply:
        r['owner_comment'] = reply
    return r


ALL_ORGS = {pid: 'Культура' for pid in ys.BAR_BY_PERMANENT_ID}
ALL_ORGS.update(ys.NOT_BARS)


class _Env:
    def __init__(self, sid=SID, sid2=SID2):
        self.vals = {ys.ENV_SESSION_ID: sid, ys.ENV_SESSION_ID2: sid2}

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


def _sync(client, store=None, now=NOW, path=None):
    path = path or os.path.join(TMP, f'state_{_n[0]}_{id(client)}.json')
    clock = lambda: now.replace(tzinfo=msk_time.MOSCOW_TZ)   # noqa: E731
    return ys.sync_all(store=store or _store(now), client_factory=lambda a, b: client, clock=clock,
                       path=path), path


def test_sync_not_configured():
    with _Env(None, None):
        state, path = _sync(FakeClient(ALL_ORGS, {}))
        assert state['status'] == 'not_configured'
        assert ys.public_state(path)['status'] == 'not_configured'


def test_sync_ok_maps_bars_and_skips_not_bars():
    pages = {pid: [_raw(f'r{pid}')] for pid in ys.BAR_BY_PERMANENT_ID}
    client = FakeClient(ALL_ORGS, pages)
    store = _store()
    with _Env():
        state, path = _sync(client, store)
        assert state['status'] == 'ok', state
        assert sorted(client.read) == sorted(ys.BAR_BY_PERMANENT_ID)    # Draftmasters и First не читались
        assert client.closed
        bars = {r['bar'] for r in store.all()}
        assert bars == set(ys.BAR_BY_PERMANENT_ID.values())
        assert state['history_cutoff'] == '2026-08-29' and state['last_success_at']
        text = json.dumps(state, ensure_ascii=False)
        assert SID not in text and SID2 not in text
        pub = ys.public_state(path)
        assert pub['status'] == 'ok' and pub['bars']['bolshoy'] == {
            'total': 1, 'received': 1, 'error': None, 'synced_at': '2026-09-28T08:30'}
        # Вторая сверка через 10 дней: граница истории прежняя, дублей нет.
        later = NOW + timedelta(days=10)
        state2 = ys.sync_all(store=store, client_factory=lambda a, b: client,
                             clock=lambda: later.replace(tzinfo=msk_time.MOSCOW_TZ), path=path)
        assert state2['history_cutoff'] == '2026-08-29' and len(store.all()) == 4


def test_sync_auth_expired_and_captcha():
    with _Env():
        state, _ = _sync(FakeClient(ALL_ORGS, {}, fail={'branches': YandexAuthError('нужны новые cookies')}))
        assert state['status'] == 'expired' and 'cookies' in state['error']
        pid = next(iter(ys.BAR_BY_PERMANENT_ID))
        state, _ = _sync(FakeClient(ALL_ORGS, {}, fail={pid: YandexCaptchaError('капча')}))
        assert state['status'] == 'captcha'
        # Сообщение с cookie внутри вырезается.
        state, _ = _sync(FakeClient(ALL_ORGS, {}, fail={'branches': RuntimeError('boom ' + SID)}))
        assert state['status'] == 'error' and SID not in state['error']


def test_sync_one_bar_fails_others_imported():
    pids = list(ys.BAR_BY_PERMANENT_ID)
    pages = {pid: [_raw(f'r{pid}')] for pid in pids}
    client = FakeClient(ALL_ORGS, pages, fail={pids[0]: YandexTemporaryError('HTTP 503 после 3 попыток')})
    store = _store()
    with _Env():
        state, _ = _sync(client, store)
    assert state['status'] == 'partial'
    assert len(store.all()) == 3
    bad = ys.BAR_BY_PERMANENT_ID[pids[0]]
    assert '503' in state['bars'][bad]['error']


def test_sync_missing_org_and_incomplete_count():
    pids = list(ys.BAR_BY_PERMANENT_ID)
    orgs = {pid: 'Культура' for pid in pids[1:]}
    pages = {pid: [_raw(f'r{pid}')] for pid in pids}
    pages[('extra', pids[1])] = 5          # Яндекс насчитывает больше, чем отдал
    store = _store()
    _up_bar = ys.BAR_BY_PERMANENT_ID[pids[1]]
    store.upsert_imported('yandex', _up_bar, [_item('old')], history_cutoff=CUTOFF, complete=True, by=BY)
    with _Env():
        state, _ = _sync(FakeClient(orgs, pages), store)
    assert state['status'] == 'partial'
    assert 'нет в аккаунте' in state['bars'][ys.BAR_BY_PERMANENT_ID[pids[0]]]['error']
    b = state['bars'][_up_bar]
    assert b['received'] == 1 and b['total'] == 6 and 'пропавшие не отмечались' in b['error']
    assert _by_ext(store)['old']['gone_at'] is None


def test_sync_single_flight():
    import portalocker
    path = os.path.join(TMP, 'state_lock.json')
    with portalocker.Lock(path + '.lock', mode='a', timeout=0):
        with _Env():
            state, _ = _sync(FakeClient(ALL_ORGS, {}), path=path)
    assert state == {'skipped': 'already_running'}


# ----------------------------------------------------------------- планировщик

def test_scheduler_timing():
    assert sched.seconds_until(8, 30, datetime(2026, 9, 28, 8, 0)) == 1800
    assert sched.seconds_until(8, 30, datetime(2026, 9, 28, 8, 30)) == 24 * 3600
    now = datetime(2026, 9, 28, 14, 0)
    assert sched.needs_startup_sync({}, now)
    assert not sched.needs_startup_sync({'last_success_at': '2026-09-28T08:30'}, now)
    assert sched.needs_startup_sync({'last_success_at': '2026-09-27T08:30'}, now)
    assert sched.needs_startup_sync({'last_success_at': 'мусор'}, now)


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
