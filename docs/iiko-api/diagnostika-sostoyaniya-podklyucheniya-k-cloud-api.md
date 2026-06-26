* [Проверка работоспособности iikoFront](/articles/api-documentations/diagnostika-sostoyaniya-podklyucheniya-k-cloud-api/a/h3__1865005608)
* [Проверка работоспособности API Front](/articles/api-documentations/diagnostika-sostoyaniya-podklyucheniya-k-cloud-api/a/h3_1302876056)
* [Проверка со стороны iikoWEB](/articles/api-documentations/diagnostika-sostoyaniya-podklyucheniya-k-cloud-api/a/h3__541222395)
* [Диагностика подключения сервера РМС](/articles/api-documentations/diagnostika-sostoyaniya-podklyucheniya-k-cloud-api/a/h3__1550294151)
* [Диагностика подключения терминальных групп](/articles/api-documentations/diagnostika-sostoyaniya-podklyucheniya-k-cloud-api/a/h3__443298347)
* [Статистика выгрузки справочников](/articles/api-documentations/diagnostika-sostoyaniya-podklyucheniya-k-cloud-api/a/h3__81553844)
* [История обновлений плагина](/articles/api-documentations/diagnostika-sostoyaniya-podklyucheniya-k-cloud-api/a/h3__536366592)

### Проверка работоспособности **iikoFront**
В нижней части панели iikoFront выбрать кнопку "Дополнения" - Cloud Connection Status.

![](/resources/Storage/api-documentations/knowledgebase/604-2022-10-17.png)

### **Проверка работоспособности API Front**
Необходимо вызвать метод [/api/1/terminal_groups/is_alive](https://api-ru.iiko.services/docs#tag/Terminal-groups/paths/~1api~11~1terminal_groups~1is_alive/post).
Если для фронта приходит признак IsAlive = true - значит, фронт успешно "отстукивается" о себе в iikoTransport.

### Проверка со стороны iikoWEB

В iikoWEB выбрать раздел "Настройки Cloud API" - Организации.

### **Диагностика подключения сервера РМС**

Проверяем подключение:

если подключение на сервер не было установлено (красный кружок) – для диагностики потребуются серверные логи: **startup.log и full.log** и лог серверного транспортного плагина **rms-integration.log**(находится тут iikoRMS\Server\Tomcat9\logs).

Для LT при проблемах начинаем с проверки наличия лицензий Api iikoCloud (Модули REST\_API(2000) и REST\_API\_V3(2400)).

![](/resources/Storage/api-documentations/perevod-klienta-s-biz-api-na-cloud-api/perevod-klienta-s-biz-api-na-cloud-api-2024-03-25-1.png)

### **Диагностика подключения терминальных групп**

Для подключенных терминальных групп (где включена галка работы с транспортом) успешно обменивающиеся группы выделены черным.

При проблемах будут выделены **красным**, если не используются - **серым**, и **оранжевым** - если группа ни разу не обменивалась с транспортом.

Статусы последних заказов по аналогии отмечены цветовыми индикаторами: зеленый - успешно, красный - не успешно, серый - статус заказа в in Progress (т.е. через время таймаута перейдет либо в успешный, либо не успешный статус). При наведении отобразится дата и время создания заказа.

Для разбора проблем логи доступны здесь же (столбец Логи).
![](/resources/Storage/api-documentations/perevod-klienta-s-biz-api-na-cloud-api/perevod-klienta-s-biz-api-na-cloud-api-2024-04-04.png)

### **Статистика выгрузки справочников**

Дата и время, когда была произведена выгрузка справочников в API. Если свежих изменений не было - даты меняться не будут. В зависимости от того откуда выгружаются данные ([подробнее здесь](/articles/api-documentations/trn-general)) потребуются разные доги для решения. Любое поднятие ревизии приводит к выгрузке справочников с сервера. Также работает автовыгрузка с периодичностью раз в 30 минут с РМС.

![](/resources/Storage/api-documentations/perevod-klienta-s-biz-api-na-cloud-api/perevod-klienta-s-biz-api-na-cloud-api-2024-04-04-1.png)

### История обновлений плагина 

В iikoWEB выбрать раздел "Конфигуратор плагинов iikoFront" - список плагинов (временно доступен только на demo)

![](/resources/Storage/api-documentations/knowledgebase/604-2022-10-17-5.png)

Подробнее с проверкой работы через Cloud API можно ознакомиться в [статье](/articles/iikoweb/iikocloudapi/a/h3_129714767).
