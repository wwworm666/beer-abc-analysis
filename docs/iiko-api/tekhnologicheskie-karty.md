* [Получение всех технологических карт (getAll)](/articles/api-documentations/tekhnologicheskie-karty/a/v2.APIтехкарт-Получениевсехтехнологическихкарт%28getAll%29)
* [Параметры запроса](/articles/api-documentations/tekhnologicheskie-karty/a/h3_1827755295)
* [Что в ответе](/articles/api-documentations/tekhnologicheskie-karty/a/h3_501454233)
* [Примечание](/articles/api-documentations/tekhnologicheskie-karty/a/h3_742091085)
* [Результат (ChartResultDto с полным списком техкарт)](/articles/api-documentations/tekhnologicheskie-karty/a/h3__663899359)
* [Пример запроса и результат](/articles/api-documentations/tekhnologicheskie-karty/a/h3_1561844723)
* [Получение обновления технологических карт (getAllUpdate)](/articles/api-documentations/tekhnologicheskie-karty/a/h2_873139701)
* [Параметры запроса](/articles/api-documentations/tekhnologicheskie-karty/a/h3__670042136)
* [Что в ответе](/articles/api-documentations/tekhnologicheskie-karty/a/h3__1225883157)
* [Результат (ChartResultDto с обновлением техкарт)](/articles/api-documentations/tekhnologicheskie-karty/a/h3_228416616)
* [Пример запроса и результат](/articles/api-documentations/tekhnologicheskie-karty/a/h3_581831634)
* [Получение дерева актуальных технологических карт для элемента номенклатуры (getTree)](/articles/api-documentations/tekhnologicheskie-karty/a/h2_725635009)
* [Параметры запроса](/articles/api-documentations/tekhnologicheskie-karty/a/h3_989587153)
* [Что в ответе](/articles/api-documentations/tekhnologicheskie-karty/a/h3__26539110)
* [Результат (ChartResultDto с деревом техкарт)](/articles/api-documentations/tekhnologicheskie-karty/a/h3__342991352)
* [Пример запроса и результат](/articles/api-documentations/tekhnologicheskie-karty/a/h3__524461335)
* [Получение исходной технологической карты для элемента номенклатуры (getAssembled)](/articles/api-documentations/tekhnologicheskie-karty/a/h2__1245203295)
* [Параметры запроса](/articles/api-documentations/tekhnologicheskie-karty/a/h3_830852681)
* [Что в ответе](/articles/api-documentations/tekhnologicheskie-karty/a/h3__1372327188)
* [Пример запроса и результат](/articles/api-documentations/tekhnologicheskie-karty/a/h3_812065382)
* [Получение технологической карты элемента номенклатуры, разложенной до конечных ингредиентов (getPrepared)](/articles/api-documentations/tekhnologicheskie-karty/a/h2_1837166759)
* [Параметры запроса](/articles/api-documentations/tekhnologicheskie-karty/a/h3__250965803)
* [Пример запроса и результат](/articles/api-documentations/tekhnologicheskie-karty/a/h3__756274422)
* [Получение технологической карты по id (byId)](/articles/api-documentations/tekhnologicheskie-karty/a/v2.APIтехкарт-Получениетехнологическойкартыпоid%28byId%29.)
* [Что в ответе](/articles/api-documentations/tekhnologicheskie-karty/a/h3_519610608)
* [Получение истории техкарт по продукту (getHistory)](/articles/api-documentations/tekhnologicheskie-karty/a/v2.APIтехкарт-Получениеисториитехкартпопродукту%28getHistory%29)
* [Что в ответе](/articles/api-documentations/tekhnologicheskie-karty/a/h3_1620570402)
* [Пример запроса и результата](/articles/api-documentations/tekhnologicheskie-karty/a/v2.APIтехкарт-Пример.1)
* [Создание технологической карты](/articles/api-documentations/tekhnologicheskie-karty/a/v2.APIтехкарт-Созданиетехнологическойкарты)
* [Что в ответе](/articles/api-documentations/tekhnologicheskie-karty/a/h3_1971557112)
* [Удаление технологической карты](/articles/api-documentations/tekhnologicheskie-karty/a/v2.APIтехкарт-Удалениетехнологическойкарты)
* [Тело запроса](/articles/api-documentations/tekhnologicheskie-karty/a/h3_1150399349)
* [Приложение: структура StoreSpecification](/articles/api-documentations/tekhnologicheskie-karty/a/v2.APIтехкарт-Приложение:структураStoreSpecification)

**Технологические карты** (рецепты) в iiko строго привязаны к элементам номенклатуры (блюдам, модификаторам, заготовкам) и датам: на каждый учетный день элементу номенклатуры может быть сопоставлено не более одной технологической карты. Единственная сопоставленная карта должна задавать метод списания (целиком/по ингредиентам) и состав + количество ингредиентов для всех действующих и удаленных подразделений, размеров блюд.

Ингредиентом блюда, модификатора, заготовки может быть заготовка, имеющая свою собственную технологическую карту. Таким образом, техкарты образуют деревья.
 
[Статья](/articles/iikooffice-8-9/topic-3090)по настройке технологических карт.
 
## Получение всех технологических карт (getAll)

