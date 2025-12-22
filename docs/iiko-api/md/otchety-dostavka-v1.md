# Otchety Dostavka V1

*Generated from PDF: otchety-dostavka-v1.pdf*

*Total pages: 9*

---


## Page 1

API Documentation Page1 of 9
1. Отчеты по доставке
Отчеты по доставке
Сводный отчет
https://host:port/resto/api/reports/delivery/consolidated
Параметры запроса
Параметры Описание
department Подразделения(КодилиИД)(department={code="005"}).Еслинеуказан,
отчетбудетпостроендлявсехподразделений(Чейн)
dateFrom Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD)
dateTo Датаокончанияотчета
writeoffAccounts Списоксчетовсписания(кодилиИД)
Что в ответе
CopyCode
JSON
<report>
<rows>
<row>
<!--средний чек-->
<avgReceipt>486.25</avgReceipt>
<!--дата-->
<date>01.04.2014</date>
<!--кол-во блюд-->
<dishAmount>468.00</dishAmount>
<!--кол-во блюд в чеке-->
<dishAmountPerOrder>2.23</dishAmountPerOrder>
<!--кол- во заказов-->
<orderCount>210.00</orderCount>
<!--заказов "курьер"-->
<orderCountCourier>65.00</orderCountCourier>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  |  |  | Описание |

|---|---|---|---|---|---|---|---|---|---|

|  |  | Параметры |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  | Подразделения(КодилиИД)(department={code="005"}).Еслинеуказан,
отчетбудетпостроендлявсехподразделений(Чейн) |

|  |  | department |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  | Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD) |

|  |  |  | dateFrom |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  | Датаокончанияотчета |

|  |  |  |  | dateTo |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  | Списоксчетовсписания(кодилиИД) |

|  | writeoffAccounts |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | <report> |  |

|  | <rows> |  |

|  | <row> |  |

|  | <!--средний чек--> |  |

|  | <avgReceipt>486.25</avgReceipt> |  |

|  | <!--дата--> |  |

|  | <date>01.04.2014</date> |  |

|  | <!--кол-во блюд--> |  |

|  | <dishAmount>468.00</dishAmount> |  |

|  | <!--кол-во блюд в чеке--> |  |

|  | <dishAmountPerOrder>2.23</dishAmountPerOrder> |  |

|  | <!--кол- во заказов--> |  |

|  | <orderCount>210.00</orderCount> |  |

|  | <!--заказов "курьер"--> |  |

|  | <orderCountCourier>65.00</orderCountCourier> |  |


---


## Page 2

API Documentation Page2 of 9
<!--заказов "с собой"-->
<orderCountPickup>145.00</orderCountPickup>
<!--% выполнения бюджета-->
<planExecutionPercent>91.00</planExecutionPercent>
<!--% списания-->
<ratioCostWriteoff>22.10</ratioCostWriteoff>
<!--выручка--><revenue>102113.00</revenue>
</row>
</rows>
</report>
Пример вызова
https://localhost:9080/resto/api/reports/delivery/consolidated?de
partment={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&writeof
fAccounts={code="5.14"}&writeoffAccounts={code="5.13"}&key=cd8cf2
c7-a0a2-8b82-b29a-f4f9bf74e5c2
Отчет по курьерам
https://host:port/resto/api/reports/delivery/couriers
Параметры запроса
Параметры Описание
department Подразделения(КодилиИД)(department={code="005"}).Еслинеуказан,
отчетбудетпостроендлявсехподразделений(Чейн)
dateFrom Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD)
dateTo Датаокончанияотчета
targetCommonTime Целевоезначениеобщеговремени,мин.(поумолчанию-30мин.)
targetOnTheWayTime Целевоезначениевременивпути,мин. (поумолчанию-0мин.)
targetDoubledOrders Целевоеколичествосдвоенныхзаказовзадень,шт. (поумолчанию-0
мин.)
targetTripledOrders Целевоеколичествостроенныхзаказовзадень,шт. (поумолчанию-0
мин.)
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <!--заказов "с собой"--> |

|  | <orderCountPickup>145.00</orderCountPickup> |

|  | <!--% выполнения бюджета--> |

|  | <planExecutionPercent>91.00</planExecutionPercent> |

|  | <!--% списания--> |

|  | <ratioCostWriteoff>22.10</ratioCostWriteoff> |

