"""Расчётный слой модуля «Аналитика гостей (CRM)» — чистые функции над guests.db.

Все метрики считаются SQL/Python по локальной витрине (core/guest_store.py),
обращений к iiko здесь нет. Каждая формула детерминирована и продублирована
пользователю в UI (тултипы + блок «Как считается», static/js/guests/formulas.js)
и в docs/guests.md.

Временная логика ТЗ (обязательная для всех разделов):
- Primary Period: неделя (ISO пн-вс) / календарный месяц / квартал / год;
- YTD: с 1 января года даты окончания периода по дату среза;
- Lifetime: вся загруженная история (покрытие витрины — в meta каждого ответа).

Дата среза (meta['asof']) одна на все отчёты раздела: min(конец периода, последний
ПОЛНЫЙ день данных) — решение владельца 2026-10-29. Период считается с первого дня по
дату среза. «Сегодня» не годится: витрина обновляется ночью, и паузы, измеренные до
дня, которого в ней ещё нет, разводили «Активных» и «Живых» оттока.

Зафиксированные ТЗ правила:
- когорты жизненного цикла — от месяца РЕГИСТРАЦИИ, Lifetime-логика;
- retention — от месяца ПЕРВОЙ ПОКУПКИ, окна 30/60/90/180/365 дней;
- RFM — скользящее окно 12 месяцев (365 дней) на дату среза, НЕ Lifetime;
- статусы активности — по последнему визиту на дату среза: Активные (active) <= 30 дн,
  Засыпают (sleeping) 31-90, Под угрозой (at_risk) 91-180, Потеряны (lost) > 180.

Отток (§17, решение владельца 2026-10-27; заменил §13 «Динамику базы»): гость
«жив» на дату, если с последнего визита прошло не больше X дней, и «мёртв», если
больше (X — переключатель вкладки 30/60/90/180, по умолчанию 30). За период
каждый гость попадает ровно в одну графу по состояниям накануне периода и на
дату среза: остался, ушёл, вернулся, новый; баланс сходится точно. Дата среза —
последний ПОЛНЫЙ день данных (data_to), а не «сегодня». С 2026-10-30 там же ущерб от
оттока в рублях, «Стали ходить реже» (скрытый отток) и подсказка к порогу — через сколько
дней гости возвращаются; гости каждой плитки поимённо — churn_guests. Подробности — churn_all.

Определения (те же, что в /discounts и месячной витрине):
- заказ (чек) = строка receipts (ключ дата+бар+номер чека+гость);
- визит = уникальная пара (гость, дата) — OpenDate.Typed времени не содержит;
- выручка = DishDiscountSumInt (что фактически заплатил гость).

Округления: деньги — целые рубли (round), проценты — 1 знак, дни/частота —
1 знак. Недозревшие ячейки когорт (конец месяца когорты + окно > даты среза)
отдаются как None и показываются в UI прочерком.

Разбивка по барам (параметр venue, с 2026-09-29) — «бар как отдельное
заведение»: берутся только чеки выбранного бара. Гость бара — тот, у кого есть
хоть один чек в нём; первый заказ, последний визит, визиты, чеки, выручка и
активность — только по этому бару. Поэтому сумма по четырём барам больше сети:
гость двух баров посчитан в обоих (так же считал RFM по точке и прежний RFM
на /discounts). Исключение — регистрация: карта одна на всю сеть, бара
регистрации iiko не хранит, поэтому регистрация закрепляется за баром ПЕРВОЙ
покупки в сети (как в «Регистраций на точку»), и регистрации по барам в сумме
дают сеть. Сравнения баров между собой (LTV и регистрации по точкам) считаются
только для всей сети; §11 «Точки» с баром — его гости и их визиты во все бары;
§15 (Orderia) и карточка гостя на бары не делятся.

Документация: docs/guests.md
"""

import calendar
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta

from core import msk_time
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

# Отток (§17): гость «мёртв», если с последнего визита прошло больше X дней.
# Переключатель вкладки — эти четыре порога; по умолчанию 30 (решение владельца
# 2026-10-27) — это и порог «Активных» в §3, поэтому при X = 30 «живые» = Активные, а
# при X = 180 «мёртвые» = Потерянные. Схема MCP перечисляет те же значения (enum).
CHURN_DEAD_DAYS_CHOICES = (30, 60, 90, 180)
CHURN_DEAD_DAYS_DEFAULT = 30
# Длина ряда по умолчанию — сколько периодов выбранного типа видно на графике:
# полгода недель, два года месяцев, три года кварталов, восемь лет (витрина с 2017-12).
CHURN_SERIES_DEFAULT = {'week': 26, 'month': 24, 'quarter': 12, 'year': 8}
# Границы параметра periods (как у прежнего months динамики базы): меньше трёх точек —
# не ряд, больше 60 — ответ перестаёт помещаться в предел моста MCP (60 тыс. знаков).
CHURN_SERIES_MIN = 3
CHURN_SERIES_MAX = 60
# «Кто уходит»: ушедшие по числу визитов за всю жизнь до даты среза. Границы те же, что
# у сегментов частоты §4, но смысл другой (там визиты за период) — поэтому своя константа:
# правка сегментов частоты не должна молча менять эту разбивку.
CHURN_LEAVER_BUCKETS = [('1', 1, 1), ('2-3', 2, 3), ('4-8', 4, 8), ('9+', 9, None)]
# Ущерб от оттока (решение владельца 2026-10-30, по статье Unisender о churn rate): формула
# статьи «потерянные × средний чек × платежей за интервал» для бара — средний чек ушедшего ×
# его чеков в месяц, то есть его выручка за год до последнего визита / 12. Год — полный
# сезонный цикл бара: за окно короче ущерб зависел бы от того, в какой сезон гость ушёл.
CHURN_DAMAGE_WINDOW_DAYS = 365
CHURN_DAMAGE_MONTHS = 12        # месяцев в окне ущерба: месячный ущерб = выручка окна / 12
# «Стали ходить реже» — скрытый отток статьи: гость ещё ходит, но заметно реже, чем раньше.
# Сравниваются два соседних окна по 90 дней (последний квартал против предыдущего): за
# 90 дней у гостя, который ходит раз в месяц, набирается 3 визита; окно короче — и «вдвое
# реже» решали бы случайные пропуски.
CHURN_SLOWING_WINDOW_DAYS = 90
# В прошлом окне — не меньше 3 визитов («ходил хотя бы раз в месяц»): у гостя с 1–2 визитами
# «вдвое реже» — это один визит против двух, случайность, а не перемена привычки.
CHURN_SLOWING_MIN_PREV = 3
# «Вдвое реже»: визитов в последнем окне не больше половины прошлых. Сравнение в целых —
# 2 × последние <= прошлые, без дробей и округлений.
CHURN_SLOWING_FACTOR = 2
# Подсказка к порогу: паузы перед повторными визитами за год до даты среза (полный сезонный
# цикл, как у ущерба). Доля пауз длиннее порога — возвраты, которые порог успел записать в
# «Ушли» (потом они же — «Вернулись после паузы»).
CHURN_RETURN_WINDOW_DAYS = 365
# Перцентили паузы для подписи «половина возвращается за N дней, 9 из 10 — за M».
CHURN_RETURN_PERCENTILES = (50, 90)
# Плитки «Оттока» с поимённым списком (кликабельны, решение владельца 2026-10-30: «если мы
# знаем имена гостей»): «Ушли», «Вернулись после паузы», «Новые гости», «Не вернулись после
# первого визита», «Стали ходить реже». Каждая группа — ровно те гости, что в счётчике плитки
# (churn_guests). Схема MCP перечисляет те же значения (enum group).
CHURN_GUEST_GROUPS = ('left', 'reactivated', 'new', 'newbie_no_return', 'slowing')

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
    # Дата московская, а не системная: прод-контейнер живёт в UTC (см.
    # core/msk_time.py), и с 00:00 до 03:00 МСК период по умолчанию уезжал бы
    # на сутки назад — а бары в это время ещё работают.
    a = _parse_date(anchor, msk_time.today())
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


def resolve_venue(raw):
    """Параметр ?store= -> ключ бара из PHYSICAL_VENUES или None (вся сеть).

    Неизвестное значение (русское имя, 'all', опечатка) означает всю сеть — так
    было и у RFM: пустой отчёт или 500 на кривом параметре хуже, а какой срез
    посчитан на самом деле, ответ говорит сам (meta.venue). Значение сверяется
    со списком, поэтому в SQL попадает только известный ключ, и то параметром.
    """
    return raw if raw in PHYSICAL_VENUES else None


def build_meta(store, period, venue=None):
    """meta каждого ответа: границы срезов, бар, покрытие витрины, режим регистраций.

    venue и venue_name — бар, по которому посчитан ответ (None — вся сеть). Режим
    регистраций (fallback) — свойство источника, поэтому считается по всей базе.
    """
    venue = resolve_venue(venue)
    cov = store.coverage()
    p_end = period['p_end']
    # Дата среза — последний ПОЛНЫЙ день данных, одна на все отчёты раздела (решение
    # владельца 2026-10-29): «сегодня» мерило паузы до дня, которого в витрине ещё нет,
    # и «Активные» расходились с «Живыми» оттока. Без чеков — вчерашний рабочий день.
    last_full = _last_full_day(cov['date_to'])
    cut = last_full or (msk_time.business_today() - timedelta(days=1)).isoformat()
    asof = min(p_end.isoformat(), cut)
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
        'asof': asof,
        'data_to': last_full,
        'ytd_start': date(p_end.year, 1, 1).isoformat(),
        'venue': venue,
        'venue_name': VENUES.get(venue, {}).get('name') if venue else None,
        'coverage_from': cov['date_from'],
        'coverage_to': cov['date_to'],
        'last_synced_at': cov['last_synced_at'],
        'fallback_share': fallback_share,
        'fallback_mode': fallback_share > FALLBACK_MODE_THRESHOLD,
    }


# ---------------------------------------------------------------- загрузчики

def _venue_cond(venue, column='store'):
    """Кусок WHERE «только этот бар» и его параметры.

    -> (" AND <column> = ?", [venue]) или ("", []) для всей сети. column —
    колонка с ключом бара (store, i.store, first_order_store).
    """
    if venue:
        return f" AND {column} = ?", [venue]
    return "", []


def _first_order_sql(venue):
    """Подзапрос (guest_id, f): дата первого заказа гостя -> (sql, params).

    Вся сеть — денормализованная guests.first_order_date; с баром — первый чек
    гостя ИМЕННО В ЭТОМ баре (новый гость бара, даже если в сети он давно).
    """
    if venue:
        return ("SELECT guest_id, MIN(open_date) AS f FROM receipts "
                "WHERE store = ? GROUP BY guest_id"), [venue]
    return "SELECT guest_id, first_order_date AS f FROM guests", []