Версия iiko: 6.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/assemblyCharts/getAll?dateFrom={dateFrom}&dateTo={dateTo}&includeDeletedProducts=true&includePreparedCharts=false |
| --- | --- |

### Параметры запроса

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| dateFrom | yyyy-MM-dd | Учетный день, начиная с которого требуются техкарты. Обязательный параметр. |
| dateTo | yyyy-MM-dd | Учетный день, начиная с которого техкарты не требуются. Если не задан, возвращаются все будущие техкарты. |
| includeDeletedProducts | Boolean | Включать ли в результат техкарты для удаленных блюд. По умолчанию true. |
| includePreparedCharts | Boolean | Включать ли в результат техкарты, разложенные до конечных ингредиентов. По умолчанию false (их может быть много). |

### Что в ответе

Списки актуальных и действующих технологических карт для всей номенклатуры, пересекающих своим интервалом действия заданный интервал (json-структура ChartResultDto).

### **Примечание**

Заданный метод списания для технологической карты влияет на результат ответа при выбранном includePreparedCharts = true:

* если метод списания "Списывать готовое блюдо", то в preparedCharts возвращается элемент списания (например, полуфабрикат в составе заготовки).
* если метод списания "Списывать ингредиенты", то в preparedCharts возвращаются ингредиенты элемента списания (например, ингредиенты полуфабриката).

###  Результат (ChartResultDto с полным списком техкарт) 

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| knownRevision | Integer | Ревизия сервера, на которую валиден ответ.<br> <br>Гарантируется, что в базе не может произойти изменений, помеченных ревизией меньше, чем данная, поэтому клиент может вызывать метод assemblyCharts/getAllUpdate с этой ревизией, чтобы получить только изменившиеся технологические карты.<br> <br>Используется в assemblyCharts/getAll и assemblyCharts/getAllUpdate. В остальных методах, возвращающих урезанные данные (непригодные для getAllUpdate) всегда равно -1. |
| assemblyCharts | AssemblyChartDto | Список исходных технологических карт, интервал действия которых пересекает запрошенный интервал. |
| preparedCharts | PreparedChartDto | Список разложенных до ингредиентов технологических карт, интервал действия которых пересекает запрошенный интервал. |
| deletedAssemblyChartIds | Список UUID | Всегда null (клиент должен удалить все ранее закешированные техкарты). |
| deletedPreparedChartIds | Список UUID | Всегда null (клиент должен удалить все ранее закешированные техкарты). |

### Пример запроса и результат

https://localhost:8080/resto/api/v2/assemblyCharts/getAll?dateFrom=2010-01-01&dateTo=2010-01-02

**ChartResultDto (список всех техкарт)**


```json
{
  "knownRevision" : -1,
  "assemblyCharts" : [ ],
  "preparedCharts" : [ ]
  } ],
  "deletedAssemblyChartIds" : null,
  "deletedPreparedChartIds" : null
}
```

```json
{
  "knownRevision" : -1,
  "assemblyCharts" : [ ],
  "preparedCharts" : [ ]
  } ],
  "deletedAssemblyChartIds" : null,
  "deletedPreparedChartIds" : null
}
```


##  Получение обновления технологических карт (getAllUpdate)
 
Версия iiko: 6.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/assemblyCharts/getAllUpdate?knownRevision={knownRevision}&dateFrom={dateFrom}&dateTo={dateTo}&includeDeletedProducts=true&includePreparedCharts=false |
| --- | --- |

### Параметры запроса 

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| knownRevision | Integer | Значение поля knownRevision из предыдущего результата вызова getAll или getAllUpdate с теми же параметрами. |
| dateFrom | yyyy-MM-dd | Учетный день, начиная с которого требуются техкарты. Обязательный параметр. |
| dateTo | yyyy-MM-dd | Учетный день, начиная с которого техкарты не требуются. Если не задан, возвращаются все техкарты, включая будущие. |
| includeDeletedProducts | Boolean | Включать ли в результат техкарты для удаленных блюд. По умолчанию true. Получение обновлений не поддерживается для false. |
| includePreparedCharts | Boolean | Включать ли в результат техкарты, разложенные до конечных ингредиентов. По умолчанию false (их может быть много). |

### Что в ответе

Списки новых и изменившихся актуальных и действующих технологических карт для всей номенклатуры, пересекающих своим интервалом действия заданный интервал (json-структура ChartResultDto).

Примечание. По состоянию на 6.0 получение обновлений полностью работает только в iikoChain.

### Результат (ChartResultDto с обновлением техкарт) 

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| knownRevision | Integer | Ревизия сервера, на которую валиден ответ.<br> <br>Гарантируется, что в базе не может произойти изменений, помеченных ревизией меньше, чем данная, поэтому клиент может вызывать метод assemblyCharts/getAllUpdate с этой ревизией, чтобы получить только изменившиеся технологические карты.<br> <br>Используется в assemblyCharts/getAll и assemblyCharts/getAllUpdate. В остальных методах, возвращающих урезанные данные (непригодные для getAllUpdate) всегда равно -1. |
| assemblyCharts | AssemblyChartDto | Список новых и изменившихся исходных технологических карт, интервал действия которых пересекает запрошенный интервал. |
| preparedCharts | PreparedChartDto | Список новых и изменившихся разложенных до ингредиентов технологических карт, интервал действия которых пересекает запрошенный интервал. |
| deletedAssemblyChartIds | Список UUID | Список UUID исходных технологических карт, удаленных начиная с указанной ревизии, либо null, если они не запрашивались. Клиент должен забыть перечисленные техкарты и начать считать актуальными те, что действовали на даты, предшествовавшие (по dateFrom/dateTo) удаленным. Если предшествующей техкарты нет в кеше клиента, следует считать, что ранее были получены не все данные и перезапрашивать полный список техкарт (getAll).<br> <br>*6.0: не работает на iikoRMS (не сообщает об удалениях, реплицированных с iikoChain)* |
| deletedPreparedChartIds | Список UUID | Список UUID разложенных технологических карт, удаленных начиная с указанной ревизии, либо null, если они не запрашивались. |

