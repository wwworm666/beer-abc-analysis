* [Получение типов явок](/articles/api-documentations/rabota-s-dannymi-yavok/a/h2_1174254487)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3_501454233)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3_1387997121)
* [Получение явок](/articles/api-documentations/rabota-s-dannymi-yavok/a/h2_375860816)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3_199559134)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3_765642244)
* [Создание или обновление явки](/articles/api-documentations/rabota-s-dannymi-yavok/a/h2__667173474)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3_1461044143)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3__1042337956)
* [Удаление явки](/articles/api-documentations/rabota-s-dannymi-yavok/a/h2_753455492)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3_1967588710)
* [Пример вызова](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3__232688264)
* [Доступность сотрудников](/articles/api-documentations/rabota-s-dannymi-yavok/a/v1.APIсотрудников-Доступностьсотрудников)
* [Получить доступность сотрудников](/articles/api-documentations/rabota-s-dannymi-yavok/a/h2__983155982)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3_1914196038)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3__1125635261)
* [Пример вызова](/articles/api-documentations/rabota-s-dannymi-yavok/a/h3__343110906)
* [Описание сущностей для представления в формате XML (XSD-схема)](/articles/api-documentations/rabota-s-dannymi-yavok/a/v1.APIсотрудников-ОписаниясущностейдляпредставлениявформатеXML%28XSD-схема%29)

## Получение типов явок

Версия API: 1.0

Версия iiko: 2.5

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/attendance/types |
| --- | --- |

### Параметры запроса
| **Название** | **Значение** | **Версия** | **Описание** |
| --- | --- | --- | --- |
| includeDeleted | true\false |  | Включать ли удаленные элементы в результат. По умолчанию false. |
| revisionFrom | число, номер ревизии | с 6.4 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |
### **Что в ответе**

Возвращаются все не удаленные типы явок.

### **Пример запроса**

https://localhost:8080/resto/api/employees/attendance/types

## Получение явок

Версия API: 1.0

Версия iiko: 2.5

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/attendance?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/attendance/byEmployee/{employeeUUID}/?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/attendance/byDepartment/{departmentCode}/?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/attendance/byDepartment/{departmentCode}/byEmployee/{employeeUUID}/?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/attendance/department/{departmentId}/?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/attendance/department/{departmentId}/byEmployee/{employeeUUID}/?from={YYYY-MM-DD}&to={YYYY-MM-DD}&withPaymentDetails={true/false}&revisionFrom=-1 |
| --- | --- |

### **Параметры запроса**

| Параметр | Описание |
| --- | --- |
| from | дата начала отчета в формате YYYY-MM-DD |
| to | дата окончания отчета (включающая) в формате YYYY-MM-DD |
| employeeUUID | ID сотрудника |
| departmentCode | код подразделения (тот, который используется при регистрации iikoRMS в iikoChain) |
| departmentId | UUID идентификатор подразделения |
| withPaymentDetails | *(начиная с 5.0)* если true, ко сменам добавляется информация об отработанном времени и начисленной по явкам заработной плате.<br>У сотрудников, работающих по расписанию или на окладе, paymentDetails явки будет пуст. |
| revisionFrom | номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

### **Что в ответе**

Возвращаются все явки, **пересекающие** интервал отчета.

При этом, в отличие от других методов API, здесь дата окончания выборки включающая: `&to=2016-03-21 `вернет явки, пересекающие 2016-03-22 00:00:00.

### **Пример запроса**

https://localhost:8080/resto/api/employees/attendance?from=2017-08-01&to=2017-10-09&withPaymentDetails=true

