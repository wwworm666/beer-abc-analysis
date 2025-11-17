# Rabota S Postavschikami

*Generated from PDF: rabota-s-postavschikami.pdf*

*Total pages: 6*

---


## Page 1

API Documentation Page1 of 6
1. Работа с поставщиками
Список поставщиков
Версияiiko: 3.9
https://host:port/resto/api/suppliers
Параметры запроса
Название Значение Версия Описание
Номерревизии,начинаяскоторойнеобходимоотфильтроватьсущности.
число, номер Невключающийсамуревизию,т.е.ревизияобъекта>revisionFrom.
revisionFrom ревизии с6.4
Поумолчанию(неревизионныйзапрос)revisionFrom=-1
Что в ответе
Список всехпоставщиков.Структура employees
Пример запроса
https://localhost:8080/resto/api/suppliers?key=52cf1990-5a4c-
b086-538d-e06607c17d16
Поиск поставщика
Версияiiko: 3.9
https://host:port/resto/api/suppliers/search
Параметры запроса
Поиск поid поставщика не производится.
Возможнопроизвестипоиск последующим полям:
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Версия |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |  |  |  |

| revisionFrom |  |  | число, номер
ревизии |  |  | с6.4 |  |  | Номерревизии,начинаяскоторойнеобходимоотфильтроватьсущности.
Невключающийсамуревизию,т.е.ревизияобъекта>revisionFrom.
Поумолчанию(неревизионныйзапрос)revisionFrom=-1 |  |  |



### Table:

| https://localhost:8080/resto/api/suppliers?key=52cf1990-5a4c- |

|---|

| b086-538d-e06607c17d16 |


---


## Page 2

API Documentation Page2 of 6
Название Описание
name поле Имявсистеме
code поле Таб.номер/Код
phone поле Телефон
cellPhone поле Мобильныйтелефон
firstName поле Имя
middleName поле Отчество
lastName поле Фамилия
email поле e-mail
cardNumber поле Номеркарты(вкладка Дополнительные сведения)
taxpayerIdNumber поле ИНН(вкладка Юр.лицо)
Что в ответе
Список найденныхпоставщиков. Структура employees (см.XSDСотрудники)
Пример запроса
https://localhost:8080/resto/api/suppliers/search?key=9a02e96c-
273a-ef74-9977-0a0005630317&name=ppl&code=3
Прайс-лист поставщика
Версияiiko: 3.9
https://host:port/resto/api/suppliers/{code}/pricelist
Параметры запроса
Название Значение Описание
date DD.MM.YYYY Дата начала действияпрайс-листа,необязательный.Если
параметрне указан,возвращаетсяпоследнийпрайс-лист.
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |

|---|---|---|---|

|  | Название |  | Описание |

|  |  |  |  |

|  |  |  |  |

| name |  |  | поле Имявсистеме |

| code |  |  | поле Таб.номер/Код |

| phone |  |  | поле Телефон |

| cellPhone |  |  | поле Мобильныйтелефон |

| firstName |  |  | поле Имя |

| middleName |  |  | поле Отчество |

| lastName |  |  | поле Фамилия |

| email |  |  | поле e-mail |

| cardNumber |  |  | поле Номеркарты(вкладка Дополнительные сведения) |

| taxpayerIdNumber |  |  | поле ИНН(вкладка Юр.лицо) |



### Table:

| https://localhost:8080/resto/api/suppliers/search?key=9a02e96c- |

|---|

| 273a-ef74-9977-0a0005630317&name=ppl&code=3 |



### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| date |  |  | DD.MM.YYYY |  |  | Дата начала действияпрайс-листа,необязательный.Если
параметрне указан,возвращаетсяпоследнийпрайс-лист. |  |  |


---


## Page 3

