# Сотрудники

## Что это

Модуль анализа эффективности сотрудников: метрики продаж, планы, KPI, бонусы, сравнение.

## Файлы

- [`core/employee_analysis.py`](../../core/employee_analysis.py) — расчёт метрик сотрудника
- [`core/employee_plans.py`](../../core/employee_plans.py) — планы из смен
- [`core/kpi_calculator.py`](../../core/kpi_calculator.py) — KPI бонусы
- [`core/iiko_api.py`](../../core/iiko_api.py) — кассовые смены, расчёт часов
- [`routes/employee.py`](../../routes/employee.py) — Flask endpoint'ы

---

## Как работает

### Метрики сотрудника

#### Источник данных

Для KPI используется `get_kpi_olap_data()` — 2 легковесных OLAP запроса:

```python
# core/olap_reports.py — get_kpi_olap_data()
# Запрос 1 (summary): groupBy [WaiterName] -> чеки, выручка, скидки (~30-50 строк)
# Запрос 2 (categories): groupBy [WaiterName, DishGroup.TopParent] -> доли, наценка (~100-200 строк)
```

Для dashboard используется `get_employee_aggregated_metrics()` (старый подход с AuthUser):

```python
# core/olap_reports.py:1025-1119
def get_employee_aggregated_metrics(self, date_from, date_to, bar_name=None):
    request = {
        "groupByRowFields": ["AuthUser"],
        "aggregateFields": [
            "UniqOrderId",
            "UniqOrderId.OrdersCount",
            "DishDiscountSumInt",
            "DiscountSum",
            "DishAmountInt"
        ]
    }
```

#### Расчёт метрик

```python
# core/employee_analysis.py:18-198
def calculate(self, employee_name, aggregated_data, ...):
    # 1. Количество чеков — из OLAP
    total_checks = int(emp_aggregated.get('UniqOrderId.OrdersCount', 0))

    # 2. Выручка — приоритет кассовые смены, fallback OLAP
    if total_revenue_override is not None:
        total_revenue = total_revenue_override
    else:
        total_revenue = float(emp_aggregated.get('DishDiscountSumInt', 0))

    # 3. Средний чек — из OLAP (не смешивать с кассовыми сменами!)
    olap_revenue = float(emp_aggregated.get('DishDiscountSumInt', 0))
    avg_check = olap_revenue / total_checks if total_checks > 0 else 0

    # 4. Выручка по категориям
    draft_revenue = self._sum_revenue(draft_records)
    bottles_revenue = self._sum_revenue(bottles_records)
    kitchen_revenue = self._sum_revenue(kitchen_records)

    # 5. Доли категорий
    draft_share = draft_revenue / total_revenue * 100 if total_revenue > 0 else 0

    # 6. Эффективность (смены, часы)
    revenue_per_shift = total_revenue / shifts_count if shifts_count > 0 else 0
    revenue_per_hour = total_revenue / total_hours if total_hours > 0 else 0

    # 7. Наценка (взвешенная)
    avg_markup = self._calculate_weighted_markup(all_records) * 100

    # 8. % скидок
    gross_revenue = total_revenue + discount_sum
    discount_percent = discount_sum / gross_revenue * 100 if gross_revenue > 0 else 0

    # 9. Отмены/возвраты
    cancelled_count = ...  # из cancelled_data OLAP

    # 10. План/факт
    plan_fact_percent = total_revenue / plan_revenue * 100 if plan_revenue > 0 else 0
```

#### Возвращаемые метрики

