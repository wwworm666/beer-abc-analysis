"""Индекс «GTIN -> карточки iiko» для приёмки на РЦ (/receiving, /receiving/review).

Что это. Свой файл receiving_index.json на постоянном томе: все карточки товаров
iiko (в том числе удалённые и архивные) и карта «штрихкод -> карточки». По нему
приёмка решает, есть ли отсканированный GTIN в iiko (classify), подбирает похожую
карточку по названию из Честного знака (similar_cards) и ищет карточки по запросу
бухгалтера (search_cards).

Почему свой индекс, а не data/cache/nomenclature__products.xml. XML /products — без
удалённых карточек и без признака «удалена», обновляется только руками (урок 16), и
его читают /stocks, /expiration, /suppliers: подложить туда удалённые карточки
нельзя — они попали бы на полки. OLAP-номенклатура без штрихкодов и только с
движением за 30 дней (урок 19). v2 /entities/products/list с includeDeleted=true даёт
сразу штрихкоды (iiko 8.7.1+), признак deleted и родительскую группу.

Как обновляется (refresh_index). Один вход в iiko -> четыре справочника (товары,
группы, пользовательские категории = поставщики, единицы измерения) -> build_index ->
атомарная запись файла; выход из iiko — в finally (каждый вход занимает слот лицензии
iikoAPI, урок про logout). Если у товаров v2 нет поля barcodes (старый сервер), штрихкоды
берутся из XML /products той же сессией. Запускают утренний шедулер, кнопка «Обновить
из iiko» и закрытие приёмки (core/receiving_service): все берут один межпроцессный лок
RUN_LOCK_FILE (portalocker, как .yml_refresh_run.lock у фидов), второй запуск получает
RefreshBusy. Состояние обновления — STATE_FILE: кнопку нажали в одном gunicorn-воркере,
статус спрашивают у другого.

Как читается (load_index). Файл перечитывается, только когда сменились (st_mtime_ns,
размер); кэш — один неизменяемый кортеж, читателям gthread лок не нужен. Словарь
индекса общий для всех запросов процесса: его только читают, наружу отдаются копии
(card_summary).

Правила статусов (раздел 1 спецификации, docs/receiving.md «Как работает»):
актуальная карточка = не удалена и не в архиве; одна актуальная с этим GTIN -> found,
две и больше -> duplicate, только удалённые/архивные -> restore, карточек нет ->
missing (сервис дальше решает similar / new по названию из ЧЗ).
"""
import atexit
import hashlib
import json
import os
import re
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional
from uuid import UUID

import portalocker
import requests

from core import msk_time
from core.iiko_barcodes import _normalize_gtin
from core.json_store import atomic_write_json, file_lock
from core.storage_paths import get_data_path

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Файл индекса: get_data_path -> /kultura на проде (переживает деплой), data/ локально.
INDEX_FILE = 'receiving_index.json'
# Состояние обновления (идёт ли, когда закончилось, ошибка): общее для двух воркеров.
STATE_FILE = 'receiving_index_state.json'
# Межпроцессный лок самого обновления — в <repo>/data/, рядом с .yml_refresh_run.lock.
# portalocker (flock): умер процесс — лок снимает ОС, «вечного» лока после kill нет.
RUN_LOCK_FILE = '.receiving_index_run.lock'
# Формат файла индекса. Файл другой версии не читается (load_index -> None) и
# пересобирается следующим обновлением — без миграций.
INDEX_VERSION = 1

# Группы-архивы: товар в такой группе (на любой глубине) не «актуальный», его надо
# восстановить. В дереве iiko «Старое и неактуальное» -> «Архив» -> «Архив товаров».
# «Старое и неактуальное» — архив целиком, со всеми подгруппами («Черная пятница»,
# «Снеки (старое)», «Октоберфест» и т. д.): решение владельца 2026-10-03. GUID «Архив» и
# «Архив товаров» — те же, что в scripts/export_keg_catalog.py (у каталога кег своё
# правило, его это решение не меняет).
ARCHIVE_GROUP_IDS = frozenset({'23881b17-8ced-47d5-aa03-c5b757e2f184',   # «Старое и неактуальное»
                               '14bc1f9d-e172-1a9d-0196-f2627515aab6',   # «Архив товаров»
                               'be375ee4-671f-4c7b-87ae-ab945b1f8edc'})  # «Архив»
