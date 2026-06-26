* [Поля OLAP-отчета](/articles/api-documentations/olap-otchety-v2/a/id-ПоляOLAP-отчета-ПоляOLAP-отчета)
* [Параметры запроса](/articles/api-documentations/olap-otchety-v2/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/olap-otchety-v2/a/h3__1412816402)
* [Пример запроса](/articles/api-documentations/olap-otchety-v2/a/h3__232688264)
* [Ответ](/articles/api-documentations/olap-otchety-v2/a/h3_592227717)
* [Общая информация (General info)](/articles/api-documentations/olap-otchety-v2/a/h2_584103350)
* [Тело запроса](/articles/api-documentations/olap-otchety-v2/a/h3_1150399349)
* [Фильтры](/articles/api-documentations/olap-otchety-v2/a/h2__1986441144)
* [Фильтр по значению](/articles/api-documentations/olap-otchety-v2/a/h3__391585873)
* [Фильтр по диапазону](/articles/api-documentations/olap-otchety-v2/a/h3__1715677954)
* [Фильтр по дате](/articles/api-documentations/olap-otchety-v2/a/h3__951638809)
* [Фильтр по дате и времени](/articles/api-documentations/olap-otchety-v2/a/h3_37586638)

##  Поля OLAP-отчета

Версия iiko: 4.1

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **https://host:port/resto/api/v2**/reports/olap/columns |
| --- | --- |

### Параметры запроса

| Параметры | Описание |
| --- | --- |
| reportType | Тип отчета:<br><ul style="margin: 10px 0px 0px; padding-left: 22px;"><li><span style="font-size: 12pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">SALES - По продажам </span></span></li><li><span style="font-size: 12pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">TRANSACTIONS - По транзакциям </span></span></li><li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;"><span style="font-size: 12pt;">DELIVERIES - По доставкам</span> </span></li></ul> |

### Что в ответе

Json структура списка полей с информацией по возможностям фильтрации, агрегации и группировки.

Устаревшие поля (deprecated) не выводятся.

### Структура списка полей 


```json
"FieldName": {
  "name": "StringValue",
  "type": "StringValue",
  "aggregationAllowed": booleanValue,
  "groupingAllowed": booleanValue,
  "filteringAllowed": booleanValue,
  "tags": [
    "StringValue1",
    "StringValue2",
    ...,
    "StringValueN",
  ]
}
```

```json
"FieldName": {
  "name": "StringValue",
  "type": "StringValue",
  "aggregationAllowed": booleanValue,
  "groupingAllowed": booleanValue,
  "filteringAllowed": booleanValue,
  "tags": [
    "StringValue1",
    "StringValue2",
    ...,
    "StringValueN",
  ]
}
```


| Название | Значение | Описание |
| --- | --- | --- |
| 
```
FieldName 
```
 | Строка | Название колонки отчета. Именно это название используется для получения данных отчета |
| 
```
name 
```
 | Строка | Название колонки отчета в iikoOffice. Справочная информация. |
| type | Строка | Тип поля. Возможны следующие значения:<br><ul style="margin: 10px 0px 0px; padding-left: 22px;"><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">ENUM - Перечислимые значения </span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">STRING - Строка </span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">ID - Внутренний идентификатор объекта в iiko (начиная с 5.0) </span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">DATETIME - Дата и время </span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">INTEGER - Целое </span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">PERCENT - Процент (от 0 до 1) </span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">DURATION_IN_SECONDS - Длительность в секундах </span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">AMOUNT - Количество </span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">MONEY - Денежная сумма </span></span></li></ul> |
| 
```
aggregationAllowed

```
 | true/false | Если true, то по данной колонке можно агрегировать данные |
| 
```
groupingAllowed

```
 | true/false | Если true, то по данной колонке можно группировать данные |
| 
```
filteringAllowed

```
 | true/false | Если true, то по данной колонке можно фильтровать данные |
| 
```
tags

```
 | Список строк | Список категорий отчета, к которому относится данное поле. Справочная информация. Соответствует списку в верхнем правом углу конструктора отчета в iikoOffice. |

###  Пример запроса

https://localhost:8080/resto/api/v2/reports/olap/columns?key=5b119afe-9468-ab68-7d56-c71495e39ee4&reportType=SALES

### Ответ 