```python
{
    'employee_name': str,
    'total_revenue': float,         # Выручка
    'draft_share': float,           # % розлива
    'bottles_share': float,         # % фасовки
    'kitchen_share': float,         # % кухни (строго группа «ЕДА», с 2026-07-16)
    'other_share': float,           # % прочего (НАБОРЫ, Чай/Кофе, Газ и Пэт) — скрытая категория
    'draft_revenue': float,
    'bottles_revenue': float,
    'kitchen_revenue': float,       # только группа «ЕДА»
    'other_revenue': float,         # прочие не-напитки
    'shifts_count': int,            # Количество смен
    'work_hours': float,            # Часы работы
    'revenue_per_shift': float,     # Выручка/смена
    'revenue_per_hour': float,      # Выручка/час
    'top_beers': [...],             # Топ сортов пива
    'total_checks': int,            # Количество чеков
    'avg_check': float,             # Средний чек
    'avg_markup': float,            # Средняя наценка %
    'discount_sum': float,          # Сумма скидок
    'discount_percent': float,      # % скидок от выручки
    'cancelled_count': int,         # Отмены/возвраты
    'plan_revenue': float,          # План выручки
    'plan_fact_percent': float,     # План/факт %
    'late_count': int,              # Опоздания
    'loyalty_cards_count': int      # Новые карты лояльности
}
```

---

### Матчинг имён

#### KPI route (2026-04-04)

KPI route использует `WaiterName` для всех OLAP запросов (единообразие):
- `get_kpi_olap_data()` summary — `WaiterName`
- `get_kpi_olap_data()` categories — `WaiterName` + `DishGroup.TopParent`

Матчинг: `_find_employee_in_olap()` — exact match + fuzzy (по словам, обрабатывает "Иван Петров" vs "Петров Иван").

#### Dashboard route (legacy)

Dashboard всё ещё использует `AuthUser` для `get_employee_aggregated_metrics()` и `WaiterName` для категорий.

---

### Планы сотрудников

#### Источник планов

Планы берутся из кассовых смен iiko:

```python
# core/iiko_api.py:346-513
def get_employee_metrics_from_shifts(self, date_from, date_to):
    """
    Возвращает:
    {
        employee_id: {
            'shifts_count': int,
            'dates': [str],
            'locations': {str: int},       # Локация -> кол-во смен
            'shift_locations': {str: str}, # Дата -> локация
            'shift_revenues': {str: float},# Дата -> выручка
            'total_revenue': float,
            ...
        }
    }
    """
```

#### Расчёт плана выручки

План на день берётся из `data/daily_plans.json` по локации и дате:

```python
# core/employee_plans.py
# Маппинг названий из iiko API на ключи daily_plans.json (английские)
BAR_NAME_MAPPING = {
    'пивная культура': 'kremenchugskaya',    # Кременчугская
    'большой пр. в.о': 'bolshoy',            # Большой пр В.О.
    'варшавская': 'varshavskaya',            # Варшавская
    'лиговский': 'ligovskiy',                # Лиговский
}

def normalize_bar_name(name: str) -> str:
    """Нормализация: lower + strip"""
    return name.lower().strip()
```

**Важно:** `daily_plans.json` использует английские ключи (`kremenchugskaya`, `bolshoy`, `varshavskaya`, `ligovskiy`), а не русские названия.

> **Override весов дней (2026-06-06).** `daily_plans.json` — производный кэш из
> месячных планов + override весов дней (`core/day_weights.py`). Если для дня задан
> особый вес (праздник = N, закрытый день = 0 — через страницу «Планы по дням»),
> дневной план этого дня меняется автоматически, и бонус сотрудника за смену в этот
> день считается уже по новому плану. Кэш `DailyPlansReader._reader` теперь
> сбрасывается при каждой регенерации (`clear_plans_cache()` в `save_daily_plans`) —
> раньше он обновлялся только рестартом процесса, из-за чего бонусы могли считаться
> по устаревшему плану.

def get_plan_for_employee(employee_name, date_from, date_to):
    # 1. Определяем локации сотрудника по сменам
    # 2. Для каждой даты берём план из JSON
    # 3. Суммируем планы по дням
    total_plan = sum(plans[location][date] for each date, location)
    return total_plan
