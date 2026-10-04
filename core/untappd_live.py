"""Связи с Untappd без деплоя: агент предлагает, владелец подтверждает на сайте.

Решение владельца 2026-10-04: реестр Untappd — единственный источник правды о пиве,
а новые кеги связываются с карточками Untappd автоматически, через ИИ-агента.
Встроенный реестр (resources/iiko_untappd_registry.json) меняется только деплоем,
поэтому связи для новых кег живут здесь — untappd_links.json на постоянном томе
(core/storage_paths) — и действуют сразу: core.untappd_registry.load_registry()
накладывает подтверждённые связи на встроенный реестр (apply), а дальше их читает
тот же строгий resolve_beer. Таплист, «Таплист пятницы», гостевой бот, фиды
Яндекса и граф знаний видят новую связь в момент подтверждения.

Как это работает:
1. Очередь «Нужна связь» (queue) — кеги без проверенной связи: на кране сейчас
   (приоритет 1, без связи стопорится пятничный пост), новые карточки номенклатуры
   iiko, которых нет во встроенном реестре (2), остальные нерешённые (3, только в
   полном списке).
2. ИИ-агент по расписанию (MCP, режим «Чтение и черновики») находит карточку
   Untappd и присылает предложение (propose): ссылка на карточку, название,
   пивоварня, стиль, крепость, IBU, основание и источники, стиль по-русски и
   короткое имя пивоварни для поста. Предложение — черновик: ни на что не влияет.
3. Администратор на странице «Связи с Untappd» (/taps/untappd) нажимает «Верно»
   (confirm) — связь проверена; «Не то» (reject) с причиной — агент видит её в
   очереди и ищет снова. «Отменить связь» (revoke) — только у связей, подтверждённых
   здесь; встроенный реестр меняет деплой.

Связь — только по GUID товара iiko и числовому id карточки Untappd. По похожему
названию ничего не связывается: предложение без подтверждения ничего не меняет.

Файл повреждён — UntappdLinksUnavailable (API 503), файл никогда не
перезаписывается; чтение для сайта (apply) тогда работает по встроенному реестру.
Правила и примеры — docs/untappd-links.md, раздел «Новые кеги: агент предлагает,
владелец подтверждает».
"""
import copy
import json
import os
import re
import secrets
import threading
from typing import Callable, Dict, List, Optional, Tuple
from uuid import UUID

from core import msk_time
from core.json_store import atomic_write_json, file_lock
from core.storage_paths import get_data_path
from core.untappd_registry import resolve_beer

SCHEMA_VERSION = 1
FILE_NAME = 'untappd_links.json'

STATUSES = ('proposed', 'verified', 'rejected', 'superseded', 'revoked')
SCOPES = ('urgent', 'all')      # очередь: срочное (на кране, новые карточки) или всё нерешённое
# Поля карточки в предпросмотре: то, что уйдёт в таплист, бота и фид Яндекса.
PREVIEW_CARD_FIELDS = ('beer_name', 'brewery', 'style', 'abv_percent', 'ibu', 'description', 'photo_url')
STATUS_NAMES = {'proposed': 'на проверке', 'verified': 'подтверждена', 'rejected': 'отклонена',
                'superseded': 'заменена новым предложением', 'revoked': 'отменена'}
ORIGIN_AGENT, ORIGIN_HUMAN = 'agent', 'human'

# Пределы полей: имена и стиль — как в карточке Untappd (самые длинные в реестре —
# около 120 знаков), описание — отрывок, как в реестре (scripts/enrich_untappd_media.py
# берёт до 25 слов), основание — как «Почему этот пост» контент-плана.
NAME_MAX = 200
STYLE_MAX = 120
DESCRIPTION_MAX = 400
REASON_MAX = 2000
NOTE_MAX = 500
URL_MAX = 500
EVIDENCE_MAX = 10
ABV_MAX = 80             # крепость в процентах: крепче 80% пива не бывает — это опечатка
IBU_MAX = 300            # горечь: у самых горьких сортов в реестре — до 100
# Журнал и старые неподтверждённые предложения: подтверждённые не удаляются никогда
# (это и есть связи), остальных хватает на год работы четырёх баров.
LOG_MAX = 2000
INACTIVE_MAX = 2000

