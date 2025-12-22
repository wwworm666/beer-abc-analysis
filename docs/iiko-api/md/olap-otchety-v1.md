# Olap Otchety V1

*Generated from PDF: olap-otchety-v1.pdf*

*Total pages: 30*

---


## Page 1

API Documentation Page1 of 30
1. OLAP-отчеты
OLAP-отчет
Версияiiko: 3.9
https://host:port/resto/api/reports/olap
Параметры запроса
Название Значение Описание
report SALES-Попродажам Типотчета
TRANSACTIONS-Потранзакциям
DELIVERIES-Подоставкам
STOCK-Контрольхранения
summary
true-вычислятьитоговыезначения Вычислятьлиитоговыезначения.
Поумолчаниювысталенtrue.При
false-невычислятьитоговыезначения значенииfalseотчетстроится
намногобыстрее.
сVersion(iiko)5.3
Сверсии9.1.2значениепо
умолчаниюfalse.
groupRow Полягруппировки,например: Дляопределениясписка
groupRow=WaiterName& доступныхполейсм.:
groupRow=OpenTime · ОписаниеполейOLAP
отчетапопродажам
· ОписаниеполейOLAP
отчетапопроводкам
· ОписаниеполейOLAP
отчетаподоставкам
Пополюможнопроводить
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

| report |  |  | SALES-Попродажам
TRANSACTIONS-Потранзакциям
DELIVERIES-Подоставкам
STOCK-Контрольхранения |  |  | Типотчета |  |  |

| summary |  |  | true-вычислятьитоговыезначения
false-невычислятьитоговыезначения |  |  | Вычислятьлиитоговыезначения.
Поумолчаниювысталенtrue.При
значенииfalseотчетстроится
намногобыстрее.
сVersion(iiko)5.3
Сверсии9.1.2значениепо
умолчаниюfalse. |  |  |

| groupRow |  |  | Полягруппировки,например:
groupRow=WaiterName&
groupRow=OpenTime |  |  | Дляопределениясписка
доступныхполейсм.:
· ОписаниеполейOLAP
отчетапопродажам
· ОписаниеполейOLAP
отчетапопроводкам
· ОписаниеполейOLAP
отчетаподоставкам
Пополюможнопроводить |  |  |


---


## Page 2

API Documentation Page2 of 30
Название Значение Описание
группировку,еслизначениев
колонкеGroupingдляполяравно
true
groupCol Полядлявыделениязначенийпоколонкам Дляопределениясписка
доступныхполейсм.:
· ОписаниеполейOLAP
отчетапопродажам
· ОписаниеполейOLAP
отчетапопроводкам
· ОписаниеполейOLAP
отчетаподоставкам
Пополюможнопроводить
группировку,еслизначениев
колонкеGroupingдляполяравно
true
agr Поляагрегации,например: · Дляопределениясписка
agr=DishDiscountSum&agr=VoucherNum доступныхполейсм.:
o Описаниеполей
OLAPотчетапо
продажам
o Описаниеполей
OLAPотчетапо
проводкам
o Описаниеполей
OLAPотчетапо
доставкам
Пополюможнопроводить
агрегацию,еслизначениев
колонкеAggregationдляполя
равноtrue
from DD.MM.YYYY Начальнаядата
to DD.MM.YYYY Конечнаядата
Что в ответе
Структура report.
Пример запроса
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|

|  | Название |  |  | Значение |  |  | Описание |  |

|  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  | группировку,еслизначениев
колонкеGroupingдляполяравно
true |  |  |

| groupCol |  |  | Полядлявыделениязначенийпоколонкам |  |  | Дляопределениясписка
доступныхполейсм.:
· ОписаниеполейOLAP
отчетапопродажам
· ОписаниеполейOLAP
отчетапопроводкам
· ОписаниеполейOLAP
отчетаподоставкам
Пополюможнопроводить
группировку,еслизначениев
колонкеGroupingдляполяравно
true |  |  |

| agr |  |  | Поляагрегации,например:
agr=DishDiscountSum&agr=VoucherNum |  |  | · Дляопределениясписка
доступныхполейсм.:
o Описаниеполей
OLAPотчетапо
продажам
o Описаниеполей
OLAPотчетапо
проводкам
o Описаниеполей
OLAPотчетапо
доставкам
Пополюможнопроводить
агрегацию,еслизначениев
колонкеAggregationдляполя
равноtrue |  |  |

| from |  |  | DD.MM.YYYY |  |  | Начальнаядата |  |  |

| to |  |  | DD.MM.YYYY |  |  | Конечнаядата |  |  |


---


## Page 3

API Documentation Page3 of 30
https://localhost:8080/resto/api/reports/olap?key=ec621550-afae-
133e-80c8-
76155db2b268&report=SALES&from=01.12.2014&to=18.12.2014&groupRow=
WaiterName&groupRow=OpenTime&agr=fullSum&agr=OrderNum
Описание полей OLAP-отчетов
[+] Описание полейOLAP-отчета подоставкам
[-] Описание полейOLAP-отчета подоставкам
Aggreatio Groupin Filterin
Name Description Type Value
n g g
DATETIM
CloseTime Времязакрытия false true true
E
Фактическое DATETIM
Delivery.ActualTime false true true
времядоставки E
Delivery.Address Адрес false true true STRING
Времяпечати DATETIM
Delivery.BillTime false true true
накладной E
Причина
Delivery.CancelCause отмены false true true STRING
доставки
Delivery.City Город false true true STRING
Времязакрытия DATETIM
Delivery.CloseTime false true true
доставки E
Длит:
Delivery.CookingToSendDuration посл.серв.печат true false false INTEGER
ь-отправка
Allrightsreserved © CompanyInc., 2023


### Table:

|  |

|---|

| https://localhost:8080/resto/api/reports/olap?key=ec621550-afae-
133e-80c8-
76155db2b268&report=SALES&from=01.12.2014&to=18.12.2014&groupRow=
WaiterName&groupRow=OpenTime&agr=fullSum&agr=OrderNum |

|  |



### Table:

| Name | Description | Aggreatio
n | Groupin
g | Filterin
g | Type | Value |

|---|---|---|---|---|---|---|

| CloseTime | Времязакрытия | false | true | true | DATETIM
E |  |

| Delivery.ActualTime | Фактическое
времядоставки | false | true | true | DATETIM
E |  |

| Delivery.Address | Адрес | false | true | true | STRING |  |

| Delivery.BillTime | Времяпечати
накладной | false | true | true | DATETIM
E |  |

| Delivery.CancelCause | Причина
отмены
доставки | false | true | true | STRING |  |

| Delivery.City | Город | false | true | true | STRING |  |

| Delivery.CloseTime | Времязакрытия
доставки | false | true | true | DATETIM
E |  |

| Delivery.CookingToSendDuration | Длит:
посл.серв.печат
ь-отправка | true | false | false | INTEGER |  |


---


## Page 4

API Documentation Page4 of 30
Delivery.Courier Курьер false true true STRING
Номеркарты
Delivery.CustomerCardNumber клиента false true true STRING
доставки
Типкарты
Delivery.CustomerCardType клиента false true true STRING
доставки
Комментарийк
Delivery.CustomerComment false true true STRING
клиенту
Delivery.CustomerCreatedDate
(доверсии4.2;в4.2+deprecated, Датасоздания
false true true STRING
замененона клиента
Delivery.CustomerCreatedDateTyped
)
Delivery.CustomerCreatedDateTyped Датасоздания
false true true DATE
(4.2+) клиента
Реклама
Delivery.CustomerMarketingSource false true true STRING
клиента
ФИОклиента
Delivery.CustomerName false true true STRING
доставки
Опоздание
Delivery.Delay false true true INTEGER
доставки(мин)
Ср.опоздание
Delivery.DelayAvg true false false AMOUNT
доставки(мин)
Allrightsreserved © CompanyInc., 2023


### Table:

| Delivery.Courier | Курьер | false | true | true | STRING |  |

|---|---|---|---|---|---|---|

| Delivery.CustomerCardNumber | Номеркарты
клиента
доставки | false | true | true | STRING |  |

| Delivery.CustomerCardType | Типкарты
клиента
доставки | false | true | true | STRING |  |

| Delivery.CustomerComment | Комментарийк
клиенту | false | true | true | STRING |  |

| Delivery.CustomerCreatedDate
(доверсии4.2;в4.2+deprecated,
замененона
Delivery.CustomerCreatedDateTyped
) | Датасоздания
клиента | false | true | true | STRING |  |

| Delivery.CustomerCreatedDateTyped
(4.2+) | Датасоздания
клиента | false | true | true | DATE |  |

