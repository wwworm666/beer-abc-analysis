# Changelog

История изменений проекта по сессиям.

---

## 2026-04-26 — Полная интеграция iiko ↔ Честный Знак

**Цель:** автоматизировать получение сроков годности фасовки из ЧЗ
и привязать их к остаткам конкретного бара. Один POST → данные
актуальные, без ручных выгрузок.

**Что построили:**

1. **Стыковка iiko↔ЧЗ по GTIN** (баркоду) — `core/iiko_barcodes.py`
   парсит XML iiko, строит `{gtin: [iiko_pid]}`. Сравнение нормализованных
   14-значных GTIN.

2. **Привязка партий к конкретному бару через КПП** — каждая строка
   CSV-выгрузки `FILTERED_CIS_REPORT` содержит поля `kpp` и `fiasId`.
   У ИНВЕСТАГРО 4 МОД = 4 КПП. Парсер агрегирует `by_kpp: [{kpp, count, batches}]`.
   Endpoint фильтрует по `target_kpp` для конкретного бара. Точные
   данные, не эвристика.

3. **Полная автоматизация через dispenser API:**
   - `POST /api/v3/true-api/dispenser/tasks` — создать задание
   - `GET /api/v3/true-api/dispenser/tasks/{id}` — опросить статус
   - `GET /api/v3/true-api/dispenser/results/{id}/file` — скачать ZIP с CSV
   - Распаковать ZIP, перестроить `chz_stock.json`
   - `POST /api/chz/refresh` запускает SSH-цепочку на бар-ПК
   - Daemon-thread авторефреш в 03:00 (`core/chz_scheduler.py`)
   - Кнопка «Обновить данные ЧЗ» в UI с polling-индикатором

4. **Расширение групп ЧЗ** до `[beer (15), nabeer (22), softdrinks (23)]`
   (water/milk/alcohol выключены — alcohol вообще не в ЧЗ а в ЕГАИС).

5. **Endpoint `GET /api/stocks/expiry?bar=X`** — главная страница
   интеграции. Возвращает фасовку с разбивкой по партиям, привязанным
   к бару. Поля `bar_chz_count` (на КПП этого бара) и `chz_total_count`
   (по всему юрлицу) для UI-предупреждений.

6. **UI вкладка «Сроки годности»** в `templates/stocks.html` —
   таблицы по поставщикам, цветовая подсветка по дням до экспирации,
   предупреждения «касса не RETIRE'ит» когда `bar_chz_count > stock`.

7. **Утилиты для отладки:**
   - `chz_test/probe_gtin.py` — поиск GTIN во всех 13 group ЧЗ
   - `chz_test/suggest_barcode_fixes.py` — авто-подбор настоящих
     GTIN для несматченных позиций (по схожести бренда, score 2-4)
   - `chz_test/export_bartender_list.py` — CSV для бармен-сверки
     с пустой колонкой для заполнения после сканирования бутылки

**Главные открытия:**

- **Каплимит /cises/search 100/страница** — старый прямой режим был
  фундаментально сломан, переход на dispenser API
- **CSV из ЛК ЧЗ уже содержит kpp/fiasId** — мы их игнорировали 2
  месяца, делая бессмысленные эвристики
- **iiko XML устаревал 4 месяца** — refresh поднял match rate +146%
- **status=APPLIED + participantInn=наш = 0 кодов** (APPLIED у producer-а)
- **alcohol (group 11) маркируется ЕГАИС, не ЧЗ** — для пива не нужна
- **01.12.2025 — водораздел** обязательного поэкземплярного учёта
  бутылок (ПП РФ № 1415 от 13.09.2025). Старые остатки не появятся
  ни в каком отчёте — это легитимно
- **Иногда iiko-баркод не совпадает с DataMatrix** — Кулинар-кейс,
  починка через бармен-сверку

**Финальные цифры:**

| Бар | Всего фасовки | С CHZ-данными |
|---|---|---|
| Большой пр. В.О | 160 | 96 |
| Лиговский | 115 | 76 |
| Кременчугская | 158 | 80 |
| Варшавская | 116 | 65 |
| Общая (юрлицо) | 366 | 241 |

