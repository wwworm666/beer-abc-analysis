"""План/факт кассовых смен по дням недели: по людям, барам и месяцам за период до года.

## Что это

Сводка под вопрос владельца (2026-11-04): «процент плана у бармена зависит от того, сколько у
него пятниц и суббот, а не от умения продавать?». Страница ЗП и `staff_bonus_calculate`
считают премии помесячно и отдают каждую смену (около 36 000 символов за месяц), поэтому год
по людям агенту был не по силам: бот посчитал помесячные смены одного бара и упёрся в предел
вопроса. Здесь те же смены за период до MAX_DAYS дней сведены в компактный ответ (десятки
тысяч символов за год, а не сотни): выходные дни против остальных и каждый день недели, по
человеку, по бару и по месяцу, плюс «норма графика» человека.

## Файлы

| Файл | Роль |
|------|------|
| `core/shift_plan_weekdays.py` | этот модуль: проверка аргументов и сводка (чистые функции) |
| `routes/employee.py` | `POST /api/shift-plan-weekdays`: расчёт премий в процессе, затем `summarize()` |
| `core/mcp/tools/staff.py` | инструмент `staff_shift_plan_weekdays` |
| `tests/test_shift_plan_weekdays.py` | тесты сводки, нормы и маршрута |

## Как работает

Смена — день кассовой смены человека из расчёта премий (`/api/bonus-calculate`, поле `days`):
дата открытия смены, бар (`venue`), выручка смены, план бара на этот день и премия за дневной
план. Это ровно те числа, что на странице ЗП; маршрут вызывает тот же расчёт, свой не ведёт.

    % плана (percent)  = сумма выручки / сумма плана x 100, по сменам с планом; 0,1
    met                = смены, где выручка выше плана: за них платится премия за дневной план
    bonus              = сумма премий за дневной план, ₽ (1000 ₽ + 5% перевыполнения за смену)
    выходные (weekend) = дни недели из weekend_days, по умолчанию пт и сб (вес 2 в плане дня);
                         остальные дни — weekdays
    weekend_share      = смены в выходные / все смены с планом x 100; 0,1

Пример: 3 смены в пт/сб с планом 60 000 ₽ каждая и выручкой 150 000 ₽ на троих —
weekend.percent = 150 000 / 180 000 x 100 = 83,3.

Норма графика (`norm`) — сколько % плана на таких же сменах сделали коллеги:

    норма ячейки       = выручка / план смен ДРУГИХ людей на том же баре, в том же месяце и
                         в той же группе дней (выходные или остальные)
    expected_revenue   = сумма по ячейкам человека: его план в ячейке x норма ячейки, ₽
    norm.percent       = expected_revenue / его план в этих ячейках x 100
    norm.fact_percent  = его выручка / его план в тех же ячейках x 100
    norm.diff          = fact_percent - percent, п.п.: плюс — продаёт лучше коллег в те же
                         дни, минус — хуже; сколько в графике пятниц и суббот, на разницу не
                         влияет — каждая смена сравнивается с такими же сменами
    weekend_diff, weekdays_diff — та же разница только по выходным или только по остальным
    norm.coverage      = доля плана человека в ячейках, где работал кто-то ещё, %; в ячейке
                         без коллег сравнивать не с кем, она в норму не входит
    norm = null        — ни в одной ячейке человека не работал никто другой

Пример нормы: человек в пт/сб октября на Лиговском сделал 90 000 ₽ при плане 100 000 ₽, коллеги
там же в пт/сб октября — 160 000 ₽ при плане 200 000 ₽ (норма 80%). expected_revenue = 100 000 x
0,8 = 80 000 ₽, norm.percent = 80,0, fact_percent = 90,0, diff = +10,0 п.п.

Смены без плана (у бара нет месячного плана на этот день, точка без плана) в проценты не входят:
их число и выручка — в `no_plan`. Поэтому % за месяц здесь может отличаться от страницы ЗП:
там выручка таких дней входит в итог, а план — нет.

Фильтр `venue_key` оставляет смены одного бара (и людей, у кого они есть); нормы тогда тоже
считаются только по этому бару — они и так считаются внутри бара.

Округление: рубли — до рубля, проценты и п.п. — до 0,1 (round Python, как в расчёте ЗП);
разница нормы считается из неокруглённых процентов.

Что сломается при неправильной правке: группы дней не совпадут с весами плана (пт/сб = 2) —
вывод про веса станет неверным; норма с самим человеком внутри подтянется к его же проценту и
разница станет около нуля у тех, кто работает в ячейке почти один.

## Changelog

- 2026-11-04 — модуль создан: бот не мог сравнить людей за год (помесячные ответы расчёта
  премий по 36 000 символов), отвечал по барам вместо людей.
"""
from collections import defaultdict
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.venues_config import KEY_TO_IIKO_NAME, PHYSICAL_VENUES

