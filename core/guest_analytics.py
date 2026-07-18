"""Расчётный слой модуля «Аналитика гостей (CRM)» — чистые функции над guests.db.

Все метрики считаются SQL/Python по локальной витрине (core/guest_store.py),
обращений к iiko здесь нет. Каждая формула детерминирована и продублирована
пользователю в UI (тултипы + блок «Как считается», static/js/guests/formulas.js)
и в docs/guests.md.

Временная логика ТЗ (обязательная для всех разделов):
- Primary Period: неделя (ISO пн-вс) / календарный месяц / квартал / год;
- YTD: с 1 января года даты окончания периода по конец периода;
- Lifetime: вся загруженная история (покрытие витрины — в meta каждого ответа).

Зафиксированные ТЗ правила:
- когорты жизненного цикла — от месяца РЕГИСТРАЦИИ, Lifetime-логика;
- retention — от месяца ПЕРВОЙ ПОКУПКИ, окна 30/60/90/180/365 дней;
- RFM — скользящее окно 12 месяцев (365 дней) на дату среза, НЕ Lifetime;
- статусы активности — по последнему визиту на дату окончания периода:
  Active <= 30 дн, Sleeping 31-90, At Risk 91-180, Lost > 180.

Определения (те же, что в /discounts и месячной витрине):
- заказ (чек) = строка receipts (ключ дата+бар+номер чека+гость);
- визит = уникальная пара (гость, дата) — OpenDate.Typed времени не содержит;
- выручка = DishDiscountSumInt (что фактически заплатил гость).

Округления: деньги — целые рубли (round), проценты — 1 знак, дни/частота —
1 знак. Недозревшие ячейки когорт (конец месяца когорты + окно > даты среза)
отдаются как None и показываются в UI прочерком.

Документация: docs/guests.md
"""

import calendar
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta

from core.guest_store import get_store
from core.venues_config import PHYSICAL_VENUES, VENUES

# --- Константы метрик (все пороги объяснены, магических чисел в коде нет) ---

# Статусы активности базы (ТЗ §3), дни с последнего визита на дату среза.
ACTIVITY_SEGMENTS = [
    ('active', 0, 30),       # визит за последние 30 дней
    ('sleeping', 31, 90),
    ('at_risk', 91, 180),
    ('lost', 181, None),     # 180+ дней
]

# Окна возврата когорт (ТЗ §2 retention-слой и §5), дни от первой покупки.
RETENTION_WINDOWS = [30, 60, 90, 180, 365]

# Сегменты частоты визитов за период (ТЗ §4).
FREQUENCY_SEGMENTS = [('1', 1, 1), ('2-3', 2, 3), ('4-8', 4, 8), ('9+', 9, None)]

# RFM (ТЗ §7): скользящее окно 12 месяцев = 365 дней, включая дату среза.
RFM_WINDOW_DAYS = 365
# R-пороги (дней с последнего визита) — те же, что в /discounts (routes/analysis.py).
RFM_R_THRESHOLDS = (7, 14, 30, 60)          # R5 <=7, R4 <=14, R3 <=30, R2 <=60, R1 >60
# F-пороги в визитах за окно 12 мес (52 недели). Утверждено владельцем 2026-07-18
# в человеческих якорях: «постоянный» = 5-7 визитов в неделю (5*52=260),
# «частый» = 2-3 визита в неделю (2*52=104); нижние ступени — «раз в неделю»
# (52) и «раз в месяц» (12).
RFM_F_THRESHOLDS = (260, 104, 52, 12)       # F5 >=260, F4 >=104, F3 >=52, F2 >=12, F1 <12

# Порог «реактивированного» гостя в динамике базы (ТЗ §13): визит после паузы
# больше порога Active (симметрия с §3).
REACTIVATION_GAP_DAYS = 30

# Витрина считает «регистрацию» по дате создания клиента в iiko; если она
# недоступна у большинства гостей — модуль переходит в fallback-режим ТЗ
# (регистрация = первая покупка, конверсия скрывается).
FALLBACK_MODE_THRESHOLD = 0.5

MONTH_NAMES = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
               'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
MONTH_NAMES_NOM = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                   'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']


# ---------------------------------------------------------------- периоды

