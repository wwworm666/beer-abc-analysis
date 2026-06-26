* [Получение элементов номенклатуры](/articles/api-documentations/elementy-nomenklatury/a/h2__2122965202)
* [Параметры запроса](/articles/api-documentations/elementy-nomenklatury/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/elementy-nomenklatury/a/h3_501454233)
* [Пример запроса и результата](/articles/api-documentations/elementy-nomenklatury/a/h3_1561844723)
* [Получение элементов номенклатуры](/articles/api-documentations/elementy-nomenklatury/a/v2.APIимпортаноменклатуры-Получениеэлементовноменклатуры%28POST%29)
* [Тело запроса](/articles/api-documentations/elementy-nomenklatury/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/elementy-nomenklatury/a/h3__910896685)
* [Импорт элемента номенклатуры](/articles/api-documentations/elementy-nomenklatury/a/h2_26989340)
* [Параметры запроса](/articles/api-documentations/elementy-nomenklatury/a/h3__1704918338)
* [Что в ответе](/articles/api-documentations/elementy-nomenklatury/a/h3__1933026233)
* [Пример запроса и результата](/articles/api-documentations/elementy-nomenklatury/a/h3__1647466043)
* [Редактирование элемента номенклатуры](/articles/api-documentations/elementy-nomenklatury/a/h2__1144036084)
* [Параметры запроса](/articles/api-documentations/elementy-nomenklatury/a/h3__1491948775)
* [Тело запроса](/articles/api-documentations/elementy-nomenklatury/a/h3__87828366)
* [Что в ответе](/articles/api-documentations/elementy-nomenklatury/a/h3_871739065)
* [Примеры запроса и результата](/articles/api-documentations/elementy-nomenklatury/a/h3_710210636)
* [Удаление элементов номенклатуры](/articles/api-documentations/elementy-nomenklatury/a/h2_1831563864)
* [Тело запроса](/articles/api-documentations/elementy-nomenklatury/a/h3__1673974090)
* [Что в ответе](/articles/api-documentations/elementy-nomenklatury/a/h3__1181879789)
* [Примеры запроса и результат](/articles/api-documentations/elementy-nomenklatury/a/h3__185610488)
* [Восстановление элементов номенклатуры](/articles/api-documentations/elementy-nomenklatury/a/h2_317365814)
* [Параметры запроса](/articles/api-documentations/elementy-nomenklatury/a/h3__313606736)
* [Тело запроса](/articles/api-documentations/elementy-nomenklatury/a/h3_268758673)
* [Что в ответе](/articles/api-documentations/elementy-nomenklatury/a/h3__801210531)
* [Пример запроса и результата](/articles/api-documentations/elementy-nomenklatury/a/h3_1226685010)

## Получение элементов номенклатуры

Чтобы пользоваться API экспорта и импорта номенклатуры:

* У пользователя, под чьим именем осуществляется вход, должно быть право B\_EN "Редактирование номенклатурных справочников".

Версия iiko: 6.1

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **https://host:port/resto/api/v2/entities/products/list** |
| --- | --- |

### Параметры запроса

| ![Information](/resources/Storage/api-documentations/info.png) | Если надо отфильтровать по полю, значение которого null, то соответствующее значение параметра не задаём: "parentId=". На сервере это будет список с одним нулевым элементом [null].<br><br>Если надо отфильтровать сразу по нескольким параметрам одного типа, например parentId, параметры передаём в следующим виде: "parentId=111&parentId=222&parentId=333". На сервере это преобразуется в список [111, 222, 333].<br><br><br>Следующий список параметров "parentId=111&parentId=222&parentId=" на сервере преобразуется в [111, 222, null]. |
| --- | --- |

