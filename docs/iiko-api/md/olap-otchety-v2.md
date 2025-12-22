# Olap Otchety V2

*Generated from PDF: olap-otchety-v2.pdf*

*Total pages: 12*

---


## Page 1

API Documentation Page1 of 12
1. OLAP-отчеты
Поля OLAP-отчета
Версияiiko: 4.1
https://host:port/resto/api/v2/reports/olap/columns
Параметры запроса
Параметры Описание
reportType Тип отчета:
· SALES - По продажам
· TRANSACTIONS - По транзакциям
· DELIVERIES - По доставкам
Что в ответе
Json структура списка полей с информацией по возможностям фильтрации,
агрегации и группировки.
Устаревшие поля (deprecated) не выводятся.
Структура списка полей
CopyCode
JSON
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
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |

|---|---|---|---|---|---|

|  | Параметры |  |  | Описание |  |

|  |  |  |  |  |  |

| reportType |  |  | Тип отчета:
· SALES - По продажам
· TRANSACTIONS - По транзакциям
· DELIVERIES - По доставкам |  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | "FieldName": { |  |

|  | "name": "StringValue", |  |

|  | "type": "StringValue", |  |

|  | "aggregationAllowed": booleanValue, |  |

|  | "groupingAllowed": booleanValue, |  |

|  | "filteringAllowed": booleanValue, |  |

|  | "tags": [ |  |

|  | "StringValue1", |  |

|  | "StringValue2", |  |

|  | ..., |  |

|  | "StringValueN", |  |


---


## Page 2

API Documentation Page2 of 12
]
}
Название Значение Описание
FieldName Строка Названиеколонкиотчета.Именноэтоназваниеиспользуетсядля
полученияданныхотчета
name Строка НазваниеколонкиотчетавiikoOffice.Справочнаяинформация.
type Строка Типполя.Возможныследующиезначения:
· ENUM-Перечислимыезначения
· STRING-Строка
· ID-Внутреннийидентификаторобъектавiiko(начинаяс
5.0)
· DATETIME-Датаивремя
· INTEGER-Целое
· PERCENT-Процент(от0до1)
· DURATION_IN_SECONDS-Длительностьвсекундах
· AMOUNT-Количество
· MONEY-Денежнаясумма
aggregationAllowed true/false Еслиtrue,топоданнойколонкеможноагрегироватьданные
groupingAllowed true/false Еслиtrue,топоданнойколонкеможногруппироватьданные
filteringAllowed true/false Еслиtrue,топоданнойколонкеможнофильтроватьданные
tags Список Списоккатегорийотчета,ккоторомуотноситсяданноеполе.
строк Справочнаяинформация.Соответствуетспискувверхнем
правомуглуконструктораотчетавiikoOffice.
Пример запроса
https://localhost:8080/resto/api/v2/reports/olap/columns?key=5b11
9afe-9468-ab68-7d56-c71495e39ee4&reportType=SALES
Ответ
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | ] |

|  | } |

|  |  |



### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| FieldName |  |  | Строка |  |  | Названиеколонкиотчета.Именноэтоназваниеиспользуетсядля
полученияданныхотчета |  |  |

| name |  |  | Строка |  |  | НазваниеколонкиотчетавiikoOffice.Справочнаяинформация. |  |  |

| type |  |  | Строка |  |  | Типполя.Возможныследующиезначения:
· ENUM-Перечислимыезначения
· STRING-Строка
· ID-Внутреннийидентификаторобъектавiiko(начинаяс
5.0)
· DATETIME-Датаивремя
· INTEGER-Целое
· PERCENT-Процент(от0до1)
· DURATION_IN_SECONDS-Длительностьвсекундах
· AMOUNT-Количество
· MONEY-Денежнаясумма |  |  |

| aggregationAllowed |  |  | true/false |  |  | Еслиtrue,топоданнойколонкеможноагрегироватьданные |  |  |

| groupingAllowed |  |  | true/false |  |  | Еслиtrue,топоданнойколонкеможногруппироватьданные |  |  |

| filteringAllowed |  |  | true/false |  |  | Еслиtrue,топоданнойколонкеможнофильтроватьданные |  |  |

| tags |  |  | Список
строк |  |  | Списоккатегорийотчета,ккоторомуотноситсяданноеполе.
Справочнаяинформация.Соответствуетспискувверхнем
правомуглуконструктораотчетавiikoOffice. |  |  |



