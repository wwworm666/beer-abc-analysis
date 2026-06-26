* [Диагностика ошибки создания заказа](/articles/api-documentations/poryadok-razbora-problem-s-dostavochnymi-zakazami/a/h2__1863382226)
* [1. Создание доставки на выключенный iikoFront/либо при проблемах с доступом](/articles/api-documentations/poryadok-razbora-problem-s-dostavochnymi-zakazami/a/h3__52802670)
* [2. Не задана шкала размеров](/articles/api-documentations/poryadok-razbora-problem-s-dostavochnymi-zakazami/a/h3_1003885137)
* [3. Некорректные настройки модификаторов и их количественных ограничений для блюда](/articles/api-documentations/poryadok-razbora-problem-s-dostavochnymi-zakazami/a/h3_194301965)
* [4. Не задан тип места приготовления для блюда или некорректно выбрано блюдо](/articles/api-documentations/poryadok-razbora-problem-s-dostavochnymi-zakazami/a/h3__1922137823)
* [5. Блюдо исключено из меню](/articles/api-documentations/poryadok-razbora-problem-s-dostavochnymi-zakazami/a/h3__1494550100)
* [6. Товар не включен в продажу](/articles/api-documentations/poryadok-razbora-problem-s-dostavochnymi-zakazami/a/h3__1917161268)

Заказы, полученные по API, могут не создаться на терминале iikoFront по ряду причин. В данной статье рассмотрим наиболее часто встречающиеся случаи и наиболее популярные причины проблем с созданием заказов через iikoTransport.

## Диагностика ошибки создания заказа

Все ошибки, связанные с созданием заказов через iikoTransport, можно найти в логе транспортного плагина **plugin-Resto.Front.Api.iikoTransport.VXPreviewX** в iikoFront.
Получив ошибку, её легко можно найти по correlation id от внешних сервисов (например, от Delivery Club). Для поиска в логе фронтового плагина транспорта также пригодится время и дата направления запроса на создание доставочного заказа от внешнего сервиса в CloudApi и ключевые слова **save order**, **create order**.

### 1. Создание доставки на выключенный iikoFront/либо при проблемах с доступом

В ответе будет (обычно **Creation timeout expired, order automatically transited to error creation status**)


Code

```
{
    "correlationId": "ba101f44-e166-4b0a-b052-2ccc815b79d8",
    "orders": [
        {
            "id": "2b370a38-7b1f-4a0b-90c4-a2d7c45570e3",
            "organizationId": "******-****-****-****-***********",
            "timestamp": 1650895228234,
            "creationStatus": "Error",
```

Code

```
{
    "correlationId": "ba101f44-e166-4b0a-b052-2ccc815b79d8",
    "orders": [
        {
            "id": "2b370a38-7b1f-4a0b-90c4-a2d7c45570e3",
            "organizationId": "******-****-****-****-***********",
            "timestamp": 1650895228234,
            "creationStatus": "Error",
```


