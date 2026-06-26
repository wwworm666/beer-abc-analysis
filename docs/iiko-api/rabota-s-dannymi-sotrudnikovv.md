* [Список активных](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h2__2109393174)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_501454233)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_1387997121)
* [Список по подразделению](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h2__1547518874)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_1553313209)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_105637038)
* [Сотрудник по ID](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h2__2094082183)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_2138875455)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3__984807956)
* [Сотрудник по коду](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h2__243212989)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_226895131)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3__1886227089)
* [Поиск сотрудника](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h2_623154327)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_1270857196)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3__1577761397)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3__237152841)
* [Добавить или заменить сотрудника (по Id)](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h2_653670241)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_945285395)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_687002477)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3__820067579)
* [Добавить сотрудника (по коду)](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h2__1324771003)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3__436508111)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_384736109)
* [Изменить/добавить сотрудника (по id)](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h2_439774833)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_179396395)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_1880996741)
* [Удалить сотрудника](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h2_1893260727)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_600101026)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/h3_1310189372)
* [Описание сущностей для представления в формате XML (XSD-схема)](/articles/api-documentations/rabota-s-dannymi-sotrudnikovv/a/v1.APIсотрудников-ОписаниясущностейдляпредставлениявформатеXML%28XSD-схема%29)

## Список активных

Версия API: 1.0

Версия iiko: 4.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees |
| --- | --- |

### Параметры запроса

### 

####  

| **Название** | **Значение** | **Версия** | **Описание** |
| --- | --- | --- | --- |
| includeDeleted | true/false | с 5.0 | Возвращать и действующих, и удаленных сотрудников |
| revisionFrom | число, номер ревизии | с 6.4 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br> <br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

### Что в ответе
Список сотрудников.  Все сотрудники (включая встроенные системные аккаунты), которые активны (не удалены)

###  **Пример запроса**

https://localhost:8080/resto/api/employees?key=284c5690-2b56-b1d6-0c81-e94b5034243d

## Список по подразделению

Версия API: 1.0

Версия iiko: 4.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **** https://host:port/resto/api/employees/byDepartment/{departmentCode} |
| --- | --- |

### Параметры запроса

| **Параметр** | **Описание** |
| --- | --- |
| **includeDeleted** (с 5.0) | Возвращать и действующих, и удаленных сотрудников |

### Что в ответе
 
Список сотрудников указанного подразделения.  Все сотрудники (включая встроенные системные аккаунты), которые активны (не удалены).
 
Для RMS идентично обычному списку, для Chain - только список сотрудников указанного подразделения.
 
**Пример запроса**

https://localhost:8080/resto/api/employees/byDepartment/1?key=284c5690-2b56-b1d6-0c81-e94b5034243d

## Сотрудник по ID

Версия API: 1.0

Версия iiko: 4.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **** https://host:port/resto/api/employees/byId/{employeeUUID} |
| --- | --- |

### 

### Что в ответе

Сотрудник с указанным GUID.

### Пример запроса

https://localhost:8080/resto/api/employees/byId/61b97cfb-6b4e-4668-9a38-c30190f7a109?key=180c8a55-efae-8183-0d6d-015a685f84f1

###  

## Сотрудник по коду

Версия API: 1.0

Версия iiko: 4.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **https://host:port/resto/api/employees/byCode/{employeeCode}** |
| --- | --- |

### Что в ответе

Сотрудник с указанным кодом.

###  **Пример запроса**

https://localhost:8080/resto/api/employees/byCode/2?key=a10b7fdc-9ae5-449f-c6fb-cb5a67e5b2e6

## Поиск сотрудника

Версия API: 1.0

Версия iiko: 4.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**employees/search?firstName={regexp}&middleName={regexp}** |
| --- | --- |

