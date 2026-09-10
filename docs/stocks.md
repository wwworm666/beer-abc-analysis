# stocks.md — Заказы и остатки (`/stocks`)

Страница «Заказы и остатки»: шесть вкладок поверх остатков iiko, операций за окно и
кэша Честного Знака. Blueprint `stocks_bp` в [routes/stocks.py](../routes/stocks.py),
шаблон [templates/stocks.html](../templates/stocks.html).

> **Сроки годности (iiko + Честный Знак)** — отдельный документ:
> [chz-stock-integration.md](chz-stock-integration.md) (частично устарел, см. баннер там).
> **Реестр проблем страницы и решения владельца** —
> [technical/audits/STOCKS_AUDIT_2026-09-10.md](technical/audits/STOCKS_AUDIT_2026-09-10.md).
> **Целевая концепция редизайна** —
> [planning/stocks-order-redesign-2026-09-10.md](planning/stocks-order-redesign-2026-09-10.md).

## Что это

| Вкладка | Эндпоинт | Что показывает |
|---|---|---|
| Сводный заказ (по умолчанию) | `GET /api/stocks/order-board?bar=` | Фасовка + кеги + кухня одной таблицей с рекомендацией к заказу и срочностью |
| Таплист | `GET /api/stocks/taplist?bar=` | Остатки кег в литрах, только сорта на активных кранах бара |
| Фасовка | `GET /api/stocks/bottles?bar=` | Остатки и расход товаров верхней группы «Напитки Фасовка» |
| Сроки годности | `GET /api/stocks/expiry?bar=`, `POST /api/chz/refresh`, `GET /api/chz/refresh/status` | Фасовка с партиями и сроками из ЧЗ (view-only) |
| Меню кухни | `GET /api/stocks/kitchen?bar=` | Остатки и расход товаров верхней группы «ЕДА» |
| Формирование заказа | нет запросов | Корзина в памяти браузера, один CSV на поставщика |

Параметр `bar` обязателен: имя из `extensions.BARS` или `Общая` (вся сеть). Любое
другое значение — `400` со списком `known_bars`.

Служебные эндпоинты: `GET /api/chz/stock` (сырой кэш ЧЗ), `GET /api/stocks/chz`
(legacy, синхронный вызов ЧЗ, UI не использует).

## Файлы

- [routes/stocks.py](../routes/stocks.py) — эндпоинты, классификация, формулы заказа.
- [core/stock_snapshot.py](../core/stock_snapshot.py) — один снимок сети (остатки + операции + номенклатура) с кэшем.
- [core/stock_consumption.py](../core/stock_consumption.py) — расход по складу за окно, знаменатель периода.
- [core/nomenclature_xml.py](../core/nomenclature_xml.py) — полная номенклатура из XML с именем верхней группы.
- [core/olap_reports.py](../core/olap_reports.py) — `get_store_balances`, `get_store_operations_report`, `get_nomenclature`.
- [extensions.py](../extensions.py) — `get_cached_nomenclature` (память 15 мин, диск 24 ч), `cached_olap`, `taps_manager`, `BARS`.
- [core/taps_manager.py](../core/taps_manager.py) — активные краны для таплиста.
- [core/iiko_barcodes.py](../core/iiko_barcodes.py) — баркоды из XML для стыковки с ЧЗ.
- [routes/expiration.py](../routes/expiration.py) — `/expiration` использует тот же снимок и тот же расчёт расхода.
- [templates/stocks.html](../templates/stocks.html) — UI всех вкладок.

## Как работает

### Снимок сети

Все пять эндпоинтов читают один и тот же снимок `core.stock_snapshot.get_stock_snapshot()`:

- `balances` — `GET /v2/reports/balance/stores` (остатки по всем складам, на текущий момент).
- `operations` — `GET /reports/storeOperations` за окно `сегодня − 30 .. сегодня` по всем
  складам: фильтр склада в `get_store_operations_report` не передаётся (закомментирован),
  поэтому запрос один на сеть, а скоуп по бару делается по `primaryStore` записи в Python.
- `today`, `date_from`, `date_to`, `window_days`, `fetched_at` — даты московские.

