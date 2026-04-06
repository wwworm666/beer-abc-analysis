import os
import json
import time
import subprocess
from datetime import datetime, timedelta
from core.taps_manager import TapsManager
from core.shifts_manager import get_shifts_manager
from core.meeting_notes import MeetingNotesManager
from core.plans_manager import PlansManager
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
