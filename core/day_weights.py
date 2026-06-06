"""
Канонический модуль весов дней для разбивки месячного плана на дни.

ЕДИНЫЙ источник правды для логики веса дня во всём проекте. И генератор
ежедневных планов (core/daily_plans_generator.py), и расчёт плана за период
(core/plans_manager.py) импортируют функции отсюда — дублировать формулу нельзя.

Формула разбивки:
    план_на_день = (месячный_план / сумма_весов_месяца) * вес_дня

Вес дня:
- По умолчанию: пятница (4) и суббота (5) = 2.0, остальные дни = 1.0.
- Может быть переопределён (override) для конкретной даты заведения —
  например, праздник = 5.0, закрытый день = 0.0.

Override — это АБСОЛЮТНЫЙ вес дня (не множитель). За счёт того, что в знаменателе
стоит сумма ВСЕХ весов месяца, при повышении веса одного дня остальные дни
автоматически уменьшаются, а сумма планов за месяц остаётся равной месячному плану.

`overrides` везде — плоский словарь {"YYYY-MM-DD": float} для ОДНОГО заведения
и месяца (только исключения; обычные дни в нём отсутствуют).
"""

from datetime import datetime, date, timedelta
from calendar import monthrange
from typing import Dict, List, Optional


# Веса дней недели по умолчанию
WEEKDAY_WEIGHT = 1.0  # пн-чт, вс
WEEKEND_WEIGHT = 2.0  # пятница (4) и суббота (5)

# Дни недели с повышенным весом (datetime.weekday(): 0=пн ... 4=пт, 5=сб, 6=вс)
WEEKEND_WEEKDAYS = (4, 5)

# Русские сокращения дней недели по индексу weekday()
WEEKDAY_NAMES_RU = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']


def default_day_weight(d: date) -> float:
    """Вес дня по умолчанию (без учёта override): пт/сб = 2.0, остальные = 1.0.

    ЕДИНСТВЕННОЕ место, где зашито правило пятница/суббота.
    """
    return WEEKEND_WEIGHT if d.weekday() in WEEKEND_WEEKDAYS else WEEKDAY_WEIGHT


def get_day_weight(d: date, overrides: Optional[Dict[str, float]] = None) -> float:
    """Вес дня с учётом override.

    Args:
        d: Дата.
        overrides: Плоский словарь {"YYYY-MM-DD": вес} для заведения+месяца.

    Returns:
        Абсолютный вес дня. Если для даты задан override (в т.ч. 0.0) —
        возвращается он; иначе вес по умолчанию.
    """
    if overrides:
        key = d.isoformat()
        if key in overrides:
            return float(overrides[key])
    return default_day_weight(d)


def is_override(d: date, overrides: Optional[Dict[str, float]] = None) -> bool:
    """True, если для даты задан явный override."""
    return bool(overrides) and d.isoformat() in overrides


def iter_month_days(year: int, month: int) -> List[date]:
    """Список всех дат календарного месяца."""
    days_in_month = monthrange(year, month)[1]
    return [date(year, month, day) for day in range(1, days_in_month + 1)]


def month_weight(year: int, month: int,
                 overrides: Optional[Dict[str, float]] = None) -> float:
    """Суммарный вес всех дней месяца (с учётом override)."""
    return sum(get_day_weight(d, overrides) for d in iter_month_days(year, month))


def daily_plan(monthly_revenue: float, year: int, month: int, day: int,
               overrides: Optional[Dict[str, float]] = None) -> float:
    """План выручки на конкретный день месяца.

    Args:
        monthly_revenue: Месячный план выручки.
        year, month, day: Дата.
        overrides: Override весов для заведения+месяца.

    Returns:
        План на день, округлённый до 2 знаков. 0.0 если месячный план <= 0
        или суммарный вес месяца == 0 (все дни закрыты) — защита от деления на ноль.
    """
    mw = month_weight(year, month, overrides)
    if mw <= 0 or monthly_revenue <= 0:
        return 0.0
    day_weight = get_day_weight(date(year, month, day), overrides)
    return round(monthly_revenue / mw * day_weight, 2)