def _load_guests(conn, venue=None):
    """Гости: список dict-строк таблицы guests.

    venue — бар или None. С баром в выборке только гости, у которых есть чек в
    этом баре, а first_order_date и last_visit_date — первый и последний визит
    именно в него. reg_here — регистрация гостя закреплена за этим баром (бар
    первой покупки в сети); для всей сети — всегда 1.
    """
    if not venue:
        return [dict(r) for r in conn.execute(
            "SELECT guest_id, name, phone, card_number, registration_date, "
            "registration_source, first_order_date, first_order_store, "
            "last_visit_date, 1 AS reg_here FROM guests")]
    return [dict(r) for r in conn.execute(
        """
        SELECT g.guest_id, g.name, g.phone, g.card_number, g.registration_date,
               g.registration_source, v.first_visit AS first_order_date,
               g.first_order_store, v.last_visit AS last_visit_date,
               CASE WHEN g.first_order_store = ? THEN 1 ELSE 0 END AS reg_here
        FROM guests g
        JOIN (SELECT guest_id, MIN(open_date) AS first_visit,
                     MAX(open_date) AS last_visit
              FROM receipts WHERE store = ? GROUP BY guest_id) v
          ON v.guest_id = g.guest_id
        """, (venue, venue))]


def _load_visits(conn, venue=None):
    """{guest_id: [даты визитов по возрастанию]} за всю историю; с баром — в него."""
    store_sql, params = ("WHERE store = ? ", [venue]) if venue else ("", [])
    visits = {}
    for r in conn.execute(
            "SELECT guest_id, open_date FROM receipts " + store_sql +
            "GROUP BY guest_id, open_date ORDER BY guest_id, open_date", params):
        visits.setdefault(r['guest_id'], []).append(r['open_date'])
    return visits


def _load_guest_totals(conn, venue=None, upto=None):
    """{guest_id: {'orders': n, 'revenue': x}} по чекам не позже upto; с баром — его чеки.

    upto — дата среза отчёта (ISO). Без неё суммы шли бы до сегодняшнего дня, и прошлый
    период видел бы будущую выручку и чеки (так считали §2 и §6 до 2026-10-27): доля
    «2+ чека» марта росла от апрельских визитов, а цифры прошлого менялись со временем.
    """
    conds, params = [], []
    if venue:
        conds.append("store = ?")
        params.append(venue)
    if upto:
        conds.append("open_date <= ?")
        params.append(upto)
    where = ("WHERE " + " AND ".join(conds) + " ") if conds else ""
    return {r['guest_id']: {'orders': r['orders'], 'revenue': r['revenue'] or 0.0}
            for r in conn.execute(
                "SELECT guest_id, COUNT(*) orders, SUM(revenue) revenue "
                "FROM receipts " + where + "GROUP BY guest_id", params)}


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
    """Дата регистрации гостя в выбранном базисе (может быть None).

    С выбранным баром регистрация из iiko есть только у гостей, чья первая
    покупка в сети была в этом баре (reg_here, см. _load_guests). В fallback-
    базисе регистрация = первая покупка, а с баром — первая покупка в нём.
    """
    if basis == 'iiko':
        if g['registration_source'] == 'iiko' and g['reg_here']:
            return g['registration_date']
        return None
    return g['first_order_date']


def _pct(part, total, digits=1):
    return round(100.0 * part / total, digits) if total else 0.0


def _last_full_day(coverage_to):
    """Последний ПОЛНЫЙ учётный день витрины (ISO) или None, если чеков нет.

    min(последний день с чеками, рабочий день бара - 1 день). Последний день с
    чеками бывает неполным: дневной деплой пересинкает текущий месяц
    (guest_sync_scheduler._startup_backfill), и в витрину попадает половина
    сегодняшней смены — гость, который зайдёт вечером, уже числился бы ушедшим.
    Рабочий день меняется в 06:00 МСК (msk_time.business_today). Срез общий для
    сети и для бара: полнота данных — свойство синка (один запрос на все бары), а
    не бара; по последнему чеку бара отток «замирал» бы как раз на его закрытии.
    """
    if not coverage_to:
        return None
    last_full = (msk_time.business_today() - timedelta(days=1)).isoformat()
    return min(coverage_to, last_full)


def data_to(meta):
    """Последний полный день данных из meta отчёта (см. _last_full_day) или None."""
    return _last_full_day(meta.get('coverage_to'))


def _cut_day(meta):
    """Последний полный день для дат среза, как в build_meta: без чеков — вчерашний рабочий."""
    return meta.get('data_to') or (msk_time.business_today() - timedelta(days=1)).isoformat()


def parse_dead_days(raw):
    """?dead_days= -> порог из CHURN_DEAD_DAYS_CHOICES; иное — CHURN_DEAD_DAYS_DEFAULT.

    Как basis/mode модуля: кривой параметр не роняет отчёт, а по какому порогу
    посчитано на самом деле, ответ говорит сам (data.dead_days). В схеме MCP — enum.
    """
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return CHURN_DEAD_DAYS_DEFAULT
    return value if value in CHURN_DEAD_DAYS_CHOICES else CHURN_DEAD_DAYS_DEFAULT


def parse_series_len(raw, period_type):
    """?periods= -> длина ряда в CHURN_SERIES_MIN..MAX; пусто или мусор — по умолчанию.

    Без int() на сыром вводе в маршруте: у прежнего ?months= мусор давал 500.
    """
    default = CHURN_SERIES_DEFAULT.get(period_type, CHURN_SERIES_DEFAULT['month'])
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return min(max(value, CHURN_SERIES_MIN), CHURN_SERIES_MAX)


def _rate(part, total, digits=1):
    """Доля в процентах или None при нулевом знаменателе.

    В отличие от _pct (там 0.0): отток при пустой базе на начало не определён, а
    «0%» читался бы как «никто не ушёл».
    """
    return round(100.0 * part / total, digits) if total else None


def _series_periods(period, n, scope_from):
    """Выбранный период и до n-1 предыдущих того же типа — от старых к новым.

    Шаг назад — resolve_period(type, prev_end): ISO-недели через границу года и
    кварталы сходятся сами. Периоды, закончившиеся раньше scope_from (ISO-дата
    начала данных: сети или первого чека бара), отбрасываются; без данных — [].
    """
    out = []
    if not scope_from:
        return out
    p = period
    for _ in range(n):
        if p['p_end'].isoformat() < scope_from:
            break
        out.append(p)
        p = resolve_period(p['type'], p['prev_end'].isoformat())
    out.reverse()
    return out


# ---------------------------------------------------------------- §1 Рост базы