### Пример запроса и результат

https://localhost:8080/resto/api/v2/assemblyCharts/getAllUpdate?knownRevision=999999999&dateFrom=2010-01-01&dateTo=2010-01-02

**ChartResultDto (невозможно получить обновление техкарт)**


```json
{
  "knownRevision" : -1,
  "assemblyCharts" : null,
  "preparedCharts" : null,
  "deletedAssemblyChartIds" : null,
  "deletedPreparedChartIds" : null
}
```

```json
{
  "knownRevision" : -1,
  "assemblyCharts" : null,
  "preparedCharts" : null,
  "deletedAssemblyChartIds" : null,
  "deletedPreparedChartIds" : null
}
```


## Получение дерева актуальных технологических карт для элемента номенклатуры (getTree) 

Версия iiko: 6.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/assemblyCharts/getTree?date={date}&productId={productId}&departmentId={departmentId} |
| --- | --- |

### Параметры запроса

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| departmentId | UUID | UUID подразделения. Если не указан, возвращается технологическая карта со строками, действующими в любом из подразделений, клиент должен сам анализировать применимость (поле items.storeSpecification). |
| productId | UUID | UUID элемента номенклатуры (блюда, модификатора, заготовки) (обязательно) |
| date | yyyy-MM-dd | Учетный день |

### Что в ответе

Дерево актуальных технологических карт для элемента номенклатуры и действующая разложенная до конечных ингредиентов его технологическая карта, в том числе с учетом "раздельных тех.карт по размерам блюда" (json-структура ChartResultDto).

### Результат (ChartResultDto с деревом техкарт) 

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| knownRevision | Integer | Всегда -1, т.к. обновление дерева техкарт невозможно вычислить по одной ревизии.<br> <br>Ревизия сервера, на которую валиден ответ.<br> <br>Гарантируется, что в базе не может произойти изменений, помеченных ревизией меньше, чем данная, поэтому клиент может вызывать метод assemblyCharts/getAllUpdate с этой ревизией, чтобы получить только изменившиеся технологические карты.<br> <br>Используется в assemblyCharts/getAll и assemblyCharts/getAllUpdate. В остальных методах всегда возвращается -1. |
| assemblyCharts | AssemblyChartDto | Дерево исходных технологических карт для заданного элемента номенклатуры.<br> <br>То есть, техкарта запрошенного продукта и техкарты всех заготовок, входящих в него, рекурсивно.<br> <br>Если фильтр departmentId не был задан, часть строк некоторых техкарт (и техкарты целиком) могут действовать не во всех подразделениях, клиент должен сам анализировать поля storeSpecification.<br> <br>Если фильтр departmentId был задан, фильтры storeSpecification будут урезаны до одного указанного подразделения. |
| preparedCharts | PreparedChartDto | Технологическая карта для корневого (запрошенного) элемента номенклатуры, разложенная до конечных ингредиентов, списываемых со склада. |
| deletedAssemblyChartIds | Список UUID | Всегда null |
| deletedPreparedChartIds | Список UUID | Всегда null |

###  Пример запроса и результат

####  Запрос

https://localhost:8080/resto/api/v2/assemblyCharts/getTree?date=2019-01-01&productId=db54eef3-8db9-4ede-93bc-c849b9d9b33d&departmentId=bc367d9e-4876-4bb1-9b31-2d332387bc5b
 [+] [ChartResultDto (дерево техкарт)](javascript:void%280%29)
 [-] [ChartResultDto (дерево техкарт)](javascript:void%280%29)
 
```
 %%CH%PRE4%%%%CH%PRE5%%
```


##  Получение исходной технологической карты для элемента номенклатуры (getAssembled)
 
Версия iiko: 6.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/assemblyCharts/getAssembled?date={date}&productId={productId}&departmentId={departmentId} |
| --- | --- |

### Параметры запроса

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| date | yyyy-MM-dd | Учетный день |
| productId | UUID | UUID элемента номенклатуры (блюда, модификатора, заготовки) (обязательно) |
| departmentId | UUID | UUID подразделения. Если не указан, возвращается технологическая карта со строками, действующими в любом из подразделений, клиент должен сам анализировать применимость (поле items.storeSpecification). |

### Что в ответе

Первый уровень актуальной технологической карты (json-структура ChartResultDto, содержащая не более одного элемента в списке assemblyCharts: AssemblyChartDto)
 [+] [Результат (AssemblyChartDto)](javascript:void%280%29)
 [-] [Результат (AssemblyChartDto)](javascript:void%280%29)
 
