* [Расписание](/articles/api-documentations/periody-deystviya/a/h3__1728986205)
* [Период действия (интервал) по дням недели](/articles/api-documentations/periody-deystviya/a/v2.APIпериодовдействий-Периоддействия%28интервал%29поднямнедели)
* [Получение расписаний](/articles/api-documentations/periody-deystviya/a/v2.APIпериодовдействий-Получениерасписаний)
* [Параметры запроса](/articles/api-documentations/periody-deystviya/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/periody-deystviya/a/h3_501454233)
* [Пример запроса и результата](/articles/api-documentations/periody-deystviya/a/v2.APIпериодовдействий-Пример)
* [Получение расписания по идентификатору](/articles/api-documentations/periody-deystviya/a/v2.APIпериодовдействий-Получениерасписанияпоидентификатору)
* [Параметры запроса](/articles/api-documentations/periody-deystviya/a/h3_1832657069)
* [Пример запроса и результата](/articles/api-documentations/periody-deystviya/a/v2.APIпериодовдействий-Пример.1)

# API периодов действий

Версия iiko: 7.8

Описание полей

### Расписание

#### PeriodScheduleDto
| Поле | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | Идентификатор. |
| **name** | String | Название. |
| **deleted** | Boolean | Удалена или нет. |
| **periods** | List&lt;PeriodScheduleItemDto&gt; | Список интервалов. |
### **Период действия (интервал) по дням недели**

#### **PeriodScheduleItemDto**
| Поле | Тип | Описание |
| --- | --- | --- |
| **begin** | String | Начало полуинтервала в виде "HH:mm". |
| **end** | String | Конец полуинтервала в виде "HH:mm". |
| **daysOfWeek** | List&lt;DayOfWeek&gt; | Дни недели, в которых действует интервал.<br>| DayOfWeek | DayOfWeek |<br>| --- | --- |<br>| Значение | Описание |<br>| --- | --- |<br>| 1 | понедельник |<br>| 2 | вторник |<br>| 3 | среда |<br>| 4 | четверг |<br>| 5 | пятница |<br>| 6 | суббота |<br>| 7 | воскресенье | |
| --- | --- | --- |
## 

## Получение расписаний

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/entities/periodSchedules |
| --- | --- |

### Параметры запроса
| Параметр | Тип | Описание |
| --- | --- | --- |
| **includeDeleted** | Boolean | Включать ли в ответ удаленные элементы. По умолчанию false. |
| **id** | List&lt;UUID&gt; | Список идентификаторов расписаний, которые требуется получить. Если не задано, то фильтрации по идентификаторам нет. |
| **revisionFrom** | Integer | В ответе будут сущности с ревизией выше данной. По умолчанию '-1'. |
### Что в ответе

Список расписаний.

Поле revision - максимальная ревизия, доступная для выгрузки во внешние системы на момент запроса (это значит, что в базе присутствуют записи с такой ревизией, а записей с ревизией выше этой в базе нет).

Эту ревизию можно использовать в качестве параметра **revisionFrom** в следующем запросе на получение списка расписаний.

### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/periodSchedules
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
## Получение расписания по идентификатору

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/entities/periodSchedules |
| --- | --- |

### Параметры запроса

| Параметр | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | Идентификатор расписания. |

### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/periodSchedules/byId?id=598ce53a-c49c-4cd5-8248-1e2b4f0994cf
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```
