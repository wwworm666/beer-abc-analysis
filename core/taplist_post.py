"""Таплист текстом: строка крана, ссылка на Untappd, новинки, свежесть кранов.

Одна строка для всех, кто показывает краны гостям: «Таплист пятницы» в каналах
баров (core/content_plan.render_live) и гостевой бот @kult_taplist_bot
(bar_message_html). Формат утвердил владелец 2026-10-04 — только текст, без цен:

    {кран}. {пивоварня и название} — {стиль}, {крепость}%[, новинка]

«Пивоварня и название» — ссылка на карточку Untappd (в посте — сущность Telegram
text_link, в боте — <a href> разметки HTML). Данные о пиве — только реестр Untappd
(core/untappd_registry, связь по GUID товара iiko) — единственный источник правды с
2026-10-04; имена и стили — из словаря resources/taplist_post_names.json. Правила с
примерами — docs/content-plan.md, раздел «Живые данные (таплист)».

Модуль без I/O при импорте: словарь читается при первом вызове load_names().
"""
import html
import json
import re
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from core import msk_time
from core.taplist import full_taplist, product_catalog
from core.untappd_registry import load_registry, resolve_beer

NAMES_PATH = Path(__file__).resolve().parents[1] / 'resources/taplist_post_names.json'

# «Новинка» (бриф, рубрика «Таплист пятницы»): сорт подключили в баре за NEW_DAYS
# дней до поста, а NEW_ABSENT_DAYS дней до этого его не было ни на одном кране бара.
# Новая кега того же сорта — не новинка: сорт в баре не прерывался.
NEW_DAYS = 7
NEW_ABSENT_DAYS = 30
NEW_MARK = 'новинка'

# Стоп (решение владельца 2026-10-04): на странице кранов бара STALE_TAPS_DAYS дней
# нет ни одного изменения (подключение, замена, снятие) — список мог устареть, пост
# этого бара не уходит. Краны меняются каждую неделю (бриф), две недели без единой
# отметки значат, что замены перестали отмечать.
STALE_TAPS_DAYS = 14

HISTORY_ACTIONS = ('start', 'replace', 'stop')
_BRACKETS_RE = re.compile(r'\s*\([^)]*\)')
# Имя кеги из iiko у крана без карточки Untappd: приставка «КЕГ»/«KEG» и объём в
# конце («30 л», «20л.», «, 20 л», одинокое «л») — служебные, гостю ничего не говорят.
_KEG_PREFIX_RE = re.compile(r'^(?:КЕГ|KEG)\s+', re.IGNORECASE)
_VOLUME_TAIL_RE = re.compile(r'(?:[\s,]*\d+(?:[.,]\d+)?\s*|\s+)(?:л|l)\.?$', re.IGNORECASE)


