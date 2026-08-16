"""Ежедневный запуск проверки открытых смен в 14:59 МСК.

Паттерн скопирован с core/chz_scheduler.py с тремя отличиями:

1. Явный МСК: на Render контейнер UTC, поэтому datetime.now(MOSCOW_TZ) вместо
   локального datetime.now().
2. Защита от двойного срабатывания под gunicorn --workers 2: первый воркер,
   проснувшийся в 14:59, создаёт atomic lock-файл через
   os.open(O_CREAT | O_EXCL); второй ловит FileExistsError и тихо выходит.
3. Гейт по env: если TELEGRAM_OPEN_CHECK_BOT_TOKEN не задан — шедулер не
   стартует (аналог REMOTE_PASS в chz_scheduler).

Lock-файлы кладутся в data/. На проде это /app/data, смонтированный на хост
(/srv/beer/data в docker-compose.yml) — lock переживает пересборку контейнера.
Это НЕСУЩЕЕ для catch-up: после деплоя поверх 14:59 lock за сегодня уже на
диске, повторной отправки не будет (иначе каждый вечерний деплой дублировал бы
сообщение). На следующий день в имени файла другая дата, старые удаляются при
старте.

Гарантия доставки (после пропуска тревоги 2026-08-16, docs/lessons.md):

- catch-up: если процесс стартовал ПОСЛЕ 14:59, а lock за сегодня не взят
  (рестарт/деплой поверх времени проверки) — проверка запускается сразу, с
  честной пометкой в сообщении. Раньше день молча терялся: _seconds_until_next_run
  ждал бы завтрашних 14:59.
- resend-поток: раз в RESEND_INTERVAL_SEC досылает недоставленное из
  core/open_check_pending.py, пока не доставит всем или не кончится день.
- падение run_check теперь шлёт тревогу (send_crash_alarm), а не только print:
  lock за день уже взят, второй попытки не будет — молчать нельзя.
- жизненный цикл lock-файла: при взятии в него пишется 'running', после
  завершения прогона (успех ИЛИ обработанное падение) — 'done'. Если воркер
  умер посреди прогона (SIGTERM деплоя, рецикл gunicorn --max-requests) —
  содержимое остаётся 'running', и resend-поток через _RUN_GRACE_SEC
  переигрывает проверку (_recover_interrupted_run). Иначе: lock есть,
  сообщения нет, crash-тревога не сработала (процесс убит), catch-up
  заблокирован существующим lock-ом — тихая потеря дня. Lock-и старого
  формата (только pid) считаются завершёнными — деплой поверх уже
  отработавшего дня дубля не даёт.
"""
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import portalocker

from core.open_check_bot import MOSCOW_TZ, now_msk, run_check, send_crash_alarm

CHECK_HOUR = int(os.environ.get("OPEN_CHECK_HOUR", "14"))
CHECK_MINUTE = int(os.environ.get("OPEN_CHECK_MINUTE", "59"))

# Период досылки недоставленного. 5 минут: блокировка ТСПУ «мигает» на
# секунды-минуты (наблюдение 2026-08-16), чаще дёргать Telegram смысла нет,
# реже — тревога опаздывает сильнее необходимого.
RESEND_INTERVAL_SEC = 300

# Через сколько секунд lock со статусом 'running' считается прерванным
# прогоном (воркер убит посреди проверки). Больше худшего реального прогона:
# iiko (2 попытки x 60с + backoff, см. --timeout 180 в Dockerfile) + 2 прохода
# отправки по ~45с на чат + пауза 10с ~= 8-10 минут. 15 минут — с запасом.
_RUN_GRACE_SEC = 900

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_DIR = os.path.join(_BASE_DIR, 'data')
LOCK_PREFIX = '.open_check_lock_'

_started = False
_lock = threading.Lock()


def _seconds_until_next_run(hour: int, minute: int) -> float:
    """Сколько секунд до следующего срабатывания в указанное МСК-время."""
    now = datetime.now(MOSCOW_TZ)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


def _lock_path(date_str: str) -> str:
    return os.path.join(LOCK_DIR, f'{LOCK_PREFIX}{date_str}')


