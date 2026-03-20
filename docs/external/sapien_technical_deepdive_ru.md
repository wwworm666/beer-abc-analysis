# Sapien AI: Технический deep-dive в архитектуру enterprise финансового AI

Sapien AI (sapien.ai/getsapien.com) разработала принципиально новый подход к enterprise финансовому AI, который фундаментально отличается от типичных LLM-систем. Их архитектура минимизирует риск галлюцинаций, **используя LLM только для понимания контекста и маршрутизации**, при этом все вычисления ограничены верифицируемыми, детерминистическими инструментами. Компания привлекла $8.7M seed-инвестиций под руководством General Catalyst в октябре 2024, чтобы построить то, что они называют "автономными коллегами" для CFO.

Ключевая техническая инновация сосредоточена на изучении company-specific представлений — embedding моделей, которые понимают, как работает компания через разрозненные источники данных. Как описывает их инженерная команда: 

> *"We seek to learn the representation of a company: building the embedding model for company financials that harnesses massive amounts of data across distinct, siloed sources to understand how they operate."*

Этот подход решает то, что они определяют как фундаментальный пробел в современном AI: неспособность глубоко понимать организационный контекст.

---

## Представление компании через иерархическую контекстуализацию

Самая амбициозная техническая цель Sapien — построение того, что они называют "представлением компании" (company representation) — системы эмбеддингов, которая захватывает не просто данные, но организационный контекст за каждой цифрой. Это решает проблему, сформулированную в их техническом блоге: 

> *"how can you make capital allocation decisions, synthesize models, or really do any form of analysis for a company if the deep context behind how the company operates is missing?"*

Архитектура обрабатывает данные через **пятиэтапный пайплайн**:

1. **Прямая API-интеграция** в источники данных (загруженные файлы или API-подключения)
2. **Локализация атомарных единиц** каждой таблицы или специфического data route
3. **Контекстуальные и иерархические вычисления** вокруг и внутри каждой единицы
4. **Построение эмбеддингов** используя как содержимое, так и окружающий контекст
5. **Вставка в knowledge graph** полностью обработанных атомарных единиц

### Детальный разбор на примере Excel

Для Excel-файлов — которые Sapien определяет как самый критичный источник данных — каждое значение получает всеобъемлющий иерархический контекст. Их техническая документация приводит конкретный пример:

> *"The number $738.26 in cell E6 (not actually explicitly defined, but rather a formula linked to 3 other sheets)... in a row called 'Margin'... in a column called '05-2024'... in a table called 'Product ABC-123 specifics' (which notes that all values are in thousands)... in a sheet called 'Plant A financials' (that has notes describing how projections were calculated)... in an Excel called '2024 Projections', last modified on January 3, 2024."*

Иными словами, система знает не просто "$738.26", а:
- Это формула, связанная с 3 другими листами
- В строке "Margin"
- В колонке "05-2024"
- В таблице "Product ABC-123 specifics" (где указано, что значения в тысячах)
- На листе "Plant A financials" (с примечаниями о методике расчета проекций)
- В файле "2024 Projections", последнее изменение 3 января 2024

### Поддерживаемые источники данных

Система поддерживает четыре основные категории источников данных:

- **Произвольные файлы**: Excel, PDFs, PowerPoints, CSVs
- **ERP-системы**: NetSuite, Microsoft Dynamics, SAP, Workday
- **CRM-системы**: Salesforce, HubSpot
- **Data lakes**: Snowflake, BigQuery

Каждая интеграция получает специализированную обработку парсинга перед стандартизацией в полностью контекстуализированные DataFrame и JSON.

---

## Архитектура knowledge graph для верифицируемого доступа к данным

После контекстуализации Sapien хранит информацию в knowledge graph, который отображает связи между концепциями как семантически, так и иерархически. Система использует **контекстуальные эмбеддинги**, основанные не только на значениях данных, но и на текстовых представлениях всего окружающего контекста.

