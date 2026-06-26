* [Content-Type: application/xml](/articles/api-documentations/zagruzka-i-redaktirovanie-prikhodnoy-nakladnoy/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/zagruzka-i-redaktirovanie-prikhodnoy-nakladnoy/a/h3_501454233)
* [Пример запроса и результата](/articles/api-documentations/zagruzka-i-redaktirovanie-prikhodnoy-nakladnoy/a/h3_1561844723)

Версия iiko: 3.9 (редактирование с 5.2)

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/documents/import/incomingInvoice |
| --- | --- |

### Content-Type: application/xml

### Тело запроса

Формат даты по полям метода загрузки приходной накладной:
&lt;dateIncoming&gt;dd.mm.YYYY&lt;/dateIncoming&gt;
&lt;dueDate&gt;dd.mm.YYYY&lt;/dueDate&gt;
&lt;incomingDate&gt;YYYY-mm-dd&lt;/incomingDate&gt;
[+] [XSD Приходная накладная](javascript:void%280%29)
 [-] [XSD Приходная накладная](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
### Что в ответе

Структура *documentValidationResult*

 [+] [XSD Результат валидации документа](javascript:void%280%29)
 [-] [XSD Результат валидации документа](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 
Пример расчета количества и цены товара:

При формировании приходной накладной есть позиция с продуктом в ящиках с базовыми единицами в кг.

Например, 5 ящиков по 1000 руб каждый, и в каждом ящике по 10 кг. Тогда заполнятся следующие поля:

"в ед." (&lt;amount&gt;) - 5\*10= 50

"Фактическое количество" (&lt;actualAmount&gt;) - 5\*10=50/documents/export/incomingInvoice

"Цена базовой единицы" (&lt;price&gt;) - 1000/10=100

Если фасовки нет, то эти поля заполняются количеством товара в единицах измерения.

###  **Пример запроса и результата**

**Запрос**
https://localhost:8080/resto/api/documents/import/incomingInvoice?key=ddb22676-38a7-afb4-d02a-d5f6898d64cc


```xml


<document>
  <items>
    <item>
      <amount>3.00</amount>
      <supplierProduct>BF1DA0F2-B511-431E-BC7D-F2A68715054B</supplierProduct>
      <product>0F22AA60-E8AE-4C8E-80CD-F1E00B88FEC6</product>
      <num>1</num>
      <containerId>00000000-0000-0000-0000-000000000000</containerId>
      <amountUnit>6040D92D-E286-F4F9-A613-ED0E6FD241E1</amountUnit>
      <actualUnitWeight/>
      <discountSum>0.00</discountSum>
      <sumWithoutNds>30.00</sumWithoutNds>
      <ndsPercent>0.00</ndsPercent>
      <sum>30.00</sum>
      <priceUnit/>
      <price>10.00</price>
      <code>25753</code>
      <store>1239d270-1bbe-f64f-b7ea-5f00518ef508</store>
      <customsDeclarationNumber>cdn-7</customsDeclarationNumber>
      <actualAmount>3.00</actualAmount>
    </item>
  <item>
      <amount>4.00</amount>
      <supplierProduct>18C66E42-9A71-402A-81B0-A0DAA8E74F4B</supplierProduct>
      <product>B2D954CE-FC7A-44FF-9987-35AF59F16966</product>
      <num>2</num>
      <containerId>00000000-0000-0000-0000-000000000000</containerId>
      <amountUnit>6040D92D-E286-F4F9-A613-ED0E6FD241E1</amountUnit>
      <actualUnitWeight/>
      <discountSum>0.00</discountSum>
      <sumWithoutNds>80.00</sumWithoutNds>
      <ndsPercent>0.00</ndsPercent>
      <sum>80.00</sum>
      <priceUnit/>
      <price>20.00</price>
      <code>25752</code>
      <store>1239d270-1bbe-f64f-b7ea-5f00518ef508</store>
      <customsDeclarationNumber>cdn-7</customsDeclarationNumber>
      <actualAmount>4.00</actualAmount>
    </item>
  </items>
  <conception>2609B25F-2180-BF98-5C1C-967664EEA837</conception>
  <comment>comment-7</comment>
  <documentNumber>dn-7</documentNumber>
  <dateIncoming>17.12.2014</dateIncoming>
  <useDefaultDocumentTime>true</useDefaultDocumentTime>
  <invoice>in-7</invoice>
  <defaultStore>1239d270-1bbe-f64f-b7ea-5f00518ef508</defaultStore>
  <supplier>3F08E41C-AA25-4573-B1E0-60B3B8A09F6A</supplier>
  <dueDate>27.12.2014</dueDate>
  <incomingDocumentNumber>idn-7</incomingDocumentNumber>
  <employeePassToAccount>9e1a4e13-f811-4dea-94b4-575b2cf0f2f8</employeePassToAccount>
  <transportInvoiceNumber>tin-7</transportInvoiceNumber>
</document>
```

```xml


<document>
  <items>
    <item>
      <amount>3.00</amount>
      <supplierProduct>BF1DA0F2-B511-431E-BC7D-F2A68715054B</supplierProduct>
      <product>0F22AA60-E8AE-4C8E-80CD-F1E00B88FEC6</product>
      <num>1</num>
      <containerId>00000000-0000-0000-0000-000000000000</containerId>
      <amountUnit>6040D92D-E286-F4F9-A613-ED0E6FD241E1</amountUnit>
      <actualUnitWeight/>
      <discountSum>0.00</discountSum>
      <sumWithoutNds>30.00</sumWithoutNds>
      <ndsPercent>0.00</ndsPercent>
      <sum>30.00</sum>
      <priceUnit/>
      <price>10.00</price>
      <code>25753</code>
      <store>1239d270-1bbe-f64f-b7ea-5f00518ef508</store>
      <customsDeclarationNumber>cdn-7</customsDeclarationNumber>
      <actualAmount>3.00</actualAmount>
    </item>
  <item>
      <amount>4.00</amount>
      <supplierProduct>18C66E42-9A71-402A-81B0-A0DAA8E74F4B</supplierProduct>
      <product>B2D954CE-FC7A-44FF-9987-35AF59F16966</product>
      <num>2</num>
      <containerId>00000000-0000-0000-0000-000000000000</containerId>
      <amountUnit>6040D92D-E286-F4F9-A613-ED0E6FD241E1</amountUnit>
      <actualUnitWeight/>
      <discountSum>0.00</discountSum>
      <sumWithoutNds>80.00</sumWithoutNds>
      <ndsPercent>0.00</ndsPercent>
      <sum>80.00</sum>
      <priceUnit/>
      <price>20.00</price>
      <code>25752</code>
      <store>1239d270-1bbe-f64f-b7ea-5f00518ef508</store>
      <customsDeclarationNumber>cdn-7</customsDeclarationNumber>
      <actualAmount>4.00</actualAmount>
    </item>
  </items>
  <conception>2609B25F-2180-BF98-5C1C-967664EEA837</conception>
  <comment>comment-7</comment>
  <documentNumber>dn-7</documentNumber>
  <dateIncoming>17.12.2014</dateIncoming>
  <useDefaultDocumentTime>true</useDefaultDocumentTime>
  <invoice>in-7</invoice>
  <defaultStore>1239d270-1bbe-f64f-b7ea-5f00518ef508</defaultStore>
  <supplier>3F08E41C-AA25-4573-B1E0-60B3B8A09F6A</supplier>
  <dueDate>27.12.2014</dueDate>
  <incomingDocumentNumber>idn-7</incomingDocumentNumber>
  <employeePassToAccount>9e1a4e13-f811-4dea-94b4-575b2cf0f2f8</employeePassToAccount>
  <transportInvoiceNumber>tin-7</transportInvoiceNumber>
</document>
```


**Результат**


```xml
HTTP/1.1 200 OK
Server: Apache-Coyote/1.1 
Vary: Accept-Encoding
Content-Type: application/xml 
Content-Length: 188
Date: Wed, 17 Dec 2014 11:27:26 GMT 
<?xml version="1.0" encoding="UTF-8" standalone="yes"?> 
<documentValidationResult> 
  <documentNumber>dn-7</documentNumber>  
  <valid>true</valid> 
  <warning>false</warning>
</documentValidationResult>
```

```xml
HTTP/1.1 200 OK
Server: Apache-Coyote/1.1 
Vary: Accept-Encoding
Content-Type: application/xml 
Content-Length: 188
Date: Wed, 17 Dec 2014 11:27:26 GMT 
<?xml version="1.0" encoding="UTF-8" standalone="yes"?> 
<documentValidationResult> 
  <documentNumber>dn-7</documentNumber>  
  <valid>true</valid> 
  <warning>false</warning>
</documentValidationResult>
```
