"""
Снимок данных личного кабинета `/me`: тяжёлые расчёты — раз в сутки, файлом на томе.

## Что это

Показатели, KPI и деньги на `/me` считаются НЕ на каждый заход страницы, а один
раз за прогон, сразу для всех сотрудников, и складываются в JSON на постоянном
томе. Причина арифметическая: все шесть OLAP-отчётов, из которых собираются
метрики сотрудника, группируются по ВСЕЙ сети (по `AuthUser` с алиасом в
`WaiterName`), а калькулятор потом выбирает из них одну строку. Значит посчитать
одного стоит столько же, сколько посчитать всех: предельная стоимость на
человека — ноль. Полный прогон месяца — 1-3 минуты, то есть синхронным
эндпоинтом это делать нельзя (`gunicorn --timeout 180`, docs/lessons.md урок 21).

Живые данные (смены, часы факта, календарь) страница берёт прямо из shifts.db и
в снимке не нуждаются — поэтому в день сбоя iiko человек всё равно видит
актуальный график, а устаревают только деньги и KPI. Эта граница «живое против
снимка» видна на странице подписями и разделением колонок.

## Файлы

| Файл | Роль |
|------|------|
| `core/me_snapshot.py` | этот модуль: чтение снимка, сборка, состояние прогонов, CLI |
| `core/me_identity.py` | `SNAPSHOT_SCHEMA`, правило имён (`strict_same_name`) — общий контракт |
| `core/me_snapshot_scheduler.py` | ночной прогон |
| `routes/me.py` | `/me` и `/api/me*` |
| `tests/test_me_snapshot.py` | тесты |

## Где лежит

`(/kultura если существует, иначе <repo>/data)/me_snapshot/`:
- `month__YYYY-MM.json` — один файл на месяц;
- `refresh_state.json` — состояние прогонов (кулдаун, последняя ошибка).

Каталог выбирается тем же способом, что кэш месячного отчёта
(`core/monthly_report.py::_cache_dir`). Файл на месяц, а не один общий: запись
заменяет файл целиком (`os.replace`), поэтому сбой на текущем месяце физически
не может испортить закрытый предыдущий.

## Как работает (чтение)

`read_month(month)` возвращает словарь снимка или `{}`. Любая ошибка (файла нет,
битый JSON, нет прав) — это `{}`, а не исключение: отсутствие снимка штатно,
страница в этом случае показывает живые блоки и объяснение вместо денег. Нулей
вместо денег не показываем никогда — ноль читается как «мне не начислили».

Совместимость версий: `_schema` сверяется читателем (`core/me_identity.py`).
Незнакомые лишние ключи игнорируются, отсутствующие необязательные берут
дефолты — у людей неделями живут открытые вкладки со старым JS, и новый формат
не должен ломать старую страницу (docs/lessons.md про откат деплоя вкладкой).

## Changelog

- 2026-08-13 — модуль создан: чтение снимка и состояние прогонов.
"""

import json
import os
import re
from typing import Dict, List

from core.me_identity import SNAPSHOT_SCHEMA
from core.msk_time import today as msk_today
from core.storage_paths import LOCAL_DATA_DIR, RENDER_DISK_DIR

SNAPSHOT_SUBDIR = 'me_snapshot'
MONTH_FILE_PREFIX = 'month__'
REFRESH_STATE_FILE = 'refresh_state.json'

MONTH_RE = re.compile(r'\d{4}-(0[1-9]|1[0-2])\Z')

# Нормы месяца для шкал «смены N/15» и «часы N/113». Дублируют то, что до сих
# пор было только на фронте (static/js/schedule/screens.js) — отдаём их с бэка,
# чтобы не заводить второй источник одного и того же числа.
from core.schedule_plans import HOURS_NORM, SHIFT_NORM  # noqa: E402


def valid_month(month) -> bool:
    """'2026-08' — да; '2026-13', '2026-8', мусор и None — нет."""
    return isinstance(month, str) and bool(MONTH_RE.fullmatch(month))


def current_month() -> str:
    """Текущий месяц по МОСКВЕ.

    Именно msk_time, а не date.today(): в прод-образе нет системного tzdata, и
    наивная дата с 00:00 до 03:00 МСК отстаёт на день — в ночь первого числа
    «текущим» стал бы прошлый месяц (docs/lessons.md, core/msk_time.py).
    """
    return msk_today().strftime('%Y-%m')


def snapshot_dir() -> str:
    """Каталог снимков. Паттерн `_cache_dir` из core/monthly_report.py."""
    base = RENDER_DISK_DIR if os.path.exists(RENDER_DISK_DIR) else LOCAL_DATA_DIR
    return os.path.join(base, SNAPSHOT_SUBDIR)


def month_path(month: str) -> str:
    return os.path.join(snapshot_dir(), f'{MONTH_FILE_PREFIX}{month}.json')


def refresh_state_path() -> str:
    return os.path.join(snapshot_dir(), REFRESH_STATE_FILE)


def read_month(month: str) -> Dict:
    """Снимок месяца с диска или {}.

    Никогда не бросает: отсутствие и порча файла — штатные состояния, которые
    страница показывает словами. Отдельно ловим не-словарь на верхнем уровне:
    полуобрезанный или подменённый файл не должен дойти до резолвера как список.
    """
    if not valid_month(month):
        return {}
    path = month_path(month)
    try:
        if not os.path.exists(path):
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[ME-SNAPSHOT WARNING] ne udalos prochitat {path}: {e}")
        return {}


