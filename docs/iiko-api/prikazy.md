* [API приказов](/articles/api-documentations/prikazy/a/v2.APIприказов-Описаниеполей)
* [MenuChangeDocumentDto](/articles/api-documentations/prikazy/a/v2.APIприказов-MenuChangeDocumentDto)
* [MenuChangeDocumentItemDto](/articles/api-documentations/prikazy/a/v2.APIприказов-MenuChangeDocumentItemDto)
* [IncludeForCategoryDto](/articles/api-documentations/prikazy/a/v2.APIприказов-IncludeForCategoryDto)
* [PriceForCategoryDto](/articles/api-documentations/prikazy/a/v2.APIприказов-PriceForCategoryDto)
* [Выгрузка приказов](/articles/api-documentations/prikazy/a/h2_1894775106)
* [Параметры запроса](/articles/api-documentations/prikazy/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/prikazy/a/h3_501454233)
* [Пример запроса и результата](/articles/api-documentations/prikazy/a/h3_1561844723)
* [Выгрузка приказа по идентификатору](/articles/api-documentations/prikazy/a/h2_362568358)
* [Параметры запроса](/articles/api-documentations/prikazy/a/h3__1718461175)
* [Пример запроса и результата](/articles/api-documentations/prikazy/a/h3_1214224988)
* [Выгрузка приказов по номеру](/articles/api-documentations/prikazy/a/h2_1748209904)
* [Параметры запроса](/articles/api-documentations/prikazy/a/h3_1693881420)
* [Пример запроса и результат](/articles/api-documentations/prikazy/a/h3__2087356861)
* [Создание/редактирование приказа](/articles/api-documentations/prikazy/a/h2_2107861861)
* [Тело запроса](/articles/api-documentations/prikazy/a/h3_1150399349)
* [Пример](/articles/api-documentations/prikazy/a/h3_1250036116)

* [Цены, заданные приказами](/articles/api-documentations/tseny-zadannye-prikazami)

##  API приказов

##  Версия iiko: 7.8

##  Описание полей

###  MenuChangeDocumentDto

| Поле | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | Идентификатор. |
| **dateIncoming** | String | Дата проведения документа (учетная) в формате "yyyy-MM-dd". |
| **documentNumber** | String | Учетный номер документа. |
| **status** | Enum | Статус документа.<br> | Значение | Описание |<br>| --- | --- |<br>| **NEW** | Новый. |<br>| **PROCESSED** | Проведенный. |<br>| **DELETED** | Удаленный. | |
| --- | --- | --- |
| **comment** | String | Комментарий к документу. |
| **shortName** | String | Короткое название приказа для отображения на кнопках фронта. |
| **deletePreviousMenu** | Boolean | Если true, то те блюда, которые не присутствуют в документе, будут исключены из меню. |
| **scheduleId** | UUID | Идентификатор расписания. Задается пользователем при создании/редактировании приказа по времени. |
| **schedule** | PeriodScheduleDto | Расписание действия приказа по времени. Только чтение. |
| **dateTo** | String | Дата окончания действия (отмены) приказа в формате "yyyy-MM-dd". |
| **items** | List&lt;MenuChangeDocumentItemDto&gt; | Позиции приказа. |

###  MenuChangeDocumentItemDto

| Поле | Тип | Описание |
| --- | --- | --- |
| **num** | Integer | Позиция строки в документе. При создании/редактировании приказа не учитывается. |
| **departmentId** | UUID | Идентификатор департамента, в котором осуществляется продажа данного продукта. |
| **productId** | UUID | Идентификатор продукта. |
| **productSizeId** | UUID | Идентификатор размера продукта. |
| **including** | Boolean | Включен ли продукт в прайс-лист. |
| **price** | BigDecimal | Цена. |
| **dishOfDay** | Boolean | Является ли блюдо хитом. |
| **flyerProgram** | Boolean | Участвует ли блюдо во флаерной программе. |
| **includeForCategories** | List&lt;IncludeForCategoryDto&gt; | Если в этом списке присутствует идентификатор категории, то для данной ценовой категории есть своя специфика ценообразования. |
| **pricesForCategories** | List&lt;PriceForCategoryDto&gt; | Цены для категорий. |

###  IncludeForCategoryDto