Из 125 несматченных:
- ~80 — легитимные остатки до 01.12.2025 (ничего не сделать)
- ~30 — импорт без подписания УПД через ЭДО (звонки поставщикам)
- ~10 — баркод-несоответствие (бармен-сверка)
- ~5 — товары в группах вне доступа (alcohol)

**Файлы:**

- `chz_test/chz.py` — переписан: dispenser_*, csv-auto, mods, парсер
  с support UTF-8/cp1251/ZIP
- `routes/stocks.py` — `/api/stocks/expiry`, `/api/chz/refresh{,/status}`
- `core/iiko_barcodes.py` (новый) — баркод-карта из XML
- `core/chz_scheduler.py` (новый) — daemon-thread авторефреш
- `remote_exec.py` — добавлен `run csv-auto` спец-режим, ALLOWED_SUBCMDS
  расширены `csv-auto`, `mods`
- `templates/stocks.html` — вкладка «Сроки годности» с polling-кнопкой
- `app.py` — стартует scheduler при наличии `REMOTE_PASS`
- `chz_test/probe_gtin.py`, `chz_test/suggest_barcode_fixes.py`,
  `chz_test/export_bartender_list.py` — утилиты
- `chz_test/debug/chz_stock.json` — изменилась структура (добавлено
  `by_kpp`, `batches`)
- `chz_test/debug/mods.json` (новый) — справочник 4 МОД
- `data/cache/nomenclature__products.xml` — обновлён со старого декабря 2025

**Документация:**

- `.claude/docs/chz-stock-integration.md` (новый) — полное описание
  системы, главный референс
- `.claude/docs/stocks.md` — добавлен указатель на новый документ
- `.claude/docs/lessons.md` — добавлены уроки 11-19 (каплимит API,
  КПП-привязка, ZIP-формат, поэтапные даты маркировки и т.д.)
- `.claude/INDEX.md` — добавлена строка для нового документа
- `docs/CHANGELOG.md` — детальные хронологические записи по дням

См. подробности: [chz-stock-integration.md](chz-stock-integration.md).

---

## 2026-04-07 -- Fix /stocks: replace /products XML with OLAP TRANSACTIONS for nomenclature

**Проблема:** страница /stocks возвращала 500/502. Корневая причина: iiko endpoint `/products` (XML) не успевает вернуть 7840+ товаров -- обрывается после ~186 сек ("Response ended prematurely"). Номенклатура = None, все 3 endpoint'а stocks падают.

**Решение:** получать номенклатуру через OLAP TRANSACTIONS вместо `/products`:
- OLAP возвращает 873 товара за 2-3 сек (vs 186+ сек у `/products`)
- Формат: `Product.Id`, `Product.Name`, `Product.Type`, `Product.MeasureUnit`, `Product.Category`, `Product.TopParent`
- 3-уровневый кэш: memory (15 мин) -> disk (24ч) -> iiko API
- Bottles: фильтрация по `Product.TopParent == "Напитки Фасовка"` вместо рекурсии по GUID

**Что изменено:**
- `core/olap_reports.py`: `get_nomenclature()` -> `_get_nomenclature_via_olap()` (основной) + `_get_nomenclature_via_xml()` (fallback)
- `core/olap_reports.py`: timeout'ы: auth=30s, nomenclature XML=300s, store operations=60s
- `core/iiko_api.py`: timeout=30s для auth, timeout=5s для logout
- `extensions.py`: disk cache для номенклатуры (`data/nomenclature_cache.json`, TTL 24h)
- `routes/stocks.py`: bottles фильтрует по имени группы (OLAP) или GUID (XML fallback)
- `templates/stocks.html`: параллельная загрузка (`Promise.allSettled`), `fetchWithRetry()` при 502
- `render.yaml`: `--workers 2`, timeout 120s

**Результат:** taplist 6.6s, bottles 9.2s, kitchen 9.3s (параллельно ~10s суммарно)

**Файлы:** `core/olap_reports.py`, `core/iiko_api.py`, `extensions.py`, `routes/stocks.py`, `templates/stocks.html`, `render.yaml`

---

## 2026-04-04 — Оптимизация OLAP для KPI + исправление отображения формулы

### Оптимизация OLAP (4 запроса -> 2)

