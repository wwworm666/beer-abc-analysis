* [Статусы репликации](/articles/api-documentations/statusy-replikatsii/a/h2__1776990759)
* [Версия iiko: 5.0](/articles/api-documentations/statusy-replikatsii/a/v1.APIрепликации%285.0%29-Статусырепликации)
* [Что в ответе](/articles/api-documentations/statusy-replikatsii/a/h3_501454233)
* [Пример вызова](/articles/api-documentations/statusy-replikatsii/a/h3__232688264)
* [Статус репликации с конкретным ТП](/articles/api-documentations/statusy-replikatsii/a/h2__719236598)
* [Версия iiko: 5.0](/articles/api-documentations/statusy-replikatsii/a/h2__1144420586)
* [Что в ответе](/articles/api-documentations/statusy-replikatsii/a/h3__76589314)
* [Пример вызова](/articles/api-documentations/statusy-replikatsii/a/h3_1723832711)
* [Тип сервера](/articles/api-documentations/statusy-replikatsii/a/h2_1673153662)
* [Версия iiko: 5.0](/articles/api-documentations/statusy-replikatsii/a/h2_2128962438)
* [Что в ответе](/articles/api-documentations/statusy-replikatsii/a/h3_93287844)
* [Пример вызова](/articles/api-documentations/statusy-replikatsii/a/h3__1801303120)

## Статусы репликации

## Версия iiko: 5.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**replication/statuses** |
| --- | --- |

### Что в ответе

Список статусов последних репликаций.
* При выполнении в Чейн - выводит список статусов репликаций для всех подключенных к Чейну РМС;
* При выполнении на РМС, будет выкинута ошибка.

### **Пример вызова**

https://localhost:9080/resto/api/replication/statuses?key=71046728-36fa-053c-b01c-c5b43bfd277f

## Статус репликации с конкретным ТП

## Версия iiko: 5.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**replication/byDepartmentId/{departmentId}/status** |
| --- | --- |

### Что в ответе

Статус репликации конкретного ТП.

При выполнении в Чейн, выводит статус репликации для указанного РМС, или ошибку, если в Чейн нет ТП с таким идентификатором;

При выполнении на РМС, будет ошибка.

### **Пример вызова**

https://localhost:9080/resto/api/replication/byDepartmentId/f176aa55-9343-46be-bf75-958a0a068360/status?key=71046728-36fa-053c-b01c-c5b43bfd277f

## Тип сервера

## Версия iiko: 5.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**replication/serverType** |
| --- | --- |

### Что в ответе

Тип сервера: CHAIN, REPLICATED\_RMS, STANDALONE\_RMS.

### **Пример вызова**

https://localhost:9080/resto/api/replication/serverType?key=71046728-36fa-053c-b01c-c5b43bfd277f