# Карточка пива Untappd: https://untappd.com/b/<slug>/<id> — тот же вид, что требует
# resolve_beer у встроенного реестра.
CARD_URL_RE = re.compile(r'^https?://(?:www\.)?untappd\.com/b/([^/?#\s]+)/([1-9][0-9]{0,11})/?$', re.IGNORECASE)
# Фото — только с хранилищ Untappd (как у scripts/enrich_untappd_media.py): картинка
# уходит в публичный фид Яндекса и в CSV.
PHOTO_URL_RE = re.compile(r'^https://(?:assets\.untappd\.com|untappd\.s3\.amazonaws\.com)/[A-Za-z0-9_./%-]+$')
HTTP_URL_RE = re.compile(r'^https?://[^\s<>"]+$', re.IGNORECASE)


class UntappdLinksUnavailable(RuntimeError):
    """Файл связей не читается — запись запрещена, API 503."""


class UntappdLinksError(ValueError):
    """Ошибка запроса: code — для API (400 bad_request, 404 not_found, 409 conflict)."""

    def __init__(self, message: str, code: str = 'bad_request'):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Проверка полей
# ---------------------------------------------------------------------------

def _clean(value) -> str:
    return ' '.join(str(value or '').split())


def _text(value, field: str, limit: int, required: bool = False) -> str:
    text = _clean(value)
    if required and not text:
        raise UntappdLinksError(f'{field}: пусто')
    if len(text) > limit:
        raise UntappdLinksError(f'{field}: длиннее {limit} знаков')
    return text


def parse_guid(value) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise UntappdLinksError('iiko_product_id: нужен GUID товара iiko (из stocks_untappd_queue)')


def parse_card_url(value) -> Tuple[str, str]:
    """Ссылка на карточку пива Untappd -> (каноническая ссылка, id). Параметры и якорь
    отбрасываются, www и http приводятся к https://untappd.com."""
    raw = str(value or '').strip().split('#', 1)[0].split('?', 1)[0]
    match = CARD_URL_RE.match(raw)
    if not match or len(raw) > URL_MAX:
        raise UntappdLinksError('untappd_url: нужна ссылка на карточку пива вида '
                                'https://untappd.com/b/<название>/<число>')
    slug, bid = match.group(1), match.group(2)
    return f'https://untappd.com/b/{slug}/{bid}', bid


def _number(value, field: str, upper: float, integer: bool = False):
    if value in (None, ''):
        return None
    try:
        number = float(str(value).replace(',', '.').replace('%', '').strip())
    except ValueError:
        raise UntappdLinksError(f'{field}: нужно число')
    if not 0 <= number <= upper:
        raise UntappdLinksError(f'{field}: от 0 до {upper}')
    if integer:
        if number != int(number):
            raise UntappdLinksError(f'{field}: нужно целое число')
        return int(number)
    return round(number, 2)


def _evidence(values, card_url: str) -> List[str]:
    out = [card_url]
    if values in (None, ''):
        values = []
    if not isinstance(values, list):
        raise UntappdLinksError('evidence_urls: нужен список ссылок')
    for value in values:
        url = str(value or '').strip()
        if not url:
            continue
        if len(url) > URL_MAX or not HTTP_URL_RE.match(url):
            raise UntappdLinksError(f'evidence_urls: «{url[:80]}» — не ссылка http(s)')
        if url not in out:
            out.append(url)
    if len(out) > EVIDENCE_MAX + 1:
        raise UntappdLinksError(f'evidence_urls: не больше {EVIDENCE_MAX} ссылок')
    return out