| Delivery.CustomerMarketingSource | Реклама
клиента | false | true | true | STRING |  |

| Delivery.CustomerName | ФИОклиента
доставки | false | true | true | STRING |  |

| Delivery.Delay | Опоздание
доставки(мин) | false | true | true | INTEGER |  |

| Delivery.DelayAvg | Ср.опоздание
доставки(мин) | true | false | false | AMOUNT |  |


---


## Page 5

API Documentation Page5 of 30
Комментарийк
Delivery.DeliveryComment false true true STRING
доставке
Оператор
Delivery.DeliveryOperator false true true STRING
доставки
Delivery.Email e-mailдоставки false true true STRING
Планируемое DATETIM
Delivery.ExpectedTime false true true
времядоставки E
Delivery.MarketingSource Реклама false true true STRING
Delivery.Number Номердоставки false true true INTEGER
Телефон
Delivery.Phone false true true STRING
доставки
Времяпечати DATETIM
Delivery.PrintTime false true true
доставки E
Delivery.Region Район false true true STRING
Времяотправки DATETIM
Delivery.SendTime false true true
доставки E
PICKUP
Delivery.ServiceType Типдоставки false true true ENUM COURIE
R
Allrightsreserved © CompanyInc., 2023


### Table:

| Delivery.DeliveryComment | Комментарийк
доставке | false | true | true | STRING |  |

|---|---|---|---|---|---|---|

| Delivery.DeliveryOperator | Оператор
доставки | false | true | true | STRING |  |

| Delivery.Email | e-mailдоставки | false | true | true | STRING |  |

| Delivery.ExpectedTime | Планируемое
времядоставки | false | true | true | DATETIM
E |  |

| Delivery.MarketingSource | Реклама | false | true | true | STRING |  |

| Delivery.Number | Номердоставки | false | true | true | INTEGER |  |

| Delivery.Phone | Телефон
доставки | false | true | true | STRING |  |

| Delivery.PrintTime | Времяпечати
доставки | false | true | true | DATETIM
E |  |

| Delivery.Region | Район | false | true | true | STRING |  |

| Delivery.SendTime | Времяотправки
доставки | false | true | true | DATETIM
E |  |

| Delivery.ServiceType | Типдоставки | false | true | true | ENUM | PICKUP
COURIE
R |


---


## Page 6

API Documentation Page6 of 30
Источник
Delivery.SourceKey false true true STRING
доставки
Delivery.Street Улица false true true STRING
Времяв
Delivery.WayDuration false true true INTEGER
пути(мин)
Ср.времяв
Delivery.WayDurationAvg true false false AMOUNT
пути(мин)
Сумм.времяв
Delivery.WayDurationSum true false false INTEGER
пути(мин)
Сервисная
печать DATETIM
DishServicePrintTime.Max true false false
последнего E
блюда
[+] Описание полейOLAP отчета попроводкам
[-] Описание полейOLAP отчета попроводкам
Поляагрегации,учитывающиеначальныйостатоктовараиденежныйостаток(StartBalance.Amount,
StartBalance.Money,FinalBalance.Amount,FinalBalance.Money)вычисляютсясуммированиемвсейтаблицы
проводокзавсевремяработысистемы(всейбазыданных)безкаких-либооптимизаций.Тоесть,такой
запросможетвыполнятьсяоченьдолгоизамедлятьработусервера.
Еслиначальныйостатокнеобходим,оставляйтевэтомOLAP-запросетолькотеполягруппировки,по
которымондействительнонеобходим(какправило,этоAccount.NameиProduct.Name),ивызывайтетакой
запроскакможнорежеивнерабочеевремя.
В5.2добавленоAPIдлябыстрогополученияостатков:Отчетыпобалансам.Вовсехслучаях
рекомендуетсяпользоватьсяимвместоOLAP.
В5.5OLAP-отчетысостаткамиоптимизированысиспользованиембалансовыхтаблицATransactionSum,
ATransactionBalance,приусловии,чтоприменяютсягруппировкиифильтрыпополямизэтихтаблиц,см.
признакStartBalanceOptimizableвописанииполей.
Тоесть,правильносоставленныйзапросприведетксуммированиюневсейтаблицыпроводок,атолько
лишьоткрытогопериода.Обратитеособоевниманиенато,чтооптимизированотолькополеAccount.Name
(счет"текущей"стороныпроводки,втомчислесклад),анеStore(первыйпопавшийся"склад"проводки,
Allrightsreserved © CompanyInc., 2023


### Table:

| Delivery.SourceKey | Источник
доставки | false | true | true | STRING |  |

|---|---|---|---|---|---|---|

| Delivery.Street | Улица | false | true | true | STRING |  |

| Delivery.WayDuration | Времяв
пути(мин) | false | true | true | INTEGER |  |

| Delivery.WayDurationAvg | Ср.времяв
пути(мин) | true | false | false | AMOUNT |  |

| Delivery.WayDurationSum | Сумм.времяв
пути(мин) | true | false | false | INTEGER |  |

| DishServicePrintTime.Max | Сервисная
печать
последнего
блюда | true | false | false | DATETIM
E |  |



### Table:

|  | Поляагрегации,учитывающиеначальныйостатоктовараиденежныйостаток(StartBalance.Amount,
StartBalance.Money,FinalBalance.Amount,FinalBalance.Money)вычисляютсясуммированиемвсейтаблицы
проводокзавсевремяработысистемы(всейбазыданных)безкаких-либооптимизаций.Тоесть,такой
запросможетвыполнятьсяоченьдолгоизамедлятьработусервера.
Еслиначальныйостатокнеобходим,оставляйтевэтомOLAP-запросетолькотеполягруппировки,по
которымондействительнонеобходим(какправило,этоAccount.NameиProduct.Name),ивызывайтетакой
запроскакможнорежеивнерабочеевремя.
В5.2добавленоAPIдлябыстрогополученияостатков:Отчетыпобалансам.Вовсехслучаях
рекомендуетсяпользоватьсяимвместоOLAP.
В5.5OLAP-отчетысостаткамиоптимизированысиспользованиембалансовыхтаблицATransactionSum,
ATransactionBalance,приусловии,чтоприменяютсягруппировкиифильтрыпополямизэтихтаблиц,см.
признакStartBalanceOptimizableвописанииполей.
Тоесть,правильносоставленныйзапросприведетксуммированиюневсейтаблицыпроводок,атолько
лишьоткрытогопериода.Обратитеособоевниманиенато,чтооптимизированотолькополеAccount.Name
(счет"текущей"стороныпроводки,втомчислесклад),анеStore(первыйпопавшийся"склад"проводки, |

|---|---|

|  |  |

|  |  |


---


## Page 7

API Documentation Page7 of 30
взятыйиз:левой,правойчастипроводки,строкидокументаилисамогодокумента).
Складвсегда,когдатольковозможно,следуетбратьизполяAccount.Name("Счет"),анеStore("Склад"),
оновычисляетсягораздобыстрее.
Aggrea Grou Filte StartBakanceOpti
Name Description Type Value
tion ping rig mizable
Account.AccountHierarch Иерархия STRIN
false true true true
yFull счета G
Account.AccountHierarch Счет2-го STRIN
false true true true
ySecond уровня G
Account.AccountHierarch Счет3-го STRIN
false true true true
yThird уровня G
Account.AccountHierarch Счет1-го STRIN
false true true true
yTop уровня G
STRIN
Account.Code Кодсчета false true true true
G
Расшифровки
Account.CounteragentTyp Тип кодовбазовых
false true true true ENUM
e контрагента типов#Тип
Контрагента
Расшифровки
кодовбазовых
Account.Group Группасчета false true true true ENUM
типов#Группа
счета
Allrightsreserved © CompanyInc., 2023


### Table:

|  | взятыйиз:левой,правойчастипроводки,строкидокументаилисамогодокумента).
Складвсегда,когдатольковозможно,следуетбратьизполяAccount.Name("Счет"),анеStore("Склад"),
оновычисляетсягораздобыстрее. |

|---|---|



### Table:

| Name | Description | Aggrea
tion | Grou
ping | Filte
rig | StartBakanceOpti
mizable | Type | Value |

|---|---|---|---|---|---|---|---|

| Account.AccountHierarch
yFull | Иерархия
счета | false | true | true | true | STRIN
G |  |

| Account.AccountHierarch
ySecond | Счет2-го
уровня | false | true | true | true | STRIN
G |  |

| Account.AccountHierarch
yThird | Счет3-го
уровня | false | true | true | true | STRIN
G |  |

| Account.AccountHierarch
yTop | Счет1-го
уровня | false | true | true | true | STRIN
G |  |

