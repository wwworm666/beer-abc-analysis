* [Список заказов для участника EDI senderId](/articles/api-documentations/api-edi-5-1-6-4/a/h2__1508050013)
* [Параметры запроса](/articles/api-documentations/api-edi-5-1-6-4/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/api-edi-5-1-6-4/a/h3_501454233)
* [Пример вызова](/articles/api-documentations/api-edi-5-1-6-4/a/h3__232688264)
* [Пример ответа](/articles/api-documentations/api-edi-5-1-6-4/a/h3_451880483)
* [Создание нового заказа](/articles/api-documentations/api-edi-5-1-6-4/a/h2_1133502582)
* [Параметры запроса](/articles/api-documentations/api-edi-5-1-6-4/a/h3_645107953)
* [Коды предупреждений](/articles/api-documentations/api-edi-5-1-6-4/a/h3_1447894543)
* [Что в ответе](/articles/api-documentations/api-edi-5-1-6-4/a/h3__1171547305)
* [Пример вызова](/articles/api-documentations/api-edi-5-1-6-4/a/h3__2068148403)
* [Пример тела запроса](/articles/api-documentations/api-edi-5-1-6-4/a/h3_1111692745)
* [Пример ответа](/articles/api-documentations/api-edi-5-1-6-4/a/h3__1746232401)
* [Модификация заказа](/articles/api-documentations/api-edi-5-1-6-4/a/h2__767325681)
* [Параметры запроса](/articles/api-documentations/api-edi-5-1-6-4/a/h3_911750331)
* [Что в ответе](/articles/api-documentations/api-edi-5-1-6-4/a/h3__455286461)
* [Пример вызова](/articles/api-documentations/api-edi-5-1-6-4/a/h3_1569786416)
* [Пример тела запроса](/articles/api-documentations/api-edi-5-1-6-4/a/h3__1063508811)
* [Пример ответа](/articles/api-documentations/api-edi-5-1-6-4/a/h3__170204426)
* [Проведение заказа](/articles/api-documentations/api-edi-5-1-6-4/a/h2_170625537)
* [Параметры запроса](/articles/api-documentations/api-edi-5-1-6-4/a/h3_328331880)
* [Что в ответе](/articles/api-documentations/api-edi-5-1-6-4/a/h3__144104208)
* [Пример вызова](/articles/api-documentations/api-edi-5-1-6-4/a/h3_681751727)
* [Пример тела запроса](/articles/api-documentations/api-edi-5-1-6-4/a/h3__1867061581)
* [Пример ответа](/articles/api-documentations/api-edi-5-1-6-4/a/h3_1870453851)
* [Распроведение заказа](/articles/api-documentations/api-edi-5-1-6-4/a/h2_452539100)
* [Параметры запроса](/articles/api-documentations/api-edi-5-1-6-4/a/h3__163168811)
* [Что в ответе](/articles/api-documentations/api-edi-5-1-6-4/a/h3__2138844181)
* [Пример вызова](/articles/api-documentations/api-edi-5-1-6-4/a/h3__2062443567)
* [Постановка заказа на отправку](/articles/api-documentations/api-edi-5-1-6-4/a/v1.APIEDI%285.1%29-Постановказаказанаотправку)
* [Параметры запроса](/articles/api-documentations/api-edi-5-1-6-4/a/h3__1463516528)
* [Что в ответе](/articles/api-documentations/api-edi-5-1-6-4/a/h3__1056910489)
* [Пример вызова](/articles/api-documentations/api-edi-5-1-6-4/a/h3__311778831)

В версии 5.1 добавлен API «на запись», а также для получения списка заказов.
 
Как залогиниться в API, а также про операции EDI API, доступные начиная с версии 5.0, см. в статье [API EDI (5.0)](/smart/project-api-documentation/api-edi).

## Список заказов для участника EDI senderId 

Независимо от статуса за выбранный диапазон дат.

