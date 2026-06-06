# Правила создания OLAP-отчётов (iiko API)

> Технический справочник проекта (Flask-аналитика на iiko OLAP). Описывает, как корректно собирать тело запроса к OLAP API iiko, какие поля/фильтры/даты использовать, и как это соотносится с кодом проекта. Каждое нетривиальное утверждение сопровождается ссылкой на исходный файл документации iiko (каталог `iiko-olap-docs/`). Где документация молчит — это указано явно.

## Что это

OLAP-отчёт iiko — это запрос к серверу iiko (iikoServer / iiko.biz), который строит сводную таблицу (pivot) по продажам, проводкам, доставкам или остаткам. Клиент указывает: тип отчёта, поля группировки по строкам и колонкам, агрегируемые метрики и фильтры (включая обязательный фильтр по дате). Сервер возвращает массив строк `data` и блок итогов `summary`.

Получить данные можно двумя путями (`iiko-olap-docs/formirovanie-olap-otcheta-v-api.md`, вступление, строки 5-9):

1. Преднастроенный отчёт — спроектировать и сохранить отчёт в классическом iikoOffice, затем выгрузить его конфигурацию через API по сохранённому ID.
2. Самостоятельное формирование — собрать тело запроса вручную по документации.

В обоих случаях рекомендуется использовать OLAP **v2** (`formirovanie-olap-otcheta-v-api.md`, строка 11). Проект использует исключительно путь 2 (ручная сборка тел), что соответствует рекомендации iiko о стабильности формата выдачи через прямой вызов `/v2/reports/olap` (сверка: `core/olap_reports.py`, преднастроенные отчёты не используются).

## Источники

Документы в каталоге `iiko-olap-docs/` (источник истины — локальные снапшоты доков iiko):

- `iiko-olap-docs/formirovanie-olap-otcheta-v-api.md` — главный гайд: проектирование отчёта в iikoOffice и перенос конфигурации в API v2, пример тела запроса и ответа.
- `iiko-olap-docs/olap-otchety-v2.md` — официальная спецификация OLAP API v2: метод полей (`/columns`), метод построения (`/olap`), типы полей, типы фильтров, форматы дат, структура ответа, ограничения.
- `iiko-olap-docs/olap-otchety-v1.md` — спецификация legacy OLAP v1 (GET, параметры в query-string), каталоги полей по продажам/проводкам/доставкам/контролю хранения.
- `iiko-olap-docs/primery-vyzova-olap-otchet-v2.md` — 7 готовых примеров вызова OLAP v2 (reportType=SALES) с телами запросов и ответами.
- `iiko-olap-docs/prednastroennye-olap-otchety-vv2.md` — работа с преднастроенными отчётами v2 (`/presets`, `/presets/{presetType}`, `/byPresetId/{presetId}`).
- `iiko-olap-docs/olap-otchety-po-dostavke.md` — OLAP по доставке через iiko.biz API (порт 9900): пресеты доставки и произвольные отчёты, reportType=DELIVERIES.
- `iiko-olap-docs/otchety-vv2.md` — отдельные v2-эндпоинты «Отчётов по балансам» (денежные балансы, остатки на складах, ЕГАИС 3 регистр). Это НЕ OLAP-конструктор.
- `iiko-olap-docs/otchety-v1.md` — преднастроенные GET-эндпоинты v1 (storeOperations, sales, productExpense и т.д.). НЕ OLAP-конструктор.
- `iiko-olap-docs/otchety-dostavka-v1.md` — пять преднастроенных delivery-эндпоинтов v1 с XML-ответами. НЕ OLAP-конструктор.

## Endpoints и версии (v1 vs v2)

Рекомендация iiko и практика проекта — использовать OLAP **v2** (`formirovanie-olap-otcheta-v-api.md`, строка 11).

### OLAP v2 (рекомендуется)

| Назначение | Метод и путь | Источник |
|---|---|---|
| Список полей отчёта | `GET https://host:port/resto/api/v2/reports/olap/columns?key={token}&reportType={SALES\|TRANSACTIONS\|DELIVERIES}` | `olap-otchety-v2.md:18-31` |
| Построение отчёта | `POST https://host:port/resto/api/v2/reports/olap?key={token}` | `olap-otchety-v2.md:135-176`; `formirovanie-olap-otcheta-v-api.md:99` |
| Список пресетов | `GET .../v2/reports/olap/presets` | `prednastroennye-olap-otchety-vv2.md:9-14` |
| Пресеты по типу | `GET .../v2/reports/olap/presets/{presetType}` | `prednastroennye-olap-otchety-vv2.md:16-21` |
| Отчёт по пресету | `GET .../v2/reports/olap/byPresetId/{presetId}` | `prednastroennye-olap-otchety-vv2.md:31-36` |

Content-Type для POST: `Application/json; charset=utf-8` (`olap-otchety-v2.md:142`). Минимальная версия iiko, упомянутая в спецификации v2: 4.1 (`olap-otchety-v2.md:135-176`).

### OLAP v1 (legacy)

`GET https://host:port/resto/api/reports/olap` — все параметры в query-string, JSON-тела нет (`olap-otchety-v1.md`, строки 6-11). Доступен с iiko 3.9.

Ключевые отличия имён параметров v1 от v2 (`olap-otchety-v1.md`, строки 15-23):

| v1 (query-параметр) | v2 (поле тела) |
|---|---|
| `report` | `reportType` |
| `groupRow` | `groupByRowFields` |
| `groupCol` | `groupByColFields` |
| `agr` | `aggregateFields` |
| `from` / `to` (формат `DD.MM.YYYY`) | фильтр `DateRange` с `periodType`/`from`/`to` |

В v1 явные `filterType` (IncludeValues/ExcludeValues/DateRange) НЕ описаны; единственный явный фильтр периода — `from`/`to` (`olap-otchety-v1.md`, строки 22-23). Документ v2 описывает только путь `/resto/api/v2/...` и прямого сравнения с v1 не содержит — версионные различия в нём привязаны к версиям iiko (4.1, 5.2, 5.3, 5.5, 9.1.2), а не к версии API (`olap-otchety-v2.md:18,139`).

### OLAP по доставке (iiko.biz, порт 9900)

Отдельный хост `https://iiko.biz:9900/api/0/olaps/` с авторизацией через `access_token` и `organizationId` (`olap-otchety-po-dostavke.md`, строки 10,28,65,71). Эндпоинты: `olapPresets`, `olapByPreset`, `olapColumns`, `olap`. Тело `olap` содержит `organizationId` и `olapSettings` (строка с экранированным JSON).

## Аутентификация

Токен (`key`) передаётся как query-параметр во всех вызовах OLAP v1/v2:

