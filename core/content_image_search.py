"""
Картинки к постам контент-плана: поиск в интернете, коллаж для агента, скачивание.

## Что это

Агент контент-плана сам подбирает картинки к историям, праздникам и событиям:
ищет в интернете (Yandex Search API, поиск по картинкам), смотрит варианты одной
картинкой-коллажем и прикрепляет выбранный к материалу. Решение владельца
2026-10-02: «агент собирает картинки сам и сразу добавляет в план публикаций»,
поиск НЕ ограничен открытыми лицензиями (каналы баров — локальные, на десятки
подписчиков). Фото баров, кранов, блюд и людей по-прежнему снимает команда: чужая
картинка там выдавала бы чужое за своё (правило агенту — core/mcp/tools/content.py).

Модуль решает: как спросить Яндекс и разобрать ответ, что отбросить, где хранить
результаты поиска, как собрать коллаж, как безопасно скачать картинку и подготовить
её для Telegram. Какие файлы у материала — по-прежнему core/content_plan.py; запись
файла на диск — core/content_media.py.

## Файлы

| Файл | Роль |
|------|------|
| core/content_image_search.py | этот модуль |
| routes/content_plan.py | маршруты POST /api/content-plan/image-search, GET .../image-search/<id>/collage, POST /api/content-plan/materials/<id>/media/found |
| core/content_plan.py | ContentPlanStore.add_media(source=...) — источник картинки в media[].source |
| core/mcp/tools/content.py | инструменты content_image_search, content_image_search_collage, content_media_add_found |
| tests/test_content_image_search.py, tests/image_search_fakes.py | тесты модуля и маршрутов (Яндекс, сайты и сеть поддельные) |
| docs/content-plan.md | раздел «Картинки к постам» простыми словами |

## Как работает

1. Поиск (YandexImageClient.search): POST SEARCH_URL с ключом API сервисного
   аккаунта (заголовок Authorization: Api-Key) и каталогом folderId; DOCS_ON_PAGE = 60
   картинок за запрос. Фильтр размера Яндекса НЕ ставим: у него «LARGE» — это
   800x600..1600x1200 (самые большие туда не входят), «ENORMOUS» — больше 1600x1200
   (отсекает хорошие картинки 1200 px); отбор по размеру делаем сами (п. 2). Ответ —
   JSON {rawData: XML в base64}. Картинка — элемент doc внутри group: url (адрес самой
   картинки), domain, title, image-properties: original-width, original-height,
   mime-type, html-link (страница с картинкой) — тот же разбор, что в официальном SDK
   yandex-ai-studio-sdk. Ошибка Яндекса — элемент error; код 15 («ничего не нашлось»)
   — пустой список, а не сбой.
2. Отбор (pick_candidates), по порядку выдачи Яндекса:
   - повтор адреса картинки — отбрасывается (duplicate);
   - сток с водяными знаками (STOCK_DOMAINS: shutterstock, depositphotos, ...) —
     отбрасывается (stock): превью у них с надписью поперёк;
   - большая сторона меньше MIN_LONG_SIDE = 1000 px — отбрасывается (small): в
     Telegram картинка шириной 600 px выглядит мутно. Размер неизвестен — оставляем,
     проверка будет при скачивании;
   - остальное — до CANDIDATES_MAX = 12 вариантов (коллаж 4 x 3).
   Пример: из 60 картинок 3 повтора, 5 со стоков, 30 мелких -> 22 годных, агенту — 12.
3. Хранение (SearchStore): каждый поиск — файл is_<YYYYMMDD>_<12 hex>.json в каталоге
   content_image_search/ на постоянном диске; вариант — «<id поиска>-<номер>», например
   is_20261002_3f9a1c2b7d4e-3. Агент прикрепляет ТОЛЬКО вариант из такого файла:
   адрес картинки сервер берёт у себя, а не из вызова. Так «команда», внедрённая в
   отзыв или описание пива, не заставит сервер сходить по произвольному адресу.
   Файлы старше KEEP_DAYS = 3 суток (и брошенные *.tmp старше часа) удаляются при
   следующем поиске.
4. Предел (запрос в Яндекс платный, петля агента не должна сжечь бюджет): поисков в
   сутки по Москве — не больше DAILY_LIMIT = 150 на всю сеть и PER_CALLER_DAILY_LIMIT =
   60 на один токен MCP (или вход человека), чтобы одно расписание (например, сбитое
   внедрённой «командой») не перекрыло поиск остальным: им остаётся не меньше 90. Место бронируется ДО запроса: сначала пишется файл поиска «pending», потом
   считаются файлы суток — так параллельные воркеры не проскочат предел вдвоём. Яндекс
   ответил ошибкой — бронь снимается (неудачный поиск не считается).
5. Коллаж (ImageFinder.collage): 4 колонки x до 3 рядов, ячейка 300 x 300; над
   картинкой — номер, размер оригинала и домен (латиницей: шрифта с кириллицей в
   образе может не быть). Превью — по порядку: ссылка на миниатюру из ответа Яндекса
   (если есть), сам оригинал (до PREVIEW_MAX_BYTES), миниатюра Яндекса по id картинки
   (адрес собран по образцу и может вернуть заглушку — поэтому последней; меньше
   PREVIEW_MIN_SIDE px — не превью). Превью качаются параллельно (PREVIEW_WORKERS
   потоков), каждое — не дольше PREVIEW_DEADLINE_S, весь коллаж — не дольше
   COLLAGE_BUDGET_S: что не успело — серая ячейка «no preview», поток воркера сайта
   не висит на медленном сайте. Коллаж кэшируется рядом с файлом поиска (через
   уникальный временный файл и os.replace), только если все превью получились:
   временный сбой сайта не должен оставить серый коллаж на 3 суток. JPEG коллажа не
   больше COLLAGE_MAX_BYTES — меньше предела, с которым мост MCP отдаёт картинку агенту
   изображением (core/mcp/bridge.IMAGE_INLINE_MAX_BYTES).
6. Скачивание (fetch_image) — защита от запросов во внутреннюю сеть:
   - адрес разбирается ОДИН раз (_target), и соединение строится из этих же частей:
     нет расхождения двух разборщиков (urlsplit и urllib3 по-разному читают «\\» и «@» —
     http://127.0.0.1:10000\\@public.example/ ушёл бы на 127.0.0.1). Обратная косая черта,
     данные входа (user@host), пробелы и управляющие символы — отказ; нелатинский домен
     (пиво.рф) переводится в punycode один раз, и это же имя идёт в DNS, TLS и Host;
   - имя разрешается в IP ОДИН раз, все адреса должны быть публичными
     (ipaddress.is_global: закрыты localhost, внутренние сети, link-local с адресом
     метаданных облака 169.254.169.254, 100.64/10 и прочие служебные; плюс IPv6 с IPv4
     внутри — 6to4, NAT64, Teredo, «IPv4-совместимые»), и соединение идёт на ЭТОТ IP:
     сокет открываем сами (_open_pinned), TLS — с проверкой сертификата по имени хоста
     (SNI, check_hostname), Host — из разбора. Подмена DNS между проверкой и соединением
     ничего не даёт;
   - каждая переадресация проверяется заново, не больше MAX_REDIRECTS;
   - общий срок на всё скачивание (DOWNLOAD_DEADLINE_S, для превью PREVIEW_DEADLINE_S)
     держит сторож (_Watchdog): по сроку он закрывает сокет, и блокирующее чтение
     заголовков или тела обрывается. Таймаут сокета этого не даёт — он отсчитывается
     заново после каждого байта, и сайт, отдающий по байту в 4 секунды, держал бы поток
     сайта часами;
   - тело читается кусками без распаковки (Accept-Encoding: identity) и обрывается после
     предела байт; Referer — страница с картинкой (часть сайтов не отдаёт картинку «со
     стороны»).
7. Подготовка (prepare_image, Pillow) — под общим на процесс семафором DECODE_SLOTS
   (распаковка картинки — сотни мегабайт памяти, параллельно не больше двух):
   только JPEG, PNG, WEBP, GIF (первый кадр; Image.open(formats=...) — других
   разборщиков не трогаем); пиксели считаются ДО распаковки: JPEG до JPEG_MAX_PIXELS
   (распаковывается сразу уменьшенным — draft), остальное до OTHER_MAX_PIXELS — защита
   от «бомбы» (маленький файл, огромная картинка); большая сторона меньше
   ATTACH_MIN_LONG_SIDE = 800 px — отказ (мелкая картинка в посте мутная); стороны в
   отношении больше MAX_ASPECT = 20 — отказ (Telegram такое фото не примет);
   прозрачность — на белый фон; большая сторона больше MAX_SIDE = 2560 px — уменьшение;
   поворот по EXIF — после уменьшения (меньше памяти). Рамка draft у JPEG — по пропорциям
   картинки (8400x4725 -> не меньше 2560x1440): квадратная рамка 2560x2560 уменьшала бы
   только картинки, у которых обе стороны от 5120, а обычные 3:2 и 16:9 распаковывались бы
   целиком. Сохраняется JPEG качества
   JPEG_QUALITY = 88; если вдруг больше 10 МБ (предел Telegram) — качество ниже шагами
   по 10.

Настройка: YANDEX_SEARCH_API_KEY — ключ API сервисного аккаунта с доступом к Search API,
YANDEX_SEARCH_FOLDER_ID — id каталога в Яндекс Облаке. Нет любого — поиск отвечает
ImageSearchNotConfigured (HTTP 503 image_search_not_configured); коллаж и прикрепление
уже найденного работают и без ключа, остальной контент-план — тоже.

Что сломается, если менять неосторожно:
- принимать в content_media_add_found произвольный адрес — сервер станет «прокси» для
  внедрённой команды (данные в адресе запроса, походы во внутреннюю сеть);
- отдать соединение requests/urllib3 по исходной строке адреса вместо проверенных частей
  и проверенного IP — вернётся обход проверки через «\\», «@» и подмену DNS;
- убрать сторожа срока или бюджет коллажа — медленный сайт займёт потоки сайта;
- поднять пределы пикселей или убрать семафор — коллаж из PNG-«бомб» съест память
  контейнера;
- поднять CANDIDATES_MAX выше 12 — коллаж не влезет в предел картинки для агента.

## Changelog

- 2026-10-02 — модуль создан: поиск через Yandex Search API, отбор, хранение поисков,
  коллаж, безопасное скачивание, подготовка JPEG для Telegram. По независимой проверке в
  тот же день: соединение на проверенный IP из одного разбора адреса, сторож общего срока
  скачивания и бюджет коллажа, семафор и пределы пикселей при распаковке, рамка draft по
  пропорциям, нелатинские домены через punycode, IPv6 с IPv4 внутри закрыты, без фильтра
  размера Яндекса, бронь места в суточном пределе, предел 60 поисков на токен, кэш
  коллажа только целиком и через уникальный временный файл.
"""

