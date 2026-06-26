* [Как выбираются терминалы](/articles/api-documentations/vygruzka-gorodov-i-ulits-kartografiya/a/h2_2095956136)
* [Автоматически](/articles/api-documentations/vygruzka-gorodov-i-ulits-kartografiya/a/h3__1111112835)
* [Принудительное назначение заказа](/articles/api-documentations/vygruzka-gorodov-i-ulits-kartografiya/a/h3_594968552)
* [Выгрузка городов в API](/articles/api-documentations/vygruzka-gorodov-i-ulits-kartografiya/a/h2_890777585)

## Как выбираются терминалы

На сайте можно по-разному выбирать терминалы доставки, куда поступит заказ.

### Автоматически

Можно использовать модуль График работы и картография. Настроить его в iikoOffice и привязать терминалы к зонам доставки.
![](/resources/Storage/api-documentations/cities-and-maps-2019-05-23.png)
В API сначала проверяем заказ перед созданием.

POST-запрос:

https://iiko.biz:9900/api/0/orders/checkCreate?access\_token=lHcyuSQXwnXbyOpwoz2pIKnR270gUHpP-MBxczeW0KmbkfqyhYRzSax\_qjDklnkYwS3uEQLbILKk8SOB01IAFQ2&request\_timeout=00%3A01%3A00

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
    "id": "d8195324-b601-8fb2-ed39-e94233ba5497",
    "date": "2019-05-23 21:49:00",
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
      "street": "Городецкая",
      "home": "3",
      "apartment": "1",
      "comment": "Доставить горячим побыстрее"
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
    "id": "d8195324-b601-8fb2-ed39-e94233ba5497",
    "date": "2019-05-23 21:49:00",
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
      "street": "Городецкая",
      "home": "3",
      "apartment": "1",
      "comment": "Доставить горячим побыстрее"
    }
  }
}

```


Результат:


```json
{
    "deliveryRestriction": {
        "minSum": 0,
        "deliveryTerminalId": "2ee01404-90f4-9186-0162-8c1072ef251e",//Идентификатор терминала доставки
        "organizationId": "f20594c6-2da7-11e8-80e0-d8d38565926f",
        "zone": "ВОСТОК",//Название зоны доставки
        "weekMap": 127,
      "from": 60,//Время работы терминала доставки в минутах. 60 - значит с 01:00
        "to": 1320,//Время работы терминала доставки в минутах. 1320 - значит до 22:00
        "priority": 1,
        "deliveryDurationInMinutes": 60//Продолжительность доставки
    },
    "problem": null,
    "resultState": 0,
    "deliveryServiceProductInfo": {
        "productId": "ad3d9d81-3312-4c5b-846c-a9876ac0edc1",//Будет добавлена дополнительная плата за доставку(блюдо)
        "productSum": 150,
        "productName": "ДОСТАВКА ВОСТОК"
    }
}
```

```json
{
    "deliveryRestriction": {
        "minSum": 0,
        "deliveryTerminalId": "2ee01404-90f4-9186-0162-8c1072ef251e",//Идентификатор терминала доставки
        "organizationId": "f20594c6-2da7-11e8-80e0-d8d38565926f",
        "zone": "ВОСТОК",//Название зоны доставки
        "weekMap": 127,
      "from": 60,//Время работы терминала доставки в минутах. 60 - значит с 01:00
        "to": 1320,//Время работы терминала доставки в минутах. 1320 - значит до 22:00
        "priority": 1,
        "deliveryDurationInMinutes": 60//Продолжительность доставки
    },
    "problem": null,
    "resultState": 0,
    "deliveryServiceProductInfo": {
        "productId": "ad3d9d81-3312-4c5b-846c-a9876ac0edc1",//Будет добавлена дополнительная плата за доставку(блюдо)
        "productSum": 150,
        "productName": "ДОСТАВКА ВОСТОК"
    }
}
```


Если же адрес доставки не входит ни в одну зону, сумма заказа меньше минимальной, неверно выставлены приоритеты терминалов доставки, то получим следующую ошибку:


```json
{
    "deliveryRestriction": null,
    "problem": "Не удалось найти точку доставки с учетом настроенных ограничений.",
    "resultState": 2,
    "deliveryServiceProductInfo": null
}
```

```json
{
    "deliveryRestriction": null,
    "problem": "Не удалось найти точку доставки с учетом настроенных ограничений.",
    "resultState": 2,
    "deliveryServiceProductInfo": null
}
```


### Принудительное назначение заказа

Можно принудительно назначать заказы на терминалы доставки, не используя модуль графика работы и картографии.

Гость на сайте выбирает город для доставки, сайт при этом опрашивает терминалы доставки.

GET-запрос

https://iiko.biz:9900/api/0/deliverySettings/getDeliveryTerminals?access\_token=TxfrBhQPd97f9AlqssWMhosoqwxEeDtP\_m4TqjU9-XfBW9fAtzqpFTlhoHFLjT2Cbka\_zvz38GYHnjuQw4WANA2&organization=f20594c6-2da7-11e8-80e0-d8d38565926f

В этом случае в запрос на создание заказа с доставкой принудительно нужно прописать идентификатор терминала доставки:

"deliveryTerminalId": "2ee01404-90f4-9186-0162-8c1072ef251e"

Связка города и терминала доставки прописана на сайте. При выборе города Х заказ будет всегда назначен на терминал Y.

## Выгрузка городов в API

Необходимо запретить ручной ввод городов и улиц на стороне iiko, чтобы гость на сайте не смог создать доставку на несуществующий адрес. Такие заказы оператор доставки должен обрабатывать вручную.

Как правило список улиц в каждом городе большой. Рекомендуется загружать улицы из КЛАДР: в контекстном меню города выберите пункт Обновить улицы из КЛАДР. Небольшие населенные пункты создаются так же, как и города. Пример:
![](/resources/Storage/api-documentations/cities-and-maps-2019-05-23-1.png)
В запросе на создание заказа в блоке address необходимо прописывать название города точно так же, как оно отображается в КЛАДР:

* "street": "Ленина" — правильно , "street": "ул.Ленина" — неправильно.
* "city": "Ялуторовск" — правильно , "city": "город Ялуторовск" — неправильно.

Получить структуру выгруженных городов и улиц можно следующим GET-запросом:

https://iiko.biz:9900/api/0/cities/cities?access\_token=TxfrBhQPd97f9AlqssWMhpYWpfi31Tybts6SOVvwdz4Q7hto1Ow0Nqag0ltlnF7BM6xTFdc9yd1IfdsXeUlJfA2&organization=f20594c6-2da7-11e8-80e0-d8d38565926f
