# stocks.md — Остатки товаров

Flask Blueprint `stocks_bp` — API остатков товаров (фасовка, кеги, кухня) и сводный заказ. Реализован в [routes/stocks.py](../routes/stocks.py).

> **Сроки годности (интеграция iiko + Честный Знак) — отдельный документ:** [chz-stock-integration.md](chz-stock-integration.md).
>
> Полная схема dispenser API, КПП-привязка партий к барам, авторефреш в 03:00 МСК, вкладка «Сроки годности» — там. Здесь — только taplist / kitchen / bottles / order-board.

## Что это

Четыре группы данных + сводный заказ:
- **Taplist** — кеги на кранах (из `taps_manager`)
- **Kitchen** — продажи кухни (из iiko OLAP, исключая «Напитки Розлив/Фасовка»)
- **Bottles** — продажи фасовки (из iiko OLAP, фильтр «Напитки Фасовка»)
- **Order Board** — сводная таблица «сколько заказать» с velocity-классификацией
- **Expiry** — сроки годности через ЧЗ (см. `chz-stock-integration.md`)

## Файлы

- [routes/stocks.py](../routes/stocks.py) — все endpoint'ы Blueprint `stocks_bp`
- [core/olap_reports.py](../core/olap_reports.py) — `get_kitchen_sales_report`, `get_draft_sales_report`, `get_store_operations_report` (для velocity)
- [core/taps_manager.py](../core/taps_manager.py) — данные о кранах для taplist
- [core/iiko_barcodes.py](../core/iiko_barcodes.py) — баркоды iiko из XML (для стыковки с ЧЗ)
- [chz_test/chz.py](../chz_test/chz.py) — единый ЧЗ-клиент (auth + dispenser API + парсер CSV)
- [core/chz_scheduler.py](../core/chz_scheduler.py) — daemon-thread авторефреш в 03:00 МСК
- [templates/stocks.html](../templates/stocks.html) — UI всех вкладок

## API endpoints

| Endpoint | Метод | Назначение |
|---|---|---|
| `/api/stocks/taplist` | GET | Кеги на кранах (taps_manager → активные) |
| `/api/stocks/kitchen` | GET | Продажи кухни за период |
| `/api/stocks/bottles` | GET | Продажи фасовки за период |
| `/api/stocks/order-board?bar=X` | GET | Сводный заказ: фасовка + кеги + кухня в одной таблице |
| `/api/stocks/expiry?bar=X` | GET | Сроки годности — см. [chz-stock-integration.md](chz-stock-integration.md) |
| `/api/chz/stock` | GET | Сырой ЧЗ-кэш — см. `chz-stock-integration.md` |
| `/api/chz/refresh` | POST | Обновить ЧЗ-кэш через бар-ПК — см. `chz-stock-integration.md` |
| `/api/chz/refresh/status` | GET | Polling прогресса refresh |

---

## Taplist (`GET /api/stocks/taplist`)

Источник: `taps_manager.get_bars()` → активные краны.

Формат ответа:
```json
[
  {
    "bar_name": "Большой пр. В.О",
    "tap_number": 5,
    "beer_name": "Жигулёвское",
    "keg_id": "KEG-12345",
    "started_at": "2026-03-25T10:00:00+03:00"
  }
]
```

`stock_level` (расчётный уровень запаса) на основе `days_left`:
- `critical` — `days_left < 3`
- `low` — `days_left < 7`
- `ok` — `days_left >= 7`

---

## Kitchen (`GET /api/stocks/kitchen`)

Параметры: `dateFrom`, `dateTo`, опционально `bar`.

Запрос: [core/olap_reports.py:_build_kitchen_olap_request](../core/olap_reports.py) — SALES report с фильтром
`DishGroup.TopParent ExcludeValues ["Напитки Фасовка", "Напитки Розлив"]`.

Группировка: `Store.Name`, `DishName`, `DishGroup.TopParent`, `DishForeignName`, `OpenDate.Typed`.
Агрегаты: `UniqOrderId.OrdersCount`, `DishAmountInt`, `DishDiscountSumInt`, `ProductCostBase.ProductCost`, `ProductCostBase.MarkUp`.

---

## Bottles (`GET /api/stocks/bottles`)

Параметры: `dateFrom`, `dateTo`, опционально `bar`.

Запрос: тот же `_build_kitchen_olap_request`-паттерн, но с фильтром
`DishGroup.TopParent IncludeValues ["Напитки Фасовка"]`.

Группировка: добавляется `DishGroup.ThirdParent` (подкатегория фасовки).

---

## Order Board (`GET /api/stocks/order-board?bar=X`)

Объединённая таблица фасовка + кеги + кухня — одно представление со всеми позициями, требующими решения «сколько заказать». Главная вкладка `/stocks` (открыта по умолчанию).

Возвращает: `items[]` отсортирован по срочности, counters по уровням срочности, суммарная рекомендация.

### Формулы

**Рекомендация к заказу** (`_calc_recommendation` в [routes/stocks.py](../routes/stocks.py)):

```
target_stock = avg_sales × (lead_time_days + SAFETY_DAYS)
deficit      = max(0, target_stock − stock)
recommended  = ceil(deficit / pack_size) × pack_size
```

