# -*- coding: utf-8 -*-
"""Детали внутри карточки дашборда: секции-вкладки раскрытой карточки.

Зачем модуль
------------
Клик по карточке раскрывал только список «По сотрудникам». Владелец хочет внутри
каждой карточки свою информацию: у розлива - топ сортов по литрам, у выручки - дни
и бары, у наценки - кто её тянет вниз, и т.д. Здесь лежит реестр «метрика ->
секции» и чистые функции, которые считают секции из СТРОК ЕДИНОГО OLAP-ЗАПРОСА
дашборда (routes/dashboard.py::load_dashboard_sales). Новых обращений к iiko нет:
в строке уже есть название позиции, категория, страна, учётный день, бар, id чека,
карта гостя и деньги. Две секции считаются из других источников и грузятся лениво
по клику на вкладку: «Литры» (проводки кегов, как на /draft) и «Краны»
(data/taps_data.json).

Инвариант
---------
Итог секции равен числу на карточке по построению: суммы, чеки, маржа, наценка,
скидки, локал/импорт и карта считаются теми же хелперами DashboardMetrics на
подмножествах тех же строк, а «Итого» берётся из calculate_metrics по всем строкам.
Строки «Остальные (N)» = итог минус показанные, поэтому топ-5 + «Остальные» =
«Итого» всегда, даже если часть строк никуда не отнесена (например, чеки без
карты в топе гостей). Отношения (средний чек, наценка, доля) не складываются: у них
«Итого» - значение карточки с подсказкой, что это не среднее строк.

Формат секции (один рендер на клиенте)
--------------------------------------
    {id, title (подпись вкладки), heading, formula (текст для пользователя),
     format: money|number|percent|liters, additive: bool,
     rows: [{name, value, share?, sub?}] (не больше TOP_N),
     rest: {name, value, share?} | None, total: {name, value, hint?} | None,
     note: str | None, link: {href, label} | None, lazy: bool, error: str | None}

Округление как в routes/employee.py::_breakdown_row: деньги и чеки до целого,
доли и наценки до 0,1, литры до 0,1.

Формулы (словами, они же уходят в поле formula)
-----------------------------------------------
    Выручка группы     = Σ DishDiscountSumInt по строкам группы
    Чеки группы        = число уникальных UniqOrderId.Id среди строк группы
    Маржа              = Σ (DishDiscountSumInt - ProductCostBase.ProductCost)
    Наценка            = (Σ выручка - Σ себестоимость) / Σ себестоимость × 100 (агрегатом,
                         как строка «Итого» в iiko; строки без себестоимости - выручкой)
    Списания           = Σ DiscountSum (все скидки чека, как и сама карточка)
    Доля               = значение строки / итог секции × 100
    Сорт розлива       = название блюда без объёма и «с собой» (extract_beer_info):
                         «ФестХаус Хеллес (0,5)» и «(0,3)» - один сорт
    Локал / импорт     = страна DishForeignName «Россия» / всё остальное и пусто
    Гость              = непустой Delivery.CustomerCardNumber; чеки гостя - уникальные
                         заказы, визиты - уникальные учётные дни
    Литры кега         = Σ Amount.Out проводок SESSION_WRITEOFF (core/draft_kegs.py)
    Активность крана   = активных дней / дней периода × 100 (core/taps_manager.py)

Файлы
-----
routes/dashboard.py - эндпоинт POST /api/dashboard-card-details; static/js/dashboard/
modules/analytics.js - вкладки и рендер; docs/dashboard.md - раздел «Детали внутри
карточки»; tests/test_dashboard_card_details.py.
"""

import re
import traceback
from datetime import datetime, timedelta
from functools import partial

from core.dashboard_analysis import DashboardMetrics
from core.draft_analysis import extract_beer_info

# Сколько строк показывать в секции; остальное сворачивается в «Остальные (N)».
TOP_N = 5

# Порог для «слабой наценки»: позиция должна давать хотя бы 1% выручки разреза,
# иначе в список попадают единичные продажи (урок с техаккаунтом при 370% наценки).
LOW_MARKUP_MIN_SHARE = 0.01

# «Дни» показываются полностью, если период не длиннее недели; дальше - топ.
DAYS_SHOW_ALL_UPTO = 7

# id карточек дашборда в порядке config.js (проверяется тестом).
METRIC_IDS = [
    'revenue', 'checks', 'averageCheck', 'markupPercent', 'draftShare', 'revenueDraft',
    'markupDraft', 'packagedShare', 'revenuePackaged', 'markupPackaged', 'kitchenShare',
    'revenueKitchen', 'markupKitchen', 'profit', 'loyaltyWriteoffs', 'tapActivity',
    'cardChecks', 'nocardChecks', 'cardChecksShare', 'cardRevenue',
]

# Ленивые секции: в bulk-ответе метрики отдаются заглушкой, грузятся по клику.
LAZY_SECTIONS = ('draft_liters', 'taps')

# Метрики, у которых ВСЕ секции ленивые: их bulk-ответ - только заглушки, строки
# единого OLAP-запроса не нужны, и роут в iiko не ходит (тест сверяет с реестром).
LAZY_ONLY_METRICS = frozenset({'tapActivity'})

WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

