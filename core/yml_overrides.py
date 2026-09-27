"""Правки к позициям YML: скрыть, другое имя, цена или описание.

Файл yml_overrides.json (на проде /kultura). Схема 2:
    {"schema": 2, "feeds": {"kitchen": {offer_id: правка}, "bar1": {...}, ...},
     "acks": {ключ предупреждения: когда отмечено «Всё верно»}}
Кухня общая на все бары — её правки лежат в "kitchen". Пиво — по бару, ключ
позиции привязан к сорту (core/taplist_yml.offer_id). Схема 1 (до 2026-09-27)
хранила пиво по номеру крана; ensure_schema переносит её один раз.
Правила и формулы — docs/yandex-feeds.md.
"""
import hashlib
import json
import os
import re
import shutil
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import portalocker

from core.storage_paths import get_data_path
from core.yml_feeds import FEED_ORDER, KITCHEN_SCOPE, legacy_scopes, overrides_for_bar

SCHEMA = 2
FIELDS = ('hidden', 'name', 'price', 'description')
MAX_PRICE = Decimal('100000')
NAME_LIMIT = 200
DESCRIPTION_LIMIT = 3000
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$')
_SCOPE = re.compile(r'^[a-z0-9-]{1,40}$')
_OLD_TAP_ID = re.compile(r'^(bar\d+)-tap(\d+)-p05$')
_ACK = re.compile(r'^[0-9a-f]{20}$')
_CONTROL = re.compile('[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f\\ufffe\\uffff]')


class OverridesCorrupted(Exception):
    """Файл правок и его копия не читаются. Публиковать фид без правок нельзя:
    скрытые позиции снова попали бы на Карты."""


class OverrideConflict(Exception):
    """Кто-то сохранил эти позиции, пока страница была открыта."""

    def __init__(self, ids):
        super().__init__('Позиции изменил кто-то ещё')
        self.ids = list(ids)


def overrides_path() -> str:
    return get_data_path('yml_overrides.json')


def _read(path):
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get('feeds', {}), dict):
        raise ValueError('не тот формат')
    acks = data.get('acks')
    return {'schema': data.get('schema', 1), 'feeds': data.get('feeds') or {},
            'acks': acks if isinstance(acks, dict) else {}}


def load_document(path=None) -> dict:
    """{'schema': N, 'feeds': {...}, 'acks': {...}}. Битый файл — берётся копия .bak."""
    path = str(path or overrides_path())
    if not os.path.exists(path):
        return {'schema': SCHEMA, 'feeds': {}, 'acks': {}}
    try:
        return _read(path)
    except (OSError, ValueError) as error:
        print(f'[YML] файл правок не читается ({type(error).__name__}), беру копию .bak')
    try:
        return _read(path + '.bak')
    except (OSError, ValueError):
        raise OverridesCorrupted('Файл правок фидов повреждён, копии нет') from None


def load_overrides(path=None) -> dict:
    """{scope: {offer_id: правка}}."""
    return load_document(path)['feeds']