def who(user: Optional[dict]) -> str:
    """Подпись в журнале: имя; вызов агента через MCP — «<имя> · агент» (как в контент-плане)."""
    user = user or {}
    name = user.get('display_name') or user.get('login') or 'неизвестно'
    return f'{name} · агент' if user.get('via_mcp') else name


def _origin(user: Optional[dict]) -> str:
    return ORIGIN_AGENT if (user or {}).get('via_mcp') else ORIGIN_HUMAN


# ---------------------------------------------------------------------------
# Наложение на реестр и имена для поста
# ---------------------------------------------------------------------------

def _empty() -> dict:
    return {'schema_version': SCHEMA_VERSION, 'proposals': [], 'log': []}


def _verified(data: dict) -> List[dict]:
    """Подтверждённые связи, по одной на GUID — последняя по времени подтверждения."""
    latest: Dict[str, dict] = {}
    for item in data.get('proposals') or []:
        if item.get('status') != 'verified':
            continue
        guid = item.get('iiko_product_id')
        if guid not in latest or (item.get('reviewed_at') or '') >= (latest[guid].get('reviewed_at') or ''):
            latest[guid] = item
    return [latest[guid] for guid in sorted(latest)]


def apply(registry: dict, data: Optional[dict] = None) -> dict:
    """Реестр + связи, подтверждённые на сайте. Входной реестр не меняется.

    Встроенная проверенная связь главнее: если тот же GUID позже проверили в
    реестре (деплой), запись отсюда не применяется. Карточка пива — из реестра, если
    этот id Untappd там уже есть (проверенные наблюдения), иначе — из предложения.
    data None — прочитать файл; файл повреждён — реестр как есть (сайт работает по
    встроенным связям, страница связей отвечает 503)."""
    if data is None:
        try:
            data = get_store()._read()
        except UntappdLinksUnavailable as e:
            print(f'[UNTAPPD-LIVE] связи с сайта не наложены: {e}')
            return registry
    verified = _verified(data)
    if not verified:
        return registry
    merged = dict(registry)
    products = dict(registry.get('products') or {})
    beers = dict(registry.get('beers') or {})
    for item in verified:
        guid, bid, url = item['iiko_product_id'], item['untappd_beer_id'], item['url']
        if resolve_beer(registry, guid):
            continue
        card = beers.get(bid)
        evidence = list(item.get('evidence_urls') or [url])
        if card and card.get('url') and card['url'] not in evidence:
            evidence.insert(0, card['url'])
        if not card:
            proposed = item.get('card') or {}
            card = {'id': bid, 'url': url, 'beer_name': proposed.get('beer_name'), 'brewery': proposed.get('brewery'),
                    'style': proposed.get('style') or None, 'abv_percent': proposed.get('abv_percent'),
                    'ibu': proposed.get('ibu'), 'description': proposed.get('description') or None,
                    'description_is_excerpt': bool(proposed.get('description')),
                    'photo_url': proposed.get('photo_url') or None,
                    'photo_kind': 'label' if proposed.get('photo_url') else None,
                    'observed_at': (item.get('reviewed_at') or '')[:10],
                    'source_method': 'Предложение ИИ-агента или сотрудника, подтверждено на сайте',
                    'media_source_url': url if proposed.get('photo_url') else None, 'live': True}
            beers[bid] = card
        old = products.get(guid) or {}
        products[guid] = dict(old, iiko_product_id=guid, iiko_name=old.get('iiko_name') or item.get('iiko_name'),
                              iiko_article=old.get('iiko_article', item.get('iiko_article')), status='verified',
                              untappd_beer_id=bid, live=True,
                              decision={'status': 'verified', 'untappd_beer_id': bid, 'reason': item.get('reason'),
                                        'reviewed_at': (item.get('reviewed_at') or '')[:10],
                                        'reviewed_by': item.get('reviewed_by'), 'evidence_urls': evidence,
                                        'confirmation_origin': 'site', 'proposal_id': item.get('id')})
    merged['products'] = products
    merged['beers'] = beers
    return merged


