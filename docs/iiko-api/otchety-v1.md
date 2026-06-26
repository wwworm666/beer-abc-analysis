* [Отчет по складским операциям](/articles/api-documentations/otchety-v1/a/v1.APIотчетов-Отчетпоскладскимоперациям)
* [Параметры запроса](/articles/api-documentations/otchety-v1/a/h3_2063281844)
* [Что в ответе](/articles/api-documentations/otchety-v1/a/h3_397569361)
* [Пресеты отчетов по складским операциям](/articles/api-documentations/otchety-v1/a/h2__1976728320)
* [Что в ответе](/articles/api-documentations/otchety-v1/a/h3_501454233)
* [Пример запроса](/articles/api-documentations/otchety-v1/a/h3_107858276)
* [Расход продуктов по продажам](/articles/api-documentations/otchety-v1/a/v1.APIотчетов-Расходпродуктовпопродажам)
* [Параметры запроса](/articles/api-documentations/otchety-v1/a/h3__6462416)
* [Что в ответе](/articles/api-documentations/otchety-v1/a/h3__390094491)
* [Пример запроса](/articles/api-documentations/otchety-v1/a/h3_2111503716)
* [Отчет по выручке](/articles/api-documentations/otchety-v1/a/v1.APIотчетов-Отчетповыручке)
* [Параметры запроса](/articles/api-documentations/otchety-v1/a/h3_642632569)
* [Что в ответе](/articles/api-documentations/otchety-v1/a/h3_875618913)
* [Пример запроса](/articles/api-documentations/otchety-v1/a/h3_1387997121)
* [План по выручке за день](/articles/api-documentations/otchety-v1/a/h2_228385197)
* [Параметры запроса](/articles/api-documentations/otchety-v1/a/h3_1718516096)
* [Что в ответе](/articles/api-documentations/otchety-v1/a/h3__722715718)
* [Пример запроса](/articles/api-documentations/otchety-v1/a/h3__523120185)
* [Отчет о вхождении товара в блюдо](/articles/api-documentations/otchety-v1/a/v1.APIотчетов-Отчетовхождениитоваравблюдо)
* [Параметры запроса](/articles/api-documentations/otchety-v1/a/h3_771325741)
* [Что в ответе](/articles/api-documentations/otchety-v1/a/h3_868823442)
* [Пример запроса](/articles/api-documentations/otchety-v1/a/h3__1446432940)
* [XSD Отчеты](/articles/api-documentations/otchety-v1/a/h2_1048369972)

## Отчет по складским операциям

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**reports/storeOperations** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| dateFrom | DD.MM.YYYY | Начальная дата |
| dateTo | DD.MM.YYYY | Конечная дата |
| stores | GUID | Список складов, по которым строится отчет. Если null или empty, строится по всем складам. |
| documentTypes | См. раздел "Расшифровки кодов базовых типов - Типы документов" | Типы документов, которые следует включать. Если null или пуст, включаются все документы. |
| productDetalization | Boolean | Если истина, отчет включает информацию по товарам, но не включает дату. Если ложь - отчет включает каждый документ одной строкой и заполняет суммы документов |
| showCostCorrections | Boolean | Включать ли коррекции себестоимости. Данная опция учитывается только если задан фильтр по типам документов. В противном случае коррекции включаются. |
| presetId | GUID | Id преднастроенного отчета. Если указан, то все настройки, кроме дат, игнорируются. |

### Что в ответе

Структура *storeReportItemDto* (см. XSD Отчет по складским операциям)

### Пример запроса

Параметры передаются явно

| https://localhost:8080/resto/api/reports/storeOperations?key=1ac6b9a3-19a0-7c60-e23b-124dd70d75da&dateFrom=01.09.2014&dateTo=09.09.2014&productDetalization=false&showCostCorrections=false&documentTypes=SALES\_DOCUMENT&documentTypes=INCOMING\_INVOICE&stores=1239d270-1bbe-f64f-b7ea-5f00518ef508&stores=93c5cc1f-4c80-4bea-9100-70053a10e37a |
| --- |

Передается presetId преднастроенного отчета в iikoOffice

| https://localhost:8080/resto/api/reports/storeOperations?key=1ac6b9a3-19a0-7c60-e23b-124dd70d75da&dateFrom=01.12.2014&dateTo=17.12.2014&presetId=bf8886b3-a765-6535-37e4-873bce201482 |
| --- |


```

```


##  Пресеты отчетов по складским операциям

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**reports/storeReportPresets** |
| --- | --- |

### Что в ответе

Структура *storeReportPresets* (см. XSD Пресеты отчетов по складским операциям)

### Пример запроса

| https://localhost:8080/resto/api/reports/storeReportPresets?key=1ac6b9a3-19a0-7c60-e23b-124dd70d75da |
| --- |

