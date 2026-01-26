# Дашборд План/Факт

## Что это

Главный экран для управленца. Выбираешь неделю, выбираешь бар — видишь план vs факт по 15 метрикам. Красное — плохо, зелёное — хорошо. Есть AI-анализ от Gemini, который пишет человеческим языком: "Выручка упала на 12%, потому что..."

## Файлы

```
dashboardNovaev/
├── dashboard_analysis.py     ← Расчёт 15 метрик
├── plans_manager.py          ← CRUD для планов (JSON)
├── weeks_generator.py        ← Генератор недель (Пн-Вс)
└── backend/
    ├── venues_config.py      ← Конфиг 4 баров
    ├── venues_manager.py     ← Агрегация по барам
    ├── comparison_calculator.py  ← Сравнение периодов
    └── trends_analyzer.py    ← Анализ трендов

templates/dashboard/
├── base.html                 ← Основной layout
├── analytics_tab.html        ← Таб "Аналитика"
├── plans_tab.html            ← Таб "Планы"
└── components/               ← Карточки метрик

data/
└── plansdashboard.json       ← Хранилище планов
```

## Как работает

### 15 Метрик дашборда

```python
# dashboard_analysis.py → DashboardMetrics.calculate_metrics()

metrics = {
    'total_revenue': 1_500_000,     # Общая выручка
    'total_checks': 3245,           # Количество чеков
    'avg_check': 462.19,            # Средний чек

    'draft_share': 45.5,            # % разливного
    'bottles_share': 35.2,          # % фасовки
    'kitchen_share': 19.3,          # % кухни

    'avg_markup': 215.5,            # Средняя наценка %
    'total_margin': 950_000,        # Прибыль (маржа)

    'tap_activity': 75.5,           # % активных кранов
}
```

### Поток данных

```
Frontend: выбрал "Большой" + "01.01-07.01"
    │
    ▼
POST /api/dashboard-analytics
{bar: "bolshoy", date_from: "2026-01-01", date_to: "2026-01-07"}
    │
    ▼
VenuesManager: "bolshoy" → "Большой пр. В.О" (для iiko)
    │
    ▼
iiko OLAP: 3 параллельных запроса
  - get_draft_sales_report()    → разливное
  - get_beer_sales_report()     → фасовка
  - get_kitchen_sales_report()  → кухня
    │
    ▼
DashboardMetrics.calculate_metrics()
  - суммирует выручку по категориям
  - считает доли (% от общей)
  - считает наценку (взвешенную по себестоимости)
  - считает маржу (выручка - себестоимость)
    │
    ▼
JSON → Frontend отрисовывает карточки
```

### Маппинг баров

```python
# venues_config.py
KEY_TO_IIKO_NAME = {
    'bolshoy': 'Большой пр. В.О',
    'ligovskiy': 'Лиговский',
    'kremenchugskaya': 'Кременчугская',
    'varshavskaya': 'Варшавская',
}
```

### Планы

Планы хранятся в `data/plansdashboard.json`:

```json
{
  "plans": {
    "2026-01-01_2026-01-07": {
      "revenue": 1500000,
      "checks": 3500,
      "averageCheck": 428,
      "draftShare": 45,
      "packagedShare": 35,
      "kitchenShare": 20,
      ...
    }
  }
}
```

PlansManager делает backup перед каждым изменением и валидирует данные (сумма долей ≈ 100%).

### AI-анализ

```python
# app.py → /api/analyze-with-ai
prompt = f"""
Проанализируй показатели бара за неделю:
- Выручка: {revenue} (план: {plan_revenue})
- Средний чек: {avg_check}
...
Напиши 3-4 предложения с выводами.
"""
response = gemini_model.generate_content(prompt)
```

Кэшируется на 1 час (AI_ANALYSIS_CACHE).

## Changelog

- 2026-01-26: Полностью переписан согласно CLAUDE.md
- 2026-01-25: Создан placeholder
