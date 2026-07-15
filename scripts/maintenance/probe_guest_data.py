"""
Фаза 0 разведки для модуля «Аналитика гостей (CRM)» — см. docs/guests.md (план).

Read-only скрипт: ничего не пишет ни в iiko, ни в базы проекта. Меряет на
реальных данных OLAP SALES:

  1. Долю чеков с картой лояльности за месяц и заполненность поля
     Delivery.CustomerCreatedDateTyped («Дата создания клиента»).
  2. Долю расхождений CustomerPhone vs CustomerCardNumber после нормализации —
     проверка правила идентичности гостя (телефон приоритет, карта псевдоним).
  3. Объёмы данных за месяц: строк уровня чека и уровня позиций — оценка
     размера будущей guests.db и длительности бэкфилла.
  4. Самый ранний день с чеком по карте лояльности -> значение для
     GUESTS_BACKFILL_FROM (бэкфилл всей истории — решение владельца).

Запуск из корня репозитория: py -3 scripts/maintenance/probe_guest_data.py
"""

import sys
import time
from datetime import date, datetime, timedelta

import requests

sys.path.insert(0, '.')
from core.olap_reports import OlapReports  # noqa: E402

# Windows-консоль может быть не в UTF-8 — не даём скрипту падать на печати.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

OLAP_TIMEOUT = 120          # сек на один OLAP-запрос
PAUSE_BETWEEN_REQUESTS = 0.5  # сек, последовательные запросы (рекомендация iiko)

NOT_DELETED_FILTERS = {
    "DeletedWithWriteoff": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]},
    "OrderDeleted": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]},
}