- v2: `POST .../v2/reports/olap?key={token}` (`formirovanie-olap-otcheta-v-api.md:99,104-106`).
- v1: `key` в query-string запроса (`olap-otchety-v1.md`, строка 31; пример `key=ec621550-afae-133e-80c8-76155db2b268`).
- byPresetId: `key` тоже query-параметр (`prednastroennye-olap-otchety-vv2.md`, строка 46).
- iiko.biz: вместо `key` используется `access_token` (`olap-otchety-po-dostavke.md`, строки 10,28).

Сам способ получения токена (метод авторизации iikoServer) в текстах OLAP-доков лишь упоминается ссылкой (`formirovanie-olap-otcheta-v-api.md`, строка 37) и в этих файлах детально не описан. В проекте получение и освобождение токена инкапсулировано в `core/olap_reports.py` (методы `connect()`/`disconnect()`, делегирующие в `IikoAPI`).

## Структура тела запроса

Тело POST `/v2/reports/olap` — JSON-объект со следующими ключами (`olap-otchety-v2.md:147-176`; `formirovanie-olap-otcheta-v-api.md:113-153`):

| Поле | Обязательность | Назначение |
|---|---|---|
| `reportType` | обязательно | Тип отчёта: `SALES` / `TRANSACTIONS` / `DELIVERIES` (`olap-otchety-v2.md:181-186`). |
| `buildSummary` | необязательно | Управляет расчётом итогов `summary` (true/false). Появился в iiko 5.3.4; до 9.1.2 дефолт `true`, с 9.1.2 — `false` (`olap-otchety-v2.md:187-191`). |
| `groupByRowFields` | обязательно (основная группировка) | Поля-измерения, по которым формируются строки отчёта. Только поля с `groupingAllowed=true` (`olap-otchety-v2.md:193-196`). |
| `groupByColFields` | необязательно | Поля группировки по колонкам. Может быть пустым массивом `[]`. Только поля с `groupingAllowed=true` (`olap-otchety-v2.md:197-201`; `formirovanie-olap-otcheta-v-api.md:127`). |
| `aggregateFields` | обязательно | Агрегируемые метрики (значения ячеек). Поля с `aggregationAllowed=true` (`olap-otchety-v2.md:202-206`). |
| `filters` | обязательно (минимум фильтр по дате) | Объект-карта `{ "FieldName": {фильтр}, ... }`. Только поля с `filteringAllowed=true` (`olap-otchety-v2.md:207-211`). |

Важно по `aggregateFields`: в тексте `olap-otchety-v2.md:202-206` для `aggregateFields` ошибочно указано условие `filteringAllowed=true`; по смыслу метода `/columns` для агрегации служит признак `aggregationAllowed=true`. При сомнениях ориентироваться на живой ответ `/columns`.

Шаблон тела (`olap-otchety-v2.md`, строки 147-176; `buildSummary` в оригинале записан строкой):

```json
{
  "reportType": "EnumValue",
  "buildSummary": "true",
  "groupByRowFields": [
    "groupByRowFieldName1",
    "groupByRowFieldName2"
  ],
  "groupByColFields": [
    "groupByColFieldName1"
  ],
  "aggregateFields": [
    "AggregateFieldName1",
    "AggregateFieldName2"
  ],
  "filters": {}
}
```

## reportType: значения

| reportType (v2) | Значение | Источник |
|---|---|---|
| `SALES` | По продажам | `olap-otchety-v2.md:181-186` |
| `TRANSACTIONS` | По транзакциям/проводкам | `olap-otchety-v2.md:181-186` |
| `DELIVERIES` | По доставкам | `olap-otchety-v2.md:181-186` |

В v1 добавляется четвёртое значение `STOCK` (контроль хранения) — параметр называется `report` (`olap-otchety-v1.md`, строка 17). В преднастроенных отчётах v2 `presetType` (нижний регистр) принимает `stock` / `sales` / `transactions` / `deliveries` (`prednastroennye-olap-otchety-vv2.md:23-27`).

Поля для разных типов описаны в отдельных статьях: поля по продажам — статья olap-sales; по проводкам — olap-transactions (`formirovanie-olap-otcheta-v-api.md`, строки 13,19). Конкретное строковое значение reportType для отчёта по проводкам в гайде `formirovanie-olap-otcheta-v-api.md` не приведено — оно дано в `olap-otchety-v2.md` (`TRANSACTIONS`).

В проекте задействованы только `SALES` (большинство запросов) и `TRANSACTIONS` (один запрос — номенклатура) (сверка: `core/olap_reports.py:102` TRANSACTIONS; `:614` и далее SALES). `DELIVERIES`/`STOCK` не используются (у заведения нет доставки).

## Поля: строки vs агрегаты, типы данных

Доступность поля для операций определяется флагами из ответа `/columns`: `groupingAllowed`, `aggregationAllowed`, `filteringAllowed` (`olap-otchety-v2.md:33-132`). Часть полей «mixed» — допускают и группировку, и агрегацию.

Типы данных полей (`olap-otchety-v2.md`, описание `type`; `olap-otchety-v1.md`, колонка Type):

- `ENUM` — перечислимые значения; `STRING` — строка; `ID` — внутренний идентификатор iiko (с 5.0); `DATETIME` — дата-время; `DATE` — округлённая дата (учётный день); `INTEGER` — целое; `PERCENT` — процент от 0 до 1; `DURATION_IN_SECONDS` — длительность; `AMOUNT` — количество; `MONEY` — денежная сумма; `OBJECT` — составной (напр. `TransactionType.Code`).

Таблица ключевых полей, встречающихся в доках и в проекте (kind: row=группировка строк, col=группировка колонок, agg=агрегат, filter=фильтр, row/filter=группировка и фильтр без агрегации, mixed=и группировка, и агрегат):