def base_growth(store, period, meta, venue=None):
    """Регистрации, первые заказы, конверсия, время до первого заказа (P + YTD).

    Ограничение источника (принято владельцем): OLAP видит только гостей с >=1
    чеком за историю, поэтому «регистрации» — по купившим хоть раз; свежие
    периоды дорастают задним числом. В fallback-режиме конверсия и время до
    первого заказа не определены (регистрация = первая покупка) и отдаются None.

    venue — бар или None. С баром первые заказы — гости, чей первый чек В ЭТОМ
    БАРЕ попал в срез (новые гости бара, в том числе пришедшие из других баров);
    регистрации, конверсия и дни до заказа — по гостям, чья первая покупка в сети
    была в этом баре (за ним закреплена регистрация); размер базы — гости с хотя
    бы одним чеком в баре.

    Период и размер базы — по дату среза (meta['asof'], последний полный день данных):
    «новые гости» те же, что у оттока, а размер базы прошлого периода не растёт от
    гостей, пришедших позже (2026-10-29).
    """
    p_start, p_end = period['p_start'].isoformat(), meta['asof']
    ytd_start = meta['ytd_start']
    fallback = meta['fallback_mode']
    venue = resolve_venue(venue)
    first_sql, first_params = _first_order_sql(venue)
    reg_sql, reg_params = _venue_cond(venue, 'first_order_store')

    def slice_metrics(conn, d_from, d_to):
        regs = conv = avg_days = None
        first = conn.execute(
            f"SELECT COUNT(*) n FROM ({first_sql}) WHERE f >= ? AND f <= ?",
            first_params + [d_from, d_to]).fetchone()['n']
        if not fallback:
            regs = conn.execute(
                "SELECT COUNT(*) n FROM guests WHERE registration_source='iiko' "
                "AND registration_date >= ? AND registration_date <= ?" + reg_sql,
                [d_from, d_to] + reg_params).fetchone()['n']
            # MAX(0, ...): чек последнего часа смены попадает в учётный день
            # НАКАНУНЕ календарной даты создания карты (бар работает за полночь),
            # отсюда формальные «-1 день» — считаем их нулём. С баром здесь только
            # гости, чья первая покупка в сети была в нём, и first_order_date —
            # это и первый чек в баре.
            row = conn.execute(
                """
                SELECT COUNT(*) converted,
                       AVG(MAX(0, julianday(first_order_date)
                                  - julianday(registration_date))) days
                FROM guests
                WHERE registration_source='iiko'
                  AND registration_date >= ? AND registration_date <= ?
                  AND first_order_date <= ?""" + reg_sql,
                [d_from, d_to, d_to] + reg_params).fetchone()
            conv = _pct(row['converted'], regs) if regs else None
            avg_days = round(row['days'], 1) if row['days'] is not None else None
        return {'registrations': regs, 'first_orders': first,
                'conversion_pct': conv, 'avg_days_to_first_order': avg_days}

    with store.conn() as conn:
        if venue:
            base_size = conn.execute(
                "SELECT COUNT(DISTINCT guest_id) n FROM receipts "
                "WHERE store = ? AND open_date <= ?", (venue, p_end)).fetchone()['n']
        else:
            base_size = conn.execute(
                "SELECT COUNT(*) n FROM guests WHERE first_order_date <= ?",
                (p_end,)).fetchone()['n']
        out = {
            'period': slice_metrics(conn, p_start, p_end),
            'ytd': slice_metrics(conn, ytd_start, p_end),
            'lifetime': {'base_size': base_size},
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


def activity(store, period, meta, venue=None):
    """Статусы базы на дату среза + сравнение с предыдущим периодом (ТЗ §3).

    С баром (venue) — гости бара и их визиты только в него: статус считается от
    последнего визита В ЭТОТ бар.
    """
    asof = meta['asof']
    prev_asof = min(period['prev_end'].isoformat(), _cut_day(meta))
    venue = resolve_venue(venue)
    with store.conn() as conn:
        guests = _load_guests(conn, venue)
        visits = _load_visits(conn, venue)
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

def frequency(store, period, meta, venue=None):
    """Частота визитов за Primary Period (ТЗ §4): сегменты и средняя частота.

    С баром (venue) — визиты только в этот бар. Период — по дату среза (meta['asof']).
    """
    p_start, p_end = period['p_start'].isoformat(), meta['asof']
    ytd_start = meta['ytd_start']
    store_sql, store_params = _venue_cond(resolve_venue(venue))

    def calc(conn, d_from, d_to):
        rows = conn.execute(
            "SELECT guest_id, COUNT(DISTINCT open_date) v FROM receipts "
            "WHERE open_date >= ? AND open_date <= ?" + store_sql + " GROUP BY guest_id",
            [d_from, d_to] + store_params).fetchall()
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

def lifecycle_cohorts(store, period, meta, months_limit=24, venue=None):
    """Когорты жизненного цикла (ТЗ §2): когорта = месяц регистрации.

    Воронка внутри когорты — Lifetime по дату среза: доля гостей с >= 2 и >= 5
    чеками от первой покупки до asof (не до сегодня: иначе прошлый период видел бы
    будущие чеки, 2026-10-27). Колонки «>= 1 чек» здесь НЕТ намеренно: гость
    попадает в витрину только вместе с первой покупкой, а оставшиеся без чеков
    удаляются (guest_store.replace_month), поэтому такая доля тождественно равна
    100% и не несёт информации. Сколько людей зарегистрировалось и не купило —
    отдельный отчёт never_buyers() по данным Orderia.

    «% активных» — НА ДАТУ СРЕЗА: последний визит не позже asof и не раньше
    asof - 30 дней. Верхняя граница обязательна: без неё листание в прошлое
    засчитывало в «активных» визиты, случившиеся ПОСЛЕ среза (в марте были бы
    активны все, кто заходил вплоть до августа).

    В fallback-режиме базис автоматически «первая покупка» (совпадает с §5) —
    помечено в meta.

    С баром (venue) в когорте — гости, чья регистрация закреплена за баром
    (первая покупка в сети — в нём); чеки и активность — только в этом баре:
    «сколько из тех, кого привёл бар, остались ЕГО гостями».
    """
    basis = _registration_basis(meta)
    asof = meta['asof']
    active_from = (_parse_date(asof) - timedelta(days=ACTIVITY_SEGMENTS[0][2])).isoformat()
    venue = resolve_venue(venue)
    with store.conn() as conn:
        guests = _load_guests(conn, venue)
        totals = _load_guest_totals(conn, venue, upto=asof)
        visits = _load_visits(conn, venue)
    cohorts = {}
    for g in guests:
        reg = _reg_date(g, basis)
        # Когорты будущее не содержат: гость существует на дату среза
        if not reg or reg > asof:
            continue
        ym = reg[:7]
        c = cohorts.setdefault(ym, {'n': 0, 'order2': 0, 'order5': 0, 'active': 0})
        c['n'] += 1
        orders = totals.get(g['guest_id'], {}).get('orders', 0)
        if orders >= 2:
            c['order2'] += 1
        if orders >= 5:
            c['order5'] += 1
        last_visit = _last_visit_at(visits.get(g['guest_id'], []), asof)
        if last_visit and last_visit >= active_from:
            c['active'] += 1
    rows = []
    for ym in sorted(cohorts.keys(), reverse=True)[:months_limit]:
        c = cohorts[ym]
        rows.append({
            'cohort': ym, 'guests': c['n'],
            'order2_pct': _pct(c['order2'], c['n']),
            'order5_pct': _pct(c['order5'], c['n']),
            'active_pct': _pct(c['active'], c['n']),
        })
    return {'basis': basis, 'cohorts': rows}


def cohort_retention(store, period, meta, basis='first_order', months_limit=24,
                     venue=None):
    """Возвраты когорт (ТЗ §5, а с basis='registration' — retention-слой §2).

    Когорта = месяц первой покупки (или регистрации). Возврат = визит в окне
    (первая покупка, первая покупка + N дней], N из RETENTION_WINDOWS.
    Ячейка зрелая, только если конец месяца когорты + N <= последнего полного дня
    данных; иначе None (в UI прочерк) — недозревшие когорты не занижают проценты.
    Зрелость — по данным, а не по концу выбранного периода (2026-10-29): возврат за
    окно — свойство когорты, после созревания оно не меняется, а «Не вернулись после
    первого визита» на «Оттоке» созревает по тому же правилу и с тем же окном, поэтому
    вместе с «Возвратами через X дней» даёт 100% и прочерки стоят в тех же местах.

    С баром (venue) первая покупка и возвраты — только в этом баре: вернулся ли
    гость именно сюда.
    """
    if basis == 'registration':
        basis = _registration_basis(meta)
    asof = meta['asof']
    venue = resolve_venue(venue)
    with store.conn() as conn:
        guests = _load_guests(conn, venue)
        visits = _load_visits(conn, venue)
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
    known = _cut_day(meta)
    rows = []
    for ym in sorted(cohorts.keys(), reverse=True)[:months_limit]:
        c = cohorts[ym]
        month_end = _parse_date(_month_end_iso(ym))
        cells = {}
        for w in RETENTION_WINDOWS:
            matured = (month_end + timedelta(days=w)).isoformat() <= known
            cells[str(w)] = _pct(c['returned'][w], c['n']) if matured else None
        rows.append({'cohort': ym, 'guests': c['n'], 'returned_pct': cells})
    return {'basis': basis, 'windows': RETENTION_WINDOWS, 'cohorts': rows}


# ---------------------------------------------------------------- §6 Доходы

def cohort_revenue(store, period, meta, basis='registration', months_limit=24,
                   venue=None):
    """Когортные доходы (ТЗ §6): накопительные выручка/заказы/LTV по когортам.

    Накопительно по дату среза (asof), а не до сегодня: прошлый период не видит
    более поздней выручки, как LTV на дату (§8, 2026-10-27).

    С баром (venue) — выручка и чеки только этого бара; когорта по регистрации —
    гости, чья регистрация закреплена за баром, по первой покупке — первый чек
    в нём.
    """
    if basis == 'registration':
        eff_basis = _registration_basis(meta)
    else:
        eff_basis = 'first_order'
    asof = meta['asof']
    venue = resolve_venue(venue)
    with store.conn() as conn:
        guests = _load_guests(conn, venue)
        totals = _load_guest_totals(conn, venue, upto=asof)
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
    """Именованный сегмент — модель /discounts (get_rfm_segment) плюс RARE_LOST.

    RARE_LOST (2026-10-29, решение владельца): ходили реже раза в неделю (F1/F2, меньше
    52 визитов за окно) и не были больше 60 дней (R1). Раньше они падали в POTENTIAL с
    описанием «визит свежий» — так в «Потенциальных» оказывались почти все пропавшие
    редкие гости, а «Уходящие» (CHURNED) брали только частых.
    """
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
    if r_code == 1:
        return 'RARE_LOST'
    if f_code in (1, 2):
        return 'POTENTIAL'
    return 'LOYAL'


def rfm(store, period, meta, include_guests=True, venue=None):
    """RFM-сегментация (ТЗ §7) на дату среза, окно 12 месяцев (365 дней).

    Население: гости с >=1 визитом в окне (p_end-364 .. p_end включительно).
    R = дней с последнего визита; F = визитов в окне; M = выручка окна.

    venue — ключ точки из PHYSICAL_VENUES или None (вся сеть). При фильтре по
    точке R/F/M считаются ТОЛЬКО по чекам этой точки: это ответ на вопрос «как
    гость ведёт себя в этом баре», а не «как он ведёт себя вообще, но был здесь».
    Поэтому сумма гостей по четырём барам БОЛЬШЕ сетевого числа — гость, ходящий
    в два бара, попадает в оба среза. Так же считал прежний RFM на /discounts,
    где фильтр по бару шёл в OLAP-запрос.
    """
    asof = meta['asof']
    win_start = (_parse_date(asof) - timedelta(days=RFM_WINDOW_DAYS - 1)).isoformat()
    venue = resolve_venue(venue)
    venue_sql, venue_params = _venue_cond(venue, 'r.store')
    params = [win_start, asof] + venue_params
    with store.conn() as conn:
        rows = conn.execute(
            f"""
            SELECT r.guest_id, COUNT(DISTINCT r.open_date) f,
                   COUNT(*) orders,
                   MAX(r.open_date) last_visit, SUM(r.revenue) m,
                   g.name, g.phone, g.card_number
            FROM receipts r JOIN guests g ON g.guest_id = r.guest_id
            WHERE r.open_date >= ? AND r.open_date <= ?{venue_sql}
            GROUP BY r.guest_id
            """, params).fetchall()
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
                'last_visit': r['last_visit'],
                'recency_days': rec_days, 'frequency': r['f'],
                'orders': r['orders'],
                # Средний чек — выручка / ЧЕКИ, единое определение проекта
                # (GUEST_FORMULAS.avg_check, docs/guests.md).
                'avg_check': (round((r['m'] or 0) / r['orders'])
                              if r['orders'] else 0),
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
           'venue': venue,
           'venue_name': VENUES.get(venue, {}).get('name') if venue else None,
           'venues': [{'key': k, 'name': VENUES.get(k, {}).get('name', k)}
                      for k in PHYSICAL_VENUES],
           'r_thresholds': list(RFM_R_THRESHOLDS),
           'f_thresholds': list(RFM_F_THRESHOLDS)}
    if include_guests:
        out['guests'] = guest_rows
    return out


# Имена сегментов RFM (результат _rfm_segment) — допустимые значения фильтра segment=.
RFM_SEGMENTS = ('CHAMPIONS', 'LOYAL', 'POTENTIAL', 'NEW', 'AT_RISK', 'CHURNED', 'RARE_LOST')
# Минимальная длина подстроки q= в списке гостей RFM — как у поиска гостя (§12,
# /api/guests/search): одна цифра совпала бы с половиной базы.
RFM_QUERY_MIN_LEN = 2


def parse_rfm_segments(raw):
    """Параметр segment= -> frozenset имён сегментов или None (фильтра нет).

    Несколько сегментов — через запятую ('AT_RISK,CHURNED'); регистр не важен.
    Raises:
        ValueError: неизвестное имя — текст для ответа 400 (молча пустой список
        выглядел бы как «таких гостей нет»).
    """
    names = [part.strip().upper() for part in str(raw or '').split(',') if part.strip()]
    if not names:
        return None
    unknown = [name for name in names if name not in RFM_SEGMENTS]
    if unknown:
        raise ValueError('Неизвестный сегмент RFM: ' + ', '.join(unknown)
                         + '. Сегменты: ' + ', '.join(RFM_SEGMENTS))
    return frozenset(names)


def rfm_filter_guests(guests, segments=None, q=None, limit=None):
    """Фильтр СПИСКА гостей RFM (с 2026-09-28; полный ответ — 500+ тыс. знаков).

    Меняется только список guests: segments и total_guests ответа по-прежнему
    считаются по всем гостям окна, иначе доли сегментов зависели бы от фильтра.

    Args:
        guests: строки rfm()['guests'] — уже по убыванию выручки окна (monetary)
        segments: множество имён из RFM_SEGMENTS или None — все сегменты
        q: подстрока без учёта регистра в имени, номере карты или guest_id; для
           телефона сравниваются только цифры ('+7 (921) 55' ищет '792155'), так
           что лишняя ведущая 7 в витрине поиску по последним цифрам не мешает;
           None или '' — без поиска
        limit: сколько строк вернуть после фильтра (первые — самые ценные гости
           окна); None — все

    Returns:
        (строки, matched) — matched = сколько подошло до обрезки limit.
    """
    needle = (q or '').strip().lower()
    digits = ''.join(ch for ch in needle if ch.isdigit())
    rows = []
    for guest in guests:
        if segments and guest.get('segment') not in segments:
            continue
        if needle:
            text_hit = any(needle in str(guest.get(field) or '').lower()
                           for field in ('name', 'card_number', 'guest_id'))
            phone_digits = ''.join(ch for ch in str(guest.get('phone') or '') if ch.isdigit())
            phone_hit = len(digits) >= RFM_QUERY_MIN_LEN and digits in phone_digits
            if not (text_hit or phone_hit):
                continue
        rows.append(guest)
    matched = len(rows)
    if limit is not None:
        rows = rows[:limit]
    return rows, matched


