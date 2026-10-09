"""Отзывы Яндекс Бизнеса: чтение через внутренний API кабинета (sprav).

Зачем. У Яндекс Бизнеса нет публичного API отзывов; кабинет владельца
(yandex.ru/sprav) сам ходит в свой JSON API, и этот модуль делает то же с
сессией владельца. Постановка — docs/апи яд, модуль — docs/yandex-reviews.md.

Только чтение — организации, филиалы сетей, отзывы. С 2026-09-28 по 2026-10-09
этим клиентом раз в сутки загружались отзывы; с 2026-10-09 их читают с публичной
страницы Карт без входа (core/yandex_maps_reviews.py, core/yandex_reviews_sync.py),
и загрузка этот модуль не использует. Он остаётся для диагностики
(scripts/yandex_reviews_probe.py) и для будущего ответа на отзыв из сервиса:
тогда — отдельный аккаунт Яндекса, добавленный представителем организаций, а не
личный аккаунт владельца (docs/yandex-reviews.md, «Кабинет»).

Почему свой тонкий клиент, а не пакет ya-business-api 4.0.1 (MIT, Kirill Lekhov).
Эндпоинты и приёмы взяты оттуда, но сам пакет не подключаем:
  - он требует requests>=2.32.5 и pydantic>=2.12.5, а в образе закреплён
    requests==2.31.0 и pydantic нет вовсе;
  - его модели строгие: в модели отзыва ~14 обязательных полей (токены чата,
    csrf ответа и т. п.), и пропажа любого из них у Яндекса ломает разбор всей
    страницы; здесь разбирается только то, что нужно, остальное — по умолчанию;
  - на 5xx он падает на assert (AssertionError), а не понятной ошибкой.
Весь код Яндекса — в этом файле: если внутренний API изменится, правится
только он (слой провайдера из постановки).

Эндпоинты (BASE_URL = https://yandex.ru/sprav):
    GET  /api/companies?page=N                     организации аккаунта
         -> {limit, page, total, listCompanies: [...]}
    GET  /api/chain/<tycoon_id>/branches/?chainPermalink=<permanent_id>&geoId=<geo_id>&page=N
         -> {companyList: {pager: {offset, limit, total}, companies: [...]}, companyIds}
    GET  /api/<permanent_id>/reviews?ranking_by=by_time&page=N
         -> {page, currentState, list: {pager: {limit, offset, total, continue_token}, items: [...]}}
    POST /api/view/chain/0/list/                   выдача CSRF-токена (ответ 488 {csrf}) —
         нужен только для ответа на отзыв (этап «отвечать»), чтению не нужен.

Пагинация отзывов — по номеру страницы (page=1, 2, ...). continue_token в
ответе есть, но сервер принимает его только вместе с unread=true (так строит
запрос и пакет: ReviewsRequest.as_query_params) — «все отзывы по
continue_token», как в примере постановки, крутили бы первую страницу
бесконечно. unread — состояние кабинета (отзыв могли открыть в Яндексе раньше
нас), поэтому «новый» у нас = id, которого ещё нет в нашем хранилище.
Остановка обхода: пустая страница; offset + число отзывов >= total; предел
страниц; страница, повторившая уже виденный отзыв (сервер проигнорировал page)
-> YandexFormatError, а не бесконечный цикл.

Авторизация — cookies Session_id и sessionid2 аккаунта, у которого есть доступ
к организациям в Яндекс Бизнесе. Это сессия ВСЕГО аккаунта Яндекса (почта,
диск и т. д.), поэтому: только из переменных окружения, никогда в логах,
ответах API и текстах ошибок (_scrub вырезает их значения из любого
сообщения). Признак протухшей сессии — 302 на passport.yandex.ru, 401 или 488
-> YandexAuthError.

Ошибки:
    YandexAuthError       сессия недействительна — нужна повторная авторизация; не повторяется
    YandexCaptchaError    429 с need-captcha: Яндекс просит капчу; не повторяется
    YandexTemporaryError  сеть, таймаут, 5xx — повтор с паузами RETRY_DELAYS_SEC, потом ошибка
    YandexFormatError     ответ не того вида (не JSON, нет ожидаемых полей, пагинация не работает)
"""
import time
from datetime import datetime
from typing import Callable, Dict, Iterator, List, Optional