### Параметры запроса
| **Параметры** | **Описание** |
| --- | --- |
| address <br> cardNumber <br> cellPhone <br> client <br> code <br> email <br> employee <br> firstName <br> lastName <br> login <br> mainRoleCode <br> middleName <br> name <br> note <br> phone <br> supplier | Регулярное выражение<br> <br>По любому из текстовых или булевых полей в dto (см. список в 1 столбце)<br> <br>Параметры необязательные. Если отсутствуют, вернет всех активных |
| **includeDeleted** (с 5.0) | Возвращать и действующих, и удаленных сотрудников |

### Что в ответе

Сотрудник с указанными именем и/или отчеством.

###  **Пример запроса**

https://localhost:8080/resto/api/employees/search?key=de7c43fc-b4d7-cf45-51b4-c40cba21265f&firstName=n&middleName=m

## Добавить или заменить сотрудника (по Id)
Версия API: 1.0

Версия iiko: 4.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **https://host:port/resto/api****/employees/byId/{UUID}** |
| --- | --- |

### Параметры запроса

### Что в ответе
 
Если передан новый id, то будет создан новый сотрудник (код возврата 201 Created).
 
Если передан id существующего сотрудника, то произойдет полное замещение всех полей сотрудника (код возврата 200 OK). При этом если не указать какое-либо из необязательных полей, то значение этого поля сбросится.
 
Для обновления частичного набора полей используйте метод POST **/employees/byId/{employeeUUID}**

###  **Пример запроса**

https://localhost:8080/resto/api/employees/byId/4f390698-241d-6ab9-015e-a3d90baa0370


Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<employee>
    <code>6</code>
    <name>АPIbyId</name>
    <login/>
    <mainRoleCode>CS1</mainRoleCode>
    <roleCodes>CS1</roleCodes>
    <phone>7979</phone>
    <cellPhone>00000</cellPhone>
    <firstName>Name</firstName>
    <lastName>Name</lastName>
    <birthday>2017-09-14T00:00:00+03:00</birthday>
    <email>email2@mail.ru</email>
    <address>address</address>
    <hireDate>2017-09-04T00:00:00+03:00</hireDate>
    <fireDate>2017-09-21T00:00:00+03:00</fireDate>
    <cardNumber/>
    <taxpayerIdNumber>111111111111111111</taxpayerIdNumber>
    <snils>455555555555555555</snils>
    <preferredDepartmentCode>1</preferredDepartmentCode>
    <departmentCodes>1</departmentCodes>
    <responsibilityDepartmentCodes>1</responsibilityDepartmentCodes>
    <deleted>false</deleted>
    <supplier>false</supplier>
    <employee>true</employee>
    <client>false</client>
    <publicExternalData>
        <entry>
            <key>keyPUT</key>
            <value>valuePUT</value>
        </entry>
    </publicExternalData>
</employee>
```

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<employee>
    <code>6</code>
    <name>АPIbyId</name>
    <login/>
    <mainRoleCode>CS1</mainRoleCode>
    <roleCodes>CS1</roleCodes>
    <phone>7979</phone>
    <cellPhone>00000</cellPhone>
    <firstName>Name</firstName>
    <lastName>Name</lastName>
    <birthday>2017-09-14T00:00:00+03:00</birthday>
    <email>email2@mail.ru</email>
    <address>address</address>
    <hireDate>2017-09-04T00:00:00+03:00</hireDate>
    <fireDate>2017-09-21T00:00:00+03:00</fireDate>
    <cardNumber/>
    <taxpayerIdNumber>111111111111111111</taxpayerIdNumber>
    <snils>455555555555555555</snils>
    <preferredDepartmentCode>1</preferredDepartmentCode>
    <departmentCodes>1</departmentCodes>
    <responsibilityDepartmentCodes>1</responsibilityDepartmentCodes>
    <deleted>false</deleted>
    <supplier>false</supplier>
    <employee>true</employee>
    <client>false</client>
    <publicExternalData>
        <entry>
            <key>keyPUT</key>
            <value>valuePUT</value>
        </entry>
    </publicExternalData>
</employee>
```