# ---------------------------------------------------------------- §8 LTV

def _ltv_daily(conn, venue=None):
    """Чеки и выручка по дням + даты первых визитов — всё для LTV на любую дату.

    -> (дни, накопленные чеки, накопленная выручка, отсортированные первые визиты);
    дни — date.toordinal(). Первый визит — первый чек гостя (с баром — в этом баре),
    из тех же чеков, что и выручка: гость без чека не попадёт в знаменатель.
    """
    store_sql, params = ("WHERE store = ? ", [venue]) if venue else ("", [])
    days, cum_checks, cum_revenue = [], [], []
    for r in conn.execute(
            "SELECT open_date, COUNT(*) n, SUM(revenue) rev FROM receipts " + store_sql +
            "GROUP BY open_date ORDER BY open_date", params):
        days.append(date.fromisoformat(r['open_date'][:10]).toordinal())
        cum_checks.append((cum_checks[-1] if cum_checks else 0) + r['n'])
        cum_revenue.append((cum_revenue[-1] if cum_revenue else 0.0) + (r['rev'] or 0.0))
    firsts = sorted(
        date.fromisoformat(r['f'][:10]).toordinal() for r in conn.execute(
            "SELECT MIN(open_date) f FROM receipts " + store_sql + "GROUP BY guest_id",
            params))
    return days, cum_checks, cum_revenue, firsts


def _ltv_at(daily, d_o):
    """(гостей, чеков, выручка) по чекам не позже дня d_o (порядковый номер)."""
    days, cum_checks, cum_revenue, firsts = daily
    i = bisect_right(days, d_o)
    return (bisect_right(firsts, d_o), cum_checks[i - 1] if i else 0,
            cum_revenue[i - 1] if i else 0.0)


def _ltv_parts(guests, checks, revenue):
    """LTV и сомножители без округления: (LTV, средний чек, чеков на гостя) или Nones."""
    if not guests or not checks:
        return None, None, None
    return revenue / guests, revenue / checks, checks / guests


def ltv(store, period, meta, venue=None, periods=None):
    """LTV на дату (ТЗ §8): средний, из чего состоит, ряд по периодам; YTD; по точкам.

    Дата среза D = min(конец периода, data_to) — та же, что у оттока (§17): последний
    полный день данных. Все суммы — по чекам не позже D: прошлый период не видит
    более поздней выручки, и его цифры не меняются со временем (до 2026-10-27
    lifetime-суммы шли до сегодняшнего дня при любом периоде).

    - LTV = выручка чеков <= D / гостей с первым визитом <= D;
    - средний чек = выручка <= D / чеков <= D; чеков на гостя = чеков <= D / гостей;
      LTV = средний чек × чеков на гостя (тождество; решение владельца 2026-10-27 —
      «из чего состоит»). Частота здесь в ЧЕКАХ, §4 считает визиты-дни;
    - series — те же величины на конец каждого периода ряда (длина — как у оттока,
      parse_series_len) и изменение к предыдущей точке, разложенное симметрично (без
      зависимости от порядка): вклад чека = (c1 - c0) × (f0 + f1) / 2, вклад частоты =
      (f1 - f0) × (c0 + c1) / 2, сумма = ΔLTV точно;
    - округления: всё считается из несокращённых сумм; delta = round(LTV1) - round(LTV0),
      check_effect = round(своего), frequency_effect = delta - check_effect (впитывает
      остаток до 1 ₽ — показанные числа складываются). Чек — до рубля, чеков на гостя —
      2 знака (с одним знаком произведение расходилось бы с LTV на сотню рублей),
      поэтому произведение показанных сомножителей может отличаться от LTV на рубли;
    - накопленные «чеков на гостя» растут, когда база стареет, и падают, когда приходит
      много новых: вклад частоты — не только «гости стали ходить чаще».

    С баром (venue) — выручка, чеки и гости только этого бара: LTV гостя В ЭТОМ баре.
    by_venue — сравнение баров между собой (гость закреплён за баром первого заказа в
    сети, выручка — по всей сети до D), поэтому считается только для всей сети; с баром
    это пустой список, как профиль баров на /packaging и /kitchen.
    """
    venue = resolve_venue(venue)
    n = periods or CHURN_SERIES_DEFAULT.get(period['type'], CHURN_SERIES_DEFAULT['month'])
    last_full = data_to(meta)
    asof = min(period['p_end'].isoformat(), last_full) if last_full else None
    store_sql, store_params = _venue_cond(venue)
    with store.conn() as conn:
        daily = _ltv_daily(conn, venue)
        ytd_row = conn.execute(
            "SELECT COUNT(DISTINCT guest_id) n, SUM(revenue) rev FROM receipts "
            "WHERE open_date >= ? AND open_date <= ?" + store_sql,
            [meta['ytd_start'], asof or meta['ytd_start']] + store_params).fetchone()
        by_venue = [] if venue or not asof else conn.execute(
            """
            SELECT g.first_order_store store, COUNT(*) guests, SUM(t.rev) revenue
            FROM guests g JOIN (
                SELECT guest_id, SUM(revenue) rev FROM receipts WHERE open_date <= ?
                GROUP BY guest_id
            ) t ON t.guest_id = g.guest_id
            GROUP BY g.first_order_store ORDER BY revenue DESC
            """, (asof,)).fetchall()
    venues_out = []
    for r in by_venue:
        venues_out.append({
            'store': r['store'],
            'store_name': VENUES.get(r['store'], {}).get('name', r['store']),
            'guests': r['guests'],
            'ltv': round((r['revenue'] or 0) / r['guests']) if r['guests'] else 0,
        })

    guests, checks, revenue = (_ltv_at(daily, date.fromisoformat(asof).toordinal())
                               if asof else (0, 0, 0.0))
    _l, avg_check, per_guest = _ltv_parts(guests, checks, revenue)

    first_day = daily[3][0] if daily[3] else None
    scope_from = date.fromordinal(first_day).isoformat() if first_day and asof else None
    dt_o = date.fromisoformat(last_full).toordinal() if last_full else None
    series = []
    prev = None
    for p in _series_periods(period, n, scope_from):
        row = {'p_start': p['p_start'].isoformat(), 'p_end': p['p_end'].isoformat(),
               'label': p['label']}
        s_o, e_o = p['p_start'].toordinal(), p['p_end'].toordinal()
        if s_o > dt_o:
            row.update({'asof': None, 'state': 'future', 'guests': None, 'checks': None,
                        'revenue': None, 'ltv': None, 'avg_check': None,
                        'checks_per_guest': None, 'delta': None, 'check_effect': None,
                        'frequency_effect': None})
            series.append(row)
            prev = None
            continue
        row_o = min(e_o, dt_o)
        g, k, rev = _ltv_at(daily, row_o)
        cur = _ltv_parts(g, k, rev)
        delta = check_effect = frequency_effect = None
        if prev and prev[0] is not None and cur[0] is not None:
            delta = round(cur[0]) - round(prev[0])
            check_effect = round((cur[1] - prev[1]) * (prev[2] + cur[2]) / 2)
            frequency_effect = delta - check_effect
        row.update({
            'asof': date.fromordinal(row_o).isoformat(),
            'state': 'complete' if e_o <= dt_o else 'partial',
            'guests': g, 'checks': k, 'revenue': round(rev),
            'ltv': round(cur[0]) if cur[0] is not None else None,
            'avg_check': round(cur[1]) if cur[1] is not None else None,
            'checks_per_guest': round(cur[2], 2) if cur[2] is not None else None,
            'delta': delta, 'check_effect': check_effect,
            'frequency_effect': frequency_effect,
        })
        series.append(row)
        prev = cur
    return {
        'asof': asof,
        'lifetime': {
            'guests': guests,
            'revenue': round(revenue),
            'avg_ltv': round(revenue / guests) if guests else 0,
            'checks': checks,
            'avg_check': round(avg_check) if avg_check is not None else None,
            'checks_per_guest': round(per_guest, 2) if per_guest is not None else None,
        },
        'ytd': {
            'guests': ytd_row['n'],
            'revenue': round(ytd_row['rev'] or 0),
            'avg_revenue_per_guest': (round((ytd_row['rev'] or 0) / ytd_row['n'])
                                      if ytd_row['n'] else 0),
        },
        'by_venue': venues_out,
        'series': series,
    }


# ---------------------------------------------------------------- §17 Отток

def _load_visit_revenue(conn, venue=None):
    """{guest_id: (дни визитов, накопленная выручка)} — один SQL на весь отчёт.

    Визит = пара (гость, учётный день), выручка визита — сумма его чеков за день.
    Дни — date.toordinal(): дальше только целые и bisect. cum[i] — выручка гостя
    за визиты 0..i включительно (LTV ушедшего на дату среза). С баром — его чеки.
    """
    store_sql, params = ("WHERE store = ? ", [venue]) if venue else ("", [])
    out = {}
    for r in conn.execute(
            "SELECT guest_id, open_date, SUM(revenue) rev FROM receipts " + store_sql +
            "GROUP BY guest_id, open_date ORDER BY guest_id, open_date", params):
        days, cum = out.setdefault(r['guest_id'], ([], []))
        days.append(date.fromisoformat(r['open_date'][:10]).toordinal())
        cum.append((cum[-1] if cum else 0.0) + (r['rev'] or 0.0))
    return out


def _leaver_buckets(items):
    """«Кто уходит» по CHURN_LEAVER_BUCKETS.

    items — [(визитов за жизнь до среза, выручка до среза, выручка за год до ухода)].
    avg_ltv — средняя выручка гостя группы до среза; damage_month — ущерб от оттока группы:
    выручка её гостей за год до их последнего визита / CHURN_DAMAGE_MONTHS. Итог damage_month
    округляется от несокращённой суммы, поэтому сумма округлённых групп может отличаться от
    него на рубль-два.
    """
    total = len(items)
    buckets = []
    for label, lo, hi in CHURN_LEAVER_BUCKETS:
        group = [(rev, year) for visits, rev, year in items
                 if visits >= lo and (hi is None or visits <= hi)]
        buckets.append({
            'segment': label, 'visits_from': lo, 'visits_to': hi,
            'count': len(group),
            'share_pct': _rate(len(group), total),
            'avg_ltv': round(sum(rev for rev, _y in group) / len(group)) if group else None,
            'damage_month': round(sum(year for _r, year in group) / CHURN_DAMAGE_MONTHS),
        })
    year_total = sum(year for _v, _r, year in items)
    return {'total': total, 'buckets': buckets,
            'damage_month': round(year_total / CHURN_DAMAGE_MONTHS),
            'damage_year': round(year_total)}


