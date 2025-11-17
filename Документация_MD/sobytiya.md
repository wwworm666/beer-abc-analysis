# Sobytiya

*Generated from PDF: sobytiya.pdf*

*Total pages: 10*

---


## Page 1

API Documentation Page1 of 10
1. События
Доступ
ЧтобыпользоватьсяAPI событий:
· В лицензии должен присутствовать модуль 2200 (прочие названия:
API_EVENTS(2200),'iikoAPI (ApiEvents)').
· У пользователя, под чьим именем осуществляется вход, должно быть право B_VTJ
"Просматриватьжурнал событий".
Список событий
Версия iiko: 3.9
https://host:port/resto/api/events
Параметры запроса
Название Значение Описание
from_time yyyy-MM- Времяскоторогозапрашиваютсясобытия,вформатеISO: yyyy-MM-
ddTHH:mm:ss.SSS ddTHH:mm:ss.SSS,поумолчанию–началотекущихсуток
to_time yyyy-MM- Времяпокоторое(невключительно)запрашиваютсясобытия вформате
ddTHH:mm:ss.SSS ISO: yyyy-MM-ddTHH:mm:ss.SSS,,поумолчаниюграницанеустановлена
from_rev Число Ревизия,скоторойзапрашиваютсясобытия,число.Каждыйответсодержит
тэгrevision,значениекоторогосоответствуетревизии,покоторую
включительноотданысобытия;приновыхзапросахследуетиспользовать
revision+1(revisionизпредыдущегоответа)дляполучениятольконовых
событий.Вштатномрежимеодноитожесобытиеповторносразными
ревизияминеприходит,однакотакойгарантиинедаётся.ID(UUID)события
уникален,можетиспользоватьсявкачествеключа.
Что в ответе
Список событий в формате eventsList (см. XSD Список событий).
Поле <type> использует значение поля <id> структуры groupsList.
Примеры запроса
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|---|---|

|  | Название |  |  |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  | yyyy-MM-
ddTHH:mm:ss.SSS |  |  | Времяскоторогозапрашиваютсясобытия,вформатеISO: yyyy-MM-
ddTHH:mm:ss.SSS,поумолчанию–началотекущихсуток |  |  |

|  | from_time |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  | yyyy-MM-
ddTHH:mm:ss.SSS |  |  | Времяпокоторое(невключительно)запрашиваютсясобытия вформате
ISO: yyyy-MM-ddTHH:mm:ss.SSS,,поумолчаниюграницанеустановлена |  |  |

|  |  | to_time |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  | Число |  |  | Ревизия,скоторойзапрашиваютсясобытия,число.Каждыйответсодержит
тэгrevision,значениекоторогосоответствуетревизии,покоторую
включительноотданысобытия;приновыхзапросахследуетиспользовать
revision+1(revisionизпредыдущегоответа)дляполучениятольконовых
событий.Вштатномрежимеодноитожесобытиеповторносразными
ревизияминеприходит,однакотакойгарантиинедаётся.ID(UUID)события
уникален,можетиспользоватьсявкачествеключа. |  |  |

|  |  | from_rev |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |


---


## Page 2

API Documentation Page2 of 10
https://localhost:8080/resto/api/events?key=39c4c88f-4758-64e3-
3b4c-ad6f589c0dc2
https://localhost:8080/resto/api/events?key=46dcaad5-b139-b976-
88a2-1cf9b567195c&from_time=2014-06-16T00:00:00.000&to_time=2014-
06-18T23:59:59.999
https://localhost:8181/resto/api/events?key=3192935b-26f7-4d61-
b11d-58feb1a7d69b&from_rev=10016007
Список событий по фильтру событий и
номеру заказа
Версия iiko: 5.0
https://host:port/resto/api/events
Тело запроса
Список id событий,покоторым производитсяфильтрация(application/xml).
CopyCode
XML
<eventsRequestData>
<events>
<event>orderCancelPrecheque</event>
<event>orderPaid</event>
</events>
<orderNums>
<orderNum>175658</orderNum>
</orderNums>
</eventsRequestData>
Что в ответе
Список событийвформате eventsList (см.XSDСписок событий).
Поле <type> использует значение поля <id> структуры groupsList.
Сохранение событий
Версия iiko: 8.0.3
Allrightsreserved © CompanyInc., 2023


