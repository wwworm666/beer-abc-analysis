"""Гифки к таплисту: набор владельца, выбор гифки на пост, ссылка на файл, кэш.

Решение владельца 2026-10-09: «к каждому таплисту прикрепляем рандомную гифку из списка».
Правила — core/taplist_gifs.py и docs/content-plan.md, «Гифка к таплисту». Отправка с
гифкой — tests/test_content_publisher.py (test_taplist_gif_*).
"""
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from core import taplist_gifs as tg


class Resp:
    def __init__(self, status=200, text='', headers=None):
        self.status_code, self.text, self.headers = status, text, headers or {}
        self.closed = False

    def close(self):
        self.closed = True


class FakeTenor:
    """Как requests.get: страницы и переадресации «страница.gif» по словарям."""

    def __init__(self, pages=None, redirects=None, error=None):
        self.pages, self.redirects, self.error = dict(pages or {}), dict(redirects or {}), error
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        if kwargs.get('allow_redirects') is False:
            location = self.redirects.get(url)
            return Resp(302 if location else 404, headers={'Location': location} if location else {})
        html = self.pages.get(url)
        return Resp(200 if html is not None else 404, html or '')


PAGE = 'https://tenor.com/view/beer-django-tap-beer-tap-django-beer-gif-13314412'
MP4 = 'https://media.tenor.com/Ry3Tx5V3o9QAAAPo/beer-django.mp4'
GIF = 'https://media1.tenor.com/m/Ry3Tx5V3o9QAAAAC/beer-django.gif'
HTML = (f'<html><head><meta property="og:image" content="{GIF}">'
        f'<meta content="{MP4}" property="og:video"></head></html>')


def _source(http_get, cache=None):
    path = cache or str(Path(tempfile.mkdtemp()) / 'taplist_gifs.json')
    return tg.GifSource(cache_file=path, http_get=http_get, now_fn=lambda: '2026-10-09T17:00')


# --------------------------------------------------------------------------- набор

def test_owner_gif_set():
    gifs = tg.load_gifs()
    assert len(gifs) == 25
    assert gifs[0]['title'] == 'Джанго освобождённый' and gifs[0]['page'] == PAGE
    assert gifs[-1]['title'] == 'Парки и зоны отдыха'
    assert len({g['page'] for g in gifs}) == 25 and all(g['note'] for g in gifs)
    assert all(tg.PAGE_RE.match(g['page']) for g in gifs)


@pytest.mark.parametrize('items', [
    [],
    [{'title': '', 'page': PAGE}],
    [{'title': 'Не Tenor', 'page': 'https://giphy.com/gifs/beer-123'}],
    [{'title': 'Раз', 'page': PAGE}, {'title': 'Два', 'page': PAGE}],
])
def test_broken_gif_set_rejected(items):
    path = Path(tempfile.mkdtemp()) / 'gifs.json'
    path.write_text(json.dumps({'gifs': items}, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ValueError):
        tg.load_gifs(path)


# --------------------------------------------------------------------------- выбор

def test_gif_rule_example_from_docs():
    # пятница 9 октября 2026 — неделя 39: (39 × 7 + сдвиг бара × 6) mod 25
    numbers = [tg.gif_for(date(2026, 10, 9), bar)['number'] for bar in tg.GIF_BARS]
    assert numbers == [24, 5, 11, 17]
    assert tg.gif_for(date(2026, 10, 9), 'bar2')['title'] == 'Побег из Шоушенка'


def test_gif_rule_distinct_bars_and_full_cycle():
    for offset in range(0, 730):
        day = tg.GIF_EPOCH + timedelta(days=offset)
        assert len({tg.gif_index(day, bar, 25) for bar in tg.GIF_BARS}) == 4, day
    for bar in tg.GIF_BARS:
        weeks = {tg.gif_index(date(2026, 10, 9) + timedelta(weeks=w), bar, 25) for w in range(25)}
        assert len(weeks) == 25, bar          # в своём баре повтор — через 25 недель
    # соседние недели не идут подряд по списку
    assert tg.gif_index(date(2026, 10, 16), 'bar1', 25) - tg.gif_index(date(2026, 10, 9), 'bar1', 25) != 1


def test_stride_coprime_with_set_size():
    assert (tg.stride(25), tg.stride(28), tg.stride(30), tg.stride(8), tg.stride(5)) == (7, 9, 7, 7, 1)


# --------------------------------------------------------------------------- ссылка на файл

def test_parse_media_url_prefers_mp4_and_only_tenor_media():
    assert tg.parse_media_url(HTML) == MP4
    assert tg.parse_media_url(f"<meta name='twitter:image' content='{GIF}'>") == GIF
    assert tg.parse_media_url(f'<meta property="og:image" content="{GIF}?a=1&amp;b=2">') is None
    assert tg.parse_media_url('<meta property="og:video" content="https://evil.example/x.mp4">') is None
    assert tg.parse_media_url('<meta property="og:image" content="https://media.tenor.com/x/a.png">') is None
    assert tg.parse_media_url('') is None


def test_source_resolves_once_and_caches():
    tenor = FakeTenor(pages={PAGE: HTML})
    source = _source(tenor)
    assert source.media_url(PAGE) == MP4
    assert source.media_url(PAGE) == MP4 and len(tenor.calls) == 1      # второй раз — из кэша
    stored = json.loads(Path(source.cache_file).read_text(encoding='utf-8'))
    assert stored['gifs'][PAGE] == {'media': MP4, 'media_at': '2026-10-09T17:00'}
    source.forget_media(PAGE)                                            # Telegram не скачал
    assert source.media_url(PAGE) == MP4 and len(tenor.calls) == 2


def test_source_redirect_fallback_and_failures():
    tenor = FakeTenor(redirects={PAGE + '.gif': GIF})                    # страница не отдалась
    assert _source(tenor).media_url(PAGE) == GIF
    assert tenor.calls[1][1]['allow_redirects'] is False
    assert _source(FakeTenor(redirects={PAGE + '.gif': 'https://evil.example/a.gif'})).media_url(PAGE) is None
    assert _source(FakeTenor(error=OSError('Tenor недоступен'))).media_url(PAGE) is None


def test_file_id_per_bot_and_broken_cache():
    source = _source(FakeTenor())
    source.remember_file_id(PAGE, 'token-a', 'CgACAgA')
    assert source.file_id(PAGE, 'token-a') == 'CgACAgA'
    assert source.file_id(PAGE, 'token-b') is None                       # file_id у бота свой
    source.forget_file_id(PAGE, 'token-a')
    assert source.file_id(PAGE, 'token-a') is None
    Path(source.cache_file).write_text('{битый', encoding='utf-8')
    assert source.file_id(PAGE, 'token-a') is None                       # кэш — не данные
    source.remember_file_id(PAGE, 'token-a', 'X')
    assert source.file_id(PAGE, 'token-a') == 'X'