def _try_acquire_daily_lock(date_str: str) -> bool:
    """Atomic test-and-set на день. True если этот воркер первый.

    В файл пишется 'running <pid>' — маркер идущего прогона для
    _recover_interrupted_run. Ошибка записи содержимого НЕ фатальна: сам факт
    существования файла — это и есть lock, а без 'running' recovery просто не
    станет переигрывать (день без маркера считается завершённым).
    """
    os.makedirs(LOCK_DIR, exist_ok=True)
    try:
        fd = os.open(_lock_path(date_str), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    try:
        os.write(fd, f'running {os.getpid()}\n'.encode())
    except OSError as e:
        # Диск полон: lock всё равно взят (файл создан), прогон продолжаем —
        # отправка в Telegram диска не требует.
        print(f"[OPEN-CHECK] маркер 'running' не записан в lock ({e}) — lock всё равно взят")
    finally:
        os.close(fd)
    return True


def _mark_lock_done(date_str: str) -> None:
    """Пометить дневной lock завершённым ('done') — прогон отработал (успешно
    или падение обработано crash-тревогой), recovery переигрывать нечего."""
    try:
        with open(_lock_path(date_str), 'w', encoding='utf-8') as f:
            f.write('done\n')
    except OSError as e:
        print(f"[OPEN-CHECK] маркер 'done' не записан в lock ({e}) — "
              f"возможен повторный прогон recovery через {_RUN_GRACE_SEC}s")


def _lock_content(date_str: str) -> Optional[str]:
    """Содержимое дневного lock-файла или None (файла нет / не читается)."""
    try:
        with open(_lock_path(date_str), encoding='utf-8') as f:
            return f.read()
    except OSError:
        return None


def _cleanup_old_locks() -> None:
    """Удалить lock-файлы старше 2 дней. Защита от мусора."""
    if not os.path.isdir(LOCK_DIR):
        return
    today = datetime.now(MOSCOW_TZ).strftime('%Y-%m-%d')
    cutoff = (datetime.now(MOSCOW_TZ) - timedelta(days=2)).strftime('%Y-%m-%d')
    for fname in os.listdir(LOCK_DIR):
        if not fname.startswith(LOCK_PREFIX):
            continue
        date_part = fname[len(LOCK_PREFIX):]
        if len(date_part) == 10 and date_part < cutoff and date_part != today:
            try:
                os.remove(os.path.join(LOCK_DIR, fname))
            except OSError:
                pass


_done_dates = set()  # процессная память завершённых дней (страховка recovery,
                     # если 'done' не записался на переполненный диск)


def _run_once(note: Optional[str] = None) -> None:
    """Одно срабатывание: lock + run_check (+ тревога, если run_check упал)."""
    check_dt = now_msk()
    date_str = check_dt.strftime('%Y-%m-%d')
    try:
        acquired = _try_acquire_daily_lock(date_str)
    except OSError as e:
        # Lock-файл не создался (диск/ФС). Раньше OSError улетал в _loop и день
        # молча терялся. Проверку без lock-а запускать нельзя (дубль от второго
        # воркера), но тревогу — можно: Telegram диска не требует.
        print(f"[OPEN-CHECK] {check_dt.isoformat()} lock-файл не создан: {e}")
        try:
            send_crash_alarm(check_dt, f"lock-файл не создан: {e}")
        except Exception as e2:
            print(f"[OPEN-CHECK] send_crash_alarm тоже упал: {e2}")
        return
    if not acquired:
        print(f"[OPEN-CHECK] {check_dt.isoformat()} lock уже взят другим воркером — пропуск")
        return
    print(f"[OPEN-CHECK] {check_dt.isoformat()} trigger")
    try:
        result = run_check(check_dt=check_dt, note=note)
        print(f"[OPEN-CHECK] результат: {result}")
    except Exception as e:
        # lock за день уже взят — второй попытки не будет. Молчать нельзя:
        # шлём тревогу «проверка упала» (с ретраями и очередью досылки).
        print(f"[OPEN-CHECK] {check_dt.isoformat()} run_check failed: {e}")
        try:
            send_crash_alarm(check_dt, str(e))
        except Exception as e2:
            print(f"[OPEN-CHECK] send_crash_alarm тоже упал: {e2}")
    finally:
        # Прогон отработал (успех или обработанное падение) — день закрыт.
        # Не дошли сюда = процесс убит посреди прогона: содержимое lock-а
        # останется 'running', и recovery переиграет проверку.
        _mark_lock_done(date_str)
        _done_dates.add(date_str)


def _catch_up_if_missed(now: Optional[datetime] = None) -> bool:
    """Рестарт/деплой поверх 14:59: если время проверки за сегодня прошло, а
    lock не взят — запустить проверку сейчас, с пометкой в сообщении.

    now — DI для тестов. Возвращает True, если catch-up запускался.
    Гонку двух воркеров разруливает atomic lock внутри _run_once; проверка
    существования lock-файла здесь — только чтобы не шуметь в логах на каждом
    старте.
    """
    if now is None:
        now = datetime.now(MOSCOW_TZ)
    target = now.replace(hour=CHECK_HOUR, minute=CHECK_MINUTE, second=0, microsecond=0)
    if now < target:
        return False
    lock_path = os.path.join(LOCK_DIR, f"{LOCK_PREFIX}{now.strftime('%Y-%m-%d')}")
    if os.path.exists(lock_path):
        return False
    print(f"[OPEN-CHECK] {now.isoformat()} проверка за сегодня не выполнялась "
          f"(рестарт поверх {CHECK_HOUR:02d}:{CHECK_MINUTE:02d}?) — catch-up")
    _run_once(note=(f"Проверка должна была пройти в {CHECK_HOUR:02d}:{CHECK_MINUTE:02d} МСК, "
                    f"выполнена позже из-за перезапуска сервиса"))
    return True


def _loop() -> None:
    try:
        _catch_up_if_missed()
    except Exception as e:
        print(f"[OPEN-CHECK] catch-up failed: {e}")
    while True:
        try:
            wait = _seconds_until_next_run(CHECK_HOUR, CHECK_MINUTE)
            next_at = datetime.now(MOSCOW_TZ) + timedelta(seconds=wait)
            print(f"[OPEN-CHECK] следующая проверка: {next_at.isoformat()} (через {wait/3600:.1f}ч)")
            time.sleep(wait)
            _run_once()
            # Не дать циклу прокрутиться слишком быстро, если _run_once упал мгновенно.
            time.sleep(60)
        except Exception as e:
            # Не даём исключению (например OSError из lock-файла) молча убить
            # daemon-поток — иначе проверка открытых смен перестанет срабатывать
            # до рестарта. Логируем и продолжаем после паузы.
            print(f"[OPEN-CHECK] исключение в цикле планировщика: {e}")
            time.sleep(60)


def _recover_interrupted_run(now: Optional[datetime] = None) -> bool:
    """Переиграть прогон, прерванный смертью процесса (SIGTERM деплоя, рецикл
    gunicorn --max-requests) ПОСЛЕ взятия дневного lock-а: crash-тревога в этом
    случае не срабатывает (процесс убит), catch-up заблокирован существующим
    lock-ом — без recovery день терялся бы тихо.

    Признак прерванного прогона: lock за сегодня существует, содержимое
    начинается с 'running', mtime старше _RUN_GRACE_SEC. Lock-и старого формата
    (pid без 'running') и 'done' считаются завершёнными. Двух воркеров
    арбитрирует portalocker на отдельном файле + перечитывание под локом.

    Зовётся из resend-цикла раз в RESEND_INTERVAL_SEC. now — DI для тестов.
    Возвращает True, если переигрывание запускалось.

    Принятый остаток: умереть можно и МЕЖДУ доставкой и записью 'done' — тогда
    получатели получат прогон дважды (с пометкой о повторе). Дубль лучше потери.
    """
    if now is None:
        now = datetime.now(MOSCOW_TZ)
    target = now.replace(hour=CHECK_HOUR, minute=CHECK_MINUTE, second=0, microsecond=0)
    if now < target + timedelta(seconds=_RUN_GRACE_SEC):
        return False  # штатному прогону ещё рано или он, возможно, ещё идёт
    date_str = now.strftime('%Y-%m-%d')
    if date_str in _done_dates:
        return False

    content = _lock_content(date_str)
    if content is None:
        # Lock-а нет вообще спустя grace после 14:59: _loop-поток мёртв, а
        # catch-up был только на старте. _run_once сам возьмёт lock атомарно.
        print(f"[OPEN-CHECK] {now.isoformat()} lock за сегодня отсутствует спустя "
              f"{_RUN_GRACE_SEC}s после {CHECK_HOUR:02d}:{CHECK_MINUTE:02d} — recovery")
        _run_once(note=(f"Проверка должна была пройти в {CHECK_HOUR:02d}:{CHECK_MINUTE:02d} МСК, "
                        f"не выполнилась вовремя — запущена повторно контрольным циклом"))
        return True
    if not content.startswith('running'):
        _done_dates.add(date_str)  # 'done' или старый формат (pid) — день закрыт
        return False
    try:
        if time.time() - os.path.getmtime(_lock_path(date_str)) < _RUN_GRACE_SEC:
            return False  # прогон, возможно, ещё идёт
    except OSError:
        return False

    recovery_lock = os.path.join(LOCK_DIR, '.open_check_recovery.lock')
    try:
        with portalocker.Lock(recovery_lock, mode='a', timeout=1):
            # Перечитать под локом: второй воркер мог только что переиграть.
            content = _lock_content(date_str)
            if content is None or not content.startswith('running'):
                _done_dates.add(date_str)
                return False
            try:
                if time.time() - os.path.getmtime(_lock_path(date_str)) < _RUN_GRACE_SEC:
                    return False
            except OSError:
                return False
            print(f"[OPEN-CHECK] {now.isoformat()} прогон за {date_str} был прерван "
                  f"(lock='running', mtime старше {_RUN_GRACE_SEC}s) — переигрываю")
            try:
                # Освежить mtime: если и recovery убьют, следующий повтор —
                # только через grace, а не на каждом тике.
                with open(_lock_path(date_str), 'w', encoding='utf-8') as f:
                    f.write(f'running {os.getpid()} recovery\n')
            except OSError:
                pass
            check_dt = now_msk()
            try:
                result = run_check(
                    check_dt=check_dt,
                    note=(f"Проверка {CHECK_HOUR:02d}:{CHECK_MINUTE:02d} МСК была прервана "
                          f"перезапуском сервиса — выполнена повторно"))
                print(f"[OPEN-CHECK] recovery результат: {result}")
            except Exception as e:
                print(f"[OPEN-CHECK] recovery run_check failed: {e}")
                try:
                    send_crash_alarm(check_dt, str(e))
                except Exception as e2:
                    print(f"[OPEN-CHECK] send_crash_alarm тоже упал: {e2}")
            _mark_lock_done(date_str)
            _done_dates.add(date_str)
            return True
    except portalocker.exceptions.BaseLockException:
        return False  # второй воркер уже занимается recovery


def _resend_loop() -> None:
    """Досылка недоставленного из core/open_check_pending.py + контроль, что
    сегодняшний прогон не был прерван смертью процесса (_recover_interrupted_run).

    Крутится в обоих gunicorn-воркерах; от двойной отправки защищают клейм в
    resend_due и portalocker в recovery. Сначала sleep: на старте очередь либо
    пуста, либо только что наполнена catch-up'ом (мгновенный повтор
    бессмысленен — Telegram только что не ответил).
    """
    from core import open_check_pending
    while True:
        time.sleep(RESEND_INTERVAL_SEC)
        try:
            _recover_interrupted_run()
        except Exception as e:
            print(f"[OPEN-CHECK] исключение в recovery: {e}")
        try:
            result = open_check_pending.resend_due(now_msk().strftime('%Y-%m-%d'))
            if result.get('status') not in ('empty', 'busy'):
                print(f"[OPEN-CHECK] resend: {result}")
        except Exception as e:
            # Аналогично _loop: исключение не должно убить daemon-поток.
            print(f"[OPEN-CHECK] исключение в resend-цикле: {e}")


def start_scheduler() -> None:
    """Запустить daemon-потоки (проверка + досылка). Идемпотентно."""
    global _started
    with _lock:
        if _started:
            return
        if not os.environ.get("TELEGRAM_OPEN_CHECK_BOT_TOKEN"):
            print("[OPEN-CHECK] TELEGRAM_OPEN_CHECK_BOT_TOKEN не задан — шедулер отключён")
            return
        _cleanup_old_locks()
        t = threading.Thread(target=_loop, name="open-check-scheduler", daemon=True)
        t.start()
        r = threading.Thread(target=_resend_loop, name="open-check-resend", daemon=True)
        r.start()
        _started = True
        print(f"[OPEN-CHECK] стартовал, проверка ежедневно в {CHECK_HOUR:02d}:{CHECK_MINUTE:02d} МСК, "
              f"досылка недоставленного каждые {RESEND_INTERVAL_SEC // 60} мин")
