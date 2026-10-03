"""
Поддельный Яндекс и поддельные сайты для тестов поиска картинок
(core/content_image_search.py). Сеть тесты не трогают: Yandex Search API — платный,
а сайты из выдачи — чужие.

- jpeg_bytes / png_bytes — настоящие картинки нужного размера (Pillow);
- yandex_xml(docs) — XML ответа Яндекса того вида, что разбирает parse_response_xml
  (тот же, что читает официальный SDK yandex-ai-studio-sdk: response -> group -> doc,
  url, domain, title, image-properties/original-width|original-height|mime-type|html-link);
- FakeYandexSession — вместо requests.Session у YandexImageClient: отвечает JSON
  {rawData: base64(XML)} или ошибкой, запоминает запросы;
- FakeWeb — вместо fetch_image: отдаёт байты по адресу, неизвестный адрес —
  ImageDownloadFailed, запоминает вызовы;
- make_finder — ImageFinder с поддельным Яндексом, поддельными сайтами и хранилищем
  поисков во временной папке.
"""
import base64
import io
import os
import tempfile
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

from core import content_image_search as cis

MSK = timezone(timedelta(hours=3))
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=MSK)


def jpeg_bytes(width, height, color=(180, 90, 30), quality=85, exif_orientation=None):
    from PIL import Image
    image = Image.new('RGB', (width, height), color)
    out = io.BytesIO()
    kwargs = {'quality': quality}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs['exif'] = exif.tobytes()
    image.save(out, 'JPEG', **kwargs)
    return out.getvalue()


def png_bytes(width, height, rgba=(200, 30, 30, 0)):
    from PIL import Image
    image = Image.new('RGBA', (width, height), rgba)
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()


def doc(n, width=1600, height=1200, domain=None, url=None, page=None, title=None, mime='jpg',
        thumb=None, image_id=None):
    """Описание одной картинки выдачи для yandex_xml."""
    domain = domain or f'site{n}.example'
    return {'url': url or f'https://{domain}/img/{n}.jpg', 'domain': domain,
            'page': page if page is not None else f'https://{domain}/page/{n}.html',
            'title': title if title is not None else f'Картинка <hlword>{n}</hlword>',
            'width': width, 'height': height, 'mime': mime, 'thumb': thumb, 'image_id': image_id}


def yandex_xml(docs=(), error_code=None, error_text='Ошибка'):
    parts = ['<?xml version="1.0" encoding="utf-8"?><yandexsearch version="1.0"><request/><response>']
    if error_code is not None:
        parts.append(f'<error code="{error_code}">{escape(error_text)}</error>')
    else:
        parts.append('<results><grouping>')
        for item in docs:
            props = []
            if item.get('image_id'):
                props.append(f'<id>{escape(item["image_id"])}</id><shard>1</shard>')
            if item.get('thumb'):
                props.append(f'<thumbnail-link>{escape(item["thumb"])}</thumbnail-link>')
            if item.get('width'):
                props.append(f'<original-width>{item["width"]}</original-width>')
            if item.get('height'):
                props.append(f'<original-height>{item["height"]}</original-height>')
            if item.get('page'):
                props.append(f'<html-link>{escape(item["page"])}</html-link>')
            props.append(f'<mime-type>{escape(item.get("mime") or "")}</mime-type>')
            # title — с подсветкой Яндекса <hlword>; в XML она приходит разметкой
            parts.append('<group><doccount>1</doccount><doc>'
                         f'<url>{escape(item["url"])}</url><domain>{escape(item["domain"])}</domain>'
                         f'<title>{item["title"]}</title>'
                         f'<image-properties>{"".join(props)}</image-properties></doc></group>')
        parts.append('</grouping></results>')
    parts.append('</response></yandexsearch>')
    return ''.join(parts).encode('utf-8')


class _Response:
    def __init__(self, status, payload=None, text=''):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError('не JSON')
        return self._payload


class FakeYandexSession:
    """requests.Session для YandexImageClient: post -> ответ из очереди (или один на все)."""

    def __init__(self, xml=None, status=200, payload=None, raise_exc=None):
        self.xml = xml if xml is not None else yandex_xml([])
        self.status = status
        self.payload = payload
        self.raise_exc = raise_exc
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({'url': url, 'json': json, 'headers': headers, 'timeout': timeout})
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.status != 200:
            return _Response(self.status, self.payload, text='ошибка')
        return _Response(200, {'rawData': base64.b64encode(self.xml).decode('ascii')})


class FakeClock:
    """Монотонные часы для бюджета коллажа: tick секунд на каждое скачивание FakeWeb."""

    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now


class FakeWeb:
    """fetch(url, referer, max_bytes, deadline_s) -> bytes по словарю pages; иначе
    ImageDownloadFailed. clock и tick — «долгий сайт»: каждое скачивание двигает часы."""

    def __init__(self, pages=None, clock=None, tick=0.0):
        self.pages = dict(pages or {})
        self.calls = []
        self.clock = clock
        self.tick = tick

    def __call__(self, url, referer=None, max_bytes=None, deadline_s=None):
        self.calls.append((url, referer, max_bytes))
        if self.clock is not None:
            self.clock.now += self.tick
        if url not in self.pages:
            raise cis.ImageDownloadFailed('Сайт не отдал картинку: HTTP 404')
        data = self.pages[url]
        if isinstance(data, Exception):
            raise data
        return data


def make_finder(docs=(), pages=None, tmp=None, now=NOW, configured=True, daily_limit=cis.DAILY_LIMIT,
                caller_limit=cis.PER_CALLER_DAILY_LIMIT, session=None, tick=0.0):
    """ImageFinder с поддельным Яндексом (docs) и сайтами (pages); -> (finder, session, web, tmp).
    Часы коллажа — FakeClock (finder.clock), tick — сколько секунд «длится» одно скачивание."""
    tmp = tmp or tempfile.mkdtemp(prefix='image_search_test_')
    session = session or FakeYandexSession(yandex_xml(list(docs)))
    client = cis.YandexImageClient('test-key', 'b1gtestfolder', session=session) if configured else None
    store = cis.SearchStore(os.path.join(tmp, 'content_image_search'), now_fn=lambda: now)
    clock = FakeClock()
    web = FakeWeb(pages, clock=clock, tick=tick)
    finder = cis.ImageFinder(client, store, fetch=web, daily_limit=daily_limit, caller_limit=caller_limit,
                             clock=clock)
    return finder, session, web, tmp