```json
{
  "PercentOfSummary.ByCol": {
    "name": "% по столбцу",
    "type": "PERCENT",
    "aggregationAllowed": true,
    "groupingAllowed": false,
    "filteringAllowed": false,
    "tags": [
      "Оплата"
    ]
  },
  "PercentOfSummary.ByRow": {
    "name": "% по строке",
    "type": "PERCENT",
    "aggregationAllowed": true,
    "groupingAllowed": false,
    "filteringAllowed": false,
    "tags": [
      "Оплата"
    ]
  },
  "Delivery.Email": {
    "name": "e-mail доставки",
    "type": "STRING",
    "aggregationAllowed": false,
    "groupingAllowed": true,
    "filteringAllowed": true,
    "tags": [
      "Доставка",
      "Клиент доставки"
    ]
  }
}
```

```json
{
  "PercentOfSummary.ByCol": {
    "name": "% по столбцу",
    "type": "PERCENT",
    "aggregationAllowed": true,
    "groupingAllowed": false,
    "filteringAllowed": false,
    "tags": [
      "Оплата"
    ]
  },
  "PercentOfSummary.ByRow": {
    "name": "% по строке",
    "type": "PERCENT",
    "aggregationAllowed": true,
    "groupingAllowed": false,
    "filteringAllowed": false,
    "tags": [
      "Оплата"
    ]
  },
  "Delivery.Email": {
    "name": "e-mail доставки",
    "type": "STRING",
    "aggregationAllowed": false,
    "groupingAllowed": true,
    "filteringAllowed": true,
    "tags": [
      "Доставка",
      "Клиент доставки"
    ]
  }
}
```


## Общая информация (General info)

Версия iiko: 4.1

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | **https://host:port/resto/api/v2/****reports/olap** |
| --- | --- |

Content-type: Application/json; charset=utf-8

###  Тело запроса


```json
{
  "reportType": "EnumValue",
  "buildSummary": "true",
  "groupByRowFields": [
    "groupByRowFieldName1",
    "groupByRowFieldName2",
    ...,
    "groupByRowFieldNameN"
  ],
  "groupByColFields": [
    "groupByColFieldName1",
    "groupByColFieldName2",
    ...,
    "groupByColFieldNameL"
  ],
  "aggregateFields": [
    "AggregateFieldName1",
    "AggregateFieldName2",
    ...,
    "AggregateFieldNameM"
  ],
  "filters": {
    filter1,
    filter2,
    ...
    filterK
  }
}
```

```json
{
  "reportType": "EnumValue",
  "buildSummary": "true",
  "groupByRowFields": [
    "groupByRowFieldName1",
    "groupByRowFieldName2",
    ...,
    "groupByRowFieldNameN"
  ],
  "groupByColFields": [
    "groupByColFieldName1",
    "groupByColFieldName2",
    ...,
    "groupByColFieldNameL"
  ],
  "aggregateFields": [
    "AggregateFieldName1",
    "AggregateFieldName2",
    ...,
    "AggregateFieldNameM"
  ],
  "filters": {
    filter1,
    filter2,
    ...
    filterK
  }
}
```


| Название | Значение | Описание |
| --- | --- | --- |
| 
```
reportType

```
 | SALES<br><br>TRANSACTIONS<br><br>DELIVERIES | Тип отчета:<br><ul style="margin: 10px 0px 0px; padding-left: 22px;"><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">SALES - По продажам </span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">TRANSACTIONS - По проводками </span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">DELIVERIES - По доставкам </span></span></li></ul> |
| 
```
buildSummary
```
 | true/false | Параметр появился в **Version(iiko) 5.3.4.** Считать ли итоговые значения. Необязательное, до версии 9.1.2 по умолчанию true, с версии 9.1.2 по умолчанию false. |
| 
```
groupByRowFields 
```
 | Список полей для группировки по строкам | Имена полей, по которым доступна группировка. Список полей можно получить через метод **reports**/**olap**/**columns**, как элементы данного списка используются поля FieldName из возвращаемой **reports**/**olap**/**columns** структуры. Для указания в данном списке доступны поля, у которых **groupingAllowed** = **true** |
| 
```
groupByColFields 
```
 | Список полей для группировки по столбцам | Необязательный. Имена полей, по которым доступна группировка. Список полей можно получить через метод **reports**/**olap**/**columns**, как элементы данного списка используются поля FieldName из возвращаемой **reports**/**olap**/**columns** структуры. Для указания в данном списке доступны поля, у которых **groupingAllowed** = **true** |
