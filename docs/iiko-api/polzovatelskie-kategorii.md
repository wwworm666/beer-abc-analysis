* [Получение пользовательских категорий (GET)](/articles/api-documentations/polzovatelskie-kategorii/a/h2__1157722915)
* [Параметры запроса](/articles/api-documentations/polzovatelskie-kategorii/a/h3_1827755295)
* [Результат (Список EntityDto)](/articles/api-documentations/polzovatelskie-kategorii/a/h3__730346366)
* [Что в ответе](/articles/api-documentations/polzovatelskie-kategorii/a/h3_501454233)
* [Пример запроса и результат](/articles/api-documentations/polzovatelskie-kategorii/a/h3_1250036116)
* [Получение пользовательских категорий (POST)](/articles/api-documentations/polzovatelskie-kategorii/a/h2_1277335404)
* [Параметры запроса](/articles/api-documentations/polzovatelskie-kategorii/a/h3__1577225432)
* [Что в ответе](/articles/api-documentations/polzovatelskie-kategorii/a/h3__918938987)
* [Импорт пользовательской категории](/articles/api-documentations/polzovatelskie-kategorii/a/h2__949064581)
* [Тело запроса](/articles/api-documentations/polzovatelskie-kategorii/a/h3_631086644)
* [Что в ответе](/articles/api-documentations/polzovatelskie-kategorii/a/h3_185825779)
* [Примеры запроса и результат](/articles/api-documentations/polzovatelskie-kategorii/a/h3__185610488)
* [Редактирование пользовательской категории](/articles/api-documentations/polzovatelskie-kategorii/a/h2_875448508)
* [Тело запроса](/articles/api-documentations/polzovatelskie-kategorii/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/polzovatelskie-kategorii/a/h3_1508133909)
* [Пример запроса и результат](/articles/api-documentations/polzovatelskie-kategorii/a/h3_276521740)
* [Удаление пользовательской категории](/articles/api-documentations/polzovatelskie-kategorii/a/h2__1948544756)
* [Тело запроса](/articles/api-documentations/polzovatelskie-kategorii/a/h3_1095830170)
* [Что в ответе](/articles/api-documentations/polzovatelskie-kategorii/a/h3__363142106)
* [Пример запроса и результат](/articles/api-documentations/polzovatelskie-kategorii/a/h3_2077977772)
* [Восстановление пользовательской категории](/articles/api-documentations/polzovatelskie-kategorii/a/h2_788676018)
* [Тело запроса](/articles/api-documentations/polzovatelskie-kategorii/a/h3_247050547)
* [Что в ответе](/articles/api-documentations/polzovatelskie-kategorii/a/h3__1120435937)
* [Примеры запроса и результат](/articles/api-documentations/polzovatelskie-kategorii/a/h3__726183675)
 
##  Получение пользовательских категорий (GET)
 
Версия iiko: 6.2

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/entities/products/category/list |
| --- | --- |

### Параметры запроса

| Параметр | Тип | Описание |
| --- | --- | --- |
| includeDeleted | Boolean | Включать ли в результат удаленные элементы. По умолчанию false. |
| ids | List&lt;UUID&gt; | Возвращаемые элементы должны иметь id из этого списка. |
| revisionFrom | -1, число | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

###  Результат (Список EntityDto) 

| Параметр | Тип | Описание |
| --- | --- | --- |
| id | UUID | UUID категории |
| deleted | Boolean | Удалена ли данная категория |
| name | String | Имя категории. |

### Что в ответе

Список пользовательских категорий

### Пример запроса и результат

#### Запрос

https://localhost:8080/resto/api/v2/entities/products/category/list

#### Результат


```json
[{ 
  "id":"7e29cd73-05da-7ac4-0165-0f11a132002b",
  "rootType":"ProductCategory",
  "deleted":false,
  "code":null,
  "name":"Категория 1"
}]
```

```json
[{ 
  "id":"7e29cd73-05da-7ac4-0165-0f11a132002b",
  "rootType":"ProductCategory",
  "deleted":false,
  "code":null,
  "name":"Категория 1"
}]
```


##  Получение пользовательских категорий (POST)
 
Версия iiko: 6.4

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/category/list |
| --- | --- |

### Параметры запроса
 
Content-Type: application/x-www-form-urlencoded

| Параметр | Версия | Тип | Описание |
| --- | --- | --- | --- |
| includeDeleted | 6.4 | Boolean | Включать ли в результат удаленные элементы. По умолчанию false. |
| ids | 6.4 | List&lt;UUID&gt; | Возвращаемые элементы должны иметь id из этого списка. |
| revisionFrom | 6.4 | -1, число | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

### Что в ответе

Список пользовательских категорий

## Импорт пользовательской категории
 
Версия iiko: 6.2

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/category/save |
| --- | --- |

### Тело запроса

| Поле | Тип данных | Значение |
| --- | --- | --- |
| name | String | Имя категории. |

### Что в ответе

Json структура результата импорта.
 
