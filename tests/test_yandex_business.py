"""
Тесты клиента кабинета Яндекс Бизнеса (core/yandex_business.py) и
диагностического скрипта (scripts/yandex_reviews_probe.py).

Self-runnable: `py -3 tests/test_yandex_business.py` (совместимо с pytest).

Сети нет: HTTP подменяется фейком с заранее заданными ответами, паузы —
заглушкой (повторы не ждут). Что проверяется:
- метка Unix -> московская строка, секунды и миллисекунды;
- разбор отзыва: полный, неполный (замечания вместо исключения), оценка вне
  1..5, ответ организации, фото, служебные токены не переносятся;
- протухшая сессия (переадресация на вход, 401) и капча — сразу ошибка, без
  повторов; 5xx и сеть — повторы с паузами 2 и 6 с, затем ошибка;
- значения cookies не попадают в тексты ошибок;
- пагинация отзывов по page: остановка по total, по пустой странице, ошибка
  при повторе страницы (без бесконечного цикла);
- организации: сеть раскрывается в филиалы, повторы по permanent_id убраны;
- скрипт: без cookies — код 2 и ни одного запроса; --dump вырезает токены.
"""
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import requests  # noqa: E402

from core import msk_time  # noqa: E402
from core import yandex_business as yb  # noqa: E402

SID, SID2 = 'SECRET-session-id-3:1758800000.5.0.1', 'SECRET-sessionid2-3:1758800000.5.0.1'


class FakeResp:
    def __init__(self, status=200, data=None, headers=None, text=None):
        self.status_code = status
        self._data = data
        self.headers = headers or {}
        self.text = text if text is not None else ''

    def json(self):
        if self._data is None:
            raise ValueError('not json')
        return self._data


