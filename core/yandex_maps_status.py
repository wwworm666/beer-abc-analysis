"""Что сейчас показывают Яндекс Карты в прайсе бара — и совпадает ли это с нашим файлом.

Источник — публичная страница организации, та же, что видит гость:
https://yandex.ru/maps/org/<id>/prices/. В неё Яндекс встраивает прайс целиком
(«fullObjects»: разделы, позиции с названием, ценой и фото) и два времени
(«relevance»): lastUploadTime — когда Яндекс скачал файл, lastUpdateTime — когда
опубликовал. Кабинет Яндекс Бизнеса не используется (он только с «ок» владельца).

Раз в 3 часа поток сверки скачивает страницы четырёх баров и хранит, что на
Картах (yml_maps_status.json). Сравнение с нашим файлом — при каждом открытии
/yandex, по текущему файлу бара. Правила — docs/yandex-feeds.md, раздел
«Сверка с Яндекс Картами».
"""
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import portalocker

from core.json_store import atomic_write_json
from core.storage_paths import get_data_path
# Заголовки браузера и признаки капчи — общие для страниц Карт (отзывы и прайс).
from core.yandex_maps_reviews import CAPTCHA_MARKERS as _CAPTCHA_MARKERS, HEADERS
from core.yandex_reviews_sync import BAR_BY_PERMANENT_ID

MOSCOW = ZoneInfo('Europe/Moscow')
MAPS_PRICES_URL = 'https://yandex.ru/maps/org/{org_id}/prices/'
# Ключ заведения (как в отзывах) -> bar1..bar4 (как в фидах и кранах).
VENUE_TO_BAR = {'bolshoy': 'bar1', 'ligovskiy': 'bar2', 'kremenchugskaya': 'bar3', 'varshavskaya': 'bar4'}
# Организация на Картах для фида бара. Соответствие подтверждено владельцем
# 2026-09-28 для отзывов (core/yandex_reviews_sync.BAR_BY_PERMANENT_ID).
ORG_BY_BAR = {VENUE_TO_BAR[venue]: org_id for org_id, venue in BAR_BY_PERMANENT_ID.items()
              if venue in VENUE_TO_BAR}
# Карты обновляют прайс за дни, а не минуты: чаще раза в 3 часа проверять незачем.
CHECK_EVERY = timedelta(hours=3)
# Кнопка «Проверить сейчас» не чаще раза в 2 минуты: ответ Карт не изменится.
MANUAL_MIN_INTERVAL = timedelta(minutes=2)
PAUSE_BETWEEN_BARS = 1.5

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_LOCK_PATH = os.path.join(_BASE_DIR, 'data', '.yml_maps_check.lock')
THREAD_LOCK_PATH = os.path.join(_BASE_DIR, 'data', '.yml_maps_thread.lock')
_decoder = json.JSONDecoder()
_started = False
_thread_lock = threading.Lock()
_lock_handle = None


class MapsCheckBusy(Exception):
    """Проверка уже идёт."""


class MapsPageError(Exception):
    """Страница Карт не разобралась (капча, другая разметка, нет связи)."""


def status_path() -> str:
    return get_data_path('yml_maps_status.json')


def maps_url(org_id) -> str:
    return MAPS_PRICES_URL.format(org_id=org_id)


def _now():
    return datetime.now(MOSCOW).replace(microsecond=0)


# ---------------------------------------------------------------- разбор страницы

def parse_prices_page(html: str) -> dict:
    """Прайс со страницы Карт. -> {items, count, last_upload, last_update, source}.

    items — [{title, price, category, photo}]; price — как на Картах (строка).
    Если в странице несколько блоков fullObjects, берётся самый полный.
    """
    if any(marker in html for marker in _CAPTCHA_MARKERS) and '"fullObjects"' not in html:
        raise MapsPageError('Яндекс показал проверку «я не робот», прайс не получен')
    best = None
    for match in re.finditer(r'"fullObjects":\{', html):
        try:
            data, _ = _decoder.raw_decode(html, match.start() + len('"fullObjects":'))
        except ValueError:
            continue
        categories = data.get('categories') if isinstance(data, dict) else None
        if not isinstance(categories, list):
            continue
        items = []
        for category in categories:
            for item in category.get('categoryItems') or []:
                if isinstance(item, dict) and item.get('title'):
                    items.append({'title': str(item['title']), 'price': str(item.get('price') or ''),
                                  'category': str(category.get('categoryName') or ''),
                                  'photo': bool(item.get('photoLink'))})
        if best is None or len(items) > len(best):
            best = items
    count = re.search(r'"fullObjectsCount":(\d+)', html)
    if best is None:
        if count and count.group(1) == '0':
            best = []
        else:
            raise MapsPageError('На странице Карт не найден прайс: Яндекс мог поменять разметку')
    relevance = {}
    found = re.search(r'"relevance":(\{[^{}]*\})', html)
    if found:
        try:
            relevance = json.loads(found.group(1))
        except ValueError:
            relevance = {}
    source = re.search(r'"source":\{"id":"([^"]*)","name":"([^"]*)"', html)
    return {
        'items': best,
        'count': int(count.group(1)) if count else len(best),
        'last_upload': relevance.get('lastUploadTime'),
        'last_update': relevance.get('lastUpdateTime'),
        'source': source.group(2) if source else None,
    }


