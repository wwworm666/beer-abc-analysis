"""
Серверная сборка payload расчёта ЗП — то же, что страница /salary шлёт в экспорт.

## Что это

Ночная выгрузка в Google Таблицу (`core/salary_scheduler.py`) работает без
браузера, а payload для экспорта до сих пор собирал фронтенд `bonus.html`
(мёрж трёх источников + сортировка). Модуль повторяет этот мёрж на сервере,
чтобы автоматическая выгрузка совпадала с тем, что видит человек на странице.

## Файлы

- `core/salary_payload.py` — этот модуль.
- `templates/bonus.html` — оригинал мёржа (`mergeAndRender`,
  `recalcEmployeeTotals`, `buildExportPayload`); при правке ЛЮБОГО из них
  второй надо править синхронно, иначе кнопка и ночная выгрузка разойдутся.
- `tests/test_salary_payload.py` — тесты мёржа (сопоставление имён, порядок).

## Как работает

1. Три источника — те же, что у страницы:
   - `POST /api/bonus-calculate` — премия за план, передача смены, штрафы;
   - `POST /api/kpi-calculate`   — KPI-премии и коэффициент смен;
   - `shifts_mgr.get_hours_by_role_for_period()` — часы/оплата по ролям и
     дневные смены (такси).
   Первые два вызываются как view-функции внутри `test_request_context`:
   так используется РОВНО та же бизнес-логика, что у страницы (дублировать
   350 строк расчёта было бы источником расхождений), и не задевается
   `before_request`-авторизация — внутренний вызов не ходит по HTTP.
2. Мёрж по имени: сопоставление «множество слов одного имени — подмножество
   другого» (`_names_match`), как `namesMatch` в bonus.html. Это нужно, потому
   что iiko и график пишут имена по-разному («Юреня Роман» / «Юреня»).
3. Порядок сотрудников = порядок КОЛОНОК в выгрузке: сортировка по итогу ЗП
   по убыванию — как на странице.

## Changelog

- 2026-08-01 — модуль создан под ночную выгрузку в Google Таблицу.
"""

import calendar
import json
from datetime import date

DEFAULT_ROLE_RATE = 300      # ставка роли по умолчанию (как в bonus.html)
DEFAULT_BASE_PREMIUM = 5000  # тариф KPI, если фонд не задан
LATE_PENALTY_STEP = 250      # прогрессивный штраф за опоздание (для сверки)


def month_bounds(month: str):
    """'2026-07' -> ('2026-07-01', '2026-07-31')."""
    year, mon = int(month[:4]), int(month[5:7])
    last = calendar.monthrange(year, mon)[1]
    return f"{month}-01", f"{month}-{last:02d}"


def current_month() -> str:
    return date.today().strftime('%Y-%m')


def previous_month(month: str = None) -> str:
    y, m = (int((month or current_month())[:4]), int((month or current_month())[5:7]))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _name_words(name):
    """Множество слов имени в нижнем регистре (nameWords в bonus.html)."""
    return set((name or '').lower().strip().split())


def _names_match(a, b):
    """Одно имя — подмножество другого по словам (namesMatch в bonus.html)."""
    wa, wb = _name_words(a), _name_words(b)
    if not wa or not wb:
        return False
    return wa <= wb or wb <= wa


def _sorted_kpi_keys(obj):
    """kpi1, kpi2, ... kpi10 по номеру (sortedKpiKeys в bonus.html)."""
    keys = [k for k in (obj or {}) if k.startswith('kpi') and k[3:].isdigit()]
    return sorted(keys, key=lambda k: int(k[3:]))


class NoDataForPeriod(Exception):
    """За период ещё нет закрытых данных iiko (404 от расчёта).

    Штатная ситуация, а не сбой: в первые дни месяца продажи ещё не закрыты.
    Обрабатывается внутри `build_payload_for_month` — источник просто даёт
    пустой результат, а месяц выгружается по тому, что есть в графике.
    """


def _call_view(app, view, path, **kwargs):
    """Вызвать view-функцию напрямую в тестовом контексте запроса.

    Не HTTP: `before_request` (авторизация) не отрабатывает, что и нужно для
    внутреннего вызова из планировщика.
    """
    with app.test_request_context(path, **kwargs):
        resp = view()
    if isinstance(resp, tuple):        # (response, status)
        resp, status = resp[0], resp[1]
        if status == 404:
            raise NoDataForPeriod(f"{path}: нет данных за период")
        if status >= 400:
            raise RuntimeError(f"{path} вернул {status}: "
                               f"{resp.get_data(as_text=True)[:200]}")
    return json.loads(resp.get_data(as_text=True))


def _merge_employees(bonus_emps, kpi_emps, hours_emps):
    """Мёрж трёх источников по имени — порядок как в mergeAndRender()."""
    merged = []
    kpi_used = set()
    for be in bonus_emps:
        entry = {'name': be.get('name'), 'bonus': be, 'kpi': None, 'hours': None}
        for i, ke in enumerate(kpi_emps):
            if i not in kpi_used and _names_match(entry['name'], ke.get('employee_name')):
                entry['kpi'] = ke
                kpi_used.add(i)
                break
        merged.append(entry)

    for i, ke in enumerate(kpi_emps):
        if i not in kpi_used:
            merged.append({'name': ke.get('employee_name'), 'bonus': None,
                           'kpi': ke, 'hours': None})

    hours_used = set()
    for entry in merged:
        for i, he in enumerate(hours_emps):
            if i not in hours_used and _names_match(entry['name'], he.get('employee_name')):
                entry['hours'] = he
                hours_used.add(i)
                break
    for i, he in enumerate(hours_emps):
        if i not in hours_used:
            merged.append({'name': he.get('employee_name'), 'bonus': None,
                           'kpi': None, 'hours': he})
    return merged