# Категории карточек: ключ -> (подпись, значение DishGroup.TopParent или None = прочее).
CATEGORIES = [
    ('draft', 'Розлив', DashboardMetrics.TOP_PARENT_DRAFT),
    ('bottles', 'Фасовка', DashboardMetrics.TOP_PARENT_BOTTLES),
    ('kitchen', 'Кухня', DashboardMetrics.TOP_PARENT_KITCHEN),
    ('other', 'Прочее', None),
]
CATEGORY_LABEL = {key: label for key, label, _ in CATEGORIES}
CATEGORY_TOP_PARENT = {key: top_parent for key, _label, top_parent in CATEGORIES}

# Единица штук/порций в подписях по категории.
UNIT_WORD = {'draft': 'порц.', 'bottles': 'шт', 'kitchen': 'порц.', 'other': 'шт', None: 'шт'}

_calc = DashboardMetrics()


# ---------- базовые хелперы ----------

def _num(value):
    """Число из строки OLAP: None и мусор -> 0.0 (как _sum_revenue в DashboardMetrics)."""
    if not value:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _round(value, fmt):
    """Округление для показа: деньги/чеки до целого, проценты и литры до 0,1."""
    if value is None:
        return None
    if fmt in ('money', 'number'):
        return int(round(value))
    return round(value, 1)


def _fmt_money(value):
    return f"{int(round(value)):,}".replace(',', ' ') + ' ₽'


def _fmt_int(value):
    return f"{int(round(value)):,}".replace(',', ' ')


def _fmt_pct(value):
    return f"{value:.1f}%".replace('.', ',')


def normalize_date(value):
    """'2026-08-24', '2026-08-24T00:00', '24.08.2026', '2026.08.24' -> '2026-08-24'; иначе None."""
    if value is None:
        return None
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    text = str(value).strip()
    if not text:
        return None
    match = re.match(r'^(\d{4})[-.](\d{2})[-.](\d{2})', text)
    if match:
        return f'{match.group(1)}-{match.group(2)}-{match.group(3)}'
    match = re.match(r'^(\d{2})\.(\d{2})\.(\d{4})', text)
    if match:
        return f'{match.group(3)}-{match.group(2)}-{match.group(1)}'
    return None


def _parse_day(iso):
    try:
        return datetime.strptime(iso, '%Y-%m-%d')
    except (TypeError, ValueError):
        return None


def day_label(iso):
    """'2026-08-24' -> 'Пн 24.08'."""
    day = _parse_day(iso)
    if day is None:
        return str(iso)
    return f"{WEEKDAYS[day.weekday()]} {day.strftime('%d.%m')}"


def category_of(record):
    """Ключ категории строки по DishGroup.TopParent (как в calculate_metrics)."""
    top = record.get('DishGroup.TopParent', '')
    for key, _label, top_parent in CATEGORIES:
        if top_parent is not None and top == top_parent:
            return key
    return 'other'


def _rows_of(records, category):
    if category is None:
        return records
    return [r for r in records if category_of(r) == category]


def draft_sort_name(dish_name):
    """Сорт розлива: название блюда без объёма и «с собой»; пустое имя остаётся пустым."""
    name = (dish_name or '').strip()
    if not name:
        return ''
    return extract_beer_info(name)[0] or name


def _aggregate(records, key_fn):
    """Один проход по строкам: {ключ: {name, revenue, cost, units, discount, orders, dates}}."""
    groups = {}
    for record in records:
        key = key_fn(record)
        if key is None or key == '':
            continue
        group = groups.get(key)
        if group is None:
            group = groups[key] = {
                'name': key, 'revenue': 0.0, 'cost': 0.0, 'units': 0.0, 'discount': 0.0,
                'orders': set(), 'dates': set(),
            }
        group['revenue'] += _num(record.get('DishDiscountSumInt'))
        group['cost'] += _num(record.get('ProductCostBase.ProductCost'))
        group['units'] += _num(record.get('DishAmountInt'))
        group['discount'] += _num(record.get('DiscountSum'))
        order_id = record.get('UniqOrderId.Id')
        if order_id:
            group['orders'].add(str(order_id))
        day = normalize_date(record.get('OpenDate.Typed'))
        if day:
            group['dates'].add(day)
    for group in groups.values():
        group['margin'] = group['revenue'] - group['cost']
        group['markup'] = ((group['revenue'] - group['cost']) / group['cost'] * 100
                           if group['cost'] > 0 else None)
        group['checks'] = len(group['orders'])
        group['visits'] = len(group['dates'])
    return groups


def _section(sid, title, heading, formula, fmt, rows, *, additive=True, total=None,
             rest=None, note=None, link=None, lazy=False, error=None):
    return {
        'id': sid, 'title': title, 'heading': heading, 'formula': formula,
        'format': fmt, 'additive': additive, 'rows': rows, 'rest': rest,
        'total': total, 'note': note, 'link': link, 'lazy': lazy, 'error': error,
    }


def _rest_row(rows, raw_values, total_value, fmt, hidden, base, rest_label, unassigned_label):
    """Строка «Остальные (N)» / «Без разбивки» складываемой секции.

    Остаток считается по УЖЕ ОКРУГЛЁННЫМ значениям строк и итога, поэтому на экране
    Σ строк + остаток == «Итого» точно. Если все значения целые (чеки, штуки),
    любое расхождение реально и строка рисуется всегда; у денег и литров строки
    округлялись, и остаток в пределах «единица на строку» - шум округления, его не
    показываем. Отрицательный остаток - сигнал задвоения (например, чек в двух барах).
    """
    total_rounded = _round(total_value, fmt)
    rest_value = total_rounded - sum(r['value'] for r in rows)
    integral = (float(total_value).is_integer()
                and all(float(v or 0).is_integer() for v in raw_values))
    if integral:
        drift = 0
    elif fmt in ('money', 'number'):
        drift = len(rows)
    else:
        drift = 0.1 * max(len(rows), 1) + 1e-9
    if hidden <= 0 and abs(rest_value) <= drift:
        return None
    label = f'{rest_label} ({hidden})' if hidden > 0 else unassigned_label
    rest = {'name': label, 'value': _round(rest_value, fmt)}
    if base and base > 0:
        rest['share'] = round(rest_value / base * 100, 1)
    return rest