def _parse_date(s, default=None):
    try:
        return datetime.strptime(str(s)[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return default


def resolve_period(period_type='month', anchor=None):
    """Границы Primary Period по типу и якорной дате (любой дате внутри периода).

    Возвращает dict: type, p_start, p_end (date), prev_start, prev_end
    (предыдущий период того же типа — для дельт §3), label (подпись в UI).
    """
    a = _parse_date(anchor, date.today())
    if period_type == 'week':
        p_start = a - timedelta(days=a.isoweekday() - 1)
        p_end = p_start + timedelta(days=6)
        prev_end = p_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=6)
        label = (f"Неделя {p_start.isocalendar()[1]}: "
                 f"{p_start.strftime('%d.%m')}-{p_end.strftime('%d.%m.%Y')}")
    elif period_type == 'quarter':
        q = (a.month - 1) // 3
        p_start = date(a.year, q * 3 + 1, 1)
        end_month = q * 3 + 3
        p_end = date(a.year, end_month, calendar.monthrange(a.year, end_month)[1])
        prev_end = p_start - timedelta(days=1)
        pq = (prev_end.month - 1) // 3
        prev_start = date(prev_end.year, pq * 3 + 1, 1)
        label = f"{['I', 'II', 'III', 'IV'][q]} квартал {a.year}"
    elif period_type == 'year':
        p_start, p_end = date(a.year, 1, 1), date(a.year, 12, 31)
        prev_start, prev_end = date(a.year - 1, 1, 1), date(a.year - 1, 12, 31)
        label = str(a.year)
    else:  # month (дефолт ТЗ)
        period_type = 'month'
        p_start = a.replace(day=1)
        p_end = date(a.year, a.month, calendar.monthrange(a.year, a.month)[1])
        prev_end = p_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        label = f"{MONTH_NAMES_NOM[a.month - 1]} {a.year}"
    return {'type': period_type, 'p_start': p_start, 'p_end': p_end,
            'prev_start': prev_start, 'prev_end': prev_end, 'label': label}


def build_meta(store, period):
    """meta каждого ответа: границы срезов, покрытие витрины, режим регистраций."""
    cov = store.coverage()
    today = date.today()
    p_end = period['p_end']
    asof = min(p_end, today)
    with store.conn() as conn:
        total = conn.execute("SELECT COUNT(*) n FROM guests").fetchone()['n']
        fb = conn.execute("SELECT COUNT(*) n FROM guests "
                          "WHERE registration_source='first_order'").fetchone()['n']
    fallback_share = round(fb / total, 4) if total else 0.0
    return {
        'period_type': period['type'],
        'period_label': period['label'],
        'p_start': period['p_start'].isoformat(),
        'p_end': p_end.isoformat(),
        'asof': asof.isoformat(),
        'ytd_start': date(p_end.year, 1, 1).isoformat(),
        'coverage_from': cov['date_from'],
        'coverage_to': cov['date_to'],
        'last_synced_at': cov['last_synced_at'],
        'fallback_share': fallback_share,
        'fallback_mode': fallback_share > FALLBACK_MODE_THRESHOLD,
    }


# ---------------------------------------------------------------- загрузчики

def _load_guests(conn):
    """Все гости: список dict-строк таблицы guests."""
    return [dict(r) for r in conn.execute(
        "SELECT guest_id, name, phone, card_number, registration_date, "
        "registration_source, first_order_date, first_order_store, "
        "last_visit_date FROM guests")]


def _load_visits(conn):
    """{guest_id: [даты визитов по возрастанию]} за всю историю."""
    visits = {}
    for r in conn.execute(
            "SELECT guest_id, open_date FROM receipts "
            "GROUP BY guest_id, open_date ORDER BY guest_id, open_date"):
        visits.setdefault(r['guest_id'], []).append(r['open_date'])
    return visits


def _load_guest_totals(conn):
    """{guest_id: {'orders': n, 'revenue': x}} за всю историю."""
    return {r['guest_id']: {'orders': r['orders'], 'revenue': r['revenue'] or 0.0}
            for r in conn.execute(
                "SELECT guest_id, COUNT(*) orders, SUM(revenue) revenue "
                "FROM receipts GROUP BY guest_id")}


def _visits_between(dates_list, d_from, d_to):
    """Число визитов в [d_from..d_to] (ISO-строки) по отсортированному списку."""
    return bisect_right(dates_list, d_to) - bisect_left(dates_list, d_from)


def _last_visit_at(dates_list, d):
    """Последний визит не позже d (ISO-строка) или None."""
    idx = bisect_right(dates_list, d)
    return dates_list[idx - 1] if idx else None


def _days_between(d1_iso, d2_iso):
    return (_parse_date(d2_iso) - _parse_date(d1_iso)).days


def _month_end_iso(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return date(y, m, calendar.monthrange(y, m)[1]).isoformat()


def _registration_basis(meta):
    """Базис «регистрации»: дата создания из iiko или первая покупка (fallback)."""
    return 'first_order' if meta['fallback_mode'] else 'iiko'


def _reg_date(g, basis):
    """Дата регистрации гостя в выбранном базисе (может быть None)."""
    if basis == 'iiko':
        if g['registration_source'] == 'iiko':
            return g['registration_date']
        return None
    return g['first_order_date']


def _pct(part, total, digits=1):
    return round(100.0 * part / total, digits) if total else 0.0


# ---------------------------------------------------------------- §1 Рост базы

def base_growth(store, period, meta):
    """Регистрации, первые заказы, конверсия, время до первого заказа (P + YTD).

    Ограничение источника (принято владельцем): OLAP видит только гостей с >=1
    чеком за историю, поэтому «регистрации» — по купившим хоть раз; свежие
    периоды дорастают задним числом. В fallback-режиме конверсия и время до
    первого заказа не определены (регистрация = первая покупка) и отдаются None.
    """
    p_start, p_end = period['p_start'].isoformat(), period['p_end'].isoformat()
    ytd_start = meta['ytd_start']
    fallback = meta['fallback_mode']

    def slice_metrics(conn, d_from, d_to):
        regs = first = conv = avg_days = None
        first = conn.execute(
            "SELECT COUNT(*) n FROM guests WHERE first_order_date >= ? "
            "AND first_order_date <= ?", (d_from, d_to)).fetchone()['n']
        if not fallback:
            regs = conn.execute(
                "SELECT COUNT(*) n FROM guests WHERE registration_source='iiko' "
                "AND registration_date >= ? AND registration_date <= ?",
                (d_from, d_to)).fetchone()['n']
            # MAX(0, ...): чек последнего часа смены попадает в учётный день
            # НАКАНУНЕ календарной даты создания карты (бар работает за полночь),
            # отсюда формальные «-1 день» — считаем их нулём.
            row = conn.execute(
                """
                SELECT COUNT(*) converted,
                       AVG(MAX(0, julianday(first_order_date)
                                  - julianday(registration_date))) days
                FROM guests
                WHERE registration_source='iiko'
                  AND registration_date >= ? AND registration_date <= ?
                  AND first_order_date <= ?
                """, (d_from, d_to, d_to)).fetchone()
            conv = _pct(row['converted'], regs) if regs else None
            avg_days = round(row['days'], 1) if row['days'] is not None else None
        return {'registrations': regs, 'first_orders': first,
                'conversion_pct': conv, 'avg_days_to_first_order': avg_days}

    with store.conn() as conn:
        out = {
            'period': slice_metrics(conn, p_start, p_end),
            'ytd': slice_metrics(conn, ytd_start, p_end),
            'lifetime': {
                'base_size': conn.execute("SELECT COUNT(*) n FROM guests").fetchone()['n'],
            },
        }
    return out


# ---------------------------------------------------------------- §3 Активность

def _activity_counts(guests, visits, asof_iso):
    """Число гостей по статусам на дату среза (население: первый заказ <= срез)."""
    counts = {name: 0 for name, _, _ in ACTIVITY_SEGMENTS}
    for g in guests:
        if not g['first_order_date'] or g['first_order_date'] > asof_iso:
            continue
        lv = _last_visit_at(visits.get(g['guest_id'], []), asof_iso)
        if lv is None:
            continue
        days = _days_between(lv, asof_iso)
        for name, lo, hi in ACTIVITY_SEGMENTS:
            if days >= lo and (hi is None or days <= hi):
                counts[name] += 1
                break
    return counts


def activity(store, period, meta):
    """Статусы базы на дату среза + сравнение с предыдущим периодом (ТЗ §3)."""
    today = date.today()
    asof = min(period['p_end'], today).isoformat()
    prev_asof = min(period['prev_end'], today).isoformat()
    with store.conn() as conn:
        guests = _load_guests(conn)
        visits = _load_visits(conn)
    cur = _activity_counts(guests, visits, asof)
    prev = _activity_counts(guests, visits, prev_asof)
    total = sum(cur.values())
    segments = []
    for name, lo, hi in ACTIVITY_SEGMENTS:
        segments.append({
            'segment': name,
            'days_from': lo, 'days_to': hi,
            'count': cur[name],
            'share_pct': _pct(cur[name], total),
            'prev_count': prev[name],
            'delta': cur[name] - prev[name],
        })
    return {'asof': asof, 'prev_asof': prev_asof,
            'total_with_orders': total, 'segments': segments}


# ---------------------------------------------------------------- §4 Частота

def frequency(store, period, meta):
    """Частота визитов за Primary Period (ТЗ §4): сегменты и средняя частота."""
    p_start, p_end = period['p_start'].isoformat(), period['p_end'].isoformat()
    ytd_start = meta['ytd_start']

    def calc(conn, d_from, d_to):
        rows = conn.execute(
            "SELECT guest_id, COUNT(DISTINCT open_date) v FROM receipts "
            "WHERE open_date >= ? AND open_date <= ? GROUP BY guest_id",
            (d_from, d_to)).fetchall()
        seg_counts = {label: 0 for label, _, _ in FREQUENCY_SEGMENTS}
        total_visits = 0
        for r in rows:
            total_visits += r['v']
            for label, lo, hi in FREQUENCY_SEGMENTS:
                if r['v'] >= lo and (hi is None or r['v'] <= hi):
                    seg_counts[label] += 1
                    break
        n_guests = len(rows)
        return {
            'guests_with_visits': n_guests,
            'total_visits': total_visits,
            'avg_visits_per_guest': round(total_visits / n_guests, 1) if n_guests else 0.0,
            'segments': [
                {'segment': label, 'count': seg_counts[label],
                 'share_pct': _pct(seg_counts[label], n_guests)}
                for label, _, _ in FREQUENCY_SEGMENTS],
        }

    with store.conn() as conn:
        return {'period': calc(conn, p_start, p_end),
                'ytd': calc(conn, ytd_start, p_end)}


# ------------------------------------------------- §2/§5 Когорты и retention

def lifecycle_cohorts(store, period, meta, months_limit=24):
    """Когорты жизненного цикла (ТЗ §2): когорта = месяц регистрации.

    Lifetime-воронка внутри когорты: % с 1-м / 2-м / 5-м заказом (по числу
    чеков за всю жизнь), % активных на дату среза. В fallback-режиме базис
    автоматически «первая покупка» (совпадает с §5) — помечено в meta.
    """
    basis = _registration_basis(meta)
    asof = meta['asof']
    active_from = (_parse_date(asof) - timedelta(days=ACTIVITY_SEGMENTS[0][2])).isoformat()
    with store.conn() as conn:
        guests = _load_guests(conn)
        totals = _load_guest_totals(conn)
    cohorts = {}
    for g in guests:
        reg = _reg_date(g, basis)
        # Когорты будущее не содержат: гость существует на дату среза
        if not reg or reg > asof:
            continue
        ym = reg[:7]
        c = cohorts.setdefault(ym, {'n': 0, 'order1': 0, 'order2': 0,
                                    'order5': 0, 'active': 0})
        c['n'] += 1
        orders = totals.get(g['guest_id'], {}).get('orders', 0)
        if g['first_order_date']:
            c['order1'] += 1
        if orders >= 2:
            c['order2'] += 1
        if orders >= 5:
            c['order5'] += 1
        if g['last_visit_date'] and g['last_visit_date'] >= active_from:
            c['active'] += 1
    rows = []
    for ym in sorted(cohorts.keys(), reverse=True)[:months_limit]:
        c = cohorts[ym]
        rows.append({
            'cohort': ym, 'guests': c['n'],
            'order1_pct': _pct(c['order1'], c['n']),
            'order2_pct': _pct(c['order2'], c['n']),
            'order5_pct': _pct(c['order5'], c['n']),
            'active_pct': _pct(c['active'], c['n']),
        })
    return {'basis': basis, 'cohorts': rows}


def cohort_retention(store, period, meta, basis='first_order', months_limit=24):
    """Возвраты когорт (ТЗ §5, а с basis='registration' — retention-слой §2).

    Когорта = месяц первой покупки (или регистрации). Возврат = визит в окне
    (первая покупка, первая покупка + N дней], N из RETENTION_WINDOWS.
    Ячейка зрелая, только если конец месяца когорты + N <= дата среза; иначе
    None (в UI прочерк) — недозревшие когорты не занижают проценты.
    """
    if basis == 'registration':
        basis = _registration_basis(meta)
    asof = meta['asof']
    with store.conn() as conn:
        guests = _load_guests(conn)
        visits = _load_visits(conn)
    cohorts = {}
    for g in guests:
        anchor = _reg_date(g, basis) if basis != 'first_order' else g['first_order_date']
        first = g['first_order_date']
        if not anchor or not first or anchor > asof:
            continue
        ym = anchor[:7]
        c = cohorts.setdefault(ym, {'n': 0, 'returned': {w: 0 for w in RETENTION_WINDOWS}})
        c['n'] += 1
        vd = visits.get(g['guest_id'], [])
        first_d = _parse_date(first)
        for w in RETENTION_WINDOWS:
            win_end = (first_d + timedelta(days=w)).isoformat()
            # визит СТРОГО после первой покупки и не позже first + w
            if _visits_between(vd, first, win_end) - _visits_between(vd, first, first) > 0:
                c['returned'][w] += 1
    rows = []
    for ym in sorted(cohorts.keys(), reverse=True)[:months_limit]:
        c = cohorts[ym]
        month_end = _parse_date(_month_end_iso(ym))
        cells = {}
        for w in RETENTION_WINDOWS:
            matured = (month_end + timedelta(days=w)).isoformat() <= asof
            cells[str(w)] = _pct(c['returned'][w], c['n']) if matured else None
        rows.append({'cohort': ym, 'guests': c['n'], 'returned_pct': cells})
    return {'basis': basis, 'windows': RETENTION_WINDOWS, 'cohorts': rows}


# ---------------------------------------------------------------- §6 Доходы

def cohort_revenue(store, period, meta, basis='registration', months_limit=24):
    """Когортные доходы (ТЗ §6): накопительные выручка/заказы/LTV по когортам."""
    if basis == 'registration':
        eff_basis = _registration_basis(meta)
    else:
        eff_basis = 'first_order'
    asof = meta['asof']
    with store.conn() as conn:
        guests = _load_guests(conn)
        totals = _load_guest_totals(conn)
    cohorts = {}
    for g in guests:
        anchor = (_reg_date(g, eff_basis) if eff_basis != 'first_order'
                  else g['first_order_date'])
        if not anchor or anchor > asof:
            continue
        ym = anchor[:7]
        t = totals.get(g['guest_id'], {'orders': 0, 'revenue': 0.0})
        c = cohorts.setdefault(ym, {'n': 0, 'revenue': 0.0, 'orders': 0})
        c['n'] += 1
        c['revenue'] += t['revenue']
        c['orders'] += t['orders']
    rows = []
    for ym in sorted(cohorts.keys(), reverse=True)[:months_limit]:
        c = cohorts[ym]
        rows.append({
            'cohort': ym, 'guests': c['n'],
            'revenue': round(c['revenue']),
            'orders': c['orders'],
            'ltv': round(c['revenue'] / c['n']) if c['n'] else 0,
        })
    return {'basis': eff_basis, 'cohorts': rows}


# ---------------------------------------------------------------- §7 RFM

def _rfm_r_code(days):
    t = RFM_R_THRESHOLDS
    if days <= t[0]:
        return 5
    if days <= t[1]:
        return 4
    if days <= t[2]:
        return 3
    if days <= t[3]:
        return 2
    return 1


def _rfm_f_code(visits_in_window):
    t = RFM_F_THRESHOLDS
    if visits_in_window >= t[0]:
        return 5
    if visits_in_window >= t[1]:
        return 4
    if visits_in_window >= t[2]:
        return 3
    if visits_in_window >= t[3]:
        return 2
    return 1


def _rfm_segment(r_code, f_code, visits_in_window):
    """Именованный сегмент — та же модель, что /discounts (get_rfm_segment)."""
    if r_code == 5 and f_code >= 4:
        return 'CHAMPIONS'
    if r_code == 1 and f_code >= 3:
        return 'CHURNED'
    if r_code in (2, 3) and f_code >= 3:
        return 'AT_RISK'
    if r_code == 5 and visits_in_window == 1:
        return 'NEW'
    if r_code in (4, 5):
        return 'LOYAL'
    if f_code in (1, 2):
        return 'POTENTIAL'
    return 'LOYAL'


def rfm(store, period, meta, include_guests=True):
    """RFM-сегментация (ТЗ §7) на дату среза, окно 12 месяцев (365 дней).

    Население: гости с >=1 визитом в окне (p_end-364 .. p_end включительно).
    R = дней с последнего визита; F = визитов в окне; M = выручка окна.
    """
    asof = meta['asof']
    win_start = (_parse_date(asof) - timedelta(days=RFM_WINDOW_DAYS - 1)).isoformat()
    with store.conn() as conn:
        rows = conn.execute(
            """
            SELECT r.guest_id, COUNT(DISTINCT r.open_date) f,
                   MAX(r.open_date) last_visit, SUM(r.revenue) m,
                   g.name, g.phone, g.card_number
            FROM receipts r JOIN guests g ON g.guest_id = r.guest_id
            WHERE r.open_date >= ? AND r.open_date <= ?
            GROUP BY r.guest_id
            """, (win_start, asof)).fetchall()
    seg_agg = {}
    guest_rows = []
    for r in rows:
        rec_days = _days_between(r['last_visit'], asof)
        r_code = _rfm_r_code(rec_days)
        f_code = _rfm_f_code(r['f'])
        seg = _rfm_segment(r_code, f_code, r['f'])
        a = seg_agg.setdefault(seg, {'count': 0, 'revenue': 0.0})
        a['count'] += 1
        a['revenue'] += r['m'] or 0.0
        if include_guests:
            guest_rows.append({
                'guest_id': r['guest_id'], 'name': r['name'],
                'phone': r['phone'], 'card_number': r['card_number'],
                'recency_days': rec_days, 'frequency': r['f'],
                'monetary': round(r['m'] or 0),
                'r': r_code, 'f': f_code, 'segment': seg,
            })
    total = len(rows)
    segments = [
        {'segment': s, 'count': a['count'], 'share_pct': _pct(a['count'], total),
         'revenue': round(a['revenue'])}
        for s, a in sorted(seg_agg.items(), key=lambda kv: -kv[1]['count'])]
    guest_rows.sort(key=lambda g: -g['monetary'])
    out = {'asof': asof, 'window_start': win_start, 'window_days': RFM_WINDOW_DAYS,
           'total_guests': total, 'segments': segments,
           'r_thresholds': list(RFM_R_THRESHOLDS),
           'f_thresholds': list(RFM_F_THRESHOLDS)}
    if include_guests:
        out['guests'] = guest_rows
    return out


# ---------------------------------------------------------------- §8 LTV

def ltv(store, period, meta):
    """LTV (ТЗ §8): средний Lifetime, YTD-вариант, по точкам (по когортам — §6)."""
    p_end = period['p_end'].isoformat()
    ytd_start = meta['ytd_start']
    with store.conn() as conn:
        life = conn.execute(
            "SELECT COUNT(DISTINCT guest_id) n, SUM(revenue) rev FROM receipts"
        ).fetchone()
        ytd_row = conn.execute(
            "SELECT COUNT(DISTINCT guest_id) n, SUM(revenue) rev FROM receipts "
            "WHERE open_date >= ? AND open_date <= ?", (ytd_start, p_end)).fetchone()
        by_venue = conn.execute(
            """
            SELECT g.first_order_store store, COUNT(*) guests, SUM(t.rev) revenue
            FROM guests g JOIN (
                SELECT guest_id, SUM(revenue) rev FROM receipts GROUP BY guest_id
            ) t ON t.guest_id = g.guest_id
            GROUP BY g.first_order_store ORDER BY revenue DESC
            """).fetchall()
    venues_out = []
    for r in by_venue:
        venues_out.append({
            'store': r['store'],
            'store_name': VENUES.get(r['store'], {}).get('name', r['store']),
            'guests': r['guests'],
            'ltv': round((r['revenue'] or 0) / r['guests']) if r['guests'] else 0,
        })
    return {
        'lifetime': {
            'guests': life['n'],
            'revenue': round(life['rev'] or 0),
            'avg_ltv': round((life['rev'] or 0) / life['n']) if life['n'] else 0,
        },
        'ytd': {
            'guests': ytd_row['n'],
            'revenue': round(ytd_row['rev'] or 0),
            'avg_revenue_per_guest': (round((ytd_row['rev'] or 0) / ytd_row['n'])
                                      if ytd_row['n'] else 0),
        },
        'by_venue': venues_out,
    }


# ---------------------------------------------------------------- §13 Динамика

def base_dynamics(store, period, meta, months=24):
    """Динамика базы по месяцам (ТЗ §13).

    active_start(M) = визит в [начало M - 30 дн, начало M);
    new(M) = первая покупка в M;
    reactivated(M) = визит в M при первой покупке до M и паузе > 30 дней
    на начало месяца; active_end(M) = визит в [конец M - 30 дн, конец M];
    churned(M) = active_start + new + reactivated - active_end (остаточный член
    баланса — прямые определения см. docs/guests.md).
    """
    with store.conn() as conn:
        guests = _load_guests(conn)
        visits = _load_visits(conn)
    end_anchor = min(period['p_end'], date.today())
    ym_list = []
    y, m = end_anchor.year, end_anchor.month
    for _ in range(months):
        ym_list.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    ym_list.reverse()

    rows = []
    gap = timedelta(days=REACTIVATION_GAP_DAYS)
    for ym in ym_list:
        m_start = _parse_date(f"{ym}-01")
        m_end = _parse_date(_month_end_iso(ym))
        ws_from = (m_start - gap).isoformat()
        ws_to_excl = m_start.isoformat()
        we_from = (m_end - gap).isoformat()
        we_to = m_end.isoformat()
        n_start = n_new = n_react = n_end = 0
        for g in guests:
            vd = visits.get(g['guest_id'], [])
            if not vd:
                continue
            if _visits_between(vd, ws_from, ws_to_excl) - _visits_between(vd, ws_to_excl, ws_to_excl) > 0:
                n_start += 1
            fo = g['first_order_date'] or ''
            if m_start.isoformat() <= fo <= we_to:
                n_new += 1
            elif fo and fo < m_start.isoformat():
                if _visits_between(vd, m_start.isoformat(), we_to) > 0:
                    lv_before = _last_visit_at(vd, (m_start - timedelta(days=1)).isoformat())
                    if lv_before and _parse_date(lv_before) < m_start - gap:
                        n_react += 1
            if _visits_between(vd, we_from, we_to) > 0:
                n_end += 1
        rows.append({
            'month': ym,
            'active_start': n_start,
            'new': n_new,
            'reactivated': n_react,
            'active_end': n_end,
            'churned': n_start + n_new + n_react - n_end,
        })
    return {'months': rows, 'gap_days': REACTIVATION_GAP_DAYS}


# ---------------------------------------------------------------- §9 Товары

def products(store, period, meta, mode='top', limit=30):
    """Товарные отчёты (ТЗ §9) по позициям чеков гостей программы лояльности."""
    p_start, p_end = period['p_start'].isoformat(), period['p_end'].isoformat()
    with store.conn() as conn:
        if mode == 'top':
            rows = conn.execute(
                """
                SELECT dish_name, ROUND(SUM(amount), 1) amount, SUM(revenue) revenue,
                       COUNT(DISTINCT guest_id) guests
                FROM receipt_items WHERE open_date >= ? AND open_date <= ?
                GROUP BY dish_name ORDER BY SUM(revenue) DESC LIMIT ?
                """, (p_start, p_end, limit)).fetchall()
        elif mode == 'first':
            # Первые покупки: позиции чеков в день первого заказа гостей,
            # чей первый заказ попал в период.
            rows = conn.execute(
                """
                SELECT i.dish_name, ROUND(SUM(i.amount), 1) amount,
                       SUM(i.revenue) revenue, COUNT(DISTINCT i.guest_id) guests
                FROM receipt_items i
                JOIN guests g ON g.guest_id = i.guest_id
                             AND i.open_date = g.first_order_date
                WHERE g.first_order_date >= ? AND g.first_order_date <= ?
                GROUP BY i.dish_name ORDER BY COUNT(DISTINCT i.guest_id) DESC
                LIMIT ?
                """, (p_start, p_end, limit)).fetchall()
        elif mode == 'repeat':
            # Повторные покупки: позиции чеков после дня первого заказа.
            rows = conn.execute(
                """
                SELECT i.dish_name, ROUND(SUM(i.amount), 1) amount,
                       SUM(i.revenue) revenue, COUNT(DISTINCT i.guest_id) guests
                FROM receipt_items i
                JOIN guests g ON g.guest_id = i.guest_id
                WHERE i.open_date > g.first_order_date
                  AND i.open_date >= ? AND i.open_date <= ?
                GROUP BY i.dish_name ORDER BY SUM(i.revenue) DESC LIMIT ?
                """, (p_start, p_end, limit)).fetchall()
        else:  # trend: динамика топ-10 товаров за 12 месяцев к концу периода
            end_d = period['p_end']
            start_d = date(end_d.year - 1, end_d.month, 1) + timedelta(days=0)
            top = [r['dish_name'] for r in conn.execute(
                """
                SELECT dish_name FROM receipt_items
                WHERE open_date >= ? AND open_date <= ?
                GROUP BY dish_name ORDER BY SUM(revenue) DESC LIMIT 10
                """, (start_d.isoformat(), p_end)).fetchall()]
            if not top:
                return {'mode': 'trend', 'months': [], 'series': []}
            placeholders = ','.join('?' * len(top))
            data = conn.execute(
                f"""
                SELECT substr(open_date, 1, 7) ym, dish_name,
                       ROUND(SUM(amount), 1) amount
                FROM receipt_items
                WHERE open_date >= ? AND open_date <= ?
                  AND dish_name IN ({placeholders})
                GROUP BY ym, dish_name ORDER BY ym
                """, [start_d.isoformat(), p_end] + top).fetchall()
            months_axis = sorted({r['ym'] for r in data})
            series = {d: {ym: 0 for ym in months_axis} for d in top}
            for r in data:
                series[r['dish_name']][r['ym']] = r['amount']
            return {'mode': 'trend', 'months': months_axis,
                    'series': [{'dish_name': d,
                                'points': [series[d][ym] for ym in months_axis]}
                               for d in top]}
    return {'mode': mode, 'items': [
        {'dish_name': r['dish_name'], 'amount': r['amount'],
         'revenue': round(r['revenue'] or 0), 'guests': r['guests']}
        for r in rows]}


# ---------------------------------------------------------------- §10 Пары

def product_pairs(store, period, meta, scope='lifetime', limit=30):
    """Сочетаемость товаров (ТЗ §10): пары в одном чеке.

    Поддержка = чеки с парой / чеки с >= 2 разными позициями;
    уверенность A->B = чеки с парой / чеки с товаром A (в том же охвате).
    """
    if scope == 'period':
        d_from, d_to = period['p_start'].isoformat(), period['p_end'].isoformat()
    else:
        scope = 'lifetime'
        d_from, d_to = '0000-01-01', '9999-12-31'
    with store.conn() as conn:
        checks2plus = conn.execute(
            """
            SELECT COUNT(*) n FROM (
                SELECT 1 FROM receipt_items
                WHERE open_date >= ? AND open_date <= ?
                GROUP BY open_date, store, order_num, guest_id
                HAVING COUNT(DISTINCT dish_name) >= 2)
            """, (d_from, d_to)).fetchone()['n']
        dish_checks = {r['dish_name']: r['n'] for r in conn.execute(
            """
            SELECT dish_name, COUNT(*) n FROM (
                SELECT DISTINCT open_date, store, order_num, guest_id, dish_name
                FROM receipt_items WHERE open_date >= ? AND open_date <= ?)
            GROUP BY dish_name
            """, (d_from, d_to)).fetchall()}
        pairs = conn.execute(
            """
            SELECT a.dish_name da, b.dish_name db, COUNT(*) n
            FROM receipt_items a
            JOIN receipt_items b
              ON a.open_date = b.open_date AND a.store = b.store
             AND a.order_num = b.order_num AND a.guest_id = b.guest_id
             AND a.dish_name < b.dish_name
            WHERE a.open_date >= ? AND a.open_date <= ?
            GROUP BY a.dish_name, b.dish_name
            ORDER BY COUNT(*) DESC LIMIT ?
            """, (d_from, d_to, limit)).fetchall()
    out = []
    for r in pairs:
        out.append({
            'dish_a': r['da'], 'dish_b': r['db'], 'checks': r['n'],
            'support_pct': _pct(r['n'], checks2plus),
            'confidence_a_to_b_pct': _pct(r['n'], dish_checks.get(r['da'], 0)),
            'confidence_b_to_a_pct': _pct(r['n'], dish_checks.get(r['db'], 0)),
        })
    return {'scope': scope, 'checks_with_2plus_items': checks2plus, 'pairs': out}


# ---------------------------------------------------------------- §11 Точки

def venues_analytics(store, period, meta):
    """Аналитика по точкам (ТЗ §11)."""
    p_start, p_end = period['p_start'].isoformat(), period['p_end'].isoformat()

    def dist(conn, d_from, d_to):
        rows = conn.execute(
            """
            SELECT store, COUNT(*) visits, COUNT(DISTINCT guest_id) guests
            FROM (SELECT DISTINCT store, guest_id, open_date FROM receipts
                  WHERE open_date >= ? AND open_date <= ?)
            GROUP BY store ORDER BY visits DESC
            """, (d_from, d_to)).fetchall()
        total = sum(r['visits'] for r in rows)
        return [{'store': r['store'],
                 'store_name': VENUES.get(r['store'], {}).get('name', r['store']),
                 'visits': r['visits'], 'guests': r['guests'],
                 'share_pct': _pct(r['visits'], total)} for r in rows]

    with store.conn() as conn:
        first_dist = conn.execute(
            """
            SELECT first_order_store store, COUNT(*) guests FROM guests
            WHERE first_order_store IS NOT NULL
            GROUP BY first_order_store ORDER BY guests DESC
            """).fetchall()
        total_guests = sum(r['guests'] for r in first_dist)
        # Любимая точка гостя: максимум дней-визитов; при равенстве — порядок
        # PHYSICAL_VENUES, затем алфавит (детерминированный tie-break).
        per_guest_store = conn.execute(
            """
            SELECT guest_id, store, COUNT(DISTINCT open_date) v
            FROM receipts GROUP BY guest_id, store
            """).fetchall()
        first_store_map = {r['guest_id']: r['first_order_store'] for r in conn.execute(
            "SELECT guest_id, first_order_store FROM guests")}
        dist_period = dist(conn, p_start, p_end)
        dist_lifetime = dist(conn, '0000-01-01', '9999-12-31')

    order_idx = {k: i for i, k in enumerate(PHYSICAL_VENUES)}
    fav = {}
    stores_per_guest = {}
    for r in per_guest_store:
        gid = r['guest_id']
        stores_per_guest.setdefault(gid, set()).add(r['store'])
        cur = fav.get(gid)
        cand = (-r['v'], order_idx.get(r['store'], 99), r['store'])
        if cur is None or cand < cur[0]:
            fav[gid] = (cand, r['store'])
    fav_counts = {}
    for _, (_, s) in fav.items():
        fav_counts[s] = fav_counts.get(s, 0) + 1

    multi_store_guests = sum(1 for s in stores_per_guest.values() if len(s) >= 2)
    matrix = {}
    for gid, (_, fav_store) in fav.items():
        fs = first_store_map.get(gid)
        if not fs:
            continue
        matrix.setdefault(fs, {})
        matrix[fs][fav_store] = matrix[fs].get(fav_store, 0) + 1

    def vname(k):
        return VENUES.get(k, {}).get('name', k)

    return {
        'first_store': [{'store': r['store'], 'store_name': vname(r['store']),
                         'guests': r['guests'],
                         'share_pct': _pct(r['guests'], total_guests)}
                        for r in first_dist],
        'favorite_store': [{'store': s, 'store_name': vname(s), 'guests': n}
                           for s, n in sorted(fav_counts.items(), key=lambda kv: -kv[1])],
        'distribution_period': dist_period,
        'distribution_lifetime': dist_lifetime,
        'multi_store_guests': multi_store_guests,
        'multi_store_share_pct': _pct(multi_store_guests, len(stores_per_guest)),
        'migration_matrix': {fs: {ts: n for ts, n in row.items()}
                             for fs, row in matrix.items()},
    }


# ---------------------------------------------------------------- §12 Карточка

def search_guests(store, q, limit=20):
    """Поиск гостя по телефону/карте/имени (ТЗ §12)."""
    like = f"%{q.strip()}%"
    with store.conn() as conn:
        rows = conn.execute(
            """
            SELECT guest_id, name, phone, card_number, last_visit_date
            FROM guests
            WHERE phone LIKE ? OR card_number LIKE ? OR name LIKE ? OR guest_id LIKE ?
            ORDER BY last_visit_date DESC LIMIT ?
            """, (like, like, like, like, limit)).fetchall()
    return [dict(r) for r in rows]


def guest_card(store, guest_id, period, meta):
    """Карточка гостя (ТЗ §12): все три среза + RFM и статус на дату среза."""
    p_start, p_end = period['p_start'].isoformat(), period['p_end'].isoformat()
    ytd_start = meta['ytd_start']
    asof = meta['asof']
    with store.conn() as conn:
        g = conn.execute("SELECT * FROM guests WHERE guest_id = ?",
                         (guest_id,)).fetchone()
        if not g:
            return None
        g = dict(g)

        def agg(d_from, d_to):
            r = conn.execute(
                """
                SELECT COUNT(*) orders, COUNT(DISTINCT open_date) visits,
                       SUM(revenue) revenue
                FROM receipts WHERE guest_id = ? AND open_date >= ? AND open_date <= ?
                """, (guest_id, d_from, d_to)).fetchone()
            rev = r['revenue'] or 0
            return {'orders': r['orders'], 'visits': r['visits'],
                    'revenue': round(rev),
                    'avg_check': round(rev / r['orders']) if r['orders'] else 0}

        slices = {
            'period': agg(p_start, p_end),
            'ytd': agg(ytd_start, p_end),
            'lifetime': agg('0000-01-01', '9999-12-31'),
        }
        top_dishes = [dict(r) for r in conn.execute(
            """
            SELECT dish_name, ROUND(SUM(amount), 1) amount, SUM(revenue) revenue
            FROM receipt_items WHERE guest_id = ?
            GROUP BY dish_name ORDER BY SUM(amount) DESC LIMIT 5
            """, (guest_id,)).fetchall()]
        for d in top_dishes:
            d['revenue'] = round(d['revenue'] or 0)
        stores = conn.execute(
            """
            SELECT store, COUNT(DISTINCT open_date) v FROM receipts
            WHERE guest_id = ? GROUP BY store
            """, (guest_id,)).fetchall()
        recent = [dict(r) for r in conn.execute(
            """
            SELECT open_date, store, order_num, revenue, discount
            FROM receipts WHERE guest_id = ?
            ORDER BY open_date DESC, order_num DESC LIMIT 50
            """, (guest_id,)).fetchall()]
        # RFM гостя на дату среза (окно 12 мес)
        win_start = (_parse_date(asof) - timedelta(days=RFM_WINDOW_DAYS - 1)).isoformat()
        w = conn.execute(
            """
            SELECT COUNT(DISTINCT open_date) f, MAX(open_date) last_visit,
                   SUM(revenue) m
            FROM receipts WHERE guest_id = ? AND open_date >= ? AND open_date <= ?
            """, (guest_id, win_start, asof)).fetchone()

    order_idx = {k: i for i, k in enumerate(PHYSICAL_VENUES)}
    fav_store = None
    if stores:
        fav_store = sorted(stores, key=lambda r: (-r['v'], order_idx.get(r['store'], 99),
                                                  r['store']))[0]['store']
    rfm_block = None
    if w and w['f']:
        rec_days = _days_between(w['last_visit'], asof)
        r_code = _rfm_r_code(rec_days)
        f_code = _rfm_f_code(w['f'])
        rfm_block = {'recency_days': rec_days, 'frequency': w['f'],
                     'monetary': round(w['m'] or 0), 'r': r_code, 'f': f_code,
                     'segment': _rfm_segment(r_code, f_code, w['f'])}
    status = None
    lv = g.get('last_visit_date')
    if lv and lv <= asof:
        days = _days_between(lv, asof)
        for name, lo, hi in ACTIVITY_SEGMENTS:
            if days >= lo and (hi is None or days <= hi):
                status = name
                break
    elif lv:
        status = 'active'

    for r in recent:
        r['revenue'] = round(r['revenue'] or 0)
        r['discount'] = round(r['discount'] or 0)
        r['store_name'] = VENUES.get(r['store'], {}).get('name', r['store'])

    return {
        'guest': {
            'guest_id': g['guest_id'], 'name': g['name'], 'phone': g['phone'],
            'card_number': g['card_number'],
            'registration_date': g['registration_date'],
            'registration_source': g['registration_source'],
            'first_order_date': g['first_order_date'],
            'first_order_store': g['first_order_store'],
            'first_order_store_name': VENUES.get(g['first_order_store'], {}).get(
                'name', g['first_order_store']),
            'last_visit_date': g['last_visit_date'],
        },
        'slices': slices,
        'ltv': slices['lifetime']['revenue'],
        'top_dishes': top_dishes,
        'favorite_store': fav_store,
        'favorite_store_name': VENUES.get(fav_store, {}).get('name', fav_store),
        'rfm': rfm_block,
        'activity_status': status,
        'recent_receipts': recent,
    }


# ---------------------------------------------------------------- §14 Сводка

def summary(store, period, meta):
    """Дашборд маркетолога (ТЗ §14): сводные показатели из готовых функций."""
    p_start, p_end = period['p_start'].isoformat(), period['p_end'].isoformat()
    growth = base_growth(store, period, meta)
    act = activity(store, period, meta)
    freq = frequency(store, period, meta)
    ltv_block = ltv(store, period, meta)
    with store.conn() as conn:
        chk = conn.execute(
            "SELECT COUNT(*) orders, SUM(revenue) rev FROM receipts "
            "WHERE open_date >= ? AND open_date <= ?", (p_start, p_end)).fetchone()
        chk_ytd = conn.execute(
            "SELECT COUNT(*) orders, SUM(revenue) rev FROM receipts "
            "WHERE open_date >= ? AND open_date <= ?",
            (meta['ytd_start'], p_end)).fetchone()
        regs_by_store = conn.execute(
            """
            SELECT first_order_store store, COUNT(*) n FROM guests
            WHERE registration_source='iiko'
              AND registration_date >= ? AND registration_date <= ?
            GROUP BY first_order_store ORDER BY n DESC
            """, (p_start, p_end)).fetchall()
    active_seg = next(s for s in act['segments'] if s['segment'] == 'active')
    return {
        'base_size': growth['lifetime']['base_size'],
        'active_guests': active_seg['count'],
        'activity_segments': act['segments'],
        'registrations': growth['period']['registrations'],
        'registrations_ytd': growth['ytd']['registrations'],
        'first_orders': growth['period']['first_orders'],
        'first_orders_ytd': growth['ytd']['first_orders'],
        'conversion_pct': growth['period']['conversion_pct'],
        'conversion_ytd_pct': growth['ytd']['conversion_pct'],
        'avg_days_to_first_order': growth['period']['avg_days_to_first_order'],
        'avg_frequency': freq['period']['avg_visits_per_guest'],
        'avg_check': (round((chk['rev'] or 0) / chk['orders'])
                      if chk['orders'] else 0),
        'avg_check_ytd': (round((chk_ytd['rev'] or 0) / chk_ytd['orders'])
                          if chk_ytd['orders'] else 0),
        'revenue_period': round(chk['rev'] or 0),
        'orders_period': chk['orders'],
        'avg_ltv': ltv_block['lifetime']['avg_ltv'],
        'registrations_by_store': [
            {'store': r['store'],
             'store_name': VENUES.get(r['store'], {}).get('name', r['store']),
             'count': r['n']} for r in regs_by_store],
    }