| Account.Code | Кодсчета | false | true | true | true | STRIN
G |  |

| Account.CounteragentTyp
e | Тип
контрагента | false | true | true | true | ENUM | Расшифровки
кодовбазовых
типов#Тип
Контрагента |

| Account.Group | Группасчета | false | true | true | true | ENUM | Расшифровки
кодовбазовых
типов#Группа
счета |


---


## Page 8

API Documentation Page8 of 30
Расшифровки
кодовбазовых
Account.IsCashFlowAcco Участвуетли
false true true true ENUM типов#Участв
unt счетвДДС
уетлисчетв
ДДС
STRIN Счет(втом
Account.Name Счет false true true true
G числесклад)
Расшифровки
кодовбазовых
Account.StoreOrAccount Склад/счет false true true true ENUM
типов#Счет/С
клад
Расшифровки
кодовбазовых
Account.Type Типсчета false true true true ENUM
типов#Тип
счета
AMOU
Amount Количество true false false -
NT
Приход(кол- AMOU
Amount.In true false false -
во) NT
Расход(кол- AMOU
Amount.Out true false false -
во) NT
Amount.StoreInOut (до
версии4.3;в4.3+ Оборот
STRIN
deprecated,замененона эл.номенклат true false false -
G
Amount.StoreInOutTyped уры
)
Amount.StoreInOutTyped Оборот
AMOU
(4.3+,взамен эл.номенклат true false false -
NT
Amount.StoreInOut) уры
Allrightsreserved © CompanyInc., 2023


### Table:

| Account.IsCashFlowAcco
unt | Участвуетли
счетвДДС | false | true | true | true | ENUM | Расшифровки
кодовбазовых
типов#Участв
уетлисчетв
ДДС |

|---|---|---|---|---|---|---|---|

| Account.Name | Счет | false | true | true | true | STRIN
G | Счет(втом
числесклад) |

| Account.StoreOrAccount | Склад/счет | false | true | true | true | ENUM | Расшифровки
кодовбазовых
типов#Счет/С
клад |

| Account.Type | Типсчета | false | true | true | true | ENUM | Расшифровки
кодовбазовых
типов#Тип
счета |

| Amount | Количество | true | false | false | - | AMOU
NT |  |

| Amount.In | Приход(кол-
во) | true | false | false | - | AMOU
NT |  |

| Amount.Out | Расход(кол-
во) | true | false | false | - | AMOU
NT |  |

| Amount.StoreInOut (до
версии4.3;в4.3+
deprecated,замененона
Amount.StoreInOutTyped
) | Оборот
эл.номенклат
уры | true | false | false | - | STRIN
G |  |

| Amount.StoreInOutTyped
(4.3+,взамен
Amount.StoreInOut) | Оборот
эл.номенклат
уры | true | false | false | - | AMOU
NT |  |


---


## Page 9

API Documentation Page9 of 30
STRIN
CashFlowCategory СтатьяДДС false true true true
G
CashFlowCategory.Hierar Иерархия STRIN
false true true true
chy статейДДС G
CashFlowCategory.Hierar СтатьяДДС STRIN
false true true true
chyLevel1 1-гоуровня G
CashFlowCategory.Hierar СтатьяДДС STRIN
false true true true
chyLevel2 2-гоуровня G
CashFlowCategory.Hierar СтатьяДДС STRIN
false true true true
chyLevel3 3-гоуровня G
Расшифровки
Типстатьи кодовбазовых
CashFlowCategory.Type false true true true ENUM
ДДС типов#Тип
статьиДДС
STRIN
Comment Комментарий false true true false
G
STRIN
Conception Концепция false true true true
G
Код STRIN
Conception.Code false true true true
концепции G
Код STRIN
Contr-Account.Code false true true false
корр.счета G
Contr-Account.Group false true true false ENUM Расшифровки
Группа
кодовбазовых
Allrightsreserved © CompanyInc., 2023


### Table:

| CashFlowCategory | СтатьяДДС | false | true | true | true | STRIN
G |  |

|---|---|---|---|---|---|---|---|

| CashFlowCategory.Hierar
chy | Иерархия
статейДДС | false | true | true | true | STRIN
G |  |

| CashFlowCategory.Hierar
chyLevel1 | СтатьяДДС
1-гоуровня | false | true | true | true | STRIN
G |  |

| CashFlowCategory.Hierar
chyLevel2 | СтатьяДДС
2-гоуровня | false | true | true | true | STRIN
G |  |

| CashFlowCategory.Hierar
chyLevel3 | СтатьяДДС
3-гоуровня | false | true | true | true | STRIN
G |  |

| CashFlowCategory.Type | Типстатьи
ДДС | false | true | true | true | ENUM | Расшифровки
кодовбазовых
типов#Тип
статьиДДС |

| Comment | Комментарий | false | true | true | false | STRIN
G |  |

| Conception | Концепция | false | true | true | true | STRIN
G |  |

| Conception.Code | Код
концепции | false | true | true | true | STRIN
G |  |

| Contr-Account.Code | Код
корр.счета | false | true | true | false | STRIN
G |  |

| Contr-Account.Group | Группа | false | true | true | false | ENUM | Расшифровки
кодовбазовых |


---


## Page 10

API Documentation Page10 of 30
корр.счета типов#Группа
счета
Корр.Счет/Ск STRIN
Contr-Account.Name false true true false
лад G
Расшифровки
Тип кодовбазовых
Contr-Account.Type false true true false ENUM
корр.счета типов#Тип
счета
Корр.количес AMOU
Contr-Amount true false false false
тво NT
Contr- Корр.Бухгалт
STRIN
Product.AccountingCateg ерская false true true false
G
ory категория
Класс
Contr- STRIN
алкогольной false true true false
Product.AlcoholClass G
продукции
Contr- Кодкласса
STRIN
Product.AlcoholClass.Cod алкогольной false true true false
G
e продукции
Contr- Группа
STRIN
Product.AlcoholClass.Gro алкогольной false true true false
G
up продукции
Расшифровки
Contr- Тип кодовбазовых
Product.AlcoholClass.Typ алкогольной false true true false ENUM типов#Тип
e продукции алкогольной
продукции
Contr-Product.Category Корр.Категор false true true false
STRIN
ия
Allrightsreserved © CompanyInc., 2023


### Table:

|  | корр.счета |  |  |  |  |  | типов#Группа
счета |

|---|---|---|---|---|---|---|---|

| Contr-Account.Name | Корр.Счет/Ск
лад | false | true | true | false | STRIN
G |  |

| Contr-Account.Type | Тип
корр.счета | false | true | true | false | ENUM | Расшифровки
кодовбазовых
типов#Тип
счета |

| Contr-Amount | Корр.количес
тво | true | false | false | false | AMOU
NT |  |

| Contr-
Product.AccountingCateg
ory | Корр.Бухгалт
ерская
категория | false | true | true | false | STRIN
G |  |

| Contr-
Product.AlcoholClass | Класс
алкогольной
продукции | false | true | true | false | STRIN
G |  |

| Contr-
Product.AlcoholClass.Cod
e | Кодкласса
алкогольной
продукции | false | true | true | false | STRIN
G |  |

| Contr-
Product.AlcoholClass.Gro
up | Группа
алкогольной
продукции | false | true | true | false | STRIN
G |  |

| Contr-
Product.AlcoholClass.Typ
e | Тип
алкогольной
продукции | false | true | true | false | ENUM | Расшифровки
кодовбазовых
типов#Тип
алкогольной
продукции |

| Contr-Product.Category | Корр.Категор
ия | false | true | true | false | STRIN |  |


---


## Page 11

API Documentation Page11 of 30
номенклатур G
ы
Корр.Тип
Contr-
места STRIN
Product.CookingPlaceTyp false true true false
приготовлени G
e
я
Корр.Иерархи
я STRIN
Contr-Product.Hierarchy false true true false
номенклатур G
ы
Contr- Корр.Единиц STRIN
false true true false
Product.MeasureUnit аизмерения G
Корр.Элемент
STRIN
Contr-Product.Name номенклатур false true true false
G
ы
Корр.Артикул
элемента STRIN
Contr-Product.Num false true true false
номенклатур G
ы
Корр.Группа
Contr- STRIN
номенклатур false true true false
Product.SecondParent G
ы2-гоуровня
Корр.Группа
Contr- STRIN
номенклатур false true true false
Product.ThirdParent G
ы3-гоуровня
Корр.Группа
STRIN
Contr-Product.TopParent номенклатур false true true false
G
ы1-гоуровня
Allrightsreserved © CompanyInc., 2023


