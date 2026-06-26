В данной статье описана работа с комбо-блюдами в iikoCloud API.

Для получение комбо нужно использовать [метод](https://api-ru.iiko.services/#tag/Menu/paths/~1api~11~1combo/post), предварительно комбо должны быть заведены в [iikoCard](/articles/iikocard/topic-18). Далее, чтобы отправить заказ с комбо, нужно использовать [метод создания доставочного заказа](https://api-ru.iiko.services/docs#tag/Deliveries:-Create-and-update/paths/~1api~11~1deliveries~1create/post) - если это доставка, или [данный метод](https://api-ru.iiko.services/docs#tag/Orders/paths/~1api~11~1order~1create/post) - если это заказ в стол.

Ниже представлен пример структуры заказа с описанием полей, где присутствует комбо-блюдо:


```json
"items": [
  {
    "type": "Product",
    "amount": 1,
    "productSizeId": null,
    "comment": null,
    "productId": "a5c3103f-64de-f5ca-0180-21fab2a727c6",
    "price": 163,
    "modifiers": [],модификаторы которые относятся к блюду  
    "positionId": "028dc21a-b16c-1c60-451c-2f96457e3a31",
    "comboInformation": {
      "comboId": "844f5017-236f-39dc-eda5-483c9b4e12b3",--- это поле соотвествует полю из Combos  которое там называется "id": "844f5017-236f-39dc-eda5-483c9b4e12b3"
      "comboSourceId": "03650000-6bec-ac1f-4592-08db051c2897",---это поле соотвествует полю из Combos  которое там называется "sourceId": "03650000-6bec-ac1f-4592-08db051c2897"
      "comboGroupId": "8736e817-786d-495a-ab48-0775e6cd7432"--- это поле берем из запроса https://api-ru.iiko.services/api/1/combo/get_combos_info там это поле "id": "8736e817-786d-495a-ab48-0775e6cd7432""groups"
  },
  {
  "type": "Product",
  "amount": 1,
  "productSizeId": null,
  
  "comment": null,
  "productId": "c05dc7a6-4c12-480c-af6d-48c32299d150",- тут id  продукта берем 
  "price": 229,-цена его
  "modifiers": [],модификаторы которые относятся к блюду 

"positionId": "77dea707-724f-d76a-d8df-8c58ffd8463f",
"comboInformation": {
  "comboId": "844f5017-236f-39dc-eda5-483c9b4e12b3",--- это поле соотвествует полю из Combos  которое там называется "id": "844f5017-236f-39dc-eda5-483c9b4e12b3"
  "comboSourceId": "03650000-6bec-ac1f-4592-08db051c2897",---это поле соотвествует полю из Combos  которое там называется "sourceId": "03650000-6bec-ac1f-4592-08db051c2897"
  "comboGroupId": "8736e817-786d-495a-ab48-0775e6cd7432"--- это поле берем из запроса https://api-ru.iiko.services/api/1/combo/get_combos_info там это поле "id": "8736e817-786d-495a-ab48-0775e6cd7432" в "groups"
}
],

"combos": [
  {
    "id": "844f5017-236f-39dc-eda5-483c9b4e12b3",- это поле вы герерируйте сами 
    "name": "Комбо", передаете название 
    "price": 425.0,, цена  комбо , которое  надо передавать 
    "sourceId": "03650000-6bec-ac1f-4592-08db051c2897" его вы берете из запроса https://api-ru.iiko.services/api/1/combo/get_combos_info там это поле "sourceActionId": "03650000-6bec-ac1f-4592-08db051c2897",
     "amount": 1, количество 
  }
]

```

```json
"items": [
  {
    "type": "Product",
    "amount": 1,
    "productSizeId": null,
    "comment": null,
    "productId": "a5c3103f-64de-f5ca-0180-21fab2a727c6",
    "price": 163,
    "modifiers": [],модификаторы которые относятся к блюду  
    "positionId": "028dc21a-b16c-1c60-451c-2f96457e3a31",
    "comboInformation": {
      "comboId": "844f5017-236f-39dc-eda5-483c9b4e12b3",--- это поле соотвествует полю из Combos  которое там называется "id": "844f5017-236f-39dc-eda5-483c9b4e12b3"
      "comboSourceId": "03650000-6bec-ac1f-4592-08db051c2897",---это поле соотвествует полю из Combos  которое там называется "sourceId": "03650000-6bec-ac1f-4592-08db051c2897"
      "comboGroupId": "8736e817-786d-495a-ab48-0775e6cd7432"--- это поле берем из запроса https://api-ru.iiko.services/api/1/combo/get_combos_info там это поле "id": "8736e817-786d-495a-ab48-0775e6cd7432""groups"
  },
  {
  "type": "Product",
  "amount": 1,
  "productSizeId": null,
  
  "comment": null,
  "productId": "c05dc7a6-4c12-480c-af6d-48c32299d150",- тут id  продукта берем 
  "price": 229,-цена его
  "modifiers": [],модификаторы которые относятся к блюду 

"positionId": "77dea707-724f-d76a-d8df-8c58ffd8463f",
"comboInformation": {
  "comboId": "844f5017-236f-39dc-eda5-483c9b4e12b3",--- это поле соотвествует полю из Combos  которое там называется "id": "844f5017-236f-39dc-eda5-483c9b4e12b3"
  "comboSourceId": "03650000-6bec-ac1f-4592-08db051c2897",---это поле соотвествует полю из Combos  которое там называется "sourceId": "03650000-6bec-ac1f-4592-08db051c2897"
  "comboGroupId": "8736e817-786d-495a-ab48-0775e6cd7432"--- это поле берем из запроса https://api-ru.iiko.services/api/1/combo/get_combos_info там это поле "id": "8736e817-786d-495a-ab48-0775e6cd7432" в "groups"
}
],

"combos": [
  {
    "id": "844f5017-236f-39dc-eda5-483c9b4e12b3",- это поле вы герерируйте сами 
    "name": "Комбо", передаете название 
    "price": 425.0,, цена  комбо , которое  надо передавать 
    "sourceId": "03650000-6bec-ac1f-4592-08db051c2897" его вы берете из запроса https://api-ru.iiko.services/api/1/combo/get_combos_info там это поле "sourceActionId": "03650000-6bec-ac1f-4592-08db051c2897",
     "amount": 1, количество 
  }
]

```

###