**Пример результата вызова API**


Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<attendances>
    <attendance>
        <id>faa6d21e-7193-4c1f-885c-6049ddddd0ce</id>
        <employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
        <roleId>6e3fa11d-3617-c735-bd29-aeac662741ed</roleId>
        <dateFrom>2017-09-21T10:27:00+03:00</dateFrom>
        <attendanceType>W</attendanceType>
        <comment/>
        <departmentId>2b602c10-2045-4f52-b5f9-d00be812d6aa</departmentId>
        <departmentName>ТП1</departmentName>
        <paymentDetails>
            <regularPayedMinutes>0</regularPayedMinutes>
            <regularPaymentSum>0</regularPaymentSum>
            <overtimePayedMinutes>0</overtimePayedMinutes>
            <overtimePayedSum>0</overtimePayedSum>
            <otherPaymentsSum>0</otherPaymentsSum>
        </paymentDetails>
        <personalDateFrom>2017-09-21T10:27:00+03:00</personalDateFrom>
        <created>2017-09-21T10:27:53.987+03:00</created>
    </attendance>
    <attendance>
        <id>72582fa9-172b-4956-9b66-c3b40efff751</id>
        <employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
        <roleId>6e3fa11d-3617-c735-bd29-aeac662741ed</roleId>
        <dateFrom>2017-09-21T09:02:00+03:00</dateFrom>
        <dateTo>2017-09-21T14:02:00+03:00</dateTo>
        <attendanceType>W</attendanceType>
        <comment/>
        <departmentId>2b602c10-2045-4f52-b5f9-d00be812d6aa</departmentId>
        <departmentName>ТП1</departmentName>
        <paymentDetails>
            <regularPayedMinutes>300</regularPayedMinutes>
            <regularPaymentSum>50.000000000</regularPaymentSum>
            <overtimePayedMinutes>0</overtimePayedMinutes>
            <overtimePayedSum>0</overtimePayedSum>
            <otherPaymentsSum>0</otherPaymentsSum>
        </paymentDetails>
        <personalDateFrom>2017-09-21T09:02:00+03:00</personalDateFrom>
        <created>2017-09-21T09:02:40.343+03:00</created>
        <modified>2017-09-21T10:17:06.620+03:00</modified>
        <userModified>c831367e-778f-e80f-18f7-bd0843cd10c6</userModified>
    </attendance>
</attendances>
```

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<attendances>
    <attendance>
        <id>faa6d21e-7193-4c1f-885c-6049ddddd0ce</id>
        <employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
        <roleId>6e3fa11d-3617-c735-bd29-aeac662741ed</roleId>
        <dateFrom>2017-09-21T10:27:00+03:00</dateFrom>
        <attendanceType>W</attendanceType>
        <comment/>
        <departmentId>2b602c10-2045-4f52-b5f9-d00be812d6aa</departmentId>
        <departmentName>ТП1</departmentName>
        <paymentDetails>
            <regularPayedMinutes>0</regularPayedMinutes>
            <regularPaymentSum>0</regularPaymentSum>
            <overtimePayedMinutes>0</overtimePayedMinutes>
            <overtimePayedSum>0</overtimePayedSum>
            <otherPaymentsSum>0</otherPaymentsSum>
        </paymentDetails>
        <personalDateFrom>2017-09-21T10:27:00+03:00</personalDateFrom>
        <created>2017-09-21T10:27:53.987+03:00</created>
    </attendance>
    <attendance>
        <id>72582fa9-172b-4956-9b66-c3b40efff751</id>
        <employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
        <roleId>6e3fa11d-3617-c735-bd29-aeac662741ed</roleId>
        <dateFrom>2017-09-21T09:02:00+03:00</dateFrom>
        <dateTo>2017-09-21T14:02:00+03:00</dateTo>
        <attendanceType>W</attendanceType>
        <comment/>
        <departmentId>2b602c10-2045-4f52-b5f9-d00be812d6aa</departmentId>
        <departmentName>ТП1</departmentName>
        <paymentDetails>
            <regularPayedMinutes>300</regularPayedMinutes>
            <regularPaymentSum>50.000000000</regularPaymentSum>
            <overtimePayedMinutes>0</overtimePayedMinutes>
            <overtimePayedSum>0</overtimePayedSum>
            <otherPaymentsSum>0</otherPaymentsSum>
        </paymentDetails>
        <personalDateFrom>2017-09-21T09:02:00+03:00</personalDateFrom>
        <created>2017-09-21T09:02:40.343+03:00</created>
        <modified>2017-09-21T10:17:06.620+03:00</modified>
        <userModified>c831367e-778f-e80f-18f7-bd0843cd10c6</userModified>
    </attendance>
</attendances>
```


## Создание или обновление явки

Версия API: 1.0

Версия iiko: 2.5

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | **https://host:port/resto/api/employees/attendance/create** |
| --- | --- |

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | **https://host:port/resto/api/employees/attendance/update** |
| --- | --- |

Структура **attendance:** при создании поле id может быть не заполнено. Даты округляются с точностью до минуты. Запрещается создание пересекающихся явок.

### Что в ответе

Структура **attendance** после сохранения, с округленными датами, сгенерированным id.

**Внимание!** При обновлении (update) явки ее id может измениться.

### **Пример запроса**
https://localhost:8080/resto/api/employees/attendance/create

