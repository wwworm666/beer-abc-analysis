# Аудит OLAP-отчётов — 2026-06-02

> Полный аудит OLAP-отчётов проекта (24 запроса, см. [OLAP_REPORTS_COLLECTION.md](../OLAP_REPORTS_COLLECTION.md)).
> Задача — найти ошибки, возможности оптимизации, рассогласования и отклонения от спецификации iiko
> ([OLAP_REPORT_BUILDING_RULES.md](../OLAP_REPORT_BUILDING_RULES.md)). **Правки НЕ вносились — только аудит.**
> Каждая сырая находка прошла состязательную верификацию (отдельный скептик перечитывал код и пытался её опровергнуть);
> подтверждённые находки сведены в консолидированные issue (одна корневая проблема = один issue).

## Резюме

- Сырых находок (6 линз): **42**; отклонено верификацией: **2**.
- После консолидации дубликатов между линзами: **26 уникальных issue**.
- Критичность: **0 critical**, **4 high**, **6 medium**, **16 low**.

| Severity | Ошибки | Оптимиз. | Согласов. | Надёжн. | Спец. | Dead | Σ |
|---|---|---|---|---|---|---|---|
| **HIGH** | 2 |  | 1 | 1 |  |  | 4 |
| **MEDIUM** |  | 2 | 2 | 1 | 1 |  | 6 |
| **LOW** | 1 | 5 | 3 | 4 |  | 3 | 16 |

Приоритет (critical/high), 4:

- **[HIGH · ERROR]** Отмены/возвраты агрегируют OrderNum как «количество удалённых чеков» вместо UniqOrderId.OrdersCount — `core/olap_reports.py:1176-1178`
- **[HIGH · ERROR]** get_store_operations_report принимает bar_name, но фильтр по складу закомментирован (TODO) — данные не скоупятся по бару — `core/olap_reports.py:504-564`
- **[HIGH · CONSISTENCY]** Выручка/чеки сотрудника берутся по AuthUser, а категории/доли — по WaiterName: разные ключи идентичности в одном отчёте — `core/olap_reports.py:1230-1231`
- **[HIGH · ROBUSTNESS]** Отсутствует единый retry/таймаут-бюджет под gunicorn --timeout 120с: бюджеты превышают лимит, таймауты разнобойны, ретрай неполон и неконсистентен — `core/olap_reports.py:460-502`

## Метод

Многоагентный workflow: 6 линз ревью параллельно (семантика, производительность, согласованность, надёжность, спецификация, мёртвый код) -> на каждую находку отдельный скептик-верификатор (перечитывает код, пытается опровергнуть; при неуверенности отклоняет) -> критик полноты -> консолидация дубликатов между линзами. Источники: `core/olap_reports.py`, потребители в `routes/`, downstream в `core/`, `extensions.py`, справочники `docs/technical/OLAP_REPORTS_COLLECTION.md` / `OLAP_REPORT_BUILDING_RULES.md` / `audits/OLAP_REQUEST_REGISTRY_2026-04-03.md`.

Severity: critical = неверные числа в проде или падение; high = заметно неверные/несогласованные данные либо явный риск; medium = ощутимая неэффективность/хрупкость; low = косметика/мелочи.

---

## Находки

## ERROR — Ошибки корректности (3)

### 1. [HIGH] Отмены/возвраты агрегируют OrderNum как «количество удалённых чеков» вместо UniqOrderId.OrdersCount

- ID: `cancelled_orders_aggregate_ordernum` · источники: `cancelled_orders_ordernum_not_unique`, `cancelled_uses_ordernum_not_uniqorderid`, `cancelled_aggregates_ordernum_not_orderscount`
- Где: `core/olap_reports.py:1176-1178`; `core/employee_analysis.py:148`; `routes/employee.py:795`; `core/kpi_calculator.py:34`; `core/kpi_calculator.py:47`; `core/kpi_calculator.py:238`
- Затронутые отчёты: `cancelled_orders_request (#8 get_cancelled_orders_by_waiter)`
- Проблема: Запрос отмен/возвратов (_build_cancelled_orders_request) группируется только по WaiterName и агрегирует OrderNum, а downstream суммирует результат как «количество удалённых чеков». OrderNum в iiko — порядковый, НЕ глобально уникальный номер чека (повторяется между сменами/днями/барами), поэтому агрегат даёт сумму номеров, а не счётчик отмен; для подсчёта числа чеков по контракту служит UniqOrderId.OrdersCount, который проект использует во всех остальных отчётах.
- Влияние: Метрика cancelled_count в карточке сотрудника (/employee), в employee-analytics и в KPI/бонусном расчёте (/api/kpi-calculate) считается принципиально неверным и несопоставимым с остальными отчётами способом — выводит сумму порядковых номеров вместо числа отмен, нестабильна между периодами и может быть завышена/занижена.
- Рекомендация (НЕ применена): Заменить aggregateFields в _build_cancelled_orders_request на ['UniqOrderId.OrdersCount'] (или DishAmountInt для позиций) и читать record.get('UniqOrderId.OrdersCount') в employee_analysis.py:148 и employee.py:795. Не применять без сверки с живым /columns и пересчёта эталонного числа отмен в iiko UI. Расхождение уже зафиксировано в OLAP_REPORT_BUILDING_RULES.md:437.

### 2. [HIGH] get_store_operations_report принимает bar_name, но фильтр по складу закомментирован (TODO) — данные не скоупятся по бару

- ID: `store_operations_bar_filter_dead_todo` · источники: `store_operations_bar_filter_dead_todo`
- Где: `core/olap_reports.py:504-564`; `core/olap_reports.py:530-533`; `routes/stocks.py:444`; `routes/stocks.py:503-513`; `routes/stocks.py:634`; `routes/stocks.py:972`; `routes/stocks.py:1202`; `routes/stocks.py:1258-1264`; `routes/expiration.py:119-125`; `routes/expiration.py:210-217`; `routes/expiration.py:252`; `docs/OLAP_REPORTS_COLLECTION.md:1448`
- Затронутые отчёты: `get_store_operations_report`, `stocks: velocity/avg_sales (routes/stocks.py)`, `expiration: board avg_sales/velocity (routes/expiration.py)`
- Проблема: Метод имеет сигнатуру get_store_operations_report(date_from, date_to, bar_name=None) и все 4 прод-вызова передают конкретный bar_name, но внутри фильтр по складу не реализован — висит закомментированным TODO, параметр stores в запрос /reports/storeOperations не уходит. Метод всегда возвращает операции по ВСЕМ барам; потребители НЕ проверяют store у записи операции, поэтому outgoing суммируется по всем барам и приписывается одному (один и тот же SKU встречается на нескольких складах).
- Влияние: avg_sales/velocity для товаров в нескольких барах завышается (суммируются продажи всех баров), искажая рекомендации пополнения и оценку риска списания/срока годности на /expiration и /stocks. В expiration.py эффект усиливается: N параллельных запросов возвращают идентичные all-bars данные — лишняя сетевая/серверная нагрузка (N одинаковых тяжёлых XML-выгрузок вместо одной).
- Рекомендация (НЕ применена): Либо реализовать серверный фильтр (передавать stores=store_id в params, смапив bar_name->store_id через stocks store_id_map / expiration _STORE_ID_MAP), либо, раз набор store_id известен потребителям, фильтровать операции по r.get('store')==target_store на стороне потребителя и делать ОДИН общий запрос storeOperations (как уже сделано для balances). Убрать вводящий в заблуждение мёртвый параметр bar_name либо честно его задействовать.

### 3. [LOW] RevenueMetricsCalculator считает «общую выручку» только по фасовке (get_beer_sales_report фильтрован Напитки Фасовка)

- ID: `revenue_metrics_fasovka_only` · источники: `revenue_metrics_fasovka_only`
- Где: `core/revenue_metrics.py:128-129`; `core/olap_reports.py:812`; `core/olap_reports.py:852-855`; `core/dashboard_analysis.py:54`
- Затронутые отчёты: `olap_request_base draft=False (#5)`, `all_sales_olap_request (#4)`
- Проблема: _calculate_actual_revenue() для метрики «Текущая выручка» вызывает get_beer_sales_report(), тело которого жёстко фильтрует DishGroup.TopParent=['Напитки Фасовка']. То есть «общая фактическая выручка» = только фасованное пиво, без розлива и кухни, что противоречит определению выручки на дашборде (сумма всех категорий из get_all_sales_report).
- Влияние: Любой потребитель RevenueMetricsCalculator.get_metrics получит выручку, заниженную на величину розлива и кухни, и неверный % плана. Живых route-вызовов get_metrics сейчас нет (только __main__ и regression-тест), поэтому в проде дремлет, но при подключении даст неверные числа. Зафиксировано как L-001 в LOGIC_DEFECT_REGISTER_2026-04-03.md.
- Рекомендация (НЕ применена): Заменить источник на get_all_sales_report() + DashboardMetrics (как dashboard) либо на запрос без фильтра по DishGroup.TopParent. До исправления не подключать get_metrics к боевым роутам; пометить/удалить класс как dead, если не нужен.

---

## OPTIMIZATION — Оптимизация и производительность (7)

### 4. [MEDIUM] UniqOrderId.Id в groupByRowFields самого горячего запроса даёт фан-аут строк (чек×блюдо×день), раздувая ответ