**Проблема:** страница /salary загружалась ~60 секунд. 4 параллельных OLAP запроса с группировкой по DishName x Store x Date возвращали тысячи строк.

**Решение:** новый метод `get_kpi_olap_data()` делает 2 легковесных запроса:
1. Summary: `groupBy [WaiterName]` — чеки, выручка, скидки (~30-50 строк)
2. Categories: `groupBy [WaiterName, DishGroup.TopParent]` — доли категорий, наценка (~100-200 строк)

OLAP-сервер агрегирует данные сам, вместо передачи тысяч строк клиенту.

**Что изменено:**
- `core/olap_reports.py`: добавлен `get_kpi_olap_data()` — 2 запроса вместо 4
- `routes/employee.py`: KPI route использует `get_kpi_olap_data()` + `_build_kpi_metrics()` вместо `ThreadPoolExecutor` с 4 запросами + `EmployeeMetricsCalculator`
- `routes/employee.py`: добавлены `_find_employee_in_olap()`, `_build_kpi_metrics()` — сборка метрик из лёгких OLAP данных

**Побочные эффекты:** `AuthUser` заменён на `WaiterName` для KPI (единообразие с категориями). Dashboard не затронут.

### Исправление отображения формулы KPI

**Было:** каждый KPI = `множитель x 5000`, итого = `сумма x коэфф.смен`
**Стало:** каждый KPI = `коэфф.смен x множитель x 5000`, итого = простая сумма трёх

**Файл:** `templates/bonus.html`

Математический результат идентичен: `k*(a+b+c) = k*a + k*b + k*c`.

### Исправление timeout (из начала сессии)

- `core/olap_reports.py`: добавлен `timeout=90` в `get_employee_aggregated_metrics`
- `core/olap_reports.py`: добавлен `timeout=60` в `get_employee_daily_revenue`
- `routes/employee.py`: проверка `aggregated_data is None` (сейчас заменено новым подходом)

---

## 2026-04-03 — Рефакторинг системы планов: удаление bar_plans.json, целевая регенерация, исправление импорта

**Проблемы, которые были найдены и исправлены:**

1. **Удалён `bar_plans.json`** — legacy файл с русскими названиями баров, дублировал `daily_plans.json`. Теперь `employee_plans.py` читает только `daily_plans.json`.

2. **`PlansManager.save_plan()` — пересчёт daily_plans только для затронутого заведения/месяца.** Раньше `save_plan()` вызывал полную пересборку всех ежедневных планов для всех заведений и месяцев. Теперь `save_plan_with_regeneration()` парсит `venue_YYYY-MM` из period_key и пересчитывает только один месяц одного заведения.

3. **Excel import — удаление dead code.** После первого `return jsonify()` оставался блок (строки 398-426), который писал данные напрямую в файл и снова вызывал `regenerate_daily_plans()`. Это было недостижимым мёртвым кодом. Также исправлена кодировка в `source` строке.

4. **BAR_NAME_MAPPING оставлен в `employee_plans.py`** — единственный источник маппинга, импортируется из `kpi_calculator.py` и `routes/employee.py`.

5. **`DailyPlansGenerator.regenerate_for_venue_month()`** — новый метод для точечной регенерации одного месяца одного заведения.

**Изменённые файлы:**
- `core/employee_plans.py` — переписан: читает только `daily_plans.json`, удалён `bar_plans.json`
- `core/daily_plans_generator.py` — добавлен `regenerate_for_venue_month()`, `regenerate_daily_plan_for_venue_month()`
- `core/plans_manager.py` — `save_plan()` больше не вызывает регенерацию; добавлен `save_plan_with_regeneration()`
- `routes/dashboard.py` — `save_plan_with_venue()` теперь вызывает `save_plan_with_regeneration()`; удалён dead code в Excel импорте
- `data/bar_plans.json` — удалён

**Затронутые функции:**
- `get_employee_plan_by_shifts()` — теперь читает `daily_plans.json` напрямую
- `PlansManager.save_plan()` — больше не регенерирует daily plans (callers должны использовать `save_plan_with_regeneration()`)
- `PlansManager.save_plan_with_regeneration()` — новый метод
- `DailyPlansGenerator.regenerate_for_venue_month()` — новый метод