import base64
import io
import ipaddress
import json
import math
import os
import re
import secrets
import socket
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin, urlsplit

import requests

from core import msk_time
from core.json_store import atomic_write_json
from core.storage_paths import get_data_path

# ---------------------------------------------------------------- константы

SEARCH_URL = 'https://searchapi.api.cloud.yandex.net/v2/image/search'
ENV_API_KEY = 'YANDEX_SEARCH_API_KEY'
ENV_FOLDER_ID = 'YANDEX_SEARCH_FOLDER_ID'

STORE_DIR_NAME = 'content_image_search'

QUERY_MIN, QUERY_MAX = 2, 400          # предел Яндекса для queryText — 400 знаков
PAGE_MAX = 9                           # страницы выдачи 0..9: дальше картинки уже случайные
DOCS_ON_PAGE = 60                      # просим у Яндекса с запасом на отсев (п. 2 докстроки)
CANDIDATES_MAX = 12                    # коллаж 4 x 3
MIN_LONG_SIDE = 1000                   # отбор по размеру из ответа Яндекса
ATTACH_MIN_LONG_SIDE = 800             # проверка настоящего файла при прикреплении
MAX_SIDE = 2560                        # большая сторона файла в материале
MAX_ASPECT = 20                        # предел Telegram на отношение сторон фото
JPEG_MAX_PIXELS = 40_000_000           # JPEG распаковывается сразу уменьшенным (draft)
OTHER_MAX_PIXELS = 12_000_000          # PNG, WEBP, GIF — распаковываются целиком
PREVIEW_OTHER_MAX_PIXELS = 8_000_000   # то же для превью коллажа
DECODE_SLOTS = 2                       # распаковок одновременно на процесс
JPEG_QUALITY = 88
KEEP_DAYS = 3                          # сколько суток хранятся результаты поиска
TMP_KEEP_S = 3600                      # брошенный временный файл коллажа старше часа — мусор
DAILY_LIMIT = 150                      # поисков в сутки на всю сеть
PER_CALLER_DAILY_LIMIT = 60            # поисков в сутки на один токен MCP или вход человека

DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024  # оригинал картинки (уменьшим сами)
PREVIEW_MAX_BYTES = 6 * 1024 * 1024    # оригинал вместо превью для коллажа
PREVIEW_MIN_SIDE = 40                  # меньше — не превью, а заглушка или счётчик
TELEGRAM_PHOTO_MAX_BYTES = 10 * 1024 * 1024
URL_MAX = 2048
MAX_REDIRECTS = 3
CONNECT_TIMEOUT_S, READ_TIMEOUT_S = 5, 5   # на каждое соединение и каждое чтение
DOWNLOAD_DEADLINE_S = 30               # всё скачивание оригинала, с переадресациями
PREVIEW_DEADLINE_S = 8                 # одно превью
COLLAGE_BUDGET_S = 25                  # весь коллаж
SEARCH_TIMEOUT_S = 25
PREVIEW_WORKERS = 6

