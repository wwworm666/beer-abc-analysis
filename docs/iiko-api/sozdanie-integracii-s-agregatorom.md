* [Что необходимо](/articles/api-documentations/sozdanie-integracii-s-agregatorom/a/h3__1865005608)
* [Описание действий агрегатора с заказом](/articles/api-documentations/sozdanie-integracii-s-agregatorom/a/h3__541222395)

В данной статье описан основной сценарий использования методов АПИ для реализации интеграции агрегаторов по созданию доставок в ресторан.

###  Что необходимо

Необходимые лицензии для работы: iikoCloud API-входит в состав тарифов iikoCloud, для LT необходимо приобретать [iikoCloud API](/smart/project-iikoweb/iikocloudapi).

### Описание действий агрегатора с заказом 

Данная интеграция позволяет агрегатору создавать заказ в кассовой системе ресторана автоматически и в дальнейшем получать статусы по данному заказу.

Доставки, которые отправляются в заведение, могут быть с проведенными платежами, тогда на стороне ресторана нужно будет только закрыть заказ. Или заказ будет отправлен без проведенного платежа, тогда ресторану необходимо будет принять платеж от гостя.
![](/resources/Storage/api-documentations/rabota-s-agregatorom-dostavki/rabota-s-agregatorom-dostavki-2025-03-21.png)
**Ссылка на схему в [Miro](https://miro.com/app/board/uXjVOIKjzMs=/?share_link_id=211820775694)**
Шаги при работе с доставочным заказом через агрегатор:
1. Получить [список организаций](https://api-ru.iiko.services/docs#tag/Organizations/paths/~1api~11~1organizations/post),

2. Получить [список терминалов](https://api-ru.iiko.services/docs#tag/Terminal-groups/paths/~1api~11~1terminal_groups/post),

3. Получить [список меню](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~12~1menu/post),

4. Получить [адрес](https://api-ru.iiko.services/#tag/Addresses),

5. Получить [тип доставки](https://api-ru.iiko.services/docs#tag/Dictionaries/paths/~1api~11~1deliveries~1order_types/post),

6. Создать [доставку](https://api-ru.iiko.services/docs#tag/Deliveries:-Create-and-update/paths/~1api~11~1deliveries~1create/post),

7. Закрыть [доставку](https://api-ru.iiko.services/docs#tag/Deliveries:-Create-and-update/paths/~1api~11~1deliveries~1close/post),

8. Получить [стоп-листы](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~11~1stop_lists/post),

9. Получить [статусы](https://api-ru.iiko.services/docs#tag/Deliveries:-Create-and-update/paths/~1api~11~1deliveries~1update_order_delivery_status/post).
