# Knowledge Graph - GraphRAG для Культуры

Модуль Knowledge Graph реализует GraphRAG (Graph Retrieval-Augmented Generation) систему для аналитики пивных баров сети "Культура".

## Архитектура

```
knowledge_graph/
├── api/                    # REST API endpoints
│   └── routes.py           # Flask Blueprint с /api/chat/ask
├── engine/                 # RAG движок
│   ├── rag.py              # GraphRAG - NL → Cypher → Answer
│   └── schema_context.py   # Схема графа для LLM
├── etl/                    # Extract-Transform-Load
│   ├── sales_loader.py     # Загрузка продаж из iiko OLAP
│   ├── abc_xyz_loader.py   # Расчёт ABC/XYZ метрик
│   └── loader.py           # Базовый loader
├── llm/                    # LLM провайдеры
│   ├── base.py             # Абстрактный интерфейс
│   └── gemini.py           # Google Gemini провайдер
├── models/                 # Pydantic модели
│   ├── nodes.py            # Beer, Sale, Bar, Waiter...
│   └── relationships.py    # SOLD_AT, OF_BEER...
├── chat_server.py          # Standalone веб-интерфейс
├── config.py               # Конфигурация из .env
├── db.py                   # Neo4j connection pool
├── load_workshifts.py      # Загрузка рабочих смен
└── GRAPH_SCHEMA.md         # Документация схемы
```

## Быстрый старт

### 1. Переменные окружения

Добавить в `.env`:

```env
# Neo4j
NEO4J_URI=bolt://95.81.123.157:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j

# Gemini (для GraphRAG)
GEMINI_API_KEY=your_gemini_api_key
```

### 2. Запуск веб-интерфейса

```bash
python -m knowledge_graph.chat_server
```

Откроется на http://localhost:5001

### 3. Загрузка данных

```bash
# Синхронизация продаж и смен за последние 7 дней
python scripts/daily_sync.py 7

# Только смены за период
python knowledge_graph/load_workshifts.py 2025-12-01 2025-12-31
```

## GraphRAG Pipeline

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Вопрос (NL)   │────►│  Gemini LLM     │────►│  Cypher Query   │
│                 │     │  + Schema       │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Ответ (NL)    │◄────│  Gemini LLM     │◄────│   Neo4j         │
│                 │     │  Format         │     │   Results       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**Пример:**
- Вопрос: "Топ-5 пива по выручке"
- Cypher: `MATCH (s:Sale)-[:OF_BEER]->(b:Beer) RETURN b.name, sum(s.revenue) ORDER BY sum(s.revenue) DESC LIMIT 5`
- Ответ: "Топ-5 пива: 1. ФестХаус Хеллес — 45,230₽..."

## API

### POST /api/chat/ask

```bash
curl -X POST http://localhost:5001/api/chat/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Какой бар продаёт больше всего?"}'
```

**Response:**
```json
{
  "success": true,
  "question": "Какой бар продаёт больше всего?",
  "answer": "Бар 'Культура на Маросейке' лидирует с выручкой 234,500₽",
  "cypher": "MATCH (s:Sale)-[:SOLD_AT]->(b:Bar) RETURN b.name, sum(s.revenue)...",
  "results": [...]
}
```

## Схема графа

Подробная документация: [GRAPH_SCHEMA.md](GRAPH_SCHEMA.md)

### Основные узлы

| Узел | Описание |
|------|----------|
| Beer | Пиво (название, стиль) |
| Sale | Факт продажи (выручка, маржа, дата) |
| Bar | Заведение |
| Waiter | Официант |
| WorkShift | Рабочая смена |
| Period | Дата (день, неделя, месяц) |

### Ключевые связи

- `Sale -[:OF_BEER]-> Beer` — какое пиво продано
- `Sale -[:SOLD_AT]-> Bar` — в каком баре
- `Sale -[:SERVED_BY]-> Waiter` — кто обслужил
- `Beer -[:ANALYZED_IN]-> Bar` — ABC/XYZ метрики
- `Waiter -[:WORKED_SHIFT]-> WorkShift` — смены

## ETL Pipeline

### Ежедневная синхронизация

Windows Task Scheduler запускает `scripts/daily_sync.bat` в 06:00:

1. Загрузка продаж из iiko OLAP API
2. Загрузка рабочих смен из iiko Attendance API
3. Расчёт ABC/XYZ метрик
4. Создание/обновление узлов и связей в Neo4j

### Ручная загрузка

```python
from knowledge_graph.etl.sales_loader import SalesDataLoader

loader = SalesDataLoader()
result = loader.load_sales("2025-12-01", "2025-12-31")
print(f"Загружено: {result['sales']} продаж, {result['beers']} пива")
```

## Разработка

### Тестирование подключения

```bash
python knowledge_graph/test_connection.py
```

### Добавление нового LLM провайдера

```python
# knowledge_graph/llm/my_provider.py
from knowledge_graph.llm.base import BaseLLMProvider

class MyProvider(BaseLLMProvider):
    def generate_cypher(self, question, schema, examples):
        # ...

    def format_response(self, question, results, cypher):
        # ...
```

## Зависимости

```
neo4j>=5.0
google-generativeai
flask
python-dotenv
```

## Neo4j Browser

Прямой доступ к графу: http://95.81.123.157:7474

---

*Часть проекта beer-abc-analysis*