def live_names(data: Optional[dict] = None) -> dict:
    """Имена для поста из подтверждённых связей: {styles: {стиль Untappd: по-русски},
    breweries: {пивоварня Untappd: короткое имя}}. Словарь в репозитории главнее —
    эти только заполняют пробелы (core/taplist_post.load_names)."""
    if data is None:
        try:
            data = get_store()._read()
        except UntappdLinksUnavailable:
            return {'styles': {}, 'breweries': {}}
    styles: Dict[str, str] = {}
    breweries: Dict[str, str] = {}
    for item in _verified(data):
        card, names = item.get('card') or {}, item.get('names') or {}
        if card.get('style') and names.get('style_ru'):
            styles.setdefault(card['style'], names['style_ru'])
        if card.get('brewery') and names.get('brewery_short') is not None:
            breweries.setdefault(card['brewery'], names['brewery_short'])
    return {'styles': styles, 'breweries': breweries}


def preview(item: dict, names: dict, registry: Optional[dict] = None) -> dict:
    """Как сорт будет выглядеть в таплисте после «Верно» — до подтверждения.

    -> {line: строка без номера крана (core/taplist_post.beer_text) и её части: name
    (пивоварня и название), style_ru, abv (крепость текстом, без «%»; пусто — None);
    known_card: id Untappd уже есть в реестре (тогда данные карточки — оттуда, как в
    apply); style_from_dictionary / brewery_from_dictionary / name_from_dictionary:
    стиль, пивоварня или всё название берутся из словаря репозитория — правка в
    предложении на них не влияет; beer_name, brewery_short и style — название из
    карточки, пивоварня в посте и стиль Untappd (из них страница собирает строку
    заново, когда администратор правит стиль по-русски или имя пивоварни); card —
    карточка, которая пойдёт в таплист (из реестра, если known_card)}.
    names — core.taplist_post.load_names()."""
    from core.taplist_post import beer_text, brewery_short, format_abv, post_name, style_ru
    bid = str(item.get('untappd_beer_id') or '')
    known = ((registry or {}).get('beers') or {}).get(bid)
    card = known or item.get('card') or {}
    proposed = item.get('names') or {}
    style, brewery = card.get('style') or '', card.get('brewery') or ''
    styles, breweries = dict(names['styles']), dict(names['breweries'])
    style_known = bool(style) and (style in styles or _clean(style) in styles)
    brewery_known = brewery in breweries or _clean(brewery) in breweries
    if style and not style_known and proposed.get('style_ru'):
        styles[style] = proposed['style_ru']
    if brewery and not brewery_known and proposed.get('brewery_short') is not None:
        breweries[brewery] = proposed['brewery_short']
    row = {'untappd_beer_id': bid, 'beer_name': card.get('beer_name'), 'brewery': brewery,
           'style': style, 'abv': card.get('abv_percent'), 'untappd_url': item.get('url')}
    merged = {'styles': styles, 'breweries': breweries, 'beers': names['beers']}
    abv = format_abv(row['abv']) if row['abv'] else None
    return {'line': beer_text(row, merged), 'name': post_name(row, merged), 'style_ru': style_ru(style, merged),
            'abv': abv if abv and abv != '0' else None, 'beer_name': _clean(card.get('beer_name')),
            'brewery_short': brewery_short(brewery, merged) if brewery else '', 'style': style,
            'card': {key: card.get(key) for key in PREVIEW_CARD_FIELDS},
            'known_card': bool(known), 'style_from_dictionary': style_known,
            'brewery_from_dictionary': brewery_known, 'name_from_dictionary': bid in names['beers']}


# ---------------------------------------------------------------------------
# Очередь «Нужна связь»
# ---------------------------------------------------------------------------

