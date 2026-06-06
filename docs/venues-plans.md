# Торговые точки и планы

## Что это

Модуль управления торговыми точками (4 бара) и планами выручки. Включает расчёт пропорциональных планов для произвольных периодов с учётом weekend weighting.

## Двухфайловая система планов

### 1. `data/plansdashboard.json` — Месячные планы (UI)

**Назначение:** Планы на месяц с 16 метриками, редактируются через UI дашборда.

**Формат:**
```json
{
  "plans": {
    "bolshoy_2025-10": {
      "revenue": 1201750.0,
      "profit": 795564.1,
      "checks": 1045,
      "averageCheck": 1150.0,
      "draftShare": 60.0,
      "packagedShare": 25.0,
      "kitchenShare": 15.0,
      "revenueDraft": 721050.0,
      "revenuePackaged": 300437.5,
      "revenueKitchen": 180262.5,
      "markupPercent": 195.86,
      "markupDraft": 260.0,
      "markupPackaged": 120.0,
      "markupKitchen": 160.0,
      "loyaltyWriteoffs": 60087.5,
      "tapActivity": 100.0
    }
  }
}
```

**Ключ:** `venue_key_YYYY-MM` (например, `bolshoy_2025-10`)

**16 метрик:**
- Абсолютные: `revenue`, `profit`, `checks`, `loyaltyWriteoffs`, `revenueDraft`, `revenuePackaged`, `revenueKitchen`
- Относительные: `averageCheck`, `draftShare`, `packagedShare`, `kitchenShare`, `markupPercent`, `markupDraft`, `markupPackaged`, `markupKitchen`, `tapActivity`

### 2. `data/daily_plans.json` — Ежедневные планы (auto)

**Назначение:** Автоматически рассчитанные планы на каждый день из месячных планов.

**Формат:**
```json
{
  "2025-10-05": {
    "bolshoy": 30044,
    "ligovskiy": 16388,
    "kremenchugskaya": 37500,
    "varshavskaya": 25000
  },
  "2025-10-06": {
    "bolshoy": 60088,
    "ligovskiy": 32775,
    "kremenchugskaya": 75000,
    "varshavskaya": 50000
  }
}
```

**Формула расчёта:**
```
weight(день) = 2.0 если Пт(4) или Сб(5), иначе 1.0
month_weight = Σ(weight(день) для всех дней месяца)
plan_per_weight = monthly_revenue / month_weight
daily_plan = plan_per_weight × weight(день)
```

**Пример (Октябрь 2025):**
- 22 будних дня × 1.0 = 22
- 9 выходных (Пт/Сб) × 2.0 = 18
- Итого весов: 40
- План на будни: 1 201 750 / 40 × 1 = 30 044 ₽
- План на Пт/Сб: 1 201 750 / 40 × 2 = 60 088 ₽

**Override веса дня:** для конкретной даты заведения вес можно переопределить
(праздник = например 5, закрытый день = 0). Вес дня берётся из
`day_weight_overrides.json`, иначе — значение по умолчанию (1 или 2). Так как в
знаменателе стоит сумма ВСЕХ весов месяца, при повышении веса одного дня остальные
автоматически уменьшаются, а сумма за месяц остаётся равной месячному плану.

**Агрегат `all`:** дневной `all` = сумма дневных планов реальных точек за день
(каждая со своими override). Отдельный месячный план `all_*` для подневной
разбивки не используется.

## Файлы

- [`core/day_weights.py`](../../core/day_weights.py) — **канонический модуль весов дня** (единый источник формулы, override-aware)
- [`core/day_weight_overrides.py`](../../core/day_weight_overrides.py) — менеджер override весов дней (праздники, закрытые дни)
- [`core/venues_config.py`](../../core/venues_config.py) — конфигурация 4 точек
- [`core/venues_manager.py`](../../core/venues_manager.py) — маппинг venue_key → название
- [`core/plans_manager.py`](../../core/plans_manager.py) — CRUD планов, расчёт периода (импортирует веса из `day_weights`)
- [`core/daily_plans_generator.py`](../../core/daily_plans_generator.py) — материализация `daily_plans.json` (производный кэш)
- [`data/plansdashboard.json`](../../data/plansdashboard.json) — месячные планы (16 метрик, UI) — **источник правды**
- [`data/day_weight_overrides.json`](../../data/day_weight_overrides.json) — override весов дней по `(venue, date)`
- [`data/daily_plans.json`](../../data/daily_plans.json) — ежедневные планы (**производный кэш** из месячных + override)

