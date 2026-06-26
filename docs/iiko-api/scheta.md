* [Получение списка счетов](/articles/api-documentations/scheta/a/v2.APIсчетов-Получениеспискасчетов)
* [Параметры запроса](/articles/api-documentations/scheta/a/v2.APIсчетов-Параметры)
* [Что в ответе](/articles/api-documentations/scheta/a/v2.APIсчетов-Результат)
* [Пример вызова](/articles/api-documentations/scheta/a/h3__232688264)

## Получение списка счетов

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/**entities/accounts/list** |
| --- | --- |

### Параметры запроса
| **Название** | **Значение** | Версия | **Описание** |
| --- | --- | --- | --- |
| includeDeleted | true, false | 5.4 | Включать ли удаленные счета, по умолчанию - нет |
| revisionFrom | -1 | 6.4 | Номер ревизии, начиная с которой необходимо отфильтровать сущности. Не включающий саму ревизию, т.е. ревизия объекта &gt; revisionFrom.<br><br>По умолчанию (неревизионный запрос) revisionFrom = -1 |
### Что в ответе

Json структура с данными счетов.

Возвращает общую справочную информацию без привязки к балансам и материально ответственным лицам.

| **Поле** | **Версия** | **Описание** |
| id |  | UUID счета |
| accountParentId |  | UUID родительского счета, у складов это поле null |
| parentCorporateId |  | UUID объекта структуры корпорации, которой принадлежит склад |
| code |  | Код счета |
| deleted |  | Удален ли |
| name |  | Название. Для предустановленных (системных) счетов название может/будет отображаться на разных языках,<br>в зависимости от Accept-Language запроса. |
| type |  | Аналогично импорту только с id редактируемого элемента:<br> <br><br>| Значение | Описание |<br>| --- | --- |<br>| 
```
CASH
```
 | Денежные средства |<br>| 
```
ACCOUNTS_RECEIVABLE
```
 | Задолженность покупателей |<br>| 
```
DEBTS_OF_EMPLOYEES
```
 | Задолженность сотрудников |<br>| 
```
CURRENT_ASSET
```
 | Текущие активы |<br>| 
```
OTHER_CURRENT_ASSET
```
 | Основные средства |<br>| 
```
INVENTORY_ASSETS
```
 | Складские запасы |<br>| 
```
EMPLOYEES_LIABILITY
```
 | Расчеты с сотрудниками |<br>| 
```
ACCOUNTS_PAYABLE
```
 | Расчеты с поставщиками |<br>| 
```
CLIENTS_LIABILITY
```
 | Расчеты с гостями |<br>| 
```
OTHER_CURRENT_LIABILITY
```
 | Прочие текущие обязательства |<br>| 
```
LONG_TERM_LIABILITY
```
 | Долгосрочные обязательства |<br>| 
```
EQUITY
```
 | Капитал |<br>| 
```
COST_OF_GOODS_SOLD
```
 | Прямые издержки |<br>| 
```
INCOME
```
 | Доходы |<br>| 
```
EXPENSES
```
 | Расходы |<br>| 
```
OTHER_INCOME
```
 | Прочие доходы |<br>| 
```
OTHER_EXPENSES
```
 | Прочие расходы | |
| --- | --- | --- |
| system |  | true, если это предустановленный склад на standalone RMS. |
| customTransactionsAllowed |  | Можно ли делать ручные проводки |
| rootType | 6.2.2 | Account |

### **Пример вызова**
https://localhost:8080/resto/api/v2/entities/accounts/list[+] [Результат](javascript:void%280%29)
 [-] [Результат](javascript:void%280%29)
 
```
 %%CH%PRE0%%%%CH%PRE1%%
```