def _churn_group(gap0, gap1, visited, x):
    """Графа гостя за период при пороге x — одно правило для счётчиков churn_all и списков churn_guests.

    gap0 — пауза на конец дня накануне периода (None — первый визит гостя в периоде), gap1 —
    пауза на дату среза, visited — заходил ли гость в периоде.
    -> 'stayed' (жив накануне и на срез), 'died' (жив накануне, мёртв на срез), 'reactivated'
       (мёртв накануне, жив на срез), 'bounced' (мёртв накануне, заходил, снова мёртв), 'gone'
       (мёртв накануне и на срез, не заходил), 'new' (первый визит в периоде, жив на срез),
       'new_died' (первый визит в периоде, мёртв на срез).
    """
    if gap0 is None:
        return 'new' if gap1 <= x else 'new_died'
    if gap0 <= x:
        return 'stayed' if gap1 <= x else 'died'
    if gap1 <= x:
        return 'reactivated'
    return 'bounced' if visited else 'gone'


def _newbie_no_return(days, x):
    """Новичок без второго визита в (первый визит, первый + x] — то же окно, что «Возвраты» §5."""
    return len(days) < 2 or days[1] - days[0] > x


def _revenue_year_before_last(days, cum, i1):
    """Выручка гостя за CHURN_DAMAGE_WINDOW_DAYS по его последний визит включительно.

    days/cum — из _load_visit_revenue, i1 — сколько визитов не позже даты среза (последний —
    days[i1 - 1]). Ушедший к срезу давно не приходит, поэтому окно кончается его последним
    визитом, а не датой среза: иначе при пороге 180 полгода окна были бы пустыми.
    """
    lo = bisect_left(days, days[i1 - 1] - (CHURN_DAMAGE_WINDOW_DAYS - 1), 0, i1)
    return cum[i1 - 1] - (cum[lo - 1] if lo else 0.0)


def _slowing_windows(days, i1, asof_o):
    """(визитов в прошлом окне, визитов в последнем окне) для «Стали ходить реже».

    Последнее окно — CHURN_SLOWING_WINDOW_DAYS дней по дату среза включительно, прошлое —
    столько же дней перед ним. days — дни визитов гостя (порядковые), i1 — сколько их не
    позже asof_o. Общая для счётчика churn_all и списка churn_guests: одно правило.
    """
    w = CHURN_SLOWING_WINDOW_DAYS
    recent_lo = bisect_left(days, asof_o - (w - 1), 0, i1)
    prev_lo = bisect_left(days, asof_o - (2 * w - 1), 0, recent_lo)
    return recent_lo - prev_lo, i1 - recent_lo


def _slowing_base(prev, recent):
    """База «Стали ходить реже»: ходил хотя бы раз в месяц (CHURN_SLOWING_MIN_PREV) и ещё ходит."""
    return prev >= CHURN_SLOWING_MIN_PREV and recent >= 1


def _is_slowing(prev, recent):
    """Из базы — те, у кого в последнем окне визитов не больше 1/CHURN_SLOWING_FACTOR прошлых."""
    return _slowing_base(prev, recent) and CHURN_SLOWING_FACTOR * recent <= prev


def _nearest_rank(sorted_values, pct):
    """Перцентиль по ближайшему рангу: значение номер ceil(pct × n / 100) по возрастанию.

    Наименьшее значение, не больше которого — не меньше pct % значений; без интерполяции,
    поэтому ответ — один из настоящих дней. Пустой список — None.
    """
    if not sorted_values:
        return None
    rank = (pct * len(sorted_values) + 99) // 100
    return sorted_values[max(rank, 1) - 1]


def _return_gap_stats(gaps, asof_o):
    """Подсказка к порогу из пауз перед повторными визитами за год до среза (см. churn_all).

    later_than — для каждого порога CHURN_DEAD_DAYS_CHOICES доля пауз длиннее него, %:
    столько возвратов порог успел бы записать в «Ушли». percentiles — паузы, за которые
    возвращается половина и 9 из 10 (CHURN_RETURN_PERCENTILES). Нет возвратов — None.
    """
    gaps = sorted(gaps)
    n = len(gaps)
    return {
        'window_from': date.fromordinal(asof_o - (CHURN_RETURN_WINDOW_DAYS - 1)).isoformat(),
        'window_to': date.fromordinal(asof_o).isoformat(),
        'returns': n,
        'percentiles': [{'pct': pct, 'days': _nearest_rank(gaps, pct)}
                        for pct in CHURN_RETURN_PERCENTILES],
        'later_than': [{'days': x, 'pct': _rate(n - bisect_right(gaps, x), n)}
                       for x in CHURN_DEAD_DAYS_CHOICES],
    }


_CHURN_COUNTS = ('start_alive', 'died', 'reactivated', 'bounced', 'new', 'new_died',
                 'end_alive')
# Ущерб и «Стали ходить реже» в строке ряда (с 2026-10-30): у будущего периода — None.
_CHURN_EXTRA = ('damage_month', 'damage_year', 'slowing', 'slowing_base', 'slowing_pct')


def churn_all(store, period, meta, periods=None, venue=None):
    """Отток (§17) сразу для всех порогов CHURN_DEAD_DAYS_CHOICES — один проход.

    Определения (зеркало — formulas.js и docs/guests.md, §17):
    - жив на дату D: с последнего визита (не позже D) прошло <= X дней; мёртв — > X;
    - data_to — последний полный день данных (см. data_to); дата среза периода
      asof = min(конец периода, data_to); строка ряда: complete (весь период в
      данных), partial (идёт или синк отстал), future (начался позже data_to —
      все числа None, а не нули и не ложные смерти);
    - начало периода — состояние на конец дня накануне его первого дня, поэтому
      живые на конец закрытого периода = живые на начало следующего;
    - графы (каждый гость — ровно в одной; сравниваются только два состояния, и
      гость, умерший 10-го и вернувшийся 12-го, — «остался»): died — жив накануне,
      мёртв на asof; reactivated — был гостем до периода, мёртв накануне, жив на
      asof; bounced — мёртв накануне, заходил в периоде, снова мёртв на asof (в
      балансе не участвует); new — первый визит в периоде, из них new_died — мёртвы
      на asof (бывает, только если X короче периода);
    - баланс: end_alive = start_alive + new + reactivated - (died + new_died);
    - churn_pct = died / start_alive (ушедшие за период / база на начало), 1 знак;
    - newbie_no_return — новые без второго визита в (первый, первый + X]: то же окно
      и то же правило зрелости, что у «Возвратов через N дней» §5 (решение владельца
      2026-10-29), поэтому для месяца это ровно 100% минус «Возвраты через X дней».
      Доля зрелая, только если конец периода + X <= data_to, иначе None (дата —
      newbie_matures_on). Гость, вернувшийся на (X + 1)-й день, здесь «не вернулся»,
      хотя мёртвым ни дня не был: согласованность с «Возвратами» важнее;
    - leavers (только выбранный период): died + new_died по числу визитов за жизнь
      до asof (CHURN_LEAVER_BUCKETS), средний LTV — выручка до asof;
    - ущерб от оттока (решение владельца 2026-10-30): damage_year — выручка ушедших
      (died + new_died) за CHURN_DAMAGE_WINDOW_DAYS по их последний визит, damage_month —
      она же / CHURN_DAMAGE_MONTHS («средний чек × чеков в месяц» статьи); то же по группам
      «Кто уходит». Это ущерб, если ушедшие не вернутся: при коротком пороге часть из них
      вернётся («Вернулись после паузы» следующих периодов);
    - «Стали ходить реже» (скрытый отток): на asof гость жив по порогу X, в прошлом окне
      CHURN_SLOWING_WINDOW_DAYS у него не меньше CHURN_SLOWING_MIN_PREV визитов, в
      последнем — хотя бы один и не больше половины прошлых (_slowing_windows). slowing —
      сколько таких, slowing_base — живые с 3+ визитами в прошлом окне и хоть одним в
      последнем, slowing_pct — доля, %. Это снимок на дату среза, поэтому у неполного
      периода не занижен, в отличие от оттока;
    - return_gaps (только выбранный период, от порога не зависит): паузы перед повторными
      визитами за CHURN_RETURN_WINDOW_DAYS по asof — доля пауз длиннее каждого порога и
      перцентили (_return_gap_stats). У будущего периода — None.

    Первый визит — первый элемент того же списка визитов, что и статусы (а не
    денормализованная guests.first_order_date): один источник, баланс не может
    разойтись. С баром — правило раздела: только его чеки, первый визит — первый
    чек в нём, «ушёл из бара» не значит «ушёл из сети»; data_to — общий для сети.

    periods — длина ряда (None — CHURN_SERIES_DEFAULT для типа периода).
    -> {'data_to', 'scope_from', 'return_gaps',
        'by_days': {X: {'series': [...], 'leavers': {...}}}}
    """
    venue = resolve_venue(venue)
    choices = CHURN_DEAD_DAYS_CHOICES
    n = periods or CHURN_SERIES_DEFAULT.get(period['type'], CHURN_SERIES_DEFAULT['month'])
    last_full = data_to(meta)
    with store.conn() as conn:
        visits = _load_visit_revenue(conn, venue)
    scope_from = None
    if last_full and visits:
        scope_from = date.fromordinal(min(d[0] for d, _c in visits.values())).isoformat()
    plist = _series_periods(period, n, scope_from)
    by_days = {x: {'series': [], 'leavers': _leaver_buckets([])} for x in choices}
    return_gaps = None
    if not plist:
        return {'data_to': last_full, 'scope_from': scope_from, 'return_gaps': return_gaps,
                'by_days': by_days}

    dt_o = date.fromisoformat(last_full).toordinal()
    guests = list(visits.values())
    k = len(choices)
    for idx, p in enumerate(plist):
        s_o, e_o = p['p_start'].toordinal(), p['p_end'].toordinal()
        base = {'p_start': p['p_start'].isoformat(), 'p_end': p['p_end'].isoformat(),
                'label': p['label']}
        if s_o > dt_o:
            for x in choices:
                row = dict(base, asof=None, state='future', churn_pct=None,
                           newbie_no_return=None, newbie_no_return_pct=None,
                           newbie_matures_on=None)
                row.update({name: None for name in _CHURN_COUNTS + _CHURN_EXTRA})
                by_days[x]['series'].append(row)
            continue
        asof_o = min(e_o, dt_o)
        prev_o = s_o - 1
        start = [0] * k
        died = [0] * k
        react = [0] * k
        bounced = [0] * k
        new_died = [0] * k
        end = [0] * k
        no_return = [0] * k
        damage = [0.0] * k
        slow_base = [0] * k
        slowing = [0] * k
        n_new = 0
        selected = idx == len(plist) - 1
        leavers = [[] for _ in choices] if selected else None
        gaps = [] if selected else None
        for days, cum in guests:
            first = days[0]
            if first > asof_o:
                continue
            i1 = bisect_right(days, asof_o)
            gap1 = asof_o - days[i1 - 1]
            # Выручка за год до ухода — только если гость ушёл хотя бы при одном пороге.
            year_rev = None
            i0 = bisect_right(days, prev_o, 0, i1)
            # gap0 = None — первый визит в периоде (не позже среза — проверено выше).
            gap0 = prev_o - days[i0 - 1] if i0 else None
            visited = i1 > i0
            if gap0 is None:
                n_new += 1
            for j, x in enumerate(choices):
                # Графа — общей функцией со списками churn_guests: счёт и список не разойдутся.
                group = _churn_group(gap0, gap1, visited, x)
                if gap1 <= x:
                    end[j] += 1
                if group == 'stayed':
                    start[j] += 1
                elif group == 'died' or group == 'new_died':
                    if group == 'died':
                        start[j] += 1
                        died[j] += 1
                    else:
                        new_died[j] += 1
                    if year_rev is None:
                        year_rev = _revenue_year_before_last(days, cum, i1)
                    damage[j] += year_rev
                    if selected:
                        leavers[j].append((i1, cum[i1 - 1], year_rev))
                elif group == 'reactivated':
                    react[j] += 1
                elif group == 'bounced':
                    bounced[j] += 1
                if gap0 is None and _newbie_no_return(days, x):
                    no_return[j] += 1
            # «Стали ходить реже» — снимок на asof, от новизны гостя не зависит.
            prev_w, recent_w = _slowing_windows(days, i1, asof_o)
            if _slowing_base(prev_w, recent_w):
                drop = _is_slowing(prev_w, recent_w)
                for j, x in enumerate(choices):
                    if gap1 <= x:
                        slow_base[j] += 1
                        if drop:
                            slowing[j] += 1
            if selected:
                # Паузы перед повторными визитами, случившимися за год по asof.
                lo = bisect_left(days, asof_o - (CHURN_RETURN_WINDOW_DAYS - 1), 0, i1)
                for i in range(max(lo, 1), i1):
                    gaps.append(days[i] - days[i - 1])
        for j, x in enumerate(choices):
            matures_o = e_o + x
            mature = matures_o <= dt_o
            row = dict(base)
            row.update({
                'asof': date.fromordinal(asof_o).isoformat(),
                'state': 'complete' if e_o <= dt_o else 'partial',
                'start_alive': start[j], 'died': died[j], 'reactivated': react[j],
                'bounced': bounced[j], 'new': n_new, 'new_died': new_died[j],
                'end_alive': end[j],
                'churn_pct': _rate(died[j], start[j]),
                'newbie_no_return': no_return[j] if mature else None,
                'newbie_no_return_pct': _rate(no_return[j], n_new) if mature else None,
                'newbie_matures_on': date.fromordinal(matures_o).isoformat(),
                'damage_month': round(damage[j] / CHURN_DAMAGE_MONTHS),
                'damage_year': round(damage[j]),
                'slowing': slowing[j], 'slowing_base': slow_base[j],
                'slowing_pct': _rate(slowing[j], slow_base[j]),
            })
            by_days[x]['series'].append(row)
            if selected:
                by_days[x]['leavers'] = _leaver_buckets(leavers[j])
        if selected:
            return_gaps = _return_gap_stats(gaps, asof_o)
    return {'data_to': last_full, 'scope_from': scope_from, 'return_gaps': return_gaps,
            'by_days': by_days}