> **Единый механизм (2026-06-06).** Вся логика веса дня живёт в `core/day_weights.py` и больше нигде не дублируется. И генератор дневного плана, и расчёт плана за период (`plans_manager.calculate_plan_for_period`) берут вес дня оттуда. Источник правды — месячные планы + override весов; `daily_plans.json` лишь материализует результат для потребителей (бонусы сотрудников, метрики выручки).

---

## Как работает

### Торговые точки

#### Конфигурация

```python
# core/venues_config.py
VENUES = {
    'bolshoy': {
        'name': 'Большой пр В.О.',
        'taps': 24,
        'address': 'Большой проспект В.О., ...'
    },
    'ligovskiy': {
        'name': 'Лиговский',
        'taps': 12,
        'address': 'Лиговский пр., ...'
    },
    'kremenchugskaya': {
        'name': 'Кременчугская',
        'taps': 12,
        'address': 'ул. Кременчугская, ...'
    },
    'varshavskaya': {
        'name': 'Варшавская',
        'taps': 12,
        'address': 'Варшавская ул., ...'
    }
}
```

#### Маппинг имён

```python
# core/venues_manager.py
BAR_NAME_MAPPING = {
    'Кременчугская': 'kremenchugskaya',
    'Варшавская': 'varshavskaya',
    'Большой пр В.О.': 'bolshoy',
    'Лиговский': 'ligovskiy'
}

def normalize_bar_name(name):
    """Нормализация названия бара"""
    return name.strip().lower()
```

---

### Кто использует планы

#### Dashboard (`routes/dashboard.py`)

Использует `plansdashboard.json` (месячные планы) для расчёта планов за период через `plans_manager.calculate_plan_for_period()`.
Сохранение через `save_plan_with_regeneration()` — пересчитывает `daily_plans.json` только для одного заведения и месяца.

#### Сотрудник и ЗП (`routes/employee.py`)

Использует `daily_plans.json` через `core/employee_plans.get_employee_plan_by_shifts()` для:
- Расчёта плана сотрудника по кассовым сменам
- Используется в расчёте бонусов и KPI

#### Метрики выручки (`core/revenue_metrics.py`)

Использует `daily_plans.json` через `get_daily_plan_for_date()` для расчёта 4 метрик:
- `current` — фактическая выручка
- `plan` — плановая выручка (сумма daily_plans)
- `expected` — прогноз
- `average` — средняя дневная

---

### Расчёт плана для периода

#### Алгоритм

```python
# core/plans_manager.py:455-559
def calculate_plan_for_period(self, venue_key, start_date_str, end_date_str):
    """
    1. Находим все месяцы в периоде
    2. Для каждого месяца берём пропорциональную долю
    3. Суммируем абсолютные метрики
    4. Усредняем относительные метрики
    """
```

#### Шаг 1: Месяцы в периоде

```python
# core/plans_manager.py:402-438
def _get_months_in_period(self, start_date, end_date):
    """
    Returns: [(year, month, ratio), ...]
    ratio = взвешенные_дни_периода_в_месяце / взвешенные_дни_месяца
    """
    months = []
    current = start_date.replace(day=1)

    while current <= end_date:
        year = current.year
        month = current.month
        days_in_month = monthrange(year, month)[1]

        # Границы периода внутри месяца
        period_start = max(start_date, current)
        month_end = current.replace(day=days_in_month)
        period_end = min(end_date, month_end)

        # Взвешенная доля
        period_weight = self._weighted_days(period_start, period_end)
        month_weight = self._weighted_days(current, month_end)
        ratio = period_weight / month_weight if month_weight > 0 else 0

        months.append((year, month, ratio))

        # Следующий месяц
        if month == 12:
            current = current.replace(year=year + 1, month=1)
        else:
            current = current.replace(month=month + 1)

    return months
```

#### Шаг 2: Weekend weighting (единый модуль)

Логика веса дня вынесена в `core/day_weights.py` и больше НЕ дублируется в
`plans_manager`. `plans_manager._get_months_in_period` вызывает `weighted_days`
оттуда, передавая override весов конкретного заведения за месяц.

