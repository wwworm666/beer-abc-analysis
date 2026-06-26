* [Создание предустановленного отчета](/articles/api-documentations/olap-otchety-po-dostavke/a/h2_1713623608)

## Создание предустановленного отчета 

1. В iikoOffice в разделе **Доставка → Отчеты по доставкам** создаем новый отчет, выбираем необходимые нам поля в нем и сохраняем.![](/resources/Storage/api-documentations/olap-otchety-po-dostavke/olap-otchety-po-dostavke-2025-01-24.png)
2. Через API запрашиваем список пресетов отчетов.

GET-запрос:

https://iiko.biz:9900/api/0/olaps/olapPresets?access\_token=nOt79Q6RqQhL4ZdIGfGQU6TL08ryShQn7UaeKyS4G4WgSbmK4FvMpWS3PzRGiquG6KP4O4npk\_1Jg15PVv83pw2&request\_timeout=00%3A02%3A00&organizationId=f20594c6-2da7-11e8-80e0-d8d38565926f

Результат:


```json
{
    "presets": [
        "{\"id\":\"b3d1eaaa-26ad-4996-947b-093dcc4be071\",\"name\":\"111\",\"buildSummary\":null,\"reportType\":\"DELIVERIES\",\"groupByRowFields\":[\"DishName\"],\"groupByColFields\":[\"Delivery.IsDelivery\"],\"aggregateFields\":[\"Bonus.Sum\",\"DishSumInt\"],\"filters\":{\"DeletedWithWriteoff\":{\"filterType\":\"IncludeValues\",\"values\":[\"NOT_DELETED\"]},\"DishName\":{\"filterType\":\"IncludeValues\",\"values\":[null,\"4 сыра\"]},\"OrderDeleted\":{\"filterType\":\"IncludeValues\",\"values\":[\"NOT_DELETED\"]}}}",
        "{\"id\":\"22c5dc3a-6ef3-2a5c-0162-2e25135c0012\",\"name\":\"Почасовая выручка\",\"buildSummary\":null,\"reportType\":\"SALES\",\"groupByRowFields\":[\"OpenDate.Typed\",\"HourClose\"],\"groupByColFields\":[],\"aggregateFields\":[\"GuestNum\",\"DishSumInt\",\"DishDiscountSumInt\",\"UniqOrderId\"],\"filters\":{\"DeletedWithWriteoff\":{\"filterType\":\"IncludeValues\",\"values\":[\"NOT_DELETED\"]},\"OrderDeleted\":{\"filterType\":\"IncludeValues\",\"values\":[\"NOT_DELETED\"]}}}",
      ...
      и т.д
```

```json
{
    "presets": [
        "{\"id\":\"b3d1eaaa-26ad-4996-947b-093dcc4be071\",\"name\":\"111\",\"buildSummary\":null,\"reportType\":\"DELIVERIES\",\"groupByRowFields\":[\"DishName\"],\"groupByColFields\":[\"Delivery.IsDelivery\"],\"aggregateFields\":[\"Bonus.Sum\",\"DishSumInt\"],\"filters\":{\"DeletedWithWriteoff\":{\"filterType\":\"IncludeValues\",\"values\":[\"NOT_DELETED\"]},\"DishName\":{\"filterType\":\"IncludeValues\",\"values\":[null,\"4 сыра\"]},\"OrderDeleted\":{\"filterType\":\"IncludeValues\",\"values\":[\"NOT_DELETED\"]}}}",
        "{\"id\":\"22c5dc3a-6ef3-2a5c-0162-2e25135c0012\",\"name\":\"Почасовая выручка\",\"buildSummary\":null,\"reportType\":\"SALES\",\"groupByRowFields\":[\"OpenDate.Typed\",\"HourClose\"],\"groupByColFields\":[],\"aggregateFields\":[\"GuestNum\",\"DishSumInt\",\"DishDiscountSumInt\",\"UniqOrderId\"],\"filters\":{\"DeletedWithWriteoff\":{\"filterType\":\"IncludeValues\",\"values\":[\"NOT_DELETED\"]},\"OrderDeleted\":{\"filterType\":\"IncludeValues\",\"values\":[\"NOT_DELETED\"]}}}",
      ...
      и т.д
```

 * Выполняем наш отчет по его presetId.
 
POST-запрос:

https://iiko.biz:9900/api/0/olaps/olapByPreset?access\_token=nOt79Q6RqQhL4ZdIGfGQU97jDXEk9yYrBmbpSCeBS48cdvnAiFKy-7NsBMzXztaGP5bQcjtoG9jSyTlM-62R1w2&organizationId=f20594c6-2da7-11e8-80e0-d8d38565926f&request\_timeout=00%3A01%3A00

с телом запроса в формате application/json:
```json
{
    "dateFrom": "2017-01-01",
    "dateTo": "2019-06-30",
    "presetId": "b3d1eaaa-26ad-4996-947b-093dcc4be071"
}
```

```json
{
    "dateFrom": "2017-01-01",
    "dateTo": "2019-06-30",
    "presetId": "b3d1eaaa-26ad-4996-947b-093dcc4be071"
}
```



```json
{
    "dateFrom": "2017-01-01",
    "dateTo": "2019-06-30",
    "presetId": "b3d1eaaa-26ad-4996-947b-093dcc4be071"
}
```

```json
{
    "dateFrom": "2017-01-01",
    "dateTo": "2019-06-30",
    "presetId": "b3d1eaaa-26ad-4996-947b-093dcc4be071"
}
```


