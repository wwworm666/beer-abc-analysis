# Otchety V1

*Generated from PDF: otchety-v1.pdf*

*Total pages: 15*

---


## Page 1

API Documentation Page1 of 15
1. Отчеты
Отчет по складским операциям
Версия iiko: 3.9
https://host:port/resto/api/reports/storeOperations
Параметры запроса
Название Значение Описание
dateFrom DD.MM.YYYY Начальнаядата
dateTo DD.MM.YYYY Конечнаядата
stores GUID Списокскладов,покоторымстроитсяотчет.Еслиnull
илиempty,строитсяповсемскладам.
documentTypes См.раздел"Расшифровки Типыдокументов,которыеследуетвключать.Если
кодовбазовыхтипов- nullилипуст,включаютсявседокументы.
Типыдокументов"
productDetalization Boolean Еслиистина,отчетвключаетинформациюпо
товарам,ноневключаетдату.Еслиложь-отчет
включаеткаждыйдокументоднойстрокойи
заполняетсуммыдокументов
showCostCorrections Boolean Включатьликоррекциисебестоимости.Данная
опцияучитываетсятолькоеслизаданфильтрпо
типамдокументов.Впротивномслучаекоррекции
включаются.
presetId GUID Idпреднастроенногоотчета.Еслиуказан,товсе
настройки,кромедат,игнорируются.
Что в ответе
Структура storeReportItemDto (см. XSD Отчет по складским операциям)
Пример запроса
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| dateFrom |  |  | DD.MM.YYYY |  |  | Начальнаядата |  |  |

| dateTo |  |  | DD.MM.YYYY |  |  | Конечнаядата |  |  |

| stores |  |  | GUID |  |  | Списокскладов,покоторымстроитсяотчет.Еслиnull
илиempty,строитсяповсемскладам. |  |  |

| documentTypes |  |  | См.раздел"Расшифровки
кодовбазовыхтипов-
Типыдокументов" |  |  | Типыдокументов,которыеследуетвключать.Если
nullилипуст,включаютсявседокументы. |  |  |

| productDetalization |  |  | Boolean |  |  | Еслиистина,отчетвключаетинформациюпо
товарам,ноневключаетдату.Еслиложь-отчет
включаеткаждыйдокументоднойстрокойи
заполняетсуммыдокументов |  |  |

| showCostCorrections |  |  | Boolean |  |  | Включатьликоррекциисебестоимости.Данная
опцияучитываетсятолькоеслизаданфильтрпо
типамдокументов.Впротивномслучаекоррекции
включаются. |  |  |

| presetId |  |  | GUID |  |  | Idпреднастроенногоотчета.Еслиуказан,товсе
настройки,кромедат,игнорируются. |  |  |


---


## Page 2

API Documentation Page2 of 15
Параметры передаются явно
https://localhost:8080/resto/api/reports/storeOperations?key=1ac6
b9a3-19a0-7c60-e23b-
124dd70d75da&dateFrom=01.09.2014&dateTo=09.09.2014&productDetaliz
ation=false&showCostCorrections=false&documentTypes=SALES_DOCUMEN
T&documentTypes=INCOMING_INVOICE&stores=1239d270-1bbe-f64f-b7ea-
5f00518ef508&stores=93c5cc1f-4c80-4bea-9100-70053a10e37a
Передается presetId преднастроенного отчета в iikoOffice
https://localhost:8080/resto/api/reports/storeOperations?key=1ac6
b9a3-19a0-7c60-e23b-
124dd70d75da&dateFrom=01.12.2014&dateTo=17.12.2014&presetId=bf888
6b3-a765-6535-37e4-873bce201482
Пресеты отчетов по складским операциям
Версия iiko: 3.9
https://host:port/resto/api/reports/storeReportPresets
Что в ответе
Структура storeReportPresets (см. XSD Пресеты отчетов по складским операциям)
Пример запроса
https://localhost:8080/resto/api/reports/storeReportPresets?key=1
ac6b9a3-19a0-7c60-e23b-124dd70d75da
Расход продуктов по продажам
Версия iiko: 3.9
https://host:port/resto/api/reports/productExpense
Allrightsreserved © CompanyInc., 2023


### Table:

|  |

|---|

| https://localhost:8080/resto/api/reports/storeOperations?key=1ac6
b9a3-19a0-7c60-e23b-
124dd70d75da&dateFrom=01.09.2014&dateTo=09.09.2014&productDetaliz
ation=false&showCostCorrections=false&documentTypes=SALES_DOCUMEN
T&documentTypes=INCOMING_INVOICE&stores=1239d270-1bbe-f64f-b7ea-
5f00518ef508&stores=93c5cc1f-4c80-4bea-9100-70053a10e37a |

|  |



### Table:

| 124dd70d75da&dateFrom=01.09.2014&dateTo=09.09.2014&productDetaliz |

|---|

| ation=false&showCostCorrections=false&documentTypes=SALES_DOCUMEN |



### Table:

|  |

|---|

| https://localhost:8080/resto/api/reports/storeOperations?key=1ac6
b9a3-19a0-7c60-e23b-
124dd70d75da&dateFrom=01.12.2014&dateTo=17.12.2014&presetId=bf888
6b3-a765-6535-37e4-873bce201482 |

|  |



### Table:

|  |

|---|

| https://localhost:8080/resto/api/reports/storeReportPresets?key=1
ac6b9a3-19a0-7c60-e23b-124dd70d75da |

|  |


---


## Page 3

API Documentation Page3 of 15
Параметры запроса
Название Значение Описание
department GUID Подразделение
dateFrom DD.MM.YYYY Начальнаядата
dateTo DD.MM.YYYY Конечнаядата
hourFrom hh Часначалаинтервалавыборкивсутках(поумолчанию-1,всевремя)
hourTo hh Часокончанияинтервалавыборкивсутках(поумолчанию-1,всевремя)
Что в ответе
Структура dayDishValue (см. XSD Расход продуктов по продажам)
Пример запроса
https://localhost:8080/resto/api/reports/productExpense?key=1ac6b
9a3-19a0-7c60-e23b-124dd70d75da&department=49023e1b-6e3a-6c33-
0133-
ce1f6f5000b&dateFrom=01.12.2014&dateTo=17.12.2014&hourFrom=12&hou
rTo=15
Отчет по выручке
Версия iiko: 3.9
https://host:port/resto/api/reports/sales
Параметры запроса
Название Значение Описание
department GUID Подразделение
dateFrom DD.MM.YYYY Начальнаядата
dateTo DD.MM.YYYY Конечнаядата
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| department |  |  | GUID |  |  | Подразделение |  |  |

| dateFrom |  |  | DD.MM.YYYY |  |  | Начальнаядата |  |  |

| dateTo |  |  | DD.MM.YYYY |  |  | Конечнаядата |  |  |

| hourFrom |  |  | hh |  |  | Часначалаинтервалавыборкивсутках(поумолчанию-1,всевремя) |  |  |

| hourTo |  |  | hh |  |  | Часокончанияинтервалавыборкивсутках(поумолчанию-1,всевремя) |  |  |



### Table:

|  |

|---|

| https://localhost:8080/resto/api/reports/productExpense?key=1ac6b
9a3-19a0-7c60-e23b-124dd70d75da&department=49023e1b-6e3a-6c33-
0133-
ce1f6f5000b&dateFrom=01.12.2014&dateTo=17.12.2014&hourFrom=12&hou
rTo=15 |

|  |



### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| department |  |  | GUID |  |  | Подразделение |  |  |