```python
# core/day_weights.py
WEEKDAY_WEIGHT = 1.0
WEEKEND_WEIGHT = 2.0  # пятница(4)/суббота(5)

def get_day_weight(d, overrides=None):
    """Вес дня: override[date] если задан (в т.ч. 0.0), иначе пт/сб=2, остальные=1."""
    if overrides and d.isoformat() in overrides:
        return float(overrides[d.isoformat()])
    return WEEKEND_WEIGHT if d.weekday() in (4, 5) else WEEKDAY_WEIGHT

def weighted_days(start, end, overrides=None):
    """Сумма весов дней в инклюзивном диапазоне [start, end]."""
    ...
```

**Пример:**
```
Период: Пт-Вс (3 дня)
Пт (weight=2) + Сб (weight=2) + Вс (weight=1) = 5 весовых единиц
```

#### Шаг 3: Суммирование абсолютных метрик

```python
# core/plans_manager.py:487-520
absolute_metrics = ['revenue', 'profit', 'checks', 'loyaltyWriteoffs',
                    'revenueDraft', 'revenuePackaged', 'revenueKitchen']

for year, month, ratio in months_data:
    month_plan = self.get_monthly_plan(venue_key, year, month)
    if month_plan:
        for metric in absolute_metrics:
            result[metric] += month_plan[metric] * ratio
```

**Формула:**
```
План_выручки = Σ(План_месяц × ratio)
```

#### Шаг 4: Усреднение относительных метрик

```python
# core/plans_manager.py:493-537
relative_metrics = ['averageCheck', 'draftShare', 'packagedShare', 'kitchenShare',
                    'markupPercent', 'markupDraft', 'markupPackaged', 'markupKitchen',
                    'tapActivity']

weighted_sums = {metric: 0.0 for metric in relative_metrics}
total_weight = 0.0

for year, month, ratio in months_data:
    weight = ratio
    total_weight += weight

    for metric in relative_metrics:
        if metric in month_plan:
            weighted_sums[metric] += month_plan[metric] * weight

# Средневзвешенное
if total_weight > 0:
    for metric in relative_metrics:
        result[metric] = weighted_sums[metric] / total_weight
```

**Формула:**
```
Средняя_доля = Σ(Доля_месяц × weight) / Σ(weight)
```

---

### Планы дашборда (15 метрик)

#### Формат

```json
// data/plansdashboard.json
{
  "plans": {
    "bolshoy_2026-03": {
      "revenue": 1234567.0,
      "checks": 5000,
      "averageCheck": 247.0,
      "draftShare": 45.0,
      "packagedShare": 30.0,
      "kitchenShare": 25.0,
      "revenueDraft": 555555.0,
      "revenuePackaged": 370370.0,
      "revenueKitchen": 308642.0,
      "markupPercent": 200.0,
      "profit": 617284.0,
      "markupDraft": 250.0,
      "markupPackaged": 180.0,
      "markupKitchen": 150.0,
      "loyaltyWriteoffs": 50000.0,
      "tapActivity": 75.0
    }
  },
  "metadata": {...}
}
```

#### Схема валидации

```python
# core/plans_manager.py:28-45
PLAN_SCHEMA = {
    'revenue': (float, int),
    'checks': (int,),
    'averageCheck': (float, int),
    'draftShare': (float, int),
    'packagedShare': (float, int),
    'kitchenShare': (float, int),
    'revenueDraft': (float, int),
    'revenuePackaged': (float, int),
    'revenueKitchen': (float, int),
    'markupPercent': (float, int),
    'profit': (float, int),
    'tapActivity': (float, int),
    ...
}
```

---

## UI управления планами

### Вкладка "Планы"

**Файлы:**
- [`templates/dashboard/plans_tab.html`](../../templates/dashboard/plans_tab.html) — HTML вкладки с модальным окном
- [`static/js/dashboard/modules/plans.js`](../../static/js/dashboard/modules/plans.js) — логика редактирования/сохранения

### Функции UI

| Функция | Описание |
|---------|----------|
| Просмотр | Таблица план vs факт с отклонениями и % выполнения |
| Создание | Кнопка "➕ Создать план" — открывает модальное окно |
| Редактирование | Кнопка "✏️ Редактировать" — загрузка текущих значений |
| Удаление | Кнопка "❌ Удалить" — подтверждение перед удалением |
| Валидация | Проверка суммы долей (100% ±1%), неотрицательность |
| Авто-расчёт | revenueDraft = revenue × draftShare / 100 |

### Модальное окно редактирования

