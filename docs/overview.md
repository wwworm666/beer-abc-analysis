# Архитектура проекта

## Что это

**Beer ABC Analysis** — Flask веб-приложение для аналитики 4 баров сети «КУЛЬТУРА ПИВА» (Санкт-Петербург, ИНВЕСТАГРО ООО). Интегрируется с **iiko API** (продажи, кассовые смены), **Честным Знаком** (маркировка/сроки годности), **Telegram** (operations-боты).

Покрывает:
- Дашборд План/Факт (15 метрик × 4 точки + общая)
- ABC/XYZ-анализ ассортимента пива, разливного и кухни
- Конструктор отчётов с pivot-агрегацией OLAP-данных
- Управление 60 разливными кранами (START/STOP/REPLACE)
- Остатки + сводный заказ с velocity-классификацией
- Shelf-Life Cockpit (tier-логика срочности уценки)
- Дашборд сотрудника, KPI/бонусы, график смен
- Open-check Telegram-бот (ежедневная проверка открытых смен)
- PWA-виджет выручки (Android/iOS)

Прод: **https://beerkultura.ru** (Selectel Cloud Server, Docker Compose + Caddy + gunicorn `--workers 2`).

---

## Файлы

### Точка входа и инфраструктура

- [app.py](../app.py) — инициализация Flask, регистрация blueprint'ов, запуск шедулеров (CHZ, open-check), Telegram init
- [extensions.py](../extensions.py) — глобальные синглтоны (taps_manager, plans_manager, venues_manager, кэши OLAP/employees)
- [config.py](../config.py) — iiko API конфиг (SERVER/LOGIN/PASSWORD)
- [requirements.txt](../requirements.txt) — Flask 3.0, pandas 2.2, gunicorn 21.2, aiogram 3.4, paramiko, portalocker, openpyxl, **playwright** (только для menu_tool)
- [.env.example](../.env.example) — шаблон переменных окружения
- [Dockerfile](../Dockerfile), [docker-compose.yml](../docker-compose.yml), [Caddyfile](../Caddyfile) — актуальный деплой на Selectel VPS
- [render.yaml](../render.yaml) — **legacy** (rollback-страховка на 1-2 недели, не используется)

### Backend: routes/ (11 blueprints)

Регистрация в [routes/__init__.py](../routes/__init__.py). `menu_bp` вынесен в [menu_tool/](../menu_tool/) как отдельное локальное приложение на порту 5050 — в прод не включается (Chromium-рендер не помещается в Starter-план).

| Blueprint | URL-префикс | Что отдаёт | Файл |
|---|---|---|---|
| `pages_bp` | `/` | HTML-страницы (/, /packaging, /draft, /waiters, /discounts, /explorer, /taps/<bar>, /schedule, /employee, /salary, /bonus, /expiration) | [routes/pages.py](../routes/pages.py) |
| `analysis_bp` | `/api` | ABC/XYZ, draft, waiters, discounts (RFM) | [routes/analysis.py](../routes/analysis.py) |
| `dashboard_bp` | `/api` | dashboard-analytics, venues, weeks, plans CRUD, export xlsx | [routes/dashboard.py](../routes/dashboard.py) |
| `employee_bp` | `/api` | employee KPI, salary, bonus | [routes/employee.py](../routes/employee.py) |
| `taps_bp` | `/api` | краны START/STOP/REPLACE, taplist export CSV | [routes/taps.py](../routes/taps.py) |
| `stocks_bp` | `/api` | taplist, kitchen, bottles, order-board, expiry, chz refresh | [routes/stocks.py](../routes/stocks.py) |
| `schedule_bp` | `/api` | график смен по барам | [routes/schedule.py](../routes/schedule.py) |
| `misc_bp` | `/api` | dish-group, wiki, Telegram webhook | [routes/misc.py](../routes/misc.py) |
| `expiration_bp` | `/api` | Shelf-Life Cockpit (board, recommend) | [routes/expiration.py](../routes/expiration.py) |
| `explorer_bp` | `/`, `/api` | Конструктор отчётов (pivot iiko) | [routes/explorer.py](../routes/explorer.py) |
| `open_check_bp` | `/api`, `/telegram/openbot` | ручной run + webhook open-check бота | [routes/open_check.py](../routes/open_check.py) |

### Backend: core/ (33 модуля)

