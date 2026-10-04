"""Названия товаров из Честного знака для приёмки на РЦ (/receiving/review).

Что это. GTIN, которого нет в iiko, бухгалтеру надо назвать: «Новая позиция
04610093628430» ничего не говорит, «Пиво FH Helles, Без товарного знака, 0,45 л» —
говорит, и по этому названию сервис ищет похожую карточку iiko
(receiving_index.similar_cards). Название берётся из национального каталога ЧЗ.

Почему через бар-ПК. Токен ЧЗ подписывается Рутокеном (CryptoPro), а он вставлен
только в бар-ПК; у сервера своего токена нет. Поэтому сервер по SSH
(remote_exec.run_cmd) запускает на бар-ПК `chz.py product-info <GTIN,...>`, а тот
спрашивает /api/v4/true-api/product/info.

Как ищется (lookup), от дешёвого к дорогому:
1. Кэш — таблица chz_products в receiving.db (core/receiving_store): найденные
   отдаются сразу (source='cache'); «в ЧЗ нет» моложе NEGATIVE_TTL_DAYS — без
   нового запроса на бар-ПК.
2. chz_test/debug/chz_stock.json — ночная выгрузка остатков ЧЗ (тот же файл, что
   читает /stocks): GTIN, которые сеть уже получала, с названием — source='stock',
   сохраняются в кэш.
3. Остальные — product/info на бар-ПК (source='product_info'); найденные и
   «в ЧЗ нет» сохраняются в кэш. Сбой (SSH, токен, устаревший chz.py) — текст в
   errors, GTIN в missing, «в ЧЗ нет» при сбое НЕ запоминается (иначе неделю не
   переспросили бы то, что не дошло).

Транспорт ответа. Стандартный вывод бар-ПК — консоль в cp1251, а run_cmd читает
его как cp866: кириллица приходит кракозябрами, а load_token ещё и печатает свои
строки. Поэтому chz.py отвечает ПОСЛЕДНЕЙ строкой SENTINEL + JSON только из ASCII
(кириллица \\u-экранирована), а сервер берёт последнюю строку с маркером и не
смотрит на остальное. Нет маркера — на бар-ПК старый chz.py: обновлений там нет,
новую версию кладёт руками `python remote_exec.py push chz_test/chz.py C:\\chz_test`
(старый chz.py на незнакомую команду печатает справку и выходит с кодом 0).

Одна команда на бар-ПК за раз — межпроцессный лок LOCK_FILE (portalocker): приёмку
обрабатывает фоновый поток, индекс сверяет другой, у gunicorn два воркера, а
get_token на бар-ПК пишет фиксированные временные файлы — два одновременных
обновления токена портят друг другу подпись.

Тексты ChzError уходят в process_note приёмки, на страницу и в MCP: в них нет
адреса бар-ПК, логина и пароля (подробности — только в логе сервера).

CLI для шага подготовки («проверить на 10 новинках»):
    python -m core.receiving_chz 04610093628430 04600000000000
печатает JSON fetch_product_info (ensure_ascii=False, indent=2).
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import portalocker

from core import msk_time

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Строка-маркер ответа chz.py product-info (там же константа CHZ_JSON_SENTINEL).
SENTINEL = '@@CHZ_JSON@@'
# GTIN на одну команду: строка команды cmd.exe ограничена 8191 символом, каждый GTIN
# с запятой — 15 символов, префикс «cd /d ... && "...python.exe" chz.py product-info» —
# около 80: 400 * 15 + 80 = 6080 < 8191 с запасом. В product/info уходит одним
# пакетом (лимит метода — 1000).
CHUNK = 400
# Секунд на одну команду: SSH-соединение (до 15 с) + запуск Python + возможное
# обновление токена через csptest (~10 с) + product/info (таймаут make_request 60 с) =
# ~90 с, двойной запас. Команда идёт в фоне (обработка приёмки, сверка индекса), не в
# HTTP-запросе, поэтому gunicorn --timeout 180 её не обрывает.
REMOTE_TIMEOUT = 180
# «В ЧЗ нет» не переспрашивать неделю: карточку в национальном каталоге заводит
# производитель, за день она обычно не появляется; через неделю спросим снова.
NEGATIVE_TTL_DAYS = 7
# Выгрузка остатков ЧЗ — тот же путь, что routes/stocks._CHZ_CACHE_FILE (на проде
# каталог chz_test/debug — постоянный том хоста).
CHZ_STOCK_FILE = os.path.join(_BASE_DIR, 'chz_test', 'debug', 'chz_stock.json')
# Межпроцессный лок «одна команда product-info на бар-ПК за раз» — в <repo>/data/,
# рядом с .receiving_index_run.lock. portalocker (flock): умер процесс — лок снимает ОС.
LOCK_FILE = os.path.join(_BASE_DIR, 'data', '.receiving_chz.lock')
# Сколько ждать чужую команду: одна команда идёт до REMOTE_TIMEOUT (180 с), 300 с —
# дождаться её с запасом. Не дождались — ChzError, GTIN спросим при следующей сверке.
LOCK_WAIT_SEC = 300
# Лок ночного обновления кэша ЧЗ (routes/stocks._CHZ_REFRESH_LOCK): пока он есть, на
# бар-ПК идёт search-stock, а она принудительно обновляет токен (chz.py token) через
# общие временные файлы — параллельный product-info мог бы попасть на их гонку.
# Свежий лок — product-info откладываем до следующей сверки.
NIGHTLY_LOCK_FILE = os.path.join(_BASE_DIR, 'chz_test', 'debug', 'refresh.lock')
# Лок старше 30 минут — висячий: тот же порог, что в routes/stocks.start_chz_refresh.
NIGHTLY_LOCK_STALE_SEC = 1800
NIGHTLY_BUSY_ERROR = ('На бар-ПК идёт обновление кэша Честного знака — названия спросим '
                      'при следующей сверке')
# Уровень упаковки в ответе product/info: «trade-unit» — единица товара, «inner-pack» —
# групповая упаковка (у неё mainGtin — GTIN единицы, multiplier — сколько единиц).
PACK_LEVEL = 'inner-pack'
# Как обновить chz.py на бар-ПК (подсказка в тексте ошибки «устарел»).
PUSH_HINT = r'python remote_exec.py push chz_test/chz.py C:\chz_test'
# Текст ошибки из ответа бар-ПК обрезается: это недоверенная строка, на странице
# хватает начала.
MAX_REMOTE_ERROR_LEN = 200

# Понятные тексты для машинных кодов ошибок chz.py product-info.
_REMOTE_ERRORS = {
    'no_token': 'нет токена Честного знака на бар-ПК (вставлен ли Рутокен?)',
    'no_gtins': 'в команду не попал ни один GTIN',
    'bad_response': 'Честный знак ответил не в том формате',
    'HTTP 401': 'Честный знак не принял токен (HTTP 401)',
}

# GTIN уходит в командную строку cmd.exe — только цифры ASCII (str.isdigit пропустил
# бы, например, арабские цифры), длина до 14.
_GTIN_RE = re.compile(r'[0-9]{1,14}')
# Код выхода из текста RuntimeError remote_exec.run_cmd: «Remote command failed (exit N): ...».
_EXIT_CODE_RE = re.compile(r'exit (-?\d+)')
# coreVolume в ЧЗ — объём в мл целым числом (бывает строкой).
_NUMBER_RE = re.compile(r'\d+(?:[.,]\d+)?')

_LOG = '[RECEIVING-CHZ]'

_lock_override: Optional[str] = None
_stock_override: Optional[str] = None
_nightly_override: Optional[str] = None


class ChzUnavailable(Exception):
    """Бар-ПК не настроен (нет REMOTE_PASS) — запрос молча пропускается."""


class ChzError(Exception):
    """Сбой SSH, Честного знака или устаревший chz.py. Текст без адреса и паролей.

    items — карточки, полученные до сбоя (пакеты, которые прошли): их можно
    сохранить, «в ЧЗ нет» при сбое — нельзя.
    """

    def __init__(self, message, items=None):
        super().__init__(message)
        self.items = dict(items or {})


# ----- пути -------------------------------------------------------------------

def lock_path() -> str:
    """Путь к межпроцессному локу команды на бар-ПК (подмена для тестов — set_paths)."""
    return _lock_override or LOCK_FILE


def stock_file_path() -> str:
    """Путь к выгрузке остатков ЧЗ chz_stock.json."""
    return _stock_override or CHZ_STOCK_FILE


def nightly_lock_path() -> str:
    """Путь к локу ночного обновления кэша ЧЗ (chz_test/debug/refresh.lock)."""
    return _nightly_override or NIGHTLY_LOCK_FILE


def set_paths(lock=None, stock_file=None, nightly_lock=None) -> None:
    """Подменить пути (тесты: реальный data/ и chz_test/debug не трогаем). None — по умолчанию."""
    global _lock_override, _stock_override, _nightly_override
    _lock_override = str(lock) if lock else None
    _stock_override = str(stock_file) if stock_file else None
    _nightly_override = str(nightly_lock) if nightly_lock else None


def nightly_refresh_running() -> bool:
    """Идёт ли сейчас ночное обновление кэша ЧЗ (свежий refresh.lock)."""
    try:
        age = time.time() - os.path.getmtime(nightly_lock_path())
    except OSError:
        return False
    return age < NIGHTLY_LOCK_STALE_SEC


# ----- мелкие помощники --------------------------------------------------------

def remote_configured() -> bool:
    """Настроен ли SSH на бар-ПК — REMOTE_PASS в окружении в момент вызова.

    Тот же признак, что у кнопки «Обновить ЧЗ» (routes/stocks.start_chz_refresh) и
    ночного шедулера ЧЗ; в тестах conftest ставит REMOTE_PASS в пустую строку.
    """
    return bool(os.environ.get('REMOTE_PASS'))


def _gtin14(value) -> Optional[str]:
    """GTIN из 1..14 цифр ASCII -> 14 цифр с нулями слева; иначе None."""
    text = str(value if value is not None else '').strip()
    if not _GTIN_RE.fullmatch(text):
        return None
    return text.zfill(14)


def _unique_gtins(values) -> list:
    """Нормализованные GTIN без повторов, порядок первого появления; мусор пропускается."""
    result = []
    seen = set()
    for value in values or ():
        gtin = _gtin14(value)
        if gtin and gtin not in seen:
            seen.add(gtin)
            result.append(gtin)
    return result


def _text(value) -> str:
    """Строка без пробелов по краям и с одиночными пробелами внутри; None -> ''."""
    if value is None or isinstance(value, (dict, list)):
        return ''
    return ' '.join(str(value).split())


def _now_iso() -> str:
    return msk_time.now().isoformat(timespec='seconds')


def _parse_iso(value) -> Optional[datetime]:
    """ISO-метка -> aware datetime (наивная считается московской); мусор -> None."""
    try:
        moment = datetime.fromisoformat(str(value or ''))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=msk_time.MOSCOW_TZ)
    return moment


def _found(row) -> bool:
    """Строка кэша — «найдено в ЧЗ»? (found хранится числом 0/1)."""
    try:
        return int(row.get('found') or 0) == 1
    except (TypeError, ValueError):
        return False


def _fresh_negative(row, now) -> bool:
    """«В ЧЗ нет» моложе NEGATIVE_TTL_DAYS. Метка из будущего — порча: переспросить."""
    fetched = _parse_iso(row.get('fetched_at'))
    if fetched is None:
        return False
    age = now - fetched
    return timedelta(0) <= age < timedelta(days=NEGATIVE_TTL_DAYS)


# ----- ответ chz.py -------------------------------------------------------------

def normalize_item(raw: dict) -> dict:
    """Объект results[] из product/info -> поля для приёмки.

    name — name, а если пусто — fullName (как в chz.get_chz_stock_via_search);
    volume — volumeWeight строкой как есть, иначе coreVolume (число -> «<n> мл»,
    в ЧЗ он в миллилитрах), иначе ''.
    Групповая упаковка (level «inner-pack», спецификация True API product/info):
    main_gtin — GTIN единицы внутри (mainGtin, 14 цифр), pack_units — сколько единиц
    (multiplier); у единицы товара («trade-unit») оба пустые. По ним сервис узнаёт
    мультипак, отсканированный вместо банок (ревью 2026-10-03).
    """
    raw = raw if isinstance(raw, dict) else {}
    level = _text(raw.get('level'))
    pack = level == PACK_LEVEL
    return {
        'name': _text(raw.get('name')) or _text(raw.get('fullName')),
        'brand': _text(raw.get('brand')),
        'full_name': _text(raw.get('fullName')),
        'product_group': _text(raw.get('productGroup')),
        'volume': _volume(raw),
        'package_type': _text(raw.get('packageType')),
        'level': level,
        'main_gtin': (_gtin14(raw.get('mainGtin')) or '') if pack else '',
        'pack_units': _pack_units(raw.get('multiplier')) if pack else '',
    }


def _pack_units(value) -> str:
    """multiplier -> целое > 1 строкой ('6'), иначе ''."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return ''
    return str(number) if number > 1 else ''