| Поле | kind | Тип | Описание | Источник |
|---|---|---|---|---|
| `OpenDate.Typed` | row/filter | DATE | Учётный день для SALES/DELIVERIES (4.2+); используется в группировке и в фильтре `DateRange`, агрегации нет. Старое имя в 4.1 — `OpenDate` | `olap-otchety-v1.md:256,255`; `olap-otchety-v2.md:362`; `formirovanie-olap-otcheta-v-api.md:117,132` |
| `OpenDate` | row/filter | STRING (DATE) | То же поле, что `OpenDate.Typed`, но имя/тип версии iiko 4.1 (4.2+ deprecated). В примерах v2 встречается как имя группировки и фильтра; в ответе формат `YYYY.MM.DD` | `olap-otchety-v1.md:255`; `primery-vyzova-olap-otchet-v2.md:16-19,59` |
| `OpenTime` | row/filter | DATETIME | Время открытия; в ответе `YYYY-MM-DDTHH:mm:ss` | `olap-otchety-v1.md:257`; `formirovanie-olap-otcheta-v-api.md:54,169` |
| `CloseTime` | row | DATETIME | Время закрытия; в ответе с миллисекундами | `formirovanie-olap-otcheta-v-api.md:55,163` |
| `DishName` | row | STRING | Название блюда | `formirovanie-olap-otcheta-v-api.md:56` |
| `DishCategory` | row | STRING | Категория блюда (в ответе может быть `null`) | `primery-vyzova-olap-otchet-v2.md:26198-26261` (значение `null` на L26204) |
| `SessionNum` | mixed | INTEGER | Номер смены/сессии; пример числового фильтра `Range` | `olap-otchety-v2.md:308-315` |
| `HourClose` | row | STRING | Час закрытия заказа (в ответе строкой) | `olap-otchety-v1.md:246`; `primery-vyzova-olap-otchet-v2.md:25650-25653` |
| `PayTypes` | row | STRING | Тип оплаты | `formirovanie-olap-otcheta-v-api.md:60` |
| `WaiterName` | row | STRING | Официант блюда | `olap-otchety-v1.md` fieldCatalog |
| `CashRegisterName` | mixed | STRING | Касса/станция; в одном примере вынесена в `groupByColFields` | `primery-vyzova-olap-otchet-v2.md:26290-26296` |
| `Delivery.IsDelivery` | col | ENUM | Признак доставки: `DELIVERY_ORDER` / `ORDER_WITHOUT_DELIVERY` | `olap-otchety-v1.md:213`; `olap-otchety-po-dostavke.md:18,53` |
| `DishSumInt` | agg | MONEY | Сумма по блюду без скидки. В ответе значение часто целое (особенность данных, не второй тип) | `olap-otchety-v1.md:241`; `formirovanie-olap-otcheta-v-api.md:64` |
| `DishDiscountSumInt` | agg | MONEY | Сумма со скидкой (в ответе бывает дробной, напр. 179786.5) | `primery-vyzova-olap-otchet-v2.md:72,121` |
| `GuestNum` | mixed | AMOUNT | Число гостей (в каталоге v1 grouping+aggregation; в примерах используется как агрегат) | `olap-otchety-v1.md:244`; `primery-vyzova-olap-otchet-v2.md:58` |
| `UniqOrderId` | agg | INTEGER | Количество уникальных чеков | `olap-otchety-v1.md:301`; `primery-vyzova-olap-otchet-v2.md:61` |
| `UniqOrderId.OrdersCount` | agg | AMOUNT | Количество заказов | `olap-otchety-v1.md:302` |
| `OrderNum` | mixed | INTEGER | Номер чека (порядковый, НЕ уникальный) | `olap-otchety-v1.md:264` |
| `DishAmountInt` | mixed | AMOUNT | Количество блюд | `olap-otchety-v1.md` fieldCatalog |
| `ProductCostBase.ProductCost` | agg | MONEY | Себестоимость | `olap-otchety-v1.md` fieldCatalog |
| `ProductCostBase.MarkUp` | agg | PERCENT | Наценка как доля (0..1; для наценки бывает >1) | `olap-otchety-v1.md` fieldCatalog |
| `PercentOfSummary.ByRow` / `.ByCol` | agg | PERCENT | % по строке / по столбцу; `groupingAllowed=false` | `olap-otchety-v2.md:98-132`; `olap-otchety-v1.md:150-151` |
| `StartBalance.Amount/.Money`, `FinalBalance.Amount/.Money` | agg | AMOUNT/MONEY | Остатки (тяжёлые — см. «Подводные камни») | `olap-otchety-v2.md:213`; `olap-otchety-v1.md:148-149` |

Для проводок (`TRANSACTIONS`): `Account.Name` (счёт, в т.ч. склад; `StartBalanceOptimizable=true` — `olap-otchety-v1.md:91`), `Product.Name`, `Amount` (`olap-otchety-v1.md:94`), `DateTime.Typed` (дата-время, `olap-otchety-v1.md:130`), `DateTime.DateTyped` (учётный день, 4.2+, `olap-otchety-v1.md:132`).

Внимание по типам PERCENT: значение — доля 0..1, а не целые проценты (`olap-otchety-v2.md`, тип PERCENT). Проект явно трактует `ProductCostBase.MarkUp` как десятичную долю и умножает на 100 для UI (сверка: `routes/dashboard.py:126-129`).

## Фильтры

`filters` — объект, где ключ это имя поля, а значение — объект с `filterType` (`olap-otchety-v2.md:207-211`). Три типа фильтров:

### 1. Фильтр по значению — IncludeValues / ExcludeValues

Применяется к полям типов ENUM и STRING (`olap-otchety-v2.md:218-264`). `IncludeValues` — оставить только перечисленные значения; `ExcludeValues` — исключить перечисленные.

```json
{
  "FieldName": {
    "filterType": "IncludeValues",
    "values": ["Value1", "Value2"]
  }
}
```

В `values` допустимы enum-коды (см. раздел «Базовые enum-коды»), текстовые значения поля и `null`.

Семантика `null` в `IncludeValues`: значение `null` отбирает строки, в которых соответствующее поле-измерение пусто (нет значения). В доке по доставке показан `DishName` с `values:[null,"4 сыра"]` (`olap-otchety-po-dostavke.md:18`) — в выборку попадут как позиции с названием «4 сыра», так и позиции, у которых `DishName` отсутствует. Это нетривиальный кейс для группировок, которые сами по себе дают `null` в измерении: чтобы оставить такие строки, `null` нужно явно перечислить в `values`; `ExcludeValues` с `null` наоборот их отсекает.

### 2. Фильтр по диапазону — Range

Применяется к числовым полям INTEGER, PERCENT, AMOUNT, MONEY (`olap-otchety-v2.md:267-315`).

```json
{
  "SessionNum": {
    "filterType": "Range",
    "from": 758,
    "to": 760,
    "includeHigh": true
  }
}
```

`includeLow` необязателен (по умолчанию `true`); `includeHigh` необязателен (по умолчанию `false`). В проекте Range-фильтр не применяется — не требуется (сверка: `core/olap_reports.py`, Range-фильтров нет).

### 3. Фильтр по дате — DateRange

Применяется к полям DATETIME и DATE (`olap-otchety-v2.md:318-360`).

```json
{
  "OpenDate.Typed": {
    "filterType": "DateRange",
    "periodType": "CUSTOM",
    "from": "2014-01-01T00:00:00.000",
    "to": "2014-01-03T00:00:00.000"
  }
}
```

`includeLow` по умолчанию `true`, `includeHigh` по умолчанию `false`. Включение верхней границы осмысленно только для полей с округлённой ДАТОЙ, а не ДАТА-ВРЕМЯ (`olap-otchety-v2.md:318-360`).

### periodType

