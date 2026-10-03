"""Шедулер приёмки на РЦ: утреннее обновление индекса iiko и подбор зависших обработок.

Что это. Три потока-демона на каждый gunicorn-воркер (start_scheduler, зовёт
app.py:_start_background_jobs):
1. Утро — в INDEX_HOUR:INDEX_MINUTE по МОСКВЕ (по умолчанию 07:30, до прихода
   бухгалтерии и первой машины на РЦ) пересобрать индекс «GTIN -> карточки iiko» и
   пересверить открытые строки разбора (receiving_service.run_index_refresh): карточки,
   заведённые вчера, закрывают свои строки сами.
2. Старт — через STARTUP_DELAY_SEC после запуска: индекса нет или он старше
   STARTUP_MAX_AGE_HOURS — пересобрать сразу (первый деплой, пропущенное утро).
3. Подбор — раз в RETRY_INTERVAL_SEC: обработки закрытых приёмок, которые не
   закончились (воркер перезапустился посреди обработки) или упали больше
   PROCESS_RETRY_SEC назад, запускаются снова (receiving_service.retry_stuck_processing).

Почему время по Москве явно. В прод-образе нет tzdata, наивное datetime.now() там —
UTC (у старых шедулеров 05:40 в .env значит 08:40 МСК). Здесь, как в
core/yandex_reviews_scheduler.py, время считается через core/msk_time: 7 в .env —
это 07:00 МСК.

Защита от двойного запуска (gunicorn --workers 2, у каждого воркера свои потоки):
- утро — lock-файл на дату МСК (O_CREAT|O_EXCL в data/, урок 20): прогон делает
  воркер, первым создавший файл; плюс межпроцессный лок самой пересборки
  (receiving_index.RUN_LOCK_FILE), общий с кнопкой и закрытием приёмки;
- старт — только лок пересборки без ожидания: второй воркер получит RefreshBusy и
  пропустит, а пришедший позже увидит свежий индекс;
- подбор — атомарный claim_processing в receiving.db: приёмку возьмёт один воркер.

Шедулер зовёт функции receiving_service напрямую, не POST в свой /api: у потока нет
сессии, auth-гейт ответил бы 401 (docs/lessons.md, «Планировщик, дёргающий свой же
HTTP-эндпоинт»).

Переменные окружения:
    RECEIVING_INDEX_HOUR / _MINUTE   время утреннего обновления, МСК (7 / 30)
    RECEIVING_INDEX_ENABLED          0 — индекс по расписанию и при старте не
                                     обновлять (по умолчанию 1); подбор обработок
                                     работает всё равно — без него закрытая приёмка,
                                     прерванная перезапуском, не обработается никогда.
Без кредов iiko (IIKO_LOGIN / IIKO_PASSWORD) потоки индекса не запускаются.
Документация: docs/receiving.md.
"""
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from core import msk_time


def _env_int(name: str, default: int, low: int, high: int) -> int:
    """Целое из окружения в [low, high]; пусто или мусор — default (с предупреждением).

    Опечатка в .env не должна ронять запуск приложения: шедулер импортируется в
    app.py:_start_background_jobs до соседних шедулеров.
    """
    raw = os.environ.get(name, '').strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = None
    if value is None or not (low <= value <= high):
        print(f'[RECEIVING-SCHED] {name}={raw!r} не годится — беру {default}')
        return default
    return value


# Утреннее обновление индекса, МСК: 07:30 — до прихода бухгалтерии и первой машины на РЦ;
# ночные шедулеры iiko (ЗП, снимок /me, месячный отчёт) к этому времени отработали.
INDEX_HOUR = _env_int('RECEIVING_INDEX_HOUR', 7, 0, 23)
INDEX_MINUTE = _env_int('RECEIVING_INDEX_MINUTE', 30, 0, 59)
ENV_ENABLED = 'RECEIVING_INDEX_ENABLED'
# Сколько утренний прогон ждёт чужую пересборку (кнопку нажали в 07:29): 10 минут —
# с запасом к обычным 1-2 минутам; потом пересобирает сам (индекс свежее на минуты).
SCHEDULE_WAIT_SEC = 600

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# <repo>/data — на проде /app/data (том /srv/beer/data), общий для двух воркеров.
LOCK_DIR = os.path.join(_BASE_DIR, 'data')
LOCK_PREFIX = '.receiving_index_lock_'
# Lock-файлы старше 2 дней удаляются при старте (как у остальных шедулеров).
LOCK_KEEP_DAYS = 2

