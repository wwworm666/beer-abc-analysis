Многие настраивают на сайте оплату банковскими картами. Для этого в iiko нужно передавать сумму оплат и факт того, что оплата была проведена во внешней системе.

| ![Warning](/resources/Storage/api-documentations/api-documentations/warning.png) | Отмена доставки в iiko не отменит транзакцию по карте. Возврат денег гостю нужно настраивать на стороне сайта. |
| --- | --- |

Настройка типа оплаты в iiko

![](/resources/Storage/api-documentations/order-wth-prepay-2019-05-16.png)

Если установлена галочка **Устанавливать точную сумму,** то вся сумма заказа будет оплачена этим типом оплаты.

Убедитесь, что API видит этот тип оплаты. Для этого выполните GET-запрос:

https://iiko.biz:9900/api/0/rmsSettings/getPaymentTypes?access\_token=BoMnuxg9A90cujUi-9gY9a8ol11yAapckN86iP3NVUaCG4QeBdmFeNRVXAVOR2n8DO-44DHLf1HY2-0LZ1N3Lg2&organization=f20594c6-2da7-11e8-80e0-d8d38565926f

Результатом будет ответ:


```json
{
            "id": "f6854694-27df-444c-b167-756d8af7defe",
            "code": "15",
            "name": "Оплата доставки банковской картой",
            "comment": "",
            "combinable": true,
            "externalRevision": 259007,
            "applicableMarketingCampaigns": null,
            "deleted": false
        }
```

```json
{
            "id": "f6854694-27df-444c-b167-756d8af7defe",
            "code": "15",
            "name": "Оплата доставки банковской картой",
            "comment": "",
            "combinable": true,
            "externalRevision": 259007,
            "applicableMarketingCampaigns": null,
            "deleted": false
        }
```


Теперь создаем заказ. В нашем примере одна часть заказа оплачена наличными, другая — банковской картой.

POST-запрос:

https://iiko.biz:9900/api/0/orders/add?access\_token=BoMnuxg9A90cujUi-9gY9dvAx3P7ivQ0XjAEFKaxzmjEoASkJeomlNm6raxuDAFQUWIOrDwaTn-KnE18eDlVXg2

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
    "id": "d8195714-b901-5fb2-ed89-e94233ba5497",
    "date": "2019-05-16 13:49:00",
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
            "isProcessedExternally": false, //Всегда FALSE для наличных!Наличные не могут быть оплачены во внешней системе!
            "isPreliminary": false,
            "isExternal": true
        },
        {
            "sum": 44,
            "paymentType": {
                "id": "f6854694-27df-444c-b167-756d8af7defe",
                "code": "15",
                "name": "Оплата доставки банковской картой",
                "comment": "",
                "combinable": true,
                "externalRevision": 20859,
                "applicableMarketingCampaigns": null,
                "deleted": false
            },
            "additionalData": null,
            "isProcessedExternally": true, //Признак ПРОВЕДЕННОГО платежа
            "isPreliminary": false, //Признак предоплаты
            "isExternal": true //Всегда true для оплаты с сайта
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
    "id": "d8195714-b901-5fb2-ed89-e94233ba5497",
    "date": "2019-05-16 13:49:00",
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
            "isProcessedExternally": false, //Всегда FALSE для наличных!Наличные не могут быть оплачены во внешней системе!
            "isPreliminary": false,
            "isExternal": true
        },
        {
            "sum": 44,
            "paymentType": {
                "id": "f6854694-27df-444c-b167-756d8af7defe",
                "code": "15",
                "name": "Оплата доставки банковской картой",
                "comment": "",
                "combinable": true,
                "externalRevision": 20859,
                "applicableMarketingCampaigns": null,
                "deleted": false
            },
            "additionalData": null,
            "isProcessedExternally": true, //Признак ПРОВЕДЕННОГО платежа
            "isPreliminary": false, //Признак предоплаты
            "isExternal": true //Всегда true для оплаты с сайта
        }
    ]
  }
}

```


Заказ, который оплачен на сайте, в iikoOffice будет выглядеть так:
![](/resources/Storage/api-documentations/order-wth-prepay-2019-05-16-1.png)