| 
```
aggregateFields 
```
 | Список полей для агрегации | Имена полей, по которым доступна агрегация. Список полей можно получить через метод **reports**/**olap**/**columns**, как элементы данного списка используются поля FieldName из возвращаемой **reports**/**olap**/**columns** структуры. Для указания в данном списке доступны поля, у которых **filteringAllowed**= **true** |
| 
```
filters 
```
 | Список фильтров | См. описание структуры фильтров. Для указания в данном списке доступны поля, у которых **filteringAllowed** = **true** |

| ![Information](/resources/Storage/api-documentations/info.png) | Поля агрегации, учитывающие начальный остаток товара и денежный остаток (StartBalance.Amount, StartBalance.Money, FinalBalance.Amount, FinalBalance.Money) вычисляются суммированием всей таблицы проводок **за все время** работы системы (всей базы данных) без каких-либо оптимизаций. То есть, такой запрос может выполняться очень долго и замедлять работу сервера.<br>Если начальный остаток необходим, оставляйте в этом OLAP-запросе только те поля группировки, по которым он действительно необходим (как правило, это Account.Name и Product.Name), и вызывайте такой запрос **как можно реже** и в **не рабочее** время.<br><br>В 5.2 добавлено API для быстрого получения остатков: Отчеты по балансам. Во всех случаях рекомендуется пользоваться им вместо OLAP.<br><br>В 5.5 OLAP-отчеты с остатками оптимизированы с использованием балансовых таблиц ATransactionSum, ATransactionBalance, при условии, что применяются группировки и фильтры по полям из этих таблиц, см. признак StartBalanceOptimizable в описании полей.<br><br>То есть, правильно составленный запрос приведет к суммированию не всей таблицы проводок, а только лишь открытого периода. Обратите особое внимание на то, что оптимизировано только поле Account.Name (счет "текущей" стороны проводки, в том числе склад), а не Store (первый попавшийся "склад" проводки, взятый из: левой, правой части проводки, строки документа или самого документа). |
| --- | --- |

## Фильтры

###  Фильтр по значению 


```json
"FieldName": {
"filterType": "filterTypeEnum",
"values": ["Value1","Value2",...,"ValueN"]
}
```

```json
"FieldName": {
"filterType": "filterTypeEnum",
"values": ["Value1","Value2",...,"ValueN"]
}
```


Работает для полей с типами:

* ENUM
* STRING

| Название | Значение | Описание |
| --- | --- | --- |
| 
```
FieldName

```
 | Имя поля для фильтрации | Поле FieldName из возвращаемой **reports**/**olap**/**columns** структуры |
| 
```
filterType

```
 | IncludeValues / ExcludeValues | IncludeValues - в фильтрации участвуют только перечисленные значения поля<br><br>ExcludeValues - в фильтрации участвуют значения поля, за исключением перечисленных |
| 
```
values 
```
 | Список значений поля | В зависимости от типа поля, это могут быть или enum из Расшифровки кодов базовых типов или текстовое значение поля |


```json
"DeletedWithWriteoff": {
"filterType": "ExcludeValues",
"values": ["DELETED_WITH_WRITEOFF","DELETED_WITHOUT_WRITEOFF"]
},
"OrderDeleted": {
"filterType": "IncludeValues",
"values": ["NOT_DELETED"]
}
```

```json
"DeletedWithWriteoff": {
"filterType": "ExcludeValues",
"values": ["DELETED_WITH_WRITEOFF","DELETED_WITHOUT_WRITEOFF"]
},
"OrderDeleted": {
"filterType": "IncludeValues",
"values": ["NOT_DELETED"]
}
```


###  Фильтр по диапазону 


```json
"FieldName": {
"filterType": "Range",
"from": Value1,
"to": Value2,
"includeLow": booleanValue,
"includeHigh": booleanValue
}
```

```json
"FieldName": {
"filterType": "Range",
"from": Value1,
"to": Value2,
"includeLow": booleanValue,
"includeHigh": booleanValue
}
```


Работает для полей с типами:

* INTEGER
* PERCENT
* AMOUNT
* MONEY

| Название | Значение | Описание |
| --- | --- | --- |
| 
```
FieldName

```
 | Имя поля для фильтрации | Поле FieldName из возвращаемой **reports**/**olap**/**columns** структуры |
| 
```
filterType

```
 | Range | Фильтр по диапазону значений |
