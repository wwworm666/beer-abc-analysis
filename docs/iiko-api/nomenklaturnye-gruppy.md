* [Получение номенклатурных групп](/articles/api-documentations/nomenklaturnye-gruppy/a/h2__1478949185)
* [Параметры запроса](/articles/api-documentations/nomenklaturnye-gruppy/a/h3_1829577547)
* [Что в ответе](/articles/api-documentations/nomenklaturnye-gruppy/a/h3_501454233)
* [Результат (Список ProductGroupDto)](/articles/api-documentations/nomenklaturnye-gruppy/a/h3_307020783)
* [Пример запроса и результата](/articles/api-documentations/nomenklaturnye-gruppy/a/h3_1561844723)
* [Получение номенклатурных групп](/articles/api-documentations/nomenklaturnye-gruppy/a/v2.APIимпортаноменклатуры-Получениеноменклатурныхгрупп%28POST%29)
* [Тело запроса](/articles/api-documentations/nomenklaturnye-gruppy/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/nomenklaturnye-gruppy/a/h3__1747822427)
* [Импорт номенклатурной группы](/articles/api-documentations/nomenklaturnye-gruppy/a/h2__905970947)
* [Параметры запроса](/articles/api-documentations/nomenklaturnye-gruppy/a/h3__998506674)
* [Тело запроса](/articles/api-documentations/nomenklaturnye-gruppy/a/h3__54014465)
* [Что в ответе](/articles/api-documentations/nomenklaturnye-gruppy/a/h3_606733053)
* [Пример запроса и результата](/articles/api-documentations/nomenklaturnye-gruppy/a/h3__506195026)
* [Редактирование номенклатурной группы](/articles/api-documentations/nomenklaturnye-gruppy/a/h2_891207551)
* [Тело запроса](/articles/api-documentations/nomenklaturnye-gruppy/a/h3_2081311269)
* [Что в ответе](/articles/api-documentations/nomenklaturnye-gruppy/a/h3__993123617)
* [Пример запроса и результата](/articles/api-documentations/nomenklaturnye-gruppy/a/h3_1957099070)
* [Удаление номенклатурной группы](/articles/api-documentations/nomenklaturnye-gruppy/a/h2__2943917)
* [Тело запроса](/articles/api-documentations/nomenklaturnye-gruppy/a/h3__2036712792)
* [Что в ответе](/articles/api-documentations/nomenklaturnye-gruppy/a/h3__1298106281)
* [Результат](/articles/api-documentations/nomenklaturnye-gruppy/a/h3_1951247192)
* [Пример запроса и результата](/articles/api-documentations/nomenklaturnye-gruppy/a/h3__1623875098)
* [Восстановление номенклатурной группы](/articles/api-documentations/nomenklaturnye-gruppy/a/h2__1597829593)
* [Параметры запроса](/articles/api-documentations/nomenklaturnye-gruppy/a/h3__1106799684)
* [Тело запроса](/articles/api-documentations/nomenklaturnye-gruppy/a/h3_1251733974)
* [Что в ответе](/articles/api-documentations/nomenklaturnye-gruppy/a/h3_880757139)

##  Получение номенклатурных групп

Версия iiko: 6.2

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/entities/products/group/list |
| --- | --- |

### Параметры запроса

| Параметр | Версия iiko | Тип, формат | Описание |
| --- | --- | --- | --- |
| includeDeleted | 6.2 | Boolean | Включать ли в результат удаленные элементы. По умолчанию false. |
| ids | 6.2 | List&lt;UUID&gt; | Возвращаемые элементы должны иметь id из этого списка. |
| parentIds | 6.2 | List&lt;UUID&gt; | Возвращаемые элементы должны иметь родительскую группу с id из этого списка. |
| revisionFrom | 6.4 | -1, число | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |
| nums | 6.2.3 | List&lt;String&gt; | Возвращаемые элементы должны иметь артикул из этого списка. |
| codes | 6.2.3 | List&lt;String&gt; | Возвращаемые элементы должны иметь код из этого списка. |

### Что в ответе

Список номенклатурных групп