```

---

### Бонусы (ежедневный расчет)

#### Формула бонуса

Бонус считается **по дням** на основе данных из кассовых смен:

```python
# routes/employee.py:495-520
for date_str in sorted(shift_dates):
    day_revenue = shift_revenues.get(date_str, 0.0)
    
    # План на день из daily_plans.json
    day_plan = get_daily_plan_for_date(date_str, bar_name)
    
    # Перевыполнение: только положительная разница
    day_over = max(0, day_revenue - day_plan) if day_plan > 0 else 0
    
    # Бонус за смену: 1000 + перевыполнение × 5%
    day_bonus = (1000 + day_over * 0.05) if day_over > 0 else 0

# Итоговый бонус:
bonus = Σ day_bonus
```

#### Штраф за опоздания

Прогрессивная шкала:

```python
penalty = 250 × late_count × (late_count + 1) // 2
```

| Опозданий | Штраф |
|-----------|-------|
| 1 | 250 ₽ |
| 2 | 750 ₽ |
| 3 | 1 500 ₽ |
| 4 | 2 500 ₽ |

#### Итоговая выплата

```
net = max(0, bonus - penalty)
shift_handover_bonus = shifts_count × 500
```

#### Пример расчета

```
Сотрудник: Артемий Новаев
Период: 2026-03-24 — 2026-03-30

День 1 (24.03):
  План: 50 000 ₽, Факт: 62 000 ₽
  Перевыполнение: 12 000 ₽
  Бонус: 1000 + (12 000 × 0.05) = 1 600 ₽

День 2 (25.03):
  План: 50 000 ₽, Факт: 48 000 ₽
  Перевыполнение: 0 ₽ (план не выполнен)
  Бонус: 0 ₽

Итого бонус: 1 600 ₽
Опоздания: 1 → штраф 250 ₽
Премия за смены: 2 × 500 = 1 000 ₽

К выплате: 1 600 - 250 + 1 000 = 2 350 ₽
```

---

### Премия за передачу смены

Премия за каждую смену — **но только за дни со сданной кассовой дисциплиной**
(наличные в сейфе на конец смены заполнены в графике). За день без кассы премия
не платится. Правило действует **с 11.07.2026** (`HANDOVER_CASH_RULE_FROM`); дни
до этой даты оплачиваются всегда, без требования кассы.

```
Премия = 500 ₽ × (смены − дни_без_кассы_с_11.07.2026)
```

- Число смен (`shifts_count`) — из кассовых смен iiko API.
- «Дни_без_кассы» — дни смен сотрудника (`shift_locations`: дата → точка), для
  которых в графике (`shifts.db`) НЕ сдана касса (`cash_end_kop IS NULL`). Кассу
  сдаёт дневной бармен, поэтому день точки считается «закрытым по кассе» для всех,
  кто в этот день на ней работал.
- Сопоставление точки iiko и точки графика — через `venue_key` (`BAR_NAME_MAPPING`),
  т.к. имена различаются (кассовая группа «Пивная культура» == точка графика
  «Кременчугская»). Логика: `routes/employee.py` — `_cash_filled_day_keys` +
  `_paid_handover_shifts` (чистая, тест `tests/test_bonus_handover_cash.py`).
- **Fail-open**: если график недоступен, премию не режем (сбой БД не обнуляет
  премию всей смене). На странице ЗП рядом с суммой показывается «(N дн. без кассы)».
- **Столбец «Касса»** в разделе смен (раскрытие сотрудника, `templates/bonus.html`):
  по каждому дню — «сдана» (зелёным) / «нет» (красным, если день влияет на премию —
  с 11.07.2026) / «нет» серым (до отсечки, на премию не влияет) / «—» (точка дня
  неизвестна или график недоступен). Поля дня из API: `cash_filled` (bool|null),
  `cash_rule_applies` (bool).
- Дата-отсечка `HANDOVER_CASH_RULE_FROM = '2026-07-11'`: дни ДО неё оплачиваются
  всегда (исторические месяцы без кассовой дисциплины не обнуляются), с 11.07.2026 —
  требуется сданная касса. Сравнение дат — строкой ISO (`d >= rule_from`).

---

### Расчёт часов работы

#### Источник данных

Часы работы рассчитываются автоматически из кассовых смен iiko API (`/v2/cashshifts`):

```python
# core/iiko_api.py:404-417
def get_employee_metrics_from_shifts(self, date_from, date_to):
    # Для каждой смены:
    open_dt = self._parse_iso_datetime(open_date_str)   # время открытия
    close_dt = self._parse_iso_datetime(close_date_str) # время закрытия

    delta = close_dt - open_dt
    shift_hours = delta.total_seconds() / 3600  # часы работы
