# Структура проекта Beer ABC/XYZ Analysis

> Дерево репозитория на 2026-05-28. Подробное описание архитектуры — в [overview.md](overview.md), модульные доки — по ссылкам в [.claude/INDEX.md](../.claude/INDEX.md).

## Корневая директория

```
beer-abc-analysis/
├── app.py                  # Точка входа Flask: blueprints + scheduler init + Telegram
├── extensions.py           # Синглтоны: taps_manager, plans_manager, кэши, OLAP locks
├── config.py               # iiko API конфиг (SERVER/PORT/LOGIN/PASSWORD)
├── requirements.txt        # Python deps (Flask, pandas, gunicorn, aiogram, paramiko, portalocker)
├── .env.example            # Шаблон переменных окружения
├── remote_exec.py          # SSH/SFTP к бар-ПК через paramiko (для ЧЗ refresh)
├── telegram_bot.py         # KULT Taplist бот (polling режим)
├── telegram_webhook.py     # KULT Taplist бот (webhook режим)
├── README.md               # Главная документация
│
├── core/                   # Бизнес-логика (33 модуля)
├── routes/                 # Flask blueprints (11 файлов)
├── templates/              # Jinja2 HTML
├── static/                 # CSS, JS, PWA
├── data/                   # Кеши и состояние (mounted persistent в проде)
├── menu_tool/              # Standalone Flask :5050 для печати меню A4 (Playwright)
├── chz_test/               # ЧЗ-клиент + утилиты отладки
├── mapping/                # Маппинг блюд на кеги (CSV)
├── utils/                  # Утилиты маппинга
├── scripts/                # Вспомогательные скрипты (debug, check, maintenance)
├── tests/                  # Тесты
├── docs/                   # Документация проекта (SoT)
├── .claude/                # Принципы + индекс для агентов
├── memory/                 # Persistent-память (auto-managed)
├── knowledge_graph/        # MCP knowledge graph
├── archive/                # Архив legacy-кода
│
├── Dockerfile              # Production-сборка (Selectel VPS)
├── docker-compose.yml      # Сервис gunicorn (--workers 2) + Caddy
├── Caddyfile               # Reverse proxy + TLS для beerkultura.ru
└── render.yaml             # (legacy) Render.com — rollback-страховка
```

---

## `core/` — Бизнес-логика (33 модуля)

### iiko-интеграция и данные (4)
| Файл | Что делает |
|---|---|
| `iiko_api.py` | Auth (SHA-1), cashshifts v2, attendance, POS-mapping |
| `olap_reports.py` | OLAP v2 (all_sales, beer, draft, kitchen, **explorer_sales**), nomenclature, store_balances, store_operations |
| `iiko_barcodes.py` | Парсер XML `/products` → `{gtin14: [iiko_pid]}` для стыковки с ЧЗ |
| `data_processor.py` | Генерация недель ISO, бакетирование |

### Аналитика (8)
| Файл | Что делает |
|---|---|
| `dashboard_analysis.py` | 15 метрик дашборда |
| `abc_analysis.py` | ABC (Парето 80/15/5) |
| `xyz_analysis.py` | XYZ (CV вариация) |
| `category_analysis.py` | Анализ по категориям |
| `draft_analysis.py` | Разливное (2-этапная нормализация) |
| `waiter_analysis.py` | Анализ по официантам |
| `trends_analyzer.py` | Тренды по неделям |
| `comparison_calculator.py` | Сравнение периодов |
| `revenue_metrics.py` | Единая точка чтения метрик выручки |
| `explorer.py` | **build_pivot()** для конструктора отчётов |

### Сотрудники и планы (6)
| Файл | Что делает |
|---|---|
| `employee_analysis.py` | Метрики по AuthUser, word-set matching имён |
| `employee_plans.py` | KPI-каталог, **BAR_NAME_MAPPING** (cashshifts vs OLAP) |
| `kpi_calculator.py` | KPI бонусы |
| `plans_manager.py` | CRUD планов + **portalocker** cross-worker |
| `shifts_manager.py` | SQLite + WAL pragma |
| `meeting_notes.py` | Заметки совещаний |

