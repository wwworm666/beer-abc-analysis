* [Список поставщиков](/articles/api-documentations/rabota-s-postavschikami/a/v1.APIпоставщиков-Списокпоставщиков)
* [Параметры запроса](/articles/api-documentations/rabota-s-postavschikami/a/h3_1827755295)
* [Что в ответе](/articles/api-documentations/rabota-s-postavschikami/a/h3_501454233)
* [Пример запроса](/articles/api-documentations/rabota-s-postavschikami/a/h3_1387997121)
* [Поиск поставщика](/articles/api-documentations/rabota-s-postavschikami/a/v1.APIпоставщиков-Поискпоставщика)
* [Параметры запроса](/articles/api-documentations/rabota-s-postavschikami/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/rabota-s-postavschikami/a/h3__593990151)
* [Пример запроса](/articles/api-documentations/rabota-s-postavschikami/a/h3__1197208648)
* [Прайс-лист поставщика](/articles/api-documentations/rabota-s-postavschikami/a/h2_1652034885)
* [Параметры запроса](/articles/api-documentations/rabota-s-postavschikami/a/h3_1492020182)
* [Что в ответе](/articles/api-documentations/rabota-s-postavschikami/a/h3_298857834)
* [Пример запроса](/articles/api-documentations/rabota-s-postavschikami/a/h3__1508308707)

## Список поставщиков

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/suppliers |
| --- | --- |

### Параметры запроса
| Название | Значение | Версия | Описание |
| --- | --- | --- | --- |
| revisionFrom | число, номер ревизии | с 6.4 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |
### Что в ответе

Список всех поставщиков. Структура*employees*

### **Пример запроса**

https://localhost:8080/resto/api/suppliers?key=52cf1990-5a4c-b086-538d-e06607c17d16

## Поиск поставщика

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/suppliers/search |
| --- | --- |

### Параметры запроса

Поиск по id поставщика не производится.

Возможно произвести поиск по следующим полям:

### 
| Название | Описание |
| --- | --- |
| name | поле Имя в системе |
| code | поле Таб.номер/Код |
| phone | поле Телефон |
| cellPhone | поле Мобильный телефон |
| firstName | поле Имя |
| middleName | поле Отчество |
| lastName | поле Фамилия |
| email | поле e-mail |
| cardNumber | поле Номер карты (вкладка Дополнительные сведения) |
| taxpayerIdNumber | поле ИНН (вкладка Юр.лицо) |
### Что в ответе
Список найденных поставщиков. Структура employees (см. XSD Сотрудники)
### **Пример запроса**

https://localhost:8080/resto/api/suppliers/search?key=9a02e96c-273a-ef74-9977-0a0005630317&name=ppl&code=3

## Прайс-лист поставщика

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/suppliers/{code}/pricelist |
| --- | --- |

### Параметры запроса
| Название | Значение | Описание |
| --- | --- | --- |
| date | DD.MM.YYYY | Дата начала действия прайс-листа, необязательный. Если параметр не указан, возвращается последний прайс-лист. |
### Что в ответе
Структура *supplierPriceListItemDto* (см. XSD Прайс-лист)
### **Пример запроса**

https://localhost:8080/resto/api/suppliers/3/pricelist?key=695173d1-a241-7261-d191-6d381a1cc851
 [+] [XSD Поставщик](javascript:void%280%29)
 [-] [XSD Поставщик](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 [+] [XSD Прайс-лист](javascript:void%280%29)
 [-] [XSD Прайс-лист](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```
