* [OLAP-отчет](/articles/api-documentations/olap-otchety-v1/a/h2_1993590971)
* [Параметры запроса](/articles/api-documentations/olap-otchety-v1/a/h3_1827755295)
* [Что в ответе](/articles/api-documentations/olap-otchety-v1/a/h3__232688264)
* [Описание полей OLAP-отчетов](/articles/api-documentations/olap-otchety-v1/a/h3_1457076905)

## OLAP-отчет
 
Версия iiko: 3.9

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | **https://host:port/resto/****api/** **reports/olap** |
| --- | --- |

### Параметры запроса

| Название | Значение | **Описание** |
| --- | --- | --- |
| *report* | SALES - По продажам<br> <br>TRANSACTIONS - По транзакциям<br> <br>DELIVERIES - По доставкам<br> <br>STOCK - Контроль хранения | Тип отчета |
| *summary* | true - вычислять итоговые значения<br><br>false - не вычислять итоговые значения | Вычислять ли итоговые значения.<br>По умолчанию выстален true. При значении false отчет строится намного быстрее.<br><br>с **Version (iiko) 5.3**<br><br>**С версии 9.1.2 значение по умолчанию false.** |
| *groupRow* | Поля группировки, например: groupRow=WaiterName& groupRow=OpenTime | Для определения списка доступных полей см.:<br><ul style="margin: 10px 0px 0px; padding-left: 22px;"> <li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;">Описание полей OLAP отчета по продажам </span></span></li> <li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;">Описание полей OLAP отчета по проводкам </span></span></li> <li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;">Описание полей OLAP отчета по доставкам </span></span></li> </ul> <br>По полю можно проводить группировку, если значение в колонке Grouping для поля равно true |
| *groupCol* | Поля для выделения значений по колонкам | Для определения списка доступных полей см.:<br><ul style="margin: 10px 0px 0px; padding-left: 22px;"> <li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;">Описание полей OLAP отчета по продажам </span></span></li> <li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;">Описание полей OLAP отчета по проводкам </span></span></li> <li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;">Описание полей OLAP отчета по доставкам </span></span></li> </ul> <br>По полю можно проводить группировку, если значение в колонке Grouping для поля равно true |
| *agr* | Поля агрегации, например: agr=DishDiscountSum&agr=VoucherNum | <ul style="margin: 0px; padding-left: 22px;"> <li> <p style="margin: 0px;"><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;">Для определения списка доступных полей см.: </span></span></p><ul style="list-style-type: disc; padding-left: 22px;"> <li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;">Описание полей OLAP отчета по продажам </span></span></li> <li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;">Описание полей OLAP отчета по проводкам </span></span></li> <li><span style="font-size: 10pt;"><span style="font-family: &quot;Open Sans&quot;, Arial, Helvetica, sans-serif;">Описание полей OLAP отчета по доставкам </span></span></li> </ul> </li> </ul> <br>По полю можно проводить агрегацию, если значение в колонке Aggregation для поля равно true |
| *from* | DD.MM.YYYY | Начальная дата |
| *to* | DD.MM.YYYY | Конечная дата |

### Что в ответе

Структура *report.*

### Пример запроса

| https://localhost:8080/resto/api/reports/olap?key=ec621550-afae-133e-80c8-76155db2b268&report=SALES&from=01.12.2014&to=18.12.2014&groupRow=WaiterName&groupRow=OpenTime&agr=fullSum&agr=OrderNum |
| --- |

### Описание полей OLAP-отчетов
 [+] [Описание полей OLAP-отчета по доставкам](javascript:void%280%29)
 [-] [Описание полей OLAP-отчета по доставкам](javascript:void%280%29)
 # 

