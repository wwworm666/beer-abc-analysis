"""
Тесты отзывов гостей (core/guest_reviews.py) и их API (routes/reviews.py),
включая полосу внимания хаба «Гости» (/api/guest-hub/attention).

Self-runnable: `py -3 tests/test_guest_reviews.py` (совместимо с pytest).

Файл отзывов — временный; часы хранилища подменяются (детерминированно);
контент-план подменяется фейком (реальный модуль проверяется последним тестом,
который пропускается, если core/content_plan.py нет или он не импортируется).

Что проверяется:
- half-up округление (4,25 -> 4,3; 4,35 -> 4,4; 12,5 -> 13) и медиана (чёт/нечет);
- проверка полей: оценка у Яндекса обязательна, нужен текст или оценка, бар
  обязателен и конкретный, дата не позже «сейчас + 5 минут», длины, форматы;
- порядок списка, age_hours / response_hours (с отсечкой в 0);
- каждая метрика и что метрики зависят только от периода и источника;
- фильтры оценки/статуса/источника/бара/периода и all=1;
- переходы reply / skip / reopen, удаление только ручных, слой календаря;
- «Сделать материалом» с фейковым контент-планом (повтор -> 409, сбой -> 503);
- material_exists (true/false/null) и устаревшая ссылка на удалённый материал:
  новый материал (200) с заменой ссылки, 409 только при живом материале,
  один проход проверки на запрос, недоступный контент-план -> null и 409;
- черновик ответа хранится как набран (без обрезки), итоговый ответ обрезается;
- огромная запись оценки («1e400000») отклоняется мгновенно;
- формулы времени ответа описывают то, что делает код (правка / возврат в работу);
- полоса внимания с фейковым и падающим контент-планом;
- битый файл -> 503, файл не перезаписан.
"""

import atexit
import os
import shutil
import sys
import tempfile
import time
import types
from contextlib import contextmanager
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['SESSION_COOKIE_SECURE'] = '0'

from flask import Flask  # noqa: E402
import routes.reviews as rrev  # noqa: E402
from routes.reviews import reviews_bp  # noqa: E402
from core import msk_time  # noqa: E402
from core.guest_reviews import (ReviewConflict, ReviewNotFound, ReviewStore,  # noqa: E402
                                ReviewStoreUnavailable, build_daily, clean_core, compute_metrics,
                                median, parse_list_query, round_half_up, FORMULAS, BARS)

USER = {'login': 'anna', 'display_name': 'Анна'}
NOW = datetime(2026, 9, 26, 15, 0, tzinfo=msk_time.MOSCOW_TZ)


class Clock:
    """Подменяемые часы: aware МСК; move(minutes) сдвигает время."""

    def __init__(self, start=NOW):
        self.value = start

    def __call__(self):
        return self.value

    def set(self, y, mo, d, h=12, mi=0):
        self.value = datetime(y, mo, d, h, mi, tzinfo=msk_time.MOSCOW_TZ)


def _store(clock=None):
    tmp = tempfile.mkdtemp(prefix='reviews_test_')
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    return ReviewStore(os.path.join(tmp, 'guest_reviews.json'), clock=clock or Clock())


def _add(store, **fields):
    base = {'source': 'yandex', 'bar': 'bolshoy', 'rating': 5, 'text': 'Отлично', 'created_at': '2026-09-20T12:00'}
    base.update(fields)
    return store.add(base, USER)