# Длина периода: год с запасом на «52 недели» и неполные месяцы по краям. Ограничение — нагрузка
# на iiko: кассовые смены за период приходят одним запросом.
MAX_DAYS = 400

# Выходные по умолчанию — пт и сб: в плане дня у них вес 2 (core/daily_plans_generator.py).
DEFAULT_WEEKEND = (4, 5)

WEEKDAY_NAMES = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')
GROUPS = ('weekend', 'weekdays')

VENUE_CHOICES = ('all',) + tuple(PHYSICAL_VENUES)


# ---------------------------------------------------------------- аргументы

def parse_period(date_from: Any, date_to: Any) -> Tuple[str, str]:
    """('YYYY-MM-DD', 'YYYY-MM-DD') -> те же строки; ValueError с причиной по-русски."""
    try:
        first = date.fromisoformat(str(date_from or ''))
        last = date.fromisoformat(str(date_to or ''))
    except ValueError:
        raise ValueError('Нужны date_from и date_to в формате YYYY-MM-DD')
    if last < first:
        raise ValueError('date_to раньше date_from')
    if (last - first).days + 1 > MAX_DAYS:
        raise ValueError(f'Период не длиннее {MAX_DAYS} дней: сузьте его')
    return first.isoformat(), last.isoformat()


def parse_weekend(value: Any) -> Tuple[int, ...]:
    """weekend_days: список номеров дней 0..6 (0 = пн); не передан — пт и сб."""
    if value is None:
        return DEFAULT_WEEKEND
    if not isinstance(value, list) or not value:
        raise ValueError('weekend_days — непустой список номеров дней 0..6 (0 = пн)')
    days = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 6:
            raise ValueError('weekend_days — номера дней 0..6 (0 = пн, 6 = вс)')
        if item not in days:
            days.append(item)
    if len(days) == 7:
        raise ValueError('weekend_days не может включать все 7 дней: не с чем сравнивать')
    return tuple(sorted(days))


def parse_venue(value: Any) -> str:
    """venue_key: ключ бара или 'all' (по умолчанию)."""
    key = (value or 'all')
    if key not in VENUE_CHOICES:
        raise ValueError('venue_key — один из: ' + ', '.join(VENUE_CHOICES))
    return key


# ---------------------------------------------------------------- сводка

class _Acc:
    """Сумма смен: число, план, выручка, смены с выполненным планом, премии."""

    __slots__ = ('shifts', 'plan', 'revenue', 'met', 'bonus')

    def __init__(self):
        self.shifts = 0
        self.plan = 0.0
        self.revenue = 0.0
        self.met = 0
        self.bonus = 0.0

    def add(self, plan: float, revenue: float, bonus: float) -> None:
        self.shifts += 1
        self.plan += plan
        self.revenue += revenue
        if bonus > 0:
            self.met += 1
        self.bonus += bonus

    def percent(self) -> Optional[float]:
        return round(self.revenue / self.plan * 100, 1) if self.plan > 0 else None

    def block(self) -> Dict[str, Any]:
        return {'shifts': self.shifts, 'plan': round(self.plan), 'revenue': round(self.revenue),
                'percent': self.percent(), 'met': self.met, 'bonus': round(self.bonus)}

    def slim(self) -> Dict[str, Any]:
        """Строка дня недели у человека: без рублей — их хватает в группах."""
        return {'shifts': self.shifts, 'percent': self.percent(), 'met': self.met}


