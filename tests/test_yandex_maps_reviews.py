"""
Тесты чтения отзывов с публичной страницы Яндекс Карт (core/yandex_maps_reviews.py).

Self-runnable: `py -3 tests/test_yandex_maps_reviews.py` (совместимо с pytest).

Сети нет: страницы — синтетические, в том виде, как Яндекс встраивает данные в
страницу (JSON: reviews с reviewId, params с count/page/totalPages). Что проверяется:
- разбор страницы: отзывы из любого места JSON, без повторов, без чужих
  организаций; число отзывов из params, иначе из микроразметки; капча; пустая
  разметка — ошибка; организация без отзывов — не ошибка;
- разбор отзыва: id, оценка, автор, текст, время ISO UTC -> Москва (с долями
  секунд и без), ответ организации; неполная запись не роняет разбор;
- листание: до count / totalPages / пустой страницы; чужой номер страницы и
  повтор — ошибка «не листают», полученное сохраняется; капча посреди листания;
  предел страниц; ссылка на страницу N.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from core import yandex_maps_reviews as mr  # noqa: E402

ORG = 31434555884


def review(i, org=ORG, when='2026-10-01T10:00:00.123Z', reply=None, rating=5, **over):
    r = {'reviewId': f'rv{i}', 'businessId': str(org), 'author': {'name': f'Гость {i}', 'avatarUrl': 'x/{size}'},
         'text': f'Отзыв {i}', 'rating': rating, 'updatedTime': when,
         'reactions': {'likes': 0, 'dislikes': 0}, 'photos': [], 'videos': []}
    if reply:
        r['businessComment'] = {'text': reply, 'updatedTime': '2026-10-02T09:00:00.5Z'}
    r.update(over)
    return r


def html(reviews, count=None, page=1, limit=50, total_pages=None, params=True, extra=''):
    """Страница как у Карт: компактный JSON в <script>, блок похожих мест рядом."""
    count = len(reviews) if count is None else count
    block = {'reviews': reviews}
    if params:
        block['params'] = {'offset': (page - 1) * limit, 'limit': limit, 'count': count,
                           'loadedReviewsCount': len(reviews), 'page': page,
                           'totalPages': total_pages if total_pages is not None else max(1, -(-count // limit)),
                           'reqId': '1', 'ranking': 'by_relevance_org'}
    state = {'config': {'params': {'lang': 'ru'}},
             'stack': [{'type': 'business', 'reviewResults': block,
                        'similar': {'reviews': [review('x', org=999)]}}]}
    return ('<html><head><title>Отзывы — Яндекс Карты</title></head><body>' + extra +
            '<script type="application/json" class="state-view">' +
            json.dumps(state, ensure_ascii=False, separators=(',', ':')) + '</script></body></html>')


# ----------------------------------------------------------------- страница

def test_parse_page_reviews_count_and_pages():
    parsed = mr.parse_reviews_page(html([review(1), review(2), review(1)], count=108, total_pages=3), ORG)
    assert [r['reviewId'] for r in parsed['reviews']] == ['rv1', 'rv2']     # повтор и похожее место — нет
    assert parsed['count'] == 108 and parsed['count_source'] == 'params'
    assert parsed['page'] == 1 and parsed['total_pages'] == 3 and parsed['limit'] == 50


def test_parse_page_without_org_filter_takes_all_and_ignores_records_without_id():
    page = html([review(1), {'text': 'без id'}])
    parsed = mr.parse_reviews_page(page)
    assert {r['reviewId'] for r in parsed['reviews']} == {'rv1', 'rvx'}


def test_count_from_microdata_when_params_missing():
    meta = '<div itemprop="aggregateRating"><meta itemprop="reviewCount" content="108"></div>'
    parsed = mr.parse_reviews_page(html([review(1)], params=False, extra=meta), ORG)
    assert parsed['count'] == 108 and parsed['count_source'] == 'microdata'
    parsed = mr.parse_reviews_page(html([review(1)], params=False), ORG)
    assert parsed['count'] is None and parsed['count_source'] is None and parsed['page'] is None


def test_captcha_and_missing_markup():
    with pytest.raises(mr.MapsCaptchaError):
        mr.parse_reviews_page('<html><form action="/checkcaptcha">Подтвердите, что запросы</form></html>')
    with pytest.raises(mr.MapsReviewsError, match='не найдены отзывы'):
        mr.parse_reviews_page('<html><script>{"state":{}}</script></html>')
    empty = mr.parse_reviews_page(html([], count=0), ORG)        # у организации нет отзывов — не ошибка
    assert empty['reviews'] == [] and empty['count'] == 0
    # Страница за концом списка (2 и дальше) пустая — не ошибка, а конец листания.
    beyond = mr.parse_reviews_page('<html><script>{"state":{}}</script></html>', ORG, allow_empty=True)
    assert beyond['reviews'] == [] and beyond['count'] is None


def test_reviews_url():
    assert mr.reviews_url(ORG) == 'https://yandex.ru/maps/org/31434555884/reviews/'
    assert mr.reviews_url(ORG, 3) == 'https://yandex.ru/maps/org/31434555884/reviews/?page=3'


# ----------------------------------------------------------------- отзыв

def test_parse_review_fields_and_moscow_time():
    item = mr.parse_review(review(7, when='2026-10-01T21:30:59.9Z', reply='Спасибо!'))
    assert item == {'external_id': 'rv7', 'rating': 5, 'author': 'Гость 7', 'text': 'Отзыв 7',
                    'created_at': '2026-10-02T00:30', 'owner_reply': {'text': 'Спасибо!', 'at': '2026-10-02T12:00'},
                    'problems': []}
    # Фото, аватар и public_rating страница не даёт — ключей нет, загрузка оставит прежние.
    assert not {'photos', 'author_avatar', 'public_rating'} & set(item)


def test_iso_time_variants():
    assert mr.iso_to_msk('2026-10-01T10:00:00Z') == '2026-10-01T13:00'
    assert mr.iso_to_msk('2026-10-01T10:00:00.1234567+00:00') == '2026-10-01T13:00'
    assert mr.iso_to_msk('2026-10-01T10:00:00') == '2026-10-01T13:00'       # без пояса — UTC
    assert mr.iso_to_msk('2026-10-01T13:00:00+03:00') == '2026-10-01T13:00'
    assert mr.iso_to_msk(1790000000) == mr.iso_to_msk('1790000000')
    assert mr.iso_to_msk('вчера') is None and mr.iso_to_msk(None) is None and mr.iso_to_msk('') is None


def test_parse_review_incomplete_does_not_raise():
    item = mr.parse_review({'reviewId': 'z', 'rating': 7, 'businessComment': {'text': '  '}})
    assert item['external_id'] == 'z' and item['rating'] is None and item['owner_reply'] is None
    assert item['author'] == '' and item['text'] == '' and item['created_at'] is None
    assert any('1..5' in p for p in item['problems']) and any('даты' in p for p in item['problems'])
    item = mr.parse_review({'reviewId': 'y', 'rating': 4.0, 'updatedTime': '2026-10-01T10:00:00Z',
                            'businessComment': {'text': 'Ок'}})
    assert item['rating'] == 4 and item['owner_reply'] == {'text': 'Ок', 'at': None}
    assert item['problems'] == ['у ответа организации нет даты']
    assert mr.parse_review(None)['problems'][0] == 'нет id'


# ----------------------------------------------------------------- листание

class Site:
    """Карты в памяти: reviews — все отзывы организации, по limit на страницу."""

    def __init__(self, reviews, limit=50, count=None, broken=None, captcha_on=None):
        self.reviews, self.limit = reviews, limit
        self.count = len(reviews) if count is None else count
        self.broken, self.captcha_on = broken, captcha_on
        self.asked = []

    def fetch(self, org, page):
        self.asked.append(page)
        if page == self.captcha_on:
            raise mr.MapsCaptchaError('капча')
        shown = 1 if self.broken == 'ignore_page' else page
        chunk = self.reviews[(shown - 1) * self.limit:shown * self.limit]
        return mr.parse_reviews_page(html(chunk, count=self.count, page=shown, limit=self.limit), org)


def _walk(site, **kw):
    return mr.collect_pages(ORG, site.fetch(ORG, 1), fetch=site.fetch, sleep=lambda s: None, **kw)


def test_collect_all_pages_until_count():
    site = Site([review(i) for i in range(108)])
    got = _walk(site)
    assert got['error'] is None and not got['captcha'] and got['pages'] == 3
    assert len(got['reviews']) == 108 and site.asked == [1, 2, 3]


def test_collect_single_page_makes_no_extra_requests():
    site = Site([review(i) for i in range(50)])
    got = _walk(site)
    assert got['pages'] == 1 and site.asked == [1] and got['error'] is None


def test_pagination_ignored_is_an_error_and_keeps_first_page():
    site = Site([review(i) for i in range(108)], broken='ignore_page')
    got = _walk(site)
    assert 'не листают' in got['error'] and len(got['reviews']) == 50 and site.asked == [1, 2]


def test_repeated_page_without_page_number_is_an_error():
    first = mr.parse_reviews_page(html([review(i) for i in range(50)], count=108), ORG)

    def fetch(org, page):
        return {'reviews': first['reviews'], 'count': 108, 'page': None, 'total_pages': None}
    got = mr.collect_pages(ORG, first, fetch=fetch, sleep=lambda s: None)
    assert 'повторила' in got['error'] and len(got['reviews']) == 50


def test_captcha_in_the_middle_keeps_what_was_read():
    site = Site([review(i) for i in range(120)], captcha_on=3)
    got = _walk(site)
    assert got['captcha'] and got['error'] == 'капча' and len(got['reviews']) == 100 and got['pages'] == 2


def test_unknown_count_stops_on_empty_page_and_page_limit():
    def fetch(org, page):
        chunk = [review(f'{page}-{i}') for i in range(2)] if page <= 3 else []
        return {'reviews': chunk, 'count': None, 'page': None, 'total_pages': None}
    got = mr.collect_pages(ORG, fetch(ORG, 1), fetch=fetch, sleep=lambda s: None)
    assert got['error'] is None and got['pages'] == 3 and len(got['reviews']) == 6
    site = Site([review(i) for i in range(500)])
    got = _walk(site, max_pages=4)
    assert 'предел 4 страниц' in got['error'] and len(got['reviews']) == 200


def test_fetch_page_status_and_network_errors():
    class Resp:
        def __init__(self, code, text=''):
            self.status_code, self.text = code, text
    assert mr.fetch_page(ORG, 2, get=lambda url, **kw: Resp(200, html([review(1)])))['reviews'][0]['reviewId'] == 'rv1'
    with pytest.raises(mr.MapsReviewsError, match='кодом 503'):
        mr.fetch_page(ORG, get=lambda url, **kw: Resp(503))

    def down(url, **kw):
        raise ConnectionError('нет сети')
    with pytest.raises(mr.MapsReviewsError, match='не ответили'):
        mr.fetch_page(ORG, get=down)
    blank = '<html><script>{"state":{}}</script></html>'
    assert mr.fetch_page(ORG, 3, get=lambda url, **kw: Resp(200, blank))['reviews'] == []
    with pytest.raises(mr.MapsReviewsError, match='не найдены отзывы'):
        mr.fetch_page(ORG, 1, get=lambda url, **kw: Resp(200, blank))
    seen = {}

    def spy(url, **kw):
        seen.update(url=url, **kw)
        return Resp(200, html([review(1)]))
    mr.fetch_page(ORG, 2, get=spy)
    assert seen['url'].endswith('/reviews/?page=2') and 'Chrome' in seen['headers']['User-Agent']


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