| Параметр | Версия iiko | Тип, формат | Описание |
| --- | --- | --- | --- |
| includeDeleted | 6.1 | Boolean | Включать ли в результат удаленные элементы. По умолчанию false. |
| ids | 6.2 | List&lt;UUID&gt; | Возвращаемые элементы номенклатуры должны иметь id из этого списка. |
| nums | 6.2 | List&lt;String&gt; | Возвращаемые элементы номенклатуры должны иметь артикул из этого списка. |
| types | 6.2 | List&lt;ProductType&gt; | Возвращаемые элементы номенклатуры должны иметь тип из этого списка. |
| categoryIds | 6.2 | List&lt;UUID&gt; | Возвращаемые элементы номенклатуры должны иметь категорию продукта с id из этого списка. |
| parentIds | 6.2 | List&lt;UUID&gt; | Возвращаемые элементы номенклатуры должны иметь родительскую группу с id из этого списка. |

###  

### Что в ответе

Список элементов номенклатуры.

###  
 [+] [Список ProductDto](javascript:void%280%29)
 [-] [Список ProductDto](javascript:void%280%29)
 
```
 
```
 

| Параметр | Версия iiko | Тип, формат | Описание |
| --- | --- | --- | --- |
| id | 6.1 | UUID | UUID элемента номенклатуры. |
| deleted | 6.1 | Boolean | Удален. |
| name | 6.1 | String | Имя. |
| description | 6.1 | String | Описание. |
| num | 6.1 | String | Артикул, используется при печати документов (тех. карт и т.д.). |
| code | 6.1 | String | Код продукта. Используется для быстрого поиска продукта <br>в экране редактирования заказа. |
| parent | 6.1 | UUID | UUID родительской группы продукта. <br>Если продукт принадлежит корневой группе, то parent == null. |
| modifiers | 6.2 | List&lt;ChoiceBindingDto&gt; | Модификаторы. Поле **не учитывает**модификаторы из схемы модификаторов.<br> <br><br>| Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| modifier | UUID | UUID модификатора либо номенклатурной группы, если это групповой модификатор. |<br>| defaultAmount | Integer | Количество по умолчанию. Для группового модификатора всегда равен 0. |<br>| freeOfChargeAmount | Integer | Количество бесплатных модификаторов. |<br>| minimumAmount | Integer | Минимальное количество. |<br>| maximumAmount | Integer | Максимальное количество. |<br>| hideIfDefaultAmount | Boolean | Скрывать, если количество по умолчанию. |<br>| required | Boolean | Является ли модификатор обязательным.<br><br>Начиная с версии iiko 6.2.3 **данный параметр не используется.** |<br>| childModifiersHaveMinMaxRestrictions | Boolean | Ограничения на мин. макс. количество у дочерних модификаторов. |<br>| splittable | Boolean | Признак делимости модификатора. Используется только в схемах модификаторов. |<br>| childModifiers | List&lt;ChoiceBindingDto&gt; | Дочерние модификаторы. | |
| --- | --- | --- | --- |
| taxCategory | 6.1 | UUID | UUID налоговой категории. |
| category | 6.1 | UUID | UUID пользовательской категории. |
| accountingCategory | 6.1 | UUID | UUID бухгалтерской категории. |
| color | 6.2 | RGBColorDto | Цвет фона оформления кнопки в iikoFront.<br> <br><br>| Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| red | Integer | Значение для красного. |<br>| green | Integer | Значение для зеленого. |<br>| blue | Integer | Значение для синего. | |
| --- | --- | --- | --- |
| fontColor | 6.2 | RGBColorDto | Цвет шрифта кнопки в iikoFront. |
| frontImageId | 6.2 | UUID | UUID изображения для отображения в iikoFront. |
| position | 6.2 | Integer | Позиция в меню. |
| mainUnit | 6.1 | UUID | UUID основной единицы измерения продукта. |
| excludedSections | 6.1 | Set&lt;UUID&gt; | Множество UUID отделений ресторана, в которых нельзя продавать данный продукт <br>(поле имеет смысл только для блюд). |
| defaultSalePrice | 6.1 | BigDecimal | Цена, по которой по умолчанию продаётся продукт (если для него нет приказов о меню). |
| placeType | 6.1 | UUID | UUID места приготовления блюда (поле имеет смысл только для блюд). |
| defaultIncludeInMenu | 6.1 | Boolean | Включать ли по умолчанию (если нет приказов о меню) позицию в меню. |
| type | 6.1 | Enum | Тип элемента номенклатуры.<br> <br><br>| Название | Значение |<br>| --- | --- |<br>| GOODS | Товар. |<br>| DISH | Блюдо. |<br>| PREPARED | Заготовка (полуфабрикат). |<br>| SERVICE | Услуга. |<br>| MODIFIER | Модификатор. |<br>| OUTER | Товары поставщиков, не являющиеся товарами систем iiko. |<br>| RATE | Тариф (дочерний элемента для услуги). | |
| --- | --- | --- | --- |
| unitWeight | 6.1 | BigDecimal | Вес одной единицы в килограммах. |
| unitCapacity | 6.1 | BigDecimal | Объем одной единицы в литрах. |
| notInStoreMovement | 6.1 | Boolean | Участвует ли в перемещениях по складу. <br>Услуга с такой настройкой, если указана в ПН, на склад никогда не приходуется ни количеством, ни суммой. <br>Она влияет только на расчет итоговых сумм документа. Относительно стоимости услуг с такой настройкой в ПН <br>рассчитываются суммы дополнительных расходов для других позиций документа. <br>Для услуги с такой настройкой в ПН не рассчитывается сумма дополнительных расходов. |
| containers | 6.2.4 | List&lt;ContainerDto&gt; | Фасовки.<br><br><br>| Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| id | UUID | UUID фасовки. |<br>| num | String | Артикул. |<br>| name | String | Название. |<br>| count | BigDecimal | Количество продукта в единицах измерения продукта. |<br>| minContainerWeight | BigDecimal | Минимальный вес элемента номенклатуры. |<br>| maxContainerWeight | BigDecimal | Максимальный вес элемента номенклатуры. |<br>| containerWeight | BigDecimal | Вес тары. |<br>| fullContainerWeight | BigDecimal | Вес элемента номенклатуры вместе с тарой. |<br>| backwardRecalculation | Boolean | Всегда false |<br>| useInFront | Boolean | Использовать на фронте. |<br>| deleted | Boolean | Удалена или нет. | |
| --- | --- | --- | --- |
| modifierSchemaId | 6.4 | UUID | UUID схемы модификаторов. |
| productScaleId | 6.4 | UUID | UUID шкалы размеров. Если задана схема модификаторов, то шкала размеров берется из нее, а эта не учитывается. |
| coldLossPercent | 7.1.2 | BigDecimal | Потери при холодной обработке (%). |
| hotLossPercent | 7.1.2 | BigDecimal | Потери при горячей обработке обработке (%). |
| allergenGroups | 7.1.5 | BigDecimal | Набор идентификаторов групп аллергенов, которые присутствуют в данном элементе номенклатуры. |
| canSetOpenPrice | 7.4.4 | Boolean | Свободная цена. |
| useBalanceForSell |  | Boolean | Товар продается на вес. |
| 
```
barcodes
```
 | 8.7.1 | 
