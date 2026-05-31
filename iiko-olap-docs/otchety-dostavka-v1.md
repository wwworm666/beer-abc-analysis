* [Отчеты по доставке](/articles/api-documentations/otchety-dostavka-v1/a/h2_1240291600)
* [Сводный отчет](/articles/api-documentations/otchety-dostavka-v1/a/v1.APIотчетов%28доставка%29-Сводныйотчет%28GETreports)
* [Параметры запроса](/articles/api-documentations/otchety-dostavka-v1/a/h3__998506674)
* [Что в ответе](/articles/api-documentations/otchety-dostavka-v1/a/h3_501454233)
* [Пример вызова](/articles/api-documentations/otchety-dostavka-v1/a/h3__232688264)
* [Отчет по курьерам](/articles/api-documentations/otchety-dostavka-v1/a/h2_1037094901)
* [Параметры запроса](/articles/api-documentations/otchety-dostavka-v1/a/h3_1258952149)
* [Что в ответе](/articles/api-documentations/otchety-dostavka-v1/a/h3__819598880)
* [Пример вызова](/articles/api-documentations/otchety-dostavka-v1/a/h3__2027210141)
* [Цикл заказа](/articles/api-documentations/otchety-dostavka-v1/a/v1.APIотчетов%28доставка%29-Циклзаказа%28GETreports)
* [Параметры запроса](/articles/api-documentations/otchety-dostavka-v1/a/h3_1316811548)
* [Что в ответе](/articles/api-documentations/otchety-dostavka-v1/a/h3_1865795195)
* [Пример вызова](/articles/api-documentations/otchety-dostavka-v1/a/h3_1793323402)
* [Получасовой детальный отчет](/articles/api-documentations/otchety-dostavka-v1/a/v1.APIотчетов%28доставка%29-Получасовойдетальныйотчет%28GETreports)
* [Параметры запроса](/articles/api-documentations/otchety-dostavka-v1/a/h3_1726970929)
* [Что в ответе](/articles/api-documentations/otchety-dostavka-v1/a/h3_1577632198)
* [Пример вызова](/articles/api-documentations/otchety-dostavka-v1/a/h3__1708034687)
* [Отчет по регионам](/articles/api-documentations/otchety-dostavka-v1/a/v1.APIотчетов%28доставка%29-Отчетпорегионам%28GETreports)
* [Параметры запроса](/articles/api-documentations/otchety-dostavka-v1/a/h3__1130534387)
* [Что в ответе](/articles/api-documentations/otchety-dostavka-v1/a/h3__614265233)
* [Пример вызова](/articles/api-documentations/otchety-dostavka-v1/a/h3_1486024652)
* [Отчет по регионам](/articles/api-documentations/otchety-dostavka-v1/a/v1.APIотчетов%28доставка%29-Отчетпорегионам%28GETreports)
* [Параметры запроса](/articles/api-documentations/otchety-dostavka-v1/a/h3__764351801)
* [Что в ответе](/articles/api-documentations/otchety-dostavka-v1/a/h3_442885765)
* [Пример вызова](/articles/api-documentations/otchety-dostavka-v1/a/h3_935121650)

## Отчеты по доставке

## Сводный отчет 

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/reports/delivery/consolidated |
| --- | --- |

### Параметры запроса

| **Параметры** | **Описание** |
| --- | --- |
| department | Подразделения (Код или ИД) (department={code="005"}). Если не указан, отчет будет построен для всех подразделений (Чейн) |
| --- | --- |
| dateFrom | Дата начала отчета (DD.MM.YYYY или YYYY-MM-DD) |
| --- | --- |
| dateTo | Дата окончания отчета |
| --- | --- |
| writeoffAccounts | Список счетов списания (код или ИД) |
| --- | --- |

### Что в ответе


```json
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
```


### Пример вызова

https://localhost:9080/resto/api/reports/delivery/consolidated?department={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&writeoffAccounts={code="5.14"}&writeoffAccounts={code="5.13"}&key=cd8cf2c7-a0a2-8b82-b29a-f4f9bf74e5c2

****

## Отчет по курьерам 

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/reports/delivery/couriers |
| --- | --- |

### Параметры запроса

| **Параметры** | **Описание** |
| --- | --- |
| department | Подразделения (Код или ИД) (department={code="005"}). Если не указан, отчет будет построен для всех подразделений (Чейн) |
| --- | --- |
| dateFrom | Дата начала отчета (DD.MM.YYYY или YYYY-MM-DD) |
| --- | --- |
| dateTo | Дата окончания отчета |
| --- | --- |
| targetCommonTime | Целевое значение общего времени, мин. (по умолчанию - 30 мин.) |
| --- | --- |
| targetOnTheWayTime | Целевое значение времени в пути, мин. (по умолчанию - 0 мин.) |
| --- | --- |
| targetDoubledOrders | Целевое количество сдвоенных заказов за день, шт. (по умолчанию - 0 мин.) |
| --- | --- |
| targetTripledOrders | Целевое количество строенных заказов за день, шт. (по умолчанию - 0 мин.) |
| --- | --- |
| targetTotalOrders | Целевое количество заказов за день, шт (по умолчанию - 0 мин.) |
| --- | --- |

