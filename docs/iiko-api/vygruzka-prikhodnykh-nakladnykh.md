* [Параметры запроса](/articles/api-documentations/vygruzka-prikhodnykh-nakladnykh/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/vygruzka-prikhodnykh-nakladnykh/a/h3_501454233)
* [Пример запроса и результат](/articles/api-documentations/vygruzka-prikhodnykh-nakladnykh/a/h3_1387997121)

Версия iiko: 5.4

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/documents/export/incomingInvoice |
| --- | --- |

### Параметры запроса

| Название | Значение | Описание |
| --- | --- | --- |
| from | YYYY-MM-DD | начальная дата (входит в интервал) |
| to | YYYY-MM-DD | конечная дата (входит в интервал, время не учитывается) |
| supplierId | GUID | Id поставщика |
| revisionFrom | число, по умолчанию -1 | **с версии 6.4**<br><br>Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |

При запросе без поставщиков возвращает все приходные накладные, попавшие в интервал.

### Что в ответе
 [+] [XSD Приходная накладная](javascript:void%280%29)
 [-] [XSD Приходная накладная](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
###  Пример запроса и результат

####  Запрос

https://localhost:9080/resto/api/documents/export/incomingInvoice?key=491eca76-beed-845e-878c-9b05c97be0e2&from=2012-07-01&to=2012-07-02&supplierId=22A2A9D7-9D9C-48AD-BF99-83BF8CDE1938&supplierId=C5C6F00D-E1E5-4E3C-A4B8-BB677F470572

### 
 [+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```

 
##