def _write(path, document):
    """Атомарно, с копией прошлой исправной версии в .bak."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    if os.path.exists(path):
        try:
            _read(path)
            shutil.copyfile(path, path + '.bak')
        except (OSError, ValueError):
            pass
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _clean(value, limit):
    """Управляющие символы убираются (ломают XML), пробелы и переводы строк
    схлопываются в один пробел: Яндекс показывает описание одним абзацем."""
    text = _CONTROL.sub(' ', str(value or ''))
    return ' '.join(text.split())[:limit]


def parse_price(value):
    """'1 000,5' -> '1000.50'. Пусто -> ''. Ошибка -> None.

    Округление до копеек ROUND_HALF_UP (0,125 -> 0,13), затем проверка
    0 < цена <= 100 000 — уже по округлённому значению.
    """
    if value is None or str(value).strip() == '':
        return ''
    text = re.sub(r'\s+', '', str(value)).replace(',', '.')
    try:
        number = Decimal(text)
        if not number.is_finite():
            return None
        number = number.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    if number <= 0 or number > MAX_PRICE:
        return None
    return format(number, 'f')


def normalize_override(raw, label=None) -> dict:
    """Пустые поля означают «как в источнике». Правка без полей и без скрытия
    удаляется. Нечисловая цена — ошибка с названием позиции."""
    raw = raw or {}
    price = parse_price(raw.get('price'))
    if price is None:
        prefix = f'«{label}»: ' if label else ''
        raise ValueError(prefix + 'цена должна быть числом от 0,01 до 100 000')
    name = _clean(raw.get('name'), NAME_LIMIT)
    description = _clean(raw.get('description'), DESCRIPTION_LIMIT)
    hidden = raw.get('hidden') is True
    if not hidden and not name and not description and not price:
        return {}
    stored = {'hidden': hidden}
    if name:
        stored['name'] = name
    if description:
        stored['description'] = description
    if price:
        stored['price'] = price
    return stored


def _check_id(offer_id):
    if not isinstance(offer_id, str) or not _ID.match(offer_id):
        raise ValueError('Некорректный id позиции')


def _set(feeds, scope, offer_id, stored):
    bucket = dict(feeds.get(scope) or {})
    if stored:
        bucket[offer_id] = stored
    else:
        bucket.pop(offer_id, None)
    if bucket:
        feeds[scope] = bucket
    else:
        feeds.pop(scope, None)


def apply_changes(bar_id, changes, kitchen_ids, path=None) -> dict:
    """Сохранить правки со страницы бара. -> новые правки {scope: {...}}.

    changes: {offer_id: {hidden, name, price, description, base?, label?}}.
    base — правка, которую страница видела при загрузке (null — правки не было).
    Если сейчас действует другая правка, ничего не пишется: OverrideConflict.
    Кухня (id из kitchen_ids) пишется в общий ключ и снимается с баров, чтобы
    общая правка действовала везде. Пиво — в ключ бара.
    """
    if bar_id not in FEED_ORDER:
        raise ValueError('Некорректный бар')
    if not isinstance(changes, dict):
        raise ValueError('Нет списка правок')
    kitchen_ids = set(kitchen_ids or ())
    prepared = []
    for offer_id, raw in changes.items():
        _check_id(offer_id)
        if not isinstance(raw, dict):
            raise ValueError('Некорректная правка')
        prepared.append((offer_id, raw, normalize_override(raw, raw.get('label') or offer_id)))
    path = str(path or overrides_path())
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with portalocker.Lock(path + '.lock', timeout=10):
        document = load_document(path)
        feeds = document['feeds']
        effective = overrides_for_bar(feeds, bar_id)
        conflicts = [offer_id for offer_id, raw, _ in prepared
                     if 'base' in raw and (effective.get(offer_id) or None) != (raw['base'] or None)]
        if conflicts:
            raise OverrideConflict(conflicts)
        for offer_id, _, stored in prepared:
            kitchen = offer_id in kitchen_ids or (
                offer_id in (feeds.get(KITCHEN_SCOPE) or {}) and not stored)
            if kitchen:
                _set(feeds, KITCHEN_SCOPE, offer_id, stored)
                for other in FEED_ORDER:
                    for scope in (*legacy_scopes(other), other):
                        _set(feeds, scope, offer_id, {})
            else:
                for scope in legacy_scopes(bar_id):
                    _set(feeds, scope, offer_id, {})
                _set(feeds, bar_id, offer_id, stored)
        _write(path, {'schema': SCHEMA, 'feeds': feeds, 'acks': document['acks']})
    return feeds


def notice_key(text) -> str:
    """Ключ предупреждения — хэш его текста. Текст включает блюда, цены, даты
    приказов или причину, поэтому любое изменение ситуации даёт новый ключ,
    и отмеченное «Всё верно» предупреждение появляется снова."""
    return hashlib.sha1(str(text).encode('utf-8')).hexdigest()[:20]


def load_acks(path=None) -> dict:
    """{ключ предупреждения: когда отмечено «Всё верно»}."""
    return load_document(path)['acks']


def set_acks(keys, acknowledged, when, path=None) -> dict:
    """Отметить предупреждения просмотренными (или вернуть). -> все отметки."""
    keys = list(keys or [])
    if not keys or any(not isinstance(key, str) or not _ACK.fullmatch(key) for key in keys):
        raise ValueError('Некорректный ключ предупреждения')
    path = str(path or overrides_path())
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with portalocker.Lock(path + '.lock', timeout=10):
        document = load_document(path)
        acks = dict(document['acks'])
        for key in keys:
            if acknowledged:
                acks[key] = when
            else:
                acks.pop(key, None)
        _write(path, {'schema': document['schema'], 'feeds': document['feeds'], 'acks': acks})
    return acks


def save_overrides(feed_id, changes, path=None) -> dict:
    """Записать правки в один ключ как есть (служебно и для тестов)."""
    if not isinstance(feed_id, str) or not _SCOPE.fullmatch(feed_id):
        raise ValueError('Некорректный фид')
    path = str(path or overrides_path())
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with portalocker.Lock(path + '.lock', timeout=10):
        document = load_document(path)
        feeds = document['feeds']
        for offer_id, raw in (changes or {}).items():
            _check_id(offer_id)
            _set(feeds, feed_id, offer_id, normalize_override(raw))
        _write(path, {'schema': document['schema'], 'feeds': feeds, 'acks': document['acks']})
    return feeds


def migrate_v1(feeds, kitchen_ids, tap_to_beer):
    """Схема 1 -> 2. -> (новые правки, отчёт строками).

    Пиво: ключ barN-tapM-p05 -> позиция сорта, который стоит на кране M сейчас
    (tap_to_beer: {(bar, M): untappd_id}). Перенесённая правка помечается
    migrated_from_tap — страница просит её проверить. Кран пуст — правка
    удаляется. Кухня: одинаковая правка во всех барах становится общей,
    разные остаются у своих баров.
    """
    from core.taplist_yml import offer_id as beer_offer_id
    kitchen_ids = set(kitchen_ids or ())
    result, report = {}, []
    per_bar = {bar: overrides_for_bar({k: v for k, v in feeds.items() if k != KITCHEN_SCOPE}, bar)
               for bar in FEED_ORDER}
    common = dict(feeds.get(KITCHEN_SCOPE) or {})
    for dish in sorted({i for bucket in per_bar.values() for i in bucket if i in kitchen_ids}):
        values = [per_bar[bar].get(dish) for bar in FEED_ORDER]
        if all(value is not None and value == values[0] for value in values):
            common[dish] = values[0]
            report.append(f'кухня {dish}: общая правка')
        else:
            for bar, value in zip(FEED_ORDER, values):
                if value is not None:
                    result.setdefault(bar, {})[dish] = value
            report.append(f'кухня {dish}: правки разные по барам, оставлены у баров')
    if common:
        result[KITCHEN_SCOPE] = common
    for bar in FEED_ORDER:
        for key, value in per_bar[bar].items():
            if key in kitchen_ids:
                continue
            match = _OLD_TAP_ID.match(key)
            if not match or match[1] != bar:
                result.setdefault(bar, {})[key] = value
                continue
            tap = int(match[2])
            untappd = tap_to_beer.get((bar, tap))
            if not untappd:
                report.append(f'{bar} кран {tap}: кран пуст или сорт не проверен, правка удалена')
                continue
            new_key = beer_offer_id(bar, untappd)
            bucket = result.setdefault(bar, {})
            if new_key in bucket:
                report.append(f'{bar} кран {tap}: у сорта уже есть правка с другого крана, эта удалена')
                continue
            bucket[new_key] = {**value, 'migrated_from_tap': tap}
            report.append(f'{bar} кран {tap} -> {new_key}')
    return result, report


def ensure_schema(kitchen_ids, tap_to_beer, path=None):
    """Перенести правки схемы 1 один раз. -> отчёт или None, если переносить нечего.

    tap_to_beer — функция без аргументов: читать таплист, только если перенос нужен.
    Исходный файл сохраняется рядом как .v1.bak.
    """
    path = str(path or overrides_path())
    if not os.path.exists(path):
        return None
    with portalocker.Lock(path + '.lock', timeout=10):
        document = load_document(path)
        if document['schema'] >= SCHEMA:
            return None
        feeds, report = migrate_v1(document['feeds'], kitchen_ids, tap_to_beer())
        if not os.path.exists(path + '.v1.bak'):
            shutil.copyfile(path, path + '.v1.bak')
        _write(path, {'schema': SCHEMA, 'feeds': feeds, 'acks': document['acks']})
    for line in report:
        print(f'[YML] перенос правок: {line}')
    return report


def merge_offer(item, override):
    """Эффективные поля для таблицы и для файла. source_* — значения до правки."""
    override = override or {}
    merged = dict(item)
    merged['source_name'] = item.get('name') or ''
    merged['source_price'] = item.get('price') or ''
    merged['source_description'] = item.get('description') or ''
    merged['hidden'] = bool(override.get('hidden'))
    if override.get('name'):
        merged['name'] = override['name']
    if override.get('description'):
        merged['description'] = override['description']
    if override.get('price'):
        merged['price'] = override['price']
    merged['edited'] = bool(override)
    return merged


def merge_offers(items, overrides):
    return [merge_offer(item, (overrides or {}).get(item.get('id'))) for item in items]
