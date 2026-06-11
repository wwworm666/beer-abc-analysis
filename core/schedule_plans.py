"""
Планы и сводка месяца для страниц графика смен (/schedule, /schedule/edit).

Источник плана дня — конвейер планов (plansdashboard.json -> core/day_weights.py
-> data/daily_plans.json). Ручной ввод плана на странице графика заморожен:
старые значения daily_revenue.plan_revenue используются ТОЛЬКО как фоллбэк
для месяцев, не покрытых daily_plans (помечаются source='manual').

Правило отображения плана дня по точке (детерминированное):
1. есть ключ venue_key в daily_plans за дату и значение > 0 -> source='weights';
2. иначе есть сохранённый ручной plan_revenue > 0          -> source='manual';
3. иначе плана нет (None, никогда не 0 — отсутствие плана не равно нулевому плану).

Все функции чистые: никакого I/O, всё тестируется на синтетике.
"""

from calendar import monthrange
from datetime import date
from typing import Dict, List, Optional

# Тексты формул для тултипов UI (принцип «показывать формулу пользователю»)
PLAN_FORMULA_TEXT = (
    'План дня = месячный план точки / сумма весов месяца x вес дня. '
    'Вес дня: пт и сб = 2.0, остальные = 1.0, праздники/закрытия — '
    'override на странице «Планы по дням».'
)
EXPECTED_FORMULA_TEXT = (
    'Ожидаемая = сумма по дням месяца: факт дня из iiko, если есть, '
    'иначе план дня. Веса пт/сб и override учтены в плане автоматически.'
)
AVG_FORMULA_TEXT = 'Средняя = сумма факта / количество дней с фактом.'
COMPLETION_FORMULA_TEXT = (
    'Выполнение % = факт / план тех же дней, где факт уже есть, x 100. '
    'Будущие дни на процент не влияют.'
)


def month_date_strs(year: int, month: int) -> List[str]:
    """Все даты месяца в формате YYYY-MM-DD."""
    days = monthrange(year, month)[1]
    return [f"{year}-{month:02d}-{day:02d}" for day in range(1, days + 1)]


def build_month_plans(year: int, month: int, locations: List[Dict],
                      daily_plans: Dict, manual_rows: List[Dict],
                      olap_fact: Optional[Dict] = None) -> Dict:
    """Собрать план/факт по дням месяца для всех точек.

    Args:
        locations: [{id, name, venue_key, ...}] из shifts.db.
        daily_plans: содержимое data/daily_plans.json -> plans
                     ({'YYYY-MM-DD': {'bolshoy': 123.0, ..., 'all': ...}}).
        manual_rows: записи daily_revenue за месяц
                     [{date, location_id, plan_revenue, fact_revenue}].
        olap_fact: факт из iiko OLAP {date_str: {venue_key: revenue}} —
                   тот же источник, что «Факт» на дашборде. None = iiko
                   недоступен, факт берётся из сохранённого daily_revenue
                   (фоллбэк-кэш).

    Returns:
        {date_str: {
            'locations': {location_id: {'plan': float|None,
                                        'plan_source': 'weights'|'manual'|None,
                                        'fact': float|None}},
            'plan_total': float|None,   # сумма планов точек, где план есть
            'fact_total': float|None,   # сумма фактов точек, где факт есть
        }}
    """
    manual_by_key = {(r['date'], r['location_id']): r for r in manual_rows}
    result = {}

    for date_str in month_date_strs(year, month):
        day_plans = daily_plans.get(date_str, {}) or {}
        olap_day = olap_fact.get(date_str, {}) if olap_fact is not None else None
        locs = {}
        plan_values = []
        fact_values = []

        for loc in locations:
            loc_id = loc['id']
            venue_key = loc.get('venue_key')
            manual = manual_by_key.get((date_str, loc_id), {})

            plan = None
            plan_source = None
            weights_plan = day_plans.get(venue_key) if venue_key else None
            if weights_plan is not None and weights_plan > 0:
                plan = round(float(weights_plan), 2)
                plan_source = 'weights'
            else:
                manual_plan = manual.get('plan_revenue')
                if manual_plan is not None and manual_plan > 0:
                    plan = round(float(manual_plan), 2)
                    plan_source = 'manual'

            # Факт: живой OLAP (как на дашборде); если iiko недоступен —
            # сохранённый daily_revenue. Отсутствие продаж за день = нет факта.
            if olap_day is not None:
                fact = olap_day.get(venue_key) if venue_key else None
            else:
                fact = manual.get('fact_revenue')
            fact = round(float(fact), 2) if fact is not None else None

            locs[loc_id] = {'plan': plan, 'plan_source': plan_source, 'fact': fact}
            if plan is not None:
                plan_values.append(plan)
            if fact is not None:
                fact_values.append(fact)

        result[date_str] = {
            'locations': locs,
            'plan_total': round(sum(plan_values), 2) if plan_values else None,
            'fact_total': round(sum(fact_values), 2) if fact_values else None,
        }

    return result


