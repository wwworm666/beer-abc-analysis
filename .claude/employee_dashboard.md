# Employee Efficiency Dashboard

## Обзор
Дашборд аналитики эффективности сотрудников (барменов). Доступен по адресу `/employee`.

## Файлы

| Файл | Описание |
|------|----------|
| `templates/employee.html` | Frontend - страница дашборда |
| `core/employee_analysis.py` | Калькулятор метрик `EmployeeMetricsCalculator` |
| `core/employee_plans.py` | Расчёт планов, `BAR_NAME_MAPPING` |
| `core/iiko_api.py` | API методы: `get_employee_metrics_from_shifts()`, `get_cash_shifts()` |
| `app.py` | API endpoints `/api/employee-analytics`, `/api/employee-compare` |
| `data/bar_plans.json` | Планы ТТ по дням |

---

## Архитектура данных (обновлено 23.01.2026)

### Источники данных

| Источник | API | Что берём |
|----------|-----|-----------|
| **Cash Shifts** | `/v2/cashshifts/list` | Сотрудник, локация, дата, часы работы |
| **OLAP Reports** | `/olap/...` | Выручка, чеки, разлив/фасовка/кухня, скидки, отмены |
| **Groups** | `/corporation/groups` | Маппинг pointOfSaleId → название точки |
| **Employees** | `/employees` | Маппинг employee_id → имя |
| **bar_plans.json** | Локальный файл | Планы по ТТ на каждый день |

### Как определяется место работы

```
Cash Shift → responsibleUserId (бармен)
          → pointOfSaleId → groups API → название точки

Один работник = одна кассовая смена
```

### Маппинг точек (BAR_NAME_MAPPING)

| Из iiko (группа) | В планах |
|------------------|----------|
| Пивная культура | Кременчугская |
| Большой пр. В.О | Большой пр В.О. |
| Варшавская | Варшавская |
| Лиговский | Лиговский |
| Планерная | Планерная (без плана) |

---

## Расчёт плана сотрудника

```
План = Σ(план_ТТ[дата] для каждого дня когда сотрудник работал)
```

**Пример:**
- Артемий Новаев работал 12 смен на "Пивная культура" (= Кременчугская)
- План Кременчугской: 43770 руб/день
- Итого план: 12 × 43770 = 525 240 руб

---

## API Endpoints

### POST /api/employee-analytics

Детальный анализ одного сотрудника.

```json
{
  "employee_name": "Артемий Новаев",
  "bar": null,
  "date_from": "2026-01-01",
  "date_to": "2026-01-22"
}
```

**Flow:**
1. OLAP: выручка, чеки, категории (параллельно, ThreadPoolExecutor)
2. Cash Shifts: смены, часы, локации (`get_employee_metrics_from_shifts()`)
3. Расчёт плана по shift_locations
4. `EmployeeMetricsCalculator.calculate()`

**Response:**
```json
{
  "total_revenue": 458763.14,
  "total_checks": 236,
  "avg_check": 1943.91,
  "draft_share": 63.7,
  "bottles_share": 21.2,
  "kitchen_share": 15.1,
  "shifts_count": 12,
  "work_hours": 124.1,
  "revenue_per_shift": 38230.26,
  "revenue_per_hour": 3696.72,
  "plan_revenue": 525238.0,
  "plan_fact_percent": 87.3,
  "cancelled_count": 0
}
```

### POST /api/employee-compare

Сравнение нескольких сотрудников.

```json
{
  "employee_names": ["Артемий Новаев", "Егор Бобриков", ...],
  "date_from": "2026-01-01",
  "date_to": "2026-01-22"
}
```

Оптимизации:
- Все метрики загружаются **одним запросом** для всех сотрудников
- Нормализация имён: "Артемий Новаев" == "Новаев Артемий"

---

## Метрики сотрудника

| Метрика | Источник | Формула |
|---------|----------|---------|
| total_revenue | OLAP | DishDiscountSumInt |
| total_checks | OLAP | OrderNum |
| avg_check | Расчёт | total_revenue / total_checks |
| shifts_count | Cash Shifts | Количество смен |
| work_hours | Cash Shifts | closeDate - openDate |
| revenue_per_shift | Расчёт | total_revenue / shifts_count |
| revenue_per_hour | Расчёт | total_revenue / work_hours |
| plan_revenue | bar_plans.json | Σ(план ТТ за рабочие дни) |
| plan_fact_percent | Расчёт | total_revenue / plan_revenue × 100 |
| draft_share | OLAP | разлив / total_revenue × 100 |
| bottles_share | OLAP | фасовка / total_revenue × 100 |
| kitchen_share | OLAP | кухня / total_revenue × 100 |

---

## Оптимизации

1. **Параллельные OLAP запросы** - `ThreadPoolExecutor(max_workers=5)`
2. **Кэш сотрудников** - `EMPLOYEES_CACHE`, TTL 5 минут
3. **Кэш планов** - в `BarPlansReader._plans_cache`

---

## Deprecated (не используется)

- `get_attendance()` - возвращал только "Пивная культура" для всех
- `get_employee_plan_by_attendance()` - не мог определить реальную точку

---

## Debug

В консоли сервера:
```
[DEBUG] Cash shifts: 12 shifts, 124.1 hours
   Plan calculated from 12 cash shifts: 525238
```

---

## Проверено 23.01.2026

График смен из кассовых смен соответствует реальному расписанию.
