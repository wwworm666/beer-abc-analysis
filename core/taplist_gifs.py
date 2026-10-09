"""
Гифки к таплисту: набор, выбор гифки на пост, ссылка на файл и file_id Telegram.

## Что это

Решение владельца 2026-10-09: «к каждому таплисту прикрепляем рандомную гифку из
списка». Набор — `resources/taplist_post_gifs.json` (25 гифок владельца с Tenor:
фильм или сериал, страница гифки, что на ней). Пост таплиста в Telegram-канале бара
уходит с гифкой (core/content_publisher.py), предпросмотр показывает, какая гифка
уйдёт (core/content_plan.render_live, поле `gif`).

## Файлы

| Файл | Роль |
|------|------|
| `core/taplist_gifs.py` | этот модуль: набор, выбор, ссылка на файл, кэш |
| `resources/taplist_post_gifs.json` | набор гифок (меняется деплоем) |
| `core/content_plan.py` | render_live: какая гифка у поста (`gif`) |
| `core/content_publisher.py` | отправка поста с гифкой |
| `tests/test_taplist_gifs.py` | тесты |

Кэш на постоянном томе — `taplist_gifs.json` (core/storage_paths): найденные ссылки
на файлы и file_id Telegram. Потеря файла ничего не ломает: ссылки найдутся заново.

## Как работает

### Какая гифка у поста (gif_index)

Не бросок монеты, а правило — чтобы предпросмотр показывал ту же гифку, что уйдёт:

    неделя = (день поста − 5 января 2026) // 7          (понедельник, как у фраз)
    шаг    = первое число от 7, взаимно простое с размером набора (25 -> 7)
    сдвиг  = позиция бара (bar1..bar4 -> 0..3) × (размер набора // 4)
    номер  = (неделя × шаг + сдвиг) mod размер набора

Шаг взаимно прост с размером набора, поэтому в своём баре гифка повторится только
через столько недель, сколько гифок в наборе (25), а соседние недели не идут подряд
по списку — выглядит случайно. Сдвиг на четверть набора даёт четырём барам в одну
пятницу разные гифки (при наборе не меньше четырёх). Пример: пятница 9 октября 2026 —
неделя 39; у bar1 номер (39 × 7) mod 25 = 23 (24-я гифка), у bar2 — (273 + 6) mod 25 = 4.

### Ссылка на файл (GifSource.media_url)

Telegram принимает гифку ссылкой на сам файл, а в наборе — страницы Tenor. Сервер
находит файл один раз и запоминает в кэше:
1. страница гифки: мета-теги og:video (mp4) и og:image (gif) — первый подходящий
   адрес на media*.tenor.com;
2. не вышло — адрес страницы с «.gif» на конце: Tenor отвечает переадресацией на файл.
Другие адреса не берутся (только https://media*.tenor.com/….mp4|.gif). Не нашлось —
None: публикация пробует отдать Telegram адрес «страница.gif», иначе выходит без гифки.

### file_id

После первой отправки Telegram возвращает file_id гифки — дальше она уходит по нему,
без Tenor. file_id у каждого бота свой: ключ — отпечаток токена (первые 16 знаков
sha256, как core/content_channels.token_hash).

## Changelog

- 2026-10-09 — модуль создан: 25 гифок владельца, выбор по неделе и бару, ссылка на
  файл со страницы Tenor, кэш ссылок и file_id.
"""

import hashlib
import json
import math
import os
import re
import threading
from datetime import date
from functools import lru_cache
from html import unescape
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

GIFS_PATH = Path(__file__).resolve().parents[1] / 'resources/taplist_post_gifs.json'
CACHE_FILE_NAME = 'taplist_gifs.json'
# Понедельник: недели считаются так же, как у фраз таплиста (taplist_post.PHRASE_EPOCH).
GIF_EPOCH = date(2026, 1, 5)
GIF_BARS = ('bar1', 'bar2', 'bar3', 'bar4')
# Наименьший шаг по неделям: соседние недели не идут подряд по списку.
STRIDE_MIN = 7
PAGE_RE = re.compile(r'^https://tenor\.com/view/[a-z0-9-]+-\d+$')
MEDIA_RE = re.compile(r'^https://media\d*\.tenor\.com/[^\s"\'<>?#]+\.(?:mp4|gif)$')
# Мета-теги страницы Tenor по порядку предпочтения: mp4 легче gif в десятки раз.
MEDIA_META = ('og:video:secure_url', 'og:video', 'og:video:url', 'og:image', 'og:image:secure_url',
              'twitter:image')