| from | Нижняя граница диапазона | Значение в формате, соответствующем типу поля |
| to | Верхняя граница диапазона | Значение в формате, соответствующем типу поля |
| includeLow | true/false | Необязательное, по умолчанию true<br><br>true - нижняя граница диапазона включается в фильтр<br><br>false - нижняя граница диапазона не включается в фильтр |
| includeHigh | true/false | Необязательное, по умолчанию false<br><br>true - верхняя граница диапазона включается в фильтр<br><br>false - верхняя граница диапазона не включается в фильтр |


```json
"SessionNum": {
"filterType": "Range",
"from": 758,
"to": 760,
"includeHigh": true
}
```

```json
"SessionNum": {
"filterType": "Range",
"from": 758,
"to": 760,
"includeHigh": true
}
```


###  Фильтр по дате 


```json
"FieldName": {
"filterType": "DateRange",
"periodType": "periodTypeEnum",
"from": "fromDateTime",
"to": "toDateTime",
"includeLow": booleanValue,
"includeHigh": booleanValue
}
```

```json
"FieldName": {
"filterType": "DateRange",
"periodType": "periodTypeEnum",
"from": "fromDateTime",
"to": "toDateTime",
"includeLow": booleanValue,
"includeHigh": booleanValue
}
```


Работает для полей с типами:

* DATETIME
* DATE

| Название | Значение | Описание |
| --- | --- | --- |
| 
```
FieldName 
```
 | Имя поля для фильтрации | Поле FieldName из возвращаемой **reports**/**olap**/**columns** структуры |
| 
```
filterType

```
 | DateRange | Фильтр по диапазону значений |
| 
```
periodType

```
 | CUSTOM - вручную<br><br>OPEN\_PERIOD - текущий открытый период<br><br>TODAY - сегодня<br><br>YESTERDAY - вчера<br><br>CURRENT\_WEEK - текущая неделя<br><br>CURRENT\_MONTH - текущий месяц<br><br>CURRENT\_YEAR - текущий год<br><br>LAST\_WEEK - прошлая неделя<br><br>LAST\_MONTH - прошлый месяц<br><br>LAST\_YEAR - прошлый год | Если период CUSTOM, то период задается вручную, используются поля from, to, includeLow, includeHigh<br><br>Для остальных типов периода данные параметры игнорируются (можно не использовать), кроме параметра from, его передача обязательна, его значение может быть любым. |
| from | Начальная дата | Дата в формате yyyy-MM-dd'T'HH:mm:ss.SSS |
| to | Конечная дата | Дата в формате yyyy-MM-dd'T'HH:mm:ss.SSS |
| includeLow | true/false | Необязательное, по умолчанию **true**<br><br>true - нижняя граница диапазона включается в фильтр<br><br>false - нижняя граница диапазона не включается в фильтр |
| includeHigh | true/false | Необязательное, по умолчанию **false**<br>true - верхняя граница диапазона включается в фильтр. Внимание: включение верхней границы имеет смысл только у полей, выдающих **округленную** **ДАТУ**, а не **ДАТУ**-**ВРЕМЯ**.<br><br>false - верхняя граница диапазона не включается в фильтр |

| ![Information](/resources/Storage/api-documentations/info.png) | В OLAP-отчете по проводкам ("reportType": "TRANSACTIONS") для фильтрации по \*дате\* рекомендуется использовать поле DateTime.DateTyped(или DateTime.Typed — но это дата-время)<br><br>В OLAP-отчете по продажам, а также доставкам используется поле OpenDate.Typed.<br><br>В 4.1 вместо отсутствующих полей OpenDate.Typed и DateTime.DateTyped используются поля OpenDate и DateTime.OperDayFilter соответственно.<br><br>Начиная с 5.5, каждый OLAP-запрос должен содержать фильтр по дате |
| --- | --- |


```json
"OpenDate.Typed": {
"filterType": "DateRange",
"periodType": "CUSTOM",
"from": "2014-01-01T00:00:00.000",
"to": "2014-01-03T00:00:00.000" 
}
```

```json
"OpenDate.Typed": {
"filterType": "DateRange",
"periodType": "CUSTOM",
"from": "2014-01-01T00:00:00.000",
"to": "2014-01-03T00:00:00.000" 
}
```


### Фильтр по дате и времени


```xml
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
```

```xml
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
```


#### Ответ