Значения `periodType` в DateRange (`olap-otchety-v2.md:351-356`): `CUSTOM` (вручную через from/to), `OPEN_PERIOD`, `TODAY`, `YESTERDAY`, `CURRENT_WEEK`, `CURRENT_MONTH`, `CURRENT_YEAR`, `LAST_WEEK`, `LAST_MONTH`, `LAST_YEAR`. Для всех типов, кроме `CUSTOM`, параметры `from`/`to`/`includeLow`/`includeHigh` игнорируются, КРОМЕ `from` — его передача обязательна, значение может быть любым. В гайде `formirovanie-olap-otcheta-v-api.md` (строка 134) и во всех примерах `primery-vyzova-olap-otchet-v2.md` фигурирует только `CUSTOM`.

### Форматы дат в фильтрах

- Полный: `yyyy-MM-dd'T'HH:mm:ss.SSS`, напр. `2014-01-01T00:00:00.000` (`olap-otchety-v2.md:357-358`; `formirovanie-olap-otcheta-v-api.md:132-138`).
- Краткий (для округлённых полей-дат): `yyyy-MM-dd`, напр. `2018-09-04` (`olap-otchety-v2.md:367-372`).
- В iiko.biz OLAP по доставке — `YYYY-MM-DD` (`olap-otchety-po-dostavke.md:82-85`).

### Выбор поля для фильтра по дате (зависит от reportType)

`olap-otchety-v2.md:362`:

- `SALES`, `DELIVERIES` → `OpenDate.Typed` (в 4.1 — `OpenDate`).
- `TRANSACTIONS` → `DateTime.DateTyped` для фильтра по *дате* (в 4.1 — `DateTime.OperDayFilter`); `DateTime.Typed` — это дата-время.

### Стандартные предохранители

Для аналитики продаж принято исключать удалённые/сторнированные позиции двумя фильтрами (`primery-vyzova-olap-otchet-v2.md:33-40`; `formirovanie-olap-otcheta-v-api.md:139-150`):

```json
{
  "DeletedWithWriteoff": { "filterType": "IncludeValues", "values": ["NOT_DELETED"] },
  "OrderDeleted": { "filterType": "IncludeValues", "values": ["NOT_DELETED"] }
}
```

Эквивалентный приём для `DeletedWithWriteoff` — `ExcludeValues` с `["DELETED_WITH_WRITEOFF","DELETED_WITHOUT_WRITEOFF"]` (`primery-vyzova-olap-otchet-v2.md:33-40`). Для инвертированного отчёта (только удалённые позиции) предохранитель инвертируется — см. «Подводные камни».

## Базовые enum-коды

`values` в IncludeValues/ExcludeValues для полей типа ENUM принимают не произвольный текст, а фиксированные коды. В локальных каталогах эти коды не дублируются: каждое ENUM-поле в `olap-otchety-v1.md` ссылается на раздел общего справочника iiko «Расшифровки кодов базовых типов#<подраздел>» (напр. `olap-otchety-v1.md:211` — `DeletedWithWriteoff` → «Типы удаления блюд»; `:259` — `OrderDeleted` → «Признак удаления заказа»; `:213` — `Delivery.IsDelivery` → «Признак доставки»). Полные таблицы кодов в каталог `iiko-olap-docs/` не входят — их источник истины на портале iiko (статья «Расшифровки кодов базовых типов»).

Коды, реально встречающиеся в примерах доков и в коде проекта (минимальный набор для сборки `values`):

| Поле | Тип | Коды (из примеров) | Источник |
|---|---|---|---|
| `DeletedWithWriteoff` | ENUM | `NOT_DELETED`, `DELETED_WITH_WRITEOFF`, `DELETED_WITHOUT_WRITEOFF` | `primery-vyzova-olap-otchet-v2.md:33-40`; `formirovanie-olap-otcheta-v-api.md:139-150`; `olap-otchety-v1.md:211` |
| `OrderDeleted` | ENUM | `NOT_DELETED` (и парный признак удаления заказа) | `formirovanie-olap-otcheta-v-api.md:139-150`; `olap-otchety-v1.md:259` |
| `Delivery.IsDelivery` | ENUM | `DELIVERY_ORDER`, `ORDER_WITHOUT_DELIVERY` | `olap-otchety-po-dostavke.md:53`; `olap-otchety-v1.md:213` |
| `Delivery.ServiceType` | ENUM | `PICKUP`, `COURIER` | `olap-otchety-v1.md:69` |

Для остальных ENUM-полей (типы счетов, операций, документов, статей ДДС и т.д.) точные коды смотреть в живом ответе `/v2/reports/olap/columns` (колонка значений) либо в портальной статье «Расшифровки кодов базовых типов» — в локальных файлах присутствуют только ссылки-якоря, а не сами таблицы.

## Даты и их семантика

- Граница `to` в DateRange трактуется как **исключающая** для полей ДАТА-ВРЕМЯ (`includeHigh=false` по умолчанию). В примере `from=2014-01-01`, `to=2014-01-03` в ответ попадают только 01 и 02 января — 03-е исключено (`primery-vyzova-olap-otchet-v2.md:59,67`).
- В `/byPresetId` период задаётся отдельными query-параметрами `dateFrom` (граница ВКЛЮЧЕНА) и `dateTo` (граница НЕ включена; полуоткрытый интервал `[dateFrom, dateTo)`) (`prednastroennye-olap-otchety-vv2.md`, строки 44-45). Формат заявлен как `YYYY-MM-DDThh:mm:ss`, но в примере используется краткий `YYYY-MM-DD` (`prednastroennye-olap-otchety-vv2.md`, строка 59).
- Формат дат в ОТВЕТЕ отличается от запроса: `OpenDate` возвращается как `YYYY.MM.DD` с точками (`primery-vyzova-olap-otchet-v2.md:59`); `OpenDate.Typed` — как `YYYY-MM-DD`; `OpenTime`/`CloseTime` — `YYYY-MM-DDTHH:mm:ss(.SSS)` (`formirovanie-olap-otcheta-v-api.md:163-172`).
- В v1 период — это `from`/`to` в формате `DD.MM.YYYY` напрямую в query-string; конструкции DateRange/periodType отсутствуют (`olap-otchety-v1.md`, строки 22-23).

Правило проекта: поскольку UI-период включительный, а OLAP `to` исключающая, перед вызовом OLAP к `date_to` добавляется `+1 день` (сверка: `routes/dashboard.py:36`; `routes/analysis.py:41-42,301-302,442-444`; `routes/employee.py:67-69,234-235`). Это единое осознанное правило (комментарии «OLAP exclusive → +1 день»). Сами builders в `core/olap_reports.py` не задают `includeLow`/`includeHigh`, полагаясь на дефолты (`includeLow=true`, `includeHigh=false`), что согласуется с доками.