### Краны и остатки (2)
| Файл | Что делает |
|---|---|
| `taps_manager.py` | CRUD 60 кранов, atomic-write через tmp+fsync+replace |
| `expiry_recommend.py` | `classify_tier()` + `recommend()` для Shelf-Life Cockpit |

### Шедулеры и боты (5)
| Файл | Что делает |
|---|---|
| `chz_scheduler.py` | Daemon-thread, ЧЗ refresh в 03:00 МСК + atomic lock |
| `open_check_scheduler.py` | Daemon-thread, open-check в 14:59 МСК + atomic lock |
| `open_check_bot.py` | Логика проверки + форматирование |
| `open_check_telegram.py` | Telegram Bot API sync через requests, inline-меню |
| `open_check_subscribers.py` | Хранилище подписок (portalocker) |

### Конфиг и утилиты (5+)
| Файл | Что делает |
|---|---|
| `venue_config.py` | 4 канонических бара + маппинги имён OLAP/UI |
| `storage_paths.py` | Единый paths-helper (`PERSISTENT_DATA_DIR=/kultura`) |
| `weeks_generator.py` | Генератор недель для UI-селектора |
| `export_manager.py` | Экспорт XLSX |

---

## `routes/` — Flask blueprints (11)

Регистрация в [routes/__init__.py](../routes/__init__.py).

| Blueprint | URL-префикс | Файл |
|---|---|---|
| `pages_bp` | `/` | `pages.py` |
| `analysis_bp` | `/api` | `analysis.py` |
| `dashboard_bp` | `/api` | `dashboard.py` |
| `employee_bp` | `/api` | `employee.py` |
| `taps_bp` | `/api` | `taps.py` |
| `stocks_bp` | `/api` | `stocks.py` |
| `schedule_bp` | `/api` | `schedule.py` |
| `misc_bp` | `/api` | `misc.py` |
| `expiration_bp` | `/api` | `expiration.py` |
| `explorer_bp` | `/`, `/api` | `explorer.py` |
| `open_check_bp` | `/api`, `/telegram/openbot` | `open_check.py` |

`menu_bp` вынесен в [menu_tool/](../menu_tool/) как отдельное локальное приложение на порту 5050 — в прод не регистрируется.

---

## `templates/` — Jinja2 HTML

```
templates/
├── dashboard.html       # Главная: 4 точки + Общая, 15 метрик, AI
├── employee.html        # Дашборд сотрудника, KPI, бонусы
├── taps_bar.html        # Краны одного бара
├── stocks.html          # 4 вкладки: Сводный заказ / Таплист / Фасовка / Сроки
├── expiration.html      # Shelf-Life Cockpit
├── explorer.html        # Конструктор отчётов
├── schedule.html, salary.html, bonus.html
├── packaging.html, draft.html, discounts.html, waiters.html
├── wiki.html            # Встроенная wiki с TOC
├── pwa-widget.html      # PWA виджет выручки
├── dashboard/           # Подшаблоны главного дашборда (plans_tab, comparison_tab, ...)
└── shared/
    └── nav.html         # Общая навигация sidebar + topbar
```

---

## `static/`

```
static/
├── js/
│   ├── dashboard/
│   │   ├── core/        # state.js (singleton), api.js, utils.js
│   │   └── modules/     # analytics, charts, trends, plans, comparison, ai_insights, ... (15+)
│   ├── employee/
│   ├── taps/
│   └── stocks/
├── css/
└── pwa/                 # manifest.webmanifest, sw.js
```

---

## `data/` — Состояние (persistent в проде)