### Критическое архитектурное решение

Knowledge graph **хранит ссылки на доступ к данным, а не сами данные**. Как объясняется в их технической документации:

> *"We can store a reference to data access (i.e. cell location ranges for Excels, functions for integrations) as a node in our knowledge graph. This enables Sapien to search for information across a company relevant to key questions and to have a structured & verifiable method to access the data directly, without actually storing it."*

### Преимущества этого дизайна:

1. **Быстрое извлечение** релевантной информации для любого запроса
2. **Адаптивные связи** — система учится новым соединениям
3. **Встроенная верифицируемость** — каждый результат можно отследить до конкретных исходных ячеек или записей в базе данных

Компания активно разрабатывает fine-tuned, вертикализированные embedding модели, используя агрегированные данные попарных сравнений от пользователей.

### Будущие технические направления

Упомянутые планы включают:
- **Convolutional архитектуры для парсинга Excel** (рассмотрение ячеек как "многомерных пикселей")
- Company-specific эвристики парсинга
- Fine-tuned SQL агенты для общих интеграций
- L1/L2/L3-style кэширование данных в памяти для часто используемых путей

---

## Library learning захватывает неявные знания аналитиков

Помимо data graph, Sapien реализует **систему library learning**, вдохновленную академическими исследованиями в program synthesis. Основная концепция:

> *"when you do something of note, you generalize it, store it in a library that you can then pull from, and apply to other queries/tasks when applicable."*

Этот подход основан на исследованиях Dreamcoder и Voyager для методологий library learning.

### Три типа библиотек:

**1. Concepts library (Библиотека концепций)**
Захватывает неявные знания аналитиков, приобретенные на работе:
- Какие KPI важны для конкретных команд
- Априорные знания о типичных финансовых паттернах
- Понимание бизнес-контекста

**2. Code library (Библиотека кода)**
Хранит переиспользуемые функции для program synthesis:
- Company-specific форматирование графиков
- Recurring паттерны вычислений
- Эти функции питают code generation suite для создания верифицируемых анализов

**3. Trees library (Библиотека деревьев)**
Записывает feedback по reasoning traces для создания MCTS-подобных (Monte Carlo Tree Search) структур:
- Обобщает общие workflows
- Избегает переplanирования каждый раз
- Пример: обновление прогнозов с разными параметрами сценария

### Ключевое преимущество:

> *"By growing these libraries, we increasingly reduce our reliance on LLMs for tasks like deep planning or code generation, instead referring to these library functions. Human feedback helps verify these functions, ensuring the building blocks behind all our processes are correct."*

Растущие библиотеки **снижают зависимость от LLM** для глубокого планирования и генерации кода.

---

## LLM используются минимально через архитектуру verifiable tools

Подход Sapien к минимизации галлюцинаций центрируется на контринтуитивном архитектурном решении: **радикальное ограничение использования LLM**. Их технический блог прямо утверждает:

> *"Most centrally, we use LLMs a lot less than you might think. LLMs are really good at understanding context and knowing what to do next, but they're awful at actually doing that thing reliably."*

### LLM ограничены только тремя функциями:

1. **Data contextualization** — понимание, что означают данные и как они связаны с запросами
2. **Query understanding and problem breakdown** — интерпретация вопросов пользователя
3. **Routing between deterministic tools** — решение, какие верифицированные компоненты вызвать

Все фактические вычисления и анализ проходят через **систему verifiable tools**. Техническая документация объясняет:

> *"We constrain our code generation system to use verifiable tools. Rather than letting the language model run free with calculations, it primarily routes between verified nodes or through tested code paths. This dramatically reduces the chance of errors, particularly crucial when small mistakes in financial calculations can compound into major issues."*

### Четырёхуровневая архитектура надежности:

1. **Verifiable tools constraint** на генерацию кода
2. **Human-in-the-loop feedback** — каждое взаимодействие как возможность обучения
3. **Structured workflows** — ограничение пространства решений установленными финансовыми практиками
4. **Comprehensive evaluation framework** — непрерывное тестирование различных типов анализа

### Полная прозрачность:

Каждый output включает точные цитаты:

> *"Every number in Sapien's analyses comes with precise citations back to source data. When Sapien says revenue grew 12.3%, you can click through to see exactly which cells, database entries, or calculations produced that figure."*

---

## Архитектура reasoning tree с translation layer для UX

Ключевой технический челлендж, который решает Sapien — это сделать сложное AI-рассуждение понятным для нетехнических финансовых пользователей. Их решение использует **reasoning tree с translation layer**.

### Базовая система:

Система использует:
> *"complete reasoning tree that tracks every analytical step at runtime. This tree structure, that functions similarly to Monte Carlo Tree Search approaches, allows us to compose complex analyses from simpler components while maintaining a clear record of the decision process."*

### Проблема прямой экспозиции:

Однако прямая экспозиция древовидных структур перегрузила бы CFO. Sapien построила **translation layer** между AI агентами и пользовательским интерфейсом, который:

> *"linearizes content so it can be presented to finance teams in ways that are easy to follow, rather than a complex branching structure. The goal here is to seamlessly match how people think, and the translation layer makes this happen through this linearization, as well as prioritization and summaries that ensure the most essential details are surfaced to the end user."*

### Практический результат:

Этот дизайн позволяет пользователям оспаривать предположения без понимания технических деталей:

> *"If an analyst disagrees with where Sapien is pulling data from or how it's thinking about a question, all they have to do is spell that out and Sapien can course correct."*

---

## Human-in-the-loop строит финансовую reward function

Архитектура непрерывного обучения Sapien рассматривает каждое взаимодействие как обучающие данные. Коррекции и валидации аналитиков улучшают подход системы для конкретных компаний при сохранении безопасности данных. Конечная цель: построение **robust financial reward function**.

Компания ссылается на исследование "Let's Verify Step by Step" для разработки reward model. Их технический блог объясняет:

> *"When analysts validate or correct our work, that feedback helps refine Sapien's approach for their specific company (while maintaining utmost data security). This builds towards our vision of a robust financial reward function."*

### Механизмы обратной связи работают на нескольких уровнях:

1. **Валидация library functions** — обеспечивает корректность строительных блоков
2. **Коррекция workflow** — обучает MCTS-подобные reasoning trees
3. **Pairwise comparison данные** — улучшает embedding модели

Это создаёт маховик, где company-specific кастомизация улучшается с использованием.

---

## Конкурентное позиционирование в FP&A ландшафте

Хотя прямого сравнительного анализа между Sapien и устоявшимися FP&A инструментами вроде Datarails, Vena или Pigment не существует, технический подход Sapien фундаментально отличается от конкурентного ландшафта, который они описывают. Их блог критикует три категории существующих решений:

### 1. Point solution patchwork (Лоскутное одеяло точечных решений)
Множество SaaS инструментов, которые не коммуницируют друг с другом, создавая больше overhead'а по управлению IT, чем аналитической ценности.

### 2. Dashboard delusion (Иллюзия дашбордов)
Business intelligence инструменты, предоставляющие статичные визуализации без actionable insights — то, что они называют:
> *"BI without the I"* (BI без Intelligence)

### 3. Chatbot chasm (Пропасть чатботов)
AI инструменты, которые извлекают данные по запросу, но не понимают и не действуют на них осмысленно.

### Позиционирование Sapien:

Sapien нацелены на пробел, который оставляют эти решения: глубокое контекстуальное понимание в сочетании с возможностью автономного анализа. Как CEO Ron Nachum объяснил Fortune:

> *"Data analysts spend 90% of their time pulling data and cleaning it and analyzing. What if instead of doing one or two models a week, they could do 100 in an hour?"*

