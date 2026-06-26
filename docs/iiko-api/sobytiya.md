* [Доступ](/articles/api-documentations/sobytiya/a/v1.APIсобытий-Доступ)
* [Список событий](/articles/api-documentations/sobytiya/a/v1.APIсобытий-Списоксобытий)
* [Параметры запроса](/articles/api-documentations/sobytiya/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/sobytiya/a/h3__232688264)
* [Список событий по фильтру событий и номеру заказа](/articles/api-documentations/sobytiya/a/v1.APIсобытий-Списоксобытийпофильтрусобытийиномерузаказа)
* [Тело запроса](/articles/api-documentations/sobytiya/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/sobytiya/a/h3_501454233)
* [Сохранение событий](/articles/api-documentations/sobytiya/a/v1.APIсобытий-Сохранениесобытий)
* [Тело запроса](/articles/api-documentations/sobytiya/a/h3_970802681)
* [Что в ответе](/articles/api-documentations/sobytiya/a/h3_1751621379)
* [Описание](/articles/api-documentations/sobytiya/a/h3__1634860086)
* [Дерево событий](/articles/api-documentations/sobytiya/a/v1.APIсобытий-Деревособытий)
* [Что в ответе](/articles/api-documentations/sobytiya/a/h3__1587991113)
* [Дерево событий по фильтру](/articles/api-documentations/sobytiya/a/v1.APIсобытий-Деревособытийпофильтру)
* [Тело запроса](/articles/api-documentations/sobytiya/a/h3_1759262507)
* [Что в ответе](/articles/api-documentations/sobytiya/a/h3__927917530)
* [Пример запроса](/articles/api-documentations/sobytiya/a/h3_792319459)
* [Информация о кассовых сменах](/articles/api-documentations/sobytiya/a/v1.APIсобытий-Информацияокассовыхсменах)
* [Параметры запроса](/articles/api-documentations/sobytiya/a/h3__801752443)
* [Что в ответе](/articles/api-documentations/sobytiya/a/h3__1002840955)

## Доступ

Чтобы пользоваться API событий:

* В лицензии должен присутствовать модуль 2200 (прочие названия: API\_EVENTS(2200), 'iikoAPI (ApiEvents)').
* У пользователя, под чьим именем осуществляется вход, должно быть право B\_VTJ "Просматривать журнал событий".

## Список событий

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**events** |
| --- | --- |

### Параметры запроса
| Название | Значение | Описание |
| --- | --- | --- |
| from\_time | *yyyy-MM-ddTHH:mm:ss.SSS* | Время с которого запрашиваются события, в формате ISO: *yyyy-MM-ddTHH:mm:ss.SSS*, по умолчанию – начало текущих суток |
| --- | --- | --- |
| to\_time | *yyyy-MM-ddTHH:mm:ss.SSS* | Время по которое (не включительно) запрашиваются события в формате ISO: *yyyy-MM-ddTHH:mm:ss.SSS*,, по умолчанию граница не установлена |
| --- | --- | --- |
| from\_rev | Число | Ревизия, с которой запрашиваются события, число. Каждый ответ содержит тэг revision, значение которого соответствует ревизии, по которую включительно отданы события; при новых запросах следует использовать revision + 1 (revision из предыдущего ответа) для получения только новых событий. В штатном режиме одно и тоже событие повторно с разными ревизиями не приходит, однако такой гарантии не даётся. ID (UUID) события уникален, может использоваться в качестве ключа. |
| --- | --- | --- |
### Что в ответе

Список событий в формате *eventsList* (см. XSD Список событий).

Поле *&lt;type&gt;* использует значение поля *&lt;id&gt;* структуры*groupsList*.

### Примеры запроса

https://localhost:8080/resto/api/events?key=39c4c88f-4758-64e3-3b4c-ad6f589c0dc2

https://localhost:8080/resto/api/events?key=46dcaad5-b139-b976-88a2-1cf9b567195c&from\_time=2014-06-16T00:00:00.000&to\_time=2014-06-18T23:59:59.999

https://localhost:8181/resto/api/events?key=3192935b-26f7-4d61-b11d-58feb1a7d69b&from\_rev=10016007

## Список событий по фильтру событий и номеру заказа

