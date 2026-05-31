* [Список преднастроенных не удаленных отчетов (конфигураций)](/articles/api-documentations/prednastroennye-olap-otchety-vv2/a/h2__1074633278)
* [Список преднастроенных не удаленных отчетов (конфигураций), отфильтрованных по типу OLAP-отчетов](/articles/api-documentations/prednastroennye-olap-otchety-vv2/a/h2__2011681203)
* [Параметры запроса](/articles/api-documentations/prednastroennye-olap-otchety-vv2/a/h3__998506674)
* [Получение отчета по сохраненной конфигурации (по ИД)](/articles/api-documentations/prednastroennye-olap-otchety-vv2/a/h2__1520457598)
* [Параметры запроса](/articles/api-documentations/prednastroennye-olap-otchety-vv2/a/h3__1602332892)
* [Пример запроса](/articles/api-documentations/prednastroennye-olap-otchety-vv2/a/h3_1387997121)
* [Тело ответа](/articles/api-documentations/prednastroennye-olap-otchety-vv2/a/id-ПреднастроенныеOLAP-отчеты-ResponseBody)

## Список преднастроенных не удаленных отчетов (конфигураций)

Версия iiko: 4.2

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/reports/olap/presets |
| --- | --- |

## Список преднастроенных не удаленных отчетов (конфигураций), отфильтрованных по типу OLAP-отчетов

Версия iiko: 4.2

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/reports/olap/presets/{presetType} |
| --- | --- |

### Параметры запроса

| Параметр | Описание |
| --- | --- |
| **presetType** | [**stock**, **sales**, **transactions**, **deliveries**]- типы OLAP-отчетов (контроль хранения остатков, продажи, проводки, доставка) |

## 

## Получение отчета по сохраненной конфигурации (по ИД)

Версия iiko: 4.2

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/reports/olap/byPresetId/{presetId} |
| --- | --- |

### Параметры запроса

| Параметр | Описание |
| --- | --- |
| presetId | UUID пресета (обязательный) |
| summary | Boolean. Вычислять итоговое значение. По умолчанию выставлен в true.<br><br>С Version (iiko) 5.3 |
| dateFrom | дата в формате YYYY-MM-DDThh:mm:ss (необязательный, включена в период) |
| dateTo | дата в формате YYYY-MM-DDThh:mm:ss (необязательный, не включена в период) |
| key | Токен |

Формат сохраненных конфигураций отчетов при обновлении iiko может измениться. Соответственно меняются поля возвращаемого отчета.

Чтобы получать отчет всегда в одном и том же формате, следует передавать полученную из **/v2/reports/olap/presets** конфигурацию в API OLAP-отчетов: **/v2/reports/olap**
Поля агрегации, учитывающие начальный остаток товара и денежный остаток (StartBalance.Amount, StartBalance.Money, FinalBalance.Amount, FinalBalance.Money) вычисляются суммированием всей таблицы проводок **за все время** работы системы (всей базы данных) без каких-либо оптимизаций. То есть, такой запрос может выполняться очень долго и замедлять работу сервера.
Если начальный остаток необходим, оставляйте в этом OLAP-запросе только те поля группировки, по которым он действительно необходим (как правило, это Store и Product.Name), и вызывайте такой запрос **как можно реже** и в **не рабочее** время.
В 5.2 добавлено API для быстрого получения остатков: Отчеты по балансам.

В 5.5 отчеты с остатками оптимизированы с использованием балансовых таблиц ATransactionSum, ATransactionBalance, при условии, что применяются группировки и фильтры по полям из этих таблиц, см. признак StartBalanceOptimizable в описании полей.

### Пример запроса

https://host:port/resto/api/v2/reports/olap/byPresetId/c80230c5-5d47-41d2-a055-367742db889d?key=5c2d45fd-5008-b18e-7f7f-cdc18a088cfd&dateFrom=2025-01-01&dateTo=2025-01-31

### Тело ответа


Код

```
[{
  "id" : "UUID",
   "name" : "Name",
  "reportType": "EnumValue",
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
,
...
...
...
]
```