def weighted_days(start: date, end: date,
                  overrides: Optional[Dict[str, float]] = None) -> float:
    """Сумма весов дней в инклюзивном диапазоне [start, end].

    Используется в core/plans_manager.py для расчёта доли периода в месяце.
    """
    total = 0.0
    d = start
    while d <= end:
        total += get_day_weight(d, overrides)
        d += timedelta(days=1)
    return total


def month_breakdown(year: int, month: int, monthly_revenue: float,
                    overrides: Optional[Dict[str, float]] = None) -> List[Dict]:
    """Подневная разбивка месяца — для страницы валидации и self-тестов.

    Returns:
        Список словарей по каждому дню месяца:
        {date, weekday, weekday_name, weight, is_override, daily_plan}.
    """
    mw = month_weight(year, month, overrides)
    plan_per_weight = (monthly_revenue / mw) if (mw > 0 and monthly_revenue > 0) else 0.0

    breakdown = []
    for d in iter_month_days(year, month):
        weight = get_day_weight(d, overrides)
        breakdown.append({
            'date': d.isoformat(),
            'weekday': d.weekday(),
            'weekday_name': WEEKDAY_NAMES_RU[d.weekday()],
            'weight': weight,
            'is_override': is_override(d, overrides),
            'daily_plan': round(plan_per_weight * weight, 2),
        })
    return breakdown


# Самотестирование
if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТ core/day_weights.py")
    print("=" * 60)

    YEAR, MONTH = 2025, 11
    REVENUE = 1_500_000.0

    # 1. Без override: сумма дней ~= месячный план, пт/сб весят 2x
    bd = month_breakdown(YEAR, MONTH, REVENUE)
    total = round(sum(d['daily_plan'] for d in bd), 2)
    print(f"\n1. Без override: сумма дней = {total:,.2f} (месячный = {REVENUE:,.2f})")
    assert abs(total - REVENUE) <= 1.0, f"drift {total - REVENUE}"
    fri = next(d for d in bd if d['weekday'] == 4)
    mon = next(d for d in bd if d['weekday'] == 0)
    print(f"   пт ({fri['date']}) = {fri['daily_plan']:,.2f}, пн ({mon['date']}) = {mon['daily_plan']:,.2f}")
    assert abs(fri['daily_plan'] - 2 * mon['daily_plan']) <= 0.05, "пт должна быть ~2x пн"

    # 2. Override: один день = 5.0 -> остальные уменьшились, сумма всё ещё ~= месячный
    ov = {f"{YEAR}-{MONTH:02d}-04": 5.0}
    bd2 = month_breakdown(YEAR, MONTH, REVENUE, ov)
    total2 = round(sum(d['daily_plan'] for d in bd2), 2)
    holiday = next(d for d in bd2 if d['date'] == f"{YEAR}-{MONTH:02d}-04")
    print(f"\n2. Override 04={ov[f'{YEAR}-{MONTH:02d}-04']}: сумма дней = {total2:,.2f}")
    print(f"   праздник 04 = {holiday['daily_plan']:,.2f} (is_override={holiday['is_override']})")
    assert abs(total2 - REVENUE) <= 1.0, f"drift {total2 - REVENUE}"
    assert holiday['is_override'] is True
    assert holiday['weight'] == 5.0

    # 3. Все дни закрыты (вес 0) -> month_weight 0, планы 0, без исключений
    all_closed = {d.isoformat(): 0.0 for d in iter_month_days(YEAR, MONTH)}
    assert month_weight(YEAR, MONTH, all_closed) == 0.0
    assert daily_plan(REVENUE, YEAR, MONTH, 1, all_closed) == 0.0
    print("\n3. Все дни закрыты: month_weight=0, daily_plan=0 (без деления на ноль)")

    print("\n" + "=" * 60)
    print("OK")
