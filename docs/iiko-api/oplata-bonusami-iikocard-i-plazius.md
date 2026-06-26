* [Бонусы iikoCard](/articles/api-documentations/oplata-bonusami-iikocard-i-plazius/a/h2__1007938869)
* [Бонусы Plazius](/articles/api-documentations/oplata-bonusami-iikocard-i-plazius/a/h2_1721281859)

##  Бонусы iikoCard 

На первом этапе нужно настроить [бонусную программу в iikoСard](/smart/project-iikocard/bonus-program). В действиях обязательно должно быть действие «Оплата со счета». Иначе бонусами нельзя будет оплатить заказ и для гостя не создастся бонусный счет.

![](/resources/Storage/api-documentations/iiko-card5-plazius-2019-05-23.png)

Создайте в iikoOffice тип оплаты и свяжите его с бонусной программой:

![](/resources/Storage/api-documentations/iiko-card5-plazius-2019-05-23-1.png)

Запрашиваем типы оплаты, доступные по API:

https://iiko.biz:9900/api/0/rmsSettings/getPaymentTypes?access\_token=lHcyuSQXwnXbyOpwoz2pIEDLoKOu660XDqOqe9TJ5L5bkXmZZKPlXB\_51F1C5nw592w9NI\_XX1B0vCJKwHey2g2&organization=f20594c6-2da7-11e8-80e0-d8d38565926f

В ответе будет следующая структура:


```json
{
            "id": "1f725e73-cef2-4512-a945-582a7636a8c8",//Идентификатор типа оплаты
            "code": "BONUS",
            "name": "Оплата бонусами",
            "comment": "",
            "combinable": true,
            "externalRevision": 79196,
            "applicableMarketingCampaigns": [
                "ae45feaa-3725-11e8-80e0-d8d38565926f"//Идентификатор бонусной программы в iiko.biz
            ],
            "deleted": false
        }
```

```json
{
            "id": "1f725e73-cef2-4512-a945-582a7636a8c8",//Идентификатор типа оплаты
            "code": "BONUS",
            "name": "Оплата бонусами",
            "comment": "",
            "combinable": true,
            "externalRevision": 79196,
            "applicableMarketingCampaigns": [
                "ae45feaa-3725-11e8-80e0-d8d38565926f"//Идентификатор бонусной программы в iiko.biz
            ],
            "deleted": false
        }
```


Создаем заказ с добавлением бонусов iikoCard:

**
```json
{
  "organization": "f20594c6-2da7-11e8-80e0-d8d38565926f",
  "customer": {
    "id": "4fc0f065-269e-47fd-bca7-7b4637b4ce97",
    "name": "Петя",
    "phone": "+79998887766"
  },
  "order": {
    "id": "d7148304-b801-5fb7-ed39-e94233ba5497",
    "date": "2019-05-23 18:49:00",
    "phone": "+79998887766",
    "isSelfService": "false",
    "items":[ 
      {
    "id": "8f60e4f6-b309-436d-9b42-12b8d709d84b",
    "name": "4 сыра",
    "amount": 1,
    "code": "31",
    "sum": 200,
    "modifiers": [
      {
        "id": "01ec7323-7659-4531-9502-9a2b129dbfcc",
        "name": "с беконом",
        "amount": 1
      }
      ]
      }
    ],  
        "address": {
      "city": "Москва",
      "street": "Смоленский бульвар",
      "home": "1",
      "apartment": "1",
      "comment": "Доставить горячим побыстрее"
    },
   "paymentItems": [
        {
            "sum": 33,
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
        },
        {
            "sum": 44,
            "paymentType": {
                "id": "1f725e73-cef2-4512-a945-582a7636a8c8",
                "code": "BONUS",
                "name": "Оплата бонусами",
                "comment": "",
                "combinable": true,
                "externalRevision": 20859,
                "applicableMarketingCampaignIds": "null",
                "deleted": false
            },
            "additionalData": "{'searchScope' : 'PHONE',
                'credential': '+79998887766'}",//Авторизация гостя по номеру телефона , у которого спишутся бонусы  
            "isProcessedExternally": false,//Всегда false , бонусы нельзя списать из внешней системы
            "isPreliminary": true,
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
    "id": "d7148304-b801-5fb7-ed39-e94233ba5497",
    "date": "2019-05-23 18:49:00",
    "phone": "+79998887766",
    "isSelfService": "false",
    "items":[ 
      {
    "id": "8f60e4f6-b309-436d-9b42-12b8d709d84b",
    "name": "4 сыра",
    "amount": 1,
    "code": "31",
    "sum": 200,
    "modifiers": [
      {
        "id": "01ec7323-7659-4531-9502-9a2b129dbfcc",
        "name": "с беконом",
        "amount": 1
      }
      ]
      }
    ],  
        "address": {
      "city": "Москва",
      "street": "Смоленский бульвар",
      "home": "1",
      "apartment": "1",
      "comment": "Доставить горячим побыстрее"
    },
   "paymentItems": [
        {
            "sum": 33,
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
        },
        {
            "sum": 44,
            "paymentType": {
                "id": "1f725e73-cef2-4512-a945-582a7636a8c8",
                "code": "BONUS",
                "name": "Оплата бонусами",
                "comment": "",
                "combinable": true,
                "externalRevision": 20859,
                "applicableMarketingCampaignIds": "null",
                "deleted": false
            },
            "additionalData": "{'searchScope' : 'PHONE',
                'credential': '+79998887766'}",//Авторизация гостя по номеру телефона , у которого спишутся бонусы  
            "isProcessedExternally": false,//Всегда false , бонусы нельзя списать из внешней системы
            "isPreliminary": true,
            "isExternal": true
        }
    ]
  }
}

```
**