def available_months() -> List[str]:
    """Месяцы, для которых есть файл снимка, новые сначала.

    Текущий месяц присутствует всегда, даже если файла ещё нет: страница обязана
    открываться в первый день месяца и показывать живые блоки со объяснением,
    что снимок ещё не собран.
    """
    months = set()
    try:
        for name in os.listdir(snapshot_dir()):
            if not (name.startswith(MONTH_FILE_PREFIX) and name.endswith('.json')):
                continue
            m = name[len(MONTH_FILE_PREFIX):-len('.json')]
            if valid_month(m):
                months.add(m)
    except OSError:
        pass
    months.add(current_month())
    return sorted(months, reverse=True)


def read_refresh_state() -> Dict:
    """Состояние прогонов: {last_started_at, last_finished_at, last_error, tag}.

    Отдельный файл, а не поле снимка: при сбое источника снимок сознательно НЕ
    перезаписывается (иначе смешались бы генерации), а факт попытки и её ошибка
    зафиксироваться обязаны.
    """
    try:
        with open(refresh_state_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def snapshot_meta(snapshot: Dict, *, expected_schema: int = SNAPSHOT_SCHEMA,
                  stale_hours: float = None) -> Dict:
    """Служебная шапка снимка для страницы: статус, дата, свежесть.

    `status`: 'missing' (файла нет) | 'schema_mismatch' | 'ok'. Дальше резолвер
    личности решает, есть ли в этом снимке строка конкретного человека —
    статусы не смешиваются: «снимка нет» и «в снимке нет меня» это разные
    сообщения с разными действиями.
    """
    if not snapshot:
        return {'status': 'missing', 'refreshed_at': None, 'refreshed_by': None,
                'schema': None, 'stale': False, 'age_hours': None,
                'source_status': {}}

    status = 'ok' if snapshot.get('_schema') == expected_schema else 'schema_mismatch'
    refreshed_at = snapshot.get('_refreshed_at')
    age = _age_hours(refreshed_at)
    limit = STALE_HOURS if stale_hours is None else stale_hours
    return {
        'status': status,
        'refreshed_at': refreshed_at,
        'refreshed_by': snapshot.get('_refreshed_by'),
        'schema': snapshot.get('_schema'),
        'age_hours': age,
        'stale': bool(age is not None and age > limit),
        'source_status': snapshot.get('_source_status') or {},
    }


def _age_hours(iso_ts):
    """Сколько часов назад собран снимок. None, если метки нет или она битая."""
    if not iso_ts:
        return None
    try:
        from datetime import datetime
        from core.msk_time import now as msk_now
        ts = datetime.fromisoformat(iso_ts)
        if ts.tzinfo is None:
            # Метку пишем с зоной; наивная — снимок от старой версии.
            from core.msk_time import MOSCOW_TZ
            ts = ts.replace(tzinfo=MOSCOW_TZ)
        return round((msk_now() - ts).total_seconds() / 3600, 1)
    except Exception:
        return None


# После этого возраста подпись «данные на ...» становится заметной: ночной
# прогон раз в сутки, поэтому 26 часов означают, что как минимум один прогон
# не состоялся.
STALE_HOURS = float(os.environ.get('ME_SNAPSHOT_STALE_HOURS', '26'))


def norms() -> Dict:
    """Нормы месяца — единственный источник для шкал страницы."""
    return {'shift_norm': SHIFT_NORM, 'hours_norm': HOURS_NORM}


# ==========================================================================
# СБОРКА СНИМКА
# ==========================================================================
#
# Порядок и стоимость (замеры — docs/lessons.md, урок 28):
#   1. bonus_calculate  — iiko auth + справочник + кассовые смены       10-40 с
#   2. kpi_calculate    — ещё auth + кассовые смены + 4 OLAP            30-70 с
#   3. hours/roles      — SQLite                                        мс
#   4. 6 OLAP-отчётов метрик, параллельно                               20-60 с
#   5. цикл по сотрудникам через EmployeeMetricsCalculator              мс
#   6. мёрж + деньги + запись файла                                     мс
# Итого 1-3 минуты на месяц. Отсюда фоновый прогон, а не эндпоинт.
#
# Правило «ВСЁ ИЛИ НИЧЕГО»: если источник сбойнул (не «данных нет», а именно
# сбой), месяц НЕ перезаписывается — на диске остаётся прежний файл со своей
# прежней датой. Соблазн «записать что получилось, остальное взять из старого»
# отклонён: это тихо смешивает генерации (свежие часы с позавчерашней
# KPI-премией), и итог не сходится ни с одной датой. У проекта уже была травма
# ровно этого рода — лист ЗП расходился со страницей на 10 500 (см.
# core/salary_layout.py). Ошибка фиксируется в refresh_state.json.

# Тарифы — из единственного места, где они заданы (раскладка ЗП).
from core.salary_layout import (  # noqa: E402
    DAY_PLAN_RATE, HANDOVER_RATE, TAXI_RATE_PER_SHIFT,
)

# Прогрессивный шаг штрафа за опоздание: 250, 500, 750... Значение живёт в
# routes/employee.py (там же и считается) — здесь только для подписи формулы.
LATE_PENALTY_STEP = 250

# Доля перевыполнения дневного плана, которая идёт в премию.
DAY_PLAN_OVER_SHARE = 0.05


def build_month(app, month: str, *, tag: str = 'manual') -> Dict:
    """Собрать и записать снимок месяца. Возвращает отчёт о прогоне.

    Отчёт: {month, written: bool, employees: int, source_status: {...},
    error: str|None, seconds: float}. Исключения наружу не пробрасываются —
    прогон одного месяца не должен ронять прогон остальных.
    """
    import time
    from core.me_identity import norm_name as _norm

    started = time.time()
    report = {'month': month, 'written': False, 'employees': 0,
              'source_status': {}, 'error': None, 'seconds': 0.0}
    if not valid_month(month):
        report['error'] = f'nekorrektny mesyac: {month}'
        return report

    try:
        date_from, date_to = _month_bounds(month)
        status = {'bonus': 'ok', 'kpi': 'ok', 'hours': 'ok', 'olap_metrics': 'ok'}

        bonus_data, status['bonus'] = _call_source(app, 'bonus_calculate',
                                                  date_from, date_to)
        kpi_data, status['kpi'] = _call_source(app, 'kpi_calculate',
                                               date_from, date_to)

        from extensions import shifts_mgr
        hours_emps = shifts_mgr.get_hours_by_role_for_period(date_from, date_to)
        roles_raw = shifts_mgr.get_roles()

        bonus_emps = (bonus_data or {}).get('employees') or []
        kpi_emps = (kpi_data or {}).get('employees') or []

        # OLAP метрик дёргаем ТОЛЬКО если есть кому их приписать: в начале месяца
        # закрытых смен нет, и десять сетевых запросов ушли бы в пустоту.
        olap_raw, status['olap_metrics'] = ({}, 'no_data')
        if bonus_emps or kpi_emps:
            olap_raw, status['olap_metrics'] = _fetch_metric_reports(date_from, date_to)

        if status['bonus'] == 'error' or status['kpi'] == 'error' \
                or status['olap_metrics'] == 'error':
            report['source_status'] = status
            report['error'] = ('istochnik dannyh sboynul, mesyac ne perezapisan: '
                               + ', '.join(f'{k}={v}' for k, v in status.items()))
            return report

        snapshot = _assemble(month, date_from, date_to, bonus_emps, kpi_emps,
                             hours_emps, roles_raw, kpi_data or {}, olap_raw,
                             status, tag, norm_fn=_norm)
        _write_month(month, snapshot)
        report['written'] = True
        report['employees'] = len(snapshot['employees'])
        report['source_status'] = status
        return report
    except Exception as e:
        import traceback
        traceback.print_exc()
        report['error'] = f'{type(e).__name__}: {e}'
        return report
    finally:
        report['seconds'] = round(time.time() - started, 1)


def _month_bounds(month):
    from core.salary_payload import month_bounds
    return month_bounds(month)


def _call_source(app, view_name, date_from, date_to):
    """Вызвать расчёт премий или KPI как view-функцию. -> (данные, статус).

    Через `_call_view` (core/salary_payload.py), а не по HTTP: планировщик,
    дёргающий свой же защищённый роут, получает 401 — этот баг у проекта уже был
    (docs/lessons.md, авторефреш ЧЗ молча стоял месяц).

    404 «нет данных за период» — НЕ сбой: в начале месяца продажи ещё не закрыты,
    премии честно нулевые, а часы и такси всё равно берутся из графика.
    """
    from core.salary_payload import NoDataForPeriod, _call_view
    from routes import employee as emp_routes

    view = getattr(emp_routes, view_name)
    body = {'date_from': date_from, 'date_to': date_to}
    try:
        return _call_view(app, view, f'/api/{view_name}', method='POST', json=body), 'ok'
    except NoDataForPeriod:
        return {}, 'no_data'
    except Exception as e:
        print(f"[ME-SNAPSHOT] {view_name} sboy: {e}")
        return {}, 'error'


def _fetch_metric_reports(date_from, date_to):
    """Шесть сетевых OLAP-отчётов метрик — один раз на всех. -> (данные, статус).

    Те же геттеры, что у `/api/employee-analytics` (routes/employee.py), и с тем
    же `bar_name=None`: отчёты группируются по всей сети, поэтому одна выборка
    обслуживает всех сотрудников. Именно это делает снимок дешёвым.

    `date_to + 1 день`: OLAP трактует правую границу как исключающую, а бары
    работают за полночь.

    Пустой ответ (`{'data': []}`) — не ошибка, а «продаж не было»: метрики
    считаются в нули. `None` — сбой (таймаут, не-200), и тогда месяц не пишется:
    нули вместо реальных продаж выглядели бы как «человек плохо работал».
    """
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timedelta

    from core.olap_reports import OlapReports

    olap_to = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    olap = OlapReports()
    if not olap.connect():
        print("[ME-SNAPSHOT] OLAP: podklyuchenie ne udalos")
        return {}, 'error'
    try:
        jobs = {
            'aggregated': olap.get_employee_aggregated_metrics,
            'draft': olap.get_draft_sales_by_waiter_report,
            'bottles': olap.get_bottles_sales_by_waiter_report,
            'kitchen': olap.get_kitchen_sales_by_waiter_report,
            'cancelled': olap.get_cancelled_orders_by_waiter,
            'loyalty': olap.get_new_loyalty_cards_by_waiter,
        }
        out = {}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {key: pool.submit(fn, date_from, olap_to) for key, fn in jobs.items()}
            for key, fut in futures.items():
                try:
                    out[key] = fut.result()
                except Exception as e:
                    print(f"[ME-SNAPSHOT] OLAP {key} sboy: {e}")
                    out[key] = None
    finally:
        olap.disconnect()

    if any(out.get(k) is None for k in jobs):
        return out, 'error'
    return out, 'ok'


def _olap_names(aggregated) -> List[str]:
    """Имена сотрудников из сводного OLAP-отчёта.

    ВНИМАНИЕ на форму данных: `get_employee_aggregated_metrics` отдаёт НЕ
    `{'data': [...]}`, как остальные геттеры, а уже свёрнутый словарь
    `{имя: {метрики}}` (см. core/olap_reports.py). Именно этот словарь ждёт
    `EmployeeMetricsCalculator.calculate`, поэтому имена берём его ключами.
    Обе формы поддержаны: сырой ответ пригодится, если геттер когда-нибудь
    перестанет свёртывать.
    """
    if not aggregated:
        return []
    names = []
    if isinstance(aggregated, dict) and 'data' in aggregated:
        for row in aggregated.get('data') or []:
            name = (row or {}).get('WaiterName') or (row or {}).get('AuthUser')
            if name and name not in names:
                names.append(name)
        return names
    if isinstance(aggregated, dict):
        for name in aggregated:
            if name and name not in names:
                names.append(name)
    return names


def resolve_olap_name(name_iiko: str, olap_names: List[str], *, norm_fn) -> str:
    """Имя из справочника iiko -> имя, под которым человек лежит в OLAP.

    Нужно потому, что `EmployeeMetricsCalculator._filter_by_employee`
    (core/employee_analysis.py) сравнивает имена СТРОГО (`==`). Страница
    `/employee` об это не спотыкается, так как берёт имя из самого OLAP, а
    снимок идёт от справочника iiko, где порядок слов может быть другим
    («Новаев Артемий» против «Артемий Новаев»).

    Правила по убыванию строгости; подмножество принимается ТОЛЬКО при
    единственном кандидате. Существующий `_find_employee_in_olap`
    (routes/employee.py) берёт первое совпадение — это и есть способ приписать
    человеку чужие продажи. Не сошлось -> None, и метрики не заполняются:
    нули читались бы как «плохо работал», а это «не сопоставили».
    """
    if not name_iiko:
        return None
    if name_iiko in olap_names:
        return name_iiko
    target = norm_fn(name_iiko)
    exact = [n for n in olap_names if norm_fn(n) == target]
    if len(exact) == 1:
        return exact[0]
    words = set(name_iiko.lower().split())
    if len(words) >= 2:
        supersets = [n for n in olap_names if words <= set(n.lower().split())]
        if len(supersets) == 1:
            return supersets[0]
    return None


def hours_trust(hours_row: Dict, my_id: str, my_names: List[str], *,
                registry_names: List[str], strict_fn, unique_fn) -> str:
    """Можно ли поручиться, что эта строка часов — про этого человека.

    'id'          — сошлось по стабильному идентификатору, доверяем;
    'name_strict' — id нет, но полное имя совпало и в реестре оно единственное;
    'unsafe'      — всё остальное.

    Зачем вердикт вообще: `get_hours_by_role_for_period` группирует по
    `COALESCE(employee_id, employee_name)` (core/shifts_manager.py), поэтому
    человек, у которого часть смен без id, распадается на ДВЕ строки, а два
    разных человека с одинаковым именем и без id — склеиваются в одну. При
    'unsafe' оплата часов и такси исключаются из итога: показать сумму, за
    которую приложение не может поручиться, хуже, чем назвать её отсутствие.
    """
    if not hours_row:
        return 'unsafe'
    row_id = str(hours_row.get('employee_id') or '').strip()
    if row_id and my_id and row_id == my_id:
        return 'id'
    if row_id:
        return 'unsafe'      # id есть, но чужой
    row_name = hours_row.get('employee_name')
    if any(strict_fn(row_name, n) for n in my_names if n) and unique_fn(row_name, registry_names):
        return 'name_strict'
    return 'unsafe'


def _assemble(month, date_from, date_to, bonus_emps, kpi_emps, hours_emps,
              roles_raw, kpi_data, olap_raw, status, tag, *, norm_fn) -> Dict:
    """Собрать структуру снимка из готовых данных источников."""
    from core.employee_analysis import EmployeeMetricsCalculator
    from core.kpi_calculator import AVAILABLE_METRICS
    from core.me_identity import (SNAPSHOT_SCHEMA, is_name_unique,
                                  strict_same_name)
    from core.msk_time import now as msk_now
    from core.salary_payload import _merge_employees, _sorted_kpi_keys

    merged = _merge_employees(bonus_emps, kpi_emps, hours_emps)

    kpi_config = kpi_data.get('kpi_config') or {}
    kpi_keys = _sorted_kpi_keys(kpi_config)
    kpi_defaults = kpi_data.get('defaults') or {}

    roles = [{'name': r.get('name'),
              'rate': r.get('rate_per_hour') if r.get('rate_per_hour') is not None else 0}
             for r in sorted(roles_raw, key=lambda r: r.get('sort_order') or 0)]

    olap_names = _olap_names(olap_raw.get('aggregated'))
    loyalty = olap_raw.get('loyalty') or {}
    registry_names = [e.get('name') for e in merged if e.get('name')]

    employees = {}
    unlinked = []
    for entry in merged:
        emp_id = str(entry.get('employee_id') or '').strip()
        b, k, h = entry.get('bonus'), entry.get('kpi'), entry.get('hours')

        # Строка без стабильного id в `employees` не попадает вообще: ключ снимка
        # обязан быть идентификатором, иначе безымянную строку можно выдать за
        # чью-то. Такие строки уходят отдельным списком и показываются человеку
        # как явный дефицит с суммой и способом починить.
        if not emp_id:
            if h:
                unlinked.append({
                    'employee_name': h.get('employee_name'),
                    'total_hours': h.get('total_hours'),
                    'total_pay': h.get('total_pay'),
                    'day_shifts': h.get('day_shifts'),
                    'shifts_without_fact': h.get('shifts_without_fact'),
                })
            continue

        name_iiko = entry.get('name') or (h or {}).get('employee_name') or ''
        name_olap = resolve_olap_name(name_iiko, olap_names, norm_fn=norm_fn)

        trust = hours_trust(h, emp_id, [name_iiko, (h or {}).get('employee_name')],
                            registry_names=registry_names,
                            strict_fn=strict_same_name, unique_fn=is_name_unique)

        metrics = _metrics_for(EmployeeMetricsCalculator, name_olap, b, olap_raw,
                               loyalty) if name_olap else {'status': 'no_olap_name'}
        kpi_block = _kpi_for(k, kpi_keys, kpi_config)
        hours_block = _hours_for(h, trust)
        money = _money_for(b, k, h, trust)

        employees[emp_id] = {
            'employee_id': emp_id,
            'name_iiko': name_iiko,
            'name_olap': name_olap,
            'name_schedule': (h or {}).get('employee_name') or name_iiko,
            'metrics': metrics,
            'kpi': kpi_block,
            'hours': hours_block,
            'money': money,
        }

    base_per_kpi = _base_per_kpi(merged, kpi_defaults, kpi_keys)
    return {
        '_schema': SNAPSHOT_SCHEMA,
        '_month': month,
        '_refreshed_at': msk_now().isoformat(timespec='seconds'),
        '_refreshed_by': tag,
        '_period': {'from': date_from, 'to': date_to},
        '_source_status': dict(status),
        'norms': norms(),
        'rates': {
            'taxi_per_shift': TAXI_RATE_PER_SHIFT,
            'handover_per_day': HANDOVER_RATE,
            'day_plan_base': DAY_PLAN_RATE,
            'day_plan_over_share': DAY_PLAN_OVER_SHARE,
            'late_penalty_step': LATE_PENALTY_STEP,
        },
        'roles': roles,
        'kpi_meta': {
            'keys': kpi_keys,
            'names': [(kpi_config.get(kk) or {}).get('name') or kk for kk in kpi_keys],
            'base_per_kpi': base_per_kpi,
            'kpi_pool': kpi_defaults.get('kpi_pool'),
            'norm_shifts': kpi_defaults.get('norm_shifts') or SHIFT_NORM,
            'max_ratio': kpi_defaults.get('max_ratio'),
            'metrics_catalog': AVAILABLE_METRICS,
        },
        'employees': employees,
        'unlinked_hours': unlinked,
    }


def _base_per_kpi(merged, defaults, kpi_keys):
    """Тариф одного KPI: фонд / число показателей. Как в build_payload_for_month."""
    for e in merged:
        k = e.get('kpi') or {}
        if k.get('base_per_kpi'):
            return k['base_per_kpi']
    if defaults.get('kpi_pool') and kpi_keys:
        return round(defaults['kpi_pool'] / len(kpi_keys))
    return defaults.get('base_premium')


def _metrics_for(calculator_cls, name_olap, bonus_row, olap_raw, loyalty):
    """Метрики дашборда сотрудника — тем же калькулятором, что у /employee.

    Смены, часы и опоздания приходят готовыми из расчёта премий (кассовые смены
    iiko), план — оттуда же: так число на /me совпадает с /employee и /salary, а
    не пересчитывается по-своему.
    """
    b = bonus_row or {}
    try:
        metrics = calculator_cls().calculate(
            employee_name=name_olap,
            aggregated_data=olap_raw.get('aggregated'),
            draft_data=olap_raw.get('draft'),
            bottles_data=olap_raw.get('bottles'),
            kitchen_data=olap_raw.get('kitchen'),
            cancelled_data=olap_raw.get('cancelled'),
            plan_revenue=b.get('plan_revenue') or 0,
            shifts_count_override=b.get('shifts_count') or 0,
            total_hours_override=b.get('total_hours') or 0,
            late_count_override=b.get('late_count') or 0,
            loyalty_cards_count=(loyalty or {}).get(name_olap, 0),
            total_revenue_override=None,
        )
    except Exception as e:
        print(f"[ME-SNAPSHOT] metriki dlya '{name_olap}' ne poschitany: {e}")
        return {'status': 'error'}
    metrics['status'] = 'ok'
    return metrics


def _kpi_for(kpi_row, kpi_keys, kpi_config):
    """Блок KPI: факт, цель, минимум, множитель и премия по каждому показателю.

    Премия одного KPI = промежуточная премия × коэффициент смен. Коэффициент
    применяется к итогу всех KPI (core/kpi_calculator.py), поэтому по каждому
    показателю он тоже разложен — иначе сумма разложения не сходилась бы с итогом.
    """
    if not kpi_row:
        return {'status': 'no_data', 'items': [], 'total_premium': 0, 'koef': 0}
    koef = kpi_row.get('koef') or 0
    kpis = kpi_row.get('kpis') or {}
    items = []
    for key in (kpi_keys or sorted(kpis)):
        src = kpis.get(key)
        if not src:
            continue
        inter = src.get('intermediate_premium') or 0
        items.append({
            'key': key,
            'name': src.get('name') or (kpi_config.get(key) or {}).get('name') or key,
            'metric': src.get('metric'),
            'fact': src.get('fact'),
            'target': src.get('target'),
            'min': src.get('min'),
            'ratio': src.get('capped_ratio', src.get('ratio')),
            'intermediate_premium': round(inter, 2),
            'premium': round(inter * koef, 2),
        })
    return {
        'status': 'ok',
        'koef': koef,
        'total_shifts': kpi_row.get('total_shifts'),
        'shifts_per_location': kpi_row.get('shifts_per_location') or {},
        'base_per_kpi': kpi_row.get('base_per_kpi'),
        'kpi_pool': kpi_row.get('kpi_pool'),
        'items': items,
        'total_premium': round(kpi_row.get('total_premium') or 0, 2),
    }


def _hours_for(hours_row, trust):
    """Часы и оплата по ролям из графика (fact_minutes × ставка роли)."""
    if not hours_row:
        return {'trust': 'none', 'total_hours': 0, 'total_pay': 0, 'day_shifts': 0,
                'shifts_with_fact': 0, 'shifts_without_fact': 0, 'by_role': []}
    return {
        'trust': trust,
        'employee_name': hours_row.get('employee_name'),
        'total_hours': hours_row.get('total_hours') or 0,
        'total_pay': hours_row.get('total_pay') or 0,
        'day_shifts': hours_row.get('day_shifts') or 0,
        'shifts_with_fact': hours_row.get('shifts_with_fact') or 0,
        'shifts_without_fact': hours_row.get('shifts_without_fact') or 0,
        'by_role': [{'role_name': r.get('role_name'),
                     'rate_per_hour': r.get('rate_per_hour'),
                     'hours': r.get('hours'), 'pay': r.get('pay')}
                    for r in (hours_row.get('roles') or [])],
    }


def _money_for(bonus_row, kpi_row, hours_row, trust) -> Dict:
    """Деньги «начислено на сегодня» с разложением по составляющим.

    ИНВАРИАНТ: `total` обязан совпадать с формулой страницы /salary
    (`recalcEmployeeTotals` в templates/bonus.html):

        total = часы×ставка + такси + премия за передачу смены
                + премия за дневной план + KPI-премия − штраф за опоздания

    Расхождение означает, что кабинет разошёлся с тем, по чему платят; на это
    есть отдельный тест. Строки, которые владелец ведёт в Excel (отпуск, доп
    доход, вычеты инвентаризации, «мосты», зачёт официального такси), в итог НЕ
    входят по построению — приложение их просто не знает, и на странице это
    сказано словами.

    При недостоверной привязке часов (trust='unsafe') оплата часов и такси
    исключаются из итога и перечисляются в `excluded_components`.
    """
    b, k, h = bonus_row or {}, kpi_row or {}, hours_row or {}
    hours_pay = h.get('total_pay') or 0
    day_shifts = h.get('day_shifts') or 0
    taxi_sum = day_shifts * TAXI_RATE_PER_SHIFT
    handover = b.get('shift_handover_bonus') or 0
    day_plan = b.get('bonus') or 0
    late = b.get('penalty') or 0
    kpi_sum = k.get('total_premium') or 0

    excluded = []
    if trust == 'unsafe':
        excluded = ['hours_pay', 'taxi']

    total = handover + day_plan + kpi_sum - late
    if 'hours_pay' not in excluded:
        total += hours_pay
    if 'taxi' not in excluded:
        total += taxi_sum

    late_count = b.get('late_count') or 0
    return {
        'hours_pay': round(hours_pay, 2),
        'taxi': {'day_shifts': day_shifts, 'rate': TAXI_RATE_PER_SHIFT,
                 'sum': round(taxi_sum, 2)},
        'handover': {'base_days': b.get('shift_handover_base_days') or 0,
                     'paid_days': b.get('shift_handover_paid_days') or 0,
                     'unpaid_days': b.get('shift_handover_unpaid_days') or 0,
                     'manual_days': b.get('shift_handover_manual_days') or 0,
                     'rate': HANDOVER_RATE, 'sum': round(handover, 2)},
        'day_plan': {'sum': round(day_plan, 2),
                     'days_paid': _days_over_plan(b),
                     'base_per_day': DAY_PLAN_RATE,
                     'overperformance': b.get('overperformance') or 0,
                     'over_share': DAY_PLAN_OVER_SHARE},
        'kpi': {'sum': round(kpi_sum, 2), 'koef': k.get('koef') or 0},
        'late': {'count': late_count, 'step': LATE_PENALTY_STEP,
                 'sum': round(late, 2), 'dates': _late_dates(b)},
        'shifts_count': b.get('shifts_count') or 0,
        'total': round(total, 2),
        'excluded_components': excluded,
    }


def _days_over_plan(bonus_row) -> int:
    """Сколько смен дали премию за дневной план (перевыполнение > 0)."""
    return sum(1 for d in (bonus_row or {}).get('days') or []
               if (d.get('overperformance') or 0) > 0)


def _late_dates(bonus_row) -> List[str]:
    """Даты опозданий — чтобы человек видел, за что вычет, а не только сумму.

    Массив дней (`days`) в снимок целиком не пишем: он крупный, а из него нужны
    только эти даты и счётчик оплаченных смен.
    """
    return [d.get('date') for d in (bonus_row or {}).get('days') or [] if d.get('is_late')]


def _write_month(month: str, snapshot: Dict):
    """Атомарная запись файла месяца под cross-worker локом.

    `atomic_write_json` (tmp + fsync + os.replace) — иначе SIGTERM посреди записи
    оставляет обрезанный JSON; `file_lock` — иначе два воркера пишут
    одновременно. Оба требования из docs/lessons.md (уроки 22 и 24).
    """
    from core.json_store import atomic_write_json, file_lock

    path = month_path(month)
    os.makedirs(snapshot_dir(), exist_ok=True)
    with file_lock(path + '.lock'):
        atomic_write_json(path, snapshot)


def write_refresh_state(**fields):
    """Обновить refresh_state.json, сохранив прежние поля.

    Read-modify-write под тем же локом: два воркера иначе затрут правки друг
    друга (last-writer-wins, docs/lessons.md урок 24).
    """
    from core.json_store import atomic_write_json, file_lock

    path = refresh_state_path()
    os.makedirs(snapshot_dir(), exist_ok=True)
    with file_lock(path + '.lock'):
        state = read_refresh_state()
        state.update(fields)
        atomic_write_json(path, state)
    return state


def months_to_build(today=None, prev_until_day: int = None) -> List[str]:
    """Какие месяцы пересчитывать: текущий всегда, предыдущий — первые дни.

    Та же логика, что `months_to_sync` в core/salary_scheduler.py: закрытый
    месяц ещё неделю подтягивает поздние правки графика и кассы, после чего
    заморожен (файл остаётся, но не пересчитывается).
    """
    day = today or msk_today()
    limit = PREV_UNTIL_DAY if prev_until_day is None else prev_until_day
    months = [day.strftime('%Y-%m')]
    if day.day <= limit:
        from core.salary_payload import previous_month
        months.append(previous_month(months[0]))
    return months


PREV_UNTIL_DAY = int(os.environ.get('ME_SNAPSHOT_PREV_UNTIL_DAY', '7'))


def run_build(app, months: List[str] = None, *, tag: str = 'manual') -> Dict:
    """Собрать снимки за несколько месяцев. Пишет refresh_state.json.

    Сбой одного месяца не мешает остальным (как sync_once в salary_scheduler).
    """
    from core.msk_time import now as msk_now

    months = months or months_to_build()
    started_at = msk_now().isoformat(timespec='seconds')
    write_refresh_state(last_started_at=started_at, tag=tag, running=True,
                        last_error=None)
    _progress(started_at=started_at, total=len(months), done=0, current_month=None)
    reports = {}
    try:
        for m in months:
            _progress(current_month=m)
            rep = build_month(app, m, tag=tag)
            reports[m] = rep
            _progress(done=len([r for r in reports.values()]))
            print(f"[ME-SNAPSHOT] {m}: written={rep['written']} "
                  f"employees={rep['employees']} za {rep['seconds']}s"
                  + (f" error={rep['error']}" if rep['error'] else ''))
    finally:
        errors = [f"{m}: {r['error']}" for m, r in reports.items() if r.get('error')]
        finished_at = msk_now().isoformat(timespec='seconds')
        write_refresh_state(last_finished_at=finished_at, running=False,
                           last_error='; '.join(errors) if errors else None)
        _progress(finished_at=finished_at, current_month=None,
                  error='; '.join(errors) if errors else None)
    return reports


def _progress(**fields):
    """Обновить in-process прогресс (для поллинга кнопкой «Обновить»).

    Определён здесь, а состояние — ниже, в блоке ручного пересчёта: ночной
    прогон и ручной пишут один и тот же прогресс, поэтому функция общая.
    """
    with _STATE_LOCK:
        _STATE.update(fields)


# ==========================================================================
# РУЧНОЙ ПЕРЕСЧЁТ («Обновить сейчас»)
# ==========================================================================
#
# Три уровня защиты, и каждый закрывает свою дыру:
#   1. cross-worker lock-файл (O_EXCL) со stale-reclaim по mtime — потому что в
#      проде gunicorn 2 воркера = 2 процесса, и threading.Lock между ними не
#      работает (docs/lessons.md урок 24). Каталог data/ смонтирован на хост и
#      переживает рестарт контейнера — поэтому reclaim обязателен, иначе один
#      жёсткий kill заблокировал бы кнопку навсегда.
#   2. in-process состояние — прогресс для поллинга и защита от двух кликов в
#      одном воркере (как _SYNC_STATE в core/guest_sync.py; там это единственная
#      защита, и это дыра, которую здесь закрывает пункт 1).
#   3. кулдаун по last_started_at из refresh_state.json — общий для всех
#      воркеров. Именно по started, а не по _refreshed_at снимка: при сбое
#      источника снимок не перезаписывается, и кулдаун по нему не остановил бы
#      серию нажатий на нерабочем iiko.

import threading  # noqa: E402

LOCK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
REFRESH_LOCK = os.path.join(LOCK_DIR, '.me_snapshot_refresh.lock')

COOLDOWN_MIN = int(os.environ.get('ME_REFRESH_COOLDOWN_MIN', '30'))
STALE_LOCK_SEC = int(os.environ.get('ME_REFRESH_STALE_SEC', '1800'))

_STATE = {'running': False, 'tag': None, 'started_at': None, 'finished_at': None,
          'current_month': None, 'done': 0, 'total': 0, 'error': None}
_STATE_LOCK = threading.Lock()


def get_progress() -> Dict:
    """Копия состояния прогона (под локом — читают несколько потоков)."""
    with _STATE_LOCK:
        return dict(_STATE)


def cooldown_left_sec() -> int:
    """Сколько секунд до следующего разрешённого пересчёта. 0 — можно сейчас."""
    from datetime import datetime

    from core.msk_time import MOSCOW_TZ, now as msk_now

    started = read_refresh_state().get('last_started_at')
    if not started:
        return 0
    try:
        ts = datetime.fromisoformat(started)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=MOSCOW_TZ)
    except (TypeError, ValueError):
        return 0
    passed = (msk_now() - ts).total_seconds()
    left = COOLDOWN_MIN * 60 - passed
    return int(left) if left > 0 else 0