def normalize_guest_id(value):
    """Нормализация идентификатора гостя — то же правило, что пойдёт в guest_store.

    Находка Фазы 0: CustomerPhone хранится с лишней ведущей 7 относительно
    CustomerCardNumber (например карта 79XXXXXXXXX, телефон 779XXXXXXXXX) —
    это один номер в двух форматах. Канонизация: если цифр >= 10, канон =
    '7' + последние 10 цифр (покрывает 8XXX..., 7XXX..., 77XXX..., 9XXX...).
    Если цифр меньше 10 (короткий код пластиковой карты) — только цифры.
    Если цифр нет вовсе — исходная строка без пробелов. Пусто -> ''.
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


def olap_post(olap, request_body):
    """Один POST к OLAP v2 с телом запроса. Возвращает list строк или None."""
    url = f"{olap.api.base_url}/v2/reports/olap"
    params = {"key": olap.token}
    try:
        response = requests.post(url, params=params, json=request_body,
                                 headers={"Content-Type": "application/json"},
                                 timeout=OLAP_TIMEOUT)
        if response.status_code == 200:
            return response.json().get('data', [])
        print(f"  [ERROR] HTTP {response.status_code}: {response.text[:300]}")
        return None
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None


def month_bounds(ym):
    """'YYYY-MM' -> (первый день месяца, первый день следующего месяца).
    Правая граница ЭКСКЛЮЗИВНАЯ (конвенция OpenDate.Typed DateRange в проекте)."""
    y, m = int(ym[:4]), int(ym[5:7])
    start = date(y, m, 1)
    end_excl = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start.isoformat(), end_excl.isoformat()


def date_range_filter(date_from, date_to_excl):
    return {
        "OpenDate.Typed": {
            "filterType": "DateRange",
            "periodType": "CUSTOM",
            "from": date_from,
            "to": date_to_excl,
        },
        **NOT_DELETED_FILTERS,
    }


def probe_receipts_month(olap, ym):
    """Уровень чеков за месяц: строки с гостевыми полями. Печатает статистику."""
    date_from, date_to_excl = month_bounds(ym)
    print(f"\n--- Чеки за {ym} (запрос уровня чека) ---")
    rows = olap_post(olap, {
        "reportType": "SALES",
        "groupByRowFields": [
            "Store.Name",
            "Delivery.CustomerCardNumber",
            "Delivery.CustomerPhone",
            "Delivery.CustomerName",
            "Delivery.CustomerCreatedDateTyped",
            "OrderNum",
            "OpenDate.Typed",
        ],
        "groupByColFields": [],
        "aggregateFields": ["DishDiscountSumInt", "DiscountSum", "DishSumInt"],
        "filters": date_range_filter(date_from, date_to_excl),
    })
    if rows is None:
        return None

    total = len(rows)
    with_guest = []
    for r in rows:
        card = (r.get('Delivery.CustomerCardNumber') or '').strip()
        phone = (r.get('Delivery.CustomerPhone') or '').strip()
        if card or phone:
            with_guest.append(r)

    n_guest_rows = len(with_guest)
    created_filled = 0
    both_present = 0
    both_equal = 0
    both_differ_examples = []
    guests = set()
    phones_seen = set()

    for r in with_guest:
        card = normalize_guest_id(r.get('Delivery.CustomerCardNumber'))
        phone = normalize_guest_id(r.get('Delivery.CustomerPhone'))
        created = (r.get('Delivery.CustomerCreatedDateTyped') or '').strip()
        guest_id = phone or card
        guests.add(guest_id)
        if phone:
            phones_seen.add(phone)
        if created:
            created_filled += 1
        if card and phone:
            both_present += 1
            if card == phone:
                both_equal += 1
            elif len(both_differ_examples) < 5:
                # маскируем середину, чтобы не светить полные номера в логах
                both_differ_examples.append(
                    (card[:3] + '***' + card[-2:], phone[:3] + '***' + phone[-2:]))

    def pct(x, base):
        return f"{(100.0 * x / base):.1f}%" if base else "n/a"

    print(f"  Всего строк (чеков): {total}")
    print(f"  С картой лояльности: {n_guest_rows} ({pct(n_guest_rows, total)})")
    print(f"  Уникальных гостей за месяц: {len(guests)}")
    print(f"  Дата создания клиента заполнена: {created_filled} из {n_guest_rows} "
          f"({pct(created_filled, n_guest_rows)})")
    print(f"  Оба идентификатора в строке: {both_present}; "
          f"совпадают после нормализации: {both_equal} ({pct(both_equal, both_present)})")
    if both_differ_examples:
        print(f"  Примеры расхождений (карта vs телефон): {both_differ_examples}")
    return {
        'ym': ym, 'rows': total, 'guest_rows': n_guest_rows,
        'unique_guests': len(guests), 'created_filled': created_filled,
        'both_present': both_present, 'both_equal': both_equal,
    }


def probe_items_month(olap, ym):
    """Уровень позиций за месяц: только объём строк (оценка размера БД)."""
    date_from, date_to_excl = month_bounds(ym)
    print(f"\n--- Позиции чеков за {ym} (запрос уровня позиции) ---")
    t0 = time.time()
    rows = olap_post(olap, {
        "reportType": "SALES",
        "groupByRowFields": [
            "Store.Name",
            "Delivery.CustomerCardNumber",
            "OrderNum",
            "OpenDate.Typed",
            "DishName",
        ],
        "groupByColFields": [],
        "aggregateFields": ["DishAmountInt", "DishDiscountSumInt"],
        "filters": date_range_filter(date_from, date_to_excl),
    })
    if rows is None:
        return None
    elapsed = time.time() - t0
    n_with_card = sum(1 for r in rows
                      if (r.get('Delivery.CustomerCardNumber') or '').strip())
    print(f"  Всего строк позиций: {len(rows)}; с картой: {n_with_card}; "
          f"время запроса: {elapsed:.1f} c")
    return {'ym': ym, 'item_rows': len(rows), 'item_rows_with_card': n_with_card,
            'elapsed_sec': round(elapsed, 1)}


def find_earliest_loyalty_check(olap, year_from=2016):
    """Самый ранний день с чеком по карте: перебор лет от старых к новым.

    Фильтр по Delivery.CustomerCreatedDateTyped (широкий диапазон) оставляет
    только строки с опознанным гостем; группировка по OpenDate.Typed даёт дни.
    """
    print("\n--- Поиск самого раннего чека с картой лояльности ---")
    current_year = date.today().year
    for year in range(year_from, current_year + 1):
        rows = olap_post(olap, {
            "reportType": "SALES",
            "groupByRowFields": ["OpenDate.Typed"],
            "groupByColFields": [],
            "aggregateFields": ["UniqOrderId.OrdersCount"],
            "filters": {
                **date_range_filter(f"{year}-01-01", f"{year + 1}-01-01"),
                "Delivery.CustomerCreatedDateTyped": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": "2000-01-01",
                    "to": "2100-01-01",
                },
            },
        })
        time.sleep(PAUSE_BETWEEN_REQUESTS)
        if rows:
            days = sorted((r.get('OpenDate.Typed') or '') for r in rows)
            days = [d for d in days if d]
            if days:
                print(f"  {year}: есть чеки с гостями, самый ранний день: {days[0]}")
                return days[0]
        print(f"  {year}: чеков с гостями нет")
    return None


def probe_min_created_date(olap):
    """MIN даты создания клиента среди гостей, активных за последние 12 месяцев."""
    print("\n--- Минимальная «Дата создания клиента» (гости за последние 12 мес) ---")
    today = date.today()
    year_ago = (today - timedelta(days=365)).isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    rows = olap_post(olap, {
        "reportType": "SALES",
        "groupByRowFields": ["Delivery.CustomerCreatedDateTyped"],
        "groupByColFields": [],
        "aggregateFields": ["UniqOrderId.OrdersCount"],
        "filters": date_range_filter(year_ago, tomorrow),
    })
    if not rows:
        return None
    dates = sorted((r.get('Delivery.CustomerCreatedDateTyped') or '').strip()
                   for r in rows)
    dates = [d for d in dates if d]
    if not dates:
        print("  Ни одной заполненной даты создания не найдено")
        return None
    print(f"  Всего уникальных дат создания: {len(dates)}; "
          f"минимальная: {dates[0]}; максимальная: {dates[-1]}")
    return dates[0]


def main():
    print("=" * 70)
    print("Фаза 0: разведка данных для модуля «Аналитика гостей (CRM)»")
    print(f"Запуск: {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70)

    olap = OlapReports()
    if not olap.connect():
        print("[ERROR] Не удалось подключиться к iiko API (проверьте .env)")
        return 1
    print("[OK] Подключение к iiko установлено")

    try:
        # 1-2. Свежий полный месяц и месяц годовой давности
        for ym in ("2026-06", "2025-06"):
            probe_receipts_month(olap, ym)
            time.sleep(PAUSE_BETWEEN_REQUESTS)

        # 3. Объём уровня позиций за свежий месяц
        probe_items_month(olap, "2026-06")
        time.sleep(PAUSE_BETWEEN_REQUESTS)

        # 4. Граница истории
        earliest_check = find_earliest_loyalty_check(olap)
        min_created = probe_min_created_date(olap)

        print("\n" + "=" * 70)
        print("ИТОГ")
        if earliest_check:
            print(f"  Самый ранний чек с гостем: {earliest_check}")
            print(f"  Рекомендация GUESTS_BACKFILL_FROM: {earliest_check[:7]}")
        if min_created:
            print(f"  Самая ранняя дата создания клиента: {min_created}")
        print("=" * 70)
        return 0
    finally:
        olap.disconnect()


if __name__ == "__main__":
    sys.exit(main())
