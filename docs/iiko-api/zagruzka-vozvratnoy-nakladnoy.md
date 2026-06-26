* [Тело запроса](/articles/api-documentations/zagruzka-vozvratnoy-nakladnoy/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/zagruzka-vozvratnoy-nakladnoy/a/h3_501454233)
* [Пример вызова и результата](/articles/api-documentations/zagruzka-vozvratnoy-nakladnoy/a/h3_41887754)

Версия iiko: 4.4

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/documents/import/returnedInvoice |
| --- | --- |

Content-Type: application/xml

### Тело запроса

Структура *returnedInvoiceDto*
 [+] [XSD Возвратная накладная](javascript:void%280%29)
 [-] [XSD Возвратная накладная](javascript:void%280%29)
 
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


### **Пример вызова и результата**

**Запрос**


```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<document>
  <documentNumber>TAKT0003</documentNumber>
  <dateIncoming>2016-05-03T00:12:35</dateIncoming>
  <status>PROCESSED</status>
  <incomingInvoiceNumber>TAKT0001</incomingInvoiceNumber>
  <incomingInvoiceDate>2016-05-01</incomingInvoiceDate>
  <counteragentId>4F1AC4B8-21AC-4FE6-8BEB-464EA10C5FFB</counteragentId>
  <items>
    <item>
      <storeId>84A2C3D1-488B-42F4-96C1-4670F7D08583</storeId>
      <productId>FBCC2C7A-9B52-4FDB-8B95-4C9725273DE4</productId>
      <price>30</price>
      <amount>10</amount>
      <sum>300</sum>
      <vatPercent>12</vatPercent>
      <vatSum>32.20</vatSum>
    </item>
  </items>
</document>

```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<document>
  <documentNumber>TAKT0003</documentNumber>
  <dateIncoming>2016-05-03T00:12:35</dateIncoming>
  <status>PROCESSED</status>
  <incomingInvoiceNumber>TAKT0001</incomingInvoiceNumber>
  <incomingInvoiceDate>2016-05-01</incomingInvoiceDate>
  <counteragentId>4F1AC4B8-21AC-4FE6-8BEB-464EA10C5FFB</counteragentId>
  <items>
    <item>
      <storeId>84A2C3D1-488B-42F4-96C1-4670F7D08583</storeId>
      <productId>FBCC2C7A-9B52-4FDB-8B95-4C9725273DE4</productId>
      <price>30</price>
      <amount>10</amount>
      <sum>300</sum>
      <vatPercent>12</vatPercent>
      <vatSum>32.20</vatSum>
    </item>
  </items>
</document>

```


**Результат**


```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<documentValidationResult>
    <valid>false</valid>
    <warning>false</warning>
    <documentNumber>400234</documentNumber>
    <errorMessage>Cannot find document of type INCOMING_INVOICE by number 'TAKT0001' and date '2016-05-01'</errorMessage>
</documentValidationResult>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<documentValidationResult>
    <valid>false</valid>
    <warning>false</warning>
    <documentNumber>400234</documentNumber>
    <errorMessage>Cannot find document of type INCOMING_INVOICE by number 'TAKT0001' and date '2016-05-01'</errorMessage>
</documentValidationResult>
```


##  

##