### Результат (Список ProductGroupDto) 

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| id | UUID | UUID номенклатурной группы. |
| deleted | Boolean | Удален. |
| name | String | Имя. |
| description | String | Описание. |
| num | String | Артикул, используется при печати документов (тех. карт и т.д.). |
| code | String | Код продукта. Используется для быстрого поиска продукта <br>в экране редактирования заказа. |
| parent | UUID | UUID родительской группы. <br>Если группа принадлежит корневой группе, то parent == null. |
| modifiers | List&lt;ChoiceBindingDto&gt; | Moдификаторы. (у групп всегда отсутствуют). |
| taxCategory | UUID | UUID налоговой категории. |
| category | UUID | UUID пользовательской категории. |
| accountingCategory | UUID | UUID бухгалтерской категории. |
| color | RGBColorDto | Цвет фона оформления кнопки в iikoFront. |
| fontColor | RGBColorDto | Цвет шрифта кнопки в iikoFront. |
| frontImageId | UUID | UUID изображения для отображения в iikoFront.API изображений. |
| position | Integer | Позиция в меню. |
| visibilityFilter | DepartmentFilterDto | | Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| departments | List&lt;UUID&gt; | Список UUID подразделений |<br>| excluding | Boolean | Включающий или исключающий фильтр | |
| --- | --- | --- |

### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/products/group/list?includeDeleted=false

 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
## Получение номенклатурных групп 

Версия iiko: 6.4

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/group/list |
| --- | --- |

### Тело запроса

| Поле | Версия iiko | Тип данных | Значение |
| --- | --- | --- | --- |
| includeDeleted | 6.4 | Boolean | Включать ли в результат удаленные элементы. По умолчанию false.. |
| revisionFrom | 6.4 | -1, число | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1. |
| ids | 6.4 | List&lt;UUID&gt; | Возвращаемые элементы должны иметь id из этого списка. |
| nums | 6.4 | List&lt;String&gt; | Возвращаемые элементы должны иметь артикул из этого списка. |
| codes | 6.4 | List&lt;String&gt; | Возвращаемые элементы должны иметь код из этого списка. |
| parentIds | 6.4 | List&lt;UUID&gt; | Возвращаемые элементы должны иметь родительскую группу с id из этого списка. |

### Что в ответе

Список номенклатурных групп

## Импорт номенклатурной группы
 
Версия iiko: 6.2

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/group/save |
| --- | --- |

### **Параметры запроса**

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| generateNomenclatureCode | Boolean | Надо ли генерировать артикул номенклатурной группы.<br><br>Необязательный. По умолчанию true. |
| generateFastCode | Boolean | Надо ли генерировать код быстрого поиска номенклатурной группы.<br><br>Необязательный. По умолчанию true. |

### Тело запроса

| Поле | Версия iiko | Тип данных | Значение |
| --- | --- | --- | --- |
| deleted | 6.2 | Boolean | Удален. |
| name | 6.2 | String | Имя. |
| description | 6.2 | String | Описание. |
| parent | 6.2 | UUID | UUID родительской группы продукта. <br>Если продукт принадлежит корневой группе, то parent == null. |
| taxCategory | 6.2 | UUID | UUID налоговой категории. |
| category | 6.2 | UUID | UUID пользовательской категории. |
| color | 6.2 | RGBColorDto | Цвет фона оформления кнопки в iikoFront. |
| fontColor | 6.2 | RGBColorDto | Цвет шрифта кнопки в iikoFront. |
| frontImageId | 6.2 | UUID | UUID изображения для отображения в iikoFront. |
| position | 6.2 | Integer | Позиция в меню. |

### Что в ответе
 
Содержит Json структуру результата импорта, которая состоит из результата валидации импортируемой группы 
и самой группы. Результат валидации состоит из ошибок. Ошибка состоит из кода ошибки и текста ошибки.

###  

| Поле | Тип данных | Значение |
| --- | --- | --- |
| result | Enum: <br>"SUCCESS", <br>"ERROR" | Результата операции. |
| errors | List&lt;ErrorDto&gt; | Список ошибок, не позволивших сделать успешный импорт документа. |
| response | ProducGrouptDto | В случае успешного импорта - сохраненный объект, <br>в противном случае импортируемый объект. |

### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/products/save

#### Результат


```json
{ 
   "name":"Группа 1",
   "description":"тест",
   "parent":"b48f8846-2395-44bb-938d-1e208b753e6d",
   "taxCategory":null,
   "category":null,
   "color":{ 
      "red":170,
      "green":170,
      "blue":170
   },
   "fontColor":{ 
      "red":0,
      "green":0,
      "blue":0
   },
   "frontImageId":"67ae50d5-d1b1-4afb-9d04-469aa49a2e05",
   "position":null
}
```