def _acquire_refresh_lock() -> bool:
    """Взять cross-worker лок. False — уже занят живым прогоном.

    Брошенный лок (mtime старше STALE_LOCK_SEC) снимаем: процесс мог умереть по
    OOM или рестарту, и вечный лок оставил бы кнопку мёртвой.
    """
    import time

    os.makedirs(LOCK_DIR, exist_ok=True)
    try:
        if os.path.exists(REFRESH_LOCK):
            age = time.time() - os.path.getmtime(REFRESH_LOCK)
            if age > STALE_LOCK_SEC:
                print(f"[ME-SNAPSHOT] broshenny lock ({int(age)}s) snyat")
                os.unlink(REFRESH_LOCK)
            else:
                return False
    except OSError:
        return False
    try:
        fd = os.open(REFRESH_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, f'{os.getpid()}\n'.encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False       # гонку выиграл другой воркер
    except OSError as e:
        print(f"[ME-SNAPSHOT] lock ne sozdan: {e}")
        return False


def _release_refresh_lock():
    try:
        os.unlink(REFRESH_LOCK)
    except OSError:
        pass


def start_background_refresh(app, months: List[str] = None, *, tag: str = 'manual'):
    """Запустить пересчёт в фоне. -> (started: bool, reason: str, info: dict).

    reason: '' при старте, иначе 'cooldown' | 'already_running'. Синхронного
    пути нет вообще: прогон 1-6 минут против `gunicorn --timeout 180` убил бы
    воркер (docs/lessons.md урок 21).
    """
    left = cooldown_left_sec()
    if left > 0:
        return False, 'cooldown', {'retry_after_sec': left,
                                   'progress': get_progress()}
    with _STATE_LOCK:
        if _STATE['running']:
            return False, 'already_running', {'progress': dict(_STATE)}
    if not _acquire_refresh_lock():
        return False, 'already_running', {'progress': get_progress()}

    months = months or months_to_build()
    with _STATE_LOCK:
        _STATE.update(running=True, tag=tag, finished_at=None, error=None,
                      current_month=None, done=0, total=len(months))

    def worker():
        try:
            run_build(app, months, tag=tag)
        except Exception as e:
            with _STATE_LOCK:
                _STATE['error'] = f'{type(e).__name__}: {e}'
            print(f"[ME-SNAPSHOT] fonovy progon upal: {e}")
        finally:
            _release_refresh_lock()
            with _STATE_LOCK:
                _STATE['running'] = False

    threading.Thread(target=worker, name='me-snapshot-refresh', daemon=True).start()
    return True, '', {'progress': get_progress()}


def _cli():
    """`py -3 -m core.me_snapshot [YYYY-MM ...]` — прогон без веб-сервера.

    Нужен, чтобы собрать и глазами сверить снимок на проде ДО того, как страница
    покажет деньги людям: `docker compose exec app python -m core.me_snapshot`.
    """
    import sys

    from app import app

    months = [a for a in sys.argv[1:] if valid_month(a)] or months_to_build()
    print(f"[ME-SNAPSHOT] CLI: {', '.join(months)}")
    reports = run_build(app, months, tag='cli')
    bad = [m for m, r in reports.items() if not r['written']]
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(_cli())