```
List<ContainerDto>
```
 | Штрихкоды.<br><br><br>| Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| barcode | String | Штрихкод. |<br>| containerId | UUID | UUID фасовки. | |
| --- | --- | --- | --- |

###
 
###  Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/products/list?includeDeleted=false
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```


 [+] [Список ProductGroupDto](javascript:void%280%29)
 [-] [Список ProductGroupDto](javascript:void%280%29)
 | Параметр | Версия iiko | Тип, формат | Описание |
| --- | --- | --- | --- |
| id | 6.1 | UUID | UUID элемента номенклатуры. |
| deleted | 6.1 | Boolean | Удален. |
| name | 6.1 | String | Имя. |
| description | 6.1 | String | Описание. |
| num | 6.1 | String | Артикул, используется при печати документов (тех. карт и т.д.). |
| code | 6.1 | String | Код продукта. Используется для быстрого поиска продукта<br>в экране редактирования заказа. |
| parent | 6.1 | UUID | UUID родительской группы продукта. <br>Если продукт принадлежит корневой группе, то parent == null. |
| modifiers | 6.2 | List&lt;ChoiceBindingDto&gt; | Модификаторы. Поле **не учитывает**модификаторы из схемы модификаторов.<br><br><br>| Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| modifier | UUID | UUID модификатора либо номенклатурной группы, если это групповой модификатор. |<br>| defaultAmount | Integer | Количество по умолчанию. Для группового модификатора всегда равен 0. |<br>| freeOfChargeAmount | Integer | Количество бесплатных модификаторов. |<br>| minimumAmount | Integer | Минимальное количество. |<br>| maximumAmount | Integer | Максимальное количество. |<br>| hideIfDefaultAmount | Boolean | Скрывать, если количество по умолчанию. |<br>| required | Boolean | Является ли модификатор обязательным.<br><br>Начиная с версии iiko 6.2.3 **данный параметр не используется.** |<br>| childModifiersHaveMinMaxRestrictions | Boolean | Ограничения на мин. макс. количество у дочерних модификаторов. |<br>| splittable | Boolean | Признак делимости модификатора. Используется только в схемах модификаторов. |<br>| childModifiers | List&lt;ChoiceBindingDto&gt; | Дочерние модификаторы. | |
| --- | --- | --- | --- |
| taxCategory | 6.1 | UUID | UUID налоговой категории. |
| category | 6.1 | UUID | UUID пользовательской категории. |
| accountingCategory | 6.1 | UUID | UUID бухгалтерской категории. |
| color | 6.2 | RGBColorDto | Цвет фона оформления кнопки в iikoFront.<br><br><br>| Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| red | Integer | Значение для красного. |<br>| green | Integer | Значение для зеленого. |<br>| blue | Integer | Значение для синего. | |
| --- | --- | --- | --- |
| fontColor | 6.2 | RGBColorDto | Цвет шрифта кнопки в iikoFront. |
| frontImageId | 6.2 | UUID | UUID изображения для отображения в iikoFront. |
| position | 6.2 | Integer | Позиция в меню. |
| mainUnit | 6.1 | UUID | UUID основной единицы измерения продукта. |
| excludedSections | 6.1 | Set&lt;UUID&gt; | Множество UUID отделений ресторана, в которых нельзя продавать данный продукт<br>(поле имеет смысл только для блюд). |
| defaultSalePrice | 6.1 | BigDecimal | Цена, по которой по умолчанию продаётся продукт (если для него нет приказов о меню). |
| placeType | 6.1 | UUID | UUID места приготовления блюда (поле имеет смысл только для блюд). |
| defaultIncludeInMenu | 6.1 | Boolean | Включать ли по умолчанию (если нет приказов о меню) позицию в меню. |
| type | 6.1 | Enum | Тип элемента номенклатуры.<br><br><br>| Название | Значение |<br>| --- | --- |<br>| GOODS | Товар. |<br>| DISH | Блюдо. |<br>| PREPARED | Заготовка (полуфабрикат). |<br>| SERVICE | Услуга. |<br>| MODIFIER | Модификатор. |<br>| OUTER | Товары поставщиков, не являющиеся товарами систем iiko. |<br>| RATE | Тариф (дочерний элемента для услуги). | |
| --- | --- | --- | --- |
| unitWeight | 6.1 | BigDecimal | Вес одной единицы в килограммах. |
| unitCapacity | 6.1 | BigDecimal | Объем одной единицы в литрах. |
| notInStoreMovement | 6.1 | Boolean | Участвует ли в перемещениях по складу.<br>Услуга с такой настройкой, если указана в ПН, на склад никогда не приходуется ни количеством, ни суммой.<br>Она влияет только на расчет итоговых сумм документа. Относительно стоимости услуг с такой настройкой в ПН<br>рассчитываются суммы дополнительных расходов для других позиций документа.<br>Для услуги с такой настройкой в ПН не рассчитывается сумма дополнительных расходов. |
| containers | 6.2.4 | List&lt;ContainerDto&gt; | Фасовки.<br><br><br>| Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| id | UUID | UUID фасовки. |<br>| num | String | Артикул. |<br>| name | String | Название. |<br>| count | BigDecimal | Количество продукта в единицах измерения продукта. |<br>| minContainerWeight | BigDecimal | Минимальный вес элемента номенклатуры. |<br>| maxContainerWeight | BigDecimal | Максимальный вес элемента номенклатуры. |<br>| containerWeight | BigDecimal | Вес тары. |<br>| fullContainerWeight | BigDecimal | Вес элемента номенклатуры вместе с тарой. |<br>| backwardRecalculation | Boolean | Всегда false |<br>| useInFront | Boolean | Использовать на фронте. |<br>| deleted | Boolean | Удалена или нет. | |
| --- | --- | --- | --- |
| modifierSchemaId | 6.4 | UUID | UUID схемы модификаторов. |
| productScaleId | 6.4 | UUID | UUID шкалы размеров. Если задана схема модификаторов, то шкала размеров берется из нее, а эта не учитывается. |
| coldLossPercent | 7.1.2 | BigDecimal | Потери при холодной обработке (%). |
| hotLossPercent | 7.1.2 | BigDecimal | Потери при горячей обработке обработке (%). |
| allergenGroups | 7.1.5 | BigDecimal | Оценочная себестоимость. Поле используется для расчёта себестоимости в случае, если по данному товару не было приходов. |
| canSetOpenPrice | 7.4.4 | Boolean | Свободная цена. |
| 
```
barcodes
```
 | 8.7.1 | 
```
List<ContainerDto>
```
 | Штрихкоды.<br><br><br>| Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| barcode | String | Штрихкод. |<br>| containerId | UUID | UUID фасовки. | |
| --- | --- | --- | --- |

## Получение элементов номенклатуры 

Версия iiko: 6.4

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/list |
| --- | --- |

### Тело запроса
 
**Content-Type: application/x-www-form-urlencoded**

| Параметр | Версия iiko | Тип, формат | Описание |
| --- | --- | --- | --- |
| includeDeleted | 6.4 | Boolean | Включать ли в результат удаленные элементы. По умолчанию false. |
| revisionFrom | 6.4 | -1, число | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |
| ids | 6.4 | List&lt;UUID&gt; | Возвращаемые элементы номенклатуры должны иметь id из этого списка. |
| nums | 6.4 | List&lt;String&gt; | Возвращаемые элементы номенклатуры должны иметь артикул из этого списка. |
| codes | 6.4 | List&lt;String&gt; | Возвращаемые элементы номенклатуры должны иметь код из этого списка. |
| types | 6.4 | List&lt;ProductType&gt; | Возвращаемые элементы номенклатуры должны иметь тип из этого списка. |
| categoryIds | 6.4 | List&lt;UUID&gt; | Возвращаемые элементы номенклатуры должны иметь категорию продукта с id из этого списка. |
| parentIds | 6.4 | List&lt;UUID&gt; |  |

### Что в ответе

Список элементов номенклатуры.

## Импорт элемента номенклатуры

Версия iiko: 6.1

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/save |
| --- | --- |

### Параметры запроса

| Название | Тип | Описание |
| --- | --- | --- |
| generateNomenclatureCode | Boolean | Надо ли генерировать артикул элемента номенклатуры.<br> <br> Необязательный. По умолчанию true |
| generateFastCode | Boolean | Надо ли генерировать код быстрого поиска элемента номенклатуры.<br> <br> Необязательный. По умолчанию true. |

 [+] [Тело запроса](javascript:void%280%29)
 [-] [Тело запроса](javascript:void%280%29)
 | Поле | Версия iiko | Тип данных | Обязательное | Значение |
| --- | --- | --- | --- | --- |
| name | 6.1 | String | да | Имя. |
| description | 6.1 | String | нет | Описание. |
| num | 6.2.4 | String | да, если generateNomenclatureCode == false | Артикул, используется при печати документов (тех. карт и т.д.). Обязателен, если generateNomenclatureCode == false. |
| code | 6.2.4 | String | нет | Код продукта. Используется для быстрого поиска продукта на экране редактирования заказа. Если generateFastCode == false и поле не задано, то создастся пустым. |
| parent | 6.1 | UUID | нет | UUID родительской группы продукта. <br>Если продукт принадлежит корневой группе, то parent == null. |
| modifiers | 6.2 | List&lt;ChoiceBindingDto&gt; | нет | Модификаторы.<br><br><br>| Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| modifier | UUID | UUID модификатора либо номенклатурной группы, если это групповой модификатор. |<br>| defaultAmount | Integer | Количество по умолчанию. Должно лежать в пределах мин. и макс. значений.<br>У группового модификатора равно сумме значений по умолчанию дочерних элементов. |<br>| freeOfChargeAmount | Integer | Количество бесплатных модификаторов. Не более макс. количества. |<br>| minimumAmount | Integer | Минимальное количество. Если модификатор обязательный, то минимальное количество<br>должно быть больше 0. |<br>| maximumAmount | Integer | Максимальное количество. |<br>| hideIfDefaultAmount | Integer | Скрывать, если количество по умолчанию. |<br>| required | Boolean | Является ли модификатор обязательным. |<br>| childModifiersHaveMinMaxRestrictions | Boolean | Ограничения на мин. макс. количество у дочерних модификаторов. Значение флага <br>в дочерних и одиночных модификаторов должно быть **false**. |<br>| splittable | Boolean | Признак делимости модификатора. Используется только в схемах модификаторов. |<br>| childModifiers | List&lt;ChoiceBindingDto&gt; | Дочерние модификаторы. Если у группового модификатора выключены ограничения на мин.<br>макс. количество у дочерних модификаторов (**childModifiersHaveMinMaxRestrictions = false**), то<br>значение**freeOfChargeAmount**у дочерних модификаторов должны быть такими же как у группового,**required**должен быть false, а мин. макс. кол-во должны быть равны нулю**(minimumAmount = 0,** **maximumAmount = 0**). | |
| --- | --- | --- | --- | --- |
| taxCategory | 6.1 | UUID | нет | UUID налоговой категории. |
| category | 6.1 | UUID | нет | UUID пользовательской категории. |
| accountingCategory | 6.2.3 | UUID | нет, по умолчанию "товар" | UUID бухгалтерской категории. |
| color | 6.2 | RGBColorDto | нет | Цвет фона оформления кнопки в iikoFront. |
| fontColor | 6.2 | RGBColorDto | нет | Цвет шрифта кнопки в iikoFront. |
| frontImageId | 6.2 | UUID | нет | UUID изображения для отображения в iikoFront. API изображений. |
| position | 6.2 | Integer | нет | Позиция в меню. |
| mainUnit | 6.1 | UUID | да | UUID основной единицы измерения продукта. |
| excludedSections | 6.1 | Set&lt;UUID&gt; | нет | Множество UUID отделений ресторана, в которых нельзя продавать данный продукт<br>(поле имеет смысл только для блюд). |
| defaultSalePrice | 6.1 | BigDecimal | нет, по умолчанию 0 | Цена, по которой по умолчанию продаётся продукт (если для него нет приказов о меню). По умолчанию 0. |
| placeType | 6.1 | UUID | обязательное, если defaultIncludeInMenu == true | UUID места приготовления блюда (поле имеет смысл только для блюд). |
| defaultIncludeInMenu | 6.1 | Boolean | нет, по умолчанию false | Включать ли по умолчанию (если нет приказов о меню) позицию в меню.[1] |
| type | 6.1 | Enum | да | Тип элемента номенклатуры.<br><br><br>| Название | Значение |<br>| --- | --- |<br>| GOODS | Товар. |<br>| DISH | Блюдо. |<br>| PREPARED | Заготовка (полуфабрикат). |<br>| MODIFIER | Модификатор. |<br>| SERVICE | Услуга. |<br>| RATE | Тариф (дочерний элемента для услуги).[2] | |
| --- | --- | --- | --- | --- |
| unitWeight | 6.2.4 | BigDecimal | нет, по умолчанию 1 | Вес одной единицы в килограммах. |
| unitCapacity | 6.1 | BigDecimal | нет, по умолчанию 0 | Объем одной единицы в литрах. По умолчанию 0. |
| notInStoreMovement | 6.1 | Boolean | нет, по умолчанию false | Участвует ли в перемещениях по складу.<br>Услуга с такой настройкой, если указана в ПН, на склад никогда не приходуется ни количеством, ни суммой.<br>Она влияет только на расчет итоговых сумм документа. Относительно стоимости услуг с такой настройкой в ПН<br>рассчитываются суммы дополнительных расходов для других позиций документа.<br>Для услуги с такой настройкой в ПН не рассчитывается сумма дополнительных расходов. |
| containers | 6.2.4 | List&lt;ContainerDto&gt; | нет | Фасовки.<br><br><br>| Параметр | Тип | Обязательный | Описание |<br>| --- | --- | --- | --- |<br>| name | String | да | Название. |<br>| num | String | да | Артикул. |<br>| count | Integer | да | Количество продукта в единицах измерения продукта. |<br>| minContainerWeight | BigDecimal | нет, по умолчанию 0 | Минимальный вес элемента номенклатуры. |<br>| containerWeight | BigDecimal | да | Вес тары. |<br>| fullContainerWeight | BigDecimal | да | Вес элемента номенклатуры вместе с тарой. |<br>| backwardRecalculation | Boolean | нет | Параметр не используется, значение будет проигнорировано |<br>| useInFront | Boolean | нет, по умолчанию true | Использовать на фронте. | |
| --- | --- | --- | --- | --- |
| coldLossPercent | 7.1.2 | BigDecimal | нет, по умолчанию 0 | Потери при холодной обработке (%). |
| hotLossPercent | 7.1.2 | BigDecimal | нет, по умолчанию 0 | Потери при горячей обработке обработке (%). |
| allergenGroups | 7.1.2 | Set&lt;UUID&gt; | нет | Набор идентификаторов групп аллергенов, которые присутствуют в данном элементе номенклатуры. |
| estimatedPurchasePrice | 7.1.5 | BigDecimal | нет, по умолчанию 0 |  |

[1]. При **defaultIncludeInMenu=true** обязательно указывается **placeType**, независимо от типа элемента номенклатуры(блюдо, товар и т.д.)
При**defaultIncludeInMenu=false** поле **excludedSections** должно быть **null**.
[2]. Менять тип номенклатуры можно только на тип той же категории, что и исходный. Категории разбиты по цветам.
 
```
 
