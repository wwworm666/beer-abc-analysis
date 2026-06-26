* [Вывести список всех бригад](/articles/api-documentations/rabota-s-dannymi-brigad/a/APIБригад-Вывестисписоквсехбригад)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_501454233)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_1387997121)
* [Вывести список бригад по подразделению](/articles/api-documentations/rabota-s-dannymi-brigad/a/APIБригад-Вывестисписокбригадпоподразделению)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_1618304206)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__976621098)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_1160782444)
* [Вывести список бригад по коду](/articles/api-documentations/rabota-s-dannymi-brigad/a/APIБригад-Вывестисписокбригадпокоду)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_136818968)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_1831665234)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__1703667854)
* [Вывести бригаду по id](/articles/api-documentations/rabota-s-dannymi-brigad/a/APIБригад-Вывестибригадупоid)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__1532176138)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_1961060346)
* [Поиск бригад по параметрам](/articles/api-documentations/rabota-s-dannymi-brigad/a/APIБригад-Поискбригадпопараметрам)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_718167440)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_1975894048)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__1537385906)
* [Добавить бригаду по коду](/articles/api-documentations/rabota-s-dannymi-brigad/a/APIБригад-Добавитьбригадупокоду)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__591255536)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__1441919473)
* [Добавить или заместить бригаду по id](/articles/api-documentations/rabota-s-dannymi-brigad/a/APIБригад-Добавитьилизаместитьбригадупоid)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_608413864)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__83152786)
* [Добавить или заместить бригаду по id](/articles/api-documentations/rabota-s-dannymi-brigad/a/h2__36013634)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_307536516)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__1108659373)
* [Удалить бригаду](/articles/api-documentations/rabota-s-dannymi-brigad/a/h2_202080259)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__204191011)
* [Назначение сотрудников в бригады](/articles/api-documentations/rabota-s-dannymi-brigad/a/APIБригад-Назначениесотрудниковвбригады)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__1925687340)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__690984701)
* [Просмотр назначений сотрудников в бригады во всех подразделениях (запрос выполняется на chain)](/articles/api-documentations/rabota-s-dannymi-brigad/a/APIБригад-Просмотрназначенийсотрудниковвбригадывовсехподразделениях%28запросвыполняетсянаchain%29)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_961129799)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__44695177)
* [Просмотр назначений сотрудников в бригады в подразделении](/articles/api-documentations/rabota-s-dannymi-brigad/a/APIБригад-Просмотрназначенийсотрудниковвбригадывподразделении)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3__910177913)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_1327012824)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-brigad/a/h3_312270173)
* [Описание бригады для представления в формате XML (XSD-схема)](/articles/api-documentations/rabota-s-dannymi-brigad/a/APIБригад-ОписаниебригадыдляпредставлениявформатеXML%28XSD-схема%29)

API бригад состоит из двух частей:

1. Работа со справочником бригад (**WaiterTeam** см. описание XSD в конце статьи). Через АПИ можно создать/прочитать/изменить/удалить бригады. 
Бригады являются локальными объектами каждого отдельного РМС. На chain хранятся бригады со всех РМС.
Создавать/изменять/удалять бригады можно только на РМС. Читать (методы GET) можно как на РМС так и на chain.
2. Назначение сотрудников в бригады. Назначение сотрудников в бригады храниться в отдельном справочнике (**WaiterTeamAssignments**см. описание XSD в конце статьи).
В элементе этого справочника хранятся все назначения по конкретному РМС, т.е. РМС хранит не более одного элемента данного справочника.
Один сотрудник может быть назначен не более чем в одну команду на каждом РМС.
На chain хранятся элементы справочника **WaiterTeamAssignments**со всех РМС.
Так же как и с бригадами изменять назначения можно только на РМС, а читать можно как на РМС, так и на chain.

## Вывести список всех бригад

Версия API: 1.0

Версия iiko: 8.1
| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/waiterTeams |
| --- | --- |
### **Параметры запроса**

| **Название** | **Значение** | **Значение по умолчанию** | **Версия** | **Описание** |
| --- | --- | --- | --- | --- |
| includeDeleted | true/false | false | 8.1 | Возвращать и действующие, и удаленные бригады. |
| revisionFrom | число, номер ревизии | -1 | 8.1 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom. |