def _brief(item: Optional[dict]) -> Optional[dict]:
    if not item:
        return None
    card = item.get('card') or {}
    return {'id': item['id'], 'status': item['status'], 'url': item.get('url'),
            'beer_name': card.get('beer_name'), 'brewery': card.get('brewery'),
            'created_at': item.get('created_at'), 'created_by': item.get('created_by'),
            'review_note': item.get('review_note')}


def taps_by_product(snapshot: Optional[dict], bar_names: Optional[dict] = None
                    ) -> Tuple[Dict[str, List[dict]], List[dict]]:
    """Где кеги стоят сейчас: ({GUID товара iiko: [{bar_id, bar, tap_number,
    started_at}]}, [краны без товара iiko — с current_beer]). Краны по порядку бара
    и номера."""
    bar_names = bar_names or {}
    on_tap: Dict[str, List[dict]] = {}
    unidentified: List[dict] = []
    for bar_id, bar in sorted((snapshot or {}).items()):
        taps = sorted((bar or {}).get('taps') or [], key=lambda t: str(t.get('tap_number')).zfill(4))
        for tap in taps:
            if tap.get('status') != 'active' or not tap.get('current_beer'):
                continue
            entry = {'bar_id': bar_id, 'bar': bar_names.get(bar_id) or bar.get('name'),
                     'tap_number': tap.get('tap_number'), 'started_at': tap.get('started_at')}
            guid = tap.get('iiko_product_id')
            if guid:
                on_tap.setdefault(str(guid), []).append(entry)
            else:
                unidentified.append(dict(entry, current_beer=tap.get('current_beer')))
    return on_tap, unidentified


def queue(registry: dict, catalog: dict, snapshot: dict, data: dict, scope: str = 'urgent',
          bar_names: Optional[dict] = None) -> dict:
    """Кеги без проверенной связи с Untappd.

    registry — реестр с наложенными связями (load_registry); catalog —
    core.taplist.product_catalog (реестр + номенклатура iiko «КЕГ …»); snapshot —
    краны (TapsManager.get_snapshot). Приоритет: 1 — стоит на кране сейчас, 2 — новая
    карточка (нет во встроенном реестре), 3 — прочие нерешённые (scope 'all').
    Технические карточки (excluded) не показываются; пропущенные владельцем при сборке
    реестра (skipped) — только когда стоят на кране. Краны без товара iiko («Уточните
    сорт на кране») — отдельным списком: это действие бармена, не связь."""
    if scope not in SCOPES:
        raise UntappdLinksError("scope: 'urgent' или 'all'")
    latest: Dict[str, dict] = {}
    for item in data.get('proposals') or []:
        guid = item.get('iiko_product_id')
        if item.get('status') in ('proposed', 'rejected', 'revoked') and \
                (item.get('updated_at') or '') >= ((latest.get(guid) or {}).get('updated_at') or ''):
            latest[guid] = item
    on_tap, unidentified = taps_by_product(snapshot, bar_names)
    products = registry.get('products') or {}
    items = []
    for guid, product in catalog.items():
        if resolve_beer(registry, guid):
            continue
        status = (products.get(guid) or {}).get('status') or 'new'
        if status == 'excluded':
            continue
        taps = on_tap.get(guid, [])
        priority = 1 if taps else (2 if guid not in products else 3)
        # «Пропущено владельцем» при сборке реестра — в очередь только когда кега на кране:
        # тогда без связи останавливается пост, и решать снова владельцу.
        if (status == 'skipped' and priority != 1) or (scope == 'urgent' and priority == 3):
            continue
        last = latest.get(guid)
        items.append({'iiko_product_id': guid, 'iiko_name': product.get('name'),
                      'iiko_article': product.get('num'), 'registry_status': status, 'priority': priority,
                      'on_tap': taps, 'proposal': _brief(last)})
    items.sort(key=lambda row: (row['priority'], (row['iiko_name'] or '').casefold(), row['iiko_product_id']))
    pending = sum(1 for row in items if (row['proposal'] or {}).get('status') == 'proposed')
    return {'scope': scope, 'items': items,
            'counts': {'total': len(items), 'on_tap': sum(1 for row in items if row['priority'] == 1),
                       'new': sum(1 for row in items if row['registry_status'] == 'new'),
                       'proposed': pending,
                       'rejected': sum(1 for row in items if (row['proposal'] or {}).get('status') == 'rejected'),
                       'waiting': sum(1 for row in items if (row['proposal'] or {}).get('status') != 'proposed')},
            'unidentified_taps': unidentified}