Результат:
```json
{
    "data": "[{\"Bonus.Sum\":null,\"Delivery.IsDelivery\":\"DELIVERY_ORDER\",\"DishName\":\"4 сыра\",\"DishSumInt\":23000},{\"Bonus.Sum\":null,\"Delivery.IsDelivery\":\"ORDER_WITHOUT_DELIVERY\",\"DishName\":\"4 сыра\",\"DishSumInt\":7400}]",
    "summary": "[[{\"Delivery.IsDelivery\":\"ORDER_WITHOUT_DELIVERY\",\"DishName\":\"4 сыра\"},{\"Bonus.Sum\":null,\"DishSumInt\":7400}],[{\"Delivery.IsDelivery\":\"DELIVERY_ORDER\"},{\"Bonus.Sum\":null,\"DishSumInt\":23000}],[{},{\"Bonus.Sum\":null,\"DishSumInt\":30400}],[{\"Delivery.IsDelivery\":\"DELIVERY_ORDER\",\"DishName\":\"4 сыра\"},{\"Bonus.Sum\":null,\"DishSumInt\":23000}],[{\"DishName\":\"4 сыра\"},{\"Bonus.Sum\":null,\"DishSumInt\":30400}],[{\"Delivery.IsDelivery\":\"ORDER_WITHOUT_DELIVERY\"},{\"Bonus.Sum\":null,\"DishSumInt\":7400}]]",
    "organizationId": "f20594c6-2da7-11e8-80e0-d8d38565926f"
}
```

```json
{
    "data": "[{\"Bonus.Sum\":null,\"Delivery.IsDelivery\":\"DELIVERY_ORDER\",\"DishName\":\"4 сыра\",\"DishSumInt\":23000},{\"Bonus.Sum\":null,\"Delivery.IsDelivery\":\"ORDER_WITHOUT_DELIVERY\",\"DishName\":\"4 сыра\",\"DishSumInt\":7400}]",
    "summary": "[[{\"Delivery.IsDelivery\":\"ORDER_WITHOUT_DELIVERY\",\"DishName\":\"4 сыра\"},{\"Bonus.Sum\":null,\"DishSumInt\":7400}],[{\"Delivery.IsDelivery\":\"DELIVERY_ORDER\"},{\"Bonus.Sum\":null,\"DishSumInt\":23000}],[{},{\"Bonus.Sum\":null,\"DishSumInt\":30400}],[{\"Delivery.IsDelivery\":\"DELIVERY_ORDER\",\"DishName\":\"4 сыра\"},{\"Bonus.Sum\":null,\"DishSumInt\":23000}],[{\"DishName\":\"4 сыра\"},{\"Bonus.Sum\":null,\"DishSumInt\":30400}],[{\"Delivery.IsDelivery\":\"ORDER_WITHOUT_DELIVERY\"},{\"Bonus.Sum\":null,\"DishSumInt\":7400}]]",
    "organizationId": "f20594c6-2da7-11e8-80e0-d8d38565926f"
}
```


Выполнение OLAP-отчета с произвольными полями
 * Запрашиваем список полей, доступных для отчета. Тип отчета может быть со значениями «SALES», «TRANSACTIONS», «DELIVERIES».
 
GET-запрос:

https://iiko.biz:9900/api/0/olaps/olapColumns?access\_token=nOt79Q6RqQhL4ZdIGfGQUxTnZEsWGuCQTmtwYkNox1ci\_Eu7bU4BUf6VHZ1KBPrsezyvf9u4yNcChzkR1UmgjQ2&request\_timeout=00%3A02%3A00&organizationId=f20594c6-2da7-11e8-80e0-d8d38565926f&reportType=SALES
 * Исходя из полученного от API списка полей, выбираем необходимые и проверяем, доступны ли поля для группировки и агрегации значений (сумма).
 * Запрашиваем свой отчет через API.
 
POST-запрос:

https://iiko.biz:9900/api/0/olaps/olap?access\_token=nOt79Q6RqQhL4ZdIGfGQU6TL08ryShQn7UaeKyS4G4WgSbmK4FvMpWS3PzRGiquG6KP4O4npk\_1Jg15PVv83pw2

с телом запроса в формате application/json с

## 


```json
{
"organizationId":"f20594c6-2da7-11e8-80e0-d8d38565926f",
"olapSettings":"{\"reportType\": \"SALES\",\"groupByRowFields\": [\"Department\",\"OpenDate\"],\"aggregateFields\": [ \"DishDiscountSumInt\",\"DishSumInt\"],\"filters\": {\"OpenDate.Typed\": { 
 \"filterType\": \"DateRange\", 
 \"periodType\": \"CUSTOM\", 
 \"from\": \"2018-01-01\", 
 \"to\":   \"2018-08-17\"
 }}}"
}
```

```json
{
"organizationId":"f20594c6-2da7-11e8-80e0-d8d38565926f",
"olapSettings":"{\"reportType\": \"SALES\",\"groupByRowFields\": [\"Department\",\"OpenDate\"],\"aggregateFields\": [ \"DishDiscountSumInt\",\"DishSumInt\"],\"filters\": {\"OpenDate.Typed\": { 
 \"filterType\": \"DateRange\", 
 \"periodType\": \"CUSTOM\", 
 \"from\": \"2018-01-01\", 
 \"to\":   \"2018-08-17\"
 }}}"
}
```