### Table:

|  | номенклатур
ы |  |  |  |  | G |  |

|---|---|---|---|---|---|---|---|

| Contr-
Product.CookingPlaceTyp
e | Корр.Тип
места
приготовлени
я | false | true | true | false | STRIN
G |  |

| Contr-Product.Hierarchy | Корр.Иерархи
я
номенклатур
ы | false | true | true | false | STRIN
G |  |

| Contr-
Product.MeasureUnit | Корр.Единиц
аизмерения | false | true | true | false | STRIN
G |  |

| Contr-Product.Name | Корр.Элемент
номенклатур
ы | false | true | true | false | STRIN
G |  |

| Contr-Product.Num | Корр.Артикул
элемента
номенклатур
ы | false | true | true | false | STRIN
G |  |

| Contr-
Product.SecondParent | Корр.Группа
номенклатур
ы2-гоуровня | false | true | true | false | STRIN
G |  |

| Contr-
Product.ThirdParent | Корр.Группа
номенклатур
ы3-гоуровня | false | true | true | false | STRIN
G |  |

| Contr-Product.TopParent | Корр.Группа
номенклатур
ы1-гоуровня | false | true | true | false | STRIN
G |  |


---


## Page 12

API Documentation Page12 of 30
Расшифровки
Корр.Тип
кодовбазовых
элемента
Contr-Product.Type false true true false ENUM типов#Тип
номенклатур
элемента
ы
номенклатуры
STRIN
Counteragent.Name Контрагент false true true true
G
DateTime (доверсии4.2;
в4.2+deprecated, STRIN
Датаивремя false true true true*
замененона G
DateTime.Typed)
DATET
DateTime.Typed(4.2+) Датаивремя false true true true*
IME
DateTime.Date (до
версии4.2;в4.2+ STRIN
Учетныйдень false true true true*
deprecated,замененона G
DateTime.DateTyped)
DateTime.DateTyped
Учетныйдень false true true true* DATE
(4.2+)
STRIN
DateTime.DayOfWeak Деньнедели false true true true*
G
STRIN
DateTime.Hour Час false true true true*
G
STRIN
DateTime.Month Месяц false true true true*
G
STRIN
DateTime.Year Год false true true true*
G
Дата
false true true DATE
DateSecondary.DateTyped проводки
Allrightsreserved © CompanyInc., 2023


### Table:

| Contr-Product.Type | Корр.Тип
элемента
номенклатур
ы | false | true | true | false | ENUM | Расшифровки
кодовбазовых
типов#Тип
элемента
номенклатуры |

|---|---|---|---|---|---|---|---|

| Counteragent.Name | Контрагент | false | true | true | true | STRIN
G |  |

| DateTime (доверсии4.2;
в4.2+deprecated,
замененона
DateTime.Typed) | Датаивремя | false | true | true | true* | STRIN
G |  |

| DateTime.Typed(4.2+) | Датаивремя | false | true | true | true* | DATET
IME |  |

| DateTime.Date (до
версии4.2;в4.2+
deprecated,замененона
DateTime.DateTyped) | Учетныйдень | false | true | true | true* | STRIN
G |  |

| DateTime.DateTyped
(4.2+) | Учетныйдень | false | true | true | true* | DATE |  |

| DateTime.DayOfWeak | Деньнедели | false | true | true | true* | STRIN
G |  |

| DateTime.Hour | Час | false | true | true | true* | STRIN
G |  |

| DateTime.Month | Месяц | false | true | true | true* | STRIN
G |  |

| DateTime.Year | Год | false | true | true | true* | STRIN
G |  |

| DateSecondary.DateTyped | Дата
проводки | false | true | true |  | DATE |  |


---


## Page 13

API Documentation Page13 of 30
(добавленов6.0)
DateSecondary.DateTime Датаивремя DATET
false true true
Typed(добавленов6.0) проводки IME
Торговое STRIN
Department false true true true
предприятие G
STRIN
Department.Category1 Категория1 false true true true
G
STRIN
Department.Category2 Категория2 false true true true
G
STRIN
Department.Category3 Категория3 false true true true
G
STRIN
Department.Category4 Категория4 false true true true
G
STRIN
Department.Category5 Категория5 false true true true
G
Код
STRIN
Department.Code подразделени false true true true
G
я
Юридическое STRIN
Department.JurPerson false true true true
лицо G
Номер STRIN
Document false true true false
документа G
FinalBalance.Amount Конечный true false false - Тяжелый
AMOU
остаток запрос,
Allrightsreserved © CompanyInc., 2023


### Table:

| (добавленов6.0) |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|

| DateSecondary.DateTime
Typed(добавленов6.0) | Датаивремя
проводки | false | true | true |  | DATET
IME |  |

| Department | Торговое
предприятие | false | true | true | true | STRIN
G |  |

| Department.Category1 | Категория1 | false | true | true | true | STRIN
G |  |

| Department.Category2 | Категория2 | false | true | true | true | STRIN
G |  |

| Department.Category3 | Категория3 | false | true | true | true | STRIN
G |  |

| Department.Category4 | Категория4 | false | true | true | true | STRIN
G |  |

| Department.Category5 | Категория5 | false | true | true | true | STRIN
G |  |

| Department.Code | Код
подразделени
я | false | true | true | true | STRIN
G |  |

| Department.JurPerson | Юридическое
лицо | false | true | true | true | STRIN
G |  |

| Document | Номер
документа | false | true | true | false | STRIN
G |  |

| FinalBalance.Amount | Конечный
остаток | true | false | false | - | AMOU | Тяжелый
запрос, |


---


## Page 14

API Documentation Page14 of 30
товара NT рекомендуется
запускать
тольконочью.
См.выше.
Тяжелый
запрос,
Конечный
MONE рекомендуется
FinalBalance.Money денежный true false false -
Y запускать
остаток
тольконочью.
См.выше.
PercentOfSummary.ByCo PERCE
%постолбцу true false false false
l NT
PercentOfSummary.ByRo PERCE
%построке true false false false
w NT
Product.AccountingCateg Бухгалтерска STRIN
false true true true
ory якатегория G
Класс
STRIN
Product.AlcoholClass алкогольной false true true true
G
продукции
Кодкласса
Product.AlcoholClass.Cod STRIN
алкогольной false true true true
e G
продукции
Группа
Product.AlcoholClass.Gro STRIN
алкогольной false true true true
up G
продукции
Расшифровки
Тип кодовбазовых
Product.AlcoholClass.Typ
алкогольной false true true true ENUM типов#Тип
e
продукции алкогольной
продукции
Allrightsreserved © CompanyInc., 2023


### Table:

|  | товара |  |  |  |  | NT | рекомендуется
запускать
тольконочью.
См.выше. |

|---|---|---|---|---|---|---|---|

| FinalBalance.Money | Конечный
денежный
остаток | true | false | false | - | MONE
Y | Тяжелый
запрос,
рекомендуется
запускать
тольконочью.
См.выше. |

| PercentOfSummary.ByCo
l | %постолбцу | true | false | false | false | PERCE
NT |  |

| PercentOfSummary.ByRo
w | %построке | true | false | false | false | PERCE
NT |  |

| Product.AccountingCateg
ory | Бухгалтерска
якатегория | false | true | true | true | STRIN
G |  |

| Product.AlcoholClass | Класс
алкогольной
продукции | false | true | true | true | STRIN
G |  |

| Product.AlcoholClass.Cod
e | Кодкласса
алкогольной
продукции | false | true | true | true | STRIN
G |  |

| Product.AlcoholClass.Gro
up | Группа
алкогольной
продукции | false | true | true | true | STRIN
G |  |

| Product.AlcoholClass.Typ
e | Тип
алкогольной
продукции | false | true | true | true | ENUM | Расшифровки
кодовбазовых
типов#Тип
алкогольной
продукции |


---


## Page 15

API Documentation Page15 of 30
MONE
Product.AvgSum Средняяцена true false false -
Y
Категория
STRIN
Product.Category номенклатур false true true true
G
ы
Типместа
Product.CookingPlaceTyp STRIN
приготовлени false true true true
e G
я
Иерархия
STRIN
Product.Hierarchy номенклатур false true true true
G
ы
Единица STRIN
Product.MeasureUnit false true true true
измерения G
Элемент
STRIN
Product.Name номенклатур false true true true
G
ы
Артикул
элемента STRIN
Product.Num false true true true
номенклатур G
ы
Группа
STRIN
Product.SecondParent номенклатур false true true true
G
ы2-гоуровня
Группа
STRIN
Product.ThirdParent номенклатур false true true true
G
ы3-гоуровня
Product.TopParent Группа false true true true
STRIN
номенклатур
Allrightsreserved © CompanyInc., 2023


