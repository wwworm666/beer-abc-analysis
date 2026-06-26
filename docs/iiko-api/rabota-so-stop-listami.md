* [Методы для работы со стоп-листами](/articles/api-documentations/rabota-so-stop-listami/a/h2_1962164077)
* [Варианты добавления блюда в стоп-лист](/articles/api-documentations/rabota-so-stop-listami/a/h3__886417724)
* [Рекомендации](/articles/api-documentations/rabota-so-stop-listami/a/h2_1483562539)

В iikoCloud API существует блок методов и веб-хук, позволяющие работать со стоп-листами.

##  Методы для работы со стоп-листами

1. [Метод](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1stop_lists/post)получения товаров, находящихся в стоп-листе.

2. [Метод](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1stop_lists~1check/post)проверки нахождения товара в стоп-листе.

Принимает на вход items - структура из запроса /api/1/deliveries/create, /api/1/order/create, /api/1/reserve/create (order.items) - т.е. позиции заказа.

Если какие-то из указанных позиций найдены в стоп-листе, то будет возвращаться структура вида:


```json
{
    "correlationId": "afbb6fa8-81f7-45a6-8748-79a9e0e064a0",
    "rejectedItems": [
        {
            "balance": 0.0,
            "productId": "5bb9a8ce-114e-4617-b8d4-1eac73a0b2f7",
            "productSizeId": "b4513563-032a-4dbc-8894-4b05c402f7de"
            "sku": "00144",
            "dateAdd": "2024-07-15 11:14:26.261"
        }
    ]
}
```

```json
{
    "correlationId": "afbb6fa8-81f7-45a6-8748-79a9e0e064a0",
    "rejectedItems": [
        {
            "balance": 0.0,
            "productId": "5bb9a8ce-114e-4617-b8d4-1eac73a0b2f7",
            "productSizeId": "b4513563-032a-4dbc-8894-4b05c402f7de"
            "sku": "00144",
            "dateAdd": "2024-07-15 11:14:26.261"
        }
    ]
}
```


где rejectedItems - это позиции, находящиеся в стоп-листе. Если позиции не в стоп-листе, то rejectedItems - null.
**Важно 1**. Учитывается так же баланс. Если запрошено позиций больше, чем в остатке в стоп-листе, то позиция будет отклонена.
**Важно 2**. Параметр sizeId будет присутствовать в ответе, только если у позиции есть размер.
**Важно 3**. Сам массив rejectedItems будет присутствовать в ответе только в том случае, если он не null (т.е. если есть отклоненные позиции). В позитивном случае поле не будет добавлено в ответ в целях экономии трафика.

3. [Метод](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1stop_lists~1add/post)добавления блюда в стоп-лист.

4. [Метод](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1stop_lists~1remove/post)удаления блюда из стоп-листа.

5. [Метод](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1stop_lists~1clear/post)очистки стоп-листа.

6. [Веб-хук](https://api-ru.iiko.services/docs#tag/Menu/paths/iikoTransport.PublicApi.Contracts.WebHooks.StopListUpdateWebHookEventInfo/post) об обновлении стоп-листа.

*\*Методы 2-5 доступны в тарифе [Enterprise](https://iiko.ru/solutions/products/price)*

### Варианты добавления блюда в стоп-лист

1. добавить блюдо в стоп-лист через iikoFront.

В iikoFront в разделе Сервис выбрать кнопку "Стоп-лист". В боковом меню справа выберите товар, который необходимо поместить в стоп-лист (убрать из продажи).

2. добавить блюдо в стоп-лист при помощи [метода](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1stop_lists~1add/post).

## Рекомендации

* На что обращать внимание при работе со стоп-листами:

- снята галочка "Включать в прайс-лист" (Места продаж) в карточке товара в iikoOffice,

- есть ли прейскурант на данное блюдо: при помощи прейскуранта можно как снять блюдо с продажи (галочка "Включить в прайс лист" снята), так и включить в прайс-лист, даже если блюдо снято с продажи - будет назначение в продажу с суммой из прейскуранта.

* Чтобы избежать попадания на рейт-лимиты у апи-логинов и получать актуальную инфу по стоп-листу мы советуем получать информацию, подписавшись на стоп-листы в настройках веб-хуков и после получения хука запрашивать стоп-лист [методом](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1stop_lists/post).
* Для случая, если не пришел веб-хук: в [методе](https://api-ru.iiko.services/docs#tag/Deliveries:-Create-and-update/paths/~1api~11~1deliveries~1create/post)создания доставочного заказа имеется параметр на проверку блюда в стоп-листе (checkStopList). Для активации параметра нужно передавать checkStopList = true.

![](/resources/Storage/api-documentations/rabota-so-stop-listami/rabota-so-stop-listami-2025-08-08.png)