### **Что в ответе**

Список всех бригад.

### **Пример запроса**

https://localhost:8080/resto/api/employees/waiterTeams?includeDeleted=true

**Пример результата вызова API:**

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeams>
    <waiterTeam>
        <id>49df70c5-22ef-436f-0181-239f8cc60035</id>
        <code>5</code>
        <name>My favourite team</name>
        <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
        <deleted>true</deleted>
    </waiterTeam>
    <waiterTeam>
        <id>49df70c5-22ef-436f-0181-239f8cc60027</id>
        <code>1</code>
        <name>New team 1</name>
        <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
        <deleted>false</deleted>
    </waiterTeam>
</waiterTeams>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeams>
    <waiterTeam>
        <id>49df70c5-22ef-436f-0181-239f8cc60035</id>
        <code>5</code>
        <name>My favourite team</name>
        <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
        <deleted>true</deleted>
    </waiterTeam>
    <waiterTeam>
        <id>49df70c5-22ef-436f-0181-239f8cc60027</id>
        <code>1</code>
        <name>New team 1</name>
        <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
        <deleted>false</deleted>
    </waiterTeam>
</waiterTeams>
```
**

## Вывести список бригад по подразделению

Версия API: 1.0

Версия iiko: 8.1
| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/waiterTeams/byDepartment**/{departmentUUID}** |
| --- | --- |
### **Параметры** запроса

| **Название** | **Значение** | **Значение по умолчанию** | **Версия** | **Описание** |
| --- | --- | --- | --- | --- |
| includeDeleted | true/false | false | 8.1 | Возвращать и действующие, и удаленные бригады. |
| revisionFrom | число, номер ревизии | -1 | 8.1 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom. |

### **Что в ответе**

Список всех бригад с указанном подразделении.

### **Пример запроса**

https://localhost:8080/resto/api/employees/waiterTeams/byDepartment/873986a7-2e4b-4029-0149-2d0362b4000d

## Вывести список бригад по коду

Версия API: 1.0

Версия iiko: 8.1

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | **https://host:port/resto/api/employees/waiterTeams/** **byCode/{teamCode}** |
| --- | --- |

### **Параметры запроса**

| **Название** | **Значение** | **Значение по умолчанию** | **Версия** | **Описание** |
| --- | --- | --- | --- | --- |
| includeDeleted | true/false | false | 8.1 | Возвращать и действующие, и удаленные бригады. |

### **Что в ответе**

Список всех бригад с указанным кодом.

Так как код должен быть уникальным для всех не удаленных бригад, то если не задан параметр includeDeleted, то возвращается список с одним элементом.

### **Пример запроса**

https://localhost:8080/resto/api/employees/waiterTeams/byCode/5555?includeDeleted=true

## Вывести бригаду по id

Версия API: 1.0

Версия iiko: 8.1

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **https://host:port/resto/api/employees/waiterTeams/** **byId/{teamUUID}** |
| --- | --- |

### **Что в ответе**

Бригада с указанным UUID

### **Пример запроса**

https://localhost:8080/resto/api/employees/waiterTeams/byId/49df70c5-22ef-436f-0181-239f8cc60035

**Пример результата вызова API:**

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeam>
    <id>49df70c5-22ef-436f-0181-239f8cc60035</id>
    <code>5</code>
    <name>My favourite team</name>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
    <deleted>true</deleted>
</waiterTeam>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeam>
    <id>49df70c5-22ef-436f-0181-239f8cc60035</id>
    <code>5</code>
    <name>My favourite team</name>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
    <deleted>true</deleted>
</waiterTeam>
```
**

## Поиск бригад по параметрам

Версия API: 1.0

Версия iiko: 8.1
| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/waiterTeams**/search?{param1}={regexp}&{param2}={regexp}&includeDeleted={true/false}** |
| --- | --- |
### **Параметры запроса**

| **Параметры** | **Описание** |
| --- | --- |
| name<br><br>code | Регулярное выражение по любому из текстовых полей в dto.<br><br>Параметры необязательные. Если отсутствуют, вернет все активные бригады. |
| includeDeleted | Возвращать и действующие, и удаленные бригады. |