```

 [+] [Пример тела запроса](javascript:void%280%29)
 [-] [Пример тела запроса](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 
### **Что в ответе**

Содержит результат импорта (Json структура), который состоит из результата валидации импортируемого элемента и самого элемента. Результат валидации состоит из ошибок. Ошибка состоит из кода ошибки и текста ошибки.

**Результат**

| Поле | Тип данных | Значение |
| --- | --- | --- |
| result | Enum: <br>"SUCCESS", <br>"ERROR" | Результата операции. |
| errors | List&lt;ErrorDto&gt; | Список ошибок, не позволивших сделать успешный импорт документа. |
| response | ProductDto | В случае успешного импорта - сохраненный объект, <br>в противном случае импортируемый объект. |

### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/products/save
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE4%%%%CH%PRE5%%
```

 [+] [Пример  результата вызова API: entities/products/save](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/save](javascript:void%280%29)
 
```
 %%CH%PRE6%%%%CH%PRE7%%
```

 [+] [Пример  результата вызова API: entities/products/save](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/save](javascript:void%280%29)
 
```
 %%CH%PRE8%%%%CH%PRE9%%
```

 
##  Редактирование элемента номенклатуры

Версия iiko: 6.1

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/update |
| --- | --- |

### Параметры запроса

| Название | Тип, формат | Описание |
| --- | --- | --- |
| overrideFastCode | Boolean | Перегенерировать ли код быстрого поиска элемента номенклатуры. <br>По умолчанию false. |
| overrideNomenclatureCode | Boolean | Перегенерировать ли артикул элемента номенклатуры. <br>По умолчанию false. |

 ### Тело запроса
 Аналогично импорту только с id редактируемого элемента