| dateFrom |  |  | DD.MM.YYYY |  |  | Начальнаядата |  |  |

| dateTo |  |  | DD.MM.YYYY |  |  | Конечнаядата |  |  |


---


## Page 4

API Documentation Page4 of 15
Название Значение Описание
hourFrom hh Часначалаинтервалавыборкивсутках(поумолчанию-1,все
время),поумолчанию-1
hourTo hh Часокончанияинтервалавыборкивсутках(поумолчанию-1,все
время),поумолчанию-1
dishDetails Boolean Включатьлиразбивкупоблюдам(true/false),поумолчаниюfalse
allRevenue Boolean Фильтрацияпотипамоплат(true-всетипы,false-только
выручка),поумолчаниюtrue
Что в ответе
Структура dayDishValue (см. XSD Отчет по выручке)
Пример запроса
https://localhost:8080/resto/api/reports/sales?key=1ac6b9a3-19a0-
7c60-e23b-124dd70d75da&department=49023e1b-6e3a-6c33-0133-
cce1f6f5000b&dateFrom=01.12.2014&dateTo=17.12.2014&hourFrom=12&ho
urTo=15&dishDetails=true&allRevenue=false
План по выручке за день
Версия iiko: 3.9
https://host:port/resto/api/reports/monthlyIncomePlan
Параметры запроса
Название Значение Описание
department GUID Подразделение
dateFrom DD.MM.YYYY Начальнаядата
dateTo DD.MM.YYYY Конечнаядата
Что в ответе
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| hourFrom |  |  | hh |  |  | Часначалаинтервалавыборкивсутках(поумолчанию-1,все
время),поумолчанию-1 |  |  |

| hourTo |  |  | hh |  |  | Часокончанияинтервалавыборкивсутках(поумолчанию-1,все
время),поумолчанию-1 |  |  |

| dishDetails |  |  | Boolean |  |  | Включатьлиразбивкупоблюдам(true/false),поумолчаниюfalse |  |  |

| allRevenue |  |  | Boolean |  |  | Фильтрацияпотипамоплат(true-всетипы,false-только
выручка),поумолчаниюtrue |  |  |



### Table:

|  |

|---|

| https://localhost:8080/resto/api/reports/sales?key=1ac6b9a3-19a0-
7c60-e23b-124dd70d75da&department=49023e1b-6e3a-6c33-0133-
cce1f6f5000b&dateFrom=01.12.2014&dateTo=17.12.2014&hourFrom=12&ho
urTo=15&dishDetails=true&allRevenue=false |

|  |



### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| department |  |  | GUID |  |  | Подразделение |  |  |

| dateFrom |  |  | DD.MM.YYYY |  |  | Начальнаядата |  |  |

| dateTo |  |  | DD.MM.YYYY |  |  | Конечнаядата |  |  |


---


## Page 5

API Documentation Page5 of 15
Структура budgetPlanItemDtoes (см. XSD План по выручке за день)
Пример запроса
https://localhost:8080/resto/api/reports/monthlyIncomePlan?key=05
e04d9e-26db-a5a2-ba2b-68af4e8a5ed4&department=49023e1b-6e3a-6c33-
0133-cce1f6f5000b&dateFrom=01.12.2014&dateTo=18.12.2014
Отчет о вхождении товара в блюдо
Версия iiko: 3.9
https://host:port/resto/api/reports/ingredientEntry
Параметры запроса
Название Значение Описание
department GUID Подразделение
date DD.MM.YYYY Накакуюдату
product DD.MM.YYYY Idпродукта
productArticle Строка Артикулпродукта(приоритетпоиска:productArticle, product)
includeSubtree Boolean Включатьливотчетстрокиподдеревьев(поумолчаниюfalse)
Что в ответе
Структура ingredientEntryDtoes (см. XSD Отчет о вхождении товара в блюдо)
Пример запроса
https://localhost:8080/resto/api/reports/ingredientEntry?key=05e0
4d9e-26db-a5a2-ba2b-
68af4e8a5ed4&date=01.12.2014&product=2c3ab3e1-266d-4667-b344-
98b6c194a305&department=49023e1b-6e3a-6c33-0133-
cce1f6f5000b&includeSubtree=false
Allrightsreserved © CompanyInc., 2023


### Table:

|  |

|---|

| https://localhost:8080/resto/api/reports/monthlyIncomePlan?key=05
e04d9e-26db-a5a2-ba2b-68af4e8a5ed4&department=49023e1b-6e3a-6c33-
0133-cce1f6f5000b&dateFrom=01.12.2014&dateTo=18.12.2014 |

|  |



### Table:

| https://localhost:8080/resto/api/reports/monthlyIncomePlan?key=05 |

|---|

| e04d9e-26db-a5a2-ba2b-68af4e8a5ed4&department=49023e1b-6e3a-6c33- |



### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| department |  |  | GUID |  |  | Подразделение |  |  |

| date |  |  | DD.MM.YYYY |  |  | Накакуюдату |  |  |

| product |  |  | DD.MM.YYYY |  |  | Idпродукта |  |  |

| productArticle |  |  | Строка |  |  | Артикулпродукта(приоритетпоиска:productArticle, product) |  |  |

| includeSubtree |  |  | Boolean |  |  | Включатьливотчетстрокиподдеревьев(поумолчаниюfalse) |  |  |



### Table:

|  |

|---|

| https://localhost:8080/resto/api/reports/ingredientEntry?key=05e0
4d9e-26db-a5a2-ba2b-
68af4e8a5ed4&date=01.12.2014&product=2c3ab3e1-266d-4667-b344-
98b6c194a305&department=49023e1b-6e3a-6c33-0133-
cce1f6f5000b&includeSubtree=false |

|  |


---


## Page 6

API Documentation Page6 of 15
XSD Отчеты
[+] XSDОтчет овхождениитовара вблюдо
[-] XSDОтчет овхождениитовара вблюдо
Copy Code
XML
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="item" type="ingredientEntryDto"/>
<xs:complexType name="ingredientEntryDto">
<xs:sequence>
<!-- Брутто в основной единице измерения (кг) -->
<xs:element name="amountInMainUnit" type="xs:decimal"
minOccurs="0"/>
<!-- Брутто в единицах измерения продукта -->
<xs:element name="amountInMeasureUnit" type="xs:decimal"
minOccurs="0"/>
<!-- Нетто в основной единице измерения (кг) -->
<xs:element name="amountMiddleMainUnit" type="xs:decimal"
minOccurs="0"/>
<!-- Нетто в единицах измерения продукта -->
<xs:element name="amountMiddleMeasureUnit" type="xs:decimal"
minOccurs="0"/>
<!-- Выход в основной единице измерения (кг) -->
<xs:element name="amountOutMainUnit" type="xs:decimal"
minOccurs="0"/>
<!-- Выход в единицах измерения продукта -->
<xs:element name="amountOutMeasureUnit" type="xs:decimal"
minOccurs="0"/>
<!-- Потери при холодной обработке (%) -->
<xs:element name="coldLoss" type="xs:decimal" minOccurs="0"/>
<!-- Процент себестоимости, т.е процент который состовляет
стоимость ингредиентов от стоимости блюда -->
<xs:element name="costNorm" type="xs:decimal" minOccurs="0"/>
<!-- Себестоимость блюда -->
<xs:element name="dishCostNorm" type="xs:decimal" minOccurs="0"/>
<!-- Цена продажи блюда -->
<xs:element name="dishSalePrice" type="xs:decimal" minOccurs="0"/>
<!-- Потери при горячей обработке (%) -->
<xs:element name="hotLoss" type="xs:decimal" minOccurs="0"/>
<!-- ИД строки отчета для представления в виде дерева (guid) -->
<xs:element name="itemId" type="xs:string" minOccurs="0"/>
<!-- ИД родительской строки отчета для представления в виде
дерева (guid) -->
<xs:element name="itemParentId" type="xs:string" minOccurs="0"/>
<!-- Наименование продукта -->
<xs:element name="name" type="xs:string" minOccurs="0"/>
<!-- Артикул продукта -->
Allrightsreserved © CompanyInc., 2023