```
data/
├── plansdashboard.json     # Месячные планы (16 метрик × venue × period_key)
├── daily_plans.json        # Ежедневные планы (авто, Пт/Сб = weight 2x)
├── kpi_targets.json        # KPI цели
├── taps_data.json          # 60 кранов + история (atomic-write)
├── meeting_notes.json      # Заметки совещаний
├── open_check_subscribers.json   # Telegram-подписки open-check
├── nomenclature_cache.json # iiko nomenclature (24ч диск + 15 мин память)
├── olap_all_fields.json    # Справочник OLAP-полей
├── beer_report.json, kegs_products.json, keg_mapping.json
├── cache/
│   ├── nomenclature__products.xml   # iiko /products (баркоды → ЧЗ)
│   ├── nomenclature_full.json       # OLAP nomenclature
│   ├── kitchen_report.json, store_operations_report.json
│   └── ...
└── .chz_refresh_lock_*, .open_check_lock_*   # Atomic locks от шедулеров
```

**Persistence на Selectel:** docker volumes — `/srv/beer/data → /app/data` и `/srv/beer/chz_debug → /app/chz_test/debug`. На локальном dev — обычная директория. Маршрутизация — через [core/storage_paths.py](../core/storage_paths.py).

---

## `menu_tool/` — Standalone Flask :5050

```
menu_tool/
├── app.py                # Flask на 127.0.0.1:5050
├── menu_routes.py        # Blueprint: страницы, CRUD, PDF/PNG-рендер
├── templates/
│   ├── menu.html         # Редактор: форма + переключатель A/B + превью
│   ├── menu_library.html # Таблица всех карточек + поиск
│   └── menu_card.html    # Шаблон одной A4-карточки
├── data/
│   ├── menu_items.json   # Источник истины — все карточки
│   └── menu_settings.json # { "variant": "v2" | "v3" }
├── requirements.txt      # flask + playwright
└── README.md             # Документация инструмента
```

Не деплоится на прод (Chromium-рендер ест ~150-200 МБ).

---

## `chz_test/` — ЧЗ-клиент + утилиты

```
chz_test/
├── chz.py                # CHZ-клиент: auth, dispenser API, парсер CSV, CLI
├── probe_gtin.py         # Поиск GTIN во всех 13 product-группах ЧЗ
├── suggest_barcode_fixes.py  # Авто-подбор настоящих GTIN для несматченных
├── export_bartender_list.py  # CSV-список для барменов на сверку DataMatrix
└── debug/
    ├── chz_stock.json    # Кеш ЧЗ (обновляется через POST /api/chz/refresh)
    ├── mods.json         # Справочник МОД (КПП ↔ адрес)
    ├── pg{15,22,23}_csv/ # Скачанные CSV из dispenser API (ZIP)
    ├── token.json        # ЧЗ-токен (~10 часов)
    ├── refresh.log       # Лог последнего refresh
    └── refresh.lock      # Cross-worker lock для /api/chz/refresh
```

CLI запускается **только на бар-ПК** с CryptoPro CSP + Rutoken. На сервере — через SSH (`remote_exec.py`).

---

## `docs/` — Документация (SoT)