Версия iiko: 5.0

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/**events** |
| --- | --- |

### Тело запроса

Список id событий, по которым производится фильтрация (application/xml).

### 


```xml
<eventsRequestData>
<events>
<event>orderCancelPrecheque</event>
<event>orderPaid</event>
</events>
<orderNums>
<orderNum>175658</orderNum>
</orderNums>
</eventsRequestData>
```

```xml
<eventsRequestData>
<events>
<event>orderCancelPrecheque</event>
<event>orderPaid</event>
</events>
<orderNums>
<orderNum>175658</orderNum>
</orderNums>
</eventsRequestData>
```


### Что в ответе

Список событий в формате *eventsList* (см. XSD Список событий).

Поле *&lt;type&gt;* использует значение поля *&lt;id&gt;* структуры*groupsList*.

## 

## Сохранение событий

Версия iiko: 8.0.3

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/events/add |
| --- | --- |

### Тело запроса

Список событий в формате *eventsList*.

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<eventsList>
    <event>
        <date>2021-12-31T19:24:29.033+03:00</date>
        <type>banana</type>
        <departmentId>2</departmentId>
        <attribute>
            <name>userName</name>
            <value>Администратор</value>
            <type>java.lang.String</type>
        </attribute>
        <attribute>
            <name>user</name>
            <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value>
            <type>User</type>
        </attribute>
        <attribute>
            <name>success</name>
            <value>1.000000000</value>
            <type>java.lang.Boolean</type>
        </attribute>
    </event>
    <event>
        <date>2021-12-31T19:25:29.033+03:00</date>
        <type>banana</type>
        <departmentId>2</departmentId>
        <attribute>
            <name>userName</name>
            <value>Администратор</value>
            <type>java.lang.String</type>
        </attribute>
        <attribute>
            <name>user</name>
            <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value>
            <type>User</type>
        </attribute>
        <attribute>
            <name>success</name>
            <value>1.000000000</value>
            <type>java.lang.Boolean</type>
        </attribute>
    </event>
</eventsList>
```

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<eventsList>
    <event>
        <date>2021-12-31T19:24:29.033+03:00</date>
        <type>banana</type>
        <departmentId>2</departmentId>
        <attribute>
            <name>userName</name>
            <value>Администратор</value>
            <type>java.lang.String</type>
        </attribute>
        <attribute>
            <name>user</name>
            <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value>
            <type>User</type>
        </attribute>
        <attribute>
            <name>success</name>
            <value>1.000000000</value>
            <type>java.lang.Boolean</type>
        </attribute>
    </event>
    <event>
        <date>2021-12-31T19:25:29.033+03:00</date>
        <type>banana</type>
        <departmentId>2</departmentId>
        <attribute>
            <name>userName</name>
            <value>Администратор</value>
            <type>java.lang.String</type>
        </attribute>
        <attribute>
            <name>user</name>
            <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value>
            <type>User</type>
        </attribute>
        <attribute>
            <name>success</name>
            <value>1.000000000</value>
            <type>java.lang.Boolean</type>
        </attribute>
    </event>
</eventsList>
```

### Что в ответе

Список событий в формате *eventsList*.

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<eventsList>
    <event>
        <id>9a48d9d4-8196-40e7-017e-e94b95b20023</id>
        <date>2021-12-31T19:24:29.033+03:00</date>
        <type>banana</type>
        <departmentId>2</departmentId>
        <attribute>
            <name>user</name>
            <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value>
            <type>User</type>
        </attribute>
        <attribute>
            <name>success</name>
            <value>1</value>
            <type>java.lang.Boolean</type>
        </attribute>
        <attribute>
            <name>userName</name>
            <value>Администратор</value>
            <type>java.lang.String</type>
        </attribute>
    </event>
    <event>
        <id>9a48d9d4-8196-40e7-017e-e94b95b20024</id>
        <date>2021-12-31T19:25:29.033+03:00</date>
        <type>banana</type>
        <departmentId>2</departmentId>
        <attribute>
            <name>user</name>
            <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value>
            <type>User</type>
        </attribute>
        <attribute>
            <name>userName</name>
            <value>Администратор</value>
            <type>java.lang.String</type>
        </attribute>
        <attribute>
            <name>success</name>
            <value>1</value>
            <type>java.lang.Boolean</type>
        </attribute>
    </event>
</eventsList>
```

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<eventsList>
    <event>
        <id>9a48d9d4-8196-40e7-017e-e94b95b20023</id>
        <date>2021-12-31T19:24:29.033+03:00</date>
        <type>banana</type>
        <departmentId>2</departmentId>
        <attribute>
            <name>user</name>
            <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value>
            <type>User</type>
        </attribute>
        <attribute>
            <name>success</name>
            <value>1</value>
            <type>java.lang.Boolean</type>
        </attribute>
        <attribute>
            <name>userName</name>
            <value>Администратор</value>
            <type>java.lang.String</type>
        </attribute>
    </event>
    <event>
        <id>9a48d9d4-8196-40e7-017e-e94b95b20024</id>
        <date>2021-12-31T19:25:29.033+03:00</date>
        <type>banana</type>
        <departmentId>2</departmentId>
        <attribute>
            <name>user</name>
            <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value>
            <type>User</type>
        </attribute>
        <attribute>
            <name>userName</name>
            <value>Администратор</value>
            <type>java.lang.String</type>
        </attribute>
        <attribute>
            <name>success</name>
            <value>1</value>
            <type>java.lang.Boolean</type>
        </attribute>
    </event>
</eventsList>
```


###  Описание 

Тип события может быть любым (с количеством символов не больше 255), но если он зарегистрирован в events.xml, то событие должно содержать все атрибуты, обязательные для данного типа.

У атрибута добавилось поле 'type'. Значения, которые может принимать это поле, перечислены в таблице. Тип атрибута накладывает ограничения на поле 'value'.

| type | value |
| --- | --- |
| java.lang.Boolean | "0" - false, "1" - true |
| java.lang.String | Текст |
| java.util.Date | Дата в формате "yyyy-MM-dd'T'HH:mm:ss.SSS" |
| resto.db.Guid | UUID |
| Наследники java.lang.Number. Примеры: java.lang.Integer, java.math.BigDecimal | Число. |
| Наследники resto.db.CachedEntity в простой форме. Примеры: User, Department, Terminal | UUID соответствующего справочника. |

В таблице UserEventAttribute для поля 'value' есть 4 колонки (valueDate, valueGuid, valueNumber, valueString) разных типов, и, в зависимости от типа атрибута, значение будет записано в одну из этих колонок.

## Дерево событий

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**events**/**metadata** |
| --- | --- |

