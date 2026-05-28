# Changelog

### 2026-05-28 — Audit Selectel: надёжность под gunicorn --workers 2, atomic writes, lock-файлы

После миграции на Selectel под Docker (gunicorn `--workers 2`) выявлены и
устранены race-conditions и потенциальные коррупции данных, незаметные на Render
(где раньше шёл один worker). Аудит провёл отдельный подагент, валидацию —
третий. Все правки прошли `py_compile`, lock-папки фактически маунтятся
persistent-volume'ами (`/srv/beer/data → /app/data`,
`/srv/beer/chz_debug → /app/chz_test/debug`).

**Что:**
- `core/chz_scheduler.py` — добавлен ежедневный atomic lock-файл
  (`data/.chz_refresh_lock_YYYY-MM-DD`, `O_CREAT|O_EXCL`). Без него оба worker'а
  тикали в 03:00 и оба POST'или `/api/chz/refresh` → двойной refresh ЧЗ-API.
  Паттерн идентичен `open_check_scheduler.py`.
- `routes/stocks.py:796-858` — `/api/chz/refresh` получил cross-worker lock
  `chz_test/debug/refresh.lock` (atomic `O_EXCL`, stale-detection >30 мин).
  Прежний `_refresh_proc` был in-process переменной → два параллельных POST
  стартовали два `remote_exec.py csv-auto` с записью в один `refresh.log`.
- `core/shifts_manager.py:36-48` — на каждом коннекте `PRAGMA journal_mode=WAL`,
  `busy_timeout=5000`, `synchronous=NORMAL`. Под 2 worker'ами без WAL писатели
  блокировали друг друга и читателей `shifts.db`. SQLite автоматически
  конвертирует существующую БД при первом WAL-pragma.
- `core/taps_manager.py:113-143` — atomic write через tmp + `flush` + `fsync`
  + `os.replace`. Раньше при крэше worker'а в `json.dump` файл
  `/kultura/taps_data.json` оставался полу-записанным (битый JSON, при рестарте
  пустой таплист).
- `core/olap_reports.py:170-173` — `timeout=300` → `100` (gunicorn `--timeout 120`
  убил бы worker раньше; теперь fallback укладывается до SIGKILL).
- `telegram_webhook.py:18`, `telegram_bot.py:18` — убран хардкод-fallback токена
  `8261982160:AAFu...`. Раньше токен утекал в git и публичные форки. Теперь
  при отсутствии env поднимается `RuntimeError`, `extensions.py:74-86` ловит
  через try/except и выставляет `TELEGRAM_BOT_ENABLED=False`.
- `app.py:46-51` — `app.run(debug=True)` → `debug=os.environ.get('FLASK_DEBUG')`.
  Под gunicorn эта ветка не исполняется, но защита от случайного `python app.py`
  на сервере.
- `requirements.txt` — добавлены upper-bounds (`<3` / `<4`) для `portalocker`,
  `openpyxl`, `python-dateutil`, `paramiko`, `Markdown` — защита от breaking
  major-релизов.

**Почему:**
- gunicorn `--workers 2` запускает 2 процесса, каждый импортирует `app.py` →
  стартует свои daemon-потоки → дубли action'ов. `chz_scheduler` дублей не
  замечал, `open_check_scheduler` уже имел свой lock.
- Сетевой/файловый I/O в фоновых тредах + SIGTERM/OOM → polу-записанный JSON
  на `/kultura` (persistent disk).
- iiko OLAP `timeout=300` > gunicorn `timeout=120` — worker рестартился до
  получения ответа, кэш не успевал прогреться.

**Файлы:**
- `core/chz_scheduler.py`, `routes/stocks.py`, `core/shifts_manager.py`,
  `core/taps_manager.py`, `core/olap_reports.py`, `telegram_webhook.py`,
  `telegram_bot.py`, `app.py`, `requirements.txt`.

**Подтверждено валидатором:**
- Все lock-пути маунтятся persistent-volume'ами (переживают рестарт контейнера).
- `os.replace` атомарен и на Windows (Python 3.3+), и на Linux.
- Существующая `shifts.db` корректно мигрирует в WAL при первом подключении.
- Конфликтов с правками URL-аудита нет (разные строки).

**Открытые P2 (не блокеры):**
- `extensions.py:35`, `core/kpi_calculator.py:75`, `core/meeting_notes.py:17`,
  `core/shifts_manager.py:28` — `os.path.exists('/kultura')` напрямую вместо
  `core/storage_paths`. В production работает (mount `/kultura`), но единый
  helper упростит dev-окружение.
- `routes/misc.py:run_async` — `asyncio.get_event_loop()` (deprecated в Py 3.12).
- `core/olap_reports.py` — 25+ `requests.*` без retry/backoff (iiko flaky).
- `print()` повсеместно вместо `logging.*` (под gunicorn `--access-logfile -`
  работает, но без уровней).
- Нет файлового lock на `/kultura/plansdashboard.json`, `meeting_notes.json`,
  `kpi_targets.json` (только in-process `threading.Lock`) — под 2 worker'ами
  потенциальная коррупция. Решается тем же tmp+replace.

### 2026-05-28 — Audit Render → Selectel: убраны захардкоженные onrender.com ссылки, актуализированы доки

После миграции с Render на Selectel VPS (https://beerkultura.ru, 139.100.200.92,
Docker Compose + Caddy) код и документация всё ещё ссылались на старые URLs.
Пройден полный аудит репозитория, исправлены некритичные, но видимые места.

**Что:**
- `telegram_bot.py:19` — default `API_BASE_URL` поменян с `https://beer-abc-analysis.onrender.com`
  на `https://beerkultura.ru`. Шапка модуля переписана.
- `routes/misc.py:setup_telegram_webhook` — теперь читает `API_BASE_URL` первым,
  потом `RENDER_EXTERNAL_URL` (оставлен как алиас, env-переменная всё ещё прописана
  на сервере для обратной совместимости). Комментарии обновлены.
- `routes/open_check.py:openbot_setup_webhook` — аналогичный порядок:
  `API_BASE_URL` → `RENDER_EXTERNAL_URL` → `request.url_root`.
- `docs/open-check-bot.md`, `docs/changelog/CHANGELOG_STOCKS_FILTERING.md`,
  `docs/technical/CODE_ANALYSIS_COMPLETE.md` — заменены примеры `curl
  https://*.onrender.com/...` на `https://beerkultura.ru/...`.
- `README.md` — баннер, секция «Архитектура», «Быстрый старт», «Инфраструктура»
  и «Поддержка» переписаны под Selectel VPS + Docker Compose + Caddy. `render.yaml`
  явно помечен как legacy rollback-страховка.
- `docs/guides/README.md`, `docs/guides/DEPLOYMENT_GUIDE.md`, `docs/PROJECT_STRUCTURE.md`
  — Render-документы помечены `(legacy)`, добавлены ссылки на актуальный
  Selectel-стек (`Dockerfile`, `docker-compose.yml`, `Caddyfile`).

**Почему:**
- Дефолтный onrender.com URL в `telegram_bot.py` означал, что если кто-то
  запустит polling-бота без `.env`, он начнёт стучать на мёртвый Render-сервис.
