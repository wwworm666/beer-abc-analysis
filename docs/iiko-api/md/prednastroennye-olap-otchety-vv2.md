# Prednastroennye Olap Otchety Vv2

*Generated from PDF: prednastroennye-olap-otchety-vv2.pdf*

*Total pages: 3*

---


## Page 1

API Documentation Page1 of 3
1. Преднастроенные OLAP-
отчеты
Список преднастроенных не удаленных
отчетов (конфигураций)
Версия iiko: 4.2
https://host:port/resto/api/v2/reports/olap/presets
Список преднастроенных не удаленных отчетов
(конфигураций), отфильтрованных по типу OLAP-
отчетов
Версия iiko: 4.2
https://host:port/resto/api/v2/reports/olap/presets/{presetType}
Параметры запроса
Параметр Описание
[stock,sales,transactions,deliveries]-типыOLAP-
presetType отчетов(контрольхраненияостатков,продажи,
проводки,доставка)
Получение отчета по сохраненной
конфигурации (по ИД)
Версия iiko: 4.2
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |

|---|---|---|---|---|---|

|  | Параметр |  |  | Описание |  |

|  |  |  |  |  |  |

| presetType |  |  | [stock,sales,transactions,deliveries]-типыOLAP-
отчетов(контрольхраненияостатков,продажи,
проводки,доставка) |  |  |


---


## Page 2

API Documentation Page2 of 3
https://host:port/resto/api/v2/reports/olap/byPresetId/{presetId}
Параметры запроса
Параметр Описание
presetId UUIDпресета(обязательный)
Boolean.Вычислятьитоговоезначение.Поумолчаниювыставленвtrue.
summary
СVersion(iiko)5.3
dateFrom датавформатеYYYY-MM-DDThh:mm:ss(необязательный,включенавпериод)
dateTo датавформатеYYYY-MM-DDThh:mm:ss(необязательный,невключенавпериод)
key Токен
Формат сохраненных конфигураций отчетов при обновлении iiko может измениться. Соответственно
меняютсяполявозвращаемогоотчета.
Чтобы получать отчет всегда в одном и том же формате, следует передавать полученную из
/v2/reports/olap/presetsконфигурациювAPIOLAP-отчетов:/v2/reports/olap
Поля агрегации, учитывающие начальный остаток товара и денежный остаток (StartBalance.Amount,
StartBalance.Money, FinalBalance.Amount, FinalBalance.Money) вычисляются суммированием всей таблицы
проводок за все время работы системы (всей базы данных) без каких-либо оптимизаций. То есть, такой
запрос может выполняться очень долго и замедлять работу сервера.
Если начальный остаток необходим, оставляйте в этом OLAP-запросе только те поля группировки, по
которымондействительнонеобходим(какправило,этоStoreиProduct.Name),ивызывайтетакойзапроскак
можно реже и в не рабочее время.
В5.2добавленоAPIдлябыстрогополученияостатков:Отчетыпобалансам.
В 5.5 отчеты с остатками оптимизированы с использованием балансовых таблиц ATransactionSum,
ATransactionBalance, при условии, что применяются группировки и фильтры по полям из этих таблиц, см.
признакStartBalanceOptimizableвописанииполей.
Пример запроса
https://host:port/resto/api/v2/reports/olap/byPresetId/c80230c5-5d47-41d2-
a055-367742db889d?key=5c2d45fd-5008-b18e-7f7f-cdc18a088cfd&dateFrom=2025-01-
01&dateTo=2025-01-31
Тело ответа
CopyCode
Код
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |

|---|---|---|---|---|---|

|  | Параметр |  |  | Описание |  |

|  |  |  |  |  |  |

| presetId |  |  | UUIDпресета(обязательный) |  |  |

| summary |  |  | Boolean.Вычислятьитоговоезначение.Поумолчаниювыставленвtrue.
СVersion(iiko)5.3 |  |  |

| dateFrom |  |  | датавформатеYYYY-MM-DDThh:mm:ss(необязательный,включенавпериод) |  |  |

| dateTo |  |  | датавформатеYYYY-MM-DDThh:mm:ss(необязательный,невключенавпериод) |  |  |

| key |  |  | Токен |  |  |



### Table:

| https://host:port/resto/api/v2/reports/olap/byPresetId/c80230c5-5d47-41d2- |

|---|

| a055-367742db889d?key=5c2d45fd-5008-b18e-7f7f-cdc18a088cfd&dateFrom=2025-01- |

| 01&dateTo=2025-01-31 |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | Код |  |

|  |  |  |


---


## Page 3

API Documentation Page3 of 3
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
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | [{ |

|  | "id" : "UUID", |

|  | "name" : "Name", |

|  | "reportType": "EnumValue", |

|  | "groupByRowFields": [ |

|  | "groupByRowFieldName1", |

|  | "groupByRowFieldName2", |

|  | ..., |

|  | "groupByRowFieldNameN" |

|  | ], |

|  | "groupByColFields": [ |

|  | "groupByColFieldName1", |

|  | "groupByColFieldName2", |

|  | ..., |

|  | "groupByColFieldNameL" |

|  | ], |

|  | "aggregateFields": [ |

|  | "AggregateFieldName1", |

|  | "AggregateFieldName2", |

|  | ..., |

|  | "AggregateFieldNameM" |

|  | ], |

|  | "filters": { |

|  | filter1, |

|  | filter2, |

|  | ... |

|  | filterK |

|  | } |

|  | } |

|  | , |

|  | ... |

|  | ... |

|  | ... |

|  | ] |

|  |  |


---
