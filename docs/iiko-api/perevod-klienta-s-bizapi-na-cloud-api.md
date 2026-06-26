* [Подключение CloudAPI](/articles/api-documentations/perevod-klienta-s-bizapi-na-cloud-api/a/h3__95843327)
* [Настройка внешнего меню](/articles/api-documentations/perevod-klienta-s-bizapi-na-cloud-api/a/h3_339060030)
* [Дополнительные н астройки для iikoCloud API](/articles/api-documentations/perevod-klienta-s-bizapi-na-cloud-api/a/h3_1294918966)
* [Настройки для перехода с API delivery на Cloud.API](/articles/api-documentations/perevod-klienta-s-bizapi-na-cloud-api/a/h2__2098681770)
* [Настройки для торговых предприятий использующих Cloud тариф](/articles/api-documentations/perevod-klienta-s-bizapi-na-cloud-api/a/h3_1411147565)
* [Настройка для торговых предприятий использующих LT Сервер](/articles/api-documentations/perevod-klienta-s-bizapi-na-cloud-api/a/h3_276434405)
* [Обновление компонентов Cloud API](/articles/api-documentations/perevod-klienta-s-bizapi-na-cloud-api/a/h2__1276555453)
* [Настройка и политики](/articles/api-documentations/perevod-klienta-s-bizapi-na-cloud-api/a/h2__1834782851)
* [Как проверить, что ресторан на Cloud-тарифе](/articles/api-documentations/perevod-klienta-s-bizapi-na-cloud-api/a/h3__938265538)
* [Особенности работы с колл-центром (КЦ)](/articles/api-documentations/perevod-klienta-s-bizapi-na-cloud-api/a/h2__862411501)

Если клиент, для работы с доставочными заказами, ранее уже использовал Biz.API, но не использовал iikoCloudAPI, то ему необходимо будет:

1.	подключить iikoCloud API;

2.	настроить внешнее меню;

3.	переключить агрегаторов доставки на работу через iikoCloud;

4.	доработать собственный сайт (мобильное приложение) на работу через iikoCloud.

****

### **Подключение CloudAPI**

Любой клиент может подключить CloudAPI, для этого необходимо зайти в ЛК iikoWeb (это можно сделать из iikoOffice: Главное меню – Обмен данными – Настройка iikoTransport), далее cогласно [инструкции подключения iikoCloud API](/articles/iikoweb-start/iikocloudapi).

**![](/resources/Storage/api-documentations/perevod-klienta-s-biz-api-na-cloud-api-2023-05-04.png)**

### **Настройка внешнего меню**

В программе есть несколько внешних меню:

* в iikoOffice (одно единое меню для всех внешних потребителей, цены только по базовому прайсу),
* в iikoWeb (одно на всех или множество разных меню (каждое для своего потребителя) с возможностью гибкой настройки цен).

**Ограничения для клиентов НЕ на Cloud-тарифах:**

1. Перед подключением iikoCloud API необходимо заказать лицензии на каждый ресторан, который будет принимать заказы через API;
2. Нельзя использовать функционал внешних меню в iikoWeb;

### **Дополнительные настройки для iikoCloud API**

1) Для группы торгового предприятия, которая будет принимать и обрабатывать заказы, необходимо проверить настроен ли Главный терминал.
![](/resources/Storage/api-documentations/perevod-klienta-s-biz-api-na-cloud-api-2023-05-04-1.png)

2) Настройка типа оплаты для внешних заказов происходит стандартным образом, через Chain или RMS ([внешний тип оплаты](/articles/api-documentations/nastroyka-vneshnego-tipa-oplaty)).

3) Для корректной сортировки в отчетах заказов из разных источников можно задать дополнительные [типы заказа](/articles/iikodelivery-8-2/topic-49).

4)	Для работы с городами и улицами на доставочных заказах их необходимо настроить через стандартные настройки iikoDelivery:

* Справочник [городов](/articles/iikodelivery-8-2/topic-35);
* Справочник [улиц](/articles/iikodelivery-8-2/topic-36);
С версии РМС 8.9.7 и выше можно использовать Flex Address (новый формат адреса).