### Table:

| Copy Code |  |  |

|---|---|---|

|  | XML |  |

|  |  |  |

|  |  |  |

|  | <?xml version="1.0" encoding="UTF-8" standalone="yes"?> |  |

|  | <xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema"> |  |

|  | <xs:element name="item" type="ingredientEntryDto"/> |  |

|  | <xs:complexType name="ingredientEntryDto"> |  |

|  | <xs:sequence> |  |

|  | <!-- Брутто в основной единице измерения (кг) --> |  |

|  | <xs:element name="amountInMainUnit" type="xs:decimal" |  |

|  | minOccurs="0"/> |  |

|  | <!-- Брутто в единицах измерения продукта --> |  |

|  | <xs:element name="amountInMeasureUnit" type="xs:decimal" |  |

|  | minOccurs="0"/> |  |

|  | <!-- Нетто в основной единице измерения (кг) --> |  |

|  | <xs:element name="amountMiddleMainUnit" type="xs:decimal" |  |

|  | minOccurs="0"/> |  |

|  | <!-- Нетто в единицах измерения продукта --> |  |

|  | <xs:element name="amountMiddleMeasureUnit" type="xs:decimal" |  |

|  | minOccurs="0"/> |  |

|  | <!-- Выход в основной единице измерения (кг) --> |  |

|  | <xs:element name="amountOutMainUnit" type="xs:decimal" |  |

|  | minOccurs="0"/> |  |

|  | <!-- Выход в единицах измерения продукта --> |  |

|  | <xs:element name="amountOutMeasureUnit" type="xs:decimal" |  |

|  | minOccurs="0"/> |  |

|  | <!-- Потери при холодной обработке (%) --> |  |

|  | <xs:element name="coldLoss" type="xs:decimal" minOccurs="0"/> |  |

|  | <!-- Процент себестоимости, т.е процент который состовляет |  |

|  | стоимость ингредиентов от стоимости блюда --> |  |

|  | <xs:element name="costNorm" type="xs:decimal" minOccurs="0"/> |  |

|  | <!-- Себестоимость блюда --> |  |

|  | <xs:element name="dishCostNorm" type="xs:decimal" minOccurs="0"/> |  |

|  | <!-- Цена продажи блюда --> |  |

|  | <xs:element name="dishSalePrice" type="xs:decimal" minOccurs="0"/> |  |

|  | <!-- Потери при горячей обработке (%) --> |  |

|  | <xs:element name="hotLoss" type="xs:decimal" minOccurs="0"/> |  |

|  | <!-- ИД строки отчета для представления в виде дерева (guid) --> |  |

|  | <xs:element name="itemId" type="xs:string" minOccurs="0"/> |  |

|  | <!-- ИД родительской строки отчета для представления в виде |  |

|  | дерева (guid) --> |  |

|  | <xs:element name="itemParentId" type="xs:string" minOccurs="0"/> |  |

|  | <!-- Наименование продукта --> |  |

|  | <xs:element name="name" type="xs:string" minOccurs="0"/> |  |

|  | <!-- Артикул продукта --> |  |


---


## Page 7

API Documentation Page7 of 15
<xs:element name="num" type="xs:string" minOccurs="0"/>
<!-- ИД продукта (guid) -->
<xs:element name="product" type="xs:string" minOccurs="0"/>
<!-- Стоимость товара в блюде -->
<xs:element name="productInDishCost" type="xs:decimal"
minOccurs="0"/>
<!-- Себестоимость продукта, по которому строится отчет -->
<xs:element name="sourceProductCostNorm" type="xs:decimal"
minOccurs="0"/>
<!-- Уровень строки в дереве -->
<xs:element name="treeLevel" type="xs:int"/>
<!-- Наименование единицы измерения -->
<xs:element name="unit" type="xs:string" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
</xs:schema>
[+] XSDОтчет повыручке
[-] XSDОтчет повыручке
Copy Code
XML
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="dayDishValue" type="dayDishValue"/>
<xs:complexType name="dayDishValue">
<xs:sequence>
<xs:element name="date" type="xs:string" minOccurs="0"/>
<xs:element name="productId" type="xs:string" minOccurs="0"/>
<xs:element name="productName" type="xs:string" minOccurs="0"/>
<xs:element name="value" type="xs:decimal" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
</xs:schema>
[+] XSDОтчет поскладским операциям
[-] XSDОтчет поскладским операциям
Copy Code
XML
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="storeReportItemDto" type="storeReportItemDto"/>
<xs:complexType name="storeReportItemDto">
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <xs:element name="num" type="xs:string" minOccurs="0"/> |

|  | <!-- ИД продукта (guid) --> |

|  | <xs:element name="product" type="xs:string" minOccurs="0"/> |

|  | <!-- Стоимость товара в блюде --> |

|  | <xs:element name="productInDishCost" type="xs:decimal" |

|  | minOccurs="0"/> |

|  | <!-- Себестоимость продукта, по которому строится отчет --> |

|  | <xs:element name="sourceProductCostNorm" type="xs:decimal" |

|  | minOccurs="0"/> |

|  | <!-- Уровень строки в дереве --> |

|  | <xs:element name="treeLevel" type="xs:int"/> |

|  | <!-- Наименование единицы измерения --> |

|  | <xs:element name="unit" type="xs:string" minOccurs="0"/> |

|  | </xs:sequence> |

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

|  | <xs:element name="dayDishValue" type="dayDishValue"/> |  |

|  | <xs:complexType name="dayDishValue"> |  |

|  | <xs:sequence> |  |

|  | <xs:element name="date" type="xs:string" minOccurs="0"/> |  |

|  | <xs:element name="productId" type="xs:string" minOccurs="0"/> |  |

|  | <xs:element name="productName" type="xs:string" minOccurs="0"/> |  |

|  | <xs:element name="value" type="xs:decimal" minOccurs="0"/> |  |

|  | </xs:sequence> |  |

|  | </xs:complexType> |  |

|  | </xs:schema> |  |

|  |  |  |



### Table:

| Copy Code |  |  |

|---|---|---|

|  | XML |  |

|  |  |  |

|  |  |  |

|  | <?xml version="1.0" encoding="UTF-8" standalone="yes"?> |  |

|  | <xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema"> |  |

|  | <xs:element name="storeReportItemDto" type="storeReportItemDto"/> |  |

|  | <xs:complexType name="storeReportItemDto"> |  |


---


## Page 8