|  | <!--выручка--><revenue>102113.00</revenue> |

|  | </row> |

|  | </rows> |

|  | </report> |

|  |  |



### Table:

| https://localhost:9080/resto/api/reports/delivery/consolidated?de |  |

|---|---|

| partment={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&writeof |  |

| fAccounts={code="5.14"}&writeoffAccounts={code="5.13"}&key=cd8cf2 |  |

| c7-a0a2-8b82-b29a-f4f9bf74e5c2 |  |



### Table:

|  |  |  |  |  |  |  |  |  |  |  | Описание |

|---|---|---|---|---|---|---|---|---|---|---|---|

|  |  |  | Параметры |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  | Подразделения(КодилиИД)(department={code="005"}).Еслинеуказан,
отчетбудетпостроендлявсехподразделений(Чейн) |

|  |  |  | department |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  | Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD) |

|  |  |  |  | dateFrom |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  | Датаокончанияотчета |

|  |  |  |  |  | dateTo |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  | Целевоезначениеобщеговремени,мин.(поумолчанию-30мин.) |

|  |  | targetCommonTime |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  | Целевоезначениевременивпути,мин. (поумолчанию-0мин.) |

|  | targetOnTheWayTime |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  | Целевоеколичествосдвоенныхзаказовзадень,шт. (поумолчанию-0
мин.) |

|  | targetDoubledOrders |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  | Целевоеколичествостроенныхзаказовзадень,шт. (поумолчанию-0
мин.) |

|  |  | targetTripledOrders |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |


---


## Page 3

API Documentation Page3 of 9
Параметры Описание
targetTotalOrders Целевоеколичествозаказовзадень,шт (поумолчанию-0мин.)
Что в ответе
CopyCode
JSON
<report>
<rows>
<row>
<!--курьер–>
<courier>Елена</courier>
<metrics><metric>
<!--сдвоенные заказы-->
<doubledOrders>0.00</doubledOrders>
<!--тип метрики (AVERAGE - среднее,TARGET - отношение к целевым
показателям,MAXIMUM - максимальное значение)-->
<metricType>AVERAGE</metricType>
<!--время в пути-->
<onTheWayTime>0.00</onTheWayTime>
<!--кол-во заказов-->
<orderCount>1.00</orderCount>
<!--общее время-->
<totalTime>34.00</totalTime>
<!--строенные заказы-->
<tripledOrders>0.00</tripledOrders>
</metric>
<metric>
<doubledOrders>100.00</doubledOrders>
<metricType>TARGET</metricType>
<onTheWayTime>100.00</onTheWayTime>
<orderCount>0.00</orderCount>
<totalTime>0.00</totalTime>
<tripledOrders>100.00</tripledOrders>
</metric>
<metric>
<doubledOrders>0.00</doubledOrders>
<metricType>MAXIMUM</metricType>
<onTheWayTime>0.00</onTheWayTime>
<orderCount>1.00</orderCount>
<totalTime>34.00</totalTime>
<tripledOrders>0.00</tripledOrders>
</metric>
</metrics>
</row>
<report>
Пример вызова
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  | Описание |

|---|---|---|---|---|---|

|  |  | Параметры |  |  |  |

|  |  |  |  |  |  |

|  |  |  |  |  | Целевоеколичествозаказовзадень,шт (поумолчанию-0мин.) |

|  | targetTotalOrders |  |  |  |  |

|  |  |  |  |  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | <report> |  |

|  | <rows> |  |

|  | <row> |  |

|  | <!--курьер–> |  |

|  | <courier>Елена</courier> |  |

|  | <metrics><metric> |  |

|  | <!--сдвоенные заказы--> |  |

|  | <doubledOrders>0.00</doubledOrders> |  |

|  | <!--тип метрики (AVERAGE - среднее,TARGET - отношение к целевым |  |

|  | показателям,MAXIMUM - максимальное значение)--> |  |

|  | <metricType>AVERAGE</metricType> |  |

|  | <!--время в пути--> |  |

|  | <onTheWayTime>0.00</onTheWayTime> |  |

|  | <!--кол-во заказов--> |  |

|  | <orderCount>1.00</orderCount> |  |

|  | <!--общее время--> |  |

|  | <totalTime>34.00</totalTime> |  |

|  | <!--строенные заказы--> |  |