## Преднастроенные отчёты

Механизм описан в `prednastroennye-olap-otchety-vv2.md` (доступно с iiko 4.2):

1. `GET .../v2/reports/olap/presets` — список всех неудалённых конфигураций (массив объектов).
2. `GET .../v2/reports/olap/presets/{presetType}` — фильтр списка по типу (`stock`/`sales`/`transactions`/`deliveries`) (`prednastroennye-olap-otchety-vv2.md:23-27`).
3. `GET .../v2/reports/olap/byPresetId/{presetId}?key=...&dateFrom=...&dateTo=...&summary=...` — построение отчёта по UUID пресета (`prednastroennye-olap-otchety-vv2.md:31-46`). Реальный пример вызова: `.../byPresetId/c80230c5-5d47-41d2-a055-367742db889d?key=...&dateFrom=2025-01-01&dateTo=2025-01-31` (`prednastroennye-olap-otchety-vv2.md:59`); тело его ответа в гайде дано плейсхолдером `%%CH%PRE1%%` (`formirovanie-olap-otcheta-v-api.md:87-92`).

Каждый объект конфигурации содержит: `id` (UUID), `name`, `reportType`, `groupByRowFields`, `groupByColFields`, `aggregateFields`, `filters` (`prednastroennye-olap-otchety-vv2.md:67-95`). Преднастроенный отчёт также может содержать `buildSummary` (в примерах `null`) (`formirovanie-olap-otcheta-v-api.md:49`).

Пример элемента ответа метода списка пресетов (`GET /v2/reports/olap/presets`) — конфигурация одного сохранённого отчёта (с `id`/`name`/`buildSummary`), а НЕ результат построения через `byPresetId`. В доке этот фрагмент озаглавлен «Ответ метода для рассматриваемого примера» и обрамлён как элемент массива (`formirovanie-olap-otcheta-v-api.md:45,81`):

```json
{
  "id": "e45124ec-6455-4a1f-ba59-9aa3efe05f30",
  "name": "Отчет по проданным блюдам в смену",
  "buildSummary": null,
  "reportType": "SALES",
  "groupByRowFields": [
    "OpenDate.Typed", "SessionNum", "OpenTime", "CloseTime",
    "DishName", "OrderType", "Delivery.CustomerName",
    "Delivery.CustomerPhone", "PayTypes"
  ],
  "groupByColFields": [],
  "aggregateFields": ["DishSumInt"],
  "filters": {
    "DeletedWithWriteoff": { "filterType": "IncludeValues", "values": ["NOT_DELETED"] },
    "OrderDeleted": { "filterType": "IncludeValues", "values": ["NOT_DELETED"] }
  }
}
```

(дословно, `formirovanie-olap-otcheta-v-api.md`, строки 46-80).

Рекомендация iiko: формат сохранённых конфигураций может меняться при обновлении iiko (`prednastroennye-olap-otchety-vv2.md`, строка 48), поэтому для стабильности выдачи конфигурацию из `/presets` следует подавать в `/v2/reports/olap` вместо `byPresetId` (`prednastroennye-olap-otchety-vv2.md`, строка 50). Проект следует этой рекомендации опосредованно — пресеты не используются вовсе, все тела собираются вручную (сверка: в `core/olap_reports.py` нет вызовов `/presets`, `/byPresetId`).

В iiko.biz пресеты доставки создаются вручную в iikoOffice (раздел «Доставка → Отчеты по доставкам»), список берётся через `GET olapPresets`, выполнение — `POST olapByPreset` с телом `{dateFrom, dateTo, presetId}` в формате `YYYY-MM-DD` (`olap-otchety-po-dostavke.md`, строки 5,8-37).

## Доставка

Для доставки есть три различных подхода в доках:

1. OLAP-конструктор с `reportType=DELIVERIES` через iiko.biz `/api/0/olaps/olap` или v2 `/v2/reports/olap` — поля доставки (`Delivery.IsDelivery` со значениями `DELIVERY_ORDER`/`ORDER_WITHOUT_DELIVERY`, `Delivery.CustomerName`, `Delivery.CustomerPhone`, `Delivery.Email`, `Delivery.ServiceType`=`PICKUP`/`COURIER`) (`olap-otchety-po-dostavke.md:18,53`; `olap-otchety-v1.md:56,61,65,69,213`).
2. Преднастроенные delivery-эндпоинты v1 `resto/api/reports/delivery/*` (`consolidated`, `couriers`, `orderCycle`, `halfHourDetailed`, `regions`, `loyalty`) — GET с фиксированным набором метрик, ответ в XML, состав строк/колонок не настраивается (`otchety-dostavka-v1.md`). Это НЕ OLAP-конструктор.
3. Отдельные delivery-метрики (целевые показатели `target*`, `metricType`=AVERAGE/MINIMUM/MAXIMUM для `/loyalty`).

Поля-длительности доставки имеют тип `INTEGER`/`AMOUNT` и измеряются В МИНУТАХ (а не в секундах, как `DURATION_IN_SECONDS`): `Delivery.WayDuration` («Время в пути(мин)», `olap-otchety-v1.md:72`), `Delivery.Delay` («Опоздание доставки(мин)», `:57`), `Delivery.DelayAvg`/`Delivery.WayDurationAvg` (средние, AMOUNT, `:58,73`). Поля типа `DURATION_IN_SECONDS`/`INTEGER` для длительностей приготовления выражены в секундах (напр. `Delivery.CookingToSendDuration`, `:48`). При интерпретации значения важно сверяться с подписью поля в `/columns` (единица измерения вынесена в название), а не предполагать секунды/минуты по типу.

Проект доставку не использует (у заведения её нет) — `DELIVERIES` среди запросов отсутствует (сверка: `core/olap_reports.py`, reportType только SALES/TRANSACTIONS).

## Структура ответа

Ответ метода построения OLAP — объект с двумя массивами (`olap-otchety-v2.md:401-475`; `formirovanie-olap-otcheta-v-api.md:159-297`):

- `data` — массив объектов; одна запись = одна строка грида iikoOffice; ключи объекта = запрошенные `groupByRowFields` + `aggregateFields`.
- `summary` — список блоков, каждый из ДВУХ объектов: [1] поля группировки промежуточного итога (пустой `{}` = общий итог по всему отчёту), [2] значения агрегатов (число ключей фиксировано = числу `aggregateFields`).

Особенности:

- Отсутствующие значения измерений возвращаются как `null` (напр. `OrderType: null`, `DishCategory: null`) (`formirovanie-olap-otcheta-v-api.md:159-297`; `primery-vyzova-olap-otchet-v2.md:26204`).
- Агрегаты — числа: счётчики целые (`GuestNum: 179`, `UniqOrderId: 189`), денежные могут быть дробными (`DishDiscountSumInt: 179786.5`) (`primery-vyzova-olap-otchet-v2.md:72-77`).
- При `buildSummary=false` блок `summary` пустой `[]` (с iiko 5.3) (`olap-otchety-v2.md:475`).