**Пример результата вызова API**


Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<employee>
    <id>4f390698-241d-6ab9-015e-a3d90baa0370</id>
    <code>6</code>
    <name>АPIbyId</name>
    <login/>
    <mainRoleCode>CS1</mainRoleCode>
    <roleCodes>CS1</roleCodes>
    <phone>7979</phone>
    <cellPhone>00000</cellPhone>
    <firstName>Name</firstName>
    <lastName>Name</lastName>
    <birthday>2017-09-14T00:00:00+03:00</birthday>
    <email>email2@mail.ru</email>
    <address>address</address>
    <hireDate>2017-09-04T00:00:00+03:00</hireDate>
    <fireDate>2017-09-21T00:00:00+03:00</fireDate>
    <cardNumber/>
    <taxpayerIdNumber>111111111111111111</taxpayerIdNumber>
    <snils>455555555555555555</snils>
    <preferredDepartmentCode>1</preferredDepartmentCode>
    <departmentCodes>1</departmentCodes>
    <responsibilityDepartmentCodes>1</responsibilityDepartmentCodes>
    <deleted>false</deleted>
    <supplier>false</supplier>
    <employee>true</employee>
    <client>false</client>
    <publicExternalData>
        <entry>
            <key>keyPUT</key>
            <value>valuePUT</value>
        </entry>
    </publicExternalData>
</employee>
```

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<employee>
    <id>4f390698-241d-6ab9-015e-a3d90baa0370</id>
    <code>6</code>
    <name>АPIbyId</name>
    <login/>
    <mainRoleCode>CS1</mainRoleCode>
    <roleCodes>CS1</roleCodes>
    <phone>7979</phone>
    <cellPhone>00000</cellPhone>
    <firstName>Name</firstName>
    <lastName>Name</lastName>
    <birthday>2017-09-14T00:00:00+03:00</birthday>
    <email>email2@mail.ru</email>
    <address>address</address>
    <hireDate>2017-09-04T00:00:00+03:00</hireDate>
    <fireDate>2017-09-21T00:00:00+03:00</fireDate>
    <cardNumber/>
    <taxpayerIdNumber>111111111111111111</taxpayerIdNumber>
    <snils>455555555555555555</snils>
    <preferredDepartmentCode>1</preferredDepartmentCode>
    <departmentCodes>1</departmentCodes>
    <responsibilityDepartmentCodes>1</responsibilityDepartmentCodes>
    <deleted>false</deleted>
    <supplier>false</supplier>
    <employee>true</employee>
    <client>false</client>
    <publicExternalData>
        <entry>
            <key>keyPUT</key>
            <value>valuePUT</value>
        </entry>
    </publicExternalData>
</employee>
```


## Добавить сотрудника (по коду)

| ![PUT Request](/resources/Storage/api-documentations/http_request_put.png) | **https://host:port/resto/api/** **employees/byCode/{employeeCode}** |
| --- | --- |

###  Что в ответе

Новый сотрудник (код возврата 201 Created).

учитывается только код, переданный в теле PUT-запроса.

###   **Пример запроса** 
https://localhost:8080/resto/api/employees/byCode/5

employeeCode - введенное значение будет отображаться в поле Табельный номер
 