### Table:

| https://localhost:8080/resto/api/v2/reports/olap/columns?key=5b11 |  |

|---|---|

| 9afe-9468-ab68-7d56-c71495e39ee4&reportType=SALES |  |


---


## Page 3

API Documentation Page3 of 12
CopyCode
JSON
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
Общая информация (General info)
Версия iiko: 4.1
https://host:port/resto/api/reports/olap
Content-type: Application/json; charset=utf-8
Тело запроса
Allrightsreserved © CompanyInc., 2023


### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | { |  |

|  | "PercentOfSummary.ByCol": { |  |

|  | "name": "% по столбцу", |  |

|  | "type": "PERCENT", |  |

|  | "aggregationAllowed": true, |  |

|  | "groupingAllowed": false, |  |

|  | "filteringAllowed": false, |  |

|  | "tags": [ |  |

|  | "Оплата" |  |

|  | ] |  |

|  | }, |  |

|  | "PercentOfSummary.ByRow": { |  |

|  | "name": "% по строке", |  |

|  | "type": "PERCENT", |  |

|  | "aggregationAllowed": true, |  |

|  | "groupingAllowed": false, |  |

|  | "filteringAllowed": false, |  |

|  | "tags": [ |  |

|  | "Оплата" |  |

|  | ] |  |

|  | }, |  |

|  | "Delivery.Email": { |  |

|  | "name": "e-mail доставки", |  |

|  | "type": "STRING", |  |

|  | "aggregationAllowed": false, |  |

|  | "groupingAllowed": true, |  |

|  | "filteringAllowed": true, |  |

|  | "tags": [ |  |

|  | "Доставка", |  |

|  | "Клиент доставки" |  |

|  | ] |  |

|  | } |  |

|  | } |  |

|  |  |  |


---


## Page 4

API Documentation Page4 of 12
CopyCode
JSON
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
Название Значение Описание
reportType SALES Типотчета:
· SALES-Попродажам
TRANSACTIONS
· TRANSACTIONS-Попроводками
DELIVERIES
· DELIVERIES-Подоставкам
buildSummary true/false ПараметрпоявилсявVersion(iiko)5.3.4.Считатьлиитоговые
значения.Необязательное,доверсии9.1.2поумолчаниюtrue,
сверсии9.1.2поумолчаниюfalse.
groupByRowFields Списокполей Именаполей,покоторымдоступнагруппировка.Список
для полейможнополучитьчерезметод reports/olap/columns,
группировкипо какэлементыданногоспискаиспользуютсяполя FieldNameиз
строкам возвращаемой reports/olap/columns структуры.Дляуказания
Allrightsreserved © CompanyInc., 2023


### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | { |  |

|  | "reportType": "EnumValue", |  |

|  | "buildSummary": "true", |  |

|  | "groupByRowFields": [ |  |

|  | "groupByRowFieldName1", |  |

|  | "groupByRowFieldName2", |  |

|  | ..., |  |

|  | "groupByRowFieldNameN" |  |

|  | ], |  |

|  | "groupByColFields": [ |  |

|  | "groupByColFieldName1", |  |

|  | "groupByColFieldName2", |  |

|  | ..., |  |

|  | "groupByColFieldNameL" |  |

|  | ], |  |

|  | "aggregateFields": [ |  |

|  | "AggregateFieldName1", |  |

|  | "AggregateFieldName2", |  |

|  | ..., |  |

|  | "AggregateFieldNameM" |  |

|  | ], |  |

|  | "filters": { |  |

|  | filter1, |  |

|  | filter2, |  |

|  | ... |  |

|  | filterK |  |

|  | } |  |

|  | } |  |

|  |  |  |



### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| reportType |  |  | SALES
TRANSACTIONS
DELIVERIES |  |  | Типотчета:
· SALES-Попродажам
· TRANSACTIONS-Попроводками
· DELIVERIES-Подоставкам |  |  |

| buildSummary |  |  | true/false |  |  | ПараметрпоявилсявVersion(iiko)5.3.4.Считатьлиитоговые
значения.Необязательное,доверсии9.1.2поумолчаниюtrue,
сверсии9.1.2поумолчаниюfalse. |  |  |

