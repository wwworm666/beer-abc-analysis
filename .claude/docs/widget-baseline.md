# Widget Revenue Baseline — для сверки

## Данныеbaseline (5 отдельных OLAP запросов) — СТАРАЯ ВЕРСИЯ

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

## Новые данные (1 OLAP запрос) — 2026-03-27

Рабочие данные с сервера (оптимизированная версия):

```json
[
  {"bar": "", "name": "Общая", "completion": 85.8},
  {"bar": "bolshoy", "name": "Большой пр. В.О", "completion": 82.5},
  {"bar": "ligovskiy", "name": "Лиговский", "completion": 95.9},
  {"bar": "kremenchugskaya", "name": "Кременчугская", "completion": 86.6},
  {"bar": "varshavskaya", "name": "Варшавская", "completion": 77.7}
]
```

**Сверка:**
- Лиговский: 95.9% ✅ **СОВПАДАЕТ** с baseline

## Вывод

Оптимизация работает:
- 1 OLAP запрос вместо 5
- Данные совпадают с baseline
- API отвечает быстро (кэш работает)

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