| Поле | Тип данных | Значение |
| --- | --- | --- |
| id | UUID | UUID редактируемого элемента номенклатуры |
 [+] [Тело запроса](javascript:void%280%29)
 [-] [Тело запроса](javascript:void%280%29)
 
```
 %%CH%PRE10%%%%CH%PRE11%%
```

 
### Что в ответе

Содержит Json структуру результата изменения, которая состоит из результата валидации измененного элемента 
и самого элемента. Результат валидации состоит из ошибок. Ошибка состоит из кода ошибки и текста ошибки.

#### 

### Примеры запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/products/update?overrideFastCode=false&overrideNomenclatureCode=false
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE12%%%%CH%PRE13%%
```

 [+] [Пример  результата вызова API: entities/products/update](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/update](javascript:void%280%29)
 
```
 %%CH%PRE14%%%%CH%PRE15%%
```

 [+] [Пример  результата вызова API: entities/products/update](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/update](javascript:void%280%29)
 
```
 %%CH%PRE16%%%%CH%PRE17%%
```


##  Удаление элементов номенклатуры
 
Версия iiko: 6.1

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/delete |
| --- | --- |

### Тело запроса

| Поле | Тип данных | Значение |
| --- | --- | --- |
| items | List&lt;IdCodetDto&gt; | Список UUID элементов, которые нужно удалить<br><br><br>| Поле | Тип данных | Значение |<br>| --- | --- | --- |<br>| id | UUID | UUID элемента | |
| --- | --- | --- |

### 


Код

```
{ 
   "items":[ 
      { 
         "id":"fcdf4324-4a2f-f250-0162-d3887cf1005d"
      }
   ]
}
```

Код

```
{ 
   "items":[ 
      { 
         "id":"fcdf4324-4a2f-f250-0162-d3887cf1005d"
      }
   ]
}
```


### 

### Что в ответе
Содержит Json структуру результата удаления.

### Примеры запроса и результат

#### Запрос

https://localhost:8080/resto/api/v2/entities/products/delete

#### Результат


```xml
{ 
   "items":[ 
      { 
         "id":"fcdf4324-4a2f-f250-0162-d3887cf1005d"
      }
   ]
}
```

```xml
{ 
   "items":[ 
      { 
         "id":"fcdf4324-4a2f-f250-0162-d3887cf1005d"
      }
   ]
}
```

 [+] [Пример  результата вызова API: entities/products/delete](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/delete](javascript:void%280%29)
 
```
 %%CH%PRE22%%%%CH%PRE23%%
