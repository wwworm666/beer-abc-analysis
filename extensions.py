import os
import json
import time
import threading
import subprocess
from datetime import datetime, timedelta
from core.taps_manager import TapsManager
from core.shifts_manager import get_shifts_manager
from core.meeting_notes import MeetingNotesManager
from core.plans_manager import PlansManager
from core.day_weight_overrides import DayWeightOverridesManager
from core.venues_manager import VenuesManager
from core.comparison_calculator import ComparisonCalculator
from core.trends_analyzer import TrendsAnalyzer
from core.export_manager import ExportManager
from core.olap_reports import OlapReports


def get_git_commit_hash():
    """Получить короткий хеш текущего git commit для версионирования"""
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).decode('ascii').strip()
    except Exception:
        # Fallback на timestamp для случаев когда git недоступен
        from datetime import datetime
        return datetime.now().strftime('%Y%m%d%H%M')


# Определяется при старте приложения
APP_VERSION = get_git_commit_hash()

# Менеджер кранов
TAPS_DATA_PATH = os.environ.get('TAPS_DATA_PATH', 'data/taps_data.json')
if os.path.exists('/kultura'):
    TAPS_DATA_PATH = '/kultura/taps_data.json'
    print(f"[INFO] Используется Render Disk: {TAPS_DATA_PATH}")
else:
    print(f"[INFO] Используется локальный путь: {TAPS_DATA_PATH}")

taps_manager = TapsManager(data_file=TAPS_DATA_PATH)
plans_manager = PlansManager()
day_weight_overrides_manager = DayWeightOverridesManager()
notes_manager = MeetingNotesManager()
venues_manager = VenuesManager()
shifts_mgr = get_shifts_manager()

# Калькуляторы для дашборда
comparison_calculator = ComparisonCalculator()
trends_analyzer = TrendsAnalyzer()
export_manager = ExportManager()

# Кэши
EMPLOYEES_CACHE = {'data': None, 'timestamp': 0}
EMPLOYEES_CACHE_TTL = 300  # 5 минут

DASHBOARD_OLAP_CACHE = {}
DASHBOARD_OLAP_CACHE_TTL = 600  # 10 минут
DASHBOARD_OLAP_CACHE_MAX_KEYS = 64  # мягкий bound против неограниченного роста кэша

# Per-key блокировки для single-flight: не дать параллельным одинаковым запросам
# внутри одного воркера дёргать дорогой OLAP по разу каждый (защита от стампеда).
_OLAP_INFLIGHT_LOCKS = {}
_OLAP_INFLIGHT_LOCKS_GUARD = threading.Lock()


def _get_olap_inflight_lock(cache_key):
    """Вернуть (создав при необходимости) per-key lock для single-flight."""
    with _OLAP_INFLIGHT_LOCKS_GUARD:
        lock = _OLAP_INFLIGHT_LOCKS.get(cache_key)
        if lock is None:
            lock = threading.Lock()
            _OLAP_INFLIGHT_LOCKS[cache_key] = lock
        # Лёгкая уборка: не копить локи для ключей, которых давно нет в кэше.
        if len(_OLAP_INFLIGHT_LOCKS) > 2 * DASHBOARD_OLAP_CACHE_MAX_KEYS:
            for k in [k for k in _OLAP_INFLIGHT_LOCKS
                      if k != cache_key and k not in DASHBOARD_OLAP_CACHE]:
                _OLAP_INFLIGHT_LOCKS.pop(k, None)
        return lock


def _evict_stale_olap_cache(now):
    """Удалить протухшие ключи и ограничить размер кэша (anti-leak)."""
    stale = [k for k, v in DASHBOARD_OLAP_CACHE.items()
             if (now - v.get('timestamp', 0)) >= DASHBOARD_OLAP_CACHE_TTL]
    for k in stale:
        DASHBOARD_OLAP_CACHE.pop(k, None)
    if len(DASHBOARD_OLAP_CACHE) > DASHBOARD_OLAP_CACHE_MAX_KEYS:
        # Выкинуть самые старые сверх лимита
        ordered = sorted(DASHBOARD_OLAP_CACHE.items(), key=lambda kv: kv[1].get('timestamp', 0))
        for k, _ in ordered[:len(DASHBOARD_OLAP_CACHE) - DASHBOARD_OLAP_CACHE_MAX_KEYS]:
            DASHBOARD_OLAP_CACHE.pop(k, None)