def _top_section(sid, title, heading, formula, fmt, items, value_key, total_value, *,
                 additive=True, share_base=None, sub_fn=None, total_name='Итого',
                 total_hint=None, reverse=True, note=None, link=None, top_n=TOP_N,
                 rest_label='Остальные', unassigned_label='Без разбивки', name_fn=None):
    """Топ строк по значению, «Остальные» и «Итого».

    additive: строки складываются - «Остальные» = итог минус показанные (по
    округлённым значениям, см. _rest_row), share от share_base (по умолчанию от
    итога). Для отношений «Остальные» не рисуются, а «Итого» - значение карточки.
    """
    ordered = sorted(items, key=lambda it: (it[value_key] if it[value_key] is not None else 0),
                     reverse=reverse)
    # Период без данных: у складываемых секций строки из нулей - шум, клиент покажет
    # «Нет данных». У отношений нулевые строки - содержание (краны с нулём активных дней).
    if additive and all(abs(it[value_key] or 0) < 1e-9 for it in ordered) and not (total_value or 0):
        ordered = []
    top = ordered[:top_n]
    base = share_base if share_base is not None else total_value
    rows = []
    for item in top:
        row = {'name': name_fn(item) if name_fn else item['name'], 'value': _round(item[value_key], fmt)}
        if additive and base and base > 0:
            row['share'] = round(item[value_key] / base * 100, 1)
        sub = sub_fn(item) if sub_fn else None
        if sub:
            row['sub'] = sub
        rows.append(row)

    rest = None
    if additive and total_value is not None:
        rest = _rest_row(rows, [it[value_key] for it in top], total_value, fmt,
                         len(ordered) - len(top), base, rest_label, unassigned_label)

    total = None
    if total_value is not None:
        total = {'name': total_name, 'value': _round(total_value, fmt)}
        if total_hint:
            total['hint'] = total_hint
    return _section(sid, title, heading, formula, fmt, rows, additive=additive,
                    total=total, rest=rest, note=note, link=link)


# ---------- контекст расчёта ----------

class DetailsContext:
    """Строки периода + промежуточные агрегаты, считающиеся один раз на запрос."""

    def __init__(self, all_sales_data, venue_key, date_from, date_to, daily_plans=None):
        self.records = (all_sales_data or {}).get('data') or []
        self.venue_key = venue_key or 'all'
        self.date_from = date_from
        self.date_to = date_to
        self.daily_plans = daily_plans or {}
        self.metrics = _calc.calculate_metrics({'data': self.records})
        self._by_day = None
        self._by_store = None
        self._dishes = {}

    # Дни периода включительно: делитель для средних по дням недели и правило «все дни».
    def period_days(self):
        start, end = _parse_day(self.date_from), _parse_day(self.date_to)
        if start is None or end is None or end < start:
            return None
        return (end - start).days + 1

    def by_day(self):
        """{'YYYY-MM-DD': calculate_metrics по строкам дня} - те же формулы, что у карточки."""
        if self._by_day is None:
            groups = {}
            for record in self.records:
                day = normalize_date(record.get('OpenDate.Typed'))
                if day:
                    groups.setdefault(day, []).append(record)
            self._by_day = {day: _calc.calculate_metrics({'data': rows}) for day, rows in groups.items()}
        return self._by_day

    def by_store(self):
        """{Store.Name: calculate_metrics по строкам бара}."""
        if self._by_store is None:
            groups = {}
            for record in self.records:
                store = str(record.get('Store.Name') or '').strip()
                if store:
                    groups.setdefault(store, []).append(record)
            self._by_store = {store: _calc.calculate_metrics({'data': rows}) for store, rows in groups.items()}
        return self._by_store

    def dishes(self, category, key='dish'):
        """Агрегат по позициям категории: key 'dish' - DishName как есть, 'sort' - сорт розлива."""
        cache_key = (category, key)
        if cache_key not in self._dishes:
            if key == 'sort':
                memo = {}

                def key_fn(record):
                    name = str(record.get('DishName') or '').strip()
                    if name not in memo:
                        memo[name] = draft_sort_name(name)
                    return memo[name]
            else:
                def key_fn(record):
                    return str(record.get('DishName') or '').strip()
            self._dishes[cache_key] = _aggregate(_rows_of(self.records, category), key_fn)
        return self._dishes[cache_key]

    def category_metric(self, category, key):
        """Значение метрики категории из calculate_metrics: draft_revenue, bottles_markup, ..."""
        return self.metrics.get(f'{category}_{key}', 0.0)


# ---------- значения для групповых секций (дни, бары) ----------

# spec: ключ calculate_metrics, формат, складывается ли, множитель для показа.
GROUP_VALUES = {
    'revenue': ('total_revenue', 'money', True),
    'checks': ('total_checks', 'number', True),
    'avg_check': ('avg_check', 'money', False),
    'kitchen_revenue': ('kitchen_revenue', 'money', True),
    'margin': ('total_margin', 'money', True),
    'discount': ('loyalty_points_written_off', 'money', True),
    'card_checks': ('card_checks', 'number', True),
    'nocard_checks': ('nocard_checks', 'number', True),
    'card_share': ('card_checks_share', 'percent', False),
    'card_revenue': ('card_revenue', 'money', True),
}

