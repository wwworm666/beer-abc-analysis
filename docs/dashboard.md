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
# core/dashboard_analysis.py
def calculate_metrics(self, all_sales_data):
    # Разделяем по категориям на основе DishGroup.TopParent
    draft_records = []    # "Напитки Розлив"
    bottles_records = []  # "Напитки Фасовка"
    kitchen_records = []  # "ЕДА" (строго эта группа)
    other_records = []    # Всё остальное: НАБОРЫ, Чай/Кофе, Газ и Пэт, ...

    # Выручка по категориям (итог = все 4 категории)
    total_revenue = draft_revenue + bottles_revenue + kitchen_revenue + other_revenue

    # Доли категорий (%): 4 доли в сумме дают 100%,
    # на дашборде отображаются только розлив/фасовка/кухня
    draft_share = draft_revenue / total_revenue * 100
    ...

    # Чеки (уникальные заказы) и средний чек — по ВСЕМ записям
    total_checks = self._count_unique_orders(all_records)
    avg_check = total_revenue / total_checks

    # Наценка — агрегатом, как строка «Итого» в OLAP iiko:
    # (Σ выручка - Σ себестоимость) / Σ себестоимость
    draft_markup = self._calculate_markup(draft_records)
    ...
    avg_markup = self._calculate_markup(all_records)

    # Прибыль (маржа) — по всем 4 категориям
    total_margin = draft + bottles + kitchen + other

    # Списания баллов
    loyalty_points = self._sum_discounts(all_records)
```

### Категории (DishGroup.TopParent)

| Категория | Группы iiko 1-го уровня | Отображается |
|-----------|-------------------------|--------------|
| Розлив | Напитки Розлив | да |
| Фасовка | Напитки Фасовка | да |
| Кухня | ЕДА (строго) | да |
| Прочее | всё остальное: НАБОРЫ, Чай/Кофе, Газ и Пэт, ... | **нет** (only backend: `other_revenue`, `other_share`, `other_markup`) |

До 2026-07-16 «Кухня» включала всё, что не напитки (НАБОРЫ с наценкой ~500%
и Чай/Кофе ~800% завышали наценку кухни: 197% вместо честных 174% по ЕДЕ).

### Таблица метрик

| № | Метрика | Формула | Ед. изм. |
|---|---------|---------|----------|
| 1 | Выручка | Σ(DishDiscountSumInt) по всем записям | ₽ |
| 2 | Чеки | count(DISTINCT UniqOrderId.Id) | шт |
| 3 | Средний чек | Выручка / Чеки | ₽ |
| 4 | Доля розлива | Розлив / Выручка × 100 | % |
| 5 | Доля фасовки | Фасовка / Выручка × 100 | % |
| 6 | Доля кухни | Кухня (ЕДА) / Выручка × 100 | % |
| 7 | Выручка розлив | Σ(DishDiscountSumInt) для розлива | ₽ |
| 8 | Выручка фасовка | Σ(DishDiscountSumInt) для фасовки | ₽ |
| 9 | Выручка кухня | Σ(DishDiscountSumInt) для группы ЕДА | ₽ |
| 10 | % наценки | (Σ выручка − Σ Cost) / Σ Cost, все записи | % |
| 11 | Прибыль | Выручка - Себестоимость (все 4 категории) | ₽ |
| 12 | Наценка розлив | (Σ выручка − Σ Cost) / Σ Cost для розлива | % |
| 13 | Наценка фасовка | (Σ выручка − Σ Cost) / Σ Cost для фасовки | % |
| 14 | Наценка кухня | (Σ выручка − Σ Cost) / Σ Cost для ЕДА | % |
| 15 | Списания баллов | Σ(DiscountSum) | баллов |

**Наценка = агрегат, а не среднее построчных MarkUp.** Формула совпадает со строкой
«Итого» OLAP-отчёта iiko: строки с нулевой себестоимостью (позиции без техкарты)
участвуют выручкой в числителе. `calculate_metrics` возвращает наценку дробью
(2.2448 = 224.48%), округление до 4 знаков; фронт и месячный отчёт умножают на 100.

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

#### Weekend Weighting (единый модуль)

Пт/Сб приносят ~2x выручки. Логика веса дня живёт в `core/day_weights.py` (единый
источник, override-aware) и НЕ дублируется в plans_manager — он импортирует
`weighted_days` оттуда:

```python
# core/day_weights.py
WEEKDAY_WEIGHT = 1.0
WEEKEND_WEIGHT = 2.0  # пятница(4)/суббота(5)

def get_day_weight(d, overrides=None):
    if overrides and d.isoformat() in overrides:
        return float(overrides[d.isoformat()])  # праздник/закрытый день
    return WEEKEND_WEIGHT if d.weekday() in (4, 5) else WEEKDAY_WEIGHT

def weighted_days(start, end, overrides=None):
    """Сумма весов дней в инклюзивном диапазоне [start, end]."""
    ...
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

UI = единственный путь редактирования. См. подробнее [venues-plans.md](venues-plans.md).

```
GET    /api/plans/<venue>/<period>            — получить план
POST   /api/plans/<venue>/<period>            — создать/обновить план
DELETE /api/plans/<venue>/<period>            — удалить план
GET    /api/plans                             — дамп всех планов (JSON)
GET    /api/plans/calculate/<v>/<from>/<to>   — пропорциональный план за период
GET    /api/plans/export                      — экспорт всех планов в xlsx
GET    /api/plans/daily/<v>/<year>/<month>    — подневная разбивка (страница «Планы по дням»)
POST   /api/plans/daily/<v>/<year>/<month>    — задать override веса дня {date, weight}
DELETE /api/plans/daily/<v>/<year>/<month>/<date> — сброс override веса дня
```

> Подвкладка «Месячные» показывает **только плановые значения** (колонки Метрика | План).
> Факт и план/факт-сравнение живут на вкладках «Аналитика» и «Сравнение» — вкладка «Планы»
> отвечает только за просмотр и редактирование самих планов.
>
> Подвкладка «Планы по дням» (внутри вкладки «Планы») показывает подневную разбивку
> месячного плана и позволяет задать особый вес дня (праздник/закрытый день) с
> авто-ренормализацией остальных дней. Единый расчёт — `core/day_weights.py`.
> Подробнее: [venues-plans.md](venues-plans.md).

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

- **2026-07-16** — Сверка метрик с OLAP iiko: (1) «Кухня» = строго группа «ЕДА»; НАБОРЫ, Чай/Кофе, Газ и Пэт выделены в скрытую категорию «Прочее» (`other_revenue/other_share/other_markup` в API есть, карточек на экране нет); (2) наценка считается агрегатом (Σвыручка−Σсебестоимость)/Σсебестоимость вместо средневзвешенного построчного MarkUp — теперь все наценки совпадают с iiko копейка в копейку (фасовка была 134% вместо 139%); (3) точность наценки — 4 знака дроби (224.48% вместо 224.0%). Метрики сотрудников/KPI (зарплата) НЕ менялись.
- **2026-06-06** — Вкладка «Планы» (подвкладка «Месячные») показывает только плановые значения: колонки Факт/Отклонение/% убраны, факт больше не запрашивается.
- **2026-06-06** — Подвкладка «Планы по дням» + 3 эндпоинта `/api/plans/daily/...`. Логика веса дня унифицирована в `core/day_weights.py`; добавлены override весов дней (праздник/закрытый день). Подробнее: [venues-plans.md](venues-plans.md).
- **2026-03-27** — Создан документ dashboard.md с описанием 15 метрик, формул расчёта, планов и weekend weighting