**5 секций:**
1. Основные показатели (выручка, чеки, средний чек, прибыль)
2. Доли категорий (%) — розлив, фасовка, кухня
3. Выручка по категориям (авто-расчёт)
4. Наценки (%) — общая, розлив, фасовка, кухня
5. Прочее (списания баллов, активность кранов)

**Валидация:**
```javascript
// Проверка суммы долей
const sharesSum = draftShare + packagedShare + kitchenShare;
if (Math.abs(sharesSum - 100) > 1) {
    error: "Сумма долей должна быть 100% (сейчас ${sharesSum.toFixed(1)}%)"
}
```

---

## Override весов дней и страница «Планы по дням»

### Зачем

Позволяет заложить особый вес для конкретного дня (праздник = например 5, закрытый
день = 0). Остальные дни месяца пересчитываются автоматически по той же формуле,
сумма дневных планов за месяц остаётся равной месячному плану.

### Хранилище

`data/day_weight_overrides.json` (на проде — `/kultura/`):
```json
{
  "overrides": {
    "bolshoy":   { "2025-11-04": 5.0 },
    "ligovskiy": { "2025-12-31": 0.0 }
  },
  "metadata": { "version": "1.0", "lastUpdate": "..." }
}
```

Хранятся только исключения по `(venue, date)`. Обычные дни (1 или 2) в файле
отсутствуют. Если выставить вес, равный значению по умолчанию для этого дня, запись
не сохраняется (no-op cleanup). Менеджер `core/day_weight_overrides.py` — атомарная
запись + блокировки как в `PlansManager`. Изменение override запускает точечную
регенерацию `daily_plans.json` для этого заведения+месяца и пересчёт агрегата `all`.

### Страница «Планы по дням»

Подвкладка внутри вкладки «Планы» дашборда:
- [`templates/dashboard/plans_tab.html`](../../templates/dashboard/plans_tab.html) — подвкладки «Месячные»/«По дням», таблица дней, модалка веса дня
- [`static/js/dashboard/modules/daily_plans.js`](../../static/js/dashboard/modules/daily_plans.js) — `DailyPlansViewer`

Таблица показывает по каждому дню месяца: дату, день недели, вес, план на день,
кнопки «Изменить»/«Сброс». Пт/сб и дни-override подсвечены. Футер-валидация
показывает сумму по дням, месячный план и совпадают ли они (`sum_check`). Заведение
берётся из глобального селектора; месяц — из локального селектора. Для `all` —
только просмотр (агрегат не редактируется).

### Поведение по дизайну (подтверждено, НЕ баги)

Эти эффекты вытекают из детерминизма «план дня = функция(месячный план, веса)» и
подтверждены как намеренные:

- **Ретроактивность.** Правка месячного плана или веса дня переписывает ВСЕ дни
  месяца, включая уже прошедшие. Бонусы не снапшотятся — пересчитываются на лету,
  поэтому изменение задним числом меняет бонусы за уже отработанные смены. Оставлено
  как есть (детерминизм и прозрачность важнее заморозки).
- **Праздник = выше планка.** Override веса вверх (например ×5) поднимает ПЛАН этого
  дня, поэтому бонус за смену в праздник, как правило, обнуляется (план недостижим).
  Это намеренно: больше вес = выше плановая планка.
- **Закрытый день (вес 0).** Вес 0 означает «бар не работает» → смен нет → премий
  нет. Если по плану 0, дневной бонус за этот день = 0 (включая базовую 1000).
- **Верхней границы веса нет** (по текущему решению). Вес валидируется только на
  `>= 0`.

## API endpoint'ы

Все правки идут только через эти endpoint'ы (UI = единственный путь редактирования).

### Получение плана

```
GET /api/plans/<venue_key>/<period_key>
Response: {
    "revenue": 123456.0,
    "checks": 500,
    ...
}
```

**Формат ключа:** `venue_key_YYYY-MM`
- Пример: `bolshoy_2025-10`

### Сохранение плана

```
POST /api/plans/<venue_key>/<period_key>
Body: {
    "revenue": 1200000.0,
    "checks": 1000,
    "draftShare": 60.0,
    ...  # 16 метрик
}
```

### Удаление плана

```
DELETE /api/plans/<venue_key>/<period_key>
```

### Расчёт плана для произвольного периода

```
GET /api/plans/calculate/<venue_key>/<start_date>/<end_date>
Response: {
    "revenue": 500000.0,  # пропорционально из месячного плана
    ...
}
```

### Получение всех планов (JSON)