| groupByRowFields |  |  | Списокполей
для
группировкипо
строкам |  |  | Именаполей,покоторымдоступнагруппировка.Список
полейможнополучитьчерезметод reports/olap/columns,
какэлементыданногоспискаиспользуютсяполя FieldNameиз
возвращаемой reports/olap/columns структуры.Дляуказания |  |  |


---


## Page 5

API Documentation Page5 of 12
Название Значение Описание
вданномспискедоступныполя,укоторых groupingAllowed
=true
groupByColFields Списокполей Необязательный.Именаполей,покоторымдоступна
для группировка.Списокполейможнополучитьчерез
группировкипо метод reports/olap/columns,какэлементыданногосписка
столбцам используютсяполя FieldNameиз
возвращаемой reports/olap/columns структуры.Дляуказания
вданномспискедоступныполя,укоторых groupingAllowed
=true
aggregateFields Списокполей Именаполей,покоторымдоступнаагрегация.Списокполей
дляагрегации можнополучитьчерезметод reports/olap/columns,как
элементыданногоспискаиспользуютсяполя FieldNameиз
возвращаемой reports/olap/columns структуры.Дляуказания
вданномспискедоступныполя,укоторых filteringAllowed =
true
filters Список См.описаниеструктурыфильтров. Дляуказаниявданном
фильтров спискедоступныполя,укоторых filteringAllowed=true
Поляагрегации,учитывающиеначальныйостатоктовараиденежныйостаток
(StartBalance.Amount,StartBalance.Money,FinalBalance.Amount,FinalBalance.Money)вычисляются
суммированиемвсейтаблицыпроводокзавсевремяработысистемы(всейбазыданных)без
каких-либооптимизаций.Тоесть,такойзапросможетвыполнятьсяоченьдолгоизамедлять
работусервера.
Еслиначальныйостатокнеобходим,оставляйтевэтомOLAP-запросетолькотеполягруппировки,
покоторымондействительнонеобходим(какправило,это Account.NameиProduct.Name),и
вызывайтетакойзапроскакможнорежеивнерабочеевремя.
В5.2добавленоAPIдлябыстрогополученияостатков:Отчетыпобалансам.Вовсехслучаях
рекомендуетсяпользоватьсяимвместоOLAP.
В5.5OLAP-отчетысостаткамиоптимизированысиспользованиембалансовыхтаблиц
ATransactionSum,ATransactionBalance,приусловии,чтоприменяютсягруппировкиифильтрыпо
полямизэтихтаблиц,см.признакStartBalanceOptimizableвописанииполей.
Тоесть,правильносоставленныйзапросприведетксуммированиюневсейтаблицыпроводок,а
тольколишьоткрытогопериода.Обратитеособоевниманиенато,чтооптимизированотолько
полеAccount.Name(счет"текущей"стороныпроводки,втомчислесклад),анеStore(первый
попавшийся"склад"проводки,взятыйиз:левой,правойчастипроводки,строкидокументаили
самогодокумента).
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  | вданномспискедоступныполя,укоторых groupingAllowed
=true |  |  |

| groupByColFields |  |  | Списокполей
для
группировкипо
столбцам |  |  | Необязательный.Именаполей,покоторымдоступна
группировка.Списокполейможнополучитьчерез
метод reports/olap/columns,какэлементыданногосписка
используютсяполя FieldNameиз
возвращаемой reports/olap/columns структуры.Дляуказания
вданномспискедоступныполя,укоторых groupingAllowed
=true |  |  |

| aggregateFields |  |  | Списокполей
дляагрегации |  |  | Именаполей,покоторымдоступнаагрегация.Списокполей
можнополучитьчерезметод reports/olap/columns,как
элементыданногоспискаиспользуютсяполя FieldNameиз
возвращаемой reports/olap/columns структуры.Дляуказания
вданномспискедоступныполя,укоторых filteringAllowed =
true |  |  |

| filters |  |  | Список
фильтров |  |  | См.описаниеструктурыфильтров. Дляуказаниявданном
спискедоступныполя,укоторых filteringAllowed=true |  |  |


---


## Page 6

