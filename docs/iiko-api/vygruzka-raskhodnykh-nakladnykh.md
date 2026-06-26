* [Параметры запроса](/articles/api-documentations/vygruzka-raskhodnykh-nakladnykh/a/h3_1827755295)
* [Что в ответе](/articles/api-documentations/vygruzka-raskhodnykh-nakladnykh/a/h3_501454233)
* [Пример запроса и результат](/articles/api-documentations/vygruzka-raskhodnykh-nakladnykh/a/h3_1561844723)

Версия iiko: 5.4

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/documents/export/outgoingInvoice |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| *from* | YYYY-MM-DD | начальная дата (входит в интервал) |
| *to* | YYYY-MM-DD | конечная дата (входит в интервал, время не учитывается) |
| *supplierId* | GUID | Id поставщика |

При запросе без поставщиков возвращает все расходные накладные, попавшие в интервал.
 
### Что в ответе

[+] [XSD Расходная накладная](javascript:void%280%29)
 [-] [XSD Расходная накладная](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
### **Пример запроса и результат**

**Запрос**

https://localhost:9080/resto/api/documents/export/outgoingInvoice?key=86024f97-3c65-08af-2798-d7817bcdadce&from=2012-07-04&to=2012-07-05&supplierId=18761e00-aa16-4d0f-a064-d26cb3e7c646

[+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 
##
