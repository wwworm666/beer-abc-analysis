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

**16 обязательных метрик + 4 необязательные** (`PlansManager.PLAN_DEFAULTS`: подставляются на
чтении и при сохранении, если поля нет):
- Абсолютные: `revenue`, `profit`, `checks`, `loyaltyWriteoffs`, `revenueDraft`, `revenuePackaged`, `revenueKitchen`, `revenueStrong`
- Относительные: `averageCheck`, `draftShare`, `packagedShare`, `kitchenShare`, `markupPercent`, `markupDraft`, `markupPackaged`, `markupKitchen`, `tapActivity`, `cardChecksShare`, `strongShare`, `markupStrong`
- Необязательные: `cardChecksShare` (дефолт 70, с 2026-09-05) и с 2026-11-03 три поля группы
  «Крепкий алкоголь» — `strongShare` (% выручки), `revenueStrong` (₽), `markupStrong` (%) —
  дефолт 0 = «план не задан» (на карточке дашборда «План не задан»). Крепкий алкоголь есть не у
  всех баров: с 09.10.2026 только на Лиговском.

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
        'taps': 24,          # с 2026-11-09; было 12
        'address': 'Лиговский пр., ...'
    },
    'kremenchugskaya': {
        'name': 'Кременчугская',
        'taps': 12,
        'address': 'ул. Кременчугская, ...'
    },
    'varshavskaya': {
        'name': 'Варшавская',
        'taps': 24,          # с 2026-11-09; было 12
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

> **«Общее» = сумма баров (агрегат).** Ключи `all`/`total`/`общая` (и пустой `''`)
> нормализуются в `calculate_plan_for_period` к `''` → план считается суммированием
> по 4 точкам, а НЕ из отдельной записи `all_*` в `plansdashboard.json` (она больше не
> читается). Поэтому:
> - `/api/revenue-metrics` для «Общее» и `GET /api/plans/all/YYYY-MM` отдают сумму баров;
> - в UI «Все заведения» убрано из окна создания плана, а кнопки «Редактировать/Удалить»
>   для агрегата отключены (редактировать нечего — план задаётся по барам);
> - месяц, где ни у одного бара нет плана, даёт 404 (агрегировать нечего).
> Абсолютные метрики суммируются, относительные (доли, наценки, средний чек) —
> средневзвешенные по долям месяцев/точек.

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

**Крепкий алкоголь (с 2026-11-03).** `revenueStrong` — абсолютная (сумма × ratio), `strongShare`
усредняется как остальные доли, с нулями: у бара или месяца без крепкого его доля и правда 0
(сеть за ноябрь 2026: 3% Лиговского и 0 у остальных баров). `markupStrong` усредняется **только
по месяцам и барам, где она задана** (> 0, `planned_only_metrics`): 0 значит «не задана», а не
«наценка 0%», и среднее с нулями баров без крепкого занизило бы план сети вчетверо. Это совпадает
с агрегатом по себестоимости: бар без крепкого не даёт ни выручки, ни себестоимости крепкого.

```
markupStrong_периода = Σ(markupStrong × weight по планам, где markupStrong > 0)
                       / Σ(weight по тем же планам);    нет ни одного — 0
```

Пример: Лиговский — октябрь без крепкого, ноябрь `strongShare` 3, `markupStrong` 300; за 01.10–30.11
план `revenueStrong` = ноябрьский, `strongShare` = (0 + 3) / 2 = 1,5, `markupStrong` = 300.

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
| Просмотр | Таблица плановых значений (только план: Метрика \| План). Факт и сравнение — на вкладках «Аналитика»/«Сравнение» |
| Создание | Кнопка "Создать план" — открывает модальное окно (месяц, год, заведение — раздел «Форма плана: месяц, год, бар» ниже) |
| Редактирование | Кнопка "Редактировать" — загрузка текущих значений |
| Удаление | Кнопка "Удалить" — подтверждение перед удалением |
| Валидация | Розлив + фасовка + крепкий алкоголь ≤ 100% (кухня — остаток), сумма четырёх долей 100 ± 1, неотрицательность; доля крепкого больше 0 требует его наценку |
| Авто-расчёт | См. ниже — 9 метрик считаются из введённых (формулы повторяют расчёт факта) |

#### Форма плана: месяц, год, бар

С 2026-11-01 (план единого виджета [planning/period-widget-rollout.md](planning/period-widget-rollout.md),
этап 3) значения формы по умолчанию — из общего выбора сайта, а не с часов устройства:

- **месяц и год** — месяц общего периода (`state.currentMonth` / `state.currentYear`: полоса
  «Бар и период» на вкладке «Планы» показывает месяц выбранного периода, у недели — месяц её
  четверга). Будущие месяцы можно — план заводят заранее;
- **список годов** строит `plans.js` (`planYears`), в шаблоне зашитых 2025–2027 больше нет:
  текущий год −1…+1 по часам сервера (`KPeriod.today()`), плюс год общего периода и годы, на
  которые уже заведены планы (ключи `/api/plans` вида `bolshoy_2026-10`, загружаются один раз
  при первом открытии формы). Пример на 01.11.2026 без планов других лет: 2025, 2026, 2027; с
  1 января 2027 — 2026, 2027, 2028;
- **заведение** — общий бар; при «Все бары» — первый бар списка (`bolshoy`): план сети не
  вводится, он считается суммой баров (`planFormDefaults`).

Тесты: `tests/test_plans_form.mjs` (годы, значения по умолчанию, нет часов устройства).

#### Авто-расчёт метрик плана

Вручную вводятся 11 метрик: `revenue`, `averageCheck`, `draftShare`, `packagedShare`,
`strongShare`, `markupDraft`, `markupPackaged`, `markupKitchen`, `markupStrong`,
`cardChecksShare`, `tapActivity`.

Остальные 9 считаются автоматически (`PlansViewer.autoCalculateDerivedMetrics` /
`updateSharesSum`). Большинство формул повторяют расчёт факта в
[`core/dashboard_analysis.py`](../../core/dashboard_analysis.py) — чтобы план и факт были сравнимы:

```
checks           = revenue / averageCheck                     (округление до целого)
kitchenShare     = 100 − draftShare − packagedShare − strongShare   (доля кухни добивает до 100%)
revenueDraft     = revenue × draftShare    / 100
revenuePackaged  = revenue × packagedShare / 100
revenueKitchen   = revenue × kitchenShare  / 100
revenueStrong    = revenue × strongShare   / 100              (крепкий алкоголь, с 2026-11-03)
costᵢ            = revenueᵢ / (1 + markupᵢ/100)               (наценка% = маржа/себест.×100)
profit           = revenue − Σ costᵢ                          (маржа = выручка − себестоимость)
markupPercent    = 100 × revenue / Σ costᵢ − 100              (наценка, взвешенная по себестоимости)
loyaltyWriteoffs = revenue × 0.05                             (плановое списание баллов = 5% выручки)
```

Крепкий алкоголь по умолчанию 0: у бара без него кухня, выручки и прибыль считаются как до
2026-11-03. Пример Лиговского: выручка 1 000 000 ₽, розлив 50%, фасовка 25%, крепкий 3% →
кухня (авто) 22%, `revenueStrong` 30 000 ₽; при наценке крепкого 300% его себестоимость
30 000 / 4 = 7 500 ₽ входит в Σ costᵢ.

`loyaltyWriteoffs` — плановое допущение (5% выручки, константа `LOYALTY_WRITEOFF_RATE`), а не повтор
факта: факт `loyalty_points_written_off` = фактическая сумма скидок из OLAP.

Важно: `markupPercent` взвешивается по **себестоимости** (как факт `avg_markup`), а не по доле
выручки. Прежняя формула (средневзвешенная по долям) давала систематическое расхождение с фактом.

> Поля авто-расчёта в модалке доступны только для чтения (`readonly`, бейдж «авто»). При открытии
> существующего плана они пересчитываются из введённых метрик — то есть пере-сохранение старого плана
> приведёт его производные поля к согласованным значениям.

### Модальное окно редактирования

**5 секций** (поля с пометкой «авто» — только для чтения):
1. Основные показатели — выручка, средний чек *(ввод)*; чеки, прибыль *(авто)*
2. Доли категорий (%) — розлив, фасовка, крепкий алкоголь *(ввод, крепкий по умолчанию 0)*; кухня *(авто)*
3. Выручка по категориям — розлив, фасовка, кухня, крепкий алкоголь *(авто)*
4. Наценки (%) — розлив, фасовка, кухня, крепкий алкоголь *(ввод)*; общая *(авто)*
5. Прочее — доля чеков с картой, активность кранов *(ввод)*; списания баллов *(авто, 5% выручки)*

**Валидация:** розлив + фасовка + крепкий алкоголь не должны превышать 100% (иначе доле кухни не
из чего взяться); сумма четырёх долей 100 ± 1 (бэкенд: `PlansManager.SHARE_FIELDS`); доля
крепкого больше 0 требует наценку крепкого больше 0 («Укажите наценку крепкого алкоголя»: иначе
прибыль плана посчиталась бы, будто крепкий продаётся по себестоимости); все значения
неотрицательны. В таблице плана поля крепкого со значением 0 показываются «—» (план не задан).

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

### 2026-11-09 — Лиговский и Варшавская: 24 крана

**Что сделано:** `VENUES['ligovskiy']['taps']` и `VENUES['varshavskaya']['taps']` — 24
(было 12); `VENUES['all']['taps']` больше не число руками (было 60), а сумма по
`PHYSICAL_VENUES` — 84. `/api/venues` отдаёт поле `taps`.
**Почему:** в барах поставили новые краны (решение владельца).
**Файлы:** `core/venues_config.py`, `core/venues_manager.py`.
**Если сломать:** число кранов расходится с `core/taps_manager.BARS_CONFIG` — справка
MCP `common_bars_reference` пишет о расхождении, тест `tests/test_mcp_protocol.py` падает.

### 2026-11-03 — План крепкого алкоголя

**Что сделано:** в план месяца добавлены необязательные поля группы «Крепкий алкоголь» —
`strongShare`, `revenueStrong`, `markupStrong` (`PLAN_SCHEMA`, `PLAN_DEFAULTS` = 0 = «план не
задан»). Сумма долей проверяется с крепким (`SHARE_FIELDS`: розлив + фасовка + кухня + крепкий
= 100 ± 1), доля крепкого ≤ 100. План периода: `revenueStrong` складывается, `strongShare`
усредняется с нулями, `markupStrong` — только по планам, где она задана. Форма: доля и наценка
крепкого вводятся, выручка — авто, кухня = 100 − розлив − фасовка − крепкий; доля крепкого
без наценки не сохраняется. Выгрузка планов xlsx получила три колонки.
**Зачем:** на Лиговском с 09.10.2026 продаётся крепкий алкоголь; на дашборде он стал отдельной
группой карточек ([dashboard.md](dashboard.md)), и владелец попросил план для неё.
**Файлы:** `core/plans_manager.py`, `routes/dashboard.py` (выгрузка планов),
`templates/dashboard/plans_tab.html`, `static/js/dashboard/modules/plans.js`,
`core/mcp/tools/analytics.py` (`analytics_plan_save`, `_get`, `_calculate`); тесты
`tests/test_dashboard_strong_alcohol.py`, `tests/test_plans_defaults.py`,
`tests/test_plans_form.mjs`.
**Что сломается при неверной правке:** если `markupStrong` усреднять с нулями, план наценки
крепкого по сети упадёт вчетверо; если долю крепкого не вычитать из кухни, план Лиговского
с крепким не пройдёт проверку суммы долей.

### 2026-11-01 — Форма плана: годы из правила, месяц и бар из общего выбора

**Что сделано:** в форме плана (вкладка «Планы» дашборда) список годов строит `plans.js`
(`planYears`: текущий год −1…+1 по часам сервера, год общего периода, годы заведённых планов
из `/api/plans`) вместо зашитых в шаблоне 2025–2027; месяц и год по умолчанию — месяц общего
периода (`state.currentMonth` / `currentYear`), а не часы устройства; заведение — общий бар, при
«Все бары» — первый бар списка (`planFormDefaults`).
**Зачем:** план единого виджета, этап 3 — с 2028 года год плана было бы не выбрать, а месяц
формы расходился с месяцем, выбранным в полосе.
**Файлы:** `templates/dashboard/plans_tab.html`, `static/js/dashboard/modules/plans.js`,
`tests/test_plans_form.mjs`.

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