GROUP_FORMULAS = {
    'revenue': 'Выручка = Σ DishDiscountSumInt по строкам разреза; сумма строк = карточка',
    'checks': 'Чеки = число уникальных заказов (UniqOrderId.Id) в разрезе; чек принадлежит одному дню и бару, сумма = карточка',
    'avg_check': 'Средний чек = выручка разреза / чеки разреза. «Итого» - по всем чекам периода, не среднее строк',
    'kitchen_revenue': 'Выручка кухни = Σ DishDiscountSumInt по строкам группы «ЕДА» в разрезе',
    'margin': 'Прибыль = Σ (выручка - себестоимость) по строкам разреза; сумма строк = карточка',
    'discount': 'Списания = Σ DiscountSum по строкам разреза (все скидки чека, как и карточка)',
    'card_checks': 'Чек с картой = непустой номер карты лояльности хотя бы в одной строке чека',
    'nocard_checks': 'Чеки без карты = все чеки разреза - чеки с картой',
    'card_share': 'Доля = чеки с картой / все чеки разреза × 100. «Итого» - по всему периоду, не среднее строк',
    'card_revenue': 'Выручка по картам = Σ DishDiscountSumInt строк чеков с картой лояльности',
}

GROUP_TOTAL_HINTS = {
    'avg_check': 'Итог по всем чекам периода, как на карточке. Это не среднее строк выше',
    'card_share': 'Доля по всем чекам периода, как на карточке. Это не среднее строк выше',
}


def _group_sub(value, m, plan=None):
    """Подпись под строкой группового разреза."""
    if value == 'revenue':
        if plan:
            pct = m['total_revenue'] / plan * 100 if plan > 0 else 0.0
            return f"план {_fmt_money(plan)} · {pct:.0f}%"
        return f"{_fmt_int(m['total_checks'])} чек."
    if value == 'checks':
        return f"средний чек {_fmt_money(m['avg_check'])}"
    if value == 'kitchen_revenue':
        return f"{_fmt_pct(m['kitchen_share'])} выручки"
    if value == 'margin':
        return f"наценка {_fmt_pct(m['avg_markup'] * 100)}"
    if value == 'card_checks':
        return f"из {_fmt_int(m['total_checks'])} чек."
    if value == 'nocard_checks':
        return f"из {_fmt_int(m['total_checks'])} чек."
    if value == 'card_share':
        return f"с картой {_fmt_int(m['card_checks'])} из {_fmt_int(m['total_checks'])}"
    if value == 'card_revenue':
        return f"{_fmt_int(m['card_checks'])} чек. с картой"
    return f"{_fmt_int(m['total_checks'])} чек."


def sec_days(ctx, value='revenue', order='desc'):
    """Дни периода: все дни хронологически, если период ≤ 7 дней, иначе топ по значению."""
    key, fmt, additive = GROUP_VALUES[value]
    by_day = ctx.by_day()
    items = []
    for day, m in by_day.items():
        plan = None
        if value == 'revenue':
            plan = _num((ctx.daily_plans.get(day) or {}).get(ctx.venue_key))
        items.append({'name': day, 'value': m[key], 'sub': _group_sub(value, m, plan)})
    total_value = ctx.metrics[key]
    period_days = ctx.period_days()
    show_all = period_days is not None and period_days <= DAYS_SHOW_ALL_UPTO
    formula = GROUP_FORMULAS[value]
    heading = 'По дням' if show_all else ('5 худших дней' if order == 'asc' else 'Топ-5 дней')
    if show_all:
        # Хронологически, без обрезки: строк не больше 7.
        rows = []
        for item in sorted(items, key=lambda it: it['name']):
            row = {'name': day_label(item['name']), 'value': _round(item['value'], fmt), 'sub': item['sub']}
            if additive and total_value > 0:
                row['share'] = round(item['value'] / total_value * 100, 1)
            rows.append(row)
        total = {'name': 'Итого', 'value': _round(total_value, fmt)}
        if value in GROUP_TOTAL_HINTS:
            total['hint'] = GROUP_TOTAL_HINTS[value]
        rest = None
        if additive:
            # Строки без учётного дня (в живых данных их нет) - отдельной строкой.
            rest = _rest_row(rows, [it['value'] for it in items], total_value, fmt, 0,
                             total_value, 'Остальные дни', 'Без даты')
        return _section('days', 'Дни', heading, formula, fmt, rows, additive=additive,
                        total=total, rest=rest)
    return _top_section('days', 'Дни', heading, formula, fmt, items, 'value', total_value,
                        additive=additive, sub_fn=lambda it: it['sub'],
                        name_fn=lambda it: day_label(it['name']),
                        total_hint=GROUP_TOTAL_HINTS.get(value), reverse=(order != 'asc'),
                        rest_label='Остальные дни', unassigned_label='Без даты')