### Table:

| Product.AvgSum | Средняяцена | true | false | false | - | MONE
Y |  |

|---|---|---|---|---|---|---|---|

| Product.Category | Категория
номенклатур
ы | false | true | true | true | STRIN
G |  |

| Product.CookingPlaceTyp
e | Типместа
приготовлени
я | false | true | true | true | STRIN
G |  |

| Product.Hierarchy | Иерархия
номенклатур
ы | false | true | true | true | STRIN
G |  |

| Product.MeasureUnit | Единица
измерения | false | true | true | true | STRIN
G |  |

| Product.Name | Элемент
номенклатур
ы | false | true | true | true | STRIN
G |  |

| Product.Num | Артикул
элемента
номенклатур
ы | false | true | true | true | STRIN
G |  |

| Product.SecondParent | Группа
номенклатур
ы2-гоуровня | false | true | true | true | STRIN
G |  |

| Product.ThirdParent | Группа
номенклатур
ы3-гоуровня | false | true | true | true | STRIN
G |  |

| Product.TopParent | Группа
номенклатур | false | true | true | true | STRIN |  |


---


## Page 16

API Documentation Page16 of 30
ы1-гоуровня G
Расшифровки
кодовбазовых
Типэлемента
типов#Тип
Product.Type номенклатур false true true true ENUM
элемента
ы
номенклатуры
STRIN
Session.CashRegister Касса false true true false
G
STRIN
Session.Group Группа false true true false
G
STRIN
Session.RestaurantSection Отделение false true true false
G
Тяжелый
запрос,
Начальный
AMOU рекомендуется
StartBalance.Amount остаток true false false -
NT запускать
товара
тольконочью.
См.выше.
Тяжелый
запрос,
Начальный
MONE рекомендуется
StartBalance.Money денежный true false false -
Y запускать
остаток
тольконочью.
См.выше.
Склад:первый
попавшийся
склад
проводки,
STRIN взятыйиз:
Store Склад false true true false
G левой,правой
части
проводки,
строки
документаили
самого
Allrightsreserved © CompanyInc., 2023


### Table:

|  | ы1-гоуровня |  |  |  |  | G |  |

|---|---|---|---|---|---|---|---|

| Product.Type | Типэлемента
номенклатур
ы | false | true | true | true | ENUM | Расшифровки
кодовбазовых
типов#Тип
элемента
номенклатуры |

| Session.CashRegister | Касса | false | true | true | false | STRIN
G |  |

| Session.Group | Группа | false | true | true | false | STRIN
G |  |

| Session.RestaurantSection | Отделение | false | true | true | false | STRIN
G |  |

| StartBalance.Amount | Начальный
остаток
товара | true | false | false | - | AMOU
NT | Тяжелый
запрос,
рекомендуется
запускать
тольконочью.
См.выше. |

| StartBalance.Money | Начальный
денежный
остаток | true | false | false | - | MONE
Y | Тяжелый
запрос,
рекомендуется
запускать
тольконочью.
См.выше. |

| Store | Склад | false | true | true | false | STRIN
G | Склад:первый
попавшийся
склад
проводки,
взятыйиз:
левой,правой
части
проводки,
строки
документаили
самого |


---


## Page 17

API Documentation Page17 of 30
документа.
Сумма MONE
Sum.Incoming true false false -
прихода Y
Сумма MONE
Sum.Outgoing true false false -
расхода Y
PERCE
Sum.PartOfIncome %отвыручки true false false -
NT
%суммыот
Sum.PartOfSummaryByC PERCE
итогапо true false false -
ol NT
столбцам
%суммыот
Sum.PartOfSummaryByR PERCE
итогапо true false false -
ow NT
строкам
%отобщей PERCE
Sum.PartOfTotalIncome true false false -
выручки NT
MONE
Sum.ResignedSum Сумма true false false -
Y
Расшифровки
кодовбазовых
TransactionSide Дебет/Кредит false true true false ENUM
типов#Дебит/
Кредит
Тип
TransactionType false true true false ENUM
транзакции
TransactionType.Code false true true false
Код OBJEC
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  | документа. |

|---|---|---|---|---|---|---|---|

| Sum.Incoming | Сумма
прихода | true | false | false | - | MONE
Y |  |

| Sum.Outgoing | Сумма
расхода | true | false | false | - | MONE
Y |  |

| Sum.PartOfIncome | %отвыручки | true | false | false | - | PERCE
NT |  |

| Sum.PartOfSummaryByC
ol | %суммыот
итогапо
столбцам | true | false | false | - | PERCE
NT |  |

| Sum.PartOfSummaryByR
ow | %суммыот
итогапо
строкам | true | false | false | - | PERCE
NT |  |

| Sum.PartOfTotalIncome | %отобщей
выручки | true | false | false | - | PERCE
NT |  |

| Sum.ResignedSum | Сумма | true | false | false | - | MONE
Y |  |

| TransactionSide | Дебет/Кредит | false | true | true | false | ENUM | Расшифровки
кодовбазовых
типов#Дебит/
Кредит |

| TransactionType | Тип
транзакции | false | true | true | false | ENUM |  |

| TransactionType.Code | Код | false | true | true | false | OBJEC |  |


---


## Page 18

API Documentation Page18 of 30
транзакции T
*группировкиподате отбрасываютсяпривычисленииначальныхостатков
[+] Описание полейOLAP отчета попродажам
[-] Описание полейOLAP отчета попродажам
Descripti Aggreat Group Filte
Name Description Type Value
onEng ion ing rig
Authorise
AuthUser Авторизовал false true true STRING
dby
TRUE
Banquet Банкет Banquet false true true ENUM
FALSE
Номер Bonus
Bonus.CardNumber бонусной card false true true STRING
карты number
Bonus
Bonus.Sum Суммабонуса true false false MONEY
amount
Bonus
Bonus.Type Типбонуса false true true STRING
type
Карта Authorisa
Card false true true STRING
авторизации tioncard
Номеркарты Paycard
CardNumber false true true STRING
оплаты type
Guest
Владелец
CardOwner cardholde false true true STRING
картыгостя
r
Кредитная Credit
CardType false true true STRING
карта card
Allrightsreserved © CompanyInc., 2023


### Table:

|  | транзакции |  |  |  |  | T |  |

|---|---|---|---|---|---|---|---|



### Table:

| Name | Description | Descripti
onEng | Aggreat
ion | Group
ing | Filte
rig | Type | Value |

|---|---|---|---|---|---|---|---|

| AuthUser | Авторизовал | Authorise
dby | false | true | true | STRING |  |

| Banquet | Банкет | Banquet | false | true | true | ENUM | TRUE
FALSE |

| Bonus.CardNumber | Номер
бонусной
карты | Bonus
card
number | false | true | true | STRING |  |

| Bonus.Sum | Суммабонуса | Bonus
amount | true | false | false | MONEY |  |

| Bonus.Type | Типбонуса | Bonus
type | false | true | true | STRING |  |

| Card | Карта
авторизации | Authorisa
tioncard | false | true | true | STRING |  |

| CardNumber | Номеркарты
оплаты | Paycard
type | false | true | true | STRING |  |

| CardOwner | Владелец
картыгостя | Guest
cardholde
r | false | true | true | STRING |  |

| CardType | Кредитная
карта | Credit
card | false | true | true | STRING |  |


---


## Page 19

API Documentation Page19 of 30
Cashier Кассир Cashier false true true STRING
Cash
Расположени
CashLocation register false true true STRING
екассы
location
Cash
CashRegisterName Касса false true true STRING
register
Время Closing DATETI
CloseTime false true true
закрытия time ME
Комментарий Item
Comment false true true STRING
кблюду comment
Conception Концепция Concept false true true STRING
Место
Productio
CookingPlace приготовлени false true true STRING
nplace
я
Credited
CreditUser Вкредитна... false true true STRING
to...
Dayof
DayOfWeekOpen Деньнедели false true true STRING
week
Расшифров
кикодов
Блюдо Item базовых
DeletedWithWriteoff false true true ENUM
удалено deleted типов#Тип
ыудаления
блюд
Комментарий Item
DeletionComment кудалению deletion false true true STRING
блюда comment
Allrightsreserved © CompanyInc., 2023


### Table:

| Cashier | Кассир | Cashier | false | true | true | STRING |  |

|---|---|---|---|---|---|---|---|

| CashLocation | Расположени
екассы | Cash
register
location | false | true | true | STRING |  |

| CashRegisterName | Касса | Cash
register | false | true | true | STRING |  |