- Доки → юзеры читают README первым, видеть «работает только через Render»
  на проде Selectel — путаница.
- `RENDER_EXTERNAL_URL` в env-переменных и в коде оставлен — задокументирован
  как алиас в `.env.example`, на сервере содержит `https://beerkultura.ru`.

**Файлы:**
- Код: `telegram_bot.py`, `routes/misc.py`, `routes/open_check.py`.
- Доки: `README.md`, `docs/PROJECT_STRUCTURE.md`, `docs/open-check-bot.md`,
  `docs/changelog/CHANGELOG_STOCKS_FILTERING.md`,
  `docs/technical/CODE_ANALYSIS_COMPLETE.md`, `docs/guides/README.md`,
  `docs/guides/DEPLOYMENT_GUIDE.md`.

**Оставлено намеренно:**
- `render.yaml`, `docs/guides/RENDER_DISK_SETUP.md` — rollback-страховка на 1-2 недели.
- `core/storage_paths.py:RENDER_DISK_DIR` — имя константы (внутреннее API),
  фактическое значение приходит из `PERSISTENT_DATA_DIR=/kultura`. Переименование
  затронуло бы импорт в `routes/dashboard.py` и не даёт функциональной пользы.
- `routes/dashboard.py:render_disk_dir/render_disk_exists` — ключи в diag-JSON,
  потребители (внешние ops-скрипты, если есть) могут на них полагаться.
- Исторические упоминания Render в `docs/CHANGELOG.md`, `.claude/docs/CHANGELOG.md`,
  `docs/changelog/*` — это история, по правилам проекта не переписываем.
- `docs/guides/ОЦЕНКА_ТРУДОЗАТРАТ_С_ИИ.md` (`RENDER_DEPLOY_HOOK` в примере
  GitHub Actions) — это иллюстрация в оценке трудозатрат, не действующий пайплайн.

**Что НЕ найдено** (хорошо):
- Захардкоженных путей `/opt/render/project/src/...` — нет.
- Проверок `os.environ.get('RENDER')` для определения окружения — нет.
- Кода, который сам бы вызывал `setWebhook` на старый Render URL при старте — нет.
  Webhook регистрируется только вручную через `/telegram/setup-webhook` или
  `/telegram/openbot/setup-webhook`, базовый URL теперь приходит из `API_BASE_URL`.

### 2026-05-15 — KPI-каталог расширен до полного набора дашборда сотрудника

В редакторе «Настройка KPI-целей» на /salary было 11 опций метрик —
меньше, чем показывает /employee. Пользователь не мог выбрать «Новые карты
лояльности», «Опоздания», «Часы» и др. как KPI.

**Что:**
- `AVAILABLE_METRICS` расширен с 11 до 19 записей: добавлены `draft_revenue`,
  `bottles_revenue`, `kitchen_revenue`, `shifts_count`, `work_hours`,
  `late_count`, `loyalty_cards_count`, `plan_fact_percent`.
- `_build_kpi_metrics()` теперь принимает `late_count`, `loyalty_cards`,
  `cancelled_count`, `plan_revenue` и возвращает все 19 полей. Стаб
  `'cancelled_count': 0` заменён на реальное значение.
- `/api/kpi-calculate` параллельно запускает 3 OLAP-операции вместо 1:
  `get_kpi_olap_data` + `get_cancelled_orders_by_waiter` +
  `get_new_loyalty_cards_by_waiter` — через `ThreadPoolExecutor(max_workers=3)`.
  План сотрудника считается через `get_employee_plan_by_shifts`.
- UI: добавлен `title=` тултип на ячейку «Коэффициент» в детализации KPI и
  на формуле в шапке (`смены с целями / норма`).
- UI: блок «Настройка KPI-целей» вынесен из `#results` (был доступен только
  после расчёта) и теперь находится сразу под селектором периода — открыть
  настройки можно без предварительного расчёта.
- Документация: исправлена формула в `.claude/docs/employee.md` (старая
  сигнатура `calculate_premium(..., total_shifts, ...)` уже не существует;
  актуальная — двухэтапная `intermediate × koef`).
- `docs/salary-instruction.txt`: уточнено, что в коэффициент попадают только
  смены на точках с настроенными KPI-целями.

**Почему:**
- Дашборд сотрудника содержит 13 метрик, которые видны руководителю; не
  иметь их в KPI-каталоге странно — пользователь не может настроить KPI на
  основе уже измеряемого показателя.
- Инверсные метрики (`late_count`, `cancelled_count`) работают через
  `target < min` без изменений формулы.
- Старая документация описывала несуществующую сигнатуру — сбивала с толку
  при ревью кода.

**Файлы:**
- `core/kpi_calculator.py` — `AVAILABLE_METRICS` +8 записей, комментарий
  про инверсные метрики.
- `routes/employee.py` — сигнатура `_build_kpi_metrics()`, OLAP-блок в
  `/api/kpi-calculate`, расчёт `plan_revenue` и подстановка
  `loyalty_cards`/`cancelled_count` в цикле.
- `templates/bonus.html` — `koefTitle` и `title=` на «Коэффициент»; tooltip
  на формуле KPI в `.formula-card`.
- `.claude/docs/employee.md` — секции «Формула расчёта», «Итоговая премия»,
  «Формулы → KPI ratio» переписаны под актуальный код.
- `docs/salary-instruction.txt` — пункт 4 «KPI-премия» уточнён.

### 2026-05-13 — Планы мая 2026 + sync-from-repo + диагностика persistence

**Зачем:** Сохранение через UI на проде «уходит при рестарте». Корневая
причина — `data/plansdashboard.json` мог писаться в эфемерный rootfs контейнера
вместо `/kultura`, плюс `seed_from_local=True` копирует repo на диск только
один раз при пустом диске, поэтому git push с новыми планами не доходит до прода.

**Что:**
- `core/storage_paths.py` — `RENDER_DISK_DIR` теперь конфигурируется через env
  `PERSISTENT_DATA_DIR` (default `/kultura`). Когда диск не найден, при resolve
  пути печатается явный warning «Данные не переживут рестарт!». Добавлена функция
  `is_persistent_storage_active()`.
- `core/plans_manager.py:_read_file` — при повреждённом JSON и отсутствии живого
  backup теперь бросает `RuntimeError`, а НЕ пересоздаёт пустую структуру. Это
  раньше приводило к молчаливому обнулению всех планов.
- `routes/dashboard.py` — два новых endpoint:
  - `GET /api/storage/diagnose` — показывает реальный путь файла, mount-статус,
    размер, mtime, число ключей. Без авторизации (без чувствительных данных).
  - `POST /api/plans/sync-from-repo` (защищён `PLANS_ADMIN_TOKEN`) — переливает
    `data/plansdashboard.json` из repo в `/kultura/plansdashboard.json`,
    предварительно создавая именованный backup
    `plansdashboard.json.before-sync-<UTC_ISO>`. Каждый ключ проходит через
    `save_plan_with_regeneration`, что запускает валидацию и точечный пересчёт
    daily_plans. Опция `?prune=true` для удаления ключей, которых нет в repo.