| **Name** | **Description** | **Aggreation** | **Grouping** | **Filtering** | **Type** | **Value** |
| --- | --- | --- | --- | --- | --- | --- |
| CloseTime | Время закрытия | false | true | true | DATETIME |  |
| Delivery.ActualTime | Фактическое время доставки | false | true | true | DATETIME |  |
| Delivery.Address | Адрес | false | true | true | STRING |  |
| Delivery.BillTime | Время печати накладной | false | true | true | DATETIME |  |
| Delivery.CancelCause | Причина отмены доставки | false | true | true | STRING |  |
| Delivery.City | Город | false | true | true | STRING |  |
| Delivery.CloseTime | Время закрытия доставки | false | true | true | DATETIME |  |
| Delivery.CookingToSendDuration | Длит: посл.серв.печать-отправка | true | false | false | INTEGER |  |
| Delivery.Courier | Курьер | false | true | true | STRING |  |
| Delivery.CustomerCardNumber | Номер карты клиента доставки | false | true | true | STRING |  |
| Delivery.CustomerCardType | Тип карты клиента доставки | false | true | true | STRING |  |
| Delivery.CustomerComment | Комментарий к клиенту | false | true | true | STRING |  |
| Delivery.CustomerCreatedDate<br><br>(до версии 4.2; в 4.2+ deprecated, заменено на Delivery.CustomerCreatedDateTyped) | Дата создания клиента | false | true | true | STRING |  |
| Delivery.CustomerCreatedDateTyped (4.2+) | Дата создания клиента | false | true | true | DATE |  |
| Delivery.CustomerMarketingSource | Реклама клиента | false | true | true | STRING |  |
| Delivery.CustomerName | ФИО клиента доставки | false | true | true | STRING |  |
| Delivery.Delay | Опоздание доставки(мин) | false | true | true | INTEGER |  |
| Delivery.DelayAvg | Ср.опоздание доставки(мин) | true | false | false | AMOUNT |  |
| Delivery.DeliveryComment | Комментарий к доставке | false | true | true | STRING |  |
| Delivery.DeliveryOperator | Оператор доставки | false | true | true | STRING |  |
| Delivery.Email | e-mail доставки | false | true | true | STRING |  |
| Delivery.ExpectedTime | Планируемое время доставки | false | true | true | DATETIME |  |
| Delivery.MarketingSource | Реклама | false | true | true | STRING |  |
| Delivery.Number | Номер доставки | false | true | true | INTEGER |  |
| Delivery.Phone | Телефон доставки | false | true | true | STRING |  |
| Delivery.PrintTime | Время печати доставки | false | true | true | DATETIME |  |
| Delivery.Region | Район | false | true | true | STRING |  |
| Delivery.SendTime | Время отправки доставки | false | true | true | DATETIME |  |
| Delivery.ServiceType | Тип доставки | false | true | true | ENUM | PICKUP<br>COURIER |
| Delivery.SourceKey | Источник доставки | false | true | true | STRING |  |
| Delivery.Street | Улица | false | true | true | STRING |  |
| Delivery.WayDuration | Время в пути(мин) | false | true | true | INTEGER |  |
| Delivery.WayDurationAvg | Ср.время в пути(мин) | true | false | false | AMOUNT |  |
| Delivery.WayDurationSum | Сумм.время в пути(мин) | true | false | false | INTEGER |  |
| DishServicePrintTime.Max | Сервисная печать последнего блюда | true | false | false | DATETIME |  |
 [+] [Описание полей OLAP отчета по проводкам](javascript:void%280%29)
 [-] [Описание полей OLAP отчета по проводкам](javascript:void%280%29)
 | ![Information](/resources/Storage/api-documentations/info.png) | Поля агрегации, учитывающие **начальный остаток товара и денежный остаток** (StartBalance.Amount, StartBalance.Money, FinalBalance.Amount, FinalBalance.Money) вычисляются суммированием всей таблицы проводок **за все время** работы системы (всей базы данных) без каких-либо оптимизаций. То есть, такой запрос может выполняться очень долго и замедлять работу сервера.<br><br>Если начальный остаток необходим, оставляйте в этом OLAP-запросе только те поля группировки, по которым он действительно необходим (как правило, это Account.Name и Product.Name), и вызывайте такой запрос **как можно реже** и в **не рабочее** время.<br><br>В 5.2 добавлено API для быстрого получения остатков: Отчеты по балансам. Во всех случаях рекомендуется пользоваться им вместо OLAP.<br><br>В 5.5 OLAP-отчеты с остатками оптимизированы с использованием балансовых таблиц ATransactionSum, ATransactionBalance, при условии, что применяются группировки и фильтры по полям из этих таблиц, см. признак StartBalanceOptimizable в описании полей.<br><br>То есть, правильно составленный запрос приведет к суммированию не всей таблицы проводок, а только лишь открытого периода. Обратите особое внимание на то, что оптимизировано только поле Account.Name (счет "текущей" стороны проводки, в том числе склад), а не Store (первый попавшийся "склад" проводки, взятый из: левой, правой части проводки, строки документа или самого документа).<br>**Склад** всегда, когда только возможно, следует брать из поля Account.Name ("Счет"), а **не** Store ("Склад"), оно вычисляется гораздо быстрее. |
