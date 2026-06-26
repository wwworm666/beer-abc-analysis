* [Получение типов смен](/articles/api-documentations/rabota-s-dannymi-smeny-i-raspisaniy/a/h2_1490336783)
* [Получение смен](/articles/api-documentations/rabota-s-dannymi-smeny-i-raspisaniy/a/h2_611132094)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-smeny-i-raspisaniy/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-smeny-i-raspisaniy/a/h3_501454233)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-smeny-i-raspisaniy/a/h3_1387997121)
* [Создание или обновление смены](/articles/api-documentations/rabota-s-dannymi-smeny-i-raspisaniy/a/h2_588945765)
* [Тело запроса](/articles/api-documentations/rabota-s-dannymi-smeny-i-raspisaniy/a/h3__1158465537)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-smeny-i-raspisaniy/a/h3__2104128272)
* [Удаление смены](/articles/api-documentations/rabota-s-dannymi-smeny-i-raspisaniy/a/h2_1431404139)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-smeny-i-raspisaniy/a/h3_1338030860)
* [Описание сущностей для представления в формате XML (XSD-схема)](/articles/api-documentations/rabota-s-dannymi-smeny-i-raspisaniy/a/v1.APIсотрудников-ОписаниясущностейдляпредставлениявформатеXML%28XSD-схема%29)

## Получение типов смен

Версия API: 1.0

Версия iiko: 2.5

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **https://host:port/resto/api/employees/schedule/types** |
| --- | --- |

**Что в ответе**

Возвращаются все не удаленные типы смен.

includeDeleted — не реализовано.

**Пример запроса**

https://localhost:8080/resto/api/employees/schedule/types

## Получение смен

Версия API: 1.0

Версия iiko: 2.5

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/schedule/?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/schedule/byEmployee/{employeeUUID}/?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/schedule/byDepartment/{departmentCode}/?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/schedule/byDepartment/{departmentCode}/byEmployee/{employeeUUID}/?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/schedule/department/{departmentId}/?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/schedule/department/{departmentId}/byEmployee/{employeeUUID}/?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

### **Параметры запроса**

| Параметр | Описание |
| --- | --- |
| from | дата начала отчета в формате YYYY-MM-DD |
| to | дата окончания отчета (включающая) в формате YYYY-MM-DD |
| employeeUUID | ID сотрудника |
| departmentCode | код подразделения (тот, который используется при регистрации iikoRMS в iikoChain) |
| departmentId | UUID идентификатор подразделения |
| withPaymentDetails | *(начиная с 5.0)* если true, ко сменам добавляется информация об отработанном времени и начисленной по явкам заработной плате. |
| revisionFrom | номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

У сотрудников, работающих по свободному графику, смен может не быть; если есть, то paymentDetails у них будет пуст. Если у сотрудника, есть незакрытые явки, начавшиеся раньше, при значении true будет ошибка.

### **Что в ответе**

Возвращаются все смены, **пересекающие** интервал отчета.

При этом, в отличие от других методов API, здесь дата окончания выборки включающая: `&to=2016-03-21` вернет явки, пересекающие 2016-03-22 00:00:00.

### **Пример запроса**

https://localhost:8080/resto/api/employees/schedule/?from=2017-03-21&to=2017-03-22&withPaymentDetails=true

## Создание или обновление смены

Версия API: 1.0

Версия iiko: 5.0

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/employees/schedule/create |
| --- | --- |

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/employees/schedule/update |
| --- | --- |
### Тело запроса

| Переменная | Описание |
| --- | --- |
| employeeId | id сотрудника |
| roleId | id роли сотрудника |
| dateFrom | время начала смены |
| dateTo | время окончания смены |
| scheduleTypeCode | код типа смены |
| nonPaidMinutesdepartmentId | неоплачиваемые минуты |
| departmentId | id подразделения |
| departmentName | наименование подразделения |

### **Что в ответе**
Структура **schedule**. При создании поле id может быть не заполнено. Даты округляются с точностью до минуты.

Структура **schedule** после сохранения, с округленными датами, сгенерированным новым id.

Внимание! При обновлении (update) смены ее id может измениться.

### **Пример запроса**
https://localhost:8080/resto/api/employees/schedule/create


Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<schedule>
<employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
    <roleId>6e3fa11d-3617-c735-bd29-aeac662741ed</roleId>
    <dateFrom>2017-10-06T16:00:00+03:00</dateFrom>
    <dateTo>2017-10-06T22:00:00+03:00</dateTo>
    <scheduleTypeCode>DSH</scheduleTypeCode>
    <nonPaidMinutes>0</nonPaidMinutes>
    <departmentId>2b602c10-2045-4f52-b5f9-d00be812d6aa</departmentId>
    <departmentName>ТП1</departmentName>
</schedule>
```

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<schedule>
<employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
    <roleId>6e3fa11d-3617-c735-bd29-aeac662741ed</roleId>
    <dateFrom>2017-10-06T16:00:00+03:00</dateFrom>
    <dateTo>2017-10-06T22:00:00+03:00</dateTo>
    <scheduleTypeCode>DSH</scheduleTypeCode>
    <nonPaidMinutes>0</nonPaidMinutes>
    <departmentId>2b602c10-2045-4f52-b5f9-d00be812d6aa</departmentId>
    <departmentName>ТП1</departmentName>
</schedule>
```


**Пример результата вызова API**


Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<schedule>
    <id>d9d8aa67-9e10-97ee-015e-f1879f9c0589</id>
    <employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
    <roleId>6e3fa11d-3617-c735-bd29-aeac662741ed</roleId>
    <dateFrom>2017-10-06T16:00:00+03:00</dateFrom>
    <dateTo>2017-10-06T22:00:00+03:00</dateTo>
    <scheduleTypeCode>DSH</scheduleTypeCode>
    <nonPaidMinutes>0</nonPaidMinutes>
    <departmentId>2b602c10-2045-4f52-b5f9-d00be812d6aa</departmentId>
    <departmentName>ТП1</departmentName>
</schedule>
```

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<schedule>
    <id>d9d8aa67-9e10-97ee-015e-f1879f9c0589</id>
    <employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
    <roleId>6e3fa11d-3617-c735-bd29-aeac662741ed</roleId>
    <dateFrom>2017-10-06T16:00:00+03:00</dateFrom>
    <dateTo>2017-10-06T22:00:00+03:00</dateTo>
    <scheduleTypeCode>DSH</scheduleTypeCode>
    <nonPaidMinutes>0</nonPaidMinutes>
    <departmentId>2b602c10-2045-4f52-b5f9-d00be812d6aa</departmentId>
    <departmentName>ТП1</departmentName>
</schedule>
```


## Удаление смены

Версия API: 1.0

Версия iiko: 5.0

| ![DELETE Request](/resources/Storage/api-documentations/http_request_delete.png) | https://host:port/resto/api/employees/schedule/byId/{scheduleUUID} |
| --- | --- |

### Что в ответе

Удаленная смена **schedule**.

## Описание сущностей для представления в формате XML (XSD-схема)

[+] [Тип смены](javascript:void%280%29)
 [-] [Тип смены](javascript:void%280%29)
 
```
 %%CH%PRE4%%%%CH%PRE5%%
```


[+] [Смена в расписании](javascript:void%280%29)
 [-] [Смена в расписании](javascript:void%280%29)
 
```
 %%CH%PRE6%%%%CH%PRE7%%
```