- `data/plansdashboard.json` — добавлены планы на май 2026 для 4 заведений и
  агрегата `all_2026-05`. Источник цифр: предоставленные значения по выручке,
  чекам, среднему чеку, прибыли, долям и наценкам. `revenueDraft/Packaged/Kitchen`
  пересчитаны из `revenue × share / 100`. `tapActivity=100`, `loyaltyWriteoffs=0`.
- `data/daily_plans.json` — регенерированы майские дневные планы для всех
  4 заведений (weekend weight 2.0 для Пт/Сб, 1.0 для остальных).

**Как применить на прод:**
1. Открыть `https://<prod>/api/storage/diagnose` — подтвердить, что
   `persistent_storage_active=true` и путь содержит `/kultura`.
2. В Render → Environment добавить `PLANS_ADMIN_TOKEN=<секрет>`.
3. После redeploy выполнить:
   `POST https://<prod>/api/plans/sync-from-repo` с заголовком
   `X-Admin-Token: <секрет>`. В ответе будут `applied`, `pruned`, `errors`,
   `backup` (путь именованного бэкапа на диске).
4. Если `persistent_storage_active=false` — НЕ запускать sync; сначала починить
   Mount Path диска или env `PERSISTENT_DATA_DIR`.

**Файлы:**
- `core/storage_paths.py`
- `core/plans_manager.py`
- `routes/dashboard.py`
- `data/plansdashboard.json`
- `data/daily_plans.json`

---

### 2026-04-30 — Shelf-Life Cockpit: оптимизация и доработка

Доработка страницы /expiration после первого запуска.

**Что:**
- Цена позиции = себестоимость `sum/amount` из balances iiko (раньше было 0,
  потому что nomenclature не содержит price/sellPrice). Это даёт честный
  `risk_rub` для оценки прямого финансового убытка от списания.
- Удалён календарь риска (визуальный шум, дублировал KPI «Под риском, ₽»).
- 3 оптимизации производительности /api/expiration/board:
  1. **Балансы — 1 запрос вместо N**: `get_store_balances()` возвращает данные
     по всем складам сразу, теперь вызывается один раз и фильтруется по `store`
     внутри `_build_bar_data()` (раньше было 4 одинаковых тяжёлых запроса).
  2. **TTL-кеш ответа** в памяти процесса (120 сек, потокобезопасный
     `threading.Lock`). Force-refresh через `?force=1`. Холодный запрос ~8с,
     тёплый — 0.23с (×35 ускорение).
  3. **Параллельный fetch operations** через `ThreadPoolExecutor(max_workers=4)`
     по барам — вместо последовательных 4 OLAP-запросов.
- UI loader: 3 стадии (Балансы → ЧЗ → Рендер) с анимированными метками,
  бейдж в meta-row показывает `0.2с` или `кеш 45с` для прозрачности скорости.

**Почему:**
- Без цены KPI и сортировка по риску бесполезны — все нули.
- Календарь не давал actionable-инфу: даты уже видны в карточках.
- Лоадер «Загружаем board...» висел 20-30с без обратной связи.

**Файлы:**
- `routes/expiration.py` — `_build_bar_data()` принимает `balances` и `ops`
  снаружи, удалён `_extract_price()`, добавлен `_BOARD_CACHE`, `ThreadPoolExecutor`
- `templates/expiration.html` — убран `renderCalendar()` и calendar HTML/CSS,
  добавлены `.stages` и `.cache-badge`, `loadBoard(force)`
- `docs/expiration.md` — переписана секция «Источники данных», убран блок про
  календарь, обновлено ограничение про цену

---

### 2026-04-30 — Shelf-Life Cockpit (страница /expiration)

Новая отдельная страница для управления сроками годности с action layer:
KPI-полоса, tier-вкладки (expired/critical/urgent/watch/fresh), карточный grid
с рекомендациями (уценка / перевод между барами), календарь риска ₽ на 31 день.

**Что:**
- Tier-классификация по дням до истечения (адаптация ShelfLifePro: 0-7/8-14/15-30/30+)
- Рекомендация уценки с учётом эластичности спроса (PRICE_ELASTICITY=1.5)
- Cross-bar transfer suggestions (если в другом баре velocity выше и сток <7 дней)
- KPI: ₽ под риском, критичных SKU, излишек шт.

**Почему:** Старый таб «Сроки годности» в /stocks — пассивный список. Менеджер видит
«истекает через 6 дней, 24 шт.» и должен сам считать сколько успеет продать
и какую скидку поставить. Cockpit делает этот расчёт и показывает рекомендацию.

**Файлы:**
- `routes/expiration.py` (новый) — Blueprint + GET /api/expiration/board
- `core/expiry_recommend.py` (новый) — classify_tier(), recommend(), константы
- `templates/expiration.html` (новый) — UI без эмодзи, IBM Plex Mono, переменные дизайн-системы
- `docs/expiration.md` (новый) — модуль-док
- `routes/__init__.py`, `templates/shared/nav.html` — регистрация и пункт меню

Старый таб «Сроки годности» в `/stocks` оставлен как было.

---

### 2026-04-26 — Поэтапные даты маркировки ЧЗ — почему «нет в ЧЗ» бывает легально

Изучил официальные ПП РФ и материалы честныйзнак.рф по этапам ввода
обязательной маркировки. Это объясняет значительную часть из 125
несматченных позиций.

**Этапы для пива (ПП РФ № 2173 от 30.11.2022, group 15):**
- 01.04.2023 — кеги, нанесение КИ обязательно
- 01.10.2023 — ПЭТ и стекло
- 15.01.2024 — алюм. банка и прочая упаковка
- 01.04.2024 — розница обязана через УПД с КИ. Запрет реализации
  немаркированной продукции, выпущенной ДО 01.04.2023
- 01.03.2025 — поэкземплярный учёт кег
- 01.09.2025 — поэкземплярный учёт потреб. упаковки

Сидр/медовуха/перри идут в group 15 (слабоалкогольные), даты те же.

**Этапы для безалкогольного пива (ПП РФ № 678 от 27.05.2024, group 22):**
- 01.09.2024 — регистрация участников
- **01.10.2024** — нанесение КИ обязательно (все виды упаковки сразу)
- Остатки до 01.10.2024:
  - срок годности ≤ 365 дней — легально продаются БЕЗ КИ до 01.10.2025
  - срок годности > 365 дней — легально продаются БЕЗ КИ до конца годности

**Этапы для безалк. напитков (ПП РФ № 887 от 31.05.2023, group 23):**
- 01.12.2023 — стекло/ПЭТ, нанесение КИ
- 01.03.2024 — банки
- 01.06.2024 — кеги, Tetra Pak, прочее
- 01.06.2024 — розница через УПД с КИ
- Соки/нектары/морсы — поэкземплярный учёт только с 01.03.2026
- Остатки до 01.10.2024 — до конца срока годности

**Что это значит для нашего списка 125 «нет в ЧЗ»:**

