* [Типы транзакций](/articles/api-documentations/kody-bazovykh-tipov/a/h2_2005976639)
* [Тип Контрагента](/articles/api-documentations/kody-bazovykh-tipov/a/h2_1301739807)
* [Группа счета](/articles/api-documentations/kody-bazovykh-tipov/a/h2_1564740693)
* [Тип счета](/articles/api-documentations/kody-bazovykh-tipov/a/h2__1251739372)
* [Тип элемента номенклатуры](/articles/api-documentations/kody-bazovykh-tipov/a/h2_1610348632)
* [Тип статьи ДДС](/articles/api-documentations/kody-bazovykh-tipov/a/h2_1866394497)
* [Участвует ли счет в ДДС](/articles/api-documentations/kody-bazovykh-tipov/a/h2_843598296)
* [Склад/счет](/articles/api-documentations/kody-bazovykh-tipov/a/h2__1216107496)
* [Тип алкогольной продукции](/articles/api-documentations/kody-bazovykh-tipov/a/h2__488025460)
* [Дебет/Кредит](/articles/api-documentations/kody-bazovykh-tipov/a/h2_566795722)
* [Типы удаления блюд](/articles/api-documentations/kody-bazovykh-tipov/a/h2__996447299)
* [Признак доставки](/articles/api-documentations/kody-bazovykh-tipov/a/h2_50007806)
* [Признак банкета](/articles/api-documentations/kody-bazovykh-tipov/a/h2__185013442)
* [Тип товара](/articles/api-documentations/kody-bazovykh-tipov/a/h2__1431944617)
* [Тип операции](/articles/api-documentations/kody-bazovykh-tipov/a/h2__1199154873)
* [Признак удаления заказа](/articles/api-documentations/kody-bazovykh-tipov/a/h2_1741231012)
* [Группа оплаты](/articles/api-documentations/kody-bazovykh-tipov/a/h2_667585615)
* [Признак фискальности оплаты](/articles/api-documentations/kody-bazovykh-tipov/a/h2_546290300)
* [Типы подразделений](/articles/api-documentations/kody-bazovykh-tipov/a/h2_775272967)
* [Типы групп продукта](/articles/api-documentations/kody-bazovykh-tipov/a/h2__1318911658)
 
# Типы документов

| Код | Название | Сокращение |
| --- | --- | --- |
| INCOMING\_INVOICE | Приходная накладная | п/н |
| INCOMING\_INVENTORY | Инвентаризация | инв |
| INCOMING\_SERVICE | Акт приема услуг | в/с |
| OUTGOING\_SERVICE | Акт оказания услуг | в/с |
| WRITEOFF\_DOCUMENT | Акт списания | а/с |
| SALES\_DOCUMENT | Акт реализации | а/р |
| SESSION\_ACCEPTANCE | Принятие смены | п/с |
| INTERNAL\_TRANSFER | Внутреннее перемещение | в/п |
| OUTGOING\_INVOICE | Расходная накладная | р/н |
| RETURNED\_INVOICE | Возвратная накладная | в/н |
| PRODUCTION\_DOCUMENT | Акт приготовления | а/пр |
| TRANSFORMATION\_DOCUMENT | Акт переработки | а/пб |
| PRODUCTION\_ORDER | Заказ в производство | з/п |
| CONSOLIDATED\_ORDER | Консолидированный заказ | к/з |
| PREPARED\_REGISTER | Ведомость полуфабрикатов | в/пф |
| MENU\_CHANGE | Приказ об изменении прейскуранта | п/м |
| PRODUCT\_REPLACEMENT | Замена товаров | з/т |
| SALES\_RETURN\_DOCUMENT | Акт приема возврата | п/в |
| DISASSEMBLE\_DOCUMENT | Акт разбора | а/рб |
| PAYROLL | Платёжная ведомость | з/в |
| INCOMING\_CASH\_ORDER | Приходный кассовый ордер | п/ко |
| OUTGOING\_CASH\_ORDER | Расходный кассовый ордер | р/ко |

##  Типы транзакций

