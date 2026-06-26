* [Стратегия расчета](/articles/api-documentations/tsenovye-kategorii/a/h3__812471)
* [Получение ценовых категорий](/articles/api-documentations/tsenovye-kategorii/a/v2.APIценовыхкатегорий-Получениеценовыхкатегорий)
* [Параметры запроса](/articles/api-documentations/tsenovye-kategorii/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/tsenovye-kategorii/a/h3_501454233)
* [Примеры запроса и результата](/articles/api-documentations/tsenovye-kategorii/a/h3_289737302)
* [Получение ценовой категории по идентификатору](/articles/api-documentations/tsenovye-kategorii/a/v2.APIценовыхкатегорий-Получениеценовойкатегориипоидентификатору)
* [Параметры запроса](/articles/api-documentations/tsenovye-kategorii/a/h3__974892588)
* [Пример запроса и результата](/articles/api-documentations/tsenovye-kategorii/a/h3_1561844723)

# API ценовых категорий

Версия iiko: 7.8

Описание полей

Ценовая категория

#### ClientPriceCategoryDto
| Поле | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | Идентификатор. |
| **name** | String | Название. |
| **deleted** | boolean | Удалена или нет. |
| **code** | String | Пользовательский код элемента справочника. |
| **assignableManually** | boolean | Может быть назначена вручную в iikoFront. |
| **pricingStrategy** | PricingStrategyDto | Стратегия расчёта новой цены. |
### 

### Стратегия расчета

#### **PricingStrategyDto**
| Поле | Тип | Описание |
| --- | --- | --- |
| **type** | Enum | Тип стратегии.<br>| Значение | Описание |<br>| --- | --- |<br>| ABSOLUTE\_VALUE | Стратегия, где скидка/наценка задаётся как абсолютное число, которое будет прибавляться к базовой цене. |<br>| PERCENT | Стратегия вычисления, когда скидка/надбавка задаётся в % от базовой цены. | |
| --- | --- | --- |
| **delta** | BigDecimal | Абсолютное значение скидки/надбавки. Если знак '-', то скидка, если '+', то надбавка. Актуально ABSOLUTE\_VALUE. |
| **percent** | BigDecimal | Значение скидки/надбавки в процентах. Если знак '-', то скидка, если '+', то надбавка. Диапазон значений: [-100, +inf). Актуально для PERCENT. |
## 

## Получение ценовых категорий

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/entities/priceCategories |
| --- | --- |

### Параметры запроса
| Параметр | Тип | Описание |
| --- | --- | --- |
| **includeDeleted** | Boolean | Включать ли в ответ удаленные элементы. По умолчанию false. |
| **id** | List&lt;UUID&gt; | Список идентификаторов ценовых категорий, которые требуется получить. Если не задано, то фильтрации по идентификаторам нет. |
| **revisionFrom** | Integer | В ответе будут сущности с ревизией выше данной. По умолчанию '-1'. |
### Что в ответе

Список ценовых категорий.

Поле revision - максимальная ревизия, доступная для выгрузки во внешние системы на момент запроса (это значит, что в базе присутствуют записи с такой ревизией, а записей с ревизией выше этой в базе нет).

Эту ревизию можно использовать в качестве параметра **revisionFrom** в следующем запросе на получение списка ценовых категорий.

### Примеры запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/priceCategories/?includeDeleted=true
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
#### Запрос

https://localhost:8080/resto/api/v2/entities/priceCategories?id=95035a38-cd23-4b3b-92d8-1db673b6848f&id=67a54111-99ff-40cc-9f34-f2feddd0ff2b
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```


## Получение ценовой категории по идентификатору

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/**entities/priceCategories/byId** |
| --- | --- |

### Параметры запроса
| Параметр | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | Идентификатор ценовой категории. |
### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/priceCategories/byId/?id=95035a38-cd23-4b3b-92d8-1db673b6848f
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE4%%%%CH%PRE5%%
```