| Категория | Кол-во в списке | Возможная причина |
|---|---|---|
| Безалк. пиво (Clausthaler 0%, Будвайзер 0%, Lapochka б/а) | ~25 | Легально без КИ если розлив до 01.10.2024 |
| Лимонады/шорли (HopHead Лимонад, Jaws Hop Water, Бульви Шорли) | ~10 | Легально без КИ если розлив до 01.12.2023 |
| Импорт Бельгия/Германия (Westmalle, La Trappe, Paulaner...) | ~50 | Должны быть с КИ; вероятно ЭДО-затык поставщика |
| Малый крафт РФ (Paradox, Bakunin, Plague Brew, Кулинар...) | ~40 | Должны быть с КИ; либо ЭДО-затык, либо производитель не маркирует |

**Вывод:** примерно **30-40 позиций** из 125 «нет в ЧЗ» — это **легитимные остатки без КИ**, не баг. Их «нет» в ЧЗ потому что их там физически и нет, и не должно быть.

**Дальше:** в UI имеет смысл различать «нет в ЧЗ» (предположительно legacy ok) vs «нет в ЧЗ» (вероятно проблема ЭДО). Эвристика: безалк-категории + дата производства до даты этапа = OK.

Источники: честныйзнак.рф/business/projects/beer/marking_dates_beer/,
честныйзнак.рф/business/projects/nonalcoholic_beer/marking_dates/,
честныйзнак.рф/business/projects/beverages/marking_dates/.

---

### 2026-04-26 — Полная автоматизация выгрузки ЧЗ через dispenser API

**До:** пользователь руками выгружал CSV из ЛК ЧЗ (3 группы: beer/water/milk),
клал в `chz_test/debug/pg*_csv/`, запускал `chz.py csv`. Без ручного действия
данные устаревали (на момент диагностики CSV был 2-недельной давности).

**Теперь:** один POST-запрос → весь цикл автоматически на бар-ПК.

**Как работает:**
1. На бар-ПК `chz.py csv-auto` для каждой группы (beer/water/nabeer):
   - `POST /api/v3/true-api/dispenser/tasks` — создать задание `FILTERED_CIS_REPORT`
   - `GET /api/v3/true-api/dispenser/tasks/{id}` — опрашивать статус до COMPLETED
   - `GET /api/v3/true-api/dispenser/results` — получить resultId
   - `GET /api/v3/true-api/dispenser/results/{id}/file` — скачать ZIP
   - Распаковать ZIP, сохранить CSV в `chz_test/debug/pg{code}_csv/auto-*.csv`
2. После всех групп — `parse_chz_csv()` → перестроить `chz_stock.json`
3. Flask тянет JSON через SSH/SFTP

**productGroupCode:**
- 15 = BEER
- 13 = WATER
- 22 = NABEER (безалкогольное на пивной основе) — **новая группа**, в ручных
  выгрузках её не было

**Изменения:**
- `chz_test/chz.py` — добавлены: `dispenser_create_task`, `dispenser_poll`,
  `dispenser_get_result_id`, `dispenser_download`, `export_csv_via_dispenser`,
  CLI команда `csv-auto`. Парсер теперь умеет читать UTF-8 / cp1251 и
  распаковывать ZIP-ответы dispenser API.
- `remote_exec.py` — добавлен спец-режим `run csv-auto`: token refresh →
  csv-auto на бар-ПК → pull `chz_stock.json` локально.
- `routes/stocks.py` — `POST /api/chz/refresh` теперь дёргает `csv-auto`
  вместо устаревшего `stock`. Новый эндпоинт `GET /api/chz/refresh/status`
  для опроса прогресса (running, exit_code, log_tail, cache_updated_at).
- `templates/stocks.html` — кнопка «Обновить данные ЧЗ» во вкладке Сроки
  годности с polling-индикатором; после успеха таблица перезагружается.
- `core/chz_scheduler.py` (новый) — daemon-thread дёргает refresh раз в
  сутки (по умолчанию 03:00, env CHZ_REFRESH_HOUR / CHZ_REFRESH_MINUTE).
- `app.py` — стартует scheduler при запуске Flask, если `REMOTE_PASS` в env.

**Match rate с фрешем через dispenser:**

| Бар | До (CSV 12.04) | После (API 26.04) |
|---|---|---|
| Большой В.О | 82 | 96 |
| Лиговский | 52 | 76 |
| Кременчугская | 78 | 80 |
| Варшавская | 58 | 65 |
| Общая | 202 | 228 |

**Эксплуатация:**
- Флешем по кнопке: открыть Stocks → Сроки годности → «Обновить данные ЧЗ»
- Авторефреш: `REMOTE_PASS=xxx py app.py` → каждый день в 03:00
- Лог: `chz_test/debug/refresh.log` (truncate перед каждым refresh)
- Лимит ЧЗ: 10 заданий в сутки на одну товарную группу — для нас 1/день более чем достаточно

**На будущее:**
- Если в `chz.py` в DISPENSER_GROUPS добавить ещё группы (например milk
  если бар начнёт продавать молоко) — сразу подхватится.
- На бар-ПК нет апдейтера: новые версии `chz.py` пушит `remote_exec.py push`.

---

### 2026-04-26 — Обновление iiko XML-номенклатуры → +146% матчей с ЧЗ

**Диагностика match rate.** Из 366 позиций фасовки (Общая):
- 80 матчились с ЧЗ
- 141 «нет в XML iiko» — товар есть в OLAP-кэше, в XML-номенклатуре нет
- 144 «есть баркод, нет в ЧЗ» — баркод корректный, но GTIN отсутствует в выгрузке ЛК
- 1 без баркода вообще

**Корень:** `data/cache/nomenclature__products.xml` от 26.12.2025, не обновлялся
4 месяца. Среди 141 «не в XML» — 99 от поставщика «БЕЗ ИМЕНИ ОРГАНИЗ…»,
16 от ИП Степанов и др. — новые товары, появившиеся в продажах после 26.12.

**Решение:** скачали свежую XML через `/products` iiko API. Результат:
- 7866 → 8362 товаров (+496)
- 3953 → 4302 с баркодом (+349)
- 4295 → 4743 уникальных GTIN в карте

**Эффект на match rate:**

| Бар | Было | Стало |
|---|---|---|
| Большой В.О | 30 | 82 |
| Лиговский | 19 | 52 |
| Кременчугская | 33 | 78 |
| Варшавская | 23 | 58 |
| Общая | 82 | 202 |

Срочных <30д было 0-1, теперь 6 на юрлицо.

**На будущее:** XML-кэш надо периодически обновлять. Вариант — добавить
TTL в `core/iiko_barcodes.py` или endpoint `POST /api/iiko/refresh-xml`.

---

### 2026-04-26 — Точная привязка партий ЧЗ к конкретному бару через КПП

**Проблема предыдущей итерации:**
Эвристика «брать последние партии по дате производства под iiko-остаток» врала
при размазывании одного SKU по нескольким барам — одни и те же партии могли
показаться в разных барах. Пользователь это сразу заметил.

**Находка:** в **локальной документации ЧЗ** (`chz_test/чз/docs.crpt22.ru.html`,
str. 2743) описан CSV-формат `FILTERED_CIS_REPORT` — ровно тот же отчёт,
который выгружается из ЛК. У него 35 колонок, две из которых критичны:
- `kpp` — КПП места осуществления деятельности (МОД), где числится CIS
- `fiasId` — ФИАС-идентификатор адреса МОД