| Код | Название | Сокращение |
| --- | --- | --- |
| OPENING\_BALANCE | Начальный баланс | БАЛНАЧ |
| CUSTOM | Ручная проводка | РУЧН |
| CASH | Продажа за наличные | ПН |
| PREPAY\_CLOSED | Продажа с предоплатой | ПН-ПРЕД |
| PREPAY | Предоплата | ПРЕДОП |
| PREPAY\_RETURN | Возврат предоплаты | ВОЗВПРЕД |
| PREPAY\_CLOSED\_RETURN | Возврат продажи с предоплатой | ПН-ВОЗВПРЕД |
| DISCOUNT | Скидка | СКИДКА |
| CARD | Выручка по картам | CARD |
| CREDIT | Выручка в кредит | КРЕД |
| PAYIN | Внесенная сумма | ВС |
| PAYOUT | Изъятая сумма | ИС |
| PAY\_COLLECTION | Снятая выручка | СВ |
| CASH\_CORRECTION | Коррекция по кассе | КОРР |
| INVENTORY\_CORRECTION | Инвентаризация | ИНВ |
| STORE\_COST\_CORRECTION | Коррекция себестоимости | СЕБЕСТ |
| CASH\_SURPLUS | Излишек по кассе | ИЗЛИШ |
| CASH\_SHORTAGE | Недостача по кассе | НЕДОСТ |
| PENALTY | Штраф | ШТРФ |
| BONUS | Премия | ПРЕМ |
| INVOICE | Накладная | НАКЛ |
| NDS\_INCOMING | НДС входящий | НДСВХ |
| NDS\_SALES | НДС с продаж | НДСПР |
| SALES\_REVENUE | Выручка от реализации | ВЫРРЕАЛ |
| OUTGOING\_INVOICE | Расходная накладная | РАСХНАКЛ |
| OUTGOING\_INVOICE\_REVENUE | Выручка расходной накладной | РАСХНАКЛВ |
| RETURNED\_INVOICE | Возвратная накладная | ВОЗВРНАКЛ |
| RETURNED\_INVOICE\_REVENUE | Выручка возвратной накладной | ВОЗВРНАКВ |
| WRITEOFF | Списание | СПИС |
| SESSION\_WRITEOFF | Реализация товаров | РЕАЛИЗ |
| TRANSFER | Внутреннее перемещение | ВНПЕРЕМ |
| TRANSFORMATION | Акт переработки | ПЕРЕРАБ |
| TARIFF\_HOUR | Почасовая оплата | ПОЧАС |
| ON\_THE\_HOUSE | Оплата заказа за счет заведения | ПЗАВЕД |
| ADVANCE | Аванс по зарплате | АВАНС |
| INCOMING\_SERVICE | Получение услуг | ВХУСЛ |
| OUTGOING\_SERVICE | Оказание услуг | ИСХУСЛ |
| INCOMING\_SERVICE\_PAYMENT | Оплата получения услуг | ВХУСЛОПЛ |
| OUTGOING\_SERVICE\_PAYMENT | Оплата оказания услуг | ИСХУСЛОПЛ |
| IMPORTED\_BANK\_STATEMENT | Загрузка банковской выписки | ВЫПИСКА |
| CLOSE\_AT\_EMPLOYEE\_EXPENSE | Закрытие стола за счет сотрудника | НЕЗАКР |
| INCENTIVE\_PAYMENT | Мотивация | МОТИВ |
| TARIFF\_PERCENT | Процент с продаж | ПРОЦ |
| SESSION\_ACCEPTANCE | Принятие смены | ПРИН |
| EMPLOYEE\_CASH\_PAYMENT | Выдача наличных сотрудникам | НАЛСОТР |
| EMPLOYEE\_PAYMENT | Начисление оклада | ОКЛ |
| INVOICE\_PAYMENT | Оплата накладной | НОПЛ |
| OUTGOING\_DOCUMENT\_PAYMENT | Принятие оплаты исходящего документа | ИДОПЛ |
| OUTGOING\_SALES\_DOCUMENT\_PAYMENT | Принятие оплаты акта реализации | АРОПЛ |
| PRODUCTION | Акт приготовления | ПРГТ |
| SALES\_RETURN\_PAYMENT | Оплата приема возврата | ПРВОЗВР |
| SALES\_RETURN\_WRITEOFF | Возврат товаров | ВОЗВРТОВ |
| DISASSEMBLE | Акт разбора | РАЗБОР |

##  Тип Контрагента

| Код | Название |
| --- | --- |
| NONE | Нет |
| COUNTERAGENT | Все |
| EMPLOYEE | Cотрудник |
| SUPPLIER | Поставщик |
| CLIENT | Гость |
| INTERNAL\_SUPPLIER | Внутренний поставщик |

##  Группа счета

| Код | Название |
| --- | --- |
| ASSETS | Активы |
| LIABILITIES | Обязательства |
| EQUITY | Капитал |
| INCOME\_EXPENSES | Доходы/Расходы |

##  Тип счета