# Стартовая проверка — через 30 с после запуска: дать приложению подняться.
STARTUP_DELAY_SEC = 30
# Индекс старше 26 ч (сутки + 2 ч запаса) — утренний прогон пропущен: обновить при старте.
# Моложе — не трогать: частые деплои не должны каждый раз ходить в iiko.
STARTUP_MAX_AGE_HOURS = 26
# Подбор зависших обработок приёмок раз в 10 минут: зависшая (running) освобождается
# через PROCESS_STALE_SEC = 15 мин, так что задержка подбора — не больше 25 минут.
RETRY_INTERVAL_SEC = 600
# Пауза после сбоя в цикле, чтобы не крутиться вхолостую.
ERROR_PAUSE_SEC = 60

_LOG = '[RECEIVING-SCHED]'

_started = False
_lock = threading.Lock()


def _now() -> datetime:
    """Сейчас по Москве, наивное (для сравнения с часами из .env и даты lock-файла)."""
    return msk_time.now().replace(tzinfo=None)


def seconds_until(hour: int, minute: int, now: datetime) -> float:
    """Секунды до ближайшего hour:minute (МСК) строго после now; ровно в hour:minute — сутки."""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def needs_startup_refresh(info: Optional[dict]) -> bool:
    """Индекса нет (info None), возраст неизвестен или старше STARTUP_MAX_AGE_HOURS."""
    if not info:
        return True
    age = info.get('age_minutes')
    if not isinstance(age, int):
        return True
    return age > STARTUP_MAX_AGE_HOURS * 60


def index_enabled() -> bool:
    return os.environ.get(ENV_ENABLED, '1').strip() != '0'


