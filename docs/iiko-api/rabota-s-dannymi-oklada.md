* [Получение оклада по ID сотрудника](/articles/api-documentations/rabota-s-dannymi-oklada/a/h2_2070011721)
* [Получение оклада по ID сотрудника на дату](/articles/api-documentations/rabota-s-dannymi-oklada/a/h2__1772301587)
* [Список окладов](/articles/api-documentations/rabota-s-dannymi-oklada/a/h2__531668256)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-oklada/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-oklada/a/h3_501454233)
* [Установка оклада](/articles/api-documentations/rabota-s-dannymi-oklada/a/h2_1039417788)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-oklada/a/h3__739759974)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-oklada/a/h3_1387997121)
* [Описание сущностей для представления в формате XML (XSD-схема)](/articles/api-documentations/rabota-s-dannymi-oklada/a/v1.APIсотрудников-ОписаниясущностейдляпредставлениявформатеXML%28XSD-схема%29)

## Получение оклада по ID сотрудника

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/salary/byId/{employeeUUID} |
| --- | --- |

## Получение оклада по ID сотрудника на дату

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/salary/byId/{employeeUUID}/{YYYY-MM-DD} |
| --- | --- |

## Список окладов

Версия API: 1.0

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/salary |
| --- | --- |

### Параметры запроса
| **Название** | **Значение** | **Версия** | **Описание** |
| --- | --- | --- | --- |
| revisionFrom | число, номер ревизии | с 6.4 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |
### Что в ответе

Список окладов не удаленных сотрудников.

## Установка оклада

Версия API: 1.0
Версия iiko: 4.0

| ![POST Request](/resources/Storage/api-documentations/http_request_post.png) | https://host:port/resto/api/employees/salary/byId/{employeeUUID}/{YYYY-MM-DD} |
| --- | --- |
**Параметры запроса**
| **Параметр** | **Описание** |
| --- | --- |
| payment | Сумма оклада |
| {employeeUUID} | id пользователя |
| {YYYY-MM-DD} | Дата начала действия оклада |
### Что в ответе

Структура **salary.**

### **Пример запроса**

https://localhost:8080/resto/api/employees/salary/byId/4f390698-241d-6ab9-015e-a3d90baa0370/2017-10-01?payment=50000

## Описание сущностей для представления в формате XML (XSD-схема)
 [+] [Ставка оплаты](javascript:void%280%29)
 [-] [Ставка оплаты](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```

 
##
