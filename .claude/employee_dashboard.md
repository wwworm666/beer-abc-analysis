# Employee Efficiency Dashboard

## Обзор
Дашборд аналитики эффективности сотрудников (барменов). Доступен по адресу `/employee`.

## Файлы

| Файл | Описание |
|------|----------|
| `templates/employee.html` | Frontend - страница дашборда |
| `core/employee_analysis.py` | Калькулятор метрик `EmployeeMetricsCalculator` |
| `core/employee_plans.py` | Чтение планов из Excel, маппинг инициалов |
| `app.py` | API endpoint `/api/employee-analytics` (строка ~1080) |

## API Endpoint

**POST** `/api/employee-analytics`

```json
{
  "employee_name": "Артемий Новаев",
  "bar": "Кременчугская",  // или null для всех баров
  "date_from": "2026-01-15",
  "date_to": "2026-01-17"
}
```

**Response:**
```json
{
  "total_revenue": 70631.0,
  "total_checks": 35,
  "avg_check": 2018.03,
  "draft_revenue": 45000.0,
  "bottles_revenue": 15000.0,
  "kitchen_revenue": 10631.0,
  "draft_share": 63.7,
  "bottles_share": 21.2,
  "kitchen_share": 15.1,
  "shifts_count": 1,
  "total_hours": 12.8,
  "revenue_per_shift": 70631.0,
  "revenue_per_hour": 5518.0,
  "plan_revenue": 58354.0,
  "plan_fact_percent": 121.0,
  "cancelled_count": 0,
  "cancelled_sum": 0.0
}
```

## Источники данных

### 1. OLAP Reports (iiko)
- `get_employee_aggregated_metrics()` - OrderNum, DishDiscountSumInt, DiscountSum
- `get_draft_sales_by_waiter_report()` - разливное пиво
- `get_bottles_sales_by_waiter_report()` - фасовка
- `get_kitchen_sales_by_waiter_report()` - кухня
- `get_cancelled_orders_by_waiter()` - отмены/возвраты

### 2. Attendance API (iiko)
- `get_attendance()` - смены сотрудника
- Возвращает: `date`, `start_time`, `end_time`, `duration_minutes`, `department_name`

### 3. Excel планы
- Файл: `план для сайта.xlsx`
- Структура: месяц -> день -> бар -> инициалы -> план
- Маппинг инициалов в `INITIALS_TO_NAME`

## Важные моменты

### Фильтрация смен
Смены фильтруются по дате **НАЧАЛА**, не окончания:
```python
if date_from <= shift_date <= date_to:
    filtered_attendances.append(a)
```
Смена 14.01 13:38 - 15.01 01:52 считается за 14 января!

### Оптимизации
1. **Параллельные OLAP запросы** - `ThreadPoolExecutor(max_workers=5)`
2. **Кэш сотрудников** - `EMPLOYEES_CACHE`, TTL 5 минут
3. **Кэш планов** - в `EmployeePlansReader._plans_cache`

### Маппинг инициалов
```python
INITIALS_TO_NAME = {
    'АН': 'Артемий Новаев',
    'НВ': 'Васильев Никита',
    'ДК': 'Дарья Коновцова',
    'ДКС': 'Дарья Коновцова',
    'ЕБ': 'Егор Бобриков',
    'ЕВ': 'Егор Верещагин',
    'ТМ': 'Макарова Татьяна',
    'МП': 'Максим Поляков',
    'КД': 'Кизатов Дамир',
}
```

## Debug

В консоли сервера выводится:
```
[DEBUG] Attendance records (filtered 1 of 2, 1 shifts, 12.8 hours):
   Date range filter: 2026-01-15 - 2026-01-17
   [SKIP] 2026-01-14 13:38-01:52 (734 min) @ Кременчугская
   [OK] 2026-01-16 14:18-03:04 (766 min) @ Кременчугская
```

## TODO / Возможные улучшения
- [ ] График выручки по дням
- [ ] Сравнение с другими сотрудниками
- [ ] Выбор нескольких сотрудников
- [ ] Экспорт в Excel