Пример фрагмента `data`:

```json
{
  "data": [
    {
      "CloseTime": "2025-03-18T12:05:24.618",
      "Delivery.CustomerName": "Пупкин Василий",
      "Delivery.CustomerPhone": "+79785160513",
      "DishName": "Лимонад",
      "DishSumInt": 176,
      "OpenDate.Typed": "2025-03-18",
      "OpenTime": "2025-03-18T11:36:48",
      "OrderType": null,
      "PayTypes": "Наличные",
      "SessionNum": 17
    }
  ],
  "summary": []
}
```

(сокращённый фрагмент, `formirovanie-olap-otcheta-v-api.md`, строки 159-297).

Пример НЕпустого `summary` (когда `buildSummary` включён): каждый элемент — пара `[ {поля группировки}, {агрегаты} ]`; элемент с пустым `{}` в первой позиции — общий итог по всему отчёту (`primery-vyzova-olap-otchet-v2.md:104-126`):

```json
{
  "summary": [
    [
      { "PayTypes": "(без оплаты)" },
      { "DishDiscountSumInt": 0, "DishSumInt": 3435, "GuestNum": 5, "UniqOrderId": 5 }
    ],
    [
      {},
      { "DishDiscountSumInt": 465839.5, "DishSumInt": 491035, "GuestNum": 457, "UniqOrderId": 482 }
    ],
    [
      { "OpenDate": "2014.01.02", "PayTypes": "(без оплаты)" },
      { "DishDiscountSumInt": 0, "DishSumInt": 1835, "GuestNum": 3, "UniqOrderId": 3 }
    ]
  ]
}
```

(дословный фрагмент, `primery-vyzova-olap-otchet-v2.md`, строки 104-150). Промежуточные итоги формируются по всем комбинациям группировок: видно блок только по `PayTypes`, блок общего итога `{}` и блоки по паре `OpenDate`+`PayTypes`.

Ответ метода `/columns` — JSON-объект, где ключ = `FieldName`, значение содержит `name` (человекочитаемое), `type`, `aggregationAllowed`, `groupingAllowed`, `filteringAllowed`, `tags` (`olap-otchety-v2.md:33-132`):

```json
{
  "Delivery.Email": {
    "name": "e-mail доставки",
    "type": "STRING",
    "aggregationAllowed": false,
    "groupingAllowed": true,
    "filteringAllowed": true,
    "tags": ["Доставка", "Клиент доставки"]
  }
}
```

(дословно, `olap-otchety-v2.md`, строки 98-132).

В iiko.biz ответ `olapByPreset`/`olap` содержит `data` и `summary` как СТРОКИ с экранированным JSON, плюс `organizationId` (`olap-otchety-po-dostavke.md:51-57`).

## Ошибки и коды ответа

В локальных OLAP-доках полная таблица кодов ошибок OLAP-метода не приведена (документация молчит) — описан только успешный путь с кодом 200. Практические правила обработки, выведенные из контракта и кода проекта:

- Успех — HTTP 200 с JSON-телом `{data, summary}`. Любой иной статус-код проект трактует как ошибку: не парсит тело, логирует `status_code` и первые 200 символов ответа, возвращает `None` (сверка: `core/olap_reports.py:57-65,133-157,1369+`).
- Отсутствие обязательного фильтра по дате: с iiko 5.5 фильтр по дате ОБЯЗАТЕЛЕН (`olap-otchety-v2.md:362`); запрос без него на свежих версиях завершится ошибкой, а не пустым отчётом.
- Невалидное имя поля / поле без нужного флага (`groupingAllowed`/`aggregationAllowed`/`filteringAllowed`): сервер отклонит запрос. Перед сборкой тела имена и флаги следует брать из живого `/columns`.
- Истёкший/неверный токен и сетевые таймауты: проект задаёт `timeout` на запросах (60-100 с) и оборачивает вызовы в try/except, при сбое возвращая `None` (сверка: `core/olap_reports.py:54-69,126-161,170-...`). Токен освобождается через `disconnect()`.

## Лимиты и производительность

- Самые тяжёлые поля — остатки `StartBalance.*`/`FinalBalance.*` (см. «Подводные камни»): без оптимизации суммируется вся таблица проводок за всё время (`olap-otchety-v2.md:213`; `olap-otchety-v1.md:78`).
- Общая нагрузка OLAP растёт с числом группировок и шириной периода: каждая дополнительная строка `groupByRowFields` увеличивает кардинальность грида. Локальные доки явных числовых лимитов на размер ответа или число строк не задают (документация молчит), и пагинации у `/v2/reports/olap` нет — отчёт возвращается одним JSON целиком.
- Практическое правило для многолетних выгрузок: дробить большой период на части (помесячно/поквартально) и при необходимости агрегировать на стороне клиента, чтобы не упереться в таймаут сервера и не держать гигантский ответ в памяти. Проект для остатков обходит проблему отдельным быстрым balance-API вместо OLAP (`core/olap_reports.py:48-52`), а OLAP-выгрузки продаж ограничивает выбранным в UI периодом.

## Пошаговый чек-лист создания отчёта

1. Выбрать `reportType`: `SALES` / `TRANSACTIONS` / `DELIVERIES` (`olap-otchety-v2.md:181-186`).
2. Получить список доступных полей: `GET /v2/reports/olap/columns?key=...&reportType=...` (`olap-otchety-v2.md:18-31`). Использовать имена `FieldName` из ответа.
3. Сформировать `groupByRowFields` — только поля с `groupingAllowed=true` (`olap-otchety-v2.md:193-196`).
4. При необходимости задать `groupByColFields` (поля с `groupingAllowed=true`) либо оставить `[]` (`olap-otchety-v2.md:197-201`).
5. Сформировать `aggregateFields` — только поля с `aggregationAllowed=true` (`olap-otchety-v2.md:202-206`).
6. Добавить обязательный фильтр по дате `DateRange` на правильное поле даты: `OpenDate.Typed` для SALES/DELIVERIES, `DateTime.DateTyped` для TRANSACTIONS (`olap-otchety-v2.md:362`). Начиная с iiko 5.5 фильтр по дате ОБЯЗАТЕЛЕН (`olap-otchety-v2.md:362`).
7. Для аналитики продаж добавить предохранители `DeletedWithWriteoff` и `OrderDeleted` = `IncludeValues ["NOT_DELETED"]` (`primery-vyzova-olap-otchet-v2.md:33-40`).
8. Учесть исключающую верхнюю границу `to`: если UI-период включительный, к `date_to` прибавить +1 день (правило проекта; согласуется с `olap-otchety-v2.md:318-360`).
9. Отправить `POST /v2/reports/olap?key={token}` с заголовком `Content-Type: Application/json; charset=utf-8` как в доке (`olap-otchety-v2.md:142`). Часть `charset=utf-8` необязательна — проект шлёт `application/json` (`core/olap_reports.py:129`).
10. Разобрать ответ: читать `data` (строки), при необходимости `summary` (итоги); учитывать `null` в измерениях и формат дат в ответе (`YYYY.MM.DD` для `OpenDate`) (`olap-otchety-v2.md:401-475`).

