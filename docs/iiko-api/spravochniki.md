* [Получение справочной информации](/articles/api-documentations/spravochniki/a/h2_514833769)
* [Параметры запроса](/articles/api-documentations/spravochniki/a/v2.APIсправочников-Параметры)
* [Что в ответе](/articles/api-documentations/spravochniki/a/h3_501454233)
* [Дополнительные поля](/articles/api-documentations/spravochniki/a/v2.APIсправочников-Дополнительныеполя)
* [Пример запроса и результата](/articles/api-documentations/spravochniki/a/h3_1561844723)
* [Получение идентификаторов сущностей](/articles/api-documentations/spravochniki/a/h2_695212168)
* [Параметры запроса](/articles/api-documentations/spravochniki/a/v2.APIсправочников-Параметры.1)
* [Что в ответе](/articles/api-documentations/spravochniki/a/h3__101450509)
* [Результат](/articles/api-documentations/spravochniki/a/v2.APIсправочников-Результат.1)
* [Пример запроса и результат](/articles/api-documentations/spravochniki/a/h3__2087356861)

## Получение справочной информации

Версия iiko: 5.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **** https://host:port/resto/api/v2/entities/list |
| --- | --- |

### 

### **Параметры запроса**
| Название | Значение | Описание |
| --- | --- | --- |
| **rootType** | Account | | Название | Версия iiko | Описание |<br>| --- | --- | --- |<br>| Account | 5.0 | Счет (в том числе склады) |<br>| AccountingCategory | 5.0 | Бухгалтерская категория номенклатуры |<br>| AlcoholClass | 5.0 | Класс алкогольной продукции |<br>| AllergenGroup | 7.1.2 | Группа аллергенов |<br>| AttendanceType | 6.4 | Тип явки сотрудника |<br>| Conception | 7.8.1 | Концепция |<br>| CookingPlaceType | 7.0.2 | Тип места приготовления |<br>| DiscountType | 5.0 | Тип скидки |<br>| MeasureUnit | 5.0 | Единица измерения |<br>| OrderType | 6.4 | Тип заказа |<br>| PaymentType | 5.0 | Тип оплаты |<br>| ProductCategory | 5.0 | Пользовательская категория номенклатуры |<br>| ProductScale | 6.4 | Шкала размеров |<br>| ProductSize | 6.4 | Размер продукта |<br>| ScheduleType | 6.4 | Тип смены |<br>| TaxCategory | 6.2.2 | Налоговая категория | |
| --- | --- | --- |
| **includeDeleted** | true, false | Включать ли удаленные элементы справочника. По умолчанию включать. |
| ~~**format**~~ | SHORT | Формат вывода. По умолчанию SHORT:<br><ul style="margin: 10px 0px 0px; padding-left: 22px;"><li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">id</span></li><li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">rootType (переданный тип)</span></li><li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">deleted</span></li><li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">code (код, артикул, номер; присутствует не во всех типах справочников)</span></li><li><span style="font-family: &quot;Segoe UI&quot;, Frutiger, &quot;Frutiger Linotype&quot;, &quot;Dejavu Sans&quot;, &quot;Helvetica Neue&quot;, Arial, sans-serif;">name (название)</span></li></ul><br>**Начиная с версии iiko 6.2.2 данный параметр не используется.**<br><br>**Формат вывода остался прежним, но в зависимости от rootType могут добавляться новые поля.** |
| **revisionFrom** | Число, номер ревизии | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |
### Что в ответе

Json структура с данными справочников.

Возвращает общую справочную информацию без привязки к подразделениям, срокам действия.

Результат вызова может содержать записи (например, типы оплат), запрещенные к применению в каких-то подразделениях.

Данный метод следует использовать только для получения названий объектов в целях отображения отчетов.

### 

#### Результат

Основной формат вывода:
| Поле | Описание |
| --- | --- |
| **id** | UUID объекта |
| **rootType** | "Основной" тип объекта (тот, что передан как аргумент метода list) |
| **deleted** | false — объект действующий, true — объект помечен как удаленный |
| **code** | Код объекта (в том числе артикул, табельный номер, и т.п.). Является строкой: "1234", "3.04". Может быть null. |
| **name** | Название объекта.<br>Для локализуемых предустановленных (например, стандартных счетов Account) — название на языке запроса. |

## Дополнительные поля

| Тип объекта | Дополнительное поле | Описание |
| --- | --- | --- |
| OrderType | orderServiceType | Режим обслуживания<br>| COMMON | Обычный заказ |<br>| --- | --- |<br>| DELIVERY\_BY\_COURIER | Доставка курьером |<br>| DELIVERY\_PICKUP | Доставка самовывоз | |
| defaultForServiceType | У каждого из режимов обслуживания может быть выбран один тип заказа по умолчанию. |
| ProductSize | shortName | Короткое название для размера |
| TaxCategory | vatPercent | Значение ставки НДС |

### **Пример запроса и результата**

**Запрос**

https://localhost:8080/resto/api/v2/entities/list?rootType=DiscountType&rootType=PaymentType&includeDeleted=false

 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
**Запрос**

https://localhost:8080/resto/api/v2/entities/list?rootType=TaxCategory
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%



```


## Получение идентификаторов сущностей
Версия iiko: 9.1

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/entities/{entityType}/ids |
| --- | --- |

### Параметры запроса
| Название | Значение | Описание |
| --- | --- | --- |
| **entityType** | Например "Account" | Название справочника |
| **includeDeleted** | true, false | Включать ли удаленные элементы справочника. По умолчанию включать. |
| **revisionFrom** | Число, номер ревизии | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (не ревизионный запрос) revisionFrom = -1 |
### Что в ответе

Список UUID идентификаторов сущностей заданного типа.

Возвращает список уникальных идентификаторов (UUID) сущностей указанного типа.

Метод используется для получения идентификаторов сущностей, которые могут быть обработаны в дальнейших операциях.

### Результат

Основной формат вывода:
| Поле | Описание |
| --- | --- |
| **id** | UUID объекта |
### Пример запроса и результат

**Запрос**
 
https://localhost:8080/resto/api/v2/entities/Account/ids?entityType=Account&includeDeleted=false&revisionFrom=10
[+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE4%%%%CH%PRE5%%

```
 
#### Запрос

#### https://localhost:8080/resto/api/v2/entities/Account/ids?entityType=Account

[+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE6%%%%CH%PRE7%%
```


###