```json
{
  "data": [
    {
      "GroupFieldName1": "Value11",
      "GroupFieldName2": "Value12",
       ...,
      "GroupFieldNameN": "Value1N",
      "AggregateFieldName1": "Value11",
      "AggregateFieldName1": "Value12",
       ...,
      "AggregateFieldNameM": "Value1M"
    },
    ...,
    {
      "GroupFieldName1": "ValueK1",
      "GroupFieldName2": "ValueK2",
       ...,
      "GroupFieldNameN": "ValueKN",
      "AggregateFieldName1": "ValueK1",
      "AggregateFieldName1": "ValueK2",
       ...,
      "AggregateFieldNameM": "ValueKM"
    }
  ],
  "summary": [
   [
      {
         
      },
      {
        "AggregateFieldName1": "TotalValue1",
        "AggregateFieldName2": "TotalValue2",
        ...,
        "AggregateFieldNameM": "TotalValueM"
      }
    ],
    [
      {
        "GroupFieldName1": "Value11"
      },
      {
        "AggregateFieldName1": "TotalValue11",
        "AggregateFieldName2": "TotalValue12",
        ...,
        "AggregateFieldNameM": "TotalValue1M"
      }
    ],
    ...,
   [
      {
        "GroupFieldName1": "Value1",
        ...
        "GroupFieldNameN": "ValueN",
      },
      {
        "AggregateFieldName1": "TotalValue11",
        "AggregateFieldName2": "TotalValue12",
        ...,
        "AggregateFieldNameM": "TotalValue1M"
      }
   ],
   ...
  ]
}
```

```json
{
  "data": [
    {
      "GroupFieldName1": "Value11",
      "GroupFieldName2": "Value12",
       ...,
      "GroupFieldNameN": "Value1N",
      "AggregateFieldName1": "Value11",
      "AggregateFieldName1": "Value12",
       ...,
      "AggregateFieldNameM": "Value1M"
    },
    ...,
    {
      "GroupFieldName1": "ValueK1",
      "GroupFieldName2": "ValueK2",
       ...,
      "GroupFieldNameN": "ValueKN",
      "AggregateFieldName1": "ValueK1",
      "AggregateFieldName1": "ValueK2",
       ...,
      "AggregateFieldNameM": "ValueKM"
    }
  ],
  "summary": [
   [
      {
         
      },
      {
        "AggregateFieldName1": "TotalValue1",
        "AggregateFieldName2": "TotalValue2",
        ...,
        "AggregateFieldNameM": "TotalValueM"
      }
    ],
    [
      {
        "GroupFieldName1": "Value11"
      },
      {
        "AggregateFieldName1": "TotalValue11",
        "AggregateFieldName2": "TotalValue12",
        ...,
        "AggregateFieldNameM": "TotalValue1M"
      }
    ],
    ...,
   [
      {
        "GroupFieldName1": "Value1",
        ...
        "GroupFieldNameN": "ValueN",
      },
      {
        "AggregateFieldName1": "TotalValue11",
        "AggregateFieldName2": "TotalValue12",
        ...,
        "AggregateFieldNameM": "TotalValue1M"
      }
   ],
   ...
  ]
}
```


| Название | Значение | Описание |
| --- | --- | --- |
| data | Данные отчета | Линейные данные отчета (построчно), одна запись внутри блока соответствует одной строке в гриде iikoOffice |
| summary | Промежуточные и общие итоги по отчету | Список блоков, состоящих из двух структур.<br><ol style="margin: 10px 0px 0px; padding-left: 22px;"><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">В первой структуре - список полей, по которым собраны промежуточные итоги, в качестве элементов этой структуры представлены поля, которые используются для группировки. Количество элементов в структуре отличается и может быть: </span></span><ol style="padding-left: 22px;"><li><span style="font-size: 10pt;"><span style="line-height: 1.42857; font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">пустым - это значит, что во втором блоке представлены общие итоги по отчету</span></span></li><li><span style="font-size: 10pt;"><span style="line-height: 1.42857; font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">список полей группировки, по которым собраны промежуточные итоги. Список имеет длину от 1 до числа полей группировки. Поля добавляются к списку в порядке их следования в запросе.&#160;</span></span></li></ol></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">Во второй - собственно промежуточные итоги. В качестве элементов данной структуры представлены поля, которые используются для агрегации. Количество элементов этой структуры фиксировано и равно количеству полей для агрегации.</span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">При параметре запроса <em>summary = false (olap, olap_presetId). </em>&quot;summary&quot;: [ ] будет пустой. C <strong>Version (iiko) 5.3</strong></span> </span></li></ol> |

## 

## 

##