#### iiko-интеграция и данные
- [iiko_api.py](../core/iiko_api.py) — auth (SHA-1), cashshifts v2, attendance, POS-mapping
- [olap_reports.py](../core/olap_reports.py) — OLAP v2 (all_sales, beer, draft, kitchen, **explorer_sales** с ThirdParent для конструктора), nomenclature, store_balances, store_operations
- [iiko_barcodes.py](../core/iiko_barcodes.py) — парсер XML iiko `/products` → `{gtin14: [iiko_pid]}` (для стыковки с ЧЗ)
- [data_processor.py](../core/data_processor.py) — генерация недель (ISO), бакетирование

#### Аналитика
- [dashboard_analysis.py](../core/dashboard_analysis.py) — 15 метрик дашборда (выручка, доли, чеки, средний чек, наценка, прибыль, баллы)
- [abc_analysis.py](../core/abc_analysis.py), [xyz_analysis.py](../core/xyz_analysis.py) — ABC (Парето 80/15/5) + XYZ (CV)
- [category_analysis.py](../core/category_analysis.py) — анализ по категориям
- [draft_analysis.py](../core/draft_analysis.py) — разливное: 2-этапная нормализация имён, корректный BeerSharePercent
- [waiter_analysis.py](../core/waiter_analysis.py) — анализ по официантам
- [trends_analyzer.py](../core/trends_analyzer.py), [comparison_calculator.py](../core/comparison_calculator.py) — тренды и сравнение периодов
- [revenue_metrics.py](../core/revenue_metrics.py) — единая точка чтения метрик выручки
- [explorer.py](../core/explorer.py) — `build_pivot()` для конструктора отчётов

#### Сотрудники и планы
- [employee_analysis.py](../core/employee_analysis.py) — метрики по AuthUser, word-set matching имён
- [employee_plans.py](../core/employee_plans.py) — KPI-каталог, BAR_NAME_MAPPING (имена касс vs OLAP)
- [kpi_calculator.py](../core/kpi_calculator.py) — KPI бонусы, взвешенные цели
- [plans_manager.py](../core/plans_manager.py) — CRUD планов с cross-worker portalocker
- [shifts_manager.py](../core/shifts_manager.py) — управление сменами (SQLite + WAL pragma)
- [meeting_notes.py](../core/meeting_notes.py) — заметки совещаний

#### Краны и остатки
- [taps_manager.py](../core/taps_manager.py) — CRUD кранов, atomic-write через tmp+fsync+replace
- [expiry_recommend.py](../core/expiry_recommend.py) — `classify_tier()` + `recommend()` для Shelf-Life Cockpit

#### Шедулеры и фоновые процессы
- [chz_scheduler.py](../core/chz_scheduler.py) — daemon-thread, авторефреш ЧЗ-кэша в 03:00 МСК + atomic lock-файл
- [open_check_scheduler.py](../core/open_check_scheduler.py) — daemon-thread, проверка открытых смен в 14:59 МСК + atomic lock-файл
- [open_check_bot.py](../core/open_check_bot.py) — логика проверки + форматирование сообщений
- [open_check_telegram.py](../core/open_check_telegram.py) — Telegram Bot API (sync через `requests`), inline-меню
- [open_check_subscribers.py](../core/open_check_subscribers.py) — хранилище подписок (`data/open_check_subscribers.json` + portalocker)

#### Конфиг и утилиты
- [venue_config.py](../core/venue_config.py) — 4 канонических бара + маппинги имён OLAP/UI
- [storage_paths.py](../core/storage_paths.py) — единый paths-helper (`PERSISTENT_DATA_DIR=/kultura`)
- [weeks_generator.py](../core/weeks_generator.py) — генератор недель для селектора
- [export_manager.py](../core/export_manager.py) — экспорт XLSX

### Frontend

```
templates/                  # Jinja2 HTML
├── dashboard.html          # главная: 4 точки + Общая, 15 метрик, AI-анализ
├── employee.html           # дашборд сотрудника, KPI, бонусы
├── taps_bar.html           # управление кранами одного бара (/taps/<bar_id>)
├── stocks.html             # 4 вкладки: Сводный заказ, Таплист, Фасовка, Сроки годности
├── expiration.html         # Shelf-Life Cockpit (отдельная страница)
├── explorer.html           # Конструктор отчётов
├── schedule.html, salary.html, bonus.html, packaging.html, draft.html, discounts.html, waiters.html
├── wiki.html               # встроенная wiki с TOC
├── pwa-widget.html         # PWA виджет выручки
└── shared/
    └── nav.html            # общая навигация (sidebar + topbar)

static/
├── js/
│   ├── dashboard/
│   │   ├── core/           # state.js (singleton), api.js, utils.js
│   │   └── modules/        # 15+ модулей: analytics, charts, trends, plans, comparison, ai_insights, ...
│   └── ...
├── css/
└── pwa/                    # manifest, service worker
```