### Table:

| https://localhost:8080/resto/api/events?key=39c4c88f-4758-64e3- |

|---|

| 3b4c-ad6f589c0dc2 |



### Table:

| https://localhost:8080/resto/api/events?key=46dcaad5-b139-b976- |

|---|

| 88a2-1cf9b567195c&from_time=2014-06-16T00:00:00.000&to_time=2014- |

| 06-18T23:59:59.999 |



### Table:

| https://localhost:8181/resto/api/events?key=3192935b-26f7-4d61- |

|---|

| b11d-58feb1a7d69b&from_rev=10016007 |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | XML |  |

|  |  |  |

|  |  |  |

|  | <eventsRequestData> |  |

|  | <events> |  |

|  | <event>orderCancelPrecheque</event> |  |

|  | <event>orderPaid</event> |  |

|  | </events> |  |

|  | <orderNums> |  |

|  | <orderNum>175658</orderNum> |  |

|  | </orderNums> |  |

|  | </eventsRequestData> |  |

|  |  |  |


---


## Page 3

API Documentation Page3 of 10
https://host:port/resto/api/events/add
Тело запроса
Список событий в формате eventsList.
CopyCode
Код
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
Allrightsreserved © CompanyInc., 2023


### Table:

| CopyCode |  |  |

|---|---|---|

|  | Код |  |

|  |  |  |

|  |  |  |

|  | <?xml version="1.0" encoding="UTF-8" standalone="yes"?> |  |

|  | <eventsList> |  |

|  | <event> |  |

|  | <date>2021-12-31T19:24:29.033+03:00</date> |  |

|  | <type>banana</type> |  |

|  | <departmentId>2</departmentId> |  |

|  | <attribute> |  |

|  | <name>userName</name> |  |

|  | <value>Администратор</value> |  |

|  | <type>java.lang.String</type> |  |

|  | </attribute> |  |

|  | <attribute> |  |

|  | <name>user</name> |  |

|  | <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value> |  |

|  | <type>User</type> |  |

|  | </attribute> |  |

|  | <attribute> |  |

|  | <name>success</name> |  |

|  | <value>1.000000000</value> |  |

|  | <type>java.lang.Boolean</type> |  |

|  | </attribute> |  |

|  | </event> |  |

|  | <event> |  |

|  | <date>2021-12-31T19:25:29.033+03:00</date> |  |

|  | <type>banana</type> |  |

|  | <departmentId>2</departmentId> |  |

|  | <attribute> |  |

|  | <name>userName</name> |  |

|  | <value>Администратор</value> |  |

|  | <type>java.lang.String</type> |  |

|  | </attribute> |  |

|  | <attribute> |  |

|  | <name>user</name> |  |

|  | <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value> |  |

|  | <type>User</type> |  |

|  | </attribute> |  |

|  | <attribute> |  |

|  | <name>success</name> |  |

|  | <value>1.000000000</value> |  |

|  | <type>java.lang.Boolean</type> |  |

|  | </attribute> |  |


---


## Page 4

API Documentation Page4 of 10
</event>
</eventsList>
Что в ответе
Список событий в формате eventsList.
CopyCode
Код
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
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | </event> |

|  | </eventsList> |

|  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | Код |  |

|  |  |  |

|  |  |  |

|  | <?xml version="1.0" encoding="UTF-8" standalone="yes"?> |  |

|  | <eventsList> |  |

|  | <event> |  |

|  | <id>9a48d9d4-8196-40e7-017e-e94b95b20023</id> |  |

|  | <date>2021-12-31T19:24:29.033+03:00</date> |  |

|  | <type>banana</type> |  |

|  | <departmentId>2</departmentId> |  |

|  | <attribute> |  |

|  | <name>user</name> |  |

|  | <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value> |  |

|  | <type>User</type> |  |

|  | </attribute> |  |

|  | <attribute> |  |

|  | <name>success</name> |  |

|  | <value>1</value> |  |

|  | <type>java.lang.Boolean</type> |  |

|  | </attribute> |  |

|  | <attribute> |  |

|  | <name>userName</name> |  |

|  | <value>Администратор</value> |  |

|  | <type>java.lang.String</type> |  |

|  | </attribute> |  |