Кэш 120 с на процесс (`SNAPSHOT_TTL`; 2 воркера gunicorn — не больше двух сессий iiko на
выбор бара вместо пяти), одновременные запросы ждут один fetch (single-flight в
`extensions.cached_olap`). Время снимка отдаётся в каждом ответе как `updated_at` и
показывается над Сводным заказом. `get_stock_snapshot(force=True)` сбрасывает кэш
(кнопка «Обновить» на `/expiration`).

Если iiko не отдал остатки или операции, или отдал пустые списки (четыре склада за 30
дней пустыми не бывают), снимка нет, он не кэшируется, и эндпоинт отвечает
`503 {"error": ..., "code": "iiko_unavailable"}`; номенклатура недоступна — `503`
`nomenclature_unavailable`. Именно 503, а не 502: фронт повторяет только 502 (прокси при
пробуждении), а это ответ приложения. После неудачи следующие 30 с (`SNAPSHOT_FAIL_TTL`)
снимок сразу `None`, чтобы пять запросов фронта не ждали таймаут iiko по очереди. Нули за
факт не выдаются.

### Номенклатура

`core.stock_snapshot.get_stocks_nomenclature()` = OLAP-номенклатура
(`extensions.get_cached_nomenclature`: товары с операциями за 30 дней, свежие
категории) поверх полной XML-номенклатуры (`data/cache/nomenclature__products.xml`,
8 тысяч товаров; файл обновляется вручную, см. chz-stock-integration.md). Запись:
`{name, type, category, mainUnit, parentId}`, где `parentId` — имя верхней группы
(`Product.TopParent`); для XML оно вычисляется подъёмом по цепочке групп
(`core/nomenclature_xml.py`). Если OLAP-запись или старый дисковый кэш несёт GUID вместо
имени, верхняя группа берётся из XML. Для OLAP запрашивается только OLAP-вариант
(`get_nomenclature_olap_only`), без XML-fallback самого iiko. Товар с остатком, но без
движения за месяц, больше не исчезает из списков. Товар без верхней группы в iiko и не в
литрах (на 2026-09-10 это ПЭТ-бутылки и одна «Мичелада») ни в одну вкладку не попадает.

### Классификация позиции (`_classify`)

По верхней группе номенклатуры, единый источник с дашбордом
(`core.dashboard_analysis.DashboardMetrics.TOP_PARENT_*`):

| Вид | Условие |
|---|---|
| пропуск | `type` не `GOODS`/`PREPARED` (блюда и модификаторы остатков не имеют) |
| `bottle` | верхняя группа «Напитки Фасовка» (или GUID `6103ecbf-…`) |
| `kitchen` | верхняя группа «ЕДА» — решение владельца 2026-09-10; поставщик и единица роли не играют |
| `draft` | верхняя группа «Напитки Розлив» в литрах (банка в штуках под «Розлив» пропускается); для товара без известной группы — `GOODS` в литрах |
| пропуск | всё остальное |

Единица (`unit`) — `mainUnit` номенклатуры (шт, л, кг), в ответе у каждой позиции.
Поставщик — `category` номенклатуры как есть (варианты написания не склеиваются).

### Остаток и расход

`stock` — сумма `amount` по записям balance/stores склада бара; для «Общая» — по всем
складам.

Расход — `core.stock_consumption.aggregate_consumption` (формулы там же в докстринге):

```
outgoing        = Σ |amount| по записям storeOperations с incoming == 'false'
                  и primaryStore == склад бара
                  включает продажи, перемещения ИЗ бара и списания
                  (решение владельца: перемещения — расход бара)
                  «Общая»: все склады, но перемещения между своими складами
                  (INTERNAL_TRANSFER) не считаются — товар сеть не покинул
days_in_period  = 30, либо для товара, которого не было в начале окна —
                  дни с первого прихода по сегодня включительно, не меньше 1
avg_per_day     = outgoing / days_in_period
```

«Не было в начале окна» = первый приход внутри окна и не позже сегодня, до него в
окне нет расхода, и остаток на начало окна (`остаток сейчас − приходы + расходы`) не
больше нуля. Так товар с остатком, которому просто привезли ещё, не становится
«новинкой». Записи без поля `incoming` пропускаются (счётчик `skipped`); нулевые
суммы порядок событий не меняют.