```json
{ 
   "name":"Группа 1",
   "description":"тест",
   "parent":"b48f8846-2395-44bb-938d-1e208b753e6d",
   "taxCategory":null,
   "category":null,
   "color":{ 
      "red":170,
      "green":170,
      "blue":170
   },
   "fontColor":{ 
      "red":0,
      "green":0,
      "blue":0
   },
   "frontImageId":"67ae50d5-d1b1-4afb-9d04-469aa49a2e05",
   "position":null
}
```

 [+] [Пример  результата вызова API: entities/products/group/save](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/group/save](javascript:void%280%29)
 
```
 %%CH%PRE4%%%%CH%PRE5%%
```

 [+] [Пример  результата вызова API: entities/products/group/save](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/group/save](javascript:void%280%29)
 
```
 %%CH%PRE6%%%%CH%PRE7%%
```

 
##  Редактирование номенклатурной группы

Версия iiko: 6.2

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/group/update |
| --- | --- |

**Параметры запроса**

| Параметр | Тип, формат | Описание |
| --- | --- | --- |
| overrideFastCode | Boolean | Перегенерировать ли код быстрого поиска номенклатурной группы.<br><br>Необязательный. По умолчанию false |
| overrideNomenclatureCode | Boolean | Перегенерировать ли артикул номенклатурной группы.<br><br>Необязательный. По умолчанию false. |

### Тело запроса
 
Аналогично импорту только с id редактируемого элемента:

| Поле | Тип данных | Значение |
| --- | --- | --- |
| id | UUID | UUID редактируемой номенклатурной группы |


```json
{ 
   "id":"68569fd5-17bc-382b-0165-0a151ab6011e",
   "name":"Группа 1",
   "description":"тестРедактировали",
   "parent":"b48f8846-2395-44bb-938d-1e208b753e6d",
   "taxCategory":null,
   "category":null,
   "color":{ 
      "red":170,
      "green":170,
      "blue":170
   },
   "fontColor":{ 
      "red":100,
      "green":0,
      "blue":0
   },
   "frontImageId":"67ae50d5-d1b1-4afb-9d04-469aa49a2e05",
   "position":null
}
```

```json
{ 
   "id":"68569fd5-17bc-382b-0165-0a151ab6011e",
   "name":"Группа 1",
   "description":"тестРедактировали",
   "parent":"b48f8846-2395-44bb-938d-1e208b753e6d",
   "taxCategory":null,
   "category":null,
   "color":{ 
      "red":170,
      "green":170,
      "blue":170
   },
   "fontColor":{ 
      "red":100,
      "green":0,
      "blue":0
   },
   "frontImageId":"67ae50d5-d1b1-4afb-9d04-469aa49a2e05",
   "position":null
}
```


###  Что в ответе

Содержит Json структуру результата изменений, которая состоит из результата валидации измененной группы 
и самой группы. Результат валидации состоит из ошибок. Ошибка состоит из кода ошибки и текста ошибки.

### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/products/update?overrideFastCode=false&overrideNomenclatureCode=false
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE10%%%%CH%PRE11%%
```

 [+] [Пример  результата вызова API: entities/products/update](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/update](javascript:void%280%29)
 
```
 %%CH%PRE12%%%%CH%PRE13%%
```

 [+] [Пример  результата вызова API: entities/products/update](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/update](javascript:void%280%29)
 
```
 %%CH%PRE14%%%%CH%PRE15%%
