"""Ночной пересчёт снимка личного кабинета (`/me`).

Раз в сутки собирает показатели, KPI и деньги по всем сотрудникам и кладёт на
том (`core/me_snapshot.py`). Считает текущий месяц всегда, предыдущий — пока
число <= ME_SNAPSHOT_PREV_UNTIL_DAY (по умолчанию 7): закрытый месяц ещё неделю
подтягивает поздние правки графика и кассы, потом заморожен.

ПОЧЕМУ ОТДЕЛЬНЫЙ ШЕДУЛЕР, а не расширение `core/salary_scheduler.py`:
- тот гейтится на наличие Google-кредов (`_configured`: SALARY_SHEET_ID + ключ
  сервис-аккаунта) и без них вообще не поднимает поток. Снимок к Google
  отношения не имеет, и привязка к этому гейту означала бы «нет Google — у
  барменов пустой личный кабинет»;
- разная семантика сбоя: там сбой месяца = «пропустить месяц, вкладку не
  создавать», здесь = «сохранить прежний файл целиком»;
- свой дневной lock-файл: общий шедулер означал бы, что упавшая
  Google-выгрузка забирает лок у снимка.

ВРЕМЯ — ВАЖНО И НЕОЧЕВИДНО. В прод-образе нет системного tzdata, переменная
TZ=Europe/Moscow на libc не действует, и наивный `datetime.now()` отдаёт UTC
(docs/lessons.md, core/msk_time.py). Поэтому ME_SNAPSHOT_HOUR=5 MINUTE=40 — это
фактически 08:40 МСК. Не «поправляйте» на 5 утра, думая, что это Москва: так же
работают ВСЕ существующие шедулеры проекта (ЧЗ 03:00 = 06:00 МСК, ЗП 04:00 =
07:00 МСК, месячный отчёт 04:30, гости 05:10). Снимок стоит последним
осознанно: он потребляет те же кассовые смены и OLAP, что выгрузка ЗП, и не
должен конкурировать с ней за воркеры.

Дата и месяц берутся из `core.msk_time` — иначе прогон в интервале 00:00-03:00
МСК первого числа посчитал бы «текущим» прошлый месяц.

ЗАЩИТА ОТ ДВОЙНОГО ЗАПУСКА (gunicorn --workers 2): каждый воркер стартует свой
поток; в момент прогона первый берёт atomic lock-file (O_CREAT|O_EXCL) на дату,
второй ловит FileExistsError и пропускает. Тот же паттерн, что в
salary_scheduler / monthly_report_scheduler / chz_scheduler.

Выключается ME_SNAPSHOT_ENABLED=0.
"""
import os
import threading
import time
from datetime import datetime, timedelta

SNAP_HOUR = int(os.environ.get('ME_SNAPSHOT_HOUR', '5'))
SNAP_MINUTE = int(os.environ.get('ME_SNAPSHOT_MINUTE', '40'))

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_DIR = os.path.join(_BASE_DIR, 'data')
LOCK_PREFIX = '.me_snapshot_lock_'
STARTUP_LOCK_PREFIX = '.me_snapshot_startup_'

_started = False
_lock = threading.Lock()
_app = None


def _enabled():
    return (os.environ.get('ME_SNAPSHOT_ENABLED', '1') or '1').strip() not in ('0', 'false', 'no')


def _iiko_configured():
    """Есть ли креды iiko. Без них прогон гарантированно ничего не посчитает."""
    try:
        import config
        if (config.IIKO_LOGIN or '').strip() and (config.IIKO_PASSWORD or '').strip():
            return True, ''
        return False, 'IIKO_LOGIN/IIKO_PASSWORD ne zadany'
    except Exception as e:
        return False, f'nastroyki iiko nedostupny: {e}'


def _seconds_until_next_run(hour, minute):
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


def _try_acquire_lock(prefix: str, date_str: str) -> bool:
    """Atomic test-and-set на день. True — этот воркер первый."""
    os.makedirs(LOCK_DIR, exist_ok=True)
    lock_path = os.path.join(LOCK_DIR, f'{prefix}{date_str}')
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, f'{os.getpid()}\n'.encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError as e:
        print(f"[ME-SNAPSHOT-SCHED] lock ne sozdan: {e}")
        return False


