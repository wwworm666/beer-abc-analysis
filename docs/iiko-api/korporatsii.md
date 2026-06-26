* [Иерархия подразделений](/articles/api-documentations/korporatsii/a/v1.APIкорпорации-Иерархияподразделений)
* [Параметры запроса](/articles/api-documentations/korporatsii/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/korporatsii/a/h3_501454233)
* [Пример запроса](/articles/api-documentations/korporatsii/a/h3_1387997121)
* [Список складов](/articles/api-documentations/korporatsii/a/v1.APIкорпорации-Списокскладов)
* [Параметры запроса](/articles/api-documentations/korporatsii/a/h3_2082204265)
* [Что в ответе](/articles/api-documentations/korporatsii/a/h3__990029522)
* [Пример запроса](/articles/api-documentations/korporatsii/a/h3__447324971)
* [Список групп и отделений](/articles/api-documentations/korporatsii/a/v1.APIкорпорации-Списокгруппиотделений)
* [Параметры запроса](/articles/api-documentations/korporatsii/a/h3_1430613933)
* [Что в ответе](/articles/api-documentations/korporatsii/a/h3__1651267685)
* [Пример запроса](/articles/api-documentations/korporatsii/a/h3_231325889)
* [Список терминалов](/articles/api-documentations/korporatsii/a/v1.APIкорпорации-Списоктерминалов)
* [Параметры запроса](/articles/api-documentations/korporatsii/a/h3_81079792)
* [Что в ответе](/articles/api-documentations/korporatsii/a/h3__1039292424)
* [Пример запроса](/articles/api-documentations/korporatsii/a/h3__1275023472)
* [Поиск подразделения](/articles/api-documentations/korporatsii/a/v1.APIкорпорации-Поискподразделения)
* [Параметры запроса](/articles/api-documentations/korporatsii/a/v1.APIкорпорации-Параметры)
* [Что в ответе](/articles/api-documentations/korporatsii/a/h3_389146006)
* [Пример запроса](/articles/api-documentations/korporatsii/a/h3__1611472903)
* [Что в ответе](/articles/api-documentations/korporatsii/a/h3_1861748801)
* [Пример запроса](/articles/api-documentations/korporatsii/a/h3_178508679)
* [Поиск групп отделений](/articles/api-documentations/korporatsii/a/v1.APIкорпорации-Поискгруппотделений)
* [Параметры запроса](/articles/api-documentations/korporatsii/a/v1.APIкорпорации-Параметры.2)
* [Что в ответе](/articles/api-documentations/korporatsii/a/h3_1460533296)
* [Пример запроса](/articles/api-documentations/korporatsii/a/h3_1320885019)
* [Поиск терминала](/articles/api-documentations/korporatsii/a/v1.APIкорпорации-Поисктерминала)
* [Параметры запроса](/articles/api-documentations/korporatsii/a/h3_1827755295)
* [Что в ответе](/articles/api-documentations/korporatsii/a/h3_964309840)
* [Пример запроса](/articles/api-documentations/korporatsii/a/h3_1383011687)
* [Получение настроек корпорации](/articles/api-documentations/korporatsii/a/v2.APIнастроекпредприятия-Получениенастроеккорпорации)
* [Доступ](/articles/api-documentations/korporatsii/a/v2.APIнастроекпредприятия-Доступ)
* [Результат](/articles/api-documentations/korporatsii/a/v2.APIнастроекпредприятия-Результат)
* [Пример запроса и результата](/articles/api-documentations/korporatsii/a/v2.APIнастроекпредприятия-Примерзапросаирезультата)

##  Иерархия подразделений

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**corporation**/**departments**/ |
| --- | --- |

### Параметры запроса

| **Название** | **Значение** | **Версия iiko** | **Описание** |
| --- | --- | --- | --- |
| revisionFrom | число, номер ревизии | с 6.4 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

### **Что в ответе**

Все подразделения по типам в виде структуры *corporateItemDto*.

См. расшифровки возможных типов в разделе "Расшифровки кодов базовых типов - Типы подразделений".

#### Типы подразделений 

| Код | Название |
| --- | --- |
| CORPORATION | Корпорация |
| JURPERSON | Юридическое лицо |
| ORGDEVELOPMENT | Структурное подразделение |
| DEPARTMENT | Торговое предприятие |
| MANUFACTURE | Производство |
| CENTRALSTORE | Центральный склад |
| CENTRALOFFICE | Центральный офис |
| SALEPOINT | Точка продаж |
| STORE | Склад |

### **Пример запроса**

https://localhost:8080/resto/api/corporation/departments?key=420d0839-2aa7-801e-9f1a-cf7d23f65fba&revisionFrom=-1

## Список складов 
 
Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**corporation**/**stores**/ |
| --- | --- |

### **Параметры запроса**

| **Название** | **Тип данных** | **Версия** | **Описание** |
| --- | --- | --- | --- |
| revisionFrom | -1, число | с 6.4 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

### **Что в ответе**

**** Все склады ТП в виде структуры *corporateItemDto.*

### **Пример запроса**

https://localhost:8080/resto/api/corporation/stores?key=71046728-36fa-053c-b01c-c5b43bfd277f&revisionFrom=-1

##  Список групп и отделений 
 
Версия iiko: 4.3

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**corporation**/**groups**/ |
| --- | --- |