В ответе есть время (в таком виде "timestamp": 1650895228234)
Переводим в привычный нам вид (любым доступным online [конвертером](https://www.unixtimestamp.com/))![](/resources/Storage/api-documentations/project-knowlege-base/getting-started-2022-04-25.png)

**GMT**: Monday, 25 April 2022 г., 14:00:28.234
**Your time zone**: понедельник, 25 апреля 2022 г., 17:00:28.234 [GMT+03:00](https://www.epochconverter.com/timezones?q=1650895228234)

В **cash-server.log** проверяем таймзону на фронте с главным терминалом:

Current time zone is (**UTC+03:00**) Kuwait, Riyadh (Arab Standard Time) with effective UTC offset 03:00

Далее проверяем plugin-Resto.Front.Api.iikoTransport.VXPreviewX.log - время из ответа.

**Решение**

1) при выполнении любого метода Cloud API iikoFront должен быть включен, так как в противном случае будет отсутствовать связь транспорта и терминальной группы, и заказы не будут доставлены на кассу.

Перед выполнением запроса на создание заказа выполните вызов метода проверки доступности терминала - [/api/1/terminal_groups/is_alive](https://api-ru.iiko.services/docs#tag/Terminal-groups/paths/~1api~11~1terminal_groups~1is_alive/post). Если в ответе метода "isAlive": true, то можно переходить к методу выполнения запроса на создание заказа.

2) после выполнения метода создания заказа можно уточнить, действительно ли заказ дошел до кассы. Для этого используйте метод [/api/1/commands/status](https://api-ru.iiko.services/docs#tag/Operations/paths/~1api~11~1commands~1status/post).

Если в ответе метода

"state": "InProgress" - заказ ещё не дошел до кассы,

если "state": "Success" - заказ дошел до кассы и можно выполнять следующие действия заказом,

если "state": "Error" и добавлено описание ошибки - в теле запроса создания заказа есть ошибка, требуется её устранение и повторное выполнение.

| ![Warning](/resources/Storage/api-documentations/api-documentations/warning.png) | Многократное выполнение любого метода с ошибочным телом запроса может привести к  API ключа. |
| --- | --- |

Ознакомьтесь с [общими принципами создания заказа](/articles/api-documentations/~obschie-printsipy-sozdaniya-zakaza-na-stol-i-na-dostavku) и по работе с [терминальными группами](/articles/iikoweb/iikocloudapi/a/h3_129714767).

### 2. Не задана шкала размеров

В таких случаях в логах**plugin-Resto.Front.Api.iikoTransport.VXPreviewX** можно найти сообщения вида:


Code

```
2021-10-29 17:37:22,466]  INFO [64] - [CorrelationId: a5148df3-e6ac-4bf6-87d4-98ec05f15588, Route: Orders/CreateOrder] 
Can not create delivery order 3b8e218f-d743-4eb9-acc4-1c0c25bf3114 / 5d34325c-a480-4a03-8411-c0ee56effaa5: 
Resto.Front.Api.Exceptions.ConstraintViolationException: 
Product “Маргарита” (28828c4a-728e-4a13-94da-ce6237cf8bde) has scale “Пицца” (73b7cd7c-1c8a-4623-958f-008be41662d7), 
therefore product size must be specified.
```

Code

```
2021-10-29 17:37:22,466]  INFO [64] - [CorrelationId: a5148df3-e6ac-4bf6-87d4-98ec05f15588, Route: Orders/CreateOrder] 
Can not create delivery order 3b8e218f-d743-4eb9-acc4-1c0c25bf3114 / 5d34325c-a480-4a03-8411-c0ee56effaa5: 
Resto.Front.Api.Exceptions.ConstraintViolationException: 
Product “Маргарита” (28828c4a-728e-4a13-94da-ce6237cf8bde) has scale “Пицца” (73b7cd7c-1c8a-4623-958f-008be41662d7), 
therefore product size must be specified.
```


**Решением** будет проверить настройки блюда и задать шкалу размеров. Дополнительно проверить все блюда и их модификаторы на включенность в прейскурант в iikoOffice.

### 3. Некорректные настройки модификаторов и их количественных ограничений для блюда

Также находим по **correlationId** или по **Orders/SetOrderError**, **Start converting delivery order**, **Start order save**, **Can not create delivery order**


Code

```
[2021-09-02 11:59:13,559]  INFO [Event Loop 1] - Schedule new message: Id: 730c60fb-b7be-4d04-aa24-cc0171e3b609, 
CorrelationId: 57cf8884-94d7-4d9e-be6e-e3a9da497883, Route: Orders/SetOrderError.

```

Code

```
[2021-09-02 11:59:13,559]  INFO [Event Loop 1] - Schedule new message: Id: 730c60fb-b7be-4d04-aa24-cc0171e3b609, 
CorrelationId: 57cf8884-94d7-4d9e-be6e-e3a9da497883, Route: Orders/SetOrderError.

```


Чуть выше запись в логе:
Code

```
[2021-09-02 11:59:13,559]  INFO [AMQP Connection amqp://rbmq-ru.iiko.services:5671] - 
Can not create delivery order f6f46419-6402-40f7-a11e-01b5d8acd48f: Resto.Front.Api.Exceptions.ConstraintViolationException: 
Order item modifier “гарнир” (2fe947ca-306a-43c2-9917-2714485d839a) has invalid group amount: min = 1, max = 1, actual = 0. 
Ensure that interconnected product and modifier changes are in the same edit session.

```

Code

```
[2021-09-02 11:59:13,559]  INFO [AMQP Connection amqp://rbmq-ru.iiko.services:5671] - 
Can not create delivery order f6f46419-6402-40f7-a11e-01b5d8acd48f: Resto.Front.Api.Exceptions.ConstraintViolationException: 
Order item modifier “гарнир” (2fe947ca-306a-43c2-9917-2714485d839a) has invalid group amount: min = 1, max = 1, actual = 0. 
Ensure that interconnected product and modifier changes are in the same edit session.

```


**Решением** будет проверить настройки блюда и модификаторов, скорректировав настройки в iikoOffice.

### 4. Не задан тип места приготовления для блюда или некорректно выбрано блюдо

В логе имеется запись:
Code

```
[2021-08-16 13:51:34,059]  INFO [12] - Finish order convert.
Start order save.
[2021-08-16 13:51:35,387]  INFO [47] - [CorrelationId: 4b26cb05-2f24-4c22-9a45-aa61bc451ec6, Route: Orders/CreateOrder] 
Can not create delivery order 0e021256-a74f-4a0b-bb2d-417bf027f2a3: Resto.Front.Api.Exceptions.ConstraintViolationException: 
Product “Округление в пользу гостя” (5b08a4c4-2453-a7f6-4275-4db8016a2e1f) doesn't have cooking place type.

```

Code

```
[2021-08-16 13:51:34,059]  INFO [12] - Finish order convert.
Start order save.
[2021-08-16 13:51:35,387]  INFO [47] - [CorrelationId: 4b26cb05-2f24-4c22-9a45-aa61bc451ec6, Route: Orders/CreateOrder] 
Can not create delivery order 0e021256-a74f-4a0b-bb2d-417bf027f2a3: Resto.Front.Api.Exceptions.ConstraintViolationException: 
Product “Округление в пользу гостя” (5b08a4c4-2453-a7f6-4275-4db8016a2e1f) doesn't have cooking place type.

```


**Решением** будет проверить настройки блюда и типа места приготовления, скорректировав настройки в iikoOffice. Проверить настройки сайта конструктора (блок "доставка" - поле "услуга доставки") или другого внешнего сервиса на предмет необходимости добавления того или иного блюда в заказ.

### 5. Блюдо исключено из меню

Частый сценарий, когда заказ создается на блюдо запрещенное к продаже. В логах фронтового транспортного плагина также будет присутствовать запись **excluded from menu**.

**Решением** будет включить блюдо в меню и проверить выгрузку меню и действующий прейскурант.

### 6. Товар не включен в продажу

Если поискать по id из ответа в логе транспортного плагина на фронте, то станет понятно в чем была ошибка.
В логе имеется запись:
Code

```
[2022-02-25 12:05:01,303]  INFO [48] - Finish order convert.
Start order save.
[2022-02-25 12:05:01,443]  INFO [ 8] - [CorrelationId: 896e8821-5e2f-44c3-93fe-5efedd168e43, 
Route: Orders/CreateOrder] Can not create delivery order c62db178-3561-4600-a098-8a8664e011d1 / 13088676-1311-8060-8769-745828518553: 
Resto.Front.Api.Exceptions.CannotAddInactiveProductException: 
Product “Молоко отдельно” (d131d813-c586-0cd0-0158-a8b4c8135c96) is inactive. Only active products can be added to order.

```

Code

```
[2022-02-25 12:05:01,303]  INFO [48] - Finish order convert.
Start order save.
[2022-02-25 12:05:01,443]  INFO [ 8] - [CorrelationId: 896e8821-5e2f-44c3-93fe-5efedd168e43, 
Route: Orders/CreateOrder] Can not create delivery order c62db178-3561-4600-a098-8a8664e011d1 / 13088676-1311-8060-8769-745828518553: 
Resto.Front.Api.Exceptions.CannotAddInactiveProductException: 
Product “Молоко отдельно” (d131d813-c586-0cd0-0158-a8b4c8135c96) is inactive. Only active products can be added to order.

```


**Решением** будет проверить включенность товара в продажу и при необходимости внести правки в прейскурант и карточку товара/блюда.