```

#### Формула

```
Часы работы = Σ(close_time - open_time) по всем сменам сотрудника
```

где:
- `open_time` — время открытия смены (из `openDate`)
- `close_time` — время закрытия смены (из `closeDate`)
- Результат суммируется по всем сменам за период

#### Защита от некорректных данных

```python
# core/iiko_api.py:413-415
if shift_hours < 0 or shift_hours > 24:
    shift_hours = 0.0  # защита от отрицательных или слишком больших значений
```

#### Использование часов

iiko-часы (`close - open`) остаются метрикой **Employee Dashboard** (выручка/час,
`work_hours`, `revenue_per_hour`) и по-прежнему возвращаются в ответах
`bonus`/`kpi`.

**Важно (с 2026-06-24): для расчёта ЗП iiko-часы больше НЕ используются.**
Единственный источник часов оплаты — **график смен** (`shifts.fact_minutes`),
а ставка берётся у роли смены (`roles.rate_per_hour`). Причина: смена может
длиться дольше кассовой, и владелец считает верными именно введённые в графике
часы. Страница ЗП тянет разбивку через `GET /api/schedule/hours-by-role` и
считает оплату = сумма по сменам (`часы × ставка роли`). Правка часов — в
графике (страница ЗП показывает часы read-only). Ставки ролей правятся на
странице ЗП («Ставки за час по ролям»). Подробно — `docs/schedule.md`, раздел
«Оплата часов по ролям».

---

### KPI бонусы

#### Формула расчёта

Двухэтапная: сначала промежуточная премия по каждому KPI без учёта смен,
затем единый коэффициент `смены/норма` применяется к сумме всех KPI.

```python
# core/kpi_calculator.py — calculate_premium()
def calculate_premium(self, fact, target, min_val, defaults, base_premium=None):
    """
    ratio              = (Факт - Мин) / (Цель - Мин)
    capped_ratio       = max(0, min(ratio, max_ratio))
    intermediate_premium = capped_ratio × base_premium   # base_premium = фонд / кол-во KPI
    """
    if base_premium is None:                 # легаси-режим (нет kpi_pool)
        base_premium = defaults.get('base_premium', 5000)
    max_ratio = defaults.get('max_ratio', 2)

    if target == min_val:
        ratio = float(max_ratio) if fact >= target else 0.0
    elif fact < min_val:
        ratio = 0.0
    else:
        ratio = (fact - min_val) / (target - min_val)

    capped_ratio = max(0.0, min(ratio, float(max_ratio)))
    intermediate_premium = capped_ratio * base_premium

    return {
        'ratio': round(ratio, 4),
        'capped_ratio': round(capped_ratio, 4),
        'intermediate_premium': round(intermediate_premium, 2),
    }
