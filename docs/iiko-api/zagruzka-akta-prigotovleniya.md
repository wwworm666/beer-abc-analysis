* [Тело запроса](/articles/api-documentations/zagruzka-akta-prigotovleniya/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/zagruzka-akta-prigotovleniya/a/h3_501454233)
* [Пример вызова и результат](/articles/api-documentations/zagruzka-akta-prigotovleniya/a/h3_41887754)

Версия iiko: 3.9

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/documents/import/productionDocument |
| --- | --- |

Content-Type: application/xml

### **Тело запроса**

Структура *productionDocumentDto*

[+] [XSD Акт приготовления](javascript:void%280%29)
 [-] [XSD Акт приготовления](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
### **Что в ответе**

Структура *documentValidationResult*
 [+] [XSD Результат валидации документа](javascript:void%280%29)
 [-] [XSD Результат валидации документа](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```


### **Пример вызова и результат**

**Запрос**

https://localhost:8080/resto/api/documents/import/productionDocument?key=d7474d4a-0a40-d918-85fa-2cd98fddfeb1


```xml
<document>
  <!--Со склада (guid)-->
  <storeFrom>1239d270-1bbe-f64f-b7ea-5f00518ef508</storeFrom>
   <!--На склад (guid)-->
  <storeTo>1239d270-1bbe-f64f-b7ea-5f00518ef508</storeTo>
   <!--Дата документа-->
  <dateIncoming>17.12.2014</dateIncoming>
   <!--Номер документа-->
  <documentNumber>api-0002</documentNumber>
   <!--Комментарий-->
  <comment>api test api-0002</comment>
  <!--Статус Проведен -->
  <status>PROCESSED</status>
   <items>
       <item>
          <!--Фасовка (guid)-->
          <amountUnit>cd19b5ea-1b32-a6e5-1df7-5d2784a0549a</amountUnit>
           <!--Контейнер (guid)-->
          <containerId>C66196B6-68F2-4C17-97C2-C2008A39A76A</containerId>   
          <!--Порядковый номер в документе-->
          <num>1</num>
          <!--Товар (guid)-->
          <product>0f22aa60-e8ae-4c8e-80cd-f1e00b88fec6</product>
          <!--Количество-->
        <amount>1</amount>
        </item> 
    </items>
  </document>
```

```xml
<document>
  <!--Со склада (guid)-->
  <storeFrom>1239d270-1bbe-f64f-b7ea-5f00518ef508</storeFrom>
   <!--На склад (guid)-->
  <storeTo>1239d270-1bbe-f64f-b7ea-5f00518ef508</storeTo>
   <!--Дата документа-->
  <dateIncoming>17.12.2014</dateIncoming>
   <!--Номер документа-->
  <documentNumber>api-0002</documentNumber>
   <!--Комментарий-->
  <comment>api test api-0002</comment>
  <!--Статус Проведен -->
  <status>PROCESSED</status>
   <items>
       <item>
          <!--Фасовка (guid)-->
          <amountUnit>cd19b5ea-1b32-a6e5-1df7-5d2784a0549a</amountUnit>
           <!--Контейнер (guid)-->
          <containerId>C66196B6-68F2-4C17-97C2-C2008A39A76A</containerId>   
          <!--Порядковый номер в документе-->
          <num>1</num>
          <!--Товар (guid)-->
          <product>0f22aa60-e8ae-4c8e-80cd-f1e00b88fec6</product>
          <!--Количество-->
        <amount>1</amount>
        </item> 
    </items>
  </document>
```


**Результат**
 

```xml
HTTP/1.1 200 OK
Server: Apache-Coyote/1.1
Vary: Accept-Encoding
Content-Type: application/xml
Content-Length: 192
Date: Wed, 17 Dec 2014 08:47:50 GMT
<?xml version="1.0" encoding="UTF-8" standalone="yes"?><documentValidationResult>
  <documentNumber>api-0002</documentNumber>
  <valid>true</valid>
  <warning>false</warning>
</documentValidationResult>

```

```xml
HTTP/1.1 200 OK
Server: Apache-Coyote/1.1
Vary: Accept-Encoding
Content-Type: application/xml
Content-Length: 192
Date: Wed, 17 Dec 2014 08:47:50 GMT
<?xml version="1.0" encoding="UTF-8" standalone="yes"?><documentValidationResult>
  <documentNumber>api-0002</documentNumber>
  <valid>true</valid>
  <warning>false</warning>
</documentValidationResult>

```


##  

##
