Рассмотрим пример настройки комбо-блюд и создание такого заказа через API.

* Создадим акцию в iiko.biz.![](/resources/Storage/api-documentations/order-with-combos-2019-06-20.png)
* Добавим блюдо «Боксмастер с картошкой» с фиксированной ценой 120 руб. Оно состоит из двух отдельных блюд.

![](/resources/Storage/api-documentations/order-with-combos-2019-06-20-1.png)

![](/resources/Storage/api-documentations/order-with-combos-2019-06-20-2.png)

 * Запросим список комбо через API.
 
GET-запрос:

https://iiko.biz:9900/api/0/orders/get\_combos\_info?access\_token=nOt79Q6RqQhL4ZdIGfGQUyNZfCHWLfADVBZQm9koxZDhaV6gVBDS\_fiaYTW-yZd9ISbhFcSPtljeaYMWV8e-dA2&organization=f20594c6-2da7-11e8-80e0-d8d38565926f

результат:


```json
{
            "categoryId": null,
            "groups": [
                {
                    "id": "060e8d59-2e33-4117-85a9-1823792c6dee",//ID комбо группы
                    "name": "группа боксмастер",
                    "products": [
                        {
                            "code": "00076",
                            "forbiddenModifiersCodes": [],
                            "priceModificationAmount": 0,
                            "size": null
                        }
                    ]
                },
                {
                    "id": "0dbfeb52-065b-41c3-86c0-6e61afe2d40c",
                    "name": "группа картошка",
                    "products": [
                        {
                            "code": "00079",
                            "forbiddenModifiersCodes": [],
                            "priceModificationAmount": 0,
                            "size": null
                        }
                    ]
                }
            ],
            "name": "боксмастер с картошкой",
            "priceModification": 120,//Фиксированная цена комбо-блюда
            "priceModificationType": 0,
            "sourceActionId": "ff54f71c-cd36-11e8-80e3-d8d38565926f"//ID источника добавления комбо
        }
```

```json
{
            "categoryId": null,
            "groups": [
                {
                    "id": "060e8d59-2e33-4117-85a9-1823792c6dee",//ID комбо группы
                    "name": "группа боксмастер",
                    "products": [
                        {
                            "code": "00076",
                            "forbiddenModifiersCodes": [],
                            "priceModificationAmount": 0,
                            "size": null
                        }
                    ]
                },
                {
                    "id": "0dbfeb52-065b-41c3-86c0-6e61afe2d40c",
                    "name": "группа картошка",
                    "products": [
                        {
                            "code": "00079",
                            "forbiddenModifiersCodes": [],
                            "priceModificationAmount": 0,
                            "size": null
                        }
                    ]
                }
            ],
            "name": "боксмастер с картошкой",
            "priceModification": 120,//Фиксированная цена комбо-блюда
            "priceModificationType": 0,
            "sourceActionId": "ff54f71c-cd36-11e8-80e3-d8d38565926f"//ID источника добавления комбо
        }
```


* Создадим заказ с таким комбо-блюдом.

POST-запрос:

https://iiko.biz:9900/api/0/orders/add?access\_token=nOt79Q6RqQhL4ZdIGfGQU8v7lw6QK2JMZIhvzaNsqkhQU74SxArgLxZ4yUHs5WS6424X3w-X9qgpA1NlZ8SLgw2&requestTimeout=00%3A02%3A00

с телом запроса в формате application/json:


```json
{
  "organization": "f20594c6-2da7-11e8-80e0-d8d38565926f",
  "customer": {
    "id": "4fc0f065-269e-47fd-bca7-7b4637b4ce97",
    "name": "Петя",
    "phone": "+79998887766"
  },
  "order": {
    "id": "d4cfe602-b391-5eb2-1d89-e54229ba9f97",
    "date": "2019-06-20 14:23:00",
    "phone": "+79998887766",
    "isSelfService": "false",
    "orderCombos": [
        {
            "id": "7C339E2E-30B2-4A9C-83C9-C0B153C4D785",//Генерируемое ID комбо.Каждое новое комбо-блюдо имеет свой уникальный ID
            "name": "боксмастер с картошкой",
            "amount": 1,
            "price": 120,
            "sourceId": "ff54f71c-cd36-11e8-80e3-d8d38565926f"//Источник добавления комбо
        }
        ],
    "items": [
                {
                    "id": "3d148917-5a7b-47d9-8e8d-a22e37efc3ac",
                    "code": "00079",
                    "name": "картошка FREE",
                    "category": null,
                    "amount": 1,
                    "size": null,
                    "modifiers": [],
                    "sum": 55,
                    "comment": null,
                    "guestId": "575ed7e5-6cda-4f76-9a8f-1ca006a2c87b",
                    "comboInformation": {
            "comboId" : "7C339E2E-30B2-4A9C-83C9-C0B153C4D785",//Генерируемое ID комбо,совпадает с тем что и в ordercombos
            "groupId" : "0dbfeb52-065b-41c3-86c0-6e61afe2d40c",//ID группы "группа картошки"
            "comboSourceId" : "ff54f71c-cd36-11e8-80e3-d8d38565926f"//Источник добавления комбо-блюда 
            }
                },
                {
                    "id": "b4070a3b-8e23-481e-a7fd-a2dfc5d175f4",
                    "code": "00076",
                    "name": "Боксмастер",
                    "category": null,
                    "amount": 1,
                    "size": null,                   
                    "sum": 200,
                    "comment": null,
                    "guestId": "575ed7e5-6cda-4f76-9a8f-1ca006a2c87b",
                    "comboInformation": {
            "comboId" : "7C339E2E-30B2-4A9C-83C9-C0B153C4D785",//Генерируемое ID комбо,совпадает с тем что и в ordercombos
            "groupId" : "060e8d59-2e33-4117-85a9-1823792c6dee",//ID группы "группа боксмастер"
            "comboSourceId" : "ff54f71c-cd36-11e8-80e3-d8d38565926f"//Источник добавления комбо-блюда 
            }
                }
            ], 
        "address": {
      "city": "Москва",
      "street": "Смоленский бульвар",
      "home": "1",
      "apartment": "1",
      "comment": "Доставить горячим"
    },
        "paymentItems": [
        {
            "sum": 120,
            "paymentType": {
                "id": "09322f46-578a-d210-add7-eec222a08871",
                "code": "CASH",
                "name": "Наличные",
                "comment": "",
                "combinable": true,
                "externalRevision": 10,
                "applicableMarketingCampaigns": null,
                "deleted": false
            },
            "additionalData": null,
            "isProcessedExternally": false,
            "isPreliminary": false,
            "isExternal": true
        }
        ]
  }
}
```

```json
{
  "organization": "f20594c6-2da7-11e8-80e0-d8d38565926f",
  "customer": {
    "id": "4fc0f065-269e-47fd-bca7-7b4637b4ce97",
    "name": "Петя",
    "phone": "+79998887766"
  },
  "order": {
    "id": "d4cfe602-b391-5eb2-1d89-e54229ba9f97",
    "date": "2019-06-20 14:23:00",
    "phone": "+79998887766",
    "isSelfService": "false",
    "orderCombos": [
        {
            "id": "7C339E2E-30B2-4A9C-83C9-C0B153C4D785",//Генерируемое ID комбо.Каждое новое комбо-блюдо имеет свой уникальный ID
            "name": "боксмастер с картошкой",
            "amount": 1,
            "price": 120,
            "sourceId": "ff54f71c-cd36-11e8-80e3-d8d38565926f"//Источник добавления комбо
        }
        ],
    "items": [
                {
                    "id": "3d148917-5a7b-47d9-8e8d-a22e37efc3ac",
                    "code": "00079",
                    "name": "картошка FREE",
                    "category": null,
                    "amount": 1,
                    "size": null,
                    "modifiers": [],
                    "sum": 55,
                    "comment": null,
                    "guestId": "575ed7e5-6cda-4f76-9a8f-1ca006a2c87b",
                    "comboInformation": {
            "comboId" : "7C339E2E-30B2-4A9C-83C9-C0B153C4D785",//Генерируемое ID комбо,совпадает с тем что и в ordercombos
            "groupId" : "0dbfeb52-065b-41c3-86c0-6e61afe2d40c",//ID группы "группа картошки"
            "comboSourceId" : "ff54f71c-cd36-11e8-80e3-d8d38565926f"//Источник добавления комбо-блюда 
            }
                },
                {
                    "id": "b4070a3b-8e23-481e-a7fd-a2dfc5d175f4",
                    "code": "00076",
                    "name": "Боксмастер",
                    "category": null,
                    "amount": 1,
                    "size": null,                   
                    "sum": 200,
                    "comment": null,
                    "guestId": "575ed7e5-6cda-4f76-9a8f-1ca006a2c87b",
                    "comboInformation": {
            "comboId" : "7C339E2E-30B2-4A9C-83C9-C0B153C4D785",//Генерируемое ID комбо,совпадает с тем что и в ordercombos
            "groupId" : "060e8d59-2e33-4117-85a9-1823792c6dee",//ID группы "группа боксмастер"
            "comboSourceId" : "ff54f71c-cd36-11e8-80e3-d8d38565926f"//Источник добавления комбо-блюда 
            }
                }
            ], 
        "address": {
      "city": "Москва",
      "street": "Смоленский бульвар",
      "home": "1",
      "apartment": "1",
      "comment": "Доставить горячим"
    },
        "paymentItems": [
        {
            "sum": 120,
            "paymentType": {
                "id": "09322f46-578a-d210-add7-eec222a08871",
                "code": "CASH",
                "name": "Наличные",
                "comment": "",
                "combinable": true,
                "externalRevision": 10,
                "applicableMarketingCampaigns": null,
                "deleted": false
            },
            "additionalData": null,
            "isProcessedExternally": false,
            "isPreliminary": false,
            "isExternal": true
        }
        ]
  }
}
```

 * Дополнительной опцией можно рассчитать стоимость комбо-блюда, чтобы точно указать сумму оплат.
 