def cached_olap(cache_key, fetch_fn, ttl=DASHBOARD_OLAP_CACHE_TTL):
    """
    Получить OLAP-данные с кэшем и single-flight (защита от стампеда внутри воркера).

    1. Проверяем кэш + TTL — при попадании возвращаем сразу.
    2. При промахе берём per-key lock, чтобы одновременные одинаковые запросы
       в этом воркере не дёргали iiko по разу каждый.
    3. Под локом повторно проверяем кэш (double-checked locking) — мог наполнить
       другой поток, пока мы ждали лок.
    4. Иначе вызываем fetch_fn(), кэшируем НЕпустой результат и возвращаем.

    fetch_fn() должна вернуть данные; falsy-результат (ошибка iiko) НЕ кэшируется.
    Шаринг между воркерами не делается (per-process кэш) — двойной запрос с фронта
    устранён на клиенте; этого хватает, см. docs/lessons.md.
    """
    now = time.time()
    entry = DASHBOARD_OLAP_CACHE.get(cache_key)
    if entry and (now - entry['timestamp']) < ttl:
        return entry['data']

    lock = _get_olap_inflight_lock(cache_key)
    with lock:
        # double-check: пока ждали лок, кэш мог наполнить другой поток
        now = time.time()
        entry = DASHBOARD_OLAP_CACHE.get(cache_key)
        if entry and (now - entry['timestamp']) < ttl:
            return entry['data']

        data = fetch_fn()
        if data:
            DASHBOARD_OLAP_CACHE[cache_key] = {'data': data, 'timestamp': time.time()}
            _evict_stale_olap_cache(time.time())
        return data


nomenclature_cache = {
    'data': None,
    'expires_at': None
}

# Список баров
BARS = [
    "Большой пр. В.О",
    "Лиговский",
    "Кременчугская",
    "Варшавская"
]

# Telegram бот
TELEGRAM_BOT_ENABLED = False
try:
    import telegram_webhook
    beer_mapping_file = os.path.join(os.path.dirname(__file__), 'data', 'beer_info_mapping.json')
    beer_mapping_for_bot = {}
    if os.path.exists(beer_mapping_file):
        with open(beer_mapping_file, 'r', encoding='utf-8') as f:
            beer_mapping_for_bot = json.load(f)
        print(f"[TELEGRAM] Загружен маппинг пива: {len(beer_mapping_for_bot)} записей")
    telegram_webhook.set_data_sources(taps_manager, beer_mapping_for_bot)
    TELEGRAM_BOT_ENABLED = True
    print("[TELEGRAM] Бот инициализирован (webhook режим)")
except Exception as e:
    print(f"[TELEGRAM] Ошибка инициализации бота: {e}")


NOMENCLATURE_DISK_CACHE = os.path.join(os.path.dirname(__file__), 'data', 'nomenclature_cache.json')
NOMENCLATURE_DISK_TTL = 86400  # 24 hours


def _load_nomenclature_from_disk():
    """Load nomenclature from disk cache if fresh enough"""
    try:
        if not os.path.exists(NOMENCLATURE_DISK_CACHE):
            return None
        age = time.time() - os.path.getmtime(NOMENCLATURE_DISK_CACHE)
        if age > NOMENCLATURE_DISK_TTL:
            print(f"[CACHE] Disk cache expired ({age/3600:.1f}h old)")
            return None
        with open(NOMENCLATURE_DISK_CACHE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"[CACHE] Loaded nomenclature from disk ({len(data)} items, {age/60:.0f}m old)")
        return data
    except Exception as e:
        print(f"[CACHE] Failed to load disk cache: {e}")
        return None


def _save_nomenclature_to_disk(nomenclature):
    """Save nomenclature to disk cache"""
    try:
        os.makedirs(os.path.dirname(NOMENCLATURE_DISK_CACHE), exist_ok=True)
        with open(NOMENCLATURE_DISK_CACHE, 'w', encoding='utf-8') as f:
            json.dump(nomenclature, f, ensure_ascii=False)
        print(f"[CACHE] Saved nomenclature to disk ({len(nomenclature)} items)")
    except Exception as e:
        print(f"[CACHE] Failed to save disk cache: {e}")


def get_cached_nomenclature(olap):
    """
    Получить номенклатуру: memory cache -> disk cache -> iiko API

    Args:
        olap: Экземпляр OlapReports

    Returns:
        Словарь с номенклатурой или None
    """
    now = datetime.now()

    # 1. Memory cache (15 min TTL)
    if nomenclature_cache['data'] is not None and nomenclature_cache['expires_at'] is not None:
        if now < nomenclature_cache['expires_at']:
            print(f"[CACHE] Memory cache hit ({(nomenclature_cache['expires_at'] - now).seconds // 60} min left)")
            return nomenclature_cache['data']

    # 2. Disk cache (24h TTL)
    disk_data = _load_nomenclature_from_disk()
    if disk_data:
        nomenclature_cache['data'] = disk_data
        nomenclature_cache['expires_at'] = now + timedelta(minutes=15)
        return disk_data

    # 3. iiko API (slow, may timeout)
    print("[CACHE] No cache available, requesting from iiko API...")
    nomenclature = olap.get_nomenclature()

    if nomenclature:
        nomenclature_cache['data'] = nomenclature
        nomenclature_cache['expires_at'] = now + timedelta(minutes=15)
        _save_nomenclature_to_disk(nomenclature)

    return nomenclature