|  | </event> |  |

|  | <event> |  |

|  | <id>9a48d9d4-8196-40e7-017e-e94b95b20024</id> |  |

|  | <date>2021-12-31T19:25:29.033+03:00</date> |  |

|  | <type>banana</type> |  |

|  | <departmentId>2</departmentId> |  |

|  | <attribute> |  |

|  | <name>user</name> |  |

|  | <value>c831367e-778f-e80f-18f7-bd0843cd10c6</value> |  |

|  | <type>User</type> |  |

|  | </attribute> |  |

|  | <attribute> |  |

|  | <name>userName</name> |  |

|  | <value>Администратор</value> |  |

|  | <type>java.lang.String</type> |  |


---


## Page 5

API Documentation Page5 of 10
</attribute>
<attribute>
<name>success</name>
<value>1</value>
<type>java.lang.Boolean</type>
</attribute>
</event>
</eventsList>
Описание
Тип события может быть любым (с количеством символов не больше 255), но если
он зарегистрирован в events.xml, то событие должно содержать все атрибуты,
обязательные для данного типа.
У атрибута добавилось поле 'type'. Значения, которые может принимать это поле,
перечислены в таблице. Тип атрибута накладывает ограничения на поле 'value'.
type value
java.lang.Boolean "0"-false,"1"-true
java.lang.String Текст
Дата в формате "yyyy-MM-
java.util.Date
dd'T'HH:mm:ss.SSS"
resto.db.Guid UUID
Наследники java.lang.Number. Примеры: java.lang.Integer,
Число.
java.math.BigDecimal
Наследники resto.db.CachedEntity в простой форме. UUID соответствующего
Примеры: User, Department, Terminal справочника.
Втаблице UserEventAttribute дляполя'value'есть4колонки(valueDate,valueGuid,
valueNumber,valueString) разныхтипов,и,взависимостиот типа атрибута,значение будет
записановоднуиз этихколонок.
Дерево событий
Версия iiko: 3.9
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | </attribute> |

|  | <attribute> |

|  | <name>success</name> |

|  | <value>1</value> |

|  | <type>java.lang.Boolean</type> |

|  | </attribute> |

|  | </event> |

|  | </eventsList> |

|  |  |



### Table:

|  |  |  |  |  |  |

|---|---|---|---|---|---|

|  | type |  |  | value |  |

|  |  |  |  |  |  |

| java.lang.Boolean |  |  | "0"-false,"1"-true |  |  |

| java.lang.String |  |  | Текст |  |  |

| java.util.Date |  |  | Дата в формате "yyyy-MM-
dd'T'HH:mm:ss.SSS" |  |  |

| resto.db.Guid |  |  | UUID |  |  |

| Наследники java.lang.Number. Примеры: java.lang.Integer,
java.math.BigDecimal |  |  | Число. |  |  |

| Наследники resto.db.CachedEntity в простой форме.
Примеры: User, Department, Terminal |  |  | UUID соответствующего
справочника. |  |  |


---


## Page 6

API Documentation Page6 of 10
https://host:port/resto/api/events/metadata
Что в ответе
Дерево событий в формате groupsList (см. XSD Дерево событий).
Возвращает дерево событий (аналог иерархии событий журнала событий в
iikoOffice). Поле <id> используется как значение поля<type> структуры eventList.
Также структура определяет список атрибутов, специфичных для данного события.
Пример запроса
https://localhost:8080/resto/api/events/metadata?key=43d272ed-
cfb1-64b1-9842-f3078cd69172
Дерево событий по фильтру
Версия iiko: 5.0
https://host:port/resto/api/events/metadata
Тело запроса
Списокidсобытий,покоторымпроизводитсяфильтрация(application/xml).
CopyCode
XML
<eventsRequestData>
<events>
<event>orderOpened</event>
</events>
</eventsRequestData>
Что в ответе
Дерево событий в формате groupsList (см. XSD Дерево событий).
Возвращает дерево событий (аналог иерархии событий журнала событий в
iikoOffice). Поле <id> используется как значение поля<type> структуры eventList.
Также структура определяет список атрибутов, специфичных для данного
события.
Allrightsreserved © CompanyInc., 2023


### Table:

| https://localhost:8080/resto/api/events/metadata?key=43d272ed- |