**Пример результата вызова API**
 

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<employee>
    <id>4f390698-241d-6ab9-015e-a3d90baa0371</id>
    <code>5</code>
    <name>АPI</name> //имя в системе
    <login/>
    <mainRoleCode>CS1</mainRoleCode>
    <roleCodes>CS1</roleCodes>
    <phone>78787878</phone>
    <cellPhone>56565</cellPhone>
    <firstName>firstName</firstName>
    <lastName>lastName</lastName>
    <birthday>2017-09-14T00:00:00+03:00</birthday>
    <email>email@mail.ru</email>
    <address>address</address>
    <hireDate>2017-09-04T00:00:00+03:00</hireDate>
    <fireDate>2017-09-21T00:00:00+03:00</fireDate>
    <cardNumber/>
    <taxpayerIdNumber>111111111111111111</taxpayerIdNumber>
    <snils>455555555555555555</snils>
    <preferredDepartmentCode>1</preferredDepartmentCode>
    <departmentCodes>1</departmentCodes>
    <responsibilityDepartmentCodes>1</responsibilityDepartmentCodes>
    <deleted>false</deleted>
    <supplier>false</supplier>
    <employee>true</employee>
    <client>false</client>
</employee>
```

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<employee>
    <id>4f390698-241d-6ab9-015e-a3d90baa0371</id>
    <code>5</code>
    <name>АPI</name> //имя в системе
    <login/>
    <mainRoleCode>CS1</mainRoleCode>
    <roleCodes>CS1</roleCodes>
    <phone>78787878</phone>
    <cellPhone>56565</cellPhone>
    <firstName>firstName</firstName>
    <lastName>lastName</lastName>
    <birthday>2017-09-14T00:00:00+03:00</birthday>
    <email>email@mail.ru</email>
    <address>address</address>
    <hireDate>2017-09-04T00:00:00+03:00</hireDate>
    <fireDate>2017-09-21T00:00:00+03:00</fireDate>
    <cardNumber/>
    <taxpayerIdNumber>111111111111111111</taxpayerIdNumber>
    <snils>455555555555555555</snils>
    <preferredDepartmentCode>1</preferredDepartmentCode>
    <departmentCodes>1</departmentCodes>
    <responsibilityDepartmentCodes>1</responsibilityDepartmentCodes>
    <deleted>false</deleted>
    <supplier>false</supplier>
    <employee>true</employee>
    <client>false</client>
</employee>
```


## Изменить/добавить сотрудника (по id)

Версия API: 1.0

Версия iiko: 4.0

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/employees/byId/{employeeUUID} |
| --- | --- |

### Что в ответе
 
Если передан новый id, то будет создан новый сотрудник (код возврата 201 Created).
 
Если передан id существующего сотрудника, то произойдет изменение указанных полей (код возврата 200 OK). Поля не указанные в запросе останутся без изменений.
 
Для полного замещения всех полей используйте метод PUT **/employees/byId/{employeeUUID}.**
 
Список пар ключ-значение в поле publicExternalData задается через XML следующим образом:
 
&lt;r&gt;&lt;entry&gt;&lt;key&gt;key\_POST1&lt;/key&gt;&lt;value&gt;value\_POST1&lt;/value&gt;&lt;/entry&gt;&lt;entry&gt;&lt;key&gt;key\_POST2&lt;/key&gt;&lt;value&gt;value\_POST2&lt;/value&gt;&lt;/entry&gt;&lt;/r&gt;.
 
Корневой тег может быть любым, можно задавать &lt;r&gt; для краткости, главное чтобы содержимое соответствовало указанному формату. Сервер "знает", что нужно распарсить это поле в виде XML и положить в виде списка пар ключ-значение в справочник User.
 
Внутри &lt;entry&gt; ключ &lt;key&gt; задавать обязательно, т.е. ключ не может быть null, а вот значение &lt;value&gt; можно не задавать, поскольку оно может быть null, см. employee.xsd ниже.
 ###   **Пример запроса** 
**** https://localhost:8080/resto/api/employees/byId/4f390698-241d-6ab9-015e-a3d90baa0370
 

Код

```
<!--Content-Type: application/x-www-form-urlencoded-->
code=10&name=name&taxpayerIdNumber=000000000000&externalData=<r><entry><key>key_POST1</key><value>value_POST1</value></entry><entry><key>key_POST2</key><value>value_POST2</value></entry></r>
```

Код