def churn_view(full, dead_days):
    """Один порог из ответа churn_all — то, что отдаёт маршрут и видит агент.

    Все четыре порога сразу — около 90 тыс. знаков на 60 периодов, мост MCP урезал
    бы ответ (предел 60 тыс.); один порог — около 22 тыс. (замер 2026-10-27).
    """
    part = full['by_days'][dead_days]
    series = part['series']
    return {
        'dead_days': dead_days,
        'choices': list(CHURN_DEAD_DAYS_CHOICES),
        'data_to': full['data_to'],
        'series': series,
        'period': series[-1] if series else None,
        'leavers': part['leavers'],
        # Подсказка к порогу от порога не зависит: доли «позже порога» — сразу для всех.
        'return_gaps': full['return_gaps'],
    }


def churn(store, period, meta, dead_days=CHURN_DEAD_DAYS_DEFAULT, periods=None,
          venue=None):
    """Отток по одному порогу (§17): churn_all + churn_view; порог — parse_dead_days."""
    return churn_view(churn_all(store, period, meta, periods, venue),
                      parse_dead_days(dead_days))


def parse_churn_group(raw):
    """?group= -> имя из CHURN_GUEST_GROUPS (регистр не важен).

    Raises:
        ValueError: группы нет или она неизвестна — текст для ответа 400 (молча пустой список
        выглядел бы как «таких гостей нет»).
    """
    group = str(raw or '').strip().lower()
    if group not in CHURN_GUEST_GROUPS:
        raise ValueError('group — одна из: ' + ', '.join(CHURN_GUEST_GROUPS))
    return group


def parse_leaver_bucket(raw):
    """?bucket= для group=left -> метка из CHURN_LEAVER_BUCKETS или None (все ушедшие).

    «9+» в адресе без кодирования приходит как «9 » (плюс — это пробел), поэтому пробел
    читается как плюс.
    Raises:
        ValueError: неизвестная метка — текст для ответа 400.
    """
    label = str(raw or '').replace(' ', '+').strip()
    if not label:
        return None
    labels = [b[0] for b in CHURN_LEAVER_BUCKETS]
    if label not in labels:
        raise ValueError('bucket — одна из: ' + ', '.join(labels))
    return label


def churn_guests(store, period, meta, group, dead_days=CHURN_DEAD_DAYS_DEFAULT, venue=None,
                 bucket=None):
    """Гости одной плитки «Оттока» поимённо (§17) — те же правила, что счётчики churn_all.

    Плитки кликабельны (решение владельца 2026-10-30: «если мы знаем имена гостей»): каждая
    группа — ровно те гости, что посчитаны в плитке с тем же порогом, периодом и баром:
    - left — «Ушли»: died + new_died (_churn_group); bucket — одна группа «Кто уходит» по числу
      визитов за жизнь до среза (CHURN_LEAVER_BUCKETS);
    - reactivated — «Вернулись после паузы»; new — «Новые гости» (первый визит в периоде);
    - newbie_no_return — «Не вернулись после первого визита» (_newbie_no_return); пока период не
      созрел (конец периода + X позже data_to), списка нет: mature = False, дата — matures_on;
    - slowing — «Стали ходить реже» (_slowing_windows, _is_slowing; жив на срез по порогу).

    Строка гостя: имя, телефон, карта; first_visit и last_visit, recency_days (дней с визита
    на срез), visits_total и ltv (визиты и выручка за жизнь по срез), visits_period и
    revenue_period (с начала периода по срез), revenue_12m (RFM_WINDOW_DAYS по срез, как M в
    RFM), pause_days (пауза перед первым визитом в периоде; у вернувшихся она длиннее порога),
    visits_prev / visits_recent (окна «Стали ходить реже»), damage_month (только у left:
    выручка за год по последний визит / 12). Порядок — самые ценные сверху: left — по ущербу,
    reactivated и new — по выручке в периоде, newbie_no_return — по LTV, slowing — по выручке
    за 12 мес; при равенстве — по guest_id. С баром — только его чеки; имя, телефон и карта —
    общие для сети.
    -> {'asof', 'dead_days', 'group', 'bucket', 'mature', 'matures_on', 'total', 'guests'}
    Raises:
        ValueError: неизвестная группа, корзина или bucket не у group=left (ответ 400).
    """
    venue = resolve_venue(venue)
    x = parse_dead_days(dead_days)
    group = parse_churn_group(group)
    if bucket is not None and group != 'left':
        raise ValueError('bucket — только для group=left («Кто уходит»)')
    out = {'asof': None, 'dead_days': x, 'group': group, 'bucket': bucket, 'mature': True,
           'matures_on': None, 'total': 0, 'guests': []}
    last_full = data_to(meta)
    if not last_full or period['p_start'].isoformat() > last_full:
        return out
    s_o, e_o = period['p_start'].toordinal(), period['p_end'].toordinal()
    dt_o = date.fromisoformat(last_full).toordinal()
    asof_o = min(e_o, dt_o)
    prev_o = s_o - 1
    out['asof'] = date.fromordinal(asof_o).isoformat()
    if group == 'newbie_no_return':
        out['matures_on'] = date.fromordinal(e_o + x).isoformat()
        if e_o + x > dt_o:
            out.update(mature=False, total=None)
            return out
    b_lo, b_hi = next(((lo, hi) for label, lo, hi in CHURN_LEAVER_BUCKETS if label == bucket),
                      (1, None))
    m_from = asof_o - (RFM_WINDOW_DAYS - 1)
    with store.conn() as conn:
        visits = _load_visit_revenue(conn, venue)
        info = {r['guest_id']: r for r in conn.execute(
            "SELECT guest_id, name, phone, card_number FROM guests")}
    picked = []
    for guest_id, (days, cum) in visits.items():
        if days[0] > asof_o:
            continue
        i1 = bisect_right(days, asof_o)
        gap1 = asof_o - days[i1 - 1]
        i0 = bisect_right(days, prev_o, 0, i1)
        gap0 = prev_o - days[i0 - 1] if i0 else None
        prev_w, recent_w = _slowing_windows(days, i1, asof_o)
        if group == 'slowing':
            hit = gap1 <= x and _is_slowing(prev_w, recent_w)
        elif group == 'newbie_no_return':
            hit = gap0 is None and _newbie_no_return(days, x)
        elif group == 'new':
            hit = gap0 is None
        else:
            kind = _churn_group(gap0, gap1, i1 > i0, x)
            hit = kind in ('died', 'new_died') if group == 'left' else kind == group
        if not hit or (group == 'left' and not (i1 >= b_lo and (b_hi is None or i1 <= b_hi))):
            continue
        ltv = cum[i1 - 1]
        before = cum[i0 - 1] if i0 else 0.0
        lo12 = bisect_left(days, m_from, 0, i1)
        rev12 = ltv - (cum[lo12 - 1] if lo12 else 0.0)
        year_rev = _revenue_year_before_last(days, cum, i1) if group == 'left' else None
        g = info.get(guest_id)
        row = {
            'guest_id': guest_id,
            'name': g['name'] if g else None,
            'phone': g['phone'] if g else None,
            'card_number': g['card_number'] if g else None,
            'first_visit': date.fromordinal(days[0]).isoformat(),
            'last_visit': date.fromordinal(days[i1 - 1]).isoformat(),
            'recency_days': gap1,
            'visits_total': i1,
            'ltv': round(ltv),
            'visits_period': i1 - i0,
            'revenue_period': round(ltv - before),
            'revenue_12m': round(rev12),
            'pause_days': days[i0] - days[i0 - 1] if i0 and i1 > i0 else None,
            'visits_prev': prev_w,
            'visits_recent': recent_w,
            'damage_month': round(year_rev / CHURN_DAMAGE_MONTHS) if year_rev is not None else None,
        }
        # Сортировка по несокращённым суммам: округлённые рубли чаще совпадают.
        value = {'left': year_rev, 'reactivated': ltv - before, 'new': ltv - before,
                 'newbie_no_return': ltv, 'slowing': rev12}[group]
        picked.append((-value, guest_id, row))
    picked.sort(key=lambda t: (t[0], t[1]))
    out.update(total=len(picked), guests=[row for _v, _g, row in picked])
    return out


# ---------------------------------------------------------------- §9 Товары

