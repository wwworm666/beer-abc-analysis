* [Список смен](/articles/api-documentations/kassovye-smeny-v2/a/h2__1634510164)
* [Параметры запроса](/articles/api-documentations/kassovye-smeny-v2/a/v2.APIкассовыесмены-Параметры.1)
* [Что в ответе](/articles/api-documentations/kassovye-smeny-v2/a/h3_501454233)
* [Пример запроса и результат](/articles/api-documentations/kassovye-smeny-v2/a/h3_1561844723)
* [Выгрузка платежей, внесений, изъятий за смену](/articles/api-documentations/kassovye-smeny-v2/a/h2_1746421875)
* [Параметры запроса](/articles/api-documentations/kassovye-smeny-v2/a/v2.APIкассовыесмены-Параметры)
* [Что в ответе](/articles/api-documentations/kassovye-smeny-v2/a/v2.APIкассовыесмены-Результат)
* [Выгрузка кассовой смены по id](/articles/api-documentations/kassovye-smeny-v2/a/h2_775061847)
* [Что в ответе](/articles/api-documentations/kassovye-smeny-v2/a/v2.APIкассовыесмены-Результат.1)
* [Пример запроса и результат](/articles/api-documentations/kassovye-smeny-v2/a/h3__2016272752)
* [Выгрузка документы принятия кассовой смены по id смены](/articles/api-documentations/kassovye-smeny-v2/a/h2_1113421559)
* [Что в ответе](/articles/api-documentations/kassovye-smeny-v2/a/v2.APIкассовыесмены-Результат.2)
* [Пример запроса и результата](/articles/api-documentations/kassovye-smeny-v2/a/h3_316519999)
* [Принятие кассовой смены](/articles/api-documentations/kassovye-smeny-v2/a/v2.APIкассовыесмены-Принятиекассовойсмены)
* [Примерный алгоритм принятия кассовой смены](/articles/api-documentations/kassovye-smeny-v2/a/v2.APIкассовыесмены-Примерныйалгоритмпринятиякассовойсмены)
* [Тело запроса](/articles/api-documentations/kassovye-smeny-v2/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/kassovye-smeny-v2/a/h3_1772527967)
* [Ошибка](/articles/api-documentations/kassovye-smeny-v2/a/v2.APIкассовыесмены-ОшибкаОшибка)
* [Пример запроса и результат](/articles/api-documentations/kassovye-smeny-v2/a/h3_1387997121)

## Список смен

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/cashshifts/list |
| --- | --- |

### Параметры запроса
| Название | Значение | Описание |
| --- | --- | --- |
| openDateFrom | YYYY-MM-DD | Период открытия смены ''с'' (входит в интервал). |
| openDateTo | YYYY-MM-DD | Период открытия смены ''по'' (входит в интервал). |
| departmentId | UUID | Список ТП, если пуст, то фильтра нет. |
| groupId | UUID | Список групп секций, если пуст, то фильтра нет. |
| status | String<br>| Значение | Описание |<br>| --- | --- |<br>| ANY | Любая. |<br>| OPEN | Открытая. |<br>| CLOSED | Закрытая. |<br>| ACCEPTED | Принята. |<br>| UNACCEPTED | Не принята. |<br>| HASWARNINGS | Подозрительная. | | Фильтр по статусу. Не может быть пустым. |
| --- | --- | --- |
| revisionFrom | число, -1 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 (**с версии iiko 6.4**) |
### Что в ответе

Json структура. Возвращает списки смен
| Поле | Значение |
| --- | --- |
| id | Id смены |
| sessionNumber | Номер кассовый смены (в нумерации фронта). |
| fiscalNumber | Фискальный номер смены (с ФРа). |
| cashRegNumber | Номер ФРа (в нумерации iiko). |
| cashRegSerial | Серийный номер ФРа. |
| openDate | Дата открытия смены. |
| closeDate | Дата закрытия смены. |
| acceptDate | Дата принятия смены. null --- смена не принята. |
| managerId | Ответственный менеджер. |
| responsibleUser | Ответственный кассир. |
| sessionStartCash | Остаток в кассе на начало дня. |
| payOrders | Сумма всех заказов с учётом скидки |
| sumWriteoffOrders | Сумма заказов, закрытых за счет заведения. |
| salesCash | Сумма продаж за наличные. |
| salesCerdit | Сумма продаж в кредит. |
| salesCard | Сумма продаж по картам. |
| payIn | Сумма всех внесений. |
| payOut | Сумма всех изъятий, без учета изъятий в конце смены. |
| payIncome | Сумма изъятия в конце смены. |
| cashRemain | Остаток в кассе после закрытия смены. |
| cashDiff | Общее расхождение сумм книжных и фактических. |
| sessionStaus | Статус смены. |
| conception | Концепция, которой принадлежит данная кассовая смена. |
| pointOfSale | Точка продаж данной кассовой смены. |
###  **Пример запроса и результат**