| CloseTime | Время
закрытия | Closing
time | false | true | true | DATETI
ME |  |

| Comment | Комментарий
кблюду | Item
comment | false | true | true | STRING |  |

| Conception | Концепция | Concept | false | true | true | STRING |  |

| CookingPlace | Место
приготовлени
я | Productio
nplace | false | true | true | STRING |  |

| CreditUser | Вкредитна... | Credited
to... | false | true | true | STRING |  |

| DayOfWeekOpen | Деньнедели | Dayof
week | false | true | true | STRING |  |

| DeletedWithWriteoff | Блюдо
удалено | Item
deleted | false | true | true | ENUM | Расшифров
кикодов
базовых
типов#Тип
ыудаления
блюд |

| DeletionComment | Комментарий
кудалению
блюда | Item
deletion
comment | false | true | true | STRING |  |


---


## Page 20

API Documentation Page20 of 30
Расшифров
кикодов
базовых
Delivery.IsDelivery Доставка Delivery false true true ENUM
типов#При
знак
доставки
Торговое
Department Outlet false true true STRING
предприятие
Процент Discount PERCE
DiscountPercent true true true
скидки rate NT
Сумма Discount
DiscountSum true false true MONEY
скидки amount
Discount
Сумма amount
скидкибез excl.VAT
discountWithoutVAT НДСне not true false true MONEY
включенного included
встоимость inthe
cost
Количество Number AMOU
DishAmountInt true true true
блюд ofitems NT
Категория Item
DishCategory false true true STRING
блюда category
DishCode Кодблюда Itemcode false true true STRING
Item
Кодбыстрого
DishCode.Quick quick false true true STRING
набораблюда
code
Amount
Суммасо
DishDiscountSumInt with true false false MONEY
скидкой
discount
Allrightsreserved © CompanyInc., 2023


### Table:

| Delivery.IsDelivery | Доставка | Delivery | false | true | true | ENUM | Расшифров
кикодов
базовых
типов#При
знак
доставки |

|---|---|---|---|---|---|---|---|

| Department | Торговое
предприятие | Outlet | false | true | true | STRING |  |

| DiscountPercent | Процент
скидки | Discount
rate | true | true | true | PERCE
NT |  |

| DiscountSum | Сумма
скидки | Discount
amount | true | false | true | MONEY |  |

| discountWithoutVAT | Сумма
скидкибез
НДСне
включенного
встоимость | Discount
amount
excl.VAT
not
included
inthe
cost | true | false | true | MONEY |  |

| DishAmountInt | Количество
блюд | Number
ofitems | true | true | true | AMOU
NT |  |

| DishCategory | Категория
блюда | Item
category | false | true | true | STRING |  |

| DishCode | Кодблюда | Itemcode | false | true | true | STRING |  |

| DishCode.Quick | Кодбыстрого
набораблюда | Item
quick
code | false | true | true | STRING |  |

| DishDiscountSumInt | Суммасо
скидкой | Amount
with
discount | true | false | false | MONEY |  |


---


## Page 21

API Documentation Page21 of 30
Average
Средняя
DishDiscountSumInt.average bill true false false MONEY
суммазаказа
amount
Средняя Average
DishDiscountSumInt.averageByGues
выручкас revenue true false false MONEY
t
гостя perguest
Average
price
Средняяцена
DishDiscountSumInt.averagePrice (VAT true false false MONEY
безНДС
exclusive
)
Amount
Суммасо with
DishDiscountSumInt.withoutVAT скидкойбез discount true false false MONEY
НДС VAT
exclusive
Наименовани Item
еблюдана nameina
DishForeignName false true true STRING
иностранном foreign
языке language
Полное Fullname
DishFullName наименование ofthe false true true STRING
блюда item
Item
DishGroup Группаблюда false true true STRING
group
Иерархия Item
DishGroup.Hierarchy false true true STRING
блюда hierarchy
Item
Кодгруппы
DishGroup.Num group false true true STRING
блюда
code
Level2
Группаблюда
DishGroup.SecondParent item false true true STRING
2-гоуровня
group
Allrightsreserved © CompanyInc., 2023


### Table:

| DishDiscountSumInt.average | Средняя
суммазаказа | Average
bill
amount | true | false | false | MONEY |  |

|---|---|---|---|---|---|---|---|

| DishDiscountSumInt.averageByGues
t | Средняя
выручкас
гостя | Average
revenue
perguest | true | false | false | MONEY |  |

| DishDiscountSumInt.averagePrice | Средняяцена
безНДС | Average
price
(VAT
exclusive
) | true | false | false | MONEY |  |

| DishDiscountSumInt.withoutVAT | Суммасо
скидкойбез
НДС | Amount
with
discount
VAT
exclusive | true | false | false | MONEY |  |

| DishForeignName | Наименовани
еблюдана
иностранном
языке | Item
nameina
foreign
language | false | true | true | STRING |  |

| DishFullName | Полное
наименование
блюда | Fullname
ofthe
item | false | true | true | STRING |  |

| DishGroup | Группаблюда | Item
group | false | true | true | STRING |  |

| DishGroup.Hierarchy | Иерархия
блюда | Item
hierarchy | false | true | true | STRING |  |

| DishGroup.Num | Кодгруппы
блюда | Item
group
code | false | true | true | STRING |  |

| DishGroup.SecondParent | Группаблюда
2-гоуровня | Level2
item
group | false | true | true | STRING |  |


---


## Page 22

API Documentation Page22 of 30
Level3
Группаблюда
DishGroup.ThirdParent item false true true STRING
3-гоуровня
group
Level1
Группаблюда
DishGroup.TopParent item false true true STRING
1-гоуровня
group
Единица Measure
DishMeasureUnit false true true STRING
измерения mentunit
DishName Блюдо Item false true true STRING
Сумма Void
DishReturnSum true true true MONEY
возврата amount
Service
Сервисная DATETI
DishServicePrintTime printing false true true
печатьблюда ME
item
Сервисная Service
печать printing DATETI
DishServicePrintTime.Max true false false
последнего latest ME
блюда item
Duration:
Длит:откр.- open
DishServicePrintTime.OpenToLastPr INTEGE
посл.серв.печ latest true false false
intDuration R
ать serv.
print.
Amount
Суммабез
DishSumInt without true false false MONEY
скидки
discount
Расшифров
кикодов
Stocklist
DishType Типтовара false true true ENUM базовых
type
типов#Тип
товара
Allrightsreserved © CompanyInc., 2023


### Table:

| DishGroup.ThirdParent | Группаблюда
3-гоуровня | Level3
item
group | false | true | true | STRING |  |

|---|---|---|---|---|---|---|---|

| DishGroup.TopParent | Группаблюда
1-гоуровня | Level1
item
group | false | true | true | STRING |  |

| DishMeasureUnit | Единица
измерения | Measure
mentunit | false | true | true | STRING |  |

| DishName | Блюдо | Item | false | true | true | STRING |  |

| DishReturnSum | Сумма
возврата | Void
amount | true | true | true | MONEY |  |

| DishServicePrintTime | Сервисная
печатьблюда | Service
printing
item | false | true | true | DATETI
ME |  |

| DishServicePrintTime.Max | Сервисная
печать
последнего
блюда | Service
printing
latest
item | true | false | false | DATETI
ME |  |

| DishServicePrintTime.OpenToLastPr
intDuration | Длит:откр.-
посл.серв.печ
ать | Duration:
open
latest
serv.
print. | true | false | false | INTEGE
R |  |

| DishSumInt | Суммабез
скидки | Amount
without
discount | true | false | false | MONEY |  |

| DishType | Типтовара | Stocklist
type | false | true | true | ENUM | Расшифров
кикодов
базовых
типов#Тип
товара |


---


## Page 23

API Documentation Page23 of 30
Amount
Суммабез excl.VAT
НДСне not
fullSum true false true MONEY
включенного included
встоимость inthe
cost
Количество Number AMOU
GuestNum true true true
гостей ofguests NT
AvgNum
Ср.кол-во berof AMOU
GuestNum.Avg true false false
гостейначек guestsper NT
receipt
Closing
HourClose Часзакрытия false true true STRING
hour
Opening
HourOpen Часоткрытия false true true STRING
hour
Мотивационн Incentive
IncentiveSumBase.Sum true false false MONEY
ыйбонус payment
Процент Surcharge PERCE
IncreasePercent true true true
надбавки rate NT
Сумма Surcharge
IncreaseSum true true true MONEY
надбавки amount
Юридическое Legal
JurName false true true STRING
лицо entity
Mounth Месяц Month false true true STRING
Non-cash
Безналичный
NonCashPaymentType payment false true true STRING
типоплаты
type
NonCashPaymentType.DocumentTyp Тип Documen false true true ENUM Расшифров
Allrightsreserved © CompanyInc., 2023


