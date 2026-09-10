"""Расход товара по складу за окно из отчёта storeOperations iiko.

Единая точка расчёта для /stocks (order-board, kitchen, bottles, expiry) и
/expiration. До 2026-09-10 каждый эндпоинт суммировал операции сам и не
проверял склад записи, поэтому расход всей сети приписывался одному бару
(S-01 в docs/technical/audits/STOCKS_AUDIT_2026-09-10.md).

Формулы (все константы именованы):

    outgoing        = Σ |amount| по записям с incoming == 'false'
                      (продажи, перемещения ИЗ бара, списания — по решению
                      владельца 2026-09-10 перемещения входят в расход бара)
    days_in_period  = WINDOW_DAYS (30), либо для «новинки» — дней с первого
                      прихода по сегодня включительно (см. ниже)
    avg_per_day     = outgoing / days_in_period

Скоуп по складу: запись считается, если её `primaryStore` равен складу бара;
для «Общая» (target_store_id = None) считаются все склады, но перемещения между
складами сети (documentType INTERNAL_TRANSFER) пропускаются целиком: товар сеть
не покинул, а его продажа в баре-получателе посчитается отдельно.

«Новинка» (укороченный знаменатель) — товар, которого в начале окна на складе
не было: первый приход внутри окна (позже date_from и не позже today), до него
в окне нет расхода, и, если известен текущий остаток, остаток на начало окна
(stock_now − incoming + outgoing) не больше OPENING_STOCK_EPS. Без остатка на
входе последняя проверка не выполняется, и под правило попадает и старый
товар, оприходованный после перерыва в наличии, — метка тогда условна.

Пропускаются (не считаются ни расходом, ни приходом): записи без product,
записи без поля incoming (неизвестно направление) — их число в stats['skipped'].
Первая дата прихода/расхода фиксируется только по записям с amount > 0 и
читаемой датой; запись с нечитаемой датой в суммы входит, но порядок событий
не меняет.

Окно запроса к iiko: dateFrom = сегодня − WINDOW_DAYS, dateTo = сегодня, обе
границы включительно, то есть 30 полных дней плюс неполный сегодняшний;
делитель — 30. Это осознанное упрощение, зафиксировано здесь и в docs/stocks.md.
"""
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, Optional

WINDOW_DAYS = 30
OPS_DATE_FMT = '%d.%m.%Y'
INTERNAL_TRANSFER = 'INTERNAL_TRANSFER'   # documentType перемещения между складами iiko
OPENING_STOCK_EPS = 1e-6                  # остаток на начало окна не больше этого = товара не было


def parse_ops_date(value) -> Optional[date]:
    """'DD.MM.YYYY' → date; пусто или мусор → None."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), OPS_DATE_FMT).date()
    except ValueError:
        return None


def period_bounds(today: date, window_days: int = WINDOW_DAYS):
    """(date_from, date_to) для запроса storeOperations: сегодня − window_days .. сегодня."""
    return today - timedelta(days=window_days), today


def format_period(date_from: date, date_to: date):
    """Границы окна в формате iiko v1 (DD.MM.YYYY)."""
    return date_from.strftime(OPS_DATE_FMT), date_to.strftime(OPS_DATE_FMT)


def is_outgoing(record: dict) -> Optional[bool]:
    """True — расход (incoming == 'false'), False — приход, None — направление неизвестно.

    Поле отсутствует или пустое → None: такую запись aggregate_consumption
    пропускает, а не гадает.
    """
    value = record.get('incoming')
    if value is None:
        return None
    if isinstance(value, bool):
        return not value
    text = str(value).strip().lower()
    if not text:
        return None
    return text != 'true'


def _amount(record: dict) -> float:
    try:
        return abs(float(record.get('amount', 0) or 0))
    except (TypeError, ValueError):
        return 0.0


def new_stats(scope: str, window_days: int = WINDOW_DAYS) -> dict:
    """Пустая статистика позиции (нет операций в окне)."""
    return {
        'outgoing': 0.0,
        'incoming': 0.0,
        'by_document_type': {},
        'first_in': None,
        'first_out': None,
        'days_in_period': window_days,
        'avg_per_day': 0.0,
        'is_new': False,
        'opening_stock': None,
        'skipped': 0,
        'scope': scope,
    }


def aggregate_consumption(operations: Iterable[dict],
                          product_ids: Optional[Iterable[str]],
                          target_store_id: Optional[str],
                          today: date,
                          window_days: int = WINDOW_DAYS,
                          stock_now: Optional[Dict[str, float]] = None) -> Dict[str, dict]:
    """Статистика расхода по товарам за окно.

    operations      — записи storeOperations (все склады сети, как отдаёт iiko)
    product_ids     — какие товары считать; None = все встреченные
    target_store_id — GUID склада бара; None = вся сеть («Общая»)
    today           — дата расчёта (конец окна)
    stock_now       — текущий остаток {product_id: amount} в том же скоупе;
                      если задан, «новинкой» считается только товар с нулевым
                      остатком на начало окна

    Возвращает {product_id: stats}, где stats — см. new_stats(); для товаров из
    product_ids без операций возвращается пустая статистика, чтобы потребителю
    не приходилось проверять наличие ключа.
    """
    scope = 'store' if target_store_id else 'network'
    wanted = set(product_ids) if product_ids is not None else None
    date_from, _ = period_bounds(today, window_days)

    stats: Dict[str, dict] = {}
    if wanted is not None:
        for pid in wanted:
            stats[pid] = new_stats(scope, window_days)

    for record in operations:
        pid = record.get('product')
        if not pid:
            continue
        if wanted is not None and pid not in wanted:
            continue
        if target_store_id and record.get('primaryStore') != target_store_id:
            continue
        doc_type = record.get('documentType') or 'UNKNOWN'
        if not target_store_id and doc_type == INTERNAL_TRANSFER:
            continue  # внутри сети перемещение не расход и не приход
        st = stats.get(pid)
        if st is None:
            st = new_stats(scope, window_days)
            stats[pid] = st
        outgoing = is_outgoing(record)
        if outgoing is None:
            st['skipped'] += 1
            continue
        amount = _amount(record)
        op_date = parse_ops_date(record.get('date')) if amount > 0 else None
        if outgoing:
            st['outgoing'] += amount
            st['by_document_type'][doc_type] = st['by_document_type'].get(doc_type, 0.0) + amount
            if op_date and (st['first_out'] is None or op_date < st['first_out']):
                st['first_out'] = op_date
        else:
            st['incoming'] += amount
            if op_date and (st['first_in'] is None or op_date < st['first_in']):
                st['first_in'] = op_date

    for pid, st in stats.items():
        first_in, first_out = st['first_in'], st['first_out']
        if stock_now is not None:
            st['opening_stock'] = float(stock_now.get(pid, 0.0) or 0.0) - st['incoming'] + st['outgoing']
        is_new = (first_in is not None
                  and date_from < first_in <= today
                  and (first_out is None or first_in <= first_out)
                  and (st['opening_stock'] is None or st['opening_stock'] <= OPENING_STOCK_EPS))
        if is_new:
            days = (today - first_in).days + 1
            st['days_in_period'] = max(1, min(window_days, days))
            st['is_new'] = True
        st['avg_per_day'] = st['outgoing'] / st['days_in_period'] if st['days_in_period'] > 0 else 0.0
    return stats