# Те же архивы по имени предка (casefold, без лишних пробелов, точное совпадение):
# на случай новой группы-архива, созданной в iiko под тем же именем.
ARCHIVE_GROUP_NAMES = ('старое и неактуальное', 'архив товаров', 'архив')
# Группа «Kеги» (первая буква — ЛАТИНСКАЯ K; есть ещё кириллическая «Кеги - …»),
# поэтому кеги узнаём по GUID, а не по имени (docs/keg-catalog.md).
KEG_GROUP_ID = '4a5b2a76-8f86-4365-b8e6-5c9aeecd3323'
# Кеговая фасовка в карточке: «кег(30)», «кега 20», «KEG 30L» — как keg_reason
# в scripts/export_keg_catalog.py. Тем же словом кегу узнаём в названии ЧЗ (см.
# is_keg_text): «кега 20 л ПЭТ», «30л. КЕГ (ПЭТ)», «пластиковый кег».
KEG_CONTAINER_RE = re.compile(r'кег|keg', re.IGNORECASE)
# Второй признак кеги в ЧЗ — объём от KEG_MIN_LITERS: половина кег в выгрузке остатков
# ЧЗ названа без слова «кег», только объёмом («Делириум Тременс" 30л. светлое»; 17 со
# словом и 19 только с объёмом из 36). Бутылки и ПЭТ — до 3 л, кеги — 20, 24, 30 л;
# 5-литровые бочонки кегой не считаем (в iiko они не в «Kеги»). Объём — число с
# единицей «л» или «мл» (так приходит и поле volume из product/info: «30000 мл»);
# число без единицы не берём — неизвестно, литры это или миллилитры.
KEG_MIN_LITERS = 10
VOLUME_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*(мл|л)(?![а-яёa-z])', re.IGNORECASE)
# Глубина цепочки групп: в дереве iiko единицы уровней; 50 — защита от кривых данных
# (цикл в parent), как _MAX_GROUP_DEPTH в core/nomenclature_xml.py.
MAX_GROUP_DEPTH = 50

# Кандидаты «похожей карточки» и поиска: товары и заготовки. Порции DISH («… (Р)»,
# «0,5 л») делят имя с товаром и забили бы выдачу; карточки других типов попадают в
# индекс, только если у них есть штрихкод (тогда classify их видит).
SEARCH_TYPES = ('GOODS', 'PREPARED')
# Порог «похожей»: минимум 2 общих слова — как в chz_test/suggest_barcode_fixes.py
# (одно слово — это обычно сорт «IPA» или пивоварня, совпадает у десятков карточек).
SIMILAR_MIN_SCORE = 2
# Сколько кандидатов показать бухгалтеру: больше пяти глазами не сравнивают.
SIMILAR_LIMIT = 5
# Слово короче 3 букв («пш», «л», «0,5» -> «0», «5») — шум: совпадает с чем угодно.
MIN_WORD_LEN = 3
# Запрос поиска из одних цифр длиной от 8 (самый короткий штрихкод — EAN-8) ищется
# как штрихкод; короче — как артикул или часть названия.
SEARCH_MIN_DIGITS = 8
# Стоп-слова «похожей»: общие слова названий пива. Без них «Пиво светлое
# фильтрованное» у карточки и «Пиво светлое пастеризованное» в ЧЗ давали бы счёт 2
# на любой паре светлого пива — ложный кандидат. Пишутся через «е» (ё -> е заранее).
STOP_WORDS = frozenset({
    'пиво', 'пивной', 'напиток', 'светлое', 'темное', 'полутемное',
    'фильтрованное', 'нефильтрованное', 'пастеризованное', 'непастеризованное',
    'осветленное', 'неосветленное', 'бут', 'бутылка', 'банка', 'кег', 'кега',
    'стекло', 'пэт', 'алк', 'безалкогольное',
})

# Таймауты запросов к iiko (соединение, чтение), с. Чтение 120 с: товары с удалёнными —
# ~9 тыс. карточек; ниже gunicorn --timeout 180 (урок 21), хотя обновление и так идёт
# в фоне, а не в запросе.
IIKO_TIMEOUT = (10, 120)
# Выход из iiko — крошечный запрос: не держим фоновое обновление две минуты из-за него.
LOGOUT_TIMEOUT = (5, 15)
# «Идёт обновление» старше 15 минут в STATE_FILE — воркер умер посреди обновления:
# прогон — не больше шести запросов к iiko (вход, четыре справочника, XML), и даже если
# каждый упрётся в таймаут чтения 120 с, это 12 минут — меньше 15.
STALE_RUNNING_SEC = 900
STALE_RUNNING_ERROR = 'Обновление прервалось (перезапуск сервиса) — запустите ещё раз'

_LOG = '[RECEIVING-INDEX]'

_index_override: Optional[str] = None
_state_override: Optional[str] = None
_run_lock_override: Optional[str] = None
# Кэш load_index: один неизменяемый кортеж (путь, (st_mtime_ns, st_size), индекс|None).
# Битый файл тоже кэшируется (None), чтобы не перечитывать его на каждом запросе.
_cache: Optional[tuple] = None
# Кэш слов карточек для similar_cards: (индекс, [(карточка, слова), ...]). Слова зависят
# только от имени, а индекс между обновлениями не меняется: разбор ~9 тыс. имён на
# каждый GTIN приёмки стоил бы ~50 мс. Держим сильную ссылку на сам индекс, чтобы
# сравнение `is` не спутало его с новым словарём на переиспользованном id().
_words_cache: Optional[tuple] = None

_STATE_DEFAULTS = {'running': False, 'trigger': '', 'started_at': '', 'finished_at': '',
                   'error': '', 'counts': None}
_NON_WORD_RE = re.compile(r'[^\w\s]')


class IndexSourceError(Exception):
    """Сбой получения данных из iiko. Текст без токена и адреса — можно показывать."""


class RefreshBusy(Exception):
    """Индекс уже обновляется (другой воркер, шедулер или вторая кнопка)."""


# ----- пути -------------------------------------------------------------------

