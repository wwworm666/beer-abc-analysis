* [Параметры запроса](/articles/api-documentations/vygruzka-prikhodnoy-nakladnoy-po-ee-nomeru/a/h3_1827755295)
* [Что в ответе](/articles/api-documentations/vygruzka-prikhodnoy-nakladnoy-po-ee-nomeru/a/h3_501454233)
* [Пример запроса и результат](/articles/api-documentations/vygruzka-prikhodnoy-nakladnoy-po-ee-nomeru/a/h3_1561844723)

Версия iiko: 5.4

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/documents/export/incomingInvoice/byNumber |
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

[+] [XSD Приходная накладная](javascript:void%280%29)
 [-] [XSD Приходная накладная](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```


###  **Пример запроса и результат** 

**Запрос**

https://localhost:9080/resto/api/documents/export/incomingInvoice/byNumber?key=49023c7b-86f4-351a-b237-554a674bf3a9&number=1711&from=2012-01-01&to=2012-12-30&currentYear=false
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 
##