```

Финальный шаг — в `calculate_employee()`:

```python
base_per_kpi = kpi_pool / kpi_count          # фонд делится поровну (15000 / 2 = 7500)
koef = total_shifts / norm_shifts            # total_shifts = смены ТОЛЬКО на точках с целями
total_intermediate = Σ intermediate_premium  # по всем KPI месяца
total_premium = total_intermediate × koef    # коэффициент применяется один раз к сумме
```

**Фонд KPI делится поровну на количество показателей.** Количество KPI задаётся помесячно
(`kpi_config` — переменное число ключей `kpi1..kpiN`), фонд `kpi_pool` — глобально в `defaults`.
Важное свойство: и потенциал на цели (`= kpi_pool`), и потолок (`= max_ratio × kpi_pool`)
**не зависят** от количества KPI — меняется только «вес» каждого. При фонде 15000: 2 KPI → по 7500 ₽,
3 KPI → по 5000 ₽. Легаси: если `kpi_pool` не задан, берётся `base_premium` за каждый KPI
(тогда сумма растёт с количеством — старое поведение).

Инверсные метрики (`late_count`, `cancelled_count`): задайте `min > target`
(например target=0, min=3). Формула `(fact - min) / (target - min)` даст
положительный ratio при низком факте и clamp в 0 при `fact > min`.

#### Метрики KPI (количество настраивается)

Конфигурация KPI привязана к месяцу и хранится в `data/kpi_targets.json`. Количество показателей —
переменное (`kpi1..kpiN`), задаётся в редакторе целей степпером «Показателей: − N +». Цели по точкам
содержат столько же ключей. Пример с 2 KPI:

```json
{
  "months": {
    "2026-07": {
      "kpi_config": {
        "kpi1": {"metric": "kitchen_share", "name": "Доля кухни (%)"},
        "kpi2": {"metric": "draft_share", "name": "Доля розлива (%)"}
      },
      "Кременчугская": {
        "kpi1": {"target": 18.0, "min": 13.0},
        "kpi2": {"target": 61.0, "min": 57.0}
      },
      ...
    }
  },
  "defaults": {
    "norm_shifts": 15,
    "kpi_pool": 15000,
    "base_premium": 5000,
    "max_ratio": 2
  }
}
```

`kpi_pool` — общий премиальный фонд за KPI; делится поровну на количество показателей месяца.
`base_premium` остаётся как легаси-fallback (используется, только если `kpi_pool` отсутствует).

#### Взвешенные цели

Если сотрудник работал в разных локациях, цели усредняются взвешенно по сменам:

```python
# core/kpi_calculator.py:166-211
def calculate_weighted_targets(self, shifts_per_location, month_targets):
    """
    weighted_target = Σ(shift_count × target) / Σ(shift_count)
    """
    for location, shift_count in shifts_per_location.items():
        loc_targets = month_targets.get(location, {})
        weighted_target += shift_count * loc_targets[kpi_key]['target']
        weighted_min += shift_count * loc_targets[kpi_key]['min']

    return {
        'target': weighted_target / total_shifts,
        'min': weighted_min / total_shifts
    }
```

#### Итоговая премия

```python
# core/kpi_calculator.py — calculate_employee()
def calculate_employee(self, employee_name, metrics, shift_locations, month):
    # 1. Считаем смены по точкам (русские названия для kpi_targets.json)
    shifts_per_location = self.count_shifts_per_location(shift_locations)

    # 2. Взвешенные цели — total_shifts здесь = ТОЛЬКО смены на точках с целями
    weighted_targets, total_shifts = self.calculate_weighted_targets(...)
    if total_shifts == 0:
        return None  # нет точек с настроенными KPI → премия не считается

    # 3. Промежуточная премия по каждому KPI (без множителя на смены)
    #    kpi_keys — динамически из kpi_config месяца (kpi1..kpiN)
    total_intermediate = 0.0
    for kpi_key in kpi_keys:
        metric_field = kpi_config[kpi_key]['metric']
        fact = metrics.get(metric_field, 0)
        targets = weighted_targets.get(kpi_key)

        result = self.calculate_premium(fact, targets['target'], targets['min'], defaults)
        total_intermediate += result['intermediate_premium']

    # 4. Финальный шаг — коэффициент применяется один раз к сумме
    koef = round(total_shifts / norm_shifts, 2)
    total_premium = round(total_intermediate * koef, 2)

    return {
        'employee_name': employee_name,
        'total_shifts': total_shifts,
        'koef': koef,
        'kpis': {...},
        'total_premium': total_premium,
    }