def _cleanup_old_locks():
    """Убрать дневные локи старше двух суток. Вызывается один раз при старте."""
    from core.msk_time import today as msk_today

    today = msk_today().isoformat()
    cutoff = (msk_today() - timedelta(days=2)).isoformat()
    try:
        for name in os.listdir(LOCK_DIR):
            if not (name.startswith(LOCK_PREFIX) or name.startswith(STARTUP_LOCK_PREFIX)):
                continue
            date_part = name.split('_')[-1]
            if len(date_part) == 10 and date_part < cutoff and date_part != today:
                try:
                    os.unlink(os.path.join(LOCK_DIR, name))
                except OSError:
                    pass
    except OSError:
        pass


def _run(tag: str):
    from core.me_snapshot import months_to_build, run_build

    started = time.time()
    months = months_to_build()
    try:
        run_build(_context_app(), months, tag=tag)
        print(f"[ME-SNAPSHOT-SCHED] {datetime.now().isoformat()} {tag}: "
              f"{', '.join(months)} za {time.time() - started:.0f}s")
    except Exception as e:
        print(f"[ME-SNAPSHOT-SCHED] {datetime.now().isoformat()} {tag} oshibka: {e}")


def _context_app():
    """Приложение как контекст запроса для внутреннего вызова расчётов.

    Обычно боевое из `start_scheduler`. Пустой Flask — фоллбэк для разового
    процесса (CLI), где `start_scheduler` не отрабатывал: расчётам приложение
    нужно ТОЛЬКО как `test_request_context`. Импортировать здесь `app.py` нельзя
    — его импорт поднимает все шедулеры и long-polling Telegram (см. тот же
    приём и то же объяснение в core/salary_scheduler.py).
    """
    if _app is not None:
        return _app
    from flask import Flask
    return Flask('me-snapshot')


def _nightly_loop():
    from core.msk_time import today as msk_today

    while True:
        try:
            wait = _seconds_until_next_run(SNAP_HOUR, SNAP_MINUTE)
            next_at = datetime.now() + timedelta(seconds=wait)
            print(f"[ME-SNAPSHOT-SCHED] sleduyushchiy pereraschet: {next_at.isoformat()} "
                  f"(cherez {wait/3600:.1f}ch)")
            time.sleep(wait)
            if _try_acquire_lock(LOCK_PREFIX, msk_today().isoformat()):
                _run('nightly')
            else:
                print("[ME-SNAPSHOT-SCHED] lock uzhe vzyat drugim vorkerom — propusk")
            time.sleep(60)   # не дать циклу прокрутиться слишком быстро
        except Exception as e:
            print(f"[ME-SNAPSHOT-SCHED] isklyuchenie v cikle: {e}")
            time.sleep(60)


def _startup_if_missing():
    """Разовый прогон при старте, ТОЛЬКО если файла текущего месяца ещё нет.

    Компромисс: свежий деплой на пустой том получает данные без участия
    человека, а тёплый рестарт не делает ничего — проверка `os.path.exists`
    отрабатывает до всякого обращения к iiko. `salary_scheduler` от стартового
    прогона отказался вовсе, но там он писал бы во внешнюю таблицу; здесь
    результат локальный.
    """
    from core.me_snapshot import current_month, month_path
    from core.msk_time import today as msk_today

    time.sleep(20)   # дать приложению подняться
    try:
        if os.path.exists(month_path(current_month())):
            return
        if not _try_acquire_lock(STARTUP_LOCK_PREFIX, msk_today().isoformat()):
            return
        print("[ME-SNAPSHOT-SCHED] snimka tekushchego mesyaca net — schitayu pri starte")
        _run('startup')
    except Exception as e:
        print(f"[ME-SNAPSHOT-SCHED] startovy progon oshibka: {e}")


def start_scheduler(app=None):
    """Запустить ночной пересчёт снимка. Идемпотентно."""
    global _started, _app
    with _lock:
        if _started:
            return
        _app = app
        if not _enabled():
            print("[ME-SNAPSHOT-SCHED] otklyuchen (ME_SNAPSHOT_ENABLED=0)")
            return
        ok, why = _iiko_configured()
        if not ok:
            print(f"[ME-SNAPSHOT-SCHED] ne nastroen: {why} — pereraschet otklyuchen")
            return
        _cleanup_old_locks()
        threading.Thread(target=_nightly_loop, name='me-snapshot-scheduler',
                         daemon=True).start()
        threading.Thread(target=_startup_if_missing, name='me-snapshot-startup',
                         daemon=True).start()
        _started = True
        print(f"[ME-SNAPSHOT-SCHED] startoval, pereraschet ezhednevno v "
              f"{SNAP_HOUR:02d}:{SNAP_MINUTE:02d} naivnogo vremeni "
              f"(= {(SNAP_HOUR + 3) % 24:02d}:{SNAP_MINUTE:02d} MSK) "
              f"+ startovy progon, esli snimka net")