def fetch_bar(bar_id, get=None) -> dict:
    """Скачать и разобрать страницу Карт бара. Ошибка — MapsPageError."""
    import requests
    get = get or requests.get
    org_id = ORG_BY_BAR.get(bar_id)
    if not org_id:
        raise MapsPageError('Для бара не указана организация на Картах')
    try:
        response = get(maps_url(org_id), headers=HEADERS, timeout=(10, 40))
    except Exception as error:
        raise MapsPageError(f'Карты не ответили ({type(error).__name__})') from None
    if response.status_code != 200:
        raise MapsPageError(f'Карты ответили кодом {response.status_code}')
    return parse_prices_page(response.text)


# ---------------------------------------------------------------- хранение

def load_status(path=None) -> dict:
    path = str(path or status_path())
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    bars = data.get('bars') if isinstance(data, dict) else None
    return bars if isinstance(bars, dict) else {}


def refresh(bars=None, get=None, path=None, manual=False, sleep=time.sleep) -> dict:
    """Проверить Карты по барам и сохранить. -> все сохранённые состояния.

    Неудача по бару не стирает прошлый удачный снимок: пишется error и время
    попытки, позиции остаются прежними (страница покажет, на когда они).
    manual=True — кнопка: если все бары проверены меньше 2 минут назад, повтора нет.
    """
    path = str(path or status_path())
    bars = [bar for bar in (bars or ORG_BY_BAR) if bar in ORG_BY_BAR]
    os.makedirs(os.path.dirname(RUN_LOCK_PATH), exist_ok=True)
    lock = portalocker.Lock(RUN_LOCK_PATH, timeout=0, fail_when_locked=True)
    try:
        lock.acquire()
    except portalocker.exceptions.LockException:
        raise MapsCheckBusy('Проверка Карт уже идёт') from None
    try:
        stored = load_status(path)
        now = _now()
        if manual and all(_fresh(stored.get(bar), now) for bar in bars):
            return stored
        for index, bar in enumerate(bars):
            if index:
                sleep(PAUSE_BETWEEN_BARS)
            previous = stored.get(bar) if isinstance(stored.get(bar), dict) else {}
            attempt = _now().isoformat()
            try:
                page = fetch_bar(bar, get=get)
                stored[bar] = {**page, 'org_id': ORG_BY_BAR[bar], 'checked_at': attempt, 'error': None,
                               'attempt_at': attempt}
            except MapsPageError as error:
                stored[bar] = {**previous, 'org_id': ORG_BY_BAR[bar], 'error': str(error), 'attempt_at': attempt}
            print(f'[YML-MAPS] {bar}: ' + (stored[bar]['error'] or
                                           f"{len(stored[bar]['items'])} позиций, опубликовано {stored[bar]['last_update']}"))
        atomic_write_json(path, {'bars': stored})
        return stored
    finally:
        lock.release()


def _fresh(state, now) -> bool:
    if not isinstance(state, dict) or not state.get('attempt_at'):
        return False
    try:
        return now - datetime.fromisoformat(state['attempt_at']) < MANUAL_MIN_INTERVAL
    except ValueError:
        return False


# ---------------------------------------------------------------- сравнение

def _key(title) -> str:
    return ' '.join(str(title or '').replace('ё', 'е').replace('Ё', 'Е').split()).casefold()


def _amount(price):
    """'1 350' / '1350.00' / '1350,5' -> Decimal; не число -> None."""
    text = re.sub(r'[^\d,.]', '', str(price or '')).replace(',', '.')
    try:
        return Decimal(text).quantize(Decimal('0.01')) if text else None
    except InvalidOperation:
        return None