---

## 2026-04-01 — Вики: Расчёт премий (бонусы + KPI)

**Что сделано:**
- Обновлён раздел `# Расчёт премий` в `wiki/content.md`
- Добавлена полная формула бонуса (дневной расчёт + прогрессивный штраф)
- Добавлена премия за передачу смены (500 ₽ × смены)
- Добавлен пример расчёта с таблицей по дням
- Добавлен раздел KPI-бонус с формулой и примером
- Добавлено описание взвешенных целей для разных локаций
- Обновлён `.claude/docs/employee.md` с разделом Frontend

**Изменённые файлы:**
- `wiki/content.md` — разделы "Расчёт премий" (бонусы + KPI + формулы)
- `.claude/docs/employee.md` — добавлен раздел Frontend (вкладки, метрики, чарты)

**Формулы в вики:**
```
Бонус за смену = 1 000 ₽ + (Выручка − План) × 5%
Штраф за опоздания = 250 × n × (n+1) / 2  (прогрессивный)
Премия за смены = 500 ₽ × shifts_count
KPI premium = ratio × Смены × (5 000 / 15)
```

---

## 2026-04-01 — Дизайн-система проекта

**Что сделано:**
- Создана полная документация дизайн-системы на основе dashboard.html
- Документированы все компоненты: карточки, кнопки, инпуты, таблицы, badges, tooltips
- Описаны цветовые палитры (light/dark темы)
- Зафиксирована типографика IBM Plex Mono
- Добавлены правила адаптивности и breakpoints
- Описаны анимации и transition timing

**Зачем:**
- Новые страницы должны создаваться в едином стиле
- Документация служит руководством для Claude при создании UI
- Предотвращает дублирование стилей и изобретение велосипедов

**Созданные файлы:**
- `.claude/docs/design-system.md` — полная дизайн-система (цвета, компоненты, layout, адаптивность)

**Изменённые файлы:**
- `.claude/INDEX.md` — обновлена ссылка на design-system.md

**Как применять:**
1. При создании новой страницы использовать компоненты из design-system.md
2. Не изобретать новые стили — использовать CSS переменные
3. Для новых компонентов расширять систему, а не дублировать

---

## 2026-04-01 — Исправление маппинга баров для daily_plans.json и KPI

**Проблема 1:** Страница ЗП (`/salary`) не отображала планы по дням за март
- `BAR_NAME_MAPPING` в `core/employee_plans.py` возвращал русские названия
- `daily_plans.json` использует английские ключи (`kremenchugskaya`, `bolshoy`)
- Планы не находились по ключу → `day_plan = 0`

**Проблема 2:** KPI-премия не рассчитывалась
- `kpi_calculator.py` маппил на английские ключи
- `kpi_targets.json` хранит цели с русскими названиями
- Цели не находились → KPI premium = 0

**Решение:**
1. `BAR_NAME_MAPPING` в `core/employee_plans.py` → английские ключи (для `daily_plans.json`)
2. `kpi_calculator.py` → добавлен `RUSSIAN_BAR_NAMES` для обратного маппинга (для `kpi_targets.json`)
3. `count_shifts_per_location()` → возвращает русские названия

**Изменённые файлы:**
- `core/employee_plans.py` — маппинг на английские ключи
- `core/kpi_calculator.py` — обратный маппинг на русские для KPI targets
- `.claude/docs/employee.md` — обновлена документация

**Результат:**
- Планы отображаются корректно в расчёте ЗП
- KPI-премия рассчитывается верно
- Weekend weighting работает (Пт/Сб = 2x)

---

## 2026-04-01 — Двухфайловая система планов выручки

**Проблема:**
- Планы хранятся в одном файле `bar_plans.json` без автоматического расчёта weekend weighting
- Нет UI для редактирования планов
- Ежедневные планы нужно поддерживать вручную

**Решение:**
- Разделены планы на 2 файла:
  1. `plansdashboard.json` — месячные планы (16 метрик, редактируются через UI)
  2. `daily_plans.json` — ежедневные планы (авто-расчёт из месячных)