API Documentation Page8 of 15
<xs:sequence>
<xs:element name="ndsPercent" type="xs:decimal" minOccurs="0"/>
<xs:element name="productCategory" type="xs:string"
minOccurs="0"/>
<xs:element name="productGroup" type="xs:string" minOccurs="0"/>
<xs:element name="product" type="xs:string" minOccurs="0"/>
<xs:element name="secondaryAccount" type="xs:string"
minOccurs="0"/>
<xs:element name="primaryStore" type="xs:string" minOccurs="0"/>
<xs:element name="documentNum" type="xs:string" minOccurs="0"/>
<xs:element name="expenseAccount" type="xs:string" minOccurs="0"/>
<xs:element name="revenueAccount" type="xs:string" minOccurs="0"/>
<xs:element name="documentComment" type="xs:string"
minOccurs="0"/>
<xs:element name="documentId" type="xs:string" minOccurs="0"/>
<xs:element name="documentType" type="documentType"
minOccurs="0"/>
<xs:element name="incoming" type="xs:boolean"/>
<xs:element name="type" type="transactionType" minOccurs="0"/>
<xs:element name="date" type="xs:string" minOccurs="0"/>
<xs:element name="operationalDate" type="xs:string"
minOccurs="0"/>
<xs:element name="cost" type="xs:decimal" minOccurs="0"/>
<xs:element name="secondEstimatedPurchasePrice" type="xs:decimal"
minOccurs="0"/>
<xs:element name="firstEstimatedPurchasePrice" type="xs:decimal"
minOccurs="0"/>
<xs:element name="documentSum" type="xs:decimal" minOccurs="0"/>
<xs:element name="secondaryAmount" type="xs:decimal"
minOccurs="0"/>
<xs:element name="amount" type="xs:decimal" minOccurs="0"/>
<xs:element name="sumWithoutNds" type="xs:decimal" minOccurs="0"/>
<xs:element name="sumNds" type="xs:decimal" minOccurs="0"/>
<xs:element name="sum" type="xs:decimal" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
<xs:simpleType name="transactionType">
<xs:restriction base="xs:string">
<xs:enumeration value="OPENING_BALANCE"/>
<xs:enumeration value="CUSTOM"/>
<xs:enumeration value="CASH"/>
<xs:enumeration value="PREPAY_CLOSED"/>
<xs:enumeration value="PREPAY"/>
<xs:enumeration value="PREPAY_RETURN"/>
<xs:enumeration value="PREPAY_CLOSED_RETURN"/>
<xs:enumeration value="DISCOUNT"/>
<xs:enumeration value="CARD"/>
<xs:enumeration value="CREDIT"/>
<xs:enumeration value="PAYIN"/>
<xs:enumeration value="PAYOUT"/>
<xs:enumeration value="PAY_COLLECTION"/>
<xs:enumeration value="CASH_CORRECTION"/>
<xs:enumeration value="INVENTORY_CORRECTION"/>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <xs:sequence> |

|  | <xs:element name="ndsPercent" type="xs:decimal" minOccurs="0"/> |

|  | <xs:element name="productCategory" type="xs:string" |

|  | minOccurs="0"/> |

|  | <xs:element name="productGroup" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="product" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="secondaryAccount" type="xs:string" |

|  | minOccurs="0"/> |

|  | <xs:element name="primaryStore" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="documentNum" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="expenseAccount" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="revenueAccount" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="documentComment" type="xs:string" |

|  | minOccurs="0"/> |

|  | <xs:element name="documentId" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="documentType" type="documentType" |

|  | minOccurs="0"/> |

|  | <xs:element name="incoming" type="xs:boolean"/> |

|  | <xs:element name="type" type="transactionType" minOccurs="0"/> |

|  | <xs:element name="date" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="operationalDate" type="xs:string" |

|  | minOccurs="0"/> |

|  | <xs:element name="cost" type="xs:decimal" minOccurs="0"/> |

|  | <xs:element name="secondEstimatedPurchasePrice" type="xs:decimal" |

|  | minOccurs="0"/> |

|  | <xs:element name="firstEstimatedPurchasePrice" type="xs:decimal" |

|  | minOccurs="0"/> |

|  | <xs:element name="documentSum" type="xs:decimal" minOccurs="0"/> |

|  | <xs:element name="secondaryAmount" type="xs:decimal" |

|  | minOccurs="0"/> |

|  | <xs:element name="amount" type="xs:decimal" minOccurs="0"/> |

|  | <xs:element name="sumWithoutNds" type="xs:decimal" minOccurs="0"/> |

|  | <xs:element name="sumNds" type="xs:decimal" minOccurs="0"/> |

|  | <xs:element name="sum" type="xs:decimal" minOccurs="0"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | <xs:simpleType name="transactionType"> |

|  | <xs:restriction base="xs:string"> |

|  | <xs:enumeration value="OPENING_BALANCE"/> |

|  | <xs:enumeration value="CUSTOM"/> |

|  | <xs:enumeration value="CASH"/> |

|  | <xs:enumeration value="PREPAY_CLOSED"/> |

|  | <xs:enumeration value="PREPAY"/> |

|  | <xs:enumeration value="PREPAY_RETURN"/> |

|  | <xs:enumeration value="PREPAY_CLOSED_RETURN"/> |

|  | <xs:enumeration value="DISCOUNT"/> |

|  | <xs:enumeration value="CARD"/> |

|  | <xs:enumeration value="CREDIT"/> |

|  | <xs:enumeration value="PAYIN"/> |

|  | <xs:enumeration value="PAYOUT"/> |

|  | <xs:enumeration value="PAY_COLLECTION"/> |

|  | <xs:enumeration value="CASH_CORRECTION"/> |

|  | <xs:enumeration value="INVENTORY_CORRECTION"/> |


---


## Page 9

API Documentation Page9 of 15
<xs:enumeration value="STORE_COST_CORRECTION"/>
<xs:enumeration value="CASH_SURPLUS"/>
<xs:enumeration value="CASH_SHORTAGE"/>
<xs:enumeration value="PENALTY"/>
<xs:enumeration value="BONUS"/>
<xs:enumeration value="INVOICE"/>
<xs:enumeration value="NDS_INCOMING"/>
<xs:enumeration value="NDS_SALES"/>
<xs:enumeration value="SALES_REVENUE"/>
<xs:enumeration value="OUTGOING_INVOICE"/>
<xs:enumeration value="OUTGOING_INVOICE_REVENUE"/>
<xs:enumeration value="RETURNED_INVOICE"/>
<xs:enumeration value="RETURNED_INVOICE_REVENUE"/>
<xs:enumeration value="WRITEOFF"/>
<xs:enumeration value="SESSION_WRITEOFF"/>
<xs:enumeration value="TRANSFER"/>
<xs:enumeration value="TRANSFORMATION"/>
<xs:enumeration value="TARIFF_HOUR"/>
<xs:enumeration value="ON_THE_HOUSE"/>
<xs:enumeration value="ADVANCE"/>
<xs:enumeration value="INCOMING_SERVICE"/>
<xs:enumeration value="OUTGOING_SERVICE"/>
<xs:enumeration value="INCOMING_SERVICE_PAYMENT"/>
<xs:enumeration value="OUTGOING_SERVICE_PAYMENT"/>
<xs:enumeration value="CLOSE_AT_EMPLOYEE_EXPENSE"/>
<xs:enumeration value="INCENTIVE_PAYMENT"/>
<xs:enumeration value="TARIFF_PERCENT"/>
<xs:enumeration value="SESSION_ACCEPTANCE"/>
<xs:enumeration value="EMPLOYEE_CASH_PAYMENT"/>
<xs:enumeration value="EMPLOYEE_PAYMENT"/>
<xs:enumeration value="INVOICE_PAYMENT"/>
<xs:enumeration value="OUTGOING_DOCUMENT_PAYMENT"/>
<xs:enumeration value="OUTGOING_SALES_DOCUMENT_PAYMENT"/>
<xs:enumeration value="PRODUCTION"/>
<xs:enumeration value="SALES_RETURN_PAYMENT"/>
<xs:enumeration value="SALES_RETURN_WRITEOFF"/>
<xs:enumeration value="DISASSEMBLE"/>
</xs:restriction>
</xs:simpleType>
<xs:simpleType name="documentType">
<xs:restriction base="xs:string">
<xs:enumeration value="INCOMING_INVOICE"/>
<xs:enumeration value="INCOMING_INVENTORY"/>
<xs:enumeration value="INCOMING_SERVICE"/>
<xs:enumeration value="OUTGOING_SERVICE"/>
<xs:enumeration value="WRITEOFF_DOCUMENT"/>
<xs:enumeration value="SALES_DOCUMENT"/>
<xs:enumeration value="SESSION_ACCEPTANCE"/>
<xs:enumeration value="INTERNAL_TRANSFER"/>
<xs:enumeration value="OUTGOING_INVOICE"/>
<xs:enumeration value="RETURNED_INVOICE"/>
<xs:enumeration value="PRODUCTION_DOCUMENT"/>
<xs:enumeration value="TRANSFORMATION_DOCUMENT"/>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <xs:enumeration value="STORE_COST_CORRECTION"/> |

