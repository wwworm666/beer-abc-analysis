"""
Тесты загрузки отзывов с Яндекс Карт: ReviewStore.upsert_imported
(core/guest_reviews.py), проверка sync_all (core/yandex_reviews_sync.py) и
расписание планировщика (core/yandex_reviews_scheduler.py).

Self-runnable: `py -3 tests/test_yandex_reviews_sync.py` (совместимо с pytest).

Сети нет: страницы Карт подменяются фейком, файлы — временные, часы
подменяются. Что проверяется:
- новый отзыв: с ответом в Яндексе -> «Отвечен» со временем из Яндекса;
  без ответа до границы истории -> «Без ответа по решению» с причиной; после
  границы -> «Без ответа»;
- повторная загрузка не плодит дублей; правка оценки и текста обновляется;
  обновляются только поля, которые прислал источник (фото, аватар и
  public_rating кабинета остаются), дата отзыва не меняется;
- ответ в Яндексе у ждущего -> «Отвечен»; у сохранённого здесь -> отметка
  «опубликован», момент ответа не меняется; правка ответа в Яндексе не
  «молодит» время; ответ пропал -> снова ждёт, прежний остаётся;
- пропавший из полного прохода -> gone_at без удаления; вернулся -> снят;
  неполный проход пропавших не отмечает; не разобравшийся — не «пропавший»;
- ручные отзывы загрузка не трогает;
- sync_all: полный проход и сводка для экрана; первый запуск после кабинета
  переносит границу истории и notify_since, id совпадают — дублей нет;
  быстрая проверка читает первую страницу и догружает остальные, только когда
  на Картах больше отзывов; защита от дублей при несовпадении id; сломанное
  листание — ошибка бара, отставание отмечено; капча останавливает проверку;
  сбой бара сохраняет прежние числа; вторая проверка в это же время — пропуск;
- планировщик: что делать на такте (полный проход раз в сутки, быстрая
  проверка раз в 3 часа, повтор неудачного полного), такт зовёт сторожа.
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

import pytest  # noqa: E402

from core import msk_time  # noqa: E402
from core import yandex_maps_reviews as mr  # noqa: E402
from core import yandex_reviews_scheduler as sched  # noqa: E402
from core import yandex_reviews_sync as ys  # noqa: E402
from core import yandex_reviews_watchdog as wd  # noqa: E402
from core.guest_reviews import HISTORY_SKIP_REASON, ReviewStore  # noqa: E402

TMP = tempfile.mkdtemp(prefix='yrs_test_')
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
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


def test_only_supplied_fields_are_updated():
    """Страница Карт не даёт фото, аватар и public_rating: у отзыва из кабинета они остаются."""
    s = _store()
    _up(s, [_item('a', photos=[{'link': '/p/1', 'width': 1, 'height': 1}], author_avatar='/a/1',
                  public_rating=False)])
    maps_item = {'external_id': 'a', 'created_at': '2026-10-01T09:00', 'rating': 5, 'text': 'Отлично',
                 'author': 'Иван', 'owner_reply': None}
    st = _up(s, [maps_item])
    r = _by_ext(s)['a']
    assert st['updated'] == 0
    assert r['photos'] == [{'link': '/p/1', 'width': 1, 'height': 1}] and r['author_avatar'] == '/a/1'
    assert r['public_rating'] is False and r['created_at'] == '2026-09-20T12:00'   # дата не «молодеет»
    st = _up(s, [dict(maps_item, text='Отлично, но шумно')])
    assert st['updated'] == 1 and _by_ext(s)['a']['text'] == 'Отлично, но шумно'
    assert _by_ext(s)['a']['photos'][0]['link'] == '/p/1'
    st = _up(s, [dict(maps_item, external_id='b')])     # новый без фото — значения по умолчанию
    b = _by_ext(s)['b']
    assert st['added_new'] == 1 and b['photos'] == [] and b['author_avatar'] is None and b['public_rating'] is None


# ----------------------------------------------------------------- sync_all (Яндекс Карты)

PIDS = list(ys.BAR_BY_PERMANENT_ID)
KREM = 31434555884                      # kremenchugskaya


def _rv(i, when='2026-10-01T10:00:00Z', reply=None):
    r = {'reviewId': str(i), 'author': {'name': 'Гость'}, 'text': f'Отзыв {i}', 'rating': 5,
         'updatedTime': when}
    if reply:
        r['businessComment'] = {'text': reply, 'updatedTime': '2026-10-02T09:00:00Z'}
    return r


class Maps:
    """Публичные страницы Карт в памяти: {org_id: [сырые отзывы]}, по 50 на страницу.

    fail — {org_id: исключение} на любую страницу; ignore_page — организации, у
    которых страница N отдаёт первую (листание сломано); count_extra — сколько
    отзывов Карты насчитывают сверх списка.
    """

    def __init__(self, reviews, fail=None, ignore_page=(), count_extra=None):
        self.reviews, self.fail = reviews, fail or {}
        self.ignore_page, self.count_extra = set(ignore_page), count_extra or {}
        self.asked = []

    def fetch(self, org, page):
        self.asked.append((org, page))
        if org in self.fail:
            raise self.fail[org]
        items = self.reviews.get(org, [])
        shown = 1 if org in self.ignore_page else page
        return {'reviews': items[(shown - 1) * 50:shown * 50], 'count': len(items) + self.count_extra.get(org, 0),
                'count_source': 'params', 'page': shown, 'total_pages': max(1, -(-len(items) // 50))}

    def pages(self, org):
        return [p for o, p in self.asked if o == org]


def _maps(n=3, extra=None):
    """У каждого бара n отзывов с id '<org>-<i>'."""
    data = {pid: [_rv(f'{pid}-{i}') for i in range(n)] for pid in PIDS}
    data.update(extra or {})
    return data


def _sync(maps, store=None, now=NOW, path=None, kind='full', notifier=None):
    path = path or os.path.join(TMP, f'state_{_n[0]}_{id(maps)}.json')
    clock = lambda: now.replace(tzinfo=msk_time.MOSCOW_TZ)   # noqa: E731
    return ys.sync_all(kind, store=store or _store(now), fetch=maps.fetch, sleep=lambda s: None,
                       clock=clock, path=path, notifier=notifier), path


def test_sync_full_ok_and_public_state():
    maps = Maps(_maps())
    store = _store()
    state, path = _sync(maps, store)
    assert state['status'] == 'ok', state
    assert state['source'] == 'maps' and state['source_since'] == '2026-09-28T08:30'
    assert state['history_cutoff'] == '2026-08-29' and state['last_success_at'] == '2026-09-28T08:30'
    assert state['last_full_at'] == state['last_full_attempt_at'] == '2026-09-28T08:30'
    assert {r['bar'] for r in store.all()} == set(ys.BAR_BY_PERMANENT_ID.values())
    assert all(r['added_by'] == 'Яндекс Карты' for r in store.all())
    b = state['bars']['kremenchugskaya']
    assert (b['org_id'], b['count'], b['received'], b['ours'], b['pages']) == (KREM, 3, 3, 3, 1)
    assert b['full_at'] == b['synced_at'] == '2026-09-28T08:30' and b['behind_since'] is None
    pub = ys.public_state(path, now=NOW)
    assert pub['status'] == 'ok' and pub['kind'] == 'full'
    assert pub['bars']['kremenchugskaya'] == {'count': 3, 'received': 3, 'ours': 3, 'error': None,
                                              'synced_at': '2026-09-28T08:30', 'full_at': '2026-09-28T08:30',
                                              'behind_since': None}
    assert pub['schedule'] == {'quick_every_hours': 3, 'full_at': '08:30'}
    assert pub['alerts'] == {'stale': [], 'behind': []}
    # Повтор через 10 дней: граница истории прежняя, дублей нет.
    state2, _ = _sync(maps, store, now=NOW + timedelta(days=10), path=path)
    assert state2['history_cutoff'] == '2026-08-29' and len(store.all()) == 12


def test_first_run_after_cabinet_keeps_history_and_matches_ids():
    """Файл состояния от кабинета: переносятся граница истории, notify_since, synced_at; id те же."""
    path = os.path.join(TMP, 'state_cabinet.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'status': 'expired', 'error': 'Сессия Яндекса не принята', 'history_cutoff': '2026-08-29',
                   'notify_since': '2026-09-28T00:38', 'last_success_at': '2026-09-28T08:30',
                   'bars': {'kremenchugskaya': {'permanent_id': KREM, 'total': 12, 'received': 12,
                                                'synced_at': '2026-09-28T08:30'}}}, f)
    pub = ys.public_state(path, now=datetime(2026, 10, 9, 15, 0))
    assert pub['status'] == 'never' and pub['bars'] == {} and pub['error'] is None
    store = _store(datetime(2026, 10, 9, 15, 0))
    cabinet = [_item(f'k{i}', photos=[{'link': f'/p/{i}'}], public_rating=True) for i in range(12)]
    store.upsert_imported('yandex', 'kremenchugskaya', cabinet, history_cutoff=CUTOFF, complete=True, by=BY)
    on_maps = [_rv('k-new', when='2026-10-05T10:00:00Z')] + [_rv(f'k{i}') for i in range(11)]   # k11 удалён
    maps = Maps(_maps(extra={KREM: on_maps}))
    state, _ = _sync(maps, store, now=datetime(2026, 10, 9, 15, 0), path=path)
    assert state['status'] == 'ok', state
    assert state['history_cutoff'] == '2026-08-29' and state['notify_since'] == '2026-09-28T00:38'
    assert 'total' not in state['bars']['kremenchugskaya'] and 'permanent_id' not in state['bars']['kremenchugskaya']
    by_ext = _by_ext(store)
    assert len([r for r in store.all() if r['bar'] == 'kremenchugskaya']) == 13          # 12 + 1 новый, без дублей
    assert by_ext['k-new']['status'] == 'new' and by_ext['k-new']['added_by'] == 'Яндекс Карты'
    assert by_ext['k11']['gone_at'] == '2026-10-09T15:00'                                    # полный проход
    assert by_ext['k0']['photos'] == [{'link': '/p/0'}] and by_ext['k0']['public_rating'] is True
    assert by_ext['k0']['created_at'] == '2026-09-20T12:00'


def test_quick_reads_first_page_and_loads_rest_only_when_behind():
    reviews = {pid: [_rv(f'{pid}-{i}') for i in range(120)] for pid in PIDS}
    maps = Maps(reviews)
    store = _store()
    _, path = _sync(maps, store)
    assert maps.pages(KREM) == [1, 2, 3]
    maps.asked.clear()
    later = NOW + timedelta(hours=3)
    state, _ = _sync(maps, store, now=later, path=path, kind='quick')
    assert state['status'] == 'ok' and all(maps.pages(pid) == [1] for pid in PIDS)    # 4 запроса
    assert state['last_full_at'] == '2026-09-28T08:30' and state['kind'] == 'quick'
    b = state['bars']['kremenchugskaya']
    assert (b['count'], b['received'], b['ours'], b['pages']) == (120, 50, 120, 1)
    # Новый отзыв не на первой странице (порядок Карт — по умолчанию): на Картах 121 > 120 у нас.
    reviews[KREM].insert(70, _rv('late', when='2026-09-28T10:00:00Z'))
    maps.asked.clear()
    state, _ = _sync(maps, store, now=later + timedelta(hours=3), path=path, kind='quick')
    assert maps.pages(KREM) == [1, 2, 3] and maps.pages(PIDS[1]) == [1]
    b = state['bars']['kremenchugskaya']
    assert (b['count'], b['received'], b['ours']) == (121, 121, 121) and b['behind_since'] is None
    assert _by_ext(store)['late']['status'] == 'new'
    # Новый на первой странице — догружать не нужно.
    reviews[KREM].insert(0, _rv('top', when='2026-09-28T16:00:00Z'))
    maps.asked.clear()
    state, _ = _sync(maps, store, now=later + timedelta(hours=6), path=path, kind='quick')
    assert maps.pages(KREM) == [1] and state['bars']['kremenchugskaya']['ours'] == 122


def test_id_mismatch_guard_does_not_duplicate():
    store = _store()
    store.upsert_imported('yandex', 'kremenchugskaya', [_item(f'old{i}') for i in range(20)],
                          history_cutoff=CUTOFF, complete=True, by=BY)
    maps = Maps(_maps(extra={KREM: [_rv(f'other{i}') for i in range(20)]}))
    state, _ = _sync(maps, store)
    assert state['status'] == 'partial'
    assert 'id не совпадают' in state['bars']['kremenchugskaya']['error']
    assert 'Кременчугская' in state['error']
    assert len([r for r in store.all() if r['bar'] == 'kremenchugskaya']) == 20
    assert not any(r.get('gone_at') for r in store.all())
    # Ниже порога проверки (меньше 10 отзывов у нас) — грузится как есть.
    assert ys.id_mismatch({'a', 'b'}, {'c'} | {f'x{i}' for i in range(20)}) is None
    assert ys.id_mismatch({f'x{i}' for i in range(10)}, {f'x{i}' for i in range(5)} | {f'y{i}' for i in range(5)}) is None


def test_broken_pagination_keeps_first_page_and_marks_behind():
    reviews = {pid: [_rv(f'{pid}-{i}') for i in range(3)] for pid in PIDS}
    reviews[KREM] = [_rv(f'k{i}') for i in range(120)]
    store = _store()
    store.upsert_imported('yandex', 'kremenchugskaya', [_item('kabinet-only')], history_cutoff=CUTOFF,
                          complete=True, by=BY)
    maps = Maps(reviews, ignore_page={KREM})
    state, path = _sync(maps, store)
    b = state['bars']['kremenchugskaya']
    assert state['status'] == 'partial' and 'не листают' in b['error']
    assert (b['count'], b['received'], b['ours']) == (120, 50, 51)
    assert b['behind_since'] == '2026-09-28T08:30' and b['full_at'] is None
    assert _by_ext(store)['kabinet-only']['gone_at'] is None          # неполный проход — пропавших нет
    # Следующая проверка: отставание длится, отсчёт прежний.
    state, _ = _sync(maps, store, now=NOW + timedelta(hours=3), path=path, kind='quick')
    assert state['bars']['kremenchugskaya']['behind_since'] == '2026-09-28T08:30'


def test_captcha_stops_the_run_and_errors():
    maps = Maps(_maps(), fail={PIDS[0]: mr.MapsCaptchaError('капча')})
    state, _ = _sync(maps)
    assert state['status'] == 'captcha' and state['error'] == 'капча'
    assert [o for o, _ in maps.asked] == [PIDS[0]]                                   # остальные не дёргали
    maps = Maps(_maps(), fail={PIDS[1]: mr.MapsReviewsError('Карты ответили кодом 503')})
    store = _store()
    state, _ = _sync(maps, store)
    assert state['status'] == 'partial' and '503' in state['bars'][ys.BAR_BY_PERMANENT_ID[PIDS[1]]]['error']
    assert len(store.all()) == 9 and 'last_success_at' not in state
    maps = Maps(_maps(), fail={pid: mr.MapsReviewsError('Карты не ответили (Timeout)') for pid in PIDS})
    state, _ = _sync(maps)
    assert state['status'] == 'error' and state['error'].startswith('Не прочитаны: ')
    with pytest.raises(ValueError):
        ys.sync_all('weekly')


def test_failed_bar_keeps_previous_numbers():
    maps = Maps(_maps())
    store = _store()
    _, path = _sync(maps, store)
    maps.fail = {KREM: mr.MapsReviewsError('Карты ответили кодом 500')}
    state, _ = _sync(maps, store, now=NOW + timedelta(hours=3), path=path, kind='quick')
    b = state['bars']['kremenchugskaya']
    assert b['error'] == 'Карты ответили кодом 500' and b['synced_at'] == '2026-09-28T08:30'
    assert (b['count'], b['ours'], b['received']) == (3, 3, None)


def test_sync_single_flight_and_disabled_state():
    import portalocker
    path = os.path.join(TMP, 'state_lock.json')
    with portalocker.Lock(path + '.lock', mode='a', timeout=0):
        state, _ = _sync(Maps(_maps()), path=path)
    assert state == {'skipped': 'already_running'}
    _, path = _sync(Maps(_maps()))
    os.environ['YANDEX_REVIEWS_SYNC_ENABLED'] = '0'
    try:
        assert ys.public_state(path, now=NOW)['status'] == 'disabled'
    finally:
        os.environ.pop('YANDEX_REVIEWS_SYNC_ENABLED')


# ----------------------------------------------------------------- планировщик

def test_scheduler_due_kind():
    slot_today = datetime(2026, 10, 9, 8, 30)
    assert sched.last_full_slot(datetime(2026, 10, 9, 8, 29)) == slot_today - timedelta(days=1)
    assert sched.last_full_slot(datetime(2026, 10, 9, 8, 30)) == slot_today
    now = datetime(2026, 10, 9, 15, 0)
    maps = {'source': 'maps'}
    assert sched.due_kind({}, now) == 'full'                                          # ещё ни одной
    assert sched.due_kind({'last_full_attempt_at': '2026-10-09T09:00', 'last_attempt_at': '2026-10-09T14:00'},
                          now) == 'full'                                              # файл от кабинета
    done = dict(maps, last_full_attempt_at='2026-10-09T08:30', last_full_at='2026-10-09T08:31')
    assert sched.due_kind(dict(done, last_attempt_at='2026-10-09T12:01'), now) is None   # меньше 3 ч
    assert sched.due_kind(dict(done, last_attempt_at='2026-10-09T12:00'), now) == 'quick'
    failed = dict(maps, last_full_attempt_at='2026-10-09T08:30', last_full_at='2026-10-08T08:31')
    assert sched.due_kind(dict(failed, last_attempt_at='2026-10-09T11:30'), now) == 'full'   # повтор полного
    assert sched.due_kind(dict(failed, last_attempt_at='2026-10-09T13:00'), now) is None
    assert sched.due_kind(dict(done, last_attempt_at='2026-10-09T08:31'), datetime(2026, 10, 10, 8, 30)) == 'full'


def test_scheduler_tick_runs_due_check_and_watchdog():
    calls = []
    saved = (ys.sync_all, ys.load_state, wd.check)
    ys.sync_all = lambda kind, notifier=None: calls.append((kind, notifier is not None)) or {'status': 'ok'}
    ys.load_state = lambda path=None: {}
    wd.check = lambda: {'skipped': 'test'}
    os.environ['YANDEX_REVIEWS_NOTIFY'] = '0'
    try:
        result = sched.tick(datetime(2026, 10, 9, 15, 0))
    finally:
        ys.sync_all, ys.load_state, wd.check = saved
        os.environ.pop('YANDEX_REVIEWS_NOTIFY')
    assert calls == [('full', False)] and result == {'kind': 'full', 'status': 'ok', 'watchdog': {'skipped': 'test'}}


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