def sec_weekdays(ctx, value='revenue'):
    """Среднее за день недели: Σ по таким дням / число таких календарных дней периода."""
    key, fmt, _additive = GROUP_VALUES[value]
    start = _parse_day(ctx.date_from)
    period_days = ctx.period_days()
    if start is None or period_days is None:
        return _section('weekdays', 'Дни недели', 'По дням недели', GROUP_FORMULAS[value], fmt, [],
                        additive=False)
    calendar_count = [0] * 7
    for offset in range(period_days):
        calendar_count[(start + timedelta(days=offset)).weekday()] += 1
    sums = [0.0] * 7
    for day, m in ctx.by_day().items():
        parsed = _parse_day(day)
        if parsed is not None:
            sums[parsed.weekday()] += m[key]
    total_value = ctx.metrics[key]
    rows = []
    for index, label in enumerate(WEEKDAYS):
        if calendar_count[index] == 0 or not total_value:
            continue
        avg = sums[index] / calendar_count[index]
        row = {'name': label, 'value': _round(avg, fmt),
               'sub': f"{calendar_count[index]} дн. · всего {_fmt_int(sums[index]) if fmt == 'number' else _fmt_money(sums[index])}"}
        if total_value > 0:
            row['share'] = round(sums[index] / total_value * 100, 1)
        rows.append(row)
    formula = ('Среднее за день недели = Σ по всем таким дням периода / число таких календарных '
               'дней (день без продаж считается нулём); доля - от итога периода')
    total = {'name': 'Итого за период', 'value': _round(total_value, fmt),
             'hint': 'Итог периода с карточки; строки выше - средние за день'}
    return _section('weekdays', 'Дни недели', 'Среднее по дням недели', formula, fmt, rows,
                    additive=False, total=total)


def sec_stores(ctx, value='revenue'):
    """По барам - только для «Все заведения»; None, если бар в строках один."""
    if ctx.venue_key != 'all':
        return None
    by_store = ctx.by_store()
    if len(by_store) < 2:
        return None
    key, fmt, additive = GROUP_VALUES[value]
    items = [{'name': store, 'value': m[key], 'sub': _group_sub(value, m)} for store, m in by_store.items()]
    return _top_section('stores', 'Бары', 'По барам', GROUP_FORMULAS[value], fmt, items, 'value',
                        ctx.metrics[key], additive=additive, sub_fn=lambda it: it['sub'],
                        total_hint=GROUP_TOTAL_HINTS.get(value), top_n=max(TOP_N, len(items)))


# ---------- категории ----------

def sec_categories(ctx, value='revenue', title='Категории'):
    """Розлив / Фасовка / Кухня / Прочее: выручка, маржа, наценка или списания."""
    m = ctx.metrics
    items = []
    if value == 'discount':
        for cat, label, _top in CATEGORIES:
            items.append({'name': label, 'value': _calc._sum_discounts(_rows_of(ctx.records, cat)),
                          'sub': f"{_fmt_pct(m[f'{cat}_share'])} выручки"})
        return _top_section('categories', title, 'Списания по категориям',
                            'Списания категории = Σ DiscountSum по её строкам; сумма = карточка',
                            'money', items, 'value', m['loyalty_points_written_off'],
                            sub_fn=lambda it: it['sub'], top_n=len(items))
    if value == 'margin':
        for cat, label, _top in CATEGORIES:
            items.append({'name': label, 'value': m[f'{cat}_margin'],
                          'sub': f"наценка {_fmt_pct(m[f'{cat}_markup'] * 100)}"})
        return _top_section('categories', title, 'Прибыль по категориям',
                            'Прибыль категории = Σ (выручка - себестоимость) по её строкам; сумма = карточка',
                            'money', items, 'value', m['total_margin'],
                            sub_fn=lambda it: it['sub'], top_n=len(items))
    if value == 'markup':
        rows = []
        for cat, label, _top in CATEGORIES:
            if not m['total_revenue']:
                break  # период без продаж - «Нет данных», а не четыре нуля
            rows.append({'name': label, 'value': round(m[f'{cat}_markup'] * 100, 1),
                         'sub': f"{_fmt_pct(m[f'{cat}_share'])} выручки · маржа {_fmt_money(m[f'{cat}_margin'])}"})
        rows.sort(key=lambda r: r['value'], reverse=True)
        total = {'name': 'Итого', 'value': round(m['avg_markup'] * 100, 1),
                 'hint': 'Наценка по всем строкам периода, как на карточке. Это не среднее категорий'}
        return _section('categories', title, 'Наценка по категориям',
                        'Наценка категории = (Σ выручка - Σ себестоимость) / Σ себестоимость × 100 по её строкам; '
                        'позиции без себестоимости участвуют выручкой', 'percent', rows,
                        additive=False, total=total)
    for cat, label, _top in CATEGORIES:
        items.append({'name': label, 'value': m[f'{cat}_revenue'],
                      'sub': f"наценка {_fmt_pct(m[f'{cat}_markup'] * 100)}"})
    return _top_section('categories', title, 'Выручка по категориям',
                        'Выручка категории = Σ DishDiscountSumInt по строкам с этой группой 1-го уровня; '
                        'кухня = строго «ЕДА», наборы и чай/кофе - «Прочее»; сумма = карточка',
                        'money', items, 'value', m['total_revenue'],
                        sub_fn=lambda it: it['sub'], top_n=len(items))


# ---------- позиции ----------

def _items_of(ctx, category, key):
    return list(ctx.dishes(category, key).values())