API Documentation Page3 of 6
Что в ответе
Структура supplierPriceListItemDto (см.XSDПрайс-лист)
Пример запроса
https://localhost:8080/resto/api/suppliers/3/pricelist?key=695173
d1-a241-7261-d191-6d381a1cc851
[+] XSDПоставщик
[-] XSDПоставщик
Copy Code
XML
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="employee" type="employee"/>
<xs:complexType name="employee">
<xs:sequence>
<xs:element name="id" type="xs:string" minOccurs="1"/>
<!-- Табельный номер сотрудника. Пуст у системных учетных
записей. -->
<xs:element name="code" type="xs:string" minOccurs="1"/>
<xs:element name="name" type="xs:string" minOccurs="1"/>
<!-- Логин для входа в бекофис -->
<xs:element name="login" type="xs:string" minOccurs="0"/>
<!-- Пароль для входа в бекофис. Доступен только на
изменение, не отображается. -->
<xs:element name="password" type="xs:string" minOccurs="0"/>
<!--
Основная должность сотрудника.
Входит в roleCodes (кроме системных учетных записей, у них
не заполнено roleCodes).
-->
<xs:element name="mainRoleCode" type="xs:string"
minOccurs="0"/>
<xs:element name="roleCodes" type="xs:string"
nillable="true" minOccurs="0" maxOccurs="unbounded"/>
<!-- Справочная информация -->
<xs:element name="phone" type="xs:string" minOccurs="0"/>
<xs:element name="cellPhone" type="xs:string"
minOccurs="0"/>
<xs:element name="firstName" type="xs:string"
minOccurs="0"/>
<xs:element name="middleName" type="xs:string"
minOccurs="0"/>
Allrightsreserved © CompanyInc., 2023


### Table:

| https://localhost:8080/resto/api/suppliers/3/pricelist?key=695173 |  |

|---|---|

| d1-a241-7261-d191-6d381a1cc851 |  |



### Table:

| Copy Code |  |  |

|---|---|---|

|  | XML |  |

|  |  |  |

|  |  |  |

| <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="employee" type="employee"/>
<xs:complexType name="employee">
<xs:sequence>
<xs:element name="id" type="xs:string" minOccurs="1"/>
<!-- Табельный номер сотрудника. Пуст у системных учетных
записей. -->
<xs:element name="code" type="xs:string" minOccurs="1"/>
<xs:element name="name" type="xs:string" minOccurs="1"/>
<!-- Логин для входа в бекофис -->
<xs:element name="login" type="xs:string" minOccurs="0"/>
<!-- Пароль для входа в бекофис. Доступен только на
изменение, не отображается. -->
<xs:element name="password" type="xs:string" minOccurs="0"/>
<!--
Основная должность сотрудника.
Входит в roleCodes (кроме системных учетных записей, у них
не заполнено roleCodes).
-->
<xs:element name="mainRoleCode" type="xs:string"
minOccurs="0"/>
<xs:element name="roleCodes" type="xs:string"
nillable="true" minOccurs="0" maxOccurs="unbounded"/>
<!-- Справочная информация -->
<xs:element name="phone" type="xs:string" minOccurs="0"/>
<xs:element name="cellPhone" type="xs:string"
minOccurs="0"/>
<xs:element name="firstName" type="xs:string"
minOccurs="0"/>
<xs:element name="middleName" type="xs:string"
minOccurs="0"/> |  |  |



### Table:

| <?xml version="1.0" encoding="UTF-8" standalone="yes"?> |

|---|

| <xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema"> |



### Table:

| <xs:complexType name="employee"> |

|---|

| <xs:sequence> |

| <xs:element name="id" type="xs:string" minOccurs="1"/> |

| <!-- Табельный номер сотрудника. Пуст у системных учетных |

| записей. --> |

| <xs:element name="code" type="xs:string" minOccurs="1"/> |

| <xs:element name="name" type="xs:string" minOccurs="1"/> |

| <!-- Логин для входа в бекофис --> |

| <xs:element name="login" type="xs:string" minOccurs="0"/> |

| <!-- Пароль для входа в бекофис. Доступен только на |

| изменение, не отображается. --> |

| <xs:element name="password" type="xs:string" minOccurs="0"/> |



### Table:

| <!-- |

|---|

| Основная должность сотрудника. |

| Входит в roleCodes (кроме системных учетных записей, у них |

| не заполнено roleCodes). |

| --> |

| <xs:element name="mainRoleCode" type="xs:string" |

| minOccurs="0"/> |

| <xs:element name="roleCodes" type="xs:string" |

| nillable="true" minOccurs="0" maxOccurs="unbounded"/> |

| <!-- Справочная информация --> |

| <xs:element name="phone" type="xs:string" minOccurs="0"/> |

| <xs:element name="cellPhone" type="xs:string" |

| minOccurs="0"/> |

| <xs:element name="firstName" type="xs:string" |