- ID: `all_sales_uniqorderid_id_fanout` · источники: `uniqorderid_id_fanout_in_all_sales`, `all_sales_uniqorderid_id_fanout`
- Где: `core/olap_reports.py:758-765`; `core/olap_reports.py:768`; `core/dashboard_analysis.py:62`; `core/dashboard_analysis.py:245-271`; `core/olap_reports.py:464-465`
- Затронутые отчёты: `all_sales_olap_request (#4 get_all_sales_report)`
- Проблема: В groupByRowFields комплексного запроса присутствует UniqOrderId.Id (UUID каждого заказа), что превращает грид из агрегата по (Store×Dish×Day) в одну строку на каждую позицию каждого чека — кардинальность растёт на порядок-два. Поле нужно лишь для подсчёта уникальных чеков через set() в _count_unique_orders, хотя у запроса уже есть агрегат UniqOrderId.OrdersCount, считаемый сервером без фан-аута. Числа при этом корректны (суммы не зависят от гранулярности), поэтому severity не critical.
- Влияние: Многократно больший JSON-ответ и время счёта на iiko на самом частом эндпоинте дашборда/выручки/виджета; на длинных периодах/всех барах объём данных кратно растёт, повышая риск ReadTimeout и нагрузку на сервер.
- Рекомендация (НЕ применена): Убрать UniqOrderId.Id из groupByRowFields и считать чеки по агрегату UniqOrderId.OrdersCount (как get_orders_count/_build_orders_count_request с группировкой только Store.Name+OpenDate.Typed), либо вынести подсчёт чеков в отдельный лёгкий запрос/summary. Проверить, что total_checks не изменится семантически, и что месяц×все бары не упирается в таймаут.

### 5. [MEDIUM] explorer.py кэширует в обход single-flight cached_olap — нет защиты от стампеда на самом тяжёлом запросе

- ID: `explorer_bypasses_single_flight_cache` · источники: `explorer_bypasses_single_flight`
- Где: `core/explorer.py:57-82`; `routes/dashboard.py:64`; `routes/dashboard.py:612`; `core/extensions.py:95-127`
- Затронутые отчёты: `explorer_sales`
- Проблема: _fetch_raw_sales делает собственную проверку и запись DASHBOARD_OLAP_CACHE напрямую, не вызывая cached_olap() с per-key inflight-локом. Самый тяжёлый retry-запрос (get_explorer_sales) не защищён от стампеда: N одновременных запросов /explorer с одинаковым ключом запустят N параллельных дорогих OLAP внутри воркера, тогда как dashboard/revenue используют тот же кэш через cached_olap с double-checked locking.
- Влияние: Параллельные открытия /explorer на одном периоде/баре умножают самый дорогой OLAP-запрос, повышая риск исчерпания воркеров и таймаутов; защита от стампеда, построенная для дашборда, на explorer не распространяется.
- Рекомендация (НЕ применена): Переписать _fetch_raw_sales на extensions.cached_olap(cache_key, fetch_fn), где fetch_fn инкапсулирует connect/get_explorer_sales/disconnect, убрав ручную работу с DASHBOARD_OLAP_CACHE. Это даст single-flight и единообразную eviction-логику.

### 6. [LOW] DishForeignName в groupByRowFields продакшн-запросов не потребляется downstream — лишнее измерение грида

- ID: `dishforeignname_unused_grouping` · источники: `dishforeignname_unused_grouping`
- Где: `core/olap_reports.py:619`; `core/olap_reports.py:762`; `core/olap_reports.py:819`; `core/olap_reports.py:1122`
- Затронутые отчёты: `all_sales_olap_request`, `kitchen_olap_request`, `olap_request_base (beer/draft/bottles)`, `kitchen_olap_request_with_waiter`
- Проблема: Поле DishForeignName включено в группировку строк во всех основных SALES-запросах, но downstream-обработчики (DashboardMetrics, EmployeeMetricsCalculator, WaiterAnalysis, DraftAnalysis, BeerDataProcessor) нигде его не читают. Лишнее измерение увеличивает кардинальность грида без пользы.
- Влияние: Раздувание ответа и нагрузка на сервер пропорционально числу различающихся значений DishForeignName — чистый оверхед без потребителя.
- Рекомендация (НЕ применена): Удалить DishForeignName из groupByRowFields во всех перечисленных builders, предварительно grep-ом по всему репозиторию (включая фронтенд/экспорт) подтвердив отсутствие потребителей.

### 7. [LOW] buildSummary=false не задан на тяжёлых SALES-запросах — сервер зря считает summary, который не парсится

- ID: `missing_buildsummary_false` · источники: `missing_buildsummary_false`
- Где: `core/olap_reports.py:613`; `core/olap_reports.py:686`; `core/olap_reports.py:756`; `core/olap_reports.py:804`; `core/olap_reports.py:1113`; `core/olap_reports.py:1228`; `core/olap_reports.py:1529`; `core/olap_reports.py:1626`; `core/olap_reports.py:1780`; `core/olap_reports.py:1867`; `core/olap_reports.py:1342`; `core/olap_reports.py:1356`
- Затронутые отчёты: `all_sales_olap_request`, `explorer_sales`, `kitchen_olap_request(+waiter)`, `olap_request_base`, `employee_aggregated_metrics`, `employee_daily_revenue`, `new_loyalty_cards_by_waiter`, `discount_report`, `rfm_report`
- Проблема: Только два KPI-запроса передают buildSummary="false" (L1342,1356). Остальные SALES-запросы полагаются на серверный дефолт (до iiko 9.1.2 — true) и читают исключительно поле data, никогда не парся summary, тогда как сервер тратит ресурсы на расчёт промежуточных итогов по всем комбинациям группировок.
- Влияние: Лишняя работа iiko на расчёт summary, тем большая, чем шире группировка (особенно all_sales с 6 полями и discount/rfm); на серверах < 9.1.2 — заметный оверхед на каждый запрос. На числа не влияет (RULES.md:441).
- Рекомендация (НЕ применена): Добавить "buildSummary": "false" (строкой, как в доке и KPI-запросах) во все SALES-builders, чьи потребители не читают summary. Поведение data не меняется.

### 8. [LOW] Эндпоинты сотрудников запускают 6 перекрывающихся OLAP-запросов с фан-аутом по DishName×Store×Day, тогда как KPI-путь доказал достижимость 2 лёгкими

- ID: `employee_redundant_six_olap_fanout` · источники: `employee_redundant_six_olap_fanout`
- Где: `routes/employee.py:78-86`; `routes/employee.py:243-251`; `core/olap_reports.py:1230-1232`; `core/olap_reports.py:1282-1287`; `core/olap_reports.py:1299-1313`; `core/olap_reports.py:1118-1125`
- Затронутые отчёты: `employee_aggregated_metrics`, `olap_request_base (draft/bottles)`, `kitchen_olap_request_with_waiter`, `cancelled_orders_request`, `new_loyalty_cards_by_waiter`
- Проблема: /api/employee-analytics и /api/employee-compare веером дёргают 6 OLAP-запросов (ThreadPoolExecutor max_workers=6), из которых 3-4 тяжёлые с фан-аутом по DishName×Store×Day, причём суммарная выручка get_employee_aggregated_metrics выводима из суммы draft+bottles+kitchen. KPI-путь get_kpi_olap_data уже доказал, что 2 лёгких запроса (summary + categories по WaiterName×TopParent) заменяют 4 тяжёлых.
- Влияние: На каждый просмотр карточки/сравнение — 6 запросов, 3-4 тяжёлых, при достижимости 2 лёгкими; лишняя нагрузка на iiko и риск таймаута на широких периодах.
- Рекомендация (НЕ применена): Перевести employee-analytics/compare на паттерн get_kpi_olap_data: summary (WaiterName) + categories (WaiterName×DishGroup.TopParent), оставив отдельно cancelled и loyalty. top_beers (требует разбивки по DishName) запрашивать отдельно и только при необходимости. Убрать дублирующий get_employee_aggregated_metrics, если суммы выводятся из categories.

### 9. [LOW] widget/revenue: DashboardMetrics пересчитывает метрики каждого бара дважды (ветка «Общая» и per-bar)

- ID: `widget_double_calculate_per_bar` · источники: `widget_recreates_calculator_per_bar`
- Где: `routes/dashboard.py:801-875`; `routes/dashboard.py:807-809`; `routes/dashboard.py:842-844`; `routes/dashboard.py:709-710`
- Затронутые отчёты: `all_sales_olap_request`
- Проблема: Виджет правильно делает один OLAP на все бары, но в цикле для «Общая» DashboardMetrics().calculate_metrics() вызывается на каждый бар (L808), а затем ещё раз per-bar ниже (L843) — метрики каждого бара считаются дважды. Это чистый CPU-оверхед приложения, не iiko, маскируемый 5-минутным WIDGET_CACHE.
- Влияние: Двойной Python-пересчёт метрик по каждому бару на cache-miss виджета. Объём данных невелик, эффект малый, на корректность чисел не влияет.
- Рекомендация (НЕ применена): Посчитать метрики каждого бара один раз (в словарь per_bar), а «Общую» собрать как сумму уже посчитанных значений вместо повторного calculate_metrics. Низкий приоритет.

### 10. [LOW] Дублирование тела kitchen-builder: _build_kitchen_olap_request vs _build_kitchen_olap_request_with_waiter

- ID: `duplicated_kitchen_builders` · источники: `dup_kitchen_builders`
- Где: `core/olap_reports.py:610-662`; `core/olap_reports.py:1113-1165`; `core/olap_reports.py:824-829`; `docs/OLAP_REPORTS_COLLECTION.md:396`
- Затронутые отчёты: `_build_kitchen_olap_request (#2)`, `_build_kitchen_olap_request_with_waiter (#7)`
- Проблема: Два kitchen-builder'а почти идентичны (~50 строк JSON-тела), отличаются ровно одной строкой groupByRowFields ('WaiterName'), тогда как для пива тот же приём решён одним параметризованным _build_olap_request(..., include_waiter=...). Builder'ы уже частично разошлись (не-waiter версия группирует ещё и по DishForeignName), и любая будущая правка требует ручной синхронизации в двух местах.
- Влияние: Поддержка: правки фильтров/полей кухни надо синхронизировать в двух местах; высок риск, что один builder обновят, а второй забудут — тогда отчёт по кухне и кухне-с-официантом дадут расходящиеся числа. Сейчас тела согласованы, severity low.
- Рекомендация (НЕ применена): Слить в один _build_kitchen_olap_request(..., include_waiter=False) по образцу _build_olap_request: при include_waiter добавлять 'WaiterName' в groupByRowFields. Сократит дубль и закроет риск рассинхрона.