def sec_top_dishes(ctx, category=None, value='revenue', key='dish', title=None):
    """Топ позиций категории по выручке, штукам, марже или сумме скидки."""
    items = _items_of(ctx, category, key)
    unit = UNIT_WORD.get(category)
    cat_label = CATEGORY_LABEL.get(category, 'все категории')
    what = 'сортов' if key == 'sort' else ('блюд' if category == 'kitchen' else 'позиций')
    if value == 'units':
        total_value = sum(it['units'] for it in items)
        return _top_section('top_units', title or 'По штукам', f'Топ-5 {what} по количеству',
                            f'Количество = Σ DishAmountInt по строкам позиции ({cat_label}); '
                            f'доля = от всех {unit} категории', 'number', items, 'units', total_value,
                            sub_fn=lambda it: _fmt_money(it['revenue']),
                            total_name=f'Всего {unit}')
    if value == 'margin':
        total_value = _calc._sum_margin(_rows_of(ctx.records, category))
        total_name = 'Итого' if category is None else f'Маржа: {cat_label.lower()}'
        return _top_section('top_margin', title or 'Лидеры маржи', f'Топ-5 {what} по марже',
                            'Маржа позиции = Σ (выручка - себестоимость) по её строкам; сумма = маржа разреза',
                            'money', items, 'margin', total_value,
                            sub_fn=lambda it: ('наценка ' + _fmt_pct(it['markup']))
                            if it['markup'] is not None else 'без себестоимости',
                            total_name=total_name)
    if value == 'discount':
        total_value = _calc._sum_discounts(_rows_of(ctx.records, category))
        return _top_section('top_discount', title or 'Позиции', f'Топ-5 {what} по сумме скидки',
                            'Скидка позиции = Σ DiscountSum по её строкам; «% от цены» = скидка / (выручка + скидка) × 100; '
                            'сумма = карточка', 'money', items, 'discount', total_value,
                            sub_fn=lambda it: (f"{_fmt_pct(it['discount'] / (it['revenue'] + it['discount']) * 100)} от цены"
                                               if it['revenue'] + it['discount'] > 0 else ''))
    total_value = (_calc._sum_revenue(_rows_of(ctx.records, category)) if category
                   else ctx.metrics['total_revenue'])
    return _top_section('top_revenue', title or 'Позиции', f'Топ-5 {what} по выручке',
                        f'Выручка = Σ DishDiscountSumInt по строкам позиции ({cat_label}); '
                        + ('объёмы одного сорта сложены; ' if key == 'sort' else '')
                        + 'сумма строк = карточка', 'money', items, 'revenue', total_value,
                        sub_fn=lambda it: f"{_fmt_int(it['units'])} {unit}")


def sec_low_markup(ctx, category=None, key='dish'):
    """Позиции с наименьшей наценкой при себестоимости > 0 и заметной выручке."""
    items = _items_of(ctx, category, key)
    cat_rows = _rows_of(ctx.records, category)
    cat_revenue = _calc._sum_revenue(cat_rows)
    threshold = cat_revenue * LOW_MARKUP_MIN_SHARE
    ranked = [it for it in items if it['cost'] > 0 and it['revenue'] >= threshold]
    zero_cost = [it for it in items if it['cost'] <= 0 and it['revenue'] > 0]
    note = None
    if zero_cost:
        note = (f"Без себестоимости: {len(zero_cost)} поз. на {_fmt_money(sum(it['revenue'] for it in zero_cost))} - "
                f"в наценке они участвуют только выручкой и не ранжируются")
    total_value = _calc._calculate_markup(cat_rows) * 100
    what = 'сортов' if key == 'sort' else ('блюд' if category == 'kitchen' else 'позиций')
    return _top_section('low_markup', 'Слабая наценка', f'5 {what} с наименьшей наценкой',
                        'Наценка позиции = (выручка - себестоимость) / себестоимость × 100; '
                        f'показаны позиции с себестоимостью > 0 и выручкой не меньше {int(LOW_MARKUP_MIN_SHARE * 100)}% разреза',
                        'percent', ranked, 'markup', total_value, additive=False, reverse=False,
                        sub_fn=lambda it: f"выручка {_fmt_money(it['revenue'])} · маржа {_fmt_money(it['margin'])}",
                        total_hint='Наценка разреза по всем строкам, как на карточке. Это не среднее строк выше',
                        note=note)


def sec_local_import(ctx, category):
    """Локал (Россия) / импорт по стране DishForeignName."""
    rows_cat = _rows_of(ctx.records, category)
    split = _calc.local_import_revenue(ctx.records, CATEGORY_TOP_PARENT[category])
    units = {'local': 0.0, 'import': 0.0}
    for record in rows_cat:
        country = (record.get('DishForeignName') or '').strip()
        bucket = 'local' if country == DashboardMetrics.LOCAL_COUNTRY else 'import'
        units[bucket] += _num(record.get('DishAmountInt'))
    unit = UNIT_WORD.get(category)
    items = [
        {'name': 'Россия', 'value': split['local'], 'sub': f"{_fmt_int(units['local'])} {unit}"},
        {'name': 'Импорт', 'value': split['import'], 'sub': f"{_fmt_int(units['import'])} {unit}"},
    ]
    total_value = _calc._sum_revenue(rows_cat)
    return _top_section('local_import', 'Локал/импорт', 'Локальное и импортное',
                        'Локал = страна позиции «Россия», импорт = остальные страны и пусто '
                        '(как в месячном отчёте); выручка = Σ DishDiscountSumInt', 'money', items,
                        'value', total_value, sub_fn=lambda it: it['sub'], top_n=2,
                        total_name=f'Выручка: {CATEGORY_LABEL[category].lower()}')


# ---------- лояльность ----------