import requests

from core import msk_time

BASE_URL = 'https://yandex.ru/sprav'
PASSPORT_URL = 'https://passport.yandex.ru'

COOKIE_SESSION_ID = 'Session_id'
COOKIE_SESSION_ID2 = 'sessionid2'
# Кабинет требует cookie «i» при выдаче CSRF, но значение не проверяет (так
# делает и ya-business-api): ставим пустую, если её нет.
COOKIE_I = 'i'

# Как у браузера: с пустым или «python-requests» User-Agent Яндекс чаще
# отвечает капчей. Строка — из ya-business-api 4.0.1.
USER_AGENT = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/138.0.0.0 Safari/537.36')

# Коды «сессия не принята»: 401 и 488 (488 кабинет отдаёт на неверный CSRF;
# на чтении без CSRF его быть не должно — значит, сессию не узнали).
AUTH_STATUSES = frozenset({401, 488})
# Временные сбои, которые имеет смысл повторить.
TEMPORARY_STATUSES = frozenset({500, 502, 503, 504})

REQUEST_TIMEOUT_SEC = 20        # один запрос; кабинет обычно отвечает за 0,3–2 с
# Повторы временных сбоев: 3 попытки с паузами 2 и 6 с. Капчу и протухшую
# сессию не повторяем: повтор капчу только усугубит, а сессия сама не оживёт.
RETRY_DELAYS_SEC = (2, 6)
# Пауза между запросами подряд (обход страниц): не частить в чужой внутренний
# API, чтобы не получить капчу. 4 филиала × несколько страниц — секунды.
REQUEST_PAUSE_SEC = 0.5
# Предохранитель обхода: страниц одного филиала за один проход. На странице
# ~20–50 отзывов, 200 страниц — это тысячи отзывов, больше, чем у любого бара.
MAX_REVIEW_PAGES = 200
MAX_LIST_PAGES = 50             # страниц организаций / филиалов сети

# Метка времени Яндекса — секунды Unix; если пришли миллисекунды (число
# больше 10^11 — это 5138 год в секундах), делим на 1000.
_MS_THRESHOLD = 10 ** 11


class YandexBusinessError(RuntimeError):
    """Базовая ошибка клиента кабинета."""


class YandexAuthError(YandexBusinessError):
    """Сессия Яндекса недействительна: нужна повторная авторизация (новые cookies)."""


class YandexCaptchaError(YandexBusinessError):
    """Яндекс просит капчу: запросы с этого адреса временно не принимаются."""


class YandexTemporaryError(YandexBusinessError):
    """Сеть, таймаут или 5xx после всех повторов."""


class YandexFormatError(YandexBusinessError):
    """Ответ не того вида: не JSON, нет ожидаемых полей, пагинация не работает."""


# ----------------------------------------------------------------- разбор

