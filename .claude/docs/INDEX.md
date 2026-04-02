# Документация проекта Beer ABC Analysis

## Навигация по документам

| Документ | Описание | Статус |
|----------|----------|--------|
| [overview.md](overview.md) | Архитектура проекта, стек технологий, структура | ✅ |
| [iiko-integration.md](iiko-integration.md) | Интеграция с iiko API: OLAP, cashshifts,-authentication | ✅ |
| [dashboard.md](dashboard.md) | Главный дашборд: 15 метрик, планы, сравнение, тренды | ✅ |
| [abc-xyz-analysis.md](abc-xyz-analysis.md) | ABC/XYZ анализ ассортимента, формулы расчётов | ✅ |
| [employee.md](employee.md) | Сотрудники: метрики, планы, KPI, бонусы | ✅ |
| [taps.md](taps.md) | Управление кранами: START/STOP/REPLACE, история | ✅ |
| [venues-plans.md](venues-plans.md) | Торговые точки, планы выручки, weekend weighting | ✅ |
| [schedule.md](schedule.md) | График смен, роли, meeting notes | ✅ |
| [frontend.md](frontend.md) | JavaScript модули, state management, Chart.js | ✅ |
| [stocks.md](stocks.md) | Остатки: кеги, кухня, фасовка, Честный ЗНАК | ✅ |
| [lessons.md](lessons.md) | Баги, паттерны, решения (Problem→Cause→Solution) | ✅ |
| [draft-beer-errors.md](draft-beer-errors.md) | Ошибки и проблемы анализа проливов | ✅ |
| [draft-beer-fixes.md](draft-beer-fixes.md) | Исправления анализа проливов (2026-03-31) | ✅ |
| [CHANGELOG.md](CHANGELOG.md) | История изменений по сессиям | ✅ |

---

## Краткое описание модулей

### overview.md
Общая архитектура системы: Flask backend, core модули (20+ файлов), routes (8 blueprint'ов), frontend (templates + 15 JS модулей), интеграции (iiko, Честный ЗНАК, Telegram).

### iiko-integration.md
Критически важный модуль. Детально описывает:
-Authentication (SHA-1 hash)
- OLAP API v2 (all_sales, beer_sales, draft_sales, kitchen_sales)
- Cashshifts API v2 (кассовые смены, локации сотрудников)
- **Критические особенности:** `to` дата EXCLUSIVE, AuthUser vs WaiterName, матчинг имён

### dashboard.md
Главный дашборд с 15 метриками:
- Выручка (розлив/фасовка/кухня)
- Доли категорий (%)
- Чеки, средний чек
- Наценка, прибыль
- Списания баллов

### abc-xyz-analysis.md
Анализ ассортимента пива:
- **ABC:** Парето 80/15/5, наценка (A≥120%, B=100-120%, C<100%)
- **XYZ:** CV вариация (X<10%, Y<25%, Z≥25%)

### employee.md
Эффективность сотрудников:
- Метрики из OLAP (AuthUser)
- Планы из кассовых смен
- KPI расчёт (3 метрики, взвешенные цели)

### taps.md
Система управления кранами:
- 4 бара, 12-24 крана
- Действия: START, STOP, REPLACE
- Thread-safe операции
- История в JSON

### venues-plans.md
Планы выручки по точкам:
- 4 точки: Кременчугская, Варшавская, Большой пр, Лиговский
- Weekend weighting (пт/сб = 2x)
- Пропорциональный расчёт периода

### schedule.md
График работы сотрудников:
- Смены, роли, локации
- Revenue plan/fact
- Meeting notes

### frontend.md
JavaScript архитектура дашборда:
- state.js (Singleton)
- api.js (HTTP клиент)
- 15+ модулей (analytics, charts, trends, comparison...)
- Chart.js визуализация

### stocks.md
Остатки товаров:
- Taplist (кеги на кранах)
- Kitchen (кухня)
- Bottles (фасовка)
- Честный ЗНАК API

### lessons.md
Изученные уроки, баги, паттерны:
- Формат: Problem → Cause → Solution
- Критические находки из production

### draft-beer-errors.md
Ошибки анализа проливов:
- Потеря данных при парсинге объема
- Дублирование из-за нормализации
- Некорректный BeerSharePercent
- Проблемы производительности OLAP
- Диагностика расхождений

### draft-beer-fixes.md
Исправления анализа проливов (2026-03-31):
- Улучшенный парсинг (10+ форматов, эвристика)
- Двухэтапная нормализация (BeerNameOriginal + BeerNameNorm)
- Эвристика вместо удаления записей
- O(1) маппинг поставщиков (вместо O(n²))
- Корректный BeerSharePercent для каждого бара
- 30 unit-тестов

### CHANGELOG.md
Посессионная история изменений:
- Дата сессии
- Что сделано
- Какие файлы изменены

---

## Обновление индекса

При добавлении нового документа:
1. Создать файл в `.claude/docs/`
2. Добавить строку в таблицу выше
3. Добавить краткое описание в секцию "Краткое описание модулей"