|  | <xs:enumeration value="CASH_SURPLUS"/> |

|  | <xs:enumeration value="CASH_SHORTAGE"/> |

|  | <xs:enumeration value="PENALTY"/> |

|  | <xs:enumeration value="BONUS"/> |

|  | <xs:enumeration value="INVOICE"/> |

|  | <xs:enumeration value="NDS_INCOMING"/> |

|  | <xs:enumeration value="NDS_SALES"/> |

|  | <xs:enumeration value="SALES_REVENUE"/> |

|  | <xs:enumeration value="OUTGOING_INVOICE"/> |

|  | <xs:enumeration value="OUTGOING_INVOICE_REVENUE"/> |

|  | <xs:enumeration value="RETURNED_INVOICE"/> |

|  | <xs:enumeration value="RETURNED_INVOICE_REVENUE"/> |

|  | <xs:enumeration value="WRITEOFF"/> |

|  | <xs:enumeration value="SESSION_WRITEOFF"/> |

|  | <xs:enumeration value="TRANSFER"/> |

|  | <xs:enumeration value="TRANSFORMATION"/> |

|  | <xs:enumeration value="TARIFF_HOUR"/> |

|  | <xs:enumeration value="ON_THE_HOUSE"/> |

|  | <xs:enumeration value="ADVANCE"/> |

|  | <xs:enumeration value="INCOMING_SERVICE"/> |

|  | <xs:enumeration value="OUTGOING_SERVICE"/> |

|  | <xs:enumeration value="INCOMING_SERVICE_PAYMENT"/> |

|  | <xs:enumeration value="OUTGOING_SERVICE_PAYMENT"/> |

|  | <xs:enumeration value="CLOSE_AT_EMPLOYEE_EXPENSE"/> |

|  | <xs:enumeration value="INCENTIVE_PAYMENT"/> |

|  | <xs:enumeration value="TARIFF_PERCENT"/> |

|  | <xs:enumeration value="SESSION_ACCEPTANCE"/> |

|  | <xs:enumeration value="EMPLOYEE_CASH_PAYMENT"/> |

|  | <xs:enumeration value="EMPLOYEE_PAYMENT"/> |

|  | <xs:enumeration value="INVOICE_PAYMENT"/> |

|  | <xs:enumeration value="OUTGOING_DOCUMENT_PAYMENT"/> |

|  | <xs:enumeration value="OUTGOING_SALES_DOCUMENT_PAYMENT"/> |

|  | <xs:enumeration value="PRODUCTION"/> |

|  | <xs:enumeration value="SALES_RETURN_PAYMENT"/> |

|  | <xs:enumeration value="SALES_RETURN_WRITEOFF"/> |

|  | <xs:enumeration value="DISASSEMBLE"/> |

|  | </xs:restriction> |

|  | </xs:simpleType> |

|  | <xs:simpleType name="documentType"> |

|  | <xs:restriction base="xs:string"> |

|  | <xs:enumeration value="INCOMING_INVOICE"/> |

|  | <xs:enumeration value="INCOMING_INVENTORY"/> |

|  | <xs:enumeration value="INCOMING_SERVICE"/> |

|  | <xs:enumeration value="OUTGOING_SERVICE"/> |

|  | <xs:enumeration value="WRITEOFF_DOCUMENT"/> |

|  | <xs:enumeration value="SALES_DOCUMENT"/> |

|  | <xs:enumeration value="SESSION_ACCEPTANCE"/> |

|  | <xs:enumeration value="INTERNAL_TRANSFER"/> |

|  | <xs:enumeration value="OUTGOING_INVOICE"/> |

|  | <xs:enumeration value="RETURNED_INVOICE"/> |

|  | <xs:enumeration value="PRODUCTION_DOCUMENT"/> |

|  | <xs:enumeration value="TRANSFORMATION_DOCUMENT"/> |


---


## Page 10

API Documentation Page10 of 15
<xs:enumeration value="PRODUCTION_ORDER"/>
<xs:enumeration value="CONSOLIDATED_ORDER"/>
<xs:enumeration value="PREPARED_REGISTER"/>
<xs:enumeration value="MENU_CHANGE"/>
<xs:enumeration value="PRODUCT_REPLACEMENT"/>
<xs:enumeration value="SALES_RETURN_DOCUMENT"/>
<xs:enumeration value="DISASSEMBLE_DOCUMENT"/>
<xs:enumeration value="FUEL_ACCEPTANCE"/>
<xs:enumeration value="FUEL_GAGING_DOCUMENT"/>
<xs:enumeration value="PAYROLL"/>
</xs:restriction>
</xs:simpleType>
</xs:schema>
[+] XSDПланповыручке за день
[-] XSDПланповыручке за день
Copy Code
XML
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="budgetPlanItemDto" type="budgetPlanItemDto"/>
<xs:complexType name="budgetPlanItemDto">
<xs:sequence>
<xs:element name="date" type="xs:string" minOccurs="0"/>
<xs:element name="planValue" type="xs:decimal" minOccurs="0"/>
<xs:element name="valueType" type="budgetPlanItemValueType"
minOccurs="0"/>
</xs:sequence>
</xs:complexType>
<xs:simpleType name="budgetPlanItemValueType">
<xs:restriction base="xs:string">
<xs:enumeration value="ABSOLUTE"/>
<xs:enumeration value="PERCENT"/>
<xs:enumeration value="AUTOMATIC"/>
</xs:restriction>
</xs:simpleType>
</xs:schema>
[+] XSDПресетыотчетовпоскладским операциям
[-] XSDПресетыотчетовпоскладским операциям
Copy Code
XML
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <xs:enumeration value="PRODUCTION_ORDER"/> |

|  | <xs:enumeration value="CONSOLIDATED_ORDER"/> |

|  | <xs:enumeration value="PREPARED_REGISTER"/> |

|  | <xs:enumeration value="MENU_CHANGE"/> |

|  | <xs:enumeration value="PRODUCT_REPLACEMENT"/> |

|  | <xs:enumeration value="SALES_RETURN_DOCUMENT"/> |

|  | <xs:enumeration value="DISASSEMBLE_DOCUMENT"/> |

|  | <xs:enumeration value="FUEL_ACCEPTANCE"/> |