API Documentation Page6 of 12
Фильтры
Фильтр по значению
CopyCode
JSON
"FieldName": {
"filterType": "filterTypeEnum",
"values": ["Value1","Value2",...,"ValueN"]
}
Работаетдляполейстипами:
· ENUM
· STRING
Название Значение Описание
FieldName Имяполядля Поле FieldNameизвозвращаемой reports/olap/columns структуры
фильтрации
filterType IncludeValues/ IncludeValues-вфильтрацииучаствуюттолькоперечисленные
ExcludeValues значенияполя
ExcludeValues -вфильтрацииучаствуютзначенияполя,за
исключениемперечисленных
values Списокзначений Взависимостиоттипаполя,этомогутбытьилиenum
поля из Расшифровкикодовбазовыхтипов илитекстовоезначениеполя
CopyCode
JSON
"DeletedWithWriteoff": {
"filterType": "ExcludeValues",
"values": ["DELETED_WITH_WRITEOFF","DELETED_WITHOUT_WRITEOFF"]
},
"OrderDeleted": {
"filterType": "IncludeValues",
"values": ["NOT_DELETED"]
}
Фильтр по диапазону
Allrightsreserved © CompanyInc., 2023


### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | "FieldName": { |  |

|  | "filterType": "filterTypeEnum", |  |

|  | "values": ["Value1","Value2",...,"ValueN"] |  |

|  | } |  |

|  |  |  |



### Table:

|  |  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|---|

|  | Название |  |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |  |

| FieldName |  |  |  | Имяполядля
фильтрации |  |  | Поле FieldNameизвозвращаемой reports/olap/columns структуры |  |  |

| filterType |  |  |  | IncludeValues/
ExcludeValues |  |  | IncludeValues-вфильтрацииучаствуюттолькоперечисленные
значенияполя
ExcludeValues -вфильтрацииучаствуютзначенияполя,за
исключениемперечисленных |  |  |

| values |  |  |  | Списокзначений
поля |  |  | Взависимостиоттипаполя,этомогутбытьилиenum
из Расшифровкикодовбазовыхтипов илитекстовоезначениеполя |  |  |

| CopyCode |  |  |  |  |  |  |  |  |  |

|  | JSON |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |

|  | "DeletedWithWriteoff": { |  |  |  |  |  |  |  |  |

|  | "filterType": "ExcludeValues", |  |  |  |  |  |  |  |  |

|  | "values": ["DELETED_WITH_WRITEOFF","DELETED_WITHOUT_WRITEOFF"] |  |  |  |  |  |  |  |  |

|  | }, |  |  |  |  |  |  |  |  |

|  | "OrderDeleted": { |  |  |  |  |  |  |  |  |

|  | "filterType": "IncludeValues", |  |  |  |  |  |  |  |  |

|  | "values": ["NOT_DELETED"] |  |  |  |  |  |  |  |  |

|  | } |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |


---


## Page 7

API Documentation Page7 of 12
CopyCode
JSON
"FieldName": {
"filterType": "Range",
"from": Value1,
"to": Value2,
"includeLow": booleanValue,
"includeHigh": booleanValue
}
Работаетдляполейстипами:
· INTEGER
· PERCENT
· AMOUNT
· MONEY
Название Значение Описание
FieldName Имяполядля Поле FieldNameиз
фильтрации возвращаемой reports/olap/columns структуры
filterType Range Фильтрподиапазонузначений
from Нижняяграница Значениевформате,соответствующемтипуполя
диапазона
to Верхняяграница Значениевформате,соответствующемтипуполя
диапазона
includeLow true/false Необязательное,поумолчаниюtrue
true-нижняяграницадиапазонавключаетсявфильтр
false -нижняяграницадиапазонаневключаетсявфильтр
includeHigh true/false Необязательное,поумолчаниюfalse
true-верхняяграницадиапазонавключаетсявфильтр
false-верхняяграницадиапазонаневключаетсявфильтр
CopyCode
JSON
"SessionNum": {
Allrightsreserved © CompanyInc., 2023


### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | "FieldName": { |  |

|  | "filterType": "Range", |  |

|  | "from": Value1, |  |

|  | "to": Value2, |  |

|  | "includeLow": booleanValue, |  |

|  | "includeHigh": booleanValue |  |

|  | } |  |

|  |  |  |



### Table:

|  |  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|---|

|  | Название |  |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |  |

| FieldName |  |  |  | Имяполядля
фильтрации |  |  | Поле FieldNameиз
возвращаемой reports/olap/columns структуры |  |  |

| filterType |  |  |  | Range |  |  | Фильтрподиапазонузначений |  |  |