def compute_month_summary(month_plans: Dict, locations: List[Dict]) -> Dict:
    """Детерминированная сводка месяца из build_month_plans().

    Формулы (дублируются строками в ответе для тултипов UI):
    - plan_total      = сумма планов всех дней, где план есть;
    - fact_total      = сумма фактов всех дней, где факт есть;
    - avg_fact        = fact_total / days_with_fact;
    - expected        = сумма по дням (факт, если есть, иначе план);
    - completion_pct  = fact_total / план тех же дней, где есть факт, x 100.
    """
    plan_total = 0.0
    has_plan = False
    fact_total = 0.0
    days_with_fact = 0
    expected = 0.0
    plan_of_fact_days = 0.0

    per_location = {
        loc['id']: {
            'location_id': loc['id'],
            'location_name': loc['name'],
            'short_name': loc.get('short_name'),
            'plan_total': 0.0, 'has_plan': False,
            'fact_total': 0.0, 'days_with_fact': 0,
            'expected': 0.0, 'plan_of_fact_days': 0.0,
        }
        for loc in locations
    }

    for date_str in sorted(month_plans.keys()):
        day = month_plans[date_str]
        if day['plan_total'] is not None:
            plan_total += day['plan_total']
            has_plan = True
        if day['fact_total'] is not None:
            fact_total += day['fact_total']
            days_with_fact += 1
            if day['plan_total'] is not None:
                plan_of_fact_days += day['plan_total']

        # Ожидаемая: факт, если есть, иначе план (если есть)
        if day['fact_total'] is not None:
            expected += day['fact_total']
        elif day['plan_total'] is not None:
            expected += day['plan_total']

        for loc_id, cell in day['locations'].items():
            agg = per_location.get(loc_id)
            if agg is None:
                continue
            if cell['plan'] is not None:
                agg['plan_total'] += cell['plan']
                agg['has_plan'] = True
            if cell['fact'] is not None:
                agg['fact_total'] += cell['fact']
                agg['days_with_fact'] += 1
                if cell['plan'] is not None:
                    agg['plan_of_fact_days'] += cell['plan']
            if cell['fact'] is not None:
                agg['expected'] += cell['fact']
            elif cell['plan'] is not None:
                agg['expected'] += cell['plan']

    def _finalize(plan_total, has_plan, fact_total, days_with_fact,
                  expected, plan_of_fact_days):
        avg = round(fact_total / days_with_fact, 2) if days_with_fact else None
        completion = (round(fact_total / plan_of_fact_days * 100, 1)
                      if plan_of_fact_days > 0 else None)
        return {
            'plan_total': round(plan_total, 2) if has_plan else None,
            'fact_total': round(fact_total, 2) if days_with_fact else None,
            'days_with_fact': days_with_fact,
            'avg_fact': avg,
            'expected': round(expected, 2) if (has_plan or days_with_fact) else None,
            'completion_pct': completion,
        }

    month = _finalize(plan_total, has_plan, fact_total, days_with_fact,
                      expected, plan_of_fact_days)

    locations_summary = []
    for loc in locations:
        agg = per_location[loc['id']]
        row = _finalize(agg['plan_total'], agg['has_plan'], agg['fact_total'],
                        agg['days_with_fact'], agg['expected'],
                        agg['plan_of_fact_days'])
        row.update({
            'location_id': agg['location_id'],
            'location_name': agg['location_name'],
            'short_name': agg['short_name'],
        })
        locations_summary.append(row)

    return {
        'month': month,
        'locations': locations_summary,
        'formulas': {
            'plan': PLAN_FORMULA_TEXT,
            'expected': EXPECTED_FORMULA_TEXT,
            'avg_fact': AVG_FORMULA_TEXT,
            'completion_pct': COMPLETION_FORMULA_TEXT,
        },
    }


def compute_employees_load(shifts: List[Dict], today_str: str) -> List[Dict]:
    """Нагрузка по сотрудникам за месяц.

    - shifts_count: число смен;
    - fact_minutes: сумма введённого барменом факта (минуты; None не суммируется);
    - missing_fact: прошедшие смены (date < today) без введённого факта —
      подсветка «кто забыл проставить часы».
    """
    by_employee: Dict[str, Dict] = {}
    for s in shifts:
        agg = by_employee.setdefault(s['employee_name'], {
            'employee_name': s['employee_name'],
            'shifts_count': 0,
            'fact_minutes': 0,
            'missing_fact': 0,
        })
        agg['shifts_count'] += 1
        if s.get('fact_minutes') is not None:
            agg['fact_minutes'] += int(s['fact_minutes'])
        elif s['date'] < today_str:
            agg['missing_fact'] += 1

    return sorted(by_employee.values(),
                  key=lambda r: (-r['shifts_count'], r['employee_name']))