```
 
```
 

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| id | UUID | UUID технологической карты. |
| assembledProductId | UUID | UUID приготавливаемого элемента номенклатуры (блюда, модификатора, заготовки) (обязательно). |
| dateFrom | yyyy-MM-dd | Учетный день начала действия технологической карты: все списания assembledProductId, начиная с 00:00 этого дня, проводятся по данной техкарте. |
| dateTo | yyyy-MM-dd | Учетный день прекращения действия технологической карты: начиная с 00:00 этого дня списания проводятся по СЛЕДУЮЩЕЙ техкарте.<br> <br>Срок действия техкарты не может быть искусственно ограничен (как у прейскурантов), последняя техкарта действует бессрочно (null). |
| assembledAmount | BigDecimal | Норма закладки приготавливаемого блюда. |
| effectiveDirectWriteoffStoreSpecification | Структура StoreSpecification | Список UUID подразделений (Department), где элемент номенклатуры списывается целиком (а не по ингредиентам).<br> <br>Описание см. ниже "Структура StoreSpecification". |
| productSizeAssemblyStrategy | Enum: <br>"COMMON", "SPECIFIC" | Способ учета размеров списываемых блюд:<br> <br>COMMON — технологическая карта содержит строки для продуктов и подразделений; рассчитанное по текхарте списываемое количество умножается на коэффициент списания, настроенный в карточке товара и зафиксированный в документе (акте реализации, списания, и т.п.).<br> <br>SPECIFIC — "Отдельные тех.карты для размеров" — технологическая карта содержит строки для продуктов, размеров приготавливаемого блюда и подразделений; коэффициенты списания, зафиксированные в документах, не учитываются. Icon<br><br><br><br>**Внимание:**<br> <br>Смешивать техкарты разных типов в иерархии техкарт одного элемента номенклатуры не рекомендуется.<br> <br>Во-первых, техкарта может содержать строки для обоих способов списания (для COMMON без указания размера, для SPECIFIC с указанием размера), даже если их не видно в iikoOffice. Какие строки действуют, определяется по способу учета размера корневого блюда, а не каждой промежуточной заготовки. Из-за этого одна и та же заготовка может списываться по-разному в разных блюдах.<br> <br>Во-вторых, в случае, когда техкарта не содержит лишних данных для "не своего" типа списания, результат ее умножения на техкарту другого типа равен нулю (никакое списание не происходит). |
| items | Массив AssemblyChartItemDto | | Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| id | UUID | UUID строки |<br>| sortWeight | Double | Порядок отображения строк в интерфейсе iikoOffice. Обычно целое число. Могут встречаться строки с одинаковым номером. |<br>| productId | UUID | UUID списываемого ингредиента (товара, заготовки). |<br>| productSizeSpecification | UUID | UUID размера блюда. Null для строк "общей" (COMMON) техкарты.<br> <br>"Раздельные" (SPECIFIC) техкарты могут содержать строки для удаленных размеров и размеров из предыдущей сопоставленной блюду шкалы размеров (для обеспечения переходного периода при смене шкалы). |<br>| storeSpecification | Структура StoreSpecification | Список подразделений, в списаниях со складов которых применяется данная строка техкарты.<br> <br>Описание см. ниже "Структура StoreSpecification". |<br>| amountIn | BigDecimal | Брутто (в основных единицах измерения ингредиента). Именно это поле участвует в расчете списаний. <br>См. ниже "PreparedChartDto.items.amount". |<br>| amountMiddle | BigDecimal | Нетто (в основных единицах измерения ингредиента, а **НЕ** в кг, отображаемых в iikoOffice). |<br>| amountOut | BigDecimal | Выход готового продукта (в основных единицах измерения ингредиента, а **НЕ** в кг, отображаемых в iikoOffice). |<br>| amountIn1 | BigDecimal | Акт проработки/Проработка 1/Брутто (в кг). |<br>| amountOut1 | BigDecimal | Акт проработки/Проработка 1/Нетто (в кг). |<br>| amountIn2 | BigDecimal | Акт проработки/Проработка 2/Брутто (в кг). |<br>| amountOut2 | BigDecimal | Акт проработки/Проработка 2/Нетто (в кг). |<br>| amountIn3 | BigDecimal | Акт проработки/Проработка 3/Брутто (в кг). |<br>| amountOut3 | BigDecimal | Акт проработки/Проработка 3/Нетто (в кг). |<br>| packageCount | BigDecimal | Часть от общей фасовки, которая входит в техкарту |<br>| packageTypeId | UUID | UUID фасовки ингредиента (product.Container) |<br>|  |  | **Обратите внимание**: в серверных расчетах и в выдаче API используются и передаются НЕ ТЕ значения, что отображаются в iikoOffice!<br><br>Все расчеты в iiko ведутся в "единицах измерения товара". Однако, помимо названия единицы измерения в карточке товара на вкладке "Единицы измерения" можно настроить вторичные параметры: фасовки, "вес единицы измерения" (unitWeight, если в качестве единица измерения выбран не килограмм). Так как эти настройки можно поменять в любой момент, в документах и технологических картах колонки "Количество в фасовке товара", "Количество в килограммах" всегда рассчитываются на лету. | |
| --- | --- | --- |
| technologyDescription | Text | Комментарий "Технология приготовления" |
| description | String(2000) | Комментарий "Описание" |
| appearance | String(2000) | Комментарий "Требования к оформлению, подаче и реализации" |
| organoleptic | String(2000) | Комментарий "Органолептические показатели качества" |
| outputComment | String(2000) | Суммарный выход |
| productWriteoffStrategy | "ASSEMBLE", "DIRECT" | Метод списания продукта:<br><br>ASSEMBLE - Списывать ингредиенты. Этот способ обычно используется для полуфабрикатов и блюд, которые не нужно учитывать на складе.<br><br>DIRECT - Списывать сам продукт. Этот способ обычно используется для товаров и полуфабрикатов, остаток которых нужно учитывать на складе. |