# Таймауты запроса к Tenor (соединение, ответ), с: публикация ждёт не дольше.
FETCH_TIMEOUT = (4, 8)
# Больше страницы не читаем: мета-теги — в начале документа.
PAGE_MAX_BYTES = 2 * 1024 * 1024
USER_AGENT = 'Mozilla/5.0 (compatible; KulturaBot/1.0; +https://beerkultura.ru)'


# ---------------------------------------------------------------------------
# Набор и выбор
# ---------------------------------------------------------------------------

def load_gifs(path=None) -> Tuple[dict, ...]:
    """Гифки из resources/taplist_post_gifs.json по порядку: ({title, page, note}, ...).
    Файл в репозитории и меняется только деплоем — читается один раз на путь.
    Пустой набор, гифка без названия, страница не Tenor или повтор страницы —
    ValueError (тест набора ловит это до деплоя)."""
    return _load_gifs(str(path or GIFS_PATH))


@lru_cache(maxsize=4)
def _load_gifs(path: str) -> Tuple[dict, ...]:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    gifs, seen = [], set()
    for item in data.get('gifs') or []:
        title = str(item.get('title') or '').strip()
        page = str(item.get('page') or '').strip()
        if not title or not PAGE_RE.match(page) or page in seen:
            raise ValueError(f'{path}: у гифки нужно название и своя страница Tenor ({title or page})')
        seen.add(page)
        gifs.append({'title': title, 'page': page, 'note': str(item.get('note') or '').strip()})
    if not gifs:
        raise ValueError(f'{path}: нужна хотя бы одна гифка')
    return tuple(gifs)


def stride(total: int) -> int:
    """Шаг по неделям: первое число от STRIDE_MIN, взаимно простое с total (25 -> 7).
    Набор меньше шага — 1 (подряд по списку)."""
    for step in range(STRIDE_MIN, total):
        if math.gcd(step, total) == 1:
            return step
    return 1


