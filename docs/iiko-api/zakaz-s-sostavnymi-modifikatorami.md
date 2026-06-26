В этой статье рассмотрим составные модификаторы.

Блюдо в iikoOffice:
![](/resources/Storage/api-documentations/sostavnye-modifiers-2019-05-15-2.png)

Вот так блюдо отображается в API:


```json
"groupId": null,
"groupModifiers": [
{
"maxAmount": 5,                                                                 //ограничение на максимум для группы.
"minAmount": 2,                                                                  //ограничение на минимум для группы.
"modifierId": "4b35b188-3e56-49cf-9bf9-523d6b542a2b",      //Уникальный идентификатор группы модификаторов "групповые модификаторы"
"required": true,
"childModifiers": [                                                               //Признак того , что модификатор групповой и имеет в своем составе дочерние
{
"maxAmount": 6,
"minAmount": 0,
"modifierId": "00554563-7d3c-4125-be41-3c4757cd8d89",
"required": false,
"defaultAmount": 0,
"hideIfDefaultAmount": false
},
{
"maxAmount": 7,
"minAmount": 0,
"modifierId": "7d0b5411-6115-44a4-8a9f-859ef4c1d53c",
"required": false,
"defaultAmount": 0,
"hideIfDefaultAmount": false
}
],
"childModifiersHaveMinMaxRestrictions": true                                        //Признак того что существуют ограничения не только на группу,но и на число дочерних модификаторов
}
],
"measureUnit": "кг",
"modifiers": [],
"price": 999

}
```

```json
"groupId": null,
"groupModifiers": [
{
"maxAmount": 5,                                                                 //ограничение на максимум для группы.
"minAmount": 2,                                                                  //ограничение на минимум для группы.
"modifierId": "4b35b188-3e56-49cf-9bf9-523d6b542a2b",      //Уникальный идентификатор группы модификаторов "групповые модификаторы"
"required": true,
"childModifiers": [                                                               //Признак того , что модификатор групповой и имеет в своем составе дочерние
{
"maxAmount": 6,
"minAmount": 0,
"modifierId": "00554563-7d3c-4125-be41-3c4757cd8d89",
"required": false,
"defaultAmount": 0,
"hideIfDefaultAmount": false
},
{
"maxAmount": 7,
"minAmount": 0,
"modifierId": "7d0b5411-6115-44a4-8a9f-859ef4c1d53c",
"required": false,
"defaultAmount": 0,
"hideIfDefaultAmount": false
}
],
"childModifiersHaveMinMaxRestrictions": true                                        //Признак того что существуют ограничения не только на группу,но и на число дочерних модификаторов
}
],
"measureUnit": "кг",
"modifiers": [],
"price": 999

}
```


Пример создания заказа с таким блюдом, POST-запрос:

https://iiko.biz:9900/api/0/orders/add?access\_token=Y4ZOYGUI2prLT4DO0rQRw9JWrHTRvrhwz99WTXrdNDZnoprR2VPBfTSq83kK0Lmf2cXs7u1eWBhqtGqP3LXG4A2&requestTimeout=00%3A01%3A00

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
"id": "d7cfe601-b801-5eb7-1d89-e54229ba9f97",
"date": "2019-05-15 16:37:00",
"phone": "+79998887766",
"isSelfService": "false",
"items":[
{
"id": "e8da1358-7664-4f36-b7be-8bbadacbfb4c",
"name": "Товар с групповыми модификаторами",
"amount": 1,
"code": "00080",
"sum": 999,
"modifiers": [
{
"id": "00554563-7d3c-4125-be41-3c4757cd8d89",
"name": "мод из группы1",
"amount": 3,
"groupId": "4b35b188-3e56-49cf-9bf9-523d6b542a2b",
"groupName": "групповые модификаторы"
},
{
"id": "7d0b5411-6115-44a4-8a9f-859ef4c1d53c",
"name": "мод из группы2",
"amount": 1,
"groupId": "4b35b188-3e56-49cf-9bf9-523d6b542a2b",
"groupName": "групповые модификаторы"
}
]
}
],
"address": {
"city": "Москва",
"street": "Смоленский бульвар",
"home": "1",
"apartment": "1",
"comment": "Доставить горячим"
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
"id": "d7cfe601-b801-5eb7-1d89-e54229ba9f97",
"date": "2019-05-15 16:37:00",
"phone": "+79998887766",
"isSelfService": "false",
"items":[
{
"id": "e8da1358-7664-4f36-b7be-8bbadacbfb4c",
"name": "Товар с групповыми модификаторами",
"amount": 1,
"code": "00080",
"sum": 999,
"modifiers": [
{
"id": "00554563-7d3c-4125-be41-3c4757cd8d89",
"name": "мод из группы1",
"amount": 3,
"groupId": "4b35b188-3e56-49cf-9bf9-523d6b542a2b",
"groupName": "групповые модификаторы"
},
{
"id": "7d0b5411-6115-44a4-8a9f-859ef4c1d53c",
"name": "мод из группы2",
"amount": 1,
"groupId": "4b35b188-3e56-49cf-9bf9-523d6b542a2b",
"groupName": "групповые модификаторы"
}
]
}
],
"address": {
"city": "Москва",
"street": "Смоленский бульвар",
"home": "1",
"apartment": "1",
"comment": "Доставить горячим"
}
}
}
```