Версия iiko: 5.1, 6.4

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**edi**/**{ediSystem}**/**orders**/**list?from**=**{dateFrom}&to**=**{dateTo}** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| 
```
ediSystem

```
 | 
```
GUID 

```
 | Идентификатор участника EDI, подключенной к нашему REST API.<br> <br>Каждый участник EDI должен получить свой собственный GUID ключ - идентификатор системы EDI (EdiSystem) для подключения к REST API электронного документооборота iiko. См. **Обмен данными → Системы EDI** в iikoOffice. |
| 
```
from

```
 | String | Нижняя граница периода (дата в формате yyyy-MM-dd). Может быть не задана. |
| to | String | Верхняя граница периода (дата в формате yyyy-MM-dd). Может быть не задана. |
| revisionFrom | -1 | **(с версии 6.4)**<br><br>Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

### Что в ответе

Cписок заказов (OrderDto). Возвращает список заказов EDI для зарегистрированного в системе iiko участника **ediSystem**.

### Пример вызова 

https://localhost:9080/resto/api/edi/709f5a71-47b6-f2fc-b5a8-d10176a851d7/orders/list?key=26b4a1e9-4709-2fa5-9fc2-2979dcfa3cd8&from=2016-01-01&to=2017-01-01

### Пример ответа 

[+] [Список заказов за период](javascript:void%280%29)
 [-] [Список заказов за период](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
##  Создание нового заказа
 
Версия iiko: 5.1

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/**edi**/**{ediSystem}**/**orders/create** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| 
```
ediSystem

```
 | 
```
GUID  
```
 | Идентификатор участника EDI, подключенной к нашему REST API.<br> <br>Каждый участник EDI должен получить свой собственный GUID ключ - идентификатор системы EDI (EdiSystem) для подключения к REST API электронного документооборота iiko. См. "Обмен данными/Системы EDI" в iikoOffice. |

### **Коды предупреждений**

| Код | Описание |
| --- | --- |
| 
```
SUPPLIER_PRODUCT_NOT_FOUND
```
 | Нет внешнего продукта с указанным артикулом |
| 
```
SUPPLIER_PRICELIST_NOT_FOUND
```
 | Нет прайс-листа поставщика на указанную дату |
| 
```
PRODUCT_AND_SUPPLIER_PRODUCT_DO_NOT_MATCH
```
 | Есть внешний продукт с заданным артикулом. И есть прайс-лист поставщика на дату заказа. Но в этом прайс-листе нет указанной в строке заказа связки "внутренний продукт" + "внешний продукт" + "фасовка". |
| 
```
ORDER_ITEM_IS_POSSIBLY_INCORRECT
```
 | Строка заказа **возможно**(вероятно) некорректна. Например, если цена \* количество не равно сумме. |

### Что в ответе

Созданный заказ вместе с дополнительной информацией (возможные предупреждения при создании) в контейнере OrderCreationOrUpdateResultDto.
 
Создает новый заказ для зарегистрированного в системе iiko участника **ediSystem**. DTO заказа передается в теле HTTP-запроса.
 
В теле запроса рекомендуется не указывать номер документа. В этом случае номер ему будет присвоен автоматически, а в возвращенном DTO он будет указан.
Если же указать номер документа, то система попытается
использовать его. Но при совпадении номера документа с уже существующим документ не сохранится, и будет сгенерирована ошибка.

### Пример вызова 

https://localhost:9080/resto/api/edi/709f5a71-47b6-f2fc-b5a8-d10176a851d7/orders/create?key=59226cd3-b7d7-943f-6b35-6803bc6ccda5

### Пример тела запроса 

[+] [Создание нового заказа](javascript:void%280%29)
 [-] [Создание нового заказа](javascript:void%280%29)
 
```
%%CH%PRE2%%%%CH%PRE3%%
```


###  Пример ответа 

[+] [Ответ «все в порядке»](javascript:void%280%29)
 [-] [Ответ «все в порядке»](javascript:void%280%29)
 
```
%%CH%PRE4%%%%CH%PRE5%% 
```

[+] [Ответ с предупреждением (warning)](javascript:void%280%29)
 [-] [Ответ с предупреждением (warning)](javascript:void%280%29)
 
```
%%CH%PRE6%%%%CH%PRE7%%
```


##  Модификация заказа
 
Версия iiko: 5.1

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | https://host:port/resto/api/**edi/{ediSystem}/orders/update** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| 
```
ediSystem 
```
 | 
```
GUID  
```
 | Идентификатор участника EDI, подключенной к нашему REST API.<br> <br>Каждый участник EDI должен получить свой собственный GUID ключ - идентификатор системы EDI (EdiSystem) для подключения к REST API электронного документооборота iiko. См. **Обмен данными → Системы EDI** в iikoOffice. |

### Что в ответе

Модифицированный заказ вместе с дополнительной информацией (возможные предупреждения при обновлении) в контейнере OrderCreationOrUpdateResultDto.

Модифицирует переданный заказ EDI для зарегистрированного в системе iiko участника **ediSystem**. 
Номер и дата документа **не могут быть модифицированы**, т.к. используются для идентификации заказа.

### Пример вызова 

https://localhost:9080/resto/api/edi/709f5a71-47b6-f2fc-b5a8-d10176a851d7/orders/update?key=85471800-4e83-edff-02d3-c245270349b9

### Пример тела запроса 

[+] [Тело PUT-запроса на модификацию ранее сохраненного заказа](javascript:void%280%29)
 [-] [Тело PUT-запроса на модификацию ранее сохраненного заказа](javascript:void%280%29)
 
```
%%CH%PRE8%%%%CH%PRE9%% 
```


### Пример ответа

[+] [Ответ на запрос (нет предупреждений)](javascript:void%280%29)
 [-] [Ответ на запрос (нет предупреждений)](javascript:void%280%29)
 
```
%%CH%PRE10%%%%CH%PRE11%% 
```


## Проведение заказа
 
Версия iiko: 5.1

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | https://host:port/resto/api/**edi/{ediSystem}/orders/register** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| 
```
ediSystem 
```
 | 
```
GUID  
```
 | Идентификатор участника EDI, подключенной к нашему REST API.<br> <br>Каждый участник EDI должен получить свой собственный GUID ключ - идентификатор системы EDI (EdiSystem) для подключения к REST API электронного документооборота iiko. См. "Обмен данными/Системы EDI" в iikoOffice. |

### Что в ответе

Список проведенных заказов (OrderDto).

Осуществляет проведение (установку статуса "проведен") для заказов EDI, номера и даты которых переданы, для зарегистрированного в системе iiko участника **ediSystem**.

### Пример вызова 

https://localhost:9080/resto/api/edi/709f5a71-47b6-f2fc-b5a8-d10176a851d7/orders/register?key=85471800-4e83-edff-02d3-c245270349b9

### Пример тела запроса
[+] [Тело запроса — список идентификаторов документов, которые необходимо провести](javascript:void%280%29)
 [-] [Тело запроса — список идентификаторов документов, которые необходимо провести](javascript:void%280%29)
 
```
%%CH%PRE12%%%%CH%PRE13%%
```


### Пример ответа
[+] [Ответ на запрос на проведение документов — список проведенных документов с обновленными статусами](javascript:void%280%29)
 [-] [Ответ на запрос на проведение документов — список проведенных документов с обновленными статусами](javascript:void%280%29)
 
```
%%CH%PRE14%%%%CH%PRE15%%
```


##  Распроведение заказа
 
Версия iiko: 5.1

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | https://host:port/resto/api/**edi/{ediSystem}/orders/unregister** |
| --- | --- |

### Параметры запроса

### 

| Название | Значение | Описание |
| --- | --- | --- |
| 
```
ediSystem 
```
 | 
```
GUID  
```
 | Идентификатор участника EDI, подключенной к нашему REST API.<br> <br>Каждый участник EDI должен получить свой собственный GUID ключ - идентификатор системы EDI (EdiSystem) для подключения к REST API электронного документооборота iiko. См. **Обмен данными → Системы EDI** в iikoOffice. |

### Что в ответе

Список проведенных заказов (OrderDto).

Осуществляет распроведение (установку статуса "не проведен") для заказов EDI, номера и даты которых переданы, для зарегистрированного в системе iiko участника **ediSystem**. 
Операция, обратная проведению документов.

### Пример вызова

https://localhost:9080/resto/api/edi/709f5a71-47b6-f2fc-b5a8-d10176a851d7/orders/unregister?key=85471800-4e83-edff-02d3-c245270349b9
[+] [Пример тела запроса](javascript:void%280%29)
 [-] [Пример тела запроса](javascript:void%280%29)
 
```
%%CH%PRE16%%%%CH%PRE17%%
```


[+] [Пример ответа](javascript:void%280%29)
 [-] [Пример ответа](javascript:void%280%29)
 
```
%%CH%PRE18%%%%CH%PRE19%% 
```


##  Постановка заказа на отправку
 
Версия iiko: 5.1

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | https://host:port/resto/api/**edi/{ediSystem}/orders/send** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| 
```
ediSystem 
```
 | 
```
GUID  
```
 | Идентификатор участника EDI, подключенной к нашему REST API.<br> <br>Каждый участник EDI должен получить свой собственный GUID ключ - идентификатор системы EDI (EdiSystem) для подключения к REST API электронного документооборота iiko. См. **Обмен данными → Системы EDI** в iikoOffice. |

### Что в ответе

Список заказов (OrderDto), поставленных на отправку, с обновленными статусами.
 
Осуществляет постановку на отправку заказов EDI, номера и даты которых переданы, для зарегистрированного в системе iiko участника **ediSystem**.
 
### Пример вызова

https://localhost:9080/resto/api/edi/709f5a71-47b6-f2fc-b5a8-d10176a851d7/orders/send?key=8af2341a-d1fb-6e26-f8a0-701664d93181

[+] [Пример тела запроса](javascript:void%280%29)
 [-] [Пример тела запроса](javascript:void%280%29)
 
```
%%CH%PRE20%%%%CH%PRE21%%
```


[+] [Пример тела ответа](javascript:void%280%29)
 [-] [Пример тела ответа](javascript:void%280%29)
 
```
%%CH%PRE22%%%%CH%PRE23%%
```