|  | <tripledOrders>0.00</tripledOrders> |  |

|  | </metric> |  |

|  | <metric> |  |

|  | <doubledOrders>100.00</doubledOrders> |  |

|  | <metricType>TARGET</metricType> |  |

|  | <onTheWayTime>100.00</onTheWayTime> |  |

|  | <orderCount>0.00</orderCount> |  |

|  | <totalTime>0.00</totalTime> |  |

|  | <tripledOrders>100.00</tripledOrders> |  |

|  | </metric> |  |

|  | <metric> |  |

|  | <doubledOrders>0.00</doubledOrders> |  |

|  | <metricType>MAXIMUM</metricType> |  |

|  | <onTheWayTime>0.00</onTheWayTime> |  |

|  | <orderCount>1.00</orderCount> |  |

|  | <totalTime>34.00</totalTime> |  |

|  | <tripledOrders>0.00</tripledOrders> |  |

|  | </metric> |  |

|  | </metrics> |  |

|  | </row> |  |

|  | <report> |  |

|  |  |  |


---


## Page 4

API Documentation Page4 of 9
https://localhost:9080/resto/api/reports/delivery/couriers?depart
ment={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&targetCommo
nTime=5&targetOnTheWayTime=6&targetDoubledOrders=7&targetTripledO
rders=8&targetTotalOrders=9&key=d34ab6bd-1515-f22e-d02d-
92d2a682a512
Цикл заказа
https://host:port/resto/api/reports/delivery/orderCycle
Параметры запроса
Параметры Описание
department Подразделения(КодилиИД)(department={code="005"}).Еслине
указан,отчетбудетпостроендлявсехподразделений(Чейн)
dateFrom Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD)
dateTo Датаокончанияотчета
targetPizzaTime ЦелевоезначениевременинастолеПицца (поумолчанию-0мин.)
targetCuttingTime Целевоезначениевременинастоленарезки (поумолчанию-0мин.)
targetOnShelfTime Целевоезначениевременинастеллажеоперативности (по
умолчанию-0мин.)
targetInRestaurantTime Целевоезначениевременивресторане (поумолчанию-0мин.)
targetOnTheWayTime Целевоезначениевременивпути (поумолчанию-0мин.)
targetTotalTime Целевоезначениеобщеговременидоставки (поумолчанию-0мин.)
Что в ответе
CopyCode
JSON
<report>
<rows>
<row>
Allrightsreserved © CompanyInc., 2023


### Table:

|  |

|---|

