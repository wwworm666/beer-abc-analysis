"""
Тесты поиска картинок к постам (core/content_image_search.py) и его маршрутов
(routes/content_plan.py: /api/content-plan/image-search*, .../media/found).

Self-runnable: `py -3 tests/test_content_image_search.py` (совместимо с pytest).

Сеть не трогается: Яндекс и сайты поддельные (tests/image_search_fakes.py), разрешение
имён — подставной resolver, соединение — подставной opener.

Что проверяется:
- разбор ответа Яндекса: картинка, домен, заголовок без подсветки, размеры, формат,
  страница, миниатюры; ошибка 15 — пустой список, другая — ImageSearchFailed;
- отбор: повторы, стоки (и их поддомены), мелкие; неизвестный размер остаётся; не больше 12;
- проверка ввода: запрос, ориентация, сайт, страница, вариант;
- запрос в Яндекс: тело (тип поиска, без фильтра размера, ориентация, каталог, сайт) и
  ключ в заголовке; HTTP-ошибка, обрыв, не-объект и rawData не строкой — ImageSearchFailed;
- хранилище поисков: id, запись и чтение, неизвестный и кривой id, счёт за сутки с
  разбивкой по подключению, уборка старых поисков и брошенных временных файлов;
- поиск целиком: не настроен, бронь места в суточном пределе (сеть и подключение),
  неудачный поиск не считается, ответ без служебных полей;
- коллаж: JPEG в пределе, размер сетки, порядок превью, «no preview», бюджет времени,
  кэш только целого коллажа;
- скачивание (регрессии независимой проверки 2026-10-02): адрес разбирается один раз,
  «\\», «@», нелатинский домен — отказ ДО разрешения имени; соединение — на проверенный IP
  с Host и именем для TLS; внутренние адреса и переадресация туда; общий срок; предел
  байт; без распаковки;
- подготовка: уменьшение, прозрачность на белый, EXIF, мелкая, вытянутая, не картинка,
  «бомба» (маленький PNG огромного размера) — отказ до распаковки;
- маршруты: поиск — POST и только администратор, 503/502/429/404/400, прикрепление с
  источником, режим черновиков (чужой материал — 409 до скачивания).
"""

import io
import json
import os
import shutil
import socket
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

import requests  # noqa: E402
from flask import Flask  # noqa: E402

import core.content_image_search as cis  # noqa: E402
import core.content_plan as cp  # noqa: E402
import core.content_publisher as cpub  # noqa: E402
import routes.content_plan as rcp  # noqa: E402
from image_search_fakes import (NOW, FakeYandexSession, doc, jpeg_bytes, make_finder, png_bytes,  # noqa: E402
                                yandex_xml)

ADMIN = {'login': 'anna', 'display_name': 'Анна', 'is_admin': True}
BARTENDER = {'login': 'bob', 'display_name': 'Боб', 'is_admin': False}
AGENT_DRAFT_MODE = dict(ADMIN, via_mcp=True, mcp_client='Claude', mcp_token_id='t1', mcp_mode='draft')
AGENT_FULL = dict(ADMIN, via_mcp=True, mcp_client='Claude', mcp_token_id='t1', mcp_mode='full')


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type as e:
        return e
    raise AssertionError(f'ожидалось {exc_type.__name__}')


# --------------------------------------------------------------------------- разбор ответа

def test_parse_response_xml_fields():
    xml = yandex_xml([doc(1, width=1920, height=1080, thumb='https://thumbs.example/1.jpg', image_id='abc123XYZ-l'),
                      doc(2, width=None, height=None, page='', mime='')])
    docs = cis.parse_response_xml(xml)
    assert len(docs) == 2
    first = docs[0]
    assert first['image_url'] == 'https://site1.example/img/1.jpg'
    assert first['domain'] == 'site1.example'
    assert first['title'] == 'Картинка 1'                       # подсветка <hlword> снята
    assert (first['width'], first['height'], first['format']) == (1920, 1080, 'jpg')
    assert first['page_url'] == 'https://site1.example/page/1.html'
    assert first['thumb_urls'] == ['https://thumbs.example/1.jpg']
    assert first['guessed_thumb_urls'][0].startswith('https://avatars.mds.yandex.net/i?id=abc123XYZ-l')
    second = docs[1]
    assert second['width'] is None and second['height'] is None and second['page_url'] == ''
    assert second['thumb_urls'] == [] and second['guessed_thumb_urls'] == []


def test_parse_response_errors():
    assert cis.parse_response_xml(yandex_xml(error_code=15, error_text='Ничего не нашлось')) == []
    err = _raises(cis.ImageSearchFailed, cis.parse_response_xml, yandex_xml(error_code=32, error_text='Лимит'))
    assert '32' in str(err) and 'Лимит' in str(err)
    _raises(cis.ImageSearchFailed, cis.parse_response_xml, b'<not xml')


def test_parse_skips_doc_without_http_url():
    xml = yandex_xml([doc(1, url='javascript:alert(1)'), doc(2)])
    docs = cis.parse_response_xml(xml)
    assert [d['image_url'] for d in docs] == ['https://site2.example/img/2.jpg']


# --------------------------------------------------------------------------- отбор

def test_pick_candidates_drops_duplicates_stock_small():
    docs = cis.parse_response_xml(yandex_xml([
        doc(1),
        doc(1),                                                          # повтор адреса
        doc(2, domain='www.shutterstock.com'),                           # сток
        doc(3, url='https://st2.depositphotos.com/1/3.jpg'),             # поддомен стока в адресе
        doc(4, width=900, height=600),                                   # мелкая
        doc(5, width=None, height=None),                                 # размер неизвестен — оставить
        doc(6, width=600, height=1400),                                  # вертикальная, большая сторона 1400
    ]))
    picked, dropped = cis.pick_candidates(docs)
    assert [d['image_url'].rsplit('/', 1)[-1] for d in picked] == ['1.jpg', '5.jpg', '6.jpg']
    assert dropped == {'duplicate': 1, 'stock': 2, 'small': 1}


def test_pick_candidates_limit():
    docs = cis.parse_response_xml(yandex_xml([doc(n) for n in range(1, 31)]))
    picked, dropped = cis.pick_candidates(docs)
    assert len(picked) == cis.CANDIDATES_MAX == 12
    assert dropped == {'duplicate': 0, 'stock': 0, 'small': 0}