- Создан `core/daily_plans_generator.py` — расчёт daily plans с weekend weighting (Пт/Сб = 2x)
- UI дашборда при сохранении месячного плана авто-генерирует `daily_plans.json`
- Все модули обновлены на использование `get_daily_plan_for_date()`

**Формула расчёта:**
```
weight(день) = 2.0 если Пт(4) или Сб(5), иначе 1.0
month_weight = Σ(weight(день) для всех дней месяца)
plan_per_weight = monthly_revenue / month_weight
daily_plan = plan_per_weight × weight(день)
```

**Пример (Октябрь 2025):**
- 22 будних × 1.0 + 9 выходных × 2.0 = 40 весовых единиц
- План на будни: 1 201 750 / 40 × 1 = 30 044 ₽
- План на Пт/Сб: 1 201 750 / 40 × 2 = 60 088 ₽

**Изменённые файлы:**
- `core/daily_plans_generator.py` — создан (расчёт daily plans)
- `core/plans_manager.py` — авто-генерация `daily_plans.json` при сохранении
- `routes/employee.py` — использует `get_daily_plan_for_date()` для bonus/KPI
- `core/revenue_metrics.py` — использует `get_daily_plan_for_date()` для метрик
- `static/js/dashboard/modules/plans.js` — авто-расчёт weighted markup и revenue по категориям
- `.claude/docs/venues-plans.md` — документация двухфайловой системы

**Результат:**
- Планы редактируются через UI дашборда (16 метрик)
- Ежедневные планы считаются автоматически с учётом weekend weighting
- Страница ЗП (/salary) использует daily_plans.json для расчёта премий
- Dashboard использует monthly plans для пропорционального расчёта периода

---

## 2026-04-01 — Исправление матчинга имён в KPI (Средний чек)

**Проблема:**
- Средний чек рассчитывался неверно у некоторых сотрудников (расхождение до 100-500 ₽)
- Причина: отчёты по категориям использовали `WaiterName`, агрегированный — `AuthUser`
- `WaiterName` и `AuthUser` могут отличаться для одного сотрудника

**Решение:**
- Все OLAP отчёты теперь используют `AuthUser` ("Авторизовал")
- `_filter_by_employee()` фильтрует по точному совпадению `AuthUser`
- Матчинг больше не нужен — данные консистентны

**Изменённые файлы:**
- `core/olap_reports.py` — `_build_olap_request()`: `AuthUser` вместо `WaiterName`
- `core/employee_analysis.py` — `_filter_by_employee()`: упрощён до точного совпадения
- `.claude/docs/employee.md` — обновлён раздел "Матчинг имён"

**Формула среднего чека (теперь корректная):**
```
Средний чек = Выручка OLAP (из AuthUser) / Чеки OLAP (из AuthUser)
Доли категорий = Выручка категории (из AuthUser) / Общая выручка (из AuthUser)
```

**Результат:**
- Средний чек теперь считается по всем чекам сотрудника
- Расхождение с ручным отчётом < 1%

---

## 2026-04-01 — UI: Расширенные карточки статистики в анализе проливов

**Что сделано:**
- Добавлены 4 карточки статистики вместо 1:
  1. **Общий объём** (литры)
  2. **Средняя цена за литр** (₽/л)
  3. **Средний объём на пиво** (литры/позиция)
  4. **Всего порций** (шт)
- Метрики рассчитываются на frontend из данных API

**Изменённые файлы:**
- `templates/draft.html` — функция `createBarSection()`, добавлены 4 карточки в `stats-grid`

**Формулы:**
```
Средняя цена за литр = Total Revenue / Total Liters
Средний объём на пиво = Total Liters / Total Beers (позиций)
```

**Результат:**
- Пользователь видит больше контекстной информации
- Быстрая оценка средней стоимости и объема

---

## 2026-03-31 — Премия за передачу смены + Авто-часы

**Что сделано:**
- Добавлена премия за передачу смены: **500 ₽ × количество смен**
- Backend возвращает `shift_handover_bonus` в API `/api/bonus-calculate`
- Frontend показывает премию за передачу смены отдельной строкой
- Backend возвращает `total_hours` из кассовых смен в API ответов
- Frontend показывает автоматические часы по умолчанию с пометкой "(авт)"
- Сохранена возможность ручного редактирования часов