### **Что в ответе**

Выводит все бригады, удовлетворяющую заданным условиям. Можно указывать любое количество из доступных параметров.

### **Пример запроса**

https://localhost:8080/resto/api/employees/waiterTeams/search?code=555&includeDeleted=true

## Добавить бригаду по коду

Версия API: 1.0

Версия iiko: 8.1

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | https://host:port/resto/api/employees/waiterTeams/byCode/{teamCode} |
| --- | --- |

### **Что в ответе**

Если бригада с указанным кодом еще не существовала, то создается новая бригада (код возврата 201 Created).

Если бригада с указанным кодом существовала, то выведется ошибка (код возврата 409 Conflict).

### **Пример запроса**

https://localhost:8080/resto/api/employees/waiterTeams/byCode/10

**Пример тела запроса:**

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<waiterTeam>
    <name>New team 10</name>
</waiterTeam>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<waiterTeam>
    <name>New team 10</name>
</waiterTeam>
```
**

**Пример результата вызова API:**

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeam>
    <id>e2c60d0b-756f-3b23-0181-23fd74e6006a</id>
    <code>10</code>
    <name>New team 10</name>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
    <deleted>false</deleted>
</waiterTeam>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeam>
    <id>e2c60d0b-756f-3b23-0181-23fd74e6006a</id>
    <code>10</code>
    <name>New team 10</name>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
    <deleted>false</deleted>
</waiterTeam>
```
**

## Добавить или заместить бригаду по id

Версия API: 1.0

Версия iiko: 8.1

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | https://host:port/resto/api/employees/waiterTeams/byId/{UUID} |
| --- | --- |

### **Что в ответе**

Если бригада с указанным UUID еще не существовала, то создается новая бригада (код возврата 201 Created).

Если бригада с указанным UUID уже существовала, то произойдет замещение всех полей бригады (код возврата 200 ОК). При этом нужно обязательно указать все поля dto, иначе неуказанным полям присвоятся значения по умолчанию.

Более подробно см. **Описание бригады для представления в формате XML (XSD-схема)**

Если требуется изменить только отдельные поля бригады, то лучше использовать метод, описанный ниже.

### **Пример запроса**

https://localhost:8080/resto/api/employees/waiterTeams/byId/76d2a834-4b0a-d67c-0180-db53849a001e

**Пример тела запроса:**

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<waiterTeam>
    <name>The best team</name>
    <code>569</code>
</waiterTeam>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<waiterTeam>
    <name>The best team</name>
    <code>569</code>
</waiterTeam>
```
**

**Пример результата вызова API:**

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeam>
    <id>76d2a834-4b0a-d67c-0180-db53849a001e</id>
    <code>569</code>
    <name>The best team</name>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
    <deleted>false</deleted>
</waiterTeam>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeam>
    <id>76d2a834-4b0a-d67c-0180-db53849a001e</id>
    <code>569</code>
    <name>The best team</name>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
    <deleted>false</deleted>
</waiterTeam>
```
**

## Добавить или заместить бригаду по id

Версия API: 1.0