**Эти колонки уже есть в выгруженных CSV у пользователя**, просто игнорировались
старым парсером. Распределение по 3016 строкам:
- KPP 784201001 — 1043 кода (Кременчугская)
- KPP 780145001 — 738 кодов (Большой В.О.)
- KPP 781045001 — 710 кодов (Варшавская)
- KPP 781645001 — 343 кода (Лиговский)

**Маппинг бар↔КПП получен через `GET /api/v3/true-api/mods/list`** (новая
команда `python chz.py mods` — добавлена в [chz_test/chz.py](chz_test/chz.py)).
Ответ сохранён в `chz_test/debug/mods.json` с адресами всех 4 МОД.

**Изменено:**
- `chz_test/chz.py:parse_chz_csv` — извлекает `kpp` и `fiasId` из CSV,
  агрегирует по `(gtin, kpp, prod_date, exp_date)`. Каждый GTIN теперь имеет
  поле `by_kpp: [{kpp, fiasId, count, batches: [{prod, exp, count}]}, ...]`.
- `chz_test/chz.py` — новая CLI команда `mods` для запроса справочника МОД.
- `routes/stocks.py:get_bottles_with_expiry` — добавлен `bar_kpp_map`
  (bar1..bar4 → КПП), для конкретного бара берёт партии **только** из
  его слота `by_kpp[kpp]`. Эвристика «обрезаем под iiko-сток» удалена —
  данные точные, показываем все партии, которые числятся за этим баром.
  Добавлено поле `bar_chz_count` (коды на КПП этого бара) рядом с
  `chz_total_count` (по всему юрлицу).
- `templates/stocks.html` — UI показывает предупреждение «⚠ В ЧЗ за этим
  баром N кодов, в iiko M — касса не RETIRE'ит» когда `bar_chz_count > stock`,
  и второе строкой «по всему юрлицу: K кодов» если SKU размазан по 2+ барам.
- `remote_exec.py` — `mods` добавлено в `ALLOWED_SUBCMDS`.

**Результат на 2026-04-26:**
- Большой пр. В.О: 160 позиций / 30 с CHZ-привязкой
- Лиговский: 115 / 19
- Кременчугская: 158 / 33
- Варшавская: 116 / 23
- Общая (юрлицо): 366 / 82

Точные партии, не эвристика. Когда `bar_chz_count >> stock` — это явный сигнал
что касса этого бара не RETIRE'ит при продажах (cash доминирующий источник
ошибки учёта).

---

### 2026-04-25 — Стыковка iiko-фасовки со сроками годности из ЧЗ

**Контекст:**
Остатки фасовки в iiko (`/api/stocks/bottles`) и сроки годности в ЧЗ
(`/api/chz/stock`) лежали в разных витринах. Бар-менеджеру нужно было одним
взглядом видеть, что физически есть на полке его бара и что из этого скоро
протухнет.

**Решение:** новый эндпоинт `GET /api/stocks/expiry?bar=<bar>` и вкладка
«Сроки годности» в `templates/stocks.html`. Стыковка по `barcode (iiko)`
↔ `gtin (ЧЗ)` через нормализацию к 14 цифрам (`zfill(14)`).

**Изменено:**
- `core/iiko_barcodes.py` (новый) — `parse_barcodes_from_xml()` и
  `get_barcode_map()`. Парсит существующий `data/cache/nomenclature__products.xml`,
  строит `{gtin14: [product_id, ...]}` с in-memory кэшем (инвалидация по mtime).
  OLAP-номенклатура `nomenclature_full.json` баркодов не содержит, поэтому
  пришлось завести отдельный загрузчик из XML.
- `routes/stocks.py` — добавлен `GET /api/stocks/expiry`. Повторяет логику
  `/api/stocks/bottles` (фильтр по `FASOVKA_GROUP_ID`, баланс по складу,
  средние продажи за 30 дней) и обогащает позиции полями `gtins`,
  `expiration_dates`, `production_dates`, `nearest_expiry`, `days_to_expiry`,
  `has_chz_data`. Сортировка: срочные (<30д) сверху, без CHZ-данных в конце.
- `templates/stocks.html` — новая вкладка «Сроки годности» с таблицей по
  поставщикам, цветовой подсветкой (красный <30д, жёлтый <90д, серый без ЧЗ),
  блоком статистики (всего / с ЧЗ / срочных), отображением даты последнего
  обновления кэша ЧЗ.

**Результат (на 2026-04-25):**
- Бар «Лиговский»: 116 позиций фасовки, 31 сматчилась с ЧЗ.
- Все 4 бара (`bar=Общая`): 367 позиций, 82 сматчилось.
- Покрытие GTIN-баркод: 4295 GTIN из XML iiko, 155 из 541 ЧЗ-GTIN сматчены
  (29%) — остальные либо устаревшие позиции в ЧЗ (бар не делает RETIRE),
  либо товары без занесённого баркода в iiko.
- Сортировка проверена на реальных данных: просроченные (-135д) первыми,
  затем по nearest_expiry asc, без ЧЗ-данных — в конце.

**Что НЕ менялось:**
- `chz_test/chz.py` — парсер CSV-экспорта из прошлой сессии работает.
- `routes/stocks.py:get_bottles_stocks` — shape ответа сохранён, существующая
  вкладка «Фасовка» не сломана.
- `core/olap_reports.py` — баркоды добавлены не туда (отдельный модуль),
  чтобы не ломать существующий disk-cache `nomenclature_full.json`.

---

### 2026-04-25 — CHZ stock: переход с API search на CSV-парсер (РАБОЧЕЕ РЕШЕНИЕ)

**Контекст проблемы:**
API `/cises/search` возвращал только 30 GTIN / 173 кода для ИНВЕСТАГРО, тогда как
в реальности у бара 540+ позиций. Расследование показало:
1. API режет страницы до 100 записей (игнорирует `limit=1000`) — пагинация рвалась
   из-за условия `len(items) < limit`.
2. Без фильтра по дате API возвращает 79,000+ INTRODUCED кодов — историческое
   накопление за все годы (бар не делает RETIRE при продажах).
3. CSV-экспорт через ЛК ЧЗ применяет фильтры `participantInn + packageType=UNIT`
   и возвращает реальный текущий склад.

**Решение:** парсить CSV-экспорты из ЛК ЧЗ вместо использования API search.

**Изменено:**
- `chz_test/chz.py` — добавлена функция `parse_chz_csv()`. Читает все
  `chz_test/debug/pg*_csv/*.csv`, фильтрует по `status=INTRODUCED + packageType=UNIT
  + ownerInn=INN_ORG`, агрегирует по GTIN.
- `chz_test/chz.py` — добавлена CLI-команда `python chz.py csv` для построения
  `chz_stock.json` из CSV-экспортов.
- `chz_test/chz.py:298` — `limit = 100` (был 1000) — это реальный потолок API.
- `chz_test/chz.py:267` — `delay_between_pages=0` (был 1) — задержка не нужна.
- `chz_test/chz.py:496-500` — убран дефолтный фильтр по дате 180 дней (он отрезал
  валидный сток с long-shelf-life продуктами).