def compare(ours, maps_items) -> dict:
    """Наш файл против Карт. ours / maps_items — [{title|name, price}].

    Сопоставление по названию без учёта регистра, лишних пробелов и «ё».
    -> {price: [{title, file, maps}], missing: [в файле, нет на Картах],
        extra: [на Картах, нет в файле], total: число расхождений}.
    """
    ours_map, maps_map = {}, {}
    for item in ours or []:
        ours_map.setdefault(_key(item.get('name') or item.get('title')), item)
    for item in maps_items or []:
        maps_map.setdefault(_key(item.get('title')), item)
    price = []
    for key, item in ours_map.items():
        other = maps_map.get(key)
        if other is not None and _amount(item.get('price')) != _amount(other.get('price')):
            price.append({'title': item.get('name') or item.get('title'),
                          'file': str(item.get('price') or ''), 'maps': str(other.get('price') or '')})
    missing = [item.get('name') or item.get('title') for key, item in ours_map.items() if key not in maps_map]
    extra = [item.get('title') for key, item in maps_map.items() if key not in ours_map]
    return {'price': price, 'missing': missing, 'extra': extra,
            'total': len(price) + len(missing) + len(extra)}


def _parse_time(value):
    """'2026-09-28T09:38:57.802503Z' -> datetime МСК.

    Дробная часть секунд приводится к 6 цифрам, 'Z' — к '+00:00': Python 3.10 (прод)
    в fromisoformat принимает только 3 или 6 цифр и не знает 'Z'.
    """
    if not value:
        return None
    text = str(value).strip().replace('Z', '+00:00')
    match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(.*)$', text)
    if match:
        fraction = '.' + match.group(2)[:6].ljust(6, '0') if match.group(2) else ''
        text = match.group(1) + fraction + match.group(3)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MOSCOW)
    return parsed.astimezone(MOSCOW)


def status_for(bar_id, ours, stored) -> dict:
    """Состояние для страницы: synced / review / waiting / error / unknown / no_card.

    synced  — позиции и цены совпадают с файлом.
    review  — расходится, но Яндекс уже скачал файл после публикации
              (lastUploadTime > lastUpdateTime): новый файл у него на проверке.
    waiting — расходится, и Яндекс ещё не скачивал файл после публикации.
    error   — Карты не проверились и сравнивать не с чем.
    """
    org_id = ORG_BY_BAR.get(bar_id)
    if not org_id:
        return {'state': 'no_card'}
    state = stored.get(bar_id) if isinstance(stored, dict) else None
    base = {'org_id': org_id, 'maps_url': maps_url(org_id)}
    if not isinstance(state, dict) or 'items' not in state:
        if isinstance(state, dict) and state.get('error'):
            return {**base, 'state': 'error', 'error': state['error'], 'attempt_at': state.get('attempt_at')}
        return {**base, 'state': 'unknown'}
    diff = compare(ours, state['items'])
    upload, update = _parse_time(state.get('last_upload')), _parse_time(state.get('last_update'))
    if not diff['total']:
        kind = 'synced'
    elif upload and update and upload > update:
        kind = 'review'
    else:
        kind = 'waiting'
    return {
        **base, 'state': kind, 'diff': diff,
        'last_upload': upload.isoformat() if upload else None,
        'last_update': update.isoformat() if update else None,
        'checked_at': state.get('checked_at'),
        'error': state.get('error'), 'attempt_at': state.get('attempt_at'),
        'maps_count': len(state['items']), 'file_count': len(ours or []),
    }


# ---------------------------------------------------------------- фон

def _loop():
    while True:
        stored = load_status()
        now = _now()
        due = [bar for bar in ORG_BY_BAR
               if not isinstance(stored.get(bar), dict) or not stored[bar].get('attempt_at')
               or now - datetime.fromisoformat(stored[bar]['attempt_at']) >= CHECK_EVERY]
        if due:
            try:
                refresh(ORG_BY_BAR)
            except MapsCheckBusy:
                pass
            except Exception as error:
                print(f'[YML-MAPS] проверка не удалась: {type(error).__name__}: {error}')
        time.sleep(15 * 60)


def start_watcher() -> None:
    """Один поток на все воркеры gunicorn: раз в 3 часа сверяет прайсы на Картах."""
    global _started, _lock_handle
    with _thread_lock:
        if _started:
            return
        os.makedirs(os.path.dirname(THREAD_LOCK_PATH), exist_ok=True)
        handle = open(THREAD_LOCK_PATH, 'a')
        try:
            portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.exceptions.BaseLockException:
            handle.close()
            return
        _lock_handle = handle
        threading.Thread(target=_loop, name='yml-maps-check', daemon=True).start()
        _started = True
        print('[YML-MAPS] сверка прайсов на Яндекс Картах раз в 3 часа')