|---|

| cfb1-64b1-9842-f3078cd69172 |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | XML |  |

|  |  |  |

|  |  |  |

|  | <eventsRequestData> |  |

|  | <events> |  |

|  | <event>orderOpened</event> |  |

|  | </events> |  |

|  | </eventsRequestData> |  |

|  |  |  |


---


## Page 7

API Documentation Page7 of 10
Пример запроса
https://localhost:8080/resto/api/events/metadata?key=933a2e7c-
be36-d2ee-0b96-9509e6f24fa1
Информация о кассовых сменах
Версия iiko: 5.0
https://host:port/resto/api/events/sessions
Параметры запроса
Название Значение Описание
from_time yyyy-MM- Времяскоторогозапрашиваютсяданныепокассовымсменам,в
ddTHH:mm:ss.SSS форматеISO: yyyy-MM-ddTHH:mm:ss.SSS.
to_time yyyy-MM- Времяпокоторое(невключительно)запрашиваются данныепо
ddTHH:mm:ss.SSS кассовымсменам вформатеISO: yyyy-MM-ddTHH:mm:ss.SSS,
Что в ответе
Информация о кассовых сменах. Время открытия, время закрытия, менеджер,
номер смены, номер кассы, опер. день.
Пример вызова
https://localhost:8080/resto/api/events/sessions?key=43d272ed-
cfb1-64b1-9842-f3078cd69172&from_time=2015-03-
28T00:00:00.000&to_time=2015-03-28T00:00:00.000
Еслиработаетепоревизии,ненужно(нельзя)указыватьto_time
[+] XSDДеревособытий
[-] XSDДеревособытий
Copy Code
XML
<!-- Схема описания дерева событий журнала событий -->
<!-- Дерево выдается в качетсве линейной структуры -->
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|---|---|

| Название |  |  |  |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  | yyyy-MM-
ddTHH:mm:ss.SSS |  |  | Времяскоторогозапрашиваютсяданныепокассовымсменам,в
форматеISO: yyyy-MM-ddTHH:mm:ss.SSS. |  |  |

| from_time |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  | yyyy-MM-
ddTHH:mm:ss.SSS |  |  | Времяпокоторое(невключительно)запрашиваются данныепо
кассовымсменам вформатеISO: yyyy-MM-ddTHH:mm:ss.SSS, |  |  |

|  | to_time |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |



### Table:

|  | Еслиработаетепоревизии,ненужно(нельзя)указыватьto_time |

|---|---|

|  |  |

|  |  |



### Table:

| Copy Code |  |  |

|---|---|---|

| XML |  |  |

|  |  |  |

|  |  |  |

| <!-- Схема описания дерева событий журнала событий -->
<!-- Дерево выдается в качетсве линейной структуры --> |  |  |


---


## Page 8

API Documentation Page8 of 10
<!-- групп событий. Информация об иерархии групп -->
<!-- внутри древовидной структуры теряется -->
<!-- Кроме этого, теряется информация об обязательности и
необязательности атрибутов событий -->
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="group" type="group"/>
<xs:element name="type" type="type"/>
<xs:element name="attribute" type="attribute"/>
<xs:element name="groupsList" type="groupsList"/>
<!-- Дерево событий состоит из списка групп -->
<xs:complexType name="groupsList">
<xs:sequence>
<xs:element ref="group" minOccurs="0" maxOccurs="unbounded"/>
</xs:sequence>
</xs:complexType>
<!-- Элементы этого списка - группы событий -->
<xs:complexType name="group">
<xs:sequence>
<!-- Идентификатор группы = resto.event.EventGroupMetadata.id )-->
<xs:element name="id" type="xs:string" minOccurs="0"/>
<!-- Имя группы = resto.event.EventGroupMetadata.name -->
<xs:element name="name" type="xs:string" minOccurs="0"/>
<!-- Список событий, входящих в данную группу-->
<xs:element ref="type" minOccurs="0" maxOccurs="unbounded"/>
</xs:sequence>
</xs:complexType>
<!-- Событие Журнала Событий -->
<xs:complexType name="type">
<!-- Каждое событие состоит из набора -->
<xs:sequence>
<!-- Список Атрибутов события -->
<xs:element name="attribute" type="attribute" minOccurs="0"
maxOccurs="unbounded"/>
<!-- Идентификатор события = resto.event.EventTypeMetadata.id -->
<xs:element name="id" type="xs:string" minOccurs="0"/>
<!-- Имя события = resto.event.EventTypeMetadata.name -->
<xs:element name="name" type="xs:string" minOccurs="0"/>
<!-- Важность события (число) (0 - Низкая, 1 - Средняя, 2 -
Высокая) -->
<xs:element name="severity" type="xs:string" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
<!-- Атрибут события -->
<xs:complexType name="attribute">
<xs:sequence>
<!-- Идентификатор обязательного аттрибута =
resto.event.EventAttributeMetadata.id -->
<xs:element name="id" type="xs:string" minOccurs="0"/>
<!-- Имя обязательного аттрибута =
resto.event.EventAttributeMetadata.name -->
<xs:element name="name" type="xs:string" minOccurs="0"/>
</xs:sequence>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <!-- групп событий. Информация об иерархии групп --> |