###
 
### Пример запроса и результат

#### Запрос

https://localhost:8080/resto/api/v2/assemblyCharts/getAssembled?date=2019-01-01&productId=db54eef3-8db9-4ede-93bc-c849b9d9b33d&departmentId=bc367d9e-4876-4bb1-9b31-2d332387bc5b
 [+] [AssemblyChartDto](javascript:void%280%29)
 [-] [AssemblyChartDto](javascript:void%280%29)
 
```
 %%CH%PRE6%%%%CH%PRE7%%
```


##  Получение технологической карты элемента номенклатуры, разложенной до конечных ингредиентов (getPrepared)
 
Версия iiko: 6.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/assemblyCharts/getPrepared?date={date}&productId={productId}&departmentId={departmentId} |
| --- | --- |

### Параметры запроса
 Параметр  Тип, формат  Описание  date  yyyy-MM-dd  Учетный день  productId  UUID  UUID элемента номенклатуры (блюда, модификатора, заготовки) (обязательно)  departmentId  UUID  UUID подразделения. Если не указан, возвращается технологическая карта со строками, действующими в любом из подразделений, клиент должен сам анализировать применимость (поле items.storeSpecification).
[+] [Результат (PreparedChartDto)](javascript:void%280%29)
 [-] [Результат (PreparedChartDto)](javascript:void%280%29)
 
```


```
 
###  

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| id | UUID | UUID технологической карты. |
| assembledProductId | UUID | UUID приготавливаемого элемента номенклатуры (блюда, модификатора, заготовки) (обязательно). |
| dateFrom | yyyy-MM-dd | Учетный день начала действия технологической карты: все списания assembledProductId, начиная с 00:00 этого дня, проводятся по данной техкарте. |
| dateTo | yyyy-MM-dd | Учетный день прекращения действия технологической карты: начиная с 00:00 этого дня списания проводятся по СЛЕДУЮЩЕЙ техкарте.<br> <br>Срок действия техкарты не может быть искусственно ограничен (как у прейскурантов), последняя техкарта действует бессрочно (null).<br> <br>В конечной техкарте норма закладки приготавливаемого блюда всегда равна **одной** основной единице его измерения. |
| effectiveDirectWriteoffStoreSpecification | Структура StoreSpecification | Список UUID подразделений (Department), где элемент номенклатуры списывается целиком.<br> <br>См. AssemblyChartDto.effectiveDirectWriteoffStoreSpecification |
| productSizeAssemblyStrategy | Enum: <br>"COMMON", "SPECIFIC" | Способ учета размеров списываемых блюд.<br> <br>См. AssemblyChartDto.productSizeAssemblyStrategy. |
| items | Массив PreparedChartItemDto | | Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| id | UUID | UUID строки |<br>| sortWeight | Double | Порядок отображения строк в интерфейсе iikoOffice. Обычно целое число. Могут встречаться строки с одинаковым номером. |<br>| productId | UUID | UUID списываемого ингредиента (товара, заготовки). |<br>| productSizeSpecification | UUID | UUID размера блюда. Null для строк "общей" (COMMON) техкарты.<br> <br>"Раздельные" (SPECIFIC) техкарты могут содержать строки для удаленных размеров и размеров из предыдущей сопоставленной блюду шкалы размеров (для обеспечения переходного периода при смене шкалы). |<br>| storeSpecification | Структура StoreSpecification | Список подразделений, в списаниях со складов которых применяется данная строка техкарты.<br> <br>См. AssemblyChartDto.storeSpecification |<br>| amount | BigDecimal | Количество списываемого ингредиента в основных единицах его измерения для нормы закладки = 1. <br>Нижеприведенная формула имеет справочный характер (не учитывает способ учета размеров блюд и размеры блюд, может содержать неточности; "разложенную до ингредиентов" техкарту рекомендуется запрашивать явно, а не рассчитывать самостоятельно):<br> <br>`amount = ROUND(PRODUCT(baseAmount), 3) baseAmount = ROUND(amountIn / assembledAmount, 4), где`<br><ul> <li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;"> baseAmount — брутто для нормы закладки = 1 (все в основных единицах измерения) для каждой исходной техкарты; </span></li> <li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">PRODUCT — перемножение с округлением до 32 знаков после запятой; </span></li> <li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">ROUND — округление до указанного числа знаков. </span></li> </ul> <br>Количество списываемого ингредиента для конкретного документа рассчитывается так (точная формула):<br> <br>`writeoffAmount = ROUND( amount * dishAmount * writeoffFactor, 9), где`<br><ul> <li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;"> amount — количество списываемого ингредиента для нормы закладки = 1, расcчитанное выше; </span></li> <li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">dishAmount — количество списываемого/приготавливаемого блюда из документа (акта списания, реализации, расходной накладной и т.п., три знака после запятой); </span></li> <li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">writeoffFactor — коэффициент списания, зафиксированный в документе (три знака после запятой). </span></li> </ul> | |
| --- | --- | --- |