| minOccurs="0"/> |

| <xs:element name="middleName" type="xs:string" |

| minOccurs="0"/> |


---


## Page 4

API Documentation Page4 of 6
<xs:element name="lastName" type="xs:string" minOccurs="0"/>
<xs:element name="birthday" type="xs:dateTime"
minOccurs="0"/>
<xs:element name="email" type="xs:string" minOccurs="0"/>
<xs:element name="address" type="xs:string" minOccurs="0"/>
<xs:element name="hireDate" type="xs:string" minOccurs="0"/>
<xs:element name="hireDocumentNumber" type="xs:string"
minOccurs="0"/>
<!--
Дата увольнения.
@since 5.4
-->
<xs:element name="fireDate" type="xs:date" nillable="true"
minOccurs="0"/>
<xs:element name="note" type="xs:string" minOccurs="0"/>
<!-- Slip карты сотрудника -->
<xs:element name="cardNumber" type="xs:string"
minOccurs="0"/>
<!-- Pin-код для входа в iikoFront. Доступен только на
изменение, не отображается. -->
<xs:element name="pinCode" type="xs:string" minOccurs="0"/>
<!-- ИНН -->
<xs:element name="taxpayerIdNumber" type="xs:string"
minOccurs="0"/>
<!--
СНИЛС.
@since 5.4
-->
<xs:element name="snils" type="xs:string" nillable="true"
minOccurs="0"/>
<!--
Global Location Number для поставщиков
@since 6.0
-->
<xs:element name="gln" type="xs:string" minOccurs="0"/>
<xs:element name="activationDate" type="xs:dateTime"
minOccurs="0"/>
<xs:element name="deactivationDate" type="xs:dateTime"
minOccurs="0"/>
<!--
Подразделение (одно из departmentCodes), в котором
сотруднику назначаются смены в первую очередь.
@since 5.0
-->
<xs:element name="preferredDepartmentCode" type="xs:string"
minOccurs="0"/>
<!--
Назначенные подразделения.
Если null - сотруднику назначены все подразделения
(существующие и будущие).
-->
<xs:element name="departmentCodes" type="xs:string"
nillable="true" minOccurs="0"
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <xs:element name="lastName" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="birthday" type="xs:dateTime" |

|  | minOccurs="0"/> |

|  | <xs:element name="email" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="address" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="hireDate" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="hireDocumentNumber" type="xs:string" |

|  | minOccurs="0"/> |

|  | <!-- |

|  | Дата увольнения. |

|  | @since 5.4 |

|  | --> |

|  | <xs:element name="fireDate" type="xs:date" nillable="true" |

|  | minOccurs="0"/> |

|  | <xs:element name="note" type="xs:string" minOccurs="0"/> |

|  | <!-- Slip карты сотрудника --> |

|  | <xs:element name="cardNumber" type="xs:string" |

|  | minOccurs="0"/> |

|  | <!-- Pin-код для входа в iikoFront. Доступен только на |

|  | изменение, не отображается. --> |

|  | <xs:element name="pinCode" type="xs:string" minOccurs="0"/> |

|  | <!-- ИНН --> |

|  | <xs:element name="taxpayerIdNumber" type="xs:string" |

|  | minOccurs="0"/> |

|  | <!-- |

|  | СНИЛС. |

|  | @since 5.4 |

|  | --> |

|  | <xs:element name="snils" type="xs:string" nillable="true" |

|  | minOccurs="0"/> |

|  | <!-- |

|  | Global Location Number для поставщиков |

|  | @since 6.0 |

|  | --> |

|  | <xs:element name="gln" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="activationDate" type="xs:dateTime" |

|  | minOccurs="0"/> |

|  | <xs:element name="deactivationDate" type="xs:dateTime" |

|  | minOccurs="0"/> |

|  | <!-- |

|  | Подразделение (одно из departmentCodes), в котором |

|  | сотруднику назначаются смены в первую очередь. |

|  | @since 5.0 |

|  | --> |

|  | <xs:element name="preferredDepartmentCode" type="xs:string" |

|  | minOccurs="0"/> |

|  | <!-- |

|  | Назначенные подразделения. |

|  | Если null - сотруднику назначены все подразделения |

|  | (существующие и будущие). |

|  | --> |

|  | <xs:element name="departmentCodes" type="xs:string" |

|  | nillable="true" minOccurs="0" |