def gif_index(day: date, bar_id: str, total: int) -> int:
    """Номер гифки (с нуля) для поста бара в этот день — правило в докстроке модуля.
    Бар не из GIF_BARS — без сдвига."""
    week = (day - GIF_EPOCH).days // 7
    position = GIF_BARS.index(bar_id) if bar_id in GIF_BARS else 0
    return (week * stride(total) + position * max(1, total // len(GIF_BARS))) % total


def gif_for(day: date, bar_id: str, gifs=None) -> dict:
    """Гифка поста: {number (с единицы), total, title, page, note}."""
    gifs = load_gifs() if gifs is None else gifs
    index = gif_index(day, bar_id, len(gifs))
    item = gifs[index]
    return {'number': index + 1, 'total': len(gifs), 'title': item['title'], 'page': item['page'],
            'note': item.get('note') or ''}


# ---------------------------------------------------------------------------
# Ссылка на файл
# ---------------------------------------------------------------------------

_META_RE = re.compile(r'<meta\b[^>]*>', re.IGNORECASE)
_ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')


def parse_media_url(page_html: str) -> Optional[str]:
    """Адрес файла гифки из мета-тегов страницы Tenor (порядок — MEDIA_META) или None.
    Берётся только https://media*.tenor.com/….mp4|.gif."""
    meta: Dict[str, str] = {}
    for tag in _META_RE.findall(page_html or ''):
        attrs = {name.lower(): unescape(a if a else b) for name, a, b in _ATTR_RE.findall(tag)}
        key = (attrs.get('property') or attrs.get('name') or '').strip().lower()
        if key and 'content' in attrs and key not in meta:
            meta[key] = attrs['content'].strip()
    for key in MEDIA_META:
        url = meta.get(key, '')
        if MEDIA_RE.match(url):
            return url
    return None


def token_hash(token: Optional[str]) -> str:
    """Отпечаток токена бота (как core/content_channels.token_hash)."""
    return hashlib.sha256((token or '').encode('utf-8')).hexdigest()[:16]


def _default_get(url: str, **kwargs):
    import requests
    return requests.get(url, **kwargs)


class GifSource:
    """Ссылки на файлы гифок и file_id Telegram с кэшем на томе.

    cache_file — путь к кэшу (по умолчанию taplist_gifs.json на томе); http_get —
    функция как requests.get (тесты подменяют); now_fn — отметка времени для кэша."""

    def __init__(self, cache_file: Optional[str] = None, http_get: Optional[Callable] = None,
                 now_fn: Optional[Callable[[], str]] = None):
        if cache_file is None:
            from core.storage_paths import get_data_path
            cache_file = get_data_path(CACHE_FILE_NAME)
        self.cache_file = cache_file
        self.http_get = http_get or _default_get
        self.now_fn = now_fn or _now_stamp
        self._lock = threading.Lock()

    # -- кэш
    def _load(self) -> dict:
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        gifs = data.get('gifs') if isinstance(data, dict) else None
        return gifs if isinstance(gifs, dict) else {}

    def _update(self, page: str, change: Callable[[dict], None]) -> None:
        from core.json_store import atomic_write_json
        with self._lock:
            gifs = self._load()
            entry = gifs.get(page) if isinstance(gifs.get(page), dict) else {}
            change(entry)
            gifs[page] = entry
            try:
                atomic_write_json(self.cache_file, {'version': 1, 'gifs': gifs})
            except OSError as e:          # кэш — не данные: без него гифка найдётся заново
                print(f'[TAPLIST_GIFS] cache not saved: {e!r}')

    def file_id(self, page: str, token: Optional[str]) -> Optional[str]:
        entry = self._load().get(page) or {}
        ids = entry.get('file_ids') if isinstance(entry, dict) else None
        value = ids.get(token_hash(token)) if isinstance(ids, dict) else None
        return value if isinstance(value, str) and value else None

    def remember_file_id(self, page: str, token: Optional[str], file_id: str) -> None:
        def change(entry):
            ids = entry.get('file_ids') if isinstance(entry.get('file_ids'), dict) else {}
            ids[token_hash(token)] = file_id
            entry['file_ids'] = ids
        self._update(page, change)

    def forget_file_id(self, page: str, token: Optional[str]) -> None:
        """Telegram не принял file_id (бота сменили, файл удалён) — найти заново."""
        def change(entry):
            ids = entry.get('file_ids') if isinstance(entry.get('file_ids'), dict) else {}
            ids.pop(token_hash(token), None)
            entry['file_ids'] = ids
        self._update(page, change)

    def forget_media(self, page: str) -> None:
        """Telegram не скачал файл по ссылке — в следующий раз найти ссылку заново."""
        self._update(page, lambda entry: entry.pop('media', None))

    # -- поиск ссылки
    def media_url(self, page: str) -> Optional[str]:
        """Адрес файла гифки: из кэша, иначе со страницы Tenor (и в кэш). None — не нашлось."""
        entry = self._load().get(page) or {}
        cached = entry.get('media') if isinstance(entry, dict) else None
        if isinstance(cached, str) and MEDIA_RE.match(cached):
            return cached
        url = self._resolve(page)
        if url:
            stamp = self.now_fn()
            self._update(page, lambda e: e.update({'media': url, 'media_at': stamp}))
        return url

    def _resolve(self, page: str) -> Optional[str]:
        headers = {'User-Agent': USER_AGENT}
        try:
            resp = self.http_get(page, timeout=FETCH_TIMEOUT, headers=headers)
            if getattr(resp, 'status_code', 0) == 200:
                url = parse_media_url((resp.text or '')[:PAGE_MAX_BYTES])
                if url:
                    return url
        except Exception as e:  # noqa: BLE001 — нет Tenor: пробуем второй путь
            print(f'[TAPLIST_GIFS] page {page}: {e!r}')
        try:
            resp = self.http_get(page + '.gif', timeout=FETCH_TIMEOUT, headers=headers,
                                 allow_redirects=False, stream=True)
            try:
                location = (getattr(resp, 'headers', None) or {}).get('Location') or ''
            finally:
                close = getattr(resp, 'close', None)
                if callable(close):
                    close()
            if MEDIA_RE.match(location.strip()):
                return location.strip()
        except Exception as e:  # noqa: BLE001
            print(f'[TAPLIST_GIFS] redirect {page}.gif: {e!r}')
        return None


def _now_stamp() -> str:
    from core import msk_time
    return msk_time.now().strftime('%Y-%m-%dT%H:%M')


_default_source: Optional[GifSource] = None
_default_guard = threading.Lock()


def default_source() -> GifSource:
    """Источник по умолчанию на процесс (кэш на томе)."""
    global _default_source
    with _default_guard:
        if _default_source is None:
            _default_source = GifSource()
        return _default_source