Версия iiko: 8.1

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/**employees/waiterTeams/byId/{UUID}** |
| --- | --- |

### **Что в ответе**

Если бригада с указанным UUID еще не существовала, то создается новая бригада (код возврата 201 Created).

Если бригада с указанным UUID уже существовала, то произойдет замещение тех полей бригады, которые явно указаны в запросе (код возврата 200 ОК).

### **Пример запроса**

https://localhost:8080/resto/api/employees/waiterTeams/byId/76d2a834-4b0a-d67c-0180-db53849a001f

#### Пример результата вызова API


```json
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeam>
    <id>76d2a834-4b0a-d67c-0180-db53849a001f</id>
    <code>147</code>
    <name>My favourite team</name>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
    <deleted>false</deleted>
</waiterTeam>
```

```json
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeam>
    <id>76d2a834-4b0a-d67c-0180-db53849a001f</id>
    <code>147</code>
    <name>My favourite team</name>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
    <deleted>false</deleted>
</waiterTeam>
```


## Удалить бригаду

Версия API: 1.0

Версия iiko: 8.1

| ![DELETE Request](/resources/Storage/api-documentations/http_request_delete.png) | https://host:port/resto/api/employees/waiterTeams/byId/{teamUUID} |
| --- | --- |

### Что в ответе

Пустой ответ, если бригада удалена (или уже была удалена).

Entity of class WaiterTeam not found by id (teamUUID), если передан несуществующий guid.

## Назначение сотрудников в бригады

Версия API: 1.0

Версия iiko: 8.1

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | https://host:port/resto/api/employees/waiterTeams/assignments |
| --- | --- |

### **Что в ответе**

Измененная карта назначений сотрудников в бригады.

Если карты назначений не было, то будет создана новая в соответствии с телом запроса.

Если назначения уже были, то запрос внесет изменения только по тем сотрудникам, которые участвовали в запросе:

1. Если сотруднику присвоил id другой бригады, то произойдет переназначение сотрудника в другую бригаду (т.е. нет необходимости сначала удалять из старой бригады, а затем назначать в новую бригаду).
2. Если сотруднику присвоили id той же самой бригады, в которой он был, то по конкретному сотруднику ничего не поменяется.
3. Если сотруднику передать пустой тэг teamId или вообще этот тэг не указывать, то сотрудник будет удален из ранее назначенной бригады.
4. Если сотрудник уже был в бригаде и в запросе на изменение бригад id этого сотрудника не было, то после выполнения запроса он останется в той же самой бригаде.

### **Пример запроса**

https://localhost:8080/resto/api/employees/waiterTeams/assignments

**Пример тела запроса:**

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeamAssignments>
    <assignment>
        <employeeId>b032e07b-b938-442d-83bf-002bd7896a3d</employeeId>
        <teamId>49df70c5-22ef-436f-0181-239f8cc60027</teamId>
    </assignment>
    <assignment>
        <employeeId>ca7a2238-faa1-4554-9418-009e4adb9ecc</employeeId>
        <teamId>76d2a834-4b0a-d67c-0180-db53849a001e</teamId>
    </assignment>
</waiterTeamAssignments>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeamAssignments>
    <assignment>
        <employeeId>b032e07b-b938-442d-83bf-002bd7896a3d</employeeId>
        <teamId>49df70c5-22ef-436f-0181-239f8cc60027</teamId>
    </assignment>
    <assignment>
        <employeeId>ca7a2238-faa1-4554-9418-009e4adb9ecc</employeeId>
        <teamId>76d2a834-4b0a-d67c-0180-db53849a001e</teamId>
    </assignment>
</waiterTeamAssignments>
```
**

**Пример результата вызова API:**

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeamAssignments>
    <id>496032ff-7142-66bc-0181-23b04b5c00d3</id>
    <assignment>
        <employeeId>b032e07b-b938-442d-83bf-002bd7896a3d</employeeId>
        <teamId>49df70c5-22ef-436f-0181-239f8cc60027</teamId>
    </assignment>
    <assignment>
        <employeeId>ca7a2238-faa1-4554-9418-009e4adb9ecc</employeeId>
        <teamId>76d2a834-4b0a-d67c-0180-db53849a001e</teamId>
    </assignment>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
</waiterTeamAssignments>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeamAssignments>
    <id>496032ff-7142-66bc-0181-23b04b5c00d3</id>
    <assignment>
        <employeeId>b032e07b-b938-442d-83bf-002bd7896a3d</employeeId>
        <teamId>49df70c5-22ef-436f-0181-239f8cc60027</teamId>
    </assignment>
    <assignment>
        <employeeId>ca7a2238-faa1-4554-9418-009e4adb9ecc</employeeId>
        <teamId>76d2a834-4b0a-d67c-0180-db53849a001e</teamId>
    </assignment>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
</waiterTeamAssignments>
```
**

## Просмотр назначений сотрудников в бригады во всех подразделениях (запрос выполняется на chain)

Версия API: 1.0

Версия iiko: 8.1
| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/waiterTeams/assignments |
| --- | --- |
### **Параметры запроса**
| **Название** | **Значение** | **Значение по умолчанию** | **Версия** | **Описание** |
| --- | --- | --- | --- | --- |
| revisionFrom | число, номер ревизии | -1 | 8.1 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom. |
### Что в ответе

Карта назначений сотрудников в бригады во всех подразделениях.

**Пример запроса**

https://localhost:8080/resto/api/employees/waiterTeams/assignments?revisionFrom=100

#### Пример результата вызова API:

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeamAssignmentsList>
    <waiterTeamAssignments>
        <id>496032ff-7142-66bc-0181-23b04b5c00d3</id>
        <assignment>
            <employeeId>b032e07b-b938-442d-83bf-002bd7896a3d</employeeId>
            <teamId>49df70c5-22ef-436f-0181-239f8cc60027</teamId>
        </assignment>
        <assignment>
            <employeeId>ca7a2238-faa1-4554-9418-009e4adb9ecc</employeeId>
            <teamId>76d2a834-4b0a-d67c-0180-db53849a001e</teamId>
        </assignment>
        <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
    </waiterTeamAssignments>
</waiterTeamAssignmentsList>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeamAssignmentsList>
    <waiterTeamAssignments>
        <id>496032ff-7142-66bc-0181-23b04b5c00d3</id>
        <assignment>
            <employeeId>b032e07b-b938-442d-83bf-002bd7896a3d</employeeId>
            <teamId>49df70c5-22ef-436f-0181-239f8cc60027</teamId>
        </assignment>
        <assignment>
            <employeeId>ca7a2238-faa1-4554-9418-009e4adb9ecc</employeeId>
            <teamId>76d2a834-4b0a-d67c-0180-db53849a001e</teamId>
        </assignment>
        <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
    </waiterTeamAssignments>
</waiterTeamAssignmentsList>
```
**

## Просмотр назначений сотрудников в бригады в подразделении

Версия API: 1.0

Версия iiko: 8.1

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/waiterTeams/assignments/byDepartment/{departmentId} |
| --- | --- |

### **Параметры запроса**
| **Название** | **Значение** | **Значение по умолчанию** | **Версия** | **Описание** |
| --- | --- | --- | --- | --- |
| revisionFrom | число, номер ревизии | -1 | 8.1 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom. |
### Что в ответе

Карта назначений сотрудников в бригады в указанном подразделении.

### **Пример запроса**

https://localhost:8080/resto/api/employees/waiterTeams/assignments/byDepartment/873986a7-2e4b-4029-0149-2d0362b4000d

**Пример результата вызова API:**

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeamAssignments>
    <id>496032ff-7142-66bc-0181-23b04b5c00d3</id>
    <assignment>
        <employeeId>b032e07b-b938-442d-83bf-002bd7896a3d</employeeId>
        <teamId>49df70c5-22ef-436f-0181-239f8cc60027</teamId>
    </assignment>
    <assignment>
        <employeeId>ca7a2238-faa1-4554-9418-009e4adb9ecc</employeeId>
        <teamId>76d2a834-4b0a-d67c-0180-db53849a001e</teamId>
    </assignment>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
</waiterTeamAssignments>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<waiterTeamAssignments>
    <id>496032ff-7142-66bc-0181-23b04b5c00d3</id>
    <assignment>
        <employeeId>b032e07b-b938-442d-83bf-002bd7896a3d</employeeId>
        <teamId>49df70c5-22ef-436f-0181-239f8cc60027</teamId>
    </assignment>
    <assignment>
        <employeeId>ca7a2238-faa1-4554-9418-009e4adb9ecc</employeeId>
        <teamId>76d2a834-4b0a-d67c-0180-db53849a001e</teamId>
    </assignment>
    <departmentId>873986a7-2e4b-4029-0149-2d0362b4000d</departmentId>
</waiterTeamAssignments>
```
**

## Описание бригады для представления в формате XML (XSD-схема)
 [+] [WaiterTeam](javascript:void%280%29)
 [-] [WaiterTeam](javascript:void%280%29)
 
```
 %%CH%PRE22%%%%CH%PRE23%%
```

 [+] [WaiterTeamAssignments](javascript:void%280%29)
 [-] [WaiterTeamAssignments](javascript:void%280%29)
 
```
 %%CH%PRE24%%%%CH%PRE25%%
```
