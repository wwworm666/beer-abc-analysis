* [Тело запроса](/articles/api-documentations/zagruzka-akta-realizatsii/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/zagruzka-akta-realizatsii/a/h3_501454233)
* [Пример вызова и результата](/articles/api-documentations/zagruzka-akta-realizatsii/a/h3_41887754)

Версия iiko: 3.9

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/documents/import/salesDocument |
| --- | --- |

Content-Type: application/xml

### Тело запроса

Структура *salesDocumentDto*
 [+] [XSD Акт реализации](javascript:void%280%29)
 [-] [XSD Акт реализации](javascript:void%280%29)
 
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

https://localhost:8080/resto/api/documents/import/salesDocument?key=d5e3186a-b5a9-edf7-5164-ca55e29fe5e1


```xml
<document>
  <items>
    <!--Zero or more repetitions:-->
      <item>
              <discountSum>11.00</discountSum>
              <sum>110.00</sum>
              <amount>3.00</amount>
              <productId>0f22aa60-e8ae-4c8e-80cd-f1e00b88fec6</productId>
              <productArticle>25753</productArticle>
              <storeId>1239D270-1BBE-F64F-B7EA-5F00518EF508</storeId>
      </item>
      <item>
              <discountSum>22.00</discountSum>
              <sum>220.00</sum>
              <amount>5.00</amount>
              <productId>b2d954ce-fc7a-44ff-9987-35af59f16966</productId>
              <productArticle>25752</productArticle>
              <storeId>153212ad-21af-4eeb-85c0-245822db3a70</storeId>
      </item>
  </items>
  <status>NEW</status>
  <accountToCode>5.01</accountToCode>
  <revenueAccountCode>4.01</revenueAccountCode>
  <documentNumber>api-015</documentNumber>
  <dateIncoming>17.12.2014</dateIncoming>
</document>

```

```xml
<document>
  <items>
    <!--Zero or more repetitions:-->
      <item>
              <discountSum>11.00</discountSum>
              <sum>110.00</sum>
              <amount>3.00</amount>
              <productId>0f22aa60-e8ae-4c8e-80cd-f1e00b88fec6</productId>
              <productArticle>25753</productArticle>
              <storeId>1239D270-1BBE-F64F-B7EA-5F00518EF508</storeId>
      </item>
      <item>
              <discountSum>22.00</discountSum>
              <sum>220.00</sum>
              <amount>5.00</amount>
              <productId>b2d954ce-fc7a-44ff-9987-35af59f16966</productId>
              <productArticle>25752</productArticle>
              <storeId>153212ad-21af-4eeb-85c0-245822db3a70</storeId>
      </item>
  </items>
  <status>NEW</status>
  <accountToCode>5.01</accountToCode>
  <revenueAccountCode>4.01</revenueAccountCode>
  <documentNumber>api-015</documentNumber>
  <dateIncoming>17.12.2014</dateIncoming>
</document>

```


**Результат**


```xml
HTTP/1.1 200 OK
Server: Apache-Coyote/1.1
Vary: Accept-Encoding
Content-Type: application/xml
Content-Length: 191
Date: Wed, 17 Dec 2014 09:16:36 GMT

<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<documentValidationResult>
  <documentNumber>api-015</documentNumber>
  <valid>true</valid>
  <warning>false</warning>
</documentValidationResult>
```

```xml
HTTP/1.1 200 OK
Server: Apache-Coyote/1.1
Vary: Accept-Encoding
Content-Type: application/xml
Content-Length: 191
Date: Wed, 17 Dec 2014 09:16:36 GMT

<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<documentValidationResult>
  <documentNumber>api-015</documentNumber>
  <valid>true</valid>
  <warning>false</warning>
</documentValidationResult>
```


##  

##