|  | <!-- внутри древовидной структуры теряется --> |

|  | <!-- Кроме этого, теряется информация об обязательности и |

|  | необязательности атрибутов событий --> |

|  | <?xml version="1.0" encoding="UTF-8" standalone="yes"?> |

|  | <xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema"> |

|  | <xs:element name="group" type="group"/> |

|  | <xs:element name="type" type="type"/> |

|  | <xs:element name="attribute" type="attribute"/> |

|  | <xs:element name="groupsList" type="groupsList"/> |

|  | <!-- Дерево событий состоит из списка групп --> |

|  | <xs:complexType name="groupsList"> |

|  | <xs:sequence> |

|  | <xs:element ref="group" minOccurs="0" maxOccurs="unbounded"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | <!-- Элементы этого списка - группы событий --> |

|  | <xs:complexType name="group"> |

|  | <xs:sequence> |

|  | <!-- Идентификатор группы = resto.event.EventGroupMetadata.id )--> |

|  | <xs:element name="id" type="xs:string" minOccurs="0"/> |

|  | <!-- Имя группы = resto.event.EventGroupMetadata.name --> |

|  | <xs:element name="name" type="xs:string" minOccurs="0"/> |

|  | <!-- Список событий, входящих в данную группу--> |

|  | <xs:element ref="type" minOccurs="0" maxOccurs="unbounded"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | <!-- Событие Журнала Событий --> |

|  | <xs:complexType name="type"> |

|  | <!-- Каждое событие состоит из набора --> |

|  | <xs:sequence> |

|  | <!-- Список Атрибутов события --> |

|  | <xs:element name="attribute" type="attribute" minOccurs="0" |

|  | maxOccurs="unbounded"/> |

|  | <!-- Идентификатор события = resto.event.EventTypeMetadata.id --> |

|  | <xs:element name="id" type="xs:string" minOccurs="0"/> |

|  | <!-- Имя события = resto.event.EventTypeMetadata.name --> |

|  | <xs:element name="name" type="xs:string" minOccurs="0"/> |

|  | <!-- Важность события (число) (0 - Низкая, 1 - Средняя, 2 - |

|  | Высокая) --> |

|  | <xs:element name="severity" type="xs:string" minOccurs="0"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | <!-- Атрибут события --> |

|  | <xs:complexType name="attribute"> |

|  | <xs:sequence> |

|  | <!-- Идентификатор обязательного аттрибута = |

|  | resto.event.EventAttributeMetadata.id --> |

|  | <xs:element name="id" type="xs:string" minOccurs="0"/> |

|  | <!-- Имя обязательного аттрибута = |

|  | resto.event.EventAttributeMetadata.name --> |

|  | <xs:element name="name" type="xs:string" minOccurs="0"/> |

|  | </xs:sequence> |


---


## Page 9

