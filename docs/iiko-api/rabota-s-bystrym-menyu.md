* [Доступ](/articles/api-documentations/rabota-s-bystrym-menyu/a/v2.APIбыстрогоменю-Доступ)
* [Описание быстрого меню](/articles/api-documentations/rabota-s-bystrym-menyu/a/v2.APIбыстрогоменю-Описаниебыстрогоменю)
* [Получение списка быстрых меню (GET)](/articles/api-documentations/rabota-s-bystrym-menyu/a/v2.APIбыстрогоменю-Получениеспискабыстрыхменю%28GET%29)
* [Параметры запроса](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3_501454233)
* [Пример](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3_1250036116)
* [Получение списка быстрых меню (POST)](/articles/api-documentations/rabota-s-bystrym-menyu/a/v2.APIбыстрогоменю-Получениеспискабыстрыхменю%28POST%29)
* [Параметры запроса](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3__130600020)
* [Что в ответе](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3_345904457)
* [Создание быстрого меню](/articles/api-documentations/rabota-s-bystrym-menyu/a/v2.APIбыстрогоменю-Созданиебыстрогоменю)
* [Тело запроса](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3_2010954337)
* [Пример запроса и результата](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3_1561844723)
* [Тело запроса](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3_235180921)
* [Что в ответе](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3_301772306)
* [Пример запроса и результата](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3_1418450275)
* [Удаление быстрого меню](/articles/api-documentations/rabota-s-bystrym-menyu/a/v2.APIбыстрогоменю-Удалениебыстрогоменю)
* [Тело запроса](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3_1215231645)
* [Что в ответе](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3__44805358)
* [Пример запроса и результата](/articles/api-documentations/rabota-s-bystrym-menyu/a/h3_2060852943)

## Доступ 

Чтобы пользоваться данным API:

* У пользователя, под чьим именем осуществляется вход, должно быть право B\_QMENU "Просматривать быстрое меню".

## Описание быстрого меню

Быстрое меню состоит из трех страниц. Каждая страница из 3 х 8 ячеек. В ячейке может содержаться либо элемент номенклатуры, либо группа элементов номенклатуры.

| Поле | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | UUID быстрого меню. |
| **deleted** | boolean | Удалено или нет. |
| **dependsOnWeekDay** | boolean | Зависит ли меню от дня недели. |
| **departmentId** | UUID | Подразделение, для которого действует данное быстрое меню. |
| **sectionId** | UUID | Отделение, для которого действует данное быстрое меню. Если null, то быстрое меню для всего подразделения. |
| **pageNames** | List&lt;String&gt; | Названия страниц (3 штуки). |
| **labels** | List&lt;QuickLabelDto&gt; | Список ячеек.<br>| Поле | Тип | Описание |<br>| --- | --- | --- |<br>| **day** | Integer | День недели. Допустимые значения: 0, 1, 2, 3, 4, 5, 6, null.<br><br>Понедельник - 0. Воскресение - 6. |<br>| **page** | Integer | Номер страницы. Допустимые значения: 0, 1, 2. |<br>| **x** | Integer | Х-координата ячейки. Допустимые значения: 0, 1, 2. |<br>| **y** | Integer | Y-координата ячейки. Допустимые значения: 0, 1, 2, 3, 4, 5, 6, 7. |<br>| **entityId** | UUID | UUID сущности. |<br>| **entityType** | Enum | Тип сущности.<br>| Поле | Описание |<br>| --- | --- |<br>| PRODUCT | Элемент номенклатуры. |<br>| PRODUCT\_GROUP | Группа элементов номенклатуры. | |<br>| --- | --- | --- | |
| --- | --- | --- |

## Получение списка быстрых меню (GET)

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/entities/quickLabels/list |
| --- | --- |

### Параметры запроса
| Параметр | Тип | Описание |
| --- | --- | --- |
| **includeDeleted** | boolean | Включать ли в ответ удаленные быстрые меню. По умолчанию false. |
| **revisionFrom** | Integer | Номер ревизии, начиная с которой необходимо отфильтровать сущности. |
| **id** | List&lt;UUID&gt; | Возвращаемые быстрые меню должны иметь id из этого списка. |
| **departmentId** | List&lt;UUID&gt; | Возвращаемые быстрые меню должны принадлежать подразделению, у которого id из этого списка. |
| **sectionId** | List&lt;UUID&gt; | Возвращаемые быстрые меню должны принадлежать отделению, у которого id из этого списка. Может содержать null. См. примеры. |
### Что в ответе

Список всех быстрых меню для всего подразделения. Содержит "общее" быстрое меню для всего подразделения и быстрое меню для конкретного отделения.

### Пример
https://localhost:9080/resto/api/v2/entities/quickLabels/list?departmentId=6713a472-973e-4215-8e0f-e3142945befd