def _int(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip('-').isdigit():
        return int(value.strip())
    return None


def _str(value) -> str:
    return value.strip() if isinstance(value, str) else ''


def ts_to_msk(value) -> Optional[str]:
    """Метка Unix (секунды или миллисекунды) -> 'YYYY-MM-DDTHH:MM' по Москве; не число -> None.

    Формат хранилища отзывов (core/guest_reviews.DT_FORMAT): наивная
    московская строка с точностью до минуты, секунды отбрасываются.
    """
    ts = _int(value)
    if ts is None or ts <= 0:
        return None
    if ts > _MS_THRESHOLD:
        ts //= 1000
    dt = datetime.fromtimestamp(ts, msk_time.MOSCOW_TZ)
    return dt.strftime('%Y-%m-%dT%H:%M')


def parse_review(raw: dict) -> dict:
    """Отзыв из ответа кабинета -> плоский словарь для нашего хранилища.

        external_id     id отзыва в Яндексе (ключ дедупликации вместе с source='yandex')
        rating          1..5 или None (не число или вне 1..5 — см. problems)
        author          имя из профиля ('' — нет)
        author_privacy  как Яндекс показывает автора (как пришло, для проверки)
        author_avatar   ссылка на аватар или None
        text            full_text, иначе snippet ('' — только оценка)
        created_at      'YYYY-MM-DDTHH:MM' по Москве или None
        owner_reply     {text, at} — ответ организации в Яндексе, или None
        photos          [{link, width, height}]
        lang            язык отзыва
        public_rating   bool | None — учитывается ли оценка в рейтинге
        problems        список замечаний разбора (пусто — всё на месте)

    Не бросает исключений на неполной записи: чего нет — None/'' и замечание
    в problems. Служебные токены отзыва (csrf ответа, токены чата) не
    переносятся: чтению они не нужны.
    """
    raw = raw if isinstance(raw, dict) else {}
    problems: List[str] = []
    rid = _str(raw.get('id'))
    if not rid:
        problems.append('нет id')
    rating = _int(raw.get('rating'))
    if rating is not None and not 1 <= rating <= 5:
        problems.append(f'оценка вне 1..5: {raw.get("rating")!r}')
        rating = None
    elif rating is None:
        problems.append(f'оценка не число: {raw.get("rating")!r}')
    author = raw.get('author') if isinstance(raw.get('author'), dict) else {}
    created = ts_to_msk(raw.get('time_created'))
    if created is None:
        problems.append(f'нет даты: {raw.get("time_created")!r}')
    reply = None
    oc = raw.get('owner_comment')
    if isinstance(oc, dict) and _str(oc.get('text')):
        reply = {'text': _str(oc.get('text')), 'at': ts_to_msk(oc.get('time_created'))}
        if reply['at'] is None:
            problems.append('у ответа организации нет даты')
    photos = []
    for p in raw.get('photos') or []:
        if isinstance(p, dict) and _str(p.get('link')):
            photos.append({'link': _str(p.get('link')), 'width': _int(p.get('width')),
                           'height': _int(p.get('height'))})
    public = raw.get('public_rating')
    return {
        'external_id': rid,
        'rating': rating,
        'author': _str(author.get('user')),
        'author_privacy': _str(author.get('privacy')),
        'author_avatar': _str(author.get('avatar')) or None,
        'text': _str(raw.get('full_text')) or _str(raw.get('snippet')),
        'created_at': created,
        'owner_reply': reply,
        'photos': photos,
        'lang': _str(raw.get('lang')),
        'public_rating': public if isinstance(public, bool) else None,
        'problems': problems,
    }


def parse_company(raw: dict) -> dict:
    """Организация из списка кабинета -> {permanent_id, tycoon_id, type, name, address, geo_id, rating, reviews_count}.

    permanent_id — постоянный id организации в Яндексе (он же в ссылке
    yandex.ru/maps/org/<...>/<permanent_id>); по нему, а не по названию,
    связываем филиал с нашим баром.
    """
    raw = raw if isinstance(raw, dict) else {}
    address = raw.get('address') if isinstance(raw.get('address'), dict) else {}
    formatted = address.get('formatted') if isinstance(address.get('formatted'), dict) else {}
    return {
        'permanent_id': _int(raw.get('permanent_id')),
        'tycoon_id': _int(raw.get('tycoon_id')),
        'type': _str(raw.get('type')),
        'name': _str(raw.get('displayName')) or _str(raw.get('display_name')),
        'address': _str(formatted.get('value')),
        'geo_id': _int(address.get('geo_id')),
        'publishing_status': _str(raw.get('publishing_status')),
        'rating': raw.get('rating') if isinstance(raw.get('rating'), (int, float)) else None,
        'reviews_count': _int(raw.get('reviewsCount')),
    }


# ----------------------------------------------------------------- клиент

class YandexBusinessClient:
    """Чтение кабинета Яндекс Бизнеса от имени сессии владельца.

    http — объект с методами get/post как у requests.Session (в тестах —
    фейк); sleep подменяется в тестах, чтобы повторы не ждали.
    """

    def __init__(self, session_id: str, session_id2: str, *, http=None,
                 sleep: Callable[[float], None] = time.sleep,
                 pause_sec: float = REQUEST_PAUSE_SEC):
        session_id = (session_id or '').strip()
        session_id2 = (session_id2 or '').strip()
        if not session_id or not session_id2:
            raise YandexAuthError('Не заданы cookies Яндекса: нужны Session_id и sessionid2')
        self._secrets = (session_id, session_id2)
        self._sleep = sleep
        self._pause = pause_sec
        self._last_request = 0.0
        if http is None:
            http = requests.Session()
            http.headers.update({'User-Agent': USER_AGENT})
        self._http = http
        self._http.cookies.set(COOKIE_SESSION_ID, session_id, domain='.yandex.ru')
        self._http.cookies.set(COOKIE_SESSION_ID2, session_id2, domain='.yandex.ru')

    def close(self) -> None:
        close = getattr(self._http, 'close', None)
        if callable(close):
            close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ----- запросы ---------------------------------------------------------

    def _scrub(self, text) -> str:
        """Сообщение без значений cookies — на случай, если их вернёт библиотека или сервер."""
        s = str(text)
        for secret in self._secrets:
            if secret:
                s = s.replace(secret, '***')
        return s

    def _throttle(self) -> None:
        wait = self._last_request + self._pause - time.monotonic()
        if wait > 0:
            self._sleep(wait)
        self._last_request = time.monotonic()

    def _get_json(self, path: str, params: Optional[dict] = None) -> dict:
        """GET BASE_URL + path -> JSON-объект; ошибки — классы Yandex*Error (см. докстринг модуля)."""
        url = BASE_URL + path
        attempts = len(RETRY_DELAYS_SEC) + 1
        last = ''
        for attempt in range(attempts):
            if attempt:
                self._sleep(RETRY_DELAYS_SEC[attempt - 1])
            self._throttle()
            try:
                resp = self._http.get(url, params=params or {}, allow_redirects=False,
                                      timeout=REQUEST_TIMEOUT_SEC)
            except (requests.ConnectionError, requests.Timeout) as e:
                last = f'сеть: {type(e).__name__}'
                continue
            status = resp.status_code
            location = resp.headers.get('Location') or resp.headers.get('location') or ''
            if status in (301, 302, 303, 307) and location.startswith(PASSPORT_URL):
                raise YandexAuthError('Сессия Яндекса не принята (переадресация на вход) — '
                                      'нужны новые cookies')
            if status in AUTH_STATUSES:
                raise YandexAuthError(f'Сессия Яндекса не принята (HTTP {status}) — нужны новые cookies')
            if status == 429 and resp.headers.get('need-captcha') == '1':
                raise YandexCaptchaError('Яндекс просит капчу — запросы временно не принимаются')
            if status in TEMPORARY_STATUSES or status == 429:
                last = f'HTTP {status}'
                continue
            if status != 200:
                raise YandexFormatError(f'Неожиданный ответ HTTP {status} на {path}')
            try:
                data = resp.json()
            except ValueError:
                raise YandexFormatError(f'Ответ на {path} — не JSON')
            if not isinstance(data, dict):
                raise YandexFormatError(f'Ответ на {path} — не объект')
            return data
        raise YandexTemporaryError(self._scrub(f'{path}: {last} после {attempts} попыток'))

    # ----- организации -----------------------------------------------------

    def list_companies(self) -> List[dict]:
        """Все организации аккаунта (как в кабинете): обычные филиалы и сети, сырые записи."""
        out: List[dict] = []
        for page in range(1, MAX_LIST_PAGES + 1):
            data = self._get_json('/api/companies', {'page': page})
            items = data.get('listCompanies')
            if not isinstance(items, list):
                raise YandexFormatError('В ответе /api/companies нет listCompanies')
            if not items:
                break
            out.extend(i for i in items if isinstance(i, dict))
            total, limit = _int(data.get('total')), _int(data.get('limit'))
            if total is not None and limit and page * limit >= total:
                break
        return out

    def chain_branches(self, chain: dict) -> List[dict]:
        """Филиалы сети (сырые записи). chain — разобранная parse_company запись типа 'chain'."""
        if not chain.get('tycoon_id') or not chain.get('permanent_id') or not chain.get('geo_id'):
            raise YandexFormatError(f'У сети «{chain.get("name")}» нет tycoon_id / permanent_id / geo_id')
        out: List[dict] = []
        seen = set()
        for page in range(1, MAX_LIST_PAGES + 1):
            data = self._get_json(f'/api/chain/{chain["tycoon_id"]}/branches/',
                                  {'chainPermalink': chain['permanent_id'], 'geoId': chain['geo_id'],
                                   'page': page})
            block = data.get('companyList') if isinstance(data.get('companyList'), dict) else {}
            items = block.get('companies')
            if not isinstance(items, list):
                raise YandexFormatError('В ответе филиалов сети нет companyList.companies')
            fresh = [i for i in items if isinstance(i, dict) and i.get('permanent_id') not in seen]
            if not fresh:
                break
            for i in fresh:
                seen.add(i.get('permanent_id'))
            out.extend(fresh)
            pager = block.get('pager') if isinstance(block.get('pager'), dict) else {}
            offset, limit, total = _int(pager.get('offset')), _int(pager.get('limit')), _int(pager.get('total'))
            if total is not None and offset is not None and offset + len(items) >= total:
                break
            if total is None and limit and len(items) < limit:
                break
        return out

    def branches(self) -> List[dict]:
        """Все обычные организации аккаунта (type 'ordinal'): сети раскрываются в филиалы.

        Результат — разобранные parse_company записи без повторов по
        permanent_id, у каждой поле via_chain (имя сети или '').
        """
        result: Dict[int, dict] = {}
        for raw in self.list_companies():
            c = parse_company(raw)
            if c['type'] == 'chain':
                for b_raw in self.chain_branches(c):
                    b = parse_company(b_raw)
                    if b['permanent_id'] and b['type'] in ('ordinal', ''):
                        b['type'] = 'ordinal'
                        b['via_chain'] = c['name']
                        result.setdefault(b['permanent_id'], b)
            elif c['permanent_id']:
                c['via_chain'] = ''
                result.setdefault(c['permanent_id'], c)
        return list(result.values())

    # ----- отзывы ----------------------------------------------------------

    def reviews_page(self, permanent_id: int, page: int = 1, ranking: str = 'by_time') -> dict:
        """Одна страница отзывов (сырой ответ). ranking: by_time — новые первыми."""
        return self._get_json(f'/api/{int(permanent_id)}/reviews', {'ranking_by': ranking, 'page': int(page)})

    def iter_review_pages(self, permanent_id: int, max_pages: int = MAX_REVIEW_PAGES) -> Iterator[dict]:
        """Страницы отзывов филиала от новых к старым: {page, total, offset, items (сырые)}.

        Остановка — см. «Пагинация отзывов» в докстринге модуля. Вызывающий
        может прекратить обход раньше (инкрементальная синхронизация).
        """
        seen = set()
        for page in range(1, max_pages + 1):
            data = self.reviews_page(permanent_id, page)
            block = data.get('list') if isinstance(data.get('list'), dict) else None
            if block is None or not isinstance(block.get('items'), list):
                raise YandexFormatError(f'В ответе отзывов филиала {permanent_id} нет list.items')
            items = [i for i in block['items'] if isinstance(i, dict)]
            if not items:
                return
            ids = [i.get('id') for i in items]
            if page > 1 and any(x in seen for x in ids):
                raise YandexFormatError(f'Пагинация отзывов не работает: страница {page} филиала '
                                        f'{permanent_id} повторяет уже полученные отзывы')
            seen.update(ids)
            pager = block.get('pager') if isinstance(block.get('pager'), dict) else {}
            total, offset = _int(pager.get('total')), _int(pager.get('offset'))
            yield {'page': page, 'total': total, 'offset': offset, 'items': items}
            if total is not None and offset is not None and offset + len(items) >= total:
                return
            if total is not None and offset is None and len(seen) >= total:
                return
