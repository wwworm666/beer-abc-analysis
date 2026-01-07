"""
Graph schema context for LLM.
Provides schema description and examples for Cypher generation.
"""

GRAPH_SCHEMA = """
# Neo4j Graph Schema - Beer Sales Analytics

## Nodes (Узлы)

### Beer (Пиво)
- name: string - Название пива, например "ФестХаус Хеллес (0,5)"

### BeerStyle (Стиль пива)
- name: string - Стиль, например "Хели (Р)", "ИПА (Р)", "Вайсс (Р)"

### Category (Категория)
- name: string - "draft" или "bottles"
- label: string - "Разливное" или "Фасовка"

### Bar (Бар)
- name: string - Название бара: "Большой пр. В.О", "Кременчугская", "Краснопутиловская", "Гражданка"

### Sale (Продажа)
- id: string - Уникальный ID
- dish_name: string - Название позиции
- quantity: float - Количество
- revenue: float - Выручка в рублях
- cost: float - Себестоимость
- margin: float - Маржа (прибыль)
- markup: float - Наценка %
- discount: float - Скидка
- category: string - "draft" (розлив) или "bottles" (фасовка)
- date: string - Дата YYYY-MM-DD

### Period (Период/Дата)
- id: string - Дата YYYY-MM-DD
- date: string - Дата

### Waiter (Официант)
- name: string - Имя официанта

## Relationships (Связи)

### Основные связи
- (Sale)-[:OF_BEER]->(Beer) - Продажа пива
- (Sale)-[:SOLD_AT]->(Bar) - Продажа в баре
- (Sale)-[:ON_DATE]->(Period) - Дата продажи
- (Sale)-[:SERVED_BY]->(Waiter) - Официант обслужил
- (Beer)-[:HAS_STYLE]->(BeerStyle) - Пиво имеет стиль
- (Beer)-[:OF_CATEGORY]->(Category) - Пиво относится к категории

### ANALYZED_IN - ABC/XYZ анализ пива по барам
- (Beer)-[r:ANALYZED_IN]->(Bar) - Аналитика пива в конкретном баре
- r.abc_revenue: string - ABC по выручке (A/B/C)
- r.abc_markup: string - ABC по наценке (A/B/C)
- r.abc_margin: string - ABC по марже (A/B/C)
- r.abc_combined: string - Комбинация 3 букв, например "AAA", "ABA", "CCC"
- r.xyz_category: string - XYZ категория (X=стабильный, Y=средний, Z=нестабильный)
- r.cv_percent: float - Коэффициент вариации в %
- r.total_revenue: float - Общая выручка пива в баре
- r.total_margin: float - Общая маржа
- r.total_qty: float - Общее количество продаж

## ABC Analysis (ABC анализ)
- 1-я буква (Revenue): A=80% выручки, B=следующие 15%, C=последние 5%
- 2-я буква (Markup): A≥120%, B=100-120%, C<100%
- 3-я буква (Margin): A=80% маржи, B=следующие 15%, C=последние 5%
- "AAA" = топ по всем метрикам, "CCC" = аутсайдер

## XYZ Analysis (XYZ анализ)
- X: CV < 10% - стабильный спрос
- Y: CV 10-25% - средняя вариация
- Z: CV > 25% - нестабильный спрос

## Important Notes

1. Выручка хранится в поле `revenue`, маржа в `margin`
2. Для топов используй SUM(s.revenue) или SUM(s.quantity)
3. Категория "draft" = разливное пиво, "bottles" = бутылочное/баночное
4. Даты в формате YYYY-MM-DD
5. ABC/XYZ метрики на связи ANALYZED_IN между Beer и Bar
6. Для вопросов про ABC/XYZ используй ANALYZED_IN связь
"""