```

 
##  Удаление номенклатурной группы
 
Версия iiko: 6.2

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/group/delete |
| --- | --- |

### Тело запроса
 
ProductsAndGroupsDto&lt;IdListDto IdListDto&gt;

| Поле | Тип данных | Значение |
| --- | --- | --- |
| products | IdListDto | Список UUID продуктов, которые нужно удалить. |
| productGroups | IdListDto | Список UUID групп, которые нужно удалить. |


```json
{ 
   "products":{ 
      "items":[ 
         { 
            "id":"883CB6A8-621D-4BFB-8595-403E41BE62E8"
         },
         { 
            "id":"6E1ECAD4-E6A8-4887-B835-9639DACB7387"
         }
      ]
   },
   "productGroups":{ 
      "items":[ 
         { 
            "id":"e10037a7-7e1f-4296-9e2c-a2c9ac551711"
         },
         { 
            "id":"cc455ea0-ad9a-4c28-a350-4d383fb4b71b"
         }
      ]
   }
}
```

```json
{ 
   "products":{ 
      "items":[ 
         { 
            "id":"883CB6A8-621D-4BFB-8595-403E41BE62E8"
         },
         { 
            "id":"6E1ECAD4-E6A8-4887-B835-9639DACB7387"
         }
      ]
   },
   "productGroups":{ 
      "items":[ 
         { 
            "id":"e10037a7-7e1f-4296-9e2c-a2c9ac551711"
         },
         { 
            "id":"cc455ea0-ad9a-4c28-a350-4d383fb4b71b"
         }
      ]
   }
}
```


###  Что в ответе

Содержит Json структуру результата удаления. Нельзя удалить уже удаленные объекты. Так же нельзя удалить группу без удаления дочерних элементов.

### Результат 

| Поле | Тип данных | Значение |
| --- | --- | --- |
| result | Enum: "SUCCESS", "ERROR" | Результат операции. |
| errors | List&lt;ErrorDto&gt; | Список ошибок, не позволивших сделать успешный импорт. |
| response | ProductsAndGroupsDto&lt;Collection&lt;ProductDto&gt;, Collection&lt;ProductGroupDto&gt;&gt; | В случае успешного удаления - списки удаленных объектов :<br> <br><br>| Поле | Тип данных | Значение |<br>| --- | --- | --- |<br>| products | Collection&lt;ProductDto&gt; | Список продуктов, которые удалили. |<br>| productGroups | Collection&lt;ProductGroupDto&gt; | Список групп, которые удалили. |<br><br> <br>в противном случае ошибка с описанием причины. |
| --- | --- | --- |

### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/products/group/delete

#### Результат


```json
{ 
   "products":{ 
      "items":[ 
         { 
            "id":"883CB6A8-621D-4BFB-8595-403E41BE62E8"
         },
         { 
            "id":"6E1ECAD4-E6A8-4887-B835-9639DACB7387"
         }
      ]
   },
   "productGroups":{ 
      "items":[ 
         { 
            "id":"e10037a7-7e1f-4296-9e2c-a2c9ac551711"
         },
         { 
            "id":"cc455ea0-ad9a-4c28-a350-4d383fb4b71b"
         }
      ]
   }
}
```

```json
{ 
   "products":{ 
      "items":[ 
         { 
            "id":"883CB6A8-621D-4BFB-8595-403E41BE62E8"
         },
         { 
            "id":"6E1ECAD4-E6A8-4887-B835-9639DACB7387"
         }
      ]
   },
   "productGroups":{ 
      "items":[ 
         { 
            "id":"e10037a7-7e1f-4296-9e2c-a2c9ac551711"
         },
         { 
            "id":"cc455ea0-ad9a-4c28-a350-4d383fb4b71b"
         }
      ]
   }
}
```

 [+] [Пример  результата вызова API: entities/products/group/delete](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/group/delete](javascript:void%280%29)
 
```
 %%CH%PRE20%%%%CH%PRE21%%
```

 [+] [Пример  результата вызова API: entities/products/delete](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/delete](javascript:void%280%29)
 
```
    Could not delete ProductGroup without deleting child groups and child products.   
   ProductGroups should be deleted too: [Удалить (PRODUCTS)].   
   Products should be deleted too: [Соус грибной (MODIFIER), Соус барбекю (GOODS), М_Соус барбекю (MODIFIER), Соус сырный (MODIFIER)]. 

```

 
## 

##  Восстановление номенклатурной группы
 
Версия iiko: 6.2

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/group/restore |
| --- | --- |

### **Параметры запроса**

| Параметр | Версия iiko | Тип, формат | Описание |
| --- | --- | --- | --- |
| overrideNomenclatureCode | 6.4 | Boolean | Если у восстанавливаемого группы артикул совпадает с одним из текущих и параметр указан равным true, то у восстанавливаемого группы будет сгенерирован новый артикул.<br><br>Необязательный. По умолчанию false. |

### Тело запроса
 
ProductsAndGroupsDto&lt;IdListDto IdListDto&gt;

| Поле | Тип данных | Значение |
| --- | --- | --- |
| products | IdListDto | Список UUID продуктов, которые нужно удалить. |
| productGroups | IdListDto | Список UUID групп, которые нужно удалить. |

### Что в ответе

Содержит Json структуру результата восстановления. Нельзя восстановить НЕ удаленные объекты. 
Так же нельзя восстановить группу без восстановления родительской группы, если та удалена.
