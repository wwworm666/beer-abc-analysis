"""Отзывы с публичной страницы бара на Яндекс Картах — без входа в кабинет.

Зачем. С 2026-10-09 отзывы в «Отзывы» загружаются отсюда, а не из кабинета
Яндекс Бизнеса (core/yandex_business.py): кабинету нужна сессия аккаунта
Яндекса, она протухла 2026-09-28, и отзывы 11 дней не обновлялись. Публичную
страницу видит любой гость, вход не нужен — так же сервис раз в 3 часа читает
прайс бара на Картах (core/yandex_maps_status.py).

Страница: https://yandex.ru/maps/org/<id>/reviews/ (вторая и дальше —
?page=N). Яндекс встраивает в неё данные страницы JSON-ом: список отзывов
(«reviews», у каждого reviewId — тот же id, что в кабинете; проверено
владельцем на Кременчугской 2026-10-09) и параметры списка («params»:
count — сколько отзывов у организации, page, totalPages, limit — 50 на
страницу). Модуль только читает: ответить или удалить что-либо так нельзя.

Разбор (parse_reviews_page) не привязан к месту блока в странице: берутся все
массивы «reviews», в которых есть записи с reviewId; повторы по reviewId
отбрасываются, отзывы чужих организаций (businessId другой — блок «похожие
места») пропускаются. Число отзывов — из params.count; если его нет — из
микроразметки <meta itemprop="reviewCount">; нет и там — None (тогда «на
Картах больше, чем у нас» не проверяется, см. yandex_reviews_sync).

Отзыв (parse_review) -> тот же плоский вид, что у кабинета
(core/yandex_business.parse_review), но только с полями, которые есть на
странице: external_id, rating, author, text, created_at, owner_reply, problems.
Фото, аватар и public_rating страница не даёт — их нет в записи, и загрузка
(ReviewStore.upsert_imported) оставляет у отзыва прежние значения.
    reviewId                      -> external_id
    rating                        -> rating 1..5 (иначе None и замечание)
    author.name                   -> author
    text                          -> text
    updatedTime (ISO, UTC)        -> created_at 'YYYY-MM-DDTHH:MM' по Москве
    businessComment.{text, updatedTime} -> owner_reply {text, at}
updatedTime — время последней правки отзыва: у нового отзыва это момент
публикации. У уже загруженного дата не меняется (created_at не обновляется
при загрузке), поэтому правка отзыва автором её не «омолодит».

Листание (collect_pages): страницы 2, 3, ... с паузой PAUSE_SEC, пока не
набрано count отзывов, не пройдено totalPages, не пришла пустая страница
или не исчерпан MAX_PAGES. Страница, вернувшая чужой номер или только уже
полученные отзывы, — ошибка «Карты не листают страницы», а не бесконечный
цикл: тогда загружается то, что успели получить.

Ошибки: MapsCaptchaError — Яндекс показал «я не робот» (повторять сразу
бессмысленно); MapsReviewsError — нет связи, код не 200, нет отзывов в
разметке, листание не работает. Документация: docs/yandex-reviews.md.
"""
import json
import re
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from core import msk_time
from core.yandex_business import _int, _str, ts_to_msk

MAPS_REVIEWS_URL = 'https://yandex.ru/maps/org/{org_id}/reviews/'
# Как у браузера: с «python-requests» Яндекс чаще отвечает капчей. Общие для
# страниц Карт (их же берёт сверка прайсов core/yandex_maps_status.py).
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/140.0 Safari/537.36'),
    'Accept-Language': 'ru-RU,ru;q=0.9',
}
CAPTCHA_MARKERS = ('showcaptcha', 'checkcaptcha', 'SmartCaptcha', 'Подтвердите, что запросы')
# Таймаут: 10 с на соединение, 40 с на ответ — страница Карт тяжёлая (как у прайсов).
TIMEOUT = (10, 40)
# Пауза между запросами подряд (страницы, бары): не частить, чтобы не получить капчу.
PAUSE_SEC = 1.5
# Предохранитель листания: 40 страниц по 50 — 2000 отзывов, больше, чем у любого бара.
MAX_PAGES = 40

_decoder = json.JSONDecoder()
_MICRODATA_COUNT = (re.compile(r'itemprop="reviewCount"[^>]*?content="(\d+)"'),
                    re.compile(r'content="(\d+)"[^>]*?itemprop="reviewCount"'))