class FakeHttp:
    """requests.Session-подобный фейк: ответы по очереди из списка или функцией (url, params)."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.cookies = requests.cookies.RequestsCookieJar()

    def get(self, url, params=None, allow_redirects=True, timeout=None):
        self.calls.append((url, dict(params or {})))
        if callable(self.responses):
            r = self.responses(url, dict(params or {}))
        else:
            r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _client(responses):
    sleeps = []
    http = FakeHttp(responses)
    api = yb.YandexBusinessClient(SID, SID2, http=http, sleep=sleeps.append, pause_sec=0)
    return api, http, sleeps


def _msk_ts(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=msk_time.MOSCOW_TZ).timestamp())


def _raises(exc_type, fn):
    try:
        fn()
    except exc_type as e:
        return e
    raise AssertionError(f'ожидалось {exc_type.__name__}')


def _review(rid, **over):
    raw = {
        'id': rid, 'lang': 'ru',
        'author': {'privacy': 'NAME', 'user': 'Иван И.', 'uid': 1, 'avatar': 'https://avatars/1'},
        'time_created': _msk_ts(2026, 9, 25, 18, 30), 'snippet': 'Коротко', 'full_text': 'Очень вкусно',
        'rating': 5, 'public_rating': True, 'business_answer_csrf_token': 'tok', 'init_chat_token': 'tok2',
        'photos': [{'link': 'https://img/1', 'width': 800, 'height': 600}],
    }
    raw.update(over)
    return raw


def _page(items, total, offset):
    return FakeResp(200, {'page': 1, 'currentState': {'filters': {'ranking': 'by_time'}},
                          'list': {'pager': {'limit': 2, 'offset': offset, 'total': total},
                                   'items': items, 'csrf_token': 'x'}})


# ----------------------------------------------------------------- разбор

def test_ts_to_msk_seconds_and_millis():
    ts = _msk_ts(2026, 9, 25, 18, 30)
    assert yb.ts_to_msk(ts) == '2026-09-25T18:30'
    assert yb.ts_to_msk(ts * 1000 + 999) == '2026-09-25T18:30'
    assert yb.ts_to_msk(ts + 59) == '2026-09-25T18:30'   # секунды отбрасываются
    for bad in (None, 0, -5, 'abc', True, 1.5):
        assert yb.ts_to_msk(bad) is None, bad


def test_parse_review_full():
    reply_ts = _msk_ts(2026, 9, 26, 10, 0)
    r = yb.parse_review(_review('abc', owner_comment={'time_created': reply_ts, 'text': ' Спасибо! '}))
    assert r['external_id'] == 'abc'
    assert r['rating'] == 5 and r['author'] == 'Иван И.' and r['author_privacy'] == 'NAME'
    assert r['text'] == 'Очень вкусно'
    assert r['created_at'] == '2026-09-25T18:30'
    assert r['owner_reply'] == {'text': 'Спасибо!', 'at': '2026-09-26T10:00'}
    assert r['photos'] == [{'link': 'https://img/1', 'width': 800, 'height': 600}]
    assert r['public_rating'] is True and r['problems'] == []
    assert 'tok' not in repr(r)   # служебные токены не переносятся


def test_parse_review_partial_and_bad_rating():
    r = yb.parse_review({'id': 'x', 'rating': 0, 'snippet': 'Только сниппет'})
    assert r['rating'] is None and r['text'] == 'Только сниппет'
    assert r['created_at'] is None and r['owner_reply'] is None and r['photos'] == []
    assert any('оценка вне' in p for p in r['problems'])
    assert any('нет даты' in p for p in r['problems'])
    empty = yb.parse_review(None)
    assert empty['external_id'] == '' and 'нет id' in empty['problems']
    # Пустой ответ организации — не ответ.
    assert yb.parse_review(_review('y', owner_comment={'text': '  ', 'time_created': 1}))['owner_reply'] is None


# ----------------------------------------------------------------- ошибки

def test_no_cookies():
    _raises(yb.YandexAuthError, lambda: yb.YandexBusinessClient('', SID2, http=FakeHttp([])))
    _raises(yb.YandexAuthError, lambda: yb.YandexBusinessClient(SID, '  ', http=FakeHttp([])))


def test_auth_redirect_and_401_no_retry():
    api, http, sleeps = _client([FakeResp(302, headers={'Location': 'https://passport.yandex.ru/auth?retpath=x'})])
    e = _raises(yb.YandexAuthError, lambda: api.reviews_page(1))
    assert len(http.calls) == 1 and sleeps == []
    assert SID not in str(e) and SID2 not in str(e)
    api, http, _ = _client([FakeResp(401)])
    _raises(yb.YandexAuthError, lambda: api.list_companies())
    assert len(http.calls) == 1


def test_captcha_no_retry():
    api, http, sleeps = _client([FakeResp(429, headers={'need-captcha': '1'})])
    _raises(yb.YandexCaptchaError, lambda: api.reviews_page(1))
    assert len(http.calls) == 1 and sleeps == []


def test_temporary_errors_retry_then_ok():
    api, http, sleeps = _client([FakeResp(503), requests.ConnectionError('boom ' + SID), _page([], 0, 0)])
    data = api.reviews_page(7)
    assert data['list']['items'] == []
    assert len(http.calls) == 3 and sleeps == [2, 6]
    assert http.calls[0] == ('https://yandex.ru/sprav/api/7/reviews', {'ranking_by': 'by_time', 'page': 1})


def test_temporary_errors_exhausted_message_scrubbed():
    api, http, sleeps = _client([FakeResp(502), FakeResp(502), requests.Timeout(SID2)])
    e = _raises(yb.YandexTemporaryError, lambda: api.reviews_page(7))
    assert len(http.calls) == 3 and sleeps == [2, 6]
    assert SID not in str(e) and SID2 not in str(e)
    assert 'после 3 попыток' in str(e)


def test_non_json_and_unexpected_status():
    api, _, _ = _client([FakeResp(200, data=None, text='<html>')])
    _raises(yb.YandexFormatError, lambda: api.reviews_page(1))
    api, _, _ = _client([FakeResp(404)])
    _raises(yb.YandexFormatError, lambda: api.reviews_page(1))


def test_cookies_set_on_session():
    api, http, _ = _client([])
    assert http.cookies.get('Session_id') == SID and http.cookies.get('sessionid2') == SID2


# ----------------------------------------------------------------- пагинация

def test_review_pages_stop_by_total():
    pages = {1: _page([_review('a'), _review('b')], 5, 0),
             2: _page([_review('c'), _review('d')], 5, 2),
             3: _page([_review('e')], 5, 4)}
    api, http, _ = _client(lambda url, params: pages[params['page']])
    got = [i['id'] for pg in api.iter_review_pages(1) for i in pg['items']]
    assert got == ['a', 'b', 'c', 'd', 'e']
    assert [c[1]['page'] for c in http.calls] == [1, 2, 3]   # четвёртой страницы не просили


def test_review_pages_stop_on_empty_and_limit():
    pages = {1: _page([_review('a')], None, None), 2: _page([], None, None)}
    api, http, _ = _client(lambda url, params: pages[params['page']])
    assert [pg['page'] for pg in api.iter_review_pages(1)] == [1]
    assert len(http.calls) == 2
    api, http, _ = _client(lambda url, params: _page([_review('p%d' % params['page'])], 100, None))
    assert len(list(api.iter_review_pages(1, max_pages=3))) == 3
    assert len(http.calls) == 3


def test_review_pages_repeated_page_is_error():
    # Сервер игнорирует page и отдаёт одно и то же: ошибка, а не бесконечный цикл.
    api, http, _ = _client(lambda url, params: _page([_review('a'), _review('b')], 50, None))
    it = api.iter_review_pages(1)
    next(it)
    _raises(yb.YandexFormatError, lambda: next(it))
    assert len(http.calls) == 2


def test_review_pages_bad_shape():
    api, _, _ = _client([FakeResp(200, {'list': {'pager': {}}})])
    _raises(yb.YandexFormatError, lambda: next(api.iter_review_pages(1)))


# ----------------------------------------------------------------- организации

def _company(pid, ctype='ordinal', name='Бар', **over):
    c = {'id': pid, 'permanent_id': pid, 'tycoon_id': 900, 'type': ctype, 'displayName': name,
         'publishing_status': 'publish', 'rating': 4.8, 'reviewsCount': 10,
         'address': {'geo_id': 2, 'formatted': {'value': 'Санкт-Петербург, ' + name, 'locale': 'ru'}}}
    c.update(over)
    return c


def test_branches_expand_chain_and_dedupe():
    def route(url, params):
        if url.endswith('/api/companies'):
            return FakeResp(200, {'limit': 20, 'page': 1, 'total': 2,
                                  'listCompanies': [_company(111, name='ВО'), _company(500, 'chain', 'Культура')]})
        assert url.endswith('/api/chain/900/branches/'), url
        assert params['chainPermalink'] == 500 and params['geoId'] == 2
        return FakeResp(200, {'companyList': {'pager': {'offset': 0, 'limit': 20, 'total': 2},
                                              'companies': [_company(111, name='ВО'), _company(222, name='Вар')]},
                              'companyIds': [111, 222]})
    api, http, _ = _client(route)
    branches = api.branches()
    assert sorted(b['permanent_id'] for b in branches) == [111, 222]
    by_id = {b['permanent_id']: b for b in branches}
    assert by_id[111]['via_chain'] == '' and by_id[222]['via_chain'] == 'Культура'
    assert by_id[222]['address'] == 'Санкт-Петербург, Вар' and by_id[222]['reviews_count'] == 10
    assert len(http.calls) == 2


def test_chain_without_ids_is_format_error():
    api, _, _ = _client([])
    _raises(yb.YandexFormatError, lambda: api.chain_branches({'name': 'Сеть', 'tycoon_id': None}))


# ----------------------------------------------------------------- скрипт

def _probe():
    import importlib.util
    spec = importlib.util.spec_from_file_location('yandex_reviews_probe',
                                                  os.path.join(ROOT, 'scripts', 'yandex_reviews_probe.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_probe_without_cookies_makes_no_requests():
    mod = _probe()
    mod._load_env = lambda: None   # не читать настоящий .env
    saved = {k: os.environ.pop(k, None) for k in (mod.ENV_SESSION_ID, mod.ENV_SESSION_ID2)}
    made = []
    orig = mod.YandexBusinessClient
    mod.YandexBusinessClient = lambda *a, **k: made.append(1)
    try:
        assert mod.main([]) == 2
        assert made == []
    finally:
        mod.YandexBusinessClient = orig
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_probe_strip_tokens():
    mod = _probe()
    data = {'list': {'items': [{'id': 'a', 'business_answer_csrf_token': 't', 'init_chat_token': 't',
                                'author': {'user': 'И'}}], 'csrf_token': 't',
                     'pager': {'continue_token': 't', 'total': 1}}}
    clean = mod._strip_tokens(data)
    assert clean == {'list': {'items': [{'id': 'a', 'author': {'user': 'И'}}], 'pager': {'total': 1}}}


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
