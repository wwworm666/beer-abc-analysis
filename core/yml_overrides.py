"""Правки к позициям YML: скрыть, другое имя, цена или описание.

Файл общий для таплиста и кухни. Ключ — id позиции в фиде, поэтому правка
бара действует и в его ссылке, и в общем файле.
"""
import json
import os
import re
from decimal import Decimal, InvalidOperation

import portalocker

from core.storage_paths import get_data_path

_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$')


def overrides_path() -> str:
    return get_data_path('yml_overrides.json')


def load_overrides(path=None) -> dict:
    """{feed_id: {offer_id: правка}}. Кухня у баров разделена, хотя меню общее."""
    path = path or overrides_path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    feeds = data.get('feeds') if isinstance(data, dict) else None
    return feeds if isinstance(feeds, dict) else {}


def _clean(value, limit):
    text = ' '.join(str(value or '').split())
    return text[:limit]


def _price(value):
    if value is None or str(value).strip() == '':
        return ''
    try:
        number = Decimal(str(value).replace(',', '.').replace(' ', ''))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    return format(number.quantize(Decimal('0.01')), 'f')


def normalize_override(raw) -> dict:
    """Пустые поля означают «как в источнике». Нечисловая цена — ошибка."""
    raw = raw or {}
    price = _price(raw.get('price'))
    if price is None:
        raise ValueError('Цена должна быть числом больше нуля')
    name = _clean(raw.get('name'), 200)
    description = _clean(raw.get('description'), 3000)
    hidden = bool(raw.get('hidden'))
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


def save_overrides(feed_id, changes, path=None) -> dict:
    """changes: {offer_id: поля}. Пустой словарь по id удаляет правку этого фида."""
    if not isinstance(feed_id, str) or not re.fullmatch(r'[a-z0-9-]{1,40}', feed_id):
        raise ValueError('Некорректный фид')
    path = str(path or overrides_path())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock_path = path + '.lock'
    with portalocker.Lock(lock_path, timeout=10):
        current = load_overrides(path)
        bucket = dict(current.get(feed_id) or {})
        for offer_id, raw in (changes or {}).items():
            if not isinstance(offer_id, str) or not _ID.match(offer_id):
                raise ValueError('Некорректный id позиции')
            stored = normalize_override(raw)
            if stored:
                bucket[offer_id] = stored
            else:
                bucket.pop(offer_id, None)
        if bucket:
            current[feed_id] = bucket
        else:
            current.pop(feed_id, None)
        temporary = path + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as handle:
            json.dump({'feeds': current}, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    return current


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