EXAMPLE_QUERIES = """
# Example Cypher Queries

## Топ пива по выручке
```cypher
MATCH (s:Sale)-[:OF_BEER]->(b:Beer)
RETURN b.name, sum(s.revenue) as revenue
ORDER BY revenue DESC
LIMIT 10
```

## Топ пива по выручке в конкретном баре
```cypher
MATCH (s:Sale)-[:OF_BEER]->(b:Beer)
MATCH (s)-[:SOLD_AT]->(bar:Bar {name: "Бар Культура 1"})
RETURN b.name, sum(s.revenue) as revenue
ORDER BY revenue DESC
LIMIT 10
```

## Выручка по стилям пива
```cypher
MATCH (s:Sale)-[:OF_BEER]->(b:Beer)-[:HAS_STYLE]->(st:BeerStyle)
RETURN st.name, sum(s.revenue) as revenue
ORDER BY revenue DESC
```

## Продажи по барам
```cypher
MATCH (s:Sale)-[:SOLD_AT]->(bar:Bar)
RETURN bar.name, sum(s.revenue) as revenue, count(s) as sales_count
ORDER BY revenue DESC
```

## Продажи за конкретную дату
```cypher
MATCH (s:Sale)-[:ON_DATE]->(p:Period {id: "2025-12-25"})
MATCH (s)-[:OF_BEER]->(b:Beer)
RETURN b.name, sum(s.revenue) as revenue
ORDER BY revenue DESC
```

## Топ официантов по выручке
```cypher
MATCH (s:Sale)-[:SERVED_BY]->(w:Waiter)
RETURN w.name, sum(s.revenue) as revenue, count(s) as sales_count
ORDER BY revenue DESC
```

## Только разливное пиво
```cypher
MATCH (s:Sale {category: "draft"})-[:OF_BEER]->(b:Beer)
RETURN b.name, sum(s.revenue) as revenue
ORDER BY revenue DESC
LIMIT 10
```

## Сравнение баров по марже
```cypher
MATCH (s:Sale)-[:SOLD_AT]->(bar:Bar)
RETURN bar.name, sum(s.margin) as margin, sum(s.revenue) as revenue
ORDER BY margin DESC
```

## Средний чек по барам
```cypher
MATCH (s:Sale)-[:SOLD_AT]->(bar:Bar)
RETURN bar.name, avg(s.revenue) as avg_check
ORDER BY avg_check DESC
```

## Поиск пива по названию (частичное совпадение)
```cypher
MATCH (b:Beer)
WHERE b.name CONTAINS "IPA" OR b.name CONTAINS "ИПА"
MATCH (s:Sale)-[:OF_BEER]->(b)
RETURN b.name, sum(s.revenue) as revenue
ORDER BY revenue DESC
```

## ABC Analysis - Топ пиво (AAA категория)
```cypher
MATCH (b:Beer)-[r:ANALYZED_IN]->(bar:Bar)
WHERE r.abc_combined = "AAA"
RETURN b.name, bar.name, r.total_revenue, r.abc_combined
ORDER BY r.total_revenue DESC
LIMIT 10
```

## ABC Analysis - Аутсайдеры (CCC категория)
```cypher
MATCH (b:Beer)-[r:ANALYZED_IN]->(bar:Bar)
WHERE r.abc_combined = "CCC"
RETURN b.name, bar.name, r.total_revenue, r.abc_combined
ORDER BY r.total_revenue ASC
LIMIT 10
```

## ABC Analysis - Пиво с высокой наценкой но низкой выручкой (CAx)
```cypher
MATCH (b:Beer)-[r:ANALYZED_IN]->(bar:Bar)
WHERE r.abc_revenue = "C" AND r.abc_markup = "A"
RETURN b.name, bar.name, r.abc_combined, r.markup_percent
ORDER BY r.markup_percent DESC
```

## XYZ Analysis - Стабильный спрос (X)
```cypher
MATCH (b:Beer)-[r:ANALYZED_IN]->(bar:Bar)
WHERE r.xyz_category = "X"
RETURN b.name, bar.name, r.xyz_category, r.cv_percent
ORDER BY r.cv_percent ASC
LIMIT 10
```

## XYZ Analysis - Нестабильный спрос (Z)
```cypher
MATCH (b:Beer)-[r:ANALYZED_IN]->(bar:Bar)
WHERE r.xyz_category = "Z"
RETURN b.name, bar.name, r.xyz_category, r.cv_percent
ORDER BY r.cv_percent DESC
LIMIT 10
```

## ABC + XYZ комбинация - Лучшие стабильные товары (AAA + X)
```cypher
MATCH (b:Beer)-[r:ANALYZED_IN]->(bar:Bar)
WHERE r.abc_combined = "AAA" AND r.xyz_category = "X"
RETURN b.name, bar.name, r.abc_combined, r.xyz_category, r.total_revenue
ORDER BY r.total_revenue DESC
```

## Статистика ABC по барам
```cypher
MATCH (b:Beer)-[r:ANALYZED_IN]->(bar:Bar)
RETURN bar.name, r.abc_combined, count(*) as count
ORDER BY bar.name, count DESC
```

## Разливное пиво (draft)
```cypher
MATCH (b:Beer)-[:OF_CATEGORY]->(c:Category {name: "draft"})
MATCH (s:Sale)-[:OF_BEER]->(b)
RETURN b.name, sum(s.revenue) as revenue
ORDER BY revenue DESC
LIMIT 10
```

## Фасовка (bottles)
```cypher
MATCH (b:Beer)-[:OF_CATEGORY]->(c:Category {name: "bottles"})
MATCH (s:Sale)-[:OF_BEER]->(b)
RETURN b.name, sum(s.revenue) as revenue
ORDER BY revenue DESC
LIMIT 10
```
"""


def get_full_context() -> str:
    """Get full schema context for LLM."""
    return f"{GRAPH_SCHEMA}\n\n{EXAMPLE_QUERIES}"


def get_schema_only() -> str:
    """Get only schema without examples."""
    return GRAPH_SCHEMA