def _volume(raw: dict) -> str:
    """Объём для экрана. Число 0 в любом поле — «не заполнено», а не объём."""
    weight = raw.get('volumeWeight')
    if _is_number(weight):
        if weight > 0:
            return str(weight)            # единица в ЧЗ не указана — без подписи
    elif isinstance(weight, str) and weight.strip():
        return weight.strip()
    core_volume = raw.get('coreVolume')
    if _is_number(core_volume):
        return f'{core_volume:g} мл' if core_volume > 0 else ''
    if isinstance(core_volume, str):
        text = core_volume.strip()
        if _NUMBER_RE.fullmatch(text):
            return f'{text} мл' if float(text.replace(',', '.')) > 0 else ''
        return text
    return ''


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def parse_output(stdout) -> dict:
    """Стандартный вывод chz.py product-info -> {'items': {gtin: raw}, 'missing': [gtin]}.

    Берётся ПОСЛЕДНЯЯ строка с SENTINEL (всё выше — печать load_token и кракозябры).
    Нет маркера -> ChzError «chz.py устарел»; {"ok": false} -> ChzError с причиной.
    """
    if isinstance(stdout, bytes):
        stdout = stdout.decode('utf-8', errors='replace')
    payload_text = None
    for line in reversed(str(stdout or '').splitlines()):
        position = line.rfind(SENTINEL)
        if position >= 0:
            payload_text = line[position + len(SENTINEL):].strip()
            break
    if payload_text is None:
        raise ChzError('chz.py на бар-ПК устарел (нет команды product-info) — обновите: ' + PUSH_HINT)
    try:
        payload = json.loads(payload_text)
    except ValueError:
        raise ChzError('Ответ chz.py с бар-ПК не разобран (обрезан или испорчен)') from None
    if not isinstance(payload, dict):
        raise ChzError('Ответ chz.py с бар-ПК не разобран (неожиданный формат)')
    if not payload.get('ok'):
        raise ChzError('Честный знак на бар-ПК: ' + _remote_error_text(payload.get('error')))
    items = payload.get('items')
    missing = payload.get('missing')
    if not isinstance(items, dict) or not isinstance(missing, list):
        raise ChzError('Ответ chz.py с бар-ПК не разобран (нет items/missing)')
    result_items = {}
    for key, raw in items.items():
        gtin = _gtin14(key)
        if gtin and isinstance(raw, dict):
            result_items[gtin] = raw
    result_missing = [g for g in _unique_gtins(missing) if g not in result_items]
    return {'items': result_items, 'missing': result_missing}


