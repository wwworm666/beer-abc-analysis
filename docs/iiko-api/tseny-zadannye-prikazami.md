* [API цен, заданных приказами](/articles/api-documentations/tseny-zadannye-prikazami/a/h2__715125863)
* [ProductPriceDto](/articles/api-documentations/tseny-zadannye-prikazami/a/v2.APIцен,заданныхприказами-ProductPriceDto)
* [ProductPriceItemDto](/articles/api-documentations/tseny-zadannye-prikazami/a/v2.APIцен,заданныхприказами-ProductPriceItemDto)
* [IncludeForCategoryDto](/articles/api-documentations/tseny-zadannye-prikazami/a/v2.APIцен,заданныхприказами-IncludeForCategoryDto)
* [PriceForCategoryDto](/articles/api-documentations/tseny-zadannye-prikazami/a/v2.APIцен,заданныхприказами-PriceForCategoryDto)
* [Получение цен](/articles/api-documentations/tseny-zadannye-prikazami/a/v2.APIцен,заданныхприказами-Получениецен.)
* [Параметры запроса](/articles/api-documentations/tseny-zadannye-prikazami/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/tseny-zadannye-prikazami/a/h3_501454233)
* [Примеры](/articles/api-documentations/tseny-zadannye-prikazami/a/h3__1185794887)

## API цен, заданных приказами

Версия iiko: 7.8

Описание полей

### ProductPriceDto
| Поле | Тип | Описание |
| --- | --- | --- |
| **departmentId** | UUID | Идентификатор департамента, в котором осуществляется продажа данного продукта. |
| **productId** | UUID | Идентификатор продукта. |
| **productSizeId** | UUID | Идентификатор размера продукта. |
| **prices** | List&lt;ProductPriceItemDto&gt; | Список цен на интервалах для данного продукта. |
### ProductPriceItemDto

Цена, действующая и остающаяся неизменной на интервале [dateFrom, dateTo), т.е. цена из базового приказа.

Если задано расписание (schedule != null), то это цена, действующая согласно расписанию на интервале [dateFrom, dateTo), т.е. цена из приказа по времени.
| Поле | Тип | Описание |
| --- | --- | --- |
| **dateFrom** | String | Начало действия приказа в формате "yyyy-MM-dd". |
| **dateTo** | String | Конец действия приказа в формате "yyyy-MM-dd". |
| **price** | BigDecimal | Цена. |
| **includeForCategories** | List&lt;IncludeForCategoryDto&gt; | Если в этом списке присутствует идентификатор категории, то для данной ценовой категории есть своя специфика ценообразования. |
| **pricesForCategories** | List&lt;PriceForCategoryDto&gt; | Цены для категорий. |
| **included** | Boolean | Включен ли продукт в прайс-лист. |
| **dishOfDay** | Boolean | Является ли блюдо хитом. |
| **flyerProgram** | Boolean | Участвует ли блюдо во флаерной программе. |
| **documentId** | UUID | Идентификатор приказа. |
| **schedule** | PeriodScheduleDto | Расписание. См. апи расписаний (структура такая же, только поле deleted исключено). |
| **taxCategoryId** | UUID | Идентификатор налоговой категории(НК). Действует только для базовых приказов без расписания. |
| **taxCategoryEnabled** | Boolean | Включена ли НК. Если да, то значение НК нужно брать из прейскуранта, заданного приказом. Если нет - из карточки товара. Действует только для базовых приказов без расписания. |
### IncludeForCategoryDto
| Поле | Тип | Описание |
| --- | --- | --- |
| **categoryId** | UUID | Идентификатор ценовой категории. |
| **include** | Boolean | Если true, то цену берем из PriceForCategoryDto, если false, то для данной ценовой категории данный продукт исключен из прайс-листа. |
### PriceForCategoryDto
| Поле | Тип | Описание |
| --- | --- | --- |
| **categoryId** | UUID | Идентификатор ценовой категории. |
| **price** | BigDecimal | Цена. |
## Получение цен

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/price |
| --- | --- |

### Параметры запроса

| Параметр | Тип | Описание |
| --- | --- | --- |
| **dateFrom** | String | Начало временного интервала в формате "yyyy-MM-dd". Обязательный. |
| **dateTo** | String | Конец временного интервала в формате "yyyy-MM-dd". По умолчанию '2500-01-01'. |
| **departmentId** | UUID | Список ресторанов, по которым делается запрос. Если не задан, то для всех. |
| **includeOutOfSale** | Boolean | Включать в ответ записи о снятии с продажи. По умолчанию false. |
| **type** | Enum | Цены какого типа выгружать. Если не задано, то все.<br>| Значение | Описание |<br>| --- | --- |<br>| **BASE** | Цена, которая действует на всем заданном интервале, т.е. из базового приказа. |<br>| **SCHEDULED** | Цена, которая действует по расписанию на заданном интервале, т.е. из приказа по времени. | |
| --- | --- | --- |
| **revisionFrom** | Integer | В ответе будут сущности с ревизией выше данной. По умолчанию '-1'. |

### Что в ответе

Список цен.

Поле revision - максимальная ревизия, доступная для выгрузки во внешние системы на момент запроса (это значит, что в базе присутствуют записи с такой ревизией, а записей с ревизией выше этой в базе нет).

Эту ревизию можно использовать в качестве параметра **revisionFrom** в следующем запросе на получение списка расписаний.

### Примеры

#### Запрос

https://localhost:8080/resto/api/v2/price?dateFrom=2019-01-01&type=BASE
[+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
#### Запрос

https://localhost:8080/resto/api/v2/price?dateFrom=2019-01-01&dateTo=2021-08-31&type=SCHEDULED
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```
