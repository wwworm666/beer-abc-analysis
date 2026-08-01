"""Ночная выгрузка расчёта ЗП в Google Таблицу бухгалтерии.

Раз в сутки (по умолчанию 04:00) собирает payload расчёта на сервере
(`core/salary_payload.py` — тот же мёрж, что делает страница /salary) и
переписывает в таблице `SALARY_SHEET_ID` вкладку «Июль_2026_Автоматическая».

ЧТО ВЫГРУЖАЕТСЯ: текущий месяц всегда — вкладка появляется 1-го числа и
наполняется по ходу месяца (в первые дни продаж ещё нет, премии честно нулевые,
часы и смены уже идут из графика). Плюс предыдущий месяц, пока число
<= SALARY_SYNC_PREV_UNTIL_DAY (по умолчанию 7): закрытый месяц ещё неделю
подтягивает поздние правки графика и кассы.

ПОЧЕМУ ОТДЕЛЬНАЯ ВКЛАДКА: ручная вкладка месяца («июль2026») содержит строки,
которых приложение не знает — «мосты», отпуск, доп доход, вычеты инвент/доп.
Ночная задача переписывает лист целиком, поэтому пишет в свой, соседний
(решение владельца 2026-08-01).

Время — env SALARY_SYNC_HOUR/MINUTE (default 04:00 локального времени).
Выключается SALARY_SYNC_ENABLED=0.

ЗАЩИТА ОТ ДВОЙНОГО ЗАПУСКА (gunicorn --workers 2): каждый воркер стартует свой
поток; в момент прогона первый берёт atomic lock-file (O_CREAT|O_EXCL) на дату,
второй ловит FileExistsError и пропускает. Тот же паттерн, что в
monthly_report_scheduler / chz_scheduler.
"""
import os
import threading
import time
from datetime import date, datetime, timedelta

SYNC_HOUR = int(os.environ.get('SALARY_SYNC_HOUR', '4'))
SYNC_MINUTE = int(os.environ.get('SALARY_SYNC_MINUTE', '0'))
# До какого числа месяца ещё обновлять предыдущий: закрытый месяц неделю
# подтягивает поздние правки графика и кассы
PREV_UNTIL_DAY = int(os.environ.get('SALARY_SYNC_PREV_UNTIL_DAY', '7'))

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_DIR = os.path.join(_BASE_DIR, 'data')
LOCK_PREFIX = '.salary_sync_lock_'

_started = False
_lock = threading.Lock()
_app = None


def _enabled():
    return (os.environ.get('SALARY_SYNC_ENABLED', '1') or '1').strip() not in ('0', 'false', 'no')


def _configured():
    """Есть ли куда и чем писать (ключ сервис-аккаунта + целевая таблица)."""
    if not (os.environ.get('SALARY_SHEET_ID') or '').strip():
        return False, 'SALARY_SHEET_ID ne zadan'
    key = os.environ.get('GOOGLE_SA_JSON') or '/app/secrets/google-sa.json'
    if not os.environ.get('GOOGLE_SA_JSON_CONTENT') and not os.path.exists(key):
        return False, f'net klyucha servis-akkaunta ({key})'
    return True, ''


def _seconds_until_next_run(hour, minute):
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


def _try_acquire_lock(date_str: str) -> bool:
    """Atomic test-and-set на день. True если этот воркер первый."""
    os.makedirs(LOCK_DIR, exist_ok=True)
    lock_path = os.path.join(LOCK_DIR, f'{LOCK_PREFIX}{date_str}')
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, f'{os.getpid()}\n'.encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False


def _cleanup_old_locks() -> None:
    """Удалить lock-файлы старше 2 дней."""
    if not os.path.isdir(LOCK_DIR):
        return
    cutoff = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    for fname in os.listdir(LOCK_DIR):
        if not fname.startswith(LOCK_PREFIX):
            continue
        date_part = fname[len(LOCK_PREFIX):]
        if len(date_part) == 10 and date_part < cutoff:
            try:
                os.remove(os.path.join(LOCK_DIR, fname))
            except OSError:
                pass


def months_to_sync(today: date = None) -> list:
    """Какие месяцы выгружать сегодня: текущий (+ предыдущий первую неделю)."""
    from core.salary_payload import previous_month
    today = today or date.today()
    current = today.strftime('%Y-%m')
    months = [current]
    if today.day <= PREV_UNTIL_DAY:
        months.append(previous_month(current))
    return months


def sync_once(tag: str = 'manual') -> dict:
    """Выгрузить нужные месяцы. Возвращает {месяц: результат|ошибка}."""
    from core.salary_gsheet import sync_to_master
    from core.salary_payload import build_payload_for_month

    results = {}
    for month in months_to_sync():
        started = time.time()
        # Сбой одного месяца не должен ронять остальные: каждый месяц
        # обрабатывается независимо, ошибка попадает в результат и в лог
        try:
            payload = build_payload_for_month(_app, month)
            # Пусто = ни продаж, ни смен в графике. Вкладку не создаём: писать
            # нечего, а пустой лист только мусорил бы в таблице
            if not payload.get('employees'):
                print(f"[SALARY-SYNC] {tag} {month}: net dannyh i grafika — propusk")
                results[month] = 'пусто'
                continue
            res = sync_to_master(payload)
            print(f"[SALARY-SYNC] {datetime.now().isoformat()} {tag} {month}: "
                  f"vkladka {res['tab']}, {len(payload['employees'])} sotr., "
                  f"{time.time() - started:.0f}s")
            results[month] = res
        except Exception as e:
            print(f"[SALARY-SYNC] {datetime.now().isoformat()} {tag} {month} oshibka: {e}")
            results[month] = f"ошибка: {e}"
    return results


def _nightly_loop():
    while True:
        try:
            wait = _seconds_until_next_run(SYNC_HOUR, SYNC_MINUTE)
            next_at = datetime.now() + timedelta(seconds=wait)
            print(f"[SALARY-SYNC] sleduyushchaya vygruzka: {next_at.isoformat()} "
                  f"(cherez {wait/3600:.1f}ch)")
            time.sleep(wait)
            date_str = datetime.now().strftime('%Y-%m-%d')
            if _try_acquire_lock(date_str):
                sync_once('nightly')
            else:
                print("[SALARY-SYNC] lock uzhe vzyat drugim vorkerom — propusk")
            time.sleep(60)   # не дать циклу прокрутиться слишком быстро
        except Exception as e:
            print(f"[SALARY-SYNC] isklyuchenie v cikle: {e}")
            time.sleep(60)


def start_scheduler(app):
    """Запустить daemon-поток ночной выгрузки. Идемпотентно.

    Стартового прогона нет намеренно: выгрузка ходит в iiko и пишет во
    внешнюю таблицу — на каждом рестарте это лишняя нагрузка и лишняя запись.
    """
    global _started, _app
    with _lock:
        if _started:
            return
        _app = app
        if not _enabled():
            print("[SALARY-SYNC] otklyuchena (SALARY_SYNC_ENABLED=0)")
            return
        ok, why = _configured()
        if not ok:
            print(f"[SALARY-SYNC] ne nastroena: {why} — vygruzka otklyuchena")
            return
        _cleanup_old_locks()
        threading.Thread(target=_nightly_loop, name='salary-gsheet-sync',
                         daemon=True).start()
        _started = True
        print(f"[SALARY-SYNC] startoval, vygruzka ezhednevno v "
              f"{SYNC_HOUR:02d}:{SYNC_MINUTE:02d} (tekushchiy mesyats"
              f" + predydushchiy do {PREV_UNTIL_DAY} chisla)")
