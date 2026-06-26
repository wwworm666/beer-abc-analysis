* [Методы для работы с заказами на стол](/articles/api-documentations/rabota-s-zakazom-na-stol/a/h2_1962164077)
* [Работа с QR кодами на столе](/articles/api-documentations/rabota-s-zakazom-na-stol/a/h2__991776161)
* [Что необходимо](/articles/api-documentations/rabota-s-zakazom-na-stol/a/h3__1865005608)
* [Описание процесса работы с QR-кодами и действий гостя в ресторане](/articles/api-documentations/rabota-s-zakazom-na-stol/a/h3__541222395)
* [Примечание](/articles/api-documentations/rabota-s-zakazom-na-stol/a/h3__81553844)

В iikoCloud API существует блок методов, позволяющих работать с заказами в стол (создание заказа по QR-коду со стола в заведении). Методы для заказов в стол отличны от методов для работы с доставками, и находятся в блоке [Orders](https://api-ru.iiko.services/docs#tag/Orders).

##  Методы для работы с заказами на стол

1. [Метод](https://api-ru.iiko.services/docs#tag/Orders/paths/~1api~11~1order~1create/post) создания ресторанного заказа в стол.
2. [Метод](https://api-ru.iiko.services/docs#tag/Orders/paths/~1api~11~1order~1by_id/post) поиска заказа по его идентификатору. Возможно только для заказов, созданных через API, или заказов, попавших в API после вызова метода из пункта 7.
3. [Метод](https://api-ru.iiko.services/docs#tag/Orders/paths/~1api~11~1order~1by_table/post) поиска заказа по номеру стола. Возможно только для заказов, созданных через API, или заказов, попавших в API после вызова метода из пункта 7.
4. [Добавление](https://api-ru.iiko.services/docs#tag/Orders/paths/~1api~11~1order~1add_items/post) позиции в заказ.
5. [Закрытие](https://api-ru.iiko.services/docs#tag/Orders/paths/~1api~11~1order~1close/post) заказа. Возможно только, если заказ оплачен. Платеж можно передать как сразу в создании заказа, так и добавить позже через вызов метода в пункте 6.
6. [Изменение](https://api-ru.iiko.services/docs#tag/Orders/paths/~1api~11~1order~1change_payments/post) платежа заказа. На данный момент нельзя добавить в заказ более одного платежа.
7. [Метод](https://api-ru.iiko.services/docs#tag/Orders/paths/~1api~11~1order~1init_by_table/post), позволяющий протолкнуть заказы в стол, созданные на фронте, в API. Если заказы были созданы не через API iikoCloud, а через кассу или другим путем, то автоматически такие заказы не отображаются в API. Чтобы они там отобразились, нужно вызвать данный метод. Данный метод будет работать только в том случае, если заказ не закрыт в iikoFront.

В данной статье описан основной сценарий использования методов АПИ для реализации пользовательских приложений об оплате и создание заказов внутри ресторана.

## Работа с QR кодами на столе

###  Что необходимо 

Необходимые лицензии для работы: iikoCloud API-входит в состав тарифов iikoCloud, для LT необходимо приобретать [iikoCloud API](/smart/project-iikoweb/iikocloudapi).

###  Описание процесса работы с QR-кодами и действий гостя в ресторане 

* QR код наклеивается на каждый стол в ресторане,

* В QR код может содержаться следующая информация: id ресторана, id зала, id стола - эти данные могут потребоваться приложению для четкого позиционированию в ресторане.

* Гость приходит в ресторан, считывает QR и попадает в приложение, где он может просмотреть меню и сделать заказ или так же после просмотра меню позвать официанта и сделать заказ через него.
* После оформления заказа (гость может в любой момент произвести полную оплату заказа) в приложения заказа уходит на фронт и сразу начинает готовиться. Также гость может просмотреть статус своего заказа в приложении.

![](/resources/Storage/api-documentations/rabota-s-zakazom-na-stol/rabota-s-zakazom-na-stol-2025-03-21.png)

**Ссылка на схему в [Miro](https://miro.com/app/board/uXjVOJM3MU8=/?invite_link_id=116382572391)**

Шаги при работе с заказом на стол по QR-коду:
1. Получить [список организаций](https://api-ru.iiko.services/docs#tag/Organizations),

2. Получить [список терминалов](https://api-ru.iiko.services/docs#tag/Terminal-groups),

3. Получить [список внешних меню](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~12~1menu/post) и [доступных позиций](https://api-ru.iiko.services/docs#tag/Menu/paths/~1api~12~1menu~1by_id/post),

4. Создать [заказ на стол](https://api-ru.iiko.services/docs#tag/Orders/paths/~1api~11~1order~1create/post),

5. Получить [список типов оплат](https://api-ru.iiko.services/docs#tag/Dictionaries/paths/~1api~11~1payment_types/post),

6. [Найти заказ для оплаты](https://api-ru.iiko.services/docs#tag/Orders/paths/~1api~11~1order~1by_id/post),

7. [Оплата заказа](https://api-ru.iiko.services/docs#tag/Orders/paths/~1api~11~1order~1close/post).

###  Примечание 

Заказы в стол, оформленные в iikoFront, можно получить только через API.Front. Для этого необходимо реализовать плагин на C#.

Ниже вы найдете ссылки на документацию и примеры

[https://iiko.github.io/front.api.doc/](https://iiko.github.io/front.api.doc/)

[https://github.com/iiko/front.api.sdk/tree/master/sample](https://github.com/iiko/front.api.sdk/tree/master/sample)

Ближайшее время данный функционал будет реализован и в iikoCloud API.