| --- | --- |

| **Name** | **Description** | **Aggreation** | **Grouping** | **Filterig** | **StartBakanceOptimizable** | **Type** | **Value** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Account.AccountHierarchyFull | Иерархия счета | false | true | true | true | STRING |  |
| Account.AccountHierarchySecond | Счет 2-го уровня | false | true | true | true | STRING |  |
| Account.AccountHierarchyThird | Счет 3-го уровня | false | true | true | true | STRING |  |
| Account.AccountHierarchyTop | Счет 1-го уровня | false | true | true | true | STRING |  |
| Account.Code | Код счета | false | true | true | true | STRING |  |
| Account.CounteragentType | Тип контрагента | false | true | true | true | ENUM | Расшифровки кодов базовых типов#Тип Контрагента |
| Account.Group | Группа счета | false | true | true | true | ENUM | Расшифровки кодов базовых типов#Группа счета |
| Account.IsCashFlowAccount | Участвует ли счет в ДДС | false | true | true | true | ENUM | Расшифровки кодов базовых типов#Участвует ли счет в ДДС |
| Account.Name | Счет | false | true | true | true | STRING | Счет (в том числе склад) |
| Account.StoreOrAccount | Склад/счет | false | true | true | true | ENUM | Расшифровки кодов базовых типов#Счет/Склад |
| Account.Type | Тип счета | false | true | true | true | ENUM | Расшифровки кодов базовых типов#Тип счета |
| Amount | Количество | true | false | false | - | AMOUNT |  |
| Amount.In | Приход (кол-во) | true | false | false | - | AMOUNT |  |
| Amount.Out | Расход (кол-во) | true | false | false | - | AMOUNT |  |
| Amount.StoreInOut (до версии 4.3; в 4.3+ deprecated, заменено на Amount.StoreInOutTyped) | Оборот эл.номенклатуры | true | false | false | - | STRING |  |
| Amount.StoreInOutTyped (4.3+, взамен Amount.StoreInOut) | Оборот эл.номенклатуры | true | false | false | - | AMOUNT |  |
| CashFlowCategory | Статья ДДС | false | true | true | true | STRING |  |
| CashFlowCategory.Hierarchy | Иерархия статей ДДС | false | true | true | true | STRING |  |
| CashFlowCategory.HierarchyLevel1 | Статья ДДС 1-го уровня | false | true | true | true | STRING |  |
| CashFlowCategory.HierarchyLevel2 | Статья ДДС 2-го уровня | false | true | true | true | STRING |  |
| CashFlowCategory.HierarchyLevel3 | Статья ДДС 3-го уровня | false | true | true | true | STRING |  |
| CashFlowCategory.Type | Тип статьи ДДС | false | true | true | true | ENUM | Расшифровки кодов базовых типов#Тип статьи ДДС |
| Comment | Комментарий | false | true | true | false | STRING |  |
| Conception | Концепция | false | true | true | true | STRING |  |
| Conception.Code | Код концепции | false | true | true | true | STRING |  |
| Contr-Account.Code | Код корр.счета | false | true | true | false | STRING |  |
| Contr-Account.Group | Группа корр.счета | false | true | true | false | ENUM | Расшифровки кодов базовых типов#Группа счета |
| Contr-Account.Name | Корр.Счет/Склад | false | true | true | false | STRING |  |
| Contr-Account.Type | Тип корр.счета | false | true | true | false | ENUM | Расшифровки кодов базовых типов#Тип счета |
| Contr-Amount | Корр.количество | true | false | false | false | AMOUNT |  |
| Contr-Product.AccountingCategory | Корр.Бухгалтерская категория | false | true | true | false | STRING |  |
| Contr-Product.AlcoholClass | Класс алкогольной продукции | false | true | true | false | STRING |  |
| Contr-Product.AlcoholClass.Code | Код класса алкогольной продукции | false | true | true | false | STRING |  |
| Contr-Product.AlcoholClass.Group | Группа алкогольной продукции | false | true | true | false | STRING |  |
| Contr-Product.AlcoholClass.Type | Тип алкогольной продукции | false | true | true | false | ENUM | Расшифровки кодов базовых типов#Тип алкогольной продукции |
| Contr-Product.Category | Корр.Категория номенклатуры | false | true | true | false | STRING |  |
| Contr-Product.CookingPlaceType | Корр.Тип места приготовления | false | true | true | false | STRING |  |
| Contr-Product.Hierarchy | Корр.Иерархия номенклатуры | false | true | true | false | STRING |  |
| Contr-Product.MeasureUnit | Корр.Единица измерения | false | true | true | false | STRING |  |
| Contr-Product.Name | Корр.Элемент номенклатуры | false | true | true | false | STRING |  |
| Contr-Product.Num | Корр.Артикул элемента номенклатуры | false | true | true | false | STRING |  |
| Contr-Product.SecondParent | Корр.Группа номенклатуры 2-го уровня | false | true | true | false | STRING |  |
| Contr-Product.ThirdParent | Корр.Группа номенклатуры 3-го уровня | false | true | true | false | STRING |  |
| Contr-Product.TopParent | Корр.Группа номенклатуры 1-го уровня | false | true | true | false | STRING |  |
| Contr-Product.Type | Корр.Тип элемента номенклатуры | false | true | true | false | ENUM | Расшифровки кодов базовых типов#Тип элемента номенклатуры |
| Counteragent.Name | Контрагент | false | true | true | true | STRING |  |
| DateTime (до версии 4.2; в 4.2+ deprecated, заменено на DateTime.Typed) | Дата и время | false | true | true | true\* | STRING |  |
| DateTime.Typed (4.2+) | Дата и время | false | true | true | true\* | DATETIME |  |
| DateTime.Date (до версии 4.2; в 4.2+ deprecated, заменено на DateTime.DateTyped) | Учетный день | false | true | true | true\* | STRING |  |
| DateTime.DateTyped (4.2+) | Учетный день | false | true | true | true\* | DATE |  |
| DateTime.DayOfWeak | День недели | false | true | true | true\* | STRING |  |
| DateTime.Hour | Час | false | true | true | true\* | STRING |  |
| DateTime.Month | Месяц | false | true | true | true\* | STRING |  |
| DateTime.Year | Год | false | true | true | true\* | STRING |  |
| DateSecondary.DateTyped (добавлено в 6.0) | Дата проводки | false | true | true |  | DATE |  |
| DateSecondary.DateTimeTyped (добавлено в 6.0) | Дата и время проводки | false | true | true |  | DATETIME |  |
| Department | Торговое предприятие | false | true | true | true | STRING |  |
| Department.Category1 | Категория 1 | false | true | true | true | STRING |  |
| Department.Category2 | Категория 2 | false | true | true | true | STRING |  |
| Department.Category3 | Категория 3 | false | true | true | true | STRING |  |
| Department.Category4 | Категория 4 | false | true | true | true | STRING |  |
| Department.Category5 | Категория 5 | false | true | true | true | STRING |  |
| Department.Code | Код подразделения | false | true | true | true | STRING |  |
| Department.JurPerson | Юридическое лицо | false | true | true | true | STRING |  |
| Document | Номер документа | false | true | true | false | STRING |  |
| FinalBalance.Amount | Конечный остаток товара | true | false | false | - | AMOUNT | Тяжелый запрос, рекомендуется запускать только ночью.<br>См. выше. |
| FinalBalance.Money | Конечный денежный остаток | true | false | false | - | MONEY | Тяжелый запрос, рекомендуется запускать только ночью.<br>См. выше. |
| PercentOfSummary.ByCol | % по столбцу | true | false | false | false | PERCENT |  |
| PercentOfSummary.ByRow | % по строке | true | false | false | false | PERCENT |  |
| Product.AccountingCategory | Бухгалтерская категория | false | true | true | true | STRING |  |
| Product.AlcoholClass | Класс алкогольной продукции | false | true | true | true | STRING |  |
| Product.AlcoholClass.Code | Код класса алкогольной продукции | false | true | true | true | STRING |  |
| Product.AlcoholClass.Group | Группа алкогольной продукции | false | true | true | true | STRING |  |
| Product.AlcoholClass.Type | Тип алкогольной продукции | false | true | true | true | ENUM | Расшифровки кодов базовых типов#Тип алкогольной продукции |
| Product.AvgSum | Средняя цена | true | false | false | - | MONEY |  |
| Product.Category | Категория номенклатуры | false | true | true | true | STRING |  |
| Product.CookingPlaceType | Тип места приготовления | false | true | true | true | STRING |  |
| Product.Hierarchy | Иерархия номенклатуры | false | true | true | true | STRING |  |
| Product.MeasureUnit | Единица измерения | false | true | true | true | STRING |  |
| Product.Name | Элемент номенклатуры | false | true | true | true | STRING |  |
| Product.Num | Артикул элемента номенклатуры | false | true | true | true | STRING |  |
| Product.SecondParent | Группа номенклатуры 2-го уровня | false | true | true | true | STRING |  |
| Product.ThirdParent | Группа номенклатуры 3-го уровня | false | true | true | true | STRING |  |
| Product.TopParent | Группа номенклатуры 1-го уровня | false | true | true | true | STRING |  |
| Product.Type | Тип элемента номенклатуры | false | true | true | true | ENUM | Расшифровки кодов базовых типов#Тип элемента номенклатуры |
| Session.CashRegister | Касса | false | true | true | false | STRING |  |
| Session.Group | Группа | false | true | true | false | STRING |  |
| Session.RestaurantSection | Отделение | false | true | true | false | STRING |  |
| StartBalance.Amount | Начальный остаток товара | true | false | false | - | AMOUNT | Тяжелый запрос, рекомендуется запускать только ночью.<br>См. выше. |
| StartBalance.Money | Начальный денежный остаток | true | false | false | - | MONEY | Тяжелый запрос, рекомендуется запускать только ночью.<br>См. выше. |
| Store | Склад | false | true | true | false | STRING | Склад: первый попавшийся склад проводки, взятый из: левой, правой части проводки, строки документа или самого документа. |
| Sum.Incoming | Сумма прихода | true | false | false | - | MONEY |  |
| Sum.Outgoing | Сумма расхода | true | false | false | - | MONEY |  |
| Sum.PartOfIncome | % от выручки | true | false | false | - | PERCENT |  |
| Sum.PartOfSummaryByCol | % суммы от итога по столбцам | true | false | false | - | PERCENT |  |
| Sum.PartOfSummaryByRow | % суммы от итога по строкам | true | false | false | - | PERCENT |  |
| Sum.PartOfTotalIncome | % от общей выручки | true | false | false | - | PERCENT |  |
| Sum.ResignedSum | Сумма | true | false | false | - | MONEY |  |
| TransactionSide | Дебет/Кредит | false | true | true | false | ENUM | Расшифровки кодов базовых типов#Дебит/Кредит |
| TransactionType | Тип транзакции | false | true | true | false | ENUM |  |
| TransactionType.Code | Код транзакции | false | true | true | false | OBJECT |  |