def index_path() -> str:
    """Путь к файлу индекса (подмена для тестов — set_paths)."""
    return _index_override or get_data_path(INDEX_FILE)


def state_path() -> str:
    """Путь к файлу состояния обновления."""
    return _state_override or get_data_path(STATE_FILE)


def run_lock_path() -> str:
    """Путь к межпроцессному локу обновления (<repo>/data/, как у фидов)."""
    return _run_lock_override or os.path.join(_BASE_DIR, 'data', RUN_LOCK_FILE)


def set_paths(index=None, state=None, run_lock=None) -> None:
    """Подменить пути (тесты). None — путь по умолчанию. Сбрасывает кэш индекса."""
    global _index_override, _state_override, _run_lock_override, _cache, _words_cache
    _index_override = str(index) if index else None
    _state_override = str(state) if state else None
    _run_lock_override = str(run_lock) if run_lock else None
    _cache = None
    _words_cache = None


# ----- мелкие помощники --------------------------------------------------------

def _clean(value) -> str:
    """Строка без пробелов по краям, с одиночными пробелами внутри.

    Имена в iiko бывают с ведущим и двойными пробелами (« Boozy  (Полусладкий)»).
    """
    if value is None:
        return ''
    return ' '.join(str(value).split())


def _fold(value) -> str:
    """Для сравнения: регистр не важен, «ё» = «е»."""
    return _clean(value).casefold().replace('ё', 'е')


def _name_words(name) -> list:
    """Значимые слова названия для «похожей»: уникальные, порядок сохранён.

    Нижний регистр, ё -> е, знаки препинания -> пробел; слово от MIN_WORD_LEN символов,
    не из одних цифр и не стоп-слово (STOP_WORDS).
    """
    words = []
    for word in _NON_WORD_RE.sub(' ', _fold(name)).split():
        if len(word) < MIN_WORD_LEN or word.isdigit() or word in STOP_WORDS:
            continue
        if word not in words:
            words.append(word)
    return words


def is_keg_text(*texts) -> bool:
    """Тексты ЧЗ (название, полное название, вид упаковки, объём) говорят, что товар —
    кега: есть слово «кег»/«keg» или объём от KEG_MIN_LITERS литров."""
    for text in texts:
        value = _clean(text)
        if not value:
            continue
        if KEG_CONTAINER_RE.search(value):
            return True
        for number, unit in VOLUME_RE.findall(value):
            liters = float(number.replace(',', '.'))
            if unit.casefold() == 'мл':
                liters /= 1000
            if liters >= KEG_MIN_LITERS:
                return True
    return False


def _text_words(text) -> list:
    """Слова текста ЧЗ для сравнения с карточкой: как _name_words, но со стоп-словами
    (они всё равно не совпадут — у карточек их нет) и с повторами (каждое слово ЧЗ
    засчитывается один раз)."""
    return [w for w in _NON_WORD_RE.sub(' ', _fold(text)).split()
            if len(w) >= MIN_WORD_LEN and not w.isdigit()]


def _parse_iso(value) -> Optional[datetime]:
    """ISO-метка -> aware datetime МСК; без зоны считаем московской; мусор -> None."""
    try:
        moment = datetime.fromisoformat(str(value or ''))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=msk_time.MOSCOW_TZ)
    return moment


def _now_iso() -> str:
    return msk_time.now().isoformat(timespec='seconds')


def _is_actual(card) -> bool:
    """Актуальная карточка: не удалена и не лежит в группе-архиве."""
    return not card.get('deleted') and not card.get('archived')


def _order_key(card) -> tuple:
    """Порядок выдачи: актуальные раньше, затем по имени; id — для однозначности."""
    return (not _is_actual(card), _fold(card.get('name')), str(card.get('id') or ''))


def _cards(index) -> dict:
    cards = index.get('cards') if isinstance(index, dict) else None
    return cards if isinstance(cards, dict) else {}


def _by_gtin(index) -> dict:
    by_gtin = index.get('by_gtin') if isinstance(index, dict) else None
    return by_gtin if isinstance(by_gtin, dict) else {}


def _names_by_id(rows) -> dict:
    """[{id, name, ...}] -> {id: имя} (категории, единицы измерения)."""
    names = {}
    for row in rows or []:
        if isinstance(row, dict) and row.get('id'):
            names[str(row['id'])] = _clean(row.get('name'))
    return names


def _unique_gtins(values) -> list:
    """Штрихкоды -> GTIN-14 без повторов (порядок сохранён).

    Нормализация core.iiko_barcodes._normalize_gtin: только цифры, не длиннее 14,
    дополнение нулями слева. Контрольная цифра НЕ проверяется: в iiko встречаются
    кривые штрихкоды, и индекс отражает iiko как есть.
    """
    out = []
    for value in values or []:
        gtin = _normalize_gtin(str(value)) if value is not None else None
        if gtin and gtin not in out:
            out.append(gtin)
    return out