|  | <xs:enumeration value="FUEL_GAGING_DOCUMENT"/> |

|  | <xs:enumeration value="PAYROLL"/> |

|  | </xs:restriction> |

|  | </xs:simpleType> |

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

|  | <xs:element name="budgetPlanItemDto" type="budgetPlanItemDto"/> |  |

|  | <xs:complexType name="budgetPlanItemDto"> |  |

|  | <xs:sequence> |  |

|  | <xs:element name="date" type="xs:string" minOccurs="0"/> |  |

|  | <xs:element name="planValue" type="xs:decimal" minOccurs="0"/> |  |

|  | <xs:element name="valueType" type="budgetPlanItemValueType" |  |

|  | minOccurs="0"/> |  |

|  | </xs:sequence> |  |

|  | </xs:complexType> |  |

|  | <xs:simpleType name="budgetPlanItemValueType"> |  |

|  | <xs:restriction base="xs:string"> |  |

|  | <xs:enumeration value="ABSOLUTE"/> |  |

|  | <xs:enumeration value="PERCENT"/> |  |

|  | <xs:enumeration value="AUTOMATIC"/> |  |

|  | </xs:restriction> |  |

|  | </xs:simpleType> |  |

|  | </xs:schema> |  |

|  |  |  |



### Table:

| Copy Code |  |  |

|---|---|---|

|  | XML |  |

|  |  |  |


---


## Page 11

API Documentation Page11 of 15
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="storeReportPreset" type="storeReportPreset"/>
<xs:complexType name="storeReportPreset">
<xs:sequence>
<xs:element name="id" type="xs:string" minOccurs="0"/>
<xs:element name="defaultReport" type="xs:boolean"/>
<xs:element name="name" type="xs:string" minOccurs="0"/>
<xs:element name="comment" type="xs:string" minOccurs="0"/>
<xs:element name="grouping" type="storeOperationsReportGrouping"
minOccurs="0"/>
<xs:element name="filter" type="filter" minOccurs="0"/>
<xs:element name="columnCaptions" minOccurs="0">
<xs:complexType>
<xs:sequence>
<xs:element name="i" type="keyValue" minOccurs="0"
maxOccurs="unbounded"/>
</xs:sequence>
</xs:complexType>
</xs:element>
</xs:sequence>
</xs:complexType>
<xs:complexType name="storeOperationsReportGrouping">
<xs:sequence>
<xs:element name="dateDetalization" type="dateDetalization"
minOccurs="0"/>
</xs:sequence>
</xs:complexType>
<xs:complexType name="filter">
<xs:sequence>
<xs:element name="primaryStores" minOccurs="0">
<xs:complexType>
<xs:sequence>
<xs:element name="i" type="xs:string" minOccurs="0"
maxOccurs="unbounded"/>
</xs:sequence>
</xs:complexType>
</xs:element>
<xs:element name="secondaryAccounts" minOccurs="0">
<xs:complexType>
<xs:sequence>
<xs:element name="i" type="xs:string" minOccurs="0"
maxOccurs="unbounded"/>
</xs:sequence>
</xs:complexType>
</xs:element>
<xs:element name="counteragents" minOccurs="0">
<xs:complexType>
<xs:sequence>
<xs:element name="i" type="xs:string" minOccurs="0"
maxOccurs="unbounded"/>
</xs:sequence>
</xs:complexType>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <?xml version="1.0" encoding="UTF-8" standalone="yes"?> |

|  | <xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema"> |

|  | <xs:element name="storeReportPreset" type="storeReportPreset"/> |

|  | <xs:complexType name="storeReportPreset"> |

|  | <xs:sequence> |

|  | <xs:element name="id" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="defaultReport" type="xs:boolean"/> |

|  | <xs:element name="name" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="comment" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="grouping" type="storeOperationsReportGrouping" |

|  | minOccurs="0"/> |

|  | <xs:element name="filter" type="filter" minOccurs="0"/> |

|  | <xs:element name="columnCaptions" minOccurs="0"> |

|  | <xs:complexType> |

|  | <xs:sequence> |

|  | <xs:element name="i" type="keyValue" minOccurs="0" |

|  | maxOccurs="unbounded"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | </xs:element> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | <xs:complexType name="storeOperationsReportGrouping"> |

|  | <xs:sequence> |

|  | <xs:element name="dateDetalization" type="dateDetalization" |

|  | minOccurs="0"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | <xs:complexType name="filter"> |

|  | <xs:sequence> |

|  | <xs:element name="primaryStores" minOccurs="0"> |

|  | <xs:complexType> |

|  | <xs:sequence> |

|  | <xs:element name="i" type="xs:string" minOccurs="0" |

|  | maxOccurs="unbounded"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | </xs:element> |

|  | <xs:element name="secondaryAccounts" minOccurs="0"> |

|  | <xs:complexType> |

|  | <xs:sequence> |

|  | <xs:element name="i" type="xs:string" minOccurs="0" |

|  | maxOccurs="unbounded"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | </xs:element> |

|  | <xs:element name="counteragents" minOccurs="0"> |

|  | <xs:complexType> |

|  | <xs:sequence> |

|  | <xs:element name="i" type="xs:string" minOccurs="0" |

|  | maxOccurs="unbounded"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |


---


## Page 12

API Documentation Page12 of 15
</xs:element>
<xs:element name="products" minOccurs="0">
<xs:complexType>
<xs:sequence>
<xs:element name="i" type="xs:string" minOccurs="0"
maxOccurs="unbounded"/>
</xs:sequence>
</xs:complexType>
</xs:element>
<xs:element name="secondaryProducts" minOccurs="0">
<xs:complexType>
<xs:sequence>
<xs:element name="i" type="xs:string" minOccurs="0"
maxOccurs="unbounded"/>
</xs:sequence>
</xs:complexType>
</xs:element>
<xs:element name="transactionTypes" minOccurs="0">
<xs:complexType>
<xs:sequence>
<xs:element name="i" type="transactionType" minOccurs="0"
maxOccurs="unbounded"/>
</xs:sequence>
</xs:complexType>
</xs:element>
<xs:element name="documentTypes" minOccurs="0">
<xs:complexType>
<xs:sequence>
<xs:element name="i" type="documentType" minOccurs="0"
maxOccurs="unbounded"/>
</xs:sequence>
</xs:complexType>
</xs:element>
<xs:element name="dataDirection" type="storeDataDirection"
minOccurs="0"/>
<xs:element name="includeZeroAmountAndSum" type="xs:boolean"/>
</xs:sequence>
</xs:complexType>
<xs:complexType name="keyValue">
<xs:sequence>
<xs:element name="k" type="xs:string" minOccurs="0"/>
<xs:element name="v" type="xs:string" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
<xs:simpleType name="dateDetalization">
<xs:restriction base="xs:string">
<xs:enumeration value="DAY"/>
<xs:enumeration value="YEAR"/>
<xs:enumeration value="MONTH"/>
<xs:enumeration value="WEEK"/>
<xs:enumeration value="HALF_MONTH"/>
<xs:enumeration value="TOTAL_ONLY"/>
<xs:enumeration value="QUARTER"/>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | </xs:element> |

|  | <xs:element name="products" minOccurs="0"> |

|  | <xs:complexType> |

|  | <xs:sequence> |

|  | <xs:element name="i" type="xs:string" minOccurs="0" |

|  | maxOccurs="unbounded"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | </xs:element> |

|  | <xs:element name="secondaryProducts" minOccurs="0"> |

|  | <xs:complexType> |