# ---------------------------------------------------------------------------
# Хранилище
# ---------------------------------------------------------------------------

def _check(data) -> dict:
    if not isinstance(data, dict) or data.get('schema_version') != SCHEMA_VERSION:
        raise UntappdLinksUnavailable('Файл связей с Untappd: неизвестная версия')
    if not isinstance(data.get('proposals'), list) or not isinstance(data.get('log'), list):
        raise UntappdLinksUnavailable('Файл связей с Untappd: нет списков proposals и log')
    for item in data['proposals']:
        if not isinstance(item, dict) or item.get('status') not in STATUSES or not item.get('id'):
            raise UntappdLinksUnavailable('Файл связей с Untappd: повреждённая запись')
    return data


class UntappdLinksStore:
    """Связи с Untappd на диске: threading.Lock + файловая блокировка, атомарная
    запись (как core/content_channels.ChannelsStore). now_fn — часы для тестов."""

    def __init__(self, data_file: Optional[str] = None, now_fn: Optional[Callable] = None):
        self.data_file = data_file or get_data_path(FILE_NAME)
        self._now_fn = now_fn or msk_time.now
        self._lock = threading.Lock()
        self._lock_path = self.data_file + '.lock'
        self._cache: Optional[Tuple[tuple, dict]] = None

    def now_str(self) -> str:
        moment = self._now_fn()
        if moment.tzinfo is not None:
            moment = moment.astimezone(msk_time.MOSCOW_TZ).replace(tzinfo=None)
        return moment.strftime('%Y-%m-%dT%H:%M')

    def _read(self) -> dict:
        """Разобранный файл — общий объект, менять нельзя (load() отдаёт копию).

        Файл читают на каждый запрос кранов (load_registry), поэтому разбор
        запоминается до изменения файла: ключ — (inode, время изменения, размер);
        запись атомарная (новый файл и переименование), так что любая запись, и из
        другого воркера, меняет ключ."""
        try:
            stat = os.stat(self.data_file)
        except FileNotFoundError:
            return _empty()
        except OSError as e:
            raise UntappdLinksUnavailable(f'Файл связей с Untappd не читается: {e}') from e
        key = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
        cached = self._cache
        if cached is not None and cached[0] == key:
            return cached[1]
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = _check(json.load(f))
        except (OSError, ValueError) as e:
            raise UntappdLinksUnavailable(f'Файл связей с Untappd не читается: {e}') from e
        self._cache = (key, data)
        return data

    def load(self) -> dict:
        """Данные (копия). Файл повреждён — UntappdLinksUnavailable."""
        return copy.deepcopy(self._read())

    def _save(self, data: dict) -> None:
        inactive = [p['id'] for p in data['proposals'] if p['status'] not in ('verified', 'proposed')]
        if len(inactive) > INACTIVE_MAX:
            drop = set(inactive[:-INACTIVE_MAX])
            data['proposals'] = [p for p in data['proposals'] if p['id'] not in drop]
        data['log'] = data['log'][-LOG_MAX:]
        atomic_write_json(self.data_file, data)

    def _tx(self, change: Callable[[dict, str], dict]) -> dict:
        with self._lock, file_lock(self._lock_path):
            data = copy.deepcopy(self._read())
            now = self.now_str()
            result = change(data, now)
            self._save(data)
            return copy.deepcopy(result)

    @staticmethod
    def _find(data: dict, pid: str) -> dict:
        for item in data['proposals']:
            if item['id'] == pid:
                return item
        raise UntappdLinksError('Предложение не найдено', code='not_found')

    def proposals(self, status: Optional[str] = None) -> List[dict]:
        """Предложения, новые первыми; status — один из STATUSES или None (все).

        Порядок — по времени последнего изменения (с точностью до минуты), при равенстве —
        позже записанное в файл первым: порядок не зависит от случайного id."""
        if status is not None and status not in STATUSES:
            raise UntappdLinksError('status: ' + ', '.join(STATUSES))
        rows = [(p.get('updated_at') or '', index, p) for index, p in enumerate(self.load()['proposals'])
                if status is None or p['status'] == status]
        rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [row[2] for row in rows]

    def propose(self, fields: dict, user: Optional[dict], registry: dict, catalog: dict) -> dict:
        """Новое предложение связи (черновик). registry — с наложенными связями,
        catalog — номенклатура кег (core/taplist.product_catalog)."""
        if not isinstance(fields, dict):
            raise UntappdLinksError('Нужен объект JSON')
        guid = parse_guid(fields.get('iiko_product_id'))
        product = catalog.get(guid)
        if product is None:
            raise UntappdLinksError('Товара с таким GUID нет среди кег номенклатуры (stocks_untappd_queue)',
                                    code='not_found')
        if resolve_beer(registry, guid):
            raise UntappdLinksError('У этого товара уже есть проверенная связь с Untappd', code='conflict')
        url, bid = parse_card_url(fields.get('untappd_url'))
        card = {'beer_name': _text(fields.get('beer_name'), 'beer_name', NAME_MAX, required=True),
                'brewery': _text(fields.get('brewery'), 'brewery', NAME_MAX, required=True),
                'style': _text(fields.get('style'), 'style', STYLE_MAX),
                'abv_percent': _number(fields.get('abv'), 'abv', ABV_MAX),
                'ibu': _number(fields.get('ibu'), 'ibu', IBU_MAX, integer=True),
                'description': _text(fields.get('description'), 'description', DESCRIPTION_MAX),
                'photo_url': None}
        warnings = []
        photo = str(fields.get('photo_url') or '').strip()
        if photo:
            if len(photo) <= URL_MAX and PHOTO_URL_RE.match(photo):
                card['photo_url'] = photo
            else:
                warnings.append('Фото (photo_url) не сохранено: принимается только с assets.untappd.com '
                                'или untappd.s3.amazonaws.com')
        names = {'style_ru': _text(fields.get('style_ru'), 'style_ru', STYLE_MAX),
                 'brewery_short': None}
        if fields.get('brewery_short') is not None:
            names['brewery_short'] = _text(fields.get('brewery_short'), 'brewery_short', NAME_MAX)
        reason = _text(fields.get('reason'), 'reason', REASON_MAX, required=True)
        evidence = _evidence(fields.get('evidence_urls'), url)
        user_name, origin = who(user), _origin(user)
        draft_mode = (user or {}).get('mcp_mode') == 'draft'

        def change(data, now):
            pending = [item for item in data['proposals']
                       if item['iiko_product_id'] == guid and item['status'] == 'proposed']
            # Коннектор «Чтение и черновики» правит только черновики агента (как контент-план):
            # предложение сотрудника ждёт решения владельца и не заменяется.
            if draft_mode and any(item.get('origin') != ORIGIN_AGENT for item in pending):
                raise UntappdLinksError('Для этой кеги ждёт решения предложение сотрудника: в режиме '
                                        '«Чтение и черновики» его не заменить', code='conflict')
            for item in pending:
                item['status'] = 'superseded'
                item['updated_at'] = now
            item = {'id': 'up_' + secrets.token_hex(6), 'iiko_product_id': guid,
                    'iiko_name': product.get('name'), 'iiko_article': product.get('num'),
                    'untappd_beer_id': bid, 'url': url, 'card': card, 'names': names,
                    'reason': reason, 'evidence_urls': evidence, 'status': 'proposed', 'origin': origin,
                    'created_at': now, 'created_by': user_name, 'updated_at': now,
                    'reviewed_at': None, 'reviewed_by': None, 'review_note': None, 'warnings': warnings}
            data['proposals'].append(item)
            data['log'].append({'at': now, 'by': user_name,
                                'text': f'Предложение {item["id"]}: «{product.get("name")}» -> {url}'})
            return item
        return self._tx(change)

    def confirm(self, pid: str, user: Optional[dict], registry: dict, fields: Optional[dict] = None) -> dict:
        """«Верно»: связь проверена и сразу действует. fields — правка имён для поста
        ({style_ru, brewery_short}) перед подтверждением."""
        fields = fields if isinstance(fields, dict) else {}
        style_ru = fields.get('style_ru')
        brewery_short = fields.get('brewery_short')
        if style_ru is not None:
            style_ru = _text(style_ru, 'style_ru', STYLE_MAX)
        if brewery_short is not None:
            brewery_short = _text(brewery_short, 'brewery_short', NAME_MAX)
        user_name = who(user)

        def change(data, now):
            item = self._find(data, pid)
            if item['status'] != 'proposed':
                raise UntappdLinksError(f'Предложение уже {STATUS_NAMES[item["status"]]}', code='conflict')
            if resolve_beer(registry, item['iiko_product_id']):
                raise UntappdLinksError('У этого товара уже есть проверенная связь с Untappd', code='conflict')
            names = dict(item.get('names') or {})
            if style_ru is not None:
                names['style_ru'] = style_ru
            if brewery_short is not None:
                names['brewery_short'] = brewery_short
            item.update(status='verified', names=names, reviewed_at=now, reviewed_by=user_name, updated_at=now)
            data['log'].append({'at': now, 'by': user_name,
                                'text': f'Подтверждена связь {pid}: «{item["iiko_name"]}» -> {item["url"]}'})
            return item
        return self._tx(change)

    def reject(self, pid: str, user: Optional[dict], note) -> dict:
        """«Не то»: предложение отклонено; причина видна агенту в очереди."""
        text = _text(note, 'note', NOTE_MAX)
        user_name = who(user)

        def change(data, now):
            item = self._find(data, pid)
            if item['status'] != 'proposed':
                raise UntappdLinksError(f'Предложение уже {STATUS_NAMES[item["status"]]}', code='conflict')
            item.update(status='rejected', review_note=text or None, reviewed_at=now, reviewed_by=user_name,
                        updated_at=now)
            data['log'].append({'at': now, 'by': user_name,
                                'text': f'Отклонено {pid}: «{item["iiko_name"]}» -> {item["url"]}'
                                        + (f' ({text})' if text else '')})
            return item
        return self._tx(change)

    def revoke(self, pid: str, user: Optional[dict], note=None) -> dict:
        """Отменить связь, подтверждённую на сайте: кега снова в очереди."""
        text = _text(note, 'note', NOTE_MAX)
        user_name = who(user)

        def change(data, now):
            item = self._find(data, pid)
            if item['status'] != 'verified':
                raise UntappdLinksError('Отменить можно только подтверждённую на сайте связь', code='conflict')
            item.update(status='revoked', review_note=text or item.get('review_note'), updated_at=now,
                        revoked_at=now, revoked_by=user_name)
            data['log'].append({'at': now, 'by': user_name,
                                'text': f'Отменена связь {pid}: «{item["iiko_name"]}» -> {item["url"]}'})
            return item
        return self._tx(change)


_STORE: Optional[UntappdLinksStore] = None


def get_store() -> UntappdLinksStore:
    """Хранилище по умолчанию (постоянный том). Тесты подменяют его set_store."""
    global _STORE
    if _STORE is None:
        _STORE = UntappdLinksStore()
    return _STORE


def set_store(store: Optional[UntappdLinksStore]) -> None:
    global _STORE
    _STORE = store