---


## Page 5

API Documentation Page5 of 6
maxOccurs="unbounded"/>
<!--
Подразделения, в которых сотрудник является ответственным.
Если null - сотруднику является ответственным во всех
существующих и будущих подразделениях.
-->
<xs:element name="responsibilityDepartmentCodes"
type="xs:string"
nillable="true" minOccurs="0"
maxOccurs="unbounded"/>
<xs:element name="deleted" type="xs:string" minOccurs="0"/>
<xs:element name="supplier" type="xs:string" minOccurs="0"/>
<xs:element name="employee" type="xs:string" minOccurs="0"/>
<xs:element name="client" type="xs:string" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
</xs:schema>
[+] XSDПрайс-лист
[-] XSDПрайс-лист
Copy Code
XML
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="supplierPriceListItemDto"
type="supplierPriceListItemDto"/>
<!-- Прайс-лист -->
<xs:complexType name="supplierPriceListItemDto">
<xs:sequence>
<!-- Товар у нас (guid) -->
<xs:element name="nativeProduct" type="xs:string" minOccurs="0"/>
<!-- Код товара у нас -->
<xs:element name="nativeProductCode" type="xs:string"
minOccurs="0"/>
<!-- Артикул товара у нас -->
<xs:element name="nativeProductNum" type="xs:string"
minOccurs="0"/>
<!-- Название товара у нас -->
<xs:element name="nativeProductName" type="xs:string"
minOccurs="0"/>
<!-- Товар у поставщика (guid) -->
<xs:element name="supplierProduct" type="xs:string"
minOccurs="0"/>
<!-- Код товара у поставщика -->
<xs:element name="supplierProductCode" type="xs:string"
minOccurs="0"/>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |

|---|

| maxOccurs="unbounded"/>
<!--
Подразделения, в которых сотрудник является ответственным.
Если null - сотруднику является ответственным во всех
существующих и будущих подразделениях.
-->
<xs:element name="responsibilityDepartmentCodes"
type="xs:string"
nillable="true" minOccurs="0"
maxOccurs="unbounded"/>
<xs:element name="deleted" type="xs:string" minOccurs="0"/>
<xs:element name="supplier" type="xs:string" minOccurs="0"/>
<xs:element name="employee" type="xs:string" minOccurs="0"/>
<xs:element name="client" type="xs:string" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
</xs:schema> |

|  |



### Table:

| maxOccurs="unbounded"/> |

|---|

| <!-- |

| Подразделения, в которых сотрудник является ответственным. |

| Если null - сотруднику является ответственным во всех |

| существующих и будущих подразделениях. |

| --> |

| <xs:element name="responsibilityDepartmentCodes" |

| type="xs:string" |

| nillable="true" minOccurs="0" |

| maxOccurs="unbounded"/> |



### Table:

| <xs:element name="deleted" type="xs:string" minOccurs="0"/> |

|---|

| <xs:element name="supplier" type="xs:string" minOccurs="0"/> |

| <xs:element name="employee" type="xs:string" minOccurs="0"/> |

| <xs:element name="client" type="xs:string" minOccurs="0"/> |

| </xs:sequence> |

| </xs:complexType> |

| </xs:schema> |



### Table:

| Copy Code |  |  |

|---|---|---|

|  | XML |  |

|  |  |  |

|  |  |  |

|  | <?xml version="1.0" encoding="UTF-8" standalone="yes"?> |  |

|  | <xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema"> |  |

|  | <xs:element name="supplierPriceListItemDto" |  |

|  | type="supplierPriceListItemDto"/> |  |

|  | <!-- Прайс-лист --> |  |

|  | <xs:complexType name="supplierPriceListItemDto"> |  |

|  | <xs:sequence> |  |

|  | <!-- Товар у нас (guid) --> |  |

|  | <xs:element name="nativeProduct" type="xs:string" minOccurs="0"/> |  |

|  | <!-- Код товара у нас --> |  |

|  | <xs:element name="nativeProductCode" type="xs:string" |  |

|  | minOccurs="0"/> |  |

|  | <!-- Артикул товара у нас --> |  |

|  | <xs:element name="nativeProductNum" type="xs:string" |  |

|  | minOccurs="0"/> |  |

|  | <!-- Название товара у нас --> |  |

|  | <xs:element name="nativeProductName" type="xs:string" |  |

