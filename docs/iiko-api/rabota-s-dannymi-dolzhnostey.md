* [Список должностей](/articles/api-documentations/rabota-s-dannymi-dolzhnostey/a/h2_334405970)
* [Параметры запроса](/articles/api-documentations/rabota-s-dannymi-dolzhnostey/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/rabota-s-dannymi-dolzhnostey/a/h3_501454233)
* [Пример запроса](/articles/api-documentations/rabota-s-dannymi-dolzhnostey/a/h3_1387997121)
* [Описание сущностей для представления в формате XML (XSD-схема)](/articles/api-documentations/rabota-s-dannymi-dolzhnostey/a/v1.APIсотрудников-ОписаниясущностейдляпредставлениявформатеXML%28XSD-схема%29)

## Список должностей

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/employees/roles |
| --- | --- |

### 

### Параметры запроса
| **Название** | **Параметр** | **Версия** | **Описание** |
| --- | --- | --- | --- |
| revisionFrom | число, номер ревизии | с 6.4 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |
### Что в ответе

Список должностей (см. описание XSD).

### **Пример запроса**

https://localhost:8080/resto/api/employees/roles

**Результат:**


Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<employeeRoles>
  <role>
    <id>d9753f67-6e87-4564-9b74-4018c37306d7</id>
    <code>BAR1</code>
    <name>Barista</name>
    <paymentPerHour>2.500000000</paymentPerHour>
    <steadySalary>1860.000000000</steadySalary>
    <scheduleType>SESSION</scheduleType>
    <deleted>false</deleted>
  </role>
  <role>
    <id>01a014eb-6609-c206-dbed-3102179f80be</id>
    <code>SMB</code>
    <name>Somebody</name>
    <paymentPerHour>2.000000000</paymentPerHour>
    <steadySalary>340.000000000</steadySalary>
    <scheduleType>HOURS</scheduleType>
    <deleted>false</deleted>
  </role>
</employeeRoles>
```

Код

```
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<employeeRoles>
  <role>
    <id>d9753f67-6e87-4564-9b74-4018c37306d7</id>
    <code>BAR1</code>
    <name>Barista</name>
    <paymentPerHour>2.500000000</paymentPerHour>
    <steadySalary>1860.000000000</steadySalary>
    <scheduleType>SESSION</scheduleType>
    <deleted>false</deleted>
  </role>
  <role>
    <id>01a014eb-6609-c206-dbed-3102179f80be</id>
    <code>SMB</code>
    <name>Somebody</name>
    <paymentPerHour>2.000000000</paymentPerHour>
    <steadySalary>340.000000000</steadySalary>
    <scheduleType>HOURS</scheduleType>
    <deleted>false</deleted>
  </role>
</employeeRoles>
```


## Описание сущностей для представления в формате XML (XSD-схема)
[+] [Должность](javascript:void%280%29)
 [-] [Должность](javascript:void%280%29)
 
```
 %%CH%PRE2%%%%CH%PRE3%%
```
