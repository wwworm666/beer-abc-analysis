* [Доступ](/articles/api-documentations/rabota-s-izyatiyami/a/v2.APIизъятия-Доступ)
* [Получение типов внесений и изъятий](/articles/api-documentations/rabota-s-izyatiyami/a/v2.APIизъятия-Получениетиповвнесенийиизъятий)
* [Параметры запроса](/articles/api-documentations/rabota-s-izyatiyami/a/v2.APIизъятия-Параметры)
* [Что в ответе](/articles/api-documentations/rabota-s-izyatiyami/a/v2.APIизъятия-Результат)
* [Пример запроса и результата](/articles/api-documentations/rabota-s-izyatiyami/a/h3__232688264)
* [Совершить изъятие](/articles/api-documentations/rabota-s-izyatiyami/a/v2.APIизъятия-Совершитьизъятие.)
* [Тело запроса](/articles/api-documentations/rabota-s-izyatiyami/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/rabota-s-izyatiyami/a/h3_501454233)
* [Пример вызова](/articles/api-documentations/rabota-s-izyatiyami/a/h3_2017789044)
* [Получение платежных ведомостей](/articles/api-documentations/rabota-s-izyatiyami/a/v2.APIизъятия-Получениеплатежныхведомостей)
* [Параметры запроса](/articles/api-documentations/rabota-s-izyatiyami/a/v2.APIкассовыесмены-Параметры)
* [Что в ответе](/articles/api-documentations/rabota-s-izyatiyami/a/v2.APIизъятия-Результат.2)
* [Пример запроса и результата](/articles/api-documentations/rabota-s-izyatiyami/a/h3_41887754)
* [Примеры изъятий](/articles/api-documentations/rabota-s-izyatiyami/a/h2_1154554098)
* [Изъятие. Платёжная ведомость](/articles/api-documentations/rabota-s-izyatiyami/a/h3__469280520)
* [Изъятие. Аванс поставщику](/articles/api-documentations/rabota-s-izyatiyami/a/h3__474185203)

## Доступ

Чтобы пользоваться API:

* Получения типов внесений и изъятий: право B\_APIO "Просматривать типы внесений/изъятий".
* Выполнения изъятий: право F\_APIO "Авторизовывать кассовые внесения и изъятия".

## Получение типов внесений и изъятий

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/entities/payInOutTypes/list |
| --- | --- |

### Параметры запроса
| **Название** | **Тип данных** | **Версия** | **Описание** |
| --- | --- | --- | --- |
| includeDeleted | Boolean |  | включая удаленные (по умолчанию false) |
| revisionFrom | -1, число | с 6.4 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |
### Что в ответе

Json структура. Возвращает список типов внесений и изъятий.

### 

| **Поле** | **Тип данных** | **Описание** |
| id | UUID | Guid внесения/изъятия в базе iiko. |
| chiefAccount | UUID | Guid шеф-счёта. При изъятии перемещаются на корр. счёт, а при внесении наоборот. |
| account | UUID | Guid корр-счёта. При изъятии перемещаются на корр. счёт, а при внесении наоборот. |
| counteragentType | Enum | Тип контрагента:<br><ul><li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">NONE (нет)</span></span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">COUNTERAGENT (все)</span></span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">EMPLOYEE (сотрудник)</span></span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">SUPPLIER (поставщик)</span></span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">CLIENT (гость)</span></span></span></li><li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">INTERNAL_SUPPLIER (внутренний поставщик)</span></span></span></li></ul> |
| transactionType | Enum | Тип проводки. |
| cashFlowCategory | DTO | Статья движения денежных средств (ДДС). |
| conception | DTO | Концепция<br> <br><br>| Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| id | String | Guid концепции в базе iiko. |<br>| code | String | Код. |<br>| name | String | Название. | |
| --- | --- | --- |
| limit | BigDecimal | Предельная сумма для внесений/изъятий на iikoFront. |
| comment | String | Комментарий |
| mandatoryFrontComment | Boolean | Требовать ввода комментария к операции в iikoFront. |
| isDeleted | Boolean | Удален |

### **Пример запроса и результата**

**Запрос**

https://localhost:8080/resto/api/v2/entities/payInOutTypes/list?includeDeleted=true