### Данные

```
data/
├── plansdashboard.json     # Месячные планы (16 метрик × venue × period_key)
├── daily_plans.json        # Ежедневные планы (авто-генерация, Пт/Сб = weight 2x)
├── kpi_targets.json        # KPI цели по месяцам
├── taps_data.json          # Состояние 60 кранов + история (atomic-write)
├── meeting_notes.json      # Заметки совещаний
├── open_check_subscribers.json  # Telegram-подписки open-check бота
├── nomenclature_cache.json # Кэш номенклатуры iiko (24ч диск + 15 мин память)
├── olap_all_fields.json    # Справочник OLAP-полей
├── beer_report.json, kegs_products.json, keg_mapping.json
├── cache/
│   ├── nomenclature__products.xml  # iiko /products XML (баркоды для ЧЗ)
│   ├── nomenclature_full.json      # OLAP nomenclature
│   ├── kitchen_report.json, store_operations_report.json
│   └── ...
└── .chz_refresh_lock_YYYY-MM-DD     # Atomic lock-файл (создаётся scheduler'ом)
   .open_check_lock_YYYY-MM-DD       # Atomic lock-файл (создаётся scheduler'ом)
```

**Persistence на Selectel:** docker volume `/srv/beer/data → /app/data` + `/srv/beer/chz_debug → /app/chz_test/debug`. Логика deduplicate'нных путей реализована в [core/storage_paths.py](../core/storage_paths.py) через `PERSISTENT_DATA_DIR=/kultura`.

### Отдельные приложения и службы

- **[menu_tool/](../menu_tool/)** — standalone Flask на `127.0.0.1:5050` для печати пивных карточек A4 через Playwright (PDF-вектор для печати, PNG-растр для соцсетей). **Не деплоится** на прод — Chromium ест ~150-200 МБ. См. [menu_tool/README.md](../menu_tool/README.md).
- **[chz_test/](../chz_test/)** — ЧЗ-клиент (`chz.py` для бар-ПК с CryptoPro+Rutoken) + утилиты отладки (`probe_gtin.py`, `suggest_barcode_fixes.py`, `export_bartender_list.py`). См. [chz-stock-integration.md](chz-stock-integration.md).
- **[telegram_bot.py](../telegram_bot.py)** / **[telegram_webhook.py](../telegram_webhook.py)** — KULT Taplist бот (polling и webhook), отдельный от open-check бота.

---

## Архитектурная схема

```
┌────────────────────────────────────────────────────────────────┐
│  Selectel Cloud Server (https://beerkultura.ru, 139.100.200.92)│
│                                                                │
│  Caddy (reverse proxy + TLS) --> gunicorn --workers 2          │
│                                       |                        │
│  +------------------------------------+----------------------+ │
│  |  Flask App (app.py)                                       | │
│  |  +- 11 blueprints (routes/__init__.py)                    | │
│  |  +- Шедулеры (daemon-threads):                            | │
│  |  |   * chz_scheduler — 03:00 МСК + atomic lock            | │
│  |  |   * open_check_scheduler — 14:59 МСК + atomic lock     | │
│  |  +- Telegram webhook handlers (open_check_bp, misc_bp)    | │
│  +------------------------------------------------------------+ │
│                                                                │
│  Docker volumes (persistent):                                  │
│   /srv/beer/data --> /app/data                                 │
│   /srv/beer/chz_debug --> /app/chz_test/debug                  │
+----------------------------------------------------------------+
                         |
   +---------------------+--------------------+
   |                                          |
   v                                          v
+----------------+              +-----------------------+
| iiko API       |              | Бар-ПК (Tailscale)    |
| - OLAP v2      |              | 100.98.149.108        |
| - cashshifts   |              | - CryptoPro + Rutoken |
| - attendance   |              | - chz.py (dispenser)  |
| - /products XML|              +----+------------------+
+----------------+                   |
                                     | SSH/SFTP
                              +------+---------------+
                              | Честный Знак API     |
                              | - dispenser/tasks    |
                              | - mods/list (КПП/бар)|
                              +----------------------+

   v (через aiogram + sync requests)
+----------------------------------------------------------------+
| Telegram                                                       |
| - @kultura_taplist_bot — KULT Taplist (polling + webhook)      |
| - @kultura_open_bot    — Open-check (webhook, sync requests)   |
+----------------------------------------------------------------+
```

---

## Внешние интеграции