| from |  |  |  | Нижняяграница
диапазона |  |  | Значениевформате,соответствующемтипуполя |  |  |

| to |  |  |  | Верхняяграница
диапазона |  |  | Значениевформате,соответствующемтипуполя |  |  |

| includeLow |  |  |  | true/false |  |  | Необязательное,поумолчаниюtrue
true-нижняяграницадиапазонавключаетсявфильтр
false -нижняяграницадиапазонаневключаетсявфильтр |  |  |

| includeHigh |  |  |  | true/false |  |  | Необязательное,поумолчаниюfalse
true-верхняяграницадиапазонавключаетсявфильтр
false-верхняяграницадиапазонаневключаетсявфильтр |  |  |

| CopyCode |  |  |  |  |  |  |  |  |  |

|  | JSON |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |

|  | "SessionNum": { |  |  |  |  |  |  |  |  |


---


## Page 8

API Documentation Page8 of 12
"filterType": "Range",
"from": 758,
"to": 760,
"includeHigh": true
}
Фильтр по дате
CopyCode
JSON
"FieldName": {
"filterType": "DateRange",
"periodType": "periodTypeEnum",
"from": "fromDateTime",
"to": "toDateTime",
"includeLow": booleanValue,
"includeHigh": booleanValue
}
Работаетдляполейстипами:
· DATETIME
· DATE
Название Значение Описание
FieldName Имяполядля ПолеFieldNameиз
фильтрации возвращаемой reports/olap/columns структуры
filterType DateRange Фильтрподиапазонузначений
periodType CUSTOM-вручную ЕслипериодCUSTOM,топериодзадаетсявручную,
используютсяполяfrom,to, includeLow, includeHigh
OPEN_PERIOD-
текущийоткрытый Дляостальныхтиповпериодаданныепараметрыигнорируются
период (можнонеиспользовать),кромепараметраfrom,егопередача
обязательна,егозначениеможетбытьлюбым.
TODAY-сегодня
YESTERDAY-вчера
CURRENT_WEEK-
текущаянеделя
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "filterType": "Range", |

|  | "from": 758, |

|  | "to": 760, |

|  | "includeHigh": true |

|  | } |

|  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | "FieldName": { |  |

|  | "periodType": "periodTypeEnum", |  |

|  | "from": "fromDateTime", |  |

|  | "to": "toDateTime", |  |

|  | "includeLow": booleanValue, |  |

|  | "includeHigh": booleanValue |  |

|  | } |  |

|  |  |  |



### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| FieldName |  |  | Имяполядля
фильтрации |  |  | ПолеFieldNameиз
возвращаемой reports/olap/columns структуры |  |  |

| filterType |  |  | DateRange |  |  | Фильтрподиапазонузначений |  |  |

| periodType |  |  | CUSTOM-вручную
OPEN_PERIOD-
текущийоткрытый
период
TODAY-сегодня
YESTERDAY-вчера
CURRENT_WEEK-
текущаянеделя |  |  | ЕслипериодCUSTOM,топериодзадаетсявручную,
используютсяполяfrom,to, includeLow, includeHigh
Дляостальныхтиповпериодаданныепараметрыигнорируются
(можнонеиспользовать),кромепараметраfrom,егопередача
обязательна,егозначениеможетбытьлюбым. |  |  |


---


## Page 9

API Documentation Page9 of 12
Название Значение Описание
CURRENT_MONTH-
текущиймесяц
CURRENT_YEAR-
текущийгод
LAST_WEEK-
прошлаянеделя
LAST_MONTH-
прошлыймесяц
LAST_YEAR-
прошлыйгод
from Начальнаядата Датавформатеyyyy-MM-dd'T'HH:mm:ss.SSS
to Конечнаядата Датавформатеyyyy-MM-dd'T'HH:mm:ss.SSS
includeLow true/false Необязательное,поумолчанию true
true-нижняяграницадиапазонавключаетсявфильтр
false-нижняяграницадиапазонаневключаетсявфильтр
includeHigh true/false
Необязательное,поумолчанию false
true-верхняяграницадиапазонавключаетсявфильтр.
Внимание:включениеверхнейграницыимеетсмыслтолькоу
полей,выдающих округленную ДАТУ,ане ДАТУ-ВРЕМЯ.
false-верхняяграницадиапазонаневключаетсявфильтр
ВOLAP-отчетепопроводкам("reportType":"TRANSACTIONS")дляфильтрациипо*дате*
рекомендуетсяиспользоватьполеDateTime.DateTyped(илиDateTime.Typed—ноэтодата-время)
ВOLAP-отчетепопродажам,атакжедоставкамиспользуетсяполеOpenDate.Typed.
В4.1вместоотсутствующихполейOpenDate.TypedиDateTime.DateTypedиспользуютсяполя
OpenDateиDateTime.OperDayFilterсоответственно.
Начинаяс5.5,каждыйOLAP-запросдолженсодержатьфильтрподате
CopyCode
JSON
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