def format_abv(value) -> Optional[str]:
    """Крепость: half-up до 0,01, без хвостовых нулей, десятичная запятая.
    5.0 → '5', 6.5 → '6,5', 7.25 → '7,25'. Нечисло → None."""
    try:
        number = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    text = format(number, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text.replace('.', ',')


def utf16_len(text: str) -> int:
    """Длина в единицах UTF-16 — так Telegram считает offset и length сущностей."""
    return len((text or '').encode('utf-16-le')) // 2


def _clean(text) -> str:
    """Пробелы схлопнуты (в том числе неразрывные из карточек Untappd)."""
    return ' '.join(str(text or '').split())


def iiko_display(name) -> str:
    """Имя кеги из iiko для гостя: «КЕГ Вудбридж ИПА 30 л» -> «Вудбридж ИПА»,
    «КЕГ Джоус Мюних Хеллес, светлое,» -> «Джоус Мюних Хеллес, светлое». Ничего не
    осталось — имя как есть."""
    text = _KEG_PREFIX_RE.sub('', _clean(name))
    text = _VOLUME_TAIL_RE.sub('', text).strip(' ,')
    return text or _clean(name)


def tap_order(row: dict):
    """Порядок кранов: номера по возрастанию, затем нечисловые."""
    number = row.get('tap_number')
    try:
        return (0, int(number), '')
    except (TypeError, ValueError):
        return (1, 0, str(number))


# ---------------------------------------------------------------------------
# Словарь имён
# ---------------------------------------------------------------------------

def load_names(path=None) -> dict:
    """{styles, breweries, beers} из resources/taplist_post_names.json.

    styles — стиль Untappd -> по-русски; breweries — пивоварня Untappd -> короткое
    имя; beers — id Untappd -> название в посте целиком. Файл в репозитории и
    меняется только деплоем, поэтому читается один раз на путь. Без path к нему
    добавляются имена из связей, подтверждённых на сайте (core/untappd_live.live_names):
    стиль и пивоварня новой кеги, которых нет в словаре, — словарь главнее."""
    base = _load_names(str(path or NAMES_PATH))
    if path is not None:
        return base
    from core import untappd_live
    extra = untappd_live.live_names()
    if not extra['styles'] and not extra['breweries']:
        return base
    styles, breweries = dict(base['styles']), dict(base['breweries'])
    for key, value in extra['styles'].items():
        styles.setdefault(key, value)
    for key, value in extra['breweries'].items():
        breweries.setdefault(key, value)
    return {'styles': styles, 'breweries': breweries, 'beers': base['beers']}


@lru_cache(maxsize=4)
def _load_names(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    beers = {}
    for bid, item in (data.get('beers') or {}).items():
        post = item.get('post') if isinstance(item, dict) else item
        if _clean(post):
            beers[str(bid)] = _clean(post)
    return {'styles': dict(data.get('styles') or {}), 'breweries': dict(data.get('breweries') or {}),
            'beers': beers}


def post_name(row: dict, names: dict) -> str:
    """Пивоварня и название так, как их видит гость.

    1. Для сорта есть своё название (beers по id Untappd) — оно целиком.
    2. Иначе короткое имя пивоварни + название Untappd. Пивоварни нет в словаре —
       её имя без скобок. Пивоварню не пишем, если короткое имя пустое (марка уже
       в названии: Black Sheep) или уже есть в названии без учёта регистра
       («Palm Spéciale», а не «Palm Palm Spéciale»).
    Без карточки Untappd — имя кеги из iiko без «КЕГ» и объёма (iiko_display): такой
    кран останавливает «Таплист пятницы», а бот показывает его этим именем."""
    bid = row.get('untappd_beer_id')
    own = names['beers'].get(str(bid)) if bid not in (None, '') else None
    if own:
        return own
    name = _clean(row.get('beer_name') or row.get('iiko_name'))
    brewery = row.get('brewery')
    if not _clean(brewery):
        return name if bid not in (None, '') else iiko_display(name)
    short = brewery_short(brewery, names)
    if not short or short.casefold() in name.casefold():
        return name
    return f'{short} {name}'


def brewery_short(brewery, names: dict) -> str:
    """Пивоварня в посте: короткое имя из словаря (пустое — пивоварню не пишем), иначе
    её имя Untappd без скобок («Pivovar Tri Čuni (Tri Chuni)» -> «Pivovar Tri Čuni»)."""
    short = names['breweries'].get(brewery)
    if short is None:
        short = names['breweries'].get(_clean(brewery))
    if short is None:
        short = _BRACKETS_RE.sub('', str(brewery or ''))
    return _clean(short)


def style_ru(style, names: dict) -> str:
    """Стиль по-русски. Нет в словаре или в словаре пусто — '': английский стиль
    в пост не попадает (тест словаря требует запись для каждого стиля реестра)."""
    if not _clean(style):
        return ''
    found = names['styles'].get(style)
    if found is None:
        found = names['styles'].get(_clean(style), '')
    return _clean(found)


def _beer_info(row: dict, names: dict, is_new: bool) -> str:
    """' — {стиль}, {крепость}%[, новинка]' или '' (все части пусты)."""
    info = []
    style = style_ru(row.get('style'), names)
    if style:
        info.append(style)
    abv = format_abv(row.get('abv')) if row.get('abv') else None
    if abv and abv != '0':
        info.append(f'{abv}%')
    if is_new:
        info.append(NEW_MARK)
    return ' — ' + ', '.join(info) if info else ''


def beer_text(row: dict, names: dict, is_new: bool = False) -> str:
    """Строка сорта без номера крана: '{имя} — {стиль}, {крепость}%[, новинка]'.
    Так новый сорт показывается до подтверждения связи (страница «Связи с Untappd»)."""
    return post_name(row, names) + _beer_info(row, names, is_new)


def tap_line(row: dict, names: dict, is_new: bool = False) -> Tuple[str, Optional[Tuple[int, int]]]:
    """'{кран}. {имя} — {стиль}, {крепость}%[, новинка]' и (начало, конец) имени в
    строке — для ссылки на Untappd (None — ссылки нет: у крана нет карточки).

    Пустые части опускаются: без стиля — '{имя} — {крепость}%', без стиля и
    крепости — только имя. Крепость 0 и пустая не пишется."""
    head = f'{row.get("tap_number")}. '
    name = post_name(row, names)
    line = head + name
    span = (len(head), len(line)) if name and row.get('untappd_url') else None
    return line + _beer_info(row, names, is_new), span


# ---------------------------------------------------------------------------
# История кранов: новинки и свежесть
# ---------------------------------------------------------------------------

def parse_moment(value) -> Optional[datetime]:
    """Метка крана -> наивное московское время. Метки пишутся с зоной (+03:00);
    старые без зоны считаются московскими. Нечитаемая -> None."""
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(msk_time.MOSCOW_TZ).replace(tzinfo=None)
    return moment


def beer_key_fn(registry: Optional[dict]) -> Callable[[Optional[str], Optional[str]], str]:
    """Функция «какой это сорт» для событий кранов.

    Один сорт = одна карточка Untappd: кеги 20 и 30 л — разные товары iiko, но
    одно пиво. Порядок: товар iiko с проверенной карточкой -> 'untappd:<id>';
    старое событие без товара, чьё имя ровно совпадает с именем товара iiko в
    реестре -> карточка этого товара; иначе 'iiko:<GUID>'; иначе 'name:<имя>'."""
    registry = registry or {}
    by_name: Dict[str, str] = {}
    for guid, product in (registry.get('products') or {}).items():
        label = _clean(product.get('iiko_name'))
        if label and product.get('status') == 'verified':
            by_name.setdefault(label.casefold(), guid)
    cache: Dict[str, Optional[str]] = {}

    def card_id(guid):
        if guid not in cache:
            card = resolve_beer(registry, guid) if registry else None
            cache[guid] = str(card['id']) if card else None
        return cache[guid]

    def key(product_id, beer_name):
        if product_id:
            bid = card_id(product_id)
            return f'untappd:{bid}' if bid else f'iiko:{product_id}'
        label = _clean(beer_name).casefold()
        guid = by_name.get(label)
        if guid and card_id(guid):
            return f'untappd:{card_id(guid)}'
        return f'name:{label}' if label else ''

    return key


def _tap_segments(tap: dict, key) -> List[Tuple[Optional[datetime], Optional[datetime], str]]:
    """Периоды, когда на кране стоял сорт: (начало, конец, ключ). None в начале —
    раньше хранимой истории, None в конце — стоит сейчас.

    События идут по времени: start / replace — на кране новый сорт, stop — кран
    пуст. До первого события: если первое — stop, стоял его сорт (подключение ушло
    за пределы истории); иначе кран был пуст. Текущее подключение, которого нет в
    истории (старые данные), берётся из started_at; без started_at — «давно»."""
    events = []
    for event in tap.get('history') or []:
        moment = parse_moment(event.get('timestamp'))
        if moment is not None and event.get('action') in HISTORY_ACTIONS:
            events.append((moment, event))
    events.sort(key=lambda item: item[0])
    segments = []
    current: Optional[Tuple[Optional[datetime], str]] = None
    if events and events[0][1]['action'] == 'stop':
        first = events[0][1]
        current = (None, key(first.get('iiko_product_id'), first.get('beer_name')))
    for moment, event in events:
        if current is not None:
            segments.append((current[0], moment, current[1]))
            current = None
        if event['action'] != 'stop':
            current = (moment, key(event.get('iiko_product_id'), event.get('beer_name')))
    active = tap.get('status') == 'active' and tap.get('current_beer')
    now_key = key(tap.get('iiko_product_id'), tap.get('current_beer')) if active else None
    if current is not None and (not active or current[1] != now_key):
        # история говорит «стоит X», а кран пуст или на нём другое — закрываем
        # период его подключением (started_at), иначе он тянулся бы до сих пор
        segments.append((current[0], parse_moment(tap.get('started_at')) or current[0], current[1]))
        current = None
    if active:
        if current is None:
            current = (parse_moment(tap.get('started_at')), now_key)
        segments.append((current[0], None, current[1]))
    return segments


def new_beer_keys(bar: dict, registry: Optional[dict], moment: datetime) -> Set[str]:
    """Ключи сортов бара, которые в посте на moment помечаются «новинка».

    Новинка ⇔ сорт сейчас на кране и ни на одном кране бара не стоял в окне
    [moment − NEW_DAYS − NEW_ABSENT_DAYS, moment − NEW_DAYS) — правый край не
    входит: подключили ровно за 7 суток до поста — ещё новинка. Пример (пост
    9 октября 16:00): окно — со 2 сентября 16:00 до 2 октября 16:00. Подключили
    5 октября, в сентябре не было — новинка; стоял с 20 сентября — нет; был в
    августе, вернулся 5 октября — новинка."""
    key = beer_key_fn(registry)
    window_end = moment - timedelta(days=NEW_DAYS)
    window_start = window_end - timedelta(days=NEW_ABSENT_DAYS)
    now_on: Set[str] = set()
    seen: Set[str] = set()
    for tap in bar.get('taps') or []:
        for start, end, beer in _tap_segments(tap, key):
            if not beer:
                continue
            if end is None:
                now_on.add(beer)
            # период пересекает окно: начался до его конца и закончился после начала
            if (start is None or start < window_end) and (end is None or end > window_start):
                seen.add(beer)
    return now_on - seen


def row_key(row: dict, registry: Optional[dict]) -> str:
    """Ключ сорта для строки таплиста (core.taplist.full_taplist)."""
    return beer_key_fn(registry)(row.get('iiko_product_id'), row.get('iiko_name'))


def last_change(bar: dict) -> Optional[datetime]:
    """Последнее изменение на странице кранов бара: самое позднее из событий
    истории (подключение, замена, снятие) и started_at кранов. Нет ни одного — None."""
    latest = None
    for tap in bar.get('taps') or []:
        stamps = [event.get('timestamp') for event in tap.get('history') or []
                  if event.get('action') in HISTORY_ACTIONS]
        stamps.append(tap.get('started_at'))
        for stamp in stamps:
            moment = parse_moment(stamp) if stamp else None
            if moment is not None and (latest is None or moment > latest):
                latest = moment
    return latest


def days_word(count: int) -> str:
    """1 день, 2 дня, 5 дней, 11 дней, 21 день."""
    tail = count % 100
    if 11 <= tail <= 14:
        return 'дней'
    return {1: 'день', 2: 'дня', 3: 'дня', 4: 'дня'}.get(count % 10, 'дней')


def stale_problem(bar: dict, moment: datetime, date_text: Callable[[datetime], str]) -> Optional[str]:
    """Текст стоп-правила stale_taps или None, если краны бара свежие.

    Свежие — последнее изменение не раньше чем за STALE_TAPS_DAYS суток до
    moment. Дни в тексте — полные сутки: изменение 11 августа 14:22, пост
    9 октября 16:00 — «59 дней»."""
    changed = last_change(bar)
    if changed is None:
        return 'на странице кранов бара нет ни одной отметки о замене кег — список не проверить'
    if moment - changed <= timedelta(days=STALE_TAPS_DAYS):
        return None
    days = (moment - changed).days
    return (f'краны бара не обновлялись {days} {days_word(days)} (последнее изменение '
            f'{date_text(changed)}) — список мог устареть')


# ---------------------------------------------------------------------------
# Краны бара: строки для поста и гостевого бота
# ---------------------------------------------------------------------------

def bar_rows(snapshot: dict, registry: dict, bar_id: str, moment: datetime) -> Tuple[List[dict], List[bool]]:
    """Активные краны бара по порядку и пометка «новинка» для каждого.

    Строки — core.taplist.full_taplist: карточка Untappd только по проверенной связи
    GUID товара (реестр). Бара нет в снимке — KeyError (как у full_taplist)."""
    rows = sorted(full_taplist(snapshot, registry, bar_id, active_only=True), key=tap_order)
    fresh = new_beer_keys(snapshot[bar_id], registry, moment)
    key = beer_key_fn(registry)
    return rows, [key(row.get('iiko_product_id'), row.get('iiko_name')) in fresh for row in rows]


def line_html(line: str, span: Optional[Tuple[int, int]], url: Optional[str]) -> str:
    """Строка крана для Telegram с parse_mode HTML: имя — <a href> на Untappd, текст
    экранирован (в названии пива бывают «&» и «<»). Без ссылки — только экранирование."""
    if not span or not url:
        return html.escape(line, quote=False)
    begin, end = span
    return (html.escape(line[:begin], quote=False) + f'<a href="{html.escape(url, quote=True)}">'
            + html.escape(line[begin:end], quote=False) + '</a>' + html.escape(line[end:], quote=False))


def bar_message_html(manager, bar_id: str, title: str, moment: Optional[datetime] = None,
                     registry: Optional[dict] = None, names: Optional[dict] = None) -> str:
    """Таплист бара для гостевого бота: заголовок с баром и те же строки, что в
    «Таплисте пятницы» (HTML). Пустой бар — «<бар>: нет активных кранов».

    manager — менеджер кранов (снимок читается на каждый вызов: страница кранов пишет
    файл, а бот живёт сутками); registry и names — для тестов, по умолчанию реестр
    Untappd и словарь имён; moment — для «новинки», по умолчанию сейчас по Москве."""
    registry = load_registry() if registry is None else registry
    names = names or load_names()
    moment = moment or msk_time.now().replace(tzinfo=None)
    snapshot = manager.get_snapshot(product_catalog(registry))
    rows, news = bar_rows(snapshot, registry, bar_id, moment)
    head = html.escape(title, quote=False)
    if not rows:
        return f'{head}: нет активных кранов'
    lines = []
    for row, is_new in zip(rows, news):
        line, span = tap_line(row, names, is_new)
        lines.append(line_html(line, span, row.get('untappd_url')))
    return f'<b>{head}</b>\n\n' + '\n'.join(lines)