def products(store, period, meta, mode='top', limit=30, venue=None):
    """Товарные отчёты (ТЗ §9) по позициям чеков гостей программы лояльности.

    С баром (venue) — только позиции чеков этого бара; «первые покупки» — что
    гость взял в день первого визита именно в этот бар, «повторные» — позиции
    после него. При равенстве главного показателя порядок — по названию:
    иначе порядок равных зависел бы от плана запроса SQLite. Период — по дату среза
    (meta['asof']).
    """
    p_start, p_end = period['p_start'].isoformat(), meta['asof']
    venue = resolve_venue(venue)
    items_sql, items_params = _venue_cond(venue)
    i_sql, i_params = _venue_cond(venue, 'i.store')
    first_sql, first_params = _first_order_sql(venue)
    with store.conn() as conn:
        if mode == 'top':
            rows = conn.execute(
                f"""
                SELECT dish_name, ROUND(SUM(amount), 1) amount, SUM(revenue) revenue,
                       COUNT(DISTINCT guest_id) guests
                FROM receipt_items WHERE open_date >= ? AND open_date <= ?{items_sql}
                GROUP BY dish_name ORDER BY SUM(revenue) DESC, dish_name LIMIT ?
                """, [p_start, p_end] + items_params + [limit]).fetchall()
        elif mode == 'first':
            # Первые покупки: позиции чеков в день первого заказа гостей,
            # чей первый заказ попал в период.
            rows = conn.execute(
                f"""
                SELECT i.dish_name, ROUND(SUM(i.amount), 1) amount,
                       SUM(i.revenue) revenue, COUNT(DISTINCT i.guest_id) guests
                FROM receipt_items i
                JOIN ({first_sql}) fo ON fo.guest_id = i.guest_id AND i.open_date = fo.f
                WHERE fo.f >= ? AND fo.f <= ?{i_sql}
                GROUP BY i.dish_name
                ORDER BY COUNT(DISTINCT i.guest_id) DESC, i.dish_name
                LIMIT ?
                """, first_params + [p_start, p_end] + i_params + [limit]).fetchall()
        elif mode == 'repeat':
            # Повторные покупки: позиции чеков после дня первого заказа.
            rows = conn.execute(
                f"""
                SELECT i.dish_name, ROUND(SUM(i.amount), 1) amount,
                       SUM(i.revenue) revenue, COUNT(DISTINCT i.guest_id) guests
                FROM receipt_items i
                JOIN ({first_sql}) fo ON fo.guest_id = i.guest_id
                WHERE i.open_date > fo.f
                  AND i.open_date >= ? AND i.open_date <= ?{i_sql}
                GROUP BY i.dish_name ORDER BY SUM(i.revenue) DESC, i.dish_name
                LIMIT ?
                """, first_params + [p_start, p_end] + i_params + [limit]).fetchall()
        else:  # trend: динамика топ-10 товаров за 12 месяцев к концу периода
            end_d = period['p_end']
            start_d = date(end_d.year - 1, end_d.month, 1) + timedelta(days=0)
            top = [r['dish_name'] for r in conn.execute(
                f"""
                SELECT dish_name FROM receipt_items
                WHERE open_date >= ? AND open_date <= ?{items_sql}
                GROUP BY dish_name ORDER BY SUM(revenue) DESC, dish_name LIMIT 10
                """, [start_d.isoformat(), p_end] + items_params).fetchall()]
            if not top:
                return {'mode': 'trend', 'months': [], 'series': []}
            placeholders = ','.join('?' * len(top))
            data = conn.execute(
                f"""
                SELECT substr(open_date, 1, 7) ym, dish_name,
                       ROUND(SUM(amount), 1) amount
                FROM receipt_items
                WHERE open_date >= ? AND open_date <= ?{items_sql}
                  AND dish_name IN ({placeholders})
                GROUP BY ym, dish_name ORDER BY ym
                """, [start_d.isoformat(), p_end] + items_params + top).fetchall()
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

def product_pairs(store, period, meta, scope='lifetime', limit=30, venue=None):
    """Сочетаемость товаров (ТЗ §10): пары в одном чеке.

    Поддержка = чеки с парой / чеки с >= 2 разными позициями;
    уверенность A->B = чеки с парой / чеки с товаром A (в том же охвате).
    С баром (venue) — только чеки этого бара (чек и так всегда в одном баре).
    Оба охвата — по дату среза (meta['asof']): «за всю историю» значит «до даты среза».
    """
    if scope == 'period':
        d_from, d_to = period['p_start'].isoformat(), meta['asof']
    else:
        scope = 'lifetime'
        d_from, d_to = '0000-01-01', meta['asof']
    venue = resolve_venue(venue)
    store_sql, store_params = _venue_cond(venue)
    a_sql, a_params = _venue_cond(venue, 'a.store')
    with store.conn() as conn:
        checks2plus = conn.execute(
            f"""
            SELECT COUNT(*) n FROM (
                SELECT 1 FROM receipt_items
                WHERE open_date >= ? AND open_date <= ?{store_sql}
                GROUP BY open_date, store, order_num, guest_id
                HAVING COUNT(DISTINCT dish_name) >= 2)
            """, [d_from, d_to] + store_params).fetchone()['n']
        dish_checks = {r['dish_name']: r['n'] for r in conn.execute(
            f"""
            SELECT dish_name, COUNT(*) n FROM (
                SELECT DISTINCT open_date, store, order_num, guest_id, dish_name
                FROM receipt_items WHERE open_date >= ? AND open_date <= ?{store_sql})
            GROUP BY dish_name
            """, [d_from, d_to] + store_params).fetchall()}
        pairs = conn.execute(
            f"""
            SELECT a.dish_name da, b.dish_name db, COUNT(*) n
            FROM receipt_items a
            JOIN receipt_items b
              ON a.open_date = b.open_date AND a.store = b.store
             AND a.order_num = b.order_num AND a.guest_id = b.guest_id
             AND a.dish_name < b.dish_name
            WHERE a.open_date >= ? AND a.open_date <= ?{a_sql}
            GROUP BY a.dish_name, b.dish_name
            ORDER BY COUNT(*) DESC LIMIT ?
            """, [d_from, d_to] + a_params + [limit]).fetchall()
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

def venues_analytics(store, period, meta, venue=None):
    """Аналитика по точкам (ТЗ §11).

    С баром (venue) правило «только чеки бара» здесь не работает — отчёт по
    природе межбарный. Поэтому население сужается до гостей бара (хоть один чек
    в нём), а их визиты берутся по ВСЕМ барам сети: откуда они пришли (первая
    точка), какой бар любимый, где ещё бывают и какую долю визитов отдают этому
    бару. guests_total — размер этого населения. Визиты за период — по дату среза
    (meta['asof']); первая и любимая точка и визиты «за всю историю» — по всей истории.
    """
    p_start, p_end = period['p_start'].isoformat(), meta['asof']
    venue = resolve_venue(venue)
    # Фильтр «гости бара» — по guest_id, а не по store: визиты в другие бары нужны.
    pop_cond = "guest_id IN (SELECT guest_id FROM receipts WHERE store = ?)"
    pop_and, pop_where = (" AND " + pop_cond, " WHERE " + pop_cond) if venue else ("", "")
    pop_params = [venue] if venue else []

    def dist(conn, d_from, d_to):
        rows = conn.execute(
            f"""
            SELECT store, COUNT(*) visits, COUNT(DISTINCT guest_id) guests
            FROM (SELECT DISTINCT store, guest_id, open_date FROM receipts
                  WHERE open_date >= ? AND open_date <= ?{pop_and})
            GROUP BY store ORDER BY visits DESC
            """, [d_from, d_to] + pop_params).fetchall()
        total = sum(r['visits'] for r in rows)
        return [{'store': r['store'],
                 'store_name': VENUES.get(r['store'], {}).get('name', r['store']),
                 'visits': r['visits'], 'guests': r['guests'],
                 'share_pct': _pct(r['visits'], total)} for r in rows]

    with store.conn() as conn:
        first_dist = conn.execute(
            f"""
            SELECT first_order_store store, COUNT(*) guests FROM guests
            WHERE first_order_store IS NOT NULL{pop_and}
            GROUP BY first_order_store ORDER BY guests DESC
            """, pop_params).fetchall()
        total_guests = sum(r['guests'] for r in first_dist)
        # Любимая точка гостя: максимум дней-визитов; при равенстве — порядок
        # PHYSICAL_VENUES, затем алфавит (детерминированный tie-break).
        per_guest_store = conn.execute(
            f"""
            SELECT guest_id, store, COUNT(DISTINCT open_date) v
            FROM receipts{pop_where} GROUP BY guest_id, store
            """, pop_params).fetchall()
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
        'guests_total': len(stores_per_guest),
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
    """Карточка гостя (ТЗ §12): все три среза + RFM и статус на дату среза.

    Период и YTD — по дату среза (meta['asof']); «за всю историю» и LTV гостя — по
    сегодняшний день: карточка показывает человека целиком.
    """
    asof = meta['asof']
    p_start, p_end = period['p_start'].isoformat(), asof
    ytd_start = meta['ytd_start']
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


# ------------------------------------------- §15 Зарегистрировались, не купили

# Болванка от автоматического сканирования формы регистрации Orderia: имя
# «Jane Doe» при пустом Telegram. В срезе 2026-08-11 таких 9 из 326.
JUNK_NAME = ('jane', 'doe')


def _is_junk_never_card(row):
    """Мусорная запись: не телефон в поле телефона или болванка сканера."""
    if not row['phone_valid']:
        return True
    return ((row['name'] or '').strip().lower() == JUNK_NAME[0]
            and (row['lastname'] or '').strip().lower() == JUNK_NAME[1]
            and not (row['telegram'] or '').strip())


def _buyer_index(conn):
    """Индексы витрины покупателей для сшивки с картами Orderia.

    Возвращает (guest_ids, card_to_guest, totals):
    - guest_ids   — множество guest_id (канонический телефон);
    - card_to_guest — номер карты (в т.ч. псевдонимы) -> guest_id;
    - totals      — guest_id -> {orders, revenue, first, last, card}.
    """
    guest_ids = set()
    card_to_guest = {}
    totals = {}
    for r in conn.execute(
            "SELECT guest_id, card_number, first_order_date, last_visit_date "
            "FROM guests"):
        guest_ids.add(r['guest_id'])
        totals[r['guest_id']] = {
            'orders': 0, 'revenue': 0.0, 'card': r['card_number'] or '',
            'first': r['first_order_date'], 'last': r['last_visit_date']}
        if r['card_number']:
            card_to_guest.setdefault(r['card_number'], r['guest_id'])
    for r in conn.execute("SELECT alias, guest_id FROM guest_aliases"):
        card_to_guest.setdefault(r['alias'], r['guest_id'])
    for r in conn.execute(
            "SELECT guest_id, COUNT(*) o, SUM(revenue) rev FROM receipts "
            "GROUP BY guest_id"):
        if r['guest_id'] in totals:
            totals[r['guest_id']]['orders'] = r['o']
            totals[r['guest_id']]['revenue'] = r['rev'] or 0.0
    return guest_ids, card_to_guest, totals