| https://localhost:9080/resto/api/reports/delivery/couriers?depart
ment={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&targetCommo
nTime=5&targetOnTheWayTime=6&targetDoubledOrders=7&targetTripledO
rders=8&targetTotalOrders=9&key=d34ab6bd-1515-f22e-d02d-
92d2a682a512 |

|  |



### Table:

| https://localhost:9080/resto/api/reports/delivery/couriers?depart |

|---|

| ment={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&targetCommo |

| nTime=5&targetOnTheWayTime=6&targetDoubledOrders=7&targetTripledO |



### Table:

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | Описание |

|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

|  |  |  |  |  | Параметры |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | Подразделения(КодилиИД)(department={code="005"}).Еслине
указан,отчетбудетпостроендлявсехподразделений(Чейн) |

|  |  |  |  |  | department |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD) |

|  |  |  |  |  |  | dateFrom |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | Датаокончанияотчета |

|  |  |  |  |  |  |  | dateTo |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ЦелевоезначениевременинастолеПицца (поумолчанию-0мин.) |

|  |  |  |  | targetPizzaTime |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | Целевоезначениевременинастоленарезки (поумолчанию-0мин.) |

|  |  |  | targetCuttingTime |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | Целевоезначениевременинастеллажеоперативности (по
умолчанию-0мин.) |

|  |  |  | targetOnShelfTime |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | Целевоезначениевременивресторане (поумолчанию-0мин.) |

|  | targetInRestaurantTime |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | Целевоезначениевременивпути (поумолчанию-0мин.) |

|  |  | targetOnTheWayTime |  |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | Целевоезначениеобщеговременидоставки (поумолчанию-0мин.) |

|  |  |  |  | targetTotalTime |  |  |  |  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | <report> |  |

|  | <rows> |  |

|  | <row> |  |


---


## Page 5

API Documentation Page5 of 9
<!--время на столе нарезки-->
<cuttingTime>0.00</cuttingTime>
<!--время в ресторане-->
<inRestaurantTime>15.90</inRestaurantTime>
<!--время на стеллаже оперативности-->
<onShelfTime>3.72</onShelfTime>
<!--время в пути-->
<onTheWayTime>8.22</onTheWayTime>
<!--время на столе Пицца-->
<pizzaTime>0.00</pizzaTime>
<!--общее время-->
<totalTime>26.61</totalTime>
<!--тип метрики (AVERAGE - среднее, TARGET - отношение к целевым
показателям, MAXIMUM - максимальное значение)-->
<metricType>AVERAGE</metricType>
</row>
</rows>
</report>
Пример вызова
https://localhost:9080/resto/api/reports/delivery/orderCycle?depa
rtment={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&targetPiz
zaTime=5&targetCuttingTime=6&targetOnShelfTime=7&targetInRestaura
ntTime=8&targetOnTheWayTime=9&targetTotalTime=10&key=a113485b-
d4f1-0856-8faf-50ba913f04eb
Получасовой детальный отчет
https://host:port/resto/api/reports/delivery/halfHourDetailed
Параметры запроса
Параметры Описание
department Подразделения(КодилиИД)(department={code="005"}).Еслинеуказан,отчет
будетпостроендлявсехподразделений(Чейн)
dateFrom Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD)
dateTo Датаокончанияотчета
Что в ответе
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |

|---|---|

|  | <!--время на столе нарезки--> |

|  | <cuttingTime>0.00</cuttingTime> |

|  | <!--время в ресторане--> |

|  | <inRestaurantTime>15.90</inRestaurantTime> |

|  | <!--время на стеллаже оперативности--> |

|  | <onShelfTime>3.72</onShelfTime> |

|  | <!--время в пути--> |

|  | <onTheWayTime>8.22</onTheWayTime> |

|  | <!--время на столе Пицца--> |

|  | <pizzaTime>0.00</pizzaTime> |

|  | <!--общее время--> |

|  | <totalTime>26.61</totalTime> |

|  | <!--тип метрики (AVERAGE - среднее, TARGET - отношение к целевым |

|  | показателям, MAXIMUM - максимальное значение)--> |

|  | <metricType>AVERAGE</metricType> |

|  | </row> |

|  | </rows> |

|  | </report> |

|  |  |



### Table:

| https://localhost:9080/resto/api/reports/delivery/orderCycle?depa |

|---|

| rtment={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&targetPiz |

| zaTime=5&targetCuttingTime=6&targetOnShelfTime=7&targetInRestaura |

| ntTime=8&targetOnTheWayTime=9&targetTotalTime=10&key=a113485b- |

| d4f1-0856-8faf-50ba913f04eb |



### Table:

|  |  |  |  |  |  |  | Описание |

|---|---|---|---|---|---|---|---|

|  | Параметры |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  | Подразделения(КодилиИД)(department={code="005"}).Еслинеуказан,отчет
будетпостроендлявсехподразделений(Чейн) |

|  | department |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  | Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD) |

|  |  | dateFrom |  |  |  |  |  |

|  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  | Датаокончанияотчета |

|  |  |  | dateTo |  |  |  |  |

|  |  |  |  |  |  |  |  |


---


## Page 6

API Documentation Page6 of 9
CopyCode
JSON
<report>
<rows>
<row>
<!--время (каждые полчаса)-->
<halfHourDate>01.04.2014 10:00</halfHourDate>
<metrics>
<metric>
<!--среднее кол-во блюд на чек-->
<avgDishAmountPerReceipt>3.500</avgDishAmountPerReceipt>
<!--средний чек-->
<avgReceipt>635.00</avgReceipt>
<!--тип доставки-->
<deliveryType>COURIER</deliveryType>
<!--кол-во блюд-->
<dishAmount>7.000</dishAmount>
<!--кол-во заказов-->
<orderCount>2.00</orderCount>
</metric>
<metric>
<avgDishAmountPerReceipt>3.000</avgDishAmountPerReceipt>
<avgReceipt>226.00</avgReceipt>
<deliveryType>PICKUP</deliveryType>
<dishAmount>6.000</dishAmount>
<orderCount>2.00</orderCount>
</metric>
</metrics>
</row>...</rows>
</report>
Пример вызова
https://localhost:9080/resto/api/reports/delivery/halfHourDetaile
d?department={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&key
=d34ab6bd-1515-f22e-d02d-92d2a682a512
Отчет по регионам
https://host:port/resto/api/reports/delivery/regions
Параметры запроса
Allrightsreserved © CompanyInc., 2023


### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | <report> |  |

|  | <rows> |  |

|  | <row> |  |

|  | <!--время (каждые полчаса)--> |  |

|  | <halfHourDate>01.04.2014 10:00</halfHourDate> |  |

|  | <metrics> |  |

|  | <metric> |  |

|  | <!--среднее кол-во блюд на чек--> |  |

|  | <avgDishAmountPerReceipt>3.500</avgDishAmountPerReceipt> |  |

|  | <!--средний чек--> |  |

|  | <avgReceipt>635.00</avgReceipt> |  |

|  | <!--тип доставки--> |  |

|  | <deliveryType>COURIER</deliveryType> |  |

|  | <!--кол-во блюд--> |  |

|  | <dishAmount>7.000</dishAmount> |  |

|  | <!--кол-во заказов--> |  |

|  | <orderCount>2.00</orderCount> |  |

|  | </metric> |  |

|  | <metric> |  |

|  | <avgDishAmountPerReceipt>3.000</avgDishAmountPerReceipt> |  |

|  | <avgReceipt>226.00</avgReceipt> |  |

|  | <deliveryType>PICKUP</deliveryType> |  |

|  | <dishAmount>6.000</dishAmount> |  |

|  | <orderCount>2.00</orderCount> |  |

|  | </metric> |  |

|  | </metrics> |  |

|  | </row>...</rows> |  |

|  | </report> |  |

|  |  |  |



### Table:

| https://localhost:9080/resto/api/reports/delivery/halfHourDetaile |  |

|---|---|

| d?department={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&key |  |

| =d34ab6bd-1515-f22e-d02d-92d2a682a512 |  |


---


## Page 7

API Documentation Page7 of 9
Параметры Описание
department Подразделения(КодилиИД)(department={code="005"}).Еслинеуказан,отчет
будетпостроендлявсехподразделений(Чейн)
dateFrom Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD)
dateTo Датаокончанияотчета
Что в ответе
CopyCode
JSON
<report>
<rows>
<row>
<!--среднее время доставки-->
<averageDeliveryTime>18.41</averageDeliveryTime>
<!--процент доставленных заказов-->
<deliveredOrdersPercent>100.00</deliveredOrdersPercent>
<!--максимальное кол-во заказов в день-->
<maxOrderCountDay>142.00</maxOrderCountDay>
<!--общее кол-во заказов-->
<orderCount>2336.00</orderCount>
<!--регион-->
<region>G1</region>
</row>
</rows>
</report>
Пример вызова
https://localhost:9080/resto/api/reports/delivery/regions?departm
ent={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&key=08c12b43
-3b43-6493-c758-3ee1e6f2a978
Отчет по регионам
https://host:port/resto/api/reports/delivery/loyalty
Параметры запроса
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  | Описание |

|---|---|---|---|---|---|---|---|

|  | Параметры |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  | Подразделения(КодилиИД)(department={code="005"}).Еслинеуказан,отчет
будетпостроендлявсехподразделений(Чейн) |

|  | department |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  | Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD) |

|  |  | dateFrom |  |  |  |  |  |

|  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  | Датаокончанияотчета |

|  |  |  | dateTo |  |  |  |  |

|  |  |  |  |  |  |  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | <report> |  |

|  | <rows> |  |

|  | <row> |  |

|  | <!--среднее время доставки--> |  |

|  | <averageDeliveryTime>18.41</averageDeliveryTime> |  |

|  | <!--процент доставленных заказов--> |  |

|  | <deliveredOrdersPercent>100.00</deliveredOrdersPercent> |  |

|  | <!--максимальное кол-во заказов в день--> |  |

|  | <maxOrderCountDay>142.00</maxOrderCountDay> |  |

|  | <!--общее кол-во заказов--> |  |

|  | <orderCount>2336.00</orderCount> |  |

|  | <!--регион--> |  |

|  | <region>G1</region> |  |

|  | </row> |  |

|  | </rows> |  |

|  | </report> |  |

|  |  |  |



### Table:

|  |

|---|

| https://localhost:9080/resto/api/reports/delivery/regions?departm
ent={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&key=08c12b43
-3b43-6493-c758-3ee1e6f2a978 |

|  |



### Table:

| https://localhost:9080/resto/api/reports/delivery/regions?departm |

|---|

| ent={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&key=08c12b43 |


---


## Page 8

API Documentation Page8 of 9
Параметры Описание
department Подразделения(КодилиИД)(department={code="005"}).Еслинеуказан,отчет
будетпостроендлявсехподразделений(Чейн)
dateFrom Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD)
dateTo Датаокончанияотчета
metricType Типметрики(AVERAGE-среднее,MINIMUM-минимальноезначение,MAXIMUM
-максимальноезначение
Что в ответе
CopyCode
JSON
<report>
<rows>
<row>
<!--дата-->
<date>01.04.2014</date>
<!--тип метрики-->
<metricType>AVERAGE</metricType>
<!--кол-во новых гостей-->
<newGuestCount>58.00</newGuestCount>
<!--среднее кол-во заказов на гостя-->
<orderCountPerGuest>1.08</orderCountPerGuest>
<regions>
<region>
<!--кол-во заказов-->
<orderCount>61.00</orderCount>
<!--регион-->
<region>G1</region>
</region>
<region>
<orderCount>153.00</orderCount>
</region>
</regions>
<totalOrderCount>214.00</totalOrderCount
</row>
...
</rows>
</report>
Пример вызова
Allrightsreserved © CompanyInc., 2023


### Table:

|  |  |  |  |  |  |  | Описание |

|---|---|---|---|---|---|---|---|

|  | Параметры |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  | Подразделения(КодилиИД)(department={code="005"}).Еслинеуказан,отчет
будетпостроендлявсехподразделений(Чейн) |

|  | department |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  | Датаначалаотчета(DD.MM.YYYYилиYYYY-MM-DD) |

|  |  | dateFrom |  |  |  |  |  |

|  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  | Датаокончанияотчета |

|  |  |  | dateTo |  |  |  |  |

|  |  |  |  |  |  |  |  |

|  |  |  |  |  |  |  | Типметрики(AVERAGE-среднее,MINIMUM-минимальноезначение,MAXIMUM
-максимальноезначение |

|  | metricType |  |  |  |  |  |  |

|  |  |  |  |  |  |  |  |



### Table:

| CopyCode |  |  |

|---|---|---|

|  | JSON |  |

|  |  |  |

|  |  |  |

|  | <report> |  |

|  | <rows> |  |

|  | <row> |  |

|  | <!--дата--> |  |

|  | <date>01.04.2014</date> |  |

|  | <!--тип метрики--> |  |

|  | <metricType>AVERAGE</metricType> |  |

|  | <!--кол-во новых гостей--> |  |

|  | <newGuestCount>58.00</newGuestCount> |  |

|  | <!--среднее кол-во заказов на гостя--> |  |

|  | <orderCountPerGuest>1.08</orderCountPerGuest> |  |

|  | <regions> |  |

|  | <region> |  |

|  | <!--кол-во заказов--> |  |

|  | <orderCount>61.00</orderCount> |  |

|  | <!--регион--> |  |

|  | <region>G1</region> |  |

|  | </region> |  |

|  | <region> |  |

|  | <orderCount>153.00</orderCount> |  |

|  | </region> |  |

|  | </regions |  |

|  | <totalOrderCount>214.00</totalOrderCount |  |

|  | </row> |  |

|  | ... |  |

|  | </rows> |  |

|  | </report> |  |

|  |  |  |


---


## Page 9

API Documentation Page9 of 9
https://localhost:9080/resto/api/reports/delivery/loyalty?departm
ent={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&metricType=A
VERAGE&key=23d49457-025c-f23c-35dd-8e32eceef8a4
Allrightsreserved © CompanyInc., 2023


### Table:

|  |

|---|

| https://localhost:9080/resto/api/reports/delivery/loyalty?departm
ent={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&metricType=A
VERAGE&key=23d49457-025c-f23c-35dd-8e32eceef8a4 |

|  |



### Table:

| https://localhost:9080/resto/api/reports/delivery/loyalty?departm |

|---|

| ent={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&metricType=A |


---