### Результат 

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| result | Enum: <br>"SUCCESS", <br>"ERROR" | Результата операции. |
| errors | List&lt;ErrorDto&gt; | Список ошибок, не позволивших сделать успешный импорт документа. |
| response | EntityDto | В случае успешного импорта - сохраненная пользовательская категория, <br>в противном случае импортируемый объект.<br> <br><br>| Поле | Тип данных | Значение |<br>| --- | --- | --- |<br>| id | UUID | UUID категории |<br>| deleted | Boolean | Удалена. |<br>| name | String | Имя категории. | |
| --- | --- | --- |

### Примеры запроса и результат

#### Запрос

https://localhost:8080/resto/api/v2/entities/products/category/save

#### Результат


```json
{  
   "name":"Категория 1"
}
```

```json
{  
   "name":"Категория 1"
}
```


Пример  результата вызова API: entities/products/category/save


```json
{  
   "result":"SUCCESS",
   "errors":null,
   "response":{  
      "id":"7e29cd73-05da-7ac4-0165-0f11a132002b",
      "rootType":"ProductCategory",
      "deleted":false,
      "code":null,
      "name":"Категория 1"
   }
}
```

```json
{  
   "result":"SUCCESS",
   "errors":null,
   "response":{  
      "id":"7e29cd73-05da-7ac4-0165-0f11a132002b",
      "rootType":"ProductCategory",
      "deleted":false,
      "code":null,
      "name":"Категория 1"
   }
}
```


Пример  результата вызова API: entities/products/category/save

Category name is not specified or consist of whitespaces

##  Редактирование пользовательской категории
 
Версия iiko: 6.2

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/category/update |
| --- | --- |

### Тело запроса

| Поле | Тип данных | Значение |
| --- | --- | --- |
| id | UUID | UUID редактируемой категории. |
| name | String | Новое имя категории. |

### Что в ответе

Json структура результата редактирования.
 
### Пример запроса и результат

#### Запрос 

https://localhost:8080/resto/api/v2/entities/products/category/save

#### Результат


```json
{ 
   "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137",
   "name":"Категория 2"
}
```

```json
{ 
   "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137",
   "name":"Категория 2"
}
```


Пример  результата вызова API: entities/products/category/update


```json
{  
   "result":"SUCCESS",
   "errors":null,
   "response":{  
      "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137",
      "rootType":"ProductCategory",
      "deleted":false,
      "code":null,
      "name":"Категория 2"
   }
}
```

```json
{  
   "result":"SUCCESS",
   "errors":null,
   "response":{  
      "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137",
      "rootType":"ProductCategory",
      "deleted":false,
      "code":null,
      "name":"Категория 2"
   }
}
```


Пример  результата вызова API: entities/products/category/update

Category name is not specified or consist of whitespaces

##  Удаление пользовательской категории
 
Версия iiko: 6.2

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/category/delete |
| --- | --- |

### Тело запроса

| Поле | Тип данных | Значение |
| --- | --- | --- |
| id | UUID | UUID удаляемой категории. |

### Что в ответе

Json структура результата удаления. Содержит результат удаления. Нельзя удалить уже удаленные объекты.
 
### Пример запроса и результат

#### Запрос 

https://localhost:8080/resto/api/v2/entities/products/category/delete

#### Результат


```json
{ 
   "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137" 
}
```

```json
{ 
   "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137" 
}
```


Пример  результата вызова API: entities/products/category/delete


```json
{  
   "result":"SUCCESS",
   "errors":null,
   "response":{  
      "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137",
      "rootType":"ProductCategory",
      "deleted":true,
      "code":null,
      "name":"Категория 1"
   }
}
```

```json
{  
   "result":"SUCCESS",
   "errors":null,
   "response":{  
      "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137",
      "rootType":"ProductCategory",
      "deleted":true,
      "code":null,
      "name":"Категория 1"
   }
}
```


Пример  результата вызова API: entities/products/category/save

Could not delete already deleted product category: [7e29cd73-05da-7ac4-0165-0f11a132002b].

## Восстановление пользовательской категории
 
Версия iiko: 6.2

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/category/restore |
| --- | --- |

### Тело запроса

| Поле | Тип данных | Значение |
| --- | --- | --- |
| id | UUID | UUID восстанавливаемой категории. |

### Что в ответе

Json структура результата восстановления. Содержит результат восстановления. Нельзя восстановить НЕ удаленные объекты.
 
### Примеры запроса и результат

#### Запрос

http://localhost:8080/resto/api/v2/entities/products/category/restore

#### Результат


```json
{ 
   "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137" 
}
```

```json
{ 
   "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137" 
}
```


Пример  результата вызова API: entities/products/category/restore


```json
{  
   "result":"SUCCESS",
   "errors":null,
   "response":{  
      "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137",
      "rootType":"ProductCategory",
      "deleted":false,
      "code":null,
      "name":"Категория 1"
   }
}
```

```json
{  
   "result":"SUCCESS",
   "errors":null,
   "response":{  
      "id":"70936cd4-474d-4b5f-b9bc-ac2799bfc137",
      "rootType":"ProductCategory",
      "deleted":false,
      "code":null,
      "name":"Категория 1"
   }
}
```


Пример  результата вызова API: entities/products/category/restore

Could not restore not deleted product category: [70936cd4-474d-4b5f-b9bc-ac2799bfc137]​.