def _remote_error_text(error) -> str:
    code = _text(error)[:MAX_REMOTE_ERROR_LEN]
    if not code:
        return 'ошибка без описания'
    return _REMOTE_ERRORS.get(code, code)


def _describe_run_error(error: Exception) -> str:
    """Исключение SSH-команды -> текст для страницы: без адреса, логина и пароля.

    Исключения paramiko/socket содержат адрес бар-ПК, RuntimeError run_cmd — команду
    и stderr; наружу уходит только вид сбоя, подробности — в лог сервера.
    """
    names = {cls.__name__ for cls in type(error).__mro__}
    if isinstance(error, TimeoutError):
        return f'Бар-ПК не ответил за {REMOTE_TIMEOUT} с'
    if 'AuthenticationException' in names:
        return 'Бар-ПК не пустил по SSH (логин или пароль)'
    if isinstance(error, RuntimeError):
        match = _EXIT_CODE_RE.search(str(error))
        code = match.group(1) if match else '?'
        return f'chz.py на бар-ПК завершился с ошибкой (код {code})'
    if isinstance(error, OSError) or 'SSHException' in names:
        return 'Бар-ПК недоступен по SSH'
    return f'Сбой связи с бар-ПК: {type(error).__name__}'


# ----- SSH на бар-ПК -------------------------------------------------------------

