# Widget Revenue Baseline — для сверки

Дата фиксации: 2026-03-27
Период: 2026-03-01 — 2026-03-27

## Текущие данные (5 отдельных OLAP запросов) — ЗАФИКСИРОВАНО

Из локального теста (один бар успешно):
```json
[
  {
    "bar": "ligovskiy",
    "name": "Лиговский",
    "revenue": 858721.0,
    "plan": 895440.0,
    "completion": 95.9
  }
]
```

Остальные бары таймаутили (iiko API нестабилен).

## Ожидаемые данные после оптимизации (1 OLAP запрос)

После изменения логики данные должны **совпадать** с baseline:
- Лиговский: ~95.9% (выручка=858721, план=895440)
- Остальные бары: согласно данным iiko

## Текущая логика (5 OLAP запросов)

```python
# В widget_revenue() — цикл по 5 барам
for bar_key, bar_name in bars:
    # 1. Подключение к iiko
    olap = OlapReports()
    olap.connect()

    # 2. OLAP запрос на каждый бар отдельно
    date_to_inclusive = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    all_sales_data = olap.get_all_sales_report(date_from, date_to_inclusive, iiko_bar_name)

    # 3. Локальный расчёт метрик
    calculator = DashboardMetrics()
    metrics = calculator.calculate_metrics(all_sales_data)

    # 4. Маппинг полей
    frontend_mapping = {...}
    mapped = {}
    for old_key, new_key in frontend_mapping.items():
        if old_key in metrics:
            value = metrics[old_key]
            if new_key in ['markupPercent', ...]:
                value = value * 100
            mapped[new_key] = value

    actual_revenue = mapped.get('revenue', 0)

    # 5. План из plansdashboard.json
    month_key = f"{bar_key if bar_key else 'all'}_{month_start.strftime('%Y-%m')}"
    with open('data/plansdashboard.json', 'r', encoding='utf-8') as f:
        plans_data = json.load(f)
    plans = plans_data.get('plans', {})
    month_plan = plans.get(month_key, {})
    plan_revenue = month_plan.get('revenue', 0.0)

    # 6. % выполнения
    completion = (actual_revenue / plan_revenue * 100) if plan_revenue > 0 else 0

    results.append({
        'bar': bar_key,
        'name': bar_name,
        'completion': round(completion, 1)
    })

    olap.disconnect()
```

## Проблемы текущей реализации

1. **5 подключений к iiko API** — каждое подключение = авторизация + получение токена
2. **5 OLAP запросов** — каждый запрос 2-5 секунд
3. **Таймауты** — некоторые бары не отвечают
4. **Нет кэширования между барами** — каждый бар запрашивается заново

## Ожидаемая оптимизация (1 OLAP запрос)

```python
# ОДИН запрос с группировкой по VenueName
olap = OlapReports()
olap.connect()

# Группировка по VenueName
all_sales_data = olap.get_all_sales_report(date_from, date_to_inclusive, None)  # Все бары сразу

# В ответе придут данные с полем VenueName для группировки
# Нужно сгруппировать и посчитать метрики по каждому бару
```

## План для сверки после оптимизации

После изменения логики проверить:
- [ ] % выполнения по каждому бару совпадает с baseline
- [ ] Общая сумма = сумма по всем барам
- [ ] Запрос выполняется в 3-5 раз быстрее