def test_is_stock():
    assert cis.is_stock('img.alamy.com') and cis.is_stock('t3.ftcdn.net') and cis.is_stock('www.lori.ru')
    assert not cis.is_stock('rodenbach.be') and not cis.is_stock('notalamy.com') and not cis.is_stock('')


# --------------------------------------------------------------------------- проверка ввода

def test_clean_inputs():
    assert cis.clean_query('  Rodenbach   foeders ') == 'Rodenbach foeders'
    _raises(ValueError, cis.clean_query, 'a')
    _raises(ValueError, cis.clean_query, 'x' * 401)
    assert cis.clean_orientation(None) is None and cis.clean_orientation('Vertical') == 'vertical'
    _raises(ValueError, cis.clean_orientation, 'diagonal')
    assert cis.clean_site('www.Rodenbach.be') == 'rodenbach.be'
    assert cis.clean_site('') is None
    for bad in ('http://rodenbach.be', 'rodenbach.be/en', 'localhost', 'a b.com'):
        _raises(ValueError, cis.clean_site, bad)
    assert cis.clean_page(None) == 0 and cis.clean_page('3') == 3 and cis.clean_page(2) == 2
    for bad in ('10', 'x', True):
        _raises(ValueError, cis.clean_page, bad)
    assert cis.parse_candidate('is_20261002_3f9a1c2b7d4e-3') == ('is_20261002_3f9a1c2b7d4e', 3)
    assert cis.parse_candidate(' is_20261002_3f9a1c2b7d4e-3\n') == ('is_20261002_3f9a1c2b7d4e', 3)  # пробелы по краям
    for bad in ('is_20261002_3f9a1c2b7d4e', 'https://evil.example/x.jpg', 'is_20261002_3F9A1C2B7D4E-3',
                'is_20261002_3f9a1c2b7d4e-3x', '../is_20261002_3f9a1c2b7d4e-3', 'is_20261002_3f9a1c2b7d4e-123'):
        _raises(ValueError, cis.parse_candidate, bad)


# --------------------------------------------------------------------------- запрос в Яндекс

def test_client_request_body_and_auth():
    session = FakeYandexSession(yandex_xml([doc(1)]))
    client = cis.YandexImageClient('KEY', 'b1gfolder', session=session)
    docs = client.search('Rodenbach foeders', orientation='vertical', site='rodenbach.be', page=2)
    assert len(docs) == 1
    call = session.calls[0]
    assert call['url'] == cis.SEARCH_URL == 'https://searchapi.api.cloud.yandex.net/v2/image/search'
    assert call['headers'] == {'Authorization': 'Api-Key KEY'}
    body = call['json']
    assert body['query'] == {'searchType': 'SEARCH_TYPE_RU', 'queryText': 'Rodenbach foeders', 'page': '2'}
    # размер Яндекса не задаём: LARGE — это 800x600..1600x1200, самые большие туда не входят
    assert body['imageSpec'] == {'orientation': 'IMAGE_ORIENTATION_VERTICAL'}
    assert body['docsOnPage'] == '60' and body['folderId'] == 'b1gfolder' and body['site'] == 'rodenbach.be'
    plain = client.body('пиво', None, None, 0)
    assert 'site' not in plain and 'imageSpec' not in plain


def test_client_errors():
    bad = cis.YandexImageClient('KEY', 'F', session=FakeYandexSession(status=403,
                                                                      payload={'message': 'Permission denied'}))
    err = _raises(cis.ImageSearchFailed, bad.search, 'пиво')
    assert '403' in str(err) and 'Permission denied' in str(err)
    listy = cis.YandexImageClient('KEY', 'F', session=FakeYandexSession(status=500, payload=['не объект']))
    assert '500' in str(_raises(cis.ImageSearchFailed, listy.search, 'пиво'))
    down = cis.YandexImageClient('KEY', 'F', session=FakeYandexSession(raise_exc=requests.ConnectionError('x')))
    assert 'не ответил' in str(_raises(cis.ImageSearchFailed, down.search, 'пиво'))

    class _Odd(FakeYandexSession):
        def __init__(self, payload):
            super().__init__()
            self.odd = payload

        def post(self, url, json=None, headers=None, timeout=None):
            from image_search_fakes import _Response
            return _Response(200, self.odd)

    for payload in ({'rawData': 123}, {'rawData': ''}, ['x'], {'other': 1}, {'rawData': '!!!не base64!!!'}):
        client = cis.YandexImageClient('KEY', 'F', session=_Odd(payload))
        _raises(cis.ImageSearchFailed, client.search, 'пиво')


# --------------------------------------------------------------------------- хранилище поисков

def test_search_store_roundtrip_count_cleanup():
    tmp = tempfile.mkdtemp(prefix='image_store_test_')
    try:
        moments = {'now': NOW}
        store = cis.SearchStore(os.path.join(tmp, 's'), now_fn=lambda: moments['now'])
        search_id = store.new_id()
        assert cis.SEARCH_ID_RE.match(search_id) and search_id.startswith('is_20261007_')
        store.save(search_id, {'search_id': search_id, 'caller': 't1', 'candidates': [{'n': 1}]})
        other = store.new_id()
        store.save(other, {'search_id': other, 'caller': 't2', 'candidates': []})
        assert store.load(search_id)['candidates'] == [{'n': 1}]
        assert store.count_today('t1') == (2, 1) and store.count_today(None) == (2, 0)
        _raises(cis.ImageSearchNotFound, store.load, 'is_20261007_000000000000')
        _raises(cis.ImageSearchNotFound, store.load, '../../etc/passwd')
        _raises(cis.ImageSearchNotFound, store.collage_path, 'is_1/../x')
        # кэш коллажа: только целый JPEG
        assert store.read_collage(search_id) is None
        store.write_collage(search_id, b'\xff\xd8\xff' + b'x' * 10)
        assert store.read_collage(search_id).startswith(b'\xff\xd8\xff')
        with open(store.collage_path(other), 'wb') as f:
            f.write(b'')                                         # пустой файл — не кэш
        assert store.read_collage(other) is None
        # старый поиск (4 суток назад) и брошенный временный файл уходят при уборке
        old_id = 'is_20261003_aaaaaaaaaaaa'
        store.save(old_id, {'candidates': []})
        with open(store.collage_path(old_id), 'wb') as f:
            f.write(b'x')
        stale_tmp = os.path.join(store.directory, search_id + '.abc.tmp')
        fresh_tmp = os.path.join(store.directory, other + '.def.tmp')
        for path in (stale_tmp, fresh_tmp):
            with open(path, 'wb') as f:
                f.write(b'x')
        os.utime(stale_tmp, (1, 1))
        assert store.cleanup() == 3
        assert not os.path.exists(stale_tmp) and os.path.exists(fresh_tmp)
        assert not os.path.exists(store.collage_path(old_id))
        moments['now'] = NOW + timedelta(days=1)
        assert store.count_today('t1') == (0, 0)
        store.delete(search_id)
        _raises(cis.ImageSearchNotFound, store.load, search_id)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- поиск целиком