def _group_chain(parent_id, groups: dict) -> tuple:
    """Предки карточки: (группы сверху вниз, множество id всех предков).

    Отсутствующий в справочнике родитель и цикл не роняют сборку: обход
    останавливается (карточка — «сирота» с неполным путём). id отсутствующего
    родителя всё равно попадает в множество — архив или кеги узнаются и по нему.
    """
    chain = []
    ids = set()
    current = parent_id
    while current and len(ids) < MAX_GROUP_DEPTH:
        current = str(current)
        if current in ids:
            break   # цикл в parent
        ids.add(current)
        group = groups.get(current)
        if group is None:
            break   # родителя нет в справочнике групп
        chain.append(group)
        current = group.get('parent')
    chain.reverse()
    return chain, ids


# ----- сборка индекса ------------------------------------------------------------

def build_index(products, groups, categories=None, units=None, xml_barcodes=None,
                built_at=None) -> dict:
    """Собрать индекс из ответов iiko (чистая функция, сети нет).

    products   — v2 /entities/products/list (с удалёнными);
    groups     — v2 /entities/products/group/list (с удалёнными: товар может
                 ссылаться на удалённую группу);
    categories — пользовательские категории {id, name} — это поставщик карточки;
    units      — единицы измерения {id, name};
    xml_barcodes — {product_id: [штрихкод, ...]} из XML /products: берётся для
                 карточки, у которой в v2 нет поля barcodes (старый сервер iiko).

    В cards — все GOODS и PREPARED (кандидаты похожей и поиска) и карточки любых
    других типов, если у них есть штрихкод. Повтор id в ответе — берётся первая запись.
    counts: products — карточек в индексе, gtins — различных GTIN, with_barcodes —
    карточек со штрихкодом, deleted / archived — удалённых / лежащих в архиве (карточка
    может быть и тем и другим), duplicates — GTIN, у которых 2+ актуальных карточки.
    """
    group_map = {}
    for group in groups or []:
        if isinstance(group, dict) and group.get('id'):
            group_map[str(group['id'])] = group
    category_names = _names_by_id(categories)
    unit_names = _names_by_id(units)

    cards = {}
    for product in products or []:
        if not isinstance(product, dict) or not product.get('id'):
            continue
        card_id = str(product['id'])
        if card_id in cards:
            continue
        card_type = _clean(product.get('type'))
        raw_codes = product.get('barcodes')
        if isinstance(raw_codes, list):
            values = [code.get('barcode') if isinstance(code, dict) else code for code in raw_codes]
        elif xml_barcodes:
            values = xml_barcodes.get(card_id) or []
        else:
            values = []
        barcodes = _unique_gtins(values)
        if card_type not in SEARCH_TYPES and not barcodes:
            continue

        chain, ancestor_ids = _group_chain(product.get('parent'), group_map)
        archived = (bool(ancestor_ids & ARCHIVE_GROUP_IDS)
                    or any(_clean(g.get('name')).casefold() in ARCHIVE_GROUP_NAMES for g in chain))
        containers = []
        for container in product.get('containers') or []:
            if isinstance(container, dict) and not container.get('deleted'):
                containers.append({'name': _clean(container.get('name')),
                                   'count': container.get('count')})
        keg = (KEG_GROUP_ID in ancestor_ids
               or any(KEG_CONTAINER_RE.search(c['name']) for c in containers))
        cards[card_id] = {
            'id': card_id,
            'name': _clean(product.get('name')),
            'num': _clean(product.get('num')),
            'code': _clean(product.get('code')),
            'type': card_type,
            'deleted': bool(product.get('deleted')),
            'archived': archived,
            'group': ' / '.join(_clean(g.get('name')) for g in chain),
            'group_id': _clean(product.get('parent')),
            'supplier': category_names.get(_clean(product.get('category')), ''),
            'unit': unit_names.get(_clean(product.get('mainUnit')), ''),
            'containers': containers,
            'barcodes': barcodes,
            'keg': keg,
        }

    by_gtin = {}
    for card_id, card in cards.items():
        for gtin in card['barcodes']:
            by_gtin.setdefault(gtin, []).append(card_id)
    by_gtin = {gtin: sorted(by_gtin[gtin], key=lambda cid: _order_key(cards[cid]))
               for gtin in sorted(by_gtin)}

    counts = {
        'products': len(cards),
        'gtins': len(by_gtin),
        'with_barcodes': sum(1 for card in cards.values() if card['barcodes']),
        'deleted': sum(1 for card in cards.values() if card['deleted']),
        'archived': sum(1 for card in cards.values() if card['archived']),
        'duplicates': sum(1 for ids in by_gtin.values()
                          if sum(1 for cid in ids if _is_actual(cards[cid])) >= 2),
    }
    return {
        'version': INDEX_VERSION,
        'built_at': built_at or _now_iso(),
        'source': 'v2' if xml_barcodes is None else 'v2+xml',
        'counts': counts,
        'cards': cards,
        'by_gtin': by_gtin,
    }


# ----- файл индекса ---------------------------------------------------------------

def save_index(index: dict) -> None:
    """Записать индекс атомарно (tmp + fsync + os.replace) под межпроцессным локом.

    Лок обязателен: atomic_write_json пишет во временный файл с фиксированным
    именем <path>.tmp, два одновременных писателя испортили бы его друг другу.
    indent=None — файл на ~9 тыс. карточек, отступы удвоили бы размер.
    """
    path = index_path()
    with file_lock(path + '.lock'):
        atomic_write_json(path, index, indent=None)


