# Knowledge Graph Schema - Культура

Документация структуры графа Neo4j для аналитики пивных баров.

**Neo4j Browser:** http://95.81.123.157:7474

---

## Узлы (Nodes)

| Узел | Описание | Свойства | Количество |
|------|----------|----------|------------|
| **Beer** | Пиво (фасовка) | `name`: название, напр. "ФестХаус Хеллес (0,5)" | 629 |
| **BeerStyle** | Стиль пива | `name`: стиль, напр. "Хели (Р)", "ИПА (Р)" | 45 |
| **Category** | Категория товара | `name`: "draft" или "bottles"<br>`label`: "Разливное" или "Фасовка" | 2 |
| **Bar** | Бар/заведение | `name`: название бара | 4 |
| **Sale** | Факт продажи | `revenue`, `margin`, `cost`, `quantity`, `category`, `date` | 3309 |
| **Period** | Дата | `date`, `year`, `month`, `week`, `day_of_week`, `month_name` | 30 |
| **Week** | Неделя | `id`: "2025-W49", `year`, `week` | 5 |
| **Month** | Месяц | `id`: "2025-12", `year`, `month`, `name` | 2 |
| **Waiter** | Официант | `name`: имя | 10 |
| **WorkShift** | Рабочая смена | `shift_id`, `date`, `start_time`, `end_time`, `duration_minutes` | — |

---

## Связи (Relationships)

| Связь | От → К | Описание | Свойства |
|-------|--------|----------|----------|
| **OF_BEER** | Sale → Beer | Какое пиво продано | — |
| **SOLD_AT** | Sale → Bar | В каком баре продано | — |
| **ON_DATE** | Sale → Period | Когда продано | — |
| **SERVED_BY** | Sale → Waiter | Кто обслужил | — |
| **HAS_STYLE** | Beer → BeerStyle | Стиль пива | — |
| **OF_CATEGORY** | Beer → Category | Разлив или фасовка | — |
| **ANALYZED_IN** | Beer → Bar | ABC/XYZ анализ | см. ниже |
| **IN_WEEK** | Period → Week | День входит в неделю | — |
| **IN_MONTH** | Period → Month | День входит в месяц | — |
| **IN_MONTH** | Week → Month | Неделя входит в месяц | — |
| **WORKED_SHIFT** | Waiter → WorkShift | Сотрудник работал смену | — |
| **AT_BAR** | WorkShift → Bar | Смена в баре | — |

---

## Узел WorkShift (Рабочая смена)

Данные загружаются из iiko API явок (`/resto/api/employees/attendance`).

| Свойство | Тип | Описание |
|----------|-----|----------|
| `shift_id` | string | UUID явки из iiko |
| `date` | string | Дата смены (YYYY-MM-DD) |
| `start_time` | string | Время начала (HH:MM) |
| `end_time` | string | Время окончания (HH:MM) |
| `duration_minutes` | int | Продолжительность в минутах |

**Загрузка данных:**
```bash
python knowledge_graph/load_workshifts.py 2025-12-01 2025-12-31
```

---

## Связь ANALYZED_IN (ABC/XYZ метрики)

Эта связь содержит рассчитанные метрики для каждой пары Пиво-Бар.

| Свойство | Тип | Описание |
|----------|-----|----------|
| `abc_revenue` | string | ABC по выручке: A, B или C |
| `abc_markup` | string | ABC по наценке: A, B или C |
| `abc_margin` | string | ABC по марже: A, B или C |
| `abc_combined` | string | Комбинация 3 букв: "AAA", "ABA", "CCC" и т.д. |
| `xyz_category` | string | XYZ категория: X, Y или Z |
| `cv_percent` | float | Коэффициент вариации в % |
| `total_revenue` | float | Общая выручка пива в этом баре |
| `total_margin` | float | Общая маржа |
| `total_qty` | float | Общее количество продаж |
| `markup_percent` | float | Средняя наценка в % |

---

## ABC Анализ

**3 буквы = 3 метрики:**

| Буква | Метрика | A | B | C |
|-------|---------|---|---|---|
| 1-я | Выручка | Топ 80% | Следующие 15% | Последние 5% |
| 2-я | Наценка | ≥120% | 100-120% | <100% |
| 3-я | Маржа | Топ 80% | Следующие 15% | Последние 5% |

**Примеры комбинаций:**
- `AAA` — топ по всем метрикам (лидер)
- `ACA` — высокая выручка, низкая наценка, высокая маржа
- `CCC` — аутсайдер по всем метрикам

---

## XYZ Анализ

Стабильность спроса на основе коэффициента вариации (CV):

| Категория | CV | Описание |
|-----------|-----|----------|
| **X** | < 10% | Стабильный спрос |
| **Y** | 10-25% | Средняя вариация |
| **Z** | > 25% | Нестабильный спрос |

---

## Визуальная схема