def _classify_never_card(row, guest_ids, card_to_guest, totals, ambiguous_cards):
    """Подтверждена ли карта как «не покупавшая», или это ложное срабатывание.

    Orderia считает покупки сама, и её счётчик ошибается: в срезе 2026-08-11
    20 карт из 326 нашлись среди покупателей iiko. Витрина здесь — арбитр,
    потому что чек в iiko это факт продажи, а check_count в Orderia — счётчик.

    Ключи сшивки по убыванию надёжности:
    1. канонический телефон — он же guest_id витрины, совпадение однозначно;
    2. номер карты — ТОЛЬКО если он уникален в срезе Orderia. Номер там не
       первичный ключ: 2002639 выдан трём записям, причём разным людям. Привязка
       по неуникальному номеру подтянула бы к одному гостю чужие карты и
       посчитала бы его выручку несколько раз.

    Возвращает (kind, guest_id): kind — 'confirmed' | 'same_card' | 'other_card'.
    - same_card  — тот же номер карты, и по нему в iiko есть чеки: счётчик
      Orderia врёт (чаще всего покупка в день регистрации его не увеличивает);
    - other_card — телефон известен витрине, но покупки шли по ДРУГОЙ карте:
      человек завёл вторую карту, старая работала.
    """
    phone = row['phone_canon'] or ''
    card = row['card_number'] or ''
    gid = None
    if phone and phone in guest_ids:
        gid = phone
    elif card and card not in ambiguous_cards:
        gid = card_to_guest.get(card)
    if not gid:
        return 'confirmed', None
    return ('same_card' if totals.get(gid, {}).get('card') == card
            else 'other_card'), gid


def never_buyers(store, period, meta, months=24, include_list=False):
    """Зарегистрировались и ни разу не купили (§15, источник — Orderia).

    Закрывает дыру, о которой сказано в §1: OLAP iiko видит гостя только с
    первой покупкой, поэтому слой «карта выдана, покупок нет» витрине не
    виден в принципе. Orderia отдаёт его эндпоинтом never.php.

    Каждая карта сверяется с витриной (см. _classify_never_card) — в отчёт как
    «подтверждённые» идут только те, кого в чеках iiko действительно нет.

    Конверсия периода считается честно, потому что теперь есть знаменатель:
    зарегистрировались(P) = купившие с датой регистрации в P + подтверждённые
    некупившие с датой регистрации в P. Считается только если период целиком
    внутри покрытия Orderia — на более ранних периодах некупивших в источнике
    нет, и конверсия ложно вышла бы 100%. Период — по дату среза (meta['asof']),
    как регистрации на «Росте базы».
    """
    p_start, p_end = period['p_start'].isoformat(), meta['asof']
    src = store.never_sync_state()

    with store.conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT source_id, card_number, name, lastname, phone_raw, "
            "phone_canon, telegram, balance, registered_at, phone_valid "
            "FROM never_cards")]
        guest_ids, card_to_guest, totals = _buyer_index(conn)
        bought_in_period = conn.execute(
            "SELECT COUNT(*) n FROM guests WHERE registration_source='iiko' "
            "AND registration_date >= ? AND registration_date <= ?",
            (p_start, p_end)).fetchone()['n']

    # Номера карт, встречающиеся в срезе Orderia больше одного раза: по ним
    # нельзя привязываться к гостю (см. _classify_never_card).
    card_counts = {}
    for r in rows:
        card = r['card_number'] or ''
        if card:
            card_counts[card] = card_counts.get(card, 0) + 1
    ambiguous_cards = {c for c, n in card_counts.items() if n > 1}

    confirmed, false_pos = [], []
    fp_revenue_by_guest = {}
    for r in rows:
        kind, gid = _classify_never_card(r, guest_ids, card_to_guest, totals,
                                         ambiguous_cards)
        if kind == 'confirmed':
            confirmed.append(r)
        else:
            t = totals.get(gid, {})
            # Выручка копится по ГОСТЮ, а не по строке: на одного человека может
            # указывать несколько карт Orderia, и суммирование по строкам
            # посчитало бы его выручку дважды.
            fp_revenue_by_guest[gid] = round(t.get('revenue', 0.0))
            false_pos.append({
                'card_number': r['card_number'],
                'kind': kind,
                'iiko_card': t.get('card') or '',
                'orders': t.get('orders', 0),
                'revenue': round(t.get('revenue', 0.0)),
                'first_order_date': t.get('first'),
                'last_visit_date': t.get('last'),
                'registered_at': r['registered_at'],
            })

    junk = [r for r in confirmed if _is_junk_never_card(r)]
    junk_ids = {r['source_id'] for r in junk}
    real = [r for r in confirmed if r['source_id'] not in junk_ids]

    reg_dates = [r['registered_at'] for r in rows if r['registered_at']]
    cov_from = min(reg_dates) if reg_dates else None
    cov_to = max(reg_dates) if reg_dates else None

    # Помесячная динамика подтверждённых (без мусора), от свежих к старым.
    by_month = {}
    for r in real:
        ym = (r['registered_at'] or '')[:7]
        if ym:
            by_month[ym] = by_month.get(ym, 0) + 1
    months_rows = [{'month': ym, 'count': by_month[ym]}
                   for ym in sorted(by_month.keys(), reverse=True)[:months]]
    months_rows.reverse()

    by_balance = {}
    for r in real:
        by_balance[r['balance']] = by_balance.get(r['balance'], 0) + 1

    in_period = [r for r in real if p_start <= (r['registered_at'] or '') <= p_end]
    registered_total = bought_in_period + len(in_period)

    # Знаменатель корректен по построению: зарегистрировавшийся либо в итоге
    # купил (и лежит в guests с датой регистрации), либо не купил и лежит в
    # never_cards. Третьего не дано, поэтому сумма — это все регистрации периода.
    #
    # Но только внутри покрытия Orderia. Самая ранняя карта в списке —
    # 2024-02-29 на проде, а регистрации в витрине начинаются с 2017 года: для
    # старых периодов некупивших в источнике просто нет, и конверсия ложно
    # вышла бы 100%. Порог берём по МЕСЯЦУ самой ранней карты: внутри месяца
    # период стартует раньше конкретной даты, и посуточное сравнение отключало
    # бы конверсию на первом же валидном месяце.
    #
    # Оговорка: сам порог эвристический. Список Orderia — снимок тех, кто НЕ
    # купил до сих пор; по нему нельзя отличить «до 2024-02 система не вела
    # карты» от «все, кто регистрировался раньше, в итоге что-то купили».
    coverage_month_start = f"{cov_from[:7]}-01" if cov_from else None
    conversion = (_pct(bought_in_period, registered_total)
                  if coverage_month_start and p_start >= coverage_month_start
                  and registered_total else None)

    out = {
        'source': {
            'configured': src['status'] != 'never_run' or bool(rows),
            'status': src['status'],
            'fetched_at': src['fetched_at'],
            'error': src['error'],
            'reported': src['total'] if src['total'] is not None else len(rows),
        },
        'coverage': {'from': cov_from, 'to': cov_to},
        'totals': {
            'reported': len(rows),
            'confirmed': len(real),
            'junk': len(junk),
            'false_positives': len(false_pos),
            'fp_same_card': sum(1 for f in false_pos if f['kind'] == 'same_card'),
            'fp_other_card': sum(1 for f in false_pos if f['kind'] == 'other_card'),
            'fp_guests': len(fp_revenue_by_guest),
            'fp_revenue': sum(fp_revenue_by_guest.values()),
            'reachable_telegram': sum(1 for r in real if (r['telegram'] or '').strip()),
        },
        'period': {
            'registered_total': registered_total,
            'bought': bought_in_period,
            'never': len(in_period),
            'conversion_pct': conversion,
            'conversion_available': conversion is not None,
        },
        'by_month': months_rows,
        'by_balance': [{'balance': b, 'count': n}
                       for b, n in sorted(by_balance.items(),
                                          key=lambda kv: (kv[0] is None, kv[0]))],
        'false_positives': sorted(false_pos, key=lambda f: -f['revenue'])[:20],
    }
    if include_list:
        out['guests'] = sorted(
            [{'card_number': r['card_number'],
              'name': ' '.join(x for x in (r['name'], r['lastname']) if x).strip(),
              'phone': r['phone_raw'], 'telegram': r['telegram'],
              'registered_at': r['registered_at'], 'balance': r['balance']}
             for r in real],
            key=lambda g: g['registered_at'] or '', reverse=True)
    return out


# ---------------------------------------------------------------- §14 Сводка

def _summary_never(never):
    """Блок never сводки из §15; never=None — выбран бар, Orderia его не знает.

    Карта без покупок к бару не привязана (Orderia бара не передаёт, а чека,
    по которому его можно было бы определить, у такой карты нет), поэтому с
    баром блок недоступен с причиной reason='venue', и сводка берёт регистрации
    и конверсию из витрины, как без Orderia.
    """
    if never is None:
        return {'available': False, 'reason': 'venue', 'source_status': None,
                'registered_total': None, 'bought': None, 'never_period': None,
                'never_total': None, 'conversion_pct': None}
    return {
        # available = срез Orderia есть и период внутри его покрытия
        'available': never['period']['conversion_available'],
        'reason': None,
        'source_status': never['source']['status'],
        'registered_total': never['period']['registered_total'],
        'bought': never['period']['bought'],
        'never_period': never['period']['never'],
        'never_total': never['totals']['confirmed'],
        'conversion_pct': never['period']['conversion_pct'],
    }


def summary(store, period, meta, venue=None):
    """Дашборд маркетолога (ТЗ §14): сводные показатели из готовых функций.

    Регистрации и конверсия берутся из §15, если данные Orderia есть: только там
    известен полный знаменатель. Без Orderia остаётся прежнее поведение — виден
    лишь тот, кто купил, и конверсия обречена быть около 100% (показывается
    справочно). Признак `never.available` говорит UI, какой из двух случаев.

    С баром (venue) все показатели — по этому бару (правила — в докстрингах
    частей). На бар не делятся: §15 (never.available=False, reason='venue') и
    «Регистраций на точку» — сравнение баров, с баром пустой список.
    """
    p_start, p_end = period['p_start'].isoformat(), meta['asof']
    venue = resolve_venue(venue)
    growth = base_growth(store, period, meta, venue)
    act = activity(store, period, meta, venue)
    freq = frequency(store, period, meta, venue)
    ltv_block = ltv(store, period, meta, venue)
    never = None if venue else never_buyers(store, period, meta)
    store_sql, store_params = _venue_cond(venue)
    with store.conn() as conn:
        chk = conn.execute(
            "SELECT COUNT(*) orders, SUM(revenue) rev FROM receipts "
            "WHERE open_date >= ? AND open_date <= ?" + store_sql,
            [p_start, p_end] + store_params).fetchone()
        chk_ytd = conn.execute(
            "SELECT COUNT(*) orders, SUM(revenue) rev FROM receipts "
            "WHERE open_date >= ? AND open_date <= ?" + store_sql,
            [meta['ytd_start'], p_end] + store_params).fetchone()
        regs_by_store = [] if venue else conn.execute(
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
        'avg_ltv_asof': ltv_block['asof'],
        'registrations_by_store': [
            {'store': r['store'],
             'store_name': VENUES.get(r['store'], {}).get('name', r['store']),
             'count': r['n']} for r in regs_by_store],
        'never': _summary_never(never),
    }