### Что в ответе


```json
<report>
<rows>
<row>
<!--курьер–>
<courier>Елена</courier>
<metrics><metric>
<!--сдвоенные заказы-->
<doubledOrders>0.00</doubledOrders>
<!--тип метрики (AVERAGE - среднее,TARGET - отношение к целевым показателям,MAXIMUM - максимальное значение)-->
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
```


### Пример вызова

| https://localhost:9080/resto/api/reports/delivery/couriers?department={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&targetCommonTime=5&targetOnTheWayTime=6&targetDoubledOrders=7&targetTripledOrders=8&targetTotalOrders=9&key=d34ab6bd-1515-f22e-d02d-92d2a682a512 |
| --- |

## Цикл заказа 

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/reports/delivery/orderCycle |
| --- | --- |

### Параметры запроса

| **Параметры** | **Описание** |
| --- | --- |
| department | Подразделения (Код или ИД) (department={code="005"}). Если не указан, отчет будет построен для всех подразделений (Чейн) |
| --- | --- |
| dateFrom | Дата начала отчета (DD.MM.YYYY или YYYY-MM-DD) |
| --- | --- |
| dateTo | Дата окончания отчета |
| --- | --- |
| targetPizzaTime | Целевое значение времени на столе Пицца (по умолчанию - 0 мин.) |
| --- | --- |
| targetCuttingTime | Целевое значение времени на столе нарезки (по умолчанию - 0 мин.) |
| --- | --- |
| targetOnShelfTime | Целевое значение времени на стеллаже оперативности (по умолчанию - 0 мин.) |
| --- | --- |
| targetInRestaurantTime | Целевое значение времени в ресторане (по умолчанию - 0 мин.) |
| --- | --- |
| targetOnTheWayTime | Целевое значение времени в пути (по умолчанию - 0 мин.) |
| --- | --- |
| targetTotalTime | Целевое значение общего времени доставки (по умолчанию - 0 мин.) |
| --- | --- |

### Что в ответе


```json
<report>
<rows>
<row>
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
<!--тип метрики (AVERAGE - среднее, TARGET - отношение к целевым показателям, MAXIMUM - максимальное значение)-->
<metricType>AVERAGE</metricType>
</row>
</rows>
</report>
```


### Пример вызова

https://localhost:9080/resto/api/reports/delivery/orderCycle?department={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&targetPizzaTime=5&targetCuttingTime=6&targetOnShelfTime=7&targetInRestaurantTime=8&targetOnTheWayTime=9&targetTotalTime=10&key=a113485b-d4f1-0856-8faf-50ba913f04eb
 
## Получасовой детальный отчет 

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/reports/delivery/halfHourDetailed |
| --- | --- |

### Параметры запроса

| **Параметры** | **Описание** |
| --- | --- |
| department | Подразделения (Код или ИД) (department={code="005"}). Если не указан, отчет будет построен для всех подразделений (Чейн) |
| --- | --- |
| dateFrom | Дата начала отчета (DD.MM.YYYY или YYYY-MM-DD) |
| --- | --- |
| dateTo | Дата окончания отчета |
| --- | --- |

### Что в ответе


```json
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
```


### Пример вызова

https://localhost:9080/resto/api/reports/delivery/halfHourDetailed?department={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&key=d34ab6bd-1515-f22e-d02d-92d2a682a512

****

## Отчет по регионам 

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/reports/delivery/regions |
| --- | --- |

### Параметры запроса

| **Параметры** | **Описание** |
| --- | --- |
| department | Подразделения (Код или ИД) (department={code="005"}). Если не указан, отчет будет построен для всех подразделений (Чейн) |
| --- | --- |
| dateFrom | Дата начала отчета (DD.MM.YYYY или YYYY-MM-DD) |
| --- | --- |
| dateTo | Дата окончания отчета |
| --- | --- |

### Что в ответе


```json
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
```


### Пример вызова

| https://localhost:9080/resto/api/reports/delivery/regions?department={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&key=08c12b43-3b43-6493-c758-3ee1e6f2a978 |
| --- |

****

## Отчет по регионам

| ![GET Request](/resources/Storage/api-documentations/http_request_get.png) | https://host:port/resto/api/reports/delivery/loyalty |
| --- | --- |

### Параметры запроса
| **Параметры** | **Описание** |
| --- | --- |
| department | Подразделения (Код или ИД) (department={code="005"}). Если не указан, отчет будет построен для всех подразделений (Чейн) |
| --- | --- |
| dateFrom | Дата начала отчета (DD.MM.YYYY или YYYY-MM-DD) |
| --- | --- |
| dateTo | Дата окончания отчета |
| --- | --- |
| metricType | Тип метрики (AVERAGE - среднее, MINIMUM- минимальное значение, MAXIMUM - максимальное значение |
| --- | --- |
### Что в ответе


```json
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
```


### Пример вызова

| https://localhost:9080/resto/api/reports/delivery/loyalty?department={code="5"}&dateFrom=01.04.2014&dateTo=30.04.2014&metricType=AVERAGE&key=23d49457-025c-f23c-35dd-8e32eceef8a4 |
| --- |

****