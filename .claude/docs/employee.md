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

Метрики рассчитываются из OLAP API с группировкой по `AuthUser`:

```python
# core/olap_reports.py:1025-1119
def get_employee_aggregated_metrics(self, date_from, date_to, bar_name=None):
    request = {
        "groupByRowFields": ["AuthUser"],  # "Авторизовал" — кто пробил чек
        "aggregateFields": [
            "UniqOrderId",
            "UniqOrderId.OrdersCount",  # Количество чеков
            "DishDiscountSumInt",       # Выручка
            "DiscountSum",              # Сумма скидок
            "DishAmountInt"             # Количество блюд
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
    'kitchen_share': float,         # % кухни
    'draft_revenue': float,
    'bottles_revenue': float,
    'kitchen_revenue': float,
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

#### Решение (2026-04-01)

Все OLAP отчёты теперь используют `AuthUser` ("Авторизовал") для группировки по сотруднику:
- `get_employee_aggregated_metrics()` — `AuthUser`
- `get_draft_sales_by_waiter_report()` — `AuthUser` (было `WaiterName`)
- `get_bottles_sales_by_waiter_report()` — `AuthUser` (было `WaiterName`)
- `get_kitchen_sales_by_waiter_report()` — `AuthUser` (было `WaiterName`)

**Проблема решена:** данные консистентны, матчинг не требуется.

```python
# core/olap_reports.py:647-652
if include_waiter:
    # Используем AuthUser ("Авторизовал") — видит ВСЕ чеки
    groupByRowFields.append("AuthUser")
```

```python
# core/employee_analysis.py:200-217
def _filter_by_employee(self, data, employee_name):
    # Простое точное совпадение AuthUser
    for r in data['data']:
        if r.get('AuthUser', '') == employee_name:
            matched.append(r)
```

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

Фиксированная премия за каждую смену:

```
Премия = 500 ₽ × количество смен
```

Данные берутся из кассовых смен iiko API (`shifts_count`).

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

#### Передача в frontend

Часы передаются в API ответов и показываются в UI по умолчанию:

```python
# routes/employee.py:528-540 (bonus API)
results.append({
    ...
    'total_hours': round(total_hours, 1),  # из кассовых смен
})

# routes/employee.py:701-703 (kpi API)
kpi_result['total_hours'] = round(total_hours, 1)
```

```javascript
// templates/bonus.html:633-642
mergedEmployees.forEach(emp => {
    emp.autoHours = emp.bonus?.total_hours ?? emp.kpi?.total_hours ?? 0;
    emp.hours = emp.autoHours;  // по умолчанию авто, но можно изменить
});
```

**Важно:** Пользователь может вручную изменить значение часов — оно пересчитает итоговую ЗП.

---

### KPI бонусы

#### Формула расчёта

```python
# core/kpi_calculator.py:213-245
def calculate_premium(self, fact, target, min_val, total_shifts, defaults):
    """
    ratio = (Факт - Мін) / (Цель - Мін)
    capped_ratio = max(0, min(ratio, max_ratio))
    Премия_kpi = capped_ratio × Смен × (base_premium / norm_shifts)
    """
    norm_shifts = defaults.get('norm_shifts', 15)
    base_premium = defaults.get('base_premium', 5000)
    max_ratio = defaults.get('max_ratio', 2)

    if target == min_val:
        ratio = float(max_ratio) if fact >= target else 0.0
    elif fact < min_val:
        ratio = 0.0
    else:
        ratio = (fact - min_val) / (target - min_val)

    capped_ratio = max(0.0, min(ratio, float(max_ratio)))
    premium = capped_ratio * total_shifts * (base_premium / norm_shifts)

    return {
        'ratio': round(ratio, 4),
        'capped_ratio': round(capped_ratio, 4),
        'premium': round(premium, 2)
    }
```

#### 3 KPI метрики

Конфигурация KPI привязана к месяцу и хранится в `data/kpi_targets.json`:

```json
{
  "months": {
    "2026-03": {
      "kpi_config": {
        "kpi1": {"metric": "kitchen_share", "name": "Доля кухни (%)"},
        "kpi2": {"metric": "draft_share", "name": "Доля розлива (%)"},
        "kpi3": {"metric": "avg_check", "name": "Средний чек (₽)"}
      },
      "Кременчугская": {
        "kpi1": {"target": 25.0, "min": 15.0},
        "kpi2": {"target": 45.0, "min": 35.0},
        "kpi3": {"target": 750, "min": 500}
      },
      ...
    }
  },
  "defaults": {
    "norm_shifts": 15,
    "base_premium": 5000,
    "max_ratio": 2
  }
}
```

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
# core/kpi_calculator.py:247-329
def calculate_employee(self, employee_name, metrics, shift_locations, month):
    # 1. Считаем смены по точкам
    shifts_per_location = self.count_shifts_per_location(shift_locations)

    # 2. Взвешенные цели
    weighted_targets, total_shifts = self.calculate_weighted_targets(...)

    # 3. Расчёт по каждому KPI
    for kpi_key in ['kpi1', 'kpi2', 'kpi3']:
        metric_field = kpi_config[kpi_key]['metric']
        fact = metrics.get(metric_field, 0)
        targets = weighted_targets.get(kpi_key)

        premium_result = self.calculate_premium(fact, targets['target'], targets['min'], ...)
        total_premium += premium_result['premium']

    return {
        'employee_name': employee_name,
        'total_shifts': total_shifts,
        'koef': total_shifts / norm_shifts,
        'kpis': {...},
        'total_premium': total_premium
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

### KPI ratio
```
ratio = (Факт - Мін) / (Цель - Мін)
capped_ratio = min(max(ratio, 0), max_ratio)
Премия = capped_ratio × Смен × (base_premium / norm_shifts)
```

---

## Зависимости

### От каких модулей зависит
- `core/olap_reports.py` → данные о продажах
- `core/iiko_api.py` → кассовые смены, сотрудники
- `core/employee_plans.py` → планы из bar_plans.json
- `core/kpi_calculator.py` → KPI цели из kpi_targets.json

### Кто использует
- Frontend сотрудников (`employee.html`)
- Дашборд бонусов
- Telegram bot

---

## Changelog

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