**Пример результата вызова API**


Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<attendance>
    <id>d9d8aa67-9e10-97ee-015e-f1879f9c5e87</id>
    <employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
    <roleId>6e3fa11d-3617-c735-bd29-aeac662741ed</roleId>
    <dateFrom>2017-10-08T10:00:00+03:00</dateFrom>
    <dateTo>2017-10-08T18:00:00+03:00</dateTo>
    <attendanceType>W</attendanceType>
    <comment/>
    <departmentId>2b602c10-2045-4f52-b5f9-d00be812d6aa</departmentId>
    <departmentName>ТП1</departmentName>
    <personalDateFrom>2017-10-08T18:00:00+03:00</personalDateFrom>
    <created>2017-10-09T09:26:22.731+03:00</created>
    <modified>2017-10-09T09:26:22.731+03:00</modified>
    <userModified>c831367e-778f-e80f-18f7-bd0843cd10c6</userModified>
</attendance>
```

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<attendance>
    <id>d9d8aa67-9e10-97ee-015e-f1879f9c5e87</id>
    <employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
    <roleId>6e3fa11d-3617-c735-bd29-aeac662741ed</roleId>
    <dateFrom>2017-10-08T10:00:00+03:00</dateFrom>
    <dateTo>2017-10-08T18:00:00+03:00</dateTo>
    <attendanceType>W</attendanceType>
    <comment/>
    <departmentId>2b602c10-2045-4f52-b5f9-d00be812d6aa</departmentId>
    <departmentName>ТП1</departmentName>
    <personalDateFrom>2017-10-08T18:00:00+03:00</personalDateFrom>
    <created>2017-10-09T09:26:22.731+03:00</created>
    <modified>2017-10-09T09:26:22.731+03:00</modified>
    <userModified>c831367e-778f-e80f-18f7-bd0843cd10c6</userModified>
</attendance>
```


## Удаление явки

Версия API: 1.0

Версия iiko: 5.0

| ![DELETE Request](/resources/Storage/api-documentations/http_request_delete.png) | https://host:port/resto/api/employees/attendance/byId/{attendanceUUID} |
| --- | --- |

### Что в ответе

Удаленная явка **attendance**.

### **Пример вызова**

https://localhost:8080/resto/api/employees/attendance/byId/d9d8aa67-9e10-97ee-015e-f1879f9c5e87

## Доступность сотрудников

## Получить доступность сотрудников

Версия API: 1.0

Версия iiko: 5.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/availability/list?from={YYYY-MM-DD}&to={YYYY-MM-DD}&department={departmentUUID}&role={roleUUID}&user={userUUID} |
| --- | --- |

### **Параметры запроса**

| **Параметр** | **Описание** |
| --- | --- |
| from | Дата начала отчета (включающая). |
| to | Дата окончания отчета (исключающая).<br><br>**Внимание!** Отрезки доступности будут сформированы по расписаниям на весь запрошенный интервал, то есть, следует использовать минимально необходимую дату (неделя/месяц вперед). |
| department | Id подразделения сотрудника для фильтрации. Можно задать параметр несколько раз. Если не задан ни один, отображаются данные по сотрудникам всех подразделений. |
| role | Id должности сотрудника для фильтрации. Можно задать параметр несколько раз. Если не задан ни один, отображаются данные по сотрудникам всех должностей. |
| user | Id сотрудника для фильтрации. Можно задать параметр несколько раз. Если не задан, отображаются данные по всем сотрудникам. |

### Что в ответе

Список отрезков доступности **availability**.

### **Пример вызова**

https://localhost:8080/resto/api/employees/availability/list?from=2017-09-01&to=2017-10-09&department=2b602c10-2045-4f52-b5f9-d00be812d6aa&role=6e3fa11d-3617-c735-bd29-aeac662741ed&user=0a508f8c-4cdb-4126-bd0d-243c4718c22f

**Пример результата вызова API**


Код

```
 <?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<availabilities>
    <availability>
        <employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
        <dateFrom>2017-09-01T00:00:00+03:00</dateFrom>
        <dateTo>2017-10-09T00:00:00+03:00</dateTo>
    </availability>
</availabilities>
```

Код

```
 <?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<availabilities>
    <availability>
        <employeeId>0a508f8c-4cdb-4126-bd0d-243c4718c22f</employeeId>
        <dateFrom>2017-09-01T00:00:00+03:00</dateFrom>
        <dateTo>2017-10-09T00:00:00+03:00</dateTo>
    </availability>
</availabilities>
```


## Описание сущностей для представления в формате XML (XSD-схема)
 [+] [Явки](javascript:void%280%29)
 [-] [Явки](javascript:void%280%29)
 
```
 %%CH%PRE6%%%%CH%PRE7%%
```

 [+] [Тип явки](javascript:void%280%29)
 [-] [Тип явки](javascript:void%280%29)
 
```
 %%CH%PRE8%%%%CH%PRE9%%
```
