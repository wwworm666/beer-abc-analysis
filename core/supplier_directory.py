"""Справочник поставщиков: имя, алиасы написаний, срок и дни поставки, кратность.

Зачем. Поставщик на странице заказа — сырая строка category из номенклатуры
iiko: три написания одного «МаркетБир» дают три группы, а сроки поставки жили
в коде (SUPPLIER_PARAMS в routes/stocks.py, только 13 кухонных поставщиков,
все пивные по умолчанию). Этап 3 редизайна (docs/planning/
stocks-order-redesign-2026-09-10.md): справочник редактируется из интерфейса
(/suppliers), код хранит только стартовые значения (SEED_SUPPLIERS) и умолчания.

Хранение. suppliers.json на постоянном томе (/kultura) или в data/ локально
(core/storage_paths.get_data_path); запись атомарная под cross-worker lock
(core/json_store), как у заказов. Файла нет → в памяти действует SEED_SUPPLIERS,
на диск он попадает при первом сохранении из интерфейса.

Модель.
    suppliers[name] = {name, aliases: [str], lead_time_days: int,
                       delivery_weekdays: [0..6], pack_size: int,
                       self_pickup: bool, note: str,
                       updated_at, updated_by}

Разрешение имени (resolve): точное имя → оно; иначе алиас после нормализации
(регистр, лишние пробелы, кавычки) → каноническое имя; иначе сама строка
category (или NO_SUPPLIER для пустой). Параметры (params): у известного
поставщика — его, у неизвестного — умолчания с флагом is_default, чтобы
интерфейс мог подписать «по умолчанию».
"""
import json
import os
import re
import threading
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from core.json_store import atomic_write_json, file_lock
from core.storage_paths import get_data_path
from core.supplier_calendar import DEFAULT_DELIVERY_WEEKDAYS

SCHEMA_VERSION = 1
NO_SUPPLIER = 'Без поставщика'          # позиции без category в номенклатуре
DEFAULT_LEAD_TIME_DAYS = 3              # срок поставки, если поставщик не заведён
DEFAULT_PACK_SIZE = 1                   # кратность (упаковка); для кег всегда 1
MAX_LEAD_TIME_DAYS = 60
MAX_PACK_SIZE = 10000
MAX_NAME_LEN = 120

# Стартовые значения (бывший SUPPLIER_PARAMS routes/stocks.py, 2026-04-27):
# подобраны эмпирически по типу поставщика; владелец правит в /suppliers.
SEED_SUPPLIERS = {
    'Метро':                       {'lead_time_days': 1, 'self_pickup': True},
    'Лента':                       {'lead_time_days': 1, 'self_pickup': True},
    'ООО "Май"':                   {'lead_time_days': 2},
    'ИП Тихомиров':                {'lead_time_days': 2},
    'ООО "Кулинарпродторг"':       {'lead_time_days': 2},
    'ИП Новиков':                  {'lead_time_days': 3},
    'ООО "Арбореал"':              {'lead_time_days': 3},
    'Криспи':                      {'lead_time_days': 3},
    'ООО "ВУРСТХАУСМАНУФАКТУР"':   {'lead_time_days': 3},
    'ООО "КВГ"':                   {'lead_time_days': 2},
    'ГС Маркет':                   {'lead_time_days': 2},
    'ООО МП Арсенал':              {'lead_time_days': 3, 'aliases': ['ООО "МП-Арсенал АО"']},
}

_QUOTES = '"«»\'`'
_WS = re.compile(r'\s+')


def normalize_name(value: Optional[str]) -> str:
    """Ключ сравнения написаний: без регистра, кавычек и лишних пробелов."""
    s = str(value or '')
    s = s.translate({ord(c): None for c in _QUOTES})
    return _WS.sub(' ', s).strip().casefold()


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _user_login(user: Optional[dict]) -> str:
    if not user:
        return 'unknown'
    return user.get('login') or user.get('display_name') or 'unknown'


def _int(value, default: int, lo: int, hi: int, field: str) -> int:
    if value is None or value == '':
        return default
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        raise ValueError(f'{field}: нужно целое число')
    if n < lo or n > hi:
        raise ValueError(f'{field}: от {lo} до {hi}')
    return n


def _weekdays(value) -> List[int]:
    if value is None:
        return list(DEFAULT_DELIVERY_WEEKDAYS)
    if not isinstance(value, (list, tuple)):
        raise ValueError('Дни доставки: нужен список дней 0..6 (пн = 0)')
    days = set()
    for d in value:
        try:
            n = int(d)
        except (TypeError, ValueError):
            raise ValueError('Дни доставки: день должен быть числом 0..6')
        if n < 0 or n > 6:
            raise ValueError('Дни доставки: день должен быть числом 0..6')
        days.add(n)
    if not days:
        raise ValueError('Дни доставки: нужен хотя бы один день')
    return sorted(days)