def _remote_exec():
    """Модуль remote_exec (корень репозитория); импорт ленивый — тянет paramiko."""
    try:
        import remote_exec
    except ImportError:
        if _BASE_DIR not in sys.path:
            sys.path.insert(0, _BASE_DIR)
        import remote_exec
    return remote_exec


def _command(chunk: list) -> str:
    """Команда cmd.exe на бар-ПК (тот же вид, что в remote_exec.py run ...)."""
    remote = _remote_exec()
    return ('cd /d ' + remote.REMOTE_CHZ_DIR + ' && "' + remote.REMOTE_PYTHON
            + '" chz.py product-info ' + ','.join(chunk))


def _default_run(cmd: str, timeout: float) -> str:
    """Выполнить команду на бар-ПК, вернуть stdout. Без REMOTE_PASS -> ChzUnavailable.

    remote_exec читает REMOTE_PASS при импорте: если модуль импортирован раньше,
    чем пароль попал в окружение, connect всё равно упадёт — считаем «не настроен».
    """
    remote = _remote_exec()
    if not remote.REMOTE_PASS:
        raise ChzUnavailable('SSH на бар-ПК не настроен (нет REMOTE_PASS)')
    return remote.run_cmd(cmd, verbose=False, timeout=timeout)[0]


def fetch_product_info(gtins: list, *, run=None) -> dict:
    """Карточки ЧЗ по GTIN через бар-ПК -> {'items': {gtin: raw}, 'missing': [gtin]}.

    gtins — любые строки; берутся GTIN из 1..14 цифр (дополняются до 14), без повторов.
    Пакетами по CHUNK, по команде `chz.py product-info` на пакет. run(cmd, timeout) ->
    stdout — транспорт (тесты); по умолчанию remote_exec.run_cmd.
    items — объекты results[] как есть; missing — GTIN, про которые ЧЗ ответил «нет».
    Без REMOTE_PASS (и транспорт по умолчанию) -> ChzUnavailable; сбой SSH, ЧЗ или
    устаревший chz.py -> ChzError (в .items — то, что успели получить до сбоя).
    """
    wanted = _unique_gtins(gtins)
    if not wanted:
        return {'items': {}, 'missing': []}
    if run is None:
        if not remote_configured():
            raise ChzUnavailable('SSH на бар-ПК не настроен (нет REMOTE_PASS)')
        run = _default_run
    items = {}
    missing = []
    for start in range(0, len(wanted), CHUNK):
        chunk = wanted[start:start + CHUNK]
        try:
            stdout = run(_command(chunk), REMOTE_TIMEOUT)
        except ChzUnavailable:
            raise
        except ChzError as error:
            raise ChzError(str(error), items=items) from None
        except Exception as error:   # paramiko/socket/run_cmd: текст наружу — без адреса
            print(f'{_LOG} product-info ({len(chunk)} GTIN) не выполнен: '
                  f'{type(error).__name__}: {str(error)[:300]}')
            raise ChzError(_describe_run_error(error), items=items) from None
        try:
            payload = parse_output(stdout)
        except ChzError as error:
            print(f'{_LOG} product-info ({len(chunk)} GTIN): {error}')
            raise ChzError(str(error), items=items) from None
        chunk_set = set(chunk)
        items.update(payload['items'])
        missing.extend(g for g in payload['missing'] if g in chunk_set and g not in items)
    return {'items': items, 'missing': missing}