В ответах: `avg_sales` (= `avg_per_day`, 2 знака), `days_in_period`, `is_new`,
`consumption_scope` (`store` / `network`), у Сводного заказа ещё `consumption_by_type`
(расход по `documentType`). В таблицах новинка подписана «(с прихода, N дн.)» с
подсказкой при наведении.

Окно запроса: `dateFrom = сегодня − 30`, `dateTo = сегодня`, границы включительно, то есть
30 полных дней плюс неполный сегодняшний; делитель 30. Осознанное упрощение.

### Уровни остатка

Фасовка, Кухня, Сроки годности (`_stock_level_by_days`): `days_left = stock / avg_per_day`;
`< 3` дней — `low`, `< 7` — `medium`, иначе `high`; без расхода — `high`. Отрицательный
остаток отдельного уровня здесь не имеет (открытый пункт S-19 реестра).

Таплист (по литрам, кеги 20/30/50 л): `< 0` — `negative`, `< 10` — `low`, `< 25` —
`medium`, иначе `high`. Константы `TAPLIST_LOW_LITERS`, `TAPLIST_MEDIUM_LITERS`.

### Таплист

Активные краны — `taps_manager.get_bar_taps(bar_id)` (`status == active`); для «Общая»
все четыре бара. Название кеги нормализуется одной функцией `_normalize_keg_name` и для
кранов, и для iiko: убираются префикс «Кег», объём «N л», хвост «кег». Совпадение только
точное. Остатки — `GOODS` в литрах из снимка, кроме верхней группы «ЕДА» (масло в литрах
не кега). Фильтр «только то, что на кранах» действует для каждого склада отдельно: если
у бара активных кранов нет, показываются все его кеги с ненулевым (в том числе
отрицательным) остатком, и в режиме «Общая» они не прячутся за кранами соседнего бара.
Активный кран без остатка в iiko попадает в список с `remaining_liters: 0`.

### Сводный заказ (`GET /api/stocks/order-board?bar=X`)

Позиции видов `bottle`, `draft`, `kitchen` по складу бара. Для `bottle` подмешиваются
`nearest_expiry` / `days_to_expiry` из кэша ЧЗ по КПП бара (та же стыковка, что во
вкладке «Сроки годности»). Разливное считается в литрах (решение владельца: к кегам не
привязываемся).

**Рекомендация** (`_calc_recommendation`):

```
target_stock = avg_sales × (lead_time_days + SAFETY_DAYS)
deficit      = max(0, target_stock − stock)
recommended  = ceil(deficit / pack_size) × pack_size
```

- `lead_time_days` — из `SUPPLIER_PARAMS` по точному имени поставщика, иначе
  `SUPPLIER_DEFAULT` (3 дня). В списке только 13 кухонных поставщиков; пивные получают
  значение по умолчанию (TODO: справочник поставщиков, этап 3 редизайна).
- `SAFETY_DAYS = 3` — страховой запас на колебания спроса и под задержку поставки на 1–2 дня (решение владельца 2026-09-10).
- `pack_size` — 1 для всех (прототип); для кег не нужен по решению владельца.

Спецслучаи: `velocity ∈ {dead, slow}` → 0; `0 <= days_to_expiry < 14`
(`NEAR_EXPIRY_BLOCK_DAYS`) → 0. Просроченная партия (`days_to_expiry < 0`) рекомендацию
не блокирует (S-15 реестра).

**Скорость** (`_velocity`, по `avg_sales × DAYS_PER_WEEK`): `dead` = 0; `slow` < 1 в неделю;
`regular` 1–7; `fast` ≥ 7 (`SLOW_MOVER_WEEKLY_SALES`, `FAST_MOVER_WEEKLY_SALES`). В блоке
формулы над таблицей и в колонках та же величина называется «расход», не «продажи».

**Срочность** (`_urgency_level`), порядок проверок важен: `stock < 0` → `critical`;
`dead/slow` → `low`; `days_left < 1` → `critical`; `< lead_time_days` → `high`;
`< lead_time_days + SAFETY_DAYS` → `medium`; иначе `low`.