```
GET /api/plans
Response: {
    "plans": { "<venue>_<YYYY-MM>": {...}, ... },
    "periods": ["bolshoy_2026-05", "ligovskiy_2026-05", ...]
}
```

### Экспорт всех планов (xlsx)

```
GET /api/plans/export
Response: xlsx-файл (один лист "All Plans", строки = период × заведение, 16 столбцов-метрик)
```

### Диагностика хранилища

```
GET /api/storage/diagnose
Response: { "persistent_storage_active": bool, "plansdashboard": {...}, "daily_plans": {...} }
```

### Подневная разбивка (страница «Планы по дням»)

```
GET /api/plans/daily/<venue_key>/<year>/<month>
Response: {
    "venue": "bolshoy", "year": 2025, "month": 11,
    "editable": true,                 # false для агрегата 'all'
    "monthly_revenue": 1000500.0,
    "month_weight": 43.0,             # null для 'all'
    "days": [ { "date": "2025-11-01", "weekday": 5, "weekday_name": "сб",
                "weight": 2.0, "is_override": false, "daily_plan": 46534.88 }, ... ],
    "daily_sum": 1000500.06,
    "tolerance": 1.0,
    "sum_check": true                 # |daily_sum - monthly_revenue| <= tolerance
}
```

```
POST /api/plans/daily/<venue_key>/<year>/<month>
Body: { "date": "2025-11-04", "weight": 5.0 }   # вес >= 0; 'all' -> 400
Response: обновлённая подневная разбивка (как GET)
```

```
DELETE /api/plans/daily/<venue_key>/<year>/<month>/<date>
# сброс override веса дня к умолчанию (идемпотентно)
Response: обновлённая подневная разбивка (как GET)
```

---

## Формулы

### Пропорциональный план

```
ratio = weighted_days(период) / weighted_days(месяц)

План_периода = Σ(План_месяц × ratio)
```

### Weekend weight

```
weight(день) = 2.0 если день = Пт(4) или Сб(5)
weight(день) = 1.0 иначе

weighted_days = Σ(weight(день) для каждого дня)
```

### Доля месяца

```
Доля = (Дни периода в месяце / Дни в месяце) × 100%
```

---

## Зависимости

### От каких модулей зависит
- Нет внешних зависимостей (работает с JSON файлами)

### Кто использует
- `core/dashboard_analysis.py` → планы для дашборда
- `core/employee_plans.py` → планы для сотрудников
- `routes/dashboard.py` → API endpoint'ы

---

## Changelog

### 2026-06-06 — Единый механизм дневного плана + override весов + страница «Планы по дням»

**Что сделано:**
- Логика веса дня сведена к одному каноническому модулю `core/day_weights.py`; убран дубль `_day_weight`/`_weighted_days` из `plans_manager.py` — теперь он импортирует `weighted_days` оттуда. И генератор дневного плана, и расчёт периода берут вес из одного места.
- Добавлены **override весов дней** (`core/day_weight_overrides.py` + `data/day_weight_overrides.json`): праздник = N, закрытый день = 0; остальные дни месяца пересчитываются автоматически, сумма за месяц = месячному плану.
- Агрегат `all` в `daily_plans.json` теперь = сумма дневных планов реальных точек (override точек автоматически в него попадают).
- `calculate_plan_for_period` стал override-aware: доли месяцев считаются с override конкретного заведения (консистентно с дневной разбивкой).
- Новая редактируемая под-вкладка «Планы по дням» внутри вкладки «Планы» + 3 эндпоинта `/api/plans/daily/...` (GET/POST/DELETE) с проверкой «сумма дней = месяц».
- Попутно: `save_daily_plans` стал атомарным (tmp+os.replace+backup) и сбрасывает кэш `DailyPlansReader` (`clear_plans_cache` + инвалидация по mtime, в т.ч. между gunicorn-воркерами); удаление месячного плана обнуляет дневные значения удалённой точки (фикс «призрачных» значений и завышенного агрегата `all`), подчищает override и пересобирает `all`.

**Изменённые файлы:**
- `core/day_weights.py` (новый), `core/day_weight_overrides.py` (новый), `data/day_weight_overrides.json` (новый)
- `core/daily_plans_generator.py` — импорт из `day_weights`, overrides, атомарная запись, агрегат `all`
- `core/plans_manager.py` — удалён дубль весов, override-aware расчёт периода
- `routes/dashboard.py` — 3 эндпоинта daily + подчистка override при delete; `extensions.py` — менеджер override
- `templates/dashboard/plans_tab.html`, `static/js/dashboard/modules/daily_plans.js` (новый), `static/js/dashboard/core/{api,config}.js`, `static/js/dashboard/main.js`