| Поле | Тип | Описание |
| --- | --- | --- |
| **categoryId** | UUID | Идентификатор ценовой категории. |
| **include** | Boolean | Если true, то цену берем из PriceForCategoryDto, если false, то для данной ценовой категории данный продукт исключен из прайс-листа. |

###  PriceForCategoryDto

| Поле | Тип | Описание |
| --- | --- | --- |
| **categoryId** | UUID | Идентификатор ценовой категории. |
| **price** | BigDecimal | Цена. |

## Выгрузка приказов

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/documents/menuChange |
| --- | --- |

### Параметры запроса

| Параметр | Тип | Описание |
| --- | --- | --- |
| dateFrom | String | Начало временного интервала в формате "yyyy-MM-dd". Обязательный. |
| dateTo | String | Конец временного интервала в формате "yyyy-MM-dd". Обязательный. |
| status | Enum | Статус документа. Если не задан, то все. |
| revisionFrom | Integer | В ответе будут сущности с ревизией выше данной. По умолчанию '-1'. |

### Что в ответе
 
Список приказов.
 
Поле revision - максимальная ревизия, доступная для выгрузки во внешние системы на момент запроса (это значит, что в базе присутствуют записи с такой ревизией, а записей с ревизией выше этой в базе нет).
 
Эту ревизию можно использовать в качестве параметра **revisionFrom** в следующем запросе на получение списка расписаний.
 
### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/documents/menuChange?dateFrom=2021-08-01&dateTo=2021-09-31
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```


##  Выгрузка приказа по идентификатору

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/documents/menuChange/byId |
| --- | --- |

### Параметры запроса
 | Параметр | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | Идентификатор приказа. |
 
### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/documents/menuChange/byId?id=d776601c-3184-40d0-8d90-e0cd2164801a
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 
##  Выгрузка приказов по номеру

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/documents/menuChange/byNumber |
| --- | --- |

### Параметры запроса
 | Параметр | Тип | Описание |
| --- | --- | --- |
| **documentNumber** | String | Номер документа. |
 
### Пример запроса и результат

#### Запрос 

https://localhost:8080/resto/api/v2/documents/menuChange/byNumber?documentNumber=0006
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE4%%%%CH%PRE5%%
```


## Создание/редактирование приказа

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/documents/menuChange |
| --- | --- |

### Тело запроса
 
См. MenuChangeDocumentDto.
 
Если идентификатор документа не задан, то это создание нового приказа.
 
Если идентификатор документа задан, то это редактирование приказа.
 
Редактировать приказ можно, если

1. он находится в статусе 'NEW'
2. он находится в статуе 'PROCESSED' и дата проведения (начала действия) приказа сегодня или позже

У приказа в статусе 'PROCESSED', дата проведения которого вчера или ранее, можно изменить только дату окончания, если дата окончания завтра или позже.
 
Редактировать НК в приказе (поля taxCategoryId и taxCategoryEnabled) можно только при наличии лицензионного модуля 'Возможность задавать налоговую категорию в приказах на изменение меню' (ModuleId = 21052802).
 
Если явно задать taxCategoryEnabled при отключенной лицензии, то значения полей taxCategoryId и taxCategoryEnabled будут проигнорированы,  в БД значения этих полей не изменятся, в серверный лог будет выведено предупреждение вида:
 
The licensing module TAXCATEGORY\_IN\_PRICECHANGEORDER is not present or expired. Failed to establish tax category TaxCategory[ade0e464-0651-459b-ab14-12bab1570983]@80623417,r124 '20' for product товар\_2 (GOODS), produceSize null, department Department[0226a08b-b08d-428d-a505-f9a0de024373]@1330525574,r27 {code: 1, 'Новое торг. предприятие'}, date Wed Jul 12 00:00:00 MSK 2023
 Если не задавать явно taxCategoryEnabled, как это делают старые интеграции, которые ничего не знают про поля НК/Включить НК,
 то в БД значения этих полей не изменятся. Наличие лицензии в этом случае не проверяется.
 
###  Пример 

https://localhost:8080/resto/api/v2/documents/menuChange
 [+] [Запрос](javascript:void%280%29)
 [-] [Запрос](javascript:void%280%29)
 
```
 %%CH%PRE6%%%%CH%PRE7%%
```

 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE8%%%%CH%PRE9%%
```
