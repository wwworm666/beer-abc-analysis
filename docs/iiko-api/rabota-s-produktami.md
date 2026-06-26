* [Список продуктов](/articles/api-documentations/rabota-s-produktami/a/h2_887569233)
* [Параметры запроса](/articles/api-documentations/rabota-s-produktami/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/rabota-s-produktami/a/h3__1629008397)
* [Пример запроса](/articles/api-documentations/rabota-s-produktami/a/h3_1387997121)
* [Поиск продуктов](/articles/api-documentations/rabota-s-produktami/a/h2__1148248612)
* [Параметры запроса](/articles/api-documentations/rabota-s-produktami/a/h3__1009070187)
* [Что в ответе](/articles/api-documentations/rabota-s-produktami/a/h3_501454233)
* [Пример запроса](/articles/api-documentations/rabota-s-produktami/a/h3_1070623621)
* [Особенности](/articles/api-documentations/rabota-s-produktami/a/h3__472055080)
* [XSD Продукт](/articles/api-documentations/rabota-s-produktami/a/h2__1759051791)

##  Список продуктов

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **https://localhost:8080/resto/api/products** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| includeDeleted | true/false | Включать ли удаленные элементы номенклатуры в результат. По умолчанию false. Реализовано в 5.0 и новее |
| revisionFrom | -1 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

### Что в ответе

###  

####  

Все активные (не удаленные) продукты по типам. Включая товары поставщика. В формате *ProductDto* (см. XSD Продукт).
 
См. расшифровки возможных типов в разделах "Расшифровки кодов базовых типов - Тип элемента номенклатуры" и "Расшифровки кодов базовых типов - Типы групп продукта"
 
**Тип элемента номенклатуры**

| Код | Название |
| --- | --- |
| GOODS | Товар |
| DISH | Блюдо |
| PREPARED | Заготовка |
| SERVICE | Услуга |
| MODIFIER | Модификатор |
| OUTER | Внешние товары |
| PETROL | Топливо |
| RATE | Тариф |

**Типы групп продукта**

| Код | Название | Комментарий |
| --- | --- | --- |
| PRODUCTS | Продукт |  |
| MODIFIERS | Модификатор | Используется только в номенклатуре, которая загружается и выгружается в/из RKeeper/StoreHouse |

###  Пример запроса 

****

https://localhost:8080/resto/api/products?key=754a4184-a626-d2eb-c7a9-94d8244b5ca7&revisionFrom=-1

##  Поиск продуктов

Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **https://localhost:8080/resto/api/products/search** |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| includeDeleted | true/false | Включать ли удаленные элементы номенклатуры в результат. По умолчанию false. Реализовано в 5.0 и новее |
| name | {regexp} - регулярное выражение | Название |
| code | {regexp} - регулярное выражение | Код быстрого набора в IikoFront |
| mainUnit | {regexp} - регулярное выражение | Базовая единица измерения |
| num | {regexp} - регулярное выражение | Артикул |
| cookingPlaceType | {regexp} - регулярное выражение | Тип места приготовления |
| productGroupType | {regexp} - регулярное выражение | Тип родительской группы |
| productType | {regexp} - регулярное выражение | Тип номенклатуры |

### Что в ответе

*ProductDto*, если существует продукт, удовлетворяющий значениям переданных параметров (см. XSD Продукт).

### **Пример запроса** 

https://localhost:8080/resto/api/products/search?key=754a4184-a626-d2eb-c7a9-94d8244b5ca7&productGroupType=P

###  Особенности 

Выгрузка и поиск идет по всем не удаленным элементам номенклатуры. Включая товары поставщика, т.к. сейчас нет возможности удалить товар поставщика, то выгрузка потянет все товары поставщика, даже те, которые реально не используются и не участвуют ни в одной связке товар у нас — товар поставщика.

##  XSD Продукт 