Ответ: `bar`, `updated_at` (время снимка), `chz_updated_at`, `consumption_scope`,
`window_days`, константы формулы (`safety_days`, `near_expiry_block_days`,
`slow_mover_weekly_sales`, `fast_mover_weekly_sales`), счётчики
(`critical_count`, `high_count`, `medium_count`, `active_count`, `slow_count`,
`dead_count`, `recommended_total`) и `items[]`: `product_id, type, name, supplier, unit,
stock, avg_sales, weekly_sales, days_in_period, is_new, consumption_by_type, velocity,
days_left, lead_time_days, pack_size, recommended, urgency, nearest_expiry,
days_to_expiry`. Сортировка: срочность, затем `days_left`.

### Фасовка и Кухня

`GET /api/stocks/bottles` и `GET /api/stocks/kitchen`: `items[]` с
`product_id, category, name, unit, stock, avg_sales, days_in_period, is_new, stock_level`,
сортировка по (`category`, `name`); верхний уровень — `bar, updated_at, consumption_scope,
window_days, total_items, low_stock_count`. UI показывает единицу рядом с остатком и
помечает новинки («новинка, N дн.»).

### Сроки годности

`GET /api/stocks/expiry`: те же позиции, что Фасовка, плюс стыковка iiko ↔ ЧЗ:
`барcode из XML → GTIN-14 → chz_stock.json → партии по КПП бара` (для «Общая» — все партии
юрлица). Поля: `gtins, chz_total_count, bar_chz_count, expiration_dates, production_dates,
inferred_batches, nearest_expiry, latest_expiry, days_to_expiry, has_chz_data`.
`near_expiry_count` считает `0 <= days_to_expiry < NEAR_EXPIRY_WARN_DAYS` (30, отдаётся в
ответе как `near_expiry_warn_days`), тот же порог поднимает «горящие» позиции наверх. Если все партии просрочены,
`nearest_expiry` — самая поздняя просроченная дата, дни отрицательные. Обновление кэша ЧЗ
и его устройство — в chz-stock-integration.md и expiration.md.

### Корзина и экспорт

`ordersByBar` в памяти браузера (теряется при перезагрузке), ключ позиции — тип + название
в пределах бара; вкладки Фасовка и Кухня передают поставщика и единицу, Таплист — нет.
Экспорт: один CSV на поставщика через все бары, колонки `Тип, Название, Бар, Количество,
Ед.` (известные дефекты S-10…S-13 реестра; корзина переезжает на сервер на этапе 1
редизайна).

## Changelog

- **2026-09-10 (этап 0 редизайна)** — Расход считается по складу выбранного бара
  (`primaryStore`), а не по всей сети; для «Общая» перемещения между своими складами не
  считаются; один снимок сети с кэшем 120 с и отрицательным кэшем 30 с вместо пяти
  iiko-сессий; сбой или пустой ответ iiko — явный 503; номенклатура OLAP поверх полной XML
  с именем верхней группы (товары без движения не исчезают, фасовка на XML не пустая, GUID
  в старом кэше заменяется именем); знаменатель периода для товара, которого не было в
  начале окна; кухня = группа «ЕДА»; классификация только для `GOODS`/`PREPARED`; единицы
  из номенклатуры; неизвестный бар → 400; таплист фильтрует по кранам посклада;
  `/expiration` переведён на тот же снимок и окно, `force=1` обновляет снимок. Документ
  переписан под фактический код (прежние разделы Taplist/Kitchen/Bottles описывали OLAP
  SALES, которого в коде не было).
- **2026-04-30** — Shelf-Life Cockpit `/expiration`; таб «Сроки годности» остался view-only.
- **2026-04-27** — Velocity-классификация; прототип «Сводный заказ»; CSV по поставщикам.
- **2026-04-26** — Интеграция iiko ↔ ЧЗ (см. chz-stock-integration.md).
- **2026-04-22** — `GET /api/chz/stock`, `POST /api/chz/refresh`.
- **2026-04-05** — `GET /api/stocks/chz` (legacy).
- **2026-03-27** — Документ создан.