```

 [+] [Пример  результата вызова API: entities/products/delete](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/delete](javascript:void%280%29)
 
```
 
  Could not delete already deleted products: [fcdf4324-4a2f-f250-0162-d3887cf1005d]​.

```

 
##  Восстановление элементов номенклатуры

Версия iiko: 6.1

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/v2/entities/products/restore |
| --- | --- |

### **Параметры запроса**

| Параметр | Версия | Тип, формат | Описание |
| --- | --- | --- | --- |
| overrideNomenclatureCode | 6.4 | Boolean | Если у восстанавливаемого продукта артикул совпадает с одним из текущих и параметр указан равным true, то у восстанавливаемого продукта будет сгенерирован новый артикул.<br><br>Необязательный. По умолчанию false. |

### **Тело запроса**

| **Поле** | **Тип данных** | **Значение** |
| items | List&lt;IdCodetDto&gt; | Список UUID элементов, которые нужно восстановить<br>| Поле | Тип данных | Описание |<br>| --- | --- | --- |<br>| id | UUID | UUID элемента. | |
| --- | --- | --- |

### Что в ответе

Содержит Json структуру результата восстановления.

### Пример запроса и результата

#### Запрос

https://localhost:8080/resto/api/v2/entities/products/restore

#### Результат


Код

```
{ 
   "items":[ 
      { 
         "id":"fcdf4324-4a2f-f250-0162-d3887cf1005d"
      }
   ]
}
```

Код

```
{ 
   "items":[ 
      { 
         "id":"fcdf4324-4a2f-f250-0162-d3887cf1005d"
      }
   ]
}
```

 [+] [Пример  результата вызова API: entities/products/restore](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/restore](javascript:void%280%29)
 
```
 %%CH%PRE26%%%%CH%PRE27%%
```

 [+] [Пример  результата вызова API: entities/products/restore](javascript:void%280%29)
 [-] [Пример  результата вызова API: entities/products/restore](javascript:void%280%29)
 
```
 Could not restore not deleted products: [fcdf4324-4a2f-f250-0162-d3887cf1005d].
```