```

---

## API endpoint'ы

### Список сотрудников

```
GET /api/employees?dateFrom=...&dateTo=...
Response: [
    {"id": "...", "name": "...", "code": "..."}
]
```

### Аналитика сотрудника

```
POST /api/employee-analytics
Body: {
    "employeeName": "...",
    "dateFrom": "...",
    "dateTo": "..."
}
Response: {
    "metrics": {...}  # все метрики из calculate()
}
```

### Сравнение сотрудников

```
POST /api/employee-compare
Body: {
    "employees": ["Иван Петров", "Анна Смирнова"],
    "dateFrom": "...",
    "dateTo": "..."
}
Response: {
    "comparison": [...]
}
```

### Бонусы

```
POST /api/bonus-calculate
POST /api/kpi-calculate
```

### Детализация скидок по чекам

Разворачивает общую метрику «% скидок» сотрудника в построчный список чеков со скидкой
(«кто кому сколько списывает»). Вызывается кликом по карточке «% скидок» на странице сотрудника.

```
POST /api/employee-discount-checks
Body: {
    "employee_name": "...",   # значение AuthUser (как на карточке)
    "bar": "Кременчугская"|null,  # Store.Name, null = все бары
    "date_from": "YYYY-MM-DD",
    "date_to": "YYYY-MM-DD"
}
Response: {
    "checks": [               # все чеки со скидкой, сортировка хронологическая (дата, № чека)
        {"date", "store", "check", "type", "discount", "check_sum",
         "check_gross",       # полная сумма чека без скидки (DishSumInt)
         "discount_pct",      # % скидки от полной суммы = discount / check_gross * 100
         "guest_name", "guest_card", "has_loyalty"}
    ],
    "by_type": [              # свод по типам скидок
        {"type", "count", "discount", "gross", "discount_pct"}
    ],
    "total_discount": 28163.0,
    "total_gross": 146865.0,
    "total_discount_pct": 19.2,
    "total_checks": 91,
    "loyalty_checks": 72      # на скольких чеках проведена карта лояльности (опознан гость)
}
```

Источник — `OlapReports.get_employee_discount_checks()`: OLAP SALES,
`groupByRowFields = [AuthUser, OpenDate.Typed, Store.Name, OrderNum, OrderDiscount.Type,
Delivery.CustomerName, Delivery.CustomerCardNumber]`,
`aggregateFields = [DiscountSum, DishDiscountSumInt]`, фильтры `NOT_DELETED × 2`.
Ключ чека — дата + касса + номер (OrderNum уникален только в пределах дня и кассы).

**Гость (карта лояльности).** `guest_name` (Delivery.CustomerName) и `guest_card`
(Delivery.CustomerCardNumber) заполнены, ТОЛЬКО если на чеке проведена карта — это и есть
пометка лояльности (`has_loyalty`). Пустые = карта не проводилась (служебные скидки
«30% сотруднику», «5% проблемы с лояльностью» и т.п.). `guest_card` содержит идентификатор
лояльности: для гостей, зарегистрированных по телефону, это телефон (`+7…`), иначе — номер карты.
Поле `Delivery.Phone` в OLAP для зала всегда пусто (проверено на живых данных 2026-06-17),
поэтому телефон берётся из `Delivery.CustomerCardNumber`.
Отбор чеков со скидкой (`DiscountSum > 0`) — постобработкой: сервер запрещает фильтрацию
по `DiscountSum` (HTTP 400 «Filtering is not allowed for field 'DiscountSum'»), поэтому
запрос всегда ограничен одним сотрудником через фильтр `AuthUser`.

---

## Формулы

### Выручка
```
Выручка = Σ(DishDiscountSumInt) из OLAP по AuthUser
```

### Средний чек
```
Средний чек = Выручка OLAP / Количество чеков OLAP
```

**Важно:** Не смешивать с кассовыми сменами!

### Доля категории
```
Доля = (Выручка категории / Общая выручка) × 100%
```

### Наценка взвешенная
```
Наценка = Σ(MarkUp × Cost) / Σ(Cost)
```

### План/факт
```
План/факт % = (Факт / План) × 100%
```

### Скидки по чекам (детализация)
```
Скидка по типу    = Σ(DiscountSum) по чекам с этим OrderDiscount.Type
Всего скидок       = Σ(DiscountSum) по всем чекам сотрудника со скидкой
% скидки (чек)     = DiscountSum / DishSumInt × 100   (DishSumInt = полная сумма без скидки)
% скидки (тип)     = Σ(DiscountSum) / Σ(DishSumInt) по типу × 100
% скидки (всего)   = total_discount / total_gross × 100
```
Проверка формулы на живых данных: именованные скидки дают ровно свой процент
(«30% сотруднику» → 30.0%, «5%…» → 5.0%, «сикспак (10%)» → 10.0%);
DishSumInt = DishDiscountSumInt + DiscountSum на всех чеках (2026-06-17).
**Сходимость:** «Всего скидок» из детализации в точности равно метрике `discount_sum`
(карточка «% скидок»), т.к. оба считаются как Σ(DiscountSum) по AuthUser за период —
менеджер всегда может сверить разбивку с общей цифрой (проверено на живых данных 2026-06-17).

### KPI ratio
```
base_per_kpi         = kpi_pool / кол-во KPI              # фонд делится поровну
ratio                = (Факт - Мин) / (Цель - Мин)
capped_ratio         = clamp(ratio, 0, max_ratio)
intermediate_premium = capped_ratio × base_per_kpi       # per KPI
total_premium        = Σ intermediate × (total_shifts / norm_shifts)
```

где `total_shifts` — смены на точках с настроенными KPI-целями (не общее число смен).

---

## Зависимости

### От каких модулей зависит
- `core/olap_reports.py` → данные о продажах
- `core/iiko_api.py` → кассовые смены, сотрудники
- `core/employee_plans.py` → планы из daily_plans.json
- `core/kpi_calculator.py` → KPI цели из kpi_targets.json

### Кто использует
- Frontend сотрудников (`employee.html`)
- Дашборд бонусов
- Telegram bot

---

## Changelog

### 2026-07-16 — Кухня = строго группа «ЕДА», скрытая категория «Прочее»

Во всех расчётах по сотрудникам (карточка /employee, KPI-метрики,
/api/employee-metrics-breakdown) «кухня» теперь строго группа iiko «ЕДА».
НАБОРЫ, Чай/Кофе, Газ и Пэт выделены в скрытую категорию «Прочее»
(`other_share`/`other_revenue` в ответах есть, в UI не отображается).
Итоговая выручка/прибыль/наценка по-прежнему считаются по всем категориям.
ВАЖНО для KPI: факт «Доля кухни» с этой даты ниже (без НАБОРОВ и чая) —
июльские цели kitchen_share ставились под старое определение.

### 2026-06-17 — Скидки по чекам: % скидки от полной суммы чека

**Добавлено:** колонка «% скидки» в таблицу чеков и в свод по типам, общий процент в сводке.
В OLAP-запрос добавлена мера `DishSumInt` (полная сумма без скидки). Формула:
`% = DiscountSum / DishSumInt × 100`. В ответе — `check_gross`, `discount_pct` на чек,
`gross`/`discount_pct` по типам, `total_gross`/`total_discount_pct`. Последняя колонка таблицы
теперь «Сумма чека (полная)» = DishSumInt (раньше показывала сумму со скидкой).
Файлы: `core/olap_reports.py`, `routes/employee.py`, `templates/employee.html`.

**Проверка (живые данные 2026-06-17):** именованные скидки считаются ровно в свой процент
(30% → 30.0%, 5% → 5.0%, 10% → 10.0%); DishSumInt = DishDiscountSumInt + DiscountSum на всех чеках.

### 2026-06-17 — Скидки по чекам: гость (имя + карта/телефон) и пометка лояльности

**Добавлено:** в детализацию скидок по чекам — колонки «Гость» (Delivery.CustomerName) и
«Карта / тел.» (Delivery.CustomerCardNumber), счётчик `loyalty_checks` в ответе и пометка
`has_loyalty` на каждом чеке. Пустые имя/карта = карта лояльности не проводилась.
Файлы: `core/olap_reports.py`, `routes/employee.py`, `templates/employee.html`.

**Реальность данных (проверено на живых данных 2026-06-17):** `Delivery.Phone` в OLAP для зала
всегда пуст — телефона как отдельного поля нет. Телефон гостя (если регистрировался по нему)
лежит в `Delivery.CustomerCardNumber` вперемешку с внутренними номерами карт, поэтому колонка
называется «Карта / тел.». Имя гостя заполняется надёжно (в тесте — 72 из 91 чека со скидкой).

### 2026-06-17 — Детализация скидок по чекам («кто кому сколько списывает»)

**Добавлено:**
- `OlapReports.get_employee_discount_checks()` — OLAP SALES с группировкой
  `[AuthUser, OpenDate.Typed, Store.Name, OrderNum, OrderDiscount.Type]`, меры
  `DiscountSum`, `DishDiscountSumInt`. Разворачивает общую скидку сотрудника до каждого чека с типом.
- `POST /api/employee-discount-checks` — отдаёт список чеков со скидкой + свод по типам.
- Карточка «% скидок» на странице сотрудника стала кликабельной: открывает таблицу
  (свод по типам + все чеки со скидкой). Файлы: `core/olap_reports.py`, `routes/employee.py`,
  `templates/employee.html`.

**Почему:** раньше на карточке была только общая сумма скидок — не было видно, какими
типами скидок и на каких чеках сотрудник списывает деньги.

**Проверено на живых данных (2026-06-17):** сумма скидок по чекам в точности сходится с
общей метрикой `discount_sum`. Сервер запрещает фильтрацию по `DiscountSum`
(HTTP 400) — отбор чеков со скидкой делается постобработкой, запрос ограничен одним сотрудником.

### 2026-06-06 — Дневной план: единый источник + override весов + фикс устаревания кэша

**Изменено:**
- Дневной план для бонусов теперь идёт из единого канонического расчёта (`core/day_weights.py`): месячный план + override весов дней. Override (праздник = N, закрытый день = 0) автоматически попадает в дневной план сотрудника.
- `save_daily_plans` вызывает `clear_plans_cache()` — устранено устаревание `DailyPlansReader._reader` (раньше сбрасывался только рестартом). Логика чтения и формула бонуса не изменены.

### 2026-04-01 — Добавлена документация бонусов и frontend

**Добавлено:**
- Формула расчета бонусов (дневной расчет + штраф за опоздания)
- Премия за передачу смены
- Расчет часов из кассовых смен
- Frontend структура (вкладки, метрики, чарты)
- Детализация API endpoints

### 2026-03-27 — Создан документ employee.md

С описанием метрик, матчинга имён, KPI формул.

---

## Frontend

### Вкладка "Анализ"

**Элементы управления:**
- Dropdown сотрудника (загружается из `/api/employees`)
- Dropdown бара (все бары / конкретный)
- Date range picker (flatpickr, режим range)
- Кнопка "Анализировать"

**Отображаемые метрики (12 карточек):**
1. Выручка
2. План/Факт %
3. Смен
4. Выручка/смена
5. Выручка/час
6. Кол-во чеков
7. Средний чек
8. Наценка %
9. % скидок
10. Отмены (шт)
11. Опоздания
12. Новые карты лояльности

**Чарты:**
- Pie chart: доли категорий (розлив/фасовка/кухня)
- Таблица: топ сортов пива (кол-во, выручка)

### Вкладка "Сравнение"

**Элементы:**
- Grid с checkbox сотрудников (минимум 2)
- Date range picker
- Кнопка "Сравнить"

**Результаты:**
- Radar chart: 5 метрик (ср.чек, выручка/час, розлив %, план/факт %, чеков)
- Таблица сравнения: 13 метрик с подсветкой лучшего значения

### Форматирование

```javascript
// money: ₽
formatMoney(value) → "123 456 ₽"

// number: разделители тысяч
formatNumber(value) → "1 234"

// percent
value.toFixed(1) + '%' → "85.3%"

// hours
value.toFixed(1) + ' ч' → "42.5 ч"
```