[+] [Результат](javascript:void%280%29)
 [-] javascript:void%280%29Результат
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```


"Общее" быстрое меню подразделения. Фильтруем по sectionId = null.
https://localhost:9080/resto/api/v2/entities/quickLabels/list?departmentId=6713a472-973e-4215-8e0f-e3142945befd&sectionId=null
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 
## Получение списка быстрых меню (POST)

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/**entities/quickLabels/list** |
| --- | --- |

### Параметры запроса

| Параметр | Тип | Описание |
| --- | --- | --- |
| **includeDeleted** | boolean | Включать ли в ответ удаленные быстрые меню. По умолчанию false. |
| **revisionFrom** | Integer | Номер ревизии, начиная с которой необходимо отфильтровать сущности. |
| **id** | List&lt;UUID&gt; | Возвращаемые быстрые меню должны иметь id из этого списка. |
| **departmentId** | List&lt;UUID&gt; | Возвращаемые быстрые меню должны принадлежать подразделению, у которого id из этого списка. |
| **sectionId** | List&lt;UUID&gt; | Возвращаемые быстрые меню должны принадлежать отделению, у которого id из этого списка. Может содержать null. См. примеры. |

### Что в ответе
Список быстрых меню.

## Создание быстрого меню

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/**entities/quickLabels/save** |
| --- | --- |

### Тело запроса

Список ячеек
| Поле | Тип | Описание |
| --- | --- | --- |
| **dependsOnWeekDay** | boolean | Зависит ли меню от дня недели. |
| **departmentId** | UUID | Подразделение, для которого действует данное быстрое меню. |
| **sectionId** | UUID | Отделение, для которого действует данное быстрое меню. Если null, то быстрое меню для всего подразделения. |
| **pageNames** | List&lt;String&gt; | Названия страниц (3 штуки). |
| **labels** | List&lt;QuickLabelDto&gt; | Список ячеек<br>| Поле | Тип | Описание |<br>| --- | --- | --- |<br>| **day** | Integer | День недели. Допустимые значения: 0, 1, 2, 3, 4, 5, 6, null.<br><br>Понедельник - 0. Воскресение - 6. |<br>| **page** | Integer | Номер страницы. Допустимые значения: 0, 1, 2. |<br>| **x** | Integer | Х-координата ячейки. Допустимые значения: 0, 1, 2. |<br>| **y** | Integer | Y-координата ячейки. Допустимые значения: 0, 1, 2, 3, 4, 5, 6, 7. |<br>| **entityId** | UUID | UUID сущности. | |
| --- | --- | --- | [+] [Пример тела запроса](javascript:void%280%29)
 [-] [Пример тела запроса](javascript:void%280%29)
 
```
 %%CH%PRE4%%%%CH%PRE5%%
```

 
### Что в ответе

Созданное быстрое меню.

### Пример запроса и результата

#### Запрос

https://localhost:9080/resto/api/v2/entities/quickLabels/save
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE6%%%%CH%PRE7%%
```

 
Редактирование быстрого меню

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/quickLabels/update |
| --- | --- |

### Тело запроса

Список ячеек.
| Поле | Тип | Описание |
| --- | --- | --- |
| **id** | Integer | День недели. Допустимые значения: 0, 1, 2, 3, 4, 5, 6, null.<br><br>Понедельник - 0. Воскресение - 6. |
| **dependsOnWeekDay** | Integer | Номер страницы. Допустимые значения: 0, 1, 2. |
| **departmentId** | Integer | Х-координата ячейки. Допустимые значения: 0, 1, 2. |
| **sectionId** | Integer | Y-координата ячейки. Допустимые значения: 0, 1, 2, 3, 4, 5, 6, 7. |
| **pageNames** | UUID | UUID сущности. |
| **labels** | List&lt;QuickLabelDto&gt; | Список ячеек.<br>| Поле | Тип | Описание |<br>| --- | --- | --- |<br>| **day** | Integer | День недели. Допустимые значения: 0, 1, 2, 3, 4, 5, 6, null.<br><br>Понедельник - 0. Воскресение - 6. |<br>| **page** | Integer | Номер страницы. Допустимые значения: 0, 1, 2. |<br>| **x** | Integer | Х-координата ячейки. Допустимые значения: 0, 1, 2. |<br>| **y** | Integer | Y-координата ячейки. Допустимые значения: 0, 1, 2, 3, 4, 5, 6, 7. |<br>| **entityId** | UUID | UUID сущности. | |
| --- | --- | --- | [+] [Пример тела запроса](javascript:void%280%29)
 [-] [Пример тела запроса](javascript:void%280%29)
 
```
 %%CH%PRE8%%%%CH%PRE9%%
```

 
### Что в ответе

Отредактированное быстрое меню.

### Пример запроса и результата

#### Запрос
https://localhost:9080/resto/api/v2/entities/quickLabels/update
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE10%%%%CH%PRE11%%
```


## Удаление быстрого меню

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/ |
| --- | --- |

### Тело запроса
| Поле | Тип | Описание |
| --- | --- | --- |
| **id** | UUID | UUID быстрого меню |
**Пример тела запроса**


Код

```
{
    "id": "345f5b9d-a356-f4e8-016b-080f9c44002a"
}
```

Код

```
{
    "id": "345f5b9d-a356-f4e8-016b-080f9c44002a"
}
```


### Что в ответе

Быстрое меню, помеченное как удаленное.

### Пример запроса и результата

#### Запрос

https://localhost:9080/resto/api/v2/entities/quickLabels/delete
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE14%%%%CH%PRE15%%
```