def _valid_index(data) -> bool:
    return (isinstance(data, dict) and data.get('version') == INDEX_VERSION
            and isinstance(data.get('cards'), dict) and isinstance(data.get('by_gtin'), dict)
            and _parse_iso(data.get('built_at')) is not None)


def load_index() -> Optional[dict]:
    """Индекс из файла или None (файла нет, битый, другой версии).

    Перечитывает файл, только когда сменились (st_mtime_ns, размер) — свежий индекс
    из другого воркера подхватывается без перезапуска. Результат общий: не менять.
    """
    global _cache
    path = index_path()
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = (stat.st_mtime_ns, stat.st_size)
    cached = _cache
    if cached is not None and cached[0] == path and cached[1] == key:
        return cached[2]
    index = None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as error:
        print(f'{_LOG} индекс не читается ({type(error).__name__}) — ждём пересборки')
    else:
        if _valid_index(data):
            index = data
        else:
            print(f'{_LOG} индекс неожиданного формата — ждём пересборки')
    _cache = (path, key, index)
    return index


def index_info(index: Optional[dict]) -> Optional[dict]:
    """Сводка для страницы и агента: {built_at, age_minutes, counts, source} или None.

    age_minutes — целые минуты от built_at до сейчас (МСК), не меньше 0; None только
    для словаря без читаемой built_at (load_index такой индекс не отдаёт).
    """
    if not isinstance(index, dict) or not index:
        return None
    built_at = str(index.get('built_at') or '')
    built = _parse_iso(built_at)
    age = None
    if built is not None:
        age = max(0, int((msk_time.now() - built).total_seconds() // 60))
    counts = index.get('counts')
    return {'built_at': built_at, 'age_minutes': age,
            'counts': dict(counts) if isinstance(counts, dict) else {},
            'source': str(index.get('source') or '')}


# ----- статусы, похожие, поиск -------------------------------------------------------

def card_summary(card: dict) -> dict:
    """Сводка карточки для строки разбора, кандидатов и поиска (копия, не ссылка)."""
    return {
        'id': str(card.get('id') or ''),
        'name': str(card.get('name') or ''),
        'num': str(card.get('num') or ''),
        'group': str(card.get('group') or ''),
        'supplier': str(card.get('supplier') or ''),
        'unit': str(card.get('unit') or ''),
        'deleted': bool(card.get('deleted')),
        'archived': bool(card.get('archived')),
        'keg': bool(card.get('keg')),
    }


def classify(gtin: str, index: dict) -> dict:
    """Статус GTIN по индексу: {'status', 'cards': [card_summary, ...]}.

    status: found — ровно одна актуальная карточка; duplicate — две и больше
    актуальных (дубль штрихкода); restore — карточки есть, но все удалены или в
    архиве; missing — карточек с этим штрихкодом нет. cards — все карточки GTIN,
    актуальные раньше. Не GTIN (буквы, длиннее 14 цифр) -> missing.
    """
    gtin_key = _normalize_gtin(str(gtin)) if gtin else None
    found = []
    if gtin_key:
        cards = _cards(index)
        found = sorted((cards[cid] for cid in _by_gtin(index).get(gtin_key, []) if cid in cards),
                       key=_order_key)
    actual = sum(1 for card in found if _is_actual(card))
    if actual == 1:
        status = 'found'
    elif actual >= 2:
        status = 'duplicate'
    elif found:
        status = 'restore'
    else:
        status = 'missing'
    return {'status': status, 'cards': [card_summary(card) for card in found]}


def _candidate_words(index) -> list:
    """Кандидаты похожей: [(карточка SEARCH_TYPES, её значимые слова)], кэш на индекс.

    Карточки, у которых значимых слов меньше SIMILAR_MIN_SCORE, порог не пройдут
    никогда — их не держим.
    """
    global _words_cache
    cached = _words_cache
    if cached is not None and cached[0] is index:
        return cached[1]
    pairs = []
    for card in _cards(index).values():
        if not isinstance(card, dict) or card.get('type') not in SEARCH_TYPES:
            continue
        words = _name_words(card.get('name'))
        if len(words) >= SIMILAR_MIN_SCORE:
            pairs.append((card, words))
    _words_cache = (index, pairs)
    return pairs


def similar_cards(name: str, index: dict, brand: str = '', limit: int = SIMILAR_LIMIT,
                  keg: bool = False) -> list:
    """Карточки iiko, похожие на товар ЧЗ по названию (порт suggest_barcode_fixes.py).

    Направление как в оригинале: значимые слова КАРТОЧКИ (_name_words) ищутся среди
    слов текста ЧЗ «name + ' ' + brand» (регистр не важен, ё = е). Слово карточки
    совпало, если одно из двух слов начинается с другого («лагер» — «лагерное»,
    «урхельское» — «урхель»), и каждое слово ЧЗ засчитывается одному слову карточки.
    Так одно слово ЧЗ не набирает порог в одиночку: в оригинале поиск подстрокой
    давал «pale» и «ale» из одного «Pale» — счёт 2 у любой карточки «… Pale Ale»
    (ревью 2026-10-03). Счёт — сколько разных слов карточки совпало; кандидат —
    счёт >= SIMILAR_MIN_SCORE. Кандидаты — карточки SEARCH_TYPES любые: актуальные,
    удалённые, архивные (пометки видны в сводке). Порядок: счёт по убыванию, при
    keg=True (товар ЧЗ — кега, см. is_keg_text) кеги раньше бутылок того же счёта,
    затем актуальные раньше, имя. «Кег» — стоп-слово, в счёт не идёт: без keg бутылка
    и кега одного сорта набирают одинаково, и кега (имя «КЕГ …») оказывалась ниже.
    Возврат: [card_summary + {'score': n}] не больше limit.
    """
    tokens = _text_words(_clean(name) + ' ' + _clean(brand))
    if not tokens:
        return []
    by_head = {}
    for i, token in enumerate(tokens):
        by_head.setdefault(token[:MIN_WORD_LEN], []).append(i)
    scored = []
    for card, words in _candidate_words(index):
        used = set()
        score = 0
        for word in words:
            for i in by_head.get(word[:MIN_WORD_LEN], ()):
                if i not in used and (tokens[i].startswith(word) or word.startswith(tokens[i])):
                    used.add(i)
                    score += 1
                    break
        if score >= SIMILAR_MIN_SCORE:
            scored.append((score, card))
    scored.sort(key=lambda item: (-item[0], bool(keg) and not item[1].get('keg')) + _order_key(item[1]))
    return [dict(card_summary(card), score=score) for score, card in scored[:max(0, int(limit))]]


def search_cards(q: str, index: dict, limit: int = 20) -> list:
    """Поиск карточек для бухгалтера: [card_summary + {'barcodes': [...]}].

    q из цифр длиной от SEARCH_MIN_DIGITS — штрихкод: карточки этого GTIN (любого
    типа) и карточки SEARCH_TYPES с артикулом, равным q. Иначе — карточки
    SEARCH_TYPES, в имени которых есть все слова запроса (подстроками; регистр не
    важен, ё = е), или с артикулом, равным запросу. Актуальные раньше, затем имя.
    """
    query = _clean(q)
    if not query:
        return []
    cards = _cards(index)
    picked = {}
    if query.isdigit() and len(query) >= SEARCH_MIN_DIGITS:
        gtin = _normalize_gtin(query)
        for card_id in (_by_gtin(index).get(gtin, []) if gtin else []):
            if card_id in cards:
                picked[card_id] = cards[card_id]
        for card_id, card in cards.items():
            if card.get('type') in SEARCH_TYPES and _clean(card.get('num')) == query:
                picked.setdefault(card_id, card)
    else:
        folded = _fold(query)
        words = folded.split()
        for card_id, card in cards.items():
            if card.get('type') not in SEARCH_TYPES:
                continue
            name = _fold(card.get('name'))
            if all(word in name for word in words) or _fold(card.get('num')) == folded:
                picked[card_id] = card
    ordered = sorted(picked.values(), key=_order_key)
    return [dict(card_summary(card), barcodes=list(card.get('barcodes') or []))
            for card in ordered[:max(0, int(limit))]]


# ----- iiko ----------------------------------------------------------------------------

def _parse_xml_barcodes(content) -> dict:
    """XML /products -> {product_id: [штрихкод как в iiko, ...]} (нормализует build_index)."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise IndexSourceError('iiko вернул нечитаемый XML номенклатуры') from None
    result = {}
    for product in root.findall('productDto'):
        product_id = (product.findtext('id') or '').strip()
        if not product_id:
            continue
        codes = [(el.text or '').strip() for el in product.iter('barcode')]
        codes = [code for code in codes if code]
        if codes:
            result.setdefault(product_id, []).extend(codes)
    return result


# Выход из iiko незавершённого обновления при остановке процесса. Фоновое обновление —
# поток-демон: gunicorn перезапускает воркер (max-requests) посреди загрузки, поток
# замирает и finally с logout не выполняется — слот лицензии iikoAPI висел бы до таймаута
# сессии. atexit срабатывает при штатном выходе воркера; SIGKILL не спасает ничто.
_active_logout = [None]


def _logout_on_exit() -> None:
    action = _active_logout[0]
    if action is None:
        return
    try:
        action()
        print(f'{_LOG} выход из iiko при остановке процесса')
    except Exception as error:  # noqa: BLE001 — процесс и так завершается
        print(f'{_LOG} выход из iiko при остановке не прошёл ({type(error).__name__})')


atexit.register(_logout_on_exit)


def fetch_iiko_sources() -> dict:
    """Справочники iiko для индекса — одним входом; выход в finally (слот лицензии).

    GET (везде includeDeleted=true): товары, группы товаров, пользовательские
    категории, единицы измерения. Если ни у одного товара v2 нет поля barcodes —
    ещё XML /products той же сессией. Ответ v2 вида {'result', 'response'}
    разворачивается. Любой сбой -> IndexSourceError без URL: в адресе запроса стоит
    ?key=<токен>, а в тексте исключения requests — полный адрес.

    Возврат: {'products', 'groups', 'categories', 'units', 'xml_barcodes': {..} | None}.
    """
    # Ленивый импорт: config читает .env, тестам сборки индекса он не нужен.
    from config import IIKO_BASE_URL, IIKO_LOGIN, IIKO_PASSWORD
    if not IIKO_LOGIN or not IIKO_PASSWORD:
        raise IndexSourceError('Не настроено подключение к iiko')
    token = None
    with requests.Session() as session:
        def get(path, params=None, *, label, accept='application/json', timeout=IIKO_TIMEOUT):
            query = dict(params or {})
            if token:
                query['key'] = token
            try:
                response = session.get(IIKO_BASE_URL + path, params=query,
                                       headers={'Accept': accept}, timeout=timeout,
                                       allow_redirects=False)
            except requests.RequestException as error:
                # Текст исключения requests содержит URL с токеном: наружу — только тип.
                raise IndexSourceError(f'Нет связи с iiko ({label}): {type(error).__name__}') from None
            if response.status_code != 200:
                if path == '/auth':
                    raise IndexSourceError(
                        f'iiko не пустил (HTTP {response.status_code}): проверьте логин и '
                        f'пароль или свободные слоты лицензии API')
                raise IndexSourceError(f'iiko ответил HTTP {response.status_code} ({label})')
            return response

        def get_list(path, params, label):
            response = get(path, params, label=label)
            try:
                payload = response.json()
            except ValueError:
                raise IndexSourceError(f'iiko вернул не JSON ({label})') from None
            if isinstance(payload, dict) and 'result' in payload:
                if payload.get('result') != 'SUCCESS':
                    raise IndexSourceError(f'iiko отклонил запрос ({label})')
                payload = payload.get('response')
            if not isinstance(payload, list):
                raise IndexSourceError(f'iiko вернул неожиданный ответ ({label})')
            return payload

        try:
            raw = get('/auth', {'login': IIKO_LOGIN,
                                'pass': hashlib.sha1(IIKO_PASSWORD.encode()).hexdigest()},
                      label='вход', accept='*/*').text.strip()
            if raw.startswith('<'):
                try:
                    raw = ''.join(ET.fromstring(raw).itertext()).strip()
                except ET.ParseError:
                    raw = ''
            try:
                token = str(UUID(raw))
            except ValueError:
                raise IndexSourceError('iiko не выдал ключ входа') from None
            _active_logout[0] = lambda: get('/logout', label='выход', accept='*/*',
                                            timeout=LOGOUT_TIMEOUT)

            products = get_list('/v2/entities/products/list', {'includeDeleted': 'true'}, 'товары')
            if not products:
                raise IndexSourceError('iiko вернул пустой список товаров')
            groups = get_list('/v2/entities/products/group/list', {'includeDeleted': 'true'},
                              'группы товаров')
            categories = get_list('/v2/entities/products/category/list', {'includeDeleted': 'true'},
                                  'категории товаров')
            units = get_list('/v2/entities/list', {'rootType': 'MeasureUnit', 'includeDeleted': 'true'},
                             'единицы измерения')
            xml_barcodes = None
            if not any(isinstance(p, dict) and 'barcodes' in p for p in products):
                response = get('/products', {'includeDeleted': 'true'},
                               label='штрихкоды XML', accept='application/xml')
                xml_barcodes = _parse_xml_barcodes(response.content)
            print(f'{_LOG} iiko: {len(products)} товаров, {len(groups)} групп, '
                  f'{len(categories)} категорий, {len(units)} единиц'
                  + ('' if xml_barcodes is None else f', штрихкоды из XML: {len(xml_barcodes)} карточек'))
            return {'products': products, 'groups': groups, 'categories': categories,
                    'units': units, 'xml_barcodes': xml_barcodes}
        finally:
            _active_logout[0] = None
            if token:
                try:
                    get('/logout', label='выход', accept='*/*', timeout=LOGOUT_TIMEOUT)
                except Exception as error:   # выход не должен заслонять основной результат
                    print(f'{_LOG} выход из iiko не прошёл ({type(error).__name__}): '
                          f'слот лицензии освободится по таймауту сессии')


# ----- обновление и его состояние ---------------------------------------------------------

def read_state() -> dict:
    """Состояние обновления: {running, trigger, started_at, finished_at, error, counts}.

    Файла нет или он битый — «не запускалось» (пустые поля). running со started_at
    старше STALE_RUNNING_SEC (или без читаемой started_at) считается False: воркер
    умер посреди обновления; тогда в error — STALE_RUNNING_ERROR, если ошибки не было.
    """
    state = dict(_STATE_DEFAULTS)
    try:
        with open(state_path(), encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return state
    except (OSError, ValueError) as error:
        print(f'{_LOG} состояние не читается ({type(error).__name__})')
        return state
    if not isinstance(data, dict):
        return state
    state['running'] = bool(data.get('running'))
    for key in ('trigger', 'started_at', 'finished_at', 'error'):
        state[key] = str(data.get(key) or '')
    counts = data.get('counts')
    state['counts'] = dict(counts) if isinstance(counts, dict) else None
    if state['running']:
        started = _parse_iso(state['started_at'])
        if (started is None or (msk_time.now() - started).total_seconds() > STALE_RUNNING_SEC
                or not _run_lock_held()):
            state['running'] = False
            state['error'] = state['error'] or STALE_RUNNING_ERROR
    return state


def _run_lock_held() -> bool:
    """Держит ли кто-то лок обновления прямо сейчас (проба без ожидания).

    «running» в файле, а лок свободен — обновлявший воркер умер (перезапуск по
    max-requests, kill): состояние не ждёт STALE_RUNNING_SEC, кнопка сразу доступна.
    flock — на открытое описание файла: проба из того же процесса, где идёт
    обновление, тоже видит лок занятым. Не проверить (нет каталога, права) — считаем
    занятым, решает таймаут STALE_RUNNING_SEC.
    """
    try:
        probe = portalocker.Lock(run_lock_path(), mode='a', timeout=0, fail_when_locked=True)
        probe.acquire()
    except portalocker.exceptions.LockException:
        return True
    except OSError:
        return True
    probe.release()
    return False


def _write_state(state: dict) -> None:
    path = state_path()
    with file_lock(path + '.lock'):
        atomic_write_json(path, state)


def acquire_run_lock(wait: float = 0):
    """Взять межпроцессный лок обновления; вернуть его (вызвавший отдаёт в refresh_index).

    wait — сколько секунд ждать чужое обновление; 0 — не ждать. Занят -> RefreshBusy.
    """
    path = run_lock_path()
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    lock = portalocker.Lock(path, timeout=wait, fail_when_locked=not wait)
    try:
        lock.acquire()
    except portalocker.exceptions.LockException:
        raise RefreshBusy('Индекс iiko уже обновляется') from None
    return lock


def refresh_index(trigger: str, *, lock=None, wait: float = 0, fetch=None, after_save=None) -> dict:
    """Пересобрать индекс из iiko синхронно; вернуть index_info нового индекса.

    trigger — кто запустил ('schedule', 'button', 'close', ...), пишется в состояние.
    lock — уже взятый acquire_run_lock (кнопка берёт его в запросе, чтобы сразу
    ответить 409, а обновляет в фоне); None — взять здесь (wait — сколько ждать).
    fetch — источник данных (тесты); по умолчанию fetch_iiko_sources.
    after_save(index) — что сделать с новым индексом ДО отметки «готово» и ДО снятия
    лока (сервис пересверяет открытые строки разбора): страница, увидев «обновление
    закончилось», сразу показывает уже пересверенный список. Сбой after_save индекс
    не отменяет: состояние done, в error — «Индекс обновлён, но …».

    Состояние: running -> done (finished_at, counts) или error (текст IndexSourceError
    как есть, иначе «Сбой обновления индекса: <тип>»), исключение пробрасывается, файл
    индекса при сбое не трогается. Лок освобождается всегда.
    """
    if lock is None:
        lock = acquire_run_lock(wait)
    try:
        started_at = _now_iso()
        started = time.monotonic()
        _write_state({'running': True, 'trigger': str(trigger or ''), 'started_at': started_at,
                      'finished_at': '', 'error': '', 'counts': None})
        try:
            sources = (fetch or fetch_iiko_sources)()
            # Время индекса — момент ДО чтения iiko, а не конец сборки: «Сделано», нажатое
            # бухгалтером во время загрузки, не должно выглядеть «старше индекса» (индекс
            # его карточку не видел; строка не переоткрывается по такому индексу).
            index = build_index(sources.get('products'), sources.get('groups'),
                                sources.get('categories'), sources.get('units'),
                                sources.get('xml_barcodes'), built_at=started_at)
            if not index['cards']:
                raise IndexSourceError('В ответе iiko нет ни одной карточки товара — индекс не перезаписан')
            save_index(index)
        except Exception as error:
            if isinstance(error, IndexSourceError):
                message = str(error)
                print(f'{_LOG} обновление ({trigger}) не удалось: {message}')
            else:
                message = f'Сбой обновления индекса: {type(error).__name__}'
                print(f'{_LOG} обновление ({trigger}) упало: {type(error).__name__}')
                if not isinstance(error, requests.RequestException):
                    # Трассировка requests содержит URL с токеном — её не печатаем.
                    traceback.print_exc()
            try:
                _write_state({'running': False, 'trigger': str(trigger or ''),
                              'started_at': started_at, 'finished_at': _now_iso(),
                              'error': message, 'counts': None})
            except Exception as state_error:   # не заслоняем исходную ошибку обновления
                print(f'{_LOG} состояние ошибки не записано: {type(state_error).__name__}')
            raise
        post_error = ''
        if after_save is not None:
            try:
                after_save(index)
            except Exception as error:   # индекс уже записан — не отменяем его
                post_error = ('Индекс обновлён, но пересверка строк разбора не удалась: '
                              + type(error).__name__)
                print(f'{_LOG} {post_error}')
                traceback.print_exc()
        _write_state({'running': False, 'trigger': str(trigger or ''), 'started_at': started_at,
                      'finished_at': _now_iso(), 'error': post_error, 'counts': dict(index['counts'])})
        counts = index['counts']
        print(f'{_LOG} обновлён ({trigger}) за {time.monotonic() - started:.0f} с: '
              f'{counts["products"]} карточек, {counts["gtins"]} GTIN, '
              f'дублей {counts["duplicates"]}, источник {index["source"]}')
        return index_info(index)
    finally:
        lock.release()
