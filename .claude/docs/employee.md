# Employee Dashboard

## Что это

Дашборд аналитики эффективности сотрудников (барменов). Показывает выручку, чеки, часы работы, выполнение плана. Доступен по `/employee`.

## Файлы

| Файл | Описание |
|------|----------|
| `templates/employee.html` | Frontend — страница дашборда |
| `core/employee_analysis.py` | `EmployeeMetricsCalculator` |
| `core/employee_plans.py` | Расчёт планов, `BAR_NAME_MAPPING` |
| `core/iiko_api.py` | `get_employee_metrics_from_shifts()`, `get_cash_shifts()` |
| `app.py` | Endpoints `/api/employee-analytics`, `/api/employee-compare` |
| `data/bar_plans.json` | Планы ТТ по дням |

## Как работает

### Источники данных

```
Cash Shifts API  →  Сотрудник, локация, дата, часы
OLAP Reports     →  Выручка, чеки, категории
Groups API       →  pointOfSaleId → название точки
bar_plans.json   →  Планы по ТТ
```

### Определение места работы

```
Cash Shift → pointOfSaleId → Groups API → название точки
```

**Важно**: Раньше использовали `get_attendance()`, но он возвращал "Пивная культура" для всех. Cash Shifts решает эту проблему.

### Расчёт плана сотрудника

```
План = Σ(план_ТТ[дата] для каждого дня, когда сотрудник работал)
```

Пример: Артемий работал 12 смен на Кременчугской (план 43770/день).
Итого: 12 × 43770 = 525 240 руб.

### Маппинг точек

```python
BAR_NAME_MAPPING = {
    "Пивная культура": "Кременчугская",
    "Большой пр. В.О": "Большой пр В.О.",  # точка!
}
```

## API

### POST /api/employee-analytics

```json
{
  "employee_name": "Артемий Новаев",
  "date_from": "2026-01-01",
  "date_to": "2026-01-22"
}
```

Response: `total_revenue`, `total_checks`, `avg_check`, `shifts_count`, `work_hours`, `plan_fact_percent`, `draft_share`, `bottles_share`, `kitchen_share`

### POST /api/employee-compare

Сравнение нескольких сотрудников. Один OLAP-запрос для всех.

## Дизайн (2026-01-24)

- Шрифт: IBM Plex Mono
- Цвета: тёплая палитра, акцент #D97757
- Светлая/тёмная тема
- Вкладки: Анализ | Сравнение

## Changelog

- 2026-01-25: Вынесено в отдельный файл
- 2026-01-24: Редизайн "Тёплый минимализм"
- 2026-01-23: Переход на Cash Shifts API
- 2026-01-22: Создан модуль
