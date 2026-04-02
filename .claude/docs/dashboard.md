# Главный дашборд

## Что это

Основной дашборд системы с 15 метриками эффективности баров. Показывает выручку, доли категорий, наценку, прибыль, списания баллов за выбранный период.

## Файлы

- [`core/dashboard_analysis.py`](../../core/dashboard_analysis.py) — расчёт 15 метрик из OLAP данных
- [`core/comparison_calculator.py`](../../core/comparison_calculator.py) — сравнение периодов
- [`core/trends_analyzer.py`](../../core/trends_analyzer.py) — тренды по неделям
- [`core/export_manager.py`](../../core/export_manager.py) — экспорт Excel/PDF
- [`core/plans_manager.py`](../../core/plans_manager.py) — планы выручки
- [`routes/dashboard.py`](../../routes/dashboard.py) — Flask endpoint'ы
- [`static/js/dashboard/modules/*.js`](../../static/js/dashboard/modules/) — frontend модули

---

## Как работает

### 15 метрик дашборда

Все метрики рассчитываются из ОДНОГО комплексного OLAP запроса (`get_all_sales_report`):

```python
# core/dashboard_analysis.py:14-108
def calculate_metrics(self, all_sales_data):
    # Разделяем по категориям на основе DishGroup.TopParent
    draft_records = []    # "Напитки Розлив"
    bottles_records = []  # "Напитки Фасовка"
    kitchen_records = []  # Всё остальное

    # 1-3. Выручка по категориям
    draft_revenue = self._sum_revenue(draft_records)
    bottles_revenue = self._sum_revenue(bottles_records)
    kitchen_revenue = self._sum_revenue(kitchen_records)
    total_revenue = draft_revenue + bottles_revenue + kitchen_revenue

    # 4-6. Доли категорий (%)
    draft_share = (draft_revenue / total_revenue * 100) if total_revenue > 0 else 0
    bottles_share = (bottles_revenue / total_revenue * 100) if total_revenue > 0 else 0
    kitchen_share = (kitchen_revenue / total_revenue * 100) if total_revenue > 0 else 0

    # 7. Количество чеков (уникальные заказы)
    total_checks = self._count_unique_orders(...)

    # 8. Средний чек
    avg_check = (total_revenue / total_checks) if total_checks > 0 else 0

    # 9-11. Наценка по категориям (%)
    draft_markup = self._calculate_weighted_markup(draft_records)
    bottles_markup = self._calculate_weighted_markup(bottles_records)
    kitchen_markup = self._calculate_weighted_markup(kitchen_records)

    # 12. Средняя наценка
    avg_markup = self._calculate_weighted_markup(all_records)

    # 13. Прибыль (маржа)
    total_margin = (
        self._sum_margin(draft_records) +
        self._sum_margin(bottles_records) +
        self._sum_margin(kitchen_records)
    )

    # 14. Списания баллов
    loyalty_points = self._sum_discounts(all_records)
```

### Таблица метрик

| № | Метрика | Формула | Ед. изм. |
|---|---------|---------|----------|
| 1 | Выручка | Σ(DishDiscountSumInt) | ₽ |
| 2 | Чеки | count(DISTINCT UniqOrderId.Id) | шт |
| 3 | Средний чек | Выручка / Чеки | ₽ |
| 4 | Доля розлива | Розлив / Выручка × 100 | % |
| 5 | Доля фасовки | Фасовка / Выручка × 100 | % |
| 6 | Доля кухни | Кухня / Выручка × 100 | % |
| 7 | Выручка розлив | Σ(DishDiscountSumInt) для розлива | ₽ |
| 8 | Выручка фасовка | Σ(DishDiscountSumInt) для фасовки | ₽ |
| 9 | Выручка кухня | Σ(DishDiscountSumInt) для кухни | ₽ |
| 10 | % наценки | Σ(MarkUp×Cost)/Σ(Cost) | % |
| 11 | Прибыль | Выручка - Себестоимость | ₽ |
| 12 | Наценка розлив | Взвешенная для розлива | % |
| 13 | Наценка фасовка | Взвешенная для фасовки | % |
| 14 | Наценка кухня | Взвешенная для кухни | % |
| 15 | Списания баллов | Σ(DiscountSum) | баллов |

---

### Планы выручки

#### Пропорциональный расчёт

Планы хранятся как месячные значения, для произвольного периода рассчитываются пропорционально:

```python
# core/plans_manager.py:455-559
def calculate_plan_for_period(self, venue_key, start_date_str, end_date_str):
    # 1. Находим все месяцы в периоде
    months_data = self._get_months_in_period(start_date, end_date)
    # Returns: [(year, month, ratio), ...]

    # 2. Для каждого месяца берём пропорциональную долю
    for year, month, ratio in months_data:
        month_plan = self.get_monthly_plan(venue_key, year, month)

        # Абсолютные метрики (выручка, прибыль, чеки) суммируем пропорционально
        for metric in ['revenue', 'profit', 'checks']:
            result[metric] += month_plan[metric] * ratio

        # Относительные метрики (доли, наценки) усредняем с весом
        for metric in ['draftShare', 'markupPercent']:
            weighted_sums[metric] += month_plan[metric] * ratio

    # 3. Рассчитываем средневзвешенные относительные метрики
    if total_weight > 0:
        for metric in relative_metrics:
            result[metric] = weighted_sums[metric] / total_weight
```

#### Weekend Weighting

Пт/Сб приносят ~2x выручки — учитывается при расчёте пропорциональной доли:

```python
# core/plans_manager.py:386-400
WEEKEND_WEIGHT = 2.0
WEEKDAY_WEIGHT = 1.0

def _day_weight(self, d: date) -> float:
    """вес дня: пт(4)/сб(5) = 2x, остальные = 1x"""
    return self.WEEKEND_WEIGHT if d.weekday() in (4, 5) else self.WEEKDAY_WEIGHT

def _weighted_days(self, start: date, end: date) -> float:
    """Сумма весов дней в диапазоне"""
    total = 0.0
    d = start
    while d <= end:
        total += self._day_weight(d)
        d += timedelta(days=1)
    return total
```

**Формула ratio:**
```
ratio = weighted_days(период в месяце) / weighted_days(весь месяц)
```

---

### Сравнение периодов

#### Формулы

```python
# core/comparison_calculator.py
diff_abs = current - previous
diff_percent = ((current - previous) / previous * 100) if previous > 0 else 0
trend = 'up' if diff_abs > 0 else 'down' if diff_abs < 0 else 'stable'
```

#### Endpoint

```
POST /api/compare/periods
Body: {
    "current": {"dateFrom": "...", "dateTo": "..."},
    "previous": {"dateFrom": "...", "dateTo": "..."}
}
```

---

### Тренды по неделям

#### Агрегация по неделям

```python
# core/trends_analyzer.py
def calculate_trend(self, daily_data, metric_field):
    """
    daily_data: {date: {metric: value, ...}, ...}
    Returns: {week_number: aggregated_value, ...}
    """
    weekly_data = {}
    for date_str, data in daily_data.items():
        week_num = datetime.fromisoformat(date_str).isocalendar()[1]
        if week_num not in weekly_data:
            weekly_data[week_num] = 0
        weekly_data[week_num] += data.get(metric_field, 0)

    return weekly_data
```

#### Endpoint

```
GET /api/trends/:venue/:metric
Query: dateFrom, dateTo
Returns: {week: value, ...}
```

---

## API endpoint'ы

### Основная аналитика

```
POST /api/dashboard-analytics
Body: {
    "venue": "bolshoy" | "ligovskiy" | "kremenchugskaya" | "varshavskaya" | "",
    "dateFrom": "YYYY-MM-DD",
    "dateTo": "YYYY-MM-DD"
}
Response: {
    "metrics": [...],  # 15 метрик
    "plan": {...},     # план на период
    "comparison": {...}# сравнение с предыдущим периодом
}
```

### Планы

```
GET /api/plans?venue=...&dateFrom=...&dateTo=...
POST /api/plans
DELETE /api/plans?period=...
```

### Сравнение

```
POST /api/compare/periods
POST /api/compare/venues
```

### Тренды

```
GET /api/trends/:venue/:metric?dateFrom=...&dateTo=...
```

### Экспорт

```
POST /api/export/excel
POST /api/export/pdf
```

---

## Зависимости

### От каких модулей зависит
- `core/olap_reports.py` → данные из iiko
- `core/plans_manager.py` → планы выручки
- `core/venues_manager.py` → названия заведений

### Кто использует
- Frontend дашборд (`dashboard.html` + JS модули)
- PWA виджет для Android
- Telegram bot (частично)

---

## Changelog

- **2026-03-27** — Создан документ dashboard.md с описанием 15 метрик, формул расчёта, планов и weekend weighting
