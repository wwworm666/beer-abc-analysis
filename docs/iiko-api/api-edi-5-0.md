* [Старт](/articles/api-documentations/api-edi-5-0/a/h2_524909881)
* [Список заказов для участника EDI senderId и поставщика seller](/articles/api-documentations/api-edi-5-0/a/h2_735442749)
* [Параметры запроса](/articles/api-documentations/api-edi-5-0/a/h3_1827755295)
* [Что в ответе](/articles/api-documentations/api-edi-5-0/a/h3_501454233)
* [Пример вызова](/articles/api-documentations/api-edi-5-0/a/h3__232688264)
* [Пример ответа](/articles/api-documentations/api-edi-5-0/a/h3_451880483)
* [Подтверждение получения (квитирование ) заказа участником EDI](/articles/api-documentations/api-edi-5-0/a/h2_40796537)
* [Параметры запроса](/articles/api-documentations/api-edi-5-0/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/api-edi-5-0/a/h3_2097874707)
* [Пример вызова](/articles/api-documentations/api-edi-5-0/a/h3_1586190054)
* [Подтверждение внешнего заказа](/articles/api-documentations/api-edi-5-0/a/v1.APIEDI%285.0%29-Подтверждениевнешнегозаказа)
* [Параметры запроса](/articles/api-documentations/api-edi-5-0/a/h3__434216502)
* [Что в ответе](/articles/api-documentations/api-edi-5-0/a/h3__1613305986)
* [Примеры тела запроса](/articles/api-documentations/api-edi-5-0/a/h3__664166922)
* [Выполнение заказа](/articles/api-documentations/api-edi-5-0/a/h2_911441897)
* [Параметры запроса](/articles/api-documentations/api-edi-5-0/a/h3__157326665)
* [Тело запроса](/articles/api-documentations/api-edi-5-0/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/api-edi-5-0/a/h3__87789119)
* [Пример вызова](/articles/api-documentations/api-edi-5-0/a/h3_826905603)
* [Пример тела запроса](/articles/api-documentations/api-edi-5-0/a/h3_1111692745)

## Старт 

Чтобы подключиться и работать с API EDI в iiko, необходимо создать в iikoOffice систему EDI.

На данный момент при старте системы на чистой базе создаются три системы EDI:

| Внешняя система EDI | 709f5a71-47b6-f2fc-b5a8-d10176a851d7 |
| --- | --- |
| Внутренняя система EDI | b478869a-2c10-c398-5600-cd9202db4cd7 |
| Контур EDI | 947385b3-1f5f-1074-249a-ba09b8eb1d64 |

Настройки для создания и управления подключенными системами EDI находятся в iikoOffice:

* **Обмен данными**→**Системы EDI**

Выбрать нужную систему EDI можно у поставщика:

* **Поставщики** →**Персональная карточка** →**Дополнительные сведения** →**Система EDI**

Реализована проверка поставщика на принадлежность к системе EDI. При обращении к внешним заказам через API заказы фильтруются по EdiSystem, который нужно указывать в запросе.

База с предварительно настроенными Customer, Products для Chain: [ChainEdiTest.zip](/resources/Storage/api-documentations/ChainEdiTest.zip).

Данные для запросов по тестовой базе:

* EdiSystem для поставщика — Внешняя система EDI 709F5A71-47B6-F2FC-B5A8-D10176A851D7
* Имя поставщика — Вася.
* GLN поставщика — 4545646546454.
* Номер документа 10001.
* Дата 2016-06-02.

##  Список заказов для участника EDI senderId и поставщика seller
 
Версия iiko: 5.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**edi**/**{ediSystem}**/**orders**/**bySeller?gln={sellerGln}&inn={sellerInn}&kpp={sellerKpp}&name={sellerName}** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| ediSystem | GUID | Идентификатор участника EDI, подключенной к нашему REST API. <br>Каждый участник EDI должен получить свой собственный GUID ключ - идентификатор системы EDI (EdiSystem) для подключения к REST API электронного документооборота iiko. См. **Обмен данными → Системы EDI** в iikoOffce. |
| gln | String | GLN поставщика. Может отсутствовать, но тогда параметр inn должен быть заполнен |
| inn | String | ИНН (идентификационный номер налогоплательщика). Может отсутствовать, но тогда параметр gln должен быть заполнен |
| kpp | String | КПП (код причины постановки). Необязательное поле. |
| name | String | Имя поставщика. Необязательное поле |

### Что в ответе

Cписок заказов (Массив ediMessageDto).

Высылает список заказов EDI для зарегистрированного в системе iiko участника **ediSystem**и указанного поставщика. 
В списке присутствуют также те отмененные на стороне iiko заказы, получение которых участник подтвердил ранее. 
Получение как отправленных, так и отмененных заказов требуется подтверждать, см. метод **edi**/**{ediSystem}**/**orders**/**ack**