|  | <xs:sequence> |

|  | <xs:element name="i" type="xs:string" minOccurs="0" |

|  | maxOccurs="unbounded"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | </xs:element> |

|  | <xs:element name="transactionTypes" minOccurs="0"> |

|  | <xs:complexType> |

|  | <xs:sequence> |

|  | <xs:element name="i" type="transactionType" minOccurs="0" |

|  | maxOccurs="unbounded"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | </xs:element> |

|  | <xs:element name="documentTypes" minOccurs="0"> |

|  | <xs:complexType> |

|  | <xs:sequence> |

|  | <xs:element name="i" type="documentType" minOccurs="0" |

|  | maxOccurs="unbounded"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | </xs:element> |

|  | <xs:element name="dataDirection" type="storeDataDirection" |

|  | minOccurs="0"/> |

|  | <xs:element name="includeZeroAmountAndSum" type="xs:boolean"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | <xs:complexType name="keyValue"> |

|  | <xs:sequence> |

|  | <xs:element name="k" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="v" type="xs:string" minOccurs="0"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | <xs:simpleType name="dateDetalization"> |

|  | <xs:restriction base="xs:string"> |

|  | <xs:enumeration value="DAY"/> |

|  | <xs:enumeration value="YEAR"/> |

|  | <xs:enumeration value="MONTH"/> |

|  | <xs:enumeration value="WEEK"/> |

|  | <xs:enumeration value="HALF_MONTH"/> |

|  | <xs:enumeration value="TOTAL_ONLY"/> |

|  | <xs:enumeration value="QUARTER"/> |


---


## Page 13

API Documentation Page13 of 15
</xs:restriction>
</xs:simpleType>
<xs:simpleType name="transactionType">
<xs:restriction base="xs:string">
<xs:enumeration value="SESSION_WRITEOFF"/>
<xs:enumeration value="OUTGOING_SALES_DOCUMENT_PAYMENT"/>
<xs:enumeration value="PREPAY_CLOSED"/>
<xs:enumeration value="CASH_SURPLUS"/>
<xs:enumeration value="RETURNED_INVOICE"/>
<xs:enumeration value="CREDIT"/>
<xs:enumeration value="CASH_SHORTAGE"/>
<xs:enumeration value="OUTGOING_SERVICE"/>
<xs:enumeration value="STORE_COST_CORRECTION"/>
<xs:enumeration value="SALES_REVENUE"/>
<xs:enumeration value="ADVANCE"/>
<xs:enumeration value="PAYOUT"/>
<xs:enumeration value="INVOICE_PAYMENT"/>
<xs:enumeration value="OUTGOING_DOCUMENT_PAYMENT"/>
<xs:enumeration value="TARIFF_HOUR"/>
<xs:enumeration value="TRANSFER"/>
<xs:enumeration value="WRITEOFF"/>
<xs:enumeration value="SALES_RETURN_WRITEOFF"/>
<xs:enumeration value="CARD"/>
<xs:enumeration value="PREPAY_CLOSED_RETURN"/>
<xs:enumeration value="PRODUCTION"/>
<xs:enumeration value="EMPLOYEE_CASH_PAYMENT"/>
<xs:enumeration value="DISCOUNT"/>
<xs:enumeration value="OUTGOING_INVOICE"/>
<xs:enumeration value="INVENTORY_CORRECTION"/>
<xs:enumeration value="IMPORTED_BANK_STATEMENT"/>
<xs:enumeration value="INCENTIVE_PAYMENT"/>
<xs:enumeration value="NDS_INCOMING"/>
<xs:enumeration value="DISASSEMBLE"/>
<xs:enumeration value="CASH"/>
<xs:enumeration value="OPENING_BALANCE"/>
<xs:enumeration value="INCOMING_SERVICE"/>
<xs:enumeration value="TRANSFORMATION"/>
<xs:enumeration value="BONUS"/>
<xs:enumeration value="SESSION_ACCEPTANCE"/>
<xs:enumeration value="PREPAY_RETURN"/>
<xs:enumeration value="ON_THE_HOUSE"/>
<xs:enumeration value="EMPLOYEE_PAYMENT"/>
<xs:enumeration value="SALES_RETURN_PAYMENT"/>
<xs:enumeration value="INVOICE"/>
<xs:enumeration value="PENALTY"/>
<xs:enumeration value="OUTGOING_SERVICE_PAYMENT"/>
<xs:enumeration value="CLOSE_AT_EMPLOYEE_EXPENSE"/>
<xs:enumeration value="PAY_COLLECTION"/>
<xs:enumeration value="TARIFF_PERCENT"/>
<xs:enumeration value="INCOMING_SERVICE_PAYMENT"/>
<xs:enumeration value="PAYIN"/>
<xs:enumeration value="RETURNED_INVOICE_REVENUE"/>
<xs:enumeration value="NDS_SALES"/>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | </xs:restriction> |

|  | </xs:simpleType> |

|  | <xs:simpleType name="transactionType"> |

|  | <xs:restriction base="xs:string"> |

|  | <xs:enumeration value="SESSION_WRITEOFF"/> |

|  | <xs:enumeration value="OUTGOING_SALES_DOCUMENT_PAYMENT"/> |

|  | <xs:enumeration value="PREPAY_CLOSED"/> |

|  | <xs:enumeration value="CASH_SURPLUS"/> |

|  | <xs:enumeration value="RETURNED_INVOICE"/> |

|  | <xs:enumeration value="CREDIT"/> |

|  | <xs:enumeration value="CASH_SHORTAGE"/> |

|  | <xs:enumeration value="OUTGOING_SERVICE"/> |

|  | <xs:enumeration value="STORE_COST_CORRECTION"/> |

|  | <xs:enumeration value="SALES_REVENUE"/> |

|  | <xs:enumeration value="ADVANCE"/> |

|  | <xs:enumeration value="PAYOUT"/> |

|  | <xs:enumeration value="INVOICE_PAYMENT"/> |

|  | <xs:enumeration value="OUTGOING_DOCUMENT_PAYMENT"/> |

|  | <xs:enumeration value="TARIFF_HOUR"/> |

|  | <xs:enumeration value="TRANSFER"/> |

|  | <xs:enumeration value="WRITEOFF"/> |

|  | <xs:enumeration value="SALES_RETURN_WRITEOFF"/> |

|  | <xs:enumeration value="CARD"/> |

|  | <xs:enumeration value="PREPAY_CLOSED_RETURN"/> |

|  | <xs:enumeration value="PRODUCTION"/> |

|  | <xs:enumeration value="EMPLOYEE_CASH_PAYMENT"/> |

|  | <xs:enumeration value="DISCOUNT"/> |

|  | <xs:enumeration value="OUTGOING_INVOICE"/> |

|  | <xs:enumeration value="INVENTORY_CORRECTION"/> |

|  | <xs:enumeration value="IMPORTED_BANK_STATEMENT"/> |

|  | <xs:enumeration value="INCENTIVE_PAYMENT"/> |

|  | <xs:enumeration value="NDS_INCOMING"/> |

|  | <xs:enumeration value="DISASSEMBLE"/> |

|  | <xs:enumeration value="CASH"/> |

|  | <xs:enumeration value="OPENING_BALANCE"/> |

|  | <xs:enumeration value="INCOMING_SERVICE"/> |

|  | <xs:enumeration value="TRANSFORMATION"/> |

|  | <xs:enumeration value="BONUS"/> |

|  | <xs:enumeration value="SESSION_ACCEPTANCE"/> |