**Изменённые файлы:**
- `routes/employee.py` — добавлено `shift_handover_bonus` и `total_hours`
- `templates/bonus.html` — отображение премии и авто-часов
- `.claude/docs/employee.md` — добавлены разделы "Премия за передачу смены" и "Расчёт часов работы"

**Формулы:**
```
Премия за передачу смены = 500 ₽ × смены
Часы работы = Σ(close_time - open_time) по всем сменам
```

**Результат:**
- Автоматический расчёт премии за каждую смену
- Часы считаются автоматически из iiko cashshifts API
- Пользователь видит авто-значения, но может переопределить вручную

---

## 2026-03-31 — Исправление анализа проливов (Draft Beer Analysis)

**Что сделано:**
- Улучшен парсинг названий: 5 паттернов вместо 3, поддержка форматов без скобок
- Добавлена эвристика для нераспознанных объемов (вместо удаления записей)
- Внедрена двухэтапная нормализация: BeerNameOriginal (для маппинга) + BeerNameNorm (для группировки)
- Исправлен расчет BeerSharePercent: считается для каждого бара отдельно (сумма = 100%)
- Оптимизирован маппинг поставщиков: O(1) поиск вместо O(n²) цикла
- Написано 30 unit-тестов для проверки всех исправлений

**Изменённые файлы:**
- `core/draft_analysis.py` — `_clean_beer_name()`, `_estimate_volume()`, `extract_beer_info()`, `prepare_draft_data()`, `get_beer_summary()`
- `routes/analysis.py` — исправлена обработка OLAP даты, улучшен логгинг
- `scripts/import_export/export_draft_sales.py` — `build_optimized_mappings()`, `get_supplier_optimized()`

**Созданные файлы:**
- `tests/test_draft_analysis.py` — 30 unit-тестов (парсинг, нормализация, BeerSharePercent)
- `.claude/docs/draft-beer-fixes.md` — документация всех исправлений
- `.claude/docs/draft-beer-errors.md` — ошибки и проблемы анализа проливов

**Результат:**
- Потеря данных снижена с ~2-5% до < 0.1%
- Поддержка 10+ форматов названий
- Скорость маппинга поставщиков увеличена в 2-3x
- > 70% записей с поставщиком (было ~40-60%)
- Сумма BeerSharePercent = 100% ±0.1% для каждого бара

---

## 2026-03-31 — RFM-сегментация гостей в анализе скидок

**Что сделано:**
- Добавлен трекинг дат визитов через `OpenDate.Typed` в OLAP-запросе
- Реализован расчёт RFM-метрик: `recency_days`, `frequency_per_week`, `visit_dates`, `active_days`
- Создана сегментация гостей: CHAMPIONS, CHURNED, AT_RISK, NEW, LOYAL, POTENTIAL
- Добавлены RFM-карточки: средний recency, % ушедших, % в риске, частота (раз/нед)
- Обновлена таблица гостей: статус сегмента, последний визит, частота, средний чек
- Реализованы фильтры: по сегменту, recency (0-7, 8-14, 15-30, 31-60, 60+ дней), частоте
- Добавлена гистограмма распределения по recency (5 бакетов)
- Создан scatter plot (Frequency vs Recency) с кликабельными точками
- Реализован экспорт отфильтрованных гостей в CSV
- Обновлена модалка гостя: timeline визитов, детали RFM-метрик

**Изменённые файлы:**
- `core/olap_reports.py` (строки 1470-1479) — добавлено `OpenDate.Typed` в groupByRowFields
- `routes/analysis.py` (строки 925-1050) — сохранение visit_dates, расчёт recency_days, frequency_per_week
- `templates/discounts.html` — RFM-карточки, фильтры, scatter plot, экспорт CSV, timeline визитов

**Созданные файлы:**
- `.claude/docs/discounts.md` — полная документация RFM-сегментации (архитектура, формулы, сценарии использования)

**Обновлённые файлы:**
- `.claude/INDEX.md` — добавлена запись в changelog

**Зачем:**
SMM-специалист теперь может:
- Выявлять ушедших гостей (60+ дней не ходили) для winback-кампаний
- Находить гостей "в риске" (31-60 дней) для превентивных акций
- Сегментировать по частоте и давности визитов
- Экспортировать списки для email/SMS-рассылок
- Видеть паттерны: "ходил 3 раза в неделю, с 28 февраля не приходил"