\* группировки по дате отбрасываются при вычислении начальных остатков
 [+] [Описание полей OLAP отчета по продажам](javascript:void%280%29)
 [-] [Описание полей OLAP отчета по продажам](javascript:void%280%29)

# 

| **Name** | **Description** | **Description Eng** | **Aggreation** | **Grouping** | **Filterig** | **Type** | **Value** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AuthUser | Авторизовал | Authorised by | false | true | true | STRING |  |
| Banquet | Банкет | Banquet | false | true | true | ENUM | TRUE<br>FALSE |
| Bonus.CardNumber | Номер бонусной карты | Bonus card number | false | true | true | STRING |  |
| Bonus.Sum | Сумма бонуса | Bonus amount | true | false | false | MONEY |  |
| Bonus.Type | Тип бонуса | Bonus type | false | true | true | STRING |  |
| Card | Карта авторизации | Authorisation card | false | true | true | STRING |  |
| CardNumber | Номер карты оплаты | Pay card type | false | true | true | STRING |  |
| CardOwner | Владелец карты гостя | Guest cardholder | false | true | true | STRING |  |
| CardType | Кредитная карта | Credit card | false | true | true | STRING |  |
| Cashier | Кассир | Cashier | false | true | true | STRING |  |
| CashLocation | Расположение кассы | Cash register location | false | true | true | STRING |  |
| CashRegisterName | Касса | Cash register | false | true | true | STRING |  |
| CloseTime | Время закрытия | Closing time | false | true | true | DATETIME |  |
| Comment | Комментарий к блюду | Item comment | false | true | true | STRING |  |
| Conception | Концепция | Concept | false | true | true | STRING |  |
| CookingPlace | Место приготовления | Production place | false | true | true | STRING |  |
| CreditUser | В кредит на... | Credited to... | false | true | true | STRING |  |
| DayOfWeekOpen | День недели | Day of week | false | true | true | STRING |  |
| DeletedWithWriteoff | Блюдо удалено | Item deleted | false | true | true | ENUM | Расшифровки кодов базовых типов#Типы удаления блюд |
| DeletionComment | Комментарий к удалению блюда | Item deletion comment | false | true | true | STRING |  |
| Delivery.IsDelivery | Доставка | Delivery | false | true | true | ENUM | Расшифровки кодов базовых типов#Признак доставки |
| Department | Торговое предприятие | Outlet | false | true | true | STRING |  |
| DiscountPercent | Процент скидки | Discount rate | true | true | true | PERCENT |  |
| DiscountSum | Сумма скидки | Discount amount | true | false | true | MONEY |  |
| discountWithoutVAT | Сумма скидки без НДС не включенного в стоимость | Discount amount excl. VAT not included in the cost | true | false | true | MONEY |  |
| DishAmountInt | Количество блюд | Number of items | true | true | true | AMOUNT |  |
| DishCategory | Категория блюда | Item category | false | true | true | STRING |  |
| DishCode | Код блюда | Item code | false | true | true | STRING |  |
| DishCode.Quick | Код быстрого набора блюда | Item quick code | false | true | true | STRING |  |
| DishDiscountSumInt | Сумма со скидкой | Amount with discount | true | false | false | MONEY |  |
| DishDiscountSumInt.average | Средняя сумма заказа | Average bill amount | true | false | false | MONEY |  |
| DishDiscountSumInt.averageByGuest | Средняя выручка с гостя | Average revenue per guest | true | false | false | MONEY |  |
| DishDiscountSumInt.averagePrice | Средняя цена без НДС | Average price (VAT exclusive) | true | false | false | MONEY |  |
| DishDiscountSumInt.withoutVAT | Сумма со скидкой без НДС | Amount with discount VAT exclusive | true | false | false | MONEY |  |
| DishForeignName | Наименование блюда на иностранном языке | Item name in a foreign language | false | true | true | STRING |  |
| DishFullName | Полное наименование блюда | Full name of the item | false | true | true | STRING |  |
| DishGroup | Группа блюда | Item group | false | true | true | STRING |  |
| DishGroup.Hierarchy | Иерархия блюда | Item hierarchy | false | true | true | STRING |  |
| DishGroup.Num | Код группы блюда | Item group code | false | true | true | STRING |  |
| DishGroup.SecondParent | Группа блюда 2-го уровня | Level 2 item group | false | true | true | STRING |  |
| DishGroup.ThirdParent | Группа блюда 3-го уровня | Level 3 item group | false | true | true | STRING |  |
| DishGroup.TopParent | Группа блюда 1-го уровня | Level 1 item group | false | true | true | STRING |  |
| DishMeasureUnit | Единица измерения | Measurement unit | false | true | true | STRING |  |
| DishName | Блюдо | Item | false | true | true | STRING |  |
| DishReturnSum | Сумма возврата | Void amount | true | true | true | MONEY |  |
| DishServicePrintTime | Сервисная печать блюда | Service printing item | false | true | true | DATETIME |  |
| DishServicePrintTime.Max | Сервисная печать последнего блюда | Service printing latest item | true | false | false | DATETIME |  |
| DishServicePrintTime.OpenToLastPrintDuration | Длит: откр.-посл.серв.печать | Duration: open latest serv. print. | true | false | false | INTEGER |  |
| DishSumInt | Сумма без скидки | Amount without discount | true | false | false | MONEY |  |
| DishType | Тип товара | Stock list type | false | true | true | ENUM | Расшифровки кодов базовых типов#Тип товара |
| fullSum | Сумма без НДС не включенного в стоимость | Amount excl. VAT not included in the cost | true | false | true | MONEY |  |
| GuestNum | Количество гостей | Number of guests | true | true | true | AMOUNT |  |
| GuestNum.Avg | Ср.кол-во гостей на чек | AvgNumber of guests per receipt | true | false | false | AMOUNT |  |
| HourClose | Час закрытия | Closing hour | false | true | true | STRING |  |
| HourOpen | Час открытия | Opening hour | false | true | true | STRING |  |
| IncentiveSumBase.Sum | Мотивационный бонус | Incentive payment | true | false | false | MONEY |  |
| IncreasePercent | Процент надбавки | Surcharge rate | true | true | true | PERCENT |  |
| IncreaseSum | Сумма надбавки | Surcharge amount | true | true | true | MONEY |  |
| JurName | Юридическое лицо | Legal entity | false | true | true | STRING |  |
| Mounth | Месяц | Month | false | true | true | STRING |  |
| NonCashPaymentType | Безналичный тип оплаты | Non-cash payment type | false | true | true | STRING |  |
| NonCashPaymentType.DocumentType | Тип документа | Document type | false | true | true | ENUM | Расшифровки кодов базовых типов#Тип документа |
| OpenDate (до версии 4.2; в 4.2+ deprecated, заменено на OpenDate.Typed) | Учетный день |  | false | true | true | STRING |  |
| OpenDate.Typed (4.2+) | Учетный день |  | false | true | true | DATE |  |
| OpenTime | Время открытия | Opening time | false | true | true | DATETIME |  |
| OperationType | Операция | Operation | false | true | true | ENUM | Расшифровки кодов базовых типов#Тип операции |
| OrderDeleted | Заказ удален | Order deleted | false | true | true | ENUM | Расшифровки кодов базовых типов#Признак удаления заказа |
| OrderDiscount.GuestCard | Гостевая карта | Guest card | false | true | true | STRING |  |
| OrderDiscount.Type | Тип скидки | Discount type | false | true | true | STRING |  |
| OrderIncrease.Type | Тип надбавки | Type of surcharge | false | true | true | STRING |  |
| OrderItems | Позиций чека | Order items | true | false | false | INTEGER |  |
| OrderNum | Номер чека | Receipt number | true | true | true | INTEGER |  |
| OrderTime.AverageOrderTime | Ср.время обсл.(мин) | AvgServing time (min) | true | false | false | AMOUNT |  |
| OrderTime.AveragePrechequeTime | Ср.время в пречеке (мин) | Avg time in guest bill (min) | true | false | false | AMOUNT |  |
| OrderTime.OrderLength | Время обслуживания (мин) | Serving time (min) | false | true | true | INTEGER |  |
| OrderTime.OrderLengthSum | Время обсл.сумм.(мин) | Serving time (min) | true | false | false | INTEGER |  |
| OrderTime.PrechequeLength | Время в пречеке (мин) | Time in guest bill (min) | false | true | true | INTEGER |  |
| OrderType | Тип заказа | Order type | false | true | true | STRING |  |
| OrderWaiter.Name | Официант заказа | Waiter for the order | false | true | true | STRING |  |
| OriginName | Источник заказа | Order origin | false | true | true | STRING |  |
| PayTypes | Тип оплаты | Payment type | false | true | true | STRING |  |
| PayTypes.Combo | Тип оплаты (комб.) | Payment type (comb.) | false | true | true | STRING |  |
| PayTypes.Group | Группа оплаты | Payment group | false | true | true | ENUM | Расшифровки кодов базовых типов#Группа оплаты |
| PayTypes.IsPrintCheque | Фиск. тип оплаты | Fisc. payment type | false | true | true | ENUM | Расшифровки кодов базовых типов#Признак фискальности оплаты |
| PayTypes.VoucherNum | Количество ваучеров | Number of vouchers | true | false | false | INTEGER |  |
| PercentOfSummary.ByCol | % по столбцу | % by column | true | false | false | PERCENT |  |
| PercentOfSummary.ByRow | % по строке | % by row | true | false | false | PERCENT |  |
| PrechequeTime | Время пречека | Guest bill time | false | true | true | DATETIME |  |
| PriceCategory | Ценовая категория клиента | Customer price category | false | true | true | STRING |  |
| PriceCategoryCard | ЦК номер карты | Price Category Card Number | false | true | true | STRING |  |
| PriceCategoryDiscountCardOwner | ЦК владелец карты | Price Category Cardholder | false | true | true | STRING |  |
| PriceCategoryUserCardOwner | ЦК контрагент | Price Category Card Owner | false | true | true | STRING |  |
| ProductCostBase.MarkUp | Наценка(%) | Markup (%) | true | false | false | PERCENT |  |
| ProductCostBase.OneItem | Себестоимость единицы | Cost per unit | true | false | false | MONEY |  |
| ProductCostBase.Percent | Себестоимость(%) | Cost(%) | true | false | false | PERCENT |  |
| ProductCostBase.ProductCost | Себестоимость | Cost | true | false | false | MONEY |  |
| ProductCostBase.Profit | Наценка | Markup | true | false | false | MONEY |  |
| RemovalType | Причина удаления блюда | Reason for item deletion | false | true | true | STRING |  |
| RestaurantSection | Отделение | Room | false | true | true | STRING |  |
| RestorauntGroup | Группа | Group | false | true | true | STRING |  |
| SessionNum | Номер смены | Shift number | false | true | true | INTEGER |  |
| SoldWithDish | Продано с блюдом | Sold with item | false | true | true | STRING |  |
| Store.Name | Со склада | From storage | false | true | true | STRING |  |
| StoreTo | На склад | To storage | false | true | true | STRING |  |
| Storned | Возврат чека | Void receipt | false | true | true | ENUM | TRUE<br>FALSE |
| sumAfterDiscountWithoutVAT | Сумма со скидкой без НДС не включенного в стоимость | Amount with discount excl. VAT not included in the cost | true | false | true | MONEY |  |
| TableNumInt (до 5.1; в 5.1+ заменено на TableNum) | Номер стола |  | false | true | true | STRING |  |
| TableNum (5.1+) | Номер стола |  | false | true | true | INTEGER |  |
| UniqOrderId | Чеков | Orders | true | false | false | INTEGER |  |
| UniqOrderId.OrdersCount | Заказов | Orders | true | false | false | AMOUNT |  |
| VAT.Percent | НДС(%) | VAT(%) | true | true | true | PERCENT |  |
| VAT.Sum | НДС по чекам(Сумма) | VAT by bill (Amount) | true | true | true | MONEY |  |
| WaiterName | Официант блюда | Item waiter | false | true | true | STRING |  |
| WriteoffReason | Причина списания | Write-off reason | false | true | true | STRING |  |
| WriteoffUser | Списано на сотрудника | Written off to employee | false | true | true | STRING |  |
| YearOpen | Год | Year | false | true | true | STRING |  |
 [+] [Описание полей OLAP отчета по контролю хранения](javascript:void%280%29)
 [-] [Описание полей OLAP отчета по контролю хранения](javascript:void%280%29)
 | Name | Description | Aggreation | Grouping | Type | Value |
| --- | --- | --- | --- | --- | --- |
| ProductNum | Артикул | false | true | STRING |  |
| ProductName | Блюдо | false | true | STRING |  |
| ProductAccountingCategory | Бухгалтерская категория блюда | false | true | STRING |  |
| EventDate | Дата | false | true | DATETIME |  |
| EventCookingDate | Дата и время приготовления | false | true | DATETIME |  |
| ProductMeasureUnit | Единицы измерения | false | true | STRING |  |
| ProductCategory | Категория блюда | false | true | STRING |  |
| Department.Code | Код подразделения | false | true | STRING |  |
| Amount | Количество | false | true | AMOUNT |  |
| ProductExpirationDuration | Просрочка на момент продажи | true | false | DATETIME |  |
| ProductCostBase.OneItem | Себестоимость единицы, р. | true | false | MONEY |  |
| ProductCostBase.ProductCost | Себестоимость, р. | true | false | MONEY |  |
| StoreFrom | Склад | false | true | STRING |  |
| User | Сотрудник | false | true | STRING |  |
| AccountTo | Счет | false | true | STRING |  |
| Event.Type | Тип события | false | true | STRING |  |
| Department | Торговое предприятие | false | true | STRING |  |