def _raises(exc, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc as e:
        return e
    raise AssertionError(f'{exc.__name__} не выброшено')


# --- числа ---------------------------------------------------------------------------

def test_round_half_up_and_median():
    assert round_half_up(4.25, 1) == 4.3
    assert round_half_up(4.35, 1) == 4.4          # round(4.35, 1) в Python дал бы 4.3
    assert round(4.35, 1) == 4.3                  # и именно поэтому round() не используется
    assert round_half_up(12.5, 0) == 13 and isinstance(round_half_up(12.5, 0), int)
    assert round_half_up(2.5, 0) == 3 and round_half_up(0.05, 1) == 0.1
    assert round_half_up(None, 1) is None
    assert median([]) is None
    assert median([7]) == 7
    assert median([3, 1, 2]) == 2                 # нечётное: среднее по порядку
    assert median([4, 1, 3, 2]) == 2.5            # чётное: полусумма двух средних
    assert median([10, 20]) == 15


# --- проверка полей ------------------------------------------------------------------

def test_validation():
    s = _store()
    ok = _add(s)
    assert ok['id'].startswith('r_') and len(ok['id']) == 14
    assert ok['status'] == 'new' and ok['origin'] == 'manual' and ok['added_by'] == 'anna'
    assert ok['reply'] is None and ok['material_id'] is None and ok['external_id'] is None
    # у Яндекса оценка обязательна; у бота — нет, но нужен текст или оценка
    e = _raises(ValueError, _add, s, rating=None)
    assert 'Яндекс' in str(e)
    assert _add(s, source='bot', rating=None, text='Было вкусно')['rating'] is None
    assert _add(s, source='bot', rating=4, text='')['text'] == ''
    e = _raises(ValueError, _add, s, source='bot', rating=None, text='   ')
    assert 'текст' in str(e).lower()
    # бар обязателен и конкретный
    for bar in (None, '', 'all', 'moscow'):
        _raises(ValueError, _add, s, bar=bar)
    _raises(ValueError, _add, s, source='')
    _raises(ValueError, _add, s, source='google')
    # оценка: целое 1..5
    for rating in (0, 6, 4.5, '4,5', 'пять', True, [4]):
        _raises(ValueError, _add, s, rating=rating)
    assert _add(s, rating='4')['rating'] == 4 and _add(s, rating=3.0)['rating'] == 3
    # дата: не позже now + 5 минут; формат; год
    assert _add(s, created_at='2026-09-26T15:05')['created_at'] == '2026-09-26T15:05'
    e = _raises(ValueError, _add, s, created_at='2026-09-26T15:06')
    assert 'будущем' in str(e)
    for bad in ('26.09.2026 12:00', '2026-09-31T12:00', '2019-12-31T12:00', '2026-09-26', 123):
        _raises(ValueError, _add, s, created_at=bad)
    assert _add(s, created_at='2026-09-20 08:30:59')['created_at'] == '2026-09-20T08:30'
    assert _add(s, created_at=None)['created_at'] == '2026-09-26T15:00'   # по умолчанию — сейчас
    # длины
    assert _add(s, author='x' * 120)['author'] == 'x' * 120
    _raises(ValueError, _add, s, author='x' * 121)
    _raises(ValueError, _add, s, text='x' * 5001)
    assert _add(s, text='  a\r\nb  ')['text'] == 'a\nb'
    # контакты: только у бота; у Яндекса игнорируются
    assert _add(s, guest={'phone': '+7 900 000-00-00', 'telegram': ''})['guest'] is None
    bot = _add(s, source='bot', guest={'phone': ' +79000000000 ', 'telegram': '@guest'})
    assert bot['guest'] == {'phone': '+79000000000', 'telegram': '@guest'}
    assert _add(s, source='bot', guest={'phone': '', 'telegram': ''})['guest'] is None
    _raises(ValueError, _add, s, source='bot', guest={'phone': '1' * 33})
    _raises(ValueError, _add, s, source='bot', guest='+7900')
    # external_id у ручного отзыва не сохраняется; импорт — сохраняется и дедуплицируется
    assert _add(s, external_id='y1')['external_id'] is None
    imp = s.add({'source': 'yandex', 'bar': 'ligovskiy', 'rating': 2, 'created_at': '2026-09-01T10:00',
                 'external_id': 'y1'}, USER, origin='import')
    assert imp['origin'] == 'import' and imp['external_id'] == 'y1'
    e = _raises(ReviewConflict, s.add, {'source': 'yandex', 'bar': 'ligovskiy', 'rating': 3,
                                        'created_at': '2026-09-02T10:00', 'external_id': 'y1'}, USER, origin='import')
    assert e.extra == {'review_id': imp['id']}
    # чистая функция: тот же вход — тот же выход
    data = {'source': 'bot', 'bar': 'varshavskaya', 'rating': '', 'text': 'x', 'created_at': '2026-09-01T00:00'}
    assert clean_core(data, NOW) == clean_core(data, NOW)


def test_update_revalidates_whole_record():
    s = _store()
    r = _add(s, source='bot', rating=None, text='Текст', guest={'phone': '+7', 'telegram': ''})
    upd = s.update(r['id'], {'bar': 'ligovskiy', 'author': 'Ира', 'status': 'answered', 'id': 'x'}, USER)
    assert upd['bar'] == 'ligovskiy' and upd['author'] == 'Ира' and upd['status'] == 'new' and upd['id'] == r['id']
    _raises(ValueError, s.update, r['id'], {'text': ''}, USER)                      # ни текста, ни оценки
    _raises(ValueError, s.update, r['id'], {'created_at': None}, USER)
    _raises(ValueError, s.update, r['id'], {'created_at': '2026-10-01T00:00'}, USER)
    _raises(ValueError, s.update, r['id'], {'source': 'yandex'}, USER)               # у Яндекса нужна оценка
    moved = s.update(r['id'], {'source': 'yandex', 'rating': 4}, USER)                # ручной: источник меняется
    assert moved['source'] == 'yandex' and moved['guest'] is None                     # контакты у Яндекса не живут
    assert s.update(r['id'], {'reply_draft': 'Спасибо!'}, USER)['reply_draft'] == 'Спасибо!'
    _raises(ReviewNotFound, s.update, 'r_000000000000', {'text': 'x'}, USER)
    imp = s.add({'source': 'yandex', 'bar': 'bolshoy', 'rating': 5, 'created_at': '2026-09-01T10:00',
                 'external_id': 'z'}, USER, origin='import')
    e = _raises(ValueError, s.update, imp['id'], {'source': 'bot'}, USER)
    assert 'Источник' in str(e)
    assert s.update(imp['id'], {'source': 'yandex', 'author': 'Олег'}, USER)['author'] == 'Олег'


# --- список, порядок, метрики --------------------------------------------------------

def test_sort_order_and_hours():
    clock = Clock()
    s = _store(clock)
    a = _add(s, created_at='2026-09-10T10:00')                       # new, самый старый
    b = _add(s, created_at='2026-09-20T10:00')                       # new
    c = _add(s, created_at='2026-09-15T10:00')                       # answered
    d = _add(s, created_at='2026-09-22T10:00')                       # skipped
    e = _add(s, created_at='2026-09-18T10:00')                       # answered
    f = _add(s, created_at='2026-09-26T15:04')                       # new, «в будущем» на 4 минуты
    clock.set(2026, 9, 15, 13, 30)
    s.reply(c['id'], 'Спасибо', USER)                                # 3,5 ч
    clock.set(2026, 9, 26, 15, 0)
    s.reply(e['id'], 'Спасибо', USER)
    s.skip(d['id'], 'спам', USER)
    listing = s.listing({'month': '2026-09'})
    order = [r['id'] for r in listing['reviews']]
    assert order == [a['id'], b['id'], f['id'], d['id'], e['id'], c['id']], order
    by_id = {r['id']: r for r in listing['reviews']}
    assert by_id[a['id']]['age_hours'] == 389.0                      # 16 суток 5 ч
    assert by_id[f['id']]['age_hours'] == 0.0                        # отрицательное -> 0
    assert by_id[c['id']]['response_hours'] == 3.5 and by_id[c['id']]['age_hours'] is None
    assert by_id[d['id']]['age_hours'] is None and by_id[d['id']]['response_hours'] is None
    # ответ раньше даты отзыва (дата «в будущем») -> 0, а не минус
    g = _add(s, created_at='2026-09-26T15:05')
    assert s.decorate(s.reply(g['id'], 'ok', USER))['response_hours'] == 0.0
    # равные даты: по id
    same = [_add(s, created_at='2026-09-05T09:00') for _ in range(3)]
    ids = [r['id'] for r in s.listing({'month': '2026-09'})['reviews'] if r['created_at'] == '2026-09-05T09:00']
    assert ids == sorted(r['id'] for r in same)


def test_metrics_formulas():
    now = datetime(2026, 9, 26, 12, 0)

    def rev(i, status='new', rating=None, created='2026-09-20T12:00', reply_at=None, bar='bolshoy'):
        return {'id': f'r_{i:012d}', 'source': 'yandex', 'bar': bar, 'rating': rating, 'status': status,
                'created_at': created, 'reply': {'text': 'x', 'at': reply_at} if reply_at else None}

    # avg 17/4 = 4,25 -> 4,3; 1 без ответа из 8 = 12,5 % -> 13
    items = [rev(0, 'new', 5, '2026-09-25T12:00')] + [
        rev(i, 'answered', r, '2026-09-20T12:00', '2026-09-20T13:00') for i, r in enumerate([4, 4, 4], 1)] + [
        rev(i, 'skipped', None) for i in range(4, 8)]
    m = compute_metrics(items, now)
    assert m['count'] == 8 and m['rated'] == 4 and m['avg_rating'] == 4.3
    assert m['unanswered'] == 1 and m['answered'] == 3 and m['skipped'] == 4
    assert m['unanswered_pct'] == 13
    assert m['median_response_hours'] == 1.0
    assert m['oldest_unanswered_hours'] == 24.0
    # avg 87/20 = 4,35 -> 4,4
    items = [rev(i, 'skipped', 5) for i in range(7)] + [rev(i, 'skipped', 4) for i in range(7, 20)]
    assert compute_metrics(items, now)['avg_rating'] == 4.4
    # медиана: нечётное (1 ч, 2 ч, 10 ч -> 2), чётное (1 ч, 2 ч, 3 ч, 10 ч -> 2,5)
    odd = [rev(i, 'answered', 5, '2026-09-20T00:00', f'2026-09-20T{h:02d}:00') for i, h in enumerate([10, 1, 2])]
    assert compute_metrics(odd, now)['median_response_hours'] == 2.0
    even = odd + [rev(9, 'answered', 5, '2026-09-20T00:00', '2026-09-20T03:00')]
    assert compute_metrics(even, now)['median_response_hours'] == 2.5
    # половина вверх на медиане: 21 мин и 21 мин -> 0,35 ч -> 0,4
    half = [rev(i, 'answered', 5, '2026-09-20T00:00', '2026-09-20T00:21') for i in range(2)]
    assert compute_metrics(half, now)['median_response_hours'] == 0.4
    # возвращённый в работу (new с ответом) в медиану не входит
    reopened = rev(20, 'new', 5, '2026-09-20T00:00', '2026-09-21T00:00')
    assert compute_metrics(odd + [reopened], now)['median_response_hours'] == 2.0
    # пусто
    empty = compute_metrics([], now)
    assert empty == {'count': 0, 'rated': 0, 'avg_rating': None, 'unanswered': 0, 'answered': 0,
                     'skipped': 0, 'unanswered_pct': None, 'median_response_hours': None,
                     'oldest_unanswered_hours': None}
    # у каждой метрики есть формула для подсказки
    for key in empty:
        assert key in FORMULAS, key


def test_filters_and_metrics_scope():
    s = _store()
    r1 = _add(s, bar='bolshoy', rating=1, created_at='2026-09-01T00:00')
    r2 = _add(s, bar='bolshoy', rating=3, created_at='2026-09-10T00:00')
    r3 = _add(s, bar='ligovskiy', rating=5, created_at='2026-09-25T10:00')
    r4 = _add(s, bar='ligovskiy', source='bot', rating=None, text='т', created_at='2026-09-12T00:00')
    r5 = _add(s, bar='varshavskaya', rating=4, created_at='2026-08-31T23:59')   # прошлый месяц
    s.reply(r2['id'], 'ok', USER)
    s.skip(r3['id'], '', USER)

    def ids(**args):
        return {r['id'] for r in s.listing(args)['reviews']}

    # период по умолчанию — текущий месяц (сентябрь), границы включительно
    assert ids() == {r1['id'], r2['id'], r3['id'], r4['id']}
    assert ids(month='2026-08') == {r5['id']}
    assert ids(all='1') == {r1['id'], r2['id'], r3['id'], r4['id'], r5['id']}
    assert ids(**{'from': '2026-08-31', 'to': '2026-09-01'}) == {r1['id'], r5['id']}
    assert ids(**{'from': '2026-09-12'}) == {r3['id'], r4['id']}
    # оценка
    assert ids(rating='low') == {r1['id']}
    assert ids(rating='mid') == {r2['id']}
    assert ids(rating='high') == {r3['id']}
    assert ids(rating='none') == {r4['id']}
    # статус, источник, бар
    assert ids(status='new') == {r1['id'], r4['id']}
    assert ids(status='answered') == {r2['id']}
    assert ids(status='skipped') == {r3['id']}
    assert ids(source='bot') == {r4['id']}
    assert ids(bar='ligovskiy') == {r3['id'], r4['id']}
    assert ids(bar='all') == ids()
    # метрики: только период и источник
    base = s.listing({})
    filtered = s.listing({'bar': 'ligovskiy', 'rating': 'high', 'status': 'skipped'})
    assert base['metrics'] == filtered['metrics']
    assert base['metrics']['total']['count'] == 4
    assert base['metrics']['by_bar']['bolshoy']['count'] == 2
    assert base['metrics']['by_bar']['kremenchugskaya']['count'] == 0
    assert set(base['metrics']['by_bar']) == {b['key'] for b in BARS}
    assert s.listing({'source': 'bot'})['metrics']['total']['count'] == 1
    assert s.listing({'month': '2026-08'})['metrics']['total']['count'] == 1
    # ответ несёт границы, справочники и формулы
    assert (base['from'], base['to'], base['month'], base['all']) == ('2026-09-01', '2026-09-30', '2026-09', False)
    all_payload = s.listing({'all': '1'})
    assert all_payload['from'] is None and all_payload['to'] is None and all_payload['all'] is True
    assert base['now'] == '2026-09-26T15:00'
    assert base['sources'] == [{'key': 'yandex', 'name': 'Яндекс Карты'}, {'key': 'bot', 'name': 'Бот'}]
    assert [b['short'] for b in base['bars']] == ['ВО', 'Лиг', 'Крем', 'Вар']
    assert base['formulas'] == FORMULAS
    # неверные параметры
    for bad in ({'rating': 'good'}, {'status': 'done'}, {'source': 'vk'}, {'bar': 'x'},
                {'month': '2026-13'}, {'from': '2026-09-10', 'to': '2026-09-01'}, {'from': '10.09.2026'}):
        _raises(ValueError, parse_list_query, bad, NOW)


def test_rating_rejects_huge_input_fast():
    """Запись оценки вида «1e400000» — отказ сразу, без построения огромного числа.

    Раньше int(Decimal('1e400000')) выполнялся ~6 с (1e3000000 — минуты) под
    блокировкой файла отзывов. Порог 1 с с большим запасом: сейчас это доли мс.
    """
    s = _store()
    started = time.perf_counter()
    for bad in ('1e400000', '1E400000', '-1e400000', '1e-400000', '9' * 100000, '5.0000000000',
                10 ** 4000, float('inf'), float('nan'), 1e308, {'v': 5}):
        _raises(ValueError, _add, s, rating=bad)
    assert time.perf_counter() - started < 1.0
    # разумные записи по-прежнему принимаются (10 знаков — с запасом)
    for ok, expected in (('5', 5), (' 4 ', 4), ('5.000', 5), (3.0, 3), (2, 2), ('   3.00000', 3)):
        assert _add(s, rating=ok)['rating'] == expected, ok
    with _client() as (c, s2):
        r = _add(s2)
        started = time.perf_counter()
        resp = c.patch(f'/api/reviews/{r["id"]}', json={'rating': '1e400000'})
        assert resp.status_code == 400 and 'Оценка' in resp.get_json()['error']
        resp = c.post('/api/reviews', json={'source': 'yandex', 'bar': 'bolshoy', 'rating': '1e400000'})
        assert resp.status_code == 400
        assert time.perf_counter() - started < 1.0


def test_reply_draft_kept_as_typed():
    """Черновик хранится как набран: пробел и перевод строки в конце не теряются после перезагрузки."""
    s = _store()
    r = _add(s)
    typed = 'Игорь, простите за ожидание. '
    assert s.update(r['id'], {'reply_draft': typed}, USER)['reply_draft'] == typed
    assert ReviewStore(s.data_file, clock=Clock()).get(r['id'])['reply_draft'] == typed   # и в файле
    assert s.update(r['id'], {'reply_draft': '  Здравствуйте!\r\n\r\n'}, USER)['reply_draft'] == '  Здравствуйте!\n\n'
    assert s.update(r['id'], {'reply_draft': ' \n\t '}, USER)['reply_draft'] == ''      # одни пробелы -> пусто
    assert s.update(r['id'], {'reply_draft': None}, USER)['reply_draft'] == ''
    # длина — по тексту как есть, с пробелами
    assert len(s.update(r['id'], {'reply_draft': 'x' * 3999 + ' '}, USER)['reply_draft']) == 4000
    _raises(ValueError, s.update, r['id'], {'reply_draft': 'x' * 3999 + '  '}, USER)
    _raises(ValueError, s.update, r['id'], {'reply_draft': ['x']}, USER)
    # правка других полей черновик не трогает; при добавлении — так же без обрезки
    s.update(r['id'], {'reply_draft': typed}, USER)
    assert s.update(r['id'], {'author': 'Игорь'}, USER)['reply_draft'] == typed
    assert _add(s, reply_draft='Спасибо, ')['reply_draft'] == 'Спасибо, '
    # итоговый ответ по-прежнему обрезается по краям, черновик очищается
    ans = s.reply(r['id'], typed + 'В выходные добавили второго бармена.  \n', USER)
    assert ans['reply']['text'] == 'Игорь, простите за ожидание. В выходные добавили второго бармена.'
    assert ans['reply_draft'] == ''
    with _client() as (c, s2):
        r2 = _add(s2)
        resp = c.patch(f'/api/reviews/{r2["id"]}', json={'reply_draft': typed})
        assert resp.status_code == 200 and resp.get_json()['review']['reply_draft'] == typed


def test_response_time_formula_matches_code():
    """Формулы времени ответа описывают код: правка момент не меняет, после возврата — новый ответ."""
    clock = Clock()
    clock.set(2026, 9, 20, 14, 0)
    s = _store(clock)
    r = _add(s, created_at='2026-09-20T12:00')
    assert s.decorate(s.reply(r['id'], 'Спасибо', USER))['response_hours'] == 2.0
    clock.set(2026, 9, 21, 9, 0)
    assert s.decorate(s.reply(r['id'], 'Спасибо!', USER))['response_hours'] == 2.0      # правка
    s.reopen(r['id'], USER)
    clock.set(2026, 9, 22, 14, 0)
    again = s.reply(r['id'], 'Новый ответ', USER)
    assert s.decorate(again)['response_hours'] == 50.0          # после «Вернуть в работу» — до нового ответа
    assert s.listing({'month': '2026-09'})['metrics']['total']['median_response_hours'] == 50.0
    for key in ('response_hours', 'median_response_hours'):
        text = FORMULAS[key]
        assert 'первого' not in text, key
        for part in ('правка ответа его не меняет', '«Вернуть в работу»', 'следующее сохранение ответа'):
            assert part in text, (key, part)


def test_link_material_replace_and_material_exists():
    """replace перезаписывает только ту же устаревшую ссылку; material_exists — по одной проверке на запрос."""
    s = _store()
    r = _add(s)
    assert s.link_material(r['id'], 'm_1', USER)['material_id'] == 'm_1'
    e = _raises(ReviewConflict, s.link_material, r['id'], 'm_2', USER)
    assert e.extra == {'material_id': 'm_1'}
    e = _raises(ReviewConflict, s.link_material, r['id'], 'm_2', USER, replace='m_other')
    assert e.extra == {'material_id': 'm_1'}                    # в отзыве не тот id — гонка, конфликт
    assert s.link_material(r['id'], 'm_2', USER, replace='m_1')['material_id'] == 'm_2'
    r2 = _add(s)
    assert s.link_material(r2['id'], 'm_3', USER, replace='m_x')['material_id'] == 'm_3'   # ссылки не было
    # decorate: без проверки -> null; по ответу проверки; сбой или не словарь -> null
    rec = s.get(r['id'])
    assert s.decorate(rec)['material_exists'] is None
    assert s.decorate(rec, lambda ids: {i: False for i in ids})['material_exists'] is False
    assert s.decorate(rec, lambda ids: {i: True for i in ids})['material_exists'] is True
    assert s.decorate(rec, lambda ids: {})['material_exists'] is None

    def boom(ids):
        raise RuntimeError('контент-план упал')
    assert s.decorate(rec, boom)['material_exists'] is None
    assert s.decorate(rec, lambda ids: 'не словарь')['material_exists'] is None
    # список: одна проверка на все разные id показанных отзывов; без ссылок — не вызывается
    s = _store()
    a, b, c, d = (_add(s, bar=bar) for bar in ('bolshoy', 'bolshoy', 'ligovskiy', 'ligovskiy'))
    s.link_material(a['id'], 'm_b', USER)
    s.link_material(b['id'], 'm_a', USER)
    s.link_material(c['id'], 'm_a', USER)
    calls = []

    def lookup(ids):
        calls.append(list(ids))
        return {'m_a': True, 'm_b': False}
    rows = {x['id']: x for x in s.listing({}, material_lookup=lookup)['reviews']}
    assert calls == [['m_a', 'm_b']]
    assert rows[a['id']]['material_exists'] is False and rows[b['id']]['material_exists'] is True
    assert rows[c['id']]['material_exists'] is True and rows[d['id']]['material_exists'] is None
    calls.clear()
    rows = s.listing({'bar': 'ligovskiy'}, material_lookup=lookup)['reviews']
    assert calls == [['m_a']] and len(rows) == 2
    calls.clear()
    s.update(c['id'], {'bar': 'bolshoy'}, USER)
    assert s.listing({'bar': 'ligovskiy'}, material_lookup=lookup)['reviews'][0]['material_exists'] is None
    assert calls == []                                          # у показанных нет ссылок — контент-план не трогаем


# --- переходы -----------------------------------------------------------------------

def test_reply_skip_reopen_transitions():
    clock = Clock()
    s = _store(clock)
    r = _add(s, created_at='2026-09-26T10:00')
    s.update(r['id'], {'reply_draft': 'черновик'}, USER)
    _raises(ValueError, s.reply, r['id'], '   ', USER)
    _raises(ValueError, s.reply, r['id'], 'x' * 4001, USER)
    ans = s.reply(r['id'], 'Спасибо!', USER)
    assert ans['status'] == 'answered' and ans['reply_draft'] == ''
    assert ans['reply'] == {'text': 'Спасибо!', 'at': '2026-09-26T15:00', 'by': 'anna', 'delivered': False}
    # правка ответа: момент ответа не меняется
    clock.set(2026, 9, 27, 9, 0)
    edited = s.reply(r['id'], 'Спасибо, ждём снова!', {'display_name': 'Оля'})
    assert edited['reply']['at'] == '2026-09-26T15:00' and edited['reply']['text'] == 'Спасибо, ждём снова!'
    assert edited['reply']['edited_at'] == '2026-09-27T09:00' and edited['reply']['edited_by'] == 'Оля'
    assert s.decorate(edited)['response_hours'] == 5.0
    _raises(ReviewConflict, s.skip, r['id'], 'x', USER)                  # skip только из new
    # reopen answered -> new, ответ остаётся
    back = s.reopen(r['id'], USER)
    assert back['status'] == 'new' and back['reply']['text'] == 'Спасибо, ждём снова!'
    _raises(ReviewConflict, s.reopen, r['id'], USER)                     # уже new
    sk = s.skip(r['id'], '  спам  ', None)
    assert sk['status'] == 'skipped' and sk['skip_reason'] == 'спам' and sk['updated_by'] == 'unknown'
    _raises(ValueError, s.skip, r['id'], 'x' * 501, USER)
    _raises(ReviewConflict, s.reply, r['id'], 'поздно', USER)            # сначала вернуть в работу
    assert s.reopen(r['id'], USER)['status'] == 'new'
    # новый ответ после возврата — с новым моментом
    again = s.reply(r['id'], 'Новый ответ', USER)
    assert again['reply']['at'] == '2026-09-27T09:00' and 'edited_at' not in again['reply']
    _raises(ReviewNotFound, s.reply, 'r_nope', 'x', USER)


def test_delete_only_manual():
    s = _store()
    manual = _add(s)
    imp = s.add({'source': 'yandex', 'bar': 'bolshoy', 'rating': 5, 'created_at': '2026-09-01T10:00',
                 'external_id': 'q'}, USER, origin='import')
    _raises(ReviewConflict, s.delete, imp['id'])
    s.delete(manual['id'])
    assert s.get(manual['id']) is None and s.get(imp['id']) is not None
    _raises(ReviewNotFound, s.delete, manual['id'])


def test_daily_layer():
    s = _store()
    _add(s, bar='bolshoy', rating=5, created_at='2026-09-03T10:00')
    _add(s, bar='bolshoy', rating=4, created_at='2026-09-03T20:00')
    _add(s, bar='ligovskiy', source='bot', rating=None, text='т', created_at='2026-09-03T21:00')
    _add(s, bar='ligovskiy', rating=4, created_at='2026-09-04T10:00')
    _add(s, bar='ligovskiy', rating=4, created_at='2026-08-04T10:00')
    d = s.daily('2026-09')
    assert d == {'month': '2026-09', 'days': {'2026-09-03': {'count': 3, 'rated': 2, 'avg': 4.5},
                                              '2026-09-04': {'count': 1, 'rated': 1, 'avg': 4.0}}}
    assert s.daily('2026-09', bar='ligovskiy')['days'] == {'2026-09-03': {'count': 1, 'rated': 0, 'avg': None},
                                                           '2026-09-04': {'count': 1, 'rated': 1, 'avg': 4.0}}
    assert s.daily('2026-09', source='bot')['days'] == {'2026-09-03': {'count': 1, 'rated': 0, 'avg': None}}
    assert s.daily()['month'] == '2026-09'                                 # по умолчанию — текущий месяц
    assert s.daily('2026-09', bar='all') == d
    _raises(ValueError, s.daily, '2026-9')
    _raises(ValueError, s.daily, '2026-09', bar='x')
    assert build_daily([], '2026-09') == {'month': '2026-09', 'days': {}}


def test_persistence_and_corrupt_file():
    s = _store()
    r = _add(s, author='Ира')
    again = ReviewStore(s.data_file, clock=Clock())
    assert again.get(r['id'])['author'] == 'Ира'
    s.update(r['id'], {'author': 'Ирина'}, USER)
    assert again.get(r['id'])['author'] == 'Ирина'                       # кэш сбрасывается по файлу
    for broken in ('{broken', '', '[]', '{"version": 1, "reviews": []}',
                   '{"version": 1, "reviews": {"r_1": {"id": "r_2"}}}',
                   '{"version": 1, "reviews": {"r_1": {"id": "r_1", "source": "yandex", "bar": "bolshoy", '
                   '"status": "new", "created_at": "2026-09-01T10:00", "rating": 9}}}'):
        with open(s.data_file, 'w', encoding='utf-8') as f:
            f.write(broken)
        for call in (s.all, lambda: s.listing({}), lambda: s.unanswered_count(),
                     lambda: _add(s), lambda: s.delete('r_1'), lambda: s.reopen('r_1', USER)):
            _raises(ReviewStoreUnavailable, call)
        assert open(s.data_file, encoding='utf-8').read() == broken
    # нет файла — пустое хранилище
    os.remove(s.data_file)
    assert s.all() == [] and s.unanswered_count() == 0 and not s.is_stored()


# --- API ----------------------------------------------------------------------------------

class FakeContentStore:
    """Фейк контент-плана: fail — сбой всего модуля, fail_get — сбой только чтения материала."""

    def __init__(self, counts=None, fail=None, fail_get=None):
        self.created = []
        self.materials = {}
        self.counts = counts or {'publications_today': 2, 'delivery_errors': 0, 'overdue': 1}
        self.fail = fail
        self.fail_get = fail_get
        self.attention_calls = []
        self.get_calls = []

    def create_material(self, fields, user):
        if self.fail:
            raise self.fail
        if not fields.get('title'):
            raise ValueError('Нужно название')
        mid = f'm_{len(self.created):012x}'
        self.created.append((dict(fields), user))
        self.materials[mid] = {'id': mid, 'month': fields['month'], 'title': fields['title']}
        return dict(self.materials[mid])

    def get_material_raw(self, material_id):
        """Как настоящий: нет материала -> core.content_plan.ContentPlanNotFound."""
        self.get_calls.append(material_id)
        if self.fail_get or self.fail:
            raise self.fail_get or self.fail
        if material_id not in self.materials:
            from core.content_plan import ContentPlanNotFound
            raise ContentPlanNotFound('Материал не найден')
        return dict(self.materials[material_id])

    def delete_material(self, material_id, user=None):
        del self.materials[material_id]
        return True

    def attention_counts(self, bar=None, now=None):
        self.attention_calls.append(bar)
        if self.fail:
            raise self.fail
        return dict(self.counts)


@contextmanager
def _client(content=None, clock=None):
    s = _store(clock)
    saved = (rrev.get_review_store, rrev.current_user, rrev._content_plan_store)
    rrev.get_review_store = lambda *a, **k: s
    rrev.current_user = lambda: USER
    if isinstance(content, Exception):
        def failing():
            raise content
        rrev._content_plan_store = failing
    elif content is not None:
        rrev._content_plan_store = lambda: content
    app = Flask('test_reviews')
    app.register_blueprint(reviews_bp)
    try:
        yield app.test_client(), s
    finally:
        rrev.get_review_store, rrev.current_user, rrev._content_plan_store = saved


def test_api_crud_and_actions():
    with _client() as (c, s):
        r = c.post('/api/reviews', json={'source': 'yandex', 'bar': 'bolshoy', 'text': 'Нет оценки'})
        assert r.status_code == 400 and 'оценка' in r.get_json()['error']
        r = c.post('/api/reviews', json={'source': 'yandex', 'bar': 'all', 'rating': 5})
        assert r.status_code == 400
        r = c.post('/api/reviews', json={'source': 'yandex', 'bar': 'bolshoy', 'rating': 5,
                                         'created_at': '2026-09-27T12:00'})
        assert r.status_code == 400 and 'будущем' in r.get_json()['error']
        r = c.post('/api/reviews', data='not json')
        assert r.status_code == 400
        r = c.post('/api/reviews', json={'source': 'yandex', 'bar': 'bolshoy', 'rating': 2, 'text': 'Долго',
                                         'author': 'Пётр', 'created_at': '2026-09-26T09:00'})
        payload = r.get_json()
        assert r.status_code == 200, payload
        rid = payload['review']['id']
        assert payload['review']['age_hours'] == 6.0 and payload['review']['added_by'] == 'anna'

        r = c.patch(f'/api/reviews/{rid}', json={'rating': 3, 'reply_draft': 'Извините'})
        assert r.status_code == 200 and r.get_json()['review']['rating'] == 3
        assert c.patch(f'/api/reviews/{rid}', json={'rating': 9}).status_code == 400
        assert c.patch('/api/reviews/r_nope', json={'rating': 3}).status_code == 404

        r = c.post(f'/api/reviews/{rid}/reply', json={'text': ''})
        assert r.status_code == 400
        r = c.post(f'/api/reviews/{rid}/reply', json={'text': 'Простите за ожидание'})
        rev = r.get_json()['review']
        assert r.status_code == 200 and rev['status'] == 'answered' and rev['reply']['delivered'] is False
        assert rev['response_hours'] == 6.0 and rev['reply_draft'] == ''
        r = c.post(f'/api/reviews/{rid}/action', json={'action': 'skip'})
        assert r.status_code == 409 and r.get_json()['error']
        r = c.post(f'/api/reviews/{rid}/action', json={'action': 'reopen'})
        assert r.status_code == 200 and r.get_json()['review']['status'] == 'new'
        r = c.post(f'/api/reviews/{rid}/action', json={'action': 'skip', 'reason': 'конкурент'})
        assert r.status_code == 200 and r.get_json()['review']['skip_reason'] == 'конкурент'
        assert c.post(f'/api/reviews/{rid}/action', json={'action': 'archive'}).status_code == 400
        assert c.post('/api/reviews/r_nope/action', json={'action': 'reopen'}).status_code == 404

        imp = s.add({'source': 'yandex', 'bar': 'ligovskiy', 'rating': 1, 'created_at': '2026-09-02T10:00',
                     'external_id': 'e'}, USER, origin='import')
        r = c.delete(f'/api/reviews/{imp["id"]}')
        assert r.status_code == 409 and 'удалить нельзя' in r.get_json()['error']
        assert c.delete(f'/api/reviews/{rid}').get_json() == {'deleted': True}
        assert c.delete(f'/api/reviews/{rid}').status_code == 404


def test_api_listing_and_daily():
    with _client() as (c, s):
        _add(s, bar='bolshoy', rating=5, created_at='2026-09-03T10:00')
        _add(s, bar='ligovskiy', rating=4, created_at='2026-09-04T10:00')
        _add(s, bar='ligovskiy', rating=4, created_at='2026-08-04T10:00')
        r = c.get('/api/reviews')
        p = r.get_json()
        assert r.status_code == 200
        for key in ('now', 'from', 'to', 'reviews', 'metrics', 'formulas', 'sources', 'bars'):
            assert key in p, key
        assert len(p['reviews']) == 2 and p['metrics']['total']['avg_rating'] == 4.5
        assert len(c.get('/api/reviews?all=1').get_json()['reviews']) == 3
        assert len(c.get('/api/reviews?bar=ligovskiy&all=1').get_json()['reviews']) == 2
        assert c.get('/api/reviews?rating=bad').status_code == 400
        d = c.get('/api/reviews/daily?month=2026-09&bar=ligovskiy').get_json()
        assert d['days'] == {'2026-09-04': {'count': 1, 'rated': 1, 'avg': 4.0}}
        assert c.get('/api/reviews/daily?month=xx').status_code == 400


def test_api_to_material():
    fake = FakeContentStore()
    with _client(fake) as (c, s):
        r1 = _add(s, bar='varshavskaya', text='Лучший таплист', author='')
        r = c.post(f'/api/reviews/{r1["id"]}/to-material', json={})
        p = r.get_json()
        assert r.status_code == 200, p
        assert p['material_id'] == 'm_000000000000' and p['month'] == '2026-09'
        assert p['review']['material_id'] == p['material_id']
        fields, user = fake.created[0]
        assert fields == {'month': '2026-09', 'title': 'Отзыв гостя — Вар', 'kind': 'fixed',
                          'base_text': '«Лучший таплист»\n— гость', 'source_review_id': r1['id']}
        assert user == USER
        # повтор -> 409 с id существующего материала, второй материал не создаётся
        r = c.post(f'/api/reviews/{r1["id"]}/to-material', json={'month': '2026-10'})
        assert r.status_code == 409 and r.get_json()['material_id'] == 'm_000000000000'
        assert len(fake.created) == 1
        # месяц из тела, автор в подписи
        r2 = _add(s, bar='bolshoy', text='Уютно', author='Ира')
        p = c.post(f'/api/reviews/{r2["id"]}/to-material', json={'month': '2026-10'}).get_json()
        assert p['month'] == '2026-10' and fake.created[1][0]['base_text'] == '«Уютно»\n— Ира'
        assert fake.created[1][0]['title'] == 'Отзыв гостя — ВО'
        # плохой месяц, отзыв без текста, нет отзыва
        r3 = _add(s, text='')
        assert c.post(f'/api/reviews/{r3["id"]}/to-material', json={'month': '2026-13'}).status_code == 400
        r = c.post(f'/api/reviews/{r3["id"]}/to-material', json={})
        assert r.status_code == 400 and 'нет текста' in r.get_json()['error']
        assert c.post('/api/reviews/r_nope/to-material', json={}).status_code == 404
        # гонка: материал привязали между проверкой и привязкой -> 409
        r4 = _add(s, text='Гонка')
        orig_create = fake.create_material

        def racing(fields, user):
            material = orig_create(fields, user)
            s.link_material(r4['id'], 'm_other', USER)
            return material
        fake.create_material = racing
        r = c.post(f'/api/reviews/{r4["id"]}/to-material', json={})
        assert r.status_code == 409 and r.get_json()['material_id'] == 'm_other'
    # контент-план недоступен -> 503 с кодом, отзыв не помечен
    for failure in (RuntimeError('файл битый'), ImportError('no module')):
        with _client(FakeContentStore(fail=failure)) as (c, s):
            r1 = _add(s)
            r = c.post(f'/api/reviews/{r1["id"]}/to-material', json={})
            assert r.status_code == 503 and r.get_json()['code'] == 'content_plan_unavailable'
            assert s.get(r1['id'])['material_id'] is None
    with _client(ImportError('no module core.content_plan')) as (c, s):
        r1 = _add(s)
        assert c.post(f'/api/reviews/{r1["id"]}/to-material', json={}).status_code == 503
    # проверка контент-плана (ValueError) -> 400 с его текстом
    with _client(FakeContentStore(fail=ValueError('Месяц уже прошёл'))) as (c, s):
        r1 = _add(s)
        r = c.post(f'/api/reviews/{r1["id"]}/to-material', json={})
        assert r.status_code == 400 and r.get_json()['error'] == 'Месяц уже прошёл'


def _content_plan_importable() -> bool:
    """routes/reviews.py узнаёт «материала нет» по core.content_plan.ContentPlanNotFound."""
    try:
        import core.content_plan  # noqa: F401
    except Exception as e:  # noqa: BLE001
        _skip(f'core.content_plan не импортируется: {e!r}')
        return False
    return True


def test_api_material_exists_and_stale_link():
    """Материал удалили в контент-плане: false в отзыве, «Сделать материалом» делает новый (200)."""
    if not _content_plan_importable():
        return
    fake = FakeContentStore()
    with _client(fake) as (c, s):
        plain = _add(s, text='Без материала')
        r1 = _add(s, bar='varshavskaya', text='Лучший таплист')
        r2 = _add(s, bar='bolshoy', text='Уютно')
        p = c.post(f'/api/reviews/{r1["id"]}/to-material', json={}).get_json()
        m1 = p['material_id']
        assert p['review']['material_exists'] is True
        m2 = c.post(f'/api/reviews/{r2["id"]}/to-material', json={}).get_json()['material_id']
        fake.get_calls.clear()
        rows = {x['id']: x for x in c.get('/api/reviews').get_json()['reviews']}
        assert rows[plain['id']]['material_exists'] is None             # ссылки нет — не проверялось
        assert rows[r1['id']]['material_exists'] is True and rows[r2['id']]['material_exists'] is True
        assert sorted(fake.get_calls) == sorted([m1, m2])               # один проход: по разу на id
        # материал удалили в контент-плане -> false; ссылка остаётся до нового «Сделать материалом»
        fake.delete_material(m1)
        rows = {x['id']: x for x in c.get('/api/reviews').get_json()['reviews']}
        assert rows[r1['id']]['material_exists'] is False and rows[r1['id']]['material_id'] == m1
        assert rows[r2['id']]['material_exists'] is True
        # одиночные ответы тоже несут material_exists
        r = c.patch(f'/api/reviews/{r1["id"]}', json={'reply_draft': 'Спасибо'})
        assert r.status_code == 200 and r.get_json()['review']['material_exists'] is False
        r = c.post(f'/api/reviews/{r2["id"]}/reply', json={'text': 'Спасибо!'})
        assert r.get_json()['review']['material_exists'] is True
        r = c.post(f'/api/reviews/{r2["id"]}/action', json={'action': 'reopen'})
        assert r.get_json()['review']['material_exists'] is True
        r = c.post('/api/reviews', json={'source': 'yandex', 'bar': 'bolshoy', 'rating': 5})
        assert r.get_json()['review']['material_exists'] is None
        # живой материал -> 409, как раньше
        r = c.post(f'/api/reviews/{r2["id"]}/to-material', json={})
        assert r.status_code == 409 and r.get_json()['material_id'] == m2
        # устаревшая ссылка -> новый материал (200), ссылка заменена
        n_created = len(fake.created)
        r = c.post(f'/api/reviews/{r1["id"]}/to-material', json={'month': '2026-10'})
        p = r.get_json()
        assert r.status_code == 200, p
        assert p['material_id'] not in (m1, m2) and p['review']['material_id'] == p['material_id']
        assert p['review']['material_exists'] is True and p['month'] == '2026-10'
        assert len(fake.created) == n_created + 1 and s.get(r1['id'])['material_id'] == p['material_id']
        assert fake.created[-1][0]['source_review_id'] == r1['id']
        # новый материал жив -> снова 409
        r = c.post(f'/api/reviews/{r1["id"]}/to-material', json={})
        assert r.status_code == 409 and r.get_json()['material_id'] == p['material_id']
        # гонка на устаревшей ссылке: пока создавали, другой запрос уже заменил её -> 409 с его id
        r3 = _add(s, text='Гонка')
        s.link_material(r3['id'], 'm_gone', USER)
        orig_create = fake.create_material

        def racing(fields, user):
            material = orig_create(fields, user)
            s.link_material(r3['id'], 'm_other', USER, replace='m_gone')
            return material
        fake.create_material = racing
        r = c.post(f'/api/reviews/{r3["id"]}/to-material', json={})
        assert r.status_code == 409 and r.get_json()['material_id'] == 'm_other'
        assert s.get(r3['id'])['material_id'] == 'm_other'
    # контент-план не читается: material_exists null (не 500), ссылку не трогаем — 409, материал не создаётся
    for content in (FakeContentStore(fail_get=RuntimeError('битый файл')), ImportError('нет модуля')):
        with _client(content) as (c, s):
            r1 = _add(s, text='Хорошо')
            s.link_material(r1['id'], 'm_gone', USER)
            r = c.get('/api/reviews')
            assert r.status_code == 200 and r.get_json()['reviews'][0]['material_exists'] is None
            r = c.patch(f'/api/reviews/{r1["id"]}', json={'author': 'Оля'})
            assert r.status_code == 200 and r.get_json()['review']['material_exists'] is None
            r = c.post(f'/api/reviews/{r1["id"]}/to-material', json={})
            assert r.status_code == 409 and r.get_json()['material_id'] == 'm_gone'
            assert s.get(r1['id'])['material_id'] == 'm_gone'
            if isinstance(content, FakeContentStore):
                assert content.created == []


def test_api_attention():
    fake = FakeContentStore()
    with _client(fake) as (c, s):
        _add(s, bar='bolshoy', created_at='2025-01-10T10:00')          # старый, но без ответа — считается
        _add(s, bar='bolshoy')
        done = _add(s, bar='ligovskiy')
        _add(s, bar='ligovskiy')
        s.reply(done['id'], 'ok', USER)
        r = c.get('/api/guest-hub/attention')
        assert r.status_code == 200
        assert r.get_json() == {'reviews_unanswered': 3, 'publications_today': 2, 'delivery_errors': 0,
                                'overdue': 1, 'content_available': True}
        assert fake.attention_calls == [None]
        p = c.get('/api/guest-hub/attention?bar=bolshoy').get_json()
        assert p['reviews_unanswered'] == 2 and fake.attention_calls[-1] == 'bolshoy'
        assert c.get('/api/guest-hub/attention?bar=all').get_json()['reviews_unanswered'] == 3
        assert fake.attention_calls[-1] is None
        assert c.get('/api/guest-hub/attention?bar=moscow').status_code == 400
        # битый файл отзывов: не 500, счётчик отзывов null
        with open(s.data_file, 'w', encoding='utf-8') as f:
            f.write('{broken')
        r = c.get('/api/guest-hub/attention')
        assert r.status_code == 200 and r.get_json()['reviews_unanswered'] is None
        assert r.get_json()['publications_today'] == 2
        assert c.get('/api/reviews').status_code == 503
        assert c.get('/api/reviews').get_json()['code'] == 'reviews_unavailable'
    # падающий контент-план и отсутствующий модуль -> null в его счётчиках, 200
    for content in (FakeContentStore(fail=RuntimeError('битый файл')), ImportError('нет модуля'),
                    FakeContentStore(counts={'publications_today': 'x', 'overdue': True})):
        with _client(content) as (c, s):
            _add(s)
            r = c.get('/api/guest-hub/attention')
            p = r.get_json()
            assert r.status_code == 200 and p['reviews_unanswered'] == 1
            assert p['publications_today'] is None and p['delivery_errors'] is None and p['overdue'] is None
            if not isinstance(content, FakeContentStore) or content.fail:
                assert p['content_available'] is False


def test_api_corrupt_file_503_and_untouched():
    with _client() as (c, s):
        _add(s)
        with open(s.data_file, 'w', encoding='utf-8') as f:
            f.write('{"version": 1, "reviews": "oops"}')
        for method, url, body in (('get', '/api/reviews', None),
                                  ('post', '/api/reviews', {'source': 'yandex', 'bar': 'bolshoy', 'rating': 5}),
                                  ('patch', '/api/reviews/r_1', {'rating': 5}),
                                  ('delete', '/api/reviews/r_1', None),
                                  ('post', '/api/reviews/r_1/reply', {'text': 'x'}),
                                  ('post', '/api/reviews/r_1/action', {'action': 'skip'}),
                                  ('post', '/api/reviews/r_1/to-material', {}),
                                  ('get', '/api/reviews/daily', None)):
            r = getattr(c, method)(url, json=body) if body is not None else getattr(c, method)(url)
            assert r.status_code == 503, (method, url, r.status_code)
            assert r.get_json()['code'] == 'reviews_unavailable' and r.get_json()['error']
        assert open(s.data_file, encoding='utf-8').read() == '{"version": 1, "reviews": "oops"}'


def test_page_route_renders_template():
    """Страница отдаёт reviews.html с версией; extensions подменён (настоящий тяжёлый)."""
    calls = []
    saved_render = rrev.render_template
    saved_ext = sys.modules.get('extensions')
    rrev.render_template = lambda name, **ctx: calls.append((name, ctx)) or 'ok'
    sys.modules['extensions'] = types.SimpleNamespace(APP_VERSION='abc123')
    try:
        app = Flask('test_reviews_page')
        app.register_blueprint(reviews_bp)
        r = app.test_client().get('/reviews')
        assert r.status_code == 200 and calls == [('reviews.html', {'app_version': 'abc123'})]
    finally:
        rrev.render_template = saved_render
        if saved_ext is None:
            sys.modules.pop('extensions', None)
        else:
            sys.modules['extensions'] = saved_ext


def test_integration_real_content_plan():
    """С настоящим core/content_plan.py на временном файле (пропуск, если модуля нет)."""
    try:
        import core.content_plan as cp
    except Exception as e:  # noqa: BLE001
        _skip(f'core.content_plan не импортируется: {e!r}')
        return
    tmp = tempfile.mkdtemp(prefix='reviews_cp_test_')
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    cp_store = _make_content_store(cp, os.path.join(tmp, 'content_plan.json'))
    if cp_store is None:
        _skip('не удалось создать хранилище контент-плана на временном файле')
        return
    with _client(cp_store) as (c, s):
        # Хранилище отзывов в тесте живёт на замороженных часах (NOW), поэтому дата
        # отзыва берётся от них, а не от реального времени — иначе «отзыв из будущего».
        month = NOW.strftime('%Y-%m')
        r1 = _add(s, bar='kremenchugskaya', text='Спасибо за вечер', author='Ира',
                  created_at=NOW.strftime('%Y-%m-%dT%H:%M'))
        r = c.post(f'/api/reviews/{r1["id"]}/to-material', json={'month': month})
        p = r.get_json()
        assert r.status_code == 200, p
        assert p['material_id'].startswith('m_') and p['month'] == month
        assert c.post(f'/api/reviews/{r1["id"]}/to-material', json={}).status_code == 409
        att = c.get('/api/guest-hub/attention?bar=kremenchugskaya').get_json()
        assert att['content_available'] is True and att['reviews_unanswered'] == 1
        for key in ('publications_today', 'delivery_errors', 'overdue'):
            assert isinstance(att[key], int), (key, att)
        rows = {x['id']: x for x in c.get('/api/reviews').get_json()['reviews']}
        assert rows[r1['id']]['material_exists'] is True
        # материал удалили в контент-плане -> false; «Сделать материалом» создаёт новый и заменяет ссылку
        cp_store.delete_material(p['material_id'], USER)
        rows = {x['id']: x for x in c.get('/api/reviews').get_json()['reviews']}
        assert rows[r1['id']]['material_exists'] is False
        r = c.post(f'/api/reviews/{r1["id"]}/to-material', json={'month': month})
        p2 = r.get_json()
        assert r.status_code == 200, p2
        assert p2['material_id'] != p['material_id'] and p2['review']['material_exists'] is True
        assert cp_store.get_material_raw(p2['material_id'])['source_review_id'] == r1['id']
        # файл контент-плана битый -> material_exists null (не 500), повтор -> 409, ссылка та же
        with open(cp_store.data_file, 'w', encoding='utf-8') as f:
            f.write('{broken')
        r = c.get('/api/reviews')
        assert r.status_code == 200 and r.get_json()['reviews'][0]['material_exists'] is None
        r = c.post(f'/api/reviews/{r1["id"]}/to-material', json={})
        assert r.status_code == 409 and r.get_json()['material_id'] == p2['material_id']


def _make_content_store(cp, path):
    """Хранилище контент-плана на временном файле: класс с data_file или геттер с data_file."""
    for name in ('ContentPlanStore', 'ContentPlan'):
        cls = getattr(cp, name, None)
        if cls is not None:
            try:
                return cls(path)
            except Exception:  # noqa: BLE001
                try:
                    return cls(data_file=path)
                except Exception:  # noqa: BLE001
                    pass
    return None


def _skip(reason):
    """Под pytest — pytest.skip; при самостоятельном запуске — просто сообщение."""
    if __name__ == '__main__':
        print(f'skip: {reason}')
        return
    import pytest
    pytest.skip(reason)


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
