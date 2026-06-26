* [Скидка в виде процента или суммы](/articles/api-documentations/zakaz-so-skidkoy-ili-nadbavkoy/a/h2__106064781)
* [Скидка со свободной суммой](/articles/api-documentations/zakaz-so-skidkoy-ili-nadbavkoy/a/h2_1903012167)
* [Надбавки](/articles/api-documentations/zakaz-so-skidkoy-ili-nadbavkoy/a/h2_1008490828)

| ![Warning](/resources/Storage/api-documentations/api-documentations/warning.png) | Применять систему лояльности iikoCard совместно с локальными скидками нельзя! Используйте одно из двух: либо только локальные скидки, либо все скидки настраивайте в iikoCard.<br><br>Локальные скидки с галочкой **Устанавливать автоматически** в API не доступны.<br><br>Скидки из iikoCard не нужно добавлять в API-запросы, они будут применяться автоматически. |
| --- | --- |

В этой статье рассмотрим добавление локальных скидок и надбавок в заказ доставки.

## Скидка в виде процента или суммы

В iikoOffice настроена скидка:
![](/resources/Storage/api-documentations/skidka-nacenka-2019-05-15.png)
Запрашиваем через API список локальных скидок организаци, GET-запрос:


```json
https://iiko.biz:9900/api/0/deliverySettings/deliveryDiscounts?access_token=Y4ZOYGUI2prLT4DO0rQRw1Jt2wd9PVM9A-osRLXs9ioE9-a33oZuL1ke9kuGf1AA0NssvLiCm9HdCT6GtdLD8A2&organization=f20594c6-2da7-11e8-80e0-d8d38565926f
```

```json
https://iiko.biz:9900/api/0/deliverySettings/deliveryDiscounts?access_token=Y4ZOYGUI2prLT4DO0rQRw1Jt2wd9PVM9A-osRLXs9ioE9-a33oZuL1ke9kuGf1AA0NssvLiCm9HdCT6GtdLD8A2&organization=f20594c6-2da7-11e8-80e0-d8d38565926f
```


Получаем структуру скидки:


```json
{
            "departmentCrmIds": [
                "vpasechnikov66"
            ],
            "id": "23cec9e7-d2ea-44b5-9d0d-4b2afedd2919",//Уникальный идентификатор скидки
            "name": "скидка 17%",//Имя скидки
            "percent": 17,//Процент скидки
            "isCategorisedDiscount": false,
            "productCategoryDiscounts": [],
            "comment": "",
            "canBeAppliedSelectively": false,
            "minOrderSum": 100,
            "mode": "PERCENT",//Признак того что скидка процентная
            "sum": 0,
            "isManual": true,
            "isCard": true,
            "canApplyByCardNumber": false,
            "isAutomatic": false
        }
```

```json
{
            "departmentCrmIds": [
                "vpasechnikov66"
            ],
            "id": "23cec9e7-d2ea-44b5-9d0d-4b2afedd2919",//Уникальный идентификатор скидки
            "name": "скидка 17%",//Имя скидки
            "percent": 17,//Процент скидки
            "isCategorisedDiscount": false,
            "productCategoryDiscounts": [],
            "comment": "",
            "canBeAppliedSelectively": false,
            "minOrderSum": 100,
            "mode": "PERCENT",//Признак того что скидка процентная
            "sum": 0,
            "isManual": true,
            "isCard": true,
            "canApplyByCardNumber": false,
            "isAutomatic": false
        }
```


Создаем заказ с указанием id нашей локальной скидки, POST-запрос:

https://iiko.biz:9900/api/0/orders/add?access\_token=Y4ZOYGUI2prLT4DO0rQRw2S0RmIIjtw0wq7pPuhqdKdIi\_xCnsMNOpxJjol2kySGGtRD3uuSO5Xwiofgwi2V9g2&requestTimeout=10000

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
"id": "d8195714-b901-5fb2-ed39-e94233ba5997",
"date": "2019-05-15 17:49:00",
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
"discountCardTypeId": "23cec9e7-d2ea-44b5-9d0d-4b2afedd2919",
"address": {
"city": "Москва",
"street": "Смоленский бульвар",
"home": "1",
"apartment": "1"
}
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
"id": "d8195714-b901-5fb2-ed39-e94233ba5997",
"date": "2019-05-15 17:49:00",
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
"discountCardTypeId": "23cec9e7-d2ea-44b5-9d0d-4b2afedd2919",
"address": {
"city": "Москва",
"street": "Смоленский бульвар",
"home": "1",
"apartment": "1"
}
}
}
```


## Скидка со свободной суммой

Через API такая скидка отображается так:


```json
{
            "departmentCrmIds": [
                "vpasechnikov66"
            ],
            "id": "38fc133c-e836-4fd9-a43a-4b065847c8b2",
            "name": "ИЗМЕНЯЕМАЯ СКИДКА",
            "percent": 1,
            "isCategorisedDiscount": false,
            "productCategoryDiscounts": [],
            "comment": "",
            "canBeAppliedSelectively": false,
            "minOrderSum": null,
            "mode": "FLEXIBLE_SUM", //Признак того что сумму скидки можно вводить произвольную
            "sum": 0,
            "isManual": true,
            "isCard": true,
            "canApplyByCardNumber": false,
            "isAutomatic": false
        }
```

```json
{
            "departmentCrmIds": [
                "vpasechnikov66"
            ],
            "id": "38fc133c-e836-4fd9-a43a-4b065847c8b2",
            "name": "ИЗМЕНЯЕМАЯ СКИДКА",
            "percent": 1,
            "isCategorisedDiscount": false,
            "productCategoryDiscounts": [],
            "comment": "",
            "canBeAppliedSelectively": false,
            "minOrderSum": null,
            "mode": "FLEXIBLE_SUM", //Признак того что сумму скидки можно вводить произвольную
            "sum": 0,
            "isManual": true,
            "isCard": true,
            "canApplyByCardNumber": false,
            "isAutomatic": false
        }
```


Создание заказа с такой скидкой выглядит следующим образом:


```json
{
  "organization": "f20594c6-2da7-11e8-80e0-d8d38565926f",
  "customer": {
    "id": "4fc0f065-269e-47fd-bca7-7b4637b4ce97",
    "name": "Петя",
    "phone": "+79998887766"
  },
  "order": {
    "id": "d8815714-b901-5fb2-ed39-e94233ba5497",
    "date": "2019-05-16 11:49:00",
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
        "discountCardTypeId": "38fc133c-e836-4fd9-a43a-4b065847c8b2", //Идентификатор свободной скидки
        "discountOrIncreaseSum": 57, //Делаем произвольную скидку на 57 рублей
        "address": {
      "city": "Москва",
      "street": "Смоленский бульвар",
      "home": "1",
      "apartment": "1"
    }
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
    "id": "d8815714-b901-5fb2-ed39-e94233ba5497",
    "date": "2019-05-16 11:49:00",
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
        "discountCardTypeId": "38fc133c-e836-4fd9-a43a-4b065847c8b2", //Идентификатор свободной скидки
        "discountOrIncreaseSum": 57, //Делаем произвольную скидку на 57 рублей
        "address": {
      "city": "Москва",
      "street": "Смоленский бульвар",
      "home": "1",
      "apartment": "1"
    }
  }
}

```


## Надбавки
Надбавки применятся точно так же, как и суммовые скидки.

Надбавка через API отображается так:

```json
{
            "departmentCrmIds": null,
            "id": "e46d2e96-6670-4745-bbc7-a13b9a656228",
            "name": "Наценка 2",
            "percent": -4,
            "isCategorisedDiscount": false,
            "productCategoryDiscounts": [],
            "comment": "",
            "canBeAppliedSelectively": false,
            "minOrderSum": null,
            "mode": "FIXED_SUM", //Признак того что наценка/скидка СУММОВАЯ
            "sum": -4, //Отрицательное значение параметра определяет наценку (положительное - скидку)
            "isManual": true,
            "isCard": true,
            "canApplyByCardNumber": false,
            "isAutomatic": false
        }
```

```json
{
            "departmentCrmIds": null,
            "id": "e46d2e96-6670-4745-bbc7-a13b9a656228",
            "name": "Наценка 2",
            "percent": -4,
            "isCategorisedDiscount": false,
            "productCategoryDiscounts": [],
            "comment": "",
            "canBeAppliedSelectively": false,
            "minOrderSum": null,
            "mode": "FIXED_SUM", //Признак того что наценка/скидка СУММОВАЯ
            "sum": -4, //Отрицательное значение параметра определяет наценку (положительное - скидку)
            "isManual": true,
            "isCard": true,
            "canApplyByCardNumber": false,
            "isAutomatic": false
        }
```