class MapsReviewsError(Exception):
    """Страница отзывов не получена или не разобралась."""


class MapsCaptchaError(MapsReviewsError):
    """Яндекс показал проверку «я не робот»."""


def reviews_url(org_id, page: int = 1) -> str:
    url = MAPS_REVIEWS_URL.format(org_id=org_id)
    return url if page <= 1 else f'{url}?page={int(page)}'


# ---------------------------------------------------------------- разбор страницы

def _params(html: str) -> dict:
    """Первый блок «params» списка отзывов: в нём есть count и totalPages (или limit)."""
    fallback = None
    for match in re.finditer(r'"params"\s*:\s*\{', html):
        try:
            data, _ = _decoder.raw_decode(html, match.end() - 1)
        except ValueError:
            continue
        if not isinstance(data, dict) or 'count' not in data:
            continue
        if 'totalPages' in data:
            return data
        if fallback is None and ('limit' in data or 'page' in data):
            fallback = data
    return fallback or {}


def parse_reviews_page(html: str, org_id=None, allow_empty: bool = False) -> dict:
    """Страница отзывов Карт -> {reviews, count, count_source, page, total_pages, limit}.

    reviews — сырые записи (dict с reviewId) без повторов, в порядке страницы.
    count_source — 'params' | 'microdata' | None: откуда взято число отзывов.
    org_id — отзывы с другим businessId (похожие места) не берутся.
    allow_empty — страница без отзывов не ошибка (страница 2 и дальше: список кончился);
    у первой страницы пустота без нулевого count — знак другой разметки.
    """
    html = html or ''
    if any(marker in html for marker in CAPTCHA_MARKERS) and '"reviewId"' not in html:
        raise MapsCaptchaError('Яндекс показал проверку «я не робот», отзывы не получены')
    reviews, seen = [], set()
    for match in re.finditer(r'"reviews"\s*:\s*\[', html):
        try:
            data, _ = _decoder.raw_decode(html, match.end() - 1)
        except ValueError:
            continue
        for raw in data if isinstance(data, list) else []:
            if not isinstance(raw, dict) or not _str(str(raw.get('reviewId') or '')):
                continue
            business = raw.get('businessId')
            if org_id is not None and business not in (None, '') and str(business) != str(org_id):
                continue
            rid = str(raw['reviewId']).strip()
            if rid not in seen:
                seen.add(rid)
                reviews.append(raw)
    params = _params(html)
    count, source = _int(params.get('count')), 'params'
    if count is None:
        source = None
        for pattern in _MICRODATA_COUNT:
            found = pattern.search(html)
            if found:
                count, source = int(found.group(1)), 'microdata'
                break
    if not reviews and count != 0 and not allow_empty:
        raise MapsReviewsError('На странице Карт не найдены отзывы: Яндекс мог поменять разметку')
    return {'reviews': reviews, 'count': count, 'count_source': source,
            'page': _int(params.get('page')), 'total_pages': _int(params.get('totalPages')),
            'limit': _int(params.get('limit'))}