---

## CONSISTENCY — Согласованность метрик (6)

### 11. [HIGH] Выручка/чеки сотрудника берутся по AuthUser, а категории/доли — по WaiterName: разные ключи идентичности в одном отчёте

- ID: `employee_authuser_vs_waitername_identity` · источники: `employee_breakdown_authuser_vs_waitername_join`, `employee_revenue_authuser_vs_waitername`
- Где: `core/olap_reports.py:1230-1231`; `core/olap_reports.py:1282-1287`; `core/employee_analysis.py:57`; `core/employee_analysis.py:80`; `core/employee_analysis.py:96-98`; `core/employee_analysis.py:204`; `routes/employee.py:80-83`; `routes/employee.py:245-248`; `routes/employee.py:965-968`; `routes/employee.py:996-1021`
- Затронутые отчёты: `employee_aggregated_metrics (#9)`, `olap_request_base draft/bottles (#5)`, `kitchen_olap_request_with_waiter (#7)`
- Проблема: В /api/employee-analytics, /api/employee-compare и /api/employee-metrics-breakdown суммарные метрики сотрудника (total_revenue, total_checks, discount_sum) берутся из get_employee_aggregated_metrics, который группирует по AuthUser («кто пробил/авторизовал чек»), а выручка/наценка по категориям (draft/bottles/kitchen) — из запросов, сгруппированных по WaiterName («официант блюда»). Это два разных бизнес-измерения людей; сопоставление в breakdown к тому же идёт строгим `name in employees_data`, тогда как employee_analytics делает fuzzy-match.
- Влияние: Когда официант блюда != авторизовавший чек (типично для барной модели) или различаются форматы имени, числители категорий и знаменатель total_revenue относятся к разным множествам чеков: доли draft/bottles/kitchen не сходятся к 100%, средний чек несогласован с разбивкой, а в breakdown категорийная выручка может вовсе обнулиться. Сравнение сотрудников искажено.
- Рекомендация (НЕ применена): Выбрать ОДНО измерение идентичности на весь отчёт: привести агрегаты к WaiterName (как уже делает KPI-путь _build_kpi_metrics в employee.py:626-660 и kpi summary в olap_reports.py:1343), либо строить категорийную разбивку по AuthUser. Минимально — в breakdown заменить строгий `in` на нормализованное/fuzzy сопоставление как в _find_employee_in_olap.

### 12. [MEDIUM] Количество чеков считается двумя несовместимыми методами: set(UniqOrderId.Id) на дашборде vs sum(UniqOrderId.OrdersCount) у сотрудников/KPI

- ID: `checks_count_two_incompatible_methods` · источники: `checks_count_two_methods`
- Где: `core/dashboard_analysis.py:62`; `core/dashboard_analysis.py:65`; `core/dashboard_analysis.py:122-123`; `core/dashboard_analysis.py:258-271`; `core/olap_reports.py:764`; `core/olap_reports.py:768`; `core/olap_reports.py:1234-1240`; `core/olap_reports.py:1346`; `core/olap_reports.py:1404`; `core/employee_analysis.py:73`; `routes/employee.py:1003`; `docs/technical/OLAP_REPORT_BUILDING_RULES.md:154-155`
- Затронутые отчёты: `all_sales_olap_request (#4)`, `employee_aggregated_metrics (#9)`, `kpi_olap_summary (#10)`, `orders_count_request (#6)`
- Проблема: Дашборд считает total_checks как число уникальных значений поля UniqOrderId.Id, тогда как employee aggregated, KPI summary и (мёртвый) get_orders_count берут агрегат UniqOrderId.OrdersCount. Это две разные метрики iiko («Количество уникальных чеков» INTEGER vs «Количество заказов» AMOUNT), которые могут расходиться. «Чеки» на главном дашборде и в карточке сотрудника считаются по-разному.
- Влияние: «Чеки» и «средний чек = выручка/чеки» на общем дашборде и на дашборде сотрудника могут не совпадать для одного периода/бара — расхождение обычно небольшое, но не нулевое, что подрывает доверие к согласованности отчётов.
- Рекомендация (НЕ применена): Зафиксировать единый канонический способ подсчёта чеков (предпочтительно UniqOrderId.OrdersCount как агрегат, без тащения UniqOrderId.Id в группировку — см. all_sales_uniqorderid_id_fanout) и применять его во всех отчётах. Если set(UniqOrderId.Id) выбран сознательно — задокументировать и использовать везде одинаково.

### 13. [MEDIUM] Категории «Напитки Розлив»/«Напитки Фасовка» и определение «кухни» захардкожены строками в 10+ местах без единой константы

- ID: `hardcoded_category_string_literals` · источники: `hardcoded_category_strings_no_shared_constant`, `magic_category_literals_no_constants`
- Где: `core/olap_reports.py:438-439`; `core/olap_reports.py:642`; `core/olap_reports.py:812`; `core/olap_reports.py:1146`; `core/dashboard_analysis.py:41-43`; `core/explorer.py:26-27`; `core/explorer.py:92-96`; `core/draft_analysis.py:24`; `routes/employee.py:646-648`; `routes/stocks.py:608`; `routes/stocks.py:620`; `routes/stocks.py:650`; `routes/stocks.py:953`; `routes/stocks.py:1188`; `routes/expiration.py:195`; `scripts/import_export/export_draft_sales.py:92`
- Затронутые отчёты: `kitchen_olap_request (#2)`, `kitchen_olap_request_with_waiter (#7)`, `all_sales_olap_request (#4)`, `olap_request_base (#5)`, `kpi_olap_categories (#11)`, `explorer_sales (#3)`
- Проблема: Названия категорий верхнего уровня DishGroup.TopParent ('Напитки Розлив', 'Напитки Фасовка') и правило «кухня = всё кроме них» захардкожены строковыми литералами минимум в 10+ местах: и в серверной фильтрации OLAP-builder'ов (ExcludeValues/IncludeValues), и в клиентской классификации продаж в Python. Единая константа есть только локально в core/explorer.py (DRAFT_TOP/BOTTLED_TOP) и не переиспользуется; kitchen-builder'ы дублируют один и тот же ExcludeValues-список.
- Влияние: При переименовании группы в iiko или опечатке в одной точке правка нужна в 10+ местах; пропуск любой даёт молчаливое расхождение классификации (продажи уедут в «кухню» вместо «розлив/фасовка») без ошибки и без падения тестов — расходятся числа между дашбордом, KPI и карточкой сотрудника.
- Рекомендация (НЕ применена): Вынести 'Напитки Розлив'/'Напитки Фасовка' в единый модуль-источник истины (напр. core/categories.py с DRAFT_TOP, BOTTLED_TOP и helper classify_top_category(record)) и импортировать во всех builders и потребителях, переиспользовав существующие DRAFT_TOP/BOTTLED_TOP из explorer. Серверные ExcludeValues и клиентское разбиение должны ссылаться на одни константы.

### 14. [LOW] Дрейф наборов aggregateFields/groupByRowFields у логически одного отчёта продаж по категориям + две реализации взвешенной наценки

- ID: `aggregatefields_drift_sales_reports` · источники: `aggregatefields_drift_same_logical_report`
- Где: `core/olap_reports.py:623-632`; `core/olap_reports.py:758-775`; `core/olap_reports.py:835-844`; `core/olap_reports.py:1359-1363`; `core/dashboard_analysis.py:192-223`; `routes/employee.py:638-666`
- Затронутые отчёты: `kitchen_olap_request (#2)`, `all_sales_olap_request (#4)`, `olap_request_base (#5)`, `kpi_olap_categories (#11)`, `kitchen_olap_request_with_waiter (#7)`
- Проблема: Логически родственные отчёты по продажам/категориям используют разнородные наборы агрегатов и измерений: kitchen/base тащат UniqOrderId + ProductCostBase.OneItem + MarkUp; all_sales заменяет UniqOrderId на UniqOrderId.Id в группировке; kpi_categories запрашивает MarkUp/ProductCost, но downstream-взвешивание наценки в _build_kpi_metrics (employee.py:653-666) дублирует логику DashboardMetrics._calculate_weighted_markup отдельной реализацией.
- Влияние: Дрейф полей сам по себе чисел не ломает (лишние агрегаты безвредны), но повышает стоимость поддержки и риск, что будущая правка одной формулы (наценка, чеки) не будет применена ко всем веткам — источник будущих рассинхронов.
- Рекомендация (НЕ применена): Свести продажи-по-категориям к минимально необходимому единому набору полей и одной реализации взвешенной наценки/подсчёта чеков (общий helper), переиспользуемой dashboard и employee/KPI путями.

### 15. [LOW] Неединообразный возврат при ошибке OLAP (None / {} / 0) — downstream трактует по-разному и маскирует сбой

- ID: `inconsistent_olap_error_returns` · источники: `inconsistent_error_returns`
- Где: `core/olap_reports.py:960-968`; `core/olap_reports.py:1619`; `core/olap_reports.py:1696-1704`; `docs/technical/OLAP_REPORT_BUILDING_RULES.md:409`
- Затронутые отчёты: `get_orders_count`, `get_new_loyalty_cards_by_waiter`, `все *_report builders`
- Проблема: Один и тот же класс сбоя (HTTP!=200 или исключение) возвращается тремя способами: get_orders_count -> 0 (целое), get_new_loyalty_cards_by_waiter -> {} (пустой dict), остальные -> None. Для get_orders_count это маскирует ошибку под валидный результат (и недоступность iiko, и реальное отсутствие чеков дают 0); для loyalty {} неотличимо от «сбой» и «нет новых карт». Док фиксирует единый контракт: None при ошибке.
- Влияние: KPI/бонусы и дашборд не могут отличить «сбой OLAP» от «честный ноль»; get_orders_count==0 при сбое участвует в делениях/долях как валидный 0, искажая средний чек/доли без сигнала об ошибке.
- Рекомендация (НЕ применена): Привести все builders к единому контракту: None при сбое, пустой контейнер только когда сервер реально вернул пусто. get_orders_count при сбое возвращать None и обрабатывать у вызывающих отдельно от 0.

