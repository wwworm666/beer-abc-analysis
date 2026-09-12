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
на диск он попадает при первом сохранении из интерфейса. Файл есть, но не
читается или содержит битую запись → чтение отдаёт стартовый набор (доска
должна открываться), а запись запрещена (SupplierDirectoryUnavailable): иначе
одна правка стёрла бы весь справочник (урок docs/lessons.md «Backup перед записью»).

Модель.
    suppliers[name] = {name, aliases: [str], lead_time_days: int,
                       delivery_weekdays: [0..6], pack_size: int,
                       self_pickup: bool, note: str,
                       updated_at, updated_by}

Разрешение имени (resolve): точное имя → оно; иначе алиас после нормализации
(регистр, кавычки, лишние пробелы) → каноническое имя; иначе сама строка
category (или NO_SUPPLIER для пустой). Параметры (params): у известного
поставщика — его, у неизвестного — умолчания с флагом is_default, чтобы
интерфейс мог подписать «по умолчанию».
"""
import copy
import json
import os
import re
import threading
from typing import Dict, Iterable, List, Optional

from core import msk_time
from core.json_store import atomic_write_json, file_lock
from core.storage_paths import get_data_path
from core.supplier_calendar import DEFAULT_DELIVERY_WEEKDAYS

SCHEMA_VERSION = 1
NO_SUPPLIER = 'Без поставщика'          # позиции без category в номенклатуре
DEFAULT_LEAD_TIME_DAYS = 3              # срок поставки, если поставщик не заведён
DEFAULT_PACK_SIZE = 1                   # кратность (упаковка); для кег всегда 1
MIN_LEAD_TIME_DAYS = 1                  # поставка раньше следующего дня доставки не бывает
MAX_LEAD_TIME_DAYS = 60
MAX_PACK_SIZE = 10000
MAX_NAME_LEN = 120

# Стартовые значения. Кухонные — бывший SUPPLIER_PARAMS routes/stocks.py (2026-04-27),
# подобраны эмпирически; пивные добавлены 2026-09-12 по категориям номенклатуры
# (ревью этапа 3: без них 90 % позиций были «по умолчанию»), срок у всех 3 дня до
# уточнения владельцем на /suppliers. Написания МаркетБир склеены сразу.
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
    'ООО Невский Синдикат':        {'lead_time_days': 3},
    'ООО Фёст':                    {'lead_time_days': 3},
    'ООО МаркетБир':               {'lead_time_days': 3, 'aliases': ['ООО "МаркетБир"', 'Маркет бир']},
    'СПБ-Премиум':                 {'lead_time_days': 3},
    'Партнер ООО':                 {'lead_time_days': 3},
    'БирИнсайдерс':                {'lead_time_days': 3},
    'ДримТим':                     {'lead_time_days': 3},
    'ЕГАИС':                       {'lead_time_days': 3},
    'ООО ТК Параллель':            {'lead_time_days': 3},
}

# Кавычки всех видов, включая типографские: «ООО “Май”» и «ООО "Май"» — одно написание.
_QUOTES = '"«»\'`“”„‟‘’‚'
_WS = re.compile(r'\s+')
_MISSING = object()
_TRUE_WORDS = {'1', 'true', 'yes', 'on', 'да'}
_FALSE_WORDS = {'', '0', 'false', 'no', 'off', 'нет', 'none', 'null'}


class SupplierDirectoryUnavailable(RuntimeError):
    """Файл справочника есть, но прочитать его нельзя: писать поверх запрещено."""


def normalize_name(value: Optional[str]) -> str:
    """Ключ сравнения написаний: без регистра, кавычек и лишних пробелов."""
    s = str(value or '')
    s = s.translate({ord(c): None for c in _QUOTES})
    return _WS.sub(' ', s).strip().casefold()


def _now() -> str:
    return msk_time.now().isoformat(timespec='seconds')


def _user_login(user: Optional[dict]) -> str:
    if not user:
        return 'unknown'
    return user.get('login') or user.get('display_name') or 'unknown'


def _int(value, default: int, lo: int, hi: int, field: str) -> int:
    if value is None or value == '':
        return default
    try:
        n = int(float(value))
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f'{field}: нужно целое число')
    if n < lo or n > hi:
        raise ValueError(f'{field}: от {lo} до {hi}')
    return n


def _bool(value) -> bool:
    """Флаг из JSON или формы: строки 'false'/'нет'/'0' — ложь, а не bool('false')."""
    if isinstance(value, str):
        word = value.strip().casefold()
        if word in _FALSE_WORDS:
            return False
        if word in _TRUE_WORDS:
            return True
        raise ValueError(f'Флаг должен быть да/нет, а не «{value}»')
    return bool(value)


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


def clean_name(name) -> str:
    return _WS.sub(' ', str(name or '')).strip().strip('/')


def make_record(name: str, fields: Optional[dict] = None, base: Optional[dict] = None) -> dict:
    """Собрать/проверить запись поставщика; ValueError с понятным текстом.

    Поле, которого нет в fields или которое передано как null, берётся из base
    («только переданные поля меняются»), иначе — умолчание.
    """
    fields = fields or {}
    base = base or {}
    name = clean_name(name)
    if not name:
        raise ValueError('Имя поставщика обязательно')
    if len(name) > MAX_NAME_LEN:
        raise ValueError(f'Имя поставщика длиннее {MAX_NAME_LEN} символов')

    def pick(key, default):
        value = fields.get(key, _MISSING)
        if value is _MISSING or value is None:
            value = base.get(key, _MISSING)
        return default if value is _MISSING or value is None else value

    record = {
        'name': name,
        'aliases': _aliases(pick('aliases', [])),
        'lead_time_days': _int(pick('lead_time_days', DEFAULT_LEAD_TIME_DAYS), DEFAULT_LEAD_TIME_DAYS,
                               MIN_LEAD_TIME_DAYS, MAX_LEAD_TIME_DAYS, 'Срок поставки'),
        'delivery_weekdays': _weekdays(pick('delivery_weekdays', None)),
        'pack_size': _int(pick('pack_size', DEFAULT_PACK_SIZE), DEFAULT_PACK_SIZE, 1, MAX_PACK_SIZE, 'Кратность'),
        'self_pickup': _bool(pick('self_pickup', False)),
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
        # Кэш по mtime — один неизменяемый кортеж (mtime, данные): читатели из других
        # потоков берут его целиком, а не два поля по отдельности (gthread, 4 потока).
        self._cache: Optional[tuple] = None

    # ----- файл ------------------------------------------------------------

    def _load(self, strict: bool = False) -> Dict[str, dict]:
        """Записи справочника.

        Нет файла — стартовый набор. Файл не читается или содержит битую запись:
        strict=False (чтение для доски) — стартовый набор / пропуск записи с
        сообщением в лог; strict=True (перед записью) — SupplierDirectoryUnavailable.
        """
        if not os.path.exists(self.data_file):
            return seed_records()
        try:
            mtime = os.path.getmtime(self.data_file)
            cached = self._cache
            if not strict and cached is not None and cached[0] == mtime:
                return copy.deepcopy(cached[1])
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[SUPPLIERS] cannot read {self.data_file}: {e}")
            if strict:
                raise SupplierDirectoryUnavailable(f'Файл справочника не читается: {e}') from e
            return seed_records()
        raw = data.get('suppliers') if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            print(f"[SUPPLIERS] unexpected structure in {self.data_file}")
            if strict:
                raise SupplierDirectoryUnavailable('Файл справочника повреждён: неожиданная структура')
            return seed_records()
        result: Dict[str, dict] = {}
        skipped = False
        for name, rec in raw.items():
            if not isinstance(rec, dict):
                rec = None
            try:
                fixed = make_record(name, rec or {})
            except ValueError as e:
                print(f"[SUPPLIERS] broken record {name!r}: {e}")
                if strict:
                    raise SupplierDirectoryUnavailable(f'Запись «{name}» повреждена: {e}') from e
                skipped = True
                continue
            fixed['updated_at'] = (rec or {}).get('updated_at')
            fixed['updated_by'] = (rec or {}).get('updated_by')
            result[fixed['name']] = fixed
        # Неполный результат (с пропущенной записью) не кэшируем: строгое чтение перед
        # записью всегда идёт в файл и обязано увидеть битую запись.
        if not skipped:
            self._cache = (mtime, copy.deepcopy(result))
        return result

    def _save(self, suppliers: Dict[str, dict]) -> None:
        atomic_write_json(self.data_file, {'version': SCHEMA_VERSION, 'suppliers': suppliers})
        self._cache = None

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
    def _find_key(suppliers: Dict[str, dict], name: str) -> Optional[str]:
        wanted = normalize_name(name)
        return next((k for k in suppliers if normalize_name(k) == wanted), None)

    @staticmethod
    def _check_unique(others: Dict[str, dict], record: dict) -> None:
        """Имя и алиасы записи не должны совпадать с именами/алиасами ДРУГИХ поставщиков
        (сама запись из others уже убрана)."""
        taken: Dict[str, str] = {}
        for name, rec in others.items():
            taken.setdefault(normalize_name(name), name)
            for a in rec.get('aliases') or []:
                taken.setdefault(normalize_name(a), name)
        own = normalize_name(record['name'])
        if own in taken:
            raise ValueError(f'Имя «{record["name"]}» уже занято поставщиком «{taken[own]}»')
        for a in record['aliases']:
            key = normalize_name(a)
            if key in taken:
                raise ValueError(f'Написание «{a}» уже принадлежит поставщику «{taken[key]}»')

    def _mutate(self, name: str, fields: dict, user: Optional[dict], rename_to: Optional[str],
                extra_aliases: Iterable[str] = ()) -> dict:
        """Общий read-modify-write под блокировкой для upsert и add_alias."""
        with self._lock, file_lock(self._lock_path):
            suppliers = self._load(strict=True)
            existing_key = self._find_key(suppliers, name)
            base = suppliers.pop(existing_key) if existing_key else None
            new_name = clean_name(rename_to) if rename_to else (existing_key or name)
            merged_fields = dict(fields)
            aliases = list(merged_fields.get('aliases') if merged_fields.get('aliases') is not None
                           else (base or {}).get('aliases') or [])
            aliases.extend(extra_aliases)
            # Переименование: старое имя остаётся написанием, чтобы категория iiko,
            # из которой поставщик заведён, не отвалилась в «по умолчанию».
            if existing_key and normalize_name(new_name) != normalize_name(existing_key):
                aliases.append(existing_key)
            merged_fields['aliases'] = aliases
            record = make_record(new_name, merged_fields, base)
            self._check_unique(suppliers, record)
            record['updated_at'] = _now()
            record['updated_by'] = _user_login(user)
            suppliers[record['name']] = record
            self._save(suppliers)
        return record

    def upsert(self, name: str, fields: dict, user: Optional[dict], rename_to: Optional[str] = None) -> dict:
        """Создать или обновить поставщика; rename_to переименовывает (алиасы и старое
        имя сохраняются). Переименовать в чужое имя или написание нельзя (ValueError)."""
        return self._mutate(name, fields, user, rename_to)

    def delete(self, name: str) -> bool:
        with self._lock, file_lock(self._lock_path):
            suppliers = self._load(strict=True)
            key = self._find_key(suppliers, name)
            if key is None:
                return False
            suppliers.pop(key)
            self._save(suppliers)
        return True

    def add_alias(self, name: str, alias: str, user: Optional[dict]) -> dict:
        """Добавить написание; слияние со списком делается под блокировкой, а не
        снаружи (два управляющих одновременно не теряют алиасы друг друга)."""
        if self._find_key(self._load(), name) is None:
            raise KeyError(name)
        return self._mutate(name, {}, user, None, extra_aliases=[alias])


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