def _remote_lock():
    """Взять межпроцессный лок команды на бар-ПК (ждать до LOCK_WAIT_SEC)."""
    path = lock_path()
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    lock = portalocker.Lock(path, mode='a', timeout=LOCK_WAIT_SEC, fail_when_locked=False)
    try:
        lock.acquire()
    except portalocker.exceptions.LockException:
        raise ChzError(f'Бар-ПК занят другим запросом к Честному знаку дольше {LOCK_WAIT_SEC} с '
                       '— спросим при следующей сверке') from None
    return lock


# ----- поиск: кэш -> chz_stock.json -> product/info ---------------------------------

def _load_stock(path: str) -> dict:
    """chz_stock.json -> {gtin14: item}. Нет файла или битый — пусто (источник необязательный)."""
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        print(f'{_LOG} {os.path.basename(path)} не читается: {type(error).__name__}')
        return {}
    result = {}
    for item in data if isinstance(data, list) else ():
        gtin = _gtin14(item.get('gtin')) if isinstance(item, dict) else None
        if gtin:
            result[gtin] = item       # ключ как в routes/stocks._load_chz_by_gtin: zfill(14)
    return result


def _stock_info(item: dict) -> dict:
    """Позиция chz_stock.json -> поля приёмки (там есть только name, brand, product_group)."""
    return {
        'name': _text(item.get('name')),
        'brand': _text(item.get('brand')),
        'full_name': '',
        'product_group': _text(item.get('product_group')),
        'volume': '',
        'package_type': '',
    }


