* [Срок жизни токена](/articles/api-documentations/obschie-printsipy-raboty/a/h3__1865005608)
* [Срок хранения заказов](/articles/api-documentations/obschie-printsipy-raboty/a/h3__861456102)
* [Работа с меню в Chain](/articles/api-documentations/obschie-printsipy-raboty/a/h3__541222395)
* [Взаимодействие с iikoCard](/articles/api-documentations/obschie-printsipy-raboty/a/h3__81553844)
* [Работа с ценами и размерами](/articles/api-documentations/obschie-printsipy-raboty/a/h3__536366592)

Общие принципы работы
 
В iikoCloud API из схемы **исключен выделенный сервер CallCenter**. Все заказы отправляются напрямую на главную кассу фронтовой группы через входящий в стандартную поставку плагин интеграции.

![](/resources/Storage/api-documentations/image2020-3-10%2012_57_35.png)

Если при [создании заказа](/articles/api-documentations/~sozdanie-dostavochnogo-zakaza) не указан идентификатор терминальной группы, то работает механизм автоназначения заказа на точку (терминальная группа выбирается автоматически в зависимости от настроек ГРиК, заданных в iikoOffice).

Доставки, созданные на фронте всегда уходят также и в iikoCloud API автоматически, если работа через данное API включена. **Ресторанные заказы на стол**, **созданные на iikoFront, в API** **не уходят.**

###  Срок жизни токена

Стандартный срок жизни токена - 1 час.

### Срок хранения заказов

Заказы хранятся в iikoCloud API 90 дней.

###  Работа с меню в Chain

Для того чтобы настроить меню для РМС, входящих в состав iikoChain, нужно:

* Если меню одинаковое для всех точек - выбрать эталонный РМС и сделать [выгрузку меню](/articles/api-documentations/rabota-s-nomenklaturoy) на него;
* Если меню или цены разные - сделать выгрузку меню для каждого РМС отдельно.

###  Взаимодействие с iikoCard

Часть методов iikoCard уже перенесена в iikoCloud API, в скором времени этот список пополнится. Для использования методов iikoCard, которых нет в iikoCloud API, необходимо использовать [API iikoCard](https://docs.google.com/document/d/1kuhs94UV_0oUkI2CI3uOsNo_dydmh9Q0MFoDWmhzwxc/edit#heading=h.o136qzcs1wn) вместе с API iikoCloud одновременно, либо можно написать заявку на добавление требуемого метода, и мы её рассмотрим.

###  Работа с ценами и размерами

iikoCloud API поддерживает размеры и схемы модификаторов.

Однако, данное API **не работает с ценовыми категориями** и временными приказами.