- `chz_test/test_filters.py` — диагностический скрипт для тестирования параметров
  фильтра API (ownerInn vs participantInn vs packageType).

**Результат:**
- Было: 30 GTIN, 173 кода (через API)
- Стало: 541 GTIN, 2878 кодов (через CSV) — увеличение в 18 раз

**Workflow для пользователя:**
1. Скачать CSV-экспорт из ЛК ЧЗ для нужных групп (beer/nabeer/water/etc.)
2. Распакованные папки положить в `chz_test/debug/pg*_csv/`
3. Запустить `python chz_test/chz.py csv`
4. Данные доступны через `GET /api/chz/stock`

**Замечание:** 203 из 541 GTIN имеют просроченные expiration_dates (2024 год) —
это коды, которые бар не закрыл RETIRE-операцией. Это проблема учёта на стороне
бара, не нашего парсера.

**Файлы:** `chz_test/chz.py`, `chz_test/test_filters.py`, `chz_test/debug/chz_stock.json`

---

### 2026-04-25 — CHZ stock integration: code review pass 4 — bug fixes and docs

**Изменено:**
- `routes/stocks.py:647` — `GET /api/chz/stock`: добавлен HTTP 404 при отсутствии кеша (ранее возвращался 200, что противоречило документации в README и plan).
- `routes/stocks.py:660-676` — `POST /api/chz/refresh`: `_refresh_proc` теперь используется как guard — при уже запущенном refresh возвращает 409 вместо запуска параллельного SSH-процесса. Popen-результат присваивается в модульную переменную.
- `chz_test/chz.py:703-705` — удалён дублирующий default для `date_from` из `main()` — он уже есть в `get_chz_stock()` (добавлен в этой ветке). Два одинаковых defaults = риск расхождения при будущих изменениях.
- `docs/stocks.md` — создан (требование CLAUDE.md: документ на каждый модуль).
- `docs/plans/chz-stock-integration.md` — добавлен статус DONE (2026-04-22).

**Почему:**
- Несоответствие 200 vs 404 нарушало API-контракт, описанный в README.
- Параллельные refreshes создавали два SSH-процесса, записывающих в один файл одновременно.
- `date_from` default в двух местах означал, что изменение периода в одном месте тихо не применится к другому.

**Файлы:** `routes/stocks.py`, `chz_test/chz.py`, `docs/stocks.md`, `docs/plans/chz-stock-integration.md`

---

### 2026-04-22 — CHZ stock integration: code review pass 3 — bug fixes and doc updates

**Изменено:**
- `routes/stocks.py` — `near_expiry_codes`: исправлена логика подсчёта — ранее считались и уже просроченные коды (`days < 0`). Теперь только коды с `0 <= days < 30`.
- `routes/stocks.py` — `GET /api/chz/stock`: `getmtime()` перенесён внутрь `try/except` — ранее при удалении файла между `.exists()` и `getmtime()` возникал необработанный `FileNotFoundError` (TOCTOU race).
- `routes/stocks.py` — удалён мёртвый блок `if amount == 0: pass` в `get_taplist_stocks`.
- `remote_exec.py` — проверка `REMOTE_PASS` перенесена из уровня модуля в `connect()` — импорт модуля больше не выбрасывает исключение.
- `remote_exec.py` — `cd` заменён на `cd /d` во всех командах `run stock` и `run` — без `/d` `cmd.exe` не меняет диск.
- `docs/remote-sync.md` — обновлены учётные данные (Администратор / REMOTE_PASS env), Python путь, состояние бар-ПК; добавлена команда `run stock`.
- `docs/changelog/CHZ_INTEGRATION.md` — обновлён пункт 7: описан дефолтный лимит 180 дней в `get_chz_stock`.
- `chz_test/README.md` — добавлена секция команды `stock`.
- `README.md` — добавлены `GET /api/chz/stock` и `POST /api/chz/refresh` в список API; `REMOTE_PASS`/`REMOTE_USER` добавлены в список env vars.

**Почему:**
- `days < 30` без проверки `>= 0` ошибочно включало давно просроченные коды в `near_expiry_codes`.
- TOCTOU гонка на файле кеша могла вызвать 500 при параллельном refresh.
- `cd` без `/d` не меняет диск в Windows cmd.exe при смене драйва.

**Файлы:**
- `remote_exec.py`, `routes/stocks.py`, `README.md`, `docs/remote-sync.md`, `docs/changelog/CHZ_INTEGRATION.md`, `chz_test/README.md`

### 2026-04-21 — CHZ stock integration: code review pass 2 — security and reliability fixes

**Изменено:**
- `remote_exec.py` — удалён захардкоженный пароль `"Krem2026"` как дефолт в `REMOTE_PASS`; теперь переменная обязательна, без неё бросается `EnvironmentError`
- `remote_exec.py` — `run_cmd`: добавлен `try/finally` для гарантированного закрытия SSH-клиента; добавлен перехват `socket.timeout` с понятным `TimeoutError`
- `remote_exec.py` — `push`, `pull`: добавлены `try/finally` для SFTP и SSH-клиентов, исключающие утечки соединений при исключениях
- `routes/stocks.py` — `GET /api/chz/stock`: при отсутствии кеша возвращает 404 (было 200)
- `routes/stocks.py` — `POST /api/chz/refresh`: `Popen` обёрнут в `try/except OSError`, возвращает 500 при ошибке запуска
- `routes/stocks.py` — `near_expiry` переименован в `near_expiry_codes` и теперь считает количество кодов (было количество GTIN); семантика согласована с `total_codes`

**Почему:**
- Хранение пароля в исходном коде — критическая уязвимость
- Утечки SSH-сессий при сетевых сбоях накапливались на бар-ПК
- `near_expiry=1` рядом с `total_codes=50` вводило в заблуждение

**Файлы:**
- `remote_exec.py`
- `routes/stocks.py`

### 2026-04-21 — CHZ stock integration: Task 5 — add Flask cache endpoints

**Изменено:**
- `routes/stocks.py` — добавлен `GET /api/chz/stock`: читает `chz_test/debug/chz_stock.json` с диска, возвращает `{items, updated_at}`. При отсутствии файла — `{items:[], error:'no data'}`. При повреждённом JSON — 500 с `error:'cache corrupted or updating'`
- `routes/stocks.py` — добавлен `POST /api/chz/refresh`: запускает `remote_exec.py run stock` через `subprocess.Popen` (неблокирующий), возвращает `{status:'started'}`

**Почему:**
- `/api/stocks/chz` вызывает CHZ API напрямую, требует CryptoPro на сервере (недоступно на Render)
- Новые endpoints используют кеш-файл, обновляемый с бар-ПК по запросу

**Файлы:**
- `routes/stocks.py`

### 2026-04-21 — CHZ stock integration: Task 6 — verify result

**Проверено:**
- `chz_test/debug/chz_stock.json` содержит 30 GTIN, 16 с product_group=BEER, все 30 с непустыми expiration_dates
- `routes/stocks.py` проходит `python -m py_compile` без ошибок
- Оба endpoint `/api/chz/stock` и `/api/chz/refresh` присутствуют в коде

**Файлы:**
- `chz_test/debug/chz_stock.json`
- `routes/stocks.py`
- `docs/plans/chz-stock-integration.md`