def _total_salary(entry, taxi_rate):
    """Итог ЗП сотрудника — по нему сортируются колонки (recalcEmployeeTotals)."""
    b, k, h = entry.get('bonus'), entry.get('kpi'), entry.get('hours')
    hours_pay = (h or {}).get('total_pay') or 0
    day_shifts = (h or {}).get('day_shifts') or 0
    base = ((b or {}).get('bonus') or 0) \
        + ((b or {}).get('shift_handover_bonus') or 0) \
        - ((b or {}).get('penalty') or 0) \
        + ((k or {}).get('total_premium') or 0)
    return base + hours_pay + day_shifts * taxi_rate


def build_payload_for_month(app, month: str) -> dict:
    """Payload экспорта за месяц — точная копия того, что шлёт страница /salary."""
    from extensions import shifts_mgr
    from routes.employee import bonus_calculate, kpi_calculate

    date_from, date_to = month_bounds(month)
    body = {'date_from': date_from, 'date_to': date_to}

    # В начале месяца закрытых продаж в iiko ещё нет — расчёт отвечает 404.
    # Это не повод не выгружать месяц: часы и смены уже есть в графике, и
    # вкладка должна существовать с первого дня, наполняясь по ходу месяца.
    # Премии в этот момент честно равны нулю — они ещё не заработаны.
    try:
        bonus_data = _call_view(app, bonus_calculate, '/api/bonus-calculate',
                                method='POST', json=body)
    except NoDataForPeriod:
        bonus_data = {}
    try:
        kpi_data = _call_view(app, kpi_calculate, '/api/kpi-calculate',
                              method='POST', json=body)
    except NoDataForPeriod:
        kpi_data = {}
    hours_emps = shifts_mgr.get_hours_by_role_for_period(date_from, date_to)
    roles_raw = shifts_mgr.get_roles()

    from core.salary_layout import TAXI_RATE_PER_SHIFT
    merged = _merge_employees(bonus_data.get('employees') or [],
                              kpi_data.get('employees') or [],
                              hours_emps)
    merged.sort(key=lambda e: -_total_salary(e, TAXI_RATE_PER_SHIFT))

    kpi_config = kpi_data.get('kpi_config') or {}
    kpi_keys = _sorted_kpi_keys(kpi_config)
    kpi_names = [(kpi_config.get(k) or {}).get('name') or k for k in kpi_keys]

    # Тариф KPI = фонд / кол-во KPI; берём у первого сотрудника с KPI,
    # иначе из defaults — как в buildExportPayload()
    defaults = kpi_data.get('defaults') or {}
    base_per_kpi = next((e['kpi']['base_per_kpi'] for e in merged
                         if e.get('kpi') and e['kpi'].get('base_per_kpi')), None)
    if base_per_kpi is None:
        if defaults.get('kpi_pool') and kpi_keys:
            base_per_kpi = round(defaults['kpi_pool'] / len(kpi_keys))
        else:
            base_per_kpi = defaults.get('base_premium') or DEFAULT_BASE_PREMIUM

    roles = [{'name': r.get('name'),
              'rate': r.get('rate_per_hour') if r.get('rate_per_hour') is not None
              else DEFAULT_ROLE_RATE}
             for r in sorted(roles_raw, key=lambda r: r.get('sort_order') or 0)]

    employees = []
    for e in merged:
        b, k, h = e.get('bonus'), e.get('kpi'), e.get('hours')
        hours_by_role, pay_by_role = {}, {}
        for r in (h or {}).get('roles') or []:
            hours_by_role[r['role_name']] = r.get('hours')
            pay_by_role[r['role_name']] = r.get('pay')
        # «Количество смен» = дневные смены графика (база такси); фоллбэк —
        # кассовые смены iiko, если сотрудника нет в графике
        shifts_count = (h or {}).get('day_shifts') or 0 if h \
            else ((b or {}).get('shifts_count') or 0)
        koef = (k or {}).get('koef') or 0
        kpis = (k or {}).get('kpis') or {}
        kpi_premiums = [((kpis.get(key) or {}).get('intermediate_premium') or 0) * koef
                        if kpis.get(key) else 0 for key in kpi_keys]
        employees.append({
            'name': e.get('name'),
            'hours_by_role': hours_by_role,
            'pay_by_role': pay_by_role,
            'shifts_count': shifts_count,
            'handover_bonus': (b or {}).get('shift_handover_bonus') or 0,
            'day_plan_bonus': (b or {}).get('bonus') or 0,
            'kpi_premiums': kpi_premiums,
            'late_penalty': (b or {}).get('penalty') or 0,
            # Отпуск/доп доход/вычеты владелец ведёт в Excel — строки пустые
            'adjustments': {},
        })

    return {'month': month, 'kpi_names': kpi_names, 'base_per_kpi': base_per_kpi,
            'roles': roles, 'employees': employees}