```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" version="1.0">
    <xs:element name="productDtoes">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="productDto" type="productDto" minOccurs="0" maxOccurs="unbounded"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
    <xs:complexType name="productDto">
        <xs:sequence>
            <!-- id продукта (guid)  -->
            <xs:element name="id" type="xs:string" minOccurs="0"/>
            <!-- Родительская группа  -->
            <xs:element name="parentId" type="xs:string" minOccurs="0"/>
            <!-- Артикул  -->
            <xs:element name="num" type="xs:string" minOccurs="0"/>
            <!-- Код быстрого набора в IikoFront  -->
            <xs:element name="code" type="xs:string" minOccurs="0"/>
            <!-- Название  -->
            <xs:element name="name" type="xs:string"/>
            <!-- Тип номенклатуры  -->
            <xs:element name="productType" type="productType_enum" minOccurs="0"/>
            <!-- Тип родительской группы  -->
            <xs:element name="productGroupType" type="productGroupType_enum" minOccurs="0"/>
            <!-- Тип места приготовления  -->
            <xs:element name="cookingPlaceType" type="xs:string" minOccurs="0"/>
            <!-- Базовая единица измерения  -->
            <xs:element name="mainUnit" type="xs:string" minOccurs="0"/>
            <!-- Категория продукта (с 5.0) -->
            <xs:element name="productCategory" type="xs:string" minOccurs="0"/>
            <!-- Фасовки (начиная с 4.4.1053.0) -->
            <xs:element name="containers" minOccurs="0">
                <xs:complexType>
                    <xs:sequence>
                        <xs:element name="container" type="containerDto" minOccurs="0" maxOccurs="unbounded"/>
                    </xs:sequence>
                </xs:complexType>
            </xs:element>
            <!-- Штрих-коды (начиная с 4.4.1053.0) -->
            <xs:element name="barcodes" minOccurs="0">
                <xs:complexType>
                    <xs:sequence>
                        <xs:element name="barcodeContainer" type="barcodeContainerDto" minOccurs="0" maxOccurs="unbounded"/>
                    </xs:sequence>
                </xs:complexType>
            </xs:element>
        </xs:sequence>
    </xs:complexType>
    <xs:complexType name="containerDto">
        <xs:sequence>
            <xs:element name="id" type="xs:string" minOccurs="0"/>
            <xs:element name="num" type="xs:string" minOccurs="0"/>
            <xs:element name="name" type="xs:string"/>
            <xs:element name="count" type="xs:decimal" minOccurs="0"/>
            <xs:element name="minContainerWeight" type="xs:decimal" minOccurs="0"/>
            <xs:element name="maxContainerWeight" type="xs:decimal" minOccurs="0"/>
            <xs:element name="containerWeight" type="xs:decimal" minOccurs="0"/>
            <xs:element name="fullContainerWeight" type="xs:decimal" minOccurs="0"/>
            <xs:element name="density" type="xs:decimal" minOccurs="0"/>
            <xs:element name="backwardRecalculation" type="xs:boolean" minOccurs="0"/>
            <xs:element name="deleted" type="xs:boolean"/>
            <xs:element name="useInFront" type="xs:boolean" minOccurs="0"/>
        </xs:sequence>
    </xs:complexType>
    <xs:complexType name="barcodeContainerDto">
        <xs:sequence>
            <xs:element name="barcode" type="xs:string"/>
            <xs:element name="containerName" type="xs:string" minOccurs="0"/>
        </xs:sequence>
    </xs:complexType>
    <xs:simpleType name="productType_enum">
        <xs:restriction base="xs:string">
            <xs:enumeration value="GOODS"/>
            <xs:enumeration value="DISH"/>
            <xs:enumeration value="PREPARED"/>
            <xs:enumeration value="SERVICE"/>
            <xs:enumeration value="MODIFIER"/>
            <xs:enumeration value="OUTER"/>
            <xs:enumeration value="PETROL"/>
            <xs:enumeration value="RATE"/>
        </xs:restriction>
    </xs:simpleType>
    <xs:simpleType name="productGroupType_enum">
        <xs:restriction base="xs:string">
            <xs:enumeration value="PRODUCTS"/>
            <xs:enumeration value="MODIFIERS"/>
        </xs:restriction>
    </xs:simpleType>
</xs:schema>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" version="1.0">
    <xs:element name="productDtoes">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="productDto" type="productDto" minOccurs="0" maxOccurs="unbounded"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
    <xs:complexType name="productDto">
        <xs:sequence>
            <!-- id продукта (guid)  -->
            <xs:element name="id" type="xs:string" minOccurs="0"/>
            <!-- Родительская группа  -->
            <xs:element name="parentId" type="xs:string" minOccurs="0"/>
            <!-- Артикул  -->
            <xs:element name="num" type="xs:string" minOccurs="0"/>
            <!-- Код быстрого набора в IikoFront  -->
            <xs:element name="code" type="xs:string" minOccurs="0"/>
            <!-- Название  -->
            <xs:element name="name" type="xs:string"/>
            <!-- Тип номенклатуры  -->
            <xs:element name="productType" type="productType_enum" minOccurs="0"/>
            <!-- Тип родительской группы  -->
            <xs:element name="productGroupType" type="productGroupType_enum" minOccurs="0"/>
            <!-- Тип места приготовления  -->
            <xs:element name="cookingPlaceType" type="xs:string" minOccurs="0"/>
            <!-- Базовая единица измерения  -->
            <xs:element name="mainUnit" type="xs:string" minOccurs="0"/>
            <!-- Категория продукта (с 5.0) -->
            <xs:element name="productCategory" type="xs:string" minOccurs="0"/>
            <!-- Фасовки (начиная с 4.4.1053.0) -->
            <xs:element name="containers" minOccurs="0">
                <xs:complexType>
                    <xs:sequence>
                        <xs:element name="container" type="containerDto" minOccurs="0" maxOccurs="unbounded"/>
                    </xs:sequence>
                </xs:complexType>
            </xs:element>
            <!-- Штрих-коды (начиная с 4.4.1053.0) -->
            <xs:element name="barcodes" minOccurs="0">
                <xs:complexType>
                    <xs:sequence>
                        <xs:element name="barcodeContainer" type="barcodeContainerDto" minOccurs="0" maxOccurs="unbounded"/>
                    </xs:sequence>
                </xs:complexType>
            </xs:element>
        </xs:sequence>
    </xs:complexType>
    <xs:complexType name="containerDto">
        <xs:sequence>
            <xs:element name="id" type="xs:string" minOccurs="0"/>
            <xs:element name="num" type="xs:string" minOccurs="0"/>
            <xs:element name="name" type="xs:string"/>
            <xs:element name="count" type="xs:decimal" minOccurs="0"/>
            <xs:element name="minContainerWeight" type="xs:decimal" minOccurs="0"/>
            <xs:element name="maxContainerWeight" type="xs:decimal" minOccurs="0"/>
            <xs:element name="containerWeight" type="xs:decimal" minOccurs="0"/>
            <xs:element name="fullContainerWeight" type="xs:decimal" minOccurs="0"/>
            <xs:element name="density" type="xs:decimal" minOccurs="0"/>
            <xs:element name="backwardRecalculation" type="xs:boolean" minOccurs="0"/>
            <xs:element name="deleted" type="xs:boolean"/>
            <xs:element name="useInFront" type="xs:boolean" minOccurs="0"/>
        </xs:sequence>
    </xs:complexType>
    <xs:complexType name="barcodeContainerDto">
        <xs:sequence>
            <xs:element name="barcode" type="xs:string"/>
            <xs:element name="containerName" type="xs:string" minOccurs="0"/>
        </xs:sequence>
    </xs:complexType>
    <xs:simpleType name="productType_enum">
        <xs:restriction base="xs:string">
            <xs:enumeration value="GOODS"/>
            <xs:enumeration value="DISH"/>
            <xs:enumeration value="PREPARED"/>
            <xs:enumeration value="SERVICE"/>
            <xs:enumeration value="MODIFIER"/>
            <xs:enumeration value="OUTER"/>
            <xs:enumeration value="PETROL"/>
            <xs:enumeration value="RATE"/>
        </xs:restriction>
    </xs:simpleType>
    <xs:simpleType name="productGroupType_enum">
        <xs:restriction base="xs:string">
            <xs:enumeration value="PRODUCTS"/>
            <xs:enumeration value="MODIFIERS"/>
        </xs:restriction>
    </xs:simpleType>
</xs:schema>
```
