# OLAP Reports Collection — копии всех OLAP-запросов проекта

> Сгенерировано 2026-05-31. Единое место со ВСЕМИ копиями OLAP-отчётов (тел запросов к iiko
> OLAP API), используемых в проекте. Документ-карта (где лежит + аудит-заметки):
> [OLAP_REQUEST_REGISTRY_2026-04-03.md](audits/OLAP_REQUEST_REGISTRY_2026-04-03.md).
> Этот файл дополняет реестр **дословными копиями JSON-тел**.

> **Обновление 2026-06-02:** идентичность сотрудника во всех отчётах переведена с `WaiterName`
> на `AuthUser` («Авторизовал», кто пробил чек) — единый ключ (см.
> [audits/OLAP_AUDIT_2026-06-02.md](audits/OLAP_AUDIT_2026-06-02.md) #11 и CHANGELOG). Затронуты
> отчёты #7, #8, #10, #11, #12, #13 и вариант #5 с `include_waiter`. Геттеры алиасят `AuthUser`
> -> `WaiterName` в ответе, поэтому downstream читает прежний ключ. JSON-тела ниже обновлены.

## Что это

Полный инвентарь из **24 OLAP-запросов** — каждое тело скопировано из исходного кода
дословно (`JSON.parse` -> `JSON.stringify`, без ручной правки). Собрано из `core/`, `routes/`,
`scripts/`, `tests/`. Запросы к iiko OLAP идут POST-ом на `/v2/reports/olap` с JSON-телом,
содержащим `reportType`, `groupByRowFields`, `aggregateFields`, `filters`.

Распределение по статусу:

- **PRODUCTION** — 16
- **DIAGNOSTIC** — 1
- **AD-HOC** — 1
- **DEBUG** — 5
- **TEST** — 1

## Как читать

- Каждый раздел — одно тело запроса. `Источник` указывает файл и диапазон строк литерала.
- JSON приведён **дословно**; f-string подстановки заменены плейсхолдерами:
  `{date_from}`, `{date_to}`, `{bar_name}`, `{field}`, `{employee_name}`.
- `Динамика` описывает, как параметры мутируют тело (например `bar_name` добавляет фильтр
  `Store.Name`; `draft` меняет значение `DishGroup.TopParent`; `include_waiter` добавляет `AuthUser`).
- Один builder может обслуживать несколько публичных отчётов — тело учтено **один раз**,
  варианты перечислены в `Динамика`/`Заметка` (см. `Потребители`).

## Правила источника истины (из реестра)

- Сначала семантика OLAP v2.
- Для `SALES` учётный день — `OpenDate.Typed`.
- `DateRange.to` трактуется как **исключающая** граница, поэтому приложение добавляет `+1 день`,
  когда период в UI включительный.
- `DeletedWithWriteoff=NOT_DELETED` и `OrderDeleted=NOT_DELETED` — стандартные предохранители
  для обычной аналитики продаж.
- `OrderNum` **не** является глобально уникальным идентификатором заказа.
- `ProductCostBase.MarkUp` в метаданных iiko — поле `PERCENT`, т.е. доля от `0` до `1`.
- Если локальные доки и живой `/v2/reports/olap/columns` расходятся — побеждают живые метаданные.

## Сводная таблица

| # | Отчёт | Endpoint | Type | Статус | Источник |
|---|---|---|---|---|---|
| 1 | Номенклатура товаров (TRANSACTIONS) | `/v2/reports/olap` | TRANSACTIONS | PRODUCTION | `core/olap_reports.py:101-121` |
| 2 | Продажи кухни (без официанта) | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:613-653` |
| 3 | Конструктор отчётов /explorer (расширенная иерархия категорий) | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:686-719` |
| 4 | Комплексные продажи (все категории за один запрос) | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:756-793` |
| 5 | Продажи пива (розлив/фасовка, опционально с официантом) | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:831-865` |
| 6 | Подсчёт количества чеков (заказов) | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:897-920` |
| 7 | Продажи кухни с официантом | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:1116-1157` |
| 8 | Отменённые/возвращённые позиции по официантам | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:1170-1192` |
| 9 | Агрегированные метрики по сотрудникам (AuthUser) | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:1228-1257` |
| 10 | KPI: сводка по сотрудникам (чеки/выручка/скидки) | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:1340-1351` |
| 11 | KPI: разбивка по категориям (доли/наценка) | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:1354-1365` |
| 12 | Дневная выручка по сотрудникам | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:1529-1555` |
| 13 | Новые карты лояльности по сотрудникам | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:1626-1659` |
| 14 | Список названий скидок (лёгкий запрос) | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:1717-1738` |
| 15 | Отчёт по скидкам с детализацией по гостям | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:1780-1812` |
| 16 | Отчёт для RFM-сегментации | `/v2/reports/olap` | SALES | PRODUCTION | `core/olap_reports.py:1867-1897` |
| 17 | Диагностика: перебор полей группировки по сотруднику | `/v2/reports/olap` | SALES | DIAGNOSTIC | `core/olap_reports.py:1450-1469` |
| 18 | Экспорт продаж разливного (расширенный набор полей) | `/v2/reports/olap` | SALES | AD-HOC | `scripts/import_export/export_draft_sales.py:67-103` |
| 19 | Чеки официанта по WaiterName (вариант дат, full/minimal) | `/v2/reports/olap` | SALES | DEBUG | `tests/debug/test_date_variants.py:9-37` |
| 20 | Чеки официанта с фильтром PayTypes (исключение) | `/v2/reports/olap` | SALES | DEBUG | `tests/debug/test_date_variants.py:122-151` |
| 21 | Чеки официанта только по закрытым заказам (OrderClose=CLOSED) | `/v2/reports/olap` | SALES | DEBUG | `tests/debug/test_date_variants.py:172-201` |
| 22 | Чеки официанта по дате закрытия (CloseDate.Typed) | `/v2/reports/olap` | SALES | DEBUG | `tests/debug/test_date_variants.py:222-247` |
| 23 | Чеки официанта по дням (OrderNum, группировка по дате) | `/v2/reports/olap` | SALES | DEBUG | `tests/debug/test_daily_checks.py:15-40` |
| 24 | Вайнштефан Хефе Вайсбир — максимальный набор полей продаж | `/v2/reports/olap` | SALES | TEST | `tests/test_weihenstephan_data.py:34-81` |

---

## Отчёты

## PRODUCTION — живое приложение (core/ + routes/)

### 1. Номенклатура товаров (TRANSACTIONS)

- ID: `nomenclature_via_olap`
- Источник: `core/olap_reports.py:101-121` — builder `_get_nomenclature_via_olap`
- Endpoint: `/v2/reports/olap` · reportType: `TRANSACTIONS` · статус: **PRODUCTION**
- Потребители:
  - `core/olap_reports.py:get_nomenclature (L71)`
- Динамика: Статичное тело. date_from = now-30 дней, date_to = now (формат YYYY-MM-DD), вычисляются внутри метода (timedelta(days=30) на L99; докстринг ошибочно говорит '90 дней'). Фильтр по DateTime.DateTyped (не OpenDate.Typed).
- Заметка: Единственный запрос с reportType=TRANSACTIONS. Используется как быстрый способ получить номенклатуру; при неудаче get_nomenclature падает на _get_nomenclature_via_xml.

```json
{
  "reportType": "TRANSACTIONS",
  "groupByRowFields": [
    "Product.Id",
    "Product.Name",
    "Product.Type",
    "Product.MeasureUnit",
    "Product.Category",
    "Product.TopParent"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "Amount"
  ],
  "filters": {
    "DateTime.DateTyped": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    }
  }
}
```

### 2. Продажи кухни (без официанта)

- ID: `kitchen_olap_request`
- Источник: `core/olap_reports.py:613-653` — builder `_build_kitchen_olap_request`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `core/olap_reports.py:get_kitchen_sales_report (L378)`
- Динамика: Если bar_name задан, добавляется filters["Store.Name"] = {filterType: IncludeValues, values: [{bar_name}]}. Иначе фильтр по бару отсутствует. Кухня = всё кроме DishGroup.TopParent 'Напитки Фасовка'/'Напитки Розлив' (ExcludeValues).
- Заметка: Builder; публичный геттер get_kitchen_sales_report (L378) формирует тело через этот метод.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "Store.Name",
    "DishName",
    "DishGroup.TopParent",
    "DishForeignName",
    "OpenDate.Typed"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId",
    "UniqOrderId.OrdersCount",
    "DishAmountInt",
    "DishDiscountSumInt",
    "DiscountSum",
    "ProductCostBase.ProductCost",
    "ProductCostBase.OneItem",
    "ProductCostBase.MarkUp"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DishGroup.TopParent": {
      "filterType": "ExcludeValues",
      "values": [
        "Напитки Фасовка",
        "Напитки Розлив"
      ]
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 3. Конструктор отчётов /explorer (расширенная иерархия категорий)

- ID: `explorer_sales`
- Источник: `core/olap_reports.py:686-719` — builder `get_explorer_sales`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `core/explorer.py:75`
- Динамика: Если bar_name задан, добавляется filters["Store.Name"] = {filterType: IncludeValues, values: [{bar_name}]}. Включает SecondParent/ThirdParent в groupByRowFields в отличие от dashboard-запроса.
- Заметка: Inline тело прямо в публичном методе get_explorer_sales (def L664). Отдельный кэш-ключ explorer_* в core/explorer.py. Ретраи по ReadTimeout обрабатываются ниже по телу метода.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "Store.Name",
    "DishName",
    "DishGroup.TopParent",
    "DishGroup.SecondParent",
    "DishGroup.ThirdParent",
    "OpenDate.Typed"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId.OrdersCount",
    "DishAmountInt",
    "DishDiscountSumInt",
    "ProductCostBase.ProductCost"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 4. Комплексные продажи (все категории за один запрос)

- ID: `all_sales_olap_request`
- Источник: `core/olap_reports.py:756-793` — builder `_build_all_sales_olap_request`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `core/olap_reports.py:get_all_sales_report (L425)`
- Динамика: Если bar_name задан, добавляется filters["Store.Name"] = {filterType: IncludeValues, values: [{bar_name}]}. НЕ фильтрует по DishGroup.TopParent — получает всё (розлив + фасовка + кухня). Включает UniqOrderId.Id в groupByRowFields для подсчёта чеков.
- Заметка: Builder; публичный геттер get_all_sales_report (L425).

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "Store.Name",
    "DishName",
    "DishGroup.TopParent",
    "DishForeignName",
    "OpenDate.Typed",
    "UniqOrderId.Id"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId.OrdersCount",
    "DishAmountInt",
    "DishDiscountSumInt",
    "DiscountSum",
    "ProductCostBase.ProductCost",
    "ProductCostBase.OneItem",
    "ProductCostBase.MarkUp"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 5. Продажи пива (розлив/фасовка, опционально с официантом)

- ID: `olap_request_base`
- Источник: `core/olap_reports.py:831-865` — builder `_build_olap_request`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `core/olap_reports.py:get_beer_sales_report (L237)`
  - `core/olap_reports.py:get_draft_sales_report (L284)`
  - `core/olap_reports.py:get_draft_sales_by_waiter_report (L331)`
  - `core/olap_reports.py:get_bottles_sales_by_waiter_report (L972)`
- Динамика: drink_group вычисляется на L812: draft=True -> "Напитки Розлив"; draft=False (по умолчанию) -> "Напитки Фасовка"; это значение попадает в DishGroup.TopParent.values. include_waiter=True добавляет "AuthUser" в конец groupByRowFields (на L829, до объявления request; показано тело без него). Если bar_name задан, добавляется filters["Store.Name"] = {filterType: IncludeValues, values: [{bar_name}]}. Базовое тело показано для draft=False, include_waiter=False.
- Заметка: Центральный builder. Геттеры: get_beer_sales_report (draft=False), get_draft_sales_report (draft=True), get_draft_sales_by_waiter_report (draft=True, include_waiter=True), get_bottles_sales_by_waiter_report (draft=False, include_waiter=True). Не дублировать — тело учтено один раз.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "Store.Name",
    "DishName",
    "DishGroup.ThirdParent",
    "DishForeignName",
    "OpenDate.Typed"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId",
    "UniqOrderId.OrdersCount",
    "DishAmountInt",
    "DishDiscountSumInt",
    "DiscountSum",
    "ProductCostBase.ProductCost",
    "ProductCostBase.OneItem",
    "ProductCostBase.MarkUp"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DishGroup.TopParent": {
      "filterType": "IncludeValues",
      "values": [
        "Напитки Фасовка"
      ]
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 6. Подсчёт количества чеков (заказов)

- ID: `orders_count_request`
- Источник: `core/olap_reports.py:897-920` — builder `_build_orders_count_request`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `core/olap_reports.py:get_orders_count (L931)`
- Динамика: Если bar_name задан, добавляется filters["Store.Name"] = {filterType: IncludeValues, values: [{bar_name}]}. Группировка только по Store.Name + OpenDate.Typed (без DishName) для корректного подсчёта уникальных заказов.
- Заметка: Builder; публичный геттер get_orders_count (L931).

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "Store.Name",
    "OpenDate.Typed"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId.OrdersCount"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 7. Продажи кухни с официантом

- ID: `kitchen_olap_request_with_waiter`
- Источник: `core/olap_reports.py:1116-1157` — builder `_build_kitchen_olap_request_with_waiter`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `core/olap_reports.py:get_kitchen_sales_by_waiter_report (L1019)`
- Динамика: Если bar_name задан, добавляется filters["Store.Name"] = {filterType: IncludeValues, values: [{bar_name}]}. Отличается от _build_kitchen_olap_request наличием "AuthUser" в groupByRowFields.
- Заметка: Builder; публичный геттер get_kitchen_sales_by_waiter_report (L1019).

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "Store.Name",
    "DishName",
    "DishGroup.TopParent",
    "DishForeignName",
    "OpenDate.Typed",
    "AuthUser"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId",
    "UniqOrderId.OrdersCount",
    "DishAmountInt",
    "DishDiscountSumInt",
    "DiscountSum",
    "ProductCostBase.ProductCost",
    "ProductCostBase.OneItem",
    "ProductCostBase.MarkUp"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DishGroup.TopParent": {
      "filterType": "ExcludeValues",
      "values": [
        "Напитки Фасовка",
        "Напитки Розлив"
      ]
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 8. Отменённые/возвращённые позиции по официантам

- ID: `cancelled_orders_request`
- Источник: `core/olap_reports.py:1170-1192` — builder `_build_cancelled_orders_request`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `core/olap_reports.py:get_cancelled_orders_by_waiter (L1066)`
- Динамика: Если bar_name задан, добавляется filters["Store.Name"] = {filterType: IncludeValues, values: [{bar_name}]}. Только удалённые/возвращённые позиции: DeletedWithWriteoff = ExcludeValues NOT_DELETED. Нет фильтра OrderDeleted.
- Заметка: Builder; публичный геттер get_cancelled_orders_by_waiter (L1066).

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "AuthUser"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "OrderNum"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "ExcludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 9. Агрегированные метрики по сотрудникам (AuthUser)

- ID: `employee_aggregated_metrics`
- Источник: `core/olap_reports.py:1228-1257` — builder `get_employee_aggregated_metrics`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `routes/employee.py:80`
  - `routes/employee.py:245`
  - `routes/employee.py:965`
- Динамика: Если bar_name задан, добавляется filters["Store.Name"] = {filterType: IncludeValues, values: [{bar_name}]}. Группировка по AuthUser ("Авторизовал" — кто пробил чек).
- Заметка: Inline тело прямо в публичном методе (def L1202). Результат — dict по именам сотрудников (ключ AuthUser). Вызывается через ThreadPoolExecutor в routes/employee.py.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "AuthUser"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId",
    "UniqOrderId.OrdersCount",
    "DishDiscountSumInt",
    "DiscountSum",
    "DishAmountInt"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 10. KPI: сводка по сотрудникам (чеки/выручка/скидки)

- ID: `kpi_olap_summary`
- Источник: `core/olap_reports.py:1340-1351` — builder `get_kpi_olap_data`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `routes/employee.py:773`
- Динамика: Статичное тело (bar_name не используется в этом методе — сигнатура get_kpi_olap_data(date_from, date_to)). filters берётся из общей переменной base_filters (L1322). buildSummary="false" (строка). Первый из двух запросов метода; выполняется параллельно через ThreadPoolExecutor(max_workers=2).
- Заметка: Первое из ДВУХ тел в get_kpi_olap_data (summary_request). Второе — kpi_olap_categories.

```json
{
  "reportType": "SALES",
  "buildSummary": "false",
  "groupByRowFields": [
    "AuthUser"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId.OrdersCount",
    "DishDiscountSumInt",
    "DiscountSum"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 11. KPI: разбивка по категориям (доли/наценка)

- ID: `kpi_olap_categories`
- Источник: `core/olap_reports.py:1354-1365` — builder `get_kpi_olap_data`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `routes/employee.py:773`
- Динамика: Статичное тело (bar_name не используется). filters берётся из общей переменной base_filters (L1322). buildSummary="false" (строка). Второй из двух запросов метода; выполняется параллельно через ThreadPoolExecutor(max_workers=2).
- Заметка: Второе из ДВУХ тел в get_kpi_olap_data (categories_request). Группировка по AuthUser + DishGroup.TopParent.

```json
{
  "reportType": "SALES",
  "buildSummary": "false",
  "groupByRowFields": [
    "AuthUser",
    "DishGroup.TopParent"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "DishDiscountSumInt",
    "ProductCostBase.ProductCost",
    "ProductCostBase.MarkUp"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 12. Дневная выручка по сотрудникам

- ID: `employee_daily_revenue`
- Источник: `core/olap_reports.py:1529-1555` — builder `get_employee_daily_revenue`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители: _внешних вызовов не найдено_
- Динамика: Статичное тело — нет параметра bar_name, фильтр по Store.Name не добавляется. Группировка по AuthUser + OpenDate.Typed.
- Заметка: Inline тело в публичном методе (def L1508). Результат: dict {name: {date: revenue}}. Внешних вызовов не найдено.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "AuthUser",
    "OpenDate.Typed"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "DishDiscountSumInt"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 13. Новые карты лояльности по сотрудникам

- ID: `new_loyalty_cards_by_waiter`
- Источник: `core/olap_reports.py:1626-1659` — builder `get_new_loyalty_cards_by_waiter`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `routes/employee.py:85`
  - `routes/employee.py:250`
  - `routes/employee.py:775`
- Динамика: Если bar_name задан, добавляется filters["Store.Name"] = {filterType: IncludeValues, values: [{bar_name}]}. Двойной фильтр по дате: OpenDate.Typed И Delivery.CustomerCreatedDateTyped (дата создания клиента в периоде).
- Заметка: Inline тело (def L1602). Считает уникальные телефоны клиентов по официантам.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "AuthUser",
    "Delivery.CustomerPhone"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId.OrdersCount"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "Delivery.CustomerCreatedDateTyped": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 14. Список названий скидок (лёгкий запрос)

- ID: `discount_names`
- Источник: `core/olap_reports.py:1717-1738` — builder `get_discount_names`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `routes/analysis.py:888`
- Динамика: Статичное тело — нет параметра bar_name, фильтр по Store.Name не добавляется. Группировка только по ItemSaleEventDiscountType (быстрый запрос).
- Заметка: Inline тело (def L1706). Возвращает только названия скидок без детализации по блюдам/чекам.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "ItemSaleEventDiscountType"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "DishDiscountSumInt"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 15. Отчёт по скидкам с детализацией по гостям

- ID: `discount_report`
- Источник: `core/olap_reports.py:1780-1812` — builder `get_discount_report`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `routes/analysis.py:930`
- Динамика: Если bar_name задан, добавляется filters["Store.Name"] = {filterType: IncludeValues, values: [{bar_name}]}. Детализация по гостям, чекам, блюдам, типу скидки. Агрегация per customer делается в Python.
- Заметка: Inline тело (def L1756). Отличается от get_rfm_report наличием DishName и ItemSaleEventDiscountType в groupByRowFields.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "Store.Name",
    "Delivery.CustomerCardNumber",
    "Delivery.CustomerName",
    "OrderNum",
    "DishName",
    "ItemSaleEventDiscountType",
    "OpenDate.Typed"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "DishDiscountSumInt",
    "DiscountSum"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 16. Отчёт для RFM-сегментации

- ID: `rfm_report`
- Источник: `core/olap_reports.py:1867-1897` — builder `get_rfm_report`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **PRODUCTION**
- Потребители:
  - `routes/analysis.py:1142`
- Динамика: Если bar_name задан, добавляется filters["Store.Name"] = {filterType: IncludeValues, values: [{bar_name}]}. Аналогичен get_discount_report, но без DishName и без ItemSaleEventDiscountType — все транзакции гостей за период.
- Заметка: Inline тело (def L1845). Используется для RFM-сегментации гостей.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "Store.Name",
    "Delivery.CustomerCardNumber",
    "Delivery.CustomerName",
    "OrderNum",
    "OpenDate.Typed"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "DishDiscountSumInt",
    "DiscountSum"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

---

## DIAGNOSTIC — диагностика полей (не для прод)

### 17. Диагностика: перебор полей группировки по сотруднику

- ID: `debug_employee_field_names`
- Источник: `core/olap_reports.py:1450-1469` — builder `debug_employee_field_names`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **DIAGNOSTIC**
- Потребители: _внешних вызовов не найдено_
- Динамика: Тело строится в цикле for field in candidates (candidates на L1438). {field} перебирает: WaiterName, OpenUser, OpenUser.Name, CloseUser, CloseUser.Name, Waiter, Waiter.Name, Employee, Employee.Name, AuthUser, OrderCloseUser, User, User.Name. На каждой итерации groupByRowFields = [field]. POST без timeout, через локальный импорт requests as req.
- Заметка: DIAGNOSTIC: инструмент поиска правильного имени поля 'Авторизовал' (def L1430). Не предназначен для прод-использования; внешних вызовов не найдено.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "{field}"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId",
    "UniqOrderId.OrdersCount",
    "DishDiscountSumInt"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

---

## AD-HOC — разовые скрипты

### 18. Экспорт продаж разливного (расширенный набор полей)

- ID: `export_draft_sales_extended`
- Источник: `scripts/import_export/export_draft_sales.py:67-103` — builder `build_extended_olap_request`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **AD-HOC**
- Потребители:
  - `scripts/import_export/export_draft_sales.py:fetch_olap_data (line 118, builds request then POSTs to f'{olap.api.base_url}/v2/reports/olap')`
  - `scripts/import_export/export_draft_sales.py:main (calls fetch_olap_data)`
- Динамика: date_from/date_to fill the OpenDate.Typed DateRange filter (CUSTOM period). Optional bar_name parameter (default None): when truthy, adds request['filters']['Store.Name'] = {filterType: IncludeValues, values: [bar_name]} (lines 105-109). Note: the only caller fetch_olap_data (line 118) never passes bar_name, so the Store.Name filter stays absent in practice; Store.Name still appears as a groupByRowField (line 70).
- Заметка: Only inline OLAP request body in the entire scripts/ tree (verified: grep 'reportType' in scripts/** returns exactly one hit, line 68). Verified line range 67-103 matches source exactly: builder build_extended_olap_request (def line 64), endpoint /v2/reports/olap (line 120), POST via requests.post with params {key: token}, Content-Type application/json, timeout 300s (lines 120-124). groupByRowFields order, aggregateFields order, all four filter blocks and literal values confirmed verbatim against source. One-off export utility (groups draft beer sales by store/dish/style/country/day with checks count, portions, revenue, markup %; later joined with keg->supplier mapping and written to Excel). All other scripts in scripts/** call helper methods on core.olap_reports.OlapReports (get_draft_sales_report, get_sales_report, get_beer_sales_report, get_kitchen_sales_report, get_draft_sales_by_waiter_report, get_nomenclature, get_store_balances) which build their request bodies inside core/, outside this assigned area.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "Store.Name",
    "DishName",
    "DishGroup.ThirdParent",
    "DishForeignName",
    "OpenDate.Typed"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId.OrdersCount",
    "DishAmountInt",
    "DishDiscountSumInt",
    "ProductCostBase.MarkUp"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DishGroup.TopParent": {
      "filterType": "IncludeValues",
      "values": [
        "Напитки Розлив"
      ]
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

---

## DEBUG — отладочные скрипты/тесты

### 19. Чеки официанта по WaiterName (вариант дат, full/minimal)

- ID: `date_variants_single`
- Источник: `tests/debug/test_date_variants.py:9-37` — builder `test_single`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **DEBUG**
- Потребители:
  - `tests/debug/test_date_variants.py::test_date_variants`
- Динамика: aggregateFields[0] = {field} parameter (e.g. OrderNum or UniqOrderId.OrdersCount). filters.WaiterName.values[0] = {employee_name} parameter. When filters_mode != 'full' (i.e. 'minimal'), the DeletedWithWriteoff and OrderDeleted filters are NOT added (lines 29-37 are conditional); body then contains only OpenDate.Typed and WaiterName filters.
- Заметка: Ad-hoc debug to reconcile a waiter's check count with iiko UI (target 233). Posts directly to {olap.api.base_url}/v2/reports/olap with params key=token.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "WaiterName"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "{field}"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "WaiterName": {
      "filterType": "IncludeValues",
      "values": [
        "{employee_name}",
        "Артемий Новаев"
      ]
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 20. Чеки официанта с фильтром PayTypes (исключение)

- ID: `date_variants_pay_types`
- Источник: `tests/debug/test_date_variants.py:122-151` — builder `test_with_pay_types`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **DEBUG**
- Потребители:
  - `tests/debug/test_date_variants.py::test_date_variants`
- Динамика: aggregateFields[0] = {field} parameter. filters.WaiterName.values[0] = {employee_name} parameter. PayTypes filter is static ExcludeValues of 'Без выручки' and 'Сертификат'.
- Заметка: Debug variant adding PayTypes exclusion to test whether unpaid order types explain the check-count discrepancy.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "WaiterName"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "{field}"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "WaiterName": {
      "filterType": "IncludeValues",
      "values": [
        "{employee_name}",
        "Артемий Новаев"
      ]
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "PayTypes": {
      "filterType": "ExcludeValues",
      "values": [
        "Без выручки",
        "Сертификат"
      ]
    }
  }
}
```

### 21. Чеки официанта только по закрытым заказам (OrderClose=CLOSED)

- ID: `date_variants_closed_orders`
- Источник: `tests/debug/test_date_variants.py:172-201` — builder `test_closed_orders`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **DEBUG**
- Потребители:
  - `tests/debug/test_date_variants.py::test_date_variants`
- Динамика: aggregateFields[0] = {field} parameter. filters.WaiterName.values[0] = {employee_name} parameter. Adds static OpenDate.OrderClose IncludeValues=['CLOSED'].
- Заметка: Debug variant restricting to CLOSED orders to test the check-count reconciliation hypothesis.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "WaiterName"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "{field}"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "WaiterName": {
      "filterType": "IncludeValues",
      "values": [
        "{employee_name}",
        "Артемий Новаев"
      ]
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OpenDate.OrderClose": {
      "filterType": "IncludeValues",
      "values": [
        "CLOSED"
      ]
    }
  }
}
```

### 22. Чеки официанта по дате закрытия (CloseDate.Typed)

- ID: `date_variants_close_date`
- Источник: `tests/debug/test_date_variants.py:222-247` — builder `test_close_date`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **DEBUG**
- Потребители: _внешних вызовов не найдено_
- Динамика: aggregateFields[0] = {field} parameter. filters.WaiterName.values[0] = {employee_name} parameter. Date range filter keyed on CloseDate.Typed (not OpenDate.Typed) — variant testing close-date semantics.
- Заметка: Debug variant filtering by CloseDate.Typed. Function test_close_date is defined but not invoked by test_date_variants (no caller in file).

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "WaiterName"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "{field}"
  ],
  "filters": {
    "CloseDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "WaiterName": {
      "filterType": "IncludeValues",
      "values": [
        "{employee_name}",
        "Артемий Новаев"
      ]
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

### 23. Чеки официанта по дням (OrderNum, группировка по дате)

- ID: `daily_checks_by_day`
- Источник: `tests/debug/test_daily_checks.py:15-40` — builder `main`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **DEBUG**
- Потребители:
  - `tests/debug/test_daily_checks.py::main`
- Динамика: filters.WaiterName.values[0] = {employee_name} variable (set to 'Новаев Артемий'). Dates are hardcoded literals '2026-01-01'..'2026-01-22'. Groups by WaiterName + OpenDate.Typed to break down check counts per day.
- Заметка: Ad-hoc debug to locate the day where a waiter's check count diverges from the iiko UI. Posts directly to {olap.api.base_url}/v2/reports/olap.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "WaiterName",
    "OpenDate.Typed"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "OrderNum"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "2026-01-01",
      "to": "2026-01-22"
    },
    "WaiterName": {
      "filterType": "IncludeValues",
      "values": [
        "{employee_name}",
        "Артемий Новаев"
      ]
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

---

## TEST — автотесты

### 24. Вайнштефан Хефе Вайсбир — максимальный набор полей продаж

- ID: `weihenstephan_all_fields`
- Источник: `tests/test_weihenstephan_data.py:34-81` — builder `test_all_fields`
- Endpoint: `/v2/reports/olap` · reportType: `SALES` · статус: **TEST**
- Потребители:
  - `tests/test_weihenstephan_data.py::test_all_fields`
- Динамика: filters.OpenDate.Typed.from = {date_from} (now - 30 days), .to = {date_to} (now), both computed via datetime.now() at runtime. All other fields/filters are static literals.
- Заметка: Probe of the full available aggregate field set for one bottled-beer position to inspect MarkUp/ProductCost. Posts directly to {olap.api.base_url}/v2/reports/olap and saves response to weihenstephan_full_data.json.

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "Store.Name",
    "DishName",
    "DishGroup.ThirdParent",
    "DishForeignName",
    "OpenDate.Typed",
    "DishId"
  ],
  "groupByColFields": [],
  "aggregateFields": [
    "UniqOrderId",
    "UniqOrderId.OrdersCount",
    "DishAmountInt",
    "DishDiscountSumInt",
    "DiscountSum",
    "ProductCostBase.ProductCost",
    "ProductCostBase.MarkUp",
    "DishSumInt"
  ],
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "{date_from}",
      "to": "{date_to}"
    },
    "DishGroup.TopParent": {
      "filterType": "IncludeValues",
      "values": [
        "Напитки Фасовка"
      ]
    },
    "DishName": {
      "filterType": "IncludeValues",
      "values": [
        "Вайнштефан Хефе Вайсбир, светлое, 0,500 бут."
      ]
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": [
        "NOT_DELETED"
      ]
    }
  }
}
```

---

## ETL — knowledge_graph (переиспользует builders)

`knowledge_graph/etl/sales_loader.py` **не** строит собственных OLAP-тел — он переиспользует
прод-builders из `core/olap_reports.py`:

- `get_draft_sales_by_waiter_report(...)` — `knowledge_graph/etl/sales_loader.py:69`
- `get_beer_sales_report(...)` — `knowledge_graph/etl/sales_loader.py:80`

Тела этих запросов см. в разделе PRODUCTION (builder `_build_olap_request`).

---

## Карта потребителей (builder -> вызовы)

Полная карта вызовов публичных методов `OlapReports` (включая отчёты на смежных endpoint'ах).

### `get_store_balances`
- `routes/stocks.py:244 — olap.get_store_balances() inside stocks route handler`
- `routes/stocks.py:433 — olap.get_store_balances()`
- `routes/stocks.py:623 — olap.get_store_balances()`
- `routes/stocks.py:963 — olap.get_store_balances()`
- `routes/stocks.py:1197 — balances = olap.get_store_balances() or []`
- `routes/expiration.py:204 — balances = olap.get_store_balances() or []`
- `scripts/check/verify_store_mapping.py:16 — balances = olap.get_store_balances()`
- `scripts/analysis/search_specific_beers.py:13 — balances = olap.get_store_balances()`
- `scripts/debug/debug_festhaus_124.py:30 — balances = olap.get_store_balances()`

### `get_nomenclature`
- `core/olap_reports.py:218 — self.get_nomenclature() inside get_products_in_group when nomenclature not passed`
- `extensions.py:220 — nomenclature = olap.get_nomenclature() (cached-nomenclature helper)`
- `scripts/check/verify_store_mapping.py:17 — nomenclature = olap.get_nomenclature()`
- `scripts/analysis/search_specific_beers.py:12 — nomenclature = olap.get_nomenclature()`
- `scripts/debug/debug_festhaus_124.py:29 — nomenclature = olap.get_nomenclature()`
- `scripts/debug/debug_categories.py:19 — nomenclature = olap.get_nomenclature()`
- `scripts/debug/debug_beer_products.py:18 — nomenclature = olap.get_nomenclature()`
- `tests/test_all_iiko_apis.py:36 — nomenclature = olap.get_nomenclature()`

### `get_beer_sales_report`
- `core/olap_reports.py:1950 — module __main__ test stub`
- `core/revenue_metrics.py:129 — report_data = olap.get_beer_sales_report(date_from, olap_date_to, bar_name) (fasovka/bottled revenue)`
- `routes/analysis.py:50 — report_data = olap.get_beer_sales_report(date_from, olap_date_to, bar_name)`
- `routes/analysis.py:314 — report_data = olap.get_beer_sales_report(date_from, olap_date_to, bar_name)`
- `knowledge_graph/etl/sales_loader.py:80 — bottles_data = self.olap.get_beer_sales_report(...)`
- `scripts/debug/debug_olap_data.py:26 — bottles_data = olap.get_beer_sales_report('2025-11-17','2025-11-24','Кременчугская')`
- `scripts/debug/debug_bars.py:10 — bottles = olap.get_beer_sales_report(...)`

### `get_draft_sales_report`
- `core/draft_analysis.py:506 — report_data = olap.get_draft_sales_report(date_from, date_to)`
- `routes/analysis.py:452 — report_data = olap.get_draft_sales_report(date_from, olap_date_to, bar_name)`
- `scripts/l4l_draft.py:23 — raw = olap.get_draft_sales_report(date_from, olap_date_to)`
- `scripts/debug/debug_order_ids.py:7 — draft_data = olap.get_draft_sales_report('2025-11-17','2025-11-24','Кременчугская')`
- `scripts/debug/debug_olap_data.py:11 — draft_data = olap.get_draft_sales_report(...)`
- `scripts/debug/debug_draft_festhaus.py:29 — report_data = olap.get_draft_sales_report(DATE_FROM, DATE_TO, BAR)`
- `scripts/debug/debug_beer_share_calculation.py:177 — data = olap.get_draft_sales_report('2025-09-01','2025-09-30',None)`
- `scripts/debug/debug_beer_share_calculation.py:192 — data = olap.get_draft_sales_report('2025-09-01','2025-09-30',None)`
- `scripts/debug/debug_bars.py:9 — draft = olap.get_draft_sales_report(...)`
- `utils/check_unmapped_dishes.py:32 — report_data = olap.get_draft_sales_report(date_from, date_to)`
- `utils/auto_add_new_dishes.py:81 — report_data = olap.get_draft_sales_report(date_from, date_to)`

### `get_draft_sales_by_waiter_report`
- `core/waiter_analysis.py:389 — report_data = olap.get_draft_sales_by_waiter_report(date_from, date_to)`
- `routes/employee.py:31 — report_data = olap.get_draft_sales_by_waiter_report(date_from, date_to, None)`
- `routes/employee.py:81 — executor.submit(olap.get_draft_sales_by_waiter_report, ...): 'draft'`
- `routes/employee.py:246 — executor.submit(olap.get_draft_sales_by_waiter_report, ...): 'draft'`
- `routes/employee.py:966 — executor.submit(olap.get_draft_sales_by_waiter_report, ...): 'draft'`
- `routes/analysis.py:812 — report_data = olap.get_draft_sales_by_waiter_report(date_from, olap_date_to, bar_name)`
- `knowledge_graph/etl/sales_loader.py:69 — draft_data = self.olap.get_draft_sales_by_waiter_report(...)`
- `scripts/analysis/calculate_real_consumption.py:25 — report_data = olap.get_draft_sales_by_waiter_report(date_from, date_to)`

### `get_kitchen_sales_report`
- `scripts/debug/debug_olap_data.py:40 — kitchen_data = olap.get_kitchen_sales_report('2025-11-17','2025-11-24','Кременчугская')`
- `scripts/debug/debug_bars.py:11 — kitchen = olap.get_kitchen_sales_report(...)`

### `get_all_sales_report`
- `routes/dashboard.py:56 — data = olap.get_all_sales_report(date_from, date_to_inclusive, bar_name)`
- `routes/dashboard.py:559 — all_sales_data = olap.get_all_sales_report(date_from, date_to_inclusive, bar_name)`
- `routes/dashboard.py:602 — data = olap.get_all_sales_report(date_from, date_to_inclusive, bar_name)`
- `routes/dashboard.py:747 — all_sales_data = olap.get_all_sales_report(date_from, date_to_inclusive, None) (all bars)`

### `get_explorer_sales`
- `core/explorer.py:75 — data = olap.get_explorer_sales(date_from, date_to_inclusive, bar_name)`

### `get_orders_count`
- _вызовов не найдено (потенциально мёртвый код)_

### `get_bottles_sales_by_waiter_report`
- `routes/employee.py:82 — executor.submit(olap.get_bottles_sales_by_waiter_report, ...): 'bottles'`
- `routes/employee.py:247 — executor.submit(olap.get_bottles_sales_by_waiter_report, ...): 'bottles'`
- `routes/employee.py:967 — executor.submit(olap.get_bottles_sales_by_waiter_report, ...): 'bottles'`

### `get_kitchen_sales_by_waiter_report`
- `routes/employee.py:83 — executor.submit(olap.get_kitchen_sales_by_waiter_report, ...): 'kitchen'`
- `routes/employee.py:248 — executor.submit(olap.get_kitchen_sales_by_waiter_report, ...): 'kitchen'`
- `routes/employee.py:968 — executor.submit(olap.get_kitchen_sales_by_waiter_report, ...): 'kitchen'`

### `get_cancelled_orders_by_waiter`
- `routes/employee.py:84 — executor.submit(olap.get_cancelled_orders_by_waiter, ...): 'cancelled'`
- `routes/employee.py:249 — executor.submit(olap.get_cancelled_orders_by_waiter, ...): 'cancelled'`
- `routes/employee.py:774 — future_cancelled = olap_executor.submit(olap.get_cancelled_orders_by_waiter, date_from, olap_date_to)`

### `get_employee_aggregated_metrics`
- `routes/employee.py:80 — executor.submit(olap.get_employee_aggregated_metrics, ...): 'aggregated'`
- `routes/employee.py:245 — executor.submit(olap.get_employee_aggregated_metrics, ...): 'aggregated'`
- `routes/employee.py:965 — executor.submit(olap.get_employee_aggregated_metrics, ...): 'aggregated'`

### `get_kpi_olap_data`
- `routes/employee.py:773 — future_kpi = olap_executor.submit(olap.get_kpi_olap_data, date_from, olap_date_to)`

### `get_employee_daily_revenue`
- _вызовов не найдено (потенциально мёртвый код)_

### `get_new_loyalty_cards_by_waiter`
- `routes/employee.py:85 — executor.submit(olap.get_new_loyalty_cards_by_waiter, ...): 'loyalty_cards'`
- `routes/employee.py:250 — executor.submit(olap.get_new_loyalty_cards_by_waiter, ...): 'loyalty_cards'`
- `routes/employee.py:775 — future_loyalty = olap_executor.submit(olap.get_new_loyalty_cards_by_waiter, date_from, olap_date_to)`

### `get_discount_names`
- `routes/analysis.py:888 — result = olap.get_discount_names(date_from_str, olap_date_to)`

### `get_discount_report`
- `routes/analysis.py:930 — report_data = olap.get_discount_report(date_from, olap_date_to, bar_name)`

### `get_rfm_report`
- `routes/analysis.py:1142 — report_data = olap.get_rfm_report(date_from, olap_date_to, bar_name)`

---

## Смежные iiko-отчёты (вне OLAP — для полноты)

Эти методы `OlapReports` обращаются к отчётным endpoint'ам iiko, но **не** являются OLAP-запросами
(`reportType`): они используют GET с query-параметрами, а не JSON-тело, поэтому полных копий тел тут нет.

- `get_store_balances` -> GET `/v2/reports/balance/stores` (JSON, остатки на складах)
- `get_store_operations_report` -> GET `/reports/storeOperations` (XML, складские операции)
- `get_product_expense_report` -> GET `/reports/productExpense` (расход продуктов; требует department GUID)
- `_get_nomenclature_via_xml` -> GET `/products` (XML, fallback к OLAP TRANSACTIONS)

---

## Changelog

- 2026-05-31 — Документ создан. Собраны 24 дословные копии OLAP-запросов из `core/olap_reports.py`,
  `core/explorer.py`, `scripts/import_export/export_draft_sales.py`, `tests/debug/`, `tests/`.
  Каждое тело перепроверено повторным чтением исходника (multi-agent workflow: discover + verify).
  Добавлена карта потребителей и список смежных не-OLAP отчётов.
