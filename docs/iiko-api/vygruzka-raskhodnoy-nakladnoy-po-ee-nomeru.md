* [Параметры запроса](/articles/api-documentations/vygruzka-raskhodnoy-nakladnoy-po-ee-nomeru/a/h3_1827755295)
* [Что в ответе](/articles/api-documentations/vygruzka-raskhodnoy-nakladnoy-po-ee-nomeru/a/h3_501454233)
* [Пример запроса и результат](/articles/api-documentations/vygruzka-raskhodnoy-nakladnoy-po-ee-nomeru/a/h3__2087356861)

Версия iiko: 5.4

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/documents/export/outgoingInvoice/byNumber |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| *number* | String | номер документа |
| *from* | YYYY-MM-DD | начальная дата (входит в интервал) |
| *to* | YYYY-MM-DD | конечная дата (входит в интервал, время не учитывается) |
| *currentYear* | Boolean | только за текущий год |

При currentYear = true, вернет документы с указанным номером документа только за текущий год. Параметры from и to должны отсутствовать.

При currentYear = false параметры from и to должны быть указаны.

currentYear — **обязательный параметр**.

###  **Что в ответе**

[+] [XSD Расходная накладная](javascript:void%280%29)
 [-] [XSD Расходная накладная](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```


###  **Пример запроса и результат**

**Запрос**

https://localhost:9080/resto/api/documents/export/outgoingInvoice/byNumber?key=49023c7b-86f4-351a-b237-554a674bf3a9&number=4&from=2012-01-01&to=2012-12-30&currentYear=false

**Результат**


```xml
<outgoingInvoiceDtoes>
    <document>
        <id>cde9adc2-1c49-4d68-9d30-31a3768df53e</id>
        <documentNumber>4</documentNumber>
        <dateIncoming>2012-07-04T23:00:00+04:00</dateIncoming>
        <useDefaultDocumentTime>false</useDefaultDocumentTime>
        <status>PROCESSED</status>
        <accountToCode>7.3</accountToCode>
        <revenueAccountCode>4.01.1</revenueAccountCode>
        <defaultStoreId>a80f6110-aa36-43ea-8fb7-de9b6a3a2346</defaultStoreId>
        <defaultStoreCode>16</defaultStoreCode>
        <counteragentId>18761e00-aa16-4d0f-a064-d26cb3e7c646</counteragentId>
        <counteragentCode>703</counteragentCode>
        <comment/>
        <items>
            <item>
                <productId>dc0c21ce-6ed9-4275-ae94-c6585ebd972a</productId>
                <productArticle>06062</productArticle>
                <storeId>a80f6110-aa36-43ea-8fb7-de9b6a3a2346</storeId>
                <storeCode>16</storeCode>
                <price>166.670000000</price>
                <amount>6.000000000</amount>
                <sum>1000.000000000</sum>
                <discountSum>0.000000000</discountSum>
                <vatPercent>0.000000000</vatPercent>
                <vatSum>0.000000000</vatSum>
            </item>
        </items>
    </document>
</outgoingInvoiceDtoes>
```

```xml
<outgoingInvoiceDtoes>
    <document>
        <id>cde9adc2-1c49-4d68-9d30-31a3768df53e</id>
        <documentNumber>4</documentNumber>
        <dateIncoming>2012-07-04T23:00:00+04:00</dateIncoming>
        <useDefaultDocumentTime>false</useDefaultDocumentTime>
        <status>PROCESSED</status>
        <accountToCode>7.3</accountToCode>
        <revenueAccountCode>4.01.1</revenueAccountCode>
        <defaultStoreId>a80f6110-aa36-43ea-8fb7-de9b6a3a2346</defaultStoreId>
        <defaultStoreCode>16</defaultStoreCode>
        <counteragentId>18761e00-aa16-4d0f-a064-d26cb3e7c646</counteragentId>
        <counteragentCode>703</counteragentCode>
        <comment/>
        <items>
            <item>
                <productId>dc0c21ce-6ed9-4275-ae94-c6585ebd972a</productId>
                <productArticle>06062</productArticle>
                <storeId>a80f6110-aa36-43ea-8fb7-de9b6a3a2346</storeId>
                <storeCode>16</storeCode>
                <price>166.670000000</price>
                <amount>6.000000000</amount>
                <sum>1000.000000000</sum>
                <discountSum>0.000000000</discountSum>
                <vatPercent>0.000000000</vatPercent>
                <vatSum>0.000000000</vatSum>
            </item>
        </items>
    </document>
</outgoingInvoiceDtoes>
```


##