###
 
### Пример запроса и результат

#### Запрос

https://localhost:8080/resto/api/v2/assemblyCharts/getPrepared?date=2019-01-01&productId=db54eef3-8db9-4ede-93bc-c849b9d9b33d&departmentId=bc367d9e-4876-4bb1-9b31-2d332387bc5b

**PreparedChartDto**


```json
{
  "knownRevision" : -1,
  "assemblyCharts" : null,
  "preparedCharts" : [ {
    "id" : "2ee10f3d-664c-c033-0161-422c7d010f68",
    "assembledProductId" : "a59c04b9-7f27-4773-8f6e-42b411f24941",
    "dateFrom" : "2018-01-29",
    "dateTo" : null,
    "effectiveDirectWriteoffStoreSpecification" : {
      "departments" : [ ],
      "inverse" : false
    },
    "productSizeAssemblyStrategy" : "COMMON",
    "items" : [ {
      "id" : "2ee10f3d-664c-c033-0161-422c7d010f69",
      "sortWeight" : 0.0,
      "productId" : "88cc2fe9-b3ff-4abb-a880-d2f2ba740461",
      "productSizeSpecification" : null,
      "storeSpecification" : null,
      "amount" : 0.001
    } ]
  } ],
  "deletedAssemblyChartIds" : null,
  "deletedPreparedChartIds" : null
}
```

```json
{
  "knownRevision" : -1,
  "assemblyCharts" : null,
  "preparedCharts" : [ {
    "id" : "2ee10f3d-664c-c033-0161-422c7d010f68",
    "assembledProductId" : "a59c04b9-7f27-4773-8f6e-42b411f24941",
    "dateFrom" : "2018-01-29",
    "dateTo" : null,
    "effectiveDirectWriteoffStoreSpecification" : {
      "departments" : [ ],
      "inverse" : false
    },
    "productSizeAssemblyStrategy" : "COMMON",
    "items" : [ {
      "id" : "2ee10f3d-664c-c033-0161-422c7d010f69",
      "sortWeight" : 0.0,
      "productId" : "88cc2fe9-b3ff-4abb-a880-d2f2ba740461",
      "productSizeSpecification" : null,
      "storeSpecification" : null,
      "amount" : 0.001
    } ]
  } ],
  "deletedAssemblyChartIds" : null,
  "deletedPreparedChartIds" : null
}
```


## Получение технологической карты по id (byId)

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/assemblyCharts/byId |
| --- | --- |

**Параметры запроса**

| Параметр | Тип | Обязательный | Описание |
| --- | --- | --- | --- |
| id | UUID | да | UUID технологической карты |

### Что в ответе

Технологическая карта

### Пример запроса и результата

#### Запрос

https://localhost:9080/resto/api/v2/assemblyCharts/byId?id=B86DA805-9512-44A7-85CA-5DE94272CE07
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE10%%%%CH%PRE11%%
```


## Получение истории техкарт по продукту (getHistory)

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/assemblyCharts/getHistory |
| --- | --- |

**Параметры запроса**

| Параметр | Тип | Обязательный | Описание |
| --- | --- | --- | --- |
| productId | UUID | да | UUID приготавливаемого элемента номенклатуры (блюда, модификатора, заготовки) |
| departmentId | UUID | да | UUID подразделения. Если не указан, возвращается технологическая карта со строками, действующими в любом из подразделений. |

### Что в ответе

Список всех тех.карт приготавливаемого элемента номенклатуры.

### Пример запроса и результата

#### Запрос

https://localhost:9080/resto/api/v2/assemblyCharts/getHistory?productId=A00A470C-6CC9-4B7F-835F-393E41AF8FCF
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE12%%%%CH%PRE13%%
```

 
## Создание технологической карты

Версия iiko: 6.4

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/assemblyCharts/save |
| --- | --- |

 [+] [Тело запроса](javascript:void%280%29)
 [-] [Тело запроса](javascript:void%280%29)
 | Поле | Тип, формат | Описание |