def _aliases(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [v for v in re.split(r'[\n;,]', value)]
    if not isinstance(value, (list, tuple)):
        raise ValueError('Написания: нужен список строк')
    result, seen = [], set()
    for a in value:
        s = _WS.sub(' ', str(a or '')).strip()
        if not s:
            continue
        key = normalize_name(s)
        if key in seen:
            continue
        seen.add(key)
        result.append(s[:MAX_NAME_LEN])
    return result


def make_record(name: str, fields: Optional[dict] = None, base: Optional[dict] = None) -> dict:
    """Собрать/проверить запись поставщика; ValueError с понятным текстом."""
    fields = fields or {}
    base = base or {}
    name = _WS.sub(' ', str(name or '')).strip()
    if not name:
        raise ValueError('Имя поставщика обязательно')
    if len(name) > MAX_NAME_LEN:
        raise ValueError(f'Имя поставщика длиннее {MAX_NAME_LEN} символов')

    def pick(key, default):
        return fields[key] if key in fields else base.get(key, default)

    record = {
        'name': name,
        'aliases': _aliases(pick('aliases', [])),
        'lead_time_days': _int(pick('lead_time_days', DEFAULT_LEAD_TIME_DAYS), DEFAULT_LEAD_TIME_DAYS,
                               0, MAX_LEAD_TIME_DAYS, 'Срок поставки'),
        'delivery_weekdays': _weekdays(pick('delivery_weekdays', None)),
        'pack_size': _int(pick('pack_size', DEFAULT_PACK_SIZE), DEFAULT_PACK_SIZE, 1, MAX_PACK_SIZE, 'Кратность'),
        'self_pickup': bool(pick('self_pickup', False)),
        'note': str(pick('note', '') or '')[:500],
    }
    # алиас, совпадающий с самим именем, лишний
    record['aliases'] = [a for a in record['aliases'] if normalize_name(a) != normalize_name(name)]
    return record


def seed_records() -> Dict[str, dict]:
    return {name: make_record(name, fields) for name, fields in SEED_SUPPLIERS.items()}


class SupplierParams(dict):
    """Параметры для формулы: dict с ключами name, lead_time_days, pack_size,
    delivery_weekdays, self_pickup, is_default (поставщик не заведён)."""


class DirectoryView:
    """Неизменяемый срез справочника на один запрос: resolve() и params()."""

    def __init__(self, suppliers: Dict[str, dict]):
        self.suppliers = suppliers
        self._by_key: Dict[str, str] = {}
        for name, rec in suppliers.items():
            self._by_key.setdefault(normalize_name(name), name)
        for name, rec in suppliers.items():
            for alias in rec.get('aliases') or []:
                self._by_key.setdefault(normalize_name(alias), name)

    def resolve(self, category: Optional[str]) -> str:
        raw = _WS.sub(' ', str(category or '')).strip()
        if not raw:
            return NO_SUPPLIER
        return self._by_key.get(normalize_name(raw), raw)

    def get(self, name: str) -> Optional[dict]:
        return self.suppliers.get(self._by_key.get(normalize_name(name), name))

    def params(self, category_or_name: Optional[str]) -> SupplierParams:
        name = self.resolve(category_or_name)
        rec = self.suppliers.get(name)
        if rec is None:
            return SupplierParams(name=name, lead_time_days=DEFAULT_LEAD_TIME_DAYS,
                                  pack_size=DEFAULT_PACK_SIZE,
                                  delivery_weekdays=list(DEFAULT_DELIVERY_WEEKDAYS),
                                  self_pickup=False, is_default=True)
        return SupplierParams(name=name, lead_time_days=rec['lead_time_days'],
                              pack_size=rec['pack_size'],
                              delivery_weekdays=list(rec['delivery_weekdays']),
                              self_pickup=bool(rec.get('self_pickup')), is_default=False)


class SupplierDirectory:
    def __init__(self, data_file: Optional[str] = None):
        self.data_file = data_file or get_data_path('suppliers.json')
        self._lock = threading.Lock()
        self._lock_path = self.data_file + '.lock'
        self._cache: Optional[Dict[str, dict]] = None
        self._cache_mtime: Optional[float] = None

    # ----- файл ------------------------------------------------------------

    def _load(self) -> Dict[str, dict]:
        """Записи справочника; без файла — стартовый набор (в памяти)."""
        if not os.path.exists(self.data_file):
            self._cache, self._cache_mtime = None, None
            return seed_records()
        try:
            mtime = os.path.getmtime(self.data_file)
            if self._cache is not None and self._cache_mtime == mtime:
                return {k: dict(v) for k, v in self._cache.items()}
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[SUPPLIERS] cannot read {self.data_file}: {e}")
            return seed_records()
        raw = data.get('suppliers') if isinstance(data, dict) else None
        result: Dict[str, dict] = {}
        for name, rec in (raw or {}).items():
            if not isinstance(rec, dict):
                continue
            try:
                fixed = make_record(name, rec)
            except ValueError as e:
                print(f"[SUPPLIERS] skip broken record {name!r}: {e}")
                continue
            fixed['updated_at'] = rec.get('updated_at')
            fixed['updated_by'] = rec.get('updated_by')
            result[fixed['name']] = fixed
        self._cache, self._cache_mtime = {k: dict(v) for k, v in result.items()}, mtime
        return result

    def _save(self, suppliers: Dict[str, dict]) -> None:
        atomic_write_json(self.data_file, {'version': SCHEMA_VERSION, 'suppliers': suppliers})
        self._cache, self._cache_mtime = None, None

    # ----- чтение ----------------------------------------------------------

    def is_stored(self) -> bool:
        """Есть ли файл на диске (иначе действует стартовый набор в памяти)."""
        return os.path.exists(self.data_file)

    def view(self) -> DirectoryView:
        return DirectoryView(self._load())

    def list(self) -> List[dict]:
        return sorted(self._load().values(), key=lambda r: normalize_name(r['name']))

    def get(self, name: str) -> Optional[dict]:
        return self.view().get(name)

    # ----- запись ----------------------------------------------------------

    @staticmethod
    def _check_unique(suppliers: Dict[str, dict], record: dict) -> None:
        """Имя и алиасы не должны совпадать с именами/алиасами других поставщиков."""
        own = normalize_name(record['name'])
        taken: Dict[str, str] = {}
        for name, rec in suppliers.items():
            if normalize_name(name) == own:
                continue
            taken[normalize_name(name)] = name
            for a in rec.get('aliases') or []:
                taken.setdefault(normalize_name(a), name)
        if own in taken:
            raise ValueError(f'«{record["name"]}» уже используется у поставщика «{taken[own]}»')
        for a in record['aliases']:
            key = normalize_name(a)
            if key in taken:
                raise ValueError(f'Алиас «{a}» уже принадлежит поставщику «{taken[key]}»')

    def upsert(self, name: str, fields: dict, user: Optional[dict], rename_to: Optional[str] = None) -> dict:
        """Создать или обновить поставщика; rename_to переименовывает (алиасы сохраняются)."""
        with self._lock, file_lock(self._lock_path):
            suppliers = self._load()
            existing_key = None
            for key in suppliers:
                if normalize_name(key) == normalize_name(name):
                    existing_key = key
                    break
            base = suppliers.get(existing_key) if existing_key else None
            new_name = rename_to if rename_to else (existing_key or name)
            record = make_record(new_name, fields, base)
            if existing_key and normalize_name(new_name) != normalize_name(existing_key):
                suppliers.pop(existing_key)
            self._check_unique(suppliers, record)
            record['updated_at'] = _now()
            record['updated_by'] = _user_login(user)
            suppliers[record['name']] = record
            self._save(suppliers)
        return record

    def delete(self, name: str) -> bool:
        with self._lock, file_lock(self._lock_path):
            suppliers = self._load()
            key = next((k for k in suppliers if normalize_name(k) == normalize_name(name)), None)
            if key is None:
                return False
            suppliers.pop(key)
            self._save(suppliers)
        return True

    def add_alias(self, name: str, alias: str, user: Optional[dict]) -> dict:
        rec = self.get(name)
        if rec is None:
            raise KeyError(name)
        aliases = list(rec.get('aliases') or []) + [alias]
        return self.upsert(rec['name'], {'aliases': aliases}, user)


_directory: Optional[SupplierDirectory] = None
_directory_guard = threading.Lock()


def get_supplier_directory() -> SupplierDirectory:
    """Ленивый синглтон на процесс (файл на томе общий для воркеров)."""
    global _directory
    with _directory_guard:
        if _directory is None:
            _directory = SupplierDirectory()
        return _directory


def categories_in_use(nomenclature: Dict[str, dict], product_types: Iterable[str] = ('GOODS', 'PREPARED')) -> Dict[str, int]:
    """{category: число товаров} по номенклатуре — подсказка для заведения алиасов."""
    wanted = set(product_types)
    counts: Dict[str, int] = {}
    for info in (nomenclature or {}).values():
        if not isinstance(info, dict) or info.get('type') not in wanted:
            continue
        cat = _WS.sub(' ', str(info.get('category') or '')).strip() or NO_SUPPLIER
        counts[cat] = counts.get(cat, 0) + 1
    return counts