POST-запрос:

https://iiko.biz:9900/api/0/orders/check\_and\_get\_combo\_price?access\_token=nOt79Q6RqQhL4ZdIGfGQUyNZfCHWLfADVBZQm9koxZDhaV6gVBDS\_fiaYTW-yZd9ISbhFcSPtljeaYMWV8e-dA2&organization=f20594c6-2da7-11e8-80e0-d8d38565926f

с телом запроса в формате application/json:


```json
{
     "items" : [
      {
            "id": "b4070a3b-8e23-481e-a7fd-a2dfc5d175f4",
            "code":"00076",
            "name": "боксмастер",
            "amount": "1",
            "sum" : "100500",
            "comboInformation" : {
            "comboId" : "7c339e2e-30b2-4a9c-83c9-c0b153c4d785",//Генерируемое ID комбо-блюда
            "groupId" : "060e8d59-2e33-4117-85a9-1823792c6dee",
            "comboSourceId" : "ff54f71c-cd36-11e8-80e3-d8d38565926f" 
            }
        },
             {
            "id": "3d148917-5a7b-47d9-8e8d-a22e37efc3ac",
            "code":"00079",
            "name": "картошка",
            "amount": "1",
            "sum" : "100500",//Суммы в этом поле API не берет в расчет
            "comboInformation" : {
            "comboId" : "7c339e2e-30b2-4a9c-83c9-c0b153c4d785",
            "groupId" : "0dbfeb52-065b-41c3-86c0-6e61afe2d40c",
            "comboSourceId" : "ff54f71c-cd36-11e8-80e3-d8d38565926f" 
            }
        }
      ]  
}
```

```json
{
     "items" : [
      {
            "id": "b4070a3b-8e23-481e-a7fd-a2dfc5d175f4",
            "code":"00076",
            "name": "боксмастер",
            "amount": "1",
            "sum" : "100500",
            "comboInformation" : {
            "comboId" : "7c339e2e-30b2-4a9c-83c9-c0b153c4d785",//Генерируемое ID комбо-блюда
            "groupId" : "060e8d59-2e33-4117-85a9-1823792c6dee",
            "comboSourceId" : "ff54f71c-cd36-11e8-80e3-d8d38565926f" 
            }
        },
             {
            "id": "3d148917-5a7b-47d9-8e8d-a22e37efc3ac",
            "code":"00079",
            "name": "картошка",
            "amount": "1",
            "sum" : "100500",//Суммы в этом поле API не берет в расчет
            "comboInformation" : {
            "comboId" : "7c339e2e-30b2-4a9c-83c9-c0b153c4d785",
            "groupId" : "0dbfeb52-065b-41c3-86c0-6e61afe2d40c",
            "comboSourceId" : "ff54f71c-cd36-11e8-80e3-d8d38565926f" 
            }
        }
      ]  
}
```


Результат:


```json
{
    "incorrectlyFilledGroups": [],//Признак того что все комбо-группы заполнены корректно
    "price": 120 //Цена комбо-блюда
}
```

```json
{
    "incorrectlyFilledGroups": [],//Признак того что все комбо-группы заполнены корректно
    "price": 120 //Цена комбо-блюда
}
```


1. Итоговый заказ на iikoFront

![](/resources/Storage/api-documentations/zakaz-s-kombo-blyudami/zakaz-s-kombo-blyudami-2025-01-24.png)