def _cache_info(row: dict) -> dict:
    info = {key: _text(row.get(key)) for key in
            ('name', 'brand', 'full_name', 'product_group', 'volume', 'package_type')}
    # Уровень упаковки в колонки кэша не вынесен — берётся из сохранённого ответа ЧЗ.
    packed = normalize_item(row.get('raw') if isinstance(row.get('raw'), dict) else {})
    for key in ('level', 'main_gtin', 'pack_units'):
        info[key] = packed[key]
    return info


def _store_row(gtin: str, found: bool, info: dict, raw: dict, source: str, fetched_at: str) -> dict:
    row = {'gtin': gtin, 'found': 1 if found else 0, 'raw': raw or {}, 'source': source,
           'fetched_at': fetched_at}
    for key in ('name', 'brand', 'full_name', 'product_group', 'volume', 'package_type'):
        row[key] = (info or {}).get(key, '')
    return row


def _save(store, rows: list, errors: list) -> None:
    """Сохранить строки в кэш; сбой кэша не мешает отдать найденное."""
    if not rows:
        return
    try:
        store.save_chz_products(rows)
    except Exception as error:
        print(f'{_LOG} кэш ЧЗ не сохранён: {type(error).__name__}: {error}')
        errors.append(f'Кэш названий ЧЗ не сохранён: {type(error).__name__}')