```
                    ┌─────────────┐
                    │  Category   │
                    │ draft/bottles│
                    └──────▲──────┘
                           │ OF_CATEGORY
                           │
┌─────────────┐      ┌─────┴─────┐      ┌─────────────┐
│  BeerStyle  │◄─────│   Beer    │─────►│    Bar      │
│             │      │           │      │             │
│ HAS_STYLE   │      └─────┬─────┘      └──────▲──────┘
└─────────────┘            │                   │
                           │              ANALYZED_IN
                      OF_BEER            (abc_combined,
                           │              xyz_category,
                           ▼              total_revenue)
                    ┌─────────────┐            │
    ┌───────────────│    Sale     │────────────┘
    │               │             │
    │               └──────┬──────┘
    │                      │
    │ SERVED_BY      ON_DATE│SOLD_AT
    │                      │
    ▼                      ▼
┌─────────┐         ┌─────────────┐
│ Waiter  │         │   Period    │
└─────────┘         │ date, week  │
                    │ month, year │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │ IN_WEEK    │ IN_MONTH   │
              ▼            │            ▼
       ┌───────────┐       │     ┌───────────┐
       │   Week    │       │     │   Month   │
       │ 2025-W49  │───────┘     │ Декабрь   │
       └───────────┘ IN_MONTH    └───────────┘
```

---

## Полезные Cypher запросы

### Топ-10 пива по выручке
```cypher
MATCH (s:Sale)-[:OF_BEER]->(b:Beer)
RETURN b.name, sum(s.revenue) as revenue
ORDER BY revenue DESC
LIMIT 10
```

### Все AAA пиво
```cypher
MATCH (b:Beer)-[r:ANALYZED_IN]->(bar:Bar)
WHERE r.abc_combined = "AAA"
RETURN b.name, bar.name, r.total_revenue
ORDER BY r.total_revenue DESC
```

### Стабильное пиво (XYZ = X)
```cypher
MATCH (b:Beer)-[r:ANALYZED_IN]->(bar:Bar)
WHERE r.xyz_category = "X"
RETURN b.name, bar.name, r.cv_percent
ORDER BY r.cv_percent ASC
LIMIT 10
```

### Разливное пиво
```cypher
MATCH (b:Beer)-[:OF_CATEGORY]->(c:Category {name: "draft"})
RETURN b.name
```

### Пиво конкретного стиля
```cypher
MATCH (b:Beer)-[:HAS_STYLE]->(s:BeerStyle)
WHERE s.name CONTAINS "ИПА"
RETURN b.name, s.name
```

### Выручка по неделям
```cypher
MATCH (s:Sale)-[:ON_DATE]->(p:Period)-[:IN_WEEK]->(w:Week)
RETURN w.id as week, sum(s.revenue) as revenue
ORDER BY week
```

### Выручка по месяцам
```cypher
MATCH (s:Sale)-[:ON_DATE]->(p:Period)-[:IN_MONTH]->(m:Month)
RETURN m.name as month, sum(s.revenue) as revenue
ORDER BY m.month
```

### Продажи за конкретную неделю
```cypher
MATCH (s:Sale)-[:ON_DATE]->(p:Period)-[:IN_WEEK]->(w:Week {week: 49})
MATCH (s)-[:OF_BEER]->(b:Beer)
RETURN b.name, sum(s.revenue) as revenue
ORDER BY revenue DESC
LIMIT 10
```

### Смены сотрудника за период
```cypher
MATCH (w:Waiter {name: "Иван"})-[:WORKED_SHIFT]->(ws:WorkShift)
WHERE ws.date >= "2025-12-01" AND ws.date <= "2025-12-31"
RETURN ws.date, ws.start_time, ws.end_time, ws.duration_minutes
ORDER BY ws.date
```

### Общее время работы сотрудников
```cypher
MATCH (w:Waiter)-[:WORKED_SHIFT]->(ws:WorkShift)
RETURN w.name,
       count(ws) as shifts,
       sum(ws.duration_minutes) as total_minutes,
       round(sum(ws.duration_minutes) / 60.0, 1) as total_hours
ORDER BY total_hours DESC
```

### Смены по барам
```cypher
MATCH (ws:WorkShift)-[:AT_BAR]->(b:Bar)
RETURN b.name, count(ws) as shifts, sum(ws.duration_minutes) as total_minutes
ORDER BY total_minutes DESC
```

---

## Статистика графа

| Метрика | Значение |
|---------|----------|
| Всего узлов | ~4036 |
| Всего связей | ~8570 |
| Beer | 629 |
| Sale | 3309 |
| Period | 30 |
| Week | 5 |
| Month | 2 |
| ABC комбинаций | 940 |
| AAA позиций | 167 |
| CCC позиций | 73 |
| XYZ = X | 148 |
| XYZ = Z | 761 |

---

*Последнее обновление: 2026-01-07*