---

## 2026-03-31 — Документация ошибок анализа проливов

**Что сделано:**
- Создан полный документ ошибок и проблем анализа разливного пива
- Описаны критические ошибки (парсинг объема, нормализация, BeerSharePercent)
- Добавлены скрипты диагностики для каждой проблемы
- Описаны проблемы производительности и UI/UX

**Созданные файлы:**
- `.claude/docs/draft-beer-errors.md` — 6 критических ошибок, 4 проблемы производительности, 2 UI/UX проблемы, чеклист диагностики

**Изменённые файлы:**
- `.claude/docs/INDEX.md` — добавлена ссылка на draft-beer-errors.md

---

## 2026-03-31 — UI управления планами дашборда (v3)

**Что сделано:**
- Восстановлена вкладка "Планы" в навигации дашборда
- Добавлен UI для создания, редактирования, удаления планов
- Реализовано модальное окно с 5 секциями (16 метрик)
- Добавлена валидация: сумма долей 100% ±1%, неотрицательность значений
- Авто-расчёт производных метрик (выручка по категориям)
- Планы сохраняются в `data/plansdashboard.json` на Render disk

**Как работает:**
- Кнопки "Создать план"/"Редактировать" открывают модальное окно
- В модальном окне: выбор Месяц, Год, Заведение
- План загружается **автоматически** при изменении любого селектора
- Если план найден — показывается для редактирования + кнопка "Удалить"
- Если план не найден — создаётся пустой шаблон для заполнения
- Кнопка "Сохранить" — всегда видна когда секция метрик активна

**Изменённые файлы:**
- `templates/dashboard/base.html` — добавлена кнопка "Планы" и контент вкладки
- `templates/dashboard/plans_tab.html` — полный редизайн с кнопками и модальным окном
- `static/js/dashboard/main.js` — раскомментирован `plansViewer.init()`
- `static/js/dashboard/modules/plans.js` — добавлены функции create/edit/save/delete/validate
- `.claude/docs/venues-plans.md` — документация UI управления планами

**Ключевые функции:**
- `createPlan()` — создание плана (с авто-расчётом из месячных данных)
- `editPlan()` — редактирование текущего плана
- `savePlan()` — сохранение с валидацией
- `deletePlan()` — удаление с подтверждением
- `validatePlanData()` — проверка всех обязательных полей
- `autoCalculateDerivedMetrics()` — авто-расчёт revenueDraft/Packaged/Kitchen

---

## 2026-03-27 — Восстановление документации

**Что сделано:**
- Создана полная документация проекта в `.claude/docs/`
- Обновлён `.claude/CLAUDE.md` с новыми принципами (детерминированные вычисления, документация, changelog)

**Созданные файлы:**
- `INDEX.md` — навигация по всем документам
- `overview.md` — архитектура проекта, стек, структура
- `iiko-integration.md` — интеграция с iiko API, формулы, критические особенности
- `dashboard.md` — 15 метрик дашборда, планы, weekend weighting
- `abc-xyz-analysis.md` — ABC/XYZ анализ, формулы расчётов
- `employee.md` — метрики сотрудников, KPI, матчинг имён
- `taps.md` — управление кранами, thread-safe операции
- `venues-plans.md` — торговые точки, пропорциональный расчёт планов
- `schedule.md` — график смен, meeting notes
- `frontend.md` — JavaScript архитектура, state management
- `stocks.md` — остатки, Честный ЗНАК API
- `lessons.md` — баги, паттерны, решения
- `CHANGELOG.md` — этот файл

**Изменённые файлы:**
- `.claude/CLAUDE.md` — сокращён до 3 главных принципов

---

## 2026-03-XX — Предыдущие изменения

*Добавляйте новую запись в начало списка после каждой сессии разработки*

### Формат записи

```markdown
## YYYY-MM-DD — <краткое описание сессии>

**Что сделано:**
- Список изменений
- ...

**Изменённые файлы:**
- `path/to/file.py` — описание
- ...

**Созданные файлы:**
- `path/to/new/file.py` — описание
```