##  Бонусы Plazius 

Настройка бонусов Plazius как тип оплаты в iikoOffice описана на стр. 8-11 в [руководстве по установке Plazius (pdf)](http://docs-cdn.plazius.ru/iiko_installation_28.03.2019.pdf).


```json
{
  "organization": "944ad991-f0f1-11e8-80e3-d8d38565926f",
  "customer": {
    "name": "Тест",
    "phone": "+79066347936"
  },
  "order": {
    "id": "d7148304-b801-5fb7-ed39-e94233ba5497",
    "date": "2019-05-06 18:49:00",
    "phone": "+79066347936",
    "isSelfService": "false",
    "items":[ 
      {
    "id": "81b99783-19ab-4f46-a329-c6d3448743ee",
    "name": "Сет Стандарт",
    "amount": 1,
    "code": "57762",
    "comment": "ТЕСТ! НЕ ГОТОВИТЬ! ОТМЕНИТЬ!",
    "sum": 640
          }
    ],  
        "address": {
      "city": "Ярославль",
      "street": "Ушинского",
      "home": "38/2",
      "apartment": "1"
    },
   "paymentItems": [
        {
            "sum": 33,
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
        },
        {
            "sum": 1,
            "paymentType": {
                "id": "4f8081dd-1f85-68a5-6a55-8e6e67dc99d0",
                "code": "PLAZI",
                "name": "Бонусы Plazius",
                "comment": "",
                "combinable": true,
                "externalRevision": 20859,
                "applicableMarketingCampaignIds": "null",
                "deleted": false
            },
            "additionalData": "{\"externalIdType\": \"PHONE\", \"externalId\": \"+79066347936\"}",//Для бонусов Plazius формат добавления отличается  
            "isProcessedExternally": false,
            "isPreliminary": true,
            "isExternal": true
        }
    ]
  }
}

```

```json
{
  "organization": "944ad991-f0f1-11e8-80e3-d8d38565926f",
  "customer": {
    "name": "Тест",
    "phone": "+79066347936"
  },
  "order": {
    "id": "d7148304-b801-5fb7-ed39-e94233ba5497",
    "date": "2019-05-06 18:49:00",
    "phone": "+79066347936",
    "isSelfService": "false",
    "items":[ 
      {
    "id": "81b99783-19ab-4f46-a329-c6d3448743ee",
    "name": "Сет Стандарт",
    "amount": 1,
    "code": "57762",
    "comment": "ТЕСТ! НЕ ГОТОВИТЬ! ОТМЕНИТЬ!",
    "sum": 640
          }
    ],  
        "address": {
      "city": "Ярославль",
      "street": "Ушинского",
      "home": "38/2",
      "apartment": "1"
    },
   "paymentItems": [
        {
            "sum": 33,
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
        },
        {
            "sum": 1,
            "paymentType": {
                "id": "4f8081dd-1f85-68a5-6a55-8e6e67dc99d0",
                "code": "PLAZI",
                "name": "Бонусы Plazius",
                "comment": "",
                "combinable": true,
                "externalRevision": 20859,
                "applicableMarketingCampaignIds": "null",
                "deleted": false
            },
            "additionalData": "{\"externalIdType\": \"PHONE\", \"externalId\": \"+79066347936\"}",//Для бонусов Plazius формат добавления отличается  
            "isProcessedExternally": false,
            "isPreliminary": true,
            "isExternal": true
        }
    ]
  }
}

```