```
<!--Content-Type: application/x-www-form-urlencoded-->
code=10&name=name&taxpayerIdNumber=000000000000&externalData=<r><entry><key>key_POST1</key><value>value_POST1</value></entry><entry><key>key_POST2</key><value>value_POST2</value></entry></r>
```

 
**Пример результата вызова API**
 

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<employee>
    <id>4f390698-241d-6ab9-015e-a3d90baa0370</id>
    <code>10</code>
    <name>name</name>
    <login/>
    <mainRoleCode>CS1</mainRoleCode>
    <roleCodes>CS1</roleCodes>
    <phone>7979</phone>
    <cellPhone>00000</cellPhone>
    <firstName>Name</firstName>
    <lastName>Name</lastName>
    <birthday>2017-09-14T00:00:00+03:00</birthday>
    <email>email2@mail.ru</email>
    <address>address</address>
    <hireDate>2017-09-04T00:00:00+03:00</hireDate>
    <fireDate>2017-09-21T00:00:00+03:00</fireDate>
    <cardNumber/>
    <taxpayerIdNumber>000000000000</taxpayerIdNumber>
    <snils>455555555555555555</snils>
    <preferredDepartmentCode>1</preferredDepartmentCode>
    <departmentCodes>1</departmentCodes>
    <responsibilityDepartmentCodes>1</responsibilityDepartmentCodes>
    <deleted>false</deleted>
    <supplier>false</supplier>
    <employee>true</employee>
    <client>false</client>
    <publicExternalData>
        <entry>
            <key>key_POST1</key>
            <value>value_POST1</value>
        </entry>
        <entry>
            <key>key_POST2</key>
            <value>value_POST2</value>
        </entry>
    </publicExternalData>
</employee>
```

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<employee>
    <id>4f390698-241d-6ab9-015e-a3d90baa0370</id>
    <code>10</code>
    <name>name</name>
    <login/>
    <mainRoleCode>CS1</mainRoleCode>
    <roleCodes>CS1</roleCodes>
    <phone>7979</phone>
    <cellPhone>00000</cellPhone>
    <firstName>Name</firstName>
    <lastName>Name</lastName>
    <birthday>2017-09-14T00:00:00+03:00</birthday>
    <email>email2@mail.ru</email>
    <address>address</address>
    <hireDate>2017-09-04T00:00:00+03:00</hireDate>
    <fireDate>2017-09-21T00:00:00+03:00</fireDate>
    <cardNumber/>
    <taxpayerIdNumber>000000000000</taxpayerIdNumber>
    <snils>455555555555555555</snils>
    <preferredDepartmentCode>1</preferredDepartmentCode>
    <departmentCodes>1</departmentCodes>
    <responsibilityDepartmentCodes>1</responsibilityDepartmentCodes>
    <deleted>false</deleted>
    <supplier>false</supplier>
    <employee>true</employee>
    <client>false</client>
    <publicExternalData>
        <entry>
            <key>key_POST1</key>
            <value>value_POST1</value>
        </entry>
        <entry>
            <key>key_POST2</key>
            <value>value_POST2</value>
        </entry>
    </publicExternalData>
</employee>
```


## Удалить сотрудника

Версия API: 1.0

Версия iiko: 4.0

| ![DELETE Request](/resources/Storage/api-documentations/http_request_delete.png) | https://host:port/resto/api/employees/byId/{employeeUUID} |
| --- | --- |

### Что в ответе
 
Пустой ответ если сотрудник удален (или уже был удален).
 
Entity of class User not found by id (employeeUUID), если передан несуществующий guid.
 
### **Пример запроса**

https://localhost:8080/resto/api/employees/byId/4f390698-241d-6ab9-015e-a3d90baa0370

## Описание сущностей для представления в формате XML (XSD-схема)
[+] [Сотрудник](javascript:void%280%29)
 [-] [Сотрудник](javascript:void%280%29)
 
```
 %%CH%PRE10%%%%CH%PRE11%%
```