|  |  |  | CURRENT_MONTH-
текущиймесяц
CURRENT_YEAR-
текущийгод
LAST_WEEK-
прошлаянеделя
LAST_MONTH-
прошлыймесяц
LAST_YEAR-
прошлыйгод |  |  |  |  |  |

| from |  |  | Начальнаядата |  |  | Датавформатеyyyy-MM-dd'T'HH:mm:ss.SSS |  |  |

| to |  |  | Конечнаядата |  |  | Датавформатеyyyy-MM-dd'T'HH:mm:ss.SSS |  |  |

| includeLow |  |  | true/false |  |  | Необязательное,поумолчанию true
true-нижняяграницадиапазонавключаетсявфильтр
false-нижняяграницадиапазонаневключаетсявфильтр |  |  |

| includeHigh |  |  | true/false |  |  | Необязательное,поумолчанию false
true-верхняяграницадиапазонавключаетсявфильтр.
Внимание:включениеверхнейграницыимеетсмыслтолькоу
полей,выдающих округленную ДАТУ,ане ДАТУ-ВРЕМЯ.
false-верхняяграницадиапазонаневключаетсявфильтр |  |  |



### Table:

|  |  | ВOLAP-отчетепопроводкам("reportType":"TRANSACTIONS")дляфильтрациипо*дате*
рекомендуетсяиспользоватьполеDateTime.DateTyped(илиDateTime.Typed—ноэтодата-время)
ВOLAP-отчетепопродажам,атакжедоставкамиспользуетсяполеOpenDate.Typed.
В4.1вместоотсутствующихполейOpenDate.TypedиDateTime.DateTypedиспользуютсяполя
OpenDateиDateTime.OperDayFilterсоответственно.
Начинаяс5.5,каждыйOLAP-запросдолженсодержатьфильтрподате |

|---|---|---|

|  |  |  |

|  |  |  |

| CopyCode |  |  |

|  | JSON |  |

|  |  |  |


---


## Page 10

API Documentation Page10 of 12
"OpenDate.Typed": {
"filterType": "DateRange",
"periodType": "CUSTOM",
"from": "2014-01-01T00:00:00.000",
"to": "2014-01-03T00:00:00.000"
}
Фильтр по дате и времени
CopyCode
XML
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
Ответ
CopyCode
JSON
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
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "OpenDate.Typed": { |

|  | "filterType": "DateRange", |

|  | "periodType": "CUSTOM", |

|  | "from": "2014-01-01T00:00:00.000", |

|  | "to": "2014-01-03T00:00:00.000" |

|  | } |

|  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | XML |  |

|  |  |  |

|  |  |  |

|  | "filters": { |  |

|  | "OpenDate.Typed": { |  |

|  | "filterType": "DateRange", |  |

|  | "periodType": "CUSTOM", |  |

|  | "from": "2018-09-04", |  |

|  | "to": "2018-09-04", |  |

|  | "includeLow": true, |  |

|  | "includeHigh": true |  |

|  | }, |  |

|  | "OpenTime": { |  |

|  | "filterType": "DateRange", |  |

|  | "periodType": "CUSTOM", |  |

|  | "from": "2018-09-04T01:00:00.000", |  |

|  | "to": "2018-09-04T23:00:00.000", |  |

|  | "includeLow": true, |  |

|  | "includeHigh": true |  |

|  | } |  |

|  | } |  |