class _Scope:
    """Итог, две группы дней и семь дней недели одного среза (сеть, бар, человек)."""

    def __init__(self):
        self.total = _Acc()
        self.groups = {g: _Acc() for g in GROUPS}
        self.days = [_Acc() for _ in range(7)]

    def add(self, weekday: int, group: str, plan: float, revenue: float, bonus: float) -> None:
        for acc in (self.total, self.groups[group], self.days[weekday]):
            acc.add(plan, revenue, bonus)

    def out(self, slim_days: bool = False) -> Dict[str, Any]:
        shifts = self.total.shifts
        share = round(self.groups['weekend'].shifts / shifts * 100, 1) if shifts else None
        if slim_days:
            by_day = [dict(day=WEEKDAY_NAMES[i], **acc.slim()) for i, acc in enumerate(self.days)
                      if acc.shifts]
        else:
            by_day = [dict(day=WEEKDAY_NAMES[i], **acc.block()) for i, acc in enumerate(self.days)]
        return {'total': self.total.block(), 'weekend': self.groups['weekend'].block(),
                'weekdays': self.groups['weekdays'].block(), 'weekend_share': share,
                'by_weekday': by_day}


def _shift_rows(employee: Dict[str, Any], venue_key: str,
                weekend: frozenset) -> Tuple[List[tuple], _Acc]:
    """Смены человека -> ([(бар, месяц, день недели, группа, план, выручка, премия)], без плана)."""
    rows: List[tuple] = []
    no_plan = _Acc()
    for day in employee.get('days') or []:
        venue = day.get('venue') or ''
        if venue_key != 'all' and venue != venue_key:
            continue
        stamp = str(day.get('date') or '')[:10]
        try:
            weekday = date.fromisoformat(stamp).weekday()
        except ValueError:
            continue
        plan = float(day.get('plan') or 0)
        revenue = float(day.get('revenue') or 0)
        bonus = float(day.get('day_bonus') or 0)
        if plan <= 0:
            no_plan.add(0.0, revenue, 0.0)
            continue
        group = 'weekend' if weekday in weekend else 'weekdays'
        rows.append((venue, stamp[:7], weekday, group, plan, revenue, bonus))
    return rows, no_plan


def _norm(cells: Dict[tuple, List[float]], totals: Dict[tuple, List[float]],
          plan_total: float) -> Optional[Dict[str, Any]]:
    """Норма графика человека: его ячейки (бар, месяц, группа) против коллег в тех же ячейках."""
    expected = covered_plan = covered_revenue = 0.0
    by_group = {g: [0.0, 0.0, 0.0] for g in GROUPS}           # ожидаемая выручка, план, выручка
    for key, (revenue, plan) in cells.items():
        all_revenue, all_plan = totals[key]
        others_plan = all_plan - plan
        if others_plan <= 1e-6:                                 # в ячейке работал только он
            continue
        rate = (all_revenue - revenue) / others_plan
        expected += plan * rate
        covered_plan += plan
        covered_revenue += revenue
        part = by_group[key[2]]
        part[0] += plan * rate
        part[1] += plan
        part[2] += revenue
    if covered_plan <= 0:
        return None

    def diff(exp: float, plan: float, revenue: float) -> Optional[float]:
        return round((revenue - exp) / plan * 100, 1) if plan > 0 else None

    return {'percent': round(expected / covered_plan * 100, 1),
            'fact_percent': round(covered_revenue / covered_plan * 100, 1),
            'diff': diff(expected, covered_plan, covered_revenue),
            'weekend_diff': diff(*by_group['weekend']),
            'weekdays_diff': diff(*by_group['weekdays']),
            'coverage': round(covered_plan / plan_total * 100, 1) if plan_total > 0 else None,
            'expected_revenue': round(expected)}


