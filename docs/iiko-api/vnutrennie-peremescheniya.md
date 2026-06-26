* [Внутренние перемещения](/articles/api-documentations/vnutrennie-peremescheniya/a/h2__350030460)
* [Описание полей](/articles/api-documentations/vnutrennie-peremescheniya/a/h3__1783388762)
* [Выгрузка документов](/articles/api-documentations/vnutrennie-peremescheniya/a/h2__1108447715)
* [Параметры запроса](/articles/api-documentations/vnutrennie-peremescheniya/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/vnutrennie-peremescheniya/a/h3_501454233)
* [Пример запроса и результат](/articles/api-documentations/vnutrennie-peremescheniya/a/h3_1561844723)
* [Выгрузка документа по идентификатору](/articles/api-documentations/vnutrennie-peremescheniya/a/h2__1311214437)
* [Параметры запроса](/articles/api-documentations/vnutrennie-peremescheniya/a/h3__1792186657)
* [Пример запроса и результата](/articles/api-documentations/vnutrennie-peremescheniya/a/h3_1387997121)
* [Выгрузка документов по номеру](/articles/api-documentations/vnutrennie-peremescheniya/a/h2_185847157)
* [Параметры запроса](/articles/api-documentations/vnutrennie-peremescheniya/a/h3__1842083848)
* [Пример запроса и результата](/articles/api-documentations/vnutrennie-peremescheniya/a/h3_201687932)
* [Запрос](/articles/api-documentations/vnutrennie-peremescheniya/a/h3_1966919031)
* [Результат](/articles/api-documentations/vnutrennie-peremescheniya/a/h3_631086644)
* [Создание/редактирование документа](/articles/api-documentations/vnutrennie-peremescheniya/a/h2_379129047)
* [Тело запроса](/articles/api-documentations/vnutrennie-peremescheniya/a/h3_1150399349)
* [Пример запроса и результата](/articles/api-documentations/vnutrennie-peremescheniya/a/h3__1280374078)

## Внутренние перемещения

Версия iiko: 7.9.3

###  Описание полей

### 
 [+] [InternalTransferDto](javascript:void%280%29)
 [-] [InternalTransferDto](javascript:void%280%29)
 | Поле | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | Идентификатор документа. |
| **dateIncoming** | String | Дата проведения документа (учетная) в формате "yyyy-MM-dd'T'HH:mm". |
| **documentNumber** | String | Учетный номер документа. |
| **status** | Enum | Статус документа.<br> | Значение | Описание |<br>| --- | --- |<br>| **NEW** | Новый. |<br>| **PROCESSED** | Проведенный. |<br>| **DELETED** | Удаленный. | |
| --- | --- | --- |
| **conceptionId** | UUID | Идентификатор концепции. |
| **comment** | String | Комментарий к документу. |
| **storeFromId** | UUID | Идентификатор склада, с которого происходит перемещение. |
| **storeToId** | UUID | Идентификатор склада, на который происходит перемещение. |
| **items** | List&lt;InternalTransferItemDto&gt; | Позиции документа. |
 [+] [InternalTransferItemDto](javascript:void%280%29)
 [-] [InternalTransferItemDto](javascript:void%280%29)
 
```

```
 
###  
 | Поле | Тип | Описание |
| --- | --- | --- |
| **num** | Integer | Позиция строки в документе. При создании/редактировании приказа не учитывается. |
| **productId** | UUID | Идентификатор продукта. |
| **amount** | BigDecimal | Количество продукта в единицах измерения продукта. |
| **measureUnitId** | UUID | Единицы измерения продукта на момент списания. Только чтение. |
| **containerId** | UUID | Идентификатор фасовки продукта. |
| **cost** | BigDecimal | Себестоимость для данного количества продукта. Только чтение. |
 
###  

## Выгрузка документов

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/documents/internalTransfer |
| --- | --- |

### Параметры запроса

| Параметр | Тип | Описание |
| --- | --- | --- |
| dateFrom | String | Начало временного интервала в формате "yyyy-MM-dd". Обязательный. |
| dateTo | String | Конец временного интервала в формате "yyyy-MM-dd". Обязательный. |
| status | Enum | Статус документа. Если не задан, то все. |
| revisionFrom | Integer | В ответе будут сущности с ревизией выше данной. По умолчанию '-1'. |

### Что в ответе
Список документов.
 
Поле revision - максимальная ревизия, доступная для выгрузки во внешние системы на момент запроса (это значит, что в базе присутствуют записи с такой ревизией, а записей с ревизией выше этой в базе нет).
 
