* [Тело запроса](/articles/api-documentations/zagruzka-i-redaktirovanie-raskhodnoy-nakladnoy/a/h3_1150399349)
* [Что в ответе](/articles/api-documentations/zagruzka-i-redaktirovanie-raskhodnoy-nakladnoy/a/h3_501454233)
* [Пример запроса и результат](/articles/api-documentations/zagruzka-i-redaktirovanie-raskhodnoy-nakladnoy/a/h3__232688264)

Версия iiko: 4.4

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/documents/import/outgoingInvoice |
| --- | --- |

Content-Type: application/xml

### Тело запроса

Структура o*utgoingInvoiceDto*

[+] [XSD Расходная накладная](javascript:void%280%29)
 [-] [XSD Расходная накладная](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
### Что в ответе

Структура *documentValidationResult*

### 

[+] [XSD Результат валидации документа​](javascript:void%280%29)
 [-] [XSD Результат валидации документа​](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 
### **Пример запроса и результат**

**Запрос**

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <document>
        <id>1f959f26-c301-43b7-9999-eabf5fc1ce70</id>
        <documentNumber>21</documentNumber>
        <dateIncoming>2025-11-19T11:10:04.943+03:00</dateIncoming>
        <useDefaultDocumentTime>false</useDefaultDocumentTime>
        <status>PROCESSED</status>
        <accountToCode>5.01</accountToCode>
        <revenueAccountCode>4.01</revenueAccountCode>
        <defaultStoreId>1239d270-1bbe-f64f-b7ea-5f00518ef508</defaultStoreId>
        <defaultStoreCode>1</defaultStoreCode>
        <counteragentId>265aaefb-b984-cc76-0194-8427903c1a87</counteragentId>
        <counteragentCode></counteragentCode>
        <items>
            <item>
                <productId>f7179241-2bba-4efc-9ef7-cbb936292ed9</productId>
                <productArticle>00025</productArticle>
                <storeId>1239d270-1bbe-f64f-b7ea-5f00518ef508</storeId>
                <storeCode>1</storeCode>
                <price>50.000000000</price>
                <priceWithoutVat>50.000000000</priceWithoutVat>
                <amount>1.000000000</amount>
                <sum>50.000000000</sum>
                <discountSum>0.000000000</discountSum>
                <vatPercent>0.000000000</vatPercent>
                <vatSum>0.000000000</vatSum>
            </item>
        </items>
    </document>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <document>
        <id>1f959f26-c301-43b7-9999-eabf5fc1ce70</id>
        <documentNumber>21</documentNumber>
        <dateIncoming>2025-11-19T11:10:04.943+03:00</dateIncoming>
        <useDefaultDocumentTime>false</useDefaultDocumentTime>
        <status>PROCESSED</status>
        <accountToCode>5.01</accountToCode>
        <revenueAccountCode>4.01</revenueAccountCode>
        <defaultStoreId>1239d270-1bbe-f64f-b7ea-5f00518ef508</defaultStoreId>
        <defaultStoreCode>1</defaultStoreCode>
        <counteragentId>265aaefb-b984-cc76-0194-8427903c1a87</counteragentId>
        <counteragentCode></counteragentCode>
        <items>
            <item>
                <productId>f7179241-2bba-4efc-9ef7-cbb936292ed9</productId>
                <productArticle>00025</productArticle>
                <storeId>1239d270-1bbe-f64f-b7ea-5f00518ef508</storeId>
                <storeCode>1</storeCode>
                <price>50.000000000</price>
                <priceWithoutVat>50.000000000</priceWithoutVat>
                <amount>1.000000000</amount>
                <sum>50.000000000</sum>
                <discountSum>0.000000000</discountSum>
                <vatPercent>0.000000000</vatPercent>
                <vatSum>0.000000000</vatSum>
            </item>
        </items>
    </document>
```
**

**Результат**

**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<documentValidationResult>
    <valid>true</valid>
    <warning>false</warning>
    <documentNumber>21</documentNumber>
</documentValidationResult>
```

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<documentValidationResult>
    <valid>true</valid>
    <warning>false</warning>
    <documentNumber>21</documentNumber>
</documentValidationResult>
```
**