### Table:

| fullSum | Суммабез
НДСне
включенного
встоимость | Amount
excl.VAT
not
included
inthe
cost | true | false | true | MONEY |  |

|---|---|---|---|---|---|---|---|

| GuestNum | Количество
гостей | Number
ofguests | true | true | true | AMOU
NT |  |

| GuestNum.Avg | Ср.кол-во
гостейначек | AvgNum
berof
guestsper
receipt | true | false | false | AMOU
NT |  |

| HourClose | Часзакрытия | Closing
hour | false | true | true | STRING |  |

| HourOpen | Часоткрытия | Opening
hour | false | true | true | STRING |  |

| IncentiveSumBase.Sum | Мотивационн
ыйбонус | Incentive
payment | true | false | false | MONEY |  |

| IncreasePercent | Процент
надбавки | Surcharge
rate | true | true | true | PERCE
NT |  |

| IncreaseSum | Сумма
надбавки | Surcharge
amount | true | true | true | MONEY |  |

| JurName | Юридическое
лицо | Legal
entity | false | true | true | STRING |  |

| Mounth | Месяц | Month | false | true | true | STRING |  |

| NonCashPaymentType | Безналичный
типоплаты | Non-cash
payment
type | false | true | true | STRING |  |

| NonCashPaymentType.DocumentTyp | Тип | Documen | false | true | true | ENUM | Расшифров |


---


## Page 24

API Documentation Page24 of 30
e документа ttype кикодов
базовых
типов#Тип
документа
OpenDate(доверсии4.2;в4.2+
deprecated,замененона Учетныйдень false true true STRING
OpenDate.Typed)
OpenDate.Typed(4.2+) Учетныйдень false true true DATE
Время Opening DATETI
OpenTime false true true
открытия time ME
Расшифров
кикодов
OperationType Операция Operation false true true ENUM базовых
типов#Тип
операции
Расшифров
кикодов
базовых
Order
OrderDeleted Заказудален false true true ENUM типов#При
deleted
знак
удаления
заказа
Гостевая Guest
OrderDiscount.GuestCard false true true STRING
карта card
Discount
OrderDiscount.Type Типскидки false true true STRING
type
Typeof
OrderIncrease.Type Типнадбавки false true true STRING
surcharge
Order INTEGE
OrderItems Позицийчека true false false
items R
Allrightsreserved © CompanyInc., 2023


### Table:

| e | документа | ttype |  |  |  |  | кикодов
базовых
типов#Тип
документа |

|---|---|---|---|---|---|---|---|

| OpenDate(доверсии4.2;в4.2+
deprecated,замененона
OpenDate.Typed) | Учетныйдень |  | false | true | true | STRING |  |

| OpenDate.Typed(4.2+) | Учетныйдень |  | false | true | true | DATE |  |

| OpenTime | Время
открытия | Opening
time | false | true | true | DATETI
ME |  |

| OperationType | Операция | Operation | false | true | true | ENUM | Расшифров
кикодов
базовых
типов#Тип
операции |

| OrderDeleted | Заказудален | Order
deleted | false | true | true | ENUM | Расшифров
кикодов
базовых
типов#При
знак
удаления
заказа |

| OrderDiscount.GuestCard | Гостевая
карта | Guest
card | false | true | true | STRING |  |

| OrderDiscount.Type | Типскидки | Discount
type | false | true | true | STRING |  |

| OrderIncrease.Type | Типнадбавки | Typeof
surcharge | false | true | true | STRING |  |

| OrderItems | Позицийчека | Order
items | true | false | false | INTEGE
R |  |


---


## Page 25

API Documentation Page25 of 30
Receipt INTEGE
OrderNum Номерчека true true true
number R
AvgServi
Ср.время AMOU
OrderTime.AverageOrderTime ngtime true false false
обсл.(мин) NT
(min)
Avgtime
Ср.времяв AMOU
OrderTime.AveragePrechequeTime inguest true false false
пречеке(мин) NT
bill(min)
Время Serving
INTEGE
OrderTime.OrderLength обслуживани time false true true
R
я(мин) (min)
Время Serving
INTEGE
OrderTime.OrderLengthSum обсл.сумм.(м time true false false
R
ин) (min)
Timein
Времяв INTEGE
OrderTime.PrechequeLength guestbill false true true
пречеке(мин) R
(min)
Order
OrderType Типзаказа false true true STRING
type
Официант Waiterfor
OrderWaiter.Name false true true STRING
заказа theorder
Источник Order
OriginName false true true STRING
заказа origin
Payment
PayTypes Типоплаты false true true STRING
type
Payment
Типоплаты
PayTypes.Combo type false true true STRING
(комб.)
(comb.)
Allrightsreserved © CompanyInc., 2023


### Table:

| OrderNum | Номерчека | Receipt
number | true | true | true | INTEGE
R |  |

|---|---|---|---|---|---|---|---|

| OrderTime.AverageOrderTime | Ср.время
обсл.(мин) | AvgServi
ngtime
(min) | true | false | false | AMOU
NT |  |

| OrderTime.AveragePrechequeTime | Ср.времяв
пречеке(мин) | Avgtime
inguest
bill(min) | true | false | false | AMOU
NT |  |

| OrderTime.OrderLength | Время
обслуживани
я(мин) | Serving
time
(min) | false | true | true | INTEGE
R |  |

| OrderTime.OrderLengthSum | Время
обсл.сумм.(м
ин) | Serving
time
(min) | true | false | false | INTEGE
R |  |

| OrderTime.PrechequeLength | Времяв
пречеке(мин) | Timein
guestbill
(min) | false | true | true | INTEGE
R |  |

| OrderType | Типзаказа | Order
type | false | true | true | STRING |  |

| OrderWaiter.Name | Официант
заказа | Waiterfor
theorder | false | true | true | STRING |  |

| OriginName | Источник
заказа | Order
origin | false | true | true | STRING |  |

| PayTypes | Типоплаты | Payment
type | false | true | true | STRING |  |

| PayTypes.Combo | Типоплаты
(комб.) | Payment
type
(comb.) | false | true | true | STRING |  |


---


## Page 26

API Documentation Page26 of 30
Расшифров
кикодов
Группа Payment
PayTypes.Group false true true ENUM базовых
оплаты group
типов#Гру
ппаоплаты
Расшифров
кикодов
Fisc. базовых
Фиск.тип
PayTypes.IsPrintCheque payment false true true ENUM типов#При
оплаты
type знак
фискально
стиоплаты
Number
Количество INTEGE
PayTypes.VoucherNum of true false false
ваучеров R
vouchers
%by PERCE
PercentOfSummary.ByCol %постолбцу true false false
column NT
PERCE
PercentOfSummary.ByRow %построке %byrow true false false
NT
Время Guestbill DATETI
PrechequeTime false true true
пречека time ME
Ценовая Customer
PriceCategory категория price false true true STRING
клиента category
Price
ЦКномер Category
PriceCategoryCard false true true STRING
карты Card
Number
Price
ЦКвладелец Category
PriceCategoryDiscountCardOwner false true true STRING
карты Cardhold
er
Allrightsreserved © CompanyInc., 2023


### Table:

| PayTypes.Group | Группа
оплаты | Payment
group | false | true | true | ENUM | Расшифров
кикодов
базовых
типов#Гру
ппаоплаты |

|---|---|---|---|---|---|---|---|

| PayTypes.IsPrintCheque | Фиск.тип
оплаты | Fisc.
payment
type | false | true | true | ENUM | Расшифров
кикодов
базовых
типов#При
знак
фискально
стиоплаты |

| PayTypes.VoucherNum | Количество
ваучеров | Number
of
vouchers | true | false | false | INTEGE
R |  |

| PercentOfSummary.ByCol | %постолбцу | %by
column | true | false | false | PERCE
NT |  |

| PercentOfSummary.ByRow | %построке | %byrow | true | false | false | PERCE
NT |  |

| PrechequeTime | Время
пречека | Guestbill
time | false | true | true | DATETI
ME |  |

| PriceCategory | Ценовая
категория
клиента | Customer
price
category | false | true | true | STRING |  |

| PriceCategoryCard | ЦКномер
карты | Price
Category
Card
Number | false | true | true | STRING |  |

| PriceCategoryDiscountCardOwner | ЦКвладелец
карты | Price
Category
Cardhold
er | false | true | true | STRING |  |


---


## Page 27