[+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```


## Совершить изъятие

Версия iiko: 6.0

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/payInOuts/addPayOut |
| --- | --- |

Content-Type: application/json

### Тело запроса

| Поле | Тип данных | Описание |
| --- | --- | --- |
| payOutTypeId | UUID | Guid типа изъятия в базе iiko. |
| payOutDate | String | Дата в формате yyyy-MM-dd. Время проставляется текущее. |
| counteragent | UUID | Guid контрагента в базе iiko. В зависимости от типа изъятия. |
| departmentSumMap | UUID -&gt; BigDecimal | Торговое предприятие -&gt; сумма изъятия. |
| payrollId | UUID | Guid платежной ведомости в базе iiko. Указывается если изъятие происходит на счет<br>(т.е. корр.счет) "Текущие расчеты с сотрудниками". |
| comment | String | Комментарий. |

### Что в ответе

Содержит результат изъятия, который состоит из результата валидации параметров изъятия и самого изъятия. Результат валидации состоит из ошибок. Ошибка состоит из кода ошибки и текста ошибки.

### 

| Поле | Тип данных | Значение |
| --- | --- | --- |
| result | Enum | SUCCESS, ERROR |
| payOutSettings | DTO | Параметры изъятия. |
| errors | DTO | Список ошибок, не позволивших сделать изъятие. |

### **Пример вызова**

**** https://localhost:8080/resto/api/v2/payInOuts/addPayOut

#### **Пример результата - SUCCESS**

**
```json
 { 
   "result":"SUCCESS",
   "errors":null,
   "payOutSettings":{ 
      "payOutTypeId":"37d410d1-c524-4a76-b28c-8b733e313d7a",
      "payOutDate":"2017-10-18",
      "counteragent":null,
      "departmentSumMap":{ 
         "06d7ec0c-8fee-f341-015f-b58127ff000d":1500
      },
      "payrollId":null,
      "comment":null
   }
}
```

```json
 { 
   "result":"SUCCESS",
   "errors":null,
   "payOutSettings":{ 
      "payOutTypeId":"37d410d1-c524-4a76-b28c-8b733e313d7a",
      "payOutDate":"2017-10-18",
      "counteragent":null,
      "departmentSumMap":{ 
         "06d7ec0c-8fee-f341-015f-b58127ff000d":1500
      },
      "payrollId":null,
      "comment":null
   }
}
```
**

#### **Пример результата - ERROR**

**
```json
{ 
   "result":"ERROR",
   "errors":[ 
      { 
         "value":"chiefAccount",
         "code":"ACCOUNT_NOT_SPECIFIED"
      }
   ],
   "payOutSettings":{ 
      "payOutTypeId":"32e01087-ded3-b5bb-4b82-6a3f0348af84",
      "payOutDate":"2017-10-18",
      "counteragent":null,
      "departmentSumMap":{ 
         "06d7ec0c-8fee-f341-015f-b58127ff000d":-100
      },
      "payrollId":null,
      "comment":null
   }
}
```

```json
{ 
   "result":"ERROR",
   "errors":[ 
      { 
         "value":"chiefAccount",
         "code":"ACCOUNT_NOT_SPECIFIED"
      }
   ],
   "payOutSettings":{ 
      "payOutTypeId":"32e01087-ded3-b5bb-4b82-6a3f0348af84",
      "payOutDate":"2017-10-18",
      "counteragent":null,
      "departmentSumMap":{ 
         "06d7ec0c-8fee-f341-015f-b58127ff000d":-100
      },
      "payrollId":null,
      "comment":null
   }
}
```
**

## Получение платежных ведомостей

Версия iiko: 6.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/payrolls/list |
| --- | --- |

### Параметры запроса

| Поле | Тип данных | Описание |
| --- | --- | --- |
| dateFrom | String | Начало периода в формате yyyy-MM-dd, включительно. |
| dateTo | String | Окончание периода в формате yyyy-MM-dd, включительно. |
| department | UUID | Guid торгового предприятия. в базе iiko. |
| includeDeleted | Boolean | Включая удаленные (по умолчанию false). |

### Что в ответе

Возвращает список платежных ведомостей.
| Поле | Тип данных | Описание |
| --- | --- | --- |
| payrollId | UUID | UUID ведомости. |
| dateFrom | Date | Дата начала действия. |
| dateTo | Date | Дата окончания действия. |
| department | UUID | Guid торгового предприятия. |
| documentNumber | String | Номер документа. |
| status | Enum | Статус документа (NEW, PROCESSED, DELETED). |
| comment | String | Комментарий. |

### **Пример запроса и результата**

**Запрос**
https://localhost:8080/resto/api/v2/payrolls/list?dateFrom=2017-08-01&dateTo=2017-10-01&department=372f68b4-8e7a-bae1-015f-0f9c638f000d

#### Результат


```json
[
    {
        "id": "d4b29bd7-076f-48ba-9f93-6f21b78f47bf",
        "dateFrom": "2017-10-01T00:00:00",
        "dateTo": "2017-10-31T23:59:59",
        "department": "372f68b4-8e7a-bae1-015f-0f9c638f000d",
        "documentNumber": "0001",
        "status": "PROCESSED",
        "comment": null
   }
]

```

```json
[
    {
        "id": "d4b29bd7-076f-48ba-9f93-6f21b78f47bf",
        "dateFrom": "2017-10-01T00:00:00",
        "dateTo": "2017-10-31T23:59:59",
        "department": "372f68b4-8e7a-bae1-015f-0f9c638f000d",
        "documentNumber": "0001",
        "status": "PROCESSED",
        "comment": null
   }
]

```


| ![Warning](/resources/Storage/api-documentations/api-documentations/warning.png) | Для использования кириллицы в комментарии (параметр comment) при совершении изъятия в headers запроса должен быть параметр: *content-type: application/json;charset=UTF-8* |
| --- | --- |

## Примеры изъятий

### **Изъятие. Платёжная ведомость**

**Запрос**

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://localhost:8080/resto/api/v2/payInOuts/addPayOut |
| --- | --- |


Код

```

{
"payOutTypeId":"114c757f-bac4-422c-a184-0935923b60b8",
"payOutDate":"2017-12-13",
"counteragent":"d244cb85-9115-4b4d-8e02-a4f7fdd8ec15",
"departmentSumMap":{
"2b9c2770-f146-43b8-9ac1-ad717d9c7996":90.0
},
"payrollId":"c1349656-8401-4476-9541-7f0325c65f98",
"comment":"Comment"
}
```

Код

```

{
"payOutTypeId":"114c757f-bac4-422c-a184-0935923b60b8",
"payOutDate":"2017-12-13",
"counteragent":"d244cb85-9115-4b4d-8e02-a4f7fdd8ec15",
"departmentSumMap":{
"2b9c2770-f146-43b8-9ac1-ad717d9c7996":90.0
},
"payrollId":"c1349656-8401-4476-9541-7f0325c65f98",
"comment":"Comment"
}
```


**Результат**


Код

```
{
"result": "SUCCESS",
"errors": null,
"payOutSettingsDto": {
"payOutTypeId": "114c757f-bac4-422c-a184-0935923b60b8",
"payOutDate": "2017-12-13",
"counteragent": "d244cb85-9115-4b4d-8e02-a4f7fdd8ec15",
"departmentSumMap": {"2b9c2770-f146-43b8-9ac1-ad717d9c7996": 90},
"payrollId": "c1349656-8401-4476-9541-7f0325c65f98",
"comment": "Comment "
}
}
```

Код

```
{
"result": "SUCCESS",
"errors": null,
"payOutSettingsDto": {
"payOutTypeId": "114c757f-bac4-422c-a184-0935923b60b8",
"payOutDate": "2017-12-13",
"counteragent": "d244cb85-9115-4b4d-8e02-a4f7fdd8ec15",
"departmentSumMap": {"2b9c2770-f146-43b8-9ac1-ad717d9c7996": 90},
"payrollId": "c1349656-8401-4476-9541-7f0325c65f98",
"comment": "Comment "
}
}
```


### **Изъятие. Аванс поставщику**

**Запрос**

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://localhost:8080/resto/api/v2/payInOuts/addPayOut |
| --- | --- |


Код

```

{
"payOutTypeId":"0cacd214-c280-4f58-afb3-28d25de90c21",
"payOutDate":"2017-12-13",
"counteragent":"ac716010-c95c-4705-a4bf-d202816c406e",
"departmentSumMap":{
"2b9c2770-f146-43b8-9ac1-ad717d9c7996":1000.0
},
"comment":"test1"
}
```

Код

```

{
"payOutTypeId":"0cacd214-c280-4f58-afb3-28d25de90c21",
"payOutDate":"2017-12-13",
"counteragent":"ac716010-c95c-4705-a4bf-d202816c406e",
"departmentSumMap":{
"2b9c2770-f146-43b8-9ac1-ad717d9c7996":1000.0
},
"comment":"test1"
}
```


**Результат**


Код

```
{
"result": "SUCCESS",
"errors": null,
"payOutSettingsDto": {
"payOutTypeId": "0cacd214-c280-4f58-afb3-28d25de90c21",
"payOutDate": "2017-12-13",
"counteragent": "ac716010-c95c-4705-a4bf-d202816c406e",
"departmentSumMap": {"2b9c2770-f146-43b8-9ac1-ad717d9c7996": 1000},
"payrollId": null,
"comment": "test1"
}
}
```

Код

```
{
"result": "SUCCESS",
"errors": null,
"payOutSettingsDto": {
"payOutTypeId": "0cacd214-c280-4f58-afb3-28d25de90c21",
"payOutDate": "2017-12-13",
"counteragent": "ac716010-c95c-4705-a4bf-d202816c406e",
"departmentSumMap": {"2b9c2770-f146-43b8-9ac1-ad717d9c7996": 1000},
"payrollId": null,
"comment": "test1"
}
}
```
