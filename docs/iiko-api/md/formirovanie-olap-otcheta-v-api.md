# Formirovanie Olap Otcheta V Api

*Generated from PDF: formirovanie-olap-otcheta-v-api.pdf*

*Total pages: 32*

---


## Page 1

API Documentation Page1 of 32
1. Формирование OLAP отчета
в API
Получитьданные вAPI припомощиOLAP отчета можноследующимипутями:
- получение данных по преднастроенному отчету в iikoOffice: в классическом приложении
iikoOffice выбрать в навигационном меню раздела «Розничные продажи» - "OLAP Отчет
по продажам", добавить в него поля и период для получения данных, сохранить данный
вариант. Далее выгрузить список преднастроенных отчетов и получить информацию по
полям ифильтрам припомощиметода «Получение отчета посохраненнойконфигурации».
- самостоятельное формирование отчета OLAP,руководствуясьдокументацией.
ВобоихслучаяхрекомендуетсяиспользоватьOLAP v2.
Тот же механизм доступен для работы с "OLAP Отчет по проводкам" в разделе
"Финансы".
Описание примеровOLAP-отчетоввiikoOffice можнонайтивздесь.
Описание примеров OLAP-отчетоввAPI можнонайтиздесь.
Подробное описание полейможнопрочитатьв статье пополям OLAP-отчета по
продажам ивстатье пополям OLAP-отчета попроводкам.
Процесс формирования отчета в iikoOffice
В классическом приложении iikoOffice выберите "OLAP Отчет по продажам" в
навигационном менюраздела «Розничные продажи»:
Allrightsreserved © CompanyInc., 2023

---


## Page 2

API Documentation Page2 of 32
После запуска «OLAP Отчет попродажам»укажите периодсбора данных,добавьте поля
длясбора данных.
Allrightsreserved © CompanyInc., 2023

---


## Page 3

API Documentation Page3 of 32
Далее сохраните сформированныйотчет,дайте емуназвание.
Готово.Отчет сохранениготовк выгрузке через API.
Дополнительно: при нажатии на комбинацию клавиш «CTRL + SHIFT + F3» выведется
окно с параметрами OLAP-отчета, на которые можно ориентироваться при построение
отчета вAPI.
Allrightsreserved © CompanyInc., 2023

---


## Page 4