```
docs/
├── overview.md              # Архитектура (читать первым)
├── PROJECT_STRUCTURE.md     # Этот файл
├── CHANGELOG.md             # История сессий
├── lessons.md               # Баги, паттерны
│
├── dashboard.md, employee.md, taps.md, stocks.md, venues-plans.md, schedule.md
├── abc-xyz-analysis.md, draft-beer-errors.md, draft-beer-fixes.md, discounts.md
├── explorer.md, expiration.md, chz-stock-integration.md, open-check-bot.md
├── iiko-integration.md, frontend.md, design-system.md
├── remote-sync.md, CONNECTIVITY.md, ralphex-guide.md
├── employee-dashboard-presentation.md, salary-instruction.txt
│
├── guides/                  # Человеко-ориентированные инструкции
│   ├── DEPLOYMENT_GUIDE.md (legacy Render)
│   ├── BACKUP_SETUP.md, RENDER_DISK_SETUP.md (legacy)
│   ├── TAPS_*.md            # TAPS_MANAGEMENT, TAPS_QUICK_START, TAPS_README, ...
│   ├── TELEGRAM_BOT_GUIDE.md, TROUBLESHOOTING.md
│   └── ИНСТРУКЦИЯ_ДЛЯ_БАРМЕНОВ.md
│
├── technical/               # Технические справочники
│   ├── IIKO_API_REFERENCE.md
│   ├── MAPPING_*.md         # MAPPING_DATA_FLOW, MAPPING_HANDLING_DIFFERENCES, MAPPING_SYSTEM_GUIDE
│   ├── CODE_ANALYSIS_COMPLETE.md
│   ├── DOCUMENTATION_OVERVIEW.md
│   ├── SYNC_FLOW_VISUAL.md
│   └── audits/
│
├── changelog/               # Исторические фиксы (заморожены)
│   ├── BEER_SHARE_CALCULATION_BUG.md
│   ├── BOTTLES_FILTERING_SOLUTION.md
│   ├── CHANGELOG_FIXES.md, CHANGELOG_STOCKS_FILTERING.md
│   ├── CHZ_INTEGRATION.md
│   ├── CRITICAL_FIXES_SUMMARY.md
│   ├── DASHBOARD_FIX_REPORT.md, DASHBOARD_NOTES.md
│   ├── FINAL_DIAGNOSIS.md, FIX_DATE_HANDLING.md
│
├── iiko-api/                # iiko API спецификации
│   ├── md/                  # Markdown версии
│   └── pdf/                 # PDF версии
│
├── plans/                   # Старые ТЗ (статус DONE/IN PROGRESS)
├── planning/                # Архитектурные заметки
├── external/                # Внешние документы
└── archive/                 # Старая документация
```

---

## `.claude/` — Принципы и индекс

```
.claude/
├── CLAUDE.md                # Принципы проекта (читать первым агентам)
├── INDEX.md                 # Индекс документации (карта по docs/)
├── context.md               # Быстрый контекст для Claude
├── settings.local.json      # Локальные настройки harness
├── agents/                  # Custom subagents (опционально)
├── agent-memory/            # Заметки агентов
├── skills/                  # Skill-определения
└── docs/                    # MOVED — модули переехали в корневой docs/ (остались stub'ы)
```

---

## `scripts/` — Вспомогательные скрипты

```
scripts/
├── debug/                   # debug_<bar>_<feature>.py
├── check/                   # check_*.py — проверка данных
├── analysis/                # analyze_*, calculate_*, search_*
└── maintenance/             # backup.bat, daily_update_mapping.bat, convert_pdf_to_md.py
```

> `scripts/import_export/` удалён в 2026-05-15 (Excel-импорт планов заменён UI-only редактированием).

---

## Важные файлы конфигурации

| Файл | Описание |
|------|----------|
| `.env` | Переменные окружения (секреты, не в git) |
| `.env.example` | Пример .env с описанием всех переменных |
| `.gitignore` | Игнорируемые файлы (test_*.json, .chz_lock, и т.д.) |
| `Dockerfile`, `docker-compose.yml`, `Caddyfile` | **Актуальный** деплой на Selectel VPS |
| `render.yaml`, `docs/guides/RENDER_DISK_SETUP.md` | **Legacy** Render-деплой (rollback-страховка) |
| `.python-version` | Версия Python для pyenv |

---

## Запуск

### Локально (dev)
```bash
pip install -r requirements.txt
python app.py    # http://127.0.0.1:5000
```

### Production (Selectel)
```bash
docker compose up -d
# Caddy слушает 80/443, проксирует на gunicorn:8000
```

---

## Основные URL (production)

| URL | Назначение |
|---|---|
| `/` | Дашборд План/Факт |
| `/packaging`, `/draft` | ABC/XYZ-анализ |
| `/explorer` | Конструктор отчётов |
| `/taps/<bar_id>` | Управление кранами |
| `/stocks` | Остатки + Сводный заказ |
| `/expiration` | Shelf-Life Cockpit |
| `/employee`, `/salary`, `/bonus`, `/schedule` | Сотрудники |
| `/discounts`, `/waiters` | Анализ |
| `/wiki` | Встроенная wiki |
| `/api/*` | JSON API |
| `/telegram/*`, `/telegram/openbot/*` | Telegram webhooks |
