"""ETL модуля «Аналитика гостей (CRM)»: iiko OLAP -> guests.db.

Наполняет локальную витрину (core/guest_store.py) помесячно, от старых месяцев
к новым — покрытие данных всегда непрерывный отрезок [GUESTS_BACKFILL_FROM ..
текущий месяц], и любой Lifetime-показатель корректен для загруженного диапазона.

Запросы к iiko последовательные с паузой (щадим сервер), одна сессия
connect()/disconnect() на прогон. Ресинк месяца идемпотентен: DELETE + INSERT
одной транзакцией (guest_store.replace_month).

Расписание (core/guest_sync_scheduler.py): ночью пересинкается ТЕКУЩИЙ месяц;
предыдущий — только в первые 2 дня нового месяца (стык: ночной запуск 1-го числа
обязан дозагрузить чеки за последний день прошлого месяца). Ретро-правок чеков
в барах не делают (решение владельца 2026-07-15), поэтому более старые месяцы
заморожены (frozen=1) и пересинкаются только вручную с force.

Границы истории: GUESTS_BACKFILL_FROM (env, 'YYYY-MM'), по разведке Фазы 0
самый ранний гостевой чек — 2017-12-18, поэтому дефолт 2017-12.

CLI для ручного прогона/бэкфилла: py -3 -m core.guest_sync [--force]

Документация: docs/guests.md
"""

import os
import threading
import time
from datetime import date, datetime

from core.venues_config import IIKO_NAME_TO_KEY

BACKFILL_FROM_DEFAULT = "2017-12"
PAUSE_BETWEEN_REQUESTS_SEC = 0.4

# Прогресс текущего прогона (для /api/guests/sync-status и single-flight запуска)
_SYNC_LOCK = threading.Lock()
_SYNC_STATE = {
    'running': False,
    'started_at': None,
    'finished_at': None,
    'current_month': None,
    'done': 0,
    'total': 0,
    'error': None,
}


def normalize_guest_id(value):
    """Канонизация идентификатора гостя (телефона или номера карты).

    Находка Фазы 0 (2026-07-15, живые данные): CustomerPhone хранится с лишней
    ведущей 7 относительно CustomerCardNumber (карта 79XXXXXXXXX, телефон
    779XXXXXXXXX) — это один номер в разных форматах; у пластиковых карт
    (короткий код 100XXXXX) телефон настоящий и связывается псевдонимом.

    Правило: только цифры; цифр >= 10 -> '7' + последние 10 цифр (покрывает
    9XX..., 79XX..., 89XX..., 779XX...); цифр < 10 (код пластика) — цифры как
    есть; цифр нет — строка без крайних пробелов; пусто -> ''.
    """
    if not value:
        return ''
    raw = str(value).strip()
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if not digits:
        return raw
    if len(digits) >= 10:
        return '7' + digits[-10:]
    return digits


def month_bounds(ym):
    """'YYYY-MM' -> (первый день месяца, первый день следующего месяца).
    Правая граница ЭКСКЛЮЗИВНАЯ (конвенция OpenDate.Typed DateRange)."""
    y, m = int(ym[:4]), int(ym[5:7])
    start = date(y, m, 1)
    end_excl = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start.isoformat(), end_excl.isoformat()


def iter_months(from_ym, to_ym):
    """Список месяцев 'YYYY-MM' от from_ym до to_ym включительно."""
    months = []
    y, m = int(from_ym[:4]), int(from_ym[5:7])
    while True:
        ym = f"{y}-{m:02d}"
        months.append(ym)
        if ym >= to_ym:
            break
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return months


def _store_key(iiko_store_name):
    """Название бара из iiko -> ключ заведения; неизвестные (исторические,
    например закрытые бары) сохраняются исходным названием — детерминированно."""
    name = (iiko_store_name or '').strip()
    return IIKO_NAME_TO_KEY.get(name, name)