| --- | --- | --- |
| assembledProductId | UUID | UUID приготавливаемого элемента номенклатуры (блюда, модификатора, заготовки) (обязательно). |
| dateFrom | yyyy-MM-dd | Учетный день начала действия технологической карты: все списания assembledProductId, начиная с 00:00 этого дня, проводятся по данной техкарте. |
| dateTo | yyyy-MM-dd | Учетный день прекращения действия технологической карты: начиная с 00:00 этого дня списания проводятся по СЛЕДУЮЩЕЙ техкарте.<br><br>Срок действия техкарты не может быть искусственно ограничен (как у прейскурантов), последняя техкарта действует бессрочно (null). |
| assembledAmount | BigDecimal | Норма закладки приготавливаемого блюда. |
| productWriteoffStrategy | "ASSEMBLE", "DIRECT" | Метод списания продукта:<br><br>ASSEMBLE - Списывать ингредиенты. Этот способ обычно используется для полуфабрикатов и блюд, которые не нужно учитывать на складе.<br><br>DIRECT - Списывать сам продукт. Этот способ обычно используется для товаров и полуфабрикатов, остаток которых нужно учитывать на складе. |
| effectiveDirectWriteoffStoreSpecification | StoreSpecification | Список UUID подразделений (Department), где элемент номенклатуры списывается целиком (а не по ингредиентам). |
| productSizeAssemblyStrategy | "COMMON", "SPECIFIC" | Способ учета размеров списываемых блюд:<br><br>COMMON — технологическая карта содержит строки для продуктов и подразделений; рассчитанное по текхарте списываемое количество умножается на коэффициент списания, настроенный в карточке товара и зафиксированный в документе (акте реализации, списания, и т.п.).<br><br>SPECIFIC — "Отдельные тех.карты для размеров" — технологическая карта содержит строки для продуктов, размеров приготавливаемого блюда и подразделений; коэффициенты списания, зафиксированные в документах, не учитываются. |
| items | List&lt;AssemblyChartItemDto&gt; | | Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| sortWeight | Double | Порядок отображения строк в интерфейсе iikoOffice. Целое число. |<br>| productId | UUID | UUID списываемого ингредиента (товара, заготовки). |<br>| productSizeSpecification | UUID | UUID размера блюда. Null для строк "общей" (COMMON) техкарты.<br><br>"Раздельные" (SPECIFIC) техкарты могут содержать строки для удаленных размеров и размеров из предыдущей сопоставленной блюду шкалы размеров (для обеспечения переходного периода при смене шкалы). |<br>| storeSpecification | Структура StoreSpecification | Список подразделений, в списаниях со складов которых применяется данная строка техкарты.<br><br>Описание см. ниже "Структура StoreSpecification". |<br>| amountIn | BigDecimal | Брутто (в основных единицах измерения ингредиента). Именно это поле участвует в расчете списаний.<br>См. ниже "PreparedChartDto.items.amount". |<br>| amountMiddle | BigDecimal | Нетто (в основных единицах измерения ингредиента, а **НЕ** в кг, отображаемых в iikoOffice). |<br>| amountOut | BigDecimal | Выход готового продукта (в основных единицах измерения ингредиента, а **НЕ** в кг, отображаемых в iikoOffice). |<br>| amountIn1 | BigDecimal | Акт проработки/Проработка 1/Брутто (в кг). |<br>| amountOut1 | BigDecimal | Акт проработки/Проработка 1/Нетто (в кг). |<br>| amountIn2 | BigDecimal | Акт проработки/Проработка 2/Брутто (в кг). |<br>| amountOut2 | BigDecimal | Акт проработки/Проработка 2/Нетто (в кг). |<br>| amountIn3 | BigDecimal | Акт проработки/Проработка 3/Брутто (в кг). |<br>| amountOut3 | BigDecimal | Акт проработки/Проработка 3/Нетто (в кг). |<br>| packageTypeId | UUID | UUID фасовки ингредиента (product.Container) | |
| --- | --- | --- |
| technologyDescription | String | Комментарий "Технология приготовления" |
| description | String | Комментарий "Описание" |
| appearance | String | Комментарий "Требования к оформлению и реализации" |
| organoleptic | String | Комментарий "Органолептические показатели качества" |
| outputComment | String | Суммарный выход |
 
**Пример Body**

**
```xml
{
    "assembledProductId": "31e6155c-e842-448f-8266-1d05eb8e977a",
    "dateFrom": "2019-04-01",
    "dateTo": null,
    "assembledAmount": 2,
    "productWriteoffStrategy": "ASSEMBLE",
    "effectiveDirectWriteoffStoreSpecification": {
        "departments": [],
        "inverse": false
    },
    "productSizeAssemblyStrategy": "COMMON",
    "items": [
        {
            "sortWeight": 0,
            "productId": "56ca36c8-eb11-4f0a-802c-f96d0ce68e27",
            "productSizeSpecification": null,
            "storeSpecification": null,
            "amountIn": 0.4,
            "amountMiddle": 0.36,
            "amountOut": 0.36,
            "amountIn1": 0,
            "amountOut1": 0,
            "amountIn2": 0,
            "amountOut2": 0,
            "amountIn3": 0,
            "amountOut3": 0,
            "packageTypeId": null
        }
    ],
    "technologyDescription": "",
    "description": "",
    "appearance": "",
    "organoleptic": "",
    "outputComment": ""
}
```

```xml
{
    "assembledProductId": "31e6155c-e842-448f-8266-1d05eb8e977a",
    "dateFrom": "2019-04-01",
    "dateTo": null,
    "assembledAmount": 2,
    "productWriteoffStrategy": "ASSEMBLE",
    "effectiveDirectWriteoffStoreSpecification": {
        "departments": [],
        "inverse": false
    },
    "productSizeAssemblyStrategy": "COMMON",
    "items": [
        {
            "sortWeight": 0,
            "productId": "56ca36c8-eb11-4f0a-802c-f96d0ce68e27",
            "productSizeSpecification": null,
            "storeSpecification": null,
            "amountIn": 0.4,
            "amountMiddle": 0.36,
            "amountOut": 0.36,
            "amountIn1": 0,
            "amountOut1": 0,
            "amountIn2": 0,
            "amountOut2": 0,
            "amountIn3": 0,
            "amountOut3": 0,
            "packageTypeId": null
        }
    ],
    "technologyDescription": "",
    "description": "",
    "appearance": "",
    "organoleptic": "",
    "outputComment": ""
}
```
**