def sec_card_split(ctx, value='avg_check'):
    """С картой лояльности / без карты: средний чек, чеки или выручка."""
    m = ctx.metrics
    card_avg = m['card_revenue'] / m['card_checks'] if m['card_checks'] else 0.0
    nocard_avg = m['nocard_revenue'] / m['nocard_checks'] if m['nocard_checks'] else 0.0
    if value == 'avg_check':
        rows = [
            {'name': 'С картой лояльности', 'value': _round(card_avg, 'money'),
             'sub': f"{_fmt_int(m['card_checks'])} чек. · {_fmt_money(m['card_revenue'])}"},
            {'name': 'Без карты', 'value': _round(nocard_avg, 'money'),
             'sub': f"{_fmt_int(m['nocard_checks'])} чек. · {_fmt_money(m['nocard_revenue'])}"},
        ] if m['total_checks'] else []
        total = {'name': 'Итого', 'value': _round(m['avg_check'], 'money'),
                 'hint': 'Средний чек по всем чекам периода, как на карточке'}
        return _section('card_split', 'Карта', 'С картой и без',
                        'Средний чек = выручка / чеки в каждой группе; чек с картой = непустой номер карты '
                        'лояльности хотя бы в одной его строке', 'money', rows, additive=False, total=total)
    if value == 'checks':
        items = [
            {'name': 'С картой лояльности', 'value': float(m['card_checks']),
             'sub': f"средний чек {_fmt_money(card_avg)}"},
            {'name': 'Без карты', 'value': float(m['nocard_checks']),
             'sub': f"средний чек {_fmt_money(nocard_avg)}"},
        ]
        return _top_section('card_split', 'Карта', 'Чеки с картой и без',
                            'Чек с картой = непустой номер карты лояльности хотя бы в одной строке чека; '
                            'без карты = все чеки - с картой', 'number', items, 'value',
                            float(m['total_checks']), sub_fn=lambda it: it['sub'], top_n=2,
                            total_name='Все чеки')
    items = [
        {'name': 'С картой лояльности', 'value': m['card_revenue'],
         'sub': f"{_fmt_int(m['card_checks'])} чек."},
        {'name': 'Без карты', 'value': m['nocard_revenue'],
         'sub': f"{_fmt_int(m['nocard_checks'])} чек."},
    ]
    return _top_section('card_split', 'Карта', 'Выручка с картой и без',
                        'Выручка по картам = Σ DishDiscountSumInt строк с непустым номером карты; '
                        'без карты = вся выручка - по картам', 'money', items, 'value',
                        m['total_revenue'], sub_fn=lambda it: it['sub'], top_n=2,
                        total_name='Вся выручка')


def _guests(ctx):
    return _aggregate(ctx.records, lambda r: str(r.get(DashboardMetrics.CARD_FIELD) or '').strip() or None)


def sec_top_guests(ctx, value='revenue'):
    """Топ гостей по номеру карты лояльности (имени гостя в строках нет)."""
    items = list(_guests(ctx).values())
    m = ctx.metrics
    if value == 'checks':
        return _top_section('guests', 'Гости', 'Топ-5 гостей по чекам',
                            'Чеки гостя = уникальные заказы с его номером карты; визиты = уникальные учётные дни; '
                            'сумма по всем картам = карточка', 'number', items, 'checks',
                            float(m['card_checks']),
                            sub_fn=lambda it: f"{_fmt_money(it['revenue'])} · {it['visits']} визит.",
                            rest_label='Остальные карты')
    return _top_section('guests', 'Гости', 'Топ-5 гостей по выручке',
                        'Выручка гостя = Σ DishDiscountSumInt строк с его номером карты; '
                        'сумма по всем картам = карточка', 'money', items, 'revenue', m['card_revenue'],
                        sub_fn=lambda it: f"{it['checks']} чек. · {it['visits']} визит.",
                        rest_label='Остальные карты')


# ---------- ленивые секции из других источников ----------

def lazy_stub(section_id):
    """Заглушка ленивой секции в bulk-ответе: фронт грузит её по клику на вкладку."""
    title = {'draft_liters': 'Литры', 'taps': 'Краны'}[section_id]
    return _section(section_id, title, title, '', 'number', [], lazy=True)


def section_draft_liters(block):
    """Топ-5 кегов по литрам из готового блока DraftKegAnalysis.build() (как на /draft)."""
    kegs = list(block.get('kegs') or [])
    items = [{'name': keg.get('KegName') or keg.get('KegId'), 'liters': _num(keg.get('TotalLiters')),
              'portions': _num(keg.get('TotalPortions'))} for keg in kegs]
    total_value = _num(block.get('total_liters'))
    section = _top_section('draft_liters', 'Литры', 'Топ-5 кегов по литрам',
                           'Литры = Σ Amount.Out проводок списания кега при продаже (SESSION_WRITEOFF, ЕИ «л»), '
                           'как на странице /draft; доля = литры кега / литры всех кегов × 100',
                           'liters', items, 'liters', total_value,
                           sub_fn=lambda it: f"{_fmt_int(it['portions'])} порц.",
                           total_name='Всего литров', rest_label='Остальные кеги',
                           link={'href': '/draft', 'label': 'Открыть проливы'})
    notes = block.get('bartender_notes') or {}
    unassigned = _num(notes.get('unassigned_liters'))
    if abs(unassigned) > 0.01:
        section['note'] = f"Литров без строки продажи: {unassigned:.1f} (граница учётного дня)".replace('.', ',')
    if block.get('generated_at'):
        section['note'] = ((section['note'] + ' · ') if section['note'] else '') + f"данные iiko на {block['generated_at']}"
    return section


