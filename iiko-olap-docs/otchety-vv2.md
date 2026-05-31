* [Балансы по счетам, контрагентам и подразделениям](/articles/api-documentations/otchety-vv2/a/h2_1559205636)
* [Параметры запроса](/articles/api-documentations/otchety-vv2/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/otchety-vv2/a/h3_1491674086)
* [Пример запроса и результата](/articles/api-documentations/otchety-vv2/a/h3_1561844723)
* [Остатки на складах](/articles/api-documentations/otchety-vv2/a/h2_2138999405)
* [Параметры запроса](/articles/api-documentations/otchety-vv2/a/h3__397291684)
* [Что в ответе](/articles/api-documentations/otchety-vv2/a/h3_501454233)
* [Пример запроса и результата](/articles/api-documentations/otchety-vv2/a/h3_1387997121)
* [Получение обновлений состояния на 3 регистре](/articles/api-documentations/otchety-vv2/a/APIОтчетпобалансуна3регистреЕГАИС%28акцизныемарки%29-Получениеобновленийсостоянияна3регистре)
* [Параметры запроса](/articles/api-documentations/otchety-vv2/a/APIОтчетпобалансуна3регистреЕГАИС%28акцизныемарки%29-Параметры)
* [Пример запроса и результат](/articles/api-documentations/otchety-vv2/a/h3__1082861155)

## Балансы по счетам, контрагентам и подразделениям

Версия iiko: 5.2

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/reports/balance/counteragents |
| --- | --- |

### Параметры запроса

| Параметр | Описание |
| --- | --- |
| **timestamp** | учетная-дата время отчета в формате yyyy-MM-dd'T'HH:mm:ss (обязательный) |
| **account** | id счета для фильтрации (необязательный, можно указать несколько) |
| **counteragent** | id контрагента для фильтрации (необязательный, можно указать несколько) |
| **department** | id подразделения для фильтрации (необязательный, можно указать несколько) |

### **Что в ответе**

Возвращает денежные балансы по указанным счетам, контрагентам и подразделениям на заданную учетную дату-время.

См. ниже пример результата.

### **Пример запроса и результата**

**Запрос**

https://localhost:9080/resto/api/v2/reports/balance/counteragents?key=88e98be8-89c4-766b-a319-dc6d1f3b8cec&timestamp=2016-10-19T23:10:10
[+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%
```


## Остатки на складах

Версия iiko: 5.2

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/reports/balance/stores |
| --- | --- |

### Параметры запроса

| Параметр | Описание |
| --- | --- |
| **timestamp** | учетная-дата время отчета в формате yyyy-MM-dd'T'HH:mm:ss (обязательный) |
| **department** | id подразделения для фильтрации (необязательный, можно указать несколько) |
| **store** | id склада для фильтрации (необязательный, можно указать несколько) |
| **product** | id элемента номенклатуры для фильтрации (необязательный, можно указать несколько) |

### **Что в ответе**

Возвращает количественные (amount) и денежные (sum) остатки товаров (product) на складах (store) на заданную учетную дату-время.

См. ниже пример результата.

### **Пример запроса и результата**

**Запрос**

https://localhost:9080/resto/api/v2/reports/balance/stores?key=88e98be8-89c4-766b-a319-dc6d1f3b8cec&timestamp=2016-10-18T23:10:10

**Результат**

**
Код

```
[
    {
        "store": "657ded9f-a1a3-416c-91a4-5a2fc78e8a36",
        "product": "f464e4d4-cf9c-49a2-9e18-1227b41a3801",
        "amount": 123,
        "sum": 64083
    },
    {
        "store": "1239d270-1bbe-f64f-b7ea-5f00518ef508",
        "product": "c6d6c2f2-7e48-4ac9-84ca-1f566c3a941e",
        "amount": 29.45,
        "sum": 1159.3
    },
    {
        "store": "1239d270-1bbe-f64f-b7ea-5f00518ef508",
        "product": "f464e4d4-cf9c-49a2-9e18-1227b41a3801",
        "amount": 15,
        "sum": 1221
    }
]
```
**

# Отчет по балансу на 3 регистре ЕГАИС (акцизные марки)

## Получение обновлений состояния на 3 регистре

Версия iiko: 7.4

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/v2/reports/egais/marks/list |
| --- | --- |

### Параметры запроса

| **Название** | **Тип данных** | **Обязательный** | **Описание** |
| --- | --- | --- | --- |
| **fsRarId** | List&lt;String&gt; | Нет, по умолчанию<br><br>возвращаются данные для всех организаций. | Список РАР-идентификаторов организаций, баланс которых запрашивается |
| **revisionFrom** | int | Нет, по умолчанию -1 | Номер ревизии, начиная с которой необходимо отфильтровать сущности.<br><br>Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom. |

### **Пример запроса и результат**

**Запрос**

https://localhost:8080/resto/api/v2/reports/egais/marks/list?fsRarId=030000455388&fsRarId=030000455399&revisionFrom=100
 [+] [Пример результата](javascript:void%280%29)
 [-] [Пример результата](javascript:void%280%29)
 
```
 %%CH%PRE2%%
```

 
**Описание полей**

| **Поле** | **Тип данных** | **Описание** |
| **revision** | int | Ревизия, по которую (включительно) выданы данные |
| **fullUpdate** | Boolean | true - пакет является "полным обновлением", то есть, клиент должен удалить все имеющие данные, не перечисленные явно.<br><br>false - пакет является "частичным обновлением", клиент должен заменить закешированные записи с теми же ключами. |
| **marksByBRegId** | Map&lt;String, EgaisBRegDto&gt; | Название вложенного поля - BRegId - Идентификатор Справки Б (Справки 2)<br><br>Значение вложенного поля:<br> <br><br> <br><br>| Поле | Тип данных | Описание |<br>| --- | --- | --- |<br>| **dateTo** | Дата в формате yyyy-MM-dd'T'HH:mm:ss.SSS | Дата-время актуальности состояния:<br><ul><li><span style="font-size: 10pt;">MAX_DATE, если марка еще не списана</span></li><li><p><span style="font-size: 10pt;">Дата-время списания + MAX_MARK_KEEP_DAYS дней, если списана документом, находящимся в нередактируемом статусе</span></p></li><li><span style="font-size: 10pt;">Дата-время удаления последнего известного EgaisMarkTableItem (информация о движении акцизной марки) (для отсутствующих марок).</span></li></ul> | |
| --- | --- | --- |
| **marksWrittenOff** | Map&lt;String, EgasMarkStateDto&gt; | Множество акцизных марок, списанных с баланса организации.<br><br>Название вложенного поля - полный текст акцизной марки.<br><br>Значения вложенного поля:<br> <br><br> <br><br>| Параметр | Тип, формат | Описание |<br>| --- | --- | --- |<br>| **dateTo** | Дата в формате yyyy-MM-dd'T'HH:mm:ss.SSS | Дата-время актуальности состояния:<br><ul><li><span style="font-size: 10pt;">MAX_DATE, если марка еще не списана</span></li><li><p><span style="font-size: 10pt;">Дата-время списания + MAX_MARK_KEEP_DAYS дней, если списана документом, находящимся в нередактируемом статусе</span></p></li><li><span style="font-size: 10pt;">Дата-время удаления последнего известного EgaisMarkTableItem (информация о движении акцизной марки) (для отсутствующих марок).</span></li></ul> | |
| --- | --- | --- |