def _try_acquire_lock(prefix: str, date_str: str) -> bool:
    """Atomic test-and-set на день (O_EXCL). True — этот воркер первый."""
    os.makedirs(LOCK_DIR, exist_ok=True)
    try:
        fd = os.open(os.path.join(LOCK_DIR, f'{prefix}{date_str}'),
                     os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    except OSError as e:
        print(f'{_LOG} lock-файл не создан: {e!r}')
        return False
    try:
        os.write(fd, f'{os.getpid()}\n'.encode())
    finally:
        os.close(fd)
    return True


def _cleanup_old_locks() -> None:
    """Удалить lock-файлы утреннего прогона старше LOCK_KEEP_DAYS дней."""
    if not os.path.isdir(LOCK_DIR):
        return
    cutoff = (_now() - timedelta(days=LOCK_KEEP_DAYS)).strftime('%Y-%m-%d')
    for fname in os.listdir(LOCK_DIR):
        if not fname.startswith(LOCK_PREFIX):
            continue
        date_part = fname[len(LOCK_PREFIX):]
        if len(date_part) == 10 and date_part < cutoff:
            try:
                os.remove(os.path.join(LOCK_DIR, fname))
            except OSError:
                pass


# ----------------------------------------------------------------- прогоны (без потоков)

def run_daily() -> Optional[dict]:
    """Утренний прогон: пересборка индекса + пересверка. Без кредов iiko — пропуск (None)."""
    from core import receiving_service
    if not receiving_service.iiko_configured():
        print(f'{_LOG} утро: креды iiko не заданы — индекс не обновляется')
        return None
    try:
        result = receiving_service.run_index_refresh('schedule', wait=SCHEDULE_WAIT_SEC)
    except Exception as e:  # noqa: BLE001 — текст ошибки уже в состоянии обновления индекса
        print(f'{_LOG} утро: индекс не обновлён ({type(e).__name__}: {e})')
        return None
    print(f'{_LOG} утро: индекс обновлён: {result}')
    return result


def run_startup() -> Optional[dict]:
    """Стартовый прогон: индекса нет или он старше суток — пересобрать (не ждать чужой)."""
    from core import receiving_index, receiving_service
    if not receiving_service.iiko_configured():
        return None
    info = receiving_index.index_info(receiving_index.load_index())
    if not needs_startup_refresh(info):
        print(f'{_LOG} индекс свежий ({info.get("built_at")}) — стартового обновления не будет')
        return None
    try:
        result = receiving_service.run_index_refresh('startup', wait=0)
    except receiving_index.RefreshBusy:
        print(f'{_LOG} старт: индекс уже обновляет другой воркер')
        return None
    except Exception as e:  # noqa: BLE001
        print(f'{_LOG} старт: индекс не обновлён ({type(e).__name__}: {e})')
        return None
    print(f'{_LOG} старт: индекс обновлён: {result}')
    return result


def retry_once() -> list:
    """Один проход подбора зависших обработок приёмок -> номера запущенных."""
    from core import receiving_service
    started = receiving_service.retry_stuck_processing()
    if started:
        print(f'{_LOG} снова запущена обработка приёмок: {started}')
    return started


# ----------------------------------------------------------------- циклы потоков

def _daily_loop():
    while True:
        try:
            wait = seconds_until(INDEX_HOUR, INDEX_MINUTE, _now())
            print(f'{_LOG} следующее обновление индекса через {wait / 3600:.1f} ч '
                  f'({INDEX_HOUR:02d}:{INDEX_MINUTE:02d} МСК)')
            time.sleep(wait)
            if _try_acquire_lock(LOCK_PREFIX, _now().strftime('%Y-%m-%d')):
                run_daily()
            time.sleep(ERROR_PAUSE_SEC)   # не попасть в ту же минуту повторно
        except Exception as e:  # noqa: BLE001 — цикл не должен умирать
            print(f'{_LOG} исключение в утреннем цикле: {e!r}')
            time.sleep(ERROR_PAUSE_SEC)


def _startup_once():
    time.sleep(STARTUP_DELAY_SEC)
    try:
        run_startup()
    except Exception as e:  # noqa: BLE001
        print(f'{_LOG} стартовое обновление: {e!r}')


def _retry_loop():
    # Первый проход — сразу после старта: приёмки, закрытые перед перезапуском (pending),
    # не ждут RETRY_INTERVAL_SEC.
    time.sleep(STARTUP_DELAY_SEC)
    while True:
        try:
            retry_once()
        except Exception as e:  # noqa: BLE001 — цикл не должен умирать
            print(f'{_LOG} исключение в подборе обработок: {e!r}')
        time.sleep(RETRY_INTERVAL_SEC)


def _start_thread(target, name: str) -> threading.Thread:
    """Запустить поток-демон (одно место: тесты подменяют, чтобы потоков не было)."""
    thread = threading.Thread(target=target, name=name, daemon=True)
    thread.start()
    return thread


def start_scheduler() -> None:
    """Запустить потоки-демоны приёмки. Идемпотентно (второй вызов ничего не делает).

    Подбор обработок — всегда. Утро и старт — если RECEIVING_INDEX_ENABLED != '0'
    и заданы креды iiko.
    """
    global _started
    with _lock:
        if _started:
            return
        _started = True
        try:
            _start_thread(_retry_loop, 'receiving-retry')
            if not index_enabled():
                print(f'{_LOG} обновление индекса по расписанию выключено ({ENV_ENABLED}=0); '
                      f'подбор обработок приёмок работает')
                return
            from core import receiving_service
            if not receiving_service.iiko_configured():
                print(f'{_LOG} креды iiko не заданы — индекс по расписанию не обновляется; '
                      f'подбор обработок приёмок работает')
                return
            _cleanup_old_locks()
            _start_thread(_daily_loop, 'receiving-index-daily')
            _start_thread(_startup_once, 'receiving-index-startup')
            print(f'{_LOG} запущен: индекс ежедневно в {INDEX_HOUR:02d}:{INDEX_MINUTE:02d} МСК, '
                  f'подбор обработок раз в {RETRY_INTERVAL_SEC // 60} мин')
        except Exception as e:  # noqa: BLE001 — сбой приёмки не должен ронять запуск приложения
            print(f'{_LOG} не запущен: {type(e).__name__}: {e}')