| Код | Название |
| --- | --- |
| CASH | Денежные средства |
| ACCOUNTS\_RECEIVABLE | Задолженность покупателей |
| DEBTS\_OF\_EMPLOYEES | Задолженность сотрудников |
| CURRENT\_ASSET | Текущие активы |
| OTHER\_CURRENT\_ASSET | Основные средства |
| INVENTORY\_ASSETS | Складские запасы |
| EMPLOYEES\_LIABILITY | Расчеты с сотрудниками |
| ACCOUNTS\_PAYABLE | Расчеты с поставщиками |
| CLIENTS\_LIABILITY | Расчеты с гостями |
| OTHER\_CURRENT\_LIABILITY | Прочие текущие обязательства |
| LONG\_TERM\_LIABILITY | Долгосрочные обязательства |
| EQUITY | Капитал |
| COST\_OF\_GOODS\_SOLD | Прямые издержки (себестоимость) |
| INCOME | Доходы |
| EXPENSES | Расходы |
| OTHER\_INCOME | Прочие доходы |
| OTHER\_EXPENSES | Прочие расходы |

##  Тип элемента номенклатуры

| Код | Название |
| --- | --- |
| GOODS | Товар |
| DISH | Блюдо |
| PREPARED | Заготовка |
| SERVICE | Услуга |
| MODIFIER | Модификатор |
| OUTER | Внешние товары |
| PETROL | Топливо |
| RATE | Тариф |

##  Тип статьи ДДС

| Код | Название |
| --- | --- |
| OPERATIONAL | Операционная деятельность |
| INVESTMENT | Инвестиционная деятельность |
| FINANCE | Финансовая деятельность |

##  Участвует ли счет в ДДС

| Код | Название |
| --- | --- |
| CASH\_FLOW | Участвует в ДДС |
| NOT\_CASH\_FLOW | Не участвует в ДДС |

##  Склад/счет

| Код | Название |
| --- | --- |
| STORE | Склад |
| ACCOUNT | Счет |

##  Тип алкогольной продукции

| Код | Название |
| --- | --- |
| STRONG | Крепкие |
| BEER | Пиво |

##  Дебет/Кредит

| Код | Название |
| --- | --- |
| DEBIT | Дебет |
| CREDIT | Кредит |

##  Типы удаления блюд

| Код | Название |
| --- | --- |
| DELETED\_WITHOUT\_WRITEOFF | Удалено без списания |
| DELETED\_WITH\_WRITEOFF | Удалено со списанием |
| NOT\_DELETED | Не удалено |

##  Признак доставки

| Код | Название |
| --- | --- |
| DELIVERY\_ORDER | Доставка |
| ORDER\_WITHOUT\_DELIVERY | Не доставка |

##  Признак банкета

| Код | Название |
| --- | --- |
| TRUE | Банкет |
| FALSE | Не банкет |

##  Тип товара

| Код | Название |
| --- | --- |
| DISH | dish |
| GOOD | good |
| MODIFIER | modifier |

##  Тип операции

| Код | Название |
| --- | --- |
| STORNED | Сторнирование |
| PREPAY | Предоплата |
| PREPAY\_RETURN | Возврат предоплаты |
| NO\_PAYMENT | (без оплаты) |
| PAYMENT | Оплата |

##  Признак удаления заказа

| Код | Название |
| --- | --- |
| NOT\_DELETED | Заказ не удален |
| DELETED | Заказ удален |

##  Группа оплаты

| Код | Название |
| --- | --- |
| CASH | Оплата наличными |
| CARD | Банковские карты |
| WRITEOFF | Без выручки |
| NON\_CASH | Безналичный расчет |

##  Признак фискальности оплаты

| Код | Название |
| --- | --- |
| FISCAL | Фискальный |
| NOT\_FISCAL | Не фискальный |
| NO\_PAYMENT | (без оплаты) |

##  Типы подразделений

| Код | Название |
| --- | --- |
| CORPORATION | Корпорация |
| JURPERSON | Юридическое лицо |
| ORGDEVELOPMENT | Структурное подразделение |
| DEPARTMENT | Торговое предприятие |
| MANUFACTURE | Производство |
| CENTRALSTORE | Центральный склад |
| CENTRALOFFICE | Центральный офис |
| SALEPOINT | Точка продаж |
| STORE | Склад |

##  Типы групп продукта

| Код | Название | Комментарий |
| --- | --- | --- |
| PRODUCTS | Продукт |
| MODIFIERS | Модификатор | Используется только в номенклатуре, которая загружается и выгружается в/из RKeeper/StoreHouse |