def transform_month(receipt_rows, item_rows, global_aliases):
    """Строки OLAP месяца -> структуры для guest_store.replace_month().

    Возвращает (receipts, items, aliases, guest_attrs) — см. докстринг
    replace_month. Правила:
    - guest_id = канонический телефон; если телефон пуст (исторические строки) —
      канонический номер карты, при возможности разрешённый через псевдонимы;
    - позиции (в них есть только номер карты) привязываются к гостю по точному
      ключу чека (дата, бар, номер, карта) из уровня чеков того же месяца;
    - строки без карты и телефона не попадают в базу (не программа лояльности);
    - дубли ключей суммируются (страховка от неожиданной грануляции OLAP).
    """
    receipts = {}
    guest_attrs = {}
    aliases = {}
    link = {}  # (open_date, store, order_num, canon_card) -> guest_id

    for r in receipt_rows or []:
        card_raw = str(r.get('Delivery.CustomerCardNumber') or '').strip()
        phone_raw = str(r.get('Delivery.CustomerPhone') or '').strip()
        if not card_raw and not phone_raw:
            continue
        canon_card = normalize_guest_id(card_raw)
        canon_phone = normalize_guest_id(phone_raw)
        guest_id = canon_phone or global_aliases.get(canon_card, canon_card)
        if not guest_id:
            continue
        open_date = str(r.get('OpenDate.Typed') or '')[:10]
        if not open_date:
            continue
        store = _store_key(r.get('Store.Name'))
        order_num = str(r.get('OrderNum') or '')

        key = (open_date, store, order_num, guest_id)
        rec = receipts.setdefault(
            key, {'revenue': 0.0, 'discount': 0.0, 'full_sum': 0.0})
        rec['revenue'] += float(r.get('DishDiscountSumInt') or 0)
        rec['discount'] += float(r.get('DiscountSum') or 0)
        rec['full_sum'] += float(r.get('DishSumInt') or 0)

        if canon_card:
            link[(open_date, store, order_num, canon_card)] = guest_id
            if canon_card != guest_id:
                aliases[canon_card] = guest_id

        created = str(r.get('Delivery.CustomerCreatedDateTyped') or '').strip()[:10]
        name = str(r.get('Delivery.CustomerName') or '').strip()
        a = guest_attrs.setdefault(guest_id, {
            'phone': canon_phone, 'card_number': card_raw, 'name': name,
            'min_created': created, 'max_date': open_date,
        })
        if created and (not a['min_created'] or created < a['min_created']):
            a['min_created'] = created
        if open_date >= a['max_date']:
            a['max_date'] = open_date
            if name:
                a['name'] = name
            if card_raw:
                a['card_number'] = card_raw
            if canon_phone:
                a['phone'] = canon_phone

    items = {}
    for r in item_rows or []:
        card_raw = str(r.get('Delivery.CustomerCardNumber') or '').strip()
        if not card_raw:
            continue
        canon_card = normalize_guest_id(card_raw)
        open_date = str(r.get('OpenDate.Typed') or '')[:10]
        dish = str(r.get('DishName') or '').strip()
        if not open_date or not dish:
            continue
        store = _store_key(r.get('Store.Name'))
        order_num = str(r.get('OrderNum') or '')
        guest_id = (link.get((open_date, store, order_num, canon_card))
                    or aliases.get(canon_card)
                    or global_aliases.get(canon_card)
                    or canon_card)
        key = (open_date, store, order_num, guest_id, dish)
        it = items.setdefault(key, {'amount': 0.0, 'revenue': 0.0})
        it['amount'] += float(r.get('DishAmountInt') or 0)
        it['revenue'] += float(r.get('DishDiscountSumInt') or 0)

    return receipts, items, aliases, guest_attrs


def sync_month(olap, store, ym, frozen):
    """Синхронизировать один месяц. Возвращает (receipts_count, items_count).
    Бросает RuntimeError, если iiko не ответил (месяц помечается error)."""
    date_from, date_to_excl = month_bounds(ym)
    store.mark_month(ym, 'in_progress')

    receipt_rows = olap.get_guest_receipts_month(date_from, date_to_excl)
    if receipt_rows is None:
        store.mark_month(ym, 'error')
        raise RuntimeError(f"iiko ne otvetil na zapros chekov za {ym}")
    time.sleep(PAUSE_BETWEEN_REQUESTS_SEC)

    item_rows = olap.get_guest_receipt_items_month(date_from, date_to_excl)
    if item_rows is None:
        store.mark_month(ym, 'error')
        raise RuntimeError(f"iiko ne otvetil na zapros pozitsiy za {ym}")

    receipts, items, aliases, guest_attrs = transform_month(
        receipt_rows, item_rows, store.get_aliases())
    store.replace_month(ym, receipts, items, aliases, guest_attrs, frozen=frozen)
    return len(receipts), len(items)