### Пример вызова 

https://localhost:9080/resto/api/edi/709f5a71-47b6-f2fc-b5a8-d10176a851d7/orders/bySeller?gln=4545646546454

###  Пример ответа 

[+] [Получили все заказы в статусе «Отправляется»](javascript:void%280%29)
 [-] [Получили все заказы в статусе «Отправляется»](javascript:void%280%29)
 
```
%%CH%PRE0%%%%CH%PRE1%% 
```


##  Подтверждение получения (квитирование) заказа участником EDI

Версия iiko: 5.0

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | https://host:port/resto/api/**edi**/**{ediSystem}**/**orders**/**bySeller?gln={sellerGln}&inn={sellerInn}&kpp={sellerKpp}&name={sellerName}** |
| --- | --- |

### Параметры запроса

###  

| Название | Значение | Описание |
| --- | --- | --- |
| ediSystem | GUID | Идентификатор участника EDI |
| number | String | Номер документа |
| date | String | Дата документа (в формате YYYY-MM-DD) |
| status | String | **original**— подтверждение получения заказа (по умолчанию).<br> <br>**canceled**— подтверждение получения участником EDI отмены заказа со стороны iikoServer'а. |

### Что в ответе
 
Вызов, подтверждающий получение заказа и изменяющий статус документа в iiko на "отправленный".
 
В этом статусе документ перестанет быть доступным в запросе списка заказов**.**
 
### Пример вызова

https://localhost:9080/resto/api/edi/709f5a71-47b6-f2fc-b5a8-d10176a851d7/orders/ack?number=10001&date=2016-06-02&status=original

## Подтверждение внешнего заказа 

* Поставщик может подтвердить, добавить и отменить позиции товаров.
* Чтобы подтвердить позицию, ее нужно прислать с теми же полями и соответствующими подтвержденными полями.
* Чтобы отменить позицию, достаточно прислать ее с нулевым количеством.
* Чтобы добавить позицию, нужно прислать ее с orderlineNumber = null и lineNumber не входящим в заказ.
* Чтобы уточнить позицию, ее нужно сначала удалить (обнулить количество), а потом добавить новую позицию.

Версия iiko: 5.0

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | https://host:port/resto/api/**edi/{ediSystem}/response** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| ediSystem | GUID | Идентификатор участника EDI |

### Что в ответе

Структура EdiMessageDto. Подтверждение внешнего заказа

### Пример вызова

https://localhost:9080/resto/api/edi/709f5a71-47b6-f2fc-b5a8-d10176a851d7/response

### Примеры тела запроса

[+] [Подтверждение всех позиций без уточнения](javascript:void%280%29)
 [-] [Подтверждение всех позиций без уточнения](javascript:void%280%29)
 
```
%%CH%PRE2%%%%CH%PRE3%% 
```

[+] [Подтверждение с удалением позиции](javascript:void%280%29)
 [-] [Подтверждение с удалением позиции](javascript:void%280%29)
 
```
%%CH%PRE4%%%%CH%PRE5%%

```

[+] [Подтверждение с новой позицией которая не является внутренним товаром](javascript:void%280%29)
 [-] [Подтверждение с новой позицией которая не является внутренним товаром](javascript:void%280%29)
 
```
%%CH%PRE6%%%%CH%PRE7%% 
```

[+] [Подтверждение с новой позицией которая является внутренним товаром](javascript:void%280%29)
 [-] [Подтверждение с новой позицией которая является внутренним товаром](javascript:void%280%29)
 
```
%%CH%PRE8%%%%CH%PRE9%%     
```

 
## Выполнение заказа 
 
Версия iiko: 5.0

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | https://host:port/resto/api/**edi/{EdiSystem}/invoice** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| senderId | GUID | Идентификатор пользователя |

### Тело запроса

Структура EdiMessageDto.

### Что в ответе 

Подтверждение отгрузки, отправка счета-фактуры в iiko.
 
### Пример вызова

https://localhost:9080/resto/api/edi/709f5a71-47b6-f2fc-b5a8-d10176a851d7/invoice

### Пример тела запроса

[+] [Подтверждение отгрузки](javascript:void%280%29)
 [-] [Подтверждение отгрузки](javascript:void%280%29)
 
```
%%CH%PRE10%%%%CH%PRE11%% 
```

[+] [XSD EdiMessageDto](javascript:void%280%29)
 [-] [XSD EdiMessageDto](javascript:void%280%29)
 
```
%%CH%PRE12%%%%CH%PRE13%% 
```