Эту ревизию можно использовать в качестве параметра **revisionFrom** в следующем запросе на получение списка расписаний.

### Пример запроса и результат

#### Запрос

https://localhost:9080/resto/api/v2/documents/internalTransfer?dateFrom=2018-01-01&dateTo=2021-12-31
[+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```


## Выгрузка документа по идентификатору

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/documents/internalTransfer/byId |
| --- | --- |

### Параметры запроса

| Параметр | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | Идентификатор документа. |

### Пример запроса и результата

#### Запрос
https://localhost:9080/resto/api/v2/documents/internalTransfer/byId?id=f26f9661-c1c1-437e-b68a-e67cd78cc1a0

#### Результат


```json
{
  "id": "f26f9661-c1c1-437e-b68a-e67cd78cc1a0",
  "dateIncoming": "2021-04-01T12:08:36.340",
  "documentNumber": "20002",
  "status": "NEW",
  "storeFromId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
  "storeToId": "cfdfaff0-382c-4851-bba2-92b408db02ef",
  "items": [
    {
      "num": 1,
      "productId": "ccdada6c-1643-4c52-9e09-752a4de117a0",
      "amount": 20,
      "measureUnitId": "cd19b5ea-1b32-a6e5-1df7-5d2784a0549a",
      "containerId": "e2e67737-18bf-437b-8230-8ec17da75096",
      "cost": null                                                
      
    }
    
  ]
  
}
```

```json
{
  "id": "f26f9661-c1c1-437e-b68a-e67cd78cc1a0",
  "dateIncoming": "2021-04-01T12:08:36.340",
  "documentNumber": "20002",
  "status": "NEW",
  "storeFromId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
  "storeToId": "cfdfaff0-382c-4851-bba2-92b408db02ef",
  "items": [
    {
      "num": 1,
      "productId": "ccdada6c-1643-4c52-9e09-752a4de117a0",
      "amount": 20,
      "measureUnitId": "cd19b5ea-1b32-a6e5-1df7-5d2784a0549a",
      "containerId": "e2e67737-18bf-437b-8230-8ec17da75096",
      "cost": null                                                
      
    }
    
  ]
  
}
```


###  

## Выгрузка документов по номеру

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/documents/internalTransfer/byNumber |
| --- | --- |

### Параметры запроса

| Параметр | Тип | Описание |
| --- | --- | --- |
| **documentNumber** | String | Номер документа. |

### Пример запроса и результата

### Запрос
https://localhost:9080/resto/api/v2/documents/internalTransfer/byNumber?documentNumber=20002

### Результат


```json
[
  {
    "id": "f26f9661-c1c1-437e-b68a-e67cd78cc1a0",
    "dateIncoming": "2021-04-01T12:08:36.340",
    "documentNumber": "20002",
    "status": "NEW",
    "storeFromId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
    "storeToId": "cfdfaff0-382c-4851-bba2-92b408db02ef",
    "items": [
      {
        "num": 1,
        "productId": "ccdada6c-1643-4c52-9e09-752a4de117a0",
        "amount": 20,
        "measureUnitId": "cd19b5ea-1b32-a6e5-1df7-5d2784a0549a",
        "containerId": "e2e67737-18bf-437b-8230-8ec17da75096",
        "cost": null                                                    
      }
      
    ]
    
  }
  
]
```

```json
[
  {
    "id": "f26f9661-c1c1-437e-b68a-e67cd78cc1a0",
    "dateIncoming": "2021-04-01T12:08:36.340",
    "documentNumber": "20002",
    "status": "NEW",
    "storeFromId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
    "storeToId": "cfdfaff0-382c-4851-bba2-92b408db02ef",
    "items": [
      {
        "num": 1,
        "productId": "ccdada6c-1643-4c52-9e09-752a4de117a0",
        "amount": 20,
        "measureUnitId": "cd19b5ea-1b32-a6e5-1df7-5d2784a0549a",
        "containerId": "e2e67737-18bf-437b-8230-8ec17da75096",
        "cost": null                                                    
      }
      
    ]
    
  }
  
]
```


###  

## Создание/редактирование документа

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/documents/internalTransfer |
| --- | --- |

### Тело запроса
 
Если задан идентификатор документа - считаем, что это редактирование (редактировать приказ можно, если его статус 'NEW'), если не задан, то создание.
 
Обязательные поля: 'dateIncoming', 'status', 'storeFromId', 'storeToId'. Также должна быть как минимум одна позиция в документе.
 
Для позиций в документе обязательными являются поля 'productId', 'amount'.
 
Если при создании документа не задано поле 'documentNumber', оно сгенерится автоматически.
 

```json
{
  "id": "0fd6f4ad-4858-401c-017d-22eacb7101a7",
  "dateIncoming": "2021-11-15T06:00",
  "documentNumber": "30002",
  "status": "NEW",
  "comment": "zzz",
  "storeFromId": "05a407d4-d7c6-4bc2-a578-6ad5de99d468",
  "storeToId": "370620fe-c789-46db-9d92-33bec29b82a3",
  "items": [
    {
      "productId": "ccdada6c-1643-4c52-9e09-752a4de117a0",
      "amount": 5,
      "containerId": "e2e67737-18bf-437b-8230-8ec17da75096"                                                                        
    },
    {
      "productId": "8972b757-4e08-4c50-a145-80cd12bb4f1e",
      "amount": 5,
      "containerId": "84d13550-d3c8-4f73-8e35-2ae470260bdc"                                                                        
    }
    
  ]
  
}
```

```json
{
  "id": "0fd6f4ad-4858-401c-017d-22eacb7101a7",
  "dateIncoming": "2021-11-15T06:00",
  "documentNumber": "30002",
  "status": "NEW",
  "comment": "zzz",
  "storeFromId": "05a407d4-d7c6-4bc2-a578-6ad5de99d468",
  "storeToId": "370620fe-c789-46db-9d92-33bec29b82a3",
  "items": [
    {
      "productId": "ccdada6c-1643-4c52-9e09-752a4de117a0",
      "amount": 5,
      "containerId": "e2e67737-18bf-437b-8230-8ec17da75096"                                                                        
    },
    {
      "productId": "8972b757-4e08-4c50-a145-80cd12bb4f1e",
      "amount": 5,
      "containerId": "84d13550-d3c8-4f73-8e35-2ae470260bdc"                                                                        
    }
    
  ]
  
}
```

 
### Пример запроса и результата

#### Запрос

https://localhost:9080/resto/api/v2/documents/internalTransfer

#### Результат


```json
{
  "result": "SUCCESS",
  "errors": [
  ],
  "response": {
    "id": "0fd6f4ad-4858-401c-017d-22eacb7101a7",
    "dateIncoming": "2021-11-15T06:00",
    "documentNumber": "30002",
    "status": "NEW",
    "comment": "zzz",
    "storeFromId": "05a407d4-d7c6-4bc2-a578-6ad5de99d468",
    "storeToId": "370620fe-c789-46db-9d92-33bec29b82a3",
    "items": [
      {
        "num": 1,
        "productId": "ccdada6c-1643-4c52-9e09-752a4de117a0",
        "amount": 5,
        "measureUnitId": "cd19b5ea-1b32-a6e5-1df7-5d2784a0549a",
        "containerId": "e2e67737-18bf-437b-8230-8ec17da75096",
        "cost": null                                                                            
      },
      {
        "num": 2,
        "productId": "8972b757-4e08-4c50-a145-80cd12bb4f1e",
        "amount": 5,
        "measureUnitId": "cd19b5ea-1b32-a6e5-1df7-5d2784a0549a",
        "containerId": "84d13550-d3c8-4f73-8e35-2ae470260bdc",
        "cost": null                                                                            
      }
      
    ]
    
  }
  
}
```

```json
{
  "result": "SUCCESS",
  "errors": [
  ],
  "response": {
    "id": "0fd6f4ad-4858-401c-017d-22eacb7101a7",
    "dateIncoming": "2021-11-15T06:00",
    "documentNumber": "30002",
    "status": "NEW",
    "comment": "zzz",
    "storeFromId": "05a407d4-d7c6-4bc2-a578-6ad5de99d468",
    "storeToId": "370620fe-c789-46db-9d92-33bec29b82a3",
    "items": [
      {
        "num": 1,
        "productId": "ccdada6c-1643-4c52-9e09-752a4de117a0",
        "amount": 5,
        "measureUnitId": "cd19b5ea-1b32-a6e5-1df7-5d2784a0549a",
        "containerId": "e2e67737-18bf-437b-8230-8ec17da75096",
        "cost": null                                                                            
      },
      {
        "num": 2,
        "productId": "8972b757-4e08-4c50-a145-80cd12bb4f1e",
        "amount": 5,
        "measureUnitId": "cd19b5ea-1b32-a6e5-1df7-5d2784a0549a",
        "containerId": "84d13550-d3c8-4f73-8e35-2ae470260bdc",
        "cost": null                                                                            
      }
      
    ]
    
  }
  
}
```