def _run_months(months, force):
    """Последовательный синк списка месяцев в одной сессии iiko.

    Пропускает месяцы, уже синхронизированные и замороженные (если не force).
    Прошлые месяцы замораживаются после успешного синка; текущий остаётся
    открытым для ночного ресинка.
    """
    from core.olap_reports import OlapReports
    from core.guest_store import get_store

    store = get_store()
    current_ym = date.today().strftime('%Y-%m')
    state = store.sync_state_map()

    todo = []
    for ym in months:
        st = state.get(ym)
        if (not force) and st and st['status'] == 'ok' and st['frozen']:
            continue
        todo.append(ym)

    with _SYNC_LOCK:
        _SYNC_STATE['total'] = len(todo)
        _SYNC_STATE['done'] = 0

    if not todo:
        return 0

    olap = OlapReports()
    if not olap.connect():
        raise RuntimeError("ne udalos podklyuchitsya k iiko API")
    try:
        for ym in todo:
            with _SYNC_LOCK:
                _SYNC_STATE['current_month'] = ym
            n_receipts, n_items = sync_month(
                olap, store, ym, frozen=(ym < current_ym))
            print(f"[GUEST-SYNC] {ym}: chekov {n_receipts}, pozitsiy {n_items}")
            with _SYNC_LOCK:
                _SYNC_STATE['done'] += 1
            time.sleep(PAUSE_BETWEEN_REQUESTS_SEC)
    finally:
        olap.disconnect()
    return len(todo)


def backfill_months():
    """Все месяцы от GUESTS_BACKFILL_FROM до текущего включительно."""
    from_ym = os.environ.get('GUESTS_BACKFILL_FROM', BACKFILL_FROM_DEFAULT)
    return iter_months(from_ym, date.today().strftime('%Y-%m'))


def nightly_months():
    """Текущий месяц + предыдущий в первые 2 дня нового месяца (стык)."""
    today = date.today()
    months = []
    if today.day <= 2:
        prev = (date(today.year - 1, 12, 1) if today.month == 1
                else date(today.year, today.month - 1, 1))
        months.append(prev.strftime('%Y-%m'))
    months.append(today.strftime('%Y-%m'))
    return months


def run_sync(months, force=False, tag='manual'):
    """Точка входа прогона: single-flight, прогресс, обработка ошибок.
    Возвращает True, если прогон состоялся (False — уже идёт другой)."""
    with _SYNC_LOCK:
        if _SYNC_STATE['running']:
            return False
        _SYNC_STATE.update(running=True, error=None, current_month=None,
                           started_at=datetime.now().isoformat(timespec='seconds'),
                           finished_at=None, done=0, total=0)
    started = time.time()
    try:
        n = _run_months(months, force=force)
        print(f"[GUEST-SYNC] {tag}: gotovo, mesyatsev {n}, "
              f"za {time.time() - started:.0f}s")
        return True
    except Exception as e:
        print(f"[GUEST-SYNC] {tag} oshibka: {e}")
        with _SYNC_LOCK:
            _SYNC_STATE['error'] = str(e)
        return True
    finally:
        with _SYNC_LOCK:
            _SYNC_STATE['running'] = False
            _SYNC_STATE['current_month'] = None
            _SYNC_STATE['finished_at'] = datetime.now().isoformat(timespec='seconds')


def start_background_sync(months=None, force=False, tag='manual'):
    """Запустить прогон в daemon-потоке. False, если синк уже идёт."""
    with _SYNC_LOCK:
        if _SYNC_STATE['running']:
            return False
    target_months = months if months is not None else backfill_months()
    threading.Thread(
        target=run_sync, args=(target_months,),
        kwargs={'force': force, 'tag': tag},
        name='guest-sync', daemon=True).start()
    return True


def get_sync_progress():
    """Снимок прогресса для /api/guests/sync-status."""
    with _SYNC_LOCK:
        return dict(_SYNC_STATE)


if __name__ == '__main__':
    # Ручной бэкфилл: py -3 -m core.guest_sync [--force]
    import sys
    force_flag = '--force' in sys.argv
    print(f"[GUEST-SYNC] CLI bekfill, force={force_flag}")
    run_sync(backfill_months(), force=force_flag, tag='cli')
    from core.guest_store import get_store
    print(f"[GUEST-SYNC] pokrytie: {get_store().coverage()}")
