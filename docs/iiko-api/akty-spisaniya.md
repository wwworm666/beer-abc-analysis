* [Акты списания](/articles/api-documentations/akty-spisaniya/a/h2_67639220)
* [Описание полей](/articles/api-documentations/akty-spisaniya/a/h3__1783388762)
* [Выгрузка документов](/articles/api-documentations/akty-spisaniya/a/h2__1108447715)
* [Параметры запроса](/articles/api-documentations/akty-spisaniya/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/akty-spisaniya/a/h3_501454233)
* [Пример запроса и результат](/articles/api-documentations/akty-spisaniya/a/h3__2087356861)
* [Выгрузка документа по идентификатору](/articles/api-documentations/akty-spisaniya/a/h2__1311214437)
* [Параметры запроса](/articles/api-documentations/akty-spisaniya/a/h3__2039552173)
* [Что в ответе](/articles/api-documentations/akty-spisaniya/a/h3_1890729610)
* [Пример запроса и результат](/articles/api-documentations/akty-spisaniya/a/h3_1561844723)
* [Выгрузка документов по номеру](/articles/api-documentations/akty-spisaniya/a/h2_185847157)
* [Параметры запроса](/articles/api-documentations/akty-spisaniya/a/h3__1893544037)
* [Примеры запроса и результат](/articles/api-documentations/akty-spisaniya/a/h3__1274244974)
* [Создание/редактирование документа](/articles/api-documentations/akty-spisaniya/a/h2_379129047)
* [Тело запроса](/articles/api-documentations/akty-spisaniya/a/h3_1150399349)
* [Пример запроса и результат](/articles/api-documentations/akty-spisaniya/a/h3_253998256)

## Акты списания

Версия iiko: 7.9.3
###  Описание полей 
 [+] [WriteoffDocumentDto](javascript:void%280%29)
 [-] [WriteoffDocumentDto](javascript:void%280%29)
 
```

```
 
###  
 | Поле | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | Идентификатор документа. |
| **dateIncoming** | String | Дата проведения документа (учетная) в формате "yyyy-MM-dd'T'HH:mm". |
| **documentNumber** | String | Учетный номер документа. |
| **status** | Enum | Статус документа.<br> | Значение | Описание |<br>| --- | --- |<br>| **NEW** | Новый. |<br>| **PROCESSED** | Проведенный. |<br>| **DELETED** | Удаленный. | |
| --- | --- | --- |
| **conceptionId** | UUID | Идентификатор концепции. |
| **comment** | String | Комментарий к документу. |
| **storeId** | UUID | Идентификатор склада, с которого происходит списывание. |
| **accountId** | UUID | Идентификатор счета, на который будет списана стоимость товара. |
| **externalOutgoingInvoiceId** | UUID | Идентификатор расходной накладной с externalStore, если идет списание со склада с отмеченным параметром "Списывать с внешнего склада". |
| **externalProductionDocumentId** | UUID | Идентификатор акта приготовления, если при проводке этого документа был сгенерирован акт приготовления. |
| **items** | List&lt;WriteoffDocumentItemDto&gt; | Позиции документа. |
 
###
 [+] [WriteoffDocumentItemDto](javascript:void%280%29)
 [-] [WriteoffDocumentItemDto](javascript:void%280%29)
 ###  
 | Поле | Тип | Описание |
| --- | --- | --- |
| **num** | Integer | Позиция строки в документе. При создании/редактировании приказа не учитывается. |
| **productId** | UUID | Идентификатор продукта. |
| **productSizeId** | UUID | Идентификатор размера продукта. |
| **amountFactor** | BigDecimal | Коэффициент списания. |
| **amount** | BigDecimal | Количество продукта в единицах измерения продукта. |
| **measureUnitId** | UUID | Единицы измерения продукта на момент списания. |
| **containerId** | UUID | Идентификатор фасовки продукта. |
| **cost** | BigDecimal | Себестоимость для данного количества продукта. Только чтение. |
 