COLLAGE_COLUMNS = 4
COLLAGE_CELL = 300                     # картинка в ячейке, px
COLLAGE_LABEL = 34                     # полоса подписи над картинкой, px
COLLAGE_MAX_BYTES = 650 * 1024         # < core.mcp.bridge.IMAGE_INLINE_MAX_BYTES (700 КБ)

USER_AGENT = 'Mozilla/5.0 (compatible; KulturaContentBot/1.0; +https://beerkultura.ru)'
IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp,image/gif;q=0.9,image/*;q=0.5'

ORIENTATIONS = ('vertical', 'horizontal', 'square')
_ORIENTATION_API = {'vertical': 'IMAGE_ORIENTATION_VERTICAL', 'horizontal': 'IMAGE_ORIENTATION_HORIZONTAL',
                    'square': 'IMAGE_ORIENTATION_SQUARE'}
ALLOWED_FORMATS = ('JPEG', 'PNG', 'WEBP', 'GIF')
REDIRECT_CODES = (301, 302, 303, 307, 308)

# Стоки, у которых превью — с водяным знаком поперёк картинки. Совпадение по домену
# или его поддомену (img.alamy.com, st2.depositphotos.com, t3.ftcdn.net).
STOCK_DOMAINS = (
    'shutterstock.com', 'depositphotos.com', 'istockphoto.com', 'gettyimages.com', 'gettyimages.ru',
    'gettyimages.co.uk', 'alamy.com', 'dreamstime.com', '123rf.com', 'stock.adobe.com', 'ftcdn.net',
    'bigstockphoto.com', 'canstockphoto.com', 'canstockphoto.ru', 'vectorstock.com', 'pond5.com',
    'agefotostock.com', 'lori.ru', 'pressfoto.ru', 'fotolia.com', 'colourbox.com', 'yayimages.com',
    'mostphotos.com', 'featurepics.com', 'stockfresh.com', 'crushpixel.com', 'photogenica.ru',
)

# Форма id поиска и варианта. Конец строки — \Z: `$` пропустил бы перевод строки.
SEARCH_ID_RE = re.compile(r'^is_\d{8}_[0-9a-f]{12}\Z')
CANDIDATE_RE = re.compile(r'^(is_\d{8}_[0-9a-f]{12})-(\d{1,2})\Z')
SITE_RE = re.compile(r'^(?=.{3,100}\Z)([a-z0-9-]+\.)+[a-z0-9-]{2,}\Z')
_HOST_RE = re.compile(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*\.?\Z')
_TAG_RE = re.compile(r'<[^>]+>')
_STORE_FILE_RE = re.compile(r'^is_(\d{8})_[0-9a-f]{12}\.(json|jpg)\Z')

# Распаковка картинок (Pillow) — сотни мегабайт памяти на большую картинку: не больше
# DECODE_SLOTS одновременно на процесс (коллаж качает превью в PREVIEW_WORKERS потоков).
_DECODE = threading.BoundedSemaphore(DECODE_SLOTS)


# ---------------------------------------------------------------- ошибки

class ImageSearchNotConfigured(Exception):
    """Нет ключа или каталога Яндекса (HTTP 503 image_search_not_configured)."""


class ImageSearchFailed(Exception):
    """Яндекс ответил ошибкой или не ответил (HTTP 502 image_search_failed)."""


class ImageSearchLimit(Exception):
    """Исчерпан суточный предел поисков (HTTP 429 image_search_daily_limit)."""


class ImageSearchNotFound(LookupError):
    """Нет такого поиска или варианта (устарел, опечатка) — HTTP 404."""


class ImageDownloadFailed(ValueError):
    """Картинку не удалось скачать или она не годится (HTTP 400): агент берёт другой вариант."""


# ---------------------------------------------------------------- настройка

def settings_from_env() -> Tuple[str, str]:
    """(ключ API, каталог) из окружения; пустые строки — не настроено."""
    return (os.environ.get(ENV_API_KEY, '').strip(), os.environ.get(ENV_FOLDER_ID, '').strip())


def is_configured() -> bool:
    key, folder = settings_from_env()
    return bool(key and folder)


# ---------------------------------------------------------------- проверки ввода

def clean_query(query) -> str:
    """Запрос поиска: пробелы схлопнуты, длина QUERY_MIN..QUERY_MAX, иначе ValueError."""
    text = ' '.join(str(query or '').split())
    if len(text) < QUERY_MIN:
        raise ValueError('Что искать: запрос из двух знаков и больше')
    if len(text) > QUERY_MAX:
        raise ValueError(f'Запрос длиннее {QUERY_MAX} знаков — сократите')
    return text


def clean_orientation(value) -> Optional[str]:
    text = str(value or '').strip().lower()
    if not text:
        return None
    if text not in ORIENTATIONS:
        raise ValueError('Ориентация: vertical, horizontal или square')
    return text


def clean_site(value) -> Optional[str]:
    """Домен сайта для поиска: rodenbach.be (без http и пути), иначе ValueError."""
    text = str(value or '').strip().lower()
    if not text:
        return None
    if text.startswith('www.'):
        text = text[4:]
    if not SITE_RE.match(text):
        raise ValueError('Сайт: только домен, например rodenbach.be')
    return text


def clean_page(value) -> int:
    if value in (None, ''):
        return 0
    if isinstance(value, bool):
        raise ValueError('Страница выдачи: число 0..9')
    try:
        page = int(str(value).strip())
    except ValueError:
        raise ValueError('Страница выдачи: число 0..9') from None
    if not 0 <= page <= PAGE_MAX:
        raise ValueError(f'Страница выдачи: число 0..{PAGE_MAX}')
    return page


def parse_candidate(ref) -> Tuple[str, int]:
    """'is_20261002_3f9a1c2b7d4e-3' -> ('is_20261002_3f9a1c2b7d4e', 3); иначе ValueError."""
    match = CANDIDATE_RE.match(str(ref or '').strip())
    if not match:
        raise ValueError('Вариант картинки: candidate из ответа поиска, например is_20261002_3f9a1c2b7d4e-3')
    return match.group(1), int(match.group(2))


# ---------------------------------------------------------------- ответ Яндекса

def _text(node: Optional[ET.Element], name: str) -> str:
    if node is None:
        return ''
    child = node.find(name)
    if child is None:
        return ''
    return ' '.join(''.join(child.itertext()).split())


def _int_or_none(value: str) -> Optional[int]:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _http_url(value: str) -> str:
    text = (value or '').strip()
    if text.startswith('//'):
        text = 'https:' + text
    return text if text.startswith(('http://', 'https://')) else ''


def parse_response_xml(raw: bytes) -> List[dict]:
    """XML ответа Яндекса -> [{image_url, domain, title, width, height, format, page_url,
    thumb_urls, guessed_thumb_urls}] в порядке выдачи. Элемент error: код 15 — [] (ничего
    не нашлось), иначе ImageSearchFailed с текстом Яндекса."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise ImageSearchFailed(f'Яндекс прислал неразборчивый ответ: {e}') from None
    response = root.find('response')
    if response is None:
        response = root
    error = response.find('error')
    if error is not None:
        code = (error.get('code') or '').strip()
        if code == '15':
            return []
        message = ' '.join(''.join(error.itertext()).split()) or 'без текста'
        raise ImageSearchFailed(f'Яндекс ответил ошибкой {code or "?"}: {message}')
    docs = []
    for doc in response.iter('doc'):
        props = doc.find('image-properties')
        image_url = _http_url(_text(doc, 'url')) or _http_url(_text(props, 'image-link'))
        if not image_url:
            continue
        thumbs, guessed = [], []
        if props is not None:
            for child in props:
                if 'thumb' in child.tag and 'link' in child.tag:
                    url = _http_url(''.join(child.itertext()))
                    if url:
                        thumbs.append(url)
            image_id = _text(props, 'id')
            if image_id and re.fullmatch(r'[0-9A-Za-z_\-]{6,200}', image_id):
                shard = _text(props, 'shard')
                shard = shard if shard.isdigit() else '0'
                guessed.append('https://avatars.mds.yandex.net/i?id=' + quote(image_id) + '&n=13')
                guessed.append('https://im' + shard + '-tub-ru.yandex.net/i?id=' + quote(image_id))
        mime = _text(props, 'mime-type').lower()
        docs.append({
            'image_url': image_url,
            'domain': _text(doc, 'domain').lower() or (urlsplit(image_url).hostname or ''),
            'title': _TAG_RE.sub('', _text(doc, 'title'))[:200],
            'width': _int_or_none(_text(props, 'original-width')),
            'height': _int_or_none(_text(props, 'original-height')),
            'format': mime.split('/')[-1] if mime else '',
            'page_url': _http_url(_text(props, 'html-link')),
            'thumb_urls': thumbs,
            'guessed_thumb_urls': guessed,
        })
    return docs


def _host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or '').lower().rstrip('.')
    except ValueError:
        return ''


def is_stock(*hosts: str) -> bool:
    """Хост принадлежит стоку с водяными знаками (сам домен или его поддомен)."""
    for host in hosts:
        host = (host or '').lower().rstrip('.')
        if host.startswith('www.'):
            host = host[4:]
        for domain in STOCK_DOMAINS:
            if host == domain or host.endswith('.' + domain):
                return True
    return False


def pick_candidates(docs: List[dict], limit: int = CANDIDATES_MAX) -> Tuple[List[dict], Dict[str, int]]:
    """Отбор из выдачи (п. 2 докстроки) -> (варианты, {duplicate, stock, small})."""
    seen = set()
    dropped = {'duplicate': 0, 'stock': 0, 'small': 0}
    picked = []
    for doc in docs:
        url = doc.get('image_url') or ''
        if url in seen:
            dropped['duplicate'] += 1
            continue
        seen.add(url)
        if is_stock(_host_of(url), doc.get('domain') or '', _host_of(doc.get('page_url') or '')):
            dropped['stock'] += 1
            continue
        width, height = doc.get('width'), doc.get('height')
        if width and height and max(width, height) < MIN_LONG_SIDE:
            dropped['small'] += 1
            continue
        if len(picked) < limit:
            picked.append(doc)
    return picked, dropped


# ---------------------------------------------------------------- клиент Яндекса

class YandexImageClient:
    """Поиск по картинкам Yandex Search API v2 (REST). session — точка подмены для тестов."""

    def __init__(self, api_key: str, folder_id: str, session: Optional[requests.Session] = None,
                 timeout: float = SEARCH_TIMEOUT_S):
        self.api_key = api_key
        self.folder_id = folder_id
        self.session = session or requests.Session()
        self.timeout = timeout

    def body(self, query: str, orientation: Optional[str] = None, site: Optional[str] = None,
             page: int = 0) -> dict:
        body = {
            'query': {'searchType': 'SEARCH_TYPE_RU', 'queryText': query, 'page': str(page)},
            'docsOnPage': str(DOCS_ON_PAGE),
            'folderId': self.folder_id,
        }
        if orientation:
            body['imageSpec'] = {'orientation': _ORIENTATION_API[orientation]}
        if site:
            body['site'] = site
        return body

    def search(self, query: str, orientation: Optional[str] = None, site: Optional[str] = None,
               page: int = 0) -> List[dict]:
        try:
            resp = self.session.post(SEARCH_URL, json=self.body(query, orientation, site, page),
                                     headers={'Authorization': 'Api-Key ' + self.api_key},
                                     timeout=self.timeout)
        except requests.RequestException as e:
            raise ImageSearchFailed(f'Яндекс не ответил: {e.__class__.__name__}') from None
        try:
            payload = resp.json()
        except ValueError:
            payload = None
        if resp.status_code != 200:
            detail = payload.get('message') if isinstance(payload, dict) else (resp.text or '')[:200]
            raise ImageSearchFailed(f'Яндекс ответил HTTP {resp.status_code}: {detail or ""}'.strip())
        raw_data = payload.get('rawData') if isinstance(payload, dict) else None
        if not isinstance(raw_data, str) or not raw_data:
            raise ImageSearchFailed('Яндекс прислал ответ без rawData')
        try:
            raw = base64.b64decode(raw_data)
        except (ValueError, TypeError):
            raise ImageSearchFailed('Яндекс прислал rawData не в base64') from None
        return parse_response_xml(raw)


# ---------------------------------------------------------------- скачивание

def _bad_chars(text: str) -> bool:
    """Пробелы, управляющие символы и обратная косая черта в адресе."""
    return any(ord(ch) <= 32 or ord(ch) == 127 or ch == '\\' for ch in text)


def _ascii_host(host: str) -> str:
    """Имя хоста латиницей: нелатинский домен (пиво.рф) — в punycode (IDNA, UTS 46). Одно и то же
    значение потом идёт и в DNS, и в TLS (SNI, проверка сертификата), и в заголовок Host."""
    if host.isascii():
        return host
    try:
        import idna
        return idna.encode(host, uts46=True).decode('ascii')
    except Exception:  # noqa: BLE001 — пакета нет или имя не кодируется
        try:
            return host.encode('idna').decode('ascii')
        except UnicodeError:
            raise ImageDownloadFailed('Адрес картинки: домен не переводится в латиницу') from None


def _target(url) -> Tuple[str, str, int, str, str]:
    """Проверить адрес и разобрать ОДИН раз (п. 6 докстроки) -> (схема, хост, порт,
    путь с запросом, заголовок Host). Соединение строится только из этих частей."""
    if not isinstance(url, str) or not url or len(url) > URL_MAX or _bad_chars(url):
        raise ImageDownloadFailed('Адрес картинки с недопустимыми символами')
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise ImageDownloadFailed('Адрес картинки не разбирается') from None
    scheme = parts.scheme.lower()
    if scheme not in ('http', 'https'):
        raise ImageDownloadFailed('Адрес картинки не http(s)')
    if not parts.netloc or '@' in parts.netloc:
        raise ImageDownloadFailed('Адрес картинки с данными входа (user@host) не принимается')
    host = (parts.hostname or '').lower()
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is None:
        host = _ascii_host(host).lower()
        if not _HOST_RE.match(host):
            raise ImageDownloadFailed('Адрес картинки: недопустимые символы в домене')
    default_port = 443 if scheme == 'https' else 80
    port = port or default_port
    path = quote(parts.path or '/', safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="/%:@!$&'()*+,;=-._~?")
    target = path + ('?' + query if query else '')
    shown = '[' + host + ']' if literal is not None and literal.version == 6 else host
    host_header = shown if port == default_port else f'{shown}:{port}'
    return scheme, host, port, target, host_header


# IPv6-адреса, внутри которых IPv4 (6to4, NAT64, старый «IPv4-совместимый»), и Teredo: в Python
# 3.10 is_global считает их публичными, а маршрут к ним может вести во внутреннюю сеть.
_IPV6_TUNNELS = tuple(ipaddress.ip_network(net) for net in
                      ('2002::/16', '64:ff9b::/96', '64:ff9b:1::/48', '::/96', '2001::/32'))


def _public_ip(host: str, port: int, resolver: Callable) -> str:
    """Разрешить имя ОДИН раз; все адреса — публичные (ipaddress.is_global), иначе отказ.
    -> IP для соединения (первый IPv4, если есть)."""
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = resolver(host, port)
        except (OSError, UnicodeError):
            infos = []
        addresses = []
        for info in infos or []:
            try:
                addresses.append(ipaddress.ip_address(str(info[4][0]).split('%')[0]))
            except (ValueError, IndexError, TypeError):
                raise ImageDownloadFailed('Адрес картинки не разрешается') from None
    if not addresses:
        raise ImageDownloadFailed('Адрес картинки не разрешается')
    checked = []
    for ip in addresses:
        mapped = getattr(ip, 'ipv4_mapped', None)
        real = mapped if mapped is not None else ip
        tunnel = real.version == 6 and any(real in net for net in _IPV6_TUNNELS)
        if tunnel or not real.is_global or real.is_multicast:
            raise ImageDownloadFailed('Адрес картинки ведёт во внутреннюю сеть')
        checked.append(real)
    v4 = [ip for ip in checked if ip.version == 4]
    return str((v4 or checked)[0])


def _ca_bundle() -> str:
    """Корневые сертификаты — как у requests: REQUESTS_CA_BUNDLE / CURL_CA_BUNDLE, иначе certifi."""
    return os.environ.get('REQUESTS_CA_BUNDLE') or os.environ.get('CURL_CA_BUNDLE') or requests.certs.where()


class _Watchdog:
    """Сторож общего срока: по истечении закрывает сокет — блокирующее чтение заголовков или
    тела сразу обрывается. Таймаут сокета (READ_TIMEOUT_S) этого не даёт: он заново
    отсчитывается после каждого байта, и сайт, отдающий по байту в 4 секунды, держал бы
    поток часами."""

    def __init__(self, seconds: float):
        self.fired = False
        self._sock = None
        self._lock = threading.Lock()
        self._timer = threading.Timer(max(0.05, seconds), self._fire)
        self._timer.daemon = True
        self._timer.start()

    def attach(self, sock) -> None:
        with self._lock:
            self._sock = sock
            fired = self.fired
        if fired:
            self._kill(sock)

    def _fire(self) -> None:
        with self._lock:
            self.fired = True
            sock = self._sock
        if sock is not None:
            self._kill(sock)

    @staticmethod
    def _kill(sock) -> None:
        for action in (lambda: sock.shutdown(socket.SHUT_RDWR), sock.close):
            try:
                action()
            except OSError:
                pass

    def cancel(self) -> None:
        self._timer.cancel()


class _PinnedResponse:
    """Ответ http.client в виде, который читает fetch_image (его же отдают поддельные сайты в тестах)."""

    def __init__(self, conn, resp, watchdog: _Watchdog):
        self.status = resp.status
        self.headers = {str(k).lower(): str(v) for k, v in resp.getheaders()}
        self._conn = conn
        self._resp = resp
        self._watchdog = watchdog

    def iter_chunks(self, size: int):
        while True:
            try:
                chunk = self._resp.read1(size)    # не ждёт, пока наберётся весь кусок
            except (OSError, ValueError):
                if self._watchdog.fired:
                    raise TimeoutError('срок скачивания вышел') from None
                raise
            if not chunk:
                if self._watchdog.fired:          # сторож закрыл сокет — это не конец файла
                    raise TimeoutError('срок скачивания вышел')
                return
            yield chunk

    def close(self):
        self._watchdog.cancel()
        for action in (self._resp.close, self._conn.close):
            try:
                action()
            except Exception:  # noqa: BLE001 — закрытие best-effort
                pass


def _open_pinned(scheme: str, ip: str, port: int, host: str, target: str, headers: dict,
                 timeout_s: float = DOWNLOAD_DEADLINE_S) -> _PinnedResponse:
    """GET на проверенный IP (п. 6 докстроки): сокет открываем сами (socket.create_connection
    на ip), TLS — с проверкой сертификата по имени хоста (SNI и check_hostname), заголовок
    Host — из разбора адреса. Без переадресаций, повторов и распаковки. Сторож закрывает
    сокет через timeout_s секунд, что бы ни делал сайт; отменяется в close() ответа."""
    import http.client
    import ssl
    watchdog = _Watchdog(timeout_s)
    sock = conn = None
    try:
        sock = socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT_S)
        watchdog.attach(sock)
        sock.settimeout(READ_TIMEOUT_S)
        if scheme == 'https':
            context = ssl.create_default_context(cafile=_ca_bundle())
            sock = context.wrap_socket(sock, server_hostname=host, do_handshake_on_connect=False)
            watchdog.attach(sock)
            sock.do_handshake()
        conn = http.client.HTTPConnection(ip, port, timeout=READ_TIMEOUT_S)
        conn.sock = sock                          # соединение уже есть: http.client его не открывает
        conn.putrequest('GET', target, skip_host=True, skip_accept_encoding=True)
        for name, value in headers.items():
            conn.putheader(name, value)
        conn.endheaders()
        resp = conn.getresponse()
    except Exception:
        watchdog.cancel()
        for closable in (conn, sock):
            if closable is not None:
                try:
                    closable.close()
                except Exception:  # noqa: BLE001
                    pass
        raise
    return _PinnedResponse(conn, resp, watchdog)


def _header_value(text: str) -> str:
    """Значение заголовка: без управляющих символов, не-латинское — в %-кодировке."""
    if not text or _bad_chars(text.replace(' ', '%20')):
        return ''
    return quote(text, safe="/%:@!$&'()*+,;=-._~?#[]")


def fetch_image(url: str, referer: Optional[str] = None, max_bytes: int = DOWNLOAD_MAX_BYTES,
                deadline_s: float = DOWNLOAD_DEADLINE_S, resolver: Callable = socket.getaddrinfo,
                opener: Optional[Callable] = None, clock: Callable[[], float] = time.monotonic) -> bytes:
    """Скачать картинку по адресу из выдачи (п. 6 докстроки) -> байты; иначе ImageDownloadFailed.
    resolver, opener и clock — точки подмены для тестов (сеть тесты не трогают)."""
    opener = opener or _open_pinned
    deadline = clock() + deadline_s
    headers = {'User-Agent': USER_AGENT, 'Accept': IMAGE_ACCEPT, 'Accept-Encoding': 'identity'}
    ref = _header_value(referer or '')
    if ref:
        headers['Referer'] = ref
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        if clock() > deadline:
            raise ImageDownloadFailed('Сайт отвечает слишком долго')
        scheme, host, port, target, host_header = _target(current)
        ip = _public_ip(host, port, resolver)
        try:
            resp = opener(scheme, ip, port, host, target, dict(headers, Host=host_header),
                          max(0.05, deadline - clock()))
        except ImageDownloadFailed:
            raise
        except Exception:  # noqa: BLE001 — сетевые ошибки ssl/сокета: одна причина для агента
            if clock() > deadline:
                raise ImageDownloadFailed('Сайт отвечает слишком долго') from None
            raise ImageDownloadFailed('Сайт не отдал картинку (нет соединения)') from None
        try:
            if resp.status in REDIRECT_CODES:
                location = resp.headers.get('location') or ''
                if not location:
                    raise ImageDownloadFailed('Сайт переадресовал без адреса')
                current = urljoin(current, location)
                continue
            if resp.status != 200:
                raise ImageDownloadFailed(f'Сайт не отдал картинку: HTTP {resp.status}')
            declared = resp.headers.get('content-length') or ''
            if declared.isdigit() and int(declared) > max_bytes:
                raise ImageDownloadFailed(f'Картинка больше {max_bytes // (1024 * 1024)} МБ')
            chunks, total = [], 0
            for chunk in resp.iter_chunks(64 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ImageDownloadFailed(f'Картинка больше {max_bytes // (1024 * 1024)} МБ')
                if clock() > deadline:
                    raise ImageDownloadFailed('Сайт отдаёт картинку слишком медленно')
                chunks.append(chunk)
            data = b''.join(chunks)
            if not data:
                raise ImageDownloadFailed('Сайт отдал пустой ответ')
            if declared.isdigit() and len(data) < int(declared):
                raise ImageDownloadFailed('Сайт оборвал передачу')
            return data
        except ImageDownloadFailed:
            raise
        except Exception:  # noqa: BLE001 — обрыв посреди чтения (в том числе сторожем срока)
            if clock() > deadline:
                raise ImageDownloadFailed('Сайт отдаёт картинку слишком медленно') from None
            raise ImageDownloadFailed('Сайт оборвал передачу') from None
        finally:
            resp.close()
    raise ImageDownloadFailed(f'Больше {MAX_REDIRECTS} переадресаций')


# ---------------------------------------------------------------- подготовка картинки

def _open_image(data: bytes, jpeg_max: int, other_max: int):
    """Pillow-картинка из байтов: только ALLOWED_FORMATS, пиксели — ДО распаковки."""
    from PIL import Image
    try:
        image = Image.open(io.BytesIO(data), formats=ALLOWED_FORMATS)
    except Exception:  # noqa: BLE001 — любой сбой разбора = «не картинка»
        raise ImageDownloadFailed('По адресу не картинка (или формат не JPEG, PNG, WEBP, GIF)') from None
    width, height = image.size
    limit = jpeg_max if image.format == 'JPEG' else other_max
    if width * height > limit:
        raise ImageDownloadFailed(f'Картинка слишком большая ({width}x{height}) — выберите другую')
    return image


def _orientation(image) -> int:
    try:
        return int(image.getexif().get(0x0112) or 1)
    except Exception:  # noqa: BLE001 — битый EXIF — без поворота
        return 1


def _orient(image, orientation: int):
    """Поворот по тегу EXIF Orientation (то же, что ImageOps.exif_transpose)."""
    from PIL import Image
    ops = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
           4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
           6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE, 8: Image.Transpose.ROTATE_90}
    op = ops.get(orientation)
    return image.transpose(op) if op is not None else image


def _to_rgb(image):
    """RGB; прозрачность — на белый фон."""
    from PIL import Image
    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
        rgba = image.convert('RGBA')
        background = Image.new('RGB', rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel('A'))
        return background
    if image.mode == 'RGB':
        image.load()
        return image                       # без лишней копии
    return image.convert('RGB')


def _draft(image, longest: int) -> None:
    """JPEG: распаковать сразу уменьшенным — рамка по пропорциям картинки, чтобы большая
    сторона после draft была не меньше longest (п. 7 докстроки). Не JPEG — ничего."""
    if image.format != 'JPEG':
        return
    width, height = image.size
    scale = longest / max(width, height)
    if scale < 1:
        image.draft('RGB', (math.ceil(width * scale), math.ceil(height * scale)))


def prepare_image(data: bytes) -> Tuple[bytes, int, int]:
    """Байты картинки -> (JPEG для Telegram, ширина, высота) по п. 7 докстроки."""
    from PIL import Image
    with _DECODE:
        image = _open_image(data, JPEG_MAX_PIXELS, OTHER_MAX_PIXELS)
        width, height = image.size
        if max(width, height) < ATTACH_MIN_LONG_SIDE:
            raise ImageDownloadFailed(f'Картинка мелкая ({width}x{height}): нужна большая сторона от '
                                      f'{ATTACH_MIN_LONG_SIDE} px — выберите другую')
        if max(width, height) > MAX_ASPECT * min(width, height):
            raise ImageDownloadFailed(f'Картинка слишком вытянутая ({width}x{height}) — Telegram её не примет')
        orientation = _orientation(image)
        try:
            image.seek(0)
            _draft(image, MAX_SIDE)                       # JPEG распаковывается сразу уменьшенным
            image = _to_rgb(image)
            if max(image.size) > MAX_SIDE:
                image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
            image = _orient(image, orientation)
        except Exception:  # noqa: BLE001 — битый файл
            raise ImageDownloadFailed('Картинка битая — не читается') from None
        quality = JPEG_QUALITY
        while True:
            out = io.BytesIO()
            image.save(out, 'JPEG', quality=quality, optimize=True, progressive=True)
            payload = out.getvalue()
            if len(payload) <= TELEGRAM_PHOTO_MAX_BYTES or quality <= 48:
                break
            quality -= 10
        if len(payload) > TELEGRAM_PHOTO_MAX_BYTES:
            raise ImageDownloadFailed('Картинка не ужимается до 10 МБ — выберите другую')
        return payload, image.size[0], image.size[1]


def _preview_cell(data: bytes):
    """Превью для ячейки коллажа (или None, если байты — не картинка или заглушка)."""
    from PIL import Image
    try:
        with _DECODE:
            image = _open_image(data, JPEG_MAX_PIXELS, PREVIEW_OTHER_MAX_PIXELS)
            if min(image.size) < PREVIEW_MIN_SIDE:
                return None                 # заглушка «нет картинки» или пиксель-счётчик
            orientation = _orientation(image)
            image.seek(0)
            _draft(image, COLLAGE_CELL)
            image = _to_rgb(image)
            image.thumbnail((COLLAGE_CELL, COLLAGE_CELL), Image.LANCZOS)
            return _orient(image, orientation)
    except Exception:  # noqa: BLE001 — нет превью — серая ячейка
        return None


def _font(size: int):
    from PIL import ImageFont
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                 '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
                 '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:            # Pillow < 10.1: размер не задаётся
        return ImageFont.load_default()


def _ascii(text: str) -> str:
    return text.encode('ascii', 'replace').decode('ascii')


def render_collage(cells: List[Tuple[int, Optional[object], str]]) -> bytes:
    """[(номер, превью или None, подпись)] -> JPEG коллажа не больше COLLAGE_MAX_BYTES."""
    from PIL import Image, ImageDraw
    count = max(1, len(cells))
    rows = (count + COLLAGE_COLUMNS - 1) // COLLAGE_COLUMNS
    cell_w, cell_h = COLLAGE_CELL + 10, COLLAGE_CELL + COLLAGE_LABEL + 10
    sheet = Image.new('RGB', (COLLAGE_COLUMNS * cell_w, rows * cell_h), (235, 235, 235))
    draw = ImageDraw.Draw(sheet)
    big, small = _font(24), _font(15)
    for index, (number, preview, caption) in enumerate(cells):
        x0 = (index % COLLAGE_COLUMNS) * cell_w + 5
        y0 = (index // COLLAGE_COLUMNS) * cell_h + 5
        draw.rectangle([x0, y0, x0 + COLLAGE_CELL, y0 + COLLAGE_LABEL - 2], fill=(20, 20, 20))
        draw.text((x0 + 6, y0 + 3), str(number), fill=(255, 210, 0), font=big)
        draw.text((x0 + 46, y0 + 9), _ascii(caption)[:34], fill=(255, 255, 255), font=small)
        top = y0 + COLLAGE_LABEL
        if preview is None:
            draw.rectangle([x0, top, x0 + COLLAGE_CELL, top + COLLAGE_CELL], fill=(190, 190, 190))
            draw.text((x0 + 95, top + 140), 'no preview', fill=(80, 80, 80), font=small)
            continue
        px = x0 + (COLLAGE_CELL - preview.width) // 2
        py = top + (COLLAGE_CELL - preview.height) // 2
        sheet.paste(preview, (px, py))
    quality = 82
    while True:
        out = io.BytesIO()
        sheet.save(out, 'JPEG', quality=quality, optimize=True)
        data = out.getvalue()
        if len(data) <= COLLAGE_MAX_BYTES or quality <= 40:
            return data
        quality -= 10


# ---------------------------------------------------------------- хранилище поисков

class SearchStore:
    """Результаты поисков на диске (п. 3 докстроки). directory и now_fn — для тестов."""

    def __init__(self, directory: Optional[str] = None, now_fn: Callable[[], datetime] = msk_time.now):
        self.directory = os.path.abspath(directory or get_data_path(STORE_DIR_NAME))
        self.now_fn = now_fn

    def _day(self) -> str:
        return self.now_fn().strftime('%Y%m%d')

    def _path(self, search_id: str, suffix: str) -> str:
        if not SEARCH_ID_RE.match(str(search_id or '')):
            raise ImageSearchNotFound('Поиск не найден')
        return os.path.join(self.directory, search_id + suffix)

    def new_id(self) -> str:
        return 'is_' + self._day() + '_' + secrets.token_hex(6)

    def save(self, search_id: str, record: dict) -> None:
        os.makedirs(self.directory, exist_ok=True)
        atomic_write_json(self._path(search_id, '.json'), record)

    def delete(self, search_id: str) -> None:
        for suffix in ('.json', '.jpg'):
            try:
                os.unlink(self._path(search_id, suffix))
            except OSError:
                pass

    def _read(self, path: str) -> Optional[dict]:
        try:
            with open(path, encoding='utf-8') as f:
                record = json.load(f)
        except (OSError, ValueError):
            return None
        return record if isinstance(record, dict) else None

    def load(self, search_id: str) -> dict:
        record = self._read(self._path(search_id, '.json'))
        if record is None:
            raise ImageSearchNotFound(f'Поиск не найден или устарел (хранится {KEEP_DAYS} сут.) — '
                                      'повторите поиск')
        if not isinstance(record.get('candidates'), list):
            raise ImageSearchNotFound('Поиск не найден — повторите поиск')
        return record

    def collage_path(self, search_id: str) -> str:
        return self._path(search_id, '.jpg')

    def read_collage(self, search_id: str) -> Optional[bytes]:
        """Кэш коллажа: только целый JPEG (не пустой, с сигнатурой), иначе None."""
        try:
            with open(self.collage_path(search_id), 'rb') as f:
                data = f.read()
        except OSError:
            return None
        return data if data[:3] == b'\xff\xd8\xff' else None

    def write_collage(self, search_id: str, data: bytes) -> None:
        """Кэш коллажа через уникальный временный файл и os.replace (best-effort)."""
        path = self._path(search_id, '.jpg')
        tmp_path = None
        try:
            os.makedirs(self.directory, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(prefix=search_id + '.', suffix='.tmp', dir=self.directory)
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            os.replace(tmp_path, path)
            tmp_path = None
        except OSError:
            pass                                    # кэш не обязателен
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _names(self) -> List[str]:
        try:
            return os.listdir(self.directory)
        except OSError:
            return []

    def count_today(self, caller: Optional[str] = None) -> Tuple[int, int]:
        """(поисков за сутки по Москве, из них — этого caller). Брони «pending» считаются."""
        prefix = 'is_' + self._day() + '_'
        total = mine = 0
        for name in self._names():
            if not (name.startswith(prefix) and name.endswith('.json')):
                continue
            total += 1
            if caller:
                record = self._read(os.path.join(self.directory, name))
                if record is not None and record.get('caller') == caller:
                    mine += 1
        return total, mine

    def cleanup(self) -> int:
        """Удалить поиски старше KEEP_DAYS суток и брошенные *.tmp старше TMP_KEEP_S -> сколько удалено."""
        border = (self.now_fn() - timedelta(days=KEEP_DAYS)).strftime('%Y%m%d')
        removed = 0
        now = time.time()
        for name in self._names():
            path = os.path.join(self.directory, name)
            match = _STORE_FILE_RE.match(name)
            stale_tmp = name.startswith('is_') and name.endswith('.tmp')
            if stale_tmp:
                try:
                    stale_tmp = now - os.path.getmtime(path) > TMP_KEEP_S
                except OSError:
                    stale_tmp = False
            if (match and match.group(1) < border) or stale_tmp:
                try:
                    os.unlink(path)
                    removed += 1
                except OSError:
                    pass
        return removed


# ---------------------------------------------------------------- поиск целиком

class ImageFinder:
    """Поиск, коллаж и скачивание варианта. client=None — ключ не настроен (поиск — 503,
    коллаж и скачивание уже найденного работают). fetch(url, referer, max_bytes, deadline_s)
    -> bytes; clock — монотонные часы (для бюджета коллажа)."""

    def __init__(self, client: Optional[YandexImageClient], store: SearchStore,
                 fetch: Callable[..., bytes] = fetch_image, daily_limit: int = DAILY_LIMIT,
                 caller_limit: int = PER_CALLER_DAILY_LIMIT, clock: Callable[[], float] = time.monotonic):
        self.client = client
        self.store = store
        self.fetch = fetch
        self.daily_limit = daily_limit
        self.caller_limit = caller_limit
        self.clock = clock

    def search(self, query, orientation=None, site=None, page=None, caller: Optional[str] = None) -> dict:
        query = clean_query(query)
        orientation = clean_orientation(orientation)
        site = clean_site(site)
        page = clean_page(page)
        if self.client is None:
            raise ImageSearchNotConfigured(
                f'Поиск картинок не настроен: на сервере нет {ENV_API_KEY} и {ENV_FOLDER_ID} '
                '(Yandex Search API) — их задаёт владелец')
        caller = str(caller or '')[:120]
        self.store.cleanup()
        search_id = self.store.new_id()
        created_at = self.store.now_fn().strftime('%Y-%m-%dT%H:%M')
        # Бронь места до запроса (п. 4 докстроки): файл есть — значит, поиск посчитан.
        self.store.save(search_id, {'search_id': search_id, 'status': 'pending', 'caller': caller,
                                    'created_at': created_at, 'candidates': []})
        try:
            total, mine = self.store.count_today(caller)
            if total > self.daily_limit:
                raise ImageSearchLimit(f'Сегодня уже {total - 1} поисков — предел {self.daily_limit} в сутки на '
                                       'всю сеть (запрос в Яндекс платный). Продолжите завтра.')
            if caller and mine > self.caller_limit:
                raise ImageSearchLimit(f'Этот агент сегодня уже сделал {mine - 1} поисков — предел '
                                       f'{self.caller_limit} в сутки на одно подключение. Продолжите завтра.')
            docs = self.client.search(query, orientation=orientation, site=site, page=page)
        except Exception:
            self.store.delete(search_id)
            raise
        picked, dropped = pick_candidates(docs)
        candidates = [dict(doc, n=number, candidate=f'{search_id}-{number}')
                      for number, doc in enumerate(picked, start=1)]
        record = {'search_id': search_id, 'status': 'done', 'caller': caller, 'query': query,
                  'orientation': orientation, 'site': site, 'page': page, 'found': len(docs), 'dropped': dropped,
                  'created_at': created_at, 'candidates': candidates}
        self.store.save(search_id, record)
        return self.public_view(record, total)

    def public_view(self, record: dict, searches_today: Optional[int] = None) -> dict:
        """Ответ API: без служебных адресов превью и без caller."""
        view = {key: record.get(key) for key in ('search_id', 'query', 'orientation', 'site', 'page', 'found',
                                                 'dropped', 'created_at')}
        view['candidates'] = [{key: item.get(key) for key in ('candidate', 'n', 'width', 'height', 'format',
                                                              'domain', 'title', 'page_url', 'image_url')}
                              for item in record.get('candidates') or []]
        view['collage'] = f'/api/content-plan/image-search/{record.get("search_id")}/collage'
        if searches_today is not None:
            view['searches_today'] = searches_today
            view['daily_limit'] = self.daily_limit
        return view

    def candidate(self, ref) -> Tuple[dict, dict]:
        """('<id поиска>-<n>') -> (запись поиска, вариант); нет — ImageSearchNotFound."""
        search_id, number = parse_candidate(ref)
        record = self.store.load(search_id)
        for item in record['candidates']:
            if item.get('n') == number:
                return record, item
        raise ImageSearchNotFound(f'В поиске {search_id} нет варианта {number} '
                                  f'(есть 1..{len(record["candidates"])})')

    def _preview(self, item: dict, deadline: float):
        """Превью варианта: миниатюра из ответа Яндекса, иначе сам оригинал, и лишь потом
        миниатюра по id (её адрес собран по образцу — может вернуть не ту картинку,
        поэтому она последняя). Каждая попытка — не дольше PREVIEW_DEADLINE_S и в бюджете
        коллажа; что не успело — None."""
        urls = (list(item.get('thumb_urls') or []) + [item.get('image_url')]
                + list(item.get('guessed_thumb_urls') or []))
        for url in urls:
            remaining = deadline - self.clock()
            if remaining <= 0.5:
                return None
            if not url:
                continue
            try:
                data = self.fetch(url, item.get('page_url') or None, PREVIEW_MAX_BYTES,
                                  min(PREVIEW_DEADLINE_S, remaining))
            except Exception:  # noqa: BLE001 — чужой сайт не роняет коллаж
                continue
            preview = _preview_cell(data)
            if preview is not None:
                return preview
        return None

    def collage(self, search_id: str) -> bytes:
        """JPEG коллажа вариантов (п. 5 докстроки)."""
        record = self.store.load(search_id)
        cached = self.store.read_collage(search_id)
        if cached:
            return cached
        items = record['candidates']
        deadline = self.clock() + COLLAGE_BUDGET_S
        pool = ThreadPoolExecutor(max_workers=PREVIEW_WORKERS)
        try:
            futures = [pool.submit(self._preview, item, deadline) for item in items]
            done, _late = wait(futures, timeout=max(0.0, deadline - self.clock()) + 1.0)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        previews = []
        for future in futures:
            try:
                previews.append(future.result(timeout=0) if future in done else None)
            except Exception:  # noqa: BLE001
                previews.append(None)
        cells = []
        for item, preview in zip(items, previews):
            size = f'{item.get("width")}x{item.get("height")}' if item.get('width') else '?'
            cells.append((item.get('n'), preview, size + '  ' + (item.get('domain') or '')))
        data = render_collage(cells)
        if items and all(preview is not None for preview in previews):
            self.store.write_collage(search_id, data)
        return data

    def download(self, ref) -> Tuple[bytes, dict]:
        """Вариант -> (JPEG для материала, сведения об источнике для media[].source)."""
        record, item = self.candidate(ref)
        data = self.fetch(item['image_url'], item.get('page_url') or None, DOWNLOAD_MAX_BYTES,
                          DOWNLOAD_DEADLINE_S)
        payload, width, height = prepare_image(data)
        source = {'image_url': item['image_url'], 'page_url': item.get('page_url') or '',
                  'domain': item.get('domain') or _host_of(item['image_url']), 'title': item.get('title') or '',
                  'query': record.get('query') or '', 'candidate': item.get('candidate'),
                  'width': width, 'height': height}
        return payload, source


def get_finder() -> ImageFinder:
    """Поиск с настройками из окружения и хранилищем на постоянном диске."""
    key, folder = settings_from_env()
    client = YandexImageClient(key, folder) if key and folder else None
    return ImageFinder(client, SearchStore())