## Подводные камни и правила проекта

На основе сверки кода с документацией:

- `OrderNum` — это номер чека (порядковый, НЕ глобально уникальный, может повторяться между сменами/днями), а не счётчик заказов; для подсчёта количества чеков предназначен `UniqOrderId` / `UniqOrderId.OrdersCount` (`olap-otchety-v1.md:264,301,302`). **Расхождение в проекте**: прод-путь отмен агрегирует `OrderNum` и суммирует как «количество удалённых чеков» (сверка: `core/olap_reports.py:1177`; `routes/employee.py:795`). Методологически для подсчёта числа отмен корректнее `UniqOrderId.OrdersCount`. В других местах проект `UniqOrderId.OrdersCount` применяет правильно (`core/olap_reports.py:836-837,902,957,1346`).
- Поля остатков (`StartBalance.Amount/.Money`, `FinalBalance.Amount/.Money`) считаются по ВСЕЙ таблице проводок за всё время — запрос очень медленный и нагружает сервер (`olap-otchety-v2.md:213`). Рекомендации iiko: оставлять минимум группировок и вызывать редко, в нерабочее время; с iiko 5.2 для остатков использовать отдельный быстрый API «Отчёты по балансам» (`/v2/reports/balance/*`); с 5.5 OLAP-остатки оптимизированы через таблицы `ATransactionSum`/`ATransactionBalance` только при группировках/фильтрах по `StartBalanceOptimizable`-полям; оптимизирован `Account.Name`, но НЕ `Store`.
  - Про набор группировок есть внутренняя нестыковка самих доков. `olap-otchety-v2.md:213` и каталог проводок `olap-otchety-v1.md:78` рекомендуют оставлять «как правило, `Account.Name` и `Product.Name`», и именно `Account.Name` помечен `StartBalanceOptimizable=true` (`olap-otchety-v1.md:91`). А `prednastroennye-olap-otchety-vv2.md:52` ту же рекомендацию формулирует через «`Store` и `Product.Name`». Это дефект текста пресет-доки, а не контракт: `Store` НЕ является оптимизируемым полем (`olap-otchety-v1.md:78` прямо предупреждает брать склад из `Account.Name`, а не `Store`). Для остатков группировать по `Account.Name`.
  - **Проект следует**: использует `/v2/reports/balance/stores` с `timestamp` вместо OLAP-остатков (сверка: `core/olap_reports.py:48-52`).
- `buildSummary` в шаблоне доки передаётся СТРОКОЙ `"true"` (`olap-otchety-v2.md:147-176`); проект тоже передаёт строкой `"false"` в двух KPI-запросах (`core/olap_reports.py:1342,1356`), в остальных полагается на серверный дефолт и `summary` не парсит (читает только `data`). Поскольку проект не читает `summary`, переключение дефолта `buildSummary` на iiko 9.1.2 (`true`→`false`) поведенчески безопасно: блок `data` от `buildSummary` не зависит (`olap-otchety-v2.md:401-475`), а пустой `summary` при `false` (`:475`) проект всё равно игнорирует.
- Расширение за рамки локального каталога доков: проект использует под-поля `UniqOrderId.OrdersCount`, `UniqOrderId.Id`, а также `DishGroup.SecondParent`/`ThirdParent`, `AuthUser`, `ProductCostBase.OneItem`, которых нет в локальных каталогах. Это валидно по принципу «при расхождении побеждают живые `/v2/reports/olap/columns`» (правило реестра, `docs/technical/OLAP_REPORTS_COLLECTION.md:43`), но формально выходит за документированный набор.
- Артефакты экспорта в доках: в `primery-vyzova-olap-otchet-v2.md` встречается битый ключ `"PayType 351 s"` и одиночная строка `'0'` — это дефекты документа, а не контракт API (`primery-vyzova-olap-otchet-v2.md:26860,26928`). В `otchety-dostavka-v1.md` ответы помечены как `json`, но фактически XML; есть незакрытые теги и одинаковые заголовки разделов (`otchety-dostavka-v1.md:152,365,277,323`).
- В v1 ряд полей deprecated и заменён типизированными аналогами: `DateTime`→`DateTime.Typed`, `OpenDate`→`OpenDate.Typed` (4.2), `TableNumInt`→`TableNum` (5.1) и др. (`olap-otchety-v1.md`, строки 129-132,255-256).

## Примеры запросов

### Пример 1. Тело POST `/v2/reports/olap` (SALES, продажи блюд за период)

```json
{
    "reportType": "SALES",
    "groupByRowFields": [
            "OpenDate.Typed",
            "SessionNum",
            "OpenTime",
            "CloseTime",
            "DishName",
            "OrderType",
            "Delivery.CustomerName",
            "Delivery.CustomerPhone",
            "PayTypes"
    ],
    "groupByColFields": [],
    "aggregateFields": [
        "DishSumInt"
    ],
    "filters": {
        "OpenDate.Typed": {
            "filterType": "DateRange",
            "periodType": "CUSTOM",
            "from": "2025-03-01T00:00:00.000",
            "to": "2025-03-31T00:00:00.000"
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

(дословно, `formirovanie-olap-otcheta-v-api.md`, строки 113-153).

### Пример 2. Выручка по типам оплат (ExcludeValues + IncludeValues)

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "PayTypes",
    "OpenDate"
  ],
  "aggregateFields": [
    "GuestNum",
    "DishSumInt",
    "DishDiscountSumInt",
    "UniqOrderId"
  ],
  "filters": {
    "OpenDate": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "2014-01-01T00:00:00.000",
      "to": "2014-01-03T00:00:00.000"
    },
    "DeletedWithWriteoff": {
      "filterType": "ExcludeValues",
      "values": ["DELETED_WITH_WRITEOFF","DELETED_WITHOUT_WRITEOFF"]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": ["NOT_DELETED"]
    }
  }
}
```

(дословно, `primery-vyzova-olap-otchet-v2.md`, L7-42).

### Пример 3. Выручка станций по дням (единственный пример с groupByColFields)