def iso_to_msk(value) -> Optional[str]:
    """'2026-09-17T16:39:00.123Z' (или Unix-время) -> 'YYYY-MM-DDTHH:MM' по Москве; не время -> None.

    Время без пояса считается UTC (так Яндекс отдаёт ISO-время). Дробная часть
    секунд приводится к 6 цифрам, 'Z' — к '+00:00': Python 3.10 (прод) иначе
    не разбирает (как _parse_time в core/yandex_maps_status.py).
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return ts_to_msk(value)
    text = _str(value)
    if not text:
        return None
    if text.isdigit():
        return ts_to_msk(int(text))
    text = text.replace('Z', '+00:00')
    match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)(?:\.(\d+))?(.*)$', text)
    if not match:
        return None
    fraction = '.' + match.group(2)[:6].ljust(6, '0') if match.group(2) else ''
    try:
        parsed = datetime.fromisoformat(match.group(1) + fraction + match.group(3))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(msk_time.MOSCOW_TZ).strftime('%Y-%m-%dT%H:%M')


def parse_review(raw: dict) -> dict:
    """Отзыв со страницы Карт -> {external_id, rating, author, text, created_at, owner_reply, problems}.

    Не бросает исключений: чего нет — None / '' и строка в problems (как
    core/yandex_business.parse_review). Ответ без текста — не ответ.
    """
    raw = raw if isinstance(raw, dict) else {}
    problems = []
    rid = _str(str(raw.get('reviewId') or ''))
    if not rid:
        problems.append('нет id')
    rating = _int(raw.get('rating'))
    if rating is None:
        problems.append(f'оценка не число: {raw.get("rating")!r}')
    elif not 1 <= rating <= 5:
        problems.append(f'оценка вне 1..5: {raw.get("rating")!r}')
        rating = None
    author = raw.get('author') if isinstance(raw.get('author'), dict) else {}
    created = iso_to_msk(raw.get('updatedTime'))
    if created is None:
        problems.append(f'нет даты: {raw.get("updatedTime")!r}')
    reply = None
    comment = raw.get('businessComment')
    if isinstance(comment, dict) and _str(comment.get('text')):
        reply = {'text': _str(comment.get('text')), 'at': iso_to_msk(comment.get('updatedTime'))}
        if reply['at'] is None:
            problems.append('у ответа организации нет даты')
    return {
        'external_id': rid,
        'rating': rating,
        'author': _str(author.get('name')),
        'text': _str(raw.get('text')),
        'created_at': created,
        'owner_reply': reply,
        'problems': problems,
    }


# ---------------------------------------------------------------- сеть

def fetch_page(org_id, page: int = 1, get=None) -> dict:
    """Скачать и разобрать одну страницу отзывов организации. Ошибка — MapsReviewsError."""
    import requests
    get = get or requests.get
    try:
        response = get(reviews_url(org_id, page), headers=HEADERS, timeout=TIMEOUT)
    except Exception as error:  # noqa: BLE001 — любая сетевая ошибка: страница не получена
        raise MapsReviewsError(f'Карты не ответили ({type(error).__name__})') from None
    if response.status_code != 200:
        raise MapsReviewsError(f'Карты ответили кодом {response.status_code}')
    return parse_reviews_page(response.text, org_id, allow_empty=page > 1)


def collect_pages(org_id, first: dict, *, fetch: Optional[Callable] = None,
                  sleep: Callable[[float], None] = time.sleep, max_pages: int = MAX_PAGES) -> dict:
    """Догрузить страницы 2, 3, ... к уже полученной первой.

    -> {reviews: все сырые записи без повторов, pages: сколько страниц получено,
        error: текст или None, captcha: bool}. Ошибка не бросается: что успели
    получить — в reviews (вызывающий загрузит это без пометки пропавших).
    fetch(org_id, page) -> разобранная страница (по умолчанию fetch_page).
    """
    fetch = fetch or fetch_page
    reviews = list(first.get('reviews') or [])
    seen = {str(r.get('reviewId')) for r in reviews}
    count, total_pages = first.get('count'), first.get('total_pages')
    result = {'reviews': reviews, 'pages': 1, 'error': None, 'captcha': False}
    page = 1
    while True:
        if count is not None and len(seen) >= count:
            break
        if total_pages is not None and page >= total_pages:
            break
        if page >= max_pages:
            result['error'] = f'Достигнут предел {max_pages} страниц отзывов'
            break
        if count is None and total_pages is None and not reviews:
            break
        page += 1
        sleep(PAUSE_SEC)
        try:
            parsed = fetch(org_id, page)
        except MapsCaptchaError as error:
            result.update(error=str(error), captcha=True)
            break
        except MapsReviewsError as error:
            result['error'] = f'Страница {page}: {error}'
            break
        if parsed.get('page') is not None and parsed['page'] != page:
            result['error'] = (f'Карты не листают страницы отзывов: на запрос страницы {page} '
                               f'пришла страница {parsed["page"]}')
            break
        fresh = [r for r in parsed.get('reviews') or [] if str(r.get('reviewId')) not in seen]
        if not parsed.get('reviews'):
            break
        if not fresh:
            if count is not None or total_pages is not None:
                result['error'] = (f'Карты не листают страницы отзывов: страница {page} '
                                   f'повторила уже полученные отзывы')
            break
        result['pages'] = page
        for raw in fresh:
            seen.add(str(raw.get('reviewId')))
            reviews.append(raw)
    return result