## Выгрузка документов

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/**documents/writeoff** |
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
https://localhost:9080/resto/api/v2/documents/writeoff?dateFrom=2018-01-01&dateTo=2021-12-31

[+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
### 

## Выгрузка документа по идентификатору

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/**documents/writeoff/byId** |
| --- | --- |

### Параметры запроса

| Параметр | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | Идентификатор документа. |

### Что в ответе

Выгруженный документ

### Пример запроса и результат

#### Запрос

https://localhost:9080/resto/api/v2/documents/writeoff/byId?id=3d27d640-d6a1-4545-86a4-b07422c3c9f0

#### Результат


```json
{
  "id": "3d27d640-d6a1-4545-86a4-b07422c3c9f0",
  "dateIncoming": "2020-01-10T23:00",
  "documentNumber": "20002",
  "status": "PROCESSED",
  "storeId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
  "accountId": "97036ddb-b2e1-cd47-1669-c145daa9f9c5",
  "items": [
    {
      "num": 1,
      "productId": "31e6155c-e842-448f-8266-1d05eb8e977a",
      "productSizeId": null,
      "amountFactor": 1,
      "amount": 2,
      "measureUnitId": "6040d92d-e286-f4f9-a613-ed0e6fd241e1",
      "containerId": null,
      "cost": 0                                                
    }
    
  ]
  
}
```

```json
{
  "id": "3d27d640-d6a1-4545-86a4-b07422c3c9f0",
  "dateIncoming": "2020-01-10T23:00",
  "documentNumber": "20002",
  "status": "PROCESSED",
  "storeId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
  "accountId": "97036ddb-b2e1-cd47-1669-c145daa9f9c5",
  "items": [
    {
      "num": 1,
      "productId": "31e6155c-e842-448f-8266-1d05eb8e977a",
      "productSizeId": null,
      "amountFactor": 1,
      "amount": 2,
      "measureUnitId": "6040d92d-e286-f4f9-a613-ed0e6fd241e1",
      "containerId": null,
      "cost": 0                                                
    }
    
  ]
  
}
```

## Выгрузка документов по номеру

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/**documents/writeoff/byNumber** |
| --- | --- |

### Параметры запроса
| Параметр | Тип | Описание |
| --- | --- | --- |
| **documentNumber** | String | Номер документа. |

### Примеры запроса и результат

#### Запрос
https://localhost:9080/resto/api/v2/documents/writeoff/byNumber?documentNumber=20002

#### Результат


```json
[
  {
    "id": "3d27d640-d6a1-4545-86a4-b07422c3c9f0",
    "dateIncoming": "2020-01-10T23:00",
    "documentNumber": "20002",
    "status": "PROCESSED",
    "storeId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
    "accountId": "97036ddb-b2e1-cd47-1669-c145daa9f9c5",
    "items": [
      {
        "num": 1,
        "productId": "31e6155c-e842-448f-8266-1d05eb8e977a",
        "productSizeId": null,
        "amountFactor": 1,
        "amount": 2,
        "measureUnitId": "6040d92d-e286-f4f9-a613-ed0e6fd241e1",
        "containerId": null,
        "cost": 0                                                    
      }
      
    ]
    
  }
  
]
```

```json
[
  {
    "id": "3d27d640-d6a1-4545-86a4-b07422c3c9f0",
    "dateIncoming": "2020-01-10T23:00",
    "documentNumber": "20002",
    "status": "PROCESSED",
    "storeId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
    "accountId": "97036ddb-b2e1-cd47-1669-c145daa9f9c5",
    "items": [
      {
        "num": 1,
        "productId": "31e6155c-e842-448f-8266-1d05eb8e977a",
        "productSizeId": null,
        "amountFactor": 1,
        "amount": 2,
        "measureUnitId": "6040d92d-e286-f4f9-a613-ed0e6fd241e1",
        "containerId": null,
        "cost": 0                                                    
      }
      
    ]
    
  }
  
]
```


## Создание/редактирование документа

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/**documents/writeoff** |
| --- | --- |

### Тело запроса
 
Если задан идентификатор документа - считаем, что это редактирование (редактировать приказ можно, если его статус 'NEW'), если не задан, то создание.
 
Обязательные поля: 'dateIncoming', 'status', 'storeId', 'accountId'. Также должна быть как минимум одна позиция в документе.
 
Для позиций в документе обязательными являются поля 'productId', 'amount'.
 
Если при создании документа не задано поле 'documentNumber', оно сгенерится автоматически.
 

```json
{
  "dateIncoming": "2021-11-16T23:00",
  "status": "NEW",
  "comment": "yyy",
  "storeId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
  "accountId": "8c46f55a-0698-4e3f-8703-8bb36b24e8ac",
  "items": [
    {
      "productId": "50cedffc-04e9-aa79-016b-d1f9c56122e8",
      "amount": 1                                                                        
    }
    
  ]
  
}
```

```json
{
  "dateIncoming": "2021-11-16T23:00",
  "status": "NEW",
  "comment": "yyy",
  "storeId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
  "accountId": "8c46f55a-0698-4e3f-8703-8bb36b24e8ac",
  "items": [
    {
      "productId": "50cedffc-04e9-aa79-016b-d1f9c56122e8",
      "amount": 1                                                                        
    }
    
  ]
  
}
```

 
### 

### Пример запроса и результат

#### Запрос

https://localhost:9080/resto/api/v2/documents/writeoff
 
#### Результат


```json
{
  "result": "SUCCESS",
  "errors": [
  ],
  "response": {
    "id": "78e58a66-1648-e023-017d-28c01da501cc",
    "dateIncoming": "2021-11-16T23:00",
    "documentNumber": "",
    "status": "NEW",
    "comment": "yyy",
    "storeId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
    "accountId": "8c46f55a-0698-4e3f-8703-8bb36b24e8ac",
    "items": [
      {
        "num": 1,
        "productId": "50cedffc-04e9-aa79-016b-d1f9c56122e8",
        "productSizeId": null,
        "amountFactor": 1,
        "amount": 1,
        "measureUnitId": "6040d92d-e286-f4f9-a613-ed0e6fd241e1",
        "containerId": null,
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
    "id": "78e58a66-1648-e023-017d-28c01da501cc",
    "dateIncoming": "2021-11-16T23:00",
    "documentNumber": "",
    "status": "NEW",
    "comment": "yyy",
    "storeId": "7954d76d-6177-402c-ba2a-cc0ff16486fa",
    "accountId": "8c46f55a-0698-4e3f-8703-8bb36b24e8ac",
    "items": [
      {
        "num": 1,
        "productId": "50cedffc-04e9-aa79-016b-d1f9c56122e8",
        "productSizeId": null,
        "amountFactor": 1,
        "amount": 1,
        "measureUnitId": "6040d92d-e286-f4f9-a613-ed0e6fd241e1",
        "containerId": null,
        "cost": null                                                                            
      }
      
    ]
    
  }
  
}
```