## Настройки для перехода с API delivery на Cloud.API

### **Настройки для торговых предприятий использующих Cloud тариф**

1. Выполнить настройки внешнего меню iikoWEB по пользовательской документации - [здесь](/articles/api-documentations/external-menu/a/h3__541222395).
2. Произвести настройки учетных записей для работы с [API](/articles/api-documentations/connect-to-iiko-cloud).

Для работы лояльности обязательно до версии 8.3 РМС актуализировать [внешнее меню](/articles/api-documentations/~rabota-s-nomenklaturoy) в бек офисе на всех точках сети для расчета лояльности. Достаточно только факта нахождения блюда во внешнем меню бека - без описания, изображения. Включить репликацию по всей сети для внешнего меню необходимо обращением в поддержку.

### **Настройка для торговых предприятий использующих LT Сервер**

Внешнее меню настраивается в бек офисе и забирается методом /api/1/nomenclature. Номенклатуру можно задать только на одном "эталонном" РМС без дополнительной репликации по сети, описание настройки [здесь.](/articles/api-documentations/~rabota-s-nomenklaturoy)

Если по сети торгового предприятия цены различаются или используется лояльность iikoCard, то номенклатуру нужно добавлять во [внешнее меню](/articles/api-documentations/~rabota-s-nomenklaturoy) бека на всех точках сети до РМС.

## **Обновление компонентов Cloud API**

Основные компоненты Cloud API:

1. облачная часть (в том числе API) - автоматически обновляется, обычно 1-2 раза в неделю;

1. плагин на сервере ресторана - автоматически обновляется, обычно 1 раз в квартал;

1. плагин на кассе ресторана - автоматически обновляется, обычно 1-2 раза в месяц;

Ручное вмешательство в процесс обновления каких-либо компонентов запрещено. Отключать автоматическое обновление плагинов нельзя.

## Настройка и политики

**Документация Cloud API**
 
[iiko Cloud API](/smart/project-iikoweb/iikocloudapi)

**Поддерживаемые версии**
 
[Блокировки и ограничения](/articles/api-documentations/~ogranichenie-i-limity)
 
### Как проверить, что ресторан на Cloud-тарифе

```json
/api/1/organizations в теле
{
"organizationIds": [],
"returnAdditionalInfo": true,
"includeDisabled": false
}
В ответе:
"isCloud": true/false

```

```json
/api/1/organizations в теле
{
"organizationIds": [],
"returnAdditionalInfo": true,
"includeDisabled": false
}
В ответе:
"isCloud": true/false

```


## Особенности работы с колл-центром (КЦ)

#### Cloud CC

Если процессы клиента подразумевают полноценную обработку всех доставочных заказов операторами в КЦ и преимущественно ручной выбор терминальной группы, по аналогии как это было в старом КЦ при работе с api delivery, то советуем воспользоваться функционалом [черновиков](https://api-ru.iiko.services/#tag/Drafts). Черновики будут доступны для редактирования и распределения по терминалам вручную операторами Cloud CC. Ограничение - черновики доступны только Cloud клиентам с настроенным внешним меню веба.

Если процессы клиента настроены на автоопределение терминальной группы на этапе создания доставочного заказа, то достаточно начать использовать [Cloud CC](/articles/iikocallcenter/getting-around) для Cloud клиентов. При создании заказа через Cloud API он сразу отобразится в списке заказов клаудного КЦ.

#### Старый КЦ в **back Office**

Не рекомендуем принимать заказы из Cloud API на одну терминальную группу и производить ручное распределение заказов операторами по точкам через офисный КЦ. Рекомендуем отказаться от этой схемы работы в пользу автоподстановки терминальной группы на этапе создания заказа [методом определения подходящей терминальной группы](https://api-ru.iiko.services/docs#tag/Delivery-restrictions/paths/~1api~11~1delivery_restrictions~1allowed/post).

При возникновении вопросов при переходе с Api Delivery на Cloud API см. [статью по диагностике состояния подключения к Cloud API](/articles/api-documentations/~diagnostika-sostoyaniya-podklyucheniya-k-cloud-api)