| Сервис | Назначение | Где конфигурируется |
|---|---|---|
| **iiko API** | Продажи (OLAP), кассовые смены, посещения сотрудников, номенклатура (баркоды через XML) | env `IIKO_SERVER/PORT/LOGIN/PASSWORD`, [core/iiko_api.py](../core/iiko_api.py) |
| **Честный Знак** | Маркировка пива/безалк/соков, сроки годности по партиям, привязка к КПП баров. Доступ — через бар-ПК с CryptoPro+Rutoken | env `REMOTE_USER/HOST/PASS`, [chz_test/chz.py](../chz_test/chz.py), [core/chz_scheduler.py](../core/chz_scheduler.py) |
| **Telegram** | KULT Taplist (уведомления барменам) + Open-check (мониторинг открытых смен) | env `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OPEN_CHECK_BOT_TOKEN`, `TELEGRAM_GROUP_CHAT_ID`, `TELEGRAM_ALARM_CHAT_IDS` |
| **Tailscale** | Mesh-сеть до бар-ПК (`100.98.149.108`) | На сервере и бар-ПК как daemon |

---

## Ключевые конвенции и инварианты

1. **Дата `to` в OLAP — EXCLUSIVE.** Везде добавляется `+1 день` перед вызовом iiko. Cashshifts — наоборот, inclusive.
2. **AuthUser, не WaiterName** — для агрегированных метрик сотрудников (waiters заполняется только для заказов с столиками).
3. **Имена сотрудников** — word-set intersection (фамилия-имя vs имя-фамилия) в [core/employee_analysis.py](../core/employee_analysis.py).
4. **BAR_NAME_MAPPING vs IIKO_NAME_TO_KEY** — кассовые смены и OLAP отдают разные имена точек («Пивная культура» vs «Кременчугская»). См. [lessons.md](lessons.md).
5. **Atomic-write для JSON** — все mutable JSON-файлы (`taps_data.json`, `plansdashboard.json`, `meeting_notes.json`, subscribers) пишутся через tmp+fsync+`os.replace`, защищены `portalocker` cross-worker и `threading.Lock` in-process.
6. **Шедулеры под `--workers 2`** — каждый daemon-thread защищён atomic lock-файлом `data/.XXX_lock_YYYY-MM-DD` (`O_CREAT|O_EXCL`), чтобы один воркер взял задачу, другой тихо вышел.
7. **Кеши OLAP** — `DASHBOARD_OLAP_CACHE` (TTL 10 мин) в [extensions.py](../extensions.py). Explorer использует префикс `explorer_*` (другой состав полей).
8. **Без эмодзи** в коде/UI/документации (см. [.claude/CLAUDE.md](../.claude/CLAUDE.md)).

---

## Основные endpoints (резюме)

| Группа | Endpoint | Метод | Модуль |
|---|---|---|---|
| Dashboard | `/api/dashboard-analytics` | POST | [dashboard.md](dashboard.md) |
| Dashboard | `/api/plans/export` | GET (xlsx) | [venues-plans.md](venues-plans.md) |
| Dashboard | `/api/venues`, `/api/weeks` | GET | overview |
| Employee | `/api/employee-analytics`, `/api/bonus-calculate`, `/api/kpi-calculate` | POST | [employee.md](employee.md) |
| Analysis | `/api/analyze`, `/api/draft-analyze`, `/api/discount-analyze` | POST | [abc-xyz-analysis.md](abc-xyz-analysis.md), [discounts.md](discounts.md) |
| Taps | `/api/taps/<bar>`, `/api/taps/<bar>/start|stop|replace` | GET/POST | [taps.md](taps.md) |
| Stocks | `/api/stocks/taplist|kitchen|bottles|order-board|expiry` | GET | [stocks.md](stocks.md) |
| Stocks | `/api/chz/stock|refresh|refresh/status` | GET/POST | [chz-stock-integration.md](chz-stock-integration.md) |
| Expiration | `/api/expiration/board?bars=...` | GET | [expiration.md](expiration.md) |
| Explorer | `/api/explorer/pivot` | GET | [explorer.md](explorer.md) |
| Open-check | `/api/admin/open-check/run-now`, `/telegram/openbot/*` | POST/GET | [open-check-bot.md](open-check-bot.md) |

---

## Changelog

- **2026-05-28** — Полная ревизия. Документация консолидирована в `docs/`. Добавлены: Selectel-деплой, atomic locks под gunicorn 2-workers, WAL для shifts.db, отдельные модули explorer/expiration/open-check, menu_tool как standalone. Удалены: упоминания удалённого menu-модуля и render.yaml-деплоя.
- **2026-03-27** — Создан overview.md с описанием 8 blueprints, 20+ core-модулей, render.yaml-деплоя.