```
%%CH%PRE0%%%%CH%PRE1%%


```

## Выгрузка платежей, внесений, изъятий за смену

Версия iiko: 5.4

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/**cashshifts/payments/list/{sessionId}** |
| --- | --- |

### Параметры запроса
| **Название** | **Значение** | **Описание** |
| --- | --- | --- |
| hideAccepted | true, false | скрыть принятые |
### Что в ответе

Json структура. Возвращает списки внесений, изъятий, безналичных платежей за смену
| Поле | Описание |
| --- | --- |
| sessionId | UUID запрошенной смены |
| cashlessRecords | Список записей, относящихся к безналичным платежам. |
| payInRecords | Список записей, относящихся к внесениям. |
| payOutRecords | Список записей, относящихся к изъятиям. || Запись в документе<br>| Поле | Описание |<br>| --- | --- |<br>| info | Описание проводки<br><br><br>| Поле | Описание |<br>| --- | --- |<br>| id | UUID проводки. |<br>| date | Дата создания в формате "yyyy-MM-dd'T'HH:MM:SS"<br><br>Проводки оплат заказов содержат в этом поле учетный день, округленный до суток. |<br>| creationDate | Дата создания в формате "yyyy-MM-dd'T'HH:MM:SS"<br>с привязкой ко времени, может быть меньше, чем date,<br>если используется настройка "конец учетного дня" &lt;&gt; 00:00. |<br>| group | группа проводок:<br><ul style="margin: 10px 0px 0px; padding-left: 22px;"><li><span style="font-size: 10pt;"><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">CARD (безнал)</span></span></span></span></li><li><span style="font-size: 10pt;"><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">CREDIT (кредит)</span></span></span></span></li><li><span style="font-size: 10pt;"><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">PAYOUT (изъятия)</span></span></span></span></li><li><span style="font-size: 10pt;"><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">PAYIN (внесения)</span></span></span></span></li></ul> |<br>| accountId | Редактируемый счет. Чаще принимается конечный счет проводки. |<br>| counteragentId | Контрагент. |<br>| paymentTypeId | Тип оплаты. |<br>| type | Тип проводки. |<br>| sum | Сумма. |<br>| comment | Комментарий. |<br>| auth | Авторизационные данные транзакции<br>| Поле | Описание |<br>| --- | --- |<br>| user | UUID пользователя. |<br>| card | Номер карты. | |<br>| --- | --- |<br>| causeEvenId | UUID события оплаты заказа. |<br>| cashierId | UUID кассира, совершившего проводку. |<br>| departmentId | UUID торгового предприятия. |<br>| cashFlowCategory | Статья движения денежных средств (ДДС).<br>| Поле | Описание |<br>| --- | --- |<br>| code | Код. |<br>| parentCategory | Родительская статья ДДС. |<br>| type | Тип деятельности:<br><ul style="margin: 10px 0px 0px; padding-left: 22px;"><li><span style="font-size: 10pt;"><span style="font-size: 10pt;"><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">OPERATIONAL (операционная)</span></span></span></span></span></li><li><span style="font-size: 10pt;"><span style="font-size: 10pt;"><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">INVESTMENT (инвестиционная)</span></span></span></span></span></li><li><span style="font-size: 10pt;"><span style="font-size: 10pt;"><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;"><span style="">FINANCE (финансовая)</span></span></span></span></span></li></ul> | |<br>| --- | --- | |<br>| --- | --- |<br>| actualSum | Сумма из элемента документа закрытия кассовой смены соответствующего данным проводки<br><br>или сумма из проводки, если такового не нашлось. |<br>| originalSum | Сумма проводки. |<br>| editedPayAccountId | Счет из элемента документа закрытия кассовой смены соответствующего данным проводки<br><br>или сумма из проводки, если такового не нашлось. Редактируемый счет. |<br>| originalPayAccountId | Счет, значение которого совпадает с editedPayAccountId. |<br>| payAgentId | Контрагент из элемента документа закрытия смены соответствующего данным проводки или<br><br>из транзакции, если такого элемента не нашлось. |<br>| paymentTypeId | Тип оплаты. |<br>| editableComment | Комментарий. | |
| --- |
**Пример запроса и результата**

**Запрос**

https://localhost:8080/resto/api/v2/cashshifts/payments/list/f67fea0a-90d4-427c-ac3d-b82c1582f7f9?hideAccepted=false
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 
```


```

## Выгрузка кассовой смены по id

Версия iiko: 5.4

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/cashshifts/byId/{sessionId} |
| --- | --- |

### Что в ответе

Json структура кассовой смены.

| Поле | Значение |
| --- | --- |
| id | Id смены |
| sessionNumber | Номер кассовый смены (в нумерации фронта). |
| fiscalNumber | Фискальный номер смены (с ФРа). |
| cashRegNumber | Номер ФРа (в нумерации iiko). |
| cashRegSerial | Серийный номер ФРа. |
| openDate | Дата открытия смены. |
| closeDate | Дата закрытия смены. |
| acceptDate | Дата принятия смены. null --- смена не принята. |
| managerId | Ответственный менеджер. |
| responsibleUser | Ответственный кассир. |
| sessionStartCash | Остаток в кассе на начало дня. |
| payOrders | Сумма всех заказов с учётом скидки |
| sumWriteoffOrders | Сумма заказов, закрытых за счет заведения. |
| salesCash | Сумма продаж за наличные. |
| salesCerdit | Сумма продаж в кредит. |
| salesCard | Сумма продаж по картам. |
| payIn | Сумма всех внесений. |
| payOut | Сумма всех изъятий, без учета изъятий в конце смены. |
| payIncome | Сумма изъятия в конце смены. |
| cashRemain | Остаток в кассе после закрытия смены. |
| cashDiff | Общее расхождение сумм книжных и фактических. |
| sessionStaus | Статус смены. |
| conception | Концепция, которой принадлежит данная кассовая смена. |
| pointOfSale | Точка продаж данной кассовой смены. |

### **Пример запроса и результат**

**Запрос**

https://localhost:8080/resto/api/v2/cashshifts/byId/1c81b65a-1b8a-428f-8a74-2c994a928a86


```

  [+] Результат
  [-] Результат

  
  
     %%CH%PRE4%%%%CH%PRE5%%
  

```

## Выгрузка документы принятия кассовой смены по id смены

Версия iiko: 5.4

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/**cashshifts/closedSessionDocument/{id}** |
| --- | --- |

### Что в ответе

Json структура документа принятия кассовой смены. Возвращает существующий документ, либо создает новый.
| Поле | Значение |
| --- | --- |
| id | id документа. |
| session | Кассовая смена<br>| Поле | Значение |<br>| --- | --- |<br>| sessionId | id смены. |<br>| groupId | id группы секций работающих в одной кассовой смене. |<br>| number | Номер смены. | |
| --- | --- |
| accountShortageId | Счет, на который записывается недостача. |
| counteragentShortageId | Контрагент, на которого записывается недостача. |
| accountSurplusId | Счет, на который записывается излишек. |
| counteragentSurplusId | Контрагент, на которого записывается излишек. |
| departmentId | Торговое предприятие кассовой смены. |
| items | Элементы/строки документа<br>| Поле | Значение |<br>| --- | --- |<br>| num | Номер элемента. |<br>| transactionId | UUID проводки. |<br>| sumReal | Отредактированная сумма. |<br>| accountOverrideId | Отредактированный счет. |<br>| counteragentOverrideId | Отредактированный контрагент. |<br>| status | Статус.<br>| Значение | Описание |<br>| --- | --- |<br>| ACCEPTED | принята |<br>| UNACCEPTED | не принята |<br>| HASWARNINGS | подозрительная | |<br>| --- | --- |<br>| comment | Комментарий. | |
| --- | --- |
### **Пример запроса и результата**

https://localhost:8080/resto/api/v2/cashshifts/closedSessionDocument/f67fea0a-90d4-427c-ac3d-b82c1582f7f9


```json
{ 
   "id":"1a94e9e8-56cf-3a14-015b-ce1629e5006b",
   "session":{ 
      "sessionId":"f67fea0a-90d4-427c-ac3d-b82c1582f7f9",
      "groupId":"94a6f400-2f9b-4a5a-be7f-19b7b62c55a7",
      "number":1
   },
   "accountShortageId":null,
   "counteragentShortageId":null,
   "accountSurplusId":null,
   "counteragentSurplusId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
   "departmentId":"cb90393a-8299-4af1-9fab-5ec308726266",
   "items":[ 
      { 
         "num":0,
         "transactionId":"e08a16b6-931c-4068-9aa5-b740d5ce726b",
         "sumReal":2660,
         "accountOverrideId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
         "counteragentOverrideId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
         "status":"ACCEPTED",
         "comment":"test"
      }
   ]
}
```

```json
{ 
   "id":"1a94e9e8-56cf-3a14-015b-ce1629e5006b",
   "session":{ 
      "sessionId":"f67fea0a-90d4-427c-ac3d-b82c1582f7f9",
      "groupId":"94a6f400-2f9b-4a5a-be7f-19b7b62c55a7",
      "number":1
   },
   "accountShortageId":null,
   "counteragentShortageId":null,
   "accountSurplusId":null,
   "counteragentSurplusId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
   "departmentId":"cb90393a-8299-4af1-9fab-5ec308726266",
   "items":[ 
      { 
         "num":0,
         "transactionId":"e08a16b6-931c-4068-9aa5-b740d5ce726b",
         "sumReal":2660,
         "accountOverrideId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
         "counteragentOverrideId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
         "status":"ACCEPTED",
         "comment":"test"
      }
   ]
}
```


## Принятие кассовой смены

### Примерный алгоритм принятия кассовой смены

1. Получить список кассовых смен. Выбрать id смены, которую нужно принять.
2. Получить документ принятия кассовой смены по id смены.
3. Получить список безналичных платежей, внесений, изъятий по выбранной из п.1 кассовой смене.
4. Дополнить список элементов документа недостающими.

Список из п.3 содержит все проводки смены. Документ принятия смены из п.2 состоит из элементов, редактирующих
такие проводок. Если есть проводки, для которых нет элементов в документе (например, когда смена закрывается впервые),
то нужно добавить новые элементы. Другими словами документ принятия смены должен содержать все проводки из п.3.

Добавление нового элемента происходит на основании записи из списка, полученного в п.3., следующим образом:

* В поле num устанавливается следующий порядковый номер.
* В поле transactionId устанавливается UUID добавляемой проводки.
* В поле sumReal указывается результат редактирования суммы проводки: поле sum. sumReal заполняется только для
изъятий. т.е. для записей из payOutRecords. Для других записей сумма не редактируется.

* В поле accountOverride устанавливаете результат редактирования счета из поля accountId. В counteragentOverride
результат редактирования counteragentId с некоторыми правилами.

* Указывается нужный статус и комментарий.

5. Отредактировать документ.

6. Отправить на сервер.

Версия iiko: 5.4

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/**cashshifts/save** |
| --- | --- |

Content-Type: application/json

### Тело запроса
| Поле | Значение |
| --- | --- |
| id | id документа. |
| session | Кассовая смена<br>| Поле | Значение |<br>| --- | --- |<br>| sessionId | id смены. |<br>| group | id группы секций работающих в одной кассовой смене. |<br>| number | Номер смены. | |
| --- | --- |
| accountShortageId | Счет, на который записывается недостача. |
| counteragentShortageId | Контрагент, на которого записывается недостача. |
| accountSurplusId | Счет, на который записывается излишек. |
| counteragentSurplusId | Контрагент, на которого записывается излишек.[1] |
| departmentId | Торговое предприятие кассовой смены. |
| items | Элементы/строки документа.<br><br>Элемент - продажа за безнал, внесение, изъятие.<br>| Поле | Значение |<br>| --- | --- |<br>| num | Номер элемента. |<br>| transactionId | UUID проводки кассовой смены. |<br>| sumReal | Отредактированная сумма. |<br>| accountOverrideId | Отредактированный счет. |<br>| counteragentOverrideId | Отредактированный контрагент.[2] |<br>| status | Статус.<br>| Значение | Описание |<br>| --- | --- |<br>| ACCEPTED | принята |<br>| UNACCEPTED | непринята |<br>| HASWARNINGS | подозрительная | |<br>| --- | --- |<br>| comment | Комментарий. | |
| --- | --- |
[1].Счета/контрагенты для недостачи/излишка должны быть заполнены независимо от выбранного счета.

Так сделано для обратной совместимости.

[2]. Контрагент в элементе документа должен быть указан только для счетов :
| Тип счета | Название |
| --- | --- |
| 
```
ACCOUNTS_RECEIVABLE
```
 | Задолженность покупателей |
| 
```
DEBTS_OF_EMPLOYEES
```
 | Задолженность сотрудников |
| 
```
EMPLOYEES_LIABILITY
```
 | Расчеты с сотрудниками |
| 
```
ACCOUNTS_PAYABLE
```
 | Расчеты с поставщиками |
| 
```
CLIENTS_LIABILITY
```
 | Расчеты с гостями |
Список доступных счетов можно получить через API счетов.


```json
{ 
   "id":"1a94e9e8-56cf-3a14-015b-ce1629e5006b",
   "session":{ 
      "sessionId":"f67fea0a-90d4-427c-ac3d-b82c1582f7f9",
      "groupId":"94a6f400-2f9b-4a5a-be7f-19b7b62c55a7",
      "number":1
   },
   "accountShortageId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
   "counteragentShortageId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
   "accountSurplusId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
   "counteragentSurplusId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
   "departmentId":"cb90393a-8299-4af1-9fab-5ec308726266",
   "items":[ 
      { 
         "num":0,
         "transactionId":"e08a16b6-931c-4068-9aa5-b740d5ce726b",
         "sumReal":2650,
         "accountOverrideId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
         "counteragentOverrideId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
         "status":"ACCEPTED",
         "comment":"test"
      }
   ]
}
```

```json
{ 
   "id":"1a94e9e8-56cf-3a14-015b-ce1629e5006b",
   "session":{ 
      "sessionId":"f67fea0a-90d4-427c-ac3d-b82c1582f7f9",
      "groupId":"94a6f400-2f9b-4a5a-be7f-19b7b62c55a7",
      "number":1
   },
   "accountShortageId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
   "counteragentShortageId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
   "accountSurplusId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
   "counteragentSurplusId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
   "departmentId":"cb90393a-8299-4af1-9fab-5ec308726266",
   "items":[ 
      { 
         "num":0,
         "transactionId":"e08a16b6-931c-4068-9aa5-b740d5ce726b",
         "sumReal":2650,
         "accountOverrideId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
         "counteragentOverrideId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
         "status":"ACCEPTED",
         "comment":"test"
      }
   ]
}
```


### Что в ответе

Содержит результат импорта, который состоит из результата валидации импортируемого документа и самого документа. Результат валидации состоит из ошибок, общих для всего документа, и ошибок по каждому отдельному элементу документа. Ошибка состоит из кода ошибки и текста ошибки.

| Поле | Значение |
| --- | --- |
| importResult | Статус результата принятия смены<br><br>SUCCESS, ERROR |
| status | Статус принятой смены. Вычисляется из совокупности статусов элементов документа.<br><br>Статус элемента задает пользователь. Если хотя бы один элемент имеет статус HASWARNINGS,<br><br>то весь документ будет в статусе HASWARNINGS, если хотя бы один элемент в статусе UNACCEPTED,<br><br>то весь документ будет в таком же статусе, ACCEPTED - все элементы приняты.<br><br>У HASWARNINGS самый высокий приоритет.<br>| Значение | Описание |<br>| --- | --- |<br>| UNACCEPTED | не принята |<br>| ACCEPTED | принята |<br>| HASWARNINGS | подозрительна | |
| --- | --- |
| errors | Список ошибок, не позволивших сделать успешный импорт документа.<br>| Поле | Значение |<br>| --- | --- |<br>| documentError | Ошибки в полях документа. |<br>| itemError | Ошибки в полях документа.<br>| Поле | Значение |<br>| --- | --- |<br>| identifier | UUID элемента. |<br>| error | Ошибка. | |<br>| --- | --- | |
| --- | --- |
| document | Импортируемый документ. |
### Ошибка
| Поле | Значение |
| --- | --- |
| value | Неверное значение, либо название пустого поля. |
| code | Код ошибки. |
### 
 [+] [Коды ошибок](javascript:void%280%29)
 [-] [Коды ошибок](javascript:void%280%29)
 | Код | Описание |
| --- | --- |
| ACCOUNT\_DELETED | Указанный счет удален. |
| COUNTERAGENT\_DELETED | Указанный контрагент удален. |
| INVENTORY\_ASSETS\_TYPE\_NOT\_ALLOWED | Счета категории "складские запасы" не допускаются. |
| COUNTERAGENT\_MISSED\_FOR\_ACCOUNT | Для указанного счета должен быть указан контрагент. |
| COUNTERAGENT\_NOT\_ALLOWED\_FOR\_ACCOUNT | Для указанного счета контрагент не указывается. |
| ACCOUNT\_NOT\_SPECIFIED | Счет не указан. |
| COUNTERAGENT\_NOT\_SPECIFIED | Контрагент не указан. |
| COUNTERAGENT\_NOT\_ALLOWED | Контрагент НЕ указывается. |
| COUNTERAGENT\_TYPE\_WRONG | Указан неверный тип для выбранного контрагента. |
| CONCEPTION\_NOT\_SPECIFIED | Концепция не указана. |
| CONCEPTION\_DELETED | Концепция удалена. |
| PAYROLL\_MISSED\_FOR\_ACCOUNT | Для указанного счета должен быть указана платежная ведомость. |
| PAYROLL\_DELETED | Платежная ведомость удалена. |
| ONLY\_POSITIVE\_VALUES\_ALLOWED | Допускаются только положительные значения. |
| DEPARTMENT\_DELETED | ТП удалено. |
| RESTAURANT\_SECTION\_DELETED | Отделение удалено. |
| MEASURE\_UNIT\_DELETED | Единица измерения удалена. |
| COOKING\_PLACE\_DELETED | Место приготовления удалено. |
| TAX\_CATEGORY\_DELETED | Налоговая категория удалена. |
| PRODUCT\_CATEGORY\_DELETED | Пользовательская категория удалена. |
| PRODUCT\_GROUP\_DELETED | Номенклатурная группа удалена. |
| PRODUCT\_DELETED | Товар удален. |
| PRODUCT\_MISSED | Товар не указан. |
| COOKING\_PLACE\_EMPTY\_FOR\_SALE\_DISH | Товар продается. Тип места приготовления не может быть пустым. |
| WRONG\_NOMENCLATURE\_TYPE | Указан недопустимый тип номенклатуры. |
| NOT\_INCLUDED\_IN\_MENU\_WITH\_EXCLUDED\_SECTIONS | У блюда указаны отделения, в которых его нельзя продавать, в то время, как <br>само блюдо не включено в меню по умолчанию. |
| CHILD\_MODIFIERS\_NOT\_ALLOWED | Вложенные модификаторы не допускаются. |
| MODIFIER\_NOT\_BELONGS\_TO\_GROUP | Модификатор не принадлежит группе. |
| NOT\_MODIFIER | Не является модификатором. |
| WRONG\_MIN\_MAX\_AMOUNT | Не правильно указаны минимальное, максимальное значение. |
| HAS\_RESTRICTION\_AND\_DEFAULT\_AMOUNT\_OUT\_OF\_RANGE | У родительского модификатора **ВКЛЮЧЕНО** "Ограничение на минимум и максимум у дочерних модификаторов",<br>но дефолтное значение у дочернего модификатора выходит за рамки мин. макс. значений. |
| DEFAULT\_AMOUNT\_OUT\_OF\_RANGE | Дефолтное значение выходит за рамки мин. макс. значений. |
| NO\_RESTRICTION\_AND\_MIN\_MAX\_NOT\_ZERO | У родительского модификатора **ВЫКЛЮЧЕНО** "Ограничение на минимум и максимум у дочерних модификаторов",<br>у дочернего мин. макс. количество не равно 0 (а должно). |
| REQUIRED\_AND\_WRONG\_MIN\_AMOUNT | Модификатор является обязательным, но мин. количество = 0, <br>либо НЕ является обязательным и мин. количество != 0.<br><br>Начиная с версии iiko 6.2.3 ошибка с таким кодом прилететь не может, т.к. поле **required** было убрано из ChoiceBindingDto |
| FREE\_OF\_CHARGE\_AMOUNT\_MORE\_THAN\_MAX | У группового или одиночного модификатора количество бесплатных больше чем максимальное. |
| HAS\_RESTRICTION\_AND\_FREE\_OF\_CHARGE\_MORE\_THAN\_MAX | У родительского модификатора **ВКЛЮЧЕНО** "Ограничение на минимум и максимум у дочерних модификаторов", но <br>бесплатное количество у дочернего модификатора больше максимального. |
| HAS\_RESTRICTION\_AND\_FREE\_OF\_CHARGE\_MORE\_THAN\_PARENT | У родительского модификатора **ВКЛЮЧЕНО** "Ограничение на минимум и максимум у дочерних модификаторов", но <br>бесплатное количество у дочернего модификатора больше чем у родительского. |
| NO\_RESTRICTION\_AND\_FREE\_OF\_CHARGE\_AMOUNT\_NOT\_EQUAL\_VALUE\_IN\_PARENT | У родительского модификатора **ВЫКЛЮЧЕНО** "Ограничение на минимум и максимум у дочерних модификаторов", но<br>бесплатное количество у дочернего модификатора не равно бесплатному количеству в родительском. |
| NO\_RESTRICTION\_AND\_REQUIRED\_SHOULD\_BE\_FALSE | У родительского модификатора **ВЫКЛЮЧЕНО** "Ограничение на минимум и максимум у дочерних модификаторов",<br>но дочерний модификатор является обязательным. |
| NOT\_GROUP\_MODIFIER\_HAS\_CHILD\_RESTRICTION | У **НЕ** группового (одиночного, дочернего) модификатора **ВКЛЮЧЕНО** "Ограничение на минимум и максимум у дочерних модификаторов". |
| SINGLE\_MODIFIER\_HIDE\_DEFAULT\_AMOUNT | У одиночного модификатора<br><br>"Скрывать, если кол-во по умолчанию". |
| PARENT\_AMOUNT\_BY\_DEFAULT\_NOT\_EQUAL\_SUM\_OF\_CHILDREN | У родительского модификатора кол-во по умолчанию не равно сумме дефолтный значений дочерних элементов. |
| IMAGE\_NOT\_FOUND | Изображение не найдено. | 
```


```


### **Пример запроса и результат**

**Запрос**


```
https://localhost:8080/resto/api/v2/cashshifts/save 

```

#### Результат

```
%%CH%PRE10%%%%CH%PRE11%%
​
```


#### Пример успешного импорта - **SUCCESS**

**
```json
{ 
   "importResult":"SUCCESS",
   "status":"ACCEPTED",
   "errors":null,
   "document":{ 
      "id":"1a94e9e8-56cf-3a14-015b-ce1629e5006b",
      "session":{ 
         "sessionId":"f67fea0a-90d4-427c-ac3d-b82c1582f7f9",
         "groupId":"94a6f400-2f9b-4a5a-be7f-19b7b62c55a7",
         "number":1
      },
      "accountShortageId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
      "counteragentShortageId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
      "accountSurplusId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
      "counteragentSurplusId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
      "departmentId":"cb90393a-8299-4af1-9fab-5ec308726266",
      "items":[ 
         { 
            "num":0,
            "transactionId":"e08a16b6-931c-4068-9aa5-b740d5ce726b",
            "sumReal":2650,
            "accountOverrideId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
            "counteragentOverrideId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
            "status":"ACCEPTED",
            "comment":"test"
         }
      ]
   }
}
```

```json
{ 
   "importResult":"SUCCESS",
   "status":"ACCEPTED",
   "errors":null,
   "document":{ 
      "id":"1a94e9e8-56cf-3a14-015b-ce1629e5006b",
      "session":{ 
         "sessionId":"f67fea0a-90d4-427c-ac3d-b82c1582f7f9",
         "groupId":"94a6f400-2f9b-4a5a-be7f-19b7b62c55a7",
         "number":1
      },
      "accountShortageId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
      "counteragentShortageId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
      "accountSurplusId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
      "counteragentSurplusId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
      "departmentId":"cb90393a-8299-4af1-9fab-5ec308726266",
      "items":[ 
         { 
            "num":0,
            "transactionId":"e08a16b6-931c-4068-9aa5-b740d5ce726b",
            "sumReal":2650,
            "accountOverrideId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
            "counteragentOverrideId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
            "status":"ACCEPTED",
            "comment":"test"
         }
      ]
   }
}
```
**

#### `Пример не успешного импорта - ``ERROR`

`
```json
{ 
   "importResult":"ERROR",
   "status":null,
   "errors":{ 
      "documentError":[ 
         { 
            "value":"ad3cc1aa-a60c-c85c-e66d-3904490de4b9",
            "code":"ACCOUNT_SHORTAGE_NOT_FOUND"
         },
         { 
            "value":"counteragentShortage",
            "code":"EMPTY_FIELD"
         }
      ],
      "itemError":[ 
         { 
            "identifier":0,
            "error":[ 
               { 
                  "value":"bd3cc1aa-a60e-c85c-e66d-3904490de4b9",
                  "code":"INVENTORY_ASSETS_TYPE_NOT_ALLOWED"
               },
               { 
                  "value":"6c6f7e76-2fee-473e-879e-4c4c2faaa032",
                  "code":"COUNTERAGENT_DELETED"
               }
            ]
         }
      ]
   },
   "document":{ 
      "id":"1a94e9e8-56cf-3a14-015b-ce1629e5006b",
      "session":{ 
         "sessionId":"f67fea0a-90d4-427c-ac3d-b82c1582f7f9",
         "group":"94a6f400-2f9b-4a5a-be7f-19b7b62c55a7",
         "number":1
      },
      "accountShortageId":"ad3cc1aa-a60c-c85c-e66d-3904490de4b9",
      "counteragentShortageId":null,
      "accountSurplusId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
      "counteragentSurplusId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
      "departmentId":"cb90393a-8299-4af1-9fab-5ec308726266",
      "items":[ 
         { 
            "num":0,
            "transactionId":"e08a16b6-931c-4068-9aa5-b740d5ce726b",
            "sumReal":2650,
            "accountOverrideId":"bd3cc1aa-a60e-c85c-e66d-3904490de4b9",
            "counteragentOverrideId":"6c6f7e76-2fee-473e-879e-4c4c2faaa032",
            "status":"HASWARNINGS",
            "comment":"test"
         }
      ]
   }
}
```

```json
{ 
   "importResult":"ERROR",
   "status":null,
   "errors":{ 
      "documentError":[ 
         { 
            "value":"ad3cc1aa-a60c-c85c-e66d-3904490de4b9",
            "code":"ACCOUNT_SHORTAGE_NOT_FOUND"
         },
         { 
            "value":"counteragentShortage",
            "code":"EMPTY_FIELD"
         }
      ],
      "itemError":[ 
         { 
            "identifier":0,
            "error":[ 
               { 
                  "value":"bd3cc1aa-a60e-c85c-e66d-3904490de4b9",
                  "code":"INVENTORY_ASSETS_TYPE_NOT_ALLOWED"
               },
               { 
                  "value":"6c6f7e76-2fee-473e-879e-4c4c2faaa032",
                  "code":"COUNTERAGENT_DELETED"
               }
            ]
         }
      ]
   },
   "document":{ 
      "id":"1a94e9e8-56cf-3a14-015b-ce1629e5006b",
      "session":{ 
         "sessionId":"f67fea0a-90d4-427c-ac3d-b82c1582f7f9",
         "group":"94a6f400-2f9b-4a5a-be7f-19b7b62c55a7",
         "number":1
      },
      "accountShortageId":"ad3cc1aa-a60c-c85c-e66d-3904490de4b9",
      "counteragentShortageId":null,
      "accountSurplusId":"ad3cc1aa-a60e-c85c-e66d-3904490de4b9",
      "counteragentSurplusId":"2c6f7e76-2fee-473e-879e-4c4c2faaa032",
      "departmentId":"cb90393a-8299-4af1-9fab-5ec308726266",
      "items":[ 
         { 
            "num":0,
            "transactionId":"e08a16b6-931c-4068-9aa5-b740d5ce726b",
            "sumReal":2650,
            "accountOverrideId":"bd3cc1aa-a60e-c85c-e66d-3904490de4b9",
            "counteragentOverrideId":"6c6f7e76-2fee-473e-879e-4c4c2faaa032",
            "status":"HASWARNINGS",
            "comment":"test"
         }
      ]
   }
}
```
​`