def section_taps(detail, bar_names=None, link_href='/taps'):
    """Краны с наибольшим простоем из TapsManager.tap_activity_by_tap()."""
    bar_names = bar_names or {}
    days = int(detail.get('days') or 0)
    taps = list(detail.get('taps') or [])
    idle = [t for t in taps if int(t.get('active_days') or 0) == 0]
    items = []
    for tap in taps:
        active = int(tap.get('active_days') or 0)
        bar = bar_names.get(tap.get('bar_id')) or tap.get('bar_name') or tap.get('bar_id')
        items.append({
            'name': f"Кран {tap.get('tap_number')} · {bar}",
            'value': (active / days * 100) if days else 0.0,
            'sub': (f"{active} из {days} дн." + (f" · {tap['current_beer']}" if tap.get('current_beer') else '')),
        })
    total_value = _num(detail.get('percent'))
    note = (f"Простаивали весь период: {len(idle)} из {len(taps)} кранов" if taps else None)
    return _top_section('taps', 'Краны', '5 кранов с наибольшим простоем',
                        'Кран активен в день, если его последнее событие до конца дня - подключение или замена кеги; '
                        'активность крана = активных дней / дней периода × 100; карточка = Σ активных кран-дней / '
                        '(кранов × дней) × 100', 'percent', items, 'value', total_value, additive=False,
                        reverse=False, sub_fn=lambda it: it['sub'],
                        total_hint='Активность всех кранов за период, как на карточке',
                        note=note, link={'href': link_href, 'label': 'Открыть краны'})


# ---------- реестр ----------

CARD_SECTIONS = {
    'revenue': [sec_days, sec_stores, partial(sec_categories, value='revenue'), sec_weekdays],
    'checks': [partial(sec_days, value='checks'), partial(sec_stores, value='checks'),
               partial(sec_weekdays, value='checks')],
    'averageCheck': [partial(sec_card_split, value='avg_check'), partial(sec_stores, value='avg_check'),
                     partial(sec_days, value='avg_check')],
    'markupPercent': [partial(sec_categories, value='markup'), partial(sec_top_dishes, value='margin'),
                      sec_low_markup],
    'draftShare': [lambda ctx: lazy_stub('draft_liters'),
                   partial(sec_categories, value='revenue', title='Структура')],
    'revenueDraft': [partial(sec_top_dishes, category='draft', key='sort', title='Сорта'),
                     partial(sec_local_import, category='draft'),
                     lambda ctx: lazy_stub('draft_liters')],
    'markupDraft': [partial(sec_top_dishes, category='draft', value='margin', key='sort'),
                    partial(sec_low_markup, category='draft', key='sort')],
    'packagedShare': [partial(sec_top_dishes, category='bottles', value='units'),
                      partial(sec_local_import, category='bottles'),
                      partial(sec_categories, value='revenue', title='Структура')],
    'revenuePackaged': [partial(sec_top_dishes, category='bottles'),
                        partial(sec_local_import, category='bottles')],
    'markupPackaged': [partial(sec_top_dishes, category='bottles', value='margin'),
                       partial(sec_low_markup, category='bottles')],
    'kitchenShare': [partial(sec_top_dishes, category='kitchen', value='units', title='По порциям'),
                     partial(sec_categories, value='revenue', title='Структура')],
    'revenueKitchen': [partial(sec_top_dishes, category='kitchen', title='Блюда'),
                       partial(sec_days, value='kitchen_revenue')],
    'markupKitchen': [partial(sec_top_dishes, category='kitchen', value='margin'),
                      partial(sec_low_markup, category='kitchen')],
    'profit': [partial(sec_categories, value='margin'), partial(sec_top_dishes, value='margin', title='Позиции'),
               partial(sec_stores, value='margin')],
    'loyaltyWriteoffs': [partial(sec_categories, value='discount'), partial(sec_top_dishes, value='discount'),
                         partial(sec_days, value='discount')],
    'tapActivity': [lambda ctx: lazy_stub('taps')],
    'cardChecks': [partial(sec_top_guests, value='checks'), partial(sec_days, value='card_checks'),
                   partial(sec_stores, value='card_checks')],
    'nocardChecks': [partial(sec_days, value='nocard_checks'), partial(sec_stores, value='nocard_checks')],
    'cardChecksShare': [partial(sec_stores, value='card_share'), partial(sec_days, value='card_share', order='asc')],
    'cardRevenue': [partial(sec_top_guests, value='revenue'), partial(sec_card_split, value='revenue'),
                    partial(sec_stores, value='card_revenue')],
}


def build_card_details(metric_id, all_sales_data, venue_key, date_from, date_to, daily_plans=None):
    """
    Секции одной карточки из строк единого запроса.

    Returns:
        list[section] в порядке реестра; секция, которую посчитать не удалось,
        приходит с error и пустыми rows, остальные не страдают. Неизвестная
        метрика -> ValueError (роут отдаёт 400).
    """
    if metric_id not in CARD_SECTIONS:
        raise ValueError(f'Неизвестная метрика: {metric_id}')
    ctx = DetailsContext(all_sales_data, venue_key, date_from, date_to, daily_plans)
    sections = []
    for builder in CARD_SECTIONS[metric_id]:
        try:
            section = builder(ctx)
        except Exception as e:  # noqa: BLE001 - изоляция секции
            print(f"[CARD DETAILS] {metric_id}: sekciya ne poschitana: {e}")
            traceback.print_exc()
            name = getattr(builder, 'func', builder)
            sid = getattr(name, '__name__', 'section').replace('sec_', '')
            section = _section(sid, 'Ошибка', 'Секция не посчитана', '', 'number', [],
                               error='Не удалось посчитать')
        if section is not None:
            sections.append(section)
    return sections