def summarize(employees: Iterable[Dict[str, Any]], date_from: str, date_to: str,
              weekend_days: Sequence[int] = DEFAULT_WEEKEND,
              venue_key: str = 'all') -> Dict[str, Any]:
    """Сотрудники расчёта премий (employees с days) -> сводка по дням недели (докстрока модуля)."""
    weekend = frozenset(weekend_days)
    network = _Scope()
    venues: Dict[str, _Scope] = defaultdict(_Scope)
    months: Dict[str, Dict[str, _Acc]] = defaultdict(lambda: {'total': _Acc(), 'weekend': _Acc(),
                                                              'weekdays': _Acc()})
    totals: Dict[tuple, List[float]] = defaultdict(lambda: [0.0, 0.0])
    no_plan_all = _Acc()
    people = []

    for employee in employees:
        rows, no_plan = _shift_rows(employee, venue_key, weekend)
        no_plan_all.shifts += no_plan.shifts
        no_plan_all.revenue += no_plan.revenue
        if not rows and not no_plan.shifts:
            continue
        scope = _Scope()
        cells: Dict[tuple, List[float]] = defaultdict(lambda: [0.0, 0.0])
        venue_shifts: Dict[str, int] = defaultdict(int)
        for venue, month, weekday, group, plan, revenue, bonus in rows:
            scope.add(weekday, group, plan, revenue, bonus)
            network.add(weekday, group, plan, revenue, bonus)
            venues[venue].add(weekday, group, plan, revenue, bonus)
            for acc in (months[month]['total'], months[month][group]):
                acc.add(plan, revenue, bonus)
            key = (venue, month, group)
            cells[key][0] += revenue
            cells[key][1] += plan
            totals[key][0] += revenue
            totals[key][1] += plan
            venue_shifts[venue] += 1
        people.append((employee, scope, cells, venue_shifts, no_plan))

    out_people = []
    for employee, scope, cells, venue_shifts, no_plan in people:
        item = {'name': employee.get('name') or '', 'employee_id': employee.get('employee_id') or '',
                'venues': sorted(venue_shifts, key=lambda v: (-venue_shifts[v], v))}
        item.update(scope.out(slim_days=True))
        item['norm'] = _norm(cells, totals, scope.total.plan) if cells else None
        if no_plan.shifts:
            item['no_plan'] = {'shifts': no_plan.shifts, 'revenue': round(no_plan.revenue)}
        out_people.append(item)
    out_people.sort(key=lambda p: (-p['total']['shifts'], p['name']))

    weekdays = [d for d in range(7) if d not in weekend]
    venue_list = []
    for key in sorted(venues, key=lambda v: (PHYSICAL_VENUES.index(v) if v in PHYSICAL_VENUES else 99, v)):
        entry = {'venue_key': key, 'name': KEY_TO_IIKO_NAME.get(key) or key}
        entry.update(venues[key].out())
        venue_list.append(entry)
    return {
        'period': {'from': date_from, 'to': date_to},
        'venue_key': venue_key,
        'groups': {'weekend': sorted(weekend), 'weekend_names': ', '.join(WEEKDAY_NAMES[d] for d in sorted(weekend)),
                   'weekdays': weekdays, 'weekdays_names': ', '.join(WEEKDAY_NAMES[d] for d in weekdays)},
        'network': network.out(),
        'venues': venue_list,
        'months': [{'month': m, **{k: acc.block() for k, acc in months[m].items()}} for m in sorted(months)],
        'employees': out_people,
        'no_plan': {'shifts': no_plan_all.shifts, 'revenue': round(no_plan_all.revenue)},
    }
