# Архитектура проекта

## Что это

Beer ABC Analysis — Flask веб-приложение для аналитики баров с интеграцией iiko API. Предоставляет дашборды, ABC/XYZ анализ, управление сотрудниками, кранами, остатками.

## Файлы

### Точка входа
- [`app.py`](../../app.py) — инициализация Flask, регистрация blueprint'ов, версионирование

### Конфигурация
- [`config.py`](../../config.py) — iiko API настройки (SERVER, LOGIN, PASSWORD)
- [`requirements.txt`](../../requirements.txt) — зависимости: Flask, pandas, numpy, requests, aiogram
- [`extensions.py`](../../extensions.py) — глобальные синглтоны (taps_manager, plans_manager, venues_manager, кэши)

### Backend структура
```
core/                    # Бизнес-логика
├── iiko_api.py         # iiko authentication, cashshifts, сотрудники
├── olap_reports.py     # OLAP отчёты (all_sales, beer, draft, kitchen)
├── dashboard_analysis.py  # 15 метрик дашборда
├── employee_analysis.py   # Метрики сотрудников
├── kpi_calculator.py   # KPI бонусы
├── plans_manager.py    # Планы выручки
├── taps_manager.py     # Управление кранами
├── abc_analysis.py     # ABC анализ
├── xyz_analysis.py     # XYZ анализ
└── ... (20+ модулей)

routes/                  # Flask blueprint'ы
├── pages.py            # Статические страницы
├── analysis.py         # ABC/XYZ, категории, разливное
├── employee.py         # Сотрудники, сравнение, бонусы
├── taps.py             # Краны API
├── dashboard.py        # Дашборд API
├── stocks.py           # Остатки API
├── schedule.py         # График смен
└── misc.py             # Тесты, wiki, Telegram

templates/              # HTML шаблоны
├── dashboard.html
├── employee.html
├── taps.html
└── ...

static/js/dashboard/    # JavaScript модули
├── core/
│   ├── state.js       # Централизованное состояние
│   ├── api.js         # HTTP клиент
│   └── utils.js
├── modules/
│   ├── analytics.js
│   ├── charts.js
│   ├── trends.js
│   └── ... (15+ модулей)
```

### Данные
- [`data/bar_plans.json`](../../data/bar_plans.json) — планы выручки по точкам на каждый день
- [`data/kpi_targets.json`](../../data/kpi_targets.json) — KPI цели по месяцам
- [`data/taps_data.json`](../../data/taps_data.json) — состояние кранов
- [`data/plansdashboard.json`](../../data/plansdashboard.json) — планы для дашборда

---

## Как работает

### Архитектурная схема

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ dashboard   │  │ employee    │  │ taps        │          │
│  │ .html       │  │ .html       │  │ .html       │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│         │                │                │                  │
│  ┌──────┴────────────────┴────────────────┴──────┐          │
│  │         JavaScript Modules (15+)              │          │
│  │  state.js │ api.js │ charts.js │ trends.js   │          │
│  └─────────────────────┬─────────────────────────┘          │
└────────────────────────┼────────────────────────────────────┘
                         │ HTTP/JSON API
┌────────────────────────┼────────────────────────────────────┐
│                      Backend                                 │
│  ┌────────────────────┴─────────────────────────┐           │
│  │        Flask App (app.py)                    │           │
│  │  /api/dashboard-analytics                    │           │
│  │  /api/employee-analytics                     │           │
│  │  /api/taps/*                                 │           │
│  │  /api/stocks/*                               │           │
│  └────────────────────┬─────────────────────────┘           │
│                       │                                      │
│  ┌────────────────────┴─────────────────────────┐           │
│  │        Routes (8 blueprints)                 │           │
│  │  pages │ analysis │ employee │ taps │ ...    │           │
│  └────────────────────┬─────────────────────────┘           │
│                       │                                      │
│  ┌────────────────────┴─────────────────────────┐           │
│  │        Core (20+ модулей)                    │           │
│  │  iiko_api.py │ olap_reports.py │ ...         │           │
│  └────────────────────┬─────────────────────────┘           │
└────────────────────────┼────────────────────────────────────┘
                         │
┌────────────────────────┼────────────────────────────────────┐
│                 Внешние API                                  │
│  ┌────────────────────┴─────────────────────────┐           │
│  │  iiko API                                    │           │
│  │  - auth (SHA-1)                              │           │
│  │  - OLAP v2 (продажи)                         │           │
│  │  - cashshifts v2 (смены)                     │           │
│  │  - attendance (явки)                         │           │
│  └──────────────────────────────────────────────┘           │
│  ┌──────────────────────────────────────────────┐           │
│  │  Честный ЗНАК API                            │           │
│  │  - balance                                   │           │
│  │  - search                                    │           │
│  │  - expiring codes                            │           │
│  └──────────────────────────────────────────────┘           │
│  ┌──────────────────────────────────────────────┐           │
│  │  Telegram Bot (aiogram)                      │           │
│  └──────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

### Основные endpoint'ы

#### Dashboard
| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/dashboard-analytics` | POST | 15 метрик за период |
| `/api/venues` | GET | Список заведений |
| `/api/weeks` | GET | Недели для селектора |
| `/api/plans/*` | GET/POST/DELETE | CRUD планов |
| `/api/compare/periods` | POST | Сравнение периодов |
| `/api/trends/:venue/:metric` | GET | Тренды по неделям |
| `/api/export/excel` | POST | Экспорт в Excel |
| `/api/export/pdf` | POST | Экспорт в PDF |

#### Сотрудники
| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/employees` | GET | Список сотрудников |
| `/api/employee-analytics` | POST | Детальная аналитика |
| `/api/employee-compare` | POST | Сравнение нескольких |
| `/api/bonus-calculate` | POST | Расчёт бонуса |
| `/api/kpi-calculate` | POST | Расчёт KPI |

#### Краны
| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/taps/bars` | GET | Список баров |
| `/api/taps/:bar_id` | GET | Краны бара |
| `/api/taps/:bar_id/start` | POST | Подключить кегу |
| `/api/taps/:bar_id/stop` | POST | Остановить кран |
| `/api/taps/:bar_id/replace` | POST | Заменить кегу |
| `/api/taps/export-taplist` | GET | CSV экспорт |

#### Анализ
| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/analyze` | POST | ABC/XYZ анализ |
| `/api/categories` | POST | Анализ по категориям |
| `/api/draft-analyze` | POST | Анализ разливного |
| `/api/waiter-analyze` | POST | Анализ по официантам |
| `/api/discount-analyze` | POST | Анализ скидок |

#### Остатки
| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/stocks/taplist` | GET | Кеги на кранах |
| `/api/stocks/kitchen` | GET | Остатки кухни |
| `/api/stocks/bottles` | GET | Фасовка |

---

## Зависимости

### Внешние
- **iiko API** — основные данные: продажи (OLAP), кассовые смены, сотрудники
- **Честный ЗНАК API** — маркировка товаров, остатки, сроки годности
- **Telegram Bot** — уведомления, виджет для Android

### Внутренние
```
iiko API → core/iiko_api.py → core/olap_reports.py
                ↓                    ↓
        core/dashboard_analysis.py → routes/dashboard.py → Frontend
        core/employee_analysis.py → routes/employee.py → Frontend
        core/taps_manager.py → routes/taps.py → Frontend
```

---

## Changelog

- **2026-03-27** — Создан документ overview.md с полной архитектурой системы