def test_finder_search_payload():
    finder, session, _web, tmp = make_finder([doc(1, thumb='https://thumbs.example/1.jpg'), doc(2),
                                              doc(3, width=500, height=400)])
    try:
        result = finder.search('Rodenbach foeders', orientation='horizontal', caller='t1')
        assert result['query'] == 'Rodenbach foeders' and result['orientation'] == 'horizontal'
        assert result['found'] == 3 and result['dropped'] == {'duplicate': 0, 'stock': 0, 'small': 1}
        assert result['searches_today'] == 1 and result['daily_limit'] == cis.DAILY_LIMIT
        search_id = result['search_id']
        assert result['collage'] == '/api/content-plan/image-search/' + search_id + '/collage'
        assert [c['candidate'] for c in result['candidates']] == [search_id + '-1', search_id + '-2']
        assert all('thumb_urls' not in c for c in result['candidates'])     # служебное не отдаём
        assert 'caller' not in result
        record = finder.store.load(search_id)
        assert record['candidates'][0]['thumb_urls'] == ['https://thumbs.example/1.jpg']
        assert record['status'] == 'done' and record['caller'] == 't1'
        assert session.calls[0]['json']['imageSpec']['orientation'] == 'IMAGE_ORIENTATION_HORIZONTAL'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_finder_not_configured():
    finder, _session, _web, tmp = make_finder([doc(1)], configured=False)
    try:
        err = _raises(cis.ImageSearchNotConfigured, finder.search, 'пиво')
        assert cis.ENV_API_KEY in str(err)
        _raises(ValueError, finder.search, 'x')                 # ввод проверяется раньше настройки
        assert finder.store.count_today() == (0, 0)             # ни брони, ни файла
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_finder_daily_limits_reserve_and_release():
    finder, session, _web, tmp = make_finder([doc(1)], daily_limit=3, caller_limit=2)
    try:
        finder.search('пиво раз', caller='t1')
        finder.search('пиво два', caller='t1')
        err = _raises(cis.ImageSearchLimit, finder.search, 'пиво три', caller='t1')
        assert 'предел 2' in str(err) and 'подключение' in str(err)
        assert len(session.calls) == 2                          # третий в Яндекс не ушёл
        assert finder.store.count_today('t1') == (2, 2)         # отказанная бронь снята
        finder.search('пиво', caller='t2')                      # другое подключение — можно
        err = _raises(cis.ImageSearchLimit, finder.search, 'пиво ещё', caller='t3')
        assert 'предел 3' in str(err) and 'всю сеть' in str(err)
        # неудачный поиск (Яндекс упал) не считается
        finder.daily_limit = 10
        finder.client.session = FakeYandexSession(status=500, payload={'message': 'boom'})
        _raises(cis.ImageSearchFailed, finder.search, 'пиво', caller='t4')
        assert finder.store.count_today('t4') == (3, 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_get_finder_reads_env():
    saved = {k: os.environ.get(k) for k in (cis.ENV_API_KEY, cis.ENV_FOLDER_ID)}
    try:
        os.environ[cis.ENV_API_KEY] = ''
        os.environ[cis.ENV_FOLDER_ID] = 'b1g'
        assert not cis.is_configured()
        os.environ[cis.ENV_API_KEY] = 'k'
        assert cis.is_configured()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# --------------------------------------------------------------------------- коллаж

def test_collage_previews_order_and_cache():
    docs = [doc(1, thumb='https://thumbs.example/1.jpg'), doc(2), doc(3, image_id='zzz999yyy'), doc(4)]
    pages = {
        'https://thumbs.example/1.jpg': jpeg_bytes(300, 200, (10, 200, 10)),     # миниатюра из ответа
        'https://site2.example/img/2.jpg': jpeg_bytes(1600, 1200, (10, 10, 200)),  # оригинал
        # у третьей оригинала нет — берётся миниатюра по id
        'https://avatars.mds.yandex.net/i?id=zzz999yyy&n=13': jpeg_bytes(320, 240, (200, 10, 10)),
        'https://site4.example/img/4.jpg': jpeg_bytes(1, 1),                        # пиксель — не превью
    }
    finder, _session, web, tmp = make_finder(docs, pages)
    try:
        search_id = finder.search('пиво')['search_id']
        data = finder.collage(search_id)
        from PIL import Image
        sheet = Image.open(io.BytesIO(data))
        assert sheet.format == 'JPEG' and len(data) <= cis.COLLAGE_MAX_BYTES
        assert sheet.size == (4 * 310, 1 * (300 + 34 + 10))
        fetched = [url for url, _ref, _max in web.calls]
        assert 'https://site1.example/img/1.jpg' not in fetched           # миниатюра нашлась — оригинал не нужен
        assert fetched.index('https://site3.example/img/3.jpg') < \
            fetched.index('https://avatars.mds.yandex.net/i?id=zzz999yyy&n=13')   # угаданная — последней
        assert ('https://site2.example/img/2.jpg', 'https://site2.example/page/2.html',
                cis.PREVIEW_MAX_BYTES) in web.calls                           # Referer — страница
        # ячейка 1 зелёная, 2 синяя, 3 красная, 4 серая («no preview»)
        def center(index):
            return sheet.getpixel((index * 310 + 5 + 150, 5 + 34 + 150))
        assert center(0)[1] > 150 and center(1)[2] > 150 and center(2)[0] > 150
        assert abs(center(3)[0] - 190) < 20 and abs(center(3)[2] - 190) < 20
        # одна ячейка серая — коллаж НЕ кэшируется: временный сбой сайта не держится 3 суток
        assert finder.store.read_collage(search_id) is None
        calls = len(web.calls)
        finder.collage(search_id)
        assert len(web.calls) > calls
        _raises(cis.ImageSearchNotFound, finder.collage, 'is_20261007_000000000000')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_collage_cached_when_complete():
    docs = [doc(1), doc(2)]
    pages = {'https://site1.example/img/1.jpg': jpeg_bytes(1200, 900),
             'https://site2.example/img/2.jpg': jpeg_bytes(1200, 900)}
    finder, _session, web, tmp = make_finder(docs, pages)
    try:
        search_id = finder.search('пиво')['search_id']
        data = finder.collage(search_id)
        assert finder.store.read_collage(search_id) == data
        calls = len(web.calls)
        assert finder.collage(search_id) == data and len(web.calls) == calls       # из кэша
        leftovers = [n for n in os.listdir(finder.store.directory) if n.endswith('.tmp')]
        assert leftovers == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_collage_budget():
    """Сайты «долгие» (каждое скачивание — 10 с по часам коллажа): после бюджета 25 с превью
    больше не качаются, ячейки — «no preview», коллаж всё равно отдаётся и не кэшируется."""
    docs = [doc(n) for n in range(1, 13)]
    pages = {f'https://site{n}.example/img/{n}.jpg': jpeg_bytes(1200, 900) for n in range(1, 13)}
    finder, _session, web, tmp = make_finder(docs, pages, tick=10.0)
    try:
        search_id = finder.search('пиво')['search_id']
        workers, cis.PREVIEW_WORKERS = cis.PREVIEW_WORKERS, 1      # по очереди — часы предсказуемы
        try:
            data = finder.collage(search_id)
        finally:
            cis.PREVIEW_WORKERS = workers
        assert data[:3] == b'\xff\xd8\xff'
        assert len(web.calls) <= 3                                # 25 с бюджета / 10 с на скачивание
        assert finder.store.read_collage(search_id) is None       # неполный — не в кэш
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_collage_twelve_cells_fits_inline_limit():
    import random
    rnd = random.Random(7)
    docs = [doc(n) for n in range(1, 13)]
    from PIL import Image
    pages = {}
    for n in range(1, 13):
        noise = Image.effect_noise((1200, 900), 90).convert('RGB')     # шум — худший случай для JPEG
        noise = Image.blend(noise, Image.new('RGB', noise.size, (rnd.randint(0, 255), 80, 80)), 0.3)
        out = io.BytesIO()
        noise.save(out, 'JPEG', quality=95)
        pages[f'https://site{n}.example/img/{n}.jpg'] = out.getvalue()
    finder, _session, _web, tmp = make_finder(docs, pages)
    try:
        data = finder.collage(finder.search('пиво')['search_id'])
        sheet = Image.open(io.BytesIO(data))
        assert sheet.size == (4 * 310, 3 * 344) and len(data) <= cis.COLLAGE_MAX_BYTES
        from core.mcp import bridge
        assert cis.COLLAGE_MAX_BYTES < bridge.IMAGE_INLINE_MAX_BYTES
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- скачивание

class _FakeResp:
    def __init__(self, status=200, body=b'', headers=None, chunk_clock=None, tick=0.0):
        self.status = status
        self.body = body
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.closed = False
        self.chunk_clock = chunk_clock
        self.tick = tick

    def iter_chunks(self, size):
        for i in range(0, len(self.body), size):
            if self.chunk_clock is not None:
                self.chunk_clock.now += self.tick
            yield self.body[i:i + size]

    def close(self):
        self.closed = True


class _FakeOpener:
    """opener(scheme, ip, port, host, target, headers): ответы по (host, target); запоминает вызовы."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, scheme, ip, port, host, target, headers, timeout_s=None):
        self.calls.append({'scheme': scheme, 'ip': ip, 'port': port, 'host': host, 'target': target,
                           'headers': headers, 'timeout_s': timeout_s})
        resp = self.responses[(host, target)]
        if isinstance(resp, Exception):
            raise resp
        return resp


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _resolver(table, calls=None):
    def resolve(host, port):
        if calls is not None:
            calls.append(host)
        if host not in table:
            raise socket.gaierror('нет такого имени')
        return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port))
                for ip in table[host]]
    return resolve


PUBLIC = {'img.example': ['93.184.216.34'], 'cdn.example': ['151.101.1.69'],
          'mixed.example': ['93.184.216.36', '10.0.0.7'], 'six.example': ['2606:2800:220:1:248:1893:25c8:1946']}


def test_fetch_connects_to_checked_ip_with_host_header():
    body = jpeg_bytes(100, 100)
    resolved = []
    opener = _FakeOpener({('img.example', '/a%20b.jpg?x=1&y=%D1%8F'): _FakeResp(200, body)})
    data = cis.fetch_image('https://img.example/a%20b.jpg?x=1&y=я', referer='https://img.example/страница',
                           resolver=_resolver(PUBLIC, resolved), opener=opener)
    assert data == body and resolved == ['img.example']         # имя разрешено один раз
    call = opener.calls[0]
    assert call['ip'] == '93.184.216.34' and call['port'] == 443 and call['scheme'] == 'https'
    assert call['headers']['Host'] == 'img.example'
    assert call['headers']['Accept-Encoding'] == 'identity'     # без распаковки на лету
    assert call['headers']['Referer'] == 'https://img.example/%D1%81%D1%82%D1%80%D0%B0%D0%BD%D0%B8%D1%86%D0%B0'
    assert 'KulturaContentBot' in call['headers']['User-Agent']
    # нестандартный порт — в Host; IPv6 — соединение на IPv6-адрес
    opener = _FakeOpener({('img.example', '/a.jpg'): _FakeResp(200, body),
                          ('six.example', '/a.jpg'): _FakeResp(200, body)})
    cis.fetch_image('http://img.example:8080/a.jpg', resolver=_resolver(PUBLIC), opener=opener)
    assert opener.calls[0]['headers']['Host'] == 'img.example:8080' and opener.calls[0]['port'] == 8080
    cis.fetch_image('https://six.example/a.jpg', resolver=_resolver(PUBLIC), opener=opener)
    assert opener.calls[1]['ip'] == '2606:2800:220:1:248:1893:25c8:1946'


def test_fetch_rejects_parser_tricks_before_resolving():
    """Регрессия независимой проверки 2026-10-02: urlsplit и urllib3 по-разному читают «\\» и
    «@» — http://127.0.0.1:10000\\@public.example/ ушёл бы на 127.0.0.1. Такие адреса —
    отказ до разрешения имени и до соединения."""
    resolved = []
    opener = _FakeOpener({})
    for url in ('http://127.0.0.1:10000\\@img.example/x.jpg', 'https://user:pw@img.example/x.jpg',
                'https://img.example@127.0.0.1/x.jpg', 'https://img.example/x .jpg', 'https://img.example/x\r\nHost: evil.jpg',
                'https://img.example:99999/x.jpg', 'ftp://img.example/x.jpg', 'file:///etc/passwd',
                'img.example/x.jpg', 'https://' + 'a' * 2100 + '.example/x.jpg', 'https://-bad-.example/x.jpg'):
        _raises(cis.ImageDownloadFailed, cis.fetch_image, url, resolver=_resolver(PUBLIC, resolved), opener=opener)
    assert resolved == [] and opener.calls == []


def test_fetch_blocks_internal_addresses():
    for ip in ('127.0.0.1', '10.1.2.3', '192.168.0.10', '169.254.169.254', '100.64.0.1', '0.0.0.0', '::1',
               '::ffff:127.0.0.1', 'fd00::1', '224.0.0.1'):
        opener = _FakeOpener({})
        err = _raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://inner.example/x.jpg',
                      resolver=_resolver({'inner.example': [ip]}), opener=opener)
        assert 'внутреннюю сеть' in str(err), ip
        assert opener.calls == [], ip                             # соединения не было
    for url in ('http://127.0.0.1/x.jpg', 'http://[::1]/x.jpg', 'http://169.254.169.254/latest/meta-data/'):
        _raises(cis.ImageDownloadFailed, cis.fetch_image, url, resolver=_resolver({}), opener=_FakeOpener({}))
    # хотя бы один внутренний адрес у имени — отказ; имя не разрешается — отказ
    _raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://mixed.example/x.jpg', resolver=_resolver(PUBLIC),
            opener=_FakeOpener({}))
    _raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://nowhere.example/x.jpg', resolver=_resolver(PUBLIC),
            opener=_FakeOpener({}))


def test_fetch_redirects_are_rechecked():
    body = jpeg_bytes(50, 50)
    opener = _FakeOpener({
        ('img.example', '/a.jpg'): _FakeResp(302, headers={'Location': '/b.jpg'}),
        ('img.example', '/b.jpg'): _FakeResp(301, headers={'Location': 'https://cdn.example/c.jpg'}),
        ('cdn.example', '/c.jpg'): _FakeResp(200, body),
    })
    assert cis.fetch_image('https://img.example/a.jpg', resolver=_resolver(PUBLIC), opener=opener) == body
    assert [c['ip'] for c in opener.calls] == ['93.184.216.34', '93.184.216.34', '151.101.1.69']
    for location in ('http://169.254.169.254/latest/', 'http://127.0.0.1:10000\\@img.example/', 'http://[::1]/'):
        opener = _FakeOpener({('img.example', '/a.jpg'): _FakeResp(302, headers={'Location': location})})
        _raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://img.example/a.jpg',
                resolver=_resolver(PUBLIC), opener=opener)
        assert len(opener.calls) == 1, location
    loop = _FakeOpener({('img.example', '/a.jpg'): _FakeResp(302, headers={'Location': '/a.jpg'})})
    err = _raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://img.example/a.jpg', resolver=_resolver(PUBLIC),
                  opener=loop)
    assert 'переадресаций' in str(err) and len(loop.calls) == cis.MAX_REDIRECTS + 1


def test_fetch_size_status_errors_and_deadline():
    big = _FakeResp(200, b'x' * 2048, headers={'Content-Length': str(10 * 1024 * 1024)})
    _raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://img.example/a.jpg', resolver=_resolver(PUBLIC),
            opener=_FakeOpener({('img.example', '/a.jpg'): big}), max_bytes=1024)
    stream = _FakeResp(200, b'x' * 5000)                           # без Content-Length
    err = _raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://img.example/a.jpg',
                  resolver=_resolver(PUBLIC), opener=_FakeOpener({('img.example', '/a.jpg'): stream}),
                  max_bytes=1024)
    assert 'больше' in str(err) and stream.closed
    missing = _FakeResp(404)
    assert 'HTTP 404' in str(_raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://img.example/a.jpg',
                                     resolver=_resolver(PUBLIC),
                                     opener=_FakeOpener({('img.example', '/a.jpg'): missing})))
    _raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://img.example/a.jpg', resolver=_resolver(PUBLIC),
            opener=_FakeOpener({('img.example', '/a.jpg'): _FakeResp(200, b'')}))
    cut = _FakeResp(200, b'x' * 10, headers={'Content-Length': '100'})   # оборвали на середине
    assert 'оборвал' in str(_raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://img.example/a.jpg',
                                    resolver=_resolver(PUBLIC),
                                    opener=_FakeOpener({('img.example', '/a.jpg'): cut})))
    refused = _FakeOpener({('img.example', '/a.jpg'): ConnectionRefusedError('нет')})
    assert 'нет соединения' in str(_raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://img.example/a.jpg',
                                           resolver=_resolver(PUBLIC), opener=refused))
    # медленный сайт: каждый кусок — 4 с, общий срок 10 с — обрыв, а не бесконечное ожидание
    clock = _Clock()
    slow = _FakeResp(200, b'x' * (64 * 1024 * 5), chunk_clock=clock, tick=4.0)
    err = _raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://img.example/a.jpg', resolver=_resolver(PUBLIC),
                  opener=_FakeOpener({('img.example', '/a.jpg'): slow}), deadline_s=10, clock=clock)
    assert 'медленно' in str(err) and slow.closed


def test_target_idna_and_ipv6_tunnels():
    """Нелатинский домен — в punycode один раз (это же имя идёт в DNS, TLS и Host); IPv6 с IPv4
    внутри (6to4, NAT64, Teredo, «IPv4-совместимые») — отказ, даже если Python считает их
    публичными."""
    scheme, host, port, target, host_header = cis._target('https://пиво.рф/картинка.jpg?размер=большой')
    assert (scheme, host, port) == ('https', 'xn--b1altb.xn--p1ai', 443)
    assert host_header == 'xn--b1altb.xn--p1ai'
    assert target == '/%D0%BA%D0%B0%D1%80%D1%82%D0%B8%D0%BD%D0%BA%D0%B0.jpg?' \
                     '%D1%80%D0%B0%D0%B7%D0%BC%D0%B5%D1%80=%D0%B1%D0%BE%D0%BB%D1%8C%D1%88%D0%BE%D0%B9'
    resolved = []
    opener = _FakeOpener({('xn--b1altb.xn--p1ai', '/a.jpg'): _FakeResp(200, b'x')})
    cis.fetch_image('https://ПИВО.рф/a.jpg', resolver=_resolver({'xn--b1altb.xn--p1ai': ['93.184.216.34']},
                                                                 resolved), opener=opener)
    assert resolved == ['xn--b1altb.xn--p1ai'] and opener.calls[0]['headers']['Host'] == 'xn--b1altb.xn--p1ai'
    for ip in ('2002:7f00:1::1', '64:ff9b::7f00:1', '64:ff9b:1::a00:1', '::7f00:1',
               '2001:0:4136:e378:8000:63bf:3fff:fdd2'):
        _raises(cis.ImageDownloadFailed, cis.fetch_image, 'https://tun.example/x.jpg',
                resolver=_resolver({'tun.example': [ip]}), opener=_FakeOpener({}))


def _serve_once(handler):
    """Локальный TCP-сервер на один запрос: handler(conn) в отдельном потоке. -> порт."""
    import threading
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', 0))
    server.listen(1)

    def run():
        try:
            conn, _addr = server.accept()
        except OSError:
            return
        try:
            handler(conn)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
            server.close()
    threading.Thread(target=run, daemon=True).start()
    return server.getsockname()[1]


def _read_request(conn):
    data = b''
    while b'\r\n\r\n' not in data:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
    return data.decode('latin-1')


def test_open_pinned_real_socket_request():
    """Настоящее соединение (локальный сервер вместо сайта): путь, ровно один Host — из разбора
    адреса, без распаковки; ответ читается кусками."""
    seen = {}
    body = b'\xff\xd8\xff' + b'x' * 5000

    def handler(conn):
        seen['request'] = _read_request(conn)
        conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(body)).encode() +
                     b'\r\nContent-Type: image/jpeg\r\n\r\n' + body)
    port = _serve_once(handler)
    resp = cis._open_pinned('http', '127.0.0.1', port, 'img.example', '/a%20b.jpg?x=1',
                            {'Host': 'img.example', 'Accept-Encoding': 'identity', 'User-Agent': cis.USER_AGENT}, 5)
    try:
        data = b''.join(resp.iter_chunks(1024))
    finally:
        resp.close()
    assert resp.status == 200 and resp.headers['content-type'] == 'image/jpeg' and data == body
    lines = seen['request'].split('\r\n')
    assert lines[0] == 'GET /a%20b.jpg?x=1 HTTP/1.1'
    hosts = [line for line in lines if line.lower().startswith('host:')]
    assert hosts == ['Host: img.example']
    assert 'Accept-Encoding: identity' in lines


def test_open_pinned_watchdog_slow_headers_and_body():
    """Регрессия второй проверки 2026-10-02: сайт отдаёт по байту — таймаут сокета (5 с)
    отсчитывается заново после каждого байта и не спасает. Сторож закрывает сокет по общему
    сроку: и на заголовках, и на теле вызов кончается за ~1 с, а не через десятки секунд."""
    import time as _time

    def slow_headers(conn):
        _read_request(conn)
        for byte in b'HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n0123456789':
            conn.sendall(bytes([byte]))
            _time.sleep(0.2)

    port = _serve_once(slow_headers)
    started = _time.monotonic()
    _raises(Exception, cis._open_pinned, 'http', '127.0.0.1', port, 'img.example', '/', {'Host': 'img.example'}, 1)
    assert _time.monotonic() - started < 3

    def slow_body(conn):
        _read_request(conn)
        conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n')
        for _ in range(200):
            conn.sendall(b'x')
            _time.sleep(0.2)

    port = _serve_once(slow_body)
    started = _time.monotonic()
    resp = cis._open_pinned('http', '127.0.0.1', port, 'img.example', '/', {'Host': 'img.example'}, 1)
    try:
        _raises(Exception, lambda: b''.join(resp.iter_chunks(65536)))
    finally:
        resp.close()
    assert _time.monotonic() - started < 3


# --------------------------------------------------------------------------- подготовка картинки

def test_prepare_image_resize_and_format():
    from PIL import Image
    payload, width, height = cis.prepare_image(jpeg_bytes(4000, 3000))
    assert (width, height) == (2560, 1920)
    image = Image.open(io.BytesIO(payload))
    assert image.format == 'JPEG' and image.size == (2560, 1920) and payload[:3] == b'\xff\xd8\xff'
    assert len(payload) <= cis.TELEGRAM_PHOTO_MAX_BYTES
    payload, width, height = cis.prepare_image(jpeg_bytes(1200, 900))
    assert (width, height) == (1200, 900)                       # меньше предела — не трогаем размер


def test_prepare_image_large_jpeg_uses_draft():
    payload, width, height = cis.prepare_image(jpeg_bytes(6400, 4800))   # 30,7 Мп — меньше JPEG_MAX_PIXELS
    assert (width, height) == (2560, 1920)


def test_draft_box_follows_aspect():
    """Регрессия второй проверки: квадратная рамка 2560x2560 не уменьшала 16:9 до 5120 по
    короткой стороне — картинка 6400x3600 распаковывалась целиком. Рамка по пропорциям —
    распаковка вдвое меньшей (3200x1800)."""
    from PIL import Image
    image = Image.open(io.BytesIO(jpeg_bytes(6400, 3600)))
    cis._draft(image, cis.MAX_SIDE)
    assert image.size == (3200, 1800)
    small = Image.open(io.BytesIO(jpeg_bytes(1200, 800)))
    cis._draft(small, cis.MAX_SIDE)
    assert small.size == (1200, 800)                            # меньше предела — не трогаем


def test_prepare_image_transparency_and_exif():
    from PIL import Image
    payload, _w, _h = cis.prepare_image(png_bytes(1000, 800, rgba=(200, 30, 30, 0)))
    pixel = Image.open(io.BytesIO(payload)).getpixel((500, 400))
    assert all(channel > 240 for channel in pixel)              # прозрачное — белое, не чёрное
    payload, width, height = cis.prepare_image(jpeg_bytes(1200, 900, exif_orientation=6))
    assert (width, height) == (900, 1200)                       # поворот по EXIF
    payload, width, height = cis.prepare_image(jpeg_bytes(4000, 3000, exif_orientation=8))
    assert (width, height) == (1920, 2560)                      # поворот после уменьшения


def test_prepare_image_rejects():
    assert 'мелкая' in str(_raises(cis.ImageDownloadFailed, cis.prepare_image, jpeg_bytes(700, 500)))
    assert 'вытянутая' in str(_raises(cis.ImageDownloadFailed, cis.prepare_image, jpeg_bytes(4200, 200)))
    _raises(cis.ImageDownloadFailed, cis.prepare_image, b'<html>not an image</html>')
    from PIL import Image
    out = io.BytesIO()
    Image.new('RGB', (1000, 800)).save(out, 'BMP')
    _raises(cis.ImageDownloadFailed, cis.prepare_image, out.getvalue())


def test_prepare_image_rejects_bomb_before_decoding():
    """Регрессия независимой проверки: однотонный PNG 4000x4000 весит килобайты, а в памяти —
    64 МБ и больше. Предел пикселей проверяется по заголовку, до распаковки."""
    from PIL import Image
    out = io.BytesIO()
    Image.new('L', (4000, 4000), 0).save(out, 'PNG', optimize=True)
    data = out.getvalue()
    assert len(data) < 200 * 1024
    err = _raises(cis.ImageDownloadFailed, cis.prepare_image, data)
    assert 'слишком большая' in str(err)
    assert cis._preview_cell(data) is None


# --------------------------------------------------------------------------- маршруты

class _Rig:
    """Голый Flask с content_plan_bp, временный план, поддельный поиск."""

    def __init__(self, user=ADMIN, docs=None, pages=None, configured=True):
        self.tmp = tempfile.mkdtemp(prefix='image_routes_test_')
        self.store = cp.ContentPlanStore(os.path.join(self.tmp, 'content_plan.json'),
                                         now_fn=lambda: datetime(2026, 10, 7, 12, 0))
        default_docs = [doc(1), doc(2), doc(3, width=700, height=500)]
        default_pages = {'https://site1.example/img/1.jpg': jpeg_bytes(3000, 2000),
                         'https://site2.example/img/2.jpg': jpeg_bytes(600, 400)}     # мельче 800
        self.finder, self.session, self.web, _ = make_finder(docs if docs is not None else default_docs,
                                                             pages if pages is not None else default_pages,
                                                             tmp=self.tmp, configured=configured)
        self.user = user
        self.saved = (rcp._store, rcp.current_user, rcp._image_finder)

    def __enter__(self):
        rcp._store = lambda: self.store
        rcp.current_user = lambda: self.user
        rcp._image_finder = lambda: self.finder
        app = Flask('test_content_image_search')
        app.register_blueprint(rcp.content_plan_bp)
        self.client = app.test_client()
        return self

    def __exit__(self, *exc):
        rcp._store, rcp.current_user, rcp._image_finder = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def material(self, origin_user=None, **fields):
        fields.setdefault('month', '2026-10')
        fields.setdefault('title', 'История')
        return self.store.create_material(fields, origin_user or self.user)

    def post_search(self, **body):
        return self.client.post('/api/content-plan/image-search', json=body)

    def search(self, q='Rodenbach foeders'):
        resp = self.post_search(q=q)
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()


def test_route_search_post_admin_only_and_not_configured():
    with _Rig(user=BARTENDER) as rig:
        resp = rig.post_search(q='пиво')
        assert resp.status_code == 403 and resp.get_json()['code'] == 'admin_required'
        assert rig.session.calls == []
    with _Rig(configured=False) as rig:
        resp = rig.post_search(q='пиво')
        assert resp.status_code == 503 and resp.get_json()['code'] == 'image_search_not_configured'
    with _Rig() as rig:
        assert rig.client.get('/api/content-plan/image-search?q=пиво').status_code == 405   # только POST
        assert rig.post_search(q='a').status_code == 400
        assert rig.post_search(q='пиво', orientation='round').status_code == 400


def test_route_search_caller_failed_and_limit():
    with _Rig(user=AGENT_FULL) as rig:
        rig.finder.client.session = FakeYandexSession(status=500, payload={'message': 'boom'})
        resp = rig.post_search(q='пиво')
        assert resp.status_code == 502 and resp.get_json()['code'] == 'image_search_failed'
        rig.finder.client.session = FakeYandexSession(yandex_xml([doc(1)]))
        rig.finder.caller_limit = 1
        found = rig.search()
        assert rig.finder.store.load(found['search_id'])['caller'] == 't1'      # предел — по токену MCP
        resp = rig.post_search(q='пиво')
        assert resp.status_code == 429 and resp.get_json()['code'] == 'image_search_daily_limit'
    with _Rig() as rig:
        found = rig.search()
        assert rig.finder.store.load(found['search_id'])['caller'] == 'login:anna'   # человек — по входу


def test_route_search_limit_per_oauth_grant_survives_token_refresh():
    """claude.ai обновляет access-токен каждый час: новый mcp_token_id, тот же грант.
    Предел «на подключение» считается по гранту (mcp_connection_id) и не обнуляется."""
    agent = dict(AGENT_FULL, mcp_token_id='oa_000000000001', mcp_connection_id='g_00000000000000aa')
    with _Rig(user=agent) as rig:
        rig.finder.client.session = FakeYandexSession(yandex_xml([doc(1)]))
        rig.finder.caller_limit = 1
        found = rig.search()
        assert rig.finder.store.load(found['search_id'])['caller'] == 'g_00000000000000aa'
        rig.user = dict(agent, mcp_token_id='oa_000000000002')                  # токен обновился
        resp = rig.post_search(q='пиво')
        assert resp.status_code == 429 and resp.get_json()['code'] == 'image_search_daily_limit'
        rig.user = dict(agent, mcp_token_id='oa_000000000003', mcp_connection_id='g_00000000000000bb')
        assert rig.post_search(q='пиво').status_code == 200                     # другое подключение


def test_found_media_name_keeps_extension():
    assert cis.found_media_name('upload.wikimedia.org', '20261007_3f9a1c2b.jpg') == 'upload.wikimedia.org.jpg'
    long_site = 'a' * 250 + '.example'
    name = cis.found_media_name(long_site, '20261007_3f9a1c2b.jpg')
    assert name == 'a' * cis.FOUND_NAME_SITE_MAX + '.jpg'
    assert cis.found_media_name('', '20261007_3f9a1c2b.jpg') == '20261007_3f9a1c2b.jpg'
    assert cis.found_media_name(None, '20261007_3f9a1c2b.jpg') == '20261007_3f9a1c2b.jpg'


def test_route_collage():
    with _Rig() as rig:
        found = rig.search()
        resp = rig.client.get(found['collage'])
        assert resp.status_code == 200 and resp.mimetype == 'image/jpeg'
        assert resp.headers['X-Content-Type-Options'] == 'nosniff'
        assert resp.data[:3] == b'\xff\xd8\xff'
        assert rig.client.get('/api/content-plan/image-search/is_20261007_000000000000/collage').status_code == 404
        assert rig.client.get('/api/content-plan/image-search/../collage').status_code == 404


def test_route_add_found_media():
    with _Rig() as rig:
        material = rig.material()
        found = rig.search()
        first = found['candidates'][0]['candidate']
        resp = rig.client.post(f'/api/content-plan/materials/{material["id"]}/media/found',
                               json={'candidate': first})
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert (body['file']['width'], body['file']['height']) == (2560, 1707)
        media = body['material']['media']
        assert len(media) == 1 and media[0]['kind'] == 'image' and media[0]['original_name'] == 'site1.example.jpg'
        source = media[0]['source']
        assert source['image_url'] == 'https://site1.example/img/1.jpg'
        assert source['page_url'] == 'https://site1.example/page/1.html'
        assert source['query'] == 'Rodenbach foeders' and source['candidate'] == first
        assert rig.store.media.exists(media[0]['name'])
        log = rig.store.log_for(material['id'])
        assert log[0]['text'] == 'Добавлена картинка из поиска: site1.example'
        # архив для Instagram: файл с расширением, телефон откроет его как фото
        with zipfile.ZipFile(cpub.build_material_zip(rig.store, rig.store.get_material_raw(material['id']))) as zf:
            assert 'files/01_site1.example.jpg' in zf.namelist()
        # мелкая — 400 с кодом, файл не остаётся
        before = sorted(os.listdir(rig.store.media.directory))
        resp = rig.client.post(f'/api/content-plan/materials/{material["id"]}/media/found',
                               json={'candidate': found['candidates'][1]['candidate']})
        assert resp.status_code == 400 and resp.get_json()['code'] == 'image_download_failed'
        assert 'мелкая' in resp.get_json()['error']
        assert sorted(os.listdir(rig.store.media.directory)) == before
        # вариант не из поиска, чужой формат и неизвестный материал
        bad = rig.client.post(f'/api/content-plan/materials/{material["id"]}/media/found',
                              json={'candidate': 'https://evil.example/x.jpg'})
        assert bad.status_code == 400
        gone = rig.client.post(f'/api/content-plan/materials/{material["id"]}/media/found',
                               json={'candidate': found['search_id'] + '-9'})
        assert gone.status_code == 404
        nope = rig.client.post('/api/content-plan/materials/m_000000000000/media/found', json={'candidate': first})
        assert nope.status_code == 404


def test_route_add_found_draft_mode():
    with _Rig(user=AGENT_DRAFT_MODE) as rig:
        human = rig.material(origin_user=ADMIN, title='Материал владельца')
        own = rig.material(title='Черновик агента')
        assert own['origin'] == 'agent' and human['origin'] == 'human'
        found = rig.search()
        downloads = len(rig.web.calls)
        resp = rig.client.post(f'/api/content-plan/materials/{human["id"]}/media/found',
                               json={'candidate': found['candidates'][0]['candidate']})
        assert resp.status_code == 409
        assert len(rig.web.calls) == downloads                  # отказ ДО скачивания
        resp = rig.client.post(f'/api/content-plan/materials/{own["id"]}/media/found',
                               json={'candidate': found['candidates'][0]['candidate']})
        assert resp.status_code == 200
        media = resp.get_json()['material']['media']
        assert media[0]['uploaded_by'] == 'anna · агент'


def test_store_add_media_guard_and_source_cleaning():
    tmp = tempfile.mkdtemp(prefix='image_store_cp_')
    try:
        store = cp.ContentPlanStore(os.path.join(tmp, 'content_plan.json'),
                                    now_fn=lambda: datetime(2026, 10, 7, 12, 0))
        human = store.create_material({'month': '2026-10', 'title': 'Пост'}, ADMIN)
        ok, name = store.media.save(jpeg_bytes(900, 900), store.today())
        assert ok
        _raises(cp.ContentPlanConflict, store.add_media, human['id'], name, 10, 'a.jpg', AGENT_DRAFT_MODE)
        view, _unapproved = store.add_media(human['id'], name, 10, 'site.example', AGENT_FULL,
                                            source={'image_url': ' https://site.example/a.jpg ', 'width': 900,
                                                    'height': True, 'evil': 'x', 'title': 'x' * 900})
        source = view['media'][0]['source']
        assert source == {'image_url': 'https://site.example/a.jpg', 'title': 'x' * cp.MEDIA_SOURCE_TEXT_MAX,
                          'width': 900}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_conftest_blanks_yandex_key():
    """Под pytest ключ Яндекса пустой (tests/conftest.py): платный поиск тесты не зовут."""
    if 'pytest' not in sys.modules:
        return
    assert os.environ.get(cis.ENV_API_KEY, '') == ''


if __name__ == '__main__':
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('ok  ', name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print('FAIL', name, repr(e))
    print(json.dumps({'failed': failed}))
    sys.exit(1 if failed else 0)