### 2026-04-21 — CHZ stock integration: Task 4 — run stock on bar-PC

**Изменено:**
- `remote_exec.py` — добавлен параметр `timeout` в `run_cmd` (передаётся в `exec_command`)
- `remote_exec.py` — добавлена специальная команда `run stock`: обновляет токен, запускает `chz.py stock` с timeout=600, скачивает `chz_stock.json` в `chz_test/debug/`
- `remote_exec.py` — исправлена кодировка вывода: теперь `sys.stdout.buffer.write` с UTF-8 вместо `print` (избегает cp1251 ошибок)
- `chz_test/debug/chz_stock.json` — обновлён: 30 GTIN, 29 с датами годности

**Почему:**
- Без timeout=600 долгие SSH-команды обрывались по таймауту paramiko
- run stock нужен как единая команда для обновления кеша (токен + сбор + скачивание)

**Файлы:**
- `remote_exec.py`
- `chz_test/debug/chz_stock.json`

### 2026-04-17 — /packaging: fintech-вид карточек (LED + сухие русские имена корзин)

**Что сделано:**
- Карточки `.abc-card` переведены со сплошной заливки цветом на fintech-паттерн из дашборда: белый фон (`--bg-secondary`), тонкий бордер (`--border-color`), маленький LED-индикатор 8px в правом верхнем углу с цветным `box-shadow`-свечением.
- 6 цветов LED: `led-success` (Ядро), `led-accent` (Объём), `led-warning` (Недооценённые), `led-violet` (Ниша), `led-neutral` (База), `led-danger` (К выводу). Для XYZ-карточек: X→success, Y→warning, Z→danger.
- Русские названия корзин стали «сухими»: Звёзды→**Ядро**, Рабочие лошадки→**Объём**, Поднять цену→**Недооценённые**, Премиум-ниша→**Ниша**, Фон→**База**, Удалить→**К выводу**. `BUCKETS_UI[key].led` хранит LED-класс рядом с именем.
- Новые JS-хелперы: `getBucketLedClass(bucketKey)`, `getBucketLedClassFromCode(code)`, `getXYZLedClass(xyz)`. Все рендеры `.abc-card` эмитят `<span class="led"></span>` и используют `led-*`-класс; старые `bucket-*`/`aaa`/`bbb`/`ccc`-классы на карточках удалены (остались только на `.badge` в таблицах).
- Починен баг в двух старых рендерерах: модалка категорий использовала `.abc-card ${abc.toLowerCase()}` и `'aaa'/'bbb'/'ccc'` — классы давно удалены, карточки были бесцветные. Теперь работают через `getBucketLedClassFromCode` / `getXYZLedClass`.

**Почему:**
После предыдущего шага карточки оказались вообще без цвета: JS продолжал ставить классы `bucket-stars`/`bucket-workhorses`/..., которые существовали только в стилях `.badge`, но не в стилях `.abc-card`. Плюс старые названия («Звёзды», «Рабочие лошадки») выглядели по-детски. Новый вид совпадает с дашбордом (`.metric-card` + `.status-indicator`) — один визуальный язык для всех страниц.

**Файлы:**
- `templates/index.html` — `.abc-card` CSS (удалён дубликат со сплошной заливкой), `BUCKETS_UI` с сухими именами и полем `led`, хелперы `getBucketLedClass/getBucketLedClassFromCode/getXYZLedClass`, правки в `createBarCard` (bucket/abcCards/xyzSection), `createBarCard`-all-bars категорийные карточки, модалка `showCategoryDetail`

**Что ломается если изменить неправильно:**
- Если JS снова начнёт ставить класс `bucket-stars`/`bucket-workhorses`/... на `.abc-card` — карточки окажутся без LED и без цвета (эти классы теперь только на `.badge`).
- Если убрать `<span class="led"></span>` из разметки — LED не появится (он рисуется абсолютным позиционированием внутри карточки).
- LED-классы (`led-*`) не путать с классами бейджей (`bucket-*`/`demand-*`) — это две независимые системы: карточки = LED, бейджи в таблицах = заливка.

---

### 2026-04-17 — /packaging: ABC_Combined = выручка + наценка + спрос, 6 корзин действий

**Что сделано:**
- 3-я буква `ABC_Combined` перекинута с маржи в рублях на XYZ (стабильность спроса). Теперь код вида `AAX`, `BCY`, `CCZ` — выручка + наценка + спрос.
- `ABC_Margin` (категория по марже в рублях) остаётся отдельным полем для сортировки, но в 3-буквенный код не входит. `ABCXYZ_Combined` удалён (дублировал `ABC_Combined`).
- Новый модуль [`core/abc_buckets.py`](../core/abc_buckets.py) — 27 комбинаций сворачиваются в 6 корзин действий по первым двум буквам (выручка × наценка): `stars`, `workhorses`, `price_up`, `premium`, `background`, `remove`. XYZ не влияет на корзину — это операционный модификатор (как планировать запас).
- На `/packaging` перед блоком «ABC-коды» появляется блок «Корзины действий» из 6 плашек, клик открывает модалку с позициями в корзине.
- Backend: ответ `/api/analyze` теперь содержит `bucket_stats: {key: count}` и поле `ABC_Bucket` на каждой записи. То же в `/api/categories` через `CategoryAnalysis.add_xyz_to_category_analysis`.
- Frontend: удалён хардкод 27 tooltip-ов (`categoryDescriptions`), заменён на функцию `createTooltip(code)`, которая разбирает 3-буквенный код и подставляет описание корзины + расшифровку каждой буквы. CSS плашек перешёл с `.badge.aaa/.../.ccc` на `.badge.bucket-stars/.../.bucket-remove` + `.badge.demand-x/y/z`.

**Почему:**
Старая 3-я буква (маржа в рублях) математически скоррелирована с выручкой × наценкой — одни и те же позиции почти всегда получают одну и ту же третью букву. Это не даёт новой информации и усложняет мониторинг. Спрос (XYZ) независим от первых двух и реально влияет на решения (запасы, закупки). 27 кодов всё равно много для daily-мониторинга, поэтому первичный вид — 6 корзин действий, а полный код остаётся на бэйджах + в тултипе.

**Файлы:**
- `core/abc_buckets.py` (новый) — маппинг корзин, `get_bucket_key`, `get_bucket_info`
- `routes/analysis.py` — `/api/analyze`: убран `ABCXYZ_Combined`, `ABC_Combined` пересобирается после merge XYZ, добавлены `ABC_Bucket` и `bucket_stats`
- `core/category_analysis.py` — `add_xyz_to_category_analysis` пересобирает `ABC_Combined = Revenue+Markup+XYZ`, считает `abc_stats` и `bucket_stats` по новой схеме
- `templates/index.html` — новые CSS-классы, helpers `getBucketKey/getBucketClass/createTooltip`, секция «Корзины действий», модалка `showBucketDetails`