### 16. [LOW] Запрос номенклатуры (TRANSACTIONS) не применяет +1 день к границе to — допустимо, но отклоняется от единого правила

- ID: `nomenclature_transactions_no_plus1_day` · источники: `nomenclature_transactions_no_plus1_but_ok`
- Где: `core/olap_reports.py:98-119`
- Затронутые отчёты: `nomenclature_via_olap (Collection #1)`, `core/olap_reports.py:get_nomenclature`
- Проблема: Единственный TRANSACTIONS-запрос строит окно дат внутри метода (now-30d .. now) и НЕ добавляет +1 день к date_to, в отличие от всех SALES-потребителей в routes/*, где правило «+1 день» для исключающей границы to применяется единообразно. Операции за текущий учётный день в выборку не попадут.
- Влияние: Товары, у которых единственная операция пришлась на текущий учётный день, не попадут в номенклатуру через быстрый OLAP-путь (есть XML-fallback). Практический эффект минимален из-за 30-дневного окна, но правило применяется неединообразно — потенциальная ловушка при будущих правках.
- Рекомендация (НЕ применена): Либо добавить +1 день к date_to для единообразия, либо явно задокументировать в докстринге, что для номенклатуры исключающая граница последнего дня несущественна и +1 намеренно опущен.

---

## ROBUSTNESS — Надёжность и обработка ошибок (6)

### 17. [HIGH] Отсутствует единый retry/таймаут-бюджет под gunicorn --timeout 120с: бюджеты превышают лимит, таймауты разнобойны, ретрай неполон и неконсистентен

- ID: `retry_timeout_budget_vs_gunicorn` · источники: `retry_budget_exceeds_gunicorn_timeout`, `timeout_disparity_across_builders`, `retry_only_two_requests`, `explorer_no_retry_on_conn_error`, `olap_timeout_vs_gunicorn_budget`
- Где: `core/olap_reports.py:460-502`; `core/olap_reports.py:730-748`; `core/olap_reports.py:269`; `core/olap_reports.py:316`; `core/olap_reports.py:363`; `core/olap_reports.py:410`; `core/olap_reports.py:465`; `core/olap_reports.py:536`; `core/olap_reports.py:596`; `core/olap_reports.py:733`; `core/olap_reports.py:950`; `core/olap_reports.py:1004`; `core/olap_reports.py:1051`; `core/olap_reports.py:1098`; `core/olap_reports.py:1269-1297`; `core/olap_reports.py:1275`; `core/olap_reports.py:1369-1385`; `core/olap_reports.py:1373`; `core/olap_reports.py:1567`; `core/olap_reports.py:1672`; `core/olap_reports.py:1677`; `core/olap_reports.py:1745`; `core/olap_reports.py:1825`; `core/olap_reports.py:1830`; `core/olap_reports.py:1910`; `core/olap_reports.py:1915`; `routes/employee.py:78-95`; `routes/employee.py:785-786`; `render.yaml:7`
- Затронутые отчёты: `all_sales_olap_request (get_all_sales_report)`, `explorer_sales (get_explorer_sales)`, `get_employee_aggregated_metrics`, `get_kpi_olap_data`, `get_cancelled_orders_by_waiter`, `get_discount_report`, `get_rfm_report`, `get_orders_count`, `get_new_loyalty_cards_by_waiter`, `get_draft/bottles/kitchen_by_waiter`, `olap_request_base (beer/draft/bottles)`, `kitchen_olap_request(+waiter)`
- Проблема: Нет единого retry/таймаут-бюджета, согласованного с реальным gunicorn --timeout 120с (код/комментарии исходят из мнимых 180с). get_all_sales_report (2×60с+backoff) уже на грани 120с; get_explorer_sales (3×120с+backoff ≈ 364с) гарантированно убивает воркер раньше ретраев, а ещё ретраит только ReadTimeout, отдавая None на ConnectionError/non-200. Per-request таймауты разнятся произвольно (30/60/90/120с), ретрай есть только у all_sales и explorer (остальные 20+ запросов рвутся с первого ReadTimeout, ломая employee/KPI/скидки/RFM), а параллельный employee-веер (max_workers=6, as_completed без deadline) не имеет общего бюджета.
- Влияние: При медленном/зависшем iiko воркер убивается по SIGKILL до возврата ответа — пользователь получает 502/обрыв вместо graceful-ошибки; на 2 воркерах два таких висящих запроса кладут сайт. Ретраи explorer/employee практически бесполезны и создают ложное ощущение устойчивости; транзиентный сбой на не-all_sales запросе детерминированно ломает соответствующую вкладку; 30с-таймауты рвут большие легитимные выборки слишком рано.
- Рекомендация (НЕ применена): Ввести единую константу OLAP_REQUEST_TIMEOUT и единый retry/backoff-хелпер так, чтобы (timeout × попытки + backoff) с запасом укладывалось в gunicorn 120с (например per-attempt ~50с при 2 попытках для тяжёлых, меньше для лёгких orders_count/categories/summary). Применить ретрай ко всем builders (минимум kpi/aggregated/by_waiter), выровнять except-набор (ReadTimeout|ConnectTimeout|ConnectionError) как в get_all_sales_report, задать общий deadline для employee-веера. Альтернатива — осознанно поднять gunicorn --timeout до 180с в render.yaml и синхронизировать комментарии.

### 18. [MEDIUM] Частичный сбой параллельных OLAP в employee/KPI: упавший aggregated молча даёт нулевую выручку при HTTP 200

- ID: `partial_failure_silent_zero_revenue` · источники: `partial_failure_silent_zero_revenue`
- Где: `routes/employee.py:88-104`; `routes/employee.py:253-262`; `routes/employee.py:962-981`; `core/employee_analysis.py:59-80`
- Затронутые отчёты: `get_employee_aggregated_metrics`, `get_draft_sales_by_waiter_report`, `get_bottles_sales_by_waiter_report`, `get_kitchen_sales_by_waiter_report`, `get_cancelled_orders_by_waiter`, `get_new_loyalty_cards_by_waiter`
- Проблема: В ThreadPoolExecutor каждый future, упавший с исключением, кладётся как results[key]=None, и анализ продолжается. Если упал именно aggregated (источник выручки и чеков), EmployeeMetricsCalculator.calculate получит aggregated_data=None и молча вернёт total_revenue=0, total_checks=0, хотя draft/bottles/kitchen могли прийти успешно. Ответ 200 с правдоподобной структурой, но неверными числами.
- Влияние: В проде сотрудник может получить выручку 0 и, как следствие, бонус 0 / KPI 0 при частично работавшем OLAP — без видимой ошибки на фронте (HTTP 200). Неверные деньги в расчёте премий.
- Рекомендация (НЕ применена): После сбора futures проверять, что критичные датасеты (aggregated для employee) не None; при сбое критичного запроса возвращать 5xx или флаг partial, а не молча считать с нулём.

### 19. [LOW] Отчёты по скидкам и RFM используют OrderNum как идентификатор визита/чека при агрегации в Python

- ID: `discount_rfm_ordernum_visit_identity` · источники: `discount_rfm_ordernum_visit_identity`
- Где: `routes/analysis.py:1036`; `core/olap_reports.py:1782-1789`; `core/olap_reports.py:1869-1874`
- Затронутые отчёты: `discount_report (#15)`, `rfm_report (#16)`
- Проблема: В discount_report и rfm_report строки группируются по Store.Name + CustomerCardNumber + CustomerName + OrderNum + OpenDate.Typed, а downstream считает уникальные визиты (RFM frequency) по OrderNum. OrderNum не глобально уникален; наличие Store.Name+OpenDate.Typed в группировке частично спасает композитным ключом, но не полностью (две смены за один учётный день).
- Влияние: RFM-frequency (число визитов гостя) и детализация скидок могут давать слегка неверный счёт уникальных чеков для активных гостей, влияя на R/F/M-сегментацию и отчёт по скидкам в /analysis. Эффект ограничен наличием Store+Date, поэтому severity low/medium.
- Рекомендация (НЕ применена): Для счёта визитов использовать агрегат UniqOrderId.OrdersCount либо явно строить композитный ключ (Store.Name + OpenDate.Typed + OrderNum) и документировать его как приближение; идеально — добавить UniqOrderId.Id для точного счёта.

### 20. [LOW] debug_employee_field_names в прод-классе: 13 OLAP POST без timeout, мёртвый и опасный

- ID: `debug_employee_field_names_no_timeout_dead` · источники: `diagnostic_no_timeout`, `diagnostic_debug_employee_field_names_in_prod`
- Где: `core/olap_reports.py:1430-1506`; `core/olap_reports.py:1438-1449`; `core/olap_reports.py:1473-1478`; `docs/OLAP_REPORTS_COLLECTION.md:876`
- Затронутые отчёты: `debug_employee_field_names (#17 DIAGNOSTIC)`
- Проблема: Диагностический метод в прод-классе OlapReports в цикле шлёт до 13 POST /v2/reports/olap подряд, причём requests.post вызывается БЕЗ параметра timeout — единственное место в файле без таймаута. Метод нигде не вызывается (grep — 0 совпадений), т.е. одновременно мёртвый и опасный: любой зависший запрос заблокирует поток бесконечно, без даже суммарного бюджета.
- Влияние: Если метод когда-либо подключат к прод-роуту, отсутствие timeout приведёт к зависанию gunicorn-воркера до SIGKILL, а 13 последовательных тяжёлых OLAP создадут заметную нагрузку на iiko (два таких зависа исчерпывают пул из 2 воркеров — сайт не отвечает). Сейчас не вызывается, фактического вреда нет — бомба замедленного действия.
- Рекомендация (НЕ применена): Перенести debug_employee_field_names в scripts/debug/ (искомое поле «Авторизовал» уже найдено — это AuthUser). Если оставлять — добавить timeout (например (5,30)) каждому req.post, общий бюджет/раннее прерывание цикла после первого найденного поля, явно пометить как непрод и убрать локальный import requests as req.

### 21. [LOW] disconnect() вне try/finally в RevenueMetricsCalculator и widget_revenue — утечка слота лицензии iiko при исключении

- ID: `disconnect_not_in_finally_token_leak` · источники: `revenue_metrics_token_leak`, `widget_revenue_token_leak`
- Где: `core/revenue_metrics.py:119-146`; `routes/dashboard.py:742-748`; `routes/dashboard.py:886`; `core/iiko_api.py:67-80`
- Затронутые отчёты: `get_beer_sales_report (через RevenueMetricsCalculator)`, `get_all_sales_report (через /api/widget/revenue)`
- Проблема: В _calculate_actual_revenue (revenue_metrics.py:131) и в widget_revenue (dashboard.py:748) olap.disconnect() вызывается линейно внутри try-блока, а не в finally. connect() берёт токен (слот лицензии iiko); если между connect и disconnect возникнет исключение (например strptime на кривой date_to, либо ошибка get_*_report или последующей обработки), управление уйдёт в except/общий 500 БЕЗ disconnect, и токен не освободится. Остальные эндпоинты (routes/*.py) используют try/finally: disconnect.
- Влияние: Накопление неосвобождённых токенов/слотов лицензии iiko при повторных ошибках на вкладке выручки и маршруте виджета -> со временем исчерпание лицензионных слотов и отказ авторизации новым запросам.
- Рекомендация (НЕ применена): Обернуть весь блок после olap.connect() в try/finally с olap.disconnect() в finally в обоих местах, единообразно с routes/dashboard.py:_fetch_all_sales и остальными эндпоинтами.

### 22. [LOW] analysis.py (discount/RFM): OpenDate.Typed парсится strptime('%Y-%m-%d') без обработки иного формата

- ID: `date_format_strptime_assumption_analysis` · источники: `date_format_assumption_analysis`
- Где: `routes/analysis.py:960`; `routes/analysis.py:1064`; `routes/analysis.py:1075-1076`; `routes/analysis.py:1160`; `routes/analysis.py:1201`; `routes/analysis.py:1210-1211`; `core/olap_reports.py:1582-1586`
- Затронутые отчёты: `get_discount_report`, `get_rfm_report`
- Проблема: visit_date берётся напрямую из OLAP-поля OpenDate.Typed и подаётся в dt.strptime(..., '%Y-%m-%d') без try/except на конкретной строке. При попадании значения с точками (YYYY.MM.DD) или пустого/нестандартного strptime бросит ValueError. В get_employee_daily_revenue нормализация '.'->'-' явно сделана, а здесь — нет (рассогласование подходов).
- Влияние: Если сервер вернёт дату в нестандартном виде, весь /api/discount-analyze или /api/rfm-analyze упадёт в 500 (ловится только внешним try эндпоинта) вместо graceful-пропуска записи. Вероятность низкая (.Typed обычно ISO), но обработка несогласованна по проекту.
- Рекомендация (НЕ применена): Ввести единый хелпер нормализации даты OLAP (как в get_employee_daily_revenue) и использовать его в analysis.py, либо оборачивать пер-строчный strptime в try/except с пропуском записи.

---

## SPEC — Соответствие спецификации iiko (1)

### 23. [MEDIUM] Новые карты лояльности фильтруются И по OpenDate.Typed, И по дате создания клиента — двойной фильтр сужает выборку

- ID: `loyalty_cards_double_date_filter` · источники: `loyalty_cards_double_date_filter_semantics`
- Где: `core/olap_reports.py:1602`; `core/olap_reports.py:1636-1649`
- Затронутые отчёты: `new_loyalty_cards_by_waiter (#13)`
- Проблема: Запрос новых карт лояльности ставит одновременно два DateRange-фильтра на один период: OpenDate.Typed (учётный день продажи) и Delivery.CustomerCreatedDateTyped (дата регистрации клиента). Это требует, чтобы клиент И зарегистрировался, И сделал покупку в тот же период; reportType=SALES даёт строки только при наличии продажи, а WaiterName привязан к официанту строки продажи, а не к регистратору карты.
- Влияние: Метрика loyalty_cards_count в дашборде сотрудника/KPI занижается (учитываются только карты с чеком в том же периоде), атрибуция идёт к официанту чека, а не к регистратору. На коротких периодах эффект усиливается; для KPI-премии — материальное искажение.
- Рекомендация (НЕ применена): Уточнить требование к метрике. Если это «зарегистрированные карты» — нужен другой источник/механика (для SALES фильтр OpenDate.Typed обязателен). Если «новые клиенты с первой покупкой в периоде» — текущая логика приемлема, но это надо отразить в названии/доке и подтвердить корректность атрибуции по WaiterName.

---

## DEAD_CODE — Мёртвый код, дубли, диагностика (3)

### 24. [LOW] Мёртвые OLAP-методы без потребителей: get_orders_count, get_employee_daily_revenue, get_product_expense_report

- ID: `dead_olap_methods` · источники: `dead_code_olap_methods`, `dead_get_orders_count`, `dead_get_employee_daily_revenue`, `dead_get_product_expense_report`
- Где: `core/olap_reports.py:876-929`; `core/olap_reports.py:931-968`; `core/olap_reports.py:1508-1600`; `core/olap_reports.py:566-608`; `core/dashboard_analysis.py:248`; `docs/OLAP_REPORTS_COLLECTION.md:1397-1398`; `docs/OLAP_REPORTS_COLLECTION.md:1423-1424`; `docs/OLAP_REPORTS_COLLECTION.md:1449`
- Затронутые отчёты: `orders_count_request (#6 get_orders_count + _build_orders_count_request)`, `employee_daily_revenue (#12 get_employee_daily_revenue)`, `get_product_expense_report (/reports/productExpense)`
- Проблема: Несколько публичных OLAP-методов прод-класса OlapReports не вызываются нигде (grep по репозиторию — 0 совпадений): get_orders_count (+ builder _build_orders_count_request), get_employee_daily_revenue и get_product_expense_report (последний к тому же структурно нерабочий — требует department_id, которого никто не передаёт, и всегда возвращает None по TODO-заглушке). Иронично, get_orders_count — эталонный «правильный» безфан-аутовый паттерн подсчёта чеков, но dashboard вместо него использует фан-аут через UniqOrderId.Id.
- Влияние: Балласт в прод-классе, который надо синхронизировать при изменении схемы OLAP, и который вводит в заблуждение при оптимизации (риск «оптимизировать» мёртвый путь вместо горячего). Прямого прод-эффекта/неверных чисел нет (не исполняется).
- Рекомендация (НЕ применена): Подтвердить отсутствие вызовов grep-ом по всему репозиторию (scripts/tests/knowledge_graph) и удалить методы (или перенести в scripts/debug). Альтернатива для get_orders_count — переиспользовать его как корректный безфан-аутовый счётчик чеков в dashboard (см. all_sales_uniqorderid_id_fanout). Обновить записи #6/#12 и productExpense в OLAP_REPORTS_COLLECTION.md.

### 25. [LOW] Лишний агрегат UniqOrderId (без .OrdersCount) в нескольких запросах — не читается downstream

- ID: `redundant_bare_uniqorderid_aggregate` · источники: `aggregated_uniqorderid_redundant_field`
- Где: `core/olap_reports.py:624`; `core/olap_reports.py:836`; `core/olap_reports.py:1128`; `core/olap_reports.py:1235`
- Затронутые отчёты: `olap_request_base (#5)`, `kitchen_olap_request_with_waiter (#7)`, `employee_aggregated_metrics (#9)`, `kitchen_olap_request (#2)`
- Проблема: В ряде запросов в aggregateFields присутствует и голый 'UniqOrderId', и 'UniqOrderId.OrdersCount', но downstream-код везде читает только 'UniqOrderId.OrdersCount' (grep по 'UniqOrderId(?!\.)' не находит ни одного потребителя). Голый UniqOrderId запрашивается, но не используется.
- Влияние: Косметика/мелкая нагрузка: лишняя колонка немного увеличивает payload, числа верны. Скорее источник путаницы при чтении кода (легко перепутать UniqOrderId и UniqOrderId.OrdersCount).
- Рекомендация (НЕ применена): Удалить 'UniqOrderId' из aggregateFields там, где используется только 'UniqOrderId.OrdersCount', оставив один счётчик чеков.

### 26. [LOW] __main__ тестовый стенд в olap_reports.py с эмодзи и записью файла в CWD

- ID: `main_test_stand_emojis_in_prod_module` · источники: `get_beer_sales_report_only_main_and_prod_mixed`
- Где: `core/olap_reports.py:1931-1968`
- Затронутые отчёты: `get_beer_sales_report (#5 olap_request_base)`
- Проблема: Блок `if __name__ == "__main__"` в прод-модуле core/olap_reports.py содержит тестовый стенд, который коннектится к боевому iiko, пишет beer_report.json в текущую директорию и печатает текст с эмодзи (нарушение Style Rules проекта «No emojis in code»). Сам метод get_beer_sales_report НЕ мёртвый (есть прод-потребители в revenue_metrics.py и analysis.py) — проблема именно в __main__-стенде.
- Влияние: Гигиена кода: эмодзи в прод-файле против правил проекта; ручной запуск модуля может случайно дёрнуть боевой iiko и насорить beer_report.json в рабочей директории. На приложение не влияет (блок не исполняется под gunicorn).
- Рекомендация (НЕ применена): Перенести демонстрационный стенд в scripts/ или tests/ и убрать эмодзи. Метод get_beer_sales_report оставить (он прод-используемый).

---

## Отклонено верификацией (не считается проблемой)

- **[CONSISTENCY/medium]** Двойной DateRange в отчёте новых карт лояльности: +1 день применяется и к OpenDate.Typed, и к Delivery.CustomerCreatedDateTyped (`spec`) — Код-факты подтверждены: в get_new_loyalty_cards_by_waiter (core/olap_reports.py:1636-1659) есть два DateRange-фильтра — OpenDate.Typed (1637-1641) и Delivery.CustomerCreatedDateTyped (1644-1649) — оба используют один date_to; все три потребителя (routes/employee.py:85, 250, 775) передают olap_date_to = date_to + 1 день (определён на :764). НО ключевой довод находки ложный. Находка утверждает, что 
- **[CONSISTENCY/low]** RFM/скидки: period_days и recency считаются по UI-дате date_to, тогда как OLAP запрашивается с olap_date_to (+1) (`spec`) — Находка опровергнута: заявленного рассогласования границ нет. Фильтр в обоих билдерах ставится на OpenDate.Typed (core/olap_reports.py:1797 для discount, :1882 для RFM) — это поле УЧЁТНОГО ДНЯ с дневной гранулярностью, возвращается как YYYY-MM-DD без времени (OLAP_REPORT_BUILDING_RULES.md:271; реестр OLAP_REQUEST_REGISTRY_2026-04-03.md:16 «treats OpenDate.Typed as the accounting day»). Для поля с 

## Проверено и найдено корректным (секция уверенности)

Что ревьюеры проверили и подтвердили как правильное (60 пунктов):

- [semantic] Поле даты под reportType выбрано корректно: для всех SALES-запросов фильтр и группировка по OpenDate.Typed; единственный TRANSACTIONS-запрос (номенклатура, olap_reports.py:114) фильтрует по DateTime.DateTyped — точно по правилу OLAP_REPORT_BUILDING_RULES.md:362/427.
- [semantic] ProductCostBase.MarkUp трактуется как доля 0..1: dashboard_analysis._calculate_weighted_markup взвешивает markup×cost и делит на сумму cost (доля остаётся долей), затем routes/dashboard.py:128-129 умножает на 100 для UI; employee_analysis.py:137 (*100) и employee.py:666 (avg_markup ... *100) — единообразно. Это соответствует типу PERCENT (доля) из доков.
- [semantic] Взвешивание наценки по себестоимости методологически корректно (sum(markup_i*cost_i)/sum(cost_i)) во всех трёх местах (dashboard_analysis.py:204-223, employee_analysis.py:235-253, employee.py:653-666) — не простое среднее.
- [semantic] Подсчёт чеков на дашборде через set уникальных UniqOrderId.Id (dashboard_analysis._count_unique_orders) корректно даёт число уникальных заказов и не зависит от фан-аута строк; суммирование revenue/cost/discount по строкам не двоится при добавлении UniqOrderId.Id в группировку (сумма инвариантна к гранулярности).
- [semantic] Категорийные фильтры согласованы: get_all_sales_report не фильтрует TopParent и разделяет в Python по DishGroup.TopParent ('Напитки Розлив'/'Напитки Фасовка'/прочее=кухня); kitchen-запросы исключают обе напиточные категории через ExcludeValues; beer/draft через IncludeValues одной из них. Дефиниция кухни как 'всё кроме розлива/фасовки' одинакова в dashboard_analysis.py:41-47, employee.py:646-651 и kitchen-билдерах — консистентно.
- [semantic] Дублирование строк официанта предотвращено: include_waiter добавляет только WaiterName (olap_reports.py:824-829 с явным комментарием почему НЕ добавлять OrderWaiter.Name); во всех waiter-запросах используется единый ключ WaiterName, без смешения WaiterName/OrderWaiter.Name/AuthUser в одном groupByRowFields.
- [semantic] Предохранители DeletedWithWriteoff=NOT_DELETED и OrderDeleted=NOT_DELETED присутствуют во всех продакшн SALES-запросах; в отчёте отмен (cancelled_orders_request) предохранитель осознанно инвертирован (DeletedWithWriteoff ExcludeValues NOT_DELETED) для выборки только удалённых позиций — корректная инверсия.
- [semantic] orders_count_request (#6) — образцовый паттерн подсчёта чеков: группировка только по Store.Name+OpenDate.Typed (без DishName), агрегат UniqOrderId.OrdersCount, без фан-аута (хотя сам get_orders_count внешне не вызывается — это отдельный вопрос мёртвого кода вне линзы).
- [semantic] KPI summary/categories (#10/#11) группируются по WaiterName (и WaiterName+TopParent) — единый ключ идентичности внутри KPI-пути; markup в _build_kpi_metrics (employee.py:653-666) взвешивается по cost и трактуется как доля (*100 в конце) — семантически верно.
- [semantic] DishGroup.ThirdParent vs TopParent: draft/bottled-запросы группируют по ThirdParent (стиль), но фильтруют по TopParent (Розлив/Фасовка) — это разные уровни иерархии, и фильтр по TopParent корректно ограничивает категорию верхнего уровня, а ThirdParent в строках даёт стиль для ABC/XYZ; конфликта нет. Explorer (#3) корректно включает Top/Second/ThirdParent для подкатегорийной агрегации.
- [semantic] Суммирование DishDiscountSumInt как рубли (MONEY), а не копейки — подтверждено комментарием и доками (employee_analysis.py:210-212); единообразно во всех _sum_revenue.
- [performance] get_kpi_olap_data (olap_reports.py:1299-1428) — образцовая оптимизация: 2 лёгких запроса (summary по WaiterName + categories по WaiterName×DishGroup.TopParent) вместо тяжёлого фан-аута; buildSummary="false" задан корректно (строкой), запросы идут параллельно через ThreadPoolExecutor(max_workers=2); потребляется в /api/kpi-calculate (employee.py:773).
- [performance] _build_orders_count_request (olap_reports.py:876-929) — корректный безфан-аутовый паттерн подсчёта чеков: группировка только по Store.Name+OpenDate.Typed, агрегат UniqOrderId.OrdersCount (хотя сам метод сейчас не вызывается — см. dead_code).
- [performance] cached_olap + single-flight (extensions.py:95-127) — реализован грамотно: double-checked locking под per-key локом, кэшируется только непустой результат, eviction по TTL и мягкий bound DASHBOARD_OLAP_CACHE_MAX_KEYS=64; защита от стампеда внутри воркера работает для dashboard-analytics и revenue-metrics (общий cache_key, кэш шарится между вкладками).
- [performance] Шаринг кэша dashboard-analytics и revenue-metrics: оба используют одинаковый cache_key `{venue_key}_{date_from}_{date_to_inclusive}` и cached_olap (dashboard.py:45,593) — повторный одинаковый запрос между вкладками не дёргает iiko второй раз.
- [performance] Номенклатура: трёхуровневый кэш memory(15м)->disk(24ч)->API с быстрым OLAP TRANSACTIONS как основным путём и медленным /products XML только как fallback (extensions.py:193-227; olap_reports.py:82-89) — тяжёлый XML на тёплом кэше не вызывается.
- [performance] Остатки берутся через быстрый /v2/reports/balance/stores с timestamp, а не через тяжёлый OLAP по StartBalance/FinalBalance (olap_reports.py:48-55) — соответствует рекомендации iiko (RULES.md:438-440).
- [performance] get_employee_metrics_from_shifts и список сотрудников: в employee-compare/bonus/kpi кассовые смены и список сотрудников грузятся один раз на эндпоинт с кэшем EMPLOYEES_CACHE (TTL 300с), а не per-employee (employee.py:264-289,429-446,732-755) — N+1 по сменам устранён.
- [performance] discount_names — лёгкий discovery-запрос (группировка только по ItemSaleEventDiscountType, один агрегат), timeout=30с адекватен (olap_reports.py:1706-1754).
- [performance] DishGroup.TopParent ExcludeValues для кухни и IncludeValues для розлива/фасовки применяются на стороне сервера iiko (фильтр в запросе), а не выборкой всего с фильтрацией в Python — категорийная фильтрация делегирована OLAP (olap_reports.py:640-643,852-855,1144-1147).
- [performance] Дедупликация строк официантов: в _build_olap_request осознанно используется только WaiterName без OrderWaiter.Name во избежание дублирования строк и двойного учёта (olap_reports.py:824-829) — корректное решение по фан-ауту.
- [consistency] Выручка как DishDiscountSumInt трактуется единообразно во всех потребителях: dashboard_analysis._sum_revenue, employee_analysis._sum_revenue, kpi summary, explorer, analysis (draft/discount/rfm), revenue_metrics — все суммируют DishDiscountSumInt как рубли (float), без путаницы с копейками; единица согласована.
- [consistency] Определение 'кухни' через DishGroup.TopParent ExcludeValues(['Напитки Фасовка','Напитки Розлив']) идентично в обоих kitchen-builder'ах (_build_kitchen_olap_request:642 и _build_kitchen_olap_request_with_waiter:1146) и согласовано с клиентским разбиением в DashboardMetrics (else->kitchen) и в _build_kpi_metrics — значения категорий совпадают (расхождение только в дублировании литералов, см. находку, не в семантике).
- [consistency] Стандартные предохранители DeletedWithWriteoff=NOT_DELETED и OrderDeleted=NOT_DELETED присутствуют единообразно во всех прод-SALES-builder'ах (kitchen, all_sales, base, orders_count, employee_aggregated, kpi summary/categories, daily_revenue, loyalty, discount, rfm); сознательная инверсия только в отчёте отмен (DeletedWithWriteoff ExcludeValues NOT_DELETED) — корректно для своей цели.
- [consistency] Правило 'OLAP to-дата exclusive → +1 день' применяется единообразно во всех роутах-потребителях: dashboard.py:36, analysis.py:42;302;442-444, employee.py:69;235;764;956, explorer.py:52, revenue_metrics.py:126 — единое осознанное правило, согласованное с OLAP_REPORT_BUILDING_RULES.md:274.
- [consistency] Фильтр по бару (Store.Name IncludeValues=[bar_name] при заданном bar_name, иначе отсутствует) реализован одинаково во всех builder'ах, поддерживающих bar_name; маппинг venue_key->iiko_name централизован (venues_manager / KEY_TO_IIKO_NAME / venue_to_bar) и согласован.
- [consistency] ProductCostBase.MarkUp трактуется как доля 0..1 и умножается на 100 для UI согласованно в dashboard.py:128-129 и в employee metrics breakdown/_build_kpi_metrics (avg_markup*100); наценка по категориям и общая считаются взвешенно по себестоимости в обоих местах.
- [consistency] explorer.py использует отдельный кэш-ключ с префиксом explorer_ (DASHBOARD_OLAP_CACHE) и отдельный builder get_explorer_sales с расширенной иерархией (Second/ThirdParent), что корректно изолирует его от dashboard-кэша (ключ {venue}_{from}_{to_inclusive}) — коллизии кэша между explorer и dashboard нет.
- [consistency] cached_olap single-flight + per-key lock в extensions.py реализован корректно (double-checked locking, не кэширует falsy-результат), общий ключ dashboard/revenue-metrics шарит ОДИН И ТОТ ЖЕ all_sales-ответ — согласованность данных между вкладками 'Дашборд' и 'Выручка' обеспечена.
- [robustness] Единое правило +1 день к date_to (OLAP to-граница exclusive) применяется консистентно во всех потребителях: routes/dashboard.py:35-36, routes/analysis.py:42,302,442-444, routes/employee.py:69,235,764,956, core/explorer.py:51-52, core/revenue_metrics.py:126 — согласуется с OLAP_REPORT_BUILDING_RULES.md:274.
- [robustness] Парсинг float/int с None защищён паттерном 'float(x or 0)' / 'int(x or 0)' во всех ключевых местах агрегации: core/employee_analysis.py:73-74,80 (_sum_revenue/_calculate_weighted_markup используют try/except (ValueError,TypeError)), routes/employee.py:795,1002-1004,1020-1021, core/olap_reports.py:957-958,1404-1422. Деления на ноль везде защищены 'if denom>0 else 0'.
- [robustness] Lifecycle токена корректен (try/finally: olap.disconnect()) во ВСЕХ route-эндпоинтах: dashboard.py:48-62,558-566 (helper), analysis.py:49-52,312-320,447-457,810-817,883-890,925-935,1137-1147, employee.py:29-33,76-104,242-262,962-980,766-781, explorer.py:67-78, stocks.py (все 6 эндпоинтов: taplist/kitchen/bottles/expiry/order-board). Исключения — revenue_metrics.py и widget_revenue (вынесены в findings).
- [robustness] ThreadPoolExecutor в employee-эндпоинтах оборачивает future.result() в try/except и не даёт исключению одного запроса уронить остальные (employee.py:91-95,256-260,973-977). Сбой изолируется (хотя для критичного aggregated это и создаёт проблему — см. partial_failure finding).
- [robustness] get_kpi_olap_data корректно обрабатывает критичный сбой: summary_raw is None -> return None (olap_reports.py:1395-1396), и вызывающий /api/kpi-calculate проверяет 'if kpi_olap is None' -> 500 с понятным сообщением (employee.py:785-786). Это правильный единообразный путь, в отличие от employee_analytics.
- [robustness] get_all_sales_report: retry-логика с бюджетом (2×60с + backoff < gunicorn 180с) и расширенным набором ретраимых исключений (ReadTimeout|ConnectTimeout|ConnectionError) реализована корректно и задокументирована (olap_reports.py:460-502).
- [robustness] Кэш OLAP (extensions.cached_olap) корректен по надёжности: falsy/ошибочный результат НЕ кэшируется (extensions.py:124 'if data:'), есть double-checked locking под per-key lock (single-flight, защита от стампеда), есть эвикция протухших ключей и bound на размер кэша + уборка осиротевших локов (extensions.py:67-127). Сбой iiko не отравляет кэш.
- [robustness] Нормализация формата даты OpenDate.Typed (YYYY.MM.DD vs YYYY-MM-DD) явно и корректно обрабатывается в get_employee_daily_revenue (olap_reports.py:1582-1590) через split('.'). Explorer использует pd.to_datetime(..., errors='coerce')+dropna (explorer.py:215-216), что устойчиво к обоим форматам.
- [robustness] iiko_api.py: logout() при ошибке логирует предупреждение про возможную утечку слота лицензии и не глотает молча (iiko_api.py:78-80); authenticate() корректно проверяет наличие логина/пароля до запроса (iiko_api.py:35-38). Все запросы iiko_api используют DEFAULT_TIMEOUT=(5,60).
- [robustness] Store balances и nomenclature берутся через быстрый /v2/reports/balance/stores и OLAP TRANSACTIONS с дисковым/memory-кэшем (get_cached_nomenclature), а не через тяжёлые OLAP-остатки StartBalance/FinalBalance — согласуется с рекомендацией доков (OLAP_REPORT_BUILDING_RULES.md:438-440).
- [spec] Обязательный фильтр по дате (iiko 5.5) присутствует во ВСЕХ 24 OLAP-запросах: каждое тело содержит DateRange-фильтр (OpenDate.Typed для SALES, DateTime.DateTyped для TRANSACTIONS, CloseDate.Typed в debug-варианте #22). Запросов без фильтра по дате нет.
- [spec] Правильное поле даты под reportType соблюдается: SALES фильтруется по OpenDate.Typed (core/olap_reports.py:114 — единственное исключение TRANSACTIONS использует DateTime.DateTyped, что соответствует OLAP_REPORT_BUILDING_RULES.md:237,427). DELIVERIES/STOCK не используются.
- [spec] periodType=CUSTOM задан во ВСЕХ DateRange-фильтрах всех 24 запросов (включая второй фильтр Delivery.CustomerCreatedDateTyped и debug-варианты). Других periodType (TODAY/LAST_MONTH и т.п.) в коде нет.
- [spec] Опора на дефолты includeLow=true/includeHigh=false: ни один builder в core/olap_reports.py не задаёт includeLow/includeHigh явно — все полагаются на серверные дефолты, что согласуется с OLAP_REPORT_BUILDING_RULES.md:220,274.
- [spec] Правило исключающей верхней границы to (+1 день) применяется единообразно во ВСЕХ прод-потребителях SALES: routes/dashboard.py:36 (date_to_inclusive), routes/dashboard.py:552,591,737, routes/analysis.py:42,302,442-444,803,880,923,1135, routes/employee.py:23,69,235,764,956, core/revenue_metrics.py:126, core/explorer.py:52. Случаев двойного применения +1 к одному и тому же date_to не обнаружено; случаев забытого +1 у SALES-потребителей не обнаружено (единственное отклонение — внутренний TRANSACTIONS-запрос номенклатуры, см. находку nomenclature_transactions_no_plus1_but_ok).
- [spec] buildSummary передаётся строкой ('false') в двух KPI-запросах (core/olap_reports.py:1342,1356), что соответствует требованию доки записывать buildSummary строкой (OLAP_REPORT_BUILDING_RULES.md:92,441). Остальные запросы buildSummary не задают и summary не парсят (читают только data) — поведенчески безопасно при смене дефолта на iiko 9.1.2.
- [spec] Стандартные предохранители DeletedWithWriteoff=NOT_DELETED и OrderDeleted=NOT_DELETED присутствуют во всех аналитических SALES-запросах; в отчёте об отменах (#8) предохранитель осознанно инвертирован (DeletedWithWriteoff ExcludeValues NOT_DELETED, OrderDeleted опущен) — корректно для выборки только удалённых позиций.
- [spec] Использование под-полей вне локальных каталогов (UniqOrderId.OrdersCount, UniqOrderId.Id, DishGroup.SecondParent/ThirdParent/TopParent, AuthUser, ProductCostBase.OneItem, Delivery.CustomerCreatedDateTyped, ItemSaleEventDiscountType) — валидно по правилу 'побеждают живые /columns' (OLAP_REPORTS_COLLECTION.md:43), отмечено как формальный выход за документированный набор, но не ошибка.
- [spec] groupByColFields=[] во всех запросах — допустимо по спецификации (OLAP_REPORT_BUILDING_RULES.md:86); проект не использует группировку по колонкам.
- [spec] reportType присутствует и обязателен во всех телах; используются только SALES и TRANSACTIONS, что соответствует профилю заведения без доставки.
- [spec] Range-фильтры (числовые) в проекте не применяются — согласуется с OLAP_REPORT_BUILDING_RULES.md:203.
- [spec] Остатки берутся через быстрый balance-API /v2/reports/balance/stores (core/olap_reports.py:48-52), а не через тяжёлые OLAP StartBalance/FinalBalance — следование рекомендации iiko по производительности.
- [spec] Смежные не-OLAP отчёты (storeOperations, productExpense, /products XML) корректно используют v1-стиль дат (DD.MM.YYYY) без конструкции DateRange/+1 — это другой контракт, правило +1 к ним не применяется, расхождения нет.
- [deadcode] Карта потребителей в OLAP_REPORTS_COLLECTION.md перепроверена grep'ом: get_orders_count, get_employee_daily_revenue, debug_employee_field_names действительно имеют 0 вызовов во всём репозитории (подтверждено `\.get_orders_count\(` / `\.get_employee_daily_revenue\(` / `\.debug_employee_field_names\(` → No matches).
- [deadcode] get_beer_sales_report НЕ мёртвый: помимо core/olap_reports.py:1950 (__main__) реально используется в core/revenue_metrics.py:129, routes/analysis.py:50 и :314, knowledge_graph/etl/sales_loader.py:80 — дубль-находки про 'вызывается только из __main__' нет, она была бы ложной.
- [deadcode] Центральный builder _build_olap_request параметризован корректно (draft -> DishGroup.TopParent value, include_waiter -> добавляет WaiterName в конец groupByRowFields); один builder честно обслуживает 4 геттера (beer/draft/draft+waiter/bottles+waiter) без дублирования тел — здесь дублей НЕТ.
- [deadcode] Все остальные requests.post/get в core/olap_reports.py имеют явный timeout (30/60/90/100/120с); единственное исключение без timeout — debug_employee_field_names (вынесено в findings). Retry-логика get_all_sales_report (2x60c+backoff) и get_explorer_sales (3x с backoff) укладывается в комментированный бюджет gunicorn.
- [deadcode] extensions.cached_olap реализует корректный single-flight (per-key lock + double-checked locking), не кэширует falsy-результаты, имеет eviction по TTL и MAX_KEYS, и уборку висячих inflight-локов — мёртвого/дублирующего кода в кэше OLAP не обнаружено.
- [deadcode] get_kpi_olap_data использует buildSummary='false' и 2 лёгких запроса вместо тяжёлых — builder'ы #10/#11 не дублируют другие тела, base_filters переиспользуется одной переменной (без копипасты фильтров).
- [deadcode] get_discount_report (#15) и get_rfm_report (#16) — близкие, но осознанно разные тела (RFM без DishName/ItemSaleEventDiscountType), оба имеют живых потребителей в routes/analysis.py — это не дубль, а намеренное разделение.
- [deadcode] Закомментированный код найден ровно в двух местах: olap_reports.py:530-533 (bar_id TODO в storeOperations — вынесено в отдельную ERROR-находку, т.к. влияет на числа) и olap_reports.py:581-582 (productExpense TODO — вынесено в DEAD_CODE). Других мёртвых закомментированных блоков в builders не обнаружено.

## Не покрыто / для дальнейшего ревью

- **knowledge_graph/etl/sales_loader.py — отсутствует +1 день к границе date_to (нарушение единого правила)** — sales_loader.load_sales/load_last_month/load_last_year передают UI-даты date_from/date_to напрямую в get_draft_sales_by_waiter_report и get_beer_sales_report без коррекции +1 день на исключающую границу OLAP (в отличие от routes/dashboard, routes/analysis, revenue_metrics, l4l_draft, explorer, которые её добавляют). Это значит, что данные последнего дня периода НЕ попадают в граф (daily_sync с days_back=1 теряет вчерашний день целиком). Проверить и зафиксировать как несоответствие spec — отдельно от уже найденного TRANSACTIONS-исключения.
- **knowledge_graph/etl/sales_loader.py — детерминизм _generate_sale_id и схлопывание агрегатов** — sale_id = md5(dish|bar|date|waiter|quantity)[:16] и MERGE по этому id. Две разные продажи одной позиции одним официантом в один день с одинаковым quantity получают ОДИН id и схлопываются в один Sale при MERGE (теряется выручка/маржа второй записи); плюс riск коллизии усечённого md5. Также revenue=DishDiscountSumInt уже агрегирован OLAP-ом по строке группировки, поэтому привязка к чеку (UniqOrderId) утрачена — граф не может корректно считать чеки/средний чек. Это семантический риск downstream-обработки, не покрытый ревью olap_reports.
- **knowledge_graph/etl/abc_xyz_loader.py — некорректная нарезка недель для XYZ (CV считается по псевдонеделям)** — _get_weekly_data строит year_week через substring(sale_date,8,2) (день месяца) /7+1 — это даёт 'неделю внутри месяца' (1..5), а не ISO-неделю; границы месяца/года ломают непрерывность, бакеты неравной длины (последний бакет — 2-3 дня). CV=(StdDev/Mean) и классификация X/Y/Z считаются по этим искажённым бакетам, что прямо искажает XYZ-метрику в графе и LLM-ответах. Также весь ABC/XYZ наследует scope только draft+bottles (кухня в граф не грузится) и определение revenue=DishDiscountSumInt. Требует отдельного семантического ревью.
- **core/dashboard_analysis.py — жёсткая зависимость подсчёта чеков от поля фан-аута UniqOrderId.Id** — _count_unique_orders считает total_checks через set(record['UniqOrderId.Id']) — то есть метрика 'Чеки' и 'Средний чек' дашборда напрямую зависят от того самого поля UniqOrderId.Id в groupByRowFields, которое в найденных проблемах (semantic/performance) предлагается убрать ради устранения фан-аута. Это незафиксированная связь: удаление поля сломает подсчёт чеков. Нужно отметить как риск согласованности правок (любой фикс фан-аута обязан одновременно переписать _count_unique_orders, например на sum(UniqOrderId.OrdersCount)).
- **knowledge_graph/engine/schema_context.py — семантический дрейф LLM-схемы относительно реальных OLAP-полей и конфигурации** — GRAPH_SCHEMA/EXAMPLE_QUERIES, отдаваемые LLM для генерации Cypher, описывают revenue как 'выручку' (фактически = DishDiscountSumInt, выручка со скидкой — то же расхождение определения, что отмечено для RevenueMetricsCalculator), markup как '%' хотя в iiko ProductCostBase.MarkUp — доля 0..1, и перечисляют бары ('Бар Культура 1', 'Гражданка', 'Краснопутиловская'), часть которых не совпадает с venues_config/реальными Store.Name. LLM будет генерировать запросы с несуществующими барами и неверно трактовать наценку. Не покрыто (ревью не включало knowledge_graph/engine).
- **scripts/daily_sync.py — рассинхрон таймзон и проглатывание ошибок ETL** — sync_data использует наивный datetime.now() (локальное/UTC время сервера), тогда как sales_loader.load_last_month и core/* работают в Europe/Moscow. На стыке полуночи это сдвигает синхронизируемый день. Плюс обе фазы обёрнуты в except Exception с logger.error без re-raise и без ненулевого кода выхода — планировщик (cron/Task Scheduler) считает запуск успешным даже при полном провале загрузки. Надёжность batch-ETL не покрыта (ревью надёжности касалось только web-роутов и core).
- **core/draft_analysis.py — недетерминированный эвристический парсинг объёма порции (нарушение принципа 'детерминированные расчёты')** — extract_beer_info/_estimate_volume извлекают литраж из строки DishName регэкспами с фолбэком 0.5л 'по умолчанию', затем DishAmountInt (порции) умножается на этот объём для расчёта литров/кег. Любая позиция без распознанного объёма молча считается как 0.5л, что искажает TotalLiters/Kegs30L. Это противоречит CLAUDE.md (никаких магических чисел, формула должна быть прозрачна) и является семантическим риском downstream OLAP-данных, не отражённым в найденном (там только strptime в analysis.py).
- **Эмодзи в коде/выводе (нарушение Style Rules) — comparison_calculator.py и __main__-стенды** — core/comparison_calculator.get_summary_insights формирует строки инсайтов с эмодзи (галочки/крестики/предупреждения), которые уходят в UI/ответы; CLAUDE.md прямо запрещает эмодзи в коде и тексте интерфейса. Уже найден только эмодзи-стенд в olap_reports __main__. Стоит расширить deadcode/style-линзу на все потребители метрик (comparison_calculator, и проверить trends_analyzer / scripts) — это потребительский слой OLAP-метрик, не покрытый ревью.
- **core/revenue_metrics.py — определение 'фактической выручки' только по фасовке + утечка слота лицензии (уточнение охвата)** — _calculate_actual_revenue берёт get_beer_sales_report (фильтр Напитки Фасовка) и комментирует 'подойдёт для общей выручки' — фактически KPI 'факт vs план' считает только бутылочную выручку, исключая розлив и кухню (родственно найденному 'RevenueMetricsCalculator считает общую выручку только по фасовке', но здесь это ДРУГОЙ метод, _calculate_actual_revenue, питающий план/факт-отчёт — стоит подтвердить отдельно). Здесь же olap.disconnect() стоит на happy-path, а не в finally (частично пересекается с найденным, но для этого конкретного метода и его влияния на план/факт KPI охват неполон).
- **Смежные не-OLAP отчёты: get_store_balances и get_store_operations_report — downstream-потребители в routes/stocks.py и routes/expiration.py** — Ревью заявило core/explorer, draft/waiter/revenue/employee_analysis как покрытые downstream, но stocks/expiration-потребители balance/stores и storeOperations (6+ вызовов get_store_balances в stocks.py, 1 в expiration.py) по сути не разобраны на предмет: единообразия обработки ошибок (or [] глушит None), скоупинга по бару (для storeOperations фильтр по складу закомментирован — это уже найдено, но влияние на expiration/остатки и согласованность Store.Name-маппинга между balances и SALES-отчётами не оценено). Стоит ревью согласованности идентичности склада/бара между balance-отчётом и OLAP SALES.

## Changelog

### 2026-06-02 — аудит OLAP-отчётов

- Проведён полный аудит 24 OLAP-запросов проекта по 6 линзам с состязательной верификацией каждой находки.
- Результат: 42 сырых находок -> 26 консолидированных issue (0 critical, 4 high, 6 medium, 16 low); 2 отклонено верификацией.
- Правки НЕ вносились — отчёт фиксирует проблемы и рекомендации для последующего исправления.
- Метод: многоагентный workflow (resume после сбоя verify-агентов) + консолидация дубликатов между линзами.