### **Параметры запроса**

| **Название** | **Тип данных** | **Версия** | **Описание** |
| --- | --- | --- | --- |
| revisionFrom | -1, число | с 6.4 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

### **Что в ответе**

**** Все группы отделений, отделения и точки продаж ТП в виде структуры *groupDto*.

В группе отделений может быть несколько точек продаж, но главная касса (свойство groupDto/pointOfSaleDtoes/pointOfSaleDto/main=true) может быть подключена только к одной из них.

В iikoChain информация о кассе точки продаж (groupDto/pointOfSaleDtoes/pointOfSaleDto/cashRegisterInfo) может отсутствовать.

### **Пример запроса**

https://localhost:8080/resto/api/corporation/groups?key=71046728-36fa-053c-b01c-c5b43bfd277f&revisionFrom=-1

##  Список терминалов 
 
Версия iiko: 4.3

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**corporation**/**terminals**/ |
| --- | --- |

### **Параметры запроса**

| **Название** | **Тип данных** | **Версия** | **Описание** |
| --- | --- | --- | --- |
| revisionFrom | -1, число | с 6.4 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

### **Что в ответе**

**** Все терминалы ТП в виде структуры *terminalDto.*

Как правило, интересны только фронтовые терминалы, см. поиск терминалов*/corporation/terminal/search.*

### **Пример запроса**

https://localhost:8080/resto/api/corporation/terminals?key=71046728-36fa-053c-b01c-c5b43bfd277f&revisionFrom=-1

## Поиск подразделения 
 
Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**corporation**/**departments**/**search** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| code | **[**departmentCode**]** | Код торгового предприятия. Значение элемента &lt;code&gt; из структуры corporateItemDto<br> <br>Регулярное выражение. Если задать просто строку, то ищет любое вхождение этой строки в код ТП с учетом регистра |

### **Что в ответе**

Структура *corporateItemDto,* если существует подразделение с данным кодом.

**** Поиск торгового предприятия по коду. Имеет смысл только для подразделений с типом DEPARTMENT и в основном только в iikoChain, т.к. в рамках iikoRMS только одна сущность с таким типом.

### **Пример запроса**

https://localhost:8080/resto/api/corporation/departments/search?key=71046728-36fa-053c-b01c-c5b43bfd277f&code=1

## 
 
### **Что в ответе**

Структура *corporateItemDto*, если существует склад с данным кодом.

Поиск склада по коду. **Для работы этого метода необходимо, чтобы коды складов в ТП были заполнены (данное поле является необязательным и по умолчанию пусто**

### **Пример запроса**

https://localhost:8080/resto/api/corporation/stores/search?key=71046728-36fa-053c-b01c-c5b43bfd277f&code=Dom

##  Поиск групп отделений 
 
Версия iiko: 4.3

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**corporation**/**groups**/**search** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| name | regex | Название группы |
| departmentId | uuid | ID подразделения |

### **Что в ответе**

Список *groupDto*, если существуют подходящие группы отделений

### **Пример запроса**

https://localhost:8080/resto/api/corporation/terminal/search?key=71046728-36fa-053c-b01c-c5b43bfd277f&name=New%20group

## Поиск терминала 
 
Версия iiko: 4.3

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**corporation**/**terminals**/**search** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| name | regex | Имя терминала в том виде, как он отображается в бекофисе |
| computerName | regex | Имя компьютера |
| anonymous | false/true | Фронты имеют anonymous=false, бекофисы и системные терминалы — true. |

### **Что в ответе**

Поиск терминалов. Список *terminalDto*, если существуют подходящие терминалы.

### **Пример запроса**

https://localhost:8080/resto/api/corporation/terminals/search?key=71046728-36fa-053c-b01c-c5b43bfd277f&anonymous=false
 
## Получение настроек корпорации

## Доступ

Чтобы пользоваться API настроек предприятия:

* У пользователя, под чьим именем осуществляется вход, должно быть право B\_ADM "Администрирование системы".

Версия iiko: 6.2

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**corporation**/**settings** |
| --- | --- |

### Результат

Json структура настроек предприятия

| **Поле** | **Значение** | **Результат** |
| --- | --- | --- |
| vatAccounting | VAT\_INCLUDED\_IN\_PRICE,<br><br>VAT\_NOT\_INCLUDED\_IN\_PRICE | "НДС вкл. в цену закупки".<br><br>"НДС не вкл. в цену закупки". |
| --- | --- | --- |

### Пример запроса и результата

https://localhost:8080/resto/api/v2/corporation/settings


Код

```
{
  "vatAccounting":"VAT_INCLUDED_IN_PRICE"
}
```

Код

```
{
  "vatAccounting":"VAT_INCLUDED_IN_PRICE"
}
```


## 
 [+] [XSD Группа отделений и точек продаж](javascript:void%280%29)
 [-] [XSD Группа отделений и точек продаж](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 [+] [XSD Терминал](javascript:void%280%29)
 [-] [XSD Терминал](javascript:void%280%29)
 
```
 %%CH%PRE4%%%%CH%PRE5%%
```

 [+] [XSD Элемент иерархии корпорации](javascript:void%280%29)
 [-] [XSD Элемент иерархии корпорации](javascript:void%280%29)
 
```
 %%CH%PRE6%%%%CH%PRE7%%
```