```json
{
  "reportType": "SALES",
  "groupByRowFields": [
    "PayTypes",
    "OpenDate"
  ],
  "groupByColFields": [
    "CashRegisterName"
  ],
  "aggregateFields": [
    "DishSumInt",
    "DishDiscountSumInt"
  ],
  "filters": {
    "OpenDate": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "2014-01-01T00:00:00.000",
      "to": "2014-01-03T00:00:00.000"
    },
    "DeletedWithWriteoff": {
      "filterType": "IncludeValues",
      "values": ["NOT_DELETED"]
    },
    "OrderDeleted": {
      "filterType": "IncludeValues",
      "values": ["NOT_DELETED"]
    }
  }
}
```

(дословно, `primery-vyzova-olap-otchet-v2.md`, L26280-26317).

### Пример 4. Фильтр по дате и времени (комбинация краткого и полного формата)

```json
{
  "filters": {
    "OpenDate.Typed": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "2018-09-04",
      "to": "2018-09-04",
      "includeLow": true,
      "includeHigh": true
    },
    "OpenTime": {
      "filterType": "DateRange",
      "periodType": "CUSTOM",
      "from": "2018-09-04T01:00:00.000",
      "to": "2018-09-04T23:00:00.000",
      "includeLow": true,
      "includeHigh": true
    }
  }
}
```

(дословно, `olap-otchety-v2.md`, L379-398; в оригинале блок помечен `xml`, но содержимое — JSON).

### Пример 5. OLAP v1 — отчёт по продажам (GET, query-string)

```
https://localhost:8080/resto/api/reports/olap?key=ec621550-afae-133e-80c8-76155db2b268&report=SALES&from=01.12.2014&to=18.12.2014&groupRow=WaiterName&groupRow=OpenTime&agr=fullSum&agr=OrderNum
```

(дословно, `olap-otchety-v1.md`, строка 31). Многозначные поля повторяются в URL; период в формате `DD.MM.YYYY`; JSON-тела нет.

### Пример 6. iiko.biz — произвольный отчёт `olap` (olapSettings как экранированная строка)

```json
{
  "organizationId": "f20594c6-2da7-11e8-80e0-d8d38565926f",
  "olapSettings": "{\"reportType\": \"SALES\",\"groupByRowFields\": [\"Department\",\"OpenDate\"],\"aggregateFields\": [\"DishDiscountSumInt\",\"DishSumInt\"],\"filters\": {\"OpenDate.Typed\": { \"filterType\": \"DateRange\", \"periodType\": \"CUSTOM\", \"from\": \"2018-01-01\", \"to\": \"2018-08-17\" }}}"
}
```

(дословно, `olap-otchety-po-dostavke.md`, строки 78-88). Внутренний JSON `olapSettings` экранирован и передаётся как строка.

## Соответствие в проекте

Реализация OLAP-запросов сосредоточена в `core/olap_reports.py` (класс `OlapReports`). Карта-инвентарь всех тел запросов — `docs/technical/OLAP_REPORTS_COLLECTION.md` (24 OLAP-запроса, дословные копии JSON-тел; PRODUCTION — 16, DIAGNOSTIC — 1, AD-HOC — 1, DEBUG — 5, TEST — 1).

Ключевые соответствия (статусы из сверки):

| Правило доков | Статус | Якорь в коде |
|---|---|---|
| Тело содержит reportType/groupByRowFields/groupByColFields/aggregateFields/filters; `groupByColFields=[]` допустимо | follows | `core/olap_reports.py:101-121,613-653,756-793,831-865` |
| `reportType` обязателен, SALES/TRANSACTIONS/DELIVERIES | follows (используются SALES, TRANSACTIONS) | `core/olap_reports.py:102,614,…` |
| SALES фильтруется/группируется по `OpenDate.Typed`; TRANSACTIONS — по `DateTime.DateTyped` | follows | `core/olap_reports.py:114,634,704,777,…` |
| `DateRange.to` исключающая → компенсация +1 день в слое routes | follows | `routes/dashboard.py:36`; `routes/analysis.py:41-42`; `routes/employee.py:67-69` |
| Предохранители `DeletedWithWriteoff`/`OrderDeleted` = NOT_DELETED | follows (инверсия в отчёте об отменах — осознанно) | `core/olap_reports.py:644-651,710-717,…,1187-1190` |
| Фильтр по значению (Include/Exclude) для ENUM/STRING | follows | `core/olap_reports.py:640-643,657-660,852-855,1187-1190` |
| Остатки брать через быстрый balance-API, а не OLAP | follows | `core/olap_reports.py:48-52` |
| `ProductCostBase.MarkUp` — доля 0..1 | follows | `routes/dashboard.py:126-129`; `core/abc_analysis.py:47,60,63` |
| `OrderNum` не уникальный идентификатор; для счёта чеков `UniqOrderId.OrdersCount` | diverges (отмены агрегируют OrderNum) | `core/olap_reports.py:1177`; `routes/employee.py:795` |
| `buildSummary` (строкой) для отключения итогов | extends (применён в 2 KPI-запросах) | `core/olap_reports.py:1342,1356` |
| Под-поля `UniqOrderId.OrdersCount`/`.Id` (нет в локальных каталогах) | extends («побеждают живые columns») | `core/olap_reports.py:836-837,764` |
| Преднастроенные отчёты (presets/byPresetId) | not-used (все тела вручную) | `core/olap_reports.py` (нет вызовов presets) |

## Changelog

### 2026-05-31 — создание справочника

- Создан единый справочник «Правила создания OLAP-отчётов (iiko API)» на основе девяти документов из `iiko-olap-docs/` и сверки с кодом проекта.
- Что: сведены endpoints v1/v2, структура тела запроса, типы полей и фильтров, базовые enum-коды, семантика дат, преднастроенные отчёты, структура ответа (с примером непустого summary), ошибки и коды ответа, лимиты и производительность, чек-лист, подводные камни и соответствие коду.
- Почему: централизовать правила построения OLAP-запросов и зафиксировать расхождения проекта с документацией (в частности, агрегацию `OrderNum` в отчёте об отменах).
- Исправления по итогам ревью: переатрибутирован пример конфигурации (это ответ метода списка `/presets`, не `byPresetId`); разведена нестыковка `Account.Name` vs `Store` в рекомендации по остаткам (presets:52 — дефект доки); `OpenDate`/`OpenDate.Typed` помечены как row/filter и связаны как имена 4.1/4.2+ одного поля; тип `DishSumInt` зафиксирован как MONEY; ссылка `DishCategory=null` уточнена (L26204); добавлены разделы про enum-коды, ошибки/коды ответа, лимиты, единицы измерения полей доставки и семантику `null` в IncludeValues.
- Источники: `iiko-olap-docs/*.md`; сверка с `core/olap_reports.py`, `routes/dashboard.py`, `routes/analysis.py`, `routes/employee.py`, `docs/technical/OLAP_REPORTS_COLLECTION.md`.