### Что в ответе

Созданная тех. карта.

### Пример запроса и результат

#### Запрос

https://localhost:9080/resto/api/v2/assemblyCharts/save

#### Результат


```xml
{
    "result": "SUCCESS",
    "errors": null,
    "response": {
        "id": "8cb98504-c000-ede1-016a-9371e3240031",
        "assembledProductId": "31e6155c-e842-448f-8266-1d05eb8e977a",
        "dateFrom": "2019-04-01",
        "dateTo": null,
        "assembledAmount": 2,
        "productWriteoffStrategy": "ASSEMBLE",
        "effectiveDirectWriteoffStoreSpecification": {
            "departments": [],
            "inverse": false
        },
        "productSizeAssemblyStrategy": "COMMON",
        "items": [
            {
                "id": "8cb98504-c000-ede1-016a-9371e3240033",
                "sortWeight": 0,
                "productId": "56ca36c8-eb11-4f0a-802c-f96d0ce68e27",
                "productSizeSpecification": null,
                "storeSpecification": null,
                "amountIn": 0.4,
                "amountMiddle": 0.36,
                "amountOut": 0.36,
                "amountIn1": 0,
                "amountOut1": 0,
                "amountIn2": 0,
                "amountOut2": 0,
                "amountIn3": 0,
                "amountOut3": 0,
                "packageCount": 0,
                "packageTypeId": null
            }
        ],
        "technologyDescription": "",
        "description": "",
        "appearance": "",
        "organoleptic": "",
        "outputComment": ""
    }
}
```

```xml
{
    "result": "SUCCESS",
    "errors": null,
    "response": {
        "id": "8cb98504-c000-ede1-016a-9371e3240031",
        "assembledProductId": "31e6155c-e842-448f-8266-1d05eb8e977a",
        "dateFrom": "2019-04-01",
        "dateTo": null,
        "assembledAmount": 2,
        "productWriteoffStrategy": "ASSEMBLE",
        "effectiveDirectWriteoffStoreSpecification": {
            "departments": [],
            "inverse": false
        },
        "productSizeAssemblyStrategy": "COMMON",
        "items": [
            {
                "id": "8cb98504-c000-ede1-016a-9371e3240033",
                "sortWeight": 0,
                "productId": "56ca36c8-eb11-4f0a-802c-f96d0ce68e27",
                "productSizeSpecification": null,
                "storeSpecification": null,
                "amountIn": 0.4,
                "amountMiddle": 0.36,
                "amountOut": 0.36,
                "amountIn1": 0,
                "amountOut1": 0,
                "amountIn2": 0,
                "amountOut2": 0,
                "amountIn3": 0,
                "amountOut3": 0,
                "packageCount": 0,
                "packageTypeId": null
            }
        ],
        "technologyDescription": "",
        "description": "",
        "appearance": "",
        "organoleptic": "",
        "outputComment": ""
    }
}
```

 
## Удаление технологической карты

Версия iiko: 6.4

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/assemblyCharts/delete |
| --- | --- |

### **Тело запроса**

| Поле | Тип | Описание |
| --- | --- | --- |
| id | UUID | UUID технологической карты |

**Пример** **Body**

**
Код

```
{
    "id": "8cb98504-c000-ede1-016a-9371e3240031"
}
```

Код

```
{
    "id": "8cb98504-c000-ede1-016a-9371e3240031"
}
```
**

**Что в ответе**

UUID удалённой технологической карты

**Пример запроса и результат**

#### **Запрос**

https://localhost:9080/resto/api/v2/assemblyCharts/delete

#### **Результат**

**
```xml
{
    "result": "SUCCESS",
    "errors": null,
    "response": "8cb98504-c000-ede1-016a-9371e3240031"
}
```

```xml
{
    "result": "SUCCESS",
    "errors": null,
    "response": "8cb98504-c000-ede1-016a-9371e3240031"
}
```
**

## Приложение: структура StoreSpecification

Структура StoreSpecification используется для указания на подмножество подразделений (департментов), в которых действует содержащая ее строка тех.карты.
| **Параметр** | **Тип, формат** | **Описание** |
| --- | --- | --- |
| **departments** | List&lt;UUID&gt; | Список ID подразделений |
| **inverse** | Boolean | false — фильтр является включающим (строка действует для всех перечисленных подразделений)<br><br>true — фильтр является исключающим (строка действует для всех подразделений, КРОМЕ перечисленных, в том числе для подразделений, созданных после последнего сохранения техкарты) |
**Примеры**

{"departments" : ["3f896777-4560-45f7-a7b0-28b4bf0d6a36", "f636376d-e871-49ad-8281-65259f29aab5"], "inverse" : false}, — только в двух указанных подразделениях.

{"departments" : ["3f896777-4560-45f7-a7b0-28b4bf0d6a36"], "inverse" : true}, — во всех подразделениях, кроме одного, включая подразделения, созданные после сохранения техкарты.

{"departments" : [], "inverse" : true}, — общая строка для всех подразделений, включая созданные после сохранения техкарты (то есть, версионирование технологических карт отсутствует).