**Что ломается если изменить неправильно:**
- Если где-то остался `ABCXYZ_Combined` — поле теперь не возвращается в `/api/analyze`.
- `/api/draft-analyze` (страница /discounts) НЕ тронут — там `ABC_Combined` по-прежнему `Revenue+Markup+Margin`. При необходимости привести к единой схеме — править `routes/analysis.py` строки ~527/623/733 и `templates/draft.html`.
- CSS-классы `.badge.aaa`...`.ccc` удалены. Если какой-то шаблон ещё генерирует `ABC_Combined.toLowerCase()` как класс — плашки окажутся без фона.

---

### 2026-04-16 — Фикс выбора периода на /packaging + удаление чужих карточек

**Что сделано:**
- `/api/analyze` и `/api/categories` теперь принимают `date_from`/`date_to` (как `/api/draft-analyze`); при их отсутствии — fallback на старое поведение (`days` от сегодня)
- К `date_to` добавляется +1 день для OLAP exclusive-границы — последний выбранный день включается в период
- Фронтенд `templates/index.html` шлёт `{bar, date_from, date_to}` вместо `{bar, days}`
- Удалены 4 карточки выручки (Текущая/План/Ожидаемая/Средняя) с `/packaging` — они принадлежат дашборду, на странице ABC/XYZ-анализа фасовки им не место. Заодно удалены связанные функции `loadRevenueMetrics`/`updateRevenueMetrics` и вызов на загрузку страницы

**Почему:**
На странице /packaging пользователь выбирал период через flatpickr, но бэкенд игнорировал даты — считал только количество дней от `datetime.now()`. Например, выбор «1–7 марта» давал данные за «последние 6 дней до сегодня». ABC/XYZ-анализ возвращал не то, что показано в карточках выручки (которые уже работали по date_from/date_to).

**Файлы:**
- `routes/analysis.py` — `/api/analyze` (lines 18-50), `/api/categories` (lines ~277-310)
- `templates/index.html` — `runAnalysis()` (lines ~942-965)

**Что ломается если изменить неправильно:**
- Если убрать `+1 день` к `date_to` — последний день периода будет выпадать из выборки (OLAP `dateTo` exclusive)
- Если убрать fallback на `days` — сломаются внешние вызовы API без `date_from`/`date_to` (если такие есть)

---

### 2026-04-11 — ЧЗ остатки: название + количество + срок годности

**Новое:**
- `chz.py stock` — CLI команда для получения остатков пива в формате "название — количество — срок годности"
- `get_product_names(gtins)` — запрос к `/api/v4/true-api/product/info` для получения названий по GTIN
- `get_chz_stock()` — объединяет коды со статусом INTRODUCED с названиями продуктов
- `/api/stocks/chz` — Flask endpoint для дашборда

**Как работает:**
1. `cises/search` получает все коды маркировки за период
2. Фильтруются только коды со статусом `INTRODUCED` (в обороте = на складе)
3. Группировка по GTIN, подсчёт количества
4. `product/info` получает названия, бренды, объёмы по GTIN
5. Результат: GTIN + название + количество + сроки годности

**Файлы:**
- `chz_test/chz.py` — добавлены `get_product_names()`, `get_chz_stock()`, `print_stock_report()`, команда `stock`
- `routes/stocks.py` — добавлен endpoint `/api/stocks/chz`

### 2026-04-08 — Beer Menu Card Creator

**Что создано:**
- Веб-конструктор A4-карточек пивного меню с live-превью
- Два режима экспорта PNG: client (html2canvas) и server (Playwright)
- CRUD API для управления позициями, загрузка логотипов
- Фиксированный дизайн (PT Serif, corner accents, dividers), не ломающийся при любом контенте

**Файлы:**
- `routes/menu.py` — Blueprint с API и Playwright-рендером
- `templates/menu.html` — страница конструктора
- `templates/menu_card.html` — standalone шаблон карточки
- `static/menu/logos/` — папка для логотипов
- `data/menu_items.json` — хранилище позиций
- `docs/menu-card.md` — документация модуля


---

### 2026-04-16 — Фикс сохранения планов в дашборде: диск = единственный источник правды

**Что сделано:**
- Убрана авто-перезапись Render Disk значениями из repo при старте сервера
- Удалён дубликат sync-логики (`_merge_json_plans` в `storage_paths.py` + `_sync_local_plans_to_storage` в `plans_manager.py` делали одно и то же)
- Удалён эндпоинт `POST /api/plans/import-from-excel` (импорт через UI больше не нужен)
- Удалён метод `PlansManager.replace_all_plans` (использовался только Excel-импортом)
- `data/plansdashboard.json` (repo-копия) теперь только **seed при первом старте** на чистом диске — если `/kultura/plansdashboard.json` уже есть, repo не влияет ни на что

**Почему:**
Старая логика на каждом рестарте Render безусловно перезаписывала значения на диске значениями из repo, если они отличались. Любые правки, сделанные через дашборд, откатывались после редеплоя. Теперь единственный способ изменить план — вручную через UI, правки живут на диске.

**Файлы:**
- `core/storage_paths.py` — упрощён до одной функции `get_data_path`
- `core/plans_manager.py` — удалён `_sync_local_plans_to_storage`, `_read_json_file_safe`, `replace_all_plans`; убран import `get_local_data_path`
- `routes/dashboard.py` — удалён эндпоинт `/api/plans/import-from-excel`

**Что ломается если изменить неправильно:**
- Если кто-то вернёт sync repo→disk — правки снова будут теряться после рестарта
- CLI-скрипты `scripts/import_export/import_plans_from_excel*.py` оставлены и работают автономно (пишут в `data/plansdashboard.json` локально); использовать только в dev-окружении как одноразовую миграцию

---

### 2026-04-07 — Исследование подключения к бар-10 и бар-ПК

**Что сделано:**
- Подключились к бар-10 (100.98.149.104) через RDP: `1` / `qwe123`
- SSH на бар-10 НЕ работает (порт 22 не отвечает)
- Сертификат КриптоПро на бар-10 просрочен (12.12.2025), владелец: Тюменева О.И.
- Носитель сертификата: Jacarta (USB токен, нельзя экспортировать)
- Тестировали 5+ вариантов SSH-логина на бар-ПК (100.98.149.108) — только sshuser работает
- sshuser НЕ в группе Администраторы, нет прав на повышение (`runas`, `net localgroup /add` — Access Denied)
- cryptcp требует доступ к хранилищу ключей Администратора
- Подпись через cryptcp не проходит валидацию на сервере (NOT_VALID_GOST_SIGNATURE)

**Файлы:**
- `docs/CONNECTIVITY.md` — полный статус подключения ко всем устройствам
- `.claude/INDEX.md` — добавлена ссылка на CONNECTIVITY.md

### 2026-04-05 — Удалённый доступ к бар-ПК

**Что сделано:**
- Настроен Tailscale сеть + OpenSSH Server + paramiko
- Создан `sshuser` учётка, SSH-ключ
- Утилита `remote_exec.py` для удалённого выполнения команд

**Файлы:**
- `docs/remote-sync.md`

### 2026-04-05 — Честный ЗНАК

**Что сделано:**
- Чистка chz_test, единый скрипт chz.py
- Получены сроки годности пива (v4 API, 8500+ записей)

**Файлы:**
- `docs/changelog/CHZ_INTEGRATION.md`
- `chz_test/chz.py`