|  | minOccurs="0"/> |  |

|  | <!-- Товар у поставщика (guid) --> |  |

|  | <xs:element name="supplierProduct" type="xs:string" |  |

|  | minOccurs="0"/> |  |

|  | <!-- Код товара у поставщика --> |  |

|  | <xs:element name="supplierProductCode" type="xs:string" |  |

|  | minOccurs="0"/> |  |


---


## Page 6

API Documentation Page6 of 6
<!-- Артикул товара у поставщика -->
<xs:element name="supplierProductNum" type="xs:string"
minOccurs="0"/>
<!-- Название товара у поставщика -->
<xs:element name="supplierProductName" type="xs:string"
minOccurs="0"/>
<!-- Стоимость товара -->
<xs:element name="costPrice" type="xs:decimal" minOccurs="0"/>
<!-- Допустимое отклонение от цены (%) -->
<xs:element name="allowablePriceDeviation" type="xs:decimal"
minOccurs="0"/>
<!-- Фасовка -->
<xs:element name="container" type="containerDto" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
<!-- Фасовка -->
<xs:complexType name="containerDto">
<xs:sequence>
<!-- id фасовки (guid) -->
<xs:element name="id" type="xs:string" minOccurs="0"/>
<!-- Название фасовки -->
<xs:element name="name" type="xs:string" minOccurs="0"/>
<!-- Количество базовых единиц измерения товара в фасовке -->
<xs:element name="count" type="xs:decimal" minOccurs="0"/>
<!-- Вес тары (если товар продается на вес) -->
<xs:element name="containerWeight" type="xs:decimal"
minOccurs="0"/>
<!-- Вес с тарой (если товар продается на вес) -->
<xs:element name="fullContainerWeight" type="xs:decimal"
minOccurs="0"/>
<!-- Обратный пересчет (true/false) -->
<xs:element name="backwardRecalculation" type="xs:boolean"
minOccurs="0"/>
<!-- Признак удаления (true/false) -->
<xs:element name="deleted" type="xs:boolean" minOccurs="0"/>
<!-- Использовать во фронте (true/false) -->
<xs:element name="useInFront" type="xs:boolean" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
</xs:schema>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <!-- Артикул товара у поставщика --> |

|  | <xs:element name="supplierProductNum" type="xs:string" |

|  | minOccurs="0"/> |

|  | <!-- Название товара у поставщика --> |

|  | <xs:element name="supplierProductName" type="xs:string" |

|  | minOccurs="0"/> |

|  | <!-- Стоимость товара --> |

|  | <xs:element name="costPrice" type="xs:decimal" minOccurs="0"/> |

|  | <!-- Допустимое отклонение от цены (%) --> |

|  | <xs:element name="allowablePriceDeviation" type="xs:decimal" |

|  | minOccurs="0"/> |

|  | <!-- Фасовка --> |

|  | <xs:element name="container" type="containerDto" minOccurs="0"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | <!-- Фасовка --> |

|  | <xs:complexType name="containerDto"> |

|  | <xs:sequence> |

|  | <!-- id фасовки (guid) --> |

|  | <xs:element name="id" type="xs:string" minOccurs="0"/> |

|  | <!-- Название фасовки --> |

|  | <xs:element name="name" type="xs:string" minOccurs="0"/> |

|  | <!-- Количество базовых единиц измерения товара в фасовке --> |

|  | <xs:element name="count" type="xs:decimal" minOccurs="0"/> |

|  | <!-- Вес тары (если товар продается на вес) --> |

|  | <xs:element name="containerWeight" type="xs:decimal" |

|  | minOccurs="0"/> |

|  | <!-- Вес с тарой (если товар продается на вес) --> |

|  | <xs:element name="fullContainerWeight" type="xs:decimal" |

|  | minOccurs="0"/> |

|  | <!-- Обратный пересчет (true/false) --> |

|  | <xs:element name="backwardRecalculation" type="xs:boolean" |

|  | minOccurs="0"/> |

|  | <!-- Признак удаления (true/false) --> |

|  | <xs:element name="deleted" type="xs:boolean" minOccurs="0"/> |

|  | <!-- Использовать во фронте (true/false) --> |

|  | <xs:element name="useInFront" type="xs:boolean" minOccurs="0"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | </xs:schema> |

|  |  |


---