---

## Заявленная производительность и case studies

Sapien сообщает о значительных улучшениях производительности для ранних клиентов.

### Case study: Carlex (производство)

Их производственный клиент Carlex:
- Устранил manual finance reporting
- Обнаружил margin opportunities, скрытые в данных о производстве и variance costs

### Значимая находка ошибки:

Согласно покрытию Fortune:
> *"One manufacturing client saved critical hours on attribution analysis and uncovered a nearly $10 million error ahead of a board meeting."*

### Общие заявления:

Компания заявляет, что их система сокращает **100+ часов ручной работы до 5 минут** для сложных финансовых анализов.

### Use cases охватывают:

- **Manufacturing**: анализ транзакционных данных через десятки заводов для mix impacts
- **Healthcare**: оценка revenue и visit trends через сотни клиник
- **Software**: сравнение неструктурированных данных через customer cohorts

---

## Безопасность и enterprise deployment

Для enterprise deployment Sapien поддерживает SOC 2 и SOC 3 compliance с zero-trust архитектурой.

### Ключевые функции безопасности:

1. **RBAC governance** (Role-Based Access Control)
2. **End-to-end encryption** с rotating keys
3. **24/7 threat detection monitoring**

### Варианты развёртывания:

- SSO (Single Sign-On)
- BYOK (Bring Your Own Key)
- BYOM (Bring Your Own Model) конфигурации

### Встроенная безопасность архитектуры:

Knowledge graph архитектура по своей природе усиливает безопасность, поскольку хранит ссылки на доступ к данным, а не сами данные, а company-specific обучение происходит в приватных, защищенных instances.

---

## Практический пример работы системы

Давайте разберём, как это работает на примере типичного финансового запроса:

### Запрос CFO:
"What drove our Q3 revenue growth?"

### Шаг 1: LLM понимает контекст
LLM разбирает намерение:
- Нужны revenue данные за Q3
- Сравнение с предыдущим периодом
- Breakdown по драйверам роста

### Шаг 2: Knowledge graph поиск
Система ищет в knowledge graph релевантные data access references:
- NetSuite.revenue_table (ячейки B45:B67 для Q3)
- Salesforce.deals_closed (Q3 cohort)
- Excel "2024_Projections.xlsx" (Product mix data)

### Шаг 3: LLM строит план через verifiable tools
```python
revenue_tool.get_data(
    source="NetSuite.revenue_table",
    period="Q3_2024",
    breakdown="product_line"
)

variance_tool.calculate(
    current=Q3_revenue,
    previous=Q2_revenue,
    method="waterfall"
)

driver_tool.analyze(
    revenue_breakdown=product_data,
    external_factors=market_data
)
```

### Шаг 4: Детерминистическое выполнение
Verifiable tools выполняются:
- Никаких LLM-вычислений
- Только проверенный код
- Каждый шаг traceable

### Шаг 5: Translation layer форматирует результат
```
Q3 Revenue Growth: +15.3%

Key Drivers:
1. Product Line A: +$2.1M (+23%)
   Source: NetSuite.revenue_table, cells B45-B52
   Driver: New enterprise contracts (verified from Salesforce)

2. Product Line B: -$0.3M (-5%)
   Source: NetSuite.revenue_table, cells B53-B59
   Note: Seasonal pattern (from historical analysis)

3. Geographic expansion: +$0.8M
   Source: Excel "2024_Projections.xlsx", Sheet "Regional"
   
[Каждая цифра кликабельна → ведёт к source cell]
```

### Шаг 6: Challengeable результаты
Аналитик может сказать:
- "Exclude seasonal products"
- "Break down by customer segment instead"
- "Use EMEA region only"

Система **пересчитывает** с новыми параметрами, используя те же verifiable tools.

---

## Ссылки на оригинальные источники

### Основные технические статьи:

| Документ | URL |
|----------|-----|
| How Sapien Learns Company Representations | https://sapien.ai/blog-posts/how-sapien-learns-company-representations |
| How We Build Trustworthy AI for CFOs | https://www.getsapien.com/blog-posts/how-we-build-trustworthy-ai-for-cfos |
| Sapien Raises $8.7M Seed Led by General Catalyst | https://sapien.ai/blog-posts/sapien-raises-8-7m-seed-led-by-general-catalyst |
| Основная страница продукта | https://sapien.ai/ |

### Новостное покрытие:

| Источник | URL |
|----------|-----|
| Fortune (October 2024) | https://fortune.com/2024/10/29/ai-coworkers-startup-cfo-8-7-million-seed-round-general-catalyst/ |
| Harvard Technology Review | https://harvardtechnologyreview.com/2024/12/17/from-dorm-room-to-boardroom-how-ron-nachum-and-sapien-are-redefining-ai-in-corporate-finance/ |

### Академические исследования, на которые ссылается Sapien:

| Исследование | Применение | arXiv |
|--------------|------------|-------|
| SpreadsheetLLM | Excel parsing подходы | arxiv.org/pdf/2407.09025v1 |
| Dreamcoder | Library learning | arxiv.org/pdf/2006.08381 |
| Voyager | Library learning | arxiv.org/pdf/2305.16291 |
| Anthropic's Contextual Retrieval | Contextual embeddings | - |
| Let's Verify Step by Step | Reward model building | arxiv.org/pdf/2305.20050 |

---

## Выводы: Что делает подход Sapien уникальным

### 1. Инвертированная архитектура
В отличие от конкурентов, которые строят AI "сверху" данных, Sapien строит "снизу вверх":
- Сначала глубокое понимание данных (company representation)
- Затем verifiable tools для манипуляции
- LLM только как router и интерпретатор

### 2. Детерминизм вместо вероятности
Финансовые вычисления **никогда** не делаются через LLM:
- Исключает hallucination risk
- Каждый результат воспроизводим
- Полная трассируемость к source

### 3. Накопление знаний
Library learning создаёт накопительный эффект:
- Система умнеет с каждым использованием
- Company-specific знания сохраняются
- Human feedback улучшает building blocks

### 4. Прозрачность для нетехнических пользователей
Translation layer решает парадокс:
- Техническая точность под капотом
- Простой интерфейс для CFO
- Challengeable без понимания кода

### 5. Enterprise-ready security
Архитектура спроектирована для compliance:
- Данные не хранятся в knowledge graph
- Private instances для обучения
- SOC 2/3 compliance out of the box

---

## Применимость для твоих баров

Для твоей сети "Пивная Культура" этот подход означает:

### Вместо обычного AI:
```
"Продажи упали на 15%"
← откуда? может hallucination
```

### Sapien-подход:
```
"Продажи упали на 15.3%"
Source: POS_Analytics.db, таблица daily_sales, SUM(2024-11)
Calculation: (Nov_revenue - Oct_revenue) / Oct_revenue

Breakdown по категориям:
- Draft Beer: -23.1% 
  Source: tap_logs.csv, column "volume_liters"
  Verified: 4 тапа были offline 12-18 Nov
  
- Bottled Beer: -8.2%
  Source: inventory_system API, endpoint /sales/bottled
  
- Snacks: +5.1%
  Source: POS.xlsx, Sheet "Kitchen"

Primary driver: Plant_A production disruption
  Source: supplier_data.xlsx, Sheet "Deliveries", cell C15
  Note: 40% reduction in kegs delivered 10-20 Nov

[Challenge options available]:
☑ "Compare vs same period last year"
☑ "Exclude location #3 (renovation)"
☑ "Show by day of week pattern"
```

**Каждая цифра верифицируема, каждый расчёт детерминистичен, каждое предположение challengeable.**

Это и есть "AI CEO с большой консистентностью", о котором ты слышал.