API Documentation Page9 of 10
</xs:complexType>
</xs:schema>
[+] XSDСписок событий
[-] XSDСписок событий
Copy Code
XML
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="event" type="event"/>
<xs:element name="eventAttribute" type="eventAttribute"/>
<xs:element name="eventsList" type="eventsList"/>
<!-- События -->
<xs:complexType name="eventsList">
<xs:sequence>
<!-- Список событий -->
<xs:element ref="event" minOccurs="0" maxOccurs="unbounded"/>
<!-- Ревизия списка событий -->
<xs:element name="revision" type="xs:int" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
<!-- Событие -->
<xs:complexType name="event">
<xs:sequence>
<!-- Список аттрибутов события -->
<!-- Аттрибуты события могут частично пересекаться с атрибутами
событий, перечисленных в groupsList.group.type.attribute -->
<!-- Некоторые события имеют обязательные атрибуты - по таким
пересеченеи обязательно -->
<xs:element name="attribute" type="eventAttribute" minOccurs="0"
maxOccurs="unbounded"/>
<!-- Дата и время события -->
<xs:element name="date" type="xs:dateTime" minOccurs="0"/>
<!-- id департамента (guid) - для iikoChain -->
<xs:element name="departmentId" type="xs:string" minOccurs="0"/>
<!-- Уникальный идентификатор события (guid) -->
<xs:element name="id" type="xs:string" minOccurs="0"/>
<!-- Тип события = resto.event.EventTypeMetadata.name =
groupsList.group.type.id -->
<xs:element name="type" type="xs:string" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
<!-- Аттрибут события -->
<xs:complexType name="eventAttribute">
<xs:sequence>
<!-- Имя атрибута -->
<xs:element name="name" type="xs:string" minOccurs="0"/>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | </xs:complexType> |

|  | </xs:schema> |

|  |  |



### Table:

| Copy Code |  |  |

|---|---|---|

|  | XML |  |

|  |  |  |

|  |  |  |

|  | <?xml version="1.0" encoding="UTF-8" standalone="yes"?> |  |

|  | <xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema"> |  |

|  | <xs:element name="event" type="event"/> |  |

|  | <xs:element name="eventAttribute" type="eventAttribute"/> |  |

|  | <xs:element name="eventsList" type="eventsList"/> |  |

|  | <!-- События --> |  |

|  | <xs:complexType name="eventsList"> |  |

|  | <xs:sequence> |  |

|  | <!-- Список событий --> |  |

|  | <xs:element ref="event" minOccurs="0" maxOccurs="unbounded"/> |  |

|  | <!-- Ревизия списка событий --> |  |

|  | <xs:element name="revision" type="xs:int" minOccurs="0"/> |  |

|  | </xs:sequence> |  |

|  | </xs:complexType> |  |

|  | <!-- Событие --> |  |

|  | <xs:complexType name="event"> |  |

|  | <xs:sequence> |  |

|  | <!-- Список аттрибутов события --> |  |

|  | <!-- Аттрибуты события могут частично пересекаться с атрибутами |  |

|  | событий, перечисленных в groupsList.group.type.attribute --> |  |

|  | <!-- Некоторые события имеют обязательные атрибуты - по таким |  |

|  | пересеченеи обязательно --> |  |

|  | <xs:element name="attribute" type="eventAttribute" minOccurs="0" |  |

|  | maxOccurs="unbounded"/> |  |

|  | <!-- Дата и время события --> |  |

|  | <xs:element name="date" type="xs:dateTime" minOccurs="0"/> |  |

|  | <!-- id департамента (guid) - для iikoChain --> |  |

|  | <xs:element name="departmentId" type="xs:string" minOccurs="0"/> |  |

|  | <!-- Уникальный идентификатор события (guid) --> |  |

|  | <xs:element name="id" type="xs:string" minOccurs="0"/> |  |

|  | <!-- Тип события = resto.event.EventTypeMetadata.name = |  |

|  | groupsList.group.type.id --> |  |

|  | <xs:element name="type" type="xs:string" minOccurs="0"/> |  |

|  | </xs:sequence> |  |

|  | </xs:complexType> |  |

|  | <!-- Аттрибут события --> |  |

|  | <xs:complexType name="eventAttribute"> |  |

|  | <xs:sequence> |  |

|  | <!-- Имя атрибута --> |  |

|  | <xs:element name="name" type="xs:string" minOccurs="0"/> |  |


---


## Page 10

API Documentation Page10 of 10
<!-- Значение атрибута -->
<xs:element name="value" type="xs:string" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
</xs:schema>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <!-- Значение атрибута --> |

|  | <xs:element name="value" type="xs:string" minOccurs="0"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | </xs:schema> |

|  |  |


---