|  |  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | { |  |

|  | "data": [ |  |

|  | { |  |

|  | "GroupFieldName1": "Value11", |  |

|  | "GroupFieldName2": "Value12", |  |

|  | ..., |  |

|  | "GroupFieldNameN": "Value1N", |  |

|  | "AggregateFieldName1": "Value11", |  |

|  | "AggregateFieldName1": "Value12", |  |

|  | ..., |  |


---


## Page 11

API Documentation Page11 of 12
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
Allrightsreserved © CompanyInc., 2023


### Table:

|  |

|---|

| "AggregateFieldNameM": "Value1M"
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
] |



### Table:

| "AggregateFieldNameM": "Value1M" |

|---|

| }, |

| ..., |

| { |

| "GroupFieldName1": "ValueK1", |

| "GroupFieldName2": "ValueK2", |

| ..., |

| "GroupFieldNameN": "ValueKN", |

| "AggregateFieldName1": "ValueK1", |

| "AggregateFieldName1": "ValueK2", |

| ..., |

| "AggregateFieldNameM": "ValueKM" |

| } |

| ], |

| "summary": [ |

| [ |

| { |



### Table:

| }, |

|---|

| { |

| "AggregateFieldName1": "TotalValue1", |

| "AggregateFieldName2": "TotalValue2", |

| ..., |

| "AggregateFieldNameM": "TotalValueM" |

| } |

| ], |

| [ |

| { |

| "GroupFieldName1": "Value11" |

| }, |

| { |

| "AggregateFieldName1": "TotalValue11", |

| "AggregateFieldName2": "TotalValue12", |

| ..., |

| "AggregateFieldNameM": "TotalValue1M" |

| } |

| ], |

| ..., |

| [ |

| { |

| "GroupFieldName1": "Value1", |

| ... |

| "GroupFieldNameN": "ValueN", |

| }, |

| { |

| "AggregateFieldName1": "TotalValue11", |

| "AggregateFieldName2": "TotalValue12", |

| ..., |

| "AggregateFieldNameM": "TotalValue1M" |

| } |

| ], |

| ... |

| ] |


---


## Page 12

API Documentation Page12 of 12
}
Название Значение Описание
data Данныеотчета Линейныеданныеотчета(построчно),одназаписьвнутриблока
соответствуетоднойстрокевгридеiikoOffice
summary Промежуточныеи Списокблоков,состоящихиздвухструктур.
общиеитогипо 1. Впервойструктуре-списокполей,покоторымсобраны
отчету промежуточныеитоги,вкачествеэлементовэтой
структурыпредставленыполя,которыеиспользуютсядля
группировки.Количествоэлементоввструктуре
отличаетсяиможетбыть:
a. пустым-этозначит,чтововторомблоке
представленыобщиеитогипоотчету
b. списокполейгруппировки,покоторымсобраны
промежуточныеитоги.Списокимеетдлинуот1
дочислаполейгруппировки.Полядобавляютсяк
спискувпорядкеихследованиявзапросе.
2. Вовторой-собственнопромежуточныеитоги.В
качествеэлементовданнойструктурыпредставлены
поля,которыеиспользуютсядляагрегации.Количество
элементовэтойструктурыфиксированоиравно
количествуполейдляагрегации.
3. Припараметрезапросаsummary=false(olap,
olap_presetId)."summary":[] будетпустой.CVersion(iiko)
5.3
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |

|---|---|---|

|  | } |  |

|  |  |  |



### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| data |  |  | Данныеотчета |  |  | Линейныеданныеотчета(построчно),одназаписьвнутриблока
соответствуетоднойстрокевгридеiikoOffice |  |  |

| summary |  |  | Промежуточныеи
общиеитогипо
отчету |  |  | Списокблоков,состоящихиздвухструктур.
1. Впервойструктуре-списокполей,покоторымсобраны
промежуточныеитоги,вкачествеэлементовэтой
структурыпредставленыполя,которыеиспользуютсядля
группировки.Количествоэлементоввструктуре
отличаетсяиможетбыть:
a. пустым-этозначит,чтововторомблоке
представленыобщиеитогипоотчету
b. списокполейгруппировки,покоторымсобраны
промежуточныеитоги.Списокимеетдлинуот1
дочислаполейгруппировки.Полядобавляютсяк
спискувпорядкеихследованиявзапросе.
2. Вовторой-собственнопромежуточныеитоги.В
качествеэлементовданнойструктурыпредставлены
поля,которыеиспользуютсядляагрегации.Количество
элементовэтойструктурыфиксированоиравно
количествуполейдляагрегации.
3. Припараметрезапросаsummary=false(olap,
olap_presetId)."summary":[] будетпустой.CVersion(iiko)
5.3 |  |  |


---