API Documentation Page4 of 32
Работа с API iikoServer
Статьяпоавторизациидляработыс методамиAPI iikoServer.
Методдляполучениясписка преднастроенныхотчетовOLAP.
Ответ метода длярассматриваемогопримера:
CopyCode
JSON
....
{
"id": "e45124ec-6455-4a1f-ba59-9aa3efe05f30",
"name": "Отчет по проданным блюдам в смену",
"buildSummary": null,
"reportType": "SALES",
"groupByRowFields": [
"OpenDate.Typed",
"SessionNum",
"OpenTime",
"CloseTime",
"DishName",
"OrderType",
"Delivery.CustomerName",
"Delivery.CustomerPhone",
Allrightsreserved © CompanyInc., 2023


### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | .... |  |

|  | { |  |

|  | "id": "e45124ec-6455-4a1f-ba59-9aa3efe05f30", |  |

|  | "name": "Отчет по проданным блюдам в смену", |  |

|  | "buildSummary": null, |  |

|  | "reportType": "SALES", |  |

|  | "groupByRowFields": [ |  |

|  | "OpenDate.Typed", |  |

|  | "SessionNum", |  |

|  | "OpenTime", |  |

|  | "CloseTime", |  |

|  | "DishName", |  |

|  | "OrderType", |  |

|  | "Delivery.CustomerName", |  |

|  | "Delivery.CustomerPhone", |  |


---


## Page 5

API Documentation Page5 of 32
"PayTypes"
],
"groupByColFields": [],
"aggregateFields": [
"DishSumInt"
],
"filters": {
"DeletedWithWriteoff": {
"filterType": "IncludeValues",
"values": [
"NOT_DELETED"
]
},
"OrderDeleted": {
"filterType": "IncludeValues",
"values": [
"NOT_DELETED"
]
}
}
}
...
Методдляполучениятела отчета посохраненнойконфигурации(id)
[+] Ответ длярассматриваемогопримера
[-] Ответ длярассматриваемогопримера
Copy Code
JSON
{
"data": [
{
"CloseTime": "2025-03-18T12:05:24.618",
"Delivery.CustomerName": "Пупкин Василий",
"Delivery.CustomerPhone": "+79785160513",
"DishName": "Лимонад",
"DishSumInt": 176,
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T11:36:48",
"OrderType": null,
"PayTypes": "Наличные",
"SessionNum": 17
},
{
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "PayTypes" |

|  | ], |

|  | "groupByColFields": [], |

|  | "aggregateFields": [ |

|  | "DishSumInt" |

|  | ], |

|  | "filters": { |

|  | "DeletedWithWriteoff": { |

|  | "filterType": "IncludeValues", |

|  | "values": [ |

|  | "NOT_DELETED" |

|  | ] |

|  | }, |

|  | "OrderDeleted": { |

|  | "filterType": "IncludeValues", |

|  | "values": [ |

|  | "NOT_DELETED" |

|  | ] |

|  | } |

|  | } |

|  | } |

|  | ... |

|  |  |



### Table:

| Copy Code |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | { |  |

|  | "data": [ |  |

|  | { |  |

|  | "CloseTime": "2025-03-18T12:05:24.618", |  |

|  | "Delivery.CustomerName": "Пупкин Василий", |  |

|  | "Delivery.CustomerPhone": "+79785160513", |  |

|  | "DishName": "Лимонад", |  |

|  | "DishSumInt": 176, |  |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |  |

|  | "OpenTime": "2025-03-18T11:36:48", |  |

|  | "OrderType": null, |  |

|  | "PayTypes": "Наличные", |  |

|  | "SessionNum": 17 |  |

|  | }, |  |

|  | { |  |


---


## Page 6

API Documentation Page6 of 32
"CloseTime": "2025-03-18T15:34:01.955",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Шоколадный батончик",
"DishSumInt": 50,
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T15:33:41",
"OrderType": null,
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T19:11:06.321",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:10:47",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T19:14:02.906",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:13:20",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T19:19:12.99",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:18:35",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T19:21:43.061",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"DishSumInt": 240,
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "CloseTime": "2025-03-18T15:34:01.955", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Шоколадный батончик", |

|  | "DishSumInt": 50, |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T15:33:41", |

|  | "OrderType": null, |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-18T19:11:06.321", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:10:47", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-18T19:14:02.906", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:13:20", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-18T19:19:12.99", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:18:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-18T19:21:43.061", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |


---


## Page 7

API Documentation Page7 of 32
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:21:25",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T23:14:50.343",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:07:22",
"OrderType": "Доставка самовывоз",
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T23:15:22.35",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:13:45",
"OrderType": "Доставка самовывоз",
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"CloseTime": "2025-03-19T12:58:35.344",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-19T12:56:35",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"CloseTime": "2025-03-24T10:26:53.437",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Шоколадный батончик MARS",
"DishSumInt": 50,
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-24T10:23:59",
"OrderType": null,
"PayTypes": "Наличные",
"SessionNum": 17
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:21:25", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-18T23:14:50.343", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:07:22", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-18T23:15:22.35", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:13:45", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-19T12:58:35.344", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-19T12:56:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-24T10:26:53.437", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Шоколадный батончик MARS", |

|  | "DishSumInt": 50, |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-24T10:23:59", |

|  | "OrderType": null, |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |


---


## Page 8

API Documentation Page8 of 32
},
{
"CloseTime": "2025-03-25T12:44:08.425",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-24T00:00:00",
"OpenTime": "2025-03-24T13:21:53",
"OrderType": "Доставка самовывоз",
"PayTypes": "Наличные",
"SessionNum": 18
}
],
//массив summary выведется с подсуммировкой, если в параметрах запроса
указано summary = true
"summary": [
[
{},
{
"DishSumInt": 2196
}
],
[
{
"CloseTime": "2025-03-18T19:21:43.061",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:21:25",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:21:43.061",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:21:25",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T15:34:01.955",
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-25T12:44:08.425", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-24T00:00:00", |

|  | "OpenTime": "2025-03-24T13:21:53", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 18 |

|  | } |

|  | ], |

|  | //массив summary выведется с подсуммировкой, если в параметрах запроса |

|  | указано summary = true |

|  | "summary": [ |

|  | [ |

|  | {}, |

|  | { |

|  | "DishSumInt": 2196 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:21:43.061", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:21:25", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:21:43.061", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:21:25", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T15:34:01.955", |


---


## Page 9

API Documentation Page9 of 32
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Шоколадный батончик",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T15:33:41",
"OrderType": null,
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-19T12:56:35",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:14:02.906",
"Delivery.CustomerName": "Ермолаев Евгений",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:13:20",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-19T12:58:35.344",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-19T12:56:35",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:21:43.061",
"Delivery.CustomerName": null,
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Шоколадный батончик", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T15:33:41", |

|  | "OrderType": null, |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-19T12:56:35", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:14:02.906", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:13:20", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-19T12:58:35.344", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-19T12:56:35", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:21:43.061", |

|  | "Delivery.CustomerName": null, |


---


## Page 10

API Documentation Page10 of 32
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:21:25",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:11:06.321",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:10:47",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:13:45",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:18:35",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"OpenDate.Typed": "2025-03-24T00:00:00"
},
{
"DishSumInt": 240
}
],
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:21:25", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:11:06.321", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:10:47", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:13:45", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:18:35", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-24T00:00:00" |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |


---


## Page 11

API Documentation Page11 of 32
[
{
"CloseTime": "2025-03-18T15:34:01.955",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T15:33:41",
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"CloseTime": "2025-03-18T12:05:24.618",
"Delivery.CustomerName": "Пупкин Василий",
"Delivery.CustomerPhone": "+79785160513",
"DishName": "Лимонад",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T11:36:48",
"OrderType": null,
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"DishSumInt": 176
}
],
[
{
"CloseTime": "2025-03-18T23:15:22.35",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:13:45",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:14:02.906",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:13:20",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T15:34:01.955", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T15:33:41", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T12:05:24.618", |

|  | "Delivery.CustomerName": "Пупкин Василий", |

|  | "Delivery.CustomerPhone": "+79785160513", |

|  | "DishName": "Лимонад", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T11:36:48", |

|  | "OrderType": null, |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 176 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:15:22.35", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:13:45", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:14:02.906", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:13:20", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |


---


## Page 12

API Documentation Page12 of 32
[
{
"CloseTime": "2025-03-18T19:14:02.906",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:13:20",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:14:02.906",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:13:20",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-25T12:44:08.425",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-24T00:00:00",
"OpenTime": "2025-03-24T13:21:53",
"OrderType": "Доставка самовывоз",
"SessionNum": 18
},
{
"DishSumInt": 240
}
],
[
{
"OpenDate.Typed": "2025-03-24T00:00:00",
"OpenTime": "2025-03-24T13:21:53",
"SessionNum": 18
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-19T12:58:35.344",
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:14:02.906", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:13:20", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:14:02.906", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:13:20", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-25T12:44:08.425", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-24T00:00:00", |

|  | "OpenTime": "2025-03-24T13:21:53", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 18 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-24T00:00:00", |

|  | "OpenTime": "2025-03-24T13:21:53", |

|  | "SessionNum": 18 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-19T12:58:35.344", |


---


## Page 13

API Documentation Page13 of 32
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-19T12:56:35",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T23:14:50.343",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:07:22",
"OrderType": "Доставка самовывоз",
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-24T10:26:53.437",
"Delivery.CustomerName": null,
"DishName": "Шоколадный батончик MARS",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-24T10:23:59",
"OrderType": null,
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"CloseTime": "2025-03-18T15:34:01.955",
"DishName": "Шоколадный батончик",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T15:33:41",
"OrderType": null,
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-19T12:56:35", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:14:50.343", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:07:22", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-24T10:26:53.437", |

|  | "Delivery.CustomerName": null, |

|  | "DishName": "Шоколадный батончик MARS", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-24T10:23:59", |

|  | "OrderType": null, |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T15:34:01.955", |

|  | "DishName": "Шоколадный батончик", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T15:33:41", |

|  | "OrderType": null, |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |


---


## Page 14

API Documentation Page14 of 32
"CloseTime": "2025-03-18T19:19:12.99",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:18:35",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:21:43.061",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:21:25",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-19T12:58:35.344",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-19T12:56:35",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-19T12:58:35.344",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-19T12:56:35",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "CloseTime": "2025-03-18T19:19:12.99", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:18:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:21:43.061", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:21:25", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-19T12:58:35.344", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-19T12:56:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-19T12:58:35.344", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-19T12:56:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |


---


## Page 15

API Documentation Page15 of 32
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-24T10:23:59",
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"CloseTime": "2025-03-18T19:14:02.906",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:13:20",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:13:20",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"OpenDate.Typed": "2025-03-18T00:00:00",
"SessionNum": 17
},
{
"DishSumInt": 1956
}
],
[
{
"CloseTime": "2025-03-18T19:11:06.321",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:10:47",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"DishSumInt": 240
}
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-24T10:23:59", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:14:02.906", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:13:20", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:13:20", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 1956 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:11:06.321", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:10:47", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |


---


## Page 16

API Documentation Page16 of 32
],
[
{
"CloseTime": "2025-03-18T19:19:12.99",
"Delivery.CustomerName": "Ермолаев Евгений",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:18:35",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"OpenDate.Typed": "2025-03-18T00:00:00"
},
{
"DishSumInt": 1956
}
],
[
{
"CloseTime": "2025-03-18T23:14:50.343",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:07:22",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T12:05:24.618",
"DishName": "Лимонад",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T11:36:48",
"SessionNum": 17
},
{
"DishSumInt": 176
}
],
[
{
"CloseTime": "2025-03-18T19:14:02.906",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:19:12.99", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:18:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-18T00:00:00" |

|  | }, |

|  | { |

|  | "DishSumInt": 1956 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:14:50.343", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:07:22", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T12:05:24.618", |

|  | "DishName": "Лимонад", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T11:36:48", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 176 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:14:02.906", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |


---


## Page 17

API Documentation Page17 of 32
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:13:20",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:11:06.321",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:10:47",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:21:43.061",
"Delivery.CustomerName": null,
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:21:25",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:21:25",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-25T12:44:08.425",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-24T00:00:00",
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:13:20", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:11:06.321", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:10:47", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:21:43.061", |

|  | "Delivery.CustomerName": null, |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:21:25", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:21:25", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-25T12:44:08.425", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-24T00:00:00", |


---


## Page 18

API Documentation Page18 of 32
"OpenTime": "2025-03-24T13:21:53",
"OrderType": "Доставка самовывоз",
"PayTypes": "Наличные",
"SessionNum": 18
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:11:06.321",
"Delivery.CustomerName": null,
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:10:47",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:11:06.321",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:10:47",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-24T10:26:53.437",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-24T10:23:59",
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"CloseTime": "2025-03-18T23:14:50.343",
"DishName": "Пицца ",
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "OpenTime": "2025-03-24T13:21:53", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 18 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:11:06.321", |

|  | "Delivery.CustomerName": null, |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:10:47", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:11:06.321", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:10:47", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-24T10:26:53.437", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-24T10:23:59", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:14:50.343", |

|  | "DishName": "Пицца ", |


---


## Page 19

API Documentation Page19 of 32
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:07:22",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T23:15:22.35",
"Delivery.CustomerName": "Ермолаев Евгений",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:13:45",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T23:15:22.35",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:13:45",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T12:05:24.618",
"DishName": "Лимонад",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T11:36:48",
"OrderType": null,
"SessionNum": 17
},
{
"DishSumInt": 176
}
],
[
{
"CloseTime": "2025-03-24T10:26:53.437",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:07:22", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:15:22.35", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:13:45", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:15:22.35", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:13:45", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T12:05:24.618", |

|  | "DishName": "Лимонад", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T11:36:48", |

|  | "OrderType": null, |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 176 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-24T10:26:53.437", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |


---


## Page 20

API Documentation Page20 of 32
"DishName": "Шоколадный батончик MARS",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-24T10:23:59",
"OrderType": null,
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"OpenDate.Typed": "2025-03-24T00:00:00",
"SessionNum": 18
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T12:05:24.618",
"Delivery.CustomerName": "Пупкин Василий",
"DishName": "Лимонад",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T11:36:48",
"OrderType": null,
"SessionNum": 17
},
{
"DishSumInt": 176
}
],
[
{
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T11:36:48",
"SessionNum": 17
},
{
"DishSumInt": 176
}
],
[
{
"CloseTime": "2025-03-18T23:14:50.343",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:07:22",
"SessionNum": 17
},
{
"DishSumInt": 240
}
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "DishName": "Шоколадный батончик MARS", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-24T10:23:59", |

|  | "OrderType": null, |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-24T00:00:00", |

|  | "SessionNum": 18 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T12:05:24.618", |

|  | "Delivery.CustomerName": "Пупкин Василий", |

|  | "DishName": "Лимонад", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T11:36:48", |

|  | "OrderType": null, |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 176 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T11:36:48", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 176 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:14:50.343", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:07:22", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |


---


## Page 21

API Documentation Page21 of 32
],
[
{
"CloseTime": "2025-03-18T19:19:12.99",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:18:35",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-24T10:26:53.437",
"DishName": "Шоколадный батончик MARS",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-24T10:23:59",
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"CloseTime": "2025-03-18T15:34:01.955",
"DishName": "Шоколадный батончик",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T15:33:41",
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"CloseTime": "2025-03-24T10:26:53.437",
"DishName": "Шоколадный батончик MARS",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-24T10:23:59",
"OrderType": null,
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"CloseTime": "2025-03-25T12:44:08.425",
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:19:12.99", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:18:35", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-24T10:26:53.437", |

|  | "DishName": "Шоколадный батончик MARS", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-24T10:23:59", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T15:34:01.955", |

|  | "DishName": "Шоколадный батончик", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T15:33:41", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-24T10:26:53.437", |

|  | "DishName": "Шоколадный батончик MARS", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-24T10:23:59", |

|  | "OrderType": null, |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-25T12:44:08.425", |


---


## Page 22

API Documentation Page22 of 32
"Delivery.CustomerName": null,
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-24T00:00:00",
"OpenTime": "2025-03-24T13:21:53",
"OrderType": "Доставка самовывоз",
"SessionNum": 18
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-25T12:44:08.425",
"OpenDate.Typed": "2025-03-24T00:00:00",
"OpenTime": "2025-03-24T13:21:53",
"SessionNum": 18
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T15:34:01.955",
"Delivery.CustomerName": "Ермолаев Евгений",
"DishName": "Шоколадный батончик",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T15:33:41",
"OrderType": null,
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"CloseTime": "2025-03-18T23:15:22.35",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:13:45",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T23:15:22.35",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "Delivery.CustomerName": null, |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-24T00:00:00", |

|  | "OpenTime": "2025-03-24T13:21:53", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 18 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-25T12:44:08.425", |

|  | "OpenDate.Typed": "2025-03-24T00:00:00", |

|  | "OpenTime": "2025-03-24T13:21:53", |

|  | "SessionNum": 18 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T15:34:01.955", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "DishName": "Шоколадный батончик", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T15:33:41", |

|  | "OrderType": null, |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:15:22.35", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:13:45", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:15:22.35", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |


---


## Page 23

API Documentation Page23 of 32
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:13:45",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T23:14:50.343",
"Delivery.CustomerName": "Ермолаев Евгений",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:07:22",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T12:05:24.618",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T11:36:48",
"SessionNum": 17
},
{
"DishSumInt": 176
}
],
[
{
"CloseTime": "2025-03-18T15:34:01.955",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Шоколадный батончик",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T15:33:41",
"OrderType": null,
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"CloseTime": "2025-03-18T19:19:12.99",
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:13:45", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:14:50.343", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:07:22", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T12:05:24.618", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T11:36:48", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 176 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T15:34:01.955", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Шоколадный батончик", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T15:33:41", |

|  | "OrderType": null, |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:19:12.99", |


---


## Page 24

API Documentation Page24 of 32
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:18:35",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:19:12.99",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:18:35",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T19:11:06.321",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:10:47",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-19T12:58:35.344",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-19T12:56:35",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:18:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:19:12.99", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:18:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:11:06.321", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:10:47", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-19T12:58:35.344", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-19T12:56:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |


---


## Page 25

API Documentation Page25 of 32
}
],
[
{
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T15:33:41",
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"CloseTime": "2025-03-18T19:21:43.061",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:21:25",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-24T10:26:53.437",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Шоколадный батончик MARS",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-24T10:23:59",
"OrderType": null,
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"DishSumInt": 50
}
],
[
{
"CloseTime": "2025-03-25T12:44:08.425",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-24T00:00:00",
"OpenTime": "2025-03-24T13:21:53",
"SessionNum": 18
},
{
"DishSumInt": 240
}
],
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T15:33:41", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:21:43.061", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:21:25", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-24T10:26:53.437", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Шоколадный батончик MARS", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-24T10:23:59", |

|  | "OrderType": null, |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 50 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-25T12:44:08.425", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-24T00:00:00", |

|  | "OpenTime": "2025-03-24T13:21:53", |

|  | "SessionNum": 18 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |


---


## Page 26

API Documentation Page26 of 32
[
{
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:10:47",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-19T12:58:35.344",
"Delivery.CustomerName": "Ермолаев Евгений",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-19T12:56:35",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T12:05:24.618",
"Delivery.CustomerName": "Пупкин Василий",
"Delivery.CustomerPhone": "+79785160513",
"DishName": "Лимонад",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T11:36:48",
"OrderType": null,
"SessionNum": 17
},
{
"DishSumInt": 176
}
],
[
{
"CloseTime": "2025-03-18T19:19:12.99",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T19:18:35",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T23:15:22.35",
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:10:47", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-19T12:58:35.344", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-19T12:56:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T12:05:24.618", |

|  | "Delivery.CustomerName": "Пупкин Василий", |

|  | "Delivery.CustomerPhone": "+79785160513", |

|  | "DishName": "Лимонад", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T11:36:48", |

|  | "OrderType": null, |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 176 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T19:19:12.99", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T19:18:35", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:15:22.35", |


---


## Page 27

API Documentation Page27 of 32
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:13:45",
"OrderType": "Доставка самовывоз",
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-18T23:14:50.343",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:07:22",
"OrderType": "Доставка самовывоз",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"OpenDate.Typed": "2025-03-18T00:00:00",
"OpenTime": "2025-03-18T20:07:22",
"SessionNum": 17
},
{
"DishSumInt": 240
}
],
[
{
"CloseTime": "2025-03-25T12:44:08.425",
"DishName": "Пицца ",
"OpenDate.Typed": "2025-03-24T00:00:00",
"OpenTime": "2025-03-24T13:21:53",
"OrderType": "Доставка самовывоз",
"SessionNum": 18
},
{
"DishSumInt": 240
}
]
]
}
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:13:45", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-18T23:14:50.343", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:07:22", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "OpenDate.Typed": "2025-03-18T00:00:00", |

|  | "OpenTime": "2025-03-18T20:07:22", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ], |

|  | [ |

|  | { |

|  | "CloseTime": "2025-03-25T12:44:08.425", |

|  | "DishName": "Пицца ", |

|  | "OpenDate.Typed": "2025-03-24T00:00:00", |

|  | "OpenTime": "2025-03-24T13:21:53", |

|  | "OrderType": "Доставка самовывоз", |

|  | "SessionNum": 18 |

|  | }, |

|  | { |

|  | "DishSumInt": 240 |

|  | } |

|  | ] |

|  | ] |

|  | } |

|  |  |


---


## Page 28

API Documentation Page28 of 32
МетоддляполученияполейOLAP отчета v2(еслинеобходимостьуточнитьполя).
Метод для формирования OLAP отчета в API (с возможностью
конфигурации тела запроса)
https://host:port.iiko.it/resto/api/v2/reports/olap?key=[token]
Параметрызапроса
Параметр Описание
key Строка-токен,получаемыйприавторизации
Телозапроса
CopyCode
Код
{
"reportType": "SALES",
"groupByRowFields": [
"OpenDate.Typed",
"SessionNum",
"OpenTime",
"CloseTime",
"DishName",
"OrderType",
"Delivery.CustomerName",
"Delivery.CustomerPhone",
"PayTypes"
],
"groupByColFields": [],
"aggregateFields": [
"DishSumInt"
],
"filters": {
"OpenDate.Typed": {
"filterType": "DateRange",
"periodType": "CUSTOM",
"from": "2025-03-01T00:00:00.000",
"to": "2025-03-31T00:00:00.000"
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |

|---|---|---|---|---|---|

|  | Параметр |  |  | Описание |  |

|  |  |  |  |  |  |

| key |  |  | Строка-токен,получаемыйприавторизации |  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | Код |  |

|  |  |  |

|  |  |  |

| {
"reportType": "SALES",
"groupByRowFields": [
"OpenDate.Typed",
"SessionNum",
"OpenTime",
"CloseTime",
"DishName",
"OrderType",
"Delivery.CustomerName",
"Delivery.CustomerPhone",
"PayTypes"
],
"groupByColFields": [],
"aggregateFields": [
"DishSumInt"
],
"filters": {
"OpenDate.Typed": {
"filterType": "DateRange",
"periodType": "CUSTOM",
"from": "2025-03-01T00:00:00.000",
"to": "2025-03-31T00:00:00.000" |  |  |



### Table:

| { |

|---|

| "reportType": "SALES", |

| "groupByRowFields": [ |

| "OpenDate.Typed", |

| "SessionNum", |

| "OpenTime", |

| "CloseTime", |

| "DishName", |

| "OrderType", |

| "Delivery.CustomerName", |

| "Delivery.CustomerPhone", |

| "PayTypes" |

| ], |

| "groupByColFields": [], |

| "aggregateFields": [ |

| "DishSumInt" |

| ], |

| "filters": { |

| "OpenDate.Typed": { |

| "filterType": "DateRange", |

| "periodType": "CUSTOM", |

| "from": "2025-03-01T00:00:00.000", |

| "to": "2025-03-31T00:00:00.000" |


---


## Page 29

API Documentation Page29 of 32
},
"DeletedWithWriteoff": {
"filterType": "IncludeValues",
"values": [
"NOT_DELETED"
]
},
"OrderDeleted": {
"filterType": "IncludeValues",
"values": [
"NOT_DELETED"
]
}
}
}
Что в ответе
CopyCode
JSON
{
"data": [
{
"CloseTime": "2025-03-18T12:05:24.618",
"Delivery.CustomerName": "Пупкин Василий",
"Delivery.CustomerPhone": "+79785160513",
"DishName": "Лимонад",
"DishSumInt": 176,
"OpenDate.Typed": "2025-03-18",
"OpenTime": "2025-03-18T11:36:48",
"OrderType": null,
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T15:34:01.955",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Шоколадный батончик",
"DishSumInt": 50,
"OpenDate.Typed": "2025-03-18",
"OpenTime": "2025-03-18T15:33:41",
"OrderType": null,
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T19:11:06.321",
"Delivery.CustomerName": null,
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | }, |

|  | "DeletedWithWriteoff": { |

|  | "filterType": "IncludeValues", |

|  | "values": [ |

|  | "NOT_DELETED" |

|  | ] |

|  | }, |

|  | "OrderDeleted": { |

|  | "filterType": "IncludeValues", |

|  | "values": [ |

|  | "NOT_DELETED" |

|  | ] |

|  | } |

|  | } |

|  | } |

|  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | { |  |

|  | "data": [ |  |

|  | { |  |

|  | "CloseTime": "2025-03-18T12:05:24.618", |  |

|  | "Delivery.CustomerName": "Пупкин Василий", |  |

|  | "Delivery.CustomerPhone": "+79785160513", |  |

|  | "DishName": "Лимонад", |  |

|  | "DishSumInt": 176, |  |

|  | "OpenDate.Typed": "2025-03-18", |  |

|  | "OpenTime": "2025-03-18T11:36:48", |  |

|  | "OrderType": null, |  |

|  | "PayTypes": "Наличные", |  |

|  | "SessionNum": 17 |  |

|  | }, |  |

|  | { |  |

|  | "CloseTime": "2025-03-18T15:34:01.955", |  |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |  |

|  | "Delivery.CustomerPhone": "+79196129578", |  |

|  | "DishName": "Шоколадный батончик", |  |

|  | "DishSumInt": 50, |  |

|  | "OpenDate.Typed": "2025-03-18", |  |

|  | "OpenTime": "2025-03-18T15:33:41", |  |

|  | "OrderType": null, |  |

|  | "PayTypes": "Наличные", |  |

|  | "SessionNum": 17 |  |

|  | }, |  |

|  | { |  |

|  | "CloseTime": "2025-03-18T19:11:06.321", |  |

|  | "Delivery.CustomerName": null, |  |


---


## Page 30

API Documentation Page30 of 32
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18",
"OpenTime": "2025-03-18T19:10:47",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T19:14:02.906",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18",
"OpenTime": "2025-03-18T19:13:20",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T19:19:12.99",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18",
"OpenTime": "2025-03-18T19:18:35",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T19:21:43.061",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18",
"OpenTime": "2025-03-18T19:21:25",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T23:14:50.343",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18",
"OpenTime": "2025-03-18T20:07:22",
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18", |

|  | "OpenTime": "2025-03-18T19:10:47", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-18T19:14:02.906", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18", |

|  | "OpenTime": "2025-03-18T19:13:20", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-18T19:19:12.99", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18", |

|  | "OpenTime": "2025-03-18T19:18:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-18T19:21:43.061", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18", |

|  | "OpenTime": "2025-03-18T19:21:25", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-18T23:14:50.343", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18", |

|  | "OpenTime": "2025-03-18T20:07:22", |


---


## Page 31

API Documentation Page31 of 32
"OrderType": "Доставка самовывоз",
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"CloseTime": "2025-03-18T23:15:22.35",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18",
"OpenTime": "2025-03-18T20:13:45",
"OrderType": "Доставка самовывоз",
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"CloseTime": "2025-03-19T12:58:35.344",
"Delivery.CustomerName": "Ермолаев Евгений",
"Delivery.CustomerPhone": "+79196129578",
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-18",
"OpenTime": "2025-03-19T12:56:35",
"OrderType": "Доставка самовывоз",
"PayTypes": "Банковские карты",
"SessionNum": 17
},
{
"CloseTime": "2025-03-24T10:26:53.437",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Шоколадный батончик MARS",
"DishSumInt": 50,
"OpenDate.Typed": "2025-03-18",
"OpenTime": "2025-03-24T10:23:59",
"OrderType": null,
"PayTypes": "Наличные",
"SessionNum": 17
},
{
"CloseTime": "2025-03-25T12:44:08.425",
"Delivery.CustomerName": null,
"Delivery.CustomerPhone": null,
"DishName": "Пицца ",
"DishSumInt": 240,
"OpenDate.Typed": "2025-03-24",
"OpenTime": "2025-03-24T13:21:53",
"OrderType": "Доставка самовывоз",
"PayTypes": "Наличные",
"SessionNum": 18
}
],
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-18T23:15:22.35", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18", |

|  | "OpenTime": "2025-03-18T20:13:45", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-19T12:58:35.344", |

|  | "Delivery.CustomerName": "Ермолаев Евгений", |

|  | "Delivery.CustomerPhone": "+79196129578", |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-18", |

|  | "OpenTime": "2025-03-19T12:56:35", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Банковские карты", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-24T10:26:53.437", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Шоколадный батончик MARS", |

|  | "DishSumInt": 50, |

|  | "OpenDate.Typed": "2025-03-18", |

|  | "OpenTime": "2025-03-24T10:23:59", |

|  | "OrderType": null, |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 17 |

|  | }, |

|  | { |

|  | "CloseTime": "2025-03-25T12:44:08.425", |

|  | "Delivery.CustomerName": null, |

|  | "Delivery.CustomerPhone": null, |

|  | "DishName": "Пицца ", |

|  | "DishSumInt": 240, |

|  | "OpenDate.Typed": "2025-03-24", |

|  | "OpenTime": "2025-03-24T13:21:53", |

|  | "OrderType": "Доставка самовывоз", |

|  | "PayTypes": "Наличные", |

|  | "SessionNum": 18 |

|  | } |

|  | ], |


---


## Page 32

API Documentation Page32 of 32
"summary": []
}
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | "summary": [] |

|  | } |

|  |  |


---