## Расход продуктов по продажам

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**reports/productExpense** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| department | GUID | Подразделение |
| dateFrom | DD.MM.YYYY | Начальная дата |
| dateTo | DD.MM.YYYY | Конечная дата |
| hourFrom | hh | Час начала интервала выборки в сутках (по умолчанию -1, все время) |
| hourTo | hh | Час окончания интервала выборки в сутках (по умолчанию -1, все время) |

### Что в ответе

Структура *dayDishValue* (см. XSD Расход продуктов по продажам)

### Пример запроса

| https://localhost:8080/resto/api/reports/productExpense?key=1ac6b9a3-19a0-7c60-e23b-124dd70d75da&department=49023e1b-6e3a-6c33-0133-ce1f6f5000b&dateFrom=01.12.2014&dateTo=17.12.2014&hourFrom=12&hourTo=15 |
| --- |

## Отчет по выручке

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**reports/sales** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| department | GUID | Подразделение |
| dateFrom | DD.MM.YYYY | Начальная дата |
| dateTo | DD.MM.YYYY | Конечная дата |
| hourFrom | hh | Час начала интервала выборки в сутках (по умолчанию -1, все время), по умолчанию -1 |
| hourTo | hh | Час окончания интервала выборки в сутках (по умолчанию -1, все время), по умолчанию -1 |
| dishDetails | Boolean | Включать ли разбивку по блюдам (true/false), по умолчанию false |
| allRevenue | Boolean | Фильтрация по типам оплат (true - все типы, false - только выручка), по умолчанию true |

###  

### Что в ответе

Структура *dayDishValue* (см. XSD Отчет по выручке)

### Пример запроса

| https://localhost:8080/resto/api/reports/sales?key=1ac6b9a3-19a0-7c60-e23b-124dd70d75da&department=49023e1b-6e3a-6c33-0133-cce1f6f5000b&dateFrom=01.12.2014&dateTo=17.12.2014&hourFrom=12&hourTo=15&dishDetails=true&allRevenue=false |
| --- |

###  


```

```


## План по выручке за день

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**reports/monthlyIncomePlan** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| *department* | GUID | Подразделение |
| *dateFrom* | DD.MM.YYYY | Начальная дата |
| *dateTo* | DD.MM.YYYY | Конечная дата |

###  

### Что в ответе

Структура budgetPlanItemDtoes (см. XSD План по выручке за день)

### Пример запроса

| https://localhost:8080/resto/api/reports/monthlyIncomePlan?key=05e04d9e-26db-a5a2-ba2b-68af4e8a5ed4&department=49023e1b-6e3a-6c33-0133-cce1f6f5000b&dateFrom=01.12.2014&dateTo=18.12.2014 |
| --- |

### 


```
 
```


##  Отчет о вхождении товара в блюдо

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**reports**/**ingredientEntry** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| department | GUID | Подразделение |
| date | DD.MM.YYYY | На какую дату |
| product | DD.MM.YYYY | Id продукта |
| productArticle | Строка | Артикул продукта (приоритет поиска:*productArticle, product*) |
| includeSubtree | Boolean | Включать ли в отчет строки поддеревьев (по умолчанию false) |

###  

### Что в ответе

Структура ingredientEntryDtoes (см. XSD Отчет о вхождении товара в блюдо)

### Пример запроса

| https://localhost:8080/resto/api/reports/ingredientEntry?key=05e04d9e-26db-a5a2-ba2b-68af4e8a5ed4&date=01.12.2014&product=2c3ab3e1-266d-4667-b344-98b6c194a305&department=49023e1b-6e3a-6c33-0133-cce1f6f5000b&includeSubtree=false |
| --- |

## 

## XSD Отчеты
[+] [XSD Отчет о вхождении товара в блюдо](javascript:void%280%29)
 [-] [XSD Отчет о вхождении товара в блюдо](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 [+] [XSD Отчет по выручке](javascript:void%280%29)
 [-] [XSD Отчет по выручке](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 [+] [XSD Отчет по складским операциям](javascript:void%280%29)
 [-] [XSD Отчет по складским операциям](javascript:void%280%29)
 
```
 %%CH%PRE4%%%%CH%PRE5%%
```

 [+] [XSD План по выручке за день](javascript:void%280%29)
 [-] [XSD План по выручке за день](javascript:void%280%29)
 
```
 %%CH%PRE6%%%%CH%PRE7%%
```

 [+] [XSD Пресеты отчетов по складским операциям](javascript:void%280%29)
 [-] [XSD Пресеты отчетов по складским операциям](javascript:void%280%29)
 
```
 %%CH%PRE8%%%%CH%PRE9%%
```

 [+] [XSD Расход продуктов по продажам](javascript:void%280%29)
 [-] [XSD Расход продуктов по продажам](javascript:void%280%29)
 
```
 %%CH%PRE10%%%%CH%PRE11%%
```

 
##  

##