API Documentation Page27 of 30
Price
ЦК Category
PriceCategoryUserCardOwner false true true STRING
контрагент Card
Owner
Markup PERCE
ProductCostBase.MarkUp Наценка(%) true false false
(%) NT
Себестоимост Costper
ProductCostBase.OneItem true false false MONEY
ьединицы unit
Себестоимост PERCE
ProductCostBase.Percent Cost(%) true false false
ь(%) NT
Себестоимост
ProductCostBase.ProductCost Cost true false false MONEY
ь
ProductCostBase.Profit Наценка Markup true false false MONEY
Причина Reason
RemovalType удаления foritem false true true STRING
блюда deletion
RestaurantSection Отделение Room false true true STRING
RestorauntGroup Группа Group false true true STRING
Shift INTEGE
SessionNum Номерсмены false true true
number R
Проданос Soldwith
SoldWithDish false true true STRING
блюдом item
Allrightsreserved © CompanyInc., 2023


### Table:

| PriceCategoryUserCardOwner | ЦК
контрагент | Price
Category
Card
Owner | false | true | true | STRING |  |

|---|---|---|---|---|---|---|---|

| ProductCostBase.MarkUp | Наценка(%) | Markup
(%) | true | false | false | PERCE
NT |  |

| ProductCostBase.OneItem | Себестоимост
ьединицы | Costper
unit | true | false | false | MONEY |  |

| ProductCostBase.Percent | Себестоимост
ь(%) | Cost(%) | true | false | false | PERCE
NT |  |

| ProductCostBase.ProductCost | Себестоимост
ь | Cost | true | false | false | MONEY |  |

| ProductCostBase.Profit | Наценка | Markup | true | false | false | MONEY |  |

| RemovalType | Причина
удаления
блюда | Reason
foritem
deletion | false | true | true | STRING |  |

| RestaurantSection | Отделение | Room | false | true | true | STRING |  |

| RestorauntGroup | Группа | Group | false | true | true | STRING |  |

| SessionNum | Номерсмены | Shift
number | false | true | true | INTEGE
R |  |

| SoldWithDish | Проданос
блюдом | Soldwith
item | false | true | true | STRING |  |


---


## Page 28

API Documentation Page28 of 30
From
Store.Name Сосклада false true true STRING
storage
To
StoreTo Насклад false true true STRING
storage
Void TRUE
Storned Возвратчека false true true ENUM
receipt FALSE
Amount
with
Суммасо
discount
скидкойбез
excl.VAT
sumAfterDiscountWithoutVAT НДСне true false true MONEY
not
включенного
included
встоимость
inthe
cost
TableNumInt(до5.1;в5.1+
Номерстола false true true STRING
замененонаTableNum)
INTEGE
TableNum(5.1+) Номерстола false true true
R
INTEGE
UniqOrderId Чеков Orders true false false
R
AMOU
UniqOrderId.OrdersCount Заказов Orders true false false
NT
PERCE
VAT.Percent НДС(%) VAT(%) true true true
NT
VATby
НДСпо
VAT.Sum bill true true true MONEY
чекам(Сумма)
(Amount)
Официант Item
WaiterName false true true STRING
блюда waiter
Allrightsreserved © CompanyInc., 2023


### Table:

| Store.Name | Сосклада | From
storage | false | true | true | STRING |  |

|---|---|---|---|---|---|---|---|

| StoreTo | Насклад | To
storage | false | true | true | STRING |  |

| Storned | Возвратчека | Void
receipt | false | true | true | ENUM | TRUE
FALSE |

| sumAfterDiscountWithoutVAT | Суммасо
скидкойбез
НДСне
включенного
встоимость | Amount
with
discount
excl.VAT
not
included
inthe
cost | true | false | true | MONEY |  |

| TableNumInt(до5.1;в5.1+
замененонаTableNum) | Номерстола |  | false | true | true | STRING |  |

| TableNum(5.1+) | Номерстола |  | false | true | true | INTEGE
R |  |

| UniqOrderId | Чеков | Orders | true | false | false | INTEGE
R |  |

| UniqOrderId.OrdersCount | Заказов | Orders | true | false | false | AMOU
NT |  |

| VAT.Percent | НДС(%) | VAT(%) | true | true | true | PERCE
NT |  |

| VAT.Sum | НДСпо
чекам(Сумма) | VATby
bill
(Amount) | true | true | true | MONEY |  |

| WaiterName | Официант
блюда | Item
waiter | false | true | true | STRING |  |


---


## Page 29

API Documentation Page29 of 30
Причина Write-off
WriteoffReason false true true STRING
списания reason
Written
Списанона
WriteoffUser offto false true true STRING
сотрудника
employee
YearOpen Год Year false true true STRING
[+] Описание полейOLAP отчета поконтролюхранения
[-] Описание полейOLAP отчета поконтролюхранения
Name Description Aggreation Grouping Type Value
ProductNum Артикул false true STRING
ProductName Блюдо false true STRING
ProductAccountingCategory Бухгалтерская
категория false true STRING
блюда
EventDate Дата false true DATETIME
Датаивремя
EventCookingDate false true DATETIME
приготовления
STRING
Единицы
ProductMeasureUnit false true
измерения
Категория
ProductCategory false true STRING
блюда
Код
Department.Code false true STRING
подразделения
Amount Количество false true AMOUNT
Просрочкана
ProductExpirationDuration момент true false DATETIME
продажи
Allrightsreserved © CompanyInc., 2023


### Table:

| WriteoffReason | Причина
списания | Write-off
reason | false | true | true | STRING |  |

|---|---|---|---|---|---|---|---|

| WriteoffUser | Списанона
сотрудника | Written
offto
employee | false | true | true | STRING |  |

| YearOpen | Год | Year | false | true | true | STRING |  |



### Table:

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

|  | Name |  |  | Description |  |  | Aggreation |  |  | Grouping |  |  | Type |  |  | Value |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| ProductNum |  |  | Артикул |  |  | false |  |  | true |  |  | STRING |  |  |  |  |  |

| ProductName |  |  | Блюдо |  |  | false |  |  | true |  |  | STRING |  |  |  |  |  |

| ProductAccountingCategory |  |  | Бухгалтерская
категория
блюда |  |  | false |  |  | true |  |  | STRING |  |  |  |  |  |

| EventDate |  |  | Дата |  |  | false |  |  | true |  |  | DATETIME |  |  |  |  |  |

| EventCookingDate |  |  | Датаивремя
приготовления |  |  | false |  |  | true |  |  | DATETIME |  |  |  |  |  |

| ProductMeasureUnit |  |  | Единицы
измерения |  |  | false |  |  | true |  |  | STRING |  |  |  |  |  |

| ProductCategory |  |  | Категория
блюда |  |  | false |  |  | true |  |  | STRING |  |  |  |  |  |

| Department.Code |  |  | Код
подразделения |  |  | false |  |  | true |  |  | STRING |  |  |  |  |  |

| Amount |  |  | Количество |  |  | false |  |  | true |  |  | AMOUNT |  |  |  |  |  |

| ProductExpirationDuration |  |  | Просрочкана
момент
продажи |  |  | true |  |  | false |  |  | DATETIME |  |  |  |  |  |


---


## Page 30

API Documentation Page30 of 30
Name Description Aggreation Grouping Type Value
MONEY
Себестоимость
ProductCostBase.OneItem true false
единицы,р.
MONEY
Себестоимость,
ProductCostBase.ProductCost true false
р.
StoreFrom Склад false true STRING
User Сотрудник false true STRING
AccountTo Счет false true STRING
Event.Type Типсобытия false true STRING
Торговое
Department false true STRING
предприятие
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

|  | Name |  |  | Description |  |  | Aggreation |  |  | Grouping |  |  | Type |  |  | Value |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| ProductCostBase.OneItem |  |  | Себестоимость
единицы,р. |  |  | true |  |  | false |  |  | MONEY |  |  |  |  |  |

| ProductCostBase.ProductCost |  |  | Себестоимость,
р. |  |  | true |  |  | false |  |  | MONEY |  |  |  |  |  |

| StoreFrom |  |  | Склад |  |  | false |  |  | true |  |  | STRING |  |  |  |  |  |

| User |  |  | Сотрудник |  |  | false |  |  | true |  |  | STRING |  |  |  |  |  |

| AccountTo |  |  | Счет |  |  | false |  |  | true |  |  | STRING |  |  |  |  |  |

| Event.Type |  |  | Типсобытия |  |  | false |  |  | true |  |  | STRING |  |  |  |  |  |

| Department |  |  | Торговое
предприятие |  |  | false |  |  | true |  |  | STRING |  |  |  |  |  |


---
