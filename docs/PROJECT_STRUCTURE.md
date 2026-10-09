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
├── core/                   # Бизнес-логика (63 модуля)
├── routes/                 # Flask blueprints (11 файлов)
├── templates/              # Jinja2 HTML
├── static/                 # CSS, JS, PWA
├── data/                   # Кеши и состояние (mounted persistent в проде)
├── resources/              # Проверенные справочные данные в образе (не перекрываются диском /app/data):
│                           # реестр Untappd, кухонное меню, снимки каталога OLAP-полей конструктора
│                           # (olap_all_fields / olap_transactions_fields / olap_stock_fields.json)
├── menu_tool/              # Standalone Flask :5050 для печати меню A4 (Playwright)
├── chz_test/               # ЧЗ-клиент + утилиты отладки
├── mapping/                # Маппинг блюд на кеги (CSV)
├── utils/                  # Утилиты маппинга
├── scripts/                # Вспомогательные скрипты (debug, check, maintenance)
├── tests/                  # Тесты (pytest + node *.mjs; раздел «Гости»: test_content_plan.py,
│                           #   test_content_brief.py, test_content_image_search.py (+ image_search_fakes.py),
│                           #   test_guest_reviews.py, test_content_plan_render.mjs,
│                           #   test_reviews_render.mjs, test_guest_hub_render.mjs; MCP: test_mcp_protocol.py,
│                           #   test_mcp_bridge.py, test_mcp_tokens.py, test_mcp_oauth.py, test_mcp_coverage.py,
│                           #   test_mcp_docs_allowlist.py, test_mcp_modes.py,
│                           #   test_mcp_tools_{content,stocks,analytics,staff}.py,
│                           #   test_mcp_admin_render.mjs, test_mcp_narrowing.py, test_mcp_eval.py +
│                           #   mcp_eval_questions.json (эталонные вопросы к агенту);
│                           #   отправка и бот: test_content_publisher.py, test_guest_subscribers.py,
│                           #   test_taplist_polling.py, test_review_notify.py; отзывы с Яндекс Карт:
│                           #   test_yandex_maps_reviews.py, test_yandex_reviews_sync.py,
│                           #   test_yandex_reviews_watchdog.py; старые ошибки:
│                           #   test_dashboard_comments.py, test_dashboard_compare_export.py,
│                           #   test_msk_today_routes.py, test_schedule_employee_update.py,
│                           #   test_docs_secrets_moved.py; приёмка на РЦ: test_receiving_*.py,
│                           #   test_receiving_*.mjs, fixtures/receiving_codes.json (паритет Python/JS);
│                           #   conftest.py — пустые боевые токены
│                           #   для каждого прогона pytest)
├── docs/                   # Документация проекта (SoT)
├── secrets/                # ТОЛЬКО локально (в .gitignore и .dockerignore): LOCAL_NOTES.md —
│                           #   пароли и токены, вынесенные из документов 2026-09-28
├── .claude/                # Принципы + индекс для агентов
├── memory/                 # Persistent-память (auto-managed)
├── knowledge_graph/        # MCP knowledge graph
├── archive/                # Архив legacy-кода
├── _archive_to_delete/     # Выведенный код на удаление владельцем (не в Docker-образе; README внутри)
│
├── Dockerfile              # Production-сборка (Selectel VPS)
├── docker-compose.yml      # Сервис gunicorn (--workers 2) + Caddy
├── Caddyfile               # Reverse proxy + TLS для beerkultura.ru
└── render.yaml             # (legacy) Render.com — rollback-страховка
```

---

## `core/` — Бизнес-логика (71 модуль)

### iiko-интеграция и данные (4)
| Файл | Что делает |
|---|---|
| `iiko_api.py` | Auth (SHA-1), cashshifts v2, attendance, POS-mapping |
| `olap_reports.py` | OLAP v2 (all_sales, beer, draft, kitchen), nomenclature, store_balances, store_operations |
| `iiko_barcodes.py` | Парсер XML `/products` → `{gtin14: [iiko_pid]}` для стыковки с ЧЗ |

### Аналитика (14)
| Файл | Что делает |
|---|---|
| `dashboard_analysis.py` | 19 из 20 метрик дашборда (в т.ч. чеки с картой лояльности / без карты; активность кранов — в routes/dashboard.py) |
| `dashboard_details.py` | **Детали внутри карточки** дашборда: реестр «метрика -> секции» и чистые функции над строками единого OLAP-запроса (дни, бары, категории, топ позиций, локал/импорт, гости), секции «Литры» и «Краны» |
| `draft_loader.py` | Общий загрузчик сырья `/draft` (`load_draft_kegs`: проводки кегов + продажи + техкарты под одним ключом кэша) — для страницы и для карточек розлива |
| `packaging_loader.py` | Общий загрузчик сырья `/packaging` (`load_packaging`: продажи с `DishId` + проводки склада группы «Напитки Фасовка» под одним ключом кэша, `fetched_at` для чипа «обновлено») |
| `packaging_analysis.py` | **ABC/XYZ фасовки** для `/packaging`: сведение баров в «Общую», ABC по выручке и марже, наценка от сумм, XYZ по недельным окнам, все категории, решения по ассортименту; вызывает блок потерь |
| `kitchen_loader.py` | Загрузчик сырья `/kitchen` (`load_kitchen`: продажи группы «ЕДА» + проводки склада кухни в рублях под одним ключом кэша) |
| `kitchen_analysis.py` | **ABC/XYZ кухни** для `/kitchen`: наследник `PackagingAnalysis` — те же формулы, пороги наценки 180/150, категория «третий уровень, иначе второй», соусы-модификаторы отдельно |
| `kitchen_losses.py` | **Баланс и потери кухни в рублях** по закупке: продукты и ингредиенты группы «ЕДА», недостача по барам, сверка «касса против склада» с долей покрытия |
| `packaging_losses.py` | **Баланс и потери фасовки в штуках**: приход, перемещения, продано, акты, недостача, изменение остатка по формуле кегов; связка товар — позиция по GUID или имени, диагностика отброшенного |
| `abc_thresholds.py` | Пороги ABC/XYZ и подписи одним местом (Парето 80/95, наценка 1.2/1.0 у фасовки и 2.5/2.0 у кегов, CV 30/60, минимум 3 недели) и константы решений по ассортименту (минимум 5 продаж, 28 дней для «вывести», пол наценки 0.5 порога B) |
| `abc_buckets.py` | **Решения по ассортименту** для `/packaging` и `/draft`: шесть групп по правилам с защитой от малых выборок (сверить учёт, новинки, мало продаж, слабые продажи, низкая наценка, основа выручки), карточки групп с правилом словами |
| `draft_kegs.py` | **Проливы** для `/draft`: литры из проводок iiko, деньги из продаж, связка и объём порции через техкарты, разрез по барменам |
| `draft_analysis.py` | Разливное по названиям блюд (2-этапная нормализация) — месячный отчёт, меню, скрипты |
| `trends_analyzer.py` | Тренды по неделям |
| `comparison_calculator.py` | Сравнение двух периодов для `POST /api/comparison/periods` теми же числами, что карточки дашборда (Δ, Δ%, п.п.) |
| `revenue_metrics.py` | Единая точка чтения метрик выручки |
| `olap_constructor.py` | Конструктор OLAP-отчётов: заявка, тела запросов, план, сводная и список с итогами |
| `olap_catalog.py` | Каталог полей OLAP iiko: живой `/columns`, запасные копии, правило итогов, запреты, коды |
| `olap_client.py` | Доступ конструктора к iiko: сессия, ошибки iiko текстом, 2 запроса одновременно, кэш |
| `olap_export.py` | Excel конструктора: «Отчёт», «Данные», «Параметры» |
| `olap_saved_reports.py` | Сохранённые отчёты конструктора (`explorer_reports.json`) |

### Сотрудники, ЗП и планы (11)
| Файл | Что делает |
|---|---|
| `employee_analysis.py` | Метрики по AuthUser, word-set matching имён |
| `employee_plans.py` | KPI-каталог, **BAR_NAME_MAPPING** (cashshifts vs OLAP) |
| `kpi_calculator.py` | KPI бонусы |
| `plans_manager.py` | CRUD планов + **portalocker** cross-worker; `PLAN_DEFAULTS` (cardChecksShare 70%), `fill_missing_defaults`, `BUDGET_METRICS`/`plan_score`; `PeriodCommentsStore` — комментарии к периодам дашборда отдельно от планов (`period_comments.json`, с 2026-09-28) |
| `shifts_manager.py` | SQLite + WAL pragma |
| `meeting_notes.py` | Заметки совещаний |
| `order_store.py` | Заказы поставщикам: общий черновик, статусы, «в пути», сверка с накладными iiko, текст для чата |
| `supplier_calendar.py` | Календарь поставок: ожидаемая дата без сб/вс, горизонт, допуск задержки |
| `supplier_directory.py` | Справочник поставщиков: написания, срок и дни доставки, кратность, самовывоз, минимальный заказ в рублях (suppliers.json) |
| `purchase_price.py` | Цена единицы для суммы заказа: последняя приходная накладная, иначе себестоимость остатка |
| `salary_payload.py` | Серверная сборка payload расчёта ЗП (зеркало страницы) |
| `salary_layout.py` | Раскладка листа ЗП: строки, формулы, порядок колонок |
| `salary_export.py` | Рендерер раскладки в .xlsx (openpyxl) |
| `salary_gsheet.py` | Рендерер раскладки в Google Таблицу (Sheets API) |
| `cash_register.py` | Регистр «Касса за месяц»: строки, пробелы кассы, ₽ -> копейки, `opening_shifts()` — кто открывающая смена дня |
| `bar_acceptance.py` | **Приёмка бара** «Как принял бар?»: правила ответа, окно, сборка журнала месяца |
| `bar_photo_store.py` | Фото приёмки на диске: имя, проверка сигнатуры JPEG, атомарная запись |

### Раздел «Гости» (11)
| Файл | Что делает |
|---|---|
| `content_plan.py` | **Контент-план**: материалы и размещения, готовность, сводка, утверждение, пауза, сдвиг, повтор, копирование месяца, живые данные таплиста, журнал (`content_plan.json`); ИИ-агент: `origin`, «Почему этот пост», «Что снять», черновики ИИ; состояние отправки `delivery` размещений — [content-plan.md](content-plan.md) |
| `content_channels.py` | **Каналы и отправка** (с 2026-09-28): канал Telegram каждого бара с проверкой, чат напоминаний об Instagram, главный выключатель, выключатели рассылок и кнопок подписки в боте, «что подключено» (`content_channels.json`; всё выключено по умолчанию) — [content-plan.md](content-plan.md) |
| `content_publisher.py` | **Отправка публикаций** (с 2026-09-28): `publish_due` — пост в канал бара, напоминание об Instagram, рассылка подписчикам бота; «отправляется» под блокировкой плана, без дублей (`safe_resend`), проверка канала и тестовое сообщение, zip для Instagram — [content-plan.md](content-plan.md) |
| `guest_subscribers.py` | **Подписчики гостевого бота** (с 2026-09-28): согласие с версией текста, бары, телефон (канон — только российские формы), сегменты рассылки, шаги диалога бота (`guest_subscribers.db`) — [guides/TELEGRAM_BOT_GUIDE.md](guides/TELEGRAM_BOT_GUIDE.md) |
| `content_brief.py` | **Бриф сети для ИИ-агента** контент-плана: разделы, бары, примеры, пределы, слияние правок, затравка (`content_brief.json`) — [content-plan.md](content-plan.md), раздел «ИИ-агент» |
| `content_media.py` | Фото и видео контент-плана на диске: имя `cp_<дата>_<12 hex>`, проверка сигнатуры, атомарная запись (`content_media/`) |
| `content_image_search.py` | **Картинки к постам** (с 2026-10-02): поиск через Yandex Search API, отбор, поиски на диске (`content_image_search/`, 3 суток), коллаж вариантов для агента, безопасное скачивание, JPEG для Telegram — [content-plan.md](content-plan.md), раздел «Картинки к постам» |
| `guest_reviews.py` | **Отзывы гостей**: хранилище, проверка полей, статусы, метрики и формулы, слой календаря (`guest_reviews.json`) — [reviews.md](reviews.md) |
| `yandex_maps_reviews.py` | **Отзывы с публичной страницы Яндекс Карт** (без входа): страница `/maps/org/<id>/reviews/`, разбор JSON страницы и отзыва, листание `?page=N`; общие заголовки и признаки капчи страниц Карт — [yandex-reviews.md](yandex-reviews.md) |
| `yandex_reviews_sync.py` | Загрузка отзывов с Карт в «Отзывы»: быстрая проверка (первая страница) и полный проход, защита от дублей, состояние `yandex_reviews_sync.json` — [yandex-reviews.md](yandex-reviews.md) |
| `yandex_reviews_scheduler.py` | Такт 15 минут: проверка раз в 3 часа, полный проход в 08:30 МСК, затем сторож |
| `yandex_reviews_watchdog.py` | Сторож отзывов: сообщение в Telegram, если не обновлялись больше суток или на Картах больше отзывов дольше 6 часов |
| `yandex_business.py` | Клиент кабинета Яндекс Бизнеса (только чтение): для загрузки с 2026-10-09 не используется, остаётся для диагностики и будущего ответа из сервиса — [yandex-reviews.md](yandex-reviews.md) |
| `review_notify.py` | Новые отзывы — подписчикам бота kulturaopenclosed: из Яндекса — после каждой проверки Карт; из гостевого бота — сразу, только бар, оценка, дата и ссылка, не больше 20 в час, подбор пропущенных раз в 10 минут; сообщения сторожа (`notify_subscribers`) |

### Краны и остатки (2)
| Файл | Что делает |
|---|---|
| `taps_manager.py` | CRUD 60 кранов, atomic-write через tmp+fsync+replace |
| `expiry_recommend.py` | `classify_tier()` + `recommend()` для Shelf-Life Cockpit |

### Приёмка на РЦ (7, с 2026-10-03, [receiving.md](receiving.md))
| Файл | Что делает |
|---|---|
| `receiving_codes.py` | Разбор кода со сканера: DataMatrix ЧЗ, EAN/UPC, SSCC, кириллическая раскладка, контрольная цифра GS1 (JS-порт — `static/js/receiving/codes.js`) |
| `receiving_index.py` | Свой индекс «GTIN → карточки iiko» с удалёнными и архивными (`receiving_index.json`): загрузка из iiko v2, статусы, похожая карточка, поиск, межпроцессный лок обновления |
| `receiving_chz.py` | Название по GTIN: кэш, `chz_stock.json`, `product-info` на бар-ПК по SSH |
| `receiving_store.py` | SQLite `receiving.db`: приёмки, сканы, фото накладных, строки разбора, кэш ответов ЧЗ |
| `receiving_photo_store.py` | Фото накладных на диске (`receiving_photos/`) |
| `receiving_service.py` | Обработка закрытой приёмки и обновление индекса с перепроверкой открытых строк |
| `receiving_notify.py` | Сообщение бухгалтерии в Telegram (бот kulturaopenclosed, чаты `RECEIVING_NOTIFY_CHAT_IDS`) |

### Шедулеры и боты (9)
| Файл | Что делает |
|---|---|
| `chz_scheduler.py` | Daemon-thread, ЧЗ refresh в 03:00 МСК + atomic lock |
| `receiving_scheduler.py` | Приёмка на РЦ: индекс iiko в 07:30 МСК (суточный лок), после старта, если индекса нет или он старше 26 ч; раз в 10 минут — подбор зависших обработок приёмок |
| `open_check_scheduler.py` | Daemon-thread, open-check в 14:59 МСК + atomic lock |
| `content_publisher_scheduler.py` | Daemon-thread, отправка контент-плана раз в минуту (hh:mm:01), один процесс (flock `data/.content_publisher.lock`); без токена бота и при `CONTENT_PUBLISH=0` не стартует |
| `taplist_polling.py` | Long-polling гостевого бота @kult_taplist_bot: краны, подписка на новости с согласием, отзывы, выключатель `bot.signup` и меню команд |
| `open_check_bot.py` | Логика проверки + форматирование |
| `open_check_telegram.py` | Telegram Bot API sync с обходом блокировок (`api_call`, файлы — `api_call_files`; `safe_resend` — запасной путь только при доказанном «не ушло»), меню подписки (кнопка) + команды /start /status |
| `open_check_subscribers.py` | Хранилище самоподписавшихся чатов (единый список, portalocker) |
| `open_check_polling.py` | Long-polling getUpdates (входящие команды/кнопки) |

### Конфиг и утилиты (5+)
| Файл | Что делает |
|---|---|
| `venue_config.py` | 4 канонических бара + маппинги имён OLAP/UI |
| `storage_paths.py` | Единый paths-helper (`PERSISTENT_DATA_DIR=/kultura`) |
| `weeks_generator.py` | Генератор недель для UI-селектора |
| `export_manager.py` | Экспорт XLSX |

### MCP-платформа — `core/mcp/` (с 2026-09-27, [mcp.md](mcp.md))
| Файл | Что делает |
|---|---|
| `mcp/__init__.py` | Обзор пакета и карта файлов |
| `mcp/db.py` | SQLite `mcp.db` на постоянном диске: `read()`, `write()` (`BEGIN IMMEDIATE`), `ensure_schema()` |
| `mcp/principal.py` | `Principal` — кто вызывает: владелец, токен, клиент, разделы токена |
| `mcp/spec.py` | `ToolSpec` (пометки `draft_write`, `owner_notice`), `PromptSpec` (`mode_required`), `DOMAINS`, режимы доступа `MODES` (`allowed_in_mode`, `prompt_allowed_in_mode`, `stricter_mode`), статическая проверка описаний |
| `mcp/registry.py` | Сбор инструментов по разделам, видимость по коннекторам, инструкции агентам, исключения |
| `mcp/protocol.py` | JSON-RPC и методы MCP двух эпох (2026-07-28 и `initialize`), режим подключения (строже из адреса и токена), проверки HTTP, лимиты частоты и одновременности (с 2026-09-28 — общие для воркеров, в `mcp.db`), журнал |
| `mcp/bridge.py` | Мост: тот же Flask-маршрут от имени владельца (`via_mcp`, `mcp_mode`), сверка пути с картой маршрутов, упаковка ответа, обрезание 60 000, семафор тяжёлых, кэш тяжёлых чтений на 5 минут |
| `mcp/schema_check.py` | Проверка аргументов по JSON Schema с русскими сообщениями |
| `mcp/auth.py` | Проверка `Authorization: Bearer`: статический токен или OAuth, активный админ, раздел |
| `mcp/tokens.py` | Статические токены для Claude Code (`kmcp_…`, sha256, режим доступа), `revoke_all_for_user` |
| `mcp/oauth.py` | OAuth 2.1 для приложения Claude и расписаний: DCR с пределами, PKCE S256, привязка к коннектору с режимом, режим гранта, ротация, `revoke_all_for_user` |
| `mcp/settings.py` | Настройки: чат Telegram для отчётов агентов, разрешённые хосты OAuth |
| `mcp/audit.py` | Журнал вызовов инструментов: отказы хранятся отдельно, история не моложе 180 дней не удаляется |
| `mcp/coverage.py` | Правило покрытия: каждый API-маршрут — инструмент или исключение; `py -3 -m core.mcp.coverage` |
| `mcp/tools/__init__.py` | Что экспортирует модуль раздела: `TOOLS`, `PROMPTS`, `INSTRUCTIONS`, `EXCLUDED` |
| `mcp/tools/common.py` | Общие инструменты (`common_*`), `DOCS_ALLOWLIST` (документы для агентов = `.dockerignore`), общие правила агентов, исключения служебных маршрутов |
| `mcp/tools/content.py`, `stocks.py`, `analytics.py`, `staff.py` | Описания инструментов, правила и сценарии разделов |

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
| `orders_bp` | `/api/orders` | `orders.py` |
| `suppliers_bp` | `/api/suppliers` | `suppliers.py` |
| `receiving_bp` | `/receiving`, `/receiving/review`, `/api/receiving` | `receiving.py` |
| `schedule_bp` | `/api` | `schedule.py` |
| `misc_bp` | `/api` | `misc.py` |
| `expiration_bp` | `/api` | `expiration.py` |
| `explorer_bp` | `/`, `/api` | `explorer.py` |
| `open_check_bp` | `/api`, `/telegram/openbot` | `open_check.py` |
| `me_bp` | `/me`, `/api/me` | `me.py` |
| `cleanliness_bp` | `/cleanliness`, `/api/cleanliness` | `cleanliness.py` |
| `content_plan_bp` | `/content-plan`, `/api/content-plan` | `content_plan.py` |
| `reviews_bp` | `/reviews`, `/api/reviews`, `/api/guest-hub/attention` | `reviews.py` |
| `mcp_bp` | `/mcp[/<раздел>][/read\|/draft]` (коннекторы MCP), `/admin/mcp`, `/api/admin/mcp/*` | `mcp.py` |
| `mcp_oauth_bp` | `/.well-known/oauth-*`, `/oauth/register`, `/oauth/authorize`, `/oauth/token`, `/oauth/revoke` | `mcp_oauth.py` |

`menu_bp` вынесен в [menu_tool/](../menu_tool/) как отдельное локальное приложение на порту 5050 — в прод не регистрируется.

---

## `templates/` — Jinja2 HTML

```
templates/
├── dashboard.html       # Дашборд /dashboard: 4 точки + Общая, 17 карточек (20 метрик в API), AI
├── employee.html        # Дашборд сотрудника, KPI, бонусы
├── taps_bar.html        # Краны одного бара
├── stocks.html          # 6 вкладок: К заказу / К отправке / Таплист / Фасовка / Сроки / Меню кухни
├── suppliers.html       # Справочник поставщиков (/suppliers)
├── receiving.html       # Приёмка на РЦ: экран приёмщика (/receiving)
├── receiving_review.html # «Разбор приёмок» для бухгалтерии (/receiving/review)
├── expiration.html      # Shelf-Life Cockpit
├── explorer.html        # Конструктор OLAP-отчётов iiko (/explorer)
├── schedule.html, salary.html, bonus.html
├── packaging.html, draft.html   # draft.html: кеги + бармены (waiters.html удалён)
├── kitchen.html         # «Кухня»: клон packaging.html (стили фасовки, id kt*)
├── wiki.html            # Встроенная wiki с TOC
├── pwa-widget.html      # PWA виджет выручки
├── guests.html          # «Маркетинг» (/guests), вверху полоса раздела «Гости»
├── content_plan.html    # «Контент-план» (/content-plan): фильтры, таблица, календарь, карточка, диалоги
├── reviews.html         # «Отзывы» (/reviews): фильтры, показатели, список, диалог отзыва
├── admin_mcp.html       # «Доступ агентов» (/admin/mcp, только админ): коннекторы, токены, OAuth, журнал, настройки
├── mcp_consent.html     # Страница согласия OAuth для MCP (и «нет доступа», «подключение не удалось»)
├── dashboard/           # Подшаблоны главного дашборда (plans_tab, comparison_tab, ...)
└── shared/
    ├── nav.html               # Общая навигация sidebar + topbar (секция «Гости»)
    ├── guest_hub_head.html    # Шапка раздела «Гости» (бургер, заголовок) + полоса
    └── guest_hub_strip.html   # Вкладки раздела и полоса «Требует внимания»
```

---

## `static/`

```
static/
├── js/
│   ├── dashboard/
│   │   ├── core/        # state.js (singleton), api.js, utils.js
│   │   └── modules/     # analytics, charts, trends, plans, comparison, ai_insights, ... (15+)
│   ├── draft/           # draft.js — весь экран «Розлив — ABC/XYZ и потери»
│   ├── packaging/       # packaging.js — весь экран «Фасовка — ABC/XYZ и потери»
│   ├── kitchen/         # kitchen.js — «Кухня — ABC/XYZ и потери», клон packaging.js
│   ├── explorer/        # конструктор OLAP: page.js (поля, зоны, фильтры, сохранение), grid.js (сводная), cube.js (3D-куб — схема раскладки)
│   ├── shared/          # общие блоки страниц: kpi_breakdown.js, abc_view.js (вкладки /draft, /packaging, /kitchen)
│   ├── employee/
│   ├── guests/          # «Маркетинг»; views-guest.js подставляет ?q= в поиск гостя
│   ├── guest_hub/       # раздел «Гости»: common.js (window.GH, полоса), content_plan.js, reviews.js
│   ├── admin_mcp.js     # страница «Доступ агентов» (/admin/mcp)
│   ├── me/
│   ├── schedule/
│   ├── taps/
│   ├── receiving/       # codes.js (разбор кода, паритет с core/receiving_codes.py), scan.js (/receiving), review.js (/receiving/review)
│   └── stocks/
├── draft/               # draft.css — оформление /draft по макету (токены --dr-*)
├── packaging/           # packaging.css — оформление /packaging как /draft (токены --pk-*)
├── explorer/            # explorer.css — конструктор отчётов (токены --ex-*, тёмная тема)
├── shared/              # kpi_breakdown.css, abc_view.css (цвета — токены страницы)
├── me/                  # me.css — оформление /me по макету (токены --me-*)
├── guest_hub/           # hub.css (токены --gh-* на .gh-scope, тёмная тема), content_plan.css, reviews.css
├── admin_mcp.css        # стили страницы «Доступ агентов» (только токены цвета)
├── receiving/           # scan.css (токены --rc-*), review.css (токены --rv-*)
├── fonts/               # IBM Plex Mono (ttf) + IBM Plex Sans (woff2, субсеты)
├── libs/                # свои копии библиотек: chart.umd.min.js, flexidatepicker, barcode-detector-2.3.1/ (полифил BarcodeDetector + zxing_reader.wasm — камера /receiving на iPhone)
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
├── orders.json             # Заказы поставщикам: черновик + история (на проде /kultura, в git нет)
├── suppliers.json          # Справочник поставщиков (на проде /kultura, в git нет; без файла — стартовый набор из кода)
├── content_plan.json       # Контент-план: материалы, размещения, журнал (на проде /kultura, в git нет)
├── content_media/          # Фото и видео контент-плана cp_<дата>_<hex>.<ext> (на проде /kultura, в git нет)
├── guest_reviews.json      # Отзывы гостей (на проде /kultura, в git нет)
├── content_brief.json      # Бриф сети для ИИ-агента контент-плана (на проде /kultura, в git нет)
├── content_channels.json   # «Каналы и отправка» контент-плана: каналы баров, выключатели (на проде /kultura, в git нет)
├── guest_subscribers.db    # Подписчики гостевого бота и шаги его диалога, SQLite WAL (на проде /kultura, в git нет)
├── period_comments.json    # Комментарии к периодам дашборда (на проде /kultura, в git нет)
├── mcp.db                  # MCP: токены, OAuth, журнал вызовов, настройки, общие лимиты (на проде /kultura, в git нет)
├── receiving.db            # Приёмка на РЦ: приёмки, сканы, разбор, кэш ЧЗ, SQLite WAL (на проде /kultura, в git нет)
├── receiving_photos/       # Фото накладных r<id>_<время>_<hex>.jpg (на проде /kultura, в git нет)
├── receiving_index.json    # Индекс «GTIN → карточки iiko» и receiving_index_state.json (на проде /kultura, в git нет)
├── open_check_subscribers.json   # Самоподписавшиеся чаты open-check ({"chats":[...]})
├── nomenclature_cache.json # iiko nomenclature (24ч диск + 15 мин память)
├── olap_all_fields.json    # Справочник OLAP-полей продаж (снимок /columns 2025-10-18; конструктор читает копию в resources/)
├── beer_report.json, kegs_products.json, keg_mapping.json
├── cache/
│   ├── nomenclature__products.xml   # iiko /products (баркоды → ЧЗ)
│   ├── nomenclature_full.json       # OLAP nomenclature
│   ├── kitchen_report.json, store_operations_report.json
│   └── ...
└── .chz_refresh_lock_*, .open_check_lock_*, .content_publisher.lock,
    .receiving_index_lock_*, .receiving_index_run.lock, .receiving_chz.lock   # Atomic locks от шедулеров
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
    ├── refresh.lock      # Cross-worker lock для /api/chz/refresh (снимает обёртка по завершении)
    ├── refresh.pid       # pid обёртки текущего refresh (статус в любом worker'е)
    └── refresh.exit      # Код выхода последнего refresh (пишет обёртка)
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
├── dashboard.md, employee.md, taps.md, stocks.md, orders.md, suppliers.md, venues-plans.md, schedule.md
├── guests.md, content-plan.md, reviews.md   # раздел «Гости»
├── mcp.md                   # MCP-платформа: весь сервис для ИИ-агентов владельца
├── abc-xyz-analysis.md, draft-beer-errors.md, draft-beer-fixes.md, discounts.md
├── explorer.md, expiration.md, chz-stock-integration.md, open-check-bot.md
├── iiko-integration.md, frontend.md, design-system.md
├── remote-sync.md, CONNECTIVITY.md, ralphex-guide.md
├── employee-dashboard-presentation.md, salary-instruction.txt
│
├── guides/                  # Человеко-ориентированные инструкции
│   ├── mcp-connect.md       # Подключение ИИ-агентов владельца: токен, приложение Claude, агенты-роли, расписания
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
│                            # iiko-api/ удалена 2026-05-29 — спеки берём с портала
│                            # ru.iiko.help (см. .claude/CLAUDE.md)
├── plans/                   # Старые ТЗ (статус DONE/IN PROGRESS)
├── planning/                # Архитектурные заметки
├── external/                # Внешние документы
└── archive/                 # Старая документация
```

> В прод-образ и ИИ-агентам по MCP из `docs/` идут **только** документы явного списка
> `DOCS_ALLOWLIST` (`core/mcp/tools/common.py`), который повторяют строки `!docs/…` в
> `.dockerignore`: в служебных документах есть доступы, которые агенту видеть нельзя. Новый
> документ для агентов — в оба списка, без паролей и токенов (проверяет
> `tests/test_mcp_docs_allowlist.py`), см. [mcp.md](mcp.md), «Документация для агентов».

---

## `.claude/` — Принципы и индекс

```
.claude/
├── CLAUDE.md                # Принципы проекта (читать первым агентам)
├── INDEX.md                 # Индекс документации (карта по docs/)
├── context.md               # Быстрый контекст для Claude
├── settings.local.json      # Локальные настройки harness
├── agents/                  # Субагенты Claude Code: kultura-analyst.md, kultura-payroll.md,
│                            #   kultura-content.md — агенты-роли MCP (docs/guides/mcp-connect.md);
│                            #   signature-docs-analyst.md
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
├── maintenance/             # backup.bat, daily_update_mapping.bat, convert_pdf_to_md.py
├── fill_plan_defaults.py    # Проставить дефолты планов (cardChecksShare = 70) во все месяцы; --dry-run; на проде через docker exec
├── mcp_eval.py              # Эталонные вопросы к ИИ-агенту (tests/mcp_eval_questions.json): по умолчанию сухой план; --run — прогон через claude -p в режиме read (тратит токены подписки) — docs/mcp.md
├── yandex_maps_reviews_probe.py  # Проверка отзывов на публичных страницах Яндекс Карт: число, страницы, листание (только чтение) — docs/yandex-reviews.md
└── yandex_reviews_probe.py  # Диагностика кабинета Яндекс Бизнеса: вход, филиалы, последние отзывы (только чтение) — docs/yandex-reviews.md
```

> `scripts/import_export/` удалён в 2026-05-15 (Excel-импорт планов заменён UI-only редактированием).

---

## Важные файлы конфигурации

| Файл | Описание |
|------|----------|
| `.env` | Переменные окружения (секреты, не в git) |
| `secrets/LOCAL_NOTES.md` | Только на машине владельца (`secrets/` в `.gitignore` и `.dockerignore`): пароли, токен бота и реквизиты, вынесенные из документов 2026-09-28; в документах — ссылка на раздел этого файла |
| `tests/conftest.py` | Для каждого прогона pytest — пустые переменные, через которые код шлёт вовне (токены ботов, чаты, ключи Google, сессия Яндекса): `load_dotenv` при импорте иначе приносит боевые значения из `.env` |
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

> Внимание: `app.py` при импорте запускает все шедулеры и Telegram long-polling с токенами из
> `.env`. С боевыми токенами локально его не запускать и не импортировать — проверять
> отдельные blueprint'ы на голом Flask (см. [content-plan.md](content-plan.md) «Проверка
> локально», [lessons.md](lessons.md)).

### Production (Selectel)
```bash
docker compose up -d
# Caddy слушает 80/443, проксирует на gunicorn:8000
```

---

## Основные URL (production)

| URL | Назначение |
|---|---|
| `/` | 302 на `/me` — главная страница сайта |
| `/me` | Личный кабинет: своя смена, часы, KPI, деньги |
| `/dashboard` | Дашборд План/Факт |
| `/packaging`, `/draft` | «Фасовка» и «Розлив»: ABC/XYZ и потери (баланс склада в штуках / кегов в литрах) |
| `/kitchen` | «Кухня»: ABC/XYZ и потери группы «ЕДА», баланс склада в рублях по закупке |
| `/explorer` | Конструктор отчётов |
| `/taps/<bar_id>` | Управление кранами |
| `/stocks` | Заказы и остатки: экран «К заказу» |
| `/suppliers` | Справочник поставщиков |
| `/receiving`, `/receiving/review` | Приёмка на РЦ: сканирование (приёмщик) и «Разбор приёмок» (бухгалтерия) |
| `/content-plan`, `/reviews`, `/guests` | Раздел «Гости»: контент-план, отзывы, маркетинг |
| `/mcp`, `/mcp/<раздел>` | MCP-коннекторы для ИИ-агентов владельца (Bearer-токен или OAuth) |
| `/admin/mcp` | «Доступ агентов»: токены, OAuth-приложения, журнал вызовов, настройки (только админ) |
| `/expiration` | Shelf-Life Cockpit |
| `/employee`, `/salary`, `/bonus`, `/schedule` | Сотрудники |
| `/waiters` | 301 на `/draft#bartenders` (страница слита в «Розлив») |
| `/wiki` | Встроенная wiki |
| `/api/*` | JSON API |
| `/telegram/*`, `/telegram/openbot/*` | Telegram webhooks |