|  | <xs:enumeration value="PREPAY_RETURN"/> |

|  | <xs:enumeration value="ON_THE_HOUSE"/> |

|  | <xs:enumeration value="EMPLOYEE_PAYMENT"/> |

|  | <xs:enumeration value="SALES_RETURN_PAYMENT"/> |

|  | <xs:enumeration value="INVOICE"/> |

|  | <xs:enumeration value="PENALTY"/> |

|  | <xs:enumeration value="OUTGOING_SERVICE_PAYMENT"/> |

|  | <xs:enumeration value="CLOSE_AT_EMPLOYEE_EXPENSE"/> |

|  | <xs:enumeration value="PAY_COLLECTION"/> |

|  | <xs:enumeration value="TARIFF_PERCENT"/> |

|  | <xs:enumeration value="INCOMING_SERVICE_PAYMENT"/> |

|  | <xs:enumeration value="PAYIN"/> |

|  | <xs:enumeration value="RETURNED_INVOICE_REVENUE"/> |

|  | <xs:enumeration value="NDS_SALES"/> |


---


## Page 14

API Documentation Page14 of 15
<xs:enumeration value="OUTGOING_INVOICE_REVENUE"/>
<xs:enumeration value="PREPAY"/>
<xs:enumeration value="CUSTOM"/>
<xs:enumeration value="CASH_CORRECTION"/>
</xs:restriction>
</xs:simpleType>
<xs:simpleType name="documentType">
<xs:restriction base="xs:string">
<xs:enumeration value="INCOMING_INVOICE"/>
<xs:enumeration value="INTERNAL_TRANSFER"/>
<xs:enumeration value="TRANSFORMATION_DOCUMENT"/>
<xs:enumeration value="PAYROLL"/>
<xs:enumeration value="DISASSEMBLE_DOCUMENT"/>
<xs:enumeration value="OUTGOING_INVOICE"/>
<xs:enumeration value="MENU_CHANGE"/>
<xs:enumeration value="OUTGOING_CASH_ORDER"/>
<xs:enumeration value="PREPARED_REGISTER"/>
<xs:enumeration value="SALES_RETURN_DOCUMENT"/>
<xs:enumeration value="INCOMING_CASH_ORDER"/>
<xs:enumeration value="SALES_DOCUMENT"/>
<xs:enumeration value="WRITEOFF_DOCUMENT"/>
<xs:enumeration value="PRODUCTION_ORDER"/>
<xs:enumeration value="FUEL_ACCEPTANCE"/>
<xs:enumeration value="PRODUCTION_DOCUMENT"/>
<xs:enumeration value="PRODUCT_REPLACEMENT"/>
<xs:enumeration value="SESSION_ACCEPTANCE"/>
<xs:enumeration value="RETURNED_INVOICE"/>
<xs:enumeration value="INCOMING_SERVICE"/>
<xs:enumeration value="FUEL_GAGING_DOCUMENT"/>
<xs:enumeration value="CONSOLIDATED_ORDER"/>
<xs:enumeration value="OUTGOING_SERVICE"/>
<xs:enumeration value="INCOMING_INVENTORY"/>
</xs:restriction>
</xs:simpleType>
<xs:simpleType name="storeDataDirection">
<xs:restriction base="xs:string">
<xs:enumeration value="IN"/>
<xs:enumeration value="INOUT"/>
<xs:enumeration value="OUT"/>
</xs:restriction>
</xs:simpleType>
</xs:schema>
[+] XSDРасходпродуктовпопродажам
[-] XSDРасходпродуктовпопродажам
Copy Code
XML
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <xs:enumeration value="OUTGOING_INVOICE_REVENUE"/> |

|  | <xs:enumeration value="PREPAY"/> |

|  | <xs:enumeration value="CUSTOM"/> |

|  | <xs:enumeration value="CASH_CORRECTION"/> |

|  | </xs:restriction> |

|  | </xs:simpleType> |

|  | <xs:simpleType name="documentType"> |

|  | <xs:restriction base="xs:string"> |

|  | <xs:enumeration value="INCOMING_INVOICE"/> |

|  | <xs:enumeration value="INTERNAL_TRANSFER"/> |

|  | <xs:enumeration value="TRANSFORMATION_DOCUMENT"/> |

|  | <xs:enumeration value="PAYROLL"/> |

|  | <xs:enumeration value="DISASSEMBLE_DOCUMENT"/> |

|  | <xs:enumeration value="OUTGOING_INVOICE"/> |

|  | <xs:enumeration value="MENU_CHANGE"/> |

|  | <xs:enumeration value="OUTGOING_CASH_ORDER"/> |

|  | <xs:enumeration value="PREPARED_REGISTER"/> |

|  | <xs:enumeration value="SALES_RETURN_DOCUMENT"/> |

|  | <xs:enumeration value="INCOMING_CASH_ORDER"/> |

|  | <xs:enumeration value="SALES_DOCUMENT"/> |

|  | <xs:enumeration value="WRITEOFF_DOCUMENT"/> |

|  | <xs:enumeration value="PRODUCTION_ORDER"/> |

|  | <xs:enumeration value="FUEL_ACCEPTANCE"/> |

|  | <xs:enumeration value="PRODUCTION_DOCUMENT"/> |

|  | <xs:enumeration value="PRODUCT_REPLACEMENT"/> |

|  | <xs:enumeration value="SESSION_ACCEPTANCE"/> |

|  | <xs:enumeration value="RETURNED_INVOICE"/> |

|  | <xs:enumeration value="INCOMING_SERVICE"/> |

|  | <xs:enumeration value="FUEL_GAGING_DOCUMENT"/> |

|  | <xs:enumeration value="CONSOLIDATED_ORDER"/> |

|  | <xs:enumeration value="OUTGOING_SERVICE"/> |

|  | <xs:enumeration value="INCOMING_INVENTORY"/> |

|  | </xs:restriction> |

|  | </xs:simpleType> |

|  | <xs:simpleType name="storeDataDirection"> |

|  | <xs:restriction base="xs:string"> |

|  | <xs:enumeration value="IN"/> |

|  | <xs:enumeration value="INOUT"/> |

|  | <xs:enumeration value="OUT"/> |

|  | </xs:restriction> |

|  | </xs:simpleType> |

|  | </xs:schema> |

|  |  |



### Table:

| Copy Code |  |  |

|---|---|---|

|  | XML |  |

|  |  |  |


---


## Page 15

API Documentation Page15 of 15
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:element name="dayDishValue" type="dayDishValue"/>
<xs:complexType name="dayDishValue">
<xs:sequence>
<xs:element name="date" type="xs:string" minOccurs="0"/>
<xs:element name="productId" type="xs:string" minOccurs="0"/>
<xs:element name="productName" type="xs:string" minOccurs="0"/>
<xs:element name="value" type="xs:decimal" minOccurs="0"/>
</xs:sequence>
</xs:complexType>
</xs:schema>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <?xml version="1.0" encoding="UTF-8" standalone="yes"?> |

|  | <xs:schema version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema"> |

|  | <xs:element name="dayDishValue" type="dayDishValue"/> |

|  | <xs:complexType name="dayDishValue"> |

|  | <xs:sequence> |

|  | <xs:element name="date" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="productId" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="productName" type="xs:string" minOccurs="0"/> |

|  | <xs:element name="value" type="xs:decimal" minOccurs="0"/> |

|  | </xs:sequence> |

|  | </xs:complexType> |

|  | </xs:schema> |

|  |  |


---