Где:
- `avg_sales` — расход/день за последние 30 дней (из `OlapReports.get_store_operations_report`)
- `lead_time_days` — срок поставки от поставщика (из `SUPPLIER_PARAMS`, fallback = 3 дня)
- `SAFETY_DAYS = 3` — страховой запас сверх lead_time
- `pack_size` — минимальная партия (упаковка), в прототипе = 1 для всех

**Velocity-классификация** (`_velocity`) по продажам в неделю:

| Класс | Условие | Поведение |
|---|---|---|
| `dead` | `avg_sales == 0` | `recommended = 0`, urgency = `low` |
| `slow` | < 1 продажи в неделю | `recommended = 0`, urgency = `low` |
| `regular` | 1–7 в неделю | обычная логика |
| `fast` | ≥ 7 в неделю | обычная логика |

Константы: `SLOW_MOVER_WEEKLY_SALES = 1.0`, `FAST_MOVER_WEEKLY_SALES = 7.0`.

**Зачем velocity:** позиция типа «Эплтон Апельсин 0.5л» с продажами 0.03/день (≈ раз в месяц) при нулевом остатке без velocity-классификации даёт `days_left = 0` → `urgency = critical`. Шум: менеджеру не нужно бежать заказывать редкое.

**Спецслучаи рекомендации:**
- `velocity ∈ {dead, slow}` → `recommended = 0` (не пополняем)
- `0 <= days_to_expiry < 14` → `recommended = 0` (расходуем то что есть)

**Срочность** (`_urgency_level`):

| Уровень | Условие |
|---|---|
| `critical` | `stock < 0` (учётная ошибка — важнее velocity) |
| `low` | `velocity ∈ {dead, slow}` (даже при stock=0) |
| `critical` | `days_left < 1` |
| `high` | `days_left < lead_time_days` |
| `medium` | `days_left < lead_time_days + SAFETY_DAYS` |
| `low` | остальное |

Порядок проверок важен: отрицательный остаток всегда critical, но slow-mover с stock=0 — это `low`.

### Параметры поставщиков

`SUPPLIER_PARAMS` в [routes/stocks.py](../routes/stocks.py) — словарь `{lead_time_days, pack_size}` на поставщика. Значения подобраны эмпирически. **TODO:** вынести в редактируемые настройки (БД/файл).

### Классификация позиций

`classify(product_id, product_info)` возвращает один из четырёх:
- `'bottle'` — `product_id ∈ fasovka_product_ids` (группа «Напитки Фасовка»)
- `'draft'` — `type == 'GOODS' AND mainUnit == 'л'` (кеги; проверка после bottle)
- `'kitchen'` — `category` ∈ `food_categories` И не пиво по ключевым словам
- `None` — пропускаем

В отличие от `/api/stocks/taplist`, **draft-кеги показываются все**, а не только те что на кране — для заказа учитываются и запасные.

### Стыковка с ЧЗ

Только для `type='bottle'`: подмешиваются `nearest_expiry`/`days_to_expiry` через `barcode_map ↔ chz_by_gtin ↔ КПП бара` (та же логика что в `/api/stocks/expiry`).

### UI

Колонки: Срочность, Поставщик, Позиция, Тип, Скорость, Остаток, **В неделю**, Хватит дн., Поставка дн., Истекает, Рекомендация, Заказ.

«В неделю» = `avg_sales × 7` — по просьбе менеджера, weekly-цифры интуитивнее для бара.

Подсветка строк:
- `critical` → красный фон
- `high` → жёлтый фон
- `days_to_expiry < 30` → светло-красный фон

Фильтры: Тип / Поставщик / Срочность / **Скорость** (по умолчанию = `Только активные (regular+fast)` — slow/dead скрыты).

Кнопка «Применить рекомендации» — заполняет инпуты значением `recommended` для всех видимых строк.

### Экспорт заказа

**Один CSV на поставщика** (через все бары), не на бар. Это совпадает с реальной единицей отправки заказа.
Колонки CSV: `Тип, Название, Бар, Количество, Ед.`

---

## Changelog

- **2026-04-30** — Shelf-Life Cockpit — отдельная страница [`/expiration`](expiration.md) с tier-классификацией и рекомендациями уценки/перевода. Таб «Сроки годности» в `/stocks` остался view-only.
- **2026-04-27 (вечер)** — Velocity-классификация (`dead/slow/regular/fast`). Slow/dead получают `recommended=0` и `urgency=low`. UI: колонка «Ср/день» → «В неделю», добавлена «Скорость» и фильтр velocity.
- **2026-04-27** — Прототип «Сводный заказ» (`/api/stocks/order-board`) с расчётом рекомендации `target − stock`. Экспорт переключён с группировки по барам на группировку по поставщикам.
- **2026-04-26** — Полная интеграция iiko ↔ ЧЗ (см. [chz-stock-integration.md](chz-stock-integration.md)).
- **2026-04-22** — Добавлены `GET /api/chz/stock` (кэш) и `POST /api/chz/refresh` (бар-ПК через SSH).
- **2026-04-05** — Добавлен `GET /api/stocks/chz` (прямой вызов ЧЗ через бар-ПК с CryptoPro).
- **2026-03-27** — Создан документ stocks.md с описанием taplist, кухни, фасовки.