def lookup(gtins: list, *, remote: bool = True, store=None, run=None, stock_file=None) -> dict:
    """Названия ЧЗ для GTIN -> {'items', 'missing', 'errors', 'remote_used'}.

    items — {gtin: normalize_item-поля + source ('cache'|'stock'|'product_info') +
    fetched_at}; missing — GTIN без названия (в порядке запроса); errors — тексты
    сбоев (без секретов); remote_used — была ли команда на бар-ПК.

    Порядок (модульный докстринг): кэш store -> chz_stock.json -> product/info.
    «В ЧЗ нет» моложе недели на бар-ПК не переспрашивается, но в chz_stock.json
    смотрим (файл локальный и бесплатный; нашлось с названием — тем лучше).
    remote=False — только кэш и файл (без SSH). store — модуль/объект с
    get_chz_products(gtins) -> {gtin: row} и save_chz_products(rows); по умолчанию
    core.receiving_store. run, stock_file — подмены для тестов.
    Мусор вместо GTIN пропускается (нет ни в items, ни в missing).
    """
    if store is None:
        from core import receiving_store as store
    wanted = _unique_gtins(gtins)
    items = {}
    errors = []
    remote_used = False
    if not wanted:
        return {'items': items, 'missing': [], 'errors': errors, 'remote_used': remote_used}
    now = msk_time.now()

    # 1. Кэш
    try:
        cached = store.get_chz_products(wanted) or {}
    except Exception as error:
        print(f'{_LOG} кэш ЧЗ не прочитан: {type(error).__name__}: {error}')
        errors.append(f'Кэш названий ЧЗ не прочитан: {type(error).__name__}')
        cached = {}
    pending = []
    fresh_negative = set()
    for gtin in wanted:
        row = cached.get(gtin)
        if isinstance(row, dict) and _found(row):
            info = _cache_info(row)
            info.update({'source': 'cache', 'fetched_at': str(row.get('fetched_at') or '')})
            items[gtin] = info
            continue
        if isinstance(row, dict) and _fresh_negative(row, now):
            fresh_negative.add(gtin)
        pending.append(gtin)

    # 2. Выгрузка остатков ЧЗ
    if pending:
        stock = _load_stock(str(stock_file) if stock_file else stock_file_path())
        stock_rows = []
        fetched_at = _now_iso()
        for gtin in pending:
            item = stock.get(gtin)
            if not item:
                continue
            info = _stock_info(item)
            if not info['name']:
                # product/info не дал названия и ночной выгрузке — запись без пользы
                continue
            raw = {'gtin': gtin, 'name': info['name'], 'brand': info['brand'],
                   'product_group': info['product_group']}
            stock_rows.append(_store_row(gtin, True, info, raw, 'stock', fetched_at))
            items[gtin] = dict(info, source='stock', fetched_at=fetched_at)
        _save(store, stock_rows, errors)

    # 3. product/info на бар-ПК
    to_fetch = [g for g in pending if g not in items and g not in fresh_negative]
    if to_fetch and remote and remote_configured() and nightly_refresh_running():
        errors.append(NIGHTLY_BUSY_ERROR)
    elif to_fetch and remote and remote_configured():
        result = None
        fetched = {}
        try:
            lock = _remote_lock()
            try:
                remote_used = True
                result = fetch_product_info(to_fetch, run=run)
                fetched = result['items']
            finally:
                lock.release()
        except ChzUnavailable:
            remote_used = False      # до бар-ПК дело не дошло — тихо пропускаем
        except ChzError as error:
            errors.append(str(error))
            fetched = error.items
        fetched_at = _now_iso()
        rows = []
        for gtin in to_fetch:
            raw = fetched.get(gtin)
            if raw is not None:
                info = normalize_item(raw)
                rows.append(_store_row(gtin, True, info, raw, 'product_info', fetched_at))
                items[gtin] = dict(info, source='product_info', fetched_at=fetched_at)
            elif result is not None and gtin in result['missing']:
                rows.append(_store_row(gtin, False, {}, {}, 'product_info', fetched_at))
        _save(store, rows, errors)

    missing = [g for g in wanted if g not in items]
    return {'items': items, 'missing': missing, 'errors': errors, 'remote_used': remote_used}


# ----- CLI --------------------------------------------------------------------

def _main(argv=None) -> int:
    """python -m core.receiving_chz GTIN [GTIN ...] — ответ product/info как JSON."""
    args = sys.argv[1:] if argv is None else list(argv)
    gtins = _unique_gtins(' '.join(args).replace(',', ' ').split())
    if not gtins:
        print('Использование: python -m core.receiving_chz GTIN [GTIN ...] '
              '(через пробел или запятую)', file=sys.stderr)
        return 2
    try:
        result = fetch_product_info(gtins)
    except (ChzUnavailable, ChzError) as error:
        print(f'Ошибка: {error}', file=sys.stderr)
        return 1
    try:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except UnicodeEncodeError:   # консоль Windows в cp1251/cp866
        print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    # Только при запуске из консоли: подтянуть REMOTE_PASS и прочее из .env (как
    # config.py у веб-приложения). В тестах _main зовут напрямую — .env не читается.
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_BASE_DIR, '.env'))
    except ImportError:
        pass
    sys.exit(_main())