### 2026-05-15 — Устранение костылей редактирования планов + экспорт

**Что сделано:**
- Удалены 5 legacy/костыльных endpoint'ов из `routes/dashboard.py`: `POST /api/plans/sync-from-repo`, `POST /api/plans` (body-based), `GET /api/plans/<period>` (без venue), `DELETE /api/plans/<period>` (без venue), `POST /api/plans/migrate-to-monthly`
- Удалён метод `PlansManager.import_monthly_plans_from_weekly()` (одноразовая миграция, давно отработала)
- Удалены legacy-скрипты `scripts/import_export/import_plans_from_excel.py` и `import_plans_from_excel_new.py` — редактирование только через UI
- Починено прямое чтение `plansdashboard.json` в `revenue_metrics` — теперь через `plans_manager.get_plan()` (единая точка)
- Добавлен cross-worker file lock (`portalocker`) в `save_plan` и `delete_plan` — защита от гонки между gunicorn-воркерами
- Добавлен `GET /api/plans/export` — экспорт всех планов одним flat-листом xlsx (Period × Venue × 16 метрик)
- В UI вкладки «Планы» добавлена кнопка «Экспорт»

**Изменённые файлы:**
- `routes/dashboard.py` — удаление 5 endpoint'ов, новый export endpoint, фикс revenue_metrics
- `core/plans_manager.py` — file lock через portalocker, удаление import_monthly_plans_from_weekly, текст ошибки
- `requirements.txt` — +portalocker, +openpyxl
- `templates/dashboard/plans_tab.html` — кнопка «Экспорт»
- `static/js/dashboard/modules/plans.js` — обработчик экспорта
- `scripts/import_export/import_plans_from_excel*.py` — удалены

### 2026-04-03 — Удаление bar_plans.json, точечная регенерация daily plans

**Что сделано:**
- Удалён `data/bar_plans.json` — legacy файл с русскими названиями, дублировал `daily_plans.json`
- `core/employee_plans.py` переписан: `DailyPlansReader` читает только `daily_plans.json` через `get_data_path()` (Render Disk compatible)
- `PlansManager.save_plan()` больше не вызывает полную регенерацию daily plans; добавлен `save_plan_with_regeneration()` с точечным пересчётом одного месяца одного заведения
- `DailyPlansGenerator.regenerate_for_venue_month()` — новый метод для точечной регенерации
- Исправлен Excel import: удалён недостижимый dead code после `return`, исправлена кодировка в `source` строке
- `BAR_NAME_MAPPING` остаётся в `employee_plans.py` — единственный источник, импортируется из `kpi_calculator.py` и `routes/employee.py`

**Изменённые файлы:**
- `core/employee_plans.py` — полная переработка
- `core/daily_plans_generator.py` — добавлен `regenerate_for_venue_month()`
- `core/plans_manager.py` — разделены `save_plan()` и `save_plan_with_regeneration()`
- `routes/dashboard.py` — Excel import fixed, endpoint updated
- `data/bar_plans.json` — удалён

### 2026-04-01 — Двухфайловая система планов

**Что сделано:**
- Разделены планы на 2 файла: `plansdashboard.json` (месячные, 16 метрик) и `daily_plans.json` (ежедневные, auto)
- Создан `core/daily_plans_generator.py` — расчёт daily plans из monthly с weekend weighting (Пт/Сб = 2x)
- Обновлены `routes/employee.py`, `core/revenue_metrics.py` — используют `get_daily_plan_for_date()`
- UI дашборда редактирует `plansdashboard.json`, при сохранении авто-генерируется `daily_plans.json`

**Формула:**
```
month_weight = Σ(weight(день)) где Пт/Сб=2.0, остальные=1.0
daily_plan = (monthly_revenue / month_weight) × day_weight
```

**Изменённые файлы:**
- `core/daily_plans_generator.py` — создан
- `core/plans_manager.py` — авто-генерация при сохранении
- `routes/employee.py` — использование daily_plans
- `core/revenue_metrics.py` — использование daily_plans
- `.claude/docs/venues-plans.md` — документация двухфайловой системы

### 2026-03-27 — Создан документ venues-plans.md