### Что в ответе

Дерево событий в формате *groupsList* (см. XSD Дерево событий).

Возвращает дерево событий (аналог иерархии событий журнала событий в iikoOffice). Поле *&lt;id&gt;* используется как значение поля*&lt;type&gt;* структуры *eventList*. Также структура определяет список атрибутов, специфичных для данного события.

### Пример запроса

https://localhost:8080/resto/api/events/metadata?key=43d272ed-cfb1-64b1-9842-f3078cd69172

## Дерево событий по фильтру

Версия iiko: 5.0

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/**events**/**metadata** |
| --- | --- |

### Тело запроса
Список id событий, по которым производится фильтрация (application/xml).


```xml
<eventsRequestData>
    <events>
        <event>orderOpened</event>
    </events>
</eventsRequestData> 
```

```xml
<eventsRequestData>
    <events>
        <event>orderOpened</event>
    </events>
</eventsRequestData> 
```


### Что в ответе

Дерево событий в формате *groupsList* (см. XSD Дерево событий).

Возвращает дерево событий (аналог иерархии событий журнала событий в iikoOffice). Поле *&lt;id&gt;* используется как значение поля*&lt;type&gt;* структуры *eventList*. Также структура определяет список атрибутов, специфичных для данного события.

### Пример запроса

https://localhost:8080/resto/api/events/metadata?key=933a2e7c-be36-d2ee-0b96-9509e6f24fa1

## Информация о кассовых сменах

Версия iiko: 5.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**events**/**sessions** |
| --- | --- |

### Параметры запроса
| Название | Значение | Описание |
| --- | --- | --- |
| from\_time | *yyyy-MM-ddTHH:mm:ss.SSS* | Время с которого запрашиваются данные по кассовым сменам, в формате ISO: *yyyy-MM-ddTHH:mm:ss.SSS.* |
| --- | --- | --- |
| to\_time | *yyyy-MM-ddTHH:mm:ss.SSS* | Время по которое (не включительно) запрашиваются данные по кассовым сменам в формате ISO: *yyyy-MM-ddTHH:mm:ss.SSS*, |
| --- | --- | --- |
### Что в ответе

Информация о кассовых сменах. Время открытия, время закрытия, менеджер, номер смены, номер кассы, опер. день.

### Пример вызова

https://localhost:8080/resto/api/events/sessions?key=43d272ed-cfb1-64b1-9842-f3078cd69172&from\_time=2015-03-28T00:00:00.000&to\_time=2015-03-28T00:00:00.000

| ![Information](/resources/Storage/api-documentations/info.png) | **Если работаете по ревизии, не нужно (нельзя) указывать *to\_time*** |
| --- | --- |

## 
 [+] [XSD Дерево событий](javascript:void%280%29)
 [-] [XSD Дерево событий](javascript:void%280%29)
 
```
 %%CH%PRE8%%%%CH%PRE9%%
```

 [+] [XSD Список событий](javascript:void%280%29)
 [-] [XSD Список событий](javascript:void%280%29)
 
```
 %%CH%PRE10%%%%CH%PRE11%%
```
